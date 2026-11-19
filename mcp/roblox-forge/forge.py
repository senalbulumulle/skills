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


# ---------------------------------------------------------------------------------------------
# Shared Luau text handling for map_remotes and audit_feel. Blanking keeps every character's position,
# so offsets and line numbers found in one version of the text are valid in the other.
LUA_TOKEN_RE = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`|--\[(=*)\[.*?\]\1\]|--[^\n]*'
                          r'|\[(=*)\[.*?\]\2\]', re.S)


def _blank_lua(text: str, strings: bool) -> str:
    """Blank comments (and string contents too when strings is true), keeping newlines and length."""
    def repl(m: re.Match) -> str:
        s = m.group(0)
        if s.startswith("--"):
            return re.sub(r"[^\n]", " ", s)
        if strings:
            return s[0] + re.sub(r"[^\n]", " ", s[1:-1]) + s[-1]
        return s
    return LUA_TOKEN_RE.sub(repl, text)


def _luau_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(f for f in root.rglob("*") if f.suffix in (".luau", ".lua") and f.is_file()
                  and not (set(f.relative_to(root).parts) & SKIP_DIRS))


def _rel(f: Path, root: Path) -> str:
    return str(f.relative_to(root)) if root.is_dir() else f.name


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# ---------------------------------------------------------------------------------------------
REMOTE_CLASSES = {"RemoteEvent": "event", "UnreliableRemoteEvent": "event", "RemoteFunction": "function"}
# (pattern, kind it needs, direction). Fires name the method; handlers name the event or callback.
REMOTE_USES = (
    (re.compile(r"[.:]\s*(FireServer)\s*\("), "event", "to_server", "fire"),
    (re.compile(r"[.:]\s*(InvokeServer)\s*\("), "function", "to_server", "fire"),
    (re.compile(r"[.:]\s*(FireClient|FireAllClients)\s*\("), "event", "to_client", "fire"),
    (re.compile(r"[.:]\s*(InvokeClient)\s*\("), "function", "to_client", "fire"),
    (re.compile(r"\.\s*(OnServerEvent)\b"), "event", "to_server", "handle"),
    (re.compile(r"\.\s*(OnServerInvoke)\b"), "function", "to_server", "handle"),
    (re.compile(r"\.\s*(OnClientEvent)\b"), "event", "to_client", "handle"),
    (re.compile(r"\.\s*(OnClientInvoke)\b"), "function", "to_client", "handle"),
)
# The remote's name at the end of an expression: :WaitForChild("X"), ["X"], .X, or a local alias.
NAME_AT_END = (
    re.compile(r"""[.:]\s*(?:WaitForChild|FindFirstChild)\s*\(\s*["']([^"']+)["']\s*(?:,[^()]*)?\)$"""),
    re.compile(r"""\[\s*["']([^"']+)["']\s*\]$"""),
    re.compile(r"(?<!\bself)\.\s*([A-Za-z_]\w*)$"),  # self.x is a field holding some remote, not its name
)
ALIAS_RE = re.compile(r"^\s*local\s+([A-Za-z_]\w*)\s*(?::\s*[\w.]+\??\s*)?=\s*(.+?)\s*(?:::\s*[\w.]+\??\s*)?;?\s*$")
INSTANCE_NEW_RE = re.compile(r"""^\s*local\s+([A-Za-z_]\w*)\s*=\s*Instance\.new\(\s*["'](\w+)["']""")
NEW_REMOTE_RE = re.compile(r"""Instance\.new\(\s*["'](?:RemoteEvent|UnreliableRemoteEvent|RemoteFunction)["']""")


def _expr_name(expr: str, aliases: dict[str, str | None]) -> str | None:
    expr = re.sub(r"\s*::\s*[\w.]+\??$", "", expr.rstrip())
    for pattern in NAME_AT_END:
        m = pattern.search(expr)
        if m:
            return m.group(1)
    bare = re.search(r"(?<![\w.:])([A-Za-z_]\w*)$", expr)
    return aliases.get(bare.group(1)) if bare else None


def _declared_in_project(node: object, path: list[str], where: str, out: list) -> None:
    if not isinstance(node, dict):
        return
    cls = node.get("$className")
    if path and cls in REMOTE_CLASSES:
        out.append((path[-1], cls, f"{where}:{'.'.join(path)}"))
    for key, child in node.items():
        if not key.startswith("$"):
            _declared_in_project(child, path + [key], where, out)


def _declared_in_model(node: object, name: str, where: str, out: list) -> None:
    if not isinstance(node, dict):
        return
    cls = node.get("ClassName") or node.get("className")
    if cls in REMOTE_CLASSES:
        out.append((name, cls, where))
    for child in node.get("Children") or node.get("children") or []:
        if isinstance(child, dict):
            _declared_in_model(child, str(child.get("Name") or child.get("name") or ""), where, out)


def map_remotes(path: str) -> dict:
    """Inventory every RemoteEvent and RemoteFunction by name: where it is declared (project or model JSON,
    or Instance.new with a literal Name), fired, and handled. Flags remotes fired with no handler, handlers
    nothing fires, Fire/Invoke used on the wrong class, and names used in code but never declared."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return {"ok": False, "error": f"not found: {root}"}
    declared: list[tuple[str, str, str]] = []
    if root.is_dir():
        for f in sorted(root.glob("*.project.json")) + sorted(
                f for f in root.rglob("*.model.json") if not (set(f.relative_to(root).parts) & SKIP_DIRS)):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if f.name.endswith(".project.json"):
                _declared_in_project(data.get("tree") if isinstance(data, dict) else None, [], f.name, declared)
            else:
                _declared_in_model(data, f.name[:-len(".model.json")], _rel(f, root), declared)

    uses: list[dict] = []
    unresolved, dynamic = [], []
    files = _luau_files(root)
    for f in files:
        try:
            code = _blank_lua(f.read_text(encoding="utf-8"), strings=False)
        except (OSError, UnicodeDecodeError):
            continue
        rel = _rel(f, root)
        lines = code.splitlines()
        # Pass 1: local aliases (a name bound to two different remotes is ambiguous) and created remotes.
        aliases: dict[str, str | None] = {}
        created: dict[str, tuple[str, int]] = {}
        for i, line in enumerate(lines, 1):
            new = INSTANCE_NEW_RE.match(line)
            if new and new.group(2) in REMOTE_CLASSES:
                created[new.group(1)] = (new.group(2), i)
                continue
            if NEW_REMOTE_RE.search(line):  # created inside an expression: its name is set some other way
                dynamic.append(f"{rel}:{i}")
            m = ALIAS_RE.match(line)
            if m:
                name = _expr_name(m.group(2), aliases)
                if name is not None:
                    aliases[m.group(1)] = name if aliases.get(m.group(1), name) == name else None
        for var, (cls, line_no) in created.items():
            named = re.search(rf"\b{re.escape(var)}\.Name\s*=\s*[\"']([^\"']+)[\"']", code)
            if named:
                declared.append((named.group(1), cls, f"{rel}:{line_no}"))
                aliases[var] = named.group(1)
            else:
                dynamic.append(f"{rel}:{line_no}")
        # Pass 2: fires and handlers.
        for i, line in enumerate(lines, 1):
            for pattern, kind, direction, role in REMOTE_USES:
                for m in pattern.finditer(line):
                    name = _expr_name(line[:m.start()], aliases)
                    where = f"{rel}:{i}"
                    if name is None:
                        unresolved.append(f"{where} ({m.group(1)})")
                    else:
                        uses.append({"name": name, "kind": kind, "direction": direction, "role": role,
                                     "member": m.group(1), "where": where})

    remotes: dict[str, dict] = {}
    for name, cls, where in declared:
        r = remotes.setdefault(name, {"name": name, "class": cls, "declared": [], "fired": [], "handled": []})
        r["declared"].append(where)
    for u in uses:
        r = remotes.setdefault(u["name"], {"name": u["name"], "class": None, "declared": [], "fired": [],
                                           "handled": []})
        r["fired" if u["role"] == "fire" else "handled"].append(f"{u['where']} ({u['member']})")

    findings = []

    def add(severity: str, name: str, issue: str):
        findings.append({"severity": severity, "remote": name, "issue": issue})

    for name, r in sorted(remotes.items()):
        mine = [u for u in uses if u["name"] == name]
        classes = {REMOTE_CLASSES[c] for _, c, _ in [d for d in declared if d[0] == name]}
        used_kinds = {u["kind"] for u in mine}
        if len(classes) == 1 and used_kinds - classes:
            wrong = sorted({u["member"] for u in mine if u["kind"] not in classes})
            add("high", name, f"declared as {r['class']} but used with {', '.join(wrong)}, which it doesn't have")
        for direction, label in (("to_server", "server"), ("to_client", "client")):
            fired = [u for u in mine if u["direction"] == direction and u["role"] == "fire"]
            handled = [u for u in mine if u["direction"] == direction and u["role"] == "handle"]
            if fired and not handled:
                # Only a declared name is surely a remote; an undeclared one may be a misread variable.
                add("high" if direction == "to_server" and r["declared"] else "medium", name,
                    f"fired to the {label} at {fired[0]['where']}, but no {label} handler was found")
            if handled and not fired:
                add("low", name, f"has a {label} handler at {handled[0]['where']}, but nothing fires it")
        if mine and not r["declared"] and not dynamic:
            add("medium", name, "used in code but not declared in a project or model file or by Instance.new")
        if r["declared"] and not mine:
            add("low", name, "declared but never used")
    if unresolved:
        findings.append({"severity": "low", "remote": None,
                         "issue": f"{len(unresolved)} remote uses whose name couldn't be resolved",
                         "where": unresolved[:10]})
    shown, hidden = _capped(findings)
    notes = ["Heuristic: names are matched by text, so a remote reached through a function argument or table is "
             "listed as unresolved."]
    if dynamic:
        notes.append(f"Remotes created without a literal Name at {', '.join(dynamic[:5])}; undeclared-name checks "
                     "were skipped.")
    return {"ok": not any(f["severity"] == "high" for f in findings), "files_scanned": len(files),
            "remotes": sorted(remotes.values(), key=lambda r: r["name"])[:MAX_FINDINGS], "findings": shown,
            "more_findings": hidden, "notes": notes}


# ---------------------------------------------------------------------------------------------
# Player actions: (pattern, label). Each pattern ends at the "(" whose arguments hold the handler.
ACTION_RES = (
    (re.compile(r"\.\s*(Activated|MouseButton1Click|MouseButton1Down|TouchTap)\s*:\s*Connect\s*\("), "button"),
    (re.compile(r"\.\s*(InputBegan)\s*:\s*Connect\s*\("), "input"),
    (re.compile(r":\s*(BindAction|BindActionAtPriority)\s*\("), "input"),
    (re.compile(r"\.\s*(Triggered)\s*:\s*Connect\s*\("), "prompt"),
    (re.compile(r"\.\s*(Touched)\s*:\s*Connect\s*\("), "touch"),
    (re.compile(r"\.\s*(OnClientEvent)\s*:\s*Connect\s*\("), "server result"),
)
# Something the player sees, hears, or feels: FEEDBACK_RE runs on code with strings blanked, and
# FEEDBACK_NEW_RE (effect instances) on code with strings kept.
FEEDBACK_NEW_RE = re.compile(r"Instance\.new\(\s*[\"'](?:Sound|ParticleEmitter|Highlight|Explosion|Beam|Trail|Fire|"
                             r"Sparkles|Smoke|BillboardGui|SelectionBox)[\"']")
FEEDBACK_RE = re.compile(
    r":\s*(?:Play|Emit|LoadAnimation|PlayLocalSound|SetMotor)\s*\("
    r"|\.\s*(?:Text|Visible|Image|ImageColor3|ImageTransparency|BackgroundColor3|BackgroundTransparency|TextColor3|"
    r"Size|Position|Rotation|Color|Transparency|Enabled|FieldOfView|Scale)\s*=(?!=)"
    r"|\.\s*Health\s*=(?!=)|:\s*TakeDamage\s*\(|\bCurrentCamera\b|\bTweenService\b"
    r"|\b\w*(?:[Ee]ffect|[Ff]eedback|[Jj]uice|[Ss]fx|SFX|[Vv]fx|VFX|[Ss]ound|[Ss]hake|[Ff]lash|[Pp]article|[Tt]ween|"
    r"[Aa]nimat|[Hh]aptic|[Cc]onfetti|[Pp]opup|[Tt]oast)\w*\s*(?:[.:]\s*\w+\s*)?\(")
BLOCK_RE = re.compile(r"\b(function|if|do|repeat|end|until)\b")
LOCAL_FUNCTION_RE = re.compile(r"\b(?:local\s+)?function\s+(?:[\w.]+[.:])?([A-Za-z_]\w*)\s*\(|\blocal\s+([A-Za-z_]\w*)"
                               r"\s*(?::[^=\n]+)?=\s*function\s*\(")
REQUIRE_RE = re.compile(r"\blocal\s+([A-Za-z_]\w*)\s*(?::[^=\n]+)?=\s*require\s*\(")


def _is_if_expression(code: str, pos: int) -> bool:
    """Luau's `x = if a then b else c` has no `end`."""
    before = code[:pos].rstrip()
    if not before:
        return False
    if before[-1] in "=(,{[+-*/%^<>~":
        return True
    word = re.search(r"([A-Za-z_]\w*)$", before)
    return bool(word) and word.group(1) in ("return", "and", "or", "not")


def _block_end(code: str, start: int) -> int:
    """End offset of the block that opens with the keyword at start (function/if/do/repeat)."""
    depth = 0
    for m in BLOCK_RE.finditer(code, start):
        word = m.group(1)
        if word == "if" and _is_if_expression(code, m.start()):
            continue
        depth += 1 if word in ("function", "if", "do", "repeat") else -1
        if depth == 0:
            return m.end()
    return len(code)


def _paren_end(code: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(code)):
        if code[i] in "([{":
            depth += 1
        elif code[i] in ")]}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(code)


def audit_feel(path: str) -> dict:
    """Heuristic scan of Luau sources for player actions (button presses, input, prompts, touches, server
    results) whose handlers give no visible, audible, or haptic feedback. Follows calls to functions defined
    in the same file; a handler that calls a required module is listed as unverified instead."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return {"ok": False, "error": f"not found: {root}"}
    files = _luau_files(root)
    findings, unverified = [], []
    actions = with_feedback = 0
    for f in files:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = _blank_lua(source, strings=False)
        code = _blank_lua(source, strings=True)
        rel = _rel(f, root)
        functions: dict[str, list[tuple[int, int]]] = {}
        for m in LOCAL_FUNCTION_RE.finditer(code):
            keyword = code.index("function", m.start())
            functions.setdefault(m.group(1) or m.group(2), []).append((keyword, _block_end(code, keyword)))
        modules = set(REQUIRE_RE.findall(code))

        def reach(start: int, end: int, seen: set) -> tuple[bool, set]:
            """Whether the span (or a same-file function it calls) gives feedback, and the modules it calls."""
            if FEEDBACK_RE.search(code, start, end) or FEEDBACK_NEW_RE.search(text, start, end):
                return True, set()
            called = set()
            for name in set(re.findall(r"(?<![\w.:])([A-Za-z_]\w*)\s*[.:]\s*\w+\s*\(", code[start:end])) & modules:
                called.add(name)
            for name in set(re.findall(r"(?<![\w.:])([A-Za-z_]\w*)", code[start:end])):  # calls and callbacks
                if name in functions and name not in seen:
                    seen.add(name)
                    for s, e in functions[name]:
                        found, more = reach(s, e, seen)
                        if found:
                            return True, set()
                        called |= more
            return False, called

        for pattern, label in ACTION_RES:
            for m in pattern.finditer(code):
                actions += 1
                open_pos = m.end() - 1
                found, called = reach(open_pos, _paren_end(code, open_pos), set())
                where = f"{rel}:{_line_of(code, m.start())}"
                if found:
                    with_feedback += 1
                elif called:
                    unverified.append({"where": where, "action": m.group(1),
                                       "feedback_may_be_in": sorted(called)})
                else:
                    findings.append({"where": where, "action": m.group(1), "kind": label,
                                     "issue": "no feedback in the handler: respond at once with a sound, tween, "
                                              "particles, or a UI change, even before the server confirms"})
    shown, hidden = _capped(findings)
    return {"ok": not findings, "files_scanned": len(files), "actions": actions, "with_feedback": with_feedback,
            "findings": shown, "more_findings": hidden, "unverified": unverified[:MAX_FINDINGS],
            "note": "Heuristic: finds whether feedback exists in each handler, not whether it feels good. Check "
                    "timing and strength in a play test."}
