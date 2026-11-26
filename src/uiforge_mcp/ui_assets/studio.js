(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    boot: null,
    canvasId: null,
    canvas: null,
    selectedId: null,
    selectedIds: new Set(),
    zoom: 1,
    showIds: false,
    showGuides: false,
    bg: "checker",
    previewState: "",
    simMode: "",
    langMode: "",
    hiddenLayers: new Set(),
    liveData: {},
    animName: "",
    animT: 0,
    playTimer: null,
    rev: 0,
    drag: null,
    resize: null,
    elFilter: "",
    activeModal: null,
    modalOpener: null,
    cmdkItems: [],
    cmdkIdx: 0,
  };

  function announce(msg) {
    const live = $("sr-live");
    if (live) live.textContent = msg;
  }

  function toast(msg, kind = "info") {
    announce(msg);
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = msg;
    $("toasts").appendChild(el);
    setTimeout(() => el.remove(), 3400);
  }

  function confirmButton(btn, label = "Saved ✓") {
    if (!btn) return;
    if (!btn.dataset.origLabel) btn.dataset.origLabel = btn.textContent;
    btn.textContent = label;
    btn.classList.add("confirmed");
    clearTimeout(btn._confirmTimer);
    btn._confirmTimer = setTimeout(() => {
      btn.textContent = btn.dataset.origLabel;
      btn.classList.remove("confirmed");
    }, 1350);
  }

  function shakeEl(el) {
    if (!el) return;
    el.classList.remove("shake");
    void el.offsetWidth;
    el.classList.add("shake");
    setTimeout(() => el.classList.remove("shake"), 280);
  }

  function isTypingTarget(el) {
    if (!el) return false;
    const tag = (el.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  // Accessible Modal Manager (focus move, Tab trap, Escape close, opener focus restore)
  function getFocusable(root) {
    return Array.from(root.querySelectorAll(
      'button:not([disabled]):not([hidden]), input:not([disabled]):not([hidden]), select:not([disabled]):not([hidden]), textarea:not([disabled]):not([hidden]), [tabindex]:not([tabindex="-1"])'
    )).filter((n) => n.offsetParent !== null);
  }

  function openModal(id, opener = document.activeElement) {
    const bg = $(id);
    if (!bg) return;
    if (state.activeModal && state.activeModal !== id) closeModal(state.activeModal, false);
    state.modalOpener = opener;
    state.activeModal = id;
    bg.hidden = false;
    requestAnimationFrame(() => {
      const focusables = getFocusable(bg);
      const firstInput = bg.querySelector("input:not([type=hidden]), select, textarea");
      if (firstInput && firstInput.offsetParent !== null) firstInput.focus();
      else if (focusables.length) focusables[0].focus();
    });
  }

  function closeModal(id = state.activeModal, restoreFocus = true) {
    if (!id) return;
    const bg = $(id);
    if (bg) bg.hidden = true;
    if (state.activeModal === id) state.activeModal = null;
    if (restoreFocus && state.modalOpener && typeof state.modalOpener.focus === "function") {
      try { state.modalOpener.focus(); } catch (_) {}
      state.modalOpener = null;
    }
  }

  document.querySelectorAll(".modal-bg").forEach((bg) => {
    bg.addEventListener("mousedown", (e) => {
      if (e.target === bg) closeModal(bg.id);
    });
  });

  // Theme Switcher (instant without cross-fade lag via data-theme-switching)
  function applyTheme(theme, persist = true) {
    const root = document.documentElement;
    root.setAttribute("data-theme-switching", "");
    root.setAttribute("data-theme", theme);
    void document.body.offsetHeight;
    requestAnimationFrame(() => root.removeAttribute("data-theme-switching"));
    if (persist) {
      try { localStorage.setItem("uiforge_studio_theme", theme); } catch (_) {}
    }
    const ico = $("ico-theme");
    if (ico) {
      ico.innerHTML = theme === "light"
        ? '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
        : '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>';
    }
  }
  try {
    const savedTheme = localStorage.getItem("uiforge_studio_theme");
    if (savedTheme === "light" || savedTheme === "dark") applyTheme(savedTheme, false);
  } catch (_) {}

  $("btn-theme-toggle").onclick = () => {
    const cur = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    applyTheme(cur, true);
    announce(`Switched to ${cur} studio theme`);
  };

  // Tab Rail Sliding Ink Indicator (transform only)
  function moveTabInk(railSelector, inkId, activeBtn) {
    const tabs = Array.from(document.querySelectorAll(railSelector));
    const idx = Math.max(0, tabs.indexOf(activeBtn));
    const ink = $(inkId);
    if (ink && tabs.length) {
      ink.style.width = `${100 / tabs.length}%`;
      ink.style.transform = `translateX(${idx * 100}%)`;
    }
  }

  async function apiOp(op, args = {}) {
    const r = await fetch("/api/op", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op, args }),
    });
    const d = await r.json();
    if (!d.ok) {
      toast(`${op}: ${d.error}`, "err");
      await refreshActivity();
      throw new Error(d.error);
    }
    $("console-last").textContent = `${op} (${d.duration_ms}ms)`;
    return d.result;
  }

  async function bootstrap(pickCanvas) {
    const r = await fetch("/api/bootstrap");
    const b = await r.json();
    state.boot = b;
    $("app-ver").textContent = `v${b.version}`;

    const pill = $("mode-pill");
    pill.classList.toggle("combined", b.mode === "combined");
    $("mode-label").textContent = b.mode === "combined" ? "Combined · MCP + UI" : "Human Studio";

    const activeGpu = (b.doctor && b.doctor.active_backend) || "cpu";
    $("gpu-label").textContent = activeGpu.toUpperCase();
    $("gpu-dot").classList.toggle("on", activeGpu !== "cpu");
    $("set-mode").textContent = b.mode;
    $("set-ws").textContent = b.workspace;
    $("set-mcp").textContent = b.mcp_available ? "Available" : "Not required (Human Mode)";
    $("set-gpu-hw").textContent = ((b.doctor && b.doctor.hardware && b.doctor.hardware.adapters) || ["CPU"]).join(", ");
    $("set-gpu-active").textContent = activeGpu.toUpperCase();

    const cSel = $("canvas-sel");
    const prev = pickCanvas || state.canvasId || b.active || (b.canvases[0] && b.canvases[0].id) || "";
    cSel.innerHTML = b.canvases.length
      ? b.canvases.map((c) => `<option value="${c.id}">${c.id} (${c.width}×${c.height})</option>`).join("")
      : '<option value="">No canvas</option>';
    if (prev && b.canvases.some((c) => c.id === prev)) {
      cSel.value = prev;
      state.canvasId = prev;
    } else {
      state.canvasId = b.canvases[0] ? b.canvases[0].id : null;
    }

    const sSel = $("style-sel");
    if (!sSel.options.length) {
      sSel.innerHTML = Object.entries(b.style_presets)
        .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
    }
    const qSel = $("quality-sel");
    if (!qSel.options.length) {
      qSel.innerHTML = Object.entries(b.quality_levels)
        .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
    }
    const prof = (b.theme && b.theme.profile) || {};
    if (prof.style_preset) sSel.value = prof.style_preset;
    if (prof.quality) qSel.value = prof.quality;

    const mSel = $("ins-mat");
    const allMats = [...b.materials.all, ...(b.materials.custom || [])];
    const curM = mSel.value;
    mSel.innerHTML = '<option value="">(None / Flat Fill)</option>' +
      allMats.map((m) => `<option value="${m}">${m}</option>`).join("");
    if (curM) mSel.value = curM;

    const ideSel = $("ide-client-sel");
    if (!ideSel.options.length) {
      ideSel.innerHTML = b.ide_clients.map((c) => `<option value="${c}">${c}</option>`).join("");
    }

    renderFramesGrid(b.frame_presets);
    renderIconsGrid(b.icons, "");
    const matGroups = (b.materials.custom && b.materials.custom.length)
      ? Object.assign({ "Custom Workspace PBR": b.materials.custom }, b.materials.groups)
      : b.materials.groups;
    renderMaterialsGallery(matGroups, $("mat-search").value || "");
    renderOpsList(b.operations, "");
    renderThemeTokens(b.theme);
    renderActivity(b.activity);

    if (state.canvasId) {
      await loadCanvas(state.canvasId);
    } else {
      $("empty-stage").hidden = false;
      $("canvas-frame").hidden = true;
      $("layers-list").innerHTML = "";
      $("elements-list").innerHTML = "";
      $("el-count").textContent = "0";
      $("dim-readout").textContent = "";
    }
  }

  async function loadCanvas(cid) {
    state.canvasId = cid;
    const r = await fetch(`/api/canvas/${encodeURIComponent(cid)}`);
    if (!r.ok) return;
    const c = await r.json();
    state.canvas = c;
    $("empty-stage").hidden = true;
    $("canvas-frame").hidden = false;
    $("dim-readout").textContent = `${c.width} × ${c.height} px · ${c.elements.length} elements`;
    $("el-count").textContent = String(c.elements.length);
    if (c.profile && c.profile.quality) $("quality-sel").value = c.profile.quality;
    if (c.profile && c.profile.style_preset) $("style-sel").value = c.profile.style_preset;

    const stSel = $("state-sel");
    stSel.innerHTML = '<option value="">State: default</option>' +
      (c.states || []).map((st) => `<option value="${st}"${state.previewState === st ? " selected" : ""}>State: ${st}</option>`).join("");

    renderLayers(c.layers || []);
    renderElementsList(c.elements || []);
    renderBindingsAndAnim(c);
    renderVersions(c.versions || []);
    if (state.selectedId && c.raw_elements[state.selectedId]) {
      selectElement(state.selectedId);
    } else {
      clearSelection();
    }
    refreshStageImage();
  }

  function refreshStageImage() {
    if (!state.canvasId) return;
    state.rev++;
    const q = new URLSearchParams({
      bg: state.bg,
      ids: state.showIds ? "1" : "0",
      guides: state.showGuides ? "1" : "0",
      r: String(state.rev),
    });
    if (state.previewState) q.set("state", state.previewState);
    if (state.simMode) q.set("sim", state.simMode);
    if (state.langMode) q.set("lang", state.langMode);
    if (state.hiddenLayers.size) q.set("hide", Array.from(state.hiddenLayers).join(","));
    if (Object.keys(state.liveData).length) q.set("data", JSON.stringify(state.liveData));
    if (state.animName) { q.set("anim", state.animName); q.set("t", String(state.animT)); }
    $("stage-img").src = `/api/render/${encodeURIComponent(state.canvasId)}?${q}`;
  }

  function renderLayers(layers) {
    const box = $("layers-list");
    if (!layers.length) {
      box.innerHTML = '<div class="list-item"><span>base</span><span class="list-meta">default</span></div>';
      return;
    }
    box.innerHTML = layers.map((ly) => {
      const checked = !state.hiddenLayers.has(ly.name);
      return `<label class="list-item"><span>${ly.name}</span><input type="checkbox" data-layer="${ly.name}" ${checked ? "checked" : ""} /></label>`;
    }).join("");
    box.querySelectorAll("input[data-layer]").forEach((cb) => {
      cb.onchange = () => {
        if (cb.checked) state.hiddenLayers.delete(cb.dataset.layer);
        else state.hiddenLayers.add(cb.dataset.layer);
        refreshStageImage();
      };
    });
  }

  function renderElementsList(elements) {
    const box = $("elements-list");
    const q = (state.elFilter || "").trim().toLowerCase();
    const list = q ? elements.filter((e) => e.id.toLowerCase().includes(q) || e.type.toLowerCase().includes(q)) : elements;
    if (!list.length) {
      box.innerHTML = `<div class="empty-note">${elements.length ? "No matching elements." : "Empty canvas — open Create or Materials to start building."}</div>`;
      return;
    }
    box.innerHTML = list.slice().reverse().map((el) => {
      const on = state.selectedIds.has(el.id) ? " on" : "";
      return `<button class="list-item${on}" type="button" data-eid="${el.id}"><span>${el.id}</span><span class="list-meta">${el.type}</span></button>`;
    }).join("");
    box.querySelectorAll("[data-eid]").forEach((row) => {
      row.onclick = (e) => selectElement(row.dataset.eid, e.shiftKey);
    });
  }

  function clearSelection() {
    state.selectedId = null;
    state.selectedIds.clear();
    const sb = $("sel-box");
    sb.style.display = "none";
    sb.style.transform = "";
    $("inspect-empty").hidden = false;
    $("inspect-form").hidden = true;
    $("elements-list").querySelectorAll("[data-eid]").forEach((n) => n.classList.remove("on"));
  }

  function selectionUnionBox() {
    if (!state.canvas || !state.selectedIds.size) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const el of state.canvas.elements || []) {
      if (!state.selectedIds.has(el.id) || !el.bbox_xywh) continue;
      const [bx, by, bw, bh] = el.bbox_xywh;
      x0 = Math.min(x0, bx); y0 = Math.min(y0, by);
      x1 = Math.max(x1, bx + bw); y1 = Math.max(y1, by + bh);
    }
    if (!isFinite(x0)) return null;
    return [x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0)];
  }

  function positionSelBox(box, label) {
    const sb = $("sel-box");
    if (!box || !state.canvas || !state.canvas.width || !state.canvas.height) { sb.style.display = "none"; return; }
    const [bx, by, bw, bh] = box;
    sb.style.display = "block";
    sb.style.transform = "";
    sb.style.left = `${(bx / state.canvas.width) * 100}%`;
    sb.style.top = `${(by / state.canvas.height) * 100}%`;
    sb.style.width = `${(bw / state.canvas.width) * 100}%`;
    sb.style.height = `${(bh / state.canvas.height) * 100}%`;
    $("sel-tag").textContent = label || `${state.selectedId} · ${Math.round(bw)}×${Math.round(bh)}`;
    const showHandles = state.selectedIds.size === 1;
    sb.querySelectorAll(".rh").forEach((h) => { h.style.display = showHandles ? "block" : "none"; });
  }

  function selectElement(eid, additive = false) {
    if (!state.canvas || !state.canvas.raw_elements[eid]) return;
    if (additive) {
      if (state.selectedIds.has(eid) && state.selectedIds.size > 1) state.selectedIds.delete(eid);
      else state.selectedIds.add(eid);
      state.selectedId = state.selectedIds.has(eid) ? eid : Array.from(state.selectedIds)[0];
    } else {
      state.selectedIds = new Set([eid]);
      state.selectedId = eid;
    }
    const raw = state.canvas.raw_elements[state.selectedId];
    const row = state.canvas.elements.find((e) => e.id === state.selectedId);
    $("elements-list").querySelectorAll("[data-eid]").forEach((n) => n.classList.toggle("on", state.selectedIds.has(n.dataset.eid)));

    const ubox = selectionUnionBox();
    if (ubox) {
      const tag = state.selectedIds.size > 1
        ? `${state.selectedIds.size} selected · ${Math.round(ubox[2])}×${Math.round(ubox[3])}`
        : `${state.selectedId} · ${Math.round(ubox[2])}×${Math.round(ubox[3])}`;
      positionSelBox(ubox, tag);
    }

    $("inspect-empty").hidden = true;
    $("inspect-form").hidden = false;
    $("ins-id").textContent = state.selectedIds.size > 1 ? `${state.selectedIds.size} elements` : state.selectedId;
    $("ins-type").textContent = state.selectedIds.size > 1 ? Array.from(state.selectedIds).slice(0, 3).join(", ") : raw.type;
    const b = (row && row.bbox_xywh) || [0, 0, 0, 0];
    $("ins-x").value = Math.round(raw.x ?? raw.cx ?? b[0]);
    $("ins-y").value = Math.round(raw.y ?? raw.cy ?? b[1]);
    $("ins-w").value = Math.round(raw.width ?? (raw.rx ? raw.rx * 2 : b[2]));
    $("ins-h").value = Math.round(raw.height ?? (raw.ry ? raw.ry * 2 : b[3]));
    $("ins-rad").value = typeof raw.radius === "number" ? raw.radius : 0;
    $("ins-rot").value = raw.rotation || 0;
    $("ins-text").value = raw.text ?? raw.label ?? "";
    const st = (typeof raw.style === "object" && raw.style) ? raw.style : {};
    const fillVal = typeof raw.fill === "string" ? raw.fill : (typeof st.fill === "string" ? st.fill : "");
    $("ins-fill").value = fillVal;
    if (/^#[0-9a-f]{6}$/i.test(fillVal)) $("ins-fill-pick").value = fillVal;
    $("ins-op").value = st.opacity ?? 1;
    const strokeObj = raw.stroke || st.stroke || {};
    $("ins-stroke").value = typeof strokeObj === "string" ? strokeObj : (typeof strokeObj.color === "string" ? strokeObj.color : "");
    $("ins-sw").value = (typeof strokeObj === "object" && strokeObj.width) ? strokeObj.width : "";
    const matName = typeof st.material === "string" ? st.material : (st.material && st.material.name) || "";
    $("ins-mat").value = matName;
    const pbr = st.pbr || {};
    $("pbr-prof").value = pbr.profile || "";
    $("pbr-met").value = pbr.metallic ?? 0.85; $("pbr-met-v").textContent = Number($("pbr-met").value).toFixed(2);
    $("pbr-rgh").value = pbr.roughness ?? 0.22; $("pbr-rgh-v").textContent = Number($("pbr-rgh").value).toFixed(2);
    $("pbr-cc").value = pbr.clearcoat ?? 0; $("pbr-cc-v").textContent = Number($("pbr-cc").value).toFixed(2);
    $("pbr-bev").value = pbr.bevel_size ?? 6; $("pbr-bev-v").textContent = Number($("pbr-bev").value).toFixed(1);
    $("pbr-wear").value = pbr.wear ?? 0.2; $("pbr-wear-v").textContent = Number($("pbr-wear").value).toFixed(2);
    const persp = st.perspective || raw.perspective || {};
    $("ins-ry").value = persp.rotate_y || 0; $("ins-ry-v").textContent = `${persp.rotate_y || 0}°`;
    $("ins-rx").value = persp.rotate_x || 0; $("ins-rx-v").textContent = `${persp.rotate_x || 0}°`;
    $("ins-vc").value = persp.visor_curve || 0; $("ins-vc-v").textContent = String(persp.visor_curve || 0);
  }

  function renderFramesGrid(presets) {
    const g = $("frames-grid");
    if (g.children.length) return;
    g.innerHTML = presets.map((p) => `<button class="chip" data-frame="${p}">${p.replace(/_/g, " ")}</button>`).join("");
    g.querySelectorAll("[data-frame]").forEach((btn) => {
      btn.onclick = () => addFramePreset(btn.dataset.frame);
    });
  }

  async function addFramePreset(preset) {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    const c = state.canvas;
    const pad = Math.round(Math.min(c.width, c.height) * 0.06);
    await apiOp("add_frame", {
      canvas: state.canvasId,
      x: pad, y: pad,
      width: Math.max(160, c.width - pad * 2),
      height: Math.max(120, c.height - pad * 2),
      preset,
      title: preset.replace(/_/g, " ").toUpperCase(),
    });
    toast(`Added ${preset} frame`, "ok");
    await loadCanvas(state.canvasId);
  }

  function renderIconsGrid(allIcons, filter) {
    const q = (filter || "").trim().toLowerCase();
    const list = q ? allIcons.filter((i) => i.name.includes(q) || i.tags.some((t) => t.includes(q))) : allIcons;
    $("icon-count").textContent = String(list.length);
    const g = $("icon-grid");
    g.innerHTML = list.slice(0, 142).map((ic) => {
      const fill = ic.mode === "fill" ? "currentColor" : "none";
      const stroke = ic.mode === "fill" ? "none" : "currentColor";
      return `<button class="ico-btn" data-icon="${ic.name}" title="${ic.name}" aria-label="Insert ${ic.name} icon"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="${ic.d}" fill="${fill}" stroke="${stroke}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`;
    }).join("");
    g.querySelectorAll("[data-icon]").forEach((btn) => {
      btn.onclick = () => insertIcon(btn.dataset.icon);
    });
  }

  async function insertIcon(name) {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    const c = state.canvas;
    const res = await apiOp("add_icon", {
      canvas: state.canvasId,
      name,
      x: Math.round(c.width * 0.5 - 22),
      y: Math.round(c.height * 0.5 - 22),
      size: 44,
      color: "#e89b3c",
    });
    toast(`Placed icon '${name}'`, "ok");
    await loadCanvas(state.canvasId);
    if (res && res.id) selectElement(res.id);
  }

  async function applyMaterial(mat) {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    if (state.selectedId) {
      await apiOp("update_element", { canvas: state.canvasId, id: state.selectedId, props: { style: { material: mat } } });
      toast(`Applied '${mat}' PBR to ${state.selectedId}`, "ok");
      await loadCanvas(state.canvasId);
    } else {
      const c = state.canvas;
      const res = await apiOp("add_rect", {
        canvas: state.canvasId,
        x: Math.round(c.width * 0.5 - 100), y: Math.round(c.height * 0.5 - 44),
        width: 200, height: 88, radius: 14, style: { material: mat },
      });
      toast(`Created '${mat}' PBR panel`, "ok");
      await loadCanvas(state.canvasId);
      if (res && res.id) selectElement(res.id);
    }
  }

  function renderMaterialsGallery(groups, filter) {
    const q = (filter || "").trim().toLowerCase();
    const host = $("materials-gallery");
    let html = "";
    for (const [gname, mats] of Object.entries(groups)) {
      const kept = q ? mats.filter((m) => m.includes(q)) : mats;
      if (!kept.length) continue;
      html += `<div class="mat-group-title">${gname}</div><div class="mat-grid">` +
        kept.map((m) => `<button class="mat-card" data-mat="${m}" title="Apply ${m} PBR material"><img src="/api/swatch/${encodeURIComponent(m)}" loading="lazy" alt="${m}"/><span>${m}</span></button>`).join("") +
        "</div>";
    }
    host.innerHTML = html || '<div class="empty-note">No matching materials.</div>';
    host.querySelectorAll("[data-mat]").forEach((btn) => {
      btn.onclick = () => applyMaterial(btn.dataset.mat);
    });
  }

  function renderOpsList(ops, filter) {
    const q = (filter || "").trim().toLowerCase();
    const list = q ? ops.filter((o) => o.name.includes(q) || o.category.includes(q) || o.summary.toLowerCase().includes(q)) : ops;
    $("ops-count").textContent = String(list.length);
    const box = $("ops-list");
    box.innerHTML = list.map((o) =>
      `<button class="list-item" type="button" data-op="${o.name}" title="${o.summary.replace(/"/g, "&quot;")}"><span>${o.name}</span><span class="list-meta">${o.category}</span></button>`
    ).join("");
    box.querySelectorAll("[data-op]").forEach((row) => {
      row.onclick = () => {
        $("runner-op-name").textContent = row.dataset.op;
        $("runner-args").value = JSON.stringify(state.canvasId ? { canvas: state.canvasId } : {}, null, 2);
      };
    });
  }

  function renderThemeTokens(theme) {
    const cols = (theme && theme.colors) || {};
    const box = $("token-swatches");
    const entries = Object.entries(cols);
    box.innerHTML = entries.length
      ? entries.map(([k, v]) => `<div class="tok-item"><span class="tok-sw" style="background:${v}"></span><div><div class="mono">$${k}</div><div class="list-meta">${v}</div></div></div>`).join("")
      : '<div class="empty-note">Pick a Style Preset or generate a palette above.</div>';
  }

  function renderBindingsAndAnim(c) {
    const bp = $("bindings-panel");
    const entries = Object.entries(c.data || {});
    if (!entries.length) {
      bp.innerHTML = '<div class="empty-note">No data variables yet. Add bound widgets or use set_binding.</div>';
    } else {
      bp.innerHTML = entries.map(([k, v]) => {
        const cur = (k in state.liveData) ? state.liveData[k] : v;
        if (typeof v === "boolean") {
          return `<label class="list-item"><span>${k}</span><input type="checkbox" data-dk="${k}" ${cur ? "checked" : ""} /></label>`;
        }
        if (typeof v === "number") {
          const mx = Math.max(100, Math.abs(v) * 2);
          return `<div class="sub-box"><div class="kv-row"><span class="mono">${k}</span><strong class="mono" id="dv-${k}">${cur}</strong></div><input type="range" min="0" max="${mx}" step="1" value="${cur}" data-dk="${k}" style="width:100%;accent-color:var(--amber)"/></div>`;
        }
        return `<label class="fld"><span>${k}</span><input type="text" class="inp" value="${String(cur).replace(/"/g, "&quot;")}" data-dk="${k}" /></label>`;
      }).join("");
      bp.querySelectorAll("[data-dk]").forEach((inp) => {
        inp.oninput = () => {
          const k = inp.dataset.dk;
          state.liveData[k] = inp.type === "checkbox" ? inp.checked : (inp.type === "range" ? Number(inp.value) : inp.value);
          const sp = $(`dv-${k}`);
          if (sp) sp.textContent = String(state.liveData[k]);
          refreshStageImage();
        };
      });
    }

    const ap = $("anim-panel");
    const anims = c.animations || [];
    if (!anims.length) {
      ap.innerHTML = '<div class="empty-note">No animations on this canvas yet.</div>';
    } else {
      const curA = anims.find((a) => a.name === state.animName) || anims[0];
      ap.innerHTML = `<select id="an-sel" class="sel full"><option value="">(Static frame)</option>${anims.map((a) => `<option value="${a.name}"${a.name === state.animName ? " selected" : ""}>${a.name} (${a.duration}s)</option>`).join("")}</select>` +
        `<div class="sub-box" style="margin-top:7px"><div class="kv-row"><span>Timeline</span><strong class="mono" id="at-v">${state.animT.toFixed(2)}s</strong></div><input id="an-t" type="range" min="0" max="${curA.duration}" step="0.05" value="${state.animT}" style="width:100%;accent-color:var(--amber)"/></div>` +
        `<button class="btn full" id="an-play">${state.playTimer ? "Pause" : "Play Preview"}</button>`;
      $("an-sel").onchange = (e) => { state.animName = e.target.value; state.animT = 0; renderBindingsAndAnim(c); refreshStageImage(); };
      $("an-t").oninput = (e) => { if (!state.animName) state.animName = anims[0].name; state.animT = Number(e.target.value); $("at-v").textContent = `${state.animT.toFixed(2)}s`; refreshStageImage(); };
      $("an-play").onclick = () => {
        if (state.playTimer) { clearInterval(state.playTimer); state.playTimer = null; $("an-play").textContent = "Play Preview"; return; }
        if (!state.animName) state.animName = anims[0].name;
        $("an-play").textContent = "Pause";
        const dur = curA.duration || 1;
        state.playTimer = setInterval(() => {
          state.animT = (state.animT + 0.1) % dur;
          if ($("an-t")) $("an-t").value = String(state.animT);
          if ($("at-v")) $("at-v").textContent = `${state.animT.toFixed(2)}s`;
          refreshStageImage();
        }, 140);
      };
    }
  }

  function renderVersions(versions) {
    const box = $("versions-list");
    const dSel = $("diff-ver-sel");
    if (!versions.length) {
      box.innerHTML = '<div class="empty-note">Save snapshots before big edits to compare with Visual Diff.</div>';
      dSel.innerHTML = '<option value="">No snapshots yet</option>';
      return;
    }
    box.innerHTML = versions.map((v) =>
      `<div class="list-item"><div><div class="mono">${v.name}</div><div class="list-meta">${v.saved}</div></div><button class="mini-btn" data-restore="${v.name}">Restore</button></div>`
    ).join("");
    box.querySelectorAll("[data-restore]").forEach((btn) => {
      btn.onclick = async () => {
        await apiOp("canvas_version", { canvas: state.canvasId, action: "restore", name: btn.dataset.restore });
        toast(`Restored snapshot '${btn.dataset.restore}'`, "ok");
        await loadCanvas(state.canvasId);
      };
    });
    dSel.innerHTML = versions.map((v) => `<option value="${v.name}">${v.name} (${v.saved})</option>`).join("");
  }

  function renderActivity(items) {
    const box = $("activity-list");
    box.innerHTML = (items || []).map((a) =>
      `<div class="act-row"><span class="list-meta">${a.ts}</span><span class="act-src ${a.source}">${a.source}</span><span>${a.operation}</span><span class="list-meta">${a.duration_ms}ms</span>${a.status === "error" ? `<span class="act-err">${a.detail}</span>` : ""}</div>`
    ).join("");
  }

  async function refreshActivity() {
    const r = await fetch("/api/activity");
    const d = await r.json();
    renderActivity(d.activity || []);
  }

  // Starter Template Builders (Tactical Sci-Fi HUD, Fantasy RPG Forge, Desktop/SaaS App)
  async function loadStarter(kind) {
    const suffix = (base) => {
      const existing = new Set(((state.boot && state.boot.canvases) || []).map((c) => c.id));
      if (!existing.has(base)) return base;
      let i = 2;
      while (existing.has(`${base}_${i}`)) i++;
      return `${base}_${i}`;
    };

    if (kind === "rpg") {
      await apiOp("set_theme", { style_preset: "dark_fantasy", quality: "aaa" });
      const cid = (await apiOp("create_canvas", { name: suffix("rpg_forge"), width: 720, height: 460, background: "#120c08" })).canvas;
      await apiOp("add_frame", { canvas: cid, x: 18, y: 18, width: 684, height: 424, preset: "rpg_gold", title: "BLACKSMITH FORGE" });
      await apiOp("batch", {
        canvas: cid,
        operations: [
          { op: "add_rect", id: "slot_gold", x: 86, y: 106, width: 164, height: 164, radius: 18, style: { material: "hammered_gold" } },
          { op: "add_rect", id: "slot_gem", x: 278, y: 106, width: 164, height: 164, radius: 18, style: { material: "gem" } },
          { op: "add_rect", id: "slot_jade", x: 470, y: 106, width: 164, height: 164, radius: 18, style: { material: "jade" } },
          { op: "add_icon", id: "ic_sword", name: "sword", x: 132, y: 152, size: 72, color: "#fff7ed" },
          { op: "add_icon", id: "ic_crown", name: "crown", x: 324, y: 152, size: 72, color: "#fff7ed" },
          { op: "add_icon", id: "ic_shield", name: "shield", x: 516, y: 152, size: 72, color: "#ecfdf5" },
          { op: "add_rect", id: "btn_forge", x: 86, y: 318, width: 548, height: 64, radius: 12, style: { material: "obsidian", stroke: { color: "#f4b054", width: 2 } } },
          { op: "add_text", id: "btn_lbl", text: "FORGE LEGENDARY BLADE · 450 GOLD", x: 360, y: 350, anchor: "center", size: 20, weight: 700, font: "Cinzel", color: "#fef08a", style: { shadow: { color: "#000@0.9", blur: 6, dy: 2 } } },
        ],
      });
      await apiOp("canvas_version", { canvas: cid, action: "save", name: "v1", note: "Initial RPG Forge" });
      toast("Loaded Fantasy RPG Forge starter", "ok");
      await bootstrap(cid);
      return;
    }

    if (kind === "saas") {
      await apiOp("set_theme", { style_preset: "web_saas", quality: "standard" });
      const cid = (await apiOp("create_canvas", { name: suffix("desktop_app"), width: 960, height: 540, background: "#0f141e" })).canvas;
      await apiOp("set_binding", { canvas: cid, data: { gpu_boost: true, quality_lvl: 85, target: "WPF (.NET 8)" } });
      await apiOp("batch", {
        canvas: cid,
        operations: [
          { op: "add_rect", id: "shell", x: 24, y: 24, width: 912, height: 492, radius: 14, fill: "#141925", stroke: { color: "#2b3346", width: 1.5 } },
          { op: "add_rect", id: "hdr", x: 24, y: 24, width: 912, height: 56, radius: [14, 14, 0, 0], fill: "#1a2030" },
          { op: "add_text", id: "hdr_t", text: "Workspace Settings · Desktop & Web", x: 48, y: 43, size: 18, weight: 700, font: "Inter", color: "#f1f5f9" },
          { op: "add_rect", id: "cta_bg", x: 796, y: 38, width: 116, height: 30, radius: 7, fill: "#e89b3c" },
          { op: "add_text", id: "cta_t", text: "Save Profile", x: 854, y: 53, anchor: "center", size: 12.5, weight: 700, font: "Inter", color: "#12100c" },
          { op: "add_input", id: "inp_proj", x: 52, y: 120, width: 390, height: 42, label: "Project Name", value: "AuroraEngineUI", placeholder: "Enter project name..." },
          { op: "add_dropdown", id: "dd_target", x: 52, y: 204, width: 390, height: 42, label: "Delivery Target", options: ["WPF (.NET 8)", "Avalonia", "Qt 6 QML", "React TSX"], selected: "WPF (.NET 8)", bind: "target" },
          { op: "add_slider", id: "sl_scale", x: 52, y: 288, width: 390, height: 28, label: "Render Quality (%)", value: 85, bind: "quality_lvl" },
          { op: "add_toggle", id: "tg_gpu", x: 52, y: 356, width: 52, height: 28, checked: true, label: "Hardware GPU Acceleration", bind: "gpu_boost" },
          { op: "add_scroll", id: "sc_exports", x: 484, y: 112, width: 424, height: 372, items: [
            { title: "SettingsView.xaml", subtitle: "C# .NET 8 WPF + INotifyPropertyChanged", badge: "XAML" },
            { title: "MainPanel.qml", subtitle: "C++ Qt 6 Quick Controls 2", badge: "QML" },
            { title: "Dashboard.tsx", subtitle: "React 19 + Tailwind CSS + Gamepad API", badge: "TSX" },
            { title: "WBP_Settings_build_umg.py", subtitle: "Unreal Engine 5.8 WidgetBlueprint", badge: "UMG" },
          ] },
        ],
      });
      await apiOp("canvas_version", { canvas: cid, action: "save", name: "v1", note: "Initial Desktop App" });
      toast("Loaded Desktop & SaaS App starter", "ok");
      await bootstrap(cid);
      return;
    }

    // Default: Tactical Sci-Fi HUD
    await apiOp("set_theme", { style_preset: "scifi", quality: "advanced" });
    const cid = (await apiOp("create_canvas", { name: suffix("tactical_hud"), width: 960, height: 540, background: "#070b14" })).canvas;
    await apiOp("set_binding", { canvas: cid, data: { shield: 84, volume: 72, autopilot: true, mode: "Tactical" } });
    await apiOp("add_frame", { canvas: cid, x: 24, y: 20, width: 912, height: 500, preset: "scifi_hud", title: "ORBITAL TELEMETRY" });
    await apiOp("batch", {
      canvas: cid,
      operations: [
        { op: "add_icon", name: "shield", x: 64, y: 84, size: 34, color: "#22d3ee", id: "ico_shield" },
        { op: "add_text", text: "SHIELD INTEGRITY", x: 112, y: 88, size: 13, weight: 700, color: "#7dd3fc", id: "lbl_sh" },
        { op: "add_rect", x: 112, y: 110, width: 320, height: 14, radius: 7, fill: "#1e293b", id: "sh_bg" },
        { op: "add_rect", x: 112, y: 110, width: 268, height: 14, radius: 7, style: { material: "energy_shield" }, id: "sh_fill" },
        { op: "add_slider", x: 64, y: 180, width: 368, height: 28, min: 0, max: 100, value: 72, label: "Thruster Output", bind: "volume", id: "sl_thrust" },
        { op: "add_toggle", x: 64, y: 244, width: 52, height: 28, checked: true, variant: "switch", label: "Auto-Stabilizer", bind: "autopilot", id: "tg_auto" },
        { op: "add_dropdown", x: 64, y: 316, width: 260, height: 40, options: ["Stealth", "Tactical", "Overdrive"], selected: "Tactical", label: "Flight Profile", bind: "mode", id: "dd_mode" },
        { op: "add_input", x: 64, y: 400, width: 368, height: 42, placeholder: "Enter waypoint...", value: "SECTOR-7G", label: "Navigation Target", id: "inp_nav" },
        { op: "add_scroll", x: 500, y: 92, width: 396, height: 350, items: [
          { title: "Reactor Core", subtitle: "Cook-Torrance GGX · 98.4% Nominal", badge: "OK" },
          { title: "Ion Thrusters", subtitle: "Vector nozzles calibrated", badge: "72%" },
          { title: "Nav Beacon", subtitle: "Long-range telemetry locked", badge: "LOCK" },
          { title: "Hull Plating", subtitle: "Carbon twill composite", badge: "100%" },
          { title: "Cryo Coolant", subtitle: "Thermal loop steady", badge: "312K" },
        ], id: "sc_sys" },
      ],
    });
    await apiOp("set_binding", { canvas: cid, target: "sh_fill", property: "width", expr: "clamp(shield / 100, 0, 1) * 320" });
    await apiOp("canvas_version", { canvas: cid, action: "save", name: "v1", note: "Initial starter HUD" });
    toast("Loaded Tactical Sci-Fi HUD starter", "ok");
    await bootstrap(cid);
  }

  // Command Palette (Ctrl+K)
  function buildCmdkCatalog() {
    const items = [
      { label: "New Blank Canvas", cat: "Action", run: () => openModal("modal-new") },
      { label: "Export & Engine Delivery", cat: "Action", run: () => $("btn-export").click() },
      { label: "Run WCAG & Layout Audit", cat: "Action", run: () => runAudit() },
      { label: "Toggle Dark / Light Studio Theme", cat: "Action", run: () => $("btn-theme-toggle").click() },
      { label: "Save Version Snapshot", cat: "Action", run: () => $("btn-save-ver").click() },
      { label: "Open Pixel Visual Diff", cat: "Action", run: () => openModal("modal-diff") },
      { label: "Multi-Device Responsive Matrix", cat: "Action", run: () => $("btn-devices").click() },
      { label: "Explore Visual Variations", cat: "Action", run: () => $("btn-variations").click() },
      { label: "Import CSS / Tailwind Tokens", cat: "Action", run: () => { document.querySelector('.rtab[data-right="theme"]').click(); $("css-tokens-inp").focus(); } },
      { label: "Workspace, GPU & MCP Settings", cat: "Action", run: () => openModal("modal-settings") },
      { label: "Load Starter: Tactical Sci-Fi HUD", cat: "Starter", run: () => loadStarter("tactical") },
      { label: "Load Starter: Fantasy RPG Forge", cat: "Starter", run: () => loadStarter("rpg") },
      { label: "Load Starter: Desktop & SaaS App", cat: "Starter", run: () => loadStarter("saas") },
    ];
    if (state.boot) {
      for (const c of state.boot.canvases || []) {
        items.push({ label: `Switch Canvas: ${c.id} (${c.width}×${c.height})`, cat: "Canvas", run: () => { $("canvas-sel").value = c.id; loadCanvas(c.id); } });
      }
      for (const f of state.boot.frame_presets || []) {
        items.push({ label: `Add Frame: ${f}`, cat: "Frame", run: () => addFramePreset(f) });
      }
      for (const m of (state.boot.materials && state.boot.materials.all) || []) {
        items.push({ label: `Apply PBR Material: ${m}`, cat: "Material", run: () => applyMaterial(m) });
      }
      for (const ic of state.boot.icons || []) {
        items.push({ label: `Insert Icon: ${ic.name}`, cat: "Icon", keywords: ic.tags.join(" "), run: () => insertIcon(ic.name) });
      }
      for (const op of state.boot.operations || []) {
        items.push({
          label: `Tool: ${op.name}`,
          cat: op.category,
          keywords: op.summary,
          run: () => {
            document.querySelector('.rtab[data-left="tools"]').click();
            $("runner-op-name").textContent = op.name;
            $("runner-args").value = JSON.stringify(state.canvasId ? { canvas: state.canvasId } : {}, null, 2);
            $("runner-args").focus();
          },
        });
      }
    }
    return items;
  }

  function renderCmdk(filter = "") {
    const q = filter.trim().toLowerCase();
    const all = buildCmdkCatalog();
    const matched = q
      ? all.filter((it) => it.label.toLowerCase().includes(q) || it.cat.toLowerCase().includes(q) || (it.keywords || "").toLowerCase().includes(q))
      : all.slice(0, 14);
    state.cmdkItems = matched.slice(0, 24);
    state.cmdkIdx = 0;
    const box = $("cmdk-list");
    if (!state.cmdkItems.length) {
      box.innerHTML = '<div class="empty-note">No matching commands, materials, or icons.</div>';
      return;
    }
    box.innerHTML = state.cmdkItems.map((it, idx) =>
      `<button class="cmdk-item${idx === 0 ? " active" : ""}" role="option" aria-selected="${idx === 0}" data-ci="${idx}"><span>${it.label}</span><span class="cmdk-cat">${it.cat}</span></button>`
    ).join("");
    box.querySelectorAll("[data-ci]").forEach((btn) => {
      btn.onclick = () => executeCmdk(Number(btn.dataset.ci));
    });
  }

  function executeCmdk(idx) {
    const item = state.cmdkItems[idx];
    if (!item) return;
    closeModal("modal-cmdk", false);
    item.run();
  }

  $("btn-cmdk").onclick = () => {
    $("cmdk-input").value = "";
    renderCmdk("");
    openModal("modal-cmdk", $("btn-cmdk"));
  };
  $("cmdk-input").oninput = (e) => renderCmdk(e.target.value);
  $("cmdk-input").onkeydown = (e) => {
    if (!state.cmdkItems.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      state.cmdkIdx = (state.cmdkIdx + 1) % state.cmdkItems.length;
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      state.cmdkIdx = (state.cmdkIdx - 1 + state.cmdkItems.length) % state.cmdkItems.length;
    } else if (e.key === "Enter") {
      e.preventDefault();
      executeCmdk(state.cmdkIdx);
      return;
    } else {
      return;
    }
    $("cmdk-list").querySelectorAll("[data-ci]").forEach((n, i) => {
      n.classList.toggle("active", i === state.cmdkIdx);
      n.setAttribute("aria-selected", String(i === state.cmdkIdx));
      if (i === state.cmdkIdx) n.scrollIntoView({ block: "nearest" });
    });
  };

  // Tabs & Responsive Drawers
  document.querySelectorAll(".rtab[data-left]").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".rtab[data-left]").forEach((b) => {
        const on = b === btn;
        b.classList.toggle("on", on);
        b.setAttribute("aria-selected", String(on));
      });
      document.querySelectorAll("#dock-left .panel").forEach((p) => p.classList.toggle("on", p.id === `left-${btn.dataset.left}`));
      moveTabInk(".rtab[data-left]", "ink-left", btn);
    };
  });
  document.querySelectorAll(".rtab[data-right]").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".rtab[data-right]").forEach((b) => {
        const on = b === btn;
        b.classList.toggle("on", on);
        b.setAttribute("aria-selected", String(on));
      });
      document.querySelectorAll("#dock-right .panel").forEach((p) => p.classList.toggle("on", p.id === `right-${btn.dataset.right}`));
      moveTabInk(".rtab[data-right]", "ink-right", btn);
    };
  });

  $("btn-toggle-left").onclick = () => {
    const open = $("dock-left").classList.toggle("open");
    $("dock-right").classList.remove("open");
    $("btn-toggle-left").setAttribute("aria-expanded", String(open));
    $("btn-toggle-right").setAttribute("aria-expanded", "false");
  };
  $("btn-toggle-right").onclick = () => {
    const open = $("dock-right").classList.toggle("open");
    $("dock-left").classList.remove("open");
    $("btn-toggle-right").setAttribute("aria-expanded", String(open));
    $("btn-toggle-left").setAttribute("aria-expanded", "false");
  };
  document.querySelectorAll("[data-close]").forEach((b) => { b.onclick = () => closeModal(b.dataset.close); });

  // Top Bar & Starters
  $("canvas-sel").onchange = (e) => { if (e.target.value) loadCanvas(e.target.value); };
  $("btn-new-canvas").onclick = (e) => openModal("modal-new", e.currentTarget);
  $("btn-empty-new").onclick = (e) => openModal("modal-new", e.currentTarget);
  $("btn-shortcuts").onclick = (e) => openModal("modal-shortcuts", e.currentTarget);
  $("btn-dup-canvas").onclick = async () => {
    if (!state.canvasId) return toast("No canvas to duplicate", "err");
    const newName = `${state.canvasId}_copy_${Date.now().toString().slice(-3)}`;
    const res = await apiOp("duplicate_canvas", { canvas: state.canvasId, new_name: newName });
    toast(`Duplicated canvas as '${res.canvas}'`, "ok");
    await bootstrap(res.canvas);
  };

  document.querySelectorAll("[data-starter]").forEach((btn) => {
    btn.onclick = () => loadStarter(btn.dataset.starter);
  });
  $("btn-empty-demo").onclick = () => loadStarter("tactical");

  document.querySelectorAll("[data-size]").forEach((b) => {
    b.onclick = () => { const [w, h] = b.dataset.size.split(","); $("new-w").value = w; $("new-h").value = h; };
  });
  $("btn-create-confirm").onclick = async () => {
    const name = $("new-name").value.trim() || "canvas";
    const width = Number($("new-w").value) || 960;
    const height = Number($("new-h").value) || 540;
    const bg = $("new-bg").value.trim() || null;
    const res = await apiOp("create_canvas", { name, width, height, background: bg });
    closeModal("modal-new", false);
    toast(`Created canvas '${res.canvas}'`, "ok");
    await bootstrap(res.canvas);
  };

  $("btn-undo").onclick = async () => { if (state.canvasId) { await apiOp("undo", { canvas: state.canvasId }); await loadCanvas(state.canvasId); } };
  $("btn-redo").onclick = async () => { if (state.canvasId) { await apiOp("redo", { canvas: state.canvasId }); await loadCanvas(state.canvasId); } };
  $("style-sel").onchange = async (e) => {
    await apiOp("set_theme", { style_preset: e.target.value, quality: $("quality-sel").value });
    if (state.canvasId) await apiOp("update_canvas", { canvas: state.canvasId, style_preset: e.target.value });
    toast(`Style preset: ${e.target.value}`, "ok");
    await bootstrap(state.canvasId);
  };
  $("quality-sel").onchange = async (e) => {
    await apiOp("set_theme", { quality: e.target.value });
    if (state.canvasId) await apiOp("update_canvas", { canvas: state.canvasId, quality: e.target.value });
    toast(`Quality tier: ${e.target.value}`, "ok");
    await loadCanvas(state.canvasId);
  };

  // Primitives & Screenshot Import
  document.querySelectorAll("[data-create]").forEach((btn) => {
    btn.onclick = async () => {
      if (!state.canvasId) return toast("Create a canvas first", "err");
      const kind = btn.dataset.create;
      const c = state.canvas;
      const cx = Math.round(c.width * 0.5), cy = Math.round(c.height * 0.5);
      const defs = {
        rect: ["add_rect", { canvas: state.canvasId, x: cx - 100, y: cy - 40, width: 200, height: 80, radius: 10, fill: "#1e293b", stroke: { color: "#e89b3c", width: 1.5 } }],
        ellipse: ["add_ellipse", { canvas: state.canvasId, cx, cy, rx: 46, ry: 46, style: { material: "gold" } }],
        text: ["add_text", { canvas: state.canvasId, text: "HEADING", x: cx, y: cy, anchor: "center", size: 28, weight: 700, color: "#f8fafc" }],
        arc: ["add_arc", { canvas: state.canvasId, cx, cy, radius: 70, start_angle: 135, end_angle: 360, thickness: 10, color: "#e89b3c" }],
        input: ["add_input", { canvas: state.canvasId, x: cx - 130, y: cy - 21, width: 260, height: 42, placeholder: "Type here...", label: "Input" }],
        scroll: ["add_scroll", { canvas: state.canvasId, x: cx - 140, y: cy - 100, width: 280, height: 200, items: [{ title: "Item Alpha", subtitle: "Ready", badge: "01" }, { title: "Item Beta", subtitle: "Active", badge: "02" }] }],
        slider: ["add_slider", { canvas: state.canvasId, x: cx - 120, y: cy - 14, width: 240, height: 28, value: 65, label: "Level" }],
        toggle: ["add_toggle", { canvas: state.canvasId, x: cx - 40, y: cy - 14, checked: true, label: "Enabled" }],
        dropdown: ["add_dropdown", { canvas: state.canvasId, x: cx - 110, y: cy - 20, width: 220, height: 40, options: ["Low", "High", "Ultra"], selected: "High", label: "Preset" }],
      };
      const [op, args] = defs[kind];
      const res = await apiOp(op, args);
      toast(`Added ${kind}`, "ok");
      await loadCanvas(state.canvasId);
      if (res && res.id) selectElement(res.id);
    };
  });

  $("btn-import-ss").onclick = $("btn-empty-ss").onclick = () => $("ss-file-input").click();
  $("ss-file-input").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      toast("Analyzing screenshot with OpenCV...", "info");
      const r = await fetch("/api/import_screenshot_upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_base64: reader.result, filename: file.name }),
      });
      const d = await r.json();
      if (!d.ok) return toast(d.error, "err");
      toast(`Reconstructed ${d.result.shapes_created} shapes + ${d.result.texts_created} texts`, "ok");
      await bootstrap(d.result.canvas);
    };
    reader.readAsDataURL(file);
  };

  $("btn-add-layer").onclick = async () => {
    if (!state.canvasId) return;
    const name = `layer_${(state.canvas.layers || []).length + 1}`;
    await apiOp("create_layer", { canvas: state.canvasId, name });
    toast(`Created layer '${name}'`, "ok");
    await loadCanvas(state.canvasId);
  };

  // Search filters & Tool runner
  $("el-search").oninput = (e) => { state.elFilter = e.target.value; if (state.canvas) renderElementsList(state.canvas.elements || []); };
  $("icon-search").oninput = (e) => renderIconsGrid(state.boot.icons, e.target.value);
  $("mat-search").oninput = (e) => renderMaterialsGallery(state.boot.materials.groups, e.target.value);
  $("ops-search").oninput = (e) => renderOpsList(state.boot.operations, e.target.value);
  $("btn-run-op").onclick = async () => {
    const op = $("runner-op-name").textContent.trim();
    let args = {};
    try {
      args = JSON.parse($("runner-args").value || "{}");
    } catch (e) {
      shakeEl($("runner-args"));
      return toast(`Invalid JSON: ${e.message}`, "err");
    }
    await apiOp(op, args);
    confirmButton($("btn-run-op"), "Executed ✓");
    await bootstrap(state.canvasId);
  };

  // Stage toolbar, Zoom & Direct Manipulation Drag Ghost (1:1 locked to pointer)
  $("bg-sel").onchange = (e) => { state.bg = e.target.value; refreshStageImage(); };
  $("btn-ids").onclick = () => {
    state.showIds = !state.showIds;
    $("btn-ids").classList.toggle("on", state.showIds);
    $("btn-ids").setAttribute("aria-pressed", String(state.showIds));
    refreshStageImage();
  };
  $("btn-guides").onclick = () => {
    state.showGuides = !state.showGuides;
    $("btn-guides").classList.toggle("on", state.showGuides);
    $("btn-guides").setAttribute("aria-pressed", String(state.showGuides));
    refreshStageImage();
  };
  $("state-sel").onchange = (e) => { state.previewState = e.target.value; refreshStageImage(); };
  $("sim-sel").onchange = (e) => {
    const v = e.target.value || "";
    state.simMode = v.startsWith("sim:") ? v.slice(4) : "";
    state.langMode = v.startsWith("lang:") ? v.slice(5) : "";
    refreshStageImage();
  };
  function setZoom(z) {
    state.zoom = Math.max(0.25, Math.min(4, z));
    $("canvas-frame").style.transform = `scale(${state.zoom})`;
    $("btn-zrst").textContent = `${Math.round(state.zoom * 100)}%`;
  }
  $("btn-zin").onclick = () => setZoom(state.zoom * 1.25);
  $("btn-zout").onclick = () => setZoom(state.zoom / 1.25);
  $("btn-zrst").onclick = () => setZoom(1);
  $("viewport").addEventListener("wheel", (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      setZoom(e.deltaY < 0 ? state.zoom * 1.12 : state.zoom / 1.12);
    }
  }, { passive: false });
  $("btn-fit-canvas").onclick = async () => { if (state.canvasId) { await apiOp("fit_canvas", { canvas: state.canvasId, padding: 12 }); await loadCanvas(state.canvasId); } };

  // Multi-Device Responsive Matrix & Visual Variations Explorer
  $("btn-devices").onclick = async (e) => {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    openModal("modal-devices", e.currentTarget);
    $("devices-status").hidden = false;
    $("devices-status").textContent = "Rendering 1080p, Ultrawide, Steam Deck & Mobile previews…";
    $("devices-img").hidden = true;
    try {
      const res = await apiOp("preview_resolutions", { canvas: state.canvasId, sizes: ["1080p", "ultrawide", "steam-deck", "iphone"] });
      const imgObj = Array.isArray(res) ? res.find((x) => x && x.image_data_uri) : res;
      if (imgObj && imgObj.image_data_uri) {
        $("devices-img").src = imgObj.image_data_uri;
        $("devices-img").hidden = false;
        $("devices-status").hidden = true;
      } else {
        $("devices-status").textContent = "Preview complete.";
      }
    } catch (err) {
      $("devices-status").textContent = `Could not render device matrix: ${err.message}`;
    }
  };

  $("btn-variations").onclick = (e) => {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    openModal("modal-variations", e.currentTarget);
  };
  $("btn-gen-vars").onclick = async () => {
    if (!state.canvasId) return;
    const btn = $("btn-gen-vars");
    btn.disabled = true;
    btn.textContent = "Generating…";
    try {
      const res = await apiOp("make_variations", { canvas: state.canvasId, count: 3 });
      const meta = Array.isArray(res) ? (typeof res[0] === "string" ? JSON.parse(res[0]) : res[0]) : res;
      const imgObj = Array.isArray(res) ? res.find((x) => x && x.image_data_uri) : null;
      if (imgObj && imgObj.image_data_uri) {
        $("var-img").src = imgObj.image_data_uri;
        $("var-img").hidden = false;
      }
      const vars = (meta && (meta.variations || meta.created || [])) || [];
      const box = $("var-pickers");
      box.innerHTML = vars.map((v, idx) => {
        const cid = typeof v === "string" ? v : (v.canvas || v.id);
        const label = typeof v === "string" ? `Direction ${idx + 1}: ${v}` : `${v.direction || v.name || cid}`;
        return `<button class="chip" data-pick-var="${cid}">Open ${label}</button>`;
      }).join("");
      box.querySelectorAll("[data-pick-var]").forEach((pb) => {
        pb.onclick = async () => {
          closeModal("modal-variations", false);
          await bootstrap(pb.dataset.pickVar);
          toast(`Switched to variation '${pb.dataset.pickVar}'`, "ok");
        };
      });
      toast("Generated 3 visual variations", "ok");
    } finally {
      btn.disabled = false;
      btn.textContent = "Generate 3 Directions";
    }
  };

  // Magnetic Smart Snap Guides + Direct Drag + 8-Point Resize Handles + Double-Click Inline Text Edit
  const imgEl = $("stage-img");
  function canvasXY(ev) {
    const r = imgEl.getBoundingClientRect();
    return [
      ((ev.clientX - r.left) / Math.max(1, r.width)) * state.canvas.width,
      ((ev.clientY - r.top) / Math.max(1, r.height)) * state.canvas.height,
    ];
  }
  function hideSnapLines() { $("snap-v").hidden = true; $("snap-h").hidden = true; }
  function computeSnap(box, dx, dy) {
    const W = state.canvas.width, H = state.canvas.height;
    const xTargets = [0, W / 2, W], yTargets = [0, H / 2, H];
    for (const el of state.canvas.elements || []) {
      if (state.selectedIds.has(el.id) || !el.bbox_xywh) continue;
      const [ex, ey, ew, eh] = el.bbox_xywh;
      xTargets.push(ex, ex + ew / 2, ex + ew);
      yTargets.push(ey, ey + eh / 2, ey + eh);
    }
    const tol = 6;
    let bestDx = dx, snapX = null, minX = tol + 1;
    const [bx, by, bw, bh] = box;
    for (const edge of [bx + dx, bx + bw / 2 + dx, bx + bw + dx]) {
      for (const t of xTargets) {
        const diff = t - edge;
        if (Math.abs(diff) < minX) { minX = Math.abs(diff); bestDx = dx + diff; snapX = t; }
      }
    }
    let bestDy = dy, snapY = null, minY = tol + 1;
    for (const edge of [by + dy, by + bh / 2 + dy, by + bh + dy]) {
      for (const t of yTargets) {
        const diff = t - edge;
        if (Math.abs(diff) < minY) { minY = Math.abs(diff); bestDy = dy + diff; snapY = t; }
      }
    }
    const sv = $("snap-v"), sh = $("snap-h");
    if (snapX !== null) { sv.style.left = `${(snapX / W) * 100}%`; sv.hidden = false; } else sv.hidden = true;
    if (snapY !== null) { sh.style.top = `${(snapY / H) * 100}%`; sh.hidden = false; } else sh.hidden = true;
    return [Math.round(bestDx), Math.round(bestDy)];
  }

  imgEl.onmousemove = (ev) => {
    if (!state.canvas) return;
    const [x, y] = canvasXY(ev);
    $("coords-readout").textContent = `x: ${Math.round(x)} , y: ${Math.round(y)}`;
  };
  imgEl.onmousedown = (ev) => {
    if (!state.canvas || ev.button !== 0) return;
    const [x, y] = canvasXY(ev);
    const els = state.canvas.elements || [];
    let hit = null;
    for (let i = els.length - 1; i >= 0; i--) {
      const b = els[i].bbox_xywh;
      if (b && x >= b[0] && x <= b[0] + b[2] && y >= b[1] && y <= b[1] + b[3]) { hit = els[i].id; break; }
    }
    if (hit) {
      selectElement(hit, ev.shiftKey);
      const ubox = selectionUnionBox();
      if (ubox) {
        state.drag = { ids: Array.from(state.selectedIds), sx: x, sy: y, box0: ubox };
        $("sel-box").classList.add("dragging");
      }
    } else {
      clearSelection();
    }
  };

  // Double-Click Inline Text Editing on Canvas
  imgEl.ondblclick = (ev) => {
    if (!state.canvas) return;
    const [x, y] = canvasXY(ev);
    const els = state.canvas.elements || [];
    let hit = null;
    for (let i = els.length - 1; i >= 0; i--) {
      const b = els[i].bbox_xywh;
      if (b && x >= b[0] && x <= b[0] + b[2] && y >= b[1] && y <= b[1] + b[3]) { hit = els[i]; break; }
    }
    if (!hit) return;
    const raw = state.canvas.raw_elements[hit.id];
    if (!raw || !["text", "input", "slider", "toggle", "dropdown"].includes(raw.type)) return;
    selectElement(hit.id, false);
    const ed = $("inline-text-editor");
    const [bx, by, bw, bh] = hit.bbox_xywh;
    ed.style.left = `${(bx / state.canvas.width) * 100}%`;
    ed.style.top = `${(by / state.canvas.height) * 100}%`;
    ed.style.minWidth = `${Math.max(120, (bw / state.canvas.width) * imgEl.clientWidth)}px`;
    ed.value = raw.text ?? raw.label ?? "";
    ed.hidden = false;
    ed.focus();
    ed.select();
    const finish = async (commit) => {
      if (ed.hidden) return;
      ed.hidden = true;
      ed.onblur = null;
      ed.onkeydown = null;
      if (!commit) return;
      const val = ed.value;
      const propKey = raw.type === "text" ? "text" : "label";
      if (val !== (raw[propKey] ?? "")) {
        await apiOp("update_element", { canvas: state.canvasId, id: hit.id, props: { [propKey]: val } });
        await loadCanvas(state.canvasId);
      }
    };
    ed.onblur = () => finish(true);
    ed.onkeydown = (ke) => {
      if (ke.key === "Enter") { ke.preventDefault(); finish(true); }
      else if (ke.key === "Escape") { ke.preventDefault(); finish(false); }
    };
  };

  // 8-Point Interactive Resize Handles
  $("sel-box").querySelectorAll("[data-rh]").forEach((h) => {
    h.addEventListener("mousedown", (ev) => {
      ev.stopPropagation();
      if (!state.canvas || !state.selectedId) return;
      const raw = state.canvas.raw_elements[state.selectedId];
      const row = (state.canvas.elements || []).find((e) => e.id === state.selectedId);
      if (!raw || !row || !row.bbox_xywh) return;
      const [sx, sy] = canvasXY(ev);
      state.resize = { id: state.selectedId, handle: h.dataset.rh, raw, box0: [...row.bbox_xywh], sx, sy, curBox: [...row.bbox_xywh] };
      $("sel-box").classList.add("dragging");
    });
  });

  window.addEventListener("mousemove", (ev) => {
    if (!state.canvas) return;
    if (state.resize) {
      const rz = state.resize;
      const [x, y] = canvasXY(ev);
      const dx = x - rz.sx, dy = y - rz.sy;
      let [bx, by, bw, bh] = rz.box0;
      const h = rz.handle;
      if (h.includes("e")) bw = Math.max(8, bw + dx);
      if (h.includes("s")) bh = Math.max(8, bh + dy);
      if (h.includes("w")) { const nw = Math.max(8, bw - dx); bx = bx + (bw - nw); bw = nw; }
      if (h.includes("n")) { const nh = Math.max(8, bh - dy); by = by + (bh - nh); bh = nh; }
      rz.curBox = [Math.round(bx), Math.round(by), Math.round(bw), Math.round(bh)];
      positionSelBox(rz.curBox, `${rz.id} · ${rz.curBox[2]}×${rz.curBox[3]}`);
      return;
    }
    if (state.drag) {
      const [x, y] = canvasXY(ev);
      const rawDx = x - state.drag.sx, rawDy = y - state.drag.sy;
      const [sdx, sdy] = ev.altKey ? [Math.round(rawDx), Math.round(rawDy)] : computeSnap(state.drag.box0, rawDx, rawDy);
      state.drag.lastDx = sdx;
      state.drag.lastDy = sdy;
      const pxScaleX = imgEl.clientWidth / Math.max(1, state.canvas.width);
      const pxScaleY = imgEl.clientHeight / Math.max(1, state.canvas.height);
      $("sel-box").style.transform = `translate3d(${sdx * pxScaleX}px, ${sdy * pxScaleY}px, 0)`;
      const who = state.drag.ids.length > 1 ? `${state.drag.ids.length} items` : state.drag.ids[0];
      $("sel-tag").textContent = `${who} · Δ${sdx >= 0 ? "+" : ""}${sdx}, ${sdy >= 0 ? "+" : ""}${sdy}`;
    }
  });

  window.addEventListener("mouseup", async (ev) => {
    if (!state.canvas) return;
    if (state.resize) {
      const rz = state.resize;
      state.resize = null;
      $("sel-box").classList.remove("dragging");
      hideSnapLines();
      const [nx, ny, nw, nh] = rz.curBox;
      const props = {};
      if (rz.raw.type === "ellipse") { props.cx = Math.round(nx + nw / 2); props.cy = Math.round(ny + nh / 2); props.rx = Math.max(4, Math.round(nw / 2)); props.ry = Math.max(4, Math.round(nh / 2)); }
      else if ("width" in rz.raw || "height" in rz.raw) { props.x = nx; props.y = ny; if ("width" in rz.raw) props.width = nw; if ("height" in rz.raw) props.height = nh; }
      if (Object.keys(props).length) {
        await apiOp("update_element", { canvas: state.canvasId, id: rz.id, props });
        await loadCanvas(state.canvasId);
      } else {
        selectElement(rz.id);
      }
      return;
    }
    if (state.drag) {
      const d = state.drag;
      state.drag = null;
      const sb = $("sel-box");
      sb.classList.remove("dragging");
      sb.style.transform = "";
      hideSnapLines();
      const dx = d.lastDx ?? 0, dy = d.lastDy ?? 0;
      if (Math.abs(dx) >= 2 || Math.abs(dy) >= 2) {
        await apiOp("move_elements", { canvas: state.canvasId, ids: d.ids, dx, dy });
        await loadCanvas(state.canvasId);
      } else if (d.ids.length === 1) {
        selectElement(d.ids[0]);
      }
    }
  });

  // Inspector Quick Align, Distribute & Layer Order (WCAG 2.5.7 non-drag alternatives)
  document.querySelectorAll("[data-align]").forEach((btn) => {
    btn.onclick = async () => {
      if (!state.canvasId || !state.selectedIds.size) return;
      const ids = Array.from(state.selectedIds);
      if (ids.length >= 2) {
        await apiOp("align_elements", { canvas: state.canvasId, ids, align: btn.dataset.align });
        await loadCanvas(state.canvasId);
        return;
      }
      const row = (state.canvas.elements || []).find((e) => e.id === state.selectedId);
      if (!row || !row.bbox_xywh) return;
      const [bx, , bw] = row.bbox_xywh;
      const pad = 24;
      const targetX = btn.dataset.align === "left" ? pad
        : btn.dataset.align === "center" ? Math.round((state.canvas.width - bw) / 2)
        : Math.round(state.canvas.width - bw - pad);
      const dx = Math.round(targetX - bx);
      if (dx !== 0) {
        await apiOp("move_elements", { canvas: state.canvasId, ids: [state.selectedId], dx, dy: 0 });
        await loadCanvas(state.canvasId);
      }
    };
  });
  document.querySelectorAll("[data-dist]").forEach((btn) => {
    btn.onclick = async () => {
      const ids = Array.from(state.selectedIds);
      if (!state.canvasId || ids.length < 3) return toast("Shift+Click 3 or more elements to distribute evenly", "info");
      await apiOp("align_elements", { canvas: state.canvasId, ids, distribute: btn.dataset.dist });
      await loadCanvas(state.canvasId);
    };
  });
  document.querySelectorAll("[data-order]").forEach((btn) => {
    btn.onclick = async () => {
      if (!state.canvasId || !state.selectedId) return;
      await apiOp("reorder_element", { canvas: state.canvasId, id: state.selectedId, position: btn.dataset.order });
      await loadCanvas(state.canvasId);
    };
  });

  // Inspector live controls, PBR Material Forge & apply
  $("ins-fill-pick").oninput = (e) => { $("ins-fill").value = e.target.value; };
  $("ins-ry").oninput = (e) => { $("ins-ry-v").textContent = `${e.target.value}°`; };
  $("ins-rx").oninput = (e) => { $("ins-rx-v").textContent = `${e.target.value}°`; };
  $("ins-vc").oninput = (e) => { $("ins-vc-v").textContent = e.target.value; };
  $("pbr-met").oninput = (e) => { $("pbr-met-v").textContent = Number(e.target.value).toFixed(2); };
  $("pbr-rgh").oninput = (e) => { $("pbr-rgh-v").textContent = Number(e.target.value).toFixed(2); };
  $("pbr-cc").oninput = (e) => { $("pbr-cc-v").textContent = Number(e.target.value).toFixed(2); };
  $("pbr-bev").oninput = (e) => { $("pbr-bev-v").textContent = Number(e.target.value).toFixed(1); };
  $("pbr-wear").oninput = (e) => { $("pbr-wear-v").textContent = Number(e.target.value).toFixed(2); };

  function readPbrOverrides() {
    const pbr = {
      metallic: Number($("pbr-met").value),
      roughness: Number($("pbr-rgh").value),
      clearcoat: Number($("pbr-cc").value),
      bevel_size: Number($("pbr-bev").value),
      wear: Number($("pbr-wear").value),
    };
    if ($("pbr-prof").value) pbr.profile = $("pbr-prof").value;
    return pbr;
  }

  $("btn-save-pbr").onclick = async () => {
    const rawName = ($("pbr-save-name").value || "").trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "_");
    if (!rawName) { shakeEl($("pbr-save-name")); return toast("Enter a custom material name", "err"); }
    const baseMat = $("ins-mat").value || "steel";
    const def = { material: baseMat, pbr: readPbrOverrides() };
    await apiOp("set_theme", { materials: { [rawName]: def } });
    confirmButton($("btn-save-pbr"), "Saved ✓");
    toast(`Saved custom PBR material '${rawName}'`, "ok");
    await bootstrap(state.canvasId);
  };

  $("btn-ins-apply").onclick = async () => {
    if (!state.canvasId || !state.selectedId) return;
    const raw = state.canvas.raw_elements[state.selectedId];
    const props = {};
    const nx = Number($("ins-x").value), ny = Number($("ins-y").value);
    const nw = Number($("ins-w").value), nh = Number($("ins-h").value);
    if (raw.type === "ellipse") { props.cx = nx; props.cy = ny; props.rx = nw / 2; props.ry = nh / 2; }
    else if ("x" in raw || raw.type !== "path") { props.x = nx; props.y = ny; if (nw > 0 && "width" in raw) props.width = nw; if (nh > 0 && "height" in raw) props.height = nh; }
    if ("radius" in raw || raw.type === "rect") props.radius = Number($("ins-rad").value) || 0;
    props.rotation = Number($("ins-rot").value) || 0;
    if (raw.type === "text") props.text = $("ins-text").value;
    else if (["input", "slider", "toggle", "dropdown"].includes(raw.type) && $("ins-text").value) props.label = $("ins-text").value;
    const style = Object.assign({}, (typeof raw.style === "object" && raw.style) ? raw.style : {});
    if ($("ins-fill").value.trim()) style.fill = $("ins-fill").value.trim();
    style.opacity = Math.max(0, Math.min(1, Number($("ins-op").value)));
    const stCol = $("ins-stroke").value.trim();
    const stW = Number($("ins-sw").value);
    if (stCol && stCol.toLowerCase() !== "none") style.stroke = { color: stCol, width: stW > 0 ? stW : 1.5 };
    else if (stCol.toLowerCase() === "none") delete style.stroke;
    if ($("ins-mat").value) style.material = $("ins-mat").value; else delete style.material;
    if ($("pbr-forge").open) style.pbr = readPbrOverrides();
    const ry = Number($("ins-ry").value), rx = Number($("ins-rx").value), vc = Number($("ins-vc").value);
    if (ry || rx || vc) style.perspective = { rotate_y: ry, rotate_x: rx, visor_curve: vc };
    else delete style.perspective;
    props.style = style;
    await apiOp("update_element", { canvas: state.canvasId, id: state.selectedId, props });
    confirmButton($("btn-ins-apply"), "Applied ✓");
    await loadCanvas(state.canvasId);
  };
  $("btn-el-dup").onclick = async () => {
    if (!state.selectedId) return;
    await apiOp("duplicate_element", { canvas: state.canvasId, id: state.selectedId, dx: 20, dy: 20 });
    await loadCanvas(state.canvasId);
  };
  $("btn-el-del").onclick = async () => {
    const ids = Array.from(state.selectedIds);
    if (!ids.length) return;
    await apiOp("delete_elements", { canvas: state.canvasId, ids });
    clearSelection();
    await loadCanvas(state.canvasId);
  };

  // Theme, HDRI & CSS/Tailwind/DESIGN.md Token Importer
  $("hdri-sel").onchange = async (e) => {
    await apiOp("set_theme", { environment: { studio: e.target.value } });
    toast(`Studio HDRI: ${e.target.value}`, "ok");
    refreshStageImage();
  };
  $("btn-make-palette").onclick = async () => {
    await apiOp("make_palette", { base: $("pal-seed").value, apply: true });
    confirmButton($("btn-make-palette"), "Palette Ready ✓");
    await bootstrap(state.canvasId);
  };
  $("btn-import-tokens").onclick = async () => {
    const raw = ($("css-tokens-inp").value || "").trim();
    if (!raw) { shakeEl($("css-tokens-inp")); return toast("Paste CSS :root, Tailwind @theme, DTCG JSON, or DESIGN.md first", "err"); }
    try {
      await apiOp("set_theme", { tokens: raw });
      confirmButton($("btn-import-tokens"), "Imported ✓");
      toast("Imported design tokens into workspace theme", "ok");
      await bootstrap(state.canvasId);
    } catch (_) {
      shakeEl($("css-tokens-inp"));
    }
  };

  // Quick Motion Preset Builder (Live Tab)
  $("btn-add-anim-preset").onclick = async () => {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    const target = state.selectedId || ((state.canvas.elements && state.canvas.elements[0] && state.canvas.elements[0].id) || null);
    if (!target) return toast("Select an element to animate", "err");
    const preset = $("anim-preset-sel").value;
    const dur = Math.max(0.1, Number($("anim-preset-dur").value) || 0.45);
    const animName = `${preset}_${target}`.slice(0, 28);
    const loop = preset === "pulse" || preset === "spin";
    await apiOp("create_animation", { canvas: state.canvasId, name: animName, duration: dur, loop });
    if (preset === "pop") {
      await apiOp("set_keyframes", { canvas: state.canvasId, animation: animName, target, property: "scale", keyframes: [[0, 0.65], [dur, 1.0, "back-out"]] });
      await apiOp("set_keyframes", { canvas: state.canvasId, animation: animName, target, property: "opacity", keyframes: [[0, 0.0], [dur * 0.45, 1.0, "quad-out"]] });
    } else if (preset === "slide") {
      await apiOp("set_keyframes", { canvas: state.canvasId, animation: animName, target, property: "dy", keyframes: [[0, 26], [dur, 0, "cubic-out"]] });
      await apiOp("set_keyframes", { canvas: state.canvasId, animation: animName, target, property: "opacity", keyframes: [[0, 0.0], [dur * 0.6, 1.0, "quad-out"]] });
    } else if (preset === "pulse") {
      await apiOp("set_keyframes", { canvas: state.canvasId, animation: animName, target, property: "opacity", keyframes: [[0, 1.0], [dur * 0.5, 0.52, "sine-in-out"], [dur, 1.0, "sine-in-out"]] });
    } else {
      await apiOp("set_keyframes", { canvas: state.canvasId, animation: animName, target, property: "rotation", keyframes: [[0, 0], [dur, 360, "linear"]] });
    }
    state.animName = animName;
    state.animT = dur * 0.35;
    confirmButton($("btn-add-anim-preset"), "Animated ✓");
    toast(`Created '${animName}' animation`, "ok");
    await loadCanvas(state.canvasId);
  };

  // Audit & Versions & Visual Diff
  async function runAudit() {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    document.querySelector('.rtab[data-right="audit"]').click();
    const res = await apiOp("review_canvas", { canvas: state.canvasId });
    const box = $("audit-results");
    let html = "";
    if (res.wcag) {
      html += `<div class="audit-card ${res.wcag.aa_pass ? "pass" : "warn"}"><strong>WCAG Contrast:</strong> min ${res.wcag.min_ratio}:1 (${res.wcag.aa_pass ? "AA PASS" : "BELOW AA"}) · ${res.wcag.checked_texts} texts, ${res.wcag.checked_widgets} widgets</div>`;
    }
    html += (res.issues || []).map((i) => `<div class="audit-card ${i.severity}"><strong>[${i.check}]</strong> ${i.message}</div>`).join("");
    box.innerHTML = html || '<div class="audit-card pass">Zero issues found.</div>';
  }
  $("btn-audit").onclick = $("btn-run-audit").onclick = runAudit;
  $("btn-save-ver").onclick = async () => {
    if (!state.canvasId) return;
    const res = await apiOp("canvas_version", { canvas: state.canvasId, action: "save" });
    confirmButton($("btn-save-ver"), "Saved ✓");
    toast(`Saved snapshot '${res.saved}'`, "ok");
    await loadCanvas(state.canvasId);
  };
  $("btn-diff").onclick = (e) => openModal("modal-diff", e.currentTarget);
  $("btn-run-diff").onclick = async () => {
    const vname = $("diff-ver-sel").value;
    if (!state.canvasId || !vname) return toast("Save a version snapshot first", "err");
    const res = await apiOp("canvas_version", { canvas: state.canvasId, action: "visual_diff", name: vname });
    const meta = typeof res[0] === "string" ? JSON.parse(res[0]) : res[0];
    const imgObj = res[1];
    $("diff-metrics").textContent = `${meta.changed_pct}% changed · MAE ${meta.mean_abs_error} · max Δ ${meta.max_delta}`;
    if (imgObj && imgObj.image_data_uri) { $("diff-img").src = imgObj.image_data_uri; $("diff-img").hidden = false; }
  };

  // Export Modal + Copy Code with in-place confirmation
  $("btn-export").onclick = (e) => {
    if (!state.canvasId) return toast("Create a canvas first", "err");
    openModal("modal-export", e.currentTarget);
  };
  $("btn-exp-copy").onclick = async () => {
    const txt = $("exp-code").textContent || "";
    if (!txt) return;
    try {
      await navigator.clipboard.writeText(txt);
      confirmButton($("btn-exp-copy"), "Copied ✓");
    } catch (_) {
      toast("Clipboard permission unavailable", "err");
    }
  };
  document.querySelectorAll("[data-exp]").forEach((btn) => {
    btn.onclick = async () => {
      if (!state.canvasId) return;
      const target = btn.dataset.exp;
      let res;
      if (target === "png") res = await apiOp("export_png", { canvas: state.canvasId, scales: [1, 2] });
      else if (target === "svg") res = await apiOp("export_svg", { canvas: state.canvasId });
      else if (target === "psd") res = await apiOp("export_psd", { canvas: state.canvasId });
      else if (target === "pbr") res = await apiOp("export_pbr_maps", { canvas: state.canvasId, engine: "generic" });
      else if (target === "dotlottie" || target === "gif") {
        const anims = (state.canvas && state.canvas.animations) || [];
        if (!anims.length) return toast("Add an animation in the Live tab first", "err");
        const animArg = target === "dotlottie" ? "all" : (state.animName || anims[0].name);
        res = await apiOp("export_animation", { canvas: state.canvasId, animation: animArg, format: target });
      }
      else if (target === "web") res = await apiOp("export_web", { canvases: [state.canvasId] });
      else if (target === "react") res = await apiOp("export_react", { canvases: [state.canvasId], typescript: true, css: "tailwind" });
      else res = await apiOp("export_screen", { canvas: state.canvasId, engine: target });

      $("export-output").hidden = false;
      $("exp-out-title").textContent = `Exported: ${target.toUpperCase()}`;
      const folder = res.folder || res.dir || "";
      const rawOut = folder || res.file || "";
      const wsRoot = (state.boot && state.boot.workspace) || "";
      const relOut = wsRoot && rawOut.startsWith(wsRoot) ? rawOut.slice(wsRoot.length).replace(/^[\\/]+/, "") : rawOut;
      $("exp-out-dir").textContent = relOut;
      const filePaths = [];
      if (res.file) filePaths.push(res.file);
      if (Array.isArray(res.files)) {
        for (const f of res.files) filePaths.push(typeof f === "string" ? (folder ? `${folder}/${f}` : f) : f.file);
      } else if (res.files && typeof res.files === "object") {
        for (const f of Object.values(res.files)) filePaths.push(folder ? `${folder}/${f}` : f);
      }
      if (Array.isArray(res.pages)) for (const p of res.pages) filePaths.push(`${folder}/${p}`);
      if (Array.isArray(res.components)) for (const p of res.components) filePaths.push(`${folder}/${p}`);

      const fBox = $("exp-files");
      fBox.innerHTML = filePaths.slice(0, 12).map((fp) => {
        const name = fp.split(/[\\/]/).pop();
        return `<button class="chip mono" data-prev="${fp.replace(/"/g, "&quot;")}">${name}</button>`;
      }).join("");
      fBox.querySelectorAll("[data-prev]").forEach((fb) => {
        fb.onclick = async () => previewExportFile(fb.dataset.prev);
      });
      toast(`Exported ${target} successfully`, "ok");
      const firstCode =
        filePaths.find((f) => /\.(py|xaml|axaml|qml|hpp|tsx|jsx|cs|gd|tscn|luau|html|svg)$/i.test(f)) ||
        filePaths.find((f) => /\.json$/i.test(f));
      if (firstCode) await previewExportFile(firstCode);
    };
  });

  async function previewExportFile(fp) {
    const codeEl = $("exp-code"), frameEl = $("exp-iframe"), copyBtn = $("btn-exp-copy");
    codeEl.hidden = true; frameEl.hidden = true; copyBtn.hidden = true;
    const url = `/api/export_preview?path=${encodeURIComponent(fp)}`;
    if (/\.html$/i.test(fp)) {
      frameEl.src = url;
      frameEl.hidden = false;
    } else {
      const r = await fetch(url);
      const ct = r.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const d = await r.json();
        codeEl.textContent = d.text || d.error || "";
        codeEl.hidden = false;
        copyBtn.hidden = false;
      }
    }
  }

  // Settings, GPU & IDE config
  $("btn-settings").onclick = (e) => openModal("modal-settings", e.currentTarget);
  $("btn-apply-gpu").onclick = async () => {
    const backend = $("set-gpu-pref").value;
    const r = await fetch("/api/gpu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend }),
    });
    const d = await r.json();
    if (!d.ok) return toast(d.error, "err");
    const act = d.doctor.active_backend || "cpu";
    $("gpu-label").textContent = act.toUpperCase();
    $("set-gpu-active").textContent = act.toUpperCase();
    $("gpu-dot").classList.toggle("on", act !== "cpu");
    confirmButton($("btn-apply-gpu"), "Applied ✓");
    toast(`GPU backend switched to ${act.toUpperCase()}`, "ok");
  };
  $("btn-ide-preview").onclick = async () => {
    const cl = $("ide-client-sel").value;
    const r = await fetch(`/api/ide_config/${encodeURIComponent(cl)}`);
    const d = await r.json();
    $("ide-config-out").textContent = JSON.stringify(d, null, 2);
    $("ide-config-out").hidden = false;
  };
  $("btn-ide-write").onclick = async () => {
    const cl = $("ide-client-sel").value;
    const r = await fetch("/api/ide_setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client: cl }),
    });
    const d = await r.json();
    if (!d.ok) return toast(d.error, "err");
    confirmButton($("btn-ide-write"), "Installed ✓");
    toast(d.written ? `Installed config at ${d.written}` : `See HTTP command for ${cl}`, "ok");
    $("ide-config-out").textContent = JSON.stringify(d.spec, null, 2);
    $("ide-config-out").hidden = false;
  };

  // Console Drawer (mouse + Enter/Space keyboard access)
  function toggleConsole() {
    const body = $("console-body");
    body.hidden = !body.hidden;
    $("console-toggle").setAttribute("aria-expanded", String(!body.hidden));
    if (!body.hidden) refreshActivity();
  }
  $("console-toggle").onclick = toggleConsole;
  $("console-toggle").onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleConsole(); }
  };

  // Global Keyboard Workstation Shortcuts + Modal Focus Trap
  window.addEventListener("keydown", async (e) => {
    // Modal Escape & Tab Focus Trap
    if (state.activeModal) {
      if (e.key === "Escape") { e.preventDefault(); closeModal(state.activeModal); return; }
      if (e.key === "Tab") {
        const focusables = getFocusable($(state.activeModal));
        if (focusables.length) {
          const first = focusables[0], last = focusables[focusables.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
        return;
      }
    }

    const mod = e.ctrlKey || e.metaKey;
    const k = e.key.toLowerCase();
    if (mod && k === "k") { e.preventDefault(); $("btn-cmdk").click(); return; }
    if (mod && k === "z") { e.preventDefault(); $("btn-undo").click(); return; }
    if (mod && k === "y") { e.preventDefault(); $("btn-redo").click(); return; }

    if (isTypingTarget(e.target) || state.activeModal) return;

    if (mod && k === "d" && state.selectedId) { e.preventDefault(); $("btn-el-dup").click(); return; }
    if ((e.key === "Delete" || e.key === "Backspace") && state.selectedId) { e.preventDefault(); $("btn-el-del").click(); return; }
    if (e.key === "Escape" && state.selectedId) { clearSelection(); return; }
    if (e.key === "?") { e.preventDefault(); openModal("modal-shortcuts"); return; }
    if (k === "i") { $("btn-ids").click(); return; }
    if (k === "g") { $("btn-guides").click(); return; }
    if (e.key === "+" || e.key === "=") { setZoom(state.zoom * 1.25); return; }
    if (e.key === "-") { setZoom(state.zoom / 1.25); return; }
    if (e.key === "0") { setZoom(1); return; }

    // WCAG 2.5.7 Arrow-Key Element Nudge (1px, Shift=10px, supports multi-select!)
    if (state.canvasId && state.selectedIds.size && ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) {
      e.preventDefault();
      const step = e.shiftKey ? 10 : 1;
      const dx = e.key === "ArrowLeft" ? -step : (e.key === "ArrowRight" ? step : 0);
      const dy = e.key === "ArrowUp" ? -step : (e.key === "ArrowDown" ? step : 0);
      await apiOp("move_elements", { canvas: state.canvasId, ids: Array.from(state.selectedIds), dx, dy });
      await loadCanvas(state.canvasId);
    }
  });

  // Live SSE Sync (Combined Mode + Multi-Tab Sync)
  const es = new EventSource("/events");
  es.onopen = () => $("sse-dot").classList.remove("off");
  es.onerror = () => $("sse-dot").classList.add("off");
  es.onmessage = async (ev) => {
    try {
      const d = JSON.parse(ev.data);
      await bootstrap(d.canvas || state.canvasId);
    } catch (_) {}
  };

  bootstrap();
})();
