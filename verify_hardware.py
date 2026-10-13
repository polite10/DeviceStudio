"""Explicit real-board smoke test: recovery, commands, two UART uploads, settings preservation."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent/'.deps'))
from device_studio.connection import Device
from device_studio.protocol import *
from device_studio import programmer

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--port',default='COM5');p.add_argument('--install',action='store_true');p.add_argument('--leave-duello',action='store_true')
a=p.parse_args();report={'checks':[]};device=None
def check(condition,name):
    report['checks'].append({'name':name,'passed':bool(condition)})
    print(('PASS ' if condition else 'FAIL ')+name,flush=True)
    if not condition:raise AssertionError(name)
def snapshot(name):
    path=ROOT/'Backup'/name;path.parent.mkdir(exist_ok=True)
    programmer.execute(programmer.connection()+['-u','0x083fc000',16384,path])
    return path.read_bytes()
def upload(path):
    last=[-1]
    def progress(percent,text):
        step=int(percent)//10
        if step!=last[0]:last[0]=step;print(f'UPLOAD {percent:.0f}% {text}',flush=True)
    return device.upload(Firmware.load(path),progress)
try:
    before=snapshot('settings-before.bin')
    if a.install:
        r=programmer.install(ROOT.parent/'DeviceBoot/Firmware/DeviceBoot.bin',ROOT/'Backup')
        report['backup']=r['backup'];print('Bootloader installed; full backup saved',flush=True)
    check(programmer.inspect()['installed'],'boot descriptor through SWD')
    device=Device(a.port);r=device.detect();check(r['app']=='DeviceBoot','bootloader UART identity')
    # Invalid sizes and commands must not erase valid firmware or protected regions.
    for size,app_id in [(APP_MAX+1,1),(0,1),(2048,99)]:
        rejected=False
        try:device.boot(BEGIN,struct.pack('<III',size,0,app_id))
        except ProtocolError:rejected=True
        check(rejected,f'BEGIN rejected size={size} id={app_id}')
    device.boot(BEGIN,struct.pack('<III',2048,0,2))
    device.boot(DATA,struct.pack('<I',0)+b'\xff'*1024)
    device.boot(ABORT)
    rejected=False
    try:device.boot(RUN)
    except ProtocolError:rejected=True
    check(rejected,'incomplete upload cannot start')
    device.close();device=None
    programmer.execute(programmer.connection()+['-rst','-g','0x08000000']);time.sleep(.4)
    device=Device(a.port);r=device.detect();check(r['app']=='DeviceBoot' and not r['valid'],'reset after aborted upload remains in recovery')
    r=upload(ROOT/'Firmware/Duello.dfw');check(r['app']=='Duello' and r['boot']==1,'Duello started after custom bootloader upload')
    check(device.runtime('FIRE')['state']['error']=='draw_first','cannot fire before drawing')
    r=device.runtime('DRAW');check(r['state']['action']=='draw','draw command accepted')
    time.sleep(.8);r=device.runtime('STATUS');check(r['state']['gun']=='drawn' and r['state']['action']=='idle','draw animation completes')
    r=device.runtime('FIRE');check(r['state']['ammo']==5 and r['state']['target_hp']==2,'fire changes ammo and target state')
    check(device.runtime('FIRE')['state']['error']=='busy','busy animation rejects second action')
    time.sleep(.4);device.runtime('RELOAD');time.sleep(1);check(device.runtime('STATUS')['state']['ammo']==6,'reload completes')
    device.runtime('HOLSTER');time.sleep(.8);check(device.runtime('STATUS')['state']['gun']=='holstered','holster animation completes')
    device.runtime('WALK');time.sleep(5.4);check(not device.runtime('STATUS')['state']['walking'],'disconnect timeout stops walking')
    check(device.runtime('RESET')['state']['target_hp']==3,'scene reset')
    r=upload(ROOT/'Firmware/Smartwatch.dfw');check(r['app']=='Smartwatch' and r['boot']==1,'Smartwatch restored through custom bootloader')
    device.close();device=None
    programmer.execute(programmer.connection()+['-rst','-g','0x08000000']);time.sleep(2)
    device=Device(a.port);r=device.detect();check(r['app']=='Smartwatch','normal reset auto-starts Smartwatch')
    device.close();device=None
    after=snapshot('settings-after.bin');check(before==after,'16 KiB settings journal preserved byte for byte')
    report['settings_sha256']=hashlib.sha256(after).hexdigest()
    if a.leave_duello:
        device=Device(a.port);device.detect();r=upload(ROOT/'Firmware/Duello.dfw');check(r['app']=='Duello','Duello ready for manual test')
    report['passed']=True
except Exception as exc:
    report['passed']=False;report['error']=str(exc);raise
finally:
    if device:device.close()
    (ROOT/'hardware-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
