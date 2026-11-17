---
name: game-procgen
description: Generate game content procedurally with seeded randomness, including dungeons, caves, terrain, object placement, loot tables, and variety, with guarantees such as connectivity checked over many seeds. Use when the user wants random or infinite levels, roguelike maps, noise terrain, wave function collapse, replayability, or generated items, enemies, or names.
---

# Game Procgen

Generate content that is varied but always valid, and reproducible from a seed.

## Steps

1. **Split guarantees from variety.** Write down what must always hold (start connects to exit, a key spawns before its door, no enemy on the spawn tile, 3-6 rooms) and what may vary. Guarantees get code and checks; variety gets randomness.
2. **Pick the technique** that fits the content (details in [techniques.md](references/techniques.md)):

   | Content | Technique |
   | --- | --- |
   | Dungeons with rooms | rooms and corridors, or BSP |
   | Caves, organic spaces | cellular automata, then keep the largest region |
   | Terrain, biomes, height | noise with fbm, thresholds per biome |
   | Even object placement | Poisson disk sampling |
   | Tile-consistent layouts | wave function collapse |
   | Loot, enemies, events | weighted tables, shuffle bags |
   | Hand-made feel | authored chunks stitched together randomly |

3. **Use the helpers** in [procgen.js](assets/procgen.js): `makeRng` (with `weighted`, `shuffle`, `fork`), `makeNoise2D` and `fbm`, `caves`, `rooms`, `regions`, `keepLargestRegion`, `poissonDisk`, `toText`.
4. **Seed everything.** One root seed per run; `rng.fork(n)` gives each subsystem its own stream so changing loot code doesn't reshape maps. Show the seed in the debug overlay and allow replaying it.
5. **Write generators as pure functions**: `(seed, params) → data`. No reading game state, no `Math.random`, no drawing. This makes them testable and replayable.
6. **Validate at scale.** Generate 1,000 seeds in a test or script and assert every guarantee; print min, max, and average of key measures (room count, path length, floor share). Fix the generator until all seeds pass. A bounded retry ("regenerate up to 10 times") is a fallback, not a fix.
7. **Look at the output.** Print maps with `toText` or render thumbnails of 20 seeds side by side, and check that they look varied and intentional, not like noise.

## Rules

- Randomness serves design: every random choice should produce something a designer would accept.
- Never `Math.random` inside generators; it breaks seeds.
- Prefer constraints that make bad outputs impossible over checks that reject them.
- Mix authored and generated content; fully random content tends to feel samey.

## Done when

- [ ] Guarantees are written down and asserted over at least 1,000 seeds with 0 failures.
- [ ] The same seed produces identical output on every run.
- [ ] Generators are pure functions of seed and parameters.
- [ ] A visual sample of outputs was reviewed for variety.
