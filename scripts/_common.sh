# Shared helpers for the install scripts. Source it; don't run it.
# Works with the bash 3.2 that ships with macOS.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# Print the comment block at the top of a script (its usage text).
usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$1"
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required but not on PATH. $2"
}

# python3 must be 3.9+ (the hooks use Path.is_relative_to and other 3.9 features).
need_python39() {
  need python3 "Install Python 3.9 or newer."
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
    || die "python3 is $(python3 -c 'import platform; print(platform.python_version())'); the hooks need 3.9 or newer."
}

# Warn (don't fail) when Codex is missing or has hooks turned off: the files still install.
check_codex_hooks_feature() {
  if ! command -v codex >/dev/null 2>&1; then
    warn "codex is not on PATH; files are installed, and Codex will load them once it is installed."
    return 0
  fi
  local state
  # Advisory only: if the command fails (no config yet, older Codex), carry on.
  state="$(codex features list 2>/dev/null | awk '$1 == "hooks" { print $NF }')" || state=""
  if [ "$state" = "false" ]; then
    warn "Codex hooks are turned off. Turn them on with: codex features enable hooks"
  fi
}
