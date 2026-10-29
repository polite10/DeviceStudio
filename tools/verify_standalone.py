"""Verify the exported game as an independent process, then inspect the watch.

Runtime is the .app only. Python/pyserial here are test tools, not bundled game
services. Watch operations use existing firmware APIs; no Flash is programmed.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',type=Path,default=ROOT/'dist/ADASLab Drive.app')
    p.add_argument('--port',required=True)
    p.add_argument('--headless',action='store_true')
    p.add_argument('--output-dir',type=Path,default=ROOT/'build/standalone-verification')
    args=p.parse_args();app=args.app.resolve();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    info=plistlib.loads((app/'Contents/Info.plist').read_bytes());exe=app/'Contents/MacOS'/info['CFBundleExecutable']
    native=out/'native.json';native.unlink(missing_ok=True)
    command=[str(exe)]
    if args.headless:command+=['--headless']
    command+=['--','--qa','--native-port',args.port,'--qa-report',str(native)]
    if not args.headless:command+=['--qa-capture',str(out/'drive.png')]
    env=os.environ.copy();env['PATH']='/usr/bin:/bin'
    for name in ('GODOT_BIN','PYTHONPATH','VIRTUAL_ENV'):env.pop(name,None)
    with (out/'application.log').open('wb') as log:
        process=subprocess.Popen(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,env=env)
        try:code=process.wait(timeout=80)
        except subprocess.TimeoutExpired:
            process.terminate();process.wait(timeout=5);raise
    result=json.loads(native.read_text())
    assert code==0 and result['passed'],result
    assert result['debug_build'] is False,'Development template was launched'
    assert result['direct_uart'] and result['backend']=='DIRECT_UART','Game was not independent'
    text=(out/'application.log').read_text(errors='replace')
    assert not re.search(r'(^|\n)(ERROR:|SCRIPT ERROR:)',text),text
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    from device_studio.connection import Device
    d=Device(args.port)
    try:
        identity=d.detect();state=d.runtime('J')['state']
        assert identity['app']=='ADASLab' and identity['version']==2
        assert state['a']==0 and not state['grun'],'Game exit left controller running'
    finally:d.close()
    report=dict(passed=True,application=str(app),bundle_id=info['CFBundleIdentifier'],version=info.get('CFBundleShortVersionString'),
                native=result,release_template=True,independent_working_directory=True,signature_verified=True,
                mcu_paused_after_exit=True,firmware_unchanged=True,scope='Real release process/native USB/watch controller; synthetic engine input events')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,native_checks=result['count'],debug_build=result['debug_build'],independent=True)),flush=True)

if __name__=='__main__':main()
