"""Tests for v0.14 features: security hardening (binding AST DoS, HTTP Bearer auth, export sandbox),
single-source versioning, modular toolsets & compact schema token reduction, pure-MIT built-in vector
icons (add_icon + uiforge://icons), native Slider/Toggle/Dropdown widgets across all targets, Unreal
Engine UMG WidgetBlueprint export, 3D diegetic perspective & curved visor HUD, SEP-1865 MCP App studio
+ Live Preview v2, screenshot v2 (layout groups, toggle detection, $token binding), pixel visual diff,
and WCAG widget contrast audit."""

import asyncio
import json
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from uiforge_mcp import __version__
from uiforge_mcp import cli, icons, server as s, tools_delivery as td
from uiforge_mcp.binding import eval_expr
from uiforge_mcp.live import LiveStudio
from uiforge_mcp.store import Store
from uiforge_mcp.studio_app import STUDIO_APP_HTML, STUDIO_APP_URI, studio_snapshot


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    s.set_export_sandbox(None)
    yield tmp_path
    s.set_export_sandbox(None)
    s.configure_server("full", compact=False)
    s.set_store(None)


def test_version_single_source_and_binding_dos_guard(ws):
    assert __version__ == "0.16.0"
    assert eval_expr("2 ** 8", {}) == 256.0
    with pytest.raises(ValueError, match="exponent|safety"):
        eval_expr("9 ** 9 ** 9", {})
    with pytest.raises(ValueError, match="exponent|safety"):
        eval_expr("2 ** 1000", {})
    with pytest.raises(ValueError, match="string repetition|safety"):
        eval_expr("'x' * 50000", {})


def test_export_sandbox_and_http_bearer_auth(ws, tmp_path):
    s.create_canvas("sbx", 64, 64, background="#111827")
    s.add_rect("sbx", 8, 8, 48, 48, fill="#38bdf8")

    s.set_export_sandbox(True)
    outside = tmp_path / "outside.png"
    with pytest.raises(ValueError, match="Export sandbox active"):
        s.export_png("sbx", path=str(outside))
    with pytest.raises(ValueError, match="Export sandbox active"):
        s.export_png("sbx", path="../escape.png")
    ok = s.export_png("sbx", path="nested/safe.png")
    assert Path(ok["files"][0]["file"]).is_file()
    s.set_export_sandbox(False)

    # Verify ASGI Bearer auth middleware rejects missing/bad tokens and allows matching token
    called = []

    async def dummy_app(scope, receive, send):
        called.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = cli.BearerAuthMiddleware(dummy_app, "topsecret-token")

    async def run_req(headers):
        events = []

        async def recv():
            return {"type": "http.request", "body": b""}

        async def send(ev):
            events.append(ev)

        await mw({"type": "http", "method": "POST", "headers": headers}, recv, send)
        return events[0]["status"]

    assert asyncio.run(run_req([])) == 401
    assert asyncio.run(run_req([(b"authorization", b"Bearer wrong")])) == 401
    assert asyncio.run(run_req([(b"authorization", b"Bearer topsecret-token")])) == 200
    assert called == [True]


def test_modular_toolsets_and_compact_token_reduction(ws):
    full = s.configure_server("full", compact=False)
    core_c = s.configure_server("core", compact=True)
    game_c = s.configure_server("game", compact=True)
    desktop_c = s.configure_server("desktop", compact=True)
    web_c = s.configure_server("web", compact=True)

    assert full["registered_tools"] >= 95
    assert core_c["registered_tools"] < full["registered_tools"] * 0.6
    assert core_c["estimated_tokens"] < full["estimated_tokens"] * 0.4
    assert game_c["estimated_tokens"] < full["estimated_tokens"] * 0.65
    assert desktop_c["registered_tools"] < full["registered_tools"]
    assert web_c["registered_tools"] < full["registered_tools"]

    with pytest.raises(ValueError, match="toolset must be"):
        s.configure_server("unknown")


def test_builtin_vector_icons_library_and_batch(ws):
    all_icons = icons.list_icons()
    assert len(all_icons) >= 90
    game_icons = icons.list_icons("rpg")
    assert any(i["name"] == "sword" for i in game_icons)

    s.create_canvas("ico", 220, 80, background="#0f172a")
    r1 = s.add_icon("ico", "shield", 16, 16, size=40, color="#38bdf8", id="i_shield")
    assert r1["icon"] == "shield" and r1["type"] == "path"
    r2 = s.batch("ico", [
        {"op": "add_icon", "name": "heart", "x": 80, "y": 16, "size": 40, "color": "#f43f5e", "id": "i_heart"},
        {"op": "add_icon", "name": "crown", "x": 144, "y": 16, "size": 40,
         "style": {"material": "gold"}, "filled": True, "id": "i_crown"},
    ])
    assert len(r2["results"]) == 2
    img = s.store().renderer(s.store().get("ico")).render()
    arr = np.asarray(img)
    assert arr[..., :3].std() > 15.0

    with pytest.raises(ValueError, match="Unknown icon"):
        s.add_icon("ico", "nonexistent_glyph_xyz", 0, 0)


