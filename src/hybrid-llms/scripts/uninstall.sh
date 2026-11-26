#!/bin/sh
# uninstall.sh - remove hybrid-llms registrations from Claude Code, Codex, and Gemini CLI,
# stop the managed engine, and remove the binary. Keeps ~/.config/hybrid-llms/config.
#
# Usage: scripts/uninstall.sh [--prefix DIR]
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PREFIX="$HOME/.local"
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX=$2; shift 2 ;;
    *) echo "uninstall.sh: unknown option $1" >&2; exit 2 ;;
  esac
done
have() { command -v "$1" >/dev/null 2>&1; }
say() { printf '==> %s\n' "$*"; }
PY=python3
HELPER="$ROOT/scripts/hybrid_config.py"
BIN="$PREFIX/bin/hybrid-llms"

[ -x "$BIN" ] && "$BIN" -q engine stop >/dev/null 2>&1 || true

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
have claude && claude mcp remove --scope user hybrid >/dev/null 2>&1 || true
rm -f "$CLAUDE_DIR/agents/hybrid.md"
rm -rf "$CLAUDE_DIR/skills/hybrid"
[ -f "$CLAUDE_DIR/CLAUDE.md" ] && "$PY" "$HELPER" block-remove "$CLAUDE_DIR/CLAUDE.md"
say "claude: removed"

CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
[ -f "$CODEX_DIR/config.toml" ] && "$PY" "$HELPER" codex-remove "$CODEX_DIR/config.toml"
rm -rf "$CODEX_DIR/skills/hybrid"
[ -f "$CODEX_DIR/AGENTS.md" ] && "$PY" "$HELPER" block-remove "$CODEX_DIR/AGENTS.md"
say "codex: removed"

GEMINI_DIR="$HOME/.gemini"
[ -f "$GEMINI_DIR/settings.json" ] && "$PY" "$HELPER" gemini-remove "$GEMINI_DIR/settings.json"
rm -f "$GEMINI_DIR/commands/hybrid.toml"
[ -f "$GEMINI_DIR/GEMINI.md" ] && "$PY" "$HELPER" block-remove "$GEMINI_DIR/GEMINI.md"
say "gemini: removed"

rm -f "$BIN"
say "removed $BIN (config kept in $HOME/.config/hybrid-llms)"
