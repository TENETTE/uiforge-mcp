"""Image frames / pan-zoom / cutout and the ready-made material library."""
import numpy as np
import pytest
from PIL import Image

from uiforge_mcp import animation as anim
from uiforge_mcp import server as s
from uiforge_mcp.materials import NAMES
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def pixels(canvas="c", el_frame=None):
    st = s.store()
    c = el_frame or st.get(canvas)
    return np.asarray(st.renderer(c).render(include_background=False))


@pytest.mark.parametrize("name", NAMES)
def test_every_material_renders_with_texture(ws, name):
    s.create_canvas("c", 120, 80)
    s.add_rect("c", 10, 10, 100, 60, radius=8, style={"material": name})
    img = pixels()
    inside = img[20:60, 20:100]
    assert inside[..., 3].mean() > 20
    if name not in ("glass", "neon", "plastic", "rubber"):
        assert inside[..., :3].astype(float).std() > 2, "material should not be a flat colour"


def test_material_colour_and_override(ws):
    s.create_canvas("c", 60, 60)
    s.add_rect("c", 0, 0, 60, 60, style={"material": {"name": "plastic", "color": "#ff0000"}, "light": None})
    px = pixels()[30, 30]
    assert px[0] > 150 and px[1] < 60
    with pytest.raises(ValueError, match="Unknown material"):
        s.add_rect("c", 0, 0, 10, 10, style={"material": "unobtanium"})


def test_material_animates_through_t(ws):
    s.create_canvas("c", 80, 80)
    s.add_rect("c", 0, 0, 80, 80, id="lava", style={"material": {"name": "lava", "t": 0}})
    s.create_animation("c", "flow", duration=1)
    s.set_keyframes("c", "flow", "lava", "style.material.t", [[0, 0], [1, 2]])
    c = s.store().get("c")
    a, _ = anim.apply_animation(c, c["animations"]["flow"], 0, {})
    b, _ = anim.apply_animation(c, c["animations"]["flow"], 1, {})
    assert np.abs(pixels(el_frame=a).astype(int) - pixels(el_frame=b).astype(int)).mean() > 2


def test_sprite_sheet_frames_play(ws, tmp_path):
    sheet = Image.new("RGBA", (40, 20), (255, 0, 0, 255))
    sheet.paste((0, 0, 255, 255), (20, 0, 40, 20))
    sheet.save(tmp_path / "sheet.png")
    s.create_canvas("c", 20, 20)
    s.add_image("c", str(tmp_path / "sheet.png"), 0, 0, id="sp", sheet={"cols": 2, "rows": 1})
    assert pixels()[10, 10, 0] > 200
    s.create_animation("c", "play", duration=1)
    s.set_keyframes("c", "play", "sp", "frame", [[0, 0], [1, 2]])
    c = s.store().get("c")
    mid, _ = anim.apply_animation(c, c["animations"]["play"], 0.75, {})
    assert pixels(el_frame=mid)[10, 10, 2] > 200


def test_gif_frames_zoom_focus_and_cutout(ws, tmp_path):
    frames = [Image.new("RGB", (20, 20), col) for col in ((255, 0, 0), (0, 255, 0))]
    frames[0].save(tmp_path / "a.gif", save_all=True, append_images=frames[1:], duration=100)
    s.create_canvas("c", 20, 20)
    s.add_image("c", str(tmp_path / "a.gif"), 0, 0, frame=1)
    assert pixels()[10, 10, 1] > 200

    pic = Image.new("RGB", (40, 20), (255, 255, 255))
    pic.paste((0, 0, 0), (20, 0, 40, 20))
    pic.save(tmp_path / "half.png")
    s.create_canvas("z", 20, 20)
    s.add_image("z", str(tmp_path / "half.png"), 0, 0, 20, 20, fit="cover", focus=[1, 0.5])
    assert pixels("z")[10, 10, 0] < 40

    photo = Image.new("RGB", (30, 30), (20, 200, 40))
    photo.paste((200, 30, 30), (10, 10, 20, 20))
    photo.save(tmp_path / "green.png")
    s.create_canvas("k", 30, 30)
    s.add_image("k", str(tmp_path / "green.png"), 0, 0, cutout=True)
    img = pixels("k")
    assert img[2, 2, 3] < 10 and img[15, 15, 3] > 240


def test_image_moves_smoothly_between_pixels(ws, tmp_path):
    Image.new("RGB", (4, 4), (255, 255, 255)).save(tmp_path / "w.png")
    s.create_canvas("c", 10, 10)
    s.add_image("c", str(tmp_path / "w.png"), 2.5, 2, id="w")
    row = pixels()[3, :, 3]
    assert 60 < row[2] < 200 and 60 < row[6] < 200
