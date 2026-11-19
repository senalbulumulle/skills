---
name: roblox-gameplay
description: Build Roblox gameplay systems that feel good and stay server-authoritative, including round loops, obby checkpoints, tycoon droppers, collectibles, combat with server-side hit validation, NPCs with PathfindingService, TweenService feedback, mobile-friendly UI and controls, and sounds. Use when adding mechanics, rounds, enemies, combat, UI, or polish to a Roblox game, or when Roblox gameplay feels laggy, unfair, or flat.
---

# Roblox Gameplay

Turn the design brief into systems where the server decides outcomes and the client makes them feel instant.

## Steps

1. **Split every mechanic into server truth and client feel.** Write one line per mechanic: what the server decides (damage, rewards, positions that matter) and what the client shows immediately (animation, sound, particles, UI). Patterns are in [systems.md](references/systems.md).
2. **Add the session structure.** For round-based games use [RoundSystem.luau](assets/RoundSystem.luau): drive `update(dt)` from a server Heartbeat connection, react in `onPhase`, call `endRound(reason)` from game logic. Publish the phase and time left to clients with attributes (for example on ReplicatedStorage) so UI updates without extra remotes.
3. **Build the core mechanic** with the patterns for its genre (checkpoints, droppers, collectibles, combat, NPCs). All requests go through validated remotes (see `roblox-scripting`); `Touched` handlers check that the toucher is a living character and debounce per player.
4. **Make it feel good on the client**: predict cosmetic effects locally (play the swing animation and sound on input, then let the server confirm the hit), use `TweenService` for UI and object motion, camera shake sparingly, and particle bursts on rewards. If the roblox-forge MCP server is connected, run `audit_feel` and give every action it lists a response.
5. **Build UI for every screen size**: `Scale`-based sizes, `UIAspectRatioConstraint`, `TextScaled` or `UITextSizeConstraint`, key buttons within thumb reach, and `Activated` instead of mouse-only events. Bind extra actions with `ContextActionService` so they get touch buttons and gamepad support.
6. **Test with real conditions**: in Studio, run a multi-client test (Test tab → Clients and Servers) and the device emulator for phones; check with simulated latency if available. Then use `roblox-playtest`.

## Rules

- Server decides; client predicts only what's safe to be wrong about (visuals, sounds).
- Validate positions and distances on the server for anything that grants rewards or damage.
- Every touch, click, and hit gets immediate feedback, even before the server confirms.
- No per-frame server loops over all parts; use events, collections (`CollectionService` tags), and slower ticks.

## Done when

- [ ] Each mechanic has a written server/client split, and rewards and damage are decided on the server.
- [ ] `Touched`-based systems debounce and verify the character.
- [ ] UI works on phone, tablet, and desktop sizes in the device emulator.
- [ ] A multi-client test shows no errors in the server or client output.
