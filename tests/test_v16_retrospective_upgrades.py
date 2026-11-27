"""Tests for all 7 retrospective AI-DX upgrades:
1. Live CSS 3D perspective layers (visor_curve=0), cut-corner clip-path & SVG fill/stroke hover CSS, live SVG end_angle
2. Batch container-relative placement (`in: "<frame>.inner_box"`) & `add_stack` auto-headroom flow layout
3. High-level composite widgets: `add_button` (icon, keycap, auto states, link, SFX) & `add_progress_bar` (auto bindings)
4. Consistent element API: `add_icon` absolute x/y update (no double-offset) & `add_ticks` 360° closed ring alignment
5. Godot 4 executable GDScript `set_binding` expressions & `key:` `_unhandled_input` shortcuts
6. Shared deduplicated `@keyframes` + `review_canvas` binding/animation conflict detection
7. Rich MCP discovery: `uiforge://cheatsheet` & `uiforge://materials` metadata (`text_safe`, `finish`, `best_for`)
"""

from __future__ import annotations

import math
import re

import pytest

from uiforge_mcp import binding, materials, reference, render, server as s, tools_delivery as td
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def test_discovery_cheatsheet_and_materials_catalog_metadata(ws):
    assert "add_button" in reference.CHEATSHEET
    assert "add_progress_bar" in reference.CHEATSHEET
    assert "add_stack" in reference.CHEATSHEET
    assert "inner_box" in reference.CHEATSHEET
    assert "visor_curve" in reference.CHEATSHEET

    cat = materials.material_catalog()
    assert len(cat) == len(materials.NAMES) == 39
    by_name = {m["name"]: m for m in cat}
    assert by_name["obsidian"]["text_safe"] is False
    assert by_name["obsidian"]["finish"] == "glossy"
    assert by_name["rubber"]["text_safe"] is True
    assert by_name["carbon_twill"]["text_safe"] is True
    assert by_name["chrome"]["text_safe"] is False


def test_add_icon_absolute_xy_update_has_no_double_offset(ws):
    s.create_canvas("ico_abs", 500, 200, background="#0b1120")
    s.add_icon("ico_abs", "shield", x=40, y=50, size=32, color="#22d3ee", id="ic1")
    el = s.store().find(s.store().get("ico_abs"), "ic1")
    assert el["x"] == 40.0 and el["y"] == 50.0
    b_before = s.store().renderer(s.store().get("ico_abs")).element_box(el)
    assert 38 <= b_before[0] <= 55 and 48 <= b_before[1] <= 65

    # Updating x/y must move to exact absolute (300, 100), NOT (340, 150)
    s.update_element("ico_abs", "ic1", {"x": 300, "y": 100})
    el2 = s.store().find(s.store().get("ico_abs"), "ic1")
    b_after = s.store().renderer(s.store().get("ico_abs")).element_box(el2)
    assert abs((b_after[0] - b_before[0]) - 260.0) < 1.0
    assert abs((b_after[1] - b_before[1]) - 50.0) < 1.0


def test_add_ticks_full_360_ring_aligns_cardinal_majors(ws):
    s.create_canvas("ring360", 300, 300, background="#060b14")
    # Passing count=49 (48 intervals + 1) on 0..360 must auto-collapse the closing duplicate so 8 majors sit at 45° multiples
    res = s.add_ticks("ring360", cx=150, cy=150, radius=100, start_angle=0, end_angle=360,
                      count=49, major_every=6, labels=["E", "SE", "S", "SW", "W", "NW", "N", "NE"], id="rad")
    assert len(res["created"]) == 10  # minor + major + 8 labels
    c = s.store().get("ring360")
    major_el = next(e for e in c["elements"] if e["id"] == "rad_major")
    g = render.vector_geometry(major_el, 4.0)
    assert len(g.lines) == 8
    angles = sorted(round(math.degrees(math.atan2(pts[0][1] - 150, pts[0][0] - 150)) % 360) for pts, *_ in g.lines)
    assert angles == [0, 45, 90, 135, 180, 225, 270, 315]


