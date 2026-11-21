#!/usr/bin/env bash
# Register this repo's MCP servers with Codex, globally ($CODEX_HOME/config.toml):
#   creative-director  concept seeds, design review, unfinished-content scan (any engine)
#   roblox-forge       Rojo project checks, remote map and audit, game-feel audit, odds, DataStore budget
#   motion-forge       reusable Web Components for motion-rich web UI, showcase page, motion audit
#
#   scripts/codex/install-codex-mcp.sh               register all three, or keep existing registrations
#   scripts/codex/install-codex-mcp.sh --uninstall   remove them, if they point at this checkout
#
# The servers run from this checkout through uv, so re-run this script if you move the repository.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

SERVERS="creative-director roblox-forge motion-forge"

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

# Prints "same" when $1 is registered with exactly our command for server $2, "ours" when its args mention
# this checkout's server, "other" when another server uses the name, and nothing when it isn't registered.
registration() {
  local json
  json="$(codex mcp get "$1" --json 2>/dev/null)" || return 0
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
' "$2"
}

if [ "$uninstall" = 1 ]; then
  for name in $SERVERS; do
    case "$(registration "$name" "$REPO_ROOT/mcp/$name/server.py")" in
      same|ours) codex mcp remove "$name" ;;
      other) warn "the MCP server '$name' was not registered from this checkout; left alone." ;;
      *) info "The MCP server '$name' is not registered." ;;
    esac
  done
  exit 0
fi

need_uv
status=0
for name in $SERVERS; do
  server="$REPO_ROOT/mcp/$name/server.py"
  state="$(registration "$name" "$server")"
  if [ "$state" = other ]; then
    printf 'error: %s\n' "an MCP server named '$name' already exists and runs something else; remove it with: codex mcp remove $name" >&2
    status=1
    continue
  fi
  # Download the MCP SDK now, so the first Codex session doesn't spend its startup timeout on it.
  uv sync --quiet --script "$server"
  if [ "$state" = same ]; then
    info "The MCP server '$name' is already registered."
  else
    codex mcp add "$name" -- uv run --quiet --script "$server"
  fi
done
info "Check them with: codex mcp list (or /mcp inside a session)."
exit "$status"
