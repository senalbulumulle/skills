# Engine notes

## Detect the engine already in use

| Files present | Engine |
| --- | --- |
| `project.godot` | Godot |
| `ProjectSettings/ProjectVersion.txt` and `Assets/` | Unity |
| `package.json` with `phaser` | Phaser |
| `package.json` with `three`, `pixi.js`, `kaboom`/`kaplay`, or `excalibur` | that library |
| `Cargo.toml` with `bevy` | Bevy |
| `conf.lua` + `main.lua` | LÖVE |
| `default.project.json` or `*.rbxlx` | Roblox (use the Roblox skills) |

Use the engine's own idioms instead of the template; keep the same layer order and rules.

## Godot 4 (GDScript)
- Gameplay movement and physics in `_physics_process(delta)` (fixed rate, default 60 Hz); visuals in `_process`.
- Define actions in Project Settings → Input Map; read with `Input.is_action_pressed("jump")` / `is_action_just_pressed`.
- One scene per entity type; instance with `preload(...).instantiate()`.
- Tunables as `@export var` so they're editable in the inspector.
- Restart: `get_tree().reload_current_scene()`.

## Unity (C#)
- Physics in `FixedUpdate`, input reads in `Update` (buffer presses for `FixedUpdate`).
- Tunables in a `ScriptableObject` or `[SerializeField]` fields.
- Restart: `SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex)`.

## Phaser 3
- Scene methods `preload`, `create`, `update(time, delta)`; `delta` is milliseconds.
- Arcade physics for prototypes; `this.physics.add.overlap(a, b, onHit)`.
- Restart: `this.scene.restart()`; reset any state kept outside the scene.

## Headless checks
- Godot: `godot --headless --quit` loads the project and reports script errors.
- Unity: batch mode builds (`-batchmode -quit`) need a licensed editor; ask the user to run them.
- Web: `scripts/check_html.py` for single-file HTML; `npx tsc --noEmit` or the bundler build for TypeScript projects.
