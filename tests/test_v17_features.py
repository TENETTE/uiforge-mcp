"""Comprehensive tests for Phase 2 (v0.17.0) 10/10 engine & Studio UI upgrades:
- Flex/Grid/Split layout engine (`add_split`, `add_grid`, `add_stack` justify / height:'fill' / spacer)
- Game UI composite suite (`add_gauge`, `add_slot`, `add_tabs`, `add_stat_card`) with theme inheritance & WCAG AA
- Expression helpers (`format_num`, `concat`, `upper`, `lower`) across Python, JS and GDScript
- Working `set_data` / `reset_data` interactions + cross-screen shared state
- Compact `batch` summary (>15 ops), `_decor` lint suppression & `preview_background` separation
- `export_web(single_file=True)`, `export_react(scaffold=True)`, `export_project`, `qa_screen`
- Human UI & Combined Mode Studio UI exposing all 108 core operations
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from uiforge_mcp import binding, core, reference, server as s, studio_ui, tools_delivery as td
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def test_split_grid_and_flex_stack_zero_math_layout(ws):
    s.set_theme(style_preset="scifi", quality="advanced")
    s.create_canvas("layout_scr", 1280, 720, background="#070b14")
    res = s.batch("layout_scr", [
        {"op": "add_split", "id": "cols", "x": 40, "y": 40, "width": 1200, "height": 640,
         "direction": "row", "sizes": ["25%", "1fr", "25%"], "gap": 20,
         "names": ["left_col", "mid_col", "right_col"],
         "children": {
             "left_col": [
                 {"op": "add_frame", "preset": "scifi_hud", "title": "ARMORY", "id_prefix": "arm",
                  "x": 0, "y": 0, "width": "fill", "height": "fill"},
                 {"op": "add_stack", "in": "arm.inner_box", "direction": "column", "gap": 12, "align": "stretch",
                  "children": [
                      {"op": "add_input", "id": "in_search", "label": "Search", "placeholder": "Filter..."},
                      {"op": "add_scroll", "id": "sc_mods", "height": "fill",
                       "items": [{"title": "Railgun", "badge": "MK-IV"}, {"title": "Ion Lance", "badge": "EXOTIC"}]},
                  ]},
             ],
             "mid_col": [
                 {"op": "add_grid", "cols": 2, "gap": 16, "x": 0, "y": 0, "width": "fill",
                  "children": [
                      {"op": "add_slot", "id": "hp_1", "label": "Primary", "sublabel": "Railgun", "rarity": "legendary"},
                      {"op": "add_slot", "id": "hp_2", "label": "Shield", "sublabel": "Aegis", "rarity": "rare"},
                      {"op": "add_stat_card", "id": "kpi_wide", "col_span": 2, "label": "COMBAT RATING", "value": "2,480 PTS", "icon": "star"},
                  ]},
             ],
             "right_col": [
                 {"op": "add_stack", "direction": "row", "justify": "space-between", "x": 0, "y": 580, "width": "fill",
                  "children": [
                      {"op": "add_button", "id": "btn_save", "label": "Apply", "width": 120, "variant": "primary"},
                      {"op": "add_button", "id": "btn_rst", "label": "Reset", "width": 120, "variant": "danger"},
                  ]},
             ],
         }},
    ])
    boxes = res["splits"]
    assert set(boxes.keys()) == {"left_col", "mid_col", "right_col"}
    # 25% of (1200 - 40 gap) = 290; mid_col = 580; right_col = 290
    assert boxes["left_col"][2] == pytest.approx(290.0, abs=1.0)
    assert boxes["mid_col"][2] == pytest.approx(580.0, abs=1.0)
    assert boxes["right_col"][2] == pytest.approx(290.0, abs=1.0)

    c = s.store().get("layout_scr")
    by_id = {e["id"]: e for e in c["elements"]}
    # Scroll widget with height:"fill" stretched well past its default 200px to fill armory frame!
    assert by_id["sc_mods"]["height"] > 400
    # col_span=2 stat card spans full mid_col width
    assert by_id["kpi_wide_bg"]["width"] == pytest.approx(580.0, abs=2.0)
    # justify="space-between" pushed btn_rst flush to the right edge of right_col
    assert by_id["btn_rst_bg"]["x"] + by_id["btn_rst_bg"]["width"] == pytest.approx(boxes["right_col"][0] + boxes["right_col"][2], abs=2.0)


def test_game_ui_composites_gauge_slot_tabs_stat_card_and_wcag_clean(ws):
    s.set_theme(
        style_preset="scifi", quality="advanced",
        colors={"bg": "#070b14", "surface": "#101726", "primary": "#f59e0b", "accent": "#38bdf8",
                "text": "#f1f5f9", "muted": "#cbd5e1", "danger": "#f43f5e", "success": "#4ade80"},
    )
    s.create_canvas("hud_v17", 1280, 720, background="#070b14")
    s.create_canvas("hangar_v17", 1280, 720, background="#070b14")
    s.batch("hud_v17", [
        {"op": "add_tabs", "id": "nav", "x": 40, "y": 24, "active": 0, "items": [
            {"label": "Combat HUD", "icon": "crosshair", "link": "hud_v17"},
            {"label": "Hangar Bay", "icon": "sliders", "link": "hangar_v17"},
        ]},
        {"op": "add_stat_card", "id": "credits", "x": 1020, "y": 26, "label": "CR", "value": "14,850",
         "icon": "star", "compact": True},
        {"op": "add_gauge", "id": "vel", "cx": 960, "cy": 360, "radius": 110, "value": 572,
         "max_value": 800, "unit": "M/S", "label": "VELOCITY", "bind_value": "speed"},
        {"op": "add_slot", "id": "ab_1", "x": 40, "y": 580, "width": 210, "height": 76,
         "icon": "bolt", "label": "Overburn", "sublabel": "READY", "keycap": "1",
         "rarity": "legendary", "cooldown": 0.25, "bind_cooldown": "cd_1"},
        {"op": "add_stat_card", "id": "therm", "x": 40, "y": 260, "width": 280, "height": 78,
         "label": "CORE THERMAL", "value": "418 C", "subvalue": "98.4%", "icon": "flame", "badge": "NOMINAL"},
    ])
    c = s.store().get("hud_v17")
    assert c["data"]["speed"] == 572 and c["data"]["cd_1"] == 0.25
    assert any(b["target"] == "vel_arc" and b["property"] == "end_angle" for b in c["bindings"])
    assert any(b["target"] == "vel_needle" and b["property"] == "rotation" for b in c["bindings"])
    assert any(b["target"] == "ab_1_cd" and b["property"] == "height" for b in c["bindings"])

    rev = s.review_canvas("hud_v17")
    warns = [i for i in rev["issues"] if i["severity"] in ("warn", "error")]
    assert not warns, f"Composite widgets should pass review_canvas cleanly out of the box: {warns}"


def test_binding_helpers_set_data_reset_data_and_shared_state(ws, tmp_path):
    assert binding.eval_expr("concat(format_num(score), ' ', upper(unit))", {"score": 2480, "unit": "pts"}) == "2,480 PTS"
    assert binding.eval_expr("format_num(eff, 1)", {"eff": 98.44}) == "98.4"
    assert binding.eval_expr("lower('HELIOS')", {}) == "helios"

    js = binding.js_expr("concat(format_num(score, 0), ' ', upper(unit))")
    assert "toLocaleString" in js and "toUpperCase" in js
    gd = binding.gdscript_expr("concat(format_num(score, 1), ' ', lower(unit))")
    assert "_fmt_num" in gd and ".to_lower()" in gd

    s.create_canvas("cfg_scr", 640, 360, preview_background={"type": "linear", "angle": 180, "stops": ["#070b14", "#101726"]})
    s.batch("cfg_scr", [
        {"op": "add_slider", "id": "sl_vol", "x": 40, "y": 60, "width": 240, "value": 80, "label": "Volume", "bind": "vol"},
        {"op": "add_text", "id": "txt_vol", "x": 40, "y": 120, "text": "{vol}%", "size": 20, "color": "#ffffff"},
        {"op": "add_button", "id": "btn_max", "x": 40, "y": 180, "width": 140, "height": 44, "label": "Max Vol"},
        {"op": "add_button", "id": "btn_rst", "x": 200, "y": 180, "width": 140, "height": 44, "label": "Reset", "variant": "danger"},
        {"op": "set_binding", "data": {"vol": 80}, "target": "txt_vol", "property": "text", "expr": "concat(format_num(vol), '%')"},
        {"op": "set_interaction", "id": "group:btn_max", "trigger": "click", "action": "set_data", "data": {"vol": 100}},
        {"op": "set_interaction", "id": "group:btn_rst", "trigger": "click", "action": "reset_data"},
    ])
    # preview_background stays transparent on PNG export, while appearing in Web export!
    png_res = s.export_png("cfg_scr", path=str(tmp_path / "cfg_transparent.png"))
    from PIL import Image
    im = Image.open(png_res["files"][0]["file"]).convert("RGBA")
    assert im.getpixel((2, 2))[3] == 0

    web_dir = tmp_path / "web_shared"
    s.export_web(["cfg_scr"], out_dir=str(web_dir), shared_state=True)
    html_txt = (web_dir / "index.html").read_text(encoding="utf-8")
    app_js = (web_dir / "app.js").read_text(encoding="utf-8")
    assert "linear-gradient(" in html_txt
    assert "uiforge_shared_state" in app_js and "a === 'set_data'" in app_js and "a === 'reset_data'" in app_js

    gd_dir = tmp_path / "godot_ctrl"
    td.export_screen("cfg_scr", engine="godot", out_dir=str(gd_dir))
    ctrl = (gd_dir / "cfg_scr_controller.gd").read_text(encoding="utf-8")
    assert "func _fmt_num(" in ctrl and 'act == "set_data"' in ctrl and 'act == "reset_data"' in ctrl


def test_compact_batch_single_file_html_vite_scaffold_export_project_and_qa_screen(ws, tmp_path):
    s.set_theme(style_preset="scifi", quality="standard")
    s.create_canvas("scr_hud", 800, 480, background="#070b14")
    s.create_canvas("scr_cfg", 800, 480, background="#070b14")

    # >15 ops triggers automatic compact batch response
    ops = [{"op": "add_frame", "x": 20, "y": 20, "width": 760, "height": 440, "preset": "scifi_hud", "title": "HUD", "id_prefix": "h"}]
    for i in range(16):
        ops.append({"op": "add_rect", "id": f"r_{i}", "x": 40 + (i % 8) * 80, "y": 80 + (i // 8) * 60,
                    "width": 60, "height": 40, "fill": "#1e293b", "radius": 6})
    bres = s.batch("scr_hud", ops)
    assert bres.get("compact") is True and bres["op_count"] == 17 and "h" in bres["frames"]

    s.add_button("scr_hud", 40, 380, 180, 44, label="Settings", link="scr_cfg", id="go_cfg")
    s.add_button("scr_cfg", 40, 380, 180, 44, label="Back", link="back", id="go_back")

    # 1. Single-file HTML prototype (no assets folder, both pages inlined into 1 index.html)
    sf_dir = tmp_path / "web_sf"
    sf_res = s.export_web(["scr_hud", "scr_cfg"], out_dir=str(sf_dir), single_file=True)
    assert sf_res["single_file"] is True and sf_res["pages"] == ["index.html"]
    assert not (sf_dir / "assets").exists() and not (sf_dir / "app.js").exists()
    sf_html = (sf_dir / "index.html").read_text(encoding="utf-8")
    assert 'data-screen="scr_hud"' in sf_html and 'data-screen="scr_cfg"' in sf_html

    # 2. React Vite runnable starter scaffold
    rv_dir = tmp_path / "react_vite"
    rv_res = s.export_react(["scr_hud", "scr_cfg"], out_dir=str(rv_dir), typescript=True, css="tailwind", scaffold=True)
    assert (rv_dir / "package.json").is_file() and (rv_dir / "vite.config.ts").is_file()
    assert (rv_dir / "src" / "App.tsx").is_file() and (rv_dir / "src" / "main.tsx").is_file()
    assert "package.json" in rv_res["scaffold_files"]

    # 3. Multi-screen export_project (Godot with UIManager.gd + tokens/ui_theme.gd)
    gp_dir = tmp_path / "godot_proj"
    gp_res = td.export_project(["scr_hud", "scr_cfg"], engine="godot", out_dir=str(gp_dir))
    assert (gp_dir / "UIManager.gd").is_file() and (gp_dir / "tokens" / "ui_theme.gd").is_file()
    assert (gp_dir / "screens" / "scr_hud" / "scr_hud.tscn").is_file()
    assert (gp_dir / "screens" / "scr_cfg" / "scr_cfg.tscn").is_file()
    assert "UIManager.gd" in gp_res["router"]

    # 4. One-call qa_screen
    qa_out = s.qa_screen("scr_hud", simulate="deuteranopia", check_pseudo_long=True)
    assert len(qa_out) == 2
    qa_meta = json.loads(qa_out[1])
    assert qa_meta["canvas"] == "scr_hud"
    assert "NORMAL" in qa_meta["panels"] and "SIM: DEUTERANOPIA" in qa_meta["panels"] and "PSEUDO-LONG (+100%)" in qa_meta["panels"]


def test_studio_ui_and_cheatsheet_expose_all_108_v17_operations(ws):
    assert "add_gauge" in reference.CHEATSHEET and "add_slot" in reference.CHEATSHEET
    assert "add_split" in reference.CHEATSHEET and "add_grid" in reference.CHEATSHEET
    assert "qa_screen" in reference.CHEATSHEET and "export_project" in reference.CHEATSHEET
    assert "set_data" in reference.CHEATSHEET and "format_num" in reference.CHEATSHEET

    ops = core.list_operations()
    op_names = {o["name"] for o in ops}
    assert len(ops) >= 108
    for expected in ("add_gauge", "add_slot", "add_tabs", "add_stat_card", "add_grid", "add_split", "qa_screen", "export_project"):
        assert expected in op_names

    srv = studio_ui.StudioServer(s.store, mode="combined", port=0)
    srv.start()
    try:
        html_txt = urllib.request.urlopen(f"{srv.url}/").read().decode("utf-8")
        for chip in ('data-create="gauge"', 'data-create="slot"', 'data-create="tabs"',
                     'data-create="stat_card"', 'data-create="grid"', 'data-create="split"',
                     'id="btn-run-qa"', 'data-exp="web-single"', 'data-exp="react-vite"', 'data-exp="project-godot"'):
            assert chip in html_txt
    finally:
        srv.stop()
