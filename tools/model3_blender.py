"""Blender script: model the Tesla Model 3 style electric saloon and export glTF.

Started by tools/build_model3_model.py, never on its own:
    blender --background --factory-startup --python tools/model3_blender.py -- OUT.glb

Proportions follow the real car: 4.69 m long, 1.85 m wide, 1.44 m tall,
2.875 m wheelbase, 235/45 R18 tyres behind aero covers. No badges or logos
are modelled.

Car space, export contract and the geometry helpers are shared with
tools/sahin_blender.py: u toward the car's left, v forward, w up. The body and
the glass canopy are lofts of analytic sections, so lamps, pillars, trim and
panel gaps are laid onto the same analytic surfaces as thin conforming panels
instead of being cut in; only the wheel wells are boolean cuts.
"""
import bisect
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sahin_blender import (MATERIALS, P, bake, box, cut, lathe, loft, material,  # noqa: E402
                           new_object, orient_outward, rounded_rect, spaced, sweep)

OUT = sys.argv[sys.argv.index('--') + 1]
FRONT, REAR = 2.345, -2.345
FRONT_AXLE, REAR_AXLE, TRACK = 1.50, -1.375, 0.79
WHEEL_RADIUS, TYRE_WIDTH, RIM_RADIUS = 0.334, 0.235, 0.229
HALF = 0.92
COWL, HEADER, DECK = 1.12, 0.20, -1.80
LOWER_N, UPPER_N, CROWN_N = 5.0, 4.5, 2.3
CENTROID = Vector((0.0, 0.0, 0.62))
PLATE_TEXT = '34 EV 2026'


# Profiles --------------------------------------------------------------------

class Profile:
    """y(x) through C1 cubic Bezier anchors: (point, direction, handle in, handle out)."""

    def __init__(self, anchors, samples=240):
        points = []
        for (p0, d0, _, h0), (p1, d1, h1, _) in zip(anchors, anchors[1:]):
            n0, n1 = math.hypot(*d0), math.hypot(*d1)
            c0 = (p0[0] + d0[0] / n0 * h0, p0[1] + d0[1] / n0 * h0)
            c1 = (p1[0] - d1[0] / n1 * h1, p1[1] - d1[1] / n1 * h1)
            for k in range(samples):
                t = k / samples
                a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
                points.append(tuple(a * p0[i] + b * c0[i] + c * c1[i] + d * p1[i] for i in (0, 1)))
        points.append(anchors[-1][0])
        points.sort()
        self.x = [p[0] for p in points]
        self.y = [p[1] for p in points]

    def __call__(self, x):
        i = bisect.bisect_left(self.x, x)
        if i <= 0:
            return self.y[0]
        if i >= len(self.x):
            return self.y[-1]
        x0, x1 = self.x[i - 1], self.x[i]
        if x1 - x0 < 1e-12:
            return self.y[i]
        return self.y[i - 1] + (self.y[i] - self.y[i - 1]) * (x - x0) / (x1 - x0)


# Centre-line heights and the plan outline, each traced from the nose back.
TOP = Profile([((FRONT, 0.47), (0, 1), 0, 0.16), ((2.03, 0.78), (-1, 0.36), 0.17, 0.30),
               ((COWL, 0.975), (-1, 0.06), 0.30, 0.9), ((DECK, 1.05), (-1, 0.0), 0.9, 0.14),
               ((-2.20, 1.04), (-1, 0.03), 0.14, 0.07), ((REAR, 0.75), (0, -1), 0.17, 0)])
BOTTOM = Profile([((FRONT, 0.47), (0, -1), 0, 0.16), ((2.13, 0.215), (-1, 0), 0.12, 0.15),
                  ((1.75, 0.175), (-1, 0), 0.15, 1.0), ((-1.75, 0.17), (-1, 0), 1.0, 0.12),
                  ((-2.10, 0.30), (-1, 0.5), 0.12, 0.08), ((REAR, 0.75), (0, 1), 0.25, 0)])
