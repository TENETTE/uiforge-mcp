"""Lottie (Bodymovin JSON) export of an animation, for apps, web (lottie-web), Unity / Unreal / Godot
Lottie players and Figma Motion style hand-off.

Every element becomes an image layer. Movement, rotation, scale and opacity stay real Lottie transform
animation (light and smooth at any frame rate); elements whose other properties animate (colour, glow,
arc sweep, text...) become one picture per frame so the result always matches the PNG. Runs of elements
that never move are merged into one picture.
"""

from __future__ import annotations

import base64
import hashlib
import io
from typing import Any

from .animation import apply_animation, frame_times
from .render import _scales, resolve_style

_MOVE_KEYS = {"x", "y", "cx", "cy", "points", "origin", "rotation", "scale", "scale_x", "scale_y", "flip_x", "flip_y"}


def _ref_point(el: dict) -> tuple[float, float]:
    if el.get("points") and el["type"] in ("polygon", "line"):
        return float(el["points"][0][0]), float(el["points"][0][1])
    if "cx" in el:
        return float(el["cx"]), float(el["cy"])
    return float(el.get("x", 0)), float(el.get("y", 0))


def _opacity(el: dict, theme: dict) -> float:
    return float(resolve_style(el.get("style"), theme).get("opacity", 1.0))


def _look(el: dict, theme: dict) -> Any:
    """Everything that changes the picture except position, rotation, scale and opacity."""
    st = dict(resolve_style(el.get("style"), theme))
    st.pop("opacity", None)
    return ({k: v for k, v in el.items() if k not in _MOVE_KEYS and k != "style"}, st)


def _prop(values: list) -> dict:
    if all(v == values[0] for v in values):
        return {"a": 0, "k": values[0]}
    dims = len(values[0]) if isinstance(values[0], list) else 1
    lin_o, lin_i = {"x": [0.0] * dims, "y": [0.0] * dims}, {"x": [1.0] * dims, "y": [1.0] * dims}
    keys = [{"t": i, "s": v if isinstance(v, list) else [v], "o": lin_o, "i": lin_i} for i, v in enumerate(values)]
    return {"a": 1, "k": keys}


class _Assets:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self._seen: dict[str, str] = {}

    def add(self, img) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        key = hashlib.sha1(data).hexdigest()
        if key not in self._seen:
            aid = f"img_{len(self.items)}"
            self._seen[key] = aid
            self.items.append({"id": aid, "w": img.width, "h": img.height, "u": "", "e": 1,
                               "p": "data:image/png;base64," + base64.b64encode(data).decode("ascii")})
        return self._seen[key]


_VECTOR_KEYS = {"fill", "stroke", "opacity", "use"}


def _rgb(value: Any, colors: dict) -> list[float] | None:
    from .colors import parse_color
    try:
        r, g, b, a = parse_color(value, colors)
    except ValueError:
        return None
    return [round(r / 255, 4), round(g / 255, 4), round(b / 255, 4), round(a / 255, 4)]


def _shape_polys(r, el: dict, st: dict) -> tuple[list, int] | None:
    """Outline polygons (canvas units, no rotation / scale) of a plain vector element, and its fill rule."""
    from .render import LINE_TYPES, VECTOR_TYPES, TextLayout, _placed_polys, vector_geometry
    t = el["type"]
    if t == "text":
        if el.get("arc") or el.get("path"):
            return None
        layout = TextLayout(el, st, r.fonts, 4.0, r.text_of(el), r.text_lang(el))
        if layout.shaper and any(layout.shaper.color_runs.get(line) for line, _ in layout.lines):
            return None
        return layout.outline_polys_units(), 1
    if t in LINE_TYPES:
        from .tools_design import _floats, _line_outline
        g = vector_geometry(el, 4.0)
        return _floats(_line_outline(g, "round")) + [list(p) for p in g.fills], 1
    if t in VECTOR_TYPES:
        rule = 1 if (t == "path" and str(el.get("fill_rule", "evenodd")).lower() == "nonzero") else 2
        return _placed_polys(el, 4.0), rule
    return None