def test_native_slider_toggle_dropdown_widgets_and_all_exporters(ws, tmp_path):
    s.create_canvas("settings", 520, 420, background="#0b1120")
    s.set_binding("settings", data={"volume": 75, "vsync": True, "quality": "Ultra"})
    s.add_rect("settings", 16, 16, 488, 388, radius=12, fill="#111827", group="bg_panel")
    s.add_text("settings", "AUDIO & VIDEO", 36, 40, size=20, weight=700, color="#f8fafc", id="hdr")
    s.add_slider("settings", 36, 100, 280, 28, min=0, max=100, value=75, label="Master Volume", bind="volume", id="sl_vol")
    s.add_toggle("settings", 36, 165, 52, 28, checked=True, variant="switch", label="V-Sync", bind="vsync", id="tg_vsync")
    s.add_toggle("settings", 240, 165, 26, 26, checked=True, variant="checkbox", label="HDR", id="cb_hdr")
    s.add_dropdown("settings", 36, 240, 280, 40, options=["Low", "High", "Ultra"], selected="Ultra",
                   label="Preset", bind="quality", id="dd_qual")

    img = s.store().renderer(s.store().get("settings")).render()
    assert img.size == (520, 420)
    assert np.asarray(img)[..., :3].std() > 15.0

    # Web + React TSX
    web_res = s.export_web(["settings"], out_dir=str(tmp_path / "web"))
    html_txt = (tmp_path / "web" / "index.html").read_text(encoding="utf-8")
    assert 'type="range"' in html_txt and 'type="checkbox"' in html_txt and "<select" in html_txt
    react_res = s.export_react(["settings"], out_dir=str(tmp_path / "react"), typescript=True)
    tsx_txt = (tmp_path / "react" / "Settings.tsx").read_text(encoding="utf-8")
    assert "defaultChecked={true}" in tsx_txt and "defaultValue=" in tsx_txt
    assert web_res["pages"] == ["index.html"] and react_res["typescript"] is True

    # Game engines: Godot, Unity UI Toolkit, Unity uGUI, Roblox, Unreal UMG
    gd = td.export_screen("settings", "godot", out_dir=str(tmp_path / "godot"))
    tscn = (tmp_path / "godot" / "settings.tscn").read_text(encoding="utf-8")
    assert 'type="HSlider"' in tscn and 'type="CheckButton"' in tscn and 'type="CheckBox"' in tscn and 'type="OptionButton"' in tscn

    ut = td.export_screen("settings", "unity", out_dir=str(tmp_path / "unity"))
    uxml = (tmp_path / "unity" / "settings.uxml").read_text(encoding="utf-8")
    assert "<ui:Slider" in uxml and "<ui:Toggle" in uxml and "<ui:DropdownField" in uxml

    ug = td.export_screen("settings", "unity-ugui", out_dir=str(tmp_path / "ugui"))
    ugui_cs = (tmp_path / "ugui" / "SettingsUGuiBuilder.cs").read_text(encoding="utf-8")
    assert "typeof(Slider)" in ugui_cs and "typeof(Toggle)" in ugui_cs and "typeof(Dropdown)" in ugui_cs

    rb = td.export_screen("settings", "roblox", out_dir=str(tmp_path / "roblox"))
    luau = (tmp_path / "roblox" / "settings.client.luau").read_text(encoding="utf-8")
    assert 'SetAttribute("Checked"' in luau and "Ultra v" in luau

    ue = td.export_screen("settings", "unreal", out_dir=str(tmp_path / "unreal"),
                          unreal_content_path="/Game/UI/Settings")
    ue_py = (tmp_path / "unreal" / "WBP_Settings_build_umg.py").read_text(encoding="utf-8")
    assert "WidgetBlueprintFactory" in ue_py and "unreal.Slider" in ue_py and "unreal.CheckBox" in ue_py and "unreal.ComboBoxString" in ue_py
    compile(ue_py, "WBP_Settings_build_umg.py", "exec")  # valid Python syntax
    assert set(["sl_vol", "tg_vsync", "cb_hdr", "dd_qual"]) <= set(ue["widgets"])

    # Desktop targets: WPF, Avalonia, WinUI, Qt QML, ImGui
    wpf = td.export_screen("settings", "wpf", out_dir=str(tmp_path / "wpf"))
    xaml = (tmp_path / "wpf" / "Settings.xaml").read_text(encoding="utf-8")
    assert "<Slider " in xaml and "<CheckBox " in xaml and "<ComboBox " in xaml and "<ComboBoxItem " in xaml

    winui = td.export_screen("settings", "winui", out_dir=str(tmp_path / "winui"))
    wxaml = (tmp_path / "winui" / "Settings.xaml").read_text(encoding="utf-8")
    assert "<ToggleSwitch " in wxaml and "StepFrequency=" in wxaml

    qt = td.export_screen("settings", "qt-qml", out_dir=str(tmp_path / "qt"))
    qml = (tmp_path / "qt" / "Settings.qml").read_text(encoding="utf-8")
    assert "Slider {" in qml and "Switch {" in qml and "ComboBox {" in qml

    ig = td.export_screen("settings", "imgui", out_dir=str(tmp_path / "imgui"))
    hpp = (tmp_path / "imgui" / "settings_ui.hpp").read_text(encoding="utf-8")
    assert "ImGui::SliderFloat" in hpp and "ImGui::Checkbox" in hpp and "ImGui::Combo" in hpp


