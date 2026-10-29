import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
import zlib
from device_studio.protocol import *

class ProtocolTests(unittest.TestCase):
    def firmware(self,app_id=2,version=1):
        data=bytearray(2048)
        struct.pack_into('<II',data,0,0x2026FFF0,APP_BASE+0x421)
        struct.pack_into('<IIII',data,0x400,0x44415631,app_id,version,1)
        return bytes(data)
    def manifest(self,data):
        return dict(schema=1,board=BOARD,protocol=1,base=APP_BASE,id=2,name='Duello',version=1,
                    size=len(data),sha256=hashlib.sha256(data).hexdigest(),crc32=zlib.crc32(data))
    def test_frame_roundtrip(self):
        payload=bytes(range(256))*4
        self.assertEqual(decode(encode(42,DATA,payload)),(42,DATA,payload))
    def test_frame_corruption(self):
        frame=bytearray(encode(3,DATA,b'firmware'));frame[-1]^=1
        with self.assertRaises(ProtocolError):decode(frame)
    def test_truncated_frame(self):
        with self.assertRaises(ProtocolError):decode(encode(3,HELLO)[:-1])
    def test_oversize_frame(self):
        with self.assertRaises(ProtocolError):decode(encode(3,DATA,b'x'*1041))
    def test_wrong_link_address(self):
        data=bytearray(self.firmware());struct.pack_into('<I',data,4,0x08000421)
        with self.assertRaises(ProtocolError):Firmware.validate(self.manifest(data),data)
    def test_wrong_board(self):
        data=self.firmware();m=self.manifest(data);m['board']='other'
        with self.assertRaises(ProtocolError):Firmware.validate(m,data)
    def test_id_mismatch(self):
        data=self.firmware();m=self.manifest(data);m['id']=1;m['name']='Smartwatch'
        with self.assertRaises(ProtocolError):Firmware.validate(m,data)
    def test_tampered_binary(self):
        data=self.firmware();m=self.manifest(data)
        with self.assertRaises(ProtocolError):Firmware.validate(m,data[:-1]+b'x')
    def test_mailbox_stack_overlap(self):
        data=bytearray(self.firmware());struct.pack_into('<I',data,0,0x20270000)
        with self.assertRaises(ProtocolError):Firmware.validate(self.manifest(data),data)
    def test_package_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/'app.bin';src.write_bytes(self.firmware());out=Path(t)/'app.dfw'
            package(src,out,'Duello');self.assertEqual(Firmware.load(out).data,src.read_bytes())
    def test_invalid_manifest_type(self):
        with self.assertRaises(ProtocolError):Firmware.validate([],self.firmware())
    def test_invalid_app_id(self):
        data=self.firmware();m=self.manifest(data);m['id']=900
        with self.assertRaises(ProtocolError):Firmware.validate(m,data)
    def test_custom_application_roundtrip(self):
        for app_id in (3,900,APP_ID_MAX):
            with self.subTest(app_id=app_id),tempfile.TemporaryDirectory() as t:
                src=Path(t)/'app.bin';src.write_bytes(self.firmware(app_id,7));out=Path(t)/'app.dfw'
                m=package(src,out,'ThirdApp')
                self.assertEqual((m['id'],m['version']),(app_id,7))
                self.assertEqual(Firmware.load(out).data,src.read_bytes())
    def test_reserved_or_out_of_range_identity(self):
        for app_id,name,version in [(0,'ThirdApp',1),(0xffffffff,'ThirdApp',1),(-1,'ThirdApp',1),
                                    (True,'Smartwatch',1),(3,'ThirdApp',0),(3,'ThirdApp',True),
                                    (3,'ThirdApp',0x100000000),(3,'DeviceBoot',1),
                                    (3,'Duello',1),(3,'smartwatch',1),(1,'ThirdApp',1),
                                    (3,'bad name',1),(3,'bad"name',1),(3,'A'*49,1)]:
            with self.subTest(app_id=app_id,name=name,version=version):
                with self.assertRaises(ProtocolError):validate_identity(app_id,name,version)
    def test_explicit_package_identity_must_match_binary(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/'app.bin';src.write_bytes(self.firmware(3,7));out=Path(t)/'app.dfw'
            for kwargs in ({'app_id':4},{'version':8}):
                with self.subTest(kwargs=kwargs),self.assertRaises(ProtocolError):package(src,out,'ThirdApp',**kwargs)
            self.assertFalse(out.exists())
if __name__=='__main__':unittest.main()
