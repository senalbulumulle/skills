#!/usr/bin/env python3
"""onPreToolCall guard: a PreToolUse hook for Claude Code and Codex, and an in-process check for API tools.

As a hook, it reads the event JSON on stdin and finds its run config by walking up from the event's cwd to
a .creative-pipeline-guard.json file, which the harness writes next to each run's worktree. With no config
it is not a pipeline session, so it allows everything and prints nothing. With a config it denies:
  - file writes outside write_roots and file reads outside read_roots
  - destructive or outward-facing shell commands (git push/reset --hard/clean, rm outside the worktree or
    of the worktree itself, sudo, curl | sh, publishing) unless an `approve` regex in the config matches
  - shell redirects and cp/mv into paths outside write_roots
Unlike most hooks, it fails closed: a guard that crashes denies the call, so a bug can't let a command past.
Every decision is appended to the config's log file. Standard library only, Python 3.9+.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

CONFIG_NAME = ".creative-pipeline-guard.json"
WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
READ_TOOLS = {"Read": "file_path", "Glob": "path", "Grep": "path", "LS": "path",
              "list_files": "path", "read_file": "path", "search_text": "path"}
SAFE_SINKS = {"/dev/null", "/dev/stdout", "/dev/stderr"}

DESTRUCTIVE = [
    (r"^git push\b", "pushes to a remote"),
    (r"^git reset\b.*--hard", "discards commits and changes"),
    (r"^git clean\b.*-[a-zA-Z]*f", "deletes untracked files"),
    (r"^git (?:checkout|restore)\b.*(?:\s--\s|\s\.$|--worktree)", "discards working-tree changes"),
    (r"^git branch\b.*\s-[a-zA-Z]*D", "deletes a branch"),
    (r"^git (?:worktree|filter-branch|filter-repo|update-ref|reflog expire|gc --prune|remote|tag -d)\b",
     "rewrites or removes repository state"),
    (r"^git rebase\b", "rewrites history"),
    (r"^(?:sudo|su|doas)\b", "runs as another user"),
    (r"^(?:mkfs\S*|dd|shutdown|reboot|halt|poweroff|diskutil|format)\b", "can wipe disks or stop the machine"),
    (r"^chmod\b.*-R|^chown\b", "changes permissions recursively or ownership"),
    (r"^(?:npm|pnpm|yarn) publish\b|^cargo publish\b|^twine upload\b|^gem push\b|^docker push\b",
     "publishes a package"),
    (r"^gh (?:pr|release|repo|issue) (?:create|delete|merge|edit)\b|^gh api\b", "changes GitHub"),
    (r"^(?:butler push|steamcmd\b.*\+run_app_build|xcrun altool|altool)\b", "uploads a build to a store"),
]
PIPE_TO_SHELL = re.compile(r"\b(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b")


def find_config(cwd: Path) -> Optional[tuple[Path, dict]]:
    for folder in (cwd, *cwd.parents):
        path = folder / CONFIG_NAME
        if path.is_file():
            return path, json.loads(path.read_text(encoding="utf-8"))
    return None


def _resolve(cwd: Path, p: str) -> Path:
    path = Path(os.path.expanduser(p))
    return Path(os.path.normpath(path if path.is_absolute() else cwd / path))


def _inside(path: Path, roots: list) -> bool:
    for root in roots:
        r = Path(os.path.normpath(root))
        if path == r or r in path.parents:
            return True
    return False


def _temp_ok(path: Path) -> bool:
    return str(path) in SAFE_SINKS or _inside(path, [tempfile.gettempdir()])


def segments(command: str) -> Optional[list[list[str]]]:
    """Shell words split into simple commands at ; & | ( ) and newlines, or None when unparsable."""
    try:
        lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return None
    out, cur = [], []
    for w in words:
        if w and set(w) <= set(";&|()"):
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(w)
    if cur:
        out.append(cur)
    return out


def _strip_prefix(words: list[str]) -> list[str]:
    words = list(words)
    while words and (re.match(r"^[A-Za-z_]\w*=", words[0]) or words[0] in ("env", "command", "exec", "time", "nohup")):
        words = words[1:]
    return words


def _approved(command: str, config: dict) -> bool:
    return any(re.search(p, command) for p in config.get("approve", []))


def bash_reason(command: str, cwd: Path, config: dict) -> str:
    """Why a shell command is blocked, or ''."""
    if _approved(command, config):
        return ""
    writes = config.get("write_roots", [])
    if PIPE_TO_SHELL.search(command):
        return "it pipes a download into a shell"
    parsed = segments(command)
    if parsed is None:
        return "the command could not be parsed; split it into simpler commands"
    for seg in parsed:
        for i, w in enumerate(seg[:-1]):  # redirects into files outside the worktree
            if w in (">", ">>", ">|") or (w == "tee" and i == 0):
                target = _resolve(cwd, seg[i + 1]) if not seg[i + 1].startswith("-") else None
                if target and not _inside(target, writes) and not _temp_ok(target):
                    return f"it writes to {target}, outside the run's worktree"
        words = _strip_prefix(seg)
        if not words:
            continue
        if words[0] == "cd" and len(words) == 2:
            cwd = _resolve(cwd, words[1])
            continue
        joined = " ".join([Path(words[0]).name] + words[1:])
        for pattern, why in DESTRUCTIVE:
            if re.search(pattern, joined):
                return f"`{joined[:80]}` {why}"
        tool = Path(words[0]).name
        args = [a for a in words[1:] if not a.startswith("-")]
        if tool in ("rm", "rmdir", "unlink", "shred") or words[:2] == ["git", "rm"]:
            targets = args[1:] if words[:2] == ["git", "rm"] else args
            for t in targets:
                path = _resolve(cwd, t.split("*")[0] or ".")
                if not _inside(path, writes) and not _temp_ok(path):
                    return f"it deletes {path}, outside the run's worktree"
                if any(path == Path(os.path.normpath(r)) or path in Path(os.path.normpath(r)).parents for r in writes):
                    return f"it deletes the whole worktree ({path})"
        if tool in ("mv", "cp", "rsync", "ln", "install") and args:
            dest = _resolve(cwd, args[-1])
            if not _inside(dest, writes) and not _temp_ok(dest):
                return f"it writes to {dest}, outside the run's worktree"
            if tool == "mv":
                for src in args[:-1]:
                    if not _inside(_resolve(cwd, src), writes):
                        return f"it moves {src} out of a folder the run may not change"
    return ""


def patch_paths(patch: str) -> list[str]:
    """Paths an apply_patch body touches (Codex sends file edits this way)."""
    out = []
    for line in patch.splitlines():
        m = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", line) or re.match(r"\*\*\* Move to: (.+?)\s*$", line)
        if m:
            out.append(m.group(1))
    return out


def check(tool: str, tool_input: dict, cwd: Path, config: dict) -> str:
    """Why this tool call is denied, or '' to allow it."""
    writes, reads = config.get("write_roots", []), config.get("read_roots", [])
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool == "Bash" or tool == "shell":
        command = tool_input.get("command")
        if isinstance(command, list):
            command = " ".join(shlex.quote(str(c)) for c in command)
        return bash_reason(command or "", cwd, config) if isinstance(command, str) else "no command given"
    if tool == "apply_patch":
        patch = tool_input.get("command") or tool_input.get("patch") or tool_input.get("input") or ""
        for p in patch_paths(patch if isinstance(patch, str) else ""):
            if not _inside(_resolve(cwd, p), writes):
                return f"the patch changes {p}, outside the run's worktree"
        return ""
    if tool in WRITE_TOOLS:
        target = tool_input.get(WRITE_TOOLS[tool])
        if not isinstance(target, str) or not _inside(_resolve(cwd, target), writes):
            return f"{tool} on {target} is outside the run's worktree"
        return ""
    if tool in READ_TOOLS:
        target = tool_input.get(READ_TOOLS[tool]) or "."
        if not isinstance(target, str) or not _inside(_resolve(cwd, target), reads + writes):
            return f"{tool} on {target} is outside the folders this step may read"
        return ""
    if tool in config.get("deny_tools", []):
        return f"{tool} is not available in this step"
    return ""


def log(config: dict, entry: dict) -> None:
    path = config.get("log")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), "step": config.get("step"), **entry}) + "\n")
    except OSError:
        pass


def decide(event: dict, config: dict, source: str) -> str:
    cwd = Path(event.get("cwd") or os.getcwd())
    tool = str(event.get("tool_name") or "")
    reason = check(tool, event.get("tool_input") or {}, cwd, config)
    log(config, {"source": source, "tool": tool, "decision": "deny" if reason else "allow", "reason": reason})
    return reason


def deny_output(reason: str) -> dict:
    # Codex appends ". Command: ..." after the reason, so no trailing period.
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": f"creative-pipeline guard: {reason}".rstrip(".")}}


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0  # not a hook event we understand
    if not isinstance(event, dict) or event.get("hook_event_name", "PreToolUse") != "PreToolUse":
        return 0
    try:
        found = find_config(Path(event.get("cwd") or os.getcwd()))
        if not found:
            return 0
        reason = decide(event, found[1], "hook")
    except Exception as e:  # fail closed: see the module docstring
        reason = f"guard error ({type(e).__name__}: {e}); the call was blocked to be safe"
    if reason:
        print(json.dumps(deny_output(reason)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
