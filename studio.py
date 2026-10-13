from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'.deps'))
from device_studio.gui import main
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--connect',action='store_true')
    main(auto_connect=p.parse_args().connect)
