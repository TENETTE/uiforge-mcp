# Multi-IDE MCP Setup Templates

Run the built-in CLI to auto-detect your GPU architecture and write/merge your IDE config automatically:

```bash
# 1. Inspect hardware GPU, active backend and installed engines/IDEs
uiforge-mcp doctor

# 2. Check or install the optimal GPU extra (auto | nvidia | amd | intel | apple | cpu)
uiforge-mcp install-gpu --arch auto
uiforge-mcp install-gpu --arch auto --apply

# 3. Auto-configure your AI IDE (merges safely without overwriting other MCP servers)
uiforge-mcp setup opencode --write
uiforge-mcp setup claude --write
uiforge-mcp setup vscode --scope project --write
uiforge-mcp setup visualstudio --write
uiforge-mcp setup antigravity --write
uiforge-mcp setup cursor --write
uiforge-mcp setup windsurf --write

# 4. ChatGPT (Streamable HTTP MCP server)
uiforge-mcp serve --transport http --host 127.0.0.1 --port 8765
```

## Ready JSON Snippets

### OpenCode v2 (`opencode.json` or `~/.config/opencode/opencode.json`)
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "uiforge": {
        "type": "local",
        "command": ["uvx", "--from", "git+https://github.com/TENETTE/uiforge-mcp", "uiforge-mcp"],
        "environment": { "UIFORGE_MCP_GPU": "auto" }
      }
    }
  }
}
```

### Visual Studio 2022 (17.14+) & Visual Studio 2026 (`%USERPROFILE%\.mcp.json` or `<repo>\.mcp.json`)
```json
{
  "servers": {
    "uiforge": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/TENETTE/uiforge-mcp", "uiforge-mcp"],
      "env": { "UIFORGE_MCP_GPU": "auto" }
    }
  }
}
```

### VS Code 2026 / Claude Code / Google Antigravity / Cursor / Windsurf (`mcpServers`)
```json
{
  "mcpServers": {
    "uiforge": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/TENETTE/uiforge-mcp", "uiforge-mcp"],
      "env": { "UIFORGE_MCP_GPU": "auto" }
    }
  }
}
```

> Replace `git+https://github.com/TENETTE/uiforge-mcp` with `"uiforge-mcp[nvidia] @ git+..."` (NVIDIA CUDA+WebGPU), `"uiforge-mcp[amd] @ git+..."`, `"uiforge-mcp[intel] @ git+..."`, or `"uiforge-mcp[apple] @ git+..."` to enable GPU acceleration for your hardware.
