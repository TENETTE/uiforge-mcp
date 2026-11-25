# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue:
use **Security → Report a vulnerability** on this repository (GitHub private vulnerability reporting).
Describe what an attacker can do, the steps or input that trigger it, and the version (`pyproject.toml`).
You should get a first reply within a week. Please give a reasonable time to ship a fix before
disclosing it publicly.

## What counts

uiforge-mcp runs locally and is driven by an AI model, which may have read untrusted content
(web pages, SVG files, documents) and can be steered by it. Issues worth reporting include:

- a tool argument that leads to code execution, including code injected into generated engine
  scripts (Unity C#, Unreal Python, Godot resources, Roblox Luau) that the user later runs
- escaping the shader-fill sandbox (it must only compute numbers)
- reading or writing files outside what a tool is documented to touch
- input that crashes the server or exhausts memory despite the documented limits
- XML / SVG parsing attacks (entity expansion, external entities)

## Supported versions

Only the latest version on the default branch receives fixes.
