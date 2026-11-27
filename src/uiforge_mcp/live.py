"""Zero-dependency two-way Live Preview Studio v2 (127.0.0.1 HTTP + Server-Sent Events).

Starts a lightweight background HTTP server that pushes instant reload events whenever the agent edits a
canvas or theme, letting the user watch designs evolve live, inspect clicked elements, toggle layers,
preview hover/pressed states, scrub live set_binding variables via sliders, and play/scrub animations
in their browser. Localhost-only, stdlib-only.
"""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>uiforge-mcp · Live Studio v2</title>
<style>
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#0d0f14;color:#e5e7eb;font:13px/1.4 system-ui,-apple-system,sans-serif;overflow:hidden}
.bar{height:44px;padding:0 14px;display:flex;align-items:center;gap:8px;background:#141720;border-bottom:1px solid #242938}
.brand{font-weight:700;letter-spacing:.02em;color:#a78bfa;margin-right:4px}
select,button,input[type=text]{background:#1d2230;color:#e5e7eb;border:1px solid #2d3448;border-radius:6px;padding:4px 9px;font:inherit}
select,button{cursor:pointer}
select:hover,button:hover{border-color:#7c5cff}
button.on{background:#7c5cff;border-color:#7c5cff;color:#fff}
.dot{width:8px;height:8px;border-radius:50%;background:#22c55e;margin-left:auto}
.dot.off{background:#ef4444}
.meta{color:#9ca3af;font-size:12px}
.workspace{height:calc(100% - 44px);display:flex}
.stage{flex:1;display:grid;place-items:center;overflow:auto;padding:24px;position:relative;background:radial-gradient(circle at 50% 45%,rgba(124,92,255,.07),transparent 65%)}
.wrap{position:relative;box-shadow:0 20px 60px rgba(0,0,0,.55);border:1px solid #262b3b;line-height:0;transform-origin:center center}
.wrap img{display:block;max-width:74vw;max-height:80vh;object-fit:contain;user-select:none}
.hl{position:absolute;border:2px solid #38bdf8;background:rgba(56,189,248,.14);pointer-events:none;display:none}
.side{width:280px;background:#12151e;border-left:1px solid #242938;display:flex;flex-direction:column;min-height:0}
.tabs{display:flex;border-bottom:1px solid #242938}
.tab{flex:1;border:0;border-radius:0;background:transparent;padding:9px 6px;color:#9ca3af;border-bottom:2px solid transparent}
.tab.on{color:#f8fafc;border-bottom-color:#7c5cff;background:transparent}
.pane{flex:1;overflow:auto;padding:12px;display:none;flex-direction:column;gap:8px}
.pane.on{display:flex}
.row{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 9px;background:#1a1f2d;border:1px solid #283044;border-radius:6px}
.lbl{font-size:11.5px;color:#94a3b8}
.val{font-family:ui-monospace,monospace;font-size:12px;color:#e2e8f0;word-break:break-all}
.tip{position:fixed;bottom:14px;left:16px;background:#141720dd;border:1px solid #2a3042;border-radius:6px;padding:5px 10px;font-size:12px;color:#cbd5e1}
input[type=range]{width:100%;accent-color:#7c5cff}
.empty{color:#64748b;font-size:12px;text-align:center;padding:24px 10px}
</style></head><body>
<div class="bar">
  <span class="brand">uiforge-mcp</span>
  <select id="cid"></select>
  <select id="bg"><option value="checker">Checker</option><option value="dark">Dark</option><option value="light">Light</option><option value="game">Game</option></select>
  <button id="ids" type="button">IDs</button>
  <button id="guides" type="button">Guides</button>
  <button id="zout" type="button">-</button>
  <button id="zrst" type="button">100%</button>
  <button id="zin" type="button">+</button>
  <span class="meta" id="info"></span>
  <span class="dot" id="dot" title="SSE connection"></span>
</div>
<div class="workspace">
  <div class="stage"><div class="wrap" id="wrap"><img id="pic" alt="Live canvas"/><div class="hl" id="hl"></div></div></div>
  <div class="side">
    <div class="tabs">
      <button class="tab on" data-t="inspect">Inspect</button>
      <button class="tab" data-t="layers">Layers</button>
      <button class="tab" data-t="data">Bindings</button>
      <button class="tab" data-t="anim">Anim</button>
    </div>
    <div class="pane on" id="p-inspect"><div class="empty">Click any element on the canvas to inspect bounds, ID, layer and style.</div></div>
    <div class="pane" id="p-layers"></div>
    <div class="pane" id="p-data"></div>
    <div class="pane" id="p-anim"></div>
  </div>
</div>
<div class="tip" id="tip">Live Studio v2 active · hover for coordinates, click to inspect element</div>
<script>
const cid = document.getElementById('cid'), bg = document.getElementById('bg'), pic = document.getElementById('pic');
const idsBtn = document.getElementById('ids'), guidesBtn = document.getElementById('guides');
const info = document.getElementById('info'), dot = document.getElementById('dot'), tip = document.getElementById('tip');
const wrap = document.getElementById('wrap'), hl = document.getElementById('hl');
const panes = {inspect: document.getElementById('p-inspect'), layers: document.getElementById('p-layers'), data: document.getElementById('p-data'), anim: document.getElementById('p-anim')};
let showIds = false, showGuides = false, rev = 0, dims = [0, 0], zoom = 1;
let meta = {elements: [], layers: [], states: [], data: {}, animations: []};
let activeState = '', hiddenLayers = new Set(), liveData = {}, animName = '', animT = 0, playTimer = null;

async function refreshList(pick) {
  const r = await fetch('/api/state');
  const s = await r.json();
  const cur = pick || cid.value || s.active || (s.canvases[0] && s.canvases[0].id) || '';
  cid.innerHTML = s.canvases.map(c => `<option value="${c.id}">${c.id} (${c.width}x${c.height})</option>`).join('');
  if (cur && s.canvases.some(c => c.id === cur)) cid.value = cur;
  const sel = s.canvases.find(c => c.id === cid.value);
  if (sel) { dims = [sel.width, sel.height]; info.textContent = `${sel.width}x${sel.height} · ${sel.elements} elements · rev ${s.rev}`; }
  await loadDetails();
  loadPic();
}
async function loadDetails() {
  if (!cid.value) return;
  const r = await fetch(`/api/details/${encodeURIComponent(cid.value)}`);
  if (!r.ok) return;
  meta = await r.json();
  liveData = Object.assign({}, meta.data || {}, liveData);
  renderPanels();
}
function loadPic() {
  if (!cid.value) return;
  rev++;
  const q = new URLSearchParams({bg: bg.value, ids: showIds ? '1' : '0', guides: showGuides ? '1' : '0', r: String(rev)});
  if (activeState) q.set('state', activeState);
  if (hiddenLayers.size) q.set('hide', Array.from(hiddenLayers).join(','));
  if (Object.keys(liveData).length) q.set('data', JSON.stringify(liveData));
  if (animName) { q.set('anim', animName); q.set('t', String(animT)); }
  pic.src = `/api/render/${encodeURIComponent(cid.value)}?${q}`;
}
function renderPanels() {
  const lp = panes.layers;
  let lh = '';
  if ((meta.states || []).length) {
    lh += `<div class="lbl">State</div><select id="st-sel"><option value="">default</option>${meta.states.map(st => `<option value="${st}"${activeState===st?' selected':''}>${st}</option>`).join('')}</select>`;
  }
  lh += `<div class="lbl">Layers (${(meta.layers || []).length || 1})</div>`;
  if (!(meta.layers || []).length) lh += '<div class="row"><span>base</span><span class="lbl">visible</span></div>';
  else for (const ly of meta.layers) {
    const chk = !hiddenLayers.has(ly.name);
    const p = ly.perspective;
    const pTag = p ? `<span class="lbl" style="color:${Math.abs(Number(p.visor_curve||0))>1e-5?'#f59e0b':'#4ade80'}">${Math.abs(Number(p.visor_curve||0))>1e-5?'3D Visor':'3D CSS'}</span>` : '';
    lh += `<label class="row"><span>${ly.name} ${pTag}</span><input type="checkbox" data-layer="${ly.name}" ${chk?'checked':''}/></label>`;
  }
  lp.innerHTML = lh;
  const stSel = lp.querySelector('#st-sel');
  if (stSel) stSel.onchange = () => { activeState = stSel.value; loadPic(); };
  lp.querySelectorAll('input[data-layer]').forEach(cb => {
    cb.onchange = () => { cb.checked ? hiddenLayers.delete(cb.dataset.layer) : hiddenLayers.add(cb.dataset.layer); loadPic(); };
  });

  const dp = panes.data;
  const entries = Object.entries(meta.data || {});
  const confHtml = (meta.conflicts || []).map(cf => `<div class="row" style="border-color:#f59e0b;color:#fde68a;font-size:11px">⚠ ${cf}</div>`).join('');
  if (!entries.length) {
    dp.innerHTML = confHtml + '<div class="empty">No set_binding(data={...}) variables on this canvas yet.</div>';
  } else {
    dp.innerHTML = confHtml + entries.map(([k, v]) => {
      const cur = (k in liveData) ? liveData[k] : v;
      if (typeof v === 'boolean') return `<label class="row"><span>${k}</span><input type="checkbox" data-dk="${k}" ${cur?'checked':''}/></label>`;
      if (typeof v === 'number') {
        const mx = Math.max(100, Math.abs(v) * 2);
        return `<div class="row" style="flex-direction:column;align-items:stretch"><div style="display:flex;justify-content:space-between"><span>${k}</span><span class="val" id="dv-${k}">${cur}</span></div><input type="range" min="0" max="${mx}" step="1" value="${cur}" data-dk="${k}"/></div>`;
      }
      return `<div class="row" style="flex-direction:column;align-items:stretch"><span class="lbl">${k}</span><input type="text" value="${String(cur).replace(/"/g,'&quot;')}" data-dk="${k}"/></div>`;
    }).join('');
    dp.querySelectorAll('[data-dk]').forEach(inp => {
      inp.oninput = () => {
        const k = inp.dataset.dk;
        liveData[k] = inp.type === 'checkbox' ? inp.checked : (inp.type === 'range' ? Number(inp.value) : inp.value);
        const sp = document.getElementById('dv-' + k);
        if (sp) sp.textContent = String(liveData[k]);
        loadPic();
      };
    });
  }

  const ap = panes.anim;
  const anims = meta.animations || [];
  if (!anims.length) {
    ap.innerHTML = '<div class="empty">No animations on this canvas yet.</div>';
  } else {
    const curA = anims.find(a => a.name === animName) || anims[0];
    ap.innerHTML = `<select id="an-sel"><option value="">(static)</option>${anims.map(a => `<option value="${a.name}"${a.name===animName?' selected':''}>${a.name} (${a.duration}s)</option>`).join('')}</select>` +
      `<div class="row" style="flex-direction:column;align-items:stretch"><div style="display:flex;justify-content:space-between"><span class="lbl">Timeline</span><span class="val" id="at-v">${animT.toFixed(2)}s</span></div><input id="an-t" type="range" min="0" max="${curA.duration}" step="0.05" value="${animT}"/></div>` +
      `<button id="an-play" type="button">${playTimer?'Pause':'Play'}</button>`;
    ap.querySelector('#an-sel').onchange = e => { animName = e.target.value; animT = 0; renderPanels(); loadPic(); };
    ap.querySelector('#an-t').oninput = e => { if (!animName && anims[0]) animName = anims[0].name; animT = Number(e.target.value); ap.querySelector('#at-v').textContent = animT.toFixed(2) + 's'; loadPic(); };
    ap.querySelector('#an-play').onclick = () => {
      if (playTimer) { clearInterval(playTimer); playTimer = null; ap.querySelector('#an-play').textContent = 'Play'; return; }
      if (!animName && anims[0]) animName = anims[0].name;
      ap.querySelector('#an-play').textContent = 'Pause';
      const dur = curA.duration || 1;
      playTimer = setInterval(() => {
        animT = (animT + 0.1) % dur;
        const sl = ap.querySelector('#an-t'), tv = ap.querySelector('#at-v');
        if (sl) sl.value = String(animT);
        if (tv) tv.textContent = animT.toFixed(2) + 's';
        loadPic();
      }, 140);
    };
  }
}
function inspectEl(el) {
  const [x, y, w, h] = el.bbox_xywh || [0, 0, 0, 0];
  panes.inspect.innerHTML =
    `<div class="row"><span class="lbl">ID</span><span class="val">${el.id}</span></div>` +
    `<div class="row"><span class="lbl">Type</span><span class="val">${el.type}</span></div>` +
    `<div class="row"><span class="lbl">BBox</span><span class="val">${x}, ${y} · ${w}×${h}</span></div>` +
    (el.layer ? `<div class="row"><span class="lbl">Layer</span><span class="val">${el.layer}</span></div>` : '') +
    (el.group ? `<div class="row"><span class="lbl">Group</span><span class="val">${el.group}</span></div>` : '') +
    (el.material ? `<div class="row"><span class="lbl">Material</span><span class="val">${typeof el.material==='string'?el.material:(el.material.name||'pbr')}</span></div>` : '') +
    (el.bind ? `<div class="row"><span class="lbl">Bind</span><span class="val">${el.bind}</span></div>` : '') +
    (el.note ? `<div class="row"><span class="lbl">Note</span><span class="val">${el.note}</span></div>` : '') +
    `<button id="cp-id" type="button">Copy ID</button>`;
  const cp = document.getElementById('cp-id');
  if (cp) cp.onclick = () => { navigator.clipboard && navigator.clipboard.writeText(el.id); cp.textContent = 'Copied!'; };
  if (dims[0] && dims[1]) {
    hl.style.display = 'block';
    hl.style.left = (x / dims[0] * 100) + '%';
    hl.style.top = (y / dims[1] * 100) + '%';
    hl.style.width = (w / dims[0] * 100) + '%';
    hl.style.height = (h / dims[1] * 100) + '%';
  }
}
document.querySelectorAll('.tab').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b === btn));
    for (const [k, p] of Object.entries(panes)) p.classList.toggle('on', k === btn.dataset.t);
  };
});
cid.onchange = () => { activeState = ''; hiddenLayers.clear(); liveData = {}; animName = ''; hl.style.display = 'none'; refreshList(cid.value); };
bg.onchange = loadPic;
idsBtn.onclick = () => { showIds = !showIds; idsBtn.classList.toggle('on', showIds); loadPic(); };
guidesBtn.onclick = () => { showGuides = !showGuides; guidesBtn.classList.toggle('on', showGuides); loadPic(); };
function setZoom(z) { zoom = Math.max(0.25, Math.min(4, z)); wrap.style.transform = `scale(${zoom})`; document.getElementById('zrst').textContent = Math.round(zoom * 100) + '%'; }
document.getElementById('zin').onclick = () => setZoom(zoom * 1.25);
document.getElementById('zout').onclick = () => setZoom(zoom / 1.25);
document.getElementById('zrst').onclick = () => setZoom(1);
pic.onmousemove = e => {
  if (!dims[0]) return;
  const r = pic.getBoundingClientRect();
  const x = Math.round((e.clientX - r.left) / r.width * dims[0]);
  const y = Math.round((e.clientY - r.top) / r.height * dims[1]);
  tip.textContent = `x: ${x}, y: ${y} (canvas ${dims[0]}x${dims[1]})`;
};
pic.onclick = e => {
  if (!dims[0]) return;
  const r = pic.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width * dims[0];
  const y = (e.clientY - r.top) / r.height * dims[1];
  const els = meta.elements || [];
  for (let i = els.length - 1; i >= 0; i--) {
    const b = els[i].bbox_xywh;
    if (b && x >= b[0] && x <= b[0] + b[2] && y >= b[1] && y <= b[1] + b[3]) { inspectEl(els[i]); break; }
  }
};
const es = new EventSource('/events');
es.onopen = () => dot.classList.remove('off');
es.onerror = () => dot.classList.add('off');
es.onmessage = e => { const d = JSON.parse(e.data); refreshList(d.canvas || cid.value); };
refreshList();
</script></body></html>
"""


class _QuietLiveHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class LiveStudio:
    """Localhost-only HTTP + SSE interactive preview studio v2 attached to a Store."""

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

            def _send(self, code: int, ctype: str, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/":
                    self._send(200, "text/html; charset=utf-8", _HTML.encode("utf-8"))
                    return
                if path == "/api/state":
                    s = studio._get_store()
                    s.on_change(studio.notify)
                    items = [{"id": c["id"], "width": c["width"], "height": c["height"],
                              "elements": len(c.get("elements", []))} for c in s.canvases.values()]
                    payload = json.dumps({"rev": s.rev, "active": studio._last_canvas, "canvases": items}).encode("utf-8")
                    self._send(200, "application/json", payload)
                    return
                if path.startswith("/api/details/"):
                    cid = unquote(path[len("/api/details/"):])
                    s = studio._get_store()
                    try:
                        from .studio_app import studio_snapshot
                        snap = studio_snapshot(s, cid, include_image=False)
                        self._send(200, "application/json", json.dumps(snap).encode("utf-8"))
                    except Exception as exc:
                        self._send(404, "text/plain; charset=utf-8", str(exc).encode("utf-8"))
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
                        except Exception:
                            data_override = None
                    anim_name = qs.get("anim", [""])[0] or None
                    anim_t = float(qs.get("t", ["0"])[0] or 0.0)
                    s = studio._get_store()
                    try:
                        from .core import render_view
                        s.sync_from_disk()
                        view, _, _ = render_view(
                            s, cid, background=bg, show_ids=show_ids, show_guides=show_guides,
                            state=state_name, data=data_override, hide_layers=hide_layers,
                            animation=anim_name, t=anim_t, max_dim=1280.0,
                        )
                        buf = io.BytesIO()
                        view.convert("RGB").save(buf, format="PNG")
                        self._send(200, "image/png", buf.getvalue())
                    except Exception as exc:
                        self._send(404, "text/plain; charset=utf-8", str(exc).encode("utf-8"))
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

        srv = _QuietLiveHTTPServer(("127.0.0.1", self.port), Handler)
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
