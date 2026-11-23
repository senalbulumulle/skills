# skills

An MCP server, a harness, and tooling for building web front ends with Claude Code and Codex.

## What's here

| Folder | What it is |
| --- | --- |
| [`mcp/web-dev/motion-forge`](mcp/web-dev/motion-forge/README.md) | An MCP server with motion-rich Web Components, a showcase builder, and a motion audit |
| [`harnesses/creative-pipeline`](harnesses/creative-pipeline/README.md) | Gemini brainstorms, Claude Code builds, an anti-slop gate rejects stock output, and Codex audits the result |
| [`platforms/codex`](platforms/codex/README.md) | Codex tooling: a list of the hook outputs Codex accepts, and a comparison of the models in its catalog |
| `skills/` | Empty for now. `tools/skills.py` installs any skill you add here; see [`AGENTS.md`](AGENTS.md) |

## Install

You need [Git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/). If you don't have uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then clone the repo:

```sh
git clone https://github.com/senalbulumulle/skills.git
cd skills
```

### MCP server in Claude Code

Replace `/path/to/skills` with where you cloned this repo:

```sh
claude mcp add --scope user motion-forge -- uv run --quiet --script /path/to/skills/mcp/web-dev/motion-forge/server.py
```

### MCP server in Codex

```sh
scripts/codex/install-codex.sh
```

This registers the MCP servers with Codex, and links any skills into `~/.agents/skills/`. Use `--only mcp` to skip the skills, and `scripts/codex/uninstall-codex.sh` to remove everything it installed.

### Skills

When `skills/` has skills, `tools/skills.py install` links them into `~/.claude/skills/` (Claude Code) and `~/.agents/skills/` (Codex). Add `-p claude` or `-p codex` for one platform, `-c CATEGORY` for some categories, or `--project DIR` to install into a project instead of your home folder. `tools/skills.py uninstall` takes the same options.

### Optional tools

- [Python](https://www.python.org/) 3.9 or newer: the Codex MCP installer and the harness.
- [Codex CLI](https://developers.openai.com/codex/cli): needed to register the MCP servers with Codex.
- [Node.js](https://nodejs.org/): only for running this repo's JavaScript tests.

## Contributing

Read [`AGENTS.md`](AGENTS.md) for the layout, the authoring rules, and the checks to run before committing.
