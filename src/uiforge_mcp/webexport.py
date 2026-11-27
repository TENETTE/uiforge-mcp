"""Website export: canvases become real HTML / CSS pages.

Rects and ellipses become CSS boxes (gradients, borders as box-shadows, shadows, backdrop-filter), text
stays live, selectable text with the fonts copied next to it, other shapes become inline SVG, and only
what the web cannot draw the same way becomes a picture. Links navigate between pages (or open an
overlay), hover / pressed / focused states become CSS, transform and opacity tracks become CSS keyframe
animations, matching element ids animate between pages (View Transitions, Figma "smart animate"), and
pins become responsive anchors.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .animation import apply_animation
from .colors import parse_color
from .render import (LINE_TYPES, TextLayout, _is_fill_stack, _is_none, _scales, _stroke_specs, apply_state,
                     resolve_style)
from . import svgexport

_CSS_KEYS = {"fill", "stroke", "opacity", "shadow", "glow", "inner_shadow", "inner_glow", "blend", "blur",
             "backdrop_blur", "use", "bevel", "adjust", "mask", "mask_mode"}
_TEXT_KEYS = _CSS_KEYS | {"font", "weight", "size", "letter_spacing", "line_height", "uppercase", "italic", "case",
                          "features", "axes", "paragraph_spacing", "indent", "trim"}
_BLENDS = {"multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light",
           "soft-light", "difference"}
_STATE_PSEUDO = {"hover": ":hover", "pressed": ":active", "focused": ":focus-within"}


def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def _ident(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", str(text)) or "x"


class _Ctx:
    def __init__(self, r, theme: dict, out: Path, scale: float) -> None:
        self.r, self.theme, self.out, self.scale = r, theme, out, scale
        self.colors = r.colors
        self.notes: set[str] = set()
        self.raster: list[str] = []
        self.fonts: dict[str, tuple[str, int, bool]] = {}

    def color(self, value: Any) -> str:
        """CSS colour; theme tokens stay live as var(--color-x, fallback) so modes switch them."""
        text = str(value).strip()
        r, g, b, a = parse_color(value, self.colors)
        literal = f"#{r:02x}{g:02x}{b:02x}" if a == 255 else f"rgba({r}, {g}, {b}, {_n(a / 255)})"
        if text.startswith("$") and "@" not in text:
            return f"var(--color-{_ident(text[1:])}, {literal})"
        return literal

    def stops(self, raw: list) -> list[tuple[float, str]]:
        n = len(raw)
        out = []
        for i, item in enumerate(raw):
            if isinstance(item, dict):
                off, col = item.get("offset", i / (n - 1)), item.get("color")
            elif isinstance(item, (list, tuple)) and len(item) == 2 and not isinstance(item[1], (int, float)):
                off, col = item
            else:
                off, col = i / (n - 1), item
            out.append((float(off), self.color(col)))
        return sorted(out)

    def paint(self, spec: Any, w: float, h: float) -> str | None:
        """A CSS background layer for a fill, or None if CSS cannot draw it the same way."""
        if _is_none(spec):
            return None
        if not isinstance(spec, dict):
            c = self.color(spec)
            return f"linear-gradient({c}, {c})"
        kind = str(spec.get("type", "linear")).lower()
        raw = spec.get("stops") or spec.get("colors") or ([spec["from"], spec["to"]] if "from" in spec else None)
        if kind in ("linear", "radial", "conic") and raw and len(raw) >= 2:
            st = self.stops(raw)
            if kind == "linear":
                deg = float(spec.get("angle", 90)) + 90
                return f"linear-gradient({_n(deg)}deg, " + ", ".join(f"{c} {_n(o * 100)}%" for o, c in st) + ")"
            cx, cy = float(spec.get("cx", 0.5)) * 100, float(spec.get("cy", 0.5)) * 100
            if kind == "radial":
                rad = float(spec.get("r", 0.5))
                rx, ry = (max(w, h) * rad,) * 2 if spec.get("circle") else (w * rad, h * rad)
                return (f"radial-gradient(ellipse {_n(rx)}px {_n(ry)}px at {_n(cx)}% {_n(cy)}%, "
                        + ", ".join(f"{c} {_n(o * 100)}%" for o, c in st) + ")")
            a0 = float(spec.get("from", 0))
            span = float(spec.get("to", a0 + 360)) - a0
            return (f"conic-gradient(from {_n(a0 + 90)}deg at {_n(cx)}% {_n(cy)}%, "
                    + ", ".join(f"{c} {_n(o * abs(span))}deg" for o, c in st) + ")")
        if kind == "stripes":
            size = float(spec.get("size", 8))
            ratio = max(0.02, min(0.98, float(spec.get("ratio", 0.5))))
            c1, c2 = self.color(spec.get("color", "#ffffff@0.15")), self.color(spec.get("color2", "transparent"))
            deg = float(spec.get("angle", 45)) + 90
            return (f"repeating-linear-gradient({_n(deg)}deg, {c1} 0 {_n(size * ratio)}px, "
                    f"{c2} {_n(size * ratio)}px {_n(size)}px)")
        return None

    def shadows(self, st: dict, stroke: dict | None) -> list[str] | None:
        out: list[str] = []
        if stroke:
            w, col = stroke["width"], self.color(stroke["paint"])
            if stroke["align"] == "inside":
                out.append(f"inset 0 0 0 {_n(w)}px {col}")
            elif stroke["align"] == "outside":
                out.append(f"0 0 0 {_n(w)}px {col}")
            else:
                out += [f"inset 0 0 0 {_n(w / 2)}px {col}", f"0 0 0 {_n(w / 2)}px {col}"]
        for key, inset in (("inner_shadow", True), ("inner_glow", True), ("shadow", False), ("glow", False)):
            items = st.get(key)
            if _is_none(items):
                continue
            for spec in (items if isinstance(items, list) and items and isinstance(items[0], dict) else [items]):
                if spec is True:
                    spec = {}
                if not isinstance(spec, dict):
                    spec = {"color": spec}
                if spec.get("knockout") or float(spec.get("strength", 1)) != 1:
                    return None
                glow = key in ("glow", "inner_glow")
                default = "#ffffff" if glow else "#000000@0.5"
                col = self.color(spec.get("color", default))
                blur = float(spec.get("blur", 12 if glow else 8))
                dx = 0.0 if glow else float(spec.get("dx", 0))
                dy = 0.0 if glow else float(spec.get("dy", 4 if key == "shadow" else 2))
                out.append(f"{'inset ' if inset else ''}{_n(dx)}px {_n(dy)}px {_n(blur)}px {_n(float(spec.get('spread', 0)))}px {col}")
        bevel = st.get("bevel")
        if bevel:
            b = bevel if isinstance(bevel, dict) else {}
            size = float(b.get("size", 2))
            out += [f"inset 0 {_n(size)}px {_n(size)}px {self.color(b.get('highlight', '#ffffff@0.35'))}",
                    f"inset 0 {_n(-size)}px {_n(size)}px {self.color(b.get('shadow', '#000000@0.35'))}"]
        return out

    def font_face(self, layout: TextLayout) -> str:
        family = re.sub(r"[^\w \-]", "", str(layout.family or "Inter")) or "Inter"
        if not layout.path:
            return f"'{family}', system-ui, sans-serif"
        src = Path(layout.path)
        variable = layout.var_weight is not None
        css_name = f"{family}" if variable else f"{family} {layout.weight}"
        if css_name not in self.fonts:
            fonts = self.out / "assets" / "fonts"
            fonts.mkdir(parents=True, exist_ok=True)
            target = fonts / src.name
            if not target.exists():
                shutil.copyfile(src, target)
                for lic in ("OFL.txt", "LICENSE", "LICENSE.txt"):
                    if (src.parent / lic).is_file() and not (fonts / f"{src.stem}-{lic}").exists():
                        shutil.copyfile(src.parent / lic, fonts / f"{src.stem}-{lic}")
            self.fonts[css_name] = (src.name, layout.weight, variable)
        return f"'{css_name}', system-ui, sans-serif"


def _box_css(left: float, top: float, w: float, h: float) -> dict:
    return {"left": f"{_n(left)}px", "top": f"{_n(top)}px", "width": f"{_n(w)}px", "height": f"{_n(h)}px"}


def _transform(el: dict, box, pivot) -> dict:
    parts = []
    rot = float(el.get("rotation", 0) or 0)
    if rot:
        parts.append(f"rotate({_n(rot)}deg)")
    sx, sy = _scales(el)
    if sx != 1 or sy != 1:
        parts.append(f"scale({_n(sx)}, {_n(sy)})")
    skew = float(el.get("skew", 0) or 0)
    if skew and el["type"] != "text":
        parts.append(f"skewX({_n(-skew)}deg)")
    if not parts:
        return {}
    return {"transform": " ".join(parts),
            "transform-origin": f"{_n(pivot[0] - box[0])}px {_n(pivot[1] - box[1])}px"}


def _style_css(ctx: _Ctx, el: dict, st: dict, w: float, h: float, text: bool = False) -> dict | None:
    """CSS for fills, borders, shadows and filters - None if any part needs the picture fallback."""
    css: dict[str, str] = {}
    fills = st.get("fill", "#ffffff" if not st.get("stroke") else None) if not text else None
    if fills is not None:
        layers = []
        for one in (fills if _is_fill_stack(fills) else [fills]):
            if isinstance(one, dict) and "blend" in one:
                return None
            p = ctx.paint(one, w, h)
            if p is None and not _is_none(one):
                return None
            if p:
                layers.append(p)
        if layers:
            css["background"] = ", ".join(reversed(layers))
    strokes = _stroke_specs(st, ctx.colors) if not text else []
    if len(strokes) > 1 or any(s["dash"] or s["offset"] or s["sides"] or isinstance(s["paint"], dict) for s in strokes):
        return None
    shadows = ctx.shadows(st, strokes[0] if strokes else None) if not text else []
    if shadows is None:
        return None
    if shadows:
        css["box-shadow"] = ", ".join(shadows)
    if float(st.get("opacity", 1)) < 1:
        css["opacity"] = _n(float(st["opacity"]))
    blend = str(st.get("blend", "normal")).lower()
    if blend != "normal":
        if blend not in _BLENDS:
            return None
        css["mix-blend-mode"] = blend
    filters = []
    if st.get("blur"):
        if isinstance(st["blur"], dict):
            return None
        filters.append(f"blur({_n(float(st['blur']) / 2)}px)")
    adj = st.get("adjust")
    if adj:
        if not isinstance(adj, dict) or set(adj) - {"brightness", "contrast", "saturation", "hue", "invert"}:
            return None
        if adj.get("brightness"):
            filters.append(f"brightness({_n(1 + float(adj['brightness']))})")
        if adj.get("contrast"):
            filters.append(f"contrast({_n(1 + float(adj['contrast']))})")
        if adj.get("saturation"):
            filters.append(f"saturate({_n(1 + float(adj['saturation']))})")
        if adj.get("hue"):
            filters.append(f"hue-rotate({_n(float(adj['hue']))}deg)")
        if adj.get("invert"):
            filters.append("invert(1)")
    if filters:
        css["filter"] = " ".join(filters)
    if st.get("backdrop_blur"):
        bb = st["backdrop_blur"]
        radius = float(bb.get("radius", 8)) if isinstance(bb, dict) else float(bb)
        if isinstance(bb, dict):
            ctx.notes.add("progressive background blur is a uniform backdrop-filter on the web")
        css["backdrop-filter"] = css["-webkit-backdrop-filter"] = f"blur({_n(radius / 2)}px)"
    if not _is_none(st.get("mask")):
        if str(st.get("mask_mode", "alpha")) != "alpha":
            return None
        m = ctx.paint(st["mask"], w, h)
        if m is None:
            return None
        css["-webkit-mask-image"] = css["mask-image"] = m
    return css


def _text_html(ctx: _Ctx, el: dict, st: dict) -> tuple[str, dict] | None:
    r = ctx.r
    if el.get("arc") or el.get("path"):
        return None
    if set(st) - _TEXT_KEYS:
        return None
    layout = TextLayout(el, st, r.fonts, 1.0, r.text_of(el), r.text_lang(el))
    if layout.shaper and any(layout.shaper.color_runs.get(line) for line, _ in layout.lines):
        ctx.notes.add("colour emoji are left to the browser's emoji font")
    x0, y0, x1, y1 = layout.box_px
    lh = layout.size * layout.line_height
    top = layout.baselines[0] - (lh - (layout.ascent + layout.descent)) / 2 - layout.ascent
    css: dict[str, str] = {"left": f"{_n(x0)}px", "top": f"{_n(top)}px", "font-family": ctx.font_face(layout),
                           "font-size": f"{_n(layout.size)}px", "font-weight": str(layout.weight),
                           "line-height": f"{_n(lh)}px", "text-align": layout.align,
                           "white-space": "pre-wrap" if el.get("max_width") else "pre"}
    if el.get("max_width"):
        css["width"] = f"{_n(float(el['max_width']))}px"
    if layout.spacing:
        css["letter-spacing"] = f"{_n(layout.spacing)}px"
    if bool(el.get("italic", st.get("italic"))):
        css["font-style"] = "italic"
    fill = st.get("fill", el.get("fill", "#ffffff"))
    if isinstance(fill, dict):
        p = ctx.paint(fill, x1 - x0, y1 - y0)
        if p is None:
            return None
        css.update({"background": p, "-webkit-background-clip": "text", "background-clip": "text", "color": "transparent"})
    elif _is_fill_stack(fill):
        return None
    else:
        css["color"] = ctx.color(fill)
    strokes = _stroke_specs(st, ctx.colors)
    if len(strokes) > 1 or (strokes and isinstance(strokes[0]["paint"], dict)):
        return None
    if strokes:
        css["-webkit-text-stroke"] = f"{_n(strokes[0]['width'] * 2)}px {ctx.color(strokes[0]['paint'])}"
        css["paint-order"] = "stroke fill"
    shadows = []
    for key in ("shadow", "glow"):
        items = st.get(key)
        if _is_none(items):
            continue
        for spec in (items if isinstance(items, list) and items and isinstance(items[0], dict) else [items]):
            spec = spec if isinstance(spec, dict) else ({} if spec is True else {"color": spec})
            glow = key == "glow"
            col = ctx.color(spec.get("color", "#ffffff" if glow else "#000000@0.5"))
            shadows.append(f"{_n(0 if glow else float(spec.get('dx', 0)))}px {_n(0 if glow else float(spec.get('dy', 4)))}px "
                           f"{_n(float(spec.get('blur', 12 if glow else 8)))}px {col}")
    if shadows:
        css["text-shadow"] = ", ".join(shadows)
    case = str(el.get("case", st.get("case")) or "").lower()
    upper = el.get("uppercase", st.get("uppercase"))
    if upper or case in ("upper", "tr-upper"):
        css["text-transform"] = "uppercase"
    elif case in ("lower", "tr-lower"):
        css["text-transform"] = "lowercase"
    elif case in ("title", "capitalize"):
        css["text-transform"] = "capitalize"
    elif case in ("small-caps", "all-small-caps"):
        css["font-variant-caps"] = case
    if layout.decoration != "none":
        css["text-decoration"] = "underline" if layout.decoration == "underline" else "line-through"
    if layout.features:
        css["font-feature-settings"] = ", ".join(f"'{k}' {v}" for k, v in layout.features.items())
    if layout.axes:
        css["font-variation-settings"] = ", ".join(f"'{k}' {_n(v)}" for k, v in layout.axes)
    if el.get("max_lines"):
        css.update({"display": "-webkit-box", "-webkit-box-orient": "vertical",
                    "-webkit-line-clamp": str(int(el["max_lines"])), "overflow": "hidden"})
    if float(st.get("opacity", 1)) < 1:
        css["opacity"] = _n(float(st["opacity"]))
    raw = r.text_of(el)
    lang = layout.lang or ("tr" if str(upper).lower() == "tr" or case.startswith("tr") else None)
    attrs = f' lang="{html.escape(lang)}"' if lang else ""
    list_style = str(el.get("list") or "none")
    para_gap = float(el.get("paragraph_spacing", st.get("paragraph_spacing", 0)) or 0)
    indent = float(el.get("indent", st.get("indent", 0)) or 0)
    paras = raw.split("\n")
    if list_style in ("bullet", "number"):
        tag = "ul" if list_style == "bullet" else "ol"
        css.update({"margin": "0", "padding-left": "1.3em", "white-space": "normal"})
        items = "".join(f'<li style="margin-bottom:{_n(para_gap)}px">{html.escape(p)}</li>' for p in paras if p.strip())
        return f"<{tag}{attrs}>{items}</{tag}>", css
    if para_gap or indent:
        body = "".join(f'<p style="margin:0 0 {_n(para_gap)}px 0;text-indent:{_n(indent)}px">{html.escape(p)}</p>'
                       for p in paras)
        return f"<div{attrs}>{body}</div>", css
    return f"<div{attrs}>{html.escape(raw)}</div>", css


def _element(ctx: _Ctx, el: dict, svg_doc) -> tuple[str, dict, str] | None:
    """(tag-body, css, kind) for one element, or None for the picture fallback."""
    r = ctx.r
    el = r._nums(el)
    st = r._nums(resolve_style(el.get("style"), ctx.theme))
    if el.get("clip") or st.get("glass") or st.get("texture") or st.get("light") or st.get("pbr") or st.get("noise"):
        return None
    t = el["type"]
    if t == "text":
        got = _text_html(ctx, el, st)
        if got is None:
            return None
        inner, css = got
        return inner, css, "text"
    if t in ("rect", "ellipse"):
        if set(st) - _CSS_KEYS:
            return None
        if t == "rect" and (str(el.get("corner", "round")) == "cut" or el.get("smoothing")):
            return _svg(ctx, el, st, svg_doc)
        box = r._geom_box(el, st)
        w, h = box[2] - box[0], box[3] - box[1]
        css = _style_css(ctx, el, st, w, h)
        if css is None:
            return None
        css.update(_box_css(box[0], box[1], w, h))
        if t == "ellipse":
            css["border-radius"] = "50%"
        elif el.get("radius"):
            rad = el["radius"]
            css["border-radius"] = " ".join(f"{_n(float(v))}px" for v in (rad if isinstance(rad, list) else [rad]))
        css.update(_transform(el, box, r._pivot(el, box)))
        return "", css, "box"
    if t == "image":
        box = r._geom_box(el, st)
        if set(st) - _CSS_KEYS or el.get("crop") or el.get("tint"):
            return None
        src = Path(str(el.get("path", ""))).expanduser()
        if not src.is_file():
            return None
        assets = ctx.out / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        name = f"{_ident(el['id'])}{src.suffix.lower()}"
        shutil.copyfile(src, assets / name)
        css = _style_css(ctx, el, {k: v for k, v in st.items() if k != "fill"}, box[2] - box[0], box[3] - box[1]) or {}
        css.update(_box_css(box[0], box[1], box[2] - box[0], box[3] - box[1]))
        css["object-fit"] = {"contain": "contain", "cover": "cover"}.get(str(el.get("fit", "stretch")), "fill")
        if el.get("radius"):
            css["border-radius"] = f"{_n(float(el['radius'] if not isinstance(el['radius'], list) else el['radius'][0]))}px"
        css.update(_transform(el, box, r._pivot(el, box)))
        return f'assets/{name}', css, "img"
    if t == "input":
        from .widgets import widget_colors_summary
        wc = widget_colors_summary(el, ctx.colors)
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = max(16.0, float(el.get("width", 220))), max(20.0, float(el.get("height", 40)))
        rad = el.get("radius", 8)
        rad_css = " ".join(f"{_n(float(v))}px" for v in (rad if isinstance(rad, list) else [rad]))
        bg_r, bg_g, bg_b, bg_a = wc["bg"]
        bd_r, bd_g, bd_b, bd_a = wc["border"]
        tx_r, tx_g, tx_b, tx_a = wc["text"]
        css = {
            **_box_css(x, y, w, h),
            "background": f"rgba({bg_r},{bg_g},{bg_b},{_n(bg_a / 255)})",
            "border": f"{_n(wc['border_width'])}px solid rgba({bd_r},{bd_g},{bd_b},{_n(bd_a / 255)})",
            "border-radius": rad_css,
            "color": f"rgba({tx_r},{tx_g},{tx_b},{_n(tx_a / 255)})",
            "font-family": f"'{el.get('font') or 'Inter'}',sans-serif",
            "font-size": f"{_n(float(el.get('size', 15)))}px",
            "padding": f"0 {_n(float(el.get('padding', 12)))}px",
            "outline": "none",
        }
        itype = html.escape(str(el.get("input_type", "text")).lower(), quote=True)
        val = html.escape(str(el.get("value") or ""), quote=True)
        ph = html.escape(str(el.get("placeholder") or ""), quote=True)
        attrs = [f'type="{itype}"', f'defaultValue="{val}"' if False else f'value="{val}"']
        if ph:
            attrs.append(f'placeholder="{ph}"')
        if el.get("bind"):
            attrs.append(f'data-bind="{html.escape(str(el["bind"]), quote=True)}"')
        if el.get("max_length"):
            attrs.append(f'maxlength="{int(el["max_length"])}"')
        if el.get("readonly"):
            attrs.append("readonly")
        return " ".join(attrs), css, "input"
    if t == "scroll":
        from .widgets import widget_colors_summary
        wc = widget_colors_summary(el, ctx.colors)
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = max(16.0, float(el.get("width", 280))), max(20.0, float(el.get("height", 220)))
        rad = el.get("radius", 10)
        rad_css = " ".join(f"{_n(float(v))}px" for v in (rad if isinstance(rad, list) else [rad]))
        bg_r, bg_g, bg_b, bg_a = wc["bg"]
        bd_r, bd_g, bd_b, bd_a = wc["border"]
        d = str(el.get("direction", "vertical")).lower()
        css = {
            **_box_css(x, y, w, h),
            "background": f"rgba({bg_r},{bg_g},{bg_b},{_n(bg_a / 255)})",
            "border": f"{_n(wc['border_width'])}px solid rgba({bd_r},{bd_g},{bd_b},{_n(bd_a / 255)})",
            "border-radius": rad_css,
            "padding": f"{_n(float(el.get('padding', 10)))}px",
            "display": "flex",
            "flex-direction": "row" if d == "horizontal" else "column",
            "gap": f"{_n(float(el.get('gap', 8)))}px",
            "overflow-y": "hidden" if d == "horizontal" else "auto",
            "overflow-x": "auto" if d in ("horizontal", "both") else "hidden",
            "font-family": f"'{el.get('font') or 'Inter'}',sans-serif",
            "scrollbar-width": "thin",
            "scrollbar-color": f"{ctx.color(el.get('scrollbar_color', '#94a3b8@0.58'))} transparent",
        }
        row_h = float(el.get("item_height", 38))
        ifill = ctx.color(el.get("item_fill", "#1e293b@0.75"))
        icol = ctx.color(el.get("item_color", "#e2e8f0"))
        scol = ctx.color(el.get("subtitle_color", "#94a3b8"))
        fsize = float(el.get("size", 13))
        parts_html = []
        for i, raw_item in enumerate(el.get("items") or []):
            if isinstance(raw_item, dict):
                title = str(raw_item.get("title") or raw_item.get("label") or f"Item {i + 1}")
                sub = str(raw_item.get("subtitle") or "")
                badge = str(raw_item.get("badge") or "")
            else:
                title, sub, badge = str(raw_item), "", ""
            sub_h = f'<div style="font-size:{_n(max(10.0, fsize * 0.82))}px;color:{scol}">{html.escape(sub)}</div>' if sub else ""
            bdg_h = f'<span style="margin-left:auto;color:#38bdf8;font-weight:700;font-size:{_n(max(10.0, fsize * 0.85))}px">{html.escape(badge)}</span>' if badge else ""
            parts_html.append(
                f'<div class="scroll-item" style="min-height:{_n(row_h)}px;flex:0 0 auto;border-radius:6px;background:{ifill};'
                f'color:{icol};font-size:{_n(fsize)}px;padding:6px 10px;display:flex;align-items:center;gap:8px">'
                f'<div><div style="font-weight:600">{html.escape(title)}</div>{sub_h}</div>{bdg_h}</div>'
            )
        return "".join(parts_html), css, "scroll"
    if t == "slider":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = max(16.0, float(el.get("width", 220))), max(16.0, float(el.get("height", 28)))
        lo, hi = float(el.get("min", 0.0)), float(el.get("max", 100.0))
        val = float(el.get("value", 50.0))
        step = float(el.get("step", 1.0))
        fill_col = ctx.color(el.get("fill_color", "#38bdf8"))
        track_col = ctx.color(el.get("track_color", "#1e293b"))
        css = {**_box_css(x, y, w, h), "accent-color": fill_col, "--fill-col": fill_col,
               "--track-col": track_col, "cursor": "pointer", "margin": "0"}
        attrs = ['type="range"', f'min="{_n(lo)}"', f'max="{_n(hi)}"', f'step="{_n(step)}"', f'value="{_n(val)}"']
        if el.get("bind"):
            attrs.append(f'data-bind="{html.escape(str(el["bind"]), quote=True)}"')
        return " ".join(attrs), css, "slider"
    if t == "toggle":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = max(16.0, float(el.get("width", 52))), max(16.0, float(el.get("height", 28)))
        variant = str(el.get("variant", "switch")).lower()
        on_col = ctx.color(el.get("on_color", "#22c55e"))
        off_col = ctx.color(el.get("off_color", "#334155"))
        thumb_col = ctx.color(el.get("thumb_color", "#ffffff"))
        if variant == "checkbox":
            box_s = min(w, h)
            css = {**_box_css(x, y + (h - box_s) * 0.5, box_s, box_s), "accent-color": on_col, "cursor": "pointer", "margin": "0"}
            kind = "input"
        else:
            css = {**_box_css(x, y, w, h), "--on-col": on_col, "--off-col": off_col, "--thumb-col": thumb_col,
                   "cursor": "pointer", "margin": "0"}
            kind = "switch"
        attrs = ['type="checkbox"']
        if el.get("checked"):
            attrs.append("checked")
        if el.get("bind"):
            attrs.append(f'data-bind="{html.escape(str(el["bind"]), quote=True)}"')
        return " ".join(attrs), css, kind
    if t == "dropdown":
        from .widgets import widget_colors_summary
        wc = widget_colors_summary(el, ctx.colors)
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = max(16.0, float(el.get("width", 220))), max(20.0, float(el.get("height", 40)))
        rad = el.get("radius", 8)
        rad_css = " ".join(f"{_n(float(v))}px" for v in (rad if isinstance(rad, list) else [rad]))
        bg_r, bg_g, bg_b, bg_a = wc["bg"]
        bd_r, bd_g, bd_b, bd_a = wc["border"]
        tx_r, tx_g, tx_b, tx_a = wc["text"]
        css = {
            **_box_css(x, y, w, h),
            "background": f"rgba({bg_r},{bg_g},{bg_b},{_n(bg_a / 255)})",
            "border": f"{_n(wc['border_width'])}px solid rgba({bd_r},{bd_g},{bd_b},{_n(bd_a / 255)})",
            "border-radius": rad_css,
            "color": f"rgba({tx_r},{tx_g},{tx_b},{_n(tx_a / 255)})",
            "font-family": f"'{el.get('font') or 'Inter'}',sans-serif",
            "font-size": f"{_n(float(el.get('size', 14)))}px",
            "padding": f"0 {_n(float(el.get('padding', 12)))}px",
            "cursor": "pointer",
        }
        opts = [str(o) for o in (el.get("options") or [])]
        sel = el.get("selected", 0)
        opt_html = []
        for i, o in enumerate(opts):
            is_sel = (o == sel) if isinstance(sel, str) else (i == int(sel or 0))
            opt_html.append(f'<option value="{html.escape(o, quote=True)}"{" selected" if is_sel else ""}>{html.escape(o)}</option>')
        sel_val = sel if (isinstance(sel, str) and sel in opts) else (opts[min(len(opts) - 1, max(0, int(sel or 0)))] if opts else "")
        bind_attr = f' data-bind="{html.escape(str(el["bind"]), quote=True)}"' if el.get("bind") else ""
        if sel_val:
            bind_attr += f' data-default="{html.escape(sel_val, quote=True)}"'
        return f"{bind_attr}||{''.join(opt_html)}", css, "select"
    if t in ("polygon", "path", "boolean") or t in LINE_TYPES:
        return _svg(ctx, el, st, svg_doc)
    return None


def _svg(ctx: _Ctx, el: dict, st: dict, svg_doc) -> tuple[str, dict, str] | None:
    mark_body, mark_defs = len(svg_doc.body), len(svg_doc.defs)
    if not svgexport._vector_element(svg_doc, ctx.r, el, st):
        del svg_doc.body[mark_body:]
        del svg_doc.defs[mark_defs:]
        return None
    defs = "".join(svg_doc.defs[mark_defs:])
    body = "".join(svg_doc.body[mark_body:])
    del svg_doc.body[mark_body:]
    W, H = ctx.r.canvas["width"], ctx.r.canvas["height"]
    box = ctx.r._geom_box(el, st)
    px, py = ctx.r._pivot(el, box)
    svg = (f'<svg viewBox="0 0 {_n(W)} {_n(H)}" width="{_n(W)}" height="{_n(H)}" aria-hidden="true">'
           + (f"<defs>{defs}</defs>" if defs else "") + body + "</svg>")
    css = {"left": "0", "top": "0", "width": f"{_n(W)}px", "height": f"{_n(H)}px",
           "transform-origin": f"{_n(px)}px {_n(py)}px"}
    return svg, css, "svg"


def _widget_chrome(ctx: _Ctx, el: dict, eid: str, layout: str, W: float, H: float) -> list[str]:
    """Emit associated HTML <label> and live slider readout elements matching canvas widget rendering."""
    t = el.get("type")
    if t not in ("input", "dropdown", "slider", "toggle"):
        return []
    out: list[str] = []
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    font = html.escape(str(el.get("font") or "Inter"), quote=True)
    pin = el.get("pin") or {}

    def _pin_shift(css: dict, lx: float, ly: float, lw: float | None, lh: float) -> None:
        if layout != "responsive":
            return
        if pin.get("x") == "right" and lw is not None:
            css.pop("left", None)
            css["right"] = f"{_n(W - (lx + lw))}px"
        if pin.get("y") == "bottom":
            css.pop("top", None)
            css["bottom"] = f"{_n(H - (ly + lh))}px"

    lbl = el.get("label")
    if t in ("input", "dropdown") and lbl:
        fsize = float(el.get("size", 15 if t == "input" else 14))
        lsize = max(11.0, fsize * (0.8 if t == "input" else 0.85))
        lh = lsize * 1.25
        lx, ly = x + 2.0, y - 6.0 - lh
        lcss = {
            "left": f"{_n(lx)}px", "top": f"{_n(ly)}px",
            "font-family": f"'{font}',sans-serif", "font-size": f"{_n(lsize)}px",
            "font-weight": "600", "color": ctx.color(el.get("label_color", "#cbd5e1")),
            "line-height": "1.2", "white-space": "nowrap", "cursor": "pointer",
        }
        _pin_shift(lcss, lx, ly, None, lh)
        out.append(f'<label class="el w-label" for="{eid}" style="{_css_decl(lcss)}">{html.escape(str(lbl))}</label>')
    elif t == "slider":
        w = max(16.0, float(el.get("width", 220)))
        fsize = float(el.get("size", 13))
        lsize = max(11.0, fsize)
        lh = lsize * 1.25
        ly = y - 5.0 - lh
        if lbl:
            lx = x + 2.0
            lcss = {
                "left": f"{_n(lx)}px", "top": f"{_n(ly)}px",
                "font-family": f"'{font}',sans-serif", "font-size": f"{_n(lsize)}px",
                "font-weight": "600", "color": ctx.color(el.get("text_color", "#cbd5e1")),
                "line-height": "1.2", "white-space": "nowrap", "cursor": "pointer",
            }
            _pin_shift(lcss, lx, ly, None, lh)
            out.append(f'<label class="el w-label" for="{eid}" style="{_css_decl(lcss)}">{html.escape(str(lbl))}</label>')
            if el.get("show_value", True):
                val = float(el.get("value", 50.0))
                vtxt = f"{int(round(val))}" if abs(val - round(val)) < 1e-4 else f"{val:.1f}"
                vcss = {
                    "left": f"{_n(x)}px", "top": f"{_n(ly)}px", "width": f"{_n(max(16.0, w - 2.0))}px",
                    "text-align": "right", "font-family": f"'{el.get('font') or 'JetBrains Mono'}',monospace",
                    "font-size": f"{_n(lsize)}px", "font-weight": "600",
                    "color": ctx.color(el.get("fill_color", "#38bdf8")),
                    "line-height": "1.2", "white-space": "nowrap", "pointer-events": "none",
                }
                _pin_shift(vcss, x, ly, max(16.0, w - 2.0), lh)
                out.append(f'<span class="el w-val" data-val-for="{eid}" style="{_css_decl(vcss)}">{html.escape(vtxt)}</span>')
    elif t == "toggle" and lbl:
        w, h = max(16.0, float(el.get("width", 52))), max(16.0, float(el.get("height", 28)))
        variant = str(el.get("variant", "switch")).lower()
        lbl_x = (x + min(w, h) + 10.0) if variant == "checkbox" else (x + w + 10.0)
        fsize = float(el.get("size", 14))
        lcss = {
            "left": f"{_n(lbl_x)}px", "top": f"{_n(y)}px", "height": f"{_n(h)}px",
            "display": "flex", "align-items": "center",
            "font-family": f"'{font}',sans-serif", "font-size": f"{_n(fsize)}px",
            "font-weight": "500", "color": ctx.color(el.get("text_color", "#f8fafc")),
            "white-space": "nowrap", "cursor": "pointer",
        }
        _pin_shift(lcss, lbl_x, y, None, h)
        out.append(f'<label class="el w-toggle-lbl" for="{eid}" style="{_css_decl(lcss)}">{html.escape(str(lbl))}</label>')
    return out


def _state_fallback_diff(ctx: _Ctx, base_el: dict, new_el: dict, state: str) -> dict[str, str]:
    """Compute graceful CSS feedback for SVG / cut-corner / raster elements in interactive states."""
    base_st = resolve_style(base_el.get("style"), ctx.theme)
    new_st = resolve_style(new_el.get("style"), ctx.theme)
    diff: dict[str, str] = {}
    b_op = float(base_st.get("opacity", 1))
    n_op = float(new_st.get("opacity", 1))
    if abs(n_op - b_op) > 1e-3:
        diff["opacity"] = _n(n_op)
    transforms: list[str] = []
    dx = float(new_el.get("x", 0) or 0) - float(base_el.get("x", 0) or 0)
    dy = float(new_el.get("y", 0) or 0) - float(base_el.get("y", 0) or 0)
    if abs(dx) > 1e-3 or abs(dy) > 1e-3:
        transforms.append(f"translate({_n(dx)}px,{_n(dy)}px)")
    bsx, bsy = _scales(base_el)
    nsx, nsy = _scales(new_el)
    if abs(nsx - bsx) > 1e-3 or abs(nsy - bsy) > 1e-3:
        transforms.append(f"scale({_n(nsx / (bsx or 1))},{_n(nsy / (bsy or 1))})")
    drot = float(new_el.get("rotation", 0) or 0) - float(base_el.get("rotation", 0) or 0)
    if abs(drot) > 1e-3:
        transforms.append(f"rotate({_n(drot)}deg)")
    filters: list[str] = []
    if new_st.get("glow") and new_st.get("glow") != base_st.get("glow"):
        g = new_st["glow"]
        g = g[0] if isinstance(g, list) and g else g
        if isinstance(g, dict):
            col = ctx.color(g.get("color", "#ffffff@0.8"))
            blur = float(g.get("blur", 10))
            filters.append(f"drop-shadow(0 0 {_n(blur)}px {col})")
    visual_changed = any(new_st.get(k) != base_st.get(k) for k in ("fill", "stroke", "material", "pbr", "shadow", "inner_glow"))
    if visual_changed:
        st_l = state.lower()
        if st_l in ("pressed", "active"):
            filters.append("brightness(0.92)")
            if not transforms:
                transforms.append("scale(0.98)")
        elif st_l == "disabled":
            filters.append("saturate(0.35) brightness(0.75)")
            diff.setdefault("opacity", "0.55")
        elif st_l == "focused":
            scol = "#38bdf8"
            ns = new_st.get("stroke")
            if isinstance(ns, dict) and ns.get("color"):
                scol = ctx.color(ns["color"])
            elif isinstance(ns, str):
                scol = ctx.color(ns)
            filters.append(f"drop-shadow(0 0 6px {scol})")
        else:
            filters.append("brightness(1.14)")
            if not new_st.get("glow"):
                ns = new_st.get("stroke")
                scol = ns.get("color") if isinstance(ns, dict) else (ns if isinstance(ns, str) else None)
                if scol:
                    filters.append(f"drop-shadow(0 0 8px {ctx.color(scol)})")
    if transforms:
        diff["transform"] = " ".join(transforms)
    if filters:
        diff["filter"] = " ".join(filters)
    return diff


def _picture(ctx: _Ctx, el: dict, big, beneath: list[str], include_background: bool) -> tuple[str, dict] | None:
    st = ctx.r._nums(resolve_style(el.get("style"), ctx.theme))
    result = big.render_element(el)
    if result is None:
        return None
    img, px0, py0, _ = result
    if st.get("glass"):
        from PIL import ImageChops
        scene = big.render(include_background=include_background, only=set(beneath))
        patch = scene.crop((px0, py0, px0 + img.width, py0 + img.height))
        foot = ImageChops.lighter(img.getchannel("A"), big.shape_mask(el, (px0, py0, img.width, img.height)))
        patch.putalpha(ImageChops.multiply(patch.getchannel("A"), foot))
        img = patch
    assets = ctx.out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    name = f"{_ident(ctx.r.canvas['id'])}-{_ident(el['id'])}.png"
    img.save(assets / name, optimize=True)
    ctx.raster.append(el["id"])
    s = ctx.scale
    css = _box_css(px0 / s, py0 / s, img.width / s, img.height / s)
    box = ctx.r._geom_box(el, st)
    px, py = ctx.r._pivot(el, box)
    css["transform-origin"] = f"{_n(px - px0 / s)}px {_n(py - py0 / s)}px"
    return f"assets/{name}", css


def _anchor(css: dict, el: dict, W: float, H: float) -> None:
    """Responsive mode: pins become left / right / centre / stretch anchors."""
    pin = el.get("pin") or {}
    if not pin or not str(css.get("left", "")).endswith("px") or not str(css.get("width", "")).endswith("px"):
        return
    left, top = float(css["left"][:-2]), float(css["top"][:-2])
    w = float(css["width"][:-2])
    h = float(css["height"][:-2]) if css.get("height", "").endswith("px") else 0.0
    px, py = pin.get("x", "left"), pin.get("y", "top")
    if px == "right":
        css.pop("left")
        css["right"] = f"{_n(W - left - w)}px"
    elif px == "center":
        css["left"] = f"calc(50% + {_n(left - W / 2)}px)"
    elif px == "stretch":
        css["right"] = f"{_n(W - left - w)}px"
        css.pop("width")
    elif px == "scale":
        css["left"], css["width"] = f"{_n(left / W * 100)}%", f"{_n(w / W * 100)}%"
    if py == "bottom":
        css.pop("top")
        css["bottom"] = f"{_n(H - top - h)}px"
    elif py == "middle":
        css["top"] = f"calc(50% + {_n(top - H / 2)}px)"
    elif py == "stretch" and h:
        css["bottom"] = f"{_n(H - top - h)}px"
        css.pop("height", None)
    elif py == "scale" and h:
        css["top"], css["height"] = f"{_n(top / H * 100)}%", f"{_n(h / H * 100)}%"


def _css_decl(css: dict, important: bool = False) -> str:
    """Inline-style text; important=True lets state rules win over the element's inline style."""
    return ";".join(f"{k}:{v}{'!important' if important else ''}" for k, v in css.items())


