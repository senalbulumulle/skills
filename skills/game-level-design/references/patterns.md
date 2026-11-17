# Level design patterns

## Layout patterns
- **Gate and key:** a visible locked door before the key, so finding the key has meaning.
- **Loop with shortcut:** a long route that opens a shortcut back to the start; rewards exploration and cuts backtracking.
- **Hub and spoke:** a safe central area with branches; good for choice and pacing.
- **Risk-reward branch:** a harder side path with a better reward, visible from the main path.
- **Landmarks:** one unique, visible object per area, so players can orient themselves.
- **Foreshadowing:** show an area or enemy before the player can reach it.
- **Breadcrumbs:** pickups or light that trace the intended path.
- **Arena lock:** close the exits for a fight, reopen on completion, clearly signalled.

## Difficulty knobs
Change one at a time between levels:
- Time pressure (timers, chasing hazards)
- Precision (smaller platforms, narrower gaps)
- Density (more enemies or hazards)
- Variety (more kinds of threats at once)
- Information (darkness, fog, hidden routes)
- Recovery (fewer checkpoints, less health)

## Puzzle design
- One insight per puzzle. The "aha" is the content; everything else is noise.
- Show all the pieces. Hidden information makes puzzles guessing games.
- Red herrings sparingly, and never in teaching levels.
- Hard puzzles: small boards. Size multiplies trial and error, not insight.
- Test that the intended solution is the only one, or accept the alternatives on purpose.

## Checkpoints and failure
- Respawn close to the failure point; repeating solved parts is padding.
- Restart in under 2 seconds.
- Save progress at the start of each level and after long sections.

## Level data formats

ASCII grid (top-down, grid, or tile-based platformers):
```
; legend: # wall, S start, G goal, a key, A door, ^ spikes, o coin, E enemy
##########
#S..o..#G#
#.####.#A#
#..^...a.#
##########
```
Check with `scripts/check_level.py levels/1-1.txt --keys a`: lines starting with `;` are skipped, `--keys a` makes `a` a key that opens door `A`, every other symbol (`o`, `E`, `^`) counts as floor, and `--wall` changes the wall character. Have the game's loader skip `;` lines too.

JSON (free-form or physics levels):
```json
{
  "id": "1-3",
  "purpose": "teaches bounce pads before introducing spikes",
  "spawn": [64, 320],
  "goal": [960, 128],
  "entities": [{ "type": "pad", "x": 300, "y": 352, "power": 1.4 }]
}
```
