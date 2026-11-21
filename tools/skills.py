#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6"]
# ///
"""Validate, scaffold, build, and install skills for every supported agent platform.

Shared skills live in skills/<category>/<name>/. A platform folder,
platforms/<platform>/skills/<category>/<name>/, either overrides a shared skill (files replace or add
to it; frontmatter.yaml merges into its frontmatter) or, when no shared skill has that name, defines a
skill for that platform only. Each category folder has a README.md that says what it is for. Skill
names are unique across categories, because every platform installs skills into one flat folder.

Usage:
  tools/skills.py list      [-c CATEGORY ...]
  tools/skills.py validate  [--strict] [-p PLATFORM] [SKILL_DIR ...]
  tools/skills.py new NAME -c CATEGORY [-p PLATFORM]
  tools/skills.py install   [-p PLATFORM ...] [-c CATEGORY ...] [--project DIR] [NAME ...]
  tools/skills.py uninstall [-p PLATFORM ...] [-c CATEGORY ...] [--project DIR] [NAME ...]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO / "skills"
PLATFORMS_DIR = REPO / "platforms"
DIST_DIR = REPO / "dist"
TEMPLATE = REPO / "template" / "SKILL.md"
FRONTMATTER_PATCH = "frontmatter.yaml"
CATEGORY_README = "README.md"

# Agent Skills spec fields: understood by every platform below and by claude.ai uploads.
SPEC_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

# user/project: install folders relative to $HOME and to a project root.
# keys: frontmatter fields only this platform understands.
PLATFORMS = {
    "claude": {
        "user": ".claude/skills", "project": ".claude/skills",
        "keys": {"when_to_use", "argument-hint", "arguments", "disable-model-invocation",
                 "user-invocable", "disallowed-tools", "model", "effort", "context", "agent",
                 "background", "hooks", "paths", "shell"},
    },
    "codex": {
        "user": ".agents/skills", "project": ".agents/skills",
        "keys": set(),
    },
}
DEFAULT_PLATFORMS = ["claude", "codex"]

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED_NAMES = {"synced"}  # Claude Code stores claude.ai-synced skills here
PLACEHOLDER_RE = re.compile(r"\bTODO\b")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_BODY_LINES = 500
MAX_BODY_TOKENS = 5000
CHARS_PER_TOKEN = 4  # rough estimate; real tokenizers vary
CODEX_LISTING_CHARS = 8000  # Codex skill-list budget when context size is unknown

OPENAI_KEYS = {
    "interface": {"display_name", "short_description", "icon_small", "icon_large",
                  "brand_color", "default_prompt"},
    "policy": {"allow_implicit_invocation"},
    "dependencies": {"tools"},
}
OPENAI_TOOL_KEYS = {"type", "value", "description", "transport", "url"}


class Report:
    def __init__(self, skill: Path):
        self.skill = skill
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.description = ""

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def split_frontmatter(text: str) -> tuple[str, str] | None:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    return None


def check_string(r: Report, data: dict, key: str, required: bool, max_len: int | None = None) -> str | None:
    if key not in data:
        if required:
            r.error(f"frontmatter: '{key}' is required")
        return None
    value = data[key]
    if not isinstance(value, str):
        r.error(f"frontmatter: '{key}' must be a string, got {type(value).__name__}")
        return None
    if not value.strip():
        r.error(f"frontmatter: '{key}' must not be empty")
        return None
    if max_len is not None and len(value) > max_len:
        r.error(f"frontmatter: '{key}' is {len(value)} chars (max {max_len})")
    return value


def check_frontmatter(r: Report, data: dict, platform: str | None) -> None:
    allowed = SPEC_KEYS | (PLATFORMS[platform]["keys"] if platform else set())
    for key in data:
        if key in allowed:
            continue
        owners = [p for p, cfg in PLATFORMS.items() if key in cfg["keys"]]
        if owners:
            r.warn(f"frontmatter: '{key}' only works in {', '.join(owners)}; "
                   f"set it in platforms/<platform>/skills/{r.skill.parent.name}/{r.skill.name}/{FRONTMATTER_PATCH}")
        else:
            r.error(f"frontmatter: unknown key '{key}'")

    name = check_string(r, data, "name", required=True, max_len=MAX_NAME)
    if name is not None:
        if not NAME_RE.match(name):
            r.error(f"name '{name}' must be lowercase a-z, 0-9 and single hyphens, no leading/trailing hyphen")
        if name != r.skill.name:
            r.error(f"name '{name}' must match directory name '{r.skill.name}'")
        if name in RESERVED_NAMES:
            r.error(f"name '{name}' is reserved by Claude Code")

    desc = check_string(r, data, "description", required=True, max_len=MAX_DESCRIPTION)
    if desc is not None:
        r.description = desc
        if "<" in desc or ">" in desc:
            r.error("description must not contain '<' or '>'")
        if PLACEHOLDER_RE.search(desc):
            r.error("description still contains a TODO placeholder")

    check_string(r, data, "license", required=False)
    check_string(r, data, "compatibility", required=False, max_len=MAX_COMPATIBILITY)
    check_string(r, data, "allowed-tools", required=False)

    if "metadata" in data:
        meta = data["metadata"]
        if not isinstance(meta, dict):
            r.error("frontmatter: 'metadata' must be a mapping")
        else:
            for k, v in meta.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    r.error(f"metadata: '{k}' must map a string to a string (quote values like \"1.0\")")


def check_body(r: Report, body: str) -> None:
    if not body.strip():
        r.error("SKILL.md has no instructions after the frontmatter")
        return
    lines = body.count("\n") + 1
    if lines > MAX_BODY_LINES:
        r.warn(f"body is {lines} lines (keep under {MAX_BODY_LINES}; move detail to references/)")
    tokens = len(body) // CHARS_PER_TOKEN
    if tokens > MAX_BODY_TOKENS:
        r.warn(f"body is ~{tokens} tokens (keep under {MAX_BODY_TOKENS}; move detail to references/)")
    if PLACEHOLDER_RE.search(body):
        r.error("body still contains a TODO placeholder")


def check_links(r: Report, md_file: Path, text: str) -> None:
    root = r.skill.resolve()
    prose = INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))
    for target in LINK_RE.findall(prose):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
            continue
        path = target.split("#", 1)[0]
        if not path:
            continue
        resolved = (md_file.parent / path).resolve()
        rel = md_file.relative_to(r.skill)
        if root != resolved and root not in resolved.parents:
            r.error(f"{rel}: link '{target}' points outside the skill folder")
        elif not resolved.exists():
            r.error(f"{rel}: broken link '{target}'")


def check_openai_yaml(r: Report) -> None:
    path = r.skill / "agents" / "openai.yaml"
    if not path.is_file():
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        r.error(f"agents/openai.yaml: invalid YAML: {e}")
        return
    if data is None:
        return
    if not isinstance(data, dict):
        r.error("agents/openai.yaml: top level must be a mapping")
        return
    for section, value in data.items():
        if section not in OPENAI_KEYS:
            r.error(f"agents/openai.yaml: unknown section '{section}'")
            continue
        if not isinstance(value, dict):
            r.error(f"agents/openai.yaml: '{section}' must be a mapping")
            continue
        for key in value:
            if key not in OPENAI_KEYS[section]:
                r.error(f"agents/openai.yaml: unknown key '{section}.{key}'")

    interface = data.get("interface")
    if isinstance(interface, dict):
        for key, value in interface.items():
            if not isinstance(value, str):
                r.error(f"agents/openai.yaml: 'interface.{key}' must be a string")
            elif key.startswith("icon_") and not (r.skill / value).is_file():
                r.error(f"agents/openai.yaml: 'interface.{key}' file not found: {value}")

    policy = data.get("policy")
    if isinstance(policy, dict) and "allow_implicit_invocation" in policy:
        if not isinstance(policy["allow_implicit_invocation"], bool):
            r.error("agents/openai.yaml: 'policy.allow_implicit_invocation' must be true or false")

    deps = data.get("dependencies")
    if isinstance(deps, dict) and "tools" in deps:
        tools = deps["tools"]
        if not isinstance(tools, list):
            r.error("agents/openai.yaml: 'dependencies.tools' must be a list")
            return
        for i, tool in enumerate(tools):
            where = f"agents/openai.yaml: dependencies.tools[{i}]"
            if not isinstance(tool, dict):
                r.error(f"{where} must be a mapping")
                continue
            for key, value in tool.items():
                if key not in OPENAI_TOOL_KEYS:
                    r.error(f"{where}: unknown key '{key}'")
                elif not isinstance(value, str):
                    r.error(f"{where}: '{key}' must be a string")
            for key in ("type", "value"):
                if key not in tool:
                    r.error(f"{where}: '{key}' is required")


def check_scripts(r: Report) -> None:
    scripts = r.skill / "scripts"
    if not scripts.is_dir():
        return
    for f in sorted(p for p in scripts.rglob("*") if p.is_file()):
        with f.open("rb") as fh:
            has_shebang = fh.read(2) == b"#!"
        if has_shebang and not os.access(f, os.X_OK):
            r.warn(f"{f.relative_to(r.skill)}: has a shebang but is not executable (chmod +x)")


def validate_skill(skill: Path, platform: str | None = None) -> Report:
    r = Report(skill)
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        r.error("missing SKILL.md")
        return r
    text = skill_md.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if parts is None:
        r.error("SKILL.md must start with '---' on line 1 and close the frontmatter with '---'")
        return r
    raw, body = parts
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        r.error(f"frontmatter: invalid YAML: {e}")
        return r
    if not isinstance(data, dict):
        r.error("frontmatter must be a YAML mapping")
        return r

    check_frontmatter(r, data, platform)
    check_body(r, body)
    for md in sorted(skill.rglob("*.md")):
        check_links(r, md, body if md == skill_md else md.read_text(encoding="utf-8"))
    check_openai_yaml(r)
    check_scripts(r)
    return r


def subdirs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__")


def categories(root: Path | None = None) -> list[Path]:
    """Category folders under a skills root. A folder holding SKILL.md is a misplaced skill, not a category."""
    return [c for c in subdirs(root or SKILLS_DIR) if not (c / "SKILL.md").exists()]


def discover(root: Path | None = None) -> list[Path]:
    """Every skill folder under a skills root (skills/ or platforms/<platform>/skills/)."""
    return [s for c in categories(root) for s in subdirs(c)]


def index(root: Path | None = None) -> dict[str, Path]:
    """Skill name -> folder. On duplicate names the first wins; validate_all reports the clash."""
    found: dict[str, Path] = {}
    for s in discover(root):
        found.setdefault(s.name, s)
    return found


def category_of(skill: Path) -> str:
    return skill.parent.name


def overlay_root(platform: str) -> Path:
    return PLATFORMS_DIR / platform / "skills"


def overlay_dir(platform: str, name: str) -> Path | None:
    return index(overlay_root(platform)).get(name)


def overlay_names(platform: str) -> list[str]:
    return sorted(index(overlay_root(platform)))


def skill_category(platform: str | None, name: str) -> str | None:
    src = index().get(name) or (overlay_dir(platform, name) if platform else None)
    return category_of(src) if src else None


def platform_skill_names(platform: str) -> list[str]:
    return sorted(set(index()) | set(overlay_names(platform)))


class BuildError(Exception):
    pass


def apply_frontmatter_patch(skill_md: Path, patch_file: Path) -> None:
    try:
        patch = yaml.safe_load(patch_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise BuildError(f"{FRONTMATTER_PATCH}: invalid YAML: {e}")
    if patch is None:
        return
    if not isinstance(patch, dict):
        raise BuildError(f"{FRONTMATTER_PATCH} must be a YAML mapping")
    parts = split_frontmatter(skill_md.read_text(encoding="utf-8")) if skill_md.is_file() else None
    if parts is None:
        raise BuildError(f"{FRONTMATTER_PATCH}: the shared SKILL.md has no valid frontmatter to merge into")
    try:
        data = yaml.safe_load(parts[0])
    except yaml.YAMLError as e:
        raise BuildError(f"{FRONTMATTER_PATCH}: the shared SKILL.md frontmatter is invalid YAML: {e}")
    if not isinstance(data, dict):
        raise BuildError(f"{FRONTMATTER_PATCH}: the shared SKILL.md frontmatter is not a mapping")
    for key, value in patch.items():
        if value is None:
            data.pop(key, None)  # `key:` with no value removes the shared key
        else:
            data[key] = value
    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=10000)
    skill_md.write_text(f"---\n{dumped}---\n{parts[1]}", encoding="utf-8")


def build_skill(platform: str, name: str, dest_root: Path) -> Path:
    """Write the platform's variant of a skill to dest_root/name: the shared skill plus its overrides."""
    shared = index().get(name)
    overlay = overlay_dir(platform, name)
    if overlay is None:
        raise BuildError(f"platforms/{platform}/skills has no override for '{name}'")
    if shared is not None and category_of(shared) != category_of(overlay):
        raise BuildError(f"override is in category '{category_of(overlay)}' but the shared skill is in "
                         f"'{category_of(shared)}'; move it to platforms/{platform}/skills/{category_of(shared)}/{name}")
    patch = overlay / FRONTMATTER_PATCH
    if patch.is_file() and (overlay / "SKILL.md").is_file():
        raise BuildError(f"override has both SKILL.md and {FRONTMATTER_PATCH}; keep one")
    if patch.is_file() and shared is None:
        raise BuildError(f"{FRONTMATTER_PATCH} needs a shared skill to merge into, but skills/*/{name} does not exist")

    dest = dest_root / name
    if dest.is_symlink():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    if shared is not None:
        shutil.copytree(shared, dest, symlinks=True)
    else:
        dest.mkdir(parents=True)
    for src in sorted(overlay.rglob("*")):
        rel = src.relative_to(overlay)
        if rel == Path(FRONTMATTER_PATCH):
            continue
        target = dest / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    if patch.is_file():
        apply_frontmatter_patch(dest / "SKILL.md", patch)
    return dest


