import tkinter as tk
import unittest
from types import SimpleNamespace
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
if __name__=='__main__':unittest.main()