PLAN = Profile([((FRONT, 0.0), (0, 1), 0, 0.50), ((1.80, HALF), (-1, 0), 0.35, 1.2),
                ((-1.92, HALF), (-1, 0), 1.2, 0.25), ((REAR, 0.0), (0, -1), 0.62, 0)])
# Glass canopy centre line: windscreen, glass roof and rear window in one sweep.
ROOF = Profile([((COWL + 0.015, 0.965), (-1, 0.46), 0, 0.30), ((HEADER, 1.405), (-1, 0.12), 0.25, 0.2),
                ((-0.25, 1.443), (-1, 0), 0.2, 0.3), ((-1.15, 1.355), (-1, -0.32), 0.3, 0.25),
                ((DECK, 1.06), (-1, -0.42), 0.25, 0)])


def superellipse(x, n):
    x = min(max(x, 0.0), 1.0)
    return (1.0 - x ** n) ** (1.0 / n)


def blend(x, a, b):
    """Smoothstep from 0 at x == a to 1 at x == b; a may be greater than b."""
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def frame(v):
    """Body section at station v: bottom, top, half width and shoulder height."""
    b, t = BOTTOM(v), TOP(v)
    return b, t, PLAN(v), b + (t - b) * 0.52


def half_width_at(v, w):
    b, t, hw, s = frame(v)
    if w >= s:
        return hw * superellipse((w - s) / max(t - s, 1e-6), UPPER_N)
    return hw * superellipse((s - w) / max(s - b, 1e-6), LOWER_N)


def deck_height(v, u):
    b, t, hw, s = frame(v)
    return s + (t - s) * superellipse(abs(u) / max(hw, 1e-6), UPPER_N)


def section_curve(v, samples=160):
    """Right half of the body section from the bottom centre to the top centre."""
    b, t, hw, s = frame(v)
    points = []
    for k in range(samples + 1):
        a = math.pi / 2 * (1 - k / samples)
        points.append((hw * math.cos(a) ** (2 / LOWER_N), s - (s - b) * math.sin(a) ** (2 / LOWER_N)))
    for k in range(1, samples + 1):
        a = math.pi / 2 * k / samples
        points.append((hw * max(math.cos(a), 0.0) ** (2 / UPPER_N), s + (t - s) * math.sin(a) ** (2 / UPPER_N)))
    return points


def lengths_of(points):
    lengths = [0.0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.hypot(x1 - x0, y1 - y0))
    return lengths


def at_length(points, lengths, d):
    d = min(max(d, 0.0), lengths[-1])
    i = min(max(1, bisect.bisect_left(lengths, d)), len(points) - 1)
    span = lengths[i] - lengths[i - 1]
    f = 0.0 if span < 1e-12 else (d - lengths[i - 1]) / span
    (x0, y0), (x1, y1) = points[i - 1], points[i]
    return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f


def resample(points, count):
    """Equal arc-length steps keep faces even for the boolean cuts and shading."""
    lengths = lengths_of(points)
    return [at_length(points, lengths, lengths[-1] * k / (count - 1)) for k in range(count)]


def glass_base(v):
    """Half width where the canopy sits on the body: narrower at the cowl and the deck."""
    return 0.80 - 0.06 * blend(v, 0.85, COWL) - 0.10 * blend(v, -1.15, DECK)


def cabin_frame(v):
    he = glass_base(v)
    e = deck_height(v, he)
    roof = ROOF(v)
    crown = min(0.055, 0.5 * max(roof - e, 0.0))
    rail = roof - crown
    return he, e, he - 0.42 * (rail - e), rail, roof


def cabin_curve(v, samples=48):
    """Right half of the canopy: leaning side glass, then the crowned roof."""
    he, e, hr, rail, roof = cabin_frame(v)
    points = [(he, e), (hr, rail)]
    for k in range(1, samples + 1):
        a = math.pi / 2 * k / samples
        points.append((hr * max(math.cos(a), 0.0) ** (2 / CROWN_N), rail + (roof - rail) * math.sin(a) ** (2 / CROWN_N)))
    return points