def _vector_layer(store, r0, el: dict, frames: list[dict], theme: dict, k: float, n: int) -> dict | None:
    """A real Lottie shape layer (crisp at any size) for plain shapes and text: solid or gradient fill,
    one stroke, animated position / rotation / scale / opacity and animated solid fill colour."""
    st0 = r0._nums(resolve_style(el.get("style"), theme))
    if set(st0) - _VECTOR_KEYS or el.get("clip") or any(el.get(x) for x in ("flip_x", "flip_y")):
        return None
    for f in frames:
        sf = resolve_style(f.get("style"), theme)
        if set(sf) - _VECTOR_KEYS:
            return None
        a, b = _look(f, theme), _look(el, theme)
        if a[0] != b[0] or {k2: v for k2, v in a[1].items() if k2 != "fill"} != {k2: v for k2, v in b[1].items() if k2 != "fill"}:
            return None
    colors = r0.colors
    fill = st0.get("fill", "#ffffff" if (el["type"] == "text" or not st0.get("stroke")) else None)
    fills = [resolve_style(f.get("style"), theme).get("fill", fill) for f in frames]
    animated_color = any(fv != fill for fv in fills)
    if animated_color and any(isinstance(fv, (dict, list)) for fv in fills):
        return None
    plain = {key: v for key, v in el.items() if key not in ("rotation", "scale", "scale_x", "scale_y")}
    got = _shape_polys(r0, r0._nums(plain), st0)
    if got is None:
        return None
    polys, rule = got
    items: list[dict] = []
    for p in polys:
        if len(p) < 3:
            continue
        v = [[round(x * k, 2), round(y * k, 2)] for x, y in p]
        z = [[0, 0]] * len(v)
        items.append({"ty": "sh", "ks": {"a": 0, "k": {"c": True, "v": v, "i": z, "o": z}}})
    if not items:
        return None
    from .render import _stroke_specs
    strokes = _stroke_specs(st0, colors)
    if len(strokes) > 1 or (strokes and (strokes[0]["dash"] or strokes[0]["sides"] or strokes[0]["offset"]
                                         or not isinstance(strokes[0]["paint"], str))):
        return None
    if isinstance(fill, list):
        return None
    if isinstance(fill, dict):
        kind = str(fill.get("type", "linear")).lower()
        raw = fill.get("stops") or fill.get("colors")
        if kind not in ("linear", "radial") or not raw:
            return None
        g = vector_geometry_box(r0, plain, st0)
        x0, y0, x1, y1 = (v * k for v in g)
        bw, bh = x1 - x0, y1 - y0
        stops = []
        nst = len(raw)
        for i, item in enumerate(raw):
            off, col = (item if isinstance(item, (list, tuple)) and len(item) == 2 and not isinstance(item[1], (int, float))
                        else (i / (nst - 1), item))
            c = _rgb(col, colors)
            if c is None or c[3] < 1:
                return None
            stops += [float(off), c[0], c[1], c[2]]
        import math
        if kind == "linear":
            ang = math.radians(float(fill.get("angle", 90)))
            ca, sa = math.cos(ang), math.sin(ang)
            half = (abs(bw * ca) + abs(bh * sa)) / 2
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            s_pt, e_pt, gt = [cx - ca * half, cy - sa * half], [cx + ca * half, cy + sa * half], 1
        else:
            if fill.get("circle") is None and abs(bw - bh) > 0.5:
                return None
            cx, cy = x0 + bw * float(fill.get("cx", 0.5)), y0 + bh * float(fill.get("cy", 0.5))
            rad = max(bw, bh) * float(fill.get("r", 0.5))
            s_pt, e_pt, gt = [cx, cy], [cx + rad, cy], 2
        items.append({"ty": "gf", "o": {"a": 0, "k": 100}, "r": rule, "t": gt, "s": {"a": 0, "k": s_pt},
                      "e": {"a": 0, "k": e_pt}, "g": {"p": nst, "k": {"a": 0, "k": stops}}})
    elif fill is not None and not (isinstance(fill, str) and fill.strip().lower() in ("none", "")):
        cols = [_rgb(fv, colors) for fv in fills]
        if any(c is None for c in cols):
            return None
        alpha = cols[0][3]
        items.append({"ty": "fl", "c": _prop([c[:3] + [1] for c in cols]), "o": {"a": 0, "k": round(alpha * 100, 2)},
                      "r": rule})
    if strokes:
        sp = strokes[0]
        c = _rgb(sp["paint"], colors)
        if sp["align"] == "center":
            items.append({"ty": "st", "c": {"a": 0, "k": c[:3] + [1]}, "o": {"a": 0, "k": round(c[3] * 100, 2)},
                          "w": {"a": 0, "k": round(sp["width"] * k, 2)}, "lc": 2, "lj": 2})
        else:
            from .pdfexport import _band
            band = _band(polys, sp["d0"], sp["d1"], sp["join"] or "round")
            group = [{"ty": "sh", "ks": {"a": 0, "k": {"c": True, "v": [[round(x * k, 2), round(y * k, 2)] for x, y in p],
                                                        "i": [[0, 0]] * len(p), "o": [[0, 0]] * len(p)}}}
                     for p in band if len(p) >= 3]
            group += [{"ty": "fl", "c": {"a": 0, "k": c[:3] + [1]}, "o": {"a": 0, "k": round(c[3] * 100, 2)}, "r": 1},
                      _group_tr()]
            items = [{"ty": "gr", "it": group}] + [{"ty": "gr", "it": items + [_group_tr()]}]
            return _shape_layer(r0, el, frames, theme, k, items, plain, st0, wrapped=True)
    return _shape_layer(r0, el, frames, theme, k, items, plain, st0)


