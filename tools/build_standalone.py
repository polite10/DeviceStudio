"""Build the self-contained macOS release game; Studio/Python are not runtime dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='4.7.2'
APP=ROOT/'dist/ADASLab Drive.app'
SDK_TAG='godot-4.5-stable'

def run(args,**kwargs):subprocess.run(list(map(str,args)),check=True,cwd=ROOT,**kwargs)

def templates():
    target=ROOT/'.tools/godot-release/macos.zip'
    if target.is_file():return target
    folder=ROOT/'build/godot-release-templates';folder.mkdir(parents=True,exist_ok=True)
    name=f'Godot_v{VERSION}-stable_export_templates.tpz'
    base=f'https://github.com/godotengine/godot/releases/download/{VERSION}-stable/'
    archive=folder/'export_templates.tpz';sums=folder/'SHA512-SUMS.txt'
    def get(url,path):
        request=urllib.request.Request(url,headers={'User-Agent':'ADASLab-Release-Builder'})
        with urllib.request.urlopen(request,timeout=60) as src,path.open('wb') as out:shutil.copyfileobj(src,out)
    if not archive.is_file():get(base+name,archive)
    get(base+'SHA512-SUMS.txt',sums)
    expected=next(line.split()[0] for line in sums.read_text().splitlines() if line.split()[-1].lstrip('*')==name)
    with archive.open('rb') as source:actual=hashlib.file_digest(source,'sha512').hexdigest()
    if actual!=expected:raise RuntimeError('Official release template checksum mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        entry=next(n for n in source.namelist() if n.endswith('/macos.zip'))
        with source.open(entry) as src,target.open('wb') as out:shutil.copyfileobj(src,out)
    return target

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--skip-native',action='store_true');parser.add_argument('--install',action='store_true');args=parser.parse_args()
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise SystemExit('This verified release target is macOS Apple Silicon.')
    engine=Path(os.environ.get('GODOT_BIN',str(ROOT/'.tools/godot/Godot.app/Contents/MacOS/Godot')))
    if not engine.is_file():raise SystemExit('Install Godot first: .venv/bin/python tools/install_godot.py')
    sdk=ROOT/'.tools/godot-cpp'
    if not args.skip_native:
        if not sdk.is_dir():run(['git','clone','--depth','1','--branch',SDK_TAG,'https://github.com/godotengine/godot-cpp.git',sdk])
        run([sys.executable,'-m','SCons','-C','native/serial','platform=macos','arch=arm64','target=template_release','build_profile=build_profile.json','-j8'])
    native=ROOT/'godot/adas_drive/native/libadas_serial.macos.template_release.arm64.dylib'
    if not native.is_file():raise SystemExit('Native USB extension was not built.')
    run(['install_name_tool','-id','@rpath/'+native.name,native])
    run(['codesign','--force','--sign','-',native])
    template=templates();project=ROOT/'godot/adas_drive'
    quote=lambda value:json.dumps(str(value),ensure_ascii=False)
    preset='''[preset.0]
name="macOS Release"
platform="macOS"
runnable=true
export_filter="all_resources"
include_filter="*.gdextension,*.txt,*.json"
exclude_filter=""
export_path="../../dist/ADASLab Drive.app"
script_export_mode=2

[preset.0.options]
custom_template/debug=RELEASE_TEMPLATE
custom_template/release=RELEASE_TEMPLATE
binary_format/architecture="universal"
application/bundle_identifier="dev.adaslab.drive"
application/signature="ADRV"
application/app_category="Games"
application/short_version="1.0.0"
application/version="1.0.0"
application/copyright="ADASLab contributors"
application/icon="res://icon.svg"
codesign/codesign=0
notarization/notarization=0
'''.replace('RELEASE_TEMPLATE',quote(template))
    (project/'export_presets.cfg').write_text(preset)
    APP.parent.mkdir(exist_ok=True)
    # Re-export only the bundle produced by this tool, preserving other outputs.
    if APP.is_dir():shutil.rmtree(APP)
    run([engine,'--headless','--editor','--path',project,'--import','--quit'])
    run([engine,'--headless','--path',project,'--export-release','macOS Release',APP])
    import plistlib
    info=plistlib.loads((APP/'Contents/Info.plist').read_bytes())
    executable=APP/'Contents/MacOS'/info['CFBundleExecutable']
    thin=executable.with_suffix('.arm64')
    run(['lipo',executable,'-thin','arm64','-output',thin])
    thin.chmod(executable.stat().st_mode);thin.replace(executable)
    info['LSMultipleInstancesProhibited']=True
    (APP/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    licenses=APP/'Contents/Resources/Licenses'
    licenses.mkdir(exist_ok=True)
    for source in (ROOT/'godot/adas_drive/native').glob('LICENSE.*.txt'):shutil.copyfile(source,licenses/source.name)
    shutil.copyfile(ROOT/'godot/adas_drive/assets/ATTRIBUTION.md',licenses/'Vehicle-assets.md')
    run(['codesign','--force','--deep','--sign','-',APP])
    run(['codesign','--verify','--deep','--strict',APP])
    print('Release application: '+str(APP),flush=True)
    if args.install:
        installed=Path.home()/'Applications/ADASLab Drive.app'
        if installed.exists():
            old=plistlib.loads((installed/'Contents/Info.plist').read_bytes())
            if old.get('CFBundleIdentifier')!='dev.adaslab.drive':raise RuntimeError('An unrelated application uses the same installation path.')
        installed.parent.mkdir(exist_ok=True)
        run(['ditto',APP,installed])
        run(['codesign','--verify','--deep','--strict',installed])
        print('Installed application: '+str(installed),flush=True)

if __name__=='__main__':main()
