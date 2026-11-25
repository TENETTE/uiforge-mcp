"""Shader fill: per-pixel formulas the model writes itself, evaluated in float32 on numpy or fused CUDA kernels.

{"type": "shader", "code": "...", "params": {...}} paints any procedural look (energy, plasma, scanlines,
holograms, wood, marble, rust, rings, ripples, distortion of a pattern...) that the fixed fill types
cannot. The code is a tiny expression language checked against a whitelist (no attributes, imports,
loops or calls outside FUNCS), so it can only compute numbers - it cannot touch files or the system.
"""

from __future__ import annotations

import ast
import hashlib
from functools import lru_cache

import numpy as np

from . import gpu
from .colors import parse_color

MAX_CODE = 6000
MAX_STATEMENTS = 80
MAX_WORK = 85e6
GPU_WORK_FACTOR = 20


def _m(*values):
    """numpy, or cupy when any value lives on the GPU: every helper below runs on either."""
    for v in values:
        xp = gpu.array_module(v)
        if xp is not np:
            return xp
    return np


def _f32(xp, v):
    if isinstance(v, (int, float)):
        return np.float32(v)
    return xp.asarray(v, dtype=xp.float32)


def _fract(a):
    xp = _m(a)
    a = _f32(xp, a)
    return a - xp.floor(a)


def _hash(ix, iy, seed=0.0):
    """Bit-exact uint32 lattice hash -> 0..1 float32 (0 divergence between CPU and GPU)."""
    xp = _m(ix, iy, seed)
    a = xp.asarray(ix, dtype=xp.float32).astype(xp.int32).view(xp.uint32)
    b = xp.asarray(iy, dtype=xp.float32).astype(xp.int32).view(xp.uint32)
    s = xp.round(xp.asarray(seed, dtype=xp.float32) * np.float32(100.0)).astype(xp.int32).view(xp.uint32)
    with np.errstate(over="ignore"):
        h = (a * np.uint32(374761393)) ^ (b * np.uint32(668265263)) ^ (s * np.uint32(2147483647))
        h = (h ^ (h >> np.uint32(13))) * np.uint32(1274126177)
        h = (h ^ (h >> np.uint32(16))) & np.uint32(0x00FFFFFF)
    return h.astype(xp.float32) * np.float32(1.0 / 16777216.0)


def _noise(x, y, seed=0.0):
    """Smooth value noise, 0..1, one feature per unit."""
    xp = _m(x, y, seed)
    x, y = _f32(xp, x), _f32(xp, y)
    ix, iy = xp.floor(x), xp.floor(y)
    fx, fy = x - ix, y - iy
    ux = fx * fx * (np.float32(3.0) - np.float32(2.0) * fx)
    uy = fy * fy * (np.float32(3.0) - np.float32(2.0) * fy)
    one = np.float32(1.0)
    a, b = _hash(ix, iy, seed), _hash(ix + one, iy, seed)
    c, d = _hash(ix, iy + one, seed), _hash(ix + one, iy + one, seed)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def _fbm(x, y, octaves=5, seed=0.0):
    """Fractal noise (sum of noise octaves), 0..1. Clouds, smoke, marble, terrain, grunge."""
    xp = _m(x, y, octaves, seed)
    n = int(max(1, min(8, float(xp.max(xp.asarray(octaves))))))
    total, amp, norm, f = np.float32(0.0), np.float32(0.5), np.float32(0.0), np.float32(1.0)
    x, y = _f32(xp, x), _f32(xp, y)
    s0 = _f32(xp, seed)
    for i in range(n):
        total = total + amp * _noise(x * f, y * f, s0 + np.float32(i * 17.0))
        norm = np.float32(norm + amp)
        amp = np.float32(amp * 0.5)
        f = np.float32(f * 2.0)
    return total / norm


