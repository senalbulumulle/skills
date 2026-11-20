#!/usr/bin/env python3
"""Engine-aware Codex hooks for game projects: Unreal, Unity, Godot, Roblox (Rojo), and more.

Codex runs: python3 game_hooks.py <SessionStart|UserPromptSubmit|PreToolUse|PostToolUse|Stop>
with the event JSON on stdin, and reads JSON from stdout. Standard library only, Python 3.9+.
Engine checks run only inside a game project. In any project, a request to build a game gets a short
creative brief (plus Roblox guidance for Roblox requests and projects), and Stop checks lines added since the last commit for unfinished or generic content.
An internal error never blocks the agent: the hook prints a note to stderr and exits 0 with no output.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

MAX_ISSUES = 20
MAX_STOP_FILES = 300
# apply_patch can never edit these correctly: they are binary.
BINARY_ASSETS = (".uasset", ".umap", ".rbxl", ".rbxm", ".blend")


@dataclass(frozen=True)
class Project:
    engine: str
    root: Path
    version: str = ""


@dataclass(frozen=True)
class Issue:
    level: str  # "error" blocks a Stop; "warning" is only reported
    path: str
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.level}: {self.message}"


# ---------------------------------------------------------------- engine detection

def _read(path: Path, limit: int = 1_000_000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def _unreal_version(uproject: Path) -> str:
    try:
        assoc = str(json.loads(_read(uproject)).get("EngineAssociation", ""))
    except (ValueError, AttributeError):
        return ""
    return "source build" if assoc.startswith("{") else assoc


def _godot_version(text: str) -> str:
    feature = re.search(r'config/features\s*=\s*PackedStringArray\(\s*"(\d+\.\d+)"', text)
    if feature:
        return feature.group(1)
    config = re.search(r"^config_version\s*=\s*(\d+)", text, re.M)
    if config:
        return {"5": "4", "4": "3"}.get(config.group(1), "")
    return ""


WEB_ENGINES = ("phaser", "three", "pixi.js", "@babylonjs/core", "kaboom", "excalibur", "playcanvas")


def match_dir(d: Path) -> Optional[Project]:
    try:
        names = os.listdir(d)
    except OSError:
        return None
    files = set(names)
    for n in sorted(names):
        if n.endswith(".uproject"):
            return Project("unreal", d, _unreal_version(d / n))
    version_file = d / "ProjectSettings" / "ProjectVersion.txt"
    if "Assets" in files and version_file.is_file():
        m = re.search(r"m_EditorVersion:\s*(\S+)", _read(version_file))
        return Project("unity", d, m.group(1) if m else "")
    if "project.godot" in files:
        return Project("godot", d, _godot_version(_read(d / "project.godot")))
    if "default.project.json" in files:  # Rojo's default name; detect it even while its JSON is broken
        return Project("roblox", d)
    for n in sorted(names):
        if n.endswith(".project.json"):
            try:
                if "tree" in json.loads(_read(d / n)):
                    return Project("roblox", d)
            except (ValueError, TypeError):
                pass
    if any(n.endswith((".rbxl", ".rbxlx")) for n in names):
        return Project("roblox", d)
    if "game.project" in files:
        return Project("defold", d)
    if any(n.endswith(".yyp") for n in names):
        return Project("gamemaker", d)
    if "Cargo.toml" in files:
        cargo = _read(d / "Cargo.toml")
        m = re.search(r'^\s*bevy\s*=\s*(?:"([^"]+)"|\{[^}\n]*version\s*=\s*"([^"]+)")', cargo, re.M)
        if m or re.search(r"^\s*\[(?:workspace\.)?dependencies\.bevy\]", cargo, re.M):
            return Project("bevy", d, (m.group(1) or m.group(2)) if m else "")
    for n in sorted(names):
        if n.endswith(".csproj") and "MonoGame.Framework" in _read(d / n):
            return Project("monogame", d)
    if "main.lua" in files and "love." in _read(d / "main.lua") + _read(d / "conf.lua"):
        return Project("love2d", d)
    if "package.json" in files:
        try:
            pkg = json.loads(_read(d / "package.json"))
            deps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
        except (ValueError, AttributeError, TypeError):
            deps = {}
        for name in WEB_ENGINES:
            if name in deps:
                return Project("web", d, f"{name} {deps[name]}")
    for n in ("requirements.txt", "pyproject.toml"):
        if n in files and re.search(r"^\s*[\"']?pygame(-ce)?\b", _read(d / n), re.M):
            return Project("pygame", d)
    return None


def detect(start: Path) -> Optional[Project]:
    """Nearest game project containing start, searching up to the git root or home."""
    d = start if start.is_dir() else start.parent
    home = Path.home()
    for _ in range(40):
        found = match_dir(d)
        if found or (d / ".git").exists() or d == home or d.parent == d:
            return found
        d = d.parent
    return None


def detect_all(cwd: Path) -> list[Project]:
    """The project containing cwd, or else every project one level below it (monorepos)."""
    found = detect(cwd)
    if found:
        return [found]
    try:
        children = sorted(p for p in cwd.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []
    return [p for p in (match_dir(c) for c in children[:100]) if p]


# ---------------------------------------------------------------- per-engine knowledge

ENGINES = {
    "unreal": {
        "name": "Unreal Engine",
        "generated": ("Binaries", "Intermediate", "DerivedDataCache", "Saved"),
        "protected": ("Content", "Config", "Source", "*.uproject"),
        "context": [
            "Never edit .uasset/.umap with text tools; change them in the editor or via Python/commandlets.",
            "Binaries/, Intermediate/, Saved/, DerivedDataCache/ and *.generated.h are generated: don't edit them.",
            'A header with UCLASS/USTRUCT/UENUM/UINTERFACE must #include "<File>.generated.h" last; classes and structs need GENERATED_BODY().',
            "Create UObjects with NewObject<T>() and actors with SpawnActor<T>(), never new.",
            "Compile with Engine/Build/BatchFiles/Build.bat (Mac/Build.sh, Linux/Build.sh) for the <Project>Editor target.",
        ],
    },
    "unity": {
        "name": "Unity",
        "generated": ("Library", "Temp", "Logs", "obj"),
        "protected": ("Assets", "ProjectSettings", "Packages/manifest.json"),
        "context": [
            "Unity writes each asset's .meta (its GUID) itself: never hand-write one; move or delete it together with its asset.",
            "Library/, Temp/, Logs/ and obj/ are generated: don't edit them.",
            "UnityEditor code goes in an Editor folder, an Editor-only asmdef, or #if UNITY_EDITOR, or player builds fail.",
            "A MonoBehaviour or ScriptableObject class must live in a file with the same name.",
            "Run tests with: Unity -batchmode -projectPath . -runTests -testPlatform EditMode (no -quit with -runTests).",
        ],
    },
    "godot": {
        "name": "Godot",
        "generated": (".godot", ".import"),
        "protected": ("project.godot",),
        "context": [
            ".godot/ (and .import/ in Godot 3) is a generated cache: don't edit it.",
            "Godot 4 GDScript: @export, @onready, @tool, await, signal.connect(callable); no yield or setget.",
            "Check a script without the editor: godot --headless --check-only --script <file.gd>.",
        ],
    },
    "roblox": {
        "name": "Roblox (Rojo)",
        "generated": ("Packages", "ServerPackages", "DevPackages"),  # Wally; only when wally.toml exists
        "protected": (),
        "context": [
            "The server owns every outcome: validate and rate-limit every RemoteEvent/RemoteFunction argument.",
            'Use task.wait/task.spawn/task.delay and game:GetService("Name"), never wait()/spawn()/delay() or game.Name.',
            "Save data with UpdateAsync under a session lock; kick on load failure instead of playing on defaults.",
            "If the roblox-forge MCP server is connected, run check_project after layout changes, map_remotes and audit_remotes after remote changes, and audit_feel and audit_polish after gameplay, effect, sound, or UI changes.",
            "Never publish (rojo upload, mantle deploy, rbxcloud): the user does that.",
        ],
    },
    "defold": {
        "name": "Defold",
        "generated": ("build", ".internal"),
        "protected": ("game.project",),
        "context": ["build/ and .internal/ are generated: don't edit them."],
    },
    "gamemaker": {
        "name": "GameMaker",
        "generated": (),
        "protected": ("*.yyp",),
        "context": ["The .yyp lists every resource: add or remove resources in the IDE, not by deleting files."],
    },
    "bevy": {
        "name": "Bevy",
        "generated": ("target",),
        "protected": (),
        "context": [
            "Bevy's API changes between minor versions: match the pinned version, not newer examples.",
            "Run cargo check after edits; target/ is generated.",
        ],
    },
    "monogame": {
        "name": "MonoGame",
        "generated": ("bin", "obj"),
        "protected": (),
        "context": ["Assets go through the MGCB content pipeline (Content/*.mgcb); bin/ and obj/ are generated."],
    },
    "love2d": {"name": "LÖVE", "generated": (), "protected": (), "context": []},
    "web": {
        "name": "Web game",
        "generated": ("node_modules",),
        "protected": (),
        "context": ["Use a fixed timestep and check the browser console for errors after changes."],
    },
    "pygame": {"name": "Pygame", "generated": (), "protected": (), "context": []},
}


def generated_reason(project: Project, path: Path) -> str:
    """Why path is a generated file the agent must not edit, or ''."""
    try:
        rel = path.resolve().relative_to(project.root.resolve())
    except ValueError:
        return ""
    parts = rel.parts
    if not parts:
        return ""
    if project.engine == "unreal":
        if path.name.endswith(".generated.h"):
            return "Unreal Header Tool regenerates *.generated.h on every build"
        if len(parts) > 1 and parts[0] == "Saved":
            return "Unreal writes Saved/ at runtime"
        nested = {"Binaries", "Intermediate", "DerivedDataCache"}.intersection(parts[:-1])  # also Plugins/<Name>/
        return f"Unreal regenerates {sorted(nested)[0]}/" if nested else ""
    gen = ENGINES[project.engine]["generated"]
    if project.engine == "roblox" and not (project.root / "wally.toml").is_file():
        return ""
    if len(parts) > 1 and parts[0] in gen:
        return f"{parts[0]}/ is generated by {ENGINES[project.engine]['name']}"
    return ""


# ---------------------------------------------------------------- source checks

def _blank_comments_c(text: str) -> str:
    """Remove // and /* */ comments (C++, C#), keeping newlines so line numbers stay right."""
    def keep_newlines(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/',
                  lambda m: m.group(0) if m.group(0).startswith('"') else keep_newlines(m), text, flags=re.S)


