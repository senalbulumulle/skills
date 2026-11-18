#!/usr/bin/env bash
# Install everything this repo provides for Codex, globally on this device:
#   skills   -> ~/.agents/skills/                                  (scripts/codex/install-codex-skills.sh)
#   hooks    -> $CODEX_HOME/hooks.json, engine-aware game hooks    (scripts/codex/install-codex-hooks.sh)
#   profile  -> $CODEX_HOME/game.config.toml and agents/ roles     (scripts/codex/install-codex-profile.sh)
#   mcp      -> the creative-director MCP server in config.toml    (scripts/codex/install-codex-mcp.sh)
#
#   scripts/codex/install-codex.sh                      all four
#   scripts/codex/install-codex.sh --only skills,hooks  just the ones listed
#
# Safe to re-run: it updates what it installed before and leaves everything else alone.
# Undo with scripts/codex/uninstall-codex.sh.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

select_components "${BASH_SOURCE[0]}" "$@"

# Check every requirement first, so a missing tool can't leave a half-finished install.
if selected skills || selected mcp; then need_uv; fi
if selected hooks || selected profile || selected mcp; then need_python39; fi
if selected mcp; then need_codex; fi

# One step failing (for example a skill folder that already exists and isn't ours) doesn't stop the others.
here="$(dirname "${BASH_SOURCE[0]}")"
status=0
for component in $ALL_COMPONENTS; do
  selected "$component" || continue
  info "== $component"
  bash "$here/install-codex-$component.sh" || status=1
done
if [ "$status" = 0 ]; then
  info "== Done."
else
  warn "finished with errors; see the messages above."
fi
exit "$status"
