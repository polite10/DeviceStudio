from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'.deps'))
from device_studio.qt_app import main
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--connect',action='store_true',help='Seçili kartın seri portuna bağlan')
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--adas',action='store_true',help='Karttaki ADASLab laboratuvar deneyini başlat')
    modes.add_argument('--adas-sim',action='store_true',help='ADASLab ARM ELF laboratuvar deneyi; fiziksel kart kullanılmaz')
    modes.add_argument('--game',action='store_true',help='Karttaki ADASLab v2 trafik oyununa bağlan; Başlat ile sür')
    modes.add_argument('--game-sim',action='store_true',help='ARM ELF trafik oyununa bağlan; fiziksel kart kullanılmaz')
    args=p.parse_args()
    sys.exit(main(auto_connect=args.connect or args.adas or args.adas_sim or args.game or args.game_sim,
                  auto_adas=args.adas or args.adas_sim,arm_sim=args.adas_sim or args.game_sim))
