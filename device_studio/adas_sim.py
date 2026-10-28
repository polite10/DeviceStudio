"""Deterministic longitudinal plant; all controller decisions come from the MCU.

No desktop copy of the ADAS controller is used. SI units in this module;
centimetre integer units on the bounded runtime wire protocol.
"""
from collections import deque
from dataclasses import dataclass
import binascii
import random
import time
from .protocol import ProtocolError

SCENARIOS={'brake':'Ani fren','follow':'Yavaş araç','cutin':'Önümüze giren araç','cruise':'Sabit takip','dropout':'Veri kesintisi'}

@dataclass(frozen=True)
class Config:
    scenario:str='brake'
    target_kmh:int=90
    headway_ms:int=1800
    acc:bool=True
    aeb:bool=True
    noise:bool=False
    repeat:bool=True

class World:
    dt=.05
    def __init__(self,config):
        if config.scenario not in SCENARIOS:raise ValueError('Bilinmeyen senaryo')
        if not 0<=config.target_kmh<=200 or not 800<=config.headway_ms<=4000:raise ValueError('Geçersiz deney ayarı')
        self.config=config;self.tick=0;self.ego=config.target_kmh/3.6
        self.lead=self.ego if config.scenario!='follow' else 60/3.6
        self.gap=70.;self.present=config.scenario!='cutin';self.collision=False
        self.random=random.Random(42)
    @property
    def seconds(self):return self.tick/1000
    def command(self):
        gap=self.gap+(self.random.uniform(-.5,.5) if self.config.noise else 0)
        flags=int(self.present)|int(self.config.acc)*2|int(self.config.aeb)*4|8
        body=f'S:{self.tick}:{round(self.ego*100)}:{round(self.lead*100)}:{round(max(0,min(1000,gap))*100)}:{flags}'
        return body+':'+str(binascii.crc_hqx(body.encode('ascii'),0xffff))
    def advance(self,acceleration):
        if not -8.5<=acceleration<=2:raise ProtocolError('Firmware ivme isteği sınır dışında')
        dt=self.dt;t=self.seconds
        lead_a=-6. if self.config.scenario in ('brake','dropout') and t>=3 and self.lead>0 else 0.
        old_ego=self.ego;old_lead=self.lead
        self.ego=max(0.,self.ego+acceleration*dt);self.lead=max(0.,self.lead+lead_a*dt)
        if self.present:self.gap+=((old_lead+self.lead)-(old_ego+self.ego))*.5*dt
        self.tick+=50
        if self.config.scenario=='cutin' and not self.present and self.seconds>=3:
            self.present=True;self.lead=45/3.6;self.gap=35.
        if self.present and self.gap<=0:self.gap=0.;self.collision=True

class Runner:
    """Own Device exclusively until run() ends; Tk reads only immutable snapshots."""
    def __init__(self,device,config,stop,emit):
        self.device=device;self.config=config;self.stop=stop;self.emit=emit
        self.rows=deque(maxlen=12000);self.overruns=0;self.cycle=0
    def run(self):
        if not self.device.current or self.device.current.get('app')!='ADASLab':
            raise ProtocolError('Önce ADASLab firmware’ine bağlanın')
        latest=None
        try:
            while not self.stop.is_set():
                world=World(self.config);self.cycle+=1;drop_done=False
                self.device.runtime('RESET')
                self.device.runtime(f'C:{round(self.config.target_kmh/3.6*100)}:{self.config.headway_ms}')
                while not self.stop.is_set() and world.seconds<25:
                    if self.config.scenario=='dropout' and world.seconds>=3 and not drop_done:
                        drop_done=True
                        if self.stop.wait(.75):break
                        latest=self.device.runtime('STATUS',timeout=.5)
                        if latest.get('state',{}).get('fresh') is not False:
                            raise ProtocolError('Veri eskime koruması çalışmadı')
                        self.emit({'response':latest,'seconds':world.seconds,'gap':world.gap,'rtt_ms':0,'cycle':self.cycle,'overruns':self.overruns,'collision':False,'data_pause':True})
                        if self.stop.wait(.5):break
                    started=time.monotonic()
                    latest=self.device.runtime(world.command(),timeout=.6)
                    rtt=(time.monotonic()-started)*1000
                    state=latest.get('state',{})
                    if latest.get('app')!='ADASLab' or latest.get('id')!=3 or state.get('error') or state.get('ms')!=world.tick or not state.get('fresh'):
                        raise ProtocolError('ADASLab ölçüm/cevap kimliği uyuşmuyor: '+str(state))
                    acceleration=state.get('a')
                    if type(acceleration) is not int or not -850<=acceleration<=200:raise ProtocolError('Geçersiz kontrol cevabı')
                    if rtt>50:self.overruns+=1
                    row=dict(cycle=self.cycle,sim_s=world.seconds,ego_kmh=world.ego*3.6,lead_kmh=world.lead*3.6,
                             gap_m=world.gap,accel_mps2=acceleration/100,ttc_ms=state.get('ttc'),
                             mode=state.get('mode'),rtt_ms=round(rtt,2),gpu=state.get('gpu'),frames=state.get('frames'))
                    self.rows.append(row)
                    self.emit({'response':latest,'seconds':world.seconds,'gap':world.gap,'rtt_ms':rtt,
                               'cycle':self.cycle,'overruns':self.overruns,'collision':world.collision,'data_pause':False})
                    world.advance(acceleration/100)
                    if world.collision:
                        self.emit({'response':latest,'seconds':world.seconds,'gap':0.,'rtt_ms':rtt,
                                   'cycle':self.cycle,'overruns':self.overruns,'collision':True,'data_pause':False})
                        return latest
                    # Fixed simulated steps; missed wall-clock deadlines slow the experiment.
                    # No catch-up burst and no unacknowledged stale acceleration extrapolation.
                    if self.stop.wait(max(0,world.dt-(time.monotonic()-started))):break
                if not self.config.repeat:break
            return latest
        finally:
            try:self.device.runtime('PAUSE',timeout=.5)
            except Exception:pass
