"""Interactions (state machine), React / video export, variations, DESIGN.md, custom materials."""
import json
import shutil

import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp import tools_delivery as d
from uiforge_mcp import tools_design as td
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def _button():
    s.set_theme(colors={"primary": "#7c3aed", "text": "#ffffff"})
    s.create_canvas("menu", 400, 200, background="#101018")
    s.add_rect("menu", 40, 40, 240, 70, radius=16, id="btn", style={"fill": "$primary"})
    s.add_text("menu", "PLAY", 160, 75, anchor="center", size=30, id="label", color="$text")
    s.create_canvas("settings", 400, 200)
    s.create_animation("menu", "hover_in", duration=0.2)
    s.set_keyframes("menu", "hover_in", "btn", "scale", [[0, 1], [0.2, 1.08, "cubic-out"]], pivot=[160, 75])
    s.create_animation("menu", "glow", duration=0.4)
    s.set_keyframes("menu", "glow", "btn", "dy", [[0, 0], [0.4, -6]])
    s.set_state("menu", "selected", "btn", {"style": {"fill": "#22d3ee"}})


def test_interactions_validate_and_reach_web(ws):
    _button()
    d.set_interaction("menu", "btn", "hover", "play", animation="hover_in")
    d.set_interaction("menu", "btn", "click", "toggle_state", state="selected")
    d.set_interaction("menu", "btn", "click", "navigate", target="settings", delay=0.2)
    d.set_interaction("menu", "canvas", "end:hover_in", "play", animation="glow")
    d.set_interaction("menu", "canvas", "key:Escape", "back")
    with pytest.raises(ValueError, match="no state"):
        d.set_interaction("menu", "btn", "click", "set_state", state="nope")
    with pytest.raises(ValueError, match="trigger"):
        d.set_interaction("menu", "btn", "wiggle", "back")
    out = s.export_web(["menu", "settings"], out_dir=str(ws / "web"))
    page = (ws / "web" / "index.html").read_text(encoding="utf-8")
    assert 'data-ix="btn"' in page and "window.UIFORGE_IX" in page
    assert ".page.p-hover_in #btn{animation:" in page and ".page.s-selected #btn{" in page and "!important" in page
    cfg = json.loads(page.split("window.UIFORGE_IX=")[1].split("</script>")[0])
    nav = next(r for r in cfg["rules"] if r["action"] == "navigate")
    assert nav["href"] == "settings.html" and nav["delay"] == 0.2
    assert "uiforgeAttach" in (ws / "web" / "app.js").read_text(encoding="utf-8")
    assert out["pages"] == ["index.html", "settings.html"]
    d.set_interaction("menu", "canvas", "key:Escape", "back", remove=True)
    assert len(s.store().get("menu")["interactions"]) == 4
    anim = s.export_animation("menu", "hover_in", format="json", path=str(ws / "a.json"))
    assert json.loads((ws / "a.json").read_text())["interactions"]
    assert anim["tracks"] == 1


def test_react_export_is_valid_jsx(ws):
    _button()
    s.add_path("menu", "M 300 40 L 360 40 L 330 100 Z", fill="#ff0", id="tri")
    d.set_interaction("menu", "btn", "click", "navigate", target="settings")
    out = s.export_react(["menu", "settings"], out_dir=str(ws / "react"))
    assert out["components"] == ["Menu.jsx", "Settings.jsx"]
    jsx = (ws / "react" / "Menu.jsx").read_text(encoding="utf-8")
    assert "className=" in jsx and "class=" not in jsx and "style={{" in jsx
    assert "dangerouslySetInnerHTML" in jsx and "uiforgeAttach" in jsx and "onNavigate" in jsx
    assert not (ws / "react" / "index.html").exists()
    assert "export function uiforgeAttach" in (ws / "react" / "uiforge-runtime.js").read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
@pytest.mark.parametrize("fmt", ["mp4", "webm"])
def test_video_export(ws, fmt):
    _button()
    out = s.export_animation("menu", "glow", format=fmt, path=str(ws / f"v.{fmt}"))
    assert (ws / f"v.{fmt}").stat().st_size > 500 and out["frames"] > 5


def test_variations_make_distinct_copies(ws):
    _button()
    s.update_element("menu", "btn", {"style": {"fill": "$primary", "stroke": {"color": "#ffffff", "width": 2}}})
    res = td.make_variations("menu", count=3)
    info = json.loads(res[1])
    assert [v["canvas"] for v in info["variations"]] == ["menu_v1", "menu_v2", "menu_v3"]
    st = s.store()
    base = np.asarray(st.renderer(st.get("menu")).render())
    for v in ("menu_v1", "menu_v2", "menu_v3"):
        img = np.asarray(st.renderer(st.get(v)).render())
        assert np.abs(img.astype(int) - base.astype(int)).mean() > 1
    assert st.get("menu_v1")["colors"]["primary"] != "#7c3aed"
    with pytest.raises(ValueError, match="already exists"):
        td.make_variations("menu", count=1)


def test_design_md_round_trip(ws):
    s.set_theme(colors={"bg": "#0b0a12", "primary": "#8b5cf6"}, numbers={"radius-lg": 16, "space-md": 12},
                styles={"title": {"font": "Rajdhani", "size": 30, "weight": 700, "fill": "$primary"}})
    out = d.export_theme("design.md", path=str(ws / "DESIGN.md"))
    text = (ws / "DESIGN.md").read_text(encoding="utf-8")
    assert text.startswith("---") and "## Colors" in text and out["colors"] == 2
    s.set_store(Store(ws / "ws2"))
    got = s.set_theme(tokens=str(ws / "DESIGN.md"))
    assert got["colors"]["primary"] == "#8b5cf6"
    assert got["numbers"] == {"radius-lg": 16.0, "space-md": 12.0}
    assert s.store().theme["styles"]["title"]["font"] == "Rajdhani"
    (ws / "other.md").write_text("# Brand\n\n| Name | Hex |\n|---|---|\n| Ink | #111111 |\n| Brand Red | #e11d48 |\n",
                                 encoding="utf-8")
    got = s.set_theme(tokens=str(ws / "other.md"))
    assert got["colors"]["brand-red"] == "#e11d48"


def test_custom_materials(ws):
    s.set_theme(colors={"primary": "#22c55e"}, materials={
        "dark_oak": {"material": "wood", "color": "#4a2c18", "scale": 2},
        "slime": {"fill": {"type": "shader", "code": "r = c_r*(1-v*0.4); g = c_g*(1-v*0.4); b = c_b; a = 0.9",
                           "params": {"c": "$primary"}}, "light": {"angle": 225, "size": 6, "gloss": 1}}})
    s.create_canvas("c", 120, 60)
    s.add_rect("c", 0, 0, 60, 60, style={"material": "dark_oak"})
    s.add_rect("c", 60, 0, 60, 60, style={"material": {"name": "slime", "color": "#ff0000"}})
    st = s.store()
    img = np.asarray(st.renderer(st.get("c")).render(include_background=False))
    assert img[30, 30, 0] < 140 and img[30, 30, 0] > img[30, 30, 2]
    assert img[30, 90, 0] > 150 and img[30, 90, 1] < 80
    with pytest.raises(ValueError, match="Unknown material"):
        s.set_theme(materials={"bad": {"material": "plutonium"}})
    assert "bad" not in (st.theme.get("materials") or {})
