"""Generate the embedded 3D drive scene's sky, surface textures and sounds.

The output is deterministic and committed under device_studio/qml/assets/, so
Studio itself never needs these packages. Regenerating needs numpy, Pillow and,
for the photographic sources, opencv-python (Radiance HDR reader):

    python3 tools/generate_drive_assets.py --source DIR

DIR holds the CC0 Poly Haven originals listed in assets/ATTRIBUTION.md; they are
not committed. Sky cube faces follow Qt Quick 3D's CubeMapTexture lookup,
measured on this Qt version: a world direction (x, y, z) samples the OpenGL
face texel of (-x, y, z).
"""
import argparse
import math
from pathlib import Path
import wave

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'device_studio/qml/assets'
SKY_HDRI = 'kloofendal_48d_partly_cloudy_puresky'
# The scene's DirectionalLight keeps this yaw so the sun stands behind the
# chase camera, to its left; its pitch is the photographed sun's elevation.
LIGHT_YAW = -32.0


def light_direction(pitch, yaw):
    p, y = math.radians(pitch), math.radians(yaw)
    forward = np.array([0.0, math.sin(p), -math.cos(p)])
    return np.array([forward[2] * math.sin(y), forward[1], forward[2] * math.cos(y)])


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


def landscape(color, directions, noise, haze):
    """Three distant mountain ranges and ground haze below the horizon."""
    x, y, z = directions[..., 0], directions[..., 1], directions[..., 2]
    elevation = np.degrees(np.arcsin(np.clip(y, -1, 1)))
    azimuth = np.arctan2(x, -z)
    texture = noise.fbm(azimuth * 160.0, elevation * 9.0, 5)
    # Atmospheric perspective lightens the farther ranges toward the haze.
    ranges = (
        (1.3, 4.4, 0, mix(srgb([154, 176, 194]), haze, 0.35), 1.5),
        (0.6, 2.7, 1, mix(srgb([122, 145, 158]), haze, 0.2), 1.35),
        (-0.1, 1.35, 2, srgb([94, 117, 103]), 1.2),
    )
    for base, height, layer, tint, sharpness in ranges:
        top = base + height * noise.ridge(azimuth, layer) ** sharpness
        inside = smoothstep(top + 0.03, top - 0.03, elevation)
        rock = tint * (0.86 + 0.24 * texture[..., None])
        fade = smoothstep(top - 0.2, -1.2, elevation)[..., None] * 0.55
        color = mix(color, mix(rock, haze, fade), inside[..., None])
    below = smoothstep(-0.6, -2.5, elevation)[..., None]
    return mix(color, haze * 0.94, below)


def read_hdr(path):
    import cv2  # opencv-python, only needed to regenerate the sky
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SystemExit(f'Cannot read {path}')
    return np.ascontiguousarray(image[:, :, ::-1], dtype=np.float32)


def write_hdr(path, image):
    import cv2
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), np.ascontiguousarray(image[:, :, ::-1], dtype=np.float32)):
        raise SystemExit(f'Cannot write {path}')
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


def luminance(image):
    return image @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def sample_equirect(image, lon, lat):
    """Bilinear lookup; lon 0 is the image centre, latitude +90 its top row."""
    height, width = image.shape[:2]
    u = (lon / (2 * math.pi) + 0.5) * width - 0.5
    v = (0.5 - lat / math.pi) * height - 0.5
    u0, v0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fu, fv = (u - u0)[..., None], (v - v0)[..., None]
    v0c, v1c = np.clip(v0, 0, height - 1), np.clip(v0 + 1, 0, height - 1)
    u0w, u1w = u0 % width, (u0 + 1) % width
    top = image[v0c, u0w] * (1 - fu) + image[v0c, u1w] * fu
    bottom = image[v1c, u0w] * (1 - fu) + image[v1c, u1w] * fu
    return top * (1 - fv) + bottom * fv


