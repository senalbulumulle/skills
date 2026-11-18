#!/usr/bin/env bash
# Register this repo's creative-director MCP server with Codex, globally ($CODEX_HOME/config.toml).
#
#   scripts/codex/install-codex-mcp.sh               register, or keep the existing registration
#   scripts/codex/install-codex-mcp.sh --uninstall   remove it, if it points at this checkout
#
# The server runs from this checkout through uv, so re-run this script if you move the repository.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

NAME="creative-director"
SERVER="$REPO_ROOT/mcp/creative-director/server.py"

uninstall=0
for arg in "$@"; do
  case "$arg" in
    --uninstall) uninstall=1 ;;
    -h|--help) usage "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown option: $arg (see --help)" ;;
  esac
done

need_codex
need_python39

# Prints "same" when NAME is registered with exactly our command, "ours" when its args mention this
# checkout's server, "other" when another server uses the name, and nothing when it isn't registered.
registration() {
  local json
  json="$(codex mcp get "$NAME" --json 2>/dev/null)" || return 0
  printf '%s' "$json" | python3 -c '
import json, sys
server = sys.argv[1]
try:
    transport = json.load(sys.stdin).get("transport") or {}
except ValueError:
    print("other"); sys.exit()
args = transport.get("args") or []
if transport.get("command") == "uv" and args == ["run", "--quiet", "--script", server]:
    print("same")
elif server in args:
    print("ours")
else:
    print("other")
' "$SERVER"
}

state="$(registration)"
if [ "$uninstall" = 1 ]; then
  case "$state" in
    same|ours) codex mcp remove "$NAME" ;;
    other) warn "the MCP server '$NAME' was not registered from this checkout; left alone." ;;
    *) info "The MCP server '$NAME' is not registered." ;;
  esac
  exit 0
fi

need_uv
# Download the MCP SDK now, so the first Codex session doesn't spend its startup timeout on it.
uv sync --quiet --script "$SERVER"
case "$state" in
  same) info "The MCP server '$NAME' is already registered." ;;
  other) die "an MCP server named '$NAME' already exists and runs something else; remove it with: codex mcp remove $NAME" ;;
  *) codex mcp add "$NAME" -- uv run --quiet --script "$SERVER" ;;
esac
info "Check it with: codex mcp list (or /mcp inside a session)."
