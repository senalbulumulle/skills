# PROMPT.md: session memory for hybrid-llms

Read this first in a new Claude Code session (e.g. `@PROMPT.md` or "read PROMPT.md and continue"). It records what was built, why, and what is still unverified.

## Goal

`hybrid-llms` is a hybrid local language model server written in C from scratch. It lets local models (Qwen and others in `~/Documents/Models` on macOS) and cloud model CLIs (Claude Code, Codex, Gemini CLI) work together, mainly to save cloud tokens. Inside each CLI, the user types `@hybrid ...` to send a request through it.

## User rules (keep following these)

- **Do not touch `README.md`.** The user writes the documentation. Don't add other docs unless asked.
- Development continues on the user's **MacBook**. The first version was written on a Linux/WSL machine and was **never built into a binary or run there**, at the user's request. It was only syntax-checked (`make check`: gcc `-fsyntax-only -Wall -Wextra -Wshadow -Werror`), which passed.
- Be careful and exact ("don't make any mistakes"). Verify assumptions instead of guessing.
- The folder lives in the `skills` repo at `src/hybrid-llms/`. The repo's `AGENTS.md` rules target `skills/`, `mcp/` and `harnesses/`; this project is self-contained under `src/`.

## Architecture

One dependency-free binary, `hybrid-llms` (C11 + POSIX threads, works with Apple clang and gcc). It has three front ends over one core:

| Front end | Command | Used by |
| --- | --- | --- |
| MCP stdio server | `hybrid-llms mcp` | Claude Code, Codex, Gemini (`@hybrid`) |
| HTTP daemon | `hybrid-llms serve` (127.0.0.1:8787) | anything OpenAI-compatible |
| CLI | `hybrid-llms ask/local/cloud/models/engine/status/config` | terminal use, scripts |

### Source map (`src/`)

- `util.*`: string buffer, logging (stderr only; stdout is the MCP channel), helpers, ANSI and `<think>` stripping.
- `json.*`: JSON parser and serializer (surrogate pairs; invalid UTF-8 becomes U+FFFD on output).
- `config.*`: `key = value` config file plus `HYBRID_LLMS_*` env overrides. The path is `$HYBRID_LLMS_CONFIG`, else `$XDG_CONFIG_HOME/hybrid-llms/config` (only if that file exists), else `~/.config/hybrid-llms/config`.
- `http.*`: plain-HTTP client (chunked and Content-Length, deadlines) and server request reader.
- `proc.*`: no-shell subprocess runner (stdin feed, stdout/stderr capture, timeout that kills the process group, closes inherited fds) and a detached spawner for engines. Command templates use shell-like quoting and `{placeholders}`.
- `engine.*`: **local model discovery and managed engine.**
  - Scans `models_dir` (default `~/Documents/Models`, recursive, depth 4) for `*.gguf` files. It skips `mmproj` files and secondary split shards (`-00002-of-…`).
  - Also finds MLX folders (a folder with `config.json` plus `*.safetensors`).
  - GGUF models run with `llama-server`; MLX folders run with `mlx_lm.server`. The engine serves on 127.0.0.1:`engine_port` (8790).
  - One engine per port is shared by all hybrid-llms processes, using `~/.cache/hybrid-llms/engine-<port>.{lock,state,log}` (flock).
  - Asking for a different model restarts the engine. By default it stays loaded for other sessions (`engine_keep_alive = 1`); stop it with `hybrid-llms engine stop`.
- `local.*`: chat with the local model. Backends are `managed` (default), `ollama` (`/api/chat`) and `openai` (`/v1/chat/completions`).
- `cloud.*`: runs the cloud CLIs headlessly, with the prompt on stdin:
  - `claude -p --output-format text --strict-mcp-config`
  - `codex exec --skip-git-repo-check --ephemeral --sandbox read-only --color never --output-last-message {out} -`
  - `gemini` (stdin piped, so it runs non-interactively)

  There is a recursion guard: the `HYBRID_LLMS_DEPTH` env var against `max_depth = 1`. `@hybrid` is also rewritten in prompts sent to the cloud.
- `hybrid.*`: the strategies.
  - `local`: local model only.
  - `cloud`: cloud model only.
  - `cascade`: local answers and ends with `CONFIDENCE: N`; below `cascade_threshold` (70) it escalates to the cloud along with the draft.
  - `draft-review`: local drafts, the cloud reviews.
  - `plan-execute`: the cloud writes a plan, local carries it out.
  - `compress`: local condenses long context in `chunk_chars` chunks, then the cloud answers from the condensed text.
  - `auto`: `compress` if the input is over `compress_threshold` (12000 chars), else `cascade`.

  Every strategy has fallbacks when one side fails. Results carry a trace, rough token estimates (chars/4), `needs_host_review` and a note.
