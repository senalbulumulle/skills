#!/usr/bin/env python3
"""Generate balance tables instead of guessing numbers. Standard library only.

  balance.py curve --type exp --base 100 --growth 1.15 --levels 20
      Value per level for costs, XP, or enemy HP. Types:
        linear    base + growth * (n - 1)
        poly      base * n ** growth
        exp       base * growth ** (n - 1)
        logistic  base / (1 + e^(-growth * (n - mid)))   (S-curve that levels off at base)
  balance.py ttk --hp 100 250 600 --damage 10 25 40 --rate 2
      Hits and seconds to kill each HP value with each damage value (first hit lands at t = 0).
  balance.py drops --chance 0.05 --tries 10 20 50 [--pity 60]
      Chance of at least one drop within N tries, expected tries, and tries needed for 50/90/99%.

Add --json to any command for machine-readable output.
"""
import argparse
import json
import math
import sys


def fmt(v):
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return f"{int(v):,}"
        return f"{v:,.2f}" if abs(v) < 1e6 else f"{v:,.4g}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows]
    return "\n".join(out)


def curve(args):
    mid = args.mid if args.mid is not None else (args.levels + 1) / 2
    formulas = {
        "linear": lambda n: args.base + args.growth * (n - 1),
        "poly": lambda n: args.base * n ** args.growth,
        "exp": lambda n: args.base * args.growth ** (n - 1),
        "logistic": lambda n: args.base / (1 + math.exp(-args.growth * (n - mid))),
    }
    f = formulas[args.type]
    rows, total, prev = [], 0.0, None
    for n in range(1, args.levels + 1):
        value = f(n)
        if args.round:
            value = float(round(value))
        total += value
        rows.append({"level": n, "value": value, "cumulative": total,
                     "growth_vs_prev": (value / prev) if prev else None})
        prev = value if value != 0 else None
    return rows, table(["level", "value", "cumulative", "x prev"],
                       [[r["level"], r["value"], r["cumulative"],
                         "" if r["growth_vs_prev"] is None else f"{r['growth_vs_prev']:.3f}"] for r in rows])


def ttk(args):
    rows = []
    for hp in args.hp:
        for dmg in args.damage:
            hits = math.ceil(hp / dmg)
            rows.append({"hp": hp, "damage": dmg, "hits": hits, "seconds": (hits - 1) / args.rate})
    return rows, table(["hp", "damage", "hits", "seconds"],
                       [[r["hp"], r["damage"], r["hits"], r["seconds"]] for r in rows])


def tries_for(p, q):
    if p >= 1:
        return 1
    return math.ceil(math.log(1 - q) / math.log(1 - p))


def drops(args):
    p = args.chance
    result = {
        "chance": p,
        "expected_tries": 1 / p,
        "tries_for": {f"{int(q * 100)}%": tries_for(p, q) for q in (0.5, 0.9, 0.99)},
        "within": {str(n): 1 - (1 - p) ** n for n in args.tries},
    }
    lines = [f"chance per try: {p:.4%}   expected tries: {1 / p:.1f}"]
    lines.append(table(["confidence", "tries needed"], [[k, v] for k, v in result["tries_for"].items()]))
    if args.tries:
        lines.append(table(["tries", "chance of at least one"],
                           [[n, f"{v:.2%}"] for n, v in result["within"].items()]))
    if args.pity:
        # With a guarantee on try N, the expected tries are the sum of P(no drop in the first k tries).
        expected = sum((1 - p) ** k for k in range(args.pity))
        result["pity"] = {"guaranteed_by": args.pity, "expected_tries": expected,
                          "share_hitting_pity": (1 - p) ** (args.pity - 1)}
        lines.append(f"pity at try {args.pity}: expected tries {expected:.1f}, "
                     f"{(1 - p) ** (args.pity - 1):.2%} of players reach the pity")
    return result, "\n\n".join(lines)


def positive(kind):
    def check(text):
        v = kind(text)
        if v <= 0:
            raise argparse.ArgumentTypeError(f"must be greater than 0, got {text}")
        return v
    return check


def probability(text):
    v = float(text)
    if not 0 < v <= 1:
        raise argparse.ArgumentTypeError(f"must be in (0, 1], got {text}")
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("curve", help="value per level")
    c.add_argument("--type", choices=["linear", "poly", "exp", "logistic"], required=True)
    c.add_argument("--base", type=float, required=True)
    c.add_argument("--growth", type=float, required=True)
    c.add_argument("--levels", type=positive(int), default=20)
    c.add_argument("--mid", type=float, help="logistic midpoint level (default: middle level)")
    c.add_argument("--round", action="store_true", help="round each value to a whole number")

    t = sub.add_parser("ttk", help="time to kill grid")
    t.add_argument("--hp", type=positive(float), nargs="+", required=True)
    t.add_argument("--damage", type=positive(float), nargs="+", required=True)
    t.add_argument("--rate", type=positive(float), default=1.0, help="attacks per second")

    d = sub.add_parser("drops", help="drop-rate odds")
    d.add_argument("--chance", type=probability, required=True)
    d.add_argument("--tries", type=positive(int), nargs="*", default=[])
    d.add_argument("--pity", type=positive(int), help="drop guaranteed on this try")

    for p in (c, t, d):
        p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    data, text = {"curve": curve, "ttk": ttk, "drops": drops}[args.cmd](args)
    print(json.dumps(data, indent=2) if args.json else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
