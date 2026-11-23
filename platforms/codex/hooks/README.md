# Codex hook discovery

What the installed Codex accepts from [hooks](https://developers.openai.com/codex/hooks), read from the binary. Check here before writing a Codex hook, because the schema accepts outputs that the runtime then rejects.

## Use

`discover.py` reads the hook surface compiled into the installed Codex without running it. It parses the embedded JSON schemas and the runtime's rejection messages.

```sh
platforms/codex/hooks/discover.py                                         # summary for the codex on PATH
platforms/codex/hooks/discover.py --diff platforms/codex/hooks/snapshots/codex-0.163.0.json  # what changed after an upgrade
```

Codex 0.163.0 findings, from the binary and a live run, that the docs don't make obvious:
- **Events:** the binary has 12 events, including `Interrupt` and `SubagentStart`. `PreModelRequest`/`PostModelRequest`, which the online docs list, are not in 0.163.0.
- **Accepted by the schema but rejected at runtime:**
  - `PreToolUse`: `permissionDecision: "ask"`, legacy `decision: "approve"`, `continue: false`, `stopReason`, and `suppressOutput`. `permissionDecision: "allow"` is rejected unless it comes with `updatedInput`.
  - `PostToolUse`: `updatedMCPToolOutput`.
  - `PermissionRequest`: `updatedInput`, `updatedPermissions`, and `interrupt: true`.
- **Handler types:** `prompt` and `agent` are parsed but skipped. `command` and `mcp_tool` run.
- **Tool calls:** shell calls arrive as `tool_name: "Bash"` with `tool_input.command` as a string. File edits arrive as `tool_name: "apply_patch"` with the raw patch text in `tool_input.command`.
- **Process environment:** Codex runs hook commands through the shell in the session's `cwd`, with no `CODEX_*` environment variables. A hook script that needs its own files must find them from `cwd` or an absolute path in its command.
- **Denial text:** Codex shows a `PreToolUse` denial as `Command blocked by PreToolUse hook: <reason>. Command: <command>`.

## Development

- Tests: `python3 -m unittest tools/test_codex_discover.py`. The snapshot test runs only when the snapshot's Codex version is installed.
- When Codex updates, run `discover.py --diff` against the latest snapshot. If anything changed, save a new snapshot (`discover.py --json > snapshots/codex-<version>.json`).
