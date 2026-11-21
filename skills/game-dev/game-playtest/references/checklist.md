# Playtest checklist

## Boot and flow
- [ ] Loads with no console errors or 404s (including favicon and fonts).
- [ ] Title screen explains how to start.
- [ ] Every scene has a way forward and a way out (no dead ends).
- [ ] Pause and resume work; the game doesn't advance while paused.
- [ ] Fail → restart works three times in a row with identical starting state.
- [ ] Win condition is reachable and shows a clear result.
- [ ] High score or progress saves and survives a reload; a broken or blocked storage doesn't crash the game.

## Input
- [ ] Every action works with every supported input (keyboard, mouse, touch, gamepad).
- [ ] Holding all keys at once doesn't break movement or state.
- [ ] Key mashing during scene transitions doesn't skip screens or double-trigger.
- [ ] Losing focus (tab switch, alert) releases held keys and pauses.
- [ ] Browser shortcuts aren't hijacked beyond the game's keys (arrows and space can scroll the page if not prevented).
- [ ] Touch: no page scroll or zoom while playing.

## Display
- [ ] Resizing keeps the game centered and correctly scaled.
- [ ] Sharp on high-DPI screens.
- [ ] Text is readable at the smallest supported window size.
- [ ] Nothing important renders off screen at unusual aspect ratios (ultrawide, portrait phone).

## Edge cases
- [ ] Dying and winning on the same frame.
- [ ] Collecting the last item while taking damage.
- [ ] Pausing during transitions, hit stop, or death animation.
- [ ] Long sessions: timers, scores, and spawn rates stay sane after 10+ minutes.
- [ ] Very fast and very slow frame rates (throttle the CPU in DevTools): physics stays stable.

## Performance
- [ ] Average frame rate at or near the display rate; no regular hitches.
- [ ] Entity, particle, and listener counts plateau instead of growing forever.
- [ ] Memory stays flat over several minutes (DevTools Memory → heap snapshots).
- [ ] Audio voice counts stay bounded during heavy action.

## Design
- [ ] The core verb is understood within 30 seconds without reading.
- [ ] Every death has a visible cause the player could have avoided.
- [ ] No dominant strategy trivializes the game.
- [ ] No way to stall forever or farm infinitely (unless intended).
- [ ] Difficulty rises at the intended pace (compare to the level pacing table).

## Accessibility
- [ ] Reduce-motion option disables shake and big camera moves.
- [ ] No more than 3 full-screen flashes per second.
- [ ] Gameplay information doesn't rely on color alone.
- [ ] Audio can be muted; volume settings persist.

## Release
- [ ] Debug overlays and cheats are off by default.
- [ ] Credits and licenses for third-party assets are listed.
- [ ] Runs from a fresh clone or the built output on a clean static server.
