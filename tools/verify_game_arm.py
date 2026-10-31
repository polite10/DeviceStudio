"""Run traffic physics against the actual ARM game controller, without a board.

Default uses ../ADASLab/build/ADASLab.elf. --elf selects a staged build. This is
closed-loop algorithm/protocol verification; GPU and physical touch aren't emulated.
"""
import argparse
import json
from pathlib import Path
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from device_studio.adas_arm import ArmDevice
from device_studio.game_sim import GameConfig,TrafficWorld,TrafficCar,DriverInput,GameRunner,MODES


class CheckedArm(ArmDevice):
    def __init__(self,elf_path=None):
        self.max_command=0;self.max_reply=0
        super().__init__(elf_path)
    def runtime(self,command,**kwargs):
        self.max_command=max(self.max_command,len(command))
        assert len(command)<=39,'Game command exceeds bounded runtime parser'
        response=super().runtime(command,**kwargs)
        length=self.u.reg_read(self.regs[0])
        assert 0<length<512,'Actual ARM wire reply exceeds DMA buffer'
        # Parse the exact emitted bytes independently of ArmDevice's JSON copy.
        assert json.loads(bytes(self.u.mem_read(0x20260100,length)))['seq']==response['seq']
        self.max_reply=max(self.max_reply,length)
        return response


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--elf',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'build/game-arm-policy-report.json')
    args=parser.parse_args();checks=[];scenarios=[];limits=[0,0]
    def check(ok,message):
        assert ok,message
        checks.append(message);print('PASS: '+message,flush=True)
    def device():
        d=CheckedArm(args.elf)
        assert d.current.get('version',0)>=2,'Build ADASLab game firmware v2 first'
        return d
    def finish(d):
        limits[0]=max(limits[0],d.max_command);limits[1]=max(limits[1],d.max_reply)
        d.close()
    # No steering or driver braking: all cases hold W and use the same seeded
    # traffic. Active assistance must override the accelerator in an emergency.
    for road in ('scheduled-brake','constant-slow-target'):
        rows={}
        for mode in MODES:
            d=device();config=GameConfig(mode=mode,duration=25,seed=42)
            world=TrafficWorld(config)
            if road=='constant-slow-target':world.cars=[TrafficCar(9,1.,45.,10.)]
            d.runtime('RESET');d.runtime(config.command());d.runtime(config.calibration());d.runtime('H:1')
            minimum=1000.;brake_override=False;no_assist=True
            try:
                for _ in range(500):
                    pedals=dict(gas=True,brake=False)
                    response=d.runtime(world.command(pedals));state=response['state']
                    assert not state['error'] and state['fresh'] and state['grun']
                    assert state['ms']==world.tick and state['gmode']==MODES[mode]
                    old_speed=world.ego;world.advance(state,pedals)
                    if state['mode']=='AEB' and world.ego<old_speed and world.acceleration<0:brake_override=True
                    no_assist &= state['a']==0
                    minimum=min(minimum,world.front()[1])
                    if world.finished:break
                row=dict(road=road,mode=mode,seconds=world.seconds,collision=world.collision,
                         minimum_gap_m=round(minimum,3),warnings=world.warnings,
                         interventions=world.interventions,brake_overrides_gas=brake_override)
                scenarios.append(row);rows[mode]=row;print(json.dumps(row),flush=True)
                if mode=='active':
                    check(brake_override and world.interventions>0,road+': ARM AEB overrides held accelerator')
                    check(not world.collision,road+': active mode avoids collision in this defined test')
                elif mode=='warn':
                    check(world.warnings>0 and world.interventions==0 and no_assist,road+': warning-only alerts with no actuator output')
                    check(world.collision,road+': ignoring warning permits collision')
                else:
                    check(world.warnings==0 and world.interventions==0 and no_assist,road+': off suppresses alerts and actuator output')
                    check(world.collision,road+': unassisted held accelerator permits collision')
                d.runtime('H:0');d.runtime('PAUSE')
            finally:finish(d)
        check(rows['warn']['seconds']==rows['off']['seconds'],road+': warning/off physics match for the same player inputs')
    # Pause/resume resets the controller sample clock but preserves road state.
    d=device();config=GameConfig(duration=25);world=TrafficWorld(config)
    try:
        def chunk(count,world):
            inputs=DriverInput();inputs.key('w',True);stop=threading.Event();snapshots=[]
            def emit(value):
                snapshots.append(value)
                if len(snapshots)>=count:stop.set()
            runner=GameRunner(d,config,inputs,stop,emit,world=world);runner.run()
            return snapshots,runner
        first,runner=chunk(4,world);paused_tick=world.tick;paused_distance=world.distance
        check(paused_tick==200 and d.current['state']['a']==0 and not d.current['state']['grun'],'Runner pause clears card output and stops at acknowledged step')
        second,_=chunk(3,world)
        check(second[0]['response']['state']['ms']==paused_tick and world.tick==350 and world.distance>paused_distance,
              'Resume retains road/traffic and accepts nonzero first timestamp after RESET')
        # Exercise the exact function called by physical LVGL button callbacks.
        old=d.runtime('J')['state'];d.call('adas_game_touch',1);selected=d.runtime('J')['state']
        check(selected['gmode']==1 and selected['grev']!=old['grev'],'Card warning-mode touch action is returned through J')
        d.call('adas_game_touch',6);started=d.runtime('J')['state']
        check(started['grun'],'Card START request is visible to the host')
        check(d.call('adas_game_touch',2)==0 and d.runtime('J')['state']['gmode']==1,'Card mode selection is locked during a run')
        d.call('adas_game_touch',6);check(not d.runtime('J')['state']['grun'],'Card PAUSE request is visible to the host')
        d.runtime('RESET');d.runtime('G:0:1:6000:4000');d.runtime('H:1');d.sequence=2147483646
        import binascii
        body='T:4294967295:6000:6000:100000:15'
        maximum=body+':'+str(binascii.crc_hqx(body.encode(),0xffff))
        check(d.runtime(maximum)['state']['ms']==4294967295,'Maximum sample fields and sequence fit the real ARM parser/formatter')
    finally:finish(d)
    check(limits[0]<=39 and limits[1]<512,'All game command/reply sizes respect existing UART buffers')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report=dict(scope='Actual compiled ARM control + deterministic desktop traffic; no physical board or GPU emulation',
                passed=len(checks),failed=0,command_max_chars=limits[0],reply_max_bytes=limits[1],
                scenarios=scenarios,checks=checks)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(checks)} closed-loop game ARM checks passed; max command {limits[0]} chars, reply {limits[1]} bytes.',flush=True)


if __name__=='__main__':main()
