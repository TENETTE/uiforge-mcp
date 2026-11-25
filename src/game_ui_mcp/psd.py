"""Minimal Photoshop (.psd) writer: 8-bit RGB with alpha, one PackBits RLE raster layer per canvas layer.

Layers keep their name, opacity, blend mode, visibility and clipping flag, so the file opens as an
editable stack in Photoshop, Photopea, Krita, GIMP and Affinity.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
from PIL import Image

BLEND_KEYS = {
    "normal": b"norm", "multiply": b"mul ", "screen": b"scrn", "overlay": b"over", "add": b"lddg",
    "soft-light": b"sLit", "hard-light": b"hLit", "color-dodge": b"div ", "color-burn": b"idiv",
    "darken": b"dark", "lighten": b"lite", "difference": b"diff",
}


def _pascal(name: str, multiple: int) -> bytes:
    raw = name.encode("ascii", "replace")[:255]
    data = bytes([len(raw)]) + raw
    return data + b"\0" * (-len(data) % multiple)


def _unicode_name(name: str) -> bytes:
    data = struct.pack(">I", len(name)) + name.encode("utf-16-be")
    data += b"\0" * (-len(data) % 4)
    return b"8BIM" + b"luni" + struct.pack(">I", len(data)) + data


def _packbits_row(row: bytes) -> bytes:
    """PackBits RLE encoder for one scanline (Adobe PSD compression = 1)."""
    n = len(row)
    if n == 0:
        return b""
    out = bytearray()
    i = 0
    while i < n:
        run_end = i + 1
        while run_end < n and row[run_end] == row[i] and run_end - i < 128:
            run_end += 1
        run_len = run_end - i
        if run_len >= 3:
            out.append(257 - run_len)
            out.append(row[i])
            i = run_end
        else:
            lit_start = i
            i += 1
            while i < n and i - lit_start < 128:
                if i + 2 < n and row[i] == row[i + 1] == row[i + 2]:
                    break
                i += 1
            lit_len = i - lit_start
            out.append(lit_len - 1)
            out.extend(row[lit_start:i])
    return bytes(out)


def _rle_plane(plane: np.ndarray) -> bytes:
    """Encode a 2D uint8 channel plane as PSD PackBits RLE (compression header + row counts + data)."""
    if plane.size == 0:
        return struct.pack(">H", 0)
    rows = [_packbits_row(plane[y].tobytes()) for y in range(plane.shape[0])]
    counts = struct.pack(f">{len(rows)}H", *(len(r) for r in rows))
    return struct.pack(">H", 1) + counts + b"".join(rows)


def write_psd(path: Path, width: int, height: int, layers: list[dict], merged: Image.Image) -> None:
    """layers: bottom to top, each {"name", "image" (RGBA, canvas size), "opacity" 0-1, "blend", "clip", "visible"}.
    merged: the flattened picture (RGBA, canvas size) stored as the file's preview/composite."""
    records = bytearray()
    pixels = bytearray()
    for layer in layers:
        img = layer["image"].convert("RGBA")
        box = img.getchannel("A").getbbox()
        if box is None:
            left = top = right = bottom = 0
            encoded = [struct.pack(">H", 0)] * 4
        else:
            left, top, right, bottom = box
            arr = np.asarray(img.crop(box))
            encoded = [_rle_plane(arr[..., c]) for c in (3, 0, 1, 2)]
        rec = struct.pack(">4i", top, left, bottom, right) + struct.pack(">H", 4)
        for channel_id, chunk in zip((-1, 0, 1, 2), encoded):
            rec += struct.pack(">hI", channel_id, len(chunk))
            pixels += chunk
        blend = BLEND_KEYS.get(str(layer.get("blend", "normal")), b"norm")
        opacity = max(0, min(255, int(round(float(layer.get("opacity", 1)) * 255))))
        flags = 8 | (0 if layer.get("visible", True) else 2)
        rec += b"8BIM" + blend + struct.pack(">4B", opacity, 1 if layer.get("clip") else 0, flags, 0)
        extra = struct.pack(">I", 0) + struct.pack(">I", 0)
        extra += _pascal(layer["name"], 4) + _unicode_name(layer["name"])
        rec += struct.pack(">I", len(extra)) + extra
        records += rec

    layer_info = struct.pack(">h", -len(layers)) + bytes(records) + bytes(pixels)
    layer_info += b"\0" * (len(layer_info) % 2)
    section = struct.pack(">I", len(layer_info)) + layer_info + struct.pack(">I", 0)

    flat = np.asarray(merged.convert("RGBA"))
    flat_rows = [[_packbits_row(flat[y, :, c].tobytes()) for y in range(height)] for c in range(4)]
    with open(path, "wb") as handle:
        handle.write(b"8BPS" + struct.pack(">H", 1) + b"\0" * 6)
        handle.write(struct.pack(">HIIHH", 4, height, width, 8, 3))
        handle.write(struct.pack(">I", 0))
        handle.write(struct.pack(">I", 0))
        handle.write(struct.pack(">I", len(section)) + section)
        handle.write(struct.pack(">H", 1))
        for ch_rows in flat_rows:
            handle.write(struct.pack(f">{height}H", *(len(r) for r in ch_rows)))
        for ch_rows in flat_rows:
            for r in ch_rows:
                handle.write(r)
