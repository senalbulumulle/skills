---
name: roblox-game-design
description: Design original Roblox experiences built for how Roblox is played, with social multiplayer sessions, a hook in the first minute, mobile-first controls, retention loops, and fair, policy-compliant monetization (game passes, developer products, disclosed odds for paid random items). Produces a one-page brief. Use when planning a Roblox game, choosing a Roblox genre, designing progression or monetization for Roblox, or improving a Roblox game's retention.
---

# Roblox Game Design

Design an original Roblox experience that is fun with friends, clear in the first minute, and monetized fairly.

## Steps

1. **Pin the frame.** Target devices (assume phones are a large share of players unless the user knows otherwise), session length, party size (solo, 2-4, server-wide), and genre family. Genre loops and their pitfalls are in [genres.md](references/genres.md).
2. **Find the original twist.** Write 4 concepts, each a familiar Roblox genre plus one new rule, theme, or social mechanic. Name the closest existing experiences for each and the difference. Never copy another experience's name, map, characters, or look.
3. **Design the first minute.** A new player spawns, understands what to do without reading, acts within 10 seconds, and gets a reward within 60 seconds. Write it as a timeline.
4. **Make it social.** At least one reason to play with others: cooperation, competition, trading, showing off (cosmetics, leaderboards), or shared building. Decide what other players see of each other.
5. **Plan retention.** Short loop (seconds), session goal (minutes), long goal (days): for example collect → upgrade → unlock a new area. Add a reason to return (daily reward, timed events, friend invites) that doesn't punish missing a day.
6. **Plan monetization fairly** using [monetization.md](references/monetization.md): game passes for permanent perks, developer products for consumables, cosmetics first. Paid random items must show every outcome and its odds as percentages summing to 100% (roblox-forge `check_odds` verifies a table). Never sell outright power that ruins play for non-payers.
7. **Write the brief** with [roblox-brief.md](assets/roblox-brief.md) to `docs/design-brief.md`, then build with `roblox-scripting` and `roblox-gameplay`.

## Rules

- Controls must work on touch with the default thumbstick and jump button, plus at most a few large on-screen buttons.
- Readable from far away: strong silhouettes, bright landmarks, clear signs; many players are on small screens.
- Respect players' time and money: no dark patterns (fake timers, confusing currencies, pressure to buy mid-failure).
- Keep scope to what one developer can finish: one core loop, polished, beats five half-built modes.

## Done when

- [ ] The brief exists, with the first-minute timeline, social hook, three loop lengths, and monetization plan.
- [ ] Closest existing experiences are named with the difference for the chosen concept.
- [ ] Every paid random item in the plan lists all outcomes with odds summing to 100%.
- [ ] The core loop works with touch controls as designed.
