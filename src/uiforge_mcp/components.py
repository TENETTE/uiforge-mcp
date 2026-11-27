"""High-level composite game & app UI builders (add_button, add_progress_bar) and container-relative
layout helpers (`in: "<frame>.inner_box"` and `add_stack`) for zero-math atomic screen assembly.
"""

from __future__ import annotations

import re
from typing import Any

from .colors import parse_color
from .icons import build_icon_element
from .store import slugify


def _contrast_ink(bg_color: str, theme_colors: dict | None = None) -> str:
    """Choose crisp high-contrast ink (#060b14 or #f8fafc) over a fill colour."""
    try:
        r, g, b, _ = parse_color(bg_color, theme_colors or {})
        # Relative sRGB luminance (WCAG)
        def _lin(c: int) -> float:
            s = c / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

        lum = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
        return "#060b14" if lum > 0.36 else "#f8fafc"
    except Exception:
        return "#f8fafc"


def _mix_hex(c1: str, c2: str, t: float, theme_colors: dict | None = None) -> str:
    try:
        r1, g1, b1, _ = parse_color(c1, theme_colors or {})
        r2, g2, b2, _ = parse_color(c2, theme_colors or {})
        r = int(round(r1 + (r2 - r1) * t))
        g = int(round(g1 + (g2 - g1) * t))
        b = int(round(b1 + (b2 - b1) * t))
        return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"
    except Exception:
        return c1


