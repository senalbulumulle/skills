# skills

Creative skills for game development and software development. Each skill works in Claude Code, Codex, Gemini CLI, GitHub Copilot, Cursor, and OpenCode.

## Goals

- More creative output
- More efficient output
- Fewer tokens spent
- Code refactored in an organized way

## Skills

### Game development

A pipeline from idea to tested game. Each skill works alone or hands off to the next.

| Skill | What it does | Ships with |
| --- | --- | --- |
| `game-concept` | Generates 6 original concepts, scores them, writes a one-page design brief | idea generators, brief template |
| `game-prototype` | Builds a playable prototype in verified layers; single-file HTML5 by default | canvas starter, HTML/JS checker |
| `game-feel` | Controls first, then hit stop, shake, squash, particles, popups | `juice.js`, tuning tables |
| `game-level-design` | Teaches mechanics through levels, paces difficulty, stores levels as data | grid level solver |
| `game-balance` | Turns targets into curves, time-to-kill, and drop odds | balance calculator |
| `game-procgen` | Seeded dungeons, caves, noise terrain, scatter, loot | `procgen.js` |
| `game-ai` | Readable, fair enemies: telegraphs, state machines, steering, A* | `ai.js` |
| `game-art` | Palette by role, shape language, pixel sprites, readability checks | contrast checker, `pixel-sprite.js` |
| `game-audio` | Event-mapped Web Audio SFX, voice limits, mixing, music | `sfx.js` synth |
| `game-playtest` | Automated smoke test, state matrix, prioritized fix list | Playwright playtest script |

In Claude Code, each also accepts an argument after its slash command (for example `/game-prototype docs/design-brief.md`).

### Roblox

| Skill | What it does | Ships with |
| --- | --- | --- |
| `roblox-game-design` | Original Roblox concepts, first-minute timeline, social hook, retention, fair and policy-compliant monetization | genre loops, monetization and receipt guide, brief template |
| `roblox-scripting` | Secure Rojo project structure, validated remotes, session-locked saves | project template and scaffolder; `PlayerData` and `RemoteGuard` modules (strict-typed, tested) |
| `roblox-gameplay` | Server-authoritative mechanics, rounds, combat, NPCs, mobile UI | `RoundSystem` module, systems reference |
| `roblox-playtest` | Multi-client testing, exploit checks, data and release checklists | checklist; uses Roblox Studio's MCP server when connected |

Codex shows these in its skill picker with a display name and default prompt (`platforms/codex/`); Claude Code adds argument hints (`platforms/claude/`).

## MCP servers

| Server | Tools | Setup |
| --- | --- | --- |
| [roblox-forge](mcp/roblox-forge/README.md) | `create_project`, `check_project`, `audit_remotes`, `check_odds`, `datastore_budget`, `luau_check` | one server for Claude Code and Codex; see its README |

## Hooks

| Hooks | Platform | What they do |
| --- | --- | --- |
| [game hooks](platforms/codex/hooks/README.md) | Codex | Detect the engine (Unreal, Unity, Godot, Roblox/Rojo, and more). Add its rules at session start, block publishing and edits to binary or generated files, check edited files, and stop the agent once if errors remain |

## Layout

```
skills/<name>/                       # shared skill, used by every platform
platforms/<platform>/skills/<name>/  # optional per-platform override or platform-only skill
template/SKILL.md                    # starting point for `new`
tools/skills.py                      # validate, new, install, uninstall
mcp/<server>/                        # MCP servers (one per folder, shared by all platforms)
platforms/codex/hooks/               # Codex lifecycle hooks for game projects
scripts/                             # install scripts (install-codex.sh, uninstall-codex.sh, ...)
```

All six platforms read the same `SKILL.md` format, so a skill lives in `skills/` unless it must differ on one platform. See [platforms/README.md](platforms/README.md) for how overrides work, and each platform's README for its folders and extra frontmatter.

## Requirements

[uv](https://docs.astral.sh/uv/). The CLI declares its own dependency (PyYAML), and uv installs it on first run.

To run every development check (see AGENTS.md): Node.js 22+, [Luau](https://github.com/luau-lang/luau/releases), and [Rojo](https://rojo.space) 7.2+.

## Install

For Codex, one script installs the skills and the game hooks globally:

```sh
scripts/install-codex.sh          # skills -> ~/.agents/skills, game hooks -> ~/.codex/hooks.json
scripts/uninstall-codex.sh        # removes only what these scripts installed
```

| Script | Effect |
| --- | --- |
| `scripts/install-codex.sh [--skills-only \| --hooks-only]` | Both steps, or one. Safe to re-run |
| `scripts/install-codex-skills.sh [name ...]` | Skills only (all, or the named ones), validated first |
| `scripts/install-codex-hooks.sh [--dry-run]` | Game hooks only. Other hooks in `hooks.json` are kept |
| `scripts/uninstall-codex.sh [--skills-only \| --hooks-only]` | Removes this repo's skill links and `game_hooks.py` handlers |

They need `uv`, and `python3` 3.9 or newer. After installing, run `/hooks` once in Codex to trust the game hooks, because Codex skips untrusted hooks. The hooks run from this checkout, so re-run the script if you move the repo.

For other platforms, or finer control, use the skills CLI directly:

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

CI runs the validator's tests, the tests for every skill script and library (Python, JavaScript, and Luau, plus strict Luau type checks and a real Rojo build), an MCP smoke test, and `validate --strict` on every push and pull request.