def cabin_rail(v):
    he, e, hr, rail, _ = cabin_frame(v)
    return math.hypot(he - hr, rail - e)


def cabin_span(v):
    return lengths_of(cabin_curve(v))[-1]


def cabin_at(v, d, side=1):
    """Canopy surface d metres from the belt, measured along the section."""
    points = cabin_curve(v)
    u, w = at_length(points, lengths_of(points), d)
    return side * u, v, w


def cabin_reach(v, u):
    """Distance along the canopy section to where its half width drops to u."""
    points = cabin_curve(v)
    lengths = lengths_of(points)
    for i in range(1, len(points)):
        if points[i][0] <= u:
            u0, u1 = points[i - 1][0], points[i][0]
            f = 0.0 if abs(u0 - u1) < 1e-12 else (u0 - u) / (u0 - u1)
            return lengths[i - 1] + (lengths[i] - lengths[i - 1]) * f
    return lengths[-1]


def cabin_height(v, u):
    he, e, hr, rail, roof = cabin_frame(v)
    return rail + (roof - rail) * superellipse(abs(u) / hr, CROWN_N)


# Surface projections for conforming panels ------------------------------------

def inside_body(u, v, w):
    if not REAR < v < FRONT:
        return False
    b, t, _, _ = frame(v)
    return b < w < t and abs(u) < half_width_at(v, w)


def radial(centre, sign, angle, w):
    """Body surface hit by a horizontal ray from (0, centre, w); sign 1 front, -1 rear."""
    du, dv = math.sin(angle), sign * math.cos(angle)
    lo, hi = 0.0, 3.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if inside_body(du * mid, centre + dv * mid, w):
            lo = mid
        else:
            hi = mid
    return du * lo, centre + dv * lo, w


def side_point(v, w, side=1):
    return side * half_width_at(v, w), v, w


def top_point(u, v):
    return u, v, deck_height(v, u)


def mirror(p, side):
    return side * p[0], p[1], p[2]


def normal_at(surface, s, t, p, h=1e-3):
    ds = Vector(surface(min(s + h, 1.0), t)) - Vector(surface(max(s - h, 0.0), t))
    dt = Vector(surface(s, min(t + h, 1.0))) - Vector(surface(s, max(t - h, 0.0)))
    n, away = ds.cross(dt), p - CENTROID
    if n.length < 1e-12:
        return away.normalized()
    n.normalize()
    return n if n.dot(away) >= 0 else -n


def panel(name, material_name, surface, rows, cols, offset=0.004):
    """Thin skin on an analytic surface: surface(s, t) -> car space for s, t in [0, 1]."""
    bm = bmesh.new()
    grid = []
    for i in range(rows + 1):
        line = []
        for j in range(cols + 1):
            s, t = i / rows, j / cols
            p = Vector(surface(s, t))
            line.append(bm.verts.new(P(*(p + normal_at(surface, s, t, p) * offset))))
        grid.append(line)
    for i in range(rows):
        for j in range(cols):
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    for face in list(bm.faces):
        if face.calc_area() < 1e-10:
            bm.faces.remove(face)
    orient_outward(bm, P(*CENTROID))
    return new_object(name, bm, material_name)


def front_depth(u, w):
    """Most forward body point at (u, w)."""
    lo, hi = 1.4, FRONT
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if inside_body(u, mid, w) else (lo, mid)
    return lo


def rear_depth(u, w):
    lo, hi = -1.4, REAR
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if inside_body(u, mid, w) else (lo, mid)
    return lo


# Materials -------------------------------------------------------------------

