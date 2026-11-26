<div align="center">

**English** · [Türkçe](README.tr.md)

<a href="#quick-start">
  <img src="docs/banner.png" alt="UIForge (uiforge-mcp) — Deterministic UI Design Studio & MCP Server" width="100%" />
</a>

<br />

**100% local, MIT-licensed UI design studio & MCP server — use the standalone visual Studio UI, connect any MCP AI client, or edit live together on one workspace.**

<p>
  <a href="https://pypi.org/project/uiforge-mcp/"><img src="https://img.shields.io/pypi/v/uiforge-mcp?style=flat-square&color=38bdf8" alt="PyPI" /></a>
  <a href="https://github.com/TENETTE/uiforge-mcp/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/TENETTE/uiforge-mcp/tests.yml?branch=main&style=flat-square&label=tests" alt="CI Tests" /></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+" /></a>
  <a href="#three-modes"><img src="https://img.shields.io/badge/modes-Human_UI_%7C_MCP_%7C_Combined-e89b3c?style=flat-square" alt="Modes" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e?style=flat-square" alt="MIT License" /></a>
</p>

<p>
  <a href="#quick-start">Quick Start</a> ·
  <a href="#three-modes">Three Modes</a> ·
  <a href="#highlights">Highlights</a> ·
  <a href="#export-targets">Exports</a> ·
  <a href="#benchmarks">Benchmarks</a> ·
  <a href="docs/SHOWCASES.md">Showcases</a> ·
  <a href="configs/README.md">IDE Setup</a>
</p>

</div>

---

## Quick Start

