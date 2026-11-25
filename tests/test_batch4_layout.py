"""Live auto layout (fill, min / max, hug, wrap, grid span, groups), component variants, hide / show, slots."""
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def el(cid, eid):
    st = s.store()
    return st.find(st.get(cid), eid)


def box(cid, eid):
    st = s.store()
    return st.renderer(st.get(cid)).element_box(el(cid, eid))


def test_button_hugs_its_label_live(ws):
    s.create_canvas("c", 400, 100)
    s.add_rect("c", 20, 20, 50, 40, id="btn")
    s.add_text("c", "Play", x=0, y=0, size=20, id="label")
    s.arrange_elements("c", mode="row", ids=["label"], container="btn", padding=[10, 24, 10, 24], hug=True,
                       align="center", live=True)
    w1 = el("c", "btn")["width"]
    s.update_element("c", "label", {"text": "Play the whole campaign"})
    w2 = el("c", "btn")["width"]
    assert w2 > w1 + 100
    lb = box("c", "label")
    assert lb[0] == pytest.approx(20 + 24, abs=0.5)


def test_fill_min_max_and_space_between(ws):
    s.create_canvas("c", 400, 60)
    s.add_rect("c", 0, 0, 300, 40, id="bar")
    s.add_rect("c", 0, 0, 40, 20, id="a")
    s.add_rect("c", 0, 0, 40, 20, id="b")
    s.add_rect("c", 0, 0, 40, 20, id="c")
    s.update_element("c", "b", {"layout_size": {"width": "fill", "max_width": 150}})
    s.update_element("c", "c", {"layout_size": {"height": "fill"}})
    s.arrange_elements("c", mode="row", ids=["a", "b", "c"], container="bar", gap=10, live=True)
    assert el("c", "b")["width"] == pytest.approx(150)
    assert el("c", "c")["height"] == pytest.approx(40)
    s.update_element("c", "bar", {"width": 200})
    assert el("c", "b")["width"] == pytest.approx(200 - 80 - 20)


def test_wrap_grid_span_and_groups(ws):
    s.create_canvas("c", 400, 400)
    s.add_rect("c", 0, 0, 230, 400, id="grid")
    for i in range(4):
        s.add_rect("c", 0, 0, 50, 50, id=f"g{i}")
    s.update_element("c", "g0", {"span": [2, 1], "layout_size": {"width": "fill"}})
    s.arrange_elements("c", mode="grid", ids=["g0", "g1", "g2", "g3"], container="grid", columns=3, gap=10,
                       live=True, align="start")
    cell = (230 - 20) / 3
    assert el("c", "g0")["width"] == pytest.approx(cell * 2 + 10)
    assert box("c", "g1")[0] == pytest.approx(2 * (cell + 10))
    assert box("c", "g2")[1] == pytest.approx(60)
    s.create_canvas("d", 400, 200)
    s.add_rect("d", 0, 0, 400, 200, id="row")
    for i in range(2):
        s.add_rect("d", 0, 0, 60, 30, group=f"w{i}", id=f"bg{i}")
        s.add_text("d", f"Item {i}", x=5, y=5, size=12, group=f"w{i}", id=f"t{i}")
    s.arrange_elements("d", mode="row", ids=["group:w0", "group:w1"], container="row", gap=20, padding=10,
                       live=True, align="start")
    assert box("d", "bg1")[0] == pytest.approx(10 + 60 + 20) and box("d", "t1")[0] == pytest.approx(10 + 60 + 20 + 5)


def test_variants_hide_show_and_slots(ws):
    s.create_canvas("btn", 100, 40)
    s.add_rect("btn", 0, 0, 100, 40, id="face", fill="#333333")
    s.add_ellipse("btn", 85, 20, 6, id="badge", fill="#ff0000")
    s.set_state("btn", "size=large", "face", {"fill": "#00ff00"})
    s.set_state("btn", "tone=danger", "face", {"fill": "#0000ff"})
    s.create_canvas("gem", 20, 20)
    s.add_ellipse("gem", 10, 10, 10, fill="#ffff00")
    s.create_canvas("slot", 60, 60)
    s.add_rect("slot", 0, 0, 60, 60, fill="#222222")
    s.add_rect("slot", 10, 10, 40, 40, id="icon", fill="#ffffff@0.1")
    s.create_canvas("c", 200, 100)
    s.add_instance("c", "btn", 0, 0, variant={"size": "large", "tone": "danger"}, hide=["badge"], id="i1")
    s.add_instance("c", "slot", 120, 0, slots={"icon": "gem"}, id="i2")
    import numpy as np
    st = s.store()
    px = np.asarray(st.renderer(st.get("c")).render(include_background=False))
    assert tuple(px[20, 30, :3]) == (0, 0, 255)
    assert tuple(px[20, 85, :3]) == (0, 0, 255)
    assert px[30, 150, 0] > 200 and px[30, 150, 2] < 60
    with pytest.raises(ValueError, match="no state"):
        s.add_instance("c", "btn", 0, 50, variant={"size": "huge"})
