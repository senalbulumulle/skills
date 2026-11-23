#!/usr/bin/env python3
"""Creative pipeline: Gemini diverges, Claude Code drafts, the anti-slop gate checks, Codex audits and refines.

  pipeline.py run BRIEF.md [--repo DIR] [--mock REPLAY.json] [--skip STEP] [options]   run every step
  pipeline.py dry-run BRIEF.md [--json] [--exact]     compile each step's context and report tokens; no model calls
  pipeline.py index                                   the skill index tier, with its token cost
  pipeline.py gate FILE... [--brief TEXT]             run the anti-slop gate on files (exit 1 when it fails)
  pipeline.py status RUN                              what a run produced
  pipeline.py clean RUN                               remove a run's worktree (its branch stays)
  pipeline.py codex-trust                             how to trust the guard hook in Codex once

A run works in its own git worktree on a pipeline/<run> branch, from the repo's HEAD. It never merges or
pushes: review the branch and merge it yourself. Run files live in <repo>/.creative-pipeline/runs/<run>/,
which is kept out of git status. Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import context  # noqa: E402
import gate  # noqa: E402
import guard  # noqa: E402
import hooks as lifecycle  # noqa: E402
import providers  # noqa: E402

STEPS_FILE = HERE / "steps.json"
DATA_DIR = ".creative-pipeline"
FALLBACK_AUTHOR = ("-c", "user.name=Creative Pipeline", "-c", "user.email=creative-pipeline@localhost")
SKIP_LIST = {".git", "node_modules", ".creative-pipeline", "dist", "build", ".venv", "__pycache__"}


class PipelineError(Exception):
    """A problem the user can fix; printed without a traceback."""


# ---------------------------------------------------------------- git

def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise PipelineError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def commit_all(worktree: Path, message: str) -> bool:
    git(worktree, "add", "-A")
    if not git(worktree, "status", "--porcelain"):
        return False
    author = () if git(worktree, "config", "user.email", check=False) else FALLBACK_AUTHOR
    proc = subprocess.run(["git", *author, "-C", str(worktree), "commit", "-q", "-m", message], capture_output=True, text=True)
    if proc.returncode != 0:
        raise PipelineError(f"commit in {worktree} failed: {proc.stderr.strip()}")
    return True


def exclude_data_dir(repo: Path) -> None:
    common = Path(git(repo, "rev-parse", "--git-common-dir"))
    exclude = (common if common.is_absolute() else repo / common) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if f"/{DATA_DIR}/" not in text.split():
        exclude.write_text(text + ("" if text.endswith("\n") or not text else "\n") + f"/{DATA_DIR}/\n", encoding="utf-8")


# ---------------------------------------------------------------- setup

def load_steps(path: Path = STEPS_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for step in data["steps"]:
        if step.get("schema"):
            step["schema_doc"] = data["schemas"][step["schema"]]
    return data


def brief_title(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip().lstrip("# ").strip()[:100]
    return ""


def baseline(index: context.SkillIndex, registry: dict, steps: list) -> int:
    personas = [(lifecycle.PROMPTS / s["persona"]).read_text(encoding="utf-8") for s in steps]
    return context.baseline_tokens(index, registry, personas, max(s.get("anchors", 0) for s in steps))


PLACEHOLDER_VALUES = {"directions": "(directions from the diverge step)",
                      "must_fix": "(violations the gate still reports after the draft step)",
                      "attempt": "1", "max_attempts": "4", "violations": "[]"}


def write_guard_config(run_dir: Path, work: Path, repo: Path, step: str, approve: list) -> dict:
    config = {"step": step, "write_roots": [str(work)],
              "read_roots": [str(work), str(repo), str(context.REPO / "skills"), str(context.REPO / "platforms")],
              "approve": approve, "log": str(run_dir / "guard.log")}
    (run_dir / guard.CONFIG_NAME).write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


# ---------------------------------------------------------------- API tools (Gemini)

def make_tool_runner(step: dict, work: Path, index: context.SkillIndex, hooks: lifecycle.Hooks, config: dict):
    declared = set(step.get("tools", []))

    def walk(root: Path, limit: int) -> list:
        out = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_LIST)
            for name in sorted(filenames):
                out.append(str((Path(dirpath) / name).relative_to(work)))
                if len(out) >= limit:
                    return out
        return out

    def run_tool(name: str, args: dict) -> dict:
        if name not in declared:
            run_tool.denied.append({"tool": name, "reason": "not declared for this step"})
            return {"error": f"{name} is not available in this step"}
        args = args if isinstance(args, dict) else {}
        if name == "read_skill_reference":
            skill = index.by_name.get(str(args.get("skill", "")))
            if not skill:
                return {"error": f"no skill named {args.get('skill')!r}"}
            target, check_as = skill.path / str(args.get("file", "")), {"path": str(skill.path / str(args.get("file", "")))}
            check_tool = "read_file"
        else:
            target, check_as, check_tool = work / str(args.get("path") or "."), {"path": str(work / str(args.get("path") or "."))}, name
        ctx = hooks.emit("onPreToolCall", {"tool": check_tool, "input": check_as, "cwd": work, "config": config})
        if ctx["deny"]:
            run_tool.denied.append({"tool": name, "reason": ctx["deny"]})
            return {"error": f"blocked: {ctx['deny']}"}
        try:
            if name == "list_files":
                return {"result": "\n".join(walk(target, int(args.get("limit") or 200)))}
            if name in ("read_file", "read_skill_reference"):
                return {"result": target.read_text(encoding="utf-8", errors="replace")[:int(args.get("max_bytes") or 20000)]}
            if name == "search_text":
                pattern, hits = re.compile(str(args.get("pattern", ""))), []
                for rel in walk(target if target.is_dir() else work, 2000):
                    try:
                        for n, line in enumerate((work / rel).read_text(encoding="utf-8").splitlines(), 1):
                            if pattern.search(line):
                                hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                    except (UnicodeDecodeError, OSError):
                        continue
                    if len(hits) >= 100:
                        break
                return {"result": "\n".join(hits) or "no matches"}
        except (OSError, re.error, ValueError) as e:
            return {"error": str(e)}
        return {"error": f"{name} has no implementation"}

    run_tool.denied = []
    return run_tool


# ---------------------------------------------------------------- steps

def gate_text(parsed: object) -> str:
    """The prose inside a structured answer, one string per line, so the gate reads the words, not the JSON."""
    if isinstance(parsed, dict):
        return "\n\n".join(gate_text(v) for v in parsed.values())
    if isinstance(parsed, list):
        return "\n\n".join(gate_text(v) for v in parsed)
    return parsed if isinstance(parsed, str) else ""


def changed_paths(work: Path, base: str) -> list:
    out = git(work, "diff", "--name-only", "--diff-filter=ACMR", base, "HEAD")
    return [p for p in out.splitlines() if p]


def trim_report(report: dict) -> dict:
    return {"passed": report["passed"], "violations": report["violations"][:15], "counts": report["counts"]}


def run_step(step: dict, values: dict, env: dict, args) -> dict:
    hooks, run_dir, work = env["hooks"], env["run_dir"], env["work"]
    config = write_guard_config(run_dir, work, env["repo"], step["id"], args.approve)
    provider = providers.for_step(step, args, env["mock"])
    ctx = hooks.emit("onPrePrompt", {"step": step, "index": env["index"], "registry": env["registry"],
                                     "values": values, "state": env["state"], "baseline": env["baseline"]})
    system = f"Your role in this pipeline: {step.get('role', step['id'])}."
    prompt, history, session = ctx["compiled"].text, None, None
    attempts_max = 1 + (args.max_retries if step.get("gate") else 0)
    record = {"id": step["id"], "provider": step["provider"], "skills": ctx["skills"], "telemetry": ctx["telemetry"],
              "attempts": 0, "all_violations": [], "usage": {}, "denied": [], "status": "failed"}
    parsed, message = None, ""
    for attempt in range(attempts_max):
        record["attempts"] = attempt + 1
        prompt_log = run_dir / "logs" / f"{step['id']}.{attempt + 1}.prompt.md"
        prompt_log.parent.mkdir(parents=True, exist_ok=True)
        prompt_log.write_text(f"<!-- system: {system} -->\n\n{prompt}\n", encoding="utf-8")
        if step["provider"] == "gemini":
            runner = make_tool_runner(step, work, env["index"], hooks, config)
            extra = {"step_id": step["id"], "attempt": attempt} if env["mock"] else {}
            res = provider.generate(system, prompt, step.get("temperature", 1.0), ctx["tools"], runner,
                                    step.get("max_tool_rounds", 4), history, json_mode=bool(step.get("schema")), **extra)
            history, files = res.history, {}
            res.denied = res.denied + runner.denied
        else:
            res = provider.run_cli(step, prompt, system, work, run_dir, session, attempt, env["add_dirs"])
            session = res.session
            commit_all(work, f"pipeline: {step['id']} (attempt {attempt + 1})")
            files = gate.read_files(work, changed_paths(work, env["base"]))
        message = res.text
        parsed = gate.extract_json(message) if step.get("schema") else None
        providers._add_usage(record["usage"], res.usage)
        record["denied"] += res.denied
        out = hooks.emit("onPostDraft", {"files": files, "message": gate_text(parsed) if parsed is not None else message,
                                         "brief": values["brief"], "schema": step.get("schema_doc"), "parsed": parsed,
                                         "rules": env["rules"]})
        report = out["report"]
        record["all_violations"] += report["violations"]
        record["report"] = trim_report(report)
        print(f"  {step['id']} attempt {attempt + 1}: gate {'passed' if report['passed'] else 'failed'} "
              f"({report['counts']['violations']} violations, {report['counts']['warnings']} warnings)", flush=True)
        if report["passed"] or not step.get("gate"):
            record["status"] = "passed"
            break
        for line in gate.summarize(report, 5):
            print(f"    {line}", flush=True)
        if attempt + 1 < attempts_max:
            prompt = lifecycle.render("revise.md", {"attempt": attempt + 1, "max_attempts": attempts_max,
                                                    "violations": json.dumps(trim_report(report), indent=2)})
    else:
        record["status"] = "gate-failed"
    record["output"] = parsed if parsed is not None else message
    if step["provider"] == "codex" and not env["mock"]:
        record["guard_seen"] = any(json.loads(l).get("step") == step["id"] for l in
                                   (run_dir / "guard.log").read_text().splitlines() if l.strip()) \
            if (run_dir / "guard.log").is_file() else False
    return record


def preflight(steps: list, args, mock) -> None:
    """Fail before creating anything when a step's provider can't run."""
    if mock:
        missing = [s["id"] for s in steps if s["id"] not in mock.replay]
        if missing:
            raise PipelineError(f"the replay has no entries for steps {missing}")
        return
    for step in steps:
        if step["provider"] in ("claude", "codex") and not shutil.which(step["provider"]):
            raise PipelineError(f"step {step['id']} needs `{step['provider']}` on PATH (or use --mock, or --skip {step['id']})")
        try:
            providers.for_step(step, args, None)
        except providers.ProviderError as e:
            raise PipelineError(f"step {step['id']}: {e} (or --skip {step['id']})") from None


def run_pipeline(args) -> int:
    repo = Path(args.repo).resolve()
    brief_path = Path(args.brief)
    brief = brief_path.read_text(encoding="utf-8").strip() if brief_path.is_file() else ""
    if not brief:
        raise PipelineError(f"brief {args.brief} is missing or empty")
    if git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        raise PipelineError(f"{repo} is not a git repository")
    repo = Path(git(repo, "rev-parse", "--show-toplevel"))
    base = git(repo, "rev-parse", "HEAD", check=False)
    if not re.fullmatch(r"[0-9a-f]{40,64}", base):
        raise PipelineError("the repository has no commits yet: commit something for the pipeline to start from")
    steps_doc = load_steps(Path(args.steps))
    steps = [s for s in steps_doc["steps"] if s["id"] not in args.skip]
    mock = providers.Mock(json.loads(Path(args.mock).read_text(encoding="utf-8"))) if args.mock else None
    args.max_retries = steps_doc.get("max_retries", 3) if args.max_retries is None else args.max_retries
    preflight(steps, args, mock)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    data = repo / DATA_DIR
    run_dir, work, branch = data / "runs" / run_id, data / "runs" / run_id / "work", f"pipeline/{run_id}"
    exclude_data_dir(repo)
    run_dir.mkdir(parents=True)
    git(repo, "worktree", "add", "-q", "-b", branch, str(work), base)
    (run_dir / "brief.md").write_text(brief + "\n", encoding="utf-8")

    index = context.SkillIndex(context.discover_skills())
    registry = context.load_tools()
    rules = gate.load_rules()
    env = {"hooks": lifecycle.default_hooks(), "run_dir": run_dir, "work": work, "repo": repo, "base": base,
           "index": index, "registry": registry, "rules": rules, "mock": mock,
           "state": lifecycle.load_state(data / "state.json"), "baseline": baseline(index, registry, steps),
           "add_dirs": [context.REPO / "skills"]}
    run = {"id": run_id, "brief_title": brief_title(brief), "branch": branch, "base": base, "steps": [],
           "mock": bool(mock), "status": "running"}
    values = {"brief": brief, "directions": "(no brainstorm step ran; work from the brief)",
              "must_fix": "Nothing from the gate. Find the problems yourself."}
    print(f"run {run_id}: worktree {work} on branch {branch}", flush=True)
    try:
        for step in steps:
            print(f"== {step['id']} ({step['provider']})", flush=True)
            record = run_step(step, values, env, args)
            run["steps"].append(record)
            if step["id"] == "diverge":
                values["directions"] = (json.dumps(record["output"], indent=2) if isinstance(record["output"], dict)
                                        else "(the brainstorm returned nothing usable; work from the brief)")
            if step["id"] == "draft" and record["status"] != "passed":
                values["must_fix"] = "The anti-slop gate still reports these after the draft:\n" + "\n".join(
                    f"- {line}" for line in gate.summarize(record["report"], 15))
            if record.get("guard_seen") is False:
                print("  warning: Codex did not run the guard hook (it runs only trusted hooks). "
                      "See `pipeline.py codex-trust`, or pass --bypass-hook-trust.", flush=True)
        run["status"] = "passed" if all(s["status"] == "passed" for s in run["steps"]) else "gate-failed"
    except (providers.ProviderError, context.BudgetError) as e:
        run["status"], run["error"] = "error", str(e)
    plan = work / "PIPELINE.md"
    if plan.is_file():
        run["decision"] = next((l.strip() for l in plan.read_text(encoding="utf-8").splitlines() if l.strip()), "")
    env["hooks"].emit("onSessionEnd", {"state_path": data / "state.json", "run": run, "rules": rules})
    (run_dir / "report.json").write_text(json.dumps(run, indent=2, default=str) + "\n", encoding="utf-8")
    print_summary(run, run_dir)
    return 0 if run["status"] == "passed" else 1


def print_summary(run: dict, run_dir: Path) -> None:
    print(f"\nrun {run['id']}: {run['status']}" + (f" ({run['error']})" if run.get("error") else ""))
    for s in run["steps"]:
        t = s["telemetry"]
        usage = ", ".join(f"{k} {v}" for k, v in s["usage"].items()) or "no usage reported"
        print(f"  {s['id']:<8} {s['status']:<11} attempts {s['attempts']}  prompt ~{t['total_tokens']} tokens "
              f"(saved ~{t['saved_tokens']}, {t['saved_pct']}%)  {usage}")
        for d in s["denied"]:
            print(f"           guard denied {d['tool']}: {d['reason']}")
    print(f"\nreport: {run_dir / 'report.json'}")
    print(f"review: git diff {run['base'][:12]}..{run['branch']}")
    print(f"merge:  git merge {run['branch']}   (the pipeline never merges or pushes)")


# ---------------------------------------------------------------- other commands

def cmd_dry_run(args) -> int:
    brief_path = Path(args.brief)
    brief = brief_path.read_text(encoding="utf-8").strip() if brief_path.is_file() else ""
    if not brief:
        raise PipelineError(f"brief {args.brief} is missing or empty")
    steps = [s for s in load_steps(Path(args.steps))["steps"] if s["id"] not in args.skip]
    index, registry = context.SkillIndex(context.discover_skills()), context.load_tools()
    base_tokens = baseline(index, registry, steps)
    state = lifecycle.load_state(Path(args.repo).resolve() / DATA_DIR / "state.json")
    hooks, rows = lifecycle.default_hooks(), []
    for step in steps:
        ctx = hooks.emit("onPrePrompt", {"step": step, "index": index, "registry": registry, "state": state,
                                         "values": {"brief": brief, **PLACEHOLDER_VALUES}, "baseline": base_tokens})
        t = ctx["telemetry"]
        if args.exact and step["provider"] == "gemini" and os.environ.get("GEMINI_API_KEY"):
            g = providers.Gemini(args.gemini_model or os.environ.get("GEMINI_MODEL", ""), os.environ["GEMINI_API_KEY"])
            t = context.telemetry(step["id"], ctx["compiled"], ctx["tools"], base_tokens,
                                  g.count_tokens("", ctx["compiled"].text, ctx["tools"]))
        rows.append({"provider": step["provider"], "skills": ctx["skills"], **t})
    index_tokens = context.estimate_tokens(index.index_text())
    summary = {"skills": len(index.skills), "index_tier_tokens": index_tokens,
               "tokens_per_skill": round(index_tokens / max(len(index.skills), 1), 1),
               "baseline_tokens": base_tokens, "steps": rows}
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"skill index tier: {len(index.skills)} skills, ~{index_tokens} tokens (~{summary['tokens_per_skill']} per skill)")
    print(f"baseline (every skill, anchor, persona, and tool schema at once): ~{base_tokens} tokens\n")
    print(f"{'step':<9}{'provider':<9}{'budget':>7}{'prompt':>8}{'tools':>7}{'total':>7}{'saved':>8}{'saved%':>8}  skills / tools / dropped")
    for r in rows:
        exact = f" (exact {r['exact_prompt_tokens']})" if r["exact_prompt_tokens"] is not None else ""
        print(f"{r['step']:<9}{r['provider']:<9}{r['budget']:>7}{r['prompt_tokens']:>8}{r['tool_schema_tokens']:>7}"
              f"{r['total_tokens']:>7}{r['saved_tokens']:>8}{r['saved_pct']:>7}%  "
              f"{','.join(r['skills']) or '-'} / {','.join(r['tools']) or '-'} / {','.join(r['dropped']) or '-'}{exact}")
    print("\nToken counts are estimates (~4 characters per token) unless marked exact. The CLI steps also carry"
          "\nClaude Code's and Codex's own system prompts, which the harness can't see; `run` reports their real usage.")
    return 0


def cmd_index(args) -> int:
    index = context.SkillIndex(context.discover_skills())
    text = index.index_text()
    print(text)
    print(f"\n~{context.estimate_tokens(text)} tokens for {len(index.skills)} skills")
    return 0


def cmd_gate(args) -> int:
    files = {}
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            raise PipelineError(f"no file {f}")
        files[f] = p.read_text(encoding="utf-8", errors="replace")
    message = Path(args.message_file).read_text(encoding="utf-8") if args.message_file else ""
    report = gate.check(files, message, args.brief or "")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def find_run(ref: str, repo: Path) -> Path:
    folder = Path(ref)
    if not (folder / "report.json").is_file() and not (folder / "work").exists():
        folder = repo / DATA_DIR / "runs" / ref
    if not folder.is_dir():
        raise PipelineError(f"no run {ref!r}: pass a run id or its folder")
    return folder.resolve()


def cmd_status(args) -> int:
    folder = find_run(args.run, Path(args.repo).resolve())
    report = folder / "report.json"
    if not report.is_file():
        print(f"{folder.name}: no report yet (still running, or it stopped before the end)")
        return 1
    print_summary(json.loads(report.read_text(encoding="utf-8")), folder)
    return 0


def cmd_clean(args) -> int:
    folder = find_run(args.run, Path(args.repo).resolve())
    work = folder / "work"
    if work.exists():
        git(Path(args.repo).resolve(), "worktree", "remove", "--force", str(work))
    print(f"removed {work}; the branch stays: git branch --list 'pipeline/{folder.name}'")
    return 0


def cmd_codex_trust(args) -> int:
    hook = providers.CodexCLI().hook_config()
    print("Codex runs a hook only after you trust it. Start Codex once with the pipeline's guard hook, run /hooks,")
    print("and trust it; later runs reuse that trust because the command is the same:\n")
    print(f"  codex -c '{hook}'\n")
    print("Or pass --bypass-hook-trust to `run`, which adds --dangerously-bypass-hook-trust to every Codex call.")
    print("That runs all of your enabled hooks without the trust check, so only use it if you know which hooks you have.")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, brief=True):
        if brief:
            p.add_argument("brief", help="a Markdown file describing what to build")
        p.add_argument("--repo", default=".", help="the git repository to build in (default: the current folder)")
        p.add_argument("--steps", default=str(STEPS_FILE), help="the pipeline definition (default: steps.json)")
        p.add_argument("--skip", action="append", default=[], help="leave out a step by id (repeatable)")
        p.add_argument("--gemini-model", default=None, help="Gemini model id (default: $GEMINI_MODEL)")

    p = sub.add_parser("run", help="run every step")
    common(p)
    p.add_argument("--mock", help="a replay file: act out every model call from it instead of calling models")
    p.add_argument("--max-retries", type=int, default=None, help="gate retries per step (default: steps.json, 3)")
    p.add_argument("--approve", action="append", default=[],
                   help="a regex of shell commands the guard allows anyway (repeatable), e.g. '^git push origin pipeline/'")
    p.add_argument("--claude-model", default=None, help="passed to claude --model")
    p.add_argument("--codex-model", default=None, help="passed to codex exec -m")
    p.add_argument("--bypass-hook-trust", action="store_true", help="let Codex run the guard without stored trust")
    p.add_argument("--timeout", type=float, default=3600, help="seconds per CLI session turn (default 3600)")
    p.set_defaults(fn=run_pipeline)

    p = sub.add_parser("dry-run", help="compile each step's context and report tokens; no model calls")
    common(p)
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--exact", action="store_true", help="count Gemini prompt tokens with its countTokens endpoint")
    p.set_defaults(fn=cmd_dry_run)

    p = sub.add_parser("index", help="print the skill index tier")
    p.set_defaults(fn=cmd_index)

    p = sub.add_parser("gate", help="run the anti-slop gate on files")
    p.add_argument("files", nargs="+")
    p.add_argument("--brief", help="brief text, for rules that a brief can switch off")
    p.add_argument("--message-file", help="a file holding a model's final message to check too")
    p.set_defaults(fn=cmd_gate)

    for name, fn, text in (("status", cmd_status, "what a run produced"), ("clean", cmd_clean, "remove a run's worktree")):
        p = sub.add_parser(name, help=text)
        p.add_argument("run")
        p.add_argument("--repo", default=".")
        p.set_defaults(fn=fn)

    p = sub.add_parser("codex-trust", help="how to trust the guard hook in Codex")
    p.set_defaults(fn=cmd_codex_trust)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except PipelineError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
