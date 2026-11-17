# Codex

- Installs to: `~/.agents/skills/` (user), `.agents/skills/` (project)
- Invoke: automatically from `description`, or `$skill-name` / `/skills`
- Extra frontmatter: none
- Extra file: `agents/openai.yaml` (UI name and icons, `policy.allow_implicit_invocation`, MCP tool dependencies). Other platforms ignore it, so it can live in the shared skill.
- Note: Gemini CLI, Copilot, Cursor, and OpenCode also read `~/.agents/skills/`.
- Docs: https://developers.openai.com/codex/skills
- MCP servers: see `mcp/` (for example `mcp/roblox-forge/README.md` for Codex setup).
- Hooks: `hooks/` has engine-aware game-dev hooks (`install.py`) and `discover.py`, which lists the hook events and outputs the installed Codex binary supports.
