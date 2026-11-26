"""Interactive widget canvas renderers for first-class native Input, Scroll, Slider, Toggle & Dropdown elements.

Each widget renders into a crisp RGBA layer using the same vector geometry, PBR/fill paint pipeline,
font shaping and clipping as standard shapes, while preserving semantic metadata so Web/React,
Godot, Unity UI Toolkit, Unity uGUI, Roblox, Unreal UMG, WPF, Avalonia, WinUI, Qt QML and Dear ImGui
export them as genuine native interactive controls.
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageChops

from .colors import parse_color


def _default_input_style(el: dict, st: dict) -> dict:
    out = dict(st)
    if "fill" not in out:
        out["fill"] = "#0f172a@0.92"
    if "stroke" not in out:
        focused = bool(el.get("focused"))
        out["stroke"] = {
            "color": "#38bdf8" if focused else "#475569@0.75",
            "width": 2.0 if focused else 1.25,
            "align": "inside",
        }
    return out


def _default_scroll_style(el: dict, st: dict) -> dict:
    out = dict(st)
    if "fill" not in out:
        out["fill"] = "#0b1120@0.88"
    if "stroke" not in out:
        out["stroke"] = {"color": "#334155@0.7", "width": 1.2, "align": "inside"}
    return out


def _composite_sub(renderer, dst: Image.Image, px0: int, py0: int, spec: dict, clip_mask: Image.Image | None = None) -> None:
    res = renderer._render_plain(spec, clip_region=False)
    if res is None:
        return
    sub, sx, sy, _ = res
    dx, dy = sx - px0, sy - py0
    tmp = Image.new("RGBA", dst.size, (0, 0, 0, 0))
    tmp.paste(sub, (dx, dy))
    if clip_mask is not None:
        tmp.putalpha(ImageChops.multiply(tmp.getchannel("A"), clip_mask))
    dst.alpha_composite(tmp)


def _render_slider(renderer, el: dict, st: dict, region: tuple[int, int, int, int],
                   layer: Image.Image, data_map: dict) -> None:
    px0, py0, _, _ = region
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    ew, eh = max(16.0, float(el.get("width", 220))), max(16.0, float(el.get("height", 28)))
    lo, hi = float(el.get("min", 0.0)), float(el.get("max", 100.0))
    if hi <= lo:
        hi = lo + 1.0
    bkey = el.get("bind")
    raw_val = data_map[bkey] if (bkey and bkey in data_map and data_map[bkey] is not None) else el.get("value", (lo + hi) * 0.5)
    try:
        val = float(raw_val)
    except (TypeError, ValueError):
        val = (lo + hi) * 0.5
    frac = max(0.0, min(1.0, (val - lo) / (hi - lo)))
    track_h = max(4.0, min(eh * 0.36, float(el.get("track_height", 8.0))))
    thumb_r = max(6.0, min(eh * 0.46, float(el.get("thumb_radius", max(9.0, track_h * 1.15)))))
    cy = y + eh * 0.5
    tx0, tw = x + thumb_r, max(8.0, ew - thumb_r * 2.0)
    cx = tx0 + tw * frac
    track_col = str(el.get("track_color", "#1e293b"))
    fill_col = str(el.get("fill_color", "#38bdf8"))
    thumb_col = str(el.get("thumb_color", "#f8fafc"))

    _composite_sub(renderer, layer, px0, py0, {
        "id": f"{el['id']}__tr", "type": "rect", "x": tx0, "y": cy - track_h * 0.5,
        "width": tw, "height": track_h, "radius": track_h * 0.5,
        "style": {"fill": track_col, "stroke": {"color": "#ffffff@0.1", "width": 1, "align": "inside"}},
    })
    if frac > 0.005:
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__fl", "type": "rect", "x": tx0, "y": cy - track_h * 0.5,
            "width": max(track_h, tw * frac), "height": track_h, "radius": track_h * 0.5,
            "style": {"fill": fill_col},
        })
    _composite_sub(renderer, layer, px0, py0, {
        "id": f"{el['id']}__th", "type": "ellipse", "cx": cx, "cy": cy, "rx": thumb_r, "ry": thumb_r,
        "style": {
            "fill": thumb_col,
            "stroke": {"color": fill_col, "width": 2.0, "align": "inside"},
            "shadow": {"color": "#000000@0.45", "blur": 6, "dy": 2},
        },
    })
    fsize = float(el.get("size", 13))
    if el.get("label"):
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__lbl", "type": "text", "text": str(el["label"]),
            "x": x + 2, "y": y - 5, "anchor": "bottom-left",
            "size": max(11.0, fsize), "font": el.get("font") or "Inter", "weight": 600,
            "style": {"fill": str(el.get("text_color", "#cbd5e1"))},
        })
        if el.get("show_value", True):
            vtxt = f"{int(round(val))}" if abs(val - round(val)) < 1e-4 else f"{val:.1f}"
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__val", "type": "text", "text": vtxt,
                "x": x + ew - 2, "y": y - 5, "anchor": "bottom-right",
                "size": max(11.0, fsize), "font": el.get("font") or "JetBrains Mono", "weight": 600,
                "style": {"fill": fill_col},
            })


def _render_toggle(renderer, el: dict, st: dict, region: tuple[int, int, int, int],
                   layer: Image.Image, data_map: dict) -> None:
    px0, py0, _, _ = region
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    ew, eh = max(16.0, float(el.get("width", 52))), max(16.0, float(el.get("height", 28)))
    bkey = el.get("bind")
    raw_chk = data_map[bkey] if (bkey and bkey in data_map and data_map[bkey] is not None) else el.get("checked", False)
    checked = bool(raw_chk)
    variant = str(el.get("variant", "switch")).lower()
    on_col = str(el.get("on_color", "#22c55e"))
    off_col = str(el.get("off_color", "#334155"))
    thumb_col = str(el.get("thumb_color", "#ffffff"))

    if variant == "checkbox":
        box_s = min(ew, eh)
        by = y + (eh - box_s) * 0.5
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__cb", "type": "rect", "x": x, "y": by, "width": box_s, "height": box_s,
            "radius": max(4.0, box_s * 0.22),
            "style": {
                "fill": on_col if checked else "#0f172a@0.9",
                "stroke": {"color": on_col if checked else "#64748b", "width": 1.8, "align": "inside"},
            },
        })
        if checked:
            p1x, p1y = x + box_s * 0.24, by + box_s * 0.52
            p2x, p2y = x + box_s * 0.44, by + box_s * 0.72
            p3x, p3y = x + box_s * 0.78, by + box_s * 0.30
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__ck", "type": "path",
                "d": f"M {p1x:.2f} {p1y:.2f} L {p2x:.2f} {p2y:.2f} L {p3x:.2f} {p3y:.2f}",
                "closed": False,
                "style": {"fill": None, "stroke": {"color": thumb_col, "width": max(2.0, box_s * 0.12), "align": "center", "join": "round"}},
            })
        lbl_x = x + box_s + 10.0
    else:
        pad_t = max(2.5, eh * 0.12)
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__sw", "type": "rect", "x": x, "y": y, "width": ew, "height": eh, "radius": eh * 0.5,
            "style": {"fill": on_col if checked else off_col, "stroke": {"color": "#ffffff@0.15", "width": 1, "align": "inside"}},
        })
        kr = (eh - pad_t * 2.0) * 0.5
        kx = (x + ew - pad_t - kr) if checked else (x + pad_t + kr)
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__kn", "type": "ellipse", "cx": kx, "cy": y + eh * 0.5, "rx": kr, "ry": kr,
            "style": {"fill": thumb_col, "shadow": {"color": "#000000@0.35", "blur": 4, "dy": 1}},
        })
        lbl_x = x + ew + 10.0

    if el.get("label"):
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__lbl", "type": "text", "text": str(el["label"]),
            "x": lbl_x, "y": y + eh * 0.5, "anchor": "middle-left",
            "size": float(el.get("size", 14)), "font": el.get("font") or "Inter", "weight": 500,
            "style": {"fill": str(el.get("text_color", "#f8fafc"))},
        })


def _render_dropdown(renderer, el: dict, st: dict, region: tuple[int, int, int, int],
                     layer: Image.Image, data_map: dict) -> None:
    px0, py0, _, _ = region
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    ew, eh = max(16.0, float(el.get("width", 220))), max(20.0, float(el.get("height", 40)))
    bg_el = {
        "id": f"{el['id']}__bg", "type": "rect", "x": x, "y": y, "width": ew, "height": eh,
        "radius": el.get("radius", 8), "corner": str(el.get("corner", "round")),
        "style": _default_input_style(el, st),
    }
    _composite_sub(renderer, layer, px0, py0, bg_el)
    clip_m = renderer.shape_mask(bg_el, region)
    opts = [str(o) for o in (el.get("options") or [])]
    bkey = el.get("bind")
    sel_raw = data_map[bkey] if (bkey and bkey in data_map and data_map[bkey] is not None) else el.get("selected", 0)
    if isinstance(sel_raw, str) and sel_raw in opts:
        shown = sel_raw
    elif isinstance(sel_raw, int) and 0 <= sel_raw < len(opts):
        shown = opts[sel_raw]
    else:
        shown = opts[0] if opts else ""
    display_txt = shown if shown else str(el.get("placeholder") or "Select...")
    pad_x, fsize = float(el.get("padding", 12)), float(el.get("size", 14))
    tcol = str(el.get("text_color", "#f8fafc") if shown else el.get("placeholder_color", "#94a3b8"))
    _composite_sub(renderer, layer, px0, py0, {
        "id": f"{el['id']}__txt", "type": "text", "text": display_txt,
        "x": x + pad_x, "y": y + eh * 0.5, "anchor": "middle-left",
        "size": fsize, "font": el.get("font") or "Inter", "weight": 500, "style": {"fill": tcol},
    }, clip_mask=clip_m)
    cx, cy = x + ew - pad_x - 5.0, y + eh * 0.5
    _composite_sub(renderer, layer, px0, py0, {
        "id": f"{el['id']}__chv", "type": "path",
        "d": f"M {cx - 5:.2f} {cy - 2.5:.2f} L {cx:.2f} {cy + 2.8:.2f} L {cx + 5:.2f} {cy - 2.5:.2f}",
        "closed": False,
        "style": {"fill": None, "stroke": {"color": "#94a3b8", "width": 1.8, "align": "center", "join": "round"}},
    }, clip_mask=clip_m)
    if el.get("label"):
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__lbl", "type": "text", "text": str(el["label"]),
            "x": x + 2, "y": y - 6, "anchor": "bottom-left",
            "size": max(11.0, fsize * 0.85), "font": el.get("font") or "Inter", "weight": 600,
            "style": {"fill": "#cbd5e1"},
        })


def _render_input(renderer, el: dict, st: dict, region: tuple[int, int, int, int],
                  layer: Image.Image, data_map: dict) -> None:
    px0, py0, _, _ = region
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    ew, eh = max(16.0, float(el.get("width", 220))), max(20.0, float(el.get("height", 40)))
    bg_el = {
        "id": f"{el['id']}__bg", "type": "rect", "x": x, "y": y, "width": ew, "height": eh,
        "radius": el.get("radius", 8), "corner": str(el.get("corner", "round")),
        "style": _default_input_style(el, st),
    }
    _composite_sub(renderer, layer, px0, py0, bg_el)
    clip_m = renderer.shape_mask(bg_el, region)
    bkey = el.get("bind")
    val = str(data_map[bkey]) if (bkey and bkey in data_map and data_map[bkey] is not None) else str(el.get("value") or "")
    itype = str(el.get("input_type", "text")).lower()
    shown = ("•" * len(val)) if (val and itype == "password") else val
    display_txt = shown if shown else str(el.get("placeholder") or "")
    pad_x, fsize = float(el.get("padding", 12)), float(el.get("size", 15))
    tcol = str(el.get("placeholder_color", "#94a3b8") if not shown else el.get("text_color", "#f8fafc"))

    if display_txt:
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__txt", "type": "text", "text": display_txt,
            "x": x + pad_x, "y": y + eh * 0.5, "anchor": "middle-left",
            "size": fsize, "font": el.get("font") or "Inter", "weight": el.get("weight", 400),
            "style": {"fill": tcol},
        }, clip_mask=clip_m)

    if bool(el.get("focused")):
        caret_x = x + pad_x + 1.5
        if shown:
            from .render import TextLayout
            tl = TextLayout(
                {"type": "text", "text": shown, "x": x + pad_x, "y": y + eh * 0.5, "anchor": "middle-left",
                 "size": fsize, "font": el.get("font") or "Inter", "weight": el.get("weight", 400)},
                {"fill": tcol}, renderer.fonts, 2.0, shown, renderer.text_lang(el),
            )
            caret_x = tl.box_units()[2] + 2.5
        caret_x = min(caret_x, x + ew - pad_x)
        caret_h = min(eh * 0.56, fsize * 1.25)
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__caret", "type": "rect", "x": caret_x, "y": y + (eh - caret_h) * 0.5,
            "width": 1.8, "height": caret_h, "radius": 0.9, "style": {"fill": "#38bdf8"},
        }, clip_mask=clip_m)

    if el.get("label"):
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__lbl", "type": "text", "text": str(el["label"]),
            "x": x + 2, "y": y - 6, "anchor": "bottom-left",
            "size": max(11.0, fsize * 0.8), "font": el.get("font") or "Inter", "weight": 600,
            "style": {"fill": "#cbd5e1"},
        })


def _render_scroll(renderer, el: dict, st: dict, region: tuple[int, int, int, int],
                   layer: Image.Image, data_map: dict) -> None:
    px0, py0, _, _ = region
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    ew, eh = max(16.0, float(el.get("width", 280))), max(20.0, float(el.get("height", 180)))
    bg_el = {
        "id": f"{el['id']}__bg", "type": "rect", "x": x, "y": y, "width": ew, "height": eh,
        "radius": el.get("radius", 10), "corner": str(el.get("corner", "round")),
        "style": _default_scroll_style(el, st),
    }
    _composite_sub(renderer, layer, px0, py0, bg_el)
    clip_m = renderer.shape_mask(bg_el, region)

    pad, gap = float(el.get("padding", 10)), float(el.get("gap", 8))
    direction = str(el.get("direction", "vertical")).lower()
    show_bar = bool(el.get("show_scrollbar", True))
    sb_w = float(el.get("scrollbar_width", 6)) if show_bar else 0.0
    items = el.get("items") or []
    scroll_off = max(0.0, min(1.0, float(el.get("scroll_offset", 0.0))))
    inner_w = max(24.0, ew - pad * 2 - (sb_w + 8.0 if (show_bar and direction != "horizontal") else 0.0))
    inner_h = max(24.0, eh - pad * 2 - (sb_w + 8.0 if (show_bar and direction == "horizontal") else 0.0))
    row_h, item_w = float(el.get("item_height", 38)), float(el.get("item_width", 120))

    if direction == "horizontal":
        total_span = max(inner_w, float(el.get("content_width") or (len(items) * (item_w + gap) - gap if items else ew * 1.6)))
        shift_px = scroll_off * max(0.0, total_span - inner_w)
    else:
        total_span = max(inner_h, float(el.get("content_height") or (len(items) * (row_h + gap) - gap if items else eh * 1.6)))
        shift_px = scroll_off * max(0.0, total_span - inner_h)

    item_fill, item_text = str(el.get("item_fill", "#1e293b@0.75")), str(el.get("item_color", "#e2e8f0"))
    item_sub, fsize = str(el.get("subtitle_color", "#94a3b8")), float(el.get("size", 13))

    for i, raw_item in enumerate(items):
        if isinstance(raw_item, dict):
            title = str(raw_item.get("title") or raw_item.get("label") or raw_item.get("text") or f"Item {i + 1}")
            sub_t, badge = str(raw_item.get("subtitle") or ""), str(raw_item.get("badge") or "")
        else:
            title, sub_t, badge = str(raw_item), "", ""
        if direction == "horizontal":
            ix, iy, iw, ih = x + pad + i * (item_w + gap) - shift_px, y + pad, item_w, inner_h
            if ix + iw < x or ix > x + ew:
                continue
        else:
            ix, iy, iw, ih = x + pad, y + pad + i * (row_h + gap) - shift_px, inner_w, row_h
            if iy + ih < y or iy > y + eh:
                continue
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__item_{i}", "type": "rect", "x": ix, "y": iy, "width": iw, "height": ih, "radius": 6,
            "style": {"fill": item_fill, "stroke": {"color": "#ffffff@0.08", "width": 1, "align": "inside"}},
        }, clip_mask=clip_m)
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__itxt_{i}", "type": "text", "text": title,
            "x": ix + 10, "y": iy + (ih * 0.36 if sub_t else ih * 0.5), "anchor": "middle-left",
            "size": fsize, "font": el.get("font") or "Inter", "weight": 600 if sub_t else 500,
            "style": {"fill": item_text},
        }, clip_mask=clip_m)
        if sub_t:
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__isub_{i}", "type": "text", "text": sub_t,
                "x": ix + 10, "y": iy + ih * 0.72, "anchor": "middle-left",
                "size": max(10.0, fsize * 0.82), "font": el.get("font") or "Inter", "weight": 400,
                "style": {"fill": item_sub},
            }, clip_mask=clip_m)
        if badge:
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__ibdg_{i}", "type": "text", "text": badge,
                "x": ix + iw - 10, "y": iy + ih * 0.5, "anchor": "middle-right",
                "size": max(10.0, fsize * 0.85), "font": el.get("font") or "Inter", "weight": 700,
                "style": {"fill": "#38bdf8"},
            }, clip_mask=clip_m)

    if show_bar:
        track_col = str(el.get("scrollbar_track", "#0f172a@0.5"))
        thumb_col = str(el.get("scrollbar_color", "#94a3b8@0.58"))
        if direction == "horizontal":
            tx, ty, tw, th = x + pad, y + eh - sb_w - 5, max(16.0, ew - pad * 2), sb_w
            thumb_len = max(24.0, tw * min(1.0, inner_w / max(1.0, total_span)))
            thumb_rect = (tx + (tw - thumb_len) * scroll_off, ty, thumb_len, th)
        else:
            tx, ty, tw, th = x + ew - sb_w - 5, y + pad, sb_w, max(16.0, eh - pad * 2)
            thumb_len = max(24.0, th * min(1.0, inner_h / max(1.0, total_span)))
            thumb_rect = (tx, ty + (th - thumb_len) * scroll_off, tw, thumb_len)
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__sb_tr", "type": "rect", "x": tx, "y": ty, "width": tw, "height": th,
            "radius": sb_w * 0.5, "style": {"fill": track_col},
        }, clip_mask=clip_m)
        _composite_sub(renderer, layer, px0, py0, {
            "id": f"{el['id']}__sb_th", "type": "rect", "x": thumb_rect[0], "y": thumb_rect[1],
            "width": thumb_rect[2], "height": thumb_rect[3], "radius": sb_w * 0.5, "style": {"fill": thumb_col},
        }, clip_mask=clip_m)


_WIDGET_RENDERERS = {
    "slider": _render_slider,
    "toggle": _render_toggle,
    "dropdown": _render_dropdown,
    "input": _render_input,
    "scroll": _render_scroll,
}


def render_widget(renderer, el: dict, st: dict, region: tuple[int, int, int, int]) -> tuple[Image.Image, Image.Image]:
    """Dispatch widget rendering to its focused renderer and return (alpha_mask, rgba_layer)."""
    _, _, w, h = region
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fn = _WIDGET_RENDERERS.get(el["type"], _render_scroll)
    fn(renderer, el, st, region, layer, renderer.canvas.get("data") or {})
    return layer.getchannel("A"), layer


def widget_colors_summary(el: dict, colors: dict) -> dict[str, Any]:
    """Return resolved RGBA tuples for widget background, border and text for native exporters."""
    st = el.get("style") if isinstance(el.get("style"), dict) else {}
    fill_raw = st.get("fill") or ("#0f172a@0.92" if el["type"] in ("input", "dropdown") else "#0b1120@0.88")
    if isinstance(fill_raw, dict):
        stops = fill_raw.get("stops") or []
        if stops:
            s0 = stops[0]
            fill_raw = s0[1] if isinstance(s0, (list, tuple)) and len(s0) == 2 else s0
        else:
            fill_raw = "#0f172a"
    if not isinstance(fill_raw, str):
        fill_raw = "#0f172a"
    stroke_raw = st.get("stroke")
    if isinstance(stroke_raw, dict):
        border_col = str(stroke_raw.get("color", "#475569"))
        border_w = float(stroke_raw.get("width", 1.25))
    elif isinstance(stroke_raw, str):
        border_col, border_w = stroke_raw, 1.25
    else:
        border_col, border_w = ("#38bdf8" if el.get("focused") else "#475569@0.75"), 1.25
    text_col = str(el.get("text_color") or el.get("item_color") or "#f8fafc")
    ph_col = str(el.get("placeholder_color") or "#94a3b8")
    return {
        "bg": parse_color(fill_raw, colors),
        "border": parse_color(border_col, colors),
        "border_width": border_w,
        "text": parse_color(text_col, colors),
        "placeholder": parse_color(ph_col, colors),
    }
