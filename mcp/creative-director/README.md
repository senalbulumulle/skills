# creative-director MCP server

Checks that keep game and software work specific instead of generic. Works with any engine (Roblox, Unreal, Unity, Godot, web) and with ordinary software projects. It changes no files.

| Tool | What it does |
| --- | --- |
| `concept_seeds` | Random, reproducible concept constraints (a core verb, a twist, a setting, a feeling) for brainstorming past the first obvious idea |
| `review_design` | Checks a game design doc for headings (or `**Label:**` lines) covering fantasy, core loop, hook, controls, win and fail, first minute, feedback, progression, and scope. With `platform: "roblox"` it checks a Roblox brief instead (hook, first minute, loops, social hook, devices, controls, closest existing experiences, monetization, scope) and asks for odds when random items are mentioned. Also flags vague marketing phrases, unfinished content, and a lack of tuning numbers |
| `find_slop` | Scans files or folders for unfinished or generic content: filler text, stubs left in place of code, marker comments standing in for work, stand-in UI text, generic titles, Roblox asset IDs that point at nothing, Roblox's default UI labels, and vague phrases in Markdown and text files. Skips dependency, build, engine-cache, and test folders |

All checks are word-list heuristics. They point the agent at likely problems, and the agent decides. The Codex game hooks run the same unfinished-content rules at `Stop`, and a test keeps both rule sets identical.

## Requirements

- [uv](https://docs.astral.sh/uv/). On first launch it installs Python 3.10+ (if needed) and the pinned MCP SDK (`mcp==2.3.0`) from the script header.

Use absolute paths in tool calls. Replace `/path/to/skills` below with this repository's location.

## Codex

```sh
scripts/codex/install-codex-mcp.sh   # registers it and downloads the SDK ahead of the first session
```

Or by hand:
```sh
codex mcp add creative-director -- uv run --quiet --script /path/to/skills/mcp/creative-director/server.py
```
Check with `codex mcp list`, or `/mcp` inside a session.

## Claude Code

```sh
claude mcp add --scope user creative-director -- uv run --quiet --script /path/to/skills/mcp/creative-director/server.py
```

## Development

- Tool logic lives in `director.py` (standard library only); `server.py` only registers tools.
- Tests: `python3 -m unittest tools/test_creative_director.py` (logic) and
  `uv run --python 3.12 --with mcp==2.3.0 python tools/mcp_smoke.py` (real stdio session).
