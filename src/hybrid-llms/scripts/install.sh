#!/bin/sh
# install.sh - build hybrid-llms and register @hybrid with Claude Code, Codex, and Gemini CLI.
#
# Usage: scripts/install.sh [--prefix DIR] [--only claude,codex,gemini] [--no-build]
#
# Each CLI is configured only if it is installed (or its config folder exists).
# Files that get edited are backed up as *.bak first. Undo with scripts/uninstall.sh.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PREFIX="$HOME/.local"
ONLY="claude,codex,gemini"
BUILD=1

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX=$2; shift 2 ;;
    --only) ONLY=$2; shift 2 ;;
    --no-build) BUILD=0; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
done

want() { case ",$ONLY," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
have() { command -v "$1" >/dev/null 2>&1; }
say() { printf '==> %s\n' "$*"; }

BIN="$PREFIX/bin/hybrid-llms"
PY=python3
have "$PY" || { echo "install.sh: python3 is required to edit CLI configs" >&2; exit 1; }
HELPER="$ROOT/scripts/hybrid_config.py"
BLOCK="$ROOT/integrations/instructions.md"

if [ "$BUILD" = 1 ]; then
  say "building"
  make -C "$ROOT" >/dev/null
  make -C "$ROOT" install PREFIX="$PREFIX" >/dev/null
fi
[ -x "$BIN" ] || { echo "install.sh: $BIN not found (build first or drop --no-build)" >&2; exit 1; }
say "installed $BIN"

CFG_DIR="$HOME/.config/hybrid-llms"
if [ ! -f "$CFG_DIR/config" ]; then
  mkdir -p "$CFG_DIR"
  cp "$ROOT/config.example" "$CFG_DIR/config"
  say "wrote default config $CFG_DIR/config"
else
  say "kept existing config $CFG_DIR/config"
fi

case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) say "note: add $PREFIX/bin to PATH" ;; esac

# ---------- Claude Code ----------
if want claude && { have claude || [ -d "$HOME/.claude" ]; }; then
  CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  if have claude; then
    claude mcp remove --scope user hybrid >/dev/null 2>&1 || true
    claude mcp add --scope user hybrid -- "$BIN" mcp >/dev/null
    say "claude: registered MCP server 'hybrid' (user scope)"
  else
    say "claude: CLI not on PATH; run later: claude mcp add --scope user hybrid -- $BIN mcp"
  fi
  mkdir -p "$CLAUDE_DIR/agents" "$CLAUDE_DIR/skills/hybrid"
  cp "$ROOT/integrations/claude/agents/hybrid.md" "$CLAUDE_DIR/agents/hybrid.md"
  cp "$ROOT/integrations/claude/skills/hybrid/SKILL.md" "$CLAUDE_DIR/skills/hybrid/SKILL.md"
  "$PY" "$HELPER" block-set "$CLAUDE_DIR/CLAUDE.md" "$BLOCK"
  say "claude: installed agent 'hybrid', skill /hybrid, and @hybrid instructions in $CLAUDE_DIR/CLAUDE.md"
fi

# ---------- Codex ----------
if want codex && { have codex || [ -d "${CODEX_HOME:-$HOME/.codex}" ]; }; then
  CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
  mkdir -p "$CODEX_DIR/skills/hybrid"
  "$PY" "$HELPER" codex-add "$CODEX_DIR/config.toml" "$BIN"
  cp "$ROOT/integrations/codex/skills/hybrid/SKILL.md" "$CODEX_DIR/skills/hybrid/SKILL.md"
  "$PY" "$HELPER" block-set "$CODEX_DIR/AGENTS.md" "$BLOCK"
  say "codex: added [mcp_servers.hybrid] to $CODEX_DIR/config.toml, skill \$hybrid, and @hybrid instructions"
fi

# ---------- Gemini CLI ----------
if want gemini && { have gemini || [ -d "$HOME/.gemini" ]; }; then
  GEMINI_DIR="$HOME/.gemini"
  mkdir -p "$GEMINI_DIR/commands"
  "$PY" "$HELPER" gemini-add "$GEMINI_DIR/settings.json" "$BIN"
  cp "$ROOT/integrations/gemini/commands/hybrid.toml" "$GEMINI_DIR/commands/hybrid.toml"
  "$PY" "$HELPER" block-set "$GEMINI_DIR/GEMINI.md" "$BLOCK"
  say "gemini: added mcpServers.hybrid to $GEMINI_DIR/settings.json, command /hybrid, and @hybrid instructions"
fi

say "done. Restart open Claude Code / Codex / Gemini sessions, then try: @hybrid explain what a mutex is"
say "check the setup any time with: hybrid-llms status"
