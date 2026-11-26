# Changelog

## 0.15.0 - 2026-11-26

- **Three Seamless Runtime Modes (`Human UI`, `MCP`, `Combined`):** added a dedicated `uiforge` CLI entrypoint (defaults to Human Mode Studio UI) alongside `uiforge-mcp` (defaults to MCP Mode), plus explicit `ui`, `mcp`, `combined`, `serve --mode mcp|ui|combined` subcommands and `UIFORGE_MODE` env support.
- **Standalone Human Mode Studio UI (`studio_ui.py`, `ui_assets/`):** built a zero-CDN, 100% offline original design studio ("Obsidian Forge Atelier" + Light Studio theme) with UIForge-forged PBR brand emblem and 3 real starter templates (`Tactical Sci-Fi HUD`, `Fantasy RPG Forge`, `Desktop & SaaS App`), **`Ctrl+K` Command Palette**, **8-point interactive resize handles**, **magnetic smart snap guides**, **`Shift+Click` multi-select & distribute**, **double-click inline text editing**, **live Cook-Torrance PBR Tuner + custom material swatches**, **Color-Blindness & `Pseudo-Long`/`Pseudo-RTL` Vision Simulator**, **Multi-Device Responsive Matrix**, **Visual Variations Explorer**, **CSS `:root` / Tailwind v4 `@theme` / `oklch()` / shadcn HSL token importer** (`tokens.py` + `set_theme(tokens=...)`), **Quick Motion Preset Builder + `dotLottie v2`/GIF export**, WCAG 2.2 keyboard navigation & focus-trapped dialogs, version snapshots + Pixel Visual Diff, one-click Export Center with inline code copy & sandboxed HTML preview, GPU & optional MCP IDE setup, and `--app` frameless native window launcher.
- **MCP-Independent Shared Core & Concurrency Hardening (`core.py`, `store.py`, `server.py`):** extracted shared `invoke_operation()`, `render_view()`, and thread-safe `ActivityLog` into `core.py` so Human Studio UI and MCP Mode execute the exact same engine logic with zero duplication; added `MCP_AVAILABLE` runtime shim so Human Mode boots and executes all 97 core operations with zero `mcp` SDK installed; hardened `Store` with re-entrant `threading.RLock`, per-write unique `tempfile.mkstemp` + `os.fsync` + retry `os.replace`, and cross-process `sync_from_disk()` for safe single-process and multi-process Combined Mode collaboration.
- **Code Quality & Slop Cleanup:** refactored 408-line monolithic `render_widget()` in `widgets.py` into focused per-widget renderers (`_render_slider`, `_render_toggle`, `_render_dropdown`, `_render_input`, `_render_scroll`), deduplicated render+overlay logic across `live.py` and `studio_app.py`, replaced silent `except Exception: pass` blocks in `store.py` with structured logging, silenced benign Windows keep-alive `ConnectionResetError` tracebacks in HTTP servers, removed unused imports across engine modules, and added OpenAI Codex (`~/.codex/config.toml`) support to `uiforge-mcp setup`.
- **Comprehensive Documentation Overhaul & Real UI Showcases:** updated every Markdown document in the repository (`README.md`, `README.tr.md`, `docs/GUIDE.md`, `docs/COMPATIBILITY.md`, `configs/README.md`, `skill/uiforge-mcp/SKILL.md`, `SECURITY.md`, `CONTRIBUTING.md`, `THIRD_PARTY_LICENSES.md`, PR template), added root `llms.txt`, removed stale/contradictory claims and vendor-specific bias, and embedded 4 real Studio UI screenshots captured from live Chrome CDP sessions.

## 0.14.0 - 2026-11-26

