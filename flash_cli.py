from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'.deps'))
from device_studio.connection import Device
from device_studio.protocol import Firmware
p=argparse.ArgumentParser();p.add_argument('package');p.add_argument('--port',default='COM5')
a=p.parse_args();firmware=Firmware.load(a.package);device=Device(a.port)
last=[-1]
def progress(percent,text):
    step=int(percent)//5
    if step!=last[0]:last[0]=step;print(f'{percent:.0f}% {text}',flush=True)
try:
    print(device.detect(),flush=True)
    print(device.upload(firmware,progress),flush=True)
finally:device.close()
