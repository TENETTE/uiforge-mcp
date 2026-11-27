"""Scene renderer: turns canvas elements into antialiased RGBA pixels.

Shapes are rasterised as supersampled coverage masks (drawn at SSx and box
filtered down), then painted and composited with effects at output resolution.
All element coordinates are in canvas units; ``k`` is pixels per unit (1 = 1x).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import zlib
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import effects as fxlib
from . import geometry as geo
from . import raster
from .colors import parse_color
from . import shader, shaping
from .fonts import FontLibrary, load_font, missing_glyphs, parse_weight

SS = 4
MAX_MASK_PIXELS = 40_000_000
MAX_OUTPUT_PIXELS = 140_000_000
TEXT_STYLE_KEYS = ("font", "weight", "size", "letter_spacing", "line_height", "uppercase", "italic", "case",
                   "features", "axes", "paragraph_spacing", "indent", "trim")


def _ot_features(spec: Any, case: str) -> dict:
    """OpenType features for HarfBuzz: {"smcp": 1, "tnum": 1} or ["smcp", "tnum"]; small caps from case."""
    if spec is None or spec is False:
        feats: dict = {}
    elif isinstance(spec, dict):
        feats = {str(k): int(v) if not isinstance(v, bool) else int(v) for k, v in spec.items()}
    elif isinstance(spec, (list, tuple)):
        feats = {str(k): 1 for k in spec}
    else:
        raise ValueError('features must be like ["smcp", "tnum"] or {"liga": 0, "ss01": 1}')
    for tag in feats:
        if len(tag) != 4:
            raise ValueError(f"OpenType feature tags have 4 letters (smcp, tnum, liga, ss01...), got '{tag}'")
    if case in ("small-caps", "all-small-caps"):
        feats.setdefault("smcp", 1)
        if case == "all-small-caps":
            feats.setdefault("c2sc", 1)
    return feats


def _letter_case(text: str, case: str) -> str:
    """Non-destructive letter case like Figma's: upper, lower, title (Capitalize), tr-upper / tr-lower."""
    if not case or case in ("none", "small-caps", "all-small-caps"):
        return text
    if case == "upper":
        return text.upper()
    if case == "tr-upper":
        return _tr_upper(text)
    if case == "lower":
        return text.lower()
    if case == "tr-lower":
        return text.replace("I", "\u0131").replace("\u0130", "i").lower()
    if case in ("title", "capitalize"):
        return " ".join(w[:1].upper() + w[1:] for w in text.split(" "))
    raise ValueError("case must be 'upper', 'lower', 'title', 'tr-upper', 'tr-lower' or 'none'")
VECTOR_TYPES = {"rect", "ellipse", "polygon", "line", "path", "arc", "ticks", "boolean"}
BOOLEAN_OPS = ("union", "subtract", "intersect", "exclude")
BITMAP_TYPES = {"image", "instance"}
WIDGET_TYPES = {"input", "scroll", "slider", "toggle", "dropdown"}
MAX_INSTANCE_DEPTH = 6
LINE_TYPES = {"line", "arc", "ticks"}
BLENDS = ("normal", "add", "screen", "multiply", "overlay", "soft-light", "hard-light", "color-dodge",
          "color-burn", "darken", "lighten", "difference", "erase")
CUT_K = math.tan(math.pi / 8)

Box = tuple[float, float, float, float]



def resolve_style(style: Any, theme: dict) -> dict:
    """Expand a style reference. ``style`` is None, a theme style name, or a dict
    (optionally with ``"use": "<theme style name>"`` as its base)."""
    styles = theme.get("styles", {})

    def lookup(name: str, depth: int = 0) -> dict:
        if name not in styles:
            known = ", ".join(sorted(styles)) or "(theme has no styles)"
            raise ValueError(f"Unknown theme style '{name}'. Known: {known}")
        if depth > 8:
            raise ValueError(f"Theme style reference loop at '{name}'")
        base = dict(styles[name])
        parent = base.pop("use", None)
        if parent:
            merged = lookup(parent, depth + 1)
            merged.update(base)
            return merged
        return base

    if style is None:
        return {}
    if isinstance(style, str):
        out = lookup(style)
        if out.get("material"):
            from .materials import expand
            out = {**expand(out.pop("material"), theme), **out}
        return out
    if not isinstance(style, dict):
        raise ValueError("style must be a theme style name or an object")
    out: dict = {}
    spec = dict(style)
    parent = spec.pop("use", None)
    if parent:
        out.update(lookup(parent))
    cleared: set[str] = set()
    for key, value in spec.items():
        if value is None:
            out.pop(key, None)
            cleared.add(key)
        else:
            out[key] = value
    if out.get("material"):
        from .materials import expand
        out = {**expand(out.pop("material"), theme), **out}
        for key in cleared:
            out.pop(key, None)
        if "light" in cleared and "pbr" not in spec:
            out.pop("pbr", None)
    return out


def _as_list(value: Any) -> list:
    if value is None or value is False:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_NO_NUMBER_KEYS = {"text", "code", "font", "id", "group", "layer", "source", "d"}


def _sub_numbers(obj: Any, numbers: dict, key: str | None = None) -> Any:
    if isinstance(obj, str):
        name = obj.strip()
        if key not in _NO_NUMBER_KEYS and name.startswith("$") and name[1:] in numbers:
            return float(numbers[name[1:]])
        return obj
    if isinstance(obj, dict):
        return {k: _sub_numbers(v, numbers, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sub_numbers(v, numbers, key) for v in obj]
    return obj


def _is_none(spec: Any) -> bool:
    return spec is None or spec is False or (isinstance(spec, str) and spec.strip().lower() in ("none", ""))


class Effects:
    def __init__(self, st: dict, colors: dict):
        self.outer: list[dict] = []
        self.inner: list[dict] = []
        for sh in _as_list(st.get("shadow")):
            self.outer.append(self._fx(sh, colors, "#000000@0.5", blur=8, dy=4))
        for gl in _as_list(st.get("glow")):
            fx = self._fx(gl, colors, "#ffffff", blur=12)
            fx["dx"] = fx["dy"] = 0.0
            self.outer.append(fx)
        bevel = st.get("bevel")
        if bevel:
            if not isinstance(bevel, dict):
                bevel = {}
            size = float(bevel.get("size", 2))
            soft = float(bevel.get("soft", size))
            self.inner.append({"color": parse_color(bevel.get("highlight", "#ffffff@0.35"), colors),
                               "blur": soft, "dx": 0.0, "dy": size, "strength": 1.0})
            self.inner.append({"color": parse_color(bevel.get("shadow", "#000000@0.35"), colors),
                               "blur": soft, "dx": 0.0, "dy": -size, "strength": 1.0})
        for sh in _as_list(st.get("inner_shadow")):
            self.inner.append(self._fx(sh, colors, "#000000@0.5", blur=6, dy=2))
        for gl in _as_list(st.get("inner_glow")):
            fx = self._fx(gl, colors, "#ffffff@0.6", blur=8)
            fx["dx"] = fx["dy"] = 0.0
            self.inner.append(fx)

    @staticmethod
    def _fx(spec: Any, colors: dict, default_color: str, blur: float = 8, dy: float = 0) -> dict:
        if isinstance(spec, (str, list, tuple)):
            spec = {"color": spec}
        if spec is True:
            spec = {}
        if not isinstance(spec, dict):
            raise ValueError(f"Effect must be an object like {{color, blur, dx, dy}}, got {spec!r}")
        return {
            "color": parse_color(spec.get("color", default_color), colors),
            "blur": max(0.0, float(spec.get("blur", blur))),
            "dx": float(spec.get("dx", 0)),
            "dy": float(spec.get("dy", dy)),
            "spread": max(0.0, float(spec.get("spread", 0))),
            "strength": max(0.0, float(spec.get("strength", 1))),
            "knockout": bool(spec.get("knockout", False)),
        }

    def pad(self) -> float:
        pad = 0.0
        for fx in self.outer:
            pad = max(pad, fx["blur"] * 1.5 + max(abs(fx["dx"]), abs(fx["dy"])) + fx.get("spread", 0))
        return pad


def _stroke_specs(st: dict, colors: dict) -> list[dict]:
    """Normalise style.stroke to a list. Each stroke covers the band between distances d0 and d1 from
    the shape edge (positive = outside), so several strokes with offsets stack into double outlines."""
    spec = st.get("stroke")
    if _is_none(spec):
        return []
    many = (isinstance(spec, (list, tuple)) and len(spec) > 0
            and not all(isinstance(i, (int, float)) for i in spec))
    out = []
    for item in (spec if many else [spec]):
        if _is_none(item):
            continue
        if isinstance(item, (str, list, tuple)):
            item = {"color": item}
        if not isinstance(item, dict):
            raise ValueError("stroke must be a color, an object like {color, width, align, offset}, or a list of those")
        width = float(item.get("width", 2))
        if width <= 0:
            continue
        align = str(item.get("align", "inside")).lower()
        if align not in ("inside", "center", "outside"):
            raise ValueError("stroke.align must be 'inside', 'center' or 'outside'")
        offset = float(item.get("offset", 0) or 0)
        if align == "inside":
            d0, d1 = -(offset + width), -offset
        elif align == "outside":
            d0, d1 = offset, offset + width
        else:
            d0, d1 = offset - width / 2, offset + width / 2
        join = item.get("join")
        if join is not None and str(join).lower() not in ("miter", "round", "bevel"):
            raise ValueError("stroke.join must be 'miter', 'round' or 'bevel'")
        dash = item.get("dash")
        if dash is not None and not _is_none(dash):
            if isinstance(dash, (int, float)):
                dash = [dash, dash]
            if (not isinstance(dash, (list, tuple)) or not dash
                    or any(not isinstance(v, (int, float)) or v < 0 for v in dash) or sum(dash) <= 0):
                raise ValueError("stroke.dash must be a number or a list like [dash, gap, ...] (canvas units)")
            dash = [float(v) for v in dash]
        else:
            dash = None
        sides = item.get("sides")
        if sides is not None:
            sides = [str(s).lower() for s in (sides if isinstance(sides, (list, tuple)) else [sides])]
            if not sides or any(s not in ("top", "right", "bottom", "left") for s in sides):
                raise ValueError("stroke.sides must list 'top', 'right', 'bottom' and/or 'left' (rects only)")
        out.append({"sides": sides, "paint": item.get("fill", item.get("color", "#ffffff")), "width": width, "align": align,
                    "offset": offset, "d0": d0, "d1": d1, "join": str(join).lower() if join else None,
                    "miter_limit": max(1.0, float(item.get("miter_limit", 4))),
                    "dash": dash, "dash_offset": float(item.get("dash_offset", 0) or 0)})
    return out



def _stops(spec: dict, colors: dict, space: str = "srgb") -> tuple[np.ndarray, np.ndarray]:
    raw = spec.get("stops") or spec.get("colors")
    if raw is None and "from" in spec and "to" in spec:
        raw = [spec["from"], spec["to"]]
    if not raw or len(raw) < 2:
        raise ValueError("Gradient needs at least 2 stops: {'stops': [[0, '#111'], [1, '#333']]} or {'from':..., 'to':...}")
    offs, cols = [], []
    n = len(raw)
    for i, item in enumerate(raw):
        if isinstance(item, dict):
            off, col = item.get("offset", i / (n - 1)), item.get("color")
        elif isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], (int, float)) \
                and not isinstance(item[1], (int, float)):
            off, col = item
        else:
            off, col = i / (n - 1), item
        offs.append(float(off))
        r, g, b, a = parse_color(col, colors)
        af = a / 255.0
        c0, c1, c2 = fxlib.encode_space(np.array([r, g, b], dtype=np.float64), space)
        cols.append((c0 * af, c1 * af, c2 * af, a))
    order = np.argsort(np.array(offs), kind="stable")
    return np.array(offs)[order], np.array(cols, dtype=np.float64)[order]


def _ramp(t: np.ndarray, offs: np.ndarray, cols: np.ndarray) -> np.ndarray:
    out = np.empty(t.shape + (4,), dtype=np.float64)
    for c in range(4):
        out[..., c] = np.interp(t, offs, cols[:, c])
    alpha = out[..., 3:4]
    safe = np.where(alpha > 0, alpha / 255.0, 1.0)
    out[..., :3] = out[..., :3] / safe
    return out


