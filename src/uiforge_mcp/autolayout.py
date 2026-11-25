"""Live auto layout (Figma / Penpot flex & grid): containers that re-flow their children after every change.

A container element (usually a rect) carries
  "layout": {"mode": "row" | "column" | "grid", "children": [ids or "group:<name>"], "gap": 8,
             "padding": 12 or [top, right, bottom, left], "align": start | center | end,
             "justify": start | center | end | space-between, "wrap": false, "columns": 3, "hug": false |
             true | "width" | "height"}
and its children may carry "layout_size": {"width": "fill" | number, "height": "fill" | number,
"min_width", "max_width", "min_height", "max_height"}, "span": [columns, rows] (grid) or "absolute": true
(left where it is). The store calls reflow() before saving a canvas, so text edits, added items or a
resized container immediately move and resize everything, like a real auto-layout frame.
"""

from __future__ import annotations

from typing import Any

from .render import shift_element

_SIZED = {"rect", "image", "instance"}


def _pad(value: Any) -> tuple[float, float, float, float]:
    if value is None:
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v, v, v, v
    vals = [float(v) for v in value]
    if len(vals) == 2:
        return vals[0], vals[1], vals[0], vals[1]
    if len(vals) == 4:
        return tuple(vals)                                   # type: ignore[return-value]
    raise ValueError("layout padding must be a number, [vertical, horizontal] or [top, right, bottom, left]")


def _items(canvas: dict, spec: dict) -> list[list[dict]]:
    by_id = {e["id"]: e for e in canvas["elements"]}
    out = []
    for ref in spec.get("children") or []:
        ref = str(ref)
        if ref.startswith("group:"):
            members = [e for e in canvas["elements"] if e.get("group") == ref[6:] and e.get("visible", True)]
        else:
            members = [by_id[ref]] if ref in by_id and by_id[ref].get("visible", True) else []
        members = [m for m in members if not m.get("absolute")]
        if members:
            out.append(members)
    return out


def _union(r, members: list[dict]) -> tuple[float, float, float, float]:
    boxes = [r.element_box(m) for m in members]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _resize(el: dict, w: float | None, h: float | None) -> None:
    if el["type"] in _SIZED:
        if w is not None:
            el["width"] = round(max(0.0, w), 3)
        if h is not None:
            el["height"] = round(max(0.0, h), 3)
    elif el["type"] == "ellipse":
        if w is not None:
            el["rx"] = round(max(0.0, w / 2), 3)
        if h is not None:
            el["ry"] = round(max(0.0, h / 2), 3)
    elif el["type"] == "text" and w is not None:
        el["max_width"] = round(max(1.0, w), 3)


def _clamp(v: float, size: dict, axis: str) -> float:
    lo, hi = size.get(f"min_{axis}"), size.get(f"max_{axis}")
    if lo is not None:
        v = max(v, float(lo))
    if hi is not None:
        v = min(v, float(hi))
    return v


