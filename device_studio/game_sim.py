"""Three-lane traffic plant and driver input. ADAS decisions stay in C firmware.

Coordinates are metres along the road and lane-width units laterally. Every
acknowledged sample advances exactly 50 ms; serial stalls never extrapolate an
old actuator command. A deterministic seed replays the same traffic schedule.
"""
from collections import deque
from dataclasses import dataclass
import binascii
import random
import threading
import time

from .protocol import ProtocolError

MODES = {'active': 0, 'warn': 1, 'off': 2}
MODE_NAMES = {0: 'active', 1: 'warn', 2: 'off'}


@dataclass(frozen=True)
class GameConfig:
    mode: str = 'active'
    acc: bool = False
    target_kmh: int = 90
    headway_ms: int = 1800
    seed: int = 42
    duration: int = 120

    def __post_init__(self):
        if self.mode not in MODES or not 0 <= self.target_kmh <= 216 or not 800 <= self.headway_ms <= 4000:
            raise ValueError('Geçersiz oyun ayarı')
        if not 1 <= self.seed <= 999999 or not 5 <= self.duration <= 600:
            raise ValueError('Geçersiz yol veya süre')

    def command(self):
        return f'G:{MODES[self.mode]}:{int(self.acc and self.mode == "active")}:{round(self.target_kmh / .036)}:{self.headway_ms}'


class DriverInput:
    """Physical aliases retain independent ownership; auto-repeat never steers."""
    allowed = {'w', 'up', 's', 'down', 'a', 'left', 'd', 'right'}

    def __init__(self):
        self._lock = threading.Lock()
        self._held = set()
        self._lanes = deque(maxlen=4)

    def key(self, key, pressed, repeat=False):
        if key not in self.allowed or repeat:
            return
        with self._lock:
            if pressed:
                if key not in self._held and key in ('a', 'left', 'd', 'right'):
                    self._lanes.append(-1 if key in ('a', 'left') else 1)
                self._held.add(key)
            else:
                self._held.discard(key)

    def sample(self):
        with self._lock:
            lane = self._lanes.popleft() if self._lanes else 0
            return dict(gas=bool(self._held & {'w', 'up'}), brake=bool(self._held & {'s', 'down'}), lane=lane)

    def release(self):
        with self._lock:
            self._held.clear()
            self._lanes.clear()


@dataclass
class TrafficCar:
    identity: int
    lane: float
    z: float
    speed: float
    braking: bool = False
    target_lane: float = -1


