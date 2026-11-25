"""uiforge-mcp: a local MCP server that lets an AI draw game UI assets with drawing tools.

No AI image generation and no network access: every pixel comes from the shapes,
text and effects the model asks for. Run with ``python -m uiforge_mcp``.
"""

from __future__ import annotations

import functools
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

try:
    from mcp.server.mcpserver import Image, MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP as _Server, Image
    try:
        from mcp.server.fastmcp.exceptions import ToolError
    except ImportError:
        ToolError = RuntimeError
try:
    from mcp.types import ToolAnnotations
except ImportError:
    ToolAnnotations = None

from . import animation as anim_mod
from . import export as ex
from . import psd as psd_mod
from . import engines
from .render import TextLayout, backdrop, composite as _composite, resolve_style
from .store import Store, slugify

INSTRUCTIONS = """\
Draw game and app UI (panels, buttons, bars, icons, HUDs, whole screens) as layered vector elements on
canvases, look at them with `preview`, fix them, then export for Unity / Unreal / Godot / Roblox / Figma.
Local and deterministic: no image model. Build icons with add_path / add_svg and AAA bordered panels
fast with add_frame (rpg_gold, scifi_hud, cyber_tech, glass_card, medieval_iron, luxury_minimal, cartoon_thick).

Workflow: set_theme (tokens, styles, modes, HDRI environment) -> create_canvas / import_screenshot ->
batch / add_* (add_frame, add_input, add_scroll...) -> preview -> review_canvas -> update_element ->
export (export_asset, export_pbr_maps, export_png, export_svg, export_layers, export_atlas...).
Interactive / data-driven UI: set_binding (variables & expressions), create_animation / set_state,
set_interaction (hover, click, keys, sfx) -> export_web, export_react (CSS / Tailwind / TypeScript),
export_animation (dotlottie v2 state machine / lottie / mp4 / webm / spritesheet), or export_screen
(Unity UI Toolkit / uGUI, Godot, Roblox, C# .NET WPF / Avalonia / WinUI, C++ Qt QML / Dear ImGui).
Use live_preview("start") so the human watches edits live. Always call preview before exporting.

Coordinates: canvas units = pixels at 1x, origin top-left, y down; later elements draw on top.
Colours: "#rrggbb", "#rrggbbaa", "rgba()", "hsl()", CSS names or "$token"; append "@0.5" for alpha.
Fill: colour, gradient (linear, radial, conic, diamond), pattern (stripes, dots, grid, hex, carbon,
brushed, clouds), image, "shader" formula, or a list of fills stacked bottom to top.
Style keys: material (39 Cook-Torrance PBR presets), pbr (metallic, roughness, clearcoat, ior,
anisotropy, sss, studio, env_map, shine), fill, stroke, shadow, glow, inner_shadow, inner_glow, bevel,
light, glass, blur, backdrop_blur, mask, adjust, opacity, blend, noise, texture.

Full reference: call guide(topic) before using an unfamiliar feature.
Topics: fills, shader, style, design, layers, geometry, text, reuse, review, animation, export.
"""

mcp = _Server("uiforge-mcp", instructions=INSTRUCTIONS)