def test_add_button_and_progress_bar_single_call_composites(ws, tmp_path):
    s.set_theme(style_preset="scifi", quality="advanced")
    s.create_canvas("hud_comp", 640, 360, background="#060b14")
    s.create_canvas("target_scr", 640, 360, background="#060b14")

    btn = s.add_button("hud_comp", 40, 40, 240, 48, label="Loadout", icon="sliders", keycap="TAB",
                       variant="primary", link="target_scr", sfx="ui_open", id="btn_lo")
    assert btn["body_id"] == "btn_lo_bg"
    assert "btn_lo_icon" in btn["ids"] and "btn_lo_keycap" in btn["ids"] and "btn_lo_label" in btn["ids"]

    bar = s.add_progress_bar("hud_comp", 40, 140, 320, 16, value=82, max_value=100,
                             label="Hull Integrity", bind_value="hp", bind_max="max_hp",
                             low_threshold=0.3, id="hp")
    assert bar["track_id"] == "hp_track" and bar["fill_id"] == "hp_fill"
    c = s.store().get("hud_comp")
    assert c["data"]["hp"] == 82 and c["data"]["max_hp"] == 100
    assert any(b["target"] == "hp_fill" and b["property"] == "width" for b in c["bindings"])
    assert any(b["target"] == "hp_fill" and b["property"] == "style.fill" for b in c["bindings"])
    assert "hover" in c["states"] and "pressed" in c["states"] and "disabled" in c["states"]

    rev = s.review_canvas("hud_comp")
    overflows = [i for i in rev["issues"] if i["check"] == "overflow"]
    assert not overflows


def test_batch_in_inner_box_and_add_stack_single_turn_panel(ws):
    s.create_canvas("one_turn", 600, 560, background="#060b14")
    res = s.batch("one_turn", [
        {"op": "add_frame", "x": 30, "y": 30, "width": 540, "height": 500,
         "preset": "scifi_hud", "title": "SYSTEMS", "id_prefix": "sys"},
        {"op": "add_stack", "in": "sys.inner_box", "x": 0, "y": 4, "direction": "column",
         "gap": 14, "align": "stretch", "children": [
             {"op": "add_input", "label": "Callsign", "value": "NOVA-01", "bind": "callsign", "id": "in_cs"},
             {"op": "add_dropdown", "label": "Weapon", "options": ["Railgun", "Lance"], "bind": "wpn", "id": "dd_wpn"},
             {"op": "add_slider", "label": "Audio Gain", "min": 0, "max": 100, "value": 80, "bind": "gain", "id": "sl_gain"},
             {"op": "add_progress_bar", "label": "Reactor Output", "value": 76, "max_value": 100, "id": "pb_rx"},
             {"op": "add_button", "label": "Deploy", "icon": "check", "variant": "gold", "id": "btn_dep"},
         ]},
    ])
    inner = res["results"][0]["inner_box"]
    c = s.store().get("one_turn")
    by_id = {e["id"]: e for e in c["elements"]}
    # Input sits inside sys.inner_box with full stretched width and 22px label headroom above y
    assert by_id["in_cs"]["x"] == pytest.approx(inner[0], abs=1.0)
    assert by_id["in_cs"]["width"] == pytest.approx(inner[2], abs=1.0)
    assert by_id["in_cs"]["y"] >= inner[1] + 22
    # Dropdown sits cleanly below input + gap + its own 22px label headroom (zero collision!)
    assert by_id["dd_wpn"]["y"] >= by_id["in_cs"]["y"] + by_id["in_cs"]["height"] + 14 + 22 - 0.5
    # Button sits inside frame vertically
    assert by_id["btn_dep_bg"]["y"] + by_id["btn_dep_bg"]["height"] <= inner[1] + inner[3] + 5


def test_review_canvas_warns_on_binding_animation_conflict(ws):
    s.create_canvas("conflict_c", 300, 120, background="#0b1120")
    s.add_rect("conflict_c", 20, 40, 200, 24, fill="#22d3ee", id="bar")
    s.set_binding("conflict_c", data={"hp": 50}, target="bar", property="width", expr="hp * 2")
    s.create_animation("conflict_c", "intro", duration=0.5)
    s.set_keyframes("conflict_c", "intro", "bar", "width", [{"t": 0, "value": 0}, {"t": 0.5, "value": 100}])
    rev = s.review_canvas("conflict_c")
    assert any(i["check"] == "binding_animation_conflict" and "bar" in (i.get("ids") or []) for i in rev["issues"])