- **Security Hardening & Single-Source Versioning:** fixed version drift across `__init__.py`, `pyproject.toml` and `export_atlas` (`__version__ = "0.14.0"`); hardened `binding.py` AST evaluator against exponentiation (`9**9**9`) and string-multiplication (`'a' * 10**6`) DoS bombs; added constant-time `BearerAuthMiddleware` (`--auth-token` / `UIFORGE_MCP_AUTH_TOKEN`), non-loopback bind protection, and automatic export path sandboxing (`--sandbox-exports` / `UIFORGE_MCP_SANDBOX_EXPORTS`) for remote Streamable HTTP MCP deployments.
- **Modular Toolsets, Schema Compression & MCP Progress:** added `--toolset` (`full | core | game | desktop | web`) and `--compact` (`UIFORGE_MCP_TOOLSET`, `UIFORGE_MCP_COMPACT_TOOLS`) cutting LLM context overhead by up to **77%** (`core + compact`: ~7.8K tokens vs ~35K full); exposed token footprint metrics in `uiforge-mcp doctor`; wired non-blocking `report_progress()` notifications for long exports.
- **Pure-MIT Built-in Vector Icon Library (`icons.py`, `add_icon`, `uiforge://icons`):** 142 originally authored 24×24 geometric vector icons (UI, navigation, media, RPG, FPS, racing, sci-fi, shop) instantiated as editable native `path` elements supporting PBR materials, glows, strokes, gradients, animations, and `batch` ops.
- **Complete Native Interactive Widget Suite (`add_slider`, `add_toggle`, `add_dropdown`):** expanded first-class widgets beyond `input` and `scroll` to include Slider, Toggle (switch & checkbox), and Dropdown/ComboBox — rendered on canvas with live `set_binding` sync and exported as genuine native controls across Web/React (TSX/Tailwind), Godot 4 (`HSlider`, `CheckButton`/`CheckBox`, `OptionButton`), Unity UI Toolkit (`<ui:Slider>`, `<ui:Toggle>`, `<ui:DropdownField>`), Unity uGUI (`Slider`, `Toggle`, `Dropdown`), Roblox, Unreal Engine UMG (`USlider`, `UCheckBox`, `UComboBoxString`), C#/.NET (`WPF`, `Avalonia`, `WinUI 3`), C++ `Qt 6 QML`, and C++17 `Dear ImGui`.
- **Unreal Engine UMG Screen Exporter (`export_screen(engine="unreal")`):** generates a complete UE 5.5–5.8 Python `WidgetBlueprint` builder (`WBP_<Name>_build_umg.py`) importing PNG slices (`TC_EDITOR_ICON`, `TEXTUREGROUP_UI`) and constructing a `CanvasPanel` hierarchy with 9-slice `SlateBrush` margins, responsive `Anchors`, `Image`, `TextBlock`, `EditableTextBox`, `ScrollBox`, `Slider`, `CheckBox`, and `ComboBoxString`.
- **3D Diegetic Perspective Tilt & Curved Visor HUD (`perspective` / `visor_curve`):** OpenCV-accelerated premultiplied-RGBA projective homography (`rotate_x`, `rotate_y`, `rotate_z`, `fov`) and cylindrical cockpit/helmet HUD curvature (`visor_curve`) on any element or layer.
- **SEP-1865 MCP App Studio (`studio_app.py`, `open_studio`, `ui://uiforge/studio.html`) & Live Preview v2 (`live.py`):** self-contained interactive studio runnable inline or in a host side pane (`aux_pane` / `global` entrypoints) with zero-token app-only tools (`studio_app_state`, `studio_app_render`), plus upgraded localhost Live Studio v2 featuring click-to-inspect element boxes, layer visibility toggles, state preview switcher, live `set_binding` variable sliders, and animation timeline scrubber.
- **Smart Screenshot v2, Pixel Visual Diff & Extended WCAG Audit:** upgraded `import_screenshot` with sibling row/column layout-group inference, pill toggle detection, and automatic `$ss_*` theme token binding; added `canvas_version(action="visual_diff")` rendering Before | After | Diff Heatmap PNGs with `changed_pct` / MAE metrics; extended `review_canvas` WCAG contrast checks to `input` and `dropdown` widgets with suggested high-contrast colors and structured `wcag` summary.
- **Multi-OS CI & PyPI Release Workflow:** expanded GitHub Actions CI to `ubuntu-latest`, `macos-latest`, `windows-latest` + `ruff` syntax/bug lint, and added `.github/workflows/release.yml` for PyPI trusted publishing.

