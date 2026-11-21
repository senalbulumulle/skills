# Audio design reference

## Sound recipes (sfx.js preset fields)
| Sound | Wave | Pitch | Length | Extra |
| --- | --- | --- | --- | --- |
| Jump | square or triangle | rising, e.g. 220 → 660 Hz | 0.1-0.2 s | |
| Land | noise | — | 0.05-0.1 s | lowpass 800 → 200 Hz |
| Coin / pickup | square | two quick rising notes | 0.2-0.3 s | `slide: "step"` |
| Shoot / laser | sawtooth or square | falling, 1200 → 200 Hz | 0.1-0.2 s | |
| Hit / impact | noise | — | 0.1-0.2 s | lowpass sweeping down |
| Explosion | noise | — | 0.4-1 s | lowpass 1200 → 80 Hz, lower voice cap |
| Hurt | sawtooth | falling | 0.2-0.3 s | lowpass to soften |
| Power-up | triangle | long rise | 0.3-0.6 s | vibrato 8-14 Hz |
| UI click | sine | tiny fall | 0.03-0.05 s | low volume |
| Error / denied | square | two low notes | 0.15 s | |

Pitch direction carries meaning: rising reads as positive or upward (jump, reward), falling as negative or downward (damage, failure).

## Layering
Big events combine layers: a click or snap (attack), a body (tone or noise), and a tail (low rumble or reverb). Start all layers together.

## Mixing
- Rough relative levels: UI and ambience quietest, music below effects, player actions and threats loudest.
- Ducking: lower music by about 30-50% for 0.3-1 s during big events, with a quick fade back.
- Stereo panning by screen position (`StereoPannerNode`) helps locate off-center events; keep it subtle (±0.5).
- Distance: lower volume and cut highs (lowpass) for faraway sources.

## Music
- Tempo by intensity: calm 70-100 BPM, action 120-160 BPM.
- Loops: make the end lead into the start; export or schedule with sample accuracy (`AudioBufferSourceNode.loop` with `loopStart`/`loopEnd`).
- Adaptive layers: start all stems together, fade layer volumes by game intensity, so they stay in sync.
- Stingers: short musical phrases for wins, deaths, and discoveries, played over ducked music.

## Web specifics
- Autoplay policy: create or resume the `AudioContext` inside a user gesture handler.
- Decode files once at load (`decodeAudioData`) and reuse buffers; create a new source node per play (sources are one-shot).
- Schedule with `ctx.currentTime`, not `setTimeout`, for tight timing.
- Pause music on `visibilitychange` when hidden.

## Provided audio files
- Normalize loudness across files before import so a single volume table works.
- Trim silence at the start; any delay reads as input lag.
- For web music, MP3 or AAC (M4A) plays in every major browser; OGG and WebM/Opus are smaller but check Safari support for your targets. WAV suits short effects where size allows.
- Only use assets the user owns or that have a compatible license; record licenses in `docs/credits.md`.
