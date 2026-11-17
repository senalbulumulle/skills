"""roblox-forge tool logic: offline checks and scaffolding for Rojo-based Roblox projects.

Standard library only, so every function is testable without the MCP SDK. server.py exposes these
as MCP tools. Results are compact dicts: "ok", then findings, then short notes.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NEW_PROJECT = REPO / "skills" / "roblox-scripting" / "scripts" / "new_project.py"
MAX_FINDINGS = 50
SKIP_DIRS = {".git", "node_modules", "Packages", "ServerPackages", "DevPackages"}

# Where Roblox runs scripts (Rojo builds Scripts with the Legacy run context).
SERVER_RUNS_IN = {"Workspace", "ServerScriptService"}
CLIENT_RUNS_IN = {"ReplicatedFirst", "StarterGui", "StarterPack"}
CLIENT_RUNS_IN_STARTER_PLAYER = {"StarterPlayerScripts", "StarterCharacterScripts"}

SCRIPT_RE = re.compile(r"^(?P<stem>.+?)(?P<kind>\.server|\.client)?\.(?:luau|lua)$")
INIT_NAMES = {f"init{kind}.{ext}" for kind in ("", ".server", ".client") for ext in ("luau", "lua")}


def _load_new_project():
    spec = importlib.util.spec_from_file_location("new_project", NEW_PROJECT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capped(items: list) -> tuple[list, int]:
    return items[:MAX_FINDINGS], max(0, len(items) - MAX_FINDINGS)


# ---------------------------------------------------------------------------------------------
def create_project(path: str, name: str | None = None) -> dict:
    """Scaffold a Rojo project from the roblox-scripting template."""
    dest = Path(path).expanduser()
    project_name = name or dest.resolve().name
    try:
        files = _load_new_project().create(dest, project_name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": str(dest.resolve()), "name": project_name, "files": files,
            "next": "rojo serve (then connect from the Rojo plugin in Studio)"}


# ---------------------------------------------------------------------------------------------
def _script_kind(filename: str) -> str | None:
    m = SCRIPT_RE.match(filename)
    if not m:
        return None
    return {".server": "server", ".client": "client"}.get(m.group("kind") or "", "module")


def _runs_here(kind: str, ancestry: list[str]) -> bool:
    top = ancestry[0] if ancestry else ""
    if kind == "server":
        return top in SERVER_RUNS_IN
    if kind == "client":
        return top in CLIENT_RUNS_IN or (top == "StarterPlayer" and len(ancestry) > 1
                                         and ancestry[1] in CLIENT_RUNS_IN_STARTER_PLAYER)
    return True


def _scan_dir(directory: Path, ancestry: list[str], root: Path, problems: list, warnings: list, counts: dict,
              check_location: bool):
    entries = sorted(p for p in directory.iterdir() if p.name not in SKIP_DIRS and not p.name.startswith("."))
    inits = [p.name for p in entries if p.is_file() and p.name in INIT_NAMES]
    if len(inits) > 1:
        problems.append(f"{directory.relative_to(root)}: more than one init script ({', '.join(inits)})")
    instance_names: dict[str, list[str]] = {}
    for entry in entries:
        rel = str(entry.relative_to(root))
        if entry.is_dir():
            instance_names.setdefault(entry.name, []).append(rel)
            _scan_dir(entry, ancestry + [entry.name], root, problems, warnings, counts, check_location)
            continue
        kind = _script_kind(entry.name)
        if kind is None:
            continue
        counts[kind] += 1
        if entry.name not in INIT_NAMES:
            instance_names.setdefault(SCRIPT_RE.match(entry.name).group("stem"), []).append(rel)
        if check_location and not _runs_here(kind, ancestry):
            where = ".".join(ancestry) or "(root)"
            label = "Script" if kind == "server" else "LocalScript"
            warnings.append(f"{rel}: {label} mapped to {where} will not run there")
    for name, paths in instance_names.items():
        if len(paths) > 1:
            warnings.append(f"duplicate instance name '{name}' from: {', '.join(paths)}")


def _walk_tree(node: dict, ancestry: list[str], base: Path, root: Path, is_datamodel: bool,
               problems: list, warnings: list, counts: dict):
    if "$path" in node:
        target = (base / node["$path"]).resolve()
        if not target.exists():
            problems.append(f"{'.'.join(ancestry) or 'tree'}: $path '{node['$path']}' does not exist")
        elif target.is_dir():
            _scan_dir(target, ancestry, root, problems, warnings, counts, is_datamodel)
        else:
            kind = _script_kind(target.name)
            if kind:
                counts[kind] += 1
                if is_datamodel and not _runs_here(kind, ancestry[:-1]):
                    warnings.append(f"{target.relative_to(root)}: {kind} script mapped to "
                                    f"{'.'.join(ancestry)} will not run there")
    for key, child in node.items():
        if key.startswith("$"):
            continue
        if not isinstance(child, dict):
            problems.append(f"{'.'.join(ancestry + [key])}: must be an object")
            continue
        _walk_tree(child, ancestry + [key], base, root, is_datamodel, problems, warnings, counts)


def check_project(path: str, build: bool = True) -> dict:
    """Validate a Rojo project: JSON, $path targets, init conflicts, scripts mapped where they won't run,
    duplicate names, and (if Rojo is installed and build is true) a real `rojo build`."""
    p = Path(path).expanduser().resolve()
    project_file = p / "default.project.json" if p.is_dir() else p
    if not project_file.is_file():
        return {"ok": False, "problems": [f"project file not found: {project_file}"]}
    try:
        project = json.loads(project_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"ok": False, "problems": [f"{project_file.name}: invalid JSON: {e}"]}

    problems: list[str] = []
    warnings: list[str] = []
    counts = {"server": 0, "client": 0, "module": 0}
    if not isinstance(project, dict) or "name" not in project or not isinstance(project.get("tree"), dict):
        problems.append("project file needs a 'name' and a 'tree' object")
    else:
        tree = project["tree"]
        is_datamodel = tree.get("$className") == "DataModel"
        _walk_tree(tree, [], project_file.parent, project_file.parent, is_datamodel, problems, warnings, counts)
        if not is_datamodel:
            warnings.append("tree is not a DataModel (library or model project); run-location checks skipped")

    build_result = "skipped"
    if build and not problems:
        rojo = shutil.which("rojo")
        if rojo is None:
            build_result = "rojo not installed"
        else:
            with tempfile.TemporaryDirectory() as tmp:
                suffix = ".rbxlx" if project.get("tree", {}).get("$className") == "DataModel" else ".rbxmx"
                out = Path(tmp) / f"build{suffix}"
                run = subprocess.run([rojo, "build", str(project_file), "-o", str(out)],
                                     capture_output=True, text=True, timeout=120)
                if run.returncode == 0:
                    build_result = "ok"
                else:
                    build_result = "failed"
                    problems.append(f"rojo build failed: {(run.stderr or run.stdout).strip()[-500:]}")

    shown, hidden = _capped(warnings)
    return {"ok": not problems, "project": str(project_file), "scripts": counts, "rojo_build": build_result,
            "problems": problems, "warnings": shown, "more_warnings": hidden}


# ---------------------------------------------------------------------------------------------
HANDLER_RE = re.compile(r"\.OnServerEvent\s*:\s*Connect\s*\(|\.OnServerInvoke\s*=")
INVOKE_CLIENT_RE = re.compile(r":\s*InvokeClient\s*\(")
FIRE_SERVER_RE = re.compile(r":\s*FireServer\s*\((?P<args>[^)]*)\)")
TRUSTED_VALUE_RE = re.compile(r"\b(price|cost|damage|amount|reward|coins|cash|money|gems|xp|health|"
                              r"position|cframe|speed|multiplier)\b", re.I)
WRAP_RE = re.compile(r"\.wrap\s*\(")


def audit_remotes(path: str) -> dict:
    """Heuristic scan of Luau sources for remote handlers without a validation wrapper, InvokeClient use,
    and FireServer calls that appear to send values the server should decide."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return {"ok": False, "error": f"not found: {root}"}
    files = [root] if root.is_file() else sorted(
        f for f in root.rglob("*") if f.suffix in (".luau", ".lua") and not (set(f.parts) & SKIP_DIRS))
    findings, handlers, wrapped = [], 0, 0
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(f.relative_to(root)) if root.is_dir() else f.name
        for i, line in enumerate(lines, 1):
            code = line.split("--", 1)[0]
            if HANDLER_RE.search(code):
                handlers += 1
                # The wrapper may start on the same line or the next one.
                if WRAP_RE.search(code) or (i < len(lines) and WRAP_RE.search(lines[i].split("--", 1)[0])):
                    wrapped += 1
                else:
                    findings.append({"severity": "high", "where": f"{rel}:{i}", "code": line.strip()[:160],
                                     "issue": "remote handler without a validation wrapper (RemoteGuard.wrap)"})
            if INVOKE_CLIENT_RE.search(code):
                findings.append({"severity": "medium", "where": f"{rel}:{i}", "code": line.strip()[:160],
                                 "issue": "InvokeClient lets a client stall or break the server; use RemoteEvents"})
            m = FIRE_SERVER_RE.search(code)
            if m and TRUSTED_VALUE_RE.search(m.group("args")):
                findings.append({"severity": "medium", "where": f"{rel}:{i}", "code": line.strip()[:160],
                                 "issue": "client sends a value the server should compute (price, damage, reward, position...)"})
    shown, hidden = _capped(findings)
    return {"ok": not any(f["severity"] == "high" for f in findings), "files_scanned": len(files),
            "handlers": handlers, "wrapped": wrapped, "findings": shown, "more_findings": hidden,
            "note": "Heuristic: a wrapper's presence is checked, not whether its checks are sufficient."}


