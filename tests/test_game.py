"""Traffic physics, driver input and firmware-mode arbitration without hardware."""
import binascii
from types import SimpleNamespace
import threading
import unittest
from device_studio.game_sim import (AIR_FULL, ASSIST_GAS, ASSIST_LANE, LANE, MAX_BRAKE, MAX_CARS, ROAD_LEFT, ROAD_RIGHT, GameConfig,
                                    DriverInput, TrafficWorld, TrafficCar, GameRunner, LaneChange, idm)
from device_studio.protocol import ProtocolError

IDLE = dict(a=0, mode='MONITOR', warn=False)
COAST = dict(gas=False, brake=False)
GAS = dict(gas=True, brake=False)
BRAKE = dict(gas=False, brake=True)


def empty_road(**config):
    world = TrafficWorld(GameConfig(duration=600, **config))
    world.cars, world.next_spawn, world.next_chaser, world.next_ease, world.next_surprise = [], 10 ** 9, 10 ** 9, 10 ** 9, 10 ** 9
    return world


def steering(direction):
    return dict(gas=False, brake=False, steer=direction)


class GameTests(unittest.TestCase):
    def test_key_aliases_have_independent_release(self):
        inputs = DriverInput()
        inputs.key('w', True); inputs.key('up', True); inputs.key('w', False)
        self.assertTrue(inputs.sample()['gas'])
        inputs.key('a', True); inputs.key('left', True); inputs.key('a', False)
        self.assertEqual(inputs.sample()['steer'], -1)
        inputs.key('left', False)
        self.assertEqual(inputs.sample()['steer'], 0)
        inputs.release()
        self.assertEqual(inputs.sample(), dict(gas=False, brake=False, steer=0, signal=0, takla=0, layer=0))

    def test_steering_is_held_and_opposite_keys_cancel(self):
        inputs = DriverInput()
        inputs.key('d', True)
        self.assertEqual([inputs.sample()['steer'] for _ in range(3)], [1, 1, 1])
        inputs.key('a', True)
        self.assertEqual(inputs.sample()['steer'], 0)
        inputs.key('d', False)
        self.assertEqual(inputs.sample()['steer'], -1)

    def test_indicator_and_takla_keys_are_single_presses(self):
        inputs = DriverInput()
        inputs.key('q', True); inputs.key('q', True, True); inputs.key('q', False); inputs.key('e', True)
        self.assertEqual([inputs.sample()['signal'] for _ in range(3)], [-1, 1, 0])
        inputs.key('z', True); inputs.key('x', True)
        self.assertEqual([inputs.sample()['takla'] for _ in range(3)], [-1, 1, 0])

    def test_space_is_a_brake_alias_with_independent_release(self):
        inputs = DriverInput()
        inputs.key('space', True)
        self.assertEqual(inputs.sample(), dict(gas=False, brake=True, steer=0, signal=0, takla=0, layer=0))
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

    def test_a_tap_nudges_the_car_and_it_stays_where_it_is(self):
        world = empty_road(vehicle='model3')
        world.ego = 90 / 3.6
        self.fly(world, 5, pedals=steering(1))
        self.fly(world, 80)
        moved = world.x
        self.assertTrue(.15 < moved < .4, moved)
        self.assertAlmostEqual(world.lane_rate, 0., places=3)
        self.fly(world, 80)
        self.assertAlmostEqual(world.x, moved, places=2)  # no automatic centring

    def test_a_held_key_crosses_a_lane_within_brisk_lateral_acceleration(self):
        world = empty_road(vehicle='model3')
        world.ego = 90 / 3.6
        peak, steps = 0., 0
        while world.x < LANE:
            self.fly(world, 1, pedals=steering(1))
            peak, steps = max(peak, abs(world.lat_accel)), steps + 1
        self.assertTrue(2. < steps * world.dt < 3.2, steps * world.dt)
        self.assertLess(peak, 2.9)
        self.assertEqual(world.target_lane, 2)

    def test_steering_is_sharper_when_evading(self):
        def time_to_clear(gap):
            world = empty_road(vehicle='model3')
            world.ego = 90 / 3.6
            world.cars = [TrafficCar(1, 1., gap, 25.)]
            steps = 0
            while world.x < 2:
                self.fly(world, 1, pedals=steering(1))
                steps += 1
            return steps * world.dt
        self.assertLess(time_to_clear(15.), time_to_clear(150.) - .4)

    def test_a_standing_car_cannot_move_sideways(self):
        world = empty_road()
        world.ego = 0.
        self.fly(world, 40, pedals=steering(-1))
        self.assertEqual(world.lane, 1.)

    def test_wheel_turns_gradually_and_comes_back(self):
        world = empty_road()
        self.fly(world, 3, pedals=steering(1))
        self.assertTrue(.2 < world.wheel < .5)
        self.fly(world, 10, pedals=steering(1))
        self.assertEqual(world.wheel, 1.)
        self.assertEqual(world.snapshot({})['wheel'], 1.)
        self.fly(world, 6)
        self.assertEqual(world.wheel, 0.)

    def test_barrier_contact_slows_the_car_and_the_drive_goes_on(self):
        for direction, limit in ((-1, ROAD_LEFT), (1, ROAD_RIGHT)):
            world = empty_road()
            world.ego = 80 / 3.6
            before = None
            for _ in range(400):
                self.fly(world, 1, pedals=dict(gas=True, brake=False, steer=direction))
                if world.scraping:
                    before = before or world.seconds
                    break
            self.assertIsNotNone(before)
            self.assertAlmostEqual(abs(world.x) + world.spec.width / 2, abs(limit), places=6)
            self.assertFalse(world.collision or world.finished)
            self.assertEqual(world.scrapes, 1)
            speed = world.ego
            self.fly(world, 20, pedals=dict(gas=False, brake=False, steer=direction))
            self.assertLess(world.ego, speed - 2)
            self.assertEqual(world.scrapes, 1)

    def test_indicator_latches_cancels_on_the_same_key_and_on_arrival(self):
        world = empty_road(vehicle='model3')
        world.ego = 90 / 3.6
        world.indicate(1)
        self.assertEqual(world.signal, 1)
        world.indicate(1)
        self.assertEqual(world.signal, 0)
        world.indicate(-1); world.indicate(1)
        self.assertEqual(world.signal, 1)
        self.fly(world, 20)
        self.assertEqual(world.signal, 1)  # waits for the driver
        while world.signal:
            self.fly(world, 1, pedals=steering(1))
            self.assertLess(world.seconds, 6)
        self.assertEqual(world.target_lane, 2)
        self.assertLessEqual(abs(world.x - LANE), (LANE - world.spec.width) / 2)

    def test_firmware_steering_moves_the_car_and_shows_on_the_wheel(self):
        world = empty_road(vehicle='model3')
        world.ego = 90 / 3.6
        control = dict(a=0, mode='MONITOR', st=-200, **{'as': ASSIST_LANE})
        self.fly(world, 20, control)
        self.assertLess(world.x, -.5)
        self.assertEqual(world.assists, 1)
        snapshot = world.snapshot(control)
        self.assertAlmostEqual(snapshot['wheel'], -200 / 280, places=6)
        self.assertEqual(snapshot['assistBits'], ASSIST_LANE)
        self.fly(world, 5)
        self.assertEqual(world.assists, 1)

    def test_warning_and_off_modes_ignore_firmware_steering(self):
        for mode in ('warn', 'off'):
            world = empty_road(mode=mode)
            self.fly(world, 20, dict(a=0, mode='MONITOR', st=-400, **{'as': ASSIST_LANE}))
            self.assertEqual((world.x, world.assists), (0., 0))

    def test_escape_floors_the_accelerator_until_the_driver_brakes(self):
        control = dict(a=600, mode='MONITOR', **{'as': ASSIST_GAS})
        world = empty_road(vehicle='model3')
        world.ego = 100 / 3.6
        self.fly(world, 30, control)
        self.assertTrue(3.5 < world.acceleration < 6.3, world.acceleration)
        self.assertEqual(world.assists, 1)
        self.fly(world, 10, control, BRAKE)
        self.assertLess(world.acceleration, -5)
        # The Şahin is what it is: about 1 m/s² at this speed, however hard it is asked.
        world = empty_road(vehicle='sahin')
        world.ego = 100 / 3.6
        self.fly(world, 60, control)
        self.assertLess(world.acceleration, 1.5)
        self.assertGreater(world.ego, 100 / 3.6)

    def test_comfort_requests_above_the_acc_limit_need_the_escape_bit(self):
        world = empty_road(mode='warn', vehicle='model3')
        self.fly(world, 30, dict(a=600, mode='MONITOR', **{'as': ASSIST_GAS}))
        self.assertLess(world.acceleration, 0)

    def test_sensors_pick_the_threat_on_each_side_and_behind(self):
        world = empty_road(vehicle='model3')
        world.ego = 25.
        world.cars = [TrafficCar(1, 0., -3., 25.), TrafficCar(2, 0., -60., 35.),  # left: in the zone beats far away
                      TrafficCar(3, 2., -40., 33.), TrafficCar(4, 2., -60., 45.),  # right: reaches the zone first
                      TrafficCar(5, 1., -12., 30.), TrafficCar(6, 1., -30., 45.),  # behind: the nearer
                      TrafficCar(7, 1., 30., 25.), TrafficCar(8, 0., 40., 25.)]    # ahead: T: looks after those
        found = world.sense()
        self.assertEqual([found[name]['car'].identity for name in ('left', 'right', 'rear')], [1, 4, 5])
        self.assertAlmostEqual(found['rear']['gap'], 12 - (4.55 + 4.72) / 2, places=6)
        self.assertAlmostEqual(found['left']['clearance'], 3.6 - (1.8 + 1.85) / 2, places=6)
        world.altitude = 3.
        self.assertEqual(world.sense(), dict(left=None, right=None, rear=None))

    def test_a_car_just_ahead_alongside_stays_the_target_over_one_far_behind(self):
        world = empty_road(vehicle='model3')
        world.ego = 25.
        world.cars = [TrafficCar(1, 2., 3.5, 25.), TrafficCar(2, 2., -70., 35.)]
        self.assertEqual(world.sense()['right']['car'].identity, 1)

    def test_a_car_straddling_lanes_is_sensed_by_its_real_clearance(self):
        world = empty_road(vehicle='model3')
        world.lane = 1.45
        world.cars = [TrafficCar(1, 2., -3., 25.), TrafficCar(2, 0., -3., 25.)]
        found = world.sense()
        self.assertAlmostEqual(found['right']['clearance'], .55 * LANE - (1.8 + 1.85) / 2, places=6)
        self.assertAlmostEqual(found['left']['clearance'], 1.45 * LANE - (1.8 + 1.85) / 2, places=6)
        # Now part of the lane to the right, and in the path of what is in it.
        world.lane = 1.75
        world.cars = [TrafficCar(1, 2., -20., 25.)]
        self.assertEqual(world.sense()['rear']['car'].identity, 1)

    def test_surround_sample_is_crc_protected_and_fits_the_command_limit(self):
        world = empty_road(vehicle='model3')
        world.ego = 25.
        world.lane = 1.25
        world.lane_rate = .1
        world.cars = [TrafficCar(1, 0., -3., 26.), TrafficCar(2, 2., -60., 35.), TrafficCar(3, 1., -20., 30.)]
        world.lane = 1.
        world.indicate(-1)
        command = world.surround_command(dict(gas=False, brake=True, steer=1))
        self.assertEqual(len(command), 39)
        body, crc = command.rsplit(':', 1)
        self.assertEqual(int(crc, 16), binascii.crc_hqx(body.encode(), 0xffff))
        fields = [int(body[2 + i * 3:5 + i * 3], 16) for i in range(10)]
        self.assertEqual(fields[:3], [0x1000 - 30, 10, 178])
        self.assertEqual(fields[3:6], [0x1000 - 600, 100, 178])
        self.assertEqual(fields[6:8], [round((20 - (4.55 + 4.72) / 2) * 10), 50])
        self.assertEqual(int(body[32:34], 16), 2 | 1 << 2 | 1 << 4 | 1 << 5 | 1 << 6 | 1 << 7)
        world.cars = []
        self.assertTrue(world.surround_command(COAST).startswith('N:800000000800000000800000'))

    def test_airborne_car_sends_no_road_flag(self):
        world = empty_road(vehicle='roadster')
        world.fly(1); self.fly(world, 40)
        command = world.surround_command(COAST)
        self.assertFalse(int(command[32:34], 16) & 16)

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
        world.takla(1)
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

    def test_without_air_there_is_no_takla_and_the_tyres_steer(self):
        world = empty_road(vehicle='roadster')
        world.air, world.ego = 0., 90 / 3.6
        world.takla(-1)
        self.assertIsNone(world.hop)
        self.assertIsNone(world.path)
        self.assertTrue(world.snapshot({})['airLow'])
        self.fly(world, 40, pedals=steering(-1))
        self.assertLess(world.x, -1.)

    def test_only_the_flier_has_a_takla(self):
        world = empty_road()
        world.takla(1)
        self.assertIsNone(world.path)

    def test_side_nozzles_steer_in_the_air_and_spend_air(self):
        world = empty_road(vehicle='roadster')
        world.fly(1); self.fly(world, 60)
        air = world.air
        world.ego = 0.
        self.fly(world, 20)
        hover = air - world.air
        air = world.air
        self.fly(world, 20, pedals=steering(1))
        self.assertGreater(world.x, .5)
        self.assertGreater(world.side, 0)
        self.assertGreater(air - world.air, hover)

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
        world.lane_rate = -.6  # about to be there
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
        world = TrafficWorld(GameConfig(duration=600, acc=True, seed=7, surprises=False))
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
        self.fly(world, 40, pedals=steering(-1))
        self.assertLess(follower.accel, -1)
        self.assertTrue(follower.braking)
        self.assertFalse(world.collision)

    def test_jam_tail_stops_hard_then_drives_on(self):
        world = TrafficWorld(GameConfig(surprises=False))
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
            world.advance(IDLE, dict(gas=False, brake=True, steer=-1))
        self.assertEqual(world.ego, 0)
        # A stopped car stays on the road, however far it was turned.
        self.assertGreater(world.x, ROAD_LEFT)

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
            current=dict(app='ADASLab', version=3)
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
            current=dict(app='ADASLab', version=3)
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
            current=dict(app='ADASLab', version=3)
        make=lambda **kwargs:GameRunner(Device(), GameConfig(**kwargs), DriverInput(), threading.Event(), lambda s:None)
        self.assertEqual(make().launch, 0)
        self.assertEqual(make(vehicle='model3').launch, 0)
        world=TrafficWorld(GameConfig(vehicle='roadster'))
        world.tick=50
        self.assertEqual(GameRunner(Device(), world.config, DriverInput(), threading.Event(), lambda s:None, world).launch, 0)

    def test_runner_rejects_firmware_without_side_sensing(self):
        class Device:
            current=dict(app='ADASLab', version=2)
            def runtime(self, command, **kwargs):raise AssertionError('Old firmware used')
        runner=GameRunner(Device(), GameConfig(), DriverInput(), threading.Event(), lambda s:None)
        with self.assertRaisesRegex(ProtocolError, 'v3'):runner.run()

    def test_runner_sends_sensors_before_each_sample_and_the_car_width_first(self):
        stop=threading.Event()
        class Device:
            current=dict(app='ADASLab', version=3)
            def __init__(self):self.calls=[]
            def runtime(self, command, **kwargs):
                self.calls.append(command)
                sample=command.startswith('T:')
                if sample and len([c for c in self.calls if c.startswith('T:')])==2:stop.set()
                return dict(app='ADASLab', id=3, state=dict(ms=int(command.split(':')[1]) if sample else 0, fresh=True, grun=True, a=0, gmode=0))
        device=Device()
        GameRunner(device, GameConfig(vehicle='model3'), DriverInput(), stop, lambda s:None, configure=False).run()
        kinds=[command.split(':')[0] for command in device.calls]
        self.assertEqual(kinds[:7], ['RESET', 'V', 'W', 'H', 'N', 'T', 'N'])
        self.assertIn('W:92', device.calls)

    def test_runner_rejects_a_damaged_sensor_reply(self):
        class Device:
            current=dict(app='ADASLab', version=3)
            def __init__(self):self.calls=[]
            def runtime(self, command, **kwargs):
                self.calls.append(command)
                return dict(state=dict(error='surround_crc' if command.startswith('N:') else ''))
        device=Device()
        runner=GameRunner(device, GameConfig(), DriverInput(), threading.Event(), lambda s:None)
        with self.assertRaisesRegex(ProtocolError, 'Çevre'):runner.run()
        self.assertEqual(runner.world.tick, 0)
        self.assertFalse(any(command.startswith('T:') for command in device.calls))

    def test_chasers_come_from_behind_faster_than_the_player_at_any_speed(self):
        for kmh in (0, 60, 140):
            world = empty_road(surprises=False)
            seen = {}
            world.ego = kmh / 3.6
            world.next_chaser = 0
            control = dict(a=0, mode='MONITOR')
            for _ in range(2400):
                world.ego = kmh / 3.6
                world.advance(control, COAST)
                for car in world.cars:
                    seen.setdefault(car.identity, (car.z - world.distance, car.speed))
            self.assertGreater(len(seen), 5)
            self.assertTrue(all(z < -100 for z, _ in seen.values()))
            self.assertTrue(all(speed > max(kmh, 70) / 3.6 + 14 / 3.6 for _, speed in seen.values()))
            self.assertGreater(max(speed for _, speed in seen.values()) - min(speed for _, speed in seen.values()), 20 / 3.6)

    def test_a_distracted_driver_sees_the_player_only_at_the_last_moment(self):
        def run(distracted):
            world = empty_road()
            world.ego = 20.
            world.cars = [TrafficCar(5, 1., -60., 35., desired=35., distracted=distracted, headway=1., comfort=3.)]
            speeds = []
            for _ in range(100):
                world.ego = 20.
                world.advance(IDLE, COAST)
                car = world.cars[0]
                speeds.append((world.distance - car.z, car.accel))
                if world.collision:
                    break
            return next((gap for gap, accel in speeds if accel < -1), None), world.collision
        attentive, _ = run(0.)
        late, _ = run(1.1)
        self.assertGreater(attentive, late + 15)
        # Only the player goes unseen: other traffic ahead is followed as usual.
        world = empty_road()
        world.ego = 40.
        lead = TrafficCar(6, 1., 500., 20.)
        chaser = TrafficCar(5, 1., 440., 35., desired=35., distracted=1.)
        world.cars = [lead, chaser]
        world._decide(chaser, world._bodies())
        self.assertLess(chaser.command, 0)

    def test_a_careless_driver_cuts_in_without_looking_for_the_player(self):
        def run(careless):
            world = empty_road(vehicle='model3')
            world.ego = 25.
            car = TrafficCar(5, 2., 0., 25., changes=True, careless=careless, signal_lead=.2, change_time=2.)
            world.cars = [car]
            world._start_change(car, 1)
            for _ in range(60):
                world.ego = 25.
                world.advance(IDLE, COAST)
                if world.collision:
                    break
            return world.collision, car
        self.assertTrue(run(True)[0])
        collided, careful = run(False)
        self.assertFalse(collided)
        self.assertEqual(careful.lane, 2.)

    def test_surprises_can_be_turned_off_for_defined_tests(self):
        world = TrafficWorld(GameConfig(surprises=False))
        self.assertGreater(world.next_surprise, 10 ** 6)
        world.ego = 20.
        chasers = []
        for _ in range(4000):
            world.ego = 20.
            world.advance(IDLE, COAST)
            chasers += [car for car in world.cars if car.distracted or car.careless]
            if world.finished:
                break
        self.assertEqual(chasers, [])

    def test_traffic_is_livelier_and_keeps_within_the_scene(self):
        world = TrafficWorld(GameConfig(duration=600, seed=11, surprises=False))
        easing, most = 0, 0
        for _ in range(2400):
            world.ego = 25.
            world.advance(IDLE, COAST)
            easing += any(world.tick < car.ease_until for car in world.cars)
            most = max(most, len(world.cars))
            world.collision = False
        self.assertGreater(easing, 100)
        self.assertGreaterEqual(most, 10)
        self.assertLessEqual(most, MAX_CARS)

    def test_card_pause_stops_without_advancing_world(self):
        class Device:
            current=dict(app='ADASLab', version=3)
            def runtime(self, command, **kwargs):
                return dict(app='ADASLab', id=3, state=dict(ms=0, fresh=True, grun=False, a=0))
        snapshots=[]
        runner=GameRunner(Device(), GameConfig(), DriverInput(), threading.Event(), snapshots.append)
        runner.run()
        self.assertEqual(runner.world.tick, 0)
        self.assertTrue(snapshots[0]['cardPause'])


if __name__ == '__main__':
    unittest.main()
