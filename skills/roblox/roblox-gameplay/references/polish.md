# Effects, sound, and UI polish

Polished Roblox games answer every important moment with several layers at once, started on the client the frame the player acts. The server still decides the outcome; if it later disagrees, undo quietly.

## Layer each moment

| Moment | Particles | Sound | Motion |
|---|---|---|---|
| Button press | none | soft click | scale to 0.9, spring back (`Back`, about 0.18 s) |
| Hit or impact | spark burst (`Emit(8 to 15)`) | punchy hit, pitch varied | small camera shake, a 0.1 s flash on the target (Highlight) |
| Pickup or coin | burst where it was, glow while it waits | bright chime, pitch rising on streaks | counter rolls up, icon pops |
| Level-up or big reward | upward fountain plus a light | rising sting | full-screen flash, panel slides in |
| Dash or fast attack | trail on the limb or root | whoosh | short FOV kick (+5, back in 0.2 s) |
| Landing or despawn | smoke puff | thud | none |

Keep each response under 0.3 seconds so it never delays the next input, and size it to the moment: a coin is small, a level-up is the biggest thing on screen.

## Particles that look finished

- Give every emitter its own texture, color, and size; the default white sparkle reads as unfinished.
- Bursts: `Rate = 0`, then `emitter:Emit(n)` at the moment. Ambient: a low `Rate` (5 to 15).
- Glow: `LightEmission = 1` for sparks, magic, and energy; `LightInfluence = 1` for smoke and dust so they take the scene's lighting.
- Shape over time: `Size` and `Transparency` as NumberSequences that shrink or fade to the end, so particles never pop out.
- Value types: `Color` is a ColorSequence, `Size` and `Transparency` are NumberSequences, `Lifetime` and `Speed` are NumberRanges. A Color3 or a plain number errors at run time.
- Parent emitters to an Attachment to place them exactly, and reuse one emitter per effect instead of creating one per hit.

[effects-catalog.md](effects-catalog.md) lists the built-in textures and sounds and the editor range of each property.

## Sound

- Use real assets only: the built-in files in the catalog, the creator's uploads, or Creator Store audio (in Studio's Toolbox, or `search_asset` from Studio's MCP server). Never write an asset ID you haven't seen.
- Vary `PlaybackSpeed` by about ±8% so repeats don't sound mechanical, and stop the same sound from stacking within a few frames (`Juice.newSoundGate` in the roblox-scripting template does both).
- Put sounds in SoundGroups (music, effects, UI) so a settings menu can set each volume.
- For positional sounds, parent the Sound to a part or attachment. UI sounds need no position: parent them outside the 3D world, for example to SoundService.

## UI

- Size with Scale, cap scaled text with `UITextSizeConstraint`, and round corners with `UICorner`; `UIStroke` and `UIGradient` give buttons depth.
- Animate state changes: panels slide or fade in (0.2 to 0.25 s, `Quint` or `Sine`), buttons pop, numbers count up instead of jumping (`Juice.countUp`).
- Use a modern font (`Enum.Font.BuilderSans` or one that fits the game's style), not `Legacy` or `Arial`.
- Show results where the player is looking: damage numbers on the target, rewards near the counter they fill.

## Check

- Code: every sequence property gets a `ColorSequence` or `NumberSequence`, every range a `NumberRange`, and every value sits in the range [effects-catalog.md](effects-catalog.md) lists.
- Studio: play-test, watch each moment on a phone-sized device in the emulator, and check the Output window for errors.
