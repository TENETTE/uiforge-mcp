"""Tests for v0.15.0: Three Runtime Modes (MCP, Human UI without mcp, Combined sync),
cross-process Store disk sync, thread concurrency safety, Studio REST/SSE security, and CLI setup."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from uiforge_mcp import cli, core, server as srv
from uiforge_mcp.store import Store
from uiforge_mcp.studio_ui import StudioServer


def _http_json(url: str, data: dict | None = None, timeout: float = 20.0) -> tuple[int, dict]:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=("POST" if body is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _http_bytes(url: str, timeout: float = 20.0) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")


@pytest.fixture
def isolated_store(tmp_path):
    st = Store(workspace=tmp_path, persist=True)
    srv.set_store(st)
    core.activity_log.clear()
    core.set_mode("mcp")
    yield st
    core.set_mode("mcp")
    srv.set_store(None)


def test_mcp_mode_standalone_without_ui(isolated_store):
    """MCP Mode runs core operations through real MCP tool dispatch with zero Studio UI server running."""
    core.set_mode("mcp")
    asyncio.run(srv.mcp.call_tool("create_canvas", {"name": "mcp_only", "width": 320, "height": 180, "background": "#0d1117"}))
    asyncio.run(srv.mcp.call_tool("add_rect", {"canvas": "mcp_only", "x": 16, "y": 16, "width": 288, "height": 148, "id": "card", "radius": 12, "fill": "#1e293b"}))
    asyncio.run(srv.mcp.call_tool("add_icon", {"canvas": "mcp_only", "name": "shield", "x": 36, "y": 36, "size": 32, "id": "ico", "color": "#38bdf8"}))
    asyncio.run(srv.mcp.call_tool("add_slider", {"canvas": "mcp_only", "x": 80, "y": 96, "width": 180, "height": 28, "id": "sl", "value": 64, "label": "Power"}))
    out = srv.export_png("mcp_only")
    assert Path(out["files"][0]["file"]).is_file()
    entries = core.activity_log.list(limit=10)
    assert any(e["source"] == "mcp" and e["operation"] == "create_canvas" for e in entries)


def test_human_mode_standalone_without_mcp_package(tmp_path):
    """Human Mode Studio UI boots and executes full workflows when the 'mcp' package is completely absent."""
    script = f"""
import json, os, sys, urllib.request, urllib.error
from pathlib import Path

# Block 'mcp' completely before importing any uiforge_mcp module
for mod in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.mcpserver", "mcp.types"):
    sys.modules[mod] = None

os.environ["UIFORGE_MCP_DIR"] = {str(tmp_path)!r}

from uiforge_mcp import core, server as srv
from uiforge_mcp.studio_ui import StudioServer

assert srv.MCP_AVAILABLE is False, "Expected MCP_AVAILABLE=False when mcp is blocked"
assert len(core.list_operations()) >= 90

studio = StudioServer(srv.store, host="127.0.0.1", port=0, mode="ui")
info = studio.start()
base = info["url"]

