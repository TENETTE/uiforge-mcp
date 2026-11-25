"""Vector geometry: shape builders, SVG path parsing and curve flattening.

Everything is flattened to polylines. A subpath is ``(points, closed)`` where
points is a list of ``(x, y)`` floats in canvas units.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Sequence

Point = tuple[float, float]
Subpath = tuple[list[Point], bool]


def _arc_points(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, res: float) -> list[Point]:
    """Points along an ellipse arc from angle a0 to a1 (radians), endpoints included."""
    length = abs(a1 - a0) * max(rx, ry) * res
    n = max(2, min(160, int(math.ceil(length / 2.5))))
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def normalize_radii(radius, w: float, h: float) -> list[float]:
    """Return [tl, tr, br, bl] corner radii clamped so they fit the box."""
    if radius is None:
        radii = [0.0] * 4
    elif isinstance(radius, (int, float)):
        radii = [float(radius)] * 4
    else:
        vals = [float(v) for v in radius]
        if len(vals) == 1:
            radii = vals * 4
        elif len(vals) == 2:
            radii = [vals[0], vals[1], vals[0], vals[1]]
        elif len(vals) == 4:
            radii = vals
        else:
            raise ValueError("radius must be a number or a list of 1, 2 or 4 numbers [tl, tr, br, bl]")
    radii = [max(0.0, r) for r in radii]
    limit = min(w, h) / 2.0
    return [min(r, limit) for r in radii]


def rect_path(x: float, y: float, w: float, h: float, radius=0, corner: str = "round", res: float = 4.0,
              smoothing: float = 0.0) -> list[Point]:
    """Rectangle outline. corner='round' gives arcs, corner='cut' gives chamfered corners.
    smoothing 0..1 (round corners): continuous-curvature "squircle" corners like Figma's corner smoothing
    (0.6 = iOS look) - the curve starts further along each edge and eases into it instead of a circle."""
    tl, tr, br, bl = normalize_radii(radius, w, h)
    s = max(0.0, min(1.0, float(smoothing or 0)))
    pts: list[Point] = []
    if corner == "cut":
        for (px, py, r, dx0, dy0, dx1, dy1) in (
            (x, y, tl, 0, 1, 1, 0),
            (x + w, y, tr, -1, 0, 0, 1),
            (x + w, y + h, br, 0, -1, -1, 0),
            (x, y + h, bl, 1, 0, 0, -1),
        ):
            if r > 0:
                pts.append((px + dx0 * r, py + dy0 * r))
                pts.append((px + dx1 * r, py + dy1 * r))
            else:
                pts.append((px, py))
        return pts
    corners = (
        (x + tl, y + tl, tl, math.pi, 1.5 * math.pi, (x, y)),
        (x + w - tr, y + tr, tr, 1.5 * math.pi, 2 * math.pi, (x + w, y)),
        (x + w - br, y + h - br, br, 0.0, 0.5 * math.pi, (x + w, y + h)),
        (x + bl, y + h - bl, bl, 0.5 * math.pi, math.pi, (x, y + h)),
    )
    for cx, cy, r, a0, a1, sharp in corners:
        if r > 0 and s > 0:
            e = min(r * (1 + s), min(w, h) / 2.0)
            n = 2.0 + 2.0 * s
            ccx = sharp[0] + math.copysign(e, cx - sharp[0])
            ccy = sharp[1] + math.copysign(e, cy - sharp[1])
            for px_, py_ in _arc_points(0, 0, 1, 1, a0, a1, res * e):
                pts.append((ccx + e * math.copysign(abs(px_) ** (2 / n), px_),
                            ccy + e * math.copysign(abs(py_) ** (2 / n), py_)))
        elif r > 0:
            pts.extend(_arc_points(cx, cy, r, r, a0, a1, res))
        else:
            pts.append(sharp)
    return pts


def ellipse_path(cx: float, cy: float, rx: float, ry: float, res: float = 4.0) -> list[Point]:
    pts = _arc_points(cx, cy, rx, ry, 0.0, 2 * math.pi, res)
    return pts[:-1]


def regular_polygon(cx: float, cy: float, radius: float, sides: int, inner_radius: float | None = None,
                    rotation: float = 0.0) -> list[Point]:
    """Regular polygon, or a star when inner_radius is given. First vertex points up."""
    if sides < 3:
        raise ValueError("sides must be >= 3")
    pts: list[Point] = []
    base = math.radians(rotation) - math.pi / 2
    count = sides * 2 if inner_radius else sides
    for i in range(count):
        r = radius if (not inner_radius or i % 2 == 0) else inner_radius
        a = base + 2 * math.pi * i / count
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def round_corners(points: Sequence[Point], radius: float, res: float = 4.0) -> list[Point]:
    """Round the corners of a closed polygon with quadratic curves."""
    n = len(points)
    if radius <= 0 or n < 3:
        return list(points)
    out: list[Point] = []
    for i in range(n):
        p0, p1, p2 = points[i - 1], points[i], points[(i + 1) % n]
        v0 = (p0[0] - p1[0], p0[1] - p1[1])
        v1 = (p2[0] - p1[0], p2[1] - p1[1])
        l0, l1 = math.hypot(*v0), math.hypot(*v1)
        if l0 < 1e-6 or l1 < 1e-6:
            out.append(p1)
            continue
        d = min(radius, l0 / 2, l1 / 2)
        a = (p1[0] + v0[0] / l0 * d, p1[1] + v0[1] / l0 * d)
        b = (p1[0] + v1[0] / l1 * d, p1[1] + v1[1] / l1 * d)
        steps = max(3, min(24, int(d * res / 2)))
        for s in range(steps + 1):
            t = s / steps
            mt = 1 - t
            out.append((mt * mt * a[0] + 2 * mt * t * p1[0] + t * t * b[0],
                        mt * mt * a[1] + 2 * mt * t * p1[1] + t * t * b[1]))
    return out



_TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point, res: float) -> list[Point]:
    length = (math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)) * res
    n = max(4, min(120, int(math.ceil(length / 3.0))))
    pts = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        a, b, c, d = mt ** 3, 3 * mt * mt * t, 3 * mt * t * t, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _quad(p0: Point, p1: Point, p2: Point, res: float) -> list[Point]:
    c1 = (p0[0] + 2 / 3 * (p1[0] - p0[0]), p0[1] + 2 / 3 * (p1[1] - p0[1]))
    c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]), p2[1] + 2 / 3 * (p1[1] - p2[1]))
    return _cubic(p0, c1, c2, p2, res)


def _svg_arc(p0: Point, rx: float, ry: float, phi_deg: float, large: bool, sweep: bool, p1: Point, res: float) -> list[Point]:
    """SVG endpoint-parameterised arc flattened to points (excluding p0)."""
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-9 or ry < 1e-9:
        return [p1]
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp, cyp = coef * rx * y1 / ry, -coef * ry * x1 / rx
    cx = cp * cxp - sp * cyp + (p0[0] + p1[0]) / 2
    cy = sp * cxp + cp * cyp + (p0[1] + p1[1]) / 2
    a0 = math.atan2((y1 - cyp) / ry, (x1 - cxp) / rx)
    a1 = math.atan2((-y1 - cyp) / ry, (-x1 - cxp) / rx)
    da = a1 - a0
    if sweep and da < 0:
        da += 2 * math.pi
    elif not sweep and da > 0:
        da -= 2 * math.pi
    length = abs(da) * max(rx, ry) * res
    n = max(3, min(160, int(math.ceil(length / 2.5))))
    pts = []
    for i in range(1, n + 1):
        a = a0 + da * i / n
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        pts.append((cp * ex - sp * ey + cx, sp * ex + cp * ey + cy))
    pts[-1] = p1
    return pts


def parse_svg_path(d: str, res: float = 4.0) -> list[Subpath]:
    """Parse SVG path data (M L H V C S Q T A Z, absolute and relative) into flattened subpaths."""
    tokens = _TOKEN.findall(d or "")
    if not tokens:
        raise ValueError("Empty or invalid SVG path data")
    subpaths: list[Subpath] = []
    cur: list[Point] = []
    pos: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    last_ctrl: Point | None = None
    last_cmd = ""
    cmd = ""
    i = 0

    def flush(closed: bool) -> None:
        nonlocal cur
        if len(cur) >= 2:
            subpaths.append((cur, closed))
        cur = []

    def nums(count: int) -> list[float]:
        nonlocal i
        vals = []
        for _ in range(count):
            if i >= len(tokens) or tokens[i][0]:
                raise ValueError(f"SVG path: command '{cmd}' is missing numbers")
            vals.append(float(tokens[i][1]))
            i += 1
        return vals

    while i < len(tokens):
        if tokens[i][0]:
            cmd = tokens[i][0]
            i += 1
        elif not cmd:
            raise ValueError("SVG path must start with a command (M)")
        elif cmd in "Mm":
            cmd = "L" if cmd == "M" else "l"
        up = cmd.upper()
        rel = cmd.islower()
        if up == "Z":
            flush(True)
            pos = start
            last_ctrl = None
            last_cmd = up
            cmd = ""
            continue
        a = nums(_ARGS[up])
        ox, oy = (pos if rel else (0.0, 0.0))
        if up == "M":
            flush(False)
            pos = (a[0] + ox, a[1] + oy)
            start = pos
            cur = [pos]
        elif up == "L":
            pos = (a[0] + ox, a[1] + oy)
            cur.append(pos)
        elif up == "H":
            pos = (a[0] + ox, pos[1])
            cur.append(pos)
        elif up == "V":
            pos = (pos[0], a[0] + oy)
            cur.append(pos)
        elif up == "C":
            c1, c2, end = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy), (a[4] + ox, a[5] + oy)
            cur.extend(_cubic(pos, c1, c2, end, res))
            last_ctrl, pos = c2, end
        elif up == "S":
            c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_ctrl and last_cmd in "CS" else pos
            c2, end = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            cur.extend(_cubic(pos, c1, c2, end, res))
            last_ctrl, pos = c2, end
        elif up == "Q":
            c1, end = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            cur.extend(_quad(pos, c1, end, res))
            last_ctrl, pos = c1, end
        elif up == "T":
            c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_ctrl and last_cmd in "QT" else pos
            end = (a[0] + ox, a[1] + oy)
            cur.extend(_quad(pos, c1, end, res))
            last_ctrl, pos = c1, end
        elif up == "A":
            end = (a[5] + ox, a[6] + oy)
            cur.extend(_svg_arc(pos, a[0], a[1], a[2], bool(a[3]), bool(a[4]), end, res))
            pos = end
        if up not in "CSQT":
            last_ctrl = None
        last_cmd = up
    flush(False)
    if not subpaths:
        raise ValueError("SVG path produced no drawable segments")
    return subpaths



def transform(points: Iterable[Point], scale: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> list[Point]:
    return [(x * scale + dx, y * scale + dy) for x, y in points]


def bbox_of(point_lists: Iterable[Iterable[Point]]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for pts in point_lists:
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def arc_path(cx: float, cy: float, radius: float, start_deg: float, end_deg: float, res: float = 4.0) -> list[Point]:
    """Points along a circular arc. Angles in degrees, 0 = 3 o'clock, clockwise (y points down)."""
    return _arc_points(cx, cy, radius, radius, math.radians(start_deg), math.radians(end_deg), res)


