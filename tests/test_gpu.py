"""Optional GPU backend: same pictures as the CPU, and the switch to turn it off."""
import numpy as np
import pytest

from uiforge_mcp import effects, gpu, shader

CODE = "n = fbm(x/40, y/40, 6); d = voronoi(x/30, y/30); r = n; g = smoothstep(0, 0.6, d); b = fract(u*7)"


def _cpu(monkeypatch):
    monkeypatch.setattr(gpu, "module_for", lambda pixels: np)


def test_gpu_switch_off_forces_cpu(monkeypatch):
    monkeypatch.setenv("UIFORGE_MCP_GPU", "0")
    gpu._cupy.cache_clear()
    try:
        assert not gpu.available() and gpu.module_for(10**9) is np
        assert gpu.info()["gpu"] is False
    finally:
        monkeypatch.delenv("UIFORGE_MCP_GPU")
        gpu._cupy.cache_clear()


@pytest.mark.skipif(not gpu.available(), reason="no CUDA GPU / CuPy (install the [gpu] extra)")
def test_gpu_shader_matches_cpu(monkeypatch):
    size, box = (700, 500), (0, 0, 700, 500)
    on_gpu = shader.evaluate({"code": CODE}, size, box, 1.0, {})
    _cpu(monkeypatch)
    on_cpu = shader.evaluate({"code": CODE}, size, box, 1.0, {})
    assert np.abs(on_gpu - on_cpu).max() < 1e-3


@pytest.mark.skipif(not gpu.available(), reason="no CUDA GPU / CuPy (install the [gpu] extra)")
def test_gpu_blur_matches_cpu(monkeypatch):
    a = np.zeros((800, 800))
    a[300:500, 300:500] = 255
    on_gpu = effects.blur_float(a, 24)
    _cpu(monkeypatch)
    on_cpu = effects.blur_float(a, 24)
    assert isinstance(on_gpu, np.ndarray) and np.abs(on_gpu - on_cpu).max() < 1e-6


@pytest.mark.skipif(not gpu.available(), reason="no CUDA GPU / CuPy (install the [gpu] extra)")
def test_gpu_raises_the_shader_work_limit():
    heavy = ";".join(f"q{i} = voronoi(x/9 + {i}, y/9)" for i in range(30)) + "; r = q1; g = 0; b = 0"
    shader.evaluate({"code": heavy}, (1024, 1024), (0, 0, 1024, 1024), 1.0, {})
