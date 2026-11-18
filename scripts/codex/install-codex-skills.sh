#!/usr/bin/env bash
# Install this repo's skills for Codex, globally: symlinks in ~/.agents/skills/.
#
#   scripts/codex/install-codex-skills.sh                 every skill
#   scripts/codex/install-codex-skills.sh game-feel ...   only the named skills
#
# Skills with a Codex variant (agents/openai.yaml) are built into dist/codex/ first.
# Every skill is validated before anything is linked. Re-run after pulling to pick up new skills.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

need uv "Install it from https://docs.astral.sh/uv/ (the skills CLI runs through uv)."
"$REPO_ROOT/tools/skills.py" install -p codex "$@"
info "Codex skills are in $HOME/.agents/skills. Start a new Codex session and type \$ or /skills to see them."
