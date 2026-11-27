# Engine, Runtime, Mode & API Compatibility Matrix (2026 Verified)

This matrix documents official API verification performed via live documentation lookup and direct local hardware/toolchain execution. Platforms not physically installed on the verification machine are marked honestly as **Spec-verified only**.

---

## 1. UIForge Runtime Modes (v0.16.0)

| Mode | Command | Runtime Requirements | Verification Status |
| --- | --- | --- | --- |
| **Human Mode (Studio UI)** | `uiforge` / `uiforge ui` (`--app` for native window) | Core Python deps only (`pillow`, `numpy`, `opencv-python-headless`, `uharfbuzz`, `pyclipper`). **Zero runtime `mcp` dependency.** Optional `[desktop]` (`pywebview`) or system Edge/Chrome `--app=`. | **Verified live in headless Chrome CDP (0 JS errors) & with `mcp` blocked in `sys.modules`** |
| **MCP Mode** | `uiforge-mcp` / `uiforge mcp` (`--transport stdio\|http`) | Core Python deps + `mcp>=1.2`. No UI server started. Supports `--toolset`, `--compact`, `--auth-token`, `--sandbox-exports`. | **Verified live via `mcp 2.x` tool/resource/prompt suite & HTTP auth tests** |
| **Combined Mode (MCP + UI)** | `uiforge combined` / `uiforge serve --mode combined` | Runs MCP server + Studio UI on one shared synced workspace (`Store` `RLock` + `mkstemp`/`fsync`/`os.replace` + disk watcher + SSE). Also syncs across separate `uiforge-mcp` + `uiforge ui` processes. | **Verified live in-process, cross-process disk sync, SSE & 8-thread concurrency stress test** |

---

## 2. Export Targets, Compute Backends & Media Formats

| Target / Runtime | Verified Version / Spec | API & Deprecation Audit | Verification Status |
| --- | --- | --- | --- |
| **Unreal Engine Python Editor API & UMG** | UE 5.5 / 5.6 / **5.8** | `AssetImportTask`, `AssetToolsHelpers.get_asset_tools().import_asset_tasks()`, `imported_object_paths`, `TextureCompressionSettings.TC_EDITOR_ICON` / `TC_NORMALMAP` / `TC_MASKS` / `TC_DEFAULT`, `TextureGroup.TEXTUREGROUP_UI`, `EditorAssetLibrary.save_loaded_asset()`, plus UMG `WidgetBlueprintFactory` + `CanvasPanel` + `Image` (9-slice `SlateBrush`) + `TextBlock` + `EditableTextBox` + `ScrollBox` + `Slider` + `CheckBox` + `ComboBoxString` (`export_screen(engine="unreal")`). | **Executed live against local Unreal Engine 5.8** (`UnrealEditor-Cmd.exe` producing real `.uasset`) |
| **C# / .NET WPF** | .NET Framework 4.8, **.NET 8.0 / .NET 10.0** | `UserControl`, `Viewbox`, `Canvas`, `Border`, `TextBox`, `PasswordBox`, `ScrollViewer`, `Slider`, `CheckBox`, `ComboBox`, `INotifyPropertyChanged`, `ICommand` (`RelayCommand`) with zero external NuGet dependencies. | **Compiled live with `dotnet build` (.NET 8/10 SDK on Windows)** |
| **C# / .NET Avalonia & WinUI 3** | Avalonia 11.x / Windows App SDK 1.6+ | `https://github.com/avaloniaui` `.axaml` (`Watermark`, `PasswordChar`, `Slider`, `CheckBox`, `ComboBox`), WinUI 3 `.xaml` (`x:Bind ViewModel`, `PlaceholderText`, `ToggleSwitch`, `Slider`, `ComboBox`, `ScrollViewer`). | Spec-verified only (Avalonia/WinUI NuGet workloads not built offline) |
| **C++ Qt 6 Quick (QML) & Dear ImGui** | Qt 6.x / Dear ImGui 1.91+ | `import QtQuick`, `import QtQuick.Controls`, `TextField`, `ScrollView`, `Slider`, `Switch`, `CheckBox`, `ComboBox`, `MouseArea`; C++17 `ImGui::InputTextWithHint`, `ImGui::SliderFloat`, `ImGui::Checkbox`, `ImGui::Combo`, `ImGui::BeginChild`. | Spec & syntax verified only (Qt SDK / ImGui headers not installed locally) |
| **Godot 4** | Godot 4.4 / 4.5 | `.tscn` `format=3`, `Control`, `LineEdit` (`secret = true`), `ScrollContainer`, `HSlider`, `CheckButton`/`CheckBox`, `OptionButton`, `CanvasTexture` (`diffuse_texture`, `normal_texture`, inverted **`specular_texture`** smoothness map), `StyleBoxTexture`. | Spec-verified via official Godot 4.4/4.5 docs (Godot binary not installed locally) |
| **Unity** | Unity 6 (`6000.x`) | UI Toolkit `.uxml`/`.uss` (`<ui:TextField>`, `<ui:ScrollView>`, `<ui:Slider>`, `<ui:Toggle>`, `<ui:DropdownField>`), `AssetPostprocessor` (`TextureImporter`, `spriteBorder`), uGUI `CanvasScaler` / `InputField` / `ScrollRect` / `Slider` / `Toggle` / `Dropdown`. | Spec-verified via official Unity 6 docs (Unity Editor not installed locally) |
| **MCP Apps (SEP-1865)** | **2026-01-26** (`mcp 2.x`) | `ui://uiforge/studio.html` (`text/html;profile=mcp-app`), `open_studio` with `aux_pane`/`global` entrypoints, app-only zero-token tools (`studio_app_state`, `studio_app_render` with `visibility: ["app"]`). | **Verified schema, resource & snapshot runtime** |
| **Roblox Studio** | Luau (`--!strict`) | `ScreenGui`, `UIScale`, `ImageLabel` (`ScaleType.Slice`), `TextBox`, `ScrollingFrame` (`AutomaticCanvasSize`), `UIListLayout`, `Font.fromName()`. | Spec-verified only (Roblox Studio headless CLI N/A) |
| **Web & React / TypeScript** | HTML5 / CSS3 / **React 19** / TS 5.x | Live `<input defaultValue>`, `<select defaultValue>`, sliders, toggles, scrollable containers, typed `(href: string, mode?: string, to?: string)`, Tailwind utilities, Web Gamepad API. | **Verified live in headless Chromium + `tsc` TypeScript compiler** |
| **Blender PBR Maps** | **Blender 5.3** | Principled BSDF (`Base Color`, `Normal Map` OpenGL `+Y` non-color, `Roughness`, `Metallic`, `Displacement/Height`). | **Executed live in local Blender 5.3 headless Python** |
| **WebGPU (`wgpu-py`)** | `wgpu 0.33.0` (`wgpu-native 29.x`) | `enumerate_adapters_sync`, `request_adapter_sync`, `request_device_sync`, explicit `create_bind_group_layout` + `create_pipeline_layout`, `create_compute_pipeline`, `queue.read_buffer`. | **Verified live on NVIDIA RTX 4060 Ti (Vulkan & D3D12)**. AMD, Intel & Apple Silicon Metal architecturally targeted via standard WGSL, **not physically tested**. |
| **NVIDIA CUDA (`cupy`)** | CuPy 14.2.0 / CUDA 12.x | Fused `cp.ElementwiseKernel` with bit-exact `uint32` hashing (`max_diff = 0.0000` vs CPU). | **Verified live on NVIDIA RTX 4060 Ti** |
| **dotLottie** | **dotLottie v2.0** | `manifest.json` (`version: "2"`), `a/<id>.json`, `s/<id>.json` state machine (`PlaybackState`, `Transition`/`Tweened`, `PointerEnter`/`PointerExit`/`PointerDown`/`PointerUp`/`Click`/`OnComplete`, typed `inputs`/`guards`). | **Verified ZIP archive & schema structure** |
| **Video (`ffmpeg`)** | **FFmpeg 9.0.2** | Streaming RGBA stdin → H.264 MP4 (`yuv420p`) and transparent VP9 WebM (`yuva420p`). | **Verified live with local FFmpeg 9.0.2** |

