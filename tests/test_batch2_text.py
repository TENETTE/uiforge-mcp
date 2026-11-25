"""Text engine: lists and paragraphs, OpenType features, vertical trim, colour emoji, text on a path,
text to vector outlines."""
import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.render import TextLayout
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def layout(**el):
    st = s.store()
    return TextLayout({"id": "t", "type": "text", "x": 0, "y": 0, **el}, {}, st.fonts, 1.0)


def test_lists_paragraphs_and_indent(ws):
    lay = layout(text="one\ntwo", list="number", paragraph_spacing=10)
    assert [ln for ln, _ in lay.lines] == ["1.  one", "2.  two"]
    plain = layout(text="one\ntwo")
    assert lay.baselines[1] - lay.baselines[0] == pytest.approx(plain.baselines[1] - plain.baselines[0] + 10)
    wrapped = layout(text="alpha beta gamma delta epsilon", list="bullet", max_width=90)
    assert len(wrapped.lines) > 1 and wrapped.line_x[1] > wrapped.line_x[0]
    assert layout(text="abc", indent=12).line_x[0] == 12


def test_features_trim_and_missing_feature_warning(ws):
    tab, prop = layout(text="1111", features=["tnum"]), layout(text="1111")
    assert tab.lines[0][1] > prop.lines[0][1]
    lay = layout(text="Hi", case="small-caps")
    assert any("smcp" in w for w in lay.warnings)
    trimmed, normal = layout(text="Hg", trim=True), layout(text="Hg")
    assert trimmed.box_px[3] < normal.box_px[3]


def test_colour_emoji_render_in_colour(ws):
    s.create_canvas("c", 120, 50)
    s.add_text("c", "A \U0001F525", x=5, y=5, size=32, color="#ffffff")
    st = s.store()
    px = np.asarray(st.renderer(st.get("c")).render(include_background=False))
    vis = px[..., 3] > 200
    assert (vis & (px[..., 0].astype(int) - px[..., 2].astype(int) > 80)).any()


def test_text_on_path_and_to_outlines(ws):
    s.create_canvas("c", 300, 160)
    s.add_text("c", "CURVED", x=0, y=0, size=20, anchor="baseline-center", id="cv",
               path={"d": "M 20 140 C 80 20 220 20 280 140"})
    box = s.store().renderer(s.store().get("c")).element_box(s.store().find(s.store().get("c"), "cv"))
    assert box[1] < 80
    with pytest.raises(ValueError, match="longer than the path"):
        s.add_text("c", "THIS TEXT IS FAR TOO LONG FOR THE PATH", x=0, y=0, size=30, path={"points": [[0, 0], [50, 0]]})
    s.add_text("c", "OK", x=20, y=20, size=40, weight=800, id="t")
    before = s.store().renderer(s.store().get("c")).element_box(s.store().find(s.store().get("c"), "t"))
    s.path_ops("c", "t", "flatten", new_id="p")
    el = s.store().find(s.store().get("c"), "p")
    assert el["type"] == "path" and el["d"].count("M") >= 2
    after = s.store().renderer(s.store().get("c")).element_box(el)
    assert abs(after[0] - before[0]) < 3 and abs(after[2] - before[2]) < 3
