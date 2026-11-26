"""Workflow tools: multi-resolution layouts, interaction states, data templates, localisation,
arranging, scattering, copying, redo and bitmap fonts. Registered on the same MCP server."""

from __future__ import annotations

import copy
import json
import math
import random

from PIL import Image as PILImage
from PIL import ImageDraw

from . import layout as lay
from .render import TextLayout, resolve_style
from .server import (Image, _label_font, _maybe_json, _out_dir, _png_bytes, _prepare_update, _summary,
                     backdrop, store, tool)
from .store import slugify

__all__ = ["set_pin", "resize_canvas", "preview_resolutions", "set_state", "delete_state", "set_strings",
           "get_strings", "generate_from_template", "arrange_elements", "scatter", "copy_elements", "redo",
           "export_bitmap_font"]



@tool
def set_pin(canvas: str, x: str = "left", y: str = "top", ids: list[str] | None = None, group: str | None = None):
    """Pin elements to canvas edges so a screen adapts to other resolutions (resize_canvas,
    preview_resolutions), like anchors in Unity / Godot / UMG.

    x: "left", "center", "right", "stretch" (keeps both side margins: top bars, wide panels) or "scale"
       (moves proportionally). y: "top", "middle", "bottom", "stretch" or "scale".
    Typical HUD: health top-left (left, top), minimap top-right (right, top), hotbar bottom-centre
    (center, bottom), crosshair (center, middle), full-width top bar (stretch, top). Pin every element of a
    widget the same way (use its group) so it moves as one piece.
    """
    st = store()
    c = st.get(canvas)
    if x not in lay.PIN_X:
        raise ValueError(f"x must be one of {', '.join(lay.PIN_X)}")
    if y not in lay.PIN_Y:
        raise ValueError(f"y must be one of {', '.join(lay.PIN_Y)}")
    targets = st.select(c, ids, group)
    st.checkpoint(c)
    for el in targets:
        if x == "left" and y == "top":
            el.pop("pin", None)
        else:
            el["pin"] = {"x": x, "y": y}
    st.save_canvas(c)
    return {"pinned": [e["id"] for e in targets], "pin": {"x": x, "y": y}}


@tool
def resize_canvas(canvas: str, width: int | None = None, height: int | None = None, preset: str | None = None):
    """Change the canvas size and move / stretch every element by its pin (set_pin; default left-top),
    the way the screen will behave in the engine. Use it to adapt a 1920x1080 HUD to 21:9, 16:10 or a
    phone. Undo restores the previous layout. For a look without changing anything use preview_resolutions."""
    st = store()
    c = st.get(canvas)
    safe = None
    if preset:
        pw, ph, safe, _ = lay.preset(preset)
        width, height = width or pw, height or ph
    if not width or not height:
        raise ValueError("give width and height, or a preset")
    r = st.renderer(c)
    st.checkpoint(c)
    try:
        warnings = lay.apply_resize(c, r, int(width), int(height))
        if preset:
            c["device"] = str(preset).lower()
            if safe and any(safe):
                c["safe_area"] = list(safe)
            else:
                c.pop("safe_area", None)
        st.renderer(c, 0.25).render()
    except Exception:
        st.drop_checkpoint(c)
        st.save_canvas(c)
        raise
    st.save_canvas(c)
    out: dict = {"canvas": c["id"], "width": c["width"], "height": c["height"]}
    if warnings:
        out["warnings"] = warnings
    return out


