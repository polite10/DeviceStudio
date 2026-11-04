"""Firmware updates from GitHub. The board has no network, so Studio is its bridge.

The feed is the Firmware folder of the public Studio repository. A package is
compared with the board's NOR catalog by version and CRC, so a rebuild published
without a version bump is still seen. A new image goes to a free NOR slot and the
old copy is erased only after the new one is verified: an interrupted update
leaves the application selectable. This module owns no thread and imports no Qt.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import threading
import urllib.error
import urllib.request

from .protocol import (ABORT, APP_MAX, CATALOG, HELLO, INSTALL, STORE_BEGIN, STORE_DATA, STORE_FINISH,
                       BootStatusError, Firmware, ProtocolError)

REPOSITORY = 'polite10/DeviceStudio'
BRANCH = 'main'
FOLDER = 'Firmware'
SLOT_COUNT = 7
MIN_BOOT_VERSION = 3
INSTALL_SECONDS = 120
_API = f'https://api.github.com/repos/{REPOSITORY}'
_PACKAGE = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,47}\.dfw')
_MAX_DOWNLOAD = APP_MAX + 1024 * 1024


class Feed:
    """Reads the published packages. Unchanged ones come from a local cache."""
    def __init__(self, cache, opener=urllib.request.urlopen):
        self.cache = Path(cache)
        self._open = opener

    def _get(self, url, accept, limit):
        request = urllib.request.Request(url, headers={'User-Agent': 'DeviceStudio-updater', 'Accept': accept})
        try:
            with self._open(request, timeout=20) as response:
                data = response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                raise ProtocolError('GitHub istek sınırı doldu; biraz sonra yeniden denetleyin.') from exc
            raise ProtocolError(f'GitHub {exc.code} döndürdü.') from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProtocolError('GitHub’a ulaşılamadı; internet bağlantısını kontrol edin.') from exc
        if len(data) > limit:
            raise ProtocolError('GitHub cevabı beklenenden büyük.')
        return data

    def _package(self, name, sha):
        path = self.cache / f'{sha}.dfw'
        if not path.is_file():
            data = self._get(f'{_API}/git/blobs/{sha}', 'application/vnd.github.raw', _MAX_DOWNLOAD)
            if hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest() != sha:
                raise ProtocolError(f'{name} indirmesi bozuk.')
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(data)
            os.replace(temporary, path)
        firmware = Firmware.load(path)
        if firmware.manifest['name'] != name[:-4]:
            raise ProtocolError(f'{name} başka bir uygulamanın paketi.')
        return firmware

    def check(self):
        """Return (firmwares by id, per-package problems); raises if GitHub is unreachable."""
        self.cache.mkdir(parents=True, exist_ok=True)
        raw = self._get(f'{_API}/contents/{FOLDER}?ref={BRANCH}', 'application/vnd.github+json', 1024 * 1024)
        try:
            listing = json.loads(raw)
        except ValueError as exc:
            raise ProtocolError('GitHub cevabı okunamadı.') from exc
        if not isinstance(listing, list):
            raise ProtocolError('GitHub cevabı okunamadı.')
        packages, problems, keep = {}, [], set()
        for entry in listing:
            name, sha = entry.get('name', ''), entry.get('sha', '')
            if not _PACKAGE.fullmatch(name) or not re.fullmatch(r'[0-9a-f]{40}', sha):
                continue
            keep.add(f'{sha}.dfw')
            try:
                firmware = self._package(name, sha)
                if firmware.manifest['id'] in packages:
                    raise ProtocolError(f'{name}: uygulama kimliği iki pakette kullanılmış.')
                packages[firmware.manifest['id']] = firmware
            except ProtocolError as exc:
                problems.append(str(exc))
        for stale in self.cache.glob('*.dfw'):
            if stale.name not in keep:
                stale.unlink(missing_ok=True)
        return packages, problems


STATUS_TEXT = dict(update='Güncelleme var', different='GitHub’da farklı derleme', missing='Kartta yok',
                   install='Kurulum gerekli', cleanup='Eski kopya temizlenecek', current='Güncel',
                   newer='Kartta daha yeni', unknown='Kartı okuyun')
ACTIONABLE = frozenset(('update', 'different', 'missing', 'install', 'cleanup'))


def _same(slot, manifest):
    return (slot['version'], slot['size'], slot['crc']) == (manifest['version'], manifest['size'], manifest['crc32'])


def classify(firmware, slots, running):
    """slots is the NOR catalog or None if unread; running is (app name, version) or None."""
    m = firmware.manifest
    here = running[1] if running and running[0] == m['name'] else None
    if slots is None:
        if here is not None and m['version'] > here:
            return 'update'
        return 'newer' if here is not None and m['version'] < here else 'unknown'
    own = [slot for slot in slots if slot['id'] == m['id']]
    if not own:
        return 'missing'
    if any(_same(slot, m) for slot in own):
        if len(own) > 1:
            return 'cleanup'
        return 'install' if here is not None and here != m['version'] else 'current'
    newest = max(slot['version'] for slot in own)
    if m['version'] > newest:
        return 'update'
    return 'different' if m['version'] == newest else 'newer'


def rows(packages, slots, running):
    result = []
    for app_id in sorted(packages):
        m = packages[app_id].manifest
        status = classify(packages[app_id], slots, running)
        own = [slot['version'] for slot in slots or () if slot['id'] == app_id]
        if own:
            card = f'Kartta v{max(own)}'
        elif slots is not None:
            card = '—'
        elif running and running[0] == m['name'] and running[1] is not None:
            card = f'Çalışan v{running[1]}'
        else:
            card = 'Kart okunmadı'
        result.append(dict(name=m['name'], id=app_id, feedVersion=m['version'], card=card, status=status,
                           statusText=STATUS_TEXT[status], canUpdate=status in ACTIONABLE))
    return result


def open_catalog(device):
    """Move to the bootloader, remembering what ran, and read the NOR catalog."""
    current = device.current or device.detect()
    version = current.get('version') if current.get('app') != 'DeviceBoot' else None
    boot = device.enter_boot()
    if boot.get('version', 0) < MIN_BOOT_VERSION or not boot.get('catalog'):
        raise ProtocolError(f'Güncelleme için DeviceBoot v{MIN_BOOT_VERSION} ve okunabilir NOR gerekli.')
    return dict(image_id=boot.get('image_id', 0), valid=bool(boot.get('valid')), running_version=version,
                slots=_read_slots(device))


def _read_slot(device, slot):
    try:
        reply = device.boot(CATALOG, struct.pack('<I', slot))
    except BootStatusError as exc:
        if exc.status == 2:  # Erased or torn header: the slot is free.
            return None
        raise
    return dict(slot=slot, id=reply['id'], version=reply['version'], size=reply['size'], crc=reply['crc'])


def _read_slots(device):
    return [entry for entry in (_read_slot(device, slot) for slot in range(SLOT_COUNT)) if entry]


def _restore(device, card):
    """Return to the application, or stay in recovery if there is none to start."""
    return device.run() if card['valid'] else device.boot(HELLO)


def read_card(device):
    card = open_catalog(device)
    return dict(slots=card['slots'], response=_restore(device, card))


def _store_begin(device, firmware, slot, size, crc, timeout):
    m = firmware.manifest
    device.boot(STORE_BEGIN, struct.pack('<5I28s', slot, size, crc, m['id'], m['version'], m['name'].encode('ascii')),
                timeout=timeout, retries=0)


def _store(device, firmware, slot, sent, total, progress, cancel):
    data = firmware.data
    m = firmware.manifest
    progress(sent / total * 90, f'{m["name"]}: NOR yuvası {slot} hazırlanıyor')
    _store_begin(device, firmware, slot, len(data), m['crc32'], 180)
    for offset in range(0, len(data), 1024):
        if cancel.is_set():
            raise InterruptedError('Güncelleme iptal edildi; kurulu uygulamalar değişmedi.')
        block = data[offset:offset + 1024]
        if device.boot(STORE_DATA, struct.pack('<I', offset) + block).get('written') != offset + len(block):
            raise ProtocolError('Yazılan bayt sayısı uyuşmuyor')
        done = offset + len(block)
        progress((sent + done) / total * 90, f'{m["name"]}: {done:,} / {len(data):,} bayt')
    progress((sent + len(data)) / total * 90, f'{m["name"]}: kart üzerinde doğrulanıyor')
    if not device.boot(STORE_FINISH, timeout=60, retries=0).get('verified'):
        raise ProtocolError('Kart paketi doğrulamadı')
    stored = _read_slot(device, slot)
    if not stored or stored['id'] != m['id'] or not _same(stored, m):
        raise ProtocolError('Karttaki kayıt indirilen paketle eşleşmiyor')
    return stored


def _erase(device, firmware, slot):
    """STORE_BEGIN erases a slot's header first; ABORT then leaves it free."""
    _store_begin(device, firmware, slot, 0x410, 0, 30)
    device.boot(ABORT)
    if _read_slot(device, slot):
        raise ProtocolError(f'NOR yuvası {slot} silinemedi')


