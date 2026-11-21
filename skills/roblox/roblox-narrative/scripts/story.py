#!/usr/bin/env python3
"""Check a Roblox game's story docs and build game files from them.

  story.py review DOCS                                  check the docs; exit 1 on high or medium findings
  story.py build DOCS OUT.luau                          write the dialogue data module for DialogueRunner
  story.py voiceover DOCS OUT.md                        write the voiceover recording script
  story.py localization DOCS OUT.csv [--locales es,fr]  write a LocalizationTable CSV

DOCS is the folder with characters.md, story.md, and dialogue/*.md; the format is in
references/format.md. build refuses while review reports high findings. Output files are only
overwritten if this script wrote them. Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

MARKER = "-- Generated from Markdown by roblox-narrative (story.py build). Don't edit: change the docs and rebuild."
DOCS_LINE_RE = re.compile(r"^-- Docs: (?P<docs>.+) \(sha256 (?P<hash>[0-9a-f]{64})\)$")
VOICEOVER_MARKER = "<!-- Generated from Markdown by roblox-narrative (story.py voiceover). Don't edit. -->"
# The same types DialogueRunner.luau exports (tools/test_game_scripts.py keeps them identical), so a strict
# script can pass the generated table to DialogueRunner.new.
LUAU_TYPES = """export type Line = { id: string, speaker: string, text: string }
export type Choice = {
	id: string?,
	text: string?,
	target: string,
	needs: { string },
	needsNot: { string },
	sets: { string },
	clears: { string },
}
export type Node = { lines: { Line }, choices: { Choice } }
export type Conversation = { title: string, npc: string, start: string, nodes: { [string]: Node } }
export type Data = { characters: { [string]: { name: string } }, conversations: { [string]: Conversation } }
"""
CSV_HEADER = ["Key", "Context", "Example", "Source"]  # the column order of Roblox's own localization CSVs

ID_RE = re.compile(r"[a-z][a-z0-9_]*")
RESERVED_SPEAKERS = {"narrator", "player"}
LUAU_KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "if", "in", "local",
                 "nil", "not", "or", "repeat", "return", "then", "true", "until", "while"}
CHARACTER_FIELDS = ("id", "role", "wants", "voice")
MAX_LINE = 100  # characters a phone shows comfortably in a dialogue box
MAX_CHOICE = 40
MAX_CHOICES = 4
WORDS_PER_SECOND = 2.5  # 150 words per minute, a natural speaking pace

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
FIELD_RE = re.compile(r"^-\s+([A-Za-z][\w ]*?)\s*:\s*(.*?)\s*$")
CHOICE_RE = re.compile(r"^-\s+\[(?P<text>[^\]]*)\]\(#(?P<target>[^)\s]*)\)(?P<rest>.*)$")
CONTINUE_RE = re.compile(r"^->\s*(?P<target>\S*)(?P<rest>.*)$")
LINE_RE = re.compile(r"^(?P<speaker>[a-z][a-z0-9_]*)\s*(?:\((?P<delivery>[^)]*)\))?\s*:\s*(?P<text>.*?)\s*$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


# ---------------------------------------------------------------------------------------------- parsing

def _lines(path: Path) -> list[str]:
    """The file's lines with HTML comments blanked (newlines kept, so line numbers stay right)."""
    text = path.read_text(encoding="utf-8")
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", "", m.group(0)), text).splitlines()


class Report:
    def __init__(self, root: Path):
        self.root = root
        self.findings: list[dict] = []

    def add(self, severity: str, path: Path, line: int | None, issue: str) -> None:
        where = _rel(path, self.root)
        self.findings.append({"severity": severity, "where": f"{where}:{line}" if line else where, "issue": issue})


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def parse_characters(path: Path) -> list[dict]:
    characters, current = [], None
    for number, raw in enumerate(_lines(path), 1):
        line = raw.strip()
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) == 2:
            current = {"name": heading.group(2), "line": number, "fields": {}}
            characters.append(current)
            continue
        field = FIELD_RE.match(line)
        if field and current is not None:
            current["fields"][field.group(1).strip().lower()] = field.group(2)
    return characters