def _ridged(x, y, octaves=4, seed=0.0):
    """Ridged multifractal noise, 0..1. Sharp veins, cracks, hammered metal, lightning, stone."""
    xp = _m(x, y, octaves, seed)
    n = int(max(1, min(8, float(xp.max(xp.asarray(octaves))))))
    total, amp, norm, f = np.float32(0.0), np.float32(0.5), np.float32(0.0), np.float32(1.0)
    x, y = _f32(xp, x), _f32(xp, y)
    s0 = _f32(xp, seed)
    for i in range(n):
        r = np.float32(1.0) - xp.abs(_noise(x * f, y * f, s0 + np.float32(i * 17.0)) * np.float32(2.0) - np.float32(1.0))
        total = total + amp * (r * r)
        norm = np.float32(norm + amp)
        amp = np.float32(amp * 0.5)
        f = np.float32(f * 2.0)
    return total / norm


def _turbulence(x, y, octaves=4, seed=0.0):
    """Absolute-value fractal turbulence, 0..1. Fire, marble wisps, plasma, jade."""
    xp = _m(x, y, octaves, seed)
    n = int(max(1, min(8, float(xp.max(xp.asarray(octaves))))))
    total, amp, norm, f = np.float32(0.0), np.float32(0.5), np.float32(0.0), np.float32(1.0)
    x, y = _f32(xp, x), _f32(xp, y)
    s0 = _f32(xp, seed)
    for i in range(n):
        t = xp.abs(_noise(x * f, y * f, s0 + np.float32(i * 17.0)) * np.float32(2.0) - np.float32(1.0))
        total = total + amp * t
        norm = np.float32(norm + amp)
        amp = np.float32(amp * 0.5)
        f = np.float32(f * 2.0)
    return total / norm