def create_materials():
    MATERIALS.clear()
    for name, color, metal, rough in [
            ('Paint', (0.04, 0.09, 0.22), 0.6, 0.3), ('Glass', (0.02, 0.025, 0.03), 0.0, 0.05),
            ('GlossBlack', (0.01, 0.01, 0.012), 0.0, 0.12), ('Trim', (0.015, 0.015, 0.017), 0.0, 0.6),
            ('Under', (0.01, 0.01, 0.01), 0.0, 0.9), ('LampDark', (0.04, 0.045, 0.05), 0.6, 0.15),
            ('Headlight', (0.9, 0.92, 0.95), 0.0, 0.1), ('TailLight', (0.45, 0.02, 0.03), 0.0, 0.2),
            ('Reflex', (0.3, 0.02, 0.02), 0.0, 0.3), ('Reflector', (0.85, 0.86, 0.88), 1.0, 0.06),
            ('Plate', (0.92, 0.92, 0.9), 0.0, 0.5), ('PlateText', (0.01, 0.01, 0.01), 0.0, 0.5),
            ('PlateBand', (0.05, 0.18, 0.6), 0.0, 0.5), ('Interior', (0.03, 0.03, 0.035), 0.0, 0.8),
            ('Screen', (0.02, 0.03, 0.05), 0.0, 0.1), ('Tyre', (0.02, 0.02, 0.02), 0.0, 0.85),
            ('Rim', (0.03, 0.03, 0.035), 0.4, 0.5), ('Aero', (0.12, 0.13, 0.14), 0.55, 0.38),
            ('AeroAccent', (0.4, 0.42, 0.44), 0.8, 0.3), ('Cap', (0.01, 0.01, 0.012), 0.0, 0.2)]:
        material(name, color, metal, rough)


# Body and canopy ---------------------------------------------------------------

def body_loop(v, count=42):
    right = resample(section_curve(v), count)
    return right + [(-u, w) for u, w in reversed(right[1:-1])]


def cabin_loop(v, count=26):
    he, e, _, _, _ = cabin_frame(v)
    curve = resample(cabin_curve(v), count)
    right = [(he, e - 0.05)] + curve[:-1]
    return [(0.0, e - 0.05)] + right + [curve[-1]] + [(-u, w) for u, w in reversed(right)]


def build_body():
    ends = (0.004, 0.009, 0.016, 0.026, 0.04, 0.058, 0.08, 0.11)
    stations = spaced(FRONT - 0.0004, REAR + 0.0004, 0.034,
                      dense_ends=[FRONT - d for d in ends] + [REAR + d for d in ends])
    shell = loft('Shell', [(v, body_loop(v)) for v in stations], 'Paint')
    wells = []
    for axle in (FRONT_AXLE, REAR_AXLE):
        for side in (-1, 1):
            well = lathe('Well', 'Under', [(side * 0.50, 0.0), (side * 0.50, 0.375), (side * 1.3, 0.375), (side * 1.3, 0.0)], 48)
            well.location = P(0, axle, WHEEL_RADIUS + 0.012)
            wells.append(well)
    cut(shell, wells, 'WellCut')
    mod = shell.modifiers.new('Normals', 'WEIGHTED_NORMAL')
    mod.mode, mod.keep_sharp, mod.weight = 'FACE_AREA', True, 100

    cabin_stations = spaced(COWL + 0.014, DECK + 0.004, 0.04,
                            dense_ends=[COWL + 0.01, COWL, COWL - 0.015, DECK + 0.012, DECK + 0.025])
    canopy = loft('Canopy', [(v, cabin_loop(v)) for v in cabin_stations], 'Glass')
    return [shell, canopy]


