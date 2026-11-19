---
name: roblox-playtest
description: Test a Roblox game before publishing, covering Studio play and multi-client tests, server and client output errors, exploit and remote security review, DataStore save and rejoin checks, performance on phones, monetization and odds compliance, and a release checklist, using the Roblox Studio MCP server when connected. Use before publishing or updating a Roblox experience, when it has bugs, lag, exploits, or lost data, or when asked to test or QA a Roblox game.
---

# Roblox Playtest

Prove the experience works for real players on real devices before it ships.

## Steps

1. **Run it.** In Studio: Play (single player), then Test → Clients and Servers with 2-3 clients. If the Roblox Studio MCP server is connected, drive it directly: `start_stop_play` to run, `get_console_output` to read errors, `execute_luau` to inspect state, `screen_capture` to look, `user_keyboard_input` / `user_mouse_input` / `character_navigation` to play.
2. **Zero errors.** Read server and client output; every red error and every warning from your own scripts gets fixed or explained.
3. **Walk the checklist** in [checklist.md](references/checklist.md): join and leave flows, round transitions, death and respawn, rejoin with saved data, two players interacting, late joiners.
4. **Attack it.** For every remote, ask what happens if a client sends any value at any rate. From a temporary test LocalScript, fire each remote with wrong types, huge numbers, NaN, extra arguments, and at high rate, and confirm the server rejects them without errors. Check that nothing granting rewards trusts client-reported positions, damage, or prices. If the roblox-forge MCP server is connected, run `audit_remotes` and `map_remotes` on the project first and review every finding.
5. **Check data.** With API access enabled in Studio, change data, leave, rejoin: it must persist. Leave and rejoin quickly: no lost or duplicated data. Force a load failure (temporarily pass `PlayerData.new` a store whose `UpdateAsync` always errors; a wrong store name does not fail, it just opens an empty store) and confirm the player is kicked rather than given defaults.
6. **Check performance on low-end devices**: device emulator for phone screens; the MicroProfiler (View tab, or Ctrl+F6 on Windows) for frame spikes; part count, unanchored parts, and particle counts; memory over 10 minutes of play.
7. **Check compliance**: paid random items list all outcomes with odds summing to 100% before purchase (roblox-forge `check_odds` verifies the numbers); offers hidden when `ArePaidRandomItemsRestricted`; experience questionnaire and maturity settings filled in.
8. **Report** a severity table (blocker, major, minor, polish) with repro steps; fix blockers and majors; re-run steps 1-5.

## Rules

- Test with at least two clients; most multiplayer bugs don't appear solo.
- Never publish with known data-loss or exploit bugs.
- Re-test the full join → play → leave → rejoin flow after any change to data code.
- Report what wasn't tested (devices you don't have, real-money purchases) instead of implying it passed.

## Done when

- [ ] A multi-client test runs with zero script errors in server and client output.
- [ ] Every remote rejects malformed and spammed input in a test.
- [ ] Data persists across rejoin, and quick rejoin doesn't lose or duplicate it.
- [ ] Phone-size UI and frame rate are acceptable in the emulator or on a device.
- [ ] No blockers or majors remain; the report lists anything untested.
