"""Exercise the upload transaction without opening a serial port or touching Flash."""
import struct
import unittest
from device_studio.connection import Device
from device_studio.protocol import *


class UploadDevice(Device):
    def __init__(self,firmware,modern=True):
        self.firmware=firmware;self.modern=modern;self.commands=[];self.written=0
    def enter_boot(self):return {'max_app_id':APP_ID_MAX} if self.modern else {'version':1}
    def boot(self,command,payload=b'',**kwargs):
        self.commands.append(command)
        if command==DATA:
            offset=struct.unpack_from('<I',payload)[0]
            if offset!=self.written:raise AssertionError('Non-contiguous upload')
            self.written+=len(payload)-4
            return {'written':self.written}
        return {}
    def run(self):
        m=self.firmware.manifest
        return dict(app=m['name'],id=m['id'],version=m['version'],ready=True)


def firmware(app_id=3,name='ThirdApp'):
    import hashlib
    import zlib
    data=bytearray(2048)
    struct.pack_into('<II',data,0,0x2026FFF0,APP_BASE+0x421)
    struct.pack_into('<4I',data,0x400,0x44415631,app_id,7,1)
    manifest=dict(schema=1,board=BOARD,protocol=1,base=APP_BASE,id=app_id,name=name,version=7,
                  size=len(data),sha256=hashlib.sha256(data).hexdigest(),crc32=zlib.crc32(data))
    return Firmware(manifest,bytes(data))


class UploadTests(unittest.TestCase):
    def test_third_application_upload(self):
        device=UploadDevice(firmware());result=device.upload(device.firmware)
        self.assertEqual((result['app'],result['id'],result['version']),('ThirdApp',3,7))
        self.assertEqual(device.commands,[BEGIN,DATA,DATA,FINISH])
    def test_legacy_bootloader_rejected_before_begin(self):
        device=UploadDevice(firmware(),modern=False)
        with self.assertRaisesRegex(ProtocolError,'DeviceBoot v2'):device.upload(device.firmware)
        self.assertEqual(device.commands,[])
    def test_both_existing_apps_still_upload_on_legacy_bootloader(self):
        for app_id,name in BUILTIN_APPS.items():
            with self.subTest(app=name):
                device=UploadDevice(firmware(app_id,name),modern=False)
                self.assertEqual(device.upload(device.firmware)['app'],name)
    def test_wrong_started_identity_aborts(self):
        device=UploadDevice(firmware());device.run=lambda:dict(app='ThirdApp',id=4,version=7)
        with self.assertRaises(ProtocolError):device.upload(device.firmware)
        self.assertEqual(device.commands[-1],ABORT)
    def test_invalid_package_rejected_before_bootloader(self):
        device=UploadDevice(firmware());device.firmware.manifest['id']=0
        device.enter_boot=lambda:self.fail('Invalid package entered bootloader')
        with self.assertRaises(ProtocolError):device.upload(device.firmware)
