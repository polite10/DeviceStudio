import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from device_studio.gui import Studio

class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.app=Studio(self.root)
    def tearDown(self):self.root.destroy()
    def test_starts_on_firmware_screen(self):
        self.assertEqual(self.app.tabs.index(self.app.tabs.select()),0)
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.control_buttons))
    def test_boot_and_running_application_are_separate(self):
        self.app.update(dict(app='Smartwatch',version=1,boot=1))
        self.assertIn('kurulu',self.app.boot_text.get());self.assertIn('Smartwatch',self.app.app_text.get())
        self.app.update(dict(app='DeviceBoot',version=1,valid=False))
        self.assertIn('çalışıyor',self.app.boot_text.get());self.assertIn('kurtarma',self.app.app_text.get())
    def test_duello_buttons_and_state(self):
        response=dict(app='Duello',version=1,boot=1,state=dict(gun='holstered',action='idle',ammo=6,target_hp=3))
        self.app.device=SimpleNamespace(current=response)
        self.app.update(response);self.app.enable()
        labels=[b['text'] for b in self.app.control_buttons]
        self.assertIn('Silahı çıkar',labels);self.assertIn('Ateş et',labels)
        self.assertTrue(all(str(b['state'])=='normal' for b in self.app.control_buttons))
        self.assertIn('Mermi: 6',self.app.state_text.get())
    def test_custom_app_generic_controls(self):
        response=dict(app='ThirdApp',id=3,version=7,boot=1,boot_version=2,state=dict(counter=42))
        self.app.device=SimpleNamespace(current=response)
        self.app.update(response);self.app.enable();self.app.upload_done(response)
        self.assertEqual(self.app.tabs.index(self.app.tabs.select()),2)
        self.assertTrue(all(str(b['state'])=='normal' for b in self.app.app_buttons))
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.control_buttons))
        self.assertIn('42',self.app.app_state_text.get());self.assertIn('v2',self.app.boot_text.get())
    def test_bootloader_disables_generic_controls(self):
        self.app.device=SimpleNamespace(current=dict(app='DeviceBoot'))
        self.app.enable()
        self.assertTrue(all(str(b['state'])=='disabled' for b in self.app.app_buttons))
        self.assertEqual(str(self.app.command_entry['state']),'disabled')
    def test_adas_panel_is_selected_for_adas_firmware(self):
        response=dict(app='ADASLab',id=3,version=1,boot=1,state={})
        self.app.device=SimpleNamespace(current=response)
        self.app.upload_done(response);self.app.enable()
        self.assertEqual(self.app.tabs.index(self.app.tabs.select()),3)
        self.assertEqual(str(self.app.adas_panel.start_button['state']),'normal')
    def test_uppercase_stlink_port_is_preferred_over_debug_console(self):
        ports=[SimpleNamespace(device='/dev/cu.debug-console',description='n/a'),
               SimpleNamespace(device='/dev/cu.usbmodem11103',description='STLINK-V3')]
        with patch('device_studio.gui.serial.tools.list_ports.comports',return_value=ports):self.app.refresh()
        self.assertEqual(self.app.port_map[self.app.port.get()],'/dev/cu.usbmodem11103')
if __name__=='__main__':unittest.main()
