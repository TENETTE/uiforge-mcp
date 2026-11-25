"""Export helpers: trimming, 9-slice detection, atlases and engine metadata."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ENGINES = ("generic", "unity", "unreal", "roblox", "godot")
ROBLOX_MAX = 1024


def trim(img: Image.Image, padding: int = 0) -> tuple[Image.Image, tuple[int, int]]:
    """Crop transparent margins. Returns (image, (offset_x, offset_y))."""
    box = img.getchannel("A").getbbox()
    if box is None:
        return img, (0, 0)
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0 - padding), max(0, y0 - padding)
    x1, y1 = min(img.width, x1 + padding), min(img.height, y1 + padding)
    return img.crop((x0, y0, x1, y1)), (x0, y0)


def _band(arr: np.ndarray, axis: int, tol: int) -> tuple[int, int]:
    """Longest run of identical rows/columns containing the centre. Returns (start, end) inclusive."""
    lines = arr if axis == 0 else arr.transpose(1, 0, 2)
    n = lines.shape[0]
    c = n // 2
    ref = lines[c].astype(np.int16)

    def same(i: int) -> bool:
        return int(np.abs(lines[i].astype(np.int16) - ref).max()) <= tol

    a = c
    while a > 0 and same(a - 1):
        a -= 1
    b = c
    while b < n - 1 and same(b + 1):
        b += 1
    return a, b


def detect_nine_slice(img: Image.Image, tolerance: int = 1, block_x: bool = False, block_y: bool = False) -> dict:
    """Find 9-slice borders: the largest centre band whose columns (and rows) are identical.

    block_x / block_y force an axis to be non-stretchable. The caller sets them when a gradient
    runs along that axis: a slow gradient has short runs of identical pixels that would
    otherwise be mistaken for a stretchable centre.
    """
    arr = np.asarray(img.convert("RGBA")).copy()
    arr[arr[..., 3] == 0] = 0
    h, w = arr.shape[:2]
    cx0, cx1 = _band(arr, 1, tolerance)
    cy0, cy1 = _band(arr, 0, tolerance)
    stretch_x = (cx1 - cx0 + 1) >= 3 and not block_x
    stretch_y = (cy1 - cy0 + 1) >= 3 and not block_y
    if stretch_x:
        left, right = cx0 + 1, w - cx1
    else:
        left = max(0, (w - 1) // 2)
        right = max(0, w - left - 1)
    if stretch_y:
        top, bottom = cy0 + 1, h - cy1
    else:
        top = max(0, (h - 1) // 2)
        bottom = max(0, h - top - 1)
    return {"left": int(left), "top": int(top), "right": int(right), "bottom": int(bottom),
            "stretch_x": bool(stretch_x), "stretch_y": bool(stretch_y)}


def minimize_nine_slice(img: Image.Image, borders: dict, keep: int = 4) -> tuple[Image.Image, dict]:
    """Collapse the stretchable centre to ``keep`` pixels so the texture is as small as possible."""
    w, h = img.size
    l, t, r, b = borders["left"], borders["top"], borders["right"], borders["bottom"]
    out = img
    if borders.get("stretch_x", True) and w - l - r > keep:
        new = Image.new("RGBA", (l + keep + r, out.height), (0, 0, 0, 0))
        new.paste(out.crop((0, 0, l + keep, out.height)), (0, 0))
        new.paste(out.crop((w - r, 0, w, out.height)), (l + keep, 0))
        out = new
    if borders.get("stretch_y", True) and h - t - b > keep:
        new = Image.new("RGBA", (out.width, t + keep + b), (0, 0, 0, 0))
        new.paste(out.crop((0, 0, out.width, t + keep)), (0, 0))
        new.paste(out.crop((0, h - b, out.width, h)), (0, t + keep))
        out = new
    return out, dict(borders)


def scale_borders(borders: dict, factor: float) -> dict:
    out = dict(borders)
    for key in ("left", "top", "right", "bottom"):
        out[key] = int(round(borders[key] * factor))
    return out


def engine_metadata(engine: str, size: tuple[int, int], borders: dict | None, scale: float) -> dict:
    """Engine-ready numbers for one exported image."""
    w, h = size
    meta: dict = {}
    if engine in ("unity", "generic"):
        meta["unity"] = {
            "textureType": "Sprite (2D and UI)", "spriteMode": "Single", "meshType": "Full Rect",
            "pixelsPerUnit": 100 * scale, "generateMipMaps": False,
        }
        if borders:
            meta["unity"]["spriteBorder_LBRT"] = [borders["left"], borders["bottom"], borders["right"], borders["top"]]
            meta["unity"]["imageType"] = "Sliced"
    if engine in ("unreal", "generic"):
        meta["unreal"] = {"compression": "UserInterface2D (RGBA)", "textureGroup": "UI", "mipGen": "NoMipmaps",
                          "sRGB": True, "imageSize": [round(w / scale), round(h / scale)]}
        if borders:
            meta["unreal"]["drawAs"] = "Box"
            meta["unreal"]["margin_LTRB"] = [round(borders["left"] / w, 5), round(borders["top"] / h, 5),
                                             round(borders["right"] / w, 5), round(borders["bottom"] / h, 5)]
    if engine in ("roblox", "generic"):
        meta["roblox"] = {"imageSize": [w, h]}
        if borders:
            meta["roblox"]["ScaleType"] = "Slice"
            meta["roblox"]["SliceCenter"] = [borders["left"], borders["top"], w - borders["right"], h - borders["bottom"]]
            meta["roblox"]["SliceScale"] = round(1 / scale, 4)
        if max(w, h) > ROBLOX_MAX:
            meta["roblox"]["warning"] = (f"{w}x{h} is larger than {ROBLOX_MAX}px; Roblox downsizes uploaded images, "
                                         "which blurs UI and breaks SliceCenter. Export smaller or split the image.")
    if engine in ("godot", "generic"):
        meta["godot"] = {"import": {"compress/mode": "Lossless", "mipmaps/generate": False},
                         "imageSize": [w, h]}
        if borders:
            meta["godot"]["node"] = "NinePatchRect or StyleBoxTexture"
            meta["godot"]["margins_LTRB"] = [borders["left"], borders["top"], borders["right"], borders["bottom"]]
    return meta


UNITY_STATE = {"hover": "highlightedSprite", "pressed": "pressedSprite", "selected": "selectedSprite",
               "focused": "selectedSprite", "disabled": "disabledSprite"}
GODOT_STATE = {"hover": "texture_hover", "pressed": "texture_pressed", "disabled": "texture_disabled",
               "focused": "texture_focused", "selected": "texture_focused"}
ROBLOX_STATE = {"hover": "HoverImage", "pressed": "PressedImage"}


def state_metadata(engine: str, normal: str, files: dict[str, str]) -> dict:
    """Which engine slot each exported state image goes into."""
    out: dict = {}
    if engine in ("unity", "generic"):
        slots = {UNITY_STATE[s]: f for s, f in files.items() if s in UNITY_STATE}
        if slots:
            out["unity_button"] = {"transition": "SpriteSwap", "spriteState": slots}
    if engine in ("godot", "generic"):
        slots = {GODOT_STATE[s]: f for s, f in files.items() if s in GODOT_STATE}
        if slots:
            out["godot_texture_button"] = {"texture_normal": normal, **slots}
    if engine in ("roblox", "generic"):
        slots = {ROBLOX_STATE[s]: f for s, f in files.items() if s in ROBLOX_STATE}
        if slots:
            out["roblox_image_button"] = slots
    return out


def pack_atlas(images: list[tuple[str, Image.Image]], padding: int = 2, max_size: int = 4096,
               power_of_two: bool = False) -> tuple[Image.Image, dict]:
    """Shelf-pack images into one atlas. Returns (atlas, frames{name: {x,y,w,h}})."""
    if not images:
        raise ValueError("Nothing to pack - give at least one canvas or image")
    order = sorted(images, key=lambda it: (-it[1].height, -it[1].width))
    total_area = sum((im.width + padding) * (im.height + padding) for _, im in order)
    widest = max(im.width for _, im in order) + padding * 2
    width = max(widest, int(np.ceil(np.sqrt(total_area) * 1.1)))
    if power_of_two:
        width = 1 << int(np.ceil(np.log2(width)))
    width = min(width, max_size)
    if widest > max_size:
        raise ValueError(f"An image is wider than max_size={max_size}")
    frames: dict = {}
    x = y = padding
    shelf_h = 0
    for name, im in order:
        if x + im.width + padding > width:
            x = padding
            y += shelf_h + padding
            shelf_h = 0
        frames[name] = {"x": x, "y": y, "w": im.width, "h": im.height}
        x += im.width + padding
        shelf_h = max(shelf_h, im.height)
    height = y + shelf_h + padding
    if power_of_two:
        height = 1 << int(np.ceil(np.log2(height)))
    if height > max_size:
        raise ValueError(f"Atlas would be {width}x{height}, larger than max_size={max_size}. Use a smaller scale or fewer images.")
    atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for name, im in order:
        f = frames[name]
        atlas.paste(im, (f["x"], f["y"]))
    return atlas, frames


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_manifest(out_dir: Path, name: str, entry: dict) -> Path:
    """Maintain ``uiforge_manifest.json`` in the export folder (one entry per asset)."""
    path = out_dir / "uiforge_manifest.json"
    data: dict = {"assets": {}}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded.get("assets"), dict):
                data = loaded
        except Exception:
            pass
    data["assets"][name] = entry
    write_json(path, data)
    return path


def nine_slice_stretch(img: Image.Image, borders: dict, width: int, height: int) -> Image.Image:
    """Draw ``img`` at width x height the way an engine 9-slices it: corners kept, edges and centre stretched."""
    w, h = img.size
    l, t, r, b = (int(borders[k]) for k in ("left", "top", "right", "bottom"))
    l, r = min(l, width // 2), min(r, width - min(l, width // 2))
    t, b = min(t, height // 2), min(b, height - min(t, height // 2))
    out = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    xs_src = [0, l, w - r, w]
    ys_src = [0, t, h - b, h]
    xs_dst = [0, l, width - r, width]
    ys_dst = [0, t, height - b, height]
    for i in range(3):
        for j in range(3):
            sx0, sx1, sy0, sy1 = xs_src[i], xs_src[i + 1], ys_src[j], ys_src[j + 1]
            dx0, dx1, dy0, dy1 = xs_dst[i], xs_dst[i + 1], ys_dst[j], ys_dst[j + 1]
            if sx1 <= sx0 or sy1 <= sy0 or dx1 <= dx0 or dy1 <= dy0:
                continue
            part = img.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.BILINEAR)
            out.paste(part, (dx0, dy0))
    return out


def svg_layer(lid: str, label: str, img, x: float, y: float, w: float, h: float) -> str:
    """One Inkscape/Illustrator/Figma layer holding a piece as an embedded PNG."""
    import base64
    import html
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return (f'  <g id="{html.escape(lid, quote=True)}" inkscape:groupmode="layer" '
            f'inkscape:label="{html.escape(label, quote=True)}">\n'
            f'    <image x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" preserveAspectRatio="none" '
            f'href="data:image/png;base64,{data}"/>\n  </g>')


def svg_document(width: float, height: float, layers: list[str]) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}">\n'
            + "\n".join(layers) + "\n</svg>\n")
