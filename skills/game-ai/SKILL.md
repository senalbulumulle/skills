---
name: game-ai
description: Design and code enemy, boss, and NPC behavior that is fun to play against, with readable telegraphs, fair attack timing, state machines, steering, A* pathfinding, line of sight, utility AI, and limits on simultaneous attackers. Use when adding enemies, bosses, NPCs, companions, or AI opponents, or when enemies feel dumb, unfair, repetitive, or too easy to cheese.
---

# Game AI

Build opponents that create interesting decisions for the player. The goal is fun, not intelligence.

## Steps

1. **Give each enemy a job.** Write one line per enemy type: what player skill it tests (aiming, dodging, positioning, priority) and how it differs from the others. Archetypes are in [patterns.md](references/patterns.md).
2. **Design the attack rhythm.** Every attack follows telegraph → attack → recovery:
   - Telegraph long enough to react to (start around 0.4-0.8 s; shorter only for late-game enemies).
   - Recovery is the player's punish window; it is what makes fights feel fair.
   - Show the telegraph with motion, color, and sound together.
3. **Pick the architecture.** Use the simplest that fits:

   | Need | Use |
   | --- | --- |
   | A few clear behaviors | `StateMachine` (aim for 6 states or fewer per enemy) |
   | Many situational choices | utility scoring with `chooseAction` |
   | Deep, reusable behavior sets | behavior tree (see patterns) |

4. **Add movement** from [ai.js](assets/ai.js): `seek`, `flee`, `arrive`, `wander`, `separation` for steering; `findPath` (A*, 4- or 8-way, no corner cutting) for grids; `lineOfSight` before chasing or shooting. Recompute paths on a timer (around 0.25-0.5 s) or when the target changes cell, not every frame.
5. **Make crowds fair.** Use `AttackTokens` so only a few enemies attack at once while others reposition. Enemies off screen don't attack. Deliberate aim error for ranged enemies.
6. **Make it visible.** Add a debug view: current state, path, sight lines, and attack token holders. Tune by watching it.
7. **Tune in data.** Speeds, ranges, telegraph and recovery times, and aggression live in a data table per enemy type.

## Rules

- Readable beats smart: players should be able to predict and learn every enemy.
- Never punish what the player couldn't see or hear.
- Vary encounters by mixing simple enemies, not by making one enemy complex.
- Bosses are a sequence of learnable patterns with phase changes, each phase adding one new idea.

## Done when

- [ ] Every enemy type has a one-line job and a data table entry.
- [ ] Every attack has a telegraph and a recovery window, both tested in play.
- [ ] No more than the configured number of enemies attack at once.
- [ ] Paths are not recomputed every frame, and enemies don't get stuck on corners (checked in the debug view).
- [ ] The debug view can be toggled on and off.