@tool
def preview_resolutions(canvas: str, sizes: list | None = None, cell: int = 480, guides: list[str] | None = None,
                        language: str | None = None):
    """Show the screen at several resolutions side by side, with elements moved by their pins
    (nothing is changed). sizes: [[w, h], ...] and / or preset names; default 16:9, 21:9, 16:10, 4:3
    and a 19.5:9 phone. guides: e.g. ["safe"]. Look for overlaps, elements leaving the screen and
    unreachable corners."""
    st = store()
    c = st.get(canvas)
    wanted = _maybe_json(sizes) or [[1920, 1080], [2560, 1080], [1280, 800], [1440, 1080], "mobile-game-landscape"]
    r = st.renderer(c)
    tiles = []
    warnings: list[str] = []
    for item in wanted:
        safe = None
        if isinstance(item, str):
            w, h, safe, _ = lay.preset(item)
            label = f"{item} {w}x{h}"
        else:
            w, h = int(item[0]), int(item[1])
            label = f"{w}x{h}"
        copy_c, warn = lay.resized_copy(c, r, w, h)
        if safe and any(safe):
            copy_c["safe_area"] = list(safe)
        warnings += warn
        scale = min(cell / w, cell / h)
        rr = st.renderer(copy_c, scale, language=language)
        img = rr.render()
        warnings += rr.warnings
        view = PILImage.alpha_composite(backdrop(img.size, "checker", {}), img)
        if guides:
            from .viewing import draw_guides
            draw_guides(view, list(_maybe_json(guides)), copy_c, scale)
        tiles.append((label, view))
    pad, label_h = 10, 18
    cols = min(3, len(tiles))
    rows = math.ceil(len(tiles) / cols)
    sheet = PILImage.new("RGB", (cols * (cell + pad) + pad, rows * (cell + label_h + pad) + pad), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    font = _label_font(12)
    for i, (label, view) in enumerate(tiles):
        x = pad + (i % cols) * (cell + pad)
        y = pad + (i // cols) * (cell + label_h + pad)
        sheet.paste(view.convert("RGB"), (x + (cell - view.width) // 2, y + (cell - view.height) // 2))
        d.text((x, y + cell + 3), label, fill="#ffffff", font=font)
    info: dict = {"canvas": c["id"], "sizes": [t[0] for t in tiles]}
    if warnings:
        info["warnings"] = sorted(set(warnings))
    return [Image(data=_png_bytes(sheet), format="png"), json.dumps(info)]



STATE_NAMES = ("hover", "pressed", "disabled", "selected", "focused", "checked", "active", "locked", "new")


@tool
def set_state(canvas: str, state: str, id: str, props: dict):
    """Define how an element looks in an interaction state, as overrides on top of the normal look.

    One canvas then holds every state of a button / slot / tab: e.g. set_state("btn", "hover", "face",
    {"style": {"glow": {"color": "$accent", "blur": 14}}}), set_state("btn", "pressed", "face", {"dy": ...})
    - props use update_element names (fill / stroke shortcuts, style merged key by key, null removes).
    Common state names: hover, pressed, disabled, selected, focused (gamepad focus!), checked, locked.
    preview(state=...) shows one; export_asset(states=[...]) writes one sprite per state with the
    engine's state slots filled in (Unity SpriteState, Godot TextureButton, Roblox Hover/PressedImage).
    """
    st = store()
    c = st.get(canvas)
    el = st.find(c, id)
    name = slugify(state, "state")
    patch = _prepare_update(copy.deepcopy(el), _maybe_json(props))
    st.checkpoint(c)
    states = c.setdefault("states", {})
    old = copy.deepcopy(states)
    entry = states.setdefault(name, {}).setdefault(el["id"], {})
    for key, value in patch.items():
        if key == "style" and isinstance(value, dict) and isinstance(entry.get("style"), dict):
            entry["style"].update(value)
        else:
            entry[key] = value
    try:
        r = st.renderer(c, min(1.0, 256 / max(c["width"], c["height"])), state=name)
        r.render()
    except Exception:
        c["states"] = old
        st.drop_checkpoint(c)
        st.save_canvas(c)
        raise
    st.save_canvas(c)
    out: dict = {"canvas": c["id"], "state": name, "overrides": states[name]}
    if name not in STATE_NAMES:
        out["note"] = f"custom state name; engines map {', '.join(STATE_NAMES[:5])} automatically"
    return out


@tool
def delete_state(canvas: str, state: str, id: str | None = None):
    """Remove a whole state, or only one element's overrides in it."""
    st = store()
    c = st.get(canvas)
    states = c.get("states") or {}
    name = slugify(state, "state")
    if name not in states:
        raise ValueError(f"no state '{name}'. States: {', '.join(sorted(states)) or '(none)'}")
    st.checkpoint(c)
    if id:
        states[name].pop(id, None)
        if not states[name]:
            states.pop(name)
    else:
        states.pop(name)
    st.save_canvas(c)
    return {"canvas": c["id"], "states": sorted(states)}



@tool
def set_strings(language: str, strings: dict, default: bool = False, replace: bool = False):
    """Add or change a string table for one language (shared by all canvases). Text elements show
    {key} placeholders filled from it: add_text(text="{menu.play}") + set_strings("tr", {"menu.play": "OYNA"}).

    preview / export / review take `language`; the first table you add is the default (fallback for
    missing keys), or pass default=true. The built-in language "pseudo" lengthens every text by ~35% and
    accents it, "pseudo-long" doubles it (short labels grow most), "pseudo-rtl" forces right-to-left -
    use them to find buttons that will clip in German or Russian. Values set to null are
    removed; replace=true starts the table over. Canvas vars (update_canvas(vars=...)) override strings.
    """
    st = store()
    table = st.set_strings(language, _maybe_json(strings) or {}, default, replace)
    return {"language": language, "keys": len(table), "default_language": st.strings.get("default"),
            "languages": sorted(st.strings["tables"])}


@tool
def get_strings(language: str | None = None):
    """List string-table languages, or one table's keys and values."""
    st = store()
    if language:
        if language not in st.strings["tables"]:
            raise ValueError(f"no string table '{language}'. Languages: {', '.join(sorted(st.strings['tables'])) or '(none)'}")
        return {"language": language, "strings": st.strings["tables"][language]}
    return {"default_language": st.strings.get("default"),
            "languages": {k: len(v) for k, v in sorted(st.strings["tables"].items())}}



@tool
def generate_from_template(template: str, rows: list[dict], name_prefix: str | None = None,
                           export: dict | None = None):
    """Make many canvases from one template canvas and a list of data rows - item cards, rarity
    frames, level badges 1-50, achievement icons, shop tiles.

    In the template, put {placeholders} in text and use colour tokens that rows can override.
    Each row: {"name": "card_sword", "colors": {"rarity": "#f59e0b"}, "props": {"<element id>": {...}},
    ...any other key becomes a text variable}, e.g. {"name": "sword", "title": "Iron Sword", "atk": "12",
    "colors": {"rarity": "$epic"}, "props": {"icon": {"d": "M..."}}}.
    export (optional): export_asset arguments applied to every result, e.g. {"engine": "unity",
    "out_dir": "...", "nine_slice": "auto"}. Returns the new canvas ids (re-running replaces them).
    """
    st = store()
    src = st.get(template)
    rows = _maybe_json(rows)
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows must be a non-empty list of objects")
    if len(rows) > 500:
        raise ValueError("at most 500 rows per call")
    prefix = slugify(name_prefix or src["id"], "item")
    made = []
    warnings: list[str] = []
    exported = []
    for i, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise ValueError(f"row {i} must be an object")
        row = dict(raw)
        name = slugify(str(row.pop("name", f"{prefix}_{i + 1}")), "item")
        if name_prefix and not name.startswith(prefix):
            name = f"{prefix}_{name}"
        colors = _maybe_json(row.pop("colors", None)) or {}
        props = _maybe_json(row.pop("props", None)) or {}
        if name in st.canvases:
            st.delete_canvas(st.canvases[name])
        c = st.duplicate_canvas(src, name)
        c["vars"] = {**(c.get("vars") or {}), **{k: str(v) for k, v in row.items()}}
        if colors:
            c["colors"] = {**(c.get("colors") or {}), **colors}
        try:
            for eid, patch in props.items():
                el = st.find(c, eid)
                st.update_element(c, el, _prepare_update(el, patch), checkpoint=False)
            r = st.renderer(c, min(1.0, 256 / max(c["width"], c["height"])))
            r.render()
            warnings += [f"{name}: {w}" for w in r.warnings]
        except Exception as exc:
            st.delete_canvas(c)
            raise ValueError(f"row {i} ({name}): {exc}") from exc
        st.save_canvas(c)
        made.append(name)
        if export:
            from .server import export_asset
            res = export_asset(name, **{k: v for k, v in _maybe_json(export).items() if k != "name"})
            exported.append(res["files"][0]["file"] if res.get("files") else name)
    out: dict = {"template": src["id"], "canvases": made}
    if exported:
        out["exported"] = exported
    if warnings:
        out["warnings"] = sorted(set(warnings))[:20]
    return out



def _wrap_rows(r, elements, mode, gap, cont_el, padding, max_width, origin, align, justify):
    """Greedy line breaking for wrap=true, then each line laid out as a row."""
    if mode != "row":
        raise ValueError("wrap works with mode='row' (items flow left to right, then onto the next line)")
    if not elements:
        raise ValueError("nothing to arrange - pass element ids or a group that has elements")
    if cont_el is not None:
        frame = r.element_box(cont_el)
        limit = frame[2] - frame[0] - 2 * padding
        x0, y0 = frame[0] + padding, frame[1] + padding
    elif max_width:
        limit = float(max_width)
        first = r.element_box(elements[0])
        x0, y0 = (float(origin[0]), float(origin[1])) if origin else (first[0], first[1])
    else:
        raise ValueError("wrap needs a container or max_width to know where lines break")
    lines, cur, used = [], [], 0.0
    for el in elements:
        b = r.element_box(el)
        w = b[2] - b[0]
        if cur and used + gap + w > limit + 1e-6:
            lines.append(cur)
            cur, used = [], 0.0
        used = w if not cur else used + gap + w
        cur.append(el)
    lines.append(cur)
    moves, content, y = [], None, y0
    share = {"center": 0.5, "end": 1.0}.get(justify, 0.0)
    for line in lines:
        lc, lm = lay.arrange(r, line, "row", gap, None, (x0, y), None, 0.0, align, "start")
        shift = max(0.0, limit - (lc[2] - lc[0])) * share
        moves += [(e, dx + shift, dy) for e, dx, dy in lm]
        lc = (lc[0] + shift, lc[1], lc[2] + shift, lc[3])
        content = lc if content is None else (min(content[0], lc[0]), min(content[1], lc[1]),
                                              max(content[2], lc[2]), max(content[3], lc[3]))
        y = lc[3] + gap
    return content, moves


@tool
def arrange_elements(canvas: str, mode: str = "row", ids: list[str] | None = None, group: str | None = None,
                     gap: float = 8, columns: int | None = None, origin: list[float] | None = None,
                     container: str | None = None, padding: float = 0, align: str = "center",
                     justify: str = "start", hug: bool | str = False, wrap: bool = False,
                     max_width: float | None = None, live: bool = False):
    """Lay elements out in a row, column or grid (like auto-layout), measured by their real bounds.

    ids are placed in the order given (or a group in draw order). gap: space between items.
    mode "grid" uses equal cells (the largest item) and `columns` per row. Without a container the layout
    starts at `origin` [x, y] (default: where the first item is). container: id of a rect to lay out
    inside, with `padding`; justify "start" | "center" | "end" | "space-between" along the main axis;
    align "start" | "center" | "end" across it. hug=true resizes the container rect to wrap the content
    plus padding (a button growing with its label, a list panel growing with its rows).
    wrap=true (mode "row"): items flow onto a new line when the next one would pass the container's inner
    width (or max_width without a container), like Figma auto-layout wrap / CSS flex-wrap - inventory
    slots, tag chips, skill icons. Lines are `gap` apart; justify start / center / end aligns each line.
    To move multi-part widgets as units, give each widget a group and arrange instances or use offsets.

    live=true (with a container) turns this into a real auto-layout frame, like Figma / Penpot: the layout is
    stored on the container and re-applied after every change - edit a label and its button grows, add an
    item and the list re-flows. ids may then include "group:<name>" to move multi-part widgets as one item;
    padding may be [top, right, bottom, left]; hug may be true, "width" or "height". Per child, set with
    update_element: layout_size {"width": "fill" | number, "height": "fill" | number, min_width, max_width,
    min_height, max_height}, span [columns, rows] in grids, absolute true to opt out. Remove with
    update_element(container, {"layout": null}).
    """
    st = store()
    c = st.get(canvas)
    if live:
        if not container:
            raise ValueError("live layout needs a container (the frame that holds and re-flows the items)")
        cont = st.find(c, container)
        refs = [str(i) for i in (_maybe_json(ids) or [])] or ([f"group:{group}"] if group else [])
        if not refs:
            raise ValueError("give ids (element ids or 'group:<name>' entries) or a group for the live layout")
        for ref in refs:
            if not ref.startswith("group:"):
                st.find(c, ref)
        st.checkpoint(c)
        cont["layout"] = {"mode": mode, "children": refs, "gap": gap, "padding": _maybe_json(padding),
                          "align": align, "justify": justify, "wrap": bool(wrap), "hug": hug,
                          **({"columns": columns} if columns else {})}
        try:
            st.save_canvas(c)
        except Exception:
            st.drop_checkpoint(c)
            raise
        return {"container": _summary(st, c, cont), "layout": cont["layout"]}
    elements = st.select(c, ids, group)
    r = st.renderer(c)
    box = None
    cont_el = None
    if container:
        cont_el = st.find(c, container)
        elements = [e for e in elements if e is not cont_el]
        box = r.element_box(cont_el)
    for value, allowed in ((align, ("start", "center", "end")), (justify, ("start", "center", "end", "space-between"))):
        if value not in allowed:
            raise ValueError(f"'{value}' must be one of {', '.join(allowed)}")
    if hug and cont_el is None:
        raise ValueError("hug needs a container")
    if hug:
        box = None
        ob = r.element_box(cont_el)
        origin = [ob[0] + padding, ob[1] + padding]
    if wrap:
        content, moves = _wrap_rows(r, elements, mode, float(gap), cont_el, float(padding), max_width,
                                    _maybe_json(origin), align, justify)
    else:
        content, moves = lay.arrange(r, elements, mode, float(gap), columns,
                                     tuple(_maybe_json(origin)) if origin else None, box, float(padding), align,
                                     justify)
    st.checkpoint(c)
    for el, dx, dy in moves:
        st.shift(el, dx, dy)
    if hug:
        if cont_el["type"] != "rect":
            st.drop_checkpoint(c)
            raise ValueError("hug works with a rect container")
        cont_el["x"], cont_el["y"] = content[0] - padding, content[1] - padding
        cont_el["width"] = round(content[2] - content[0] + 2 * padding, 3)
        cont_el["height"] = round(content[3] - content[1] + 2 * padding, 3)
    st.save_canvas(c)
    out = {"arranged": [e["id"] for e, _, _ in moves],
           "content_box_xywh": [round(content[0], 2), round(content[1], 2), round(content[2] - content[0], 2),
                                round(content[3] - content[1], 2)]}
    if hug:
        out["container"] = _summary(st, c, cont_el)
    return out


@tool
def scatter(canvas: str, id: str, count: int, area: list[float], seed: int = 1, shape: str = "rect",
            scale: list[float] | None = None, rotation: list[float] | None = None,
            opacity: list[float] | None = None, min_distance: float = 0, new_id: str | None = None,
            group: str | None = None, keep_source: bool = False, animate: dict | None = None):
    """Copy an element `count` times at random spots - sparkles, stars, confetti, embers, dust, debris,
    rain, background bokeh - reproducibly (same seed = same result).

    area [x, y, width, height]; shape "rect" or "ellipse" (inside the inscribed ellipse).
    scale / rotation / opacity: [min, max] random ranges per copy. min_distance keeps copies apart.
    Copies get ids "<new_id or id>_s1"... and `group` (default "<id>_scatter"). The source is removed
    unless keep_source. animate: give each copy the same keyframes at a random time offset so they
    twinkle / drift out of sync: {"animation": "idle", "property": "opacity",
    "keyframes": [[0, 0.2], [0.6, 1, "sine-in-out"], [1.2, 0.2, "sine-in-out"]], "spread": 1.2}.
    """
    st = store()
    c = st.get(canvas)
    src = st.find(c, id)
    count = int(count)
    if not 1 <= count <= 500:
        raise ValueError("count must be 1-500")
    a = _maybe_json(area)
    if not isinstance(a, list) or len(a) != 4:
        raise ValueError("area must be [x, y, width, height]")
    x0, y0, w, h = (float(v) for v in a)
    pts = lay.scatter_plan(count, (x0, y0, x0 + w, y0 + h), int(seed), float(min_distance), shape)
    rng = random.Random(int(seed) * 7919 + 1)
    r = st.renderer(c)
    sb = r.element_box(src)
    scx, scy = (sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2

    def pick(rangev, default):
        rv = _maybe_json(rangev)
        if not rangev:
            return default
        if isinstance(rv, (int, float)):
            return float(rv)
        return rng.uniform(float(rv[0]), float(rv[1]))

    grp = group or f"{src['id']}_scatter"
    base_id = slugify(new_id or src["id"], "s")
    st.checkpoint(c)
    made = []
    try:
        for i, (px, py) in enumerate(pts):
            clone = copy.deepcopy(src)
            clone.pop("id")
            etype = clone.pop("type")
            st.shift(clone, px - scx, py - scy)
            sc = pick(scale, 1.0)
            if sc != 1.0:
                base_x = float(clone.get("scale_x", 1) or 1)
                base_y = float(clone.get("scale_y", 1) or 1)
                clone["scale_x"], clone["scale_y"] = round(base_x * sc, 4), round(base_y * sc, 4)
            rot = pick(rotation, 0.0)
            if rot:
                clone["rotation"] = round(float(clone.get("rotation", 0) or 0) + rot, 3)
            op = pick(opacity, None)
            if op is not None:
                stl = clone.get("style")
                stl = dict(stl) if isinstance(stl, dict) else ({"use": stl} if stl else {})
                stl["opacity"] = round(max(0.0, min(1.0, op)), 3)
                clone["style"] = stl
            clone["group"] = grp
            clone["id"] = f"{base_id}_s{i + 1}"
            el, _ = st.add_element(c, etype, clone, checkpoint=False)
            made.append(el)
        if not keep_source:
            st.delete_elements(c, [src], checkpoint=False)
        anim_out = None
        if animate:
            from .server import _set_keyframes
            from . import animation as anim_mod
            spec = dict(_maybe_json(animate))
            spread = float(spec.pop("spread", 1.0))
            arng = random.Random(int(seed) * 31 + 7)
            _, anim = st.get_animation(c, spec.get("animation", ""))
            last = max(k["t"] for k in anim_mod.normalize_keyframes(_maybe_json(spec.get("keyframes")),
                                                                    anim["duration"], 0.0))
            spread = max(0.0, min(spread, float(anim["duration"]) - last))
            for el in made:
                _set_keyframes(c, {**spec, "target": el["id"], "offset": round(arng.uniform(0, spread), 3)},
                               checkpoint=False)
            anim_out = spec.get("animation")
    except Exception:
        st.drop_checkpoint(c)
        st.save_canvas(c)
        raise
    st.save_canvas(c)
    out: dict = {"group": grp, "count": len(made), "ids": [e["id"] for e in made][:12]}
    if len(made) < count:
        out["note"] = f"only {len(made)} spots fit with min_distance {min_distance:g}"
    if anim_out:
        out["animated"] = anim_out
    return out


@tool
def copy_elements(source_canvas: str, target_canvas: str, ids: list[str] | None = None, group: str | None = None,
                  dx: float = 0, dy: float = 0, layer: str | None = None):
    """Copy elements from one canvas to another (ids or a whole group), offset by (dx, dy). Clashing ids
    get a numeric suffix; clip references inside the copied set are kept. For a part that should stay
    linked to its source, use add_instance instead."""
    st = store()
    src = st.get(source_canvas)
    dst = st.get(target_canvas)
    items = st.select(src, ids, group)
    taken = {e["id"] for e in dst["elements"]}
    rename: dict[str, str] = {}
    for el in items:
        new = el["id"]
        n = 2
        while new in taken:
            new = f"{el['id']}_{n}"
            n += 1
        taken.add(new)
        rename[el["id"]] = new
    st.checkpoint(dst)
    made = []
    try:
        for el in items:
            clone = copy.deepcopy(el)
            clone["id"] = rename[el["id"]]
            if clone.get("clip"):
                clone["clip"] = rename.get(clone["clip"])
                if clone["clip"] is None:
                    clone.pop("clip")
            clone.pop("layer", None)
            if layer:
                clone["layer"] = layer
            st.shift(clone, float(dx), float(dy))
            etype = clone.pop("type")
            new_el, _ = st.add_element(dst, etype, clone, checkpoint=False)
            made.append(new_el["id"])
    except Exception:
        st.drop_checkpoint(dst)
        st.save_canvas(dst)
        raise
    st.save_canvas(dst)
    return {"target": dst["id"], "copied": made}


@tool
def redo(canvas: str):
    """Redo the last change undone with undo."""
    st = store()
    c = st.get(canvas)
    if not st.redo(c):
        return {"redone": False, "reason": "nothing to redo"}
    return {"redone": True, "elements": [e["id"] for e in c["elements"]]}



@tool
def export_bitmap_font(name: str, characters: str = "0123456789+-x%.,:!", size: float = 48,
                       font: str | None = None, weight: int | str | None = None,
                       style: str | dict | None = None, fill: str | dict | None = None,
                       stroke: str | dict | None = None, letter_spacing: float = 0, padding: int = 4,
                       out_dir: str | None = None, preview_text: str | None = None):
    """Bake a styled bitmap font: damage numbers, score counters, combo text, gold amounts - glyphs with
    gradient fills, thick outlines, shadows and glow that engine text cannot do cheaply.

    Writes <name>.png (glyph atlas) + <name>.fnt (BMFont text format: Godot imports it directly, Unity
    via TextMesh Pro / BMFont importers, many Roblox and web pipelines read it) + <name>.json.
    style / fill / stroke work as in add_text (effects included, e.g. {"shadow": {...}, "glow": {...}}).
    Returns a preview of `preview_text` set with the baked glyphs.
    """
    from . import export as ex
    st = store()
    chars = []
    for ch in str(characters):
        if ch not in chars and ch not in "\n\r\t":
            chars.append(ch)
    if not chars:
        raise ValueError("characters is empty - pass the text whose glyphs you need, e.g. '0123456789:'")
    if len(chars) > 256:
        raise ValueError("at most 256 characters")
    fill, stroke, style = _maybe_json(fill), _maybe_json(stroke), _maybe_json(style)
    base_style: dict = {}
    if isinstance(style, str):
        base_style = {"use": style}
    elif isinstance(style, dict):
        base_style = dict(style)
    if fill is not None:
        base_style["fill"] = fill
    if stroke is not None:
        base_style["stroke"] = stroke
    probe_el = {"id": "g", "type": "text", "text": "Hg", "x": 0, "y": 0, "size": size, "font": font,
                "weight": weight, "style": base_style}
    probe_el = {k: v for k, v in probe_el.items() if v is not None}
    st_res = resolve_style(base_style, st.theme)
    layout = TextLayout(probe_el, st_res, st.fonts, 1.0)
    ascent, descent = layout.ascent, layout.descent
    reach = 0.0
    from .render import Effects, _stroke_specs
    fx = Effects(st_res, st.theme.get("colors", {}))
    for sp in _stroke_specs(st_res, st.theme.get("colors", {})):
        reach = max(reach, sp["offset"] + sp["width"])
    margin = int(math.ceil(reach + fx.pad() + padding))
    line_h = int(math.ceil(ascent + descent))
    tmp = {"id": "__bmfont", "width": 8, "height": 8, "background": None, "elements": []}
    glyphs = []
    for ch in chars:
        adv = float(layout.font.getlength(ch))
        cw = int(math.ceil(adv)) + 2 * margin
        ch_h = line_h + 2 * margin
        tmp["width"], tmp["height"] = max(1, cw), ch_h
        tmp["elements"] = [{**probe_el, "id": "g", "text": ch, "x": margin, "y": margin + ascent,
                            "anchor": "baseline-left"}]
        r = st.renderer(tmp)
        img = r.render(include_background=False)
        glyphs.append((ch, img, adv))
    atlas, frames = ex.pack_atlas([(f"g{i}", g[1]) for i, g in enumerate(glyphs)], padding=2, max_size=4096)
    folder = _out_dir(out_dir, "fonts")
    base = slugify(name, "font")
    png = folder / f"{base}.png"
    atlas.save(png)
    lines = [f'info face="{base}" size={int(round(size))} bold=0 italic=0 charset="" unicode=1 stretchH=100 smooth=1 aa=1 '
             f'padding={margin},{margin},{margin},{margin} spacing=2,2',
             f"common lineHeight={line_h} base={int(round(ascent))} scaleW={atlas.width} scaleH={atlas.height} pages=1 packed=0",
             f'page id=0 file="{png.name}"', f"chars count={len(glyphs)}"]
    meta = {}
    for i, (ch, img, adv) in enumerate(glyphs):
        f = frames[f"g{i}"]
        xadv = int(round(adv + letter_spacing))
        lines.append(f"char id={ord(ch)} x={f['x']} y={f['y']} width={f['w']} height={f['h']} "
                     f"xoffset={-margin} yoffset={-margin} xadvance={xadv} page=0 chnl=15")
        meta[ch] = {**f, "xadvance": xadv}
    (folder / f"{base}.fnt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / f"{base}.json").write_text(json.dumps({"atlas": png.name, "lineHeight": line_h, "base": round(ascent),
                                                     "offset": [-margin, -margin], "glyphs": meta},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    sample = preview_text or "".join(chars[:12])
    width = sum(int(round(next((g[2] for g in glyphs if g[0] == ch), size / 2) + letter_spacing)) for ch in sample)
    view = PILImage.new("RGBA", (max(16, width + 2 * margin + 16), line_h + 2 * margin + 16), (0, 0, 0, 0))
    x = 8
    lookup = {g[0]: g for g in glyphs}
    missing = [ch for ch in sample if ch not in lookup and ch != " "]
    for ch in sample:
        g = lookup.get(ch)
        if g is None:
            x += int(size / 3)
            continue
        view.alpha_composite(g[1], (x, 8))
        x += int(round(g[2] + letter_spacing))
    shown = PILImage.alpha_composite(backdrop(view.size, "checker", {}), view)
    info: dict = {"png": str(png), "fnt": str(folder / f"{base}.fnt"), "glyphs": len(glyphs),
                  "line_height": line_h, "atlas_size": list(atlas.size)}
    if missing:
        info["note"] = f"preview_text uses characters that are not in the font: {''.join(sorted(set(missing)))}"
    return [Image(data=_png_bytes(shown.convert("RGB")), format="png"), json.dumps(info, ensure_ascii=False)]
