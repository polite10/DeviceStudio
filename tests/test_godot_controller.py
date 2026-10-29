"""Real loopback + Qt focus/worker ownership without physical hardware."""
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent
from device_studio.godot_bridge import GodotBridge
from device_studio.qt_controller import StudioController


class GameDevice:
    def __init__(self):
        self.current=None;self.running=False;self.mode=0;self.acc=0;self.target=2500;self.headway=1800;self.calls=[]
    def detect(self):return self.runtime('J')
    def close(self):pass
    def runtime(self, command, **kwargs):
        self.calls.append(command)
        if command.startswith('G:'):
            _,mode,acc,target,headway=command.split(':')
            self.mode=int(mode);self.acc=int(acc);self.target=int(target);self.headway=int(headway)
        elif command.startswith('H:'):self.running=command=='H:1'
        elif command in ('RESET','PAUSE'):self.running=False
        fields=command.split(':');sample=command.startswith('T:')
        state=dict(mode='MONITOR',ego=int(fields[2]) if sample else 0,lead=0,gap=10000,ttc=-1,a=0,warn=False,
                   fresh=sample,ms=int(fields[1]) if sample else 0,error='',gmode=self.mode,gacc=bool(self.acc),
                   gtarget=self.target,gheadway=self.headway,grun=self.running,grev=0)
        self.current=dict(app='ADASLab',id=3,version=2,boot=1,boot_version=2,state=state)
        return self.current


class GodotControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        self.device=GameDevice();self.peer=None;self.keepalive=True;self.focus_active=True;self.next_beat=0
        with patch('serial.tools.list_ports.comports',return_value=[SimpleNamespace(device='godot-test',description='STLINK')]):
            self.controller=StudioController(device_factory=lambda p:self.device,start_timers=False)
        self.wait(lambda:self.controller._worker is None)
        self.controller.connectDevice();self.wait(lambda:self.controller._worker is None)
        self.bridge=GodotBridge();self.controller._game3d_bridge=self.bridge
        self.peer=socket.create_connection(('127.0.0.1',self.bridge.port),timeout=.5)
        self.send(dict(type='hello',protocol=1,token=self.bridge.token))
        self.send(dict(type='heartbeat',active=True))
        self.wait(lambda:self.controller.gameState['renderer3dConnected'] and self.controller._external_driving_active())
    def send(self,value):
        if value.get('type')=='heartbeat' or (value.get('type')=='action' and value.get('name')=='focus'):
            self.focus_active=value['active']
        self.peer.sendall(json.dumps(value).encode()+b'\n')
    def wait(self,predicate,timeout=3):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.peer and self.keepalive and self.controller._game3d_bridge and time.monotonic()>=self.next_beat:
                try:self.send(dict(type='heartbeat',active=self.focus_active))
                except OSError:pass
                self.next_beat=time.monotonic()+.08
            self.qt.processEvents()
            if predicate():return
            time.sleep(.004)
        self.fail('Controller state did not settle: '+str(self.controller.gameState))
    def start(self):
        self.send(dict(type='action',name='start'))
        self.wait(lambda:self.controller.gameState['elapsed']>=.15)
    def tearDown(self):
        self.keepalive=False
        self.controller.pauseGame();self.wait(lambda:self.controller._worker is None)
        self.controller.requestClose()
        if self.peer:self.peer.close();self.peer=None
        self.controller.deleteLater();self.qt.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.qt.processEvents()
    def test_external_window_can_drive_while_studio_is_inactive(self):
        self.controller.setWindowActive(False);self.start()
        speed=self.controller.gameState['egoKmh']
        self.send(dict(type='input',key='w',pressed=True,repeat=False))
        self.wait(lambda:self.controller.gameState['egoKmh']>speed+1)
        self.controller.focusLost()
        self.assertTrue(self.controller.gameState['running'])
        self.assertTrue(self.controller._game_inputs.sample()['gas'])
    def test_external_focus_loss_releases_and_pauses_even_if_studio_active(self):
        self.start();self.send(dict(type='input',key='w',pressed=True))
        self.wait(lambda:self.controller._game_inputs.sample()['gas'])
        self.send(dict(type='action',name='focus',active=False))
        self.wait(lambda:self.controller._worker is None)
        self.assertFalse(self.controller._game_inputs.sample()['gas'])
        self.assertEqual(self.controller.gameState['status'],'paused')
        self.assertEqual(self.device.calls[-2:],['H:0','PAUSE'])
    def test_input_while_external_inactive_is_not_applied(self):
        self.start();self.send(dict(type='heartbeat',active=False))
        self.wait(lambda:self.controller._worker is None)
        self.send(dict(type='input',key='w',pressed=True))
        self.send(dict(type='action',name='start'))
        self.controller._poll_game_3d()
        self.assertFalse(self.controller.gameState['running'])
        self.assertFalse(self.controller._game_inputs.sample()['gas'])
    def test_stale_external_input_pauses_even_with_active_studio(self):
        self.start();self.send(dict(type='input',key='w',pressed=True))
        self.wait(lambda:self.controller._game_inputs.sample()['gas'])
        self.keepalive=False
        self.wait(lambda:not self.controller.gameState['renderer3dConnected'] and self.controller._worker is None)
        self.assertEqual(self.controller.gameState['status'],'paused')
        self.assertFalse(self.controller._game_inputs.sample()['gas'])
    def test_socket_disconnect_pauses_and_releases_held_gas(self):
        self.start();self.send(dict(type='input',key='w',pressed=True))
        self.wait(lambda:self.controller._game_inputs.sample()['gas'])
        self.peer.close();self.peer=None
        self.wait(lambda:not self.controller.gameState['renderer3dConnected'] and self.controller._worker is None)
        self.assertFalse(self.controller._game_inputs.sample()['gas'])
    def test_malformed_peer_cannot_apply_prior_setting_in_same_batch(self):
        self.peer.sendall(b'{"type":"setting","key":"mode","value":"off"}\n{bad}\n')
        self.wait(lambda:not self.controller.gameState['renderer3dConnected'])
        self.assertEqual(self.controller.gameState['mode'],'active')
    def test_card_start_works_with_external_focus_only(self):
        self.controller.setWindowActive(False)
        self.device.running=True;self.controller._heartbeat()
        self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.assertTrue(self.controller.gameState['running'])
    def test_queued_external_start_is_rechecked_after_focus_loss(self):
        self.controller.setWindowActive(False)
        entered=threading.Event();release=threading.Event()
        def delayed():
            entered.set();release.wait(2);return self.device.runtime('J')
        self.controller._job('heartbeat',delayed)
        self.assertTrue(entered.wait(1))
        self.send(dict(type='action',name='start'))
        self.wait(lambda:bool(self.controller._deferred))
        self.controller.setWindowActive(True)
        self.send(dict(type='heartbeat',active=False))
        self.wait(lambda:not self.controller._external_driving_active())
        release.set();self.wait(lambda:self.controller._worker is None)
        self.assertFalse(self.controller.gameState['running'])
        self.assertNotIn('H:1',self.device.calls)
    def test_process_exit_pauses_game(self):
        self.start()
        self.controller._game3d_process=SimpleNamespace(poll=lambda:7)
        self.wait(lambda:self.controller._game3d_bridge is None and self.controller._worker is None)
        self.assertFalse(self.controller.gameState['running'])
    def test_missing_engine_reports_actionable_error(self):
        with patch('device_studio.qt_controller.find_godot',return_value=None):self.controller.openGame3D()
        self.assertFalse(self.controller.gameState['renderer3dAvailable'])
        self.assertIn('GODOT_BIN',self.controller.gameState['renderer3dMessage'])
    def test_launcher_and_close_own_only_the_godot_process(self):
        class Process:
            def __init__(self):self.exited=False;self.returncode=None
            def poll(self):
                self.returncode=0 if self.exited else None
                return self.returncode
            def terminate(self):self.exited=True
            def wait(self,timeout):return 0
        importer=Process();process=Process()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);project=root/'godot/adas_drive/project.godot'
            project.parent.mkdir(parents=True);project.write_text('config_version=5\n')
            with patch('device_studio.qt_controller.ROOT',root),patch('device_studio.qt_controller.find_godot',return_value=Path('/fake/Godot')),patch('device_studio.qt_controller.subprocess.Popen',side_effect=[importer,process]) as launched:
                self.controller.openGame3D()
                command=launched.call_args.args[0]
                self.assertEqual(command[:4],['/fake/Godot','--headless','--editor','--path'])
                self.assertIn('--import',command)
                self.assertEqual(self.controller._game3d_phase,'importing')
                importer.exited=True
                self.controller._poll_game_3d()
                command=launched.call_args.args[0]
                self.assertEqual(command[:3],['/fake/Godot','--path',str(project.parent)])
                self.assertIn('--bridge-token',command)
                self.assertFalse(any('usb' in part for part in command))
                self.controller.closeGame3D()
                self.assertTrue(process.exited)
                self.assertIsNone(self.controller._game3d_bridge)
