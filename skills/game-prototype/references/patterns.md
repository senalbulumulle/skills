# Prototype architecture patterns

## Fixed-timestep loop
Update the simulation at a constant step; render as often as the display allows.

```js
let acc = 0, last = performance.now();
function frame(now) {
  let dt = Math.min((now - last) / 1000, 0.25); // clamp: avoid the spiral of death after a stall
  last = now;
  acc += dt;
  while (acc >= STEP) { update(STEP); acc -= STEP; }
  render(acc / STEP); // alpha: interpolate between previous and current positions
  requestAnimationFrame(frame);
}
```
- Store `px, py` before moving and draw `lerp(px, x, alpha)` for smooth motion on high-refresh displays.
- Clear "pressed this step" input after each `update`, not each frame, so taps aren't lost at 144 Hz.

## Scene state machine
`title → play ⇄ paused → over → play`. One `scene` string and one switch in `update` and `render`. Every scene has a way out (no dead ends).

## Input as actions
Map keys, buttons, and touch to named actions (`left`, `jump`, `action`). Game code never reads key codes. Release all held input on window blur.

## Data-driven tuning
All numbers in `CONFIG` (or JSON loaded at start). Never inline speeds, timers, or costs in logic.

## Seeded randomness
One seeded RNG per run (mulberry32 in the template). Log the seed in debug view; set `CONFIG.seed` to replay a bug.

## Entities
Plain objects in arrays per type. Remove by iterating backwards with `splice`, or swap-and-pop when order doesn't matter. Use a spatial grid only when collision checks show up in profiling (roughly hundreds of entities).

## Collision
- AABB: `|ax - bx| < (aw + bw) / 2 && |ay - by| < (ah + bh) / 2`
- Circle: `dx*dx + dy*dy < (ar + br) ** 2` (no square root)
- Fast movers tunnel through thin walls: move in sub-steps or sweep the shape.

## Object pools
When bullets or particles are created every frame, reuse dead objects from an array instead of allocating, to avoid garbage-collection hitches.

## Pause and focus
Pause on blur and `visibilitychange`. Clamp `dt` so returning to the tab doesn't run seconds of simulation at once.

## Debug overlay
Toggle with a key (the template uses the backtick key): FPS, entity counts, seed, current state. Leave it in; it costs nothing when off.
