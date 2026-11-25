"""Keyframe animation: easing, value interpolation and per-frame evaluation.

An animation belongs to a canvas and is a set of tracks. A track animates one
property of one element (or of every element in a group) through keyframes:

    {"target": "needle", "property": "rotation",
     "keyframes": [{"t": 0, "value": 135}, {"t": 0.6, "value": 380, "ease": "back-out"}]}

A keyframe's ``ease`` shapes the motion *arriving* at that keyframe. Before the
first keyframe the property holds the first value; after the last it holds the last.
"""

from __future__ import annotations

import copy
import math
import re
from collections import OrderedDict
from typing import Any

from .colors import parse_color, to_hex
from .render import shift_element

STYLES = ("linear", "sine", "quad", "cubic", "quart", "quint", "expo", "circ", "back", "elastic", "bounce", "spring")
VIRTUAL = ("dx", "dy", "scale", "scale_x", "scale_y", "opacity", "motion")
COLOR_KEYS = {"fill", "color", "color2", "highlight", "tint", "background", "from_color", "to_color"}
MAX_FRAMES = 300

ROBLOX_STYLE = {"linear": "Linear", "sine": "Sine", "quad": "Quad", "cubic": "Cubic", "quart": "Quart",
                "quint": "Quint", "expo": "Exponential", "circ": "Circular", "back": "Back", "elastic": "Elastic",
                "bounce": "Bounce", "spring": "Back"}
DOTWEEN_STYLE = {"linear": "Linear", "sine": "Sine", "quad": "Quad", "cubic": "Cubic", "quart": "Quart",
                 "quint": "Quint", "expo": "Expo", "circ": "Circ", "back": "Back", "elastic": "Elastic",
                 "bounce": "Bounce", "spring": "Back"}
DIRECTION = {"in": "In", "out": "Out", "in-out": "InOut"}



def _bounce_out(t: float) -> float:
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def _ease_in(style: str, t: float) -> float:
    if style == "linear":
        return t
    if style == "sine":
        return 1 - math.cos(t * math.pi / 2)
    if style == "quad":
        return t * t
    if style == "cubic":
        return t ** 3
    if style == "quart":
        return t ** 4
    if style == "quint":
        return t ** 5
    if style == "expo":
        return 0.0 if t <= 0 else 2 ** (10 * t - 10)
    if style == "circ":
        return 1 - math.sqrt(max(0.0, 1 - t * t))
    if style == "back":
        c1 = 1.70158
        return (c1 + 1) * t ** 3 - c1 * t * t
    if style == "elastic":
        if t <= 0 or t >= 1:
            return float(t >= 1)
        return -(2 ** (10 * t - 10)) * math.sin((t * 10 - 10.75) * (2 * math.pi / 3))
    if style == "bounce":
        return 1 - _bounce_out(1 - t)
    if style == "spring":
        def out(x: float) -> float:
            return 1 - math.exp(-6.5 * x) * math.cos(2.6 * math.pi * x)
        return 1 - out(1 - t) / out(1.0)
    raise ValueError(f"unknown easing style '{style}'")


def parse_ease(spec: Any) -> tuple:
    """Normalise an easing spec to ("step",), ("bezier", x1, y1, x2, y2) or ("ease", style, direction).

    Accepted: "linear", "step"/"hold", "ease-in"/"ease-out"/"ease-in-out" (cubic), any style from
    sine, quad, cubic, quart, quint, expo, circ, back, elastic, bounce with a direction, written
    "back-out", "out-back", "OutBack", "quad-in-out", "InOutQuad"...; or [x1, y1, x2, y2] (cubic-bezier).
    """
    if spec is None:
        return ("ease", "linear", "in")
    if isinstance(spec, (list, tuple)):
        if len(spec) != 4:
            raise ValueError("cubic-bezier ease must be [x1, y1, x2, y2]")
        x1, y1, x2, y2 = (float(v) for v in spec)
        if not (0 <= x1 <= 1 and 0 <= x2 <= 1):
            raise ValueError("cubic-bezier x1 and x2 must be between 0 and 1")
        return ("bezier", x1, y1, x2, y2)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", "-", str(spec)).lower()
    tokens = [t for t in re.split(r"[^a-z]+", text) if t]
    joined = "".join(tokens)
    if joined in ("step", "hold", "steps", "none", "jump"):
        return ("step",)
    aliases = {"exponential": "expo", "circular": "circ", "quadratic": "quad", "quartic": "quart",
               "quintic": "quint", "sinusoidal": "sine"}
    style, parts = None, []
    for tok in tokens:
        tok = aliases.get(tok, tok)
        if tok in STYLES:
            style = tok
        elif tok in ("in", "out", "inout"):
            parts.append(tok)
        elif tok in ("ease", "easing"):
            continue
        else:
            raise ValueError(
                f"Unknown ease '{spec}'. Use linear, step, ease-in/out/in-out, or <style>-<in|out|in-out> with style "
                f"in {', '.join(STYLES[1:])} (e.g. 'back-out', 'quad-in-out'), or a cubic-bezier [x1, y1, x2, y2].")
    if "inout" in parts or ("in" in parts and "out" in parts):
        direction = "in-out"
    elif "out" in parts:
        direction = "out"
    elif "in" in parts:
        direction = "in"
    else:
        direction = "in" if style == "linear" else "in-out"
    if style is None:
        style = "cubic"
    return ("ease", style, direction)


