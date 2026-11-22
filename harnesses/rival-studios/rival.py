#!/usr/bin/env python3
"""Rival studios: several agents build the same brief in separate git worktrees, a blind judge plays every
build and picks a winner, and the winner takes the best ideas from the others.

  rival.py start BRIEF.md [--repo DIR] [--studios N] [--name NAME]   create a run: one worktree per studio
  rival.py build RUN [--agent claude|codex] [--trust edits|full]     every studio builds the brief, in parallel
  rival.py judge RUN [--agent ...]                                    a blind judge scores the builds
  rival.py merge RUN [--agent ...]                                    the winner takes the ideas the judge named
  rival.py run BRIEF.md [options]                                     all four steps
  rival.py status RUN                                                 what each step produced
  rival.py clean RUN                                                  remove the worktrees (branches stay)

RUN is a run id or its folder (<repo>/.rival/<id>). Studios branch from the repo's HEAD commit and never touch
your working tree; the winner's branch is left for you to review and merge. --agent-cmd runs any other agent:
a JSON list where {prompt}, {cwd}, and {last} (a file for the final message) are replaced.
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
STANCES = json.loads((HERE / "studios.json").read_text(encoding="utf-8"))
CRITERIA = ("works", "hook", "feel", "originality", "polish")
RUNS_DIR = ".rival"
FALLBACK_AUTHOR = ("-c", "user.name=Rival Studios", "-c", "user.email=rival-studios@localhost")


class RivalError(Exception):
    """A problem the user can fix; printed without a traceback."""


# ---------------------------------------------------------------- git and files

def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RivalError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def commit_all(worktree: Path, message: str) -> bool:
    """Commit every change in the worktree; True when there was something to commit."""
    git(worktree, "add", "-A")
    if not git(worktree, "status", "--porcelain"):
        return False
    author = () if git(worktree, "config", "user.email", check=False) else FALLBACK_AUTHOR
    proc = subprocess.run(["git", *author, "-C", str(worktree), "commit", "-q", "-m", message],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RivalError(f"commit in {worktree} failed: {proc.stderr.strip()}")
    return True


def load_run(ref: str, repo: Optional[Path] = None) -> tuple[Path, dict]:
    folder = Path(ref)
    if not (folder / "run.json").is_file():
        folder = (repo or Path.cwd()) / RUNS_DIR / ref
    if not (folder / "run.json").is_file():
        raise RivalError(f"no run {ref!r}: pass a run id or its folder")
    return folder.resolve(), json.loads((folder / "run.json").read_text(encoding="utf-8"))


def save_run(folder: Path, run: dict) -> None:
    (folder / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


def render(template: str, **values: str) -> str:
    text = (PROMPTS / template).read_text(encoding="utf-8")
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)) - set(values))
    if missing:
        raise RivalError(f"{template} has unfilled placeholders: {missing}")
    # One pass, so a brief that happens to contain {{...}} is inserted as written.
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], text)


# ---------------------------------------------------------------- agents

def agent_argv(agent: str, trust: str, prompt: str, cwd: Path, last: Path, read_dirs: list,
               custom: Optional[list] = None, model: Optional[str] = None) -> list:
    """The command that runs one agent turn headless in cwd."""
    if custom:
        return [part.replace("{prompt}", prompt).replace("{cwd}", str(cwd)).replace("{last}", str(last))
                for part in custom]
    if agent == "claude":
        mode = "bypassPermissions" if trust == "full" else "acceptEdits"
        argv = ["claude", "-p", "--permission-mode", mode, "--output-format", "text"]
        argv += ["--model", model] if model else []
        for d in read_dirs:
            argv += ["--add-dir", str(d)]
        return argv + [prompt]
    if agent == "codex":
        sandbox = ["--dangerously-bypass-approvals-and-sandbox"] if trust == "full" else ["-s", "workspace-write"]
        chosen = ["-m", model] if model else []
        return ["codex", "exec", "-C", str(cwd), *sandbox, *chosen, "--skip-git-repo-check", "-o", str(last), prompt]
    raise RivalError(f"unknown agent {agent!r}: use claude, codex, or --agent-cmd")


def launch(argv: list, cwd: Path, log: Path):
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("w", encoding="utf-8")
    try:
        return subprocess.Popen(argv, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL), handle
    except FileNotFoundError:
        handle.close()
        raise RivalError(f"{argv[0]} is not installed or not on PATH")


def wait_all(procs: dict, timeout: float) -> dict:
    """Wait for every process; {key: exit code, or None when it timed out and was killed}."""
    deadline, codes = time.monotonic() + timeout, {}
    for key, (proc, handle) in procs.items():
        try:
            codes[key] = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            codes[key] = None
        handle.close()
    return codes


def final_message(last: Path, log: Path) -> str:
    """What the agent said last: the {last} file when it wrote one, else its whole output."""
    if last.is_file() and last.read_text(encoding="utf-8").strip():
        return last.read_text(encoding="utf-8")
    return log.read_text(encoding="utf-8") if log.is_file() else ""


def run_one(args, prompt: str, cwd: Path, log: Path, read_dirs: list) -> tuple[Optional[int], str]:
    last = log.with_suffix(".last.txt")
    last.unlink(missing_ok=True)
    argv = agent_argv(args.agent, args.trust, prompt, cwd, last, read_dirs, args.agent_cmd, args.model)
    code = wait_all({"one": launch(argv, cwd, log)}, args.timeout)["one"]
    return code, final_message(last, log)


# ---------------------------------------------------------------- verdicts

def extract_json(text: str) -> Optional[dict]:
    """The last JSON object in the text that has a "winner" key."""
    decoder, found = json.JSONDecoder(), None
    for m in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(value, dict) and "winner" in value:
            found = value
    return found


def validate_verdict(verdict: object, ids: list) -> list:
    """Problems with a judge's verdict; an empty list means it can be used."""
    if not isinstance(verdict, dict):
        return ["the verdict is not a JSON object"]
    problems = []
    winner, scores, steal = verdict.get("winner"), verdict.get("scores"), verdict.get("steal", [])
    if winner not in ids:
        problems.append(f"winner {winner!r} is not one of {ids}")
    if not isinstance(scores, dict) or set(scores) != set(ids):
        problems.append(f"scores must have exactly these entries: {ids}")
        scores = {}
    totals = {}
    for entry, row in scores.items():
        if not isinstance(row, dict) or set(row) != set(CRITERIA):
            problems.append(f"scores[{entry!r}] must score exactly {list(CRITERIA)}")
            continue
        bad = [c for c in CRITERIA if not isinstance(row[c], (int, float)) or isinstance(row[c], bool)
               or not 0 <= row[c] <= 10]
        if bad:
            problems.append(f"scores[{entry!r}] needs numbers from 0 to 10 for {bad}")
        else:
            totals[entry] = sum(row.values())
    if winner in totals and len(totals) == len(ids) and totals[winner] < max(totals.values()):
        problems.append(f"winner {winner!r} scores {totals[winner]}, below the top total {max(totals.values())}")
    if not isinstance(steal, list):
        problems.append("steal must be a list")
        steal = []
    for i, idea in enumerate(steal):
        if not isinstance(idea, dict) or not isinstance(idea.get("idea"), str) or not idea["idea"].strip():
            problems.append(f"steal[{i}] needs an 'idea' string")
        elif idea.get("from") not in ids or idea.get("from") == winner:
            problems.append(f"steal[{i}] must come from an entry other than the winner")
    if not isinstance(verdict.get("reason"), str) or not verdict["reason"].strip():
        problems.append("reason must be a non-empty string")
    return problems


