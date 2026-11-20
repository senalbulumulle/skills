"""roblox-forge story tools: review Markdown story docs and build dialogue, voiceover, and localization files.

The parsing and building live in the roblox-narrative skill's scripts/story.py, so the skill works without this
server. This module adds the creative-director checks for unfinished text (filler, stand-in lines, generic
titles), which block a build like any other high finding, and copies DialogueRunner.luau next to a new build.
"""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "skills" / "roblox-narrative"
RUNNER = SKILL / "assets" / "DialogueRunner.luau"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


story = _load("story", SKILL / "scripts" / "story.py")
director = _load("director", REPO / "mcp" / "creative-director" / "director.py")


def _unfinished(docs: Path) -> list[dict]:
    if not docs.is_dir():
        return []
    findings = []
    for path in sorted(docs.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for f in director.scan_text(text, prose=True):
            findings.append({"severity": "low" if f["rule"] == "vague-phrase" else "high",
                             "where": f"{path.relative_to(docs).as_posix()}:{f['line']}",
                             "issue": f"{f['message']}: {f['text']}"})
    return findings


def review_story(path: str) -> dict:
    docs = Path(path).expanduser().resolve()
    result = story.review(docs)
    extra = _unfinished(docs)
    if extra:
        findings = sorted(result["findings"] + extra, key=lambda f: story.SEVERITY[f["severity"]])
        result = {**result, "ok": not any(f["severity"] in ("high", "medium") for f in findings), "findings": findings}
    return result


def _blocked(path: str) -> dict | None:
    high = [f for f in _unfinished(Path(path).expanduser().resolve()) if f["severity"] == "high"]
    if high:
        return {"ok": False, "error": f"fix the {len(high)} high findings first", "findings": high}
    return None


def build_dialogue(path: str, out: str) -> dict:
    result = _blocked(path) or story.build(path, out)
    if result["ok"]:
        runner = Path(result["wrote"]).parent / "DialogueRunner.luau"
        if runner.exists():
            result["runner"] = f"kept the existing {runner.name}"
        else:
            shutil.copyfile(RUNNER, runner)
            result["runner"] = f"wrote {runner}"
    return result


def export_voiceover(path: str, out: str) -> dict:
    return _blocked(path) or story.voiceover(path, out)


def export_localization(path: str, out: str, locales: list[str] | None = None) -> dict:
    return _blocked(path) or story.localization(path, out, locales)
