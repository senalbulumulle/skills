The anti-slop gate rejected part of a draft (attempt {{attempt}} of {{max_attempts}}). Fix only what it flagged; everything else passed.

## Brief

{{brief}}

## Violations

```json
{{violations}}
```

## The flagged lines, with a few lines around each

{{excerpts}}

## The final message

{{message}}

## Required shape of the answer, if any

{{schema}}

## How to answer

Reply with one JSON object and nothing else: `{"edits": [{"file": "...", "old": "...", "new": "..."}], "message": "..."}`

- Each edit replaces `old` with `new` in `file`. Copy `old` exactly from the lines above, without the line numbers, and make it long enough to appear only once in the file.
- Rewrite the flagged passage so the idea is said plainly. Swapping one stock word for a synonym will fail again.
- `message`: the corrected final message if a violation is in it (when an answer shape is given above, the whole corrected answer in that shape). Otherwise an empty string.
