"""Blender script: model the boxy 1980s Turkish saloon (Şahin style) and export glTF.

Started by tools/build_sahin_model.py, never on its own:
    blender --background --factory-startup --python tools/sahin_blender.py -- OUT.glb

Proportions follow the real car: 4.26 m long, 1.65 m wide, 1.39 m tall,
2.49 m wheelbase, 165/80 R13 tyres. No badges or logos are modelled.

Car space used below: u toward the car's left, v forward, w up. Blender's -Y is
the car's front, so the glTF export (+Y up) faces +Z like the other Studio cars.
Every exported object carries one material and is named after it; the wheel is
exported once, centred on its axle, and instanced four times by the wrapper.
"""
import math
import sys

import bmesh
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index('--') + 1]
FRONT_AXLE, REAR_AXLE, TRACK = 1.35, -1.14, 0.69
WHEEL_RADIUS, TYRE_WIDTH = 0.297, 0.165
SCREEN, ROOF_FRONT, ROOF_REAR, BACKLIGHT, ROOF_Y = 0.80, 0.27, -0.57, -1.02, 1.395
PLATE_TEXT = '34 STM 32'


def P(u, v, w):
    return Vector((u, -v, w))


def lerp_table(table, x):
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 >= x >= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[0][1] if x > table[0][0] else table[-1][1]


TOP = [(2.16, 0.70), (2.15, 0.725), (2.13, 0.748), (2.10, 0.765), (1.95, 0.795), (1.30, 0.855), (SCREEN, 0.9),
       (BACKLIGHT, 0.945), (-1.95, 0.935), (-2.09, 0.912), (-2.13, 0.89), (-2.16, 0.85)]


def top(v):
    return lerp_table(TOP, v)


def half_width(v):
    if v > 1.85:
        return 0.825 - ((v - 1.85) / 0.31) ** 2 * 0.045
    if v < -1.85:
        return 0.825 - ((-1.85 - v) / 0.31) ** 2 * 0.04
    return 0.825


def bottom(v):
    return 0.215 + max(0.0, abs(v) - 1.98) * 0.55


def roof(v):
    if v > ROOF_FRONT:
        return top(v) + (ROOF_Y - top(SCREEN)) * (SCREEN - v) / (SCREEN - ROOF_FRONT)
    if v < ROOF_REAR:
        return top(v) + (ROOF_Y - top(BACKLIGHT)) * (v - BACKLIGHT) / (ROOF_REAR - BACKLIGHT)
    middle, half = (ROOF_FRONT + ROOF_REAR) / 2, (ROOF_FRONT - ROOF_REAR) / 2
    return ROOF_Y + 0.006 * math.cos((v - middle) / half * math.pi / 2)


def spaced(a, b, step, dense_ends=()):
    count = max(2, int(abs(b - a) / step) + 1)
    values = {round(a + (b - a) * i / (count - 1), 5) for i in range(count)} | set(dense_ends)
    return sorted(values, reverse=a > b)


# Materials -------------------------------------------------------------------

MATERIALS = {}


def material(name, color, metallic=0.0, roughness=0.5):
    if name not in MATERIALS:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1.0)
        mat.metallic = metallic
        mat.roughness = roughness
        MATERIALS[name] = mat
    return MATERIALS[name]


def create_materials():
    MATERIALS.clear()
    for name, color, metal, rough in [
            ('Paint', (0.55, 0.05, 0.05), 0.2, 0.3), ('Glass', (0.02, 0.03, 0.035), 0.0, 0.05),
            ('Trim', (0.015, 0.015, 0.017), 0.0, 0.6), ('Chrome', (0.8, 0.8, 0.82), 1.0, 0.15),
            ('Under', (0.01, 0.01, 0.01), 0.0, 0.9), ('Grille', (0.02, 0.022, 0.025), 0.3, 0.45),
            ('Headlight', (0.9, 0.9, 0.88), 0.0, 0.1), ('Reflector', (0.85, 0.86, 0.88), 1.0, 0.08),
            ('TailLight', (0.5, 0.02, 0.03), 0.0, 0.2), ('Signal', (0.85, 0.42, 0.05), 0.0, 0.2),
            ('Reverse', (0.85, 0.86, 0.85), 0.0, 0.2), ('Plate', (0.92, 0.92, 0.9), 0.0, 0.5),
            ('PlateText', (0.01, 0.01, 0.01), 0.0, 0.5), ('PlateBand', (0.05, 0.18, 0.6), 0.0, 0.5),
            ('Interior', (0.05, 0.05, 0.055), 0.0, 0.85), ('Tyre', (0.02, 0.02, 0.02), 0.0, 0.85),
            ('Hubcap', (0.6, 0.62, 0.64), 0.9, 0.25), ('Rim', (0.03, 0.03, 0.035), 0.4, 0.5)]:
        material(name, color, metal, rough)


