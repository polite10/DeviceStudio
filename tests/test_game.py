"""Traffic physics, driver input and firmware-mode arbitration without hardware."""
import binascii
from types import SimpleNamespace
import threading
import unittest
from device_studio.game_sim import (AIR_FULL, LANE, MAX_BRAKE, GameConfig, DriverInput, TrafficWorld, TrafficCar, GameRunner,
                                    LaneChange, idm)
from device_studio.protocol import ProtocolError

IDLE = dict(a=0, mode='MONITOR', warn=False)
COAST = dict(gas=False, brake=False)
GAS = dict(gas=True, brake=False)
BRAKE = dict(gas=False, brake=True)


def empty_road(**config):
    world = TrafficWorld(GameConfig(duration=600, **config))
    world.cars, world.next_spawn = [], 10 ** 9
    return world


class GameTests(unittest.TestCase):
    def test_key_aliases_have_independent_release_and_repeat_does_not_steer(self):
        inputs = DriverInput()
        inputs.key('w', True); inputs.key('up', True); inputs.key('w', False)
        self.assertTrue(inputs.sample()['gas'])
        inputs.key('a', True); inputs.key('a', True, True); inputs.key('a', True)
        self.assertEqual(inputs.sample()['lane'], -1)
        self.assertEqual(inputs.sample()['lane'], 0)
        inputs.release()
        self.assertEqual(inputs.sample(), dict(gas=False, brake=False, lane=0, layer=0))

    def test_space_is_a_brake_alias_with_independent_release(self):
        inputs = DriverInput()
        inputs.key('space', True)
        self.assertEqual(inputs.sample(), dict(gas=False, brake=True, lane=0, layer=0))
        inputs.key('s', True); inputs.key('space', False)
        self.assertTrue(inputs.sample()['brake'])
        inputs.key('space', True); inputs.key('s', False)
        self.assertTrue(inputs.sample()['brake'])
        inputs.key('space', False)
        self.assertFalse(inputs.sample()['brake'])

    def test_flight_keys_queue_layers_and_repeat_does_not_climb(self):
        inputs = DriverInput()
        inputs.key('r', True); inputs.key('r', True, True); inputs.key('r', False); inputs.key('f', True)
        self.assertEqual([inputs.sample()['layer'] for _ in range(3)], [1, -1, 0])

    def fly(self, world, steps, control=None, pedals=COAST):
        for _ in range(steps):
            world.advance(control or IDLE, pedals)

    def test_unknown_vehicle_is_rejected(self):
        with self.assertRaises(ValueError):
            GameConfig(vehicle='zeppelin')

    def test_vehicle_performance_matches_published_figures(self):
        def zero_to(vehicle, kmh):
            world = empty_road(vehicle=vehicle)
            world.ego = 0.
            while world.ego < kmh / 3.6:
                self.fly(world, 1, pedals=GAS)
            return world.seconds
        def stopping(vehicle):
            world = empty_road(vehicle=vehicle)
            world.ego = 100 / 3.6
            while world.ego > 0:
                self.fly(world, 1, pedals=BRAKE)
            return world.distance
        # Tofaş Şahin 1.6: ~12-14 s; Model 3 Long Range AWD: 4.4 s; Roadster: 0-60 mph under 1.6 s on tyres.
        self.assertTrue(11 < zero_to('sahin', 100) < 14)
        self.assertTrue(4.2 < zero_to('model3', 100) < 4.8)
        self.assertLess(zero_to('roadster', 96.56), 1.6)
        self.assertTrue(35 < stopping('model3') < 41)
        self.assertTrue(50 < stopping('sahin') < 58)
        world = empty_road(vehicle='sahin')
        self.fly(world, 1200, pedals=GAS)
        self.assertTrue(155 < world.ego * 3.6 < 172)  # drag and power, no governor
        world = empty_road(vehicle='model3')
        self.fly(world, 600, pedals=GAS)
        self.assertAlmostEqual(world.ego * 3.6, 201, delta=1.5)

    def test_manual_gearbox_shifts_with_a_torque_gap(self):
        world = empty_road(vehicle='sahin')
        world.ego, gears, pauses = 0., set(), 0
        for _ in range(500):
            self.fly(world, 1, pedals=GAS)
            gears.add(world.gear)
            pauses += world.shifting > 0
        self.assertEqual(gears, {0, 1, 2, 3})
        self.assertGreater(pauses, 10)

    def test_releasing_the_pedal_coasts_with_engine_or_regenerative_braking(self):
        sahin, tesla = empty_road(vehicle='sahin'), empty_road(vehicle='model3')
        for world in (sahin, tesla):
            world.ego = 100 / 3.6
            self.fly(world, 20)
        self.assertTrue(-.9 < sahin.acceleration < -.3)
        self.assertTrue(-1.8 < tesla.acceleration < -1.1)
        self.assertTrue(tesla.braking)  # strong regeneration lights the stop lamps

    def test_lane_change_is_minimum_jerk_within_brisk_lateral_acceleration(self):
        world = empty_road(vehicle='model3')
        world.ego = 90 / 3.6
        world.steer(1)
        peak, steps, signalled = 0., 0, 0
        while world.path is not None:
            self.fly(world, 1, pedals=GAS if world.ego < 25 else COAST)
            peak, steps = max(peak, abs(world.lat_accel)), steps + 1
            signalled += world.signal == 1
        self.assertTrue(2.5 < steps * world.dt < 3.5)
        self.assertLess(peak, 2.9)
        self.assertGreater(signalled, .8 * steps)  # cancelled as the car settles in its lane
        self.assertEqual((world.lane, world.lane_rate, world.signal), (2., 0., 0))

    def test_lane_change_is_sharper_when_evading(self):
        def duration(gap):
            world = empty_road(vehicle='model3')
            world.ego = 90 / 3.6
            world.cars = [TrafficCar(1, 1., gap, 10.)]
            world.steer(1)
            return world.path.length / world.ego
        self.assertLess(duration(40.), duration(150.) - .6)

    def test_quintic_path_replans_smoothly_from_the_current_motion(self):
        path = LaneChange(0., 0., 0., LANE, 60.)
        x, slope, curve = path.at(30.)
        back = LaneChange(x, slope, curve, 0., 60.)
        self.assertEqual(back.at(0.), (x, slope, curve))
        self.assertEqual(back.at(60.), (0., 0., 0.))

    def test_only_flying_cars_change_layers(self):
        world = TrafficWorld(GameConfig())
        world.fly(1); self.fly(world, 20)
        self.assertEqual((world.layer, world.altitude), (0, 0.))

    def test_airborne_car_has_no_adas_target_and_passes_over_traffic(self):
        world = empty_road(vehicle='roadster')
        world.cars = [TrafficCar(1, 1., 40., 0., kind='van')]
        world.fly(1); self.fly(world, 60)
        self.assertEqual(world.layer, 1)
        self.assertAlmostEqual(world.altitude, 4., delta=.25)
        body = world.command(COAST).rsplit(':', 1)[0].split(':')
        self.assertEqual((int(body[4]), int(body[5]) & 1), (100000, 0))
        self.fly(world, 50)
        self.assertGreater(world.distance, 40 + world.spec.length)
        self.assertFalse(world.collision)

    def test_hover_empties_the_tank_then_lands_itself(self):
        world = empty_road(vehicle='roadster')
        world.fly(1)
        airborne = 0
        for _ in range(1200):
            self.fly(world, 1)
            airborne += world.airborne
            if world.seconds > 1 and not world.airborne:
                break
        # Hover burns weight / exhaust velocity: ten seconds of a full 600 L tank,
        # stretched 5.25 times for the game.
        self.assertTrue(46 < airborne * world.dt < 60)
        self.assertEqual(world.layer, 0)
        self.assertFalse(world.collision)
        self.assertGreater(world.air, 0)

    def test_climbing_needs_air_and_the_tank_refills_on_the_road(self):
        world = empty_road(vehicle='roadster')
        world.air = 20.
        world.fly(1)
        self.assertEqual(world.layer, 0)
        self.assertTrue(world.snapshot({})['airLow'])
        self.fly(world, 40)
        self.assertAlmostEqual(world.air, 55., places=6)

    def test_road_takla_hops_rolls_and_spends_air(self):
        world = empty_road(vehicle='roadster')
        world.ego = 90 / 3.6
        world.steer(1)
        apex, roll = 0., 0.
        while world.hop is not None:
            self.fly(world, 1, pedals=GAS)
            apex, roll = max(apex, world.altitude), min(roll, world.roll)
        spent = AIR_FULL - world.air
        self.assertTrue(.5 < apex < 1.)
        self.assertEqual(roll, -360)
        self.assertTrue(7 < spent < 18)
        self.assertEqual((world.lane, world.roll), (2., 0.))
        self.assertFalse(world.collision)

    def test_without_air_the_flying_car_changes_lanes_on_its_tyres(self):
        world = empty_road(vehicle='roadster')
        world.air, world.ego = 0., 90 / 3.6
        world.steer(-1)
        self.assertIsNone(world.hop)
        self.assertFalse(world.path_time)

    def test_landing_waits_for_a_clear_lane(self):
        world = empty_road(vehicle='roadster')
        world.fly(1); world.fly(1); self.fly(world, 70)
        self.assertEqual(world.layer, 2)
        self.assertAlmostEqual(world.altitude, 9., delta=.3)
        world.cars = [TrafficCar(1, 1., world.distance + 3, world.ego)]
        world.fly(-1); world.fly(-1)
        self.assertEqual(world.layer, 1)
        self.assertTrue(world.snapshot({})['landingBlocked'])
        world.cars = []
        world.fly(-1); self.fly(world, 80)
        self.assertEqual((world.layer, world.altitude), (0, 0.))
        self.assertFalse(world.collision)

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
        lead = world.cars[0]
        self.assertEqual(int(body.split(':')[4]), round((lead.z - (lead.length + world.spec.length) / 2) * 100))
        self.assertEqual(int(body.split(':')[5]), 9)

    def test_active_emergency_braking_overrides_player_accelerator(self):
        for vehicle, decel in (('sahin', 7.4), ('model3', 8.5)):
            world = TrafficWorld(GameConfig(mode='active', vehicle=vehicle))
            before = world.ego
            self.fly(world, 10, dict(a=-850, mode='AEB', warn=True), GAS)
            self.assertLess(world.ego, before)
            # The request is met up to what the brakes and tyres can do.
            self.assertAlmostEqual(world.acceleration, -decel, delta=.45)
            self.assertEqual(world.interventions, 1)

    def test_warning_only_does_not_apply_firmware_actuator_request(self):
        warn, off = TrafficWorld(GameConfig(mode='warn')), TrafficWorld(GameConfig(mode='off'))
        # Flooring it at 50 km/h, the Şahin's driver first kicks down to second.
        self.fly(warn, 30, dict(a=-850, mode='AEB', warn=True), GAS)
        self.fly(off, 30, pedals=GAS)
        self.assertGreater(warn.acceleration, 1)
        self.assertEqual(warn.acceleration, off.acceleration)
        self.assertEqual((warn.warnings, warn.interventions), (1, 0))

    def test_off_mode_suppresses_warning_and_intervention(self):
        world = TrafficWorld(GameConfig(mode='off'))
        self.fly(world, 30, dict(a=-850, mode='AEB', warn=True), GAS)
        self.assertGreater(world.acceleration, 1)
        self.assertEqual(world.warnings, 0)
        self.assertFalse(world.snapshot(dict(warn=True))['warning'])

    def test_service_brake_wins_when_both_pedals_held(self):
        world = TrafficWorld(GameConfig(mode='warn'))
        self.fly(world, 10, pedals=dict(gas=True, brake=True))
        self.assertEqual(world.throttle, 0)
        self.assertLess(world.acceleration, -7)

    def test_acc_is_overridden_by_manual_pedals(self):
        world = TrafficWorld(GameConfig(acc=True, vehicle='model3'))
        self.assertEqual(int(world.command(COAST).split(':')[5]), 11)
        self.fly(world, 10, dict(a=-300, mode='ACC'))
        self.assertAlmostEqual(world.acceleration, -3, delta=.15)
        self.assertEqual(int(world.command(BRAKE).split(':')[5]), 9)

    def test_collision_checks_actual_lane_and_swept_motion(self):
        world = TrafficWorld(GameConfig(mode='off'))
        world.ego = 200/3.6
        world.cars = [TrafficCar(9, 1, 6, 0)]
        world.advance(IDLE, COAST)
        self.assertTrue(world.collision)
        self.assertTrue(world.finished)
        other = TrafficWorld(GameConfig(mode='off'))
        other.cars = [TrafficCar(9, 0, 0, 0)]
        other.advance(IDLE, COAST)
        self.assertFalse(other.collision)

    def test_same_seed_replays_identical_traffic(self):
        worlds = [TrafficWorld(GameConfig(seed=97)) for _ in range(2)]
        for world in worlds:
            world.ego=0
            for _ in range(250):
                world.advance(IDLE, COAST)
        self.assertEqual(worlds[0].snapshot({}), worlds[1].snapshot({}))

    def test_traffic_flows_with_idm_and_mobil_without_crashing_into_each_other(self):
        world = TrafficWorld(GameConfig(duration=600, acc=True, seed=7))
        changes, signalled = 0, 0
        for _ in range(2400):
            # A stand-in for the firmware: follow at 90 km/h, brake hard when closing in.
            car, gap = world.front()
            me = SimpleNamespace(speed=world.ego, desired=25., headway=1.5, accel_max=2., comfort=3.)
            a = max(-850, min(200, round(idm(me, car, gap) * 100)))
            control = dict(a=a, mode='AEB' if a < -350 else 'ACC')
            lanes = {car.identity: (car.signal, car.lane_rate) for car in world.cars}
            world.advance(control, COAST)
            for car in world.cars:
                signal, rate = lanes.get(car.identity, (0, 0.))
                if car.lane_rate and not rate and car.identity > 4:
                    changes += 1
                    signalled += signal != 0
            for i, a in enumerate(world.cars):
                for b in world.cars[i + 1:]:
                    self.assertFalse(abs(a.z - b.z) < (a.length + b.length) / 2 and abs(a.x - b.x) < (a.width + b.width) / 2,
                                     f'cars {a.identity} and {b.identity} overlap at {world.seconds} s')
                self.assertTrue(-MAX_BRAKE - 1e-9 <= a.accel <= a.accel_max + 1e-9)
        self.assertFalse(world.collision)
        self.assertGreater(changes, 2)
        self.assertGreater(signalled, 0)

    def test_traffic_brakes_for_the_player_cutting_in(self):
        world = empty_road(vehicle='model3')
        world.ego = 70 / 3.6
        follower = TrafficCar(5, 0., -45., 80 / 3.6, desired=80 / 3.6)
        world.cars = [follower]
        world.steer(-1)
        self.fly(world, 40, pedals=COAST)
        self.assertLess(follower.accel, -1)
        self.assertTrue(follower.braking)
        self.assertFalse(world.collision)

    def test_jam_tail_stops_hard_then_drives_on(self):
        world = TrafficWorld(GameConfig())
        lead = world.cars[0]
        self.fly(world, 120, pedals=BRAKE)  # 6 s, the player stops well behind
        self.assertLess(lead.speed, 2.5)
        self.assertTrue(lead.braking)
        self.fly(world, 100, pedals=BRAKE)  # 11 s
        self.assertGreater(lead.speed, 4)
        self.assertFalse(world.collision)

    def test_speed_stays_nonnegative_and_lane_stays_on_road(self):
        world = TrafficWorld(GameConfig())
        for _ in range(100):
            world.steer(-1)
            world.advance(IDLE, BRAKE)
        self.assertEqual(world.ego, 0)
        self.assertEqual(world.target_lane, 0)
        # A stopped car cannot finish its lane change sideways.
        self.assertTrue(0 < world.lane < 1)

    def test_invalid_control_does_not_advance_physics(self):
        world = TrafficWorld(GameConfig())
        with self.assertRaises(ProtocolError):
            world.advance(dict(a=-1700), dict(gas=True, brake=False))
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

    def test_flier_launch_sends_no_samples_and_ignores_keys_pressed_on_the_ramp(self):
        stop=threading.Event()
        class Device:
            current=dict(app='ADASLab', version=2)
            def __init__(self):self.calls=[]
            def runtime(self, command, **kwargs):
                self.calls.append(command)
                sample=command.startswith('T:')
                if sample:stop.set()
                return dict(app='ADASLab', id=3, state=dict(ms=int(command.split(':')[1]) if sample else 0, fresh=True, grun=True, a=0, gmode=0))
        device, inputs=Device(), DriverInput()
        runner=GameRunner(device, GameConfig(vehicle='roadster'), inputs, stop, lambda s:None, configure=False)
        self.assertGreater(runner.launch, 0)
        runner.launch=.15
        inputs.key('a', True)
        runner.run()
        first=next(i for i, command in enumerate(device.calls) if command.startswith('T:'))
        self.assertLess(device.calls.index('H:1'), device.calls.index('J'))
        self.assertLess(device.calls.index('J'), first)
        self.assertEqual(runner.world.target_lane, 1)

    def test_only_a_new_flier_drive_climbs_the_ramp(self):
        class Device:
            current=dict(app='ADASLab', version=2)
        make=lambda **kwargs:GameRunner(Device(), GameConfig(**kwargs), DriverInput(), threading.Event(), lambda s:None)
        self.assertEqual(make().launch, 0)
        self.assertEqual(make(vehicle='model3').launch, 0)
        world=TrafficWorld(GameConfig(vehicle='roadster'))
        world.tick=50
        self.assertEqual(GameRunner(Device(), world.config, DriverInput(), threading.Event(), lambda s:None, world).launch, 0)

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


if __name__ == '__main__':
    unittest.main()
