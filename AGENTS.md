# Authoring rules for this repo

Skills here must work in Claude Code and Codex. Follow these rules for every change.

## Layout

- One skill per folder: `skills/<name>/SKILL.md`. The folder name must equal `name`.
- Optional subfolders: `references/` (docs loaded on demand), `scripts/` (executables), `assets/` (templates, data), `agents/openai.yaml` (Codex UI and invocation policy).
- Link files with relative paths from the skill root, one level deep. Never link outside the skill folder; installs are symlinks and the skill must stand alone.
- Put a skill in `skills/` by default. Add `platforms/<platform>/skills/<name>/` only when that platform needs something different (see `platforms/README.md`). Never copy a whole skill into a platform folder: change only what differs, preferably with `frontmatter.yaml`.
- A skill only one platform can use goes in `platforms/<platform>/skills/<name>/` (`tools/skills.py new <name> -p <platform>`).

## Writing a skill

- Start with `tools/skills.py new <name>` and replace every TODO.
- `description` decides when the skill loads. Say what it does, then "Use when ..." with concrete tasks and trigger words. Max 1024 chars, no `<` or `>`.
- Keep the SKILL.md body short (under 500 lines and about 5,000 tokens). It stays in context once loaded, so every line costs tokens on every turn. Put long material in `references/`.
- Write instructions, not essays: numbered steps, then a "Done when" checklist of observable checks.
- Prefer a script in `scripts/` over asking the agent to reason through a mechanical task.
- Use only the portable frontmatter keys: `name`, `description`, `license`, `compatibility`, `metadata` (string values), `allowed-tools`. Platform-only keys (listed in each `platforms/<platform>/README.md`) belong in that platform's `frontmatter.yaml`; anywhere else they produce a warning and fail `--strict`.

## Before committing

Run all of these, and fix every failure (Luau and Rojo are needed for the Roblox checks):

```sh
tools/skills.py validate --strict
uv run --with pyyaml python -m unittest discover -s tools
node --test tools/test_game_assets.test.mjs
luau tools/luau/test_roblox_modules.luau
uv run --python 3.12 --with mcp==2.3.0 python tools/mcp_smoke.py
```

Every script or library added under a skill's `scripts/` or `assets/` needs tests in `tools/` (`test_game_scripts.py` for Python, `test_game_assets.test.mjs` for JavaScript, `luau/test_roblox_modules.luau` for Luau). Pure Luau modules must also pass `luau-analyze --mode=strict` (listed in the CI workflow).

## Hooks

Codex hooks live in `platforms/codex/hooks/`: standard-library Python 3.9+ that fails open (an internal error exits 0 with no output), tested in `tools/test_codex_hooks.py`. Use only hook outputs that the installed Codex accepts: check with `platforms/codex/hooks/discover.py`, and save a new snapshot when Codex changes. The unfinished-content rules in `game_hooks.py` must stay identical to `mcp/creative-director/director.py` (a test enforces it); change both together.

The Codex `game` profile and agent roles live in `platforms/codex/profile/`. After a Codex update, save a model snapshot with `platforms/codex/models/export_models.py --json`; it records structure only, never OpenAI's instruction text.

## MCP servers

MCP servers live in `mcp/<name>/`: tool logic in a standard-library module with unit tests, a thin `server.py` that registers tools, and a README with setup for Claude Code and Codex. One server serves every platform; only registration differs.
