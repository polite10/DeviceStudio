"""Regressions for controls interrupted by periodic telemetry/heartbeat updates."""
from copy import deepcopy
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent


class RefreshDevice:
    def __init__(self):
        self.current = None
        self.commands = []
        self.status_entered = threading.Event()
        self.status_release = threading.Event()
        self.block_status = False
        self.active = 0
        self.max_active = 0
        self.sequence = 0

    def response(self, command):
        self.sequence += 1
        tick = int(command.split(':')[1]) if command.startswith('S:') else 0
        state = dict(mode='PAUSED' if command == 'PAUSE' else 'ACC', ego=2500,
                     lead=1667, gap=5000, ttc=6000, a=0, fresh=True, ms=tick,
                     gpu=self.sequence, frames=self.sequence, error='')
        return dict(app='ADASLab', id=3, version=1, protocol=1, boot=1,
                    boot_version=2, ready=True, error='', state=state)

    def detect(self):
        self.current = self.response('HELLO')
        return self.current

    def close(self):
        pass

    def runtime(self, command, **kwargs):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.commands.append(command)
        try:
            if command == 'STATUS':
                self.status_entered.set()
                if self.block_status:
                    if not self.status_release.wait(3):
                        raise TimeoutError('Test heartbeat remained blocked')
            self.current = self.response(command)
            return self.current
        finally:
            self.active -= 1


class QtRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        from device_studio.qt_controller import StudioController
        self.device = RefreshDevice()
        self.ports = patch('serial.tools.list_ports.comports', return_value=[
            SimpleNamespace(device='refresh-test', description='STLINK-V3')])
        self.ports.start()
        self.addCleanup(self.ports.stop)
        self.controller = StudioController(device_factory=lambda p: self.device,
                                           start_timers=True)
        self.controller.connectDevice()
        self.wait(lambda: self.controller.state['connected'] and
                         not self.controller.state['busy'])

    def tearDown(self):
        self.device.status_release.set()
        self.controller.stopOperation()
        self.wait(lambda: not self.controller.state['busy'] and self.device.active == 0)
        self.controller.requestClose()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.qt.processEvents()

    def wait(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.qt.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail('Qt operation did not reach the expected state')

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.qt.processEvents()
            time.sleep(.005)

    def test_background_heartbeat_never_disables_controls(self):
        structural = []
        self.controller.stateChanged.connect(lambda: structural.append(deepcopy(self.controller.state)))
        self.wait(self.device.status_entered.is_set)
        self.wait(lambda: self.device.active == 0)
        self.pump(.08)
        self.assertFalse(self.controller.state['busy'])
        self.assertFalse(any(state['busy'] for state in structural))
        self.assertEqual(structural, [], 'Measurement-only heartbeat must not reset control models')

    def test_live_experiment_does_not_republish_structural_models(self):
        structural = []
        live = []
        self.controller.startExperiment()
        self.wait(lambda: sum(c.startswith('S:') for c in self.device.commands) >= 2)
        self.controller.stateChanged.connect(lambda: structural.append(True))
        self.controller.liveChanged.connect(lambda: live.append(self.controller.liveState))
        self.pump(.25)
        self.assertTrue(self.controller.state['running'])
        self.assertGreaterEqual(len(live), 2)
        self.assertEqual(structural, [], '20 Hz data must not replace scenario/port model values')

    def test_command_during_heartbeat_is_queued_without_concurrent_uart(self):
        self.device.block_status = True
        self.wait(self.device.status_entered.is_set)
        self.assertFalse(self.controller.state['busy'])
        self.controller.sendCommand('HELLO')
        self.assertNotIn('HELLO', self.device.commands)
        self.device.status_release.set()
        self.wait(lambda: 'HELLO' in self.device.commands and not self.controller.state['busy'])
        self.assertEqual(self.device.max_active, 1)
        self.assertTrue(self.controller.state['connected'])

    def test_start_during_heartbeat_is_queued_without_losing_click(self):
        self.device.block_status = True
        self.wait(self.device.status_entered.is_set)
        self.controller.startExperiment()
        self.device.status_release.set()
        self.wait(lambda: any(c.startswith('S:') for c in self.device.commands))
        self.assertTrue(self.controller.state['running'])
        self.assertEqual(self.device.max_active, 1)


if __name__ == '__main__':
    unittest.main()
