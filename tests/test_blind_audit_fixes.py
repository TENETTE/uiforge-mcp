"""Regression tests for bugs discovered during zero-context blind AI game-UI testing."""

from __future__ import annotations

import re

import pytest

from uiforge_mcp import server as s, tools_delivery as td
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def test_batch_delete_layer_keep_and_delete_elements(ws):
    s.create_canvas("bdel", 200, 120, background="#0f172a")
    s.batch("bdel", [
        {"op": "create_layer", "name": "keep_me"},
        {"op": "add_rect", "x": 10, "y": 10, "width": 40, "height": 40, "fill": "#38bdf8", "id": "r_keep"},
        {"op": "create_layer", "name": "drop_me"},
        {"op": "add_rect", "x": 70, "y": 10, "width": 40, "height": 40, "fill": "#f43f5e", "id": "r_drop"},
        {"op": "create_layer", "name": "legacy_drop"},
        {"op": "add_rect", "x": 130, "y": 10, "width": 40, "height": 40, "fill": "#22c55e", "id": "r_legacy"},
    ])
    res = s.batch("bdel", [
        {"op": "delete_layer", "layer": "keep_me", "keep_elements": True},
        {"op": "delete_layer", "layer": "drop_me", "keep_elements": False},
        {"op": "delete_layer", "layer": "legacy_drop", "delete_elements": True},
    ])
    assert res["results"][0]["elements_kept"] == ["r_keep"]
    assert res["results"][1]["elements_deleted"] == ["r_drop"]
    assert res["results"][2]["elements_deleted"] == ["r_legacy"]
    c = s.store().get("bdel")
    ids = {e["id"] for e in c["elements"]}
    assert ids == {"r_keep"}
    assert "layer" not in c["elements"][0]
    assert c["layers"] == []


def test_open_stroke_icons_export_valid_svg_and_web_paths(ws, tmp_path):
    s.create_canvas("ico_svg", 320, 80, background="#0b1120")
    open_icons = ["sliders", "arrow_left", "check", "info", "medkit"]
    for i, name in enumerate(open_icons):
        s.add_icon("ico_svg", name, 12 + i * 60, 16, size=40, color="#22d3ee", id=f"ic_{name}")

    svg_path = tmp_path / "icons.svg"
    s.export_svg("ico_svg", path=str(svg_path))
    svg_txt = svg_path.read_text(encoding="utf-8")

    # No empty d="" paths anywhere
    assert 'd=""' not in svg_txt
    # Sliders has 6 two-point open subpaths -> must contain stroke-linecap="round" and 6 M... L... without Z
    sliders_grp = re.search(r'<g id="ic_sliders">.*?</g>', svg_txt, re.S)
    assert sliders_grp is not None
    sliders_d = re.search(r'<path[^>]*\bd="([^"]+)"', sliders_grp.group(0)).group(1)
    assert sliders_d.count("M") == 6
    assert " Z" not in sliders_d
    assert 'stroke-linecap="round"' in sliders_grp.group(0)

    # Checkmark must remain an open stroke (not force-closed into a triangle)
    check_grp = re.search(r'<g id="ic_check">.*?</g>', svg_txt, re.S)
    assert check_grp is not None
    check_d = re.search(r'<path[^>]*\bd="([^"]+)"', check_grp.group(0)).group(1)
    assert " Z" not in check_d

    # Same fix propagates cleanly into export_web inline SVGs
    s.export_web("ico_svg", out_dir=str(tmp_path / "web"))
    html_txt = (tmp_path / "web" / "index.html").read_text(encoding="utf-8")
    assert 'd=""' not in html_txt