---

## 3. MCP Client Configuration Schemas (Provider-Neutral, Verified 2026)

| AI Client / IDE | Config File Path | Top-Level Schema Key | Transport | Auto-Setup CLI |
| --- | --- | --- | --- | --- |
| **OpenCode v2** | `opencode.json` / `~/.config/opencode/opencode.json` | `mcp.servers.<name>` (`type: "local"`, `command: [...]`) | stdio | `uiforge-mcp setup opencode --write` |
| **OpenAI Codex CLI** | `~/.codex/config.toml` | `[mcp_servers.<name>]` (`command`, `args`) | stdio | `uiforge-mcp setup codex --write` |
| **Claude Code** | `.mcp.json` / `~/.claude.json` | `mcpServers.<name>` | stdio | `uiforge-mcp setup claude --write` |
| **Visual Studio 2022 (17.14+) / 2026** | `%USERPROFILE%\.mcp.json` or `<repo>\.mcp.json` | `servers.<name>` (`type: "stdio"`) | stdio | `uiforge-mcp setup visualstudio --write` |
| **VS Code (2026 Copilot)** | `<repo>\.mcp.json` (native) / `.vscode/mcp.json` (legacy) | `mcpServers` (native) / `servers` (legacy) | stdio | `uiforge-mcp setup vscode --write` |
| **Google Antigravity** | `~/.gemini/antigravity/mcp_config.json` | `mcpServers.<name>` | stdio | `uiforge-mcp setup antigravity --write` |
| **Cursor** | `~/.cursor/mcp.json` or `.cursor/mcp.json` | `mcpServers.<name>` | stdio | `uiforge-mcp setup cursor --write` |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | `mcpServers.<name>` | stdio | `uiforge-mcp setup windsurf --write` |
| **ChatGPT (Apps / Connectors)** | Streamable HTTP endpoint | `http://127.0.0.1:8765/mcp` (+ HTTPS tunnel + `--auth-token`) | Streamable HTTP | `uiforge-mcp serve --transport http --port 8765 --auth-token <secret>` |
