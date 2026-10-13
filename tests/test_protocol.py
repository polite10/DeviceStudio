import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
import zlib
from device_studio.protocol import *

class ProtocolTests(unittest.TestCase):
    def firmware(self):
        data=bytearray(2048)
        struct.pack_into('<II',data,0,0x2026FFF0,APP_BASE+0x421)
        struct.pack_into('<IIII',data,0x400,0x44415631,2,1,1)
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
if __name__=='__main__':unittest.main()
