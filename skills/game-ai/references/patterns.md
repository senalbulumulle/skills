# Enemy and AI patterns

## Archetypes
| Archetype | Tests | Behavior |
| --- | --- | --- |
| Chaser | movement, kiting | approaches directly; dangerous in groups |
| Shooter | dodging, cover | keeps distance, fires telegraphed shots |
| Charger | timing | winds up, dashes in a straight line, stuns itself on walls |
| Tank | damage focus | slow, high health, blocks paths |
| Swarmer | area control | weak, many, uses separation |
| Support | target priority | heals, shields, or buffs others; flees when approached |
| Trapper | awareness | places hazards that persist |
| Ambusher | attention | hides until close; must have a tell (sound, shimmer) |

Mixing two or three archetypes per encounter creates more decisions than one complex enemy.

## A typical melee state machine
```
idle ──sees player──▶ chase ──in range & has token──▶ windup ──time──▶ attack ──time──▶ recover ──time──▶ chase
  ▲                     │                                                                      
  └──lost sight 3 s─────┘                       (hit while in windup? optional stagger state)
```
Store timings per state in data: windup 0.5 s, attack 0.15 s, recover 0.6 s.

## Behavior trees (when state machines get tangled)
- Selector: try children in order; succeed on the first success. ("Flee if low health, else attack if in range, else chase.")
- Sequence: run children in order; fail on the first failure. ("Has line of sight → aim → shoot.")
- Decorators: invert, repeat, cooldown, time limit.
- Leaves: conditions (checks) and actions (may return running).
Tick the tree a few times per second, not every frame, unless actions need it.

## Utility AI
Score every action 0-1 from curves of inputs (distance, health, ammo, cover), multiply the factors, and pick the highest. Add small random noise or a "momentum" bonus for the current action to prevent flip-flopping each tick.

## Boss design
- 2-4 phases, each triggered by health thresholds; announce phase changes clearly.
- Each phase: 2-3 attacks, one new.
- Cycle attacks in learnable but not fully fixed orders (shuffle bag of patterns).
- Safe windows after big attacks; damage windows clearly shown.
- Final phase can speed up timings by about 10-25%, but keep telegraphs readable.

## Pathfinding at scale
- Many units to one target: a flow field (one BFS from the target, every unit follows the gradient) beats per-unit A*.
- Large open maps: path on a coarse grid or navmesh, steer locally with `separation`.
- Stuck detection: if an agent hasn't moved more than a small distance in 1-2 seconds, repath or nudge.

## Difficulty knobs
Reaction delay, aim error, telegraph length, recovery length, aggression (attack token count), movement speed, health. Change telegraphs and recovery before raw stats: speed and health inflate tedium; timing changes skill.

## Perception
- Vision cone plus `lineOfSight`; hearing radius for noise events.
- Last-known position: when sight is lost, go there and search briefly instead of instantly knowing where the player is.
- Alert states (unaware → suspicious → alert) with visible indicators.
