"""Build the boxy 1980s Turkish saloon used as Studio's ego car (Şahin style).

Proportions follow the real car: 4.26 m long, 1.65 m wide, 1.39 m tall,
2.49 m wheelbase, 165/80 R13 tyres. The body is lofted from cross-sections,
details are thin boxes, wheels are lathed. One OBJ object per material is
converted with PySide6 Balsam; the Qt wrapper QML is written here as well.
No badges or logos are modelled.

    .venv/bin/python tools/build_sahin_model.py
"""
from collections import defaultdict
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'device_studio/qml/assets/vehicles/sahin'
FRONT_AXLE, REAR_AXLE, TRACK = 1.35, -1.14, 0.69
WHEEL_RADIUS, TYRE_WIDTH, ARCH = 0.297, 0.165, 0.37


def lerp_table(table, z):
    for (z0, y0), (z1, y1) in zip(table, table[1:]):
        if z0 >= z >= z1:
            return y0 + (y1 - y0) * (z - z0) / (z1 - z0)
    return table[0][1] if z > table[0][0] else table[-1][1]


# Side profile, front (+Z) to rear (-Z).
TOP = [(2.16, 0.70), (2.11, 0.755), (1.95, 0.795), (1.30, 0.855), (0.80, 0.9), (-1.02, 0.945),
       (-1.95, 0.935), (-2.10, 0.905), (-2.16, 0.85)]
# Glasshouse: windscreen base, roof front/rear edges, rear window base, roof height.
SCREEN, ROOF_FRONT, ROOF_REAR, BACKLIGHT, ROOF_Y = 0.80, 0.27, -0.57, -1.02, 1.395


def top(z):
    return lerp_table(TOP, z)


def half_width(z):
    if z > 1.9:
        return 0.825 - (z - 1.9) * 0.14
    if z < -1.9:
        return 0.825 - (-1.9 - z) * 0.12
    return 0.825


def bottom(z):
    return 0.25 + max(0.0, abs(z) - 2.02) * 0.5


def arch(z):
    lift = bottom(z)
    for axle in (FRONT_AXLE, REAR_AXLE):
        d = abs(z - axle)
        if d < ARCH:
            lift = max(lift, WHEEL_RADIUS + math.sqrt(ARCH * ARCH - d * d))
    return lift


def roof(z):
    if z > ROOF_FRONT:
        return top(z) + (ROOF_Y - top(SCREEN)) * (SCREEN - z) / (SCREEN - ROOF_FRONT)
    if z < ROOF_REAR:
        return top(z) + (ROOF_Y - top(BACKLIGHT)) * (z - BACKLIGHT) / (ROOF_REAR - BACKLIGHT)
    middle, half = (ROOF_FRONT + ROOF_REAR) / 2, (ROOF_FRONT - ROOF_REAR) / 2
    return ROOF_Y + 0.006 * math.cos((z - middle) / half * math.pi / 2)