## 0.13.0 - 2026-11-25

- **Cross-GPU WebGPU Compute Backend (`gpu_wgpu.py`, `[wgpu]` extra):** modular pluggable backend registry (`UIFORGE_MCP_GPU=auto|cuda|wgpu|cpu`) compiling sandboxed shader ASTs to WGSL `@compute` with bit-exact `u32` lattice hashing (`max_diff < 1e-4` vs CPU, **32× faster** at 512×512 on RTX 4060 Ti Vulkan) plus a WGSL Cook-Torrance GGX PBR compute shader (**7.1× faster** than CPU). Targets Vulkan, DirectX 12 and Metal through `wgpu-py` (physically verified on NVIDIA RTX 4060 Ti Vulkan/D3D12; AMD, Intel and Apple Silicon architecturally targeted via standard WGSL, not physically tested).
- **Custom `.hdr` & `.exr` HDRI Environment Maps (IBL):** pure-Python Radiance `.hdr` (RGBE + RLE) decoder and pure-Python OpenEXR `.exr` (uncompressed / ZIPS / ZIP HALF & FLOAT) decoder, plus workspace-level `set_theme(environment=...)` and canvas-level `update_canvas(environment=...)` IBL settings that automatically light all PBR materials.
- **AAA Procedural Frame Generator Upgrade (`frames.py`):** upgraded `add_frame` to 9 presets (adding `royal_ornate` and `fantasy_parchment`) with symmetrical cubic-Bézier corner filigree scrollwork, winged gemstone crests, bottom fleur-de-lis finials, forged iron corner hinge clasps, perimeter blacksmith rivet rings, tactical HUD telemetry rulers, LED indicators, and warning chevrons.
- **dotLottie v2.0 Interactive State Machines (`lottie.py`):** upgraded `export_animation(..., format="dotlottie")` to the official dotLottie v2.0 spec (`manifest.json` `version: "2"`, `a/<id>.json` animations, `s/<id>.json` state machine synthesized from `set_interaction` + `set_binding` + animations with `PlaybackState`, `Transition`/`Tweened`, `PointerEnter`/`PointerExit`/`PointerDown`/`PointerUp`/`Click`/`OnComplete`, and typed `inputs`/`guards`).
- **First-Class Interactive `Scroll` and `Input` Widgets (`widgets.py`, `add_input`, `add_scroll`):** realistic canvas rendering (with shaped `TextLayout` focus caret, password masking, labels, clipped scrollable rows and proportional scrollbars) + native control export across Web/React (`<input>` + `overflow: auto`), Godot 4 (`LineEdit` + `ScrollContainer`), Unity UI Toolkit (`<ui:TextField>` + `<ui:ScrollView>`), Unity uGUI (`InputField` + `ScrollRect`), Roblox (`TextBox` + `ScrollingFrame`), and all desktop targets.
- **C# / .NET & C++ Desktop UI Exporters (`desktop_export.py`):** extended `export_screen(engine=...)` with 5 native desktop frameworks: `"wpf"` (.NET Framework 4.8 & .NET 8/9 `.xaml` + `.xaml.cs` + `INotifyPropertyChanged` ViewModel), `"avalonia"` (cross-platform `.axaml`), `"winui"` (WinUI 3 `.xaml`), `"qt-qml"` (C++ Qt 6 `.qml`), and `"imgui"` (C++17 Dear ImGui self-contained `_ui.hpp`).
- **Screenshot-to-Editable-Canvas (`screenshot.py`, `import_screenshot`):** OpenCV SIMD K-means palette extraction, hierarchical `RETR_TREE` card/button/circle segmentation with corner-radius estimation, solid vs linear gradient & border detection, and optional local OCR (`rapidocr_onnxruntime` / `pytesseract`) with OpenCV text-line heuristic fallback.
- **Configurable Quality Tiers & Visual Style Presets (`profiles.py`):** 4 real rendering/geometry quality tiers (`simple`, `standard`, `advanced`, `aaa`) and 9 visual style presets (`kids`, `cartoon`, `stylized`, `minimal`, `web_saas`, `scifi`, `dark_fantasy`, `realistic`, `photorealistic`) wired into `set_theme`, `update_canvas`, `add_frame(preset="auto")`, `Renderer` SS/noise/PBR pipeline, plus bugfix expanding `"material"` inside named string theme styles.
- **GPU Architecture Installer & Multi-IDE CLI (`cli.py`, `configs/README.md`):** hardware GPU auto-detector (`doctor`), architecture-grouped pip extras (`[nvidia]`, `[amd]`, `[intel]`, `[apple]`, `[cpu]`, `[ocr]`), Streamable HTTP transport (`serve --transport http` for ChatGPT MCP Connectors), and one-command safe-merge config installer (`setup opencode|claude|vscode|visualstudio|antigravity|cursor|windsurf|chatgpt --write`).
- **2026 API Compatibility Audit (`docs/COMPATIBILITY.md`):** Exa-verified API audit + Godot 4.5 `CanvasTexture` inverted smoothness `specular_texture` fix + Unreal Engine 5.5–5.8 `export_pbr_maps(engine="unreal")` automated Python importer (`TC_NORMALMAP` / `TC_MASKS` / `TC_DEFAULT`), physically verified live in local Unreal Engine 5.8.4, Blender 5.3.0, .NET 8 WPF (`dotnet build` 0 errors / 0 warnings), Chromium Playwright, `tsc`, and FFmpeg 9.0.2.

