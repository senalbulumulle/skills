# creative-pipeline

Three models, each on the step it's good at, with code (not prompts) deciding what counts as done:

```
brief.md ─► diverge (Gemini API) ─► draft (Claude Code) ─► anti-slop gate ─► audit (Codex) ─► anti-slop gate ─► pipeline/<run>
              3-5 directions         builds one             fail? cheap fix,   hostile edit      fail? cheap fix
              JSON, schema-checked   in a worktree          up to 3 retries    and fixes         up to 3 retries
```

| Step | Model | Why this model | How it runs |
| --- | --- | --- | --- |
| `diverge` | Gemini | Long context and divergent ideas | HTTP API. Reads the project through 3 sandboxed tools, then returns directions as JSON |
| `draft` | Claude Code | Opinionated building and synthesis | `claude -p` in the run's worktree, with only the declared built-in tools and no MCP servers |
| `audit` | Codex | Literal checking and hostile editing | `codex exec` in the same worktree with its `workspace-write` sandbox, answering in a JSON schema |

The harness never merges or pushes. Each run builds on a `pipeline/<run>` branch in its own git worktree and prints the commands to review and merge it.

## Use it

Needs Git and Python 3.9+, plus whichever of these the steps you run use:
- **Gemini:** `GEMINI_API_KEY` and `GEMINI_MODEL`.
- **Claude Code:** the `claude` CLI, signed in.
- **Codex:** the `codex` CLI, signed in.

Run it from the repository to build in:

```sh
harnesses/creative-pipeline/pipeline.py dry-run brief.md      # what each step's prompt costs; no model calls
harnesses/creative-pipeline/pipeline.py run brief.md          # every step
harnesses/creative-pipeline/pipeline.py run brief.md --skip diverge   # without Gemini
harnesses/creative-pipeline/pipeline.py run brief.md --mock harnesses/creative-pipeline/replays/demo.json
harnesses/creative-pipeline/pipeline.py bench brief.md        # one plain Claude Code session vs. the pipeline
```

`--mock` runs every step from a replay file instead of models. The demo replay's first attempts contain stock phrasing, placeholder copy, a default gradient, a `git push`, and a write outside the worktree, and the output shows the gate and guard catching each one. Its usage numbers are made up, to show the shape of the reports; only a real `bench` run measures anything.

| Command | What it does |
| --- | --- |
| `run BRIEF` | Run every step. `--skip STEP`, `--max-retries N`, `--retry fix\|resume`, `--approve REGEX`, `--claude-model`, `--codex-model`, `--gemini-model`, `--timeout`, `--bypass-hook-trust`, `--mock REPLAY` |
| `bench BRIEF` | Run the brief as one plain Claude Code session and through the pipeline, then compare real token usage and the gate's verdict on each build. Takes the `run` options plus `--baseline-model` |
| `dry-run BRIEF` | Compile each step's prompt and print the token report. `--json`, and `--exact` to count Gemini's prompt tokens with its `countTokens` endpoint |
| `index` | Print the skill index tier and its token cost |
| `gate FILE...` | Run the anti-slop gate on any files (exit 1 on failure). `--brief TEXT`, `--message-file` |
| `status RUN` / `clean RUN` | Summarize a run / remove its worktree (the branch stays) |
| `codex-trust` | Print how to trust the guard hook in Codex once |

## How it works

### Lean context (`context.py`)

- **Two-tier skills.** The index tier is each skill's name and the leading clause of its description, about 22 tokens per skill. The execution tier is a skill's full `SKILL.md` body plus a few taste anchors, and it loads only for the skills that match the brief (`max_skills` per step). Matching is deterministic keyword scoring: name words count 3, "Use when" words 2, other description words 1.
- **Taste anchors.** A skill can name an anchors file with `metadata.anchors` (default `references/examples.md`). Each `## ` section is one generic-vs-specific pair.
- **Budgets.** Each step in `steps.json` has a token budget. The persona and brief are mandatory; lessons, skills, and anchors are added by priority while they fit. A step whose mandatory part doesn't fit stops the run.
- **Tool filtering.** An API step sends only the tool schemas it declares (`tools`). A Claude Code step gets only its declared built-in tools (`--tools`), and only its declared MCP servers (`--strict-mcp-config`). An empty `mcp` loads none, which also drops the schemas of every MCP server you have configured.
- **Telemetry.** `dry-run` and every run report each step's prompt tokens, tool-schema tokens, and savings against a baseline that loads every skill, anchor, persona, and tool schema at once. These counts are estimates at about 4 characters per token. `--exact` asks Gemini's `countTokens` endpoint for the real count. The CLIs add their own system prompts, which the harness can't see, so `run` also reports the usage each CLI returns.

### Hooks (`hooks.py`)

| Event | Default handler |
| --- | --- |
| `onPrePrompt` | Builds the step's prompt within budget: persona, lessons from earlier runs, matched skills, anchors. Removes duplicate sections |
| `onPostDraft` | Runs the anti-slop gate on the files the step changed and on its final message. Checks the JSON structure when the step has a `schema` |
| `onPreToolCall` | Runs the guard (below) |
| `onSessionEnd` | Folds the run into `<repo>/.creative-pipeline/state.json`: the last 20 runs, the last 10 decisions, and how many runs tripped each rule |

A rule that trips in 2 or more runs becomes a lesson, and `onPrePrompt` adds it to later prompts. You can add your own lines to `notes` in `state.json`, and they go into every prompt. Add more handlers with `hooks.on(event, fn)`.

