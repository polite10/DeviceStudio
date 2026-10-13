"""Initial ST-LINK installation and read-only boot descriptor diagnostics."""
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from .protocol import ProtocolError,APP_BASE,APP_MAX
BOOT_INFO=0x08007F00

def find_programmer():
    candidates=[]
    if os.environ.get('STM32_PROGRAMMER_CLI'): candidates.append(Path(os.environ['STM32_PROGRAMMER_CLI']))
    candidates+=list(Path('C:/ST').glob('STM32CubeIDE_*/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_*/tools/bin/STM32_Programmer_CLI.exe'))
    candidates.append(Path('C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe'))
    for p in reversed(candidates):
        if p.is_file(): return p
    raise FileNotFoundError('STM32CubeProgrammer bulunamadi; STM32_PROGRAMMER_CLI yolunu ayarlayin')

def execute(args,timeout=120,log=lambda s:None):
    result=subprocess.run([str(find_programmer()),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=result.stdout.decode('utf-8',errors='replace')
    log(output)
    if result.returncode or re.search(r'Error:|No ST-Link detected|No STM32 target found',output,re.I):
        raise ProtocolError('ST-LINK islemi basarisiz: '+output[-1200:])
    return output

def connection(serial_number=None,mode='HOTPLUG'):
    return ['-c','port=SWD',f'mode={mode}',*([f'sn={serial_number}'] if serial_number else [])]

def inspect(serial_number=None,log=lambda s:None):
    with tempfile.TemporaryDirectory() as temp:
        target=Path(temp)/'identity.bin'
        execute(connection(serial_number)+['-u',hex(BOOT_INFO),32,target],log=log)
        data=target.read_bytes()
        if len(data)!=32: raise ProtocolError('Bootloader kimligi okunamadi')
        magic,version,base,size,protocol,board,baud,_=struct.unpack('<8I',data)
        present=(magic,base,size,protocol,board)==(0x44425631,APP_BASE,APP_MAX,1,0x481)
        return {'installed':present,'version':version if present else None,'baud':baud if present else None}

def install(binary,backup_dir,serial_number=None,log=lambda s:None):
    binary=Path(binary).resolve();data=binary.read_bytes()
    if not 0x7f20<=len(data)<=0x8000 or struct.unpack_from('<I',data,0x7f00)[0]!=0x44425631:
        raise ProtocolError('Gecersiz DeviceBoot binary')
    with tempfile.TemporaryDirectory() as temp:
        chip=Path(temp)/'chip.bin'
        target_info=execute(connection(serial_number)+['-u','0x08000000',16,chip],log=log)
        if not re.search(r'Device ID\s*:\s*0x481',target_info) or not re.search(r'NVM size\s*:\s*4 MBytes',target_info):
            raise ProtocolError('Bu DeviceBoot yalniz 4 MiB STM32U5A9J-DK icindir')
        if len(chip.read_bytes())!=16: raise ProtocolError('Kart bellegi okunamadi')
    import datetime
    folder=Path(backup_dir)/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder.mkdir(parents=True,exist_ok=False)
    backup=folder/'before-deviceboot-flash.bin'
    execute(connection(serial_number)+['-u','0x08000000',4194304,backup],log=log)
    if backup.stat().st_size!=4194304: raise ProtocolError('Tam yedek alinmadan kuruluma devam edilemez')
    (folder/'sha256.txt').write_text(hashlib.sha256(backup.read_bytes()).hexdigest()+'\n',encoding='ascii')
    # Only boot+metadata pages are erased; application and settings pages remain untouched.
    execute(connection(serial_number,'UR')+['-e','0','1','2','3','4','-d',binary,'0x08000000','-v','-rst','-g','0x08000000'],log=log)
    return {'installed':True,'version':1,'backup':str(backup)}
