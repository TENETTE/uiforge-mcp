"""Design-system tools: the full reference (guide), colour palettes, kit-wide restyling and path operations.
Registered on the same MCP server."""

from __future__ import annotations

import copy
import json
import math
from typing import Any

import numpy as np

from . import effects as fxlib
from .colors import parse_color
from .reference import TOPICS
from .render import LINE_TYPES, VECTOR_TYPES, _placed_polys, _stroke_specs, resolve_style, vector_geometry
from .server import _maybe_json, _prepare_update, _summary, slugify, store, tool

__all__ = ["guide", "make_palette", "restyle", "path_ops", "find_elements", "vectorize_image", "make_variations"]



@tool
def guide(topic: str = "index"):
    """Full reference for this server (MCP clients cut long server instructions, so the details live here).

    topic: "index" (list), "fills", "shader", "style", "design", "layers", "geometry", "text", "reuse",
    "review", "animation", "export", or "all". Read the topic before using a feature for the first time.
    """
    key = str(topic or "index").strip().lower()
    if key == "all":
        return "\n\n".join(f"## {name}\n{TOPICS[name]}" for name in TOPICS if name != "index")
    if key not in TOPICS:
        raise ValueError(f"unknown topic '{topic}'. Topics: {', '.join(sorted(TOPICS))}, all")
    return TOPICS[key]



_STEPS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
_L = (0.975, 0.94, 0.88, 0.80, 0.71, 0.62, 0.53, 0.45, 0.37, 0.29, 0.21)
_C = (0.12, 0.25, 0.45, 0.70, 0.90, 1.0, 0.95, 0.85, 0.72, 0.60, 0.50)


def _oklab(rgb) -> np.ndarray:
    return fxlib.encode_space(np.array(rgb[:3], dtype=np.float64), "oklab")


def _srgb(lab) -> np.ndarray:
    return fxlib.decode_space(np.array(lab, dtype=np.float64), "oklab")


def _in_gamut(L: float, C: float, h: float) -> np.ndarray:
    """sRGB for an OKLCH colour, with chroma lowered until it fits (no clipped, shifted hues)."""
    lo, hi = 0.0, C
    best = _srgb([L, 0.0, 0.0])
    for _ in range(18):
        mid = (lo + hi) / 2
        rgb = _srgb([L, mid * math.cos(h), mid * math.sin(h)])
        if np.all(rgb >= -0.5) and np.all(rgb <= 255.5):
            lo, best = mid, rgb
        else:
            hi = mid
    rgb = _srgb([L, hi * math.cos(h), hi * math.sin(h)])
    if np.all(rgb >= -0.5) and np.all(rgb <= 255.5):
        best = rgb
    return np.clip(best, 0, 255)


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(v)):02x}" for v in rgb[:3])


