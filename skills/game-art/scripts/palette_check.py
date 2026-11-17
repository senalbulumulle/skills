#!/usr/bin/env python3
"""Check a game palette for readability: luminance, contrast against the background, and pairs that
look alike in grayscale. Uses the WCAG 2 relative luminance and contrast formulas.

Usage:
  palette_check.py bg=#1b1b2f player=#f4d35e enemy=#ee6c4d pickup=#5fd068 text=#f5f5f5 [--bg bg]

Checks (exit 1 if any fail):
  - Every color vs the background: at least 3:1 (WCAG non-text contrast). Roles starting with "text"
    need 4.5:1 (WCAG AA for normal text).
  - Every pair of gameplay colors: at least 1.5:1, or they are hard to tell apart in grayscale and for
    many color-blind players. Roles starting with "text" or "ui" are UI and skip this pair check.
    Pass --ignore-pairs to skip it entirely.
"""
import argparse
import re
import sys

HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
BG_MIN, TEXT_MIN, PAIR_MIN = 3.0, 4.5, 1.5


def parse_color(text):
    m = HEX.match(text)
    if not m:
        raise ValueError(f"not a hex color: {text}")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def gray_hex(lum):
    # Inverse sRGB transfer: the gray with the same luminance, for a grayscale preview.
    c = lum * 12.92 if lum <= 0.0031308 else 1.055 * lum ** (1 / 2.4) - 0.055
    v = round(max(0.0, min(1.0, c)) * 255)
    return f"#{v:02x}{v:02x}{v:02x}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("colors", nargs="+", help="role=#rrggbb")
    ap.add_argument("--bg", default="bg", help="role name of the background (default: bg)")
    ap.add_argument("--ignore-pairs", action="store_true", help="skip the foreground pair check")
    args = ap.parse_args(argv)

    palette = {}
    for item in args.colors:
        role, sep, value = item.partition("=")
        if not sep or not role:
            ap.error(f"expected role=#rrggbb, got '{item}'")
        try:
            palette[role] = parse_color(value)
        except ValueError as e:
            ap.error(str(e))
    if args.bg not in palette:
        ap.error(f"background role '{args.bg}' is missing (name it {args.bg}=... or pass --bg ROLE)")

    lum = {role: luminance(rgb) for role, rgb in palette.items()}
    problems = []

    print("| role | color | luminance | gray | contrast vs bg | needs |")
    print("| --- | --- | --- | --- | --- | --- |")
    for role, rgb in palette.items():
        color = "#%02x%02x%02x" % rgb
        if role == args.bg:
            print(f"| {role} | {color} | {lum[role]:.3f} | {gray_hex(lum[role])} | - | - |")
            continue
        ratio = contrast(lum[role], lum[args.bg])
        need = TEXT_MIN if role.startswith("text") else BG_MIN
        ok = ratio >= need
        print(f"| {role} | {color} | {lum[role]:.3f} | {gray_hex(lum[role])} | {ratio:.2f}:1 {'ok' if ok else 'LOW'} | {need}:1 |")
        if not ok:
            problems.append(f"{role} vs {args.bg}: {ratio:.2f}:1, needs {need}:1")

    if not args.ignore_pairs:
        fg = [r for r in palette if r != args.bg and not r.startswith(("text", "ui"))]
        for i, a in enumerate(fg):
            for b in fg[i + 1:]:
                ratio = contrast(lum[a], lum[b])
                if ratio < PAIR_MIN:
                    problems.append(f"{a} vs {b}: {ratio:.2f}:1, similar in grayscale; separate by value, "
                                    "or make sure shape or motion tells them apart")

    print()
    for p in problems:
        print(f"problem: {p}")
    print(f"{len(palette)} color(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