def _group_tr() -> dict:
    return {"ty": "tr", "p": {"a": 0, "k": [0, 0]}, "a": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [100, 100]},
            "r": {"a": 0, "k": 0}, "o": {"a": 0, "k": 100}}


def vector_geometry_box(r0, plain: dict, st: dict):
    return r0._geom_box(plain, st)


def _shape_layer(r0, el, frames, theme, k, items, plain, st0, wrapped: bool = False) -> dict:
    pivot0 = r0._pivot(plain, r0._geom_box(plain, st0))
    ref0 = _ref_point(el)
    pos, rot, scl, opa = [], [], [], []
    for f in frames:
        rx, ry = _ref_point(f)
        sx, sy = _scales(f)
        pos.append([round((pivot0[0] + rx - ref0[0]) * k, 3), round((pivot0[1] + ry - ref0[1]) * k, 3), 0])
        rot.append(round(float(f.get("rotation", 0) or 0), 4))
        scl.append([round(sx * 100, 4), round(sy * 100, 4), 100])
        opa.append(round(_opacity(f, theme) * 100, 3))
    shapes = items if wrapped else [{"ty": "gr", "it": items + [_group_tr()]}]
    return {"ddd": 0, "ty": 4, "nm": el["id"], "sr": 1, "ao": 0, "bm": 0, "st": 0, "ip": 0, "op": len(frames),
            "shapes": shapes,
            "ks": {"o": _prop(opa), "r": _prop(rot), "p": _prop(pos),
                   "a": {"a": 0, "k": [round(pivot0[0] * k, 3), round(pivot0[1] * k, 3), 0]}, "s": _prop(scl)}}


