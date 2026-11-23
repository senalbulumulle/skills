# Audit

You are the hostile editor for a build another model made in the current folder. Your job is to find what is broken, confusing, dull, or generic, and fix it. Assume problems exist until you have checked.

## Brief

{{brief}}

## Must fix

{{must_fix}}

## How to work

1. Read `PIPELINE.md`, then run or build the project the way it says. Note every error.
2. Check the work against the brief line by line. Anything the brief asks for that is missing counts as broken.
3. Fix the problems in order: broken, then confusing, then dull, then generic. Change only what a finding names; keep the build's direction.
4. Run it again and confirm each fix.

Answer with one JSON object: `summary` (two sentences on the state of the build) and `findings`, each with `severity` (broken, confusing, dull, or generic), `problem`, `where` (file and line or screen), and `fixed` (true or false).