def canopy_trim():
    """Body-colour A and C pillars, gloss black header, rails, B pillar and belt."""
    parts = []
    for side in (1, -1):
        def a_pillar(s, t, side=side):
            v = COWL + 0.01 + (HEADER - 0.015 - COWL - 0.01) * s
            rail = cabin_rail(v)
            return cabin_at(v, max(rail - 0.045, 0.0) + (rail + 0.062 - max(rail - 0.045, 0.0)) * t, side)
        parts.append(panel('APillar', 'Paint', a_pillar, 40, 6))

        def header(s, t, side=side):
            v = HEADER - 0.015 - 0.065 * s
            rail = cabin_rail(v)
            return cabin_at(v, rail - 0.03 + (cabin_span(v) - rail + 0.03) * t, side)
        parts.append(panel('Header', 'GlossBlack', header, 3, 16))

        def roof_rail(s, t, side=side):
            v = HEADER - 0.015 + (-1.16 - HEADER + 0.015) * s
            rail = cabin_rail(v)
            return cabin_at(v, rail - 0.03 + 0.07 * t, side)
        parts.append(panel('Rail', 'GlossBlack', roof_rail, 44, 3, 0.0045))

        def b_pillar(s, t, side=side):
            v = -0.23 - 0.10 * s
            return cabin_at(v, (cabin_rail(v) - 0.03) * t, side)
        parts.append(panel('BPillar', 'GlossBlack', b_pillar, 3, 10))

        def belt(s, t, side=side):
            v = COWL - 0.06 + (-1.40 - COWL + 0.06) * s
            return cabin_at(v, 0.016 * t, side)
        parts.append(panel('Belt', 'GlossBlack', belt, 60, 1, 0.0045))

        def c_pillar(s, t, side=side):
            front = -1.42 + 0.26 * t
            v = front + (DECK + 0.006 - front) * s
            glass = 0.57 + (cabin_frame(-1.16)[2] - 0.035 - 0.57) * blend(v, DECK, -1.16)
            return cabin_at(v, cabin_reach(v, glass) * t, side)
        parts.append(panel('CPillar', 'Paint', c_pillar, 26, 14))
    # High-level stop lamp across the top of the rear window.
    for side in (1, -1):
        def stop(s, t, side=side):
            v = -1.165 - 0.03 * s
            span = cabin_span(v)
            return cabin_at(v, span - 0.13 + 0.13 * t, side)
        parts.append(panel('StopLamp', 'TailLight', stop, 1, 6))
    return parts


def headlamp(s, t, side=1):
    """Housing from the round inner end (s = 0) to the tip swept back over the fender."""
    half = 0.042 * (1 - s) ** 0.75 + 0.008
    if s < 0.1:
        half *= superellipse((0.1 - s) / 0.1, 2.0) ** 0.5
    centre = 0.655 + 0.09 * s
    return mirror(radial(1.55, 1, math.radians(27 + 39 * s), centre + half * (2 * t - 1)), side)


def taillamp(s, t, side=1):
    """Upper edge follows the boot lip; the outer half drops into an L."""
    low = 0.948 - 0.078 * blend(s, 0.42, 0.62)
    high = 0.992 - 0.008 * s
    return mirror(radial(-1.55, -1, math.radians(20 + 42 * s), low + (high - low) * t), side)


def lamps():
    parts = []
    for side in (1, -1):
        parts.append(panel('Headlamp', 'LampDark', lambda s, t, side=side: headlamp(s, t, side), 36, 8))

        def drl(s, t, side=side):
            # Daytime running light along the upper edge of the housing.
            s = 0.05 + 0.9 * s
            centre = 0.655 + 0.09 * s
            top = centre + 0.042 * (1 - s) ** 0.75 + 0.008
            return mirror(radial(1.55, 1, math.radians(27 + 39 * s), top - 0.004 - 0.011 * t), side)
        parts.append(panel('DRL', 'Headlight', drl, 32, 2, 0.0055))

        def projector(s, t, side=side):
            a, r = 2 * math.pi * s, 0.017 * t
            return mirror(radial(1.55, 1, math.radians(33.5) + r * math.cos(a) / 0.85, 0.646 + r * math.sin(a)), side)
        parts.append(panel('Projector', 'Headlight', projector, 16, 1, 0.0055))

        parts.append(panel('Tail', 'TailLight', lambda s, t, side=side: taillamp(s, t, side), 40, 8))

        def tail_inner(s, t, side=side):
            # Darker smoked band inside the L, like the real lamp's lower lens.
            low, high = 0.878, 0.912
            return mirror(radial(-1.55, -1, math.radians(47 + 13 * s), low + (high - low) * t), side)
        parts.append(panel('TailInner', 'LampDark', tail_inner, 10, 3, 0.0055))

        def reflex(s, t, side=side):
            return mirror(radial(-1.55, -1, math.radians(52 + 15 * s), 0.452 + 0.022 * t), side)
        parts.append(panel('Reflex', 'Reflex', reflex, 8, 1))

    def intake(s, t):
        # Lower front intake; rounded ends come from the shrinking height.
        x = 2 * s - 1
        half = 0.045 * superellipse(abs(x), 4.0) ** 0.5
        return radial(1.55, 1, math.radians(31) * x, 0.284 + half * (2 * t - 1))
    parts.append(panel('Intake', 'Trim', intake, 40, 4))

    def diffuser(s, t):
        return radial(-1.55, -1, math.radians(48) * (2 * s - 1), 0.315 + 0.085 * t)
    parts.append(panel('Diffuser', 'Trim', diffuser, 40, 3))
    return parts