def tool(fn):
    """Register ``fn`` as an MCP tool.

    The registered wrapper turns expected failures into ToolError so the model reads the real
    message (SDK 2.x hides the text of any other exception), and returns compact JSON.
    The plain function is returned unchanged so it can be called and tested directly.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except ToolError:
            raise
        except MemoryError as exc:
            raise ToolError(f"{fn.__name__}: out of memory. Use a smaller canvas, scale, region or frame count "
                            "and call again.") from exc
        except KeyError as exc:
            raise ToolError(f"{fn.__name__}: missing key {exc}. Add it to the argument and call again.") from exc
        except (ValueError, TypeError, OSError) as exc:
            raise ToolError(f"{fn.__name__}: {exc}\nFix that argument and call {fn.__name__} again "
                            "(do not repeat the identical call).") from exc
        except Exception as exc:
            raise ToolError(f"{fn.__name__}: unexpected {type(exc).__name__}: {exc}. This is likely a uiforge-mcp "
                            "bug, not your input. Do not repeat the identical call: change the value that "
                            "triggers it, split the step into smaller calls, or take another route.") from exc
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        return result

    name = fn.__name__
    read_only = name.startswith(("get_", "list_", "preview", "view_", "inspect_", "measure_", "find_")) or name in (
        "review_canvas", "guide")
    if ToolAnnotations is None:
        mcp.tool()(wrapper)
    else:
        mcp.tool(annotations=ToolAnnotations(readOnlyHint=read_only, destructiveHint=name.startswith("delete_"),
                                             idempotentHint=read_only, openWorldHint=False))(wrapper)
    return fn

_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def set_store(new_store: Store | None) -> None:
    """Swap the document store (used by tests)."""
    global _store
    _store = new_store



def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in "{[" and text[-1:] in "}]":
            try:
                return json.loads(text)
            except ValueError:
                return value
    return value


def _merge_style(style: Any, fill: Any = None, stroke: Any = None) -> Any:
    style, fill, stroke = _maybe_json(style), _maybe_json(fill), _maybe_json(stroke)
    if fill is None and stroke is None:
        return style
    if style is None:
        out: dict = {}
    elif isinstance(style, str):
        out = {"use": style}
    elif isinstance(style, dict):
        out = dict(style)
    else:
        raise ValueError("style must be a theme style name or an object")
    if fill is not None:
        out["fill"] = fill
    if stroke is not None:
        out["stroke"] = stroke
    return out


def _round(v: float) -> float:
    return round(float(v), 2)


def _box(st: Store, canvas: dict, el: dict) -> list[float]:
    x0, y0, x1, y1 = st.renderer(canvas).element_box(el)
    return [_round(x0), _round(y0), _round(x1 - x0), _round(y1 - y0)]


def _summary(st: Store, canvas: dict, el: dict, warnings: list[str] | None = None) -> dict:
    out = {"id": el["id"], "type": el["type"], "bbox_xywh": _box(st, canvas, el)}
    if el.get("layer"):
        out["layer"] = el["layer"]
    x, y, w, h = out["bbox_xywh"]
    if x < -0.5 or y < -0.5 or x + w > canvas["width"] + 0.5 or y + h > canvas["height"] + 0.5:
        out["note"] = "extends outside the canvas and will be cut off on export"
    if warnings:
        out["warnings"] = warnings
    return out


_SHORTHAND = ("fill", "stroke", "color")


def _prepare(etype: str, args: dict) -> dict:
    """Turn tool arguments into stored element properties."""
    props = {k: _maybe_json(v) for k, v in args.items() if v is not None}
    fill = props.pop("fill", None)
    stroke = props.pop("stroke", None)
    color = props.pop("color", None)
    if color is not None and fill is None:
        fill = color
    if etype in ("line", "arc", "ticks"):
        stroke = None
    style = _merge_style(props.pop("style", None), fill, stroke)
    if style is not None:
        props["style"] = style
    return props


def _add(canvas_id: str, etype: str, args: dict, checkpoint: bool = True) -> dict:
    st = store()
    canvas = st.get(canvas_id)
    el, warnings = st.add_element(canvas, etype, _prepare(etype, args), checkpoint=checkpoint)
    return _summary(st, canvas, el, warnings)


def _png_bytes(img: PILImage.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _out_path(path: str | None, default_name: str, subdir: str | None = None, suffixes: tuple = (".png",)) -> Path:
    st = store()
    if path:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = st.exports_dir / p
    else:
        p = st.exports_dir / (subdir or "") / default_name
    if p.suffix.lower() not in suffixes:
        raise ValueError(f"Output file must end with {' or '.join(suffixes)}")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _out_dir(out_dir: str | None, sub: str = "") -> Path:
    st = store()
    if out_dir:
        p = Path(out_dir).expanduser()
        if not p.is_absolute():
            p = st.exports_dir / p
    else:
        p = st.exports_dir / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def _scale_suffix(scale: float) -> str:
    if abs(scale - 1) < 1e-6:
        return ""
    text = f"{scale:g}".replace(".", "_")
    return f"_{text}x"



@tool
def create_canvas(name: str, width: int | None = None, height: int | None = None,
                  background: str | dict | None = None, preset: str | None = None):
    """Create a new canvas (one canvas = one asset or one screen mockup).

    Size the canvas to the asset: e.g. 64x64 icon, 320x96 button, 256x256 panel, 1920x1080 screen.
    Leave room for shadows/glows (they are cut off at the canvas edge), or draw roomy and fit_canvas later.
    background: omit for transparent (normal for assets); a color or gradient object for mockups.
    preset: a screen / device size that also records its safe area (notch, home bar, TV overscan) for
      preview(guides=["safe"]): 1080p, 1440p, 4k, 720p, ultrawide, ultrawide-1440, tv-1080p, steam-deck,
      switch, iphone, iphone-landscape, iphone-se, ipad, ipad-landscape, android, android-landscape,
      mobile-game-landscape, app-icon. Phone / tablet presets are in points / dp (the units app layouts
      use); export at scale 2-3 for device pixels.
    Returns the canvas id used by every other tool.
    """
    from . import layout as lay
    safe = None
    note = None
    if preset:
        pw, ph, safe, note = lay.preset(preset)
        width, height = width or pw, height or ph
    if not width or not height:
        raise ValueError("give width and height, or a preset")
    st = store()
    canvas = st.create_canvas(name, width, height, _maybe_json(background))
    if preset:
        canvas["device"] = str(preset).lower()
        if any(safe):
            canvas["safe_area"] = list(safe)
        st.save_canvas(canvas)
    out = {"canvas": canvas["id"], "width": canvas["width"], "height": canvas["height"],
           "workspace": str(st.workspace)}
    if preset:
        out["preset"] = {"name": canvas["device"], "note": note, "safe_area_ltrb": canvas.get("safe_area", [0, 0, 0, 0])}
    return out


@tool
def list_canvases():
    """List all canvases in the workspace (they persist between sessions)."""
    st = store()
    return {"workspace": str(st.workspace),
            "canvases": [{"canvas": c["id"], "name": c.get("name"), "width": c["width"], "height": c["height"],
                          "elements": len(c["elements"])} for c in st.canvases.values()]}


@tool
def get_canvas(canvas: str, details: bool = False, ids: list[str] | None = None):
    """Describe a canvas: its layers (bottom to top) and element ids in draw order with type, layer, group
    and bounding box.

    details=true also returns every stored property (use it before editing an element you did not just create).
    ids limits the result to those elements.
    """
    st = store()
    c = st.get(canvas)
    items = []
    for el in c["elements"]:
        if ids and el["id"] not in ids:
            continue
        item: dict = {"id": el["id"], "type": el["type"], "bbox_xywh": _box(st, c, el)}
        for key in ("layer", "group", "clip"):
            if el.get(key):
                item[key] = el[key]
        if el.get("visible") is False:
            item["visible"] = False
        if el["type"] == "text":
            item["text"] = el.get("text")
        if el.get("pin"):
            item["pin"] = el["pin"]
        if details:
            item["props"] = {k: v for k, v in el.items() if k not in ("id", "type")}
        items.append(item)
    out = {"canvas": c["id"], "name": c.get("name"), "width": c["width"], "height": c["height"],
           "background": c.get("background"), "elements": items}
    if c.get("layers"):
        out["layers_bottom_to_top"] = _layer_list(c)
        out["active_layer"] = c.get("active_layer")
    if c.get("animations"):
        out["animations"] = sorted(c["animations"])
    for key in ("device", "safe_area", "vars", "colors", "language", "pixel_art", "links"):
        if c.get(key):
            out[key] = c[key]
    if c.get("states"):
        out["states"] = {k: sorted(v) for k, v in c["states"].items()}
    return out


def _layer_list(c: dict) -> list[dict]:
    names = {layer["name"] for layer in c.get("layers", [])}
    out = []
    loose = sum(1 for e in c["elements"] if e.get("layer") not in names)
    if loose:
        out.append({"layer": "base", "elements": loose, "note": "implicit bottom layer for elements without a layer"})
    for layer in c.get("layers", []):
        item: dict = {"layer": layer["name"], "elements": sum(1 for e in c["elements"] if e.get("layer") == layer["name"])}
        for key in ("opacity", "blend", "clip", "visible"):
            if key in layer and layer[key] not in (None, 1, 1.0, "normal") and not (key == "clip" and not layer[key]) \
                    and not (key == "visible" and layer[key]):
                item[key] = layer[key]
        if layer.get("style"):
            item["style"] = layer["style"]
        out.append(item)
    return out


@tool
def update_canvas(canvas: str, name: str | None = None, width: int | None = None, height: int | None = None,
                  background: str | dict | None = None, clear_background: bool = False,
                  safe_area: list[float] | None = None, vars: dict | None = None, colors: dict | None = None,
                  language: str | None = None, pixel_art: bool | dict | None = None, mode: str | None = None,
                  focus_order: list[str] | None = None, environment: dict | None = None,
                  quality: str | None = None, style_preset: str | None = None):
    """Change canvas settings. Elements keep their coordinates when width/height change (use
    resize_canvas to move pinned elements with the edges).

    safe_area [left, top, right, bottom]: insets kept free of important UI (notch, rounded corners, TV
      overscan); shown by preview(guides=["safe"]) and checked by review_canvas.
    vars: values for {placeholders} in text on this canvas, e.g. {"name": "Iron Sword", "price": "250"}
      (merged; null removes a key). colors: canvas-only overrides of theme colour tokens, e.g.
      {"rarity": "#a855f7"} - one template, many recolours.
    language: default string-table language for this canvas (see set_strings).
    pixel_art: true or {"palette": [...colors], "max_colors": 16, "alpha_threshold": 128} - renders without
      anti-aliasing at 1x, snaps alpha and colours, and scales up by whole pixels. false turns it off.
    mode: theme variable mode for this canvas only (see set_theme modes); "" follows the theme's mode.
    focus_order: element ids in the order a gamepad / keyboard moves focus (accessibility and console UI);
      written to export_spec, export_web (tab order) and export_screen notes. [] clears it.
    environment: canvas-level PBR IBL environment override, e.g. {"env_map": "scene.hdr", "rotation": 45,
      "intensity": 1.2, "studio": "warm"}. Supports Radiance .hdr, OpenEXR .exr, or equirectangular PNG/JPG.
      Pass {} to clear the canvas override and inherit the workspace theme environment.
    quality: per-canvas quality tier override ("simple" | "standard" | "advanced" | "aaa"; "" resets).
    style_preset: per-canvas style preset ("kids" | "cartoon" | "stylized" | "minimal" | "web_saas" |
      "scifi" | "dark_fantasy" | "realistic" | "photorealistic"; "" resets).
    """
    st = store()
    c = st.get(canvas)
    if focus_order is not None:
        order = _maybe_json(focus_order) or []
        for fid in order:
            st.find(c, str(fid))
        if order:
            c["focus_order"] = [str(f) for f in order]
        else:
            c.pop("focus_order", None)
    if mode is not None:
        if mode and mode not in (st.theme.get("modes") or {}):
            raise ValueError(f"no mode '{mode}'. Modes: {', '.join(sorted(st.theme.get('modes') or {})) or '(none)'}")
        if mode:
            c["mode"] = mode
        else:
            c.pop("mode", None)
    changes: dict = {"name": name, "width": width, "height": height}
    if clear_background:
        changes["background"] = None
    elif background is not None:
        changes["background"] = _maybe_json(background)
    st.update_canvas(c, **changes)
    safe_area, vars, colors, pixel_art = (_maybe_json(v) for v in (safe_area, vars, colors, pixel_art))
    if safe_area is not None:
        if not isinstance(safe_area, list) or len(safe_area) != 4:
            raise ValueError("safe_area must be [left, top, right, bottom]")
        c["safe_area"] = [float(v) for v in safe_area]
    for key, value in (("vars", vars), ("colors", colors)):
        if value is not None:
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object")
            merged = dict(c.get(key) or {})
            for k2, v2 in value.items():
                if v2 is None:
                    merged.pop(k2, None)
                else:
                    merged[k2] = v2 if key == "colors" else str(v2)
            if key == "colors":
                from .colors import parse_color
                ctx = {**st.theme.get("colors", {}), **merged}
                for v2 in merged.values():
                    parse_color(v2, ctx)
            c[key] = merged
    if language is not None:
        c["language"] = language or None
    if pixel_art is not None:
        if pixel_art is False:
            c.pop("pixel_art", None)
        else:
            c["pixel_art"] = pixel_art if isinstance(pixel_art, dict) else True
            st.renderer(c, 0.25).render()
    env_cfg = _maybe_json(environment)
    if env_cfg is not None:
        if not isinstance(env_cfg, dict):
            raise ValueError('environment must be an object, e.g. {"env_map": "scene.hdr", "rotation": 45}')
        if not env_cfg:
            c.pop("environment", None)
        else:
            merged_env = dict(c.get("environment") or {})
            for ek, ev in env_cfg.items():
                if ev is None:
                    merged_env.pop(ek, None)
                else:
                    merged_env[ek] = ev
            if merged_env.get("env_map"):
                ep = Path(str(merged_env["env_map"])).expanduser()
                if not ep.is_file():
                    raise ValueError(f"environment.env_map file not found: {ep}")
                merged_env["env_map"] = str(ep.resolve())
            if merged_env:
                c["environment"] = merged_env
            else:
                c.pop("environment", None)
    if quality is not None or style_preset is not None:
        from . import profiles
        prof = dict(c.get("profile") or {})
        if quality is not None:
            nq = profiles.normalize_quality(quality)
            if nq:
                prof["quality"] = nq
            else:
                prof.pop("quality", None)
        if style_preset is not None:
            nsp = profiles.normalize_style_preset(style_preset)
            if nsp:
                prof["style_preset"] = nsp
            else:
                prof.pop("style_preset", None)
        if prof:
            c["profile"] = prof
        else:
            c.pop("profile", None)
    st.save_canvas(c)
    out = {"canvas": c["id"], "name": c["name"], "width": c["width"], "height": c["height"],
           "background": c.get("background")}
    for key in ("safe_area", "vars", "colors", "language", "pixel_art", "environment", "profile"):
        if c.get(key):
            out[key] = c[key]
    return out


@tool
def duplicate_canvas(canvas: str, new_name: str):
    """Copy a canvas with all its elements. Use it for button states (normal -> hover/pressed/disabled)
    or size variants: duplicate, then update_element only what differs."""
    st = store()
    clone = st.duplicate_canvas(st.get(canvas), new_name)
    return {"canvas": clone["id"], "elements": [e["id"] for e in clone["elements"]]}


@tool
def fit_canvas(canvas: str, padding: float = 0, include_animations: bool = True):
    """Resize the canvas to exactly what is painted (shadows and glows included) plus `padding`, moving
    every element and position keyframe so nothing changes visually. Use it after drawing an asset with
    generous room, so the exported PNG has no wasted transparent border and no clipped glow.
    include_animations also keeps every animation frame inside the new bounds."""
    st = store()
    c = st.get(canvas)
    return {"canvas": c["id"], **st.fit_canvas(c, padding, include_animations)}


@tool
def delete_canvas(canvas: str):
    """Delete a canvas and its saved project file. Exported PNGs are not touched.
    Refuses while other canvases still place it with add_instance (it names them)."""
    st = store()
    c = st.get(canvas)
    users = sorted({other["id"] for other in st.canvases.values() if other is not c
                    for e in other["elements"] if e["type"] == "instance" and e.get("source") == c["id"]})
    if users:
        raise ValueError(f"canvas '{c['id']}' is used as an instance on: {', '.join(users)}. "
                         "Delete or change those instances first.")
    st.delete_canvas(c)
    return {"deleted": c["id"]}



def _layer_settings(opacity, blend, clip, visible, style) -> dict:
    out: dict = {}
    if opacity is not None:
        out["opacity"] = max(0.0, min(1.0, float(opacity)))
    if blend is not None:
        out["blend"] = str(blend).lower()
    if clip is not None:
        out["clip"] = bool(clip)
    if visible is not None:
        out["visible"] = bool(visible)
    style = _maybe_json(style)
    if style is not None:
        out["style"] = style
    return out


@tool
def create_layer(canvas: str, name: str, opacity: float = 1, blend: str = "normal", clip: bool = False,
                 visible: bool = True, style: str | dict | None = None, position: str | None = None):
    """Add a layer to the canvas and make it the active one: every element you add afterwards lands on it
    (or pass layer="..." to an add tool). Layers stack bottom to top; elements drawn before any layer
    exists stay in the implicit bottom layer "base".

    Build in passes the way an artist does, one layer each: base shapes -> shading -> highlights ->
    details -> text. That keeps each pass adjustable (opacity, blend, hide) and exportable on its own.

    opacity: 0-1 for the whole layer. blend: how the layer mixes with what is below - "normal",
      "multiply" (shadows, tinting), "screen" / "add" (light, glow), "overlay" / "soft-light" (contrast,
      colored light), "color-dodge", "color-burn", "hard-light", "darken", "lighten", "difference".
    clip=true: the layer only shows where the layer directly below it has pixels. Paint freely on a
      clipped layer - soft dark ellipses for shading, light streaks for gloss - and nothing spills outside
      the base shape. Several clipped layers in a row all clip to the same base.
    style: effects applied to the merged content of the layer as one shape - shadow, glow, stroke (one
      outline around a whole icon + text group), light (emboss), inner_shadow, blur, adjust, mask.
      Use it instead of repeating an effect on every element.
    position: "top" (default), "bottom", "above:<layer>", "below:<layer>" or an index (0 = lowest).
    """
    st = store()
    c = st.get(canvas)
    layer = st.create_layer(c, name, _layer_settings(None if opacity == 1 else opacity, None if blend == "normal" else blend,
                                                     clip or None, None if visible else False, style), position)
    return {"layer": layer["name"], "active_layer": c.get("active_layer"), "layers_bottom_to_top": _layer_list(c)}


@tool
def update_layer(canvas: str, layer: str, name: str | None = None, opacity: float | None = None,
                 blend: str | None = None, clip: bool | None = None, visible: bool | None = None,
                 style: dict | str | None = None, position: str | None = None, activate: bool | None = None):
    """Change a layer: rename, opacity, blend mode, clip, show / hide, restack (position), or its style
    (merged key by key into the current style; set a key to null to remove that effect).
    activate=true makes it the layer new elements go to. Hiding a layer is a quick way to compare a
    design with and without a shading pass."""
    st = store()
    c = st.get(canvas)
    target = st.get_layer(c, layer)
    changes = _layer_settings(opacity, blend, clip, visible, style)
    if name:
        changes["name"] = name
    updated = st.update_layer(c, target, changes, position, activate)
    return {"layer": updated["name"], "active_layer": c.get("active_layer"), "layers_bottom_to_top": _layer_list(c)}


@tool
def delete_layer(canvas: str, layer: str, keep_elements: bool = False):
    """Delete a layer. Its elements are deleted with it, unless keep_elements=true, which drops them
    into the bottom "base" layer instead."""
    st = store()
    c = st.get(canvas)
    affected = st.delete_layer(c, st.get_layer(c, layer), keep_elements)
    return {"deleted": layer, "elements_kept" if keep_elements else "elements_deleted": affected,
            "layers_bottom_to_top": _layer_list(c)}


@tool
def set_layer(canvas: str, layer: str, ids: list[str] | None = None, group: str | None = None):
    """Move existing elements (by ids, or a whole group) to another layer. layer="base" takes them out of
    all layers. Their order among themselves is kept."""
    st = store()
    c = st.get(canvas)
    elements = st.select(c, ids, group)
    name = None if layer.strip().lower() == "base" else st.get_layer(c, layer)["name"]
    st.assign_layer(c, elements, name)
    return {"layer": name or "base", "moved": [e["id"] for e in elements], "layers_bottom_to_top": _layer_list(c)}



@tool
def add_rect(canvas: str, x: float, y: float, width: float, height: float, radius: float | list[float] = 0,
             corner: str = "round", fill: str | dict | None = None, stroke: str | dict | None = None,
             style: str | dict | None = None, rotation: float = 0, skew: float = 0,
             origin: list[float] | None = None, id: str | None = None,
             group: str | None = None, clip: str | None = None, layer: str | None = None,
             smoothing: float = 0):
    """Add a rectangle (panels, buttons, bars, slots, dividers).

    x, y: top-left corner. radius: one number or [top-left, top-right, bottom-right, bottom-left].
    corner: "round" (default) or "cut" (chamfered corners, sci-fi / military look).
    smoothing: 0..1 corner smoothing (Figma-style "squircle"; 0.6 = iOS app-icon look) for round corners.
    fill / stroke: shortcuts for style.fill / style.stroke (see server instructions for the style object).
    skew: slant in degrees (top edge moves right) -> parallelogram tabs and banners, racing-style.
    rotation turns it clockwise around origin [x, y] (default: its centre).
    clip: id of another element whose shape masks this one (e.g. a bar fill clipped to its rounded track).
    Default look with no fill, stroke or style is solid white.
    """
    return _add(canvas, "rect", dict(x=x, y=y, width=width, height=height, radius=radius or None,
                                     corner=None if corner == "round" else corner, fill=fill, stroke=stroke,
                                     style=style, rotation=rotation or None, skew=skew or None, origin=origin,
                                     id=id, group=group, clip=clip, layer=layer, smoothing=smoothing or None))


@tool
def add_ellipse(canvas: str, cx: float, cy: float, rx: float, ry: float | None = None,
                fill: str | dict | None = None, stroke: str | dict | None = None,
                style: str | dict | None = None, rotation: float = 0, id: str | None = None,
                group: str | None = None, clip: str | None = None, layer: str | None = None):
    """Add a circle or ellipse centred at (cx, cy). Omit ry for a circle.
    Good for avatar frames, orbs, round buttons, radial glows (use a radial gradient fill)."""
    return _add(canvas, "ellipse", dict(cx=cx, cy=cy, rx=rx, ry=ry, fill=fill, stroke=stroke, style=style,
                                        rotation=rotation or None, id=id, group=group, clip=clip, layer=layer))


@tool
def add_line(canvas: str, points: list[list[float]], width: float = 2, color: str | dict | None = None,
             cap: str = "round", closed: bool = False, dash: list[float] | None = None,
             style: str | dict | None = None,
             id: str | None = None, group: str | None = None, clip: str | None = None, layer: str | None = None,
             start_cap: str | None = None, end_cap: str | None = None, cap_size: float | None = None,
             taper: str | None = None, width_profile: list[float] | None = None, wiggle: dict | float | None = None):
    """Add a line or polyline through points [[x, y], ...] (dividers, accents, brackets, ticks).

    width: thickness. cap: "round" or "butt". color may be a color or a gradient object.
    dash [on, off] cuts it into segments: with cap "butt" and a thick width that gives LED rows,
    shift lights and segmented bars (draw a dim full row first, then a shorter bright one on top).
    style can add shadow/glow/opacity; style.stroke does not apply to lines.
    start_cap / end_cap: line endings - "arrow", "triangle", "circle", "square", "diamond", "bar" (arrows,
      connectors, sliders, timelines); cap_size: their size as a multiple of the width (default 3).
      add_arc takes them too through update_element.
    taper: "start" | "end" | "both" (brush-like pointed ends); width_profile: width multipliers along the
      line, e.g. [0.3, 1, 1, 0.3]; wiggle: {"amount": 3, "frequency": 6, "seed": 1} for a hand-drawn,
      wobbly line (Figma variable-width and dynamic strokes).
    """
    return _add(canvas, "line", dict(points=points, width=width, cap=None if cap == "round" else cap,
                                     closed=closed or None, dash=dash, color=color, style=style, id=id,
                                     group=group, clip=clip, layer=layer, start_cap=start_cap, end_cap=end_cap,
                                     cap_size=cap_size, taper=taper, width_profile=width_profile, wiggle=wiggle))


@tool
def add_polygon(canvas: str, points: list[list[float]] | None = None, cx: float | None = None,
                cy: float | None = None, radius: float | None = None, sides: int = 6,
                inner_radius: float | None = None, point_rotation: float = 0, corner_radius: float = 0,
                fill: str | dict | None = None, stroke: str | dict | None = None,
                style: str | dict | None = None, rotation: float = 0, origin: list[float] | None = None,
                id: str | None = None, group: str | None = None, clip: str | None = None, layer: str | None = None):
    """Add a polygon. Either give explicit points [[x, y], ...], or a regular shape with
    cx, cy, radius, sides (3 = triangle, 6 = hexagon, ...). The first vertex points up;
    point_rotation turns it. inner_radius makes a star (sides = number of points).
    corner_radius rounds the corners. rotation + origin [x, y] spin it around a pivot
    (a gauge needle: thin polygon, origin at the hub)."""
    if not points and (cx is None or cy is None or radius is None):
        raise ValueError("Give either points, or cx + cy + radius (+ sides) for a regular polygon")
    return _add(canvas, "polygon", dict(points=points, cx=cx, cy=cy, radius=radius,
                                        sides=None if points else sides, inner_radius=inner_radius,
                                        point_rotation=point_rotation or None, corner_radius=corner_radius or None,
                                        fill=fill, stroke=stroke, style=style, rotation=rotation or None,
                                        origin=origin, id=id, group=group, clip=clip, layer=layer))


@tool
def add_path(canvas: str, d: str, x: float = 0, y: float = 0, scale: float = 1,
             fill: str | dict | None = None, stroke: str | dict | None = None,
             style: str | dict | None = None, rotation: float = 0, skew: float = 0,
             origin: list[float] | None = None, id: str | None = None,
             group: str | None = None, clip: str | None = None, layer: str | None = None):
    """Add a free-form shape from SVG path data (commands M L H V C S Q T A Z, absolute or relative).

    Use it for icons, emblems, banners, ribbons, angled HUD frames, curved bars. The path is scaled by
    `scale` and then moved by (x, y). Overlapping subpaths cut holes (even-odd); fill_rule "nonzero" (via
    update_element or batch) makes same-direction overlaps merge instead.
    Icons: design on a 24x24 grid and place with scale = size / 24. Line icons: fill "none" plus stroke
    {"color": ..., "width": 2, "align": "center", "join": "round"}; solid icons: one filled silhouette with
    holes for detail. Keep one stroke width and corner style across a whole icon set.
    """
    return _add(canvas, "path", dict(d=d, x=x or None, y=y or None, scale=None if scale == 1 else scale,
                                     fill=fill, stroke=stroke, style=style, rotation=rotation or None,
                                     skew=skew or None, origin=origin, id=id, group=group, clip=clip, layer=layer))


@tool
def add_arc(canvas: str, cx: float, cy: float, radius: float, start_angle: float, end_angle: float,
            thickness: float = 6, color: str | dict | None = None, cap: str = "butt",
            dash: list[float] | None = None, style: str | dict | None = None, id: str | None = None,
            group: str | None = None, clip: str | None = None, layer: str | None = None):
    """Add a circular arc (gauge tracks and fills, rev bands, circular progress, radar rings).

    radius is the centre line of the band, thickness its width. Angles in degrees, 0 = 3 o'clock,
    clockwise; a classic gauge sweeps from 135 to 405. end - start = 360 gives a full ring.
    cap: "butt" (flat ends) or "round". dash [on, off] splits it into segments (LED bands, segmented bars).
    color may be a conic gradient with the same from/to angles, e.g. a rev band going green -> red:
      {"type":"conic","from":135,"to":405,"stops":[[0,"#22c55e"],[0.7,"#facc15"],[1,"#ef4444"]]}
    For a value fill, draw the track first, then a second arc ending at start + (end - start) * value.
    """
    return _add(canvas, "arc", dict(cx=cx, cy=cy, radius=radius, start_angle=start_angle, end_angle=end_angle,
                                    thickness=thickness, color=color, cap=None if cap == "butt" else cap,
                                    dash=dash, style=style, id=id, group=group, clip=clip, layer=layer))


def _ticks(c: dict, args: dict) -> dict:
    """Create minor ticks, major ticks and labels for a dial. The caller owns the undo checkpoint."""
    st = store()
    a = {k: _maybe_json(v) for k, v in args.items() if v is not None}
    try:
        cx, cy, radius = float(a["cx"]), float(a["cy"]), float(a["radius"])
        start, end, count = float(a["start_angle"]), float(a["end_angle"]), int(a["count"])
    except KeyError as exc:
        raise ValueError(f"add_ticks is missing {exc}") from exc
    length, width = float(a.get("length", 8)), float(a.get("width", 2))
    major_every = int(a.get("major_every", 0) or 0)
    major_length = float(a.get("major_length", length * 1.8))
    major_width = float(a.get("major_width", width * 1.5))
    base = slugify(a["id"], "ticks") if a.get("id") else None
    if base is None:
        counters = c.setdefault("counters", {})
        counters["dial"] = counters.get("dial", 0) + 1
        base = f"dial{counters['dial']}"
    group = a.get("group") or base
    common = dict(cx=cx, cy=cy, radius=radius, start_angle=start, end_angle=end, count=count, group=group,
                  clip=a.get("clip"), cap=a.get("cap"), layer=a.get("layer"))
    created = []
    minor = dict(common, length=length, width=width, id=f"{base}_minor", color=a.get("color"), style=a.get("style"))
    if major_every > 1:
        minor["skip_every"] = major_every
    if major_every != 1:
        el, _ = st.add_element(c, "ticks", _prepare("ticks", minor), checkpoint=False)
        created.append(el["id"])
    if major_every >= 1:
        major = dict(common, length=major_length, width=major_width, every=major_every, id=f"{base}_major",
                     color=a.get("major_color", a.get("color")), style=a.get("style"))
        el, _ = st.add_element(c, "ticks", _prepare("ticks", major), checkpoint=False)
        created.append(el["id"])
    warnings: list[str] = []
    labels = a.get("labels")
    if labels:
        import math
        every = major_every if major_every >= 1 else 1
        full = abs(end - start) >= 360 - 1e-6
        positions = [i for i in range(count) if i % every == 0]
        if len(labels) != len(positions):
            raise ValueError(f"labels: got {len(labels)} but there are {len(positions)} "
                             f"{'major ' if major_every >= 1 else ''}ticks to label")
        size = float(a.get("label_size", 14))
        label_radius = float(a.get("label_radius", radius - (major_length if major_every >= 1 else length) - size * 0.95))
        step = (end - start) / (count if full else count - 1)
        for n, (i, text) in enumerate(zip(positions, labels)):
            ang = math.radians(start + step * i)
            label = dict(text=str(text), x=round(cx + label_radius * math.cos(ang), 2),
                         y=round(cy + label_radius * math.sin(ang), 2), anchor="center", size=size,
                         font=a.get("label_font"), weight=a.get("label_weight"), italic=a.get("label_italic"),
                         color=a.get("label_color", a.get("color")), id=f"{base}_label{n}", group=group,
                         layer=a.get("layer"))
            el, warn = st.add_element(c, "text", _prepare("text", label), checkpoint=False)
            warnings += warn
            created.append(el["id"])
    out: dict = {"group": group, "created": created}
    if warnings:
        out["warnings"] = sorted(set(warnings))
    return out


@tool
def add_ticks(canvas: str, cx: float, cy: float, radius: float, start_angle: float, end_angle: float, count: int,
              length: float = 8, width: float = 2, color: str | dict | None = None, major_every: int = 0,
              major_length: float | None = None, major_width: float | None = None,
              major_color: str | dict | None = None, labels: list[str] | None = None,
              label_radius: float | None = None, label_size: float = 14, label_font: str | None = None,
              label_weight: int | str | None = None, label_italic: bool | None = None,
              label_color: str | dict | None = None, style: str | dict | None = None,
              id: str | None = None, group: str | None = None, layer: str | None = None):
    """Add dial tick marks (speedometer, tachometer, compass, clock) in one call.

    `count` ticks are spread evenly from start_angle to end_angle (both ends included), each drawn from
    `radius` inwards by `length`. Angles: 0 = 3 o'clock, clockwise; gauges usually run 135 -> 405.
    major_every=N makes every Nth tick a major tick (longer / thicker / own color); 0 = all the same.
    labels: one string per major tick (or per tick when there are no majors), placed upright at
    label_radius (default: just inside the ticks). Example, a 0-8 x1000 rpm dial with 4 minor steps
    between numbers: count=33, major_every=4, labels=["0","1","2","3","4","5","6","7","8"].
    Creates elements "<id>_minor", "<id>_major", "<id>_label0..N" in one group, so move_elements(group=...)
    and delete_elements(group=...) treat the dial as one piece.
    """
    st = store()
    c = st.get(canvas)
    st.checkpoint(c)
    try:
        result = _ticks(c, dict(cx=cx, cy=cy, radius=radius, start_angle=start_angle, end_angle=end_angle, count=count,
                                length=length, width=width, color=color, major_every=major_every,
                                major_length=major_length, major_width=major_width, major_color=major_color,
                                labels=labels, label_radius=label_radius, label_size=label_size,
                                label_font=label_font, label_weight=label_weight, label_italic=label_italic,
                                label_color=label_color, style=style, id=id, group=group, layer=layer))
    except Exception:
        st.drop_checkpoint(c)
        st.save_canvas(c)
        raise
    st.save_canvas(c)
    return result


@tool
def add_text(canvas: str, text: str, x: float, y: float, size: float | None = None, font: str | None = None,
             weight: int | str | None = None, color: str | dict | None = None, anchor: str = "top-left",
             align: str | None = None, max_width: float | None = None, fit_width: float | None = None,
             line_height: float | None = None, letter_spacing: float | None = None,
             uppercase: bool | str | None = None, italic: bool | None = None, skew: float = 0,
             stroke: str | dict | None = None, style: str | dict | None = None, rotation: float = 0,
             origin: list[float] | None = None, arc: dict | None = None, id: str | None = None,
             group: str | None = None, clip: str | None = None, layer: str | None = None,
             lang: str | None = None, max_lines: int | None = None, decoration: str | None = None,
             case: str | None = None, note: str | None = None, features: list[str] | dict | None = None,
             axes: dict | None = None, paragraph_spacing: float | None = None, indent: float | None = None,
             list: str | None = None, trim: bool | None = None, path: dict | None = None):
    """Add text.

    (x, y) is where `anchor` sits: "top-left", "center" (centre of a button), "middle-left",
    "middle-right", "top-center", "bottom-right", "baseline-left", ... Vertical centring uses the
    capital-letter height, so "center" at a button's centre looks optically centred.
    size: font size in px (default 24). font: family name (see list_fonts; default Inter).
    weight: 100-900 or "regular"/"medium"/"semibold"/"bold"/"black".
    color: color or gradient. stroke: outline drawn behind the glyphs, e.g. {"color":"#000","width":3}.
    max_width: wrap lines at this width. fit_width: shrink the size until the text fits this width.
    max_lines (with max_width): cut longer text and end the last line with "..." (player names, item
      titles, chat previews; 1 = single line). decoration: "underline" or "strikethrough" (old prices).
    letter_spacing: extra px between letters. uppercase: true, or "tr" for Turkish i -> İ rules.
    case: "upper", "lower", "title", "tr-upper", "tr-lower", "small-caps", "all-small-caps" (non-destructive).
    features: OpenType features, e.g. ["tnum"] (equal-width digits for timers and scores), ["smcp"], ["ss01"],
      {"liga": 0}. axes: variable-font axes, e.g. {"wdth": 75, "slnt": -10, "opsz": 32} (fonts that have them).
    paragraph_spacing: extra px between paragraphs ("
"); indent: first-line indent; list: "bullet" | "number"
      (each paragraph becomes a list item with a hanging indent). trim: true makes the box hug the capital
      height and baseline (vertical trim), so centring in buttons and layouts is exact.
    path: run the text along any path - {"d": "M 20 120 C 80 20 200 20 260 120"} or {"points": [...]}, with
      optional "start" and "offset" (units). Colour emoji are drawn in colour.
    italic: use the family's italic (Barlow Condensed has one); other fonts are slanted automatically.
    skew: extra slant in degrees.
    arc: set text along a circle instead of a straight line (badges, emblems, round gauges):
      {"cx": 200, "cy": 200, "radius": 90, "angle": -90, "side": "outer"}. radius is where `anchor`'s
      vertical part sits (baseline by default; "top-center" puts the letter tops on it); angle (deg,
      0 = right, 90 = down) is where the horizontal anchor point lands (default -90 top / 90 bottom);
      side "outer" reads clockwise over the top, "inner" reads left-to-right along the bottom.
      Each letter is placed upright on the curve, not warped. x / y are ignored with arc.
    style may carry shadow / glow / opacity and text defaults (font, weight, size, letter_spacing).
    lang: language of this text ("ar", "he", "hi", "th", "ja", "zh-Hans", "zh-Hant", "ko", "tr"...);
      defaults to the render language, then the canvas language. Arabic, Hebrew, Indic, Thai and CJK
      are shaped with HarfBuzz (joined letters, right-to-left, conjuncts) and characters the font lacks
      come from bundled Noto / system fallback fonts. Always set it for Han text: the same character
      looks different in Japanese, Simplified and Traditional Chinese and Korean.
    The result's bbox_xywh tells you how much room the text really takes.
    """
    return _add(canvas, "text", dict(text=text, x=x, y=y, size=size, font=font, weight=weight, color=color,
                                     anchor=None if anchor == "top-left" else anchor, align=align,
                                     max_width=max_width, fit_width=fit_width, line_height=line_height,
                                     letter_spacing=letter_spacing, uppercase=uppercase or None,
                                     italic=italic or None, skew=skew or None, stroke=stroke, style=style,
                                     rotation=rotation or None, origin=origin, arc=arc, id=id, group=group,
                                     clip=clip, layer=layer, lang=lang, max_lines=max_lines,
                                     decoration=decoration, case=case, note=note, features=features, axes=axes,
                                     paragraph_spacing=paragraph_spacing, indent=indent, list=list, trim=trim,
                                     path=path))


@tool
def add_image(canvas: str, path: str, x: float, y: float, width: float | None = None, height: float | None = None,
              fit: str = "stretch", radius: float | list[float] = 0, tint: str | None = None,
              style: str | dict | None = None, rotation: float = 0, id: str | None = None,
              group: str | None = None, clip: str | None = None, layer: str | None = None,
              crop: list[float] | None = None, zoom: float | None = None, focus: list[float] | None = None,
              cutout: bool | dict | None = None, sheet: dict | None = None, frame: float | None = None):
    """Place an existing image file (PNG / JPG / WebP / GIF) from disk, e.g. a character portrait, a logo,
    a photo, or a PNG exported earlier. Give width and/or height (the missing one keeps the aspect ratio).
    fit: "stretch", "contain" or "cover". radius rounds the corners. tint recolors using the alpha
    (handy for white icons). style can add shadow / glow / light / adjust / mask like any shape.

    crop [x, y, w, h] in source pixels uses part of the file. cutout: true (or {"tolerance": 40}) removes a
    flat background colour around the subject. zoom (>= 1) and focus [fx, fy] (0..1 of the picture) pan and
    zoom inside the box (keyframe them for a Ken Burns move). Put a picture into any shape exactly: draw the
    shape and give it fill {"type": "image", "path": ..., "zoom", "focus"}, or clip the image to a shape.

    Animated pictures: an animated GIF / APNG / WebP, or a sprite sheet with sheet {"cols", "rows", "count"};
    frame picks the picture (keyframe "frame" from 0 to count over time to play it, it loops)."""
    return _add(canvas, "image", dict(path=str(Path(path).expanduser()), x=x, y=y, width=width, height=height,
                                      fit=None if fit == "stretch" else fit, radius=radius or None, tint=tint,
                                      style=style, rotation=rotation or None, id=id, group=group, clip=clip, layer=layer,
                                      crop=crop, zoom=zoom, focus=focus, cutout=cutout, sheet=sheet, frame=frame))


@tool
def add_instance(canvas: str, source: str, x: float, y: float, width: float | None = None,
                 height: float | None = None, fit: str = "stretch", animation: str | None = None,
                 time: float = 0, background: bool = True, tint: str | None = None,
                 style: str | dict | None = None, rotation: float = 0, origin: list[float] | None = None,
                 flip_x: bool = False, flip_y: bool = False, vars: dict | None = None, state: str | None = None,
                 colors: dict | None = None, id: str | None = None, group: str | None = None,
                 clip: str | None = None, layer: str | None = None, variant: dict | None = None,
                 hide: list[str] | None = None, show: list[str] | None = None, slots: dict | None = None):
    """Place another canvas inside this one as a live, re-rendered copy (a component instance).

    Component properties (Figma variants, boolean props, slots): variant {"size": "large", "state": "hover"}
    applies the source's states named "size=large" then "state=hover" (define them with set_state - a full
    variant matrix on one component); hide / show [element ids] toggle optional parts (icon, badge, close
    button); slots {"placeholder_id": "other_canvas"} swap a placeholder rect / ellipse in the source for
    an instance of another canvas, fitted inside it (an item icon in a slot frame, content in a card).

    Build a part once on its own canvas (a gem, a slot frame, a key cap, a medal) and stamp it many times:
    edit the source canvas and every instance follows. It is drawn as vectors at the size it is placed,
    so it stays sharp. width/height default to the source size; give one to keep the aspect ratio.
    fit: "stretch", "contain" or "cover". animation + time pose the source at that moment of one of its
    animations (e.g. several spinners at different phases). background: include the source canvas
    background. tint recolors using alpha. style adds shadow / glow / light / adjust / mask like an image.
    flip_x / flip_y mirror it (shadows and lighting stay the way the scene is lit).
    vars fill the source's {placeholders} for this copy only ({"label": "SETTINGS"} - one button
    component, many labels); colors override its colour tokens ({"accent": "#ef4444"}); state shows one
    of its interaction states ("hover", "disabled"...).
    """
    if fit not in ("stretch", "contain", "cover"):
        raise ValueError("fit must be 'stretch', 'contain' or 'cover'")
    st = store()
    st.get(source)
    return _add(canvas, "instance", dict(source=slugify(source), x=x, y=y, width=width, height=height,
                                         fit=None if fit == "stretch" else fit, animation=animation,
                                         time=time or None, background=None if background else False,
                                         tint=tint, style=style, rotation=rotation or None, origin=origin,
                                         flip_x=flip_x or None, flip_y=flip_y or None, vars=_maybe_json(vars),
                                         state=state, colors=_maybe_json(colors), id=id, group=group,
                                         clip=clip, layer=layer, variant=_maybe_json(variant),
                                         hide=_maybe_json(hide), show=_maybe_json(show), slots=_maybe_json(slots)))


def _svg_elements(c: dict, svg: str, x: float, y: float, width: float | None, height: float | None,
                  color: str, group: str | None, id_prefix: str | None, layer: str | None,
                  detail: float) -> dict:
    from . import svgimport
    text = str(svg).strip()
    if not text.startswith("<"):
        path = Path(text).expanduser()
        if not path.is_file():
            raise ValueError("svg must be SVG markup starting with '<' or the path of a .svg file")
        text = path.read_text(encoding="utf-8", errors="replace")
    elements, notes, size = svgimport.convert(text, float(x), float(y), width, height, color, float(detail))
    st = store()
    grp = group or slugify(id_prefix or "svg", "svg")
    prefix = slugify(id_prefix or grp, "svg")
    made = []
    taken = {e["id"] for e in c["elements"]}
    n = 0
    for props in elements:
        n += 1
        eid = f"{prefix}_{n}"
        while eid in taken:
            n += 1
            eid = f"{prefix}_{n}"
        taken.add(eid)
        props = dict(props, id=eid, group=grp)
        if layer:
            props["layer"] = layer
        el, _ = st.add_element(c, "path", props, checkpoint=False)
        made.append(el["id"])
    out: dict = {"group": grp, "ids": made, "placed_size": [_round(size[0]), _round(size[1])]}
    if notes:
        out["notes"] = notes
    return out


@tool
def add_svg(canvas: str, svg: str, x: float = 0, y: float = 0, width: float | None = None,
            height: float | None = None, color: str = "#ffffff", group: str | None = None,
            id_prefix: str | None = None, layer: str | None = None, detail: float = 1):
    """Import vector art from SVG markup (or a .svg file path) as editable path elements.

    Use it for a logo you were given, an icon from any open icon set, or a complex silhouette you wrote as
    SVG yourself. The art is fitted into width x height at (x, y), keeping its aspect ratio (give only one
    to scale by it; neither = 1 SVG unit per px). color replaces currentColor (most icon sets use it).
    Each shape becomes one `path` element in `group`, keeping its fill, stroke (width, join), opacity and
    linear/radial gradients; transforms are applied. Afterwards restyle freely with update_element (add
    light, bevel, gradients...). Unsupported parts (text, filters, masks, <use>, CSS classes) are listed
    in "notes". detail > 1 flattens curves more finely.
    """
    st = store()
    c = st.get(canvas)
    st.checkpoint(c)
    try:
        result = _svg_elements(c, svg, x, y, width, height, color, group, id_prefix, layer, detail)
    except Exception:
        st.drop_checkpoint(c)
        st.save_canvas(c)
        raise
    st.save_canvas(c)
    return result


@tool
def import_screenshot(path: str, canvas: str | None = None, max_width: int = 1280,
                      max_elements: int = 60, extract_theme: bool = True, ocr: str = "auto"):
    """Analyze a UI screenshot (PNG/JPG/WebP) with OpenCV and reconstruct an editable layered canvas.

    Extracts the canvas background, dominant K-means palette, hierarchical cards/buttons/pills/circles
    (with estimated corner radius, solid or linear gradient fill, and inner border strokes), and text
    regions (using rapidocr_onnxruntime or pytesseract when installed, else OpenCV morphological text
    line detection). The resulting canvas is 100% editable vector elements ready for restyling or export.

    path: path to the screenshot image file.
    canvas: name for the new canvas (defaults to the file stem).
    max_width: downscale oversized screenshots while keeping aspect ratio (default 1280).
    max_elements: cap on detected vector shapes to keep the canvas clean and fast (default 60).
    extract_theme: merge extracted palette colours into theme tokens (ss_bg, ss_c1..c5).
    ocr: "auto" (use local OCR if installed, else OpenCV heuristic) or "off" (shapes only).
    """
    from .screenshot import analyze_screenshot
    p = Path(path).expanduser()
    info = analyze_screenshot(p, max_width=int(max_width), max_elements=int(max_elements), ocr=str(ocr or "auto"))
    st = store()
    cid = slugify(canvas or p.stem, "screenshot")
    if cid in st.canvases:
        n = 2
        while f"{cid}_{n}" in st.canvases:
            n += 1
        cid = f"{cid}_{n}"
    c = st.create_canvas(cid, info["width"], info["height"], background=info["background"])
    st.checkpoint(c)
    created_shapes: list[str] = []
    created_texts: list[str] = []
    try:
        for spec in info["shapes"]:
            item = dict(spec)
            etype = item.pop("type")
            el, _ = st.add_element(c, etype, _prepare(etype, item), checkpoint=False)
            created_shapes.append(el["id"])
        for spec in info["texts"]:
            item = dict(spec)
            etype = item.pop("type")
            el, _ = st.add_element(c, etype, _prepare(etype, item), checkpoint=False)
            created_texts.append(el["id"])
    except Exception:
        st.drop_checkpoint(c)
        raise
    st.save_canvas(c)
    theme_tokens = {}
    if extract_theme and info["palette"]:
        theme_tokens = {"ss_bg": info["background"]}
        for i, hx in enumerate(info["palette"][1:], 1):
            theme_tokens[f"ss_c{i}"] = hx
        st.set_theme(theme_tokens, None, False)
    notes = []
    if info["ocr_engine"] == "opencv_heuristic":
        notes.append("No OCR backend installed (install rapidocr-onnxruntime or pytesseract for automatic text reading); "
                     "text boxes were placed with placeholder labels so you can inspect the screenshot and update_element them.")
    return {
        "canvas": c["id"],
        "width": info["width"],
        "height": info["height"],
        "background": info["background"],
        "palette": info["palette"],
        "theme_tokens": theme_tokens,
        "shapes_created": len(created_shapes),
        "texts_created": len(created_texts),
        "ocr_engine": info["ocr_engine"],
        "notes": notes,
    }



@tool
def update_element(canvas: str, id: str, props: dict):
    """Change properties of an element. `props` uses the same names as the add_* tools
    (x, y, width, radius, text, size, points, rotation, origin, skew, dash, group, clip, visible, arc,
    scale, scale_x, scale_y, flip_x, flip_y, fill_rule, ...).
    A "style" object is merged into the existing style key by key; set a key to null to remove it.
    Shortcuts "fill", "stroke" and "color" work here too. Example:
    {"width": 240, "style": {"glow": {"color": "$accent", "blur": 16}, "shadow": null}}"""
    st = store()
    c = st.get(canvas)
    el = st.find(c, id)
    warnings = st.update_element(c, el, _prepare_update(el, _maybe_json(props)))
    return _summary(st, c, el, warnings)


def _prepare_update(el: dict, props: dict) -> dict:
    if not isinstance(props, dict):
        raise ValueError("props must be an object")
    props = {k: _maybe_json(v) for k, v in props.items()}
    fill = props.pop("fill", None)
    stroke = props.pop("stroke", None)
    color = props.pop("color", None)
    if color is not None and fill is None:
        fill = color
    if fill is not None or stroke is not None:
        patch = props.get("style")
        if isinstance(patch, str):
            patch = {"use": patch}
        patch = dict(patch or {})
        if fill is not None:
            patch["fill"] = fill
        if stroke is not None:
            patch["stroke"] = stroke
        if isinstance(el.get("style"), str):
            patch = {"use": el["style"], **patch}
            el["style"] = {"use": el["style"]}
        props["style"] = patch
    return props


@tool
def delete_elements(canvas: str, ids: list[str] | None = None, group: str | None = None):
    """Delete elements by ids, or every element in a group."""
    st = store()
    c = st.get(canvas)
    return {"deleted": st.delete_elements(c, st.select(c, ids, group))}


@tool
def boolean_elements(canvas: str, ids: list[str], op: str = "union", id: str | None = None,
                     style: str | dict | None = None, keep_originals: bool = False):
    """Combine filled shapes into one exact vector shape (Figma / Penpot boolean groups).

    op: "union" (merge), "subtract" (cut every later shape out of the first), "intersect" (keep only the
    overlap) or "exclude" (keep what is covered an odd number of times). ids: rects, ellipses, polygons,
    paths or other booleans, first = the base shape. The result takes the first shape's style, layer and
    group unless `style` is given; its stroke, shadow and light follow the combined outline (unlike
    blend "erase", which only hides pixels). The children are kept inside the element, so the result stays
    editable: update_element(id, {"op": "intersect"}) switches the operation. keep_originals leaves the
    source shapes on the canvas too. Lines, arcs, ticks, text and images cannot be combined.
    """
    st = store()
    c = st.get(canvas)
    st.checkpoint(c)
    try:
        el, warnings = _boolean(c, ids, op, id, style, keep_originals)
    except Exception:
        st.drop_checkpoint(c)
        raise
    st.save_canvas(c)
    return _summary(st, c, el, warnings)


def _boolean(c: dict, ids, op: str, new_id: str | None, style, keep_originals: bool):
    """Replace shapes by one boolean element (no undo checkpoint: the caller owns it)."""
    from .render import BOOLEAN_OPS
    import copy
    st = store()
    ids = _maybe_json(ids)
    if not isinstance(ids, list) or len(ids) < 2:
        raise ValueError("ids must list at least 2 shapes, base shape first")
    op = str(op).lower()
    if op not in BOOLEAN_OPS:
        raise ValueError(f"op must be one of {', '.join(BOOLEAN_OPS)}")
    children = [st.find(c, str(i)) for i in ids]
    if len({ch["id"] for ch in children}) != len(children):
        raise ValueError("ids contains the same shape twice")
    first = children[0]
    positions = [c["elements"].index(ch) for ch in children]
    props = {"op": op, "children": [copy.deepcopy(ch) for ch in children], "id": new_id,
             "group": first.get("group"), "layer": first.get("layer"),
             "style": _maybe_json(style) if style is not None else first.get("style")}
    if not keep_originals:
        c["elements"] = [e for e in c["elements"] if e not in children]
    el, warnings = st.add_element(c, "boolean", props, checkpoint=False)
    c["elements"].remove(el)
    c["elements"].insert(min(positions) if not keep_originals else max(positions) + 1, el)
    return el, warnings


@tool
def duplicate_element(canvas: str, id: str, dx: float = 0, dy: float = 0, new_id: str | None = None,
                      props: dict | None = None, count: int = 1, rotate: float = 0,
                      pivot: list[float] | None = None):
    """Copy an element, offset by (dx, dy), optionally overriding properties (same format as
    update_element). Use it for repeated things: inventory slots, list rows, bar segments.

    count makes an array: copy i is moved by (dx*i, dy*i). rotate (degrees) turns copy i by rotate*i
    around pivot [x, y] - a radial array (gear teeth, sun rays, dial markers, a ring of slots):
    duplicate_element(id="tooth", count=11, rotate=30, pivot=[200, 200]). With count > 1 and new_id,
    ids are "<new_id>_1", "<new_id>_2", ...
    """
    st = store()
    c = st.get(canvas)
    src = st.find(c, id)
    patch = _prepare_update(dict(src), _maybe_json(props)) if props else None
    made = st.duplicate_element(c, src, dx, dy, new_id, patch, count=count, rotate=rotate, pivot=_maybe_json(pivot))
    if len(made) == 1:
        return _summary(st, c, made[0][0], made[0][1])
    warnings = sorted({w for _, ws in made for w in ws})
    out: dict = {"ids": [e["id"] for e, _ in made], "count": len(made)}
    if warnings:
        out["warnings"] = warnings
    return out


@tool
def move_elements(canvas: str, dx: float, dy: float, ids: list[str] | None = None, group: str | None = None):
    """Move elements (by ids, or a whole group) by (dx, dy)."""
    st = store()
    c = st.get(canvas)
    elements = st.select(c, ids, group)
    st.move_elements(c, elements, dx, dy)
    return {"moved": [_summary(st, c, e) for e in elements]}


@tool
def reorder_element(canvas: str, id: str, position: str):
    """Change draw order. position: "front" (top), "back" (bottom), "forward", "backward",
    "above:<other id>", "below:<other id>", or a zero-based index (0 = bottom)."""
    st = store()
    c = st.get(canvas)
    index = st.reorder(c, st.find(c, id), position)
    return {"id": id, "index": index, "order": [e["id"] for e in c["elements"]]}


@tool
def align_elements(canvas: str, ids: list[str], align: str | None = None, distribute: str | None = None,
                   relative_to: str = "canvas", gap: float | None = None):
    """Align and/or evenly space elements using their real bounding boxes.

    align: "left", "center-x", "right", "top", "center-y", "bottom", or "center" (both axes).
    relative_to: "canvas", "selection" (bounds of the ids), or the id of a reference element (not moved).
    distribute: "horizontal" or "vertical" - keeps the first and last in place and spaces the rest evenly,
    or uses a fixed `gap` between neighbours starting from the first.
    """
    st = store()
    c = st.get(canvas)
    elements = st.select(c, ids)
    r = st.renderer(c)
    boxes = {e["id"]: r.element_box(e) for e in elements}
    st.checkpoint(c)
    if align:
        if relative_to == "canvas":
            ref = (0.0, 0.0, float(c["width"]), float(c["height"]))
        elif relative_to == "selection":
            ref = (min(b[0] for b in boxes.values()), min(b[1] for b in boxes.values()),
                   max(b[2] for b in boxes.values()), max(b[3] for b in boxes.values()))
        else:
            ref = r.element_box(st.find(c, relative_to))
        modes = ["center-x", "center-y"] if align == "center" else [align]
        for mode in modes:
            for e in elements:
                if e["id"] == relative_to:
                    continue
                b = boxes[e["id"]]
                dx = dy = 0.0
                if mode == "left":
                    dx = ref[0] - b[0]
                elif mode == "right":
                    dx = ref[2] - b[2]
                elif mode == "center-x":
                    dx = (ref[0] + ref[2]) / 2 - (b[0] + b[2]) / 2
                elif mode == "top":
                    dy = ref[1] - b[1]
                elif mode == "bottom":
                    dy = ref[3] - b[3]
                elif mode == "center-y":
                    dy = (ref[1] + ref[3]) / 2 - (b[1] + b[3]) / 2
                else:
                    st.drop_checkpoint(c)
                    raise ValueError("align must be left, center-x, right, top, center-y, bottom or center")
                st.shift(e, dx, dy)
                boxes[e["id"]] = (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)
    if distribute:
        axis = 0 if distribute == "horizontal" else 1 if distribute == "vertical" else None
        if axis is None:
            st.drop_checkpoint(c)
            raise ValueError("distribute must be 'horizontal' or 'vertical'")
        ordered = sorted(elements, key=lambda e: boxes[e["id"]][axis])
        if len(ordered) >= 2:
            sizes = [boxes[e["id"]][axis + 2] - boxes[e["id"]][axis] for e in ordered]
            start = boxes[ordered[0]["id"]][axis]
            if gap is None:
                end = boxes[ordered[-1]["id"]][axis + 2]
                gap_value = (end - start - sum(sizes)) / (len(ordered) - 1)
            else:
                gap_value = float(gap)
            pos = start
            for e, size in zip(ordered, sizes):
                delta = pos - boxes[e["id"]][axis]
                st.shift(e, delta if axis == 0 else 0.0, delta if axis == 1 else 0.0)
                pos += size + gap_value
    st.save_canvas(c)
    return {"elements": [_summary(st, c, e) for e in elements]}


_BATCH_ADD = {"add_rect": "rect", "add_ellipse": "ellipse", "add_line": "line", "add_polygon": "polygon",
              "add_arc": "arc", "add_path": "path", "add_text": "text", "add_image": "image",
              "add_input": "input", "add_scroll": "scroll"}


@tool
def add_input(canvas: str, x: float, y: float, width: float = 240, height: float = 42,
              placeholder: str = "", value: str = "", input_type: str = "text", label: str | None = None,
              bind: str | None = None, radius: float = 8, corner: str = "round", font: str = "Inter",
              size: float = 15, weight: int | str = 400, text_color: str = "#f8fafc",
              placeholder_color: str = "#94a3b8", padding: float = 12, max_length: int | None = None,
              readonly: bool = False, focused: bool = False, style: str | dict | None = None,
              fill: str | dict | None = None, stroke: str | dict | None = None,
              id: str | None = None, group: str | None = None, clip: str | None = None,
              layer: str | None = None, rotation: float = 0, origin: list[float] | None = None):
    """Add a first-class interactive text Input field.

    Renders realistically on the canvas (with optional label, placeholder, password dots and focus caret)
    AND exports as a genuine native input control across platforms:
      - Web / React: live <input> bound to `bind` / onChange
      - Godot 4: LineEdit (+ text_changed hook in controller)
      - Unity UI Toolkit: <ui:TextField> (+ RegisterValueChangedCallback)
      - Unity uGUI: InputField with Placeholder & Text children
      - Roblox: TextBox with UICorner + UIStroke
      - .NET (WPF / Avalonia / WinUI) & C++ (Qt QML / Dear ImGui): TextBox/PasswordBox, TextField, InputText
    input_type: "text" | "password" | "number" | "email" | "search".
    bind: optional data key in set_binding(data={...}) for automatic two-way sync.
    """
    itype = str(input_type or "text").lower()
    if itype not in ("text", "password", "number", "email", "search"):
        raise ValueError("input_type must be text, password, number, email or search")
    return _add(canvas, "input", dict(
        x=float(x), y=float(y), width=float(width), height=float(height),
        placeholder=str(placeholder), value=str(value), input_type=itype, label=label,
        bind=bind, radius=radius, corner=corner, font=font, size=float(size), weight=weight,
        text_color=text_color, placeholder_color=placeholder_color, padding=float(padding),
        max_length=max_length, readonly=bool(readonly) or None, focused=bool(focused) or None,
        style=_merge_style(style, fill, stroke), id=id, group=group, clip=clip, layer=layer,
        rotation=rotation or None, origin=origin,
    ))


@tool
def add_scroll(canvas: str, x: float, y: float, width: float = 280, height: float = 220,
               items: list | None = None, direction: str = "vertical", radius: float = 10,
               corner: str = "round", padding: float = 10, gap: float = 8, item_height: float = 38,
               item_width: float = 120, content_height: float | None = None,
               content_width: float | None = None, scroll_offset: float = 0.0,
               show_scrollbar: bool = True, scrollbar_color: str = "#94a3b8@0.58",
               scrollbar_track: str = "#0f172a@0.5", scrollbar_width: float = 6,
               item_fill: str = "#1e293b@0.75", item_color: str = "#e2e8f0",
               subtitle_color: str = "#94a3b8", font: str = "Inter", size: float = 13,
               style: str | dict | None = None, fill: str | dict | None = None,
               stroke: str | dict | None = None, id: str | None = None, group: str | None = None,
               clip: str | None = None, layer: str | None = None, rotation: float = 0,
               origin: list[float] | None = None):
    """Add a first-class native Scroll container / scrollable list.

    Renders a clipped viewport with scrollable item rows and a proportional scrollbar on canvas, AND
    exports as a real native scrollable widget across platforms:
      - Web / React: overflow-y/x: auto container with styled rows
      - Godot 4: ScrollContainer + VBoxContainer/HBoxContainer
      - Unity UI Toolkit: <ui:ScrollView>
      - Unity uGUI: ScrollRect + Mask + VerticalLayoutGroup + ContentSizeFitter
      - Roblox: ScrollingFrame + UIListLayout
      - .NET (WPF / Avalonia / WinUI) & C++ (Qt QML / Dear ImGui): ScrollViewer, ScrollView, BeginChild
    items: list of strings or objects [{"title": "Iron Sword", "subtitle": "ATK +42", "badge": "x1"}, ...].
    direction: "vertical" | "horizontal" | "both". scroll_offset: 0..1 preview scroll position.
    """
    d = str(direction or "vertical").lower()
    if d not in ("vertical", "horizontal", "both"):
        raise ValueError("direction must be vertical, horizontal or both")
    return _add(canvas, "scroll", dict(
        x=float(x), y=float(y), width=float(width), height=float(height),
        items=_maybe_json(items) or [], direction=d, radius=radius, corner=corner,
        padding=float(padding), gap=float(gap), item_height=float(item_height),
        item_width=float(item_width), content_height=content_height, content_width=content_width,
        scroll_offset=float(scroll_offset), show_scrollbar=bool(show_scrollbar),
        scrollbar_color=scrollbar_color, scrollbar_track=scrollbar_track,
        scrollbar_width=float(scrollbar_width), item_fill=item_fill, item_color=item_color,
        subtitle_color=subtitle_color, font=font, size=float(size),
        style=_merge_style(style, fill, stroke), id=id, group=group, clip=clip, layer=layer,
        rotation=rotation or None, origin=origin,
    ))


def _add_frame_elements(st: Store, c: dict, args: dict) -> dict:
    from . import profiles
    from .frames import frame_operations
    prof = profiles.resolve_profile(st.theme, c)
    q = profiles.normalize_quality(args.get("quality")) or prof["quality"]
    preset = str(args.get("preset", "auto") or "auto").lower().strip()
    if preset == "auto":
        preset = prof.get("frame_preset", "rpg_gold")
    specs, inner = frame_operations(
        args["x"], args["y"], args["width"], args["height"],
        preset=preset, ornament=args.get("ornament", "auto"),
        material=args.get("material"), accent=args.get("accent"), title=args.get("title"),
        group=args.get("group"), id_prefix=args.get("id_prefix"), layer=args.get("layer"),
        quality=q,
    )
    ids = []
    warnings: list[str] = []
    for raw in specs:
        item = dict(raw)
        etype = item.pop("type")
        el, w = st.add_element(c, etype, _prepare(etype, item), checkpoint=False)
        ids.append(el["id"])
        warnings.extend(w)
    out: dict = {"preset": preset, "quality": q, "group": specs[0].get("group"),
                 "ids": ids, "inner_box": inner}
    if warnings:
        out["warnings"] = sorted(set(warnings))
    return out


@tool
def add_frame(canvas: str, x: float, y: float, width: float, height: float, preset: str = "rpg_gold",
              ornament: str = "auto", material: str | None = None, accent: str | None = None,
              title: str | None = None, group: str | None = None, id_prefix: str | None = None,
              layer: str | None = None, quality: str | None = None):
    """Build a multi-layered panel/border frame from editable vector shapes and PBR materials in one call.

    preset: "auto" (follows active style_preset), "rpg_gold" (double-stepped gold molding + cubic-Bezier
      corner filigree + winged ruby crest), "royal_ornate" (bronze + hammered gold molding + woven royal
      fabric bed + sapphire gems + perimeter beads), "fantasy_parchment" (aged parchment scroll + wood
      rollers + bronze end-caps + wax seal), "scifi_hud" (cut-corner glass + glowing corner brackets +
      telemetry ticks + LEDs), "cyber_tech" (carbon twill chassis + dual neon rails + warning chevrons +
      bolts), "glass_card" (squircle liquid glass), "medieval_iron" (forged iron + stone bed + corner
      hinge clasps + perimeter rivets), "luxury_minimal" (chrome bezel + dark satin inlay), "cartoon_thick"
      (glossy outlined badge).
    ornament: "auto" | "none" | "rivets" | "brackets" | "filigree" | "notches".
    quality: optional override ("simple" | "standard" | "advanced" | "aaa"); "simple" removes heavy ornaments.
    material / accent: optional override for the main PBR material name or highlight colour.
    title: optional header label placed cleanly at the top of the frame.
    Returns {preset, quality, group, ids, inner_box: [ix, iy, iw, ih]} where inner_box is the safe area.
    """
    st = store()
    c = st.get(canvas)
    st.checkpoint(c)
    try:
        res = _add_frame_elements(st, c, {"x": x, "y": y, "width": width, "height": height, "preset": preset,
                                          "ornament": ornament, "material": material, "accent": accent, "title": title,
                                          "group": group, "id_prefix": id_prefix, "layer": layer, "quality": quality})
    except Exception:
        st.drop_checkpoint(c)
        raise
    st.save_canvas(c)
    return {"canvas": c["id"], **res}


@tool
def batch(canvas: str, operations: list[dict]):
    """Run many drawing, layout, state, binding and interaction operations in one atomic call.

    Each operation is {"op": "<tool name>", ...the same arguments that tool takes, without canvas}.
    Supported ops: add_rect, add_ellipse, add_line, add_polygon, add_path, add_arc, add_ticks, add_text,
    add_image, add_instance, add_svg, add_frame, add_input, add_scroll, create_layer, update_layer, delete_layer, set_layer,
    create_animation, set_keyframes, update_element, delete_elements, move_elements, reorder_element,
    duplicate_element, boolean_elements (use "operation" key), align_elements, arrange_elements, set_pin,
    set_state, set_binding, set_interaction, set_link.
    Add ops accept any extra element property directly (flip_x, scale, skew, fill_rule, visible...).
    Give elements explicit "id"s so later ops (clip, pin, state, binding, interaction) can refer to them.
    Atomic: if any op fails nothing is changed, and the error names the failing op index.
    """
    st = store()
    c = st.get(canvas)
    operations = _maybe_json(operations)
    if not isinstance(operations, list) or not operations:
        raise ValueError("operations must be a non-empty list")
    st.checkpoint(c)
    results = []
    try:
        for index, raw in enumerate(operations):
            op_args = dict(_maybe_json(raw))
            op = op_args.pop("op", None)
            op_args.pop("canvas", None)
            try:
                if op in _BATCH_ADD:
                    etype = _BATCH_ADD[op]
                    if etype == "image" and op_args.get("path"):
                        op_args["path"] = str(Path(op_args["path"]).expanduser())
                    el, warnings = st.add_element(c, etype, _prepare(etype, op_args), checkpoint=False)
                    results.append(_summary(st, c, el, warnings))
                elif op == "add_ticks":
                    results.append(_ticks(c, op_args))
                elif op == "add_frame":
                    results.append(_add_frame_elements(st, c, op_args))
                elif op == "create_layer":
                    layer = st.create_layer(c, op_args["name"], _layer_settings(
                        op_args.get("opacity"), op_args.get("blend"), op_args.get("clip"), op_args.get("visible"),
                        op_args.get("style")), op_args.get("position"), checkpoint=False)
                    results.append({"layer": layer["name"], "active": True})
                elif op == "update_layer":
                    target = st.get_layer(c, op_args["layer"])
                    changes = _layer_settings(op_args.get("opacity"), op_args.get("blend"), op_args.get("clip"),
                                              op_args.get("visible"), op_args.get("style"))
                    if op_args.get("name"):
                        changes["name"] = op_args["name"]
                    updated = st.update_layer(c, target, changes, op_args.get("position"), op_args.get("activate"),
                                              checkpoint=False)
                    results.append({"layer": updated["name"]})
                elif op == "delete_layer":
                    target = st.get_layer(c, op_args["layer"])
                    st.delete_layer(c, target, bool(op_args.get("delete_elements", False)), checkpoint=False)
                    results.append({"deleted_layer": target["name"]})
                elif op == "set_layer":
                    targets = st.select(c, op_args.get("ids"), op_args.get("group"))
                    name = None if str(op_args["layer"]).strip().lower() == "base" else st.get_layer(c, op_args["layer"])["name"]
                    for el in targets:
                        if name:
                            el["layer"] = name
                        else:
                            el.pop("layer", None)
                    results.append({"layer": name or "base", "moved": [e["id"] for e in targets]})
                elif op == "create_animation":
                    key, anim, _ = st.create_animation(c, op_args["name"], op_args["duration"],
                                                       op_args.get("loop", False), op_args.get("fps", 30))
                    st._undo[c["id"]].pop()
                    results.append({"animation": key, "duration": anim["duration"], "loop": anim["loop"]})
                elif op == "set_keyframes":
                    results.append(_set_keyframes(c, op_args, checkpoint=False))
                elif op == "update_element":
                    el = st.find(c, op_args["id"])
                    warnings = st.update_element(c, el, _prepare_update(el, op_args.get("props", {})), checkpoint=False)
                    results.append(_summary(st, c, el, warnings))
                elif op == "delete_elements":
                    targets = st.select(c, op_args.get("ids"), op_args.get("group"))
                    results.append({"deleted": st.delete_elements(c, targets, checkpoint=False)})
                elif op == "move_elements":
                    targets = st.select(c, op_args.get("ids"), op_args.get("group"))
                    st.move_elements(c, targets, op_args.get("dx", 0), op_args.get("dy", 0), checkpoint=False)
                    results.append({"moved": [e["id"] for e in targets]})
                elif op == "reorder_element":
                    st.reorder(c, st.find(c, op_args["id"]), op_args["position"], checkpoint=False)
                    results.append({"reordered": op_args["id"]})
                elif op == "duplicate_element":
                    src = st.find(c, op_args["id"])
                    patch = _prepare_update(dict(src), op_args["props"]) if op_args.get("props") else None
                    made = st.duplicate_element(c, src, float(op_args.get("dx", 0)), float(op_args.get("dy", 0)),
                                                op_args.get("new_id"), patch, count=op_args.get("count", 1),
                                                rotate=op_args.get("rotate", 0), pivot=op_args.get("pivot"),
                                                checkpoint=False)
                    if len(made) == 1:
                        results.append(_summary(st, c, made[0][0], made[0][1]))
                    else:
                        results.append({"ids": [e["id"] for e, _ in made]})
                elif op == "add_instance":
                    st.get(op_args["source"])
                    op_args["source"] = slugify(op_args["source"])
                    el, warnings = st.add_element(c, "instance", _prepare("instance", op_args), checkpoint=False)
                    results.append(_summary(st, c, el, warnings))
                elif op == "boolean_elements":
                    el, warnings = _boolean(c, op_args["ids"], op_args.get("operation", "union"),
                                            op_args.get("id"), op_args.get("style"), op_args.get("keep_originals", False))
                    results.append(_summary(st, c, el, warnings))
                elif op == "add_svg":
                    results.append(_svg_elements(c, op_args["svg"], op_args.get("x", 0), op_args.get("y", 0),
                                                 op_args.get("width"), op_args.get("height"),
                                                 op_args.get("color", "#ffffff"), op_args.get("group"),
                                                 op_args.get("id_prefix"), op_args.get("layer"),
                                                 op_args.get("detail", 1)))
                elif op == "align_elements":
                    results.append(align_elements(c["id"], **op_args))
                elif op == "arrange_elements":
                    results.append(arrange_elements(c["id"], **op_args))
                elif op == "set_pin":
                    results.append(set_pin(c["id"], **op_args))
                elif op == "set_state":
                    results.append(set_state(c["id"], **op_args))
                elif op == "set_binding":
                    results.append(set_binding(c["id"], **op_args))
                elif op == "set_interaction":
                    results.append(set_interaction(c["id"], **op_args))
                elif op == "set_link":
                    results.append(set_link(c["id"], **op_args))
                else:
                    raise ValueError(f"unknown op '{op}'")
            except KeyError as exc:
                raise ValueError(f"operation {index} ({op}): missing argument {exc}") from exc
            except (ValueError, TypeError) as exc:
                raise ValueError(f"operation {index} ({op}): {exc}") from exc
    except Exception:
        st.drop_checkpoint(c)
        st.save_canvas(c)
        raise
    st.save_canvas(c)
    return {"canvas": c["id"], "results": results, "element_count": len(c["elements"])}


@tool
def undo(canvas: str):
    """Undo the last change on a canvas (up to 40 steps; a whole batch counts as one step)."""
    st = store()
    c = st.get(canvas)
    if not st.undo(c):
        return {"undone": False, "reason": "nothing to undo"}
    return {"undone": True, "elements": [e["id"] for e in c["elements"]]}


@tool
def canvas_version(canvas: str, action: str = "list", name: str | None = None, note: str | None = None):
    """Named version history for a canvas (like Figma's version history), beyond the 40-step undo.

    action "save": snapshot the canvas now as `name` (default v1, v2...) with an optional note - do it
      before a risky redesign or to keep alternatives ("rounded", "sharp") to compare later.
    "list": saved versions with time, note and element count. "restore": put the canvas back to that
      version (undo returns to what was there before). "delete": remove a saved version.
    "diff": what changed between that version and now - added, removed and changed elements (with the
      changed property names), like Figma's compare changes.
    Versions are stored next to the canvas file and survive restarts (at most 30 per canvas).
    """
    st = store()
    c = st.get(canvas)
    act = str(action).lower()
    if act == "save":
        entry = st.save_version(c, name, note)
        return {"saved": entry["name"], "versions": [v["name"] for v in st.list_versions(c)]}
    if act == "list":
        return {"canvas": c["id"], "versions": st.list_versions(c)}
    if act == "diff":
        if not name:
            raise ValueError("diff needs the version name (see action='list')")
        versions = st._versions(c["id"])
        key = slugify(name, "version")
        if key not in versions:
            raise ValueError(f"no version '{key}'. Versions: {', '.join(versions) or '(none)'}")
        old = {e["id"]: e for e in versions[key]["canvas"]["elements"]}
        new = {e["id"]: e for e in c["elements"]}
        changed = {i: sorted(k for k in set(old[i]) | set(new[i]) if old[i].get(k) != new[i].get(k))
                   for i in old.keys() & new.keys() if old[i] != new[i]}
        canvas_keys = sorted(k for k in set(versions[key]["canvas"]) | set(c)
                             if k not in ("elements",) and versions[key]["canvas"].get(k) != c.get(k))
        return {"version": key, "added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
                "changed": changed, "canvas_changed": canvas_keys}
    if act in ("restore", "delete"):
        if not name:
            raise ValueError(f"{act} needs the version name (see action='list')")
        if act == "restore":
            st.restore_version(c, name)
            return {"restored": slugify(name, "version"), "elements": [e["id"] for e in c["elements"]]}
        st.delete_version(c, name)
        return {"deleted": slugify(name, "version"), "versions": [v["name"] for v in st.list_versions(c)]}
    raise ValueError("action must be 'save', 'list', 'diff', 'restore' or 'delete'")



def _set_keyframes(c: dict, args: dict, checkpoint: bool = True) -> dict:
    st = store()
    try:
        name, target, prop = args["animation"], str(args["target"]), str(args["property"])
        raw = _maybe_json(args["keyframes"])
    except KeyError as exc:
        raise ValueError(f"set_keyframes is missing {exc}") from exc
    key, anim = st.get_animation(c, name)
    keys = anim_mod.normalize_keyframes(raw, anim["duration"], float(args.get("offset", 0) or 0))
    elements, warnings = st.set_track(c, anim, target, prop, keys, _maybe_json(args.get("pivot")), checkpoint,
                                      _maybe_json(args.get("path")))
    out: dict = {"animation": key, "target": target, "property": prop, "elements": [e["id"] for e in elements],
                 "keyframes": [{"t": k["t"], "value": k["value"], **({"ease": anim_mod.ease_name(k["ease"])}
                                                                      if "ease" in k else {})} for k in keys]}
    if warnings:
        out["warnings"] = warnings
    return out


@tool
def create_animation(canvas: str, name: str, duration: float, loop: bool = False, fps: float = 30):
    """Create an animation on a canvas (or change the duration / loop / fps of an existing one; its
    keyframes are kept). A canvas can hold several: "hover", "press", "appear", "idle", ...

    duration in seconds. UI feedback is short: hover/press 0.1-0.2 s, panel appear 0.25-0.4 s;
    idle loops (pulsing glow, breathing) 1.5-3 s with loop=true. fps is the default sampling rate for
    previews and frame exports. The animation is empty until you add tracks with set_keyframes.
    """
    st = store()
    c = st.get(canvas)
    key, anim, created = st.create_animation(c, name, duration, loop, fps)
    return {"animation": key, "created": created, "duration": anim["duration"], "loop": anim["loop"],
            "fps": anim["fps"], "tracks": len(anim["tracks"])}


@tool
def set_keyframes(canvas: str, animation: str, target: str, property: str, keyframes: list,
                  pivot: list[float] | None = None, offset: float = 0, stagger: float = 0,
                  path: dict | None = None):
    """Animate one property of an element (or of a whole group) with keyframes. Calling it again for
    the same target + property replaces that track.

    target: an element id, or "group:<name>" for every element in a group.
    property: what changes over time -
      helpers:  "dx", "dy" (offset from the drawn position), "scale", "scale_x", "scale_y" (1 = normal size,
                grows around the pivot, effects included), "opacity" (0-1)
      any numeric element property: "x", "y", "width", "height", "radius", "rotation", "skew", "size",
                "thickness", "start_angle", "end_angle", "dash_offset", "letter_spacing", "cx", "rx", ...
      any style value by path: "style.glow.blur", "style.glow.strength", "style.shadow.dy", "style.blur",
                "style.stroke.width", "style.bevel.size"
      colors and gradients: "style.fill", "style.glow.color", "style.stroke.color" (gradients blend when
                both keyframes have the same stops layout)
      switches: "visible", "text" (these jump at the keyframe instead of blending)
      "motion": travel along a path - values are progress 0..1, path {"d": "M 0 0 C 80 -120 220 -120 300 0",
                "rotate": true} (relative to where the element is drawn; rotate turns it with the path):
                coins flying to the HUD, orbiting icons, a cursor tracing a route.
    keyframes: [{"t": seconds, "value": v, "ease": "..."}] or [[t, v], [t, v, ease]]. A keyframe's ease
      shapes the motion arriving at it. Eases: "linear", "step", "ease-in" / "ease-out" / "ease-in-out",
      or style + direction such as "quad-out", "cubic-in-out", "back-out" (overshoot), "elastic-out",
      "bounce-out", "expo-out", "sine-in-out"; or a cubic-bezier [x1, y1, x2, y2].
      Before the first keyframe the property holds the first value; after the last, the last value.
    pivot [x, y]: centre for rotation / scale during this animation (e.g. the hub of a gauge needle, or
      one shared point so a group scales as one piece). Default: each element's own centre or origin.
    offset: seconds added to every keyframe time.
    stagger: with a "group:<name>" target, element i of the group starts i * stagger seconds later
      (menu rows sliding in one after another, a list of rewards popping in sequence). Each element gets
      its own track.

    Example - a button pops in: property "scale", keyframes [[0, 0.6], [0.22, 1, "back-out"]], plus
    property "opacity", keyframes [[0, 0], [0.12, 1, "quad-out"]].
    """
    c = store().get(canvas)
    if stagger and str(target).startswith("group:"):
        st = store()
        members = st.select(c, None, str(target)[6:])
        st.checkpoint(c)
        results = []
        try:
            st.delete_tracks(c, st.get_animation(c, animation)[1], target, property)
            for i, el in enumerate(members):
                results.append(_set_keyframes(c, dict(animation=animation, target=el["id"], property=property,
                                                      keyframes=keyframes, pivot=pivot, path=path,
                                                      offset=float(offset) + i * float(stagger)), checkpoint=False))
        except Exception:
            st.drop_checkpoint(c)
            st.save_canvas(c)
            raise
        st.save_canvas(c)
        return {"animation": results[0]["animation"], "property": property, "staggered": [r["target"] for r in results],
                "stagger": float(stagger)}
    return _set_keyframes(c, dict(animation=animation, target=target, property=property,
                                  keyframes=keyframes, pivot=pivot, offset=offset, path=path))


@tool
def delete_keyframes(canvas: str, animation: str, target: str | None = None, property: str | None = None):
    """Remove tracks from an animation: one target + property, everything for a target, or (with
    neither) every track."""
    st = store()
    c = st.get(canvas)
    key, anim = st.get_animation(c, animation)
    removed = st.delete_tracks(c, anim, target, property)
    return {"animation": key, "removed_tracks": removed, "tracks_left": len(anim["tracks"])}


@tool
def get_animations(canvas: str, name: str | None = None):
    """List the animations on a canvas, or show one in full (tracks, keyframes, eases)."""
    st = store()
    c = st.get(canvas)
    if name:
        key, anim = st.get_animation(c, name)
        return anim_mod.describe(key, anim, c)
    return {"canvas": c["id"], "animations": [
        {"animation": key, "duration": a["duration"], "loop": a["loop"], "fps": a.get("fps", 30),
         "tracks": [f"{t['target']} -> {t['property']} ({len(t['keyframes'])} keys)" for t in a["tracks"]]}
        for key, a in st.animations(c).items()]}


@tool
def delete_animation(canvas: str, name: str):
    """Delete an animation from a canvas. The elements themselves are not changed."""
    st = store()
    c = st.get(canvas)
    key, _ = st.get_animation(c, name)
    st.delete_animation(c, key)
    return {"deleted": key, "animations_left": sorted(st.animations(c))}


def _static_plan(c: dict, anim: dict, scale: float, include_background: bool, only: set[str] | None):
    """Pre-render static element runs once for animations without styled/clipped layers, so multi-frame
    exports skip re-compositing untouched cards, panels and materials on every frame."""
    if c.get("layers") or c.get("pixel_art"):
        return None
    st = store()
    moving: set[str] = set()
    for tr in anim.get("tracks", []):
        for el in anim_mod.track_targets(c, tr["target"]):
            moving.add(el["id"])
    elements = [e for e in c["elements"] if e.get("visible", True) and (only is None or e["id"] in only)]
    for e in elements:
        es = resolve_style(e.get("style"), st.theme)
        if es.get("backdrop_blur") or es.get("glass") or str(es.get("blend", "normal")).lower() == "erase":
            return None
        if e.get("clip") and e["clip"] in moving:
            moving.add(e["id"])
    if not any(e["id"] not in moving for e in elements):
        return None
    base_r = st.renderer(c, scale)
    segments: list[tuple[str, Any]] = []
    run: list[str] = []
    first = True
    for e in elements:
        if e["id"] in moving:
            if run or (first and include_background):
                img = base_r.render(include_background=first and include_background, only=set(run))
                segments.append(("img", img))
                run = []
                first = False
            segments.append(("dyn", e["id"]))
        else:
            run.append(e["id"])
    if run or (first and include_background):
        img = base_r.render(include_background=first and include_background, only=set(run))
        segments.append(("img", img))
    return segments, base_r.width, base_r.height, base_r.warnings


def _pose(c: dict, anim: dict, t: float, scale: float, include_background: bool = True,
          only: set[str] | None = None, plan=None) -> tuple[PILImage.Image, list[str]]:
    st = store()
    frame, warnings = anim_mod.apply_animation(c, anim, t, st.theme.get("colors", {}))
    r = st.renderer(frame, scale)
    if plan is not None:
        segments, w, h, base_warn = plan
        out = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
        by_id = {e["id"]: e for e in frame["elements"]}
        for kind, val in segments:
            if kind == "img":
                out = PILImage.alpha_composite(out, val)
            else:
                el = by_id.get(val)
                if el is not None and el.get("visible", True):
                    res = r.render_element(el)
                    if res is not None:
                        layer, ox, oy, blend = res
                        _composite(out, layer, ox, oy, blend)
        return out, warnings + base_warn + r.warnings
    return r.render(include_background=include_background, only=only), warnings + r.warnings


def _blurred_pose(c: dict, anim: dict, t: float, scale: float, include_background: bool, only, samples: int,
                  frame_dt: float, plan=None):
    """Motion blur: the average of `samples` poses over half a frame (a 180-degree shutter), premultiplied."""
    import numpy as np
    acc, warns = None, []
    for i in range(samples):
        sub = min(float(anim["duration"]), t + frame_dt * 0.5 * (i / max(1, samples - 1) - 0.5))
        img, w = _pose(c, anim, max(0.0, sub), scale, include_background, only, plan=plan)
        warns += w
        arr = np.asarray(img.convert("RGBa"), dtype=np.float32)
        acc = arr if acc is None else acc + arr
    out = PILImage.fromarray((acc / np.float32(samples) + np.float32(0.5)).astype(np.uint8), "RGBa").convert("RGBA")
    return out, warns


def _poses(c: dict, anim: dict, times: list[float], scale: float, include_background: bool = True,
           only: set[str] | None = None, motion_blur: int = 0, fps: float = 30) -> tuple[list[PILImage.Image], list[str]]:
    """Render many animation frames at once: static runs are baked once, and threads render dynamic frames."""
    import os
    from concurrent.futures import ThreadPoolExecutor
    workers = max(1, min(len(times), os.cpu_count() or 1, 8))
    samples = max(0, min(16, int(motion_blur or 0)))
    plan = _static_plan(c, anim, scale, include_background, only) if len(times) > 1 else None

    def one(t):
        if samples > 1:
            return _blurred_pose(c, anim, t, scale, include_background, only, samples, 1.0 / fps, plan=plan)
        return _pose(c, anim, t, scale, include_background, only, plan=plan)

    if workers == 1:
        done = [one(t) for t in times]
    else:
        with ThreadPoolExecutor(workers) as pool:
            done = list(pool.map(one, times))
    return [img for img, _ in done], [w for _, warns in done for w in warns]


@tool
def preview_animation(canvas: str, animation: str, frames: int = 8, columns: int = 4, cell: int = 320,
                      background: str = "checker", region: list[float] | None = None,
                      times: list[float] | None = None):
    """Show an animation as a filmstrip: `frames` moments spread evenly over its duration, side by side,
    each labelled with its time. This is how you watch your own animation - read it left to right and
    check spacing between frames (even spacing = linear, bunching at the end = ease-out), overshoot,
    anything popping, clipping at the canvas edge, and that a loop's last frame leads back into the first.

    times: exact moments in seconds instead of the even spread (zoom in on a fast part).
    region [x, y, width, height] crops every frame to one area. For a single moment at full size use
    preview(canvas, animation=..., time=...).
    """
    st = store()
    c = st.get(canvas)
    key, anim = st.get_animation(c, animation)
    duration = anim["duration"]
    if times:
        moments = [max(0.0, min(duration, float(t))) for t in times][:24]
    else:
        frames = max(2, min(24, int(frames)))
        last = duration * (frames - 1) / frames if anim.get("loop") else duration
        moments = [last * i / (frames - 1) for i in range(frames)]
    if region:
        rx, ry, rw, rh = (float(v) for v in region)
        if rw <= 0 or rh <= 0:
            raise ValueError("region width and height must be > 0")
    else:
        rx, ry, rw, rh = 0.0, 0.0, float(c["width"]), float(c["height"])
    columns = max(1, min(8, int(columns), len(moments)))
    cell = max(96, min(512, int(cell)))
    scale = min(4.0, cell / max(rw, rh))
    fw, fh = max(1, int(round(rw * scale))), max(1, int(round(rh * scale)))
    rows = (len(moments) + columns - 1) // columns
    pad, label_h = 10, 18
    sheet = PILImage.new("RGBA", (columns * (fw + pad) + pad, rows * (fh + label_h + pad) + pad), (18, 18, 22, 255))
    draw = ImageDraw.Draw(sheet)
    font = _label_font(12)
    frames_img, warnings = _poses(c, anim, moments, scale)
    for i, (t, img) in enumerate(zip(moments, frames_img)):
        if region:
            img = img.crop((int(round(rx * scale)), int(round(ry * scale)),
                            int(round(rx * scale)) + fw, int(round(ry * scale)) + fh))
        tile = backdrop((fw, fh), background, st.theme.get("colors", {}))
        tile.alpha_composite(img)
        ox, oy = pad + (i % columns) * (fw + pad), pad + (i // columns) * (fh + label_h + pad)
        sheet.paste(tile, (ox, oy))
        draw.text((ox, oy + fh + 2), f"{t:.3f}s", fill="#ffffff", font=font)
    info: dict = {"animation": key, "duration": duration, "loop": anim.get("loop", False),
                  "times": [round(t, 4) for t in moments], "frame_scale": round(scale, 3),
                  "tracks": len(anim["tracks"])}
    if not anim["tracks"]:
        info["note"] = "this animation has no tracks yet - add some with set_keyframes"
    if warnings:
        info["warnings"] = sorted(set(warnings))
    return [Image(data=_png_bytes(sheet.convert("RGB")), format="png"), json.dumps(info)]


def _encode_video(images: list, rate: float, path: Path, fmt: str) -> None:
    import shutil
    import subprocess
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            exe = None
    if not exe:
        raise ValueError('mp4 / webm export needs ffmpeg: install it (winget install ffmpeg, brew install ffmpeg, '
                         'apt install ffmpeg) or pip install "uiforge-mcp[video]"')
    w, h = images[0].size
    if fmt == "mp4":
        codec = ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                 "-preset", "slow", "-movflags", "+faststart"]
    else:
        codec = ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:color=0x00000000", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                 "-b:v", "0", "-crf", "24", "-row-mt", "1", "-auto-alt-ref", "0"]
    cmd = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", f"{rate:g}",
           "-i", "-", *codec, str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for im in images:
            proc.stdin.write(im.convert("RGBA").tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    stderr = proc.stderr.read() if proc.stderr else b""
    if proc.wait() != 0:
        raise ValueError("ffmpeg failed: " + stderr.decode("utf-8", "replace")[-400:])


@tool
def export_animation(canvas: str, animation: str, format: str = "spritesheet", path: str | None = None,
                     fps: float | None = None, scale: float = 1, background: str | None = None,
                     trim: bool = True, ids: list[str] | None = None, group: str | None = None,
                     motion_blur: int = 0, repeat: int = 1, state_machine: dict | None = None):
    """Export an animation.

    format:
      "json"        keyframe data (targets, properties, times, values, eases with their Roblox TweenService and
                    DOTween names). Use this when the engine can tween the property itself - crisp at any
                    size and cheap. Pair it with export_layers so each animated part is its own image.
      "spritesheet" every frame in one PNG grid + a JSON with frame size, columns, fps. For effects an engine
                    cannot tween (shine sweeps, morphing shapes, clipped fills): Unity sprite animation,
                    Unreal flipbook / SubUV, Roblox ImageRectOffset.
      "frames"      numbered PNG files in a folder.
      "gif" / "apng" / "webp"   one animated file to look at or share (GIF: 256 colors, hard edges on
                    transparency; APNG and WebP keep full quality and alpha).
      "mp4" / "webm" video for trailers, store pages, social posts and video players (H.264 MP4 is opaque,
                    on the canvas background or `background`; VP9 WebM keeps transparency). Needs ffmpeg
                    on PATH or pip install "uiforge-mcp[video]". repeat plays a loop several times.
      "lottie"      Lottie JSON for apps, the web (lottie-web), and Lottie players in Unity / Unreal / Godot.
                    Plain shapes and text become real vector shape layers (crisp at any size, solid colour
                    changes animate natively); effects become pictures moved by Lottie; parts whose glow /
                    shape animates become one picture per frame (the result lists each kind).
      "dotlottie"   dotLottie v2 (.lottie) ZIP archive with manifest.json (version "2"), a/<id>.json
                    animations, and s/<id>.json interactive State Machine (synthesized from set_interaction,
                    set_binding and multi-animations, or passed explicitly via state_machine={...}). Pass
                    animation="all" to bundle every animation of the canvas into one Rive-like .lottie package.
    fps: sampling rate (default: the animation's own). scale: resolution multiplier.
    background: "dark", "light", "checker", "game" or a color to put behind the frames. Without it, sprite
      sheets and frames are transparent; animated files show the canvas background if it has one (a GIF
      with nothing behind it gets a dark backdrop).
    trim: crop all frames to the area that is ever painted (sprite sheets and frames only).
    motion_blur: 4-8 sub-frame samples per frame blur fast motion like a camera shutter (spins, dashes,
      swipes) in sprite sheets, frames, GIF / APNG / WebP; 0 = off. Costs that many renders per frame.
    ids / group: export only those elements.
    state_machine: optional explicit dotLottie v2 state machine JSON object (initial, states, interactions, inputs).
    path: output file (or folder for "frames"); relative paths go to the workspace exports folder.
    """
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, None)
    fmt = format.lower()
    if fmt not in ("json", "spritesheet", "frames", "gif", "apng", "webp", "lottie", "dotlottie", "mp4", "webm"):
        raise ValueError("format must be json, spritesheet, frames, gif, apng, webp, mp4, webm, lottie or dotlottie")
    if fmt == "dotlottie":
        from . import lottie
        if not 0.1 <= float(scale) <= 8:
            raise ValueError("scale must be between 0.1 and 8")
        anim_names = sorted((c.get("animations") or {}).keys()) if str(animation).lower() == "all" else [animation]
        if not anim_names:
            raise ValueError(f"canvas '{c['id']}' has no animations to bundle; call create_animation first")
        base_name = f"{c['id']}_all" if str(animation).lower() == "all" else f"{c['id']}_{slugify(animation, 'anim')}"
        out = Path(path).expanduser() if path else st.exports_dir / "animations" / f"{base_name}.lottie"
        if not out.is_absolute():
            out = st.exports_dir / out
        if out.suffix.lower() != ".lottie":
            raise ValueError("dotlottie export path must end with .lottie")
        out.parent.mkdir(parents=True, exist_ok=True)
        blob, rep = lottie.build_dotlottie(st, c, anim_names, fps, float(scale),
                                           bool(background) or bool(c.get("background")),
                                           state_machine=_maybe_json(state_machine))
        out.write_bytes(blob)
        res_dl = {"file": str(out), "format": "dotlottie", "spec_version": rep["spec_version"],
                  "count": rep["count"], "animations": rep["animations"], "bytes": len(blob)}
        if rep.get("state_machine"):
            res_dl["state_machine"] = rep["state_machine"]
        return res_dl
    key, anim = st.get_animation(c, animation)
    base_name = f"{c['id']}_{key}"
    if fmt == "lottie":
        from . import lottie
        if not 0.1 <= float(scale) <= 8:
            raise ValueError("scale must be between 0.1 and 8")
        out = Path(path).expanduser() if path else st.exports_dir / "animations" / f"{base_name}.lottie.json"
        if not out.is_absolute():
            out = st.exports_dir / out
        if out.suffix.lower() != ".json":
            raise ValueError("lottie export path must end with .json")
        out.parent.mkdir(parents=True, exist_ok=True)
        doc, report = lottie.build(st, c, anim, base_name, fps, float(scale), bool(background) or bool(c.get("background")))
        out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        return {"file": str(out), "frames": doc["op"], "fps": doc["fr"], "size": [doc["w"], doc["h"]],
                "vector_layers": report["vector"], "animated_by_transform": report["transform"],
                "baked_per_frame": report["frames"],
                "static": report["static"], "bytes": out.stat().st_size}
    if fmt == "json":
        out = Path(path).expanduser() if path else st.exports_dir / "animations" / f"{base_name}.anim.json"
        if not out.is_absolute():
            out = st.exports_dir / out
        if out.suffix.lower() != ".json":
            raise ValueError("json export path must end with .json")
        out.parent.mkdir(parents=True, exist_ok=True)
        data = anim_mod.describe(key, anim, c)
        if c.get("interactions"):
            data["interactions"] = c["interactions"]
        ex.write_json(out, data)
        return {"file": str(out), "tracks": len(data["tracks"]), "duration": data["duration"], "loop": data["loop"]}

    if not 0.1 <= float(scale) <= 8:
        raise ValueError("scale must be between 0.1 and 8")
    times = anim_mod.frame_times(anim, fps)
    rate = float(fps or anim.get("fps", 30))
    only = {e["id"] for e in st.select(c, ids, group)} if (ids or group) else None
    own_bg = c.get("background") if fmt in ("gif", "apng", "webp", "mp4", "webm") and not background else None
    images, warnings = _poses(c, anim, times, float(scale), include_background=bool(own_bg), only=only,
                              motion_blur=motion_blur, fps=rate)
    result: dict = {"animation": key, "frames": len(images), "fps": rate, "duration": anim["duration"],
                    "loop": bool(anim.get("loop"))}
    offset = (0, 0)
    if trim and fmt in ("spritesheet", "frames"):
        boxes = [im.getchannel("A").getbbox() for im in images]
        boxes = [b for b in boxes if b]
        if boxes:
            box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
            images = [im.crop(box) for im in images]
            offset = (box[0], box[1])
    if not own_bg and (background or fmt in ("gif", "mp4")):
        flat = []
        for im in images:
            bg = backdrop(im.size, background or "dark", st.theme.get("colors", {}))
            bg.alpha_composite(im)
            flat.append(bg)
        images = flat
    fw, fh = images[0].size

    if fmt == "frames":
        folder = Path(path).expanduser() if path else st.exports_dir / "animations" / base_name
        if not folder.is_absolute():
            folder = st.exports_dir / folder
        folder.mkdir(parents=True, exist_ok=True)
        digits = max(3, len(str(len(images) - 1)))
        for i, im in enumerate(images):
            im.save(folder / f"{base_name}_{i:0{digits}d}.png")
        ex.write_json(folder / f"{base_name}.frames.json", {
            "animation": key, "frames": len(images), "fps": rate, "duration": anim["duration"],
            "loop": bool(anim.get("loop")), "frame_width": fw, "frame_height": fh, "scale": scale,
            "offset": [round(offset[0] / float(scale), 2), round(offset[1] / float(scale), 2)],
            "pattern": f"{base_name}_{'#' * digits}.png"})
        result.update(folder=str(folder), frame_size=[fw, fh])
    elif fmt == "spritesheet":
        out = _out_path(path, f"{base_name}_sheet.png", "animations")
        columns = max(1, int(len(images) ** 0.5 + 0.999))
        rows = (len(images) + columns - 1) // columns
        sheet = PILImage.new("RGBA", (columns * fw, rows * fh), (0, 0, 0, 0))
        for i, im in enumerate(images):
            sheet.paste(im, ((i % columns) * fw, (i // columns) * fh))
        sheet.save(out)
        meta = {"animation": key, "image": out.name, "frames": len(images), "columns": columns, "rows": rows,
                "frame_width": fw, "frame_height": fh, "fps": rate, "duration": anim["duration"],
                "loop": bool(anim.get("loop")), "scale": scale,
                "offset": [round(offset[0] / float(scale), 2), round(offset[1] / float(scale), 2)]}
        ex.write_json(out.with_suffix(".json"), meta)
        result.update(file=str(out), json=str(out.with_suffix(".json")), sheet_size=list(sheet.size),
                      frame_size=[fw, fh], columns=columns, rows=rows)
        if max(sheet.size) > ex.ROBLOX_MAX:
            result["note"] = (f"sheet is {sheet.width}x{sheet.height}; Roblox downsizes images over {ex.ROBLOX_MAX}px. "
                              "Lower fps or scale, or tween the property in engine with format='json'.")
    else:
        suffix = {"gif": ".gif", "apng": ".png", "webp": ".webp", "mp4": ".mp4", "webm": ".webm"}[fmt]
        st_path = Path(path).expanduser() if path else st.exports_dir / "animations" / f"{base_name}{suffix}"
        if not st_path.is_absolute():
            st_path = st.exports_dir / st_path
        if st_path.suffix.lower() != suffix:
            raise ValueError(f"{fmt} export path must end with {suffix}")
        st_path.parent.mkdir(parents=True, exist_ok=True)
        ms = max(10, int(round(1000 / rate)))
        loops = 0 if anim.get("loop") else 1
        if fmt in ("mp4", "webm"):
            reps = max(1, min(100, int(repeat))) if anim.get("loop") else 1
            _encode_video(images * reps, rate, st_path, fmt)
            result["bytes"] = st_path.stat().st_size
        elif fmt == "gif":
            frames_p = [im.convert("RGB").quantize(colors=255, method=PILImage.Quantize.MEDIANCUT,
                                                   dither=PILImage.Dither.FLOYDSTEINBERG) for im in images]
            frames_p[0].save(st_path, save_all=True, append_images=frames_p[1:], duration=ms, loop=0, disposal=1,
                             optimize=False)
            if not anim.get("loop"):
                result["note"] = "GIF preview repeats forever in most viewers; the animation itself is not a loop."
        elif fmt == "apng":
            images[0].save(st_path, format="PNG", save_all=True, append_images=images[1:], duration=ms, loop=loops,
                           disposal=1, blend=0)
        else:
            images[0].save(st_path, format="WEBP", save_all=True, append_images=images[1:], duration=ms, loop=loops,
                           lossless=True)
        result.update(file=str(st_path), frame_size=[fw, fh])
    if warnings:
        result["warnings"] = sorted(set(warnings))
    return result



@tool
def set_theme(colors: dict | None = None, styles: dict | None = None, replace: bool = False,
              modes: dict | None = None, mode: str | None = None, numbers: dict | None = None,
              tokens: dict | str | None = None, materials: dict | None = None,
              environment: dict | None = None, quality: str | None = None,
              style_preset: str | None = None, apply_preset_tokens: bool = True):
    """Define the design tokens, quality tier and visual style preset shared by every canvas.

    quality: output realism & detail tier ("simple" | "standard" | "advanced" | "aaa").
      - "simple": fast clean flat shading, zero micro-grain, minimal frame ornaments, 2x supersampling (ideal for kids/casual/wireframes).
      - "standard": balanced bevels, moderate grain, core frame brackets, 3x supersampling (ideal for cartoon/stylized/web apps).
      - "advanced": full Cook-Torrance GGX PBR, HDR IBL, rich procedural ornaments, 4x supersampling.
      - "aaa": deepened bevels, heightened edge wear & micro-bump, full ornate details, 4x supersampling.
    style_preset: design direction ("kids" | "cartoon" | "stylized" | "minimal" | "web_saas" | "scifi" |
      "dark_fantasy" | "realistic" | "photorealistic"). When apply_preset_tokens=true (default), seeds matching
      palette colours, spacing/radius numbers, panel/button/title/body styles, studio lighting and default quality.
    modes: Figma-style variable modes - named sets of colour overrides, e.g.
      {"light": {"bg": "#f5f5f7", "text": "#111"}, "colorblind": {"danger": "#ff8800"}}. mode: the active one
      for every canvas ("" = base colours); one canvas can pick its own with update_canvas(mode=...).
      Every "$token" in fills, strokes, effects and theme styles follows the mode, so one kit renders as
      dark, light, team colours or seasonal skins; export_theme writes all modes.
    numbers: number variables, e.g. {"space-md": 16, "radius-card": 12, "stroke-thin": 1.5, "text-h1": 32} -
      use "$space-md" anywhere a number goes (radius, width, gap, font size, stroke width, blur...; not x / y).
      A mode may override them too: modes={"compact": {"space-md": 10}}.
    tokens: import a W3C design-tokens (DTCG) JSON - a dict or a .json path - as exported by Tokens Studio,
      Penpot or Style Dictionary: colours become colour tokens, dimensions / numbers become number tokens,
      {group.name} aliases become $group-name. A DESIGN.md path (as written by AI design and coding tools)
      imports its colours, typography (as text styles), rounded / spacing (as radius-* / space-* numbers).
    materials: your own named materials, used like the built-in ones as style {"material": "name"}. Each is a
      style object: build on a built-in one ({"material": "wood", "color": "#5a3a22", "scale": 2,
      "light": {...}}) or write it from scratch with a shader fill ({"fill": {"type": "shader", "code": ...,
      "params": {"c": "$primary", "t": 0}}, "light": {...}, "noise": 0.05}). A use like {"material":
      {"name": "mine", "color": ..., "scale": ..., "t": ...}} feeds those into its shader params (c, sc, t).
    environment: workspace-wide PBR IBL environment lighting for all metallic and glossy materials, e.g.
      {"env_map": "/path/to/scene.hdr", "rotation": 30, "intensity": 1.15, "studio": "warm"}. Accepts Radiance
      .hdr, OpenEXR .exr, or equirectangular PNG/JPG files; pass {} to reset to default studio lighting.
    colors: {"bg": "#0d0b14", "primary": "#8b5cf6", ...} -> use anywhere as "$primary" or "$primary@0.5".
    styles: named style objects, usable as style="panel" or {"use": "panel", ...overrides}. A style can
      hold any style key plus text defaults (font, weight, size, letter_spacing, uppercase), e.g.
      {"panel": {"fill": "$surface", "stroke": {"color": "$primary@0.6", "width": 2}, "shadow": {"blur": 24, "dy": 8}},
       "title": {"font": "Rajdhani", "weight": 700, "size": 32, "fill": "$text", "uppercase": true}}
    Entries are merged into the existing theme (set a key to null to remove it); replace=true starts over.
    Changing the theme restyles every element that references it.
    """
    from . import profiles
    st = store()
    colors, numbers = _maybe_json(colors), _maybe_json(numbers)
    styles = _maybe_json(styles)
    if tokens is not None:
        tok = _maybe_json(tokens)
        if isinstance(tok, str) and tok.strip().lower().endswith(".md"):
            from .tokens import read_design_md
            md = Path(tok).expanduser()
            if not md.is_file():
                raise ValueError(f"DESIGN.md not found: {md}")
            got_colors, got_numbers, got_styles = read_design_md(md.read_text(encoding="utf-8"))
            styles = {**got_styles, **(styles or {})}
        else:
            from .tokens import read_dtcg
            got_colors, got_numbers = read_dtcg(tok)
        colors = {**got_colors, **(colors or {})}
        numbers = {**got_numbers, **(numbers or {})}
    st.set_theme(colors, styles, replace, _maybe_json(modes), mode, numbers, _maybe_json(materials),
                 _maybe_json(environment), quality=quality, style_preset=style_preset,
                 apply_preset_tokens=bool(apply_preset_tokens))
    eff_prof = profiles.resolve_profile(st.theme)
    out = {"colors": st.theme["colors"], "numbers": st.theme.get("numbers", {}), "styles": sorted(st.theme["styles"]),
           "modes": sorted(st.theme.get("modes") or {}), "mode": st.theme.get("mode"),
           "materials": sorted(st.theme.get("materials") or {}),
           "profile": {"quality": eff_prof["quality"], "style_preset": eff_prof.get("style_preset"),
                       "pbr_mode": eff_prof["pbr_mode"], "ornament_density": eff_prof["ornament_density"]}}
    if st.theme.get("environment"):
        out["environment"] = st.theme["environment"]
    return out


@tool
def get_theme():
    """Return the current theme (color tokens and named styles)."""
    return store().theme


@tool
def list_fonts(include_system: bool = False):
    """List available font families. Bundled: Inter (clean, modern AAA menus), Barlow Condensed (motorsport /
    realistic HUD, has italics), Bebas Neue (tall display caps), Michroma (wide dashboard lettering),
    JetBrains Mono (fixed-width digits for timers and telemetry), Rajdhani and Orbitron (sci-fi/tech),
    Cinzel (fantasy/medieval), Fredoka (rounded, casual/cartoon), Bangers (comic/arcade).
    include_system=true also scans fonts installed on this computer. Extra .ttf/.otf files dropped
    into the workspace "fonts" folder are picked up as well."""
    st = store()
    st.fonts.rescan_user()
    return {"fonts": st.fonts.families(include_system), "user_font_folder": str(st.fonts_dir)}


@tool
def measure_text(text: str, size: float = 24, font: str | None = None, weight: int | str | None = None,
                 letter_spacing: float = 0, max_width: float | None = None, uppercase: bool | str | None = None,
                 line_height: float = 1.2):
    """Measure text without drawing it: width, height and wrapped lines. Use it to size a button or
    panel around a label before drawing."""
    st = store()
    el = {"id": "measure", "type": "text", "text": text, "x": 0, "y": 0, "size": size, "font": font,
          "weight": weight, "letter_spacing": letter_spacing, "max_width": max_width, "uppercase": uppercase,
          "line_height": line_height}
    layout = TextLayout({k: v for k, v in el.items() if v is not None}, {}, st.fonts, 4.0)
    x0, y0, x1, y1 = layout.box_units()
    return {"width": _round(x1 - x0), "height": _round(y1 - y0), "cap_height": _round(layout.cap / 4.0),
            "line_step": _round(layout.size * layout.line_height),
            "lines": [{"text": line, "width": _round(w / 4.0)} for line, w in layout.lines]}



def _label_font(size: int = 12):
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


@tool
def preview(canvas: str, background: str = "checker", max_size: int = 1024, show_ids: bool = False,
            region: list[float] | None = None, zoom: float | None = None,
            animation: str | None = None, time: float = 0, layers: list[str] | None = None,
            state: str | None = None, language: str | None = None, guides: list[str] | None = None,
            simulate: str | None = None, data: dict | None = None):
    """Render a canvas and return the picture so you can check your work. Look at it critically:
    alignment, spacing, contrast, clipped shadows, text overflow.

    background (only behind transparent areas, never exported): "checker", "checker-light", "dark",
    "light", "game" (a busy scene stand-in, to test HUD readability) or any color.
    show_ids=true outlines every element with its id - use it to find what to fix.
    region [x, y, width, height] zooms into part of the canvas for detail checks.
    zoom: render scale; by default the view is scaled to fit max_size (small assets are enlarged up to 4x).
    animation + time: show the canvas posed at `time` seconds of that animation (one frame, full detail).
    layers: show only these layers (e.g. ["shade"] to inspect a shading pass alone; "base" = the
    implicit bottom layer). Clipped layers stay clipped to their base.
    background may also be an image file path: your HUD over a real gameplay screenshot.
    state: show an interaction state (set_state), e.g. "hover". language: fill {placeholders} from that
      string table; "pseudo" = accented, 35% longer text to catch clipping before translation,
      "pseudo-long" = 100% longer (short labels), "pseudo-rtl" = pseudo forced right-to-left.
    guides (drawn on the preview only): "safe" (device safe area), "tv" (title / action safe),
      "grid:8", "columns:12", "thirds", "center", "thumb" (thumb reach on a landscape phone).
    simulate: "protanopia", "deuteranopia", "tritanopia" (colour blindness), "grayscale", "low-contrast"
      (sunlit phone) - check that states and rarities differ by more than hue.
    data: override bound variables (set_binding) for this preview only, e.g. {"hp": 15} to check low-HP look.
    """
    st = store()
    c = st.get(canvas)
    pose_warnings: list[str] = []
    if data:
        from . import binding
        c = binding.apply_bindings(c, _maybe_json(data))
    if animation:
        _, anim = st.get_animation(c, animation)
        c, pose_warnings = anim_mod.apply_animation(c, anim, float(time), st.theme.get("colors", {}))
    if region:
        rx, ry, rw, rh = (float(v) for v in region)
        if rw <= 0 or rh <= 0:
            raise ValueError("region width and height must be > 0")
    else:
        rx, ry, rw, rh = 0.0, 0.0, float(c["width"]), float(c["height"])
    max_size = max(64, min(2048, int(max_size)))
    if zoom:
        scale = max(0.05, min(8.0, float(zoom)))
        if max(rw, rh) * scale > 2048:
            scale = 2048 / max(rw, rh)
    else:
        scale = min(4.0, max_size / max(rw, rh))
    r = st.renderer(c, scale, state=state, language=language)
    solo = None
    if layers:
        solo = {"base" if str(n).strip().lower() == "base" else st.get_layer(c, n)["name"] for n in layers}
    img = r.render(only_layers=solo)
    if region:
        crop = (int(round(rx * scale)), int(round(ry * scale)), int(round((rx + rw) * scale)), int(round((ry + rh) * scale)))
        img = img.crop(crop)
    view = _backdrop_any(background, img.size, c, scale, (rx, ry))
    view = PILImage.alpha_composite(view, img)
    notes: list[str] = []
    if simulate:
        from .viewing import simulate as _sim
        view = _sim(view, simulate)
    if guides:
        from .viewing import draw_guides
        notes += draw_guides(view, list(_maybe_json(guides)), c, scale, (rx, ry))
    if show_ids:
        draw = ImageDraw.Draw(view)
        font = _label_font(12)
        palette = ["#ff4d6d", "#4dd2ff", "#ffd24d", "#7dff7a", "#d59bff", "#ff9d4d"]
        for i, el in enumerate(r.canvas["elements"]):
            if not el.get("visible", True):
                continue
            x0, y0, x1, y1 = r.element_box(el)
            col = palette[i % len(palette)]
            box = [(x0 - rx) * scale, (y0 - ry) * scale, (x1 - rx) * scale - 1, (y1 - ry) * scale - 1]
            if box[2] < 0 or box[3] < 0 or box[0] > view.width or box[1] > view.height:
                continue
            draw.rectangle(box, outline=col, width=1)
            label = el["id"]
            tw = draw.textlength(label, font=font)
            lx, ly = max(0, box[0]), max(0, box[1] - 14)
            draw.rectangle([lx, ly, lx + tw + 6, ly + 14], fill=col)
            draw.text((lx + 3, ly), label, fill="#000000", font=font)
    info = {"canvas": c["id"], "canvas_size": [c["width"], c["height"]], "shown_scale": round(scale, 3),
            "image_size": list(view.size), "elements": len(c["elements"])}
    if animation:
        info["animation"], info["time"] = animation, float(time)
    for key, value in (("state", state), ("language", language), ("simulate", simulate)):
        if value:
            info[key] = value
    if notes:
        info["notes"] = notes
    if r.warnings or pose_warnings:
        info["warnings"] = sorted(set(r.warnings + pose_warnings))
    return [Image(data=_png_bytes(view.convert("RGB")), format="png"), json.dumps(info)]


def _backdrop_any(background: str, size: tuple[int, int], c: dict, scale: float,
                  origin: tuple[float, float] = (0.0, 0.0)) -> PILImage.Image:
    """Preview background: a named backdrop / colour, or an image file (e.g. a gameplay screenshot)
    stretched over the whole canvas and cropped to the shown region."""
    text = str(background or "checker")
    if any(text.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        from .viewing import image_backdrop
        full = image_backdrop(text, (max(1, round(c["width"] * scale)), max(1, round(c["height"] * scale))))
        if full is None:
            raise ValueError(f"background image not found: {Path(text).expanduser().resolve()} - use an absolute path (relative paths resolve against the server's working folder, not yours)")
        ox, oy = round(origin[0] * scale), round(origin[1] * scale)
        return full.crop((ox, oy, ox + size[0], oy + size[1]))
    return backdrop(size, text, store().theme.get("colors", {}))


@tool
def contact_sheet(canvases: list[str] | None = None, columns: int = 4, cell: int = 256,
                  background: str = "checker", save_path: str | None = None):
    """Render several canvases side by side in one labelled image (all canvases if none are given).
    Use it to check that a kit is consistent (same radii, stroke weights, colors, lighting) and to
    compare button states. save_path optionally writes the sheet as a PNG too."""
    st = store()
    ids = canvases or list(st.canvases)
    if not ids:
        raise ValueError("No canvases to show - create_canvas first, or pass canvas ids")
    items = [st.get(i) for i in ids]
    columns = max(1, min(8, int(columns), len(items)))
    cell = max(96, min(512, int(cell)))
    rows = (len(items) + columns - 1) // columns
    pad, label_h = 12, 30
    sheet = PILImage.new("RGBA", (columns * (cell + pad) + pad, rows * (cell + label_h + pad) + pad), (18, 18, 22, 255))
    draw = ImageDraw.Draw(sheet)
    font = _label_font(12)
    warnings: list[str] = []
    for i, c in enumerate(items):
        scale = min(4.0, cell / max(c["width"], c["height"]))
        r = st.renderer(c, scale)
        img = r.render()
        warnings += r.warnings
        tile = backdrop((cell, cell), background, st.theme.get("colors", {}))
        tile.alpha_composite(img, ((cell - img.width) // 2, (cell - img.height) // 2))
        col, row = i % columns, i // columns
        ox, oy = pad + col * (cell + pad), pad + row * (cell + label_h + pad)
        sheet.paste(tile, (ox, oy))
        draw.text((ox, oy + cell + 2), c["id"][:38], fill="#ffffff", font=font)
        draw.text((ox, oy + cell + 15), f"{c['width']}x{c['height']}", fill="#9aa0aa", font=font)
    info: dict = {"canvases": [c["id"] for c in items], "image_size": list(sheet.size)}
    if save_path:
        out = _out_path(save_path, "contact_sheet.png")
        sheet.convert("RGB").save(out)
        info["saved"] = str(out)
    if warnings:
        info["warnings"] = warnings
    return [Image(data=_png_bytes(sheet.convert("RGB")), format="png"), json.dumps(info)]




def _luminance(rgb) -> float:
    def ch(v: float) -> float:
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _over(rgba, under=(0, 0, 0)) -> tuple[float, float, float]:
    a = rgba[3] / 255.0
    return tuple(rgba[i] * a + under[i] * (1 - a) for i in range(3))


@tool
def review_canvas(canvas: str, min_contrast: float = 4.5, min_text_size: float = 12,
                  backdrop_color: str = "#000000", language: str | None = None, state: str | None = None):
    """Automatic quality check - run it before exporting, next to looking at `preview` yourself.

    Reports: paint cut off at the canvas edge (shadow/glow/outline clipped), elements outside the canvas,
    text with low contrast against what is really behind it (WCAG ratio; min_contrast 4.5 for small text,
    3 is acceptable for big bold labels), text smaller than min_text_size, missing font glyphs,
    rectangles on fractional pixels (soft, blurry edges), invisible or fully transparent elements,
    empty / hidden layers, clipped layers with nothing to clip to, animation tracks whose target is gone,
    and instances whose source is missing. backdrop_color: what transparent areas sit on in the game.
    Design lint (info): edges that almost line up, too many corner radii / stroke widths / text sizes,
    hard-coded colours where the theme has tokens.
    Also: text that overflows the shape it sits in (the smallest shape drawn under it that holds its
    anchor point, or the element named in the text's "container" prop) and important UI inside the
    canvas safe_area margins (notch, home bar, TV overscan).
    language: check a translation - "pseudo" (35% longer, accented), "pseudo-long" (100% longer) and
      "pseudo-rtl" (forced right-to-left) find clipping before translators do.
    state: check an interaction state (hover, disabled...).
    """
    import numpy as np
    from .colors import parse_color as _pc
    st = store()
    c = st.get(canvas)
    colors = st.theme.get("colors", {})
    under = _pc(backdrop_color, colors)[:3]
    issues: list[dict] = []

    def add(kind: str, msg: str, ids: list[str] | None = None, severity: str = "warn") -> None:
        item: dict = {"severity": severity, "check": kind, "message": msg}
        if ids:
            item["ids"] = ids
        issues.append(item)

    r = st.renderer(c, state=state, language=language)
    c = r.canvas
    try:
        full = r.render(include_background=False)
    except ValueError as exc:
        add("render", str(exc), severity="error")
        return {"canvas": c["id"], "ok": False, "issues": issues}
    for w in sorted(set(r.warnings)):
        add("glyphs" if "glyph" in w else "render", w)
    a = np.asarray(full.getchannel("A"))
    edges = {"top": a[0, :], "bottom": a[-1, :], "left": a[:, 0], "right": a[:, -1]}
    cut = [side for side, row in edges.items() if (row > 8).mean() > 0.002]
    bg_set = c.get("background") not in (None, "none", "transparent")
    if cut and not bg_set:
        touch = []
        for el in c["elements"]:
            if not el.get("visible", True):
                continue
            x0, y0, x1, y1 = r.element_box(el)
            if x0 < 1 or y0 < 1 or x1 > c["width"] - 1 or y1 > c["height"] - 1:
                touch.append(el["id"])
        add("edge", f"paint reaches the canvas edge ({', '.join(cut)}): a shadow, glow or outline is probably "
                    "cut off in the exported PNG. Make the canvas bigger, move the art inward, or run fit_canvas "
                    "with some padding (unless the asset is meant to be full-bleed).", touch or None)

    names = {l["name"] for l in c.get("layers", [])}
    texts = []
    for el in c["elements"]:
        eid = el["id"]
        if not el.get("visible", True):
            add("hidden", "element is hidden (visible: false)", [eid], "info")
            continue
        try:
            x0, y0, x1, y1 = r.element_box(el)
        except ValueError as exc:
            add("render", f"{eid}: {exc}", [eid], "error")
            continue
        if x1 <= 0 or y1 <= 0 or x0 >= c["width"] or y0 >= c["height"]:
            add("offcanvas", "element is entirely outside the canvas", [eid])
        style = el.get("style")
        if isinstance(style, dict) and float(style.get("opacity", 1) or 0) <= 0.01 and "opacity" in style:
            add("transparent", "element has opacity 0", [eid], "info")
        if el["type"] == "rect" and not el.get("rotation"):
            vals = [float(el.get(k, 0)) for k in ("x", "y", "width", "height")]
            if any(abs(v - round(v)) > 1e-6 for v in vals):
                add("subpixel", "rectangle is not on whole pixels, so its edges render soft "
                                f"({', '.join(f'{v:g}' for v in vals)})", [eid], "info")
        if el["type"] == "instance":
            try:
                st.get(str(el.get("source")))
            except ValueError:
                add("instance", f"instance source '{el.get('source')}' does not exist", [eid], "error")
        if el["type"] == "text":
            texts.append(el)
        if el.get("layer") and el["layer"] not in names:
            add("layer", f"element points at a missing layer '{el['layer']}' (drawn on base)", [eid])

    cs = min(1.0, 900.0 / max(c["width"], c["height"]))
    with_all = None
    boxes = {}
    for e in c["elements"]:
        try:
            boxes[e["id"]] = r.element_box(e)
        except ValueError:
            pass
    reach = 64.0

    def nearby(eid: str) -> set[str]:
        a = boxes[eid]
        return {o for o, b in boxes.items() if o != eid and b[0] - reach < a[2] and a[0] < b[2] + reach
                and b[1] - reach < a[3] and a[1] < b[3] + reach}

    for el in texts:
        eid = el["id"]
        tst = resolve_style(el.get("style"), st.theme)
        size = el.get("size") or tst.get("size") or 24
        if float(size) < min_text_size:
            add("text_size", f"text size {float(size):g}px is below {min_text_size:g}px; hard to read in game", [eid])
        try:
            if with_all is None:
                with_all = np.asarray(st.renderer(c, cs, language=language).render(), dtype=np.float64)
            bx = r.element_box(el)
            hidden = dict(c, elements=[e for e in c["elements"] if e is not el])
            without = np.asarray(st.renderer(hidden, cs, language=language).render(only=nearby(eid)),
                                 dtype=np.float64)
        except ValueError:
            continue
        H, W = with_all.shape[:2]
        x0, y0 = max(0, int(bx[0] * cs)), max(0, int(bx[1] * cs))
        x1, y1 = min(W, int(bx[2] * cs) + 1), min(H, int(bx[3] * cs) + 1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        a_box, b_box = with_all[y0:y1, x0:x1], without[y0:y1, x0:x1]
        diff = np.abs(a_box - b_box).sum(axis=-1)
        if diff.max() < 3:
            continue
        lit = diff > diff.max() * 0.25
        core = diff >= np.quantile(diff[lit], 0.6) if lit.sum() > 8 else diff >= diff.max() * 0.7
        fg = [float(v) for v in a_box[core].mean(axis=0)]
        from .effects import dilate
        near = dilate(lit.astype(np.uint8) * 255, max(2.0, float(size) * cs * 0.35)) > 0
        around = near & ~lit
        pool = b_box[around] if around.sum() > 8 else b_box.reshape(-1, 4)
        bg = [float(v) for v in pool.mean(axis=0)]
        ratio = _contrast(_over(fg, under), _over(bg, under))
        if ratio < min_contrast:
            add("contrast", f"text contrast {ratio:.2f}:1 is below {min_contrast:g}:1 (text ~{_hex(fg)} on "
                            f"~{_hex(bg)}). Lighten/darken one side or add a dark outline / shadow.", [eid])

    order = {e["id"]: i for i, e in enumerate(c["elements"])}
    for el in texts:
        if el.get("arc"):
            continue
        try:
            tb = r.element_box(el)
        except ValueError:
            continue
        holder = None
        if el.get("container"):
            holder = next((e for e in c["elements"] if e["id"] == el["container"]), None)
        else:
            ax, ay = float(el.get("x", 0)), float(el.get("y", 0))
            best = None
            for other in c["elements"]:
                if other is el or other["type"] in ("text", "line", "arc", "ticks") or order[other["id"]] > order[el["id"]]:
                    continue
                if not other.get("visible", True):
                    continue
                try:
                    ob = r.element_box(other)
                except ValueError:
                    continue
                area = (ob[2] - ob[0]) * (ob[3] - ob[1])
                if ob[0] <= ax <= ob[2] and ob[1] <= ay <= ob[3] and area > 0:
                    if best is None or area < best[0]:
                        best = (area, other, ob)
            holder = best[1] if best else None
        if holder is None:
            continue
        hb = r.element_box(holder)
        over = max(hb[0] - tb[0], tb[2] - hb[2], hb[1] - tb[1], tb[3] - hb[3])
        if over > 0.5:
            where = f" in language '{language}'" if language else ""
            add("overflow", f"text overflows '{holder['id']}' by {over:.0f}px{where}: use fit_width / max_width, "
                            "a smaller size, or a wider shape", [el["id"], holder["id"]])

    if c.get("safe_area"):
        l, t, rr_, b = (float(v) for v in c["safe_area"])
        W, H = float(c["width"]), float(c["height"])
        offenders = []
        for el in c["elements"]:
            if not el.get("visible", True):
                continue
            try:
                bx = r.element_box(el)
            except ValueError:
                continue
            if bx[2] - bx[0] >= W * 0.9 or bx[3] - bx[1] >= H * 0.9:
                continue
            if bx[0] < l - 0.5 or bx[1] < t - 0.5 or bx[2] > W - rr_ + 0.5 or bx[3] > H - b + 0.5:
                offenders.append(el["id"])
        if offenders:
            add("safe_area", "elements reach into the safe-area margin (notch, rounded corners, home bar or TV "
                             "overscan) - keep text and buttons inside; backgrounds may bleed", offenders[:20])

    from .lint import design_lint
    for kind, msg, ids in design_lint(r, c, st.theme):
        add(kind, msg, ids, "info")

    layers = c.get("layers", [])
    for i, layer in enumerate(layers):
        members = [e for e in c["elements"] if e.get("layer") == layer["name"]]
        if not members:
            add("layer", f"layer '{layer['name']}' is empty", None, "info")
        if not layer.get("visible", True):
            add("layer", f"layer '{layer['name']}' is hidden", None, "info")
        if layer.get("clip"):
            has_base = i > 0 or any(e.get("layer") not in names for e in c["elements"])
            if not has_base:
                add("layer", f"layer '{layer['name']}' clips to the layer below, but there is nothing below it")
    for name, anim in (c.get("animations") or {}).items():
        _, warns = anim_mod.apply_animation(c, anim, 0, st.theme.get("colors", {}))
        for w in warns:
            add("animation", f"animation '{name}': {w}")
        if not anim.get("tracks"):
            add("animation", f"animation '{name}' has no tracks", None, "info")
    order = {"error": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: order[i["severity"]])
    return {"canvas": c["id"], "ok": not any(i["severity"] != "info" for i in issues),
            "issues": issues or [{"severity": "info", "check": "all", "message": "no problems found"}]}


def _hex(rgba) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(v)))):02x}" for v in rgba[:3])


@tool
def inspect_pixels(canvas: str, points: list[list[float]], scale: float = 1, include_background: bool = True):
    """Read exact rendered colours at canvas points [[x, y], ...] (canvas units). Returns RGBA hex per point,
    and the WCAG contrast ratio between the first two points (e.g. a text pixel and the panel behind it).
    Use it to verify things the eye can miss in a scaled preview: is the bar really the theme colour, is the
    hole really transparent, is a highlight blown out to pure white."""
    st = store()
    c = st.get(canvas)
    pts = _maybe_json(points)
    if not isinstance(pts, list) or not pts or len(pts) > 64:
        raise ValueError("points must be a list of 1-64 [x, y] pairs")
    scale = max(0.25, min(8.0, float(scale)))
    img = st.renderer(c, scale).render(include_background=include_background)
    out = []
    samples = []
    for pt in pts:
        x, y = float(pt[0]), float(pt[1])
        px, py = int(x * scale), int(y * scale)
        if not (0 <= px < img.width and 0 <= py < img.height):
            out.append({"point": [x, y], "error": "outside the canvas"})
            continue
        rgba = img.getpixel((px, py))
        samples.append(rgba)
        out.append({"point": [x, y], "rgba": "#" + "".join(f"{v:02x}" for v in rgba), "alpha": round(rgba[3] / 255, 3)})
    result: dict = {"canvas": c["id"], "pixels": out}
    if len(samples) >= 2:
        result["contrast_first_two"] = round(_contrast(_over(samples[0]), _over(samples[1])), 2)
    return result


@tool
def view_image(path: str, max_size: int = 1024, palette: int = 8):
    """Look at an image file on this computer: a reference screenshot of the game, a mood board, a logo,
    or a PNG you exported. Returns the picture plus its dominant colours (hex, share of pixels, darkest
    to lightest) so you can match a reference's palette with set_theme instead of guessing."""
    src = Path(path).expanduser()
    if not src.is_file():
        raise ValueError(f"Image file not found: {src.resolve()} - use an absolute path (relative paths resolve against the server's working folder, not yours)")
    try:
        img = PILImage.open(src)
        img.load()
    except Exception as exc:
        raise ValueError(f"Could not open {src.name} as an image: {exc}") from exc
    info: dict = {"file": str(src), "size": list(img.size), "mode": img.mode}
    rgba = img.convert("RGBA")
    max_size = max(64, min(2048, int(max_size)))
    view = rgba.copy()
    view.thumbnail((max_size, max_size), PILImage.LANCZOS)
    small = rgba.copy()
    small.thumbnail((256, 256))
    import numpy as np
    arr = np.asarray(small).reshape(-1, 4)
    opaque = arr[arr[:, 3] > 128][:, :3]
    if len(opaque) and palette > 0:
        q = PILImage.fromarray(opaque.reshape(1, -1, 3).astype(np.uint8), "RGB").quantize(
            colors=max(1, min(16, int(palette))), method=PILImage.Quantize.MEDIANCUT)
        pal = q.getpalette()
        counts = sorted(q.getcolors() or [], reverse=True)
        total = sum(n for n, _ in counts) or 1
        cols = []
        for n, idx in counts:
            rgb = pal[idx * 3: idx * 3 + 3]
            cols.append({"hex": "#" + "".join(f"{v:02x}" for v in rgb), "share": round(n / total, 3),
                         "lum": round(_luminance(rgb), 3)})
        cols.sort(key=lambda d: d["lum"])
        info["palette"] = [{"hex": d["hex"], "share": d["share"]} for d in cols]
    if rgba.getchannel("A").getextrema()[0] < 255:
        info["has_transparency"] = True
        view = PILImage.alpha_composite(backdrop(view.size, "checker", {}), view)
    return [Image(data=_png_bytes(view.convert("RGB")), format="png"), json.dumps(info)]


def _paint_axes(spec: Any) -> tuple[bool, bool]:
    """Whether a fill/stroke paint changes along x / along y (gradients only)."""
    if not isinstance(spec, dict):
        return False, False
    kind = str(spec.get("type", "linear")).lower()
    if kind == "radial":
        return True, True
    if kind == "linear":
        import math
        ang = math.radians(float(spec.get("angle", 90)))
        return abs(math.cos(ang)) > 0.01, abs(math.sin(ang)) > 0.01
    return False, False


def _gradient_blocks(c: dict, centre: tuple[float, float]) -> tuple[bool, bool]:
    """Axes that must not be 9-slice stretched because a gradient crosses the centre lines."""
    st = store()
    r = st.renderer(c)
    block_x = block_y = False
    for el in c["elements"]:
        if not el.get("visible", True):
            continue
        style = resolve_style(el.get("style"), st.theme)
        paints = [style.get("fill")]
        stroke = style.get("stroke")
        if isinstance(stroke, dict):
            paints.append(stroke.get("fill", stroke.get("color")))
        x0, y0, x1, y1 = r.element_box(el)
        for paint_spec in paints:
            along_x, along_y = _paint_axes(paint_spec)
            if along_x and x0 < centre[0] < x1:
                block_x = True
            if along_y and y0 < centre[1] < y1:
                block_y = True
    return block_x, block_y


def _render_export(c: dict, scale: float, include_background: bool, ids: list[str] | None, group: str | None,
                   state: str | None = None, language: str | None = None):
    st = store()
    only = None
    if ids or group:
        only = {e["id"] for e in st.select(c, ids, group)}
    r = st.renderer(c, scale, state=state, language=language)
    return r.render(include_background=include_background, only=only), r.warnings


@tool
def export_svg(canvas: str, path: str | None = None, include_background: bool = True, state: str | None = None,
               language: str | None = None, image_scale: float = 2):
    """Save the canvas as an editable vector SVG for Figma, Penpot, Illustrator, Inkscape or the web.

    Shapes (rect, ellipse, polygon, path, boolean, line, arc, ticks) keep their outlines, solid / linear /
    radial fills, fill stacks, strokes (inside / center / outside, dashes) and drop shadows / glows; text
    stays real, editable text (same font names - install them where the SVG is opened). Layers become
    named groups. Whatever SVG cannot show the same way (shader / pattern fills, light, inner effects,
    blur, special blends, clipped or styled layers, images, arc text) is embedded as a picture of just that
    element, so the SVG still looks like the PNG. The result lists which ids stayed vector.
    Stripes / dots / grid fills and rect side strokes stay vector too. image_scale (1-8, default 2) sets how
    sharp those embedded pictures are: 4 keeps them crisp at 400% zoom or on large prints, at a bigger file.
    """
    from . import svgexport
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, language)
    r = st.renderer(c, 1.0, state=state, language=language)
    svg, report = svgexport.canvas_svg(r, include_background, image_scale)
    out = _out_path(path, f"{c['id']}.svg", suffixes=(".svg",))
    out.write_text(svg, encoding="utf-8")
    result: dict = {"file": str(out), "vector": report["vector"], "embedded_as_image": report["raster"]}
    if report["notes"]:
        result["notes"] = report["notes"]
    if r.warnings:
        result["warnings"] = sorted(set(r.warnings))
    return result


@tool
def export_web(canvases: list[str] | str, out_dir: str | None = None, layout: str = "fit",
               language: str | None = None, include_background: bool = True, image_scale: float = 2):
    """Export canvases as a working website: one HTML page per canvas (the first is index.html), with
    styles.css, app.js and an assets folder - open index.html in a browser or upload the folder.

    Rects and ellipses become CSS boxes (gradients, borders, shadows, blur, backdrop-filter), text stays
    real, selectable text with its fonts copied in, other shapes become inline SVG, and only effects the
    web cannot draw the same way become pictures. Theme colours stay CSS variables (set
    <html data-theme="light"> to switch a mode). Interactivity: set_link targets become page links
    (mode "overlay" opens a page as a dialog, "url" an external link); "hover" / "pressed" / "focused"
    states become CSS; move / rotate / scale / fade animations become CSS keyframes (they autoplay);
    elements with the same id animate between pages (smart animate via View Transitions);
    canvas focus_order sets keyboard order; an element's "fixed": true keeps it in place while scrolling.
    layout: "fit" scales each page to the window like a prototype; "responsive" uses the elements' pins
    (set_pin) as CSS anchors so the page adapts to any window size and scrolls when taller.
    """
    from . import webexport
    st = store()
    names = [canvases] if isinstance(canvases, str) and not canvases.strip().startswith("[") else (_maybe_json(canvases) or [])
    if not names:
        raise ValueError("canvases must name at least one canvas")
    if layout not in ("fit", "responsive"):
        raise ValueError("layout must be 'fit' or 'responsive'")
    pages = [st.get(n) for n in names]
    for c in pages:
        st.require_glyphs(c, language)
    folder = _out_dir(out_dir, f"web/{pages[0]['id']}")
    report = webexport.build(st, pages, folder, layout, language, include_background, image_scale)
    result: dict = {"folder": str(folder), "open": str(folder / "index.html"), "pages": report["pages"],
                    "embedded_as_image": report["picture"]}
    if report["notes"]:
        result["notes"] = report["notes"]
    return result


@tool
def export_react(canvases: list[str] | str, out_dir: str | None = None, language: str | None = None,
                 include_background: bool = True, image_scale: float = 2, css: str = "css",
                 typescript: bool = False):
    """Export canvases as React components (JSX or TypeScript TSX + CSS or Tailwind utilities) for React / Next.js / Vite:
    one <Name>.jsx/.tsx (and <Name>.css) per canvas, uiforge-runtime.js and an assets folder.
    Supports live data bindings (pass data={{hp: 40}} prop), onNavigate(canvasId, mode), onSfx(name),
    keyboard + gamepad focus navigation, hover / pressed CSS, keyframe animations and set_interaction rules.
    css: "css" (default stylesheet per component) or "tailwind" (Tailwind utility classes on elements).
    typescript: true emits typed .tsx components with <Name>Props interfaces and index.ts."""
    from . import webexport
    st = store()
    names = [canvases] if isinstance(canvases, str) and not canvases.strip().startswith("[") else (_maybe_json(canvases) or [])
    if not names:
        raise ValueError("canvases must name at least one canvas")
    css_mode = str(css or "css").lower()
    if css_mode not in ("css", "tailwind"):
        raise ValueError("css must be 'css' or 'tailwind'")
    pages = [st.get(n) for n in names]
    for c in pages:
        st.require_glyphs(c, language)
    folder = _out_dir(out_dir, f"react/{pages[0]['id']}")
    report = webexport.build_react(st, pages, folder, language, include_background, image_scale,
                                   css_mode=css_mode, typescript=bool(typescript))
    stem = Path(report["components"][0]).stem
    result: dict = {"folder": str(folder), "components": report["components"],
                    "embedded_as_image": report["picture"], "css": css_mode, "typescript": bool(typescript),
                    "usage": f"import {stem} from './{folder.name}/{stem}';"}
    if report["notes"]:
        result["notes"] = report["notes"]
    return result


@tool
def export_pdf(canvases: list[str] | str, path: str | None = None, include_background: bool = True,
               image_scale: float = 2, language: str | None = None, state: str | None = None):
    """Save one or more canvases as a vector PDF (one page each): print, client review, a kit book.

    Shapes, booleans, lines and text are real vectors (text as glyph outlines, so the PDF needs no fonts),
    with solid and linear / radial gradient fills and exact strokes; shadows and glows sit underneath as a
    picture. Effects PDF cannot show the same way (shader / pattern fills, light, inner effects, blur,
    glass, special blends, styled layers, images, colour emoji) are embedded as a picture of that element,
    at image_scale (2 = crisp at 200%; 4 for large prints). The result lists which ids stayed vector.
    """
    from . import pdfexport
    st = store()
    names = [canvases] if isinstance(canvases, str) and not canvases.strip().startswith("[") else (_maybe_json(canvases) or [])
    if not names:
        raise ValueError("canvases must name at least one canvas")
    renderers = []
    for name in names:
        c = st.get(name)
        st.require_glyphs(c, language)
        renderers.append(st.renderer(c, 1.0, state=state, language=language))
    data, report = pdfexport.canvases_pdf(renderers, include_background, image_scale)
    out = _out_path(path, f"{renderers[0].canvas['id']}.pdf", suffixes=(".pdf",))
    out.write_bytes(data)
    result: dict = {"file": str(out), "pages": len(renderers), "vector": report["vector"],
                    "embedded_as_image": report["raster"]}
    warnings = sorted({w for r in renderers for w in r.warnings})
    if warnings:
        result["warnings"] = warnings
    return result


@tool
def export_png(canvas: str, path: str | None = None, scales: list[float] | None = None, trim: bool = False,
               padding: int = 0, include_background: bool = False, ids: list[str] | None = None,
               group: str | None = None, format: str = "png", state: str | None = None,
               language: str | None = None, sizes: list[int] | None = None, preset: str | None = None):
    """Save a canvas as PNG (transparent unless include_background=true).

    path: file path ending in .png; relative paths go to the workspace "exports" folder
    (default "<canvas>.png"). scales: e.g. [1, 2] also writes "<name>_2x.png".
    trim crops transparent margins (padding keeps a few px). ids / group export only those elements,
    e.g. one layer of a mockup. For engine-ready assets with 9-slice data use export_asset instead.
    format: "png", "webp" (lossless), "jpg" (needs include_background or gets a black matte) or "ico"
      (Windows app / launcher icon; `sizes` default [16, 24, 32, 48, 64, 128, 256]).
    sizes: for square icons, exact pixel sizes instead of scales, e.g. [16, 32, 64, 128, 512, 1024]
      (store / app icon sets): writes <name>_<size>.png each, rendered sharp at that size.
    state / language: export an interaction state or a translated version.
    preset: a whole density set in one call, like Figma's export presets - "ios" (name, name@2x, name@3x),
      "web" (name, name@2x), "android" (drawable-mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi folders, 1x to 4x; the
      file name is made lowercase with underscores as Android requires). Overrides scales.
    """
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, language)
    fmt = str(format).lower().lstrip(".")
    if fmt == "png" and path and Path(path).suffix.lower() in (".webp", ".jpg", ".jpeg", ".ico"):
        fmt = Path(path).suffix.lower().lstrip(".")
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in ("png", "webp", "jpg", "ico"):
        raise ValueError("format must be png, webp, jpg or ico")
    base = _out_path(path, f"{c['id']}.{fmt}", suffixes=(".png", ".webp", ".jpg", ".jpeg", ".ico"))
    base = base.with_suffix("." + fmt)
    files = []
    warnings: list[str] = []
    if fmt == "ico":
        icon_sizes = [int(v) for v in (_maybe_json(sizes) or [16, 24, 32, 48, 64, 128, 256]) if 8 <= int(v) <= 256]
        if not icon_sizes:
            raise ValueError("ico sizes must be between 8 and 256")
        frames = []
        for size in icon_sizes:
            img, warn = _render_export(c, size / max(c["width"], c["height"]), include_background, ids, group,
                                       state, language)
            warnings += warn
            sq = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
            sq.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
            frames.append(sq)
        out = base.with_suffix(".ico")
        frames[-1].save(out, format="ICO", sizes=[(f.width, f.height) for f in frames], append_images=frames[:-1])
        result: dict = {"files": [{"file": str(out), "sizes": icon_sizes}]}
        if warnings:
            result["warnings"] = sorted(set(warnings))
        return result
    jobs = []
    if preset:
        key = str(preset).lower()
        if key in ("ios", "web"):
            factors = (1, 2, 3) if key == "ios" else (1, 2)
            jobs = [(float(f), "" if f == 1 else f"@{f}x") for f in factors]
        elif key == "android":
            name = slugify(base.stem, "asset").replace("-", "_")
            for folder, f in (("mdpi", 1), ("hdpi", 1.5), ("xhdpi", 2), ("xxhdpi", 3), ("xxxhdpi", 4)):
                target = base.parent / f"drawable-{folder}" / f"{name}.{fmt}"
                target.parent.mkdir(parents=True, exist_ok=True)
                jobs.append((float(f), target))
        else:
            raise ValueError("preset must be 'ios', 'android' or 'web'")
    elif sizes:
        for size in _maybe_json(sizes):
            jobs.append((int(size) / max(c["width"], c["height"]), f"_{int(size)}"))
    else:
        jobs = [(float(v), None) for v in (scales or [1])]
    for scale, suffix in jobs:
        if not 0.01 <= scale <= 16:
            raise ValueError("scale must be between 0.01 and 16 (check sizes)")
        img, warn = _render_export(c, scale, include_background, ids, group, state, language)
        warnings += warn
        offset = (0, 0)
        if trim:
            img, offset = ex.trim(img, int(round(padding * scale)))
        if isinstance(suffix, Path):
            out = suffix
        else:
            out = base.with_name(base.stem + (suffix if suffix is not None else _scale_suffix(scale)) + "." + fmt)
        _save_image(img, out, fmt)
        files.append({"file": str(out), "scale": round(scale, 4), "width": img.width, "height": img.height,
                      "trim_offset": list(offset)})
    result: dict = {"files": files}
    if warnings:
        result["warnings"] = sorted(set(warnings))
    return result


def _save_image(img, out: Path, fmt: str) -> None:
    if fmt == "jpg":
        flat = PILImage.new("RGB", img.size, (0, 0, 0))
        flat.paste(img, mask=img.getchannel("A"))
        flat.save(out, quality=92)
    elif fmt == "webp":
        img.save(out, lossless=True)
    else:
        img.save(out)


def _layer_units(r, merge_clipped: bool) -> list[dict]:
    """Group the layer stack into export units: a base layer plus (optionally) the layers clipped to it."""
    items = r.stack()
    units = []
    i = 0
    while i < len(items):
        layer, elements = items[i]
        j = i + 1
        children = []
        while j < len(items) and items[j][0] is not None and items[j][0].get("clip"):
            children.append(items[j])
            j += 1
        units.append({"layer": layer, "elements": elements, "children": children if merge_clipped else []})
        if not merge_clipped:
            for child in children:
                units.append({"layer": child[0], "elements": child[1], "children": [], "clip_base": (layer, elements)})
        i = j
    return units


@tool
def export_layers(canvas: str, out_dir: str | None = None, name: str | None = None, by: str = "auto",
                  layers: list[str] | None = None, groups: list[str] | None = None,
                  scales: list[float] | None = None, trim: bool = True, padding: int = 2,
                  merge_clipped: bool = True, format: str = "png"):
    """Export a canvas in pieces: one image per layer (or per element group) plus a layout JSON that says
    where each piece sits, so an engine can rebuild the picture and move the parts independently -
    a gauge (dial / needle / value arc), a HUD (each widget), a button (background / shine / label).

    by: "layer" = one image per canvas layer, with its layer style, opacity and clipping applied;
        "group" = one image per element `group` (elements without one go to "base");
        "auto" (default) = "layer" if the canvas has layers, else "group".
    layers / groups: export only these names (default: all, bottom to top).
    merge_clipped (by layer): layers clipped onto a base (shading, highlights) are baked into that base's
      image, since an engine cannot clip or blend them itself. false exports each one separately.
    trim crops every piece to its pixels and records its x, y so it can be placed exactly.
    format: "png" (default), "webp" (lossless), "jpg" (no transparency: each piece gets a black matte -
      only for opaque layers) or "svg" (ONE layered <name>.svg: every piece is a named layer group that
      Figma, Illustrator and Inkscape open as separate layers; pixels are embedded PNG at the largest
      scale, not editable vector paths).
    out_dir: any folder (absolute, or relative to the workspace exports folder); created if missing.
    Writes "<name>_<piece>.<format>" (or "<name>.svg") and "<name>.layout.json":
      {"canvas": {"width", "height"}, "layers": [{"name", "file", "x", "y", "width", "height", "order",
        "blend", "merged", "origin"}]}   (canvas units at 1x; "origin" = rotation pivot of the part).
    For a fully editable stack in an image editor use export_psd.
    """
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, None)
    mode = by.lower()
    if mode not in ("auto", "layer", "group"):
        raise ValueError("by must be 'auto', 'layer' or 'group'")
    if mode == "auto":
        mode = "layer" if c.get("layers") else "group"
    fmt = format.lower().lstrip(".").replace("jpeg", "jpg")
    if fmt not in ("png", "webp", "jpg", "svg"):
        raise ValueError("format must be png, webp, jpg or svg")
    folder = _out_dir(out_dir, "layers")
    base = slugify(name or c["id"], "layers")
    scale_list = [float(v) for v in (scales or [1])]
    for scale in scale_list:
        if not 0.1 <= scale <= 8:
            raise ValueError("scale must be between 0.1 and 8")
    warnings: list[str] = []
    notes: list[str] = []
    pieces: list[dict] = []

    if mode == "group":
        order: list[str] = []
        members: dict[str, list[dict]] = {}
        for el in c["elements"]:
            if not el.get("visible", True):
                continue
            key = el.get("group") or "base"
            if key not in members:
                members[key] = []
                order.append(key)
            members[key].append(el)
        wanted = groups or order
        for g in wanted:
            if g not in members:
                raise ValueError(f"No visible elements in group '{g}'. Groups: {', '.join(order) or '(none)'}")
        for g in wanted:
            ids = {e["id"] for e in members[g]}

            def render_group(scale: float, ids=ids):
                r = st.renderer(c, scale)
                img = r.render(include_background=False, only=ids)
                warnings.extend(r.warnings)
                return img

            pivots = [e["origin"] for e in members[g] if e.get("origin")]
            pieces.append({"name": g, "render": render_group,
                           "meta": {"order": order.index(g), "elements": sorted(ids),
                                    **({"origin": pivots[0]} if pivots else {})}})
    else:
        probe = st.renderer(c, 1.0)
        units = _layer_units(probe, merge_clipped)
        names = [(u["layer"]["name"] if u["layer"] else "base") for u in units]
        wanted_layers = None
        if layers:
            wanted_layers = {"base" if str(n).strip().lower() == "base" else st.get_layer(c, n)["name"] for n in layers}
        for index, unit in enumerate(units):
            layer = unit["layer"]
            lname = layer["name"] if layer else "base"
            if wanted_layers is not None and lname not in wanted_layers:
                continue
            props = probe.layer_props(layer) if layer else {"blend": "normal", "visible": True, "clip": False}
            if not props["visible"]:
                notes.append(f"layer '{lname}' is hidden and was skipped")
                continue
            if not unit["elements"] and not unit["children"]:
                continue

            def render_unit(scale: float, unit=unit):
                r = st.renderer(c, scale)
                clip_alpha = None
                if unit.get("clip_base"):
                    _, clip_alpha = r.layer_image(*unit["clip_base"])
                final, alpha = r.layer_image(unit["layer"], unit["elements"], clip_alpha)
                for child_layer, child_elements in unit["children"]:
                    child_props = r.layer_props(child_layer)
                    if not child_props["visible"]:
                        continue
                    piece, _ = r.layer_image(child_layer, child_elements, alpha)
                    _composite(final, piece, 0, 0, child_props["blend"])
                warnings.extend(r.warnings)
                return final

            meta: dict = {"order": index, "elements": sorted(e["id"] for e in unit["elements"])}
            if props["blend"] != "normal":
                meta["blend"] = props["blend"]
                notes.append(f"layer '{lname}' uses blend '{props['blend']}': a plain image in an engine draws as "
                             "normal. Bake it (clip it onto its base, or merge the layers) or use a material.")
            if unit["children"]:
                meta["merged"] = [child[0]["name"] for child in unit["children"]]
            pivots = [e["origin"] for e in unit["elements"] if e.get("origin")]
            if pivots:
                meta["origin"] = pivots[0]
            pieces.append({"name": lname, "render": render_unit, "meta": meta})
        if not pieces:
            raise ValueError(f"Nothing to export. Layers: {', '.join(names) or '(none)'}")

    if fmt == "svg":
        scale_list = [max(scale_list)]
    svg_parts: list[str] = []
    out_layers = []
    for piece in pieces:
        entry: dict = {"name": piece["name"], **piece["meta"]}
        files = []
        for scale in scale_list:
            img = piece["render"](scale)
            offset = (0, 0)
            if trim:
                img, offset = ex.trim(img, int(round(padding * scale)))
            if fmt == "svg":
                lid = slugify(piece["name"], "layer")
                svg_parts.append(ex.svg_layer(lid, piece["name"], img, offset[0] / scale, offset[1] / scale,
                                              img.width / scale, img.height / scale))
                filename = f"{base}.svg"
            else:
                filename = f"{base}_{slugify(piece['name'], 'layer')}{_scale_suffix(scale)}.{fmt}"
                _save_image(img, folder / filename, fmt)
            files.append({"file": filename, "scale": scale, "pixel_width": img.width, "pixel_height": img.height})
            if scale == scale_list[0]:
                entry.update(file=filename, x=_round(offset[0] / scale), y=_round(offset[1] / scale),
                             width=_round(img.width / scale), height=_round(img.height / scale))
        entry["files"] = files
        out_layers.append(entry)
    if fmt == "svg":
        (folder / f"{base}.svg").write_text(ex.svg_document(c["width"], c["height"], svg_parts), encoding="utf-8")
    if fmt == "jpg":
        notes.append("jpg has no transparency: every piece was flattened on black. Use png/webp for overlay layers.")
    layout = {"canvas": {"name": c["id"], "width": c["width"], "height": c["height"]}, "split_by": mode,
              "layers": out_layers}
    layout_path = folder / f"{base}.layout.json"
    ex.write_json(layout_path, layout)
    result: dict = {"folder": str(folder), "layout": str(layout_path), "split_by": mode,
                    "layers": [{k: v for k, v in layer.items() if k != "elements"} for layer in out_layers]}
    if notes:
        result["notes"] = sorted(set(notes))
    if warnings:
        result["warnings"] = sorted(set(warnings))
    return result


