"""Hand-off tools: 9-slice stretch test, developer spec, design tokens, clickable prototype and
engine scene export (Godot .tscn, Roblox Luau, Unity UI Toolkit UXML/USS)."""

from __future__ import annotations

import base64
import copy
import html
import json
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL import ImageDraw

from . import export as ex
from . import shaping
from .colors import parse_color, to_hex
from .render import TextLayout, _stroke_specs, resolve_style
from .server import (Image, _gradient_blocks, _label_font, _maybe_json, _out_dir, _out_path, _png_bytes,
                     backdrop, store, tool)
from .store import slugify

__all__ = ["preview_nine_slice", "export_spec", "export_theme", "set_link", "set_interaction", "set_binding",
           "live_preview", "export_prototype", "export_screen", "export_project"]

_STUDIO = None

_TRIGGERS = ("load", "hover", "leave", "press", "release", "click")
_ACTIONS = ("play", "stop", "set_state", "clear_state", "toggle_state", "navigate", "overlay", "back", "url",
            "set_data", "reset_data")



def _borders_for(c: dict, img: PILImage.Image, nine_slice: Any) -> dict:
    nine = _maybe_json(nine_slice)
    if isinstance(nine, dict):
        return {k: int(round(float(nine[k]))) for k in ("left", "top", "right", "bottom")}
    bx, by = _gradient_blocks(c, (c["width"] / 2, c["height"] / 2))
    return ex.detect_nine_slice(img, block_x=bx, block_y=by)


@tool
def preview_nine_slice(canvas: str, sizes: list[list[int]] | None = None, nine_slice: str | dict = "auto",
                       background: str = "checker", without_text: bool = False):
    """Show how a 9-sliced asset looks when the engine stretches it to other sizes - before exporting.
    Corners must stay crisp, edges must not smear, gradients must not band or skew. Red lines mark the
    slice borders on the original. sizes default: wider, taller, much bigger and smaller versions.
    nine_slice: "auto" (same detection as export_asset) or {"left", "top", "right", "bottom"}.
    without_text: test the frame alone, the way it is used when the label is engine text (recommended
    for buttons and panels: text baked into a 9-slice smears when stretched)."""
    st = store()
    c = st.get(canvas)
    if without_text:
        c = dict(c, elements=[e for e in c["elements"] if e["type"] != "text"])
    img = st.renderer(c).render(include_background=False)
    b = _borders_for(c, img, nine_slice)
    w, h = img.size
    wanted = _maybe_json(sizes) or [[w * 2, h], [w, int(h * 1.8)], [int(w * 2.5), int(h * 1.6)],
                                    [max(b["left"] + b["right"] + 4, int(w * 0.6)), h]]
    tiles = [("original", img)]
    for size in wanted:
        tw, th = int(size[0]), int(size[1])
        if tw < 1 or th < 1 or tw > 4096 or th > 4096:
            raise ValueError("sizes must be between 1 and 4096")
        tiles.append((f"{tw}x{th}", ex.nine_slice_stretch(img, b, tw, th)))
    pad, label_h = 12, 18
    scale = min(1.0, 900 / max(t[1].width for t in tiles))
    shown = [(n, t.resize((max(1, int(t.width * scale)), max(1, int(t.height * scale))), PILImage.LANCZOS)) for n, t in tiles]
    W = sum(t.width for _, t in shown) + pad * (len(shown) + 1)
    H = max(t.height for _, t in shown) + label_h + 2 * pad
    sheet = PILImage.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    font = _label_font(12)
    x = pad
    for i, (name, t) in enumerate(shown):
        tile = PILImage.alpha_composite(backdrop(t.size, background, st.theme.get("colors", {})), t)
        sheet.paste(tile.convert("RGB"), (x, pad))
        if i == 0:
            dd = ImageDraw.Draw(sheet)
            for vx in (b["left"], w - b["right"]):
                dd.line([(x + vx * scale, pad), (x + vx * scale, pad + t.height)], fill=(255, 60, 60), width=1)
            for vy in (b["top"], h - b["bottom"]):
                dd.line([(x, pad + vy * scale), (x + t.width, pad + vy * scale)], fill=(255, 60, 60), width=1)
        d.text((x, pad + t.height + 3), name, fill="#ffffff", font=font)
        x += t.width + pad
    info = {"canvas": c["id"], "borders": {k: b[k] for k in ("left", "top", "right", "bottom")},
            "stretch_x": b.get("stretch_x", True), "stretch_y": b.get("stretch_y", True)}
    if b.get("stretch_x") is False or b.get("stretch_y") is False:
        info["note"] = ("auto detection found an axis that cannot stretch cleanly (gradient or content across the "
                        "centre); the stretched tiles show what happens anyway")
    return [Image(data=_png_bytes(sheet), format="png"), json.dumps(info)]



def _paint_hex(spec: Any, colors: dict) -> Any:
    if spec is None or spec == "none":
        return None
    if isinstance(spec, dict):
        stops = spec.get("stops") or []
        out = []
        for stop in stops:
            col = stop[1] if isinstance(stop, (list, tuple)) and len(stop) == 2 else stop
            try:
                out.append(to_hex(parse_color(col, colors)))
            except ValueError:
                pass
        return {"type": spec.get("type", "linear"), "stops": out} if out else {"type": spec.get("type")}
    try:
        return to_hex(parse_color(spec, colors))
    except ValueError:
        return str(spec)


def _first_color(spec: Any, colors: dict) -> tuple[int, int, int, int]:
    if isinstance(spec, dict):
        stops = spec.get("stops") or []
        if stops:
            first = stops[0]
            col = first[1] if isinstance(first, (list, tuple)) and len(first) == 2 else first
            return parse_color(col, colors)
        return parse_color(spec.get("color", "#ffffff"), colors)
    if spec is None:
        return (255, 255, 255, 255)
    return parse_color(spec, colors)


def _text_info(r, el: dict) -> dict:
    st = store()
    style = resolve_style(el.get("style"), st.theme)
    layout = TextLayout(el, style, st.fonts, 1.0, r.text_of(el))
    fill = style.get("fill", el.get("fill", "#ffffff"))
    info: dict = {"text": layout.text, "font": layout.family or "Inter", "weight": layout.weight,
                  "size": round(layout.size, 2), "letter_spacing": layout.spacing,
                  "line_height": layout.line_height, "align": layout.align,
                  "color": _paint_hex(fill, r.colors), "font_file": Path(layout.path).name if layout.path else None,
                  "_font_path": layout.path}
    strokes = _stroke_specs(style, r.colors)
    if strokes:
        info["outline"] = {"width": strokes[0]["width"], "color": _paint_hex(strokes[0]["paint"], r.colors)}
    sh = style.get("shadow")
    if isinstance(sh, list):
        sh = sh[0] if sh else None
    if isinstance(sh, dict):
        info["shadow"] = {"color": _paint_hex(sh.get("color", "#000000@0.5"), r.colors),
                          "dx": float(sh.get("dx", 0)), "dy": float(sh.get("dy", 4)), "blur": float(sh.get("blur", 8))}
    return info


@tool
def export_spec(canvas: str, out_dir: str | None = None, name: str | None = None, language: str | None = None):
    """Developer hand-off: a redline image (every element boxed with id, size and position; text with
    font / size / colour) plus <name>.spec.json with exact numbers - bounds, pins, colours (hex), text
    styles, states, animations, theme tokens - so whoever builds the screen in the engine does not guess."""
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, language)
    r = st.renderer(c, language=language)
    folder = _out_dir(out_dir, "spec")
    base = slugify(name or c["id"], "spec")
    colors = r.colors
    items = []
    for el in c["elements"]:
        if not el.get("visible", True):
            continue
        x0, y0, x1, y1 = r.element_box(el)
        style = resolve_style(el.get("style"), st.theme)
        item: dict = {"id": el["id"], "type": el["type"], "x": round(x0, 2), "y": round(y0, 2),
                      "width": round(x1 - x0, 2), "height": round(y1 - y0, 2)}
        for key in ("group", "layer", "pin", "radius", "rotation", "note"):
            if el.get(key):
                item[key] = el[key]
        if el["type"] == "text":
            info = _text_info(r, el)
            info.pop("_font_path", None)
            item["text"] = info
        else:
            if style.get("fill") is not None:
                item["fill"] = _paint_hex(style.get("fill"), colors)
            strokes = _stroke_specs(style, colors)
            if strokes:
                item["stroke"] = [{"width": s_["width"], "align": s_["align"], "color": _paint_hex(s_["paint"], colors)}
                                  for s_ in strokes]
            for fx in ("shadow", "glow", "inner_shadow", "inner_glow"):
                if style.get(fx):
                    item[fx] = style[fx]
            if style.get("opacity") is not None:
                item["opacity"] = style["opacity"]
        if el["type"] == "instance":
            item["source"] = el.get("source")
        items.append(item)
    spec = {"canvas": {"id": c["id"], "width": c["width"], "height": c["height"],
                       "safe_area_ltrb": c.get("safe_area"), "device": c.get("device")},
            "colors": {k: to_hex(parse_color(v, colors)) for k, v in colors.items()},
            "elements": items,
            "states": c.get("states") or {},
            "animations": {k: {"duration": a["duration"], "loop": a.get("loop", False),
                               "tracks": len(a.get("tracks", []))} for k, a in (c.get("animations") or {}).items()},
            "links": c.get("links") or {}}
    engine_text = shaping.engine_notes("all", [i["text"]["text"] for i in items if i["type"] == "text"])
    if engine_text:
        spec["engine_text_notes"] = engine_text
    (folder / f"{base}.spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")

    scale = min(2.0, 1600 / max(c["width"], c["height"]))
    img = st.renderer(c, scale, language=language).render()
    view = PILImage.alpha_composite(backdrop(img.size, "dark", {}), img)
    margin = 0
    d = ImageDraw.Draw(view, "RGBA")
    font = _label_font(11)
    palette = [(255, 77, 109), (77, 210, 255), (255, 210, 77), (125, 255, 122), (213, 155, 255)]
    for i, item in enumerate(items):
        col = palette[i % len(palette)]
        rx0, ry0 = item["x"] * scale, item["y"] * scale
        rx1 = max(rx0, (item["x"] + item["width"]) * scale - 1)
        ry1 = max(ry0, (item["y"] + item["height"]) * scale - 1)
        bx = [rx0, ry0, rx1, ry1]
        d.rectangle(bx, outline=col + (220,), width=1)
        label = f"{item['id']}  {item['width']:g}x{item['height']:g} @ {item['x']:g},{item['y']:g}"
        if item["type"] == "text":
            t = item["text"]
            label += f"  {t['font']} {t['weight']} {t['size']:g}px {t['color'] if isinstance(t['color'], str) else ''}"
        tw = d.textlength(label, font=font)
        lx, ly = max(0, bx[0]), max(0, bx[1] - 13)
        d.rectangle([lx, ly, lx + tw + 4, ly + 13], fill=(0, 0, 0, 170))
        d.text((lx + 2, ly), label, fill=col + (255,), font=font)
    out_png = folder / f"{base}.spec.png"
    view.convert("RGB").save(out_png)
    info = {"spec_json": str(folder / f"{base}.spec.json"), "spec_png": str(out_png), "elements": len(items)}
    if engine_text:
        info["engine_text_notes"] = engine_text
    shown = view.copy()
    shown.thumbnail((1200, 1200))
    return [Image(data=_png_bytes(shown.convert("RGB")), format="png"), json.dumps(info)]


def _ident(name: str, case: str) -> str:
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", name) if p]
    if not parts:
        parts = ["token"]
    if case == "pascal":
        out = "".join(p[:1].upper() + p[1:] for p in parts)
    elif case == "upper":
        out = "_".join(p.upper() for p in parts)
    elif case == "kebab":
        out = "-".join(p.lower() for p in parts)
    else:
        out = "_".join(p.lower() for p in parts)
    return ("_" + out) if out[0].isdigit() else out


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _rgba_hex(v) -> str:
    return "#" + "".join(f"{c:02x}" for c in v[:4])


@tool
def export_theme(format: str = "json", path: str | None = None):
    """Export the theme as design tokens for the engine or a web / app codebase, so code uses exactly
    the colours and text styles the art was drawn with.

    format: "json", "css" (custom properties + text classes), "uss" (Unity UI Toolkit variables +
    classes), "csharp" (static Color32 class), "gdscript" (Godot constants), "luau" (Roblox module with
    Color3 + transparency), "dtcg" (W3C design tokens JSON for Tokens Studio, Penpot, Style Dictionary;
    modes go into $extensions), "design.md" (DESIGN.md for AI design and coding agents:
    YAML front-matter tokens plus readable colour, type, spacing and component sections).
    Text styles (theme styles with font / size / weight) become typography tokens.
    """
    st = store()
    fmt = format.lower()
    ext = {"json": ".json", "css": ".css", "uss": ".uss", "csharp": ".cs", "gdscript": ".gd", "luau": ".luau",
           "dtcg": ".tokens.json", "design.md": ".md"}
    if fmt not in ext:
        raise ValueError(f"format must be one of {', '.join(ext)}")
    colors = st.theme.get("colors", {})
    rgba = {k: parse_color(v, colors) for k, v in colors.items()}
    numbers = st.theme.get("numbers") or {}
    modes = {name: {k: parse_color(v, {**colors, **vals}) for k, v in vals.items() if not _num(v)}
             for name, vals in (st.theme.get("modes") or {}).items()}
    mode_numbers = {name: {k: v for k, v in vals.items() if _num(v)}
                    for name, vals in (st.theme.get("modes") or {}).items()}
    text_styles = {}
    for name in st.theme.get("styles", {}):
        sty = resolve_style(name, st.theme)
        if any(k in sty for k in ("font", "size", "weight")):
            text_styles[name] = {k: sty[k] for k in ("font", "size", "weight", "letter_spacing", "uppercase", "italic")
                                 if k in sty}
            if "fill" in sty and not isinstance(sty["fill"], dict):
                try:
                    text_styles[name]["color"] = to_hex(parse_color(sty["fill"], colors))
                except ValueError:
                    pass
    lines: list[str] = []
    if fmt == "design.md":
        from .tokens import write_design_md
        title = Path(path).stem.replace("DESIGN", "").strip("_- ") if path else ""
        text = write_design_md(title or "UI kit", {k: to_hex(v) if v[3] == 255 else _rgba_hex(v) for k, v in rgba.items()},
                               numbers, text_styles, {m: {k: to_hex(v) for k, v in vals.items()} for m, vals in modes.items()},
                               st.theme.get("styles", {}))
    elif fmt == "dtcg":
        from .tokens import write_dtcg
        text = json.dumps(write_dtcg({k: to_hex(v) if v[3] == 255 else _rgba_hex(v) for k, v in rgba.items()}, numbers,
                                     text_styles, {m: {k: to_hex(v) for k, v in vals.items()} for m, vals in modes.items()},
                                     mode_numbers), ensure_ascii=False, indent=1)
    elif fmt == "json":
        text = json.dumps({"colors": {k: to_hex(v) for k, v in rgba.items()}, "numbers": numbers, "text_styles": text_styles,
                           "modes": {m: {k: to_hex(v) for k, v in vals.items()} for m, vals in modes.items()}},
                          ensure_ascii=False, indent=1)
    elif fmt in ("css", "uss"):
        lines.append(":root {")
        for k, v in rgba.items():
            lines.append(f"    --color-{_ident(k, 'kebab')}: {to_hex(v) if fmt == 'css' or v[3] == 255 else f'rgba({v[0]}, {v[1]}, {v[2]}, {round(v[3] / 255, 3)})'};")
        for k, v in numbers.items():
            lines.append(f"    --{_ident(k, 'kebab')}: {v:g}px;")
        lines.append("}")
        for mname, vals in modes.items():
            sel = f'[data-theme="{_ident(mname, "kebab")}"]' if fmt == "css" else f".theme-{_ident(mname, 'kebab')}"
            lines.append(sel + " {")
            for k, v in vals.items():
                lines.append(f"    --color-{_ident(k, 'kebab')}: {to_hex(v) if fmt == 'css' or v[3] == 255 else f'rgba({v[0]}, {v[1]}, {v[2]}, {round(v[3] / 255, 3)})'};")
            lines.append("}")
        for name, ts in text_styles.items():
            lines.append(f".text-{_ident(name, 'kebab')} {{")
            if fmt == "css" and ts.get("font"):
                lines.append(f"    font-family: '{ts['font']}';")
            if ts.get("size"):
                lines.append(f"    font-size: {ts['size']}px;")
            weight = str(ts.get("weight", ""))
            if fmt == "css" and weight:
                lines.append(f"    font-weight: {weight};")
            elif fmt == "uss" and (weight in ("bold", "black", "semibold", "extrabold") or (weight.isdigit() and int(weight) >= 600)):
                lines.append("    -unity-font-style: bold;")
            if ts.get("letter_spacing"):
                lines.append(f"    letter-spacing: {ts['letter_spacing']}px;")
            if ts.get("color"):
                lines.append(f"    color: {ts['color']};")
            if fmt == "css" and ts.get("uppercase"):
                lines.append("    text-transform: uppercase;")
            lines.append("}")
        text = "\n".join(lines) + "\n"
    elif fmt == "csharp":
        lines += ["// Generated by uiforge-mcp - design tokens", "using UnityEngine;", "",
                  "public static class UiTheme", "{"]
        for k, v in rgba.items():
            lines.append(f"    public static readonly Color32 {_ident(k, 'pascal')} = new Color32({v[0]}, {v[1]}, {v[2]}, {v[3]});")
        for name, ts in text_styles.items():
            if ts.get("size"):
                lines.append(f"    public const float {_ident(name, 'pascal')}FontSize = {float(ts['size'])}f;")
        lines.append("}")
        text = "\n".join(lines) + "\n"
    elif fmt == "gdscript":
        lines += ["# Generated by uiforge-mcp - design tokens", "class_name UiTheme", ""]
        for k, v in rgba.items():
            lines.append(f"const {_ident(k, 'upper')} := Color({v[0] / 255:.4f}, {v[1] / 255:.4f}, {v[2] / 255:.4f}, {v[3] / 255:.4f})")
        for name, ts in text_styles.items():
            lines.append(f"const TEXT_{_ident(name, 'upper')} := {json.dumps(ts, ensure_ascii=False)}")
        text = "\n".join(lines) + "\n"
    else:
        lines += ["-- Generated by uiforge-mcp - design tokens", "local Theme = {}", "", "Theme.colors = {"]
        for k, v in rgba.items():
            lines.append(f"\t{_ident(k, 'snake')} = Color3.fromRGB({v[0]}, {v[1]}, {v[2]}),")
        lines += ["}", "", "-- 0 = opaque, 1 = invisible (Roblox convention)", "Theme.transparency = {"]
        for k, v in rgba.items():
            lines.append(f"\t{_ident(k, 'snake')} = {round(1 - v[3] / 255, 3)},")
        lines += ["}", "", "Theme.text = {"]
        for name, ts in text_styles.items():
            lines.append(f"\t{_ident(name, 'snake')} = {{ size = {ts.get('size', 16)}, font = \"{ts.get('font', 'Inter')}\" }},")
        lines += ["}", "", "return Theme"]
        text = "\n".join(lines) + "\n"
    out = _out_path(path, "DESIGN.md" if fmt == "design.md" else "ui_theme" + ext[fmt], suffixes=tuple(ext.values()))
    out.write_text(text, encoding="utf-8")
    result = {"file": str(out), "colors": len(rgba), "text_styles": len(text_styles), "modes": sorted(modes)}
    if modes and fmt in ("csharp", "gdscript", "luau"):
        result["note"] = "this format holds the base colours only; use json, css or uss for every mode"
    return result



