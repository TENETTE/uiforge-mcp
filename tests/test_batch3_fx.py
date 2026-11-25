"""Effects: progressive blur, glass, noise modes, texture, luminance masks, per-fill blend, image crop and
adjustments, variable-width and wiggly strokes."""
import numpy as np
import pytest
from PIL import Image

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def img(canvas="c"):
    st = s.store()
    return np.asarray(st.renderer(st.get(canvas)).render(include_background=False)).astype(int)


def stripes():
    s.create_canvas("c", 200, 100)
    s.add_rect("c", 0, 0, 200, 100, fill="#000000")
    for i in range(20):
        s.add_rect("c", i * 10, 0, 5, 100, fill="#ffffff")


def test_progressive_backdrop_blur_ramps(ws):
    stripes()
    s.add_rect("c", 0, 0, 200, 100, style={"fill": "#ffffff@0.01", "backdrop_blur": {"radius": 20, "angle": 90}})
    a = img()[..., 0]
    assert np.ptp(a[3, 20:120]) > 150 and np.ptp(a[96, 20:120]) < 60


def test_glass_bends_and_lights_the_backdrop(ws):
    stripes()
    before = img()
    s.add_rect("c", 40, 20, 120, 60, radius=20, style={"fill": "#ffffff@0.02", "glass": {"refraction": 0.8, "depth": 12}})
    after = img()
    edge = np.abs(after[22:30, 45:155, 0] - before[22:30, 45:155, 0]).mean()
    middle = np.abs(after[48:52, 95:105, 0] - before[48:52, 95:105, 0]).mean()
    assert edge > middle + 10


def test_noise_modes_texture_and_fill_blend(ws):
    s.create_canvas("c", 60, 60)
    s.add_rect("c", 0, 0, 60, 60, id="r", style={"fill": "#808080", "noise": {"mode": "multi", "amount": 0.5}})
    px = img()
    assert np.ptp(px[..., 0] - px[..., 2]) > 40
    with pytest.raises(ValueError, match="noise.mode"):
        s.update_element("c", "r", {"style": {"noise": {"mode": "rainbow"}}})
    s.update_element("c", "r", {"style": {"noise": None, "fill": ["#ff0000", {"color": "#808080", "blend": "multiply"}]}})
    assert tuple(img()[30, 30, :3]) == (128, 0, 0)
    s.create_canvas("t", 60, 60)
    s.add_rect("t", 10, 10, 40, 40, id="rough", style={"fill": "#000000", "texture": {"amount": 3, "size": 4}})
    edge = img("t")[8:13, 10:50, 3]
    assert 0 < (edge > 128).mean() < 1


def test_luminance_mask_and_clip(ws):
    s.create_canvas("c", 100, 20)
    s.add_rect("c", 0, 0, 100, 20, id="a", style={"fill": "#ff0000", "mask_mode": "luminance",
                                                   "mask": {"type": "linear", "angle": 0, "stops": [[0, "#000000"], [1, "#ffffff"]]}})
    a = img()[10, :, 3]
    assert a[2] < 20 and a[97] > 230
    s.add_rect("c", 0, 0, 100, 20, id="m", fill={"type": "linear", "angle": 0, "stops": [[0, "#ffffff"], [1, "#000000"]]})
    s.update_element("c", "m", {"visible": False})
    s.update_element("c", "a", {"visible": False})
    s.add_rect("c", 0, 0, 100, 20, id="b", fill="#00ff00", clip="m")
    s.update_element("c", "b", {"clip_mode": "luminance"})
    g = img()[10, :, 3]
    assert g[2] > 230 and g[97] < 30


def test_image_crop_adjust_and_variable_strokes(ws, tmp_path):
    src = Image.new("RGBA", (40, 20), (255, 0, 0, 255))
    src.paste((0, 0, 255, 255), (20, 0, 40, 20))
    path = tmp_path / "two.png"
    src.save(path)
    s.create_canvas("c", 20, 20)
    s.add_image("c", str(path), 0, 0, 20, 20, id="im")
    s.update_element("c", "im", {"crop": [20, 0, 20, 20]})
    assert tuple(img()[10, 10, :3]) == (0, 0, 255)
    s.update_element("c", "im", {"style": {"adjust": {"exposure": -1}}})
    assert img()[10, 10, 2] < 140
    s.create_canvas("l", 200, 60)
    s.add_line("l", [[10, 30], [190, 30]], width=10, taper="both", id="t")
    a = img("l")[..., 3]
    assert (a[:, 100] > 128).sum() > (a[:, 15] > 128).sum() + 4
    s.add_line("l", [[10, 50], [190, 50]], width=2, wiggle={"amount": 4, "frequency": 5})
    rows = np.where(img("l")[40:60, :, 3].max(axis=1) > 128)[0]
    assert rows.max() - rows.min() > 5