def check_layout(root: Path, label: str) -> list[tuple[str, Report]]:
    """Category READMEs, skills placed outside a category, and names used twice."""
    reports = []
    for folder in subdirs(root):
        if (folder / "SKILL.md").exists():
            r = Report(folder)
            r.error(f"{label}/{folder.name} is a skill outside any category; move it to {label}/<category>/{folder.name}")
            reports.append((f"{label}/{folder.name}", r))
    seen: dict[str, Path] = {}
    for c in categories(root):
        r = Report(c)
        readme = c / CATEGORY_README
        if root == SKILLS_DIR:
            if not NAME_RE.match(c.name):
                r.error(f"category name '{c.name}' must be lowercase a-z, 0-9 and single hyphens")
            if not readme.is_file():
                r.error(f"missing {CATEGORY_README} saying what the category is for")
            elif PLACEHOLDER_RE.search(readme.read_text(encoding="utf-8")):
                r.error(f"{CATEGORY_README} still contains a TODO placeholder")
            if not subdirs(c) and not any(subdirs(overlay_root(p) / c.name) for p in PLATFORMS):
                r.warn("category has no skills")
        elif not (SKILLS_DIR / c.name / CATEGORY_README).is_file():
            r.error(f"category '{c.name}' is not defined; add skills/{c.name}/{CATEGORY_README}")
        for s in subdirs(c):
            if s.name in seen:
                r.error(f"skill name '{s.name}' is also used by {seen[s.name].relative_to(root)}; names must be unique")
            seen.setdefault(s.name, s)
        if r.errors or r.warnings:
            reports.append((f"{label}/{c.name}", r))
    return reports


