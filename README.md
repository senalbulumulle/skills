# skills

Skills, an MCP server, and a harness for building games and web front ends with Claude Code and Codex.

## What's here

| Folder | What it is |
| --- | --- |
| [`skills/game-dev`](skills/game-dev/README.md) | 10 skills for making games, from concept to playtest. HTML5 canvas by default; adapts to Godot, Unity, or Phaser |
| [`mcp/web-dev/motion-forge`](mcp/web-dev/motion-forge/README.md) | An MCP server with motion-rich Web Components, a showcase builder, and a motion audit |
| [`harnesses/creative-pipeline`](harnesses/creative-pipeline/README.md) | Gemini brainstorms, Claude Code builds, an anti-slop gate rejects stock output, and Codex audits the result |
| [`platforms/codex`](platforms/codex/README.md) | Codex extras: a `game` profile with two agent roles, and a tool that lists the hook outputs Codex accepts |

The game-dev skills: `game-concept`, `game-prototype`, `game-feel`, `game-art`, `game-audio`, `game-ai`, `game-level-design`, `game-procgen`, `game-balance`, `game-playtest`. Run `tools/skills.py list` to see each one's summary.

## Install

You need [Git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/). If you don't have uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then:

```sh
git clone https://github.com/senalbulumulle/skills.git
cd skills
tools/skills.py install
```

This links every skill into `~/.claude/skills/` (Claude Code) and `~/.agents/skills/` (Codex). The links point back to the clone, so keep it where it is.

To update, run `git pull` and then `tools/skills.py install` again from the `skills` folder.

### Options

| Command | What it does |
| --- | --- |
| `tools/skills.py install -p claude` | Install for one platform only: `claude` or `codex` (default: both) |
| `tools/skills.py install -c game-dev` | Install only some categories (repeat `-c` for more) |
| `tools/skills.py install --project DIR` | Install into `DIR/.claude/skills/` and `DIR/.agents/skills/` instead of your home folder |
| `tools/skills.py uninstall` | Remove the links. Takes the same `-p`, `-c`, and `--project` options |

### Codex extras

```sh
scripts/codex/install-codex.sh
```

This installs the skills, the `game` profile (start it with `codex -p game`), and the MCP servers. Use `--only skills,mcp` to pick components, and `scripts/codex/uninstall-codex.sh` to remove them.

### MCP server in Claude Code

Replace `/path/to/skills` with where you cloned this repo:

```sh
claude mcp add --scope user motion-forge -- uv run --quiet --script /path/to/skills/mcp/web-dev/motion-forge/server.py
```

### Optional tools

- [Python](https://www.python.org/) 3.9 or newer: scripts in some skills, the Codex profile and MCP installers, and the harness.
- [Node.js](https://nodejs.org/): the browser playtest in `game-playtest` and the HTML check in `game-prototype`.
- [Codex CLI](https://developers.openai.com/codex/cli): needed to register the MCP servers with Codex.

## Contributing

Read [`AGENTS.md`](AGENTS.md) for the layout, the authoring rules, and the checks to run before committing.