def test_web_live_css_3d_perspective_cut_clip_shared_keyframes_and_arc_binding(ws, tmp_path):
    s.create_canvas("web3d", 800, 500, background="#060b14")
    # Flat 3D perspective layer (visor_curve=0) must remain LIVE CSS 3D, not flattened to PNG!
    s.create_layer("web3d", "tilt_hud", style={"perspective": {"rotate_y": 20, "rotate_x": -6, "visor_curve": 0}})
    s.add_rect("web3d", 40, 40, 200, 30, radius=8, corner="cut", fill="#22d3ee", id="live_bar")
    s.set_binding("web3d", data={"hp": 80, "ang": 300}, target="live_bar", property="width", expr="hp * 2")
    s.add_arc("web3d", cx=400, cy=250, radius=80, start_angle=135, end_angle=300, thickness=10, color="#22d3ee", id="live_arc")
    s.set_binding("web3d", target="live_arc", property="end_angle", expr="ang")

    # Stroked cut-corner button gets direct SVG path fill/stroke hover rules
    s.create_layer("web3d", "ui")
    s.add_rect("web3d", 40, 120, 180, 44, radius=10, corner="cut", fill="#101b2e",
               stroke={"color": "#22d3ee", "width": 1.5}, id="cut_stroked", group="gbtn")
    s.set_state("web3d", "hover", "cut_stroked", {"fill": "#1e3a5f", "stroke": {"color": "#f59e0b", "width": 1.5}})

    # 6 elements sharing identical fade-in keyframes must deduplicate to ONE @keyframes block
    s.create_animation("web3d", "fade_in", duration=0.4)
    for i in range(6):
        eid = f"dot_{i}"
        s.add_rect("web3d", 40 + i * 30, 220, 20, 20, fill="#38bdf8", id=eid)
        s.set_keyframes("web3d", "fade_in", eid, "opacity", [{"t": 0, "value": 0}, {"t": 0.4, "value": 1}])

    res = s.export_web("web3d", out_dir=str(tmp_path / "web"))
    html_txt = (tmp_path / "web" / "index.html").read_text(encoding="utf-8")
    js_txt = (tmp_path / "web" / "app.js").read_text(encoding="utf-8")

    # 1. Live CSS 3D wrapper preserved (NOT rasterized!)
    assert 'class="layer layer-3d"' in html_txt
    assert "perspective(" in html_txt and "rotateY(20deg)" in html_txt
    assert "web3d:layer:tilt_hud" not in res["embedded_as_image"]
    # 2. Strokeless cut-corner rect uses CSS clip-path:polygon(...)
    assert "clip-path:polygon(" in html_txt
    # 3. Stroked cut-corner SVG button gets exact SVG fill & stroke hover CSS
    assert 'path[fill]:not([fill="none"]){fill:#1e3a5f!important' in html_txt
    assert "path[stroke]{stroke:#f59e0b!important" in html_txt
    # 4. Live SVG end_angle binding metadata + JS runtime handler
    assert "data-arc=" in html_txt and "b.prop === 'end_angle'" in js_txt
    # 5. Deduplicated @keyframes: only 1 @keyframes rule emitted for all 6 identical dot animations!
    kf_matches = re.findall(r"@keyframes a-web3d-fade_in-", html_txt)
    assert len(kf_matches) == 1
    assert "#dot_0" in html_txt and "#dot_5" in html_txt


def test_godot_executable_gdscript_bindings_and_key_shortcuts(ws, tmp_path):
    assert "clampf(" in binding.gdscript_expr("clamp(hp / max_hp, 0, 1) * 400")
    assert "float(" in binding.gdscript_expr("hp / max_hp")
    assert "if" in binding.gdscript_expr("where(hp < 30, '#fb6b84', '#4ade80')")

    s.create_canvas("gd_exec", 640, 360, background="#060b14")
    s.create_canvas("loadout", 640, 360, background="#060b14")
    s.add_rect("gd_exec", 40, 40, 200, 20, fill="#4ade80", id="hp_fill")
    s.set_binding("gd_exec", data={"hp": 80, "max_hp": 100}, target="hp_fill", property="width",
                  expr="clamp(hp / max_hp, 0, 1) * 200")
    s.set_binding("gd_exec", target="hp_fill", property="style.fill",
                  expr="where(hp < 30, '#fb6b84', '#4ade80')")
    s.set_interaction("gd_exec", "canvas", "key:Tab", "navigate", target="loadout", sfx="ui_open")

    td.export_screen("gd_exec", "godot", out_dir=str(tmp_path / "godot"))
    gd = (tmp_path / "godot" / "gd_exec_controller.gd").read_text(encoding="utf-8")
    assert gd.count("var b_hp_fill :=") == 1
    assert "b_hp_fill.size.x = maxf(0.0, float(" in gd
    assert "b_hp_fill.modulate = Color.html(str(" in gd
    assert "func _unhandled_input(event: InputEvent) -> void:" in gd
    assert 'if k == "tab":' in gd


