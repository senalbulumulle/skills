#!/usr/bin/env python3
"""Discover the hook surface compiled into the installed Codex binary, including what the docs omit.

  discover.py                       summary for the codex on PATH
  discover.py --binary PATH --json  full report as JSON (save it as a snapshot)
  discover.py --diff OLD.json       what changed since a saved snapshot (exit 1 if anything did)

It reads the binary without running it: the embedded JSON schemas give every event with its input
and output fields, and the runtime's validation messages show which documented-looking outputs
Codex rejects. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import mmap
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA_START = re.compile(rb'\{\s*"\$schema": "http://json-schema\.org/draft-07/schema#"')


def find_binary() -> Path:
    exe = shutil.which("codex")
    if not exe:
        raise SystemExit("error: codex is not on PATH; pass --binary")
    return Path(os.path.realpath(exe))


def codex_version(binary: Path) -> str:
    try:
        out = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"(\d+\.\d+\.\d+\S*)", out)
    return m.group(1) if m else ""


def _schemas(data: bytes) -> list[dict]:
    decoder = json.JSONDecoder()
    found = []
    for m in SCHEMA_START.finditer(data):
        chunk = data[m.start():m.start() + 200_000].decode("utf-8", errors="replace")
        try:
            obj, _ = decoder.raw_decode(chunk)
        except ValueError:
            continue
        if isinstance(obj, dict) and str(obj.get("title", "")).endswith((".command.input", ".command.output")):
            found.append(obj)
    return found


def _literal_hits(data: bytes, literal: bytes) -> list[int]:
    """Offsets of literal in data. A literal find is fast on a 250 MB binary; a leading regex wildcard is not."""
    hits, pos = [], data.find(literal)
    while pos != -1:
        hits.append(pos)
        pos = data.find(literal, pos + 1)
    return hits


def _resolve(schema: dict, prop: dict) -> dict:
    """Follow allOf/$ref one level into the schema's definitions. Boolean schemas (`true`) resolve to {}."""
    if not isinstance(prop, dict):
        return {}
    for ref in [prop.get("$ref")] + [p.get("$ref") for p in prop.get("allOf", []) if isinstance(p, dict)]:
        if ref and ref.startswith("#/definitions/"):
            return schema.get("definitions", {}).get(ref.rsplit("/", 1)[1], {})
    return prop


def _property_names(node: object) -> set:
    """Every key under any "properties" object, at any depth."""
    names = set()
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            names.update(node["properties"])
        for value in node.values():
            names |= _property_names(value)
    elif isinstance(node, list):
        for value in node:
            names |= _property_names(value)
    return names


def analyze(data: bytes) -> dict:
    events: dict[str, dict] = {}
    output_fields: set = set()
    for schema in _schemas(data):
        props = schema.get("properties", {})
        if schema["title"].endswith(".input"):
            name = props.get("hook_event_name", {}).get("const")
            if not name:
                continue
            entry = events.setdefault(name, {})
            entry["input"] = sorted(props)
            entry["required"] = sorted(schema.get("required", []))
            enums = {k: _resolve(schema, v).get("enum") for k, v in props.items()}
            entry["input_enums"] = {k: v for k, v in sorted(enums.items()) if v}
            entry["codex_extensions"] = sorted(k for k, v in props.items()
                                               if isinstance(v, dict) and "Codex extension" in str(v.get("description", "")))
        else:
            output_fields |= _property_names(schema)
            slug = schema["title"].split(".")[0]
            entry = events.setdefault("@" + slug, {})
            entry["output"] = sorted(props)
            specific = _resolve(schema, props.get("hookSpecificOutput", {}))
            if specific.get("properties"):
                entry["hookSpecificOutput"] = sorted(specific["properties"])
            decisions = {}
            for key in ("decision", "permissionDecision"):
                holder = props if key in props else specific.get("properties", {})
                if key in holder:
                    decisions[key] = _resolve(schema, holder[key]).get("enum")
            entry["output_enums"] = {k: v for k, v in decisions.items() if v}
    # Outputs are keyed by kebab-case slug; attach them to the CamelCase event names.
    for slug in [k for k in events if k.startswith("@")]:
        camel = "".join(part.title() for part in slug[1:].split("-"))
        events.setdefault(camel, {}).update(events.pop(slug))

    names = sorted(events, key=len, reverse=True)
    fields = sorted(output_fields, key=len, reverse=True)
    rejected = set()
    if names and fields:
        name = rb"(" + b"|".join(re.escape(n.encode()) for n in names) + rb")"
        field = rb"(" + b"|".join(re.escape(f.encode()) for f in fields) + rb")"
        value = rb"(?::(allow|ask|deny|approve|block|true|false))?"
        unsupported = re.compile(name + rb" hook returned unsupported " + field + value)
        requires = re.compile(name + rb" hook returned " + field + rb" without " + field + value)
        # Match only the message whose " hook returned " sits at this hit, so overlapping windows can't
        # produce a truncated duplicate.
        for pos in _literal_hits(data, b" hook returned "):
            start = max(0, pos - 40)
            window = data[start:pos + 200]
            for regex in (unsupported, requires):
                for m in regex.finditer(window):
                    if m.end(1) != pos - start:
                        continue
                    g = [x.decode() if x else "" for x in m.groups()]
                    text = f"{g[0]}: {g[1]}" + (f" requires {g[2]}" if regex is requires else "")
                    rejected.add(text + (f":{g[-1]}" if g[-1] else ""))
    skipped = set()
    for pos in _literal_hits(data, b" hooks are not supported yet"):
        m = re.search(rb"(\w+)$", data[max(0, pos - 30):pos])
        if m:
            skipped.add(m.group(1).decode())
    return {
        "events": dict(sorted(events.items())),
        "rejected_outputs": sorted(rejected),
        "skipped_handler_types": sorted(skipped),
        "bypass_trust_flag": data.find(b"--dangerously-bypass-hook-trust") != -1,
    }


