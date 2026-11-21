# Balance models

## Progression curves
| Curve | Formula | Feels like | Typical use |
| --- | --- | --- | --- |
| Linear | `base + k(n-1)` | steady, predictable | short games, early levels |
| Polynomial | `base · n^p` (p ≈ 1.5-3) | accelerating but tame | XP per level, enemy HP |
| Exponential | `base · g^(n-1)` | explosive | idle and incremental costs |
| Logistic | `max / (1 + e^(-k(n-mid)))` | ramps then plateaus | difficulty that caps out |

Incremental games commonly use cost growth between about 1.07 and 1.15 per purchase. Lower feels generous; higher forces new income sources.

## Income vs. cost
- Time to next purchase = `cost(n) / income(n)`. Plot it; it should stay flat or rise gently.
- With cost `c·g^n` and income that grows by a multiplier `m` per purchase, the wait changes by `g/m` per purchase: `g > m` slows down, `g < m` speeds up.

## Combat
- Time to kill (first hit at t = 0): `(ceil(HP / damage) - 1) / attacks per second`.
- Damage per second: `damage × attacks per second × (1 + crit chance × (crit multiplier - 1))`.
- Effective HP against flat armor: changes how many hits a fight takes.

Armor models:
| Model | Formula | Behavior |
| --- | --- | --- |
| Subtractive | `max(1, dmg - armor)` | strong against many small hits; can trivialize enemies |
| Percentage | `dmg × 100 / (100 + armor)` | diminishing returns, never immune |
| Capped percent | `dmg × (1 - min(cap, armor%))` | simple, clear for players |

## Randomness
- Chance of at least one success in n tries: `1 - (1 - p)^n`.
- Expected tries: `1 / p`; tries for confidence q: `ceil(ln(1 - q) / ln(1 - p))`.
- A 1% item: about 1 in 3 players still lacks it after 100 tries. Add pity.
- Pity (guarantee on try N): expected tries = `Σ_{k=0}^{N-1} (1-p)^k`.
- Pseudo-random distribution: increase the chance after each miss and reset on hit; smoother streaks than pure chance.
- Shuffle bags (deck of outcomes): exact frequencies per cycle, no long droughts.

## Difficulty
- Target success rate on a challenge: often 60-80% for the main path, lower for optional content.
- Dynamic difficulty: adjust quietly (spawn rates, drop rates), and avoid changes players would read as cheating or could exploit, such as dying on purpose to weaken a boss.
- Rubber banding in races keeps groups close but can punish skill; cap it.

## Economy health checks
- Inflation: the currency's purchasing power should not collapse late game. Add sinks (consumables, repairs, upgrades with rising cost).
- Hoarding: if saving is always optimal, spending choices disappear. Add time-limited offers or decaying value carefully.
- Exploits: check loops where a buy-sell or craft-sell cycle yields profit.