def panel_gaps():
    """Shut lines and flush door handles as fine dark strips on the paint."""
    parts = []
    width = 0.0045
    for side in (1, -1):
        for v, w0 in ((1.02, 0.27), (-0.27, 0.27), (-1.0, 0.45)):
            top = cabin_frame(v)[1] - 0.012
            parts.append(panel('Gap', 'Trim', lambda s, t, v=v, w0=w0, top=top, side=side:
                               side_point(v + width * (t - 0.5), w0 + (top - w0) * s, side), 24, 1, 0.0025))
        parts.append(panel('Sill', 'Trim', lambda s, t, side=side:
                           side_point(1.02 + (-0.97 - 1.02) * s, 0.27 + width * (t - 0.5), side), 60, 1, 0.0025))
        parts.append(panel('Bonnet', 'Trim', lambda s, t, side=side:
                           top_point(side * (0.70 + width * (t - 0.5)), 1.16 + (1.99 - 1.16) * s), 30, 1, 0.0025))
        parts.append(panel('Boot', 'Trim', lambda s, t, side=side:
                           top_point(side * (0.64 + width * (t - 0.5)), -1.835 + (-2.17 + 1.835) * s), 14, 1, 0.0025))
        for v in (0.40, -0.70):
            parts.append(panel('Handle', 'Trim', lambda s, t, v=v, side=side:
                               side_point(v - 0.16 * s, 0.862 + 0.022 * t, side), 6, 1, 0.003))
    parts.append(panel('BonnetFront', 'Trim', lambda s, t: top_point(0.70 * (2 * s - 1), 1.99 + width * (t - 0.5)), 30, 1, 0.0025))
    parts.append(panel('BootFront', 'Trim', lambda s, t: top_point(0.64 * (2 * s - 1), -1.835 + width * (t - 0.5)), 26, 1, 0.0025))
    return parts


def mirrors_and_wipers():
    parts = []
    for side in (1, -1):
        parts.append(box('Mirror', 'Paint', (side * 0.955, 0.86, 1.005), (0.17, 0.095, 0.1), bevel=0.035))
        parts.append(box('MirrorGlass', 'Reflector', (side * 0.96, 0.8115, 1.005), (0.14, 0.004, 0.074)))
        parts.append(box('MirrorArm', 'GlossBlack', (side * 0.855, 0.872, 0.962), (0.1, 0.065, 0.035), bevel=0.012))
    for u0 in (0.62, 0.06):
        path = []
        for k in range(5):
            u = u0 - 0.13 * k
            v = COWL - 0.07 - 0.012 * k
            path.append((u, v, cabin_height(v, u) + 0.011))
        parts.append(sweep('Wiper', 'Trim', rounded_rect(0.012, 0.012, 0.004), path))
    return parts


