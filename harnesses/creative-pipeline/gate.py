"""Deterministic anti-slop gate: regex rules, prose cadence, and structural checks on model output.

check(files, message, brief) returns {"passed": bool, "violations": [...], "warnings": [...]}, where each
item is {"rule", "file", "line", "match", "hint"}. Only error-severity rules fail the gate. Rules live in
rules/slop.json so they can be tuned without touching code. Standard library only, Python 3.9+.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Iterable, Optional

HERE = Path(__file__).resolve().parent
RULES_FILE = HERE / "rules" / "slop.json"

PROSE_EXT = {".md", ".markdown", ".txt", ".rst"}
MARKUP_EXT = {".html", ".htm", ".svelte", ".vue", ".jsx", ".tsx"}
CSS_EXT = {".css", ".scss", ".sass", ".less"}
CODE_EXT = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".py", ".gd", ".cs", ".lua", ".rs", ".go", ".java",
            ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".rb", ".php", ".svelte", ".vue", ".html", ".htm"}
SKIP_PARTS = {"node_modules", ".git", "dist", "build", "vendor", ".venv", "__pycache__"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Cargo.lock"}
MAX_FILE_BYTES = 300_000
MAX_REPORTED = 40


def load_rules(path: Path = RULES_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for rule in data["rules"]:
        flags = re.M | (0 if rule.get("case_sensitive") else re.I)
        rule["_re"] = re.compile(rule["pattern"], flags)
        rule["_unless"] = re.compile(rule["unless_brief"], re.I) if rule.get("unless_brief") else None
    return data


# ---------------------------------------------------------------- text extraction

def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _blank(m: re.Match) -> str:
    """Replace a match with spaces but keep its newlines, so line numbers still line up."""
    return re.sub(r"[^\n]", " ", m.group(0))


def code_text(source: str) -> str:
    """String literals and comments from source code (where copy and stubs live), positions preserved."""
    keep = [" "] * len(source)
    pattern = re.compile(r"""("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`|//[^\n]*|\#[^\n]*|/\*.*?\*/|<!--.*?-->)""",
                         re.S)
    for m in pattern.finditer(source):
        keep[m.start():m.end()] = list(m.group(0))
    return "".join(c if c != " " or source[i] != "\n" else "\n" for i, c in enumerate(keep))


def markup_text(source: str) -> str:
    """Visible text of HTML-like markup: scripts, styles, and tags blanked out, positions preserved."""
    text = re.sub(r"<(script|style)\b.*?</\1\s*>", _blank, source, flags=re.S | re.I)
    return re.sub(r"<[^>]*>", _blank, text)


def css_text(source: str) -> str:
    """CSS in a file: the whole file for stylesheets; style blocks and attributes for markup."""
    out = [" "] * len(source)
    for m in re.finditer(r"<style\b[^>]*>(.*?)</style\s*>|style\s*=\s*\"([^\"]*)\"|style\s*=\s*'([^']*)'", source, re.S | re.I):
        group = next(g for g in (1, 2, 3) if m.group(g) is not None)
        out[m.start(group):m.end(group)] = list(m.group(group))
    return "".join(c if source[i] != "\n" else "\n" for i, c in enumerate(out))


def paragraphs(markdown: str) -> list[str]:
    """Running prose from Markdown: no code fences, headings, lists, tables, quotes, or HTML lines."""
    text = re.sub(r"^(```|~~~).*?^\1[^\n]*$", "", markdown, flags=re.S | re.M)
    out, cur = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s or re.match(r"^(#|[-*+]\s|\d+[.)]\s|\||>|<|!\[|---|===)", s):
            if cur:
                out.append(" ".join(cur))
            cur = []
        else:
            cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def sentences(paragraph: str) -> list[str]:
    paragraph = re.sub(r"\b(?:e\.g|i\.e|etc|vs|Mr|Mrs|Dr|St)\.", lambda m: m.group(0).replace(".", ""), paragraph)
    return [s for s in re.split(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z0-9\"'(])", paragraph) if re.search(r"\w", s)]


# ---------------------------------------------------------------- checks

def _kinds(path: str) -> set:
    ext = Path(path).suffix.lower()
    kinds = set()
    if ext in PROSE_EXT:
        kinds.add("prose")
    if ext in MARKUP_EXT:
        kinds.add("markup")
    if ext in CSS_EXT or ext in MARKUP_EXT:
        kinds.add("css")
    if ext in CODE_EXT:
        kinds.add("code")
    return kinds


def _views(path: str, text: str) -> dict:
    """Which text each rule scope sees for one file."""
    kinds = _kinds(path)
    views = {}
    if "prose" in kinds:
        views["prose"] = text
    if "markup" in kinds:
        views["markup"] = text
        views["prose_markup"] = markup_text(text)
    if "css" in kinds:
        views["css"] = text if Path(path).suffix.lower() in CSS_EXT else css_text(text)
    if "code" in kinds:
        views["code"] = code_text(text)
    return views


def _scope_text(rule_scope: str, views: dict) -> list[str]:
    if rule_scope == "all":
        return [v for k, v in views.items() if k in ("prose", "prose_markup", "code", "message")]
    if rule_scope == "prose":
        return [v for k, v in views.items() if k in ("prose", "message")]
    if rule_scope == "markup":
        return [views["markup"]] if "markup" in views else []
    return [views[rule_scope]] if rule_scope in views else []


def _item(rule: str, file: str, line: int, match: str, hint: str) -> dict:
    return {"rule": rule, "file": file, "line": line, "match": match.strip()[:120], "hint": hint}


