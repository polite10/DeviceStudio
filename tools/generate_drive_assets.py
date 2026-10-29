"""Generate the embedded 3D drive scene's sky, surface textures and sounds.

The output is deterministic and committed under device_studio/qml/assets/, so
Studio itself never needs these packages. Regenerating needs numpy and Pillow,
which are not Studio runtime requirements:

    python3 tools/generate_drive_assets.py

Sky cube faces follow Qt Quick 3D's CubeMapTexture lookup, measured on this Qt
version: a world direction (x, y, z) samples the OpenGL face texel of (-x, y, z).
"""
import argparse
import math
from pathlib import Path
import wave

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'device_studio/qml/assets'
# Same orientation as the scene's DirectionalLight (eulerRotation -38, -32, 0):
# the sun stands behind the chase camera, to its left.
LIGHT = (-38.0, -32.0)


def light_direction(pitch, yaw):
    p, y = math.radians(pitch), math.radians(yaw)
    forward = np.array([0.0, math.sin(p), -math.cos(p)])
    return np.array([forward[2] * math.sin(y), forward[1], forward[2] * math.cos(y)])


SUN = -light_direction(*LIGHT)


def srgb(values):
    return np.array(values, np.float32) / 255.0


def smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, t):
    return a + (b - a) * t


# Tileable noise -------------------------------------------------------------

def periodic_noise(size, cells_x, rng, cells_y=None):
    """Quintic value noise on a size×size image that wraps in both directions."""
    cells_y = cells_y or cells_x
    lattice = rng.random((cells_y, cells_x)).astype(np.float32)

    def axis(cells):
        coords = (np.arange(size, dtype=np.float32) + 0.5) * cells / size
        i0 = np.floor(coords).astype(int)
        f = coords - i0
        return i0 % cells, (i0 + 1) % cells, f * f * f * (f * (f * 6 - 15) + 10)

    x0, x1, fx = axis(cells_x)
    y0, y1, fy = axis(cells_y)
    fx, fy = fx[None, :], fy[:, None]
    top = lattice[np.ix_(y0, x0)] * (1 - fx) + lattice[np.ix_(y0, x1)] * fx
    bottom = lattice[np.ix_(y1, x0)] * (1 - fx) + lattice[np.ix_(y1, x1)] * fx
    return top * (1 - fy) + bottom * fy


