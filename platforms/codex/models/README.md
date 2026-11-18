# Codex models: Sol, Astra, Luna, Terra

`export_models.py` summarizes the model catalog Codex uses and compares models. It prints settings and the structure of each model's instructions (headings, sizes, hashes), never the instruction text, so its output is safe to commit.

```sh
platforms/codex/models/export_models.py                             # every model the installed Codex lists
platforms/codex/models/export_models.py --compare gpt-6-luna gpt-6-astra
platforms/codex/models/export_models.py --catalog ~/.codex/models_cache.json --json
```

`snapshots/` holds the summaries for Codex 0.163.0 (the CLI) and 0.169.0-alpha.11.1 (the CLI bundled with the ChatGPT desktop app).

## How Codex gets a model's behavior

Codex downloads a catalog for its own version: one entry per model, with settings and a full instruction set (`model_messages.instructions_template`). `codex debug models` prints it, and `~/.codex/models_cache.json` caches it. Both Codex clients on a Mac share that cache, so it holds whichever catalog was fetched last.

A model's behavior in Codex comes from its weights plus that instruction set. Neither is a hidden setting you can switch on. What a user can change:

| Setting | Effect | Used here |
| --- | --- | --- |
| `developer_instructions` (config or a `-p` profile file) | Adds a developer message before the conversation | yes: the `game` profile |
| `[agents.<name>]`, or a role file in `$CODEX_HOME/agents/` | Adds a sub-agent role with its own instructions | yes: game-designer, game-critic |
| hooks (`hooks.json`) | Add context or block actions at lifecycle events | yes: `platforms/codex/hooks/` |
| MCP servers | Add tools | yes: `mcp/creative-director/` |
| `model_instructions_file` | Replaces the model's instruction set entirely | no: it would drop OpenAI's tuning for that model |
| `model_catalog_json` | Replaces the whole catalog | no: the catalog would stop updating |

## Findings

Codex 0.163.0 lists 8 models and hides 2 (`gpt-reserve`, `codex-auto-review`). 0.169.0-alpha.11.1 adds `gpt-6.2-sol` and `gpt-6.2-astra`. A 0.163.0 client signed in with ChatGPT gets an error for `gpt-6.2-astra`: "The 'gpt-6.2-astra' model is not supported when using Codex with a ChatGPT account".

| Family | Catalog description | Distinct settings | Instructions |
| --- | --- | --- | --- |
| Luna (`gpt-6-luna`) | Fast and affordable, for easier tasks | Highest effort is `max` (no `ultra`) | Same sections as `gpt-6-sol`, with shorter permission and work rules |
| Sol (`gpt-6-sol`, `gpt-6.1-sol`, `gpt-6.2-sol`) | Coding and everyday work | 6.1 and 6.2: 500k context, low default effort. 6.2 also takes audio input and has the extra-fast speed tier | 6.1 matches 6-Astra except for writing style. 6.2 adds sections on completing the task, frontend design, and coding style |
| Astra (`gpt-6-astra`, `gpt-6.2-astra`) | Complex coding and professional work | 272k context | 6-Astra adds technical-communication and PR-description sections to the Sol and Luna set. 6.2-Astra follows the 6.2 layout |
| Terra (`gpt-6.1-terra`) | Visual understanding and computer use | 500k context, low default effort | Identical to `gpt-6-astra` |

Sub-agents run at `xhigh` effort on `gpt-6-astra` and on every 6.1 and 6.2 model; `gpt-6-sol` and `gpt-6-luna` leave them at the default. The three 5.6 models, `gpt-reserve`, and `codex-auto-review` share one older instruction set.

None of the instruction sets says anything about game design, game feel, or engines. Only `gpt-6.2-sol` mentions games, in a rule against recreating existing ones. That gap is what this repo fills: the skills, the `game` profile, the agent roles, the hooks, and the creative-director MCP server.

## Development

- Standard library only, Python 3.9+. Tests: `python3 -m unittest tools/test_codex_models.py`.
- After a Codex update, save a snapshot: `export_models.py --json > snapshots/codex-<version>.json`.
