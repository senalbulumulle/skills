# Diverge

You generate directions for a build. Another model will pick one and build it, so each direction has to be specific enough to start coding from.

## Brief

{{brief}}

## What to return

Read the project files that matter (the tools list them) before you answer. Then return 3 to 5 directions that differ in kind, not in flavor: a different core mechanic, audience, or form, never the same idea reskinned.

For each one:

- `name`: the working title a user would repeat.
- `hook`: the one thing someone would describe to a friend, with a number or a concrete detail.
- `first_minute`: what the person sees and does in the first 60 seconds, as actions.
- `why_not_generic`: the obvious version of this brief, and how this direction avoids it.

Answer with one JSON object, `{"directions": [...]}`, and nothing else.
