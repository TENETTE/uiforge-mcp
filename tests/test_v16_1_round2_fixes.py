"""Regression tests for all 7 bugs & export flaws discovered in the Round-2 blind Game UI test."""

from __future__ import annotations

import re

import pytest

from uiforge_mcp import binding, server as s, tools_delivery as td
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def test_bug1_stack_buttons_isolated_groups_and_no_double_nav(ws, tmp_path):
    s.set_theme(style_preset="scifi", quality="advanced")
    s.create_canvas("scr_a", 800, 200, background="#070b14")
    s.create_canvas("scr_b", 800, 200, background="#070b14")
    s.create_canvas("scr_c", 800, 200, background="#070b14")

    s.add_stack(
        "scr_a", x=20, y=40, direction="row", gap=16, group="footer_bar",
        children=[
            {"op": "add_button", "id": "btn_b", "label": "Go B", "link": "scr_b", "sfx": "ui_click"},
            {"op": "add_button", "id": "btn_c", "label": "Go C", "link": "scr_c", "sfx": "ui_click"},
            {"op": "add_button", "id": "btn_back", "label": "Back", "link": "back", "sfx": "ui_click"},
        ],
    )
    c = s.store().get("scr_a")
    ix = c.get("interactions") or []
    ids = [r["id"] for r in ix]
    # Each button must have its own distinct group interaction, never sharing group:footer_bar
    assert "group:footer_bar" not in ids
    assert set(ids) == {"group:btn_b", "group:btn_c", "group:btn_back"}

    # Web export runtime must guard [data-href] clicks when a click navigation rule already exists in data-ix
    web_out = tmp_path / "web_nav"
    s.export_web(["scr_a", "scr_b", "scr_c"], out_dir=str(web_out))
    app_js = (web_out / "app.js").read_text(encoding="utf-8")
    assert "ixEl.dataset.ix" in app_js
    assert "r.action === 'navigate'" in app_js


def test_bug2_token_alpha_bindings_live_bar_conic_arc_and_godot_split(ws, tmp_path):
    s.set_theme(
        style_preset="scifi", quality="advanced",
        colors={"bg": "#070b14", "surface": "#101726", "primary": "#f59e0b", "accent": "#38bdf8",
                "text": "#f1f5f9", "muted": "#bccbe0", "success": "#4ade80", "danger": "#f43f5e"},
    )
    colors = s.store().theme["colors"]
    js_out = binding.js_expr("where((hull / max_hull) < 0.35, '$danger', '#4ade80@0.5')", theme_colors=colors)
    assert "$danger" not in js_out and "@0.5" not in js_out
    assert "#f43f5e" in js_out and "rgba(74,222,128,0.502)" in js_out

    gd_out = binding.gdscript_expr("where((hull / max_hull) < 0.35, '$danger', '#f43f5e@0.28')", theme_colors=colors)
    assert "$danger" not in gd_out and "@0.28" not in gd_out
    assert "#f43f5e" in gd_out and "#f43f5e47" in gd_out

    s.create_canvas("hud_live", 640, 360, background="#070b14")
    s.batch("hud_live", [
        {"op": "add_progress_bar", "id": "bar_hull", "x": 30, "y": 40, "width": 280, "height": 16,
         "value": 80, "max_value": 100, "label": "Hull", "color": "$success", "low_color": "$danger",
         "bind_value": "hull", "bind_max": "max_hull", "group": "left_visor"},
        {"op": "add_rect", "id": "status_pill", "x": 30, "y": 90, "width": 220, "height": 36, "radius": 6,
         "fill": "#4ade80@0.2", "stroke": {"color": "$success", "width": 1.5}, "group": "left_visor"},
        {"op": "add_arc", "id": "speed_arc", "cx": 480, "cy": 180, "radius": 80, "start_angle": 135, "end_angle": 320,
         "thickness": 10, "color": {"type": "conic", "from": 135, "to": 405, "stops": ["#38bdf8", "#f59e0b", "#f43f5e"]},
         "group": "right_visor"},
        {"op": "set_binding", "data": {"speed": 500}, "target": "speed_arc", "property": "end_angle",
         "expr": "135 + clamp(speed / 800, 0, 1) * 270"},
        {"op": "set_binding", "target": "status_pill", "property": "style.stroke.color",
         "expr": "where(hull < 30, '$danger', '$success')"},
    ])

    web_dir = tmp_path / "web_live"
    s.export_web(["hud_live"], out_dir=str(web_dir))
    html_txt = (web_dir / "index.html").read_text(encoding="utf-8")
    app_js = (web_dir / "app.js").read_text(encoding="utf-8")
    # bar_hull_fill must be a live CSS div (not a static <img>)
    assert '<div class="el box" id="bar_hull_fill"' in html_txt
    # speed_arc with conic fill + end_angle binding must export as live SVG with data-arc
    assert 'id="speed_arc"' in html_txt and "data-arc=" in html_txt
    # Resolved tokens in UIFORGE_IX bindings (zero raw $danger / $success)
    ix_json = html_txt.split("window.UIFORGE_IX=", 1)[1].split("</script>", 1)[0]
    assert "$danger" not in ix_json and "$success" not in ix_json
    assert "style.stroke.color" in app_js

    # Godot export_screen must split dynamic bound elements out of parent group PNGs and resolve tokens
    gd_dir = tmp_path / "godot_live"
    res = td.export_screen("hud_live", engine="godot", out_dir=str(gd_dir))
    assert "bar_hull_fill" in res["pieces"]
    assert "status_pill" in res["pieces"]
    assert "speed_arc" in res["pieces"]
    gd_ctrl = (gd_dir / "hud_live_controller.gd").read_text(encoding="utf-8")
    assert "$danger" not in gd_ctrl and "$success" not in gd_ctrl
    assert 'get_node_or_null("bar_hull_fill")' in gd_ctrl