def ease_name(spec: Any) -> str:
    parsed = parse_ease(spec)
    if parsed[0] == "step":
        return "step"
    if parsed[0] == "bezier":
        return "cubic-bezier(" + ", ".join(f"{v:g}" for v in parsed[1:]) + ")"
    return "linear" if parsed[1] == "linear" else f"{parsed[1]}-{parsed[2]}"


def ease(spec: Any, t: float) -> float:
    """Eased progress for linear progress t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    parsed = parse_ease(spec)
    if parsed[0] == "step":
        return 1.0 if t >= 1 else 0.0
    if parsed[0] == "bezier":
        _, x1, y1, x2, y2 = parsed
        lo, hi = 0.0, 1.0
        for _ in range(40):
            s = (lo + hi) / 2
            x = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s * s * x2 + s ** 3
            if x < t:
                lo = s
            else:
                hi = s
        s = (lo + hi) / 2
        return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s * s * y2 + s ** 3
    _, style, direction = parsed
    if direction == "in":
        return _ease_in(style, t)
    if direction == "out":
        return 1 - _ease_in(style, 1 - t)
    return _ease_in(style, 2 * t) / 2 if t < 0.5 else 1 - _ease_in(style, 2 - 2 * t) / 2


def engine_ease(spec: Any) -> dict:
    """How this ease is called in common engines (empty for step / bezier)."""
    parsed = parse_ease(spec)
    if parsed[0] != "ease":
        return {}
    _, style, direction = parsed
    if style == "linear":
        return {"roblox": {"EasingStyle": "Linear", "EasingDirection": "Out"}, "dotween": "Linear"}
    return {"roblox": {"EasingStyle": ROBLOX_STYLE[style], "EasingDirection": DIRECTION[direction]},
            "dotween": DIRECTION[direction] + DOTWEEN_STYLE[style]}



def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def lerp_value(a: Any, b: Any, u: float, colors: dict, is_color: bool = False) -> Any:
    """Blend two property values. Numbers, colors, lists and objects of the same shape are
    interpolated part by part; anything else switches from a to b at the end of the segment."""
    if _is_number(a) and _is_number(b):
        return a + (b - a) * u
    if isinstance(a, str) and isinstance(b, str) and is_color:
        ca, cb = parse_color(a, colors), parse_color(b, colors)
        aa, ab = ca[3] / 255.0, cb[3] / 255.0
        alpha = aa + (ab - aa) * u
        if alpha <= 0:
            return to_hex((cb[0], cb[1], cb[2], 0))
        rgb = [((ca[i] * aa) + (cb[i] * ab - ca[i] * aa) * u) / alpha for i in range(3)]
        return to_hex(tuple(max(0, min(255, int(round(v)))) for v in rgb) + (int(round(alpha * 255)),))
    if isinstance(a, dict) and isinstance(b, dict) and set(a) == set(b):
        if a.get("type") != b.get("type"):
            return b if u >= 1 else a
        return {k: (a[k] if k == "type" else
                    lerp_value(a[k], b[k], u, colors, is_color or k in COLOR_KEYS or k in ("stops", "colors")))
                for k in a}
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        out = []
        for x, y in zip(a, b):
            if is_color and isinstance(x, (list, tuple)) and len(x) == 2 and _is_number(x[0]):
                out.append([lerp_value(x[0], y[0], u, colors), lerp_value(x[1], y[1], u, colors, True)])
            else:
                out.append(lerp_value(x, y, u, colors, is_color))
        return out
    return b if u >= 1 else a


def _is_color_property(prop: str) -> bool:
    parts = prop.split(".")
    return parts[-1] in COLOR_KEYS or (parts[-1] == "shadow" and "bevel" in parts)


def sample_track(track: dict, t: float, colors: dict) -> Any:
    keys = track["keyframes"]
    if t <= keys[0]["t"]:
        return keys[0]["value"]
    if t >= keys[-1]["t"]:
        return keys[-1]["value"]
    for a, b in zip(keys, keys[1:]):
        if a["t"] <= t <= b["t"]:
            span = b["t"] - a["t"]
            u = 1.0 if span <= 0 else ease(b.get("ease"), (t - a["t"]) / span)
            return lerp_value(a["value"], b["value"], u, colors, _is_color_property(track["property"]))
    return keys[-1]["value"]



def normalize_keyframes(keyframes: Any, duration: float, offset: float = 0.0) -> list[dict]:
    if not isinstance(keyframes, (list, tuple)) or not keyframes:
        raise ValueError("keyframes must be a non-empty list like [{\"t\": 0, \"value\": 0}, {\"t\": 0.3, \"value\": 1, \"ease\": \"back-out\"}]")
    out = []
    for item in keyframes:
        if isinstance(item, dict):
            if "t" not in item or "value" not in item:
                raise ValueError("each keyframe needs 't' (seconds) and 'value'")
            t, value, easing = item["t"], item["value"], item.get("ease")
        elif isinstance(item, (list, tuple)) and len(item) in (2, 3):
            t, value = item[0], item[1]
            easing = item[2] if len(item) == 3 else None
        else:
            raise ValueError("a keyframe is {t, value, ease?} or [t, value] or [t, value, ease]")
        try:
            t = float(t) + float(offset)
        except (TypeError, ValueError) as exc:
            raise ValueError("keyframe time 't' must be a number of seconds") from exc
        if t < -1e-9 or t > duration + 1e-9:
            raise ValueError(f"keyframe time {t:g}s is outside the animation (0 to {duration:g}s)")
        frame = {"t": round(max(0.0, min(duration, t)), 5), "value": value}
        if easing is not None:
            parse_ease(easing)
            frame["ease"] = easing
        out.append(frame)
    out.sort(key=lambda k: k["t"])
    return out


def track_targets(canvas: dict, target: str) -> list[dict]:
    """Elements addressed by a track target: an element id, 'group:<name>' or 'layer:<name>'."""
    if target.startswith("group:"):
        name = target.split(":", 1)[1]
        return [e for e in canvas["elements"] if e.get("group") == name]
    if target.startswith("layer:"):
        name = target.split(":", 1)[1]
        named = {l["name"] for l in canvas.get("layers") or []}
        if name == "base":
            return [e for e in canvas["elements"] if e.get("layer") not in named]
        return [e for e in canvas["elements"] if e.get("layer") == name]
    return [e for e in canvas["elements"] if e["id"] == target]


def _set_path(el: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    node = el
    for i, key in enumerate(parts[:-1]):
        cur = node.get(key)
        if key == "style" and i == 0 and isinstance(cur, str):
            cur = {"use": cur}
        elif not isinstance(cur, dict):
            cur = {"color": cur} if isinstance(cur, str) else {}
        else:
            cur = dict(cur)
        node[key] = cur
        node = cur
    node[parts[-1]] = value


def apply_animation(canvas: dict, animation: dict, t: float, colors: dict) -> tuple[dict, list[str]]:
    """Return a copy of ``canvas`` posed at time ``t`` (seconds) plus warnings about dead tracks."""
    frame = copy.deepcopy({k: v for k, v in canvas.items() if k != "animations"})
    warnings: list[str] = []
    offsets: dict[str, list[float]] = {}
    for track in animation.get("tracks", []):
        elements = track_targets(frame, track["target"])
        if not elements:
            warnings.append(f"track '{track['target']}' -> {track['property']}: target no longer exists")
            continue
        value = sample_track(track, t, colors)
        prop = track["property"]
        for el in elements:
            if track.get("pivot"):
                el["origin"] = list(track["pivot"])
            if prop == "motion":
                px, py, angle = motion_point(track.get("path") or {}, float(value))
                off = offsets.setdefault(el["id"], [0.0, 0.0])
                off[0] += px
                off[1] += py
                if (track.get("path") or {}).get("rotate"):
                    el["rotation"] = float(el.get("rotation", 0) or 0) + angle
                continue
            if prop in ("dx", "dy"):
                off = offsets.setdefault(el["id"], [0.0, 0.0])
                off[0 if prop == "dx" else 1] += float(value)
            elif prop == "opacity":
                _set_path(el, "style.opacity", max(0.0, min(1.0, float(value))))
            elif prop == "scale":
                el["scale_x"] = el["scale_y"] = float(value)
            else:
                _set_path(el, prop, value)
    for el in frame["elements"]:
        if el["id"] in offsets:
            shift_element(el, *offsets[el["id"]])
    return frame, warnings


_PATHS: OrderedDict[str, tuple] = OrderedDict()


def motion_path(spec: dict) -> tuple:
    """(points, cumulative lengths) of a motion path {"d": svg path} or {"points": [[x, y], ...]}."""
    from . import geometry as geo
    key = repr(spec.get("d") or spec.get("points"))
    if key in _PATHS:
        _PATHS.move_to_end(key)
        return _PATHS[key]
    if spec.get("d"):
        subs = geo.parse_svg_path(str(spec["d"]), 8.0)
        if not subs:
            raise ValueError("motion path d has no drawable segments")
        pts = [(float(x), float(y)) for x, y in subs[0][0]]
    elif spec.get("points"):
        pts = [(float(p[0]), float(p[1])) for p in spec["points"]]
    else:
        raise ValueError('a "motion" track needs path {"d": "M 0 0 C ..."} or {"points": [[x, y], ...]}')
    if len(pts) < 2:
        raise ValueError("a motion path needs at least 2 points")
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    while len(_PATHS) >= 128:
        _PATHS.popitem(last=False)
    _PATHS[key] = (pts, acc)
    return _PATHS[key]


def motion_point(spec: dict, progress: float) -> tuple[float, float, float]:
    """Offset from the path start and the direction of travel (degrees) at progress 0..1 along the path."""
    pts, acc = motion_path(spec)
    total = acc[-1] or 1.0
    d = max(0.0, min(1.0, progress)) * total
    for i in range(1, len(pts)):
        if d <= acc[i] or i == len(pts) - 1:
            seg = acc[i] - acc[i - 1] or 1e-9
            u = (d - acc[i - 1]) / seg
            (ax, ay), (bx, by) = pts[i - 1], pts[i]
            x, y = ax + (bx - ax) * u, ay + (by - ay) * u
            return x - pts[0][0], y - pts[0][1], math.degrees(math.atan2(by - ay, bx - ax))
    return pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1], 0.0


def frame_times(animation: dict, fps: float | None = None) -> list[float]:
    """Sample times for export. Looping animations stop one frame short so the loop does not stutter."""
    fps = float(fps or animation.get("fps", 30))
    if not 1 <= fps <= 120:
        raise ValueError("fps must be between 1 and 120")
    duration = float(animation["duration"])
    count = max(1, int(round(duration * fps)))
    times = [i / fps for i in range(count)]
    if not animation.get("loop"):
        times.append(duration)
    if len(times) > MAX_FRAMES:
        raise ValueError(f"{len(times)} frames is over the limit of {MAX_FRAMES}; lower fps or shorten the animation")
    return times


def describe(name: str, animation: dict, canvas: dict) -> dict:
    """Engine-neutral description of an animation (what export_animation(format='json') writes)."""
    tracks = []
    for track in animation.get("tracks", []):
        elements = track_targets(canvas, track["target"])
        keys = []
        for i, key in enumerate(track["keyframes"]):
            item = {"t": key["t"], "value": key["value"]}
            if i > 0:
                item["ease"] = ease_name(key.get("ease"))
                item.update(engine_ease(key.get("ease")))
            keys.append(item)
        entry = {"target": track["target"], "property": track["property"],
                 "elements": [e["id"] for e in elements],
                 "layers": sorted({e.get("group") or "base" for e in elements}), "keyframes": keys}
        if track.get("pivot"):
            entry["pivot"] = track["pivot"]
        tracks.append(entry)
    return {"animation": name, "canvas": canvas["id"], "canvas_size": [canvas["width"], canvas["height"]],
            "duration": animation["duration"], "loop": bool(animation.get("loop")), "fps": animation.get("fps", 30),
            "tracks": tracks}
