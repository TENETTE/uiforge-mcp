"""MCP App (SEP-1865) Interactive Studio UI for Antigravity, Claude, VS Code and ChatGPT.

Exposes:
  - Resource ``ui://uiforge/studio.html`` (MIME ``text/html;profile=mcp-app``)
  - Entrypoint tool ``open_studio`` with Antigravity ``aux_pane`` / ``global`` entrypoints
  - App-only tools ``studio_app_state`` and ``studio_app_render`` (``visibility: ["app"]`` so
    they add zero tokens to the LLM context)

The HTML is 100% self-contained (zero external scripts/CDNs, CSP-compliant), honors host
``styles.variables`` and light/dark theme updates, and speaks SEP-1865 JSON-RPC 2.0 over
``postMessage`` with automatic fallback when opened standalone.
"""

from __future__ import annotations

from typing import Any

from . import __version__

STUDIO_APP_URI = "ui://uiforge/studio.html"

STUDIO_APP_META: dict[str, Any] = {
    "ui": {"resourceUri": STUDIO_APP_URI},
    "com.google.antigravity/ui": {
        "entrypoints": [
            {"type": "aux_pane", "title": "UIForge Studio"},
            {"type": "global", "title": "UIForge Studio"},
        ]
    },
}

STUDIO_INLINE_META: dict[str, Any] = {
    "ui": {"resourceUri": STUDIO_APP_URI},
}

APP_ONLY_META: dict[str, Any] = {
    "ui": {"visibility": ["app"]},
}

