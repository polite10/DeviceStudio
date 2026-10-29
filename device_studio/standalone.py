"""Launch the independent release game without loading Qt or opening serial."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
INSTALLED=Path.home()/'Applications/ADASLab Drive.app'
APP=INSTALLED if INSTALLED.is_dir() else ROOT/'dist/ADASLab Drive.app'
def launch():
    if sys.platform!='darwin' or not APP.is_dir():
        raise RuntimeError('ADASLab Drive.app bulunamadı. Önce .venv/bin/python tools/build_standalone.py çalıştırın.')
    subprocess.run(['open',str(APP)],check=True)
    return 0