@tool
def export_psd(canvas: str, path: str | None = None, scale: float = 1, include_background: bool = True):
    """Save the canvas as a layered Photoshop file (.psd): every canvas layer becomes a PSD layer with its
    name, opacity, blend mode, visibility and clipping kept, so the stack stays editable in Photoshop,
    Photopea, Krita, GIMP or Affinity. Elements on a layer are flattened into that layer's pixels and
    layer styles (shadow, stroke, light...) are baked in. Elements outside any layer go to a "base" layer;
    the canvas background becomes a "background" layer.

    scale: resolution multiplier (2 = double size). path: relative paths go to the workspace exports folder.
    """
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, None)
    scale = float(scale)
    if not 0.1 <= scale <= 8:
        raise ValueError("scale must be between 0.1 and 8")
    out = Path(path).expanduser() if path else st.exports_dir / f"{c['id']}.psd"
    if not out.is_absolute():
        out = st.exports_dir / out
    if out.suffix.lower() != ".psd":
        raise ValueError("Output file must end with .psd")
    out.parent.mkdir(parents=True, exist_ok=True)
    r = st.renderer(c, scale)
    stack_layers: list[dict] = []
    if include_background and c.get("background"):
        bg_only = dict(c, elements=[], layers=[])
        stack_layers.append({"name": "background", "image": st.renderer(bg_only, scale).render(), "opacity": 1,
                             "blend": "normal", "clip": False, "visible": True})
    has_base = False
    psd_notes: list[str] = []
    for layer, elements in r.stack():
        props = r.layer_props(layer) if layer else {"name": "base", "opacity": 1.0, "blend": "normal", "clip": False,
                                                     "visible": True}
        image, _ = r.layer_image(layer, elements, None, bake_opacity=False)
        visible = props["visible"]
        if props["blend"] == "erase":
            visible = False
            psd_notes.append(f"layer '{props['name']}' uses blend 'erase', which PSD cannot store: it is saved hidden "
                             "(use it as a layer mask in your editor). The merged preview inside the PSD is correct.")
        stack_layers.append({"name": props["name"], "image": image, "opacity": props["opacity"],
                             "blend": "normal" if props["blend"] == "erase" else props["blend"],
                             "clip": props["clip"] and has_base, "visible": visible})
        has_base = True
    if not stack_layers:
        raise ValueError("The canvas is empty - add elements (or make hidden layers visible) before exporting")
    merged = r.render(include_background=include_background)
    psd_mod.write_psd(out, r.width, r.height, stack_layers, merged)
    result: dict = {"file": str(out), "size": [r.width, r.height],
                    "layers_bottom_to_top": [{"name": l["name"], "blend": l["blend"], "opacity": l["opacity"],
                                              **({"clip": True} if l["clip"] else {}),
                                              **({} if l["visible"] else {"visible": False})} for l in stack_layers]}
    if r.warnings:
        result["warnings"] = sorted(set(r.warnings))
    if psd_notes:
        result["notes"] = psd_notes
    return result