def _flow(store, canvas: dict, cont: dict) -> None:
    spec = cont["layout"]
    mode = str(spec.get("mode", "row")).lower()
    if mode not in ("row", "column", "grid"):
        raise ValueError("layout mode must be 'row', 'column' or 'grid'")
    gap = float(spec.get("gap", 8))
    pt, pr, pb, pl = _pad(spec.get("padding", 0))
    align = str(spec.get("align", "start")).lower()
    justify = str(spec.get("justify", "start")).lower()
    hug = spec.get("hug", False)
    hug_w = hug is True or hug == "width"
    hug_h = hug is True or hug == "height"
    items = _items(canvas, spec)
    if not items:
        return
    r = store.renderer(canvas)
    x0, y0, x1, y1 = r.element_box(cont)
    inner_w, inner_h = x1 - x0 - pl - pr, y1 - y0 - pt - pb

    main = "width" if mode != "column" else "height"
    cross = "height" if main == "width" else "width"
    boxes = [_union(r, m) for m in items]
    sizes = [[b[2] - b[0], b[3] - b[1]] for b in boxes]
    fill_main = []
    for i, members in enumerate(items):
        size = members[0].get("layout_size") or {} if len(members) == 1 else {}
        for axis, idx in (("width", 0), ("height", 1)):
            val = size.get(axis)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                sizes[i][idx] = float(val)
            elif val == "fill" and mode != "grid":
                if axis == main and not (hug_w if main == "width" else hug_h):
                    fill_main.append(i)
                elif axis == cross and not (hug_h if cross == "height" else hug_w):
                    sizes[i][idx] = inner_h if cross == "height" else inner_w
            sizes[i][idx] = _clamp(sizes[i][idx], size, axis)
    if fill_main and mode != "grid":
        mi = 0 if main == "width" else 1
        avail = (inner_w if main == "width" else inner_h) - gap * (len(items) - 1)
        fixed = sum(s[mi] for j, s in enumerate(sizes) if j not in fill_main)
        share = max(0.0, (avail - fixed) / len(fill_main))
        for i in fill_main:
            size = items[i][0].get("layout_size") or {}
            sizes[i][mi] = _clamp(share, size, main)
    if mode == "grid":
        cols = max(1, int(spec.get("columns") or 2))
        cell_w = (sizes and max(s[0] for s in sizes)) if hug_w else (inner_w - gap * (cols - 1)) / cols
    for i, members in enumerate(items):
        if len(members) != 1:
            continue
        el = members[0]
        size = el.get("layout_size") or {}
        want_w, want_h = sizes[i]
        if mode == "grid" and (size.get("width") == "fill" or size.get("height") == "fill"):
            span = el.get("span") or [1, 1]
            if size.get("width") == "fill":
                want_w = cell_w * int(span[0]) + gap * (int(span[0]) - 1)
        if any(isinstance(size.get(a), (int, float)) or size.get(a) == "fill" or size.get(f"min_{a}") is not None
               or size.get(f"max_{a}") is not None for a in ("width", "height")):
            cur = r.element_box(el)
            _resize(el, want_w if abs(want_w - (cur[2] - cur[0])) > 1e-6 else None,
                    want_h if abs(want_h - (cur[3] - cur[1])) > 1e-6 and el["type"] != "text" else None)

    r = store.renderer(canvas)
    boxes = [_union(r, m) for m in items]
    sizes = [(b[2] - b[0], b[3] - b[1]) for b in boxes]
    ox, oy = x0 + pl, y0 + pt
    targets: list[tuple[float, float]] = []
    if mode == "grid":
        cols = max(1, int(spec.get("columns") or 2))
        cell_w = max(s[0] for s in sizes) if hug_w else (inner_w - gap * (cols - 1)) / cols
        taken: set[tuple[int, int]] = set()
        placed = []
        for i, members in enumerate(items):
            span = members[0].get("span") or [1, 1] if len(members) == 1 else [1, 1]
            cs, rs = max(1, min(cols, int(span[0]))), max(1, int(span[1]))
            row = 0
            while True:
                spot = next((c for c in range(cols - cs + 1)
                             if all((row + dr, c + dc) not in taken for dr in range(rs) for dc in range(cs))), None)
                if spot is not None:
                    break
                row += 1
            for dr in range(rs):
                for dc in range(cs):
                    taken.add((row + dr, spot + dc))
            placed.append((row, spot, cs, rs))
        n_rows = max(p[0] + p[3] for p in placed)
        row_h = [0.0] * n_rows
        for (row, _, _, rs), (_, h) in zip(placed, sizes):
            per = (h - gap * (rs - 1)) / rs
            for dr in range(rs):
                row_h[row + dr] = max(row_h[row + dr], per)
        row_y = [oy + sum(row_h[:k]) + gap * k for k in range(n_rows)]
        for (row, col, cs, rs), (w, h) in zip(placed, sizes):
            cx = ox + col * (cell_w + gap)
            span_w = cell_w * cs + gap * (cs - 1)
            span_h = sum(row_h[row:row + rs]) + gap * (rs - 1)
            tx = cx + {"start": 0, "center": (span_w - w) / 2, "end": span_w - w}.get(align, 0)
            ty = row_y[row] + {"start": 0, "center": (span_h - h) / 2, "end": span_h - h}.get(align, 0)
            targets.append((tx, ty))
        content = (ox, oy, ox + cell_w * cols + gap * (cols - 1), oy + sum(row_h) + gap * (n_rows - 1))
    else:
        horizontal = mode == "row"
        limit = inner_w if horizontal else inner_h
        lines: list[list[int]] = [[]]
        used = 0.0
        for i, (w, h) in enumerate(sizes):
            m = w if horizontal else h
            if spec.get("wrap") and lines[-1] and used + gap + m > limit + 1e-6 and not (hug_w if horizontal else hug_h):
                lines.append([])
                used = 0.0
            used = m if not lines[-1] else used + gap + m
            lines[-1].append(i)
        cursor_cross = oy if horizontal else ox
        ends = []
        for line in lines:
            mains = [sizes[i][0 if horizontal else 1] for i in line]
            crosses = [sizes[i][1 if horizontal else 0] for i in line]
            total = sum(mains) + gap * (len(line) - 1)
            line_cross = max(crosses)
            hugging = hug_w if horizontal else hug_h
            free = 0.0 if hugging else limit - total
            step_gap = gap
            start = 0.0
            if justify == "center":
                start = free / 2
            elif justify == "end":
                start = free
            elif justify == "space-between" and len(line) > 1 and not hugging:
                step_gap = gap + free / (len(line) - 1)
            pos = (ox if horizontal else oy) + start
            cross_room = line_cross if (len(lines) > 1 or (hug_h if horizontal else hug_w)) else (inner_h if horizontal else inner_w)
            for i, m, c in zip(line, mains, crosses):
                off = {"start": 0, "center": (cross_room - c) / 2, "end": cross_room - c}.get(align, 0)
                targets.append((pos, cursor_cross + off) if horizontal else (cursor_cross + off, pos))
                pos += m + step_gap
            ends.append(pos - step_gap)
            cursor_cross += line_cross + gap
        span_main = max(ends) - (ox if horizontal else oy)
        span_cross = cursor_cross - gap - (oy if horizontal else ox)
        content = ((ox, oy, ox + span_main, oy + span_cross) if horizontal
                   else (ox, oy, ox + span_cross, oy + span_main))
        order = [i for line in lines for i in line]
        targets = [t for _, t in sorted(zip(order, targets))]
    for members, box, (tx, ty) in zip(items, boxes, targets):
        dx, dy = tx - box[0], ty - box[1]
        if abs(dx) > 1e-6 or abs(dy) > 1e-6:
            for m in members:
                shift_element(m, dx, dy)

    if (hug_w or hug_h) and cont["type"] == "rect":
        if hug_w:
            cont["width"] = round(content[2] - content[0] + pl + pr, 3)
        if hug_h:
            cont["height"] = round(content[3] - content[1] + pt + pb, 3)


def reflow(store, canvas: dict) -> None:
    """Re-flow every auto-layout container, innermost first (a container may itself be a child)."""
    containers = [e for e in canvas["elements"] if isinstance(e.get("layout"), dict)]
    if not containers:
        return
    child_of: dict[str, set[str]] = {}
    for c in containers:
        for members in _items(canvas, c["layout"]):
            for m in members:
                child_of.setdefault(m["id"], set()).add(c["id"])
    done: set[str] = set()
    pending = list(containers)
    while pending:
        progress = False
        for c in list(pending):
            inner = [o for o in pending if o is not c and c["id"] in child_of.get(o["id"], set())]
            if not inner:
                _flow(store, canvas, c)
                done.add(c["id"])
                pending.remove(c)
                progress = True
        if not progress:
            for c in pending:
                _flow(store, canvas, c)
            break