## 0.12.0 - 2026-11-25

- **Performance engine (OpenCV SIMD + Fused CUDA 12):** added `opencv-python-headless` for native C++ AVX2/NEON `distanceTransform` (~2.8 ms at 512x512, ~9x faster than NumPy JFA), Scharr normal gradients, `GaussianBlur`, exact Euclidean disc morphology, and `remap` liquid-glass refraction; full `float32` pixel pipeline; AST-to-CUDA fused `ElementwiseKernel` compilation on NVIDIA GPUs (3.3-5.7 ms at 1024x1024); bit-exact uint32 noise hash across CPU and GPU; 128 MB LRU element render cache; static-layer baking in animation exports (4.7x faster); cropped shader/PBR/layer-style bounding boxes; streaming `ffmpeg` stdin video encoding; PackBits RLE PSD compression.
- **Photorealistic Cook-Torrance GGX PBR engine (`pbr.py`, `style.pbr`):** full linear-HDR dual-lobe Cook-Torrance GGX BRDF with perspective camera view vectors, curvature edge wear, 5 studio HDRI light tents (`bright`, `warm`, `dark`, `sunset`, `cyberpunk`) plus optional custom equirectangular `.hdr`/`.png`/`.jpg` IBL (`env_map`), clearcoat lacquer, linear & radial bowtie anisotropy, subsurface scattering wrap, crevice AO, HDR emission, ACES filmic tone mapping, layer-level PBR styling, and flip-safe light mirroring.
- **Engine PBR Texture Map Export (`export_pbr_maps`):** bakes any 2D UI canvas into Albedo, Tangent Normal (OpenGL `+Y` and Unreal DirectX `-Y`), Roughness, Metallic, AO, Height, ORM-packed, and Emissive PNGs — plus ready Godot 4 `CanvasTexture .tres` for dynamic in-engine 2D lighting.
- **Parametric AAA Frame Builder (`add_frame`):** generates 100% editable vector + PBR borders across 7 presets (`rpg_gold`, `scifi_hud`, `cyber_tech`, `glass_card`, `medieval_iron`, `luxury_minimal`, `cartoon_thick`) returning the exact `inner_box` safe area.
- **New export formats & AI Ergonomics:** compressed **dotLottie (`.lottie`)** multi-animation archive (`export_animation(..., animation="all", format="dotlottie")`), **TypeScript React (`.tsx`)** (`export_react(..., typescript=True)`), industry-standard **TexturePacker / Godot `AtlasTexture` / Unity / CSS** sprite atlases (`export_atlas(..., format=...)`), expanded atomic `batch` ops (`add_frame`, `set_pin`, `set_state`, `set_binding`, `set_interaction`, `set_link`, `align_elements`, `arrange_elements`, `delete_layer`), native MCP Resources & Prompts, atomic JSON writes in `store.py`.
- **Legal & license hygiene:** replaced LGPL-3.0 `python-bidi` with a clean pure-Python MIT Unicode UAX #9 BiDi resolver in `shaping.py`; added `THIRD_PARTY_LICENSES.md` documenting all dependencies and bundled SIL OFL-1.1 fonts; rebuilt hero banner and showcase examples.
- **39 built-in materials (+16 new):** rebuilt all 39 materials on Cook-Torrance GGX PBR & domain-warped shaders (`gold`, `silver`, `chrome`, `bronze`, `copper`, `steel`, `iron`, `radial_metal`, `hammered_gold`, `rust`, `wood`, `stone`, `runic_stone`, `marble`, `obsidian`, `jade`, `gem`, `ruby`, `emerald`, `lava`, `ice`, `leather`, `paper`, `aged_parchment`, `fabric`, `carbon_twill`, `wax_seal`, `enamel`, `glass`, `liquid_glass`, `hologram`, `energy_shield`, `foil_holographic`, `neon`, `plastic`, `candy_gloss`, `clay_3d`, `rubber`, `jelly`). Fixed `theme.json` persistence for custom materials and `light: null` / `pbr: null` overrides.
- **Reactive data binding (`set_binding`):** canvas variables and sandboxed AST expressions driving bar widths, colours, visibility and `{placeholders}`; live override in `preview(..., data=...)`, `window.uiforgeSetData()` in web export, `data` prop in React, and typed controllers in engines.
- **Engine controllers & Unity uGUI (`export_screen`):** added `engine="unity-ugui"` C# Canvas/RectTransform builder; automatic interactive controller generation (`_controller.gd` for Godot 4 with gamepad `focus_neighbor_*`, `Controller.cs` for Unity UI Toolkit) wired to `set_binding`, `set_interaction` and optional `sfx` audio events.
- **Live Preview Studio (`live_preview`):** zero-dependency localhost (`127.0.0.1`) HTTP + SSE live browser previewer that auto-reloads on every edit with IDs, safe-area guides, backdrop switcher and cursor coordinate inspection.
- **Web / React upgrades:** Tailwind CSS utility mode (`export_react(..., css="tailwind")`), keyboard arrow + Web Gamepad API focus navigation, `onSfx` hook, and Git-friendly `.uiforge/` auto-detected project-local workspace mode.

