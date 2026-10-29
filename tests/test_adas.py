import binascii
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from device_studio.adas_sim import World,Config,Runner
from device_studio.protocol import ProtocolError

class PlantTests(unittest.TestCase):
    def test_units_and_crc(self):
        world=World(Config());cmd=world.command();body,checksum=cmd.rsplit(':',1)
        self.assertLessEqual(len(cmd),39);self.assertEqual(int(checksum),binascii.crc_hqx(body.encode(),0xffff))
        self.assertEqual(body,'S:0:2500:2500:7000:15')
    def test_cutin_changes_target_at_three_seconds(self):
        world=World(Config(scenario='cutin'));self.assertFalse(world.present)
        for _ in range(60):world.advance(0)
        self.assertTrue(world.present);self.assertEqual(world.gap,35);self.assertEqual(world.lead,12.5)
    def test_physics_integrates_acceleration(self):
        world=World(Config(scenario='cruise'));world.advance(-2)
        self.assertAlmostEqual(world.ego,24.9);self.assertGreater(world.gap,70)
    def test_invalid_acceleration_does_not_advance_time(self):
        world=World(Config())
        with self.assertRaises(ProtocolError):world.advance(10)
        self.assertEqual(world.tick,0)
    def test_stop_never_makes_speed_negative(self):
        world=World(Config(target_kmh=5))
        for _ in range(20):world.advance(-8.5)
        self.assertEqual(world.ego,0)
    def test_runner_stops_on_wrong_response_time(self):
        device=SimpleNamespace(current={'app':'ADASLab'})
        commands=[]
        def runtime(cmd,**kwargs):
            commands.append(cmd)
            return {'app':'ADASLab','id':3,'state':{'fresh':True,'ms':99,'a':0}}
        device.runtime=runtime
        runner=Runner(device,Config(),threading.Event(),lambda s:None)
        with self.assertRaises(ProtocolError):runner.run()
        self.assertEqual(commands[-1],'PAUSE');self.assertEqual(len(runner.rows),0)
    def test_no_desktop_controller_fallback_on_serial_failure(self):
        device=SimpleNamespace(current={'app':'ADASLab'})
        def runtime(cmd,**kwargs):
            if cmd.startswith('S:'):raise TimeoutError('Disconnected')
            return {}
        device.runtime=runtime
        runner=Runner(device,Config(),threading.Event(),lambda s:None)
        with self.assertRaises(TimeoutError):runner.run()
        self.assertEqual(len(runner.rows),0)
