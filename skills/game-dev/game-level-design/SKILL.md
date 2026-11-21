---
name: game-level-design
description: Design levels, stages, and progression that teach mechanics through play, pace difficulty, and are stored as checkable data. Includes a solver that verifies grid levels are completable. Use when creating levels, worlds, stages, maps, puzzles, tutorials, onboarding, or a difficulty curve, or when players get stuck, bored, or lost.
---

# Game Level Design

Turn a game's mechanics into a sequence of levels that teaches, escalates, and stays solvable.

## Steps

1. **List the mechanics** and every combination worth exploring. Order them so each level introduces at most one new idea.
2. **Teach each mechanic in four beats** across one or several levels:
   1. Introduce it where failure is safe and the solution is obvious.
   2. Practice it with light pressure.
   3. Twist it: a new context or a surprising use.
   4. Test it: combine it with earlier mechanics under real pressure.
   No text tutorial if a level can teach it.
3. **Plan pacing** as a table, one row per level: new idea, intensity 1-5, estimated play time, rest beat (yes/no). Alternate tension with release; each rise peaks higher than the last (a sawtooth, not a straight ramp).
4. **Write levels as data**, not code: ASCII grids or JSON in `levels/`, with the legend in `;` comment lines at the top. Data levels are diffable, quick to edit, and checkable. Patterns and formats are in [patterns.md](references/patterns.md).
5. **Check every grid level** with `scripts/check_level.py levels/*.txt` (`--keys ab` when key `a` opens door `A`, and so on; `--diagonal` for 8-way movement). Fix unreachable goals and unintended unreachable areas. For platformers and physics games, which the script can't solve, play each level once and record the result.
6. **Playtest the sequence** (use `game-playtest`): watch where players hesitate, die repeatedly, or skip content, then adjust the level, not the player.

## Rules

- The intended path should be readable: lead with light, color, landmarks, and sightlines.
- One new idea per level. Combinations count as new ideas.
- Every level has a purpose you can say in one sentence ("teaches wall jump under a time limit").
- Let early levels be short; a fast first win hooks players.
- Avoid unavoidable surprise deaths: telegraph hazards before they can kill.

## Done when

- [ ] The pacing table exists, and every level has a one-sentence purpose.
- [ ] Each mechanic goes through introduce, practice, twist, test.
- [ ] `scripts/check_level.py` passes for every grid level, or non-grid levels each have a recorded completion.
- [ ] Levels are stored as data files with a legend.