def plates():
    parts = []
    front_w, rear_w = 0.415, 0.625
    front = front_depth(0.0, front_w)
    front_back = min(front_depth(x, front_w) for x in (-0.27, 0.27))
    rear = rear_depth(0.0, rear_w)
    rear_back = max(rear_depth(x, rear_w) for x in (-0.27, 0.27))
    # Dark brackets fill the gap between the flat plates and the curved fascia.
    parts.append(box('Bracket', 'Trim', (0, (front + front_back) / 2 + 0.004, front_w), (0.53, front - front_back + 0.01, 0.12)))
    parts.append(box('Bracket', 'Trim', (0, (rear + rear_back) / 2 - 0.004, rear_w), (0.53, rear_back - rear + 0.01, 0.12)))
    for v, sign, w in ((front + 0.013, 1, front_w), (rear - 0.013, -1, rear_w)):
        parts.append(box('Plate', 'Plate', (0, v, w), (0.52, 0.006, 0.112), bevel=0.003))
        parts.append(box('PlateBand', 'PlateBand', (-0.236 * sign, v + sign * 0.0035, w), (0.042, 0.002, 0.106)))
        curve = bpy.data.curves.new('PlateText', 'FONT')
        curve.body = PLATE_TEXT
        curve.size, curve.extrude = 0.07, 0.0012
        curve.align_x, curve.align_y = 'CENTER', 'CENTER'
        curve.space_character = 1.02
        text = bpy.data.objects.new('PlateText', curve)
        bpy.context.scene.collection.objects.link(text)
        text.data.materials.append(MATERIALS['PlateText'])
        text.rotation_euler = (math.pi / 2, 0, 0 if sign > 0 else math.pi)
        text.location = P(0.02 * sign, v + sign * 0.0045, w - 0.002)
        parts.append(text)
    return parts


def interior():
    """Minimal cabin: slim seats, low dashboard, floating centre screen, yoke-free wheel."""
    parts = []
    for side in (1, -1):
        seat = box('SeatBack', 'Interior', (0, 0, 0), (0.5, 0.12, 0.5), bevel=0.05)
        seat.rotation_euler, seat.location = (math.radians(-12), 0, 0), P(side * 0.37, -0.36, 1.0)
        parts.append(seat)
        parts.append(box('Headrest', 'Interior', (side * 0.37, -0.42, 1.27), (0.27, 0.1, 0.14), bevel=0.04))
    parts.append(box('RearBench', 'Interior', (0, -1.12, 1.02), (1.2, 0.13, 0.3), bevel=0.05))
    parts.append(box('Dashboard', 'Interior', (0, 0.66, 0.97), (1.44, 0.4, 0.14), bevel=0.05))
    screen = box('Screen', 'Screen', (0, 0, 0), (0.34, 0.016, 0.21), bevel=0.006)
    screen.rotation_euler, screen.location = (math.radians(-14), 0, 0), P(0, 0.44, 1.13)
    parts.append(screen)
    parts.append(box('ScreenMount', 'Interior', (0, 0.47, 1.03), (0.06, 0.05, 0.08)))
    wheel = lathe('SteeringWheel', 'Interior', [(-0.016, 0.16), (0.016, 0.16), (0.016, 0.185), (-0.016, 0.185)], 32)
    # Ring axis toward the driver and tilted up 25 degrees.
    wheel.rotation_euler = (0, math.radians(-25), math.pi / 2)
    wheel.location = P(0.37, 0.30, 1.05)
    parts.append(wheel)
    return parts


