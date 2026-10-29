"""Traffic physics, driver input and firmware-mode arbitration without hardware."""
from copy import deepcopy
import binascii
import threading
import unittest
from device_studio.game_sim import GameConfig, DriverInput, TrafficWorld, TrafficCar, GameRunner
from device_studio.protocol import ProtocolError


class GameTests(unittest.TestCase):
    def test_key_aliases_have_independent_release_and_repeat_does_not_steer(self):
        inputs = DriverInput()
        inputs.key('w', True); inputs.key('up', True); inputs.key('w', False)
        self.assertTrue(inputs.sample()['gas'])
        inputs.key('a', True); inputs.key('a', True, True); inputs.key('a', True)
        self.assertEqual(inputs.sample()['lane'], -1)
        self.assertEqual(inputs.sample()['lane'], 0)
        inputs.release()
        self.assertEqual(inputs.sample(), dict(gas=False, brake=False, lane=0))

    def test_target_selection_excludes_adjacent_lane_and_includes_entered_lane(self):
        world = TrafficWorld(GameConfig())
        world.cars = [TrafficCar(1, 0, 8, 0), TrafficCar(2, 1, 30, 0)]
        self.assertEqual(world.front()[0].identity, 2)
        world.steer(-1)
        self.assertEqual(world.front()[0].identity, 1)

    def test_sample_is_bounded_crc_protected_and_uses_bumper_gap(self):
        world = TrafficWorld(GameConfig())
        command = world.command(dict(gas=True, brake=False))
        body, crc = command.rsplit(':', 1)
        self.assertEqual(int(crc), binascii.crc_hqx(body.encode(), 0xffff))
        self.assertLessEqual(len(command), 39)
        self.assertEqual(int(body.split(':')[4]), 6040)
        self.assertEqual(int(body.split(':')[5]), 9)

    def test_active_emergency_braking_overrides_player_accelerator(self):
        world = TrafficWorld(GameConfig(mode='active'))
        before = world.ego
        world.advance(dict(a=-850, mode='AEB', warn=True), dict(gas=True, brake=False))
        self.assertLess(world.ego, before)
        self.assertEqual(world.acceleration, -8.5)
        self.assertEqual(world.interventions, 1)

    def test_warning_only_does_not_apply_firmware_actuator_request(self):
        world = TrafficWorld(GameConfig(mode='warn'))
        world.advance(dict(a=-850, mode='AEB', warn=True), dict(gas=True, brake=False))
        self.assertEqual(world.acceleration, 2.8)
        self.assertEqual(world.warnings, 1)
        self.assertEqual(world.interventions, 0)

    def test_off_mode_suppresses_warning_and_intervention(self):
        world = TrafficWorld(GameConfig(mode='off'))
        world.advance(dict(a=-850, mode='AEB', warn=True), dict(gas=True, brake=False))
        self.assertEqual(world.acceleration, 2.8)
        self.assertEqual(world.warnings, 0)
        self.assertFalse(world.snapshot(dict(warn=True))['warning'])

    def test_service_brake_wins_when_both_pedals_held(self):
        world = TrafficWorld(GameConfig(mode='warn'))
        world.advance(dict(a=0), dict(gas=True, brake=True))
        self.assertEqual(world.acceleration, -8)

    def test_acc_is_overridden_by_manual_pedals(self):
        world = TrafficWorld(GameConfig(acc=True))
        self.assertEqual(int(world.command(dict(gas=False, brake=False)).split(':')[5]), 11)
        world.advance(dict(a=-300, mode='ACC'), dict(gas=False, brake=False))
        self.assertEqual(world.acceleration, -3)
        self.assertEqual(int(world.command(dict(gas=False, brake=True)).split(':')[5]), 9)

    def test_collision_checks_actual_lane_and_swept_motion(self):
        world = TrafficWorld(GameConfig(mode='off'))
        world.ego = 200/3.6
        world.cars = [TrafficCar(9, 1, 6, 0)]
        world.advance(dict(a=0), dict(gas=False, brake=False))
        self.assertTrue(world.collision)
        self.assertTrue(world.finished)
        other = TrafficWorld(GameConfig(mode='off'))
        other.cars = [TrafficCar(9, 0, 0, 0)]
        other.advance(dict(a=0), dict(gas=False, brake=False))
        self.assertFalse(other.collision)

    def test_same_seed_replays_identical_traffic(self):
        worlds = [TrafficWorld(GameConfig(seed=97)) for _ in range(2)]
        for world in worlds:
            world.ego=0
            for _ in range(250):
                world.advance(dict(a=0), dict(gas=False, brake=False))
        self.assertEqual(worlds[0].snapshot({}), worlds[1].snapshot({}))

    def test_speed_stays_nonnegative_and_lane_stays_on_road(self):
        world = TrafficWorld(GameConfig())
        for _ in range(100):
            world.steer(-1)
            world.advance(dict(a=0), dict(gas=False, brake=True))
        self.assertEqual(world.ego, 0)
        self.assertEqual(world.lane, 0)

    def test_invalid_control_does_not_advance_physics(self):
        world = TrafficWorld(GameConfig())
        with self.assertRaises(ProtocolError):
            world.advance(dict(a=-900), dict(gas=True, brake=False))
        self.assertEqual(world.tick, 0)

    def test_runner_rejects_old_firmware(self):
        class OldDevice:
            current=dict(app='ADASLab', version=1)
            def runtime(self, command, **kwargs):raise AssertionError('Old firmware used')
        runner=GameRunner(OldDevice(), GameConfig(), DriverInput(), threading.Event(), lambda s:None)
        with self.assertRaises(ProtocolError):runner.run()

    def test_runner_rejects_bad_sample_and_sends_pause(self):
        class Device:
            current=dict(app='ADASLab', version=2)
            def __init__(self):self.calls=[]
            def runtime(self, command, **kwargs):
                self.calls.append(command)
                return dict(app='ADASLab', id=3, state=dict(ms=999, fresh=True, grun=True, a=0))
        device=Device()
        runner=GameRunner(device, GameConfig(), DriverInput(), threading.Event(), lambda s:None)
        with self.assertRaises(ProtocolError):runner.run()
        self.assertEqual(device.calls[-2:], ['H:0', 'PAUSE'])
        self.assertEqual(runner.world.tick, 0)

    def test_card_pause_stops_without_advancing_world(self):
        class Device:
            current=dict(app='ADASLab', version=2)
            def runtime(self, command, **kwargs):
                return dict(app='ADASLab', id=3, state=dict(ms=0, fresh=True, grun=False, a=0))
        snapshots=[]
        runner=GameRunner(Device(), GameConfig(), DriverInput(), threading.Event(), snapshots.append)
        runner.run()
        self.assertEqual(runner.world.tick, 0)
        self.assertTrue(snapshots[0]['cardPause'])
