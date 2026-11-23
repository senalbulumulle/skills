# Authoring rules for this repo

Skills here must work in Claude Code and Codex. Follow these rules for every change.

## Layout

- One skill per folder, grouped by use case: `skills/<category>/<name>/SKILL.md`. The folder name must equal `name`, and names are unique across categories (installs are flat).
- Every category has a `README.md`: one sentence on what it covers, the usual order of its skills, and its install command. Add a skill to an existing category when it fits; create a new category only for a new use case, not for one skill that could live elsewhere. Category and skill names use the same lowercase-hyphen rules.
- Optional subfolders: `references/` (docs loaded on demand), `scripts/` (executables), `assets/` (templates, data), `agents/openai.yaml` (Codex UI and invocation policy).
- Link files with relative paths from the skill root, one level deep. Never link outside the skill folder; installs are symlinks and the skill must stand alone.
- Put a skill in `skills/<category>/` by default. Add `platforms/<platform>/skills/<category>/<name>/` (same category as the shared skill) only when that platform needs something different (see `platforms/README.md`). Never copy a whole skill into a platform folder: change only what differs, preferably with `frontmatter.yaml`.
- A skill only one platform can use goes in `platforms/<platform>/skills/<category>/<name>/` (`tools/skills.py new <name> -c <category> -p <platform>`). Its category still needs `skills/<category>/README.md`.

## Writing a skill

- Start with `tools/skills.py new <name> -c <category>` and replace every TODO (a new category also gets a `README.md` with a TODO). Add the skill to its category README and to the table in the root `README.md`.
- `description` decides when the skill loads. Say what it does, then "Use when ..." with concrete tasks and trigger words. Max 1024 chars, no `<` or `>`.
- Keep the SKILL.md body short (under 500 lines and about 5,000 tokens). It stays in context once loaded, so every line costs tokens on every turn. Put long material in `references/`.
- Write instructions, not essays: numbered steps, then a "Done when" checklist of observable checks.
- Prefer a script in `scripts/` over asking the agent to reason through a mechanical task.
- Use only the portable frontmatter keys: `name`, `description`, `license`, `compatibility`, `metadata` (string values), `allowed-tools`. Platform-only keys (listed in each `platforms/<platform>/README.md`) belong in that platform's `frontmatter.yaml`; anywhere else they produce a warning and fail `--strict`.

## Before committing

Run all of these, and fix every failure:

```sh
tools/skills.py validate --strict
uv run --with pyyaml python -m unittest discover -s tools
node --test tools/test_game_assets.test.mjs tools/test_motion_components.test.mjs
uv run --python 3.12 --with mcp==2.3.0 python tools/mcp_smoke.py
```

Every script or library added under a skill's `scripts/` or `assets/` needs tests in `tools/` (`test_game_scripts.py` for Python, `test_game_assets.test.mjs` for JavaScript).

## Hooks

A Codex hook may use only the outputs the installed Codex accepts: check with `platforms/codex/hooks/discover.py`, and save a new snapshot when Codex changes.

The Codex `game` profile and agent roles live in `platforms/codex/profile/`. After a Codex update, save a model snapshot with `platforms/codex/models/export_models.py --json`; it records structure only, never OpenAI's instruction text.

## Harnesses

Harnesses live in `harnesses/<name>/`; list each one in `harnesses/README.md`. Run Claude Code and Codex steps as headless CLI sessions so skills and MCP servers stay available; call a model API directly only for steps that need nothing but text. Each harness has standard-library Python 3.9+ scripts, its prompts as Markdown files in `prompts/`, and a README. Tests go in `tools/test_<name>.py` and use mocks or fake CLIs so they run without a model. Never let a harness merge, push, or publish: it leaves branches for the user.

## MCP servers

MCP servers live in `mcp/<category>/<name>/`, using the skill category names (plus categories such as `web-dev` that have no skills yet); list each one in `mcp/README.md`. Each has tool logic in a standard-library module with unit tests, a thin `server.py` that registers tools, and a README with setup for Claude Code and Codex. One server serves every platform; only registration differs.