def test_web_and_react_ts_tailwind_widget_labels_features_and_bindings(ws, tmp_path):
    s.create_canvas("ui_web", 800, 540, background="#070b14")
    s.set_binding("ui_web", data={"pilot": "VANGUARD", "fov": 95, "vsync": True, "mode": "Balanced", "angle": 45})
    s.add_text("ui_web", "98420", x=40, y=30, size=24, font="Inter", features=["tnum"], color="#f8fafc", id="score")
    s.add_rect("ui_web", 40, 80, 160, 44, radius=10, corner="cut", fill="#101b2e",
               stroke={"color": "#22d3ee", "width": 1.5}, id="cut_btn", group="cta")
    s.set_state("ui_web", "hover", "cut_btn", {"style": {"glow": {"color": "#22d3ee", "blur": 12}}})
    s.set_link("ui_web", "cut_btn", "ui_web")
    s.add_rect("ui_web", 260, 80, 10, 40, fill="#22d3ee", id="needle")
    s.set_binding("ui_web", target="needle", property="rotation", expr="angle")
    s.add_input("ui_web", 40, 180, 260, 40, label="Pilot Callsign", value="VANGUARD", max_length=24,
                bind="pilot", id="inp_pilot")
    s.add_slider("ui_web", 40, 270, 260, 28, min=60, max=120, value=95, label="Field of View",
                 show_value=True, bind="fov", id="sl_fov")
    s.add_toggle("ui_web", 40, 340, 52, 28, checked=True, variant="switch", label="V-Sync",
                 bind="vsync", id="tg_vsync")
    s.add_dropdown("ui_web", 40, 420, 260, 40, options=["Performance", "Balanced", "Quality"],
                   selected="Balanced", label="Preset", bind="mode", id="dd_mode")

    # Web export checks
    s.export_web("ui_web", out_dir=str(tmp_path / "web"))
    html_txt = (tmp_path / "web" / "index.html").read_text(encoding="utf-8")
    css_txt = (tmp_path / "web" / "styles.css").read_text(encoding="utf-8")
    js_txt = (tmp_path / "web" / "app.js").read_text(encoding="utf-8")

    # 1. Single-quoted font-feature-settings inside style="..."
    assert "font-feature-settings:'tnum' 1" in html_txt
    assert 'font-feature-settings:"tnum"' not in html_txt
    # 2. Native widget labels, live slider value readout, and switch styling
    assert '<label class="el w-label" for="inp_pilot"' in html_txt and ">Pilot Callsign</label>" in html_txt
    assert '<label class="el w-label" for="sl_fov"' in html_txt and ">Field of View</label>" in html_txt
    assert 'data-val-for="sl_fov"' in html_txt and ">95</span>" in html_txt
    assert 'class="el input toggle-switch"' in html_txt
    assert '<label class="el w-toggle-lbl" for="tg_vsync"' in html_txt and ">V-Sync</label>" in html_txt
    assert '<label class="el w-label" for="dd_mode"' in html_txt and ">Preset</label>" in html_txt
    assert ".toggle-switch{" in css_txt and ".toggle-switch:checked::after{" in css_txt
    # 3. Cut-corner hover CSS fallback + rotation binding in runtime JS
    assert ".g-cta:hover #cut_btn{" in html_txt and "drop-shadow(" in html_txt
    assert "b.prop === 'rotation'" in js_txt and "data-val-for" in js_txt

    # React TypeScript + Tailwind checks
    s.export_react("ui_web", out_dir=str(tmp_path / "react"), css="tailwind", typescript=True)
    tsx_txt = (tmp_path / "react" / "UiWeb.tsx").read_text(encoding="utf-8")
    assert "sel absolute m-0ect" not in tsx_txt
    assert "el absolute m-0 select" in tsx_txt
    assert "tabIndex={0}" in tsx_txt and 'tabIndex={"0"}' not in tsx_txt
    assert "maxLength={24}" in tsx_txt and 'maxLength={"24"}' not in tsx_txt
    assert "onNavigate(to || href, mode || 'navigate')" in tsx_txt
    assert 'htmlFor={"inp_pilot"}' in tsx_txt
    assert (tmp_path / "react" / "uiforge-runtime.d.ts").is_file()
    assert (tmp_path / "react" / "uiforge-assets.d.ts").is_file()


def test_perspective_layer_rasterization_warns_when_dynamic_elements_inside(ws, tmp_path):
    s.create_canvas("visor_dyn", 400, 220, background="#050810")
    s.create_layer("visor_dyn", "hud_3d", style={"perspective": {"rotate_y": 18, "visor_curve": 0.14}})
    s.add_rect("visor_dyn", 40, 60, 200, 20, fill="#22d3ee", id="hp_fill")
    s.set_binding("visor_dyn", data={"hp": 70}, target="hp_fill", property="width", expr="hp * 2")
    res = s.export_web("visor_dyn", out_dir=str(tmp_path / "web"))
    assert any("hud_3d" in n and "hp_fill" in n for n in res["notes"])