def _keyframes(ctx: _Ctx, canvas: dict, name: str, anim: dict, ids: set[str],
               baked_rot: dict[str, float] | None = None) -> tuple[str, dict[str, str]]:
    """CSS @keyframes for move / rotate / scale / fade tracks; returns (css, {element id: animation decl})."""
    tracks = anim.get("tracks", [])
    if not tracks:
        return "", {}
    baked = baked_rot or {}
    duration = float(anim.get("duration", 1))
    steps = max(2, min(60, int(duration * 20) + 1))
    colors = ctx.colors
    poses = [apply_animation(canvas, anim, duration * i / (steps - 1), colors)[0] for i in range(steps)]
    base = {e["id"]: e for e in canvas["elements"]}
    rules, decls = [], {}
    for eid in ids:
        frames = [next((e for e in p["elements"] if e["id"] == eid), None) for p in poses]
        if any(f is None for f in frames) or all(f == base[eid] for f in frames):
            continue
        keep = {"x", "y", "cx", "cy", "points", "origin", "rotation", "scale", "scale_x", "scale_y", "style"}
        if any({k for k in set(f) | set(base[eid]) if f.get(k) != base[eid].get(k)} - keep for f in frames):
            ctx.notes.add(f"{eid}: only movement, rotation, scale and opacity animate on the web")
        b = base[eid]
        bx, by = (float(b["points"][0][0]), float(b["points"][0][1])) if b.get("points") else \
            ((float(b["cx"]), float(b["cy"])) if "cx" in b else (float(b.get("x", 0)), float(b.get("y", 0))))
        base_rot = baked.get(eid, 0.0)
        lines = []
        for i, f in enumerate(frames):
            fx, fy = (float(f["points"][0][0]), float(f["points"][0][1])) if f.get("points") else \
                ((float(f["cx"]), float(f["cy"])) if "cx" in f else (float(f.get("x", 0)), float(f.get("y", 0))))
            sx, sy = _scales(f)
            rot = float(f.get("rotation", 0) or 0) - base_rot
            op = float(resolve_style(f.get("style"), ctx.theme).get("opacity", 1))
            lines.append(f"{_n(100 * i / (steps - 1))}%{{transform:translate({_n(fx - bx)}px,{_n(fy - by)}px) "
                         f"rotate({_n(rot)}deg) scale({_n(sx)},{_n(sy)});opacity:{_n(op)}}}")
        kf = f"a-{_ident(canvas['id'])}-{_ident(name)}-{_ident(eid)}"
        rules.append(f"@keyframes {kf}{{{''.join(lines)}}}")
        decls[eid] = f"{kf} {_n(duration)}s linear {'infinite' if anim.get('loop') else '1 both'}"
    return "\n".join(rules), decls


