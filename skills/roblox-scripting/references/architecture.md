# Roblox architecture reference

## Where code lives
| Container | Runs / visible on | Put here |
| --- | --- | --- |
| ServerScriptService | server only, never replicated | server Scripts, server-only ModuleScripts |
| ServerStorage | server only | maps, templates, items not yet spawned |
| ReplicatedStorage | server and every client | shared modules, remotes, shared config, assets clients need |
| StarterPlayerScripts | each client (once per join) | client entry LocalScripts |
| StarterCharacterScripts | each client (per character spawn) | character-specific client code |
| StarterGui | each client's PlayerGui | UI |
| Workspace | everyone | the 3D world |

Anything in ReplicatedStorage or Workspace can be read by exploiters. Secrets, admin lists, and authoritative logic stay on the server.

## Rojo file mapping (Rojo 7.2+)
| File | Becomes |
| --- | --- |
| `Name.server.luau` | Script |
| `Name.client.luau` | LocalScript |
| `Name.luau` | ModuleScript |
| `folder/init.luau` (`init.server.luau`, `init.client.luau`) | the folder itself becomes a ModuleScript (Script, LocalScript) |
| directory | Folder |

Instances without files (remotes, folders) can be declared in `default.project.json` with `$className`.
Commands: `rojo serve` (live sync to Studio via the Rojo plugin), `rojo build -o build.rbxlx` (place file).

## Client-server model
- Server: game rules, spawning, damage, currency, saving, round state.
- Client: input, camera, UI, visual effects, sound, prediction for responsiveness.
- RemoteEvent: one-way messages (`FireServer`, `FireClient`, `FireAllClients`).
- RemoteFunction: request-response. Avoid `InvokeClient` (a client can stall it forever).
- UnreliableRemoteEvent: frequent, loss-tolerant updates (cosmetic positions, effects).
- Attributes and ValueObjects replicate server → client automatically; good for simple state such as round phase and time left.

## Security checklist for every remote
1. Rate limit per player.
2. Check argument count and types (`RemoteGuard`).
3. Check game rules: does the player own this item? Is the target in range? Is the cooldown over? Can they afford it?
4. Compute outcomes on the server; send results back for display.
5. Ask: "If a client sent any value at any rate, what's the worst outcome?" and handle it.

## Data
- `UpdateAsync` whenever a write depends on the current value or several servers may write the same key; it counts against both read and write limits.
- Wrap DataStore calls in `pcall` with exponential backoff; process retries in order per key.
- Limits worth knowing: about 4 MB per key value; key and store names 50 characters; per-server request budgets grow with player count. Check the current limits in the DataStore docs before designing heavy usage.
- Save interval must be shorter than the session-lock timeout (`PlayerData`: autosave 60 s, lock 600 s).
- Version store names (`PlayerData_v1`) and migrate deliberately; never rename keys in place.
- Studio needs "Enable Studio Access to API Services" (Game Settings → Security) to use DataStores while testing.

## Module patterns
- One responsibility per module; return a table of functions.
- Pass dependencies in (services, clocks, wait functions) so modules run in tests.
- `export type` for shared shapes; `--!strict` at the top.
- Avoid deep `require` cycles: shared modules must not require server modules.

## Performance basics
- Avoid per-frame work on the server for many objects; batch on Heartbeat or a slower loop.
- Prefer events (`Touched`, `GetPropertyChangedSignal`) over polling, but debounce `Touched`.
- Enable StreamingEnabled for large maps; don't assume distant parts exist on the client.
- Use the MicroProfiler and Script Profiler in Studio to find hot spots before optimizing.
