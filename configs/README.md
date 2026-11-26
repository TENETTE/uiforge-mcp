# Multi-Mode Launch & Multi-IDE MCP Setup Templates

UIForge runs in **three modes** over the exact same shared engine and workspace. Choose the mode you need — no AI IDE or MCP client is required for Human Mode.

---

## 1. Quick Launch by Mode

```bash
# Human Mode — standalone Studio UI (no MCP client or AI IDE required)
uiforge
uiforge ui --app                       # Frameless native window (pywebview or Edge/Chrome --app)
uiforge ui --workspace ./my-project/.uiforge

# MCP Mode — headless MCP server only (stdio by default)
uiforge-mcp
uiforge-mcp mcp --toolset game --compact

# Combined Mode — Studio UI + MCP server live on the same synced workspace
uiforge combined
uiforge serve --mode combined --ui-port 8766

# Inspect GPU hardware, active backends, modes & tool token footprint
uiforge-mcp doctor

# Inspect or install the optimal GPU extra (auto | nvidia | amd | intel | apple | cpu)
uiforge-mcp install-gpu --arch auto
uiforge-mcp install-gpu --arch auto --apply
```

---

## 2. One-Command MCP Client Auto-Configuration

All `setup` commands auto-detect your GPU architecture and **safely merge** into existing config files without overwriting other MCP servers:

```bash
uiforge-mcp setup opencode --write
uiforge-mcp setup claude --write
uiforge-mcp setup codex --write
uiforge-mcp setup vscode --scope project --write
uiforge-mcp setup visualstudio --write
uiforge-mcp setup antigravity --write
uiforge-mcp setup cursor --write
uiforge-mcp setup windsurf --write
```

Add `--local-python` if you installed UIForge into a local virtual environment and want the config to invoke your local Python directly instead of `uvx`.

---

## 3. Manual Configuration Templates (Provider-Neutral)

> To enable GPU acceleration, pass `"--from", "uiforge-mcp[nvidia]", "uiforge-mcp"` (NVIDIA CUDA 12 + WebGPU) or `"uiforge-mcp[amd]"` / `"uiforge-mcp[intel]"` / `"uiforge-mcp[apple]"` (WebGPU).
>
> To run **Combined Mode** automatically whenever your AI client connects, append `"combined"` (or `"serve", "--mode", "combined"`) to `args` / `command`. To cut LLM token usage by up to 77%, append `"mcp", "--toolset", "core", "--compact"` (or `game` / `desktop` / `web`).

### OpenCode v2 (`opencode.json` or `~/.config/opencode/opencode.json`)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "uiforge": {
        "type": "local",
        "command": ["uvx", "uiforge-mcp"],
        "environment": { "UIFORGE_MCP_GPU": "auto" }
      }
    }
  }
}
```

### OpenAI Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.uiforge]
command = "uvx"
args = ["uiforge-mcp"]
```

### Claude Code (`~/.claude.json` or `<repo>/.mcp.json`)

```bash
claude mcp add uiforge -s user -- uvx uiforge-mcp
```

Or in JSON:

```json
{
  "mcpServers": {
    "uiforge": {
      "command": "uvx",
      "args": ["uiforge-mcp"],
      "env": { "UIFORGE_MCP_GPU": "auto" }
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
      "args": ["uiforge-mcp"],
      "env": { "UIFORGE_MCP_GPU": "auto" }
    }
  }
}
```

### VS Code Copilot (`<repo>/.mcp.json` native or `.vscode/mcp.json` legacy)

```json
{
  "mcpServers": {
    "uiforge": {
      "type": "stdio",
      "command": "uvx",
      "args": ["uiforge-mcp"],
      "env": { "UIFORGE_MCP_GPU": "auto" }
    }
  }
}
```

*(Legacy `.vscode/mcp.json` uses `"servers"` as the top-level key instead of `"mcpServers"`.)*

### Google Antigravity (`~/.gemini/antigravity/mcp_config.json`), Cursor (`~/.cursor/mcp.json`), Windsurf (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "uiforge": {
      "command": "uvx",
      "args": ["uiforge-mcp"],
      "env": { "UIFORGE_MCP_GPU": "auto" }
    }
  }
}
```

### Remote Streamable HTTP Clients (ChatGPT Apps/Connectors & Custom HTTP Agents)

Streamable HTTP automatically enables export sandboxing (`--sandbox-exports`) and requires `--auth-token` (or `UIFORGE_MCP_AUTH_TOKEN`) whenever binding beyond `127.0.0.1`:

```bash
# Localhost with Bearer authentication (recommended for any tunneled connector)
uiforge-mcp serve --transport http --host 127.0.0.1 --port 8765 --auth-token YOUR_SECRET_TOKEN

# Combined Mode with Studio UI on 8766 + authenticated Streamable HTTP MCP on 8765
uiforge combined --transport http --host 127.0.0.1 --port 8765 --ui-port 8766 --auth-token YOUR_SECRET_TOKEN
```

Endpoint URL: `http://127.0.0.1:8765/mcp` (expose over your own HTTPS tunnel when connecting from a web-hosted MCP client). Send header `Authorization: Bearer YOUR_SECRET_TOKEN`.
