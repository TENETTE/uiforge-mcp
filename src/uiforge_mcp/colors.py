"""Color parsing and theme-token resolution."""

from __future__ import annotations

import re
from typing import Any

RGBA = tuple[int, int, int, int]

NAMED = {
    "transparent": (0, 0, 0, 0),
    "none": (0, 0, 0, 0),
    "white": (255, 255, 255, 255),
    "black": (0, 0, 0, 255),
    "red": (255, 0, 0, 255),
    "green": (0, 200, 0, 255),
    "blue": (0, 0, 255, 255),
    "yellow": (255, 221, 0, 255),
    "orange": (255, 140, 0, 255),
    "purple": (150, 60, 220, 255),
    "cyan": (0, 220, 255, 255),
    "magenta": (255, 0, 220, 255),
    "gray": (128, 128, 128, 255),
    "grey": (128, 128, 128, 255),
}


_CSS = """aliceblue f0f8ff antiquewhite faebd7 aqua 00ffff aquamarine 7fffd4 azure f0ffff beige f5f5dc bisque ffe4c4 blanchedalmond ffebcd blueviolet 8a2be2 brown a52a2a burlywood deb887 cadetblue 5f9ea0 chartreuse 7fff00 chocolate d2691e coral ff7f50 cornflowerblue 6495ed cornsilk fff8dc crimson dc143c darkblue 00008b darkcyan 008b8b darkgoldenrod b8860b darkgray a9a9a9 darkgrey a9a9a9 darkgreen 006400 darkkhaki bdb76b darkmagenta 8b008b darkolivegreen 556b2f darkorange ff8c00 darkorchid 9932cc darkred 8b0000 darksalmon e9967a darkseagreen 8fbc8f darkslateblue 483d8b darkslategray 2f4f4f darkslategrey 2f4f4f darkturquoise 00ced1 darkviolet 9400d3 deeppink ff1493 deepskyblue 00bfff dimgray 696969 dimgrey 696969 dodgerblue 1e90ff firebrick b22222 floralwhite fffaf0 forestgreen 228b22 fuchsia ff00ff gainsboro dcdcdc ghostwhite f8f8ff gold ffd700 goldenrod daa520 greenyellow adff2f honeydew f0fff0 hotpink ff69b4 indianred cd5c5c indigo 4b0082 ivory fffff0 khaki f0e68c lavender e6e6fa lavenderblush fff0f5 lawngreen 7cfc00 lemonchiffon fffacd lightblue add8e6 lightcoral f08080 lightcyan e0ffff lightgoldenrodyellow fafad2 lightgray d3d3d3 lightgrey d3d3d3 lightgreen 90ee90 lightpink ffb6c1 lightsalmon ffa07a lightseagreen 20b2aa lightskyblue 87cefa lightslategray 778899 lightslategrey 778899 lightsteelblue b0c4de lightyellow ffffe0 lime 00ff00 limegreen 32cd32 linen faf0e6 maroon 800000 mediumaquamarine 66cdaa mediumblue 0000cd mediumorchid ba55d3 mediumpurple 9370db mediumseagreen 3cb371 mediumslateblue 7b68ee mediumspringgreen 00fa9a mediumturquoise 48d1cc mediumvioletred c71585 midnightblue 191970 mintcream f5fffa mistyrose ffe4e1 moccasin ffe4b5 navajowhite ffdead navy 000080 oldlace fdf5e6 olive 808000 olivedrab 6b8e23 orangered ff4500 orchid da70d6 palegoldenrod eee8aa palegreen 98fb98 paleturquoise afeeee palevioletred db7093 papayawhip ffefd5 peachpuff ffdab9 peru cd853f pink ffc0cb plum dda0dd powderblue b0e0e6 rebeccapurple 663399 rosybrown bc8f8f royalblue 4169e1 saddlebrown 8b4513 salmon fa8072 sandybrown f4a460 seagreen 2e8b57 seashell fff5ee sienna a0522d silver c0c0c0 skyblue 87ceeb slateblue 6a5acd slategray 708090 slategrey 708090 snow fffafa springgreen 00ff7f steelblue 4682b4 tan d2b48c teal 008080 thistle d8bfd8 tomato ff6347 turquoise 40e0d0 violet ee82ee wheat f5deb3 whitesmoke f5f5f5 yellowgreen 9acd32"""
_toks = _CSS.split()
for _name, _hex in zip(_toks[0::2], _toks[1::2]):
    NAMED.setdefault(_name, (int(_hex[0:2], 16), int(_hex[2:4], 16), int(_hex[4:6], 16), 255))

_FUNC = re.compile(r"^rgba?\(([^)]+)\)$")
_HSL = re.compile(r"^hsla?\(([^)]+)\)$")


def _split_args(body: str) -> list[str]:
    body = body.replace("/", " ").replace(",", " ")
    return [p for p in body.split() if p]


