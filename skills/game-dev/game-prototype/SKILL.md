---
name: game-prototype
description: Build a playable game prototype fast from a concept or design brief, core loop first, then win, lose, restart, and difficulty. Defaults to a single-file HTML5 canvas game with no build step, and adapts to Godot, Unity, Phaser, or an engine already in the repo. Use when asked to make, build, code, or prototype a game, a game jam entry, a playable demo, or a mechanic test.
metadata:
  anchors: "references/examples.md"
---

# Game Prototype

Get a playable build on screen in the fewest steps, then grow it one verified layer at a time.

## Steps

1. **Read the brief.** Use `docs/design-brief.md` if it exists. Otherwise pull from the request: core verb, goal, fail state, controls. If those are missing, answer them in three lines and state the assumptions; for a full concept use the `game-concept` skill.
2. **Pick the stack.** Use an engine already in the repo (detection table in [engines.md](references/engines.md)). With no engine and no stated preference, copy [canvas-template.html](assets/canvas-template.html) to `index.html`: one file, no install, runs from any static server.
3. **Build in layers.** After each layer, run the game and confirm it works before starting the next:
   1. The core verb works on screen with gray boxes.
   2. One goal or obstacle makes the verb matter.
   3. Fail, win, and instant restart (target under 2 seconds to play again).
   4. Score or progress is visible.
   5. Difficulty ramps over time or levels.
   6. Hand off to `game-feel` for polish.
4. **Follow the architecture rules** in [patterns.md](references/patterns.md): fixed-timestep update, all tunables in one `CONFIG`, input read as actions, scene state machine, seeded RNG, no allocation in hot loops once the loop works.
5. **Check before running.** For HTML games run `scripts/check_html.py index.html`, which syntax-checks every script and finds missing files. Fix everything it reports.
6. **Run it.** Serve with `python3 -m http.server` and open it. If a browser tool is available (Playwright, Chrome DevTools, a browser MCP), load the page, play one round, and read the console. Otherwise ask the user to play one round and report what they saw.

## Rules

- Gray boxes until the loop is fun. No art, menus, or settings screens before layer 5.
- Change one system at a time and re-run. Don't stack untested changes.
- Keep the template's `window.__game` hook; `game-playtest` reads state through it.
- When replacing the demo gameplay, keep the loop, input, scenes, and RNG.

## Done when

- [ ] `scripts/check_html.py` reports 0 problems (HTML games), or the engine builds with no errors.
- [ ] A full round plays: start, play, fail or win, restart, with no console errors.
- [ ] Restart fully resets state (score, entities, timers) on the third restart, not just the first.
- [ ] All tunable numbers live in `CONFIG` or a data file.
- [ ] The user is told how to run it and the controls.