### Anti-slop gate (`gate.py`, `rules/slop.json`)

- **Rules:** regexes for stock vocabulary (delve, tapestry, testament, crucial, landscape, and similar), sycophantic openers, "not just X, it's Y" templates, placeholder names and copy (Acme, Lorem ipsum, "My Website" titles), stub code (TODO, "implement me"), and the stock purple-blue gradient in CSS or Tailwind classes.
- **Scopes:** each rule applies to prose, visible markup text, CSS, or code strings and comments. A brief can switch a rule off with `unless_brief`, so asking for a purple gradient allows one.
- **Cadence:** flags paragraphs of 6 or more sentences with nearly equal lengths, and runs of 5 sentences within 2 words of each other. Em-dash density is only a warning.
- **Retries stop** at `max_retries` (3). A draft that never passes hands its remaining violations to the audit step as its must-fix list.

### Cheap retries

When the gate fails, the default retry (`"retry": "fix"` in `steps.json`) doesn't resume the step's session, which would send its whole history again. Instead it makes a small, fresh call (`prompts/fix.md`) that sees only:
- the gate's report, `{"passed": false, "violations": [{rule, file, line, match, hint}]}`
- the flagged lines with 4 lines around each, numbered, up to 8,000 characters
- the final message, and the answer's JSON shape if the step has one

The call can't change anything itself. Claude Code gets no tools (`--tools ""`) and no MCP servers. Codex runs in a read-only sandbox with `--ephemeral` and low reasoning effort (`fix_effort` on the step changes it). Gemini gets no tools and none of its earlier conversation. The call answers with `{"edits": [{file, old, new}], "message": "..."}`. The harness applies an edit only when its file is inside the worktree and its `old` text appears exactly once, then gates again. Set `fix_model` on a step to send fix calls to a cheaper model.

If a fix round changes nothing, the next attempt falls back to resuming the session with `prompts/revise.md`. Use `"retry": "resume"` on a step, or `--retry resume`, to always resume.

### Benchmark (`bench`)

`bench` answers whether the pipeline is worth its cost. It builds the same brief twice from the same commit, each in its own worktree:
- **Baseline:** one `claude -p` session with your own settings, MCP servers, and tools, given the brief and "Build this in the current folder." It also gets the guard hook, and its branch is `bench/<id>/baseline`.
- **Pipeline:** a normal `run`, on its `pipeline/<run>` branch.

It prints fresh input, cached input, output, and total tokens for each side, per step, and per attempt type (`initial`, `fix`, `resume`). It also prints the gate's verdict on each build's changed files, and writes everything to `<repo>/.creative-pipeline/bench/<id>/bench.json`.

Read the numbers with care:
- Token usage is what each provider reports, converted to one shape: Claude's cache writes count as fresh input, and Codex's and Gemini's cached tokens are taken out of their input counts.
- Cost appears only where Claude Code reports it, so the pipeline's cost leaves out its Gemini and Codex steps and is marked `*`.
- One run of each is a sample, not an average. Repeat it before drawing conclusions, and look at both branches: the gate catches stock output, not whether a build is good.

### Guard (`guard.py`)

One script serves as the `PreToolUse` hook for both CLIs, passed to Claude Code with `--settings` and to Codex with `-c hooks.PreToolUse=...`. The harness also calls it in-process for Gemini's tools. It finds the run's `.creative-pipeline-guard.json` from the session's working folder, so it does nothing in sessions that aren't pipeline runs.

It denies:
- file writes outside the worktree, and reads outside the worktree, the repo, and this repo's skills
- `git push`, `reset --hard`, `clean`, `branch -D`, and other history rewrites
- `rm`, `mv`, or `cp` outside the worktree, and deleting the worktree itself
- redirects into outside paths, `sudo`, `curl ... | sh`, and package or store publishing

To allow a specific command anyway, pass `--approve REGEX`. Unlike most hooks, the guard fails closed: if it crashes, the call is denied. Every decision is logged in the run's `guard.log`.

Claude Code runs `--settings` hooks right away. **Codex runs only hooks you have trusted,** and a hook passed with `-c` counts as new. Run `pipeline.py codex-trust` once for the exact command to trust it. Alternatively, pass `--bypass-hook-trust`, which skips the trust check for all of your enabled Codex hooks. After a Codex step, the harness checks `guard.log` and warns if Codex didn't run the guard.

## Files

Everything a run produces stays in `<repo>/.creative-pipeline/runs/<run>/`, which is kept out of `git status` through `.git/info/exclude`:
- `report.json`: steps, every attempt's mode and usage, violations, guard denials, and telemetry
- `brief.md`
- `guard.log`
- `logs/`: every attempt's prompt (`<step>.<n>.prompt.md`, or `<step>.<n>.fix.md` for a fix call) and each CLI's output

A benchmark adds `<repo>/.creative-pipeline/bench/<id>/` with `bench.json`, the baseline's worktree, and its log.

## Change it

- **Steps:** `steps.json` sets each step's provider, persona, budget, skills mode, tools, MCP servers, gate, schema, retry mode, and fix model.
- **Rules:** `rules/slop.json`. Test a change with `pipeline.py gate some-file.md`.
- **Prompts:** `prompts/`. Placeholders look like `{{brief}}`, and a prompt with a placeholder the harness can't fill is refused.
- **Tests:** `python3 -m unittest tools/test_creative_pipeline.py`. They run every step and the benchmark with the replay mock, and again with fake `claude` and `codex` executables that call the guard as a real hook.
