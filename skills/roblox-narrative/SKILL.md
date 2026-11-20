---
name: roblox-narrative
description: Write a Roblox game's characters, story, NPC dialogue, and voiceover scripts as Markdown docs, check them, and build them into a dialogue module, a voice recording script, and a localization CSV that the game plays with a server-side DialogueRunner. Use when creating characters, NPCs, quests, branching dialogue, cutscene lines, story outlines, or voiceover scripts for a Roblox game, or when dialogue in a Roblox game is flat, inconsistent, or hard to change.
---

# Roblox Narrative

Write the story once as Markdown, check it, and build every game file from it, so dialogue, voiceover, and translations never drift apart.

## Steps

1. **Start the docs** in the game project at `docs/story/`, using [example/docs](assets/example/docs) as the pattern: `characters.md`, `story.md`, and one `dialogue/<conversation_id>.md` per conversation. The format is in [format.md](references/format.md).
2. **Write the characters first.** Each one gets an `id`, a `role`, what they `want`, how they talk (`voice`), and a `vo` direction for the voice actor. Make each voice recognisable without the name tag, following [writing.md](references/writing.md).
3. **Outline the story** in `story.md`: the premise, a `### ` heading per act with its `- goal:`, and under `## Flags` every flag game code sets (items picked up, levers pulled), so dialogue can check them.
4. **Write each conversation** as nodes: spoken lines (`mara (dry): ...`), then choices (`- [text](#node) | needs flag | sets flag`) or one `-> node` line. Keep lines under 100 characters and at most 4 choices on screen.
5. **Check the docs** with `scripts/story.py review docs/story` (or roblox-forge's `review_story`) and fix every high and medium finding.
6. **Build the game files** (each refuses while high findings remain):
   - `scripts/story.py build docs/story src/shared/Dialogue.luau` (or `build_dialogue`, which also copies [DialogueRunner.luau](assets/DialogueRunner.luau) next to it). Never edit the output: change the docs and build again.
   - `scripts/story.py voiceover docs/story docs/story/voiceover.md` (or `export_voiceover`): the recording script, grouped by character, with line IDs, delivery notes, and lengths.
   - `scripts/story.py localization docs/story localization.csv --locales es,pt-br` (or `export_localization`): import it into a LocalizationTable.
7. **Play it on the server** with `DialogueRunner.new(Dialogue, conversationId, flags)`: show `runner.current()` to the client, and call `runner.choose(i)` when it sends a choice index (validated with `RemoteGuard.integer`). Store flags with the player's saved data. The usage comment at the top of DialogueRunner.luau shows the wiring.

## Rules

- The docs are the source of truth; every generated file is rebuilt, never hand-edited.
- The server owns story progress: clients send a choice index, never a flag or a node.
- Every node ends with choices or `-> end`, and at least one choice per node needs no flag.
- Line IDs (`conversation.node.n`) are keys for recordings and translations: renaming a node or reordering its lines changes them, so re-export after such edits.

## Done when

- [ ] `story.py review` (or `review_story`) reports no high or medium findings.
- [ ] `Dialogue.luau`, `voiceover.md`, and the localization CSV were rebuilt after the last docs change.
- [ ] Each conversation was played through in Studio, including every choice the player can see.
