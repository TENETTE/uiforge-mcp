"""Cross-vendor WebGPU compute backend (wgpu-py: Vulkan / DirectX 12 / Metal).

Compiles sandboxed shader ASTs directly into WGSL @compute shaders with bit-exact u32 lattice hashing
matching CPU NumPy and CUDA C++, and provides a WGSL Cook-Torrance GGX PBR compute shader.
Optional extra: pip install "uiforge-mcp[wgpu]".
"""

from __future__ import annotations

import ast
import math
import struct
import threading
from typing import Any

import numpy as np

_LOCK = threading.Lock()
_DEVICE = None
_ADAPTER_INFO: dict[str, Any] | None = None
_CHECKED = False
_PIPELINE_CACHE: dict[tuple[str, int], tuple[Any, Any]] = {}

_WGSL_HELPERS = r"""
fn _hash_u32(ix: i32, iy: i32, seed: f32) -> f32 {
    let a: u32 = bitcast<u32>(ix);
    let b: u32 = bitcast<u32>(iy);
    let s: u32 = bitcast<u32>(i32(round(seed * 100.0)));
    var h: u32 = (a * 374761393u) ^ (b * 668265263u) ^ (s * 2147483647u);
    h = (h ^ (h >> 13u)) * 1274126177u;
    h = (h ^ (h >> 16u)) & 16777215u;
    return f32(h) * (1.0 / 16777216.0);
}
fn _fract(v: f32) -> f32 { return v - floor(v); }
fn _mod(a: f32, b: f32) -> f32 { return a - b * floor(a / b); }
fn _clamp01(v: f32) -> f32 { return clamp(v, 0.0, 1.0); }
fn _step(e: f32, v: f32) -> f32 { return select(0.0, 1.0, v >= e); }
fn _smoothstep(a: f32, b: f32, x: f32) -> f32 {
    let d: f32 = b - a;
    if (abs(d) < 1e-6) { return select(0.0, 1.0, x >= b); }
    let t: f32 = clamp((x - a) / d, 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}
fn _vnoise(x: f32, y: f32, seed: f32) -> f32 {
    let ix: i32 = i32(floor(x));
    let iy: i32 = i32(floor(y));
    let fx: f32 = x - f32(ix);
    let fy: f32 = y - f32(iy);
    let ux: f32 = fx * fx * (3.0 - 2.0 * fx);
    let uy: f32 = fy * fy * (3.0 - 2.0 * fy);
    let a: f32 = _hash_u32(ix, iy, seed);
    let b: f32 = _hash_u32(ix + 1, iy, seed);
    let c: f32 = _hash_u32(ix, iy + 1, seed);
    let d: f32 = _hash_u32(ix + 1, iy + 1, seed);
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
}
fn _fbm(x: f32, y: f32, oct: i32, seed: f32) -> f32 {
    var total: f32 = 0.0;
    var amp: f32 = 0.5;
    var freq: f32 = 1.0;
    var norm: f32 = 0.0;
    let n: i32 = clamp(oct, 1, 8);
    for (var i: i32 = 0; i < 8; i = i + 1) {
        if (i >= n) { break; }
        total = total + amp * _vnoise(x * freq, y * freq, seed + f32(i) * 17.0);
        norm = norm + amp;
        amp = amp * 0.5;
        freq = freq * 2.0;
    }
    return total / norm;
}
fn _ridged(x: f32, y: f32, oct: i32, seed: f32) -> f32 {
    var total: f32 = 0.0;
    var amp: f32 = 0.5;
    var freq: f32 = 1.0;
    var norm: f32 = 0.0;
    let n: i32 = clamp(oct, 1, 8);
    for (var i: i32 = 0; i < 8; i = i + 1) {
        if (i >= n) { break; }
        let r: f32 = 1.0 - abs(2.0 * _vnoise(x * freq, y * freq, seed + f32(i) * 17.0) - 1.0);
        total = total + amp * r * r;
        norm = norm + amp;
        amp = amp * 0.5;
        freq = freq * 2.0;
    }
    return total / norm;
}
fn _turbulence(x: f32, y: f32, oct: i32, seed: f32) -> f32 {
    var total: f32 = 0.0;
    var amp: f32 = 0.5;
    var freq: f32 = 1.0;
    var norm: f32 = 0.0;
    let n: i32 = clamp(oct, 1, 8);
    for (var i: i32 = 0; i < 8; i = i + 1) {
        if (i >= n) { break; }
        let t: f32 = abs(2.0 * _vnoise(x * freq, y * freq, seed + f32(i) * 17.0) - 1.0);
        total = total + amp * t;
        norm = norm + amp;
        amp = amp * 0.5;
        freq = freq * 2.0;
    }
    return total / norm;
}
fn _voronoi(x: f32, y: f32, seed: f32) -> f32 {
    let ix: i32 = i32(floor(x));
    let iy: i32 = i32(floor(y));
    var best: f32 = 9.0;
    for (var dy: i32 = -1; dy <= 1; dy = dy + 1) {
        for (var dx: i32 = -1; dx <= 1; dx = dx + 1) {
            let cx: i32 = ix + dx;
            let cy: i32 = iy + dy;
            let px: f32 = f32(cx) + _hash_u32(cx, cy, seed + 1.3);
            let py: f32 = f32(cy) + _hash_u32(cx, cy, seed + 7.9);
            let dist: f32 = length(vec2<f32>(px - x, py - y));
            if (dist < best) { best = dist; }
        }
    }
    return best;
}
fn _rand(x: f32, y: f32, seed: f32) -> f32 {
    return _hash_u32(i32(floor(x)), i32(floor(y)), seed);
}
"""


