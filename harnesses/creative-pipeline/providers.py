"""Model adapters: Gemini over its HTTP API, Claude Code and Codex as headless CLI sessions, and a replay mock.

Every adapter returns a Result whose usage is in one shape for every provider (see usage()). Each adapter has:
  generate() / run_cli()  the step's main call: an API turn, or one CLI session turn in the worktree (or a
                          resumed turn of the same session)
  fix()                   a cheap retry: a fresh, tool-less call that sees only the gate's violations and the
                          lines around them, and answers with exact-text edits (see prompts/fix.md)
  plain()                 (Claude Code and the mock) one ordinary session with the user's own settings, the
                          baseline for `pipeline.py bench`
The mock reads a replay file and acts out the same calls, including tool calls through the guard.
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import guard

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
PLAIN_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]


class ProviderError(Exception):
    """A provider call failed in a way the user can act on."""


@dataclass
class Result:
    text: str
    session: Optional[str] = None
    usage: dict = field(default_factory=dict)
    tool_events: int = 0
    denied: list = field(default_factory=list)
    history: list = field(default_factory=list)
    seconds: float = 0.0


# ---------------------------------------------------------------- usage

def usage(fresh: int = 0, cached: int = 0, output: int = 0, cost: Optional[float] = None) -> dict:
    """Token usage in one shape for every provider.

    fresh_input: input tokens billed at the full rate (for Claude, cache writes count here)
    cached_input: input tokens read from a prompt cache
    output: output tokens, including reasoning or thinking tokens
    cost_usd: only when the provider reports it (Claude Code does)
    """
    out = {"fresh_input": max(int(fresh), 0), "cached_input": max(int(cached), 0), "output": max(int(output), 0)}
    if cost is not None:
        out["cost_usd"] = float(cost)
    return out


def claude_usage(data: dict) -> dict:
    u = data.get("usage") or {}
    return usage(u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0),
                 u.get("output_tokens", 0), data.get("total_cost_usd"))


def codex_usage(u: dict) -> dict:
    cached = u.get("cached_input_tokens", 0)  # OpenAI counts cached tokens inside input_tokens
    return usage(u.get("input_tokens", 0) - cached, cached, u.get("output_tokens", 0))


def gemini_usage(m: dict) -> dict:
    cached = m.get("cachedContentTokenCount", 0)  # included in promptTokenCount
    return usage(m.get("promptTokenCount", 0) - cached, cached, m.get("candidatesTokenCount", 0) + m.get("thoughtsTokenCount", 0))


def total_tokens(u: dict) -> int:
    return u.get("fresh_input", 0) + u.get("cached_input", 0) + u.get("output", 0)


def add_usage(total: dict, more: dict) -> dict:
    for k, v in (more or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total[k] = total.get(k, 0) + v
            if isinstance(total[k], float):
                total[k] = round(total[k], 6)  # sums of float costs would otherwise drift (0.21 + 0.02)
    return total


# ---------------------------------------------------------------- Gemini (API)

class Gemini:
    def __init__(self, model: str, api_key: str, timeout: float = 300, base: str = GEMINI_BASE):
        if not model:
            raise ProviderError("set GEMINI_MODEL (or --gemini-model) to the Gemini model id to use")
        if not api_key:
            raise ProviderError("set GEMINI_API_KEY to call Gemini, or use --mock to run without models")
        self.model, self.key, self.timeout, self.base = model, api_key, timeout, base

    def _post(self, method: str, body: dict, model: Optional[str] = None) -> dict:
        req = urllib.request.Request(f"{self.base}/models/{model or self.model}:{method}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": self.key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode()).get("error", {}).get("message", "")
            except ValueError:
                detail = ""
            raise ProviderError(f"Gemini {method} failed with HTTP {e.code}: {detail or e.reason}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise ProviderError(f"Gemini {method} failed: {e}") from None

    @staticmethod
    def declarations(tools: list) -> list:
        return [{"functionDeclarations": [{k: t[k] for k in ("name", "description", "parameters") if k in t}
                                          for t in tools]}] if tools else []

    def body(self, system: str, contents: list, temperature: float, tools: list, json_mode: bool) -> dict:
        body = {"contents": contents, "generationConfig": {"temperature": temperature}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = self.declarations(tools)
        elif json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        return body

    def count_tokens(self, system: str, prompt: str, tools: list) -> int:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        request = {"model": f"models/{self.model}", **self.body(system, contents, 1.0, tools, False)}
        request.pop("generationConfig", None)
        return int(self._post("countTokens", {"generateContentRequest": request}).get("totalTokens", 0))

    def generate(self, system: str, prompt: str, temperature: float, tools: list,
                 run_tool: Callable[[str, dict], dict], max_rounds: int = 4, history: Optional[list] = None,
                 json_mode: bool = False, model: Optional[str] = None) -> Result:
        start = time.monotonic()
        contents = list(history or []) + [{"role": "user", "parts": [{"text": prompt}]}]
        used: dict = {}
        events = 0
        for round_no in range(max_rounds + 1):
            body = self.body(system, contents, temperature, tools, json_mode)
            if round_no == max_rounds and tools:
                body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
            resp = self._post("generateContent", body, model)
            add_usage(used, gemini_usage(resp.get("usageMetadata", {})))
            candidates = resp.get("candidates") or []
            if not candidates or "content" not in candidates[0]:
                reason = (resp.get("promptFeedback") or {}).get("blockReason") or (candidates[0].get("finishReason") if candidates else "no candidates")
                raise ProviderError(f"Gemini returned no content ({reason})")
            content = candidates[0]["content"]
            contents.append(content)  # kept whole, so thought signatures go back unchanged
            calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
            if not calls:
                text = "".join(p.get("text", "") for p in content.get("parts", []) if not p.get("thought"))
                return Result(text, usage=used, tool_events=events, history=contents, seconds=time.monotonic() - start)
            events += len(calls)
            contents.append({"role": "user", "parts": [
                {"functionResponse": {"name": c.get("name", ""), "response": run_tool(c.get("name", ""), c.get("args") or {})}}
                for c in calls]})
        raise ProviderError("Gemini kept calling tools past the round limit")

    def fix(self, step: dict, prompt: str, system: str, cwd: Path, run_dir: Path, attempt: int,
            model: Optional[str] = None) -> Result:
        """A fresh call with no tools and no history: only the fix prompt."""
        return self.generate(system, prompt, step.get("temperature", 1.0), [], lambda n, a: {}, 0, None,
                             json_mode=True, model=model)


# ---------------------------------------------------------------- CLI sessions

def _run(argv: list, cwd: Path, stdin: str, log: Path, timeout: float) -> tuple[Optional[int], str]:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(argv, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ProviderError(f"{argv[0]} is not installed or not on PATH") from None
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        log.write_text(out, encoding="utf-8")
        return None, out
    with log.open("a", encoding="utf-8") as f:
        f.write(f"$ {' '.join(argv[:2])} ... (exit {proc.returncode})\n{proc.stdout}\n{proc.stderr}\n")
    return proc.returncode, proc.stdout


def guard_command() -> str:
    return f"python3 {json.dumps(str(Path(guard.__file__).resolve()))}"


def guard_settings() -> str:
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": guard_command(),
                                                                             "timeout": 30}]}]}})


class ClaudeCLI:
    """Claude Code in print mode. The guard runs as a PreToolUse hook passed with --settings."""

    def __init__(self, model: Optional[str] = None, timeout: float = 3600):
        self.model, self.timeout = model, timeout

    def argv(self, system: str, tools: list, mcp_path: Path, session: str, resume: bool, add_dirs: list,
             model: Optional[str] = None) -> list:
        argv = ["claude", "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
                "--settings", guard_settings(), "--strict-mcp-config", "--mcp-config", str(mcp_path),
                "--append-system-prompt", system]
        argv += ["--resume", session] if resume else ["--session-id", session]
        argv += ["--model", model or self.model] if (model or self.model) else []
        for d in add_dirs:
            argv += ["--add-dir", str(d)]
        # Variadic flags last, and the prompt goes on stdin, so they can't swallow a positional argument.
        argv += ["--tools", *tools, "--allowedTools", *tools] if tools else ["--tools", ""]
        return argv

    def plain_argv(self, model: Optional[str] = None) -> list:
        """An ordinary session: the user's own settings, MCP servers, and tools, plus the guard for safety."""
        argv = ["claude", "-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--settings", guard_settings()]
        argv += ["--model", model or self.model] if (model or self.model) else []
        return argv + ["--allowedTools", *PLAIN_TOOLS]

    def _call(self, argv: list, prompt: str, cwd: Path, log: Path, label: str) -> dict:
        code, out = _run(argv, cwd, prompt, log, self.timeout)
        if code is None:
            raise ProviderError(f"claude timed out after {self.timeout:.0f}s in {label}")
        try:
            data = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
        except ValueError:
            data = {}
        if code != 0 or data.get("is_error"):
            raise ProviderError(f"claude failed in {label} (exit {code}): {str(data.get('result') or out)[-400:]}")
        return data

    def _mcp(self, run_dir: Path, name: str, servers: dict) -> Path:
        path = run_dir / f"{name}.mcp.json"
        path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
        return path

    def run_cli(self, step: dict, prompt: str, system: str, cwd: Path, run_dir: Path, session: Optional[str],
                attempt: int, add_dirs: list) -> Result:
        start = time.monotonic()
        resume = session is not None
        session = session or str(uuid.uuid4())
        argv = self.argv(system, step.get("cli_tools", []), self._mcp(run_dir, step["id"], step.get("mcp", {})),
                         session, resume, add_dirs)
        data = self._call(argv, prompt, cwd, run_dir / "logs" / f"{step['id']}.log", f"step {step['id']}")
        return Result(data.get("result", ""), session=data.get("session_id") or session, usage=claude_usage(data),
                      tool_events=int(data.get("num_turns") or 0), seconds=time.monotonic() - start)

    def fix(self, step: dict, prompt: str, system: str, cwd: Path, run_dir: Path, attempt: int,
            model: Optional[str] = None) -> Result:
        start = time.monotonic()
        argv = self.argv(system, [], self._mcp(run_dir, f"{step['id']}.fix", {}), str(uuid.uuid4()), False, [], model)
        data = self._call(argv, prompt, cwd, run_dir / "logs" / f"{step['id']}.fix.log", f"step {step['id']} (fix)")
        return Result(data.get("result", ""), usage=claude_usage(data), seconds=time.monotonic() - start)

    def plain(self, prompt: str, cwd: Path, log: Path, model: Optional[str] = None) -> Result:
        start = time.monotonic()
        data = self._call(self.plain_argv(model), prompt, cwd, log, "the baseline session")
        return Result(data.get("result", ""), session=data.get("session_id"), usage=claude_usage(data),
                      tool_events=int(data.get("num_turns") or 0), seconds=time.monotonic() - start)


