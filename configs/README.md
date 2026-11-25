# Multi-IDE MCP Setup Templates

Run the built-in CLI to auto-detect your GPU architecture and write/merge your IDE config automatically:

```bash
# 1. Inspect hardware GPU, active backend and installed engines/IDEs
game-ui-mcp doctor

# 2. Check or install the optimal GPU extra (auto | nvidia | amd | intel | apple | cpu)
game-ui-mcp install-gpu --arch auto
game-ui-mcp install-gpu --arch auto --apply

# 3. Auto-configure your AI IDE (merges safely without overwriting other MCP servers)
game-ui-mcp setup opencode --write
game-ui-mcp setup claude --write
game-ui-mcp setup vscode --scope project --write
game-ui-mcp setup visualstudio --write
game-ui-mcp setup antigravity --write
game-ui-mcp setup cursor --write
game-ui-mcp setup windsurf --write

# 4. ChatGPT (Streamable HTTP MCP server)
game-ui-mcp serve --transport http --host 127.0.0.1 --port 8765
```

## Ready JSON Snippets

### OpenCode v2 (`opencode.json` or `~/.config/opencode/opencode.json`)
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "game-ui": {
        "type": "local",
        "command": ["uvx", "--from", "git+https://github.com/TENETTE/game-ui-mcp", "game-ui-mcp"],
        "environment": { "GAME_UI_MCP_GPU": "auto" }
      }
    }
  }
}
```

### Visual Studio 2022 (17.14+) & Visual Studio 2026 (`%USERPROFILE%\.mcp.json` or `<repo>\.mcp.json`)
```json
{
  "servers": {
    "game-ui": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/TENETTE/game-ui-mcp", "game-ui-mcp"],
      "env": { "GAME_UI_MCP_GPU": "auto" }
    }
  }
}
```

### VS Code 2026 / Claude Code / Google Antigravity / Cursor / Windsurf (`mcpServers`)
```json
{
  "mcpServers": {
    "game-ui": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/TENETTE/game-ui-mcp", "game-ui-mcp"],
      "env": { "GAME_UI_MCP_GPU": "auto" }
    }
  }
}
```

> Replace `git+https://github.com/TENETTE/game-ui-mcp` with `"game-ui-mcp[nvidia] @ git+..."` (NVIDIA CUDA+WebGPU), `"game-ui-mcp[amd] @ git+..."`, `"game-ui-mcp[intel] @ git+..."`, or `"game-ui-mcp[apple] @ git+..."` to enable GPU acceleration for your hardware.
