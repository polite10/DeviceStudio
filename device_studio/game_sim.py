"""Three-lane traffic plant and driver input. ADAS decisions stay in C firmware.

Every acknowledged sample advances exactly 50 ms; serial stalls never
extrapolate an old actuator command, and a deterministic seed replays the same
traffic. Positions are metres: z along the road at each vehicle's centre, x
across it in 3.6 m lanes (lane 0 is the left, overtaking lane; traffic keeps
right), altitude of the underbody above the road.

The physics follows published vehicle data and standard models:
- longitudinal: tyre, torque and power limits, aerodynamic drag, rolling
  resistance, regenerative or engine braking, gear shifts, pedal travel and
  actuator lag (VehicleSpec);
- lateral: minimum-jerk (quintic) lane changes whose length keeps the lateral
  acceleration and heading to what a brisk driver uses, sharper when evading;
- traffic: Intelligent Driver Model car following and MOBIL lane changes
  (Treiber & Kesting) with indicators; the player is a car like any other;
- flight (Taklacı Güvercin): cold compressed-air thrusters, as revealed for the
  2028 Roadster; the tank empties at thrust / exhaust velocity and refills on
  the road.
"""
from collections import deque
from dataclasses import dataclass
import binascii
import math
import random
import threading
import time

from .protocol import ProtocolError

MODES = {'active': 0, 'warn': 1, 'off': 2}
MODE_NAMES = {0: 'active', 1: 'warn', 2: 'off'}
DT = .05
G = 9.81
RHO = 1.225                     # kg/m³, sea-level air at 15 °C
LANE = 3.6                      # m
# The T: sample carries at most 6000 cm/s: every car is governed below 216 km/h.
MAX_SPEED = 59.9
# Flight layers of flying cars in metres: the road, under the gantries, above them.
LAYERS = (0., 4., 9.)

# A keyboard pedal is floored in 0.25 s and released in 0.17 s; the brake
# reaches full service pressure in 0.25 s, then the hydraulics lag 0.12 s.
THROTTLE_RATE = (4., 6.)
BRAKE_RATE = (4., 6.)
BRAKE_LAG = .12
# Lane changes: naturalistic ones take 4-6 s at ~1 m/s²; a brisk driver keeps
# under 2.8 m/s², an evasive swerve uses 60 % of the tyre grip.
LATERAL_BRISK = 2.8
EVASIVE_GRIP = .6
MAX_HEADING = math.radians(25)
# UN R13-H: regenerative braking above 1.3 m/s² lights the stop lamps.
STOP_LAMP_DECEL = 1.3

# Intelligent Driver Model and MOBIL (traffic-simulation.de reference values).
MIN_GAP = 2.                    # jam distance s0, m
MAX_BRAKE = 9.                  # emergency braking on dry asphalt, m/s²
TRAFFIC_LAG = .25               # s
SAFE_BRAKE = 4.                 # never force a follower to brake harder, m/s²
CHANGE_THRESHOLD = .15          # advantage needed to change lanes, m/s²
KEEP_RIGHT = .25                # bias toward the right lane: overtake on the left
LANE_SPEEDS = (105., 90., 75.)  # mean desired km/h, left to right lane
MAX_CARS = 12

# Taklacı Güvercin: 600 L carbon tank of air at 700 bar, 15 °C (≈585 kg/m³),
# expanded cold through the nozzles (exhaust ≈640 m/s, Isp ≈65 s).
AIR_FULL = 350.
EXHAUST = 640.
LIFT_MAX = 2.                   # lift thrust / full-tank weight, eight nozzles
HORIZONTAL_THRUST = .4          # × weight from the rear (W) or nose (S) nozzles in the air
# Game scale for short test drives: the tank lasts 5.25 times longer than the
# thrust / exhaust velocity physics gives (about 50 s of hover instead of 10 s)
# and the road compressor refills it at 17.5 kg/s (a real one would need about
# half an hour for a full tank). Budgets below are in game kilograms.
AIR_ECONOMY = 5.25
AIR_REFILL = 17.5
CLIMB, SINK, LAYER_ACCEL = 4., 5., 4.
CLIMB_MARGIN = 60. / AIR_ECONOMY  # kg above the landing reserve to start climbing
LANDING_MARGIN = 15. / AIR_ECONOMY  # kg above the reserve where the descent starts
HOP_TIME, AIR_CHANGE_TIME = 2.2, 2.4  # s for a lane: road takla, sideways in the air
HOP_HEIGHT, HOP_SHARE = .75, .5       # m apex, share of the lane change off the road
ROAD_ROLL, AIR_ROLL = .4, .6          # share of the lane change spent rolling
HOP_AIR = 70. / AIR_ECONOMY     # kg a road takla burns (lift arc and side push)
HARD_LANDING = 4.5              # m/s touchdown that wrecks the car


@dataclass(frozen=True)
class VehicleSpec:
    """Published size and performance. Mass includes a 75 kg driver."""
    name: str
    length: float
    width: float
    height: float
    mass: float
    cda: float                  # drag coefficient × frontal area, m²
    rolling: float              # rolling resistance coefficient
    grip: float                 # tyre friction (with fan downforce on the Roadster)
    brake: float                # full service braking, m/s²
    drive_force: float = 0.     # electric drive: traction/torque limit, N
    power: float = 0.           # electric drive power at the wheels, W
    top_speed: float = MAX_SPEED
    regen_force: float = 0.     # one-pedal regenerative braking ceiling, N
    regen_power: float = 0.     # W
    lag: float = .05            # torque response time constant, s
    # Manual gearbox: overall ratios (gear × final drive), engine torque curve
    # as (rpm, N·m) points, dynamic tyre radius and driveline efficiency.
    gears: tuple = ()
    torque: tuple = ()
    wheel_radius: float = .3
    efficiency: float = .9
    flight: bool = False


