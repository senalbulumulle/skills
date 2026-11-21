#!/usr/bin/env bash
# Register this repo's MCP servers (mcp/<category>/<name>/server.py) with Codex, globally ($CODEX_HOME/config.toml):
#   web-dev/motion-forge  reusable Web Components for motion-rich web UI, showcase page, motion audit
#
#   scripts/codex/install-codex-mcp.sh                  register every server, or keep existing registrations
#   scripts/codex/install-codex-mcp.sh -c web-dev       only the servers in these categories (repeatable)
#   scripts/codex/install-codex-mcp.sh --uninstall      remove them, if they point at this checkout
#
# The servers run from this checkout through uv, so re-run this script if you move the repository.
# Registrations from an older layout of this checkout are moved to the current server path.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

uninstall=0
categories=""
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) uninstall=1; shift ;;
    -c|--category) [ $# -ge 2 ] || die "$1 needs a category, for example -c web-dev"; categories="$categories $2"; shift 2 ;;
    --category=*) categories="$categories ${1#--category=}"; shift ;;
    -h|--help) usage "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

# SERVERS: "category/name" for every mcp/<category>/<name>/server.py, filtered by -c.
SERVERS=""
for server in "$REPO_ROOT"/mcp/*/*/server.py; do
  [ -f "$server" ] || continue
  dir="${server%/server.py}"
  SERVERS="$SERVERS ${dir#"$REPO_ROOT/mcp/"}"
done
for category in $categories; do
  [ -d "$REPO_ROOT/mcp/$category" ] || die "no such MCP category: $category (have: $(cd "$REPO_ROOT/mcp" && ls -d */ | tr -d / | tr '\n' ' '))"
done
if [ -n "$categories" ]; then
  kept=""
  for entry in $SERVERS; do
    case " $categories " in *" ${entry%%/*} "*) kept="$kept $entry" ;; esac
  done
  SERVERS="$kept"
fi

need_codex
need_python39

# Prints "same" when $1 is registered with exactly our command for server $2, "ours" when its args mention
# a server.py under this checkout's mcp/ (including an older layout), "other" when another server uses the
# name, and nothing when it isn't registered.
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
elif server in args or any(a.startswith(sys.argv[2]) and a.endswith("/server.py") for a in args):
    print("ours")
else:
    print("other")
' "$2" "$REPO_ROOT/mcp/"
}

if [ "$uninstall" = 1 ]; then
  for entry in $SERVERS; do
    name="${entry#*/}"
    case "$(registration "$name" "$REPO_ROOT/mcp/$entry/server.py")" in
      same|ours) codex mcp remove "$name" ;;
      other) warn "the MCP server '$name' was not registered from this checkout; left alone." ;;
      *) info "The MCP server '$name' is not registered." ;;
    esac
  done
  exit 0
fi

need_uv
status=0
for entry in $SERVERS; do
  name="${entry#*/}"
  server="$REPO_ROOT/mcp/$entry/server.py"
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
  elif [ "$state" = ours ]; then
    codex mcp remove "$name" >/dev/null
    codex mcp add "$name" -- uv run --quiet --script "$server"
    info "Moved the MCP server '$name' to $server."
  else
    codex mcp add "$name" -- uv run --quiet --script "$server"
  fi
done
info "Check them with: codex mcp list (or /mcp inside a session)."
exit "$status"
