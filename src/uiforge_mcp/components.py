"""High-level composite game & app UI builders (add_button, add_progress_bar) and container-relative
layout helpers (`in: "<frame>.inner_box"` and `add_stack`) for zero-math atomic screen assembly.
"""

from __future__ import annotations

import re
from typing import Any

from .colors import parse_color
from .icons import build_icon_element
from .store import slugify


def _rel_lum(bg_color: str, theme_colors: dict | None = None) -> float:
    r, g, b, _ = parse_color(bg_color, theme_colors or {})

    def _lin(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _wcag_ratio(c1: str, c2: str, theme_colors: dict | None = None) -> float:
    l1, l2 = _rel_lum(c1, theme_colors), _rel_lum(c2, theme_colors)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _contrast_ink(bg_color: str, theme_colors: dict | None = None) -> str:
    """Choose crisp high-contrast ink (#060b14 or #f8fafc) maximizing WCAG contrast ratio."""
    try:
        r_dark = _wcag_ratio("#060b14", bg_color, theme_colors)
        r_light = _wcag_ratio("#f8fafc", bg_color, theme_colors)
        return "#060b14" if r_dark >= r_light else "#f8fafc"
    except Exception:
        return "#f8fafc"


def _theme_font(theme: dict | None, role: str, style_preset: str, explicit: str | None = None) -> str:
    """Resolve explicit font -> active theme style font -> style_preset default."""
    if explicit:
        return str(explicit)
    if isinstance(theme, dict):
        styles = theme.get("styles") or {}
        st_role = styles.get(role) or styles.get("title" if role == "heading" else "body") or {}
        if isinstance(st_role, dict) and st_role.get("font"):
            return str(st_role["font"])
    sp = str(style_preset or "scifi").lower()
    if role in ("title", "heading", "button"):
        return (
            "Rajdhani" if sp == "scifi" else
            "Cinzel" if sp == "dark_fantasy" else
            "Barlow Condensed" if sp == "realistic" else
            "Fredoka" if sp in ("kids", "cartoon") else
            "Inter"
        )
    return "JetBrains Mono" if role == "mono" else "Inter"


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
    theme: dict | None = None,
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
        "#be123c" if var == "danger" else
        "#f59e0b" if var == "gold" else
        tc.get("primary") or ("#22d3ee" if sp == "scifi" else "#3b82f6")
    )
    if var in ("primary", "danger", "gold"):
        # Pick ink maximizing WCAG contrast and ensure gradient stops stay >= 4.8:1
        text_col = _contrast_ink(acc, tc)
        if text_col == "#f8fafc" and _wcag_ratio("#f8fafc", acc, tc) < 4.8:
            for step in (0.18, 0.32, 0.45):
                cand = _mix_hex(acc, "#060b14", step, tc)
                if _wcag_ratio("#f8fafc", cand, tc) >= 4.8:
                    acc = cand
                    break
        elif text_col == "#060b14" and _wcag_ratio("#060b14", acc, tc) < 4.8:
            for step in (0.16, 0.28, 0.42):
                cand = _mix_hex(acc, "#ffffff", step, tc)
                if _wcag_ratio("#060b14", cand, tc) >= 4.8:
                    acc = cand
                    break
        acc_hi = _mix_hex(acc, "#ffffff", 0.14 if text_col == "#f8fafc" else 0.22, tc)
        acc_lo = _mix_hex(acc, "#060b14", 0.36 if text_col == "#f8fafc" else 0.20, tc)
        body_fill: Any = {"type": "linear", "angle": 90, "stops": [[0, acc_hi], [0.55, acc], [1, acc_lo]]}
        stroke_col = f"{acc_hi}@0.85"
        hover_fill: Any = {"type": "linear", "angle": 90, "stops": [[0, _mix_hex(acc, "#ffffff", 0.28, tc)], [1, acc]]}
        press_fill: Any = {"type": "linear", "angle": 90, "stops": [[0, acc_lo], [1, _mix_hex(acc, "#020617", 0.55, tc)]]}
        glow_col = f"{acc}@0.55"
    else:
        acc_hi = _mix_hex(acc, "#ffffff", 0.22, tc)
        acc_lo = _mix_hex(acc, "#060b14", 0.38, tc)
        if var == "ghost":
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
        kc_h = max(22, min(26, ih - 12))
        kc_w = max(30, round(len(kc_txt) * 9.0 + 16))
        kc_x = ix + iw - kc_w - 12
        kc_y = round(iy + (ih - kc_h) * 0.5)
        kc_bg = "#090d16@0.88"
        kc_bd = "#060b14@0.65" if text_col == "#060b14" else f"{acc}@0.6"
        kc_ink = "#f8fafc"
        specs.append({
            "type": "rect", "id": f"{base}_keycap", "group": grp, "layer": layer,
            "x": kc_x, "y": kc_y, "width": kc_w, "height": kc_h, "radius": 4,
            "style": {"fill": kc_bg, "stroke": {"color": kc_bd, "width": 1, "align": "inside"}},
        })
        specs.append({
            "type": "text", "id": f"{base}_keytxt", "group": grp, "layer": layer,
            "text": kc_txt, "x": round(kc_x + kc_w * 0.5), "y": round(kc_y + kc_h * 0.5),
            "anchor": "center", "size": 12, "weight": 700, "font": "JetBrains Mono",
            "color": kc_ink,
        })

    # Icon + label placement
    fsize = round(float(size)) if size is not None else max(13, min(20, round(ih * 0.34)))
    eff_font = _theme_font(theme, "button", sp, font)
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
    font: str | None = None,
    style_preset: str = "scifi",
    id: str | None = None,
    group: str | None = None,
    layer: str | None = None,
    theme_colors: dict | None = None,
    theme: dict | None = None,
) -> dict[str, Any]:
    """Generate editable track + clipped fill + label + live readout + auto data bindings for a bar."""
    ix, iy = round(float(x)), round(float(y))
    iw, ih = max(24, round(float(width))), max(6, round(float(height)))
    hi = max(1e-6, float(max_value))
    val = float(value)
    frac = max(0.0, min(1.0, val / hi))
    base = slugify(id, "bar") if id else "bar"
    grp = group or base
    tc = theme_colors or (theme.get("colors", {}) if isinstance(theme, dict) else {})
    eff_font = _theme_font(theme, "title", style_preset, font)
    lbl_col = tc.get("muted") or "#cbd5e1"
    val_col = tc.get("text") or "#f8fafc"
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
            "x": ix, "y": iy, "width": fill_w, "height": ih, "_decor": True,
            "style": {"fill": fill_paint},
        },
    ]

    if label:
        specs.append({
            "type": "text", "id": f"{base}_label", "group": grp, "layer": layer,
            "text": str(label).upper(), "x": ix, "y": iy - 6, "anchor": "bottom-left",
            "size": 13, "weight": 700, "font": eff_font, "letter_spacing": 1.6, "color": lbl_col,
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
            "size": 13, "weight": 600, "font": "JetBrains Mono", "color": val_col,
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


def resolve_split_boxes(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    direction: str = "row",
    sizes: list[Any] | None = None,
    gap: float = 20.0,
    padding: float = 0.0,
) -> list[list[float]]:
    """Split a container rect into proportional tracks supporting px numbers, '27%' and '1fr'/'2fr'."""
    d = str(direction or "row").lower()
    if d not in ("row", "column"):
        raise ValueError("add_split direction must be 'row' or 'column'")
    tracks = list(sizes or ["1fr", "1fr"])
    if not tracks:
        raise ValueError("add_split requires at least one size track")
    ix, iy = float(x) + float(padding), float(y) + float(padding)
    iw = max(16.0, float(width) - float(padding) * 2.0)
    ih = max(16.0, float(height) - float(padding) * 2.0)
    g = max(0.0, float(gap))
    total_main = iw if d == "row" else ih
    avail = max(1.0, total_main - g * max(0, len(tracks) - 1))

    fixed_px: list[float | None] = []
    fr_weights: list[float] = []
    fixed_sum = 0.0
    for tok in tracks:
        if isinstance(tok, (int, float)):
            v = max(8.0, float(tok))
            fixed_px.append(v)
            fr_weights.append(0.0)
            fixed_sum += v
        else:
            s = str(tok).strip().lower()
            m_pct = re.fullmatch(r"(\d+(?:\.\d+)?)%", s)
            m_fr = re.fullmatch(r"(\d+(?:\.\d+)?)fr", s)
            if m_pct:
                v = max(8.0, avail * float(m_pct.group(1)) / 100.0)
                fixed_px.append(v)
                fr_weights.append(0.0)
                fixed_sum += v
            elif m_fr:
                fixed_px.append(None)
                fr_weights.append(max(0.01, float(m_fr.group(1))))
            elif s in ("auto", "fill"):
                fixed_px.append(None)
                fr_weights.append(1.0)
            else:
                v = max(8.0, float(s.rstrip("px")))
                fixed_px.append(v)
                fr_weights.append(0.0)
                fixed_sum += v

    rem = max(0.0, avail - fixed_sum)
    total_fr = sum(fr_weights) or 1.0
    resolved = [
        round(fp if fp is not None else max(8.0, rem * (fw / total_fr)), 2)
        for fp, fw in zip(fixed_px, fr_weights)
    ]

    boxes: list[list[float]] = []
    cur = ix if d == "row" else iy
    for span in resolved:
        if d == "row":
            boxes.append([round(cur, 2), round(iy, 2), round(span, 2), round(ih, 2)])
        else:
            boxes.append([round(ix, 2), round(cur, 2), round(iw, 2), round(span, 2)])
        cur += span + g
    return boxes


RARITY_COLORS: dict[str, tuple[str, str]] = {
    "common": ("#64748b", "#94a3b8"),
    "uncommon": ("#22c55e", "#4ade80"),
    "rare": ("#38bdf8", "#7dd3fc"),
    "epic": ("#a855f7", "#c084fc"),
    "legendary": ("#f59e0b", "#fbbf24"),
    "exotic": ("#f43f5e", "#fb7185"),
}


def gauge_operations(
    cx: float,
    cy: float,
    radius: float = 90.0,
    *,
    value: float = 65.0,
    min_value: float = 0.0,
    max_value: float = 100.0,
    start_angle: float | None = None,
    end_angle: float | None = None,
    style: str = "radial",
    unit: str = "",
    label: str | None = None,
    redline: float = 0.8,
    ticks: int = 8,
    minor_per_major: int = 4,
    color: str | None = None,
    redline_color: str | None = None,
    bind_value: str | None = None,
    style_preset: str = "scifi",
    theme: dict | None = None,
    id: str | None = None,
    group: str | None = None,
    layer: str | None = None,
) -> dict[str, Any]:
    """Generate a complete AAA radial/semi/segmented dial gauge with ticks, needle, hub & live bindings."""
    import math
    icx, icy = round(float(cx)), round(float(cy))
    r = max(42.0, float(radius))
    gstyle = str(style or "radial").lower()
    a0 = float(start_angle) if start_angle is not None else (180.0 if gstyle == "semi" else 135.0)
    a1 = float(end_angle) if end_angle is not None else (360.0 if gstyle == "semi" else 405.0)
    span = max(30.0, a1 - a0)
    lo, hi = float(min_value), max(float(min_value) + 1e-6, float(max_value))
    val = float(value)
    frac = max(0.0, min(1.0, (val - lo) / (hi - lo)))
    val_angle = round(a0 + span * frac, 2)

    base = slugify(id, "gauge") if id else "gauge"
    grp = group or base
    tc = (theme.get("colors", {}) if isinstance(theme, dict) else {})
    acc = color or tc.get("primary") or "#22d3ee"
    acc2 = tc.get("accent") or "#f59e0b"
    red_c = redline_color or tc.get("danger") or "#f43f5e"
    txt_c = tc.get("text") or "#f8fafc"
    mut_c = tc.get("muted") or "#cbd5e1"
    title_font = _theme_font(theme, "title", style_preset)

    arc_r = round(r * 0.86, 1)
    arc_thick = max(6.0, round(r * 0.085, 1))
    specs: list[dict[str, Any]] = [
        {
            "type": "ellipse", "id": f"{base}_face", "group": grp, "layer": layer, "_decor": True,
            "cx": icx, "cy": icy, "rx": round(r), "ry": round(r),
            "style": {
                "fill": {"type": "radial", "cx": 0.5, "cy": 0.42, "r": 0.85,
                         "stops": [[0, "#141e30"], [0.75, "#090f1a"], [1, "#05080f"]]},
                "stroke": {"color": "#ffffff@0.22", "width": 2.0, "align": "inside"},
                "shadow": {"color": "#000000@0.65", "blur": 20, "dy": 8},
                "inner_shadow": {"color": "#000000@0.85", "blur": 14, "dy": 4},
            },
        },
        {
            "type": "arc", "id": f"{base}_track", "group": grp, "layer": layer, "_decor": True,
            "cx": icx, "cy": icy, "radius": arc_r, "start_angle": a0, "end_angle": a1,
            "thickness": arc_thick, "cap": "butt" if gstyle == "segmented" else "round",
            **({"dash": [8, 4]} if gstyle == "segmented" else {}),
            "style": {"fill": "#ffffff@0.10"},
        },
    ]

    if 0.0 < float(redline) < 1.0:
        rl_start = round(a0 + span * float(redline), 2)
        specs.append({
            "type": "arc", "id": f"{base}_redline", "group": grp, "layer": layer, "_decor": True,
            "cx": icx, "cy": icy, "radius": round(arc_r - arc_thick * 0.9, 1),
            "start_angle": rl_start, "end_angle": a1, "thickness": max(3.0, round(arc_thick * 0.42, 1)),
            "style": {"fill": red_c},
        })

    arc_id = f"{base}_arc"
    arc_paint: Any = (
        {"type": "conic", "from": a0, "to": a1, "stops": [[0, acc], [0.65, acc2], [0.85, red_c]]}
        if 0.0 < float(redline) < 1.0 else acc
    )
    specs.append({
        "type": "arc", "id": arc_id, "group": grp, "layer": layer,
        "cx": icx, "cy": icy, "radius": arc_r, "start_angle": a0, "end_angle": val_angle,
        "thickness": arc_thick, "cap": "butt" if gstyle == "segmented" else "round",
        **({"dash": [8, 4]} if gstyle == "segmented" else {}),
        "style": {"fill": arc_paint, "glow": {"color": f"{acc}@0.45", "blur": 10}},
    })

    major_n = max(2, int(ticks))
    sub_n = max(1, int(minor_per_major))
    lbl_list = [
        f"{int(round(lo + (hi - lo) * i / major_n))}"
        if abs((lo + (hi - lo) * i / major_n) - round(lo + (hi - lo) * i / major_n)) < 1e-4
        else f"{lo + (hi - lo) * i / major_n:.1f}"
        for i in range(major_n + 1)
    ]
    ticks_op = {
        "cx": icx, "cy": icy, "radius": round(r * 0.76, 1),
        "start_angle": a0, "end_angle": a1,
        "count": major_n * sub_n + 1, "major_every": sub_n,
        "length": max(4.0, round(r * 0.055, 1)), "width": 1.2,
        "major_length": max(8.0, round(r * 0.11, 1)), "major_width": 2.0,
        "color": "#ffffff@0.35", "major_color": txt_c,
        "labels": lbl_list, "label_size": max(12, round(r * 0.135)),
        "label_font": title_font, "label_weight": 700, "label_color": txt_c,
        "id": f"{base}_ticks", "group": grp, "layer": layer,
    }

    needle_id = f"{base}_needle"
    if gstyle != "segmented":
        n_len = round(r * 0.72, 1)
        tail = round(r * 0.14, 1)
        specs.append({
            "type": "polygon", "id": needle_id, "group": grp, "layer": layer,
            "origin": [icx, icy], "rotation": val_angle,
            "points": [
                [round(icx - tail, 1), round(icy - 2.6, 1)],
                [round(icx + n_len, 1), round(icy - 1.0, 1)],
                [round(icx + n_len, 1), round(icy + 1.0, 1)],
                [round(icx - tail, 1), round(icy + 2.6, 1)],
            ],
            "style": {"fill": red_c, "glow": {"color": f"{red_c}@0.6", "blur": 8}},
        })
        specs.append({
            "type": "ellipse", "id": f"{base}_hub", "group": grp, "layer": layer, "_decor": True,
            "cx": icx, "cy": icy, "rx": max(8.0, round(r * 0.12, 1)), "ry": max(8.0, round(r * 0.12, 1)),
            "style": {"material": "radial_metal", "stroke": {"color": "#000000@0.65", "width": 1.2}},
        })

    val_y = round(icy + (r * 0.36 if gstyle != "semi" else -r * 0.16))
    val_txt = f"{{{bind_value}}}" if bind_value else (f"{int(round(val))}" if abs(val - round(val)) < 1e-4 else f"{val:.1f}")
    specs.append({
        "type": "text", "id": f"{base}_val", "group": grp, "layer": layer,
        "text": val_txt, "x": icx, "y": val_y, "anchor": "center",
        "size": max(18, round(r * 0.28)), "weight": 700, "font": "JetBrains Mono",
        "color": txt_c,
    })
    if unit or label:
        sub = f"{unit}  {label}".strip() if (unit and label) else (unit or str(label))
        specs.append({
            "type": "text", "id": f"{base}_unit", "group": grp, "layer": layer,
            "text": sub.upper(), "x": icx, "y": round(val_y + max(18, round(r * 0.22))),
            "anchor": "center", "size": 12, "weight": 700, "font": title_font,
            "letter_spacing": 1.4, "color": mut_c,
        })

    data_defaults: dict[str, Any] = {}
    bindings: list[dict[str, str]] = []
    if bind_value:
        data_defaults[bind_value] = int(round(val)) if abs(val - round(val)) < 1e-4 else val
        angle_expr = f"{a0:g} + clamp(({bind_value} - {lo:g}) / {hi - lo:g}, 0, 1) * {span:g}"
        bindings.append({"target": arc_id, "property": "end_angle", "expr": angle_expr})
        if gstyle != "segmented":
            bindings.append({"target": needle_id, "property": "rotation", "expr": angle_expr})

    _ = math.pi
    return {
        "specs": specs,
        "ticks_op": ticks_op,
        "bindings": bindings,
        "data_defaults": data_defaults,
        "group": grp,
        "arc_id": arc_id,
        "needle_id": needle_id if gstyle != "segmented" else None,
        "bbox": [round(icx - r, 2), round(icy - r, 2), round(r * 2, 2), round(r * 2, 2)],
    }


def slot_operations(
    x: float,
    y: float,
    width: float = 180.0,
    height: float = 74.0,
    *,
    icon: str | None = None,
    label: str = "Ability",
    sublabel: str | None = None,
    keycap: str | None = None,
    badge: str | None = None,
    rarity: str = "common",
    selected: bool = False,
    cooldown: float = 0.0,
    bind_cooldown: str | None = None,
    layout: str = "horizontal",
    states: str | bool = "auto",
    click_toggle: bool = True,
    style_preset: str = "scifi",
    theme: dict | None = None,
    id: str | None = None,
    group: str | None = None,
    layer: str | None = None,
) -> dict[str, Any]:
    """Generate an AAA game ability / inventory / hardpoint slot with rarity accents, keycap & cooldown."""
    ix, iy = round(float(x)), round(float(y))
    iw, ih = max(64, round(float(width))), max(52, round(float(height)))
    base = slugify(id, "slot") if id else "slot"
    grp = group or base
    tc = (theme.get("colors", {}) if isinstance(theme, dict) else {})
    r_key = str(rarity or "common").lower()
    r_col, r_hi = RARITY_COLORS.get(r_key, (tc.get("primary") or "#38bdf8", tc.get("accent") or "#7dd3fc"))
    txt_c = tc.get("text") or "#f8fafc"
    mut_c = tc.get("muted") or "#cbd5e1"
    title_font = _theme_font(theme, "title", style_preset)
    sp = str(style_preset or "scifi").lower()
    corner = "cut" if sp in ("scifi", "realistic") else "round"
    rad = 8 if corner == "cut" else 10

    bg_id = f"{base}_bg"
    border_c = r_hi if selected else f"{r_col}@0.68"
    bg_style: dict[str, Any] = {
        "fill": {"type": "linear", "angle": 180, "stops": [[0, "#121c2f@0.95"], [1, "#080e1a@0.98"]]},
        "stroke": {"color": border_c, "width": 2.0 if selected else 1.5, "align": "inside"},
        "shadow": {"color": "#000000@0.5", "blur": 12, "dy": 4},
    }
    if selected:
        bg_style["glow"] = {"color": f"{r_col}@0.45", "blur": 12}

    specs: list[dict[str, Any]] = [{
        "type": "rect", "id": bg_id, "group": grp, "layer": layer,
        "x": ix, "y": iy, "width": iw, "height": ih, "radius": rad, "corner": corner,
        "style": bg_style,
    }]

    # Rarity accent top/left bar
    specs.append({
        "type": "rect", "id": f"{base}_rar", "group": grp, "layer": layer, "_decor": True,
        "x": ix + 4, "y": iy + 8, "width": 3, "height": max(16, ih - 16), "radius": 2,
        "style": {"fill": r_col},
    })

    lay_mode = str(layout or "horizontal").lower()
    if lay_mode == "square":
        if icon:
            isz = max(20, min(36, round(min(iw, ih) * 0.42)))
            _, ico_el = build_icon_element(icon, round(ix + (iw - isz) * 0.5), round(iy + ih * 0.24),
                                           size=isz, color=r_hi, stroke_width=2.0,
                                           id=f"{base}_icon", group=grp, layer=layer)
            ico_el["type"] = "path"
            specs.append(ico_el)
        specs.append({
            "type": "text", "id": f"{base}_label", "group": grp, "layer": layer,
            "text": str(label).upper() if sp in ("scifi", "realistic") else str(label),
            "x": round(ix + iw * 0.5), "y": round(iy + ih - 14), "anchor": "center",
            "size": 12, "weight": 700, "font": title_font, "color": txt_c, "fit_width": iw - 14,
        })
    else:
        lbl_x = ix + 16
        if icon:
            isz = max(18, min(28, round(ih * 0.40)))
            _, ico_el = build_icon_element(icon, ix + 15, round(iy + (ih - isz) * 0.5),
                                           size=isz, color=r_hi, stroke_width=2.0,
                                           id=f"{base}_icon", group=grp, layer=layer)
            ico_el["type"] = "path"
            specs.append(ico_el)
            lbl_x = ix + 15 + isz + 12
        right_pad = 44 if (keycap or badge) else 14
        max_w = max(40, iw - (lbl_x - ix) - right_pad)
        lbl_y = round(iy + ih * (0.37 if sublabel else 0.50))
        specs.append({
            "type": "text", "id": f"{base}_label", "group": grp, "layer": layer,
            "text": str(label).upper() if sp in ("scifi", "realistic") else str(label),
            "x": lbl_x, "y": lbl_y, "anchor": "middle-left",
            "size": 14, "weight": 700, "font": title_font, "letter_spacing": 1.0,
            "color": txt_c, "fit_width": max_w,
        })
        if sublabel:
            specs.append({
                "type": "text", "id": f"{base}_sub", "group": grp, "layer": layer,
                "text": str(sublabel), "x": lbl_x, "y": round(iy + ih * 0.68), "anchor": "middle-left",
                "size": 12, "weight": 500, "font": "JetBrains Mono", "color": mut_c, "fit_width": max_w,
            })

    tag_txt = str(keycap or badge or "").upper()
    if tag_txt:
        kw = max(24, round(len(tag_txt) * 8.5 + 12))
        kh = 22
        kx = ix + iw - kw - 8
        ky = iy + 8
        specs.append({
            "type": "rect", "id": f"{base}_tag_bg", "group": grp, "layer": layer, "_decor": True,
            "x": kx, "y": ky, "width": kw, "height": kh, "radius": 4,
            "style": {"fill": "#090d16@0.9", "stroke": {"color": f"{r_col}@0.55", "width": 1, "align": "inside"}},
        })
        specs.append({
            "type": "text", "id": f"{base}_tag_txt", "group": grp, "layer": layer,
            "text": tag_txt, "x": round(kx + kw * 0.5), "y": round(ky + kh * 0.5),
            "anchor": "center", "size": 12, "weight": 700, "font": "JetBrains Mono", "color": "#f8fafc",
        })

    cd_id = f"{base}_cd"
    data_defaults: dict[str, Any] = {}
    bindings: list[dict[str, str]] = []
    cd_frac = max(0.0, min(1.0, float(cooldown or 0.0)))
    if cd_frac > 0 or bind_cooldown:
        cd_h = round(ih * cd_frac)
        specs.append({
            "type": "rect", "id": cd_id, "group": grp, "layer": layer, "clip": bg_id, "_decor": True,
            "x": ix, "y": iy + ih - cd_h, "width": iw, "height": max(0, cd_h),
            "style": {"fill": "#020617@0.68"},
        })
        if bind_cooldown:
            data_defaults[bind_cooldown] = cd_frac
            bindings.append({"target": cd_id, "property": "height", "expr": f"clamp({bind_cooldown}, 0, 1) * {ih}"})

    state_rules: list[tuple[str, str, dict]] = []
    if states == "auto" or states is True:
        state_rules = [
            ("hover", bg_id, {"style": {"stroke": {"color": r_hi, "width": 2, "align": "inside"},
                                        "glow": {"color": f"{r_col}@0.5", "blur": 12}}}),
            ("selected", bg_id, {"style": {"fill": {"type": "linear", "angle": 180, "stops": [[0, "#1c2d4a@0.98"], [1, "#0d1729@0.98"]]},
                                           "stroke": {"color": r_hi, "width": 2.2, "align": "inside"},
                                           "glow": {"color": f"{r_col}@0.65", "blur": 16}}}),
            ("focused", bg_id, {"style": {"stroke": {"color": "#ffffff", "width": 2, "align": "inside"}}}),
            ("disabled", bg_id, {"style": {"opacity": 0.45}}),
        ]

    interactions: list[dict[str, Any]] = []
    if click_toggle:
        interactions.append({"id": f"group:{grp}", "trigger": "click", "action": "toggle_state", "state": "selected"})

    return {
        "specs": specs,
        "states": state_rules,
        "interactions": interactions,
        "bindings": bindings,
        "data_defaults": data_defaults,
        "group": grp,
        "body_id": bg_id,
        "bbox": [ix, iy, iw, ih],
    }


def tabs_operations(
    x: float,
    y: float,
    items: list[dict | str],
    *,
    width: float | None = None,
    height: float = 42.0,
    active: int = 0,
    gap: float = 10.0,
    variant: str = "cut",
    style_preset: str = "scifi",
    quality: str = "advanced",
    theme: dict | None = None,
    id: str | None = None,
    layer: str | None = None,
) -> dict[str, Any]:
    """Generate a row of themed navigation tab buttons with isolated per-tab groups & links."""
    if not items:
        raise ValueError("add_tabs requires a non-empty items list")
    ix, iy = round(float(x)), round(float(y))
    ih = max(32, round(float(height)))
    g = max(0.0, float(gap))
    base = slugify(id, "tabs") if id else "tabs"
    n = len(items)
    tab_w = (
        max(80.0, (float(width) - g * max(0, n - 1)) / n)
        if width is not None else None
    )
    var = str(variant or "cut").lower()
    corner = "cut" if var == "cut" else "round"
    tc = (theme.get("colors", {}) if isinstance(theme, dict) else {})
    acc = tc.get("primary") or "#22d3ee"

    button_calls: list[dict[str, Any]] = []
    extra_specs: list[dict[str, Any]] = []
    cur_x = float(ix)
    for i, raw in enumerate(items):
        if isinstance(raw, str):
            lbl, ico, lnk, tid = raw, None, None, f"{base}_{i}"
        else:
            lbl = str(raw.get("label") or raw.get("title") or f"Tab {i + 1}")
            ico = raw.get("icon")
            lnk = raw.get("link") or raw.get("target")
            tid = str(raw.get("id") or f"{base}_{i}")
        is_act = (i == int(active))
        w = round(tab_w if tab_w is not None else max(116.0, len(lbl) * 10.5 + (48.0 if ico else 32.0)))
        btn_var = "primary" if (is_act and var != "underline") else ("ghost" if var == "underline" else "secondary")
        button_calls.append({
            "x": round(cur_x), "y": iy, "width": w, "height": ih,
            "label": lbl, "icon": ico, "variant": btn_var, "corner": corner,
            "link": lnk if not is_act else None, "sfx": "ui_click" if lnk and not is_act else None,
            "id": tid, "layer": layer,
        })
        if is_act and var == "underline":
            extra_specs.append({
                "type": "rect", "id": f"{tid}_ind", "group": tid, "layer": layer, "_decor": True,
                "x": round(cur_x + 8), "y": iy + ih - 3, "width": max(16, w - 16), "height": 3, "radius": 2,
                "style": {"fill": acc, "glow": {"color": f"{acc}@0.6", "blur": 8}},
            })
        cur_x += w + g
    total_w = round(cur_x - g - ix, 2)
    return {
        "button_calls": button_calls,
        "extra_specs": extra_specs,
        "bbox": [ix, iy, total_w, ih],
    }


def stat_card_operations(
    x: float,
    y: float,
    *,
    width: float | None = None,
    height: float | None = None,
    label: str = "METRIC",
    value: str = "100",
    subvalue: str | None = None,
    icon: str | None = None,
    accent: str | None = None,
    badge: str | None = None,
    compact: bool = False,
    style_preset: str = "scifi",
    theme: dict | None = None,
    id: str | None = None,
    group: str | None = None,
    layer: str | None = None,
) -> dict[str, Any]:
    """Generate a telemetry KPI stat card or an auto-sized hug badge pill."""
    ix, iy = round(float(x)), round(float(y))
    base = slugify(id, "stat") if id else "stat"
    grp = group or base
    tc = (theme.get("colors", {}) if isinstance(theme, dict) else {})
    acc = accent or tc.get("primary") or "#22d3ee"
    txt_c = tc.get("text") or "#f8fafc"
    mut_c = tc.get("muted") or "#cbd5e1"
    title_font = _theme_font(theme, "title", style_preset)
    sp = str(style_preset or "scifi").lower()
    corner = "cut" if sp in ("scifi", "realistic") else "round"

    specs: list[dict[str, Any]] = []
    if compact:
        # Auto-fit hug pill (e.g. "14,850 CR" or "ALT 42.8K")
        txt = f"{label}  {value}".strip() if label else str(value)
        ih = round(float(height)) if height is not None else 36
        est_w = round(len(txt) * 9.5 + (38 if icon else 26))
        iw = round(float(width)) if width is not None else max(88, est_w)
        specs.append({
            "type": "rect", "id": f"{base}_bg", "group": grp, "layer": layer,
            "x": ix, "y": iy, "width": iw, "height": ih, "radius": 8 if corner == "cut" else round(ih * 0.5),
            "corner": corner,
            "style": {"fill": "#0b1322@0.94", "stroke": {"color": f"{acc}@0.65", "width": 1.5, "align": "inside"}},
        })
        tx = ix + 14
        if icon:
            _, ico_el = build_icon_element(icon, ix + 10, round(iy + (ih - 16) * 0.5),
                                           size=16, color=acc, stroke_width=2.0,
                                           id=f"{base}_icon", group=grp, layer=layer)
            ico_el["type"] = "path"
            specs.append(ico_el)
            tx = ix + 34
        specs.append({
            "type": "text", "id": f"{base}_val", "group": grp, "layer": layer,
            "text": txt, "x": tx if icon else round(ix + iw * 0.5), "y": round(iy + ih * 0.5),
            "anchor": "middle-left" if icon else "center",
            "size": 13, "weight": 700, "font": "JetBrains Mono",
            "color": txt_c, "fit_width": max(40, iw - (tx - ix) - 10 if icon else iw - 18),
        })
    else:
        iw = round(float(width)) if width is not None else 250
        ih = round(float(height)) if height is not None else 74
        specs.append({
            "type": "rect", "id": f"{base}_bg", "group": grp, "layer": layer,
            "x": ix, "y": iy, "width": iw, "height": ih, "radius": 8 if corner == "cut" else 10,
            "corner": corner,
            "style": {
                "fill": {"type": "linear", "angle": 180, "stops": [[0, "#111b2e@0.94"], [1, "#080d18@0.97"]]},
                "stroke": {"color": f"{acc}@0.42", "width": 1.2, "align": "inside"},
            },
        })
        specs.append({
            "type": "rect", "id": f"{base}_accent", "group": grp, "layer": layer, "_decor": True,
            "x": ix + 4, "y": iy + 10, "width": 3, "height": max(16, ih - 20), "radius": 2,
            "style": {"fill": acc},
        })
        tx = ix + 18
        if icon:
            isz = max(18, min(26, round(ih * 0.34)))
            _, ico_el = build_icon_element(icon, ix + 16, round(iy + (ih - isz) * 0.5),
                                           size=isz, color=acc, stroke_width=2.0,
                                           id=f"{base}_icon", group=grp, layer=layer)
            ico_el["type"] = "path"
            specs.append(ico_el)
            tx = ix + 16 + isz + 12
        max_w = max(50, iw - (tx - ix) - 14)
        specs.append({
            "type": "text", "id": f"{base}_label", "group": grp, "layer": layer,
            "text": str(label).upper(), "x": tx, "y": round(iy + ih * 0.30), "anchor": "middle-left",
            "size": 12, "weight": 700, "font": title_font, "letter_spacing": 1.4,
            "color": mut_c, "fit_width": max_w,
        })
        val_str = f"{value}  {subvalue}".strip() if subvalue else str(value)
        specs.append({
            "type": "text", "id": f"{base}_val", "group": grp, "layer": layer,
            "text": val_str, "x": tx, "y": round(iy + ih * 0.67), "anchor": "middle-left",
            "size": 20, "weight": 700, "font": "JetBrains Mono",
            "color": txt_c, "fit_width": max_w,
        })
        if badge:
            bw = max(36, round(len(str(badge)) * 8.0 + 14))
            bx = ix + iw - bw - 10
            by = iy + 10
            specs.append({
                "type": "rect", "id": f"{base}_bdg", "group": grp, "layer": layer, "_decor": True,
                "x": bx, "y": by, "width": bw, "height": 20, "radius": 4,
                "style": {"fill": "#090d16@0.9", "stroke": {"color": f"{acc}@0.55", "width": 1}},
            })
            specs.append({
                "type": "text", "id": f"{base}_bdg_txt", "group": grp, "layer": layer,
                "text": str(badge).upper(), "x": round(bx + bw * 0.5), "y": round(by + 10),
                "anchor": "center", "size": 12, "weight": 700, "font": "JetBrains Mono", "color": "#f8fafc",
            })

    return {
        "specs": specs,
        "group": grp,
        "body_id": f"{base}_bg",
        "bbox": [ix, iy, iw, ih],
    }


def _num_or(val: Any, fallback: float) -> float:
    if val is None or isinstance(val, bool):
        return fallback
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip())
    except ValueError:
        return fallback


def estimate_stack_child(child: dict[str, Any], default_w: float | None = None) -> tuple[float, float, float]:
    """Return (width, height, top_headroom) for a child op inside add_stack or add_grid."""
    op = str(child.get("op", ""))
    top_pad = 0.0
    if op == "spacer":
        return _num_or(child.get("width"), 0.0), _num_or(child.get("height"), 0.0), 0.0
    if op in ("add_input", "add_dropdown"):
        w = _num_or(child.get("width"), default_w or 240.0)
        h = _num_or(child.get("height"), 42.0 if op == "add_input" else 40.0)
        if child.get("label"):
            top_pad = 22.0
    elif op == "add_slider":
        w = _num_or(child.get("width"), default_w or 240.0)
        h = _num_or(child.get("height"), 28.0)
        if child.get("label"):
            top_pad = 22.0
    elif op == "add_toggle":
        w = _num_or(child.get("width"), 52.0)
        h = _num_or(child.get("height"), 28.0)
    elif op == "add_progress_bar":
        w = _num_or(child.get("width"), default_w or 240.0)
        h = _num_or(child.get("height"), 16.0)
        if child.get("label") or child.get("show_value", True):
            top_pad = 20.0
    elif op == "add_button":
        w = _num_or(child.get("width"), default_w or 180.0)
        h = _num_or(child.get("height"), 44.0)
    elif op == "add_slot":
        w = _num_or(child.get("width"), default_w or 180.0)
        h = _num_or(child.get("height"), 74.0)
    elif op == "add_stat_card":
        compact = bool(child.get("compact"))
        w = _num_or(child.get("width"), 140.0 if compact else (default_w or 250.0))
        h = _num_or(child.get("height"), 36.0 if compact else 74.0)
    elif op == "add_tabs":
        w = _num_or(child.get("width"), default_w or 360.0)
        h = _num_or(child.get("height"), 42.0)
    elif op == "add_gauge":
        rad = _num_or(child.get("radius"), 90.0)
        w, h = rad * 2.0, rad * 2.0
    elif op == "add_text":
        sz = _num_or(child.get("size"), 18.0)
        w = _num_or(child.get("max_width") or child.get("fit_width"), default_w or max(60.0, len(str(child.get("text", ""))) * sz * 0.58))
        h = max(sz * 1.3, 18.0)
    elif op == "add_icon":
        sz = _num_or(child.get("size"), 28.0)
        w, h = sz, sz
    elif op == "add_scroll":
        w = _num_or(child.get("width"), default_w or 280.0)
        h = _num_or(child.get("height"), 200.0)
    else:
        w = _num_or(child.get("width"), default_w or 120.0)
        h = _num_or(child.get("height"), 40.0)
    return w, h, top_pad
