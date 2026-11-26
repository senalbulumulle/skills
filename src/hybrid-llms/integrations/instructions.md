## @hybrid (hybrid-llms)

When a message contains `@hybrid`, send that request through the `hybrid` MCP server instead of answering it alone:

1. Call the `hybrid` tool with the request (without `@hybrid`) as `prompt`. Put long file contents, diffs, or logs in `context`, not in `prompt`.
2. Choose `strategy`: `auto` by default; `local` when the user says local only; `compress` for large inputs; `draft-review` when accuracy matters; `plan-execute` for multi-step work; `cloud` to skip the local model.
3. Leave `cloud` as `host` (you are the cloud model) unless the user names `claude`, `codex`, or `gemini`; then pass that name.
4. If the result reports needs_host_review, check and fix the answer before replying. Reply with the answer, then the one-line `[hybrid]` summary.

Use `local_generate` for cheap subtasks (summaries, boilerplate, rewrites), `cloud_ask` for a second opinion from another cloud model, and `hybrid_status` when something fails.
