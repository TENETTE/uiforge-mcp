# Third-Party Licenses & Attribution

`uiforge-mcp` (UIForge) itself is licensed under the **MIT License** ([LICENSE](LICENSE)). All procedural graphics code, Cook-Torrance PBR shaders, UAX #9 BiDi level resolution, vector rasterizer, parametric frames, 142 built-in vector icons (`icons.py`), standalone Studio UI assets (`studio_ui.py`, `ui_assets/`), and example showcase assets in this repository are original works created for `uiforge-mcp` with no third-party copyrighted images, icon packs, or proprietary game assets.

---

## 1. Core Python Dependencies (Installed Separately via pip / uv)

None of the packages below are vendored inside this repository; they are installed by the user's package manager.

| Package | License | Notes |
| --- | --- | --- |
| `mcp` | MIT | Model Context Protocol Python SDK (required for MCP Mode & Combined Mode; **optional at runtime** for standalone Human Mode Studio UI) |
| `pillow` | MIT-CMU | Image I/O and 2D compositing |
| `numpy` | BSD-3-Clause | Vectorized numeric arrays |
| `opencv-python-headless` | Apache-2.0 (OpenCV) / MIT (wrapper) | Optional at runtime (graceful pure-NumPy fallback if absent). Note: PyPI binary wheels of `opencv-python-headless` bundle LGPL-2.1 FFmpeg binaries inside the `cv2` wheel (not invoked by `uiforge-mcp`); see `cv2/LICENSE-3RD-PARTY.txt`. |
| `uharfbuzz` | Apache-2.0 (binding) / Old MIT (HarfBuzz) | OpenType text shaping for complex scripts |
| `pyclipper` | MIT (binding) / Boost Software License 1.0 (Clipper) | Exact polygon boolean & offset operations |

> **Copyleft audit note:** As of v0.12.0, the LGPL-3.0 `python-bidi` dependency was replaced by an original pure-Python MIT Unicode UAX #9 Bidirectional Algorithm resolver in `src/uiforge_mcp/shaping.py` using Python's standard-library `unicodedata` module.

## 2. Optional Extras (Not Required for Core Usage)

| Extra / Package | License | Notes |
| --- | --- | --- |
| `[nvidia]` / `[gpu]` — `cupy-cuda12x` + `wgpu` | MIT (CuPy) + NVIDIA CUDA EULA + BSD-2-Clause (`wgpu-py`) | Optional NVIDIA CUDA 12 fused shader acceleration + WebGPU fallback |
| `[wgpu]` / `[amd]` / `[intel]` / `[apple]` — `wgpu` | BSD-2-Clause (`wgpu-py`) + MIT / Apache-2.0 (`wgpu-native`) | Optional cross-vendor WebGPU compute shaders & PBR (Vulkan / DirectX 12 / Metal) |
| `[desktop]` — `pywebview` | BSD-3-Clause | Optional frameless native desktop window wrapper for Human Mode (`uiforge ui --app`) |
| `[ocr]` — `rapidocr-onnxruntime` | Apache-2.0 | Optional local offline OCR for `import_screenshot` |
| `[video]` — `imageio-ffmpeg` | BSD-2-Clause (wrapper) + LGPL/GPL (FFmpeg binary) | Optional external CLI invoked via subprocess for MP4/WebM encoding |
| `[dev]` — `pytest`, `ruff` | MIT | Test runner and linter for development only |

---

## 3. Bundled Fonts (`src/uiforge_mcp/assets/fonts/`)

Every bundled font is distributed unmodified under the **SIL Open Font License, Version 1.1 (OFL-1.1)**, with its full `OFL.txt` license file included in its directory and packaged in built wheels. OFL-1.1 permits free commercial and open-source use, bundling, and embedding in rendered images/games, provided the font software itself is not sold on its own and Reserved Font Names are respected if modified.

| Font Family | Copyright & Upstream | License File | Reserved Font Name |
| --- | --- | --- | --- |
| **Bangers** | Copyright 2010 The Bangers Project Authors | `assets/fonts/bangers/OFL.txt` | None |
| **Barlow Condensed** | Copyright 2017 The Barlow Project Authors | `assets/fonts/barlowcondensed/OFL.txt` | None |
| **Bebas Neue** | Copyright 2010 Dharma Type | `assets/fonts/bebasneue/OFL.txt` | None |
| **Cinzel** | Copyright 2020 The Cinzel Project Authors | `assets/fonts/cinzel/OFL.txt` | None |
| **Fredoka** | Copyright 2016 The Fredoka Project Authors | `assets/fonts/fredoka/OFL.txt` | None |
| **Inter** | Copyright 2020 The Inter Project Authors | `assets/fonts/inter/OFL.txt` | None |
| **JetBrains Mono** | Copyright 2020 The JetBrains Mono Project Authors | `assets/fonts/jetbrainsmono/OFL.txt` | None |
| **Michroma** | Copyright 2011 The Michroma Project Authors | `assets/fonts/michroma/OFL.txt` | None |
| **Noto Sans** (Arabic, Bengali, Devanagari, Hebrew, Tamil, Thai) | Copyright 2022 The Noto Project Authors | `assets/fonts/noto/OFL.txt` | None |
| **Orbitron** | Copyright 2018 The Orbitron Project Authors | `assets/fonts/orbitron/OFL.txt` | `"Orbitron"` (distributed unmodified) |
| **Rajdhani** | Copyright 2014 Indian Type Foundry | `assets/fonts/rajdhani/OFL.txt` | None |

---

## 4. Published Graphics Algorithms & Trademarks

- Shading and tone-mapping equations in `src/uiforge_mcp/pbr.py` implement standard published computer graphics literature (Walter et al. GGX/Trowbridge-Reitz, Schlick Fresnel approximation, Heitz Smith height-correlated visibility, Narkowicz ACES filmic approximation).
- Product, engine, and device names mentioned in documentation or export targets (Unity, Unreal Engine, Godot, Roblox, Figma, Penpot, Pencil, Rive, React, Tailwind CSS, Qt, iPhone, Steam Deck, etc.) are trademarks of their respective owners; `uiforge-mcp` is an independent open-source project and is not affiliated with or endorsed by any of them.