def _blank_strings(m: re.Match) -> str:
    """Keep a string literal's quotes but blank its contents, so code patterns can't match inside it."""
    s = m.group(0)
    return s[0] + " " * (len(s) - 2) + s[-1]


def _blank_comments_lua(text: str) -> str:
    def keep_newlines(m: re.Match) -> str:
        return _blank_strings(m) if m.group(0)[0] in "\"'" else re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|--\[(=*)\[.*?\]\1\]|--[^\n]*',
                  keep_newlines, text, flags=re.S)


def _blank_comments_hash(text: str) -> str:
    def keep(m: re.Match) -> str:
        return _blank_strings(m) if m.group(0)[0] in "\"'" else ""
    return re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|#[^\n]*', keep, text)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _version_tuple(version: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:2])


def check_unreal(project: Project, path: Path, text: str, rel: str) -> list[Issue]:
    issues = []
    code = _blank_comments_c(text)
    if path.suffix == ".h" and not path.name.endswith(".generated.h"):
        macro = re.search(r"^\s*(UCLASS|USTRUCT|UENUM|UINTERFACE)\s*\(", code, re.M)
        if macro:
            line = _line(code, macro.start(1))
            expected = f"{path.stem}.generated.h"
            includes = [Path(m.group(1)).name for m in re.finditer(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', code, re.M)]
            if expected not in includes:
                issues.append(Issue("error", rel, line, f'add #include "{expected}" as the last #include (UHT fails without it)'))
            elif includes[-1] != expected:
                issues.append(Issue("error", rel, line, f'"{expected}" must be the last #include'))
            if re.search(r"^\s*(UCLASS|USTRUCT|UINTERFACE)\s*\(", code, re.M) and not re.search(
                    r"\bGENERATED_(?:BODY|UCLASS_BODY|USTRUCT_BODY|UINTERFACE_BODY|IINTERFACE_BODY)\s*\(", code):
                issues.append(Issue("error", rel, line, "reflected class or struct is missing GENERATED_BODY()"))
    if path.suffix in (".h", ".cpp"):
        for m in re.finditer(r"\bnew\s+([UA][A-Z]\w*)\s*[(;{]", code):
            kind = "SpawnActor<T>()" if m.group(1).startswith("A") else "NewObject<T>()"
            issues.append(Issue("warning", rel, _line(code, m.start()), f"create {m.group(1)} with {kind}, not new"))
    return issues


def _editor_only_asmdef(project: Project, path: Path) -> bool:
    """True when the nearest .asmdef above path targets only the Editor platform."""
    d = path.parent
    root = project.root.resolve()
    while True:
        asmdefs = sorted(d.glob("*.asmdef"))
        if asmdefs:
            try:
                data = json.loads(_read(asmdefs[0]))
                return data.get("includePlatforms") == ["Editor"]
            except (ValueError, AttributeError):
                return False
        if d.resolve() == root or d.parent == d:
            return False
        d = d.parent


def check_unity(project: Project, path: Path, text: str, rel: str) -> list[Issue]:
    if path.suffix != ".cs":
        return []
    issues = []
    code = _blank_comments_c(text)
    editor_api = re.search(r"\bUnityEditor\b", code)
    if (editor_api and "Editor" not in Path(rel).parts[:-1]
            and not re.search(r"^\s*#\s*if\b[^\n]*\bUNITY_EDITOR\b", code, re.M)
            and not _editor_only_asmdef(project, path)):
        issues.append(Issue("error", rel, _line(code, editor_api.start()),
                            "UnityEditor is unavailable in player builds: move the file to an Editor folder or wrap it in #if UNITY_EDITOR"))
    components = re.findall(r"^(?:(?!abstract)[^\n])*\bclass\s+(\w+)\s*:\s*(?:MonoBehaviour|ScriptableObject|NetworkBehaviour)\b",
                            code, re.M)
    if components and path.stem not in components:
        issues.append(Issue("warning", rel, 1, f"Unity only attaches {components[0]} if the file is named {components[0]}.cs"))
    if _version_tuple(project.version) >= (2023, 1):
        for m in re.finditer(r"\bFindObjectsOfType\b|\bFindObjectOfType\b", code):
            issues.append(Issue("warning", rel, _line(code, m.start()),
                                f"{m.group(0)} is obsolete in Unity {project.version}: use FindFirstObjectByType, FindAnyObjectByType, or FindObjectsByType"))
    return issues


GODOT4_ONLY = [
    (r"^\s*@(onready|export\w*|tool)\b", "@{0} is Godot 4 syntax; this project is Godot 3"),
    (r"\bawait\b", "await is Godot 4 syntax; use yield in Godot 3"),
]
GODOT3_ONLY = [
    (r"\byield\s*\(", "yield was removed in Godot 4: use await"),
    (r"^\s*onready\s+var\b", "use @onready var in Godot 4"),
    (r"^\s*export(?:\s*\(|\s+var\b)", "use @export in Godot 4"),
    (r"^\s*tool\s*$", "use @tool in Godot 4"),
    (r"\bsetget\b", "setget was removed in Godot 4: use property get/set blocks"),
    (r'\.connect\(\s*"[^"]*"\s*,\s*self\s*,', 'Godot 4 connects with signal.connect(callable), e.g. button.pressed.connect(_on_pressed)'),
]


def check_godot(project: Project, path: Path, text: str, rel: str) -> list[Issue]:
    if path.suffix != ".gd" or not project.version:
        return []
    code = _blank_comments_hash(text)
    rules = GODOT3_ONLY if project.version.startswith("4") else GODOT4_ONLY
    issues = []
    for pattern, message in rules:
        for m in re.finditer(pattern, code, re.M):
            issues.append(Issue("error", rel, _line(code, m.start()), message.format(*m.groups())))
    return issues


ROBLOX_SERVICES = ("Players|Workspace|ReplicatedStorage|ReplicatedFirst|ServerScriptService|ServerStorage|StarterGui|"
                   "StarterPlayer|StarterPack|Lighting|SoundService|Teams|TweenService|RunService|UserInputService|"
                   "HttpService|DataStoreService|MarketplaceService|CollectionService|PhysicsService|TextChatService")


def _rojo_paths(node: object, base: Path, rel: str, issues: list[Issue], text: str) -> None:
    if not isinstance(node, dict):
        return
    target = node.get("$path")
    if isinstance(target, str) and not (base / target).exists():
        pos = text.find(json.dumps(target))
        issues.append(Issue("error", rel, _line(text, max(pos, 0)), f"$path {target!r} does not exist"))
    for key, child in node.items():
        if not key.startswith("$"):
            _rojo_paths(child, base, rel, issues, text)


def check_roblox(project: Project, path: Path, text: str, rel: str) -> list[Issue]:
    if path.name.endswith(".project.json"):
        try:
            data = json.loads(text)
        except ValueError as e:
            return [Issue("error", rel, getattr(e, "lineno", 1), f"invalid JSON: {e}")]
        issues: list[Issue] = []
        _rojo_paths(data.get("tree") if isinstance(data, dict) else None, path.parent, rel, issues, text)
        return issues
    if path.suffix not in (".lua", ".luau"):
        return []
    code = _blank_comments_lua(text)
    issues = []
    for m in re.finditer(r"(?<![\w.:])(wait|spawn|delay)\s*\(", code):
        if not re.search(r"\bfunction\s+$", code[max(0, m.start() - 20):m.start()]):
            issues.append(Issue("warning", rel, _line(code, m.start()), f"{m.group(1)}() is deprecated: use task.{m.group(1)}()"))
    for m in re.finditer(rf"\bgame\.({ROBLOX_SERVICES})\b", code):
        issues.append(Issue("warning", rel, _line(code, m.start()), f'use game:GetService("{m.group(1)}")'))
    return issues + _value_type_issues(text, code, rel)


# Properties whose value type is a sequence, range, or vector: assigning a Color3 or a plain number errors at
# run time. The same table as VALUE_TYPES in mcp/roblox-forge/forge.py (tools/test_codex_hooks.py keeps them
# identical).
VALUE_TYPES = {
    "ParticleEmitter": {"Color": "ColorSequence", "Size": "NumberSequence", "Transparency": "NumberSequence",
                        "Squash": "NumberSequence", "Lifetime": "NumberRange", "Speed": "NumberRange",
                        "Rotation": "NumberRange", "RotSpeed": "NumberRange", "SpreadAngle": "Vector2"},
    "Beam": {"Color": "ColorSequence", "Transparency": "NumberSequence"},
    "Trail": {"Color": "ColorSequence", "Transparency": "NumberSequence", "WidthScale": "NumberSequence"},
    "UIGradient": {"Color": "ColorSequence", "Transparency": "NumberSequence"},
}
INSTANCE_VAR_RE = re.compile(r"""\blocal\s+([A-Za-z_]\w*)\s*(?::\s*[\w.]+\??\s*)?=\s*Instance\.new\(\s*["'](\w+)["']""")
ASSIGN_RE = re.compile(r"(?<![\w.:])([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*=(?!=)[ \t]*([^\n]*)")
NUMBER_RE = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
CONSTRUCTOR_RE = re.compile(r"(Color3|BrickColor|ColorSequence|NumberSequence|NumberRange|Vector2|Vector3)\s*\.")
LOCAL_NAMES_RE = re.compile(r"\blocal\s+(?!function\b)([A-Za-z_][^=\n]*)")
FOR_NAMES_RE = re.compile(r"\bfor\s+([A-Za-z_][\w\s,:]*?)\s+(?:in\b|=)")
FUNCTION_RE = re.compile(r"\bfunction\b[^(\n]*\(")


def _split_top(text: str) -> list:
    """Split on commas outside brackets, so `a: { x: number, y: number }, b` gives two parts."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        depth += ch in "([{"
        depth -= ch in ")]}"
        if ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    return parts + [text[start:]]


def _bindings(code: str) -> list:
    """(offset, name) for every local, loop variable, and function parameter."""
    out = []
    for m in LOCAL_NAMES_RE.finditer(code):
        out += [(m.start(), part.split(":")[0].strip()) for part in _split_top(m.group(1))]
    for m in FOR_NAMES_RE.finditer(code):
        out += [(m.start(), part.split(":")[0].strip()) for part in m.group(1).split(",")]
    for m in FUNCTION_RE.finditer(code):
        depth, end = 1, len(code)
        for i in range(m.end(), len(code)):
            depth += code[i] in "([{"
            depth -= code[i] in ")]}"
            if depth == 0:
                end = i
                break
        out += [(m.end(), part.split(":")[0].strip()) for part in _split_top(code[m.end():end])]
    return sorted(out)


def _value_type_issues(text: str, code: str, rel: str) -> list[Issue]:
    """`emitter.Color = Color3...` and similar, for instances created with `local x = Instance.new(...)`."""
    kept = re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|--\[(=*)\[.*?\]\1\]|--[^\n]*',
                  lambda m: m.group(0) if m.group(0)[0] in "\"'" else re.sub(r"[^\n]", " ", m.group(0)),
                  text, flags=re.S)  # comments blanked, strings kept: class names are strings
    classes = {m.start(): m.group(2) for m in INSTANCE_VAR_RE.finditer(kept)}
    if not set(classes.values()) & set(VALUE_TYPES):
        return []
    bindings = _bindings(code)
    issues = []
    for m in ASSIGN_RE.finditer(code):
        latest = [pos for pos, name in bindings if name == m.group(1) and pos < m.start()]
        cls = classes.get(latest[-1]) if latest else None  # the latest declaration must be the Instance.new
        expected = VALUE_TYPES.get(cls, {}).get(m.group(2)) if cls else None
        if not expected:
            continue
        rhs = m.group(3).strip().rstrip(";").strip()
        found = CONSTRUCTOR_RE.match(rhs)
        got = "number" if NUMBER_RE.fullmatch(rhs) else found.group(1) if found else None
        if got and got != expected:
            issues.append(Issue("error", rel, _line(code, m.start()),
                                f"{cls}.{m.group(2)} takes a {expected}, not a {got}; this errors at run time"))
    return issues


CHECKS = {"unreal": check_unreal, "unity": check_unity, "godot": check_godot, "roblox": check_roblox}


def check_file(path: Path, cwd: Path) -> list[Issue]:
    project = detect(path)
    check = CHECKS.get(project.engine) if project else None
    if not check or not path.is_file():
        return []
    try:
        rel = str(path.resolve().relative_to(cwd.resolve()))
    except ValueError:
        rel = str(path)
    return check(project, path, _read(path), rel)


# ---------------------------------------------------------------- creative quality

# The same rules as mcp/creative-director/director.py (tools/test_codex_hooks.py keeps them identical).
# Patterns are split across string pieces so this file never matches its own rules.
UNFINISHED_RULES = (
    ("filler-text", re.compile("lorem" + r"\s+" + "ipsum", re.I), "filler text"),
    ("todo-stub", re.compile(r"\b(?:TO" + r"DO|FIX" + r"ME)\b(?:\([^)]*\))?\s*[:-]\s*.{0,40}?\b(?i:implement|placeholder|stub"
                             r"|replace (?:this|with)|add (?:real|actual))"),
     "a TODO stands in for the work"),
    ("stub", re.compile(r"NotImplemented" + "Exception|\\b(?:to" + r"do|unimplemented)!\(|throw new Error\(\s*[\"'`]"
                        "not " + "implemented", re.I),
     "a stub stands in for the implementation"),
    ("placeholder-text", re.compile(r"[\"'>]\s*(?:your (?:text|title|name|description) " + "here|insert [\\w ]{1,30} "
                                    + "here|sample " + "text|placeholder " + "text)\\b", re.I),
     "stand-in text that users would see"),
    ("generic-title", re.compile(r"[\"'>#]\s*(?:My|Untitled|Awesome|Amazing|Epic|Cool) (?:Game|Adventure|Quest|Project)"
                                 r"\b"),
     "a generic title; name it after what makes it different"),
    ("fake-asset-id", re.compile(r"(?:rbxasset" + r"id://|roblox\.com/asset/\?id=)(?:(?:0+|"
                                 + "|".join("1234567890"[:n] for n in range(10, 2, -1))
                                 + r")(?!\w)|(?=[\"'](?!\s*(?:\.\.|\+))))"),
     "a Roblox asset ID that points at nothing; upload the real asset or leave the property unset"),
    ("default-ui-text", re.compile(r"\bText\s*=\s*[\"'](?:Label|Button|Text" + "Label|Text" + "Button|Text" + r"Box)[\"']"),
     "a default or class-name UI label; write what the player should read"),
)
GAME_REQUEST_RE = re.compile(r"\b(?:games?|gameplay|minigames?|boss(?:es)?|enem(?:y|ies)|platformer|shooter|roguelike|"
                             r"rpg|obby|tycoon|simulator|npcs?|quests?)\b", re.I)
LEVEL_RE = re.compile(r"\b(?:levels?|mechanics?|power-?ups?|weapons?)\b", re.I)
CREATIVE_VERB_RE = re.compile(r"\b(?:make|build|create|design|prototype|develop|implement|add|write|remake|generate)\b",
                              re.I)
CREATIVE_BRIEF = ("Creative brief (from game_hooks): commit to one specific idea with a hook a player would describe to "
                  "a friend. Use real names, numbers, and text that fit the world, never stand-ins. Get the smallest "
                  "playable version running, make input feel instant and give every action visible and audible "
                  "feedback, then build or run it to verify before you finish.")
ROBLOX_RE = re.compile(r"\b(?:roblox|rojo|obby|obbies)\b", re.I)
ROBLOX_BRIEF = ("Roblox: assume many players are on phones (default thumbstick and jump, a few large buttons sized "
                "with Scale) and give them a reason to play together. A new player should act within 10 seconds and "
                "earn something within 60. The server decides every outcome. If roblox-forge is connected, run "
                "map_remotes and audit_feel on the project before you finish.")
POLISH_RE = re.compile(r"\b(?:vfx|sfx|effects?|particles?|trails?|beams?|sounds?|audio|music|juice|juicy|polish|"
                       r"feedback|ui|hud|menus?|buttons?|animations?|tweens?)\b", re.I)
POLISH_BRIEF = ("Roblox polish: layer each important moment (particles, a sound, a quick tween or camera shake) and "
                "start it the frame the player acts. Use only real assets: built-in rbxasset:// files, the user's "
                "uploads, or IDs found with Roblox Studio's search_asset tool; never invent an asset ID. If roblox-forge "
                "is connected, start effects from vfx_recipe and run audit_polish and audit_feel before you finish. If "
                "Roblox Studio's MCP server is connected, play-test with start_stop_play and look with screen_capture.")
# "character" alone usually means the player's avatar in Roblox, so only character-writing phrases count.
STORY_RE = re.compile(r"\b(?:npcs?|dialog(?:ue)?s?|story|stories|storylines?|narrative|quests?|cutscenes?|lore|"
                      r"backstor(?:y|ies)|voice[- ]?overs?|voice lines?|cast of characters|"
                      r"characters? (?:sheets?|bios?|arcs?|profiles?|personalit(?:y|ies)))\b", re.I)
STORY_BRIEF = ("Roblox story: write the Markdown docs first (characters.md with a distinct voice and a vo direction "
               "per character, story.md with premise, acts, and the flags game code sets, and one dialogue/<id>.md per "
               "conversation), keep lines under 100 characters for phones, and give every node a way out. If "
               "roblox-forge is connected, run review_story until it is clean, then build_dialogue, export_voiceover, "
               "and export_localization; play the result with DialogueRunner on the server. Never hand-edit the "
               "generated dialogue module: change the docs and rebuild.")
MAX_LINE_SHOWN = 100


def _skip_for_unfinished(path: str) -> bool:
    """Tests, fixtures, lockfiles, and minified files may contain these patterns on purpose."""
    parts = path.lower().split("/")
    name = parts[-1]
    return (name.startswith("test_") or ".test." in name or ".spec." in name or name.endswith(("_test.py", ".lock",
            ".min.js", "-lock.json")) or any(part in {"test", "tests", "__tests__", "spec", "fixtures"} for part in parts))


def _git(root: Path, *args: str, timeout: int = 10) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *args],
                             capture_output=True, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def added_lines(cwd: Path) -> list[tuple[str, int, str]]:
    """(path relative to the git root, line number, text) for each line added since HEAD, untracked files included."""
    top = _git(cwd, "rev-parse", "--show-toplevel", timeout=5)
    if top is None:
        return []
    root = Path(top.strip())
    added: list[tuple[str, int, str]] = []
    diff = _git(root, "diff", "--no-color", "--no-ext-diff", "-U0", "HEAD") or ""
    path, number = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)", line)
            number = int(m.group(1)) if m else 0
        elif line.startswith("+") and path is not None:
            added.append((path, number, line[1:]))
            number += 1
    head_exists = _git(root, "rev-parse", "--verify", "--quiet", "HEAD", timeout=5) is not None
    new_files = _git(root, "ls-files", "-z", "--others", "--exclude-standard") or ""
    if not head_exists:  # no commit yet: every tracked file is new too
        new_files += _git(root, "ls-files", "-z") or ""
    for name in sorted(set(filter(None, new_files.split("\0"))))[:MAX_STOP_FILES]:
        file = root / name
        if file.is_file() and file.stat().st_size <= 1_000_000:
            data = file.read_bytes()
            if b"\0" not in data[:4096]:
                added += [(name, i, text) for i, text in enumerate(data.decode("utf-8", "replace").splitlines(), 1)]
    return added


def unfinished_issues(cwd: Path) -> list[Issue]:
    issues = []
    for path, number, text in added_lines(cwd):
        if _skip_for_unfinished(path):
            continue
        for _rule, pattern, message in UNFINISHED_RULES:
            if pattern.search(text):
                issues.append(Issue("error", path, number, f"{message}: {text.strip()[:MAX_LINE_SHOWN]}"))
    return issues


# ---------------------------------------------------------------- generated dialogue

# Written by the roblox-narrative skill's story.py build (and roblox-forge's build_dialogue). Line 2 is the
# marker; line 3 names the docs folder and the hash of the docs it was built from.
DIALOGUE_MARKER = "-- Generated from Markdown by roblox-narrative (story.py build)."
DOCS_LINE_RE = re.compile(r"^-- Docs: (?P<docs>.+) \(sha256 (?P<hash>[0-9a-f]{64})\)$")
SCAN_SKIP = {".git", "node_modules", "Packages", "ServerPackages", "DevPackages"}
MAX_SCANNED = 3000


def dialogue_header(path: Path) -> Optional[tuple]:
    """(docs folder, recorded hash) when path is a generated dialogue module, else None."""
    head = _read(path, 600).split("\n")
    if len(head) < 3 or not head[1].startswith(DIALOGUE_MARKER):
        return None
    m = DOCS_LINE_RE.match(head[2])
    return (Path(os.path.normpath(path.parent / m.group("docs"))), m.group("hash")) if m else None


def docs_hash(docs: Path) -> Optional[str]:
    """The same hash as story.py's docs_hash, or None when the docs are gone."""
    if not (docs / "characters.md").is_file():
        return None
    files = [docs / "characters.md"] + ([docs / "story.md"] if (docs / "story.md").is_file() else [])
    h = hashlib.sha256()
    for path in files + sorted((docs / "dialogue").glob("*.md")):
        try:
            h.update(path.relative_to(docs).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
        except OSError:
            return None
    return h.hexdigest()


def stale_dialogue(cwd: Path, changed: list[Path]) -> list[Issue]:
    """Generated dialogue modules whose docs changed since the build, when either side changed this session."""
    if not changed:
        return []
    changed_set = {p.resolve() for p in changed}
    issues, scanned = [], 0
    for project in detect_all(cwd):
        if project.engine != "roblox":
            continue
        for directory, dirs, names in os.walk(project.root):
            dirs[:] = [d for d in dirs if d not in SCAN_SKIP]
            for name in names:
                if not name.endswith((".luau", ".lua")):
                    continue
                scanned += 1
                if scanned > MAX_SCANNED:
                    return issues
                path = Path(directory) / name
                header = dialogue_header(path)
                if not header:
                    continue
                docs, recorded = header
                docs_resolved = docs.resolve()
                involved = path.resolve() in changed_set or any(
                    docs_resolved in p.parents for p in changed_set)
                if involved and docs_hash(docs) != recorded:
                    try:
                        rel = str(path.relative_to(cwd))
                    except ValueError:
                        rel = str(path)
                    issues.append(Issue("error", rel, 1, f"built from {docs} but the docs changed since: run "
                                                         "build_dialogue (roblox-forge) or story.py build again"))
    return issues


# ---------------------------------------------------------------- tool input parsing

def parse_patch(patch: str) -> list[tuple[str, str]]:
    """(op, path) for each file in an apply_patch body; op is Add, Update, Delete, or Move (the new path)."""
    ops = []
    for line in patch.splitlines():
        m = re.match(r"\*\*\* (Add|Update|Delete) File: (.+?)\s*$", line) or re.match(r"\*\*\* (Move) to: (.+?)\s*$", line)
        if m:
            ops.append((m.group(1), m.group(2)))
    return ops


def _resolve(cwd: Path, p: str) -> Path:
    path = Path(os.path.expanduser(p))
    return Path(os.path.normpath(path if path.is_absolute() else cwd / path))


BINARY_RE = r"[^\s'\";&|<>]+(?:" + "|".join(re.escape(e) for e in BINARY_ASSETS) + r")\b"
BINARY_MESSAGE = "Binary engine assets (.uasset, .umap, .rbxl, .rbxm, .blend) can't be edited as text; change them in the editor."


def _publishes(words: list[str]) -> str:
    """What a simple command publishes, or ''."""
    tool, args = Path(words[0]).name.lower(), words[1:]
    if tool == "xcrun" and args[:1] == ["altool"]:
        tool, args = "altool", args[1:]
    if tool == "steamcmd" and any(a.lower().startswith("+run_app_build") for a in args):
        return "uploads a build to Steam"
    if tool == "butler" and args[:1] == ["push"]:
        return "uploads a build to itch.io"
    if tool == "rojo" and args[:1] == ["upload"]:
        return "overwrites a live Roblox place"
    if tool == "mantle" and args[:1] == ["deploy"]:
        return "deploys a live Roblox experience"
    if tool == "rbxcloud" and args[:2] == ["experience", "publish"]:
        return "publishes a live Roblox place"
    if tool in ("buildpatchtool", "buildpatchtool.exe"):
        return "uploads a build to the Epic Games Store"
    if tool == "altool" and any(a in ("--upload-app", "--upload-package") for a in args):
        return "uploads a build to App Store Connect"
    return ""


def _segments(command: str) -> Optional[list[list[str]]]:
    """Shell words split into simple commands at ; & | ( ) and newlines, or None if unparsable."""
    try:
        lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return None
    out: list[list[str]] = []
    cur: list[str] = []
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


def _command_words(segment: list[str]) -> list[str]:
    """The command and its arguments, without VAR=value prefixes, sudo, or env."""
    words = list(segment)
    while words and (re.match(r"^[A-Za-z_]\w*=", words[0]) or words[0] in ("sudo", "env", "command", "exec")):
        words = words[1:]
    return words


def _rm_targets(words: list[str]) -> list[str]:
    if words and Path(words[0]).name == "rm":
        args = words[1:]
    elif words[:2] == ["git", "rm"]:
        args = words[2:]
    else:
        return []
    return [a for a in args if not a.startswith("-") and a not in (">", ">>", "<")]


def bash_denial(command: str, cwd: Path) -> str:
    segments = _segments(command)
    if segments is None:  # unbalanced quotes: Codex will reject it anyway; only check the raw text
        return BINARY_MESSAGE if re.search(r"(?:>>?|\btee\b)\s*" + BINARY_RE, command) else ""
    commands = [w for w in (_command_words(s) for s in segments) if w]
    for words in commands:
        what = _publishes(words)
        if what:
            return f"This command {what}. Publishing is outward-facing: ask the user to run it themselves."
        joined = " ".join(words)
        tool = Path(words[0]).name
        in_place = tool in ("sed", "gsed", "perl") and any(re.match(r"^-[a-zA-Z]*i|^--in-place", a) for a in words[1:])
        if (in_place and re.search(BINARY_RE, joined)) or re.search(r"(?:>>?|\btee\b(?:\s+-a)?)\s*" + BINARY_RE, joined):
            return BINARY_MESSAGE
    project = detect(cwd)
    if not project:
        return ""
    for words in commands:
        if words[0] == "cd" and len(words) == 2:  # later relative paths resolve from the new folder
            cwd = _resolve(cwd, words[1])
            continue
        targets = _rm_targets(words)
        for t in targets:
            reason = _protected_reason(project, cwd, t)
            if not reason and project.engine == "unity" and t.endswith(".meta") and not re.search(r"[*?\[]", t):
                asset = _resolve(cwd, t[:-5])
                if asset.exists() and not any(_resolve(cwd, o) == asset for o in targets):
                    reason = f"deleting {t} without its asset orphans the asset's GUID and breaks every reference to it"
            if reason:
                return f"Blocked: {reason}. Ask the user before deleting it."
    return ""


def _protected_reason(project: Project, cwd: Path, target: str) -> str:
    """Why rm on target would destroy core project data, or ''."""
    glob = re.search(r"[*?\[]", target)
    if glob:
        base, rest = target[:glob.start()], target[glob.start():]
        if rest.strip("/") not in ("*", "**", ".*", "**/*"):
            return ""  # a pattern inside a folder (Assets/*.tmp) deletes files, not the folder's purpose
        wiped = _resolve(cwd, base or ".")
    else:
        wiped = _resolve(cwd, target)
    root = project.root.resolve()
    try:
        wiped = wiped.resolve()
    except OSError:
        return ""
    name = ENGINES[project.engine]["name"]
    for pattern in ENGINES[project.engine]["protected"]:
        for core in (sorted(root.glob(pattern)) if "*" in pattern else [root / pattern]):
            if core == wiped or (not glob and core.is_relative_to(wiped)):
                return f"{core.relative_to(root)} is core {name} project data"
    return ""


def patch_review(patch: str, cwd: Path) -> tuple[str, list[str]]:
    """(denial reason or '', advisory notes) for an apply_patch body."""
    ops = parse_patch(patch)
    deleted = {_resolve(cwd, p) for op, p in ops if op == "Delete"}
    notes = []
    current = None
    for op, p in ops:
        path = _resolve(cwd, p)
        if op != "Delete" and path.suffix.lower() in BINARY_ASSETS:
            return f"{p} is a binary engine asset; it can't be edited as a text patch. Change it in the editor.", []
        project = detect(path)
        if op == "Update":
            current = path
        if op in ("Add", "Update", "Move") and project:
            reason = generated_reason(project, path)
            if reason:
                return f"{p} is generated ({reason}). Edit the source instead.", []
        if op == "Update" and path.suffix in (".luau", ".lua") and path.is_file() and dialogue_header(path):
            return (f"{p} is built from the Markdown docs in {dialogue_header(path)[0]}. Change the docs and run "
                    "build_dialogue (roblox-forge) or story.py build again."), []
        if not project or project.engine != "unity":
            continue
        meta = Path(str(path) + ".meta")
        if op == "Delete" and path.suffix == ".meta":
            asset = Path(str(path)[:-5])
            if asset.exists() and asset not in deleted:
                return f"Deleting {p} without its asset orphans the asset's GUID and breaks every reference to it.", []
        elif op == "Delete" and meta.exists() and meta not in deleted:
            notes.append(f"Also delete {p}.meta, or Unity will log a missing-asset warning.")
        elif op == "Add" and path.suffix == ".meta":
            notes.append(f"Unity generates {path.name} when it imports the asset; a hand-written .meta invents a GUID. Let Unity create it.")
        elif op == "Move" and current is not None:
            if Path(str(current) + ".meta").exists():
                notes.append(f"Move {current.name}.meta next to {p} too, or Unity assigns a new GUID and references break.")
    return "", notes


# ---------------------------------------------------------------- events

def describe(project: Project) -> str:
    spec = ENGINES[project.engine]
    version = f" {project.version}" if project.version else ""
    lines = [f"{spec['name']}{version} project at {project.root}."]
    lines += [f"- {c}" for c in spec["context"]]
    return "\n".join(lines)


def on_session_start(event: dict) -> Optional[dict]:
    projects = detect_all(Path(event.get("cwd") or os.getcwd()))
    if not projects:
        return None
    context = "Game project rules (from game_hooks):\n" + "\n".join(describe(p) for p in projects[:5])
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}


def on_user_prompt_submit(event: dict) -> Optional[dict]:
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or not CREATIVE_VERB_RE.search(prompt):
        return None
    game, level, polish = GAME_REQUEST_RE.search(prompt), LEVEL_RE.search(prompt), POLISH_RE.search(prompt)
    narrative = STORY_RE.search(prompt)
    if not game and not level and not polish and not narrative:
        return None
    projects = detect_all(Path(event.get("cwd") or os.getcwd()))
    roblox = bool(ROBLOX_RE.search(prompt)) or any(p.engine == "roblox" for p in projects)
    briefs = []
    if game or (level and projects):  # level and mechanic words mean a game only inside a game project
        briefs.append(CREATIVE_BRIEF)
        if roblox:
            briefs.append(ROBLOX_BRIEF)
    if polish and roblox:
        briefs.append(POLISH_BRIEF)
    if narrative and roblox:
        briefs.append(STORY_BRIEF)
    if not briefs:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(briefs)}}