def periodic_fbm(size, cells, octaves, rng, gain=0.5, stretch=1):
    total = np.zeros((size, size), np.float32)
    amplitude, norm = 1.0, 0.0
    for octave in range(octaves):
        cx = cells * 2 ** octave
        if cx > size:
            break
        total += amplitude * periodic_noise(size, cx, rng, max(1, cx // stretch))
        norm += amplitude
        amplitude *= gain
    return total / norm


def wrap_blur(image, sigma):
    """Gaussian blur with wrap-around edges, so tiles stay seamless."""
    size_y, size_x = image.shape[:2]
    fy = np.fft.fftfreq(size_y)[:, None]
    fx = np.fft.fftfreq(size_x)[None, :]
    kernel = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    if image.ndim == 3:
        kernel = kernel[..., None]
    return np.real(np.fft.ifft2(np.fft.fft2(image, axes=(0, 1)) * kernel, axes=(0, 1))).astype(np.float32)


def cellular(size, cells, rng):
    """Wrapped Worley noise: nearest/second-nearest feature distances and cell ids."""
    points = rng.random((cells, cells, 2)).astype(np.float32)
    ids = rng.random((cells, cells)).astype(np.float32)
    coords = (np.arange(size, dtype=np.float32) + 0.5) * cells / size
    gx, gy = np.meshgrid(coords, coords)
    cx, cy = np.floor(gx).astype(int), np.floor(gy).astype(int)
    first = np.full((size, size), 9.0, np.float32)
    second = np.full((size, size), 9.0, np.float32)
    nearest = np.zeros((size, size), np.float32)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            nx, ny = cx + ox, cy + oy
            px = nx + points[ny % cells, nx % cells, 0]
            py = ny + points[ny % cells, nx % cells, 1]
            distance = np.hypot(gx - px, gy - py)
            closer = distance < first
            second = np.where(closer, first, np.minimum(second, distance))
            nearest = np.where(closer, ids[ny % cells, nx % cells], nearest)
            first = np.where(closer, distance, first)
    return first, second, nearest


def normal_map(height, strength):
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5 * strength
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5 * strength
    normal = np.stack([-dx, dy, np.ones_like(height)], -1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return normal * 0.5 + 0.5


def periodic_curve(size, rng, harmonics=3, amplitude=0.06):
    """x offset for each row that returns to its start, for seamless cracks."""
    rows = np.arange(size) / size
    curve = np.zeros(size)
    for harmonic in range(1, harmonics + 1):
        curve += amplitude / harmonic * np.sin(2 * math.pi * harmonic * rows + rng.uniform(0, 2 * math.pi))
    return curve


def save_rgb(path, image, quality=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(image * 255 + np.random.default_rng(7).uniform(-0.5, 0.5, image.shape), 0, 255).astype(np.uint8)
    picture = Image.fromarray(data, 'RGB' if data.ndim == 3 and data.shape[2] == 3 else 'RGBA')
    if quality:
        picture.save(path, quality=quality, optimize=True)
    else:
        picture.save(path, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


# Sky ----------------------------------------------------------------------

class SkyNoise:
    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        self.perm = rng.permutation(256)
        self.ridges = [rng.random(cells) for cells in (9, 18, 36, 72, 144, 288, 576)]

    def value(self, x, y):
        ix, iy = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
        fx, fy = x - ix, y - iy
        ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
        uy = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
        p = self.perm

        def corner(cx, cy):
            return p[(p[cx & 255] + cy) & 255] / 255.0

        a, b = corner(ix, iy), corner(ix + 1, iy)
        c, d = corner(ix, iy + 1), corner(ix + 1, iy + 1)
        return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy

    def fbm(self, x, y, octaves, gain=0.5):
        total, amplitude, norm = 0.0, 1.0, 0.0
        for octave in range(octaves):
            scale = 2.0 ** octave
            total = total + amplitude * self.value(x * scale + octave * 17.3, y * scale - octave * 9.1)
            norm += amplitude
            amplitude *= gain
        return total / norm

    def ridge(self, azimuth, layer, octaves=6):
        """Periodic skyline height in 0..1 for an azimuth in radians."""
        total, norm, amplitude = 0.0, 0.0, 1.0
        for octave in range(octaves):
            table = self.ridges[(layer + octave) % len(self.ridges)]
            cells = len(table)
            position = (azimuth / (2 * math.pi) % 1.0) * cells + layer * 3.7
            i0 = np.floor(position).astype(int)
            f = position - i0
            f = f * f * (3 - 2 * f)
            total = total + amplitude * (table[i0 % cells] * (1 - f) + table[(i0 + 1) % cells] * f)
            norm += amplitude
            amplitude *= 0.48
        return total / norm


def sky(directions, noise):
    x, y, z = directions[..., 0], directions[..., 1], directions[..., 2]
    up = np.clip(y, -1, 1)
    elevation = np.degrees(np.arcsin(up))
    azimuth = np.arctan2(x, -z)

    zenith, middle, horizon = srgb([46, 104, 178]), srgb([109, 160, 212]), srgb([196, 216, 227])
    haze = srgb([186, 204, 210])
    t = np.clip(up, 0, 1)[..., None]
    color = mix(horizon, middle, smoothstep(0.0, 0.32, t))
    color = mix(color, zenith, smoothstep(0.25, 1.0, t))

    sun = np.clip((directions * SUN).sum(-1), -1, 1)[..., None]
    color = color + srgb([255, 236, 200]) * (0.32 * np.exp((sun - 1) * 9) + 0.9 * np.exp((sun - 1) * 900))

    # Fair-weather cumulus on a flat layer: perspective packs them toward the horizon.
    lifted = np.maximum(up, 0.0) + 0.035
    px, pz = x / lifted * 1.15, z / lifted * 1.15
    warp_x = noise.fbm(px * 0.45 + 31.0, pz * 0.45, 3)
    warp_z = noise.fbm(px * 0.45, pz * 0.45 - 17.0, 3)
    density = noise.fbm(px + warp_x * 1.6, pz + warp_z * 1.6, 7)
    detail = noise.fbm(px * 3.1 - 5.0, pz * 3.1 + 2.0, 4)
    density = density * 0.82 + detail * 0.18
    cover = smoothstep(0.50, 0.70, density) * smoothstep(0.015, 0.13, up) * (1 - 0.35 * smoothstep(0.55, 1.0, up))
    toward_sun = noise.fbm(px + warp_x * 1.6 + SUN[0] * 0.35, pz + warp_z * 1.6 + SUN[2] * 0.35, 5)
    shade = smoothstep(0.52, 0.82, toward_sun) * 0.42 + (1 - smoothstep(0.5, 0.8, density)) * 0.12
    cloud = mix(srgb([252, 252, 250]), srgb([150, 164, 182]), shade[..., None])
    cloud = mix(cloud, horizon, (1 - smoothstep(0.02, 0.3, up))[..., None] * 0.7)
    color = mix(color, cloud, (cover * 0.96)[..., None])

    # Three mountain ranges; atmospheric perspective lightens the farther ones.
    texture = noise.fbm(azimuth * 160.0, elevation * 9.0, 5)
    ranges = (
        (1.3, 4.4, 0, [154, 176, 194], 1.5),
        (0.6, 2.7, 1, [122, 145, 158], 1.35),
        (-0.1, 1.35, 2, [94, 117, 103], 1.2),
    )
    for base, height, layer, tint, sharpness in ranges:
        top = base + height * noise.ridge(azimuth, layer) ** sharpness
        inside = smoothstep(top + 0.03, top - 0.03, elevation)
        rock = srgb(tint) * (0.86 + 0.24 * texture[..., None])
        fade = smoothstep(top - 0.2, -1.2, elevation)[..., None] * 0.55
        rock = mix(rock, haze, fade)
        color = mix(color, rock, inside[..., None])
    below = smoothstep(-0.6, -2.5, elevation)[..., None]
    color = mix(color, haze * 0.94, below)
    return np.clip(color, 0, 1)


def face_directions(face, size):
    s = (np.arange(size, dtype=np.float64) + 0.5) / size * 2 - 1
    sc, tc = np.meshgrid(s, s)
    one = np.ones_like(sc)
    gl = {
        'posx': (one, -tc, -sc), 'negx': (-one, -tc, sc),
        'posy': (sc, one, tc), 'negy': (sc, -one, -tc),
        'posz': (sc, -tc, one), 'negz': (-sc, -tc, -one),
    }[face]
    direction = np.stack([-gl[0], gl[1], gl[2]], -1)
    return direction / np.linalg.norm(direction, axis=-1, keepdims=True)


def build_sky(size):
    noise = SkyNoise(20261029)
    for face in ('posx', 'negx', 'posy', 'negy', 'posz', 'negz'):
        save_rgb(ASSETS / f'sky/sky_{face}.jpg', sky(face_directions(face, size), noise), quality=90)
    width = size // 2
    lon = ((np.arange(width) + 0.5) / width - 0.5) * 2 * math.pi
    lat = (0.5 - (np.arange(width // 2) + 0.5) / (width // 2)) * math.pi
    lon, lat = np.meshgrid(lon, lat)
    directions = np.stack([np.sin(lon) * np.cos(lat), np.sin(lat), -np.cos(lon) * np.cos(lat)], -1)
    save_rgb(ASSETS / 'sky/probe.jpg', sky(directions, noise), quality=92)


# Surfaces -------------------------------------------------------------------

def build_asphalt(size=1024):
    """3.6 m square of worn motorway asphalt; wheel tracks are added by the shader."""
    rng = np.random.default_rng(3601)
    tone = 0.36 + 0.035 * (periodic_fbm(size, 4, 5, rng) - 0.5) + 0.05 * (periodic_fbm(size, 16, 4, rng) - 0.5)
    grain = wrap_blur(rng.standard_normal((size, size)).astype(np.float32), 0.7) * 0.045
    stones = wrap_blur((rng.random((size, size)) > 0.982).astype(np.float32), 0.9) * 0.55
    pits = wrap_blur((rng.random((size, size)) > 0.986).astype(np.float32), 0.8) * 0.5
    height = grain * 4 + stones - pits
    value = tone + grain + stones * 0.32 - pits * 0.22
    columns = np.arange(size)[None, :]
    # Crack sealant: irregular tar strips that appear in segments, not lines
    # running through every repeated tile.
    seal = np.zeros((size, size), np.float32)
    centre = (rng.uniform(0.15, 0.85) + periodic_curve(size, rng, 7, 0.01)) * size
    width = rng.uniform(1.8, 2.6) * (0.75 + 0.5 * periodic_noise(size, 9, rng)[:, :1])
    distance = np.abs((columns - centre[:, None] + size / 2) % size - size / 2)
    segment = smoothstep(0.55, 0.66, periodic_fbm(size, 3, 3, rng)[:, :1])
    seal = np.maximum(seal, smoothstep(width, width * 0.4, distance) * segment)
    centre = (rng.uniform(0.2, 0.8) + periodic_curve(size, rng, 6, 0.008)) * size
    distance = np.abs((columns - centre[:, None] + size / 2) % size - size / 2).T
    crack = smoothstep(2.4, 0.8, distance) * smoothstep(0.56, 0.66, periodic_fbm(size, 4, 3, rng).T[:, :1].T)
    seal = np.maximum(seal, crack)
    value = value * (1 - 0.32 * seal)
    height = height - seal * 0.25
    tint = np.stack([value * 0.985, value, value * 1.03], -1)
    save_rgb(ASSETS / 'surfaces/asphalt.jpg', tint, quality=90)
    normal = normal_map(wrap_blur(height, 0.6), 2.4)
    small = Image.fromarray((normal * 255).astype(np.uint8), 'RGB').resize((256, 256), Image.LANCZOS)
    path = ASSETS / 'surfaces/asphalt_normal.png'
    small.save(path, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


def build_grass(size=1024):
    """4 m square of roadside grass with dry and clover patches."""
    rng = np.random.default_rng(4004)
    # No structure larger than ~0.5 m: the shader's macro map varies the rest,
    # so the 4 m repeat never shows as stripes.
    lush, mown, dry = srgb([70, 96, 44]), srgb([96, 116, 54]), srgb([138, 132, 82])
    variation = periodic_fbm(size, 16, 5, rng)
    color = mix(lush, mown, smoothstep(0.3, 0.7, variation)[..., None])
    dry_mask = smoothstep(0.62, 0.78, periodic_fbm(size, 24, 3, rng))
    color = mix(color, dry, (dry_mask * 0.45)[..., None])
    clumps = periodic_fbm(size, 48, 3, rng)
    blades = wrap_blur(rng.standard_normal((size, size)).astype(np.float32), 0.55)
    color = color * (0.78 + 0.32 * clumps[..., None] + 0.07 * blades[..., None])
    flowers = wrap_blur((rng.random((size, size)) > 0.9993).astype(np.float32), 0.9) * 4.0
    color = mix(color, srgb([235, 228, 170]), np.clip(flowers, 0, 0.8)[..., None])
    save_rgb(ASSETS / 'surfaces/grass.jpg', np.clip(color, 0, 1), quality=88)


def build_terrain_macro(size=512):
    """400 m wrap: R broad tone, G farmland parcels, B soil/dryness."""
    rng = np.random.default_rng(4400)
    broad = periodic_fbm(size, 4, 5, rng)
    first, second, parcel = cellular(size, 14, rng)
    edge = smoothstep(0.0, 0.05, second - first)
    parcels = parcel * edge + 0.5 * (1 - edge)
    soil = periodic_fbm(size, 12, 4, rng)
    image = np.stack([broad, parcels, soil], -1)
    path = ASSETS / 'surfaces/terrain_macro.png'
    Image.fromarray((np.clip(image, 0, 1) * 255).astype(np.uint8), 'RGB').save(path, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


def build_foliage(size=512):
    rng = np.random.default_rng(5150)
    first, second, cell = cellular(size, 22, rng)
    clump = np.clip(1 - first / 0.75, 0, 1)
    fine_first, _, _ = cellular(size, 70, rng)
    leaves = np.clip(1 - fine_first / 0.8, 0, 1)
    height = clump * 0.75 + leaves * 0.35
    shade = smoothstep(0.05, 0.9, height)
    base = mix(srgb([44, 68, 34]), srgb([92, 122, 56]), cell[..., None] * 0.6 + 0.2)
    color = base * (0.42 + 0.78 * shade[..., None])
    save_rgb(ASSETS / 'surfaces/foliage.jpg', np.clip(color, 0, 1), quality=88)
    normal = normal_map(wrap_blur(height, 0.8), 9.0)
    path = ASSETS / 'surfaces/foliage_normal.png'
    Image.fromarray((normal * 255).astype(np.uint8), 'RGB').resize((256, 256), Image.LANCZOS).save(path, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


def build_concrete(size=512):
    rng = np.random.default_rng(6060)
    value = 0.72 + 0.06 * (periodic_fbm(size, 4, 5, rng) - 0.5) + 0.05 * (periodic_fbm(size, 24, 3, rng) - 0.5)
    value += wrap_blur(rng.standard_normal((size, size)).astype(np.float32), 0.6) * 0.025
    stains = smoothstep(0.62, 0.8, periodic_fbm(size, 3, 4, rng, stretch=3)) * 0.12
    value -= stains
    save_rgb(ASSETS / 'surfaces/concrete.jpg', np.stack([value, value * 0.99, value * 0.96], -1), quality=88)


def build_contact_shadow():
    width, height = 128, 256
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    nx = np.abs(x + 0.5 - width / 2) / (width / 2)
    ny = np.abs(y + 0.5 - height / 2) / (height / 2)
    inner_x, inner_y = 0.62, 0.8
    dx = np.maximum(nx - inner_x, 0) / (1 - inner_x)
    dy = np.maximum(ny - inner_y, 0) / (1 - inner_y)
    alpha = np.clip(1 - np.hypot(dx, dy), 0, 1) ** 1.8
    image = np.zeros((height, width, 4), np.uint8)
    image[..., 3] = (alpha * 255).astype(np.uint8)
    path = ASSETS / 'fx/contact_shadow.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, 'RGBA').save(path, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


# Sounds ---------------------------------------------------------------------

def write_wav(name, samples, rate):
    path = ASSETS / 'sounds' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(samples, -1, 1) * 32000).astype('<i2')
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(data.tobytes())
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


def tone(frequency, seconds, rate, harmonics=((1, 1.0), (2, 0.18), (3, 0.08)), attack=0.006, release=0.05):
    t = np.arange(int(seconds * rate)) / rate
    wave_ = sum(level * np.sin(2 * math.pi * frequency * order * t) for order, level in harmonics)
    envelope = np.minimum(1, t / attack) * np.minimum(1, (seconds - t) / release)
    return wave_ * envelope


def silence(seconds, rate):
    return np.zeros(int(seconds * rate))


def lowpass(signal, cutoff, rate):
    spectrum = np.fft.rfft(signal)
    frequencies = np.fft.rfftfreq(len(signal), 1 / rate)
    spectrum *= 1 / np.sqrt(1 + (frequencies / cutoff) ** 4)
    return np.fft.irfft(spectrum, len(signal))


def build_sounds():
    rate = 44100
    chime = np.concatenate([tone(1568, 0.11, rate), silence(0.06, rate), tone(1568, 0.11, rate)])
    write_wav('fcw.wav', chime * 0.55, rate)
    pulse = tone(2350, 0.065, rate, ((1, 1.0), (3, 0.3), (5, 0.12)), 0.002, 0.02)
    alarm = np.concatenate([pulse, silence(0.035, rate)] * 3)
    write_wav('aeb.wav', alarm * 0.6, rate)
    rng = np.random.default_rng(11)
    t = np.arange(int(0.045 * rate)) / rate
    click = (rng.standard_normal(len(t)) * 0.5 + np.sin(2 * math.pi * 2900 * t)) * np.exp(-t / 0.006)
    write_wav('indicator.wav', lowpass(click, 5000, rate) * 0.5, rate)
    # Seamless tyre/wind bed: periodic FFT noise loops without a click.
    rate = 22050
    length = int(4.0 * rate)
    noise = rng.standard_normal(length)
    rumble = lowpass(noise, 180, rate) * 2.2 + lowpass(noise, 900, rate) * 0.7 + lowpass(rng.standard_normal(length), 2600, rate) * 0.18
    t = np.arange(length) / rate
    rumble *= 0.85 + 0.15 * np.sin(2 * math.pi * 0.5 * t)
    write_wav('road.wav', rumble / np.abs(rumble).max() * 0.8, rate)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--sky-size', type=int, default=2048)
    parser.add_argument('--only', choices=('sky', 'surfaces', 'sounds'))
    args = parser.parse_args()
    if args.only in (None, 'sky'):
        build_sky(args.sky_size)
    if args.only in (None, 'surfaces'):
        build_asphalt()
        build_grass()
        build_terrain_macro()
        build_foliage()
        build_concrete()
        build_contact_shadow()
    if args.only in (None, 'sounds'):
        build_sounds()


if __name__ == '__main__':
    main()