@tool
def export_asset(canvas: str, engine: str = "generic", out_dir: str | None = None, name: str | None = None,
                 nine_slice: str | dict | None = None, minimize: bool = True, scales: list[float] | None = None,
                 trim: bool = False, padding: int = 0, states: list[str] | str | None = None,
                 language: str | None = None):
    """Export a canvas as an engine-ready UI asset: PNG + "<name>.uiforge.json" metadata + manifest entry.

    engine: "unity", "unreal", "roblox", "godot" or "generic" (metadata for all of them).
    out_dir: target folder, e.g. "<UnityProject>/Assets/UI/Generated"; default is the workspace exports folder.
    nine_slice: omit for fixed-size images (icons, logos). "auto" detects the stretchable centre, or give
      {"left": 24, "top": 24, "right": 24, "bottom": 24} in canvas px. Use it for panels, buttons, bars,
      tooltips - anything the engine should resize without distorting corners.
    minimize: shrink the stretchable centre to a few px so the texture stays tiny (9-slice only).
    The result contains the exact numbers per engine: Unity sprite border (L,B,R,T), Unreal brush
    Margin (L,T,R,B as fractions), Roblox SliceCenter, Godot patch / texture margins (L,T,R,B px). Run write_engine_helpers once per project folder
    to get the import scripts that apply them automatically.
    states: interaction states to export too ("all" = every state set with set_state). Each becomes
      "<name>_<state>.png" with the same size and 9-slice borders, and the metadata maps them to the
      engine's slots: Unity Button SpriteState (hover -> highlighted, pressed, selected/focused, disabled),
      Godot TextureButton textures, Roblox ImageButton HoverImage / PressedImage.
    language: export a translated version (string tables, see set_strings).
    """
    st = store()
    c = st.get(canvas)
    st.require_glyphs(c, language)
    wanted_states = _maybe_json(states)
    if wanted_states == "all":
        wanted_states = sorted(c.get("states") or {})
    elif isinstance(wanted_states, str):
        wanted_states = [wanted_states]
    for sname in wanted_states or []:
        if sname not in (c.get("states") or {}):
            raise ValueError(f"no state '{sname}' on '{c['id']}'. States: {', '.join(sorted(c.get('states') or {})) or '(none)'}")
    engine = engine.lower()
    if engine not in ex.ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ex.ENGINES)}")
    folder = _out_dir(out_dir, engine)
    asset = slugify(name or c["id"], "asset")
    nine = _maybe_json(nine_slice)
    files = []
    notes: list[str] = []
    warnings: list[str] = []
    for scale in (scales or [1]):
        scale = float(scale)
        if not 0.1 <= scale <= 8:
            raise ValueError("scale must be between 0.1 and 8")
        img, warn = _render_export(c, scale, False, None, None, None, language)
        warnings += warn
        offset = (0, 0)
        state_imgs = []
        for sname in wanted_states or []:
            simg, warn = _render_export(c, scale, False, None, None, sname, language)
            warnings += warn
            state_imgs.append((sname, simg))
        if trim:
            img, offset = ex.trim(img, int(round(padding * scale)))
            box = (offset[0], offset[1], offset[0] + img.width, offset[1] + img.height)
            state_imgs = [(n, si.crop(box)) for n, si in state_imgs]
        borders = None
        if nine:
            if isinstance(nine, str):
                if nine.lower() != "auto":
                    raise ValueError("nine_slice must be 'auto' or an object with left/top/right/bottom")
                centre = ((offset[0] + img.width / 2) / scale, (offset[1] + img.height / 2) / scale)
                block_x, block_y = _gradient_blocks(c, centre)
                borders = ex.detect_nine_slice(img, block_x=block_x, block_y=block_y)
                if not borders["stretch_x"] and not borders["stretch_y"]:
                    note = ("auto 9-slice found no stretchable area: the centre is not uniform (gradient, pattern, "
                            "noise, or content such as text/icons in the middle). Keep the centre flat, or pass "
                            "explicit borders.")
                    if note not in notes:
                        notes.append(note)
                elif not borders["stretch_x"] or not borders["stretch_y"]:
                    axis = "horizontally" if borders["stretch_x"] else "vertically"
                    note = (f"asset only stretches {axis}; the other axis is not uniform (a gradient or content "
                            "runs along it). That is fine for fixed-height buttons/bars; use a flat fill if it "
                            "must stretch both ways.")
                    if note not in notes:
                        notes.append(note)
            else:
                try:
                    base = {k: float(nine[k]) for k in ("left", "top", "right", "bottom")}
                except (KeyError, TypeError) as exc:
                    raise ValueError("nine_slice object needs left, top, right and bottom") from exc
                borders = ex.scale_borders(base, scale)
                borders.update(stretch_x=True, stretch_y=True)
                if borders["left"] + borders["right"] >= img.width or borders["top"] + borders["bottom"] >= img.height:
                    raise ValueError("nine_slice borders are larger than the image")
            if minimize:
                full_borders = dict(borders)
                img, borders = ex.minimize_nine_slice(img, full_borders)
                state_imgs = [(n, ex.minimize_nine_slice(si, full_borders)[0]) for n, si in state_imgs]
        filename = asset + _scale_suffix(scale) + ".png"
        img.save(folder / filename)
        state_files = {}
        for sname, simg in state_imgs:
            sfile = f"{asset}_{sname}{_scale_suffix(scale)}.png"
            simg.save(folder / sfile)
            state_files[sname] = sfile
        meta = ex.engine_metadata(engine, img.size, borders, scale)
        if state_files:
            meta.update(ex.state_metadata(engine, filename, state_files))
        entry = {"file": filename, "scale": scale, "width": img.width, "height": img.height, **meta}
        if state_files:
            entry["states"] = state_files
        sidecar: dict = {"name": asset, "file": filename, "width": img.width, "height": img.height, "scale": scale,
                         "has_border": bool(borders), "pixels_per_unit": 100 * scale,
                         "border_left": 0, "border_bottom": 0, "border_right": 0, "border_top": 0}
        if borders:
            entry["nine_slice"] = {k: borders[k] for k in ("left", "top", "right", "bottom")}
            sidecar.update(border_left=borders["left"], border_bottom=borders["bottom"],
                           border_right=borders["right"], border_top=borders["top"])
        sidecar.update(meta)
        ex.write_json(folder / (Path(filename).stem + ".uiforge.json"), sidecar)
        files.append(entry)
        rb_warn = meta.get("roblox", {}).get("warning")
        if rb_warn and engine in ("roblox",):
            notes.append(rb_warn)
    manifest = folder / "uiforge_manifest.json"
    previous = {}
    if manifest.is_file():
        try:
            previous = json.loads(manifest.read_text(encoding="utf-8")).get("assets", {}).get(asset, {})
        except Exception:
            previous = {}
    record: dict = {"canvas": c["id"], "files": files}
    if previous.get("roblox_id"):
        record["roblox_id"] = previous["roblox_id"]
    if wanted_states:
        record["states"] = {sname: f"{asset}_{sname}" for sname in wanted_states}
    ex.update_manifest(folder, asset, record)
    for sname in wanted_states or []:
        sname_asset = f"{asset}_{sname}"
        try:
            prev_s = json.loads(manifest.read_text(encoding="utf-8")).get("assets", {}).get(sname_asset, {})
        except Exception:
            prev_s = {}
        srec: dict = {"canvas": c["id"], "state_of": asset,
                      "files": [{**{k: v for k, v in f.items() if k not in ("states", "file", "state_slots")},
                                 "file": f["states"][sname]} for f in files]}
        if prev_s.get("roblox_id"):
            srec["roblox_id"] = prev_s["roblox_id"]
        ex.update_manifest(folder, sname_asset, srec)
    result: dict = {"asset": asset, "folder": str(folder), "files": files, "manifest": str(manifest)}
    if notes:
        result["notes"] = notes
    if warnings:
        result["warnings"] = sorted(set(warnings))
    return result


