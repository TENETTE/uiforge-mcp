"""Vector PDF export, written directly (no extra dependency).

Shapes, booleans, lines and text (as glyph outlines, so no fonts are needed to open it) become real PDF
paths with solid or linear / radial gradient paint and real strokes. Drop shadows and glows are placed
as a picture under the vector shape. Anything PDF cannot show the same way (shader / pattern fills,
light, inner effects, blur, glass, special blends, styled layers, images, colour emoji) is embedded as a
picture of just that element, so the page always looks like the PNG. Several canvases make several pages.
"""

from __future__ import annotations

import math
import zlib
from typing import Any

import numpy as np

from .colors import parse_color
from .render import (LINE_TYPES, VECTOR_TYPES, Renderer, TextLayout, _is_fill_stack, _is_none, _placed_polys,
                     _stroke_specs, resolve_style, vector_geometry)

_SIMPLE_KEYS = {"fill", "stroke", "opacity", "use", "shadow", "glow", "blend"}


def _n(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


class _Writer:
    def __init__(self) -> None:
        self.objs: list[bytes | None] = []

    def reserve(self) -> int:
        self.objs.append(None)
        return len(self.objs)

    def put(self, num: int, body: bytes) -> int:
        self.objs[num - 1] = body
        return num

    def add(self, body: bytes) -> int:
        self.objs.append(body)
        return len(self.objs)

    def stream(self, data: bytes, extra: str = "") -> int:
        packed = zlib.compress(data, 9)
        return self.add(f"<< /Length {len(packed)} /Filter /FlateDecode {extra}>>\nstream\n".encode()
                        + packed + b"\nendstream")

    def build(self, root: int) -> bytes:
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(self.objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + (body or b"null") + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(self.objs) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(self.objs) + 1} /Root {root} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


class _Page:
    """Content stream and resources of one page; coordinates are canvas units (y down)."""

    def __init__(self, w: _Writer, height: float, colors: dict) -> None:
        self.w, self.h, self.colors = w, height, colors
        self.ops: list[str] = [f"1 0 0 -1 0 {_n(height)} cm"]
        self.gstates: dict[str, int] = {}
        self.patterns: dict[str, int] = {}
        self.images: dict[str, int] = {}

    def alpha(self, a: float) -> str:
        key = f"GS{len(self.gstates) + 1}"
        for name, num in self.gstates.items():
            if self.w.objs[num - 1] == f"<< /ca {_n(a)} /CA {_n(a)} >>".encode():
                return name
        self.gstates[key] = self.w.add(f"<< /ca {_n(a)} /CA {_n(a)} >>".encode())
        return key

    def image(self, img, x: float, y: float, scale: float) -> None:
        rgba = np.asarray(img.convert("RGBA"))
        h, w = rgba.shape[:2]
        smask = self.w.stream(rgba[..., 3].tobytes(), f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
                                                     "/ColorSpace /DeviceGray /BitsPerComponent 8 ")
        num = self.w.stream(rgba[..., :3].tobytes(), f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
                                                    f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /SMask {smask} 0 R ")
        name = f"Im{len(self.images) + 1}"
        self.images[name] = num
        self.ops.append(f"q {_n(w / scale)} 0 0 {_n(-h / scale)} {_n(x / scale)} {_n((y + h) / scale)} cm /{name} Do Q")

    def gradient(self, spec: dict, box) -> str | None:
        """A shading pattern for a linear / radial fill with opaque stops; None if PDF cannot match it."""
        kind = str(spec.get("type", "linear")).lower()
        raw = spec.get("stops") or spec.get("colors") or ([spec["from"], spec["to"]] if "from" in spec else None)
        if kind not in ("linear", "radial") or not raw or len(raw) < 2:
            return None
        stops = []
        n = len(raw)
        for i, item in enumerate(raw):
            if isinstance(item, dict):
                off, col = item.get("offset", i / (n - 1)), item.get("color")
            elif isinstance(item, (list, tuple)) and len(item) == 2 and not isinstance(item[1], (int, float)):
                off, col = item
            else:
                off, col = i / (n - 1), item
            r, g, b, a = parse_color(col, self.colors)
            if a < 255:
                return None
            stops.append((float(off), (r / 255, g / 255, b / 255)))
        stops.sort(key=lambda s: s[0])
        funcs = []
        for (o0, c0), (o1, c1) in zip(stops, stops[1:]):
            funcs.append(self.w.add(f"<< /FunctionType 2 /Domain [0 1] /N 1 /C0 [{' '.join(_n(v) for v in c0)}] "
                                    f"/C1 [{' '.join(_n(v) for v in c1)}] >>".encode()))
        lo, hi = stops[0][0], stops[-1][0]
        if len(funcs) == 1:
            fn = funcs[0]
        else:
            bounds = " ".join(_n(o) for o, _ in stops[1:-1])
            fn = self.w.add(f"<< /FunctionType 3 /Domain [{_n(lo)} {_n(hi)}] /Functions [{' '.join(f'{f} 0 R' for f in funcs)}] "
                            f"/Bounds [{bounds}] /Encode [{' '.join('0 1' for _ in funcs)}] >>".encode())
        x0, y0, x1, y1 = box
        bw, bh = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
        H = self.h
        if kind == "linear":
            ang = math.radians(float(spec.get("angle", 90)))
            ca, sa = math.cos(ang), math.sin(ang)
            half = (abs(bw * ca) + abs(bh * sa)) / 2
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            ax, ay = cx - ca * half + ca * 2 * half * lo, cy - sa * half + sa * 2 * half * lo
            bx, by = cx - ca * half + ca * 2 * half * hi, cy - sa * half + sa * 2 * half * hi
            shading = (f"<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [{_n(ax)} {_n(H - ay)} {_n(bx)} {_n(H - by)}] "
                       f"/Domain [{_n(lo)} {_n(hi)}] /Function {fn} 0 R /Extend [true true] >>")
            matrix = "1 0 0 1 0 0"
        else:
            cx, cy = x0 + bw * float(spec.get("cx", 0.5)), y0 + bh * float(spec.get("cy", 0.5))
            rad = float(spec.get("r", 0.5))
            rx, ry = (max(bw, bh) * rad,) * 2 if spec.get("circle") else (bw * rad, bh * rad)
            shading = (f"<< /ShadingType 3 /ColorSpace /DeviceRGB /Coords [0 0 {_n(lo)} 0 0 {_n(hi)}] "
                       f"/Domain [{_n(lo)} {_n(hi)}] /Function {fn} 0 R /Extend [true true] >>")
            matrix = f"{_n(rx)} 0 0 {_n(ry)} {_n(cx)} {_n(H - cy)}"
        sh = self.w.add(shading.encode())
        name = f"P{len(self.patterns) + 1}"
        self.patterns[name] = self.w.add(f"<< /PatternType 2 /Shading {sh} 0 R /Matrix [{matrix}] >>".encode())
        return name

    def fill(self, polys, paint: Any, box, rule: str, alpha: float = 1.0) -> bool:
        if _is_none(paint):
            return True
        if isinstance(paint, dict):
            name = self.gradient(paint, box)
            if name is None:
                return False
            set_paint = f"/Pattern cs /{name} scn"
            a = alpha
        else:
            r, g, b, pa = parse_color(paint, self.colors)
            set_paint = f"{_n(r / 255)} {_n(g / 255)} {_n(b / 255)} rg"
            a = alpha * pa / 255
        path = " ".join("".join([f"{_n(p[0][0])} {_n(p[0][1])} m "] + [f"{_n(x)} {_n(y)} l " for x, y in p[1:]]) + "h"
                        for p in polys if len(p) >= 3)
        if not path:
            return True
        gs = f"/{self.alpha(a)} gs " if a < 0.999 else ""
        self.ops.append(f"q {gs}{set_paint} {path} {'f*' if rule == 'evenodd' else 'f'} Q")
        return True

    def content(self) -> int:
        return self.w.stream("\n".join(self.ops).encode())

    def resources(self) -> str:
        parts = []
        if self.gstates:
            parts.append("/ExtGState << " + " ".join(f"/{k} {v} 0 R" for k, v in self.gstates.items()) + " >>")
        if self.patterns:
            parts.append("/Pattern << " + " ".join(f"/{k} {v} 0 R" for k, v in self.patterns.items()) + " >>")
        if self.images:
            parts.append("/XObject << " + " ".join(f"/{k} {v} 0 R" for k, v in self.images.items()) + " >>")
        return "<< " + " ".join(parts) + " >>"


def _band(polys, d0: float, d1: float, join: str):
    """A stroke band between distances d0 and d1 from the outline, as polygons."""
    from .tools_design import _difference, _floats, _offset
    outer = _offset(polys, d1, join)
    inner = _offset(polys, d0, join)
    return _floats(_difference(outer, inner))


def _vector(page: _Page, r: Renderer, el: dict, st: dict, big: Renderer, scale: float) -> bool:
    """Draw one element as PDF vectors (shadows as a picture underneath). False = needs the picture fallback."""
    if set(st) - _SIMPLE_KEYS or el.get("clip") or any(el.get(k) for k in ("scale_x", "scale_y", "flip_x", "flip_y")):
        return False
    if str(st.get("blend", "normal")).lower() != "normal":
        return False
    t = el["type"]
    opacity = float(st.get("opacity", 1))
    rule = "evenodd"
    if t == "text":
        if el.get("arc") or el.get("path"):
            return False
        layout = TextLayout(el, st, r.fonts, 4.0, r.text_of(el), r.text_lang(el))
        if layout.shaper and any(f.color for f in layout.shaper.chain if layout.shaper.used):
            if any(layout.shaper.color_runs.get(line) for line, _ in layout.lines):
                return False
        if _stroke_specs(st, r.colors):
            return False
        polys = layout.outline_polys_units()
        rot = float(el.get("rotation", 0) or 0)
        if rot:
            cx, cy = r._pivot(el, layout.box_units())
            c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            polys = [[(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in p] for p in polys]
        from .tools_design import _floats, _ints
        import pyclipper
        polys = _floats(pyclipper.SimplifyPolygons(_ints(polys), pyclipper.PFT_NONZERO))
        box = layout.box_units()
        fills = st.get("fill", "#ffffff")
    elif t in LINE_TYPES:
        from .tools_design import _floats, _line_outline
        g = vector_geometry(el, 4.0)
        polys = _floats(_line_outline(g, "round")) + [list(p) for p in g.fills]
        rule = "nonzero"
        box = g.paint_box or g.box
        fills = st.get("fill", "#ffffff")
    elif t in VECTOR_TYPES:
        polys = _placed_polys(el, 4.0)
        g = vector_geometry(el, 4.0)
        rule = str(el.get("fill_rule", "evenodd")).lower() if t == "path" else "evenodd"
        box = g.box
        fills = st.get("fill", "#ffffff" if not st.get("stroke") else None)
    else:
        return False
    if st.get("shadow") or st.get("glow"):
        ghost = dict(el, style={k: st[k] for k in ("shadow", "glow") if k in st} | {"fill": "#00000000"})
        ghost.pop("id", None)
        ghost["id"] = el["id"] + "__shadow"
        result = big.render_element(ghost)
        if result is not None:
            img, px0, py0, _ = result
            page.image(img, px0, py0, scale)
    for one in (fills if _is_fill_stack(fills) else [fills]):
        if isinstance(one, dict) and "blend" in one:
            return False
        if not page.fill(polys, one, box, rule, opacity):
            return False
    if t not in LINE_TYPES and t != "text":
        for sp in _stroke_specs(st, r.colors):
            if sp["dash"] or sp["sides"]:
                return False
            band = _band(polys, sp["d0"], sp["d1"], sp["join"] or ("miter" if t in ("polygon", "path") else "round"))
            if not page.fill(band, sp["paint"], box, "nonzero", opacity):
                return False
    return True


def canvases_pdf(renderers: list[Renderer], include_background: bool = True, image_scale: float = 2.0) -> tuple[bytes, dict]:
    w = _Writer()
    pages_num = w.reserve()
    page_refs = []
    report: dict[str, list[str]] = {"vector": [], "raster": []}
    scale = max(1.0, min(8.0, float(image_scale)))
    for r in renderers:
        c = r.canvas
        page = _Page(w, float(c["height"]), r.colors)
        big = r.derive(r.k * scale)
        if include_background and not _is_none(c.get("background")):
            bg = c["background"]
            if isinstance(bg, str) and not bg.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                page.fill([[(0, 0), (c["width"], 0), (c["width"], c["height"]), (0, c["height"])]], bg,
                          (0, 0, c["width"], c["height"]), "nonzero")
            else:
                page.image(big.render(include_background=True, only=set()), 0, 0, scale)
        beneath: list[str] = []
        for layer, elements in r.stack():
            props = r.layer_props(layer) if layer else None
            if props and not props["visible"]:
                continue
            plain = props is None or (not props["style"] and props["blend"] == "normal" and not props["clip"]
                                      and props["opacity"] >= 1)
            if not plain:
                ids = {e["id"] for e in elements}
                beneath.extend(ids)
                img = big.render(include_background=False, only=ids)
                bbox = img.getchannel("A").getbbox()
                if bbox:
                    page.image(img.crop(bbox), bbox[0], bbox[1], scale)
                report["raster"].append(f"layer:{props['name']}")
                continue
            for el in elements:
                st = r._nums(resolve_style(el.get("style"), r.theme))
                beneath.append(el["id"])
                if st.get("backdrop_blur") or st.get("glass"):
                    result = big.render_element(el)
                    if result is not None:
                        from PIL import ImageChops
                        own, px0, py0, _ = result
                        scene = big.render(include_background=include_background, only=set(beneath))
                        patch = scene.crop((px0, py0, px0 + own.width, py0 + own.height))
                        foot = ImageChops.lighter(own.getchannel("A"), big.shape_mask(el, (px0, py0, own.width, own.height)))
                        patch.putalpha(ImageChops.multiply(patch.getchannel("A"), foot))
                        page.image(patch, px0, py0, scale)
                    report["raster"].append(el["id"])
                    continue
                mark = len(page.ops)
                try:
                    done = _vector(page, r, r._nums(el), st, big, scale)
                except ValueError:
                    done = False
                if done:
                    report["vector"].append(el["id"])
                    continue
                del page.ops[mark:]
                result = big.render_element(el)
                if result is not None:
                    img, px0, py0, _ = result
                    page.image(img, px0, py0, scale)
                report["raster"].append(el["id"])
        content = page.content()
        res = w.add(page.resources().encode())
        page_refs.append(w.add(f"<< /Type /Page /Parent {pages_num} 0 R /MediaBox [0 0 {_n(c['width'])} {_n(c['height'])}] "
                               f"/Resources {res} 0 R /Contents {content} 0 R >>".encode()))
    w.put(pages_num, f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_refs)}] /Count {len(page_refs)} >>".encode())
    root = w.add(f"<< /Type /Catalog /Pages {pages_num} 0 R >>".encode())
    return w.build(root), report
