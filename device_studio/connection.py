"""Single-owner serial connection; all work occurs off the GUI thread."""
import json
import struct
import time
import threading
import serial
from .protocol import *

class Device:
    def __init__(self,port):
        self.port=serial.Serial(port,RUNTIME_BAUD,timeout=.08,write_timeout=3)
        self.seq=0
        self.current=None
    def close(self): self.port.close()
    def _seq(self):
        self.seq=(self.seq+1)&0x7fffffff
        return self.seq
    def runtime(self,command,timeout=2):
        self.port.baudrate=RUNTIME_BAUD
        seq=self._seq()
        self.port.write(f'REQ {seq} {command}\n'.encode('ascii'))
        end=time.monotonic()+timeout
        line=bytearray()
        while time.monotonic()<end:
            b=self.port.read(1)
            if b==b'\n':
                try: response=json.loads(line)
                except (ValueError,UnicodeDecodeError): response={}
                line.clear()
                if isinstance(response,dict) and response.get('seq')==seq:
                    if response.get('protocol')!=1: raise ProtocolError('Desteklenmeyen protokol')
                    self.current=response
                    if response.get('error'): raise ProtocolError(response['error'])
                    return response
            elif b:
                if len(line)<1024: line.extend(b)
                else: line.clear()
        raise TimeoutError('Uygulamadan cevap alinamadi')
    def boot(self,command,payload=b'',timeout=3,retries=2):
        self.port.baudrate=BOOT_BAUD
        seq=self._seq();frame=encode(seq,command,payload)
        for attempt in range(retries+1):
            self.port.write(frame)
            end=time.monotonic()+timeout
            buffer=bytearray()
            while time.monotonic()<end:
                buffer.extend(self.port.read(max(1,self.port.in_waiting)))
                index=buffer.find(MAGIC)
                if index<0:
                    if len(buffer)>3: del buffer[:-3]
                    continue
                if index: del buffer[:index]
                if len(buffer)<20: continue
                length=struct.unpack_from('<I',buffer,12)[0]
                if length>1040: del buffer[0];continue
                if len(buffer)<20+length: continue
                candidate=bytes(buffer[:20+length]);del buffer[:20+length]
                try: rseq,cmd,data=decode(candidate)
                except ProtocolError: continue
                if rseq!=seq or cmd!=(command|0x80000000): continue
                if len(data)<4: raise ProtocolError('Eksik bootloader cevabi')
                status=struct.unpack_from('<I',data)[0]
                if status: raise ProtocolError(f'Bootloader hata kodu: {status}')
                try: response=json.loads(data[4:])
                except ValueError as exc: raise ProtocolError('Bootloader cevabi okunamadi') from exc
                if not isinstance(response,dict): raise ProtocolError('Gecersiz bootloader cevabi')
                if command in (HELLO,STATUS): self.current=response
                return response
        raise TimeoutError('Bootloader cevap vermedi; baglantiyi ve USER butonuyla kurtarma modunu kontrol edin')
    def detect(self,timeout=16):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.port.baudrate=RUNTIME_BAUD
            self.port.reset_input_buffer();self.port.write(b'\n')
            try: return self.runtime('HELLO',timeout=.65)
            except TimeoutError:
                self.port.reset_input_buffer()
                try: result=self.boot(HELLO,timeout=3,retries=0)
                except TimeoutError: continue
                if result.get('protocol')!=1 or result.get('base')!=APP_BASE or result.get('max')!=APP_MAX:
                    raise ProtocolError('Bootloader bellek yerlesimi uyusmuyor')
                return result
        raise TimeoutError('Cihaz cevap vermedi; bootloader durumu tespit edilemedi')
    def enter_boot(self):
        if not self.current: self.detect()
        if self.current.get('app')=='DeviceBoot': return self.boot(HELLO)
        if self.current.get('boot')!=1: raise ProtocolError('DeviceBoot kurulu degil; once ST-LINK kurulumu yapin')
        self.runtime('BOOT')
        time.sleep(.3)
        self.port.baudrate=BOOT_BAUD;self.port.reset_input_buffer()
        self.current=self.boot(HELLO,timeout=2)
        return self.current
    def run(self):
        self.boot(RUN)
        self.port.baudrate=RUNTIME_BAUD
        end=time.monotonic()+12
        while time.monotonic()<end:
            try: return self.runtime('HELLO',timeout=.8)
            except TimeoutError: time.sleep(.15)
        raise TimeoutError('Firmware dogrulandi ama uygulamadan hazir cevabi gelmedi')
    def upload(self,firmware,progress=lambda p,s:None,cancel=None):
        cancel=cancel or threading.Event()
        self.enter_boot();data=firmware.data;m=firmware.manifest
        progress(0,'Uygulama alani hazirlaniyor; bootloader ve saat kayitlari korunuyor')
        self.boot(BEGIN,struct.pack('<III',len(data),m['crc32'],m['id']),timeout=90,retries=0)
        try:
            for offset in range(0,len(data),1024):
                if cancel.is_set(): raise InterruptedError('Yukleme iptal edildi; cihaz kurtarma modunda')
                block=data[offset:offset+1024]
                response=self.boot(DATA,struct.pack('<I',offset)+block,timeout=3)
                if response.get('written')!=offset+len(block): raise ProtocolError('Yazilan bayt sayisi uyusmuyor')
                progress((offset+len(block))/len(data)*95,f'{offset+len(block):,} / {len(data):,} bayt')
            progress(96,'Flash icerigi CRC ile dogrulaniyor')
            self.boot(FINISH,timeout=15)
            progress(98,'Firmware dogrulandi; uygulamanin hazir cevabi bekleniyor')
            response=self.run()
            if response.get('app')!=m['name']: raise ProtocolError('Beklenen uygulama baslamadi')
            progress(100,'Firmware basariyla yuklendi; uygulama hazir')
            return response
        except Exception:
            try: self.boot(ABORT,timeout=1,retries=0)
            except Exception: pass
            raise