@tool
def export_atlas(canvases: list[str], path: str | None = None, scale: float = 1, padding: int = 2,
                 power_of_two: bool = False, max_size: int = 4096, trim: bool = False,
                 format: str = "json", godot_res_path: str = "res://ui/generated"):
    """Pack several canvases into one atlas PNG + metadata (icon sets, small HUD pieces).
    One atlas = one upload on Roblox (ImageRectOffset / ImageRectSize) and one draw call elsewhere.
    format:
      "json"          default {"image", "size", "scale", "frames": {canvas: {x, y, w, h}}}.
      "texturepacker" standard TexturePacker JSON Hash (Phaser, PixiJS, Cocos, Spine, Defold, GameMaker).
      "godot"         writes Godot 4 AtlasTexture <id>.atlas.tres files alongside the packed PNG.
      "unity"         writes Unity bottom-left sprite rects JSON for Multiple-Sprite slicing.
      "css"           writes <name>.css sprite classes (.sprite-<id>) for web icons.
    """
    st = store()
    fmt = str(format or "json").lower()
    if fmt not in ("json", "texturepacker", "godot", "unity", "css"):
        raise ValueError("format must be 'json', 'texturepacker', 'godot', 'unity' or 'css'")
    images = []
    warnings: list[str] = []
    for cid in canvases:
        c = st.get(cid)
        st.require_glyphs(c, None)
        img, warn = _render_export(c, float(scale), False, None, None)
        warnings += warn
        if trim:
            img, _ = ex.trim(img)
        images.append((c["id"], img))
    atlas, frames = ex.pack_atlas(images, int(padding), int(max_size), power_of_two)
    out = _out_path(path, "atlas.png")
    atlas.save(out)
    extras: list[str] = []
    if fmt == "texturepacker":
        tp = {
            "frames": {
                f"{k}.png": {"frame": f, "rotated": False, "trimmed": bool(trim),
                             "spriteSourceSize": {"x": 0, "y": 0, "w": f["w"], "h": f["h"]},
                             "sourceSize": {"w": f["w"], "h": f["h"]}}
                for k, f in frames.items()
            },
            "meta": {"app": "uiforge-mcp", "version": "0.12.0", "image": out.name, "format": "RGBA8888",
                     "size": {"w": atlas.width, "h": atlas.height}, "scale": str(scale)},
        }
        ex.write_json(out.with_suffix(".json"), tp)
    elif fmt == "unity":
        u_sprites = [{"name": k, "rect": {"x": f["x"], "y": atlas.height - f["y"] - f["h"],
                                          "width": f["w"], "height": f["h"]}, "pivot": {"x": 0.5, "y": 0.5}}
                     for k, f in frames.items()]
        ex.write_json(out.with_suffix(".json"), {"image": out.name, "size": {"w": atlas.width, "h": atlas.height},
                                                 "scale": scale, "unity_sprites": u_sprites, "frames": frames})
    else:
        data = {"image": out.name, "size": {"w": atlas.width, "h": atlas.height}, "scale": scale, "frames": frames}
        ex.write_json(out.with_suffix(".json"), data)
    if fmt == "godot":
        if not re.fullmatch(r"res://[A-Za-z0-9_\-/.]*", godot_res_path or "") or ".." in godot_res_path:
            raise ValueError("godot_res_path must be a res:// path without '..'")
        res_base = godot_res_path.rstrip("/")
        for k, f in frames.items():
            tfile = out.parent / f"{k}.atlas.tres"
            tfile.write_text(
                '[gd_resource type="AtlasTexture" load_steps=2 format=3]\n\n'
                f'[ext_resource type="Texture2D" path="{res_base}/{out.name}" id="1_atlas"]\n\n'
                '[resource]\n'
                'atlas = ExtResource("1_atlas")\n'
                f'region = Rect2({f["x"]}, {f["y"]}, {f["w"]}, {f["h"]})\n',
                encoding="utf-8",
            )
            extras.append(tfile.name)
    elif fmt == "css":
        css_lines = [f".sprite{{display:inline-block;background-image:url('{out.name}');background-repeat:no-repeat;}}"]
        for k, f in frames.items():
            css_lines.append(f".sprite-{slugify(k, 'icon')}{{width:{f['w']}px;height:{f['h']}px;background-position:-{f['x']}px -{f['y']}px;}}")
        cfile = out.with_suffix(".css")
        cfile.write_text("\n".join(css_lines) + "\n", encoding="utf-8")
        extras.append(cfile.name)
    result: dict = {"file": str(out), "json": str(out.with_suffix(".json")), "format": fmt,
                    "size": [atlas.width, atlas.height], "frames": frames}
    if extras:
        result["extras"] = extras
    if max(atlas.size) > ex.ROBLOX_MAX:
        result["note"] = f"larger than {ex.ROBLOX_MAX}px: Roblox would downscale it. Split it or lower the scale for Roblox."
    if warnings:
        result["warnings"] = sorted(set(warnings))
    return result


