"""Pixel effects that need more precision than 8-bit filters: float blur, round dilation,
2D jump-flood SDF, 2.5D PBR-lite surface lighting (emboss with bump / studio env / anisotropy / fresnel /
shine), color adjustment, procedural noise, OKLab conversion and refracting liquid glass."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import gpu
from .colors import parse_color

try:
    import cv2
except ImportError:
    cv2 = None


def _box(a, r: int, axis: int):
    """Box blur of half-width r along one axis; outside the array counts as zero (numpy or cupy)."""
    if r <= 0:
        return a
    xp = gpu.array_module(a)
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = xp.cumsum(xp.pad(a, pad), axis=axis, dtype=xp.float64)
    n = a.shape[axis]
    hi = xp.take(c, xp.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = xp.take(c, xp.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def blur_float(a: np.ndarray, radius: float, passes: int = 3) -> np.ndarray:
    """Smooth float blur. passes=3 is close to a Gaussian of sigma ~ radius / 2; passes=1 is a plain
    box of half-width ``radius`` (turns a hard edge into a linear ramp)."""
    if radius <= 0:
        return a
    if passes == 1:
        r = max(1, int(round(radius)))
    else:
        sigma = radius / 2.0
        r = max(1, int(round((math.sqrt(12 * sigma * sigma / passes + 1) - 1) / 2)))
    xp = gpu.module_for(a.size)

    def _run():
        out = xp.asarray(a, dtype=xp.float64)
        for _ in range(passes):
            out = _box(_box(out, r, 0), r, 1)
        return gpu.to_numpy(out)

    if xp is not np:
        with gpu.gpu_lock():
            return _run()
    return _run()


_DISC_CACHE: dict[int, np.ndarray] = {}


def _disc_kernel(radius: float) -> np.ndarray:
    """Exact Euclidean circular structuring element for OpenCV morphological ops."""
    key = int(round(radius * 100))
    k = _DISC_CACHE.get(key)
    if k is None:
        big = int(math.ceil(radius))
        ys, xs = np.ogrid[-big:big + 1, -big:big + 1]
        k = ((xs * xs + ys * ys) <= radius * radius + 1e-9).astype(np.uint8)
        if len(_DISC_CACHE) > 256:
            _DISC_CACHE.clear()
        _DISC_CACHE[key] = k
    return k


def dilate(alpha: np.ndarray, radius: float) -> np.ndarray:
    """Grow a coverage mask by ``radius`` pixels with a round (disc) brush. uint8 in, uint8 out."""
    if radius <= 0:
        return alpha
    big = int(math.ceil(radius))
    if cv2 is not None and big <= 128:
        return cv2.dilate(np.ascontiguousarray(alpha, dtype=np.uint8), _disc_kernel(radius),
                          borderType=cv2.BORDER_CONSTANT, borderValue=0)
    h, w = alpha.shape
    levels = max(1, int(math.floor(math.log2(2 * big + 1))) + 1)
    padded = np.pad(alpha, ((0, 0), (big, big + (1 << levels))))
    tables = [padded]
    for j in range(levels):
        prev = tables[-1]
        shifted = np.zeros_like(prev)
        shifted[:, : prev.shape[1] - (1 << j)] = prev[:, (1 << j):]
        tables.append(np.maximum(prev, shifted))
    out = np.zeros((h + 2 * big, w), dtype=np.uint8)
    rows: dict[int, np.ndarray] = {}
    for dy in range(-big, big + 1):
        hw = int(math.floor(math.sqrt(max(0.0, radius * radius - dy * dy))))
        if dy * dy > radius * radius:
            continue
        if hw not in rows:
            length = 2 * hw + 1
            j = int(math.floor(math.log2(length)))
            t = tables[j]
            start = big - hw
            a = t[:, start: start + w]
            b = t[:, start + length - (1 << j): start + length - (1 << j) + w]
            rows[hw] = np.maximum(a, b)
        np.maximum(out[big + dy: big + dy + h], rows[hw], out=out[big + dy: big + dy + h])
    return out[big: big + h]


def erode(alpha: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return alpha
    big = int(math.ceil(radius))
    if cv2 is not None and big <= 128:
        return cv2.erode(np.ascontiguousarray(alpha, dtype=np.uint8), _disc_kernel(radius),
                         borderType=cv2.BORDER_CONSTANT, borderValue=0)
    return 255 - dilate(255 - alpha, radius)


def grow(alpha: np.ndarray, distance: float) -> np.ndarray:
    """Positive distance grows the mask, negative shrinks it."""
    return dilate(alpha, distance) if distance > 0 else erode(alpha, -distance) if distance < 0 else alpha


def distance_field(alpha: Image.Image | np.ndarray, k: float = 1.0, max_radius_px: int | None = None) -> np.ndarray:
    """Interior Euclidean distance from the shape edge in canvas units (float32, 0 outside, >0 inside).

    Uses OpenCV SIMD C++ exact L2 distance transform when installed (~1 ms at 512x512), falling back to
    vectorized numpy Jump Flooding.
    """
    arr = np.asarray(alpha, dtype=np.uint8)
    h, w = arr.shape[:2]
    inside = arr >= 128
    if not inside.any():
        return np.zeros((h, w), dtype=np.float32)
    if cv2 is not None:
        padded = np.pad(inside.astype(np.uint8), 1, constant_values=0)
        dist_px = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
        frac = np.clip(arr.astype(np.float32) / np.float32(255.0) - np.float32(0.5), np.float32(-0.5), np.float32(0.5))
        dist_px = np.maximum(np.float32(0.0), dist_px + frac)
        return (dist_px / np.float32(max(1e-6, k))).astype(np.float32)
    padded = np.pad(inside, 1, constant_values=False)
    outside = ~padded
    ys = np.arange(h + 2, dtype=np.float32)[:, None]
    xs = np.arange(w + 2, dtype=np.float32)[None, :]
    inf = np.float32(1e6)
    nx = np.where(outside, np.broadcast_to(xs, (h + 2, w + 2)), inf).astype(np.float32)
    ny = np.where(outside, np.broadcast_to(ys, (h + 2, w + 2)), inf).astype(np.float32)
    best_d2 = np.where(outside, np.float32(0.0), np.float32(1e12)).astype(np.float32)

    cap = max_radius_px if max_radius_px is not None else max(h, w)
    step = 1
    while step * 2 < cap:
        step *= 2
    while step >= 1:
        for dy in (-step, 0, step):
            if abs(dy) >= h + 2:
                continue
            y_src = slice(max(0, -dy), h + 2 - max(0, dy))
            y_dst = slice(max(0, dy), h + 2 - max(0, -dy))
            for dx in (-step, 0, step):
                if (dx == 0 and dy == 0) or abs(dx) >= w + 2:
                    continue
                x_src = slice(max(0, -dx), w + 2 - max(0, dx))
                x_dst = slice(max(0, dx), w + 2 - max(0, -dx))
                cx = nx[y_src, x_src]
                cy = ny[y_src, x_src]
                ddx = xs[:, x_dst] - cx
                ddy = ys[y_dst, :] - cy
                d2 = ddx * ddx + ddy * ddy
                cur = best_d2[y_dst, x_dst]
                better = d2 < cur
                if better.any():
                    cur[better] = d2[better]
                    nx[y_dst, x_dst][better] = cx[better]
                    ny[y_dst, x_dst][better] = cy[better]
        step //= 2
    dist_px = np.sqrt(best_d2[1:-1, 1:-1])
    frac = np.clip(arr.astype(np.float32) / np.float32(255.0) - np.float32(0.5), np.float32(-0.5), np.float32(0.5))
    dist_px = np.maximum(np.float32(0.0), dist_px + frac)
    return (dist_px / np.float32(max(1e-6, k))).astype(np.float32)


def _studio_env(rx: np.ndarray, ry: np.ndarray, rz: np.ndarray, env_rot: float) -> tuple[np.ndarray, np.ndarray]:
    """Analytic studio lighting dome: returns (bright softboxes 0..1, dark horizon band 0..1)."""
    ca, sa = math.cos(env_rot), math.sin(env_rot)
    rrx = rx * np.float32(ca) - ry * np.float32(sa)
    rry = rx * np.float32(sa) + ry * np.float32(ca)
    softbox_top = np.exp(-((rrx + np.float32(0.35)) ** 2 * np.float32(4.5)
                           + (rry + np.float32(0.45)) ** 2 * np.float32(7.0)))
    rim_strip = np.exp(-((rrx - np.float32(0.55)) ** 2 * np.float32(10.0)
                         + (rry - np.float32(0.2)) ** 2 * np.float32(2.5))) * np.float32(0.7)
    horizon_hi = np.exp(-((rry + np.float32(0.06)) * np.float32(6.0)) ** 2) * np.float32(0.45)
    horizon_lo = np.exp(-((rry - np.float32(0.28)) * np.float32(4.0)) ** 2) * np.float32(0.65)
    bright = np.clip(softbox_top + rim_strip + horizon_hi, np.float32(0.0), np.float32(1.0))
    dark = np.clip(horizon_lo * (np.float32(1.0) - softbox_top), np.float32(0.0), np.float32(1.0))
    return bright, dark


def emboss(alpha: Image.Image, spec: dict, colors: dict, k: float,
           bump: np.ndarray | None = None, sdf: np.ndarray | None = None) -> Image.Image:
    """Light a shape as a 2.5D PBR-lite surface.

    Supports bevel profiles (round, chisel, machined, pillow, engraved), optional shader bump height,
    studio softbox reflections (env / metallic), anisotropic brushed specular (anisotropy / brush_angle),
    Schlick Fresnel rim highlights (fresnel) and animated diagonal shine sweeps (shine).
    """
    if not isinstance(spec, dict):
        spec = {}
    size = max(0.5, float(spec.get("size", 6))) * k
    depth = max(0.0, float(spec.get("depth", 1)))
    angle = math.radians(float(spec.get("angle", 225)))
    altitude = math.radians(max(5.0, min(85.0, float(spec.get("altitude", 40)))))
    profile = str(spec.get("profile", "round")).lower()
    if profile not in ("round", "chisel", "machined", "pillow", "engraved"):
        raise ValueError("light.profile must be 'round', 'chisel', 'machined', 'pillow' or 'engraved'")
    hi_color = parse_color(spec.get("highlight", "#ffffff@0.7"), colors)
    sh_color = parse_color(spec.get("shadow", "#000000@0.6"), colors)
    gloss = max(0.0, float(spec.get("gloss", 0)))
    gloss_power = max(1.0, float(spec.get("gloss_size", 0.25)) ** -1 * 8)
    env_amt = max(0.0, float(spec.get("env", 0) or 0))
    env_rot = math.radians(float(spec.get("env_rotation", 0) or 0))
    aniso = max(0.0, min(0.95, float(spec.get("anisotropy", 0) or 0)))
    brush_ang = math.radians(float(spec.get("brush_angle", 0) or 0))
    fresnel_amt = max(0.0, float(spec.get("fresnel", 0) or 0))
    bump_strength = float(spec.get("bump_strength", 0.45 if bump is not None else 0.0))
    shine_pos = spec.get("shine")

    a = np.asarray(alpha, dtype=np.float32) / np.float32(255.0)
    h_img, w_img = a.shape
    if profile in ("machined", "pillow", "engraved"):
        d_u = sdf if sdf is not None and sdf.shape == a.shape else distance_field(alpha, k)
        bw = max(0.5, float(spec.get("size", 6)))
        u = np.clip(d_u / np.float32(bw), np.float32(0.0), np.float32(1.0))
        if profile == "machined":
            outer = np.clip(u / np.float32(0.28), np.float32(0.0), np.float32(1.0))
            mid = np.clip((u - np.float32(0.28)) / np.float32(0.44), np.float32(0.0), np.float32(1.0))
            inner = np.clip((u - np.float32(0.72)) / np.float32(0.28), np.float32(0.0), np.float32(1.0))
            height = np.float32(0.55) * np.sqrt(np.maximum(np.float32(0.0), outer * (np.float32(2.0) - outer))) \
                + np.float32(0.25) * mid + np.float32(0.20) * inner * inner * (np.float32(3.0) - np.float32(2.0) * inner)
        elif profile == "pillow":
            p_max = max(bw, float(d_u.max()) if d_u.size else bw)
            pu = np.clip(d_u / np.float32(max(1.0, p_max)), np.float32(0.0), np.float32(1.0))
            height = np.sqrt(np.maximum(np.float32(0.0), pu * (np.float32(2.0) - pu)))
            height = blur_float(height, max(4.0 * k, size * 0.65), 3).astype(np.float32)
        else:
            height = np.float32(1.0) - np.sqrt(np.maximum(np.float32(0.0), u * (np.float32(2.0) - u)))
        soften = float(spec.get("soften", 0.8)) * k
        if soften > 0 and profile != "pillow":
            height = blur_float(height, soften, 2).astype(np.float32)
        gy, gx = np.gradient(height)
        slope = np.float32(size * depth * (1.3 if profile == "machined" else 1.5))
    else:
        pad = int(math.ceil(size)) + 2
        ap = np.pad(a, pad)
        height = blur_float(ap, size, 1 if profile == "chisel" else 3).astype(np.float32)
        height = np.clip((height - np.float32(0.5)) * np.float32(2.0), np.float32(0.0), np.float32(1.0))
        soften = float(spec.get("soften", 0)) * k
        if soften > 0:
            height = blur_float(height, soften, 3).astype(np.float32)
        gy_full, gx_full = np.gradient(height)
        crop = (slice(pad, pad + h_img), slice(pad, pad + w_img))
        gx, gy = gx_full[crop], gy_full[crop]
        slope = np.float32(size * depth * (1.0 if profile == "chisel" else 1.6))

    nx = -gx * slope
    ny = -gy * slope
    if bump is not None and bump_strength > 0 and bump.shape == a.shape:
        bgy, bgx = np.gradient(bump.astype(np.float32))
        bs = np.float32(bump_strength * 3.5 * k)
        nx = nx - bgx * bs
        ny = ny - bgy * bs
    norm = np.sqrt(nx * nx + ny * ny + np.float32(1.0))
    nx, ny, nz = nx / norm, ny / norm, np.float32(1.0) / norm

    lx = np.float32(math.cos(angle) * math.cos(altitude))
    ly = np.float32(math.sin(angle) * math.cos(altitude))
    lz = np.float32(math.sin(altitude))
    lit = nx * lx + ny * ly + nz * lz
    hi = np.clip((lit - lz) / np.float32(max(1e-6, 1.0 - float(lz))), np.float32(0.0), np.float32(1.0))
    sh = np.clip((lz - lit) / np.float32(max(1e-6, float(lz))), np.float32(0.0), np.float32(1.0))

    if gloss > 0:
        hx, hy, hz = float(lx), float(ly), float(lz) + 1.0
        hn = math.sqrt(hx * hx + hy * hy + hz * hz)
        hx, hy, hz = np.float32(hx / hn), np.float32(hy / hn), np.float32(hz / hn)
        ndh = np.clip(nx * hx + ny * hy + nz * hz, np.float32(0.0), np.float32(1.0))
        if aniso > 0:
            tx, ty = np.float32(math.cos(brush_ang)), np.float32(math.sin(brush_ang))
            bx_, by_ = -ty, tx
            ht = (hx - nx * ndh) * tx + (hy - ny * ndh) * ty
            hb = (hx - nx * ndh) * bx_ + (hy - ny * ndh) * by_
            ax = np.float32(0.18 * (1.0 - aniso * 0.82))
            ay = np.float32(0.18 * (1.0 + aniso * 3.2))
            aniso_spec = np.exp(-((ht / ax) ** 2 + (hb / ay) ** 2)) * np.power(ndh, np.float32(2.0))
            base_val = math.exp(-(((float(hx) * float(tx) + float(hy) * float(ty)) / float(ax)) ** 2
                                  + ((float(hx) * float(bx_) + float(hy) * float(by_)) / float(ay)) ** 2)) * (float(hz) ** 2)
            hi = np.clip(hi + np.clip(aniso_spec - np.float32(base_val * 0.5), np.float32(0.0), np.float32(1.0))
                         * np.float32(gloss * 1.4), np.float32(0.0), np.float32(1.0))
        else:
            spec_core = np.power(ndh, np.float32(gloss_power)) - np.float32(float(hz) ** gloss_power)
            spec_halo = np.power(ndh, np.float32(max(2.0, gloss_power * 0.25))) - np.float32(float(hz) ** max(2.0, gloss_power * 0.25))
            spec_term = np.clip(spec_core, np.float32(0.0), np.float32(1.0)) * np.float32(1.8) \
                + np.clip(spec_halo, np.float32(0.0), np.float32(1.0)) * np.float32(0.45)
            hi = np.clip(hi + spec_term * np.float32(gloss), np.float32(0.0), np.float32(1.0))

    if env_amt > 0:
        rx = np.float32(2.0) * nz * nx
        ry = np.float32(2.0) * nz * ny
        rz = np.float32(2.0) * nz * nz - np.float32(1.0)
        eb, ed = _studio_env(rx, ry, rz, env_rot)
        hi = np.clip(hi + eb * np.float32(env_amt * 0.85), np.float32(0.0), np.float32(1.0))
        sh = np.clip(sh + ed * np.float32(env_amt * 0.55), np.float32(0.0), np.float32(1.0))

    if fresnel_amt > 0:
        grazing = np.power(np.clip(np.float32(1.0) - nz, np.float32(0.0), np.float32(1.0)), np.float32(2.2))
        hi = np.clip(hi + grazing * np.float32(fresnel_amt * 1.35), np.float32(0.0), np.float32(1.0))

    if shine_pos is not None:
        s_val = float(shine_pos)
        ys_n = np.linspace(0.0, 1.0, h_img, dtype=np.float32)[:, None]
        xs_n = np.linspace(0.0, 1.0, w_img, dtype=np.float32)[None, :]
        diag = (xs_n * np.float32(0.75) + ys_n * np.float32(0.25)) - np.float32(s_val * 1.4 - 0.2)
        sweep = np.exp(-((diag / np.float32(0.09)) ** 2)) * np.float32(0.85)
        hi = np.clip(hi + sweep, np.float32(0.0), np.float32(1.0))

    ha = hi * np.float32(hi_color[3] / 255.0) * a
    sa = sh * np.float32(sh_color[3] / 255.0) * a
    total = ha + sa
    safe = np.where(total > np.float32(0.0), total, np.float32(1.0))
    out = np.empty(a.shape + (4,), dtype=np.float32)
    for c in range(3):
        out[..., c] = (np.float32(hi_color[c]) * ha + np.float32(sh_color[c]) * sa) / safe
    out[..., 3] = np.clip(total, np.float32(0.0), np.float32(1.0)) * np.float32(255.0)
    return Image.fromarray(np.clip(out + np.float32(0.5), 0, 255).astype(np.uint8), "RGBA")


def adjust(img: Image.Image, spec: dict, colors: dict) -> Image.Image:
    """brightness, contrast, saturation, exposure, temperature, shadows, highlights (-1..1), hue (degrees),
    tint (color; its alpha is the amount), invert."""
    if not isinstance(spec, dict):
        raise ValueError("adjust must be an object like {brightness, contrast, saturation, hue, tint}")
    arr = np.asarray(img, dtype=np.float32).copy()
    rgb = arr[..., :3]
    hue = float(spec.get("hue", 0) or 0)
    if hue:
        t = math.radians(hue)
        c, s = math.cos(t), math.sin(t)
        m = np.array([[0.299 + 0.701 * c + 0.168 * s, 0.587 - 0.587 * c + 0.330 * s, 0.114 - 0.114 * c - 0.497 * s],
                      [0.299 - 0.299 * c - 0.328 * s, 0.587 + 0.413 * c + 0.035 * s, 0.114 - 0.114 * c + 0.292 * s],
                      [0.299 - 0.300 * c + 1.250 * s, 0.587 - 0.588 * c - 1.050 * s, 0.114 + 0.886 * c - 0.203 * s]],
                     dtype=np.float32)
        rgb = rgb @ m.T
    sat = float(spec.get("saturation", 0) or 0)
    if sat:
        lum = (np.float32(0.2126) * rgb[..., 0] + np.float32(0.7152) * rgb[..., 1] + np.float32(0.0722) * rgb[..., 2])[..., None]
        rgb = lum + (rgb - lum) * np.float32(max(0.0, 1.0 + sat))
    bright = float(spec.get("brightness", 0) or 0)
    if bright:
        rgb = rgb + np.float32(bright * 255.0)
    contrast = float(spec.get("contrast", 0) or 0)
    if contrast:
        rgb = (rgb - np.float32(127.5)) * np.float32(max(0.0, 1.0 + contrast)) + np.float32(127.5)
    exposure = float(spec.get("exposure", 0) or 0)
    if exposure:
        rgb = rgb * np.float32(2.0 ** exposure)
    temp = float(spec.get("temperature", 0) or 0)
    if temp:
        rgb = rgb + np.array([1.0, 0.25, -1.0], dtype=np.float32) * np.float32(temp * 40.0)
    shadows = float(spec.get("shadows", 0) or 0)
    highlights = float(spec.get("highlights", 0) or 0)
    if shadows or highlights:
        lum = np.clip((np.float32(0.2126) * rgb[..., 0] + np.float32(0.7152) * rgb[..., 1]
                       + np.float32(0.0722) * rgb[..., 2]) / np.float32(255.0), 0, 1)[..., None]
        rgb = rgb + np.float32(shadows * 110.0) * (np.float32(1.0) - lum) ** 2 + np.float32(highlights * 110.0) * lum ** 2
    if spec.get("invert"):
        rgb = np.float32(255.0) - rgb
    if spec.get("tint"):
        r, g, b, a = parse_color(spec["tint"], colors)
        amount = np.float32(a / 255.0)
        rgb = rgb * (np.float32(1.0) - amount) + np.array([r, g, b], dtype=np.float32) * amount
    arr[..., :3] = np.clip(rgb, 0, 255)
    return Image.fromarray((arr + np.float32(0.5)).astype(np.uint8), "RGBA")


def _lattice(ix: np.ndarray, iy: np.ndarray, seed: float) -> np.ndarray:
    v = np.sin(ix * np.float32(127.1) + iy * np.float32(311.7) + np.float32(seed * 74.7)) * np.float32(43758.5453)
    return v - np.floor(v)


def fractal_noise(ux: np.ndarray, uy: np.ndarray, scale: float, octaves: int, seed: float) -> np.ndarray:
    """Smooth cloud-like noise in 0..1 at coordinates (ux, uy); ``scale`` is the size of the largest blobs."""
    ux, uy = ux.astype(np.float32, copy=False), uy.astype(np.float32, copy=False)
    total = np.zeros(np.broadcast_shapes(ux.shape, uy.shape), dtype=np.float32)
    weight, amp, cell = np.float32(0.0), np.float32(1.0), np.float32(max(0.5, scale))
    for o in range(max(1, min(8, int(octaves)))):
        x, y = ux / cell, uy / cell
        x0, y0 = np.floor(x), np.floor(y)
        tx, ty = x - x0, y - y0
        tx = tx * tx * (np.float32(3.0) - np.float32(2.0) * tx)
        ty = ty * ty * (np.float32(3.0) - np.float32(2.0) * ty)
        s = seed + o * 17.0
        one = np.float32(1.0)
        top = _lattice(x0, y0, s) * (one - tx) + _lattice(x0 + one, y0, s) * tx
        bottom = _lattice(x0, y0 + one, s) * (one - tx) + _lattice(x0 + one, y0 + one, s) * tx
        total += (top * (one - ty) + bottom * ty) * amp
        weight = np.float32(weight + amp)
        amp = np.float32(amp * 0.5)
        cell = np.float32(cell / 2.0)
    return total / weight


def _to_linear(c: np.ndarray) -> np.ndarray:
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _from_linear(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055) * 255.0


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])
_M1_INV = np.linalg.inv(_M1)
_M2_INV = np.linalg.inv(_M2)


def encode_space(rgb: np.ndarray, space: str) -> np.ndarray:
    """sRGB 0-255 (…, 3) -> coordinates of the interpolation space."""
    if space == "srgb":
        return rgb.astype(np.float64)
    lin = _to_linear(rgb.astype(np.float64))
    if space == "linear":
        return lin
    if space == "oklab":
        return np.cbrt(lin @ _M1.T) @ _M2.T
    raise ValueError("gradient space must be 'srgb', 'linear' or 'oklab'")


def decode_space(values: np.ndarray, space: str) -> np.ndarray:
    if space == "srgb":
        return values
    if space == "linear":
        return _from_linear(values)
    lms = values @ _M2_INV.T
    return _from_linear((lms ** 3) @ _M1_INV.T)


def blur_amount(spec) -> tuple[float, dict | None]:
    """(largest radius, progressive spec or None) of a style.blur / backdrop_blur value."""
    if isinstance(spec, dict):
        return max(0.0, float(spec.get("radius", 8))), spec
    return max(0.0, float(spec or 0)), None


def progressive_t(size: tuple[int, int], spec: dict, box_px) -> np.ndarray:
    """0..1 blur strength across the box: 0 at `start`, full at `end` along `angle` (like a linear gradient)."""
    w, h = size
    x0, y0, x1, y1 = box_px
    bw, bh = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    ang = math.radians(float(spec.get("angle", 90)))
    ca, sa = np.float32(math.cos(ang)), np.float32(math.sin(ang))
    xs = np.arange(w, dtype=np.float32)[None, :] + np.float32(0.5)
    ys = np.arange(h, dtype=np.float32)[:, None] + np.float32(0.5)
    proj = ((xs - np.float32((x0 + x1) / 2)) * ca + (ys - np.float32((y0 + y1) / 2)) * sa) \
        / np.float32(abs(bw * float(ca)) + abs(bh * float(sa))) + np.float32(0.5)
    start, end = float(spec.get("start", 0)), float(spec.get("end", 1))
    if abs(end - start) < 1e-6:
        end = start + 1e-6
    return np.clip((proj - np.float32(start)) / np.float32(end - start), np.float32(0.0), np.float32(1.0))


def blur_image(img: Image.Image, radius_px: float, t: np.ndarray | None = None) -> Image.Image:
    """Gaussian blur in premultiplied space; uses OpenCV SIMD when available."""
    from PIL import ImageFilter
    if radius_px <= 0:
        return img
    pre = img.convert("RGBa")
    if t is None:
        if cv2 is not None:
            arr = np.ascontiguousarray(np.asarray(pre), dtype=np.uint8)
            blurred = cv2.GaussianBlur(arr, (0, 0), sigmaX=float(radius_px), sigmaY=float(radius_px),
                                       borderType=cv2.BORDER_REPLICATE)
            return Image.fromarray(blurred, "RGBa").convert("RGBA")
        return pre.filter(ImageFilter.GaussianBlur(radius_px)).convert("RGBA")
    levels = 6
    base = np.asarray(pre, dtype=np.float32)
    stack = [base]
    for i in range(1, levels):
        sig = float(radius_px * i / (levels - 1))
        if cv2 is not None:
            stack.append(cv2.GaussianBlur(base, (0, 0), sigmaX=sig, sigmaY=sig, borderType=cv2.BORDER_REPLICATE))
        else:
            stack.append(np.asarray(pre.filter(ImageFilter.GaussianBlur(sig)), dtype=np.float32))
    f = t.astype(np.float32) * np.float32(levels - 1)
    i0 = np.clip(np.floor(f).astype(np.int32), 0, levels - 2)
    wgt = (f - i0)[..., None]
    out = np.zeros_like(stack[0])
    for i in range(levels - 1):
        m = i0 == i
        if m.any():
            out[m] = stack[i][m] * (np.float32(1.0) - wgt[m]) + stack[i + 1][m] * wgt[m]
    return Image.fromarray(np.clip(out + np.float32(0.5), 0, 255).astype(np.uint8), "RGBa").convert("RGBA")


def apply_noise(img: Image.Image, spec, seed: int, k: float, colors: dict) -> Image.Image:
    """Grain on a painted fill. A number = mono grain (as before); an object = Figma-style noise:
    {amount, mode: mono | duo | multi, size (grain size in units), colors: [c1, c2] (duo), density (duo)}."""
    arr = np.asarray(img, dtype=np.float32).copy()
    h, w = arr.shape[:2]
    rng = np.random.default_rng(seed)
    if not isinstance(spec, dict):
        arr[..., :3] = np.clip(arr[..., :3] + rng.normal(0, float(spec) * 128, (h, w, 1)).astype(np.float32), 0, 255)
        return Image.fromarray(arr.astype(np.uint8), "RGBA")
    amount = max(0.0, min(1.0, float(spec.get("amount", 0.3))))
    mode = str(spec.get("mode", "mono")).lower()
    if mode not in ("mono", "duo", "multi"):
        raise ValueError("noise.mode must be 'mono', 'duo' or 'multi'")
    cell = max(1, int(round(float(spec.get("size", 1)) * k)))
    gh, gw = -(-h // cell), -(-w // cell)

    def grid(channels: int) -> np.ndarray:
        g = rng.normal(0, 1, (gh, gw, channels)).astype(np.float32)
        return np.repeat(np.repeat(g, cell, 0), cell, 1)[:h, :w]

    if mode == "mono":
        arr[..., :3] += grid(1) * np.float32(amount * 128)
    elif mode == "multi":
        arr[..., :3] += grid(3) * np.float32(amount * 128)
    else:
        cols = spec.get("colors") or ["#000000", "#ffffff"]
        c1 = np.array(parse_color(cols[0], colors)[:3], dtype=np.float32)
        c2 = np.array(parse_color(cols[1] if len(cols) > 1 else "#ffffff", colors)[:3], dtype=np.float32)
        density = max(0.0, min(1.0, float(spec.get("density", 0.5))))
        u = np.repeat(np.repeat(rng.random((gh, gw), dtype=np.float32), cell, 0), cell, 1)[:h, :w]
        speck = np.where((u < density)[..., None], c1, c2)
        arr[..., :3] = arr[..., :3] * np.float32(1 - amount) + speck * np.float32(amount)
    arr[..., :3] = np.clip(arr[..., :3], 0, 255)
    return Image.fromarray((arr + np.float32(0.5)).astype(np.uint8), "RGBA")


def roughen(mask: Image.Image, spec, k: float, origin: tuple[float, float]) -> Image.Image:
    """Figma "texture": distress the shape's edge. spec: number (edge movement in units) or
    {amount, size (feature size in units), seed}."""
    if not isinstance(spec, dict):
        spec = {"amount": float(spec)}
    amount = max(0.1, float(spec.get("amount", 2)))
    size = max(0.5, float(spec.get("size", 4)))
    seed = float(spec.get("seed", 1))
    a = np.asarray(mask, dtype=np.float32)
    soft = blur_float(a, amount * k).astype(np.float32) / np.float32(255.0)
    h, w = a.shape
    xs = (np.arange(w, dtype=np.float32)[None, :] + np.float32(0.5)) / np.float32(k) + np.float32(origin[0])
    ys = (np.arange(h, dtype=np.float32)[:, None] + np.float32(0.5)) / np.float32(k) + np.float32(origin[1])
    n = fractal_noise(xs, ys, size, 3, seed)
    out = np.clip((soft + (n - np.float32(0.5)) * np.float32(0.9) - np.float32(0.5)) * np.float32(amount * k * 2)
                  + np.float32(0.5), np.float32(0.0), np.float32(1.0))
    return Image.fromarray((out * np.float32(255.0) + np.float32(0.5)).astype(np.uint8), "L")


def _bilinear(arr: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    h, w = arr.shape[:2]
    xs = np.clip(xs, np.float32(0.0), np.float32(w - 1.001))
    ys = np.clip(ys, np.float32(0.0), np.float32(h - 1.001))
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    fx = (xs - x0)[..., None]
    fy = (ys - y0)[..., None]
    one = np.float32(1.0)
    a, b = arr[y0, x0], arr[y0, x0 + 1]
    c, d = arr[y0 + 1, x0], arr[y0 + 1, x0 + 1]
    return (a * (one - fx) + b * fx) * (one - fy) + (c * (one - fx) + d * fx) * fy


def _remap_rgba(arr: np.ndarray, map_x: np.ndarray, map_y: np.ndarray) -> np.ndarray:
    """Fast SIMD bilinear warp via OpenCV when installed, with NumPy fallback."""
    if cv2 is not None:
        return cv2.remap(arr, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return _bilinear(arr, map_x, map_y)


def glass(backdrop: Image.Image, mask: Image.Image, spec, k: float, colors: dict) -> Image.Image:
    """Refracting liquid glass: SDF lens curvature, chromatic dispersion, Beer-Lambert absorption,
    optional frost blur, and crisp dual-rim Fresnel specular catchlights."""
    if not isinstance(spec, dict):
        spec = {}
    refraction = float(spec.get("refraction", 0.6))
    depth = max(1.0, float(spec.get("depth", 14))) * k
    dispersion = max(0.0, float(spec.get("dispersion", 0.25)))
    frost = max(0.0, float(spec.get("frost", 0))) * k
    intensity = max(0.0, float(spec.get("intensity", 0.55)))
    fresnel = max(0.0, float(spec.get("fresnel", 0.4)))
    ang = math.radians(float(spec.get("light", 225)))
    m = np.asarray(mask, dtype=np.float32)
    h, w = m.shape
    sdf = distance_field(m)
    t_edge = np.clip(sdf / np.float32(depth), np.float32(0.0), np.float32(1.0))
    dome = np.sqrt(np.maximum(np.float32(0.0), np.float32(1.0) - (np.float32(1.0) - t_edge) ** np.float32(2.0)))
    soft = blur_float(m, max(1.5, depth * 0.45)).astype(np.float32) / np.float32(255.0)
    height = dome * np.float32(0.75) + soft * np.float32(0.25)
    if cv2 is not None:
        gx = cv2.Scharr(height, cv2.CV_32F, 1, 0) * np.float32(1.0 / 32.0)
        gy = cv2.Scharr(height, cv2.CV_32F, 0, 1) * np.float32(1.0 / 32.0)
    else:
        gy, gx = np.gradient(height)
    src = backdrop.convert("RGBa")
    if frost > 0:
        src = blur_image(src, frost / 2)
    arr = np.asarray(src, dtype=np.float32)
    xs = np.broadcast_to(np.arange(w, dtype=np.float32)[None, :], (h, w))
    ys = np.broadcast_to(np.arange(h, dtype=np.float32)[:, None], (h, w))
    push = np.float32(refraction * depth * 5.2)
    if dispersion <= 1e-4:
        out = _remap_rgba(arr, (xs + gx * push).astype(np.float32), (ys + gy * push).astype(np.float32))
    else:
        out = np.empty_like(arr)
        mid = _remap_rgba(arr, (xs + gx * push).astype(np.float32), (ys + gy * push).astype(np.float32))
        out[..., 1] = mid[..., 1]
        out[..., 3] = mid[..., 3]
        pr = np.float32(float(push) * (1.0 - dispersion))
        pb = np.float32(float(push) * (1.0 + dispersion))
        out[..., 0] = _remap_rgba(arr, (xs + gx * pr).astype(np.float32), (ys + gy * pr).astype(np.float32))[..., 0]
        out[..., 2] = _remap_rgba(arr, (xs + gx * pb).astype(np.float32), (ys + gy * pb).astype(np.float32))[..., 2]
    if spec.get("tint"):
        tr, tg, tb, ta = parse_color(spec["tint"], colors)
        thick = np.clip(height, np.float32(0.0), np.float32(1.0))[..., None] * np.float32(ta / 255.0)
        tint_rgb = np.array([tr / 255.0, tg / 255.0, tb / 255.0], dtype=np.float32)
        absorb = np.exp(-thick * (np.float32(1.0) - tint_rgb) * np.float32(1.4))
        out[..., :3] = out[..., :3] * absorb + tint_rgb * np.float32(255.0) * thick * np.float32(0.22)
    slope = np.hypot(gx, gy) * np.float32(depth * 2.0)
    lx, ly = np.float32(math.cos(ang)), np.float32(math.sin(ang))
    dot_dir = -(gx * lx + gy * ly) * np.float32(depth * 2.1)
    edge_band = np.clip(np.float32(1.0) - sdf / np.float32(max(2.0, depth * 0.55)), np.float32(0.0), np.float32(1.0))
    rim_top = (np.clip(dot_dir, np.float32(0.0), np.float32(1.0)) ** np.float32(2.2)) * edge_band * np.float32(intensity * 0.95)
    rim_opp = (np.clip(-dot_dir, np.float32(0.0), np.float32(1.0)) ** np.float32(2.6)) * edge_band * np.float32(intensity * 0.42)
    rim_fresnel = (np.clip(slope, np.float32(0.0), np.float32(1.0)) ** np.float32(2.8)) * edge_band * np.float32(fresnel * intensity * 0.65)
    glint = np.clip(rim_top + rim_opp + rim_fresnel, np.float32(0.0), np.float32(0.92))
    out[..., :3] = out[..., :3] + glint[..., None] * (np.float32(255.0) - out[..., :3]) * (out[..., 3:4] / np.float32(255.0))
    out = Image.fromarray(np.clip(out + np.float32(0.5), 0, 255).astype(np.uint8), "RGBa").convert("RGBA")
    return Image.composite(out, backdrop, mask)


def perspective_warp(img: Image.Image, spec: dict | float | int) -> Image.Image:
    """Apply 3D diegetic perspective tilt (rotate_x/rotate_y/rotate_z/fov) and/or cylindrical HUD visor_curve.

    Runs on premultiplied RGBA via OpenCV warpPerspective / remap for crisp halo-free edges, with a
    pure-NumPy bilinear fallback.
    """
    if isinstance(spec, (int, float)):
        spec = {"rotate_y": float(spec)}
    if not isinstance(spec, dict):
        return img
    rx = max(-65.0, min(65.0, float(spec.get("rotate_x", 0.0))))
    ry = max(-65.0, min(65.0, float(spec.get("rotate_y", 0.0))))
    rz = max(-180.0, min(180.0, float(spec.get("rotate_z", 0.0))))
    curve = max(-0.6, min(0.6, float(spec.get("visor_curve", spec.get("curve", 0.0)))))
    fov = max(0.6, min(8.0, float(spec.get("fov", spec.get("depth", 1.8)))))
    if abs(rx) < 1e-4 and abs(ry) < 1e-4 and abs(rz) < 1e-4 and abs(curve) < 1e-4:
        return img

    w, h = img.size
    if w < 2 or h < 2:
        return img
    arr = np.asarray(img.convert("RGBa"), dtype=np.float32)

    # 1. Optional cylindrical visor curvature (barrel/pincushion along X compressing Y cleanly)
    if abs(curve) >= 1e-4:
        cx, cy = (w - 1) * 0.5, (h - 1) * 0.5
        nx = (np.arange(w, dtype=np.float32)[None, :] - cx) / max(1.0, cx)
        ny = (np.arange(h, dtype=np.float32)[:, None] - cy) / max(1.0, cy)
        nx2 = nx * nx
        # Cylindrical bow: edges scale vertically and pull slightly inward toward center
        scale_y = np.float32(1.0) + np.float32(curve) * nx2
        src_y = cy + (ny / np.maximum(np.float32(0.35), scale_y)) * cy
        src_x = cx + nx * (np.float32(1.0) + np.float32(abs(curve) * 0.14) * nx2) * cx
        map_x = np.broadcast_to(src_x, (h, w)).astype(np.float32)
        map_y = np.broadcast_to(src_y, (h, w)).astype(np.float32)
        if cv2 is not None:
            arr = cv2.remap(arr, map_x, map_y, cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0.0, 0.0, 0.0, 0.0))
        else:
            valid = (map_x >= 0) & (map_x <= w - 1) & (map_y >= 0) & (map_y <= h - 1)
            sampled = _bilinear(arr, np.clip(map_x, 0, w - 1), np.clip(map_y, 0, h - 1))
            arr = np.where(valid[..., None], sampled, np.float32(0.0))

    # 2. True 3D projective homography (Rz @ Ry @ Rx) around image center
    if abs(rx) >= 1e-4 or abs(ry) >= 1e-4 or abs(rz) >= 1e-4:
        ax, ay, az = math.radians(rx), math.radians(ry), math.radians(rz)
        cx, cy = w * 0.5, h * 0.5
        f = max(w, h) * fov
        Rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]], dtype=np.float64)
        Ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]], dtype=np.float64)
        Rz = np.array([[math.cos(az), -math.sin(az), 0], [math.sin(az), math.cos(az), 0], [0, 0, 1]], dtype=np.float64)
        R = Rz @ Ry @ Rx
        src_pts = np.array([[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]], dtype=np.float32)
        dst_pts = np.empty((4, 2), dtype=np.float32)
        for i, (px, py) in enumerate(src_pts):
            v = R @ np.array([px - cx, py - cy, 0.0], dtype=np.float64)
            z = max(f * 0.25, f + v[2])
            dst_pts[i, 0] = cx + (v[0] * f) / z
            dst_pts[i, 1] = cy + (v[1] * f) / z
        if cv2 is not None:
            H = cv2.getPerspectiveTransform(src_pts, dst_pts)
            arr = cv2.warpPerspective(
                arr, H, (w, h), flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, borderValue=(0.0, 0.0, 0.0, 0.0),
            )
        else:
            # Pure-NumPy inverse homography fallback
            A = []
            b_vec = []
            for (sx, sy), (dx, dy) in zip(src_pts, dst_pts):
                A.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
                b_vec.append(sx)
                A.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
                b_vec.append(sy)
            coeffs = np.linalg.solve(np.array(A, dtype=np.float64), np.array(b_vec, dtype=np.float64))
            Hinv = np.array([[coeffs[0], coeffs[1], coeffs[2]],
                             [coeffs[3], coeffs[4], coeffs[5]],
                             [coeffs[6], coeffs[7], 1.0]], dtype=np.float64)
            ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
            denom = np.maximum(1e-6, Hinv[2, 0] * xs + Hinv[2, 1] * ys + Hinv[2, 2])
            mx = ((Hinv[0, 0] * xs + Hinv[0, 1] * ys + Hinv[0, 2]) / denom).astype(np.float32)
            my = ((Hinv[1, 0] * xs + Hinv[1, 1] * ys + Hinv[1, 2]) / denom).astype(np.float32)
            valid = (mx >= 0) & (mx <= w - 1) & (my >= 0) & (my <= h - 1)
            sampled = _bilinear(arr, np.clip(mx, 0, w - 1), np.clip(my, 0, h - 1))
            arr = np.where(valid[..., None], sampled, np.float32(0.0))

    return Image.fromarray(np.clip(arr + np.float32(0.5), 0, 255).astype(np.uint8), "RGBa").convert("RGBA")