def parse_story(path: Path, report: Report) -> dict:
    story = {"title": None, "premise": "", "acts": [], "flags": {}, "sections": set()}
    section, act = None, None
    for number, raw in enumerate(_lines(path), 1):
        line = raw.strip()
        heading = HEADING_RE.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            if level == 1 and story["title"] is None:
                story["title"] = title
            elif level == 2:
                section, act = title.lower(), None
                story["sections"].add(section)
            elif level == 3 and section == "acts":
                act = {"name": title, "line": number, "goal": ""}
                story["acts"].append(act)
            continue
        field = FIELD_RE.match(line)
        if section == "premise" and line:
            story["premise"] += line + " "
        elif section == "acts" and act is not None and field and field.group(1).lower() == "goal":
            act["goal"] = field.group(2)
        elif section == "flags" and field:
            name = field.group(1).strip()
            if not ID_RE.fullmatch(name):
                report.add("high", path, number, f"flag {name!r} must be lowercase letters, digits, and underscores")
            else:
                story["flags"][name] = number
    return story


def _edge_options(rest: str, path: Path, number: int, report: Report) -> dict | None:
    """Parse `| needs a, !b | sets c | clears d` after a choice or continue."""
    options = {"needs": [], "needsNot": [], "sets": [], "clears": []}
    rest = rest.strip()
    if not rest:
        return options
    if not rest.startswith("|"):
        report.add("high", path, number, f"unexpected text {rest!r}: conditions start with '| needs', '| sets', or "
                                         "'| clears'")
        return None
    for segment in rest[1:].split("|"):
        words = segment.strip().split(None, 1)
        if len(words) != 2 or words[0] not in ("needs", "sets", "clears"):
            report.add("high", path, number, f"{segment.strip()!r} should be 'needs FLAGS', 'sets FLAGS', or "
                                             "'clears FLAGS'")
            return None
        for flag in (f.strip() for f in words[1].split(",")):
            negated = words[0] == "needs" and flag.startswith("!")
            name = flag[1:] if negated else flag
            if not ID_RE.fullmatch(name):
                report.add("high", path, number, f"flag {flag!r} must be lowercase letters, digits, and underscores"
                                                 + (" (only 'needs' takes '!')" if flag.startswith("!") else ""))
                return None
            options["needsNot" if negated else words[0]].append(name)
    return options


def parse_conversation(path: Path, report: Report) -> dict:
    conv = {"id": path.stem, "path": path, "title": None, "npc": None, "start": None, "nodes": {}, "order": []}
    node = None
    for number, raw in enumerate(_lines(path), 1):
        line = raw.strip()
        if not line or line.startswith(">"):
            continue  # blank lines and > notes for the team
        heading = HEADING_RE.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            if level == 1 and conv["title"] is None and node is None:
                conv["title"] = title
            elif level == 2:
                if not ID_RE.fullmatch(title) or title == "end":
                    report.add("high", path, number, f"node {title!r} needs an id of lowercase letters, digits, and "
                                                     "underscores (and not 'end')")
                    node = None
                    continue
                if title in conv["nodes"]:
                    report.add("high", path, number, f"node {title!r} is defined twice")
                node = {"id": title, "line": number, "lines": [], "choices": [], "continue": None}
                conv["nodes"][title] = node
                conv["order"].append(title)
            else:
                report.add("high", path, number, "use # for the title and ## for each node")
            continue
        if node is None:
            field = FIELD_RE.match(line)
            if field and field.group(1).lower() in ("npc", "start"):
                conv[field.group(1).lower()] = field.group(2)
            else:
                report.add("high", path, number, "before the first node, write only '- npc: ID' and '- start: NODE'")
            continue
        choice, cont = CHOICE_RE.match(line), CONTINUE_RE.match(line)
        if choice or cont:
            m = choice or cont
            options = _edge_options(m.group("rest"), path, number, report)
            target = m.group("target")
            if not (ID_RE.fullmatch(target)):
                report.add("high", path, number, f"target {target!r} must be a node id or 'end'")
                continue
            if options is None:
                continue
            edge = {"target": target, "line": number, **options}
            if choice:
                edge["text"] = choice.group("text").strip()
                if not edge["text"]:
                    report.add("high", path, number, "a choice needs text")
                if node["continue"]:
                    report.add("high", path, number, "a node has either choices or one '->' line, not both")
                node["choices"].append(edge)
            else:
                if node["choices"] or node["continue"]:
                    report.add("high", path, number, "a node has either choices or one '->' line, not both")
                node["continue"] = edge
            continue
        spoken = LINE_RE.match(line)
        if spoken:
            if node["choices"] or node["continue"]:
                report.add("high", path, number, "spoken lines come before the node's choices or '->' line")
            if not spoken.group("text"):
                report.add("high", path, number, "a spoken line needs text after the colon")
            node["lines"].append({"speaker": spoken.group("speaker"), "delivery": (spoken.group("delivery") or "").strip(),
                                  "text": spoken.group("text"), "line": number})
            continue
        report.add("high", path, number, "not a spoken line ('speaker (delivery): text'), a choice "
                                         "('- [text](#node)'), a '->' line, or a '>' note")
    return conv