def build(store, canvases: list[dict], out: Path, layout: str, language: str | None, include_background: bool,
          image_scale: float) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pages = {c["id"]: ("index.html" if i == 0 else f"{_ident(c['id'])}.html") for i, c in enumerate(canvases)}
    theme = store.theme
    css_rules: list[str] = []
    all_fonts: dict[str, tuple[str, int, bool]] = {}
    report = {"pages": [], "picture": [], "notes": set()}
    root = [f"--color-{_ident(k)}:{_hex(v, theme)}" for k, v in theme.get("colors", {}).items()]
    css_rules.append(":root{" + ";".join(root) + "}")
    for mode, vals in (theme.get("modes") or {}).items():
        decl = [f"--color-{_ident(k)}:{_hex(v, {**theme.get('colors', {}), **vals})}" for k, v in vals.items()
                if not isinstance(v, (int, float))]
        if decl:
            css_rules.append(f'[data-theme="{_ident(mode)}"]{{' + ";".join(decl) + "}")
    for c in canvases:
        r = store.renderer(c, 1.0, language=language)
        big = r.derive(max(1.0, min(8.0, image_scale)))
        ctx = _Ctx(r, theme, out, max(1.0, min(8.0, image_scale)))
        svg_doc = svgexport._Doc()
        W, H = float(c["width"]), float(c["height"])
        links = c.get("links") or {}
        groups_with_links = {el.get("group") for el in c["elements"] if el["id"] in links and el.get("group")}
        body: list[str] = []
        beneath: list[str] = []
        page_css: list[str] = []
        states = c.get("states") or {}
        focus = {eid: i + 1 for i, eid in enumerate(c.get("focus_order") or [])}
        open_group = None
        ix = c.get("interactions") or []
        ix_ids = {rule["id"] for rule in ix}
        played = {rule["animation"] for rule in ix if rule.get("animation")}
        used_states = {rule["state"] for rule in ix if rule.get("state")}
        clickable = {rule["id"] for rule in ix if rule["trigger"] in ("click", "press", "release")}
        baked_rot: dict[str, float] = {}
        dynamic_ids = (
            {b["target"] for b in (c.get("bindings") or [])}
            | {t["target"] for a in (c.get("animations") or {}).values() for t in (a.get("tracks") or [])}
            | {rule["id"] for rule in ix if not str(rule["id"]).startswith("group:")}
            | set(links.keys())
        )
        for lay, elements in r.stack():
            props = r.layer_props(lay) if lay else None
            if props and not props["visible"]:
                continue
            if props and (props["style"] or props["clip"]):
                ids = {e["id"] for e in elements}
                beneath.extend(ids)
                dyn_hit = sorted((ids & dynamic_ids) | {e["id"] for e in elements if e.get("type") in ("input", "scroll", "slider", "toggle", "dropdown")})
                if dyn_hit:
                    report["notes"].add(
                        f"{c['id']}: layer '{props['name']}' was rasterized (layer style/clip), so live bindings/interactions on {', '.join(dyn_hit)} will not update individually on the web"
                    )
                img = big.render(include_background=False, only=ids)
                bbox = img.getchannel("A").getbbox()
                if bbox:
                    (out / "assets").mkdir(parents=True, exist_ok=True)
                    name = f"{_ident(c['id'])}-layer-{_ident(props['name'])}.png"
                    img.crop(bbox).save(out / "assets" / name, optimize=True)
                    s = ctx.scale
                    body.append(f'<img class="el" alt="" src="assets/{name}" style="{_css_decl(_box_css(bbox[0] / s, bbox[1] / s, (bbox[2] - bbox[0]) / s, (bbox[3] - bbox[1]) / s))}">')
                    report["picture"].append(f"{c['id']}:layer:{props['name']}")
                continue
            layer_open = bool(props and (props["opacity"] < 1 or props["blend"] != "normal"))
            if layer_open:
                lstyle = {"position": "absolute", "inset": "0", "pointer-events": "none"}
                if props["opacity"] < 1:
                    lstyle["opacity"] = _n(props["opacity"])
                if props["blend"] != "normal" and props["blend"] in _BLENDS:
                    lstyle["mix-blend-mode"] = props["blend"]
                body.append(f'<div class="layer" style="{_css_decl(lstyle)}">')
            for el in elements:
                beneath.append(el["id"])
                grp = el.get("group")
                if grp != open_group:
                    if open_group is not None:
                        body.append("</div>")
                    if grp:
                        attrs = ""
                        if grp in groups_with_links:
                            target = links[next(e["id"] for e in c["elements"] if e.get("group") == grp and e["id"] in links)]
                            attrs = _link_attrs(target, pages, focus.get(grp, 0))
                        attrs += _ix_attrs(f"group:{grp}", ix_ids, clickable, attrs, focus.get(grp, 0))
                        body.append(f'<div class="g g-{_ident(grp)}"{attrs}>')
                    open_group = grp
                got = _element(ctx, el, svg_doc)
                eid = _ident(el["id"])
                vt = f"view-transition-name:v-{eid}"
                extra_attrs = ""
                if el["id"] in links and not grp:
                    extra_attrs = _link_attrs(links[el["id"]], pages, focus.get(el["id"], 0))
                extra_attrs += _ix_attrs(el["id"], ix_ids, clickable, extra_attrs, focus.get(el["id"], 0))
                if el.get("note"):
                    extra_attrs += f' title="{html.escape(str(el["note"]))}"'
                if got is None:
                    pic = _picture(ctx, el, big, beneath, include_background)
                    if pic is None:
                        continue
                    src, css = pic
                    if layout == "responsive":
                        _anchor(css, el, W, H)
                    if el.get("fixed"):
                        css["position"] = "fixed"
                    brot = float(el.get("rotation", 0) or 0)
                    baked_rot[el["id"]] = brot
                    rot_attr = f' data-base-rot="{_n(brot)}"' if brot else ""
                    body.append(f'<img class="el" id="{eid}" alt="" src="{src}" style="{_css_decl(css)};{vt}"{rot_attr}{extra_attrs}>')
                    continue
                inner, css, kind = got
                if layout == "responsive":
                    _anchor(css, el, W, H)
                if el.get("fixed"):
                    css["position"] = "fixed"
                decl = _css_decl(css) + ";" + vt
                if kind == "img":
                    body.append(f'<img class="el" id="{eid}" alt="" src="{inner}" style="{decl}"{extra_attrs}>')
                elif kind == "svg":
                    brot = float(el.get("rotation", 0) or 0)
                    baked_rot[el["id"]] = brot
                    rot_attr = f' data-base-rot="{_n(brot)}"' if brot else ""
                    body.append(f'<div class="el vec" id="{eid}" style="{decl}"{rot_attr}{extra_attrs}>{inner}</div>')
                elif kind == "input":
                    body.extend(_widget_chrome(ctx, el, eid, layout, W, H))
                    body.append(f'<input class="el input" id="{eid}" {inner} style="{decl}"{extra_attrs}>')
                elif kind == "slider":
                    body.extend(_widget_chrome(ctx, el, eid, layout, W, H))
                    body.append(f'<input class="el input w-slider" id="{eid}" {inner} style="{decl}"{extra_attrs}>')
                elif kind == "switch":
                    body.append(f'<input class="el input toggle-switch" id="{eid}" {inner} style="{decl}"{extra_attrs}>')
                    body.extend(_widget_chrome(ctx, el, eid, layout, W, H))
                elif kind == "scroll":
                    body.append(f'<div class="el scroll" id="{eid}" style="{decl}"{extra_attrs}>{inner}</div>')
                elif kind == "select":
                    body.extend(_widget_chrome(ctx, el, eid, layout, W, H))
                    b_attr, opt_body = inner.split("||", 1)
                    body.append(f'<select class="el select" id="{eid}"{b_attr} style="{decl}"{extra_attrs}>{opt_body}</select>')
                else:
                    body.append(f'<div class="el {kind}" id="{eid}" style="{decl}"{extra_attrs}>{inner}</div>')
            if open_group is not None:
                body.append("</div>")
                open_group = None
            if layer_open:
                body.append("</div>")
        for state in [s for s in states if s in _STATE_PSEUDO or s in used_states]:
            pseudo = _STATE_PSEUDO.get(state)
            posed = apply_state(c, state)
            pr = store.renderer(posed, 1.0, language=language)
            pctx = _Ctx(pr, theme, out, ctx.scale)
            for eid in states[state]:
                base_el = next((e for e in c["elements"] if e["id"] == eid), None)
                new_el = next((e for e in posed["elements"] if e["id"] == eid), None)
                if base_el is None or new_el is None:
                    continue
                a, b = _element(ctx, base_el, svgexport._Doc()), _element(pctx, new_el, svgexport._Doc())
                if a is None or b is None or a[2] in ("svg", "img"):
                    diff = _state_fallback_diff(ctx, base_el, new_el, state)
                    if not diff:
                        report["notes"].add(f"{c['id']}: the {state} look of '{eid}' is not reproduced on the web")
                        continue
                else:
                    diff = {k: v for k, v in b[1].items() if a[1].get(k) != v}
                    if not diff:
                        continue
                if pseudo:
                    sel = (f".g-{_ident(base_el['group'])}{pseudo} #{_ident(eid)}" if base_el.get("group")
                           else f"#{_ident(eid)}{pseudo}")
                    page_css.append(f"{sel}{{{_css_decl(diff, True)};transition:all .15s ease}}")
                if state in used_states:
                    page_css.append(f".page.s-{_ident(state)} #{_ident(eid)}{{{_css_decl(diff, True)};transition:all .15s ease}}")
        for name, anim in (c.get("animations") or {}).items():
            rules, decls = _keyframes(ctx, c, name, anim, {e["id"] for e in c["elements"]}, baked_rot)
            if rules:
                page_css.append(rules)
                for eid, decl in decls.items():
                    sel = f".page.p-{_ident(name)} #{_ident(eid)}" if name in played else f"#{_ident(eid)}"
                    page_css.append(f"{sel}{{animation:{decl}}}")
        bg = c.get("background") if include_background else None
        bg_css = ""
        if bg and not _is_none(bg):
            if isinstance(bg, str) and not bg.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                bg_css = f"background:{ctx.color(bg)};"
            else:
                (out / "assets").mkdir(parents=True, exist_ok=True)
                name = f"{_ident(c['id'])}-background.png"
                big.render(include_background=True, only=set()).save(out / "assets" / name, optimize=True)
                bg_css = f"background:url(assets/{name}) center/cover;"
        size = (f"width:{_n(W)}px;height:{_n(H)}px" if layout == "fit"
                else f"width:100vw;min-height:max(100vh,{_n(H)}px)")
        fonts_css = "".join(
            f"@font-face{{font-family:'{fam}';src:url(assets/fonts/{file});font-weight:{'100 900' if var else w};font-display:swap}}"
            for fam, (file, w, var) in ctx.fonts.items())
        all_fonts.update(ctx.fonts)
        cfg = _ix_config(c, ix, pages)
        has_runtime = bool(ix or c.get("focus_order") or c.get("bindings") or c.get("data"))
        ix_script = ("<script>window.UIFORGE_IX=" + json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
                     + "</script>") if has_runtime else ""
        report.setdefault("parts", {})[c["id"]] = {
            "file": pages[c["id"]], "fonts_css": fonts_css, "size": size, "bg_css": bg_css,
            "page_css": "".join(page_css), "body": "\n".join(body), "W": W, "H": H, "ix": cfg}
        doc = (f"<!doctype html>\n<html lang=\"{html.escape(language or 'en')}\"><head><meta charset=\"utf-8\">"
               f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
               f"<link rel=\"icon\" href=\"data:,\">"
               f"<title>{html.escape(str(c.get('name') or c['id']))}</title>"
               f"<link rel=\"stylesheet\" href=\"styles.css\"><style>{fonts_css}"
               f".page{{{size};{bg_css}}}{''.join(page_css)}</style></head>"
               f"<body class=\"{layout}\"><main class=\"page\" data-w=\"{_n(W)}\" data-h=\"{_n(H)}\">"
               + "\n".join(body) + f"</main>{ix_script}<script src=\"app.js\"></script></body></html>\n")
        (out / pages[c["id"]]).write_text(doc, encoding="utf-8")
        report["pages"].append(pages[c["id"]])
        report["picture"] += [f"{c['id']}:{i}" for i in ctx.raster]
        report["notes"] |= ctx.notes
    css_rules.append(_BASE_CSS)
    (out / "styles.css").write_text("\n".join(css_rules) + "\n", encoding="utf-8")
    (out / "app.js").write_text(_APP_JS, encoding="utf-8")
    report["notes"] = sorted(report["notes"])
    return report


