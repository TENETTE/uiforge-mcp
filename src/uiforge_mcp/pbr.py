"""Physically-based 2.5D surface shading (Blender/Filament Cook-Torrance GGX + Perspective HDRI + ACES)
and real-time engine PBR texture map baking (Albedo, Tangent Normal, Roughness, Metallic, AO, Height, ORM, Emissive).

Supports dual-lobe GGX specular, curvature edge wear, 5 analytic HDR studio tents plus optional custom
equirectangular HDRI maps (.hdr/.png/.jpg), clearcoat lacquer, linear & radial anisotropic brushed metal,
subsurface wrap, crevice AO, HDR emission, and ACES filmic tone mapping.
"""

from __future__ import annotations

import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from . import effects as fxlib
from . import gpu

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

try:
    import cv2
except ImportError:
    cv2 = None


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, np.float32(0.0), np.float32(1.0))
    return np.where(c <= np.float32(0.04045), c / np.float32(12.92),
                    np.power((c + np.float32(0.055)) / np.float32(1.055), np.float32(2.4)))


def _linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, np.float32(0.0), np.float32(1.0))
    return np.where(c <= np.float32(0.0031308), c * np.float32(12.92),
                    np.float32(1.055) * np.power(c, np.float32(1.0 / 2.4)) - np.float32(0.055))


def _aces_filmic(x: np.ndarray) -> np.ndarray:
    """Narkowicz ACES filmic tone-mapping curve for natural HDR highlight roll-off."""
    a, b, c, d, e = np.float32(2.51), np.float32(0.03), np.float32(2.43), np.float32(0.59), np.float32(0.14)
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), np.float32(0.0), np.float32(1.0))


def _smoothstep(edge0: float | np.ndarray, edge1: float | np.ndarray, x: np.ndarray) -> np.ndarray:
    e0 = np.float32(edge0) if not isinstance(edge0, np.ndarray) else edge0
    e1 = np.float32(edge1) if not isinstance(edge1, np.ndarray) else edge1
    t = np.clip((x - e0) / np.maximum(np.float32(1e-5), e1 - e0), np.float32(0.0), np.float32(1.0))
    return t * t * (np.float32(3.0) - np.float32(2.0) * t)


