---
name: game-feel
description: Add game feel (juice) to a working game, starting with responsive controls, then hit stop, screen shake, easing, squash and stretch, particles, flashes, and feedback for every player action, with an accessibility toggle. Use when a game feels flat, floaty, stiff, unresponsive, or boring, or when asked to polish, juice up, add impact, or make a game feel good.
---

# Game Feel

Make every player action feel responsive and every event readable, without drowning the game in noise.

## Steps

1. **Inventory.** Play or read the code and fill a table of every player action and game event:

   | Event | How often | Importance | Current feedback | Planned feedback |
   | --- | --- | --- | --- | --- |

2. **Controls first.** Juice can't fix bad controls. Apply only what fits the genre (starting values in [tuning.md](references/tuning.md)):
   - Acceleration and deceleration instead of instant speed (or deliberately instant for precise games).
   - Platformers: coyote time, jump buffering, variable jump height, faster fall than rise.
   - Read input every step; never drop a press made between updates.
3. **Layer feedback by importance.** The bigger or rarer the event, the bigger the reaction. Frequent events (footsteps, small pickups) get small, cheap feedback; rare events (boss hit, death, level clear) get the full stack:
   - Visual: flash, squash and stretch, particles, color change.
   - Motion: hit stop, screen shake, knockback, camera nudge.
   - Audio: a sound per event (use `game-audio`).
   - UI: number popups, bar animations, eased transitions.
4. **Use the helpers** in [juice.js](assets/juice.js): `Tweens`, `ease`, `Shake` (trauma-based), `HitStop`, `Flash`, `Squash`, `Particles` (pooled), `Popups`, `JumpAssist`. Drive them all from the game's update with `dt` in seconds.
5. **Wire it cleanly.** Put every juice value in `CONFIG.juice`. Add a key that toggles all juice off, and compare with and without; each effect must earn its place.
6. **Respect players.** Add a "reduce motion" option that disables shake and large camera moves. Never flash the full screen more than 3 times per second. Don't shake on frequent events.

## Rules

- Hit stop and shake apply to the game world, not the UI.
- Scale reactions to magnitude: a 5-damage hit and a 50-damage hit should feel different.
- Anticipation, action, follow-through: wind-ups make big actions readable.
- One effect at a time, tested in play, before adding the next.

## Done when

- [ ] Every row of the inventory table has planned feedback, and the important ones are implemented.
- [ ] Controls changes are tested by playing, not just coded.
- [ ] The juice toggle and reduce-motion option both work.
- [ ] No full-screen flash exceeds 3 per second; frequent events don't shake the screen.
- [ ] All juice values live in `CONFIG.juice`.
