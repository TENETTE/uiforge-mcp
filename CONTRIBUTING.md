# Contributing

Thanks for helping. Bug reports, examples and pull requests are welcome.

## Setup

```bash
git clone https://github.com/TENETTE/uiforge-mcp
cd uiforge-mcp
uv venv && uv pip install -e ".[dev]"
uv run pytest
```

Plain `python -m venv .venv` + `pip install -e ".[dev]"` works too (Python 3.10+).

## Before opening a pull request

- Run the whole test suite (`pytest`) and add a test for new behaviour or a fixed bug.
- Keep the server local and deterministic: no network access, no image-generation models, no new
  heavy dependencies without discussing it in an issue first.
- Tool errors must tell the model what was wrong and how to fix it (see `tests/test_tool_errors.py`).
- Values that end up inside generated scripts (C#, Python, Luau, GDScript, `.tres`, HTML) must be
  validated or escaped (see `tests/test_security.py`).
- Only add fonts or images you have the right to share under an open licence, and include the licence
  file next to them.
- If a change affects how the model should use a tool, update its docstring, `docs/GUIDE.md` and
  `skill/uiforge-mcp/SKILL.md`.

## Reporting bugs

Open an issue with the tool calls (or the canvas JSON from `get_canvas`) that reproduce it, what you
expected and what happened. Security problems go through [SECURITY.md](SECURITY.md) instead.

By contributing you agree that your work is released under the [MIT licence](LICENSE).