def button_operations(
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    *,
    icon: str | None = None,
    keycap: str | None = None,
    variant: str = "primary",
    corner: str | None = None,
    radius: float | None = None,
    accent: str | None = None,
    font: str | None = None,
    size: float | None = None,
    states: str | bool = "auto",
    style_preset: str = "scifi",
    quality: str = "advanced",
    theme_colors: dict | None = None,
    id: str | None = None,
    group: str | None = None,
    layer: str | None = None,
) -> dict[str, Any]:
    """Generate editable vector specs + automatic hover/pressed/focused/disabled states for one button."""
    ix, iy = round(float(x)), round(float(y))
    iw, ih = max(48, round(float(width))), max(28, round(float(height)))
    var = str(variant or "primary").lower().strip()
    sp = str(style_preset or "scifi").lower()
    base = slugify(id, "btn") if id else "btn"
    grp = group or base
    tc = theme_colors or {}

    if corner is None:
        eff_corner = "cut" if sp in ("scifi", "realistic") else "round"
    else:
        eff_corner = str(corner).lower()
    if radius is None:
        eff_rad = min(14, max(6, round(ih * 0.24))) if eff_corner == "cut" else (
            min(16, round(ih * 0.35)) if sp in ("kids", "cartoon") else min(12, max(6, round(ih * 0.22)))
        )
    else:
        eff_rad = round(float(radius))

    acc = accent or (
        "#f43f5e" if var == "danger" else
        "#f59e0b" if var == "gold" else
        tc.get("primary") or ("#22d3ee" if sp == "scifi" else "#3b82f6")
    )
    acc_hi = _mix_hex(acc, "#ffffff", 0.22, tc)
    acc_lo = _mix_hex(acc, "#060b14", 0.38, tc)

    if var in ("primary", "danger", "gold"):
        body_fill: Any = {"type": "linear", "angle": 90, "stops": [[0, acc_hi], [0.55, acc], [1, acc_lo]]}
        stroke_col = f"{acc_hi}@0.85"
        text_col = _contrast_ink(acc, tc)
        hover_fill: Any = {"type": "linear", "angle": 90, "stops": [[0, _mix_hex(acc, "#ffffff", 0.34, tc)], [1, acc]]}
        press_fill: Any = {"type": "linear", "angle": 90, "stops": [[0, acc_lo], [1, _mix_hex(acc, "#020617", 0.55, tc)]]}
        glow_col = f"{acc}@0.55"
    elif var == "ghost":
        body_fill = "#0f172a@0.35"
        stroke_col = f"{acc}@0.55"
        text_col = "#f8fafc"
        hover_fill = f"{acc}@0.18"
        press_fill = f"{acc}@0.28"
        glow_col = f"{acc}@0.45"
    else:  # secondary
        body_fill = {"type": "linear", "angle": 180, "stops": [[0, "#17253d@0.95"], [1, "#0b1322@0.98"]]}
        stroke_col = f"{acc}@0.62"
        text_col = "#f8fafc"
        hover_fill = {"type": "linear", "angle": 180, "stops": [[0, "#1e3252@0.98"], [1, "#101b30@0.98"]]}
        press_fill = {"type": "linear", "angle": 180, "stops": [[0, "#0b1322"], [1, "#060b14"]]}
        glow_col = f"{acc}@0.55"

    body_style: dict[str, Any] = {
        "fill": body_fill,
        "stroke": {"color": stroke_col, "width": 1.5, "align": "inside"},
        "shadow": {"color": "#000000@0.48", "blur": 14, "dy": 5},
    }
    if quality in ("advanced", "aaa") and var in ("primary", "danger", "gold"):
        body_style["bevel"] = {"size": 1.5}
    if sp == "cartoon" or sp == "kids":
        body_style["stroke"] = {"color": "#020617", "width": 3, "align": "outside"}

    body_id = f"{base}_bg"
    lbl_id = f"{base}_label"
    specs: list[dict[str, Any]] = [{
        "type": "rect", "id": body_id, "group": grp, "layer": layer,
        "x": ix, "y": iy, "width": iw, "height": ih,
        "radius": eff_rad, "corner": eff_corner,
        "style": body_style,
    }]

    # Optional keycap badge on the right
    kc_w = 0
    if keycap:
        kc_txt = str(keycap).upper()
        kc_h = max(20, min(26, ih - 14))
        kc_w = max(28, round(len(kc_txt) * 8.5 + 16))
        kc_x = ix + iw - kc_w - 12
        kc_y = round(iy + (ih - kc_h) * 0.5)
        kc_bg = "#060b14@0.35" if text_col == "#060b14" else "#020617@0.65"
        kc_bd = "#060b14@0.45" if text_col == "#060b14" else f"{acc}@0.55"
        specs.append({
            "type": "rect", "id": f"{base}_keycap", "group": grp, "layer": layer,
            "x": kc_x, "y": kc_y, "width": kc_w, "height": kc_h, "radius": 4,
            "style": {"fill": kc_bg, "stroke": {"color": kc_bd, "width": 1, "align": "inside"}},
        })
        specs.append({
            "type": "text", "id": f"{base}_keytxt", "group": grp, "layer": layer,
            "text": kc_txt, "x": round(kc_x + kc_w * 0.5), "y": round(kc_y + kc_h * 0.5),
            "anchor": "center", "size": 11, "weight": 700, "font": "JetBrains Mono",
            "color": text_col,
        })

    # Icon + label placement
    fsize = round(float(size)) if size is not None else max(13, min(20, round(ih * 0.34)))
    eff_font = font or (
        "Rajdhani" if sp == "scifi" else
        "Cinzel" if sp == "dark_fantasy" else
        "Fredoka" if sp in ("kids", "cartoon") else
        "Inter"
    )
    txt_str = str(label).upper() if sp in ("scifi", "realistic") else str(label)
    ico_sz = max(16, min(26, round(ih * 0.44)))
    content_right = (ix + iw - kc_w - 20) if keycap else (ix + iw - 14)

    if icon:
        ico_x = ix + 16
        ico_y = round(iy + (ih - ico_sz) * 0.5)
        _, ico_el = build_icon_element(
            icon, ico_x, ico_y, size=ico_sz, color=text_col,
            stroke_width=2.0, id=f"{base}_icon", group=grp, layer=layer,
        )
        ico_el["type"] = "path"
        specs.append(ico_el)
        lbl_x = ico_x + ico_sz + 10
        lbl_anchor = "middle-left"
        max_w = max(36, content_right - lbl_x)
    elif keycap:
        lbl_x = ix + 16
        lbl_anchor = "middle-left"
        max_w = max(36, content_right - lbl_x)
    else:
        lbl_x = round(ix + iw * 0.5)
        lbl_anchor = "center"
        max_w = max(36, iw - 24)

    specs.append({
        "type": "text", "id": lbl_id, "group": grp, "layer": layer,
        "text": txt_str, "x": lbl_x, "y": round(iy + ih * 0.5),
        "anchor": lbl_anchor, "size": fsize, "weight": 700, "font": eff_font,
        "letter_spacing": 1.6 if sp in ("scifi", "realistic") else 0.4,
        "color": text_col, "fit_width": max_w,
    })

    state_rules: list[tuple[str, str, dict]] = []
    if states == "auto" or states is True:
        state_rules = [
            ("hover", body_id, {"style": {"fill": hover_fill, "glow": {"color": glow_col, "blur": 14}}}),
            ("pressed", body_id, {"style": {"fill": press_fill, "shadow": {"color": "#000000@0.3", "blur": 6, "dy": 2}}}),
            ("focused", body_id, {"style": {"stroke": {"color": "#ffffff", "width": 2, "align": "inside"},
                                            "glow": {"color": glow_col, "blur": 10}}}),
            ("disabled", body_id, {"style": {"opacity": 0.45}}),
            ("disabled", lbl_id, {"style": {"opacity": 0.45}}),
        ]

    return {
        "specs": specs,
        "states": state_rules,
        "group": grp,
        "body_id": body_id,
        "label_id": lbl_id,
        "bbox": [ix, iy, iw, ih],
    }


