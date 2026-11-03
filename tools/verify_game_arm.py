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
from device_studio.game_sim import GameConfig,LANE,TrafficWorld,TrafficCar,DriverInput,GameRunner,MODES


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
        assert d.current.get('version',0)>=3,'Build ADASLab game firmware v3 first'
        return d
    def finish(d):
        limits[0]=max(limits[0],d.max_command);limits[1]=max(limits[1],d.max_reply)
        d.close()
    # No steering or driver braking: all cases hold W and use the same seeded
    # traffic. Active assistance must override the accelerator in an emergency.
    for road in ('scheduled-brake','constant-slow-target'):
        rows={}
        for mode in MODES:
            d=device();config=GameConfig(mode=mode,duration=25,seed=42,surprises=False)
            world=TrafficWorld(config);world.next_chaser=10**9
            if road=='constant-slow-target':world.cars=[TrafficCar(9,1.,45.,10.)]
            d.runtime('RESET');d.runtime(config.command());d.runtime(config.calibration());d.runtime(config.geometry());d.runtime('H:1')
            minimum=1000.;brake_override=False;no_assist=True
            try:
                for _ in range(500):
                    pedals=dict(gas=True,brake=False)
                    d.runtime(world.surround_command(pedals))
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
    def drive(config,setup,steps,pedals=lambda world,step:dict(gas=False,brake=False)):
        """A defined road against the real controller; yields each step's state."""
        d=device();world=TrafficWorld(config)
        world.cars,world.next_spawn,world.next_chaser,world.next_ease,world.next_surprise=[],10**9,10**9,10**9,10**9
        setup(world)
        rows=[]
        try:
            d.runtime('RESET');d.runtime(config.command());d.runtime(config.calibration());d.runtime(config.geometry());d.runtime('H:1')
            for step in range(steps):
                now=pedals(world,step)
                assert not d.runtime(world.surround_command(now))['state']['error']
                state=d.runtime(world.command(now))['state']
                assert not state['error'] and state['fresh'] and state['ms']==world.tick
                world.advance(state,now);rows.append(dict(state))
                if world.finished:break
            return world,rows
        finally:finish(d)
    def steering(direction,gas=False):return dict(gas=gas,brake=False,steer=direction)
    def report_row(name,world,rows):
        row=dict(road=name,seconds=world.seconds,lane=round(world.lane,3),speed_kmh=round(world.ego*3.6,1),collision=world.collision,
                 assists=world.assists,assist_bits=sorted({r['as'] for r in rows}))
        scenarios.append(row);print(json.dumps(row),flush=True)
    def fast(world):world.ego=90/3.6
    # Lane keeping: released it comes back, held on it lets go, signalled it stays out.
    active=GameConfig(mode='active',duration=60,vehicle='model3',surprises=False)
    world,rows=drive(active,fast,200,lambda world,step:steering(1 if step<14 else 0))
    edges=[(r['st'],r['as']) for r in rows]
    check(any(st<0 and bits&1 for st,bits in edges),'Hands off after a push toward the line: lane keeping steers back')
    check(not any(r['as']&32 for r in rows) and world.target_lane==1,'A short push never crosses: the car stays in its lane')
    check(max(rows[i]['st'] for i in range(len(rows)))<=0 and abs(world.x)<(LANE-world.spec.width)/2,'The car ends inside the lane with the wheel quiet')
    report_row('lane-keep-return',world,rows)
    world,rows=drive(active,fast,140,lambda world,step:steering(1))
    resisted=[i for i,r in enumerate(rows) if r['as']&1]
    took=next(i for i,r in enumerate(rows) if r['as']&32)
    check(resisted and 15<=took-resisted[0]<=25,'Holding the wheel against it: it resists for a second, then lets go: '+str(took-resisted[0]))
    check(world.lane>1.5,'Held on, the car changes lanes without a signal: '+str(round(world.lane,3)))
    report_row('lane-keep-override',world,rows)
    world,rows=drive(active,fast,260,lambda world,step:steering(1 if step<46 else 0))
    check(any(r['as']&32 for r in rows) and any(r['as']&1 for r in rows[46:]),'Released on the line after an override: it steers again')
    check(abs(world.lane-round(world.lane))<(LANE-world.spec.width)/2/LANE and not rows[-1]['as'],'and the car settles inside the nearest lane: '+str(round(world.lane,3)))
    report_row('lane-keep-release-on-line',world,rows)
    def signalled(world):
        fast(world);world.indicate(1)
    world,rows=drive(active,signalled,120,lambda world,step:steering(1 if world.signal else 0))
    check(not any(r['as']&1 for r in rows[:30]) and world.signal==0 and world.target_lane==2,'With the indicator on: a lane change without resistance, the stalk cancels on arrival')
    report_row('signalled-change',world,rows)
    warn=GameConfig(mode='warn',duration=60,vehicle='model3',surprises=False)
    world,rows=drive(warn,fast,120,lambda world,step:steering(1))
    check(any(r['as']&64 for r in rows) and world.assists==0 and not any(r['st'] for r in rows) and world.lane>1.5,'Warning-only warns at the line and never steers')
    off=GameConfig(mode='off',duration=60,vehicle='model3',surprises=False)
    world,rows=drive(off,fast,120,lambda world,step:steering(1))
    check(not any(r['as'] or r['st'] or r['bl'] or r['br'] or r['rr'] for r in rows) and world.lane>1.5,'Off mode leaves the wheel alone')
    # Blind spot: a car overtakes on the right; indicating toward it is refused.
    def overtaker(world):
        fast(world);world.cars=[TrafficCar(5,2.,-28.,29.,desired=29.)]
    world,rows=drive(active,overtaker,180)
    lit=[i for i,r in enumerate(rows) if r['br']]
    check(lit and rows[lit[0]]['br']==1 and not any(r['st'] for r in rows),'An overtaker lights the blind spot lamp and nothing moves')
    report_row('overtaker',world,rows)
    def alongside(world):
        fast(world);world.cars=[TrafficCar(5,2.,-3.,25.,desired=25.)];world.indicate(1)
    world,rows=drive(active,alongside,120,lambda world,step:steering(1))
    check(any(r['br']==2 for r in rows) and any(r['st']<0 and r['as']&2 for r in rows),'Indicating and steering at a car in the blind spot: red lamp and counter-steering')
    check(not world.collision,'The car in the blind spot is not hit: '+str(round(world.lane,3)))
    report_row('blind-spot-block',world,rows)
    alone=GameConfig(mode='off',duration=60,vehicle='model3',surprises=False)
    world,rows=drive(alone,alongside,120,lambda world,step:steering(1))
    check(world.collision,'Without ADAS the same steering hits it')
    # A car cutting into the flank without looking.
    def cutter(world):
        fast(world)
        car=TrafficCar(5,2.,.5,25.,desired=25.,changes=True,careless=True,signal_lead=.2,change_time=2.2)
        world.cars=[car];world._start_change(car,1)
    def holding(world,step):return dict(gas=world.ego<25,brake=False)
    world,rows=drive(active,cutter,120,holding)
    check(any(r['as']&2 for r in rows) and any(r['st']<0 for r in rows),'A careless cut-in at the flank: the card steers away')
    check(not world.collision,'and no contact in this defined test')
    report_row('flank-cut-in',world,rows)
    world,rows=drive(off,cutter,120,holding)
    check(world.collision,'Without ADAS the same cut-in hits the car')
    # A distracted driver from behind.
    def tailgater(world):
        fast(world);world.cars=[TrafficCar(5,1.,-55.,40.,desired=40.,distracted=.6,comfort=3.)]
    tesla=GameConfig(mode='active',duration=60,vehicle='model3',surprises=False)
    world,rows=drive(tesla,tailgater,160)
    check(any(r['rr']==1 for r in rows) and any(r['rr']==2 for r in rows),'A fast follower raises the rear warning, then the threat')
    check(any(r['as']&4 and r['a']>200 for r in rows),'The card floors the accelerator, past the ACC limit')
    check(not world.collision,'and the Model 3 gets away in this defined test')
    report_row('rear-escape-model3',world,rows)
    world,rows=drive(GameConfig(mode='active',duration=60,vehicle='sahin',surprises=False),tailgater,160)
    check(any(r['as']&16 for r in rows) and abs(world.lane-1)>.5,'The Şahin cannot outrun it: under 1.2 s the card leaves the lane')
    check(not world.collision,'and the Şahin avoids it in this defined test')
    report_row('rear-evade-sahin',world,rows)
    world,rows=drive(GameConfig(mode='off',duration=60,vehicle='sahin',surprises=False),tailgater,160)
    check(world.collision,'Without ADAS the same driver hits the car')
    def blocked(world):
        fast(world);world.cars=[TrafficCar(5,1.,-55.,40.,desired=40.,distracted=.6,comfort=3.),TrafficCar(6,1.,22.,25.,desired=25.)]
    world,rows=drive(tesla,blocked,60)
    check(not any(r['as']&4 for r in rows[:30]) or world.front()[1]>5,'A car close ahead keeps the escape from accelerating into it')
    report_row('rear-with-car-ahead',world,rows)
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
        check(not d.runtime(TrafficWorld(config).surround_command(dict(gas=False,brake=False)))['state']['error'],'Sensor samples fit the real ARM parser')
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
