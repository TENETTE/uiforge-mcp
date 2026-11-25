"""Shader fill: model-written per-pixel formulas, sandboxed to arithmetic and whitelisted functions."""
import numpy as np
import pytest

from uiforge_mcp import server as s
from uiforge_mcp.store import Store


@pytest.fixture()
def ws(tmp_path):
    s.set_store(Store(tmp_path / "ws"))
    yield tmp_path
    s.set_store(None)


def pixels(canvas="c"):
    st = s.store()
    return np.asarray(st.renderer(st.get(canvas)).render(include_background=False))


def test_shader_paints_gradient_from_formula(ws):
    s.create_canvas("c", 100, 20)
    s.add_rect("c", 0, 0, 100, 20, style={"fill": {"type": "shader", "code": "r = u; g = 0; b = 1 - u"}})
    img = pixels()
    assert img[10, 2, 0] < 20 and img[10, 97, 0] > 235
    assert img[10, 2, 2] > 235 and img[10, 97, 2] < 20


def test_shader_color_params_alpha_and_noise(ws):
    s.create_canvas("c", 64, 64)
    code = "n = fbm(x/8, y/8, 4); r = c_r; g = c_g; b = c_b; a = step(0.5, n)"
    s.add_rect("c", 0, 0, 64, 64, style={"fill": {"type": "shader", "code": code, "params": {"c": "#ff8800"}}})
    img = pixels()
    opaque = img[..., 3] > 250
    assert 0 < opaque.mean() < 1
    assert tuple(img[opaque][0][:3]) == (255, 136, 0)


def test_shader_param_animates(ws):
    s.create_canvas("c", 20, 20)
    s.add_rect("c", 0, 0, 20, 20, id="box",
               style={"fill": {"type": "shader", "code": "r = t; g = 0; b = 0", "params": {"t": 0}}})
    s.create_animation("c", "pulse", duration=1)
    s.set_keyframes("c", "pulse", "box", "style.fill.params.t", [{"t": 0, "value": 0}, {"t": 1, "value": 1}])
    st = s.store()
    from uiforge_mcp import animation as anim
    c = st.get("c")
    frame, _ = anim.apply_animation(c, c["animations"]["pulse"], 0.5, {})
    red = np.asarray(st.renderer(frame).render(include_background=False))[10, 10, 0]
    assert 110 < red < 145


@pytest.mark.parametrize("code", [
    "import os", "r = ().__class__", "r = open('x'); g = 0; b = 0", "r = x.real; g = 0; b = 0",
    "r = __import__('os'); g = 0; b = 0", "r = [1][0]; g = 0; b = 0", "r = lambda: 1; g = 0; b = 0",
    "r = 'a'; g = 0; b = 0", "r = 1; g = 1",
])
def test_shader_rejects_anything_but_math(ws, code):
    s.create_canvas("c", 10, 10)
    with pytest.raises(ValueError, match="shader"):
        s.add_rect("c", 0, 0, 10, 10, style={"fill": {"type": "shader", "code": code}})


def test_shader_too_heavy_is_refused_before_running(ws, monkeypatch):
    from uiforge_mcp import gpu, shader
    monkeypatch.setattr(gpu, "module_for", lambda pixels: np)
    heavy = ";".join(f"q{i} = voronoi(x/9 + {i}, y/9)" for i in range(70)) + "; r = q1; g = 0; b = 0"
    with pytest.raises(ValueError, match="too heavy"):
        shader.evaluate({"code": heavy}, (1024, 1024), (0, 0, 1024, 1024), 1.0, {})
    shader.evaluate({"code": "n = fbm(x, y, 8); r = n; g = n; b = n"}, (64, 64), (0, 0, 64, 64), 1.0, {})


@pytest.mark.parametrize("code,params", [("r = where(u > 0.5); g = 0; b = 0", {}), ("r = t; g = 0; b = 0", {"t": [1]})])
def test_shader_misuse_gives_shader_error(ws, code, params):
    s.create_canvas("c", 8, 8)
    with pytest.raises(ValueError, match="shader"):
        s.add_rect("c", 0, 0, 8, 8, style={"fill": {"type": "shader", "code": code, "params": params}})


def test_shader_huge_power_fails_fast(ws):
    s.create_canvas("c", 10, 10)
    with pytest.raises(ValueError, match="shader"):
        s.add_rect("c", 0, 0, 10, 10, style={"fill": {"type": "shader", "code": "r = 9**9**9; g = 0; b = 0"}})