def _target(slots, firmware):
    """The slot holding this exact image, else a free one, else this app's own."""
    m = firmware.manifest
    own = [slot for slot in slots if slot['id'] == m['id']]
    exact = next((slot for slot in own if _same(slot, m)), None)
    if exact:
        return exact['slot'], True
    used = {slot['slot'] for slot in slots}
    free = next((slot for slot in range(SLOT_COUNT) if slot not in used), None)
    if free is not None:
        return free, False
    if own:  # No room for two copies: an interruption here loses this NOR copy.
        return min(own, key=lambda slot: slot['version'])['slot'], False
    raise ProtocolError('NOR’da boş yuva yok.')


def _install(device, firmware, slot, progress):
    m = firmware.manifest
    progress(92, f'{m["name"]} kuruluyor; ekran kısa süre kararır')
    if not device.boot(INSTALL, struct.pack('<I', slot), timeout=60, retries=0).get('installing'):
        raise ProtocolError('Kurulum isteği onaylanmadı')
    response = device.wait_runtime(INSTALL_SECONDS)
    if response.get('app') != m['name'] or response.get('version') != m['version']:
        raise ProtocolError('Beklenen uygulama sürümü başlamadı')
    return response


def apply_updates(device, firmwares, progress=lambda percent, text: None, cancel=None):
    """Bring the listed packages onto the board; reinstall the running one if it changed."""
    cancel = cancel or threading.Event()
    card = open_catalog(device)
    slots = list(card['slots'])
    try:
        total = sum(len(f.data) for f in firmwares if not _target(slots, f)[1]) or 1
        sent, chosen, stored = 0, None, 0
        for firmware in firmwares:
            m = firmware.manifest
            slot, present = _target(slots, firmware)
            if not present:
                entry = _store(device, firmware, slot, sent, total, progress, cancel)
                sent += len(firmware.data)
                stored += 1
                slots = [s for s in slots if s['slot'] != slot] + [entry]
            for other in [s for s in slots if s['id'] == m['id'] and s['slot'] != slot]:
                _erase(device, firmware, other['slot'])
                slots.remove(other)
            if m['id'] == card['image_id'] and (not present or card['running_version'] != m['version']):
                chosen = (firmware, slot)
            elif chosen is None and not card['valid']:
                chosen = (firmware, slot)
    except Exception:
        try:
            device.boot(ABORT, timeout=1, retries=0)
            _restore(device, card)
        except Exception:
            pass
        raise
    response = _install(device, *chosen, progress) if chosen else _restore(device, card)
    progress(100, 'Güncelleme tamamlandı')
    return dict(slots=slots, response=response, stored=stored)