def find_sun(image):
    """Longitude/latitude (radians) of the brightest blurred region."""
    import cv2
    small = cv2.resize(luminance(image), (1024, 512), interpolation=cv2.INTER_AREA)
    v, u = np.unravel_index(np.argmax(cv2.GaussianBlur(small, (9, 9), 0)), small.shape)
    return ((u + 0.5) / 1024 - 0.5) * 2 * math.pi, (0.5 - (v + 0.5) / 512) * math.pi


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


def build_sky(source, size):
    """Photographed sky (Poly Haven HDRI) turned so its sun matches the scene light."""
    image = read_hdr(source / f'{SKY_HDRI}_8k.hdr')
    sun_lon, sun_lat = find_sun(image)
    target = -light_direction(-math.degrees(sun_lat), LIGHT_YAW)
    turn = math.atan2(target[0], -target[2]) - sun_lon
    print(f'Sun elevation {math.degrees(sun_lat):.1f} deg; set the DirectionalLight to '
          f'eulerRotation ({-math.degrees(sun_lat):.1f}, {LIGHT_YAW:.0f}, 0).')
    sky_lum = luminance(image[int(image.shape[0] * 0.17):int(image.shape[0] * 0.47)])
    exposure = 0.42 / float(np.median(sky_lum))
    noise = SkyNoise(20261029)
    horizon = None
    for face in ('posx', 'negx', 'posy', 'negy', 'posz', 'negz'):
        directions = face_directions(face, size)
        lon = np.arctan2(directions[..., 0], -directions[..., 2]) - turn
        lat = np.arcsin(np.clip(directions[..., 1], -1, 1))
        radiance = sample_equirect(image, (lon + math.pi) % (2 * math.pi) - math.pi, lat) * exposure
        # Soft shoulder instead of clipping keeps cloud tops and the sun halo.
        lum = luminance(radiance)[..., None]
        shoulder = np.where(lum > 0.7, 0.7 + 0.3 * (1 - np.exp(-(lum - 0.7) / 0.3)), lum)
        color = radiance * (shoulder / np.maximum(lum, 1e-6))
        if horizon is None:
            band = (np.degrees(lat) > 0.5) & (np.degrees(lat) < 3)
            horizon = np.median(color[band], axis=0) if band.any() else srgb([186, 204, 210]) ** 2.2
        color = landscape(np.clip(color, 0, 1) ** (1 / 2.2), directions, noise, np.clip(horizon, 0, 1) ** (1 / 2.2))
        save_rgb(ASSETS / f'sky/sky_{face}.jpg', np.clip(color, 0, 1), quality=90)
    haze = np.clip(horizon, 0, 1) ** (1 / 2.2)
    print('Horizon haze sRGB #%02x%02x%02x: use it for the scene fog.' % tuple(int(c * 255) for c in haze))
    # Image-based light: the same turn, the sun clipped because the
    # DirectionalLight already provides it, scaled to the old probe's level.
    # Measured: Qt's lightProbe shows longitude A - 90 deg at view azimuth A.
    probe = read_hdr(source / f'{SKY_HDRI}_2k.hdr')
    probe = np.roll(probe, int(round((turn - math.pi / 2) / (2 * math.pi) * probe.shape[1])), axis=1)
    level = float(np.median(luminance(probe[int(probe.shape[0] * 0.17):int(probe.shape[0] * 0.47)])))
    probe *= 0.55 / level
    lum = luminance(probe)[..., None]
    probe *= np.minimum(1.0, 6.0 / np.maximum(lum, 1e-6))
    # The pure-sky photo mirrors the sky below the horizon; reflections in car
    # paint should show road and fields instead, as in the scene.
    rows = (0.5 - (np.arange(probe.shape[0]) + 0.5) / probe.shape[0]) * 180
    below = smoothstep(0.5, -6.0, rows)[:, None, None]
    ground = np.array([0.16, 0.16, 0.13], np.float32)
    probe = probe * (1 - below) + ground * below
    write_hdr(ASSETS / 'sky/probe.hdr', probe)


# Surfaces -------------------------------------------------------------------

