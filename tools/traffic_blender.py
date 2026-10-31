"""Blender script: model the traffic fleet (hatchback, sedan, SUV, light van, taxi) and export glTF.

Started by tools/build_traffic_models.py, never on its own:
    blender --background --factory-startup --python tools/traffic_blender.py -- OUT_DIR

Each body style is a set of real dimensions (class leaders on Turkish roads:
Renault Clio, Fiat Egea sedan, Togg T10X / Hyundai Tucson, Fiat Doblo, a yellow
Egea taxi) and the side-view lines of its body and glasshouse. The geometry
follows tools/model3_blender.py: the body and the glasshouse are lofts of
analytic sections; glass, pillars, lamps, grille and trim are thin conforming
panels laid on those surfaces; only the wheel wells are boolean cuts. Unlike the
Model 3's glass canopy, these roofs are painted and the windows are panels with
a black surround. No badges or logos are modelled.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model3_blender import Profile, at_length, blend, lengths_of, resample, superellipse  # noqa: E402
from sahin_blender import (MATERIALS, P, bake, box, cut, lathe, loft, material,  # noqa: E402
                           new_object, orient_outward, rounded_rect, spaced, sweep)

OUT_DIR = sys.argv[sys.argv.index('--') + 1]


def line(*anchors):
    """Profile traced from the nose back through (x, y, slope, handle in, handle out)
    anchors; a slope of None is vertical, going up (1) or down (-1) by a sixth value."""
    return Profile([((a[0], a[1]), (-1, a[2]) if a[2] is not None else (0, a[5]), a[3], a[4]) for a in anchors])


# Body styles -------------------------------------------------------------------
# length, half width, height; axles and wheels; the body's top and bottom centre
# lines and plan outline; the glasshouse roof line with its cowl, header, rear
# header and deck stations; door and pillar stations; lamps and plates.

STYLES = {
    # Renault Clio V class: 4.05 × 1.76 × 1.44 m, 2.58 m wheelbase, 195/55 R16.
    'Hatch': dict(
        length=4.05, half=0.88, height=1.44, axles=(1.24, -1.34), track=0.755,
        wheel=(0.310, 0.195, 0.203), spokes=('star', 10), n=(5.4, 4.4, 2.4), tumble=0.30, glass_half=0.76,
        top=[(2.025, 0.60, None, 0, 0.22, 1), (1.89, 0.82, 0.26, 0.08, 0.35), (0.97, 0.985, 0.08, 0.40, 0.8),
             (-1.95, 1.015, -0.3, 0.6, 0.03), (-2.025, 0.62, None, 0.36, 0, -1)],
        bottom=[(2.025, 0.56, None, 0, 0.26, -1), (1.80, 0.20, 0.0, 0.12, 0.2), (-1.72, 0.20, 0.0, 0.8, 0.12),
                (-2.025, 0.62, None, 0.26, 0, 1)],
        plan=[(2.025, 0.0, None, 0, 0.70, 1), (1.74, 0.88, 0.0, 0.22, 1.0), (-1.76, 0.88, 0.0, 1.0, 0.2),
              (-2.025, 0.0, None, 0.68, 0, -1)],
        roof=[(0.985, 0.99, 0.62, 0, 0.3), (0.10, 1.405, 0.10, 0.28, 0.25), (-0.80, 1.44, 0.0, 0.3, 0.3),
              (-1.52, 1.40, -0.25, 0.25, 0.1), (-1.90, 1.03, -2.2, 0.12, 0)],
        cowl=0.97, header=0.10, rear_header=-1.52, deck=-1.90,
        doors=(0.93, -0.42, -1.42), b_pillar=-0.42, c_pillar=None, d_pillar=(-1.50, -1.22),
        head=(1.35, 22, 58, (0.68, 0.79), (0.66, 0.80)), grille=(28, 0.46, 0.64), intake=(32, 0.28, 0.40),
        tail=(-1.45, 30, 66, (0.84, 0.98), (0.82, 0.99)), plates=(0.42, 0.72), plate_text='34 KLM 482',
        cladding=False, rails=False, sign=False, bumpers='Paint'),
    # Fiat Egea / Toyota Corolla sedan class: 4.55 × 1.79 × 1.47 m, 2.64 m wheelbase, 205/55 R16.
    'Sedan': dict(
        length=4.55, half=0.895, height=1.47, axles=(1.37, -1.27), track=0.77,
        wheel=(0.316, 0.205, 0.203), spokes=('twin', 5), n=(5.5, 4.6, 2.4), tumble=0.30, glass_half=0.77,
        top=[(2.275, 0.60, None, 0, 0.22, 1), (2.13, 0.82, 0.22, 0.08, 0.35), (0.92, 1.00, 0.06, 0.45, 0.9),
             (-1.62, 1.065, 0.0, 0.9, 0.3), (-2.20, 1.07, -0.25, 0.3, 0.03), (-2.275, 0.62, None, 0.36, 0, -1)],
        bottom=[(2.275, 0.56, None, 0, 0.26, -1), (2.05, 0.21, 0.0, 0.14, 0.2), (-1.92, 0.21, 0.0, 0.8, 0.12),
                (-2.275, 0.62, None, 0.26, 0, 1)],
        plan=[(2.275, 0.0, None, 0, 0.72, 1), (1.98, 0.895, 0.0, 0.22, 1.0), (-2.02, 0.895, 0.0, 1.0, 0.2),
              (-2.275, 0.0, None, 0.70, 0, -1)],
        roof=[(0.935, 1.005, 0.56, 0, 0.32), (0.02, 1.43, 0.10, 0.3, 0.25), (-0.45, 1.47, 0.0, 0.25, 0.3),
              (-1.05, 1.405, -0.35, 0.28, 0.2), (-1.62, 1.075, -0.62, 0.22, 0)],
        cowl=0.92, header=0.02, rear_header=-1.05, deck=-1.62,
        doors=(0.88, -0.30, -1.30), b_pillar=-0.30, c_pillar=None, d_pillar=(-1.22, -0.98),
        head=(1.50, 20, 58, (0.68, 0.79), (0.66, 0.80)), grille=(27, 0.46, 0.65), intake=(34, 0.28, 0.40),
        tail=(-1.70, 24, 68, (0.87, 0.99), (0.86, 1.0)), plates=(0.42, 0.74), plate_text='06 BTR 314',
        cladding=False, rails=False, sign=False, bumpers='Paint'),
    # Togg T10X / Hyundai Tucson class SUV: 4.50 × 1.86 × 1.66 m, 2.68 m wheelbase, 235/60 R18.
    'Suv': dict(
        length=4.50, half=0.93, height=1.66, axles=(1.33, -1.35), track=0.80,
        wheel=(0.370, 0.235, 0.229), spokes=('twin', 5), n=(6.0, 4.8, 2.6), tumble=0.26, glass_half=0.79,
        top=[(2.25, 0.74, None, 0, 0.24, 1), (2.08, 1.00, 0.20, 0.08, 0.35), (0.80, 1.14, 0.05, 0.45, 0.9),
             (-2.17, 1.18, -0.3, 0.9, 0.03), (-2.25, 0.74, None, 0.36, 0, -1)],
        bottom=[(2.25, 0.70, None, 0, 0.30, -1), (2.00, 0.27, 0.0, 0.14, 0.2), (-1.85, 0.27, 0.0, 0.8, 0.12),
                (-2.25, 0.74, None, 0.30, 0, 1)],
        plan=[(2.25, 0.0, None, 0, 0.74, 1), (1.95, 0.93, 0.0, 0.22, 1.0), (-1.97, 0.93, 0.0, 1.0, 0.2),
              (-2.25, 0.0, None, 0.72, 0, -1)],
        roof=[(0.815, 1.145, 0.66, 0, 0.32), (-0.05, 1.615, 0.06, 0.3, 0.25), (-0.70, 1.66, 0.0, 0.3, 0.3),
              (-1.72, 1.625, -0.12, 0.3, 0.1), (-2.05, 1.20, -3.0, 0.14, 0)],
        cowl=0.80, header=-0.05, rear_header=-1.72, deck=-2.05,
        doors=(0.76, -0.40, -1.45), b_pillar=-0.40, c_pillar=-1.42, d_pillar=(-1.86, -1.68),
        head=(1.45, 18, 60, (0.86, 0.95), (0.84, 0.96)), grille=(29, 0.52, 0.82), intake=(36, 0.32, 0.48),
        tail=(-1.62, 26, 68, (0.98, 1.10), (0.97, 1.11)), plates=(0.50, 0.84), plate_text='35 AYD 77',
        cladding=True, rails=True, sign=False, bumpers='Paint'),
    # Fiat Doblo class light van: 4.40 × 1.85 × 1.85 m, 2.75 m wheelbase, 195/65 R15.
    'Van': dict(
        length=4.40, half=0.925, height=1.85, axles=(1.32, -1.43), track=0.79,
        wheel=(0.317, 0.195, 0.191), spokes=('steel', 8), n=(6.5, 6.0, 3.2), tumble=0.12, glass_half=0.84,
        top=[(2.20, 0.70, None, 0, 0.24, 1), (2.05, 0.95, 0.30, 0.08, 0.35), (0.98, 1.11, 0.12, 0.40, 0.9),
             (-2.15, 1.16, -0.5, 0.9, 0.02), (-2.20, 0.62, None, 0.4, 0, -1)],
        bottom=[(2.20, 0.66, None, 0, 0.30, -1), (1.98, 0.24, 0.0, 0.12, 0.2), (-2.00, 0.24, 0.0, 0.8, 0.08),
                (-2.20, 0.62, None, 0.3, 0, 1)],
        plan=[(2.20, 0.0, None, 0, 0.78, 1), (1.95, 0.925, 0.0, 0.20, 1.0), (-2.08, 0.925, 0.0, 1.0, 0.08),
              (-2.20, 0.0, None, 0.8, 0, -1)],
        roof=[(0.995, 1.12, 0.95, 0, 0.32), (0.18, 1.73, 0.18, 0.3, 0.2), (-0.40, 1.85, 0.0, 0.25, 0.4),
              (-1.98, 1.84, -0.05, 0.4, 0.05), (-2.14, 1.17, None, 0.12, 0, -1)],
        cowl=0.98, header=0.18, rear_header=-1.98, deck=-2.14,
        doors=(0.94, -0.42, -1.48), b_pillar=-0.42, c_pillar=-1.45, d_pillar=(-2.02, -1.94),
        head=(1.50, 20, 60, (0.80, 0.92), (0.78, 0.93)), grille=(25, 0.55, 0.80), intake=(34, 0.30, 0.46),
        tail=(-1.80, 46, 72, (0.72, 1.10), (0.72, 1.11)), plates=(0.46, 0.66), plate_text='16 ULD 905',
        cladding=False, rails=True, sign=False, bumpers='Trim'),
}
# Istanbul taxis: the sedan in yellow, a lit roof sign and a T-series plate.
STYLES['Taxi'] = dict(STYLES['Sedan'], plate_text='34 T 6142', sign=True)


class Car:
    """Analytic body and glasshouse of one style, and conforming panels on them."""

    def __init__(self, style):
        s = self.s = style
        self.front, self.rear = s['length'] / 2, -s['length'] / 2
        self.top, self.bottom = line(*s['top']), line(*s['bottom'])
        self.plan, self.roof = line(*s['plan']), line(*s['roof'])
        self.lower_n, self.upper_n, self.crown_n = s['n']
        self.centroid = Vector((0.0, 0.0, s['height'] * 0.45))

    # Body ----------------------------------------------------------------------

    def frame(self, v):
        b, t = self.bottom(v), self.top(v)
        return b, t, self.plan(v), b + (t - b) * 0.55

    def half_width_at(self, v, w):
        b, t, hw, s = self.frame(v)
        if w >= s:
            return hw * superellipse((w - s) / max(t - s, 1e-6), self.upper_n)
        return hw * superellipse((s - w) / max(s - b, 1e-6), self.lower_n)

    def deck_height(self, v, u):
        b, t, hw, s = self.frame(v)
        return s + (t - s) * superellipse(abs(u) / max(hw, 1e-6), self.upper_n)

    def section_curve(self, v, samples=120):
        b, t, hw, s = self.frame(v)
        points = []
        for k in range(samples + 1):
            a = math.pi / 2 * (1 - k / samples)
            points.append((hw * math.cos(a) ** (2 / self.lower_n), s - (s - b) * math.sin(a) ** (2 / self.lower_n)))
        for k in range(1, samples + 1):
            a = math.pi / 2 * k / samples
            points.append((hw * max(math.cos(a), 0.0) ** (2 / self.upper_n), s + (t - s) * math.sin(a) ** (2 / self.upper_n)))
        return points

    # Glasshouse ----------------------------------------------------------------

    def glass_base(self, v):
        s = self.s
        return (s['glass_half'] - 0.07 * blend(v, s['cowl'] - 0.3, s['cowl'])
                - 0.08 * blend(v, s['deck'] + 0.45, s['deck']))

    def cabin_frame(self, v):
        he = self.glass_base(v)
        e = self.deck_height(v, he)
        roof = self.roof(v)
        crown = min(0.05, 0.5 * max(roof - e, 0.0))
        rail = roof - crown
        return he, e, he - self.s['tumble'] * (rail - e), rail, roof

    def cabin_curve(self, v, samples=40):
        he, e, hr, rail, roof = self.cabin_frame(v)
        points = [(he, e), (hr, rail)]
        for k in range(1, samples + 1):
            a = math.pi / 2 * k / samples
            points.append((hr * max(math.cos(a), 0.0) ** (2 / self.crown_n),
                           rail + (roof - rail) * math.sin(a) ** (2 / self.crown_n)))
        return points

    def cabin_rail(self, v):
        he, e, hr, rail, _ = self.cabin_frame(v)
        return math.hypot(he - hr, rail - e)

    def cabin_span(self, v):
        return lengths_of(self.cabin_curve(v))[-1]

    def cabin_at(self, v, d, side=1):
        points = self.cabin_curve(v)
        u, w = at_length(points, lengths_of(points), min(max(d, 0.0), lengths_of(points)[-1]))
        return side * u, v, w

    # Projections ---------------------------------------------------------------

    def inside_body(self, u, v, w):
        if not self.rear < v < self.front:
            return False
        b, t, _, _ = self.frame(v)
        return b < w < t and abs(u) < self.half_width_at(v, w)

    def radial(self, centre, sign, angle, w):
        """Body surface hit by a horizontal ray from (0, centre, w); sign 1 front, -1 rear."""
        du, dv = math.sin(angle), sign * math.cos(angle)
        lo, hi = 0.0, 3.0
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if self.inside_body(du * mid, centre + dv * mid, w) else (lo, mid)
        return du * lo, centre + dv * lo, w

    def side_point(self, v, w, side=1):
        return side * self.half_width_at(v, w), v, w

    def top_point(self, u, v):
        return u, v, self.deck_height(v, u)

    def depth(self, sign, u, w):
        """Most forward (sign 1) or rearward body point at (u, w)."""
        lo, hi = 1.0 * sign, self.front if sign > 0 else self.rear
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if self.inside_body(u, mid, w) else (lo, mid)
        return lo

    def normal_at(self, surface, s, t, p, h=1e-3):
        ds = Vector(surface(min(s + h, 1.0), t)) - Vector(surface(max(s - h, 0.0), t))
        dt = Vector(surface(s, min(t + h, 1.0))) - Vector(surface(s, max(t - h, 0.0)))
        n, away = ds.cross(dt), p - self.centroid
        if n.length < 1e-12:
            return away.normalized()
        n.normalize()
        return n if n.dot(away) >= 0 else -n

    def panel(self, name, material_name, surface, rows, cols, offset=0.004):
        """Thin skin on an analytic surface: surface(s, t) -> car space for s, t in [0, 1]."""
        bm = bmesh.new()
        grid = []
        for i in range(rows + 1):
            row = []
            for j in range(cols + 1):
                s, t = i / rows, j / cols
                p = Vector(surface(s, t))
                row.append(bm.verts.new(P(*(p + self.normal_at(surface, s, t, p) * offset))))
            grid.append(row)
        for i in range(rows):
            for j in range(cols):
                bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
        for face in list(bm.faces):
            if face.calc_area() < 1e-10:
                bm.faces.remove(face)
        orient_outward(bm, P(*self.centroid))
        return new_object(name, bm, material_name)


def mirror(p, side):
    return side * p[0], p[1], p[2]


# Materials -------------------------------------------------------------------

def create_materials():
    MATERIALS.clear()
    for name, color, metal, rough in [
            ('Paint', (0.5, 0.5, 0.52), 0.5, 0.3), ('Glass', (0.02, 0.025, 0.03), 0.0, 0.05),
            ('GlossBlack', (0.01, 0.01, 0.012), 0.0, 0.12), ('Trim', (0.015, 0.015, 0.017), 0.0, 0.6),
            ('Under', (0.01, 0.01, 0.01), 0.0, 0.9), ('LampDark', (0.04, 0.045, 0.05), 0.6, 0.15),
            ('Headlight', (0.9, 0.92, 0.95), 0.0, 0.1), ('TailLight', (0.45, 0.02, 0.03), 0.0, 0.2),
            ('Signal', (0.8, 0.4, 0.05), 0.0, 0.2), ('Reflex', (0.3, 0.02, 0.02), 0.0, 0.3),
            ('Reflector', (0.85, 0.86, 0.88), 1.0, 0.06), ('Chrome', (0.8, 0.82, 0.85), 1.0, 0.12),
            ('Plate', (0.92, 0.92, 0.9), 0.0, 0.5), ('PlateText', (0.01, 0.01, 0.01), 0.0, 0.5),
            ('PlateBand', (0.05, 0.18, 0.6), 0.0, 0.5), ('Interior', (0.03, 0.03, 0.035), 0.0, 0.8),
            ('SignBody', (0.95, 0.93, 0.85), 0.0, 0.4), ('SignText', (0.01, 0.01, 0.01), 0.0, 0.5),
            ('Tyre', (0.02, 0.02, 0.02), 0.0, 0.85), ('Rim', (0.6, 0.62, 0.64), 0.9, 0.3),
            ('Steel', (0.08, 0.08, 0.09), 0.5, 0.5), ('Cap', (0.5, 0.52, 0.55), 0.8, 0.3)]:
        material(name, color, metal, rough)


# Body and glasshouse -----------------------------------------------------------

def body_loop(car, v, count=40):
    right = resample(car.section_curve(v), count)
    return right + [(-u, w) for u, w in reversed(right[1:-1])]


def cabin_loop(car, v, count=24):
    he, e, _, _, _ = car.cabin_frame(v)
    curve = resample(car.cabin_curve(v), count)
    right = [(he, e - 0.05)] + curve[:-1]
    return [(0.0, e - 0.05)] + right + [curve[-1]] + [(-u, w) for u, w in reversed(right)]


def build_body(car):
    s = car.s
    radius, tyre, _ = s['wheel']
    near = (0.004, 0.009, 0.016, 0.026, 0.04, 0.058, 0.08, 0.11)
    stations = spaced(car.front - 0.0004, car.rear + 0.0004, 0.034,
                      dense_ends=[car.front - d for d in near] + [car.rear + d for d in near])
    shell = loft('Shell', [(v, body_loop(car, v)) for v in stations], 'Paint')
    wells = []
    inner, arch = s['track'] - tyre / 2 - 0.07, radius + 0.065
    for axle in s['axles']:
        for side in (-1, 1):
            well = lathe('Well', 'Under', [(side * inner, 0.0), (side * inner, arch), (side * 1.4, arch), (side * 1.4, 0.0)], 48)
            well.location = P(0, axle, radius + 0.015)
            wells.append(well)
    cut(shell, wells, 'WellCut')
    mod = shell.modifiers.new('Normals', 'WEIGHTED_NORMAL')
    mod.mode, mod.keep_sharp, mod.weight = 'FACE_AREA', True, 100
    cabin_stations = spaced(s['cowl'] + 0.014, s['deck'] + 0.004, 0.04,
                            dense_ends=[s['cowl'] + 0.01, s['cowl'], s['cowl'] - 0.015, s['deck'] + 0.012, s['deck'] + 0.025])
    roof = loft('Roof', [(v, cabin_loop(car, v)) for v in cabin_stations], 'Paint')
    return [shell, roof]


def windows(car):
    """Windscreen, side glass and rear window on the painted glasshouse, each with
    a gloss black surround; blacked-out B (and C) pillars over the side glass."""
    s, parts = car.s, []
    cowl, header, back, deck = s['cowl'], s['header'], s['rear_header'], s['deck']
    for side in (1, -1):
        def screen(a, b, side=side, grow=0.0):
            v = cowl + 0.016 + (header - 0.03 + grow - cowl - 0.016) * a
            rail = car.cabin_rail(v)
            return car.cabin_at(v, rail + 0.055 - grow + (car.cabin_span(v) - rail - 0.055 + grow) * b, side)

        def rear(a, b, side=side, grow=0.0):
            v = back - 0.035 + grow + (deck + 0.016 - back + 0.035 - grow) * a
            rail = car.cabin_rail(v)
            return car.cabin_at(v, rail + 0.06 - grow + (car.cabin_span(v) - rail - 0.06 + grow) * b, side)

        def glass(a, b, side=side, grow=0.0):
            rear_bottom, rear_top = s['d_pillar']
            v_rear = rear_bottom + (rear_top - rear_bottom) * b - grow
            v = cowl + 0.02 - grow + (v_rear - cowl - 0.02 + grow) * a
            d0 = 0.03 - grow
            d1 = max(car.cabin_rail(v) - 0.04 + grow, d0)
            return car.cabin_at(v, d0 + (d1 - d0) * b, side)
        for name, surface, rows, cols in (('Screen', screen, 24, 10), ('Back', rear, 16, 10), ('Side', glass, 48, 8)):
            parts.append(car.panel(name + 'Frame', 'GlossBlack', lambda a, b, f=surface: f(a, b, grow=0.018), rows, cols, 0.003))
            parts.append(car.panel(name, 'Glass', surface, rows, cols, 0.0045))
        for v in [s['b_pillar']] + ([s['c_pillar']] if s['c_pillar'] else []):
            parts.append(car.panel('Pillar', 'GlossBlack', lambda a, b, v=v, side=side:
                                   car.cabin_at(v + 0.045 - 0.09 * a, (car.cabin_rail(v) - 0.01) * b + 0.012, side), 3, 10, 0.0062))
    # High-level stop lamp at the top of the rear window.
    for side in (1, -1):
        parts.append(car.panel('StopLamp', 'TailLight', lambda a, b, side=side:
                               car.cabin_at(back - 0.05 - 0.025 * a, car.cabin_span(back - 0.05) - 0.16 + 0.16 * b, side), 1, 6, 0.006))
    return parts


def lamps(car):
    s, parts = car.s, []

    def corner(spec, sign, side):
        centre, a0, a1, inner, outer = spec

        def surface(a, b):
            low = inner[0] + (outer[0] - inner[0]) * a
            high = inner[1] + (outer[1] - inner[1]) * a
            return mirror(car.radial(centre, sign, math.radians(a0 + (a1 - a0) * a), low + (high - low) * b), side)
        return surface
    for side in (1, -1):
        head = corner(s['head'], 1, side)
        parts.append(car.panel('Headlamp', 'LampDark', head, 28, 6))
        parts.append(car.panel('Lens', 'Headlight', lambda a, b, h=head: h(0.06 + 0.7 * a, 0.25 + 0.5 * b), 20, 3, 0.0055))
        parts.append(car.panel('DRL', 'Headlight', lambda a, b, h=head: h(0.04 + 0.92 * a, 0.86 + 0.08 * b), 24, 1, 0.0058))
        parts.append(car.panel('Turn', 'Signal', lambda a, b, h=head: h(0.8 + 0.16 * a, 0.2 + 0.55 * b), 4, 3, 0.0058))
        tail = corner(s['tail'], -1, side)
        grown = corner((s['tail'][0], s['tail'][1] - 1.5, s['tail'][2] + 1.5, (s['tail'][3][0] - 0.012, s['tail'][3][1] + 0.012),
                        (s['tail'][4][0] - 0.012, s['tail'][4][1] + 0.012)), -1, side)
        parts.append(car.panel('TailHousing', 'LampDark', grown, 28, 6, 0.003))
        parts.append(car.panel('Tail', 'TailLight', tail, 28, 6, 0.0045))
        parts.append(car.panel('TailDark', 'LampDark', lambda a, b, t=tail: t(0.1 + 0.3 * a, 0.12 + 0.3 * b), 8, 2, 0.0055))
        parts.append(car.panel('Reverse', 'Headlight', lambda a, b, t=tail: t(0.12 + 0.18 * a, 0.5 + 0.22 * b), 4, 2, 0.0058))
        rb = s['plates'][1] - 0.32
        parts.append(car.panel('Reflex', 'Reflex', lambda a, b, side=side:
                               mirror(car.radial(s['tail'][0], -1, math.radians(58 + 14 * a), rb + 0.025 * b), side), 6, 1))
    angle, low, high = s['grille']

    def grille(a, b, grow=0.0):
        x = 2 * a - 1
        half = (high - low) / 2 * superellipse(abs(x), 6.0) ** 0.3
        return car.radial(s['head'][0], 1, math.radians(angle + grow * 60) * x, (low + high) / 2 + (half + grow) * (2 * b - 1))
    parts.append(car.panel('GrilleFrame', 'Chrome' if s['bumpers'] == 'Paint' else 'Trim', lambda a, b: grille(a, b, 0.012), 30, 4, 0.0035))
    parts.append(car.panel('Grille', 'GlossBlack', grille, 30, 4, 0.0048))
    for k in range(1, 4):
        w = low + (high - low) * k / 4
        parts.append(car.panel('Slat', 'Trim', lambda a, b, w=w: car.radial(s['head'][0], 1, math.radians(angle * 0.95) * (2 * a - 1), w + 0.008 * b), 24, 1, 0.006))
    angle, low, high = s['intake']
    parts.append(car.panel('Intake', 'Trim', lambda a, b: car.radial(s['head'][0], 1, math.radians(angle) * (2 * a - 1),
                                                                     low + (high - low) * b), 30, 3))
    lip = car.frame(car.front - 0.25)[0]
    parts.append(car.panel('Splitter', 'Trim', lambda a, b: car.radial(s['head'][0], 1, math.radians(55) * (2 * a - 1),
                                                                       lip + 0.03 + 0.07 * b), 40, 2, 0.0035))
    rear_low = car.frame(car.rear + 0.25)[0]
    parts.append(car.panel('Valance', 'Trim', lambda a, b: car.radial(s['tail'][0], -1, math.radians(56) * (2 * a - 1),
                                                                      rear_low + 0.03 + 0.12 * b), 40, 3, 0.0035))
    if s['bumpers'] == 'Trim':
        # Unpainted bumpers of a working van, front and rear.
        for sign, centre in ((1, s['head'][0]), (-1, s['tail'][0])):
            base = car.frame(car.front - 0.2 if sign > 0 else car.rear + 0.2)[0]
            parts.append(car.panel('Bumper', 'Trim', lambda a, b, sign=sign, centre=centre, base=base:
                                   car.radial(centre, sign, math.radians(58) * (2 * a - 1), base + 0.06 + 0.27 * b), 48, 6, 0.003))
    return parts


def sides(car):
    """Shut lines, handles, mirrors, SUV cladding, roof rails and the taxi sign."""
    s, parts, gap = car.s, [], 0.0045
    radius = s['wheel'][0]
    for side in (1, -1):
        for v in s['doors']:
            top = car.cabin_frame(v)[1] - 0.012
            low = car.frame(v)[0] + 0.1
            parts.append(car.panel('Gap', 'Trim', lambda a, b, v=v, top=top, low=low, side=side:
                                   car.side_point(v + gap * (b - 0.5), low + (top - low) * a, side), 24, 1, 0.0025))
        for front_edge in s['doors'][:2]:
            v, w = front_edge - 0.16, car.cabin_frame(front_edge)[1] - 0.12
            parts.append(car.panel('Handle', 'Chrome' if s['bumpers'] == 'Paint' else 'Trim', lambda a, b, v=v, w=w, side=side:
                                   car.side_point(v - 0.17 * a, w + 0.028 * b, side), 6, 1, 0.006))
        # Mirror on the door's front corner, glass facing back.
        v = s['cowl'] - 0.16
        belt = car.cabin_frame(v)[1]
        u = car.half_width_at(v, belt) + 0.075
        mirror_paint = 'Paint' if s['bumpers'] == 'Paint' else 'Trim'
        parts.append(box('Mirror', mirror_paint, (side * u, v, belt + 0.075), (0.17, 0.10, 0.11), bevel=0.035))
        parts.append(box('MirrorGlass', 'Reflector', (side * (u + 0.005), v - 0.051, belt + 0.075), (0.14, 0.004, 0.08)))
        parts.append(box('MirrorArm', 'Trim', (side * (u - 0.085), v + 0.01, belt + 0.035), (0.1, 0.06, 0.035), bevel=0.012))
        parts.append(car.panel('Repeater', 'Signal', lambda a, b, side=side:
                               car.side_point(s['axles'][0] + 0.45 + 0.07 * a, car.frame(s['axles'][0] + 0.45)[3] + 0.06 + 0.025 * b, side), 3, 1, 0.004))
        if s['cladding']:
            # Unpainted arch flares and sill of a crossover.
            for axle in s['axles']:
                path = []
                for k in range(25):
                    a = math.pi * k / 24
                    v, w = axle + (radius + 0.09) * math.cos(a), radius + 0.015 + (radius + 0.09) * math.sin(a)
                    path.append((side * (car.half_width_at(v, w) - 0.012), v, w))
                parts.append(sweep('Flare', 'Trim', rounded_rect(0.075, 0.03, 0.01), path, up=Vector((side, 0, 0))))
            front_v, rear_v = s['axles'][0] - radius - 0.1, s['axles'][1] + radius + 0.1
            parts.append(car.panel('Sill', 'Trim', lambda a, b, side=side, f=front_v, r=rear_v:
                                   car.side_point(f + (r - f) * a, car.frame(f + (r - f) * a)[0] + 0.03 + 0.14 * b, side), 40, 3, 0.003))
        if s['rails']:
            path = []
            for k in range(13):
                v = s['header'] - 0.12 + (s['rear_header'] + 0.12 - s['header'] + 0.12) * k / 12
                x, _, w = car.cabin_at(v, car.cabin_rail(v) + 0.07, side)
                path.append((x, v, w + 0.035))
            parts.append(sweep('Rail', 'Chrome' if s['cladding'] else 'Trim', rounded_rect(0.03, 0.04, 0.01), path))
    if s['sign']:
        v = s['b_pillar'] - 0.1
        roof = car.roof(v)
        parts.append(box('Sign', 'SignBody', (0, v, roof + 0.085), (0.6, 0.17, 0.15), bevel=0.02))
        parts.append(box('SignBase', 'Trim', (0, v, roof + 0.008), (0.46, 0.15, 0.02), bevel=0.006))
        for sign in (1, -1):
            parts.append(text('SignText', 'TAKSİ', 0.085, (0, v + sign * 0.087, roof + 0.083), sign))
    return parts


def text(name, body, size, location, facing):
    """Flat lettering in the u-w plane, readable from the front (1) or rear (-1)."""
    curve = bpy.data.curves.new(name, 'FONT')
    curve.body = body
    curve.size, curve.extrude = size, 0.0012
    curve.align_x, curve.align_y = 'CENTER', 'CENTER'
    curve.space_character = 1.04
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(MATERIALS['SignText' if name == 'SignText' else 'PlateText'])
    obj.rotation_euler = (math.pi / 2, 0, 0 if facing > 0 else math.pi)
    obj.location = P(*location)
    return obj


def plates(car):
    s, parts = car.s, []
    front_w, rear_w = s['plates']
    front = car.depth(1, 0.0, front_w)
    front_back = min(car.depth(1, x, front_w) for x in (-0.27, 0.27))
    rear = car.depth(-1, 0.0, rear_w)
    rear_back = max(car.depth(-1, x, rear_w) for x in (-0.27, 0.27))
    parts.append(box('Bracket', 'Trim', (0, (front + front_back) / 2 + 0.004, front_w), (0.53, front - front_back + 0.01, 0.12)))
    parts.append(box('Bracket', 'Trim', (0, (rear + rear_back) / 2 - 0.004, rear_w), (0.53, rear_back - rear + 0.01, 0.12)))
    for v, sign, w in ((front + 0.013, 1, front_w), (rear - 0.013, -1, rear_w)):
        parts.append(box('Plate', 'Plate', (0, v, w), (0.52, 0.006, 0.112), bevel=0.003))
        parts.append(box('PlateBand', 'PlateBand', (-0.236 * sign, v + sign * 0.0035, w), (0.042, 0.002, 0.106)))
        parts.append(text('PlateText', s['plate_text'], 0.07, (0.02 * sign, v + sign * 0.0045, w - 0.002), sign))
    return parts


def interior(car):
    s, parts = car.s, []
    belt = car.cabin_frame(s['b_pillar'])[1]
    seat_v = s['b_pillar'] - 0.12
    for side in (1, -1):
        seat = box('SeatBack', 'Interior', (0, 0, 0), (0.5, 0.12, 0.55), bevel=0.05)
        seat.rotation_euler, seat.location = (math.radians(-14), 0, 0), P(side * 0.37, seat_v, belt - 0.02)
        parts.append(seat)
        parts.append(box('Headrest', 'Interior', (side * 0.37, seat_v - 0.07, belt + 0.27), (0.26, 0.1, 0.15), bevel=0.04))
    parts.append(box('RearBench', 'Interior', (0, seat_v - 0.85, belt - 0.02), (1.25, 0.14, 0.5), bevel=0.05))
    # Behind the windscreen base, under the glass.
    parts.append(box('Dashboard', 'Interior', (0, s['cowl'] - 0.45, belt - 0.03), (1.45, 0.38, 0.16), bevel=0.05))
    wheel = lathe('SteeringWheel', 'Interior', [(-0.016, 0.16), (0.016, 0.16), (0.016, 0.185), (-0.016, 0.185)], 32)
    wheel.rotation_euler = (0, math.radians(-25), math.pi / 2)
    wheel.location = P(0.37, s['cowl'] - 0.55, belt + 0.06)
    parts.append(wheel)
    return parts


def wheel_parts(car):
    radius, width, rim = car.s['wheel']
    kind, count = car.s['spokes']
    w, r = width / 2, radius
    wall = r - rim
    profile = [(-w + 0.008, rim - 0.004), (-w, rim + 0.02), (-w - 0.005, rim + wall * 0.5), (-w, r - wall * 0.22),
               (-w + 0.016, r - 0.008), (-w + 0.034, r - 0.002)]
    for k in range(9):
        x = -w + 0.04 + k * (2 * w - 0.08) / 8
        profile.append((x, r - (0.006 if k in (2, 4, 6) else 0.0)))
    profile += [(w - 0.034, r - 0.002), (w - 0.016, r - 0.008), (w, r - wall * 0.22), (w + 0.005, rim + wall * 0.5),
                (w, rim + 0.02), (w - 0.008, rim - 0.004)]
    parts = [lathe('WheelTyre', 'Tyre', profile, 64)]
    face = 'Steel' if kind == 'steel' else 'Rim'
    parts.append(lathe('WheelBarrel', 'Steel', [(-w + 0.01, 0.0), (-w + 0.01, rim), (w - 0.01, rim), (w - 0.01, 0.0)], 56))
    for side in (-1, 1):
        x = side * (w - 0.004)
        # Rim lip, then a recessed face the spokes stand on.
        parts.append(lathe('WheelLip', face, [(x, rim + 0.004), (x + side * 0.012, rim - 0.006),
                                              (x + side * 0.012, rim - 0.02), (x, rim - 0.026)], 64))
        parts.append(lathe('WheelFace', 'Steel', [(x - side * 0.03, rim - 0.02), (x - side * 0.03, 0.0)], 48))
        if kind == 'steel':
            # Pressed steel wheel behind a plain plastic cover with vents.
            parts.append(lathe('WheelCover', 'Cap', [(x, rim - 0.01), (x + side * 0.016, rim - 0.03), (x + side * 0.024, 0.09),
                                                    (x + side * 0.028, 0.0)], 56))
            for k in range(count):
                a = 2 * math.pi * (k + 0.5) / count
                parts.append(box('WheelVent', 'Steel', (x + side * 0.02, 0, 0), (0.006, 0.05, 0.018)))
                vent = parts[-1]
                vent.location = P(x + side * 0.021, 0.13 * math.cos(a), 0.13 * math.sin(a))
                vent.rotation_euler = (a, 0, 0)
            continue
        spokes = [(2 * math.pi * k / count + d, 0.012 if kind == 'twin' else 0.016)
                  for k in range(count) for d in ((-0.12, 0.12) if kind == 'twin' else (0.0,))]
        for a, thick in spokes:
            path = []
            for j in range(5):
                f = j / 4
                rr = 0.055 + (rim - 0.075) * f
                path.append((x + side * (0.026 - 0.016 * f), rr * math.cos(a + 0.04 * f * side), rr * math.sin(a + 0.04 * f * side)))
            parts.append(sweep('WheelSpoke', face, rounded_rect(thick * 2.2, 0.018, 0.005),
                               [(px, -py, pz) for px, py, pz in path], up=Vector((1, 0, 0))))
        parts.append(lathe('WheelHub', face, [(x + side * 0.03, 0.07), (x + side * 0.034, 0.05), (x + side * 0.036, 0.0)], 40))
        parts.append(lathe('WheelCap', 'Cap', [(x + side * 0.036, 0.03), (x + side * 0.04, 0.02), (x + side * 0.041, 0.0)], 32))
    return parts


# Assembly and export ---------------------------------------------------------

def build(name, style):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create_materials()
    car = Car(style)
    parts = build_body(car) + windows(car) + lamps(car) + sides(car) + plates(car) + interior(car)
    pieces = bake([o for o in parts if o.visible_get()])
    wheel = bake(wheel_parts(car))
    for prefix, group in ((name, pieces), (name + 'Wheel', wheel)):
        for obj in group:
            obj.name = obj.data.name = prefix + obj.data.materials[0].name
    for obj in bpy.data.objects:
        if not obj.visible_get():
            bpy.data.objects.remove(obj)
    bpy.ops.object.select_all(action='SELECT')
    bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(32), keep_sharp_edges=True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT_DIR, name + '.glb'), export_format='GLB', export_apply=True,
                              export_yup=True, export_materials='EXPORT', export_normals=True, export_texcoords=False,
                              use_selection=False)
    points = [obj.matrix_world @ vert.co for obj in pieces for vert in obj.data.vertices]
    rear, front = min(-p.y for p in points), max(-p.y for p in points)
    half = max(abs(p.x) for obj in pieces if obj.name != name + 'Reflector' for p in
               (obj.matrix_world @ vert.co for vert in obj.data.vertices))
    print(name, 'BOUNDS', rear, front, style['half'], max(p.z for p in points), half)
    print(name, 'WHEELS', style['axles'][0], style['axles'][1], style['track'], style['wheel'][0])
    centre = (front + rear) / 2
    head, tail = style['head'], style['tail']
    lamp_front = car.radial(head[0], 1, math.radians(head[2] - 4), (head[4][0] + head[4][1]) / 2)
    lamp_rear = car.radial(tail[0], -1, math.radians(tail[2] - 4), (tail[4][0] + tail[4][1]) / 2)
    print(name, 'INDICATORS', lamp_front[2], lamp_rear[2], lamp_front[0], lamp_rear[0],
          lamp_front[1] - centre, lamp_rear[1] - centre)


def main():
    only = sys.argv[sys.argv.index('--') + 2:] or list(STYLES)
    for name in only:
        build(name, STYLES[name])


if __name__ == '__main__':
    main()