def progress_bar_operations(
    x: float,
    y: float,
    width: float,
    height: float = 16,
    *,
    value: float = 75.0,
    max_value: float = 100.0,
    label: str | None = None,
    show_value: bool = True,
    value_format: str | None = None,
    color: str | None = None,
    track_color: str = "#0b1322@0.92",
    low_color: str = "#fb6b84",
    low_threshold: float = 0.3,
    bind_value: str | None = None,
    bind_max: str | None = None,
    corner: str = "round",
    radius: float | None = None,
    font: str = "Rajdhani",
    id: str | None = None,
    group: str | None = None,
    layer: str | None = None,
    theme_colors: dict | None = None,
) -> dict[str, Any]:
    """Generate editable track + clipped fill + label + live readout + auto data bindings for a bar."""
    ix, iy = round(float(x)), round(float(y))
    iw, ih = max(24, round(float(width))), max(6, round(float(height)))
    hi = max(1e-6, float(max_value))
    val = float(value)
    frac = max(0.0, min(1.0, val / hi))
    base = slugify(id, "bar") if id else "bar"
    grp = group or base
    tc = theme_colors or {}
    col = color or tc.get("primary") or tc.get("accent") or "#22d3ee"
    col_hi = _mix_hex(col, "#ffffff", 0.25, tc)
    eff_corner = str(corner or "round").lower()
    eff_rad = round(float(radius)) if radius is not None else (min(6, ih // 2) if eff_corner == "cut" else round(ih * 0.5))

    track_id = f"{base}_track"
    fill_id = f"{base}_fill"
    fill_w = max(0, round(iw * frac))
    fill_paint: Any = low_color if (low_threshold > 0 and frac < low_threshold) else {
        "type": "linear", "angle": 0, "stops": [[0, col], [1, col_hi]],
    }

    specs: list[dict[str, Any]] = [
        {
            "type": "rect", "id": track_id, "group": grp, "layer": layer,
            "x": ix, "y": iy, "width": iw, "height": ih,
            "radius": eff_rad, "corner": eff_corner,
            "style": {
                "fill": track_color,
                "stroke": {"color": "#ffffff@0.14", "width": 1, "align": "inside"},
                "inner_shadow": {"color": "#000000@0.72", "blur": 6, "dy": 2},
            },
        },
        {
            "type": "rect", "id": fill_id, "group": grp, "layer": layer, "clip": track_id,
            "x": ix, "y": iy, "width": fill_w, "height": ih,
            "style": {"fill": fill_paint},
        },
    ]

    if label:
        specs.append({
            "type": "text", "id": f"{base}_label", "group": grp, "layer": layer,
            "text": str(label).upper(), "x": ix, "y": iy - 6, "anchor": "bottom-left",
            "size": 13, "weight": 700, "font": font, "letter_spacing": 1.6, "color": "#cbd5e1",
        })
    if show_value:
        if value_format:
            vtxt = str(value_format)
        elif bind_value and bind_max:
            vtxt = f"{{{bind_value}}} / {{{bind_max}}}"
        elif bind_value:
            vtxt = f"{{{bind_value}}}%"
        else:
            v_str = f"{int(round(val))}" if abs(val - round(val)) < 1e-4 else f"{val:.1f}"
            m_str = f"{int(round(hi))}" if abs(hi - round(hi)) < 1e-4 else f"{hi:.1f}"
            vtxt = f"{v_str} / {m_str}"
        specs.append({
            "type": "text", "id": f"{base}_value", "group": grp, "layer": layer,
            "text": vtxt, "x": ix + iw, "y": iy - 6, "anchor": "bottom-right",
            "size": 13, "weight": 600, "font": "JetBrains Mono", "color": "#f8fafc",
        })

    data_defaults: dict[str, Any] = {}
    bindings: list[dict[str, str]] = []
    if bind_value:
        data_defaults[bind_value] = int(round(val)) if abs(val - round(val)) < 1e-4 else val
        denom = bind_max if bind_max else f"{hi:g}"
        if bind_max:
            data_defaults[bind_max] = int(round(hi)) if abs(hi - round(hi)) < 1e-4 else hi
        bindings.append({
            "target": fill_id, "property": "width",
            "expr": f"clamp({bind_value} / {denom}, 0, 1) * {iw}",
        })
        if low_threshold > 0:
            bindings.append({
                "target": fill_id, "property": "style.fill",
                "expr": f"where(({bind_value} / {denom}) < {low_threshold:g}, '{low_color}', '{col}')",
            })

    return {
        "specs": specs,
        "bindings": bindings,
        "data_defaults": data_defaults,
        "group": grp,
        "track_id": track_id,
        "fill_id": fill_id,
        "bbox": [ix, iy - (20 if (label or show_value) else 0), iw, ih + (20 if (label or show_value) else 0)],
    }


def resolve_in_box(canvas: dict, ref: str, frame_boxes: dict[str, list[float]]) -> list[float]:
    """Resolve an `in` reference like 'armory_frm.inner_box', 'armory_frm', or an element id to [x, y, w, h]."""
    raw = str(ref).strip()
    key = raw[:-10] if raw.endswith(".inner_box") else raw
    if key in frame_boxes:
        return [float(v) for v in frame_boxes[key]]
    persisted = canvas.get("_boxes") or {}
    if key in persisted:
        return [float(v) for v in persisted[key]]
    for el in canvas.get("elements", []):
        if el.get("id") == key:
            if "width" in el and "height" in el:
                return [float(el.get("x", 0)), float(el.get("y", 0)), float(el["width"]), float(el["height"])]
            if "cx" in el and "rx" in el:
                rx, ry = float(el["rx"]), float(el.get("ry", el["rx"]))
                return [float(el["cx"]) - rx, float(el["cy"]) - ry, rx * 2, ry * 2]
    known = sorted(set(frame_boxes) | set(persisted))
    hint = f" Known frame boxes: {', '.join(known)}" if known else ""
    raise ValueError(f"Unknown container reference in='{ref}'.{hint}")


def _resolve_span(val: Any, total: float, offset: float = 0.0) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lower()
    if s in ("fill", "100%"):
        return max(8.0, total - offset)
    m = re.fullmatch(r"fill\s*-\s*(\d+(?:\.\d+)?)", s)
    if m:
        return max(8.0, total - offset - float(m.group(1)))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)%", s)
    if m:
        return max(8.0, total * float(m.group(1)) / 100.0)
    return float(val)


def apply_in_box(op: str, op_args: dict[str, Any], box: list[float]) -> None:
    """Mutate op_args in-place to translate container-relative coordinates & fill/% sizes into canvas pixels."""
    bx, by, bw, bh = box
    rel_x = 0.0
    rel_y = 0.0
    center_x = False
    center_y = False

    if "x" in op_args:
        if isinstance(op_args["x"], str) and op_args["x"].strip().lower() == "center":
            center_x = True
        else:
            rel_x = float(op_args["x"])
    if "y" in op_args:
        if isinstance(op_args["y"], str) and op_args["y"].strip().lower() in ("center", "middle"):
            center_y = True
        else:
            rel_y = float(op_args["y"])

    if "width" in op_args and op_args["width"] is not None:
        op_args["width"] = round(_resolve_span(op_args["width"], bw, 0.0 if center_x else rel_x), 2)
    if "height" in op_args and op_args["height"] is not None:
        op_args["height"] = round(_resolve_span(op_args["height"], bh, 0.0 if center_y else rel_y), 2)

    if op in ("add_ellipse", "add_arc", "add_ticks") or ("cx" in op_args and "cy" in op_args):
        if "cx" in op_args:
            op_args["cx"] = round(bx + (bw * 0.5 if str(op_args["cx"]).lower() == "center" else float(op_args["cx"])), 2)
        if "cy" in op_args:
            op_args["cy"] = round(by + (bh * 0.5 if str(op_args["cy"]).lower() in ("center", "middle") else float(op_args["cy"])), 2)
    elif op == "add_line" and op_args.get("points"):
        op_args["points"] = [[round(bx + float(p[0]), 2), round(by + float(p[1]), 2)] for p in op_args["points"]]
    elif op == "add_polygon" and op_args.get("points"):
        op_args["points"] = [[round(bx + float(p[0]), 2), round(by + float(p[1]), 2)] for p in op_args["points"]]
    else:
        w = float(op_args.get("width", 0) or 0)
        h = float(op_args.get("height", 0) or 0)
        if center_x:
            if op == "add_text":
                op_args["x"] = round(bx + bw * 0.5, 2)
                op_args.setdefault("anchor", "center")
            else:
                op_args["x"] = round(bx + max(0.0, (bw - w) * 0.5), 2)
        else:
            op_args["x"] = round(bx + rel_x, 2)
        if center_y:
            if op == "add_text":
                op_args["y"] = round(by + bh * 0.5, 2)
                op_args.setdefault("anchor", "center")
            else:
                op_args["y"] = round(by + max(0.0, (bh - h) * 0.5), 2)
        else:
            op_args["y"] = round(by + rel_y, 2)

    if op_args.get("origin") and isinstance(op_args["origin"], list) and len(op_args["origin"]) == 2:
        op_args["origin"] = [round(bx + float(op_args["origin"][0]), 2), round(by + float(op_args["origin"][1]), 2)]


def estimate_stack_child(child: dict[str, Any], default_w: float | None = None) -> tuple[float, float, float]:
    """Return (width, height, top_headroom) for a child op inside add_stack."""
    op = str(child.get("op", ""))
    top_pad = 0.0
    if op in ("add_input", "add_dropdown"):
        w = float(child.get("width") or default_w or 240)
        h = float(child.get("height") or (42 if op == "add_input" else 40))
        if child.get("label"):
            top_pad = 22.0
    elif op == "add_slider":
        w = float(child.get("width") or default_w or 240)
        h = float(child.get("height") or 28)
        if child.get("label"):
            top_pad = 22.0
    elif op == "add_toggle":
        w = float(child.get("width") or 52)
        h = float(child.get("height") or 28)
    elif op == "add_progress_bar":
        w = float(child.get("width") or default_w or 240)
        h = float(child.get("height") or 16)
        if child.get("label") or child.get("show_value", True):
            top_pad = 20.0
    elif op == "add_button":
        w = float(child.get("width") or default_w or 180)
        h = float(child.get("height") or 44)
    elif op == "add_text":
        sz = float(child.get("size") or 18)
        w = float(child.get("max_width") or child.get("fit_width") or default_w or max(60.0, len(str(child.get("text", ""))) * sz * 0.58))
        h = max(sz * 1.3, 18.0)
    elif op == "add_icon":
        sz = float(child.get("size") or 28)
        w, h = sz, sz
    elif op == "add_scroll":
        w = float(child.get("width") or default_w or 280)
        h = float(child.get("height") or 200)
    else:
        w = float(child.get("width") or default_w or 120)
        h = float(child.get("height") or 40)
    return w, h, top_pad
