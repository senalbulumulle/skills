Role: judge

Several studios built the same brief. You judge blind: the folders below are named at random, and nothing in them tells you who made what. Judge only what is in front of you.

## Brief

{{brief}}

## Entries

Each one is a folder in the current directory:

{{entries}}

## How to judge

1. For each entry, read its `RIVAL.md`, then run or build it the way it says. If you can't run it here, read the code closely and say so in your reason.
2. Use it the way a new person would for at least a minute: first impression, controls or flow, what happens on success and on failure.
3. Score each entry from 0 to 10 on each criterion ({{criteria}}):
   - works: it runs without errors and does what the brief asks
   - hook: a new person wants to keep going after the first minute
   - feel: input is instant and every action gives clear feedback
   - originality: it has an idea the other entries don't
   - polish: it looks and sounds finished, with no placeholders
4. The winner must have the highest total. Break ties on "works", then "hook".
5. From the entries that lost, name the ideas the winner should take: specific mechanics, moments, or details, never "make it better". Leave the list empty if no idea would improve the winner.
6. Don't change any files.

## Answer

End your final message with one JSON object and nothing after it. Use these entry ids exactly: {{ids}}

```json
{
  "winner": "entry-xxxx",
  "scores": {"entry-xxxx": {"works": 0, "hook": 0, "feel": 0, "originality": 0, "polish": 0}},
  "steal": [{"from": "entry-yyyy", "idea": "the specific idea and where it goes in the winner"}],
  "reason": "two sentences on why the winner won"
}
```