def load(docs: Path) -> tuple[dict, Report]:
    """Parse every doc under DOCS. Returns (story, report)."""
    docs = docs.expanduser().resolve()
    report = Report(docs)
    story = {"docs": docs, "characters": [], "outline": None, "conversations": []}
    if not docs.is_dir():
        report.add("high", docs, None, "docs folder not found")
        return story, report
    characters = docs / "characters.md"
    if characters.is_file():
        story["characters"] = parse_characters(characters)
    else:
        report.add("high", characters, None, "missing: every speaker needs a character sheet")
    outline = docs / "story.md"
    if outline.is_file():
        story["outline"] = parse_story(outline, report)
    else:
        report.add("medium", outline, None, "missing: write the premise, acts, and flags the game sets")
    for path in sorted((docs / "dialogue").glob("*.md")):
        if not ID_RE.fullmatch(path.stem):
            report.add("high", path, None, "rename it: conversation file names use lowercase letters, digits, and "
                                           "underscores (the name becomes the conversation id)")
            continue
        story["conversations"].append(parse_conversation(path, report))
    if not story["conversations"]:
        report.add("high", docs / "dialogue", None, "no conversations: add dialogue/<conversation_id>.md")
    return story, report


# ---------------------------------------------------------------------------------------------- review

def _check(story: dict, report: Report) -> dict:
    docs = story["docs"]
    chars_path = docs / "characters.md"
    ids = {}
    for c in story["characters"]:
        f = c["fields"]
        for key in CHARACTER_FIELDS:
            if not f.get(key):
                report.add("high" if key == "id" else "medium", chars_path, c["line"],
                           f"{c['name']} has no '- {key}:'")
        cid = f.get("id", "")
        if cid and (not ID_RE.fullmatch(cid) or cid in RESERVED_SPEAKERS):
            report.add("high", chars_path, c["line"], f"id {cid!r} must be lowercase letters, digits, and underscores, "
                                                      f"and not {' or '.join(sorted(RESERVED_SPEAKERS))}")
        elif cid in ids:
            report.add("high", chars_path, c["line"], f"id {cid!r} is used twice")
        elif cid:
            ids[cid] = c

    outline = story["outline"]
    if outline is not None:
        path = docs / "story.md"
        if not outline["title"]:
            report.add("medium", path, None, "no '# Title'")
        if not outline["premise"].strip():
            report.add("medium", path, None, "no '## Premise': say who the player is, what they want, and what is in "
                                             "the way")
        if not outline["acts"]:
            report.add("medium", path, None, "no acts: add '## Acts' with a '### ' heading per act")
        for act in outline["acts"]:
            if not act["goal"]:
                report.add("medium", path, act["line"], f"act {act['name']!r} has no '- goal:'")
    declared = dict(outline["flags"]) if outline else {}

    sets, needed, spoken_by = {}, {}, set()
    totals = {"lines": 0, "choices": 0}
    for conv in story["conversations"]:
        path, nodes = conv["path"], conv["nodes"]
        if not conv["title"]:
            report.add("medium", path, None, "no '# Title'")
        if not conv["npc"]:
            report.add("high", path, None, "no '- npc: ID' naming the character who owns this conversation")
        elif conv["npc"] not in ids:
            report.add("high", path, None, f"npc {conv['npc']!r} has no character sheet in characters.md")
        if not conv["start"]:
            report.add("high", path, None, "no '- start: NODE'")
        elif conv["start"] not in nodes:
            report.add("high", path, None, f"start node {conv['start']!r} doesn't exist")
        for node in nodes.values():
            totals["lines"] += len(node["lines"])
            for spoken in node["lines"]:
                if spoken["speaker"] not in ids and spoken["speaker"] not in RESERVED_SPEAKERS:
                    report.add("high", path, spoken["line"], f"speaker {spoken['speaker']!r} has no character sheet")
                spoken_by.add(spoken["speaker"])
                if len(spoken["text"]) > MAX_LINE:
                    report.add("low", path, spoken["line"], f"{len(spoken['text'])} characters: split lines over "
                                                            f"{MAX_LINE} so they fit a phone's dialogue box")
            edges = node["choices"] + ([node["continue"]] if node["continue"] else [])
            totals["choices"] += len(node["choices"])
            if not edges:
                report.add("high", path, node["line"], f"node {node['id']!r} is a dead end: add choices or '-> end'")
            shown = _most_visible(node["choices"])
            if shown > MAX_CHOICES:
                report.add("low", path, node["line"], f"up to {shown} choices show at once: more than {MAX_CHOICES} "
                                                      "crowd a phone screen")
            if node["choices"] and all(c["needs"] or c["needsNot"] for c in node["choices"]):
                report.add("medium", path, node["line"], f"every choice in {node['id']!r} has a condition, so the "
                                                         "player can get stuck: add one with none")
            for edge in edges:
                if edge["target"] != "end" and edge["target"] not in nodes:
                    report.add("high", path, edge["line"], f"target {edge['target']!r} doesn't exist")
                if len(edge.get("text", "")) > MAX_CHOICE:
                    report.add("low", path, edge["line"], f"choice is {len(edge['text'])} characters: keep choices "
                                                          f"under {MAX_CHOICE}")
                for flag in edge["sets"] + edge["clears"]:
                    sets.setdefault(flag, (path, edge["line"]))
                for flag in edge["needs"] + edge["needsNot"]:
                    needed.setdefault(flag, []).append((path, edge["line"], flag in edge["needsNot"]))
        if conv["start"] in nodes:
            seen, todo = set(), [conv["start"]]
            while todo:
                current = todo.pop()
                if current in seen or current not in nodes:
                    continue
                seen.add(current)
                n = nodes[current]
                todo += [e["target"] for e in n["choices"] + ([n["continue"]] if n["continue"] else [])]
            for node_id in conv["order"]:
                if node_id not in seen:
                    report.add("medium", path, nodes[node_id]["line"], f"node {node_id!r} can't be reached from "
                                                                       f"{conv['start']!r}")

    for flag, uses in sorted(needed.items()):
        if flag in sets or flag in declared:
            continue
        path, line, negated = uses[0]
        if negated:
            report.add("low", path, line, f"flag {flag!r} is never set, so '!{flag}' always passes")
        else:
            report.add("high", path, line, f"flag {flag!r} is never set by dialogue or listed under '## Flags' in "
                                            "story.md, so this choice never appears")
    for flag, (path, line) in sorted(sets.items()):
        if flag not in needed and flag not in declared:
            report.add("low", path, line, f"flag {flag!r} is set but nothing checks it: use it, or list it under "
                                          "'## Flags' if game code reads it")
    for cid, c in ids.items():
        if cid not in spoken_by:
            report.add("low", chars_path, c["line"], f"{c['name']} never speaks")
        elif not c["fields"].get("vo"):
            report.add("low", chars_path, c["line"], f"{c['name']} speaks but has no '- vo:' direction for the voice "
                                                     "actor")
    return {"conversations": len(story["conversations"]), "characters": len(ids), **totals,
            "flags": {"set_by_dialogue": sorted(sets), "needed": sorted(needed), "set_by_game": sorted(declared)}}