@tool
def set_link(canvas: str, id: str, target: str | None, mode: str = "navigate"):
    """Make an element clickable in export_prototype and export_web: target is another canvas id (a screen),
    "back", a URL (mode "url"), or null to remove the link. mode: "navigate" (go to the screen), "overlay"
    (open the screen on top - menus, dialogs, tooltips; its "back" link closes it) or "url". Hover / pressed looks come from the element's states automatically
    (an instance whose source has "hover" / "pressed" states, or this canvas's "hover" / "pressed"
    states that override this element)."""
    st = store()
    c = st.get(canvas)
    el = st.find(c, id)
    links = c.setdefault("links", {})
    mode = str(mode).lower()
    if mode not in ("navigate", "overlay", "url"):
        raise ValueError("mode must be 'navigate', 'overlay' or 'url'")
    if target is None:
        links.pop(el["id"], None)
    elif mode == "url":
        if not re.match(r"^(https?://|mailto:|#)", str(target)):
            raise ValueError("a url link must start with https://, http://, mailto: or #")
        links[el["id"]] = {"target": str(target), "mode": "url"}
    else:
        if target != "back":
            st.get(target)
            target = slugify(target)
        links[el["id"]] = target if mode == "navigate" else {"target": target, "mode": mode}
    if not links:
        c.pop("links", None)
    st.save_canvas(c)
    return {"canvas": c["id"], "links": c.get("links", {})}


@tool
def set_interaction(canvas: str, id: str, trigger: str, action: str, animation: str | None = None,
                    state: str | None = None, target: str | None = None, delay: float = 0,
                    sfx: str | None = None, data: dict | None = None, remove: bool = False):
    """A state machine for the canvas: when `trigger` happens on `id`, do `action`. Rules run in
    export_web and export_react, are listed in export_animation(format="json"), and generate controller
    scripts in export_screen (Unity, Godot, Roblox).

    id: an element id, "group:<name>", or "canvas" (for load / key / end triggers).
    trigger: "load", "hover", "leave", "press", "release", "click", "key:<Key>" (e.g. "key:Escape",
      "key:ArrowDown"), or "end:<animation>" (when that animation finishes - chain animations).
    action: "play" / "stop" an animation (it no longer autoplays once a rule plays it; restarts on each
      play), "set_state" / "clear_state" / "toggle_state" a canvas state (set_state looks: selected, open,
      muted, tab=2...), "set_data" (merges `data` dict into canvas reactive variables), "reset_data"
      (restores initial canvas defaults), "navigate" / "overlay" to another canvas, "back", or "url".
    delay: seconds before the action. sfx: optional sound / haptic event id (e.g. "ui_click", "ui_hover").
    data: dict of variable updates when action="set_data", e.g. {"volume": 80, "selected_weapon": "Railgun"}.
    remove=true deletes the rule with this id + trigger + action."""
    st = store()
    c = st.get(canvas)
    trigger = str(trigger).strip()
    action = str(action).lower()
    if remove:
        rows = [
            r for r in (c.get("interactions") or [])
            if not (
                r.get("id") == id
                and r.get("trigger") == trigger
                and str(r.get("action", "")).lower() == action
                and (animation is None or r.get("animation") == animation)
                and (state is None or r.get("state") == state)
            )
        ]
        if rows:
            c["interactions"] = rows
        else:
            c.pop("interactions", None)
        st.save_canvas(c)
        return {"canvas": c["id"], "interactions": rows}
    if id != "canvas":
        if id.startswith("group:"):
            if not any(e.get("group") == id[6:] for e in c["elements"]):
                raise ValueError(f"no group '{id[6:]}' on canvas '{c['id']}'")
        else:
            id = st.find(c, id)["id"]
    if trigger not in _TRIGGERS and not re.match(r"^(key:.+|end:.+)$", trigger):
        raise ValueError(f"trigger must be one of {', '.join(_TRIGGERS)}, key:<Key> or end:<animation>")
    if trigger.startswith("end:"):
        trigger = "end:" + st.get_animation(c, trigger[4:])[0]
    if action not in _ACTIONS:
        raise ValueError(f"action must be one of {', '.join(_ACTIONS)}")
    rule: dict = {"id": id, "trigger": trigger, "action": action}
    if action in ("play", "stop"):
        if not animation:
            raise ValueError(f'action "{action}" needs animation=<name>')
        rule["animation"] = st.get_animation(c, animation)[0]
    elif action.endswith("_state"):
        if not state:
            raise ValueError(f'action "{action}" needs state=<name> (define its look with set_state)')
        if state not in (c.get("states") or {}):
            known = ", ".join(sorted(c.get("states") or {})) or "(none)"
            raise ValueError(f"no state '{state}' on canvas '{c['id']}' - define it with set_state first. States: {known}")
        rule["state"] = state
    elif action in ("navigate", "overlay"):
        if not target:
            raise ValueError(f'action "{action}" needs target=<canvas id>')
        rule["target"] = st.get(target)["id"]
    elif action == "url":
        if not target or not re.match(r"^(https?://|mailto:)", str(target)):
            raise ValueError("action url needs target starting with https://, http:// or mailto:")
        rule["target"] = str(target)
    elif action == "set_data":
        parsed_data = _maybe_json(data)
        if not isinstance(parsed_data, dict) or not parsed_data:
            raise ValueError('action "set_data" needs data={...} dictionary of variable updates')
        rule["data"] = parsed_data
    if delay:
        rule["delay"] = max(0.0, float(delay))
    if sfx:
        sfx_clean = re.sub(r"[^A-Za-z0-9_.\-:/]", "", str(sfx))
        if not sfx_clean:
            raise ValueError("sfx must be a sound event name like 'ui_click' or 'hover_tick'")
        rule["sfx"] = sfx_clean
    key = (id, trigger, action, rule.get("animation"), rule.get("state"))
    rows = [r for r in (c.get("interactions") or [])
            if (r["id"], r["trigger"], r["action"], r.get("animation"), r.get("state")) != key]
    if not remove:
        rows.append(rule)
    if rows:
        c["interactions"] = rows
    else:
        c.pop("interactions", None)
    st.save_canvas(c)
    return {"canvas": c["id"], "interactions": rows}


@tool
def set_binding(canvas: str, data: dict | None = None, target: str | None = None, property: str | None = None,
                expr: str | None = None, remove: bool = False):
    """Bind canvas data variables to element properties (Rive / Envy style reactive UI).

    data: default variable values on the canvas, e.g. {"hp": 75, "max_hp": 100, "player": "Aria"}.
      Also fills {hp} / {player} placeholders in text elements automatically.
    target + property + expr: bind an element property to a safe expression evaluated against `data`:
      - Bar width:  target="hp_fill", property="width", expr="clamp(hp / max_hp, 0, 1) * 240"
      - Low-HP red: target="hp_fill", property="style.fill", expr="where(hp / max_hp < 0.25, '#ef4444', '#22c55e')"
      - Warning:    target="low_icon", property="visible", expr="hp < 25"
      - Text:       target="hp_txt", property="text", expr="pct(hp, max_hp)"
    Test different values with preview(canvas, data={"hp": 15}). Exported live to Web (window.uiforgeSetData),
    React (<Hud data={{ hp: 40 }} />), Unity C#, Godot GDScript and Roblox Luau.
    remove=true deletes the binding for (target, property)."""
    from . import binding
    st = store()
    c = st.get(canvas)
    st.checkpoint(c)
    try:
        if data is not None:
            parsed = _maybe_json(data)
            if not isinstance(parsed, dict):
                raise ValueError('data must be a JSON object like {"hp": 75, "max_hp": 100}')
            cur = dict(c.get("data") or {})
            for k, v in parsed.items():
                if not str(k).isidentifier() or str(k).startswith("_"):
                    raise ValueError(f"data variable '{k}' must be a plain identifier (letters, digits, _)")
                if v is None:
                    cur.pop(k, None)
                else:
                    cur[str(k)] = v
            if cur:
                c["data"] = cur
            else:
                c.pop("data", None)
        if target is not None:
            el = st.find(c, target)
            if not property:
                raise ValueError("property is required when binding a target (e.g. 'width', 'visible', 'style.fill')")
            prop = str(property).strip()
            rows = [r for r in (c.get("bindings") or []) if not (r["target"] == el["id"] and r["property"] == prop)]
            if not remove:
                if not expr:
                    raise ValueError("expr is required (e.g. \"clamp(hp / max_hp, 0, 1) * 240\")")
                binding.compile_expr(expr)
                binding.eval_expr(expr, c.get("data") or {})
                rows.append({"target": el["id"], "property": prop, "expr": str(expr).strip()})
            if rows:
                c["bindings"] = rows
            else:
                c.pop("bindings", None)
        st.renderer(c, 0.25).render()
    except Exception:
        st.drop_checkpoint(c)
        raise
    st.save_canvas(c)
    return {"canvas": c["id"], "data": c.get("data", {}), "bindings": c.get("bindings", [])}


@tool
def live_preview(action: str = "start", canvas: str | None = None, port: int = 0):
    """Start, check or stop a zero-dependency localhost live preview studio (127.0.0.1 HTTP + SSE).

    The browser window auto-reloads whenever you create or edit any canvas or theme, lets the user
    toggle element IDs, safe-area guides, backdrops and inspect cursor coordinates in real time.
    action: "start" (opens local HTTP server and returns its URL), "status" or "stop".
    port: 0 picks a free port automatically (e.g. http://127.0.0.1:54321), or pass e.g. 8765."""
    global _STUDIO
    from .live import LiveStudio
    act = str(action or "start").strip().lower()
    if act not in ("start", "status", "stop"):
        raise ValueError("action must be 'start', 'status' or 'stop'")
    cid = store().get(canvas)["id"] if canvas else None
    if act == "status":
        if _STUDIO is None or not _STUDIO.running:
            return {"running": False}
        return {"running": True, "url": _STUDIO.url, "active": _STUDIO._last_canvas}
    if act == "stop":
        if _STUDIO is None:
            return {"running": False}
        return _STUDIO.stop()
    p = int(port or 0)
    if p != 0 and not (1024 <= p <= 65535):
        raise ValueError("port must be 0 (auto) or between 1024 and 65535")
    if _STUDIO is None or (not _STUDIO.running and p != _STUDIO.port):
        _STUDIO = LiveStudio(store, port=p)
    return _STUDIO.start(cid)


def _data_uri(img: PILImage.Image) -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes(img)).decode("ascii")


def _state_render(st, c: dict, el: dict, state: str, scale: float, language: str | None):
    """The page rendered with one element in an interaction state, or None if it has none."""
    if el["type"] == "instance":
        try:
            src = st.get(str(el.get("source")))
        except ValueError:
            return None
        if state in (src.get("states") or {}):
            page = copy.deepcopy(c)
            for e in page["elements"]:
                if e["id"] == el["id"]:
                    e["state"] = state
            return st.renderer(page, scale, language=language).render()
    states = c.get("states") or {}
    for name in (f"{state}_{el['id']}", f"{el['id']}_{state}"):
        if name in states:
            return st.renderer(c, scale, state=name, language=language).render()
    if state in states and el["id"] in states[state]:
        return st.renderer(c, scale, state=state, language=language).render()
    return None