def on_pre_tool_use(event: dict) -> Optional[dict]:
    cwd = Path(event.get("cwd") or os.getcwd())
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return None
    if event.get("tool_name") == "apply_patch":
        reason, notes = patch_review(command, cwd)
    elif event.get("tool_name") == "Bash":
        reason, notes = bash_denial(command, cwd), []
    else:
        return None
    if reason:
        # Codex appends ". Command: ..." after the reason, so drop a trailing period.
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": reason.rstrip(".")}}
    if notes:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n".join(notes)}}
    return None


def _report(issues: list[Issue]) -> str:
    shown = [i.render() for i in issues[:MAX_ISSUES]]
    if len(issues) > MAX_ISSUES:
        shown.append(f"... and {len(issues) - MAX_ISSUES} more")
    return "\n".join(shown)


def on_post_tool_use(event: dict) -> Optional[dict]:
    if event.get("tool_name") != "apply_patch":
        return None
    cwd = Path(event.get("cwd") or os.getcwd())
    tool_input = event.get("tool_input")
    patch = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(patch, str):
        return None
    issues: list[Issue] = []
    seen = set()
    for op, p in parse_patch(patch):
        path = _resolve(cwd, p)
        if op != "Delete" and path not in seen:
            seen.add(path)
            issues += check_file(path, cwd)
    if not issues:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": "Engine checks on the patched files:\n" + _report(issues)}}


