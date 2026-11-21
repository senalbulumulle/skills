# skills

Creative skills for game development and software development. Each skill works in Claude Code and Codex.

## Categories

Skills are grouped by use case under `skills/<category>/`. Install everything, or only the categories you need.

| Category | What it covers | Skills |
| --- | --- | --- |
| [`game-dev`](skills/game-dev/README.md) | Engine-agnostic games: HTML5 canvas by default, adapts to Godot, Unity, or Phaser | `game-concept`, `game-prototype`, `game-feel`, `game-art`, `game-audio`, `game-ai`, `game-level-design`, `game-procgen`, `game-balance`, `game-playtest` |
| [`roblox`](skills/roblox/README.md) | Roblox experiences in Luau with Rojo | `roblox-game-design`, `roblox-scripting`, `roblox-gameplay`, `roblox-narrative`, `roblox-playtest` |

Run `tools/skills.py list` to see every skill with its summary.

MCP servers are grouped the same way under `mcp/<category>/<name>/` (see [`mcp/README.md`](mcp/README.md)):

| Category | Server | What it covers |
| --- | --- | --- |
| `web-dev` | `motion-forge` | Motion-rich Web Components, showcase builder, motion audit |

## Installation

### Dependencies

Required:

- [Git](https://git-scm.com/), to clone the repository.
- [uv](https://docs.astral.sh/uv/), to run `tools/skills.py` and the MCP servers. It downloads the Python version and packages they need.

Optional, only for the features that use them:

- [Python](https://www.python.org/) 3.9 or newer: the scripts in some skills, and the Codex hooks and profile installers.
- [Node.js](https://nodejs.org/): the browser playtest (`game-playtest`) and the HTML script check (`game-prototype`).
- [Codex CLI](https://developers.openai.com/codex/cli): `scripts/codex/install-codex.sh` registers the MCP servers with it.
- [Rojo](https://rojo.space) and [Luau](https://github.com/luau-lang/luau/releases): building the Roblox project template and type-checking Luau modules.

### Install

Install uv if you don't have it yet:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Clone the repository and install the skills:

```sh
git clone https://github.com/senalbulumulle/skills.git
cd skills
tools/skills.py install
```

This links every skill into `~/.claude/skills/` (Claude Code) and `~/.agents/skills/` (Codex). The installs link back to the clone, so keep it where it is.

### Update

Run these from the `skills` folder:

```sh
git pull
tools/skills.py install
```

### Choose platforms

Install for just one of `claude` or `codex` (the default is both):

```sh
tools/skills.py install -p claude
```

### Choose categories

Install only some categories (repeat `-c` for more than one):

```sh
tools/skills.py install -c roblox
```

Installed skills keep their own names (`~/.claude/skills/roblox-scripting`, not `roblox/roblox-scripting`), so skill names are unique across categories.

### Install into one project

Replace `/path/to/project` with your project folder:

```sh
tools/skills.py install --project /path/to/project
```

### Codex: skills, hooks, profile, and MCP servers

```sh
scripts/codex/install-codex.sh
```

Run `scripts/codex/install-codex.sh --help` to see the options. To register only some MCP categories, run `scripts/codex/install-codex-mcp.sh -c <category>`. For MCP setup in Claude Code, see `mcp/web-dev/motion-forge/README.md`.

### Uninstall

```sh
tools/skills.py uninstall
```

`uninstall` takes the same `-p`, `-c`, and `--project` options as `install`. To remove everything the Codex script installed:

```sh
scripts/codex/uninstall-codex.sh
```