- **cloud = `host`** (the MCP default, `mcp_cloud = host`): the CLI that called the tool *is* the cloud model. No extra CLI is spawned; low-confidence or draft output comes back flagged `needs_host_review`, and the host model finishes it. This is the main token saver. Naming `claude`, `codex` or `gemini` explicitly spawns that CLI instead.
- `mcp.*`: MCP server (protocol 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05; newline-delimited JSON-RPC; tool calls run on threads; batches are rejected).
  - Tools: `hybrid`, `local_generate`, `cloud_ask`, `local_models`, `hybrid_status`.
  - Prompt: `hybrid`. Its server instructions tell the host to call `hybrid` when the user writes `@hybrid`.
- `server.*`: HTTP API.
  - Endpoints: `GET /health`, `GET /v1/models`, `GET /v1/status`, `POST /v1/chat/completions` (`stream` is sent as one SSE chunk) and `POST /v1/hybrid`.
  - Model names: `hybrid`, `hybrid/<strategy>[/<cloud>]`, `local[/<model>]`, `cloud/<claude|codex|gemini>`.
  - Optional bearer `token`.
- `main.c`: the CLI (`hybrid-llms help`).

### How `@hybrid` is wired into each CLI (`scripts/install.sh`)

- **Claude Code:**
  - `claude mcp add --scope user hybrid -- ~/.local/bin/hybrid-llms mcp`
  - `~/.claude/agents/hybrid.md` (subagent, @-mention as `@agent-hybrid`)
  - `~/.claude/skills/hybrid/SKILL.md` (`/hybrid`)
  - an `@hybrid` instruction block in `~/.claude/CLAUDE.md`
- **Codex:**
  - `[mcp_servers.hybrid]` in `~/.codex/config.toml`, with `tool_timeout_sec = 1800` and `env_vars = ["HYBRID_LLMS_DEPTH","HYBRID_LLMS_CONFIG"]`
  - `~/.codex/skills/hybrid/SKILL.md` (`$hybrid`)
  - an instruction block in `~/.codex/AGENTS.md`
- **Gemini CLI:**
  - `mcpServers.hybrid` in `~/.gemini/settings.json` (timeout 1800000 ms)
  - `~/.gemini/commands/hybrid.toml` (`/hybrid`)
  - an instruction block in `~/.gemini/GEMINI.md`
- The instruction blocks sit between `<!-- hybrid-llms:begin -->` and `<!-- hybrid-llms:end -->` markers. Edits go through `scripts/hybrid_config.py`, which writes `.bak` backups. `scripts/uninstall.sh` reverses all of it and keeps the config.

Typed `@hybrid` is plain text to every CLI. It works because the host model reads the instruction block, the MCP server instructions and the tool description, then calls the `hybrid` tool. The native shortcuts are `/hybrid` (Claude skill, Gemini command), `$hybrid` (Codex skill) and `@agent-hybrid` (Claude subagent).

## Status

Done: all source, Makefile, tests, integrations, installer and uninstaller, `config.example`. Never built or run.

### Next steps on the MacBook

1. `xcode-select --install` if needed. Then `cd src/hybrid-llms && make check && make && make test`, and fix anything Apple clang reports.
2. Install an engine: `brew install llama.cpp` (GGUF) and/or `pip install mlx-lm` (MLX).
3. `./build/hybrid-llms models`: confirm it lists the files in `~/Documents/Models`.
4. `./build/hybrid-llms engine start`, then `./build/hybrid-llms local "hello"`.
5. `./build/hybrid-llms ask -s cascade "what is a mutex?"` and `ask -c claude -s draft-review "..."`.
6. `scripts/install.sh`, restart the CLIs, then try `@hybrid ...` in Claude Code, Codex and Gemini.
7. `hybrid-llms serve` and `curl localhost:8787/v1/models`.

### Assumptions to verify on the Mac (not confirmed yet)

- Codex: `env_vars` (array of strings) is accepted in `[mcp_servers.*]` in the installed version. The key exists in the codex 0.171 binary, but its type is unchecked. Also confirm that `codex exec … -` reads the prompt from stdin and that `--output-last-message` works.
- Gemini CLI is not installed yet. Confirm that piped stdin with no `-p` runs non-interactively, and that settings `mcpServers.<name>.timeout` is in milliseconds.
- `llama-server` supports `--jinja` in the brew version, and `/health` returns 200 once ready (503 while loading).
- `mlx_lm.server` answers `GET /v1/models` when ready and accepts the model path in the `model` field.
- Claude Code's subagent @-mention syntax (`@agent-hybrid`), and that the MCP tool timeout is long enough for model loading.

## Ideas not done yet

True token streaming. Prompt caching of the system prompt. A per-request choice of engine port so two models can stay loaded. Per-task routing rules (for example, code to a coder model). Real token counts from backend `usage` fields.
