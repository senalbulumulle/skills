---
name: game-audio
description: Add sound effects and music to a game, with procedural SFX synthesized in code (Web Audio) or provided files, an audio event map, pitch variation, voice limits, mixing buses, ducking, adaptive music, and mute and volume settings. Use when a game is silent, needs jump, hit, coin, explosion, laser, UI, or power-up sounds, background music, or audio polish, or when its sound is repetitive, harsh, or too loud.
---

# Game Audio

Give every important event a sound that confirms it, without fatigue or clipping.

## Steps

1. **Map events to sounds** in a table, from the `game-feel` inventory if it exists:

   | Event | Sound | Priority | Variation | Max voices |
   | --- | --- | --- | --- | --- |

   Priority: player actions and threats first, ambience last.
2. **Make the sounds.** For web games use [sfx.js](assets/sfx.js): `Sfx.create()`, call `unlock()` from the first pointer or key event (browsers block audio until a user gesture), then `play("jump")`. Presets: `jump`, `coin`, `hit`, `explosion`, `laser`, `powerup`, `hurt`, `click`, `select`; add custom presets with the same fields. Recipes for new sounds are in [audio-design.md](references/audio-design.md). For engines or provided files, follow the same map with the engine's audio API.
3. **Prevent repetition fatigue.** Vary pitch about ±5-10% per play (`vary`, default 0.06), and keep 2-3 alternative sounds for the most frequent events.
4. **Limit voices.** Cap simultaneous instances per sound (preset `maxVoices`, default 4) so twenty bullets don't become one loud buzz.
5. **Mix with buses:** master, sfx, music (`setVolume`). Music sits below effects; important one-off sounds briefly duck the music. The synth's master compressor keeps stacked sounds from clipping.
6. **Add music** if the brief calls for it: a seamless loop, with a second layer or tempo change for higher intensity. Connect music sources to `sfx.musicBus`. Start it only after unlock.
7. **Expose settings**: a mute key (M) and volume sliders for music and effects, saved between sessions.

## Rules

- Every sound starts on the same step as its visual event.
- Sounds for frequent events are short, soft, and varied; rare events can be big.
- Never play audio before a user gesture on the web; it will be blocked or throw warnings.
- Leave headroom: if everything is loud, nothing is.

## Done when

- [ ] Every high-priority event in the map has a sound.
- [ ] Audio starts after the first click or key press, with no console warnings.
- [ ] Rapid repeated events don't stack into clipping or a wall of noise (voice limits work).
- [ ] Mute and volume settings work and persist.