# ---------------------------------------------------------------- steps

def cmd_start(args) -> Path:
    repo = Path(args.repo).resolve()
    brief = Path(args.brief)
    if not brief.is_file() or not brief.read_text(encoding="utf-8").strip():
        raise RivalError(f"brief {brief} is missing or empty")
    if git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        raise RivalError(f"{repo} is not a git repository")
    repo = Path(git(repo, "rev-parse", "--show-toplevel"))
    base = git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False)
    if not base:
        raise RivalError("the repository has no commits yet: commit something for the studios to start from")
    if not 2 <= args.studios <= len(STANCES):
        raise RivalError(f"--studios must be from 2 to {len(STANCES)}")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        print("note: uncommitted changes are not included; studios start from HEAD", file=sys.stderr)

    slug = re.sub(r"[^a-z0-9]+", "-", (args.name or brief.stem).lower()).strip("-")[:30] or "run"
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
    n = 1
    while (repo / RUNS_DIR / run_id).exists():  # two runs in the same second
        n += 1
        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{slug}-{n}"
    folder = repo / RUNS_DIR / run_id
    exclude = Path(git(repo, "rev-parse", "--git-path", "info/exclude"))
    exclude = exclude if exclude.is_absolute() else repo / exclude
    exclude.parent.mkdir(parents=True, exist_ok=True)
    excluded = exclude.read_text(encoding="utf-8").splitlines() if exclude.is_file() else []
    if f"/{RUNS_DIR}/" not in excluded:  # keep runs out of git status without touching .gitignore
        with exclude.open("a", encoding="utf-8") as f:
            f.write(("" if not excluded or excluded[-1] == "" else "\n") + f"/{RUNS_DIR}/\n")

    rng = random.Random(args.seed)
    stances = rng.sample(STANCES, args.studios)
    ids: list = []
    while len(ids) < args.studios:  # random names, so nothing in a path hints at a studio's stance
        new = f"entry-{secrets.token_hex(2)}"
        ids += [] if new in ids else [new]
    entries = []
    for entry_id, stance in zip(ids, stances):
        path = folder / "entries" / entry_id
        branch = f"rival/{run_id}/{entry_id}"
        git(repo, "worktree", "add", "-q", "-b", branch, str(path), base)
        entries.append({"id": entry_id, "branch": branch, "path": str(path), "stance": stance["name"]})
    folder.joinpath("brief.md").write_text(brief.read_text(encoding="utf-8"), encoding="utf-8")
    save_run(folder, {"id": run_id, "repo": str(repo), "base": base, "entries": entries})
    print(f"started {run_id}: {len(entries)} studios in {folder / 'entries'}")
    return folder