def test_3d_perspective_and_curved_visor_hud(ws):
    s.create_canvas("hud_flat", 320, 180, background="#050810")
    s.add_rect("hud_flat", 40, 30, 240, 120, radius=10, fill="#1e293b", stroke={"color": "#38bdf8", "width": 2})

    s.create_canvas("hud_3d", 320, 180, background="#050810")
    s.create_layer("hud_3d", "visor", style={"perspective": {"rotate_y": 24, "rotate_x": -8, "visor_curve": 0.18}})
    s.add_rect("hud_3d", 40, 30, 240, 120, radius=10, fill="#1e293b", stroke={"color": "#38bdf8", "width": 2})

    img_flat = np.asarray(s.store().renderer(s.store().get("hud_flat")).render(), dtype=np.float32)
    img_3d = np.asarray(s.store().renderer(s.store().get("hud_3d")).render(), dtype=np.float32)
    diff = float(np.abs(img_flat - img_3d).mean())
    assert diff > 2.0  # genuinely warped 3D geometry


def test_mcp_app_studio_and_live_preview_v2(ws):
    s.create_canvas("studio_c", 300, 180, background="#0f172a")
    s.create_layer("studio_c", "hud")
    s.add_rect("studio_c", 20, 20, 200, 40, fill="#22c55e", id="hp_bar")
    s.set_binding("studio_c", data={"hp": 80}, target="hp_bar", property="width", expr="hp * 2")
    s.set_state("studio_c", "hover", "hp_bar", {"fill": "#4ade80"})

    assert STUDIO_APP_URI.startswith("ui://") and "ui/initialize" in STUDIO_APP_HTML
    open_res = s.open_studio("studio_c")
    assert open_res["studio"] == "open" and open_res["active"] == "studio_c"
    snap = studio_snapshot(s.store(), "studio_c", data={"hp": 40}, state="hover", include_image=True)
    assert snap["image_data_uri"].startswith("data:image/png;base64,")
    assert snap["layers"][0]["name"] == "hud" and "hover" in snap["states"]

    studio = LiveStudio(s.store, port=0)
    info = studio.start("studio_c")
    try:
        with urllib.request.urlopen(info["url"] + "/api/details/studio_c", timeout=5) as r:
            det = json.loads(r.read().decode("utf-8"))
            assert det["active"] == "studio_c" and det["data"]["hp"] == 80
        with urllib.request.urlopen(info["url"] + "/api/render/studio_c?state=hover&data=%7B%22hp%22%3A25%7D", timeout=5) as r:
            png = r.read()
            assert png[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        studio.stop()


def test_screenshot_v2_visual_diff_and_wcag_widget_audit(ws, tmp_path):
    # Screenshot v2: aligned row + toggle pill + token binding
    s.create_canvas("ss_src", 460, 220, background="#0f172a")
    s.add_rect("ss_src", 30, 40, 180, 48, radius=10, fill="#2563eb")
    s.add_rect("ss_src", 230, 40, 180, 48, radius=10, fill="#2563eb")
    s.add_rect("ss_src", 30, 120, 52, 26, radius=13, fill="#22c55e")
    ss_path = tmp_path / "v2_screen.png"
    s.store().renderer(s.store().get("ss_src")).render().save(ss_path)

    imp = s.import_screenshot(str(ss_path), canvas="ss_v2", ocr="off")
    assert imp["tokens_bound"] >= 1
    assert any(g["direction"] == "row" for g in imp["layout_groups"])

    # Pixel visual_diff in canvas_version
    s.create_canvas("ver_c", 200, 120, background="#0f172a")
    s.add_rect("ver_c", 20, 20, 160, 80, radius=8, fill="#3b82f6", id="card")
    s.canvas_version("ver_c", "save", "v1")
    s.update_element("ver_c", "card", {"fill": "#ef4444"})
    diff_out = tmp_path / "diff.png"
    res = s.canvas_version("ver_c", "visual_diff", "v1", out_path=str(diff_out))
    meta = json.loads(res[0])
    assert meta["changed_pct"] > 20.0 and meta["max_delta"] > 100.0
    assert diff_out.is_file()

    # WCAG contrast audit catches low-contrast input widget
    s.create_canvas("wcag_c", 320, 140, background="#111827")
    s.add_input("wcag_c", 20, 40, 240, 40, value="Dim text", text_color="#263042", fill="#1e293b", id="bad_inp")
    rev = s.review_canvas("wcag_c")
    assert not rev["ok"]
    assert rev["wcag"]["checked_widgets"] == 1
    assert any(i["check"] == "contrast" and "bad_inp" in (i.get("ids") or []) for i in rev["issues"])