def _init_device():
    """Lazily acquire a hardware WebGPU adapter/device (Vulkan / DirectX 12 / Metal)."""
    global _DEVICE, _ADAPTER_INFO, _CHECKED
    if _CHECKED:
        return _DEVICE
    with _LOCK:
        if _CHECKED:
            return _DEVICE
        _CHECKED = True
        try:
            import wgpu
            adapters = wgpu.gpu.enumerate_adapters_sync()
            chosen = None
            for a in adapters:
                inf = dict(a.info)
                if inf.get("adapter_type") in ("DiscreteGPU", "IntegratedGPU") and inf.get("backend_type") in ("Vulkan", "D3D12", "Metal"):
                    chosen = a
                    break
            if chosen is None:
                chosen = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
            if chosen is None:
                return None
            _DEVICE = chosen.request_device_sync()
            _ADAPTER_INFO = dict(chosen.info)
        except Exception:
            _DEVICE = None
            _ADAPTER_INFO = None
        return _DEVICE


def available() -> bool:
    return _init_device() is not None


def info() -> dict[str, Any]:
    dev = _init_device()
    if dev is None:
        return {"wgpu": False, "hint": 'install with pip install "uiforge-mcp[wgpu]" for cross-GPU Vulkan/DX12/Metal acceleration'}
    inf = _ADAPTER_INFO or {}
    return {"wgpu": True, "device": str(inf.get("device", "")), "backend_type": str(inf.get("backend_type", "")),
            "adapter_type": str(inf.get("adapter_type", "")), "vendor": str(inf.get("vendor", ""))}


def _wgsl_float(v: float) -> str:
    s = f"{float(v):.7g}"
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s