def _most_visible(choices: list[dict]) -> int:
    """The most choices that can show at the same time, trying every combination of the flags they check."""
    flags = sorted({f for c in choices for f in c["needs"] + c["needsNot"]})
    if len(flags) > 12:
        return len(choices)
    best = 0
    for mask in range(1 << len(flags)):
        on = {f for i, f in enumerate(flags) if mask >> i & 1}
        best = max(best, sum(set(c["needs"]) <= on and not set(c["needsNot"]) & on for c in choices))
    return best


SEVERITY = {"high": 0, "medium": 1, "low": 2}


def review(docs: str | Path) -> dict:
    story, report = load(Path(docs))
    counts = _check(story, report) if story["docs"].is_dir() else {}
    findings = sorted(report.findings, key=lambda f: SEVERITY[f["severity"]])
    return {"ok": not any(f["severity"] in ("high", "medium") for f in findings), **counts, "findings": findings}


# ---------------------------------------------------------------------------------------------- outputs

def sources(docs: Path) -> list[Path]:
    """The files a build reads, in hash order. game_hooks.py selects the same files to spot stale builds."""
    found = [docs / "characters.md"] + ([docs / "story.md"] if (docs / "story.md").is_file() else [])
    return found + sorted((docs / "dialogue").glob("*.md"))


