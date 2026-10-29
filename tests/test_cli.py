"""CLI mode routing must preserve hardware/simulator and 2D/3D separation."""
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_modes_route_to_expected_backends_without_starting_a_drive(self):
        cases={
            None:(False,False,False,False),
            '--connect':(True,False,False,False),
            '--adas':(True,True,False,False),
            '--adas-sim':(True,True,True,False),
            '--game-sim':(True,False,True,True),
            '--game-2d':(True,False,False,False),
            '--game-2d-sim':(True,False,True,False),
        }
        for flag,expected in cases.items():
            with self.subTest(flag=flag):
                calls=[];fake=types.ModuleType('device_studio.qt_app')
                def main(**kwargs):calls.append(kwargs);return 0
                fake.main=main
                with patch.dict(sys.modules,{'device_studio.qt_app':fake}),patch.object(sys,'argv',[str(ROOT/'studio.py')]+([flag] if flag else [])):
                    with self.assertRaises(SystemExit) as result:runpy.run_path(str(ROOT/'studio.py'),run_name='__main__')
                self.assertEqual(result.exception.code,0)
                self.assertEqual(calls,[dict(zip(('auto_connect','auto_adas','arm_sim','auto_game3d'),expected))])

    def test_game_opens_standalone_without_loading_the_qt_application(self):
        calls=[];standalone=types.ModuleType('device_studio.standalone');qt=types.ModuleType('device_studio.qt_app')
        def launch():calls.append('release');return 0
        def forbidden(**kwargs):raise AssertionError('Studio should not be loaded for the independent game')
        standalone.launch=launch;qt.main=forbidden
        with patch.dict(sys.modules,{'device_studio.standalone':standalone,'device_studio.qt_app':qt}),patch.object(sys,'argv',[str(ROOT/'studio.py'),'--game']):
            with self.assertRaises(SystemExit) as result:runpy.run_path(str(ROOT/'studio.py'),run_name='__main__')
        self.assertEqual(result.exception.code,0)
        self.assertEqual(calls,['release'])


if __name__=='__main__':unittest.main()