def _hex(value: Any, theme_colors: Any) -> str:
    colors = theme_colors.get("colors", theme_colors) if isinstance(theme_colors, dict) else {}
    r, g, b, a = parse_color(value, colors)
    return f"#{r:02x}{g:02x}{b:02x}" if a == 255 else f"rgba({r}, {g}, {b}, {_n(a / 255)})"


def _ix_attrs(key: str, ix_ids: set, clickable: set, existing: str, tab: int) -> str:
    if key not in ix_ids:
        return ""
    attr = f' data-ix="{html.escape(key)}"'
    if key in clickable and "tabindex" not in existing:
        attr += f' role="button" tabindex="{tab or 0}"'
    return attr


def _ix_config(c: dict, ix: list, pages: dict) -> dict:
    """The page's interaction rules, focus order, and data bindings for the runtime (uiforgeAttach)."""
    from . import binding
    rules = []
    for rule in ix:
        r = dict(rule)
        if r.get("animation"):
            r["animKey"] = _ident(r["animation"])
        if r.get("state"):
            r["stateKey"] = _ident(r["state"])
        if r["action"] in ("navigate", "overlay"):
            r["href"], r["to"] = pages.get(r["target"], f"{_ident(r['target'])}.html"), r["target"]
        elif r["action"] == "back":
            r["href"] = "#back"
        elif r["action"] == "url":
            r["href"] = r["target"]
        rules.append(r)
    anims = {k: {"duration": float(a.get("duration", 1)), "loop": bool(a.get("loop"))}
             for k, a in (c.get("animations") or {}).items()}
    binds = []
    for b in c.get("bindings") or []:
        try:
            binds.append({"id": _ident(b["target"]), "prop": b["property"], "js": binding.js_expr(b["expr"])})
        except Exception:
            continue
    text_tpls = {
        _ident(e["id"]): str(e.get("text", ""))
        for e in c.get("elements", [])
        if e.get("type") == "text" and "{" in str(e.get("text", ""))
    }
    focus = [_ident(eid) for eid in (c.get("focus_order") or [])]
    return {"rules": rules, "anims": anims, "focus": focus, "data": dict(c.get("data") or {}),
            "bindings": binds, "templates": text_tpls}