def docs_hash(docs: Path) -> str:
    h = hashlib.sha256()
    for path in sources(docs):
        h.update(path.relative_to(docs).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def lua_string(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append("\\%03d" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _key(name: str) -> str:
    return f'["{name}"]' if name in LUAU_KEYWORDS else name


def _list(items: list[str]) -> str:
    return "{ " + ", ".join(lua_string(i) for i in items) + " }" if items else "{}"


def _ready(docs: str | Path) -> tuple[dict | None, dict]:
    """(parsed story, review) when the docs have no high findings, else (None, review)."""
    result = review(docs)
    if any(f["severity"] == "high" for f in result["findings"]):
        return None, result
    story, _ = load(Path(docs))
    return story, result


def _refuse(result: dict) -> dict:
    high = [f for f in result["findings"] if f["severity"] == "high"]
    return {"ok": False, "error": f"fix the {len(high)} high findings first", "findings": high}


def _writable(out: Path, ours) -> str | None:
    if out.is_dir():
        return f"{out} is a folder"
    if out.exists() and not ours(out.read_text(encoding="utf-8", errors="replace")):
        return f"{out} exists and wasn't written by story.py; choose another path or move it"
    return None


def render_module(story: dict, out: Path) -> str:
    docs = story["docs"]
    rel = Path(os.path.relpath(docs, out.parent)).as_posix()
    lines = ["--!strict", MARKER, f"-- Docs: {rel} (sha256 {docs_hash(docs)})", "", LUAU_TYPES,
             "local data: Data = {", "\tcharacters = {"]
    for c in story["characters"]:
        lines.append(f"\t\t{_key(c['fields']['id'])} = {{ name = {lua_string(c['name'])} }},")
    lines += ["\t},", "\tconversations = {"]
    for conv in story["conversations"]:
        lines += [f"\t\t{_key(conv['id'])} = {{",
                  f"\t\t\ttitle = {lua_string(conv['title'] or conv['id'])},",
                  f"\t\t\tnpc = {lua_string(conv['npc'])},",
                  f"\t\t\tstart = {lua_string(conv['start'])},",
                  "\t\t\tnodes = {"]
        for node_id in conv["order"]:
            node = conv["nodes"][node_id]
            lines += [f"\t\t\t\t{_key(node_id)} = {{", "\t\t\t\t\tlines = {"]
            prefix = f"{conv['id']}.{node_id}"
            for i, spoken in enumerate(node["lines"], 1):
                lines.append(f"\t\t\t\t\t\t{{ id = {lua_string(f'{prefix}.{i}')}, "
                             f"speaker = {lua_string(spoken['speaker'])}, text = {lua_string(spoken['text'])} }},")
            lines += ["\t\t\t\t\t},", "\t\t\t\t\tchoices = {"]
            edges = node["choices"] or ([node["continue"]] if node["continue"] else [])
            for i, edge in enumerate(edges, 1):
                label = (f"id = {lua_string(f'{prefix}.choice{i}')}, text = {lua_string(edge['text'])}, "
                         if "text" in edge else "")
                lines.append(f"\t\t\t\t\t\t{{ {label}target = {lua_string(edge['target'])}, "
                             f"needs = {_list(edge['needs'])}, needsNot = {_list(edge['needsNot'])}, "
                             f"sets = {_list(edge['sets'])}, clears = {_list(edge['clears'])} }},")
            lines += ["\t\t\t\t\t},", "\t\t\t\t},"]
        lines += ["\t\t\t},", "\t\t},"]
    lines += ["\t},", "}", "", "return data"]
    return "\n".join(lines) + "\n"


def build(docs: str | Path, out: str | Path) -> dict:
    """Write the dialogue data module DialogueRunner plays."""
    story, result = _ready(docs)
    if story is None:
        return _refuse(result)
    out = Path(out).expanduser().resolve()
    problem = _writable(out, lambda text: MARKER in text.split("\n", 3)[:3])
    if problem:
        return {"ok": False, "error": problem}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_module(story, out), encoding="utf-8")
    return {"ok": True, "wrote": str(out), "conversations": result["conversations"], "lines": result["lines"],
            "choices": result["choices"], "findings": result["findings"]}


def _spoken(story: dict):
    """(conversation, node id, line number in node, line) for every spoken line, in document order."""
    for conv in story["conversations"]:
        for node_id in conv["order"]:
            for i, spoken in enumerate(conv["nodes"][node_id]["lines"], 1):
                yield conv, node_id, i, spoken


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|")


def render_voiceover(story: dict) -> str:
    title = (story["outline"] or {}).get("title") or story["docs"].name
    names = {c["fields"]["id"]: c for c in story["characters"]}
    by_speaker: dict[str, list] = {}
    for conv, node_id, i, spoken in _spoken(story):
        by_speaker.setdefault(spoken["speaker"], []).append((f"{conv['id']}.{node_id}.{i}", spoken))
    order = [c["fields"]["id"] for c in story["characters"]] + sorted(RESERVED_SPEAKERS)
    lines = [VOICEOVER_MARKER, f"# Voiceover script: {title}", "",
             "Record one file per line and name it after the line's ID (for example `"
             + (next(iter(by_speaker.values()))[0][0] if by_speaker else "conversation.node.1")
             + ".ogg`), so recordings match the game's lines. Seconds assume 150 words per minute.", ""]
    total_lines, total_seconds = 0, 0.0
    for speaker in order:
        if speaker not in by_speaker:
            continue
        sheet = names.get(speaker)
        lines.append(f"## {sheet['name'] if sheet else speaker.capitalize()} (`{speaker}`)")
        lines.append("")
        if sheet:
            lines += [f"Voice: {sheet['fields'].get('vo') or 'no direction yet; add a - vo: line to characters.md'}",
                      ""]
        lines += ["| ID | Line | Delivery | Words | Seconds |", "|---|---|---|---|---|"]
        for line_id, spoken in by_speaker[speaker]:
            words = len(spoken["text"].split())
            seconds = max(1.0, round(words / WORDS_PER_SECOND, 1))
            total_lines += 1
            total_seconds += seconds
            lines.append(f"| `{line_id}` | {_cell(spoken['text'])} | {_cell(spoken['delivery'])} | {words} | "
                         f"{seconds:.1f} |")
        lines.append("")
    lines.append(f"Total: {total_lines} lines, about {round(total_seconds)} seconds of audio.")
    return "\n".join(lines) + "\n"


def voiceover(docs: str | Path, out: str | Path) -> dict:
    """Write the recording script: every spoken line grouped by character, with IDs, delivery, and length."""
    story, result = _ready(docs)
    if story is None:
        return _refuse(result)
    out = Path(out).expanduser().resolve()
    problem = _writable(out, lambda text: text.startswith(VOICEOVER_MARKER))
    if problem:
        return {"ok": False, "error": problem}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_voiceover(story), encoding="utf-8")
    return {"ok": True, "wrote": str(out), "lines": result["lines"]}


LOCALE_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,4})?")
KEY_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+")


