# Contributing to UIForge (`uiforge-mcp`)

Thanks for helping make UIForge better! Bug reports, real showcases, engine improvements, Studio UI polish, and pull requests are welcome.

## Development Setup

```bash
git clone https://github.com/TENETTE/uiforge-mcp
cd uiforge-mcp
uv venv && uv pip install -e ".[dev]"
uv run pytest -q
uv run ruff check src tests
```

Plain `python -m venv .venv` + `pip install -e ".[dev]"` works as well (Python 3.10+).

## Architecture Rules

- **Shared core, zero duplication:** Business logic, rendering, widgets, and exporters belong in the MCP-independent core (`core.py`, `store.py`, `render.py`, `pbr.py`, `widgets.py`, `export.py`, `tools_delivery.py`, `desktop_export.py`, `webexport.py`). Never duplicate engine logic separately for MCP vs Studio UI.
- **Keep Human Mode MCP-free at runtime:** `uiforge` / `uiforge ui` must continue to boot and execute core operations cleanly even if the `mcp` package is absent (`MCP_AVAILABLE = False`).
- **Maintain Combined Mode safety:** Any new state mutation in `Store` must hold `self._lock`, persist atomically via `_atomic_write`, and update `_disk_stamps` / `_notify()` so in-process and cross-process Combined Mode stay consistent.
- **Stay local and deterministic:** Zero outbound network calls, zero diffusion/image-generation models, and no heavy mandatory dependencies without discussion in an issue first.

## Before Opening a Pull Request

- Run the full test suite (`pytest -q`) and `ruff check src tests`, and add tests covering new behaviour or bug fixes across relevant modes (`mcp`, `ui`, `combined`).
- Tool errors must explain clearly what went wrong and how to fix it (see `tests/test_tool_errors.py`).
- Any value interpolated into generated scripts (Unreal Python, Unity C#, Godot GDScript/`.tscn`, Roblox Luau, WPF/Avalonia/WinUI XAML, Qt QML, Dear ImGui C++, HTML/TSX) must be validated or escaped (see `tests/test_security.py`).
- Only add fonts or media under an open license (e.g. MIT, SIL OFL-1.1) and include the license file alongside them + update `THIRD_PARTY_LICENSES.md`.
- If a change affects CLI flags, modes, or tools, update docstrings, `README.md`, `README.tr.md`, `docs/GUIDE.md`, `skill/uiforge-mcp/SKILL.md`, and `llms.txt` as needed.

## Reporting Bugs

Open an issue with the tool calls or UI steps (plus canvas JSON from `get_canvas` if applicable), what you expected, and what happened. Report security vulnerabilities privately via [SECURITY.md](SECURITY.md).

By contributing you agree that your work is released under the [MIT License](LICENSE).