def resize_photo(source, name, target, size=1024, quality=90, mode='RGB'):
    path = ASSETS / 'surfaces' / target
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.open(source / name).convert(mode).resize((size, size), Image.LANCZOS).save(path, quality=quality, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')


def build_photo_surfaces(source):
    """Poly Haven scans: asphalt_02 (3 m square) and aerial_grass_rock (15 m)."""
    resize_photo(source, 'asphalt_02_diff_2k.jpg', 'asphalt_color.jpg')
    resize_photo(source, 'asphalt_02_nor_gl_2k.jpg', 'asphalt_normal.jpg', quality=94)
    resize_photo(source, 'asphalt_02_rough_2k.jpg', 'asphalt_rough.jpg', size=512, mode='L')
    resize_photo(source, 'aerial_grass_rock_diff_2k.jpg', 'grass_color.jpg')
    resize_photo(source, 'aerial_grass_rock_nor_gl_2k.jpg', 'grass_normal.jpg', quality=94)
    grass = np.asarray(Image.open(ASSETS / 'surfaces/grass_color.jpg'), np.float32) / 255
    print('Grass mean linear luminance: %.4f (ground.frag grassMean)' % float(luminance(grass ** 2.2).mean()))


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


def build_jet_sprites():
    """Billowing puff and lifetime colour ramp for the compressed-air jet particles.

    Cold air leaves the nozzles nearly invisible; what shows is the moisture it
    condenses, a soft white billow that fades within a fraction of a second.
    """
    size = 128
    rng = np.random.default_rng(29)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    r = np.hypot(x + 0.5 - size / 2, y + 0.5 - size / 2) / (size / 2)
    billow = periodic_fbm(size, 4, 5, rng, gain=0.55)
    billow = (billow - billow.min()) / (billow.max() - billow.min())
    edge = np.clip(1 - r, 0, 1) ** 1.6 * smoothstep(1.0, 0.55, r + (billow - 0.5) * 0.35)
    alpha = np.clip(edge * (0.55 + 0.6 * billow), 0, 1)
    shade = 0.84 + 0.16 * billow
    image = np.zeros((size, size, 4), np.uint8)
    image[..., 0] = (shade * 247).astype(np.uint8)
    image[..., 1] = (shade * 250).astype(np.uint8)
    image[..., 2] = (shade * 253).astype(np.uint8)
    image[..., 3] = (alpha * 255).astype(np.uint8)
    path = ASSETS / 'fx/jet_puff.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, 'RGBA').save(path, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KiB')
    # Over a particle's life: a quick bloom, then thinning to clear air.
    t = (np.arange(64, dtype=np.float32) + 0.5) / 64
    life = smoothstep(0.0, 0.08, t) * (1 - t) ** 1.4
    ramp = np.zeros((1, 64, 4), np.uint8)
    ramp[..., 0] = (236 + 14 * t).astype(np.uint8)
    ramp[..., 1] = (242 + 10 * t).astype(np.uint8)
    ramp[..., 2] = 252
    ramp[..., 3] = (life / life.max() * 255).astype(np.uint8)
    path = ASSETS / 'fx/jet_life.png'
    Image.fromarray(ramp, 'RGBA').save(path, optimize=True)
    print(f'{path.relative_to(ROOT)}  {path.stat().st_size} B')


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
    parser.add_argument('--source', type=Path, help='folder with the downloaded Poly Haven originals')
    parser.add_argument('--sky-size', type=int, default=2048)
    parser.add_argument('--only', choices=('sky', 'surfaces', 'fx', 'sounds'))
    args = parser.parse_args()
    if args.only in (None, 'sky', 'surfaces') and not args.source:
        parser.error('--source is required for the sky and surfaces')
    if args.only in (None, 'sky'):
        build_sky(args.source, args.sky_size)
    if args.only in (None, 'surfaces'):
        build_photo_surfaces(args.source)
        build_terrain_macro()
        build_foliage()
        build_concrete()
    if args.only in (None, 'fx'):
        build_contact_shadow()
        build_jet_sprites()
    if args.only in (None, 'sounds'):
        build_sounds()


if __name__ == '__main__':
    main()