def _luminance(rgb) -> float:
    c = np.array(rgb[:3], dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


def _contrast(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@tool
def make_palette(base: str, name: str = "primary", apply: bool = False, mode: str | None = None):
    """Build a full colour scale from one colour, like design-system palettes (50 lightest ... 950 darkest).

    Steps are spaced evenly in perceived lightness (OKLCH), keep the base hue, and lower saturation only
    where sRGB cannot show it, so they never shift hue or clip. The step nearest the base is the base itself.
    Returns the scale, which text colour (white or black) reads best on each step with its WCAG contrast,
    and matching accent hues (complement, analogous, triadic) at the same weight.
    apply=true adds the scale to the theme as "<name>-50" ... "<name>-950" (and "<name>" = the base);
    with mode, it goes into that theme mode instead (e.g. a light mode built from a lighter base).
    """
    st = store()
    rgb = parse_color(base, st.theme.get("colors", {}))
    L0, a0, b0 = _oklab(rgb)
    C0, h0 = math.hypot(a0, b0), math.atan2(b0, a0)
    key = slugify(name, "color")
    nearest = min(range(len(_L)), key=lambda i: abs(_L[i] - L0))
    scale: dict[str, str] = {}
    readable: dict[str, str] = {}
    for i, (step, L, share) in enumerate(zip(_STEPS, _L, _C)):
        col = np.array(rgb[:3], dtype=np.float64) if i == nearest else _in_gamut(L, C0 * share / _C[nearest], h0)
        token = f"{key}-{step}"
        scale[token] = _hex(col)
        white, black = _contrast(col, (255, 255, 255)), _contrast(col, (0, 0, 0))
        best, ratio = ("white", white) if white >= black else ("black", black)
        grade = "AAA" if ratio >= 7 else "AA" if ratio >= 4.5 else "AA large" if ratio >= 3 else "fail"
        readable[token] = f"{best} text {ratio:.1f}:1 ({grade})"
    L_mid = _L[nearest]

    def hue(turn: float) -> str:
        return _hex(_in_gamut(L_mid, C0, h0 + math.radians(turn)))

    accents = {"complement": hue(180), "analogous": [hue(-30), hue(30)], "triadic": [hue(120), hue(240)]}
    result: dict[str, Any] = {"base": _hex(rgb), "scale": scale, "text_on": readable, "accents": accents}
    if apply:
        colors = {**scale, key: _hex(rgb)}
        if mode:
            st.set_theme(None, None, False, {mode: colors}, None)
        else:
            st.set_theme(colors, None, False)
        result["applied"] = f"theme mode '{mode}'" if mode else "theme colours"
    return result



_NOT_COLOURS = {"code", "text", "font", "use", "type", "blend", "align", "join", "profile", "space", "path",
                "fit", "anchor", "id", "group", "layer", "clip", "source", "d", "op", "decoration", "lang"}


def _colour_matcher(src: str, colors: dict):
    src = str(src).strip()
    if src.startswith("$"):
        token = src.split("@")[0]
        return lambda value: value.split("@")[0].strip() == token
    target = parse_color(src, colors)[:3]

    def match(value: str) -> bool:
        if value.strip().startswith("$"):
            return False
        try:
            return parse_color(value.split("@")[0], colors)[:3] == target
        except ValueError:
            return False
    return match


def _swap(value: str, dst: str, colors: dict) -> str:
    """Replacement colour, keeping the original's own transparency."""
    if "@" in value:
        return f"{dst.split('@')[0]}@{value.split('@', 1)[1]}"
    try:
        a = parse_color(value, colors)[3]
    except ValueError:
        a = 255
    return dst if a == 255 else f"{dst.split('@')[0]}@{a / 255:.3g}"


def _recolour(node: Any, rules, colors: dict, key: str | None = None) -> tuple[Any, int]:
    if isinstance(node, str):
        if key in _NOT_COLOURS:
            return node, 0
        for match, dst in rules:
            if match(node):
                return _swap(node, dst, colors), 1
        return node, 0
    if isinstance(node, list):
        total, out = 0, []
        for item in node:
            new, n = _recolour(item, rules, colors, key)
            out.append(new)
            total += n
        return out, total
    if isinstance(node, dict):
        total, out = 0, {}
        for k, v in node.items():
            new, n = _recolour(v, rules, colors, k)
            out[k] = new
            total += n
        return out, total
    return node, 0


def _refont(node: Any, fonts: dict) -> tuple[Any, int]:
    if isinstance(node, dict):
        total, out = 0, {}
        for k, v in node.items():
            if k == "font" and isinstance(v, str) and v.lower() in fonts:
                out[k], total = fonts[v.lower()], total + 1
            else:
                out[k], n = _refont(v, fonts)
                total += n
        return out, total
    return node, 0


def _matches(el: dict, where: dict) -> bool:
    for k, v in where.items():
        if k == "ids":
            if el["id"] not in v:
                return False
        elif k == "style":
            s = el.get("style")
            name = s if isinstance(s, str) else (s or {}).get("use") if isinstance(s, dict) else None
            if name != v:
                return False
        elif el.get(k) != v:
            return False
    return True


@tool
def restyle(canvases: list[str] | None = None, replace_colors: dict | None = None, replace_fonts: dict | None = None,
            where: dict | None = None, props: dict | None = None, include_theme: bool = True, dry_run: bool = False,
            replace_text: dict | None = None):
    """Change a whole kit at once, like Figma's "selection colours" and "replace fonts".

    canvases: which canvases (default all). replace_colors: {"#3b82f6": "$primary", "$accent": "$gold"} -
      every fill, stroke, gradient stop, shadow, glow and tint with that colour gets the new one (the
      original transparency is kept); a "$token" key swaps token references. replace_fonts: {"Inter": "Rajdhani"}.
    replace_text: {"Play": "Start", "Gold": "Coins"} - find and replace inside text content (exact substrings).
    where: only elements matching all of {"type", "group", "layer", "ids", "style" (theme style name)}.
    props: element properties to set on every matching element (same as update_element props).
    include_theme: also recolour / refont the theme's named styles. dry_run: only report what would change.
    The whole call is one undo step per canvas.
    """
    st = store()
    colors = st.theme.get("colors", {})
    names = _maybe_json(canvases) or list(st.canvases)
    replace_colors, replace_fonts = _maybe_json(replace_colors) or {}, _maybe_json(replace_fonts) or {}
    where, props = _maybe_json(where) or {}, _maybe_json(props)
    texts = {str(k): str(v) for k, v in (_maybe_json(replace_text) or {}).items() if str(k)}
    if not (replace_colors or replace_fonts or props or texts):
        raise ValueError("give replace_colors, replace_fonts, replace_text or props - otherwise there is nothing to change")
    for dst in replace_colors.values():
        parse_color(dst, colors)
    rules = [(_colour_matcher(src, colors), str(dst)) for src, dst in replace_colors.items()]
    fonts = {str(k).lower(): str(v) for k, v in replace_fonts.items()}
    report: dict[str, Any] = {"canvases": {}, "dry_run": bool(dry_run)}
    for cid in names:
        c = st.get(cid)
        work = copy.deepcopy(c)
        changes, touched = 0, []
        for el in work["elements"]:
            if not _matches(el, where):
                continue
            before = changes
            for k in ("style", "tint", "color", "colors"):
                if k in el and rules:
                    el[k], n = _recolour(el[k], rules, colors, None if k == "style" else k)
                    changes += n
            if fonts:
                if isinstance(el.get("font"), str) and el["font"].lower() in fonts:
                    el["font"], changes = fonts[el["font"].lower()], changes + 1
                if isinstance(el.get("style"), dict):
                    el["style"], n = _refont(el["style"], fonts)
                    changes += n
            if texts and isinstance(el.get("text"), str):
                original = el["text"]
                for old, new in texts.items():
                    el["text"] = el["text"].replace(old, new)
                changes += original != el["text"]
            if props:
                el.update(_prepare_update(el, props))
                changes += 1
            if changes > before:
                touched.append(el["id"])
        if not touched:
            continue
        report["canvases"][c["id"]] = {"changes": changes, "elements": touched}
        if dry_run:
            continue
        st.checkpoint(c)
        try:
            c.clear()
            c.update(work)
            for el in c["elements"]:
                if el["id"] in touched:
                    st._validate(c, el)
        except Exception:
            st.drop_checkpoint(c)
            raise
        st.save_canvas(c)
    if include_theme and (rules or fonts):
        styles = copy.deepcopy(st.theme.get("styles", {}))
        n_theme = 0
        if rules:
            styles, n = _recolour(styles, rules, colors)
            n_theme += n
        if fonts:
            styles, n = _refont(styles, fonts)
            n_theme += n
        if n_theme:
            report["theme_styles_changed"] = n_theme
            if not dry_run:
                st.set_theme(None, styles, False)
    if not report["canvases"] and not report.get("theme_styles_changed"):
        report["note"] = "nothing matched - check the colour / font names, or loosen `where`"
    return report



@tool
def find_elements(canvas: str | None = None, like: str | None = None, type: str | None = None,
                  color: str | None = None, font: str | None = None, text_contains: str | None = None,
                  style: str | None = None, group: str | None = None, layer: str | None = None):
    """Find elements, like Figma's "select matching objects" and layer search (read-only).

    canvas: one canvas (default: every canvas). like: an element id - finds elements of the same type and
    the same look (same style name, or same fill / stroke / font / size). Other filters (all must match):
    type, color (used anywhere in its style, alpha ignored), font, text_contains, style (theme style name),
    group, layer. Returns {canvas: [ids]} to feed restyle(where={"ids": ...}), update or align tools.
    """
    st = store()
    colors = st.theme.get("colors", {})
    names = [canvas] if canvas else list(st.canvases)
    probe = None
    if like:
        if not canvas:
            raise ValueError("like needs the canvas it lives on")
        ref = st.find(st.get(canvas), like)
        rs = resolve_style(ref.get("style"), st.theme)
        probe = (ref["type"], ref.get("style") if isinstance(ref.get("style"), str) else None,
                 repr(rs.get("fill")), repr(rs.get("stroke")), ref.get("font") or rs.get("font"),
                 ref.get("size") or rs.get("size"), ref.get("radius"))
    match_color = _colour_matcher(color, colors) if color else None
    found: dict[str, list[str]] = {}
    for cid in names:
        c = st.get(cid)
        hits = []
        for el in c["elements"]:
            rs = resolve_style(el.get("style"), st.theme)
            if probe is not None:
                key = (el["type"], el.get("style") if isinstance(el.get("style"), str) else None,
                       repr(rs.get("fill")), repr(rs.get("stroke")), el.get("font") or rs.get("font"),
                       el.get("size") or rs.get("size"), el.get("radius"))
                if key != probe:
                    continue
            if type and el["type"] != type:
                continue
            if group and el.get("group") != group:
                continue
            if layer and el.get("layer") != layer:
                continue
            if style and not (el.get("style") == style or (isinstance(el.get("style"), dict)
                                                            and el["style"].get("use") == style)):
                continue
            if font and str(el.get("font") or rs.get("font") or "").lower() != font.lower():
                continue
            if text_contains and text_contains.lower() not in str(el.get("text", "")).lower():
                continue
            if match_color:
                _, n = _recolour({"style": rs, "tint": el.get("tint")}, [(match_color, "#000000")], colors)
                if not n:
                    continue
            hits.append(el["id"])
        if hits:
            found[c["id"]] = hits
    return {"found": found, "count": sum(len(v) for v in found.values())}



_Q = 1024.0


def _ints(polys):
    return [[(round(x * _Q), round(y * _Q)) for x, y in p] for p in polys if len(p) >= 3]


def _floats(polys):
    return [[(x / _Q, y / _Q) for x, y in p] for p in polys]


def _offset(polys, distance: float, join: str):
    import pyclipper
    jt = {"round": pyclipper.JT_ROUND, "miter": pyclipper.JT_MITER, "bevel": pyclipper.JT_SQUARE}[join]
    clean = pyclipper.SimplifyPolygons(_ints(polys), pyclipper.PFT_EVENODD)
    if distance == 0:
        return clean
    po = pyclipper.PyclipperOffset(miter_limit=4.0, arc_tolerance=0.1 * _Q)
    po.AddPaths(clean, jt, pyclipper.ET_CLOSEDPOLYGON)
    return po.Execute(distance * _Q)


def _difference(a, b):
    import pyclipper
    if not a:
        return []
    pc = pyclipper.Pyclipper()
    pc.AddPaths(a, pyclipper.PT_SUBJECT, True)
    if b:
        pc.AddPaths(b, pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def _line_outline(g, res_join: str):
    import pyclipper
    po = pyclipper.PyclipperOffset(arc_tolerance=0.1 * _Q)
    out = []
    for pts, closed, width, cap in g.lines:
        po.Clear()
        end = (pyclipper.ET_CLOSEDLINE if closed else
               pyclipper.ET_OPENROUND if cap == "round" else pyclipper.ET_OPENBUTT)
        po.AddPath([(round(x * _Q), round(y * _Q)) for x, y in pts], pyclipper.JT_ROUND, end)
        out += po.Execute(width / 2 * _Q)
    return pyclipper.SimplifyPolygons(out, pyclipper.PFT_NONZERO) if out else []


def _rdp(points, tol: float):
    """Ramer-Douglas-Peucker on a closed outline."""
    pts = list(points)
    if len(pts) < 4:
        return pts

    def rec(seg):
        (ax, ay), (bx, by) = seg[0], seg[-1]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy) or 1e-12
        best, idx = -1.0, 0
        for i in range(1, len(seg) - 1):
            px, py = seg[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / n
            if d > best:
                best, idx = d, i
        if best <= tol:
            return [seg[0], seg[-1]]
        return rec(seg[:idx + 1])[:-1] + rec(seg[idx:])

    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    return rec(pts[:far + 1])[:-1] + rec(pts[far:] + [pts[0]])[:-1]


def _d(polys) -> str:
    def n(v: float) -> str:
        return f"{v:.3f}".rstrip("0").rstrip(".")
    return " ".join("M" + " L".join(f"{n(x)} {n(y)}" for x, y in p) + " Z" for p in polys if len(p) >= 3)


@tool
def path_ops(canvas: str, id: str, action: str = "flatten", distance: float = 2, join: str = "round",
             keep_original: bool = False, new_id: str | None = None):
    """Figma-style vector operations that turn an element into an editable path.

    action:
      "flatten"        the shape (rect, ellipse, polygon, path, boolean; rotation and skew baked in) becomes
                       one plain path - edit its points, or feed it to boolean_elements.
      "offset"         grow (distance > 0) or shrink (distance < 0) the shape by `distance` units with
                       round / miter / bevel corners: inner panels, even rims, bleed areas, thick outlines.
      "outline_stroke" the element's first stroke (or a line / arc / ticks' own stroke) becomes a filled path
                       painted like the stroke, so it can take gradients, effects and booleans of its own.
      "simplify"       fewer points (distance = how far, in units, the outline may move): lighter paths for
                       vectorised images, SVG imports and traced shapes.
    keep_original: leave the source element as it is (flatten / offset) or keep its stroke (outline_stroke).
    The new path takes the source's style (outline_stroke: the stroke paint as its fill), group and layer.
    """
    st = store()
    c = st.get(canvas)
    el = st.find(c, id)
    act = str(action).lower()
    if act not in ("flatten", "offset", "outline_stroke", "simplify"):
        raise ValueError("action must be 'flatten', 'offset', 'outline_stroke' or 'simplify'")
    if join not in ("round", "miter", "bevel"):
        raise ValueError("join must be 'round', 'miter' or 'bevel'")
    if el["type"] not in VECTOR_TYPES and el["type"] != "text":
        raise ValueError(f"'{id}' is a {el['type']}; path_ops works on shapes, lines and text (not images, instances)")
    style = resolve_style(el.get("style"), st.theme)
    if el["type"] == "text":
        if act not in ("flatten", "offset"):
            raise ValueError("text supports action 'flatten' (text to vector outlines) or 'offset'")
        from .render import TextLayout
        r = st.renderer(c)
        layout = TextLayout(el, style, st.fonts, 4.0, r.text_of(el), r.text_lang(el))
        shape = layout.outline_polys_units()
        rot = float(el.get("rotation", 0) or 0)
        if rot:
            bx = layout.box_units()
            cx, cy = r._pivot(el, bx)
            cs, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            shape = [[(cx + (x - cx) * cs - (y - cy) * sn, cy + (x - cx) * sn + (y - cy) * cs) for x, y in p] for p in shape]
        import pyclipper
        merged = pyclipper.SimplifyPolygons(_ints(shape), pyclipper.PFT_NONZERO)
        polys = merged if act == "flatten" else _offset(_floats(merged), float(distance), join)
        keep_keys = ("fill", "stroke", "shadow", "glow", "inner_shadow", "inner_glow", "bevel", "light", "pbr",
                     "material", "noise", "texture", "opacity", "blend", "blur", "mask", "adjust")
        new_style = {k: v for k, v in style.items() if k in keep_keys} or {"fill": "#ffffff"}
        replace_source = not keep_original
    elif el["type"] in LINE_TYPES:
        if act != "outline_stroke":
            raise ValueError(f"'{id}' is a {el['type']} (a stroke): use action='outline_stroke' to turn it into a shape")
        polys = _line_outline(vector_geometry(el, 8.0), join)
        new_style = {k: v for k, v in style.items() if k not in ("stroke",)}
        replace_source = not keep_original
    else:
        shape = _placed_polys(el, 8.0)
        if act == "flatten":
            polys = _offset(shape, 0, join)
            new_style = el.get("style")
        elif act == "offset":
            polys = _offset(shape, float(distance), join)
            new_style = el.get("style")
        elif act == "simplify":
            tol = max(0.01, abs(float(distance)))
            polys = _ints([q for q in (_rdp(p, tol) for p in shape) if len(q) >= 3])
            new_style = el.get("style")
        else:
            strokes = _stroke_specs(style, st.theme.get("colors", {}))
            if not strokes:
                raise ValueError(f"'{id}' has no stroke to outline - give it style.stroke first")
            sp = strokes[0]
            outer = _offset(shape, sp["d1"], sp["join"] or join)
            inner = _offset(shape, sp["d0"], sp["join"] or join)
            polys = _difference(outer, inner)
            new_style = {"fill": sp["paint"]}
        replace_source = act != "outline_stroke" and not keep_original
    polys = _floats(polys)
    if not polys:
        raise ValueError("the operation left nothing (a shrink larger than the shape?) - use a smaller distance")
    props = {"d": _d(polys), "fill_rule": "evenodd", "id": new_id or None, "group": el.get("group"),
             "layer": el.get("layer"), "style": copy.deepcopy(new_style)}
    st.checkpoint(c)
    try:
        index = c["elements"].index(el)
        made, warnings = st.add_element(c, "path", {k: v for k, v in props.items() if v is not None}, checkpoint=False)
        c["elements"].remove(made)
        if replace_source:
            c["elements"][index] = made
        else:
            c["elements"].insert(index + 1, made)
            if act == "outline_stroke" and not keep_original and el["type"] not in LINE_TYPES:
                base = el.get("style")
                el["style"] = ({"use": base} if isinstance(base, str) else dict(base or {}))
                el["style"]["stroke"] = None
            elif act == "outline_stroke" and not keep_original:
                c["elements"].remove(el)
    except Exception:
        st.drop_checkpoint(c)
        raise
    st.save_canvas(c)
    out = _summary(st, c, made, warnings)
    out["points"] = sum(len(p) for p in polys)
    return out



@tool
def vectorize_image(canvas: str, path: str, x: float = 0, y: float = 0, width: float | None = None,
                    colors: int = 6, detail: float = 1.0, smooth: int = 1, group: str | None = None,
                    layer: str | None = None):
    """Turn a picture (logo, sketch, icon, flat illustration, pixel art) into editable vector paths, like
    Figma's "vectorize": the colours are reduced to `colors` (2-32), each colour region becomes one path
    (holes kept), largest first. detail 0.5-2 sets how finely edges are followed; smooth 0-3 rounds
    corners (0 keeps pixel-art steps). The paths land at x, y, scaled to `width` (default: the image width),
    in one group so they move together; then restyle, boolean, light or animate them like any shape.
    Works best on flat art; photos become posterised shapes.
    """
    from pathlib import Path as _Path
    from PIL import Image as _PIL
    from .vectorize import trace
    st = store()
    c = st.get(canvas)
    src = _Path(path).expanduser()
    if not src.is_file():
        raise ValueError(f"image not found: {src.resolve()} - use an absolute path")
    try:
        img = _PIL.open(src)
        img.load()
    except Exception as exc:
        raise ValueError(f"could not open {src.name} as an image: {exc}") from exc
    regions = trace(img, colors, max(0.25, min(2.0, float(detail))), max(0, min(3, int(smooth))))
    if not regions:
        raise ValueError("nothing to trace (the image is empty or fully transparent)")
    s = float(width) / img.width if width else 1.0
    grp = slugify(group or f"vector_{src.stem}", "vector")
    st.checkpoint(c)
    made = []
    try:
        for i, (rgba, polys, _) in enumerate(regions):
            d = " ".join("M" + " L".join(f"{x + px * s:.2f} {y + py * s:.2f}" for px, py in poly) + " Z" for poly in polys)
            props = {"d": d, "fill_rule": "evenodd", "group": grp, "style": {"fill": "#%02x%02x%02x" % rgba[:3]},
                     "id": f"{grp}_{i + 1}"}
            if layer:
                props["layer"] = layer
            el, _ = st.add_element(c, "path", props, checkpoint=False)
            made.append(el["id"])
    except Exception:
        st.drop_checkpoint(c)
        raise
    st.save_canvas(c)
    return {"group": grp, "paths": made, "colors": ["#%02x%02x%02x" % r[0][:3] for r in regions],
            "size": [round(img.width * s, 2), round(img.height * s, 2)]}


_PAIRS = [("Rajdhani", "Inter"), ("Bebas Neue", "Barlow Condensed"), ("Cinzel", "Inter"), ("Fredoka", "Fredoka"),
          ("Orbitron", "JetBrains Mono"), ("Michroma", "Barlow Condensed"), ("Bangers", "Fredoka")]
_SKIP = {"id", "text", "font", "path", "code", "d", "group", "layer", "source", "type", "anchor", "name", "note"}


def _hue(value: str, colors: dict, degrees: float, sat: float) -> str:
    import colorsys
    r, g, b, a = parse_color(value, colors)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    r2, g2, b2 = colorsys.hls_to_rgb((h + degrees / 360) % 1, l, max(0.0, min(1.0, s * sat)))
    out = f"#{round(r2 * 255):02x}{round(g2 * 255):02x}{round(b2 * 255):02x}"
    return out + (f"{a:02x}" if a < 255 else "")


def _recolor_all(obj: Any, colors: dict, degrees: float, sat: float) -> Any:
    if isinstance(obj, dict):
        return {k: v if k in _SKIP else _recolor_all(v, colors, degrees, sat) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_recolor_all(v, colors, degrees, sat) for v in obj]
    if isinstance(obj, str) and obj.lower().startswith(("#", "rgb", "hsl")):
        try:
            return _hue(obj, colors, degrees, sat)
        except ValueError:
            return obj
    return obj


@tool
def make_variations(canvas: str, count: int = 3, vary: list[str] | None = None, seed: int = 1):
    """Explore design alternatives in one go: `count` copies of a canvas named <canvas>_v1, _v2..., each
    with a different direction, plus a contact sheet comparing them with the original.

    vary (default all): "palette" (hue-shifted colour scheme - theme tokens are overridden on the copy only,
      hand-typed colours are shifted too), "shape" (sharp / round / cut corners and lighter / heavier
      strokes), "type" (a different display + body font pairing; big text gets the display font).
    seed changes which directions are picked. Look at the sheet, keep the copy you like (continue editing
    it, or copy what works back), and delete the others with delete_canvas."""
    import random
    from .server import contact_sheet
    st = store()
    src = st.get(canvas)
    vary = _maybe_json(vary) or ["palette", "shape", "type"]
    vary = [vary] if isinstance(vary, str) else list(vary)
    bad = set(vary) - {"palette", "shape", "type"}
    if bad:
        raise ValueError(f"vary takes palette, shape, type (got {', '.join(sorted(bad))})")
    count = max(1, min(8, int(count)))
    rng = random.Random(seed)
    theme_colors = {**st.theme.get("colors", {}), **(src.get("colors") or {})}
    sizes = [float(e.get("size") or 0) for e in src["elements"] if e["type"] == "text"]
    big = max(sizes) * 0.7 if sizes else 0
    shapes = [(0.3, "round", 1.0), (2.0, "round", 1.6), (1.0, "cut", 1.0), (1.5, "round", 0.6), (0.0, "round", 2.0)]
    made, notes = [], []
    for i in range(count):
        name = f"{src['id']}_v{i + 1}"
        if name in st.canvases:
            raise ValueError(f"canvas '{name}' already exists - delete it or pass another seed / canvas")
        clone = st.duplicate_canvas(src, name)
        desc = []
        if "palette" in vary:
            deg = (i + 1) * 360 / (count + 1) + rng.uniform(-15, 15)
            sat = rng.uniform(0.85, 1.25)
            clone["elements"] = _recolor_all(clone["elements"], theme_colors, deg, sat)
            over = {}
            for k, v in theme_colors.items():
                if isinstance(v, str) and not v.startswith("$"):
                    try:
                        over[k] = _hue(v, theme_colors, deg, sat)
                    except ValueError:
                        pass
            clone["colors"] = over
            if clone.get("background") and isinstance(clone["background"], (str, dict)):
                clone["background"] = _recolor_all(clone["background"], theme_colors, deg, sat)
            desc.append(f"hue {round(deg)}")
        if "shape" in vary:
            mult, corner, stroke = shapes[(i + seed) % len(shapes)]
            for el in clone["elements"]:
                if el["type"] in ("rect", "image", "instance") and isinstance(el.get("radius"), (int, float)):
                    r = float(el["radius"]) * mult if corner == "round" else max(6.0, float(el["radius"]))
                    el["radius"] = round(min(r, min(float(el.get("width") or r * 2), float(el.get("height") or r * 2)) / 2), 2)
                    if el["type"] == "rect":
                        el["corner"] = corner
                sty = el.get("style")
                if isinstance(sty, dict) and isinstance(sty.get("stroke"), dict) and                         isinstance(sty["stroke"].get("width"), (int, float)):
                    sty["stroke"] = {**sty["stroke"], "width": round(float(sty["stroke"]["width"]) * stroke, 2)}
            desc.append(f"{corner} corners x{mult:g}, strokes x{stroke:g}")
        if "type" in vary and sizes:
            display, body = _PAIRS[(i + seed) % len(_PAIRS)]
            for el in clone["elements"]:
                if el["type"] == "text":
                    el["font"] = display if float(el.get("size") or 0) >= big else body
            desc.append(f"{display} + {body}")
        st.save_canvas(clone)
        made.append(clone["id"])
        notes.append({"canvas": clone["id"], "direction": ", ".join(desc)})
    sheet = contact_sheet([src["id"]] + made, columns=min(4, count + 1))
    info = json.loads(sheet[1])
    info["variations"] = notes
    return [sheet[0], json.dumps(info)]