def _voronoi(x, y, seed=0.0):
    """Distance to the nearest random cell point (0 at a point, ~0.7 max). Cells, scales, cracks, crystals."""
    xp = _m(x, y, seed)
    x, y = _f32(xp, x), _f32(xp, y)
    s = _f32(xp, seed)
    ix, iy = xp.floor(x), xp.floor(y)
    bx, by = xp.broadcast_arrays(x, y)
    best = xp.full(bx.shape, np.float32(9.0), dtype=xp.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cx, cy = ix + np.float32(dx), iy + np.float32(dy)
            px = cx + _hash(cx, cy, s + np.float32(1.3))
            py = cy + _hash(cx, cy, s + np.float32(7.9))
            best = xp.minimum(best, xp.hypot(px - x, py - y))
    return best


def _smoothstep(e0, e1, v):
    xp = _m(e0, e1, v)
    e0, e1, v = _f32(xp, e0), _f32(xp, e1), _f32(xp, v)
    diff = e1 - e0
    denom = xp.where(diff == np.float32(0.0), np.float32(1e-6), diff)
    t = xp.clip((v - e0) / denom, np.float32(0.0), np.float32(1.0))
    return t * t * (np.float32(3.0) - np.float32(2.0) * t)


def _funcs(xp) -> dict:
    """The shader function table built on numpy or cupy (same names, same maths in float32)."""
    z0, z1, eps = np.float32(0.0), np.float32(1.0), np.float32(1e-7)
    return {
        "sin": lambda a: xp.sin(_f32(xp, a)),
        "cos": lambda a: xp.cos(_f32(xp, a)),
        "tan": lambda a: xp.tan(_f32(xp, a)),
        "asin": lambda a: xp.arcsin(xp.clip(_f32(xp, a), np.float32(-1.0), z1)),
        "acos": lambda a: xp.arccos(xp.clip(_f32(xp, a), np.float32(-1.0), z1)),
        "atan": lambda a: xp.arctan(_f32(xp, a)),
        "atan2": lambda a, b: xp.arctan2(_f32(xp, a), _f32(xp, b)),
        "sqrt": lambda a: xp.sqrt(xp.maximum(_f32(xp, a), z0)),
        "abs": lambda a: xp.abs(_f32(xp, a)),
        "exp": lambda a: xp.exp(xp.clip(_f32(xp, a), np.float32(-40.0), np.float32(40.0))),
        "log": lambda a: xp.log(xp.maximum(_f32(xp, a), eps)),
        "pow": lambda a, b: xp.power(xp.maximum(_f32(xp, a), z0), _f32(xp, b)),
        "floor": lambda a: xp.floor(_f32(xp, a)),
        "ceil": lambda a: xp.ceil(_f32(xp, a)),
        "round": lambda a: xp.round(_f32(xp, a)),
        "fract": _fract,
        "mod": lambda a, b: xp.mod(_f32(xp, a), _f32(xp, b)),
        "min": lambda a, b: xp.minimum(_f32(xp, a), _f32(xp, b)),
        "max": lambda a, b: xp.maximum(_f32(xp, a), _f32(xp, b)),
        "sign": lambda a: xp.sign(_f32(xp, a)),
        "clamp": lambda a, lo=0.0, hi=1.0: xp.clip(_f32(xp, a), _f32(xp, lo), _f32(xp, hi)),
        "mix": lambda a, b, t: _f32(xp, a) + (_f32(xp, b) - _f32(xp, a)) * _f32(xp, t),
        "step": lambda edge, a: (_f32(xp, a) >= _f32(xp, edge)).astype(xp.float32),
        "smoothstep": _smoothstep,
        "length": lambda a, b: xp.hypot(_f32(xp, a), _f32(xp, b)),
        "hypot": lambda a, b: xp.hypot(_f32(xp, a), _f32(xp, b)),
        "where": lambda c, a, b: xp.where(xp.asarray(c), _f32(xp, a), _f32(xp, b)),
        "noise": _noise,
        "fbm": _fbm,
        "ridged": _ridged,
        "turbulence": _turbulence,
        "voronoi": _voronoi,
        "rand": lambda a, b, seed=0.0: _hash(xp.floor(_f32(xp, a)), xp.floor(_f32(xp, b)), seed),
    }


FUNCS = _funcs(np)
_NODES = (ast.Module, ast.Assign, ast.Expr, ast.Name, ast.Load, ast.Store, ast.Constant, ast.BinOp, ast.UnaryOp,
          ast.Compare, ast.Call, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub,
          ast.UAdd, ast.BitAnd, ast.BitOr, ast.Invert, ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq)
INPUTS = ("x", "y", "u", "v", "w", "h", "px", "pi", "d", "edge")
OUTPUTS = ("r", "g", "b", "a")


@lru_cache(maxsize=256)
def _parse_and_validate(code: str):
    if len(code) > MAX_CODE:
        raise ValueError(f"shader code is over {MAX_CODE} characters")
    try:
        lines = (ln.strip() for ln in code.replace(";", "\n").splitlines())
        tree = ast.parse("\n".join(lines), mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"shader code: syntax error on line {exc.lineno}: {exc.msg}") from exc
    if len(tree.body) > MAX_STATEMENTS:
        raise ValueError(f"shader code: at most {MAX_STATEMENTS} statements")
    for node in ast.walk(tree):
        if not isinstance(node, _NODES):
            raise ValueError(f"shader code: '{type(node).__name__}' is not allowed - use plain assignments, "
                             "arithmetic, comparisons and the listed functions (where() instead of if)")
        if isinstance(node, ast.Assign) and not all(isinstance(t, ast.Name) for t in node.targets):
            raise ValueError("shader code: assign to plain names only")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("shader code: names cannot start with '_'")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS or node.keywords:
                raise ValueError(f"shader code: unknown function. Available: {', '.join(sorted(FUNCS))}")
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ValueError("shader code: only number constants (put colours in params)")
            node.value = float(node.value)
    assigned = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets}
    if not {"r", "g", "b"} <= assigned:
        raise ValueError("shader code must assign r, g and b (0..1); a (alpha 0..1) is optional")
    return tree, compile(tree, "<shader>", "exec"), _cost(tree), "height" in assigned


def compile_code(code: str):
    """Compile and cost-check shader code. Returns (compiled_code, cost_units)."""
    _, compiled, units, _ = _parse_and_validate(code)
    return compiled, units


