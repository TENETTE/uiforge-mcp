"""MCP-independent shared engine core for UIForge.

Both the MCP server (MCP Mode), the standalone Studio web/desktop interface (Human Mode),
and simultaneous AI + human sessions (Combined Mode) execute operations through this single
core facade so behavior, quality, rendering and export outputs are 100% identical.
"""

from __future__ import annotations

import base64
import collections
import io
import logging
import threading
import time
from typing import Any

from PIL import Image as PILImage

log = logging.getLogger("uiforge_mcp")

_MODE_LOCK = threading.Lock()
_ACTIVE_MODE: str = "mcp"  # "mcp" | "ui" | "combined"


def get_mode() -> str:
    with _MODE_LOCK:
        return _ACTIVE_MODE


def set_mode(mode: str) -> str:
    global _ACTIVE_MODE
    m = str(mode or "mcp").strip().lower()
    if m not in ("mcp", "ui", "combined"):
        raise ValueError("mode must be 'mcp', 'ui' or 'combined'")
    with _MODE_LOCK:
        _ACTIVE_MODE = m
    return m


class ActivityLog:
    """Thread-safe ring buffer of recent engine operations (MCP + Human UI) for live inspection."""

    def __init__(self, maxlen: int = 200) -> None:
        self._lock = threading.Lock()
        self._entries: collections.deque[dict[str, Any]] = collections.deque(maxlen=maxlen)
        self._seq = 0

    def record(self, operation: str, source: str = "mcp", status: str = "ok",
               duration_ms: float = 0.0, detail: str = "", canvas: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "ts": time.strftime("%H:%M:%S"),
                "operation": operation,
                "source": source,
                "status": status,
                "duration_ms": round(duration_ms, 1),
                "canvas": canvas,
                "detail": detail[:240] if detail else "",
            }
            self._entries.append(entry)
            return entry

    def list(self, limit: int = 60) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._entries)
        return list(reversed(items[-max(1, limit):]))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


activity_log = ActivityLog()


def canvas_element_rows(st, canvas: dict[str, Any], language: str | None = None) -> list[dict[str, Any]]:
    """Compute element metadata & bounding boxes without rasterising any pixels (used by /api/canvas & render_view)."""
    r1 = st.renderer(canvas, 1.0, language=language)
    el_rows: list[dict[str, Any]] = []
    for el in canvas.get("elements", []):
        if not el.get("visible", True):
            continue
        try:
            x0, y0, x1, y1 = r1.element_box(el)
            box = [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)]
        except ValueError:
            box = [0.0, 0.0, 0.0, 0.0]
        row: dict[str, Any] = {"id": el["id"], "type": el["type"], "bbox_xywh": box}
        for key in ("layer", "group", "note", "text", "label", "bind"):
            if el.get(key) is not None:
                row[key] = el[key]
        if isinstance(el.get("style"), dict):
            if "material" in el["style"]:
                row["material"] = el["style"]["material"]
            if "fill" in el["style"] and isinstance(el["style"]["fill"], str):
                row["fill"] = el["style"]["fill"]
        el_rows.append(row)
    return el_rows


def render_view(st, canvas_id: str, *, background: str = "checker",
                show_ids: bool = False, show_guides: bool = False, state: str | None = None,
                data: dict[str, Any] | None = None, hide_layers: list[str] | None = None,
                animation: str | None = None, t: float | None = None,
                simulate: str | None = None, language: str | None = None,
                max_dim: float = 1280.0) -> tuple[PILImage.Image, dict[str, Any], list[dict[str, Any]]]:
    """Single source of truth for rendering a canvas view with optional state, bindings, animation,
    accessibility vision simulation, pseudo-localization & overlays.

    Used identically by MCP App studio, Live Preview SSE, and the standalone Human Studio UI.
    """
    from .animation import apply_animation
    from .binding import apply_bindings
    from .render import apply_state, backdrop
    from .viewing import SIMULATIONS, draw_guides, simulate as sim_vision

    base_c = st.get(canvas_id)
    c = base_c
    if state and state in (c.get("states") or {}):
        c = apply_state(c, state)
    if data:
        c = apply_bindings(c, data)
    if animation and animation in (c.get("animations") or {}):
        c = apply_animation(c, c["animations"][animation], float(t or 0.0))
    if hide_layers:
        hidden = set(hide_layers)
        c = dict(c, layers=[
            dict(ly, visible=False) if ly.get("name") in hidden else ly
            for ly in (c.get("layers") or [])
        ])

    el_rows = canvas_element_rows(st, c, language=language)

    scale = min(1.0, float(max_dim) / max(1, c["width"], c["height"]))
    r = st.renderer(c, scale, language=language)
    img = r.render()
    view = PILImage.alpha_composite(backdrop(img.size, background, st.theme.get("colors", {})), img)
    if simulate and simulate.lower() in SIMULATIONS:
        view = sim_vision(view, simulate.lower())
    if show_guides:
        draw_guides(view, ["center", "thirds", "safe"], c, scale, (0.0, 0.0))
    if show_ids:
        from PIL import ImageDraw
        from .server import _label_font
        draw = ImageDraw.Draw(view)
        font = _label_font(12)
        palette = ["#ff4d6d", "#4dd2ff", "#ffd24d", "#7dff7a", "#d59bff", "#ff9d4d"]
        for i, el in enumerate(r.canvas["elements"]):
            if not el.get("visible", True):
                continue
            try:
                x0, y0, x1, y1 = r.element_box(el)
            except ValueError:
                continue
            col = palette[i % len(palette)]
            draw.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale], outline=col, width=1)
            draw.text((x0 * scale + 2, y0 * scale + 2), el["id"], fill=col, font=font)
    return view, base_c, el_rows


