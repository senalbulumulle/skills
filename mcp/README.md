# MCP servers

Servers are grouped by use case under `mcp/<category>/<name>/`, using the same category names as `skills/`. Each server's README covers setup for Claude Code and Codex.

| Category | Server | What it does | Pairs with |
| --- | --- | --- | --- |
| `web-dev` | [`motion-forge`](web-dev/motion-forge/README.md) | Dependency-free Web Components for motion-rich UI (WebGL, scroll, tactile, text), a showcase builder, and a motion audit | web front ends |

Register the servers in one category with Codex:

```sh
scripts/codex/install-codex-mcp.sh -c web-dev
```

To add a server, create `mcp/<category>/<name>/` with tool logic in a standard-library module, a thin `server.py`, and a README, add a row here, and add a stdio check to `tools/mcp_smoke.py`. The Codex installer finds servers by folder, so a new category needs no other registration. `tools/test_mcp_layout.py` fails if a server is missing from this table or the smoke test.