def _sobel(field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Clean 3x3 Scharr/Sobel gradient (gx, gy) using OpenCV SIMD when available."""
    f = np.ascontiguousarray(field, dtype=np.float32)
    if cv2 is not None:
        gx = cv2.Scharr(f, cv2.CV_32F, 1, 0, scale=1.0 / 32.0, borderType=cv2.BORDER_REPLICATE)
        gy = cv2.Scharr(f, cv2.CV_32F, 0, 1, scale=1.0 / 32.0, borderType=cv2.BORDER_REPLICATE)
        return gx, gy
    gy, gx = np.gradient(f)
    return gx.astype(np.float32), gy.astype(np.float32)


def _gauss_f32(field: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0.05:
        return field
    f = np.ascontiguousarray(field, dtype=np.float32)
    if cv2 is not None:
        return cv2.GaussianBlur(f, (0, 0), sigmaX=float(sigma), sigmaY=float(sigma), borderType=cv2.BORDER_REPLICATE)
    return fxlib.blur_float(f, sigma * 2.0, passes=3).astype(np.float32)


def _bevel_height(alpha_u8: np.ndarray, sdf: np.ndarray, profile: str, bw: float, k: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (bevel_height 0..1, edge_ao 0.65..1.0, edge_wear 0..1) with smooth curvature."""
    h, w = alpha_u8.shape
    u = np.clip(sdf / np.float32(max(0.5, bw)), np.float32(0.0), np.float32(1.0))
    if profile == "flat":
        ones = np.ones((h, w), dtype=np.float32)
        return ones, ones, np.zeros((h, w), dtype=np.float32)
    if profile == "chamfer":
        soft_u = np.clip(u, np.float32(0.0), np.float32(1.0))
        height = soft_u * np.float32(0.88) + np.float32(0.12) * (soft_u * soft_u * (np.float32(3.0) - np.float32(2.0) * soft_u))
        height = _gauss_f32(height, max(0.5, 0.6 * k))
    elif profile == "machined":
        outer = np.clip(u / np.float32(0.28), np.float32(0.0), np.float32(1.0))
        mid = np.clip((u - np.float32(0.28)) / np.float32(0.46), np.float32(0.0), np.float32(1.0))
        inner = np.clip((u - np.float32(0.74)) / np.float32(0.26), np.float32(0.0), np.float32(1.0))
        height = (np.float32(0.44) * np.sqrt(np.maximum(np.float32(0.0), outer * (np.float32(2.0) - outer)))
                  + np.float32(0.36) * mid
                  + np.float32(0.20) * inner * inner * (np.float32(3.0) - np.float32(2.0) * inner))
        height = _gauss_f32(height, max(0.45, 0.45 * k))
    elif profile == "dome":
        ys = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
        xs = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        r2 = np.clip(np.power(np.abs(xs), np.float32(2.6)) + np.power(np.abs(ys), np.float32(2.6)),
                     np.float32(0.0), np.float32(1.0))
        ellip = np.sqrt(np.maximum(np.float32(0.0), np.float32(1.0) - r2))
        edge_round = np.sqrt(np.maximum(np.float32(0.0), u * (np.float32(2.0) - u)))
        height = _gauss_f32(edge_round * np.float32(0.52) + ellip * np.float32(0.48), max(1.1, bw * 0.22 * k))
    elif profile == "facet":
        step1 = np.clip(u / np.float32(0.52), np.float32(0.0), np.float32(1.0))
        step2 = np.clip((u - np.float32(0.52)) / np.float32(0.48), np.float32(0.0), np.float32(1.0))
        height = step1 * np.float32(0.62) + step2 * np.float32(0.38)
        height = _gauss_f32(height, max(0.35, 0.3 * k))
    elif profile == "engraved":
        height = np.float32(1.0) - np.sqrt(np.maximum(np.float32(0.0), u * (np.float32(2.0) - u)))
        height = _gauss_f32(height, max(0.65, 0.65 * k))
    else:
        height = np.sqrt(np.maximum(np.float32(0.0), u * (np.float32(2.0) - u)))
        height = _gauss_f32(height, max(0.65, 0.75 * k))
    ao = np.float32(0.72) + np.float32(0.28) * np.clip(u * np.float32(1.6), np.float32(0.0), np.float32(1.0))
    wear = np.exp(-(((u - np.float32(0.86)) / np.float32(0.16)) ** 2))
    return height, ao, wear


def _decode_rgbe_hdr(path: Path) -> np.ndarray | None:
    """Pure-Python Radiance .hdr (RGBE + adaptive RLE) 32-bit float HDRI decoder."""
    data = path.read_bytes()
    pos = 0
    n = len(data)
    header_end = data.find(b"\n\n")
    if header_end < 0:
        return None
    pos = header_end + 2
    res_end = data.find(b"\n", pos)
    if res_end < 0:
        return None
    res_line = data[pos:res_end].decode("ascii", errors="ignore").strip()
    m = re.match(r"^[+-]Y\s+(\d+)\s+[+-]X\s+(\d+)$", res_line)
    if not m:
        return None
    h, w = int(m.group(1)), int(m.group(2))
    pos = res_end + 1
    rgbe = np.empty((h, w, 4), dtype=np.uint8)
    for y in range(h):
        if pos + 4 > n:
            return None
        b0, b1, b2, b3 = data[pos], data[pos + 1], data[pos + 2], data[pos + 3]
        if b0 == 2 and b1 == 2 and ((b2 << 8) | b3) == w:
            pos += 4
            for ch in range(4):
                x = 0
                while x < w:
                    if pos >= n:
                        return None
                    cnt = data[pos]
                    pos += 1
                    if cnt > 128:
                        run = cnt - 128
                        val = data[pos]
                        pos += 1
                        rgbe[y, x:x + run, ch] = val
                        x += run
                    else:
                        rgbe[y, x:x + cnt, ch] = np.frombuffer(data, dtype=np.uint8, count=cnt, offset=pos)
                        pos += cnt
                        x += cnt
        else:
            row_bytes = w * 4
            if pos + row_bytes > n:
                return None
            rgbe[y] = np.frombuffer(data, dtype=np.uint8, count=row_bytes, offset=pos).reshape(w, 4)
            pos += row_bytes
    exp = rgbe[..., 3].astype(np.int32)
    scale = np.where(exp > 0, np.ldexp(np.float32(1.0), exp - 136), np.float32(0.0)).astype(np.float32)
    rgb = (rgbe[..., :3].astype(np.float32) + np.float32(0.5)) * scale[..., None]
    return np.clip(rgb, np.float32(0.0), np.float32(24.0))


def _decode_exr(path: Path) -> np.ndarray | None:
    """Pure-Python OpenEXR scanline decoder supporting NO_COMPRESSION (0), ZIPS (2) and ZIP (3) in HALF/FLOAT."""
    import struct
    import zlib
    data = path.read_bytes()
    if len(data) < 16 or struct.unpack_from("<I", data, 0)[0] != 20000630:
        return None
    version_flags = struct.unpack_from("<I", data, 4)[0]
    if version_flags & 0x200:
        return None
    pos = 8
    channels: list[tuple[str, int]] = []
    comp = 0
    dw = None
    while pos < len(data):
        end_name = data.find(b"\x00", pos)
        if end_name == pos or end_name < 0:
            pos += 1
            break
        aname = data[pos:end_name].decode("latin1")
        pos = end_name + 1
        end_type = data.find(b"\x00", pos)
        if end_type < 0:
            return None
        pos = end_type + 1
        asize = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        aval = data[pos:pos + asize]
        pos += asize
        if aname == "channels":
            cpos = 0
            while cpos < len(aval) and aval[cpos] != 0:
                ce = aval.find(b"\x00", cpos)
                cname = aval[cpos:ce].decode("latin1")
                ptype = struct.unpack_from("<i", aval, ce + 1)[0]
                channels.append((cname, ptype))
                cpos = ce + 17
        elif aname == "compression" and asize >= 1:
            comp = aval[0]
        elif aname == "dataWindow" and asize >= 16:
            dw = struct.unpack_from("<iiii", aval, 0)
    if not channels or dw is None or comp not in (0, 2, 3):
        return None
    w = dw[2] - dw[0] + 1
    h = dw[3] - dw[1] + 1
    if w <= 0 or h <= 0 or w * h > 33554432:
        return None
    block_lines = 16 if comp == 3 else 1
    n_blocks = (h + block_lines - 1) // block_lines
    offsets = struct.unpack_from(f"<{n_blocks}Q", data, pos)
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    ch_map = {"R": 0, "G": 1, "B": 2}
    for off in offsets:
        y0, csize = struct.unpack_from("<iI", data, off)
        raw = data[off + 8:off + 8 + csize]
        lines = min(block_lines, dw[3] - y0 + 1)
        if comp in (2, 3):
            raw = zlib.decompress(raw)
            buf = np.frombuffer(raw, dtype=np.uint8).copy()
            for i in range(1, buf.size):
                buf[i] = (int(buf[i - 1]) + int(buf[i]) - 128) & 0xFF
            half = (buf.size + 1) // 2
            out_b = np.empty_like(buf)
            out_b[0::2] = buf[:half]
            out_b[1::2] = buf[half:]
            raw = out_b.tobytes()
        bpos = 0
        for row_i in range(lines):
            ry = y0 - dw[1] + row_i
            for cname, ptype in channels:
                dt = np.float16 if ptype == 1 else (np.float32 if ptype == 2 else np.uint32)
                nbytes = w * np.dtype(dt).itemsize
                if 0 <= ry < h and cname in ch_map:
                    vals = np.frombuffer(raw, dtype=dt, count=w, offset=bpos).astype(np.float32)
                    rgb[ry, :, ch_map[cname]] = vals
                bpos += nbytes
    return np.clip(np.nan_to_num(rgb, nan=0.0, posinf=24.0, neginf=0.0), np.float32(0.0), np.float32(24.0))


@lru_cache(maxsize=8)
def _load_env_map(path_str: str, mtime: float) -> tuple[np.ndarray, ...]:
    """Load an equirectangular .hdr / .exr / .png / .jpg panorama and build 5 roughness mip levels."""
    p = Path(path_str).expanduser()
    if not p.is_file():
        raise ValueError(f"pbr env_map file not found: {p}")
    img_lin = None
    suf = p.suffix.lower()
    if suf == ".hdr":
        try:
            img_lin = _decode_rgbe_hdr(p)
        except Exception:
            img_lin = None
    elif suf == ".exr":
        try:
            img_lin = _decode_exr(p)
        except Exception:
            img_lin = None
    if img_lin is None and cv2 is not None and suf in (".hdr", ".exr"):
        raw = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if raw is not None and raw.ndim == 3 and raw.shape[2] >= 3:
            img_lin = np.ascontiguousarray(raw[..., 2::-1], dtype=np.float32)
            img_lin = np.clip(img_lin, np.float32(0.0), np.float32(24.0))
    if img_lin is None:
        if suf == ".exr":
            raise ValueError(f"could not decode EXR file '{p}' (unsupported EXR compression - use uncompressed/ZIP .exr or Radiance .hdr)")
        pil = Image.open(p).convert("RGB")
        if pil.width > 512:
            pil = pil.resize((512, max(128, int(round(pil.height * 512 / pil.width)))), Image.LANCZOS)
        img_lin = _srgb_to_linear(np.asarray(pil, dtype=np.float32) / np.float32(255.0)) * np.float32(2.2)
    elif img_lin.shape[1] > 512 and cv2 is not None:
        nh = max(128, int(round(img_lin.shape[0] * 512 / img_lin.shape[1])))
        img_lin = cv2.resize(img_lin, (512, nh), interpolation=cv2.INTER_AREA)
    mips = [img_lin]
    for sig in (2.0, 6.0, 14.0, 28.0):
        if cv2 is not None:
            mips.append(cv2.GaussianBlur(img_lin, (0, 0), sigmaX=sig, sigmaY=sig, borderType=cv2.BORDER_REFLECT_101))
        else:
            ch = [fxlib.blur_float(img_lin[..., c], sig * 2.0, passes=2).astype(np.float32) for c in range(3)]
            mips.append(np.stack(ch, axis=-1))
    return tuple(mips)


def _sample_env_map(path_str: str, rx: np.ndarray, ry: np.ndarray, rz: np.ndarray,
                    roughness: np.ndarray, env_rot: float) -> np.ndarray:
    p = Path(path_str).expanduser()
    mips = _load_env_map(str(p), p.stat().st_mtime if p.is_file() else 0.0)
    eh, ew = mips[0].shape[:2]
    rn = np.maximum(np.float32(1e-5), np.sqrt(rx * rx + ry * ry + rz * rz))
    ux, uy, uz = rx / rn, ry / rn, rz / rn
    u = np.mod((np.arctan2(ux, uz) + np.float32(env_rot)) / np.float32(2.0 * math.pi) + np.float32(0.5), np.float32(1.0))
    v = np.arccos(np.clip(-uy, np.float32(-1.0), np.float32(1.0))) / np.float32(math.pi)
    mx = (u * np.float32(ew - 1)).astype(np.float32)
    my = (v * np.float32(eh - 1)).astype(np.float32)
    r_mean = float(np.clip(roughness.mean(), 0.0, 1.0))
    lvl = r_mean * (len(mips) - 1)
    i0 = min(len(mips) - 1, int(math.floor(lvl)))
    i1 = min(len(mips) - 1, i0 + 1)
    t = np.float32(lvl - i0)
    if cv2 is not None:
        s0 = cv2.remap(mips[i0], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        s1 = cv2.remap(mips[i1], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP) if i1 != i0 else s0
    else:
        xi = np.clip(mx.astype(np.int32), 0, ew - 1)
        yi = np.clip(my.astype(np.int32), 0, eh - 1)
        s0 = mips[i0][yi, xi]
        s1 = mips[i1][yi, xi] if i1 != i0 else s0
    return s0 * (np.float32(1.0) - t) + s1 * t


def _softbox_rect(x: np.ndarray, y: np.ndarray, cx: float, cy: float, hw: float, hh: float,
                  blur: np.ndarray) -> np.ndarray:
    """Roughness-convolved broad curved studio softbox light source."""
    dx = np.abs(x - np.float32(cx)) - np.float32(hw)
    dy = np.abs(y - np.float32(cy)) - np.float32(hh)
    sd = np.hypot(np.maximum(dx, np.float32(0.0)), np.maximum(dy, np.float32(0.0))) + np.minimum(np.maximum(dx, dy), np.float32(0.0))
    edge = np.float32(0.11) + blur * np.float32(0.45)
    return (np.float32(1.0) - _smoothstep(-edge * np.float32(0.35), edge, sd)) / (np.float32(1.0) + blur * np.float32(1.6))


def _studio_ibl(rx: np.ndarray, ry: np.ndarray, rz: np.ndarray, roughness: np.ndarray,
                env_rot: float, preset: str = "bright") -> np.ndarray:
    """High-contrast HDR product-photography cyclorama light tent sampled along reflection vector.
    Presets: bright, warm, dark, sunset, cyberpunk."""
    ca, sa = np.float32(math.cos(env_rot)), np.float32(math.sin(env_rot))
    rrx = rx * ca - ry * sa
    rry = rx * sa + ry * ca
    blur = np.clip(roughness * roughness, np.float32(0.006), np.float32(0.95))

    diag = rrx * np.float32(0.42) + rry * np.float32(0.91)
    sky_t = _smoothstep(-0.72, 0.58, -diag)
    if preset == "warm":
        top_c = np.array([0.52, 0.41, 0.28], dtype=np.float32)
        bot_c = np.array([0.07, 0.045, 0.025], dtype=np.float32)
        key_c = np.array([3.3, 2.75, 1.98], dtype=np.float32)
        fill_c = np.array([1.45, 1.18, 0.88], dtype=np.float32)
        rim_c = np.array([1.15, 0.96, 0.82], dtype=np.float32)
    elif preset == "dark":
        top_c = np.array([0.26, 0.30, 0.38], dtype=np.float32)
        bot_c = np.array([0.025, 0.028, 0.038], dtype=np.float32)
        key_c = np.array([3.0, 3.1, 3.2], dtype=np.float32)
        fill_c = np.array([1.05, 1.28, 1.65], dtype=np.float32)
        rim_c = np.array([0.95, 1.22, 1.75], dtype=np.float32)
    elif preset == "sunset":
        top_c = np.array([0.62, 0.36, 0.30], dtype=np.float32)
        bot_c = np.array([0.06, 0.05, 0.09], dtype=np.float32)
        key_c = np.array([3.8, 2.35, 1.35], dtype=np.float32)
        fill_c = np.array([1.1, 1.35, 2.1], dtype=np.float32)
        rim_c = np.array([1.8, 1.0, 1.3], dtype=np.float32)
    elif preset == "cyberpunk":
        top_c = np.array([0.16, 0.28, 0.45], dtype=np.float32)
        bot_c = np.array([0.08, 0.02, 0.10], dtype=np.float32)
        key_c = np.array([1.3, 3.4, 3.8], dtype=np.float32)
        fill_c = np.array([3.4, 0.8, 2.6], dtype=np.float32)
        rim_c = np.array([2.8, 1.2, 3.2], dtype=np.float32)
    else:
        top_c = np.array([0.40, 0.45, 0.54], dtype=np.float32)
        bot_c = np.array([0.055, 0.062, 0.08], dtype=np.float32)
        key_c = np.array([3.3, 3.25, 3.15], dtype=np.float32)
        fill_c = np.array([1.25, 1.42, 1.72], dtype=np.float32)
        rim_c = np.array([1.08, 1.35, 1.82], dtype=np.float32)

    base = bot_c + (top_c - bot_c) * sky_t[..., None]
    neg_w = np.float32(0.11) + blur * np.float32(0.36)
    neg_flag_1 = np.exp(-((diag - np.float32(0.12)) ** 2) / (neg_w * neg_w * np.float32(2.4)))
    neg_flag_2 = np.exp(-((rry - np.float32(0.46)) ** 2) / (neg_w * neg_w * np.float32(3.2)))
    base = base * (np.float32(1.0) - np.clip(neg_flag_1 * np.float32(0.72) + neg_flag_2 * np.float32(0.48),
                                            np.float32(0.0), np.float32(0.80)))[..., None]

    sb_key = _softbox_rect(rrx, rry, -0.22, -0.56, 0.78, 0.22, blur)
    sb_strip = np.exp(-(((diag + np.float32(0.36)) ** 2) / (np.float32(0.018) + blur * np.float32(0.18)))) \
        / (np.float32(1.0) + blur * np.float32(2.0)) * np.float32(0.92)
    sb_rim = _softbox_rect(rrx, rry, 0.30, 0.64, 0.74, 0.18, blur) * np.float32(0.95)
    sb_fill = np.exp(-(((rrx + np.float32(0.68)) ** 2) / (np.float32(0.08) + blur * np.float32(0.35)))) * np.float32(0.55)

    return (base
            + sb_key[..., None] * key_c
            + sb_strip[..., None] * key_c * np.float32(0.62)
            + sb_fill[..., None] * fill_c
            + sb_rim[..., None] * rim_c)


def _ggx_direct(nx: np.ndarray, ny: np.ndarray, nz: np.ndarray,
                vx: np.ndarray, vy: np.ndarray, vz: np.ndarray,
                lx: float, ly: float, lz: float,
                radiance: np.ndarray, albedo_lin: np.ndarray, f0: np.ndarray, metallic: np.ndarray,
                roughness: np.ndarray, sss: float, aniso: float,
                tx: np.ndarray | float, ty: np.ndarray | float) -> np.ndarray:
    """Direct Filament/Blender dual-lobe Cook-Torrance GGX light evaluation with perspective view V."""
    lxf, lyf, lzf = np.float32(lx), np.float32(ly), np.float32(lz)
    hx = lxf + vx
    hy = lyf + vy
    hz = lzf + vz
    hn = np.maximum(np.float32(1e-5), np.sqrt(hx * hx + hy * hy + hz * hz))
    hxf, hyf, hzf = hx / hn, hy / hn, hz / hn

    ndv = np.maximum(nx * vx + ny * vy + nz * vz, np.float32(1e-4))
    ndl_raw = nx * lxf + ny * lyf + nz * lzf
    ndl = np.clip(ndl_raw, np.float32(0.0), np.float32(1.0))
    ndh = np.clip(nx * hxf + ny * hyf + nz * hzf, np.float32(0.0), np.float32(1.0))
    vdh = np.clip(vx * hxf + vy * hyf + vz * hzf, np.float32(0.0), np.float32(1.0))

    alpha = np.maximum(np.float32(0.003), roughness * roughness)
    if aniso > 0.01:
        at = np.maximum(np.float32(0.012), alpha * np.float32(1.0 + aniso * 2.6))
        ab = np.maximum(np.float32(0.005), alpha * np.float32(1.0 - aniso * 0.72))
        bx_ = -ty
        by_ = tx
        tdh = hxf * tx + hyf * ty
        bdh = hxf * bx_ + hyf * by_
        d_den = (tdh / at) ** 2 + (bdh / ab) ** 2 + ndh * ndh
        D = np.float32(1.0) / (np.float32(math.pi) * at * ab * d_den * d_den + np.float32(1e-5))
    else:
        a2 = alpha * alpha
        d_den = ndh * ndh * (a2 - np.float32(1.0)) + np.float32(1.0)
        D_main = a2 / (np.float32(math.pi) * d_den * d_den + np.float32(1e-5))
        a_wide = np.minimum(np.float32(0.85), alpha * np.float32(2.6) + np.float32(0.08))
        aw2 = a_wide * a_wide
        dw_den = ndh * ndh * (aw2 - np.float32(1.0)) + np.float32(1.0)
        D_tail = aw2 / (np.float32(math.pi) * dw_den * dw_den + np.float32(1e-5))
        D = D_main * np.float32(0.84) + D_tail * np.float32(0.16)

    a2 = alpha * alpha
    ggx_l = ndv * np.sqrt((-ndl * a2 + ndl) * ndl + a2 + np.float32(1e-5))
    ggx_v = ndl * np.sqrt((-ndv * a2 + ndv) * ndv + a2 + np.float32(1e-5))
    V = np.float32(0.5) / (ggx_v + ggx_l + np.float32(1e-5))

    one = np.float32(1.0)
    fres = f0 + (one - f0) * np.power(one - vdh, np.float32(5.0))[..., None]
    spec = (D * V)[..., None] * fres

    kd = (one - fres) * (one - metallic)[..., None]
    diff = kd * albedo_lin * np.float32(1.0 / math.pi)
    out = (diff * ndl[..., None] + spec * ndl[..., None]) * radiance
    if sss > 0.0:
        wrap = np.clip((ndl_raw + np.float32(0.55)) / np.float32(1.55), np.float32(0.0), np.float32(1.0))
        sub = (one - metallic)[..., None] * albedo_lin * (wrap * wrap)[..., None] * np.float32(sss * 0.36) * radiance
        out = out + sub
    return out


def compute_pbr_fields(fill_img: Image.Image, shape_mask: Image.Image, spec: dict[str, Any], k: float,
                       bump: np.ndarray | None = None, sdf: np.ndarray | None = None) -> dict[str, Any]:
    """Compute physical surface channels (albedo, normal, roughness, metallic, ao, height, emissive, wear)."""
    arr = np.asarray(fill_img, dtype=np.float32)
    alpha_u8 = np.asarray(shape_mask, dtype=np.uint8)
    h, w = alpha_u8.shape
    albedo_lin = _srgb_to_linear(arr[..., :3] / np.float32(255.0))
    fill_a = arr[..., 3] / np.float32(255.0)

    bevel_size = max(0.5, float(spec.get("bevel_size", 6.0)))
    bevel_depth = float(spec.get("bevel_depth", 1.15))
    profile = str(spec.get("profile", "round")).lower()
    metallic_val = float(spec.get("metallic", 0.0))
    rough_val = max(0.04, min(0.98, float(spec.get("roughness", 0.35))))
    bump_str = float(spec.get("bump_strength", 0.30 if bump is not None else 0.0))
    ao_str = max(0.0, min(1.0, float(spec.get("ao", 0.35))))
    emissive_amt = max(0.0, float(spec.get("emissive", 0.0)))
    wear_amt = max(0.0, min(1.0, float(spec.get("wear", 0.14 if metallic_val > 0.5 else 0.08))))
    crown = float(spec.get("crown", 0.22 if metallic_val > 0.5 else 0.14))

    ys_c = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    xs_c = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]

    d_u = sdf if (sdf is not None and sdf.shape == (h, w)) else fxlib.distance_field(alpha_u8, k)
    bev_h, edge_ao, edge_wear = _bevel_height(alpha_u8, d_u, profile, bevel_size, k)
    gx, gy = _sobel(bev_h)
    slope = np.float32(bevel_size * k * bevel_depth * (0.9 if profile == "dome" else 1.25))
    nx = -gx * slope + xs_c * np.float32(crown)
    ny = -gy * slope + ys_c * np.float32(crown)

    rough = np.full((h, w), np.float32(rough_val), dtype=np.float32)
    ao = edge_ao.copy()
    height_out = bev_h.copy()
    if bump is not None and bump.shape == (h, w):
        bf = bump.astype(np.float32, copy=False)
        if bump_str > 0:
            bgx, bgy = _sobel(bf)
            bs = np.float32(bump_str * 4.5 * k)
            nx = nx - bgx * bs
            ny = ny - bgy * bs
        rough = np.clip(rough + (np.float32(0.5) - bf) * np.float32(spec.get("roughness_var", 0.14)),
                        np.float32(0.03), np.float32(0.98))
        ao = ao * (np.float32(1.0) - np.float32(ao_str) * np.clip((np.float32(0.58) - bf) * np.float32(1.5),
                                                                  np.float32(0.0), np.float32(1.0)))
        height_out = np.clip(bev_h * np.float32(0.65) + bf * np.float32(0.35), np.float32(0.0), np.float32(1.0))

    if profile == "facet":
        dx_f = (np.abs(xs_c) - np.float32(0.52)) / np.float32(0.48)
        dy_f = (np.abs(ys_c) - np.float32(0.48)) / np.float32(0.52)
        in_table = _smoothstep(bevel_size * 0.85, bevel_size * 1.15, d_u)
        fx_dir = np.where(dx_f > dy_f, np.sign(xs_c), np.sign(xs_c) * np.float32(0.28))
        fy_dir = np.where(dy_f >= dx_f, np.sign(ys_c), np.sign(ys_c) * np.float32(0.28))
        step_tilt = np.where(d_u < np.float32(bevel_size * 0.52), np.float32(0.95), np.float32(0.52))
        crown_k = np.float32(1.0) - in_table
        nx = nx * (np.float32(1.0) - crown_k * np.float32(0.75)) + fx_dir * step_tilt * crown_k
        ny = ny * (np.float32(1.0) - crown_k * np.float32(0.75)) + fy_dir * step_tilt * crown_k

    if wear_amt > 0.005:
        rough = np.clip(rough - edge_wear * np.float32(wear_amt * 0.25), np.float32(0.03), np.float32(0.98))
        albedo_lin = np.clip(albedo_lin * (np.float32(1.0) + edge_wear[..., None] * np.float32(wear_amt * 0.45)),
                             np.float32(0.0), np.float32(1.0))

    norm = np.sqrt(nx * nx + ny * ny + np.float32(1.0))
    nx, ny, nz = nx / norm, ny / norm, np.float32(1.0) / norm
    metallic = np.full((h, w), np.float32(metallic_val), dtype=np.float32)

    if emissive_amt > 0:
        lum = np.float32(0.2126) * albedo_lin[..., 0] + np.float32(0.7152) * albedo_lin[..., 1] + np.float32(0.0722) * albedo_lin[..., 2]
        hot = np.clip((lum - np.float32(0.16)) * np.float32(2.4), np.float32(0.0), np.float32(1.0))
        emissive_lin = albedo_lin * hot[..., None] * np.float32(emissive_amt)
    else:
        emissive_lin = np.zeros((h, w, 3), dtype=np.float32)

    return {"albedo_lin": albedo_lin, "fill_a": fill_a, "nx": nx, "ny": ny, "nz": nz, "rough": rough,
            "metallic": metallic, "ao": ao, "height": height_out, "emissive_lin": emissive_lin,
            "wear": edge_wear, "xs_c": xs_c, "ys_c": ys_c, "d_u": d_u}


def shade_pbr(fill_img: Image.Image, shape_mask: Image.Image, spec: dict[str, Any], k: float,
              bump: np.ndarray | None = None, sdf: np.ndarray | None = None) -> Image.Image:
    """Apply full linear-HDR Cook-Torrance GGX + Perspective Studio/Custom HDRI + ACES Filmic shading."""
    f = compute_pbr_fields(fill_img, shape_mask, spec, k, bump=bump, sdf=sdf)
    albedo_lin, fill_a = f["albedo_lin"], f["fill_a"]
    nx, ny, nz = f["nx"], f["ny"], f["nz"]
    rough, metallic, ao = f["rough"], f["metallic"], f["ao"]
    xs_c, ys_c, d_u = f["xs_c"], f["ys_c"], f["d_u"]
    h, w = rough.shape

    profile = str(spec.get("profile", "round")).lower()
    ior = max(1.1, float(spec.get("ior", 1.5)))
    clearcoat = max(0.0, min(1.0, float(spec.get("clearcoat", 0.0))))
    cc_rough = max(0.03, min(0.5, float(spec.get("clearcoat_roughness", 0.06))))
    aniso = max(0.0, min(0.95, float(spec.get("anisotropy", 0.0))))
    brush_mode = spec.get("brush_angle", 0.0)
    sss = max(0.0, min(1.0, float(spec.get("sss", 0.0))))
    env_rot = math.radians(float(spec.get("env_rotation", 0.0)))
    env_str = float(spec.get("env", 1.0))
    env_map = spec.get("env_map")
    exposure = float(spec.get("exposure", 1.02))
    studio = str(spec.get("studio", "bright")).lower()
    cam_fov = float(spec.get("fov", 0.42))
    key_ang = math.radians(float(spec.get("angle", 225.0)))
    key_alt = math.radians(max(10.0, min(80.0, float(spec.get("altitude", 46.0)))))

    _pbr_backend = gpu.backend_name(w * h)
    if (not env_map and aniso <= 0.01 and str(brush_mode).lower() != "radial"
            and profile not in ("facet", "dome") and spec.get("shine") is None
            and (_pbr_backend == "wgpu" or (_pbr_backend == "cuda" and gpu.wgpu_available()))):
        from . import gpu_wgpu
        wgpu_img = gpu_wgpu.shade_pbr_wgpu(f, spec)
        if wgpu_img is not None:
            return Image.fromarray(wgpu_img, "RGBA")

    aspect = float(w) / max(1.0, float(h))
    vx_raw = -xs_c * np.float32(cam_fov * min(1.35, max(0.75, aspect * 0.65)))
    vy_raw = -ys_c * np.float32(cam_fov)
    v_norm = np.sqrt(vx_raw * vx_raw + vy_raw * vy_raw + np.float32(1.0))
    vx, vy, vz = vx_raw / v_norm, vy_raw / v_norm, np.float32(1.0) / v_norm

    f0_d = np.float32(((ior - 1.0) / (ior + 1.0)) ** 2)
    f0 = f0_d * (np.float32(1.0) - metallic)[..., None] + albedo_lin * metallic[..., None]

    is_radial = str(brush_mode).lower() == "radial"
    if is_radial:
        ys_r = (np.arange(h, dtype=np.float32) - np.float32(h * 0.5))[:, None]
        xs_r = (np.arange(w, dtype=np.float32) - np.float32(w * 0.5))[None, :]
        rl = np.maximum(np.float32(1e-4), np.hypot(xs_r, ys_r))
        tx: np.ndarray | float = -ys_r / rl
        ty: np.ndarray | float = xs_r / rl
    else:
        ba = math.radians(float(brush_mode))
        tx = np.float32(math.cos(ba))
        ty = np.float32(math.sin(ba))

    lx1 = math.cos(key_ang) * math.cos(key_alt)
    ly1 = math.sin(key_ang) * math.cos(key_alt)
    lz1 = math.sin(key_alt)
    key_rad = np.array([2.25, 2.15, 2.0], dtype=np.float32)
    rim_rad = np.array([0.72, 0.88, 1.15], dtype=np.float32)
    color = _ggx_direct(nx, ny, nz, vx, vy, vz, lx1, ly1, lz1, key_rad, albedo_lin, f0, metallic, rough, sss, aniso, tx, ty)
    color = color + _ggx_direct(nx, ny, nz, vx, vy, vz, -lx1 * 0.85, -ly1 * 0.85, 0.42, rim_rad, albedo_lin, f0, metallic, rough, sss * 0.45, aniso, tx, ty)

    ndv = np.maximum(nx * vx + ny * vy + nz * vz, np.float32(1e-4))
    rx = np.float32(2.0) * ndv * nx - vx
    ry = np.float32(2.0) * ndv * ny - vy
    rz = np.float32(2.0) * ndv * nz - vz

    def _sample_ibl(srx, sry, srz, srough):
        if env_map:
            return _sample_env_map(str(env_map), srx, sry, srz, srough, env_rot)
        return _studio_ibl(srx, sry, srz, srough, env_rot, studio)

    if env_str > 0:
        erx, ery, erz = rx, ry, rz
        if aniso > 0.05:
            bx_ = -ty
            by_ = tx
            r_along = erx * tx + ery * ty
            r_across = erx * bx_ + ery * by_
            stretch = np.float32(1.0 - aniso * 0.65)
            erx = r_along * tx * stretch + r_across * bx_
            ery = r_along * ty * stretch + r_across * by_
        env_spec = _sample_ibl(erx, ery, erz, rough)
        f_ibl = f0 + (np.maximum(np.float32(1.0) - rough[..., None], f0) - f0) * np.power(np.float32(1.0) - ndv, np.float32(5.0))[..., None]
        spec_ibl = env_spec * f_ibl * (np.float32(0.88) + np.float32(0.32) * metallic[..., None])
        diff_ibl = (np.float32(1.0) - f_ibl) * (np.float32(1.0) - metallic)[..., None] * albedo_lin * np.array([0.36, 0.38, 0.43], dtype=np.float32)
        color = color + (spec_ibl + diff_ibl) * np.float32(env_str) * ao[..., None]

    if is_radial:
        az_r = np.arctan2(ys_c, xs_c)
        bowtie = np.power(np.abs(np.cos(az_r * np.float32(2.0) - np.float32(key_ang * 2.0))), np.float32(2.2))
        bowtie_sec = np.power(np.abs(np.cos(az_r * np.float32(2.0) - np.float32(key_ang * 2.0 + 0.55))), np.float32(6.0))
        color = color * (np.float32(0.52) + np.float32(0.82) * bowtie[..., None]) \
            + f0 * bowtie_sec[..., None] * np.float32(1.15) * ao[..., None]

    if clearcoat > 0.01:
        cc_f0 = np.full((h, w, 3), np.float32(0.045), dtype=np.float32)
        cc_m = np.zeros((h, w), dtype=np.float32)
        cc_r = np.full((h, w), np.float32(cc_rough), dtype=np.float32)
        cc_direct = _ggx_direct(nx, ny, nz, vx, vy, vz, lx1, ly1, lz1, key_rad, np.zeros_like(albedo_lin), cc_f0, cc_m, cc_r, 0.0, 0.0, 1.0, 0.0)
        cc_env = _sample_ibl(rx, ry, rz, cc_r)
        cc_f = np.float32(0.045) + np.float32(0.955) * np.power(np.float32(1.0) - ndv, np.float32(5.0))
        color = color + (cc_direct + cc_env * cc_f[..., None] * np.float32(0.75)) * np.float32(clearcoat)

    if profile == "facet":
        ys_n = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        xs_n = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
        caustic = np.exp(-(((xs_n - np.float32(0.68)) ** 2) * np.float32(8.5) + ((ys_n - np.float32(0.72)) ** 2) * np.float32(10.5)))
        fire_r = np.exp(-(((xs_n - np.float32(0.21)) ** 2) * np.float32(55.0) + ((ys_n - np.float32(0.22)) ** 2) * np.float32(55.0)))
        fire_g = np.exp(-(((xs_n - np.float32(0.225)) ** 2) * np.float32(55.0) + ((ys_n - np.float32(0.23)) ** 2) * np.float32(55.0)))
        fire_b = np.exp(-(((xs_n - np.float32(0.24)) ** 2) * np.float32(55.0) + ((ys_n - np.float32(0.24)) ** 2) * np.float32(55.0)))
        fire = np.stack([fire_r, fire_g, fire_b], axis=-1) * np.float32(2.1)
        color = color + albedo_lin * caustic[..., None] * np.float32(1.55) + fire
    elif sss > 0.45 and profile == "dome":
        ys_n = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        xs_n = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
        trans = np.exp(-(((xs_n - np.float32(0.64)) ** 2) * np.float32(6.0) + ((ys_n - np.float32(0.74)) ** 2) * np.float32(8.0)))
        color = color + albedo_lin * trans[..., None] * np.float32(sss * 0.72)

    if spec.get("shine") is not None:
        s_val = float(spec["shine"])
        ys_n = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        xs_n = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
        diag = (xs_n * np.float32(0.75) + ys_n * np.float32(0.25)) - np.float32(s_val * 1.4 - 0.2)
        sweep = np.exp(-((diag / np.float32(0.075)) ** 2)) * np.float32(1.6)
        color = color + sweep[..., None] * (np.float32(0.5) + np.float32(0.5) * f0)

    color = color + f["emissive_lin"]

    srgb = _linear_to_srgb(_aces_filmic(color * np.float32(exposure))) * np.float32(255.0)
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[..., :3] = np.clip(srgb + np.float32(0.5), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(fill_a * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def bake_pbr_maps(fill_img: Image.Image, shape_mask: Image.Image, spec: dict[str, Any], k: float,
                  bump: np.ndarray | None = None, sdf: np.ndarray | None = None,
                  normal_format: str = "opengl") -> dict[str, Image.Image]:
    """Bake real-time engine PBR texture maps for one element (Albedo, Tangent Normal, Roughness, Metallic, AO, Height, ORM, Emissive)."""
    f = compute_pbr_fields(fill_img, shape_mask, spec, k, bump=bump, sdf=sdf)
    h, w = f["rough"].shape
    albedo_srgb = (_linear_to_srgb(f["albedo_lin"]) * np.float32(255.0) + np.float32(0.5)).clip(0, 255).astype(np.uint8)
    alpha_u8 = np.clip(f["fill_a"] * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    albedo = np.dstack([albedo_srgb, alpha_u8])

    y_sign = np.float32(-1.0) if str(normal_format).lower() == "opengl" else np.float32(1.0)
    n_rgb = np.empty((h, w, 3), dtype=np.uint8)
    n_rgb[..., 0] = np.clip((f["nx"] * np.float32(0.5) + np.float32(0.5)) * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    n_rgb[..., 1] = np.clip((f["ny"] * y_sign * np.float32(0.5) + np.float32(0.5)) * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    n_rgb[..., 2] = np.clip((f["nz"] * np.float32(0.5) + np.float32(0.5)) * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    normal_rgba = np.dstack([n_rgb, alpha_u8])

    r_u8 = np.clip(f["rough"] * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    m_u8 = np.clip(f["metallic"] * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    ao_u8 = np.clip(f["ao"] * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    ht_u8 = np.clip(f["height"] * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
    em_srgb = (_linear_to_srgb(_aces_filmic(f["emissive_lin"])) * np.float32(255.0) + np.float32(0.5)).clip(0, 255).astype(np.uint8)

    return {
        "albedo": Image.fromarray(albedo, "RGBA"),
        "normal": Image.fromarray(normal_rgba, "RGBA"),
        "roughness": Image.fromarray(np.dstack([r_u8, r_u8, r_u8, alpha_u8]), "RGBA"),
        "metallic": Image.fromarray(np.dstack([m_u8, m_u8, m_u8, alpha_u8]), "RGBA"),
        "ao": Image.fromarray(np.dstack([ao_u8, ao_u8, ao_u8, alpha_u8]), "RGBA"),
        "height": Image.fromarray(np.dstack([ht_u8, ht_u8, ht_u8, alpha_u8]), "RGBA"),
        "orm": Image.fromarray(np.dstack([ao_u8, r_u8, m_u8, alpha_u8]), "RGBA"),
        "emissive": Image.fromarray(np.dstack([em_srgb, alpha_u8]), "RGBA"),
    }
