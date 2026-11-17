#!/usr/bin/env python3
"""Create a Rojo project for a Roblox game from this skill's template.

Usage: new_project.py PATH [--name GameName]

Creates PATH (which must not exist or must be empty) with default.project.json, .luaurc, and
src/{server,client,shared} including PlayerData, RemoteGuard, and a server/client entry point.
Then: cd PATH && rojo serve   (connect from the Rojo plugin in Roblox Studio)
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "rojo-template"
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ -]{0,49}$")


def create(dest: Path, name: str) -> list:
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise ValueError(f"{dest} already exists and is not an empty folder")
    if not NAME_RE.match(name):
        raise ValueError("name must start with a letter and use letters, digits, spaces, '-' or '_' (max 50)")
    shutil.copytree(TEMPLATE, dest, dirs_exist_ok=True)
    project = dest / "default.project.json"
    data = json.loads(project.read_text(encoding="utf-8"))
    data["name"] = name
    project.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--name", help="project name (default: folder name)")
    args = ap.parse_args(argv)
    name = args.name or args.path.resolve().name
    try:
        files = create(args.path, name)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"Created Rojo project '{name}' at {args.path}:")
    for f in files:
        print(f"  {f}")
    print(f"Next: cd {args.path} && rojo serve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
