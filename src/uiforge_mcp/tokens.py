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
