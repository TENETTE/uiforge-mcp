"""W3C Design Tokens (DTCG) JSON: read colour / number tokens in, write the theme out.

Format: nested groups; a token is an object with "$value" (and "$type", possibly inherited from its group).
Aliases look like "{group.token}". Used by Tokens Studio, Penpot, Style Dictionary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ALIAS = re.compile(r"^\{([^{}]+)\}$")


def _name(parts: list[str]) -> str:
    return "-".join(re.sub(r"[^\w-]+", "-", p).strip("-").lower() for p in parts if p)


def _dimension(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, dict) and "value" in value:
        scale = 16.0 if str(value.get("unit", "px")) == "rem" else 1.0
        return float(value["value"]) * scale
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(px|rem|em)?\s*", value)
        if m:
            return float(m.group(1)) * (16.0 if m.group(2) in ("rem", "em") else 1.0)
    return None


def _color(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        comps = value.get("components")
        if isinstance(comps, list) and len(comps) >= 3:
            rgb = "".join(f"{max(0, min(255, round(float(c) * 255))):02x}" for c in comps[:3])
            alpha = float(value.get("alpha", 1))
            return f"#{rgb}" + (f"{round(alpha * 255):02x}" if alpha < 1 else "")
        if "hex" in value:
            return str(value["hex"])
    return None


def read_dtcg(data: dict | str) -> tuple[dict, dict]:
    """(colours, numbers) from a DTCG document or a path to one."""
    if isinstance(data, str):
        path = Path(data).expanduser()
        if not path.is_file():
            raise ValueError(f"tokens file not found: {path.resolve()} - pass the JSON object or an absolute path")
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("tokens must be a DTCG JSON object: nested groups of {\"$value\": ..., \"$type\": ...}")
    colors: dict[str, str] = {}
    numbers: dict[str, float] = {}

    def walk(node: dict, path: list[str], inherited: str | None) -> None:
        kind = node.get("$type", inherited)
        if "$value" in node:
            name, value = _name(path), node["$value"]
            alias = _ALIAS.match(value) if isinstance(value, str) else None
            if alias:
                target = _name(alias.group(1).split("."))
                (colors if kind == "color" else numbers if kind in ("dimension", "number") else colors)[name] = f"${target}"
            elif kind == "color" and _color(value):
                colors[name] = _color(value)
            elif kind in ("dimension", "number", "fontWeight", "duration") and _dimension(value) is not None:
                numbers[name] = _dimension(value)
            return
        for key, child in node.items():
            if not key.startswith("$") and isinstance(child, dict):
                walk(child, path + [key], kind)

    walk(data, [], None)
    for name, value in list(numbers.items()):
        seen = set()
        while isinstance(value, str) and value.startswith("$") and value[1:] in numbers and value not in seen:
            seen.add(value)
            value = numbers[value[1:]]
        if isinstance(value, str):
            numbers.pop(name)
        else:
            numbers[name] = value
    if not colors and not numbers:
        raise ValueError("no colour or number tokens found - check that tokens have \"$value\" and a "
                         "\"$type\" of color / dimension / number (on the token or its group)")
    return colors, numbers


def write_dtcg(colors: dict, numbers: dict, text_styles: dict, modes: dict, mode_numbers: dict) -> dict:
    doc: dict[str, Any] = {}
    if colors:
        doc["color"] = {k: {"$type": "color", "$value": v} for k, v in colors.items()}
    if numbers:
        doc["size"] = {k: {"$type": "dimension", "$value": f"{v:g}px"} for k, v in numbers.items()}
    if text_styles:
        doc["typography"] = {
            k: {"$type": "typography", "$value": {
                key: val for key, val in (("fontFamily", ts.get("font")), ("fontSize", f"{ts['size']:g}px" if ts.get("size") else None),
                                          ("fontWeight", ts.get("weight")),
                                          ("letterSpacing", f"{ts['letter_spacing']:g}px" if ts.get("letter_spacing") else None))
                if val is not None}}
            for k, ts in text_styles.items()}
    if modes or any(mode_numbers.values()):
        doc["$extensions"] = {"uiforge-mcp": {"modes": {
            m: {**{k: v for k, v in modes.get(m, {}).items()}, **{k: v for k, v in mode_numbers.get(m, {}).items()}}
            for m in sorted(set(modes) | set(mode_numbers))}}}
    return doc


def _yaml_scalar(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return text


def _front_matter(text: str) -> dict:
    """The YAML front matter of a DESIGN.md (nested maps of scalars - the subset DESIGN.md files use)."""
    m = re.match(r"﻿?---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return {}
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, value = raw.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        key = _yaml_scalar(key)
        if value.strip():
            parent[str(key)] = _yaml_scalar(value.split(" #")[0])
        else:
            parent[str(key)] = {}
            stack.append((indent, parent[str(key)]))
    return root


def read_design_md(text: str) -> tuple[dict, dict, dict]:
    """(colors, numbers, styles) from a DESIGN.md: YAML front matter (colors, typography, rounded, spacing,
    other number maps), or failing that "| name | #hex |" table rows and "- name: #hex" lines."""
    fm = _front_matter(text)
    colors: dict = {}
    numbers: dict = {}
    styles: dict = {}
    for key, value in (fm.get("colors") or {}).items():
        col = _color(value) if not isinstance(value, dict) else None
        if col and col.startswith("{"):
            col = "$" + _name([col.strip("{}").split(".")[-1]])
        if col:
            colors[_name([str(key)])] = col
    prefixes = {"rounded": "radius", "radius": "radius", "spacing": "space", "space": "space"}
    for group, values in fm.items():
        if group in ("colors", "typography") or not isinstance(values, dict):
            continue
        for key, value in values.items():
            num = _dimension(value)
            if num is not None:
                numbers[f"{prefixes.get(group, _name([group]))}-{_name([str(key)])}"] = num
    for key, spec in (fm.get("typography") or {}).items():
        if not isinstance(spec, dict):
            continue
        style: dict = {}
        if spec.get("fontFamily"):
            style["font"] = str(spec["fontFamily"]).split(",")[0].strip().strip("'\"")
        for src, dst in (("fontSize", "size"), ("letterSpacing", "letter_spacing")):
            num = _dimension(spec.get(src))
            if num is not None:
                style[dst] = num
        if spec.get("fontWeight") is not None:
            style["weight"] = spec["fontWeight"]
        if spec.get("color"):
            col = _color(spec["color"]) or (f"${_name([str(spec['color']).strip('{}').split('.')[-1]])}"
                                             if str(spec["color"]).startswith("{") else None)
            if col:
                style["fill"] = col
        if style:
            styles[_name([str(key)])] = style
    if not fm:
        for name, value in re.findall(r"^\|\s*`?([\w .-]+?)`?\s*\|\s*`?(#[0-9a-fA-F]{3,8})`?", text, re.M) + \
                re.findall(r"^[-*]\s*\**`?([\w .-]+?)`?\**\s*[:=-]\s*`?(#[0-9a-fA-F]{3,8})\b", text, re.M):
            colors[_name(name.strip().lower().split())] = value.lower()
    if not (colors or numbers or styles):
        raise ValueError("no design tokens found in this DESIGN.md (expected YAML front matter with colors / "
                         "typography / rounded / spacing, or '| name | #hex |' rows)")
    return colors, numbers, styles


def write_design_md(name: str, colors: dict, numbers: dict, text_styles: dict, modes: dict, styles: dict) -> str:
    """A DESIGN.md: YAML front matter tokens for tools and agents, then readable sections for people."""
    def q(v: Any) -> str:
        return f'"{v}"' if isinstance(v, str) else f"{v:g}" if isinstance(v, float) else str(v)
    groups: dict[str, dict] = {"rounded": {}, "spacing": {}, "numbers": {}}
    for key, value in numbers.items():
        if key.startswith("radius-"):
            groups["rounded"][key[7:]] = f"{value:g}px"
        elif key.startswith("space-"):
            groups["spacing"][key[6:]] = f"{value:g}px"
        else:
            groups["numbers"][key] = value
    fm = ["---", f"name: {q(name)}", "colors:"] + [f"  {k}: {q(v)}" for k, v in colors.items()]
    if text_styles:
        fm.append("typography:")
        for key, ts in text_styles.items():
            fm.append(f"  {key}:")
            for src, dst, unit in (("font", "fontFamily", ""), ("size", "fontSize", "px"), ("weight", "fontWeight", ""),
                                   ("letter_spacing", "letterSpacing", "px"), ("color", "color", "")):
                if ts.get(src) is not None:
                    v = ts[src]
                    fm.append(f"    {dst}: {q(f'{v:g}{unit}' if unit and isinstance(v, (int, float)) else v)}")
    for group, values in groups.items():
        if values:
            fm.append(f"{group}:")
            fm += [f"  {k}: {q(v)}" for k, v in values.items()]
    fm.append("---")
    body = ["", f"# {name} design system", "",
            "Tokens above are the source of truth (generated by uiforge-mcp). Use them by name; never hand-type colours.",
            "", "## Colors", "", "| Token | Value |", "| --- | --- |"]
    body += [f"| `{k}` | `{v}` |" for k, v in colors.items()]
    for mode, vals in modes.items():
        body += ["", f"### Mode: {mode}", "", "| Token | Value |", "| --- | --- |"]
        body += [f"| `{k}` | `{v}` |" for k, v in vals.items()]
    if text_styles:
        body += ["", "## Typography", "", "| Style | Font | Size | Weight |", "| --- | --- | --- | --- |"]
        body += [f"| `{k}` | {ts.get('font', '')} | {ts.get('size', '')} | {ts.get('weight', '')} |"
                 for k, ts in text_styles.items()]
    if numbers:
        body += ["", "## Spacing and shape", ""] + [f"- `{k}`: {v:g}" for k, v in numbers.items()]
    comp = {k: v for k, v in styles.items() if k not in text_styles}
    if comp:
        body += ["", "## Component styles", ""]
        body += [f"- `{k}`: " + ", ".join(f"{a} {json.dumps(b, ensure_ascii=False)}" for a, b in v.items())
                 for k, v in comp.items()]
    return "\n".join(fm + body) + "\n"


def _oklch_to_hex(l_val: float, c_val: float, h_deg: float) -> str:
    """Convert CSS oklch(L C H) into clamped sRGB #rrggbb."""
    import math
    if l_val > 1.0:
        l_val /= 100.0
    hr = math.radians(h_deg)
    a = c_val * math.cos(hr)
    b = c_val * math.sin(hr)
    l_ = l_val + 0.3963377774 * a + 0.2158037573 * b
    m_ = l_val - 0.1055613458 * a - 0.0638541728 * b
    s_ = l_val - 0.0894841775 * a - 1.2914855480 * b
    l3, m3, s3 = l_ ** 3, m_ ** 3, s_ ** 3
    rl = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
    gl = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
    bl = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3

    def enc(v: float) -> int:
        v = max(0.0, min(1.0, v))
        s = 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1.0 / 2.4)) - 0.055
        return max(0, min(255, round(s * 255)))

    return f"#{enc(rl):02x}{enc(gl):02x}{enc(bl):02x}"


