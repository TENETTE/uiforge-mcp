"""Tests for v0.13 modular features: cross-GPU WebGPU backend (wgpu-py), Radiance .hdr & pure-Python
OpenEXR .exr IBL + workspace environment, upgraded 9-preset AAA procedural frames, dotLottie v2 state
machines, native Input & Scroll widgets across Web/React/Godot/Unity/Roblox, C#/.NET (WPF, Avalonia,
WinUI) & C++ (Qt QML, Dear ImGui) desktop exporters, and OpenCV import_screenshot."""

import json
import struct
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from game_ui_mcp import frames, gpu, gpu_wgpu, pbr, render, shader
from game_ui_mcp import server as s
from game_ui_mcp import tools_delivery as td
from game_ui_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    render.clear_render_cache()
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    gpu.select_backend("auto")
    s.set_store(None)


def _write_test_hdr(path: Path, w: int = 32, h: int = 16) -> None:
    header = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {h} +X {w}\n".encode("ascii")
    body = bytearray()
    for y in range(h):
        for _ in range(w):
            r, g, b = (2.6, 1.9, 0.8) if y < h // 2 else (0.12, 0.28, 0.65)
            m = max(r, g, b)
            exp = int(np.floor(np.log2(m))) + 1
            sc = 256.0 / (2.0 ** exp)
            body.extend([int(r * sc), int(g * sc), int(b * sc), exp + 128])
    path.write_bytes(header + bytes(body))


