"""Exercise an already installed ADASLab on the real board; does not flash it.

Runs the desktop plant against MCU decisions, then compares the saved settings
journal. Leaves ADASLab paused, ready for the Studio panel.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
from device_studio.connection import Device
from device_studio.protocol import ProtocolError
from device_studio.adas_sim import World,Config
from device_studio import programmer

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True)
p.add_argument('--settings-before',type=Path,default=ROOT/'Backup/adaslab-initial/settings-before.bin')
a=p.parse_args();report={'scope':'Physical STM32U5A9J-DK UART closed-loop tests; no physical sensors','checks':[],'scenarios':[]}
def check(ok,name):
    report['checks'].append({'name':name,'passed':bool(ok)});print(('PASS: ' if ok else 'FAIL: ')+name,flush=True)
    if not ok:raise AssertionError(name)
d=Device(a.port)
try:
    hello=d.detect();check((hello.get('app'),hello.get('id'),hello.get('boot_version'))==('ADASLab',3,2),'ADASLab ID 3 starts under DeviceBoot revision 2')
    for scenario in ('brake','follow','cutin','cruise'):
        world=World(Config(scenario=scenario,repeat=False));d.runtime('RESET');d.runtime('C:2500:1800')
        modes=set();minimum=1000.;rtts=[];initial_frames=0;initial_gpu=0;latest={}
        for i in range(240):
            start=time.monotonic();r=d.runtime(world.command(),timeout=.8);rtts.append((time.monotonic()-start)*1000)
            latest=r['state'];assert not latest['error'] and latest['ms']==world.tick and latest['fresh']
            modes.add(latest['mode'])
            if i==0:initial_frames=latest['frames'];initial_gpu=latest['gpu']
            world.advance(latest['a']/100);minimum=min(minimum,world.gap)
            if world.collision:break
            if i%80==79:print(f'{scenario}: {world.seconds:.1f} simulated seconds, gap {world.gap:.2f} m',flush=True)
            time.sleep(max(0,.05-(time.monotonic()-start)))
        check(not world.collision,scenario+': no collision')
        check(latest['gpu']>initial_gpu and latest['frames']>initial_frames,scenario+': real GPU and LCD presentation counters advance')
        row=dict(scenario=scenario,minimum_gap_m=round(minimum,3),modes=sorted(modes),samples=len(rtts),
                 rtt_mean_ms=round(statistics.mean(rtts),2),rtt_max_ms=round(max(rtts),2),
                 deadline_overruns=sum(t>50 for t in rtts),compute_max_us=latest['us'],
                 frame_max_ms=latest['frame_max_ms'],gpu=latest['gpu'],frames=latest['frames'])
        report['scenarios'].append(row);print(json.dumps(row),flush=True)
    d.runtime('RESET');world=World(Config());cmd=world.command();r=d.runtime(cmd)
    corrupt=cmd[:-1]+('0' if cmd[-1]!='0' else '1')
    check(d.runtime(corrupt)['state']['error']=='sample_crc','CRC-damaged measurement is rejected')
    check(d.runtime(cmd)['state']['error']=='invalid_sample','Duplicate timestamp is rejected')
    time.sleep(.7);r=d.runtime('STATUS')
    check(r['state']['mode']=='NO_DATA' and r['state']['a']==0,'Missing samples disable acceleration after 500 ms')
    check(d.runtime('PAUSE')['state']['a']==0,'PAUSE clears control output')
    d.close();d=None
    after=ROOT/'Backup/adaslab-initial/settings-after.bin'
    programmer.execute(programmer.connection()+['-u','0x083fc000',16384,after])
    check(a.settings_before.read_bytes()==after.read_bytes(),'16 KiB settings journal preserved byte for byte')
    report['settings_sha256']=hashlib.sha256(after.read_bytes()).hexdigest();report['passed']=True
    # CubeProgrammer's memory-read session can leave the core stopped. Resume
    # through the installed bootloader before handing the device back to Studio.
    programmer.execute(programmer.connection()+['-rst','-g','0x08000000'])
except Exception as exc:
    report['passed']=False;report['error']=str(exc);raise
finally:
    if d:
        try:d.runtime('PAUSE',timeout=.5)
        except Exception:pass
        d.close()
    (ROOT/'adas-hardware-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