# ---------------------------------------------------------------------------------------------
def check_odds(outcomes: list[dict], rounded: bool = False) -> dict:
    """Check paid random item odds against Roblox policy: every outcome listed as a percentage, summing
    to exactly 100% (or, if rounded, within rounding error, with a disclaimer shown)."""
    problems: list[str] = []
    if not outcomes:
        return {"ok": False, "problems": ["no outcomes given"]}
    names: set[str] = set()
    total = 0.0
    decimals = 0
    display = []
    for i, o in enumerate(outcomes):
        name = str(o.get("name", "")).strip() if isinstance(o, dict) else ""
        percent = o.get("percent") if isinstance(o, dict) else None
        if not name:
            problems.append(f"outcome {i + 1}: missing name")
        elif name in names:
            problems.append(f"duplicate outcome name '{name}'")
        names.add(name)
        if isinstance(percent, bool) or not isinstance(percent, (int, float)) or not 0 < percent <= 100:
            problems.append(f"'{name or i + 1}': percent must be a number above 0 and at most 100")
            continue
        total += percent
        text = repr(float(percent)).rstrip("0").rstrip(".")
        decimals = max(decimals, len(text.split(".")[1]) if "." in text else 0)
        display.append(f"{name}: {text}%")
    total = round(total, 10)
    disclaimer = False
    if abs(total - 100) > 1e-9:
        tolerance = 0.5 * 10 ** (-decimals) * len(outcomes)
        if rounded and abs(total - 100) <= tolerance:
            disclaimer = True
        else:
            problems.append(f"percentages sum to {total}%, not 100%"
                            + ("" if rounded else " (pass rounded=true if they are rounded values)"))
    result = {"ok": not problems, "total_percent": total, "display": display, "problems": problems,
              "disclaimer_required": disclaimer}
    if disclaimer:
        result["disclaimer"] = ("Probabilities are rounded; total of displayed individual probabilities "
                                "may not equal 100%.")
    result["also_required"] = ("Show all outcomes and odds before purchase; long lists may use a clearly "
                               "labelled Info/Details button; hide offers when ArePaidRandomItemsRestricted.")
    return result


