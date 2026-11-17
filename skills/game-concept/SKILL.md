---
name: game-concept
description: Generate original game concepts, score them, and turn the best one into a one-page design brief ready to build. Use when the user wants game ideas, a game jam concept, a core mechanic, a pitch, or says "help me design a game", or gives a theme, constraint, or genre to build a game around.
---

# Game Concept

Produce one original, buildable concept and a one-page brief that the `game-prototype` skill can build from.

## Steps

1. **Pin constraints.** Platform, input, session length, scope (jam / days / weeks), engine, theme. If platform or scope is unknown, ask one question; if the user wants speed, assume web + keyboard/mouse + 1-week scope and say so.
2. **Diverge.** Write 6 concepts, each from a different generator in [idea-generators.md](references/idea-generators.md). Each concept is 4 lines:
   - Hook: one sentence a stranger would repeat.
   - Core verb: what the player does every few seconds.
   - Twist: the rule that makes this verb new.
   - 30-second loop: act, consequence, reward.
3. **Check originality.** For each concept name the closest existing games and the difference. Drop or change any concept that is a reskin. Never recreate a specific existing game, its characters, levels, or look.
4. **Score and pick.** Rate 1-5 per concept and show the table:

   | Concept | Verb fun in gray boxes | Novelty | Scope fit | One-sentence clarity | Feedback potential | Total |
   | --- | --- | --- | --- | --- | --- | --- |

   Pick the top total; break ties on "verb fun in gray boxes". State why in one line. If the user is present, let them override.
5. **Stress-test the pick** and fix every hole before writing it down:
   - Second 1, minute 1, minute 10: what is the player doing, and is it still interesting?
   - Is there a dominant strategy or a way to stall?
   - How does the player fail, and does failing teach them?
   - What skill improves with practice?
6. **Write the brief.** Fill [design-brief.md](assets/design-brief.md) and save it to `docs/design-brief.md` (or the path the user gives). Keep it to one page.

## Rules

- Mechanics before theme: a concept must be fun as gray boxes. Theme should explain the mechanic, not decorate it.
- One core verb. Every other feature must make that verb more interesting or it goes on the cut list.
- MVP list has at most 5 items. Everything else is "later" or "cut".

## Done when

- [ ] The table of 6 scored concepts is shown, with closest-existing-game comparisons.
- [ ] The core loop of the pick fits in one sentence.
- [ ] The brief exists at the stated path, fits one page, and has an MVP list of 5 or fewer items and a cut list.
- [ ] Every stress-test question has an answer in the brief.
