# Tuning starting points

These are common starting values, not rules. Tune by playing; change one value at a time.

## Movement
| Parameter | Start | Notes |
| --- | --- | --- |
| Time to full speed | 0.05-0.15 s | Shorter for precise games, longer for heavy characters |
| Time to stop | 0.03-0.1 s | Stopping faster than starting feels responsive |
| Air control | 50-80% of ground | 100% feels floaty-but-precise; low feels committed |

## Jumping (platformers)
| Parameter | Start | Notes |
| --- | --- | --- |
| Coyote time | 0.08-0.12 s | Jump allowed shortly after leaving a ledge |
| Jump buffer | 0.1-0.15 s | Early press executes on landing |
| Fall gravity | 1.5-2.5x rise gravity | Snappy arcs instead of moon jumps |
| Variable height | cut upward velocity by 40-60% on release | Short tap = small hop |
| Max fall speed | clamp it | Keeps landings readable |

Derive gravity from the jump you want: `g = 2h / t²`, `v0 = 2h / t`, where `h` is jump height and `t` is time to apex.

## Impact
| Effect | Light hit | Heavy hit / kill |
| --- | --- | --- |
| Hit stop | 0.03-0.05 s | 0.08-0.15 s |
| Shake trauma (`Shake.add`) | 0.1-0.2 | 0.4-0.7 |
| Flash on target | 0.05 s | 0.1 s |
| Knockback | small, 1-2 frames of travel | large, with brief stun |
| Particles | 4-8 | 16-40 |

Shake model: offset = max × trauma²; trauma decays linearly (about 1.5 per second). Squaring keeps small hits subtle and big ones dramatic. Typical max offset: 8-16 px at 360p logical resolution; max rotation 2-4 degrees (0.03-0.07 rad).

## Squash and stretch
- Jump take-off: stretch +0.2 to +0.3. Landing: squash −0.2 to −0.35, scaled by fall speed.
- Keep volume: `scaleX = 1 / scaleY` (the `Squash` helper does this).
- Anchor at the feet when squashing, or characters appear to sink.

## Tweens and UI
| Use | Duration | Easing |
| --- | --- | --- |
| Button hover / press | 0.08-0.12 s | outQuad |
| Panel in / out | 0.2-0.3 s | outCubic in, inQuad out |
| Score count-up | 0.3-0.6 s | outCubic |
| Item pop / reward | 0.3-0.5 s | outBack |
| Bouncy celebration | 0.5-0.8 s | outElastic (sparingly) |

## Camera
- Follow with damping (`damp` helper, rate around 0.001-0.01) instead of locking to the player.
- Look-ahead in the movement direction: 10-20% of screen width.
- Dead zone in the middle of the screen so small moves don't move the camera.

## Audio-visual sync
The sound, flash, and hit stop of one impact start on the same step. Delayed feedback reads as lag.

## Accessibility
- Reduce-motion option: disable shake, scale down camera moves and parallax.
- Flashing: no more than 3 full-screen flashes in any one second.
- Don't rely on color alone for important feedback; pair it with shape, motion, or sound.
