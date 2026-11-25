"""Figma / Penpot style features: boolean shapes, corner smoothing, fill stacks, variable modes,
auto-layout wrap, vector SVG export and parallel animation frames."""
import pathlib
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def alpha(canvas="c", scale=1.0):
    st = s.store()
    return np.asarray(st.renderer(st.get(canvas), scale).render(include_background=False))[..., 3]


def test_boolean_ops_cut_merge_and_keep_overlap(ws):
    s.create_canvas("c", 100, 60)
    s.add_rect("c", 10, 10, 40, 40, id="a")
    s.add_rect("c", 30, 10, 40, 40, id="b")
    s.boolean_elements("c", ["a", "b"], op="subtract", id="r")
    a = alpha()
    assert a[30, 20] == 255 and a[30, 40] == 0 and a[30, 60] == 0
    s.update_element("c", "r", {"op": "intersect"})
    a = alpha()
    assert a[30, 20] == 0 and a[30, 40] == 255 and a[30, 60] == 0
    s.update_element("c", "r", {"op": "exclude"})
    a = alpha()
    assert a[30, 20] == 255 and a[30, 40] == 0 and a[30, 60] == 255
    s.update_element("c", "r", {"op": "union"})
    assert alpha()[30, 40] == 255


def test_boolean_stroke_follows_the_cut_and_moves_with_children(ws):
    s.create_canvas("c", 100, 60)
    s.add_rect("c", 10, 10, 60, 40, id="a")
    s.add_ellipse("c", 70, 30, 15, id="hole")
    s.boolean_elements("c", ["a", "hole"], op="subtract", id="r",
                       style={"fill": "#000000", "stroke": {"color": "#ff0000", "width": 3, "align": "inside"}})
    st = s.store()
    img = np.asarray(st.renderer(st.get("c")).render(include_background=False))
    assert img[30, 54, 0] > 200 and img[30, 54, 3] > 200
    s.move_elements("c", ids=["r"], dx=10, dy=0)
    assert s.store().get("c")["elements"][0]["children"][1]["cx"] == 80


def test_boolean_rejects_lines_and_works_in_batch(ws):
    s.create_canvas("c", 100, 60)
    s.add_rect("c", 10, 10, 40, 40, id="a")
    s.add_line("c", [[0, 0], [90, 50]], id="l")
    with pytest.raises(ValueError, match="only filled shapes"):
        s.boolean_elements("c", ["a", "l"])
    assert [e["id"] for e in s.store().get("c")["elements"]] == ["a", "l"]
    s.batch("c", [{"op": "add_ellipse", "id": "e", "cx": 50, "cy": 30, "rx": 10},
                  {"op": "boolean_elements", "ids": ["a", "e"], "operation": "union", "id": "u"}])
    assert [e["id"] for e in s.store().get("c")["elements"]] == ["u", "l"]


def test_corner_smoothing_eases_corners(ws):
    s.create_canvas("c", 120, 120)
    s.add_rect("c", 10, 10, 100, 100, radius=30, id="r")
    plain = alpha().astype(int).sum()
    s.update_element("c", "r", {"smoothing": 1})
    smooth = alpha().astype(int).sum()
    assert smooth != plain and abs(smooth - plain) < 0.05 * plain


def test_fill_stack_paints_bottom_to_top(ws):
    s.create_canvas("c", 40, 40)
    s.add_rect("c", 0, 0, 40, 40, style={"fill": ["#0000ff", "#ff000080"]})
    st = s.store()
    px = np.asarray(st.renderer(st.get("c")).render(include_background=False))[20, 20]
    assert px[0] > 100 and px[2] > 100 and px[3] == 255


def test_variable_modes_switch_tokens(ws):
    s.set_theme(colors={"bg": "#000000"}, modes={"light": {"bg": "#ffffff"}})
    s.create_canvas("c", 10, 10)
    s.add_rect("c", 0, 0, 10, 10, fill="$bg")
    st = s.store()

    def red():
        return np.asarray(st.renderer(st.get("c")).render(include_background=False))[5, 5, 0]

    assert red() == 0
    s.set_theme(mode="light")
    assert red() == 255
    s.update_canvas("c", mode="light")
    s.set_theme(mode="")
    assert red() == 255
    with pytest.raises(ValueError, match="no mode"):
        s.set_theme(mode="sepia")
    css = s.export_theme("css", path=str(ws / "t.css"))
    text = (ws / "t.css").read_text(encoding="utf-8")
    assert css["modes"] == ["light"] and '[data-theme="light"]' in text and "#ffffff" in text


def test_wrap_flows_items_onto_new_lines(ws):
    s.create_canvas("c", 200, 200)
    s.add_rect("c", 0, 0, 150, 200, id="box")
    for i in range(5):
        s.add_rect("c", 0, 0, 40, 30, id=f"i{i}", group="items")
    s.arrange_elements("c", group="items", container="box", gap=10, padding=5, wrap=True, align="start")
    els = {e["id"]: e for e in s.store().get("c")["elements"]}
    assert [els[f"i{i}"]["y"] for i in range(5)] == [5, 5, 5, 45, 45]
    assert [els[f"i{i}"]["x"] for i in (0, 1, 2, 3)] == [5, 55, 105, 5]