def changed_files(cwd: Path) -> list[Path]:
    try:
        top = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        if top.returncode:
            return []
        root = Path(top.stdout.strip())
        status = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    entries = status.stdout.split("\0")
    files = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, name = entry[:2], entry[3:]
        if code[0] in "RC":
            i += 1  # the next entry is the rename source
        if "D" not in code:
            files.append(root / name)
    return files[:MAX_STOP_FILES]


def on_stop(event: dict) -> Optional[dict]:
    if event.get("stop_hook_active"):
        return None  # already asked once this turn; never loop
    cwd = Path(event.get("cwd") or os.getcwd())
    changed = changed_files(cwd)
    errors = [i for f in changed for i in check_file(f, cwd) if i.level == "error"]
    errors += stale_dialogue(cwd, changed)
    unfinished = unfinished_issues(cwd)
    parts = []
    if errors:
        parts.append("Engine checks found errors in changed files:\n" + _report(errors))
    if unfinished:
        parts.append("Lines added since the last commit look unfinished or generic:\n" + _report(unfinished))
    if not parts:
        return None
    return {"decision": "block", "reason": "\n".join(parts) + "\nFix them, or tell the user why they should stay."}


HANDLERS = {"SessionStart": on_session_start, "UserPromptSubmit": on_user_prompt_submit,
            "PreToolUse": on_pre_tool_use, "PostToolUse": on_post_tool_use, "Stop": on_stop}


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    handler = HANDLERS.get(args[0]) if args else None
    if handler is None:
        print(f"usage: game_hooks.py {{{'|'.join(HANDLERS)}}}", file=sys.stderr)
        return 0
    try:
        event = json.load(sys.stdin)
        result = handler(event) if isinstance(event, dict) else None
    except Exception as e:  # fail open: a hook bug must never block the agent
        print(f"game_hooks: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if result:
        json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
