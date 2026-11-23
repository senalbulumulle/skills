"""Lifecycle hooks: onPrePrompt, onPostDraft, onPreToolCall, onSessionEnd.

Each handler takes the event's context dict and returns it (or None to leave it as is). Handlers run in the
order they were added, so extra ones can be appended after the defaults:

    hooks = default_hooks()
    hooks.on("onPostDraft", my_extra_check)

Defaults:
  onPrePrompt    compile the step's prompt within its token budget: persona, matched skills (execution tier),
                 taste anchors, lessons from earlier runs; sets ctx["compiled"], ctx["tools"], ctx["telemetry"]
  onPostDraft    run the anti-slop gate (and the step's JSON structure, if any); sets ctx["report"]
  onPreToolCall  run the guard; sets ctx["deny"] to a reason, or ''
  onSessionEnd   compact the run into <repo>/.creative-pipeline/state.json for future runs
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import context
import gate
import guard

EVENTS = ("onPrePrompt", "onPostDraft", "onPreToolCall", "onSessionEnd")
PROMPTS = Path(__file__).resolve().parent / "prompts"
KEEP_RUNS = 20
KEEP_DECISIONS = 10
LESSON_MIN_RUNS = 2
MAX_LESSONS = 5


class Hooks:
    def __init__(self):
        self.handlers: dict[str, list] = {e: [] for e in EVENTS}

    def on(self, event: str, fn: Callable[[dict], Optional[dict]]) -> "Hooks":
        if event not in self.handlers:
            raise ValueError(f"unknown hook event {event!r}; use one of {EVENTS}")
        self.handlers[event].append(fn)
        return self

    def emit(self, event: str, ctx: dict) -> dict:
        for fn in self.handlers[event]:
            out = fn(ctx)
            if out is not None:
                ctx = out
        return ctx


def render(template: str, values: dict) -> str:
    text = (PROMPTS / template).read_text(encoding="utf-8")
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)) - set(values))
    if missing:
        raise ValueError(f"{template} has unfilled placeholders: {missing}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values[m.group(1)]), text)  # one pass: inserted text stays as is


# ---------------------------------------------------------------- onPrePrompt

def lessons(state: dict) -> str:
    """What earlier runs got wrong often enough to warn about, plus the user's own notes."""
    counts = state.get("rule_counts", {})
    hints = state.get("rule_hints", {})
    lines = [f"- Earlier runs tripped `{r}` in {n} runs. {hints.get(r, '')}".rstrip()
             for r, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if n >= LESSON_MIN_RUNS][:MAX_LESSONS]
    lines += [f"- {n}" for n in state.get("notes", []) if isinstance(n, str) and n.strip()]
    return ("## Lessons from earlier runs\n\n" + "\n".join(lines)) if lines else ""


def pre_prompt(ctx: dict) -> dict:
    step, index = ctx["step"], ctx["index"]
    sections = [context.Section("persona", render(step["persona"], ctx["values"]), 0)]
    sections.append(context.Section("lessons", lessons(ctx.get("state", {})), 1))
    mode = step.get("skills", "none")
    matched = []
    if mode == "index":
        sections.append(context.Section("skill-index", index.index_text(), 2))
    elif mode == "match":
        matched = index.match(ctx["values"].get("brief", ""), step.get("max_skills", 2), force=step.get("force_skills"))
        for s in matched:
            sections.append(context.Section(f"skill:{s.name}", s.execution_text(0), 2))
            for i, anchor in enumerate(s.anchors(step.get("anchors", 0))):
                sections.append(context.Section(f"anchor:{s.name}:{i + 1}", f"#### Taste anchor ({s.name})\n\n{anchor}", 3))
    seen, unique = set(), []
    for s in sections:  # trim redundant context: identical text goes in once
        key = re.sub(r"\s+", " ", s.text).strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(context.Section(s.name, re.sub(r"\n{3,}", "\n\n", s.text), s.priority))
    compiled = context.compile_sections(unique, step.get("budget", 6000))
    tools = context.select_tools(step.get("tools", []), ctx["registry"])
    ctx.update(compiled=compiled, tools=tools, skills=[s.name for s in matched],
               telemetry=context.telemetry(step["id"], compiled, tools, ctx["baseline"], ctx.get("exact")))
    return ctx


# ---------------------------------------------------------------- onPostDraft

def post_draft(ctx: dict) -> dict:
    report = gate.check(ctx.get("files", {}), ctx.get("message", ""), ctx.get("brief", ""), ctx.get("rules"))
    schema = ctx.get("schema")
    if schema is not None:
        parsed = ctx.get("parsed")
        problems = (gate.check_structure(parsed, schema) if parsed is not None else
                    [{"rule": "schema", "file": "(final message)", "line": 0, "match": "",
                      "hint": "the answer must be one JSON object matching the step's schema"}])
        report["violations"] = problems + report["violations"]
        report["counts"]["violations"] += len(problems)
        report["passed"] = report["passed"] and not problems
    ctx["report"] = report
    return ctx


# ---------------------------------------------------------------- onPreToolCall

def pre_tool_call(ctx: dict) -> dict:
    event = {"cwd": str(ctx["cwd"]), "tool_name": ctx["tool"], "tool_input": ctx.get("input", {})}
    ctx["deny"] = guard.decide(event, ctx["config"], ctx.get("source", "api"))
    return ctx


# ---------------------------------------------------------------- onSessionEnd

def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def compact(state: dict, run: dict, hints: dict) -> dict:
    """Fold one run into the state: keep recent runs and decisions, count rules by runs tripped."""
    state = {"version": 1, "runs": [], "rule_counts": {}, "rule_hints": {}, "decisions": [], "notes": [], **state}
    tripped = sorted({v["rule"] for step in run.get("steps", []) for v in step.get("all_violations", [])})
    for rule in tripped:
        state["rule_counts"][rule] = state["rule_counts"].get(rule, 0) + 1
        if rule in hints:
            state["rule_hints"].setdefault(rule, hints[rule])
    state["runs"] = (state["runs"] + [{
        "id": run["id"], "ended": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief": run.get("brief_title", ""), "status": run.get("status"), "branch": run.get("branch"),
        "attempts": {s["id"]: s.get("attempts", 0) for s in run.get("steps", [])}, "tripped": tripped}])[-KEEP_RUNS:]
    if run.get("decision"):
        state["decisions"] = (state["decisions"] + [{"run": run["id"], "decision": run["decision"]}])[-KEEP_DECISIONS:]
    return state


def session_end(ctx: dict) -> dict:
    path: Path = ctx["state_path"]
    hints = {r["id"]: r["hint"] for r in (ctx.get("rules") or gate.load_rules())["rules"]}
    hints.update({"cadence-monotone": "Mix short and long sentences.", "cadence-run": "Vary sentence length.",
                  "schema": "Answer in the step's JSON shape."})
    state = compact(load_state(path), ctx["run"], hints)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    ctx["state"] = state
    return ctx


def default_hooks() -> Hooks:
    return (Hooks().on("onPrePrompt", pre_prompt).on("onPostDraft", post_draft)
            .on("onPreToolCall", pre_tool_call).on("onSessionEnd", session_end))