def check_rules(path: str, views: dict, brief: str, rules: dict) -> list[tuple[str, dict]]:
    found, seen = [], set()
    for rule in rules["rules"]:
        if rule["_unless"] and rule["_unless"].search(brief or ""):
            continue
        for text in _scope_text(rule["applies"], views):
            for m in rule["_re"].finditer(text):
                key = (rule["id"], _line_of(text, m.start()))
                if key in seen:
                    continue
                seen.add(key)
                found.append((rule["severity"], _item(rule["id"], path, key[1], m.group(0), rule["hint"])))
    return found


def check_cadence(path: str, prose: str, rules: dict) -> list[tuple[str, dict]]:
    """Monotone sentence lengths, runs of same-length sentences, and em-dash density."""
    cfg = rules["cadence"]
    found = []
    for para in paragraphs(prose):
        lengths = [len(s.split()) for s in sentences(para)]
        line = _line_of(prose, max(prose.find(para[:40]), 0))
        if len(lengths) >= cfg["min_sentences"]:
            mean = statistics.mean(lengths)
            variation = statistics.pstdev(lengths) / mean if mean else 0
            if variation < cfg["min_variation"]:
                found.append(("error", _item("cadence-monotone", path, line, para[:80],
                                             f"{len(lengths)} sentences with nearly equal lengths ({lengths}); "
                                             "mix short and long sentences.")))
        n, tol = cfg["run_length"], cfg["run_tolerance"]
        for i in range(len(lengths) - n + 1):
            window = lengths[i:i + n]
            if max(window) - min(window) <= tol:
                found.append(("error", _item("cadence-run", path, line, para[:80],
                                             f"{n} sentences in a row of {min(window)}-{max(window)} words; vary the rhythm.")))
                break
    words = len(re.findall(r"\b\w+\b", prose))
    dashes = prose.count("—")
    if words >= cfg["min_words_for_dashes"] and dashes * 100 / words > cfg["max_em_dashes_per_100_words"]:
        found.append(("warn", _item("cadence-em-dash", path, 1, f"{dashes} em dashes in {words} words",
                                    "Use commas, colons, or full stops for most of these.")))
    return found


def gateable(path: str) -> bool:
    p = Path(path)
    if p.name in SKIP_NAMES or SKIP_PARTS & set(p.parts) or p.name.endswith((".min.js", ".min.css", ".map")):
        return False
    return bool(_kinds(path))


def check(files: dict, message: str = "", brief: str = "", rules: Optional[dict] = None) -> dict:
    """Gate a draft: {path: text} for changed files plus the model's final message."""
    rules = rules or load_rules()
    found: list[tuple[str, dict]] = []
    for path, text in sorted(files.items()):
        if not gateable(path) or len(text) > MAX_FILE_BYTES:
            continue
        views = _views(path, text)
        found += check_rules(path, views, brief, rules)
        if "prose" in views:
            found += check_cadence(path, views["prose"], rules)
    if message.strip():
        found += check_rules("(final message)", {"message": message}, brief, rules)
        found += check_cadence("(final message)", message, rules)
    errors = [i for s, i in found if s == "error"]
    warnings = [i for s, i in found if s != "error"]
    return {"passed": not errors, "violations": errors[:MAX_REPORTED], "warnings": warnings[:MAX_REPORTED],
            "counts": {"violations": len(errors), "warnings": len(warnings)}}


def check_structure(value: object, schema: dict, where: str = "$") -> list[dict]:
    """A small JSON-schema subset (type, required, properties, items, minItems, maxItems, minLength, enum)."""
    problems = []
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
    want = schema.get("type")
    if want and (not isinstance(value, types[want]) or (want in ("integer", "number") and isinstance(value, bool))):
        return [_item("schema", where, 0, type(value).__name__, f"{where} must be {want}")]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(_item("schema", where, 0, str(value), f"{where} must be one of {schema['enum']}"))
    if isinstance(value, str) and len(value.strip()) < schema.get("minLength", 0):
        problems.append(_item("schema", where, 0, value, f"{where} needs at least {schema['minLength']} characters"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(_item("schema", where, 0, "", f"{where} is missing '{key}'"))
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                problems += check_structure(value[key], sub, f"{where}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10 ** 9):
            problems.append(_item("schema", where, 0, f"{len(value)} items",
                                  f"{where} needs {schema.get('minItems', 0)} to {schema.get('maxItems', 'any')} items"))
        for i, item in enumerate(value):
            problems += check_structure(item, schema.get("items", {}), f"{where}[{i}]")
    return problems


def extract_json(text: str) -> Optional[object]:
    """The last top-level JSON object in text (models often wrap it in prose or a code fence)."""
    decoder, found, pos = json.JSONDecoder(), None, 0
    while True:
        start = text.find("{", pos)
        if start < 0:
            return found
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            pos = start + 1
            continue
        if isinstance(value, dict):
            found = value
        pos = end  # skip the inside of this object, so nested objects never win


def summarize(report: dict, limit: int = 8) -> list[str]:
    return [f"{v['file']}:{v['line']} {v['rule']}: {v['match']!r} - {v['hint']}" for v in report["violations"][:limit]]


def read_files(root: Path, paths: Iterable[str]) -> dict:
    out = {}
    for rel in paths:
        p = root / rel
        if p.is_file() and gateable(rel) and p.stat().st_size <= MAX_FILE_BYTES:
            try:
                out[rel] = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    return out
