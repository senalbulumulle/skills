# Codex

- Installs to: `~/.agents/skills/` (user), `.agents/skills/` (project)
- Invoke: automatically from `description`, or `$skill-name` / `/skills`
- Extra frontmatter: none
- Extra file: `agents/openai.yaml` (UI name and icons, `policy.allow_implicit_invocation`, MCP tool dependencies). Other platforms ignore it, so it can live in the shared skill.
- Docs: https://developers.openai.com/codex/skills
- MCP servers: see `mcp/` (for example `mcp/web-dev/motion-forge/README.md` for Codex setup).
- Hooks: `hooks/discover.py` lists the hook events and outputs the installed Codex binary supports.
- Models: `models/` compares the models in Codex's catalog (Sol, Astra, Luna, Terra) without printing their instructions.
- Install everything: `scripts/codex/install-codex.sh` (`--help` lists the options).
