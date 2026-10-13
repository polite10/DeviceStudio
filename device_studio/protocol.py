"""DeviceBoot v1 framing and bounded .dfw firmware packages."""
import hashlib
import json
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

MAGIC=b'DBT1'
APP_BASE=0x0800A000
APP_MAX=0x083FC000-APP_BASE
BOOT_BAUD=921600
RUNTIME_BAUD=115200
BOARD='STM32U5A9J-DK'
HELLO,BEGIN,DATA,FINISH,RUN,STATUS,ABORT=range(1,8)

class ProtocolError(Exception): pass

def encode(seq,command,payload=b''):
    prefix=struct.pack('<4sIII',MAGIC,seq,command,len(payload))
    return prefix+struct.pack('<I',zlib.crc32(prefix+payload))+payload

def decode(frame):
    if len(frame)<20: raise ProtocolError('Eksik paket')
    magic,seq,cmd,size,crc=struct.unpack('<4sIIII',frame[:20])
    if magic!=MAGIC or size>1040 or len(frame)!=20+size: raise ProtocolError('Gecersiz paket boyutu')
    if zlib.crc32(frame[:16]+frame[20:])!=crc: raise ProtocolError('Paket CRC hatasi')
    return seq,cmd,frame[20:]

@dataclass(frozen=True)
class Firmware:
    manifest: dict
    data: bytes
    @classmethod
    def load(cls,path):
        try:
            with zipfile.ZipFile(path) as archive:
                if set(archive.namelist())!={'manifest.json','firmware.bin'}: raise ProtocolError('Paket iki beklenen dosyayi icermeli')
                if archive.getinfo('manifest.json').file_size>4096 or archive.getinfo('firmware.bin').file_size>APP_MAX:
                    raise ProtocolError('Paket cok buyuk')
                manifest=json.loads(archive.read('manifest.json'))
                data=archive.read('firmware.bin')
        except (OSError,zipfile.BadZipFile,json.JSONDecodeError,KeyError) as exc:
            raise ProtocolError(f'Firmware paketi okunamadi: {exc}') from exc
        cls.validate(manifest,data)
        return cls(manifest,data)
    @staticmethod
    def validate(m,data):
        if not isinstance(m,dict) or m.get('schema')!=1 or m.get('board')!=BOARD or m.get('protocol')!=1 or m.get('base')!=APP_BASE:
            raise ProtocolError('Kart veya protokol uyusmuyor')
        if not 0x410<=len(data)<=APP_MAX or m.get('size')!=len(data): raise ProtocolError('Firmware bellek sinirlarinin disinda')
        if m.get('id') not in (1,2) or m.get('name')!={1:'Smartwatch',2:'Duello'}[m['id']]: raise ProtocolError('Uygulama kimligi gecersiz')
        if m.get('sha256')!=hashlib.sha256(data).hexdigest() or m.get('crc32')!=zlib.crc32(data): raise ProtocolError('Dosya dogrulamasi basarisiz')
        sp,pc=struct.unpack_from('<II',data)
        if not 0x20000000<=sp<=0x2026FFF0 or sp&7 or not pc&1 or not APP_BASE<=pc&~1<APP_BASE+len(data):
            raise ProtocolError('Yanlis adrese derlenmis firmware')
        magic,app_id,version,protocol=struct.unpack_from('<IIII',data,0x400)
        if (magic,app_id,protocol)!=(0x44415631,m['id'],1) or version!=m.get('version'): raise ProtocolError('Firmware kimligi eslesmiyor')

def package(binary,output,name,version=1):
    data=Path(binary).read_bytes()
    m={'schema':1,'board':BOARD,'protocol':1,'base':APP_BASE,'id':{'Smartwatch':1,'Duello':2}[name],
       'name':name,'version':version,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'crc32':zlib.crc32(data)}
    Firmware.validate(m,data)
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(m,ensure_ascii=False,indent=2))
        archive.writestr('firmware.bin',data)
    return m