def _num(p: str, scale: float = 1.0) -> float:
    """'50%' -> 0.5*scale*... ; plain numbers pass through."""
    p = p.strip()
    if p.endswith("%"):
        return float(p[:-1]) / 100.0 * scale
    return float(p)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    h = (h % 360) / 360.0
    if s == 0:
        return (l, l, l)
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def hue(t: float) -> float:
        t %= 1.0
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    return (hue(h + 1 / 3), hue(h), hue(h - 1 / 3))


def _clamp8(v: float) -> int:
    return max(0, min(255, int(round(v))))


def parse_color(value: Any, theme_colors: dict[str, Any] | None = None, _depth: int = 0) -> RGBA:
    """Parse a color into an (r, g, b, a) tuple of 0-255 ints.

    Accepted forms:
      "#rgb", "#rgba", "#rrggbb", "#rrggbbaa", "rgb(r,g,b)", "rgba(r,g,b,a)", "hsl(h,s%,l%)",
      "hsla(h,s%,l%,a)", all CSS color names, [r, g, b] / [r, g, b, a] lists, and "$token" theme references.
      Any string form may end with "@alpha" (0-1), e.g. "#ffffff@0.4", "$primary@0.5".
    """
    if value is None:
        return (0, 0, 0, 0)
    if isinstance(value, (list, tuple)):
        if len(value) not in (3, 4):
            raise ValueError(f"Color list must have 3 or 4 numbers, got {value!r}")
        r, g, b = (_clamp8(v) for v in value[:3])
        a = 255
        if len(value) == 4:
            av = float(value[3])
            a = _clamp8(av * 255 if av <= 1 else av)
        return (r, g, b, a)
    if not isinstance(value, str):
        raise ValueError(f"Unsupported color value: {value!r}")

    text = value.strip()
    alpha_mul = 1.0
    if "@" in text:
        text, _, alpha_text = text.rpartition("@")
        try:
            alpha_mul = max(0.0, min(1.0, float(alpha_text)))
        except ValueError as exc:
            raise ValueError(f"Bad alpha suffix in color {value!r}") from exc
        text = text.strip()

    if text.startswith("$"):
        if _depth > 8:
            raise ValueError(f"Theme color reference loop at {value!r}")
        key = text[1:]
        if not theme_colors or key not in theme_colors:
            known = ", ".join(sorted(theme_colors or {})) or "(theme has no colors)"
            raise ValueError(f"Unknown theme color '${key}'. Known: {known}")
        r, g, b, a = parse_color(theme_colors[key], theme_colors, _depth + 1)
    elif text.startswith("#"):
        h = text[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8) or not re.fullmatch(r"[0-9a-fA-F]+", h):
            raise ValueError(f"Bad hex color: {value!r}")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16) if len(h) == 8 else 255
    elif (m := _FUNC.match(text.lower())) is not None:
        parts = _split_args(m.group(1))
        if len(parts) not in (3, 4):
            raise ValueError(f"Bad rgb()/rgba() color: {value!r}")
        try:
            r, g, b = (_clamp8(_num(p, 255.0)) for p in parts[:3])
            a = 255
            if len(parts) == 4:
                av = _num(parts[3], 1.0)
                a = _clamp8(av * 255 if av <= 1 else av)
        except ValueError as exc:
            raise ValueError(f"Bad rgb()/rgba() color: {value!r}") from exc
    elif (m := _HSL.match(text.lower())) is not None:
        parts = _split_args(m.group(1))
        if len(parts) not in (3, 4):
            raise ValueError(f"Bad hsl()/hsla() color: {value!r} (use hsl(h, s%, l%) or hsla(h, s%, l%, a))")
        try:
            h = float(parts[0].removesuffix("deg"))
            sat = max(0.0, min(1.0, _num(parts[1]) if parts[1].endswith("%") else float(parts[1]) / 100))
            lig = max(0.0, min(1.0, _num(parts[2]) if parts[2].endswith("%") else float(parts[2]) / 100))
            rf, gf, bf = _hsl_to_rgb(h, sat, lig)
            r, g, b = _clamp8(rf * 255), _clamp8(gf * 255), _clamp8(bf * 255)
            a = 255
            if len(parts) == 4:
                av = _num(parts[3], 1.0)
                a = _clamp8(av * 255 if av <= 1 else av)
        except ValueError as exc:
            raise ValueError(f"Bad hsl()/hsla() color: {value!r}") from exc
    elif text.lower() in NAMED:
        r, g, b, a = NAMED[text.lower()]
    else:
        raise ValueError(
            f"Unknown color {value!r}. Use #rrggbb, #rrggbbaa, rgba(r,g,b,a), hsl(h,s%,l%), a CSS color name, or a $theme token."
        )
    return (r, g, b, _clamp8(a * alpha_mul))


def to_hex(color: RGBA) -> str:
    r, g, b, a = color
    return f"#{r:02x}{g:02x}{b:02x}" + (f"{a:02x}" if a != 255 else "")
