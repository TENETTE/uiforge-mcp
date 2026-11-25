"""Screen-level helpers: device presets and safe areas, pins for multi-resolution layouts,
row / column / grid arrangement and seeded scattering."""

from __future__ import annotations

import copy
import math
import random
from typing import Any

from .render import Renderer, resolve_style, shift_element

PRESETS: dict[str, tuple[int, int, tuple[float, float, float, float], str]] = {
    "720p": (1280, 720, (0, 0, 0, 0), "HD"),
    "1080p": (1920, 1080, (0, 0, 0, 0), "Full HD, the usual PC / console design size"),
    "1440p": (2560, 1440, (0, 0, 0, 0), "QHD"),
    "4k": (3840, 2160, (0, 0, 0, 0), "UHD"),
    "ultrawide": (2560, 1080, (0, 0, 0, 0), "21:9"),
    "ultrawide-1440": (3440, 1440, (0, 0, 0, 0), "21:9"),
    "tv-1080p": (1920, 1080, (96, 54, 96, 54), "console / TV: 5% title-safe margin"),
    "steam-deck": (1280, 800, (0, 0, 0, 0), "16:10 handheld"),
    "switch": (1280, 720, (0, 0, 0, 0), "handheld mode"),
    "iphone": (393, 852, (0, 59, 0, 34), "iPhone 15 portrait, points (x3 for pixels)"),
    "iphone-landscape": (852, 393, (59, 0, 59, 21), "iPhone 15 landscape, points"),
    "iphone-se": (375, 667, (0, 20, 0, 0), "small iPhone portrait, points"),
    "ipad": (820, 1180, (0, 24, 0, 20), "iPad Air portrait, points"),
    "ipad-landscape": (1180, 820, (0, 24, 0, 20), "iPad Air landscape, points"),
    "android": (412, 915, (0, 24, 0, 48), "common Android phone portrait, dp"),
    "android-landscape": (915, 412, (24, 0, 48, 0), "common Android phone landscape, dp"),
    "mobile-game-landscape": (2340, 1080, (132, 0, 132, 63), "19.5:9 phone, pixels, notch side margins"),
    "app-icon": (1024, 1024, (0, 0, 0, 0), "store icon master; keep art inside the centre 80%"),
}

PIN_X = ("left", "center", "right", "stretch", "scale")
PIN_Y = ("top", "middle", "bottom", "stretch", "scale")


def preset(name: str) -> tuple[int, int, tuple[float, float, float, float], str]:
    key = str(name).lower().strip()
    if key not in PRESETS:
        raise ValueError(f"Unknown preset '{name}'. Presets: {', '.join(PRESETS)}")
    return PRESETS[key]


def safe_insets(canvas: dict) -> tuple[float, float, float, float] | None:
    ins = canvas.get("safe_area")
    if ins:
        return tuple(float(v) for v in ins)          # type: ignore[return-value]
    return None



def _stretch(el: dict, axis: int, delta: float, warnings: list[str]) -> bool:
    """Grow an element along one axis by delta, keeping its start edge. False when the type cannot."""
    t = el["type"]
    if t in ("rect", "image", "instance"):
        key = "width" if axis == 0 else "height"
        if el.get(key) is None:
            return False
        el[key] = max(0.0, float(el[key]) + delta)
        return True
    if t == "ellipse":
        key = "rx" if axis == 0 else "ry"
        if axis == 1 and el.get("ry") is None:
            el["ry"] = float(el["rx"])
        el[key] = max(0.0, float(el[key]) + delta / 2)
        el["cx" if axis == 0 else "cy"] = float(el["cx" if axis == 0 else "cy"]) + delta / 2
        return True
    if t == "line" or (t == "polygon" and el.get("points")):
        pts = [[float(p[0]), float(p[1])] for p in el["points"]]
        lo = min(p[axis] for p in pts)
        hi = max(p[axis] for p in pts)
        span = hi - lo
        if span <= 0:
            return False
        for p in pts:
            p[axis] = lo + (p[axis] - lo) * (span + delta) / span
        el["points"] = pts
        return True
    if t == "text" and axis == 0 and el.get("max_width"):
        el["max_width"] = max(1.0, float(el["max_width"]) + delta)
        return True
    return False


def apply_resize(canvas: dict, renderer: Renderer, width: int, height: int) -> list[str]:
    """Resize ``canvas`` in place, moving / stretching elements by their pin (default left / top)."""
    dw, dh = width - float(canvas["width"]), height - float(canvas["height"])
    sw, sh = width / float(canvas["width"]), height / float(canvas["height"])
    warnings: list[str] = []
    boxes = {el["id"]: renderer.element_box(el) for el in canvas["elements"]}
    for el in canvas["elements"]:
        pin = el.get("pin") or {}
        px, py = str(pin.get("x", "left")), str(pin.get("y", "top"))
        b = boxes[el["id"]]
        dx = dy = 0.0
        if px == "right":
            dx = dw
        elif px == "center":
            dx = dw / 2
        elif px == "scale":
            dx = (b[0] + b[2]) / 2 * (sw - 1)
        elif px == "stretch" and not _stretch(el, 0, dw, warnings):
            dx = dw / 2
            warnings.append(f"{el['id']}: a {el['type']} cannot stretch horizontally; it was centred instead")
        if py == "bottom":
            dy = dh
        elif py == "middle":
            dy = dh / 2
        elif py == "scale":
            dy = (b[1] + b[3]) / 2 * (sh - 1)
        elif py == "stretch" and not _stretch(el, 1, dh, warnings):
            dy = dh / 2
            warnings.append(f"{el['id']}: a {el['type']} cannot stretch vertically; it was centred instead")
        if dx or dy:
            shift_element(el, dx, dy)
    canvas["width"], canvas["height"] = int(width), int(height)
    return warnings


