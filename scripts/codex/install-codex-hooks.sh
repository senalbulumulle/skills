#!/usr/bin/env bash
# Install the engine-aware game hooks for Codex, globally: $CODEX_HOME/hooks.json (default ~/.codex).
#
#   scripts/codex/install-codex-hooks.sh            install or update
#   scripts/codex/install-codex-hooks.sh --dry-run  print the resulting hooks.json without writing it
#
# Other hooks in hooks.json are kept. The hooks run from this checkout, so re-run this script
# if you move the repository. Codex skips new or changed hooks until you trust them in /hooks.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

need_python39
check_codex_hooks_feature
python3 "$REPO_ROOT/platforms/codex/hooks/install.py" --user "$@"