def test_human_combined_studio_ui_and_mcp_app_expose_all_v16_features(ws):
    import json
    import urllib.request
    from uiforge_mcp.studio_app import STUDIO_APP_HTML, studio_snapshot
    from uiforge_mcp.studio_ui import StudioServer

    for mode in ("ui", "combined"):
        srv = StudioServer(s.store, port=0, mode=mode)
        info = srv.start()
        try:
            with urllib.request.urlopen(info["url"] + "/api/bootstrap", timeout=5) as r:
                boot = json.loads(r.read().decode("utf-8"))
            assert boot["mode"] == mode
            assert len(boot["materials"]["catalog"]) == 39
            op_names = {o["name"]: o["category"] for o in boot["operations"]}
            assert op_names["add_button"] == "widgets"
            assert op_names["add_progress_bar"] == "widgets"
            assert op_names["add_stack"] == "widgets"

            with urllib.request.urlopen(info["url"] + "/api/cheatsheet", timeout=5) as r:
                cs = json.loads(r.read().decode("utf-8"))
            assert "add_button" in cs["cheatsheet"] and "add_stack" in cs["cheatsheet"]

            with urllib.request.urlopen(info["url"] + "/", timeout=5) as r:
                html = r.read().decode("utf-8")
            assert 'data-create="button"' in html and 'data-create="progress_bar"' in html
            assert 'data-create="stack"' in html and 'data-create="ticks"' in html
            assert 'id="btn-mat-textsafe"' in html and 'id="btn-cheatsheet"' in html
            assert 'id="ins-corner"' in html and 'id="btn-apply-layer-3d"' in html

            # Exercise /api/op in both Human Mode and Combined Mode
            def post_op(op, args):
                req = urllib.request.Request(
                    info["url"] + "/api/op",
                    data=json.dumps({"op": op, "args": args}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            cname = f"studio_{mode}"
            assert post_op("create_canvas", {"name": cname, "width": 800, "height": 480, "background": "#070b14"})["ok"]
            assert post_op("create_layer", {"canvas": cname, "name": "hud_3d", "style": {"perspective": {"rotate_y": 15, "visor_curve": 0}}})["ok"]
            assert post_op("add_frame", {"canvas": cname, "x": 20, "y": 20, "width": 760, "height": 440, "preset": "scifi_hud", "id_prefix": "f1"})["ok"]
            assert post_op("add_button", {"canvas": cname, "x": 50, "y": 80, "width": 220, "height": 48, "label": "Deploy", "icon": "rocket", "keycap": "E", "id": "b1"})["ok"]
            assert post_op("add_progress_bar", {"canvas": cname, "x": 50, "y": 160, "width": 260, "height": 16, "label": "Shield", "bind_value": "sh", "bind_max": "max_sh", "id": "pb1"})["ok"]
            assert post_op("create_animation", {"canvas": cname, "name": "intro", "duration": 0.4})["ok"]
            assert post_op("set_keyframes", {"canvas": cname, "animation": "intro", "target": "pb1_fill", "property": "width", "keyframes": [[0, 0], [0.4, 200]]})["ok"]

            with urllib.request.urlopen(info["url"] + f"/api/canvas/{cname}", timeout=5) as r:
                cjson = json.loads(r.read().decode("utf-8"))
            assert "f1" in cjson["boxes"]
            assert cjson["layers"][0]["perspective"]["rotate_y"] == 15

            # MCP App Studio + Live Preview v2 snapshot carries 3D layer perspective + binding/anim conflicts
            snap = studio_snapshot(s.store(), cname, include_image=False)
            assert snap["layers"][0]["perspective"]["rotate_y"] == 15
            assert any("pb1_fill.width" in cf for cf in snap["conflicts"])
            assert "3D CSS" in STUDIO_APP_HTML and "conflicts" in STUDIO_APP_HTML
        finally:
            srv.stop()

