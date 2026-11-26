"""Font discovery and loading (bundled fonts, user fonts, system fonts)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

BUNDLED_DIR = Path(__file__).parent / "assets" / "fonts"
FONT_EXTS = {".ttf", ".otf", ".ttc"}

WEIGHT_NAMES = {
    "thin": 100, "hairline": 100, "extralight": 200, "ultralight": 200, "light": 300,
    "regular": 400, "normal": 400, "book": 400, "medium": 500, "semibold": 600, "demibold": 600,
    "bold": 700, "extrabold": 800, "ultrabold": 800, "black": 900, "heavy": 900,
}


def parse_weight(weight) -> int:
    if weight is None:
        return 400
    if isinstance(weight, (int, float)):
        return int(max(1, min(1000, weight)))
    key = str(weight).lower().replace(" ", "").replace("-", "")
    if key.isdigit():
        return int(key)
    if key in WEIGHT_NAMES:
        return WEIGHT_NAMES[key]
    raise ValueError(f"Unknown font weight {weight!r}. Use 100-900 or a name like 'regular', 'semibold', 'bold'.")


def _style_weight(style: str) -> int:
    key = style.lower().replace(" ", "").replace("-", "").replace("italic", "").replace("oblique", "")
    best = 400
    for name, value in sorted(WEIGHT_NAMES.items(), key=lambda kv: -len(kv[0])):
        if name in key:
            best = value
            break
    return best


def _system_font_dirs() -> list[Path]:
    dirs: list[Path] = []
    if sys.platform.startswith("win"):
        dirs.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
                 Path.home() / ".local" / "share" / "fonts"]
    return [d for d in dirs if d.is_dir()]


class FontLibrary:
    """Indexes font files by family name. System fonts are scanned lazily."""

    def __init__(self, user_dir: Path | None = None):
        self.user_dir = user_dir
        self._index: dict[str, list[dict]] = {}
        self._display: dict[str, str] = {}
        self._sources: dict[str, str] = {}
        self._system_scanned = False
        self._scan(BUNDLED_DIR, "bundled")
        if user_dir and user_dir.is_dir():
            self._scan(user_dir, "user")

    def _scan(self, root: Path, source: str) -> None:
        if not root.is_dir():
            return
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in FONT_EXTS:
                continue
            font = None
            for probe_sz in (16, 109, 64, 48, 40, 32, 20, 128):
                try:
                    font = ImageFont.truetype(str(path), probe_sz)
                    family, style = font.getname()
                    break
                except Exception:
                    font = None
            if font is None:
                continue
            if not family:
                continue
            variable = False
            try:
                axes = font.get_variation_axes()
                variable = any(_axis_name(a) == "weight" for a in axes)
            except Exception:
                pass
            key = family.lower()
            entry = {"path": str(path), "style": style or "Regular", "weight": _style_weight(style or ""),
                     "italic": "italic" in (style or "").lower() or "oblique" in (style or "").lower(),
                     "variable": variable}
            self._index.setdefault(key, []).append(entry)
            self._display.setdefault(key, family)
            self._sources.setdefault(key, source)

    def _ensure_system(self) -> None:
        if self._system_scanned:
            return
        self._system_scanned = True
        for d in _system_font_dirs():
            self._scan(d, "system")

    def rescan_user(self) -> None:
        if self.user_dir and self.user_dir.is_dir():
            self._scan(self.user_dir, "user")

    def families(self, include_system: bool = False) -> list[dict]:
        if include_system:
            self._ensure_system()
        out = []
        for key in sorted(self._index):
            source = self._sources[key]
            if source == "system" and not include_system:
                continue
            entries = self._index[key]
            if any(e["variable"] for e in entries):
                weights = "variable"
            else:
                weights = sorted({e["weight"] for e in entries if not e["italic"]}) or sorted({e["weight"] for e in entries})
            item = {"family": self._display[key], "source": source, "weights": weights}
            if any(e["italic"] for e in entries):
                item["italic"] = True
            out.append(item)
        return out

    def resolve(self, family: str | None, weight: int, italic: bool = False) -> tuple[str | None, int | None, bool]:
        """Return (path, variable_weight, faux_italic). faux_italic means the family has no italic
        file, so the renderer should slant the upright glyphs instead."""
        if not family:
            family = "Inter"
        key = family.lower().strip()
        if os.path.isfile(family) and Path(family).suffix.lower() in FONT_EXTS:
            return family, None, italic
        if key not in self._index:
            self._ensure_system()
        if key not in self._index:
            known = ", ".join(f["family"] for f in self.families(include_system=False))
            raise ValueError(
                f"Font '{family}' not found. Bundled/user fonts: {known}. "
                "Call list_fonts(include_system=true) to see installed system fonts, "
                "or drop a .ttf/.otf into the workspace 'fonts' folder."
            )
        entries = self._index[key]
        slanted = [e for e in entries if e["italic"]]
        upright = [e for e in entries if not e["italic"]] or entries
        pool = slanted if (italic and slanted) else upright
        faux = italic and not slanted
        for e in pool:
            if e["variable"]:
                return e["path"], weight, faux
        best = min(pool, key=lambda e: abs(e["weight"] - weight))
        return best["path"], None, faux


def _axis_name(axis: dict) -> str:
    name = axis.get("name", "")
    if isinstance(name, bytes):
        name = name.decode("utf-8", "ignore")
    return str(name).strip().lower()


@lru_cache(maxsize=256)
def load_font(path: str | None, size_px: int, var_weight: int | None):
    size_px = max(1, int(size_px))
    if path is None:
        return ImageFont.load_default(size_px)
    font = ImageFont.truetype(path, size_px)
    if var_weight is not None:
        try:
            axes = font.get_variation_axes()
            values = []
            for axis in axes:
                if _axis_name(axis) == "weight":
                    values.append(max(axis["minimum"], min(axis["maximum"], var_weight)))
                elif _axis_name(axis) == "optical size":
                    values.append(max(axis["minimum"], min(axis["maximum"], size_px)))
                else:
                    values.append(axis["default"])
            font.set_variation_by_axes(values)
        except Exception:
            pass
    return font


def missing_glyphs(font, text: str) -> list[str]:
    """Characters in ``text`` that the font cannot draw (best effort)."""
    try:
        ref = font.getmask("\uffff")
        ref_bytes = bytes(ref)
        ref_size = ref.size
    except Exception:
        return []
    missing = []
    for ch in sorted(set(text)):
        if ch.isspace():
            continue
        try:
            mask = font.getmask(ch)
        except Exception:
            continue
        if mask.getbbox() is None or (mask.size == ref_size and bytes(mask) == ref_bytes):
            missing.append(ch)
    return missing
