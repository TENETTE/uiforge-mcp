"""guide, make_palette, restyle, path_ops and the design-lint findings of review_canvas."""
import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def alpha(canvas="c"):
    st = s.store()
    return np.asarray(st.renderer(st.get(canvas)).render(include_background=False))[..., 3]


def test_instructions_fit_clients_and_guide_has_the_rest():
    assert len(s.INSTRUCTIONS) < 3500
    assert "backdrop_blur" in s.guide("design") and "design" in s.guide("index")
    assert "export_svg" in s.guide("export") and "## shader" in s.guide("all")
    with pytest.raises(ValueError, match="Topics"):
        s.guide("nope")


def test_palette_is_ordered_keeps_base_and_reports_contrast(ws):
    res = s.make_palette("#3b82f6", name="brand", apply=True)
    from uiforge_mcp.tools_design import _luminance
    from uiforge_mcp.colors import parse_color
    lum = [_luminance(parse_color(v)) for v in res["scale"].values()]
    assert lum == sorted(lum, reverse=True)
    assert "#3b82f6" in res["scale"].values()
    assert res["text_on"]["brand-950"].startswith("white") and res["text_on"]["brand-50"].startswith("black")
    assert s.store().theme["colors"]["brand-500"] and s.store().theme["colors"]["brand"] == "#3b82f6"


def test_restyle_swaps_colours_fonts_and_keeps_alpha(ws):
    s.set_theme(colors={"primary": "#7c5cff"}, styles={"card": {"fill": "#ff0000", "stroke": "#ff0000@0.5"}})
    s.create_canvas("c", 50, 50)
    s.add_rect("c", 0, 0, 20, 20, id="a", style={"fill": "#ff0000", "shadow": {"color": "#ff0000@0.4"}})
    s.add_rect("c", 25, 0, 20, 20, id="b", style="card")
    s.add_text("c", "Hi", x=0, y=30, id="t", font="Inter", color="#FF0000")
    dry = s.restyle(replace_colors={"#ff0000": "$primary"}, dry_run=True)
    assert dry["canvases"]["c"]["elements"] == ["a", "t"] and s.store().find(s.store().get("c"), "a")["style"]["fill"] == "#ff0000"
    s.restyle(replace_colors={"#ff0000": "$primary"}, replace_fonts={"inter": "Rajdhani"})
    st = s.store()
    a, t = st.find(st.get("c"), "a"), st.find(st.get("c"), "t")
    assert a["style"]["fill"] == "$primary" and a["style"]["shadow"]["color"] == "$primary@0.4"
    assert t["font"] == "Rajdhani" and st.theme["styles"]["card"]["stroke"] == "$primary@0.5"
    s.undo("c")
    assert st.find(st.get("c"), "a")["style"]["fill"] == "#ff0000"


def test_path_ops_flatten_offset_and_outline_stroke(ws):
    s.create_canvas("c", 100, 60)
    s.add_rect("c", 20, 20, 40, 20, id="r", rotation=30)
    before = alpha().astype(int).sum()
    s.path_ops("c", "r", "flatten", new_id="p")
    st = s.store()
    assert [e["type"] for e in st.get("c")["elements"]] == ["path"]
    assert abs(alpha().astype(int).sum() - before) < before * 0.02
    s.path_ops("c", "p", "offset", distance=4, new_id="big")
    assert alpha().astype(int).sum() > before * 1.4
    s.add_line("c", [[5, 55], [95, 55]], width=4, id="ln")
    s.path_ops("c", "ln", "outline_stroke", new_id="lnshape")
    ids = [e["id"] for e in st.get("c")["elements"]]
    assert "ln" not in ids and "lnshape" in ids
    s.boolean_elements("c", ["big", "lnshape"], op="union")
    with pytest.raises(ValueError, match="no stroke"):
        s.add_rect("c", 0, 0, 5, 5, id="plain")
        s.path_ops("c", "plain", "outline_stroke")


def test_review_lints_near_misses_and_hardcoded_colours(ws):
    s.set_theme(colors={"a": "#111", "b": "#222", "c": "#333"})
    s.create_canvas("c", 200, 100)
    s.add_rect("c", 10, 10, 50, 30, id="one", fill="#ff0000")
    s.add_rect("c", 11, 50, 50, 30, id="two", fill="#00ff00")
    checks = {i["check"]: i for i in s.review_canvas("c")["issues"]}
    assert "alignment" in checks and set(checks["alignment"]["ids"]) == {"one", "two"}
    assert "tokens" in checks and checks["tokens"]["severity"] == "info"
