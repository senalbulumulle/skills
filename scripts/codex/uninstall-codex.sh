#!/usr/bin/env bash
# Remove what scripts/codex/install-codex.sh installed for Codex:
#   skills   skill links in ~/.agents/skills/ that point into this repo (other skills are kept)
#   mcp      every MCP server in mcp/<category>/, if they point at this checkout
#
#   scripts/codex/uninstall-codex.sh               both
#   scripts/codex/uninstall-codex.sh --only mcp    just the ones listed
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

select_components "${BASH_SOURCE[0]}" "$@"

if selected skills; then need_uv; fi
if selected mcp; then need_python39; fi
if selected mcp; then need_codex; fi

here="$(dirname "${BASH_SOURCE[0]}")"
status=0
for component in $ALL_COMPONENTS; do
  selected "$component" || continue
  info "== $component"
  case "$component" in
    skills) "$REPO_ROOT/tools/skills.py" uninstall -p codex || status=1 ;;
    mcp) bash "$here/install-codex-mcp.sh" --uninstall || status=1 ;;
  esac
done
exit "$status"