def compile_wgsl_shader(tree: ast.Module, param_names: tuple[str, ...], has_sdf: bool, want_height: bool) -> str | None:
    """Compile a validated shader AST into a single WGSL @compute shader."""
    known = {"x", "y", "u", "v", "w", "h", "px", "pi", "d", "edge"} | set(param_names)
    declared: set[str] = set(known)
    out_vars: set[str] = set()

    def _var(name: str) -> str:
        return f"v_{name}"

    def _emit_expr(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return _wgsl_float(float(node.value))
        if isinstance(node, ast.Name):
            if node.id not in known:
                return None
            return _var(node.id)
        if isinstance(node, ast.UnaryOp):
            op = _emit_expr(node.operand)
            if op is None:
                return None
            if isinstance(node.op, ast.UAdd):
                return f"({op})"
            if isinstance(node.op, ast.USub):
                return f"(-({op}))"
            return None
        if isinstance(node, ast.BinOp):
            l, r = _emit_expr(node.left), _emit_expr(node.right)
            if l is None or r is None:
                return None
            if isinstance(node.op, ast.Add):
                return f"({l} + {r})"
            if isinstance(node.op, ast.Sub):
                return f"({l} - {r})"
            if isinstance(node.op, ast.Mult):
                return f"({l} * {r})"
            if isinstance(node.op, ast.Div):
                return f"({l} / {r})"
            if isinstance(node.op, ast.FloorDiv):
                return f"floor({l} / {r})"
            if isinstance(node.op, ast.Mod):
                return f"_mod({l}, {r})"
            if isinstance(node.op, ast.Pow):
                return f"pow(max({l}, 0.0), {r})"
            return None
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            l, r = _emit_expr(node.left), _emit_expr(node.comparators[0])
            if l is None or r is None:
                return None
            sym = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}.get(type(node.ops[0]))
            return f"select(0.0, 1.0, ({l} {sym} {r}))" if sym else None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = node.func.id
            args = [_emit_expr(a) for a in node.args]
            if any(a is None for a in args):
                return None
            if fn in ("sin", "cos", "tan", "asin", "acos", "atan", "abs", "exp", "floor", "ceil", "round", "sign") and len(args) == 1:
                return f"{fn}({args[0]})"
            if fn == "sqrt" and len(args) == 1:
                return f"sqrt(max({args[0]}, 0.0))"
            if fn == "log" and len(args) == 1:
                return f"log(max({args[0]}, 1e-12))"
            if fn == "fract" and len(args) == 1:
                return f"_fract({args[0]})"
            if fn == "atan2" and len(args) == 2:
                return f"atan2({args[0]}, {args[1]})"
            if fn == "pow" and len(args) == 2:
                return f"pow(max({args[0]}, 0.0), {args[1]})"
            if fn in ("min", "max") and len(args) == 2:
                return f"{fn}({args[0]}, {args[1]})"
            if fn == "mod" and len(args) == 2:
                return f"_mod({args[0]}, {args[1]})"
            if fn == "step" and len(args) == 2:
                return f"_step({args[0]}, {args[1]})"
            if fn == "clamp":
                if len(args) == 1:
                    return f"_clamp01({args[0]})"
                if len(args) == 3:
                    return f"clamp({args[0]}, {args[1]}, {args[2]})"
            if fn == "mix" and len(args) == 3:
                return f"mix({args[0]}, {args[1]}, {args[2]})"
            if fn == "smoothstep" and len(args) == 3:
                return f"_smoothstep({args[0]}, {args[1]}, {args[2]})"
            if fn == "where" and len(args) == 3:
                return f"select({args[2]}, {args[1]}, ({args[0]}) != 0.0)"
            if fn in ("length", "hypot") and len(args) == 2:
                return f"sqrt(({args[0]}) * ({args[0]}) + ({args[1]}) * ({args[1]}))"
            if fn == "noise" and len(args) in (2, 3):
                return f"_vnoise({args[0]}, {args[1]}, {args[2] if len(args) == 3 else '0.0'})"
            if fn == "fbm" and len(args) in (2, 3, 4):
                oct_s = f"i32({args[2]})" if len(args) >= 3 else "5"
                seed_s = args[3] if len(args) == 4 else "0.0"
                return f"_fbm({args[0]}, {args[1]}, {oct_s}, {seed_s})"
            if fn == "ridged" and len(args) in (2, 3, 4):
                oct_s = f"i32({args[2]})" if len(args) >= 3 else "4"
                seed_s = args[3] if len(args) == 4 else "0.0"
                return f"_ridged({args[0]}, {args[1]}, {oct_s}, {seed_s})"
            if fn == "turbulence" and len(args) in (2, 3, 4):
                oct_s = f"i32({args[2]})" if len(args) >= 3 else "4"
                seed_s = args[3] if len(args) == 4 else "0.0"
                return f"_turbulence({args[0]}, {args[1]}, {oct_s}, {seed_s})"
            if fn == "voronoi" and len(args) in (2, 3):
                return f"_voronoi({args[0]}, {args[1]}, {args[2] if len(args) == 3 else '0.0'})"
            if fn == "rand" and len(args) in (2, 3):
                return f"_rand({args[0]}, {args[1]}, {args[2] if len(args) == 3 else '0.0'})"
        return None

    stmts: list[str] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return None
        name = stmt.targets[0].id
        expr = _emit_expr(stmt.value)
        if expr is None:
            return None
        if name not in declared:
            stmts.append(f"    var {_var(name)}: f32 = {expr};")
            declared.add(name)
        else:
            stmts.append(f"    {_var(name)} = {expr};")
        known.add(name)
        out_vars.add(name)

    if not {"r", "g", "b"} <= out_vars:
        return None

    param_loads = "\n".join(f"    var {_var(p)}: f32 = params[{idx}u];" for idx, p in enumerate(param_names))
    a_expr = _var("a") if "a" in out_vars else "1.0"
    h_expr = _var("height") if ("height" in out_vars and want_height) else "-1.0"
    d_load = "sdf_buf[idx]" if has_sdf else "min(min(v_x, v_w - v_x), min(v_y, v_h - v_y))"
    edge_load = "clamp(v_d / max(1.0, min(v_w, v_h) * 0.25), 0.0, 1.0)"
    wgsl = f"""
struct Uniforms {{
    width: u32,
    height: u32,
    x0: f32,
    y0: f32,
    bw: f32,
    bh: f32,
    k: f32,
    pad: f32,
}};
@group(0) @binding(0) var<uniform> uni: Uniforms;
@group(0) @binding(1) var<storage, read> params: array<f32>;
@group(0) @binding(2) var<storage, read> sdf_buf: array<f32>;
@group(0) @binding(3) var<storage, read_write> out_buf: array<vec4<f32>>;
@group(0) @binding(4) var<storage, read_write> h_buf: array<f32>;
{_WGSL_HELPERS}
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {{
    if (gid.x >= uni.width || gid.y >= uni.height) {{ return; }}
    let idx: u32 = gid.y * uni.width + gid.x;
    var v_x: f32 = (f32(gid.x) + 0.5 - uni.x0) / uni.k;
    var v_y: f32 = (f32(gid.y) + 0.5 - uni.y0) / uni.k;
    var v_w: f32 = uni.bw / uni.k;
    var v_h: f32 = uni.bh / uni.k;
    var v_u: f32 = (f32(gid.x) + 0.5 - uni.x0) / max(1e-6, uni.bw);
    var v_v: f32 = (f32(gid.y) + 0.5 - uni.y0) / max(1e-6, uni.bh);
    var v_px: f32 = uni.k;
    var v_pi: f32 = 3.141592653589793;
    var v_d: f32 = {d_load};
    var v_edge: f32 = {edge_load};
{param_loads}
{chr(10).join(stmts)}
    out_buf[idx] = vec4<f32>(clamp(v_r, 0.0, 1.0), clamp(v_g, 0.0, 1.0), clamp(v_b, 0.0, 1.0), clamp({a_expr}, 0.0, 1.0));
    h_buf[idx] = {h_expr};
}}
"""
    return wgsl


