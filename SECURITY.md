# Security Policy

## Reporting a Vulnerability

Please report security problems privately rather than opening a public issue:
use **Security → Report a vulnerability** on this repository (GitHub private vulnerability reporting).
Describe what an attacker can achieve, the steps or inputs that trigger it, and the version (`pyproject.toml`).
You should receive an initial response within a week. Please allow reasonable time to ship a fix before public disclosure.

## Built-in Security Defenses

UIForge (`uiforge-mcp`) runs 100% locally and can be driven by humans (Studio UI) or by AI models (MCP Mode / Combined Mode) that may have processed untrusted inputs (web pages, SVGs, screenshots, documents). Built-in safeguards include:

- **Offline by default:** Zero outbound network requests. Human Studio UI (`uiforge ui`) and `live_preview` bind exclusively to `127.0.0.1` loopback.
- **Streamable HTTP authentication & bind guard:** Non-loopback HTTP binds (e.g. `0.0.0.0`) are refused unless `--auth-token` (`UIFORGE_MCP_AUTH_TOKEN`) is supplied. Bearer tokens are checked with constant-time `hmac.compare_digest` via `BearerAuthMiddleware`.
- **Export path sandboxing:** `--sandbox-exports` (`UIFORGE_MCP_SANDBOX_EXPORTS=1`, auto-enabled on HTTP transport) confines all file writes strictly inside `<workspace>/exports/`. Studio UI's `/api/export_preview` endpoint independently resolves and rejects any path outside `<workspace>/exports/`.
- **Sandboxed expression & shader ASTs:** Both `shader.py` and `binding.py` validate ASTs against strict whitelists (no imports, attributes, subscripts, or loops), cap exponentiation (`<= 64`) and string repetition (`<= 4096`), and enforce pixel/work budgets before execution.
- **Injection-safe code generation:** Identifiers and engine paths embedded into generated Unity C#, Unreal Python, Godot GDScript/`.tscn`, Roblox Luau, C# XAML, Qt QML, Dear ImGui C++, and HTML/React files are validated or safely escaped (`json.loads` / XML / HTML escaping). Generated scripts are written to disk and never executed by the server.
- **Hardened SVG & atomic persistence:** SVG `DOCTYPE` and `ENTITY` declarations are rejected. `Store` writes JSON atomically via per-call `tempfile.mkstemp` + `os.fsync` + `os.replace` under a re-entrant lock (`RLock`).

## What Counts as a Vulnerability

- Any tool argument or Studio API request leading to arbitrary code execution, including script injection into generated engine/desktop/web outputs.
- Escaping the `shader.py` or `binding.py` AST sandboxes.
- Bypassing `--sandbox-exports`, `/api/export_preview` confinement, or HTTP Bearer authentication.
- Reading or writing files outside documented workspace/export paths.
- Input causing unbounded memory allocation, crash, or DoS despite documented limits.
- XML/SVG entity expansion or external entity attacks.

## Supported Versions

Only the latest release on the `main` branch receives security fixes.
