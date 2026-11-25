"""Line ends, diamond gradients, spring easing, number tokens, DTCG tokens, text replace, find, simplify,
version diff, letter case, notes and focus order."""
import json

import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def img(canvas="c"):
    st = s.store()
    return np.asarray(st.renderer(st.get(canvas)).render(include_background=False))


def test_line_end_caps_draw_and_export(ws):
    s.create_canvas("c", 120, 40)
    s.add_line("c", [[10, 20], [100, 20]], width=4, id="l", end_cap="triangle", start_cap="circle")
    a = img()[..., 3]
    assert a[15, 91] > 100 and a[20, 10] > 200 and a[15, 50] == 0
    with pytest.raises(ValueError, match="end_cap"):
        s.update_element("c", "l", {"end_cap": "heart"})
    root = s.export_svg("c", path=str(ws / "l.svg"))
    assert "l" in root["vector"]


def test_diamond_gradient_and_spring_ease(ws):
    s.create_canvas("c", 40, 40)
    s.add_rect("c", 0, 0, 40, 40, style={"fill": {"type": "diamond", "stops": [[0, "#ffffff"], [1, "#000000"]]}})
    px = img()
    assert px[20, 20, 0] > 230 and px[20, 1, 0] < 60 and px[1, 1, 0] < 30
    from uiforge_mcp.animation import ease
    vals = [ease("spring-out", t / 20) for t in range(21)]
    assert vals[0] == 0 and abs(vals[-1] - 1) < 1e-9 and max(vals) > 1.0


def test_number_tokens_follow_modes(ws):
    s.set_theme(numbers={"r": 0, "w": 20}, modes={"big": {"w": 36}})
    s.create_canvas("c", 60, 20)
    s.add_rect("c", 0, 0, "$w", 20, radius="$r", id="bar")
    assert img()[10, 30, 3] == 0
    s.update_canvas("c", mode="big")
    assert img()[10, 30, 3] == 255
    with pytest.raises(ValueError, match="number"):
        s.set_theme(numbers={"x": "big"})


def test_dtcg_round_trip(ws):
    doc = {"color": {"$type": "color", "brand": {"$value": "#7c5cff"}, "link": {"$value": "{color.brand}"}},
           "space": {"$type": "dimension", "md": {"$value": "16px"}, "lg": {"$value": "1.5rem"}}}
    res = s.set_theme(tokens=doc)
    assert res["colors"]["color-brand"] == "#7c5cff" and res["colors"]["color-link"] == "$color-brand"
    assert res["numbers"] == {"space-md": 16.0, "space-lg": 24.0}
    out = s.export_theme("dtcg", path=str(ws / "t.tokens.json"))
    data = json.loads((ws / "t.tokens.json").read_text(encoding="utf-8"))
    assert data["color"]["color-brand"]["$value"] == "#7c5cff" and data["size"]["space-md"]["$value"] == "16px"


def test_replace_text_find_and_diff(ws):
    s.create_canvas("c", 100, 60)
    s.add_text("c", "Play now", x=0, y=0, id="t", font="Inter", color="#ff0000")
    s.add_rect("c", 0, 30, 20, 20, id="r1", fill="#ff0000@0.5")
    s.add_rect("c", 30, 30, 20, 20, id="r2", fill="#00ff00")
    s.canvas_version("c", "save", name="v1")
    s.restyle(replace_text={"Play": "Start"})
    assert s.store().find(s.store().get("c"), "t")["text"] == "Start now"
    assert s.find_elements("c", color="#ff0000")["found"]["c"] == ["t", "r1"]
    assert s.find_elements("c", like="r2")["found"]["c"] == ["r2"]
    assert s.find_elements(text_contains="start")["count"] == 1
    s.delete_elements("c", ids=["r2"])
    diff = s.canvas_version("c", "diff", name="v1")
    assert diff["removed"] == ["r2"] and diff["changed"] == {"t": ["text"]}


def test_simplify_case_note_focus(ws):
    s.create_canvas("c", 100, 100)
    s.add_ellipse("c", 50, 50, 40, id="e")
    s.path_ops("c", "e", "flatten", new_id="p")
    before = s.store().find(s.store().get("c"), "p")["d"].count("L")
    s.path_ops("c", "p", "simplify", distance=0.5, new_id="q")
    after = s.store().find(s.store().get("c"), "q")["d"].count("L")
    assert after < before / 2
    s.add_text("c", "istanbul ışık", x=0, y=0, id="t", case="tr-upper")
    from uiforge_mcp.render import TextLayout, resolve_style
    st = s.store()
    el = st.find(st.get("c"), "t")
    assert TextLayout(el, {}, st.fonts, 1.0).lines[0][0] == "İSTANBUL IŞIK"
    s.update_element("c", "t", {"case": "title", "note": "Use the city name from the server"})
    assert TextLayout(st.find(st.get("c"), "t"), {}, st.fonts, 1.0).lines[0][0] == "Istanbul Işık"
    s.update_canvas("c", focus_order=["t", "q"])
    spec = s.export_spec("c", out_dir=str(ws / "spec"))
    data = json.loads(next((ws / "spec").glob("*.spec.json")).read_text(encoding="utf-8"))
    assert any(i.get("note") for i in data["elements"])
