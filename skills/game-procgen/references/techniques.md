# Procgen techniques

## Rooms and corridors
Place random non-overlapping rooms, then connect them. `rooms()` chains rooms left to right with L-shaped corridors, so all rooms connect.
- Extra loops: after chaining, connect a few random non-adjacent pairs; loops reduce backtracking.
- Start in the leftmost room, exit in the room farthest by path distance (BFS), not straight-line distance.

## BSP dungeons
Split the map rectangle recursively (alternating or random axis, split between 40% and 60%) until leaves reach a minimum size. Put one room per leaf; connect sibling leaves bottom-up. Gives even coverage and no overlaps by construction.

## Cellular automata caves
Fill about 45% walls at random, then run 4-6 smoothing steps with the 4-5 rule (a wall stays a wall with ≥4 wall neighbours; floor becomes wall with ≥5). Always follow with `keepLargestRegion` or connect regions with tunnels, because the automaton leaves isolated pockets.
- More fill or more steps: tighter, chunkier caves.
- Run 1-2 extra steps with a "fill tiny holes" rule for smoother walls.

## Noise terrain
- `fbm(noise, x * scale, y * scale)`, scale around 0.01-0.1 per tile. Octaves 4-6, lacunarity 2, gain 0.5 are standard starting points.
- Biomes: threshold height (water below 0.35, sand to 0.4, grass to 0.65, rock above). Use a second noise map for moisture to pick biomes in two dimensions.
- Islands: subtract distance from center so edges fall into water.
- Value noise (in `procgen.js`) is blockier than gradient noise (Perlin, simplex); with fbm the difference is small for most games.

## Poisson disk sampling
Points no closer than `radius`, filling space evenly. Use for trees, rocks, enemy spawns, and item scatter; looks natural, never clumped. Filter points afterward by terrain (no trees in water).

## Wave function collapse (tiled model)
1. Define tiles and which tiles may sit next to each other on each side.
2. Every cell starts with all tiles possible.
3. Repeatedly pick the cell with the fewest options (lowest entropy, random tie-break), collapse it to one tile by weight, and propagate: remove now-impossible options from neighbours, repeatedly.
4. On contradiction (a cell with zero options), restart with a new seed or backtrack.
Pre-place fixed tiles (entrance, exit) before collapsing to force structure. Keep the tileset small at first; contradictions grow with rule complexity.

## Weighted tables and shuffle bags
- Loot: `rng.weighted([{ item: "potion", weight: 60 }, { item: "sword", weight: 5 }])`.
- Rarity tiers first, then item within tier: easier to tune than one big table.
- Shuffle bag: put N outcomes in a list, `rng.shuffle`, draw in order, refill when empty. Exact frequencies, no droughts. Good for spawn patterns and power-ups.

## Authored chunks
Hand-design small rooms or segments with marked connection points; the generator picks and links them. Most of the variety of random generation with designed quality. Validate that connection points line up.

## Names and text
- Syllable lists: `prefix + middle? + suffix` per culture or faction.
- Markov chains on example names (order 2-3) for natural-sounding variants; filter out real words and duplicates.

## Validation measures
For every generator, track over many seeds: success rate of guarantees, path length start→exit, floor or open-area share, number of rooms or regions, spawn distances. Plot or print min, max, and average, and investigate the extremes, because that's where broken levels hide.