def req_json(path, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {{"Content-Type": "application/json"}} if data is not None else {{}}
    r = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(r, timeout=25) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

try:
    # 1. Serve offline HTML, CSS, JS, bundled fonts, MCP-forged brand art & live PBR swatch
    for asset_path, expected_sub in [
        ("/", b"UIForge"),
        ("/assets/studio.css", b"--amber"),
        ("/assets/studio.js", b"/api/bootstrap"),
        ("/assets/brand/emblem.png", b"\\x89PNG"),
        ("/assets/brand/starter_tactical.png", b"\\x89PNG"),
        ("/assets/brand/starter_rpg.png", b"\\x89PNG"),
        ("/assets/brand/starter_saas.png", b"\\x89PNG"),
        ("/favicon.ico", b"\\x89PNG"),
        ("/fonts/inter.ttf", b""),
        ("/api/swatch/gold", b"\\x89PNG"),
    ]:
        with urllib.request.urlopen(base + asset_path, timeout=25) as resp:
            raw = resp.read()
            assert resp.status == 200 and len(raw) > 100
            if expected_sub:
                assert expected_sub in raw

    # 2. Bootstrap reports Human Mode with mcp_available=False
    code, boot = req_json("/api/bootstrap")
    assert code == 200
    assert boot["mode"] == "ui"
    assert boot["mcp_available"] is False
    assert len(boot["materials"]["all"]) == 39
    assert len(boot["icons"]) >= 140

    # 3. Full design & export pipeline via UI /api/op (zero MCP)
    ops = [
        ("create_canvas", {{"name": "human_hud", "width": 640, "height": 360, "background": "#0b1120"}}),
        ("add_frame", {{"canvas": "human_hud", "x": 16, "y": 16, "width": 608, "height": 328, "preset": "scifi_hud", "title": "STANDALONE"}}),
        ("add_icon", {{"canvas": "human_hud", "name": "shield", "x": 40, "y": 80, "size": 36, "color": "#38bdf8"}}),
        ("add_slider", {{"canvas": "human_hud", "x": 40, "y": 140, "width": 220, "height": 28, "id": "sl1", "value": 70, "label": "Output"}}),
        ("add_toggle", {{"canvas": "human_hud", "x": 40, "y": 200, "id": "tg1", "checked": True, "label": "Lock"}}),
        ("add_dropdown", {{"canvas": "human_hud", "x": 40, "y": 250, "width": 200, "height": 36, "id": "dd1", "options": ["Auto", "Manual"], "selected": "Auto"}}),
    ]
    for op_name, args in ops:
        st_code, res = req_json("/api/op", {{"op": op_name, "args": args}})
        assert st_code == 200 and res["ok"], f"{{op_name}} failed: {{res}}"

    # 4. Render canvas PNG through Studio endpoint
    with urllib.request.urlopen(base + "/api/render/human_hud", timeout=25) as resp:
        png = resp.read()
        assert png.startswith(b"\\x89PNG") and len(png) > 1000

    # 5. Export PNG, Web, WPF, and Unreal UMG purely from Human Mode
    for op_name, args in [
        ("export_png", {{"canvas": "human_hud"}}),
        ("export_web", {{"canvases": ["human_hud"]}}),
        ("export_screen", {{"canvas": "human_hud", "engine": "wpf"}}),
        ("export_screen", {{"canvas": "human_hud", "engine": "unreal"}}),
    ]:
        st_code, res = req_json("/api/op", {{"op": op_name, "args": args}})
        assert st_code == 200 and res["ok"], f"{{op_name}} failed: {{res}}"

    # 6. Verify /api/export_preview sandbox blocks traversal outside exports/
    blocked = False
    try:
        urllib.request.urlopen(base + "/api/export_preview?path=../../pyproject.toml", timeout=10)
    except urllib.error.HTTPError as e:
        blocked = e.code == 403
    assert blocked, "Expected 403 when attempting path traversal via /api/export_preview"

    # 7. Verify legitimate export file preview succeeds
    umg_py = Path({str(tmp_path)!r}) / "exports" / "screens" / "human_hud" / "WBP_HumanHud_build_umg.py"
    assert umg_py.is_file()
    rel = umg_py.relative_to(Path({str(tmp_path)!r})).as_posix()
    with urllib.request.urlopen(base + "/api/export_preview?path=" + rel, timeout=10) as resp:
        txt = resp.read().decode("utf-8")
        assert "WidgetBlueprintFactory" in txt

    print("HUMAN_NO_MCP_OK")
finally:
    studio.stop()
"""
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "HUMAN_NO_MCP_OK" in proc.stdout


def test_combined_mode_in_process_bidirectional_sync(isolated_store):
    """Combined Mode keeps UI and MCP completely synchronized in real time with unified Activity Log & SSE."""
    studio = StudioServer(srv.store, host="127.0.0.1", port=0, mode="combined")
    info = studio.start()
    base = info["url"]
    try:
        assert core.get_mode() == "combined"

        # 1. Human creates canvas via Studio UI -> MCP immediately reads & edits it
        code, res = _http_json(base + "/api/op", {
            "op": "create_canvas",
            "args": {"name": "shared_hud", "width": 480, "height": 270, "background": "#0f172a"},
        })
        assert code == 200 and res["ok"]

        mcp_view = srv.get_canvas("shared_hud")
        assert mcp_view["canvas"] == "shared_hud"
        assert mcp_view["width"] == 480

        # 2. Listen on SSE /events in background thread while MCP mutates the canvas
        sse_lines: list[str] = []
        sse_ready = threading.Event()

        def _read_sse():
            req = urllib.request.Request(base + "/events")
            with urllib.request.urlopen(req, timeout=6) as resp:
                sse_ready.set()
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        sse_lines.append(line)
                    if "shared_hud" in line:
                        break

        t = threading.Thread(target=_read_sse, daemon=True)
        t.start()
        assert sse_ready.wait(timeout=3.0)

        # MCP adds elements to the UI-created canvas via real MCP call_tool
        asyncio.run(srv.mcp.call_tool("add_rect", {"canvas": "shared_hud", "x": 24, "y": 24, "width": 200, "height": 80, "id": "mcp_panel", "fill": "#1e293b", "radius": 10}))
        asyncio.run(srv.mcp.call_tool("add_text", {"canvas": "shared_hud", "text": "SYNCED", "x": 124, "y": 64, "id": "mcp_lbl", "anchor": "center", "size": 22, "color": "#f8fafc"}))
        t.join(timeout=4.0)

        # 3. UI immediately sees MCP elements and renders them
        code, canvas_json = _http_json(base + "/api/canvas/shared_hud")
        assert code == 200
        ids = {e["id"] for e in canvas_json["elements"]}
        assert {"mcp_panel", "mcp_lbl"} <= ids

        st_code, png_bytes, ctype = _http_bytes(base + "/api/render/shared_hud")
        assert st_code == 200 and ctype == "image/png" and png_bytes.startswith(b"\x89PNG")

        # 4. Activity Log interleaves both [UI] and [MCP] operations
        code, act = _http_json(base + "/api/activity")
        assert code == 200
        sources = {e["source"] for e in act["activity"]}
        assert "ui" in sources and "mcp" in sources

        # 5. SSE delivered live update event
        assert any("shared_hud" in ln for ln in sse_lines), f"Expected SSE update for shared_hud, got {sse_lines}"
    finally:
        studio.stop()


def test_combined_mode_cross_process_disk_sync(tmp_path):
    """Two separate Store instances (simulating separate uiforge-mcp and uiforge ui processes) stay synced via disk."""
    store_mcp = Store(workspace=tmp_path, persist=True)
    store_ui = Store(workspace=tmp_path, persist=True)

    # Process A (MCP) creates canvas & updates theme
    c = store_mcp.create_canvas("cross_proc", 400, 200, background="#111827")
    store_mcp.add_element(c, "rect", {"id": "from_mcp", "x": 10, "y": 10, "width": 120, "height": 60, "fill": "#38bdf8"})
    store_mcp.theme["colors"]["brand"] = "#e89b3c"
    store_mcp.save_theme()

    # Process B (UI) syncs from disk and sees both canvas and theme
    assert store_ui.sync_from_disk() is True
    assert "cross_proc" in store_ui.canvases
    assert {e["id"] for e in store_ui.get("cross_proc")["elements"]} == {"from_mcp"}
    assert store_ui.theme["colors"]["brand"] == "#e89b3c"

    # Process B (UI) adds another element -> Process A (MCP) picks it up
    time.sleep(0.02)
    c_ui = store_ui.get("cross_proc")
    store_ui.add_element(c_ui, "text", {"id": "from_ui", "text": "Hello", "x": 200, "y": 40, "size": 20, "color": "#fff"})
    assert store_mcp.sync_from_disk() is True
    assert {e["id"] for e in store_mcp.get("cross_proc")["elements"]} == {"from_mcp", "from_ui"}

    # Process A deletes canvas -> Process B cleans it up on disk sync
    store_mcp.delete_canvas(store_mcp.get("cross_proc"))
    assert store_ui.sync_from_disk() is True
    assert "cross_proc" not in store_ui.canvases


def test_store_concurrency_stress_no_corruption(tmp_path):
    """8 concurrent threads mutating and saving the same canvas never corrupt JSON or collide on temp files."""
    st = Store(workspace=tmp_path, persist=True)
    c = st.create_canvas("stress", 500, 400, background="#0b0c0f")

    errors: list[Exception] = []

    def worker(idx: int):
        try:
            for j in range(5):
                el, _ = st.add_element(
                    c, "rect",
                    {"id": f"r_{idx}_{j}", "x": (idx * 50) % 420, "y": j * 60, "width": 40, "height": 40, "fill": "#38bdf8"},
                    checkpoint=False,
                )
                st.update_element(c, el, {"radius": 6}, checkpoint=False)
        except Exception as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(worker, i) for i in range(8)]
        for f in futs:
            f.result()

    assert not errors, f"Concurrency errors: {errors}"
    assert len(c["elements"]) == 40
    # Verify on-disk JSON is completely valid and contains all 40 elements
    disk_data = json.loads((tmp_path / "projects" / "stress.json").read_text(encoding="utf-8"))
    assert len(disk_data["elements"]) == 40
    # No lingering .tmp files
    assert not list((tmp_path / "projects").glob("*.tmp"))


def test_cli_codex_setup_and_doctor(tmp_path):
    """Verify OpenAI Codex TOML config generation, idempotent write, and doctor mode reporting."""
    spec = cli.client_config("codex", gpu_arch="cpu")
    assert spec["format"] == "toml"
    assert "[mcp_servers.uiforge]" in spec["toml"]
    assert "uiforge-mcp" in spec["toml"]

    # Redirect path to tmp_path and verify idempotent merge
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('[model]\nname = "default"\n', encoding="utf-8")
    spec["path"] = str(toml_file)
    cli.write_client_config(spec)
    cli.write_client_config(spec)  # calling twice must not duplicate section
    content = toml_file.read_text(encoding="utf-8")
    assert content.count("[mcp_servers.uiforge]") == 1
    assert "[model]" in content

    # Verify CLI doctor reports version & all 3 modes
    proc = subprocess.run([sys.executable, "-m", "uiforge_mcp.server", "doctor"], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0
    rep = json.loads(proc.stdout)
    assert "version" in rep
    assert set(rep["modes_available"]) == {"ui", "mcp", "combined"}
    assert rep["mcp_sdk_available"] is True


def test_css_tailwind_shadcn_token_importer(isolated_store):
    """set_theme(tokens=...) parses CSS :root, Tailwind v4 @theme oklch(), shadcn HSL triplets & dark/light modes."""
    css = """
    :root {
      --primary: 222.2 47.4% 11.2%;
      --radius-card: 14px;
      --space-md: 1rem;
    }
    @theme {
      --color-forge-amber: oklch(0.74 0.14 68);
      --color-plasma: #22d3ee;
    }
    .dark {
      --surface: #0b0e14;
    }
    """
    res = srv.set_theme(tokens=css)
    cols = res["colors"]
    assert cols["plasma"] == "#22d3ee"
    assert cols["primary"].startswith("#") and len(cols["primary"]) == 7
    assert cols["forge-amber"].startswith("#") and len(cols["forge-amber"]) == 7
    assert res["numbers"]["radius-card"] == 14.0
    assert res["numbers"]["space-md"] == 16.0
    assert "dark" in res["modes"]


def test_vision_simulator_pseudo_i18n_and_custom_pbr_swatch(isolated_store):
    """Studio /api/render supports CVD vision simulation & pseudo-localization, and /api/swatch renders custom PBR."""
    studio = StudioServer(srv.store, host="127.0.0.1", port=0, mode="ui")
    info = studio.start()
    base = info["url"]
    try:
        srv.create_canvas("vis_test", 320, 180, background="#0b1120")
        srv.add_text("vis_test", "PLAY GAME", 160, 90, anchor="center", size=24, color="#ef4444")
        st1, normal_png, _ = _http_bytes(base + "/api/render/vis_test")
        st2, cvd_png, _ = _http_bytes(base + "/api/render/vis_test?sim=deuteranopia")
        st3, pseudo_png, _ = _http_bytes(base + "/api/render/vis_test?lang=pseudo-long")
        assert st1 == 200 and st2 == 200 and st3 == 200
        assert normal_png != cvd_png, "Deuteranopia vision simulation should visibly transform red pixels"
        assert normal_png != pseudo_png, "Pseudo-long localization should visibly expand text"

        # Save custom tuned Cook-Torrance PBR material & render live swatch
        srv.set_theme(materials={"molten_alloy": {"material": "gold", "pbr": {"metallic": 0.95, "roughness": 0.14, "wear": 0.35}}})
        st4, sw_png, ctype = _http_bytes(base + "/api/swatch/molten_alloy")
        assert st4 == 200 and ctype == "image/png" and sw_png.startswith(b"\x89PNG") and len(sw_png) > 500
    finally:
        studio.stop()