VEHICLES = {
    # Tofaş Şahin 1.6: 4316×1642×1437 mm, ~1035 kg, 59 kW (80 PS) at 5500 rpm,
    # 126 N·m at 3250 rpm, five-speed manual, rear drive, rear drums, no ABS.
    'sahin': VehicleSpec('Tofaş Şahin', 4.316, 1.642, 1.437, 1110., cda=.78, rolling=.013, grip=.85, brake=7.4,
                         lag=.25, gears=(14.33, 8.21, 5.32, 3.909, 3.444),
                         torque=((800, 88), (2000, 112), (3250, 126), (4500, 118), (5500, 103), (6300, 84)),
                         wheel_radius=.283),
    # Tesla Model 3 Long Range AWD (2024): 4720×1850×1441 mm, 1830 kg, Cd 0.22,
    # 0-100 km/h in 4.4 s, governed at 201 km/h, ~10 m/s² braking.
    'model3': VehicleSpec('Tesla Model 3', 4.72, 1.85, 1.441, 1905., cda=.49, rolling=.009, grip=1., brake=10.,
                          drive_force=12500., power=310e3, top_speed=201 / 3.6, regen_force=3400., regen_power=60e3),
    # Roadster "Rocket" trim as revealed on 2026-10-15: fans pull it onto the road
    # (over 2 g cornering), 0-60 mph under 1.6 s on its tyres alone, lift and roll
    # thrusters on compressed air refilled while driving. The mass is an estimate.
    'roadster': VehicleSpec('Tesla Taklacı Güvercin', 4.566, 1.98, 1.129, 2025., cda=.44, rolling=.01, grip=2.,
                            brake=15., drive_force=47000., power=1e6, regen_force=5000., regen_power=120e3, lag=.04,
                            flight=True),
}


@dataclass(frozen=True)
class Kind:
    length: float
    width: float
    height: float
    accel: float                # IDM acceleration of an average driver, m/s²
    share: int                  # % of the traffic mix


