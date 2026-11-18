#!/usr/bin/env bash
# Install everything this repo provides for Codex, globally on this device:
#   1. skills -> ~/.agents/skills/        (scripts/codex/install-codex-skills.sh)
#   2. game hooks -> $CODEX_HOME/hooks.json (scripts/codex/install-codex-hooks.sh)
#
#   scripts/codex/install-codex.sh                 both
#   scripts/codex/install-codex.sh --skills-only   skills only
#   scripts/codex/install-codex.sh --hooks-only    hooks only
#
# Safe to re-run: it updates what it installed before and leaves everything else alone.
# Undo with scripts/codex/uninstall-codex.sh.
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
[ "$skills" = 1 ] || [ "$hooks" = 1 ] || die "--skills-only and --hooks-only together install nothing"

# Check every requirement first, so a missing tool can't leave a half-finished install.
if [ "$skills" = 1 ]; then need uv "Install it from https://docs.astral.sh/uv/ (the skills CLI runs through uv)."; fi
if [ "$hooks" = 1 ]; then need_python39; fi

# One step failing (for example a skill folder that already exists and isn't ours) doesn't stop the other.
here="$(dirname "${BASH_SOURCE[0]}")"
status=0
if [ "$skills" = 1 ]; then
  info "== Skills"
  bash "$here/install-codex-skills.sh" || status=1
fi
if [ "$hooks" = 1 ]; then
  info "== Game hooks"
  bash "$here/install-codex-hooks.sh" || status=1
fi
if [ "$status" = 0 ]; then
  info "== Done."
else
  warn "finished with errors; see the messages above."
fi
exit "$status"
