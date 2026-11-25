"""Zero-dependency live local preview studio (127.0.0.1 HTTP + Server-Sent Events).

Starts a lightweight background HTTP server that pushes instant reload events whenever the agent edits a
canvas or theme, letting the user watch designs evolve live, switch canvases/modes/backdrops and inspect
element bounds in their browser. Localhost-only, stdlib-only.
"""

from __future__ import annotations

import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from PIL import Image as PILImage

from .render import backdrop

_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>uiforge-mcp · Live Preview</title>
<style>
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#0d0f14;color:#e5e7eb;font:13px/1.4 system-ui,-apple-system,sans-serif;overflow:hidden}
.bar{height:44px;padding:0 14px;display:flex;align-items:center;gap:10px;background:#141720;border-bottom:1px solid #242938}
.brand{font-weight:700;letter-spacing:.02em;color:#a78bfa;margin-right:6px}
select,button{background:#1d2230;color:#e5e7eb;border:1px solid #2d3448;border-radius:6px;padding:5px 9px;font:inherit;cursor:pointer}
select:hover,button:hover{border-color:#7c5cff}
button.on{background:#7c5cff;border-color:#7c5cff;color:#fff}
.dot{width:8px;height:8px;border-radius:50%;background:#22c55e;margin-left:auto}
.dot.off{background:#ef4444}
.meta{color:#9ca3af;font-size:12px}
.stage{height:calc(100% - 44px);display:grid;place-items:center;overflow:auto;padding:24px;position:relative}
.wrap{position:relative;box-shadow:0 20px 60px rgba(0,0,0,.55);border:1px solid #262b3b;line-height:0}
.wrap img{display:block;max-width:92vw;max-height:82vh;object-fit:contain}
.tip{position:fixed;bottom:14px;left:16px;background:#141720dd;border:1px solid #2a3042;border-radius:6px;padding:5px 10px;font-size:12px;color:#cbd5e1}
</style></head><body>
<div class="bar">
  <span class="brand">uiforge-mcp</span>
  <select id="cid"></select>
  <select id="bg"><option value="checker">Checker</option><option value="dark">Dark</option><option value="light">Light</option><option value="game">Game</option></select>
  <button id="ids" type="button">IDs</button>
  <button id="guides" type="button">Guides</button>
  <span class="meta" id="info"></span>
  <span class="dot" id="dot" title="SSE connection"></span>
</div>
<div class="stage"><div class="wrap"><img id="pic" alt="Live canvas"/></div></div>
<div class="tip" id="tip">Live reload active · hover image to inspect coordinates</div>
<script>
const cid = document.getElementById('cid'), bg = document.getElementById('bg'), pic = document.getElementById('pic');
const idsBtn = document.getElementById('ids'), guidesBtn = document.getElementById('guides');
const info = document.getElementById('info'), dot = document.getElementById('dot'), tip = document.getElementById('tip');
let showIds = false, showGuides = false, rev = 0, dims = [0, 0];

async function refreshList(pick) {
  const r = await fetch('/api/state');
  const s = await r.json();
  const cur = pick || cid.value || s.active || (s.canvases[0] && s.canvases[0].id) || '';
  cid.innerHTML = s.canvases.map(c => `<option value="${c.id}">${c.id} (${c.width}x${c.height})</option>`).join('');
  if (cur && s.canvases.some(c => c.id === cur)) cid.value = cur;
  const sel = s.canvases.find(c => c.id === cid.value);
  if (sel) { dims = [sel.width, sel.height]; info.textContent = `${sel.width}x${sel.height} · ${sel.elements} elements · rev ${s.rev}`; }
  loadPic();
}
function loadPic() {
  if (!cid.value) return;
  rev++;
  const q = new URLSearchParams({bg: bg.value, ids: showIds ? '1' : '0', guides: showGuides ? '1' : '0', r: String(rev)});
  pic.src = `/api/render/${encodeURIComponent(cid.value)}?${q}`;
}
cid.onchange = () => refreshList(cid.value);
bg.onchange = loadPic;
idsBtn.onclick = () => { showIds = !showIds; idsBtn.classList.toggle('on', showIds); loadPic(); };
guidesBtn.onclick = () => { showGuides = !showGuides; guidesBtn.classList.toggle('on', showGuides); loadPic(); };
pic.onmousemove = e => {
  if (!dims[0]) return;
  const r = pic.getBoundingClientRect();
  const x = Math.round((e.clientX - r.left) / r.width * dims[0]);
  const y = Math.round((e.clientY - r.top) / r.height * dims[1]);
  tip.textContent = `x: ${x}, y: ${y} (canvas ${dims[0]}x${dims[1]})`;
};
const es = new EventSource('/events');
es.onopen = () => dot.classList.remove('off');
es.onerror = () => dot.classList.add('off');
es.onmessage = e => { const d = JSON.parse(e.data); refreshList(d.canvas || cid.value); };
refreshList();
</script></body></html>
"""


class LiveStudio:
    """Localhost-only HTTP + SSE preview server attached to a Store."""

    def __init__(self, store_getter, port: int = 0) -> None:
        self._get_store = store_getter
        self._cond = threading.Condition()
        self._seq = 0
        self._last_canvas: str | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = int(port)

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def notify(self, canvas_id: str | None = None) -> None:
        with self._cond:
            self._seq += 1
            if canvas_id:
                self._last_canvas = canvas_id
            self._cond.notify_all()

    def start(self, canvas_id: str | None = None) -> dict[str, Any]:
        st = self._get_store()
        st.on_change(self.notify)
        if canvas_id:
            self._last_canvas = canvas_id
        if self._server is not None:
            self.notify(canvas_id)
            return {"running": True, "url": self.url, "active": self._last_canvas}
        studio = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/":
                    data = _HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if path == "/api/state":
                    s = studio._get_store()
                    s.on_change(studio.notify)
                    items = [{"id": c["id"], "width": c["width"], "height": c["height"],
                              "elements": len(c.get("elements", []))} for c in s.canvases.values()]
                    payload = json.dumps({"rev": s.rev, "active": studio._last_canvas, "canvases": items}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if path.startswith("/api/render/"):
                    cid = path[len("/api/render/"):]
                    qs = parse_qs(parsed.query)
                    bg = qs.get("bg", ["checker"])[0]
                    show_ids = qs.get("ids", ["0"])[0] == "1"
                    show_guides = qs.get("guides", ["0"])[0] == "1"
                    s = studio._get_store()
                    try:
                        c = s.get(cid)
                        scale = min(1.0, 1280 / max(1, c["width"], c["height"]))
                        r = s.renderer(c, scale)
                        img = r.render()
                        view = PILImage.alpha_composite(backdrop(img.size, bg, s.theme.get("colors", {})), img)
                        if show_guides:
                            from .viewing import draw_guides
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
                                except Exception:
                                    continue
                                col = palette[i % len(palette)]
                                draw.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale], outline=col, width=1)
                                draw.text((x0 * scale + 2, y0 * scale + 2), el["id"], fill=col, font=font)
                        buf = io.BytesIO()
                        view.convert("RGB").save(buf, format="PNG")
                        body = buf.getvalue()
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    except Exception as exc:
                        msg = str(exc).encode("utf-8")
                        self.send_response(404)
                        self.send_header("Content-Type", "text/plain; charset=utf-8")
                        self.send_header("Content-Length", str(len(msg)))
                        self.end_headers()
                        self.wfile.write(msg)
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
                                studio._cond.wait(timeout=15.0)
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
                self.send_response(404)
                self.end_headers()

        srv = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        srv.daemon_threads = True
        self.port = srv.server_address[1]
        self._server = srv
        self._thread = threading.Thread(target=srv.serve_forever, daemon=True, name="uiforge-live")
        self._thread.start()
        return {"running": True, "url": self.url, "active": self._last_canvas}

    def stop(self) -> dict[str, Any]:
        srv = self._server
        self._server = None
        with self._cond:
            self._cond.notify_all()
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        return {"running": False}
