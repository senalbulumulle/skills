---
name: roblox-scripting
description: Structure and write secure, reliable Roblox game code in Luau, covering Rojo projects, client-server boundaries, validated and rate-limited RemoteEvents, session-locked DataStore saves with UpdateAsync and retries, typed --!strict modules, and a ready project template. Use when starting a Roblox game, writing or reviewing Roblox scripts, adding saving, remotes, or leaderstats, or fixing exploits, data loss, or messy Roblox code.
---

# Roblox Scripting

Build Roblox code where the server owns every outcome, data never gets lost or duplicated, and modules stay small and testable.

## Steps

1. **Start from the template.** For a new game run `scripts/new_project.py my-game --name "My Game"`, then `cd my-game && rojo serve` and connect from the Rojo plugin in Studio (Rojo 7.2 or newer, for `.luau` files). It contains:
   - `src/server/PlayerData.luau`: session-locked saves via `UpdateAsync`, retries with backoff, new-field reconciliation, `saveAll` for shutdown.
   - `src/server/RemoteGuard.luau`: argument checks and per-player rate limits for remotes.
   - `src/server/Main.server.luau` and `src/client/Main.client.luau`: wiring examples (load and kick on failure, leaderstats, a validated remote, autosave, `BindToClose`).
   - Remotes declared in `default.project.json`, so they exist before any script runs.
   For an existing place, copy the modules in and adopt the same rules.
2. **Put code where it belongs** (map in [architecture.md](references/architecture.md)): server-only logic and modules in ServerScriptService; shared modules and remotes in ReplicatedStorage; client code in StarterPlayerScripts. Never place server secrets or authority in ReplicatedStorage.
3. **Make the server authoritative.** Clients send intents ("use slot 2"), never results ("I earned 500 coins"). Every `OnServerEvent` / `OnServerInvoke` goes through `RemoteGuard.wrap` with a check per argument and a rate limiter. Then validate game rules in the handler: ownership, cooldowns, distance, currency.
4. **Save data safely** with `PlayerData`: load on join (kick if it fails, so default data never overwrites a real save), `release` on leave, autosave on an interval shorter than the lock timeout, `saveAll(true)` in `BindToClose`. Keep saved data plain tables of numbers, strings, booleans.
5. **Write modules as pure as possible**: pass services in (like `PlayerData.new({ store = ..., wait = task.wait })`) so logic runs and is tested outside Studio. Start every module with `--!strict`.
6. **Check before running.** If `luau-analyze` is installed, run it on pure modules (`luau-analyze --mode=strict src/server/RemoteGuard.luau`). Engine scripts need Roblox type definitions, so check those in Studio's Script Analysis window or with luau-lsp. If the Roblox Studio MCP server is connected, use it to read scripts, run code, and read output (`script_read`, `execute_luau`, `get_console_output`). If the roblox-forge MCP server is connected, run `check_project` after layout changes, and `map_remotes` and `audit_remotes` after adding or renaming remotes.

## Rules

- Never trust the client: assume every remote argument is forged and every call is spammed.
- No `wait()`, `spawn()`, `delay()`: use `task.wait`, `task.spawn`, `task.delay`.
- Use `game:GetService("Name")`, never `game.Name`.
- No yielding inside `UpdateAsync` callbacks.
- Disconnect connections and clean up per-player state on `PlayerRemoving`.

## Done when

- [ ] Every remote handler is wrapped with argument checks and a rate limit, and re-checks game rules on the server.
- [ ] Data loads with session locking, saves on leave, autosave, and shutdown, and the game kicks instead of playing on unloaded data.
- [ ] No server-only module or secret lives in ReplicatedStorage.
- [ ] Pure modules pass `luau-analyze --mode=strict` (when available) and engine scripts show no Script Analysis errors in Studio.
