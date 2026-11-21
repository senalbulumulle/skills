# Story doc format

Three kinds of Markdown files in one folder (`docs/story/` by convention). `story.py review` reports every line it can't read, with its file and line number. HTML comments (`<!-- -->`) are ignored everywhere.

```
docs/story/
  characters.md
  story.md
  dialogue/
    harbor_shop.md      the file name is the conversation id
```

Ids (characters, conversations, nodes, flags) use lowercase letters, digits, and underscores, and start with a letter.

## characters.md

One `## ` heading per character (the display name), then `- key: value` lines. Other keys, such as `fear` or `age`, are allowed and ignored by the tools.

```
## Mara Quell
- id: mara
- role: Keeper of the Lantern Pier lighthouse
- wants: the lamp lit before the storm reaches the boats
- voice: Dry and clipped. Short sentences, sailing words.
- vo: Alto, late fifties, gravelly and unhurried.
```

| Key | Required | Used for |
|---|---|---|
| `id` | yes | the speaker name in dialogue files; not `narrator` or `player`, which are built in |
| `role`, `wants`, `voice` | yes | keeping the character consistent across writers |
| `vo` | when they speak | the voice direction printed in the voiceover script |

## story.md

```
# Lantern Pier

## Premise
Who the player is, what they want, and what is in the way.

## Acts
### Act 1: The dark tower
- goal: Talk to Mara and learn the lamp needs oil.

## Flags
- oil_found: set by game code when the player picks up the oil can
```

List every flag that game code sets under `## Flags`. Review treats a flag as possible only if dialogue sets it or it is listed here.

## dialogue/<conversation_id>.md

A `# ` title, `- npc:` (the character who owns the conversation) and `- start:` (the first node), then one `## ` section per node.

```
## greet
mara (dry): Storm's two hours out. You here to help or to drip on my floor?
- [I'll help. What do you need?](#need_oil) | needs !oil_delivered
- [Here's your oil.](#lit) | needs oil_found, !oil_delivered | sets oil_delivered
- [Just looking around.](#end)

## need_oil
mara: My lamp's dark and it drinks oil.
-> end | sets asked_about_oil
```

| Line | Meaning |
|---|---|
| `speaker (delivery): text` | A spoken line. `speaker` is a character id, `narrator`, or `player`; `(delivery)` is optional and goes into the voiceover script. |
| `- [text](#node)` | A player choice that goes to `node`, or to `end` to finish the conversation. |
| `-> node` | Continue without a choice. A node has either choices or one `->` line. |
| `\| needs a, !b` | Show the choice only while flag `a` is set and `b` is not. Works on choices and `->` lines. |
| `\| sets a` / `\| clears a` | Set or clear flags when the choice is taken. |
| `> text` | A note for the team; ignored by the tools. |

Spoken lines come first in a node, then its choices or `->` line.

## Generated files

| File | Built by | Contents |
|---|---|---|
| `Dialogue.luau` | `story.py build` | Typed data for DialogueRunner. Line 3 records the docs folder and their hash, so the Codex hooks can tell when it is out of date. |
| `voiceover.md` | `story.py voiceover` | Lines grouped by character with IDs, delivery, word counts, and seconds at 150 words per minute. |
| `*.csv` | `story.py localization` | `Key,Context,Example,Source` and one column per locale, the layout of Roblox's own localization CSVs. |

IDs: spoken lines are `conversation.node.n` (counting from 1 in each node), choices are `conversation.node.choiceN`, and character names are `characters.id.name`. Name voice recordings after line IDs, and look text up with `Translator:FormatByKey(id)` in a localized game.
