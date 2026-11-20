# Writing characters and dialogue for Roblox

Roblox players are often young and on phones, read in short bursts, and skip anything that feels like homework. Write so a line lands in one glance.

## Characters

- **One want, one fear, one habit of speech.** "Wants the lamp lit; fears the town has given up on it; never says please." That is enough to write any line for them.
- **Recognisable without the name tag.** Cover the speaker names and read a conversation: if you can't tell who is talking, sharpen the `voice` notes (sentence length, favourite words, what they never say).
- **Specific names and details.** "Mara Quell, keeper of Lantern Pier" beats "the Old Keeper". Give each character one concrete object or place they care about.
- **Write the `vo` line for a stranger.** Age, register, pace, and one emotional note ("deadpan; the warmth is in the pauses"). A voice actor reads only this and the lines.

## Lines

- **Under 100 characters, one idea each.** Split longer thoughts into two lines; the player taps through.
- **Subtext over exposition.** "Last can went missing off the pier this morning" tells the player where to look without a quest log.
- **Every line earns its tap:** it moves the goal forward, shows character, or pays off a choice. Cut the rest.
- **Delivery notes in brackets** (`(quieter)`, `(laughing)`) only where the reading isn't obvious; they go straight to the voice actor.

## Choices

- **2 to 4 options, each under 40 characters**, written in the player's voice.
- **Make choices differ in intent**, not wording: help, refuse, joke, or ask. Avoid three ways of saying yes.
- **Always leave a way out.** At least one choice per node needs no flag, so a player is never stuck.
- **Pay choices off.** If a choice sets a flag, let another conversation or the world react to it, or cut the flag.

## Structure

- **Conversations are short:** two or three nodes per visit, then back to playing. Return visits change with flags ("The light's on. Can I go up?").
- **Flags record facts, not feelings:** `oil_found`, `asked_about_oil`, `lamp_lit`. Game code sets world facts; dialogue sets conversation facts.
- **Each act has one goal** the player can say out loud, and every conversation points toward the current one.

## Voiceover

- Review the voiceover script aloud before booking anyone: lines that are awkward to say are awkward to read.
- The script's lengths assume 150 words per minute; a fast talker like a child character runs shorter, a slow one longer.
- Record one file per line ID so a rewritten line needs only one new take.
