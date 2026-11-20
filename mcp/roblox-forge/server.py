#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==2.3.0"]
# ///
"""roblox-forge: an MCP server with offline tools for building Roblox games with Rojo.

It complements Roblox Studio's built-in MCP server (live editing, play testing, console output)
with checks that work on the project files: scaffolding, Rojo project validation, remote security
audit, a map of every remote, a game-feel audit, a polish audit and effect recipes checked against a
catalog of Roblox Studio's API, paid-random-item odds, DataStore budget, and Luau type checking.

Run: uv run --script server.py   (stdio transport; register it with Claude Code or Codex, see README.md)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import forge  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

server = MCPServer(
    name="roblox-forge",
    version="1.0.0",
    instructions=(
        "Offline tools for Rojo-based Roblox projects. Pass absolute paths. Use check_project after "
        "changing the project layout, map_remotes and audit_remotes after adding or renaming remotes, "
        "audit_feel and audit_polish after changing gameplay, effects, sounds, or UI, vfx_recipe for particle, "
        "trail, and beam effects, check_odds for any paid random item, datastore_budget "
        "when changing save frequency, and luau_check on pure modules. For live "
        "Studio actions (play, console output, running code), use Roblox Studio's own MCP server."
    ),
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


@server.tool(annotations=WRITES)
def create_project(path: str, name: str | None = None) -> dict:
    """Create a Rojo project for a Roblox game at `path` (must not exist or be empty): project file,
    strict .luaurc, server/client entry points, PlayerData (session-locked saves) and RemoteGuard
    (validated, rate-limited remotes). `name` defaults to the folder name."""
    return forge.create_project(path, name)


@server.tool(annotations=READ_ONLY)
def check_project(path: str, build: bool = True) -> dict:
    """Validate a Rojo project (folder or *.project.json): JSON shape, missing $path targets, multiple
    init scripts in one folder, Scripts or LocalScripts mapped where Roblox won't run them, duplicate
    instance names, and a real `rojo build` when Rojo is installed and `build` is true."""
    return forge.check_project(path, build)


@server.tool(annotations=READ_ONLY)
def audit_remotes(path: str) -> dict:
    """Scan Luau files under `path` for RemoteEvent/RemoteFunction handlers without a validation wrapper,
    InvokeClient use, and FireServer calls that send values the server should decide. Heuristic."""
    return forge.audit_remotes(path)


@server.tool(annotations=READ_ONLY)
def map_remotes(path: str) -> dict:
    """List every RemoteEvent and RemoteFunction in a Rojo project with where it is declared, fired, and
    handled. Flags remotes fired with no handler on the other side, handlers nothing fires, Fire/Invoke
    calls on the wrong remote class, and names used in code but never declared. Heuristic name matching."""
    return forge.map_remotes(path)


@server.tool(annotations=READ_ONLY)
def audit_feel(path: str) -> dict:
    """Find player actions (button presses, input bindings, ProximityPrompts, touches, server results)
    whose handlers give no feedback: no sound, tween, particles, animation, camera, or UI change. Follows
    functions in the same file; handlers that call required modules are listed as unverified. Heuristic."""
    return forge.audit_feel(path)


@server.tool(annotations=READ_ONLY)
def audit_polish(path: str) -> dict:
    """Check effect, sound, and UI code against a catalog of Roblox Studio's API: members that don't exist on
    the created class, Color3 or numbers given to sequence properties, deprecated members, values outside
    Studio's editor ranges, missing built-in files, emitters left at default look, sounds with no SoundId,
    scaled text with no size limit, and dated fonts. Heuristic."""
    return forge.audit_polish(path)


@server.tool(annotations=READ_ONLY)
def vfx_recipe(effect: str, color: str | None = None) -> dict:
    """Luau code for a ready-made effect: hit_spark, pickup_glow, level_up, smoke_puff, dash_trail, or
    magic_beam. Uses only members, value types, ranges, and built-in textures from the Roblox Studio catalog.
    `color` is a hex color such as "#ff8800" (each effect has a default)."""
    return forge.vfx_recipe(effect, color)


@server.tool(annotations=READ_ONLY)
def check_odds(outcomes: list[dict], rounded: bool = False) -> dict:
    """Check paid random item odds against Roblox policy. `outcomes` is a list of
    {"name": str, "percent": number}; percentages must sum to exactly 100, or be within rounding error
    when `rounded` is true (then a disclaimer is required)."""
    return forge.check_odds(outcomes, rounded)


@server.tool(annotations=READ_ONLY)
def datastore_budget(players: int, autosave_seconds: float = 60, joins_per_minute: float | None = None,
                     extra_reads_per_minute: float = 0, extra_writes_per_minute: float = 0) -> dict:
    """Estimate one server's DataStore requests per minute (PlayerData-style UpdateAsync saves) against
    the documented default per-server budget, and report usage as a percentage."""
    return forge.datastore_budget(players, autosave_seconds, joins_per_minute,
                                  extra_reads_per_minute, extra_writes_per_minute)


@server.tool(annotations=READ_ONLY)
def luau_check(paths: list[str], mode: str = "strict") -> dict:
    """Type-check and lint .luau/.lua files or folders with luau-analyze (if installed). Best for pure
    modules; engine scripts report unknown Roblox globals without Roblox type definitions."""
    return forge.luau_check(paths, mode)


if __name__ == "__main__":
    server.run()
