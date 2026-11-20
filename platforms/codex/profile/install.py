#!/usr/bin/env python3
"""Install or remove the Codex "game" profile and the game-designer, game-critic,
roblox-polisher, and narrative-designer agent roles.

  install.py                 write $CODEX_HOME/game.config.toml and a file per role in $CODEX_HOME/agents/ (default ~/.codex)
  install.py --model SLUG    use this model instead of the strongest one the installed Codex lists
  add --uninstall to remove them, --dry-run to print what would be written.

Start a session with the profile: codex -p game. The roles are available in every session; ask for
them by name ("use the game-critic agent"). Files are overwritten or removed only when their first
line is the marker below, so files you wrote yourself are never touched.
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTRUCTIONS = HERE / "game-instructions.md"
ROLES = sorted((HERE / "agents").glob("*.toml"))
MARKER = "# Installed by senalbulumulle/skills (scripts/codex). The installer overwrites and removes only files with this line."
PROFILE_NAME = "game"
# Strongest first. Codex 0.163 lists gpt-6-astra; newer clients add gpt-6.2-astra.
PREFERRED_MODELS = ("gpt-6.2-astra", "gpt-6-astra")
EFFORT = "high"


def listed_models() -> dict | None:
    """{slug: supported reasoning efforts} for the models the installed Codex lists, or None if unavailable."""
    try:
        out = subprocess.run(["codex", "debug", "models"], capture_output=True, text=True, timeout=60)
        catalog = json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(catalog, dict) or not isinstance(catalog.get("models"), list):
        return None
    return {m["slug"]: [level.get("effort") for level in m.get("supported_reasoning_levels") or []]
            for m in catalog["models"] if isinstance(m, dict) and m.get("visibility") == "list" and m.get("slug")}


def choose_model(requested: str | None) -> tuple[str | None, str | None, str]:
    """(model, effort, note). model None means the profile keeps the user's default model."""
    models = listed_models()
    if requested:
        if models is not None and requested not in models:
            raise SystemExit(f"error: {requested} is not in this Codex's model list: {', '.join(models)}")
        efforts = (models or {}).get(requested)
        return requested, EFFORT if efforts is None or EFFORT in efforts else None, f"model {requested} (requested)"
    if models is None:
        return None, EFFORT, "codex is unavailable, so the profile keeps your default model"
    for slug in PREFERRED_MODELS:
        if slug in models:
            return slug, EFFORT if EFFORT in models[slug] else None, f"model {slug}"
    return None, EFFORT, f"none of {', '.join(PREFERRED_MODELS)} is listed, so the profile keeps your default model"


def profile_text(model: str | None, effort: str | None) -> str:
    instructions = INSTRUCTIONS.read_text(encoding="utf-8")
    if "'''" in instructions:
        raise SystemExit(f"error: {INSTRUCTIONS} must not contain ''' (it is embedded in a TOML literal string)")
    lines = [MARKER, f"# Use with: codex -p {PROFILE_NAME}"]
    if model:
        lines.append(f'model = "{model}"')
    if effort:
        lines.append(f'model_reasoning_effort = "{effort}"')
    lines.append(f"developer_instructions = '''\n{instructions.rstrip()}\n'''")
    return "\n".join(lines) + "\n"


def ours(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as f:
            return f.readline().rstrip("\n") == MARKER
    except (OSError, UnicodeDecodeError):
        return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="model slug for the profile")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    targets = {home / f"{PROFILE_NAME}.config.toml": None}
    targets.update({home / "agents" / role.name: role for role in ROLES})
    for role in ROLES:
        if not ours(role):
            raise SystemExit(f"error: {role} must start with the marker line")

    if args.uninstall:
        removed = [t for t in targets if t.is_file() and ours(t)]
        for t in removed:
            print(f"{'Would remove' if args.dry_run else 'Removed'} {t}")
            if not args.dry_run:
                t.unlink()
        agents = home / "agents"
        if not args.dry_run and agents.is_dir() and not any(agents.iterdir()):
            agents.rmdir()
        if not removed:
            print("Nothing to remove.")
        return 0

    foreign = [t for t in targets if t.exists() and not ours(t)]
    if foreign:
        for t in foreign:
            print(f"error: {t} exists and was not installed by this script; rename it or remove it first.",
                  file=sys.stderr)
        return 1
    model, effort, note = choose_model(args.model)
    contents = {t: role.read_text(encoding="utf-8") if role else profile_text(model, effort)
                for t, role in targets.items()}
    if args.dry_run:
        for t, text in contents.items():
            print(f"# {t}\n{text}")
        return 0
    for t, text in contents.items():
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(text, encoding="utf-8")
        print(f"Installed {t}")
    print(f"Profile: {note}, reasoning {effort or 'default'}. Start it with: codex -p {PROFILE_NAME}")
    print("Roles: game-designer, game-critic. Ask for them by name in any session.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