@tool
def write_engine_helpers(engine: str, out_dir: str, roblox_ids: dict | None = None,
                         unreal_content_path: str = "/Game/UI/Generated", godot_res_path: str = "res://ui/generated"):
    """Write the engine-side helper that applies exported metadata automatically.

    unity:  UiForgeImporter.cs - out_dir must be an "Editor" folder inside Assets. It imports every PNG that
            has a .uiforge.json next to it as a UI sprite with the 9-slice border set.
    unreal: import_uiforge.py - written into out_dir (the folder that holds uiforge_manifest.json). Run it in
            the editor's Python console to import textures with UI settings; it logs each brush Margin.
    roblox: UiForgeAssets.luau - a ModuleScript built from uiforge_manifest.json in out_dir, with
            UiForge.apply(imageLabel, "asset_name"). After uploading the PNGs in Studio pass
            roblox_ids={"asset_name": 1234567890} to fill in the asset ids.
    godot:  one <asset>.stylebox.tres (StyleBoxTexture with texture margins) per 9-sliced asset in out_dir;
            godot_res_path is where that folder lives inside the Godot project.
    """
    engine = engine.lower()
    if not re.fullmatch(r"/[A-Za-z0-9_/]+", unreal_content_path or ""):
        raise ValueError("unreal_content_path must be a content path like /Game/UI/Generated "
                         "(letters, digits, _ and / only)")
    if not re.fullmatch(r"res://[A-Za-z0-9_\-/.]*", godot_res_path or "") or ".." in godot_res_path:
        raise ValueError("godot_res_path must be a resource path like res://ui/generated "
                         "(letters, digits, _ - . / only, no '..')")
    folder = Path(out_dir).expanduser()
    if not folder.is_absolute():
        folder = store().exports_dir / folder
    folder.mkdir(parents=True, exist_ok=True)
    if engine == "unity":
        if folder.name != "Editor" and "Editor" not in folder.parts:
            raise ValueError("For Unity, out_dir must be (inside) a folder named 'Editor', e.g. <Project>/Assets/Editor")
        target = folder / "UiForgeImporter.cs"
        target.write_text(engines.UNITY_IMPORTER, encoding="utf-8")
        return {"file": str(target), "next": "Unity compiles it automatically. Export assets with export_asset into "
                                             "any Assets folder; each PNG with a .uiforge.json is set up on import."}
    manifest_path = folder / "uiforge_manifest.json"
    if engine == "unreal":
        target = folder / "import_uiforge.py"
        target.write_text(engines.UNREAL_IMPORT.replace("__DEST_PATH__", unreal_content_path), encoding="utf-8")
        note = "" if manifest_path.is_file() else " (no uiforge_manifest.json here yet - export_asset into this folder first)"
        return {"file": str(target), "next": f'In Unreal: Output Log -> Python ->  py "{target.as_posix()}"{note}'}
    if engine == "roblox":
        if not manifest_path.is_file():
            raise ValueError(f"No uiforge_manifest.json in {folder}. Run export_asset(engine='roblox', out_dir=...) first.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for asset, asset_id in (_maybe_json(roblox_ids) or {}).items():
            key = slugify(asset, "asset")
            if key not in manifest.get("assets", {}):
                raise ValueError(f"roblox_ids: asset '{asset}' is not in the manifest ({', '.join(sorted(manifest['assets']))})")
            rid = str(asset_id).strip().removeprefix("rbxassetid://")
            if not rid.isdigit() or not rid.isascii():
                raise ValueError(f"roblox_ids: '{asset}' must be a numeric asset id like 1234567890, got {asset_id!r}")
            manifest["assets"][key]["roblox_id"] = rid
        ex.write_json(manifest_path, manifest)
        target = folder / "UiForgeAssets.luau"
        target.write_text(engines.roblox_module(manifest), encoding="utf-8")
        missing = [a for a, e in manifest["assets"].items() if not e.get("roblox_id")]
        return {"file": str(target), "assets_without_id": missing,
                "next": "Upload the PNGs in Roblox Studio, then call this again with roblox_ids to fill them in."}
    if engine == "godot":
        if not manifest_path.is_file():
            raise ValueError(f"No uiforge_manifest.json in {folder}. Run export_asset(engine='godot', out_dir=...) first.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        written = []
        for fname, text in engines.godot_styleboxes(manifest, godot_res_path).items():
            (folder / fname).write_text(text, encoding="utf-8")
            written.append(fname)
        return {"folder": str(folder), "files": written,
                "next": (f"Put this folder at {godot_res_path} in the Godot project. Each .stylebox.tres is a "
                         "StyleBoxTexture with the 9-slice margins set: assign it to a Panel/Button theme override. "
                         "For a NinePatchRect use the margins_LTRB numbers from the .uiforge.json files.")
                if written else "No 9-sliced assets in the manifest; plain PNGs need no helper in Godot."}
    raise ValueError("engine must be 'unity', 'unreal', 'roblox' or 'godot'")


from .tools_workflow import *  # noqa: E402,F401,F403  (registers the workflow tools)
from .tools_delivery import *  # noqa: E402,F401,F403  (registers the hand-off tools)
from .tools_design import *  # noqa: E402,F401,F403  (registers guide, palettes, restyle, path ops)


def _register_mcp_dx() -> None:
    """Register native MCP resources and workflow prompts for zero-guesswork AI discovery."""
    if hasattr(mcp, "resource"):
        @mcp.resource("uiforge://materials")
        def res_materials() -> str:
            """All 39 built-in Cook-Torrance PBR material names plus any custom theme materials."""
            from .materials import NAMES
            custom = sorted((store().theme.get("materials") or {}).keys())
            return json.dumps({"builtin": NAMES, "custom": custom}, indent=2)

        @mcp.resource("uiforge://workspace")
        def res_workspace() -> str:
            """Live summary of canvases, theme tokens and workspace directory."""
            st = store()
            return json.dumps({
                "workspace": str(st.workspace),
                "rev": st.rev,
                "canvases": [{"id": c["id"], "width": c["width"], "height": c["height"],
                              "elements": len(c["elements"])} for c in st.canvases.values()],
                "theme_colors": sorted((st.theme.get("colors") or {}).keys()),
                "theme_styles": sorted((st.theme.get("styles") or {}).keys()),
            }, indent=2)

        @mcp.resource("uiforge://guide/{topic}")
        def res_guide(topic: str) -> str:
            """Reference manual for one uiforge-mcp topic (fills, shader, style, design, layers, geometry, text, reuse, review, animation, export, all)."""
            from .reference import TOPICS
            t = str(topic).strip().lower()
            if t == "all":
                return "\n\n".join(f"=== {k} ===\n{v}" for k, v in TOPICS.items() if k != "index")
            return TOPICS.get(t, TOPICS["index"])

    if hasattr(mcp, "prompt"):
        @mcp.prompt()
        def design_game_hud(genre: str = "sci-fi shooter", engine: str = "unity", resolution: str = "1920x1080") -> str:
            """Step-by-step workflow prompt to design, review, bind and export a production game HUD."""
            return (
                f"Design an original AAA {genre} HUD at {resolution} for {engine} using uiforge-mcp.\n"
                "1. Call live_preview('start') if the user wants to watch live.\n"
                "2. Set a cohesive token theme with set_theme (1 background, 2 surfaces, 1 primary, 1 accent, semantic states).\n"
                "3. Create the canvas with safe_area, use add_frame (scifi_hud / rpg_gold / cyber_tech) and Cook-Torrance PBR materials inside batch().\n"
                "4. Pin every corner widget with set_pin and wire live stats (hp/ammo/level) via set_binding.\n"
                "5. Inspect with preview(background='game') + preview_resolutions + review_canvas, fix every warning.\n"
                f"6. Export via export_screen(engine='{engine}') (plus export_pbr_maps for dynamic engine lighting)."
            )

        @mcp.prompt()
        def design_rpg_panel(title: str = "Inventory", style_preset: str = "rpg_gold") -> str:
            """Workflow prompt to build a richly shaded ornate RPG modal with PBR materials and states."""
            return (
                f"Create an ornate '{title}' RPG panel using uiforge-mcp.\n"
                "1. Call set_theme with warm medieval/fantasy palette tokens and Cinzel/Inter typography.\n"
                f"2. Build the outer frame with add_frame(preset='{style_preset}', title='{title}') and use its returned inner_box.\n"
                "3. Populate slots with add_instance + variants (common/rare/epic/legendary), faceted gem/ruby/emerald PBR accents, and live auto layout.\n"
                "4. Add hover/pressed/selected states with set_state and click SFX via set_interaction.\n"
                "5. Inspect with preview() and review_canvas(), fix issues, then export PNG + PBR normal/roughness/metallic maps via export_pbr_maps()."
            )

        @mcp.prompt()
        def audit_and_polish(canvas: str) -> str:
            """Closed-loop visual and WCAG quality audit prompt for an existing canvas."""
            return (
                f"Audit and polish canvas '{canvas}' in uiforge-mcp:\n"
                "1. Run review_canvas(canvas) and preview(canvas, show_ids=true).\n"
                "2. Check contrast (WCAG >= 4.5:1 body, 3:1 headings), clipped shadows, half-pixel edges, safe areas, and pseudo-long localization.\n"
                "3. Fix every warning with batch() / update_element(), then re-verify with preview() and review_canvas() until ok=true."
            )


_register_mcp_dx()


def main() -> None:
    from .cli import cli_main
    cli_main()


if __name__ == "__main__":
    main()
