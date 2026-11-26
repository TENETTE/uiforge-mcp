"""Tests for v0.12 features: 2.5D PBR-lite materials/SDF/bump, PackBits PSD, render cache,
data binding, live preview studio, engine controller codegen, Unity uGUI, Tailwind React, and .uiforge/ mode."""
import json
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from uiforge_mcp import binding, materials, render
from uiforge_mcp import server as s
from uiforge_mcp import tools_delivery as td
from uiforge_mcp.store import Store, default_workspace


@pytest.fixture()
def ws(tmp_path):
    render.clear_render_cache()
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    td.live_preview("stop")
    s.set_store(None)


def _arr(canvas="c"):
    st = s.store()
    return np.asarray(st.renderer(st.get(canvas)).render(include_background=False))


def test_pbr_lite_sdf_bump_profiles_and_shine(ws):
    s.create_canvas("c", 140, 100)
    s.add_rect("c", 10, 10, 120, 80, radius=14, id="r1", style={
        "fill": {"type": "shader", "code": "r = edge; g = ridged(x/12, y/12, 3); b = turbulence(x/16, y/16, 3); height = g"},
        "light": {"profile": "machined", "size": 6, "gloss": 0.8, "env": 0.5, "anisotropy": 0.5, "fresnel": 0.4,
                  "bump_strength": 0.6, "shine": 0.5},
    })
    img_bump = _arr()
    assert img_bump[50, 70, 3] > 240
    assert img_bump[20:80, 20:120, 0].mean() > img_bump[11:13, 20:120, 0].mean()

    s.update_element("c", "r1", {"style": {
        "fill": {"type": "shader", "code": "r = edge; g = ridged(x/12, y/12, 3); b = turbulence(x/16, y/16, 3); height = g"},
        "light": {"profile": "machined", "size": 6, "gloss": 0.8, "env": 0.5, "anisotropy": 0.5, "fresnel": 0.4,
                  "bump_strength": 0.0, "shine": 0.5},
    }})
    img_flat = _arr()
    assert np.abs(img_bump.astype(int) - img_flat.astype(int)).mean() > 1.5

    for prof in ("pillow", "engraved"):
        s.update_element("c", "r1", {"style": {"fill": "#3b82f6", "light": {"profile": prof, "size": 8, "depth": 1.1}}})
        assert _arr()[50, 70, 3] > 240


def test_39_materials_and_theme_material_persistence(ws, tmp_path):
    assert len(materials.NAMES) >= 39
    for must in ("liquid_glass", "foil_holographic", "radial_metal", "hammered_gold", "aged_parchment",
                 "obsidian", "jade", "ruby", "emerald", "runic_stone", "energy_shield", "carbon_twill",
                 "clay_3d", "candy_gloss", "enamel", "wax_seal"):
        assert must in materials.NAMES
    s.set_theme(materials={"dark_oak": {"material": "wood", "color": "#4a2c18", "scale": 2}})
    reloaded = Store(tmp_path / "ws")
    assert "dark_oak" in reloaded.theme.get("materials", {})


def test_data_binding_render_preview_and_security(ws):
    s.create_canvas("hud", 320, 80, background="#0f172a")
    s.add_rect("hud", 20, 24, 240, 24, radius=8, id="hp_bar", style={"fill": "#22c55e"})
    s.add_text("hud", "HP {hp}/{max_hp}", 20, 56, id="hp_txt", size=14, color="#ffffff")
    td.set_binding("hud", data={"hp": 50, "max_hp": 100})
    td.set_binding("hud", target="hp_bar", property="width", expr="clamp(hp / max_hp, 0, 1) * 240")
    td.set_binding("hud", target="hp_bar", property="style.fill", expr="where(hp < 30, '#ef4444', '#22c55e')")

    img_half = _arr("hud")
    assert img_half[36, 100, 1] > 150
    assert img_half[36, 200, 1] < 40

    low_canvas = binding.apply_bindings(s.store().get("hud"), {"hp": 20})
    img_low = np.asarray(s.store().renderer(low_canvas).render(include_background=False))
    assert img_low[36, 40, 0] > 200 and img_low[36, 40, 1] < 100

    res = s.preview("hud", data={"hp": 20})
    assert len(res) == 2

    for bad in ("__import__('os')", "hp.__class__", "open('x')", "[1][0]"):
        with pytest.raises(ValueError, match="binding"):
            binding.compile_expr(bad)


