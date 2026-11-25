"""Interactive widget canvas renderers for first-class native Input and Scroll elements.

Each widget renders into a crisp RGBA layer using the same vector geometry, PBR/fill paint pipeline,
font shaping and clipping as standard shapes, while preserving semantic metadata so Web/React,
Godot, Unity UI Toolkit, Unity uGUI, Roblox, WPF, Avalonia, WinUI, Qt QML and Dear ImGui export
them as genuine native interactive controls.
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
    if clip_mask is not None:
        tmp = Image.new("RGBA", dst.size, (0, 0, 0, 0))
        tmp.paste(sub, (dx, dy))
        tmp.putalpha(ImageChops.multiply(tmp.getchannel("A"), clip_mask))
        dst.alpha_composite(tmp)
    else:
        tmp = Image.new("RGBA", dst.size, (0, 0, 0, 0))
        tmp.paste(sub, (dx, dy))
        dst.alpha_composite(tmp)


def render_widget(renderer, el: dict, st: dict, region: tuple[int, int, int, int]) -> tuple[Image.Image, Image.Image]:
    """Render an 'input' or 'scroll' element into (alpha_mask, rgba_layer) covering region."""
    px0, py0, w, h = region
    x = float(el.get("x", 0))
    y = float(el.get("y", 0))
    ew = max(16.0, float(el.get("width", 220)))
    eh = max(20.0, float(el.get("height", 40 if el["type"] == "input" else 180)))
    rad = el.get("radius", 8 if el["type"] == "input" else 10)
    corner = str(el.get("corner", "round"))

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    if el["type"] == "input":
        bg_st = _default_input_style(el, st)
        bg_el = {
            "id": f"{el['id']}__bg",
            "type": "rect",
            "x": x,
            "y": y,
            "width": ew,
            "height": eh,
            "radius": rad,
            "corner": corner,
            "style": bg_st,
        }
        _composite_sub(renderer, layer, px0, py0, bg_el)
        clip_m = renderer.shape_mask(bg_el, region)

        val = str(el.get("value") or "")
        bind_key = el.get("bind")
        data_map = renderer.canvas.get("data") or {}
        if bind_key and bind_key in data_map and data_map[bind_key] is not None:
            val = str(data_map[bind_key])
        itype = str(el.get("input_type", "text")).lower()
        shown = ("•" * len(val)) if (val and itype == "password") else val
        is_ph = not bool(shown)
        display_txt = shown if shown else str(el.get("placeholder") or "")
        pad_x = float(el.get("padding", 12))
        fsize = float(el.get("size", 15))
        tcol = str(el.get("placeholder_color", "#94a3b8") if is_ph else el.get("text_color", "#f8fafc"))

        if display_txt:
            txt_el = {
                "id": f"{el['id']}__txt",
                "type": "text",
                "text": display_txt,
                "x": x + pad_x,
                "y": y + eh * 0.5,
                "anchor": "middle-left",
                "size": fsize,
                "font": el.get("font") or "Inter",
                "weight": el.get("weight", 400),
                "style": {"fill": tcol},
            }
            _composite_sub(renderer, layer, px0, py0, txt_el, clip_mask=clip_m)

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
            caret_el = {
                "id": f"{el['id']}__caret",
                "type": "rect",
                "x": caret_x,
                "y": y + (eh - caret_h) * 0.5,
                "width": 1.8,
                "height": caret_h,
                "radius": 0.9,
                "style": {"fill": "#38bdf8"},
            }
            _composite_sub(renderer, layer, px0, py0, caret_el, clip_mask=clip_m)

        if el.get("label"):
            lbl_el = {
                "id": f"{el['id']}__lbl",
                "type": "text",
                "text": str(el["label"]),
                "x": x + 2,
                "y": y - 6,
                "anchor": "bottom-left",
                "size": max(11.0, fsize * 0.8),
                "font": el.get("font") or "Inter",
                "weight": 600,
                "style": {"fill": "#cbd5e1"},
            }
            _composite_sub(renderer, layer, px0, py0, lbl_el)

        return layer.getchannel("A"), layer

    bg_st = _default_scroll_style(el, st)
    bg_el = {
        "id": f"{el['id']}__bg",
        "type": "rect",
        "x": x,
        "y": y,
        "width": ew,
        "height": eh,
        "radius": rad,
        "corner": corner,
        "style": bg_st,
    }
    _composite_sub(renderer, layer, px0, py0, bg_el)
    clip_m = renderer.shape_mask(bg_el, region)

    pad = float(el.get("padding", 10))
    gap = float(el.get("gap", 8))
    direction = str(el.get("direction", "vertical")).lower()
    show_bar = bool(el.get("show_scrollbar", True))
    sb_w = float(el.get("scrollbar_width", 6)) if show_bar else 0.0
    items = el.get("items") or []
    scroll_off = max(0.0, min(1.0, float(el.get("scroll_offset", 0.0))))

    inner_w = max(24.0, ew - pad * 2 - (sb_w + 8.0 if (show_bar and direction != "horizontal") else 0.0))
    inner_h = max(24.0, eh - pad * 2 - (sb_w + 8.0 if (show_bar and direction == "horizontal") else 0.0))
    row_h = float(el.get("item_height", 38))
    item_w = float(el.get("item_width", 120))

    if direction == "horizontal":
        total_span = max(inner_w, float(el.get("content_width") or (len(items) * (item_w + gap) - gap if items else ew * 1.6)))
        shift_px = scroll_off * max(0.0, total_span - inner_w)
    else:
        total_span = max(inner_h, float(el.get("content_height") or (len(items) * (row_h + gap) - gap if items else eh * 1.6)))
        shift_px = scroll_off * max(0.0, total_span - inner_h)

    item_fill = str(el.get("item_fill", "#1e293b@0.75"))
    item_text = str(el.get("item_color", "#e2e8f0"))
    item_sub = str(el.get("subtitle_color", "#94a3b8"))
    fsize = float(el.get("size", 13))

    for i, raw_item in enumerate(items):
        if isinstance(raw_item, dict):
            title = str(raw_item.get("title") or raw_item.get("label") or raw_item.get("text") or f"Item {i + 1}")
            sub_t = str(raw_item.get("subtitle") or "")
            badge = str(raw_item.get("badge") or "")
        else:
            title, sub_t, badge = str(raw_item), "", ""

        if direction == "horizontal":
            ix = x + pad + i * (item_w + gap) - shift_px
            iy = y + pad
            iw, ih = item_w, inner_h
            if ix + iw < x or ix > x + ew:
                continue
        else:
            ix = x + pad
            iy = y + pad + i * (row_h + gap) - shift_px
            iw, ih = inner_w, row_h
            if iy + ih < y or iy > y + eh:
                continue

        card_el = {
            "id": f"{el['id']}__item_{i}",
            "type": "rect",
            "x": ix,
            "y": iy,
            "width": iw,
            "height": ih,
            "radius": 6,
            "style": {"fill": item_fill, "stroke": {"color": "#ffffff@0.08", "width": 1, "align": "inside"}},
        }
        _composite_sub(renderer, layer, px0, py0, card_el, clip_mask=clip_m)

        ty = iy + (ih * 0.36 if sub_t else ih * 0.5)
        t_el = {
            "id": f"{el['id']}__itxt_{i}",
            "type": "text",
            "text": title,
            "x": ix + 10,
            "y": ty,
            "anchor": "middle-left",
            "size": fsize,
            "font": el.get("font") or "Inter",
            "weight": 600 if sub_t else 500,
            "style": {"fill": item_text},
        }
        _composite_sub(renderer, layer, px0, py0, t_el, clip_mask=clip_m)

        if sub_t:
            s_el = {
                "id": f"{el['id']}__isub_{i}",
                "type": "text",
                "text": sub_t,
                "x": ix + 10,
                "y": iy + ih * 0.72,
                "anchor": "middle-left",
                "size": max(10.0, fsize * 0.82),
                "font": el.get("font") or "Inter",
                "weight": 400,
                "style": {"fill": item_sub},
            }
            _composite_sub(renderer, layer, px0, py0, s_el, clip_mask=clip_m)

        if badge:
            b_el = {
                "id": f"{el['id']}__ibdg_{i}",
                "type": "text",
                "text": badge,
                "x": ix + iw - 10,
                "y": iy + ih * 0.5,
                "anchor": "middle-right",
                "size": max(10.0, fsize * 0.85),
                "font": el.get("font") or "Inter",
                "weight": 700,
                "style": {"fill": "#38bdf8"},
            }
            _composite_sub(renderer, layer, px0, py0, b_el, clip_mask=clip_m)

    if show_bar:
        track_col = str(el.get("scrollbar_track", "#0f172a@0.5"))
        thumb_col = str(el.get("scrollbar_color", "#94a3b8@0.58"))
        if direction == "horizontal":
            tx, ty, tw, th = x + pad, y + eh - sb_w - 5, max(16.0, ew - pad * 2), sb_w
            ratio = min(1.0, inner_w / max(1.0, total_span))
            thumb_len = max(24.0, tw * ratio)
            thumb_x = tx + (tw - thumb_len) * scroll_off
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__sb_tr", "type": "rect", "x": tx, "y": ty, "width": tw, "height": th,
                "radius": sb_w * 0.5, "style": {"fill": track_col},
            }, clip_mask=clip_m)
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__sb_th", "type": "rect", "x": thumb_x, "y": ty, "width": thumb_len, "height": th,
                "radius": sb_w * 0.5, "style": {"fill": thumb_col},
            }, clip_mask=clip_m)
        else:
            tx, ty, tw, th = x + ew - sb_w - 5, y + pad, sb_w, max(16.0, eh - pad * 2)
            ratio = min(1.0, inner_h / max(1.0, total_span))
            thumb_len = max(24.0, th * ratio)
            thumb_y = ty + (th - thumb_len) * scroll_off
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__sb_tr", "type": "rect", "x": tx, "y": ty, "width": tw, "height": th,
                "radius": sb_w * 0.5, "style": {"fill": track_col},
            }, clip_mask=clip_m)
            _composite_sub(renderer, layer, px0, py0, {
                "id": f"{el['id']}__sb_th", "type": "rect", "x": tx, "y": thumb_y, "width": tw, "height": thumb_len,
                "radius": sb_w * 0.5, "style": {"fill": thumb_col},
            }, clip_mask=clip_m)

    return layer.getchannel("A"), layer


def widget_colors_summary(el: dict, colors: dict) -> dict[str, Any]:
    """Return resolved RGBA tuples for widget background, border and text for native exporters."""
    st = el.get("style") if isinstance(el.get("style"), dict) else {}
    fill_raw = st.get("fill") or ("#0f172a@0.92" if el["type"] == "input" else "#0b1120@0.88")
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