def cmd_build(args) -> None:
    folder, run = load_run(args.run, Path(args.repo))
    brief = (folder / "brief.md").read_text(encoding="utf-8")
    by_name = {s["name"]: s for s in STANCES}
    procs = {}
    for e in run["entries"]:
        stance = by_name[e["stance"]]
        prompt = render("studio.md", brief=brief, stance=stance["direction"])
        log = folder / "logs" / f"{e['id']}.build.log"
        last = log.with_suffix(".last.txt")
        last.unlink(missing_ok=True)
        argv = agent_argv(args.agent, args.trust, prompt, Path(e["path"]), last, [], args.agent_cmd, args.model)
        procs[e["id"]] = launch(argv, Path(e["path"]), log)
    started = time.monotonic()
    codes = wait_all(procs, args.timeout)
    for e in run["entries"]:
        code = codes[e["id"]]
        changed = commit_all(Path(e["path"]), "rival: studio build")
        ahead = int(git(Path(e["path"]), "rev-list", "--count", f"{run['base']}..HEAD"))
        error = "timed out" if code is None else f"exit code {code}" if code else ""
        if not ahead:
            error = f"{error}, no changes" if error else "no changes"
        e["build"] = {"exit": code, "ok": not error, "commits": ahead, "committed_leftovers": changed, "error": error}
    run["build_seconds"] = round(time.monotonic() - started)
    save_run(folder, run)
    for e in run["entries"]:
        print(f"{e['id']}: {'ok' if e['build']['ok'] else 'failed: ' + e['build']['error']}")
    if not any(e["build"]["ok"] for e in run["entries"]):
        raise RivalError(f"every studio failed; see {folder / 'logs'}")