def _hsl_to_hex(h_deg: float, s_pct: float, l_pct: float) -> str:
    import colorsys
    r, g, b = colorsys.hls_to_rgb((h_deg % 360.0) / 360.0, max(0.0, min(1.0, l_pct / 100.0)), max(0.0, min(1.0, s_pct / 100.0)))
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _parse_css_color(val: str) -> str | None:
    s = val.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", s):
        return s.lower()
    if re.match(r"^(?:rgba?|hsla?)\s*\(", s, re.I):
        return s
    # Tailwind v4 / modern CSS oklch(0.72 0.15 55) or oklch(72% 0.15 55)
    m = re.match(r"^oklch\(\s*([\d.]+)%?\s+([\d.]+)\s+([\d.]+)(?:deg)?(?:\s*/\s*[\d.%]+)?\s*\)$", s, re.I)
    if m:
        return _oklch_to_hex(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    # shadcn/ui raw HSL triplet: "222.2 47.4% 11.2%"
    m = re.fullmatch(r"([\d.]+)\s+([\d.]+)%\s+([\d.]+)%", s)
    if m:
        return _hsl_to_hex(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return None


def read_css_tokens(text: str) -> tuple[dict[str, str], dict[str, float], dict[str, dict[str, str]]]:
    """Parse CSS custom properties (:root, Tailwind v4 @theme, shadcn HSL triplets, oklch(), .dark / [data-theme=light]).

    Returns ``(colors, numbers, modes)``.
    """
    clean = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    colors: dict[str, str] = {}
    numbers: dict[str, float] = {}
    modes: dict[str, dict[str, str]] = {}

    def _strip_prefix(raw_name: str) -> str:
        n = raw_name.strip().lstrip("-").lower()
        for pref in ("color-", "ui-", "tw-"):
            if n.startswith(pref):
                n = n[len(pref):]
                break
        return _name([n])

    def _ingest_decls(block_body: str, target_colors: dict[str, str], collect_nums: bool) -> None:
        for raw_key, raw_val in re.findall(r"--([\w-]+)\s*:\s*([^;}\n]+)", block_body):
            val = raw_val.strip()
            if val.startswith("var("):
                continue
            key = _strip_prefix(raw_key)
            if not key:
                continue
            col = _parse_css_color(val)
            if col:
                target_colors[key] = col
                continue
            if collect_nums:
                num = _dimension(val)
                if num is not None:
                    numbers[key] = num

    blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", clean)
    if blocks:
        for sel, body in blocks:
            s_low = sel.lower()
            if ".dark" in s_low or 'data-theme="dark"' in s_low or "data-theme='dark'" in s_low:
                _ingest_decls(body, modes.setdefault("dark", {}), False)
            elif ".light" in s_low or 'data-theme="light"' in s_low or "data-theme='light'" in s_low:
                _ingest_decls(body, modes.setdefault("light", {}), False)
            else:
                _ingest_decls(body, colors, True)
    else:
        _ingest_decls(clean, colors, True)

    modes = {k: v for k, v in modes.items() if v}
    if not colors and not numbers and not modes:
        raise ValueError("No CSS custom property tokens found (expected --name: #hex | oklch(...) | hsl | px/rem)")
    return colors, numbers, modes