def _link_attrs(target: Any, pages: dict, tab: int) -> str:
    if isinstance(target, dict):
        mode, dest = str(target.get("mode", "navigate")), target.get("target") or target.get("url")
    else:
        mode, dest = "navigate", target
    if dest == "back":
        href = "#back"
    elif mode == "url":
        href = str(dest)
    else:
        href = pages.get(str(dest), f"{_ident(str(dest))}.html")
    attr = f' data-href="{html.escape(href)}" data-mode="{html.escape(mode)}" role="link" tabindex="{tab or 0}"'
    if mode != "url" and dest != "back":
        attr += f' data-to="{html.escape(str(dest))}"'
    return attr


_BASE_CSS = """*{box-sizing:border-box}
html,body{margin:0;background:#0b0b10;color:#fff}
@view-transition{navigation:auto}
body.fit{display:grid;place-items:center;min-height:100vh;overflow:hidden}
.page{position:relative;overflow:hidden}
body.fit .page{transform-origin:center center}
.el{position:absolute;margin:0}
.text{overflow-wrap:break-word}
.vec svg{display:block;overflow:visible;pointer-events:none}
.vec svg *{pointer-events:visiblePainted}
.vec{pointer-events:none}
.g{display:contents}
.w-label,.w-val,.w-toggle-lbl{user-select:none}
.toggle-switch{appearance:none;-webkit-appearance:none;border-radius:999px;background:var(--off-col,#334155);border:1px solid rgba(255,255,255,.15);transition:background .18s ease}
.toggle-switch::after{content:"";position:absolute;top:12%;left:3px;height:76%;aspect-ratio:1/1;border-radius:50%;background:var(--thumb-col,#fff);box-shadow:0 1px 4px rgba(0,0,0,.35);transition:left .18s ease,transform .18s ease}
.toggle-switch:checked{background:var(--on-col,#22c55e)}
.toggle-switch:checked::after{left:calc(100% - 3px);transform:translateX(-100%)}
[data-href]{cursor:pointer}
[data-href]:focus-visible{outline:2px solid #fff;outline-offset:2px}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.55);display:grid;place-items:center;z-index:9999}
.overlay iframe{border:0;width:min(92vw,var(--ow));height:min(92vh,var(--oh));background:transparent}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

RUNTIME_JS = """function uiforgeApplyData(root, cfg, patch) {
  cfg = cfg || {};
  var d = Object.assign({}, cfg.data || {}, patch || {});
  var tpls = cfg.templates || {};
  Object.keys(tpls).forEach(function (id) {
    var el = root.querySelector('#' + id);
    if (el) el.textContent = tpls[id].replace(/\\{([A-Za-z_][\\w.-]*)\\}/g, function (m, k) { return k in d ? String(d[k]) : m; });
  });
  (cfg.bindings || []).forEach(function (b) {
    var el = root.querySelector('#' + b.id);
    if (!el) return;
    try {
      var v = (new Function('d', 'return (' + b.js + ');'))(d);
      if (b.prop === 'width' || b.prop === 'height') el.style[b.prop] = Math.max(0, Number(v)) + 'px';
      else if (b.prop === 'x') el.style.left = Number(v) + 'px';
      else if (b.prop === 'y') el.style.top = Number(v) + 'px';
      else if (b.prop === 'rotation') el.style.transform = 'rotate(' + (Number(v) - Number(el.dataset.baseRot || 0)) + 'deg)';
      else if (b.prop === 'opacity') el.style.opacity = String(Math.max(0, Math.min(1, Number(v))));
      else if (b.prop === 'visible') el.style.display = v ? '' : 'none';
      else if (b.prop === 'text') el.textContent = String(v);
      else if (b.prop === 'style.fill' || b.prop === 'fill') el.style.background = String(v);
      else if (b.prop === 'style.color' || b.prop === 'color') el.style.color = String(v);
    } catch (e) {}
  });
  root.querySelectorAll('[data-bind]').forEach(function (inp) {
    var k = inp.dataset.bind;
    if (!(k in d)) return;
    if (inp.type === 'checkbox') inp.checked = !!d[k];
    else if (inp !== document.activeElement) inp.value = String(d[k]);
    if (inp.id) {
      var valEl = root.querySelector('[data-val-for="' + inp.id + '"]');
      if (valEl) { var n = Number(d[k]); valEl.textContent = isNaN(n) ? String(d[k]) : (Math.abs(n - Math.round(n)) < 1e-4 ? String(Math.round(n)) : n.toFixed(1)); }
    }
  });
  return d;
}
function uiforgeAttach(root, cfg, go, onSfx) {
  cfg = cfg || {};
  var rules = cfg.rules || [], anims = cfg.anims || {}, timers = [];
  function act(r) {
    var run = function () {
      if (r.sfx && onSfx) onSfx(r.sfx, r.id);
      var a = r.action;
      if (a === 'play') {
        var cls = 'p-' + r.animKey;
        root.classList.remove(cls); void root.offsetWidth; root.classList.add(cls);
        var info = anims[r.animation];
        if (info && !info.loop) timers.push(setTimeout(function () { fire(null, 'end:' + r.animation); }, info.duration * 1000));
      } else if (a === 'stop') root.classList.remove('p-' + r.animKey);
      else if (a === 'set_state') root.classList.add('s-' + r.stateKey);
      else if (a === 'clear_state') root.classList.remove('s-' + r.stateKey);
      else if (a === 'toggle_state') root.classList.toggle('s-' + r.stateKey);
      else go(r.href, a, r.to);
    };
    if (r.delay) timers.push(setTimeout(run, r.delay * 1000)); else run();
  }
  function fire(id, trigger) {
    rules.forEach(function (r) { if (r.trigger === trigger && (id === null || r.id === id)) act(r); });
  }
  function on(type, trigger, edge) {
    root.addEventListener(type, function (e) {
      var el = e.target && e.target.closest ? e.target.closest('[data-ix]') : null;
      if (el && (!edge || !el.contains(e.relatedTarget))) fire(el.dataset.ix, trigger);
    });
  }
  function focusables() {
    var list = (cfg.focus || []).map(function (id) { return root.querySelector('#' + id); }).filter(Boolean);
    if (!list.length) list = Array.prototype.slice.call(root.querySelectorAll('[data-href],[data-ix],[tabindex]'));
    return list.filter(function (el) { return el.style.display !== 'none'; });
  }
  function moveFocus(step) {
    var list = focusables();
    if (!list.length) return;
    var idx = list.indexOf(document.activeElement);
    var next = idx < 0 ? (step > 0 ? 0 : list.length - 1) : (idx + step + list.length) % list.length;
    if (list[next].tabIndex < 0) list[next].tabIndex = 0;
    list[next].focus();
  }
  on('pointerover', 'hover', true); on('pointerout', 'leave', true);
  on('pointerdown', 'press'); on('pointerup', 'release'); on('click', 'click');
  function syncBoundInput(e) {
    var el = e.target;
    if (el && el.id && el.type === 'range') {
      var valEl = root.querySelector('[data-val-for="' + el.id + '"]');
      if (valEl) { var n = Number(el.value); valEl.textContent = Math.abs(n - Math.round(n)) < 1e-4 ? String(Math.round(n)) : n.toFixed(1); }
    }
    if (el && el.dataset && el.dataset.bind) {
      cfg.data = Object.assign({}, cfg.data || {});
      var v = el.type === 'checkbox' ? !!el.checked : (el.type === 'range' || el.type === 'number' ? Number(el.value) : el.value);
      cfg.data[el.dataset.bind] = v;
      uiforgeApplyData(root, cfg, cfg.data);
    }
  }
  root.addEventListener('input', syncBoundInput);
  root.addEventListener('change', syncBoundInput);
  root.addEventListener('click', function (e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-href]') : null;
    if (el) go(el.dataset.href, el.dataset.mode, el.dataset.to);
  });
  root.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-href],[data-ix]')) { e.preventDefault(); e.target.click(); }
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); moveFocus(1); }
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); moveFocus(-1); }
  });
  function key(e) { fire(null, 'key:' + e.key); }
  document.addEventListener('keydown', key);
  var gpPrev = {}, raf = 0;
  function pollGamepad() {
    var pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (var i = 0; i < pads.length; i++) {
      var gp = pads[i]; if (!gp) continue;
      var up = (gp.buttons[12] && gp.buttons[12].pressed) || (gp.axes[1] || 0) < -0.5;
      var dn = (gp.buttons[13] && gp.buttons[13].pressed) || (gp.axes[1] || 0) > 0.5;
      var lt = (gp.buttons[14] && gp.buttons[14].pressed) || (gp.axes[0] || 0) < -0.5;
      var rt = (gp.buttons[15] && gp.buttons[15].pressed) || (gp.axes[0] || 0) > 0.5;
      var ok = gp.buttons[0] && gp.buttons[0].pressed;
      var bk = gp.buttons[1] && gp.buttons[1].pressed;
      if ((dn || rt) && !gpPrev.next) moveFocus(1);
      if ((up || lt) && !gpPrev.prev) moveFocus(-1);
      if (ok && !gpPrev.ok && document.activeElement && root.contains(document.activeElement)) document.activeElement.click();
      if (bk && !gpPrev.bk) go('#back', 'back');
      gpPrev = { next: dn || rt, prev: up || lt, ok: ok, bk: bk };
      break;
    }
    raf = requestAnimationFrame(pollGamepad);
  }
  if (typeof requestAnimationFrame === 'function' && navigator.getGamepads) raf = requestAnimationFrame(pollGamepad);
  if ((cfg.bindings && cfg.bindings.length) || (cfg.data && Object.keys(cfg.data).length)) uiforgeApplyData(root, cfg, cfg.data);
  fire(null, 'load');
  return function () { timers.forEach(clearTimeout); if (raf) cancelAnimationFrame(raf); document.removeEventListener('keydown', key); };
}
"""

_APP_JS = """// uiforge-mcp web export: fit-to-window scaling, links, overlays, interactions, gamepad nav, data binding
(function () {
  const page = document.querySelector('.page');
  function fit() {
    if (!document.body.classList.contains('fit') || !page) return;
    const w = +page.dataset.w, h = +page.dataset.h;
    const s = Math.min(innerWidth / w, innerHeight / h);
    page.style.transform = 'scale(' + s + ')';
  }
  addEventListener('resize', fit); fit();
  function go(el) {
    const href = el.dataset.href, mode = el.dataset.mode;
    if (href === '#back') { if (window.parent !== window) { parent.postMessage('close-overlay', '*'); } else { history.back(); } return; }
    if (mode === 'overlay') {
      const o = document.createElement('div'); o.className = 'overlay';
      const f = document.createElement('iframe'); f.src = href;
      f.addEventListener('load', () => { const p = f.contentDocument && f.contentDocument.querySelector('.page');
        if (p) { o.style.setProperty('--ow', p.dataset.w + 'px'); o.style.setProperty('--oh', p.dataset.h + 'px'); } });
      o.appendChild(f); o.addEventListener('click', e => { if (e.target === o) o.remove(); });
      document.body.appendChild(o); return;
    }
    if (mode === 'url') { window.open(href, '_blank', 'noopener'); return; }
    if (window.parent !== window && mode !== 'navigate-top') { location.href = href; return; }
    location.href = href;
  }
  addEventListener('message', e => { if (e.data === 'close-overlay') document.querySelectorAll('.overlay').forEach(o => o.remove()); });
  if (page) {
    uiforgeAttach(page, window.UIFORGE_IX, (href, mode) => go({ dataset: { href: href, mode: mode } }));
    window.uiforgeSetData = patch => uiforgeApplyData(page, window.UIFORGE_IX, patch);
  }
""" + RUNTIME_JS + """})();
"""


_VOID = {"img", "br", "hr", "input", "source", "meta", "link"}
_JSX_ATTR = {"class": "className", "for": "htmlFor", "tabindex": "tabIndex", "srcset": "srcSet",
             "crossorigin": "crossOrigin", "readonly": "readOnly", "maxlength": "maxLength",
             "contenteditable": "contentEditable", "spellcheck": "spellCheck"}
_JSX_NUM_ATTR = {"tabindex", "maxlength"}


def _style_object(css: str) -> str:
    parts, depth, cur = [], 0, ""
    for ch in css:
        depth += (ch == "(") - (ch == ")")
        if ch == ";" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    items = []
    for part in parts:
        prop, _, val = part.partition(":")
        prop, val = prop.strip(), val.strip()
        if prop and val:
            key = prop if prop.startswith("--") else re.sub(r"-([a-z])", lambda m: m.group(1).upper(), prop)
            items.append(f"{json.dumps(key)}: {json.dumps(val)}")
    return "{{" + ", ".join(items) + "}}"


_TW_PROP = {
    "left": "left", "top": "top", "right": "right", "bottom": "bottom", "width": "w", "height": "h",
    "border-radius": "rounded", "font-size": "text", "color": "text", "opacity": "opacity",
    "letter-spacing": "tracking", "line-height": "leading",
}
_TW_WEIGHT = {"100": "font-thin", "200": "font-extralight", "300": "font-light", "400": "font-normal",
              "500": "font-medium", "600": "font-semibold", "700": "font-bold", "800": "font-extrabold", "900": "font-black"}


def _css_to_tailwind(css: str) -> tuple[list[str], str]:
    """Convert simple CSS declarations to Tailwind utility classes; return (classes, leftover_css)."""
    parts, depth, cur = [], 0, ""
    for ch in css:
        depth += (ch == "(") - (ch == ")")
        if ch == ";" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    tw, rest = [], []
    for part in parts:
        prop, _, val = part.partition(":")
        prop, val = prop.strip(), val.strip()
        if not prop or not val:
            continue
        clean = re.sub(r"\s+", "_", val)
        if prop == "font-weight" and val in _TW_WEIGHT:
            tw.append(_TW_WEIGHT[val])
        elif prop == "text-align" and val in ("left", "center", "right"):
            tw.append(f"text-{val}")
        elif prop == "position" and val in ("absolute", "fixed", "relative"):
            tw.append(val)
        elif prop == "background" and re.fullmatch(r"#[0-9a-fA-F]{3,8}|rgba\([^)]+\)|var\(--[^)]+\)", val):
            tw.append(f"bg-[{clean}]")
        elif prop in _TW_PROP and " " not in val:
            tw.append(f"{_TW_PROP[prop]}-[{clean}]")
        else:
            rest.append(f"{prop}:{val}")
    return tw, ";".join(rest)


class _Jsx(HTMLParser):
    """HTML (from the web export) -> JSX: className, style objects (or Tailwind classes), imported images."""

    def __init__(self, images: dict, tailwind: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.images = images
        self.tailwind = tailwind

    def _attrs(self, tag: str, attrs: list) -> str:
        res = []
        extra_tw: list[str] = []
        cleaned = []
        for name, value in attrs:
            if name == "style" and self.tailwind and value:
                tw, rest = _css_to_tailwind(value)
                extra_tw.extend(tw)
                if rest:
                    cleaned.append((name, rest))
            else:
                cleaned.append((name, value))
        has_class = any(n == "class" for n, _ in cleaned)
        for name, value in cleaned:
            if name == "data-gsvg":
                res.append(f"dangerouslySetInnerHTML={{{{ __html: SVG_{value} }}}}")
            elif name == "style":
                res.append(f"style={_style_object(value or '')}")
            elif name == "class" and extra_tw:
                base = re.sub(r"\bel\b", "el absolute m-0", value or "") if self.tailwind else (value or "")
                res.append(f"className={{{json.dumps((base + ' ' + ' '.join(extra_tw)).strip(), ensure_ascii=False)}}}")
            elif tag == "img" and name == "src" and value and value.startswith("assets/"):
                var = self.images.setdefault(value, f"img{len(self.images)}")
                res.append(f"src={{{var}}}")
            elif tag == "input" and name == "value":
                res.append(f"defaultValue={{{json.dumps(value, ensure_ascii=False)}}}")
            elif tag == "input" and name == "checked":
                res.append("defaultChecked={true}")
            elif tag == "select" and name == "data-default":
                res.append(f"defaultValue={{{json.dumps(value, ensure_ascii=False)}}}")
            elif tag == "option" and name == "selected":
                continue
            else:
                key = _JSX_ATTR.get(name, name)
                if value is None:
                    res.append(key)
                elif name in _JSX_NUM_ATTR and re.fullmatch(r"-?\d+", value):
                    res.append(f"{key}={{{int(value)}}}")
                else:
                    res.append(f"{key}={{{json.dumps(value, ensure_ascii=False)}}}")
        if extra_tw and not has_class:
            res.append(f"className={{{json.dumps(' '.join(extra_tw), ensure_ascii=False)}}}")
        return (" " + " ".join(res)) if res else ""

    def handle_starttag(self, tag, attrs):
        self.out.append(f"<{tag}{self._attrs(tag, attrs)}{' />' if tag in _VOID else '>'}")

    def handle_startendtag(self, tag, attrs):
        self.out.append(f"<{tag}{self._attrs(tag, attrs)} />")

    def handle_endtag(self, tag):
        if tag not in _VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if data and not data.isspace():
            self.out.append("{" + json.dumps(data, ensure_ascii=False) + "}")
        elif data and "\n" not in data:
            self.out.append('{" "}')


def to_jsx(body: str, tailwind: bool = False) -> tuple[str, dict, list[str]]:
    """(jsx, {asset path: import name}, [svg markup]) for a page body."""
    svgs: list[str] = []

    def keep(m: re.Match) -> str:
        svgs.append(m.group(2))
        return f'{m.group(1)} data-gsvg="{len(svgs) - 1}"></div>'
    body = re.sub(r'(<div class="el vec"[^>]*)>(<svg.*?</svg>)</div>', keep, body, flags=re.S)
    images: dict = {}
    p = _Jsx(images, tailwind=tailwind)
    p.feed(body)
    p.close()
    return "\n      ".join(p.out), images, svgs


def build_react(store, canvases: list[dict], out: Path, language: str | None, include_background: bool,
                image_scale: float, css_mode: str = "css", typescript: bool = False) -> dict:
    report = build(store, canvases, out, "fit", language, include_background, image_scale)
    tailwind = css_mode == "tailwind"
    ext = "tsx" if typescript else "jsx"
    used: set[str] = set()
    components = []
    for c in canvases:
        part = report["parts"][c["id"]]
        name = re.sub(r"[^0-9a-zA-Z]+", " ", str(c["id"])).title().replace(" ", "") or "Screen"
        if not name[0].isalpha():
            name = "Screen" + name
        while name in used:
            name += "X"
        used.add(name)
        cls = f"page-{_ident(c['id'])}"
        (out / f"{name}.css").write_text(part["fonts_css"] + f".{cls}{{{part['size']};{part['bg_css']}}}"
                                         + part["page_css"] + "\n", encoding="utf-8")
        jsx, images, svgs = to_jsx(part["body"], tailwind=tailwind)
        lines = ["import { useEffect, useRef } from 'react';", "import './styles.css';", f"import './{name}.css';",
                 "import { uiforgeAttach, uiforgeApplyData } from './uiforge-runtime.js';"]
        lines += [f"import {var} from './{path}';" for path, var in images.items()]
        lines += ["", f"const IX = {json.dumps(part['ix'], ensure_ascii=False)};"]
        lines += [f"const SVG_{i} = {json.dumps(s, ensure_ascii=False)};" for i, s in enumerate(svgs)]
        page_cls = f"page relative overflow-hidden {cls}" if tailwind else f"page {cls}"
        if typescript:
            data_fields = "".join(f"  {k}?: any;\n" for k in (c.get("data") or {}).keys())
            data_ty = f"{{\n{data_fields}  [key: string]: any;\n}}" if data_fields else "Record<string, any>"
            lines += ["", f"export interface {name}Props {{",
                      "  onNavigate?: (target: string, mode: string) => void;",
                      "  onSfx?: (name: string) => void;",
                      f"  data?: {data_ty};",
                      "  className?: string;",
                      "}", ""]
            sig = f"export default function {name}({{ onNavigate, onSfx, data, className }}: {name}Props) {{"
            ref_decl = "  const ref = useRef<HTMLElement | null>(null);"
        else:
            sig = f"export default function {name}({{ onNavigate, onSfx, data, className }}) {{"
            ref_decl = "  const ref = useRef(null);"
        nav_cb = "(href: string, mode?: string, to?: string)" if typescript else "(href, mode, to)"
        lines += ["", sig, ref_decl,
                  f"  useEffect(() => uiforgeAttach(ref.current, IX, {nav_cb} => {{",
                  "    if (onNavigate) return onNavigate(to || href, mode || 'navigate');",
                  "    if (mode === 'url') window.open(href, '_blank', 'noopener');",
                  "  }, onSfx), [onNavigate, onSfx]);",
                  "  useEffect(() => { if (ref.current && data) uiforgeApplyData(ref.current, IX, data); }, [data]);",
                  "  return (",
                  f'    <main ref={{ref}} className={{`{page_cls} ${{className || ""}}`.trim()}} data-w="{_n(part["W"])}" data-h="{_n(part["H"])}">',
                  f"      {jsx}",
                  "    </main>",
                  "  );",
                  "}", ""]
        (out / f"{name}.{ext}").write_text("\n".join(lines), encoding="utf-8")
        (out / part["file"]).unlink(missing_ok=True)
        components.append(f"{name}.{ext}")
    (out / "app.js").unlink(missing_ok=True)
    css = (out / "styles.css").read_text(encoding="utf-8")
    css = "\n".join(line for line in css.splitlines() if not line.startswith(("html,body", "body.fit", "@view-transition")))
    (out / "styles.css").write_text(css + "\n", encoding="utf-8")
    runtime_esm = RUNTIME_JS.replace("function uiforgeApplyData", "export function uiforgeApplyData").replace(
        "function uiforgeAttach", "export function uiforgeAttach")
    (out / "uiforge-runtime.js").write_text(runtime_esm, encoding="utf-8")
    if typescript:
        (out / "uiforge-runtime.d.ts").write_text(
            "export interface UIForgeRuntimeConfig {\n"
            "  rules?: Array<Record<string, any>>;\n"
            "  anims?: Record<string, { duration: number; loop: boolean }>;\n"
            "  focus?: string[];\n"
            "  data?: Record<string, any>;\n"
            "  bindings?: Array<{ id: string; prop: string; js: string }>;\n"
            "  templates?: Record<string, string>;\n"
            "}\n"
            "export function uiforgeApplyData(\n"
            "  root: HTMLElement | null,\n"
            "  cfg?: UIForgeRuntimeConfig,\n"
            "  patch?: Record<string, any>,\n"
            "): Record<string, any>;\n"
            "export function uiforgeAttach(\n"
            "  root: HTMLElement | null,\n"
            "  cfg?: UIForgeRuntimeConfig,\n"
            "  go?: (href: string, mode?: string, to?: string) => void,\n"
            "  onSfx?: (name: string, id?: string) => void,\n"
            "): () => void;\n",
            encoding="utf-8",
        )
        (out / "uiforge-assets.d.ts").write_text(
            "declare module '*.css';\n"
            "declare module '*.png' { const src: string; export default src; }\n"
            "declare module '*.webp' { const src: string; export default src; }\n"
            "declare module '*.jpg' { const src: string; export default src; }\n"
            "declare module '*.jpeg' { const src: string; export default src; }\n"
            "declare module '*.svg' { const src: string; export default src; }\n",
            encoding="utf-8",
        )
    idx_ext = "ts" if typescript else "js"
    (out / f"index.{idx_ext}").write_text(
        "".join(f"export {{ default as {Path(cmp).stem} }} from './{Path(cmp).stem}';\n" for cmp in components),
        encoding="utf-8")
    return {"components": components, "picture": report["picture"], "notes": report["notes"]}
