"""Complex text: built-in UAX #9 BiDi + shaping (HarfBuzz) + per-character font fallback.

Pillow's own layout on Windows has no Raqm, so Arabic comes out disconnected and left-to-right,
Indic conjuncts never form and the language tag is ignored. Text that needs any of that goes
through here instead; plain Latin / Greek / Cyrillic text keeps Pillow's path.
Glyph outlines are drawn with the exact scanline rasteriser at the renderer's supersampling.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

import numpy as np
from pathlib import Path
import uharfbuzz as hb
from PIL import Image

from . import raster
from .fonts import BUNDLED_DIR

NOTO_DIR = BUNDLED_DIR / "noto"
_NOTO = ("Arabic", "Hebrew", "Devanagari", "Bengali", "Tamil", "Thai")

_CJK = {
    "ja": ["Yu Gothic", "Yu Gothic UI", "Meiryo", "MS Gothic", "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP"],
    "zh-hans": ["Microsoft YaHei", "Microsoft YaHei UI", "SimSun", "PingFang SC", "Hiragino Sans GB", "Heiti SC", "STHeiti", "Songti SC", "Noto Sans CJK SC", "Noto Sans SC"],
    "zh-hant": ["Microsoft JhengHei", "Microsoft JhengHei UI", "PingFang TC", "PingFang HK", "Heiti TC", "Songti TC", "Noto Sans CJK TC", "Noto Sans TC"],
    "ko": ["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR"],
}
_SYSTEM = ["Segoe UI", "Nirmala UI", "Leelawadee UI", "Kohinoor Devanagari", "Thonburi", "Noto Sans",
           "DejaVu Sans", "Segoe UI Symbol", "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji"]
COLOR_FONTS = ("seguiemj.ttf", "applecoloremoji.ttc", "notocoloremoji.ttf", "twemojimozilla.ttf")


def is_color_font(path: str) -> bool:
    norm = Path(path).name.lower().replace(" ", "").replace("-", "").replace("_", "")
    return norm in COLOR_FONTS


def _is_emoji(text: str, i: int) -> bool:
    cp = ord(text[i])
    nxt = text[i + 1] if i + 1 < len(text) else ""
    return (0x1F000 <= cp <= 0x1FAFF or (0x2600 <= cp <= 0x27BF and nxt == "\ufe0f")
            or (0x2B00 <= cp <= 0x2BFF and nxt == "\ufe0f") or cp in (0x2B50, 0x2B55, 0x231A, 0x231B, 0x23F0))

_NO_START = set("、。，．・：；？！ー）」』】〕〉》〙〗｝］’”ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〻…‥")
_NO_END = set("（「『【〔〈《〘〖｛［‘“")


def norm_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    k = str(lang).strip().replace("_", "-").lower()
    if k in ("zh", "zh-cn", "zh-sg", "zh-hans-cn"):
        return "zh-hans"
    if k in ("zh-tw", "zh-hk", "zh-mo"):
        return "zh-hant"
    return k


def _is_cjk(cp: int) -> bool:
    return (0x3040 <= cp <= 0x30FF or 0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF
            or 0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF or 0x20000 <= cp <= 0x3FFFF)


def _is_han(cp: int) -> bool:
    return 0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF or 0x20000 <= cp <= 0x3FFFF


def _simple(cp: int) -> bool:
    """Scripts Pillow's basic layout draws correctly: Latin, Greek, Cyrillic, common punctuation."""
    return cp < 0x0590 or 0x1E00 <= cp <= 0x1FFF or 0x2000 <= cp <= 0x2BFF and not 0x2066 <= cp <= 0x2069 \
        and not 0x202A <= cp <= 0x202E and cp not in (0x200D, 0x200E, 0x200F)


def needs_shaping(text: str, covered) -> bool:
    return any(not ch.isspace() and (not _simple(ord(ch)) or not covered(ord(ch))) for ch in text)


