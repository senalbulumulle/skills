# rival-studios

Several studios build the same brief at once, each with a different creative stance. A judge who doesn't know which studio is which runs every build and scores it. The winner then takes the best ideas from the losing builds. It works for games, apps, and web UI: anything an agent can build and run in a git repository.

```
brief.md ──► start ──► studio A (feel-first)    ─┐
                       studio B (strange-idea)  ─┼─► blind judge ──► winner + ideas to take ──► merge ──► rival/<run>/<winner>
                       studio C (one-thing)     ─┘
```

## Use it

Needs Git, Python 3.9+, and [Claude Code](https://claude.com/claude-code) or the [Codex CLI](https://developers.openai.com/codex/cli). Run it from the repository the studios should build in:

```sh
harnesses/rival-studios/rival.py run brief.md --studios 3                         # Claude Code
harnesses/rival-studios/rival.py run brief.md --agent codex --model gpt-6-astra   # Codex
```

`run` does four steps. Run them one at a time to check each result first:

```sh
rival.py start brief.md --studios 3   # one worktree and branch per studio, from HEAD; prints the run id
rival.py build <run>                  # every studio builds the brief, in parallel
rival.py judge <run>                  # the blind judge writes verdict.json
rival.py merge <run>                  # the winner takes the ideas the judge named
rival.py status <run>                 # what each step produced
rival.py clean <run>                  # remove the worktrees; the branches stay
```

The harness never merges into your branch. When it finishes, it prints the `git diff` and `git merge` commands for the winning branch.

## Options

| Option | Default | What it does |
| --- | --- | --- |
| `--studios N` | 2 | 2 to 5 studios, each with a different stance from `studios.json` |
| `--agent` | `claude` | `claude` or `codex` |
| `--model` | the agent's own setting | Passed to `claude --model` or `codex exec -m` |
| `--trust` | `edits` | `edits`: Claude may only edit files (`acceptEdits`), and Codex runs in its `workspace-write` sandbox. `full`: no prompts and no sandbox (`bypassPermissions`, `--dangerously-bypass-approvals-and-sandbox`). Use `full` only on a machine or container you're willing to lose |
| `--agent-cmd` | | Any other agent, as a JSON list in which `{prompt}`, `{cwd}`, and `{last}` (a file for its final message) are replaced |
| `--timeout` | 3600 | Seconds per step. An agent that runs over is stopped |
| `--seed` | random | Fixes the stance assignment and the order the judge sees the entries in |

With `--trust edits`, Claude Code can't run commands in headless mode, so its studios can't test their builds and its judge has to read the code instead of running it. Codex can run commands inside its sandbox. Running builds gives much better results, so use Codex, or `--trust full` in a sandboxed environment.

## How it works

- **Start:** creates `<repo>/.rival/<run>/` (kept out of `git status` through `.git/info/exclude`) and a worktree on a `rival/<run>/entry-xxxx` branch for each studio. Entry names are random, so neither a path nor a branch name tells the judge which stance made which build.
- **Build:** runs `prompts/studio.md` with the brief and the studio's stance in every worktree at once, then commits whatever each studio left. A studio that fails, times out, or changes nothing is left out of judging.
- **Judge:** runs `prompts/judge.md` in the folder that holds the entries. The judge scores each entry from 0 to 10 on works, hook, feel, originality, and polish, and must end with a JSON verdict. The harness checks it: every entry is scored, the winner has the top total, and every idea to take comes from a losing entry. An unusable verdict gets one retry that lists the problems. If only one studio built something, it wins without judging.
- **Merge:** runs `prompts/merge.md` in the winner's worktree, with the losing builds readable, and commits the result.

Everything a run produces stays in its folder: `run.json`, `brief.md`, `verdict.json`, and `logs/` with each agent's full output.

## Change it

- **Stances:** edit `studios.json`. Each stance needs a `name` and a `direction`, which is the one paragraph that makes that studio different.
- **Prompts:** edit the files in `prompts/`. Placeholders look like `{{brief}}`, and the harness refuses to run a prompt with a placeholder it can't fill.
- **Tests:** `tools/test_rival_studios.py` runs every step with a fake agent: `uv run --with pyyaml python -m unittest tools/test_rival_studios.py`.
