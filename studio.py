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
    modes.add_argument('--game',action='store_true',help='Karttaki ADASLab v2 ile Godot 3B sürüş penceresini aç')
    modes.add_argument('--game-sim',action='store_true',help='ARM ELF ile Godot 3B sürüşü aç; fiziksel kart kullanılmaz')
    modes.add_argument('--game-2d',action='store_true',help='Mevcut QML trafik görünümünü gerçek kartla aç')
    modes.add_argument('--game-2d-sim',action='store_true',help='Mevcut QML trafik görünümünü ARM simülasyonuyla aç')
    args=p.parse_args()
    sys.exit(main(auto_connect=args.connect or args.adas or args.adas_sim or args.game or args.game_sim or args.game_2d or args.game_2d_sim,
                  auto_adas=args.adas or args.adas_sim,arm_sim=args.adas_sim or args.game_sim or args.game_2d_sim,
                  auto_game3d=args.game or args.game_sim))