Requires Python **3.10+** and [uv](https://docs.astral.sh/uv/) (or `pip`). Zero subscriptions, zero cloud calls, zero diffusion hallucinations.

```bash
# 1. Human Mode — open the standalone Studio UI (no MCP or AI IDE required)
uvx --from uiforge-mcp uiforge
uvx --from uiforge-mcp uiforge ui --app   # frameless desktop window

# 2. Combined Mode — Studio UI + MCP server synced live on the same workspace
uvx --from uiforge-mcp uiforge combined

# 3. MCP Mode — auto-configure your AI client (opencode, claude, codex, vscode, visualstudio, antigravity, cursor, windsurf)
uvx uiforge-mcp setup claude --write
```

<details>
<summary>Persistent install, GPU extras & token-saving MCP toolsets</summary>

```bash
pip install uiforge-mcp

# Optional acceleration & features
pip install "uiforge-mcp[nvidia]"   # CUDA 12 + WebGPU
pip install "uiforge-mcp[wgpu]"     # AMD / Intel / Apple Metal
pip install "uiforge-mcp[desktop]"  # pywebview native window

# Shrink MCP tool-list tokens by up to 77%
uiforge-mcp mcp --toolset game --compact   # core | game | desktop | web | full
```

</details>

<br />

<img src="docs/ui_studio.png" alt="UIForge Studio running locally in Combined Mode" width="100%" />

---

## Three Modes

All three modes share the **exact same MCP-independent core engine** (`core.py` + `store.py`) and read/write the same `.uiforge/` (or `~/UIForge`) workspace with atomic JSON sync (`mkstemp` + `fsync` + `os.replace`).

| Mode | Command | What It Does | Requires MCP? |
| --- | --- | --- | :---: |
| **Human Mode** | `uiforge` / `uiforge ui --app` | Standalone visual Studio UI in browser or desktop window — works even without the `mcp` package installed | **No** |
| **MCP Mode** | `uiforge-mcp` (`stdio` / `http`) | Headless MCP server for OpenCode, Claude Code, Codex, VS Code, Visual Studio, Antigravity, Cursor, Windsurf, ChatGPT | Yes |
| **Combined Mode** | `uiforge combined` | Human Studio UI + MCP server editing the **same project live** via SSE, RLock & unified Activity Log | Optional |

---

## Highlights

- **Deterministic Vector + Cook-Torrance GGX PBR:** 39 built-in materials, custom `.hdr`/`.exr` IBL, live PBR parameter tuning & custom material saving, HarfBuzz BiDi/Indic typography, and 3D curved visor perspective.
- **Built-in Production Studio UI:** 3 instant starter templates, 8-point resize handles, magnetic snap guides, `Shift+Click` multi-select, inline text edit, `Ctrl+K` Command Palette, Dark/Light themes, Color-Blindness & Pseudo-Loc simulator, Multi-Device Matrix, CSS/Tailwind/shadcn token import, and WCAG contrast audit.
- **97 Core Operations + 142 MIT Vector Icons + 9 AAA Frames:** Native `input`, `scroll`, `slider`, `toggle`, and `dropdown` widgets plus `import_screenshot` v2 and pixel `visual_diff`.

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/ui_materials.png" alt="Cook-Torrance PBR Material Forge" width="100%" /><br />
      <strong>Cook-Torrance PBR Forge &amp; 142 Vector Icons</strong>
    </td>
    <td width="50%" valign="top">
      <img src="docs/ui_export.png" alt="One-click Engine & Desktop Export" width="100%" /><br />
      <strong>One-Click Engine Delivery &amp; Inline Code Inspector</strong>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <img src="examples/materials.png" alt="39 PBR Materials" width="100%" /><br />
      <strong>39 Built-in Cook-Torrance GGX Materials</strong>
    </td>
    <td width="50%" valign="top">
      <img src="examples/frames.png" alt="9 Parametric AAA Frames" width="100%" /><br />
      <strong>9 Editable Parametric AAA Frames</strong>
    </td>
  </tr>
</table>

> **See more:** [Full Showcase Gallery (`docs/SHOWCASES.md`)](docs/SHOWCASES.md) — Studio launcher, responsive mode, PBR normal/ORM texture maps, racing HUD, animations, and all 97 operations.

---

## Export Targets

| Category | Supported Outputs |
| --- | --- |
| **Game Engines** | **Unreal Engine 5.5–5.8** (UMG Python `WidgetBlueprint` builder), **Unity 6** (UI Toolkit + uGUI C#), **Godot 4** (`.tscn` + `_controller.gd` + `.tres`), **Roblox** (`ScreenGui .client.luau`) |
| **Desktop Apps** | **C# .NET** (`WPF` XAML + ViewModel, `Avalonia`, `WinUI 3`), **C++** (`Qt 6 QML`, self-contained `Dear ImGui` C++17) |
| **Web & Tokens** | **React 19 TSX / Tailwind**, **HTML5/CSS3** prototypes (live bindings + Gamepad API), W3C DTCG, `DESIGN.md`, CSS `:root` / Tailwind v4 `@theme` / shadcn import |
| **Assets & PBR Maps** | Albedo / Tangent Normal (OpenGL & DirectX) / Roughness / Metallic / AO / Height / ORM, PNG, editable SVG, PackBits PSD, PDF, sprite atlases, BMFont |
| **Motion & Video** | **dotLottie v2** (`.lottie` + interactive State Machine), Lottie JSON, H.264 MP4 / VP9 WebM, GIF, APNG, WebP, sprite sheets |

---

## Benchmarks

Measured locally on **Windows 11, Python 3.12, NVIDIA GeForce RTX 4060 Ti** (`UIFORGE_MCP_GPU=cpu|wgpu|auto`; zero mandatory GPU deps):

| Workload | CPU (OpenCV SIMD) | WebGPU (`wgpu` Vulkan) | Hybrid `auto` (CUDA + WebGPU) |
| --- | ---: | ---: | ---: |
| `512×512` exact Euclidean SDF (`distance_field`) | **2.69 ms** | 2.69 ms *(CPU SIMD)* | 2.69 ms *(CPU SIMD)* |
| `512×512` procedural shader (`fbm` + `ridged` + `voronoi`) | 143.9 ms | **4.16 ms** (35×) | **1.13 ms** (127× CUDA) |
| `512×512` Cook-Torrance GGX PBR + Studio IBL | 283.5 ms | **38.1 ms** (7.4×) | **37.3 ms** (7.6×) |
| 18 Cook-Torrance PBR cards (`1200×800`, cold / cached) | 531 ms / **7.8 ms** | 527 ms / **7.6 ms** | 572 ms / **7.5 ms** |
| 21-frame `1280×720` HUD sprite sheet | 4.23 s | 4.06 s | **2.95 s** (1.4×) |

<sub>Hardware GPU benchmarks measured on NVIDIA RTX 4060 Ti. AMD, Intel, and Apple Silicon (Metal) target portable WGSL via `wgpu-py` — see [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).</sub>

---

## Documentation & License

- **[`docs/SHOWCASES.md`](docs/SHOWCASES.md)** — Full Studio UI, PBR, HUD, animation & 97-tool gallery
- **[`configs/README.md`](configs/README.md)** — Multi-mode launch & MCP configs for 9+ AI clients
- **[`docs/GUIDE.md`](docs/GUIDE.md)** — Complete feature & engine reference (Turkish)
- **[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md)** — Verified OS, engine, GPU & client matrix
- **[`skill/uiforge-mcp/SKILL.md`](skill/uiforge-mcp/SKILL.md)** · **[`llms.txt`](llms.txt)** — Provider-neutral AI craft skill & index
- **[`SECURITY.md`](SECURITY.md)** · **[`CONTRIBUTING.md`](CONTRIBUTING.md)** · **[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)** · **[`CHANGELOG.md`](CHANGELOG.md)**

[MIT License](LICENSE) — free for personal and commercial use (11 bundled fonts are SIL OFL-1.1). Everything you create with UIForge belongs to you.

<!-- mcp-name: io.github.TENETTE/uiforge-mcp -->