def _pattern_cov(spec: dict, kind: str, size: tuple[int, int], origin: tuple[float, float], k: float) -> np.ndarray:
    w, h = size
    xs = np.arange(w, dtype=np.float32)[None, :]
    ys = np.arange(h, dtype=np.float32)[:, None]
    ux = (xs + np.float32(0.5)) / np.float32(k) - np.float32(origin[0])
    uy = (ys + np.float32(0.5)) / np.float32(k) - np.float32(origin[1])
    cell = np.float32(max(0.5, float(spec.get("size", 48 if kind == "clouds" else 16 if kind == "hex" else 8))))
    ang = math.radians(float(spec.get("angle", 45 if kind == "stripes" else 0)))
    ca, sa = np.float32(math.cos(ang)), np.float32(math.sin(ang))
    rx, ry = ux * ca + uy * sa, -ux * sa + uy * ca
    kf = np.float32(k)
    if kind == "stripes":
        ratio = np.float32(max(0.02, min(0.98, float(spec.get("ratio", 0.5)))))
        f = np.mod(rx / cell, np.float32(1.0))
        f = np.where(f > (np.float32(1.0) + ratio) / np.float32(2.0), f - np.float32(1.0), f)
        return np.clip(np.minimum(f, ratio - f) * cell * kf + np.float32(0.5), 0, 1)
    if kind == "dots":
        radius = np.float32(float(spec.get("radius", float(cell) * 0.25)))
        fx = (np.mod(rx / cell, np.float32(1.0)) - np.float32(0.5)) * cell
        fy = (np.mod(ry / cell, np.float32(1.0)) - np.float32(0.5)) * cell
        return np.clip((radius - np.hypot(fx, fy)) * kf + np.float32(0.5), 0, 1)
    if kind == "grid":
        lw = np.float32(float(spec.get("line_width", 1)))
        dx = np.abs((np.mod(rx / cell + np.float32(0.5), np.float32(1.0)) - np.float32(0.5)) * cell)
        dy = np.abs((np.mod(ry / cell + np.float32(0.5), np.float32(1.0)) - np.float32(0.5)) * cell)
        return np.clip((lw / np.float32(2.0) - np.minimum(dx, dy)) * kf + np.float32(0.5), 0, 1)
    if kind == "carbon":
        cu, cv = rx / cell, ry / cell
        fu, fv = np.mod(cu, np.float32(1.0)), np.mod(cv, np.float32(1.0))
        horizontal = (np.floor(cu) + np.floor(cv)) % 2 == 0
        shade = np.where(horizontal, fu, fv)
        return np.clip(np.float32(0.15) + np.float32(0.85) * shade, 0, 1)
    if kind == "brushed":
        seed = zlib.crc32(repr(sorted((str(a), str(b)) for a, b in spec.items())).encode())
        rng = np.random.default_rng(seed)
        amount = np.float32(max(0.0, min(1.0, float(spec.get("amount", 0.5)))))
        span = max(h, w) * 2 + 8
        fine = rng.normal(0, 1, span * 2).astype(np.float32)
        coarse = np.repeat(rng.normal(0, 1, span // 6 + 2).astype(np.float32), 12)[: span * 2]
        streak = np.float32(0.65) * fine + np.float32(0.35) * coarse
        idx = np.clip((ry * kf + span).astype(np.int64), 0, span * 2 - 1)
        grain = rng.normal(0, 0.25, (h, w)).astype(np.float32)
        return np.clip(np.float32(0.5) + (streak[idx] + grain) * np.float32(0.22) * amount, 0, 1)
    if kind == "hex":
        lw = np.float32(float(spec.get("line_width", 1)))
        px_, py_ = rx / cell, ry / cell
        r3 = np.float32(1.7320508)
        ax, ay = np.mod(px_, np.float32(1.0)) - np.float32(0.5), np.mod(py_, r3) - r3 / np.float32(2.0)
        bx, by = np.mod(px_ - np.float32(0.5), np.float32(1.0)) - np.float32(0.5), np.mod(py_ - r3 / np.float32(2.0), r3) - r3 / np.float32(2.0)
        near_a = ax * ax + ay * ay < bx * bx + by * by
        gx, gy = np.abs(np.where(near_a, ax, bx)), np.abs(np.where(near_a, ay, by))
        edge = np.float32(0.5) - np.maximum(gx, gx * np.float32(0.5) + gy * (r3 / np.float32(2.0)))
        return np.clip((lw / np.float32(2.0) - edge * cell) * kf + np.float32(0.5), 0, 1)
    if kind == "clouds":
        seed = float(spec.get("seed", 1))
        n = fxlib.fractal_noise(rx, ry, float(cell), int(spec.get("octaves", 4)), seed)
        contrast = np.float32(float(spec.get("contrast", 1)))
        return np.clip((n - np.float32(0.5)) * contrast + np.float32(0.5), 0, 1)
    raise ValueError(f"Unknown fill type '{kind}'. Use linear, radial, conic, shader, stripes, dots, grid, hex, carbon, "
                     "brushed, clouds or image.")


def _paint_surface(mask: Image.Image, spec: Any, box_px: Box, colors: dict, k: float,
                   sdf: np.ndarray | None = None, want_height: bool = False) -> tuple[Image.Image | None, np.ndarray | None]:
    """Paint ``spec`` limited to ``mask`` (cropped to mask bbox to skip empty shadow padding).
    Returns (RGBA image, optional bump height float32 array matching mask.size)."""
    if _is_none(spec):
        return None, None
    w, h = mask.size
    if not isinstance(spec, dict):
        r, g, b, a = parse_color(spec, colors)
        img = Image.new("RGBA", (w, h), (r, g, b, 0))
        img.putalpha(mask if a == 255 else mask.point(lambda v: v * a // 255))
        return img, None
    kind = str(spec.get("type", "linear")).lower()
    if kind == "image":
        return _image_fill(mask, spec, box_px, k), None

    bbox = mask.getbbox()
    if bbox is None:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0)), None
    cx0, cy0, cx1, cy1 = bbox
    cw, ch = cx1 - cx0, cy1 - cy0
    cropped = (cx0 > 0 or cy0 > 0 or cx1 < w or cy1 < h)
    sub_mask = mask.crop(bbox) if cropped else mask
    sub_box = (box_px[0] - cx0, box_px[1] - cy0, box_px[2] - cx0, box_px[3] - cy0)
    sub_sdf = sdf[cy0:cy1, cx0:cx1] if (sdf is not None and cropped) else sdf
    bump_full: np.ndarray | None = None

    x0, y0, x1, y1 = sub_box
    bw, bh = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    if kind == "shader":
        rgba, sub_h = shader.evaluate_surface(spec, (cw, ch), sub_box, k, colors, sdf=sub_sdf, want_height=want_height)
        if sub_h is not None:
            if cropped:
                bump_full = np.full((h, w), np.float32(0.5), dtype=np.float32)
                bump_full[cy0:cy1, cx0:cx1] = sub_h
            else:
                bump_full = sub_h
    elif kind in ("linear", "radial", "conic", "diamond"):
        space = str(spec.get("space", "srgb")).lower()
        offs, cols = _stops(spec, colors, space)
        xs = np.arange(cw, dtype=np.float32)[None, :] + np.float32(0.5)
        ys = np.arange(ch, dtype=np.float32)[:, None] + np.float32(0.5)
        if kind == "linear":
            ang = math.radians(float(spec.get("angle", 90)))
            ca, sa = np.float32(math.cos(ang)), np.float32(math.sin(ang))
            length = max(1e-6, abs(bw * float(ca)) + abs(bh * float(sa)))
            t = ((xs - np.float32((x0 + x1) / 2)) * ca + (ys - np.float32((y0 + y1) / 2)) * sa) / np.float32(length) + np.float32(0.5)
        elif kind == "diamond":
            cx = np.float32(x0 + bw * float(spec.get("cx", 0.5)))
            cy = np.float32(y0 + bh * float(spec.get("cy", 0.5)))
            rad = float(spec.get("r", 0.5))
            t = np.abs(xs - cx) / np.float32(max(1e-6, bw * rad)) + np.abs(ys - cy) / np.float32(max(1e-6, bh * rad))
        elif kind == "conic":
            cx = np.float32(x0 + bw * float(spec.get("cx", 0.5)))
            cy = np.float32(y0 + bh * float(spec.get("cy", 0.5)))
            a_from = float(spec.get("from", 0))
            a_to = float(spec.get("to", a_from + 360))
            span = a_to - a_from
            if abs(span) < 1e-6:
                raise ValueError("conic gradient: 'from' and 'to' angles must differ")
            ang = np.degrees(np.arctan2(ys - cy, xs - cx))
            rel = np.mod((ang - np.float32(a_from)) * np.float32(1 if span > 0 else -1), np.float32(360.0))
            width = np.float32(min(360.0, abs(span)))
            t = rel / width
            if float(width) < 360:
                dead = np.float32(360.0) - width
                t = np.where(rel <= width, t, np.where(rel - width < dead / np.float32(2.0), np.float32(1.0), np.float32(0.0)))
        else:
            cx = np.float32(x0 + bw * float(spec.get("cx", 0.5)))
            cy = np.float32(y0 + bh * float(spec.get("cy", 0.5)))
            rad = float(spec.get("r", 0.5))
            if spec.get("circle"):
                t = np.hypot(xs - cx, ys - cy) / np.float32(max(1e-6, max(bw, bh) * rad))
            else:
                t = np.hypot((xs - cx) / np.float32(max(1e-6, bw * rad)), (ys - cy) / np.float32(max(1e-6, bh * rad)))
        rgba = _ramp(np.clip(t, 0, 1), offs, cols).astype(np.float32)
        if space != "srgb":
            rgba[..., :3] = fxlib.decode_space(rgba[..., :3].astype(np.float64), space).astype(np.float32)
        if spec.get("dither", True):
            rng = np.random.default_rng(zlib.crc32(repr(spec.get("stops") or spec.get("colors") or "").encode()))
            rgba[..., :3] += rng.uniform(-0.5, 0.5, (ch, cw, 1)).astype(np.float32)
            soft = (rgba[..., 3] > 0.5) & (rgba[..., 3] < 254.5)
            rgba[..., 3] += np.where(soft, rng.uniform(-0.5, 0.5, (ch, cw)).astype(np.float32), np.float32(0.0))
    else:
        c1 = np.array(parse_color(spec.get("color", "#ffffff@0.15"), colors), dtype=np.float32)
        c2 = np.array(parse_color(spec.get("color2", spec.get("background", "transparent")), colors), dtype=np.float32)
        cov = _pattern_cov(spec, kind, (cw, ch), (x0 / k, y0 / k), k)[..., None]
        a1, a2 = c1[3] / np.float32(255.0), c2[3] / np.float32(255.0)
        pre = cov * np.append(c1[:3] * a1, c1[3]) + (np.float32(1.0) - cov) * np.append(c2[:3] * a2, c2[3])
        alpha = pre[..., 3:4]
        safe = np.where(alpha > 0, alpha / np.float32(255.0), np.float32(1.0))
        rgba = np.concatenate([pre[..., :3] / safe, alpha], axis=-1)
    m = np.asarray(sub_mask, dtype=np.float32) / np.float32(255.0)
    rgba[..., 3] *= m
    patch = Image.fromarray(np.clip(rgba + np.float32(0.5), 0, 255).astype(np.uint8), "RGBA")
    if cropped:
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.paste(patch, (cx0, cy0))
        return out, bump_full
    return patch, bump_full


def paint(mask: Image.Image, spec: Any, box_px: Box, colors: dict, k: float) -> Image.Image | None:
    """Return an RGBA image: ``spec`` (color / gradient / pattern / shader) limited to ``mask``."""
    img, _ = _paint_surface(mask, spec, box_px, colors, k)
    return img


_IMAGE_CACHE: OrderedDict[tuple[str, float], Image.Image] = OrderedDict()


def _image_fill(mask: Image.Image, spec: dict, box_px: Box, k: float) -> Image.Image:
    """Use a picture as paint: {"type": "image", "path": ..., "fit": "cover" | "stretch" | "tile", "scale": 1}."""
    path = Path(str(spec.get("path", ""))).expanduser()
    if not path.is_file():
        raise ValueError(f"image fill: file not found: {path.resolve()} - use an absolute path (relative paths resolve against the server's working folder, not yours)")
    key = (str(path), path.stat().st_mtime)
    if key in _IMAGE_CACHE:
        _IMAGE_CACHE.move_to_end(key)
    else:
        while len(_IMAGE_CACHE) >= 32:
            _IMAGE_CACHE.popitem(last=False)
        _IMAGE_CACHE[key] = Image.open(path).convert("RGBA")
    src = _IMAGE_CACHE[key]
    w, h = mask.size
    x0, y0, x1, y1 = box_px
    bw, bh = max(1, int(round(x1 - x0))), max(1, int(round(y1 - y0)))
    fit = str(spec.get("fit", "cover")).lower()
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if fit == "tile":
        scale = max(0.01, float(spec.get("scale", 1))) * k
        tile = src.resize((max(1, int(round(src.width * scale))), max(1, int(round(src.height * scale)))), Image.LANCZOS)
        ox, oy = int(round(x0)) % tile.width - tile.width, int(round(y0)) % tile.height - tile.height
        for ty in range(oy, h, tile.height):
            for tx in range(ox, w, tile.width):
                out.paste(tile, (tx, ty))
    elif fit in ("cover", "stretch"):
        img = src.resize((bw, bh), Image.LANCZOS, box=view_box(src.size, (bw, bh), fit, spec))
        out.paste(img, (int(round(x0)), int(round(y0))))
    else:
        raise ValueError("image fill: fit must be 'cover', 'stretch' or 'tile'")
    opacity = max(0.0, min(1.0, float(spec.get("opacity", 1))))
    alpha = ImageChops.multiply(out.getchannel("A"), mask)
    out.putalpha(alpha if opacity >= 1 else alpha.point(lambda v: int(v * opacity + 0.5)))
    return out


def view_box(size: tuple[int, int], target: tuple[float, float], fit: str, spec: dict) -> tuple[float, float, float, float]:
    """Source rectangle shown in a target box: cover / stretch, then zoom (>= 1 zooms in) around focus
    [fx, fy] (0..1 of the picture). Float edges keep pan / zoom animation smooth."""
    sw, sh = float(size[0]), float(size[1])
    vw, vh = sw, sh
    if fit == "cover":
        aspect = target[0] / max(1e-6, target[1])
        vw, vh = (sh * aspect, sh) if sw / sh > aspect else (sw, sw / aspect)
    zoom = max(1.0, float(spec.get("zoom", 1) or 1))
    vw, vh = vw / zoom, vh / zoom
    fx, fy = (spec.get("focus") or (0.5, 0.5))[:2]
    x0 = min(max(float(fx) * sw - vw / 2, 0.0), sw - vw)
    y0 = min(max(float(fy) * sh - vh / 2, 0.0), sh - vh)
    return x0, y0, x0 + vw, y0 + vh


def _cutout(img: Image.Image, spec: Any) -> Image.Image:
    """Remove a flat background: flood from the four corners within a colour tolerance, soft edge."""
    tol = float(spec.get("tolerance", 40)) if isinstance(spec, dict) else 40.0
    rgb = img.convert("RGB")
    probe = rgb.copy()
    mark = (255, 0, 254)
    for xy in ((0, 0), (rgb.width - 1, 0), (0, rgb.height - 1), (rgb.width - 1, rgb.height - 1)):
        if probe.getpixel(xy) != mark:
            ImageDraw.floodfill(probe, xy, mark, thresh=tol)
    bg = np.all(np.asarray(probe) == mark, axis=-1) & np.any(np.asarray(rgb) != mark, axis=-1)
    keep = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.7))
    out = img.copy()
    out.putalpha(ImageChops.multiply(img.getchannel("A"), keep))
    return out


_FRAMES: OrderedDict[tuple, Image.Image] = OrderedDict()