def test_engine_controllers_ugui_and_tailwind_react(ws, tmp_path):
    s.create_canvas("menu", 640, 360, background="#111827")
    s.add_rect("menu", 40, 40, 200, 56, radius=12, id="play_btn", style={"fill": "#6366f1"})
    s.add_text("menu", "PLAY {user}", 140, 68, id="play_lbl", anchor="center", size=18, weight=700, color="#ffffff")
    s.store().get("menu")["focus_order"] = ["play_btn"]
    td.set_binding("menu", data={"user": "Nova"})
    td.set_interaction("menu", "play_btn", "click", "url", target="https://example.com", sfx="ui_click")

    g_res = td.export_screen("menu", "godot", out_dir=str(tmp_path / "godot"))
    assert "menu_controller.gd" in g_res["files"]
    gd = (tmp_path / "godot" / "menu_controller.gd").read_text(encoding="utf-8")
    assert "sfx_requested" in gd and "focus_neighbor_bottom" in gd and "set_data" in gd

    u_res = td.export_screen("menu", "unity", out_dir=str(tmp_path / "unity"))
    assert "MenuController.cs" in u_res["files"]
    cs = (tmp_path / "unity" / "MenuController.cs").read_text(encoding="utf-8")
    assert "OnSfx" in cs and "SetData" in cs and "ui_click" in cs

    ug_res = td.export_screen("menu", "unity-ugui", out_dir=str(tmp_path / "ugui"))
    assert "MenuUGuiBuilder.cs" in ug_res["files"]
    ug = (tmp_path / "ugui" / "MenuUGuiBuilder.cs").read_text(encoding="utf-8")
    assert "CanvasScaler" in ug and "RectTransform" in ug

    r_res = s.export_react("menu", out_dir=str(tmp_path / "react"), css="tailwind")
    assert r_res["css"] == "tailwind"
    jsx = (tmp_path / "react" / "Menu.jsx").read_text(encoding="utf-8")
    assert "onSfx" in jsx and "uiforgeApplyData" in jsx and "rounded-[12px]" in jsx
    rt = (tmp_path / "react" / "uiforge-runtime.js").read_text(encoding="utf-8")
    assert "getGamepads" in rt and "ArrowDown" in rt


def test_live_preview_server_serves_state_and_png(ws):
    s.create_canvas("live_c", 200, 120, background="#1e293b")
    s.add_rect("live_c", 20, 20, 160, 80, radius=10, id="box", style={"material": "gold"})
    started = td.live_preview("start", canvas="live_c")
    assert started["running"] and started["url"].startswith("http://127.0.0.1:")
    url = started["url"]
    with urllib.request.urlopen(url + "/") as resp:
        assert resp.status == 200 and b"uiforge-mcp" in resp.read()
    with urllib.request.urlopen(url + "/api/state") as resp:
        state = json.loads(resp.read().decode("utf-8"))
        assert any(c["id"] == "live_c" for c in state["canvases"])
    with urllib.request.urlopen(url + "/api/render/live_c?bg=dark&ids=1&guides=1") as resp:
        png = resp.read()
        assert resp.status == 200 and png[:8] == b"\x89PNG\r\n\x1a\n"
    stopped = td.live_preview("stop")
    assert stopped["running"] is False


def test_packbits_psd_compression_and_local_workspace(ws, tmp_path, monkeypatch):
    s.create_canvas("p", 256, 256, background="#111827")
    s.add_rect("p", 20, 20, 216, 216, radius=16, style={"fill": "#3b82f6"})
    out = tmp_path / "test.psd"
    s.export_psd("p", path=str(out))
    data = out.read_bytes()
    assert data[:4] == b"8BPS"
    assert len(data) < 256 * 256 * 4

    proj = tmp_path / "mygame"
    (proj / ".uiforge").mkdir(parents=True)
    monkeypatch.delenv("UIFORGE_MCP_DIR", raising=False)
    monkeypatch.chdir(proj)
    assert default_workspace() == proj / ".uiforge"


def test_cook_torrance_pbr_metal_clearcoat_and_studio_ibl(ws):
    s.create_canvas("pbr_c", 160, 100)
    s.add_rect("pbr_c", 10, 10, 140, 80, radius=14, id="m1", style={
        "fill": "#e6b038",
        "pbr": {"metallic": 0.98, "roughness": 0.16, "profile": "machined", "studio": "warm", "crown": 0.3},
    })
    gold = _arr("pbr_c")[20:80, 20:140]
    assert gold[..., 3].mean() > 250
    assert gold[..., 0].std() > 18
    assert gold[..., 0].mean() > gold[..., 2].mean() + 40

    s.update_element("pbr_c", "m1", {"style": {
        "fill": "#e11d48",
        "pbr": {"metallic": 0.0, "roughness": 0.08, "clearcoat": 1.0, "sss": 0.5, "profile": "dome", "shine": 0.5},
    }})
    candy = _arr("pbr_c")[20:80, 20:140]
    assert candy[..., 0].mean() > 130 and candy[..., 1].std() > 15


