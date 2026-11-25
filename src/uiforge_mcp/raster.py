"""Exact scanline rasteriser (numpy).

Pillow's polygon fill truncates coordinates to whole pixels and includes the far
edge, which leaks a faint extra row/column around pixel-aligned UI shapes. This
module samples pixel centres exactly instead: a pixel is inside when its centre
is. Used at supersampled resolution, then box-filtered down by the renderer.
"""

from __future__ import annotations

import numpy as np


def _poly_edges(poly: np.ndarray) -> tuple[np.ndarray, ...]:
    nxt = np.roll(poly, -1, axis=0)
    return poly[:, 0], poly[:, 1], nxt[:, 0], nxt[:, 1]


def _accumulate(x0: np.ndarray, y0: np.ndarray, x1: np.ndarray, y1: np.ndarray, mult: np.ndarray | None,
                w: int, h: int) -> np.ndarray:
    """Winding number of every pixel centre for the given directed edges. Returns int16 (h, w)."""
    acc = np.zeros((h, w + 1), dtype=np.int16)
    ya, yb = np.minimum(y0, y1), np.maximum(y0, y1)
    r0 = np.clip(np.ceil(ya - 0.5), 0, h).astype(np.int64)
    r1 = np.clip(np.ceil(yb - 0.5), 0, h).astype(np.int64)
    cnt = r1 - r0
    keep = cnt > 0
    if not keep.any():
        return acc[:, :w]
    x0, y0, x1, y1, r0, cnt = x0[keep], y0[keep], x1[keep], y1[keep], r0[keep], cnt[keep]
    sign = np.where(y1 > y0, 1, -1).astype(np.int16)
    if mult is not None:
        sign = sign * mult[keep].astype(np.int16)
    slope = (x1 - x0) / (y1 - y0)
    idx = np.repeat(np.arange(len(cnt)), cnt)
    starts = np.cumsum(cnt) - cnt
    rows = r0[idx] + (np.arange(int(cnt.sum())) - starts[idx])
    xs = x0[idx] + (rows + 0.5 - y0[idx]) * slope[idx]
    cols = np.clip(np.ceil(xs - 0.5), 0, w).astype(np.int64)
    np.add.at(acc, (rows, cols), sign[idx])
    np.cumsum(acc, axis=1, out=acc)
    return acc[:, :w]


def fill_polygons(polys: list[np.ndarray], w: int, h: int, rule: str = "evenodd") -> np.ndarray:
    """Fill closed polygons (each an (N, 2) float array in pixel coordinates). Returns uint8 0/255.

    rule="evenodd": overlapping subpaths cut holes. rule="union": everything covered by any polygon.
    rule="nonzero": SVG's default winding rule (holes only where a subpath runs the other way).
    """
    polys = [np.asarray(p, dtype=np.float64) for p in polys if len(p) >= 3]
    if not polys:
        return np.zeros((h, w), dtype=np.uint8)
    xs0, ys0, xs1, ys1, mults = [], [], [], [], []
    for p in polys:
        x0, y0, x1, y1 = _poly_edges(p)
        xs0.append(x0)
        ys0.append(y0)
        xs1.append(x1)
        ys1.append(y1)
        if rule == "union":
            area = float(np.sum(x0 * y1 - x1 * y0))
            mults.append(np.full(len(p), 1 if area >= 0 else -1, dtype=np.int16))
    mult = np.concatenate(mults) if rule == "union" else None
    acc = _accumulate(np.concatenate(xs0), np.concatenate(ys0), np.concatenate(xs1), np.concatenate(ys1), mult, w, h)
    inside = (acc & 1).astype(bool) if rule == "evenodd" else (acc != 0)
    return inside.astype(np.uint8) * 255


def stroke_polylines(items: list[tuple[np.ndarray, bool, float, bool]], w: int, h: int) -> np.ndarray:
    """Thick polylines with round joins. items: (points (M, 2) px, closed, radius px, round_caps)."""
    x0s, y0s, x1s, y1s, mults = [], [], [], [], []

    def push(stack: np.ndarray) -> None:
        """stack: (count, verts, 2) convex polygons, any orientation."""
        nxt = np.roll(stack, -1, axis=1)
        area = np.sum(stack[..., 0] * nxt[..., 1] - nxt[..., 0] * stack[..., 1], axis=1)
        orient = np.sign(area).astype(np.int16)
        x0s.append(stack[..., 0].ravel())
        y0s.append(stack[..., 1].ravel())
        x1s.append(nxt[..., 0].ravel())
        y1s.append(nxt[..., 1].ravel())
        mults.append(np.repeat(orient, stack.shape[1]))

    for pts, closed, radius, round_caps in items:
        p = np.asarray(pts, dtype=np.float64)
        if len(p) < 2:
            continue
        r = max(0.5, float(radius))
        if closed and len(p) > 2:
            p = np.vstack([p, p[:1]])
        a, b = p[:-1], p[1:]
        d = b - a
        length = np.hypot(d[:, 0], d[:, 1])
        ok = length > 1e-9
        if ok.any():
            a, b, d, length = a[ok], b[ok], d[ok], length[ok]
            n = np.stack([-d[:, 1], d[:, 0]], axis=1) / length[:, None] * r
            push(np.stack([a + n, b + n, b - n, a - n], axis=1))
        if closed or round_caps:
            segs = int(max(8, min(72, np.ceil(2 * np.pi * r / 3.0))))
            ang = np.linspace(0, 2 * np.pi, segs, endpoint=False)
            circle = np.stack([np.cos(ang), np.sin(ang)], axis=1) * r
            push(p[:, None, :] + circle[None, :, :])
        elif ok.any() and len(a) > 1:
            joint, n_in, n_out = b[:-1], n[:-1], n[1:]
            push(np.stack([joint, joint + n_in, joint + n_out], axis=1))
            push(np.stack([joint, joint - n_in, joint - n_out], axis=1))
    if not x0s:
        return np.zeros((h, w), dtype=np.uint8)
    acc = _accumulate(np.concatenate(x0s), np.concatenate(y0s), np.concatenate(x1s), np.concatenate(y1s),
                      np.concatenate(mults), w, h)
    return (acc != 0).astype(np.uint8) * 255