class CodexCLI:
    """codex exec with the guard as an inline PreToolUse hook (-c hooks...). Codex runs only trusted hooks."""

    def __init__(self, model: Optional[str] = None, timeout: float = 3600, bypass_hook_trust: bool = False):
        self.model, self.timeout, self.bypass = model, timeout, bypass_hook_trust

    def hook_config(self) -> str:
        command = json.dumps(guard_command())
        return f'hooks.PreToolUse=[{{matcher="Bash|apply_patch", hooks=[{{type="command", command={command}, timeout=30}}]}}]'

    def argv(self, step: dict, cwd: Path, last: Path, schema: Optional[Path], session: Optional[str],
             sandbox: str = "workspace-write", effort: Optional[str] = None, model: Optional[str] = None,
             ephemeral: bool = False) -> list:
        argv = ["codex", "exec"] + (["resume", session] if session else ["-C", str(cwd)])
        argv += ["-c", self.hook_config(), "-c", f'sandbox_mode="{sandbox}"',
                 "-c", f'model_reasoning_effort="{effort or step.get("effort", "high")}"',
                 "--json", "-o", str(last), "--skip-git-repo-check"]
        argv += ["-m", model or self.model] if (model or self.model) else []
        argv += ["--output-schema", str(schema)] if schema else []
        argv += ["--ephemeral"] if ephemeral else []
        argv += ["--dangerously-bypass-hook-trust"] if self.bypass else []
        return argv + ["-"]  # prompt on stdin

    def _exec(self, argv: list, prompt: str, cwd: Path, log: Path, last: Path, label: str,
              session: Optional[str]) -> Result:
        start = time.monotonic()
        code, out = _run(argv, cwd, prompt, log, self.timeout)
        if code is None:
            raise ProviderError(f"codex timed out after {self.timeout:.0f}s in {label}")
        thread, used, events = session, {}, 0
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "thread.started":
                thread = ev.get("thread_id") or thread
            elif ev.get("type") == "turn.completed":
                add_usage(used, codex_usage(ev.get("usage") or {}))
            elif ev.get("type") == "item.completed" and (ev.get("item") or {}).get("type") in (
                    "command_execution", "file_change", "mcp_tool_call"):
                events += 1
        if code != 0:
            raise ProviderError(f"codex failed in {label} (exit {code}); see {log}")
        text = last.read_text(encoding="utf-8") if last.is_file() else ""
        return Result(text, session=thread, usage=used or usage(), tool_events=events, seconds=time.monotonic() - start)

    @staticmethod
    def _schema_file(run_dir: Path, name: str, schema: Optional[dict]) -> Optional[Path]:
        if not schema:
            return None
        path = run_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema), encoding="utf-8")
        return path

    def run_cli(self, step: dict, prompt: str, system: str, cwd: Path, run_dir: Path, session: Optional[str],
                attempt: int, add_dirs: list) -> Result:
        last = run_dir / "logs" / f"{step['id']}.{attempt}.last.txt"
        last.parent.mkdir(parents=True, exist_ok=True)
        argv = self.argv(step, cwd, last, self._schema_file(run_dir, step["id"], step.get("schema_doc")), session)
        return self._exec(argv, f"{system}\n\n{prompt}" if system else prompt, cwd,
                          run_dir / "logs" / f"{step['id']}.log", last, f"step {step['id']}", session)

    def fix(self, step: dict, prompt: str, system: str, cwd: Path, run_dir: Path, attempt: int,
            model: Optional[str] = None) -> Result:
        """A fresh, read-only, ephemeral turn that answers in the fix schema."""
        last = run_dir / "logs" / f"{step['id']}.{attempt}.fix.last.txt"
        last.parent.mkdir(parents=True, exist_ok=True)
        argv = self.argv(step, cwd, last, self._schema_file(run_dir, "fix", step.get("fix_schema_doc")), None,
                         sandbox="read-only", effort=step.get("fix_effort", "low"), model=model, ephemeral=True)
        return self._exec(argv, f"{system}\n\n{prompt}" if system else prompt, cwd,
                          run_dir / "logs" / f"{step['id']}.fix.log", last, f"step {step['id']} (fix)", None)