class TrafficWorld:
    dt = .05
    car_length = 4.6

    def __init__(self, config):
        self.config = config
        self.rng = random.Random(config.seed)
        self.tick = 0
        self.ego = 50 / 3.6
        self.distance = 0.
        self.lane = 1.
        self.target_lane = 1
        self.collision = False
        self.acceleration = 0.
        self.cars = [TrafficCar(1, 1., 65., 55 / 3.6),
                     TrafficCar(2, 0., 38., 65 / 3.6),
                     TrafficCar(3, 2., 100., 48 / 3.6),
                     TrafficCar(4, 2., 170., 70 / 3.6)]
        self.next_id = 5
        self.next_spawn = 6000
        self.cutin_started = False
        self.warnings = 0
        self.interventions = 0
        self.near_misses = set()
        self._warning = False
        self._aeb = False
        self._warning_at = None
        self.reactions = []
        self.hard_brakes = 0

    @property
    def seconds(self):
        return self.tick / 1000

    @property
    def finished(self):
        return self.collision or self.seconds >= self.config.duration

    @property
    def score(self):
        return max(0, round(self.distance * 2) - len(self.near_misses) * 50 - int(self.collision) * 500 - self.hard_brakes * 5)

    def steer(self, delta):
        self.target_lane = max(0, min(2, self.target_lane + delta))

    def front(self):
        moving = abs(self.lane - self.target_lane) > .01
        candidates = [car for car in self.cars if car.z >= self.distance and
                      (abs(car.lane - self.lane) < .56 or moving and abs(car.lane - self.target_lane) < .56)]
        if not candidates:
            return None, 1000.
        car = min(candidates, key=lambda item: item.z)
        return car, max(0., car.z - self.distance - self.car_length)

    def command(self, pedals):
        car, gap = self.front()
        acc = self.config.acc and self.config.mode == 'active' and not pedals['gas'] and not pedals['brake']
        flags = int(car is not None) | int(acc) * 2 | 8
        body = f'T:{self.tick}:{round(self.ego*100)}:{round(car.speed*100) if car else 0}:{round(min(1000,gap)*100)}:{flags}'
        command = body + ':' + str(binascii.crc_hqx(body.encode('ascii'), 0xffff))
        if len(command) > 39:
            raise ProtocolError('Oyun ölçümü komut sınırını aştı')
        return command

    def advance(self, control, pedals):
        if self.finished:
            return
        a = control.get('a')
        if type(a) is not int or not -850 <= a <= 200:
            raise ProtocolError('Geçersiz ADAS kontrol cevabı')
        warning = bool(control.get('warn')) and self.config.mode != 'off'
        aeb = self.config.mode == 'active' and control.get('mode') == 'AEB'
        if warning and not self._warning:
            self.warnings += 1
            self._warning_at = self.tick
        if aeb and not self._aeb:
            self.interventions += 1
        if pedals['brake'] and self._warning_at is not None:
            self.reactions.append(self.tick - self._warning_at)
            self._warning_at = None
        self._warning, self._aeb = warning, aeb
        manual = -8. if pedals['brake'] else 2.8 if pedals['gas'] else -.35
        if self.config.mode == 'active' and self.config.acc and not pedals['gas'] and not pedals['brake']:
            manual = a / 100
        applied = min(manual, a / 100) if aeb else manual
        if applied < -5 and self.acceleration >= -5:
            self.hard_brakes += 1
        self.acceleration = applied
        old_distance, old_lane, old_speed = self.distance, self.lane, self.ego
        self.ego = max(0., min(200 / 3.6, self.ego + applied * self.dt))
        self.distance += (old_speed + self.ego) * .5 * self.dt
        step = 2.4 * self.dt
        self.lane += max(-step, min(step, self.target_lane - self.lane))
        if self.tick >= 10000 and not self.cutin_started:
            self.cutin_started = True
            # The event is scheduled in road time, not spawned on top of player.
            car = next((c for c in self.cars if c.identity == 3), None)
            if car and car.z - self.distance > 15:
                car.target_lane = 1.
        for car in self.cars:
            old_z, previous_lane = car.z, car.lane
            car.braking = car.identity == 1 and 3000 <= self.tick < 7000 and car.speed > 2.
            if car.braking:
                car.speed = max(2., car.speed - 6 * self.dt)
            car.z += car.speed * self.dt
            if car.target_lane >= 0:
                car.lane += max(-.6 * self.dt, min(.6 * self.dt, car.target_lane - car.lane))
            # Swept checks catch a car crossing during a step, including lateral
            # entry. Four substeps are much smaller than a vehicle footprint.
            for fraction in (.25, .5, .75, 1.):
                ego_z = old_distance + (self.distance - old_distance) * fraction
                ego_lane = old_lane + (self.lane - old_lane) * fraction
                z = old_z + (car.z - old_z) * fraction
                lane = previous_lane + (car.lane - previous_lane) * fraction
                if abs(z - ego_z) < self.car_length and abs(lane - ego_lane) < .52:
                    self.collision = True
            gap = car.z - self.distance - self.car_length
            if not self.collision and 0 < gap < 8 and abs(car.lane - self.lane) < .56:
                self.near_misses.add(car.identity)
        self.tick += 50
        self.cars = [car for car in self.cars if car.z - self.distance > -45]
        if self.tick >= self.next_spawn and len(self.cars) < 12:
            self.next_spawn += 6000
            lane = self.rng.randrange(3)
            z = self.distance + self.rng.uniform(145, 210)
            if all(abs(car.z - z) > 30 or abs(car.lane - lane) > .6 for car in self.cars):
                self.cars.append(TrafficCar(self.next_id, float(lane), z, self.rng.uniform(45, 85) / 3.6))
                self.next_id += 1

    def snapshot(self, control):
        car, gap = self.front()
        return dict(elapsed=self.seconds, remaining=max(0., self.config.duration - self.seconds),
                    distance=self.distance, egoKmh=self.ego * 3.6, egoLane=self.lane, targetLane=self.target_lane,
                    accelMps2=self.acceleration, gap=gap if car else -1., ttc=float(control.get('ttc', -1)) / 1000 if self.config.mode != 'off' and control.get('ttc', -1) >= 0 else -1.,
                    warning=bool(control.get('warn')) and self.config.mode != 'off',
                    aeb=control.get('mode') == 'AEB' and self.config.mode == 'active',
                    traffic=[dict(id=c.identity, lane=c.lane, relativeZ=c.z - self.distance,
                                  speedKmh=c.speed * 3.6, braking=c.braking) for c in sorted(self.cars, key=lambda c: abs(c.z-self.distance))[:12]],
                    score=self.score, collisions=int(self.collision), nearMisses=len(self.near_misses),
                    warnings=self.warnings, interventions=self.interventions,
                    reactionMs=round(sum(self.reactions) / len(self.reactions)) if self.reactions else -1.)


