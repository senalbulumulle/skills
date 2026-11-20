# skills

Creative skills for game development and software development. Each skill works in Claude Code, Codex, Gemini CLI, GitHub Copilot, Cursor, and OpenCode.

## Installation

You need [uv](https://docs.astral.sh/uv/). Install it if you don't have it yet:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Clone the repository and install the skills:

```sh
git clone https://github.com/senalbulumulle/skills.git
cd skills
tools/skills.py install
```

This links every skill into `~/.claude/skills/` (Claude Code) and `~/.agents/skills/` (Codex). Gemini CLI, GitHub Copilot, Cursor, and OpenCode also read `~/.agents/skills/`, so they pick the skills up too. The installs link back to the clone, so keep it where it is.

### Update

Run these from the `skills` folder:

```sh
git pull
tools/skills.py install
```

### Choose platforms

Pick one or more of `claude`, `codex`, `gemini`, `copilot`, `cursor`, and `opencode`:

```sh
tools/skills.py install -p claude -p cursor
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

Run `scripts/codex/install-codex.sh --help` to see the options. For MCP setup in Claude Code, see `mcp/creative-director/README.md` and `mcp/roblox-forge/README.md`.

### Uninstall

```sh
tools/skills.py uninstall
```

`uninstall` takes the same `-p` and `--project` options as `install`. To remove everything the Codex script installed:

```sh
scripts/codex/uninstall-codex.sh
```
