#!/usr/bin/env bash
# Install the Codex "game" profile and the game-designer and game-critic agent roles, globally:
# $CODEX_HOME/game.config.toml and $CODEX_HOME/agents/ (default ~/.codex).
#
#   scripts/codex/install-codex-profile.sh                 install or update
#   scripts/codex/install-codex-profile.sh --model SLUG    pick the profile's model yourself
#   scripts/codex/install-codex-profile.sh --dry-run       print the files without writing them
#   scripts/codex/install-codex-profile.sh --uninstall     remove them
#
# Start a session with the profile: codex -p game. Files you wrote yourself are never overwritten.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

need_python39
python3 "$REPO_ROOT/platforms/codex/profile/install.py" "$@"