def validate_all(tmp: Path) -> list[tuple[str, Report]]:
    reports = [(s.name, validate_skill(s)) for s in discover()]
    reports += check_layout(SKILLS_DIR, "skills")
    for folder in subdirs(PLATFORMS_DIR):
        if folder.name not in PLATFORMS:
            r = Report(folder)
            r.error(f"platforms/{folder.name} is not a supported platform ({', '.join(PLATFORMS)})")
            reports.append((folder.name, r))
    for platform in PLATFORMS:
        reports += check_layout(overlay_root(platform), f"platforms/{platform}/skills")
        for name in overlay_names(platform):
            label = f"{platform}/{name}"
            try:
                built = build_skill(platform, name, tmp / platform)
            except BuildError as e:
                r = Report(overlay_dir(platform, name) or overlay_root(platform))
                r.error(str(e))
                reports.append((label, r))
                continue
            reports.append((label, validate_skill(built, platform)))
    return reports


def cmd_validate(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        if args.paths:
            reports = [(Path(p).name, validate_skill(Path(p), args.platform)) for p in args.paths]
        else:
            reports = validate_all(Path(tmp))
    if not reports:
        print("No skills found.")
        return 0
    errors = warnings = 0
    for label, r in reports:
        status = "FAIL" if r.errors else ("WARN" if r.warnings else "ok")
        print(f"{status:4}  {label}")
        for msg in r.errors:
            print(f"      error: {msg}")
        for msg in r.warnings:
            print(f"      warn:  {msg}")
        errors += len(r.errors)
        warnings += len(r.warnings)
    if not args.paths:
        codex_overrides = set(overlay_names("codex"))
        total = sum(len(r.description) for label, r in reports
                    if label.startswith("codex/") or ("/" not in label and label not in codex_overrides))
        if total > CODEX_LISTING_CHARS:
            print(f"warn: Codex skill descriptions total {total} chars; Codex may trim its skill list past {CODEX_LISTING_CHARS}")
            warnings += 1
    print(f"\n{len(reports)} skill(s), {errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


def cmd_new(args: argparse.Namespace) -> int:
    name = args.name
    if not NAME_RE.match(name) or len(name) > MAX_NAME or name in RESERVED_NAMES:
        print(f"error: invalid skill name '{name}'", file=sys.stderr)
        return 1
    category = args.category
    if not NAME_RE.match(category):
        print(f"error: invalid category name '{category}'", file=sys.stderr)
        return 1
    shared = index().get(name)
    if shared is not None:
        if args.platform:
            print(f"error: {shared.relative_to(REPO)} is shared; to change it for {args.platform}, add files to "
                  f"platforms/{args.platform}/skills/{category_of(shared)}/{name}/ (see AGENTS.md)", file=sys.stderr)
        else:
            print(f"error: {shared.relative_to(REPO)} already exists", file=sys.stderr)
        return 1
    taken = next((overlay_dir(p, name) for p in PLATFORMS if overlay_dir(p, name)), None)
    if taken is not None:
        print(f"error: {taken.relative_to(REPO)} already uses that name", file=sys.stderr)
        return 1
    readme = SKILLS_DIR / category / CATEGORY_README
    if not readme.is_file():
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(f"# {category}\n\nTODO: one sentence on what this category is for and who uses it.\n",
                          encoding="utf-8")
        print(f"Created new category {readme.relative_to(REPO)}; replace its TODO")
    dest = (overlay_root(args.platform) if args.platform else SKILLS_DIR) / category / name
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(TEMPLATE.read_text(encoding="utf-8").replace("{{name}}", name), encoding="utf-8")
    print(f"Created {dest.relative_to(REPO)}/SKILL.md; replace every TODO, then run: tools/skills.py validate")
    return 0


def selected_platforms(args: argparse.Namespace) -> list[str]:
    chosen = args.platform or DEFAULT_PLATFORMS
    return list(PLATFORMS) if "all" in chosen else list(dict.fromkeys(chosen))


def target_dir(platform: str, args: argparse.Namespace) -> Path:
    if args.project:
        return Path(args.project).expanduser().resolve() / PLATFORMS[platform]["project"]
    return Path.home() / PLATFORMS[platform]["user"]


def is_ours(link: Path) -> bool:
    if not link.is_symlink():
        return False
    target = link.resolve()
    return any(root.resolve() in target.parents for root in (SKILLS_DIR, DIST_DIR))


def known_categories() -> set[str]:
    return {c.name for c in categories()} | {c.name for p in PLATFORMS for c in categories(overlay_root(p))}


def check_categories(args: argparse.Namespace) -> bool:
    unknown = [c for c in (args.category or []) if c not in known_categories()]
    if unknown:
        print(f"error: no such category: {', '.join(unknown)} (have: {', '.join(sorted(known_categories()))})",
              file=sys.stderr)
        return False
    return True


def in_categories(platform: str, name: str, args: argparse.Namespace) -> bool:
    return not args.category or skill_category(platform, name) in args.category


def cmd_install(args: argparse.Namespace) -> int:
    if not check_categories(args):
        return 1
    platforms = selected_platforms(args)
    available = {p: [n for n in platform_skill_names(p) if in_categories(p, n, args)] for p in platforms}
    unknown = [n for n in args.names if not any(n in names for names in available.values())]
    if unknown:
        where = f" in {', '.join(args.category)}" if args.category else ""
        print(f"error: no such skill(s) for {', '.join(platforms)}{where}: {', '.join(unknown)}", file=sys.stderr)
        return 1

    # Build and validate everything before touching any install folder.
    sources: dict[str, dict[str, Path]] = {}
    failed = []
    for p in platforms:
        sources[p] = {}
        for name in available[p]:
            if args.names and name not in args.names:
                continue
            try:
                variant = name in overlay_names(p)
                src = build_skill(p, name, DIST_DIR / p) if variant else index()[name]
            except BuildError as e:
                failed.append(f"{p}/{name} ({e})")
                continue
            if validate_skill(src, p if variant else None).errors:
                failed.append(f"{p}/{name}" if variant else name)
            sources[p][name] = src
    if failed:
        print(f"error: fix validation errors first: {', '.join(sorted(set(failed)))}", file=sys.stderr)
        return 1

    status = 0
    for p in platforms:
        target = target_dir(p, args)
        target.mkdir(parents=True, exist_ok=True)
        for name, src in sources[p].items():
            link = target / name
            if link.is_symlink() and link.resolve() == src.resolve():
                print(f"exists   {link}")
                continue
            if is_ours(link):
                link.unlink()
            elif link.exists() or link.is_symlink():
                print(f"skipped  {link} (already exists and is not from this repo)", file=sys.stderr)
                status = 1
                continue
            link.symlink_to(src.resolve(), target_is_directory=True)
            print(f"linked   {link} -> {src.resolve()}")
    if any(n in overlay_names(p) for p in platforms for n in sources[p]):
        print("note: platform variants are copies in dist/; run install again after editing or pulling")
    return status


def cmd_uninstall(args: argparse.Namespace) -> int:
    if not check_categories(args):
        return 1
    for p in selected_platforms(args):
        target = target_dir(p, args)
        if not target.is_dir():
            continue
        links = [target / n for n in args.names] if args.names else sorted(target.iterdir())
        for link in links:
            if is_ours(link) and in_categories(p, link.name, args):
                link.unlink()
                print(f"removed  {link}")
    return 0


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]


def read_description(skill: Path) -> str:
    parts = split_frontmatter((skill / "SKILL.md").read_text(encoding="utf-8")) if (skill / "SKILL.md").is_file() else None
    try:
        data = yaml.safe_load(parts[0]) if parts else None
    except yaml.YAMLError:
        data = None
    return str(data.get("description", "")) if isinstance(data, dict) else ""


def cmd_list(args: argparse.Namespace) -> int:
    if not check_categories(args):
        return 1
    rows: dict[str, list[tuple[str, str, str]]] = {}
    for name in sorted(set(index()) | {n for p in PLATFORMS for n in overlay_names(p)}):
        src = index().get(name)
        only = [p for p in PLATFORMS if src is None and overlay_dir(p, name)]
        src = src or overlay_dir(only[0], name)
        if args.category and category_of(src) not in args.category:
            continue
        rows.setdefault(category_of(src), []).append((name, ", ".join(only), first_sentence(read_description(src))))
    for category in sorted(rows):
        readme = SKILLS_DIR / category / CATEGORY_README
        about = ""
        if readme.is_file():
            body = [l for l in readme.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
            about = f" — {first_sentence(body[0])}" if body else ""
        print(f"{category}{about}")
        for name, only, desc in rows[category]:
            tag = f" [{only} only]" if only else ""
            print(f"  {name}{tag}: {desc}")
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show skills grouped by category")
    p.add_argument("-c", "--category", action="append", help="repeatable; only these categories")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("validate", help="check shared skills and every platform variant")
    p.add_argument("paths", nargs="*", help="standalone skill directories (default: skills/ and platforms/)")
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")
    p.add_argument("-p", "--platform", choices=list(PLATFORMS), help="with paths: allow this platform's frontmatter keys")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("new", help="scaffold a skill from the template")
    p.add_argument("name")
    p.add_argument("-c", "--category", required=True,
                   help="folder under skills/ (for example game-dev); a new name creates the category")
    p.add_argument("-p", "--platform", choices=list(PLATFORMS), help="create a skill for this platform only")
    p.set_defaults(func=cmd_new)

    for cmd, func, verb in (("install", cmd_install, "symlink"), ("uninstall", cmd_uninstall, "remove symlinks for")):
        p = sub.add_parser(cmd, help=f"{verb} skills in each platform's skill folder")
        p.add_argument("names", nargs="*", help="skill names (default: all)")
        p.add_argument("-p", "--platform", action="append", choices=[*PLATFORMS, "all"],
                       help=f"repeatable; default: {' '.join(DEFAULT_PLATFORMS)}")
        p.add_argument("-c", "--category", action="append", help="repeatable; only skills in these categories")
        p.add_argument("--project", metavar="DIR", help="use the project folders under DIR instead of $HOME")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
