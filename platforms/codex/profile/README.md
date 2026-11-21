# Codex "game" profile and agent roles

| File | Installed to | What it does |
| --- | --- | --- |
| `game-instructions.md` | `$CODEX_HOME/game.config.toml`, as `developer_instructions` | Creative direction for games and software: commit to one idea, use concrete names and numbers, get a playable version running, make it feel good, verify before finishing, report plainly |
| `agents/game-designer.toml` | `$CODEX_HOME/agents/` | A sub-agent that writes a buildable design: fantasy, core loop, hook, controls, win and fail, first minute, feedback, progression, scope, and tuning numbers |
| `agents/game-critic.toml` | `$CODEX_HOME/agents/` | A sub-agent that playtests or reads the build and ranks what is broken, confusing, dull, or generic |
| `agents/roblox-polisher.toml` | `$CODEX_HOME/agents/` | A sub-agent that adds and fixes effects, sounds, and UI feedback in a Roblox project from the roblox-gameplay effects catalog, using only real assets |
| `agents/narrative-designer.toml` | `$CODEX_HOME/agents/` | A sub-agent that writes characters, a story outline, and NPC dialogue as Markdown, checks them with `story.py review`, and builds the dialogue module, voiceover script, and localization CSV |

The profile also sets the model: the first of `gpt-6.2-astra` and `gpt-6-astra` that the installed Codex lists, at `high` reasoning effort. Pick another with `--model`.

## Use

```sh
scripts/codex/install-codex-profile.sh   # or scripts/codex/install-codex.sh for everything
codex -p game                            # a session with the profile
```

The roles work in any session, but Codex passes a role to a sub-agent only when you ask for it, for example "use the game-critic agent on this build".

The installer writes and removes only files that start with its marker line, so it never touches a profile or role you wrote yourself. `--dry-run` prints the files and `--uninstall` removes them.

## Verified in Codex 0.163.0

- `codex -p NAME` layers `$CODEX_HOME/NAME.config.toml` on top of `config.toml`, and its `developer_instructions` becomes the first developer message.
- Role files in `$CODEX_HOME/agents/` are loaded automatically. Each needs `name` and `developer_instructions`, and its `description` is what the spawn tool lists.
- A captured request with the profile showed model `gpt-6-astra`, effort `high`, the profile instructions, every role (roblox-polisher and narrative-designer included), and the game hooks' creative brief.
