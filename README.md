# skills

Creative skills for game development and software development. Each skill works in Claude Code, Codex, Gemini CLI, GitHub Copilot, Cursor, and OpenCode.

## Goals

- More creative output
- More efficient output
- Fewer tokens spent
- Code refactored in an organized way

## Skills

None yet.

## Layout

```
skills/<name>/                       # shared skill, used by every platform
platforms/<platform>/skills/<name>/  # optional per-platform override or platform-only skill
template/SKILL.md                    # starting point for `new`
tools/skills.py                      # validate, new, install, uninstall
```

All six platforms read the same `SKILL.md` format, so a skill lives in `skills/` unless it must differ on one platform. See [platforms/README.md](platforms/README.md) for how overrides work, and each platform's README for its folders and extra frontmatter.

## Requirements

[uv](https://docs.astral.sh/uv/). The CLI declares its own dependency (PyYAML), and uv installs it on first run.

## Install

```sh
tools/skills.py install
```

By default this links every skill into `~/.claude/skills` (Claude Code) and `~/.agents/skills` (Codex). Gemini CLI, Copilot, Cursor, and OpenCode also read `~/.agents/skills`, so the default covers all six platforms.

| Platform | `-p` | User folder | Project folder |
| --- | --- | --- | --- |
| Claude Code | `claude` | `~/.claude/skills` | `.claude/skills` |
| Codex | `codex` | `~/.agents/skills` | `.agents/skills` |
| Gemini CLI | `gemini` | `~/.gemini/skills` | `.gemini/skills` |
| GitHub Copilot | `copilot` | `~/.copilot/skills` | `.github/skills` |
| Cursor | `cursor` | `~/.cursor/skills` | `.cursor/skills` |
| OpenCode | `opencode` | `~/.config/opencode/skills` | `.opencode/skills` |

| Command | Effect |
| --- | --- |
| `tools/skills.py install -p cursor -p claude` | Only those platforms (`-p all` for every one) |
| `tools/skills.py install --project ~/code/my-game` | Into that project's folders instead of your home folder |
| `tools/skills.py install <name> ...` | Only the named skill(s) |
| `tools/skills.py uninstall` | Removes only symlinks that point into this repo |

Install a platform's own folder only when you have variants for it. Several platforms also read other platforms' folders, so installing the same skill for both can list it twice; install prints a note when that applies.

Shared skills are symlinked, so `git pull` updates them everywhere. Platform variants are built into `dist/` (git-ignored), so run `install` again after changing them. Install never overwrites a folder it didn't create, and it refuses skills that fail validation.

## Create a skill

```sh
tools/skills.py new my-skill      # shared skill, from template/SKILL.md
tools/skills.py new my-skill -p cursor  # Cursor-only skill
tools/skills.py validate --strict # fails until every TODO is replaced
```

Authoring rules are in [AGENTS.md](AGENTS.md), which Codex reads directly and Claude Code reads through `CLAUDE.md`.

## What the validator checks

It checks every shared skill, and every platform variant as that platform will receive it.

Errors:
- `SKILL.md` exists and its YAML frontmatter starts on line 1.
- `name`: 1–64 chars of `a-z`, `0-9` and single hyphens; matches the folder; not `synced`.
- `description`: 1–1024 chars, no `<` or `>`.
- No TODO placeholders and no empty body.
- Only known frontmatter keys (portable keys, plus the platform's own keys in its variants). `metadata` maps strings to strings, and `compatibility` is at most 500 chars.
- Relative links resolve and stay inside the skill folder.
- `agents/openai.yaml` uses known keys and types, and its icon files exist.
- Overrides use `frontmatter.yaml` or `SKILL.md`, not both, and only folders for supported platforms exist in `platforms/`.

Warnings (these fail with `--strict`):
- Platform-only frontmatter keys in a shared skill, or in another platform's variant.
- Body over 500 lines or about 5,000 tokens.
- Scripts that have a shebang but are not executable.
- Codex's combined descriptions over 8,000 chars (its skill-list budget).

CI runs the validator's tests and `validate --strict` on every push and pull request.
