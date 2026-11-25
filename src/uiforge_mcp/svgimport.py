"""Turn SVG markup into path elements (no external dependencies, no network).

Supported: <path>, <rect> (incl. rx/ry), <circle>, <ellipse>, <line>, <polyline>, <polygon>,
nested <g> and <svg> with transform (matrix, translate, scale, rotate, skewX, skewY), presentation
attributes and inline style="..." for fill, stroke, stroke-width, opacity, fill-opacity,
stroke-opacity, fill-rule, display/visibility, and linear/radial gradients referenced by url(#id)
(mapped to the element's box). Curves are flattened to polylines in canvas units.
Not supported (reported back): text, images, filters, masks, clipPath, patterns, <use>, CSS classes.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any

from . import geometry as geo

Matrix = tuple[float, float, float, float, float, float]
IDENT: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
CONTAINERS = {"svg", "g", "a", "switch"}
SKIP_SILENT = {"defs", "title", "desc", "metadata", "style", "linearGradient", "radialGradient", "stop",
               "symbol", "clipPath", "mask", "filter", "pattern", "marker"}
INHERITED = ("fill", "stroke", "stroke-width", "fill-rule", "fill-opacity", "stroke-opacity", "color",
             "visibility", "stroke-linecap", "stroke-linejoin")
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def apply(m: Matrix, pts: list[geo.Point]) -> list[geo.Point]:
    a, b, c, d, e, f = m
    return [(a * x + c * y + e, b * x + d * y + f) for x, y in pts]


def parse_transform(text: str | None) -> Matrix:
    m = IDENT
    if not text:
        return m
    for name, args in re.findall(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", text):
        v = [float(x) for x in _NUM.findall(args)]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0] if v else 0, v[1] if len(v) > 1 else 0)
        elif name == "scale":
            sx = v[0] if v else 1
            t = (sx, 0, 0, v[1] if len(v) > 1 else sx, 0, 0)
        elif name == "rotate":
            a = math.radians(v[0] if v else 0)
            ca, sa = math.cos(a), math.sin(a)
            t = (ca, sa, -sa, ca, 0, 0)
            if len(v) >= 3:
                cx, cy = v[1], v[2]
                t = mul(mul((1, 0, 0, 1, cx, cy), t), (1, 0, 0, 1, -cx, -cy))
        elif name == "skewX":
            t = (1, 0, math.tan(math.radians(v[0] if v else 0)), 1, 0, 0)
        elif name == "skewY":
            t = (1, math.tan(math.radians(v[0] if v else 0)), 0, 1, 0, 0)
        else:
            continue
        m = mul(m, t)          # type: ignore[arg-type]
    return m


def _attrs(node: ET.Element) -> dict[str, str]:
    out = {k: v for k, v in node.attrib.items() if "}" not in k}
    for decl in (node.get("style") or "").split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _length(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    m = _NUM.match(str(v).strip())
    return float(m.group(0)) if m else default


def _shape_paths(tag: str, a: dict[str, str], res: float) -> list[tuple[list[geo.Point], bool]]:
    if tag == "path":
        return geo.parse_svg_path(a.get("d", ""), res)
    if tag == "rect":
        x, y, w, h = (_length(a.get(k)) for k in ("x", "y", "width", "height"))
        if w <= 0 or h <= 0:
            return []
        rx, ry = a.get("rx"), a.get("ry")
        r = _length(rx if rx is not None else ry)
        return [(geo.rect_path(x, y, w, h, min(r, w / 2, h / 2), "round", res), True)]
    if tag == "circle":
        r = _length(a.get("r"))
        return [(geo.ellipse_path(_length(a.get("cx")), _length(a.get("cy")), r, r, res), True)] if r > 0 else []
    if tag == "ellipse":
        rx, ry = _length(a.get("rx")), _length(a.get("ry"))
        if rx <= 0 or ry <= 0:
            return []
        return [(geo.ellipse_path(_length(a.get("cx")), _length(a.get("cy")), rx, ry, res), True)]
    if tag == "line":
        return [([(_length(a.get("x1")), _length(a.get("y1"))), (_length(a.get("x2")), _length(a.get("y2")))], False)]
    if tag in ("polyline", "polygon"):
        v = [float(x) for x in _NUM.findall(a.get("points", ""))]
        pts = list(zip(v[0::2], v[1::2]))
        return [(pts, tag == "polygon")] if len(pts) >= 2 else []
    return []


def _fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def to_d(subpaths: list[tuple[list[geo.Point], bool]]) -> str:
    parts = []
    for pts, closed in subpaths:
        if len(pts) < 2:
            continue
        parts.append("M" + _fmt(pts[0][0]) + " " + _fmt(pts[0][1]))
        parts.append("L" + " ".join(_fmt(x) + " " + _fmt(y) for x, y in pts[1:]))
        if closed:
            parts.append("Z")
    return " ".join(parts)


def _gradients(root: ET.Element) -> dict[str, ET.Element]:
    out = {}
    for node in root.iter():
        if _local(node.tag) in ("linearGradient", "radialGradient") and node.get("id"):
            out[node.get("id")] = node
    return out


def _paint(value: str | None, opacity: float, current: str, grads: dict, notes: set) -> Any:
    if value is None:
        return None
    v = value.strip()
    if v in ("none", "transparent"):
        return "none"
    if v == "currentColor":
        v = current
    m = re.match(r"url\(\s*#([^)\s]+)\s*\)", v)
    if m:
        node = grads.get(m.group(1))
        if node is None:
            notes.add(f"gradient #{m.group(1)} not found; used the fallback colour")
            return _paint(v[m.end():].strip() or "#000000", opacity, current, grads, notes)
        return _gradient(node, opacity, current, grads, notes)
    return v + (f"@{opacity:.3f}" if opacity < 1 else "")


def _gradient(node: ET.Element, opacity: float, current: str, grads: dict, notes: set) -> Any:
    stops_src = node
    seen = 0
    while not [s for s in stops_src if _local(s.tag) == "stop"] and seen < 8:
        href = stops_src.get("href") or stops_src.get("{http://www.w3.org/1999/xlink}href") or ""
        nxt = grads.get(href.lstrip("#"))
        if nxt is None:
            break
        stops_src, seen = nxt, seen + 1
    stops = []
    for s in stops_src:
        if _local(s.tag) != "stop":
            continue
        a = _attrs(s)
        off = a.get("offset", "0").strip()
        t = float(off[:-1]) / 100 if off.endswith("%") else _length(off)
        col = a.get("stop-color", "#000000")
        if col == "currentColor":
            col = current
        op = _length(a.get("stop-opacity"), 1.0) * opacity
        stops.append([max(0.0, min(1.0, t)), col + (f"@{op:.3f}" if op < 1 else "")])
    if not stops:
        notes.add("a gradient had no stops; drew nothing for it")
        return "none"
    if node.get("gradientTransform"):
        notes.add("gradientTransform is ignored (gradient mapped to the element box)")
    if _local(node.tag) == "linearGradient":
        def frac(name: str, d: float) -> float:
            v = node.get(name)
            if v is None:
                return d
            return float(v[:-1]) / 100 if v.strip().endswith("%") else _length(v)
        if node.get("gradientUnits") == "userSpaceOnUse":
            notes.add("userSpaceOnUse gradient approximated by its direction over the element box")
        x1, y1, x2, y2 = frac("x1", 0), frac("y1", 0), frac("x2", 1), frac("y2", 0)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        return {"type": "linear", "angle": round(angle, 2), "stops": stops}
    return {"type": "radial", "cx": 0.5, "cy": 0.5, "r": 0.5, "stops": stops}


def convert(svg_text: str, x: float, y: float, width: float | None, height: float | None,
            current_color: str = "#ffffff", detail: float = 1.0) -> tuple[list[dict], list[str], tuple[float, float]]:
    """Return (path element props, notes, (placed width, placed height))."""
    if re.search(r"<!(DOCTYPE|ENTITY)", svg_text, re.I):
        raise ValueError("SVG with DOCTYPE/ENTITY declarations is not accepted; remove them")
    try:
        root = ET.fromstring(svg_text.strip())
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse SVG: {exc} - pass complete, well-formed <svg>...</svg> markup") from exc
    if _local(root.tag) != "svg":
        raise ValueError("root element must be <svg>")
    vb = [float(v) for v in _NUM.findall(root.get("viewBox", ""))]
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        vx, vy, vw, vh = vb
    else:
        vx, vy = 0.0, 0.0
        vw, vh = _length(root.get("width"), 0), _length(root.get("height"), 0)
        if vw <= 0 or vh <= 0:
            vw = vh = 0.0
    notes: set[str] = set()
    grads = _gradients(root)

    items: list[tuple[str, dict, dict, Matrix]] = []

    def walk(node: ET.Element, inherited: dict, m: Matrix, opacity: float) -> None:
        tag = _local(node.tag)
        a = _attrs(node)
        if a.get("display", "").strip() == "none":
            return
        style = dict(inherited)
        for k in INHERITED:
            if k in a:
                style[k] = a[k]
        op = opacity * _length(a.get("opacity"), 1.0)
        mm = mul(m, parse_transform(a.get("transform")))
        if tag in CONTAINERS:
            if tag == "svg" and node is not root:
                inner_x, inner_y = _length(a.get("x")), _length(a.get("y"))
                mm = mul(mm, (1, 0, 0, 1, inner_x, inner_y))
            for child in node:
                walk(child, style, mm, op)
            return
        if tag in SHAPES:
            if style.get("visibility") in ("hidden", "collapse"):
                return
            items.append((tag, a, dict(style, opacity=str(op)), mm))
            return
        if tag not in SKIP_SILENT:
            notes.add(f"<{tag}> is not supported and was skipped")

    walk(root, {}, IDENT, 1.0)
    if not items:
        raise ValueError("the SVG has no drawable shapes (path, rect, circle, ellipse, line, polyline, polygon)")

    if vw <= 0:
        allpts = [p for tag, a, _, m in items for pts, _ in _shape_paths(tag, a, 4.0) for p in apply(m, pts)]
        if not allpts:
            raise ValueError("the SVG shapes are all empty")
        x0, y0, x1, y1 = geo.bbox_of([allpts])
        vx, vy, vw, vh = x0, y0, max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    if width and height:
        s = min(width / vw, height / vh)
        ox = x + (width - vw * s) / 2
        oy = y + (height - vh * s) / 2
    elif width:
        s = width / vw
        ox, oy = x, y
    elif height:
        s = height / vh
        ox, oy = x, y
    else:
        s, ox, oy = 1.0, x, y
    place: Matrix = (s, 0, 0, s, ox - vx * s, oy - vy * s)

    out = []
    for tag, a, style, m in items:
        full = mul(place, m)
        det = abs(full[0] * full[3] - full[1] * full[2])
        lin = math.sqrt(det) if det > 0 else s
        subs = _shape_paths(tag, a, max(0.05, 4.0 * lin * max(0.25, detail)))
        if not subs:
            continue
        paths = [(apply(full, pts), closed) for pts, closed in subs]
        current = style.get("color", current_color)
        if current == "currentColor":
            current = current_color
        op = float(style.get("opacity", 1))
        fill_val = style.get("fill", "#000000")
        fill = _paint(fill_val, op * _length(style.get("fill-opacity"), 1.0), current_color if fill_val == "currentColor" else current, grads, notes)
        stroke_val = style.get("stroke")
        stroke = _paint(stroke_val, op * _length(style.get("stroke-opacity"), 1.0),
                        current_color if stroke_val == "currentColor" else current, grads, notes)
        if not any(closed for _, closed in paths) and len(paths) and fill not in (None, "none") and stroke in (None, "none"):
            paths = [(pts, True) for pts, _ in paths]
        st: dict[str, Any] = {"fill": fill if fill is not None else "none"}
        if stroke not in (None, "none"):
            width_px = _length(style.get("stroke-width"), 1.0) * lin
            if width_px > 0:
                join = style.get("stroke-linejoin", "miter").strip()
                st["stroke"] = {"fill" if isinstance(stroke, dict) else "color": stroke, "width": round(width_px, 3),
                                "align": "center", "join": "round" if join == "round" else ("bevel" if join == "bevel" else "miter")}
        if st["fill"] == "none" and "stroke" not in st:
            continue
        props: dict[str, Any] = {"d": to_d(paths), "style": st}
        if style.get("fill-rule", "nonzero").strip() == "nonzero":
            props["fill_rule"] = "nonzero"
        out.append(props)
    return out, sorted(notes), (vw * s, vh * s)