def load_frame(path: Path, el: dict) -> Image.Image:
    """One picture of an image element: its animation frame (GIF / APNG / WebP, or a sprite sheet
    {"cols", "rows", "count"}), then crop and cutout. Cached per file version."""
    sheet = el.get("sheet")
    frame = int(math.floor(float(el.get("frame", 0) or 0)))
    key = (str(path), path.stat().st_mtime, frame, repr(sheet), repr(el.get("crop")), repr(el.get("cutout")))
    if key in _FRAMES:
        _FRAMES.move_to_end(key)
        return _FRAMES[key]
    src = Image.open(path)
    if sheet:
        cols, rows = max(1, int(sheet.get("cols", 1))), max(1, int(sheet.get("rows", 1)))
        count = max(1, min(cols * rows, int(sheet.get("count", cols * rows))))
        i = frame % count
        cw, ch = src.width / cols, src.height / rows
        img = src.convert("RGBA").crop((int(round(i % cols * cw)), int(round(i // cols * ch)),
                                         int(round((i % cols + 1) * cw)), int(round((i // cols + 1) * ch))))
    else:
        n = int(getattr(src, "n_frames", 1) or 1)
        if n > 1:
            src.seek(frame % n)
        img = src.convert("RGBA")
    crop = el.get("crop")
    if crop:
        try:
            cx, cy, cw, ch = (float(v) for v in crop)
        except (TypeError, ValueError) as exc:
            raise ValueError("crop must be [x, y, width, height] in source-image pixels") from exc
        if cw <= 0 or ch <= 0:
            raise ValueError("crop width and height must be > 0")
        img = img.crop((int(cx), int(cy), int(cx + cw), int(cy + ch)))
    if el.get("cutout"):
        img = _cutout(img, el["cutout"])
    while len(_FRAMES) >= 256:
        _FRAMES.popitem(last=False)
    _FRAMES[key] = img
    return img


_EL_CACHE_LOCK = threading.Lock()
_EL_CACHE: OrderedDict[str, tuple[tuple[Image.Image, int, int, str] | None, int]] = OrderedDict()
_EL_CACHE_BYTES = 0
_EL_CACHE_MAX_BYTES = 128 * 1024 * 1024


def clear_render_cache() -> None:
    """Drop cached element renders (mainly for tests or memory pressure)."""
    global _EL_CACHE_BYTES
    with _EL_CACHE_LOCK:
        _EL_CACHE.clear()
        _EL_CACHE_BYTES = 0


def _cache_get(key: str):
    with _EL_CACHE_LOCK:
        hit = _EL_CACHE.get(key)
        if hit is not None:
            _EL_CACHE.move_to_end(key)
            return True, hit[0]
        return False, None


def _cache_put(key: str, value) -> None:
    global _EL_CACHE_BYTES
    res = value[0]
    size = (res[0].width * res[0].height * 4) if res is not None else 64
    if size > _EL_CACHE_MAX_BYTES // 2:
        return
    with _EL_CACHE_LOCK:
        old = _EL_CACHE.pop(key, None)
        if old is not None:
            _EL_CACHE_BYTES -= old[1]
        while _EL_CACHE and _EL_CACHE_BYTES + size > _EL_CACHE_MAX_BYTES:
            _, (_, old_sz) = _EL_CACHE.popitem(last=False)
            _EL_CACHE_BYTES -= old_sz
        _EL_CACHE[key] = (value, size)
        _EL_CACHE_BYTES += size


_DITHER: dict[tuple[int, int], np.ndarray] = {}


def _dither(shape: tuple[int, int]) -> np.ndarray:
    """Fixed blue-ish noise in [0, 1) used to break 8-bit banding in soft gradients (deterministic)."""
    noise = _DITHER.get(shape)
    if noise is None:
        noise = np.random.default_rng(7).random(shape)
        if len(_DITHER) > 32:
            _DITHER.clear()
        _DITHER[shape] = noise
    return noise


def _soft_tint(cov: np.ndarray, color: tuple[int, int, int, int], strength: float) -> Image.Image:
    """Float coverage (0-255) -> colour layer whose alpha is dithered, so wide soft shadows and glows
    fade smoothly instead of in visible 8-bit steps."""
    r, g, b, a = color
    alpha = cov * (a / 255.0 * strength)
    alpha = np.floor(np.clip(alpha, 0, 255) + _dither(alpha.shape))
    img = Image.new("RGBA", (cov.shape[1], cov.shape[0]), (r, g, b, 0))
    img.putalpha(Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8), "L"))
    return img


def _outer_effects(layer: Image.Image, sil: Image.Image, fx: "Effects", k: float) -> Image.Image:
    """Shadows and glows cast by the silhouette, composited onto ``layer`` (which is still empty)."""
    for e in fx.outer:
        m = sil
        spread = e["spread"] * k
        if spread > 0:
            m = Image.fromarray(fxlib.dilate(np.asarray(m), spread), "L")
        m = _shift(m, int(round(e["dx"] * k)), int(round(e["dy"] * k)))
        cov = np.asarray(m, dtype=np.float64)
        if e["blur"] > 0:
            cov = fxlib.blur_float(cov, e["blur"] * k)
        if e["knockout"]:
            cov = cov * (1.0 - np.asarray(sil, dtype=np.float64) / 255.0)
        layer = Image.alpha_composite(layer, _soft_tint(cov, e["color"], e["strength"]))
    return layer


def _inner_effects(layer: Image.Image, shape: Image.Image, fx: "Effects", k: float) -> Image.Image:
    """Inner shadows / glows / simple bevel, limited to the shape."""
    shape_f = np.asarray(shape, dtype=np.float64) / 255.0
    for e in fx.inner:
        m = ImageChops.invert(shape)
        m = _shift(m, int(round(e["dx"] * k)), int(round(e["dy"] * k)), fill=255)
        cov = np.asarray(m, dtype=np.float64)
        if e["blur"] > 0:
            pad = int(math.ceil(e["blur"] * k * 1.6)) + 1
            cov = fxlib.blur_float(np.pad(cov, pad, constant_values=255.0), e["blur"] * k)[pad:-pad, pad:-pad]
        layer = Image.alpha_composite(layer, _soft_tint(cov * shape_f, e["color"], e.get("strength", 1.0)))
    return layer


def _soft_mask(size: tuple[int, int], spec: Any, box_px: Box, colors: dict, k: float,
               mode: str = "alpha") -> Image.Image:
    """The fade mask for style.mask: the paint's alpha, or its brightness with mask_mode "luminance"."""
    painted = paint(Image.new("L", size, 255), spec, box_px, colors, k)
    if painted is None:
        return Image.new("L", size, 255)
    if str(mode).lower() == "luminance":
        return ImageChops.multiply(painted.convert("L"), painted.getchannel("A"))
    if str(mode).lower() != "alpha":
        raise ValueError("mask_mode must be 'alpha' or 'luminance'")
    return painted.getchannel("A")


def _fill_blend(spec: Any) -> tuple[Any, str]:
    """A fill-stack entry may carry its own blend: {"type": ..., "blend": "multiply"} or {"color": c, "blend": ...}."""
    if isinstance(spec, dict) and "blend" in spec:
        spec = dict(spec)
        blend = str(spec.pop("blend")).lower()
        if blend not in BLENDS:
            raise ValueError(f"fill blend must be one of {', '.join(BLENDS)}")
        if "type" not in spec and "color" in spec:
            spec = spec["color"]
        return spec, blend
    return spec, "normal"


def _tint(mask: Image.Image, color: tuple[int, int, int, int], strength: float = 1.0) -> Image.Image:
    r, g, b, a = color
    if a == 255 and strength == 1.0:
        alpha = mask
    else:
        f = a / 255.0 * strength
        alpha = mask.point(lambda v: min(255, int(v * f + 0.5)))
    img = Image.new("RGBA", mask.size, (r, g, b, 0))
    img.putalpha(alpha)
    return img


def _shift(mask: Image.Image, dx: int, dy: int, fill: int = 0) -> Image.Image:
    if not dx and not dy:
        return mask
    out = Image.new("L", mask.size, fill)
    out.paste(mask, (dx, dy))
    return out


def composite(dst: Image.Image, src: Image.Image, ox: int, oy: int, blend: str = "normal") -> None:
    """Composite ``src`` onto ``dst`` in place at (ox, oy), cropping to bounds."""
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(dst.width, ox + src.width), min(dst.height, oy + src.height)
    if x1 <= x0 or y1 <= y0:
        return
    part = src.crop((x0 - ox, y0 - oy, x1 - ox, y1 - oy))
    base = dst.crop((x0, y0, x1, y1))
    if blend == "erase":
        b = np.asarray(base, dtype=np.float32).copy()
        b[..., 3] *= np.float32(1.0) - np.asarray(part, dtype=np.float32)[..., 3] / np.float32(255.0)
        merged = Image.fromarray((b + np.float32(0.5)).astype(np.uint8), "RGBA")
    elif blend == "add":
        b = np.asarray(base, dtype=np.float32)
        s = np.asarray(part, dtype=np.float32)
        sa = s[..., 3:4] / np.float32(255.0)
        ba = b[..., 3:4] / np.float32(255.0)
        rgb = np.clip(b[..., :3] * ba + s[..., :3] * sa, 0, 255)
        alpha = np.clip(b[..., 3:4] + s[..., 3:4] * (np.float32(1.0) - ba), 0, 255)
        safe = np.where(alpha > 0, alpha / np.float32(255.0), np.float32(1.0))
        out = np.concatenate([np.clip(rgb / safe, 0, 255), alpha], axis=-1)
        merged = Image.fromarray((out + np.float32(0.5)).astype(np.uint8), "RGBA")
    elif blend != "normal":
        b = np.asarray(base, dtype=np.float32) / np.float32(255.0)
        s = np.asarray(part, dtype=np.float32) / np.float32(255.0)
        bc, sc, ba, sa = b[..., :3], s[..., :3], b[..., 3:4], s[..., 3:4]
        one = np.float32(1.0)
        half = np.float32(0.5)
        two = np.float32(2.0)
        if blend == "multiply":
            mixed = bc * sc
        elif blend == "screen":
            mixed = one - (one - bc) * (one - sc)
        elif blend == "overlay":
            mixed = np.where(bc <= half, two * bc * sc, one - two * (one - bc) * (one - sc))
        elif blend == "hard-light":
            mixed = np.where(sc <= half, two * bc * sc, one - two * (one - bc) * (one - sc))
        elif blend == "soft-light":
            d = np.where(bc <= np.float32(0.25), ((np.float32(16.0) * bc - np.float32(12.0)) * bc + np.float32(4.0)) * bc, np.sqrt(bc))
            mixed = np.where(sc <= half, bc - (one - two * sc) * bc * (one - bc), bc + (two * sc - one) * (d - bc))
        elif blend == "color-dodge":
            mixed = np.where(sc >= one, one, np.minimum(one, bc / np.maximum(np.float32(1e-6), one - sc)))
        elif blend == "color-burn":
            mixed = np.where(sc <= 0, np.float32(0.0), one - np.minimum(one, (one - bc) / np.maximum(np.float32(1e-6), sc)))
        elif blend == "darken":
            mixed = np.minimum(bc, sc)
        elif blend == "lighten":
            mixed = np.maximum(bc, sc)
        elif blend == "difference":
            mixed = np.abs(bc - sc)
        else:
            raise ValueError(f"blend must be one of {', '.join(BLENDS)}")
        pre = (one - sa) * bc * ba + (one - ba) * sc * sa + ba * sa * mixed
        alpha = ba + sa - ba * sa
        safe = np.where(alpha > 0, alpha, one)
        out = np.concatenate([np.clip(pre / safe, 0, 1), alpha], axis=-1) * np.float32(255.0)
        merged = Image.fromarray((out + np.float32(0.5)).astype(np.uint8), "RGBA")
    else:
        merged = Image.alpha_composite(base, part)
    dst.paste(merged, (x0, y0))



def parse_anchor(anchor: str | None) -> tuple[str, str]:
    """Parse an anchor like 'top-left', 'center', 'middle-right', 'baseline-center' into (h, v)."""
    tokens = [t for t in str(anchor or "top-left").lower().replace("_", "-").replace(" ", "-").split("-") if t]
    h = v = None
    centers = 0
    for t in tokens:
        if t in ("left", "right"):
            h = t
        elif t in ("top", "bottom", "middle", "baseline"):
            v = t
        elif t == "center":
            centers += 1
        else:
            raise ValueError(
                f"Bad anchor '{anchor}'. Examples: 'top-left', 'center', 'middle-left', 'bottom-right', 'baseline-center'.")
    if tokens in (["center"], ["middle"]):
        return "center", "middle"
    if centers and h is None:
        h = "center"
        centers -= 1
    if centers and v is None:
        v = "middle"
    return h or "left", v or "top"


def _tr_upper(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


class TextLayout:
    """Lays out a text element at a given pixel density (px per canvas unit)."""

    def __init__(self, el: dict, st: dict, fonts: FontLibrary, ppu: float, text: str | None = None,
                 lang: str | None = None):
        text = str(el.get("text", "")) if text is None else text
        case = str(el.get("case", st.get("case")) or "").lower().replace("_", "-")
        upper = el.get("uppercase", st.get("uppercase"))
        if upper and not case:
            case = "tr-upper" if str(upper).lower() == "tr" else "upper"
        text = _letter_case(text, case)
        self.family = el.get("font") or st.get("font")
        self.weight = parse_weight(el.get("weight", st.get("weight")))
        self.size = float(el.get("size") or st.get("size") or 24)
        self.spacing = float(el.get("letter_spacing", st.get("letter_spacing", 0)) or 0)
        self.line_height = float(el.get("line_height", st.get("line_height", 1.2)) or 1.2)
        self.ppu = ppu
        self.h, self.v = parse_anchor(el.get("anchor"))
        self.align = str(el.get("align") or self.h).lower()
        max_width = el.get("max_width")
        fit_width = el.get("fit_width")
        italic = bool(el.get("italic", st.get("italic")))
        self.path, self.var_weight, faux = fonts.resolve(self.family, self.weight, italic)
        self.skew = float(el.get("skew", 0) or 0) + (12.0 if faux else 0.0)
        self.lang, lang_warn = shaping.guess_lang(text, lang or el.get("lang"))
        self.warnings = [f"{el.get('id')}: {lang_warn}"] if lang_warn else []
        self._fonts = fonts
        self.features = _ot_features(el.get("features", st.get("features")), case)
        axes = el.get("axes", st.get("axes")) or {}
        if not isinstance(axes, dict):
            raise ValueError('axes must be an object of variable-font axes, e.g. {"wdth": 75, "slnt": -8}')
        self.axes = tuple(sorted((str(k), float(v)) for k, v in axes.items())) or None
        self.paragraph_spacing = float(el.get("paragraph_spacing", st.get("paragraph_spacing", 0)) or 0)
        self.indent = float(el.get("indent", st.get("indent", 0)) or 0)
        self.list_style = str(el.get("list") or "none").lower()
        if self.list_style not in ("none", "bullet", "number"):
            raise ValueError("list must be 'bullet', 'number' or 'none'")
        self._shaped = bool(self.path) and (bool(self.features) or bool(self.axes) or shaping.needs_shaping(
            text, shaping._face(self.path)[1].__contains__))
        if self.features and self.path:
            missing = shaping.unsupported_features(self.path, self.features)
            if missing:
                hint = " (for small caps without one: case 'upper' at a smaller size)" if "smcp" in missing else ""
                self.warnings.append(f"{el.get('id')}: font '{self.family or 'Inter'}' has no OpenType "
                                     f"{', '.join(missing)} - pick a font that has it{hint}")

        self._load()
        if fit_width:
            min_size = float(el.get("min_size", 8))
            for _ in range(40):
                lines = self._wrap(text, float(max_width) * ppu if max_width else None)
                if max((w for _, w in lines), default=0) <= float(fit_width) * ppu or self.size <= min_size:
                    break
                self.size = max(min_size, self.size * 0.95)
                self._load()
        self.lines = self._wrap(text, float(max_width) * ppu if max_width else None)
        self.text = text
        self.truncated = False
        self.trim = bool(el.get("trim", st.get("trim", False)))
        max_lines = el.get("max_lines")
        if max_lines:
            keep = int(max_lines)
            if keep < 1:
                raise ValueError("max_lines must be 1 or more")
            if not max_width:
                raise ValueError("max_lines needs max_width (the width the text is cut to)")
            if len(self.lines) > keep:
                last, limit = self.lines[keep - 1][0].rstrip(), float(max_width) * ppu
                while last and self._width(last + "\u2026") > limit:
                    last = last[:-1].rstrip()
                self.lines = self.lines[:keep - 1] + [(last + "\u2026", self._width(last + "\u2026"))]
                self._indents, self._gaps = self._indents[:keep], self._gaps[:keep]
                self.truncated = True
        self.decoration = str(el.get("decoration") or "none").lower()
        if self.decoration not in ("none", "underline", "strikethrough"):
            raise ValueError("decoration must be 'underline', 'strikethrough' or 'none'")

        n = max(1, len(self.lines))
        step = self.size * ppu * self.line_height
        gaps = (self._gaps + [0.0] * n)[:n]
        extra = sum(gaps[1:])
        x, y = float(el.get("x", 0)) * ppu, float(el.get("y", 0)) * ppu
        if self.v == "top":
            b0 = y + self.cap
        elif self.v == "middle":
            b0 = y + self.cap / 2 - ((n - 1) * step + extra) / 2
        elif self.v == "bottom":
            b0 = y - (n - 1) * step - extra - (0.0 if self.trim else self.descent)
        else:
            b0 = y - (n - 1) * step - extra
        self.baselines, acc = [], 0.0
        for i in range(n):
            acc += gaps[i] if i else 0.0
            self.baselines.append(b0 + i * step + acc)
        indents = (self._indents + [0.0] * n)[:n]
        self.block_w = max((w + ind for (_, w), ind in zip(self.lines, indents)), default=0.0)
        if self.h == "left":
            bx = x
        elif self.h == "center":
            bx = x - self.block_w / 2
        else:
            bx = x - self.block_w
        self.block_x = bx
        self.line_x = []
        for (_, w), ind in zip(self.lines, indents):
            if self.align == "center":
                self.line_x.append(bx + (self.block_w - w) / 2)
            elif self.align == "right":
                self.line_x.append(bx + self.block_w - w)
            else:
                self.line_x.append(bx + ind)
        top, bottom = self.cap, self.descent
        if self.shaper:
            used = [self.shaper.chain[i] for i in self.shaper.used]
            top = max([top] + [f.ascent for f in used])
            bottom = max([bottom] + [f.descent for f in used])
        if self.trim:
            top, bottom = self.cap, 0.0
        self.box_px = (bx, self.baselines[0] - top, bx + self.block_w, self.baselines[-1] + bottom)
        self.arc = None
        if el.get("arc") or el.get("path"):
            if self.shaper:
                raise ValueError("text on an arc or path supports Latin, Greek and Cyrillic only; this text needs "
                                 "shaping or fallback fonts (draw it straight, or bake it as an image)")
            if el.get("arc"):
                self._layout_arc(el["arc"])
            else:
                self._layout_path(el["path"])

    def _layout_path(self, spec: Any) -> None:
        """Place glyphs upright along any path (Figma "text on a path"). spec: {"d": svg path} or
        {"points": [[x, y], ...]}, optional "start" (units along the path) and "offset" (distance off it)."""
        if not isinstance(spec, dict) or not (spec.get("d") or spec.get("points")):
            raise ValueError('path must be {"d": "M 0 100 C ..."} or {"points": [[x, y], ...]}')
        if len(self.lines) != 1:
            raise ValueError("text on a path must be a single line (no newlines, no max_width wrapping)")
        ppu = self.ppu
        if spec.get("d"):
            subs = geo.parse_svg_path(str(spec["d"]), 8.0)
            if not subs:
                raise ValueError("path d has no drawable segments")
            pts = subs[0][0]
        else:
            pts = [(float(p[0]), float(p[1])) for p in spec["points"]]
        pts = [(px * ppu, py * ppu) for px, py in pts]
        if len(pts) < 2:
            raise ValueError("the text path needs at least 2 points")
        seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
        length = sum(seg)
        text = self.lines[0][0]
        advances = [float(self.font.getlength(ch)) for ch in text]
        total = sum(advances) + self.spacing * ppu * max(0, len(text) - 1)
        if total > length * 1.001:
            raise ValueError(f"text is longer than the path ({total / ppu:.0f} vs {length / ppu:.0f} units); "
                             "use a smaller size or a longer path")
        start = float(spec.get("start", 0)) * ppu
        if self.h == "center":
            s = start + (length - start - total) / 2
        elif self.h == "right":
            s = length - total
        else:
            s = start
        offset = float(spec.get("offset", 0)) * ppu
        shift = {"top": -self.cap, "middle": -self.cap / 2, "bottom": self.descent}.get(self.v, 0.0)

        def at(dist: float):
            d = max(0.0, min(length, dist))
            for (a, b), L in zip(zip(pts, pts[1:]), seg):
                if d <= L or (a, b) == (pts[-2], pts[-1]):
                    t = d / L if L else 0.0
                    ux, uy = ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L else (1.0, 0.0)
                    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, ux, uy
                d -= L
            return pts[-1][0], pts[-1][1], 1.0, 0.0

        glyphs, corners = [], []
        for ch, adv in zip(text, advances):
            mid = s + adv / 2
            px, py, ux, uy = at(mid)
            nx, ny = uy, -ux
            lift = offset - shift
            gx, gy = px + nx * lift, py + ny * lift
            rot = math.degrees(math.atan2(uy, ux))
            glyphs.append((ch, gx, gy, rot, adv))
            ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            for lx, ly in ((-adv / 2, -self.cap * 1.25), (adv / 2, -self.cap * 1.25),
                           (-adv / 2, self.descent), (adv / 2, self.descent)):
                corners.append((gx + lx * ca - ly * sa, gy + lx * sa + ly * ca))
            s += adv + self.spacing * ppu
        self.arc = glyphs
        xs, ys = [q[0] for q in corners], [q[1] for q in corners]
        self.box_px = (min(xs), min(ys), max(xs), max(ys))

    def color_layer(self, size: tuple[int, int], ox: float, oy: float):
        """RGBA picture of the colour emoji in this text (None when there are none)."""
        if not self.shaper or self.arc is not None:
            return None
        if not self.chain_has_color:
            return None
        img = None
        for (line, _), lx, by in zip(self.lines, self.line_x, self.baselines):
            if not line:
                continue
            self.shaper.shape(line)
            if self.shaper.color_runs.get(line):
                if img is None:
                    img = Image.new("RGBA", size, (0, 0, 0, 0))
                self.shaper.draw_color(img, line, lx - ox, by - oy, self.size * self.ppu)
        return img

    @property
    def chain_has_color(self) -> bool:
        return any(f.color for f in self.shaper.chain) if self.shaper else False

    def outline_polys_units(self) -> list[list[tuple[float, float]]]:
        """Every glyph outline of this text as polygons in canvas units (text to vector paths)."""
        if self.arc is not None:
            raise ValueError("text on an arc or path cannot be converted to a path yet - draw it straight")
        shaper = self.shaper or shaping.ShapedText(
            shaping.fallback_chain(self._fonts, self.path, self.var_weight, self.weight, self.size * self.ppu,
                                   self.lang, self.axes), self.lang, self.spacing * self.ppu, self.features)
        out = []
        lean = math.tan(math.radians(self.skew)) if self.skew else 0.0
        mid = (self.box_px[1] + self.box_px[3]) / 2
        for (line, _), lx, by in zip(self.lines, self.line_x, self.baselines):
            for poly in shaper.outline_polys(line, lx, by):
                if lean:
                    poly = np.column_stack((poly[:, 0] + (mid - poly[:, 1]) * lean, poly[:, 1]))
                out.append([(float(px) / self.ppu, float(py) / self.ppu) for px, py in poly])
        return out

    def _layout_arc(self, spec: Any) -> None:
        """Place each glyph upright along a circle. spec: {cx, cy, radius, angle, side}. ``radius`` is
        the baseline radius; ``angle`` (degrees, 0 = right, 90 = down) is where the anchor point of the
        text sits; side 'outer' reads clockwise over the top, 'inner' reads anticlockwise under the
        bottom, like the lower text on a badge."""
        if not isinstance(spec, dict):
            raise ValueError("arc must be an object like {cx, cy, radius, angle, side}")
        if len(self.lines) != 1:
            raise ValueError("text on an arc must be a single line (no newlines, no max_width wrapping)")
        try:
            cx, cy, radius = float(spec["cx"]), float(spec["cy"]), float(spec["radius"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("arc needs numeric cx, cy and radius") from exc
        if radius <= 0:
            raise ValueError("arc radius must be > 0")
        side = str(spec.get("side", "outer")).lower()
        if side not in ("outer", "inner"):
            raise ValueError("arc side must be 'outer' or 'inner'")
        angle = float(spec.get("angle", -90 if side == "outer" else 90))
        ppu = self.ppu
        R = radius * ppu
        text = self.lines[0][0]
        advances = []
        for ch in text:
            advances.append(float(self.font.getlength(ch)))
        total = sum(advances) + self.spacing * ppu * max(0, len(text) - 1)
        if total > 2 * math.pi * R * 0.98:
            raise ValueError(f"text is longer than the circle ({total / ppu:.0f} vs {2 * math.pi * radius:.0f} units); "
                             "use a bigger radius, smaller size or less letter_spacing")
        if self.h == "left":
            s0 = 0.0
        elif self.h == "center":
            s0 = -total / 2
        else:
            s0 = -total
        sign = 1.0 if side == "outer" else -1.0
        glyphs = []
        pos = s0
        pts = []
        if self.v == "top":
            shift = -self.cap
        elif self.v == "middle":
            shift = -self.cap / 2
        elif self.v == "bottom":
            shift = self.descent
        else:
            shift = 0.0
        Rb = R + shift if side == "outer" else R - shift
        for ch, adv in zip(text, advances):
            mid = pos + adv / 2
            theta = math.radians(angle) + sign * mid / max(1e-6, Rb)
            gx, gy = cx * ppu + Rb * math.cos(theta), cy * ppu + Rb * math.sin(theta)
            rot = math.degrees(theta) + (90.0 if side == "outer" else -90.0)
            glyphs.append((ch, gx, gy, rot, adv))
            ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            for lx, ly in ((-adv / 2, -self.cap * 1.25), (adv / 2, -self.cap * 1.25),
                           (-adv / 2, self.descent), (adv / 2, self.descent)):
                pts.append((gx + lx * ca - ly * sa, gy + lx * sa + ly * ca))
            pos += adv + self.spacing * ppu
        self.arc = glyphs
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        self.box_px = (min(xs), min(ys), max(xs), max(ys))

    def draw_arc(self, img: Image.Image, ox: float, oy: float, stroke_px: int = 0) -> None:
        """Draw arc-placed glyph coverage onto ``img`` (L mode) at offset (-ox, -oy)."""
        size_px = self.size * self.ppu
        tile = int(math.ceil(size_px * 2.4 + 4 * stroke_px)) + 4
        lean = math.tan(math.radians(self.skew)) if self.skew else 0.0
        for ch, gx, gy, rot, _ in self.arc:
            if ch.isspace():
                continue
            t = Image.new("L", (tile, tile), 0)
            d = ImageDraw.Draw(t)
            kwargs: dict = {"font": self.font, "fill": 255, "anchor": "ms"}
            if stroke_px > 0:
                kwargs.update(stroke_width=stroke_px, stroke_fill=255)
            d.text((tile / 2, tile / 2), ch, **kwargs)
            if lean:
                t = t.transform(t.size, Image.AFFINE, (1, lean, -lean * tile / 2, 0, 1, 0), resample=Image.BICUBIC)
            if rot:
                t = t.rotate(-rot, resample=Image.BICUBIC, center=(tile / 2, tile / 2))
            x0 = int(round(gx - ox - tile / 2))
            y0 = int(round(gy - oy - tile / 2))
            box = (x0, y0, x0 + tile, y0 + tile)
            under = img.crop(box)
            img.paste(ImageChops.lighter(under, t), box)

    def _load(self) -> None:
        self.font = load_font(self.path, int(round(self.size * self.ppu)), self.var_weight)
        ascent, descent = self.font.getmetrics()
        self.ascent, self.descent = float(ascent), float(descent)
        try:
            self.cap = float(-self.font.getbbox("H", anchor="ls")[1])
        except Exception:
            self.cap = self.ascent * 0.72
        if self.cap <= 0:
            self.cap = self.ascent * 0.72
        self.shaper = None
        if self._shaped:
            chain = shaping.fallback_chain(self._fonts, self.path, self.var_weight, self.weight,
                                           self.size * self.ppu, self.lang, self.axes)
            self.shaper = shaping.ShapedText(chain, self.lang, self.spacing * self.ppu, self.features)

    def fallback_note(self) -> str | None:
        """Which characters the chosen font lacked and which fallback font drew them."""
        if not self.shaper or not self.shaper.fallback:
            return None
        parts = [f"{''.join(sorted(chars))!r} with {Path(self.shaper.chain[i].path).stem}"
                 for i, chars in sorted(self.shaper.fallback.items())]
        return (f"font '{self.family or 'Inter'}' lacks some characters, drawn with fallback fonts: "
                f"{'; '.join(parts)}. The engine font needs these glyphs too.")

    def missing(self) -> list[str]:
        """Characters no font in the fallback chain can draw."""
        if self.shaper:
            for line, _ in self.lines:
                self.shaper.shape(line)
            return sorted(self.shaper.missing)
        return missing_glyphs(self.font, self.text)

    def _width(self, s: str) -> float:
        if not s:
            return 0.0
        if self.shaper:
            return self.shaper.width(s)
        return float(self.font.getlength(s)) + self.spacing * self.ppu * max(0, len(s) - 1)

    def _wrap(self, text: str, max_px: float | None) -> list[tuple[str, float]]:
        """Lines with their widths; also fills self._indents (px) and self._gaps (extra px before a line)."""
        lines: list[tuple[str, float]] = []
        self._indents, self._gaps = [], []
        number = 0
        para_gap = self.paragraph_spacing * self.ppu
        for pi, para in enumerate(text.split("\n")):
            marker = ""
            if self.list_style != "none" and para.strip():
                number += 1
                marker = "\u2022  " if self.list_style == "bullet" else f"{number}.  "
            hang = self._width(marker) if marker else 0.0
            first = hang if marker else self.indent * self.ppu
            avail = None if max_px is None else max(1.0, max_px - max(first, hang))
            body = self._wrap_para(para, avail)
            for li, (ln, w) in enumerate(body):
                if li == 0 and marker:
                    lines.append((marker + ln, self._width(marker + ln)))
                    self._indents.append(0.0)
                else:
                    lines.append((ln, w))
                    self._indents.append(first if li == 0 else hang)
                self._gaps.append(para_gap if (li == 0 and pi > 0) else 0.0)
        return lines

    def _wrap_para(self, para: str, max_px: float | None) -> list[tuple[str, float]]:
        if max_px is None:
            return [(para, self._width(para))]
        if self.shaper:
            return [(ln, self._width(ln)) for ln in self.shaper.wrap(para, max_px)]
        lines, cur = [], ""
        for word in para.split(" "):
            trial = word if not cur else cur + " " + word
            if cur and self._width(trial) > max_px:
                lines.append((cur, self._width(cur)))
                cur = word
            else:
                cur = trial
        lines.append((cur, self._width(cur)))
        return lines

    def box_units(self) -> Box:
        x0, y0, x1, y1 = self.box_px
        return (x0 / self.ppu, y0 / self.ppu, x1 / self.ppu, y1 / self.ppu)

    def draw(self, img: Image.Image, ox: float, oy: float, stroke_px: int = 0) -> None:
        """Draw glyph coverage (optionally dilated by stroke_px) onto ``img`` (L mode) at offset (-ox, -oy)."""
        self._draw_glyphs(img, ox, oy, stroke_px)
        if self.decoration != "none":
            px = self.size * self.ppu
            thick = max(1.0, px * 0.07)
            lift = -px * 0.12 if self.decoration == "underline" else px * 0.3
            draw = ImageDraw.Draw(img)
            for (line, width), lx, by in zip(self.lines, self.line_x, self.baselines):
                if line.strip():
                    y = by - lift - oy
                    draw.rectangle((lx - ox - stroke_px, y - thick / 2 - stroke_px,
                                    lx + width - ox + stroke_px, y + thick / 2 + stroke_px), fill=255)

    def _draw_glyphs(self, img: Image.Image, ox: float, oy: float, stroke_px: int = 0) -> None:
        if self.shaper:
            for (line, _), lx, by in zip(self.lines, self.line_x, self.baselines):
                if line:
                    self.shaper.draw(img, line, lx - ox, by - oy, stroke_px)
            return
        draw = ImageDraw.Draw(img)
        kwargs: dict = {"font": self.font, "fill": 255, "anchor": "ls"}
        if stroke_px > 0:
            kwargs.update(stroke_width=stroke_px, stroke_fill=255)
        for (line, _), lx, by in zip(self.lines, self.line_x, self.baselines):
            if not line:
                continue
            if self.spacing:
                cx = lx
                for ch in line:
                    draw.text((cx - ox, by - oy), ch, **kwargs)
                    cx += float(self.font.getlength(ch)) + self.spacing * self.ppu
            else:
                draw.text((lx - ox, by - oy), line, **kwargs)



class Geometry:
    def __init__(self) -> None:
        self.fills: list[list[geo.Point]] = []
        self.lines: list[tuple[list[geo.Point], bool, float, str]] = []
        self.outline: list[tuple[list[geo.Point], bool]] = []
        self.kind = "poly"
        self.rect: tuple | None = None
        self.ellipse: tuple | None = None
        self.box: Box = (0, 0, 0, 0)
        self.paint_box: Box | None = None


def vector_geometry(el: dict, res: float) -> Geometry:
    g = Geometry()
    t = el["type"]
    if t == "rect":
        x, y, w, h = (float(el[k]) for k in ("x", "y", "width", "height"))
        if w < 0 or h < 0:
            raise ValueError("rect width and height cannot be negative - move x/y to the other corner and use positive sizes")
        corner = str(el.get("corner", "round")).lower()
        if corner not in ("round", "cut"):
            raise ValueError("rect corner must be 'round' or 'cut'")
        g.box = (x, y, x + w, y + h)
        if w == 0 or h == 0:
            return g
        smooth = float(el.get("smoothing", 0) or 0)
        g.kind, g.rect = "rect", (x, y, w, h, el.get("radius", 0), corner, smooth)
        g.fills = [geo.rect_path(x, y, w, h, el.get("radius", 0), corner, res, smooth)]
    elif t == "ellipse":
        cx, cy, rx = float(el["cx"]), float(el["cy"]), float(el["rx"])
        ry = float(rx if el.get("ry") is None else el["ry"])
        if rx < 0 or ry < 0:
            raise ValueError("ellipse radii cannot be negative")
        g.box = (cx - rx, cy - ry, cx + rx, cy + ry)
        if rx == 0 or ry == 0:
            return g
        g.kind, g.ellipse = "ellipse", (cx, cy, rx, ry)
        g.fills = [geo.ellipse_path(cx, cy, rx, ry, res)]
    elif t == "polygon":
        if el.get("points"):
            pts = [(float(p[0]), float(p[1])) for p in el["points"]]
            if len(pts) < 3:
                raise ValueError("polygon needs at least 3 points, like [[0, 0], [10, 0], [5, 8]]")
        else:
            pts = geo.regular_polygon(float(el["cx"]), float(el["cy"]), float(el["radius"]), int(el.get("sides", 6)),
                                      float(el["inner_radius"]) if el.get("inner_radius") else None,
                                      float(el.get("point_rotation", 0)))
        if el.get("corner_radius"):
            pts = geo.round_corners(pts, float(el["corner_radius"]), res)
        g.fills = [pts]
        g.outline = [(pts, True)]
        g.box = geo.bbox_of([pts])
    elif t == "line":
        pts = [(float(p[0]), float(p[1])) for p in el.get("points", [])]
        if len(pts) < 2:
            raise ValueError("line needs at least 2 points, like [[0, 0], [100, 0]]")
        width = max(0.25, float(el.get("width", 2)))
        closed = bool(el.get("closed", False))
        pts = _line_ends(g, el, pts, width, closed)
        if el.get("width_profile") or el.get("taper") or el.get("wiggle"):
            g.fills += _variable_stroke(pts + ([pts[0]] if closed else []), width, el)
        else:
            g.lines = _dashed(el, pts, closed, width, str(el.get("cap", "round")).lower()) + g.lines
        x0, y0, x1, y1 = geo.bbox_of([pts] + g.fills + [p for p, _, _, _ in g.lines])
        g.box = (x0 - width / 2, y0 - width / 2, x1 + width / 2, y1 + width / 2)
    elif t == "arc":
        cx, cy, radius = float(el["cx"]), float(el["cy"]), float(el["radius"])
        start, end = float(el.get("start_angle", 0)), float(el.get("end_angle", 360))
        width = max(0.25, float(el.get("thickness", 4)))
        if radius <= 0:
            raise ValueError("arc radius must be > 0")
        g.paint_box = (cx - radius - width / 2, cy - radius - width / 2, cx + radius + width / 2, cy + radius + width / 2)
        if abs(end - start) < 1e-6:
            g.box = (cx, cy, cx, cy)
            return g
        full = abs(end - start) >= 360 - 1e-6
        pts = geo.arc_path(cx, cy, radius, start, start + 360 if full else end, res)
        if full:
            pts = pts[:-1]
        else:
            pts = _line_ends(g, el, pts, width, False)
        g.lines = _dashed(el, pts, full, width, str(el.get("cap", "butt")).lower()) + g.lines
        x0, y0, x1, y1 = geo.bbox_of([pts] + g.fills + [p for p, _, _, _ in g.lines])
        g.box = (x0 - width / 2, y0 - width / 2, x1 + width / 2, y1 + width / 2)
    elif t == "ticks":
        cx, cy, radius = float(el["cx"]), float(el["cy"]), float(el["radius"])
        start, end = float(el.get("start_angle", 0)), float(el.get("end_angle", 360))
        count = int(el.get("count", 11))
        length = float(el.get("length", 8))
        width = max(0.25, float(el.get("width", 2)))
        if count < 2 or radius <= 0 or length <= 0:
            raise ValueError("ticks need count >= 2, radius > 0 and length > 0")
        g.paint_box = (cx - radius, cy - radius, cx + radius, cy + radius)
        every = int(el.get("every", 1) or 1)
        skip_every = int(el.get("skip_every", 0) or 0)
        full = abs(end - start) >= 360 - 1e-6
        step = (end - start) / (count if full else count - 1)
        cap = str(el.get("cap", "butt")).lower()
        for i in range(count):
            if i % every or (skip_every and i % skip_every == 0):
                continue
            a = math.radians(start + step * i)
            ca, sa = math.cos(a), math.sin(a)
            g.lines.append(([(cx + radius * ca, cy + radius * sa),
                             (cx + (radius - length) * ca, cy + (radius - length) * sa)], False, width, cap))
        if not g.lines:
            raise ValueError("ticks: every / skip_every removed every tick - raise count or lower skip_every")
        x0, y0, x1, y1 = geo.bbox_of([pts for pts, _, _, _ in g.lines])
        g.box = (x0 - width / 2, y0 - width / 2, x1 + width / 2, y1 + width / 2)
    elif t == "path":
        scale = float(el.get("scale", 1))
        dx, dy = float(el.get("x", 0)), float(el.get("y", 0))
        subs = [(geo.transform(pts, scale, dx, dy), closed) for pts, closed in geo.parse_svg_path(el["d"], res * scale)]
        g.fills = [pts for pts, _ in subs if len(pts) >= 3]
        g.outline = subs
        g.box = geo.bbox_of([pts for pts, _ in subs])
    elif t == "boolean":
        g.fills = _boolean_polys(el, res)
        g.outline = [(pts, True) for pts in g.fills]
        g.box = geo.bbox_of(g.fills) if g.fills else (0, 0, 0, 0)
    else:
        raise ValueError(f"Not a vector element type: {t}")
    return g


def _placed_polys(el: dict, res: float) -> list[list[geo.Point]]:
    """A child's filled outlines with its own skew and rotation applied, for boolean operations."""
    if el.get("type") in LINE_TYPES or el.get("type") not in VECTOR_TYPES:
        raise ValueError(f"boolean: '{el.get('id')}' is a {el.get('type')}; only filled shapes (rect, ellipse, "
                         "polygon, path, boolean) can be combined - draw lines as thin rects or paths")
    g = vector_geometry(el, res)
    polys = [list(p) for p in g.fills]
    lean = _skew_tan(el)
    if lean:
        mid = (g.box[1] + g.box[3]) / 2
        polys = [[(x + (mid - y) * lean, y) for x, y in p] for p in polys]
    rot = float(el.get("rotation", 0) or 0)
    if rot:
        cx, cy = Renderer._pivot(el, g.box)
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        polys = [[(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in p]
                 for p in polys]
    return polys


def _boolean_polys(el: dict, res: float) -> list[list[geo.Point]]:
    """Exact polygon boolean of the children (first child = subject), like Figma / Penpot boolean groups."""
    import pyclipper
    op = str(el.get("op", "union")).lower()
    if op not in BOOLEAN_OPS:
        raise ValueError(f"boolean op must be one of {', '.join(BOOLEAN_OPS)}")
    children = el.get("children") or []
    if len(children) < 2:
        raise ValueError("boolean needs at least 2 child shapes")
    q = 1024.0

    def ints(polys):
        return [[(round(x * q), round(y * q)) for x, y in p] for p in polys if len(p) >= 3]

    def rule(child):
        nonzero = child.get("type") == "path" and str(child.get("fill_rule", "evenodd")).lower() == "nonzero"
        return pyclipper.PFT_NONZERO if nonzero else pyclipper.PFT_EVENODD

    clip_type = {"union": pyclipper.CT_UNION, "subtract": pyclipper.CT_DIFFERENCE,
                 "intersect": pyclipper.CT_INTERSECTION, "exclude": pyclipper.CT_XOR}[op]
    result = None
    for child in children:
        polys = ints(_placed_polys(child, res))
        pc = pyclipper.Pyclipper()
        if result is None:
            if not polys:
                result = []
                continue
            pc.AddPaths(polys, pyclipper.PT_SUBJECT, True)
            result = pc.Execute(pyclipper.CT_UNION, rule(child), rule(child))
            continue
        if not result and not polys:
            continue
        if result:
            pc.AddPaths(result, pyclipper.PT_SUBJECT, True)
        if polys:
            pc.AddPaths(polys, pyclipper.PT_CLIP, True)
        result = pc.Execute(clip_type, pyclipper.PFT_NONZERO, rule(child))
    return [[(x / q, y / q) for x, y in p] for p in (result or [])]


def _side_strips(rect: tuple, sides: list[str], d0: float, d1: float) -> list[list[geo.Point]]:
    """Strips along each chosen edge that hold that edge's stroke band (full length, like Figma)."""
    x, y, w, h = rect[:4]
    inner = max(0.0, -d0) + 0.01
    far = max(0.0, d1) + 1.0 + max(w, h)
    x0, y0, x1, y1 = x - far, y - far, x + w + far, y + h + far
    strips = {"top": (x0, y0, x1, y + inner), "bottom": (x0, y + h - inner, x1, y1),
              "left": (x0, y0, x + inner, y1), "right": (x + w - inner, y0, x1, y1)}
    return [[(a, b), (c, b), (c, d), (a, d)] for a, b, c, d in (strips[s] for s in sides)]


END_CAPS = ("none", "arrow", "triangle", "circle", "square", "diamond", "bar")


def _variable_stroke(pts: list, width: float, el: dict) -> list:
    """A line drawn as a filled outline whose width varies (Figma variable-width / dynamic strokes).
    width_profile: multipliers along the line, e.g. [0.2, 1, 0.4]; taper: "start" | "end" | "both";
    wiggle: {"amount": units, "frequency": waves per 100 units, "seed"} for hand-drawn wobble."""
    arr = np.asarray(pts, dtype=np.float64)
    seg = np.hypot(*np.diff(arr, axis=0).T)
    total = float(seg.sum())
    if total <= 0:
        return []
    step = max(0.4, width / 3)
    n = max(2, int(total / step) + 1)
    s_pts = np.concatenate([[0.0], np.cumsum(seg)])
    s = np.linspace(0, total, n)
    xy = np.column_stack((np.interp(s, s_pts, arr[:, 0]), np.interp(s, s_pts, arr[:, 1])))
    d = np.gradient(xy, axis=0)
    d /= np.maximum(1e-9, np.hypot(d[:, 0], d[:, 1]))[:, None]
    normal = np.column_stack((-d[:, 1], d[:, 0]))
    u = s / total
    profile = el.get("width_profile")
    taper = str(el.get("taper") or "").lower()
    if profile:
        vals = [float(v) for v in profile]
        mult = np.interp(u, np.linspace(0, 1, len(vals)), vals) if len(vals) > 1 else np.full(n, vals[0])
    elif taper in ("start", "end", "both"):
        mult = np.ones(n)
        if taper in ("start", "both"):
            mult = np.minimum(mult, np.clip(u / 0.35, 0.05, 1))
        if taper in ("end", "both"):
            mult = np.minimum(mult, np.clip((1 - u) / 0.35, 0.05, 1))
    elif taper:
        raise ValueError("taper must be 'start', 'end' or 'both'")
    else:
        mult = np.ones(n)
    wig = el.get("wiggle")
    if wig:
        if not isinstance(wig, dict):
            wig = {"amount": float(wig)}
        amount = float(wig.get("amount", width))
        freq = max(0.01, float(wig.get("frequency", 6))) / 100.0
        rng = np.random.default_rng(int(wig.get("seed", 1)))
        phases = rng.uniform(0, 2 * np.pi, 2)
        wob = (np.sin(2 * np.pi * freq * s + phases[0]) + 0.3 * np.sin(2 * np.pi * freq * 1.7 * s + phases[1])) / 1.3
        xy = xy + normal * (wob * amount)[:, None]
    half = np.maximum(0.05, width * mult / 2)[:, None]
    left, right = xy + normal * half, xy - normal * half
    polys = [list(map(tuple, np.vstack((left, right[::-1]))))]
    cap = str(el.get("cap", "round")).lower()
    if cap == "round":
        for i in (0, -1):
            r = float(half[i, 0])
            if r > 0.3:
                polys.append(geo.ellipse_path(float(xy[i, 0]), float(xy[i, 1]), r, r, 8.0))
    return polys


def _line_ends(g, el: dict, pts: list, width: float, closed: bool) -> list:
    """Figma-style line endings: add arrow / triangle / circle / square / diamond / bar shapes at the ends.
    Filled ends go to g.fills, open ones to g.lines; returns the line points (shortened under solid tips)."""
    if closed or len(pts) < 2:
        return pts
    size = max(1.0, float(el.get("cap_size", 3))) * width
    pts = list(pts)
    for which in ("start_cap", "end_cap"):
        kind = str(el.get(which) or "none").lower()
        if kind not in END_CAPS:
            raise ValueError(f"{which} must be one of {', '.join(END_CAPS)}")
        if kind == "none":
            continue
        tip, prev = (pts[0], pts[1]) if which == "start_cap" else (pts[-1], pts[-2])
        dx, dy = tip[0] - prev[0], tip[1] - prev[1]
        n = math.hypot(dx, dy) or 1.0
        ux, uy = dx / n, dy / n
        nx, ny = -uy, ux
        bx, by = tip[0] - ux * size, tip[1] - uy * size
        half = size * 0.6
        if kind == "triangle":
            g.fills.append([tip, (bx + nx * half, by + ny * half), (bx - nx * half, by - ny * half)])
            new_end = (bx + ux * 0.5, by + uy * 0.5)
            if which == "start_cap":
                pts[0] = new_end
            else:
                pts[-1] = new_end
        elif kind == "arrow":
            g.lines.append(([(bx + nx * half, by + ny * half), tip, (bx - nx * half, by - ny * half)],
                            False, width, "round"))
        elif kind == "circle":
            r = size * 0.45
            g.fills.append(geo.ellipse_path(tip[0], tip[1], r, r, 8.0))
        elif kind == "square":
            h = size * 0.4
            g.fills.append([(tip[0] + (ux + nx) * h, tip[1] + (uy + ny) * h), (tip[0] + (ux - nx) * h, tip[1] + (uy - ny) * h),
                            (tip[0] - (ux + nx) * h, tip[1] - (uy + ny) * h), (tip[0] - (ux - nx) * h, tip[1] - (uy - ny) * h)])
        elif kind == "diamond":
            h = size * 0.5
            g.fills.append([(tip[0] + ux * h, tip[1] + uy * h), (tip[0] + nx * h, tip[1] + ny * h),
                            (tip[0] - ux * h, tip[1] - uy * h), (tip[0] - nx * h, tip[1] - ny * h)])
        else:
            g.lines.append(([(tip[0] + nx * size * 0.6, tip[1] + ny * size * 0.6),
                             (tip[0] - nx * size * 0.6, tip[1] - ny * size * 0.6)], False, width, "butt"))
    return pts


def _dashed(el: dict, pts: list, closed: bool, width: float, cap: str) -> list:
    dash = el.get("dash")
    if not dash:
        return [(pts, closed, width, cap)]
    if isinstance(dash, (int, float)):
        dash = [dash, dash]
    pieces = geo.dash_polyline(pts, closed, dash, float(el.get("dash_offset", 0) or 0))
    if not pieces:
        raise ValueError("dash pattern left nothing to draw - make the dash longer than 0 or the gap shorter")
    return [(piece, False, width, cap) for piece in pieces]


def _skew_tan(el: dict) -> float:
    skew = float(el.get("skew", 0) or 0)
    if abs(skew) > 75:
        raise ValueError("skew must be between -75 and 75 degrees")
    return math.tan(math.radians(skew))


def _inset_rect(rect: tuple, delta: float, res: float) -> list[geo.Point] | None:
    """Rect outline grown (delta > 0) or shrunk (delta < 0) by ``delta`` on every side."""
    x, y, w, h, radius, corner, smooth = rect
    nw, nh = w + 2 * delta, h + 2 * delta
    if nw <= 0 or nh <= 0:
        return None
    radii = geo.normalize_radii(radius, w, h)
    factor = CUT_K if corner == "cut" else 1.0
    radii = [max(0.0, r + delta * factor) if r > 0 else 0.0 for r in radii]
    return geo.rect_path(x - delta, y - delta, nw, nh, radii, corner, res, smooth)



class Renderer:
    def __init__(self, canvas: dict, theme: dict, fonts: FontLibrary, scale: float = 1.0,
                 lookup=None, depth: int = 0, state: str | None = None, language: str | None = None,
                 strings: dict | None = None, extra_vars: dict | None = None, extra_colors: dict | None = None,
                 extra_data: dict | None = None):
        if canvas.get("bindings") or extra_data:
            from . import binding
            canvas = binding.apply_bindings(canvas, extra_data)
        if state:
            canvas = apply_state(canvas, state)
        self.canvas = canvas
        self.lookup = lookup
        self.depth = depth
        self.theme = theme
        self.state = state
        self.language = language
        self.strings = strings or {}
        self.mode = canvas.get("mode") or theme.get("mode")
        mode_vals = ((theme.get("modes") or {}).get(self.mode) or {}) if self.mode else {}
        mode_colors = {k: v for k, v in mode_vals.items() if not _is_number(v)}
        self.colors = {**theme.get("colors", {}), **mode_colors, **(canvas.get("colors") or {}),
                       **(extra_colors or {})}
        self.numbers = {**(theme.get("numbers") or {}), **{k: v for k, v in mode_vals.items() if _is_number(v)},
                        **(canvas.get("numbers") or {})}
        self._num_cache: dict[int, tuple] = {}
        merged_vars = {**(canvas.get("data") or {}), **(extra_vars or {})}
        self.text_vars = text_vars(canvas, language, self.strings, merged_vars)
        self.fonts = fonts
        self.k = float(scale)
        self.width = max(1, int(round(canvas["width"] * self.k)))
        self.height = max(1, int(round(canvas["height"] * self.k)))
        if self.width * self.height > MAX_OUTPUT_PIXELS:
            raise ValueError(f"render would be {self.width}x{self.height} px, over the {MAX_OUTPUT_PIXELS // 1_000_000}M "
                             "pixel limit - lower scale or export a region")
        self.warnings: list[str] = []
        self._by_id = {e["id"]: e for e in canvas["elements"]}


    def render(self, include_background: bool = True, only: set[str] | None = None,
               only_layers: set[str] | None = None) -> Image.Image:
        pixel = self.canvas.get("pixel_art")
        if pixel and not getattr(self, "_pixel_pass", False):
            base = self.derive(1.0)
            base._pixel_pass = True
            img = base.render(include_background, only, only_layers)
            self.warnings += base.warnings
            img = pixelate(img, pixel if isinstance(pixel, dict) else {}, self.colors)
            if (self.width, self.height) != img.size:
                img = img.resize((self.width, self.height), Image.NEAREST)
            return img
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        bg = self.canvas.get("background")
        if include_background and not _is_none(bg):
            full = Image.new("L", img.size, 255)
            layer = paint(full, bg, (0, 0, self.width, self.height), self.colors, self.k)
            if layer is not None:
                img = Image.alpha_composite(img, layer)
        return self.render_stack(img, only, only_layers)

    def _nums(self, obj):
        """``obj`` with "$number-token" strings replaced by their values (same object when there are none)."""
        if not self.numbers:
            return obj
        hit = self._num_cache.get(id(obj))
        if hit is not None and hit[0] is obj:
            return hit[1]
        out = _sub_numbers(obj, self.numbers)
        self._num_cache[id(obj)] = (obj, out)
        return out

    def element_box(self, el: dict) -> Box:
        """Bounds of the element geometry in canvas units (no effects), after rotation."""
        el = self._nums(el)
        st = self._nums(resolve_style(el.get("style"), self.theme))
        box = self._geom_box(el, st)
        pivot = self._pivot(el, box)
        sx, sy = _scales(el)
        if sx != 1 or sy != 1:
            xs = sorted((pivot[0] + (box[0] - pivot[0]) * sx, pivot[0] + (box[2] - pivot[0]) * sx))
            ys = sorted((pivot[1] + (box[1] - pivot[1]) * sy, pivot[1] + (box[3] - pivot[1]) * sy))
            box = (xs[0], ys[0], xs[1], ys[1])
        rot = float(el.get("rotation", 0) or 0)
        if (sx < 0) != (sy < 0):
            rot = -rot
        return geo.rotated_bbox(box, rot, pivot)

    def derive(self, scale: float) -> "Renderer":
        """Same canvas, context and colours at another resolution."""
        r = Renderer.__new__(Renderer)
        r.__dict__.update(self.__dict__)
        r.k = float(scale)
        r.width = max(1, int(round(self.canvas["width"] * r.k)))
        r.height = max(1, int(round(self.canvas["height"] * r.k)))
        r.warnings = []
        return r

    def text_of(self, el: dict) -> str:
        """The text an element shows: {placeholders} filled from vars / string tables, then the
        pseudo-localisation transform when language is "pseudo"."""
        raw = str(el.get("text", ""))
        missing: list[str] = []

        def sub(m) -> str:
            key = m.group(1)
            if key in self.text_vars:
                return str(self.text_vars[key])
            missing.append(key)
            return m.group(0)

        text = _PLACEHOLDER.sub(sub, raw)
        if missing:
            msg = f"{el.get('id')}: no value for {', '.join('{' + k + '}' for k in missing)}" + (
                f" in language '{self.language}'" if self.language else "")
            if msg not in self.warnings:
                self.warnings.append(msg)
        if self.language in PSEUDO_LANGS:
            text = pseudo_localize(text, self.language)
        return text

    def text_lang(self, el: dict) -> str | None:
        """Language tag for shaping: the element's own, else the render language, else the canvas'."""
        lang = self.language if self.language and not str(self.language).startswith("pseudo") else None
        return el.get("lang") or lang or self.canvas.get("language")

    def glyph_problems(self) -> dict[str, str]:
        """{element id: characters no font can draw} for every text element (exports refuse these)."""
        out = {}
        for el in self.canvas.get("elements", []):
            if el.get("type") != "text" or el.get("visible") is False:
                continue
            st = resolve_style(el.get("style"), self.theme)
            miss = TextLayout(el, st, self.fonts, 1.0, self.text_of(el), self.text_lang(el)).missing()
            if miss:
                out[el["id"]] = "".join(miss)
        return out

    @staticmethod
    def _pivot(el: dict, box: Box) -> tuple[float, float]:
        """Rotation centre: the element's ``origin`` [x, y] if given, else the middle of its box."""
        origin = el.get("origin")
        if origin:
            try:
                return float(origin[0]), float(origin[1])
            except (TypeError, IndexError, ValueError) as exc:
                raise ValueError("origin must be [x, y]") from exc
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


    def _geom_box(self, el: dict, st: dict) -> Box:
        t = el["type"]
        if t in VECTOR_TYPES:
            box = vector_geometry(el, 1.0).box
            lean = abs(_skew_tan(el)) * (box[3] - box[1]) / 2
            return (box[0] - lean, box[1], box[2] + lean, box[3])
        if t == "text":
            layout = TextLayout(el, st, self.fonts, 4.0, self.text_of(el), self.text_lang(el))
            box = layout.box_units()
            lean = abs(math.tan(math.radians(layout.skew))) * (box[3] - box[1]) / 2
            return (box[0] - lean, box[1], box[2] + lean, box[3])
        if t in BITMAP_TYPES:
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            w, h = self._image_size(el)
            return (x, y, x + w, y + h)
        if t in WIDGET_TYPES:
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            def_w = 52.0 if t == "toggle" else 220.0
            def_h = {"input": 40.0, "scroll": 180.0, "slider": 28.0, "toggle": 28.0, "dropdown": 40.0}.get(t, 40.0)
            w = max(16.0, float(el.get("width", def_w)))
            h = max(16.0, float(el.get("height", def_h)))
            top_pad = 22.0 if (t in ("input", "slider", "dropdown") and el.get("label")) else 0.0
            right_pad = 0.0
            if t == "toggle" and el.get("label"):
                right_pad = max(60.0, len(str(el["label"])) * float(el.get("size", 14)) * 0.65 + 14.0)
            return (x, y - top_pad, x + w + right_pad, y + h)
        raise ValueError(f"Unknown element type '{t}'")

    def _source_canvas(self, el: dict) -> dict:
        """The canvas an instance element shows (posed at its animation time, if any)."""
        src_id = str(el.get("source", ""))
        if not src_id:
            raise ValueError("instance needs 'source' (the id of another canvas)")
        if src_id == self.canvas.get("id"):
            raise ValueError("an instance cannot show the canvas it is placed on")
        if self.lookup is None:
            raise ValueError("instances are not available here")
        src = self.lookup(src_id)
        if self.depth == 0:
            loop = _instance_cycle(src, self.canvas.get("id"), self.lookup)
            if loop:
                raise ValueError("instance loop: " + " -> ".join([str(self.canvas.get("id"))] + loop)
                                 + " (a canvas cannot end up containing itself)")
        if self.depth >= MAX_INSTANCE_DEPTH:
            raise ValueError(f"instances nest deeper than {MAX_INSTANCE_DEPTH} levels")
        if el.get("animation"):
            from .animation import apply_animation
            anims = src.get("animations") or {}
            name = str(el["animation"])
            if name not in anims:
                known = ", ".join(sorted(anims)) or "(none)"
                raise ValueError(f"source canvas '{src_id}' has no animation '{name}'. Animations: {known}")
            anim = anims[name]
            t = float(el.get("time", 0) or 0)
            dur = float(anim.get("duration", 1) or 1)
            if anim.get("loop", True) and dur > 0:
                t = t % dur
            src, _ = apply_animation(src, anim, t, self.colors)
        return src

    def _image_size(self, el: dict) -> tuple[float, float]:
        w, h = el.get("width"), el.get("height")
        if w and h:
            return float(w), float(h)
        if el["type"] == "instance":
            src = self._source_canvas(el)
            iw, ih = float(src["width"]), float(src["height"])
        else:
            iw, ih = self._load_image(el).size
        if w:
            return float(w), float(w) * ih / iw
        if h:
            return float(h) * iw / ih, float(h)
        return float(iw), float(ih)

    def _load_image(self, el: dict) -> Image.Image:
        path = Path(str(el.get("path", ""))).expanduser()
        if not path.is_file():
            raise ValueError(f"Image file not found: {path.resolve()} - use an absolute path (relative paths resolve against the server's working folder, not yours)")
        return load_frame(path, el)

    def _region(self, box: Box, pad: float, clip: bool = True) -> tuple[int, int, int, int] | None:
        """Pixel region (x0, y0, w, h) covering ``box`` + pad, limited to the padded canvas."""
        k = self.k
        x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
        if clip:
            x0, y0 = max(x0, -pad - 2), max(y0, -pad - 2)
            x1, y1 = min(x1, self.canvas["width"] + pad + 2), min(y1, self.canvas["height"] + pad + 2)
        if x1 <= x0 or y1 <= y0:
            return None
        px0, py0 = int(math.floor(x0 * k)) - 1, int(math.floor(y0 * k)) - 1
        px1, py1 = int(math.ceil(x1 * k)) + 1, int(math.ceil(y1 * k)) + 1
        return px0, py0, px1 - px0, py1 - py0

    def _profile(self) -> dict:
        from . import profiles
        return profiles.resolve_profile(self.theme, self.canvas)

    def _pick_ss(self, w: int, h: int) -> int:
        if self.canvas.get("pixel_art"):
            return 1
        ss = min(SS, int(self._profile().get("ss_max", SS)))
        while ss > 1 and w * h * ss * ss > MAX_MASK_PIXELS:
            ss -= 1
        return ss

    def _vector_masks(self, el: dict, st: dict, region, ss: int, strokes: list[dict]):
        """Return (shape_mask, [stroke_mask per stroke]) at region size."""
        px0, py0, w, h = region
        k = self.k
        f = k * ss
        g = vector_geometry(el, f)
        bw, bh = w * ss, h * ss
        offset = np.array([px0 * ss, py0 * ss], dtype=np.float64)

        lean = _skew_tan(el)
        mid_y = (g.box[1] + g.box[3]) / 2

        def px(pts) -> np.ndarray:
            arr = np.asarray(pts, dtype=np.float64)
            if lean:
                arr = arr.copy()
                arr[:, 0] += (mid_y - arr[:, 1]) * lean
            return arr * f - offset

        rule = (str(el.get("fill_rule", "evenodd")).lower() if el["type"] == "path"
                else "nonzero" if el["type"] in LINE_TYPES else "evenodd")
        if rule not in ("evenodd", "nonzero"):
            raise ValueError("fill_rule must be 'evenodd' or 'nonzero'")

        def fill(polys, how: str | None = None) -> np.ndarray:
            return raster.fill_polygons([px(p) for p in polys], bw, bh, how or rule)

        def lines(items) -> np.ndarray:
            return raster.stroke_polylines(
                [(px(pts), closed, width * f / 2.0, cap == "round") for pts, closed, width, cap in items], bw, bh)

        shape = fill(g.fills)
        if g.lines:
            shape = shape | lines(g.lines)

        bands: list[np.ndarray] = []
        if strokes and el["type"] not in LINE_TYPES:
            closed_paths = [pts for pts, c in g.outline if c]
            open_paths = [pts for pts, c in g.outline if not c]
            inside = fill(closed_paths) if closed_paths else None

            def grown(d: float, join: str = "round", limit: float = 4.0) -> np.ndarray:
                """The shape grown (d > 0) or shrunk (d < 0) by distance d."""
                if g.kind == "rect":
                    poly = _inset_rect(g.rect, d, f) if d else g.fills[0]
                    return fill([poly]) if poly else np.zeros((bh, bw), dtype=np.uint8)
                if g.kind == "ellipse":
                    cx, cy, rx, ry = g.ellipse
                    if rx + d <= 0 or ry + d <= 0:
                        return np.zeros((bh, bw), dtype=np.uint8)
                    return fill([geo.ellipse_path(cx, cy, rx + d, ry + d, f)])
                if inside is None:
                    return np.zeros((bh, bw), dtype=np.uint8)
                if d == 0:
                    return inside
                rim = lines([(pts, True, abs(d) * 2, "round") for pts in closed_paths])
                if join == "round":
                    return (inside | rim) if d > 0 else (inside & ~rim)
                sharp = fill(geo.offset_shape(closed_paths, d, join, limit), "evenodd")
                if d > 0:
                    return inside | rim | sharp
                return inside & (~rim | sharp)

            for spec in strokes:
                if g.kind == "poly" and not g.fills and not g.outline:
                    bands.append(np.zeros((bh, bw), dtype=np.uint8))
                    continue
                join = spec["join"] or ("miter" if g.kind == "poly" else "round")
                band = (grown(spec["d1"], join, spec["miter_limit"])
                        & ~grown(spec["d0"], join, spec["miter_limit"]))
                if open_paths:
                    band = band | lines([(pts, False, spec["width"], "round") for pts in open_paths])
                if spec["sides"]:
                    if g.kind != "rect":
                        raise ValueError("stroke.sides works on rects only (Figma individual strokes)")
                    band = band & fill(_side_strips(g.rect, spec["sides"], spec["d0"], spec["d1"]), "nonzero")
                if spec["dash"]:
                    edge = [(pts, c) for pts, c in g.outline] if g.outline else [(pts, True) for pts in g.fills]
                    reach = 4 * max(abs(spec["d0"]), abs(spec["d1"])) + 2.0 / f
                    pieces = []
                    for pts, c in edge:
                        pieces += geo.dash_polyline(pts, c, spec["dash"], spec["dash_offset"])
                    band = band & lines([(pc, False, reach, "butt") for pc in pieces]) if pieces else band * 0
                bands.append(band)

        shape_img = Image.fromarray(shape, "L")
        stroke_imgs = [Image.fromarray(b, "L") for b in bands]
        rot = float(el.get("rotation", 0) or 0)
        if rot:
            pvx, pvy = self._pivot(el, g.box)
            cx = (pvx * k - px0) * ss
            cy = (pvy * k - py0) * ss
            shape_img = shape_img.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy))
            stroke_imgs = [m.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy)) for m in stroke_imgs]
        if ss > 1:
            shape_img = shape_img.reduce(ss)
            stroke_imgs = [m.reduce(ss) for m in stroke_imgs]
        return shape_img, stroke_imgs

    def _text_masks(self, el: dict, st: dict, region, ss: int, strokes: list[dict]):
        px0, py0, w, h = region
        k = self.k
        layout = TextLayout(el, st, self.fonts, k * ss, self.text_of(el), self.text_lang(el))
        self.warnings += [w for w in layout.warnings if w not in self.warnings]
        miss = layout.missing()
        if miss:
            self.warnings.append(
                f"{el['id']}: font '{layout.family or 'Inter'}' has no glyph for {''.join(miss)!r}; pick another font.")
        note = layout.fallback_note()
        if note and f"{el['id']}: {note}" not in self.warnings:
            self.warnings.append(f"{el['id']}: {note}")
        big = (w * ss, h * ss)

        def glyphs(grow_units: float) -> Image.Image:
            img = Image.new("L", big, 0)
            grow_px = int(round(grow_units * k * ss)) if grow_units > 0 else 0
            if layout.arc is not None:
                layout.draw_arc(img, px0 * ss, py0 * ss, grow_px)
            else:
                layout.draw(img, px0 * ss, py0 * ss, grow_px)
            return img

        shape = glyphs(0)
        color = layout.color_layer(big, px0 * ss, py0 * ss)
        masks = []
        for spec in strokes:
            inner = max(0.0, spec["offset"])
            band = glyphs(inner + spec["width"])
            if inner > 0:
                band = ImageChops.subtract(band, glyphs(inner))
            masks.append(band)
        bx0, by0, bx1, by1 = layout.box_px
        if layout.skew and layout.arc is None:
            lean = math.tan(math.radians(layout.skew))
            mid = (by0 + by1) / 2 - py0 * ss
            matrix = (1, lean, -lean * mid, 0, 1, 0)
            shape = shape.transform(big, Image.AFFINE, matrix, resample=Image.BICUBIC)
            masks = [m.transform(big, Image.AFFINE, matrix, resample=Image.BICUBIC) for m in masks]
            if color is not None:
                color = color.transform(big, Image.AFFINE, matrix, resample=Image.BICUBIC)
        rot = float(el.get("rotation", 0) or 0)
        if rot:
            if el.get("origin"):
                pvx, pvy = self._pivot(el, (0, 0, 0, 0))
                cx, cy = (pvx * k - px0) * ss, (pvy * k - py0) * ss
            else:
                cx, cy = (bx0 + bx1) / 2 - px0 * ss, (by0 + by1) / 2 - py0 * ss
            shape = shape.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy))
            masks = [m.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy)) for m in masks]
            if color is not None:
                color = color.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy))
        if ss > 1:
            shape = shape.reduce(ss)
            masks = [m.reduce(ss) for m in masks]
            if color is not None:
                color = color.reduce(ss)
        self._text_color = color
        return shape, masks

    def _instance_image(self, el: dict, tw: int, th: int) -> Image.Image:
        src = _component_overrides(self._source_canvas(el), el, self.lookup)
        fit = str(el.get("fit", "stretch")).lower()
        sx, sy = tw / float(src["width"]), th / float(src["height"])
        scale = max(sx, sy) if fit in ("stretch", "cover") else min(sx, sy)
        sub = Renderer(src, self.theme, self.fonts, scale, self.lookup, self.depth + 1, state=el.get("state"),
                       language=self.language, strings=self.strings,
                       extra_vars={**{k: v for k, v in self.text_vars.items() if k in (el.get("pass_vars") or [])},
                                   **(el.get("vars") or {})},
                       extra_colors=el.get("colors"))
        img = sub.render(include_background=bool(el.get("background", True)))
        self.warnings += [f"{el['id']} -> {w}" for w in sub.warnings]
        return img

    def _image_layer(self, el: dict, region):
        """Return (alpha_mask, rgba_layer) for an image or instance element at region size."""
        px0, py0, w, h = region
        k = self.k
        uw, uh = self._image_size(el)
        tw, th = max(1, int(round(uw * k))), max(1, int(round(uh * k)))
        src = self._instance_image(el, tw, th) if el["type"] == "instance" else self._load_image(el)
        fit = str(el.get("fit", "stretch")).lower()
        if fit == "stretch" and src.size == (tw, th) and not el.get("zoom") and not el.get("focus"):
            img = src
        elif fit in ("stretch", "cover"):
            img = src.resize((tw, th), Image.LANCZOS, box=view_box(src.size, (tw, th), fit, el))
        elif fit == "contain":
            ratio = (min if fit == "contain" else max)(tw / src.width, th / src.height)
            rs = src.resize((max(1, int(round(src.width * ratio))), max(1, int(round(src.height * ratio)))), Image.LANCZOS)
            img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            img.paste(rs, ((tw - rs.width) // 2, (th - rs.height) // 2))
        else:
            raise ValueError("image fit must be 'stretch', 'contain' or 'cover'")
        if el.get("radius"):
            ss = 4
            pts = geo.rect_path(0, 0, tw / k, th / k, el["radius"], str(el.get("corner", "round")), k * ss)
            m = Image.fromarray(raster.fill_polygons([np.asarray(pts) * k * ss], tw * ss, th * ss), "L")
            img.putalpha(ImageChops.multiply(img.getchannel("A"), m.reduce(ss)))
        if not _is_none(el.get("tint")):
            r, g, b, a = parse_color(el["tint"], self.colors)
            alpha = img.getchannel("A")
            img = Image.new("RGBA", img.size, (r, g, b, 0))
            img.putalpha(alpha if a == 255 else alpha.point(lambda v: v * a // 255))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        fx_, fy_ = float(el.get("x", 0)) * k - px0, float(el.get("y", 0)) * k - py0
        ox, oy = int(math.floor(fx_)), int(math.floor(fy_))
        sub_x, sub_y = fx_ - ox, fy_ - oy
        if (sub_x > 0.02 or sub_y > 0.02) and not self.canvas.get("pixel_art"):
            padded = Image.new("RGBa", (img.width + 3, img.height + 3), (0, 0, 0, 0))
            padded.paste(img.convert("RGBa"), (1, 1))
            img = padded.transform(padded.size, Image.AFFINE, (1, 0, -sub_x, 0, 1, -sub_y),
                                   resample=Image.BICUBIC).convert("RGBA")
            ox, oy = ox - 1, oy - 1
        layer.paste(img, (ox, oy))
        rot = float(el.get("rotation", 0) or 0)
        if rot:
            centre = (fx_ + tw / 2, fy_ + th / 2)
            if el.get("origin"):
                pvx, pvy = self._pivot(el, (0, 0, 0, 0))
                centre = (pvx * k - px0, pvy * k - py0)
            layer = layer.rotate(-rot, resample=Image.BICUBIC, center=centre)
        return layer.getchannel("A"), layer

    def shape_mask(self, el: dict, region) -> Image.Image:
        """Filled-shape coverage of an element inside ``region`` (used for clipping)."""
        el = self._nums(el)
        st = self._nums(resolve_style(el.get("style"), self.theme))
        t = el["type"]
        ss = min(2, self._pick_ss(region[2], region[3]))
        if t in VECTOR_TYPES:
            return self._vector_masks(el, st, region, ss, [])[0]
        if t == "text":
            return self._text_masks(el, st, region, ss, [])[0]
        if t in WIDGET_TYPES:
            from . import widgets
            return widgets.render_widget(self, el, st, region)[0]
        return self._image_layer(el, region)[0]

    def _env_cfg(self) -> dict:
        """Merge workspace theme environment with canvas-level environment override."""
        base = dict(self.theme.get("environment") or {})
        override = self.canvas.get("environment") or {}
        if isinstance(override, dict):
            base.update(override)
        return base

    def _pbr_spec(self, raw_spec) -> dict | None:
        """Merge workspace/canvas HDRI environment defaults and quality profile into an element's PBR spec."""
        if not raw_spec:
            return None
        from . import profiles
        spec = dict(raw_spec) if isinstance(raw_spec, dict) else {}
        env = self._env_cfg()
        if env:
            if env.get("env_map") and not spec.get("env_map"):
                spec["env_map"] = env["env_map"]
            if env.get("studio") and "studio" not in spec:
                spec["studio"] = env["studio"]
            if "rotation" in env and "env_rotation" not in spec:
                spec["env_rotation"] = float(env["rotation"])
            if "env_rotation" in env and "env_rotation" not in spec:
                spec["env_rotation"] = float(env["env_rotation"])
            if "intensity" in env and "env" not in spec:
                spec["env"] = float(env["intensity"])
            elif "env" in env and "env" not in spec:
                spec["env"] = float(env["env"])
        return profiles.apply_quality_to_pbr(spec, self._profile())

    def _el_cache_key(self, el: dict, st: dict) -> str | None:
        """Content key for caching a rendered element, or None if the element depends on external state."""
        t = el.get("type")
        if t in ("instance", "image") or el.get("clip"):
            return None
        if t in ("input", "slider", "toggle", "dropdown") and el.get("bind"):
            return None
        if st.get("backdrop_blur") or st.get("glass"):
            return None
        fill = st.get("fill")
        if isinstance(fill, dict) and str(fill.get("type", "")).lower() == "image":
            return None
        if isinstance(fill, list) and any(isinstance(f, dict) and str(f.get("type", "")).lower() == "image" for f in fill):
            return None
        prof = self._profile()
        payload = {
            "el": el, "st": st, "k": round(self.k, 5),
            "cw": self.canvas["width"], "ch": self.canvas["height"],
            "px": bool(self.canvas.get("pixel_art")),
            "cols": self.colors,
            "q": prof["quality"],
            "sp": prof.get("style_preset"),
        }
        if st.get("pbr"):
            env = self._env_cfg()
            if env:
                payload["env"] = env
        if t == "text":
            payload["txt"] = self.text_of(el)
            payload["lang"] = self.text_lang(el)
            payload["fonts_dir"] = str(self.fonts.user_dir or "")
        raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def render_element(self, el: dict):
        """Render one element to (layer, x, y, blend). Handles scale_x / scale_y, which grow or shrink
        the finished element (effects included) around its pivot, the way an engine scales a widget."""
        el = self._nums(el)
        st_resolved = self._nums(resolve_style(el.get("style"), self.theme))
        ckey = self._el_cache_key(el, st_resolved)
        if ckey is not None:
            found, cached = _cache_get(ckey)
            if found:
                res, cwarns = cached
                for w in cwarns:
                    if w not in self.warnings:
                        self.warnings.append(w)
                return res
        w_before = len(self.warnings)
        sx, sy = _scales(el)
        if sx == 1 and sy == 1:
            res = self._render_plain(el)
            if ckey is not None:
                _cache_put(ckey, (res, tuple(self.warnings[w_before:])))
            return res
        if sx == 0 or sy == 0:
            return None
        ax, ay = abs(sx), abs(sy)
        if max(ax, ay) > 16:
            raise ValueError("scale is limited to 16")
        fx_, fy_ = sx < 0, sy < 0
        k = self.k
        m = max(ax, ay)
        drop = ("scale_x", "scale_y", "flip_x", "flip_y", "clip") + (() if el["type"] == "path" else ("scale",))
        plain = {key: value for key, value in el.items() if key not in drop}
        if fx_ or fy_:
            plain["style"] = _mirror_style(resolve_style(el.get("style"), self.theme), fx_, fy_)
            if fx_ != fy_ and plain.get("rotation"):
                plain["rotation"] = -float(plain["rotation"])
        if m == 1:
            sub = self
            result = self._render_plain(plain, clip_region=False)
        else:
            sub = self.derive(k * m)
            result = sub._render_plain(plain, clip_region=False)
            self.warnings += sub.warnings
        if result is None:
            return None
        layer, px0, py0, blend = result
        if ax != ay:
            layer = layer.resize((max(1, int(round(layer.width * ax / m))), max(1, int(round(layer.height * ay / m)))),
                                 Image.LANCZOS)
        st = resolve_style(el.get("style"), self.theme)
        pvx, pvy = self._pivot(el, self._geom_box(plain, st))
        lx = (pvx * k * m - px0) * ax / m
        ly = (pvy * k * m - py0) * ay / m
        if fx_:
            layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
            lx = layer.width - lx
        if fy_:
            layer = layer.transpose(Image.FLIP_TOP_BOTTOM)
            ly = layer.height - ly
        ox = int(round(pvx * k - lx))
        oy = int(round(pvy * k - ly))
        clip_id = el.get("clip")
        if clip_id:
            target = self._by_id.get(clip_id)
            if target is None:
                raise ValueError(f"clip target '{clip_id}' does not exist on this canvas")
            cm = self.shape_mask(target, (ox, oy, layer.width, layer.height))
            layer.putalpha(ImageChops.multiply(layer.getchannel("A"), cm))
        res = (layer, ox, oy, blend)
        if ckey is not None:
            _cache_put(ckey, (res, tuple(self.warnings[w_before:])))
        return res

    def _render_plain(self, el: dict, clip_region: bool = True):
        el = self._nums(el)
        st = self._nums(resolve_style(el.get("style"), self.theme))
        t = el["type"]
        k = self.k
        opacity = float(st.get("opacity", 1.0))
        if opacity <= 0:
            return None
        fx = Effects(st, self.colors)
        strokes = _stroke_specs(st, self.colors)
        box = self._geom_box(el, st)
        if t == "text":
            grow = max((sp["offset"] + sp["width"] for sp in strokes), default=0.0)
        else:
            grow = 0.0
            for sp in strokes:
                reach = max(0.0, sp["d1"])
                if t in ("polygon", "path") and (sp["join"] or "miter") == "miter":
                    reach *= sp["miter_limit"]
                grow = max(grow, reach)
        gbox = (box[0] - grow, box[1] - grow, box[2] + grow, box[3] + grow)
        rot = float(el.get("rotation", 0) or 0)
        soften, soften_prog = fxlib.blur_amount(st.get("blur"))
        feather = max(0.0, float(st.get("feather", 0) or 0))
        pad = fx.pad() + soften * 1.5 + feather * 1.5 + (3 if t == "text" else 1)
        if st.get("perspective") or el.get("perspective"):
            pad = max(pad, max(gbox[2] - gbox[0], gbox[3] - gbox[1]) * 0.18 + 8.0)
        pivot = self._pivot(el, box)
        if rot:
            half = max(math.hypot(px_ - pivot[0], py_ - pivot[1])
                       for px_ in (gbox[0], gbox[2]) for py_ in (gbox[1], gbox[3]))
            cx, cy = pivot
            region = self._region((cx - half, cy - half, cx + half, cy + half), pad, clip=False)
        else:
            region = self._region(gbox, pad, clip=clip_region)
        if region is None:
            return None
        px0, py0, w, h = region
        ss = self._pick_ss(w, h)

        color_layer = None
        if t in VECTOR_TYPES:
            shape, smasks = self._vector_masks(el, st, region, ss, strokes)
        elif t == "text":
            shape, smasks = self._text_masks(el, st, region, ss, strokes)
        elif t in BITMAP_TYPES:
            shape, color_layer = self._image_layer(el, region)
            smasks = []
        elif t in WIDGET_TYPES:
            from . import widgets
            shape, layer = widgets.render_widget(self, el, st, region)
            if st.get("adjust"):
                layer = fxlib.adjust(layer, st["adjust"], self.colors)
            if soften > 0:
                wbox_px = (box[0] * k - px0, box[1] * k - py0, box[2] * k - px0, box[3] * k - py0)
                prog = fxlib.progressive_t((w, h), soften_prog, wbox_px) if soften_prog else None
                layer = fxlib.blur_image(layer, soften * k / 2, prog)
            clip_id = el.get("clip")
            if clip_id:
                target = self._by_id.get(clip_id)
                if target is None:
                    raise ValueError(f"clip target '{clip_id}' does not exist on this canvas")
                cm = self.shape_mask(target, region)
                layer.putalpha(ImageChops.multiply(layer.getchannel("A"), cm))
            if opacity < 1:
                layer.putalpha(layer.getchannel("A").point(lambda v: int(v * opacity + 0.5)))
            blend = str(st.get("blend", "normal")).lower()
            if blend not in BLENDS:
                raise ValueError(f"style.blend must be one of {', '.join(BLENDS)}")
            return layer, px0, py0, blend
        else:
            raise ValueError(f"Unknown element type '{t}'")
        if feather > 0:
            from PIL import ImageFilter as _IF
            shape = shape.filter(_IF.GaussianBlur(feather * k / 2))
            smasks = [m.filter(_IF.GaussianBlur(feather * k / 2)) for m in smasks]
        if not _is_none(st.get("texture")):
            origin = (px0 / k, py0 / k)
            shape = fxlib.roughen(shape, st["texture"], k, origin)
            smasks = [fxlib.roughen(m, st["texture"], k, origin) for m in smasks]
        drawn = list(zip(strokes, smasks))

        fill_spec = st.get("fill", "#ffffff" if (not strokes or t in LINE_TYPES or t == "text") else None)
        has_fill = color_layer is not None or not _is_none(fill_spec)
        if not has_fill and not drawn:
            return None
        sil = shape if has_fill else Image.new("L", (w, h), 0)
        for _, m in drawn:
            sil = ImageChops.lighter(sil, m)

        paint_ref = vector_geometry(el, 1.0).paint_box if t in ("arc", "ticks") else None
        rbox_plain = geo.rotated_bbox(paint_ref or box, rot, pivot)
        box_px = (rbox_plain[0] * k - px0, rbox_plain[1] * k - py0, rbox_plain[2] * k - px0, rbox_plain[3] * k - py0)
        layer = _outer_effects(Image.new("RGBA", (w, h), (0, 0, 0, 0)), sil, fx, k)

        def draw_strokes(target: Image.Image, items) -> Image.Image:
            for spec, m in items:
                img = paint(m, spec["paint"], box_px, self.colors, k)
                if img is not None:
                    target = Image.alpha_composite(target, img)
            return target

        if t == "text":
            layer = draw_strokes(layer, reversed(drawn))
            drawn = []
        emoji = self.__dict__.pop("_text_color", None) if t == "text" else None

        if has_fill:
            light_spec = st.get("light")
            pbr_spec = st.get("pbr")
            want_bump = bool(light_spec or pbr_spec)
            sdf_arr: np.ndarray | None = None
            def _needs_sdf(fs) -> bool:
                if isinstance(fs, dict) and str(fs.get("type", "")).lower() == "shader":
                    code_t = str(fs.get("code", ""))
                    return bool(re.search(r"\b(d|edge)\b", code_t))
                return False
            need_sdf = bool(pbr_spec) or (isinstance(light_spec, dict)
                        and str(light_spec.get("profile", "")).lower() in ("machined", "pillow", "engraved"))
            if not need_sdf:
                if _is_fill_stack(fill_spec):
                    need_sdf = any(_needs_sdf(_fill_blend(one)[0]) for one in fill_spec)
                else:
                    need_sdf = _needs_sdf(fill_spec)
            sb = shape.getbbox()
            if need_sdf and sb is not None:
                sx0, sy0, sx1, sy1 = sb
                sdf_arr = np.zeros((h, w), dtype=np.float32)
                sdf_arr[sy0:sy1, sx0:sx1] = fxlib.distance_field(shape.crop(sb), k)

            bump_map: np.ndarray | None = None
            if color_layer is not None:
                fill_img = color_layer
            elif _is_fill_stack(fill_spec):
                fill_img = None
                for one in fill_spec:
                    one, fill_blend = _fill_blend(one)
                    one_img, one_bump = _paint_surface(shape, one, box_px, self.colors, k, sdf=sdf_arr, want_height=want_bump)
                    if one_bump is not None:
                        bump_map = one_bump
                    if one_img is None:
                        continue
                    if fill_img is None:
                        fill_img = one_img
                    elif fill_blend == "normal":
                        fill_img = Image.alpha_composite(fill_img, one_img)
                    else:
                        composite(fill_img, one_img, 0, 0, fill_blend)
            else:
                fill_img, bump_map = _paint_surface(shape, fill_spec, box_px, self.colors, k, sdf=sdf_arr, want_height=want_bump)
            if fill_img is not None and pbr_spec and sb is not None:
                from . import pbr as pbr_mod
                sx0, sy0, sx1, sy1 = sb
                sub_fill = fill_img.crop(sb)
                sub_mask = shape.crop(sb)
                sub_bump = bump_map[sy0:sy1, sx0:sx1] if bump_map is not None else None
                sub_sdf = sdf_arr[sy0:sy1, sx0:sx1] if sdf_arr is not None else None
                shaded = pbr_mod.shade_pbr(sub_fill, sub_mask, self._pbr_spec(pbr_spec), k, bump=sub_bump, sdf=sub_sdf)
                if sx0 > 0 or sy0 > 0 or sx1 < w or sy1 < h:
                    full_pbr = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    full_pbr.paste(shaded, (sx0, sy0))
                    fill_img = full_pbr
                else:
                    fill_img = shaded
            noise = st.get("noise")
            n_scale = float(self._profile().get("noise_scale", 1.0))
            if fill_img is not None and n_scale > 0 and not _is_none(noise) and (isinstance(noise, dict) or float(noise) > 0):
                if n_scale != 1.0:
                    if isinstance(noise, dict):
                        noise = {**noise, "amount": float(noise.get("amount", 0.05)) * n_scale}
                    else:
                        noise = float(noise) * n_scale
                fill_img = fxlib.apply_noise(fill_img, noise, zlib.crc32(el["id"].encode()), k, self.colors)
            if fill_img is not None:
                layer = Image.alpha_composite(layer, fill_img)
            if emoji is not None:
                layer = Image.alpha_composite(layer, emoji)
            if light_spec:
                layer = Image.alpha_composite(layer, fxlib.emboss(shape, light_spec, self.colors, k,
                                                                  bump=bump_map, sdf=sdf_arr))
            layer = _inner_effects(layer, shape, fx, k)

        layer = draw_strokes(layer, drawn)

        if st.get("adjust"):
            layer = fxlib.adjust(layer, st["adjust"], self.colors)
        if soften > 0:
            prog = fxlib.progressive_t((w, h), soften_prog, box_px) if soften_prog else None
            layer = fxlib.blur_image(layer, soften * k / 2, prog)
        persp = st.get("perspective") or el.get("perspective")
        if persp:
            layer = fxlib.perspective_warp(layer, persp)
        if not _is_none(st.get("mask")):
            layer.putalpha(ImageChops.multiply(layer.getchannel("A"),
                                               _soft_mask((w, h), st["mask"], box_px, self.colors, k,
                                                          st.get("mask_mode", "alpha"))))

        clip_id = el.get("clip")
        if clip_id:
            target = self._by_id.get(clip_id)
            if target is None:
                raise ValueError(f"clip target '{clip_id}' does not exist on this canvas")
            if str(el.get("clip_mode", "alpha")).lower() == "luminance":
                cm = self._luminance_mask(target, region)
            else:
                cm = self.shape_mask(target, region)
            layer.putalpha(ImageChops.multiply(layer.getchannel("A"), cm))
        if opacity < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * opacity + 0.5)))
        blend = str(st.get("blend", "normal")).lower()
        if blend not in BLENDS:
            raise ValueError(f"style.blend must be one of {', '.join(BLENDS)}")
        return layer, px0, py0, blend


    def layer_props(self, layer: dict) -> dict:
        """Validated compositing settings of a layer."""
        blend = str(layer.get("blend", "normal")).lower()
        if blend not in BLENDS:
            raise ValueError(f"layer blend must be one of {', '.join(BLENDS)}")
        return {"name": layer["name"], "opacity": max(0.0, min(1.0, float(layer.get("opacity", 1)))), "blend": blend,
                "clip": bool(layer.get("clip", False)), "visible": bool(layer.get("visible", True)),
                "style": self._nums(resolve_style(layer.get("style"), self.theme))}

    def stack(self, only: set[str] | None = None) -> list[tuple[dict | None, list[dict]]]:
        """Layers bottom to top as (layer | None, elements). None is the implicit base layer that holds
        every element not assigned to a layer."""
        layers = self.canvas.get("layers") or []
        names = {layer["name"] for layer in layers}

        def keep(el: dict) -> bool:
            return el.get("visible", True) and (only is None or el["id"] in only)

        out: list[tuple[dict | None, list[dict]]] = []
        base = [e for e in self.canvas["elements"] if e.get("layer") not in names and keep(e)]
        if base:
            out.append((None, base))
        for layer in layers:
            out.append((layer, [e for e in self.canvas["elements"] if e.get("layer") == layer["name"] and keep(e)]))
        return out

    def _draw_elements(self, img: Image.Image, elements: list[dict], margin: int = 0) -> None:
        for el in elements:
            try:
                result = self.render_element(el)
            except ValueError as exc:
                if str(exc).startswith("Element '"):
                    raise
                raise ValueError(f"Element '{el['id']}' ({el['type']}): {exc}") from exc
            if result is None:
                continue
            layer, ox, oy, blend = result
            st_el = self._nums(resolve_style(el.get("style"), self.theme))
            if st_el.get("backdrop_blur") or st_el.get("glass"):
                self._backdrop(img, el, (ox, oy, layer.width, layer.height), margin, st_el)
            composite(img, layer, ox + margin, oy + margin, blend)

    def _backdrop(self, img: Image.Image, el: dict, region, margin: int, st: dict) -> None:
        """Figma "background blur" and "glass": rework what is already drawn beneath the element, inside its shape."""
        ox, oy, w, h = region
        radius, prog = fxlib.blur_amount(st.get("backdrop_blur"))
        r_px = radius * self.k / 2
        glass = st.get("glass")
        reach = r_px * 3 + (float(glass.get("depth", 14)) * self.k * 2 if isinstance(glass, dict) else 30 * self.k)
        pad = int(math.ceil(reach if glass else r_px * 3)) + 1
        x0, y0 = max(0, ox + margin - pad), max(0, oy + margin - pad)
        x1, y1 = min(img.width, ox + margin + w + pad), min(img.height, oy + margin + h + pad)
        if x1 <= x0 or y1 <= y0:
            return
        patch = img.crop((x0, y0, x1, y1))
        mask = Image.new("L", patch.size, 0)
        mask.paste(self.shape_mask(el, region), (ox + margin - x0, oy + margin - y0))
        out = patch
        if r_px > 0:
            box = mask.getbbox() or (0, 0, patch.width, patch.height)
            t = fxlib.progressive_t(patch.size, prog, box) if prog else None
            out = fxlib.blur_image(patch, r_px, t)
        if glass:
            out = fxlib.glass(out, mask, glass, self.k, self.colors)
        img.paste(Image.composite(out, patch, mask), (x0, y0))

    def _luminance_mask(self, target: dict, region) -> Image.Image:
        """Brightness of the rendered target element as a mask (Figma luminance mask)."""
        px0, py0, w, h = region
        out = Image.new("L", (w, h), 0)
        result = self.render_element(target)
        if result is None:
            return out
        layer, ox, oy, _ = result
        lum = ImageChops.multiply(layer.convert("L"), layer.getchannel("A"))
        out.paste(lum, (ox - px0, oy - py0))
        return out

    def _style_layer(self, content: Image.Image, st: dict, box_px: Box) -> Image.Image:
        """Apply layer-level effects to the merged content of a layer, using its alpha as the silhouette."""
        k = self.k
        alpha = content.getchannel("A")
        fx = Effects(st, self.colors)
        strokes = _stroke_specs(st, self.colors)
        a_np = np.asarray(alpha)
        bands = []
        for spec in strokes:
            outer = fxlib.grow(a_np, spec["d1"] * k)
            inner = fxlib.grow(a_np, spec["d0"] * k)
            bands.append(Image.fromarray(np.clip(outer.astype(np.int16) - inner, 0, 255).astype(np.uint8), "L"))
        sil = alpha
        for m in bands:
            sil = ImageChops.lighter(sil, m)
        out = _outer_effects(Image.new("RGBA", content.size, (0, 0, 0, 0)), sil, fx, k)
        body = fxlib.adjust(content, st["adjust"], self.colors) if st.get("adjust") else content
        if st.get("pbr"):
            from . import pbr as pbr_mod
            lb = alpha.getbbox()
            if lb is not None:
                sub = pbr_mod.shade_pbr(body.crop(lb), alpha.crop(lb), self._pbr_spec(st["pbr"]), k)
                full_b = Image.new("RGBA", body.size, (0, 0, 0, 0))
                full_b.paste(sub, (lb[0], lb[1]))
                body = full_b
        out = Image.alpha_composite(out, body)
        if st.get("light"):
            out = Image.alpha_composite(out, fxlib.emboss(alpha, st["light"], self.colors, k))
        out = _inner_effects(out, alpha, fx, k)
        for spec, m in zip(strokes, bands):
            img = paint(m, spec["paint"], box_px, self.colors, k)
            if img is not None:
                out = Image.alpha_composite(out, img)
        soften, soften_prog = fxlib.blur_amount(st.get("blur"))
        if soften > 0:
            prog = fxlib.progressive_t(out.size, soften_prog, box_px) if soften_prog else None
            out = fxlib.blur_image(out, soften * k / 2, prog)
        if st.get("perspective"):
            lb = out.getchannel("A").getbbox()
            if lb is not None:
                pad_p = max(16, int(round(max(lb[2] - lb[0], lb[3] - lb[1]) * 0.18)))
                x0 = max(0, lb[0] - pad_p)
                y0 = max(0, lb[1] - pad_p)
                x1 = min(out.width, lb[2] + pad_p)
                y1 = min(out.height, lb[3] + pad_p)
                warped = fxlib.perspective_warp(out.crop((x0, y0, x1, y1)), st["perspective"])
                full_w = Image.new("RGBA", out.size, (0, 0, 0, 0))
                full_w.paste(warped, (x0, y0))
                out = full_w
        if not _is_none(st.get("mask")):
            out.putalpha(ImageChops.multiply(out.getchannel("A"), _soft_mask(out.size, st["mask"], box_px, self.colors, k,
                                                                             st.get("mask_mode", "alpha"))))
        return out

    def render_pbr_maps(self, normal_format: str = "opengl", include_background: bool = False) -> dict[str, Image.Image]:
        """Bake full-canvas engine-ready PBR texture maps (beauty, albedo, normal, roughness, metallic, ao, height, orm, emissive)."""
        from . import pbr as pbr_mod
        beauty = self.render(include_background=include_background)
        W, H = beauty.size
        albedo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        normal = Image.new("RGBA", (W, H), (128, 128, 255, 255))
        roughness = Image.new("RGBA", (W, H), (128, 128, 128, 255))
        metallic = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        ao = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        height = Image.new("RGBA", (W, H), (128, 128, 128, 255))
        orm = Image.new("RGBA", (W, H), (255, 128, 0, 255))
        emissive = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        if include_background and not _is_none(self.canvas.get("background")):
            bg = paint(Image.new("L", (W, H), 255), self._nums(self.canvas["background"]), (0, 0, W, H), self.colors, self.k)
            if bg is not None:
                albedo = Image.alpha_composite(albedo, bg)

        def _paste_over(dst: Image.Image, src: Image.Image, px0: int, py0: int) -> None:
            sx0, sy0 = max(0, -px0), max(0, -py0)
            dx0, dy0 = max(0, px0), max(0, py0)
            cw = min(src.width - sx0, W - dx0)
            ch = min(src.height - sy0, H - dy0)
            if cw <= 0 or ch <= 0:
                return
            crop = src.crop((sx0, sy0, sx0 + cw, sy0 + ch))
            dst.alpha_composite(crop, (dx0, dy0))

        for layer_cfg, els in self.stack():
            if layer_cfg and not layer_cfg.get("visible", True):
                continue
            for el in els:
                if not el.get("visible", True):
                    continue
                st = self._nums(resolve_style(el.get("style"), self.theme))
                pbr_spec = st.get("pbr")
                if not pbr_spec and st.get("light"):
                    lt = st["light"] if isinstance(st["light"], dict) else {}
                    pbr_spec = {"metallic": 0.0, "roughness": max(0.08, 1.0 - float(lt.get("gloss", 0.45)) * 0.7),
                                "bevel_size": float(lt.get("size", 6.0)), "bevel_depth": float(lt.get("depth", 1.0)),
                                "profile": str(lt.get("profile", "round"))}
                if pbr_spec and el["type"] in VECTOR_TYPES:
                    try:
                        plain = dict(el)
                        plain_st = dict(st)
                        plain_st.pop("pbr", None)
                        plain_st.pop("light", None)
                        plain_st.pop("shadow", None)
                        plain_st.pop("glow", None)
                        plain["style"] = plain_st
                        res = self.render_element(plain)
                    except Exception:
                        res = None
                    if res is not None:
                        unlit, px0, py0, _ = res
                        mask = unlit.getchannel("A")
                        sb = mask.getbbox()
                        if sb is not None:
                            sub_fill = unlit.crop(sb)
                            sub_mask = mask.crop(sb)
                            sdf_sub = fxlib.distance_field(sub_mask, self.k)
                            bump_sub = None
                            fspec = plain_st.get("fill")
                            if isinstance(fspec, dict) and str(fspec.get("type", "")).lower() == "shader":
                                _, bump_sub = _paint_surface(sub_mask, fspec, (0, 0, sub_mask.width, sub_mask.height),
                                                             self.colors, self.k, sdf=sdf_sub, want_height=True)
                            maps = pbr_mod.bake_pbr_maps(sub_fill, sub_mask, self._pbr_spec(pbr_spec), self.k,
                                                         bump=bump_sub, sdf=sdf_sub, normal_format=normal_format)
                            ox, oy = px0 + sb[0], py0 + sb[1]
                            _paste_over(albedo, maps["albedo"], ox, oy)
                            _paste_over(normal, maps["normal"], ox, oy)
                            _paste_over(roughness, maps["roughness"], ox, oy)
                            _paste_over(metallic, maps["metallic"], ox, oy)
                            _paste_over(ao, maps["ao"], ox, oy)
                            _paste_over(height, maps["height"], ox, oy)
                            _paste_over(orm, maps["orm"], ox, oy)
                            _paste_over(emissive, maps["emissive"], ox, oy)
                            continue
                res = self.render_element(el)
                if res is None:
                    continue
                img_el, px0, py0, _ = res
                _paste_over(albedo, img_el, px0, py0)
                a_ch = img_el.getchannel("A")
                flat_n = Image.merge("RGBA", (Image.new("L", img_el.size, 128), Image.new("L", img_el.size, 128),
                                              Image.new("L", img_el.size, 255), a_ch))
                _paste_over(normal, flat_n, px0, py0)
                if st.get("glow") or (isinstance(el.get("style"), dict) and el["style"].get("material") in ("neon", "hologram", "energy_shield")):
                    _paste_over(emissive, img_el, px0, py0)

        return {"beauty": beauty, "albedo": albedo, "normal": normal.convert("RGB"),
                "roughness": roughness.convert("L"), "metallic": metallic.convert("L"),
                "ao": ao.convert("L"), "height": height.convert("L"),
                "orm": orm.convert("RGB"), "emissive": emissive.convert("RGB")}

    def layer_image(self, layer: dict | None, elements: list[dict], clip_alpha: Image.Image | None = None,
                    bake_opacity: bool = True) -> tuple[Image.Image, Image.Image]:
        """Render one layer on its own. Returns (finished layer, alpha of its raw content); the second
        is what a layer above clips to."""
        props = self.layer_props(layer) if layer else {"opacity": 1.0, "style": {}}
        st = props["style"]
        margin = 0
        if st:
            fx = Effects(st, self.colors)
            reach = max(0.0, max((sp["d1"] for sp in _stroke_specs(st, self.colors)), default=0.0))
            b_rad, _ = fxlib.blur_amount(st.get("blur"))
            margin = int(math.ceil((fx.pad() + b_rad * 1.5 + reach + 2) * self.k))
        size = (self.width + 2 * margin, self.height + 2 * margin)
        content = Image.new("RGBA", size, (0, 0, 0, 0))
        self._draw_elements(content, elements, margin)
        frame = (margin, margin, margin + self.width, margin + self.height)
        content_alpha = content.getchannel("A").crop(frame)
        if st:
            bb = content.getchannel("A").getbbox()
            if bb is None:
                final = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            else:
                pad = max(margin, 4)
                x0, y0 = max(0, bb[0] - pad), max(0, bb[1] - pad)
                x1, y1 = min(size[0], bb[2] + pad), min(size[1], bb[3] + pad)
                if (x1 - x0) * (y1 - y0) < size[0] * size[1] * 0.75:
                    sub = content.crop((x0, y0, x1, y1))
                    sub_frame = (float(margin - x0), float(margin - y0),
                                 float(margin + self.width - x0), float(margin + self.height - y0))
                    styled = self._style_layer(sub, st, sub_frame)
                    full = Image.new("RGBA", size, (0, 0, 0, 0))
                    full.paste(styled, (x0, y0))
                    final = full.crop(frame)
                else:
                    final = self._style_layer(content, st, tuple(float(v) for v in frame)).crop(frame)
        else:
            final = content.crop(frame)
        if clip_alpha is not None:
            final.putalpha(ImageChops.multiply(final.getchannel("A"), clip_alpha))
        if bake_opacity and props["opacity"] < 1:
            opacity = props["opacity"]
            final.putalpha(final.getchannel("A").point(lambda v: int(v * opacity + 0.5)))
        return final, content_alpha

    def render_stack(self, img: Image.Image, only: set[str] | None = None,
                     only_layers: set[str] | None = None) -> Image.Image:
        """Composite every layer onto ``img`` (bottom to top)."""
        items = self.stack(only)
        base_alpha: Image.Image | None = None
        base_visible = True
        for index, (layer, elements) in enumerate(items):
            name = layer["name"] if layer else "base"
            props = self.layer_props(layer) if layer else {"opacity": 1.0, "blend": "normal", "clip": False,
                                                            "visible": True, "style": {}}
            shown = only_layers is None or name in only_layers
            nxt = items[index + 1][0] if index + 1 < len(items) else None
            clipped_onto = bool(nxt and nxt.get("clip"))
            if not props["visible"]:
                if not props["clip"]:
                    base_alpha, base_visible = None, False
                continue
            erases = any(str(resolve_style(e.get("style"), self.theme).get("blend", "")).lower() == "erase"
                         for e in elements)
            plain = (not props["style"] and props["opacity"] >= 1 and props["blend"] == "normal"
                     and not props["clip"] and not erases)
            if plain and not clipped_onto:
                if shown:
                    self._draw_elements(img, elements)
                base_alpha, base_visible = None, True
                continue
            clip_alpha = base_alpha if props["clip"] else None
            if props["clip"] and (base_alpha is None or not base_visible):
                if not base_visible:
                    continue
                clip_alpha = None
            final, content_alpha = self.layer_image(layer, elements, clip_alpha)
            if not props["clip"]:
                base_alpha, base_visible = content_alpha, True
            if shown:
                composite(img, final, 0, 0, props["blend"])
        return img


_PLACEHOLDER = re.compile(r"\{([A-Za-z_][\w.\-]*)\}")
_PSEUDO = str.maketrans("aeiouycnsAEIOUYCNS", "áéîöüýçñšÅÉÎÖÛÝÇÑŠ")


PSEUDO_LANGS = ("pseudo", "pseudo-long", "pseudo-rtl")


def pseudo_localize(text: str, mode: str = "pseudo") -> str:
    """Pseudo-localisation for clipping and missing glyphs: "pseudo" is accented and ~35% longer
    (typical translation growth), "pseudo-long" ~100% longer (short labels in German / Finnish /
    Russian), "pseudo-rtl" is "pseudo" forced right-to-left, like Godot's fake BiDi."""
    if not text.strip():
        return text
    grow = 1.0 if mode == "pseudo-long" else 0.35
    out = []
    for line in text.split("\n"):
        body = line.translate(_PSEUDO)
        pad = "·" * max(1, int(round(len(line) * grow)))
        item = f"[{body} {pad}]"
        out.append(f"‮{item}‬" if mode == "pseudo-rtl" else item)
    return "\n".join(out)


def text_vars(canvas: dict, language: str | None, strings: dict, extra: dict | None = None) -> dict:
    """Placeholder values: default-language strings < chosen language < canvas vars < instance vars."""
    tables = strings.get("tables", {}) if strings else {}
    default = strings.get("default") if strings else None
    out: dict = {}
    if default and default in tables:
        out.update(tables[default])
    lang = language or canvas.get("language")
    if lang and lang in tables:
        out.update(tables[lang])
    out.update(canvas.get("vars") or {})
    out.update(extra or {})
    return out


def _component_overrides(src: dict, el: dict, lookup) -> dict:
    """Per-instance component properties: variant {prop: value} (states named "prop=value"),
    hide / show [ids] (boolean properties) and slots {placeholder_id: canvas_id} (Figma slots / instance swap)."""
    variant, hide, show, slots = el.get("variant"), el.get("hide"), el.get("show"), el.get("slots")
    if not (variant or hide or show or slots):
        return src
    import copy as _copy
    if variant:
        if not isinstance(variant, dict):
            raise ValueError('variant must be like {"size": "large", "state": "hover"}')
        for prop, value in variant.items():
            name = re.sub(r"[^\w-]+", "_", f"{prop}={value}".strip().replace("İ", "i")).strip("_").lower()
            src = apply_state(src, name)
    else:
        src = _copy.deepcopy(src)
    by_id = {e["id"]: e for e in src["elements"]}
    for ids, flag in ((hide, False), (show, True)):
        for eid in ids or []:
            if eid not in by_id:
                raise ValueError(f"component '{src.get('id')}' has no element '{eid}' to hide / show")
            by_id[eid]["visible"] = flag
    for slot_id, canvas_id in (slots or {}).items():
        if slot_id not in by_id:
            raise ValueError(f"component '{src.get('id')}' has no slot element '{slot_id}'")
        holder = by_id[slot_id]
        x, y = float(holder.get("x", holder.get("cx", 0))), float(holder.get("y", holder.get("cy", 0)))
        w = float(holder.get("width") or 2 * float(holder.get("rx", 0)) or 0)
        h = float(holder.get("height") or 2 * float(holder.get("ry", holder.get("rx", 0))) or 0)
        if holder["type"] == "ellipse":
            x, y = x - w / 2, y - h / 2
        if w <= 0 or h <= 0:
            raise ValueError(f"slot '{slot_id}' needs a size (use a rect or ellipse as the placeholder)")
        swapped = {"id": slot_id, "type": "instance", "source": str(canvas_id), "x": x, "y": y, "width": w,
                   "height": h, "fit": holder.get("fit", "contain"), "background": False}
        for keep in ("layer", "group", "rotation", "origin", "clip"):
            if keep in holder:
                swapped[keep] = holder[keep]
        src["elements"][src["elements"].index(holder)] = swapped
    return src


def apply_state(canvas: dict, state: str) -> dict:
    """A copy of ``canvas`` with the overrides of one interaction state (hover, pressed...) applied."""
    import copy as _copy
    states = canvas.get("states") or {}
    if state not in states:
        known = ", ".join(sorted(states)) or "(none)"
        raise ValueError(f"canvas '{canvas.get('id')}' has no state '{state}'. States: {known}")
    out = _copy.deepcopy(canvas)
    by_id = {e["id"]: e for e in out["elements"]}
    for eid, props in states[state].items():
        el = by_id.get(eid)
        if el is None:
            continue
        for key, value in props.items():
            if key == "style" and isinstance(value, dict):
                base = el.get("style")
                merged = dict(base) if isinstance(base, dict) else ({"use": base} if base else {})
                for sk, sv in value.items():
                    if sv is None:
                        merged.pop(sk, None)
                    else:
                        merged[sk] = sv
                el["style"] = merged
            elif value is None:
                el.pop(key, None)
            else:
                el[key] = value
    return out


def pixelate(img: Image.Image, spec: dict, colors: dict) -> Image.Image:
    """Binary alpha + limited palette for pixel-art canvases."""
    arr = np.asarray(img, dtype=np.uint8).copy()
    thr = int(spec.get("alpha_threshold", 128))
    opaque = arr[..., 3] >= thr
    arr[..., 3] = np.where(opaque, 255, 0)
    palette = spec.get("palette")
    if palette:
        pal = np.array([parse_color(c, colors)[:3] for c in palette], dtype=np.float64)
        rgb = arr[..., :3].reshape(-1, 3).astype(np.float64)
        idx = np.argmin(((rgb[:, None, :] - pal[None, :, :]) ** 2).sum(-1), axis=1)
        arr[..., :3] = pal[idx].reshape(arr.shape[:2] + (3,)).astype(np.uint8)
    elif spec.get("max_colors"):
        n = max(2, min(256, int(spec["max_colors"])))
        q = Image.fromarray(arr[..., :3], "RGB").quantize(colors=n, method=Image.Quantize.MAXCOVERAGE,
                                                          dither=Image.Dither.NONE).convert("RGB")
        arr[..., :3] = np.asarray(q)
    arr[~opaque] = 0
    return Image.fromarray(arr, "RGBA")


def _instance_cycle(src: dict, target: Any, lookup, seen: tuple = ()) -> list[str] | None:
    """Path of canvas ids from ``src`` back to ``target`` through instance elements, if any."""
    sid = src.get("id")
    if sid == target:
        return [str(sid)]
    if sid in seen or len(seen) > 32:
        return None
    for el in src.get("elements", []):
        if el.get("type") == "instance" and el.get("source"):
            try:
                child = lookup(str(el["source"]))
            except ValueError:
                continue
            path = _instance_cycle(child, target, lookup, seen + (sid,))
            if path:
                return [str(sid)] + path
    return None


def _scales(el: dict) -> tuple[float, float]:
    """Signed scale of an element: scale / scale_x / scale_y, with flip_x / flip_y mirroring.
    A path's own "scale" sizes its path data, so only scale_x / scale_y transform a path."""
    uniform = 1 if el.get("type") == "path" else el.get("scale", 1)
    sx = el.get("scale_x", uniform)
    sy = el.get("scale_y", uniform)
    sx = float(sx) if sx is not None else 1.0
    sy = float(sy) if sy is not None else 1.0
    if el.get("flip_x"):
        sx = -sx
    if el.get("flip_y"):
        sy = -sy
    return sx, sy


def _mirror_style(st: dict, fx: bool, fy: bool) -> dict:
    """Pre-mirror a style so that, after the rendered element is flipped, shadows, glows, bevels and
    surface light still fall the way the rest of the UI is lit."""
    st = dict(st)

    for key, default_dy in (("shadow", 4.0), ("inner_shadow", 2.0)):
        if key in st and not _is_none(st[key]):
            items = []
            for spec in _as_list(st[key]):
                if spec is True:
                    spec = {}
                elif isinstance(spec, (str, list, tuple)):
                    spec = {"color": spec}
                if isinstance(spec, dict):
                    spec = dict(spec)
                    if fx:
                        spec["dx"] = -float(spec.get("dx", 0) or 0)
                    if fy:
                        spec["dy"] = -float(spec.get("dy", default_dy))
                items.append(spec)
            st[key] = items
    if fy and st.get("bevel"):
        bevel = dict(st["bevel"]) if isinstance(st["bevel"], dict) else {}
        bevel["highlight"], bevel["shadow"] = bevel.get("shadow", "#000000@0.35"), bevel.get("highlight", "#ffffff@0.35")
        st["bevel"] = bevel
    for lkey in ("light", "pbr"):
        if st.get(lkey):
            light = dict(st[lkey]) if isinstance(st[lkey], dict) else {}
            a = float(light.get("angle", 225))
            if fx:
                a = 180.0 - a
            if fy:
                a = -a
            light["angle"] = a
            st[lkey] = light
    st.pop("use", None)
    return st


def _is_fill_stack(spec: Any) -> bool:
    """A list of fills (not an [r, g, b(, a)] colour list)."""
    return isinstance(spec, list) and bool(spec) and not all(isinstance(v, (int, float)) for v in spec)


def shift_element(el: dict, dx: float, dy: float) -> None:
    """Move an element (and its rotation pivot) by (dx, dy) in place."""
    if el.get("type") == "boolean":
        for child in el.get("children") or []:
            shift_element(child, dx, dy)
    elif "points" in el and el["type"] in ("polygon", "line"):
        el["points"] = [[float(p[0]) + dx, float(p[1]) + dy] for p in el["points"]]
    elif "cx" in el:
        el["cx"], el["cy"] = float(el["cx"]) + dx, float(el["cy"]) + dy
    else:
        el["x"], el["y"] = float(el.get("x", 0)) + dx, float(el.get("y", 0)) + dy
    if el.get("origin"):
        el["origin"] = [float(el["origin"][0]) + dx, float(el["origin"][1]) + dy]
    if isinstance(el.get("arc"), dict) and "cx" in el["arc"]:
        el["arc"] = dict(el["arc"], cx=float(el["arc"]["cx"]) + dx, cy=float(el["arc"]["cy"]) + dy)



def checkerboard(size: tuple[int, int], cell: int = 12, dark: bool = True) -> Image.Image:
    w, h = size
    a, b = ((38, 38, 44), (52, 52, 60)) if dark else ((235, 235, 238), (255, 255, 255))
    pick = (((np.arange(w, dtype=np.int32)[None, :] // cell) + (np.arange(h, dtype=np.int32)[:, None] // cell)) & 1).astype(bool)
    arr = np.empty((h, w, 4), dtype=np.uint8)
    arr[..., 3] = 255
    for c in range(3):
        arr[..., c] = np.where(pick, a[c], b[c])
    return Image.fromarray(arr, "RGBA")


def backdrop(size: tuple[int, int], background: str, colors: dict) -> Image.Image:
    key = (background or "checker").lower()
    if key in ("checker", "checker-dark"):
        return checkerboard(size, dark=True)
    if key == "checker-light":
        return checkerboard(size, dark=False)
    if key == "dark":
        return Image.new("RGBA", size, (24, 24, 30, 255))
    if key == "light":
        return Image.new("RGBA", size, (240, 240, 244, 255))
    if key == "game":
        w, h = size
        xs = np.arange(w, dtype=np.float32)[None, :]
        ys = np.arange(h, dtype=np.float32)[:, None]
        arr = np.empty((h, w, 4), dtype=np.uint8)
        t = ys / np.float32(max(1, h - 1))
        wave = np.float32(12.0) * np.sin(xs / np.float32(37.0)) * np.cos(ys / np.float32(23.0))
        arr[..., 0] = np.clip(np.float32(70.0) + np.float32(60.0) * t + wave, 0, 255).astype(np.uint8)
        arr[..., 1] = np.clip(np.float32(110.0) + np.float32(30.0) * (np.float32(1.0) - t) + wave, 0, 255).astype(np.uint8)
        arr[..., 2] = np.clip(np.float32(150.0) - np.float32(70.0) * t + wave, 0, 255).astype(np.uint8)
        arr[..., 3] = 255
        return Image.fromarray(arr, "RGBA")
    r, g, b, _ = parse_color(background, colors)
    return Image.new("RGBA", size, (r, g, b, 255))
