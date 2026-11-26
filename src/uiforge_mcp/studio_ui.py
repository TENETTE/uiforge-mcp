"""Standalone Human Mode & Combined Mode Studio UI server for UIForge.

Zero third-party web server dependencies (Python stdlib ThreadingHTTPServer + SSE) and zero runtime
dependency on the ``mcp`` package. Every user action executes through ``core.invoke_operation`` and
``core.render_view`` — the exact same engine core used by MCP Mode.
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__

_ASSETS_DIR = Path(__file__).parent / "ui_assets"
_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"

_SWATCH_CACHE: dict[str, bytes] = {}
_SWATCH_LOCK = threading.Lock()

_MATERIAL_GROUPS: dict[str, list[str]] = {
    "Metals": ["gold", "hammered_gold", "silver", "chrome", "bronze", "copper", "steel", "iron", "radial_metal", "rust"],
    "Stone & Gems": ["stone", "runic_stone", "marble", "obsidian", "jade", "gem", "ruby", "emerald", "lava", "ice"],
    "Craft & Organic": ["wood", "leather", "paper", "aged_parchment", "fabric", "carbon_twill", "wax_seal", "enamel"],
    "Glass & Sci-Fi": ["glass", "liquid_glass", "hologram", "energy_shield", "foil_holographic", "neon", "plastic", "candy_gloss", "clay_3d", "rubber", "jelly"],
}


def _render_material_swatch(mat_name: str, st) -> bytes:
    """Render and cache a genuine 72x72 Cook-Torrance PBR preview tile for the Material Forge gallery."""
    with _SWATCH_LOCK:
        cached = _SWATCH_CACHE.get(mat_name)
    if cached is not None:
        return cached
    from .render import Renderer
    mini = {
        "id": f"swatch_{mat_name}",
        "width": 72,
        "height": 72,
        "background": "#101218",
        "elements": [{
            "id": "tile",
            "type": "rect",
            "x": 6,
            "y": 6,
            "width": 60,
            "height": 60,
            "radius": 14,
            "style": {"material": mat_name},
        }],
    }
    img = Renderer(mini, st.theme, st.fonts).render()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    blob = buf.getvalue()
    with _SWATCH_LOCK:
        _SWATCH_CACHE[mat_name] = blob
    return blob


def _find_chromium_app_browser() -> str | None:
    """Find a local Chromium-based browser that supports native frameless ``--app=<url>`` windows."""
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("google-chrome"),
    ]
    if sys.platform == "win32":
        candidates += [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    for c in candidates:
        if c and Path(c).is_file():
            return str(c)
    return None


def launch_ui_window(url: str, app_window: bool = False) -> str:
    """Open the Studio UI in an optional pywebview/Chromium frameless app window or default browser."""
    if app_window:
        try:
            import webview  # type: ignore
            webview.create_window("UIForge Studio", url, width=1440, height=900, min_size=(900, 620))
            webview.start()
            return "pywebview"
        except ImportError:
            pass
        browser = _find_chromium_app_browser()
        if browser:
            subprocess.Popen([browser, f"--app={url}", "--window-size=1440,900"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "chromium-app"
    webbrowser.open(url)
    return "browser"


class _QuietHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class StudioServer:
    """Localhost-only full Studio HTTP + SSE server supporting Human Mode and Combined Mode."""

    def __init__(self, store_getter, host: str = "127.0.0.1", port: int = 0, mode: str = "ui") -> None:
        self._get_store = store_getter
        self.host = host
        self.port = int(port)
        self.mode = mode
        self._cond = threading.Condition()
        self._seq = 0
        self._last_canvas: str | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._watcher: threading.Thread | None = None
        self._stop_evt = threading.Event()

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def notify(self, canvas_id: str | None = None) -> None:
        with self._cond:
            self._seq += 1
            if canvas_id:
                self._last_canvas = canvas_id
            self._cond.notify_all()

    def _watch_disk(self) -> None:
        """Poll workspace files every 0.6s so separate-process Combined Mode reflects external edits live."""
        while not self._stop_evt.wait(0.6):
            try:
                st = self._get_store()
                st.sync_from_disk()
            except Exception:
                pass

    def start(self, canvas_id: str | None = None) -> dict[str, Any]:
        from . import cli, core, frames, icons, materials, profiles
        from . import server as srv

        core.set_mode(self.mode)
        st = self._get_store()
        st.on_change(self.notify)
        if canvas_id:
            self._last_canvas = canvas_id
        if self._server is not None:
            self.notify(canvas_id)
            return {"running": True, "url": self.url, "mode": self.mode}

        studio = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _send(self, code: int, ctype: str, body: bytes, cache: str = "no-store") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", cache)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_json(self, code: int, obj: Any) -> None:
                self._send(code, "application/json; charset=utf-8",
                           json.dumps(obj, ensure_ascii=False).encode("utf-8"))

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0 or length > 25_000_000:
                    return {}
                raw = self.rfile.read(length)
                return json.loads(raw.decode("utf-8"))

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/":
                    html_file = _ASSETS_DIR / "index.html"
                    self._send(200, "text/html; charset=utf-8", html_file.read_bytes())
                    return
                if path == "/assets/studio.css":
                    self._send(200, "text/css; charset=utf-8", (_ASSETS_DIR / "studio.css").read_bytes())
                    return
                if path == "/assets/studio.js":
                    self._send(200, "application/javascript; charset=utf-8", (_ASSETS_DIR / "studio.js").read_bytes())
                    return
                if path == "/favicon.ico" or path.startswith("/assets/brand/"):
                    fname = "emblem.png" if path == "/favicon.ico" else path[len("/assets/brand/"):]
                    if fname in ("emblem.png", "starter_tactical.png", "starter_rpg.png", "starter_saas.png"):
                        bf = _ASSETS_DIR / "brand" / fname
                        if bf.is_file():
                            self._send(200, "image/png", bf.read_bytes(), cache="public, max-age=86400")
                            return
                    self._send(404, "text/plain", b"not found")
                    return
                if path == "/fonts/inter.ttf":
                    f = _FONTS_DIR / "inter" / "Inter[opsz,wght].ttf"
                    if f.is_file():
                        self._send(200, "font/ttf", f.read_bytes(), cache="public, max-age=86400")
                        return
                if path == "/fonts/mono.ttf":
                    f = _FONTS_DIR / "jetbrainsmono" / "JetBrainsMono[wght].ttf"
                    if f.is_file():
                        self._send(200, "font/ttf", f.read_bytes(), cache="public, max-age=86400")
                        return

                if path == "/api/bootstrap":
                    s = studio._get_store()
                    s.on_change(studio.notify)
                    s.sync_from_disk()
                    icon_catalog = [
                        {"name": n, "d": icons._RAW_ICONS[n][0], "mode": icons._RAW_ICONS[n][1],
                         "tags": icons._RAW_ICONS[n][2].split(",")}
                        for n in icons.ICON_NAMES
                    ]
                    self._send_json(200, {
                        "version": __version__,
                        "mode": studio.mode,
                        "mcp_available": bool(srv.MCP_AVAILABLE),
                        "workspace": str(s.workspace),
                        "exports_dir": str(s.exports_dir),
                        "rev": s.rev,
                        "active": studio._last_canvas,
                        "canvases": [
                            {"id": c["id"], "name": c.get("name", c["id"]), "width": c["width"],
                             "height": c["height"], "elements": len(c.get("elements", []))}
                            for c in s.canvases.values()
                        ],
                        "theme": s.theme,
                        "doctor": cli.doctor_report(),
                        "quality_levels": {k: {"label": v["label"], "summary": v["summary"]}
                                           for k, v in profiles.QUALITY_LEVELS.items()},
                        "style_presets": {k: {"label": v["label"], "default_quality": v["default_quality"],
                                              "frame_preset": v["frame_preset"], "colors": v["colors"]}
                                          for k, v in profiles.STYLE_PRESETS.items()},
                        "frame_presets": list(frames.FRAME_PRESETS),
                        "materials": {"all": list(materials.NAMES), "groups": _MATERIAL_GROUPS,
                                      "custom": sorted((s.theme.get("materials") or {}).keys())},
                        "icons": icon_catalog,
                        "operations": core.list_operations(),
                        "activity": core.activity_log.list(60),
                        "ide_clients": list(cli.CLIENTS),
                    })
                    return

                if path.startswith("/api/canvas/"):
                    cid = unquote(path[len("/api/canvas/"):])
                    s = studio._get_store()
                    s.sync_from_disk()
                    try:
                        c = s.get(cid)
                        _, _, el_rows = core.render_view(s, cid, max_dim=480.0)
                        self._send_json(200, {
                            "id": c["id"],
                            "name": c.get("name", c["id"]),
                            "width": c["width"],
                            "height": c["height"],
                            "background": c.get("background"),
                            "profile": profiles.resolve_profile(s.theme, c),
                            "layers": [{"name": ly["name"], "visible": bool(ly.get("visible", True)),
                                        "blend": ly.get("blend", "normal"), "clip": bool(ly.get("clip", False))}
                                       for ly in (c.get("layers") or [])],
                            "states": sorted((c.get("states") or {}).keys()),
                            "data": dict(c.get("data") or {}),
                            "bindings": list(c.get("bindings") or []),
                            "animations": [{"name": k, "duration": float(v.get("duration", 1.0)),
                                            "loop": bool(v.get("loop")), "tracks": len(v.get("tracks") or [])}
                                           for k, v in sorted((c.get("animations") or {}).items())],
                            "versions": s.list_versions(c),
                            "elements": el_rows,
                            "raw_elements": {e["id"]: e for e in c.get("elements", [])},
                        })
                    except Exception as exc:
                        self._send_json(404, {"error": str(exc)})
                    return

                if path.startswith("/api/render/"):
                    cid = unquote(path[len("/api/render/"):])
                    qs = parse_qs(parsed.query)
                    bg = qs.get("bg", ["checker"])[0]
                    show_ids = qs.get("ids", ["0"])[0] == "1"
                    show_guides = qs.get("guides", ["0"])[0] == "1"
                    state_name = qs.get("state", [""])[0] or None
                    hide_raw = qs.get("hide", [""])[0]
                    hide_layers = [h for h in hide_raw.split(",") if h] if hide_raw else None
                    data_raw = qs.get("data", [""])[0]
                    data_override = None
                    if data_raw:
                        try:
                            data_override = json.loads(data_raw)
                        except ValueError:
                            data_override = None
                    anim_name = qs.get("anim", [""])[0] or None
                    anim_t = float(qs.get("t", ["0"])[0] or 0.0)
                    sim_mode = qs.get("sim", [""])[0] or None
                    lang_mode = qs.get("lang", [""])[0] or None
                    s = studio._get_store()
                    s.sync_from_disk()
                    try:
                        view, _, _ = core.render_view(
                            s, cid, background=bg, show_ids=show_ids, show_guides=show_guides,
                            state=state_name, data=data_override, hide_layers=hide_layers,
                            animation=anim_name, t=anim_t, simulate=sim_mode, language=lang_mode,
                            max_dim=1440.0,
                        )
                        buf = io.BytesIO()
                        view.convert("RGB").save(buf, format="PNG")
                        self._send(200, "image/png", buf.getvalue())
                    except Exception as exc:
                        self._send(404, "text/plain; charset=utf-8", str(exc).encode("utf-8"))
                    return

                if path.startswith("/api/swatch/"):
                    mname = unquote(path[len("/api/swatch/"):])
                    s = studio._get_store()
                    is_custom = mname in (s.theme.get("materials") or {})
                    if mname not in materials.NAMES and not is_custom:
                        self._send(404, "text/plain", b"unknown material")
                        return
                    try:
                        if is_custom:
                            _SWATCH_CACHE.pop(mname, None)
                        blob = _render_material_swatch(mname, s)
                        self._send(200, "image/png", blob, cache=("no-store" if is_custom else "public, max-age=3600"))
                    except Exception as exc:
                        self._send(500, "text/plain", str(exc).encode("utf-8"))
                    return

                if path == "/api/activity":
                    self._send_json(200, {"activity": core.activity_log.list(80)})
                    return

                if path.startswith("/api/ide_config/"):
                    cl = unquote(path[len("/api/ide_config/"):])
                    try:
                        spec = cli.client_config(cl)
                        self._send_json(200, spec)
                    except Exception as exc:
                        self._send_json(400, {"error": str(exc)})
                    return

                if path == "/api/export_preview":
                    qs = parse_qs(parsed.query)
                    target = qs.get("path", [""])[0]
                    s = studio._get_store()
                    try:
                        raw_p = Path(target)
                        p = (s.workspace / raw_p).resolve() if not raw_p.is_absolute() else raw_p.resolve()
                        p.relative_to(s.exports_dir.resolve())
                        if not p.is_file():
                            raise FileNotFoundError("File not found")
                        ext = p.suffix.lower()
                        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                            ctype = f"image/{'jpeg' if ext in ('.jpg', '.jpeg') else ext[1:]}"
                            self._send(200, ctype, p.read_bytes())
                        elif ext == ".html":
                            self._send(200, "text/html; charset=utf-8", p.read_bytes())
                        elif ext == ".svg":
                            self._send(200, "image/svg+xml; charset=utf-8", p.read_bytes())
                        else:
                            txt = p.read_text(encoding="utf-8", errors="replace")[:120_000]
                            self._send_json(200, {"file": p.name, "path": str(p), "text": txt})
                    except Exception as exc:
                        self._send_json(403, {"error": str(exc)})
                    return

                if path == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    seen = studio._seq
                    try:
                        while studio.running:
                            with studio._cond:
                                studio._cond.wait(timeout=12.0)
                                cur = studio._seq
                                active = studio._last_canvas
                            if cur != seen:
                                seen = cur
                                chunk = f"data: {json.dumps({'seq': cur, 'canvas': active})}\n\n".encode("utf-8")
                            else:
                                chunk = b": keepalive\n\n"
                            self.wfile.write(chunk)
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    return

                self._send(404, "text/plain", b"Not found")

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path
                try:
                    body = self._read_json()
                except Exception as exc:
                    self._send_json(400, {"ok": False, "error": f"Invalid JSON: {exc}"})
                    return

                if path == "/api/op":
                    op = str(body.get("op") or "").strip()
                    args = body.get("args") if isinstance(body.get("args"), dict) else {}
                    res = core.invoke_operation(op, args, source="ui")
                    self._send_json(200 if res["ok"] else 400, res)
                    return

                if path == "/api/import_screenshot_upload":
                    b64 = str(body.get("image_base64") or "")
                    fname = str(body.get("filename") or "screenshot.png")
                    cname = body.get("canvas") or None
                    if "," in b64:
                        b64 = b64.split(",", 1)[1]
                    try:
                        raw = base64.b64decode(b64)
                        s = studio._get_store()
                        up_dir = s.workspace / "imports"
                        up_dir.mkdir(parents=True, exist_ok=True)
                        safe_name = Path(fname).name or "screenshot.png"
                        dst = up_dir / f"{int(time.time())}_{safe_name}"
                        dst.write_bytes(raw)
                        res = core.invoke_operation("import_screenshot", {"path": str(dst), "canvas": cname}, source="ui")
                        self._send_json(200 if res["ok"] else 400, res)
                    except Exception as exc:
                        self._send_json(400, {"ok": False, "error": str(exc)})
                    return

                if path == "/api/gpu":
                    pref = str(body.get("backend") or "auto").strip().lower()
                    if pref not in ("auto", "cuda", "wgpu", "cpu"):
                        self._send_json(400, {"ok": False, "error": "backend must be auto, cuda, wgpu or cpu"})
                        return
                    os.environ["UIFORGE_MCP_GPU"] = pref
                    from . import gpu
                    gpu._cupy.cache_clear()
                    core.activity_log.record("set_gpu_backend", source="ui", detail=pref)
                    self._send_json(200, {"ok": True, "doctor": cli.doctor_report()})
                    return

                if path == "/api/ide_setup":
                    cl = str(body.get("client") or "").strip().lower()
                    try:
                        spec = cli.client_config(cl)
                        written = str(cli.write_client_config(spec)) if spec.get("path") else None
                        core.activity_log.record("setup_ide", source="ui", detail=f"{cl} -> {written or 'http'}")
                        self._send_json(200, {"ok": True, "written": written, "spec": spec})
                    except Exception as exc:
                        self._send_json(400, {"ok": False, "error": str(exc)})
                    return

                self._send_json(404, {"ok": False, "error": "Unknown endpoint"})

        srv_http = _QuietHTTPServer((self.host, self.port), Handler)
        srv_http.daemon_threads = True
        self.port = srv_http.server_address[1]
        self._server = srv_http
        self._stop_evt.clear()
        self._thread = threading.Thread(target=srv_http.serve_forever, daemon=True, name="uiforge-studio")
        self._thread.start()
        self._watcher = threading.Thread(target=self._watch_disk, daemon=True, name="uiforge-disk-sync")
        self._watcher.start()
        return {"running": True, "url": self.url, "mode": self.mode, "active": self._last_canvas}

    def stop(self) -> dict[str, Any]:
        self._stop_evt.set()
        srv_http = self._server
        self._server = None
        with self._cond:
            self._cond.notify_all()
        if srv_http is not None:
            srv_http.shutdown()
            srv_http.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._watcher is not None:
            self._watcher.join(timeout=1.5)
            self._watcher = None
        return {"running": False}