def build(store, canvas: dict, anim: dict, name: str, fps: float | None, scale: float, include_background: bool) -> tuple[dict, dict]:
    theme = store.theme
    colors = theme.get("colors", {})
    times = frame_times(anim, fps)
    rate = float(fps or anim.get("fps", 30))
    n = len(times)
    poses = [apply_animation(canvas, anim, t, colors)[0] for t in times]
    r0 = store.renderer(canvas, scale)
    k = scale
    assets = _Assets()
    layers: list[dict] = []
    report = {"transform": [], "frames": [], "static": [], "vector": []}

    def image_layer(asset: str, x: float, y: float, ip: int = 0, op: int | None = None, ks: dict | None = None, nm: str = ""):
        layers.append({"ddd": 0, "ty": 2, "nm": nm, "refId": asset, "sr": 1, "ao": 0, "bm": 0, "st": 0,
                       "ip": ip, "op": n if op is None else op,
                       "ks": ks or {"o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0}, "p": {"a": 0, "k": [x, y, 0]},
                                    "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}}})

    if include_background and canvas.get("background"):
        bg = r0.render(include_background=True, only=set())
        image_layer(assets.add(bg), 0, 0, nm="background")

    order = [el for _, els in r0.stack() for el in els]
    posed_by_id = [{e["id"]: e for e in p["elements"]} for p in poses]
    static_run: list[str] = []

    def flush() -> None:
        if not static_run:
            return
        img = r0.render(include_background=False, only=set(static_run))
        bbox = img.getchannel("A").getbbox()
        if bbox:
            image_layer(assets.add(img.crop(bbox)), bbox[0], bbox[1], nm="static: " + ", ".join(static_run[:4]))
        report["static"] += static_run
        static_run.clear()

    for el in order:
        frames = [pb.get(el["id"], el) for pb in posed_by_id]
        if all(f == el for f in frames):
            static_run.append(el["id"])
            continue
        flush()
        vec = _vector_layer(store, r0, el, frames, theme, k, n)
        if vec is not None:
            layers.append(vec)
            report["vector"].append(el["id"])
            continue
        looks_same = all(_look(f, theme) == _look(el, theme) for f in frames)
        if looks_same:
            plain = {key: v for key, v in el.items() if key not in ("rotation", "scale", "scale_x", "scale_y",
                                                                   "flip_x", "flip_y")}
            st = resolve_style(el.get("style"), theme)
            if "opacity" in st:
                plain["style"] = {**st, "opacity": 1.0}
            result = r0.render_element(plain)
            if result is None:
                continue
            img, px0, py0, _ = result
            st0 = r0._nums(resolve_style(plain.get("style"), theme))
            pivot0 = r0._pivot(plain, r0._geom_box(r0._nums(plain), st0))
            ref0 = _ref_point(el)
            pos, rot, scl, opa = [], [], [], []
            for f in frames:
                rx, ry = _ref_point(f)
                dx, dy = rx - ref0[0], ry - ref0[1]
                sx, sy = _scales(f)
                pos.append([round((pivot0[0] + dx) * k, 3), round((pivot0[1] + dy) * k, 3), 0])
                rot.append(round(float(f.get("rotation", 0) or 0), 4))
                scl.append([round(sx * 100, 4), round(sy * 100, 4), 100])
                opa.append(round(_opacity(f, theme) * 100, 3))
            ks = {"o": _prop(opa), "r": _prop(rot), "p": _prop(pos),
                  "a": {"a": 0, "k": [round(pivot0[0] * k - px0, 3), round(pivot0[1] * k - py0, 3), 0]},
                  "s": _prop(scl)}
            image_layer(assets.add(img), 0, 0, ks=ks, nm=el["id"])
            report["transform"].append(el["id"])
        else:
            for i, (pose, f) in enumerate(zip(poses, frames)):
                result = store.renderer(pose, scale).render_element(f)
                if result is None:
                    continue
                img, px0, py0, _ = result
                image_layer(assets.add(img), px0, py0, ip=i, op=i + 1, nm=f"{el['id']} #{i}")
            report["frames"].append(el["id"])
    flush()
    for i, layer in enumerate(reversed(layers), 1):
        layer["ind"] = i
    doc = {"v": "5.7.4", "fr": rate, "ip": 0, "op": n, "w": round(canvas["width"] * k), "h": round(canvas["height"] * k),
           "nm": name, "ddd": 0, "assets": assets.items, "layers": list(reversed(layers)),
           "markers": [{"tm": 0, "cm": name, "dr": n}]}
    return doc, report


def build_state_machine(canvas: dict, anim_names: list[str], anim_meta: dict[str, dict]) -> dict | None:
    """Synthesize an official dotLottie v2 State Machine JSON from canvas animations, interactions and bindings."""
    interactions = canvas.get("interactions") or []
    data_map = canvas.get("data") or {}
    if not interactions and len(anim_names) < 2 and not data_map:
        return None

    inputs: list[dict] = []
    input_names: set[str] = set()

    def ensure_input(itype: str, name: str, value: Any) -> None:
        if name in input_names:
            return
        input_names.add(name)
        inputs.append({"type": itype, "name": name, "value": value})

    for dk, dv in data_map.items():
        if isinstance(dv, bool):
            ensure_input("Boolean", str(dk), dv)
        elif isinstance(dv, (int, float)):
            ensure_input("Numeric", str(dk), float(dv))
        elif isinstance(dv, str):
            ensure_input("String", str(dk), dv)

    anim_set = set(anim_names)
    initial_anim = anim_names[0]
    for pref in ("idle", "default", "base", "loop"):
        if pref in anim_set:
            initial_anim = pref
            break

    state_transitions: dict[str, list[dict]] = {a: [] for a in anim_names}
    listeners: list[dict] = []

    for idx, inter in enumerate(interactions):
        ev = str(inter.get("trigger") or inter.get("on") or "click").lower()
        target_el = str(inter.get("id") or inter.get("target") or "")
        to_state = str(inter.get("animation") or inter.get("state") or "")
        to_anim = to_state if to_state in anim_set else (anim_names[1] if len(anim_names) > 1 else initial_anim)
        in_name = f"is_{to_anim}_{idx}" if to_anim != initial_anim else f"active_{idx}"

        if ev == "hover":
            ensure_input("Boolean", in_name, False)
            listeners.append({
                "type": "PointerEnter",
                "layerName": target_el,
                "actions": [{"type": "SetBoolean", "inputName": in_name, "value": True}],
            })
            listeners.append({
                "type": "PointerExit",
                "layerName": target_el,
                "actions": [{"type": "SetBoolean", "inputName": in_name, "value": False}],
            })
            if to_anim != initial_anim:
                state_transitions[initial_anim].append({
                    "type": "Tweened",
                    "toState": to_anim,
                    "duration": 0.18,
                    "easing": [0.25, 0.1, 0.25, 1.0],
                    "guards": [{"type": "Boolean", "inputName": in_name, "conditionType": "Equal", "compareTo": True}],
                })
                state_transitions[to_anim].append({
                    "type": "Tweened",
                    "toState": initial_anim,
                    "duration": 0.18,
                    "easing": [0.25, 0.1, 0.25, 1.0],
                    "guards": [{"type": "Boolean", "inputName": in_name, "conditionType": "Equal", "compareTo": False}],
                })
        elif ev == "press":
            ensure_input("Boolean", in_name, False)
            listeners.append({
                "type": "PointerDown",
                "layerName": target_el,
                "actions": [{"type": "SetBoolean", "inputName": in_name, "value": True}],
            })
            listeners.append({
                "type": "PointerUp",
                "layerName": target_el,
                "actions": [{"type": "SetBoolean", "inputName": in_name, "value": False}],
            })
            if to_anim != initial_anim:
                state_transitions[initial_anim].append({
                    "type": "Transition",
                    "toState": to_anim,
                    "guards": [{"type": "Boolean", "inputName": in_name, "conditionType": "Equal", "compareTo": True}],
                })
                state_transitions[to_anim].append({
                    "type": "Transition",
                    "toState": initial_anim,
                    "guards": [{"type": "Boolean", "inputName": in_name, "conditionType": "Equal", "compareTo": False}],
                })
        else:
            ensure_input("Boolean", in_name, False)
            listeners.append({
                "type": "Click",
                "layerName": target_el,
                "actions": [{"type": "Toggle", "inputName": in_name}],
            })
            if to_anim != initial_anim:
                state_transitions[initial_anim].append({
                    "type": "Tweened",
                    "toState": to_anim,
                    "duration": 0.22,
                    "easing": [0.22, 1.0, 0.36, 1.0],
                    "guards": [{"type": "Boolean", "inputName": in_name, "conditionType": "Equal", "compareTo": True}],
                })
                state_transitions[to_anim].append({
                    "type": "Tweened",
                    "toState": initial_anim,
                    "duration": 0.22,
                    "easing": [0.22, 1.0, 0.36, 1.0],
                    "guards": [{"type": "Boolean", "inputName": in_name, "conditionType": "Equal", "compareTo": False}],
                })

    if not interactions and len(anim_names) >= 2:
        ensure_input("Numeric", "state_index", 0.0)
        for i, aname in enumerate(anim_names):
            nxt = anim_names[(i + 1) % len(anim_names)]
            state_transitions[aname].append({
                "type": "Tweened",
                "toState": nxt,
                "duration": 0.2,
                "easing": [0.25, 0.1, 0.25, 1.0],
                "guards": [{"type": "Numeric", "inputName": "state_index", "conditionType": "Equal",
                            "compareTo": float((i + 1) % len(anim_names))}],
            })
        listeners.append({
            "type": "Click",
            "layerName": "",
            "actions": [{"type": "Increment", "inputName": "state_index", "value": 1.0}],
        })

    states: list[dict] = []
    for aname in anim_names:
        meta = anim_meta.get(aname, {})
        trans = list(state_transitions.get(aname, []))
        if not meta.get("loop") and aname != initial_anim:
            listeners.append({
                "type": "OnComplete",
                "stateName": aname,
                "actions": [{"type": "SetBoolean", "inputName": f"done_{aname}", "value": True}],
            })
            ensure_input("Boolean", f"done_{aname}", False)
            trans.append({
                "type": "Transition",
                "toState": initial_anim,
                "guards": [{"type": "Boolean", "inputName": f"done_{aname}", "conditionType": "Equal", "compareTo": True}],
            })
        states.append({
            "name": aname,
            "type": "PlaybackState",
            "animation": aname,
            "loop": bool(meta.get("loop", False)),
            "autoplay": True,
            "mode": "Forward",
            "speed": 1.0,
            "transitions": trans,
        })

    return {
        "initial": initial_anim,
        "states": states,
        "interactions": listeners,
        "inputs": inputs,
    }


def build_dotlottie(store, canvas: dict, anim_names: list[str], fps: float | None, scale: float,
                    include_background: bool, state_machine: dict | None = None) -> tuple[bytes, dict]:
    """Pack one or more canvas animations and an optional dotLottie v2 state machine into a .lottie ZIP archive."""
    import json
    import zipfile
    buf = io.BytesIO()
    manifest_anims = []
    summaries = {}
    anim_meta: dict[str, dict] = {}
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for aname in anim_names:
            key, anim = store.get_animation(canvas, aname)
            doc, rep = build(store, canvas, anim, f"{canvas['id']}_{key}", fps, scale, include_background)
            zf.writestr(f"a/{key}.json", json.dumps(doc, separators=(",", ":")).encode("utf-8"))
            manifest_anims.append({"id": key, "name": key})
            anim_meta[key] = {"loop": bool(anim.get("loop")), "fps": doc["fr"], "frames": doc["op"]}
            summaries[key] = {"frames": doc["op"], "fps": doc["fr"], "vector": rep["vector"],
                              "transform": rep["transform"], "baked_per_frame": rep["frames"]}
        sm_doc = state_machine if isinstance(state_machine, dict) else build_state_machine(canvas, [a["id"] for a in manifest_anims], anim_meta)
        manifest: dict[str, Any] = {
            "version": "2",
            "generator": "game-ui-mcp",
            "animations": manifest_anims,
        }
        sm_id = None
        if sm_doc:
            sm_id = f"{canvas['id']}_sm"
            zf.writestr(f"s/{sm_id}.json", json.dumps(sm_doc, separators=(",", ":")).encode("utf-8"))
            manifest["stateMachines"] = [{"id": sm_id, "name": sm_id}]
            manifest["initial"] = {"stateMachine": sm_id}
        else:
            manifest["initial"] = {"animation": manifest_anims[0]["id"]}
        zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
    report: dict[str, Any] = {"animations": summaries, "count": len(manifest_anims), "spec_version": "2"}
    if sm_doc and sm_id:
        report["state_machine"] = {"id": sm_id, "states": len(sm_doc.get("states", [])),
                                   "interactions": len(sm_doc.get("interactions", [])),
                                   "inputs": len(sm_doc.get("inputs", []))}
    return buf.getvalue(), report
