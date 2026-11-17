---
name: game-playtest
description: Playtest and verify a game before calling it done, by running it, catching console errors and exceptions, measuring frame rate, testing every state transition and edge case, automating smoke runs with Playwright, reviewing design issues, and writing a prioritized fix list. Use when a game is "finished", before a release or jam submission, when it has bugs or performance problems, or when asked to test, QA, or review a game.
---

# Game Playtest

Prove the game works by running it, then report problems in priority order and fix the blockers.

## Steps

1. **Run it.** Serve it (`python3 -m http.server`) or launch it in its engine. A game that hasn't been run hasn't been tested.
2. **Automate the smoke test** for browser games: copy [playtest.mjs](scripts/playtest.mjs) into the project, run `npm install --no-save playwright-core` there, then:
   ```sh
   node playtest.mjs http://localhost:8000/ --seconds 20 --screenshot playtest.png
   ```
   It starts the game, mashes keys, restarts several times, and fails on console errors, exceptions, low frame rate, or (via `window.__game`) state that doesn't reset. Use `--chrome PATH` for a local Chrome, `--keys` and `--start` for custom controls. Look at the screenshot.
3. **Walk the state matrix** by hand or with a browser tool. Full list in [checklist.md](references/checklist.md); the essentials:
   - Boot, title → play, pause → resume, fail → restart three times, win.
   - Resize the window, switch tabs and come back, unfocus mid-input.
   - Mash every key, hold all keys at once, click outside the game.
4. **Check performance**: average frame rate, worst frames, and whether entity counts or memory grow without limit over a few minutes of play.
5. **Review the design** with fresh eyes: does the first 30 seconds teach the core verb without text? Do deaths feel fair? Can the player stall, cheese, or softlock?
6. **Report** as a table, highest severity first:

   | Severity | Problem | Repro steps | Fix |
   | --- | --- | --- | --- |

   Severities: blocker (crash, softlock, can't finish), major (wrong behavior, big frustration), minor, polish.
7. **Fix blockers and majors**, then re-run steps 2-4. Repeat until no blockers remain.

## Rules

- Reproduce before fixing; write the exact repro steps.
- Fix the cause, not the symptom (a restart bug usually means state that isn't reset in one place).
- Re-test everything a fix touches, plus the full smoke test.
- Report honestly: list what wasn't tested and why.

## Done when

- [ ] The game ran, and the automated smoke test (or a manual run for non-browser engines) passes with 0 console errors.
- [ ] Every row of the state matrix was exercised.
- [ ] No blockers or majors remain open; minors and polish are listed for the user.
- [ ] The report states what was not tested.
