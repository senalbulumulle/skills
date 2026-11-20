# roblox-forge MCP server

Offline tools for building Roblox games with Rojo. It complements Roblox Studio's built-in MCP server, which handles live work in Studio (running code, play testing, console output, screenshots). roblox-forge works on your project files, so it runs anywhere, including Codex's sandbox and CI.

| Tool | What it does | Changes files? |
| --- | --- | --- |
| `create_project` | Scaffolds a Rojo project from the `roblox-scripting` template (session-locked saves, validated remotes, entry scripts) | yes, in an empty or new folder only |
| `check_project` | Validates `default.project.json`: missing `$path` targets, multiple init scripts in one folder, Scripts or LocalScripts mapped where Roblox won't run them, duplicate names, plus a real `rojo build` if Rojo is installed | no |
| `map_remotes` | Lists every RemoteEvent and RemoteFunction with where it is declared, fired, and handled. Flags remotes fired with no handler on the other side, handlers nothing fires, `Fire`/`Invoke` on the wrong remote class, and names used in code but never declared (heuristic) | no |
| `audit_remotes` | Flags remote handlers without a validation wrapper, `InvokeClient` use, and `FireServer` calls that send values the server should decide (heuristic) | no |
| `audit_feel` | Finds player actions (button presses, input bindings, ProximityPrompts, touches, server results) whose handlers give no feedback: no sound, tween, particles, animation, camera, or UI change. Follows functions in the same file; handlers that call required modules are listed as unverified (heuristic) | no |
| `audit_polish` | Checks effect, sound, and UI code against a catalog of Roblox Studio's API: members that don't exist on the created class, a `Color3` or number given to a sequence property (`ParticleEmitter.Color`, `Lifetime`, ...), deprecated members, values outside Studio's editor ranges, `rbxasset://` paths that aren't built in, emitters left at their default look, sounds with no `SoundId`, scaled text with no size limit, and dated fonts (heuristic) | no |
| `vfx_recipe` | Returns Luau for a ready-made effect (`hit_spark`, `pickup_glow`, `level_up`, `smoke_puff`, `dash_trail`, `magic_beam`) in a chosen color. Every property, value type, and range is checked against the catalog, and textures are built-in files, so it needs no upload | no |
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
`scripts/codex/install-codex-mcp.sh` registers it (and creative-director) and downloads the SDK ahead of the first session. Or by hand:
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
Run both: Studio's server for live actions, roblox-forge for file checks. Enable Studio's from the Assistant panel (Manage MCP Servers → Enable Studio as MCP server); Roblox's docs list the connect command for each client. On macOS the server is `/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP`, a stdio proxy to the running Studio. In Studio 0.748 it lists 40 tools; the polish workflow uses `search_asset` and `insert_asset` for real sounds and models, `start_stop_play`, `screen_capture`, and `get_console_output`.

## The Studio catalog
`audit_polish` and `vfx_recipe` read `catalog.json`: member names, editor ranges, and deprecations for 48 effect, sound, and UI classes, plus the built-in particle textures and sounds. `studio_catalog.py` builds it from a local Roblox Studio install (`content/api_docs`, `ReflectionMetadata.xml`, and `content/`) and writes the same facts to `skills/roblox-gameplay/references/effects-catalog.md`. It keeps names, numbers, and paths only, never Roblox's documentation text or asset files. After a Studio update:
```sh
python3 mcp/roblox-forge/studio_catalog.py            # rewrite both files
python3 mcp/roblox-forge/studio_catalog.py --check    # exit 1 if they are out of date
```
Value types for sequence properties aren't in Studio's files, so `VALUE_TYPES` in `forge.py` lists them by hand (the Codex hooks keep an identical copy).

## Development
- Tool logic lives in `forge.py` (standard library only); `server.py` only registers tools; `studio_catalog.py` builds `catalog.json`.
- Tests: `python3 -m unittest tools/test_roblox_forge.py` (logic) and
  `uv run --python 3.12 --with mcp==2.3.0 python tools/mcp_smoke.py` (real stdio session).