def test_scifi_hud_and_cyber_tech_frames_clear_titles_and_integer_coords(ws):
    s.create_canvas("frm_audit", 960, 420, background="#060b14")
    s.add_frame("frm_audit", 30, 30, 420, 320, preset="scifi_hud", title="SYSTEM TELEMETRY", id_prefix="sc")
    s.add_frame("frm_audit", 500, 30, 420, 320, preset="cyber_tech", title="WEAPON MATRIX", id_prefix="cy")
    c = s.store().get("frm_audit")
    by_id = {e["id"]: e for e in c["elements"]}
    # scifi_hud title x clears bracket_0 (arm up to 28 -> title >= x + 34)
    assert by_id["sc_title"]["x"] >= 30 + 30
    # cyber_tech title x clears title_tag (x+18+6=x+24 -> title at x+34)
    assert by_id["cy_title"]["x"] >= 500 + 34
    rev = s.review_canvas("frm_audit")
    title_overlap = [i for i in rev.get("issues", []) if "sc_title" in str(i) and "overlap" in str(i).lower()]
    assert not title_overlap


def test_godot_controller_wires_all_interactive_widgets_and_labels(ws, tmp_path):
    s.create_canvas("gd_ctrl", 600, 420, background="#0b1120")
    s.set_binding("gd_ctrl", data={"name": "Nova", "gain": 80, "bloom": True, "diff": "Hard"})
    s.add_input("gd_ctrl", 40, 60, 240, 38, label="Name", value="Nova", bind="name", id="in_name")
    s.add_slider("gd_ctrl", 40, 140, 240, 28, min=0, max=100, value=80, label="Gain", bind="gain", id="sl_gain")
    s.add_toggle("gd_ctrl", 40, 210, 52, 28, checked=True, variant="switch", label="Bloom", bind="bloom", id="tg_bloom")
    s.add_dropdown("gd_ctrl", 40, 290, 240, 38, options=["Normal", "Hard"], selected="Hard",
                   label="Difficulty", bind="diff", id="dd_diff")

    td.export_screen("gd_ctrl", "godot", out_dir=str(tmp_path / "godot"))
    tscn = (tmp_path / "godot" / "gd_ctrl.tscn").read_text(encoding="utf-8")
    gd = (tmp_path / "godot" / "gd_ctrl_controller.gd").read_text(encoding="utf-8")

    assert 'name="in_name_Label" type="Label"' in tscn
    assert 'name="sl_gain_Label" type="Label"' in tscn
    assert 'name="dd_diff_Label" type="Label"' in tscn
    assert "text_changed.connect" in gd
    assert "value_changed.connect" in gd
    assert "toggled.connect" in gd
    assert "item_selected.connect" in gd


def test_opentype_missing_feature_warning_only_mentions_small_caps_for_smcp(ws):
    s.create_canvas("ot_warn", 240, 80, background="#0f172a")
    res = s.add_text("ot_warn", "12345", x=12, y=16, size=20, font="Orbitron", features=["tnum"], id="num")
    # Orbitron lacks tnum (if bundled without tnum), any warning must NOT give misleading smcp hint
    for w in res.get("warnings") or []:
        if "tnum" in w and "smcp" not in w:
            assert "small caps" not in w.lower()


def test_svg_gauge_needle_preserves_pivot_and_baked_rotation_delta(ws, tmp_path):
    s.create_canvas("gauge_web", 400, 400, background="#050810")
    s.add_polygon("gauge_web", points=[[180, 196], [340, 199], [340, 201], [180, 204]],
                  origin=[200, 200], rotation=340, fill="#f43f5e", id="needle")
    s.set_binding("gauge_web", data={"rpm": 7.6}, target="needle", property="rotation", expr="135 + rpm / 10 * 270")
    s.create_animation("gauge_web", "boot", duration=0.5, loop=False)
    s.set_keyframes("gauge_web", "boot", "needle", "rotation", [
        {"t": 0.0, "value": 135},
        {"t": 0.5, "value": 340},
    ])
    s.export_web("gauge_web", out_dir=str(tmp_path / "web"))
    html_txt = (tmp_path / "web" / "index.html").read_text(encoding="utf-8")
    js_txt = (tmp_path / "web" / "app.js").read_text(encoding="utf-8")

    # SVG container sets transform-origin to exact hub pivot (200px 200px) and records baked rotation (135 + 7.6/10*270 = 340.2)
    assert "transform-origin:200px 200px" in html_txt
    assert 'data-base-rot="340.2"' in html_txt
    # Keyframes emit delta relative to baked 340.2deg (from -205.2deg to -0.2deg, never double-rotated +340deg)
    assert "rotate(-205.2deg)" in html_txt
    assert "100%{transform:translate(0px,0px) rotate(-0.2deg)" in html_txt
    # Runtime subtracts dataset.baseRot
    assert "el.dataset.baseRot" in js_txt