## 0.11.0 - 2026-11-16

- `set_interaction`: a state machine (hover / press / click / key / animation-end triggers; play, states, navigation) that runs in web and React output and is listed in the animation JSON.
- `export_react`: React components (JSX + CSS + runtime, images imported).
- `export_animation` MP4 / WebM video (ffmpeg; `[video]` extra).
- `make_variations`: alternative palette / shape / type directions with a comparison sheet.
- DESIGN.md import (`set_theme(tokens=...)`) and export (`export_theme("design.md")`).
- Custom materials: `set_theme(materials=...)`.
- Web: state looks now beat inline styles (hover / pressed CSS did not apply before).

## 0.10.0 - 2026-11-16

- 23 ready materials (`style.material`): metals, wood, stone, marble, leather, fabric, paper, rust, lava, ice, gem, plastic, rubber, jelly, glass, neon, hologram; tintable, seedable, animatable.
- Images: `crop`, `cutout` background removal, `zoom` / `focus` pan and zoom (also on image fills), animated GIF / APNG / WebP and sprite sheets via `frame`, sub-pixel placement.

## 0.9.0 - 2026-11-16

- Lottie: plain shapes and text export as vector shape layers (solid / gradient fill, stroke, animated colour).
- Animation: `motion` property moves along a path (optional rotate), `motion_blur` in export_animation.
- Style: `feather` softens edges.
- Skill rewritten; code comments removed.

