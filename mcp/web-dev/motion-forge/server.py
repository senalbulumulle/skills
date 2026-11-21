#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==2.3.0"]
# ///
"""motion-forge: an MCP server with reusable, dependency-free Web Components for motion-rich web UI.

Components: a WebGL gradient field and a 3D tilt card, scroll parallax, a pinned scroll-scrubbed scene, and
staggered reveals, a magnetic button and a pointer spotlight, and text scramble and split-text headlines.
Each handles reduced motion, pauses offscreen, and cleans up after itself. Tools browse and install them,
build a self-contained showcase page, and audit a project's own motion code.

Run: uv run --script server.py   (stdio transport; register it with Claude Code, Codex, or Gemini CLI, see README.md)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motion  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

server = MCPServer(
    name="motion-forge",
    version="1.0.0",
    instructions=(
        "Reusable Web Components for motion-rich web UI: WebGL and 3D, scroll and motion graphics, tactile "
        "micro-interactions, and expressive hero text. Pass absolute paths. Call list_components, then "
        "get_component for the attributes, example markup, and notes of each one you use; install_components "
        "copies the files into the project unchanged, so build with them instead of rewriting them. Use "
        "build_showcase to preview components in a browser. Run audit_motion on the project's motion code "
        "after changing it, and fix its warn findings."
    ),
)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


@server.tool(annotations=READ_ONLY)
def list_components(category: str | None = None) -> dict:
    """List the components with their tag and a one-line summary. `category` filters to one of: webgl-3d,
    scroll-motion, tactile, hero-text."""
    return motion.list_components(category)


@server.tool(annotations=READ_ONLY)
def get_component(name: str, include_source: bool = True) -> dict:
    """One component's tag, attributes, CSS custom properties, data attributes, API, notes, example markup,
    framework notes, and (unless `include_source` is false) its full JavaScript source."""
    return motion.get_component(name, include_source)


@server.tool(annotations=WRITES)
def install_components(names: list[str], out: str, overwrite: bool = False) -> dict:
    """Copy component files (one ES module each, no dependencies) into the folder `out`, creating it. `names`
    lists components, or ["all"]. Leaves an existing different file alone unless `overwrite` is true."""
    return motion.install_components(names, out, overwrite)


@server.tool(annotations=WRITES)
def build_showcase(out: str, names: list[str] | None = None) -> dict:
    """Write a self-contained HTML page that demonstrates the components with their markup, for previewing
    in a browser. `out` is an .html path or a folder (motion-showcase.html inside it); `names` defaults to
    every component. Replaces only a page this tool wrote."""
    return motion.build_showcase(out, names)


@server.tool(annotations=READ_ONLY)
def audit_motion(paths: list[str]) -> dict:
    """Scan CSS, HTML, JS/TS, Vue, Svelte, and Astro files or folders for motion problems: no
    prefers-reduced-motion handling, transitions or keyframes on layout properties, transition: all, wheel
    or touch listeners that block scrolling, animation loops that never stop, WebGL without context-loss
    handling or with an uncapped pixel ratio, hover effects with no focus style, will-change overuse, and
    layout writes in animation code. Skips dependency and build folders. Heuristic."""
    return motion.audit_motion(paths)


if __name__ == "__main__":
    server.run()
