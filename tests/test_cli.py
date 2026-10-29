"""All launch modes use the embedded Studio scene; simulation remains explicit."""
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
            None:(True,False,False,False),
            '--connect':(True,False,False,False),
            '--adas':(True,False,False,False),
            '--adas-sim':(True,False,True,False),
            '--game-sim':(True,False,True,False),
            '--game':(True,False,False,False),
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



if __name__=='__main__':unittest.main()