def wheel_parts():
    w, r = TYRE_WIDTH / 2, WHEEL_RADIUS
    # Low-profile tyre: rounded shoulders, slight sidewall bulge, four grooves.
    profile = [(-w + 0.008, RIM_RADIUS - 0.004), (-w, RIM_RADIUS + 0.018), (-w - 0.004, 0.275), (-w, 0.302),
               (-w + 0.014, 0.322), (-w + 0.034, r - 0.002)]
    tread = []
    for k in range(11):
        x = -w + 0.04 + k * (2 * w - 0.08) / 10
        tread.append((x, r - (0.006 if k in (2, 4, 6, 8) else 0.0)))
    profile += tread + [(w - 0.034, r - 0.002), (w - 0.014, 0.322), (w, 0.302), (w + 0.004, 0.275),
                        (w, RIM_RADIUS + 0.018), (w - 0.008, RIM_RADIUS - 0.004)]
    parts = [lathe('WheelTyre', 'Tyre', profile, 64)]
    parts.append(lathe('WheelRim', 'Rim', [(-w + 0.01, 0.0), (-w + 0.01, RIM_RADIUS), (w - 0.01, RIM_RADIUS), (w - 0.01, 0.0)], 56))
    for side in (-1, 1):
        # Aero cover: shallow dish, a raised outer lip, five turbine blades, hub cap.
        dish = [(side * (w - 0.006), RIM_RADIUS), (side * (w + 0.006), RIM_RADIUS - 0.006),
                (side * (w + 0.012), RIM_RADIUS - 0.02), (side * (w + 0.009), 0.19), (side * (w + 0.014), 0.13),
                (side * (w + 0.02), 0.07), (side * (w + 0.024), 0.03), (side * (w + 0.025), 0.0)]
        parts.append(lathe('WheelAero', 'Aero', dish, 64))
        parts.append(lathe('WheelLip', 'AeroAccent', [(side * (w + 0.004), RIM_RADIUS - 0.002),
                                                      (side * (w + 0.013), RIM_RADIUS - 0.012),
                                                      (side * (w + 0.013), RIM_RADIUS - 0.024),
                                                      (side * (w + 0.004), RIM_RADIUS - 0.03)], 64))
        for k in range(5):
            path = []
            for j in range(6):
                f = j / 5
                radius = 0.06 + 0.13 * f
                a = 2 * math.pi * k / 5 + side * 0.55 * f
                x = side * (w + 0.026 - 0.012 * f)
                path.append((x, radius * math.cos(a), radius * math.sin(a)))
            # Wheel parts are built in Blender axes; sweep() expects car space.
            parts.append(sweep('WheelBlade', 'AeroAccent', rounded_rect(0.024, 0.008, 0.003),
                               [(x, -y, z) for x, y, z in path], up=Vector((1, 0, 0))))
        parts.append(lathe('WheelCap', 'Cap', [(side * (w + 0.024), 0.05), (side * (w + 0.031), 0.044),
                                               (side * (w + 0.034), 0.02), (side * (w + 0.035), 0.0)], 32))
    return parts


# Assembly and export ---------------------------------------------------------

def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create_materials()
    car = build_body() + canopy_trim() + lamps() + panel_gaps() + mirrors_and_wipers() + plates() + interior()
    pieces = bake([o for o in car if o.visible_get()])
    wheel = bake(wheel_parts())
    # Mesh data shares the object name so Balsam writes the same mesh files on
    # every run and platform.
    for prefix, group in (('Model3', pieces), ('Model3Wheel', wheel)):
        for obj in group:
            obj.name = obj.data.name = prefix + obj.data.materials[0].name
    for obj in bpy.data.objects:
        if not obj.visible_get():
            bpy.data.objects.remove(obj)
    bpy.ops.object.select_all(action='SELECT')
    bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(32), keep_sharp_edges=True)
    bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_apply=True, export_yup=True,
                              export_materials='EXPORT', export_normals=True, export_texcoords=False, use_selection=False)
    body_points = [obj.matrix_world @ vert.co for obj in pieces for vert in obj.data.vertices]
    rear, front = min(-p.y for p in body_points), max(-p.y for p in body_points)
    print('BOUNDS', rear, front, HALF, max(p.z for p in body_points))
    print('WHEELS', FRONT_AXLE, REAR_AXLE, TRACK, WHEEL_RADIUS)
    # Vehicle3D's blinking indicators: the outer ends of the head and tail lamps,
    # as height, half width and position from the body centre.
    centre = (front + rear) / 2
    lamp_front, lamp_rear = headlamp(0.82, 0.5), taillamp(0.8, 0.5)
    print('INDICATORS', lamp_front[2], lamp_rear[2], lamp_front[0], lamp_rear[0],
          lamp_front[1] - centre, lamp_rear[1] - centre)
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        print('PART', obj.name, len(obj.data.polygons))


if __name__ == '__main__':
    main()