def report(binary: Path) -> dict:
    with open(binary, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
        result = analyze(data)
    return {"codex_version": codex_version(binary), **result}


def diff(old: dict, new: dict) -> list[str]:
    lines = []
    old_e, new_e = old.get("events", {}), new.get("events", {})
    for name in sorted(set(new_e) - set(old_e)):
        lines.append(f"+ event {name}")
    for name in sorted(set(old_e) - set(new_e)):
        lines.append(f"- event {name}")
    for name in sorted(set(old_e) & set(new_e)):
        for key in sorted(set(old_e[name]) | set(new_e[name])):
            a, b = old_e[name].get(key), new_e[name].get(key)
            if a != b:
                lines.append(f"~ {name}.{key}: {json.dumps(a)} -> {json.dumps(b)}")
    for key in ("rejected_outputs", "skipped_handler_types"):
        a, b = set(old.get(key, [])), set(new.get(key, []))
        lines += [f"+ {key}: {x}" for x in sorted(b - a)] + [f"- {key}: {x}" for x in sorted(a - b)]
    return lines


def summary(r: dict) -> str:
    out = [f"Codex {r['codex_version'] or '(unknown version)'}: {len(r['events'])} hook events"]
    for name, e in r["events"].items():
        extra = []
        if e.get("hookSpecificOutput"):
            extra.append("hookSpecificOutput: " + ", ".join(f for f in e["hookSpecificOutput"] if f != "hookEventName"))
        if e.get("output_enums"):
            extra.append("; ".join(f"{k}: {'|'.join(v)}" for k, v in e["output_enums"].items()))
        inputs = {k: v for k, v in e.get("input_enums", {}).items() if k != "permission_mode"}
        if inputs:
            extra.append("; ".join(f"{k}: {'|'.join(v)}" for k, v in inputs.items()))
        out.append(f"  {name}" + (f"  ({' / '.join(extra)})" if extra else ""))
    if r["rejected_outputs"]:
        out.append("Rejected at runtime despite the schema:")
        out += [f"  {x}" for x in r["rejected_outputs"]]
    if r["skipped_handler_types"]:
        out.append("Handler types parsed but skipped: " + ", ".join(r["skipped_handler_types"]))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, help="Codex executable (default: codex on PATH)")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--diff", type=Path, metavar="OLD.json", help="compare with a saved --json report")
    args = ap.parse_args(argv)
    r = report(args.binary.resolve() if args.binary else find_binary())
    if not r["events"]:
        print("error: no hook schemas found; this Codex build may not embed them", file=sys.stderr)
        return 2
    if args.diff:
        changes = diff(json.loads(args.diff.read_text(encoding="utf-8")), r)
        print("\n".join(changes) if changes else "no changes")
        return 1 if changes else 0
    print(json.dumps(r, indent=2) if args.json else summary(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