def test_pbr_maps_export_and_custom_hdri_env_map(ws, tmp_path):
    from PIL import Image
    hdri = tmp_path / "env.png"
    env_arr = np.zeros((64, 128, 3), dtype=np.uint8)
    env_arr[:32, :, :] = [240, 210, 170]
    env_arr[32:, :, :] = [20, 40, 90]
    Image.fromarray(env_arr, "RGB").save(hdri)

    s.create_canvas("medallion", 160, 160)
    s.add_ellipse("medallion", 80, 80, 62, 62, id="ring",
                  style={"material": "gold", "pbr": {"metallic": 0.98, "roughness": 0.14, "env_map": str(hdri)}})
    s.add_ellipse("medallion", 80, 80, 28, 28, id="jewel", style={"material": "ruby"})

    g_res = td.export_pbr_maps("medallion", out_dir=str(tmp_path / "pbr_godot"), engine="godot")
    folder = Path(g_res["folder"])
    for key in ("beauty", "albedo", "normal", "roughness", "metallic", "ao", "height", "orm", "emissive"):
        assert (folder / g_res["files"][key]).is_file()
    assert "medallion.canvas_texture.tres" in g_res["extras"]
    tres = (folder / "medallion.canvas_texture.tres").read_text(encoding="utf-8")
    assert "normal_texture" in tres and "diffuse_texture" in tres

    n_gl = np.asarray(Image.open(folder / g_res["files"]["normal"]))
    assert n_gl[80, 80, 2] > 180
    assert n_gl[..., 0].std() > 8

    u_res = td.export_pbr_maps("medallion", out_dir=str(tmp_path / "pbr_ue"), engine="unreal")
    assert u_res["normal_format"] == "directx"
    n_dx = np.asarray(Image.open(Path(u_res["folder"]) / u_res["files"]["normal"]))
    assert not np.array_equal(n_gl[..., 1], n_dx[..., 1])


def test_add_frame_presets_expanded_batch_dotlottie_atlas_and_tsx(ws, tmp_path):
    import zipfile
    s.create_canvas("f_test", 520, 320, background="#0b0f19")
    res = s.add_frame("f_test", 20, 20, 220, 140, preset="rpg_gold", title="INVENTORY", id_prefix="inv")
    assert len(res["ids"]) >= 6 and len(res["inner_box"]) == 4 and res["inner_box"][2] > 120

    s.batch("f_test", [
        {"op": "add_frame", "x": 260, "y": 20, "width": 240, "height": 140, "preset": "scifi_hud", "title": "RADAR", "id_prefix": "hud"},
        {"op": "add_rect", "id": "bar", "x": 280, "y": 90, "width": 160, "height": 18, "radius": 9, "fill": "#22d3ee"},
        {"op": "set_pin", "ids": ["bar"], "x": "stretch", "y": "bottom"},
        {"op": "set_binding", "data": {"hp": 80}, "target": "bar", "property": "width", "expr": "hp * 2"},
        {"op": "set_state", "state": "hover", "id": "bar", "props": {"style": {"fill": "#38bdf8"}}},
        {"op": "set_interaction", "id": "bar", "trigger": "click", "action": "toggle_state", "state": "hover", "sfx": "tap"},
        {"op": "create_animation", "name": "in", "duration": 0.4, "fps": 10},
        {"op": "set_keyframes", "animation": "in", "target": "bar", "property": "opacity", "keyframes": [[0, 0], [0.4, 1]]},
        {"op": "create_animation", "name": "pulse", "duration": 0.4, "fps": 10, "loop": True},
        {"op": "set_keyframes", "animation": "pulse", "target": "bar", "property": "scale", "keyframes": [[0, 1], [0.4, 1.05]]},
    ])
    img = _arr("f_test")
    assert img.shape == (320, 520, 4)

    dl = s.export_animation("f_test", "all", format="dotlottie", path=str(tmp_path / "bundle.lottie"))
    assert dl["count"] == 2 and dl["bytes"] > 100 and dl["spec_version"] == "2"
    assert dl["state_machine"]["states"] == 2
    with zipfile.ZipFile(dl["file"]) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names and "a/in.json" in names and "a/pulse.json" in names
        assert "s/f_test_sm.json" in names
        mf = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert mf["version"] == "2" and mf["initial"]["stateMachine"] == "f_test_sm"

    s.create_canvas("ic1", 48, 48)
    s.add_ellipse("ic1", 24, 24, 18, 18, fill="#f59e0b")
    s.create_canvas("ic2", 48, 48)
    s.add_rect("ic2", 6, 6, 36, 36, radius=8, fill="#38bdf8")

    tp = s.export_atlas(["ic1", "ic2"], path=str(tmp_path / "tp.png"), format="texturepacker")
    tp_json = json.loads(Path(tp["json"]).read_text(encoding="utf-8"))
    assert "ic1.png" in tp_json["frames"] and tp_json["meta"]["app"] == "uiforge-mcp"

    gd = s.export_atlas(["ic1", "ic2"], path=str(tmp_path / "gd.png"), format="godot")
    assert "ic1.atlas.tres" in gd["extras"]

    cs = s.export_atlas(["ic1", "ic2"], path=str(tmp_path / "sp.png"), format="css")
    assert "sp.css" in cs["extras"]

    tsx = s.export_react("f_test", out_dir=str(tmp_path / "react_ts"), css="tailwind", typescript=True)
    assert tsx["typescript"] is True and tsx["components"][0].endswith(".tsx")
    code = (tmp_path / "react_ts" / tsx["components"][0]).read_text(encoding="utf-8")
    assert "export interface" in code and "useRef<HTMLElement | null>(null)" in code