# Turkish motorway mix; sizes of the class leaders named.
TRAFFIC = {
    'hatch': Kind(4.05, 1.76, 1.46, 1.4, 26),   # Renault Clio, Hyundai i20
    'sedan': Kind(4.55, 1.80, 1.47, 1.5, 34),   # Fiat Egea, Toyota Corolla
    'suv': Kind(4.50, 1.86, 1.66, 1.3, 18),     # Togg T10X, Hyundai Tucson
    'van': Kind(4.40, 1.85, 1.85, 1.1, 10),     # Fiat Doblo, Ford Courier
    'taxi': Kind(4.55, 1.80, 1.62, 1.7, 6),     # yellow sedan with a roof sign
    'sahin': Kind(4.316, 1.642, 1.437, 1., 3),
    'model3': Kind(4.72, 1.85, 1.441, 2., 3),
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _toward(value, target, rates):
    step = (rates[0] if target > value else rates[1]) * DT
    return value + _clamp(target - value, -step, step)


def _smoothstep(u):
    u = _clamp(u, 0., 1.)
    return u * u * (3 - 2 * u)


def _curve(points, x):
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def idm(car, leader, gap):
    """Intelligent Driver Model acceleration (Treiber, Hennecke & Helbing 2000)."""
    v = car.speed
    if car.desired > .1:
        free = max(-car.comfort, car.accel_max * (1 - (v / car.desired) ** 4))
    else:
        free = -car.comfort if v > .05 else 0.
    if leader is None:
        return free
    dynamic = v * car.headway + v * (v - leader.speed) / (2 * math.sqrt(car.accel_max * car.comfort))
    wanted = MIN_GAP + max(0., dynamic)
    return free - car.accel_max * (wanted / max(gap, .1)) ** 2


class LaneChange:
    """Minimum-jerk (quintic) lateral path over road distance or time.

    It starts from the current offset, slope and curvature, so changing one's
    mind mid-manoeuvre stays smooth, and ends level on the new lane centre.
    """

    def __init__(self, x0, slope, curve, x1, length):
        L = max(length, 1e-3)
        h = x1 - x0 - slope * L - curve / 2 * L * L
        v = -slope - curve * L
        w = -curve
        self.c = (x0, slope, curve / 2, (20 * h - 8 * v * L + w * L * L) / (2 * L ** 3),
                  (-30 * h + 14 * v * L - 2 * w * L * L) / (2 * L ** 4), (12 * h - 6 * v * L + w * L * L) / (2 * L ** 5))
        self.length, self.end = L, x1

    def at(self, s):
        if s >= self.length:
            return self.end, 0., 0.
        c0, c1, c2, c3, c4, c5 = self.c
        return (c0 + s * (c1 + s * (c2 + s * (c3 + s * (c4 + s * c5)))),
                c1 + s * (2 * c2 + s * (3 * c3 + s * (4 * c4 + s * 5 * c5))),
                2 * c2 + s * (6 * c3 + s * (12 * c4 + s * 20 * c5)))


@dataclass(frozen=True)
class GameConfig:
    mode: str = 'active'
    acc: bool = False
    target_kmh: int = 90
    headway_ms: int = 1800
    seed: int = 42
    duration: int = 120
    # The player's car; the Taklacı Güvercin flies on R/F and rolls between lanes.
    vehicle: str = 'sahin'

    def __post_init__(self):
        if self.mode not in MODES or not 0 <= self.target_kmh <= 216 or not 800 <= self.headway_ms <= 4000:
            raise ValueError('Geçersiz oyun ayarı')
        if not 1 <= self.seed <= 999999 or not 5 <= self.duration <= 600 or self.vehicle not in VEHICLES:
            raise ValueError('Geçersiz yol, süre veya araç')

    @property
    def flight(self):
        return VEHICLES[self.vehicle].flight

    def command(self):
        return f'G:{MODES[self.mode]}:{int(self.acc and self.mode == "active")}:{round(self.target_kmh / .036)}:{self.headway_ms}'

    def calibration(self):
        """The card's AEB calibration: 95 % of the car's full braking, cm/s²."""
        return f'V:{min(1600, round(VEHICLES[self.vehicle].brake * 95))}'


class DriverInput:
    """Physical aliases retain independent ownership; auto-repeat never steers or climbs."""
    allowed = {'w', 'up', 's', 'down', 'space', 'a', 'left', 'd', 'right', 'r', 'f'}

    def __init__(self):
        self._lock = threading.Lock()
        self._held = set()
        self._lanes = deque(maxlen=4)
        self._layers = deque(maxlen=4)

    def key(self, key, pressed, repeat=False):
        if key not in self.allowed or repeat:
            return
        with self._lock:
            if pressed:
                if key not in self._held and key in ('a', 'left', 'd', 'right'):
                    self._lanes.append(-1 if key in ('a', 'left') else 1)
                if key not in self._held and key in ('r', 'f'):
                    self._layers.append(1 if key == 'r' else -1)
                self._held.add(key)
            else:
                self._held.discard(key)

    def sample(self):
        with self._lock:
            lane = self._lanes.popleft() if self._lanes else 0
            layer = self._layers.popleft() if self._layers else 0
            return dict(gas=bool(self._held & {'w', 'up'}), brake=bool(self._held & {'s', 'down', 'space'}), lane=lane, layer=layer)

    def release(self):
        with self._lock:
            self._held.clear()
            self._lanes.clear()
            self._layers.clear()


@dataclass
class TrafficCar:
    identity: int
    lane: float                 # lateral position in lanes, 0 = left lane
    z: float                    # centre along the road, m
    speed: float                # m/s
    kind: str = 'sedan'
    desired: float = -1.        # m/s; negative keeps the starting speed
    headway: float = 1.4        # IDM desired time gap, s
    accel_max: float = 1.5      # IDM acceleration, m/s²
    comfort: float = 2.         # IDM comfortable deceleration, m/s²
    politeness: float = .3      # MOBIL politeness
    changes: bool = False       # decides its own lane changes (MOBIL)
    change_time: float = 4.     # s to cross one lane
    signal_lead: float = 1.5    # s of indicator before steering; 0 never signals
    accel: float = 0.
    command: float = 0.
    braking: bool = False
    signal: int = 0
    target_lane: int = -1
    lane_rate: float = 0.
    path: LaneChange = None
    path_s: float = 0.
    steer_at: int = 0
    next_look: int = 0

    def __post_init__(self):
        if self.desired < 0:
            self.desired = self.speed
        if not self.next_look:
            self.next_look = 1000 + self.identity * 137 % 1000

    @property
    def size(self):
        return TRAFFIC[self.kind]

    @property
    def length(self):
        return self.size.length

    @property
    def width(self):
        return self.size.width

    @property
    def height(self):
        return self.size.height

    @property
    def x(self):
        return (self.lane - 1) * LANE


class _Ego:
    """The player's car as other drivers see it, with a typical driver's IDM."""
    identity, headway, accel_max, comfort = 0, 1.2, 2., 3.

    def __init__(self, world):
        self.z, self.x, self.speed = world.distance, world.x, world.ego
        self.length, self.width, self.height = world.spec.length, world.spec.width, world.spec.height
        self.desired = max(world.ego, 1.)


class TrafficWorld:
    dt = DT

    def __init__(self, config):
        self.config = config
        self.spec = VEHICLES[config.vehicle]
        self.rng = random.Random(config.seed)
        self.tick = 0
        self.ego = 50 / 3.6
        self.distance = 0.
        self.acceleration = 0.
        self.throttle = self.brake_pedal = 0.
        self.drive_force = self.brake_force = 0.
        # A driver at 50 km/h in the Şahin rolls in third.
        self.gear, self.next_gear, self.shifting, self.shift_wait = 2, 2, 0., 0.
        self.lane = 1.
        self.target_lane = 1
        self.path, self.path_s, self.path_time = None, 0., False
        self.lane_rate = self.lat_accel = 0.
        self.signal = 0
        self.collision = False
        self.cars = [TrafficCar(1, 1., 65., 55 / 3.6, kind='sedan', headway=1.3),          # jam tail: brakes at 3-7 s
                     TrafficCar(2, 0., 38., 65 / 3.6, kind='hatch', desired=100 / 3.6, changes=True),
                     TrafficCar(3, 2., 100., 48 / 3.6, kind='van', desired=52 / 3.6),       # cuts in at 10 s
                     TrafficCar(4, 2., 170., 70 / 3.6, kind='suv', desired=78 / 3.6, changes=True)]
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
        self.layer = 0
        self.altitude = self.climb_rate = 0.
        self.layer_ref = (0., 0.)
        self.air = AIR_FULL if self.spec.flight else 0.
        self.hop = None
        self.roll = self.lift = self.boost = self.retro = self.side = 0.
        self.auto_land = False
        self.landing_blocked = 0
        self.air_refused = 0

    @property
    def seconds(self):
        return self.tick / 1000

    @property
    def finished(self):
        return self.collision or self.seconds >= self.config.duration

    @property
    def score(self):
        return max(0, round(self.distance * 2) - len(self.near_misses) * 50 - int(self.collision) * 500 - self.hard_brakes * 5)

    @property
    def flight(self):
        return self.spec.flight

    @property
    def airborne(self):
        """Wheels off the road: no tyre forces, thrusters only."""
        return self.altitude > .02

    @property
    def mass(self):
        return self.spec.mass + self.air

    @property
    def x(self):
        return (self.lane - 1) * LANE

    @property
    def braking(self):
        return (self.brake_force > .05 * self.mass * G or self.acceleration < -STOP_LAMP_DECEL
                or self.retro > .1 or self.brake_pedal > .05)

    # Driver commands -------------------------------------------------------

    def steer(self, delta):
        target = max(0, min(2, self.target_lane + delta))
        if delta and target != self.target_lane:
            self.target_lane = target
            self._plan_lane_change()

    def _plan_lane_change(self):
        spec, v = self.spec, self.ego
        x0, x1 = self.x, (self.target_lane - 1) * LANE
        d = abs(x1 - x0)
        vy, ay = self.lane_rate * LANE, self.lat_accel
        if self.airborne and self.air <= self._reserve(self.altitude) + LANDING_MARGIN:
            self.target_lane = round(self.lane)  # the reserve is kept for landing
            return
        takla = spec.flight and (self.airborne or self.air >= self._reserve(0.) + HOP_AIR)
        if takla:
            # Thrusters carry it sideways whatever the road speed: plan in time.
            duration = (AIR_CHANGE_TIME if self.airborne else HOP_TIME) * max(.5, d / LANE) ** .5
            self.path, self.path_time = LaneChange(x0, vy, ay, x1, duration), True
            if self.hop is None and d > LANE / 2:
                self.hop = dict(start=self.tick, time=duration, sign=-1 if x1 > x0 else 1, ground=not self.airborne)
        else:
            grip = spec.grip * G * EVASIVE_GRIP
            limit = grip if self._evasive() else min(LATERAL_BRISK, grip)
            length = max(1.875 * d / math.tan(MAX_HEADING), v * math.sqrt(5.7735 * d / limit), v, 4.)
            slope, curve = (vy / v, ay / (v * v)) if v > .5 else (0., 0.)
            self.path, self.path_time = LaneChange(x0, slope, curve, x1, length), False
        self.path_s = 0.

    def _evasive(self):
        """Closing in on the car ahead: swerve with most of the grip."""
        car, gap = self._ahead([self.x])
        if car is None:
            return False
        closing = self.ego - car.speed
        return gap < .8 * self.ego or (closing > .1 and gap / closing < 3.)

    def fly(self, delta):
        """R climbs a layer; F descends, landing only where the road below is clear."""
        if not delta or not self.flight:
            return
        layer = max(0, min(len(LAYERS) - 1, self.layer + delta))
        if layer > self.layer and (self.auto_land or self.air < self._reserve(LAYERS[layer]) + CLIMB_MARGIN):
            self.air_refused = 1500
            return
        if layer == 0 and self.layer > 0 and self.landing_occupied():
            self.landing_blocked = 1500
            return
        self.layer = layer

    def landing_occupied(self):
        """A car under the landing spot now or within the next two seconds."""
        lanes = (self.x, (self.target_lane - 1) * LANE)
        for car in self.cars:
            if min(abs(car.x - x) for x in lanes) >= (car.width + self.spec.width) / 2 + .3:
                continue
            for t in (0., .5, 1., 1.5, 2.):
                if abs(car.z + car.speed * t - self.distance - self.ego * t) < (car.length + self.spec.length) / 2 + 3:
                    return True
        return False

    # Sensors ---------------------------------------------------------------

    def _ahead(self, lanes):
        best, gap = None, 1000.
        for car in self.cars:
            if car.z < self.distance or self.altitude >= car.height:
                continue
            if min(abs(car.x - x) for x in lanes) >= (car.width + self.spec.width) / 2 + .2:
                continue
            g = car.z - self.distance - (car.length + self.spec.length) / 2
            if best is None or g < gap:
                best, gap = car, g
        return best, max(0., gap)

    def front(self):
        """The in-path target: the current lane, plus the lane being entered."""
        return self._ahead([self.x] + ([(self.target_lane - 1) * LANE] if self.path else []))

    def command(self, pedals):
        car, gap = self.front()
        acc = self.config.acc and self.config.mode == 'active' and not pedals['gas'] and not pedals['brake']
        flags = int(car is not None) | int(acc) * 2 | 8
        body = f'T:{self.tick}:{round(self.ego*100)}:{round(car.speed*100) if car else 0}:{round(min(1000,gap)*100)}:{flags}'
        command = body + ':' + str(binascii.crc_hqx(body.encode('ascii'), 0xffff))
        if len(command) > 39:
            raise ProtocolError('Oyun ölçümü komut sınırını aştı')
        return command

    # Plant step ------------------------------------------------------------

    def advance(self, control, pedals):
        if self.finished:
            return
        a = control.get('a')
        if type(a) is not int or not -1600 <= a <= 200:
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
        if self.tick >= 10000 and not self.cutin_started:
            self._cut_in()
        # Everyone decides on the state at the start of the step, then moves.
        old_distance, old_x, old_altitude = self.distance, self.x, self.altitude
        before = [(car, car.z, car.x) for car in self.cars]
        bodies = self._bodies()
        for car in self.cars:
            self._decide(car, bodies)
        self._longitudinal(a / 100, aeb, pedals)
        self._lateral(self.distance - old_distance)
        if self.flight:
            self._flight()
        for car in self.cars:
            self._move(car)
        self._contacts(old_distance, old_x, old_altitude, before)
        self.tick += 50
        self._spawn()

    def _longitudinal(self, request, aeb, pedals):
        spec, v, m = self.spec, self.ego, self.mass
        gas, brake = pedals['gas'] and not pedals['brake'], pedals['brake']
        self.throttle = _toward(self.throttle, float(gas), THROTTLE_RATE)
        self.brake_pedal = _toward(self.brake_pedal, float(brake), BRAKE_RATE)
        drag = .5 * RHO * spec.cda * v * v
        if self.airborne:
            # No tyre contact: the rear (W) and nose (S) nozzles push, drag slows.
            # The landing reserve is never spent on pushing around.
            thrust = HORIZONTAL_THRUST * m * G if self.air > self._reserve(self.altitude) + LANDING_MARGIN else 0.
            self.boost = _toward(self.boost, float(gas and thrust > 0), (4., 4.))
            self.retro = _toward(self.retro, float(brake and thrust > 0), (4., 4.))
            self.drive_force = self.brake_force = 0.
            force = (self.boost - self.retro) * thrust - drag
            self._spend((self.boost + self.retro) * thrust)
        else:
            self.boost = self.retro = 0.
            resist = drag + (spec.rolling * m * G if v > .01 else 0.)
            if spec.gears:
                self._shift()
            acc = self.config.acc and self.config.mode == 'active' and not pedals['gas'] and not pedals['brake']
            if aeb:
                # Emergency braking cuts the drive torque and overrides the accelerator.
                drive, braking = 0., max(self.brake_pedal * m * spec.brake, -request * m - resist)
            elif acc:
                need, coast = request * m + resist, self._coast()
                drive = min(need, self._tractive(1.)) if need >= 0 else max(need, -coast)
                braking = max(0., -need - coast)
            else:
                drive = self._tractive(self.throttle) if self.throttle > .01 else -self._coast()
                braking = self.brake_pedal * m * spec.brake
            braking = _clamp(braking, 0., m * spec.brake)
            self.drive_force += (drive - self.drive_force) * (1 - math.exp(-DT / spec.lag))
            self.brake_force += (braking - self.brake_force) * (1 - math.exp(-DT / BRAKE_LAG))
            force = self.drive_force - self.brake_force - resist
        accel = force / m
        if v <= .01 and accel <= 0:
            new, travelled = 0., 0.
        else:
            new = v + accel * DT
            if new < 0:
                new, travelled = 0., v * v / (2 * -accel)
            else:
                travelled = (v + new) / 2 * DT
        new = min(new, MAX_SPEED)
        previous, self.acceleration = self.acceleration, (new - v) / DT
        if self.acceleration < -5 <= previous:
            self.hard_brakes += 1
        self.ego = new
        self.distance += travelled

    def _rpm(self, gear):
        return self.ego / self.spec.wheel_radius * self.spec.gears[gear] * 60 / (2 * math.pi)

    def _shift(self):
        """The Şahin's driver: up at 5900 rpm, kick down when lugging, 0.5 s per shift."""
        spec = self.spec
        if self.shifting > 0:
            self.shifting -= DT
            if self.shifting <= 0:
                self.gear = self.next_gear
            return
        if self.ego < 4:
            self.gear = 0  # clutch down, first gear selected while stopping
            return
        self.shift_wait = max(0., self.shift_wait - DT)
        if self.shift_wait > 0:
            return
        rpm, gear = self._rpm(self.gear), self.gear
        if gear + 1 < len(spec.gears) and (rpm > 5900 or (self.throttle < .5 and rpm > 4500)):
            gear += 1
        elif gear > 0 and (rpm < 1300 or (self.throttle > .9 and rpm < 3000 and self._rpm(gear - 1) < 4500)):
            gear -= 1
        if gear != self.gear:
            self.next_gear, self.shifting, self.shift_wait = gear, .5, 1.

    def _tractive(self, throttle):
        spec, v = self.spec, self.ego
        if spec.gears:
            if self.shifting > 0:
                return 0.
            rpm = self._rpm(self.gear)
            if self.gear == 0:
                rpm = max(rpm, 1200 + 1800 * throttle)  # slipping clutch
            if rpm > 6300:
                return 0.  # rev limiter
            force = throttle * _curve(spec.torque, rpm) * spec.gears[self.gear] * spec.efficiency / spec.wheel_radius
            return min(force, spec.grip * self.mass * G * .55)  # rear axle load
        force = min(spec.drive_force, spec.power / max(v, .1), spec.grip * self.mass * G)
        return throttle * force * _clamp(spec.top_speed - v, 0., 1.)

    def _coast(self):
        """Engine braking in gear, or one-pedal regeneration, with the pedals released."""
        spec, v = self.spec, self.ego
        if spec.gears:
            if self.shifting > 0 or v < 4:
                return 0.
            return (12 + .0035 * self._rpm(self.gear)) * spec.gears[self.gear] / spec.wheel_radius
        return min(spec.regen_force, spec.regen_power / max(v, .1)) * min(1., v / 3)

    def _lateral(self, travelled):
        if self.path is None:
            self.lane_rate = self.lat_accel = self.side = 0.
            self.signal = 0
            return
        self.path_s += DT if self.path_time else travelled
        x, d1, d2 = self.path.at(self.path_s)
        if self.path_time:
            vy, ay = d1, d2
        else:
            vy, ay = d1 * self.ego, d2 * self.ego * self.ego + d1 * self.acceleration
        self.lane = x / LANE + 1
        self.lane_rate, self.lat_accel = vy / LANE, ay
        self.signal = (1 if self.path.end > x else -1) if abs(self.path.end - x) > .05 else 0
        # Tyres turn a moving car; in the air or near standstill the side nozzles push.
        if self.flight and (self.airborne or self.ego < 3):
            self.side = _clamp(ay / 6, -1., 1.)
            self._spend(self.mass * abs(ay))
        else:
            self.side = 0.
        if self.path_s >= self.path.length:
            self.path = None
            self.lane = float(self.target_lane)
            self.lane_rate = self.lat_accel = self.side = 0.
            self.signal = 0

    def _spend(self, thrust):
        self.air = max(0., self.air - thrust / EXHAUST * DT / AIR_ECONOMY)

    def _reserve(self, altitude):
        """Air to land from this height: a 5 m/s descent and a powered flare."""
        return (35. + 7.5 * altitude) / AIR_ECONOMY

    def _bump(self, now):
        """Height, rate and acceleration of a road takla: a sin² arc mid-change."""
        hop = self.hop
        if not hop or not hop['ground']:
            return 0., 0., 0.
        t, T = (now - hop['start']) / 1000, hop['time']
        a, b = (1 - HOP_SHARE) / 2 * T, (1 + HOP_SHARE) / 2 * T
        if not a < t < b:
            return 0., 0., 0.
        w = math.pi / (b - a)
        u = (t - a) * w
        return HOP_HEIGHT * math.sin(u) ** 2, HOP_HEIGHT * w * math.sin(2 * u), 2 * HOP_HEIGHT * w * w * math.cos(2 * u)

    def _flight(self):
        spec, m, now = self.spec, self.mass, self.tick + 50
        # Land automatically while the reserve still covers the descent.
        reserve = self._reserve(self.altitude)
        if self.layer > 0 and self.air <= reserve + LANDING_MARGIN:
            if not self.landing_occupied() or self.air <= reserve:
                self.layer, self.auto_land = 0, True
            else:
                self.landing_blocked = 1500
        # Layer reference: rate and acceleration limited, settling without overshoot.
        target = LAYERS[self.layer]
        ref, rate = self.layer_ref
        a_ref = _clamp((_clamp(1.4 * (target - ref), -SINK, CLIMB) - rate) / .4, -LAYER_ACCEL, LAYER_ACCEL)
        rate += a_ref * DT
        ref += rate * DT
        if ref <= 0 and target == 0:
            ref = rate = a_ref = 0.
        self.layer_ref = (ref, rate)
        bump = self._bump(now)
        h_ref, v_ref, a_ff = ref + bump[0], rate + bump[1], a_ref + bump[2]
        lift_max = LIFT_MAX * (spec.mass + AIR_FULL) * G
        if (h_ref <= 0 and not self.airborne) or self.air <= 0:
            lift = 0.
        else:
            lift = _clamp(m * (G + a_ff + 25 * (h_ref - self.altitude) + 9 * (v_ref - self.climb_rate)), 0., lift_max)
        drag = .5 * RHO * spec.length * spec.width * self.climb_rate * abs(self.climb_rate)
        az = (lift - drag) / m - G
        if not self.airborne and az <= 0:
            self.altitude = self.climb_rate = 0.
        else:
            self.climb_rate += az * DT
            self.altitude += self.climb_rate * DT
            if self.altitude <= 0:
                if self.climb_rate < -HARD_LANDING:
                    self.collision = True
                self.altitude = self.climb_rate = 0.
        self.lift = lift / lift_max
        self._spend(lift)
        if self.hop:
            t, T = (now - self.hop['start']) / 1000, self.hop['time']
            share = ROAD_ROLL if self.hop['ground'] else AIR_ROLL
            self.roll = self.hop['sign'] * 360 * _smoothstep((t - (1 - share) / 2 * T) / (share * T))
            if t >= T:
                self.hop, self.roll = None, 0.
        if not self.airborne and self.layer == 0:
            self.auto_land = False
            if self.hop is None:
                self.air = min(AIR_FULL, self.air + AIR_REFILL * DT)
        self.landing_blocked = max(0, self.landing_blocked - 50)
        self.air_refused = max(0, self.air_refused - 50)

    # Traffic ---------------------------------------------------------------

    def _bodies(self):
        """What drivers react to: the traffic, and the player's car near the road."""
        return self.cars + ([_Ego(self)] if self.altitude < 2.5 else [])

    @staticmethod
    def _leader(car, bodies, lanes):
        best, gap = None, math.inf
        for other in bodies:
            if other is car or other.z <= car.z:
                continue
            if min(abs(other.x - x) for x in lanes) >= (other.width + car.width) / 2 + .5:
                continue
            g = other.z - car.z - (other.length + car.length) / 2
            if g < gap:
                best, gap = other, g
        return best, gap

    @staticmethod
    def _follower(car, bodies, x):
        best, gap = None, math.inf
        for other in bodies:
            if other is car or other.z >= car.z or abs(other.x - x) >= (other.width + car.width) / 2 + .5:
                continue
            g = car.z - other.z - (other.length + car.length) / 2
            if g < gap:
                best, gap = other, g
        return best, gap

    def _lanes(self, car):
        return [car.x] + ([(car.target_lane - 1) * LANE] if car.target_lane >= 0 else [])

    def _decide(self, car, bodies):
        leader, gap = self._leader(car, bodies, self._lanes(car))
        accel = idm(car, leader, gap)
        if car.identity == 1 and 3000 <= self.tick < 7000:
            # Scripted jam tail: a hard 6 m/s² stop down to walking pace.
            accel = min(accel, -6. if car.speed > 2 else 0.)
        car.command = _clamp(accel, -MAX_BRAKE, car.accel_max)
        if car.target_lane >= 0 and car.path is None and self.tick >= car.steer_at:
            if car.changes and not self._safe(car, bodies, (car.target_lane - 1) * LANE):
                car.target_lane, car.signal = -1, 0  # the gap closed while signalling
            else:
                car.path = LaneChange(car.x, 0., 0., (car.target_lane - 1) * LANE,
                                      max(car.speed * car.change_time, 1.875 * LANE / math.tan(MAX_HEADING)))
                car.path_s = 0.
        elif car.changes and car.target_lane < 0 and self.tick >= car.next_look:
            car.next_look = self.tick + 1000
            self._mobil(car, bodies, leader, accel)

    def _safe(self, car, bodies, x):
        front, gap_front = self._leader(car, bodies, [x])
        back, gap_back = self._follower(car, bodies, x)
        if front and gap_front < MIN_GAP + .3 * car.speed:
            return False
        return not back or (gap_back > MIN_GAP + .3 * back.speed and idm(back, car, gap_back) >= -SAFE_BRAKE)

    def _mobil(self, car, bodies, leader, accel):
        """MOBIL: change when it pays, counting the gain of the cars behind, never unsafely."""
        lane = round(car.lane)
        if abs(car.lane - lane) > .05:
            return
        old_back, old_gap = self._follower(car, bodies, car.x)
        old_gain = 0.
        if old_back:
            # Our old follower would follow our leader instead.
            new_gap = leader.z - old_back.z - (leader.length + old_back.length) / 2 if leader else math.inf
            old_gain = idm(old_back, leader, new_gap) - idm(old_back, car, old_gap)
        best = None
        for side in (-1, 1):
            target = lane + side
            if not 0 <= target <= 2:
                continue
            x = (target - 1) * LANE
            if not self._safe(car, bodies, x):
                continue
            front, gap_front = self._leader(car, bodies, [x])
            back, gap_back = self._follower(car, bodies, x)
            back_gain = 0.
            if back:
                back_leader, back_leader_gap = self._leader(back, bodies, [back.x])
                back_gain = idm(back, car, gap_back) - idm(back, back_leader, back_leader_gap)
            gain = (idm(car, front, gap_front) - accel + car.politeness * (back_gain + old_gain)
                    + (KEEP_RIGHT if side > 0 else -KEEP_RIGHT))
            if gain > CHANGE_THRESHOLD and (best is None or gain > best[0]):
                best = (gain, target)
        if best:
            self._start_change(car, best[1])

    def _start_change(self, car, lane):
        car.target_lane = lane
        car.signal = (1 if lane > car.lane else -1) if car.signal_lead > 0 else 0
        car.steer_at = self.tick + round(car.signal_lead * 20) * 50

    def _cut_in(self):
        """At 10 s the slow van in the right lane cuts into the middle lane."""
        self.cutin_started = True
        car = next((c for c in self.cars if c.identity == 3), None)
        if not car or car.z - self.distance <= 15 or car.target_lane >= 0 or abs(car.lane - 2) > .1:
            return
        if any(abs(other.z - car.z) < (other.length + car.length) / 2 + 6 and abs(other.lane - 1) < .5
               for other in self.cars if other is not car):
            return
        car.change_time, car.signal_lead = 2.5, .5
        self._start_change(car, 1)
        car.changes = True

    def _move(self, car):
        car.accel += (car.command - car.accel) * (1 - math.exp(-DT / TRAFFIC_LAG))
        speed = car.speed + car.accel * DT
        if speed < 0:
            travel = car.speed * car.speed / (2 * -car.accel) if car.accel < 0 else 0.
            speed = 0.
        else:
            travel = (car.speed + speed) / 2 * DT
        car.z += travel
        car.speed = speed
        car.braking = car.accel < -.6 or car.speed < .1
        if car.path:
            car.path_s += travel
            x, slope, _ = car.path.at(car.path_s)
            car.lane = x / LANE + 1
            car.lane_rate = slope * car.speed / LANE
            if car.path_s >= car.path.length:
                car.lane, car.path, car.target_lane, car.signal, car.lane_rate = float(car.target_lane), None, -1, 0, 0.
                car.next_look = self.tick + 4000  # settle before the next decision

    def _contacts(self, old_distance, old_x, old_altitude, before):
        spec = self.spec
        for car, old_z, old_cx in before:
            # Swept checks catch a car crossing during a step, including lateral
            # entry. Four substeps are much smaller than a vehicle footprint.
            reach, side = (car.length + spec.length) / 2, (car.width + spec.width) / 2
            for fraction in (.25, .5, .75, 1.):
                ego_z = old_distance + (self.distance - old_distance) * fraction
                ego_x = old_x + (self.x - old_x) * fraction
                altitude = old_altitude + (self.altitude - old_altitude) * fraction
                z = old_z + (car.z - old_z) * fraction
                x = old_cx + (car.x - old_cx) * fraction
                if altitude < car.height and abs(z - ego_z) < reach and abs(x - ego_x) < side:
                    self.collision = True
            gap = car.z - self.distance - reach
            if (not self.collision and self.altitude < car.height and abs(car.x - self.x) < side
                    and 0 < gap < max(3., .5 * self.ego)):
                self.near_misses.add(car.identity)

    def _kind(self):
        pick = self.rng.random() * sum(kind.share for kind in TRAFFIC.values())
        for name, kind in TRAFFIC.items():
            pick -= kind.share
            if pick < 0:
                return name
        return 'sedan'

    def _spawn(self):
        self.cars = [car for car in self.cars if -160 < car.z - self.distance < 330]
        if self.tick < self.next_spawn or len(self.cars) >= MAX_CARS:
            return
        rng = self.rng
        self.next_spawn += rng.randrange(3000, 6050, 50)
        lane, kind = rng.randrange(3), self._kind()
        desired = _clamp(rng.gauss(LANE_SPEEDS[lane], 7.), 55., 130.) / 3.6
        # Faster traffic catches up from behind a slow player.
        behind = self.ego + 2 < .9 * desired
        z = self.distance + (rng.uniform(-140., -110.) if behind else rng.uniform(170., 240.))
        x = (lane - 1) * LANE
        car = TrafficCar(self.next_id, float(lane), z, desired, kind=kind, desired=desired,
                         headway=_clamp(rng.gauss(1.4, .2), 1., 2.), accel_max=TRAFFIC[kind].accel * rng.uniform(.85, 1.15),
                         comfort=rng.uniform(1.8, 2.6), politeness=rng.uniform(.1, .5), changes=True,
                         change_time=rng.uniform(3., 5.), signal_lead=rng.uniform(1., 2.5) if rng.random() < .85 else 0.)
        # Join the lane's flow at the speed ahead, two time gaps from anyone.
        for other in self._bodies():
            if abs(other.x - x) < 2.5:
                if abs(other.z - z) < max(25., 2.5 * car.speed):
                    return
                if 0 < other.z - z < 120:
                    car.speed = min(car.speed, other.speed)
        self.cars.append(car)
        self.next_id += 1

    def snapshot(self, control):
        car, gap = self.front()
        return dict(elapsed=self.seconds, remaining=max(0., self.config.duration - self.seconds),
                    distance=self.distance, egoKmh=self.ego * 3.6, egoLane=self.lane, targetLane=self.target_lane,
                    egoLaneRate=self.lane_rate, egoLatAccel=self.lat_accel, egoSignal=self.signal,
                    egoBraking=self.braking, vehicle=self.config.vehicle, gear=self.gear + 1 if self.spec.gears else 0,
                    accelMps2=self.acceleration, gap=gap if car else -1., ttc=float(control.get('ttc', -1)) / 1000 if self.config.mode != 'off' and control.get('ttc', -1) >= 0 else -1.,
                    warning=bool(control.get('warn')) and self.config.mode != 'off',
                    aeb=control.get('mode') == 'AEB' and self.config.mode == 'active',
                    traffic=[dict(id=c.identity, kind=c.kind, lane=c.lane, laneRate=c.lane_rate, relativeZ=c.z - self.distance,
                                  speedKmh=c.speed * 3.6, braking=c.braking, signal=c.signal)
                             for c in sorted(self.cars, key=lambda c: abs(c.z - self.distance))[:MAX_CARS]],
                    flight=self.flight, layer=self.layer, altitude=self.altitude, roll=self.roll,
                    lift=self.lift, boost=self.boost, retro=self.retro, side=self.side,
                    air=self.air, airFull=AIR_FULL if self.flight else 0., autoLand=self.auto_land,
                    airLow=self.air_refused > 0, landingBlocked=self.landing_blocked > 0,
                    score=self.score, collisions=int(self.collision), nearMisses=len(self.near_misses),
                    warnings=self.warnings, interventions=self.interventions,
                    reactionMs=round(sum(self.reactions) / len(self.reactions)) if self.reactions else -1.)


# The flier's launch before a new drive: up the ramp (Drive3DView draws it), then a
# moment stopped on the ceiling. The plant starts when it lets go.
LAUNCH_SECONDS = 4.6


class GameRunner:
    def __init__(self, device, config, inputs, stop, emit, world=None, *, configure=True):
        self.device, self.config, self.inputs, self.stop, self.emit = device, config, inputs, stop, emit
        self.world = world or TrafficWorld(config)
        self.configure = configure
        self.launch = LAUNCH_SECONDS if self.world.flight and not self.world.tick else 0.
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
            # The car's braking sets when AEB must act; firmware before it keeps 8.5 m/s².
            calibrated = self.device.runtime(self.config.calibration()).get('state', {}).get('error')
            if calibrated and calibrated != 'unsupported_command':
                raise ProtocolError('Kart araç fren ayarını kabul etmedi.')
            self.device.runtime('H:1')
            if not self._climb():
                return self.last_response
            while not self.stop.is_set() and not self.world.finished:
                started = time.monotonic()
                pedals = self.inputs.sample()
                self.world.steer(pedals['lane'])
                self.world.fly(pedals['layer'])
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
                    vehicle=self.config.vehicle, ego_kmh=self.world.ego*3.6, lane=self.world.lane, gap_m=snapshot['gap'],
                    accel_mps2=self.world.acceleration, altitude_m=self.world.altitude, warning=snapshot['warning'],
                    aeb=snapshot['aeb'], score=self.world.score, rtt_ms=round(rtt, 2)))
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

    def _climb(self):
        """Hold the plant during the launch. Traffic waits and the card has no samples
        yet, which it allows until the first one; it can still pause the run."""
        end = time.monotonic() + self.launch
        while time.monotonic() < end:
            if self.stop.wait(.1):
                return False
            self.inputs.sample()  # a lane key pressed on the ramp must not fire on landing
            self.last_response = self.device.runtime('J', timeout=.6)
            if not self.last_response.get('state', {}).get('grun'):
                return False
        return True
