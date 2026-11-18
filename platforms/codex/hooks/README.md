# Codex game-dev hooks

Engine-aware [Codex hooks](https://developers.openai.com/codex/hooks) for game projects. They detect the engine from the project files and apply that engine's rules. Two checks run in every project: a creative brief for game requests, and an unfinished-content check at `Stop`.

| Event | What it does |
| --- | --- |
| `SessionStart` | Adds a short rule sheet for the detected engine and version (about 5 lines) to the model's context |
| `UserPromptSubmit` | When a prompt asks to make or change a game, adds a four-sentence creative brief: one specific idea with a hook, concrete names and numbers, a playable version first, feedback on every action, and verification before finishing. Words like "level" or "weapon" count only inside a game project |
| `PreToolUse` (`Bash`, `apply_patch`) | Blocks publishing, text edits to binary assets, edits to generated folders, and deletes of core project data. Adds notes for Unity `.meta` handling |
| `PostToolUse` (`apply_patch`) | Runs the engine checks on the patched files and returns any errors and warnings to the model |
| `Stop` | Blocks the stop once if git-changed files still have engine check errors, or if lines added since the last commit look unfinished or generic. The agent then fixes them or explains why they stay. It never loops, and warnings never block |

The unfinished-content check flags filler text, a TODO or FIXME whose note says to implement, stub, or replace something, stubs that throw "not implemented" (C#, JavaScript, Rust), stand-in UI text, and generic titles. It skips test files, fixtures, lockfiles, and minified files, and it ignores ordinary TODOs and Python's `NotImplementedError`, which abstract methods use. The rules are the same as the creative-director MCP server's `find_slop`, and a test keeps them identical.

## Engines

| Engine | Detected by | Checks after edits | Guards |
| --- | --- | --- | --- |
| Unreal Engine | `*.uproject` (version from `EngineAssociation`) | Reflected headers include `<File>.generated.h` last and have `GENERATED_BODY()`. Warns on `new` for `U`/`A` classes | No edits to `Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/` (also in plugins) or `*.generated.h`. No deleting `Content/`, `Config/`, `Source/`, `*.uproject` |
| Unity | `Assets/` + `ProjectSettings/ProjectVersion.txt` | `UnityEditor` outside an Editor folder, `#if UNITY_EDITOR`, or an Editor-only asmdef (error). `MonoBehaviour`/`ScriptableObject` class name must match the file name. `FindObjectOfType` warning on 2023.1+ | No edits to `Library/`, `Temp/`, `Logs/`, `obj/`. No deleting `Assets/`, `ProjectSettings/`, `Packages/manifest.json`. No deleting a `.meta` while its asset stays. Notes for moving or deleting an asset without its `.meta`, and for hand-written `.meta` files |
| Godot | `project.godot` (3 vs 4 from `config_version`/features) | Wrong-version GDScript: `yield`, `onready var`, `export var`, `tool`, `setget`, string `connect()` in Godot 4, or `@onready`/`await` in Godot 3 | No edits to `.godot/` or `.import/`. No deleting `project.godot` |
| Roblox (Rojo) | `default.project.json`, any `*.project.json` with a `tree`, or `.rbxl(x)` | Luau: deprecated `wait`/`spawn`/`delay`, `game.Service` instead of `GetService`. Project file: valid JSON, every `$path` exists | No edits to Wally `Packages/` folders (when `wally.toml` exists) |
| Defold, GameMaker, Bevy, MonoGame, LÖVE, Pygame, web (Phaser, three.js, PixiJS, Babylon.js, Kaboom, Excalibur, PlayCanvas) | `game.project`, `*.yyp`, `Cargo.toml` with `bevy`, `*.csproj` with MonoGame, `main.lua` using `love.`, `requirements.txt`/`pyproject.toml` with pygame, `package.json` | none yet | Generated folders where the engine has them (`build/`, `target/`, `bin/`/`obj/`, `node_modules/`). Core project files |

These guards apply in every project:
- **Publishing:** blocks `rojo upload`, `mantle deploy`, `rbxcloud experience publish`, `steamcmd … +run_app_build`, `butler push`, `BuildPatchTool`, and `altool --upload-app`. These change live games or stores, so the user runs them.
- **Binary assets:** blocks text edits (`sed -i`, `perl -i`, `>`, `tee`, or `apply_patch`) to `.uasset`, `.umap`, `.rbxl`, `.rbxm`, and `.blend`.

## Install

Requires `python3` 3.9+ on PATH. macOS and Linux are tested; Windows is not.

```sh
platforms/codex/hooks/install.py --user               # every Codex session; points at this checkout
platforms/codex/hooks/install.py --project ~/my-game  # copies the script into the game's .codex/ for the team
```

Then open Codex and run `/hooks` to review and trust them, because Codex skips new or changed hooks until you trust them. Project hooks also need the project itself to be trusted.

- **Updating:** after updating this repo, run the same install command again. The installer replaces only handlers whose command mentions `game_hooks.py`.
- **Removing:** add `--uninstall`.
- **Previewing:** `--dry-run` prints the resulting `hooks.json` without writing it.

## What Codex actually supports (discovered from the binary)

`discover.py` reads the hook surface compiled into the installed Codex without running it. It parses the embedded JSON schemas and the runtime's rejection messages.

```sh
platforms/codex/hooks/discover.py                                         # summary for the codex on PATH
platforms/codex/hooks/discover.py --diff platforms/codex/hooks/snapshots/codex-0.163.0.json  # what changed after an upgrade
```

Codex 0.163.0 findings, from the binary and a live run, that the docs don't make obvious:
- **Events:** the binary has 12 events, including `Interrupt` and `SubagentStart`. `PreModelRequest`/`PostModelRequest`, which the online docs list, are not in 0.163.0.
- **Accepted by the schema but rejected at runtime:**
  - `PreToolUse`: `permissionDecision: "ask"`, legacy `decision: "approve"`, `continue: false`, `stopReason`, and `suppressOutput`. `permissionDecision: "allow"` is rejected unless it comes with `updatedInput`.
  - `PostToolUse`: `updatedMCPToolOutput`.
  - `PermissionRequest`: `updatedInput`, `updatedPermissions`, and `interrupt: true`.
- **Handler types:** `prompt` and `agent` are parsed but skipped. `command` and `mcp_tool` run.
- **Tool calls:** shell calls arrive as `tool_name: "Bash"` with `tool_input.command` as a string. File edits arrive as `tool_name: "apply_patch"` with the raw patch text in `tool_input.command`.
- **Process environment:** Codex runs hook commands through the shell in the session's `cwd`, with no `CODEX_*` environment variables. That is why project installs locate the script with `git rev-parse --show-toplevel`.
- **Denial text:** Codex shows a `PreToolUse` denial as `Command blocked by PreToolUse hook: <reason>. Command: <command>`.

## Development

- `game_hooks.py` is standard library only. Every internal error exits 0 with no output, so a hook bug never blocks the agent.
- Tests: `python3 -m unittest tools/test_codex_hooks.py`. They cover every engine, guard, and check, the creative brief and the unfinished-content check, plus the installer and the discovery parser. The snapshot test runs only when Codex 0.163.0 is installed.
- When Codex updates, run `discover.py --diff` against the latest snapshot. If anything changed, save a new snapshot (`discover.py --json > snapshots/codex-<version>.json`) and adjust the hooks.