STUDIO_APP_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>UIForge Studio</title>
<style>
*{box-sizing:border-box}
:root{
  --bg:var(--color-background-primary,#0d0f14);
  --bg2:var(--color-background-secondary,#141720);
  --bg3:var(--color-background-tertiary,#1d2230);
  --fg:var(--color-text-primary,#e5e7eb);
  --muted:var(--color-text-secondary,#94a3b8);
  --bd:var(--color-border-primary,#262b3b);
  --acc:#7c5cff;
  --font:var(--font-sans,system-ui,-apple-system,sans-serif);
}
html,body{margin:0;padding:0;height:100%;min-height:460px;background:var(--bg);color:var(--fg);font:12.5px/1.4 var(--font);overflow:hidden}
.shell{display:flex;flex-direction:column;height:100vh;min-height:460px}
.bar{height:40px;padding:0 10px;display:flex;align-items:center;gap:6px;background:var(--bg2);border-bottom:1px solid var(--bd);flex:0 0 auto;overflow-x:auto}
.brand{font-weight:700;color:#a78bfa;letter-spacing:.02em;margin-right:2px;white-space:nowrap}
select,button,input[type=text]{background:var(--bg3);color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:3px 8px;font:inherit}
button{cursor:pointer;white-space:nowrap}
button:hover,select:hover{border-color:var(--acc)}
button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.sp{flex:1}
.main{flex:1;display:flex;min-height:0}
.stage{flex:1;display:grid;place-items:center;overflow:auto;padding:14px;position:relative;background:radial-gradient(circle at 50% 45%,rgba(124,92,255,.07),transparent 65%)}
.wrap{position:relative;border:1px solid var(--bd);box-shadow:0 14px 40px rgba(0,0,0,.45);line-height:0;transform-origin:center center}
.wrap img{display:block;max-width:100%;max-height:70vh;object-fit:contain;user-select:none}
.hl{position:absolute;border:2px solid #38bdf8;background:rgba(56,189,248,.12);pointer-events:none;display:none}
.side{width:248px;flex:0 0 248px;background:var(--bg2);border-left:1px solid var(--bd);display:flex;flex-direction:column;min-height:0}
.tabs{display:flex;border-bottom:1px solid var(--bd)}
.tab{flex:1;border:0;border-radius:0;background:transparent;padding:7px 4px;font-size:11.5px;color:var(--muted);border-bottom:2px solid transparent}
.tab.on{color:var(--fg);border-bottom-color:var(--acc);background:transparent}
.pane{flex:1;overflow:auto;padding:10px;display:none;flex-direction:column;gap:8px}
.pane.on{display:flex}
.row{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:5px 7px;background:var(--bg3);border:1px solid var(--bd);border-radius:6px}
.lbl{font-size:11.5px;color:var(--muted)}
.val{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--fg);word-break:break-all}
.foot{height:26px;padding:0 10px;display:flex;align-items:center;gap:10px;background:var(--bg2);border-top:1px solid var(--bd);font-size:11px;color:var(--muted)}
input[type=range]{width:100%;accent-color:var(--acc)}
.empty{color:var(--muted);font-size:12px;text-align:center;padding:18px 8px}
</style></head><body>
<div class="shell">
  <div class="bar">
    <span class="brand">UIForge</span>
    <select id="cid" title="Canvas"></select>
    <select id="bg" title="Backdrop"><option value="checker">Checker</option><option value="dark">Dark</option><option value="light">Light</option><option value="game">Game</option></select>
    <button id="ids" type="button">IDs</button>
    <button id="guides" type="button">Guides</button>
    <button id="zout" type="button" title="Zoom out">-</button>
    <button id="zrst" type="button" title="Reset zoom">100%</button>
    <button id="zin" type="button" title="Zoom in">+</button>
    <span class="sp"></span>
    <button id="refresh" type="button">Refresh</button>
  </div>
  <div class="main">
    <div class="stage" id="stage">
      <div class="wrap" id="wrap"><img id="pic" alt="Canvas preview"/><div class="hl" id="hl"></div></div>
    </div>
    <div class="side">
      <div class="tabs">
        <button class="tab on" data-t="inspect">Inspect</button>
        <button class="tab" data-t="layers">Layers</button>
        <button class="tab" data-t="data">Data</button>
        <button class="tab" data-t="anim">Anim</button>
      </div>
      <div class="pane on" id="p-inspect"><div class="empty">Click any element on the canvas to inspect its ID, bounds and style.</div></div>
      <div class="pane" id="p-layers"></div>
      <div class="pane" id="p-data"></div>
      <div class="pane" id="p-anim"></div>
    </div>
  </div>
  <div class="foot"><span id="status">Connecting to MCP host...</span><span class="sp"></span><span id="coords">x: -, y: -</span></div>
</div>
<script>
(function(){
  const cid = document.getElementById('cid'), bg = document.getElementById('bg'), pic = document.getElementById('pic');
  const idsBtn = document.getElementById('ids'), guidesBtn = document.getElementById('guides');
  const wrap = document.getElementById('wrap'), hl = document.getElementById('hl');
  const statusEl = document.getElementById('status'), coordsEl = document.getElementById('coords');
  const panes = {inspect: document.getElementById('p-inspect'), layers: document.getElementById('p-layers'), data: document.getElementById('p-data'), anim: document.getElementById('p-anim')};

  let state = {canvases: [], active: null, elements: [], layers: [], states: [], data: {}, animations: []};
  let showIds = false, showGuides = false, zoom = 1, activeState = null, hiddenLayers = new Set(), liveData = {}, animName = null, animT = 0, playTimer = null;
  let dims = [0, 0], reqId = 1;
  const pending = new Map();

  function post(msg) { try { window.parent.postMessage(msg, '*'); } catch (_) {} }
  function rpc(method, params) {
    return new Promise((resolve, reject) => {
      const id = reqId++;
      pending.set(id, {resolve, reject});
      post({jsonrpc: '2.0', id, method, params: params || {}});
      setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error('timeout')); } }, 15000);
    });
  }
  function notify(method, params) { post({jsonrpc: '2.0', method, params: params || {}}); }
  function reportSize() { notify('ui/notifications/size-changed', {height: Math.min(760, Math.max(480, document.documentElement.scrollHeight))}); }

  function applyHostContext(ctx) {
    if (!ctx) return;
    if (ctx.theme) document.documentElement.dataset.theme = ctx.theme;
    const vars = ctx.styles && ctx.styles.variables;
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        if (typeof v === 'string') document.documentElement.style.setProperty(k, v);
      }
    }
  }

  async function callTool(name, args) {
    const res = await rpc('tools/call', {name, arguments: args || {}});
    if (res && res.structuredContent) return res.structuredContent;
    if (res && Array.isArray(res.content)) {
      for (const block of res.content) {
        if (block && block.type === 'text' && block.text) {
          try { return JSON.parse(block.text); } catch (_) { return {text: block.text}; }
        }
      }
    }
    return res || {};
  }

  function applyState(s) {
    if (!s || !Array.isArray(s.canvases)) return;
    state = s;
    const cur = s.active || cid.value || (s.canvases[0] && s.canvases[0].id) || '';
    cid.innerHTML = s.canvases.map(c => `<option value="${c.id}">${c.id} (${c.width}x${c.height})</option>`).join('');
    if (cur && s.canvases.some(c => c.id === cur)) cid.value = cur;
    const sel = s.canvases.find(c => c.id === cid.value);
    dims = sel ? [sel.width, sel.height] : [0, 0];
    liveData = Object.assign({}, s.data || {});
    renderSidePanels();
    if (s.image_data_uri) {
      pic.src = s.image_data_uri;
      statusEl.textContent = `${cid.value} · ${dims[0]}x${dims[1]} · ${state.elements.length} elements`;
    } else if (cid.value) {
      renderCanvas();
    }
    reportSize();
  }

  async function refreshState(target) {
    try {
      statusEl.textContent = 'Syncing...';
      const s = await callTool('studio_app_state', target ? {canvas: target} : {});
      applyState(s);
    } catch (e) {
      statusEl.textContent = 'Studio ready (offline preview)';
    }
  }

  async function renderCanvas() {
    if (!cid.value) return;
    try {
      const args = {canvas: cid.value, background: bg.value, show_ids: showIds, show_guides: showGuides};
      if (activeState) args.state = activeState;
      if (hiddenLayers.size) args.hide_layers = Array.from(hiddenLayers);
      if (Object.keys(liveData).length) args.data = liveData;
      if (animName) { args.animation = animName; args.t = animT; }
      const r = await callTool('studio_app_render', args);
      if (r && r.image_data_uri) {
        pic.src = r.image_data_uri;
        dims = [r.width || dims[0], r.height || dims[1]];
        if (Array.isArray(r.elements)) state.elements = r.elements;
        statusEl.textContent = `${cid.value} · ${dims[0]}x${dims[1]} · ${state.elements.length} elements`;
      }
    } catch (_) {}
  }

  function renderSidePanels() {
    const lPane = panes.layers;
    const layers = state.layers || [];
    const states = state.states || [];
    let lh = '';
    if (states.length) {
      lh += `<div class="lbl">State Preview</div><select id="st-sel"><option value="">default</option>${states.map(st => `<option value="${st}"${activeState===st?' selected':''}>${st}</option>`).join('')}</select>`;
    }
    lh += `<div class="lbl" style="margin-top:4px">Layers (${layers.length || 1})</div>`;
    if (!layers.length) {
      lh += '<div class="row"><span>base</span><span class="lbl">visible</span></div>';
    } else {
      for (const ly of layers) {
        const chk = !hiddenLayers.has(ly.name);
        lh += `<label class="row"><span>${ly.name}</span><input type="checkbox" data-layer="${ly.name}" ${chk?'checked':''}/></label>`;
      }
    }
    lPane.innerHTML = lh;
    const stSel = lPane.querySelector('#st-sel');
    if (stSel) stSel.onchange = () => { activeState = stSel.value || null; renderCanvas(); };
    lPane.querySelectorAll('input[data-layer]').forEach(cb => {
      cb.onchange = () => {
        if (cb.checked) hiddenLayers.delete(cb.dataset.layer); else hiddenLayers.add(cb.dataset.layer);
        renderCanvas();
      };
    });

    const dPane = panes.data;
    const entries = Object.entries(liveData);
    if (!entries.length) {
      dPane.innerHTML = '<div class="empty">No data bindings yet. Use set_binding(data={...}) to test live variables here.</div>';
    } else {
      dPane.innerHTML = entries.map(([k, v]) => {
        if (typeof v === 'boolean') return `<label class="row"><span>${k}</span><input type="checkbox" data-dk="${k}" ${v?'checked':''}/></label>`;
        if (typeof v === 'number') {
          const mx = Math.max(100, Math.abs(v) * 2);
          return `<div class="row" style="flex-direction:column;align-items:stretch"><div style="display:flex;justify-content:space-between"><span>${k}</span><span class="val" id="dv-${k}">${v}</span></div><input type="range" min="0" max="${mx}" step="1" value="${v}" data-dk="${k}"/></div>`;
        }
        return `<div class="row" style="flex-direction:column;align-items:stretch"><span class="lbl">${k}</span><input type="text" value="${String(v).replace(/"/g,'&quot;')}" data-dk="${k}"/></div>`;
      }).join('');
      dPane.querySelectorAll('[data-dk]').forEach(inp => {
        inp.oninput = () => {
          const k = inp.dataset.dk;
          liveData[k] = inp.type === 'checkbox' ? inp.checked : (inp.type === 'range' ? Number(inp.value) : inp.value);
          const sp = document.getElementById('dv-' + k);
          if (sp) sp.textContent = String(liveData[k]);
          renderCanvas();
        };
      });
    }

    const aPane = panes.anim;
    const anims = state.animations || [];
    if (!anims.length) {
      aPane.innerHTML = '<div class="empty">No animations on this canvas yet.</div>';
    } else {
      const curA = anims.find(a => a.name === animName) || anims[0];
      animName = curA.name;
      aPane.innerHTML = `<select id="an-sel">${anims.map(a => `<option value="${a.name}"${a.name===animName?' selected':''}>${a.name} (${a.duration}s)</option>`).join('')}</select>` +
        `<div class="row" style="flex-direction:column;align-items:stretch"><div style="display:flex;justify-content:space-between"><span class="lbl">Time</span><span class="val" id="at-v">${animT.toFixed(2)}s</span></div><input id="an-t" type="range" min="0" max="${curA.duration}" step="0.05" value="${animT}"/></div>` +
        `<div style="display:flex;gap:6px"><button id="an-play" type="button" style="flex:1">Play</button><button id="an-rst" type="button">Reset</button></div>`;
      aPane.querySelector('#an-sel').onchange = e => { animName = e.target.value; animT = 0; renderSidePanels(); renderCanvas(); };
      aPane.querySelector('#an-t').oninput = e => { animT = Number(e.target.value); aPane.querySelector('#at-v').textContent = animT.toFixed(2) + 's'; renderCanvas(); };
      aPane.querySelector('#an-rst').onclick = () => { if (playTimer) { clearInterval(playTimer); playTimer = null; } animName = null; animT = 0; renderCanvas(); };
      aPane.querySelector('#an-play').onclick = () => {
        if (playTimer) { clearInterval(playTimer); playTimer = null; aPane.querySelector('#an-play').textContent = 'Play'; return; }
        aPane.querySelector('#an-play').textContent = 'Pause';
        const dur = curA.duration || 1;
        playTimer = setInterval(() => {
          animT = (animT + 0.1) % dur;
          const sl = aPane.querySelector('#an-t'), tv = aPane.querySelector('#at-v');
          if (sl) sl.value = String(animT);
          if (tv) tv.textContent = animT.toFixed(2) + 's';
          renderCanvas();
        }, 160);
      };
    }
  }

  function inspectElement(el) {
    if (!el) return;
    const [x, y, w, h] = el.bbox_xywh || [0, 0, 0, 0];
    panes.inspect.innerHTML =
      `<div class="row"><span class="lbl">ID</span><span class="val">${el.id}</span></div>` +
      `<div class="row"><span class="lbl">Type</span><span class="val">${el.type}</span></div>` +
      `<div class="row"><span class="lbl">Box</span><span class="val">${x}, ${y} · ${w}×${h}</span></div>` +
      (el.layer ? `<div class="row"><span class="lbl">Layer</span><span class="val">${el.layer}</span></div>` : '') +
      (el.group ? `<div class="row"><span class="lbl">Group</span><span class="val">${el.group}</span></div>` : '') +
      (el.note ? `<div class="row"><span class="lbl">Note</span><span class="val">${el.note}</span></div>` : '');
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
  cid.onchange = () => { activeState = null; hiddenLayers.clear(); animName = null; hl.style.display = 'none'; refreshState(cid.value); };
  bg.onchange = renderCanvas;
  idsBtn.onclick = () => { showIds = !showIds; idsBtn.classList.toggle('on', showIds); renderCanvas(); };
  guidesBtn.onclick = () => { showGuides = !showGuides; guidesBtn.classList.toggle('on', showGuides); renderCanvas(); };
  document.getElementById('refresh').onclick = () => refreshState(cid.value);
  function setZoom(z) { zoom = Math.max(0.25, Math.min(4, z)); wrap.style.transform = `scale(${zoom})`; document.getElementById('zrst').textContent = Math.round(zoom * 100) + '%'; }
  document.getElementById('zin').onclick = () => setZoom(zoom * 1.25);
  document.getElementById('zout').onclick = () => setZoom(zoom / 1.25);
  document.getElementById('zrst').onclick = () => setZoom(1);

  pic.onmousemove = e => {
    if (!dims[0]) return;
    const r = pic.getBoundingClientRect();
    const x = Math.round((e.clientX - r.left) / r.width * dims[0]);
    const y = Math.round((e.clientY - r.top) / r.height * dims[1]);
    coordsEl.textContent = `x: ${x}, y: ${y}`;
  };
  pic.onclick = e => {
    if (!dims[0]) return;
    const r = pic.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width * dims[0];
    const y = (e.clientY - r.top) / r.height * dims[1];
    const els = state.elements || [];
    for (let i = els.length - 1; i >= 0; i--) {
      const b = els[i].bbox_xywh;
      if (b && x >= b[0] && x <= b[0] + b[2] && y >= b[1] && y <= b[1] + b[3]) {
        inspectElement(els[i]);
        break;
      }
    }
  };

  window.addEventListener('message', ev => {
    const m = ev.data;
    if (!m || typeof m !== 'object' || m.jsonrpc !== '2.0') return;
    if (m.id !== undefined && (m.result !== undefined || m.error !== undefined)) {
      const p = pending.get(m.id);
      if (p) { pending.delete(m.id); m.error ? p.reject(m.error) : p.resolve(m.result); }
      return;
    }
    if (m.method === 'ping' && m.id !== undefined) {
      post({jsonrpc: '2.0', id: m.id, result: {}});
    } else if (m.method === 'ui/notifications/host-context-changed') {
      applyHostContext(m.params);
    } else if (m.method === 'ui/notifications/tool-result') {
      const res = m.params || {};
      if (res.structuredContent) applyState(res.structuredContent);
      else refreshState(cid.value || undefined);
    }
  });

  (async function init() {
    try {
      const initRes = await rpc('ui/initialize', {
        appInfo: {name: 'UIForge Studio', version: '__UIFORGE_VERSION__'},
        appCapabilities: {},
        protocolVersion: '2026-01-26',
      });
      if (initRes && initRes.hostContext) applyHostContext(initRes.hostContext);
      notify('ui/notifications/initialized', {});
      await refreshState();
    } catch (_) {
      statusEl.textContent = 'UIForge Studio ready';
    }
  })();
})();
</script></body></html>
"""


STUDIO_APP_HTML = STUDIO_APP_HTML.replace("__UIFORGE_VERSION__", __version__)


def studio_snapshot(st, canvas_id: str | None = None, *, background: str = "checker",
                    show_ids: bool = False, show_guides: bool = False, state: str | None = None,
                    data: dict[str, Any] | None = None, hide_layers: list[str] | None = None,
                    animation: str | None = None, t: float | None = None,
                    include_image: bool = True) -> dict[str, Any]:
    """Build JSON-serializable studio state + optional inline PNG data URI via shared core.render_view."""
    from .core import image_to_data_uri, render_view

    st.sync_from_disk()
    canvases_list = [
        {"id": c["id"], "width": c["width"], "height": c["height"], "elements": len(c.get("elements", []))}
        for c in st.canvases.values()
    ]
    cid = canvas_id if (canvas_id and canvas_id in st.canvases) else (canvases_list[0]["id"] if canvases_list else None)
    if cid is None:
        return {"canvases": [], "active": None, "elements": [], "layers": [], "states": [], "data": {}, "animations": []}

    view, base_c, el_rows = render_view(
        st, cid, background=background, show_ids=show_ids, show_guides=show_guides,
        state=state, data=data, hide_layers=hide_layers, animation=animation, t=t, max_dim=960.0,
    )
    out: dict[str, Any] = {
        "canvases": canvases_list,
        "active": cid,
        "width": base_c["width"],
        "height": base_c["height"],
        "rev": st.rev,
        "layers": [{"name": ly["name"], "visible": bool(ly.get("visible", True)), "blend": ly.get("blend", "normal")}
                   for ly in (base_c.get("layers") or [])],
        "states": sorted((base_c.get("states") or {}).keys()),
        "data": dict(base_c.get("data") or {}),
        "animations": [{"name": k, "duration": float(v.get("duration", 1.0)), "loop": bool(v.get("loop"))}
                       for k, v in sorted((base_c.get("animations") or {}).items())],
        "elements": el_rows,
    }
    if include_image:
        out["image_data_uri"] = image_to_data_uri(view)
    return out