def resized_copy(canvas: dict, renderer: Renderer, width: int, height: int) -> tuple[dict, list[str]]:
    clone = copy.deepcopy(canvas)
    clone["id"] = f"{canvas['id']}@{width}x{height}"
    return clone, apply_resize(clone, renderer, width, height)



def arrange(renderer: Renderer, elements: list[dict], mode: str, gap: float, columns: int | None,
            origin: tuple[float, float] | None, container: tuple[float, float, float, float] | None,
            padding: float, align: str, justify: str) -> tuple[tuple[float, float, float, float], list[tuple[dict, float, float]]]:
    """Plan moves that lay elements out in a row, column or grid. Returns (content box, [(el, dx, dy)])."""
    if not elements:
        raise ValueError("nothing to arrange - pass element ids or a group that has elements")
    boxes = [renderer.element_box(e) for e in elements]
    sizes = [(b[2] - b[0], b[3] - b[1]) for b in boxes]
    mode = mode.lower()
    if mode not in ("row", "column", "grid"):
        raise ValueError("mode must be 'row', 'column' or 'grid'")
    n = len(elements)
    if mode == "row":
        cols, rows = n, 1
    elif mode == "column":
        cols, rows = 1, n
    else:
        cols = max(1, int(columns or math.ceil(math.sqrt(n))))
        rows = math.ceil(n / cols)
    col_w = [0.0] * cols
    row_h = [0.0] * rows
    for i, (w, h) in enumerate(sizes):
        c, r = i % cols, i // cols
        col_w[c] = max(col_w[c], w)
        row_h[r] = max(row_h[r], h)
    if mode == "grid":
        cw, rh = max(col_w), max(row_h)
        col_w, row_h = [cw] * cols, [rh] * rows
    total_w = sum(col_w) + gap * (cols - 1)
    total_h = sum(row_h) + gap * (rows - 1)
    if container is not None:
        cx0, cy0, cx1, cy1 = container
        inner_w, inner_h = cx1 - cx0 - 2 * padding, cy1 - cy0 - 2 * padding
        if justify == "space-between" and mode != "column" and cols > 1:
            gap_x = (inner_w - sum(col_w)) / (cols - 1)
        else:
            gap_x = gap
        if justify == "space-between" and mode == "column" and rows > 1:
            gap_y = (inner_h - sum(row_h)) / (rows - 1)
        else:
            gap_y = gap
        total_w = sum(col_w) + gap_x * (cols - 1)
        total_h = sum(row_h) + gap_y * (rows - 1)
        main_free_x = inner_w - total_w
        main_free_y = inner_h - total_h
        ox = cx0 + padding + (main_free_x / 2 if justify == "center" else main_free_x if justify == "end" else 0)
        oy = cy0 + padding + (main_free_y / 2 if justify == "center" else main_free_y if justify == "end" else 0)
        if mode == "row":
            oy = cy0 + padding
            row_h = [inner_h]
        if mode == "column":
            ox = cx0 + padding
            col_w = [inner_w]
    else:
        gap_x = gap_y = gap
        ox, oy = origin if origin is not None else (boxes[0][0], boxes[0][1])
    moves = []
    y = oy
    for r in range(rows):
        x = ox
        for c in range(cols):
            i = r * cols + c
            if i >= n:
                break
            w, h = sizes[i]
            cell_w, cell_h = col_w[c], row_h[r]
            if mode == "row":
                tx = x
                ty = y + (0 if align == "start" else (cell_h - h) / 2 if align == "center" else cell_h - h)
            elif mode == "column":
                ty = y
                tx = x + (0 if align == "start" else (cell_w - w) / 2 if align == "center" else cell_w - w)
            else:
                tx = x + (cell_w - w) / 2 if align == "center" else x if align == "start" else x + cell_w - w
                ty = y + (cell_h - h) / 2 if align == "center" else y if align == "start" else y + cell_h - h
            moves.append((elements[i], tx - boxes[i][0], ty - boxes[i][1]))
            x += cell_w + gap_x
        y += row_h[r] + gap_y
    content = (ox, oy, ox + total_w, oy + total_h)
    return content, moves



def scatter_plan(count: int, area: tuple[float, float, float, float], seed: int, min_distance: float,
                 shape: str = "rect") -> list[tuple[float, float]]:
    """Seeded random points inside an area (rect or inscribed ellipse), optionally kept apart."""
    rng = random.Random(seed)
    x0, y0, x1, y1 = area
    pts: list[tuple[float, float]] = []
    tries = 0
    while len(pts) < count and tries < count * 200:
        tries += 1
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if shape == "ellipse":
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            if rx <= 0 or ry <= 0 or ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 > 1:
                continue
        if min_distance > 0 and any((x - px) ** 2 + (y - py) ** 2 < min_distance ** 2 for px, py in pts):
            continue
        pts.append((x, y))
    return pts
