"""Turn a raster image into flat vector shapes (Figma "vectorize"): quantise the colours, trace each colour
region's pixel boundary into polygons (holes included), then simplify them into smooth editable paths."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from PIL import Image


def _loops(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """Closed boundary loops (pixel-corner coordinates) of a boolean mask, holes included.
    Edges are directed so the filled side is always on the right, so loops chain without ambiguity."""
    h, w = mask.shape
    m = np.pad(mask, 1)
    nxt: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    up, down = m[:-1, 1:-1], m[1:, 1:-1]
    for y, x in zip(*np.nonzero(down & ~up)):
        nxt[(x, y)].append((x + 1, y))
    for y, x in zip(*np.nonzero(up & ~down)):
        nxt[(x + 1, y)].append((x, y))
    left, right = m[1:-1, :-1], m[1:-1, 1:]
    for y, x in zip(*np.nonzero(right & ~left)):
        nxt[(x, y + 1)].append((x, y))
    for y, x in zip(*np.nonzero(left & ~right)):
        nxt[(x, y)].append((x, y + 1))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop = [start]
        cur = start
        while True:
            options = nxt.get(cur)
            if not options:
                break
            step = options.pop()
            if not options:
                del nxt[cur]
            if step == start:
                break
            loop.append(step)
            cur = step
        if len(loop) >= 4:
            loops.append(loop)
    return loops


def _rdp(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    if len(pts) < 4:
        return pts

    def rec(seg):
        (ax, ay), (bx, by) = seg[0], seg[-1]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy) or 1e-12
        best, idx = -1.0, 0
        for i in range(1, len(seg) - 1):
            d = abs(dy * seg[i][0] - dx * seg[i][1] + bx * ay - by * ax) / n
            if d > best:
                best, idx = d, i
        if best <= tol:
            return [seg[0], seg[-1]]
        return rec(seg[:idx + 1])[:-1] + rec(seg[idx:])

    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    return rec(pts[:far + 1])[:-1] + rec(pts[far:] + [pts[0]])[:-1]


def _round_corners(pts: list[tuple[float, float]], radius: float, rounds: int) -> list[tuple[float, float]]:
    """Chaikin-style corner cutting with a fixed reach, so long straight edges stay straight."""
    for _ in range(rounds):
        out = []
        n = len(pts)
        for i in range(n):
            (px, py), (cx, cy), (nx, ny) = pts[i - 1], pts[i], pts[(i + 1) % n]
            la, lb = math.hypot(px - cx, py - cy), math.hypot(nx - cx, ny - cy)
            if la < 1e-9 or lb < 1e-9:
                continue
            da, db = min(la * 0.25, radius), min(lb * 0.25, radius)
            out += [(cx + (px - cx) * da / la, cy + (py - cy) * da / la), (cx + (nx - cx) * db / lb, cy + (ny - cy) * db / lb)]
        pts = out
    return pts


def _grow(polys: list[list[tuple[float, float]]], d: float) -> list[list[tuple[float, float]]]:
    """Grow a region a little so neighbouring colours overlap instead of leaving hairline gaps."""
    import pyclipper
    q = 256.0
    ints = [[(round(x * q), round(y * q)) for x, y in p] for p in polys if len(p) >= 3]
    clean = pyclipper.SimplifyPolygons(ints, pyclipper.PFT_EVENODD)
    po = pyclipper.PyclipperOffset(arc_tolerance=0.05 * q)
    po.AddPaths(clean, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    return [[(x / q, y / q) for x, y in p] for p in po.Execute(d * q)]


def trace(img: Image.Image, colors: int = 6, detail: float = 1.0, smooth: int = 1,
          min_area: float = 4.0) -> list[tuple[tuple[int, int, int, int], list[list[tuple[float, float]]], int]]:
    """[(rgba, polygons in image pixels, pixel count)] from the largest colour region to the smallest."""
    rgba = img.convert("RGBA")
    longest = max(rgba.size)
    target = max(32, min(512, int(256 * detail)))
    if longest > target:
        scale = target / longest
        rgba = rgba.resize((max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))), Image.LANCZOS)
    else:
        scale = 1.0
    alpha = np.asarray(rgba.getchannel("A")) > 127
    flat = Image.new("RGB", rgba.size, (0, 0, 0))
    flat.paste(rgba, mask=rgba.getchannel("A"))
    q = flat.quantize(colors=max(2, min(32, int(colors))), method=Image.Quantize.MEDIANCUT, kmeans=3,
                      dither=Image.Dither.NONE)
    idx = np.asarray(q)
    pal = q.getpalette()[: 3 * 256]
    out = []
    for c in np.unique(idx[alpha]) if alpha.any() else []:
        mask = (idx == c) & alpha
        count = int(mask.sum())
        if count < min_area:
            continue
        polys = []
        for loop in _loops(mask):
            pts = [(x / scale, y / scale) for x, y in loop]
            pts = _rdp(pts, 0.75 / scale)
            if smooth:
                pts = _round_corners(pts, 1.2 / scale, smooth)
            if len(pts) >= 3:
                polys.append(pts)
        polys = _grow(polys, 0.5 / scale)
        if polys:
            out.append(((pal[3 * c], pal[3 * c + 1], pal[3 * c + 2], 255), polys, count))
    out.sort(key=lambda item: -item[2])
    return out