# ---------------------------------------------------------------------------------------------
def datastore_budget(players: int, autosave_seconds: float = 60, joins_per_minute: float | None = None,
                     extra_reads_per_minute: float = 0, extra_writes_per_minute: float = 0) -> dict:
    """Estimate one server's standard DataStore usage per minute against the documented default
    per-server budget (60 + players x 40 per minute for reads and for writes). Assumes PlayerData-style
    saves: every load, autosave, and release is one UpdateAsync, which counts as a read and a write."""
    if players < 1 or autosave_seconds <= 0:
        return {"ok": False, "error": "players must be at least 1 and autosave_seconds above 0"}
    joins = players / 5 if joins_per_minute is None else joins_per_minute  # rough churn default
    budget = 60 + players * 40
    update_async = players * 60 / autosave_seconds + joins * 2  # autosaves + (load on join, release on leave)
    reads = update_async + extra_reads_per_minute
    writes = update_async + extra_writes_per_minute
    usage = {"reads": round(reads / budget * 100, 1), "writes": round(writes / budget * 100, 1)}
    worst = max(usage.values())
    status = "over budget" if worst > 100 else "tight" if worst > 50 else "comfortable"
    return {"ok": worst <= 100, "status": status, "budget_per_minute": budget,
            "estimated_reads_per_minute": round(reads, 1), "estimated_writes_per_minute": round(writes, 1),
            "usage_percent": usage,
            "source": "Roblox docs, data store error codes and limits (server defaults); verify current limits"}


# ---------------------------------------------------------------------------------------------
def luau_check(paths: list[str], mode: str = "strict") -> dict:
    """Type-check and lint Luau files with luau-analyze. Engine scripts that use Roblox globals need
    Roblox type definitions, so run this on pure modules or expect unknown-global reports."""
    exe = shutil.which("luau-analyze")
    if exe is None:
        return {"ok": False, "error": "luau-analyze not installed (https://github.com/luau-lang/luau releases)"}
    if mode not in ("strict", "nonstrict"):
        return {"ok": False, "error": "mode must be 'strict' or 'nonstrict'"}
    files = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix in (".luau", ".lua") and not (set(f.parts) & SKIP_DIRS))
        elif p.is_file():
            files.append(p)
        else:
            return {"ok": False, "error": f"not found: {p}"}
    if not files:
        return {"ok": False, "error": "no .luau or .lua files found"}
    run = subprocess.run([exe, f"--mode={mode}", "--formatter=plain", *map(str, files)],
                         capture_output=True, text=True, timeout=120)
    issues = [line for line in (run.stdout + run.stderr).splitlines() if line.strip()]
    shown, hidden = _capped(issues)
    return {"ok": run.returncode == 0 and not issues, "files": len(files), "issues": shown, "more_issues": hidden}
