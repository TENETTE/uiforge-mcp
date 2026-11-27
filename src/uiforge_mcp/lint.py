"""Design lint for review_canvas: the small inconsistencies that make a kit look unpolished.

Near-miss alignment (edges 0.5-2 units apart), too many corner radii / stroke widths / text sizes, and hard-coded
colours where the theme has tokens. All findings are "info": they are judgement calls, not errors.
"""

from __future__ import annotations

from typing import Any

from .render import _stroke_specs, resolve_style


def _colors_in(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for key in ("fill", "color", "stroke", "stops", "colors", "from", "to"):
            if key in value:
                _colors_in(value[key], out)
    elif isinstance(value, list):
        for item in value:
            _colors_in(item, out)


def design_lint(r, canvas: dict, theme: dict) -> list[tuple[str, str, list[str] | None]]:
    found: list[tuple[str, str, list[str] | None]] = []
    W, H = float(canvas["width"]), float(canvas["height"])
    elements = [e for e in canvas["elements"] if e.get("visible", True) and not e.get("_decor")]

    edges: dict[str, list[tuple[float, str]]] = {"x": [], "y": []}
    for el in elements:
        try:
            x0, y0, x1, y1 = r.element_box(el)
        except ValueError:
            continue
        if x1 - x0 >= W * 0.9 and y1 - y0 >= H * 0.9:
            continue
        edges["x"] += [(x0, el["id"]), (x1, el["id"]), ((x0 + x1) / 2, el["id"])]
        edges["y"] += [(y0, el["id"]), (y1, el["id"]), ((y0 + y1) / 2, el["id"])]
    misses: list[tuple[float, str, str, float, float, str]] = []
    for axis, items in edges.items():
        items.sort()
        for (a, ida), (b, idb) in zip(items, items[1:]):
            if ida != idb and 0.5 <= b - a <= 2.0:
                misses.append((b - a, axis, ida, a, b, idb))
    if misses:
        misses.sort()
        text = "; ".join(f"{ida} {axis}={a:g} vs {idb} {axis}={b:g}" for _, axis, ida, a, b, idb in misses[:6])
        ids = sorted({m[2] for m in misses[:6]} | {m[5] for m in misses[:6]})
        found.append(("alignment", f"edges or centres that almost line up (0.5-2 units apart): {text}. "
                                   "Snap them with align_elements or exact coordinates.", ids))

    radii, widths, sizes = set(), set(), set()
    raw, tokenised = [], 0
    for el in elements:
        st = resolve_style(el.get("style"), theme)
        if el["type"] == "rect" and el.get("radius"):
            rad = el["radius"]
            radii.add(tuple(rad) if isinstance(rad, list) else float(rad))
        try:
            for sp in _stroke_specs(st, {}):
                widths.add(round(sp["width"], 2))
        except ValueError:
            pass
        if el["type"] == "text":
            sizes.add(float(el.get("size") or st.get("size") or 24))
        found_colors: list[str] = []
        _colors_in(el.get("style") if isinstance(el.get("style"), dict) else None, found_colors)
        for col in found_colors:
            if col.startswith("$"):
                tokenised += 1
            elif col.strip().lower() not in ("none", "transparent", ""):
                raw.append(el["id"])
    if len(radii) > 4:
        found.append(("consistency", f"{len(radii)} different corner radii ({', '.join(str(v) for v in sorted(radii, key=str)[:8])}) - "
                                     "a kit usually uses 2-3 (small / medium / large)", None))
    if len(widths) > 4:
        found.append(("consistency", f"{len(widths)} different stroke widths ({', '.join(f'{v:g}' for v in sorted(widths))}) - "
                                     "pick 2-3 and reuse them", None))
    if len(sizes) > 6:
        found.append(("consistency", f"{len(sizes)} different text sizes ({', '.join(f'{v:g}' for v in sorted(sizes))}) - "
                                     "a type scale of 4-6 sizes reads cleaner", None))
    if len(theme.get("colors", {})) >= 3 and raw and len(raw) > tokenised:
        found.append(("tokens", f"{len(raw)} colours are hard-coded although the theme has tokens - use $tokens so "
                                "theme modes and restyle reach them", sorted(set(raw))[:20]))
    return found
