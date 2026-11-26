---
name: hybrid
description: Send a request through hybrid-llms so the local language model (from ~/Documents/Models) and a cloud model work together. Use when the user writes @hybrid or $hybrid, or asks to use the hybrid server, the local model, or to save cloud tokens.
---

# hybrid

1. Strip `@hybrid` / `$hybrid` from the request. Read any files it refers to and pass their contents as `context`.
2. Call the `hybrid` tool of the `hybrid` MCP server:
   - `prompt`: the request.
   - `strategy`: `auto` (default), `local`, `cloud`, `cascade`, `draft-review`, `plan-execute`, or `compress` (large `context`).
   - `cloud`: omit (you are the cloud model) unless the user names `claude`, `codex`, or `gemini`.
3. If the result reports needs_host_review, check the answer and fix it.
4. Reply with the answer and the `[hybrid]` summary line.

If the tool is missing, tell the user to run `scripts/install.sh` from the hybrid-llms folder and restart Codex. If it errors, call `hybrid_status` and report what it shows.

Done when: the reply came from the `hybrid` tool (or reports its error and status) and includes the summary line.
