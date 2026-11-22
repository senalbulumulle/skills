# Harnesses

Harnesses run several agent sessions as one workflow: they give each session a role, run them in parallel or in turn, and pass the results between them. Claude Code and Codex do the work, so every skill and MCP server in this repo is available to them. The harness only orchestrates.

| Harness | What it does |
| --- | --- |
| [`rival-studios`](rival-studios/README.md) | Several studios with different creative stances build the same brief in separate git worktrees. A blind judge runs every build and picks a winner, and the winner takes the best ideas from the others |

Each harness is one folder: a standard-library Python 3.9+ script, its prompts as Markdown files, and a README. Tests live in `tools/test_<harness>.py` and use a fake agent, so they run without a model.