def test_bug3_export_spec_does_not_crash_on_thin_lines_at_1080p(ws, tmp_path):
    s.create_canvas("spec_1080", 1920, 1080, background="#070b14")
    s.batch("spec_1080", [
        {"op": "add_frame", "x": 40, "y": 40, "width": 500, "height": 400, "preset": "scifi_hud", "title": "HUD"},
        {"op": "add_line", "id": "thin_h", "points": [[40, 500], [1880, 500]], "width": 1, "color": "#38bdf8"},
        {"op": "add_line", "id": "thin_v", "points": [[960, 100], [960, 980]], "width": 1, "color": "#f59e0b"},
    ])
    out = td.export_spec("spec_1080", out_dir=str(tmp_path / "specs"))
    assert len(out) == 2
    assert (tmp_path / "specs" / "spec_1080.spec.png").is_file()
    assert (tmp_path / "specs" / "spec_1080.spec.json").is_file()


def test_bug4_batch_in_inner_box_resolves_add_text_across_multiple_frames(ws):
    s.create_canvas("two_frm", 1920, 1080, background="#070b14")
    res = s.batch("two_frm", [
        {"op": "add_frame", "x": 40, "y": 100, "width": 400, "height": 300, "preset": "scifi_hud", "id_prefix": "left_f"},
        {"op": "add_text", "id": "t_left", "in": "left_f.inner_box", "x": 16, "y": 24, "text": "LEFT", "color": "#ffffff"},
        {"op": "add_frame", "x": 1440, "y": 100, "width": 400, "height": 300, "preset": "scifi_hud", "id_prefix": "right_f"},
        {"op": "add_text", "id": "t_right", "in": "right_f.inner_box", "x": 16, "y": 24, "text": "RIGHT", "color": "#ffffff"},
    ])
    r_inner = res["results"][2]["inner_box"]
    c = s.store().get("two_frm")
    t_right = next(e for e in c["elements"] if e["id"] == "t_right")
    assert t_right["x"] == pytest.approx(r_inner[0] + 16, abs=1.0)
    assert t_right["y"] == pytest.approx(r_inner[1] + 24, abs=1.0)


def test_bug5_add_button_variants_and_keycaps_pass_review_canvas(ws):
    s.set_theme(
        style_preset="scifi", quality="advanced",
        colors={"bg": "#070b14", "surface": "#101726", "primary": "#f59e0b", "accent": "#38bdf8",
                "text": "#f1f5f9", "muted": "#bccbe0", "danger": "#f43f5e"},
    )
    s.create_canvas("btn_wcag", 900, 160, background="#070b14")
    s.batch("btn_wcag", [
        {"op": "add_button", "id": "b_pri", "x": 20, "y": 50, "width": 200, "height": 48,
         "label": "Deploy", "icon": "play", "keycap": "ESC", "variant": "primary"},
        {"op": "add_button", "id": "b_gold", "x": 240, "y": 50, "width": 200, "height": 48,
         "label": "Upgrade", "icon": "star", "keycap": "TAB", "variant": "gold"},
        {"op": "add_button", "id": "b_dng", "x": 460, "y": 50, "width": 200, "height": 48,
         "label": "Reset", "icon": "trash", "keycap": "DEL", "variant": "danger"},
        {"op": "add_button", "id": "b_sec", "x": 680, "y": 50, "width": 200, "height": 48,
         "label": "Config", "icon": "settings", "keycap": "F1", "variant": "secondary"},
    ])
    rev = s.review_canvas("btn_wcag")
    warns = [i for i in rev["issues"] if i["severity"] in ("warn", "error")]
    assert not warns, f"Unexpected review warnings on default add_button variants: {warns}"