def eval_shader(tree: ast.Module, size: tuple[int, int], box_px: tuple[float, float, float, float], k: float,
                param_names: tuple[str, ...], param_vals: tuple[float, ...],
                sdf: np.ndarray | None = None, want_height: bool = False) -> tuple[np.ndarray, np.ndarray | None] | None:
    """Execute compiled WGSL shader on WebGPU hardware. Returns (rgba_uint8, height_f32 | None) or None on fallback."""
    dev = _init_device()
    if dev is None:
        return None
    has_sdf = sdf is not None
    wgsl = compile_wgsl_shader(tree, param_names, has_sdf, want_height)
    if wgsl is None:
        return None
    import wgpu
    w, h = size
    x0, y0, x1, y1 = box_px
    bw, bh = max(1e-6, float(x1 - x0)), max(1e-6, float(y1 - y0))
    n_pix = w * h

    with _LOCK:
        ckey = (wgsl, 1 if has_sdf else 0)
        cached = _PIPELINE_CACHE.get(ckey)
        if cached is None:
            bgl = dev.create_bind_group_layout(entries=[
                {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
                {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
                {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
                {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
                {"binding": 4, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
            ])
            playout = dev.create_pipeline_layout(bind_group_layouts=[bgl])
            mod = dev.create_shader_module(code=wgsl)
            pipe = dev.create_compute_pipeline(layout=playout, compute={"module": mod, "entry_point": "main"})
            if len(_PIPELINE_CACHE) > 96:
                _PIPELINE_CACHE.clear()
            _PIPELINE_CACHE[ckey] = (pipe, bgl)
        else:
            pipe, bgl = cached

        uni_bytes = struct.pack("IIffffff", w, h, float(x0), float(y0), bw, bh, float(k), 0.0)
        p_arr = np.asarray(param_vals if param_vals else (0.0,), dtype=np.float32)
        sdf_arr = np.ascontiguousarray(sdf.reshape(-1), dtype=np.float32) if has_sdf else np.zeros(1, dtype=np.float32)

        b_uni = dev.create_buffer_with_data(data=uni_bytes, usage=wgpu.BufferUsage.UNIFORM)
        b_par = dev.create_buffer_with_data(data=p_arr.tobytes(), usage=wgpu.BufferUsage.STORAGE)
        b_sdf = dev.create_buffer_with_data(data=sdf_arr.tobytes(), usage=wgpu.BufferUsage.STORAGE)
        out_nbytes = n_pix * 16
        h_nbytes = n_pix * 4
        b_out = dev.create_buffer(size=out_nbytes, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)
        b_h = dev.create_buffer(size=h_nbytes, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)

        bg = dev.create_bind_group(layout=bgl, entries=[
            {"binding": 0, "resource": {"buffer": b_uni}},
            {"binding": 1, "resource": {"buffer": b_par}},
            {"binding": 2, "resource": {"buffer": b_sdf}},
            {"binding": 3, "resource": {"buffer": b_out}},
            {"binding": 4, "resource": {"buffer": b_h}},
        ])
        enc = dev.create_command_encoder()
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups((w + 15) // 16, (h + 15) // 16, 1)
        cp.end()
        dev.queue.submit([enc.finish()])

        raw_out = np.frombuffer(dev.queue.read_buffer(b_out), dtype=np.float32).reshape(h, w, 4)
        rgba = np.clip(raw_out * np.float32(255.0), np.float32(0.0), np.float32(255.0)).copy()
        height_arr = None
        if want_height:
            raw_h = np.frombuffer(dev.queue.read_buffer(b_h), dtype=np.float32).reshape(h, w)
            if raw_h[0, 0] >= -0.5:
                height_arr = np.clip(raw_h.copy(), np.float32(0.0), np.float32(1.0))
        return rgba, height_arr


_WGSL_PBR = r"""
struct PbrParams {
    width: u32,
    height: u32,
    lx: f32, ly: f32, lz: f32,
    ior: f32,
    clearcoat: f32, cc_rough: f32,
    sss: f32, env_str: f32,
    env_cos: f32, env_sin: f32,
    exposure: f32, cam_fov: f32,
    aspect_k: f32, studio_id: u32,
};
@group(0) @binding(0) var<uniform> p: PbrParams;
@group(0) @binding(1) var<storage, read> albedo_in: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> norm_in: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read> mat_in: array<vec4<f32>>;
@group(0) @binding(4) var<storage, read> emis_in: array<vec4<f32>>;
@group(0) @binding(5) var<storage, read_write> rgba_out: array<vec4<f32>>;

fn smoothstep_f(e0: f32, e1: f32, x: f32) -> f32 {
    let t: f32 = clamp((x - e0) / max(1e-5, e1 - e0), 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}
fn aces(x: vec3<f32>) -> vec3<f32> {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), vec3<f32>(0.0), vec3<f32>(1.0));
}
fn lin_to_srgb(c: vec3<f32>) -> vec3<f32> {
    let cc = clamp(c, vec3<f32>(0.0), vec3<f32>(1.0));
    let lo = cc * 12.92;
    let hi = 1.055 * pow(cc, vec3<f32>(1.0 / 2.4)) - 0.055;
    return select(hi, lo, cc <= vec3<f32>(0.0031308));
}
fn softbox(x: f32, y: f32, cx: f32, cy: f32, hw: f32, hh: f32, blur: f32) -> f32 {
    let dx = abs(x - cx) - hw;
    let dy = abs(y - cy) - hh;
    let sd = length(max(vec2<f32>(dx, dy), vec2<f32>(0.0))) + min(max(dx, dy), 0.0);
    let edge = 0.11 + blur * 0.45;
    return (1.0 - smoothstep_f(-edge * 0.35, edge, sd)) / (1.0 + blur * 1.6);
}
fn studio_ibl(r: vec3<f32>, rough: f32) -> vec3<f32> {
    let rrx = r.x * p.env_cos - r.y * p.env_sin;
    let rry = r.x * p.env_sin + r.y * p.env_cos;
    let blur = clamp(rough * rough, 0.006, 0.95);
    let diag = rrx * 0.42 + rry * 0.91;
    let sky_t = smoothstep_f(-0.72, 0.58, -diag);
    var top_c = vec3<f32>(0.40, 0.45, 0.54);
    var bot_c = vec3<f32>(0.055, 0.062, 0.08);
    var key_c = vec3<f32>(3.3, 3.25, 3.15);
    var fill_c = vec3<f32>(1.25, 1.42, 1.72);
    var rim_c = vec3<f32>(1.08, 1.35, 1.82);
    if (p.studio_id == 1u) {
        top_c = vec3<f32>(0.52, 0.41, 0.28); bot_c = vec3<f32>(0.07, 0.045, 0.025);
        key_c = vec3<f32>(3.3, 2.75, 1.98); fill_c = vec3<f32>(1.45, 1.18, 0.88); rim_c = vec3<f32>(1.15, 0.96, 0.82);
    } else if (p.studio_id == 2u) {
        top_c = vec3<f32>(0.26, 0.30, 0.38); bot_c = vec3<f32>(0.025, 0.028, 0.038);
        key_c = vec3<f32>(3.0, 3.1, 3.2); fill_c = vec3<f32>(1.05, 1.28, 1.65); rim_c = vec3<f32>(0.95, 1.22, 1.75);
    } else if (p.studio_id == 3u) {
        top_c = vec3<f32>(0.62, 0.36, 0.30); bot_c = vec3<f32>(0.06, 0.05, 0.09);
        key_c = vec3<f32>(3.8, 2.35, 1.35); fill_c = vec3<f32>(1.1, 1.35, 2.1); rim_c = vec3<f32>(1.8, 1.0, 1.3);
    } else if (p.studio_id == 4u) {
        top_c = vec3<f32>(0.16, 0.28, 0.45); bot_c = vec3<f32>(0.08, 0.02, 0.10);
        key_c = vec3<f32>(1.3, 3.4, 3.8); fill_c = vec3<f32>(3.4, 0.8, 2.6); rim_c = vec3<f32>(2.8, 1.2, 3.2);
    }
    var base = mix(bot_c, top_c, sky_t);
    let nw = 0.11 + blur * 0.36;
    let nf1 = exp(-((diag - 0.12) * (diag - 0.12)) / (nw * nw * 2.4));
    let nf2 = exp(-((rry - 0.46) * (rry - 0.46)) / (nw * nw * 3.2));
    base = base * (1.0 - clamp(nf1 * 0.72 + nf2 * 0.48, 0.0, 0.80));
    let sb_key = softbox(rrx, rry, -0.22, -0.56, 0.78, 0.22, blur);
    let sb_strip = exp(-((diag + 0.36) * (diag + 0.36)) / (0.018 + blur * 0.18)) / (1.0 + blur * 2.0) * 0.92;
    let sb_rim = softbox(rrx, rry, 0.30, 0.64, 0.74, 0.18, blur) * 0.95;
    let sb_fill = exp(-((rrx + 0.68) * (rrx + 0.68)) / (0.08 + blur * 0.35)) * 0.55;
    return base + sb_key * key_c + sb_strip * key_c * 0.62 + sb_fill * fill_c + sb_rim * rim_c;
}
fn ggx_direct(N: vec3<f32>, V: vec3<f32>, L: vec3<f32>, rad: vec3<f32>, alb: vec3<f32>, f0: vec3<f32>, met: f32, rough: f32, sss: f32) -> vec3<f32> {
    let H = normalize(L + V);
    let ndv = max(dot(N, V), 1e-4);
    let ndl_raw = dot(N, L);
    let ndl = clamp(ndl_raw, 0.0, 1.0);
    let ndh = clamp(dot(N, H), 0.0, 1.0);
    let vdh = clamp(dot(V, H), 0.0, 1.0);
    let alpha = max(0.003, rough * rough);
    let a2 = alpha * alpha;
    let d_den = ndh * ndh * (a2 - 1.0) + 1.0;
    let D_main = a2 / (3.14159265 * d_den * d_den + 1e-5);
    let aw = min(0.85, alpha * 2.6 + 0.08);
    let aw2 = aw * aw;
    let dw_den = ndh * ndh * (aw2 - 1.0) + 1.0;
    let D = D_main * 0.84 + (aw2 / (3.14159265 * dw_den * dw_den + 1e-5)) * 0.16;
    let gl = ndv * sqrt((-ndl * a2 + ndl) * ndl + a2 + 1e-5);
    let gv = ndl * sqrt((-ndv * a2 + ndv) * ndv + a2 + 1e-5);
    let vis = 0.5 / (gv + gl + 1e-5);
    let fres = f0 + (vec3<f32>(1.0) - f0) * pow(1.0 - vdh, 5.0);
    let spec = (D * vis) * fres;
    let diff = (vec3<f32>(1.0) - fres) * (1.0 - met) * alb * 0.31830989;
    var out = (diff + spec) * ndl * rad;
    if (sss > 0.0) {
        let wrap = clamp((ndl_raw + 0.55) / 1.55, 0.0, 1.0);
        out = out + (1.0 - met) * alb * (wrap * wrap * sss * 0.36) * rad;
    }
    return out;
}
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    if (gid.x >= p.width || gid.y >= p.height) { return; }
    let idx = gid.y * p.width + gid.x;
    let alb4 = albedo_in[idx];
    let alb = alb4.xyz;
    let N = normalize(norm_in[idx].xyz);
    let mp = mat_in[idx];
    let rough = mp.x;
    let met = mp.y;
    let ao = mp.z;
    let xs = (f32(gid.x) / max(1.0, f32(p.width - 1u))) * 2.0 - 1.0;
    let ys = (f32(gid.y) / max(1.0, f32(p.height - 1u))) * 2.0 - 1.0;
    let V = normalize(vec3<f32>(-xs * p.cam_fov * p.aspect_k, -ys * p.cam_fov, 1.0));
    let f0_d = ((p.ior - 1.0) / (p.ior + 1.0)) * ((p.ior - 1.0) / (p.ior + 1.0));
    let f0 = mix(vec3<f32>(f0_d), alb, met);
    let L1 = vec3<f32>(p.lx, p.ly, p.lz);
    let L2 = normalize(vec3<f32>(-p.lx * 0.85, -p.ly * 0.85, 0.42));
    var col = ggx_direct(N, V, L1, vec3<f32>(2.25, 2.15, 2.0), alb, f0, met, rough, p.sss);
    col = col + ggx_direct(N, V, L2, vec3<f32>(0.72, 0.88, 1.15), alb, f0, met, rough, p.sss * 0.45);
    let ndv = max(dot(N, V), 1e-4);
    let R = 2.0 * ndv * N - V;
    if (p.env_str > 0.0) {
        let env_s = studio_ibl(R, rough);
        let f_ibl = f0 + (max(vec3<f32>(1.0 - rough), f0) - f0) * pow(1.0 - ndv, 5.0);
        let spec_i = env_s * f_ibl * (0.88 + 0.32 * met);
        let diff_i = (vec3<f32>(1.0) - f_ibl) * (1.0 - met) * alb * vec3<f32>(0.36, 0.38, 0.43);
        col = col + (spec_i + diff_i) * p.env_str * ao;
    }
    if (p.clearcoat > 0.01) {
        let cc_d = ggx_direct(N, V, L1, vec3<f32>(2.25, 2.15, 2.0), vec3<f32>(0.0), vec3<f32>(0.045), 0.0, p.cc_rough, 0.0);
        let cc_e = studio_ibl(R, p.cc_rough);
        let cc_f = 0.045 + 0.955 * pow(1.0 - ndv, 5.0);
        col = col + (cc_d + cc_e * cc_f * 0.75) * p.clearcoat;
    }
    col = col + emis_in[idx].xyz;
    let srgb = lin_to_srgb(aces(col * p.exposure));
    rgba_out[idx] = vec4<f32>(srgb, alb4.w);
}
"""


def shade_pbr_wgpu(fields: dict[str, Any], spec: dict[str, Any]) -> np.ndarray | None:
    """Execute Cook-Torrance GGX PBR + Studio IBL + ACES Filmic in WGSL compute on WebGPU hardware."""
    dev = _init_device()
    if dev is None:
        return None
    import wgpu
    alb = fields["albedo_lin"]
    h, w = alb.shape[:2]
    n_pix = w * h
    studio_map = {"bright": 0, "warm": 1, "dark": 2, "sunset": 3, "cyberpunk": 4}
    studio_id = studio_map.get(str(spec.get("studio", "bright")).lower(), 0)
    key_ang = math.radians(float(spec.get("angle", 225.0)))
    key_alt = math.radians(max(10.0, min(80.0, float(spec.get("altitude", 46.0)))))
    lx = math.cos(key_ang) * math.cos(key_alt)
    ly = math.sin(key_ang) * math.cos(key_alt)
    lz = math.sin(key_alt)
    env_rot = math.radians(float(spec.get("env_rotation", 0.0)))
    aspect = float(w) / max(1.0, float(h))
    aspect_k = min(1.35, max(0.75, aspect * 0.65))

    alb4 = np.empty((h, w, 4), dtype=np.float32)
    alb4[..., :3] = alb
    alb4[..., 3] = fields["fill_a"]
    norm4 = np.zeros((h, w, 4), dtype=np.float32)
    norm4[..., 0], norm4[..., 1], norm4[..., 2] = fields["nx"], fields["ny"], fields["nz"]
    mat4 = np.zeros((h, w, 4), dtype=np.float32)
    mat4[..., 0], mat4[..., 1], mat4[..., 2] = fields["rough"], fields["metallic"], fields["ao"]
    emis4 = np.zeros((h, w, 4), dtype=np.float32)
    emis4[..., :3] = fields["emissive_lin"]

    with _LOCK:
        ckey = ("_pbr_wgsl_", 0)
        cached = _PIPELINE_CACHE.get(ckey)
        if cached is None:
            bgl = dev.create_bind_group_layout(entries=[
                {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.uniform}},
                {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
                {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
                {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
                {"binding": 4, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
                {"binding": 5, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}},
            ])
            playout = dev.create_pipeline_layout(bind_group_layouts=[bgl])
            mod = dev.create_shader_module(code=_WGSL_PBR)
            pipe = dev.create_compute_pipeline(layout=playout, compute={"module": mod, "entry_point": "main"})
            _PIPELINE_CACHE[ckey] = (pipe, bgl)
        else:
            pipe, bgl = cached

        ubytes = struct.pack(
            "IIfffffffffffffI", w, h, lx, ly, lz,
            max(1.1, float(spec.get("ior", 1.5))),
            max(0.0, min(1.0, float(spec.get("clearcoat", 0.0)))),
            max(0.03, min(0.5, float(spec.get("clearcoat_roughness", 0.06)))),
            max(0.0, min(1.0, float(spec.get("sss", 0.0)))),
            float(spec.get("env", 1.0)),
            math.cos(env_rot), math.sin(env_rot),
            float(spec.get("exposure", 1.02)),
            float(spec.get("fov", 0.42)),
            aspect_k, studio_id,
        )
        b_u = dev.create_buffer_with_data(data=ubytes, usage=wgpu.BufferUsage.UNIFORM)
        b_a = dev.create_buffer_with_data(data=alb4.tobytes(), usage=wgpu.BufferUsage.STORAGE)
        b_n = dev.create_buffer_with_data(data=norm4.tobytes(), usage=wgpu.BufferUsage.STORAGE)
        b_m = dev.create_buffer_with_data(data=mat4.tobytes(), usage=wgpu.BufferUsage.STORAGE)
        b_e = dev.create_buffer_with_data(data=emis4.tobytes(), usage=wgpu.BufferUsage.STORAGE)
        b_out = dev.create_buffer(size=n_pix * 16, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)

        bg = dev.create_bind_group(layout=bgl, entries=[
            {"binding": 0, "resource": {"buffer": b_u}},
            {"binding": 1, "resource": {"buffer": b_a}},
            {"binding": 2, "resource": {"buffer": b_n}},
            {"binding": 3, "resource": {"buffer": b_m}},
            {"binding": 4, "resource": {"buffer": b_e}},
            {"binding": 5, "resource": {"buffer": b_out}},
        ])
        enc = dev.create_command_encoder()
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups((w + 15) // 16, (h + 15) // 16, 1)
        cp.end()
        dev.queue.submit([enc.finish()])
        raw = np.frombuffer(dev.queue.read_buffer(b_out), dtype=np.float32).reshape(h, w, 4)
        return np.clip(raw * np.float32(255.0) + np.float32(0.5), 0, 255).astype(np.uint8)
