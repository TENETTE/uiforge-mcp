"""Preview-only helpers: guide overlays, colour-vision simulation and image backdrops.
Nothing here ends up in exported files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

_CVD = {
    "protanopia": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                            [-0.003882, -0.048116, 1.051998]]),
    "deuteranopia": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                              [-0.011820, 0.042940, 0.968881]]),
    "tritanopia": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
                            [0.004733, 0.691367, 0.303900]]),
}
SIMULATIONS = ("protanopia", "deuteranopia", "tritanopia", "grayscale", "low-contrast")


def simulate(img: Image.Image, mode: str) -> Image.Image:
    """How the picture looks with a colour-vision deficiency (or in grayscale / a washed-out screen)."""
    mode = mode.lower()
    if mode not in SIMULATIONS:
        raise ValueError(f"simulate must be one of {', '.join(SIMULATIONS)}")
    rgba = np.asarray(img.convert("RGBA"), dtype=np.float64)
    rgb = rgba[..., :3] / 255.0
    if mode == "low-contrast":
        out = 0.35 + (rgb - 0.5) * 0.55 + 0.15
    else:
        lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        if mode == "grayscale":
            y = lin @ np.array([0.2126, 0.7152, 0.0722])
            lin = np.repeat(y[..., None], 3, axis=-1)
        else:
            lin = np.clip(lin @ _CVD[mode].T, 0, 1)
        out = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    rgba[..., :3] = np.clip(out, 0, 1) * 255.0
    return Image.fromarray((rgba + 0.5).astype(np.uint8), "RGBA")


def image_backdrop(path: str, size: tuple[int, int]) -> Image.Image | None:
    """A file path used as preview background: cover-fitted (e.g. a gameplay screenshot)."""
    p = Path(path).expanduser()
    if not p.is_file():
        return None
    src = Image.open(p).convert("RGBA")
    w, h = size
    ratio = max(w / src.width, h / src.height)
    rs = src.resize((max(1, round(src.width * ratio)), max(1, round(src.height * ratio))), Image.LANCZOS)
    left, top = (rs.width - w) // 2, (rs.height - h) // 2
    return rs.crop((left, top, left + w, top + h))


def draw_guides(view: Image.Image, guides: list[str], canvas: dict, scale: float,
                offset: tuple[float, float] = (0.0, 0.0)) -> list[str]:
    """Overlay guides on a preview image. Returns notes about what was drawn."""
    d = ImageDraw.Draw(view, "RGBA")
    W, H = float(canvas["width"]), float(canvas["height"])
    ox, oy = offset
    notes = []

    def X(v: float) -> float:
        return (v - ox) * scale

    def Y(v: float) -> float:
        return (v - oy) * scale

    for raw in guides:
        g = str(raw).lower().strip()
        name, _, arg = g.partition(":")
        if name == "safe":
            ins = canvas.get("safe_area")
            if not ins:
                notes.append("no safe_area on this canvas (set a device preset or update_canvas(safe_area=...)); "
                             "showing 5% title-safe instead")
                ins = [W * 0.05, H * 0.05, W * 0.05, H * 0.05]
            l, t, r, b = (float(v) for v in ins)
            col = (255, 80, 80, 70)
            for box in ((0, 0, W, t), (0, H - b, W, H), (0, 0, l, H), (W - r, 0, W, H)):
                if box[2] > box[0] and box[3] > box[1]:
                    d.rectangle([X(box[0]), Y(box[1]), X(box[2]) - 1, Y(box[3]) - 1], fill=col)
            d.rectangle([X(l), Y(t), X(W - r) - 1, Y(H - b) - 1], outline=(255, 80, 80, 220), width=2)
        elif name == "tv":
            for frac, col in ((0.05, (255, 200, 0, 200)), (0.035, (0, 200, 255, 160))):
                d.rectangle([X(W * frac), Y(H * frac), X(W * (1 - frac)) - 1, Y(H * (1 - frac)) - 1], outline=col, width=1)
            notes.append("tv: yellow = 90% title-safe, blue = 93% action-safe")
        elif name == "grid":
            step = float(arg or 8)
            if step * scale < 4:
                notes.append(f"grid {step:g} too dense at this zoom; skipped")
                continue
            v = step
            while v < W:
                d.line([(X(v), Y(0)), (X(v), Y(H))], fill=(255, 255, 255, 28))
                v += step
            v = step
            while v < H:
                d.line([(X(0), Y(v)), (X(W), Y(v))], fill=(255, 255, 255, 28))
                v += step
        elif name == "columns":
            n = int(arg or 12)
            margin = W * 0.04
            gutter = W * 0.015
            cw = (W - 2 * margin - gutter * (n - 1)) / n
            for i in range(n):
                x0 = margin + i * (cw + gutter)
                d.rectangle([X(x0), Y(0), X(x0 + cw) - 1, Y(H)], fill=(255, 60, 120, 30))
            notes.append(f"columns: {n} columns, 4% margins, 1.5% gutters")
        elif name == "thirds":
            for f in (1 / 3, 2 / 3):
                d.line([(X(W * f), Y(0)), (X(W * f), Y(H))], fill=(120, 255, 120, 120))
                d.line([(X(0), Y(H * f)), (X(W), Y(H * f))], fill=(120, 255, 120, 120))
        elif name == "center":
            d.line([(X(W / 2), Y(0)), (X(W / 2), Y(H))], fill=(0, 255, 255, 150))
            d.line([(X(0), Y(H / 2)), (X(W), Y(H / 2))], fill=(0, 255, 255, 150))
        elif name == "thumb":
            r = min(W, H) * 0.45
            for cx in (0, W):
                d.ellipse([X(cx - r), Y(H - r), X(cx + r), Y(H + r)], outline=(120, 255, 160, 200), width=2)
            notes.append("thumb: green arcs = easy thumb reach on a landscape phone held in two hands")
        else:
            raise ValueError("guides: use 'safe', 'tv', 'grid:<step>', 'columns:<n>', 'thirds', 'center', 'thumb'")
    return notes
