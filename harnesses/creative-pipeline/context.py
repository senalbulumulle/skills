"""Two-tier skill loader, context compiler, token budgeter, and tool-schema filter.

Index tier: every skill's name and the first sentence of its description (what loads at startup).
Execution tier: one skill's full SKILL.md body plus up to N taste anchors from its anchors file, loaded only
when the skill matches the step's task. The compiler packs sections by priority into a step's token budget
and reports what it left out and how many tokens it saved against loading every skill and tool schema.

Token counts are estimates (about 4 characters per token, the usual rule of thumb for English and code);
pass exact counts from a provider's token-count endpoint where one is available. Standard library only.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SKILL_ROOTS = [REPO / "skills", REPO / "platforms" / "claude" / "skills"]
TOOLS_FILE = HERE / "tools.json"
DEFAULT_ANCHORS = "references/examples.md"
INDEX_WORDS = 20  # most words of a description the index tier keeps
INDEX_MIN_WORDS = 5  # cut at a clause break only after this many words
# Where a description's leading clause ends and its list of details begins.
CLAUSE_BREAK = re.compile(r",\s+(?:with|by|covering|including|starting|core|then|using|such as)\b")
STOPWORDS = set("""a an and are as at be by for from has have in into is it its of on or that the this to
use used uses using when with without your you asked ask any every add adds make makes making""".split())


class BudgetError(Exception):
    """The mandatory sections of a step don't fit its token budget."""


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


# ---------------------------------------------------------------- skills

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """The small YAML subset skills here use: `key: value` lines and one level of nested mapping."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    data: dict = {}
    parent: Optional[str] = None
    for raw in text[3:end].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\s*)([\w.-]+):\s*(.*)$", raw)
        if not m:
            continue
        indent, key, value = m.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if indent and parent is not None:
            data[parent][key] = value
        elif value == "":
            data[key], parent = {}, key
        else:
            data[key], parent = value, None
    return data, text[end + 4:].lstrip("\n")


def first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return m.group(1) if m else text.strip()


def words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z][a-z0-9-]+", text.lower()):
        for part in w.split("-") + ([w] if "-" in w else []):
            if len(part) > 2 and part not in STOPWORDS:
                out.append(stem(part))
    return out


def stem(word: str) -> str:
    """Crude suffix stripping so 'levels', 'leveling', and 'level' match."""
    if len(word) > 5:
        word = re.sub(r"(?:ing|ed)$", "", word)
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


@dataclass
class Skill:
    name: str
    description: str
    path: Path
    metadata: dict = field(default_factory=dict)

    @property
    def trigger(self) -> str:
        """The description's first sentence, cut to its leading clause (about 20 tokens) for the index tier."""
        sentence = first_sentence(self.description).rstrip(".")
        m = CLAUSE_BREAK.search(sentence)
        if m and len(sentence[:m.start()].split()) >= INDEX_MIN_WORDS:
            return sentence[:m.start()]
        parts = sentence.split()
        return sentence if len(parts) <= INDEX_WORDS else " ".join(parts[:INDEX_WORDS])

    @property
    def index_line(self) -> str:
        return f"- {self.name}: {self.trigger}"

    def body(self) -> str:
        return parse_frontmatter((self.path / "SKILL.md").read_text(encoding="utf-8"))[1]

    def anchors(self, limit: int) -> list[str]:
        """Up to `limit` curated examples: the `## ` sections of the skill's anchors file."""
        rel = self.metadata.get("anchors", DEFAULT_ANCHORS)
        path = (self.path / rel).resolve()
        if limit <= 0 or not path.is_file() or self.path.resolve() not in path.parents:
            return []
        text = path.read_text(encoding="utf-8")
        return [s.strip() for s in re.split(r"(?m)^(?=## )", text) if s.startswith("## ")][:limit]

    def execution_text(self, anchors: int) -> str:
        parts = [f"### Skill: {self.name}\nSkill folder (relative links resolve here): {self.path}\n\n{self.body().strip()}"]
        picked = self.anchors(anchors)
        if picked:
            parts.append("#### Taste anchors\n\n" + "\n\n".join(picked))
        return "\n\n".join(parts)


def discover_skills(roots: Optional[list] = None) -> list[Skill]:
    """Every skill under skills/<category>/<name>/ (and platform-only skills), sorted by name."""
    found: dict[str, Skill] = {}
    for root in roots or SKILL_ROOTS:
        for md in sorted(Path(root).glob("*/*/SKILL.md")):
            meta, _ = parse_frontmatter(md.read_text(encoding="utf-8"))
            name = meta.get("name") or md.parent.name
            if name in found or not meta.get("description"):
                continue
            found[name] = Skill(name, meta["description"], md.parent,
                                meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {})
    return [found[n] for n in sorted(found)]