def guess_lang(text: str, lang: str | None) -> tuple[str | None, str | None]:
    """(language to shape with, warning). Han without a language tag is ambiguous (JP vs SC vs TC)."""
    lang = norm_lang(lang)
    if lang and not lang.startswith("pseudo"):
        return lang, None
    if not any(_is_han(ord(c)) for c in text):
        return None, None
    if any(0x3040 <= ord(c) <= 0x30FF for c in text):
        return "ja", None
    if any(0xAC00 <= ord(c) <= 0xD7AF for c in text):
        return "ko", None
    return "zh-hans", ("Han characters without a language tag were drawn as Simplified Chinese; "
                       "set language ('ja', 'zh-Hans', 'zh-Hant', 'ko') so the right glyph forms are used")



@lru_cache(maxsize=64)
def _face(path: str):
    face = hb.Face(hb.Blob.from_file_path(path), 0)
    return face, frozenset(face.unicodes)


class _Font:
    def __init__(self, path: str, var_weight: int | None, size_px: float, axes: tuple | None = None):
        self.path = path
        self.face, self.cmap = _face(path)
        self.font = hb.Font(self.face)
        self.var = None
        var = {"wght": float(var_weight), "opsz": float(size_px)} if var_weight is not None else {}
        var.update(dict(axes or ()))
        if var:
            self.var = var
            self.font.set_variations(self.var)
        self.color = is_color_font(path)
        self.scale = size_px / self.face.upem
        ext = self.font.get_font_extents("ltr")
        self.ascent, self.descent = ext.ascender * self.scale, -ext.descender * self.scale


@lru_cache(maxsize=128)
def fallback_chain(fonts, primary_path: str | None, var_weight: int | None, weight: int, size_px: float,
                   lang: str | None, axes: tuple | None = None) -> tuple[_Font, ...]:
    chain = []
    if primary_path:
        chain.append(_Font(primary_path, var_weight, size_px, axes))
    bold = weight >= 600
    for script in _NOTO:
        p = NOTO_DIR / f"NotoSans{script}-{'Bold' if bold else 'Regular'}.ttf"
        if p.is_file():
            chain.append(_Font(str(p), None, size_px))
    cjk = _CJK.get(lang or "", []) + [f for k, v in _CJK.items() if k != lang for f in v]
    for family in cjk + _SYSTEM:
        try:
            path, vw, _ = fonts.resolve(family, weight)
        except ValueError:
            continue
        if path and path not in {f.path for f in chain}:
            chain.append(_Font(path, vw, size_px))
    return tuple(chain)



class _Pen:
    def __init__(self) -> None:
        self.contours: list[list[tuple[float, float]]] = []

    def moveTo(self, p):
        self.contours.append([p])

    def lineTo(self, p):
        self.contours[-1].append(p)

    def qCurveTo(self, c, p):
        p0 = self.contours[-1][-1]
        for t in np.linspace(0, 1, 9)[1:]:
            u = 1 - t
            self.contours[-1].append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p[0],
                                      u * u * p0[1] + 2 * u * t * c[1] + t * t * p[1]))

    def curveTo(self, c1, c2, p):
        p0 = self.contours[-1][-1]
        for t in np.linspace(0, 1, 13)[1:]:
            u = 1 - t
            self.contours[-1].append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p[0],
                                      u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p[1]))

    def closePath(self):
        pass


@lru_cache(maxsize=4096)
def _outline(path: str, var: tuple | None, gid: int) -> tuple:
    font = hb.Font(_face(path)[0])
    if var:
        font.set_variations(dict(var))
    pen = _Pen()
    font.draw_glyph_with_pen(gid, pen)
    return tuple(np.asarray(c, dtype=np.float64) for c in pen.contours if len(c) >= 3)