## 0.8.0 - 2026-11-16

Layout, components, effects, text and export additions:

- Live auto layout (re-flows on every change), fill / min / max sizing, grid spans, group items.
- Component variants (states named prop=value), optional parts (hide / show), slots.
- Number tokens, W3C DTCG token import / export, letter case, spring easing, diamond gradients.
- Glass refraction, progressive blur, noise modes, edge texture, luminance masks and clips, per-fill blend,
  image crop and exposure / temperature / shadows / highlights.
- Line ends (arrows...), tapered / variable-width / wiggly strokes.
- Text: lists, paragraph spacing, indent, OpenType features, variable axes, vertical trim, colour emoji,
  text on any path, text to vector outlines.
- vectorize_image, path simplify, find_elements, restyle replace_text, version diff, notes, focus order.
- New outputs: vector PDF (export_pdf), Lottie (export_animation lottie) and websites (export_web: HTML / CSS
  with links, overlays, hover states, CSS animations, View Transitions, responsive pins).
- Fix: export_theme had lost its tool registration.

## 0.7.0 - 2026-11-15

- Server instructions cut to ~1.8k characters: clients truncate long instructions (Claude Code near 4k),
  which hid half the reference. The full reference now comes from the read-only `guide(topic)` tool.
- `make_palette`: OKLCH colour scales (50-950) with WCAG text contrast per step and accent hues.
- `restyle`: replace a colour or font across every canvas and theme style, or set props by filter.
- `path_ops`: flatten, offset (grow / shrink) and outline stroke, turning shapes and lines into paths.
- `review_canvas` design lint: near-miss alignment, radius / stroke / text-size sprawl, hard-coded colours.

## 0.6.0 - 2026-11-15

- SVG export keeps more as vector: stripes / dots / grid fills become SVG patterns, single-side strokes
  stay vector, shadows and glows use the standard filter chain Figma itself writes (several shadows on
  one shape no longer shadow each other), and frosted-glass panels carry the blurred scene behind them.
- `export_svg(image_scale=...)`: sharper embedded pictures for large prints.
- `export_png(preset="ios" | "android" | "web")`: the whole density set in one call.
- English README with a Turkish version, banner, badges, issue and pull-request templates, changelog.

## 0.5.0 - 2026-11-14

- Optional GPU acceleration: `pip install "uiforge-mcp[gpu]"` (CuPy, CUDA 12) runs shader fills and large
  blurs on an NVIDIA GPU, with an automatic CPU fallback.

## 0.4.0 - 2026-11-14

- Background blur (frosted glass), single-side strokes, ellipsis truncation, underline / strikethrough,
  named version history (`canvas_version`).
- Security policy, contributing guide, code of conduct, Windows CI, trademark notice.

## 0.3.0 - 2026-11-14

- Exact boolean shapes, smoothed corners, fill stacks, variable modes, auto-layout wrap, editable vector
  SVG export, parallel animation frames.
- One-line `uvx` install, tool annotations (read-only / destructive), layered JPG / WebP / SVG layer export.
- Every tool error explains how to recover; allow-listed values in generated engine scripts; render size limit.

## 0.2.0 - 2026-11-14

- Multilingual text engine (HarfBuzz shaping, bidi, Noto fallback fonts, CJK line breaking).
- Shader fills, designer workflow tools (states, templates, string tables, pins, prototypes, engine scenes).
- Components, arrays, cut-outs, SVG import, self-review.

## 0.1.0 - 2026-11-13

- First release: shapes, text, styles, layers and lighting, keyframe animation, 9-slice export for
  Unity, Unreal, Roblox and Godot.