def _cost(tree) -> float:
    """Work per pixel in 'noise calls' (one is ~0.06 s per megapixel on CPU), so a heavy formula is refused."""
    units = 0.1 * len(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id
            if name in ("fbm", "ridged", "turbulence"):
                oct_arg = node.args[2] if len(node.args) > 2 else None
                units += min(8.0, max(1.0, oct_arg.value)) if isinstance(oct_arg, ast.Constant) else \
                    (5.0 if oct_arg is None else 8.0)
            elif name == "voronoi":
                units += 4.0
            elif name in ("noise", "rand"):
                units += 1.0
    return units


_CUDA_PREAMBLE = r"""
__device__ inline float s_fract(float a) { return a - floorf(a); }
__device__ inline float s_mod(float a, float b) {
    float r = fmodf(a, b);
    return (r != 0.0f && ((r < 0.0f) != (b < 0.0f))) ? r + b : r;
}
__device__ inline float s_clamp(float a, float lo, float hi) { return fminf(hi, fmaxf(lo, a)); }
__device__ inline float s_mix(float a, float b, float t) { return a + (b - a) * t; }
__device__ inline float s_step(float e, float a) { return a >= e ? 1.0f : 0.0f; }
__device__ inline float s_smoothstep(float e0, float e1, float v) {
    float diff = e1 - e0;
    float t = s_clamp((v - e0) / (diff == 0.0f ? 1e-6f : diff), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}
__device__ inline float s_sign(float a) { return (a > 0.0f) ? 1.0f : ((a < 0.0f) ? -1.0f : 0.0f); }
__device__ inline float s_hash(float ix, float iy, float seed) {
    unsigned int a = (unsigned int)(int)ix;
    unsigned int b = (unsigned int)(int)iy;
    unsigned int s = (unsigned int)(int)rintf(seed * 100.0f);
    unsigned int h = (a * 374761393u) ^ (b * 668265263u) ^ (s * 2147483647u);
    h = (h ^ (h >> 13)) * 1274126177u;
    h = (h ^ (h >> 16)) & 0x00FFFFFFu;
    return (float)h * (1.0f / 16777216.0f);
}
__device__ inline float s_noise(float x, float y, float seed) {
    float ix = floorf(x), iy = floorf(y);
    float fx = x - ix, fy = y - iy;
    float ux = fx * fx * (3.0f - 2.0f * fx);
    float uy = fy * fy * (3.0f - 2.0f * fy);
    float a = s_hash(ix, iy, seed);
    float b = s_hash(ix + 1.0f, iy, seed);
    float c = s_hash(ix, iy + 1.0f, seed);
    float d = s_hash(ix + 1.0f, iy + 1.0f, seed);
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
}
__device__ inline float s_fbm(float x, float y, float oct, float seed) {
    int n = (int)s_clamp(oct, 1.0f, 8.0f);
    float total = 0.0f, amp = 0.5f, norm = 0.0f, f = 1.0f;
    for (int i = 0; i < n; ++i) {
        total += amp * s_noise(x * f, y * f, seed + i * 17.0f);
        norm += amp; amp *= 0.5f; f *= 2.0f;
    }
    return total / norm;
}
__device__ inline float s_ridged(float x, float y, float oct, float seed) {
    int n = (int)s_clamp(oct, 1.0f, 8.0f);
    float total = 0.0f, amp = 0.5f, norm = 0.0f, f = 1.0f;
    for (int i = 0; i < n; ++i) {
        float r = 1.0f - fabsf(s_noise(x * f, y * f, seed + i * 17.0f) * 2.0f - 1.0f);
        total += amp * r * r;
        norm += amp; amp *= 0.5f; f *= 2.0f;
    }
    return total / norm;
}
__device__ inline float s_turbulence(float x, float y, float oct, float seed) {
    int n = (int)s_clamp(oct, 1.0f, 8.0f);
    float total = 0.0f, amp = 0.5f, norm = 0.0f, f = 1.0f;
    for (int i = 0; i < n; ++i) {
        total += amp * fabsf(s_noise(x * f, y * f, seed + i * 17.0f) * 2.0f - 1.0f);
        norm += amp; amp *= 0.5f; f *= 2.0f;
    }
    return total / norm;
}
__device__ inline float s_voronoi(float x, float y, float seed) {
    float ix = floorf(x), iy = floorf(y), best = 9.0f;
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            float cx = ix + (float)dx, cy = iy + (float)dy;
            float px = cx + s_hash(cx, cy, seed + 1.3f);
            float py = cy + s_hash(cx, cy, seed + 7.9f);
            float dist = hypotf(px - x, py - y);
            if (dist < best) best = dist;
        }
    }
    return best;
}
"""


def _emit_cuda(node: ast.AST, known: set[str]) -> str:
    """Translate a validated shader AST node into a float32 CUDA C++ expression."""
    if isinstance(node, ast.Constant):
        v = float(node.value)
        if not np.isfinite(v):
            raise ValueError("non-finite constant")
        return f"({v:.8e}f)"
    if isinstance(node, ast.Name):
        if node.id not in known:
            raise ValueError(f"unknown name '{node.id}'")
        return f"v_{node.id}"
    if isinstance(node, ast.UnaryOp):
        inner = _emit_cuda(node.operand, known)
        if isinstance(node.op, ast.USub):
            return f"(-{inner})"
        if isinstance(node.op, ast.UAdd):
            return f"(+{inner})"
        if isinstance(node.op, ast.Invert):
            return f"((float)(!((bool){inner})))"
        raise ValueError("unsupported unary op")
    if isinstance(node, ast.BinOp):
        l, r = _emit_cuda(node.left, known), _emit_cuda(node.right, known)
        if isinstance(node.op, ast.Add):
            return f"({l} + {r})"
        if isinstance(node.op, ast.Sub):
            return f"({l} - {r})"
        if isinstance(node.op, ast.Mult):
            return f"({l} * {r})"
        if isinstance(node.op, ast.Div):
            return f"({l} / {r})"
        if isinstance(node.op, ast.FloorDiv):
            return f"floorf({l} / {r})"
        if isinstance(node.op, ast.Mod):
            return f"s_mod({l}, {r})"
        if isinstance(node.op, ast.Pow):
            return f"powf(fmaxf({l}, 0.0f), {r})"
        if isinstance(node.op, ast.BitAnd):
            return f"((float)((({l}) != 0.0f) && (({r}) != 0.0f)))"
        if isinstance(node.op, ast.BitOr):
            return f"((float)((({l}) != 0.0f) || (({r}) != 0.0f)))"
        raise ValueError("unsupported binop")
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1:
            raise ValueError("chained compare")
        l, r = _emit_cuda(node.left, known), _emit_cuda(node.comparators[0], known)
        op_map = {ast.Lt: "<", ast.Gt: ">", ast.LtE: "<=", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}
        return f"((float)({l} {op_map[type(node.ops[0])]} {r}))"
    if isinstance(node, ast.Call):
        fn = node.func.id
        a = [_emit_cuda(arg, known) for arg in node.args]
        if fn in ("sin", "cos", "tan", "atan", "floor", "ceil", "round"):
            return f"{fn}f({a[0]})"
        if fn == "abs":
            return f"fabsf({a[0]})"
        if fn == "asin":
            return f"asinf(s_clamp({a[0]}, -1.0f, 1.0f))"
        if fn == "acos":
            return f"acosf(s_clamp({a[0]}, -1.0f, 1.0f))"
        if fn == "atan2":
            return f"atan2f({a[0]}, {a[1]})"
        if fn == "sqrt":
            return f"sqrtf(fmaxf({a[0]}, 0.0f))"
        if fn == "exp":
            return f"expf(s_clamp({a[0]}, -40.0f, 40.0f))"
        if fn == "log":
            return f"logf(fmaxf({a[0]}, 1e-7f))"
        if fn == "pow":
            return f"powf(fmaxf({a[0]}, 0.0f), {a[1]})"
        if fn == "fract":
            return f"s_fract({a[0]})"
        if fn == "mod":
            return f"s_mod({a[0]}, {a[1]})"
        if fn == "min":
            return f"fminf({a[0]}, {a[1]})"
        if fn == "max":
            return f"fmaxf({a[0]}, {a[1]})"
        if fn == "sign":
            return f"s_sign({a[0]})"
        if fn == "clamp":
            lo = a[1] if len(a) > 1 else "0.0f"
            hi = a[2] if len(a) > 2 else "1.0f"
            return f"s_clamp({a[0]}, {lo}, {hi})"
        if fn == "mix":
            return f"s_mix({a[0]}, {a[1]}, {a[2]})"
        if fn == "step":
            return f"s_step({a[0]}, {a[1]})"
        if fn == "smoothstep":
            return f"s_smoothstep({a[0]}, {a[1]}, {a[2]})"
        if fn in ("length", "hypot"):
            return f"hypotf({a[0]}, {a[1]})"
        if fn == "where":
            if len(a) != 3:
                raise ValueError("where requires 3 args")
            return f"(({a[0]} != 0.0f) ? ({a[1]}) : ({a[2]}))"
        if fn == "noise":
            s = a[2] if len(a) > 2 else "0.0f"
            return f"s_noise({a[0]}, {a[1]}, {s})"
        if fn in ("fbm", "ridged", "turbulence"):
            oct_a = a[2] if len(a) > 2 else ("5.0f" if fn == "fbm" else "4.0f")
            s = a[3] if len(a) > 3 else "0.0f"
            return f"s_{fn}({a[0]}, {a[1]}, {oct_a}, {s})"
        if fn == "voronoi":
            s = a[2] if len(a) > 2 else "0.0f"
            return f"s_voronoi({a[0]}, {a[1]}, {s})"
        if fn == "rand":
            s = a[2] if len(a) > 2 else "0.0f"
            return f"s_hash(floorf({a[0]}), floorf({a[1]}), {s})"
    raise ValueError("cannot emit cuda")


@lru_cache(maxsize=128)
def _cuda_kernel(code: str, param_names: tuple[str, ...], has_sdf: bool, want_height: bool):
    """Build and cache a single fused CuPy ElementwiseKernel for a validated shader."""
    cp = gpu._cupy()
    if cp is None:
        return None
    tree, _, _, has_height = _parse_and_validate(code)
    known = set(INPUTS) | set(param_names)
    declared: set[str] = set()
    body = [
        "int px_i = i % w_px;",
        "int py_i = i / w_px;",
        "float xs = (float)px_i + 0.5f;",
        "float ys = (float)py_i + 0.5f;",
        "float v_x = (xs - x0) / k_val;",
        "float v_y = (ys - y0) / k_val;",
        "float v_u = (xs - x0) / bw_px;",
        "float v_v = (ys - y0) / bh_px;",
        "float v_w = bw_u;",
        "float v_h = bh_u;",
        "float v_px = k_val;",
        "float v_pi = 3.141592653589793f;",
        "float v_d = " + ("sdf_in[i];" if has_sdf else "fminf(fminf(v_x, v_w - v_x), fminf(v_y, v_h - v_y));"),
        "float v_edge = s_clamp(v_d / fmaxf(1.0f, fminf(v_w, v_h) * 0.25f), 0.0f, 1.0f);",
        "float v_a = 1.0f;",
        "float v_height = 0.5f;",
    ]
    declared.update(known)
    declared.update({"a", "height"})
    try:
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                expr = _emit_cuda(stmt.value, known)
                for tgt in stmt.targets:
                    name = tgt.id
                    if name not in declared:
                        body.append(f"float v_{name} = {expr};")
                        declared.add(name)
                        known.add(name)
                    else:
                        body.append(f"v_{name} = {expr};")
            elif isinstance(stmt, ast.Expr):
                _emit_cuda(stmt.value, known)
    except Exception:
        return None
    body += [
        "out_r = isnan(v_r) ? 0.0f : s_clamp(v_r, 0.0f, 1.0f) * 255.0f;",
        "out_g = isnan(v_g) ? 0.0f : s_clamp(v_g, 0.0f, 1.0f) * 255.0f;",
        "out_b = isnan(v_b) ? 0.0f : s_clamp(v_b, 0.0f, 1.0f) * 255.0f;",
        "out_a = isnan(v_a) ? 0.0f : s_clamp(v_a, 0.0f, 1.0f) * 255.0f;",
    ]
    in_params = ["int32 w_px", "float32 x0", "float32 y0", "float32 bw_px", "float32 bh_px",
                 "float32 bw_u", "float32 bh_u", "float32 k_val"]
    if has_sdf:
        in_params.append("raw float32 sdf_in")
    for pname in param_names:
        in_params.append(f"float32 v_{pname}")
    out_params = "float32 out_r, float32 out_g, float32 out_b, float32 out_a"
    if want_height and has_height:
        body.append("out_h = isnan(v_height) ? 0.5f : s_clamp(v_height, 0.0f, 1.0f);")
        out_params += ", float32 out_h"
    sig = hashlib.sha1(f"{code}|{param_names}|{has_sdf}|{want_height}".encode()).hexdigest()[:12]
    try:
        return cp.ElementwiseKernel(", ".join(in_params), out_params, "\n".join(body),
                                    name=f"gui_sh_{sig}", preamble=_CUDA_PREAMBLE)
    except Exception:
        return None


def _env(params: dict, colors: dict) -> dict:
    env: dict = {}
    for key, value in (params or {}).items():
        if not str(key).isidentifier() or key.startswith("_") or key in INPUTS or key in FUNCS:
            raise ValueError(f"shader param '{key}' must be a plain name not used by inputs or functions")
        if isinstance(value, str):
            r, g, b, a = parse_color(value, colors)
            env.update({f"{key}_r": np.float32(r / 255.0), f"{key}_g": np.float32(g / 255.0),
                        f"{key}_b": np.float32(b / 255.0), f"{key}_a": np.float32(a / 255.0)})
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            env[key] = np.float32(value)
        else:
            raise ValueError(f"shader param '{key}' must be a number or a colour string, got {type(value).__name__}")
    return env


def evaluate_surface(spec: dict, size: tuple[int, int], box_px, k: float, colors: dict,
                     sdf: np.ndarray | None = None, want_height: bool = False) -> tuple[np.ndarray, np.ndarray | None]:
    """Evaluate a shader fill. Returns (rgba float32 0..255 (h, w, 4), optional bump height float32 0..1 (h, w))."""
    code_str = str(spec.get("code", ""))
    tree, code, units, has_height = _parse_and_validate(code_str)
    w_px, h_px = size
    n_pix = w_px * h_px
    backend = gpu.backend_name(n_pix)
    xp = gpu.module_for(n_pix)
    use_gpu = (xp is not np) or (backend == "wgpu")
    budget = MAX_WORK * (GPU_WORK_FACTOR if use_gpu else 1)
    if units * n_pix > budget:
        raise ValueError(f"shader code is too heavy for a {w_px}x{h_px} px fill (~{units:.0f} noise calls per "
                         f"pixel, limit ~{budget / n_pix:.0f}): use fewer fbm octaves or "
                         "voronoi/noise calls, or compute a value once and reuse it")
    x0, y0, x1, y1 = box_px
    bw_px = max(1e-6, float(x1 - x0))
    bh_px = max(1e-6, float(y1 - y0))
    bw_u, bh_u = bw_px / float(k), bh_px / float(k)
    env = _env(spec.get("params") or {}, colors)

    if backend == "wgpu":
        from . import gpu_wgpu
        pnames = tuple(sorted(env))
        pvals = tuple(float(env[p]) for p in pnames)
        wgpu_res = gpu_wgpu.eval_shader(tree, size, box_px, k, pnames, pvals, sdf=sdf, want_height=want_height and has_height)
        if wgpu_res is not None:
            return wgpu_res

    if xp is not np:
        pnames = tuple(sorted(env))
        kern = _cuda_kernel(code_str, pnames, sdf is not None, want_height and has_height)
        if kern is not None:
            with gpu.gpu_lock():
                n_pix = w_px * h_px
                out_r = xp.empty(n_pix, dtype=xp.float32)
                out_g = xp.empty(n_pix, dtype=xp.float32)
                out_b = xp.empty(n_pix, dtype=xp.float32)
                out_a = xp.empty(n_pix, dtype=xp.float32)
                args: list = [np.int32(w_px), np.float32(x0), np.float32(y0), np.float32(bw_px), np.float32(bh_px),
                              np.float32(bw_u), np.float32(bh_u), np.float32(k)]
                if sdf is not None:
                    args.append(xp.asarray(sdf, dtype=xp.float32).ravel())
                args += [np.float32(env[p]) for p in pnames]
                if want_height and has_height:
                    out_h = xp.empty(n_pix, dtype=xp.float32)
                    kern(*args, out_r, out_g, out_b, out_a, out_h)
                    rgba = xp.stack([out_r, out_g, out_b, out_a], axis=-1).reshape(h_px, w_px, 4)
                    return gpu.to_numpy(rgba), gpu.to_numpy(out_h.reshape(h_px, w_px))
                kern(*args, out_r, out_g, out_b, out_a)
                rgba = xp.stack([out_r, out_g, out_b, out_a], axis=-1).reshape(h_px, w_px, 4)
                return gpu.to_numpy(rgba), None

    def _run():
        xs = (xp.arange(w_px, dtype=xp.float32)[None, :] + np.float32(0.5))
        ys = (xp.arange(h_px, dtype=xp.float32)[:, None] + np.float32(0.5))
        x_u = (xs - np.float32(x0)) / np.float32(k)
        y_u = (ys - np.float32(y0)) / np.float32(k)
        if sdf is not None:
            d_arr = xp.asarray(sdf, dtype=xp.float32)
        else:
            d_arr = xp.minimum(xp.minimum(x_u, np.float32(bw_u) - x_u), xp.minimum(y_u, np.float32(bh_u) - y_u))
        edge_arr = xp.clip(d_arr / np.float32(max(1.0, min(bw_u, bh_u) * 0.25)), np.float32(0.0), np.float32(1.0))
        ns = {"__builtins__": {}}
        ns.update(_funcs(xp))
        ns.update(env)
        ns.update({
            "x": x_u, "y": y_u,
            "u": (xs - np.float32(x0)) / np.float32(bw_px),
            "v": (ys - np.float32(y0)) / np.float32(bh_px),
            "w": np.float32(bw_u), "h": np.float32(bh_u),
            "px": np.float32(k), "pi": np.float32(np.pi),
            "d": d_arr, "edge": edge_arr,
        })
        with np.errstate(all="ignore"):
            try:
                exec(code, ns)
            except (TypeError, ValueError, ZeroDivisionError, OverflowError, NameError) as exc:
                raise ValueError(f"shader code failed: {exc}") from exc
        out = xp.empty((h_px, w_px, 4), dtype=xp.float32)
        for i, name in enumerate(OUTPUTS):
            try:
                val = xp.broadcast_to(xp.asarray(ns.get(name, np.float32(1.0)), dtype=xp.float32), (h_px, w_px))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"shader output '{name}' must be one number per pixel (where() needs 3 arguments: "
                                 "condition, value_if_true, value_if_false)") from exc
            out[..., i] = xp.nan_to_num(xp.clip(val, np.float32(0.0), np.float32(1.0)))
        h_out = None
        if want_height and "height" in ns:
            try:
                hv = xp.broadcast_to(xp.asarray(ns["height"], dtype=xp.float32), (h_px, w_px))
                h_out = gpu.to_numpy(xp.nan_to_num(xp.clip(hv, np.float32(0.0), np.float32(1.0))))
            except (TypeError, ValueError):
                h_out = None
        return gpu.to_numpy(out * np.float32(255.0)), h_out

    if xp is not np:
        with gpu.gpu_lock():
            return _run()
    return _run()


def evaluate(spec: dict, size: tuple[int, int], box_px, k: float, colors: dict,
             sdf: np.ndarray | None = None) -> np.ndarray:
    """RGBA float32 array 0..255 of shape (h, w, 4) for the shader fill."""
    rgba, _ = evaluate_surface(spec, size, box_px, k, colors, sdf=sdf, want_height=False)
    return rgba