def _write_test_exr(path: Path, w: int = 32, h: int = 16) -> None:
    hdr = bytearray(struct.pack("<II", 20000630, 2))

    def attr(name: str, typ: str, val: bytes) -> bytes:
        return name.encode() + b"\x00" + typ.encode() + b"\x00" + struct.pack("<I", len(val)) + val

    ch = b""
    for cname in ("B", "G", "R"):
        ch += cname.encode() + b"\x00" + struct.pack("<iB3sii", 2, 0, b"\x00\x00\x00", 1, 1)
    ch += b"\x00"
    hdr += attr("channels", "chlist", ch)
    hdr += attr("compression", "compression", bytes([0]))
    hdr += attr("dataWindow", "box2i", struct.pack("<iiii", 0, 0, w - 1, h - 1))
    hdr += attr("displayWindow", "box2i", struct.pack("<iiii", 0, 0, w - 1, h - 1))
    hdr += attr("lineOrder", "lineOrder", bytes([0]))
    hdr += b"\x00"
    row_bytes = w * 4 * 3
    data_start = len(hdr) + h * 8
    for y in range(h):
        hdr += struct.pack("<Q", data_start + y * (8 + row_bytes))
    for y in range(h):
        b_row = np.full(w, 3.0 if y < h // 2 else 0.15, dtype=np.float32)
        g_row = np.full(w, 1.4 if y < h // 2 else 0.35, dtype=np.float32)
        r_row = np.full(w, 0.7 if y < h // 2 else 1.25, dtype=np.float32)
        hdr += struct.pack("<iI", y, row_bytes) + b_row.tobytes() + g_row.tobytes() + r_row.tobytes()
    path.write_bytes(bytes(hdr))


def test_wgpu_backend_registry_and_hardware_parity(ws):
    info = gpu.info()
    assert "backend" in info and "wgpu" in info and "cuda" in info
    with pytest.raises(ValueError):
        gpu.select_backend("nonexistent_gpu")
    gpu.select_backend("cpu")
    assert gpu.backend_name(512 * 512) == "cpu"

    if not gpu_wgpu.available():
        pytest.skip("No WebGPU adapter available on this host")

    code = (
        "n = fbm(u * 4.0, v * 4.0, 4); "
        "w = ridged(u * 5.0, v * 5.0, 3); "
        "vv = voronoi(u * 4.0, v * 4.0); "
        "r = clamp(0.2 + 0.5 * n + 0.2 * w, 0.0, 1.0); "
        "g = clamp(0.15 + 0.4 * vv, 0.0, 1.0); "
        "b = clamp(0.4 + 0.3 * sin(u * 6.28), 0.0, 1.0); "
        "height = clamp(0.5 * n + 0.5 * w, 0.0, 1.0)"
    )
    spec = {"type": "shader", "code": code}
    sz = (256, 256)
    box = (0.0, 0.0, 256.0, 256.0)

    gpu.select_backend("cpu")
    cpu_rgba, cpu_h = shader.evaluate_surface(spec, sz, box, 1.0, {}, want_height=True)
    gpu.select_backend("wgpu")
    assert gpu.backend_name(256 * 256) == "wgpu"
    wgpu_rgba, wgpu_h = shader.evaluate_surface(spec, sz, box, 1.0, {}, want_height=True)
    assert np.max(np.abs(wgpu_rgba - cpu_rgba)) < 1e-2
    assert np.max(np.abs(wgpu_h - cpu_h)) < 1e-4

    fill = Image.new("RGBA", (256, 256), (220, 178, 86, 255))
    arr_m = np.zeros((256, 256), dtype=np.uint8)
    arr_m[20:236, 20:236] = 255
    mask = Image.fromarray(arr_m, "L")
    pspec = {"metallic": 0.94, "roughness": 0.22, "bevel_size": 12, "bevel_depth": 1.2, "clearcoat": 0.25}
    gpu.select_backend("cpu")
    p_cpu = np.asarray(pbr.shade_pbr(fill, mask, pspec, 1.0), dtype=np.float32)
    gpu.select_backend("wgpu")
    p_wgpu = np.asarray(pbr.shade_pbr(fill, mask, pspec, 1.0), dtype=np.float32)
    assert np.mean(np.abs(p_wgpu - p_cpu)) < 6.0


def test_hdr_and_exr_ibl_workspace_environment(ws, tmp_path):
    hdr_path = tmp_path / "warm_sky.hdr"
    exr_path = tmp_path / "cool_sky.exr"
    _write_test_hdr(hdr_path)
    _write_test_exr(exr_path)

    dec_hdr = pbr._decode_rgbe_hdr(hdr_path)
    assert dec_hdr.shape == (16, 32, 3) and float(dec_hdr.max()) > 2.0
    dec_exr = pbr._decode_exr(exr_path)
    assert dec_exr.shape == (16, 32, 3) and float(dec_exr[2, 2, 2]) > 2.5

    s.create_canvas("ibl_c", 140, 140)
    s.add_ellipse("ibl_c", 70, 70, 52, 52, id="orb", style={"material": "chrome"})

    res_t = s.set_theme(environment={"env_map": str(hdr_path), "rotation": 30, "intensity": 1.2})
    assert res_t["environment"]["env_map"].endswith("warm_sky.hdr")
    warm_arr = np.asarray(s.store().renderer(s.store().get("ibl_c")).render(include_background=False))

    res_c = s.update_canvas("ibl_c", environment={"env_map": str(exr_path), "rotation": 90, "intensity": 1.2})
    assert res_c["environment"]["env_map"].endswith("cool_sky.exr")
    cool_arr = np.asarray(s.store().renderer(s.store().get("ibl_c")).render(include_background=False))

    assert np.abs(warm_arr.astype(float) - cool_arr.astype(float)).mean() > 4.0

    reloaded = Store(tmp_path / "ws")
    assert reloaded.theme["environment"]["env_map"].endswith("warm_sky.hdr")


def test_all_nine_aaa_procedural_frames(ws):
    assert len(frames.FRAME_PRESETS) == 9
    assert "royal_ornate" in frames.FRAME_PRESETS and "fantasy_parchment" in frames.FRAME_PRESETS
    s.create_canvas("f_all", 340, 260, background="#0f121b")
    for preset in frames.FRAME_PRESETS:
        s.create_canvas(f"f_{preset}", 340, 260, background="#0f121b")
        res = s.add_frame(f"f_{preset}", 16, 16, 308, 228, preset=preset, title=preset.upper(), id_prefix=preset)
        assert len(res["ids"]) >= 4 and res["inner_box"][2] > 180 and res["inner_box"][3] > 100
        img = np.asarray(s.store().renderer(s.store().get(f"f_{preset}")).render(include_background=False))
        assert img[..., 3].max() == 255


def test_dotlottie_v2_state_machine_spec(ws, tmp_path):
    s.create_canvas("btn_sm", 200, 80, background="#0f172a")
    s.add_rect("btn_sm", 20, 16, 160, 48, radius=12, id="btn", fill="#6366f1")
    td.set_binding("btn_sm", data={"energy": 100, "armed": False})
    s.create_animation("btn_sm", "idle", duration=0.5, fps=10, loop=True)
    s.set_keyframes("btn_sm", "idle", "btn", "scale", [[0, 1.0], [0.25, 1.03], [0.5, 1.0]])
    s.create_animation("btn_sm", "hover", duration=0.3, fps=10, loop=False)
    s.set_keyframes("btn_sm", "hover", "btn", "scale", [[0, 1.0], [0.3, 1.1]])
    td.set_interaction("btn_sm", "btn", "hover", "play", animation="hover")

    out = tmp_path / "btn.lottie"
    res = s.export_animation("btn_sm", "all", format="dotlottie", path=str(out))
    assert res["spec_version"] == "2" and res["count"] == 2
    assert res["state_machine"]["states"] == 2 and res["state_machine"]["interactions"] >= 2

    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "a/idle.json", "a/hover.json", "s/btn_sm_sm.json"} <= names
        mf = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert mf["version"] == "2" and mf["initial"]["stateMachine"] == "btn_sm_sm"
        sm = json.loads(zf.read("s/btn_sm_sm.json").decode("utf-8"))
        assert sm["initial"] == "idle"
        assert any(st["type"] == "PlaybackState" and st["name"] == "idle" for st in sm["states"])
        assert any(it["type"] == "PointerEnter" for it in sm["interactions"])
        assert any(inp["name"] == "energy" and inp["type"] == "Numeric" for inp in sm["inputs"])


def test_scroll_and_input_widgets_across_all_engines_and_desktop(ws, tmp_path):
    s.create_canvas("dash", 640, 400, background="#0b1020")
    s.create_canvas("app", 640, 400, background="#0b1020")
    s.batch("app", [
        {"op": "add_input", "id": "user_in", "x": 32, "y": 48, "width": 240, "height": 42,
         "label": "Username", "placeholder": "Enter name", "value": "Ada", "bind": "username", "focused": True},
        {"op": "add_input", "id": "pass_in", "x": 32, "y": 124, "width": 240, "height": 42,
         "label": "Password", "placeholder": "Secret", "value": "1234", "input_type": "password", "bind": "pwd"},
        {"op": "add_scroll", "id": "feed", "x": 310, "y": 36, "width": 290, "height": 300, "scroll_offset": 0.25,
         "items": [{"title": "Quest A", "subtitle": "Ready", "badge": "NEW"}, "Quest B", "Quest C"]},
        {"op": "add_rect", "id": "go_btn", "x": 32, "y": 200, "width": 240, "height": 44, "radius": 10, "fill": "#38bdf8"},
        {"op": "add_text", "id": "go_txt", "text": "SIGN IN", "x": 152, "y": 222, "anchor": "center", "size": 15, "weight": 700, "color": "#0b1020"},
        {"op": "set_binding", "data": {"username": "Ada", "pwd": "1234"}},
        {"op": "set_interaction", "id": "go_btn", "trigger": "click", "action": "navigate", "target": "dash", "sfx": "ok"},
    ])

    rendered = np.asarray(s.store().renderer(s.store().get("app")).render())
    assert rendered.shape == (400, 640, 4) and rendered[..., 3].min() == 255

    rx = s.export_react("app", out_dir=str(tmp_path / "react"), typescript=True)
    tsx = (tmp_path / "react" / rx["components"][0]).read_text(encoding="utf-8")
    assert "<input" in tsx and 'type={"password"}' in tsx and "overflowY" in tsx and "defaultValue" in tsx

    g = td.export_screen("app", "godot", out_dir=str(tmp_path / "godot"))
    tscn = (tmp_path / "godot" / "app.tscn").read_text(encoding="utf-8")
    gd = (tmp_path / "godot" / "app_controller.gd").read_text(encoding="utf-8")
    assert 'type="LineEdit"' in tscn and "secret = true" in tscn and 'type="ScrollContainer"' in tscn
    assert "text_changed" in gd

    u = td.export_screen("app", "unity", out_dir=str(tmp_path / "unity"))
    uxml = (tmp_path / "unity" / "app.uxml").read_text(encoding="utf-8")
    ucs = (tmp_path / "unity" / "AppController.cs").read_text(encoding="utf-8")
    assert "<ui:TextField" in uxml and 'password="true"' in uxml and "<ui:ScrollView" in uxml
    assert "RegisterValueChangedCallback" in ucs

    ug = td.export_screen("app", "unity-ugui", out_dir=str(tmp_path / "ugui"))
    ug_cs = (tmp_path / "ugui" / "AppUGuiBuilder.cs").read_text(encoding="utf-8")
    assert "typeof(InputField)" in ug_cs and "typeof(ScrollRect)" in ug_cs

    rb = td.export_screen("app", "roblox", out_dir=str(tmp_path / "roblox"))
    luau = (tmp_path / "roblox" / "app.client.luau").read_text(encoding="utf-8")
    assert 'Instance.new("TextBox")' in luau and 'Instance.new("ScrollingFrame")' in luau

    wpf = td.export_screen("app", "wpf", out_dir=str(tmp_path / "wpf"))
    wpf_xaml = (tmp_path / "wpf" / "App.xaml").read_text(encoding="utf-8")
    wpf_vm = (tmp_path / "wpf" / "AppViewModel.cs").read_text(encoding="utf-8")
    assert "<TextBox" in wpf_xaml and "<PasswordBox" in wpf_xaml and "<ScrollViewer" in wpf_xaml
    assert "INotifyPropertyChanged" in wpf_vm and "RelayCommand" in wpf_vm

    av = td.export_screen("app", "avalonia", out_dir=str(tmp_path / "avalonia"))
    axaml = (tmp_path / "avalonia" / "App.axaml").read_text(encoding="utf-8")
    assert "https://github.com/avaloniaui" in axaml and 'PasswordChar="•"' in axaml and "<ScrollViewer" in axaml

    wu = td.export_screen("app", "winui", out_dir=str(tmp_path / "winui"))
    wux = (tmp_path / "winui" / "App.xaml").read_text(encoding="utf-8")
    assert "x:Bind ViewModel" in wux and "<ScrollViewer" in wux

    qt = td.export_screen("app", "qt-qml", out_dir=str(tmp_path / "qt"))
    qml = (tmp_path / "qt" / "App.qml").read_text(encoding="utf-8")
    assert "import QtQuick.Controls" in qml and "TextField {" in qml and "ScrollView {" in qml

    ig = td.export_screen("app", "imgui", out_dir=str(tmp_path / "imgui"))
    hpp = (tmp_path / "imgui" / "app_ui.hpp").read_text(encoding="utf-8")
    assert "ImGui::InputTextWithHint" in hpp and "ImGui::BeginChild" in hpp and "ImGuiInputTextFlags_Password" in hpp


def test_import_screenshot_reconstructs_editable_canvas(ws, tmp_path):
    s.create_canvas("src_ui", 480, 280, background="#0f172a")
    s.add_rect("src_ui", 28, 24, 424, 232, radius=16, style={"fill": "#1e293b", "stroke": {"color": "#334155", "width": 2, "align": "inside"}})
    s.add_ellipse("src_ui", 88, 86, 30, 30, fill="#38bdf8")
    s.add_rect("src_ui", 56, 158, 170, 44, radius=10, style={"fill": {"type": "linear", "angle": 90, "stops": ["#6366f1", "#4f46e5"]}})
    s.add_rect("src_ui", 254, 158, 170, 44, radius=10, style={"fill": "#0f172a", "stroke": {"color": "#38bdf8", "width": 2, "align": "inside"}})
    s.add_text("src_ui", "PLAY NOW", 141, 180, anchor="center", size=15, weight=700, color="#ffffff")

    ss_file = tmp_path / "screen.png"
    s.store().renderer(s.store().get("src_ui")).render().save(ss_file)

    res = s.import_screenshot(str(ss_file), canvas="imported_ui")
    assert res["canvas"] == "imported_ui"
    assert res["width"] == 480 and res["height"] == 280
    assert res["background"] == "#0f172a"
    assert res["shapes_created"] >= 3
    assert len(res["palette"]) >= 3
    rec = s.store().get("imported_ui")
    assert any(e["type"] == "ellipse" for e in rec["elements"])
    assert any(e["type"] == "rect" for e in rec["elements"])
    img = np.asarray(s.store().renderer(rec).render())
    assert img.shape == (280, 480, 4)


def test_quality_tiers_style_presets_and_named_material_style(ws):
    from game_ui_mcp import profiles
    assert len(profiles.QUALITY_LEVELS) == 4 and len(profiles.STYLE_PRESETS) == 9

    res_k = s.set_theme(replace=True, style_preset="kids", quality="simple")
    assert res_k["profile"]["quality"] == "simple" and res_k["profile"]["style_preset"] == "kids"
    s.create_canvas("c_kids", 280, 180, background="$bg")
    fk = s.add_frame("c_kids", 16, 16, 248, 148, preset="rpg_gold", id_prefix="fk")
    assert fk["quality"] == "simple"

    res_a = s.set_theme(replace=True, style_preset="dark_fantasy", quality="aaa")
    assert res_a["profile"]["quality"] == "aaa" and res_a["profile"]["style_preset"] == "dark_fantasy"
    s.create_canvas("c_aaa", 280, 180, background="$bg")
    fa = s.add_frame("c_aaa", 16, 16, 248, 148, preset="rpg_gold", id_prefix="fa")
    assert len(fa["ids"]) > len(fk["ids"])

    s.add_rect("c_aaa", 40, 60, 180, 48, radius=8, style="button", id="gold_btn")
    arr = np.asarray(s.store().renderer(s.store().get("c_aaa")).render(include_background=False))
    patch = arr[70:100, 60:200]
    assert patch[..., 0].mean() > patch[..., 2].mean() + 30


def test_gpu_architecture_cli_and_multi_ide_setup(ws, tmp_path):
    from game_ui_mcp import cli
    doc = cli.doctor_report()
    assert "hardware" in doc and "active_backend" in doc
    for arch in ("nvidia", "amd", "intel", "apple", "cpu"):
        plan = cli.install_gpu_plan(arch)
        assert plan["selected_arch"] == arch
        if arch in ("amd", "intel", "apple"):
            assert plan["packages"] == ["wgpu>=0.19"]
        elif arch == "nvidia":
            assert any("cupy" in p for p in plan["packages"]) and "wgpu>=0.19" in plan["packages"]
        else:
            assert plan["packages"] == []

    for cl in cli.CLIENTS:
        spec = cli.client_config(cl)
        assert spec["client"] == cl and "config" in spec

    oc = cli.client_config("opencode", scope="project")
    assert "servers" in oc["config"]["mcp"]
    vs = cli.client_config("visualstudio", scope="project")
    assert "servers" in vs["config"]
    cg = cli.client_config("chatgpt")
    assert cg["transport"] == "streamable-http" and "/mcp" in cg["endpoint_url"]

    target_json = tmp_path / "test_mcp.json"
    target_json.write_text('{"mcpServers": {"other": {"command": "echo"}}}', encoding="utf-8")
    merged_spec = dict(cli.client_config("claude"), path=str(target_json))
    cli.write_client_config(merged_spec)
    saved = json.loads(target_json.read_text(encoding="utf-8"))
    assert "other" in saved["mcpServers"] and "game-ui" in saved["mcpServers"]


def test_godot_smoothness_and_unreal_pbr_importer(ws, tmp_path):
    s.create_canvas("pbr_check", 128, 128)
    s.add_ellipse("pbr_check", 64, 64, 50, 50, style={"material": "gold"})
    gd = td.export_pbr_maps("pbr_check", out_dir=str(tmp_path / "gd"), engine="godot")
    assert "smoothness" in gd["files"]
    tres = (Path(gd["folder"]) / "pbr_check.canvas_texture.tres").read_text(encoding="utf-8")
    assert "pbr_check_smoothness.png" in tres
    ue = td.export_pbr_maps("pbr_check", out_dir=str(tmp_path / "ue"), engine="unreal")
    assert "pbr_check_import_pbr.py" in ue["extras"]
    ue_py = (Path(ue["folder"]) / "pbr_check_import_pbr.py").read_text(encoding="utf-8")
    assert "TC_NORMALMAP" in ue_py and "TC_MASKS" in ue_py