def image_to_data_uri(img: PILImage.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def invoke_operation(name: str, args: dict[str, Any] | None = None, source: str = "ui") -> dict[str, Any]:
    """Execute any registered UIForge engine operation identically to an MCP tool call.

    Returns ``{"ok": True, "result": ...}`` or ``{"ok": False, "error": "..."}``.
    Works identically whether the ``mcp`` package is installed or not.
    """
    from . import server as srv

    st = srv.store()
    st.sync_from_disk()
    entry = srv._ALL_TOOLS.get(name)
    if entry is None:
        err = f"Unknown operation '{name}'"
        activity_log.record(name, source=source, status="error", detail=err)
        return {"ok": False, "error": err}

    call_args = dict(args or {})
    canvas_hint = call_args.get("canvas") if isinstance(call_args.get("canvas"), str) else None
    t0 = time.perf_counter()
    try:
        raw = entry["fn"](**call_args)
        dur = (time.perf_counter() - t0) * 1000.0
        result = _normalize_result(raw)
        if not canvas_hint and isinstance(result, dict):
            canvas_hint = result.get("canvas") or result.get("id")
        activity_log.record(name, source=source, status="ok", duration_ms=dur,
                            canvas=canvas_hint if isinstance(canvas_hint, str) else None)
        return {"ok": True, "result": result, "duration_ms": round(dur, 1)}
    except Exception as exc:
        dur = (time.perf_counter() - t0) * 1000.0
        msg = str(exc)
        activity_log.record(name, source=source, status="error", duration_ms=dur,
                            detail=msg, canvas=canvas_hint)
        return {"ok": False, "error": msg, "duration_ms": round(dur, 1)}


def _normalize_result(raw: Any) -> Any:
    """Turn MCP tool return values (dict, Image, list of [json, Image]) into JSON-friendly objects."""
    if isinstance(raw, (dict, int, float, bool)) or raw is None:
        return raw
    if isinstance(raw, str):
        return raw
    if hasattr(raw, "data") and isinstance(getattr(raw, "data", None), (bytes, bytearray)):
        fmt = getattr(raw, "format", "png") or "png"
        return {"image_data_uri": f"data:image/{fmt};base64," + base64.b64encode(bytes(raw.data)).decode("ascii")}
    if isinstance(raw, list):
        items = [_normalize_result(item) for item in raw]
        return items
    return str(raw)


def list_operations() -> list[dict[str, Any]]:
    """Return the complete catalog of UIForge engine operations grouped by category."""
    from . import server as srv

    cats = {
        "canvas": ("create_canvas", "list_canvases", "get_canvas", "update_canvas", "duplicate_canvas",
                   "delete_canvas", "fit_canvas", "resize_canvas", "canvas_version", "import_screenshot"),
        "layers": ("create_layer", "update_layer", "delete_layer", "set_layer"),
        "shapes": ("add_rect", "add_ellipse", "add_line", "add_polygon", "add_path", "add_arc",
                   "add_ticks", "add_text", "add_image", "add_instance", "add_svg", "add_frame", "add_icon"),
        "widgets": ("add_button", "add_progress_bar", "add_stack", "add_grid", "add_split",
                    "add_gauge", "add_slot", "add_tabs", "add_stat_card",
                    "add_input", "add_scroll", "add_slider", "add_toggle", "add_dropdown"),
        "edit": ("update_element", "delete_elements", "duplicate_element", "move_elements",
                 "reorder_element", "align_elements", "arrange_elements", "boolean_elements",
                 "path_ops", "restyle", "find_elements", "scatter", "copy_elements", "batch",
                 "undo", "redo", "vectorize_image"),
        "theme": ("set_theme", "get_theme", "make_palette", "make_variations", "list_fonts",
                  "measure_text", "set_strings", "get_strings", "generate_from_template"),
        "interactive": ("set_pin", "set_state", "delete_state", "set_binding", "set_interaction", "set_link"),
        "animation": ("create_animation", "set_keyframes", "delete_keyframes", "get_animations",
                      "delete_animation", "preview_animation", "export_animation"),
        "inspect": ("preview", "preview_resolutions", "preview_nine_slice", "contact_sheet",
                    "review_canvas", "qa_screen", "inspect_pixels", "view_image", "guide"),
        "export": ("export_png", "export_svg", "export_pdf", "export_web", "export_react",
                   "export_asset", "export_pbr_maps", "export_layers", "export_psd", "export_atlas",
                   "export_bitmap_font", "export_spec", "export_theme", "export_prototype",
                   "export_screen", "export_project", "write_engine_helpers"),
    }
    by_cat = {op: cat for cat, ops in cats.items() for op in ops}
    out = []
    for name, entry in sorted(srv._ALL_TOOLS.items()):
        if (entry.get("meta") or {}).get("ui", {}).get("visibility") == ["app"]:
            continue
        doc = (entry.get("doc") or "").strip().splitlines()[0] if entry.get("doc") else ""
        out.append({
            "name": name,
            "category": by_cat.get(name, "other"),
            "summary": doc,
        })
    return out