def dash_polyline(points: Sequence[Point], closed: bool, dash: Sequence[float], offset: float = 0.0) -> list[list[Point]]:
    """Cut a polyline into dashes. ``dash`` is [on, off, on, off, ...] lengths."""
    pattern = [max(0.01, float(v)) for v in dash]
    if len(pattern) % 2:
        pattern = pattern * 2
    pts = list(points) + ([points[0]] if closed and len(points) > 2 else [])
    total = sum(pattern)
    pos = offset % total
    idx = 0
    while pos >= pattern[idx]:
        pos -= pattern[idx]
        idx = (idx + 1) % len(pattern)
    remaining = pattern[idx] - pos
    drawing = idx % 2 == 0
    out: list[list[Point]] = []
    cur: list[Point] = [pts[0]] if drawing else []
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if seg < 1e-9:
            continue
        travelled = 0.0
        while seg - travelled > remaining + 1e-9:
            travelled += remaining
            t = travelled / seg
            cut = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if drawing:
                cur.append(cut)
                if len(cur) >= 2:
                    out.append(cur)
                cur = []
            else:
                cur = [cut]
            idx = (idx + 1) % len(pattern)
            remaining = pattern[idx]
            drawing = idx % 2 == 0
        remaining -= seg - travelled
        if drawing:
            cur.append(b)
    if drawing and len(cur) >= 2:
        out.append(cur)
    return out


