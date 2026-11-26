"""In-memory document store with JSON persistence, theme and undo."""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .fonts import FontLibrary
from .render import Renderer, shift_element

_log = logging.getLogger("uiforge_mcp.store")

ELEMENT_TYPES = ("rect", "ellipse", "polygon", "line", "path", "text", "image", "arc", "ticks", "instance",
                 "boolean", "input", "scroll", "slider", "toggle", "dropdown")
MAX_CANVAS = 8192
MAX_UNDO = 40
MAX_VERSIONS = 30


def default_workspace() -> Path:
    env = os.environ.get("UIFORGE_MCP_DIR")
    if env:
        return Path(env).expanduser()
    local = Path.cwd() / ".uiforge"
    if local.is_dir():
        return local
    return Path.home() / "UIForge"


def slugify(name: str, fallback: str = "canvas") -> str:
    slug = re.sub(r"[^\w-]+", "_", str(name).strip().replace("İ", "i")).strip("_").lower()
    return slug or fallback


class Store:
    def __init__(self, workspace: Path | None = None, persist: bool = True):
        self.workspace = Path(workspace) if workspace else default_workspace()
        self.persist = persist
        self.projects_dir = self.workspace / "projects"
        self.exports_dir = self.workspace / "exports"
        self.fonts_dir = self.workspace / "fonts"
        if persist:
            for d in (self.projects_dir, self.exports_dir, self.fonts_dir):
                d.mkdir(parents=True, exist_ok=True)
        self.fonts = FontLibrary(self.fonts_dir if persist else None)
        self.canvases: dict[str, dict] = {}
        self.theme: dict[str, dict] = {"colors": {}, "styles": {}}
        self.strings: dict = {"default": None, "tables": {}}
        self._undo: dict[str, list[dict]] = {}
        self._redo: dict[str, list[dict]] = {}
        self._version_mem: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._disk_stamps: dict[str, tuple[int, int]] = {}
        self.rev: int = 0
        self._listeners: list = []
        if persist:
            self._load()

    def on_change(self, fn) -> None:
        """Register a callback invoked as fn(canvas_id | None) whenever the store changes."""
        with self._lock:
            if fn not in self._listeners:
                self._listeners.append(fn)

    def _notify(self, canvas_id: str | None = None) -> None:
        with self._lock:
            self.rev += 1
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(canvas_id)
            except Exception as exc:
                _log.debug("Store change listener failed: %s", exc)

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int] | None:
        try:
            st = path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _record_stamp(self, path: Path) -> None:
        s = self._stamp(path)
        if s is not None:
            self._disk_stamps[str(path)] = s

    def sync_from_disk(self) -> bool:
        """Reload canvases/theme/strings modified externally by another process (Combined Mode safety)."""
        if not self.persist:
            return False
        changed = False
        with self._lock:
            strings_file = self.workspace / "strings.json"
            sf = self._stamp(strings_file)
            if sf and self._disk_stamps.get(str(strings_file)) != sf:
                try:
                    data = json.loads(strings_file.read_text(encoding="utf-8"))
                    self.strings = {"default": data.get("default"), "tables": dict(data.get("tables", {}))}
                    self._disk_stamps[str(strings_file)] = sf
                    changed = True
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    _log.warning("Could not reload %s: %s", strings_file, exc)

            theme_file = self.workspace / "theme.json"
            tf = self._stamp(theme_file)
            if tf and self._disk_stamps.get(str(theme_file)) != tf:
                try:
                    data = json.loads(theme_file.read_text(encoding="utf-8"))
                    self.theme = {"colors": dict(data.get("colors", {})), "styles": dict(data.get("styles", {})),
                                  "modes": dict(data.get("modes", {})), "mode": data.get("mode"),
                                  "numbers": dict(data.get("numbers", {})), "materials": dict(data.get("materials", {})),
                                  "environment": dict(data.get("environment", {})) if isinstance(data.get("environment"), dict) else {},
                                  "profile": dict(data.get("profile", {})) if isinstance(data.get("profile"), dict) else {}}
                    self._disk_stamps[str(theme_file)] = tf
                    changed = True
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    _log.warning("Could not reload %s: %s", theme_file, exc)

            if self.projects_dir.is_dir():
                seen_ids: set[str] = set()
                for path in sorted(self.projects_dir.glob("*.json")):
                    pf = self._stamp(path)
                    if pf is None:
                        continue
                    cid_guess = path.stem
                    seen_ids.add(cid_guess)
                    if self._disk_stamps.get(str(path)) != pf:
                        try:
                            canvas = json.loads(path.read_text(encoding="utf-8"))
                            if {"id", "width", "height", "elements"} <= set(canvas):
                                self.canvases[canvas["id"]] = canvas
                                seen_ids.add(canvas["id"])
                                self._disk_stamps[str(path)] = pf
                                changed = True
                        except (OSError, json.JSONDecodeError, ValueError) as exc:
                            _log.warning("Could not reload %s: %s", path, exc)
                # Remove canvases deleted on disk by another process
                for existing_id in list(self.canvases):
                    p = self.projects_dir / f"{existing_id}.json"
                    if str(p) in self._disk_stamps and existing_id not in seen_ids and not p.is_file():
                        self.canvases.pop(existing_id, None)
                        self._disk_stamps.pop(str(p), None)
                        changed = True
        if changed:
            self._notify(None)
        return changed

    def _load(self) -> None:
        with self._lock:
            strings_file = self.workspace / "strings.json"
            if strings_file.is_file():
                try:
                    data = json.loads(strings_file.read_text(encoding="utf-8"))
                    self.strings = {"default": data.get("default"), "tables": dict(data.get("tables", {}))}
                    self._record_stamp(strings_file)
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    _log.warning("Failed to load %s: %s", strings_file, exc)
            theme_file = self.workspace / "theme.json"
            if theme_file.is_file():
                try:
                    data = json.loads(theme_file.read_text(encoding="utf-8"))
                    self.theme = {"colors": dict(data.get("colors", {})), "styles": dict(data.get("styles", {})),
                                  "modes": dict(data.get("modes", {})), "mode": data.get("mode"),
                                  "numbers": dict(data.get("numbers", {})), "materials": dict(data.get("materials", {})),
                                  "environment": dict(data.get("environment", {})) if isinstance(data.get("environment"), dict) else {},
                                  "profile": dict(data.get("profile", {})) if isinstance(data.get("profile"), dict) else {}}
                    self._record_stamp(theme_file)
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    _log.warning("Failed to load %s: %s", theme_file, exc)
            for path in sorted(self.projects_dir.glob("*.json")):
                try:
                    canvas = json.loads(path.read_text(encoding="utf-8"))
                    if {"id", "width", "height", "elements"} <= set(canvas):
                        self.canvases[canvas["id"]] = canvas
                        self._record_stamp(path)
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    _log.warning("Failed to load canvas %s: %s", path, exc)

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        """Write via a unique per-call temp file + retry replace so concurrent threads/processes never collide."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(5):
                try:
                    os.replace(tmp_path, path)
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.015 * (attempt + 1))
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def save_canvas(self, canvas: dict) -> None:
        with self._lock:
            if any(isinstance(e.get("layout"), dict) for e in canvas.get("elements", [])):
                from .autolayout import reflow
                reflow(self, canvas)
            if self.persist:
                path = self.projects_dir / f"{canvas['id']}.json"
                self._atomic_write(path, json.dumps(canvas, ensure_ascii=False, indent=1, sort_keys=True))
                self._record_stamp(path)
        self._notify(canvas["id"])

    def save_theme(self) -> None:
        with self._lock:
            if self.persist:
                path = self.workspace / "theme.json"
                self._atomic_write(path, json.dumps(self.theme, ensure_ascii=False, indent=1, sort_keys=True))
                self._record_stamp(path)
        self._notify(None)


    def get(self, canvas_id: str) -> dict:
        if canvas_id in self.canvases:
            return self.canvases[canvas_id]
        slug = slugify(canvas_id)
        if slug in self.canvases:
            return self.canvases[slug]
        known = ", ".join(sorted(self.canvases)) or "(none yet - call create_canvas)"
        raise ValueError(f"Canvas '{canvas_id}' not found. Existing canvases: {known}")

    def create_canvas(self, name: str, width: int, height: int, background: Any = None) -> dict:
        with self._lock:
            width, height = int(width), int(height)
            if not (1 <= width <= MAX_CANVAS and 1 <= height <= MAX_CANVAS):
                raise ValueError(f"Canvas size must be between 1 and {MAX_CANVAS} px per side")
            cid = slugify(name)
            if cid in self.canvases:
                raise ValueError(f"Canvas '{cid}' already exists. Pick another name, or delete_canvas / duplicate_canvas.")
            canvas = {"id": cid, "name": str(name), "width": width, "height": height, "background": background,
                      "elements": [], "counters": {}}
            self._validate_background(canvas)
            self.canvases[cid] = canvas
            self.save_canvas(canvas)
            return canvas

    def _validate_background(self, canvas: dict) -> None:
        probe = dict(canvas, width=min(canvas["width"], 8), height=min(canvas["height"], 8), elements=[])
        Renderer(probe, self.theme, self.fonts, lookup=self.get).render()

    def update_canvas(self, canvas: dict, **changes: Any) -> None:
        self.checkpoint(canvas)
        for key in ("width", "height"):
            if changes.get(key) is not None:
                value = int(changes[key])
                if not 1 <= value <= MAX_CANVAS:
                    raise ValueError(f"Canvas size must be between 1 and {MAX_CANVAS} px per side")
                canvas[key] = value
        if changes.get("name") is not None:
            canvas["name"] = str(changes["name"])
        if "background" in changes:
            old = canvas.get("background")
            canvas["background"] = changes["background"]
            try:
                self._validate_background(canvas)
            except Exception:
                canvas["background"] = old
                raise
        self.save_canvas(canvas)


    def _versions(self, cid: str) -> dict:
        mem = self._version_mem
        if cid not in mem:
            mem[cid] = {}
            folder = self.projects_dir / "versions" / cid
            if self.persist and folder.is_dir():
                for path in sorted(folder.glob("*.json")):
                    try:
                        mem[cid][path.stem] = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
        return mem[cid]

    def save_version(self, canvas: dict, name: str | None, note: str | None) -> dict:
        with self._lock:
            versions = self._versions(canvas["id"])
            key = slugify(name or f"v{len(versions) + 1}", "version")
            if key in versions:
                raise ValueError(f"version '{key}' already exists - pick another name or delete it first")
            if len(versions) >= MAX_VERSIONS:
                raise ValueError(f"at most {MAX_VERSIONS} versions per canvas - delete old ones first")
            entry = {"name": key, "note": note or "", "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "canvas": copy.deepcopy(canvas)}
            versions[key] = entry
            if self.persist:
                folder = self.projects_dir / "versions" / canvas["id"]
                self._atomic_write(folder / f"{key}.json", json.dumps(entry, ensure_ascii=False))
            return entry

    def list_versions(self, canvas: dict) -> list[dict]:
        return [{"name": v["name"], "note": v.get("note", ""), "saved": v.get("saved", ""),
                 "elements": len(v["canvas"].get("elements", []))} for v in self._versions(canvas["id"]).values()]

    def restore_version(self, canvas: dict, name: str) -> None:
        versions = self._versions(canvas["id"])
        key = slugify(name, "version")
        if key not in versions:
            raise ValueError(f"no version '{key}'. Versions: {', '.join(versions) or '(none - save one first)'}")
        self.checkpoint(canvas)
        snapshot = copy.deepcopy(versions[key]["canvas"])
        snapshot["id"] = canvas["id"]
        canvas.clear()
        canvas.update(snapshot)
        self.save_canvas(canvas)

    def delete_version(self, canvas: dict, name: str) -> None:
        versions = self._versions(canvas["id"])
        key = slugify(name, "version")
        if versions.pop(key, None) is None:
            raise ValueError(f"no version '{key}'. Versions: {', '.join(versions) or '(none)'}")
        path = self.projects_dir / "versions" / canvas["id"] / f"{key}.json"
        if self.persist and path.is_file():
            path.unlink()

    def delete_canvas(self, canvas: dict) -> None:
        with self._lock:
            cid = canvas["id"]
            self.canvases.pop(cid, None)
            self._undo.pop(cid, None)
            self._redo.pop(cid, None)
            if self.persist:
                path = self.projects_dir / f"{cid}.json"
                self._disk_stamps.pop(str(path), None)
                if path.is_file():
                    path.unlink()
        self._notify(cid)

    def duplicate_canvas(self, canvas: dict, new_name: str) -> dict:
        with self._lock:
            cid = slugify(new_name)
            if cid in self.canvases:
                raise ValueError(f"Canvas '{cid}' already exists")
            clone = copy.deepcopy(canvas)
            clone["id"], clone["name"] = cid, str(new_name)
            self.canvases[cid] = clone
            self.save_canvas(clone)
            return clone


    def checkpoint(self, canvas: dict) -> None:
        with self._lock:
            stack = self._undo.setdefault(canvas["id"], [])
            stack.append(copy.deepcopy(canvas))
            del stack[:-MAX_UNDO]
            self._redo.pop(canvas["id"], None)

    def undo(self, canvas: dict) -> bool:
        with self._lock:
            stack = self._undo.get(canvas["id"])
            if not stack:
                return False
            previous = stack.pop()
            redo = self._redo.setdefault(canvas["id"], [])
            redo.append(copy.deepcopy(canvas))
            del redo[:-MAX_UNDO]
            canvas.clear()
            canvas.update(previous)
            self.save_canvas(canvas)
            return True

    def redo(self, canvas: dict) -> bool:
        with self._lock:
            stack = self._redo.get(canvas["id"])
            if not stack:
                return False
            nxt = stack.pop()
            self._undo.setdefault(canvas["id"], []).append(copy.deepcopy(canvas))
            canvas.clear()
            canvas.update(nxt)
            self.save_canvas(canvas)
            return True

    def drop_checkpoint(self, canvas: dict) -> None:
        stack = self._undo.get(canvas["id"])
        if stack:
            previous = stack.pop()
            canvas.clear()
            canvas.update(previous)


    def renderer(self, canvas: dict, scale: float = 1.0, state: str | None = None,
                 language: str | None = None) -> Renderer:
        return Renderer(canvas, self.theme, self.fonts, scale, lookup=self.get, state=state, language=language,
                        strings=self.strings)

    def require_glyphs(self, canvas: dict, language: str | None = None) -> None:
        """Exports refuse text that would ship with missing glyphs (tofu boxes)."""
        problems = self.renderer(canvas, language=language).glyph_problems()
        if problems:
            where = "; ".join(f"{eid}: {chars!r}" for eid, chars in problems.items())
            raise ValueError(f"export refused - no font can draw these characters ({where}). Set a font that "
                             "has them on those elements, or drop a .ttf/.otf covering them into the workspace "
                             "'fonts' folder.")


    def set_strings(self, language: str, strings: dict, default: bool, replace: bool) -> dict:
        with self._lock:
            lang = str(language).strip()
            if not lang or lang.startswith("pseudo"):
                raise ValueError("language must be a code like 'en', 'tr', 'de' ('pseudo', 'pseudo-long', 'pseudo-rtl' are built in)")
            table = {} if replace else dict(self.strings["tables"].get(lang, {}))
            for key, value in (strings or {}).items():
                if value is None:
                    table.pop(key, None)
                else:
                    table[str(key)] = str(value)
            self.strings["tables"][lang] = table
            if default or not self.strings.get("default"):
                self.strings["default"] = lang
            if self.persist:
                path = self.workspace / "strings.json"
                self._atomic_write(path, json.dumps(self.strings, ensure_ascii=False, indent=1))
                self._record_stamp(path)
        self._notify(None)
        return table

    def find(self, canvas: dict, element_id: str) -> dict:
        for el in canvas["elements"]:
            if el["id"] == element_id:
                return el
        ids = ", ".join(e["id"] for e in canvas["elements"]) or "(canvas is empty)"
        raise ValueError(f"Element '{element_id}' not found on canvas '{canvas['id']}'. Elements: {ids}")

    def select(self, canvas: dict, ids: list[str] | None = None, group: str | None = None) -> list[dict]:
        if ids:
            return [self.find(canvas, i) for i in ids]
        if group:
            found = [e for e in canvas["elements"] if e.get("group") == group]
            if not found:
                groups = ", ".join(sorted({e["group"] for e in canvas["elements"] if e.get("group")})) or "(none)"
                raise ValueError(f"No elements in group '{group}'. Groups: {groups}")
            return found
        raise ValueError("Give either ids or group")

    def _new_id(self, canvas: dict, etype: str, wanted: str | None) -> str:
        existing = {e["id"] for e in canvas["elements"]}
        if wanted:
            eid = slugify(wanted, etype)
            if eid in existing:
                raise ValueError(f"Element id '{eid}' is already used on this canvas")
            return eid
        counters = canvas.setdefault("counters", {})
        while True:
            counters[etype] = counters.get(etype, 0) + 1
            eid = f"{etype}{counters[etype]}"
            if eid not in existing:
                return eid

    def _validate(self, canvas: dict, el: dict) -> list[str]:
        """Render the element once at low resolution so bad input fails immediately."""
        scale = min(1.0, 256.0 / max(canvas["width"], canvas["height"]))
        r = self.renderer(canvas, max(scale, 0.05))
        r.render_element(el)
        return r.warnings

    def add_element(self, canvas: dict, etype: str, props: dict, checkpoint: bool = True) -> tuple[dict, list[str]]:
        with self._lock:
            if etype not in ELEMENT_TYPES:
                raise ValueError(f"Unknown element type '{etype}'. Types: {', '.join(ELEMENT_TYPES)}")
            props = {k: v for k, v in props.items() if v is not None}
            el = {"id": self._new_id(canvas, etype, props.pop("id", None)), "type": etype}
            el.update(props)
            if el.get("clip"):
                self.find(canvas, el["clip"])
            if el.get("layer"):
                el["layer"] = self.get_layer(canvas, el["layer"])["name"]
            elif canvas.get("active_layer") and any(l["name"] == canvas["active_layer"] for l in canvas.get("layers", [])):
                el["layer"] = canvas["active_layer"]
            if checkpoint:
                self.checkpoint(canvas)
            canvas["elements"].append(el)
            try:
                warnings = self._validate(canvas, el)
            except Exception:
                canvas["elements"].remove(el)
                if checkpoint:
                    self._undo[canvas["id"]].pop()
                raise
            self.save_canvas(canvas)
            return el, warnings

    def update_element(self, canvas: dict, el: dict, props: dict, checkpoint: bool = True) -> list[str]:
        with self._lock:
            if "id" in props or "type" in props:
                raise ValueError("id and type cannot be changed; duplicate or re-add the element instead")
            backup = copy.deepcopy(el)
            if checkpoint:
                self.checkpoint(canvas)
            for key, value in props.items():
                if key == "style" and isinstance(value, dict) and isinstance(el.get("style"), (dict, str)):
                    merged = dict(el["style"]) if isinstance(el["style"], dict) else {"use": el["style"]}
                    for sk, sv in value.items():
                        if sv is None:
                            merged.pop(sk, None)
                        else:
                            merged[sk] = sv
                    el["style"] = merged
                elif value is None:
                    el.pop(key, None)
                else:
                    el[key] = value
            try:
                if el.get("clip"):
                    self.find(canvas, el["clip"])
                if el.get("layer"):
                    if str(el["layer"]).lower() == "base":
                        el.pop("layer")
                    else:
                        el["layer"] = self.get_layer(canvas, el["layer"])["name"]
                warnings = self._validate(canvas, el)
            except Exception:
                el.clear()
                el.update(backup)
                if checkpoint:
                    self._undo[canvas["id"]].pop()
                raise
            self.save_canvas(canvas)
            return warnings

    def delete_elements(self, canvas: dict, elements: list[dict], checkpoint: bool = True) -> list[str]:
        with self._lock:
            if checkpoint:
                self.checkpoint(canvas)
            ids = {e["id"] for e in elements}
            canvas["elements"] = [e for e in canvas["elements"] if e["id"] not in ids]
            for e in canvas["elements"]:
                if e.get("clip") in ids:
                    e.pop("clip", None)
            for anim in canvas.get("animations", {}).values():
                anim["tracks"] = [t for t in anim["tracks"] if t["target"] not in ids]
            self.save_canvas(canvas)
            return sorted(ids)

    @staticmethod
    def shift(el: dict, dx: float, dy: float) -> None:
        shift_element(el, dx, dy)

    def move_elements(self, canvas: dict, elements: list[dict], dx: float, dy: float, checkpoint: bool = True) -> None:
        with self._lock:
            if checkpoint:
                self.checkpoint(canvas)
            for el in elements:
                self.shift(el, float(dx), float(dy))
            self.save_canvas(canvas)

    def reorder(self, canvas: dict, el: dict, position: Any, checkpoint: bool = True) -> int:
        with self._lock:
            others = [e for e in canvas["elements"] if e is not el]
            idx = canvas["elements"].index(el)
            pos = str(position).lower().strip()
            if pos == "front":
                new = len(others)
            elif pos == "back":
                new = 0
            elif pos == "forward":
                new = min(len(others), idx + 1)
            elif pos == "backward":
                new = max(0, idx - 1)
            elif pos.startswith(("above:", "below:")):
                target = str(position).split(":", 1)[1].strip()
                if target == el["id"]:
                    raise ValueError("cannot reorder an element relative to itself")
                other = self.find(canvas, target)
                new = others.index(other) + (1 if pos.startswith("above:") else 0)
            else:
                try:
                    new = max(0, min(len(others), int(position)))
                except (TypeError, ValueError):
                    raise ValueError("position must be 'front', 'back', 'forward', 'backward', 'above:<id>', "
                                     "'below:<id>' or an index") from None
            if checkpoint:
                self.checkpoint(canvas)
            others.insert(new, el)
            canvas["elements"] = others
            self.save_canvas(canvas)
            return new

    def duplicate_element(self, canvas: dict, el: dict, dx: float, dy: float, new_id: str | None,
                          props: dict | None, count: int = 1, rotate: float = 0.0,
                          pivot: list[float] | None = None, checkpoint: bool = True) -> list[tuple[dict, list[str]]]:
        """Make ``count`` copies. Copy i is moved by (dx*i, dy*i) and, when ``rotate`` is set, turned by
        rotate*i degrees around ``pivot`` (default: the element's own pivot) - a radial array."""
        count = int(count)
        if count < 1 or count > 360:
            raise ValueError("count must be between 1 and 360")
        rotate = float(rotate or 0)
        if pivot is not None:
            try:
                pivot_xy = (float(pivot[0]), float(pivot[1]))
            except (TypeError, IndexError, ValueError) as exc:
                raise ValueError("pivot must be [x, y]") from exc
        else:
            pivot_xy = None
        r = self.renderer(canvas)
        from .render import resolve_style
        own = r._pivot(el, r._geom_box(el, resolve_style(el.get("style"), self.theme)))
        if checkpoint:
            self.checkpoint(canvas)
        made: list[tuple[dict, list[str]]] = []
        try:
            for i in range(1, count + 1):
                tmp = copy.deepcopy(el)
                tmp.pop("id")
                self.shift(tmp, float(dx) * i, float(dy) * i)
                if rotate:
                    angle = rotate * i
                    px, py = pivot_xy or (own[0] + float(dx) * i, own[1] + float(dy) * i)
                    cx, cy = own[0] + float(dx) * i, own[1] + float(dy) * i
                    a = math.radians(angle)
                    nx = px + (cx - px) * math.cos(a) - (cy - py) * math.sin(a)
                    ny = py + (cx - px) * math.sin(a) + (cy - py) * math.cos(a)
                    self.shift(tmp, nx - cx, ny - cy)
                    tmp["rotation"] = round(float(tmp.get("rotation", 0) or 0) + angle, 4)
                etype = tmp.pop("type")
                if new_id:
                    tmp["id"] = new_id if count == 1 else f"{new_id}_{i}"
                new_el, warnings = self.add_element(canvas, etype, tmp, checkpoint=False)
                if props:
                    warnings = self.update_element(canvas, new_el, props, checkpoint=False)
                made.append((new_el, warnings))
        except Exception:
            if checkpoint:
                self.drop_checkpoint(canvas)
                self.save_canvas(canvas)
            raise
        return made

    def fit_canvas(self, canvas: dict, padding: float = 0.0, include_animations: bool = True) -> dict:
        """Shrink or grow the canvas to what is actually painted (effects included) plus padding, and
        move every element (and position keyframes) so nothing changes visually."""
        from .animation import apply_animation
        frames = [canvas]
        if include_animations:
            for anim in (canvas.get("animations") or {}).values():
                dur = float(anim.get("duration", 1) or 1)
                for j in range(13):
                    frames.append(apply_animation(canvas, anim, dur * j / 12, self.theme.get("colors", {}))[0])
        pad_big = 2048
        box = None
        for frame in frames:
            probe = dict(frame, width=frame["width"] + 2 * pad_big, height=frame["height"] + 2 * pad_big,
                         elements=copy.deepcopy(frame["elements"]))
            for e in probe["elements"]:
                shift_element(e, pad_big, pad_big)
            img = Renderer(probe, self.theme, self.fonts, 0.5, lookup=self.get).render(include_background=False)
            bb = img.getchannel("A").point(lambda v: 255 if v > 2 else 0).getbbox()
            if bb is None:
                continue
            fb = (bb[0] * 2 - pad_big, bb[1] * 2 - pad_big, bb[2] * 2 - pad_big, bb[3] * 2 - pad_big)
            box = fb if box is None else (min(box[0], fb[0]), min(box[1], fb[1]), max(box[2], fb[2]), max(box[3], fb[3]))
        if box is None:
            raise ValueError("nothing is painted on this canvas - add visible elements first")
        pad = float(padding)
        x0, y0 = math.floor(box[0] - 1 - pad), math.floor(box[1] - 1 - pad)
        x1, y1 = math.ceil(box[2] + 1 + pad), math.ceil(box[3] + 1 + pad)
        w, h = int(x1 - x0), int(y1 - y0)
        if w > MAX_CANVAS or h > MAX_CANVAS:
            raise ValueError(f"fitted canvas would be {w}x{h}, over the {MAX_CANVAS} limit")
        dx, dy = -float(x0), -float(y0)
        self.checkpoint(canvas)
        for e in canvas["elements"]:
            shift_element(e, dx, dy)
        moved_tracks = 0
        for anim in (canvas.get("animations") or {}).values():
            for track in anim.get("tracks", []):
                prop = track["property"]
                for kf in track["keyframes"]:
                    v = kf["value"]
                    if prop in ("x", "cx"):
                        kf["value"] = float(v) + dx
                    elif prop in ("y", "cy"):
                        kf["value"] = float(v) + dy
                    elif prop == "origin" and isinstance(v, (list, tuple)):
                        kf["value"] = [float(v[0]) + dx, float(v[1]) + dy]
                    elif prop == "points" and isinstance(v, (list, tuple)):
                        kf["value"] = [[float(q[0]) + dx, float(q[1]) + dy] for q in v]
                    else:
                        continue
                    moved_tracks += 1
        canvas["width"], canvas["height"] = w, h
        self.save_canvas(canvas)
        return {"width": w, "height": h, "moved_by": [round(dx, 2), round(dy, 2)], "keyframes_moved": moved_tracks}


    def get_layer(self, canvas: dict, name: str) -> dict:
        layers = canvas.get("layers") or []
        key = slugify(name, "layer")
        for layer in layers:
            if layer["name"] in (name, key):
                return layer
        known = ", ".join(l["name"] for l in layers) or "(none yet - call create_layer)"
        raise ValueError(f"Layer '{name}' not found on canvas '{canvas['id']}'. Layers (bottom to top): {known}. "
                         "Elements without a layer sit in the implicit bottom layer 'base'.")

    def _layer_index(self, canvas: dict, position: Any, moving: dict | None = None) -> int:
        others = [l for l in canvas.get("layers", []) if l is not moving]
        if position is None:
            return len(others)
        pos = str(position).lower().strip()
        if pos in ("top", "front"):
            return len(others)
        if pos in ("bottom", "back"):
            return 0
        if pos.startswith(("above:", "below:")):
            target = self.get_layer(canvas, str(position).split(":", 1)[1].strip())
            if target is moving:
                raise ValueError("cannot place a layer relative to itself")
            return others.index(target) + (1 if pos.startswith("above:") else 0)
        try:
            return max(0, min(len(others), int(position)))
        except (TypeError, ValueError):
            raise ValueError("layer position must be 'top', 'bottom', 'above:<layer>', 'below:<layer>' or an index "
                             "(0 = lowest)") from None

    def _check_layer(self, canvas: dict, layer: dict) -> None:
        """Render a tiny probe through the layer so a bad style / blend fails immediately."""
        probe = {"id": "layer_probe", "width": 24, "height": 24, "background": None,
                 "layers": [dict(layer, clip=False, visible=True)],
                 "elements": [{"id": "p", "type": "rect", "x": 6, "y": 6, "width": 12, "height": 12,
                               "layer": layer["name"]}]}
        Renderer(probe, self.theme, self.fonts, lookup=self.get).render()

    def create_layer(self, canvas: dict, name: str, settings: dict, position: Any, checkpoint: bool = True) -> dict:
        key = slugify(name, "layer")
        if key == "base":
            raise ValueError("'base' is the name of the implicit bottom layer; pick another name")
        layers = canvas.setdefault("layers", [])
        if any(l["name"] == key for l in layers):
            raise ValueError(f"Layer '{key}' already exists; use update_layer to change it")
        layer = {"name": key}
        layer.update({k: v for k, v in settings.items() if v is not None})
        self._check_layer(canvas, layer)
        index = self._layer_index(canvas, position)
        if checkpoint:
            self.checkpoint(canvas)
        layers.insert(index, layer)
        canvas["active_layer"] = key
        self.save_canvas(canvas)
        return layer

    def update_layer(self, canvas: dict, layer: dict, changes: dict, position: Any = None,
                     activate: bool | None = None, checkpoint: bool = True) -> dict:
        updated = dict(layer)
        for key, value in changes.items():
            if key == "style" and isinstance(value, dict) and isinstance(updated.get("style"), (dict, str)):
                merged = dict(updated["style"]) if isinstance(updated["style"], dict) else {"use": updated["style"]}
                for sk, sv in value.items():
                    if sv is None:
                        merged.pop(sk, None)
                    else:
                        merged[sk] = sv
                updated["style"] = merged
            elif value is None:
                continue
            else:
                updated[key] = value
        if "name" in changes and changes["name"]:
            new_name = slugify(changes["name"], "layer")
            if new_name == "base" or any(l is not layer and l["name"] == new_name for l in canvas["layers"]):
                raise ValueError(f"Layer name '{new_name}' is already taken")
            updated["name"] = new_name
        self._check_layer(canvas, updated)
        index = self._layer_index(canvas, position, layer) if position is not None else None
        if checkpoint:
            self.checkpoint(canvas)
            layer = self.get_layer(canvas, layer["name"])
        old_name = layer["name"]
        layer.clear()
        layer.update(updated)
        if layer["name"] != old_name:
            for el in canvas["elements"]:
                if el.get("layer") == old_name:
                    el["layer"] = layer["name"]
            if canvas.get("active_layer") == old_name:
                canvas["active_layer"] = layer["name"]
        if index is not None:
            canvas["layers"] = [l for l in canvas["layers"] if l is not layer]
            canvas["layers"].insert(index, layer)
        if activate:
            canvas["active_layer"] = layer["name"]
        self.save_canvas(canvas)
        return layer

    def delete_layer(self, canvas: dict, layer: dict, keep_elements: bool) -> list[str]:
        self.checkpoint(canvas)
        layer = self.get_layer(canvas, layer["name"])
        name = layer["name"]
        affected = [e["id"] for e in canvas["elements"] if e.get("layer") == name]
        if keep_elements:
            for el in canvas["elements"]:
                if el.get("layer") == name:
                    el.pop("layer")
        else:
            ids = set(affected)
            canvas["elements"] = [e for e in canvas["elements"] if e["id"] not in ids]
            for e in canvas["elements"]:
                if e.get("clip") in ids:
                    e.pop("clip", None)
            for anim in canvas.get("animations", {}).values():
                anim["tracks"] = [t for t in anim["tracks"] if t["target"] not in ids]
        canvas["layers"] = [l for l in canvas["layers"] if l is not layer]
        if canvas.get("active_layer") == name:
            canvas["active_layer"] = canvas["layers"][-1]["name"] if canvas["layers"] else None
        self.save_canvas(canvas)
        return affected

    def assign_layer(self, canvas: dict, elements: list[dict], layer_name: str | None) -> None:
        self.checkpoint(canvas)
        ids = {e["id"] for e in elements}
        for el in canvas["elements"]:
            if el["id"] in ids:
                if layer_name:
                    el["layer"] = layer_name
                else:
                    el.pop("layer", None)
        self.save_canvas(canvas)


    def animations(self, canvas: dict) -> dict:
        return canvas.setdefault("animations", {})

    def get_animation(self, canvas: dict, name: str) -> tuple[str, dict]:
        anims = self.animations(canvas)
        key = name if name in anims else slugify(name, "anim")
        if key not in anims:
            known = ", ".join(sorted(anims)) or "(none yet - call create_animation)"
            raise ValueError(f"Animation '{name}' not found on canvas '{canvas['id']}'. Animations: {known}")
        return key, anims[key]

    def create_animation(self, canvas: dict, name: str, duration: float, loop: bool, fps: float) -> tuple[str, dict, bool]:
        duration, fps = float(duration), float(fps)
        if not 0.01 <= duration <= 120:
            raise ValueError("duration must be between 0.01 and 120 seconds")
        if not 1 <= fps <= 120:
            raise ValueError("fps must be between 1 and 120")
        key = slugify(name, "anim")
        anims = self.animations(canvas)
        existing = anims.get(key)
        if existing:
            latest = max((k["t"] for tr in existing["tracks"] for k in tr["keyframes"]), default=0.0)
            if latest > duration + 1e-9:
                raise ValueError(f"duration {duration:g}s is shorter than an existing keyframe at {latest:g}s")
        self.checkpoint(canvas)
        if existing:
            existing.update(duration=duration, loop=bool(loop), fps=fps)
        else:
            anims[key] = {"duration": duration, "loop": bool(loop), "fps": fps, "tracks": []}
        self.save_canvas(canvas)
        return key, anims[key], existing is None

    def set_track(self, canvas: dict, anim: dict, target: str, prop: str, keyframes: list[dict],
                  pivot: list[float] | None, checkpoint: bool = True,
                  path: dict | None = None) -> tuple[list[dict], list[str]]:
        from .animation import apply_animation, track_targets
        prop = str(prop).strip()
        if not prop or prop.split(".")[0] in ("id", "type", "group", "clip"):
            raise ValueError(f"'{prop}' cannot be animated")
        elements = track_targets(canvas, target)
        if not elements:
            ids = ", ".join(e["id"] for e in canvas["elements"]) or "(canvas is empty)"
            groups = ", ".join(sorted({e["group"] for e in canvas["elements"] if e.get("group")})) or "(none)"
            raise ValueError(f"Animation target '{target}' not found. Use an element id ({ids}) or "
                             f"'group:<name>' (groups: {groups}).")
        track = {"target": target, "property": prop, "keyframes": keyframes}
        if prop == "motion":
            from .animation import motion_path
            if not isinstance(path, dict):
                raise ValueError('property "motion" needs path {"d": "M 0 0 C ...", "rotate": true} or {"points": [...]}')
            motion_path(path)
            track["path"] = path
        if pivot:
            if len(pivot) != 2:
                raise ValueError("pivot must be [x, y]")
            track["pivot"] = [float(pivot[0]), float(pivot[1])]
        warnings: list[str] = []
        probe = {"tracks": [track]}
        for key in keyframes:
            frame, _ = apply_animation(canvas, probe, key["t"], self.theme.get("colors", {}))
            for el in track_targets(frame, target):
                try:
                    warnings += self._validate(frame, el)
                except Exception as exc:
                    raise ValueError(f"keyframe at {key['t']:g}s ({prop} = {key['value']!r}) cannot be drawn: {exc}") from exc
        if checkpoint:
            self.checkpoint(canvas)
        anim["tracks"] = [t for t in anim["tracks"] if not (t["target"] == target and t["property"] == prop)]
        anim["tracks"].append(track)
        self.save_canvas(canvas)
        return elements, sorted(set(warnings))

    def delete_tracks(self, canvas: dict, anim: dict, target: str | None, prop: str | None) -> int:
        keep = [t for t in anim["tracks"]
                if not ((target is None or t["target"] == target) and (prop is None or t["property"] == prop))]
        removed = len(anim["tracks"]) - len(keep)
        if removed:
            self.checkpoint(canvas)
            anim["tracks"] = keep
            self.save_canvas(canvas)
        return removed

    def delete_animation(self, canvas: dict, key: str) -> None:
        self.checkpoint(canvas)
        self.animations(canvas).pop(key, None)
        self.save_canvas(canvas)


    def set_theme(self, colors: dict | None, styles: dict | None, replace: bool,
                  modes: dict | None = None, mode: str | None = None, numbers: dict | None = None,
                  materials: dict | None = None, environment: dict | None = None,
                  quality: str | None = None, style_preset: str | None = None,
                  apply_preset_tokens: bool = True) -> None:
        from . import profiles
        old = copy.deepcopy(self.theme)
        if replace:
            self.theme = {"colors": {}, "styles": {}}
        if quality is not None or style_preset is not None:
            prof = dict(self.theme.get("profile") or {})
            if style_preset is not None:
                norm_sp = profiles.normalize_style_preset(style_preset)
                if norm_sp:
                    prof["style_preset"] = norm_sp
                    if apply_preset_tokens:
                        sp_data = profiles.STYLE_PRESETS[norm_sp]
                        colors = {**sp_data["colors"], **(colors or {})}
                        numbers = {**sp_data["numbers"], **(numbers or {})}
                        styles = {**sp_data["styles"], **(styles or {})}
                else:
                    prof.pop("style_preset", None)
            if quality is not None:
                norm_q = profiles.normalize_quality(quality)
                if norm_q:
                    prof["quality"] = norm_q
                else:
                    prof.pop("quality", None)
            if prof:
                self.theme["profile"] = prof
            else:
                self.theme.pop("profile", None)
        if environment is not None:
            if not isinstance(environment, dict):
                self.theme = old
                raise ValueError('environment must be an object, e.g. {"env_map": "studio.hdr", "rotation": 45, "intensity": 1.1}')
            if not environment:
                self.theme.pop("environment", None)
            else:
                merged_env = dict(self.theme.get("environment") or {})
                for ek, ev in environment.items():
                    if ev is None:
                        merged_env.pop(ek, None)
                    else:
                        merged_env[ek] = ev
                if merged_env.get("env_map"):
                    ep = Path(str(merged_env["env_map"])).expanduser()
                    if not ep.is_file():
                        self.theme = old
                        raise ValueError(f"environment.env_map file not found: {ep}")
                    merged_env["env_map"] = str(ep.resolve())
                if merged_env:
                    self.theme["environment"] = merged_env
                else:
                    self.theme.pop("environment", None)
        if materials:
            own = self.theme.setdefault("materials", {})
            for key, value in materials.items():
                if value is None:
                    own.pop(key, None)
                elif not isinstance(value, dict):
                    self.theme = old
                    raise ValueError(f"material '{key}' must be a style object, e.g. "
                                     '{"material": "wood", "color": "#5a3a22"} or {"fill": {"type": "shader", ...}}')
                else:
                    own[key] = value
            try:
                from .materials import expand
                for key in materials:
                    if materials[key] is not None:
                        expand(key, self.theme)
            except ValueError:
                self.theme = old
                raise
        theme_numbers = self.theme.setdefault("numbers", {})
        for key, value in (numbers or {}).items():
            if value is None:
                theme_numbers.pop(key, None)
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                self.theme = old
                raise ValueError(f"number token '{key}' must be a number (spacing, radius, size...), got {value!r}")
            else:
                theme_numbers[key] = value
        theme_modes = self.theme.setdefault("modes", {})
        for name, values in (modes or {}).items():
            if values is None:
                theme_modes.pop(name, None)
                continue
            if not isinstance(values, dict):
                self.theme = old
                raise ValueError(f"mode '{name}' must be an object of colour overrides, e.g. {{\"bg\": \"#ffffff\"}}")
            merged = dict(theme_modes.get(name) or {})
            for key, value in values.items():
                if value is None:
                    merged.pop(key, None)
                else:
                    merged[key] = value
            theme_modes[name] = merged
        if mode is not None:
            if mode and mode not in theme_modes:
                self.theme = old
                raise ValueError(f"no mode '{mode}'. Modes: {', '.join(sorted(theme_modes)) or '(none)'} - "
                                 "define it with modes={...} first; mode='' goes back to the base colours")
            self.theme["mode"] = mode or None
        for key, value in (colors or {}).items():
            if value is None:
                self.theme["colors"].pop(key, None)
            else:
                self.theme["colors"][key] = value
        for key, value in (styles or {}).items():
            if value is None:
                self.theme["styles"].pop(key, None)
            elif not isinstance(value, dict):
                self.theme = old
                raise ValueError(f"Theme style '{key}' must be an object")
            else:
                self.theme["styles"][key] = value
        try:
            from .colors import parse_color
            from .render import resolve_style
            for value in self.theme["colors"].values():
                parse_color(value, self.theme["colors"])
            for name, values in self.theme.get("modes", {}).items():
                palette = {**self.theme["colors"], **values}
                for key, value in values.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        continue
                    try:
                        parse_color(value, palette)
                    except ValueError as exc:
                        raise ValueError(f"mode '{name}', colour '{key}': {exc}") from exc
            probe = {"id": "theme_probe", "width": 16, "height": 16, "background": None, "elements": []}
            for name in self.theme["styles"]:
                st = resolve_style(name, self.theme)
                shape_style = {k: v for k, v in st.items() if k not in ("font", "weight", "size", "letter_spacing",
                                                                       "line_height", "uppercase", "italic")}
                el = {"id": "p", "type": "rect", "x": 2, "y": 2, "width": 12, "height": 12, "style": shape_style}
                probe["elements"] = [el]
                Renderer(probe, self.theme, self.fonts, lookup=self.get).render()
                if st.get("font"):
                    self.fonts.resolve(st["font"], 400)
        except Exception as exc:
            self.theme = old
            raise ValueError(f"Theme rejected: {exc}") from exc
        self.save_theme()
