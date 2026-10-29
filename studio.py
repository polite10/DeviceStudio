from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'.deps'))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--connect',action='store_true',help='Seçili kartın seri portuna bağlan')
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--adas',action='store_true',help=argparse.SUPPRESS)
    modes.add_argument('--adas-sim',action='store_true',help=argparse.SUPPRESS)
    modes.add_argument('--game',action='store_true',help='Studio içindeki 3B sürüş görünümünü aç; başlatma saatten yapılır')
    modes.add_argument('--game-sim',action='store_true',help='Studio içindeki 3B sürüşü ARM ELF ile aç; fiziksel kart kullanılmaz')
    modes.add_argument('--game-2d',action='store_true',help=argparse.SUPPRESS)
    modes.add_argument('--game-2d-sim',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    from device_studio.qt_app import main
    sys.exit(main(auto_connect=True,
                  auto_adas=False,arm_sim=args.adas_sim or args.game_sim or args.game_2d_sim,
                  auto_game3d=False))