@tool
def export_prototype(start: str, path: str | None = None, scale: float = 1, language: str | None = None,
                     pages: list[str] | None = None):
    """Export a clickable prototype: one self-contained HTML file (open it in any browser, share it)
    with every screen reachable from `start` through set_link links, plus `pages`. Linked elements react
    to hover and click with their own hover / pressed states. Esc or "back" links go back.
    Use it to test a menu flow (title -> play -> settings -> back) before building it in the engine."""
    st = store()
    first = st.get(start)
    queue = [first["id"]] + [slugify(p) for p in (_maybe_json(pages) or [])]
    seen: list[str] = []
    while queue:
        cid = queue.pop(0)
        if cid in seen:
            continue
        c = st.get(cid)
        seen.append(cid)
        for target in (c.get("links") or {}).values():
            if target != "back" and target not in seen:
                queue.append(target)
    scale = max(0.25, min(3.0, float(scale)))
    page_html = []
    for cid in seen:
        c = st.get(cid)
        r = st.renderer(c, scale, language=language)
        img = r.render()
        spots = []
        for eid, target in (c.get("links") or {}).items():
            el = next((e for e in c["elements"] if e["id"] == eid), None)
            if el is None:
                continue
            x0, y0, x1, y1 = r.element_box(el)
            pad = 16
            box = [max(0, x0 - pad), max(0, y0 - pad), min(c["width"], x1 + pad), min(c["height"], y1 + pad)]
            crop = tuple(int(round(v * scale)) for v in box)
            layers = ""
            for state in ("hover", "pressed"):
                full = _state_render(st, c, el, state, scale, language)
                if full is not None:
                    layers += (f'<img class="{state}" src="{_data_uri(full.crop(crop))}" '
                               f'style="left:{box[0] - x0}px;top:{box[1] - y0}px;width:{box[2] - box[0]}px;'
                               f'height:{box[3] - box[1]}px">')
            cls = "spot" + ("" if layers else " plain")
            spots.append(f'<a class="{cls}" data-go="{html.escape(target)}" style="left:{x0}px;top:{y0}px;'
                         f'width:{x1 - x0}px;height:{y1 - y0}px">{layers}</a>')
        page_html.append(f'<section class="page" id="p-{html.escape(cid)}" data-w="{c["width"]}" data-h="{c["height"]}" '
                         f'style="width:{c["width"]}px;height:{c["height"]}px">'
                         f'<img class="base" src="{_data_uri(img)}" style="width:{c["width"]}px;height:{c["height"]}px">'
                         + "".join(spots) + "</section>")
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(first.get('name') or first['id'])} - prototype</title>
<style>
html,body{{margin:0;height:100%;background:#0d0d10;overflow:hidden;font:12px system-ui,sans-serif;color:#9aa0aa}}
#stage{{position:absolute;left:50%;top:50%;transform-origin:0 0}}
.page{{position:absolute;left:0;top:0;display:none;background:repeating-conic-gradient(#26262c 0 25%,#1d1d22 0 50%) 0 0/24px 24px}}
.page.on{{display:block}}
.base{{position:absolute;left:0;top:0;image-rendering:auto}}
.spot{{position:absolute;cursor:pointer;display:block}}
.spot img{{position:absolute;display:none;pointer-events:none}}
.spot:hover img.hover{{display:block}}
.spot:active img.hover{{display:none}}
.spot:active img.pressed{{display:block}}
.spot.plain:hover{{outline:2px solid rgba(255,255,255,.55);outline-offset:3px;border-radius:6px}}
.spot.plain:active{{outline-color:#fff;background:rgba(255,255,255,.08)}}
#bar{{position:fixed;left:8px;bottom:6px}}
</style></head><body><div id="stage">{''.join(page_html)}</div>
<div id="bar"></div>
<script>
const stage=document.getElementById('stage'),bar=document.getElementById('bar');let hist=[],cur=null;
function fit(){{const p=document.getElementById('p-'+cur);if(!p)return;const w=+p.dataset.w,h=+p.dataset.h;
const s=Math.min(innerWidth/w,(innerHeight-24)/h);stage.style.width=w+'px';stage.style.height=h+'px';
stage.style.transform='scale('+s+') translate(-50%,-50%)';}}
function show(id,push){{if(push&&cur)hist.push(cur);document.querySelectorAll('.page').forEach(p=>p.classList.toggle('on',p.id==='p-'+id));
cur=id;bar.textContent=id+(hist.length?'  ·  Esc = back':'');fit();}}
document.querySelectorAll('.spot').forEach(a=>a.addEventListener('click',()=>{{const t=a.dataset.go;
if(t==='back'){{if(hist.length)show(hist.pop(),false);}}else show(t,true);}}));
addEventListener('keydown',e=>{{if(e.key==='Escape'&&hist.length)show(hist.pop(),false);}});
addEventListener('resize',fit);show({json.dumps(first['id'])},false);
</script></body></html>
"""
    out = _out_path(path, f"{first['id']}_prototype.html", suffixes=(".html",))
    out.write_text(doc, encoding="utf-8")
    unlinked = [cid for cid in seen if not st.get(cid).get("links")]
    result: dict = {"file": str(out), "screens": seen, "size_kb": round(out.stat().st_size / 1024)}
    if unlinked:
        result["dead_ends"] = unlinked
    return result



ROBLOX_FONTS = {"inter": "BuilderSans", "rajdhani": "TitilliumWeb", "orbitron": "Michroma", "michroma": "Michroma",
                "bangers": "Bangers", "fredoka": "FredokaOne", "bebas neue": "Oswald", "barlow condensed": "Oswald",
                "jetbrains mono": "RobotoMono", "cinzel": "Merriweather"}
ROBLOX_WEIGHT = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
                 700: "Bold", 800: "ExtraBold", 900: "Heavy"}


def _pieces(c: dict, scale: float, bake_text: bool, language: str | None):
    """Split a screen into image pieces (one per group, or per ungrouped/dynamic element) and text nodes,
    in draw order. Elements targeted by data bindings, animation tracks, links or individual click rules
    are kept as independent nodes so generated engine controllers can look them up by exact id."""
    st = store()
    r = st.renderer(c, scale, language=language)
    r1 = st.renderer(c, 1.0, language=language)
    dynamic_ids = (
        {b.get("target") for b in (c.get("bindings") or []) if b.get("target")}
        | {t.get("target") for a in (c.get("animations") or {}).values()
           for t in (a.get("tracks") or []) if t.get("target") and not str(t.get("target")).startswith("group:")}
        | {rule.get("id") for rule in (c.get("interactions") or [])
           if rule.get("id") and rule.get("id") != "canvas" and not str(rule.get("id")).startswith("group:")}
        | set((c.get("links") or {}).keys())
    )
    nodes = []
    groups_done: set[str] = set()
    for el in c["elements"]:
        if not el.get("visible", True):
            continue
        if el["type"] == "text" and not bake_text and not el.get("arc"):
            x0, y0, x1, y1 = r1.element_box(el)
            info = _text_info(r1, el)
            extra = max(8.0, (x1 - x0) * 0.4)
            if info["align"] == "center":
                x0, x1 = x0 - extra / 2, x1 + extra / 2
            elif info["align"] == "right":
                x0 -= extra
            else:
                x1 += extra
            cy, line = (y0 + y1) / 2, float(info["size"]) * 1.4
            y0, y1 = cy - max(line, y1 - y0) / 2, cy + max(line, y1 - y0) / 2
            nodes.append({"kind": "text", "id": el["id"], "box": (x0, y0, x1, y1), "pin": el.get("pin") or {},
                          "el": el, "info": info})
            continue
        if el["type"] in ("input", "scroll", "slider", "toggle", "dropdown"):
            x0, y0, x1, y1 = r1.element_box(el)
            nodes.append({"kind": el["type"], "id": el["id"], "box": (x0, y0, x1, y1), "pin": el.get("pin") or {},
                          "el": el})
            continue
        if el.get("group") and el["id"] not in dynamic_ids:
            if el["group"] in groups_done:
                continue
            groups_done.add(el["group"])
            members = [e for e in c["elements"] if e.get("group") == el["group"] and e.get("visible", True)
                       and e["id"] not in dynamic_ids
                       and e["type"] not in ("input", "scroll", "slider", "toggle", "dropdown")
                       and (bake_text or e["type"] != "text" or e.get("arc"))]
            if not members:
                continue
            name = el["group"]
        else:
            members = [el]
            name = el["id"]
        img = r.render(include_background=False, only={e["id"] for e in members})
        bbox = img.getchannel("A").getbbox()
        if bbox is None:
            continue
        piece = img.crop(bbox)
        nodes.append({"kind": "image", "id": slugify(name, "piece"), "img": piece,
                      "box": (bbox[0] / scale, bbox[1] / scale, bbox[2] / scale, bbox[3] / scale),
                      "pin": members[0].get("pin") or {}, "members": [e["id"] for e in members]})
    return nodes, r.warnings


def _godot_color(rgba) -> str:
    return f"Color({rgba[0] / 255:.4f}, {rgba[1] / 255:.4f}, {rgba[2] / 255:.4f}, {rgba[3] / 255:.4f})"


def _anchor_axis(pin: str, a0: float, a1: float, size: float) -> tuple[float, float, float, float]:
    """(anchor_start, anchor_end, offset_start, offset_end) for one axis, Godot style."""
    if pin in ("right", "bottom"):
        return 1.0, 1.0, a0 - size, a1 - size
    if pin in ("center", "middle"):
        return 0.5, 0.5, a0 - size / 2, a1 - size / 2
    if pin == "stretch":
        return 0.0, 1.0, a0, a1 - size
    if pin == "scale":
        return a0 / size, a1 / size, 0.0, 0.0
    return 0.0, 0.0, a0, a1


def _write_godot(c: dict, nodes: list, folder: Path, res: str, name: str, colors: dict) -> Path:
    res = res.rstrip("/")
    ext_lines, body = [], []
    ids: dict[str, str] = {}
    n = 0

    def ext(kind: str, path: str) -> str:
        nonlocal n
        if path not in ids:
            n += 1
            ids[path] = f"{n}_{kind[:4].lower()}"
            ext_lines.append(f'[ext_resource type="{kind}" path="{res}/{path}" id="{ids[path]}"]')
        return ids[path]

    W, H = float(c["width"]), float(c["height"])
    body += [f'[node name="{_ident_node(name)}" type="Control"]', "layout_mode = 3", "anchors_preset = 15",
             "anchor_right = 1.0", "anchor_bottom = 1.0", "grow_horizontal = 2", "grow_vertical = 2",
             "mouse_filter = 2", ""]
    for node in nodes:
        x0, y0, x1, y1 = node["box"]
        pin = node["pin"]
        al, ar, ol, orr = _anchor_axis(pin.get("x", "left"), x0, x1, W)
        at, ab, ot, ob = _anchor_axis(pin.get("y", "top"), y0, y1, H)
        anchors = [f"anchor_left = {al:.4f}", f"anchor_top = {at:.4f}", f"anchor_right = {ar:.4f}",
                   f"anchor_bottom = {ab:.4f}", f"offset_left = {ol:.2f}", f"offset_top = {ot:.2f}",
                   f"offset_right = {orr:.2f}", f"offset_bottom = {ob:.2f}"]
        if node["kind"] == "image":
            tex = ext("Texture2D", node["file"])
            if node.get("nine"):
                b = node["nine"]
                body += [f'[node name="{_ident_node(node["id"])}" type="NinePatchRect" parent="."]', "layout_mode = 1",
                         *anchors, "mouse_filter = 2", f'texture = ExtResource("{tex}")',
                         f"patch_margin_left = {b['left']}", f"patch_margin_top = {b['top']}",
                         f"patch_margin_right = {b['right']}", f"patch_margin_bottom = {b['bottom']}", ""]
            else:
                body += [f'[node name="{_ident_node(node["id"])}" type="TextureRect" parent="."]', "layout_mode = 1",
                         *anchors, "mouse_filter = 2", f'texture = ExtResource("{tex}")', "expand_mode = 1", ""]
        elif node["kind"] == "input":
            el = node["el"]
            nid = _ident_node(node["id"])
            if el.get("label"):
                ex, ey = float(el.get("x", x0)), float(el.get("y", y0))
                ew = max(16.0, float(el.get("width", x1 - x0)))
                lal, lar, lol, lorr = _anchor_axis(pin.get("x", "left"), ex + 2, ex + ew, W)
                lat, lab, lot, lob = _anchor_axis(pin.get("y", "top"), max(0.0, ey - 22), max(4.0, ey - 4), H)
                l_anchors = [f"anchor_left = {lal:.4f}", f"anchor_top = {lat:.4f}", f"anchor_right = {lar:.4f}",
                             f"anchor_bottom = {lab:.4f}", f"offset_left = {lol:.2f}", f"offset_top = {lot:.2f}",
                             f"offset_right = {lorr:.2f}", f"offset_bottom = {lob:.2f}"]
                body += [f'[node name="{nid}_Label" type="Label" parent="."]', "layout_mode = 1", *l_anchors,
                         f'text = {json.dumps(str(el["label"]), ensure_ascii=False)}',
                         f"theme_override_font_sizes/font_size = {max(11, int(round(float(el.get('size', 15)) * 0.8)))}",
                         "theme_override_colors/font_color = Color(0.7961, 0.8353, 0.8824, 1.0000)", ""]
            from .widgets import widget_colors_summary
            wc = widget_colors_summary(el, colors)
            props = [f'[node name="{nid}" type="LineEdit" parent="."]', "layout_mode = 1", *anchors,
                     f'placeholder_text = {json.dumps(str(el.get("placeholder") or ""), ensure_ascii=False)}',
                     f'text = {json.dumps(str(el.get("value") or ""), ensure_ascii=False)}',
                     f"theme_override_colors/font_color = {_godot_color(wc['text'])}",
                     f"theme_override_colors/font_placeholder_color = {_godot_color(wc['placeholder'])}",
                     f"theme_override_font_sizes/font_size = {int(round(float(el.get('size', 15))))}"]
            if str(el.get("input_type", "")).lower() == "password":
                props.append("secret = true")
            if el.get("max_length"):
                props.append(f"max_length = {int(el['max_length'])}")
            if el.get("readonly"):
                props.append("editable = false")
            body += props + [""]
        elif node["kind"] == "scroll":
            el = node["el"]
            nid = _ident_node(node["id"])
            horiz = str(el.get("direction", "vertical")).lower() == "horizontal"
            box_type = "HBoxContainer" if horiz else "VBoxContainer"
            body += [f'[node name="{nid}" type="ScrollContainer" parent="."]', "layout_mode = 1", *anchors,
                     f"horizontal_scroll_mode = {1 if horiz or el.get('direction') == 'both' else 0}",
                     f"vertical_scroll_mode = {0 if horiz else 1}", "",
                     f'[node name="Content" type="{box_type}" parent="{nid}"]',
                     "size_flags_horizontal = 3",
                     f"theme_override_constants/separation = {int(round(float(el.get('gap', 8))))}", ""]
            for i, raw_item in enumerate(el.get("items") or []):
                title = (raw_item.get("title") or raw_item.get("label") or f"Item {i + 1}") if isinstance(raw_item, dict) else str(raw_item)
                body += [f'[node name="Item{i}" type="Label" parent="{nid}/Content"]',
                         f'text = {json.dumps(str(title), ensure_ascii=False)}',
                         f"theme_override_font_sizes/font_size = {int(round(float(el.get('size', 13))))}", ""]
        elif node["kind"] == "slider":
            el = node["el"]
            nid = _ident_node(node["id"])
            if el.get("label"):
                ex, ey = float(el.get("x", x0)), float(el.get("y", y0))
                ew = max(16.0, float(el.get("width", x1 - x0)))
                lal, lar, lol, lorr = _anchor_axis(pin.get("x", "left"), ex + 2, ex + ew, W)
                lat, lab, lot, lob = _anchor_axis(pin.get("y", "top"), max(0.0, ey - 22), max(4.0, ey - 4), H)
                l_anchors = [f"anchor_left = {lal:.4f}", f"anchor_top = {lat:.4f}", f"anchor_right = {lar:.4f}",
                             f"anchor_bottom = {lab:.4f}", f"offset_left = {lol:.2f}", f"offset_top = {lot:.2f}",
                             f"offset_right = {lorr:.2f}", f"offset_bottom = {lob:.2f}"]
                body += [f'[node name="{nid}_Label" type="Label" parent="."]', "layout_mode = 1", *l_anchors,
                         f'text = {json.dumps(str(el["label"]), ensure_ascii=False)}',
                         f"theme_override_font_sizes/font_size = {max(11, int(round(float(el.get('size', 13)))))}",
                         "theme_override_colors/font_color = Color(0.7961, 0.8353, 0.8824, 1.0000)", ""]
            body += [f'[node name="{nid}" type="HSlider" parent="."]', "layout_mode = 1", *anchors,
                     f"min_value = {float(el.get('min', 0.0)):g}",
                     f"max_value = {float(el.get('max', 100.0)):g}",
                     f"step = {float(el.get('step', 1.0)):g}",
                     f"value = {float(el.get('value', 50.0)):g}", ""]
        elif node["kind"] == "toggle":
            el = node["el"]
            gtype = "CheckBox" if str(el.get("variant", "switch")).lower() == "checkbox" else "CheckButton"
            body += [f'[node name="{_ident_node(node["id"])}" type="{gtype}" parent="."]', "layout_mode = 1", *anchors,
                     f'text = {json.dumps(str(el.get("label") or ""), ensure_ascii=False)}',
                     f"button_pressed = {'true' if el.get('checked') else 'false'}", ""]
        elif node["kind"] == "dropdown":
            el = node["el"]
            nid = _ident_node(node["id"])
            if el.get("label"):
                ex, ey = float(el.get("x", x0)), float(el.get("y", y0))
                ew = max(16.0, float(el.get("width", x1 - x0)))
                lal, lar, lol, lorr = _anchor_axis(pin.get("x", "left"), ex + 2, ex + ew, W)
                lat, lab, lot, lob = _anchor_axis(pin.get("y", "top"), max(0.0, ey - 22), max(4.0, ey - 4), H)
                l_anchors = [f"anchor_left = {lal:.4f}", f"anchor_top = {lat:.4f}", f"anchor_right = {lar:.4f}",
                             f"anchor_bottom = {lab:.4f}", f"offset_left = {lol:.2f}", f"offset_top = {lot:.2f}",
                             f"offset_right = {lorr:.2f}", f"offset_bottom = {lob:.2f}"]
                body += [f'[node name="{nid}_Label" type="Label" parent="."]', "layout_mode = 1", *l_anchors,
                         f'text = {json.dumps(str(el["label"]), ensure_ascii=False)}',
                         f"theme_override_font_sizes/font_size = {max(11, int(round(float(el.get('size', 14)) * 0.85)))}",
                         "theme_override_colors/font_color = Color(0.7961, 0.8353, 0.8824, 1.0000)", ""]
            opts = [str(o) for o in (el.get("options") or [])]
            sel = el.get("selected", 0)
            idx = opts.index(sel) if (isinstance(sel, str) and sel in opts) else int(sel or 0)
            props = [f'[node name="{nid}" type="OptionButton" parent="."]', "layout_mode = 1", *anchors,
                     f"selected = {idx}", f"item_count = {len(opts)}"]
            for i, opt in enumerate(opts):
                props.append(f'popup/item_{i}/text = {json.dumps(opt, ensure_ascii=False)}')
            body += props + [""]
        else:
            t = node["info"]
            props = [f'[node name="{_ident_node(node["id"])}" type="Label" parent="."]', "layout_mode = 1", *anchors]
            col = _first_color_hexlike(t["color"], colors)
            props.append(f"theme_override_colors/font_color = {_godot_color(col)}")
            if t.get("outline"):
                props.append(f"theme_override_colors/font_outline_color = {_godot_color(_first_color_hexlike(t['outline']['color'], colors))}")
                props.append(f"theme_override_constants/outline_size = {int(round(t['outline']['width'] * 2))}")
            if t.get("shadow"):
                props.append(f"theme_override_colors/font_shadow_color = {_godot_color(_first_color_hexlike(t['shadow']['color'], colors))}")
                props.append(f"theme_override_constants/shadow_offset_x = {int(round(t['shadow']['dx']))}")
                props.append(f"theme_override_constants/shadow_offset_y = {int(round(t['shadow']['dy']))}")
            if node.get("font_file"):
                props.append(f'theme_override_fonts/font = ExtResource("{ext("FontFile", node["font_file"])}")')
            props.append(f"theme_override_font_sizes/font_size = {int(round(t['size']))}")
            props.append(f"text = {json.dumps(t['text'], ensure_ascii=False)}")
            props.append(f"horizontal_alignment = {({'left': 0, 'center': 1, 'right': 2}).get(t['align'], 0)}")
            props.append("vertical_alignment = 1")
            body += props + [""]
    head = f"[gd_scene load_steps={len(ext_lines) + 1} format=3]\n\n" + "\n".join(ext_lines) + "\n\n"
    out = folder / f"{name}.tscn"
    out.write_text(head + "\n".join(body), encoding="utf-8")
    return out


def _ident_node(name: str) -> str:
    return re.sub(r"[.:@/\"%]", "_", name) or "node"


def _first_color_hexlike(value: Any, colors: dict) -> tuple[int, int, int, int]:
    if isinstance(value, dict):
        stops = value.get("stops") or []
        return parse_color(stops[0], colors) if stops else (255, 255, 255, 255)
    return parse_color(value or "#ffffff", colors)


def _udim_axis(pin: str, a0: float, a1: float, size: float) -> tuple[str, str]:
    """(position UDim, size UDim) for one axis, Roblox style."""
    length = a1 - a0
    if pin in ("right", "bottom"):
        return f"1, {a0 - size:.1f}", f"0, {length:.1f}"
    if pin in ("center", "middle"):
        return f"0.5, {a0 - size / 2:.1f}", f"0, {length:.1f}"
    if pin == "stretch":
        return f"0, {a0:.1f}", f"1, {-(a0 + size - a1):.1f}"
    if pin == "scale":
        return f"{a0 / size:.4f}, 0", f"{length / size:.4f}, 0"
    return f"0, {a0:.1f}", f"0, {length:.1f}"


def _write_roblox(c: dict, nodes: list, folder: Path, name: str, colors: dict) -> Path:
    W, H = float(c["width"]), float(c["height"])
    lines = [f"-- {name}  -  generated by uiforge-mcp from canvas '{c['id']}' ({int(W)}x{int(H)})",
             "-- LocalScript: put it in StarterPlayerScripts (or StarterGui). Upload the PNGs in Studio and",
             "-- paste each asset id into IMAGES. Layout keeps the design's pins and scales with screen height.",
             "", "local Players = game:GetService(\"Players\")", "local player = Players.LocalPlayer",
             "", "local IMAGES = {"]
    for node in nodes:
        if node["kind"] == "image":
            lines.append(f'\t["{node["id"]}"] = "rbxassetid://0", -- {node["file"]}')
    lines += ["}", "", f"local DESIGN = Vector2.new({int(W)}, {int(H)})", "",
              "local gui = Instance.new(\"ScreenGui\")", f'gui.Name = "{name}"', "gui.IgnoreGuiInset = true",
              "gui.ResetOnSpawn = false", "gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling", "",
              "local root = Instance.new(\"Frame\")", 'root.Name = "Root"', "root.BackgroundTransparency = 1",
              "root.Parent = gui", "local uiScale = Instance.new(\"UIScale\")", "uiScale.Parent = root", "",
              "local function fit()", "\tlocal vp = workspace.CurrentCamera.ViewportSize",
              "\tlocal s = vp.Y / DESIGN.Y", "\tuiScale.Scale = s",
              "\troot.Size = UDim2.fromOffset(vp.X / s, vp.Y / s)", "end", "fit()",
              "workspace.CurrentCamera:GetPropertyChangedSignal(\"ViewportSize\"):Connect(fit)", ""]
    z = 1
    for node in nodes:
        x0, y0, x1, y1 = node["box"]
        pin = node["pin"]
        px, sx = _udim_axis(pin.get("x", "left"), x0, x1, W)
        py, sy = _udim_axis(pin.get("y", "top"), y0, y1, H)
        var = "n" + str(z)
        if node["kind"] == "image":
            lines += [f'local {var} = Instance.new("ImageLabel")', f'{var}.Name = "{node["id"]}"',
                      f'{var}.Image = IMAGES["{node["id"]}"]', f"{var}.BackgroundTransparency = 1"]
            if node.get("nine"):
                b = node["nine"]
                iw, ih = node["img"].size
                lines += [f"{var}.ScaleType = Enum.ScaleType.Slice",
                          f"{var}.SliceCenter = Rect.new({b['left']}, {b['top']}, {iw - b['right']}, {ih - b['bottom']})",
                          f"{var}.SliceScale = {round(1 / node['scale'], 4)}"]
        elif node["kind"] == "input":
            el = node["el"]
            from .widgets import widget_colors_summary
            wc = widget_colors_summary(el, colors)
            rad = int(round(float(el.get("radius", 8) if not isinstance(el.get("radius"), list) else el["radius"][0])))
            lines += [
                f'local {var} = Instance.new("TextBox")', f'{var}.Name = "{node["id"]}"',
                f"{var}.BackgroundColor3 = Color3.fromRGB({wc['bg'][0]}, {wc['bg'][1]}, {wc['bg'][2]})",
                f"{var}.BackgroundTransparency = {round(1 - wc['bg'][3] / 255, 3)}",
                f'{var}.PlaceholderText = {json.dumps(str(el.get("placeholder") or ""), ensure_ascii=False)}',
                f'{var}.Text = {json.dumps(str(el.get("value") or ""), ensure_ascii=False)}',
                f"{var}.TextColor3 = Color3.fromRGB({wc['text'][0]}, {wc['text'][1]}, {wc['text'][2]})",
                f"{var}.PlaceholderColor3 = Color3.fromRGB({wc['placeholder'][0]}, {wc['placeholder'][1]}, {wc['placeholder'][2]})",
                f"{var}.TextSize = {int(round(float(el.get('size', 15))))}",
                f"{var}.ClearTextOnFocus = false",
                f"{var}.TextXAlignment = Enum.TextXAlignment.Left",
                f'local {var}c = Instance.new("UICorner")', f"{var}c.CornerRadius = UDim.new(0, {rad})", f"{var}c.Parent = {var}",
                f'local {var}p = Instance.new("UIPadding")', f"{var}p.PaddingLeft = UDim.new(0, {int(round(float(el.get('padding', 12))))})", f"{var}p.Parent = {var}",
            ]
        elif node["kind"] == "scroll":
            el = node["el"]
            from .widgets import widget_colors_summary
            wc = widget_colors_summary(el, colors)
            rad = int(round(float(el.get("radius", 10) if not isinstance(el.get("radius"), list) else el["radius"][0])))
            horiz = str(el.get("direction", "vertical")).lower() == "horizontal"
            lines += [
                f'local {var} = Instance.new("ScrollingFrame")', f'{var}.Name = "{node["id"]}"',
                f"{var}.BackgroundColor3 = Color3.fromRGB({wc['bg'][0]}, {wc['bg'][1]}, {wc['bg'][2]})",
                f"{var}.BackgroundTransparency = {round(1 - wc['bg'][3] / 255, 3)}",
                f"{var}.AutomaticCanvasSize = Enum.AutomaticSize.{'X' if horiz else 'Y'}",
                f"{var}.CanvasSize = UDim2.new(0, 0, 0, 0)",
                f"{var}.ScrollBarThickness = {int(round(float(el.get('scrollbar_width', 6))))}",
                f'local {var}c = Instance.new("UICorner")', f"{var}c.CornerRadius = UDim.new(0, {rad})", f"{var}c.Parent = {var}",
                f'local {var}l = Instance.new("UIListLayout")',
                f"{var}l.FillDirection = Enum.FillDirection.{'Horizontal' if horiz else 'Vertical'}",
                f"{var}l.Padding = UDim.new(0, {int(round(float(el.get('gap', 8))))})",
                f"{var}l.Parent = {var}",
            ]
            for i, raw_item in enumerate(el.get("items") or []):
                title = (raw_item.get("title") or raw_item.get("label") or f"Item {i + 1}") if isinstance(raw_item, dict) else str(raw_item)
                lines += [
                    f'local {var}_i{i} = Instance.new("TextLabel")',
                    f'{var}_i{i}.Name = "Item{i}"',
                    f"{var}_i{i}.Size = UDim2.new(1, -12, 0, {int(round(float(el.get('item_height', 38))))})",
                    f"{var}_i{i}.BackgroundColor3 = Color3.fromRGB(30, 41, 59)",
                    f"{var}_i{i}.TextColor3 = Color3.fromRGB(226, 232, 240)",
                    f'{var}_i{i}.Text = {json.dumps(str(title), ensure_ascii=False)}',
                    f"{var}_i{i}.TextSize = {int(round(float(el.get('size', 13))))}",
                    f"{var}_i{i}.Parent = {var}",
                ]
        elif node["kind"] == "slider":
            el = node["el"]
            lo, hi = float(el.get("min", 0.0)), float(el.get("max", 100.0))
            frac = max(0.0, min(1.0, (float(el.get("value", 50.0)) - lo) / max(1e-6, hi - lo)))
            lines += [
                f'local {var} = Instance.new("Frame")', f'{var}.Name = "{node["id"]}"',
                f"{var}.BackgroundColor3 = Color3.fromRGB(30, 41, 59)",
                f'local {var}c = Instance.new("UICorner")', f"{var}c.CornerRadius = UDim.new(1, 0)", f"{var}c.Parent = {var}",
                f'local {var}_fill = Instance.new("Frame")', f'{var}_fill.Name = "Fill"',
                f"{var}_fill.Size = UDim2.new({frac:.3f}, 0, 1, 0)",
                f"{var}_fill.BackgroundColor3 = Color3.fromRGB(56, 189, 248)",
                f"{var}_fill.Parent = {var}",
            ]
        elif node["kind"] == "toggle":
            el = node["el"]
            chk = bool(el.get("checked"))
            lines += [
                f'local {var} = Instance.new("TextButton")', f'{var}.Name = "{node["id"]}"',
                f'{var}.Text = {json.dumps(str(el.get("label") or ("ON" if chk else "OFF")), ensure_ascii=False)}',
                f"{var}.BackgroundColor3 = Color3.fromRGB({'34, 197, 94' if chk else '51, 65, 85'})",
                f"{var}.TextColor3 = Color3.fromRGB(248, 250, 252)",
                f'{var}:SetAttribute("Checked", {"true" if chk else "false"})',
                f'local {var}c = Instance.new("UICorner")', f"{var}c.CornerRadius = UDim.new(1, 0)", f"{var}c.Parent = {var}",
            ]
        elif node["kind"] == "dropdown":
            el = node["el"]
            opts = [str(o) for o in (el.get("options") or ["Option 1"])]
            sel = el.get("selected", 0)
            shown = sel if (isinstance(sel, str) and sel in opts) else opts[min(len(opts) - 1, max(0, int(sel or 0)))]
            lines += [
                f'local {var} = Instance.new("TextButton")', f'{var}.Name = "{node["id"]}"',
                f'{var}.Text = {json.dumps(shown + " v", ensure_ascii=False)}',
                f"{var}.BackgroundColor3 = Color3.fromRGB(15, 23, 42)",
                f"{var}.TextColor3 = Color3.fromRGB(248, 250, 252)",
                f"{var}.TextXAlignment = Enum.TextXAlignment.Left",
                f'local {var}c = Instance.new("UICorner")', f"{var}c.CornerRadius = UDim.new(0, 8)", f"{var}c.Parent = {var}",
            ]
        else:
            t = node["info"]
            col = _first_color_hexlike(t["color"], colors)
            family = ROBLOX_FONTS.get(str(t["font"]).lower(), "BuilderSans")
            weight = ROBLOX_WEIGHT.get(int(round(int(t["weight"] or 400) / 100.0) * 100), "Regular")
            lines += [f'local {var} = Instance.new("TextLabel")', f'{var}.Name = "{node["id"]}"',
                      f"{var}.BackgroundTransparency = 1", f"{var}.Text = {json.dumps(t['text'], ensure_ascii=False)}",
                      f"{var}.TextColor3 = Color3.fromRGB({col[0]}, {col[1]}, {col[2]})",
                      f"{var}.TextTransparency = {round(1 - col[3] / 255, 3)}",
                      f"{var}.TextSize = {int(round(t['size']))}",
                      f'{var}.FontFace = Font.fromName("{family}", Enum.FontWeight.{weight})  -- designed with {t["font"]}',
                      f"{var}.TextXAlignment = Enum.TextXAlignment.{({'left': 'Left', 'center': 'Center', 'right': 'Right'}).get(t['align'], 'Left')}",
                      f"{var}.TextYAlignment = Enum.TextYAlignment.Center"]
            if t.get("outline"):
                oc = _first_color_hexlike(t["outline"]["color"], colors)
                lines += [f'local {var}s = Instance.new("UIStroke")', f"{var}s.Thickness = {round(t['outline']['width'], 2)}",
                          f"{var}s.Color = Color3.fromRGB({oc[0]}, {oc[1]}, {oc[2]})",
                          f"{var}s.Transparency = {round(1 - oc[3] / 255, 3)}", f"{var}s.Parent = {var}"]
        lines += [f"{var}.Position = UDim2.new({px}, {py})", f"{var}.Size = UDim2.new({sx}, {sy})",
                  f"{var}.ZIndex = {z}", f"{var}.Parent = root", ""]
        z += 1
    lines += ['gui.Parent = player:WaitForChild("PlayerGui")', ""]
    out = folder / f"{name}.client.luau"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def _css_axis(pin: str, a0: float, a1: float, size: float, start: str, end: str, length: str) -> list[str]:
    span = a1 - a0
    if pin in ("right", "bottom"):
        return [f"{end}: {size - a1:.1f}px", f"{length}: {span:.1f}px"]
    if pin in ("center", "middle"):
        return [f"{start}: 50%", f"margin-{start}: {a0 - size / 2:.1f}px", f"{length}: {span:.1f}px"]
    if pin == "stretch":
        return [f"{start}: {a0:.1f}px", f"{end}: {size - a1:.1f}px"]
    if pin == "scale":
        return [f"{start}: {a0 / size * 100:.3f}%", f"{length}: {span / size * 100:.3f}%"]
    return [f"{start}: {a0:.1f}px", f"{length}: {span:.1f}px"]


def _write_unity(c: dict, nodes: list, folder: Path, name: str, colors: dict) -> list[Path]:
    W, H = float(c["width"]), float(c["height"])
    uss = [f"/* {name} - generated by uiforge-mcp. PanelSettings: Scale With Screen Size, reference "
           f"resolution {int(W)}x{int(H)}, match 1 (height). */",
           f".{name}-root {{ position: absolute; left: 0; top: 0; right: 0; bottom: 0; }}"]
    uxml = ['<ui:UXML xmlns:ui="UnityEngine.UIElements">', f'    <Style src="{name}.uss" />',
            f'    <ui:VisualElement name="{name}" class="{name}-root" picking-mode="Ignore">']
    for node in nodes:
        x0, y0, x1, y1 = node["box"]
        pin = node["pin"]
        cls = f"{name}-{node['id']}".replace("_", "-")
        rules = ["position: absolute"] + _css_axis(pin.get("x", "left"), x0, x1, W, "left", "right", "width") + \
            _css_axis(pin.get("y", "top"), y0, y1, H, "top", "bottom", "height")
        if node["kind"] == "image":
            rules.append(f'background-image: url("{node["file"]}")')
            if node.get("nine"):
                b = node["nine"]
                rules += [f"-unity-slice-left: {b['left']}", f"-unity-slice-top: {b['top']}",
                          f"-unity-slice-right: {b['right']}", f"-unity-slice-bottom: {b['bottom']}",
                          f"-unity-slice-scale: {round(1 / node['scale'], 4)}px"]
            uxml.append(f'        <ui:VisualElement name="{node["id"]}" class="{cls}" picking-mode="Ignore" />')
        elif node["kind"] == "input":
            el = node["el"]
            from .widgets import widget_colors_summary
            wc = widget_colors_summary(el, colors)
            rad = float(el.get("radius", 8) if not isinstance(el.get("radius"), list) else el["radius"][0])
            rules += [
                f"background-color: rgba({wc['bg'][0]}, {wc['bg'][1]}, {wc['bg'][2]}, {wc['bg'][3] / 255:.3f})",
                f"border-color: rgba({wc['border'][0]}, {wc['border'][1]}, {wc['border'][2]}, {wc['border'][3] / 255:.3f})",
                f"border-width: {wc['border_width']:.1f}px",
                f"border-radius: {rad:.1f}px",
                f"color: rgba({wc['text'][0]}, {wc['text'][1]}, {wc['text'][2]}, {wc['text'][3] / 255:.3f})",
                f"font-size: {float(el.get('size', 15)):.0f}px",
            ]
            pw = ' password="true"' if str(el.get("input_type", "")).lower() == "password" else ""
            ro = ' readonly="true"' if el.get("readonly") else ""
            val = html.escape(str(el.get("value") or ""), quote=True)
            uxml.append(f'        <ui:TextField name="{node["id"]}" class="{cls}" value="{val}"{pw}{ro} />')
        elif node["kind"] == "scroll":
            el = node["el"]
            from .widgets import widget_colors_summary
            wc = widget_colors_summary(el, colors)
            rad = float(el.get("radius", 10) if not isinstance(el.get("radius"), list) else el["radius"][0])
            rules += [
                f"background-color: rgba({wc['bg'][0]}, {wc['bg'][1]}, {wc['bg'][2]}, {wc['bg'][3] / 255:.3f})",
                f"border-color: rgba({wc['border'][0]}, {wc['border'][1]}, {wc['border'][2]}, {wc['border'][3] / 255:.3f})",
                f"border-width: {wc['border_width']:.1f}px",
                f"border-radius: {rad:.1f}px",
                f"padding: {float(el.get('padding', 10)):.0f}px",
            ]
            mode = {"horizontal": "Horizontal", "both": "VerticalAndHorizontal"}.get(str(el.get("direction", "vertical")).lower(), "Vertical")
            uxml.append(f'        <ui:ScrollView name="{node["id"]}" class="{cls}" mode="{mode}">')
            for i, raw_item in enumerate(el.get("items") or []):
                title = (raw_item.get("title") or raw_item.get("label") or f"Item {i + 1}") if isinstance(raw_item, dict) else str(raw_item)
                uxml.append(f'            <ui:Label name="{node["id"]}_item_{i}" text="{html.escape(str(title), quote=True)}" />')
            uxml.append("        </ui:ScrollView>")
        elif node["kind"] == "slider":
            el = node["el"]
            lbl = html.escape(str(el.get("label") or ""), quote=True)
            uxml.append(
                f'        <ui:Slider name="{node["id"]}" class="{cls}" label="{lbl}" '
                f'low-value="{float(el.get("min", 0.0)):g}" high-value="{float(el.get("max", 100.0)):g}" '
                f'value="{float(el.get("value", 50.0)):g}" />'
            )
        elif node["kind"] == "toggle":
            el = node["el"]
            lbl = html.escape(str(el.get("label") or ""), quote=True)
            val = "true" if el.get("checked") else "false"
            uxml.append(f'        <ui:Toggle name="{node["id"]}" class="{cls}" label="{lbl}" value="{val}" />')
        elif node["kind"] == "dropdown":
            el = node["el"]
            opts = [str(o) for o in (el.get("options") or [])]
            sel = el.get("selected", 0)
            idx = opts.index(sel) if (isinstance(sel, str) and sel in opts) else int(sel or 0)
            choices = html.escape(",".join(opts), quote=True)
            uxml.append(f'        <ui:DropdownField name="{node["id"]}" class="{cls}" choices="{choices}" index="{idx}" />')
        else:
            t = node["info"]
            col = _first_color_hexlike(t["color"], colors)
            align_h = {"left": "left", "center": "center", "right": "right"}.get(t["align"], "left")
            rules += [f"font-size: {t['size']:.0f}px", f"color: rgba({col[0]}, {col[1]}, {col[2]}, {col[3] / 255:.3f})",
                      f"-unity-text-align: middle-{align_h}", "white-space: nowrap", "margin: 0", "padding: 0"]
            if node.get("font_file"):
                rules.append(f'-unity-font: url("{node["font_file"]}")')
            if int(t["weight"] or 400) >= 600:
                rules.append("-unity-font-style: bold")
            if t.get("letter_spacing"):
                rules.append(f"letter-spacing: {t['letter_spacing']}px")
            if t.get("outline"):
                oc = _first_color_hexlike(t["outline"]["color"], colors)
                rules += [f"-unity-text-outline-width: {t['outline']['width']}px",
                          f"-unity-text-outline-color: rgba({oc[0]}, {oc[1]}, {oc[2]}, {oc[3] / 255:.3f})"]
            if t.get("shadow"):
                sc = _first_color_hexlike(t["shadow"]["color"], colors)
                rules.append(f"text-shadow: {t['shadow']['dx']}px {t['shadow']['dy']}px {t['shadow']['blur']}px "
                             f"rgba({sc[0]}, {sc[1]}, {sc[2]}, {sc[3] / 255:.3f})")
            uxml.append(f'        <ui:Label name="{node["id"]}" class="{cls}" text="{html.escape(t["text"], quote=True)}" '
                        f'picking-mode="Ignore" />')
        uss.append(f".{cls} {{ " + "; ".join(rules) + "; }")
    uxml += ["    </ui:VisualElement>", "</ui:UXML>"]
    a = folder / f"{name}.uxml"
    b = folder / f"{name}.uss"
    a.write_text("\n".join(uxml) + "\n", encoding="utf-8")
    b.write_text("\n".join(uss) + "\n", encoding="utf-8")
    return [a, b]


def _pascal_id(name: str) -> str:
    out = re.sub(r"[^0-9a-zA-Z]+", " ", str(name)).title().replace(" ", "") or "Screen"
    return out if out[0].isalpha() else "Screen" + out


def _write_godot_controller(c: dict, nodes: list, folder: Path, name: str, colors: dict | None = None) -> Path | None:
    """Emit a Godot 4 GDScript controller wiring data bindings, interactions, sfx signals and gamepad focus."""
    ix = c.get("interactions") or []
    data = c.get("data") or {}
    binds = c.get("bindings") or []
    focus = c.get("focus_order") or []
    inputs = [n for n in nodes if n["kind"] == "input"]
    sliders = [n for n in nodes if n["kind"] == "slider"]
    toggles = [n for n in nodes if n["kind"] == "toggle"]
    dropdowns = [n for n in nodes if n["kind"] == "dropdown"]
    if not (ix or data or binds or focus or inputs or sliders or toggles or dropdowns):
        return None
    node_ids = {n["id"]: _ident_node(n["id"]) for n in nodes}
    lines = [
        f"# {name}_controller.gd  -  generated by uiforge-mcp from canvas '{c['id']}'",
        "extends Control", "",
        "signal navigate_requested(target: String, mode: String)",
        "signal sfx_requested(event_name: String)",
        "signal state_changed(state_name: String, active: bool)", "",
        f"var data: Dictionary = {json.dumps(data, ensure_ascii=False)}",
        f"var _defaults: Dictionary = {json.dumps(data, ensure_ascii=False)}",
        "var _states: Dictionary = {}", "",
        "func _ready() -> void:",
    ]
    valid_focus = [node_ids[f] for f in focus if f in node_ids]
    if valid_focus:
        for i, nid in enumerate(valid_focus):
            nxt = valid_focus[(i + 1) % len(valid_focus)]
            prv = valid_focus[(i - 1) % len(valid_focus)]
            lines += [
                f'\tvar f_{i} := get_node_or_null("{nid}")',
                f"\tif f_{i} is Control:",
                f"\t\tf_{i}.focus_mode = Control.FOCUS_ALL",
                f'\t\tf_{i}.focus_neighbor_bottom = NodePath("../{nxt}")',
                f'\t\tf_{i}.focus_neighbor_top = NodePath("../{prv}")',
            ]
        lines.append(f'\tif get_node_or_null("{valid_focus[0]}") is Control: get_node("{valid_focus[0]}").grab_focus()')
    for rule in ix:
        rid = rule["id"]
        target_node = node_ids.get(rid) or (node_ids.get(slugify(rid[6:], "piece")) if rid.startswith("group:") else None)
        if rule["trigger"] == "click" and target_node:
            lines += [
                f'\tvar n_{_ident_node(target_node)} := get_node_or_null("{target_node}")',
                f"\tif n_{_ident_node(target_node)} is Control:",
                f"\t\tn_{_ident_node(target_node)}.mouse_filter = Control.MOUSE_FILTER_STOP",
                f'\t\tn_{_ident_node(target_node)}.gui_input.connect(func(ev): if ev is InputEventMouseButton and ev.pressed: _run_rule({json.dumps(rule, ensure_ascii=False)}))',
            ]
    for n in inputs:
        nid = _ident_node(n["id"])
        bkey = n["el"].get("bind") or n["id"]
        lines += [
            f'\tvar inp_{nid} := get_node_or_null("{nid}")',
            f"\tif inp_{nid} is LineEdit:",
            f'\t\tinp_{nid}.text_changed.connect(func(v): set_data({{"{bkey}": v}}))',
        ]
    for n in sliders:
        nid = _ident_node(n["id"])
        bkey = n["el"].get("bind") or n["id"]
        lines += [
            f'\tvar sl_{nid} := get_node_or_null("{nid}")',
            f"\tif sl_{nid} is Range:",
            f'\t\tsl_{nid}.value_changed.connect(func(v): set_data({{"{bkey}": v}}))',
        ]
    for n in toggles:
        nid = _ident_node(n["id"])
        bkey = n["el"].get("bind") or n["id"]
        lines += [
            f'\tvar tg_{nid} := get_node_or_null("{nid}")',
            f"\tif tg_{nid} is BaseButton:",
            f'\t\ttg_{nid}.toggled.connect(func(v): set_data({{"{bkey}": v}}))',
        ]
    for n in dropdowns:
        nid = _ident_node(n["id"])
        bkey = n["el"].get("bind") or n["id"]
        lines += [
            f'\tvar dd_{nid} := get_node_or_null("{nid}")',
            f"\tif dd_{nid} is OptionButton:",
            f'\t\tdd_{nid}.item_selected.connect(func(i): set_data({{"{bkey}": dd_{nid}.get_item_text(i)}}))',
        ]
    lines += ["\tset_data(data)", ""]
    lines += [
        "func set_data(patch: Dictionary) -> void:",
        "\tdata.merge(patch, true)",
    ]
    for n in nodes:
        if n["kind"] == "text" and "{" in str(n["info"].get("text", "")):
            tpl = str(n["el"].get("text", ""))
            lines += [
                f'\tvar lbl_{_ident_node(n["id"])} := get_node_or_null("{_ident_node(n["id"])}")',
                f"\tif lbl_{_ident_node(n['id'])} is Label:",
                f"\t\tvar txt_{_ident_node(n['id'])} := {json.dumps(tpl, ensure_ascii=False)}",
                "\t\tfor k in data: txt_" + _ident_node(n["id"]) + ' = txt_' + _ident_node(n["id"]) + '.replace("{" + str(k) + "}", str(data[k]))',
                f"\t\tlbl_{_ident_node(n['id'])}.text = txt_{_ident_node(n['id'])}",
            ]
    declared_b: set[str] = set()
    for b in binds:
        tgt = _ident_node(b["target"])
        prop = str(b.get("property", ""))
        try:
            from . import binding as _bnd
            gexpr = _bnd.gdscript_expr(b["expr"], theme_colors=colors)
        except Exception:
            lines.append(f"\t# binding: {b['target']}.{prop} = {b['expr']}")
            continue
        if tgt not in declared_b:
            lines.append(f'\tvar b_{tgt} := get_node_or_null("{tgt}")')
            declared_b.add(tgt)
        if prop == "width":
            lines.append(f"\tif b_{tgt} is Control: b_{tgt}.size.x = maxf(0.0, float({gexpr}))")
        elif prop == "height":
            lines.append(f"\tif b_{tgt} is Control: b_{tgt}.size.y = maxf(0.0, float({gexpr}))")
        elif prop == "x":
            lines.append(f"\tif b_{tgt} is Control: b_{tgt}.position.x = float({gexpr})")
        elif prop == "y":
            lines.append(f"\tif b_{tgt} is Control: b_{tgt}.position.y = float({gexpr})")
        elif prop == "rotation":
            lines.append(f"\tif b_{tgt} is Control: b_{tgt}.rotation_degrees = float({gexpr})")
        elif prop in ("opacity", "style.opacity"):
            lines.append(f"\tif b_{tgt} is CanvasItem: b_{tgt}.modulate.a = clampf(float({gexpr}), 0.0, 1.0)")
        elif prop == "visible":
            lines.append(f"\tif b_{tgt} is CanvasItem: b_{tgt}.visible = bool({gexpr})")
        elif prop == "text":
            lines.append(f'\tif b_{tgt} and b_{tgt}.has_method("set_text"): b_{tgt}.text = str({gexpr})')
        elif prop in ("style.fill", "fill", "style.color", "color"):
            lines.append(f"\tif b_{tgt} is CanvasItem: b_{tgt}.modulate = Color.html(str({gexpr}))")
        else:
            lines.append(f"\t# binding: {b['target']}.{prop} = {gexpr}")
    key_rules = [r for r in ix if str(r.get("trigger", "")).startswith("key:")]
    if key_rules:
        lines += [
            "", "func _unhandled_input(event: InputEvent) -> void:",
            "\tif event is InputEventKey and event.pressed and not event.echo:",
            "\t\tvar k := OS.get_keycode_string(event.keycode).to_lower()",
        ]
        for kr in key_rules:
            kname = str(kr["trigger"]).split(":", 1)[1].strip().lower()
            lines.append(f'\t\tif k == {json.dumps(kname)}: _run_rule({json.dumps(kr, ensure_ascii=False)})')
    lines += [
        "", "func _run_rule(rule: Dictionary) -> void:",
        '\tif rule.has("sfx"): sfx_requested.emit(str(rule["sfx"]))',
        '\tvar act := str(rule.get("action", ""))',
        '\tif act in ["navigate", "overlay", "back", "url"]: navigate_requested.emit(str(rule.get("target", "back")), act)',
        '\telif act == "set_state": _states[rule["state"]] = true; state_changed.emit(rule["state"], true)',
        '\telif act == "clear_state": _states.erase(rule["state"]); state_changed.emit(rule["state"], false)',
        '\telif act == "toggle_state":',
        '\t\tvar on := not _states.get(rule["state"], false)',
        '\t\t_states[rule["state"]] = on; state_changed.emit(rule["state"], on)',
        '\telif act == "set_data" and rule.has("data") and rule["data"] is Dictionary:',
        '\t\tset_data(rule["data"])',
        '\telif act == "reset_data":',
        '\t\tdata = _defaults.duplicate(true); set_data(data)',
        "",
        "func _fmt_num(val: float, decimals: int = 0) -> String:",
        '\tvar raw := ("%." + str(maxi(0, decimals)) + "f") % val',
        '\tvar parts := raw.split(".")',
        '\tvar sign_s := "-" if parts[0].begins_with("-") else ""',
        '\tvar digits := parts[0].lstrip("-")',
        '\tvar out_s := ""',
        '\tfor i in range(digits.length()):',
        '\t\tif i > 0 and (digits.length() - i) % 3 == 0: out_s += ","',
        '\t\tout_s += digits[i]',
        '\treturn sign_s + out_s + (("." + parts[1]) if parts.size() > 1 else "")',
    ]
    out = folder / f"{name}_controller.gd"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _write_unity_controller(c: dict, nodes: list, folder: Path, name: str) -> Path | None:
    """Emit a Unity UI Toolkit C# MonoBehaviour controller for data bindings, interactions and sfx events."""
    ix = c.get("interactions") or []
    data = c.get("data") or {}
    binds = c.get("bindings") or []
    focus = c.get("focus_order") or []
    inputs = [n for n in nodes if n["kind"] == "input"]
    sliders = [n for n in nodes if n["kind"] == "slider"]
    toggles = [n for n in nodes if n["kind"] == "toggle"]
    dropdowns = [n for n in nodes if n["kind"] == "dropdown"]
    if not (ix or data or binds or focus or inputs or sliders or toggles or dropdowns):
        return None
    cls = _pascal_id(name) + "Controller"
    lines = [
        f"// {cls}.cs  -  generated by uiforge-mcp from canvas '{c['id']}'",
        "using System;",
        "using System.Collections.Generic;",
        "using UnityEngine;",
        "using UnityEngine.UIElements;", "",
        "[RequireComponent(typeof(UIDocument))]",
        f"public class {cls} : MonoBehaviour",
        "{",
        "    public event Action<string, string> OnNavigate;",
        "    public event Action<string> OnSfx;",
        "    public event Action<string, bool> OnStateChanged;", "",
        "    private VisualElement _root;",
        "    private readonly Dictionary<string, object> _data = new Dictionary<string, object>();",
        "    private readonly HashSet<string> _states = new HashSet<string>();", "",
        "    private void OnEnable()",
        "    {",
        "        _root = GetComponent<UIDocument>().rootVisualElement;",
    ]
    for k, v in data.items():
        lit = f'"{v}"' if isinstance(v, str) else ("true" if v is True else "false" if v is False else f"{v}f")
        lines.append(f'        _data["{k}"] = {lit};')
    for rule in ix:
        rid = rule["id"]
        tgt = slugify(rid[6:], "piece") if rid.startswith("group:") else rid
        sfx_call = f'OnSfx?.Invoke("{rule["sfx"]}"); ' if rule.get("sfx") else ""
        act = rule["action"]
        if act in ("navigate", "overlay", "back", "url"):
            body = f'{sfx_call}OnNavigate?.Invoke("{rule.get("target", "back")}", "{act}");'
        elif act == "set_state":
            body = f'{sfx_call}_states.Add("{rule["state"]}"); OnStateChanged?.Invoke("{rule["state"]}", true);'
        elif act == "clear_state":
            body = f'{sfx_call}_states.Remove("{rule["state"]}"); OnStateChanged?.Invoke("{rule["state"]}", false);'
        elif act == "toggle_state":
            body = f'{sfx_call}bool on = !_states.Contains("{rule["state"]}"); if (on) _states.Add("{rule["state"]}"); else _states.Remove("{rule["state"]}"); OnStateChanged?.Invoke("{rule["state"]}", on);'
        else:
            body = f'{sfx_call}// action: {act}'
        if rule["trigger"] == "click":
            lines += [
                f'        var el_{slugify(tgt, "n")} = _root.Q<VisualElement>("{tgt}");',
                f'        if (el_{slugify(tgt, "n")} != null) {{ el_{slugify(tgt, "n")}.pickingMode = PickingMode.Position; el_{slugify(tgt, "n")}.RegisterCallback<ClickEvent>(_ => {{ {body} }}); }}',
            ]
    for n in inputs:
        tid = slugify(n["id"], "inp")
        bkey = n["el"].get("bind") or n["id"]
        lines += [
            f'        var inp_{tid} = _root.Q<TextField>("{n["id"]}");',
            f'        if (inp_{tid} != null) inp_{tid}.RegisterValueChangedCallback(ev => SetData("{bkey}", ev.newValue));',
        ]
    lines += [
        "        Refresh();",
        "    }", "",
        "    public void SetData(string key, object value) { _data[key] = value; Refresh(); }", "",
        "    public void Refresh()",
        "    {",
    ]
    for n in nodes:
        if n["kind"] == "text" and "{" in str(n["el"].get("text", "")):
            tpl = str(n["el"].get("text", "")).replace("\\", "\\\\").replace('"', '\\"')
            lines += [
                f'        var lbl_{slugify(n["id"], "t")} = _root.Q<Label>("{n["id"]}");',
                f'        if (lbl_{slugify(n["id"], "t")} != null) {{ string s = "{tpl}"; foreach (var kv in _data) s = s.Replace("{{" + kv.Key + "}}", kv.Value?.ToString() ?? ""); lbl_{slugify(n["id"], "t")}.text = s; }}',
            ]
    for b in binds:
        lines.append(f'        // binding: {b["target"]}.{b["property"]} = {b["expr"]}')
    lines += ["    }", "}"]
    out = folder / f"{cls}.cs"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _write_unity_ugui(c: dict, nodes: list, folder: Path, name: str, colors: dict) -> Path:
    """Emit a Unity uGUI (Canvas + RectTransform + Image + Text) editor builder script."""
    W, H = float(c["width"]), float(c["height"])
    cls = _pascal_id(name) + "UGuiBuilder"
    lines = [
        f"// {cls}.cs  -  generated by uiforge-mcp from canvas '{c['id']}' ({int(W)}x{int(H)})",
        "// Put in Assets/Editor/ and run Tools -> UIForge -> Build " + cls + " to create a uGUI Canvas.",
        "#if UNITY_EDITOR",
        "using UnityEditor;",
        "using UnityEngine;",
        "using UnityEngine.UI;", "",
        f"public static class {cls}",
        "{",
        f'    [MenuItem("Tools/UIForge/Build {cls}")]',
        "    public static void Build()",
        "    {",
        f'        var root = new GameObject("{name}", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));',
        "        var canvas = root.GetComponent<Canvas>();",
        "        canvas.renderMode = RenderMode.ScreenSpaceOverlay;",
        "        var scaler = root.GetComponent<CanvasScaler>();",
        "        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;",
        f"        scaler.referenceResolution = new Vector2({int(W)}, {int(H)});",
        "        scaler.matchWidthOrHeight = 1f;",
    ]
    for idx, node in enumerate(nodes):
        x0, y0, x1, y1 = node["box"]
        w, h = x1 - x0, y1 - y0
        pin = node["pin"]
        px, py = pin.get("x", "left"), pin.get("y", "top")
        ax0, ax1 = (1.0, 1.0) if px == "right" else (0.5, 0.5) if px == "center" else (0.0, 1.0) if px == "stretch" else (0.0, 0.0)
        ay0, ay1 = (0.0, 0.0) if py == "bottom" else (0.5, 0.5) if py == "middle" else (0.0, 1.0) if py == "stretch" else (1.0, 1.0)
        var = f"n{idx}"
        if node["kind"] == "image":
            lines += [
                f'        var {var} = new GameObject("{node["id"]}", typeof(RectTransform), typeof(Image));',
                f"        {var}.transform.SetParent(root.transform, false);",
                f'        var {var}Img = {var}.GetComponent<Image>();',
                f'        {var}Img.type = Image.Type.{"Sliced" if node.get("nine") else "Simple"};',
                f'        // Assign sprite "{node["file"]}" to {var}Img.sprite',
            ]
        elif node["kind"] == "input":
            el = node["el"]
            from .widgets import widget_colors_summary
            wc = widget_colors_summary(el, colors)
            ph = str(el.get("placeholder") or "").replace("\\", "\\\\").replace('"', '\\"')
            val = str(el.get("value") or "").replace("\\", "\\\\").replace('"', '\\"')
            lines += [
                f'        var {var} = new GameObject("{node["id"]}", typeof(RectTransform), typeof(Image), typeof(InputField));',
                f"        {var}.transform.SetParent(root.transform, false);",
                f"        {var}.GetComponent<Image>().color = new Color({wc['bg'][0]/255:.3f}f, {wc['bg'][1]/255:.3f}f, {wc['bg'][2]/255:.3f}f, {wc['bg'][3]/255:.3f}f);",
                f'        var {var}Inp = {var}.GetComponent<InputField>();',
                f'        var {var}TxtGo = new GameObject("Text", typeof(RectTransform), typeof(Text));',
                f"        {var}TxtGo.transform.SetParent({var}.transform, false);",
                f"        var {var}Txt = {var}TxtGo.GetComponent<Text>(); {var}Txt.text = \"{val}\"; {var}Txt.fontSize = {int(round(float(el.get('size', 15))))};",
                f"        {var}Inp.textComponent = {var}Txt;",
                f'        var {var}PhGo = new GameObject("Placeholder", typeof(RectTransform), typeof(Text));',
                f"        {var}PhGo.transform.SetParent({var}.transform, false);",
                f'        var {var}Ph = {var}PhGo.GetComponent<Text>(); {var}Ph.text = "{ph}"; {var}Inp.placeholder = {var}Ph;',
            ]
            if str(el.get("input_type", "")).lower() == "password":
                lines.append(f"        {var}Inp.contentType = InputField.ContentType.Password;")
        elif node["kind"] == "scroll":
            el = node["el"]
            from .widgets import widget_colors_summary
            wc = widget_colors_summary(el, colors)
            horiz = str(el.get("direction", "vertical")).lower() == "horizontal"
            lines += [
                f'        var {var} = new GameObject("{node["id"]}", typeof(RectTransform), typeof(Image), typeof(Mask), typeof(ScrollRect));',
                f"        {var}.transform.SetParent(root.transform, false);",
                f"        {var}.GetComponent<Image>().color = new Color({wc['bg'][0]/255:.3f}f, {wc['bg'][1]/255:.3f}f, {wc['bg'][2]/255:.3f}f, {wc['bg'][3]/255:.3f}f);",
                f"        var {var}Sr = {var}.GetComponent<ScrollRect>(); {var}Sr.vertical = {'false' if horiz else 'true'}; {var}Sr.horizontal = {'true' if horiz else 'false'};",
                f'        var {var}Content = new GameObject("Content", typeof(RectTransform), typeof({"HorizontalLayoutGroup" if horiz else "VerticalLayoutGroup"}), typeof(ContentSizeFitter));',
                f"        {var}Content.transform.SetParent({var}.transform, false);",
                f"        {var}Sr.content = {var}Content.GetComponent<RectTransform>();",
            ]
        elif node["kind"] == "slider":
            el = node["el"]
            lines += [
                f'        var {var} = new GameObject("{node["id"]}", typeof(RectTransform), typeof(Slider));',
                f"        {var}.transform.SetParent(root.transform, false);",
                f"        var {var}Sl = {var}.GetComponent<Slider>(); {var}Sl.minValue = {float(el.get('min', 0.0)):g}f; {var}Sl.maxValue = {float(el.get('max', 100.0)):g}f; {var}Sl.value = {float(el.get('value', 50.0)):g}f;",
            ]
        elif node["kind"] == "toggle":
            el = node["el"]
            lines += [
                f'        var {var} = new GameObject("{node["id"]}", typeof(RectTransform), typeof(Toggle));',
                f"        {var}.transform.SetParent(root.transform, false);",
                f"        {var}.GetComponent<Toggle>().isOn = {'true' if el.get('checked') else 'false'};",
            ]
        elif node["kind"] == "dropdown":
            el = node["el"]
            opts = [str(o).replace("\\", "\\\\").replace('"', '\\"') for o in (el.get("options") or ["Option 1"])]
            sel = el.get("selected", 0)
            idx = opts.index(sel) if (isinstance(sel, str) and sel in opts) else int(sel or 0)
            opt_args = ", ".join(f'new Dropdown.OptionData("{o}")' for o in opts)
            lines += [
                f'        var {var} = new GameObject("{node["id"]}", typeof(RectTransform), typeof(Image), typeof(Dropdown));',
                f"        {var}.transform.SetParent(root.transform, false);",
                f"        var {var}Dd = {var}.GetComponent<Dropdown>();",
                f"        {var}Dd.options = new System.Collections.Generic.List<Dropdown.OptionData> {{ {opt_args} }};",
                f"        {var}Dd.value = {idx};",
            ]
        else:
            t = node["info"]
            col = _first_color_hexlike(t["color"], colors)
            txt = str(t["text"]).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines += [
                f'        var {var} = new GameObject("{node["id"]}", typeof(RectTransform), typeof(Text));',
                f"        {var}.transform.SetParent(root.transform, false);",
                f"        var {var}Txt = {var}.GetComponent<Text>();",
                f'        {var}Txt.text = "{txt}";',
                f"        {var}Txt.fontSize = {int(round(t['size']))};",
                f"        {var}Txt.color = new Color({col[0] / 255:.3f}f, {col[1] / 255:.3f}f, {col[2] / 255:.3f}f, {col[3] / 255:.3f}f);",
            ]
        lines += [
            f"        var {var}Rt = {var}.GetComponent<RectTransform>();",
            f"        {var}Rt.anchorMin = new Vector2({ax0:.2f}f, {ay0:.2f}f);",
            f"        {var}Rt.anchorMax = new Vector2({ax1:.2f}f, {ay1:.2f}f);",
            f"        {var}Rt.pivot = new Vector2(0f, 1f);",
            f"        {var}Rt.sizeDelta = new Vector2({w:.1f}f, {h:.1f}f);",
            f"        {var}Rt.anchoredPosition = new Vector2({x0 - ax0 * W:.1f}f, {-y0 + (1.0 - ay1) * H:.1f}f);",
        ]
    lines += [
        "        Selection.activeGameObject = root;",
        "    }",
        "}",
        "#endif",
    ]
    out = folder / f"{cls}.cs"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _write_unreal_umg(c: dict, nodes: list, folder: Path, name: str, colors: dict,
                      unreal_content_path: str = "/Game/UI/Generated") -> Path:
    """Emit an Unreal Engine 5.5-5.8 Python Editor script that imports pieces & constructs a UMG WidgetBlueprint."""
    if not re.fullmatch(r"/[A-Za-z0-9_/]+", unreal_content_path or ""):
        raise ValueError("unreal_content_path must be a content path like /Game/UI/Generated (letters, digits, _ and / only)")
    W, H = float(c["width"]), float(c["height"])
    bp_name = "WBP_" + _pascal_id(name)
    spec_nodes = []
    for node in nodes:
        x0, y0, x1, y1 = node["box"]
        entry: dict[str, Any] = {
            "kind": node["kind"],
            "id": _ident_node(node["id"]),
            "x": round(x0, 2), "y": round(y0, 2),
            "w": round(max(1.0, x1 - x0), 2), "h": round(max(1.0, y1 - y0), 2),
            "pin": node.get("pin") or {"x": "left", "y": "top"},
        }
        if node["kind"] == "image":
            entry["file"] = node["file"]
            if node.get("nine"):
                iw, ih = node["img"].size
                b = node["nine"]
                entry["margin"] = [
                    round(b["left"] / max(1, iw), 4),
                    round(b["top"] / max(1, ih), 4),
                    round(b["right"] / max(1, iw), 4),
                    round(b["bottom"] / max(1, ih), 4),
                ]
        elif node["kind"] == "text":
            t = node["info"]
            col = _first_color_hexlike(t["color"], colors)
            entry["text"] = str(t["text"])
            entry["size"] = int(round(float(t["size"])))
            entry["color"] = [round(c_ / 255.0, 4) for c_ in col]
            entry["align"] = str(t.get("align", "left"))
        elif node["kind"] in ("input", "scroll", "slider", "toggle", "dropdown"):
            el = node["el"]
            entry["props"] = {
                "value": el.get("value"),
                "placeholder": el.get("placeholder", ""),
                "password": str(el.get("input_type", "")).lower() == "password",
                "direction": str(el.get("direction", "vertical")).lower(),
                "items": [(it.get("title") or it.get("label") or str(it)) if isinstance(it, dict) else str(it)
                          for it in (el.get("items") or [])],
                "min": float(el.get("min", 0.0)),
                "max": float(el.get("max", 100.0)),
                "step": float(el.get("step", 1.0)),
                "checked": bool(el.get("checked", False)),
                "options": [str(o) for o in (el.get("options") or [])],
                "selected": el.get("selected", 0),
                "label": str(el.get("label") or ""),
            }
        spec_nodes.append(entry)

    script = f'''# {bp_name}_build_umg.py - generated by uiforge-mcp for Unreal Engine 5.5-5.8
# Run in Unreal Editor (Python Editor Script Plugin + Editor Scripting Utilities enabled):
#   Output Log -> Python -> py "<path>/{bp_name}_build_umg.py"
import json
import os
import unreal

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DEST_PATH = {json.dumps(unreal_content_path)}
BP_NAME = {json.dumps(bp_name)}
CANVAS_W = {W:g}
CANVAS_H = {H:g}
NODES = json.loads({json.dumps(json.dumps(spec_nodes, ensure_ascii=False))})


def _import_textures(src_dir, dest_path):
    tasks = []
    by_stem = {{}}
    for n in NODES:
        if n["kind"] != "image":
            continue
        fpath = os.path.join(src_dir, n["file"])
        if not os.path.isfile(fpath):
            continue
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", fpath)
        t.set_editor_property("destination_path", dest_path + "/Textures")
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
        by_stem[os.path.splitext(n["file"])[0]] = n["id"]
    textures = {{}}
    if not tasks:
        return textures
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    for t in tasks:
        for obj_path in t.get_editor_property("imported_object_paths"):
            tex = unreal.load_asset(obj_path)
            if not isinstance(tex, unreal.Texture2D):
                continue
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
            tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
            tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
            tex.set_editor_property("srgb", True)
            tex.set_editor_property("never_stream", True)
            unreal.EditorAssetLibrary.save_loaded_asset(tex)
            nid = by_stem.get(tex.get_name())
            if nid:
                textures[nid] = tex
    return textures


def _anchor_range(pin, a0, a1, span):
    if pin in ("right", "bottom"):
        return 1.0, 1.0, a0 - span, a1 - a0
    if pin in ("center", "middle"):
        return 0.5, 0.5, a0 - span * 0.5, a1 - a0
    if pin == "stretch":
        return 0.0, 1.0, a0, span - a1
    if pin == "scale":
        return a0 / span, a1 / span, 0.0, 0.0
    return 0.0, 0.0, a0, a1 - a0


def _apply_slot(slot, n):
    if slot is None:
        return
    pin = n.get("pin") or {{}}
    px, py = pin.get("x", "left"), pin.get("y", "top")
    ax0, ax1, ox, sx = _anchor_range(px, n["x"], n["x"] + n["w"], CANVAS_W)
    ay0, ay1, oy, sy = _anchor_range(py, n["y"], n["y"] + n["h"], CANVAS_H)
    anchors = unreal.Anchors(minimum=unreal.Vector2D(ax0, ay0), maximum=unreal.Vector2D(ax1, ay1))
    slot.set_anchors(anchors)
    slot.set_offsets(unreal.Margin(left=ox, top=oy, right=sx, bottom=sy))


def build_umg(src_dir=SRC_DIR, dest_path=DEST_PATH, bp_name=BP_NAME):
    textures = _import_textures(src_dir, dest_path)
    full_path = dest_path.rstrip("/") + "/" + bp_name
    wbp = unreal.load_asset(full_path) if unreal.EditorAssetLibrary.does_asset_exist(full_path) else None
    if wbp is None:
        factory = unreal.WidgetBlueprintFactory()
        wbp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            bp_name, dest_path, unreal.WidgetBlueprint, factory
        )
    if wbp is None:
        raise RuntimeError("Could not create WidgetBlueprint at " + full_path)

    subsys = unreal.get_editor_subsystem(unreal.WidgetEditorSubsystem) if hasattr(unreal, "WidgetEditorSubsystem") else None
    tree = getattr(wbp, "widget_tree", None)
    if tree is None:
        tree = unreal.find_object(wbp, "WidgetTree")

    def _make(cls, wname, parent_panel=None):
        if hasattr(unreal, "WidgetBlueprintEditorUtils") and hasattr(unreal.WidgetBlueprintEditorUtils, "create_widget"):
            w = unreal.WidgetBlueprintEditorUtils.create_widget(wbp, cls, wname)
        elif tree is not None and hasattr(tree, "construct_widget"):
            w = tree.construct_widget(cls, wname)
        else:
            w = unreal.new_object(cls, outer=tree or wbp, name=wname)
        if parent_panel is not None and w is not None:
            return w, parent_panel.add_child(w)
        return w, None

    root_panel, _ = _make(unreal.CanvasPanel, "RootCanvas")
    if tree is not None:
        if hasattr(tree, "set_root_widget"):
            tree.set_root_widget(root_panel)
        elif hasattr(tree, "root_widget"):
            tree.root_widget = root_panel

    for idx, n in enumerate(NODES):
        kind = n["kind"]
        wname = n["id"] + "_" + str(idx)
        props = n.get("props") or {{}}
        if kind == "image":
            w, slot = _make(unreal.Image, wname, root_panel)
            tex = textures.get(n["id"])
            if tex is not None and hasattr(w, "set_brush_from_texture"):
                w.set_brush_from_texture(tex, match_size=False)
                if n.get("margin"):
                    m = n["margin"]
                    brush = w.get_editor_property("brush")
                    brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.BOX)
                    brush.set_editor_property("margin", unreal.Margin(left=m[0], top=m[1], right=m[2], bottom=m[3]))
                    w.set_editor_property("brush", brush)
            _apply_slot(slot, n)
        elif kind == "text":
            w, slot = _make(unreal.TextBlock, wname, root_panel)
            w.set_text(n.get("text", ""))
            col = n.get("color", [1.0, 1.0, 1.0, 1.0])
            w.set_color_and_opacity(unreal.SlateColor(unreal.LinearColor(col[0], col[1], col[2], col[3])))
            _apply_slot(slot, n)
        elif kind == "input":
            w, slot = _make(unreal.EditableTextBox, wname, root_panel)
            w.set_text(str(props.get("value") or ""))
            if hasattr(w, "set_hint_text"):
                w.set_hint_text(str(props.get("placeholder") or ""))
            if props.get("password") and hasattr(w, "set_is_password"):
                w.set_is_password(True)
            _apply_slot(slot, n)
        elif kind == "scroll":
            w, slot = _make(unreal.ScrollBox, wname, root_panel)
            if props.get("direction") == "horizontal" and hasattr(w, "set_orientation"):
                w.set_orientation(unreal.Orientation.ORIENT_HORIZONTAL)
            for i, it in enumerate(props.get("items") or []):
                item_w, _ = _make(unreal.TextBlock, wname + "_Item_" + str(i), w)
                item_w.set_text(str(it))
            _apply_slot(slot, n)
        elif kind == "slider":
            w, slot = _make(unreal.Slider, wname, root_panel)
            w.set_min_value(float(props.get("min", 0.0)))
            w.set_max_value(float(props.get("max", 100.0)))
            w.set_step_size(float(props.get("step", 1.0)))
            w.set_value(float(props.get("value", 50.0)))
            _apply_slot(slot, n)
        elif kind == "toggle":
            w, slot = _make(unreal.CheckBox, wname, root_panel)
            w.set_is_checked(bool(props.get("checked", False)))
            _apply_slot(slot, n)
        elif kind == "dropdown":
            w, slot = _make(unreal.ComboBoxString, wname, root_panel)
            opts = props.get("options") or []
            for o in opts:
                w.add_option(str(o))
            sel = props.get("selected", 0)
            chosen = sel if (isinstance(sel, str) and sel in opts) else (opts[int(sel)] if (opts and 0 <= int(sel or 0) < len(opts)) else "")
            if chosen:
                w.set_selected_option(str(chosen))
            _apply_slot(slot, n)

    if hasattr(unreal, "BlueprintEditorLibrary"):
        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(wbp)
        except Exception:
            pass
    unreal.EditorAssetLibrary.save_loaded_asset(wbp)
    unreal.log("uiforge-mcp: built Unreal UMG WidgetBlueprint " + full_path + " with " + str(len(NODES)) + " widgets")
    return wbp


if __name__ == "__main__":
    build_umg()
'''
    out = folder / f"{bp_name}_build_umg.py"
    out.write_text(script, encoding="utf-8")
    return out


@tool
def export_screen(canvas: str, engine: str, out_dir: str | None = None, name: str | None = None,
                  scale: float = 1, bake_text: bool = False, language: str | None = None,
                  godot_res_path: str | None = None, unreal_content_path: str = "/Game/UI/Generated"):
    """Turn a screen mockup into a real engine or native desktop UI: image pieces + scene/view/script
    rebuilding the layout with native text, Input, Scroll, Slider, Toggle, Dropdown widgets and responsive pins.
    When the canvas has interactions, data bindings or focus_order, also emits a ready controller/ViewModel.

    engine:
      Game engines:
        - "godot"      (.tscn with LineEdit/ScrollContainer/HSlider/CheckButton/OptionButton + _controller.gd)
        - "roblox"     (LocalScript with ScreenGui + TextBox/ScrollingFrame/controls)
        - "unity"      (UI Toolkit .uxml + .uss with TextField/ScrollView/Slider/Toggle/DropdownField + Controller.cs)
        - "unity-ugui" (C# uGUI Canvas / RectTransform / InputField / ScrollRect / Slider / Toggle / Dropdown builder)
        - "unreal"     (UE 5.5-5.8 Python UMG WidgetBlueprint builder with CanvasPanel/Image 9-slice/TextBlock/EditableTextBox/ScrollBox/Slider/CheckBox/ComboBoxString)
      C# / .NET & C++ desktop UI frameworks:
        - "wpf"        (C# .NET Framework 4.8 & .NET 8/9 WPF .xaml + .xaml.cs + INotifyPropertyChanged ViewModel)
        - "avalonia"   (Cross-platform .NET 8/9 Avalonia .axaml + .axaml.cs + ViewModel)
        - "winui"      (Windows App SDK / WinUI 3 .xaml + .xaml.cs + ViewModel)
        - "qt-qml"     (C++ Qt 6 Quick .qml with TextField, ScrollView, Slider, Switch, ComboBox)
        - "imgui"      (C++17 Dear ImGui self-contained _ui.hpp header with State struct & all native widgets)
      Generic:
        - "json"       (pieces + layout JSON only)
    Pieces: every element group becomes one image (so group each widget), ungrouped elements one image
    each. Text and interactive widgets stay native unless bake_text=true (text only). Pieces pinned
    "stretch" get 9-slice margins when their centre allows it. scale: export pieces at 2x for high-DPI.
    """
    from .desktop_export import DESKTOP_ENGINES, write_desktop
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, language)
    engine = engine.lower()
    valid_engines = ("godot", "roblox", "unity", "unity-ugui", "unreal", "json") + DESKTOP_ENGINES
    if engine not in valid_engines:
        raise ValueError(f"engine must be one of {', '.join(valid_engines)}")
    scale = max(0.5, min(4.0, float(scale)))
    base = slugify(name or c["id"], "screen")
    folder = _out_dir(out_dir, f"screens/{base}")
    nodes, warnings = _pieces(c, scale, bake_text, language)
    colors = st.renderer(c).colors
    fonts_copied = []
    for node in nodes:
        if node["kind"] == "image":
            node["file"] = f"{node['id']}.png"
            node["scale"] = scale
            node["img"].save(folder / node["file"])
            pin = node["pin"]
            if pin.get("x") == "stretch" or pin.get("y") == "stretch":
                b = ex.detect_nine_slice(node["img"])
                if b["stretch_x"] or b["stretch_y"]:
                    small, b = ex.minimize_nine_slice(node["img"], b)
                    node["img"] = small
                    small.save(folder / node["file"])
                    node["nine"] = {k: b[k] for k in ("left", "top", "right", "bottom")}
        elif node["kind"] == "text":
            src = node["info"].get("_font_path")
            if src and Path(src).is_file():
                dst = folder / Path(src).name
                if not dst.exists():
                    shutil.copyfile(src, dst)
                    fonts_copied.append(dst.name)
                node["font_file"] = dst.name
    layout = {"canvas": {"id": c["id"], "width": c["width"], "height": c["height"]}, "scale": scale,
              "data": c.get("data"), "bindings": c.get("bindings"), "interactions": c.get("interactions"),
              "focus_order": c.get("focus_order"),
              "nodes": [{k: v for k, v in {
                  "kind": n["kind"], "id": n["id"], "x": round(n["box"][0], 2), "y": round(n["box"][1], 2),
                  "width": round(n["box"][2] - n["box"][0], 2), "height": round(n["box"][3] - n["box"][1], 2),
                  "pin": n["pin"] or {"x": "left", "y": "top"}, "file": n.get("file"), "nine_slice": n.get("nine"),
                  "members": n.get("members"),
                  "text": {k: v for k, v in n["info"].items() if not k.startswith("_")} if n["kind"] == "text" else None,
                  "widget": ({k: v for k, v in n["el"].items() if k not in ("type", "id", "x", "y", "width", "height")}
                             if n["kind"] in ("input", "scroll", "slider", "toggle", "dropdown") else None),
              }.items() if v is not None} for n in nodes]}
    layout = {k: v for k, v in layout.items() if v is not None}
    (folder / f"{base}.screen.json").write_text(json.dumps(layout, ensure_ascii=False, indent=1), encoding="utf-8")
    files = [f"{base}.screen.json"]
    nxt = "Use the pieces and layout JSON in your engine."
    if engine == "godot":
        out = _write_godot(c, nodes, folder, godot_res_path or f"res://ui/{base}", base, colors)
        files.append(out.name)
        ctrl = _write_godot_controller(c, nodes, folder, base, colors=colors)
        if ctrl:
            files.append(ctrl.name)
        nxt = (f"Copy the folder to {godot_res_path or f'res://ui/{base}'} in your Godot 4 project and instance "
               f"{out.name} under a CanvasLayer. Labels, LineEdit, ScrollContainer, HSlider, CheckButton and OptionButton are native.")
    elif engine == "roblox":
        out = _write_roblox(c, nodes, folder, base, colors)
        files.append(out.name)
        nxt = ("Upload the PNGs in Studio, paste their ids into IMAGES at the top of the script, and put the "
               "LocalScript in StarterPlayerScripts. TextBox, ScrollingFrame and interactive controls are native Roblox instances.")
    elif engine == "unity":
        outs = _write_unity(c, nodes, folder, base, colors)
        files += [o.name for o in outs]
        ctrl = _write_unity_controller(c, nodes, folder, base)
        if ctrl:
            files.append(ctrl.name)
        nxt = (f"Put the folder under Assets/, create a UIDocument with {base}.uxml and a PanelSettings set to "
               f"Scale With Screen Size, reference {c['width']}x{c['height']}, match = 1.")
    elif engine == "unity-ugui":
        out = _write_unity_ugui(c, nodes, folder, base, colors)
        files.append(out.name)
        nxt = (f"Put {out.name} in Assets/Editor/ and run Tools -> UIForge -> Build {_pascal_id(base)}UGuiBuilder "
               "to create a ready uGUI Canvas with RectTransform anchors and native UI widgets.")
    elif engine == "unreal":
        out = _write_unreal_umg(c, nodes, folder, base, colors, unreal_content_path)
        files.append(out.name)
        nxt = (f'In Unreal Engine 5.5-5.8: Output Log -> switch Cmd to Python -> py "{out.as_posix()}" '
               f"to import PNGs and generate WBP_{_pascal_id(base)} in {unreal_content_path}.")
    elif engine in DESKTOP_ENGINES:
        outs, nxt = write_desktop(engine, c, nodes, folder, base, colors)
        files += [o.name for o in outs]
    result: dict = {"folder": str(folder), "engine": engine, "files": files,
                    "pieces": [n["id"] for n in nodes if n["kind"] == "image"],
                    "texts": [n["id"] for n in nodes if n["kind"] == "text"],
                    "widgets": [n["id"] for n in nodes if n["kind"] in ("input", "scroll", "slider", "toggle", "dropdown")], "next": nxt}
    if fonts_copied:
        result["fonts_copied"] = fonts_copied
    notes = []
    for n in nodes:
        if n["kind"] == "text" and isinstance(n["info"]["color"], dict):
            notes.append(f"{n['id']}: gradient text is exported with its first colour; bake_text=true keeps the gradient")
    if any(n["kind"] == "text" and n["info"].get("weight") and str(n["info"].get("font", "")).lower() in ("inter",)
           for n in nodes):
        notes.append("Inter is a variable font: set the weight in the engine's font settings if it shows regular")
    notes = shaping.engine_notes(engine, [n["info"]["text"] for n in nodes if n["kind"] == "text"]) + notes
    if notes:
        result["notes"] = notes[:10]
    if warnings:
        result["warnings"] = sorted(set(warnings))[:10]
    return result


@tool
def export_pbr_maps(canvas: str, out_dir: str | None = None, name: str | None = None, scale: float = 1,
                    engine: str = "generic", normal_format: str | None = None, include_background: bool = False,
                    godot_res_path: str | None = None):
    """Export real-time engine PBR texture maps straight from a 2D UI canvas so game engines (Unity URP/HDRP,
    Unreal Engine, Godot 4 CanvasTexture + Light2D, Blender, Three.js) can dynamically light your UI.

    Writes: <name>_beauty.png (final lit render), <name>_albedo.png (unlit base colour), <name>_normal.png
    (exact tangent-space normal map), <name>_roughness.png, <name>_metallic.png, <name>_ao.png,
    <name>_height.png, <name>_orm.png (R=AO, G=Roughness, B=Metallic), <name>_emissive.png and <name>_pbr.json.
    engine: "generic" | "unity" | "unreal" | "godot".
      - "unreal" automatically uses DirectX (-Y) normals unless normal_format is passed.
      - "godot" also writes a ready Godot 4 <name>.canvas_texture.tres wired to diffuse + normal + specular.
    normal_format: "opengl" (+Y green, Unity/Godot/Blender/glTF) or "directx" (-Y green, Unreal).
    """
    st = store()
    c = st.get(canvas)
    eng = str(engine or "generic").lower()
    if eng not in ("generic", "unity", "unreal", "godot"):
        raise ValueError("engine must be 'generic', 'unity', 'unreal' or 'godot'")
    nfmt = str(normal_format or ("directx" if eng == "unreal" else "opengl")).lower()
    if nfmt not in ("opengl", "directx"):
        raise ValueError("normal_format must be 'opengl' or 'directx'")
    sc = max(0.25, min(4.0, float(scale)))
    base = slugify(name or c["id"], "pbr")
    folder = _out_dir(out_dir, f"pbr/{base}")
    r = st.renderer(c, sc)
    maps = r.render_pbr_maps(normal_format=nfmt, include_background=include_background)
    files: dict[str, str] = {}
    for key, img in maps.items():
        fname = f"{base}_{key}.png"
        img.save(folder / fname, optimize=True)
        files[key] = fname
    extras: list[str] = []
    if eng == "godot":
        import numpy as _np
        from PIL import Image as _Image
        r_arr = (255 - _np.asarray(maps["roughness"].convert("L"), dtype=_np.uint8))
        sm_name = f"{base}_smoothness.png"
        _Image.fromarray(r_arr, "L").save(folder / sm_name, optimize=True)
        files["smoothness"] = sm_name
        res = (godot_res_path or f"res://ui/pbr/{base}").rstrip("/")
        if not re.fullmatch(r"res://[A-Za-z0-9_\-/.]*", res) or ".." in res:
            raise ValueError("godot_res_path must be a res:// path without '..'")
        tres = (
            '[gd_resource type="CanvasTexture" load_steps=4 format=3]\n\n'
            f'[ext_resource type="Texture2D" path="{res}/{files["albedo"]}" id="1_albedo"]\n'
            f'[ext_resource type="Texture2D" path="{res}/{files["normal"]}" id="2_normal"]\n'
            f'[ext_resource type="Texture2D" path="{res}/{sm_name}" id="3_spec"]\n\n'
            '[resource]\n'
            'diffuse_texture = ExtResource("1_albedo")\n'
            'normal_texture = ExtResource("2_normal")\n'
            'specular_texture = ExtResource("3_spec")\n'
            'specular_shininess = 0.65\n'
        )
        tname = f"{base}.canvas_texture.tres"
        (folder / tname).write_text(tres, encoding="utf-8")
        extras.append(tname)
    elif eng == "unreal":
        ue_py = (
            f"# {base}_import_pbr.py - generated by uiforge-mcp for Unreal Engine 5.5-5.8\n"
            "import os\nimport unreal\n\n"
            "SRC = os.path.dirname(os.path.abspath(__file__))\n"
            f'DEST = "/Game/UI/PBR/{base}"\n'
            f"MAPS = {json.dumps(files, indent=2)}\n\n"
            "def run(src=SRC, dest=DEST):\n"
            "    tasks = []\n"
            "    by_stem = {}\n"
            "    for role, fname in MAPS.items():\n"
            "        fpath = os.path.join(src, fname)\n"
            "        if not os.path.isfile(fpath):\n"
            "            continue\n"
            "        t = unreal.AssetImportTask()\n"
            '        t.set_editor_property("filename", fpath)\n'
            '        t.set_editor_property("destination_path", dest)\n'
            '        t.set_editor_property("automated", True)\n'
            '        t.set_editor_property("replace_existing", True)\n'
            '        t.set_editor_property("save", True)\n'
            "        tasks.append(t)\n"
            "        by_stem[os.path.splitext(fname)[0]] = role\n"
            "    if not tasks:\n"
            "        return\n"
            "    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)\n"
            "    for t in tasks:\n"
            '        for p in t.get_editor_property("imported_object_paths"):\n'
            "            tex = unreal.load_asset(p)\n"
            "            if not isinstance(tex, unreal.Texture2D):\n"
            "                continue\n"
            "            role = by_stem.get(tex.get_name(), 'albedo')\n"
            "            if role == 'normal':\n"
            '                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)\n'
            '                tex.set_editor_property("srgb", False)\n'
            "            elif role in ('orm', 'roughness', 'metallic', 'ao', 'height'):\n"
            '                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)\n'
            '                tex.set_editor_property("srgb", False)\n'
            "            else:\n"
            '                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)\n'
            '                tex.set_editor_property("srgb", True)\n'
            "            unreal.EditorAssetLibrary.save_loaded_asset(tex)\n\n"
            "run()\n"
        )
        uname = f"{base}_import_pbr.py"
        (folder / uname).write_text(ue_py, encoding="utf-8")
        extras.append(uname)
    meta = {"canvas": c["id"], "engine": eng, "normal_format": nfmt, "scale": sc,
            "size": [maps["albedo"].width, maps["albedo"].height],
            "channel_packing": {"orm": {"r": "ao", "g": "roughness", "b": "metallic"}},
            "files": files, "extras": extras}
    mfile = f"{base}_pbr.json"
    (folder / mfile).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"folder": str(folder), "engine": eng, "normal_format": nfmt,
            "size": [maps["albedo"].width, maps["albedo"].height],
            "files": files, "manifest": mfile, "extras": extras}


@tool
def export_project(canvases: list[str] | str, engine: str = "godot", out_dir: str | None = None,
                   name: str = "ui_project", scale: float = 1, single_file: bool = False,
                   scaffold: bool = False, language: str | None = None,
                   godot_res_path: str = "res://ui/generated"):
    """Export multiple connected UI screens as one cohesive multi-screen project with shared tokens,
    deduplicated fonts, and an auto-generated screen router / UIManager!

    engine: "godot" | "unity" | "unity-ugui" | "unreal" | "roblox" | "web" | "react" | "wpf" | "avalonia" | "winui" | "qt-qml" | "imgui".
    - For "godot": writes screens/<id>/ + shared tokens/ui_theme.gd + ready UIManager.gd screen router!
    - For "unity": writes screens/<id>/ + shared tokens/ui_theme.uss + UiScreenRouter.cs!
    - For "web": multi-page or single-file (single_file=true) shareable HTML prototype with shared state!
    - For "react": full TypeScript React components + optional runnable Vite starter (scaffold=true)!
    """
    from . import server as _srv
    st = store()
    raw_names = [canvases] if isinstance(canvases, str) and not canvases.strip().startswith("[") else (_maybe_json(canvases) or [])
    if not raw_names:
        raise ValueError("canvases must list at least one canvas id")
    c_list = [st.get(cid) for cid in raw_names]
    eng = str(engine or "godot").lower()
    base = slugify(name, "ui_project")
    root = _out_dir(out_dir, f"projects/{base}")
    tokens_dir = root / "tokens"
    tokens_dir.mkdir(parents=True, exist_ok=True)
    tok_fmt = {"godot": "gdscript", "unity": "uss", "unity-ugui": "csharp", "roblox": "luau"}.get(eng, "css")
    tok_ext = {"gdscript": ".gd", "uss": ".uss", "csharp": ".cs", "luau": ".luau", "css": ".css"}[tok_fmt]
    export_theme(tok_fmt, path=str(tokens_dir / f"ui_theme{tok_ext}"))

    if eng == "web":
        wres = _srv.export_web([c["id"] for c in c_list], out_dir=str(root / "web"),
                               language=language, single_file=bool(single_file), shared_state=True)
        return {"folder": str(root), "engine": "web", "screens": [c["id"] for c in c_list],
                "web": wres, "tokens": str(tokens_dir / f"ui_theme{tok_ext}")}
    if eng == "react":
        rres = _srv.export_react([c["id"] for c in c_list], out_dir=str(root / "react"),
                                 language=language, css="tailwind", typescript=True, scaffold=bool(scaffold))
        return {"folder": str(root), "engine": "react", "screens": [c["id"] for c in c_list],
                "react": rres, "tokens": str(tokens_dir / f"ui_theme{tok_ext}")}

    screens_dir = root / "screens"
    fonts_dir = root / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    exported_screens: dict[str, dict] = {}
    shared_fonts: set[str] = set()
    for c in c_list:
        sid = slugify(c["id"], "screen")
        s_folder = screens_dir / sid
        res = export_screen(
            c["id"], engine=eng, out_dir=str(s_folder), name=sid, scale=scale,
            language=language, godot_res_path=f"{godot_res_path.rstrip('/')}/screens/{sid}",
        )
        # Deduplicate copied fonts into shared root/fonts/
        for fname in res.get("fonts_copied") or []:
            src_f = s_folder / fname
            dst_f = fonts_dir / fname
            if src_f.is_file() and not dst_f.exists():
                shutil.copyfile(src_f, dst_f)
            shared_fonts.add(fname)
        exported_screens[c["id"]] = res

    router_file: str | None = None
    if eng == "godot":
        res_base = godot_res_path.rstrip("/")
        entries = ",\n".join(
            f'\t"{c["id"]}": "{res_base}/screens/{slugify(c["id"], "screen")}/{slugify(c["id"], "screen")}.tscn"'
            for c in c_list
        )
        first_id = c_list[0]["id"]
        mgr = (
            f"# UIManager.gd - generated by uiforge-mcp multi-screen project export\n"
            f"extends CanvasLayer\n\n"
            f"signal sfx_requested(sfx_name: String)\n\n"
            f"const SCREENS := {{\n{entries}\n}}\n\n"
            f"var shared_data: Dictionary = {{}}\n"
            f"var _stack: Array[String] = []\n"
            f"var _active: Node = null\n\n"
            f'func _ready() -> void:\n\tnavigate("{first_id}")\n\n'
            f"func navigate(screen_id: String, mode: String = \"navigate\") -> void:\n"
            f'\tif screen_id == "back" or mode == "back":\n'
            f"\t\tif _stack.size() > 1:\n\t\t\t_stack.pop_back()\n\t\t\t_mount(_stack[-1])\n\t\treturn\n"
            f"\tif not SCREENS.has(screen_id):\n\t\tpush_warning(\"Unknown screen: \" + screen_id)\n\t\treturn\n"
            f"\t_stack.append(screen_id)\n\t_mount(screen_id)\n\n"
            f"func _mount(screen_id: String) -> void:\n"
            f"\tif _active:\n\t\t_active.queue_free()\n"
            f"\tvar scene: PackedScene = load(SCREENS[screen_id])\n"
            f"\tif scene == null: return\n"
            f"\t_active = scene.instantiate()\n\tadd_child(_active)\n"
            f'\tif _active.has_signal("navigate_requested"): _active.navigate_requested.connect(navigate)\n'
            f'\tif _active.has_signal("sfx_requested"): _active.sfx_requested.connect(func(s): sfx_requested.emit(s))\n'
            f'\tif _active.has_method("set_data") and not shared_data.is_empty(): _active.set_data(shared_data)\n'
        )
        rpath = root / "UIManager.gd"
        rpath.write_text(mgr, encoding="utf-8")
        router_file = str(rpath)
    elif eng in ("unity", "unity-ugui"):
        names_arr = ", ".join(f'"{c["id"]}"' for c in c_list)
        cs = (
            "// UiScreenRouter.cs - generated by uiforge-mcp multi-screen project export\n"
            "using System.Collections.Generic;\nusing UnityEngine;\n\n"
            "public class UiScreenRouter : MonoBehaviour\n{\n"
            f"    public static readonly string[] ScreenIds = new[] {{ {names_arr} }};\n"
            "    private readonly Stack<string> _history = new();\n"
            "    public string CurrentScreen => _history.Count > 0 ? _history.Peek() : ScreenIds[0];\n"
            "    public void Navigate(string target, string mode = \"navigate\") {\n"
            "        if (target == \"back\" || mode == \"back\") { if (_history.Count > 1) _history.Pop(); return; }\n"
            "        _history.Push(target);\n"
            "    }\n"
            "}\n"
        )
        rpath = root / "UiScreenRouter.cs"
        rpath.write_text(cs, encoding="utf-8")
        router_file = str(rpath)

    return {
        "folder": str(root),
        "engine": eng,
        "screens": [c["id"] for c in c_list],
        "shared_fonts": sorted(shared_fonts),
        "tokens": str(tokens_dir / f"ui_theme{tok_ext}"),
        "router": router_file,
        "details": {k: {"folder": v["folder"], "files": v["files"]} for k, v in exported_screens.items()},
    }
