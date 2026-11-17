# roblox-forge MCP server

Offline tools for building Roblox games with Rojo. It complements Roblox Studio's built-in MCP server, which handles live work in Studio (running code, play testing, console output, screenshots). roblox-forge works on your project files, so it runs anywhere, including Codex's sandbox and CI.

| Tool | What it does | Changes files? |
| --- | --- | --- |
| `create_project` | Scaffolds a Rojo project from the `roblox-scripting` template (session-locked saves, validated remotes, entry scripts) | yes, in an empty or new folder only |
| `check_project` | Validates `default.project.json`: missing `$path` targets, multiple init scripts in one folder, Scripts or LocalScripts mapped where Roblox won't run them, duplicate names, plus a real `rojo build` if Rojo is installed | no |
| `audit_remotes` | Flags remote handlers without a validation wrapper, `InvokeClient` use, and `FireServer` calls that send values the server should decide (heuristic) | no |
| `check_odds` | Checks paid random item odds against Roblox policy (all outcomes, percentages summing to 100%, rounding disclaimer) | no |
| `datastore_budget` | Estimates a server's DataStore requests per minute against the documented default budget | no |
| `luau_check` | Runs `luau-analyze` (strict by default) on files or folders | no |

## Requirements
- [uv](https://docs.astral.sh/uv/). On first launch it installs Python 3.10+ (if needed) and the pinned MCP SDK (`mcp==2.3.0`) from the script header.
- Optional: [Rojo](https://rojo.space) for build checks and [Luau](https://github.com/luau-lang/luau/releases) for `luau_check`.

Use absolute paths in tool calls. Replace `/path/to/skills` below with this repository's location.

## Claude Code
```sh
claude mcp add --scope user roblox-forge -- uv run --quiet --script /path/to/skills/mcp/roblox-forge/server.py
```
Or share it with a game project by adding `.mcp.json` to that project's root:
```json
{
  "mcpServers": {
    "roblox-forge": {
      "command": "uv",
      "args": ["run", "--quiet", "--script", "/path/to/skills/mcp/roblox-forge/server.py"]
    }
  }
}
```
Check with `claude mcp list`, or `/mcp` inside a session.

## Codex
```sh
codex mcp add roblox-forge -- uv run --quiet --script /path/to/skills/mcp/roblox-forge/server.py
```
The first launch downloads the SDK, which can exceed Codex's default startup timeout. Raise it in `~/.codex/config.toml`:
```toml
[mcp_servers.roblox-forge]
command = "uv"
args = ["run", "--quiet", "--script", "/path/to/skills/mcp/roblox-forge/server.py"]
startup_timeout_sec = 60
tool_timeout_sec = 180
```
`tool_timeout_sec` leaves room for `check_project` builds and `luau_check` on large projects. Check with `codex mcp list`, or `/mcp` inside a session.

## Use with the Roblox Studio MCP server
Run both: Studio's server for live actions, roblox-forge for file checks. Enable Studio's from the Assistant panel (Manage MCP Servers → Enable Studio as MCP server); Roblox's docs list the connect command for each client.

## Development
- Tool logic lives in `forge.py` (standard library only); `server.py` only registers tools.
- Tests: `python3 -m unittest tools/test_roblox_forge.py` (logic) and
  `uv run --python 3.12 --with mcp==2.3.0 python tools/mcp_smoke.py` (real stdio session).
