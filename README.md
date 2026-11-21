# skills

Creative skills for game development and software development. Each skill works in Claude Code and Codex.

## Installation

### Dependencies

Required:

- [Git](https://git-scm.com/), to clone the repository.
- [uv](https://docs.astral.sh/uv/), to run `tools/skills.py` and the MCP servers. It downloads the Python version and packages they need.

Optional, only for the features that use them:

- [Python](https://www.python.org/) 3.9 or newer: the scripts in some skills, and the Codex hooks and profile installers.
- [Node.js](https://nodejs.org/): the browser playtest (`game-playtest`) and the HTML script check (`game-prototype`).
- [Codex CLI](https://developers.openai.com/codex/cli): `scripts/codex/install-codex.sh` registers the MCP servers with it.
- [Rojo](https://rojo.space) and [Luau](https://github.com/luau-lang/luau/releases): build and type checks in the `roblox-forge` MCP server.

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

### Install into one project

Replace `/path/to/project` with your project folder:

```sh
tools/skills.py install --project /path/to/project
```

### Codex: skills, hooks, profile, and MCP servers

```sh
scripts/codex/install-codex.sh
```

Run `scripts/codex/install-codex.sh --help` to see the options. For MCP setup in Claude Code, see `mcp/creative-director/README.md`, `mcp/roblox-forge/README.md`, and `mcp/motion-forge/README.md` (which also covers Gemini CLI).

### Uninstall

```sh
tools/skills.py uninstall
```

`uninstall` takes the same `-p` and `--project` options as `install`. To remove everything the Codex script installed:

```sh
scripts/codex/uninstall-codex.sh
```