def render_localization(story: dict, locales: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER + locales)
    for c in story["characters"]:
        writer.writerow([f"characters.{c['fields']['id']}.name", "", "", c["name"]] + [""] * len(locales))
    for conv in story["conversations"]:
        for node_id in conv["order"]:
            node = conv["nodes"][node_id]
            for i, spoken in enumerate(node["lines"], 1):
                writer.writerow([f"{conv['id']}.{node_id}.{i}", "", "", spoken["text"]] + [""] * len(locales))
            for i, choice in enumerate(node["choices"], 1):
                writer.writerow([f"{conv['id']}.{node_id}.choice{i}", "", "", choice["text"]] + [""] * len(locales))
    return buffer.getvalue()


def _our_csv(text: str) -> bool:
    rows = list(csv.reader(io.StringIO(text)))
    return bool(rows) and rows[0][:4] == CSV_HEADER and all(r and KEY_RE.fullmatch(r[0]) for r in rows[1:] if r)


def localization(docs: str | Path, out: str | Path, locales: list[str] | None = None) -> dict:
    """Write a CSV that Roblox's LocalizationTable imports: one row per line, choice, and character name, keyed by
    the same IDs the dialogue module uses."""
    locales = [l.strip().lower() for l in (locales or []) if l.strip()]
    bad = [l for l in locales if not LOCALE_RE.fullmatch(l)]
    if bad:
        return {"ok": False, "error": f"not locale codes: {', '.join(bad)} (use codes like es, pt-br)"}
    story, result = _ready(docs)
    if story is None:
        return _refuse(result)
    out = Path(out).expanduser().resolve()
    problem = _writable(out, _our_csv)
    if problem:
        return {"ok": False, "error": problem}
    out.parent.mkdir(parents=True, exist_ok=True)
    text = render_localization(story, locales)
    out.write_text(text, encoding="utf-8")
    return {"ok": True, "wrote": str(out), "rows": text.count("\n") - 1, "locales": locales}


# ---------------------------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("review").add_argument("docs")
    for name in ("build", "voiceover"):
        p = sub.add_parser(name)
        p.add_argument("docs")
        p.add_argument("out")
    p = sub.add_parser("localization")
    p.add_argument("docs")
    p.add_argument("out")
    p.add_argument("--locales", default="", help="comma-separated locale columns to add, such as es,pt-br")
    args = parser.parse_args(argv)
    if args.command == "review":
        result = review(args.docs)
    elif args.command == "build":
        result = build(args.docs, args.out)
    elif args.command == "voiceover":
        result = voiceover(args.docs, args.out)
    else:
        result = localization(args.docs, args.out, args.locales.split(","))
    print(json.dumps(result, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
