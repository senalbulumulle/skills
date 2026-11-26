---
name: hybrid
description: Send a request through hybrid-llms so the local language model (from ~/Documents/Models) and a cloud model work together. Use when the user writes @hybrid or /hybrid, or asks to use the hybrid server, the local model, or to save cloud tokens.
---

# hybrid

1. Strip `@hybrid` from the request. Gather any files it refers to; pass their contents as `context`.
2. Call the `hybrid` tool of the `hybrid` MCP server (`mcp__hybrid__hybrid`):
   - `prompt`: the request.
   - `strategy`: `auto` (default), `local`, `cloud`, `cascade`, `draft-review`, `plan-execute`, or `compress` (large `context`).
   - `cloud`: omit (you are the cloud model) unless the user names `claude`, `codex`, or `gemini`.
3. If the result reports needs_host_review, check the answer and fix it.
4. Reply with the answer and the `[hybrid]` summary line.

If the tool is missing, tell the user to run `scripts/install.sh` from the hybrid-llms folder. If it errors, call `mcp__hybrid__hybrid_status` and report what it shows.

Done when: the reply came from the `hybrid` tool (or reports its error and status) and includes the summary line.