def new_object(name, bm, material_name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(MATERIALS[material_name])
    return obj


def orient_outward(bm, centre):
    bm.normal_update()
    for face in bm.faces:
        if face.normal.dot(face.calc_center_median() - centre) < 0:
            face.normal_flip()


# Geometry builders -----------------------------------------------------------

def loft(name, sections, material_name, closed=True):
    """Closed tube through equal-length (u, w) loops at stations v."""
    bm = bmesh.new()
    rings = [[bm.verts.new(P(u, v, w)) for u, w in loop] for v, loop in sections]
    for a, b in zip(rings, rings[1:]):
        for i in range(len(a)):
            j = (i + 1) % len(a)
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if closed:
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_object(name, bm, material_name)


def box(name, material_name, centre, size, bevel=0.0):
    """Axis-aligned box in car space, optionally with rounded edges."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        u, v, w = vert.co.x * size[0], -vert.co.y * size[1], vert.co.z * size[2]
        vert.co = P(centre[0] + u, centre[1] + v, centre[2] + w)
    obj = new_object(name, bm, material_name)
    if bevel:
        mod = obj.modifiers.new('Round', 'BEVEL')
        mod.width, mod.segments, mod.limit_method = bevel, 3, 'NONE'
    return obj


def prism(name, material_name, outline, axis, start, end):
    """Extrude a 2D outline along one car axis ('u', 'v' or 'w')."""
    bm = bmesh.new()

    def point(a, b, c):
        return {'u': P(c, a, b), 'v': P(a, c, b), 'w': P(a, b, c)}[axis]
    near = [bm.verts.new(point(a, b, start)) for a, b in outline]
    far = [bm.verts.new(point(a, b, end)) for a, b in outline]
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        bm.faces.new((near[i], near[j], far[j], far[i]))
    bm.faces.new(near)
    bm.faces.new(far)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_object(name, bm, material_name)


def sweep(name, material_name, section, path, up=Vector((0, 0, 1)), closed=False):
    """Sweep a 2D section (x across, y up) along a 3D path given in car space."""
    bm = bmesh.new()
    points = [P(*p) for p in path]
    rings = []
    for i, point in enumerate(points):
        if closed:
            ahead, behind = points[(i + 1) % len(points)], points[i - 1]
        else:
            ahead, behind = points[min(i + 1, len(points) - 1)], points[max(i - 1, 0)]
        tangent = (ahead - behind).normalized()
        side = tangent.cross(up).normalized()
        lift = side.cross(tangent).normalized()
        rings.append([bm.verts.new(point + side * x + lift * y) for x, y in section])
    pairs = list(zip(rings, rings[1:] + ([rings[0]] if closed else [])))
    for a, b in pairs:
        for i in range(len(section)):
            j = (i + 1) % len(section)
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if not closed:
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_object(name, bm, material_name)


def lathe(name, material_name, profile, segments=48):
    """Revolve [(x, r)] around the X axis (the axle); the profile need not close."""
    bm = bmesh.new()
    rings = []
    for x, r in profile:
        rings.append([bm.verts.new((x, r * math.cos(2 * math.pi * k / segments), r * math.sin(2 * math.pi * k / segments)))
                      for k in range(segments)])
    for a, b in zip(rings, rings[1:]):
        for k in range(segments):
            q = (k + 1) % segments
            bm.faces.new((a[k], a[q], b[q], b[k]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    for face in list(bm.faces):
        if face.calc_area() < 1e-10:
            bm.faces.remove(face)
    if all(edge.is_manifold for edge in bm.edges):
        # Closed solids (wheel-well cutters, rings): end caps must face away
        # from the solid, not from the axle origin.
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    else:
        orient_outward(bm, Vector((0, 0, 0)))
    return new_object(name, bm, material_name)


def rounded_rect(width, height, radius, steps=4):
    points = []
    for cx, cy, start in ((width / 2 - radius, height / 2 - radius, 0), (-width / 2 + radius, height / 2 - radius, 90),
                          (-width / 2 + radius, -height / 2 + radius, 180), (width / 2 - radius, -height / 2 + radius, 270)):
        for k in range(steps + 1):
            a = math.radians(start + 90 * k / steps)
            points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return points


def join(objects, name):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    objects[0].name = name
    return objects[0]


def cut(target, cutters, name):
    """Boolean-subtract the joined cutters; new faces take the cutter's material.

    Applied at once while the cutter is still evaluated: a boolean whose
    operand is hidden from the viewport can read stale geometry later.
    """
    cutter = join(cutters, name)
    mod = target.modifiers.new(name, 'BOOLEAN')
    mod.operation, mod.object, mod.solver = 'DIFFERENCE', cutter, 'EXACT'
    mod.material_mode = 'TRANSFER'
    # Joined cutters overlap (gap lines meet at corners), so let the solver
    # resolve self-intersections instead of assuming disjoint volumes.
    mod.use_self, mod.use_hole_tolerant = True, True
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter)


# Body ------------------------------------------------------------------------

def body_section(v):
    """Closed loop; the side wall and top carry extra points so wheel wells
    and panel gaps cut into well-shaped faces instead of long slivers."""
    hw, t, b = half_width(v), top(v), bottom(v)
    crease = t - 0.11
    wall = [b + 0.1 + (crease - 0.02 - b - 0.1) * k / 7 for k in range(1, 7)]
    edge = hw - 0.095
    right = ([(hw * 0.45, b), (hw - 0.07, b), (hw - 0.015, b + 0.03), (hw, b + 0.1)] + [(hw, w) for w in wall] +
             [(hw, crease - 0.02), (hw + 0.007, crease), (hw - 0.004, crease + 0.02), (hw - 0.022, t - 0.05),
              (hw - 0.048, t - 0.013), (edge, t), (edge * 0.88, t), (edge * 0.6, t), (edge * 0.3, t)])
    return [(0.0, b)] + right + [(0.0, t)] + [(-u, w) for u, w in reversed(right)]


def cabin_section(v, inset=0.0):
    belt = top(v) - 0.05 - inset
    r = max(roof(v), top(v) + 0.025) - inset
    hb, hr = half_width(v) - 0.072 - inset, 0.655 - inset
    right = [(hb, belt), (hr + 0.012, r - 0.05), (hr - 0.012, r - 0.013), (hr - 0.055, r)]
    return right + [(-u, w) for u, w in reversed(right)]


def side_surface(v, w):
    """Half width of the glasshouse side at height w (for glass and trim)."""
    belt, r = top(v) - 0.05, max(roof(v), top(v) + 0.025)
    hb, hr = half_width(v) - 0.072, 0.667
    t = max(0.0, min(1.0, (w - belt) / max(r - 0.05 - belt, 1e-6)))
    return hb + (hr - hb) * t


def window_outline(v0, v1, samples=16):
    """Side window opening (v, w): straight sill, top following the roof line."""
    top_edge = []
    for k in range(samples + 1):
        v = v0 + (v1 - v0) * k / samples
        top_edge.append((v, max(roof(v) - 0.068, top(v) + 0.03)))
    return [(v1, top(v1) + 0.014)] + top_edge[::-1] + [(v0, top(v0) + 0.014)]


def round_edges(obj):
    """Bevel the clean loft before any boolean: bevelling the cut result can
    leave garbage vertices now and then."""
    mod = obj.modifiers.new('Edges', 'BEVEL')
    mod.width, mod.segments, mod.limit_method, mod.angle_limit = 0.006, 2, 'ANGLE', math.radians(40)
    # No hardened (custom) normals: booleans afterwards interpolate them badly.
    mod.harden_normals, mod.miter_outer = False, 'MITER_ARC'
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def build_body():
    stations = spaced(2.16, -2.16, 0.04, dense_ends=[2.155, 2.15, 2.14, 2.13, 2.12, 2.11, -2.11, -2.12, -2.13, -2.14, -2.15, -2.155])
    shell = loft('Shell', [(v, body_section(v)) for v in stations], 'Paint')
    round_edges(shell)
    cabin_stations = spaced(SCREEN, BACKLIGHT, 0.03, dense_ends=[ROOF_FRONT, ROOF_REAR])
    cabin = loft('Cabin', [(v, cabin_section(v)) for v in cabin_stations], 'Paint')
    round_edges(cabin)
    # Hollow it with an explicit inner loft: a clean manifold cavity, unlike a
    # solidify shell that folds over itself where the glasshouse tapers out.
    inner = spaced(SCREEN - 0.05, BACKLIGHT + 0.05, 0.03, dense_ends=[ROOF_FRONT, ROOF_REAR])
    cut(cabin, [loft('Cavity', [(v, cabin_section(v, 0.03)) for v in inner], 'Interior')], 'Hollow')

    # Glass openings: side windows go through both sides of the hollow cabin.
    front_window = window_outline(0.70, -0.045)
    rear_window = window_outline(-0.145, -0.74)
    cutters = [prism('SideFront', 'Trim', front_window, 'u', -1.2, 1.2),
               prism('SideRear', 'Trim', rear_window, 'u', -1.2, 1.2)]
    screen = [(-0.585, top(SCREEN) + 0.035), (0.585, top(SCREEN) + 0.035), (0.548, ROOF_Y - 0.045), (-0.548, ROOF_Y - 0.045)]
    back = [(-0.58, top(BACKLIGHT) + 0.035), (0.58, top(BACKLIGHT) + 0.035), (0.548, ROOF_Y - 0.045), (-0.548, ROOF_Y - 0.045)]
    cutters.append(prism('Screen', 'Trim', screen, 'v', 0.05, 1.0))
    cutters.append(prism('Backlight', 'Trim', back, 'v', -1.45, -0.45))
    cut(cabin, cutters, 'WindowCut')

    # Wheel wells (dark liner), panel gaps and lamp/grille recesses in the shell.
    wells = []
    for axle in (FRONT_AXLE, REAR_AXLE):
        for side in (-1, 1):
            well = lathe('Well', 'Under', [(side * 0.46, 0.0), (side * 0.46, 0.36), (side * 1.2, 0.36), (side * 1.2, 0.0)], 40)
            well.location = P(0, axle, WHEEL_RADIUS + 0.012)
            wells.append(well)
    groove = rounded_rect(0.006, 0.02, 0.0025, 1)
    gaps = []
    hw = 0.825
    for v, low, high in ((0.79, 0.28, top(0.79) - 0.012), (-0.095, 0.26, top(-0.095) - 0.012), (-0.93, 0.27, top(-0.93) - 0.012)):
        for side in (-1, 1):
            gaps.append(sweep('Gap', 'Trim', groove, [(side * hw, v, low), (side * hw, v, (low + high) / 2), (side * hw, v, high)],
                              up=Vector((0, -1, 0))))
    for side in (-1, 1):
        gaps.append(sweep('Sill', 'Trim', groove, [(side * hw, v, 0.272) for v in (0.79, 0.4, 0.0, -0.5, -0.93)],
                          up=Vector((side, 0, 0))))
        # Bonnet and boot lid edges along the top surface.
        gaps.append(sweep('Bonnet', 'Trim', groove, [(side * 0.72, v, top(v)) for v in spaced(2.1, 0.8, 0.1)]))
        gaps.append(sweep('Boot', 'Trim', groove, [(side * 0.72, v, top(v)) for v in spaced(-1.07, -2.08, 0.1)]))
    gaps.append(sweep('BonnetRear', 'Trim', groove, [(u, 0.805, top(0.805)) for u in (-0.72, 0, 0.72)]))
    gaps.append(sweep('BootFront', 'Trim', groove, [(u, -1.07, top(-1.07)) for u in (-0.72, 0, 0.72)]))
    for side in (-1, 1):
        gaps.append(box('LampPocket', 'Trim', (side * 0.552, 2.17, 0.588), (0.37, 0.05, 0.172)))
        gaps.append(box('TailPocket', 'Trim', (side * 0.6, -2.165, 0.702), (0.43, 0.03, 0.182)))
    gaps.append(box('GrillePocket', 'Grille', (0, 2.175, 0.585), (0.68, 0.06, 0.168)))
    gaps.append(box('PlateRecess', 'Trim', (0, -2.165, 0.702), (0.54, 0.024, 0.15)))
    cut(shell, wells + gaps, 'BodyCut')
    # Area-weighted normals keep flat panels flat next to the thin slivers
    # that the cuts leave behind.
    for obj in (shell, cabin):
        mod = obj.modifiers.new('Normals', 'WEIGHTED_NORMAL')
        mod.mode, mod.keep_sharp, mod.weight = 'FACE_AREA', True, 100
    return [shell, cabin], front_window, rear_window


def glass_panes(front_window, rear_window):
    panes = []
    for outline in (front_window, rear_window):
        vs = [v for v, _ in outline]
        v_front, v_back = max(vs) + 0.01, min(vs) - 0.01
        for side in (-1, 1):
            bm = bmesh.new()
            rows = []
            for k in range(13):
                v = v_front + (v_back - v_front) * k / 12
                low = top(v) + 0.005
                high = max(roof(v) - 0.058, low + 0.02)
                rows.append([bm.verts.new(P(side * (side_surface(v, w) - 0.013), v, w)) for w in (low, high)])
            for a, b in zip(rows, rows[1:]):
                bm.faces.new((a[0], a[1], b[1], b[0]))
            orient_outward(bm, P(0, (v_front + v_back) / 2, 1.1))
            panes.append(new_object('SideGlass', bm, 'Glass'))
    for v0, v1 in ((SCREEN - 0.012, ROOF_FRONT - 0.02), (ROOF_REAR + 0.02, BACKLIGHT + 0.012)):
        bm = bmesh.new()
        rows = []
        for k in range(9):
            v = v0 + (v1 - v0) * k / 8
            w = roof(v) - 0.013
            rows.append([bm.verts.new(P(u, v, w)) for u in (-0.6, -0.3, 0.0, 0.3, 0.6)])
        for a, b in zip(rows, rows[1:]):
            for i in range(4):
                bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
        orient_outward(bm, P(0, 0, 0.6))
        panes.append(new_object('ScreenGlass', bm, 'Glass'))
    return panes


def lamps_and_trim():
    parts = []
    for side in (-1, 1):
        u = side * 0.552
        # Headlamp: chrome reflector, clear lens, and a slim chrome bezel.
        parts.append(box('Reflector', 'Reflector', (u, 2.142, 0.588), (0.34, 0.01, 0.15)))
        parts.append(box('Lens', 'Headlight', (u, 2.152, 0.588), (0.33, 0.012, 0.142), bevel=0.004))
        for dw in (-0.081, 0.081):
            parts.append(box('Bezel', 'Chrome', (u, 2.162, 0.588 + dw), (0.36, 0.008, 0.008)))
        parts.append(box('Signal', 'Signal', (side * 0.775, 2.135, 0.588), (0.06, 0.05, 0.13), bevel=0.006))
        parts.append(box('SideRepeater', 'Signal', (side * 0.829, 1.72, 0.66), (0.006, 0.05, 0.022), bevel=0.002))
        # Ribbed rear cluster: stop/tail, indicator and reverse sections.
        for k in range(4):
            w = 0.643 + k * 0.038
            parts.append(box('TailRib', 'TailLight', (side * 0.665, -2.153, w), (0.25, 0.012, 0.03), bevel=0.003))
            parts.append(box('SignalRib', 'Signal', (side * 0.468, -2.153, w), (0.13, 0.012, 0.03), bevel=0.003))
            parts.append(box('ReverseRib', 'Reverse', (side * 0.36, -2.153, w), (0.075, 0.012, 0.03), bevel=0.003))
        parts.append(box('TailFrame', 'Trim', (side * 0.6, -2.148, 0.702), (0.43, 0.006, 0.176)))
    # Grille slats and centre bar between the headlamps.
    for k in range(5):
        parts.append(box('Slat', 'Grille' if k % 2 else 'Chrome', (0, 2.16, 0.528 + k * 0.03), (0.64, 0.012, 0.011), bevel=0.003))
    parts.append(box('GrilleFrame', 'Chrome', (0, 2.163, 0.668), (0.66, 0.008, 0.008)))
    parts.append(box('GrilleFrameLow', 'Chrome', (0, 2.163, 0.503), (0.66, 0.008, 0.008)))
    # Wrap-around black bumpers with a fine upper rub strip.
    bumper = rounded_rect(0.085, 0.16, 0.03)
    for v_tip, sign in ((2.215, 1), (-2.205, -1)):
        path = [(-0.86, v_tip - sign * 0.32, 0.385), (-0.86, v_tip - sign * 0.15, 0.385), (-0.8, v_tip - sign * 0.04, 0.385),
                (-0.6, v_tip, 0.385), (0.0, v_tip + sign * 0.006, 0.385), (0.6, v_tip, 0.385),
                (0.8, v_tip - sign * 0.04, 0.385), (0.86, v_tip - sign * 0.15, 0.385), (0.86, v_tip - sign * 0.32, 0.385)]
        parts.append(sweep('Bumper', 'Trim', bumper, path))
        parts.append(sweep('BumperStrip', 'Grille', rounded_rect(0.012, 0.022, 0.005), [(x, y + sign * 0.043, 0.43) for x, y, _ in path[2:-2]]))
    # Side rubbing strips between the wheel arches.
    strip = rounded_rect(0.014, 0.048, 0.006)
    for side in (-1, 1):
        for v0, v1 in ((1.75, 2.02), (0.95, -0.75), (-1.53, -2.0)):
            parts.append(sweep('RubStrip', 'Trim', strip, [(side * (half_width(v) + 0.006), v, 0.52) for v in spaced(v0, v1, 0.1)],
                               up=Vector((0, 0, 1))))
        # Door handles, mirrors, window sill chrome, B-pillar applique.
        for v in (0.02, -0.82):
            parts.append(box('Handle', 'Trim', (side * 0.83, v, 0.835), (0.016, 0.13, 0.03), bevel=0.006))
        parts.append(box('Mirror', 'Trim', (side * 0.9, 0.62, 1.0), (0.1, 0.07, 0.085), bevel=0.02))
        parts.append(box('MirrorArm', 'Trim', (side * 0.83, 0.64, 0.965), (0.08, 0.05, 0.03), bevel=0.008))
        parts.append(box('MirrorGlass', 'Reflector', (side * 0.905, 0.584, 1.0), (0.08, 0.004, 0.065)))
        parts.append(sweep('SillChrome', 'Chrome', rounded_rect(0.008, 0.012, 0.003),
                           [(side * (side_surface(v, top(v) + 0.012) + 0.004), v, top(v) + 0.012) for v in spaced(0.72, -0.98, 0.08)]))
        parts.append(box('BPillar', 'Trim', (side * (side_surface(-0.095, 1.15) + 0.004), -0.095, 1.15), (0.006, 0.105, 0.38)))
    # Windscreen wipers and a roof antenna.
    for u0 in (0.36, -0.12):
        parts.append(sweep('Wiper', 'Trim', rounded_rect(0.012, 0.012, 0.004),
                           [(u0, SCREEN - 0.03, top(SCREEN) + 0.03), (u0 - 0.2, SCREEN - 0.07, top(SCREEN) + 0.062), (u0 - 0.42, SCREEN - 0.11, top(SCREEN) + 0.095)]))
    parts.append(box('Antenna', 'Trim', (0.0, -0.45, ROOF_Y + 0.11), (0.006, 0.006, 0.22)))
    parts.append(lathe('Exhaust', 'Under', [(0.0, 0.0), (0.0, 0.03), (0.16, 0.03), (0.16, 0.0)], 16))
    parts[-1].rotation_euler = (0, 0, math.pi / 2)
    parts[-1].location = P(-0.45, -2.07, 0.24)
    return parts


def plates():
    parts = []
    for v, sign, w in ((2.262, 1, 0.39), (-2.168, -1, 0.702)):
        parts.append(box('Plate', 'Plate', (0, v, w), (0.52, 0.006, 0.112), bevel=0.003))
        parts.append(box('PlateBand', 'PlateBand', (-0.236, v + sign * 0.0035, w), (0.042, 0.002, 0.106)))
        curve = bpy.data.curves.new('PlateText', 'FONT')
        curve.body = PLATE_TEXT
        curve.size, curve.extrude = 0.072, 0.0012
        curve.align_x, curve.align_y = 'CENTER', 'CENTER'
        curve.space_character = 1.05
        text = bpy.data.objects.new('PlateText', curve)
        bpy.context.scene.collection.objects.link(text)
        text.data.materials.append(MATERIALS['PlateText'])
        text.rotation_euler = (math.pi / 2, 0, 0 if sign > 0 else math.pi)
        text.location = P(0.02, v + sign * 0.0045, w - 0.002)
        parts.append(text)
    return parts


def interior():
    """Only what shows above the solid lower body: seat backs, headrests, dash."""
    parts = []
    for side in (1, -1):
        u = side * 0.36
        parts.append(box('SeatBack', 'Interior', (u, -0.34, 1.0), (0.46, 0.12, 0.36), bevel=0.04))
        parts.append(box('Headrest', 'Interior', (u, -0.37, 1.24), (0.25, 0.09, 0.13), bevel=0.03))
    parts.append(box('RearBench', 'Interior', (0, -0.8, 0.96), (1.26, 0.12, 0.24), bevel=0.04))
    parts.append(box('Shelf', 'Interior', (0, -0.98, top(-0.98) + 0.012), (1.24, 0.14, 0.02)))
    parts.append(box('Dashboard', 'Interior', (0, 0.45, 0.9), (1.28, 0.3, 0.2), bevel=0.04))
    wheel = lathe('SteeringWheel', 'Interior', [(-0.015, 0.165), (0.015, 0.165), (0.015, 0.19), (-0.015, 0.19)], 32)
    wheel.rotation_euler = (math.radians(62), 0, math.pi / 2)
    wheel.location = P(0.36, 0.24, 1.0)
    parts.append(wheel)
    return parts


def wheel_parts():
    w, r = TYRE_WIDTH / 2, WHEEL_RADIUS
    # Tyre: rounded shoulders, sidewall bulge and four circumferential grooves.
    profile = [(-w + 0.004, 0.175), (-w, 0.2), (-w - 0.004, 0.24), (-w, 0.268), (-w + 0.012, 0.287), (-w + 0.03, r - 0.003)]
    tread = []
    for k in range(9):
        x = -w + 0.036 + k * (2 * w - 0.072) / 8
        tread.append((x, r - (0.006 if k in (2, 4, 6) else 0.0)))
    profile += tread + [(w - 0.03, r - 0.003), (w - 0.012, 0.287), (w, 0.268), (w + 0.004, 0.24), (w, 0.2), (w - 0.004, 0.175)]
    parts = [lathe('WheelTyre', 'Tyre', profile, 56)]
    # Steel wheel with a domed hubcap, a raised ring and dark vents.
    parts.append(lathe('WheelRim', 'Rim', [(-w + 0.006, 0.0), (-w + 0.006, 0.178), (w - 0.006, 0.178), (w - 0.006, 0.0)], 48))
    for side in (-1, 1):
        cap = [(side * (w - 0.002), 0.176), (side * (w + 0.008), 0.17), (side * (w + 0.012), 0.15), (side * (w + 0.01), 0.128),
               (side * (w + 0.014), 0.115), (side * (w + 0.018), 0.07), (side * (w + 0.024), 0.035), (side * (w + 0.026), 0.0)]
        parts.append(lathe('WheelHubcap', 'Hubcap', cap, 48))
        for k in range(8):
            a = 2 * math.pi * (k + 0.5) / 8
            vent = box('WheelVent', 'Rim', (0, 0, 0), (0.006, 0.026, 0.012), bevel=0.003)
            vent.location = Vector((side * (w + 0.0125), 0.139 * math.cos(a), 0.139 * math.sin(a)))
            vent.rotation_euler = (a, 0, 0)
            parts.append(vent)
    return parts


# Assembly and export ---------------------------------------------------------

def bake(objects):
    """Apply modifiers and transforms, then split every object by material."""
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.convert(target='MESH')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    merged = join([o for o in bpy.context.selected_objects], 'Merged')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')
    return [o for o in bpy.context.selected_objects]


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    create_materials()
    body, front_window, rear_window = build_body()
    car = body + glass_panes(front_window, rear_window) + lamps_and_trim() + plates() + interior()
    pieces = bake([o for o in car if o.visible_get()])
    wheel = bake(wheel_parts())
    # Mesh data shares the object name so Balsam writes the same mesh files on
    # every run and platform.
    for prefix, group in (('Sahin', pieces), ('SahinWheel', wheel)):
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
    print('BOUNDS', min(-p.y for p in body_points), max(-p.y for p in body_points),
          max(abs(p.x) for p in body_points), max(p.z for p in body_points))
    print('WHEELS', FRONT_AXLE, REAR_AXLE, TRACK, WHEEL_RADIUS)
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        print('PART', obj.name, len(obj.data.polygons))


if __name__ == '__main__':
    main()
