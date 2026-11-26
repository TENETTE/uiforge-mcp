"""CLI commands for hardware GPU auto-detection, architecture-aware GPU installation, diagnostics,
Streamable HTTP transport (ChatGPT/remote MCP) and zero-friction multi-IDE MCP configuration.

Commands:
  uiforge-mcp                              Start MCP stdio server (default)
  uiforge-mcp serve --transport http       Start MCP Streamable HTTP server (ChatGPT / remote clients)
  uiforge-mcp doctor                       Inspect GPU, backends, installed engines/IDEs and fallbacks
  uiforge-mcp install-gpu [--arch auto]    Recommend or install the optimal GPU extra for this machine
  uiforge-mcp setup <client> [--write]     Generate or install MCP config for OpenCode, Claude Code,
                                           VS Code, Visual Studio, Antigravity, Cursor, Windsurf, ChatGPT
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__, gpu

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

CLIENTS = ("opencode", "claude", "codex", "vscode", "visualstudio", "antigravity", "cursor", "windsurf", "chatgpt")


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
            f'Install acceleration with: pip install "uiforge-mcp[{extra}]" or uiforge-mcp install-gpu --apply'
        )
    return {
        "python": sys.version.split()[0],
        "hardware": hw,
        "gpu_runtime": ginfo,
        "active_backend": active,
        "fallback_notice": fallback_notice,
        "local_tools": {k: v for k, v in tools_found.items() if v},
    }


def install_gpu_plan(arch: str = "auto", repo_url: str | None = None) -> dict[str, Any]:
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
    if repo_url:
        uv_cmd = f'uvx --from "uiforge-mcp[{extra}] @ {repo_url}" uiforge-mcp' if extra != "cpu" else f"uvx --from {repo_url} uiforge-mcp"
    else:
        uv_cmd = f'uvx --from "uiforge-mcp[{extra}]" uiforge-mcp' if extra != "cpu" else "uvx uiforge-mcp"
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


def _launch_command(server_name: str, extra: str | None, repo_url: str | None, local_python: bool = False) -> tuple[str, list[str]]:
    if local_python:
        return sys.executable, ["-m", "uiforge_mcp.server"]
    if repo_url:
        src = f"uiforge-mcp[{extra}] @ {repo_url}" if (extra and extra != "cpu") else repo_url
        return "uvx", ["--from", src, "uiforge-mcp"]
    if extra and extra != "cpu":
        return "uvx", ["--from", f"uiforge-mcp[{extra}]", "uiforge-mcp"]
    return "uvx", ["uiforge-mcp"]


def client_config(client: str, scope: str = "user", gpu_arch: str = "auto",
                  server_name: str = "uiforge", repo_url: str | None = None,
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
                        "environment": {"UIFORGE_MCP_GPU": "auto"},
                    }
                }
            },
        }
        cli_cmd = f"opencode mcp add {server_name} -- {cmd} " + " ".join(args)
        return {"client": c, "path": str(cfg_path), "config": cfg, "cli_command": cli_cmd,
                "notes": "OpenCode v2 uses mcp.servers.<name> with type='local'."}

    if c == "claude":
        cfg_path = (cwd / ".mcp.json") if scope == "project" else (home / ".claude.json")
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"UIFORGE_MCP_GPU": "auto"}}}}
        cli_cmd = f"claude mcp add {server_name} -s {scope} -- {cmd} " + " ".join(args)
        return {"client": c, "path": str(cfg_path), "config": cfg, "cli_command": cli_cmd,
                "notes": "Copy skill/uiforge-mcp/ into ~/.claude/skills/ for full AI craft guidance."}

    if c == "codex":
        cfg_path = home / ".codex" / "config.toml"
        toml_snippet = (
            f"[mcp_servers.{server_name}]\n"
            f'command = {json.dumps(cmd)}\n'
            f"args = {json.dumps(args)}\n"
        )
        return {"client": c, "path": str(cfg_path), "format": "toml", "toml": toml_snippet,
                "config": {"mcp_servers": {server_name: {"command": cmd, "args": args}}},
                "notes": "OpenAI Codex CLI reads ~/.codex/config.toml under [mcp_servers.<name>]."}

    if c == "vscode":
        cfg_path = (cwd / ".mcp.json") if scope == "project" else (home / ".mcp.json")
        cfg = {
            "mcpServers": {
                server_name: {
                    "type": "stdio",
                    "command": cmd,
                    "args": args,
                    "env": {"UIFORGE_MCP_GPU": "auto"},
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
                    "env": {"UIFORGE_MCP_GPU": "auto"},
                }
            }
        }
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Visual Studio 2022 17.14+ and Visual Studio 2026 auto-discover %USERPROFILE%\\.mcp.json and <repo>\\.mcp.json."}

    if c == "antigravity":
        cfg_path = home / ".gemini" / "antigravity" / "mcp_config.json"
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"UIFORGE_MCP_GPU": "auto"}}}}
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Google Antigravity loads MCP servers from ~/.gemini/antigravity/mcp_config.json and skills from ~/.gemini/config/skills/."}

    if c == "cursor":
        cfg_path = (cwd / ".cursor" / "mcp.json") if scope == "project" else (home / ".cursor" / "mcp.json")
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"UIFORGE_MCP_GPU": "auto"}}}}
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Cursor reads ~/.cursor/mcp.json (global) or .cursor/mcp.json (project)."}

    if c == "windsurf":
        cfg_path = home / ".codeium" / "windsurf" / "mcp_config.json"
        cfg = {"mcpServers": {server_name: {"command": cmd, "args": args, "env": {"UIFORGE_MCP_GPU": "auto"}}}}
        return {"client": c, "path": str(cfg_path), "config": cfg,
                "notes": "Windsurf reads ~/.codeium/windsurf/mcp_config.json."}

    return {
        "client": "chatgpt",
        "transport": "streamable-http",
        "start_command": f"uiforge-mcp serve --transport http --host 127.0.0.1 --port {http_port}",
        "endpoint_url": f"http://127.0.0.1:{http_port}/mcp",
        "config": {"name": server_name, "transport": "streamable-http", "url": f"http://127.0.0.1:{http_port}/mcp"},
        "notes": "ChatGPT Apps/Connectors require an HTTPS Streamable HTTP MCP URL. Run the local HTTP server and expose it via your own HTTPS tunnel (e.g. cloudflared/ngrok) when connecting from ChatGPT Web.",
    }


def write_client_config(spec: dict[str, Any]) -> Path:
    """Safely merge generated MCP server entry into an existing IDE JSON/TOML config without clobbering other servers."""
    if not spec.get("path"):
        raise ValueError(f"client '{spec.get('client')}' uses HTTP setup and has no local config file")
    path = Path(spec["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if spec.get("format") == "toml" and spec.get("toml"):
        existing_txt = path.read_text(encoding="utf-8") if path.is_file() else ""
        header = spec["toml"].splitlines()[0].strip()
        if header not in existing_txt:
            sep = "\n\n" if existing_txt.strip() else ""
            path.write_text(existing_txt.rstrip() + sep + spec["toml"], encoding="utf-8")
        return path
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
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


class BearerAuthMiddleware:
    """Constant-time Bearer token ASGI middleware for remote Streamable HTTP / SSE MCP servers."""

    def __init__(self, app, token: str):
        self.app = app
        self._expected = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method", "").upper() == "OPTIONS":
            await self.app(scope, receive, send)
            return
        auth = b""
        for k, v in scope.get("headers") or ():
            if k.lower() == b"authorization":
                auth = v
                break
        if not hmac.compare_digest(auth, self._expected):
            body = b'{"error":"unauthorized","detail":"Valid Authorization: Bearer <token> header required"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="uiforge-mcp"'),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def build_http_app(host: str = "127.0.0.1", auth_token: str | None = None):
    """Build the Streamable HTTP ASGI app, optionally wrapped in constant-time Bearer token auth."""
    from .server import mcp
    app = mcp.streamable_http_app(host=host)
    if auth_token:
        app = BearerAuthMiddleware(app, auth_token)
    return app


def _run_human_ui(host: str = "127.0.0.1", port: int = 8766, open_browser: bool = True,
                  app_window: bool = False, workspace: str | None = None, block: bool = True) -> dict[str, Any]:
    """Start standalone Human Mode Studio UI (requires zero MCP SDK or AI IDE)."""
    if workspace:
        os.environ["UIFORGE_MCP_DIR"] = workspace
    from . import server as srv
    from .studio_ui import StudioServer, launch_ui_window

    studio = StudioServer(srv.store, host=host, port=port, mode="ui")
    info = studio.start()
    print(f"UIForge Human Studio running at {info['url']} (workspace: {srv.store().workspace})", file=sys.stderr, flush=True)
    if open_browser:
        launch_ui_window(info["url"], app_window=app_window)
    if block:
        import time
        try:
            while studio.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            studio.stop()
    return info


def _run_mcp_server(transport: str, host: str, port: int, toolset: str | None, compact: bool,
                    auth_token: str | None, sandbox_exports: bool, allow_arbitrary_paths: bool,
                    insecure_no_auth: bool, parser: argparse.ArgumentParser) -> None:
    from . import server as srv
    if not srv.MCP_AVAILABLE:
        parser.error("MCP Mode requires the 'mcp' package (pip install 'mcp>=1.2'). For Human Mode run: uiforge ui")
    srv.configure_server(toolset=toolset, compact=(True if compact else None))
    tr = "streamable-http" if transport == "http" else transport
    if tr == "stdio":
        if sandbox_exports:
            srv.set_export_sandbox(True)
        srv.mcp.run()
    else:
        token = auth_token or os.environ.get("UIFORGE_MCP_AUTH_TOKEN") or None
        is_loopback = host in ("127.0.0.1", "localhost", "::1")
        if not is_loopback and not token and not insecure_no_auth:
            parser.error(
                f"Refusing to bind non-loopback host '{host}' without --auth-token "
                "(pass --auth-token <secret>, set UIFORGE_MCP_AUTH_TOKEN, or pass --insecure-no-auth)."
            )
        if not allow_arbitrary_paths:
            srv.set_export_sandbox(True)
        if tr == "streamable-http" and hasattr(srv.mcp, "streamable_http_app"):
            import uvicorn
            app = build_http_app(host=host, auth_token=token)
            uvicorn.run(app, host=host, port=port)
        else:
            if hasattr(srv.mcp, "settings"):
                srv.mcp.settings.host = host
                srv.mcp.settings.port = port
            srv.mcp.run(transport=tr)


def _add_mcp_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--transport", choices=("stdio", "http", "streamable-http", "sse"), default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--toolset", choices=("full", "core", "game", "desktop", "web"), default=None,
                   help="Limit exposed MCP tools to a focused profile to cut LLM token overhead.")
    p.add_argument("--compact", action="store_true",
                   help="Compress tool descriptions to cut MCP tool-list token footprint by ~60-70%.")
    p.add_argument("--auth-token", default=None,
                   help="Require Authorization: Bearer <token> on HTTP/SSE transport (or set UIFORGE_MCP_AUTH_TOKEN).")
    p.add_argument("--sandbox-exports", action="store_true",
                   help="Lock all export writes inside workspace exports/ (auto-enabled on HTTP transport).")
    p.add_argument("--allow-arbitrary-paths", action="store_true",
                   help="Disable automatic export sandboxing on HTTP transport (trusted networks only).")
    p.add_argument("--insecure-no-auth", action="store_true",
                   help="Allow binding non-loopback HTTP addresses without --auth-token (NOT recommended).")


def cli_main(argv: list[str] | None = None, default_mode: str = "mcp") -> None:
    """Entry point for uiforge-mcp (default MCP Mode) and uiforge (default Human UI Mode)."""
    args_list = sys.argv[1:] if argv is None else list(argv)
    env_mode = os.environ.get("UIFORGE_MODE", "").strip().lower()
    if not args_list:
        chosen = env_mode if env_mode in ("mcp", "ui", "combined") else default_mode
        if chosen == "ui":
            _run_human_ui()
            return
        if chosen == "combined":
            args_list = ["combined"]
        else:
            from . import core
            from .server import MCP_AVAILABLE, configure_server, mcp
            if not MCP_AVAILABLE:
                print("Error: MCP Mode requires the 'mcp' package (pip install 'mcp>=1.2'). "
                      "To launch standalone Human Studio UI without MCP, run: uiforge ui", file=sys.stderr)
                sys.exit(2)
            core.set_mode("mcp")
            configure_server()
            mcp.run()
            return

    parser = argparse.ArgumentParser(
        prog="uiforge" if default_mode == "ui" else "uiforge-mcp",
        description=f"UIForge {__version__}: deterministic UI design studio & MCP server (MCP Mode, Human UI Mode, Combined Mode).",
    )
    parser.add_argument("--version", action="version", version=f"uiforge-mcp {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_ui = sub.add_parser("ui", help="Human Mode: launch the standalone UIForge Studio (no MCP or AI IDE required).")
    p_ui.add_argument("--host", default="127.0.0.1")
    p_ui.add_argument("--port", type=int, default=8766)
    p_ui.add_argument("--app", action="store_true", help="Open as a frameless desktop window (pywebview or Edge/Chrome --app).")
    p_ui.add_argument("--no-browser", action="store_true", help="Start the UI server without opening a browser tab.")
    p_ui.add_argument("--workspace", default=None, help="Explicit workspace directory (defaults to .uiforge/ or ~/UIForge).")

    p_mcp = sub.add_parser("mcp", help="MCP Mode: run the MCP server only (stdio or Streamable HTTP, no UI).")
    _add_mcp_args(p_mcp)
    p_mcp.add_argument("--workspace", default=None)

    p_comb = sub.add_parser("combined", help="Combined Mode: run MCP server + Human Studio UI simultaneously on a shared synced workspace.")
    _add_mcp_args(p_comb)
    p_comb.add_argument("--ui-host", default="127.0.0.1")
    p_comb.add_argument("--ui-port", type=int, default=8766)
    p_comb.add_argument("--app", action="store_true", help="Open Studio UI as a frameless desktop window.")
    p_comb.add_argument("--no-browser", action="store_true", help="Do not auto-open browser on startup.")
    p_comb.add_argument("--workspace", default=None)

    p_srv = sub.add_parser("serve", help="Run UIForge in any mode (--mode mcp | ui | combined).")
    p_srv.add_argument("--mode", choices=("mcp", "ui", "combined"), default="mcp")
    _add_mcp_args(p_srv)
    p_srv.add_argument("--ui-host", default="127.0.0.1")
    p_srv.add_argument("--ui-port", type=int, default=8766)
    p_srv.add_argument("--app", action="store_true")
    p_srv.add_argument("--no-browser", action="store_true")
    p_srv.add_argument("--workspace", default=None)

    sub.add_parser("doctor", help="Diagnose GPU hardware, active backends, modes, toolsets and local engines/IDEs.")

    p_gpu = sub.add_parser("install-gpu", help="Auto-detect GPU architecture and print or install the optimal extra.")
    p_gpu.add_argument("--arch", choices=("auto", "nvidia", "amd", "intel", "apple", "cpu"), default="auto")
    p_gpu.add_argument("--apply", action="store_true", help="Actually invoke pip install for the selected GPU extra.")

    p_set = sub.add_parser("setup", help="Generate or write MCP config for OpenCode, Claude Code, Codex, VS Code, Visual Studio, Antigravity, Cursor, Windsurf or ChatGPT.")
    p_set.add_argument("client", choices=(*CLIENTS, "all"))
    p_set.add_argument("--scope", choices=("user", "project"), default="user")
    p_set.add_argument("--gpu", choices=("auto", "nvidia", "amd", "intel", "apple", "cpu"), default="auto")
    p_set.add_argument("--name", default="uiforge")
    p_set.add_argument("--local-python", action="store_true")
    p_set.add_argument("--port", type=int, default=8765)
    p_set.add_argument("--write", action="store_true", help="Write/merge directly into the IDE config file.")

    ns = parser.parse_args(args_list)
    if getattr(ns, "workspace", None):
        os.environ["UIFORGE_MCP_DIR"] = ns.workspace

    if ns.cmd == "ui":
        _run_human_ui(host=ns.host, port=ns.port, open_browser=not ns.no_browser,
                      app_window=ns.app, workspace=ns.workspace, block=True)
    elif ns.cmd == "mcp":
        from . import core
        core.set_mode("mcp")
        _run_mcp_server(ns.transport, ns.host, ns.port, ns.toolset, ns.compact,
                        ns.auth_token, ns.sandbox_exports, ns.allow_arbitrary_paths, ns.insecure_no_auth, parser)
    elif ns.cmd == "combined" or (ns.cmd == "serve" and ns.mode == "combined"):
        from . import core, server as srv
        from .studio_ui import StudioServer, launch_ui_window
        core.set_mode("combined")
        studio = StudioServer(srv.store, host=ns.ui_host, port=ns.ui_port, mode="combined")
        info = studio.start()
        print(f"UIForge Combined Mode: Studio UI live at {info['url']} (shared workspace: {srv.store().workspace})",
              file=sys.stderr, flush=True)
        if not ns.no_browser:
            launch_ui_window(info["url"], app_window=ns.app)
        try:
            _run_mcp_server(ns.transport, ns.host, ns.port, ns.toolset, ns.compact,
                            ns.auth_token, ns.sandbox_exports, ns.allow_arbitrary_paths, ns.insecure_no_auth, parser)
        finally:
            studio.stop()
    elif ns.cmd == "serve":
        if ns.mode == "ui":
            _run_human_ui(host=ns.ui_host, port=ns.ui_port, open_browser=not ns.no_browser,
                          app_window=ns.app, workspace=ns.workspace, block=True)
        else:
            from . import core
            core.set_mode("mcp")
            _run_mcp_server(ns.transport, ns.host, ns.port, ns.toolset, ns.compact,
                            ns.auth_token, ns.sandbox_exports, ns.allow_arbitrary_paths, ns.insecure_no_auth, parser)
    elif ns.cmd == "doctor":
        rep = doctor_report()
        try:
            from .server import MCP_AVAILABLE, tool_stats
            rep["version"] = __version__
            rep["modes_available"] = ["ui", "mcp", "combined"] if MCP_AVAILABLE else ["ui"]
            rep["mcp_sdk_available"] = MCP_AVAILABLE
            rep["mcp_tools"] = tool_stats()
        except Exception:
            pass
        print(json.dumps(rep, indent=2, ensure_ascii=False))
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
        from . import core
        from .server import configure_server, mcp
        core.set_mode("mcp")
        configure_server()
        mcp.run()


def uiforge_main(argv: list[str] | None = None) -> None:
    """Entry point for the ``uiforge`` command (defaults to Human UI Mode)."""
    cli_main(argv=argv, default_mode="ui")
