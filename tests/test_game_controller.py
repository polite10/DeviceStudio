"""Qt game ownership, panel requests and focus-loss behavior with a fake UART."""
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent

from device_studio.qt_controller import StudioController


class PanelDevice:
    def __init__(self):
        self.current=None;self.mode=0;self.acc=False;self.target=2500;self.headway=1800
        self.running=False;self.revision=0;self.calls=[]
    def detect(self):return self.runtime('J')
    def close(self):pass
    def runtime(self, command, **kwargs):
        self.calls.append(command)
        if command.startswith('G:'):
            _,mode,acc,target,headway=command.split(':')
            self.mode=int(mode);self.acc=bool(int(acc));self.target=int(target);self.headway=int(headway)
        elif command.startswith('H:'):self.running=command=='H:1'
        elif command in ('RESET','PAUSE'):self.running=False
        fields=command.split(':')
        sample=command.startswith('T:')
        s=dict(mode='MONITOR',ego=int(fields[2]) if sample else 0,lead=0,gap=10000,ttc=-1,a=0,warn=False,
               fresh=sample,ms=int(fields[1]) if sample else 0,error='',gmode=self.mode,gacc=self.acc,
               gtarget=self.target,gheadway=self.headway,grun=self.running,grev=self.revision)
        self.current=dict(app='ADASLab',id=3,version=3,boot=1,boot_version=2,state=s)
        return self.current


class GameControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        self.device=PanelDevice()
        with patch('serial.tools.list_ports.comports',return_value=[SimpleNamespace(device='game-test',description='STLINK')]):
            self.controller=StudioController(device_factory=lambda p:self.device,start_timers=False)
        self.controller.connectDevice();self.wait(lambda:not self.controller.state['busy'])
    def wait(self,predicate,timeout=3):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.qt.processEvents()
            if predicate():return
            time.sleep(.005)
        self.fail('Game worker did not reach expected state')
    def tearDown(self):
        self.controller.pauseGame();self.wait(lambda:not self.controller.state['busy'])
        self.controller.requestClose();self.controller.deleteLater()
        self.qt.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.qt.processEvents()
    def test_version_three_routes_to_game_and_keyboard_moves_player(self):
        self.assertEqual(self.controller.state['page'],'game')
        self.assertTrue(self.controller.gameState['ready'])
        self.controller.startGame();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        speed=self.controller.gameState['egoKmh']
        self.controller.gameKey('w',True,False);self.controller.gameKey('a',True,False)
        self.wait(lambda:self.controller.gameState['egoKmh']>speed and self.controller.gameState['egoLane']<.98)
    def test_focus_loss_pauses_and_does_not_leave_stuck_throttle(self):
        self.controller.startGame();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.controller.gameKey('w',True,False);self.controller.focusLost()
        self.wait(lambda:not self.controller.state['busy'])
        self.assertEqual(self.controller.gameState['status'],'paused')
        self.assertEqual(self.device.calls[-2:],['H:0','PAUSE'])
        elapsed=self.controller.gameState['elapsed'];speed=self.controller.gameState['egoKmh']
        self.controller.startGame();self.wait(lambda:self.controller.gameState['elapsed']>elapsed+.1)
        self.assertLess(self.controller.gameState['egoKmh'],speed)
    def test_mode_cannot_change_while_driving(self):
        self.controller.startGame();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.controller.setGameOption('mode','off')
        self.assertEqual(self.controller.gameState['mode'],'active')
    def test_card_start_mode_and_pause_are_applied_by_host(self):
        self.device.mode=1;self.device.running=True;self.device.revision+=1
        self.controller._heartbeat()
        self.wait(lambda:self.controller.gameState['running'] and self.controller.gameState['elapsed']>=.1)
        self.assertEqual(self.controller.gameState['mode'],'warn')
        self.device.running=False;self.device.revision+=1
        self.wait(lambda:not self.controller.state['busy'])
        self.assertEqual(self.controller.gameState['status'],'paused')
    def test_watch_maximum_target_is_preserved_without_host_reconfiguration(self):
        self.device.target=5999
        self.device.running=True
        self.controller._heartbeat()
        self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.assertEqual(self.controller.gameState['targetKmh'],216)
        self.assertEqual(self.device.target,5999)
        self.assertFalse(any(c.startswith('G:') for c in self.device.calls))

    def test_card_start_does_not_resume_when_window_inactive(self):
        self.controller.setWindowActive(False)
        self.device.running=True;self.device.revision+=1
        self.controller._heartbeat()
        self.wait(lambda:self.controller._worker is None)
        self.qt.processEvents()
        self.assertFalse(self.controller.gameState['running'])
        self.assertNotIn('H:1',self.device.calls)
        self.controller.setWindowActive(True)
        self.controller._heartbeat()
        self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.assertTrue(self.controller.gameState['running'])
    def test_scheduled_card_start_rechecks_focus_and_page(self):
        response=self.device.runtime('H:1')
        self.controller._panel_response(response,allow_start=True)
        self.controller.setWindowActive(False)
        self.qt.processEvents()
        self.assertFalse(self.controller.gameState['running'])
        self.controller.setWindowActive(True)
        self.controller._panel_response(response,allow_start=True)
        self.controller.navigate('firmware')
        self.qt.processEvents()
        self.assertFalse(self.controller.gameState['running'])
        self.assertEqual(self.controller.state['page'],'firmware')
    def test_queued_start_rechecks_focus_after_heartbeat(self):
        entered=threading.Event();release=threading.Event()
        def delayed():
            entered.set();release.wait(2)
            return self.device.runtime('J')
        self.controller._job('heartbeat',delayed)
        self.assertTrue(entered.wait(1))
        self.controller.startGame()
        self.assertEqual(len(self.controller._deferred),1)
        self.controller.setWindowActive(False)
        release.set()
        self.wait(lambda:self.controller._worker is None)
        self.assertFalse(self.controller.gameState['running'])
        self.assertNotIn('H:1',self.device.calls)
    def blocked_heartbeat(self):
        """Hold the UART in a heartbeat; returns the event that lets it finish."""
        entered=threading.Event();release=threading.Event()
        def delayed():
            entered.set();release.wait(2)
            return self.device.runtime('J')
        self.controller._job('heartbeat',delayed)
        self.assertTrue(entered.wait(1))
        return release
    def test_studio_start_reads_watch_settings_and_shows_on_watch(self):
        # The watch changed its mode after the last heartbeat. Starting on the
        # stale value would fail the runner's mode check and drop the device.
        self.device.mode=1;self.device.revision+=1
        self.assertEqual(self.controller.gameState['mode'],'active')
        self.device.calls.clear()
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.assertEqual(self.controller.gameState['mode'],'warn')
        self.assertEqual(self.controller.gameState['status'],'running')
        self.assertTrue(self.device.running,'Watch must show the run started from Studio')
        self.assertEqual(self.device.calls[0],'J')
        self.assertLess(self.device.calls.index('RESET'),self.device.calls.index('H:1'))
        self.assertFalse(any(c.startswith('G:') for c in self.device.calls),'Studio must not rewrite watch settings')
    def test_studio_pause_stops_watch_and_watch_start_resumes_same_road(self):
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.controller.pauseGame();self.wait(lambda:not self.controller.state['busy'])
        self.assertEqual(self.controller.gameState['status'],'paused')
        self.assertFalse(self.device.running,'Watch must show the pause made in Studio')
        elapsed=self.controller.gameState['elapsed']
        self.device.running=True;self.device.revision+=1
        self.controller._heartbeat()
        self.wait(lambda:self.controller.gameState['running'] and self.controller.gameState['elapsed']>elapsed)
    def test_watch_pause_and_studio_start_resumes_same_road(self):
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.device.running=False;self.device.revision+=1
        self.wait(lambda:not self.controller.state['busy'])
        self.assertEqual(self.controller.gameState['status'],'paused')
        elapsed=self.controller.gameState['elapsed']
        self.controller.requestGameStart()
        self.wait(lambda:self.controller.gameState['running'] and self.controller.gameState['elapsed']>elapsed)
        self.assertTrue(self.device.running)
    def test_pause_leaves_no_stale_stopping_message(self):
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.controller.pauseGame();self.wait(lambda:not self.controller.state['busy'])
        self.assertEqual(self.controller.state['statusMessage'],'')
    def test_repeated_start_clicks_do_not_restart_after_pause(self):
        release=self.blocked_heartbeat()
        self.controller.requestGameStart();self.controller.requestGameStart()
        release.set()
        self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.assertEqual(len(self.controller._deferred),0)
        self.controller.pauseGame();self.wait(lambda:not self.controller.state['busy'])
        self.device.calls.clear();self.wait(lambda:self.controller._worker is None)
        self.qt.processEvents()
        self.assertEqual(self.controller.gameState['status'],'paused')
        self.assertNotIn('H:1',self.device.calls)
    def test_pause_cancels_a_start_still_waiting_for_heartbeat(self):
        release=self.blocked_heartbeat()
        self.controller.requestGameStart()
        self.assertEqual(len(self.controller._deferred),1)
        self.controller.pauseGame()
        release.set()
        self.wait(lambda:self.controller._worker is None)
        self.assertFalse(self.controller.gameState['running'])
        self.assertNotIn('H:1',self.device.calls)
    def test_space_brakes_without_pausing(self):
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        speed=self.controller.gameState['egoKmh']
        self.controller.gameKey('space',True,False)
        self.wait(lambda:self.controller.gameState['egoKmh']<speed-1)
        self.assertEqual(self.controller.gameState['status'],'running')
        self.controller.gameKey('space',False,False)
    def launch(self):
        self.controller.setVehicle('roadster')
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['running'])
    def test_flier_climbs_before_the_plant_starts_then_drives(self):
        with patch('device_studio.game_sim.LAUNCH_SECONDS',.4):
            self.device.calls.clear()
            self.launch()
            self.assertTrue(self.controller.gameState['launching'])
            self.assertTrue(self.device.running,'Watch must show the run during the climb')
            self.wait(lambda:'J' in self.device.calls[1:])
            self.assertEqual(self.controller.gameState['elapsed'],0.)
            self.assertFalse(any(c.startswith('T:') for c in self.device.calls))
            self.wait(lambda:self.controller.gameState['elapsed']>=.1)
            self.assertFalse(self.controller.gameState['launching'])
    def test_pause_on_the_ramp_goes_back_to_the_start_and_replays(self):
        with patch('device_studio.game_sim.LAUNCH_SECONDS',5):
            self.launch()
            self.controller.pauseGame();self.wait(lambda:not self.controller.state['busy'])
            self.assertEqual(self.controller.gameState['status'],'ready')
            self.assertFalse(self.controller.gameState['launching'])
            self.assertFalse(self.device.running)
            self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['running'])
            self.assertTrue(self.controller.gameState['launching'],'A new start must climb again')
    def test_watch_pause_on_the_ramp_stops_the_launch(self):
        with patch('device_studio.game_sim.LAUNCH_SECONDS',5):
            self.launch()
            self.device.running=False;self.device.revision+=1
            self.wait(lambda:not self.controller.state['busy'])
            self.assertEqual(self.controller.gameState['status'],'ready')
            self.assertFalse(any(c.startswith('T:') for c in self.device.calls))
    def test_resuming_after_the_release_does_not_climb_again(self):
        with patch('device_studio.game_sim.LAUNCH_SECONDS',.2):
            self.launch();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
            self.controller.pauseGame();self.wait(lambda:not self.controller.state['busy'])
            self.assertEqual(self.controller.gameState['status'],'paused')
            self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['running'])
            self.assertFalse(self.controller.gameState['launching'])
    def test_pause_menu_restart_goes_back_to_choosing_a_car(self):
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.2)
        self.controller.pauseGame();self.wait(lambda:not self.controller.state['busy'])
        self.assertEqual(self.controller.gameState['status'],'paused')
        self.controller.chooseNewCar();self.wait(lambda:self.controller.gameState['status']=='ready')
        game=self.controller.gameState
        self.assertEqual((game['elapsed'],game['distance'],game['traffic'],game['running']),(0.,0.,[],False))
        self.assertIsNone(self.controller._game_world)
        self.assertFalse(self.device.running,'The watch stays stopped until the next start')
        # A car can be chosen again, and the next start is a new road.
        self.controller.setVehicle('model3')
        self.assertEqual(self.controller.gameState['vehicle'],'model3')
        self.device.calls.clear()
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.assertLess(self.controller.gameState['elapsed'],1)
        self.assertIn('W:92',self.device.calls)
    def test_pause_menu_restart_is_ignored_while_driving(self):
        self.controller.requestGameStart();self.wait(lambda:self.controller.gameState['elapsed']>=.2)
        self.controller.chooseNewCar()
        self.assertEqual(self.controller.gameState['status'],'running')
        self.assertIsNotNone(self.controller._game_world)
    def test_navigation_away_pauses_game_and_releases_keys(self):
        self.controller.startGame();self.wait(lambda:self.controller.gameState['elapsed']>=.1)
        self.controller.gameKey('w',True,False);self.controller.navigate('firmware')
        self.wait(lambda:not self.controller.state['busy'])
        self.assertEqual(self.controller.state['page'],'firmware')
        self.assertFalse(self.controller.gameState['running'])