class GameRunner:
    def __init__(self, device, config, inputs, stop, emit, world=None, *, configure=True):
        self.device, self.config, self.inputs, self.stop, self.emit = device, config, inputs, stop, emit
        self.world = world or TrafficWorld(config)
        self.configure = configure
        self.rows = deque(maxlen=12000)
        self.last_response = None
        self.overruns = 0

    def run(self):
        current = self.device.current or {}
        if current.get('app') != 'ADASLab' or current.get('version', 0) < 2:
            raise ProtocolError('Trafik oyunu için ADASLab v2 firmware’i gerekli.')
        try:
            self.device.runtime('RESET')
            # A watch-owned session has already read its exact configuration
            # via J. RESET preserves that panel; do not quantize/rewrite its
            # centimetres/second target through the rounded HUD km/h value.
            if self.configure:
                configured = self.device.runtime(self.config.command())
                if configured.get('state', {}).get('error'):
                    raise ProtocolError('Kart oyun ayarlarını kabul etmedi.')
            self.device.runtime('H:1')
            while not self.stop.is_set() and not self.world.finished:
                started = time.monotonic()
                pedals = self.inputs.sample()
                self.world.steer(pedals['lane'])
                response = self.device.runtime(self.world.command(pedals), timeout=.6)
                self.last_response = response
                control = response.get('state', {})
                if response.get('app') != 'ADASLab' or response.get('id') != 3 or control.get('error') or control.get('ms') != self.world.tick:
                    raise ProtocolError('Oyun ölçüm cevabı doğrulanamadı: ' + str(control))
                if not control.get('grun'):
                    self.emit(dict(response=response, game=self.world.snapshot(control), status='paused', cardPause=True))
                    break
                if not control.get('fresh') or control.get('gmode') != MODES[self.config.mode]:
                    raise ProtocolError('Kart modu veya ölçüm zamanı değişti; oyun duraklatıldı.')
                rtt = (time.monotonic() - started) * 1000
                if rtt > 50:
                    self.overruns += 1
                self.world.advance(control, pedals)
                status = 'collision' if self.world.collision else 'finished' if self.world.finished else 'running'
                snapshot = self.world.snapshot(control)
                snapshot.update(rttMs=round(rtt, 2), overruns=self.overruns)
                self.rows.append(dict(sim_s=self.world.seconds, mode=self.config.mode, seed=self.config.seed,
                    ego_kmh=self.world.ego*3.6, lane=self.world.lane, gap_m=snapshot['gap'],
                    accel_mps2=self.world.acceleration, warning=snapshot['warning'], aeb=snapshot['aeb'],
                    score=self.world.score, rtt_ms=round(rtt, 2)))
                self.emit(dict(response=response, game=snapshot, status=status))
                if self.stop.wait(max(0., self.world.dt-(time.monotonic()-started))):
                    break
            return self.last_response
        finally:
            self.inputs.release()
            try:
                self.device.runtime('H:0', timeout=.5)
                self.device.runtime('PAUSE', timeout=.5)
            except Exception:
                pass
