#!/usr/bin/env python3
"""Check ASCII grid levels for top-down and grid-based games (not platformer jump arcs).

Reports whether every goal is reachable from the start, the shortest path length, floor tiles the
player can never reach, and dead ends. Optional keys and doors: with --keys ab, key 'a' opens door 'A' and key 'b' opens door 'B'.

Usage:
  check_level.py LEVEL.txt [LEVEL.txt ...] [--keys ab] [--wall "#"] [--start S] [--goal G] [--diagonal] [--json]

Legend (defaults): '#' wall, 'S' start (exactly one), 'G' goal (one or more), keys and doors from --keys,
anything else = floor.
Lines starting with ';' are comments (put the legend there).
Exit codes: 0 all goals reachable, 1 a problem was found, 2 usage error.
"""
import argparse
import json
import sys
from collections import deque
from pathlib import Path


def parse(text, wall="#"):
    lines = [line for line in text.rstrip("\n").split("\n") if not line.startswith(";")]  # ; = comment
    width = max((len(line) for line in lines), default=0)
    return [line.ljust(width, wall) for line in lines]  # ragged lines: missing cells are wall


def neighbors(x, y, diagonal):
    steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if diagonal:
        steps += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    for dx, dy in steps:
        yield x + dx, y + dy


def analyze(grid, wall="#", start="S", goal="G", diagonal=False, keys=""):
    height, width = len(grid), len(grid[0]) if grid else 0
    cells = {(x, y): grid[y][x] for y in range(height) for x in range(width)}
    starts = [p for p, c in cells.items() if c == start]
    goals = [p for p, c in cells.items() if c == goal]
    problems = []
    if len(starts) != 1:
        problems.append(f"expected exactly one start '{start}', found {len(starts)}")
    if not goals:
        problems.append(f"no goal '{goal}' found")
    if problems:
        return {"ok": False, "problems": problems}

    key_set = set(keys)

    def is_door(c):
        return c.isupper() and c.lower() in key_set

    def is_key(c):
        return c in key_set

    def passable(p, keys):
        c = cells.get(p)
        if c is None or c == wall:
            return False
        return not is_door(c) or c.lower() in keys

    # BFS over (position, keys held). Keys are few in hand-made levels, so the state space stays small.
    origin = (starts[0], frozenset())
    dist = {origin: 0}
    queue = deque([origin])
    while queue:
        pos, keys = queue.popleft()
        for nxt in neighbors(*pos, diagonal):
            if not passable(nxt, keys):
                continue
            c = cells[nxt]
            nkeys = keys | {c} if is_key(c) else keys
            state = (nxt, nkeys)
            if state not in dist:
                dist[state] = dist[(pos, keys)] + 1
                queue.append(state)

    reached = {}
    for (pos, _), d in dist.items():
        reached[pos] = min(d, reached.get(pos, d))

    goal_paths = {f"{x},{y}": reached.get((x, y)) for x, y in goals}
    for where, d in goal_paths.items():
        if d is None:
            problems.append(f"goal at {where} (x,y) is unreachable")

    floor = [p for p, c in cells.items() if c != wall]
    unreachable = sorted(p for p in floor if p not in reached)
    dead_ends = sorted(
        p for p in reached
        if cells[p] not in (start, goal)
        and sum(1 for n in neighbors(*p, False) if cells.get(n, wall) != wall) == 1
    )
    present = set(cells.values())
    for key in sorted(key_set):
        if key not in present:
            problems.append(f"key '{key}' is not placed in the level")
        if key.upper() not in present:
            problems.append(f"key '{key}' has no door '{key.upper()}' in the level")

    reachable_goals = [d for d in goal_paths.values() if d is not None]
    return {
        "ok": not problems,
        "problems": problems,
        "size": [width, height],
        "shortest_path": min(reachable_goals) if reachable_goals else None,
        "goals": goal_paths,
        "floor_tiles": len(floor),
        "unreachable_tiles": len(unreachable),
        "unreachable_sample": [f"{x},{y}" for x, y in unreachable[:10]],
        "dead_ends": len(dead_ends),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("levels", nargs="+", type=Path)
    ap.add_argument("--wall", default="#")
    ap.add_argument("--start", default="S")
    ap.add_argument("--goal", default="G")
    ap.add_argument("--diagonal", action="store_true", help="allow 8-way movement")
    ap.add_argument("--keys", default="", help="lowercase key letters; each opens the uppercase door of the same letter")
    ap.add_argument("--json", action="store_true", help="print machine-readable results")
    args = ap.parse_args(argv)
    for opt in ("wall", "start", "goal"):
        if len(getattr(args, opt)) != 1:
            ap.error(f"--{opt} must be a single character")
    if not all(k.isalpha() and k.islower() for k in args.keys):
        ap.error("--keys takes lowercase letters, e.g. --keys ab")
    if {k.upper() for k in args.keys} & {args.start, args.goal, args.wall}:
        ap.error("a door letter from --keys clashes with --start, --goal, or --wall")

    results = {}
    for path in args.levels:
        if not path.is_file():
            print(f"error: {path} not found", file=sys.stderr)
            return 2
        results[str(path)] = analyze(parse(path.read_text(encoding="utf-8"), args.wall),
                                     args.wall, args.start, args.goal, args.diagonal, args.keys)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for name, r in results.items():
            print(f"{'ok  ' if r['ok'] else 'FAIL'}  {name}")
            for p in r["problems"]:
                print(f"      problem: {p}")
            if "size" in r:
                print(f"      size {r['size'][0]}x{r['size'][1]}, shortest path {r['shortest_path']}, "
                      f"unreachable floor {r['unreachable_tiles']}/{r['floor_tiles']}, dead ends {r['dead_ends']}")
    return 0 if all(r["ok"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
