#!/usr/bin/env python3
"""Install or remove the game_hooks Codex hooks.

  install.py --user                 add to $CODEX_HOME/hooks.json (default ~/.codex), pointing at this checkout
  install.py --project DIR          copy game_hooks.py into DIR/.codex/hooks/ and add to DIR/.codex/hooks.json
  add --uninstall to remove them, --dry-run to print the result without writing.

Only handlers whose command mentions game_hooks.py are added or removed; other hooks are kept.
Codex skips new or changed hooks until you trust them: run /hooks in Codex after installing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "game_hooks.py"
MARK = "game_hooks.py"
# event -> (matcher or None, statusMessage or None). Tool names were confirmed against Codex 0.163.0.
EVENTS = {
    "SessionStart": (None, None),
    "UserPromptSubmit": (None, None),
    "PreToolUse": ("^(Bash|apply_patch)$", None),
    "PostToolUse": ("^apply_patch$", None),
    "Stop": (None, "Checking changed files"),
}
TIMEOUT = 30


def command_for(event: str, script_ref: str) -> str:
    return f"python3 {script_ref} {event}"


def ours(handler: object) -> bool:
    return isinstance(handler, dict) and MARK in str(handler.get("command", ""))


def merge(config: dict, script_ref: str | None) -> dict:
    """Remove our handlers from config, then add them back (unless script_ref is None)."""
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit("error: 'hooks' in the existing file is not an object")
    for event in list(hooks):
        groups = []
        for group in hooks[event] if isinstance(hooks[event], list) else []:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                group = {**group, "hooks": [h for h in group["hooks"] if not ours(h)]}
                if not group["hooks"]:
                    continue
            groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if script_ref is not None:
        for event, (matcher, status) in EVENTS.items():
            handler = {"type": "command", "command": command_for(event, script_ref), "timeout": TIMEOUT}
            if status:
                handler["statusMessage"] = status
            group = {"matcher": matcher, "hooks": [handler]} if matcher else {"hooks": [handler]}
            hooks.setdefault(event, []).append(group)
    if not hooks:
        del config["hooks"]
    return config


def inline_hooks(config_toml: Path) -> bool:
    try:
        text = config_toml.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"^\s*\[\[?hooks\.(?!state\b)", text, re.M))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--user", action="store_true", help="install for every Codex session of this user")
    where.add_argument("--project", type=Path, metavar="DIR", help="install into a game project (a git repository root)")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.user:
        layer = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        copy_to = None
        script_ref = shlex.quote(str(SCRIPT))
    else:
        root = args.project.expanduser().resolve()
        if not (root / ".git").exists():
            print(f"error: {root} is not a git repository root. Project hooks locate the script with "
                  "`git rev-parse --show-toplevel`; use --user for folders outside git.", file=sys.stderr)
            return 1
        layer = root / ".codex"
        copy_to = layer / "hooks" / "game_hooks.py"
        script_ref = '"$(git rev-parse --show-toplevel)/.codex/hooks/game_hooks.py"'

    target = layer / "hooks.json"
    try:
        config = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
    except ValueError as e:
        print(f"error: {target} is not valid JSON ({e}); fix it first.", file=sys.stderr)
        return 1
    if not isinstance(config, dict):
        print(f"error: {target} must contain a JSON object.", file=sys.stderr)
        return 1
    merged = merge(config, None if args.uninstall else script_ref)
    text = json.dumps(merged, indent=2) + "\n"

    if args.dry_run:
        print(f"# {target}\n{text}", end="")
        return 0
    layer.mkdir(parents=True, exist_ok=True)
    if merged:
        target.write_text(text, encoding="utf-8")
    elif target.is_file():
        target.unlink()
    if copy_to is not None:
        if args.uninstall:
            if copy_to.is_file():
                copy_to.unlink()
        else:
            copy_to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SCRIPT, copy_to)

    action = "Removed game hooks from" if args.uninstall else "Installed game hooks in"
    print(f"{action} {target}")
    if inline_hooks(layer / "config.toml"):
        print(f"warning: {layer / 'config.toml'} also defines [hooks]; Codex warns when one layer uses both. "
              "Keep one format.", file=sys.stderr)
    if not args.uninstall:
        print("Next: open Codex and run /hooks to review and trust them (Codex skips untrusted hooks).")
        if copy_to is not None:
            print(f"Commit {copy_to.relative_to(layer.parent)} and .codex/hooks.json so your team gets them too; "
                  "Codex loads project hooks only in trusted projects.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
