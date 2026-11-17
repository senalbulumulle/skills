# Authoring rules for this repo

Skills here must work in Claude Code, Codex, Gemini CLI, GitHub Copilot, Cursor, and OpenCode. Follow these rules for every change.

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

Run both, and fix every failure:

```sh
tools/skills.py validate --strict
uv run --with pyyaml python -m unittest discover -s tools
```
