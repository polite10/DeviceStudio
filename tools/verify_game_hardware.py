"""Exercise already-installed ADASLab v2 via UART; never programs Flash.

Real MCU/GPU counters are checked. Keyboard/finger actions are covered separately
by Qt/ARM tests; this tool supplies deterministic driver inputs to the game plant.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from device_studio.connection import Device
from device_studio.game_sim import GameConfig,TrafficWorld


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--output',type=Path,default=ROOT/'build/game-hardware-report.json')
    args=p.parse_args()
    report=dict(scope='Physical STM32 UART/controller/GPU; simulated traffic and driver inputs',checks=[],scenarios=[])
    def check(ok,name):
        assert ok,name
        report['checks'].append(name);print('PASS: '+name,flush=True)
    d=Device(args.port)
    try:
        hello=d.detect()
        check((hello['app'],hello['id'],hello['version'],hello['boot_version'])==('ADASLab',3,2,2),
              'Physical ADASLab v2 runs under DeviceBoot v2')
        for mode in ('active','warn','off'):
            cfg=GameConfig(mode=mode,seed=42,duration=12)
            world=TrafficWorld(cfg);d.runtime('RESET');d.runtime(cfg.command());d.runtime('H:1')
            times=[];initial=None;latest={};no_actuation=True
            for _ in range(240):
                started=time.monotonic();pedals=dict(gas=True,brake=False)
                latest=d.runtime(world.command(pedals),timeout=.8)['state']
                times.append((time.monotonic()-started)*1000)
                assert not latest['error'] and latest['fresh'] and latest['ms']==world.tick
                if initial is None:initial=latest
                no_actuation &= latest['a']==0
                world.advance(latest,pedals)
                if world.finished:break
                time.sleep(max(0,.05-(time.monotonic()-started)))
            if mode=='active':check(not world.collision and world.interventions>0,'Active AEB brakes against held W and avoids defined braking traffic')
            elif mode=='warn':check(world.collision and world.warnings>0 and world.interventions==0 and no_actuation,'Warning mode alerts without applying the brake')
            else:check(world.collision and world.warnings==0 and world.interventions==0 and no_actuation,'Off mode suppresses warnings and intervention')
            check(latest['gpu']>initial['gpu'] and latest['frames']>initial['frames'],mode+': real GPU completion and LCD frame counters advance')
            row=dict(mode=mode,seconds=world.seconds,collision=world.collision,warnings=world.warnings,
                     interventions=world.interventions,rtt_mean_ms=round(statistics.mean(times),2),
                     rtt_max_ms=round(max(times),2),deadline_overruns=sum(t>50 for t in times),
                     compute_max_us=latest['us'],gpu=latest['gpu'],frames=latest['frames'])
            report['scenarios'].append(row);print(json.dumps(row),flush=True)
            paused=d.runtime('H:0')['state'];d.runtime('PAUSE')
            check(not paused['grun'] and paused['a']==0,mode+': pause clears physical controller output')
        cfg=GameConfig(mode='active',acc=True,duration=12)
        world=TrafficWorld(cfg);world.cars=[];start_speed=world.ego
        d.runtime('RESET');d.runtime(cfg.command());d.runtime('H:1')
        no_pedals=dict(gas=False,brake=False)
        for _ in range(60):
            started=time.monotonic();state=d.runtime(world.command(no_pedals))['state'];world.advance(state,no_pedals)
            time.sleep(max(0,.05-(time.monotonic()-started)))
        check(world.ego>start_speed and state['a']>0,'Physical ACC accelerates toward target with no pedals pressed')
        cmd=world.command(no_pedals);accepted=d.runtime(cmd)['state']
        check(d.runtime(cmd)['state']['error']=='invalid_sample','Physical controller rejects duplicate timestamps')
        corrupted=cmd[:-1]+('0' if cmd[-1]!='0' else '1')
        check(d.runtime(corrupted)['state']['error']=='sample_crc','Physical controller rejects damaged sample CRC')
        time.sleep(.65);stale=d.runtime('J')['state']
        check(stale['mode']=='NO_DATA' and stale['a']==0 and not stale['fresh'],'Physical controller clears output when data stops')
        d.runtime('H:0');d.runtime('PAUSE');d.runtime('G:0:0:2500:1800');d.runtime('J')
        report.update(passed=True,checks_passed=len(report['checks']))
    except Exception as exc:
        report.update(passed=False,error=str(exc));raise
    finally:
        try:d.runtime('H:0');d.runtime('PAUSE')
        except Exception:pass
        d.close();args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(str(report['checks_passed'])+' physical game checks passed.',flush=True)


if __name__=='__main__':main()
