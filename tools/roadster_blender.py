"""Blender script: model the 2028 Tesla Roadster style flying hypercar and export glTF.

Started by tools/build_roadster_model.py, never on its own:
    blender --background --factory-startup --python tools/roadster_blender.py -- OUT.glb

Follows the October 2026 reveal: a crisp wedge whose character line runs from
the nose light bar over the front wheel well to a broad Kamm tail, hidden corner
headlamps, a cab-forward T-top canopy with gold tinted glass around a
body-colour spine, camera winglets instead of mirrors, barge boards and black
aero fences, a pop-up tail wing with stabilisers, four suction fans under the
rear and the Rocket trim's ten cold gas thrusters (four rear, one behind each
wheel pointing down, two sideways at the nose). Wheelbase 2.825 m and width
2.0 m are published; length and height are estimates. No badges or logos.

Car space and export contract follow tools/sahin_blender.py; the profile and
conforming-panel helpers come from tools/model3_blender.py. Sections are
polygons with fixed points per edge, so the crease and chamfers stay sharp.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sahin_blender import MATERIALS, P, bake, box, cut, lathe, loft, material, rounded_rect, spaced, sweep  # noqa: E402
from model3_blender import Profile, at_length, blend, lengths_of, mirror, panel, resample  # noqa: E402

OUT = sys.argv[sys.argv.index('--') + 1]
FRONT, REAR = 2.30, -2.25
FRONT_AXLE, REAR_AXLE, TRACK = 1.40, -1.425, 0.855
WHEEL_RADIUS, TYRE_WIDTH, RIM_RADIUS = 0.355, 0.275, 0.267
COWL, HEADER, ROOF_END, DECK = 0.95, 0.12, -0.60, -1.30
PLATE_TEXT = '34 RDS 28'
# Points per polygon edge: bottom, rocker bevel, lower side, crease, upper side, shoulder, deck.
SEGMENTS = (6, 2, 5, 1, 5, 2, 9)
# Rocket trim nozzles: (u, v, w) of each nozzle centre.
LIFT = [(side * 0.70, axle - 0.50, 0.118) for axle in (FRONT_AXLE, REAR_AXLE) for side in (1, -1)]
BOOST = [(u, REAR + 0.004, 0.70) for u in (0.70, 0.55, -0.55, -0.70)]
YAW = [(side * 0.965, 1.95, 0.43) for side in (1, -1)]


# Profiles --------------------------------------------------------------------

TOP = Profile([((FRONT, 0.40), (0, 1), 0, 0.025), ((2.25, 0.44), (-1, 0.30), 0.03, 0.4),
               ((COWL, 0.82), (-1, 0.12), 0.35, 0.5), ((DECK, 0.935), (-1, 0.02), 0.6, 0.25),
               ((-2.12, 0.955), (-1, 0.0), 0.25, 0.05), ((REAR, 0.60), (0, -1), 0.22, 0)])
BOTTOM = Profile([((FRONT, 0.40), (-0.2, -1), 0, 0.08), ((2.18, 0.15), (-1, 0), 0.07, 0.25),
                  ((1.70, 0.12), (-1, 0), 0.25, 1.0), ((-1.55, 0.12), (-1, 0), 1.0, 0.2),
                  ((-2.14, 0.30), (-1, 0.45), 0.15, 0.06), ((REAR, 0.60), (0, 1), 0.2, 0)])
PLAN = Profile([((FRONT, 0.80), (-0.35, 1), 0, 0.10), ((2.02, 0.975), (-1, 0.04), 0.14, 0.2),
                ((1.70, 0.99), (-1, 0), 0.2, 1.2), ((-1.95, 0.99), (-1, 0), 1.2, 0.12),
                ((REAR, 0.90), (-0.25, -1), 0.08, 0)])
# Canopy centre line: raked windscreen, T-top roof, short rear glass onto the deck.
ROOF = Profile([((COWL + 0.012, 0.815), (-1, 0.38), 0, 0.30), ((HEADER, 1.10), (-1, 0.08), 0.25, 0.2),
                ((-0.25, 1.125), (-1, 0), 0.2, 0.2), ((ROOF_END, 1.10), (-1, -0.15), 0.2, 0.25),
                ((DECK, 0.94), (-1, -0.30), 0.25, 0)])


def crease(v):
    """Character line: from the nose light bar, rising across the front wheel well to the tail."""
    return 0.40 + (FRONT - v) / (FRONT - REAR) * 0.42


def fender(v):
    """Front fender crowns rise above the bonnet valley to cover the front wheels."""
    return min(0.46 + (2.25 - v) * 0.40, 0.80 + (1.40 - v) * 0.044) if COWL < v < 2.25 else 0.0


def body_polygon(v):
    """Right half from the bottom centre to the top centre; chamfers shrink on thin end sections."""
    b, t, hw = BOTTOM(v), TOP(v), PLAN(v)
    s = max(t, fender(v))
    k = min(1.0, (t - b) / 0.5)
    c = min(max(crease(v), b + 0.10 * k + 0.004), s - 0.07 * k - 0.004)
    return [(0.0, b), (hw - 0.10 * k, b), (hw - 0.03 * k, b + 0.06 * k), (hw, c - 0.04 * k),
            (hw + 0.008 * k, c), (hw - 0.08 * k, s - 0.045 * k), (hw - 0.17 * k, s - 0.004 * k), (0.0, t)]


def body_loop(v):
    poly = body_polygon(v)
    right = []
    for (p0, p1), count in zip(zip(poly, poly[1:]), SEGMENTS):
        right += [(p0[0] + (p1[0] - p0[0]) * k / count, p0[1] + (p1[1] - p0[1]) * k / count) for k in range(count)]
    right.append(poly[-1])
    return right + [(-u, w) for u, w in reversed(right[1:-1])]


def side_u(v, w):
    """Half width of the outer surface at height w (the outer chain is monotonic in w)."""
    chain = body_polygon(v)[1:]
    for (u0, w0), (u1, w1) in zip(chain, chain[1:]):
        if w1 > w0 and w0 <= w <= w1:
            return u0 + (u1 - u0) * (w - w0) / (w1 - w0)
    return 0.0


def deck_w(v, u):
    """Height of the upper surface at half width u (crease to centre, monotonic in u)."""
    chain = body_polygon(v)[4:]
    u = abs(u)
    for (u0, w0), (u1, w1) in zip(chain, chain[1:]):
        if u1 <= u <= u0 and u0 > u1:
            return w0 + (w1 - w0) * (u0 - u) / (u0 - u1)
    return chain[-1][1] if u < chain[-1][0] + 1e-9 else chain[0][1]


def inside_body(u, v, w):
    if not REAR < v < FRONT:
        return False
    return BOTTOM(v) < w < TOP(v) and abs(u) < side_u(v, w)


def radial(centre, sign, angle, w):
    """Body surface hit by a horizontal ray from (0, centre, w); sign 1 front, -1 rear."""
    du, dv = math.sin(angle), sign * math.cos(angle)
    lo, hi = 0.0, 3.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if inside_body(du * mid, centre + dv * mid, w) else (lo, mid)
    return du * lo, centre + dv * lo, w


def side_point(v, w, side=1):
    return side * side_u(v, w), v, w


def top_point(u, v):
    return u, v, deck_w(v, u)


# Canopy ------------------------------------------------------------------------

def glass_base(v):
    return 0.74 - 0.08 * blend(v, 0.70, COWL) - 0.12 * blend(v, -0.85, DECK)


def cabin_frame(v):
    he = glass_base(v)
    e = deck_w(v, he)
    roof = ROOF(v)
    crown = min(0.04, 0.5 * max(roof - e, 0.0))
    rail = roof - crown
    return he, e, he - 0.55 * (rail - e), rail, roof


def cabin_curve(v, samples=40):
    he, e, hr, rail, roof = cabin_frame(v)
    points = [(he, e), (hr, rail)]
    for k in range(1, samples + 1):
        a = math.pi / 2 * k / samples
        points.append((hr * max(math.cos(a), 0.0) ** (2 / 2.6), rail + (roof - rail) * math.sin(a) ** (2 / 2.6)))
    return points


def cabin_rail(v):
    he, e, hr, rail, _ = cabin_frame(v)
    return math.hypot(he - hr, rail - e)


def cabin_span(v):
    return lengths_of(cabin_curve(v))[-1]


def cabin_at(v, d, side=1):
    points = cabin_curve(v)
    u, w = at_length(points, lengths_of(points), d)
    return side * u, v, w


def cabin_reach(v, u):
    points = cabin_curve(v)
    lengths = lengths_of(points)
    for i in range(1, len(points)):
        if points[i][0] <= u:
            u0, u1 = points[i - 1][0], points[i][0]
            f = 0.0 if abs(u0 - u1) < 1e-12 else (u0 - u) / (u0 - u1)
            return lengths[i - 1] + (lengths[i] - lengths[i - 1]) * f
    return lengths[-1]


def cabin_loop(v, count=24):
    he, e, _, _, _ = cabin_frame(v)
    curve = resample(cabin_curve(v), count)
    right = [(he, e - 0.05)] + curve[:-1]
    return [(0.0, e - 0.05)] + right + [curve[-1]] + [(-u, w) for u, w in reversed(right)]


# Materials -------------------------------------------------------------------

def create_materials():
    MATERIALS.clear()
    for name, color, metal, rough in [
            ('Paint', (0.86, 0.87, 0.88), 0.1, 0.3), ('Glass', (0.25, 0.18, 0.05), 0.8, 0.06),
            ('GlossBlack', (0.01, 0.01, 0.012), 0.0, 0.12), ('Trim', (0.015, 0.015, 0.017), 0.0, 0.6),
            ('Under', (0.01, 0.01, 0.01), 0.0, 0.9), ('LampDark', (0.04, 0.045, 0.05), 0.6, 0.15),
            ('Headlight', (0.9, 0.92, 0.95), 0.0, 0.1), ('TailLight', (0.45, 0.02, 0.03), 0.0, 0.2),
            ('Signal', (0.85, 0.42, 0.05), 0.0, 0.2), ('Fan', (0.05, 0.055, 0.06), 0.7, 0.3),
            ('Thruster', (0.1, 0.11, 0.12), 0.9, 0.25), ('Wing', (0.86, 0.87, 0.88), 0.1, 0.3),
            ('Plate', (0.92, 0.92, 0.9), 0.0, 0.5), ('PlateText', (0.01, 0.01, 0.01), 0.0, 0.5),
            ('PlateBand', (0.05, 0.18, 0.6), 0.0, 0.5), ('Interior', (0.03, 0.03, 0.035), 0.0, 0.8),
            ('Tyre', (0.02, 0.02, 0.02), 0.0, 0.85), ('Rim', (0.03, 0.03, 0.035), 0.4, 0.5),
            ('Aero', (0.08, 0.085, 0.09), 0.7, 0.3), ('AeroAccent', (0.5, 0.52, 0.55), 0.9, 0.25),
            ('Cap', (0.01, 0.01, 0.012), 0.0, 0.2)]:
        material(name, color, metal, rough)


# Body and canopy ---------------------------------------------------------------

def build_body():
    ends = (0.003, 0.008, 0.015, 0.025, 0.04, 0.06, 0.09)
    stations = spaced(FRONT - 0.0005, REAR + 0.0005, 0.032,
                      dense_ends=[FRONT - d for d in ends] + [REAR + d for d in ends])
    shell = loft('Shell', [(v, body_loop(v)) for v in stations], 'Paint')
    wells = []
    for axle in (FRONT_AXLE, REAR_AXLE):
        for side in (-1, 1):
            well = lathe('Well', 'Under', [(side * 0.60, 0.0), (side * 0.60, 0.395), (side * 1.3, 0.395), (side * 1.3, 0.0)], 48)
            well.location = P(0, axle, WHEEL_RADIUS + 0.005)
            wells.append(well)
    cut(shell, wells, 'WellCut')
    stations = spaced(COWL + 0.012, DECK + 0.004, 0.04, dense_ends=[COWL + 0.008, COWL, DECK + 0.012, DECK + 0.025])
    canopy = loft('Canopy', [(v, cabin_loop(v)) for v in stations], 'Glass')
    return [shell, canopy]


def canopy_trim():
    """Gloss black A pillars; white header, rails, T-top spine, rear bar and buttresses."""
    parts = []
    for side in (1, -1):
        def a_pillar(s, t, side=side):
            v = COWL + 0.01 + (HEADER - 0.012 - COWL - 0.01) * s
            rail = cabin_rail(v)
            low = max(rail - 0.035, 0.0)
            return cabin_at(v, low + (rail + 0.05 - low) * t, side)
        parts.append(panel('APillar', 'GlossBlack', a_pillar, 36, 5))

        def header(s, t, side=side):
            v = HEADER - 0.012 - 0.06 * s
            rail = cabin_rail(v)
            return cabin_at(v, rail - 0.03 + (cabin_span(v) - rail + 0.03) * t, side)
        parts.append(panel('Header', 'Paint', header, 3, 14))

        def roof_rail(s, t, side=side):
            v = HEADER - 0.072 + (ROOF_END - HEADER + 0.072) * s
            rail = cabin_rail(v)
            return cabin_at(v, rail - 0.025 + 0.075 * t, side)
        parts.append(panel('Rail', 'Paint', roof_rail, 22, 3, 0.0045))

        def spine(s, t, side=side):
            v = HEADER - 0.072 + (ROOF_END - HEADER + 0.072) * s
            span = cabin_span(v)
            return cabin_at(v, span - 0.11 + 0.11 * t, side)
        parts.append(panel('Spine', 'Paint', spine, 22, 3))

        def rear_bar(s, t, side=side):
            v = ROOF_END - 0.06 * s
            rail = cabin_rail(v)
            return cabin_at(v, rail - 0.03 + (cabin_span(v) - rail + 0.03) * t, side)
        parts.append(panel('RearBar', 'Paint', rear_bar, 3, 14))

        def buttress(s, t, side=side):
            front = -0.66 + 0.06 * t
            v = front + (DECK + 0.006 - front) * s
            glass = 0.50 + (cabin_frame(ROOF_END)[2] - 0.05 - 0.50) * blend(v, DECK, ROOF_END)
            return cabin_at(v, cabin_reach(v, glass) * t, side)
        parts.append(panel('Buttress', 'Paint', buttress, 22, 12))

        def belt(s, t, side=side):
            v = COWL - 0.05 + (-0.64 - COWL + 0.05) * s
            return cabin_at(v, 0.014 * t, side)
        parts.append(panel('Belt', 'GlossBlack', belt, 40, 1, 0.0045))
    return parts


def lamps():
    parts = []

    def drl(s, t):
        return radial(1.5, 1, math.radians(52) * (2 * s - 1), 0.372 + 0.016 * t)
    parts.append(panel('DRL', 'Headlight', drl, 48, 1, 0.005))

    def tail(s, t):
        return radial(-1.5, -1, math.radians(63) * (2 * s - 1), 0.905 + 0.017 * t)
    parts.append(panel('TailBar', 'TailLight', tail, 56, 1, 0.005))
    for side in (1, -1):
        def corner(s, t, side=side):
            # Triangular corner panel, folded down to show the jewel lamp.
            low = 0.255 + 0.06 * s
            return mirror(radial(1.5, 1, math.radians(54 + 10 * s), low + (0.355 - low) * t), side)
        parts.append(panel('Headlamp', 'LampDark', corner, 10, 4))

        def jewel(s, t, side=side):
            a, r = 2 * math.pi * s, 0.018 * t
            return mirror(radial(1.5, 1, math.radians(58) + r * math.cos(a) / 0.95, 0.318 + r * math.sin(a)), side)
        parts.append(panel('Jewel', 'Headlight', jewel, 16, 1, 0.0055))
        # Rear thruster nozzles on the tail and sideways yaw nozzles on the nose.
        for u, v, w in BOOST:
            if u * side > 0:
                parts.append(panel('Boost', 'Thruster', disc(u, w, 0.034, -1), 18, 2, 0.005))
        u, v, w = YAW[0 if side > 0 else 1]

        def yaw(s, t, side=side, v=v, w=w):
            a, r = 2 * math.pi * s, 0.03 * t
            return side_point(v + r * math.cos(a), w + r * math.sin(a), side)
        parts.append(panel('Yaw', 'Thruster', yaw, 18, 2, 0.004))
    # Four suction fans under the rear bumper.
    for u in (-0.62, -0.22, 0.22, 0.62):
        parts.append(panel('Fan', 'Fan', disc(u, 0.40, 0.088, -1), 24, 3, 0.004))
        parts.append(panel('FanHub', 'Trim', disc(u, 0.40, 0.03, -1), 16, 1, 0.006))
    for u, v, w in LIFT:
        nozzle = lathe('Lift', 'Thruster', [(0.0, 0.0), (0.0, 0.036), (0.012, 0.036), (0.012, 0.0)], 20)
        nozzle.rotation_euler = (0, math.pi / 2, 0)
        nozzle.location = P(u, v, w - 0.004)
        parts.append(nozzle)
    return parts


def disc(u, w, radius, sign):
    """Round panel centred at (u, w) on the nose (sign 1) or tail (sign -1) face."""
    centre = 1.5 * sign
    reach = abs(radial(centre, sign, 0, w)[1] - centre)

    def surface(s, t):
        a = 2 * math.pi * s
        x, y = u + radius * t * math.cos(a), w + radius * t * math.sin(a)
        return radial(centre, sign, math.atan2(x, reach), y)
    return surface


def aero_details():
    """Shut lines, hood vent, aero fences, barge boards and camera winglets."""
    parts = []
    width = 0.0045
    for side in (1, -1):
        for v in (0.92, -0.78):
            top = cabin_frame(v)[1] - 0.012
            parts.append(panel('Gap', 'Trim', lambda s, t, v=v, top=top, side=side:
                               side_point(v + width * (t - 0.5), 0.22 + (top - 0.22) * s, side), 20, 1, 0.0025))
        parts.append(panel('Sill', 'Trim', lambda s, t, side=side:
                           side_point(0.92 + (-0.78 - 0.92) * s, 0.22 + width * (t - 0.5), side), 50, 1, 0.0025))
        parts.append(panel('Fence', 'Trim', lambda s, t, side=side:
                           side_point(1.0 + (-1.02 - 1.0) * s, 0.125 + 0.07 * t, side), 50, 2, 0.003))
        parts.append(box('BargeBoard', 'Trim', (side * 1.006, 0.86, 0.36), (0.014, 0.12, 0.26), bevel=0.004))
        parts.append(box('Winglet', 'Trim', (side * 0.86, 0.97, 0.80), (0.10, 0.07, 0.035), bevel=0.01))
        parts.append(box('Repeater', 'Signal', (side * 0.905, 0.97, 0.80), (0.012, 0.045, 0.012)))
        parts.append(panel('Bonnet', 'Trim', lambda s, t, side=side:
                           top_point(side * (0.70 + width * (t - 0.5)), 1.02 + (2.10 - 1.02) * s), 30, 1, 0.0025))
    parts.append(panel('BonnetFront', 'Trim', lambda s, t: top_point(0.70 * (2 * s - 1), 2.10 + width * (t - 0.5)), 24, 1, 0.0025))
    parts.append(panel('HoodVent', 'Trim', lambda s, t: top_point(0.42 * (2 * s - 1), 1.04 + 0.16 * t), 16, 3, 0.003))
    return parts


def wing():
    """Tail section that pops up as the active wing; the stabiliser fins hide in the body when flush."""
    parts = [panel('WingPlate', 'Wing', lambda s, t: top_point(0.80 * (2 * s - 1), -1.86 + (-2.10 + 1.86) * t), 24, 6, 0.006)]
    for side in (1, -1):
        w = deck_w(-1.98, 0.80)
        parts.append(box('WingFin', 'Wing', (side * 0.80, -1.98, w - 0.125), (0.014, 0.24, 0.24), bevel=0.005))
    return parts


def plate():
    rear = radial(-1.5, -1, 0, 0.60)[1]
    parts = [box('Bracket', 'Trim', (0, rear + 0.01, 0.60), (0.53, 0.03, 0.12)),
             box('Plate', 'Plate', (0, rear - 0.008, 0.60), (0.52, 0.006, 0.112), bevel=0.003),
             box('PlateBand', 'PlateBand', (0.236, rear - 0.0115, 0.60), (0.042, 0.002, 0.106))]
    curve = bpy.data.curves.new('PlateText', 'FONT')
    curve.body = PLATE_TEXT
    curve.size, curve.extrude = 0.07, 0.0012
    curve.align_x, curve.align_y = 'CENTER', 'CENTER'
    curve.space_character = 1.02
    text = bpy.data.objects.new('PlateText', curve)
    bpy.context.scene.collection.objects.link(text)
    text.data.materials.append(MATERIALS['PlateText'])
    text.rotation_euler = (math.pi / 2, 0, math.pi)
    text.location = P(-0.02, rear - 0.0125, 0.598)
    parts.append(text)
    return parts


def interior():
    """Two seats moulded into the tub, a yoke and a slim dashboard."""
    parts = []
    for side in (1, -1):
        seat = box('Seat', 'Interior', (0, 0, 0), (0.46, 0.11, 0.52), bevel=0.06)
        seat.rotation_euler, seat.location = (math.radians(-24), 0, 0), P(side * 0.36, -0.42, 0.78)
        parts.append(seat)
    parts.append(box('Dashboard', 'Interior', (0, 0.62, 0.79), (1.3, 0.34, 0.12), bevel=0.04))
    for dx in (-0.13, 0.13):
        grip = box('YokeGrip', 'Interior', (0, 0, 0), (0.035, 0.035, 0.16), bevel=0.012)
        grip.rotation_euler, grip.location = (math.radians(-28), 0, 0), P(0.36 + dx, 0.36, 0.84)
        parts.append(grip)
    yoke = box('YokeBar', 'Interior', (0, 0, 0), (0.30, 0.03, 0.035), bevel=0.01)
    yoke.rotation_euler, yoke.location = (math.radians(-28), 0, 0), P(0.36, 0.38, 0.79)
    parts.append(yoke)
    return parts


def wheel_parts():
    w, r = TYRE_WIDTH / 2, WHEEL_RADIUS
    profile = [(-w + 0.008, RIM_RADIUS - 0.004), (-w, RIM_RADIUS + 0.014), (-w - 0.004, 0.31), (-w, 0.33),
               (-w + 0.016, 0.345), (-w + 0.036, r - 0.002)]
    tread = [(-w + 0.04 + k * (2 * w - 0.08) / 10, r - (0.006 if k in (2, 5, 8) else 0.0)) for k in range(11)]
    profile += tread + [(w - 0.036, r - 0.002), (w - 0.016, 0.345), (w, 0.33), (w + 0.004, 0.31),
                        (w, RIM_RADIUS + 0.014), (w - 0.008, RIM_RADIUS - 0.004)]
    parts = [lathe('WheelTyre', 'Tyre', profile, 64),
             lathe('WheelRim', 'Rim', [(-w + 0.01, 0.0), (-w + 0.01, RIM_RADIUS), (w - 0.01, RIM_RADIUS), (w - 0.01, 0.0)], 56)]
    for side in (-1, 1):
        # Aero cover: deep dish, a bright lip and seven swept turbine blades.
        dish = [(side * (w - 0.006), RIM_RADIUS), (side * (w + 0.008), RIM_RADIUS - 0.008), (side * (w + 0.012), 0.23),
                (side * (w + 0.006), 0.18), (side * (w + 0.016), 0.10), (side * (w + 0.024), 0.04), (side * (w + 0.026), 0.0)]
        parts.append(lathe('WheelAero', 'Aero', dish, 64))
        parts.append(lathe('WheelLip', 'AeroAccent', [(side * (w + 0.004), RIM_RADIUS - 0.002), (side * (w + 0.014), RIM_RADIUS - 0.012),
                                                      (side * (w + 0.014), RIM_RADIUS - 0.022), (side * (w + 0.004), RIM_RADIUS - 0.03)], 64))
        for k in range(7):
            path = []
            for j in range(6):
                f = j / 5
                radius = 0.055 + 0.17 * f
                a = 2 * math.pi * k / 7 + side * 0.7 * f
                x = side * (w + 0.026 - 0.014 * f)
                path.append((x, radius * math.cos(a), radius * math.sin(a)))
            # Wheel parts are built in Blender axes; sweep() expects car space.
            parts.append(sweep('WheelBlade', 'AeroAccent', rounded_rect(0.02, 0.008, 0.003),
                               [(x, -y, z) for x, y, z in path], up=Vector((1, 0, 0))))
        parts.append(lathe('WheelCap', 'Cap', [(side * (w + 0.024), 0.05), (side * (w + 0.031), 0.044),
                                               (side * (w + 0.034), 0.02), (side * (w + 0.035), 0.0)], 32))
    return parts


# Assembly and export ---------------------------------------------------------

def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create_materials()
    car = build_body() + canopy_trim() + lamps() + aero_details() + wing() + plate() + interior()
    pieces = bake([o for o in car if o.visible_get()])
    wheel = bake(wheel_parts())
    # Mesh data shares the object name so Balsam writes the same mesh files on
    # every run and platform.
    for prefix, group in (('Roadster', pieces), ('RoadsterWheel', wheel)):
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
    print('BOUNDS', rear, front, max(PLAN(v) for v in (0.0, 1.0, -1.0)), max(p.z for p in body_points))
    print('WHEELS', FRONT_AXLE, REAR_AXLE, TRACK, WHEEL_RADIUS)
    centre = (front + rear) / 2
    lamp_front, lamp_rear = radial(1.5, 1, math.radians(60), 0.31), radial(-1.5, -1, math.radians(60), 0.913)
    print('INDICATORS', lamp_front[2], lamp_rear[2], lamp_front[0], lamp_rear[0],
          lamp_front[1] - centre, lamp_rear[1] - centre)
    for name, nozzles in (('LIFT', LIFT), ('BOOST', BOOST), ('YAW', YAW)):
        print(name, ' '.join(f'{u:.3f},{w:.3f},{v:.3f}' for u, v, w in nozzles))
    print('WING', deck_w(-1.98, 0.0))
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        print('PART', obj.name, len(obj.data.polygons))


if __name__ == '__main__':
    main()
