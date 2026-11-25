"""CLI commands for hardware GPU auto-detection, architecture-aware GPU installation, diagnostics,
Streamable HTTP transport (ChatGPT/remote MCP) and zero-friction multi-IDE MCP configuration.

Commands:
  game-ui-mcp                              Start MCP stdio server (default)
  game-ui-mcp serve --transport http       Start MCP Streamable HTTP server (ChatGPT / remote clients)
  game-ui-mcp doctor                       Inspect GPU, backends, installed engines/IDEs and fallbacks
  game-ui-mcp install-gpu [--arch auto]    Recommend or install the optimal GPU extra for this machine
  game-ui-mcp setup <client> [--write]     Generate or install MCP config for OpenCode, Claude Code,
                                           VS Code, Visual Studio, Antigravity, Cursor, Windsurf, ChatGPT
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import gpu

GPU_ARCH_PACKAGES: dict[str, dict[str, Any]] = {
    "nvidia": {
        "extra": "nvidia",
        "packages": ["cupy-cuda12x[ctk]>=13.4", "wgpu>=0.19"],
        "backend": "cuda (+ wgpu Vulkan/D3D12 fallback)",
        "notes": "Fused CUDA 12 kernels + WebGPU PBR/shader compute. Falls back automatically to WebGPU or CPU.",
    },
    "amd": {
        "extra": "amd",
        "packages": ["wgpu>=0.19"],
        "backend": "wgpu (Vulkan / D3D12)",
        "notes": "Uses shared portable WebGPU WGSL runtime via wgpu-py. No proprietary ROCm install required.",
    },
    "intel": {
        "extra": "intel",
        "packages": ["wgpu>=0.19"],
        "backend": "wgpu (Vulkan / D3D12)",
        "notes": "Uses shared portable WebGPU WGSL runtime via wgpu-py for Intel Arc and integrated Xe GPUs.",
    },
    "apple": {
        "extra": "apple",
        "packages": ["wgpu>=0.19"],
        "backend": "wgpu (Metal)",
        "notes": "Uses shared portable WebGPU WGSL runtime targeting Apple Silicon Metal via wgpu-py.",
    },
    "cpu": {
        "extra": "cpu",
        "packages": [],
        "backend": "cpu (OpenCV C++ SIMD + NumPy)",
        "notes": "Zero GPU dependencies; fully deterministic OpenCV SIMD + NumPy rendering.",
    },
}

CLIENTS = ("opencode", "claude", "vscode", "visualstudio", "antigravity", "cursor", "windsurf", "chatgpt")


def detect_gpu_hardware() -> dict[str, Any]:
    """Detect system GPU adapters and recommend the right architecture extra ('nvidia'|'amd'|'intel'|'apple'|'cpu')."""
    sys_name = platform.system()
    machine = platform.machine().lower()
    adapters: list[str] = []

    if sys_name == "Darwin" and ("arm" in machine or "aarch64" in machine):
        adapters.append("Apple Silicon (Metal)")
    elif sys_name == "Windows":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController).Name"],
                stderr=subprocess.DEVNULL, timeout=5, text=True,
            )
            adapters = [ln.strip() for ln in out.splitlines() if ln.strip()]
        except Exception:
            pass
    elif sys_name == "Linux":
        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    stderr=subprocess.DEVNULL, timeout=4, text=True,
                )
                adapters += [ln.strip() for ln in out.splitlines() if ln.strip()]
            except Exception:
                pass
        if shutil.which("lspci"):
            try:
                out = subprocess.check_output(["lspci"], stderr=subprocess.DEVNULL, timeout=4, text=True)
                for ln in out.splitlines():
                    if "VGA" in ln or "3D controller" in ln:
                        adapters.append(ln.split(":", 2)[-1].strip())
            except Exception:
                pass

    low = " ".join(adapters).lower()
    if "nvidia" in low or "geforce" in low or "rtx" in low or "quadro" in low or "tesla" in low:
        arch = "nvidia"
    elif "apple" in low or (sys_name == "Darwin" and ("arm" in machine or "aarch64" in machine)):
        arch = "apple"
    elif "amd" in low or "radeon" in low or "rx " in low:
        arch = "amd"
    elif "intel" in low or "arc " in low or "iris" in low or "uhd graphics" in low:
        arch = "intel"
    else:
        arch = "cpu"

    return {
        "os": f"{sys_name} {platform.release()} ({platform.machine()})",
        "adapters": adapters,
        "recommended_arch": arch,
        "recommended_extra": GPU_ARCH_PACKAGES[arch]["extra"],
        "packages": GPU_ARCH_PACKAGES[arch]["packages"],
        "notes": GPU_ARCH_PACKAGES[arch]["notes"],
    }


def doctor_report() -> dict[str, Any]:
    """Return full diagnostic report of GPU hardware, active backends, fallback status and local tools."""
    hw = detect_gpu_hardware()
    ginfo = gpu.info()
    tools_found = {
        name: shutil.which(name)
        for name in ("uv", "uvx", "dotnet", "node", "npm", "tsc", "ffmpeg", "git", "code", "opencode", "claude")
    }
    active = ginfo.get("backend", "cpu")
    fallback_notice = None
    if active == "cpu" and hw["recommended_arch"] != "cpu":
        extra = hw["recommended_extra"]
        fallback_notice = (
            f"Hardware GPU detected ({hw['recommended_arch'].upper()}), currently running on CPU fallback. "
            f'Install acceleration with: pip install "game-ui-mcp[{extra}]" or game-ui-mcp install-gpu --apply'
        )
    return {
        "python": sys.version.split()[0],
        "hardware": hw,
        "gpu_runtime": ginfo,
        "active_backend": active,
        "fallback_notice": fallback_notice,
        "local_tools": {k: v for k, v in tools_found.items() if v},
    }


def install_gpu_plan(arch: str = "auto", repo_url: str = "git+https://github.com/TENETTE/game-ui-mcp") -> dict[str, Any]:
    """Build exact architecture-appropriate install plan (uv & pip commands) without duplicating packages."""
    chosen = str(arch or "auto").strip().lower()
    hw = detect_gpu_hardware()
    if chosen == "auto":
        chosen = hw["recommended_arch"]
    if chosen not in GPU_ARCH_PACKAGES:
        raise ValueError(f"arch must be one of auto, {', '.join(GPU_ARCH_PACKAGES)}")
    spec = GPU_ARCH_PACKAGES[chosen]
    extra = spec["extra"]
    pkgs = spec["packages"]
    pip_cmd = [sys.executable, "-m", "pip", "install", *pkgs] if pkgs else []
    uv_cmd = f'uvx --from "game-ui-mcp[{extra}] @ {repo_url}" game-ui-mcp' if extra != "cpu" else f"uvx --from {repo_url} game-ui-mcp"
    return {
        "detected_arch": hw["recommended_arch"],
        "selected_arch": chosen,
        "extra": extra,
        "backend": spec["backend"],
        "packages": pkgs,
        "pip_command": " ".join(pip_cmd) if pip_cmd else "(no extra packages needed for CPU)",
        "uvx_command": uv_cmd,
        "notes": spec["notes"],
    }


def _launch_command(server_name: str, extra: str | None, repo_url: str, local_python: bool = False) -> tuple[str, list[str]]:
    if local_python:
        return sys.executable, ["-m", "game_ui_mcp.server"]
    src = f"game-ui-mcp[{extra}] @ {repo_url}" if (extra and extra != "cpu") else repo_url
    return "uvx", ["--from", src, "game-ui-mcp"]


def client_config(client: str, scope: str = "user", gpu_arch: str = "auto",
                  server_name: str = "game-ui", repo_url: str = "git+https://github.com/TENETTE/game-ui-mcp",
                  local_python: bool = False, http_port: int = 8765) -> dict[str, Any]:
    """Generate official 2026 MCP configuration JSON, target path and CLI command for an AI IDE/client."""
    c = str(client).strip().lower()
    if c not in CLIENTS:
        raise ValueError(f"client must be one of {', '.join(CLIENTS)}")
    plan = install_gpu_plan(gpu_arch, repo_url=repo_url)
    extra = plan["extra"]
    cmd, args = _launch_command(server_name, extra, repo_url, local_python=local_python)
    home = Path.home()
    cwd = Path.cwd()

    if c == "opencode":
        cfg_path = (cwd / "opencode.json") if scope == "project" else (home / ".config" / "opencode" / "opencode.json")
        cfg = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "servers": {
                    server_name: {
                        "type": "local",
                        "command": [cmd, *args],
                        "environment": {"GAME_UI_MCP_GPU": "auto"},
                    }
                }
            },
        }
        cli_cmd = f"opencode mcp add {server_name} -- {cmd} " + " ".join(args)
        return {"client": c, "path": str(cfg_path), "config": cfg, "cli_command": cli_cmd,
                "notes": "OpenCode v2 uses mcp.servers.<name> with type='local'."}

    if c == "claude":
        cfg_path = (cwd / ".mcp.json") if scope == "project" else (home / ".claude.json")
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"GAME_UI_MCP_GPU": "auto"}}}}
        cli_cmd = f"claude mcp add {server_name} -s {scope} -- {cmd} " + " ".join(args)
        return {"client": c, "path": str(cfg_path), "config": cfg, "cli_command": cli_cmd,
                "notes": "Also copy skill/game-ui-mcp/ into ~/.claude/skills/ for full AI craft guidance."}

    if c == "vscode":
        cfg_path = (cwd / ".mcp.json") if scope == "project" else (home / ".mcp.json")
        cfg = {
            "mcpServers": {
                server_name: {
                    "type": "stdio",
                    "command": cmd,
                    "args": args,
                    "env": {"GAME_UI_MCP_GPU": "auto"},
                }
            }
        }
        legacy_cfg = {"servers": {server_name: {"type": "stdio", "command": cmd, "args": args}}}
        return {"client": c, "path": str(cfg_path), "config": cfg, "legacy_vscode_mcp_json": legacy_cfg,
                "notes": "VS Code 2026 Copilot reads workspace-root .mcp.json (mcpServers); legacy .vscode/mcp.json uses servers."}

    if c == "visualstudio":
        cfg_path = (cwd / ".mcp.json") if scope == "project" else (home / ".mcp.json")
        cfg = {
            "servers": {
                server_name: {
                    "type": "stdio",
                    "command": cmd,
                    "args": args,
                    "env": {"GAME_UI_MCP_GPU": "auto"},
                }
            }
        }
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Visual Studio 2022 17.14+ and Visual Studio 2026 auto-discover %USERPROFILE%\\.mcp.json and <repo>\\.mcp.json."}

    if c == "antigravity":
        cfg_path = home / ".gemini" / "antigravity" / "mcp_config.json"
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"GAME_UI_MCP_GPU": "auto"}}}}
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Google Antigravity loads MCP servers from ~/.gemini/antigravity/mcp_config.json and skills from ~/.gemini/config/skills/."}

    if c == "cursor":
        cfg_path = (cwd / ".cursor" / "mcp.json") if scope == "project" else (home / ".cursor" / "mcp.json")
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"GAME_UI_MCP_GPU": "auto"}}}}
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Cursor reads ~/.cursor/mcp.json (global) or .cursor/mcp.json (project)."}

    if c == "windsurf":
        cfg_path = home / ".codeium" / "windsurf" / "mcp_config.json"
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"GAME_UI_MCP_GPU": "auto"}}}}
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Windsurf reads ~/.codeium/windsurf/mcp_config.json."}

    return {
        "client": "chatgpt",
        "transport": "streamable-http",
        "start_command": f"game-ui-mcp serve --transport http --host 127.0.0.1 --port {http_port}",
        "endpoint_url": f"http://127.0.0.1:{http_port}/mcp",
        "config": {"name": server_name, "transport": "streamable-http", "url": f"http://127.0.0.1:{http_port}/mcp"},
        "notes": "ChatGPT Apps/Connectors require an HTTPS Streamable HTTP MCP URL. Run the local HTTP server and expose it via your own HTTPS tunnel (e.g. cloudflared/ngrok) when connecting from ChatGPT Web.",
    }


def write_client_config(spec: dict[str, Any]) -> Path:
    """Safely merge generated MCP server entry into an existing IDE JSON config file without clobbering other servers."""
    if not spec.get("path"):
        raise ValueError(f"client '{spec.get('client')}' uses HTTP setup and has no local JSON config file")
    path = Path(spec["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    def _deep_merge(dst: dict, src: dict) -> dict:
        out = dict(dst)
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = _deep_merge(out[k], v)
            else:
                out[k] = v
        return out

    merged = _deep_merge(existing, spec["config"])
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def cli_main(argv: list[str] | None = None) -> None:
    """Entry point for game-ui-mcp: runs MCP stdio server by default or dispatches CLI utilities."""
    args_list = sys.argv[1:] if argv is None else list(argv)
    if not args_list:
        from .server import mcp
        mcp.run()
        return

    parser = argparse.ArgumentParser(prog="game-ui-mcp", description="Local deterministic UI design, PBR & multi-engine MCP server.")
    sub = parser.add_subparsers(dest="cmd")

    p_srv = sub.add_parser("serve", help="Run the MCP server (stdio or Streamable HTTP for ChatGPT/remote clients).")
    p_srv.add_argument("--transport", choices=("stdio", "http", "streamable-http", "sse"), default="stdio")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8765)

    sub.add_parser("doctor", help="Diagnose GPU hardware, active backends, fallbacks and local engines/IDEs.")

    p_gpu = sub.add_parser("install-gpu", help="Auto-detect GPU architecture and print or install the optimal extra.")
    p_gpu.add_argument("--arch", choices=("auto", "nvidia", "amd", "intel", "apple", "cpu"), default="auto")
    p_gpu.add_argument("--apply", action="store_true", help="Actually invoke pip install for the selected GPU extra.")

    p_set = sub.add_parser("setup", help="Generate or write MCP config for OpenCode, Claude Code, VS Code, Visual Studio, Antigravity, Cursor, Windsurf or ChatGPT.")
    p_set.add_argument("client", choices=(*CLIENTS, "all"))
    p_set.add_argument("--scope", choices=("user", "project"), default="user")
    p_set.add_argument("--gpu", choices=("auto", "nvidia", "amd", "intel", "apple", "cpu"), default="auto")
    p_set.add_argument("--name", default="game-ui")
    p_set.add_argument("--local-python", action="store_true")
    p_set.add_argument("--port", type=int, default=8765)
    p_set.add_argument("--write", action="store_true", help="Write/merge directly into the IDE config file.")

    ns = parser.parse_args(args_list)
    if ns.cmd == "serve":
        from .server import mcp
        tr = "streamable-http" if ns.transport == "http" else ns.transport
        if tr == "stdio":
            mcp.run()
        else:
            if hasattr(mcp, "settings"):
                mcp.settings.host = ns.host
                mcp.settings.port = ns.port
            mcp.run(transport=tr)
    elif ns.cmd == "doctor":
        print(json.dumps(doctor_report(), indent=2, ensure_ascii=False))
    elif ns.cmd == "install-gpu":
        plan = install_gpu_plan(ns.arch)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        if ns.apply and plan["packages"]:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *plan["packages"]])
    elif ns.cmd == "setup":
        targets = CLIENTS if ns.client == "all" else (ns.client,)
        results = []
        for cl in targets:
            spec = client_config(cl, scope=ns.scope, gpu_arch=ns.gpu, server_name=ns.name,
                                 local_python=ns.local_python, http_port=ns.port)
            if ns.write and spec.get("path"):
                written = write_client_config(spec)
                spec["written"] = str(written)
            results.append(spec)
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False))
    else:
        from .server import mcp
        mcp.run()
