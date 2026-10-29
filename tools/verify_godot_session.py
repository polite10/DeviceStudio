"""Run the real Godot client/input handlers against Studio and ADASLab firmware.

Defaults to headless Godot and compiled ARM simulation. --visible renders a real
window; --backend hardware requires an already-installed v2 board and never
programs Flash. Run the project's Godot import before this verifier.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QCoreApplication
from device_studio.qt_controller import StudioController
from device_studio.godot_bridge import GodotBridge,find_godot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visible',action='store_true')
    parser.add_argument('--backend',choices=('arm','hardware'),default='arm')
    parser.add_argument('--port')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/godot-session-qa')
    args=parser.parse_args()
    if args.backend=='hardware' and not args.port:parser.error('--port is required with --backend hardware')
    executable=find_godot(ROOT)
    if executable is None:raise SystemExit('Godot executable not found; install it or set GODOT_BIN')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.output_dir=args.output_dir.resolve()
    report_path=args.output_dir/'godot-input-report.json'
    report_path.unlink(missing_ok=True)
    log_path=args.output_dir/'godot.log'
    app=QCoreApplication.instance() or QCoreApplication(['godot-session-qa'])
    controller=StudioController(arm_sim=args.backend=='arm',start_timers=False)
    controller.setWindowActive(False)  # Only the external game's focus may start a run.
    process=None;log_stream=None;responses=[];checks=[];native={}
    report=dict(scope='Real Godot process/TCP/input handlers and Studio UART owner; synthetic key events',
                backend='ARM_SIM' if args.backend=='arm' else 'STM32_UART',visible=args.visible)
    def check(condition,description):
        assert condition,description
        checks.append(description);print('PASS: '+description,flush=True)
    def pump_until(predicate,description,timeout=8):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            time.sleep(.003)
        raise AssertionError(description+'; '+controller.state['statusMessage'])
    try:
        if args.port:
            index=next((i for i,p in enumerate(controller.state['ports']) if p['device']==args.port),None)
            if index is None:raise RuntimeError('Requested VCP port not found: '+args.port)
            controller.selectPort(index)
        controller.connectDevice()
        pump_until(lambda:not controller.state['busy'],'Firmware connection timed out',20)
        check(controller.gameState['ready'],'ADASLab v2 is connected before launching Godot')
        device=controller._device
        original_runtime=device.runtime
        def record_runtime(command,**kwargs):
            response=original_runtime(command,**kwargs)
            if command.startswith('T:'):
                state=response.get('state',{})
                responses.append(dict(gmode=state.get('gmode'),a=state.get('a'),warn=state.get('warn'),mode=state.get('mode')))
            return response
        device.runtime=record_runtime
        bridge=GodotBridge()
        controller._game3d_bridge=bridge
        controller._game3d_phase='running'
        log_stream=log_path.open('wb')
        command=[str(executable)]
        if not args.visible:command.append('--headless')
        command+=['--path',str(ROOT/'godot/adas_drive'),'--','--bridge-port',str(bridge.port),
                  '--bridge-token',bridge.token,'--qa','--qa-report',str(report_path)]
        if args.visible:command+=['--qa-capture',str(args.output_dir/'godot-live.png')]
        process=subprocess.Popen(command,cwd=ROOT,stdout=log_stream,stderr=subprocess.STDOUT)
        controller._game3d_process=process
        # _drain's Qt timer polls transport and applies every input on the GUI
        # thread. Its dedicated worker remains the sole firmware owner.
        pump_until(lambda:process.poll() is not None,'Godot QA process did not finish',65)
        pump_until(lambda:controller._worker is None,'Renderer exit did not cancel the firmware worker',8)
        app.processEvents()
        check(report_path.is_file(),'Real Godot QA script produced its report')
        native=json.loads(report_path.read_text())
        check(process.returncode==0 and native.get('passed'), 'Godot key/UI checks passed: '+str(native.get('error','')))
        check(not controller.gameState['running'] and not controller.gameState['renderer3dConnected'],
              'Closing Godot pauses the authoritative world and disconnects its renderer')
        keys=controller._game_inputs.sample()
        check(not keys['gas'] and not keys['brake'] and keys['lane']==0,'Renderer close clears all pedals and queued steering')
        final=device.current['state']
        check(final['a']==0 and not final['grun'],'Renderer close ends with zero actuator output and MCU pause')
        check(any(r['gmode']==0 and r['mode']=='AEB' and r['a']==-850 for r in responses),
              'Actual compiled/physical ARM controller requested emergency braking during Godot driving')
        for mode in (1,2):
            samples=[r for r in responses if r['gmode']==mode]
            check(bool(samples) and all(r['a']==0 for r in samples),'Mode '+str(mode)+' sends no automatic actuator command')
        check(any(r['gmode']==1 and r['warn'] for r in responses),'Warning-only controller output contains real risk warnings')
        check(all(not r['warn'] for r in responses if r['gmode']==2),'Off controller output suppresses warnings')
        log_stream.flush()
        output=log_path.read_text(errors='replace')
        errors=[line for line in output.splitlines() if re.search(r'(^|\s)(SCRIPT ERROR:|ERROR:|Parse Error:)',line)]
        check(not errors,'Godot emitted no script/parse/runtime errors: '+str(errors[:3]))
        report.update(passed=True,checks=checks,checks_passed=len(checks),native=native,
                      firmware_samples=len(responses),log=str(log_path.relative_to(ROOT)) if log_path.is_relative_to(ROOT) else str(log_path))
    except Exception as exc:
        report.update(passed=False,error=str(exc),checks=checks,native=native)
        raise
    finally:
        controller.pauseGame()
        controller.closeGame3D()
        pump_until(lambda:controller._worker is None,'Final controller cleanup timed out',8)
        controller.requestClose()
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
        if log_stream:log_stream.close()
        (args.output_dir/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,python_checks=len(checks),godot_checks=native.get('checks_passed'),backend=report['backend'])),flush=True)


if __name__=='__main__':main()
