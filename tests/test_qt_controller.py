"""Qt bridge behavior without a serial port, physical Flash, or native dialogs."""
from copy import deepcopy
import csv
from pathlib import Path
import struct
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent

from device_studio.protocol import APP_BASE, APP_MAX, package


def app_response(name="ADASLab"):
    return dict(app=name, id={"Smartwatch": 1, "Duello": 2, "ADASLab": 3}.get(name, 4),
                version=1, protocol=1, boot=1, boot_version=2, ready=True, error="",
                state=dict(mode="ACC", ego=2500, lead=1667, gap=5000, ttc=6000,
                           a=-100, fresh=True, ms=0, gpu=12, frames=4))


class FakeDevice:
    """Single-owner fake with controllable blocking to expose close/worker races."""
    def __init__(self, name="ADASLab"):
        self.response = app_response(name)
        self.current = None
        self.calls = []
        self.closed = 0
        self.runtime_error = None
        self.uploads = 0
        self.block_upload = False
        self.upload_entered = threading.Event()
        self.upload_release = threading.Event()
        self.active_calls = 0
        self.max_active_calls = 0
        self.closed_while_active = False

    def detect(self):
        self.calls.append(("detect", threading.get_ident()))
        self.current = deepcopy(self.response)
        return self.current

    def close(self):
        self.closed_while_active |= self.active_calls > 0
        self.closed += 1

    def runtime(self, command, **kwargs):
        self.calls.append((command, threading.get_ident()))
        if self.runtime_error:
            raise self.runtime_error
        response = deepcopy(self.response)
        if command == "PAUSE":
            response["state"].update(mode="PAUSED", a=0)
        elif command.startswith("S:"):
            response["state"]["ms"] = int(command.split(":")[1])
        self.current = response
        return response

    def upload(self, firmware, progress, cancel):
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        self.uploads += 1
        self.upload_entered.set()
        try:
            progress(20, "Test transfer")
            if self.block_upload:
                while not self.upload_release.wait(.005):
                    if cancel.is_set():
                        raise InterruptedError("Test upload cancelled")
            progress(100, "Test ready")
            self.current = deepcopy(self.response)
            return self.current
        finally:
            self.active_calls -= 1

    def enter_boot(self):
        self.calls.append(("enter_boot", threading.get_ident()))
        self.current = dict(app="DeviceBoot", version=2, protocol=1, valid=True,
                            max_app_id=0xfffffffe)
        return self.current

    def run(self):
        return self.detect()


class FakeProgrammer:
    def __init__(self):
        self.inspections = 0
        self.installs = 0

    def inspect(self, **kwargs):
        self.inspections += 1
        return dict(installed=True, version=2, baud=921600)

    def install(self, binary, backup_dir, **kwargs):
        self.installs += 1
        return dict(installed=True, version=2, backup="Backup/test-before.bin")


class QtControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        from device_studio.qt_controller import StudioController
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = FakeDevice()
        self.programmer = FakeProgrammer()
        self.port_patch = patch("serial.tools.list_ports.comports", return_value=[
            SimpleNamespace(device="debug", description="Debug console"),
            SimpleNamespace(device="test-port", description="STLINK-V3"),
        ])
        self.port_patch.start()
        self.addCleanup(self.port_patch.stop)
        self.controller = StudioController(device_factory=lambda port: self.fake,
                                           programmer_api=self.programmer,
                                           start_timers=False)

    def tearDown(self):
        self.fake.upload_release.set()
        self.controller.stopOperation()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.controller.requestClose()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.qt.processEvents()

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.qt.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail("Qt worker did not reach the expected state")

    def connect(self, name="ADASLab"):
        self.fake.response = app_response(name)
        self.controller.connectDevice()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertTrue(self.controller.state["connected"])
        return self.controller.state

    def firmware_file(self):
        data = bytearray(2048)
        struct.pack_into("<2I", data, 0, 0x2026fff0, APP_BASE + 0x421)
        struct.pack_into("<4I", data, 0x400, 0x44415631, 3, 1, 1)
        binary = self.root / "ADASLab.bin"
        binary.write_bytes(data)
        output = self.root / "ADASLab.dfw"
        package(binary, output, "ADASLab")
        return output

    def test_stlink_port_is_preferred_and_offline_actions_are_gated(self):
        state = self.controller.state
        self.assertEqual(state["ports"][state["portIndex"]]["device"], "test-port")
        self.assertFalse(state["connected"])
        self.controller.sendCommand("STATUS")
        self.controller.duelloCommand("FIRE")
        self.controller.startExperiment()
        self.assertFalse(self.controller.state["busy"])
        self.assertEqual(self.fake.calls, [])

    def test_detect_runs_off_ui_thread_and_updates_connected_identity(self):
        ui_thread = threading.get_ident()
        changes = []
        self.controller.stateChanged.connect(lambda: changes.append(threading.get_ident()))
        state = self.connect()
        self.assertEqual(state["app"], "ADASLab")
        self.assertEqual(state["page"], "adas")
        self.assertNotEqual(self.fake.calls[0][1], ui_thread)
        self.assertTrue(changes)
        self.assertTrue(all(thread == ui_thread for thread in changes))

    def test_busy_notification_cannot_reenter_another_job(self):
        attempted = []
        def request_during_notification():
            if self.controller.state["busy"] and not attempted:
                attempted.append(True)
                self.controller.inspectBootloader()
        self.controller.stateChanged.connect(request_during_notification)
        self.connect()
        self.assertEqual(attempted, [True])
        self.assertEqual(self.programmer.inspections, 0)

    def test_application_identity_routes_to_its_controls(self):
        for app, page in (("Duello", "duello"), ("Smartwatch", "firmware"),
                          ("ThirdApp", "console")):
            with self.subTest(app=app):
                state = self.connect(app)
                self.assertEqual(state["page"], page)
                self.controller.disconnectDevice()
                self.wait_until(lambda: not self.controller.state["connected"] and
                                not self.controller.state["busy"])

    def test_worker_failure_clears_identity_and_stale_control_eligibility(self):
        self.connect("Duello")
        self.fake.runtime_error = TimeoutError("Test USB disconnect")
        self.controller.sendCommand("STATUS")
        self.wait_until(lambda: not self.controller.state["busy"])
        state = self.controller.state
        self.assertFalse(state["connected"])
        self.assertFalse(state["running"])
        self.assertNotEqual(state["app"], "Duello")
        before = len(self.fake.calls)
        self.controller.duelloCommand("FIRE")
        self.assertEqual(len(self.fake.calls), before)

    def test_bootloader_state_cannot_start_experiment_or_duello_action(self):
        self.fake.response = dict(app="DeviceBoot", version=2, protocol=1, valid=True)
        self.controller.connectDevice()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(self.controller.state["app"], "DeviceBoot")
        before = len(self.fake.calls)
        self.controller.startExperiment()
        self.controller.duelloCommand("DRAW")
        self.assertFalse(self.controller.state["running"])
        self.assertEqual(len(self.fake.calls), before)

    def test_upload_requires_confirmation_and_cancel_leaves_flash_untouched(self):
        self.connect()
        self.controller.loadFirmware(str(self.firmware_file()))
        self.controller.requestUpload()
        self.assertTrue(self.controller.state["confirmation"]["visible"])
        self.assertEqual(self.fake.uploads, 0)
        self.assertFalse(self.controller.state["busy"])
        self.controller.confirmAction(False)
        self.assertFalse(self.controller.state["confirmation"]["visible"])
        self.assertEqual(self.fake.uploads, 0)

    def test_confirmed_upload_reports_progress_and_completion(self):
        self.connect()
        self.controller.loadFirmware(str(self.firmware_file()))
        self.controller.requestUpload()
        self.controller.confirmAction(True)
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(self.fake.uploads, 1)
        self.assertEqual(self.controller.state["progress"], 100)
        self.assertEqual(self.controller.state["app"], "ADASLab")

    def test_invalid_selection_clears_previous_valid_firmware(self):
        self.controller.loadFirmware(str(self.firmware_file()))
        self.assertTrue(self.controller.state["firmwarePath"])
        invalid = self.root / "broken.dfw"
        invalid.write_bytes(b"not a firmware package")
        self.controller.loadFirmware(str(invalid))
        self.assertFalse(self.controller.state["firmwarePath"])
        self.connect()
        self.controller.requestUpload()
        self.assertFalse(self.controller.state["confirmation"]["visible"])
        self.assertEqual(self.fake.uploads, 0)

    def test_bootloader_install_requires_separate_confirmation(self):
        binary = self.root / "DeviceBoot.bin"
        data = bytearray(b"\xff" * 0x7f20)
        struct.pack_into("<2I", data, 0, 0x2026fff0, 0x08000421)
        struct.pack_into("<8I", data, 0x7f00, 0x44425631, 2, APP_BASE, APP_MAX,
                         1, 0x481, 921600, 0xfffffffe)
        binary.write_bytes(data)
        self.controller.loadBootloader(str(binary))
        self.assertTrue(self.controller.state["confirmation"]["visible"])
        self.assertEqual(self.programmer.installs, 0)
        self.controller.confirmAction(False)
        self.assertEqual(self.programmer.installs, 0)

    def test_cancel_keeps_single_serial_owner_and_defers_close(self):
        self.connect()
        self.controller.loadFirmware(str(self.firmware_file()))
        self.fake.block_upload = True
        self.controller.requestUpload()
        self.controller.confirmAction(True)
        self.wait_until(self.fake.upload_entered.is_set)
        self.assertTrue(self.controller.state["busy"])
        self.controller.sendCommand("STATUS")
        self.controller.inspectBootloader()
        self.controller.disconnectDevice()
        self.assertEqual(self.programmer.inspections, 0)
        self.assertEqual(self.fake.closed, 0)
        self.assertFalse(self.controller.requestClose())
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertFalse(self.fake.closed_while_active)
        self.assertEqual(self.fake.max_active_calls, 1)

    def test_close_during_busy_notification_cancels_before_upload_starts(self):
        self.connect()
        self.controller.loadFirmware(str(self.firmware_file()))
        self.controller.requestUpload()
        close_results = []
        shutdown = []
        self.controller.shutdownReady.connect(lambda: shutdown.append(True))
        def close_during_notification():
            state = self.controller.state
            if state["busy"] and state["operation"] == "upload" and not close_results:
                # Reserve a marker before requestClose publishes another state.
                close_results.append(None)
                close_results[0] = self.controller.requestClose()
        self.controller.stateChanged.connect(close_during_notification)
        self.controller.confirmAction(True)
        self.wait_until(lambda: bool(shutdown))
        self.assertEqual(close_results, [False])
        self.assertEqual(self.fake.uploads, 0)
        self.assertFalse(self.fake.closed_while_active)
        self.assertEqual(self.fake.closed, 1)

    def test_experiment_pauses_before_returning_serial_ownership(self):
        self.connect()
        self.controller.startExperiment()
        self.wait_until(lambda: sum(command.startswith("S:") for command, _ in
                                    self.fake.calls) >= 2)
        self.assertTrue(self.controller.state["running"])
        self.controller.sendCommand("STATUS")
        self.assertFalse(any(command == "STATUS" for command, _ in self.fake.calls))
        self.controller.stopOperation()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertFalse(self.controller.state["running"])
        self.assertTrue(self.controller.state["connected"])
        self.assertEqual(sum(command == "PAUSE" for command, _ in self.fake.calls), 1)

    def test_csv_export_preserves_measurement_columns_and_values(self):
        self.connect()
        self.controller.startExperiment()
        self.wait_until(lambda: sum(command.startswith("S:") for command, _ in
                                    self.fake.calls) >= 2)
        self.controller.stopOperation()
        self.wait_until(lambda: not self.controller.state["busy"])
        output = self.root / "measurements.csv"
        with patch("device_studio.qt_controller.QFileDialog.getSaveFileName",
                   return_value=(str(output), "CSV (*.csv)")):
            self.controller.exportCsv()
        with output.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            rows = list(reader)
        self.assertEqual(reader.fieldnames,
                         ["cycle", "sim_s", "ego_kmh", "lead_kmh", "gap_m",
                          "accel_mps2", "ttc_ms", "mode", "rtt_ms", "gpu", "frames"])
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(float(rows[0]["sim_s"]), 0)
        self.assertEqual(float(rows[0]["ego_kmh"]), 90)
        self.assertEqual(float(rows[0]["gap_m"]), 70)
        self.assertEqual(float(rows[0]["accel_mps2"]), -1)
        self.assertEqual(rows[0]["mode"], "ACC")
        self.assertGreater(float(rows[1]["sim_s"]), float(rows[0]["sim_s"]))

    def test_generic_boot_command_uses_boot_transition_and_updates_identity(self):
        self.connect()
        self.controller.sendCommand("BOOT")
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(self.controller.state["app"], "DeviceBoot")
        self.assertEqual(self.controller.state["page"], "firmware")
        self.assertEqual(sum(command == "enter_boot" for command, _ in self.fake.calls), 1)
        self.assertFalse(any(command == "BOOT" for command, _ in self.fake.calls))

    def test_all_duello_commands_are_dispatched_only_to_duello(self):
        self.connect("Duello")
        commands = ("DRAW", "FIRE", "HOLSTER", "RELOAD", "WALK", "STOP", "RESET")
        for command in commands:
            self.controller.duelloCommand(command)
            self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual([command for command, _ in self.fake.calls if command in commands],
                         list(commands))
        before = len(self.fake.calls)
        self.controller.duelloCommand("ERASE")
        self.assertEqual(len(self.fake.calls), before)
        self.controller.disconnectDevice()
        self.wait_until(lambda: not self.controller.state["connected"])
        self.connect("ADASLab")
        before = len(self.fake.calls)
        self.controller.duelloCommand("FIRE")
        self.assertEqual(len(self.fake.calls), before)

    def test_experiment_options_reject_invalid_values(self):
        initial = self.controller.state
        self.controller.setOption("targetKmh", 201)
        self.controller.setOption("headwayMs", 799)
        self.controller.setOption("scenario", "unknown")
        state = self.controller.state
        self.assertEqual(state["targetKmh"], initial["targetKmh"])
        self.assertEqual(state["headwayMs"], initial["headwayMs"])
        self.assertEqual(state["scenario"], initial["scenario"])

    def test_collision_remains_visible_after_runner_pause(self):
        self.connect()
        fake = self.fake
        class CollisionRunner:
            def __init__(self, device, config, stop, emit):
                self.emit = emit
            def run(self):
                response = fake.runtime('S:50:2500:0:0:9:0')
                self.emit(dict(response=response, seconds=.05, gap=0., cycle=1,
                               rtt_ms=30., overruns=0, collision=True, present=True))
                fake.runtime('PAUSE')
                return response
        with patch('device_studio.qt_controller.Runner', CollisionRunner):
            self.controller.startExperiment()
            self.wait_until(lambda: not self.controller.state['busy'])
        state = self.controller.state
        self.assertTrue(state['connected'])
        self.assertFalse(state['running'])
        self.assertTrue(state['telemetry']['collision'])
        self.assertEqual(state['telemetry']['mode'], 'COLLISION')
        self.assertIn('Çarpışma', state['telemetry']['modeLabel'])
        self.assertIn('Çarpışma', state['statusMessage'])


if __name__ == "__main__":
    unittest.main()
