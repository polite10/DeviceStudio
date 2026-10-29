"""Install a verified official Blender locally for the asset tools; never changes system tools."""
import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '5.2.3'
DEST = ROOT / '.tools/blender'


def executable(version=VERSION):
    """Path of the locally installed Blender for this platform."""
    system = platform.system()
    if system == 'Darwin':
        return DEST / 'Blender.app/Contents/MacOS/Blender'
    if system == 'Windows':
        return DEST / f'blender-{version}-windows-x64/blender.exe'
    return DEST / f'blender-{version}-linux-x64/blender'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=VERSION)
    args = parser.parse_args()
    system, machine = platform.system(), platform.machine().lower()
    if system == 'Darwin' and machine == 'arm64':
        filename = f'blender-{args.version}-macos-arm64.dmg'
    elif system == 'Windows' and machine in ('amd64', 'x86_64'):
        filename = f'blender-{args.version}-windows-x64.zip'
    elif system == 'Linux' and machine in ('amd64', 'x86_64'):
        filename = f'blender-{args.version}-linux-x64.tar.xz'
    else:
        raise SystemExit('Bu platformda resmi Blender indirmesini açıp BLENDER_BIN yolunu ayarlayın.')
    target = executable(args.version)
    if target.is_file():
        print('Blender hazır: ' + str(target))
        return
    series = '.'.join(args.version.split('.')[:2])
    base = f'https://download.blender.org/release/Blender{series}/'

    def download(url, path):
        request = urllib.request.Request(url, headers={'User-Agent': 'DeviceStudio-Blender-Setup'})
        with urllib.request.urlopen(request, timeout=60) as source, path.open('wb') as out:
            shutil.copyfileobj(source, out)

    with tempfile.TemporaryDirectory(prefix='studio-blender-') as temp:
        folder = Path(temp)
        archive, checksums = folder / filename, folder / f'blender-{args.version}.sha256'
        print('Resmi Blender indiriliyor: ' + filename, flush=True)
        download(base + filename, archive)
        download(base + checksums.name, checksums)
        expected = next((line.split()[0] for line in checksums.read_text().splitlines()
                         if line.split() and line.split()[-1].lstrip('*') == filename), None)
        digest = hashlib.sha256()
        with archive.open('rb') as data:
            for chunk in iter(lambda: data.read(1 << 20), b''):
                digest.update(chunk)
        if not expected or digest.hexdigest() != expected:
            raise SystemExit('Blender SHA256 doğrulaması başarısız; kurulum yapılmadı.')
        DEST.mkdir(parents=True, exist_ok=True)
        if system == 'Darwin':
            mount = folder / 'mount'
            mount.mkdir()
            subprocess.run(['hdiutil', 'attach', '-nobrowse', '-readonly', '-mountpoint', str(mount), str(archive)],
                           check=True, stdout=subprocess.DEVNULL)
            try:
                subprocess.run(['ditto', str(mount / 'Blender.app'), str(DEST / 'Blender.app')], check=True)
            finally:
                subprocess.run(['hdiutil', 'detach', str(mount)], check=False, stdout=subprocess.DEVNULL)
        elif system == 'Windows':
            with zipfile.ZipFile(archive) as source:
                for member in source.infolist():
                    if not (DEST / member.filename).resolve().is_relative_to(DEST.resolve()):
                        raise SystemExit('Güvensiz arşiv yolu; kurulum durduruldu.')
                source.extractall(DEST)
        else:
            with tarfile.open(archive) as source:
                source.extractall(DEST, filter='data')
    subprocess.run([str(target), '--version'], check=True)
    print('Blender hazır: ' + str(target))


if __name__ == '__main__':
    main()
