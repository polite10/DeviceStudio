"""GitHub feed and NOR update flow against a simulated DeviceBoot; no network or board."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import zlib

from PySide6.QtCore import QCoreApplication

from device_studio import updates
from device_studio.protocol import (ABORT, APP_BASE, CATALOG, HELLO, INSTALL, RUN, STORE_BEGIN, STORE_DATA,
                                    STORE_FINISH, BootStatusError, Firmware, ProtocolError, package)
from device_studio.qt_controller import StudioController

NAMES = {1: 'Smartwatch', 2: 'Duello', 3: 'ADASLab'}


def binary(app_id, version, fill=0):
    data = bytearray(bytes([fill]) * 0x1200)
    struct.pack_into('<II', data, 0, 0x20010000, APP_BASE + 0x801)
    struct.pack_into('<IIII', data, 0x400, 0x44415631, app_id, version, 1)
    return bytes(data)


def dfw_bytes(app_id, version, fill=0):
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / 'x.bin'
        source.write_bytes(binary(app_id, version, fill))
        target = Path(folder) / 'x.dfw'
        package(source, target, NAMES[app_id])
        return target.read_bytes()


def firmware(app_id, version, fill=0):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'x.dfw'
        path.write_bytes(dfw_bytes(app_id, version, fill))
        return Firmware.load(path)


def entry(fw, slot):
    m = fw.manifest
    return dict(slot=slot, id=m['id'], version=m['version'], size=m['size'], crc=m['crc32'])


class Board:
    """DeviceBoot semantics that matter: header written last, STORE_BEGIN erases first."""
    def __init__(self, slots=(), app=None, valid=True):
        self.slots = {s['slot']: dict(s) for s in slots}
        self.app = app  # (id, version) of the internal application.
        self.valid = valid
        self.in_boot = False
        self.current = None
        self.ops = []
        self.store = None
        self.fail_data_at = None
        self.lose_power_after_finish = False

    def close(self):
        pass

    def detect(self):
        self.current = self._runtime_reply() if not self.in_boot else self._hello()
        return self.current

    def _runtime_reply(self):
        return dict(app=NAMES[self.app[0]], id=self.app[0], version=self.app[1], protocol=1, boot=1, boot_version=4, state={})

    def _hello(self):
        return dict(app='DeviceBoot', version=4, protocol=1, valid=self.valid, catalog=True,
                    image_id=self.app[0] if self.app else 0)

    def runtime(self, command, timeout=2):
        self.ops.append(command)
        if self.in_boot:
            raise TimeoutError
        self.current = self._runtime_reply()
        return self.current

    def enter_boot(self):
        self.in_boot = True
        self.current = self._hello()
        return self.current

    def wait_runtime(self, seconds=12):
        self.in_boot = False
        self.current = self._runtime_reply()
        return self.current

    def run(self):
        self.boot(RUN)
        return self.wait_runtime()

    def boot(self, command, payload=b'', timeout=3, retries=2):
        assert self.in_boot
        self.ops.append(command)
        if command == HELLO:
            return self._hello()
        if command == CATALOG:
            slot = struct.unpack('<I', payload)[0]
            if slot not in self.slots:
                raise BootStatusError(2)
            return {k: v for k, v in self.slots[slot].items()}
        if command == STORE_BEGIN:
            slot, size, crc, app_id, version, _ = struct.unpack('<5I28s', payload)
            self.slots.pop(slot, None)
            self.store = dict(slot=slot, size=size, crc=crc, id=app_id, version=version, data=bytearray())
            return {}
        if command == STORE_DATA:
            offset = struct.unpack_from('<I', payload)[0]
            if self.fail_data_at is not None and offset >= self.fail_data_at:
                raise TimeoutError('USB koptu')
            self.store['data'] += payload[4:]
            return dict(written=len(self.store['data']))
        if command == STORE_FINISH:
            s = self.store
            assert zlib.crc32(bytes(s['data'])) == s['crc'] and len(s['data']) == s['size']
            self.slots[s['slot']] = dict(slot=s['slot'], id=s['id'], version=s['version'], size=s['size'], crc=s['crc'])
            self.store = None
            return dict(verified=True)
        if command == ABORT:
            self.store = None
            return dict(aborted=True)
        if command == INSTALL:
            s = self.slots[struct.unpack('<I', payload)[0]]
            self.app = (s['id'], s['version'])
            self.valid = True
            return dict(installing=True)
        if command == RUN:
            assert self.valid
            return dict(starting=True)
        raise AssertionError(command)


class ClassifyTest(unittest.TestCase):
    def test_statuses(self):
        new = firmware(2, 2)
        same = entry(new, 1)
        older = dict(same, version=1, crc=1)
        run = ('Duello', 2)
        self.assertEqual(updates.classify(new, [same], run), 'current')
        self.assertEqual(updates.classify(new, [older], run), 'update')
        self.assertEqual(updates.classify(new, [dict(same, crc=1)], run), 'different')
        self.assertEqual(updates.classify(new, [dict(same, version=9, crc=1)], run), 'newer')
        self.assertEqual(updates.classify(new, [], run), 'missing')
        self.assertEqual(updates.classify(new, [same, dict(older, slot=4)], run), 'cleanup')
        self.assertEqual(updates.classify(new, [same], ('Duello', 1)), 'install')

    def test_unread_card_uses_only_the_running_version(self):
        new = firmware(2, 2)
        self.assertEqual(updates.classify(new, None, ('Duello', 1)), 'update')
        self.assertEqual(updates.classify(new, None, ('Duello', 2)), 'unknown')
        self.assertEqual(updates.classify(new, None, ('Duello', 3)), 'newer')
        self.assertEqual(updates.classify(new, None, ('ADASLab', 1)), 'unknown')
        self.assertEqual(updates.classify(new, None, None), 'unknown')


class ApplyTest(unittest.TestCase):
    def test_new_image_goes_to_free_slot_and_old_is_erased_after_verify(self):
        old, new = firmware(2, 1), firmware(2, 2, fill=7)
        board = Board([entry(firmware(1, 1), 0), entry(old, 1), entry(firmware(3, 3), 2)], app=(3, 3))
        board.detect()
        result = updates.apply_updates(board, [new])
        self.assertEqual(board.slots[3]['version'], 2)
        self.assertNotIn(1, board.slots)
        self.assertLess(board.ops.index(STORE_FINISH), len(board.ops) - 1 - board.ops[::-1].index(ABORT))
        self.assertEqual(board.app, (3, 3), 'another application keeps running')
        self.assertNotIn(INSTALL, board.ops)
        self.assertIn(RUN, board.ops)
        self.assertEqual(result['stored'], 1)
        self.assertEqual({s['slot'] for s in result['slots']}, {0, 2, 3})

    def test_running_application_is_installed(self):
        old, new = firmware(3, 3), firmware(3, 4, fill=1)
        board = Board([entry(old, 2)], app=(3, 3))
        board.detect()
        result = updates.apply_updates(board, [new])
        self.assertEqual(board.app, (3, 4))
        self.assertEqual(result['response']['version'], 4)
        self.assertNotIn(RUN, board.ops)

    def test_interrupted_upload_keeps_old_copy_and_returns_to_app(self):
        old, new = firmware(2, 1), firmware(2, 2, fill=7)
        board = Board([entry(old, 1)], app=(3, 3))
        board.detect()
        board.fail_data_at = 1024
        with self.assertRaises(TimeoutError):
            updates.apply_updates(board, [new])
        self.assertEqual(board.slots, {1: entry(old, 1)})
        self.assertFalse(board.in_boot)

    def test_cancel_keeps_old_copy(self):
        old, new = firmware(2, 1), firmware(2, 2, fill=7)
        board = Board([entry(old, 1)], app=(3, 3))
        board.detect()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            updates.apply_updates(board, [new], cancel=cancel)
        self.assertEqual(board.slots, {1: entry(old, 1)})
        self.assertIn(ABORT, board.ops)

    def test_full_catalog_overwrites_own_slot_and_unrelated_app_is_refused(self):
        filler = [entry(firmware(1, 1), s) for s in range(6)]
        old = entry(firmware(2, 1), 6)
        board = Board(filler + [old], app=(1, 1))
        board.detect()
        updates.apply_updates(board, [firmware(2, 2, fill=7)])
        self.assertEqual(board.slots[6]['version'], 2)
        board = Board([entry(firmware(1, 1), s) for s in range(7)], app=(1, 1))
        board.detect()
        with self.assertRaises(ProtocolError):
            updates.apply_updates(board, [firmware(2, 2)])

    def test_several_packages_get_distinct_slots(self):
        board = Board([entry(firmware(1, 1), 0), entry(firmware(2, 1), 1)], app=(1, 1))
        board.detect()
        updates.apply_updates(board, [firmware(1, 2, fill=1), firmware(2, 2, fill=2), firmware(3, 1, fill=3)])
        self.assertEqual(sorted((s['id'], s['version']) for s in board.slots.values()), [(1, 2), (2, 2), (3, 1)])
        self.assertEqual(board.app, (1, 2))

    def test_leftover_copy_is_cleaned_without_rewriting(self):
        new = firmware(2, 2)
        board = Board([dict(entry(new, 1), version=1, crc=5), entry(new, 4)], app=(3, 3))
        board.detect()
        updates.apply_updates(board, [new])
        self.assertEqual(list(board.slots), [4])
        self.assertNotIn(STORE_DATA, board.ops)

    def test_recovery_board_installs_when_no_app_is_valid(self):
        board = Board([], app=None, valid=False)
        board.in_boot = True
        board.detect()
        updates.apply_updates(board, [firmware(3, 1)])
        self.assertEqual(board.app, (3, 1))

    def test_old_bootloader_is_refused_before_any_write(self):
        board = Board([], app=(3, 3))
        board.detect()
        board._hello = lambda: dict(app='DeviceBoot', version=2, protocol=1, valid=True, catalog=False, image_id=3)
        with self.assertRaises(ProtocolError):
            updates.apply_updates(board, [firmware(2, 2)])
        self.assertNotIn(STORE_BEGIN, board.ops)


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def git_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


class FeedTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.blobs = {}
        self.requests = []

    def opener(self, request, timeout):
        self.requests.append(request.full_url)
        self.assertNotIn('Authorization', request.headers)
        if '/contents/' in request.full_url:
            self.assertTrue(request.full_url.endswith('ref=main'))
            return Reply(json.dumps(self.listing).encode())
        return Reply(self.blobs[request.full_url.rsplit('/', 1)[1]])

    def publish(self, **packages):
        self.listing = [dict(name='README.txt', sha='0' * 40)]
        for name, data in packages.items():
            sha = git_sha(data)
            self.blobs[sha] = data
            self.listing.append(dict(name=name + '.dfw', sha=sha))

    def test_download_then_cache(self):
        self.publish(Duello=dfw_bytes(2, 1), ADASLab=dfw_bytes(3, 3))
        feed = updates.Feed(self.folder.name, opener=self.opener)
        packages, problems = feed.check()
        self.assertEqual(problems, [])
        self.assertEqual(sorted(packages), [2, 3])
        self.requests.clear()
        feed.check()
        self.assertEqual(len(self.requests), 1, 'unchanged packages are not downloaded again')

    def test_corrupt_download_and_wrong_name_are_rejected(self):
        good = dfw_bytes(2, 1)
        self.publish(Duello=good, ADASLab=dfw_bytes(1, 1))
        self.blobs[git_sha(good)] = good + b'x'
        packages, problems = updates.Feed(self.folder.name, opener=self.opener).check()
        self.assertEqual(packages, {})
        self.assertEqual(len(problems), 2)
        self.assertEqual(list(Path(self.folder.name).glob('*.tmp')), [])

    def test_rate_limit_and_offline_messages(self):
        def limited(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, 'x', {}, None)
        with self.assertRaisesRegex(ProtocolError, 'sınırı'):
            updates.Feed(self.folder.name, opener=limited).check()
        def offline(request, timeout):
            raise urllib.error.URLError('down')
        with self.assertRaisesRegex(ProtocolError, 'ulaşılamadı'):
            updates.Feed(self.folder.name, opener=offline).check()


class FakeFeed:
    def __init__(self, packages):
        self.packages = packages

    def check(self):
        return self.packages, []


class ControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def pump(self, condition):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self.app.processEvents()
            if condition():
                return
            time.sleep(.005)
        self.fail('Condition not reached')

    def controller(self, board, packages):
        c = StudioController(device_factory=lambda port: board, start_timers=False, update_feed=FakeFeed(packages))
        c._state.update(ports=[dict(device='X', label='X')], portIndex=0)
        self.addCleanup(c.shutdown)
        return c

    def test_check_read_and_update(self):
        new = firmware(2, 2, fill=7)
        board = Board([entry(firmware(2, 1), 1), entry(firmware(3, 3), 2)], app=(3, 3))
        c = self.controller(board, {2: new, 3: firmware(3, 3)})
        c.checkUpdates()
        self.pump(lambda: c.state['updates'])
        self.assertFalse(any(item['canUpdate'] for item in c.state['updates']))
        self.assertEqual(c.state['updates'][0]['statusText'], 'Kartı okuyun')
        self.assertEqual(board.ops, [], 'a GitHub check does not touch the board')
        c.connectDevice()
        self.pump(lambda: c.state['connected'] and not c.state['busy'])
        c.readCardCatalog()
        self.pump(lambda: c.state['updates'][0]['status'] == 'update' and not c.state['busy'])
        c.requestUpdate('Duello')
        self.assertTrue(c.state['confirmation']['visible'])
        c.confirmAction(True)
        self.pump(lambda: c.state['updates'][0]['status'] == 'current' and not c.state['busy'])
        self.assertEqual(c.state['statusTone'], 'success')
        self.assertEqual(c.state['app'], 'ADASLab')

    def test_running_app_is_compared_without_reading_card(self):
        board = Board([], app=(3, 2))
        c = self.controller(board, {3: firmware(3, 3)})
        c.connectDevice()
        self.pump(lambda: c.state['connected'] and not c.state['busy'])
        c.checkUpdates()
        self.pump(lambda: c.state['updates'] and c.state['updates'][0]['canUpdate'])
        self.assertIn('ADASLab', c.state['statusMessage'])
        self.assertEqual(board.boot.__self__.ops, [])

    def test_failed_check_keeps_last_list(self):
        board = Board([], app=(3, 3))
        c = self.controller(board, {3: firmware(3, 3)})
        c.checkUpdates()
        self.pump(lambda: c.state['updates'])
        def fail():
            raise ProtocolError('GitHub’a ulaşılamadı')
        c._feed.check = fail
        c.checkUpdates()
        self.pump(lambda: 'ulaşılamadı' in c.state['updateText'])
        self.assertEqual(len(c.state['updates']), 1)

    def test_update_all_skips_a_build_of_unknown_age(self):
        github, card = firmware(1, 1, fill=1), firmware(1, 1, fill=2)
        board = Board([entry(card, 0), entry(firmware(3, 1), 1)], app=(3, 1))
        c = self.controller(board, {1: github, 3: firmware(3, 2)})
        c.checkUpdates()
        self.pump(lambda: c.state['updates'])
        c.connectDevice()
        self.pump(lambda: c.state['connected'] and not c.state['busy'])
        c.readCardCatalog()
        self.pump(lambda: c.state['updates'][0]['status'] == 'different' and not c.state['busy'])
        self.assertIn('1 güncelleme', c.state['updateText'])
        c.requestUpdate('')
        self.assertIn('ADASLab', c.state['confirmation']['message'])
        self.assertNotIn('Smartwatch', c.state['confirmation']['message'])
        c.confirmAction(True)
        self.pump(lambda: board.app == (3, 2) and not c.state['busy'])
        self.assertEqual(board.slots[0]['crc'], card.manifest['crc32'], 'card build kept')
        c.requestUpdate('Smartwatch')
        self.assertIn('bilinemiyor', c.state['confirmation']['message'])
        c.confirmAction(False)

    def test_update_is_refused_while_disconnected(self):
        c = self.controller(Board([], app=(3, 3)), {3: firmware(3, 3)})
        c.requestUpdate('')
        self.assertFalse(c.state['confirmation']['visible'])
        self.assertEqual(c.state['statusTone'], 'warning')


if __name__ == '__main__':
    unittest.main()
