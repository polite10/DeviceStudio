from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'.deps'))
from device_studio.gui import main
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--connect',action='store_true');p.add_argument('--adas',action='store_true')
    p.add_argument('--adas-sim',action='store_true',help='ADASLab ARM ELF simülasyonu; fiziksel kart kullanılmaz')
    args=p.parse_args();main(auto_connect=args.connect or args.adas or args.adas_sim,auto_adas=args.adas or args.adas_sim,arm_sim=args.adas_sim)