def test_bug6_review_canvas_accurate_wcag_on_3d_perspective_layer(ws):
    s.create_canvas("hud_3d_wcag", 1280, 720, background="#070b14")
    s.batch("hud_3d_wcag", [
        {"op": "create_layer", "name": "left_3d", "style": {"perspective": {"rotate_y": 18, "rotate_x": -5, "visor_curve": 0}}},
        {"op": "add_frame", "x": 60, "y": 140, "width": 380, "height": 420, "preset": "scifi_hud",
         "title": "CHASSIS INTEGRITY", "id_prefix": "p3d", "layer": "left_3d"},
        {"op": "add_text", "id": "p3d_status", "in": "p3d.inner_box", "x": 16, "y": 60,
         "text": "ALL SYSTEMS NOMINAL", "size": 20, "weight": 700, "color": "#f8fafc", "layer": "left_3d"},
    ])
    rev = s.review_canvas("hud_3d_wcag")
    contrast_warns = [i for i in rev["issues"] if i["check"] == "contrast"]
    assert not contrast_warns, f"False contrast warnings on 3D perspective layer: {contrast_warns}"
    assert rev["wcag"]["checked_texts"] >= 2
    assert rev["wcag"]["aa_pass"] is True


def test_bug7_lenient_remove_interaction_and_web_export_cleanliness(ws, tmp_path):
    s.create_canvas("clean_web", 640, 360, background={"type": "linear", "angle": 180, "stops": ["#070b14", "#101726"]})
    s.create_canvas("other_scr", 640, 360, background="#070b14")
    s.batch("clean_web", [
        {"op": "add_rect", "id": "slot_1", "x": 40, "y": 40, "width": 120, "height": 60, "radius": 8,
         "corner": "cut", "fill": "#101726", "stroke": {"color": "#38bdf8", "width": 1.5}},
        {"op": "add_rect", "id": "slot_2", "x": 180, "y": 40, "width": 120, "height": 60, "radius": 8,
         "fill": "#101726", "stroke": {"color": "#38bdf8", "width": 1.5}},
        {"op": "add_rect", "id": "glow_dot", "x": 400, "y": 60, "width": 20, "height": 20, "radius": 10,
         "fill": "#f59e0b", "style": {"glow": {"color": "#f59e0b", "blur": 8}}},
        {"op": "set_state", "state": "selected", "id": "slot_1", "props": {"style": {"stroke": {"color": "#f59e0b", "width": 2}}}},
        {"op": "set_state", "state": "selected", "id": "slot_2", "props": {"style": {"stroke": {"color": "#f59e0b", "width": 2}}}},
        {"op": "set_interaction", "id": "slot_1", "trigger": "click", "action": "toggle_state", "state": "selected"},
        {"op": "set_interaction", "id": "slot_2", "trigger": "click", "action": "navigate", "target": "other_scr"},
        {"op": "create_animation", "name": "glow_only", "duration": 1.0, "loop": True},
        {"op": "set_keyframes", "animation": "glow_only", "target": "glow_dot", "property": "style.glow.blur",
         "keyframes": [[0, 6], [0.5, 18], [1.0, 6]]},
    ])
    # Removing a navigate rule without passing target must succeed
    res_rm = td.set_interaction("clean_web", id="slot_2", trigger="click", action="navigate", remove=True)
    assert all(r["id"] != "slot_2" for r in res_rm["interactions"])
    # Removing a stale rule referencing an already-emptied group must not raise
    td.set_interaction("clean_web", id="group:deleted_grp", trigger="click", action="back", remove=True)

    out_dir = tmp_path / "web_clean"
    s.export_web(["clean_web", "other_scr"], out_dir=str(out_dir))
    html_txt = (out_dir / "index.html").read_text(encoding="utf-8")
    app_js = (out_dir / "app.js").read_text(encoding="utf-8")

    # 1. Pure gradient canvas background exports as CSS, NOT a PNG file
    assert not (out_dir / "assets" / "clean_web-background.png").exists()
    assert "linear-gradient(" in html_txt
    # 2. No duplicate DOM id between wrapper <div id="slot_1"> and inner SVG <g>/<path>
    assert len(re.findall(r'\bid="slot_1"', html_txt)) == 1
    assert 'id="slot_1-svg"' in html_txt
    # 3. Non-CSS glow-only animation does NOT emit a useless no-op @keyframes block
    assert "@keyframes a-clean_web-glow_only-glow_dot" not in html_txt
    # 4. Element-scoped state selector (#slot_1.s-selected) & stateHost() present in runtime
    assert "#slot_1.s-selected" in html_txt
    assert "function stateHost" in app_js
