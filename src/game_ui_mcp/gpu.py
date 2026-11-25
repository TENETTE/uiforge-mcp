"""Pluggable GPU acceleration registry: NVIDIA CUDA (CuPy) + Cross-Vendor WebGPU (wgpu-py) + CPU fallback.

Configure via GAME_UI_MCP_GPU:
  "auto" / "1" (default): prefers CUDA (CuPy) -> WebGPU (wgpu-py Vulkan/DX12/Metal) -> CPU (OpenCV SIMD + NumPy).
  "cuda": force NVIDIA CuPy backend when available.
  "wgpu": force WebGPU compute backend (Vulkan / DirectX 12 / Metal via wgpu-py).
  "cpu" / "0" / "off": force CPU-only execution with identical deterministic results.
"""

from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Any

import numpy as np

MIN_PIXELS = 65_536
_GPU_LOCK = threading.Lock()
_OVERRIDE: str | None = None


def select_backend(name: str | None) -> None:
    """Explicitly select backend ('auto', 'cuda', 'wgpu', 'cpu') at runtime (used by tests & CLI)."""
    global _OVERRIDE
    if name is None:
        _OVERRIDE = None
    else:
        val = str(name).strip().lower()
        if val not in ("auto", "cuda", "cupy", "wgpu", "webgpu", "cpu", "0", "off"):
            raise ValueError(f"Unknown GPU backend '{name}'. Choose one of: auto, cuda, wgpu, cpu")
        _OVERRIDE = "cpu" if val in ("0", "off") else ("wgpu" if val == "webgpu" else ("cuda" if val == "cupy" else val))
    _cupy.cache_clear()


def _requested_mode() -> str:
    if _OVERRIDE is not None:
        return _OVERRIDE
    raw = os.environ.get("GAME_UI_MCP_GPU", "auto").strip().lower()
    if raw in ("0", "false", "off", "no", "cpu"):
        return "cpu"
    if raw in ("wgpu", "webgpu"):
        return "wgpu"
    if raw in ("cuda", "cupy"):
        return "cuda"
    return "auto"


@lru_cache(maxsize=1)
def _cupy():
    """The CuPy module if installed and a CUDA device answers, else None (checked once)."""
    mode = _requested_mode()
    if mode in ("cpu", "wgpu"):
        return None
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import cupy
        cupy.cuda.runtime.getDeviceCount()
        cupy.asarray([1.0], dtype=cupy.float32).sum().item()
        return cupy
    except Exception:
        return None


def wgpu_available() -> bool:
    if _requested_mode() in ("cpu", "cuda"):
        return False
    from . import gpu_wgpu
    return gpu_wgpu.available()


def backend_name(pixels: int = MIN_PIXELS) -> str:
    """Active compute backend for an operation of ``pixels`` pixels: 'cuda', 'wgpu' or 'cpu'."""
    if pixels < MIN_PIXELS:
        return "cpu"
    mode = _requested_mode()
    if mode == "cpu":
        return "cpu"
    if mode == "wgpu":
        return "wgpu" if wgpu_available() else "cpu"
    if mode == "cuda":
        return "cuda" if _cupy() is not None else "cpu"
    if _cupy() is not None:
        return "cuda"
    if wgpu_available():
        return "wgpu"
    return "cpu"


def available() -> bool:
    return _cupy() is not None or wgpu_available()


def module_for(pixels: int):
    """numpy or cupy for an array of this many pixels."""
    cp = _cupy()
    return cp if cp is not None and pixels >= MIN_PIXELS else np


def array_module(a):
    """The module that owns array ``a`` (cupy for GPU arrays, numpy otherwise)."""
    cp = _cupy()
    if cp is not None and isinstance(a, cp.ndarray):
        return cp
    return np


def to_numpy(a) -> np.ndarray:
    cp = _cupy()
    if cp is not None and isinstance(a, cp.ndarray):
        return cp.asnumpy(a)
    return np.asarray(a)


def gpu_lock() -> threading.Lock:
    """Serialize GPU kernel launches across worker threads."""
    return _GPU_LOCK


def info() -> dict[str, Any]:
    from . import gpu_wgpu
    active = backend_name(MIN_PIXELS)
    cp = _cupy()
    cuda_info: dict[str, Any] = {"available": False}
    if cp is not None:
        props = cp.cuda.runtime.getDeviceProperties(cp.cuda.Device().id)
        name = props["name"].decode() if isinstance(props["name"], bytes) else str(props["name"])
        cuda_info = {"available": True, "device": name, "cupy": cp.__version__}
    wgpu_info = gpu_wgpu.info()
    out: dict[str, Any] = {"gpu": active != "cpu", "backend": active, "cuda": cuda_info, "wgpu": wgpu_info}
    if active == "cuda":
        out["device"] = cuda_info["device"]
        out["cupy"] = cuda_info["cupy"]
    elif active == "wgpu":
        out["device"] = wgpu_info.get("device", "WebGPU")
        out["adapter_backend"] = wgpu_info.get("backend_type", "")
    else:
        out["hint"] = 'install "game-ui-mcp[wgpu]" (cross-GPU Vulkan/DX12/Metal) or "game-ui-mcp[gpu]" (NVIDIA CUDA 12)'
    return out
