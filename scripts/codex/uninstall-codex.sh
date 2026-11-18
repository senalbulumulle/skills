#!/usr/bin/env bash
# Remove what scripts/codex/install-codex.sh installed for Codex:
#   - skill links in ~/.agents/skills/ that point into this repo (other skills are kept)
#   - game_hooks.py handlers in $CODEX_HOME/hooks.json (other hooks are kept)
#
#   scripts/codex/uninstall-codex.sh                 both
#   scripts/codex/uninstall-codex.sh --skills-only   skills only
#   scripts/codex/uninstall-codex.sh --hooks-only    hooks only
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

skills=1
hooks=1
for arg in "$@"; do
  case "$arg" in
    --skills-only) hooks=0 ;;
    --hooks-only) skills=0 ;;
    -h|--help) usage "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown option: $arg (see --help)" ;;
  esac
done
[ "$skills" = 1 ] || [ "$hooks" = 1 ] || die "--skills-only and --hooks-only together remove nothing"

if [ "$skills" = 1 ]; then need uv "Install it from https://docs.astral.sh/uv/ (the skills CLI runs through uv)."; fi
if [ "$hooks" = 1 ]; then need_python39; fi

status=0
if [ "$skills" = 1 ]; then
  info "== Skills"
  "$REPO_ROOT/tools/skills.py" uninstall -p codex || status=1
fi
if [ "$hooks" = 1 ]; then
  info "== Game hooks"
  python3 "$REPO_ROOT/platforms/codex/hooks/install.py" --user --uninstall || status=1
fi
exit "$status"
