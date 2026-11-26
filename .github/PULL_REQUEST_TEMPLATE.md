## What and why

<!-- What does this change add or fix, and which mode(s) does it affect (Human UI / MCP / Combined)? -->

## Checks

- [ ] `pytest -q` and `ruff check src tests` pass, and new behaviour has tests
- [ ] Shared core engine reused cleanly (no duplicated logic between Studio UI and MCP; Human Mode works without `mcp`)
- [ ] Values written into generated scripts (Unreal, Unity, Godot, Roblox, .NET, C++, Web/React) are validated or escaped
- [ ] Docs (`README.md`, `README.tr.md`, `docs/GUIDE.md`, `skill/uiforge-mcp/SKILL.md`, `llms.txt`) updated if user- or agent-facing behaviour changed
- [ ] Any newly added fonts or assets include an open license file and attribution in `THIRD_PARTY_LICENSES.md`
