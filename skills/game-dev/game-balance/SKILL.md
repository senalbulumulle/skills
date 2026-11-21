---
name: game-balance
description: Balance game numbers with formulas and generated tables instead of guesses, covering difficulty curves, XP and level curves, economies, damage, health, time to kill, upgrade costs, and drop rates with pity timers. Use when tuning stats, designing progression, pricing upgrades, setting loot odds, or fixing a game that is too easy, too hard, too grindy, or has an overpowered strategy or item.
---

# Game Balance

Turn the experience you want into numbers, generate the tables, and keep every number in data.

## Steps

1. **State targets as numbers.** Examples: "an upgrade every 60-90 seconds early on", "a normal enemy dies in 2-3 hits", "a 10-minute session", "a rare item within about 30 runs". No target, no balancing.
2. **Map the economy.** List every source and sink of each resource:

   | Resource | Sources (rate) | Sinks (cost) | Net per minute |
   | --- | --- | --- | --- |

   Every source needs a sink, or the resource inflates until it means nothing.
3. **Choose curves.** Pick a formula per progression from [models.md](references/models.md) and generate it with `scripts/balance.py`:
   - `curve --type exp|poly|linear|logistic` for costs, XP, enemy stats.
   - `ttk` for hits and seconds to kill.
   - `drops` for loot odds, tries needed, and pity timers.
   Compare income against cost: time to afford the next upgrade = cost ÷ income per minute. It should match the step 1 target.
4. **Hunt dominant options.** For items, units, or upgrades that compete, compute value per cost (damage per second per gold, healing per mana). Anything clearly ahead of the rest is a dominant strategy: raise its cost, add a drawback, or give the others a niche.
5. **Put numbers in data.** All values go in a data file (`balance.json`, a CONFIG object, a spreadsheet export) loaded by the game, never in logic.
6. **Simulate, then play.** Where outcomes are random, simulate many runs (the `drops` command, or a small script). Then playtest and change one number at a time, recording each change and why.

## Rules

- Balance the first 10 minutes first; most players never see the rest.
- Exponential costs need exponential (or multiplicative) income; mixing exponential costs with linear income creates a hard wall.
- Prefer clear numbers players can reason about (10, 25, 50) over precise ones (13.7).
- Random rewards need a floor: pity timers or bad-luck protection for anything players chase.

## Done when

- [ ] Targets are written as numbers, and the generated tables meet them.
- [ ] Every resource has at least one source and one sink.
- [ ] Value-per-cost has been compared across competing options, with outliers fixed or justified.
- [ ] All balance numbers live in a data file.
- [ ] Random rewards have stated odds and, for chased items, a pity rule.