def test_svg_export_keeps_shapes_and_text_editable(ws):
    s.create_canvas("c", 200, 100, background="#101018")
    s.add_rect("c", 10, 10, 80, 40, radius=8, id="panel",
               style={"fill": {"type": "linear", "stops": [[0, "#38bdf8"], [1, "#1d4ed8"]]},
                      "stroke": {"color": "#ffffff", "width": 2}, "shadow": {"blur": 6, "dy": 3}})
    s.add_text("c", "PLAY", x=50, y=30, size=16, anchor="center", id="label")
    s.add_rect("c", 110, 10, 80, 40, id="fancy", style={"fill": {"type": "shader", "code": "r = u; g = v; b = 1"}})
    res = s.export_svg("c", path=str(ws / "c.svg"))
    assert set(res["vector"]) == {"panel", "label"} and res["embedded_as_image"] == ["fancy"]
    root = ET.parse(ws / "c.svg").getroot()
    ns = "{http://www.w3.org/2000/svg}"
    assert root.find(f".//{ns}linearGradient") is not None
    assert root.find(f".//{ns}feGaussianBlur") is not None and root.find(f".//{ns}feMerge") is not None
    assert [t.text for t in root.iter(f"{ns}tspan")] == ["PLAY"]


def test_parallel_frames_match_sequential(ws):
    s.create_canvas("c", 80, 40)
    s.add_rect("c", 0, 0, 20, 20, id="r")
    s.create_animation("c", "a", duration=1)
    s.set_keyframes("c", "a", "r", "dx", [{"t": 0, "value": 0}, {"t": 1, "value": 60}])
    c = s.store().get("c")
    anim = c["animations"]["a"]
    times = [i / 6 for i in range(6)]
    par, _ = s._poses(c, anim, times, 1.0)
    seq = [s._pose(c, anim, t, 1.0)[0] for t in times]
    assert all(a.tobytes() == b.tobytes() for a, b in zip(par, seq))


def test_backdrop_blur_softens_what_is_beneath_only_inside_the_shape(ws):
    s.create_canvas("c", 120, 60)
    for i in range(12):
        s.add_rect("c", i * 10, 0, 5, 60, fill="#ffffff")
    s.add_rect("c", 30, 10, 60, 40, id="glass", style={"fill": "#ffffff@0.1", "backdrop_blur": 12})
    st = s.store()
    img = np.asarray(st.renderer(st.get("c")).render(include_background=False)).astype(int)
    inside, outside = img[30, 40:80, 0], img[5, 40:80, 0]
    assert inside.max() - inside.min() < 60
    assert outside.max() - outside.min() > 200


def test_text_truncation_and_decoration(ws):
    s.create_canvas("c", 200, 60)
    s.add_text("c", "Supercalifragilistic expialidocious hero name", x=5, y=5, size=16, max_width=120,
               max_lines=1, id="name")
    s.add_text("c", "999", x=5, y=35, size=16, decoration="strikethrough", id="old")
    st = s.store()
    r = st.renderer(st.get("c"))
    box = r.element_box(st.find(st.get("c"), "name"))
    assert box[2] - box[0] <= 121
    from uiforge_mcp.render import TextLayout, resolve_style
    el = st.find(st.get("c"), "name")
    assert TextLayout(el, resolve_style(el.get("style"), st.theme), st.fonts, 1.0).lines[0][0].endswith("…")
    with_line = np.asarray(r.render(include_background=False))[..., 3].astype(int).sum()
    s.update_element("c", "old", {"decoration": "none"})
    without = np.asarray(st.renderer(st.get("c")).render(include_background=False))[..., 3].astype(int).sum()
    assert with_line > without
    with pytest.raises(ValueError, match="max_width"):
        s.add_text("c", "x", x=0, y=0, max_lines=2)


def test_stroke_on_chosen_sides_only(ws):
    s.create_canvas("c", 100, 60)
    s.add_rect("c", 10, 10, 80, 40, style={"fill": "none",
                                           "stroke": {"color": "#ffffff", "width": 4, "sides": ["bottom"]}})
    a = alpha()
    assert a[48, 50] > 200 and a[12, 50] == 0 and a[30, 12] == 0
    with pytest.raises(ValueError, match="rects only"):
        s.add_ellipse("c", 50, 30, 10, style={"stroke": {"color": "#fff", "width": 2, "sides": ["top"]}})


def test_version_history_save_restore_and_survives_restart(ws):
    s.create_canvas("c", 50, 50)
    s.add_rect("c", 0, 0, 10, 10, id="a")
    s.canvas_version("c", "save", name="first", note="one rect")
    s.add_rect("c", 20, 20, 10, 10, id="b")
    assert [v["name"] for v in s.canvas_version("c")["versions"]] == ["first"]
    s.canvas_version("c", "restore", name="first")
    assert [e["id"] for e in s.store().get("c")["elements"]] == ["a"]
    s.undo("c")
    assert [e["id"] for e in s.store().get("c")["elements"]] == ["a", "b"]
    s.set_store(Store(ws / "ws"))
    assert s.canvas_version("c")["versions"][0]["note"] == "one rect"
    with pytest.raises(ValueError, match="already exists"):
        s.canvas_version("c", "save", name="first")
    s.canvas_version("c", "delete", name="first")
    assert s.canvas_version("c")["versions"] == []


def test_export_presets_write_density_sets(ws):
    s.create_canvas("c", 20, 10)
    s.add_rect("c", 0, 0, 20, 10)
    ios = s.export_png("c", path=str(ws / "out" / "Play Button.png"), preset="ios")
    assert [pathlib.Path(f["file"]).name for f in ios["files"]] == ["Play Button.png", "Play Button@2x.png",
                                                                    "Play Button@3x.png"]
    assert [f["width"] for f in ios["files"]] == [20, 40, 60]
    android = s.export_png("c", path=str(ws / "res" / "Play Button.png"), preset="android")
    assert (ws / "res" / "drawable-xxxhdpi" / "play_button.png").is_file() and android["files"][-1]["width"] == 80