def cmd_judge(args) -> dict:
    folder, run = load_run(args.run, Path(args.repo))
    built = [e for e in run["entries"] if e.get("build", {}).get("ok")]
    if not built:
        raise RivalError("no successful builds to judge: run build first")
    ids = [e["id"] for e in built]
    random.Random(args.seed).shuffle(ids)
    if len(ids) == 1:
        verdict = {"winner": ids[0], "scores": None, "steal": [], "reason": "the only studio that built anything"}
    else:
        prompt = render("judge.md", brief=(folder / "brief.md").read_text(encoding="utf-8"),
                        entries="\n".join(f"- {i}/" for i in ids), ids=", ".join(ids),
                        criteria=", ".join(CRITERIA))
        verdict, problems = None, ["no verdict JSON found in the judge's final message"]
        for attempt in range(2):
            code, said = run_one(args, prompt, folder / "entries", folder / "logs" / f"judge-{attempt + 1}.log", [])
            verdict = extract_json(said)
            problems = validate_verdict(verdict, ids) if verdict else ["no verdict JSON found in the judge's final message"]
            if code == 0 and not problems:
                break
            prompt += ("\n\nYour previous verdict could not be used:\n- " + "\n- ".join(problems)
                       + "\nAnswer again with one corrected JSON object.")
        else:
            raise RivalError("the judge gave no usable verdict: " + "; ".join(problems))
    (folder / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    run["winner"] = verdict["winner"]
    save_run(folder, run)
    print(f"winner: {verdict['winner']} ({verdict['reason']})")
    return verdict


def cmd_merge(args) -> None:
    folder, run = load_run(args.run, Path(args.repo))
    if not (folder / "verdict.json").is_file():
        raise RivalError("no verdict yet: run judge first")
    verdict = json.loads((folder / "verdict.json").read_text(encoding="utf-8"))
    paths = {e["id"]: Path(e["path"]) for e in run["entries"]}
    if verdict.get("winner") not in paths or any(s.get("from") not in paths for s in verdict.get("steal", [])):
        raise RivalError(f"{folder / 'verdict.json'} names entries that aren't in this run: run judge again")
    winner = paths[verdict["winner"]]
    if verdict["steal"]:
        ideas = "\n".join(f"- From {paths[s['from']]}: {s['idea']}" for s in verdict["steal"])
        prompt = render("merge.md", brief=(folder / "brief.md").read_text(encoding="utf-8"), ideas=ideas)
        donors = sorted({paths[s["from"]] for s in verdict["steal"]})
        code, _ = run_one(args, prompt, winner, folder / "logs" / "merge.log", donors)
        if code != 0:
            raise RivalError(f"merge failed ({'timed out' if code is None else f'exit code {code}'}); "
                             f"see {folder / 'logs' / 'merge.log'}")
        commit_all(winner, "rival: take ideas from rival studios")
    run["merged"] = True
    save_run(folder, run)
    branch = next(e["branch"] for e in run["entries"] if e["id"] == verdict["winner"])
    print(f"done. Review the winner, then merge it yourself:\n  git diff {run['base'][:12]}..{branch}\n"
          f"  git merge {branch}")


def cmd_status(args) -> None:
    folder, run = load_run(args.run, Path(args.repo))
    print(f"{run['id']} (base {run['base'][:12]})")
    for e in run["entries"]:
        build = e.get("build")
        state = "not built" if not build else "built" if build["ok"] else f"failed: {build['error']}"
        mark = "  <- winner" if run.get("winner") == e["id"] else ""
        print(f"  {e['id']}  {e['stance']:<14} {state}  {e['branch']}{mark}")
    print("merged" if run.get("merged") else "judged" if run.get("winner") else "not judged")


def cmd_clean(args) -> None:
    folder, run = load_run(args.run, Path(args.repo))
    for e in run["entries"]:
        if Path(e["path"]).exists():
            git(Path(run["repo"]), "worktree", "remove", "--force", e["path"])
    shutil.rmtree(folder / "entries", ignore_errors=True)
    git(Path(run["repo"]), "worktree", "prune")
    print(f"removed the worktrees; branches stay: git branch --list 'rival/{run['id']}/*'")


def cmd_run(args) -> None:
    args.run = str(cmd_start(args))
    cmd_build(args)
    cmd_judge(args)
    cmd_merge(args)


# ---------------------------------------------------------------- cli

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    agent = argparse.ArgumentParser(add_help=False)
    agent.add_argument("--agent", default="claude", help="claude (default) or codex")
    agent.add_argument("--trust", choices=("edits", "full"), default="edits",
                       help="edits: file edits only (Claude) or the workspace sandbox (Codex); full: no prompts or sandbox")
    agent.add_argument("--model", help="model for the agent (default: the agent's own setting)")
    agent.add_argument("--agent-cmd", type=json.loads, help='JSON list, e.g. ["my-agent", "--cwd", "{cwd}", "{prompt}"]')
    agent.add_argument("--timeout", type=float, default=3600, help="seconds per step (default 3600)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=".", help="the git repository (default: current folder)")
    common.add_argument("--seed", type=int, help="fix the stance and judging order")
    begin = argparse.ArgumentParser(add_help=False)
    begin.add_argument("brief", help="a Markdown file describing what to build")
    begin.add_argument("--studios", type=int, default=2, help=f"2 to {len(STANCES)} (default 2)")
    begin.add_argument("--name", help="a short name for the run")
    ref = argparse.ArgumentParser(add_help=False)
    ref.add_argument("run", help="run id or folder")
    sub.add_parser("start", parents=[begin, common], help="create a run").set_defaults(fn=cmd_start)
    sub.add_parser("build", parents=[ref, agent, common], help="build in every studio").set_defaults(fn=cmd_build)
    sub.add_parser("judge", parents=[ref, agent, common], help="blind-judge the builds").set_defaults(fn=cmd_judge)
    sub.add_parser("merge", parents=[ref, agent, common], help="give the winner the best ideas").set_defaults(fn=cmd_merge)
    sub.add_parser("run", parents=[begin, agent, common], help="start, build, judge, merge").set_defaults(fn=cmd_run)
    sub.add_parser("status", parents=[ref, common], help="show a run").set_defaults(fn=cmd_status)
    sub.add_parser("clean", parents=[ref, common], help="remove a run's worktrees").set_defaults(fn=cmd_clean)
    return p


def main(argv: Optional[list] = None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "agent_cmd", None) is not None and (
            not isinstance(args.agent_cmd, list) or not all(isinstance(a, str) for a in args.agent_cmd)):
        print("error: --agent-cmd must be a JSON list of strings", file=sys.stderr)
        return 2
    try:
        args.fn(args)
    except RivalError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
