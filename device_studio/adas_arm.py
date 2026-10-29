"""Explicit ARM simulation backend, running the built firmware controller ELF.

This backend never opens a serial port or programs physical hardware. GPU/display
peripherals are not emulated; their counters remain zero. Used with --adas-sim.
"""
from pathlib import Path
import json
import struct
import sys
import time
from .protocol import ProtocolError

class ArmDevice:
    def __init__(self,elf_path=None):
        root=Path(__file__).resolve().parents[2]
        for name in ('smart_watch-main','Smartwatch','smart_watch'):
            libs=root/name/'tmp/simulator-libs'
            if libs.is_dir():sys.path.insert(0,str(libs));break
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
        from unicorn.arm_const import UC_CPU_ARM_CORTEX_M33,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_LR
        from elftools.elf.elffile import ELFFile
        self.regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
        self.pc=UC_ARM_REG_PC;self.sp=UC_ARM_REG_SP;self.lr=UC_ARM_REG_LR
        self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);self.u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M33)
        for address,size in [(0x08000000,0x400000),(0x20000000,0x280000),(0x0fff0000,0x1000),(0xe0000000,0x10000)]:self.u.mem_map(address,size)
        path=Path(elf_path) if elf_path else root/'ADASLab/build/ADASLab.elf'
        with path.open('rb') as source:
            elf=ELFFile(source)
            self.symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
            for segment in elf.iter_segments():
                if segment['p_type']=='PT_LOAD':self.u.mem_write(segment['p_vaddr'],segment.data())
        self.epoch=time.monotonic();self.sequence=0;self.current=None;self.closed=False
        def get_tick(*args):
            self.u.reg_write(self.regs[0],int((time.monotonic()-self.epoch)*1000)&0xffffffff)
            self.u.reg_write(self.pc,self.u.reg_read(self.lr))
        address=self.symbols['HAL_GetTick']&~1
        self.u.hook_add(UC_HOOK_CODE,get_tick,begin=address,end=address)
        self.u.mem_write(0x20260000,b'ADASLab\0')
        self.call('device_runtime_init',0x20260000,self.symbols['adas_command'])
        self.runtime('RESET')
    def call(self,name,*args):
        stack=0x2026f000
        for register,value in zip(self.regs,args[:4]):self.u.reg_write(register,value)
        for index,value in enumerate(args[4:]):self.u.mem_write(stack+index*4,struct.pack('<I',value))
        self.u.reg_write(self.sp,stack);self.u.reg_write(self.lr,0x0fff0001)
        self.u.emu_start(self.symbols[name]|1,0x0fff0000,count=1000000)
        if self.u.reg_read(self.pc)!=0x0fff0000:raise ProtocolError('ARM simülasyonu komutu tamamlayamadı')
        return self.u.reg_read(self.regs[0])
    def runtime(self,command,timeout=2):
        if self.closed:raise ProtocolError('ARM simülasyonu kapalı')
        if not command or len(command)>39 or any(ord(c)<=32 or ord(c)>126 for c in command):raise ProtocolError('Geçersiz runtime komutu')
        self.sequence+=1;self.u.mem_write(0x20260080,command.encode('ascii')+b'\0')
        n=self.call('device_runtime_format_reply',self.sequence,0x20260080,0x20260100,512,0x20260400)
        if not 0<n<512:raise ProtocolError('ARM cevabı TX tamponuna sığmadı')
        response=json.loads(bytes(self.u.mem_read(0x20260100,n)))
        response['backend']='ARM_SIM'
        self.current=response
        if response.get('error'):raise ProtocolError(response['error'])
        return response
    def detect(self):return self.runtime('HELLO')
    def close(self):self.closed=True;self.current=None
    def enter_boot(self):raise ProtocolError('ARM simülasyonunda Flash yükleme kapalı; fiziksel karta bağlanın')
    def run(self):return self.runtime('HELLO')
    def upload(self,*args,**kwargs):self.enter_boot()
