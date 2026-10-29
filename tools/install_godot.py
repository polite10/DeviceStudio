"""Install a verified official Godot binary locally; never changes system tools."""
import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='4.7.2'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default=VERSION)
    args=parser.parse_args()
    system=platform.system();machine=platform.machine().lower()
    if system=='Darwin':
        suffix='macos.universal.zip';relative='Godot.app/Contents/MacOS/Godot'
    elif system=='Windows' and machine in ('amd64','x86_64'):
        suffix='win64.exe.zip';relative=f'Godot_v{args.version}-stable_win64.exe'
    elif system=='Linux' and machine in ('amd64','x86_64'):
        suffix='linux.x86_64.zip';relative=f'Godot_v{args.version}-stable_linux.x86_64'
    else:
        raise SystemExit('Bu platformda resmi Godot 4 indirmesini açıp GODOT_BIN yolunu ayarlayın.')
    dest=ROOT/'.tools/godot';executable=dest/relative
    if executable.is_file():
        current=subprocess.check_output([str(executable),'--version'],text=True,timeout=15).strip()
        if current.startswith(args.version+'.'):
            print('Godot hazır: '+str(executable));return
    filename=f'Godot_v{args.version}-stable_{suffix}'
    base=f'https://github.com/godotengine/godot/releases/download/{args.version}-stable/'
    def download(url,target):
        request=urllib.request.Request(url,headers={'User-Agent':'DeviceStudio-Godot-Setup'})
        with urllib.request.urlopen(request,timeout=60) as src,target.open('wb') as out:
            shutil.copyfileobj(src,out)
    with tempfile.TemporaryDirectory(prefix='studio-godot-') as temp:
        folder=Path(temp);archive=folder/filename;checksums=folder/'SHA512-SUMS.txt'
        print('Resmi Godot indiriliyor: '+filename,flush=True)
        download(base+filename,archive);download(base+'SHA512-SUMS.txt',checksums)
        expected=next((line.split()[0] for line in checksums.read_text().splitlines() if line.split()[-1].lstrip('*')==filename),None)
        if not expected or hashlib.sha512(archive.read_bytes()).hexdigest()!=expected:
            raise SystemExit('Godot SHA512 doğrulaması başarısız; kurulum yapılmadı.')
        dest.mkdir(parents=True,exist_ok=True)
        if system=='Darwin':
            subprocess.run(['ditto','-x','-k',str(archive),str(dest)],check=True)
        else:
            with zipfile.ZipFile(archive) as source:
                for member in source.infolist():
                    if not (dest/member.filename).resolve().is_relative_to(dest.resolve()):
                        raise SystemExit('Güvensiz arşiv yolu; kurulum durduruldu.')
                source.extractall(dest)
            if system=='Linux':executable.chmod(executable.stat().st_mode|stat.S_IXUSR)
    subprocess.run([str(executable),'--version'],check=True)
    print('Godot hazır: '+str(executable))


if __name__=='__main__':main()