class Mesh:
    def __init__(self):
        self.faces = defaultdict(list)

    def polygon(self, material, points, reference):
        """Add a face wound counter-clockwise when seen from outside `reference`."""
        n = normal(points)
        if n is None:
            return
        centre = [sum(p[i] for p in points) / len(points) for i in range(3)]
        if sum(n[i] * (centre[i] - reference[i]) for i in range(3)) < 0:
            points = points[::-1]
        for i in range(1, len(points) - 1):
            triangle = [points[0], points[i], points[i + 1]]
            if normal(triangle) is not None:
                self.faces[material].append(triangle)

    def box(self, material, centre, size):
        cx, cy, cz = centre
        hx, hy, hz = (s / 2 for s in size)
        corners = [(cx + sx * hx, cy + sy * hy, cz + sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        for axis in range(3):
            for sign in (-1, 1):
                face = [c for c in corners if (c[axis] - centre[axis]) * sign > 0]
                face = sorted(face, key=lambda c: math.atan2(c[(axis + 2) % 3] - centre[(axis + 2) % 3],
                                                           c[(axis + 1) % 3] - centre[(axis + 1) % 3]))
                self.polygon(material, face, centre)

    def loft(self, sections, material, reference):
        """sections: [(z, [(x, y), ...])] with equal point counts, loops closed."""
        for (z0, a), (z1, b) in zip(sections, sections[1:]):
            for i in range(len(a)):
                j = (i + 1) % len(a)
                quad = [(a[i][0], a[i][1], z0), (a[j][0], a[j][1], z0), (b[j][0], b[j][1], z1), (b[i][0], b[i][1], z1)]
                self.polygon(material(i, (z0 + z1) / 2), quad, reference((z0 + z1) / 2, a, b))

    def cap(self, material, z, points, outward):
        centre = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
        for i in range(len(points)):
            j = (i + 1) % len(points)
            self.polygon(material, [(centre[0], centre[1], z), (points[i][0], points[i][1], z), (points[j][0], points[j][1], z)],
                         (centre[0], centre[1], z - outward))

    def lathe(self, material, profile, segments=28):
        """Revolve [(x, r)] around the X axis (the wheel's axle)."""
        for k in range(segments):
            a0, a1 = 2 * math.pi * k / segments, 2 * math.pi * (k + 1) / segments
            for (x0, r0), (x1, r1) in zip(profile, profile[1:]):
                quad = [(x0, r0 * math.cos(a0), r0 * math.sin(a0)), (x1, r1 * math.cos(a0), r1 * math.sin(a0)),
                        (x1, r1 * math.cos(a1), r1 * math.sin(a1)), (x0, r0 * math.cos(a1), r0 * math.sin(a1))]
                if r0 < 1e-6 or r1 < 1e-6:
                    quad = [q for q in quad if abs(q[1]) + abs(q[2]) > 1e-9 or q is quad[0] or q is quad[1]]
                self.polygon(material, quad, (0.0, 0.0, 0.0) if abs(x0 + x1) < 1e-6 else ((x0 + x1) * 0.25, 0.0, 0.0))


def normal(points):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points[0], points[1], points[2]
    ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    length = math.sqrt(sum(c * c for c in n))
    if length < 1e-10 and len(points) > 3:
        return normal(points[1:])
    return None if length < 1e-10 else tuple(c / length for c in n)


def body():
    mesh = Mesh()
    stations = sorted({round(-2.16 + i * 0.04, 4) for i in range(109)} | {2.16, -2.16}, reverse=True)

    def section(z):
        hw, t, base, lift = half_width(z), top(z), bottom(z), arch(z)
        crease = t - 0.1
        right = [(0.0, base), (hw - 0.22, base), (hw - 0.22, lift), (hw - 0.015, lift), (hw, lift + 0.04),
                 (hw, crease), (hw - 0.012, crease + 0.02), (hw - 0.025, t - 0.035), (hw - 0.07, t), (0.0, t)]
        return right + [(-x, y) for x, y in reversed(right[1:-1])]

    sections = [(z, section(z)) for z in stations]

    def lower_material(i, z):
        # 0: floor, 1-2: wheel-well walls, mirrored at the end of the loop.
        count = len(sections[0][1])
        return 'Under' if i in (0, 1, 2, count - 3, count - 2, count - 1) else 'Paint'
    mesh.loft(sections, lower_material, lambda z, a, b: (0.0, (top(z) + bottom(z)) / 2, z))
    mesh.cap('Paint', 2.16, sections[0][1], 1)
    mesh.cap('Paint', -2.16, sections[-1][1], -1)

    cabin = sorted({round(SCREEN - i * 0.04, 4) for i in range(46) if SCREEN - i * 0.04 > BACKLIGHT}
                   | {SCREEN, ROOF_FRONT, -0.02, -0.12, ROOF_REAR, -0.74, BACKLIGHT}, reverse=True)

    def cabin_section(z):
        belt, r = top(z) + 0.004, roof(z)
        hb, hr = half_width(z) - 0.07, 0.655
        r = max(r, belt)
        side_top = belt + (r - belt) * 0.97
        side_w = hb + (hr - hb) * (side_top - belt) / max(r - belt, 1e-6) if r > belt else hb
        right = [(hb, belt), (side_w, side_top), (hr - 0.05, r), (0.0, r)]
        return right + [(-x, y) for x, y in reversed(right[:-1])] + [(0.0, belt)]

    cabin_sections = [(z, cabin_section(z)) for z in cabin]

    def cabin_material(i, z):
        if i in (1, 5):          # roof rails, A and C pillars
            return 'Paint'
        if i in (0, 6):          # side windows, B pillar trim, C pillar
            if -0.12 < z < -0.02:
                return 'Trim'
            return 'Glass' if -0.74 < z < 0.5 else 'Paint'
        if i in (2, 3, 4):       # windscreen, roof, rear window
            return 'Glass' if z > ROOF_FRONT or z < ROOF_REAR else 'Paint'
        return 'Paint'
    mesh.loft(cabin_sections, cabin_material, lambda z, a, b: (0.0, top(z) + 0.2, z))

    box = mesh.box
    # Front: grille with chrome bars between wide rectangular headlamps.
    box('Grille', (0, 0.585, 2.163), (0.62, 0.16, 0.02))
    for y in (0.545, 0.585, 0.625):
        box('Chrome', (0, y, 2.176), (0.6, 0.012, 0.012))
    for side in (-1, 1):
        box('Trim', (side * 0.555, 0.585, 2.156), (0.37, 0.18, 0.02))
        box('Headlight', (side * 0.55, 0.585, 2.166), (0.33, 0.145, 0.02))
        box('Signal', (side * 0.76, 0.585, 2.15), (0.07, 0.13, 0.02))
    # Black plastic bumpers with wrap-around ends and plates.
    for z, sign in ((2.19, 1), (-2.19, -1)):
        box('Trim', (0, 0.385, z), (1.66, 0.15, 0.09))
        for side in (-1, 1):
            box('Trim', (side * 0.79, 0.385, z - sign * 0.14), (0.09, 0.15, 0.24))
        box('Plate', (0, 0.39, z + sign * 0.05), (0.5, 0.11, 0.008))
        box('PlateBand', (-0.225, 0.39, z + sign * 0.055), (0.05, 0.11, 0.006))
    # Rear: horizontal lamp clusters (stop/tail, indicator, reverse).
    box('Trim', (0, 0.70, -2.161), (1.6, 0.2, 0.015))
    for side in (-1, 1):
        box('TailLight', (side * 0.64, 0.70, -2.168), (0.3, 0.165, 0.02))
        box('Signal', (side * 0.445, 0.70, -2.168), (0.08, 0.165, 0.02))
        box('Reverse', (side * 0.365, 0.70, -2.168), (0.07, 0.165, 0.02))
    box('Plate', (0, 0.70, -2.172), (0.5, 0.11, 0.008))
    box('PlateBand', (-0.225, 0.70, -2.177), (0.05, 0.11, 0.006))
    box('Trim', (-0.5, 0.27, -2.15), (0.05, 0.05, 0.14))
    # Sides: rubbing strips between the arches, door shut lines, handles, mirrors, belt chrome.
    for side in (-1, 1):
        for z0, z1 in ((1.74, 2.04), (-0.74, 0.95), (-2.04, -1.54)):
            box('Trim', (side * 0.831, 0.52, (z0 + z1) / 2), (0.014, 0.05, z1 - z0))
        for z in (0.78, -0.08, -0.9):
            box('Shut', (side * 0.827, 0.6, z), (0.006, 0.66, 0.008))
        for z in (0.0, -0.82):
            box('Chrome', (side * 0.83, 0.83, z), (0.012, 0.026, 0.12))
        box('Trim', (side * 0.87, 0.99, 0.64), (0.08, 0.08, 0.13))
        box('Trim', (side * 0.81, 0.95, 0.64), (0.06, 0.03, 0.05))
        box('Chrome', (side * 0.757, 0.951, -0.1), (0.012, 0.01, 1.64))
    return mesh


def wheel():
    mesh = Mesh()
    w, r = TYRE_WIDTH / 2, WHEEL_RADIUS
    tyre = [(-w, 0.18), (-w, 0.25), (-w + 0.01, 0.278), (-w + 0.028, r - 0.004), (-w + 0.045, r),
            (w - 0.045, r), (w - 0.028, r - 0.004), (w - 0.01, 0.278), (w, 0.25), (w, 0.18)]
    mesh.lathe('Tyre', tyre)
    for side in (-1, 1):
        cap = [(side * (w + 0.002), 0.182), (side * (w + 0.012), 0.16), (side * (w + 0.016), 0.11),
               (side * (w + 0.02), 0.05), (side * (w + 0.022), 0.0)]
        mesh.lathe('Hubcap', cap)
        mesh.lathe('Tyre', [(side * (w - 0.002), 0.0), (side * (w - 0.002), 0.18)])
    return mesh


def write_obj(path, mesh, prefix):
    vertices, lines = [], []
    for material, faces in mesh.faces.items():
        # Smooth across faces within 38° that share a position; hard edges elsewhere.
        by_position = defaultdict(list)
        face_normals = [normal(f) for f in faces]
        for index, face in enumerate(faces):
            for p in face:
                by_position[tuple(round(c, 5) for c in p)].append(index)
        lines.append(f'o {prefix}{material}')
        for index, face in enumerate(faces):
            n0 = face_normals[index]
            refs = []
            for p in face:
                acc = [0.0, 0.0, 0.0]
                for other in by_position[tuple(round(c, 5) for c in p)]:
                    n1 = face_normals[other]
                    if sum(a * b for a, b in zip(n0, n1)) > math.cos(math.radians(38)):
                        acc = [a + b for a, b in zip(acc, n1)]
                length = math.sqrt(sum(c * c for c in acc)) or 1.0
                vertices.append((p, tuple(c / length for c in acc)))
                refs.append(len(vertices))
            lines.append('f ' + ' '.join(f'{i}//{i}' for i in refs))
    text = [f'v {p[0]:.5f} {p[1]:.5f} {p[2]:.5f}' for p, _ in vertices]
    text += [f'vn {n[0]:.5f} {n[1]:.5f} {n[2]:.5f}' for _, n in vertices]
    path.write_text('\n'.join(text + lines) + '\n')


QML = '''pragma ComponentBehavior: Bound
import QtQuick
import QtQuick3D

// Generated by tools/build_sahin_model.py: boxy 1980s Turkish saloon, metres,
// +Z forward, ground at y = 0. Same contract as the Balsam-imported cars.
Node {
    id: root
    property color paint: "#b5221f"
    property real metallic: 0.15
    property bool braking: false
    property real lamps: 0.35
    property real wheelAngle: 0
    // Positive pitch dives the nose; positive roll leans toward the car's right.
    property real bodyPitch: 0
    property real bodyRoll: 0

    PrincipledMaterial {
        id: paintMaterial
        baseColor: root.paint
        metalness: root.metallic
        roughness: 0.4 - root.metallic * 0.12
        clearcoatAmount: 1
        clearcoatRoughnessAmount: 0.06
    }
    PrincipledMaterial { id: trimMaterial; baseColor: "#17181a"; roughness: 0.62 }
    PrincipledMaterial { id: underMaterial; baseColor: "#0d0e0f"; roughness: 0.9 }
    PrincipledMaterial { id: shutMaterial; baseColor: "#060606"; roughness: 0.9 }
    PrincipledMaterial { id: chromeMaterial; baseColor: "#d6dadd"; metalness: 1; roughness: 0.16 }
    PrincipledMaterial { id: grilleMaterial; baseColor: "#1d2023"; metalness: 0.4; roughness: 0.45 }
    PrincipledMaterial {
        id: glassMaterial
        baseColor: "#0e171d"; roughness: 0.04; metalness: 0; specularAmount: 1
        clearcoatAmount: 1; clearcoatRoughnessAmount: 0.02
    }
    PrincipledMaterial {
        id: headlightMaterial
        baseColor: "#eef1ee"; roughness: 0.12; metalness: 0.3
        emissiveFactor: Qt.vector3d(root.lamps * 2.4, root.lamps * 2.35, root.lamps * 2.2)
    }
    PrincipledMaterial {
        id: tailMaterial
        baseColor: root.braking ? "#ff3340" : "#6e0d14"; roughness: 0.25
        emissiveFactor: root.braking ? Qt.vector3d(5.5, 0.18, 0.14) : Qt.vector3d(root.lamps * 0.3, 0.005, 0.005)
    }
    PrincipledMaterial { id: signalMaterial; baseColor: "#e48a1c"; roughness: 0.25; emissiveFactor: Qt.vector3d(0.12, 0.05, 0) }
    PrincipledMaterial { id: reverseMaterial; baseColor: "#e9ecea"; roughness: 0.2 }
    PrincipledMaterial { id: plateMaterial; baseColor: "#f4f4ef"; roughness: 0.5 }
    PrincipledMaterial { id: plateBandMaterial; baseColor: "#1f4fa8"; roughness: 0.5 }
    PrincipledMaterial { id: tyreMaterial; baseColor: "#141515"; roughness: 0.88 }
    PrincipledMaterial { id: hubcapMaterial; baseColor: "#c5cacd"; metalness: 0.9; roughness: 0.28 }

    Node {
        // The body rotates around its suspension centre; wheels stay on the road.
        position: Qt.vector3d(0, 0.45, 0)
        pivot: Qt.vector3d(0, 0.45, 0)
        eulerRotation: Qt.vector3d(root.bodyPitch, 0, -root.bodyRoll)
%(parts)s
    }
    Repeater3D {
        model: [%(wheels)s]
        delegate: Node {
            required property var modelData
            position: Qt.vector3d(modelData[0], %(radius).3f, modelData[1])
            eulerRotation.x: -root.wheelAngle
            Model { source: "meshes/%(tyre)s"; materials: tyreMaterial }
            Model { source: "meshes/%(hubcap)s"; materials: hubcapMaterial }
        }
    }
}
'''
MATERIALS = {'Paint': 'paintMaterial', 'Trim': 'trimMaterial', 'Under': 'underMaterial', 'Shut': 'shutMaterial',
             'Chrome': 'chromeMaterial', 'Grille': 'grilleMaterial', 'Glass': 'glassMaterial',
             'Headlight': 'headlightMaterial', 'TailLight': 'tailMaterial', 'Signal': 'signalMaterial',
             'Reverse': 'reverseMaterial', 'Plate': 'plateMaterial', 'PlateBand': 'plateBandMaterial'}


def main():
    balsam = ROOT / '.venv/bin/pyside6-balsam'
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        write_obj(work / 'sahin.obj', body(), 'sahin')
        write_obj(work / 'sahinwheel.obj', wheel(), 'sahinwheel')
        if DEST.exists():
            shutil.rmtree(DEST)
        out = work / 'out'
        for name in ('sahin', 'sahinwheel'):
            subprocess.run([str(balsam), str(work / f'{name}.obj'), '-o', str(out)], check=True, capture_output=True)
        (DEST / 'meshes').mkdir(parents=True)
        meshes = sorted((out / 'meshes').glob('*.mesh'))
        for mesh in meshes:
            shutil.copy2(mesh, DEST / 'meshes' / mesh.name)
    names = {m.name for m in meshes}

    def mesh_for(object_name):
        match = [n for n in names if n.lower().startswith(object_name.lower() + '_') or n.lower() == object_name.lower() + '.mesh']
        if len(match) != 1:
            raise RuntimeError(f'Balsam mesh for {object_name} not found in {sorted(names)}')
        return match[0]
    parts = '\n'.join(f'        Model {{ source: "meshes/{mesh_for("sahin" + m)}"; materials: {q} }}'
                      for m, q in MATERIALS.items())
    wheels = ', '.join(f'[{x:.3f}, {z:.3f}]' for z in (FRONT_AXLE, REAR_AXLE) for x in (TRACK, -TRACK))
    (DEST / 'Sahin.qml').write_text(QML % dict(parts=parts, wheels=wheels, radius=WHEEL_RADIUS,
                                              tyre=mesh_for('sahinwheelTyre'), hubcap=mesh_for('sahinwheelHubcap')))
    print('Wrote', DEST.relative_to(ROOT), sorted(names))


if __name__ == '__main__':
    main()
