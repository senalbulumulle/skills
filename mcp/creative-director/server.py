#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==2.3.0"]
# ///
"""creative-director: an MCP server that keeps game and software work specific instead of generic.

Tools: concept_seeds (brainstorm past the first idea), review_design (check a game design doc before
building), find_slop (find unfinished or generic content before finishing). Engine-agnostic: works
for Roblox, Unreal, Unity, Godot, web games, and ordinary software projects.

Run: uv run --script server.py   (stdio transport; register it with Claude Code or Codex, see README.md)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import director  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

server = MCPServer(
    name="creative-director",
    version="1.0.0",
    instructions=(
        "Checks for creative quality in games and software. Pass absolute paths. For a new game or feature with "
        "creative freedom, call concept_seeds and compare its constraints with your first idea; write the design "
        "and run review_design on it before building; run find_slop on the files you changed before you finish. "
        "Findings are heuristics: fix real problems, and say why when one is intended."
    ),
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
RANDOM = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


@server.tool(annotations=RANDOM)
def concept_seeds(count: int = 3, seed: int | None = None, genre: str | None = None) -> dict:
    """Random concept constraints for brainstorming: each has a core verb, a twist, a setting, and a feeling.
    `count` is 1-10. Pass the returned `seed` again to get the same set. `genre` adds a fit instruction."""
    return director.concept_seeds(count, seed, genre)


@server.tool(annotations=READ_ONLY)
def review_design(text: str | None = None, path: str | None = None) -> dict:
    """Check a game design doc (Markdown `text`, or a file `path`; pass one) for headings that answer: player
    fantasy, core loop, hook, controls, win and fail states, first minute, feedback, progression, scope.
    Also reports vague phrases, unfinished content, and how many tuning numbers it gives."""
    return director.review_design(text, path)


@server.tool(annotations=READ_ONLY)
def find_slop(paths: list[str], include_tests: bool = False) -> dict:
    """Scan files or folders for unfinished or generic content: filler text, stubs left in place of code,
    marker comments standing in for work, stand-in UI text, generic titles, and (in Markdown and text files)
    vague marketing phrases. Skips dependency, build, and engine cache folders, and test files by default."""
    return director.find_slop(paths, include_tests)


if __name__ == "__main__":
    server.run()
