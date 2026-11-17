#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==2.3.0"]
# ///
"""roblox-forge: an MCP server with offline tools for building Roblox games with Rojo.

It complements Roblox Studio's built-in MCP server (live editing, play testing, console output)
with checks that work on the project files: scaffolding, Rojo project validation, remote security
audit, paid-random-item odds, DataStore budget, and Luau type checking.

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
        "changing the project layout, audit_remotes before publishing, check_odds for any paid random "
        "item, datastore_budget when changing save frequency, and luau_check on pure modules. For live "
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