def rotated_bbox(box: tuple[float, float, float, float], degrees: float,
                 pivot: Point | None = None) -> tuple[float, float, float, float]:
    """Axis-aligned bounds of ``box`` rotated clockwise by ``degrees`` around ``pivot`` (default: its centre)."""
    if not degrees:
        return box
    x0, y0, x1, y1 = box
    cx, cy = pivot if pivot is not None else ((x0 + x1) / 2, (y0 + y1) / 2)
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    xs, ys = [], []
    for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        dx, dy = px - cx, py - cy
        xs.append(cx + dx * c - dy * s)
        ys.append(cy + dx * s + dy * c)
    return (min(xs), min(ys), max(xs), max(ys))


def signed_area(pts: list[Point]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def point_in_polygon(x: float, y: float, pts: list[Point]) -> bool:
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _clean_ring(pts: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append((float(p[0]), float(p[1])))
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-9:
        out.pop()
    return out


def offset_ring(pts: list[Point], d: float, outward_sign: float, join: str = "miter",
                miter_limit: float = 4.0) -> list[Point]:
    """Offset a closed ring by ``d`` (positive = away from the filled side) with sharp (miter) or
    bevel corners. ``outward_sign`` is +1 or -1 and says which edge normal points out of the shape.
    Corners whose miter would be longer than ``miter_limit`` * |d| are bevelled."""
    ring = _clean_ring(pts)
    n = len(ring)
    if n < 3 or d == 0:
        return ring
    normals = []
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ln = math.hypot(ex, ey) or 1.0
        normals.append((outward_sign * ey / ln, -outward_sign * ex / ln))
    out: list[Point] = []
    for i in range(n):
        n1 = normals[i - 1]
        n2 = normals[i]
        vx, vy = ring[i]
        dot = n1[0] * n2[0] + n1[1] * n2[1]
        if dot > 1 - 1e-9:
            out.append((vx + d * n2[0], vy + d * n2[1]))
            continue
        factor = math.sqrt(2.0 / max(1e-9, 1.0 + dot))
        if join == "bevel" or factor > miter_limit or 1.0 + dot < 1e-6:
            out.append((vx + d * n1[0], vy + d * n1[1]))
            out.append((vx + d * n2[0], vy + d * n2[1]))
        else:
            sx, sy = n1[0] + n2[0], n1[1] + n2[1]
            out.append((vx + d * sx / (1.0 + dot), vy + d * sy / (1.0 + dot)))
    return out


def offset_shape(rings: list[list[Point]], d: float, join: str = "miter", miter_limit: float = 4.0) -> list[list[Point]]:
    """Offset every ring of an even-odd filled shape: outlines grow by d, holes shrink by d."""
    cleaned = [_clean_ring(r) for r in rings]
    out = []
    for i, ring in enumerate(cleaned):
        if len(ring) < 3:
            continue
        depth = sum(1 for j, other in enumerate(cleaned)
                    if j != i and len(other) >= 3 and point_in_polygon(ring[0][0], ring[0][1], other))
        sign = 1.0 if signed_area(ring) > 0 else -1.0
        if depth % 2:
            sign = -sign
        out.append(offset_ring(ring, d, sign, join, miter_limit))
    return out