_EXPLICIT = {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"}


def _levels(text: str) -> list[int]:
    """Resolve Unicode UAX #9 Bidirectional embedding levels (pure Python, MIT-clean via stdlib unicodedata)."""
    n = len(text)
    if n == 0:
        return []
    raw_types = [unicodedata.bidirectional(ch) for ch in text]
    base = 0
    for bt in raw_types:
        if bt == "L":
            base = 0
            break
        if bt in ("R", "AL"):
            base = 1
            break

    levels = [base] * n
    types = list(raw_types)
    stack: list[tuple[int, str | None, bool]] = [(base, None, False)]
    for i, bt in enumerate(raw_types):
        cur_lvl, cur_ovr, _ = stack[-1]
        if bt in ("RLE", "LRE", "RLO", "LRO"):
            want_odd = bt in ("RLE", "RLO")
            nxt = (cur_lvl + 1) if ((cur_lvl + 1) % 2 == (1 if want_odd else 0)) else (cur_lvl + 2)
            ovr = "R" if bt == "RLO" else "L" if bt == "LRO" else None
            if nxt <= 125:
                stack.append((nxt, ovr, False))
            levels[i] = cur_lvl
            types[i] = "BN"
        elif bt == "PDF":
            if len(stack) > 1 and not stack[-1][2]:
                stack.pop()
            levels[i] = stack[-1][0]
            types[i] = "BN"
        elif bt in ("RLI", "LRI", "FSI"):
            levels[i] = cur_lvl
            types[i] = "ON"
            want_odd = bt == "RLI"
            if bt == "FSI":
                depth = 0
                for j in range(i + 1, n):
                    t2 = raw_types[j]
                    if t2 in ("RLI", "LRI", "FSI"):
                        depth += 1
                    elif t2 == "PDI":
                        if depth == 0:
                            break
                        depth -= 1
                    elif depth == 0 and t2 in ("L", "R", "AL"):
                        want_odd = t2 in ("R", "AL")
                        break
            nxt = (cur_lvl + 1) if ((cur_lvl + 1) % 2 == (1 if want_odd else 0)) else (cur_lvl + 2)
            if nxt <= 125:
                stack.append((nxt, None, True))
        elif bt == "PDI":
            while len(stack) > 1 and not stack[-1][2]:
                stack.pop()
            if len(stack) > 1 and stack[-1][2]:
                stack.pop()
            levels[i] = stack[-1][0]
            types[i] = "ON"
        else:
            levels[i] = cur_lvl
            if cur_ovr is not None and bt not in ("B", "S", "BN"):
                types[i] = cur_ovr

    run_start = 0
    while run_start < n:
        lvl = levels[run_start]
        run_end = run_start + 1
        while run_end < n and levels[run_end] == lvl:
            run_end += 1
        sor = "R" if lvl % 2 else "L"
        next_lvl = levels[run_end] if run_end < n else base
        eor = "R" if max(lvl, next_lvl) % 2 else "L"

        prev_t = sor
        for i in range(run_start, run_end):
            if types[i] == "NSM":
                types[i] = prev_t
            elif types[i] != "BN":
                prev_t = types[i]

        strong = sor
        for i in range(run_start, run_end):
            if types[i] in ("L", "R", "AL"):
                strong = types[i]
            elif types[i] == "EN" and strong == "AL":
                types[i] = "AN"

        for i in range(run_start, run_end):
            if types[i] == "AL":
                types[i] = "R"

        for i in range(run_start, run_end):
            if types[i] in ("ES", "CS"):
                p = types[i - 1] if i > run_start else sor
                q = types[i + 1] if i + 1 < run_end else eor
                if types[i] == "ES" and p == "EN" and q == "EN":
                    types[i] = "EN"
                elif types[i] == "CS" and ((p == "EN" and q == "EN") or (p == "AN" and q == "AN")):
                    types[i] = p

        i = run_start
        while i < run_end:
            if types[i] == "ET":
                j = i
                while j < run_end and types[j] == "ET":
                    j += 1
                p = types[i - 1] if i > run_start else sor
                q = types[j] if j < run_end else eor
                rep = "EN" if (p == "EN" or q == "EN") else "ON"
                for k_idx in range(i, j):
                    types[k_idx] = rep
                i = j
            else:
                i += 1

        for i in range(run_start, run_end):
            if types[i] in ("ES", "ET", "CS"):
                types[i] = "ON"

        strong = sor
        for i in range(run_start, run_end):
            if types[i] in ("L", "R"):
                strong = types[i]
            elif types[i] == "EN" and strong == "L":
                types[i] = "L"

        i = run_start
        while i < run_end:
            if types[i] in ("B", "S", "WS", "ON", "BN"):
                j = i
                while j < run_end and types[j] in ("B", "S", "WS", "ON", "BN"):
                    j += 1
                p = types[i - 1] if i > run_start else sor
                q = types[j] if j < run_end else eor
                p_dir = "R" if p in ("R", "AN", "EN") else "L"
                q_dir = "R" if q in ("R", "AN", "EN") else "L"
                rep = p_dir if p_dir == q_dir else ("R" if lvl % 2 else "L")
                for k_idx in range(i, j):
                    if types[k_idx] != "BN":
                        types[k_idx] = rep
                i = j
            else:
                i += 1

        for i in range(run_start, run_end):
            t = types[i]
            if lvl % 2 == 0:
                if t == "R":
                    levels[i] = lvl + 1
                elif t in ("AN", "EN"):
                    levels[i] = lvl + 2
            else:
                if t in ("L", "EN", "AN"):
                    levels[i] = lvl + 1

        run_start = run_end
    return levels


class ShapedText:
    """Shapes lines of one text element through a fallback chain. Positions are in pixels."""

    def __init__(self, chain: list[_Font], lang: str | None, spacing_px: float, features: dict | None = None):
        self.chain = chain
        self.lang = lang
        self.spacing = spacing_px
        self.features = dict(features or {})
        self.color_runs: dict[str, list[tuple[float, str, int]]] = {}
        self.missing: set[str] = set()
        self.used: set[int] = set()
        self.fallback: dict[int, set[str]] = {}
        self._cache: dict[str, tuple] = {}

    def _pick(self, text: str) -> list[int]:
        out: list[int] = []
        prev = None
        for ch in text:
            cp, cat = ord(ch), unicodedata.category(ch)
            if prev is not None and (cat[0] == "M" or cat in ("Cf", "Cc")
                                     or (cat[0] != "L" and cp in self.chain[prev].cmap)):
                out.append(prev)
                continue
            idx = None
            if _is_emoji(text, len(out)):
                idx = next((i for i, f in enumerate(self.chain) if f.color and cp in f.cmap), None)
            if idx is None:
                idx = next((i for i, f in enumerate(self.chain) if cp in f.cmap), None)
            if idx is None:
                if not ch.isspace() and cat not in ("Cf", "Cc"):
                    self.missing.add(ch)
                idx = prev if prev is not None else 0
            elif idx and not ch.isspace():
                self.fallback.setdefault(idx, set()).add(ch)
            out.append(idx)
            prev = idx
        return out

    def shape(self, text: str) -> tuple[list[tuple[int, int, float, float]], float]:
        """Visual-order glyphs (font index, glyph id, x px, y offset px) and the advance width."""
        if text not in self._cache:
            self._cache[text] = self._shape(text)
        return self._cache[text]

    def _shape(self, text: str) -> tuple[list[tuple[int, int, float, float]], float]:
        if not text or not self.chain:
            return [], 0.0
        levels = _levels(text)
        picks = self._pick(text)
        runs: list[tuple[int, int, int, int]] = []
        start = 0
        for i in range(1, len(text) + 1):
            if i == len(text) or levels[i] != levels[start] or picks[i] != picks[start]:
                runs.append((start, i, levels[start], picks[start]))
                start = i
        order = list(range(len(runs)))
        top = max(r[2] for r in runs)
        low_odd = min((r[2] for r in runs if r[2] % 2), default=top + 1)
        for lvl in range(top, low_odd - 1, -1):
            i = 0
            while i < len(order):
                if runs[order[i]][2] >= lvl:
                    j = i
                    while j < len(order) and runs[order[j]][2] >= lvl:
                        j += 1
                    order[i:j] = order[i:j][::-1]
                    i = j
                else:
                    i += 1
        glyphs: list[tuple[int, int, float, float]] = []
        colored: list[tuple[float, str, int]] = []
        x = 0.0
        for ri in order:
            s, e, lvl, fi = runs[ri]
            f = self.chain[fi]
            self.used.add(fi)
            if f.color:
                colored.append((x, text[s:e], fi))
            buf = hb.Buffer()
            buf.add_str(text, s, e - s)
            buf.guess_segment_properties()
            buf.direction = "rtl" if lvl % 2 else "ltr"
            if self.lang:
                buf.language = self.lang
            hb.shape(f.font, buf, self.features)
            prev_cluster = None
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
                if info.codepoint == 0:
                    ch = text[info.cluster] if info.cluster < len(text) else ""
                    if ch and not ch.isspace() and unicodedata.category(ch) not in ("Cf", "Cc"):
                        self.missing.add(ch)
                if self.spacing and prev_cluster is not None and info.cluster != prev_cluster:
                    x += self.spacing
                prev_cluster = info.cluster
                glyphs.append((fi, info.codepoint, x + pos.x_offset * f.scale, pos.y_offset * f.scale))
                x += pos.x_advance * f.scale
        self.color_runs[text] = colored
        return glyphs, x

    def width(self, text: str) -> float:
        return self.shape(text)[1]


    @staticmethod
    def _segments(text: str) -> list[str]:
        """Pieces between break opportunities: after spaces, and between CJK characters (kinsoku-aware)."""
        segs: list[str] = []
        cur = ""
        for i, ch in enumerate(text):
            nxt = text[i + 1] if i + 1 < len(text) else ""
            cur += ch
            if not nxt:
                break
            if ch == " " and nxt != " ":
                segs.append(cur)
                cur = ""
            elif (_is_cjk(ord(ch)) or _is_cjk(ord(nxt))) and nxt not in _NO_START and ch not in _NO_END \
                    and not unicodedata.category(nxt).startswith("M") and nxt != " ":
                segs.append(cur)
                cur = ""
        if cur:
            segs.append(cur)
        return segs

    def _split_long(self, word: str, max_px: float) -> list[str]:
        """Emergency break inside a word at character-cluster boundaries (Thai, Lao, Khmer have no
        spaces; shortcut: no dictionary segmentation, breaks may fall mid-word - add one if Thai ships)."""
        parts, cur = [], ""
        for ch in word:
            joins = unicodedata.category(ch).startswith("M") or ch in "‍️"
            if cur and not joins and self.width((cur + ch).rstrip()) > max_px:
                parts.append(cur)
                cur = ch
            else:
                cur += ch
        return parts + ([cur] if cur else [])

    def wrap(self, para: str, max_px: float) -> list[str]:
        lines: list[str] = []
        cur = ""
        for seg in self._segments(para):
            trial = cur + seg
            if not cur or self.width(trial.rstrip()) <= max_px:
                cur = trial
            else:
                lines.append(cur.rstrip())
                cur = seg
            if self.width(cur.rstrip()) > max_px:
                pieces = self._split_long(cur, max_px)
                lines += [p.rstrip() for p in pieces[:-1]]
                cur = pieces[-1] if pieces else ""
        lines.append(cur.rstrip())
        return lines


    def draw(self, img, text: str, x: float, baseline: float, stroke_px: int = 0) -> None:
        """OR the glyph coverage of ``text`` into the L-mode image ``img`` (already offset)."""
        glyphs, _ = self.shape(text)
        W, H = img.size
        pad = stroke_px + 2
        for fi, gid, gx, gy in glyphs:
            f = self.chain[fi]
            if f.color and stroke_px == 0:
                continue
            var = tuple(sorted(f.var.items())) if f.var else None
            contours = _outline(f.path, var, gid)
            if not contours:
                continue
            polys = [np.column_stack((x + gx + c[:, 0] * f.scale, baseline - gy - c[:, 1] * f.scale)) for c in contours]
            allp = np.vstack(polys)
            x0, y0 = int(np.floor(allp[:, 0].min())) - pad, int(np.floor(allp[:, 1].min())) - pad
            x1, y1 = int(np.ceil(allp[:, 0].max())) + pad, int(np.ceil(allp[:, 1].max())) + pad
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
            if x1 <= x0 or y1 <= y0:
                continue
            local = [p - (x0, y0) for p in polys]
            cov = raster.fill_polygons(local, x1 - x0, y1 - y0, "nonzero")
            if stroke_px > 0:
                cov = np.maximum(cov, raster.stroke_polylines([(p, True, stroke_px, True) for p in local],
                                                               x1 - x0, y1 - y0))
            box = (x0, y0, x1, y1)
            under = np.asarray(img.crop(box))
            img.paste(Image.fromarray(np.maximum(under, cov), "L"), box)


    def draw_color(self, img, text: str, x: float, baseline: float, size_px: float) -> None:
        """Paint colour emoji of ``text`` into the RGBA ``img`` (already offset)."""
        from PIL import ImageDraw
        self.shape(text)
        req_sz = max(1, int(round(size_px)))

        def _draw_safe(canvas, pos, part_txt, pil_font, sz_ref):
            draw = ImageDraw.Draw(canvas)
            try:
                draw.text(pos, part_txt, font=pil_font, anchor="ls", embedded_color=True)
            except (ValueError, OSError):
                draw.text((pos[0], pos[1] - sz_ref * 0.85), part_txt, font=pil_font, embedded_color=True)

        for gx, part, fi in self.color_runs.get(text, []):
            try:
                font, actual_sz = _pil_font_with_strike(self.chain[fi].path, req_sz)
            except OSError:
                continue
            if actual_sz == req_sz:
                try:
                    _draw_safe(img, (x + gx, baseline), part, font, req_sz)
                except OSError:
                    continue
            else:
                # Bitmap colour emoji fonts (NotoColorEmoji 109px, Apple Color Emoji SBIX strikes)
                # only rasterise at fixed strike sizes; render at the strike size and LANCZOS-scale cleanly.
                pad = max(16, actual_sz // 2)
                tmp_w = max(actual_sz * (len(part) + 2), actual_sz * 2) + pad * 2
                tmp_h = actual_sz * 2 + pad * 2
                base_y = actual_sz + pad
                patch = Image.new("RGBA", (tmp_w, tmp_h), (0, 0, 0, 0))
                try:
                    _draw_safe(patch, (pad, base_y), part, font, actual_sz)
                except OSError:
                    continue
                bbox = patch.getbbox()
                if not bbox:
                    continue
                ratio = req_sz / float(actual_sz)
                crop = patch.crop(bbox)
                nw = max(1, int(round(crop.width * ratio)))
                nh = max(1, int(round(crop.height * ratio)))
                scaled = crop.resize((nw, nh), Image.LANCZOS)
                dx = int(round(x + gx + (bbox[0] - pad) * ratio))
                dy = int(round(baseline + (bbox[1] - base_y) * ratio))
                img.alpha_composite(scaled, (dx, dy))

    def outline_polys(self, text: str, x: float, baseline: float) -> list:
        """Glyph outlines of ``text`` as polygons in pixels (text to vector paths)."""
        glyphs, _ = self.shape(text)
        out = []
        for fi, gid, gx, gy in glyphs:
            f = self.chain[fi]
            var = tuple(sorted(f.var.items())) if f.var else None
            for c in _outline(f.path, var, gid):
                out.append(np.column_stack((x + gx + c[:, 0] * f.scale, baseline - gy - c[:, 1] * f.scale)))
        return out


@lru_cache(maxsize=256)
def _font_features(path: str) -> frozenset:
    """OpenType feature tags the font's GSUB / GPOS tables offer."""
    face = _face(path)[0]
    tags = set()
    for table in ("GSUB", "GPOS"):
        try:
            for si in range(len(face.get_table_script_tags(table))):
                tags |= set(face.get_language_feature_tags(table, si, 0xFFFF))
        except Exception:
            return frozenset({"*"})
    return frozenset(tags)


def unsupported_features(path: str, features: dict) -> list[str]:
    have = _font_features(path)
    if "*" in have:
        return []
    return [t for t, on in features.items() if on and t not in have and t not in ("kern", "liga", "calt")]


@lru_cache(maxsize=32)
def _pil_font(path: str, size: int):
    from PIL import ImageFont
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=32)
def _pil_font_with_strike(path: str, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(path, size), size
    except OSError:
        strikes = sorted((20, 32, 40, 48, 64, 96, 109, 128, 160), key=lambda s: (s < size, abs(s - size)))
        for st in strikes:
            try:
                return ImageFont.truetype(path, st), st
            except OSError:
                continue
        raise



def _needs(texts: list[str]) -> tuple[bool, bool, bool]:
    """(right-to-left, Indic / South-East Asian, CJK) present in any of the texts."""
    joined = "".join(texts)
    rtl = any(unicodedata.bidirectional(c) in ("R", "AL") for c in joined)
    complex_ = any(0x0900 <= ord(c) <= 0x0DFF or 0x0E00 <= ord(c) <= 0x0EFF or 0x1000 <= ord(c) <= 0x109F
                   or 0x1780 <= ord(c) <= 0x17FF for c in joined)
    cjk = any(_is_cjk(ord(c)) for c in joined)
    return rtl, complex_, cjk


def engine_notes(engine: str, texts: list[str]) -> list[str]:
    """What live text in these scripts needs on the engine side. engine "all" lists every engine."""
    rtl, complex_, cjk = _needs(texts)
    if not (rtl or complex_ or cjk):
        return []
    engines = ("unity", "unreal", "godot", "roblox") if engine == "all" else (engine,)
    out = []
    for e in engines:
        if e == "unity":
            if rtl or complex_:
                out.append("Unity: TextMeshPro on uGUI does not shape Arabic/Hebrew or Indic/Thai (letters come out "
                           "isolated, order reversed). Use UI Toolkit with the Advanced Text Generator "
                           "(-unity-text-generator: advanced; default from Unity 6.5) or RTLTMPro for uGUI.")
            if cjk:
                out.append("Unity: order CJK fallback font assets by language (a JP font above SC makes Chinese use "
                           "Japanese glyph forms); fallback glyphs take the root font's line height.")
        elif e == "unreal":
            if complex_:
                out.append("Unreal: set Text Shaping Method = Full Shaping on these text blocks - 'Auto' uses "
                           "kerning-only for left-to-right scripts, which breaks Devanagari, Bengali, Tamil and Thai.")
            if rtl or complex_ or cjk:
                out.append("Unreal: use a Composite Font with a sub-font per script range; add a Cultures filter so "
                           "Japanese and Chinese get their own Han glyphs.")
        elif e == "godot":
            if complex_ or cjk:
                out.append("Godot: enable Project Settings > internationalization/locale/include_text_server_data "
                           "(~4 MB ICU data) or Thai/CJK line breaking fails in exported builds.")
            if rtl:
                out.append("Godot: TextServerAdvanced shapes RTL; leave Label text_direction on Auto (or set RTL).")
            out.append("Godot: give the Label font fallbacks covering these scripts (FontFile.fallbacks).")
        elif e == "roblox":
            out.append("Roblox: few built-in fonts cover Arabic, Hebrew, Indic, Thai or CJK (Builder Sans is Latin "
                       "only) - check the text in Studio, or bake stylised headers as images (bake_text=true).")
            if rtl:
                out.append("Roblox: set TextDirection on RTL labels; mixed digits and punctuation have had bidi bugs.")
    return out