# ---------------------------------------------------------------- replay mock

class Mock:
    """Acts out a replay file: {step_id: [attempt, ...], "<step_id>.fix": [fix, ...], "baseline": [entry]}.

    An entry has optional tool_calls, files, text, and usage (in the usage() shape).
    API steps: each tool call goes through run_tool (so the guard and tool filter apply), then text is returned.
    CLI steps: each tool call and each file write is checked by the guard as the real hook would, and only
    allowed writes land in the worktree. Fix entries return their text, which should be a fix-schema answer.
    Missing entries reuse the list's last entry.
    """

    def __init__(self, replay: dict):
        self.replay = replay
        self.calls: list = []
        self.fix_count: dict = {}

    def _entry(self, key: str, n: int) -> dict:
        entries = self.replay.get(key)
        if not entries:
            raise ProviderError(f"the replay has no entries for {key!r}")
        return entries[min(n, len(entries) - 1)]

    def count_tokens(self, system: str, prompt: str, tools: list) -> int:
        raise ProviderError("the mock has no exact token counts")

    def generate(self, system: str, prompt: str, temperature: float, tools: list,
                 run_tool: Callable[[str, dict], dict], max_rounds: int = 4, history: Optional[list] = None,
                 json_mode: bool = False, step_id: str = "", attempt: int = 0) -> Result:
        entry = self._entry(step_id, attempt)
        self.calls.append({"step": step_id, "attempt": attempt, "kind": "generate", "tools": [t["name"] for t in tools],
                           "temperature": temperature, "prompt": prompt, "system": system})
        results = [run_tool(c["name"], c.get("args", {})) for c in entry.get("tool_calls", [])[:max_rounds]]
        used = entry.get("usage") or usage(len(system + prompt) // 4, 0, len(entry.get("text", "")) // 4)
        return Result(entry.get("text", ""), usage=dict(used), tool_events=len(results),
                      history=(history or []) + [{"role": "user", "parts": [{"text": prompt}]},
                                                 {"role": "model", "parts": [{"text": entry.get("text", "")}]}])

    def _act(self, entry: dict, cwd: Path) -> list:
        found = guard.find_config(cwd)
        config = found[1] if found else {}
        denied = []
        calls = list(entry.get("tool_calls", []))
        calls += [{"tool_name": "Write", "tool_input": {"file_path": str(cwd / rel), "content": text}}
                  for rel, text in entry.get("files", {}).items()]
        for call in calls:
            event = {"hook_event_name": "PreToolUse", "cwd": str(cwd), **call}
            reason = guard.decide(event, config, "mock") if config else ""
            if reason:
                denied.append({"tool": call["tool_name"], "reason": reason})
            elif call["tool_name"] == "Write":
                target = Path(call["tool_input"]["file_path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(call["tool_input"]["content"], encoding="utf-8")
        return denied

    def run_cli(self, step: dict, prompt: str, system: str, cwd: Path, run_dir: Path, session: Optional[str],
                attempt: int, add_dirs: list) -> Result:
        entry = self._entry(step["id"], attempt)
        self.calls.append({"step": step["id"], "attempt": attempt, "kind": "run_cli", "session": session,
                           "prompt": prompt, "system": system, "tools": step.get("cli_tools")})
        denied = self._act(entry, cwd)
        return Result(entry.get("text", ""), session=session or f"mock-{step['id']}", usage=dict(entry.get("usage") or usage()),
                      tool_events=len(entry.get("tool_calls", [])) + len(entry.get("files", {})), denied=denied)

    def fix(self, step: dict, prompt: str, system: str, cwd: Path, run_dir: Path, attempt: int,
            model: Optional[str] = None) -> Result:
        n = self.fix_count.get(step["id"], 0)
        self.fix_count[step["id"]] = n + 1
        entry = self._entry(f"{step['id']}.fix", n)
        self.calls.append({"step": step["id"], "attempt": attempt, "kind": "fix", "model": model, "prompt": prompt})
        return Result(entry.get("text", ""), usage=dict(entry.get("usage") or usage(len(prompt) // 4, 0, len(entry.get("text", "")) // 4)))

    def plain(self, prompt: str, cwd: Path, log: Path, model: Optional[str] = None) -> Result:
        entry = self._entry("baseline", 0)
        self.calls.append({"step": "baseline", "kind": "plain", "prompt": prompt, "model": model})
        denied = self._act(entry, cwd)
        return Result(entry.get("text", ""), session="mock-baseline", usage=dict(entry.get("usage") or usage()), denied=denied)


def for_step(step: dict, args, mock: Optional[Mock]):
    if mock:
        return mock
    if step["provider"] == "gemini":
        return Gemini(args.gemini_model or os.environ.get("GEMINI_MODEL", ""), os.environ.get("GEMINI_API_KEY", ""),
                      timeout=min(args.timeout, 600))
    if step["provider"] == "claude":
        return ClaudeCLI(args.claude_model, args.timeout)
    if step["provider"] == "codex":
        return CodexCLI(args.codex_model, args.timeout, args.bypass_hook_trust)
    raise ProviderError(f"unknown provider {step['provider']!r} in steps.json")
