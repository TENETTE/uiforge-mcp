"""Motion path, motion blur and vector feathering."""
import numpy as np
import pytest
from PIL import Image

from uiforge_mcp import animation as am
from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def test_motion_path_moves_and_turns(ws):
    s.create_canvas("c", 300, 200)
    s.add_rect("c", 0, 90, 20, 20, id="coin")
    s.create_animation("c", "fly", duration=1)
    s.set_keyframes("c", "fly", "coin", "motion", [[0, 0], [1, 1]], path={"points": [[0, 0], [100, 0], [100, 100]], "rotate": True})
    c = s.store().get("c")
    half, _ = am.apply_animation(c, c["animations"]["fly"], 0.5, {})
    end, _ = am.apply_animation(c, c["animations"]["fly"], 1.0, {})
    h, e = half["elements"][0], end["elements"][0]
    assert (h["x"], h["y"]) == (100, 90) and h["rotation"] == pytest.approx(0)
    assert (e["x"], e["y"]) == (100, 190) and e["rotation"] == pytest.approx(90)
    with pytest.raises(ValueError, match="motion"):
        s.set_keyframes("c", "fly", "coin", "motion", [[0, 0], [1, 1]])


def test_motion_blur_smears_fast_motion(ws):
    s.create_canvas("c", 200, 40)
    s.add_rect("c", 0, 10, 20, 20, id="r", fill="#ffffff")
    s.create_animation("c", "dash", duration=1, fps=10, loop=True)
    s.set_keyframes("c", "dash", "r", "dx", [[0, 0], [1, 180]])
    sharp = s.export_animation("c", "dash", format="frames", path=str(ws / "sharp"), trim=False)
    blurred = s.export_animation("c", "dash", format="frames", path=str(ws / "blur"), trim=False, motion_blur=6)
    a = np.asarray(Image.open(next((ws / "sharp").glob("*_005.png"))))[20, :, 3]
    b = np.asarray(Image.open(next((ws / "blur").glob("*_005.png"))))[20, :, 3]
    assert ((b > 10) & (b < 245)).sum() > ((a > 10) & (a < 245)).sum() + 6        # soft trailing edges


def test_feather_softens_only_the_edge(ws):
    s.create_canvas("c", 100, 100)
    s.add_rect("c", 20, 20, 60, 60, id="r", style={"fill": "#ffffff", "feather": 12})
    st = s.store()
    a = np.asarray(st.renderer(st.get("c")).render(include_background=False))[..., 3]
    assert a[50, 50] > 250 and 40 < a[50, 20] < 220
