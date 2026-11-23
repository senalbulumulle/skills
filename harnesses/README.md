# Harnesses

Harnesses run several model sessions as one workflow: they give each session a role, run them in turn, check what comes back, and pass the results on. Claude Code and Codex steps run as headless CLI sessions, so the skills and MCP servers in this repo stay available to them. Steps that only need text can call a model API directly.

| Harness | What it does |
| --- | --- |
| [`creative-pipeline`](creative-pipeline/README.md) | Gemini brainstorms directions, Claude Code builds one, a deterministic anti-slop gate rejects stock output and sends it back for revision, and Codex audits and fixes the result. A guard hook blocks destructive commands in every session |

Each harness is one folder: standard-library Python 3.9+ scripts, its prompts as Markdown files in `prompts/`, and a README. Tests live in `tools/test_<harness>.py` and use mocks or fake CLIs, so they run without a model.
