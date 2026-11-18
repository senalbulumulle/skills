#!/usr/bin/env python3
"""Summarize and compare the models in Codex's model catalog (GPT Sol, Astra, Luna, Terra, ...).

  export_models.py                       summary of `codex debug models` (the catalog this Codex uses)
  export_models.py --catalog FILE        summary of a saved catalog, e.g. ~/.codex/models_cache.json
  export_models.py --compare A B         what differs between two models
  add --json for machine-readable output.

The output describes each model's settings and the shape of its instructions (section headings, sizes,
content hashes). It never prints the instruction text itself, so it is safe to commit.
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# Catalog fields that change how a model behaves in Codex, in display order.
SETTINGS = (
    "display_name", "description", "visibility", "priority", "default_reasoning_level", "reasoning_levels",
    "context_window", "max_context_window", "default_verbosity", "default_reasoning_summary", "tool_mode",
    "shell_type", "apply_patch_tool_type", "web_search_tool_type", "multi_agent_version",
    "multi_agent_reasoning_effort", "experimental_supported_tools", "input_modalities", "truncation_policy",
    "additional_speed_tiers",
)
HEADING = re.compile(r"^(#{1,4}) +(.+?) *$", re.M)


def load_catalog(path: Path | None) -> dict:
    if path is None:
        try:
            out = subprocess.run(["codex", "debug", "models"], capture_output=True, text=True, timeout=60)
        except OSError:
            raise SystemExit("error: codex is not on PATH; pass --catalog FILE instead")
        if out.returncode:
            raise SystemExit(f"error: `codex debug models` failed: {out.stderr.strip()}")
        text = out.stdout
    else:
        text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise SystemExit(f"error: the catalog is not JSON ({e})")
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise SystemExit("error: the catalog has no `models` list")
    if path is None and not data.get("client_version"):
        version = subprocess.run(["codex", "--version"], capture_output=True, text=True, timeout=30).stdout
        data["client_version"] = version.split()[-1] if version.split() else None
    return data


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def sections(text: str) -> list[dict]:
    """Each heading of a Markdown prompt with the size and hash of the text under it."""
    marks = list(HEADING.finditer(text))
    found = []
    for i, m in enumerate(marks):
        body = text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)].strip()
        found.append({"heading": f"{m.group(1)} {m.group(2)}", "chars": len(body), "sha": _digest(body)})
    return found


def _messages(messages: object, prefix: str = "") -> dict:
    """Flatten model_messages to {dotted.key: size and hash}, skipping empty entries."""
    flat = {}
    if isinstance(messages, dict):
        for key, value in messages.items():
            flat.update(_messages(value, f"{prefix}{key}."))
    elif isinstance(messages, str) and messages:
        flat[prefix.rstrip(".")] = {"chars": len(messages), "sha": _digest(messages)}
    elif isinstance(messages, (bool, int, float)):
        flat[prefix.rstrip(".")] = {"value": messages}
    return flat


def summarize(model: dict) -> dict:
    settings = {key: model.get(key) for key in SETTINGS if key != "reasoning_levels"}
    settings["reasoning_levels"] = [level.get("effort") for level in model.get("supported_reasoning_levels") or []
                                    if isinstance(level, dict)]
    messages = model.get("model_messages") or {}
    template = messages.get("instructions_template") or model.get("base_instructions") or ""
    return {
        "slug": model.get("slug"),
        "settings": {key: settings[key] for key in SETTINGS},
        "instructions": {"chars": len(template), "sha": _digest(template), "sections": sections(template)},
        "messages": _messages({k: v for k, v in messages.items() if k != "instructions_template"}),
    }


def compare(a: dict, b: dict) -> dict:
    settings = {key: [a["settings"][key], b["settings"][key]]
                for key in SETTINGS if a["settings"][key] != b["settings"][key]}
    sec_a = {s["heading"]: s for s in a["instructions"]["sections"]}
    sec_b = {s["heading"]: s for s in b["instructions"]["sections"]}
    msg_keys = sorted(set(a["messages"]) | set(b["messages"]))
    return {
        "models": [a["slug"], b["slug"]],
        "settings": settings,
        "same_instructions": a["instructions"]["sha"] == b["instructions"]["sha"],
        "sections_only_in": {a["slug"]: [h for h in sec_a if h not in sec_b],
                             b["slug"]: [h for h in sec_b if h not in sec_a]},
        "sections_changed": [{"heading": h, "chars": [sec_a[h]["chars"], sec_b[h]["chars"]]}
                             for h in sec_a if h in sec_b and sec_a[h]["sha"] != sec_b[h]["sha"]],
        "messages_differ": [k for k in msg_keys if a["messages"].get(k) != b["messages"].get(k)],
    }


def render_summary(catalog: dict, models: list[dict]) -> str:
    lines = [f"Codex model catalog (client {catalog.get('client_version', 'unknown')}): {len(models)} models", ""]
    for m in models:
        s = m["settings"]
        lines.append(f"{m['slug']}  [{s['visibility']}, priority {s['priority']}]  {s['description']}")
        lines.append(f"  reasoning {'/'.join(s['reasoning_levels'])} (default {s['default_reasoning_level']}), "
                     f"context {s['context_window']}, multi-agent {s['multi_agent_version']}, "
                     f"inputs {'+'.join(s['input_modalities'] or [])}")
        if s["experimental_supported_tools"]:
            lines.append(f"  experimental tools: {', '.join(s['experimental_supported_tools'])}")
        ins = m["instructions"]
        lines.append(f"  instructions {ins['chars']} chars, sha {ins['sha']}, "
                     f"{len(ins['sections'])} sections: {' | '.join(x['heading'].lstrip('# ') for x in ins['sections'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_compare(diff: dict) -> str:
    a, b = diff["models"]
    lines = [f"{a} vs {b}"]
    for key, (va, vb) in diff["settings"].items():
        lines.append(f"  {key}: {json.dumps(va)} -> {json.dumps(vb)}")
    lines.append(f"  instructions: {'identical' if diff['same_instructions'] else 'differ'}")
    for slug, headings in diff["sections_only_in"].items():
        if headings:
            lines.append(f"  sections only in {slug}: {' | '.join(headings)}")
    for change in diff["sections_changed"]:
        lines.append(f"  section changed: {change['heading']} ({change['chars'][0]} -> {change['chars'][1]} chars)")
    if diff["messages_differ"]:
        lines.append(f"  other messages that differ: {', '.join(diff['messages_differ'])}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", type=Path, help="a saved catalog JSON (default: ask the installed codex)")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two model slugs")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    catalog = load_catalog(args.catalog)
    models = [summarize(m) for m in catalog["models"] if isinstance(m, dict)]
    if args.compare:
        by_slug = {m["slug"]: m for m in models}
        missing = [s for s in args.compare if s not in by_slug]
        if missing:
            print(f"error: not in the catalog: {', '.join(missing)}. Models: {', '.join(by_slug)}", file=sys.stderr)
            return 1
        diff = compare(by_slug[args.compare[0]], by_slug[args.compare[1]])
        print(json.dumps(diff, indent=2) if args.json else render_compare(diff), end="\n" if args.json else "")
        return 0
    if args.json:
        print(json.dumps({"client_version": catalog.get("client_version"), "models": models}, indent=2))
    else:
        print(render_summary(catalog, models), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