class SkillIndex:
    def __init__(self, skills: list[Skill]):
        self.skills = skills
        self.by_name = {s.name: s for s in skills}

    def index_text(self) -> str:
        return "Available skills (name: when to use):\n" + "\n".join(s.index_line for s in self.skills)

    def score(self, skill: Skill, task: str) -> float:
        want = set(words(task))
        if not want:
            return 0.0
        desc = skill.description
        use_when = desc[desc.find("Use when"):] if "Use when" in desc else ""
        score = 3.0 * len(want & set(words(skill.name)))
        score += 2.0 * len(want & set(words(use_when)))
        score += 1.0 * len(want & (set(words(desc)) - set(words(use_when))))
        return score

    def match(self, task: str, limit: int = 2, min_score: float = 3.0, force: Optional[list] = None) -> list[Skill]:
        """Forced skills first, then the best keyword matches above min_score (ties broken by name)."""
        picked = [self.by_name[n] for n in (force or []) if n in self.by_name]
        ranked = sorted(self.skills, key=lambda s: (-self.score(s, task), s.name))
        for s in ranked:
            if len(picked) >= limit:
                break
            if s not in picked and self.score(s, task) >= min_score:
                picked.append(s)
        return picked[:max(limit, len(force or []))]


# ---------------------------------------------------------------- tools

def load_tools(path: Path = TOOLS_FILE) -> dict:
    return {t["name"]: t for t in json.loads(path.read_text(encoding="utf-8"))["tools"]}


def select_tools(declared: list, registry: dict) -> list[dict]:
    """Only the schemas a step declares, in its order. An unknown name is a configuration error."""
    unknown = [n for n in declared if n not in registry]
    if unknown:
        raise ValueError(f"steps.json declares unknown tools {unknown}; tools.json has {sorted(registry)}")
    return [registry[n] for n in declared]


def schema_text(schemas: list[dict]) -> str:
    return json.dumps(schemas, separators=(",", ":")) if schemas else ""


# ---------------------------------------------------------------- compiler

@dataclass
class Section:
    name: str
    text: str
    priority: int = 0  # 0 is mandatory; higher numbers are dropped first

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


@dataclass
class Compiled:
    text: str
    included: list
    dropped: list
    tokens: int
    budget: int


def compile_sections(sections: list[Section], budget: int) -> Compiled:
    """Mandatory sections always; optional ones by priority while they fit. Order in the output is kept."""
    sections = [s for s in sections if s.text.strip()]
    mandatory = sum(s.tokens for s in sections if s.priority == 0)
    if mandatory > budget:
        names = ", ".join(f"{s.name} ({s.tokens})" for s in sections if s.priority == 0)
        raise BudgetError(f"mandatory sections need {mandatory} tokens, over the budget of {budget}: {names}")
    keep, used = set(), mandatory
    for s in sorted((s for s in sections if s.priority > 0), key=lambda s: (s.priority, s.tokens)):
        if used + s.tokens <= budget:
            keep.add(id(s))
            used += s.tokens
    chosen = [s for s in sections if s.priority == 0 or id(s) in keep]
    text = "\n\n".join(s.text.strip() for s in chosen)
    return Compiled(text, [s.name for s in chosen], [s.name for s in sections if s not in chosen],
                    estimate_tokens(text), budget)


def baseline_tokens(index: SkillIndex, registry: dict, personas: list[str], anchors: int) -> int:
    """What one prompt would cost with every skill's full instructions and every tool schema loaded."""
    everything = [index.index_text(), schema_text(list(registry.values()))]
    everything += [s.execution_text(anchors) for s in index.skills]
    everything += personas
    return estimate_tokens("\n\n".join(everything))


def telemetry(step: str, compiled: Compiled, tools: list[dict], baseline: int,
              exact: Optional[int] = None) -> dict:
    used = compiled.tokens + estimate_tokens(schema_text(tools))
    return {"step": step, "budget": compiled.budget, "prompt_tokens": compiled.tokens,
            "tool_schema_tokens": estimate_tokens(schema_text(tools)), "tools": [t["name"] for t in tools],
            "total_tokens": used, "baseline_tokens": baseline, "saved_tokens": max(baseline - used, 0),
            "saved_pct": round(100 * max(baseline - used, 0) / baseline, 1) if baseline else 0.0,
            "included": compiled.included, "dropped": compiled.dropped,
            "exact_prompt_tokens": exact, "estimate": exact is None}
