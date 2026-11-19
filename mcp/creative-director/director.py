"""creative-director tool logic: checks that keep game and software work specific instead of generic.

Standard library only, so every function is testable without the MCP SDK. server.py exposes these
as MCP tools. Results are compact dicts: "ok", then findings, then short notes. All checks are
heuristics with fixed word lists; they find likely problems for the agent to judge, not proof.
"""
from __future__ import annotations

import random
import re
import secrets
from pathlib import Path

MAX_FINDINGS = 60
MAX_FILE_BYTES = 1_000_000
SKIP_DIRS = {".git", "node_modules", "Packages", "ServerPackages", "DevPackages", "Library", "Temp", "Binaries",
             "Intermediate", "DerivedDataCache", "Saved", ".godot", ".import", "target", "dist", "build",
             "__pycache__", ".venv", "venv"}
PROSE_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
TEXT_SUFFIXES = PROSE_SUFFIXES | {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".lua", ".luau", ".gd", ".cs", ".cpp", ".cc", ".h", ".hpp",
    ".rs", ".go", ".java", ".kt", ".swift", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
}

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

# Phrases that describe a game or product without saying anything specific.
VAGUE_PHRASES = (
    "fun and engaging", "engaging gameplay", "addictive gameplay", "immersive experience", "unique gameplay",
    "unique experience", "stunning visuals", "breathtaking", "endless possibilities", "something for everyone",
    "players will love", "exciting adventure", "epic battles", "rich story", "deep mechanics", "next level",
    "captivating", "cutting-edge", "game-changer", "unleash", "embark on", "delve", "tapestry",
    "testament to", "a world where", "look no further", "unlock the full potential", "in today's fast-paced",
)
VAGUE_RE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in VAGUE_PHRASES) + r")", re.I)

# A design doc should answer these; each is found by a heading (or **Label:**) that matches the pattern.
FIRST_MINUTE = r"first (?:minute|session|30|thirty|60|sixty|level)|onboarding|tutorial|opening"
SCOPE = r"scope|mvp|milestone|\bcut\b|later|backlog"
DESIGN_SECTIONS = (
    ("fantasy", r"fantasy|pitch|premise|concept|logline|elevator", "who the player is and what they get to do"),
    ("core_loop", r"core loop|gameplay loop|\bloops?\b", "the repeated verbs and what each cycle rewards"),
    ("hook", r"hook|twist|unique|different|\busp\b", "the one thing a player would describe to a friend"),
    ("controls", r"control|input", "every input and what it does"),
    ("win_fail", r"\bwin|\bfail|\blose|goal|objective|game over|victory|death", "how a run or round ends, both ways"),
    ("first_minute", FIRST_MINUTE, "what happens in the first minute of play"),
    ("feedback", r"feedback|juice|game feel|\bfeel\b|polish", "what the player sees and hears on each action"),
    ("progression", r"progression|difficulty|economy|upgrade|levels?\b|pacing", "how it changes over time"),
    ("scope", SCOPE, "what ships first and what waits"),
)
# A Roblox brief (skills/roblox-game-design/assets/roblox-brief.md) answers these instead.
ROBLOX_SECTIONS = (
    ("hook", r"hook|twist|pitch|premise|concept|logline", "the one sentence a player would tell a friend"),
    ("first_minute", FIRST_MINUTE, "what a new player sees, does, and earns in the first 60 seconds"),
    ("loops", r"\bloops?\b|retention|reason to return", "the short, session, and long loops, and the reason to return"),
    ("social", r"social|multiplayer|co-?op|friends|party|together|trading", "why playing with others is better"),
    ("devices", r"device|touch|mobile|phone|console", "which devices it targets, phones included"),
    ("controls", r"control|input", "every action on touch, keyboard and mouse, and gamepad"),
    ("comparables", r"closest|comparable|existing experiences|similar|inspiration|competitor",
     "the closest existing experiences and how this one differs"),
    ("monetization", r"moneti[sz]|game pass|developer product|robux|\bshop\b",
     "what is sold, for how much, and why it is fair"),
    ("scope", SCOPE, "what ships first and what waits"),
)
SECTIONS = {"game": DESIGN_SECTIONS, "roblox": ROBLOX_SECTIONS}
RANDOM_ITEM_RE = re.compile(r"loot ?box|\bcrates?\b|\beggs?\b|gacha|\bspins?\b|mystery box|random (?:items?|rewards?|pets?)",
                            re.I)
PERCENT_RE = re.compile(r"\d(?:\.\d+)?\s?%")
BOLD_LABEL_RE = re.compile(r"\*\*([^*\n]{1,40}?):\*\*")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$|^(.+)\n(?:=+|-+)\s*$", re.M)
LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s", re.M)
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:\s?(?:%|s|ms|px|m|hp|x)\b)?")

# Ingredients for concept_seeds. Each list is specific enough to suggest a mechanic, not a mood board.
VERBS = (
    "grapple", "stack", "herd", "rewind", "paint", "trade", "dig", "deflect", "tether", "possess", "launch", "sneak",
    "cook", "repair", "map", "juggle", "pilot", "grow", "echolocate", "swap places", "magnetize", "carve",
    "build bridges", "ring bells",
)
TWISTS = (
    "enemies move only when you move", "the arena shrinks every 30 seconds", "you see only what you have lit",
    "your score is also your health", "gravity flips on every fourth beat", "the level keeps the scars of your last run",
    "a second player controls the camera", "you play the boss defending the final room", "you can carry one thing",
    "every sound you make reveals you and your enemies", "each coin you spend rebuilds part of the level",
    "the tutorial lies and the player learns to doubt it", "you lose an ability each time you use it",
    "the map is drawn by where you have walked", "enemies copy your last ten seconds of moves",
    "the world is a single screen that rotates", "time pauses while you aim", "you win by being forgotten",
    "every room is the same room, changed", "your weapon is the level geometry", "you share one body with a rival",
    "rescued characters become new tools", "the soundtrack is the timer", "failure leaves a ghost that helps you",
)
SETTINGS = (
    "a night market on a whale's back", "a lighthouse in a storm", "a museum after closing", "a sinking clock tower",
    "a desert post office", "a laundromat in orbit", "a city grown from coral", "a snowed-in ski lodge",
    "a freight train crossing a canyon", "the inside of a sleeping giant", "a greenhouse on Mars",
    "a flooded subway line", "a mountain monastery that brews tea", "a carnival that only opens during eclipses",
    "a library where books are alive", "a tiny kitchen at dinner rush", "a radio station at the end of the world",
    "a fungus forest under a parking lot", "an airship hauling mail", "a toy shop after the owner left",
)
FEELINGS = (
    "tense", "cozy", "frantic", "mischievous", "lonely", "triumphant", "eerie", "playful", "precise", "chaotic",
    "melancholy", "clever",
)


def _capped(items: list) -> tuple[list, int]:
    return items[:MAX_FINDINGS], max(0, len(items) - MAX_FINDINGS)


def _is_test_path(path: Path) -> bool:
    name = path.name.lower()
    return (name.startswith("test_") or ".test." in name or ".spec." in name or name.endswith("_test.py")
            or any(part.lower() in {"test", "tests", "__tests__", "spec", "fixtures"} for part in path.parts))


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def _iter_files(paths: list[str]) -> tuple[list[Path], list[str]]:
    files, missing = [], []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                rel = child.relative_to(p).parts
                if child.is_file() and not any(part in SKIP_DIRS for part in rel[:-1]) \
                        and child.suffix.lower() in TEXT_SUFFIXES and not child.name.endswith((".min.js", ".lock")):
                    files.append(child)
        else:
            missing.append(raw)
    return files, missing


def scan_text(text: str, prose: bool) -> list[dict]:
    """Findings for one file's text: unfinished-work rules always, vague phrases only in prose."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for rule, pattern, message in UNFINISHED_RULES:
            if pattern.search(line):
                found.append({"line": number, "rule": rule, "message": message, "text": line.strip()[:160]})
        if prose:
            for m in VAGUE_RE.finditer(line):
                found.append({"line": number, "rule": "vague-phrase",
                              "message": f"'{m.group(0)}' says nothing specific; describe what the player sees or does",
                              "text": line.strip()[:160]})
    return found


# ---------------------------------------------------------------------------------------------
def find_slop(paths: list[str], include_tests: bool = False) -> dict:
    """Scan files or folders for unfinished work (filler text, stubs, placeholder text, generic titles) and,
    in prose files, vague marketing phrases. Test files are skipped unless include_tests is true."""
    files, missing = _iter_files(paths)
    findings = []
    scanned = 0
    for path in files:
        if not include_tests and _is_test_path(path):
            continue
        text = _read(path)
        if text is None:
            continue
        scanned += 1
        for f in scan_text(text, prose=path.suffix.lower() in PROSE_SUFFIXES):
            findings.append({"path": str(path), **f})
    shown, more = _capped(findings)
    result = {"ok": not findings and not missing, "files_scanned": scanned, "findings": shown}
    if more:
        result["more"] = more
    if missing:
        result["missing"] = missing
    return result


# ---------------------------------------------------------------------------------------------
def review_design(text: str | None = None, path: str | None = None, platform: str = "game") -> dict:
    """Check a game design doc for the decisions a team needs before building, vague phrases, and tuning numbers.
    platform "roblox" checks for the sections of a Roblox brief instead, and for odds on random items."""
    if (text is None) == (path is None):
        return {"ok": False, "error": "pass exactly one of text or path"}
    if platform not in SECTIONS:
        return {"ok": False, "error": f"platform must be one of: {', '.join(SECTIONS)}"}
    if path is not None:
        text = _read(Path(path).expanduser())
        if text is None:
            return {"ok": False, "error": f"cannot read {path} as text"}
    found = [(m.start(), (m.group(1) or m.group(2)).strip()) for m in HEADING_RE.finditer(text)]
    found += [(m.start(), m.group(1).strip()) for m in BOLD_LABEL_RE.finditer(text)]
    headings = [h for _, h in sorted(found)]
    sections, missing = {}, []
    for key, pattern, question in SECTIONS[platform]:
        match = next((h for h in headings if re.search(pattern, h, re.I)), None)
        sections[key] = match
        if match is None:
            missing.append({"section": key, "answers": question})
    vague = [f for f in scan_text(text, prose=True) if f["rule"] == "vague-phrase"]
    unfinished = scan_text(text, prose=False)
    numbers = len(NUMBER_RE.findall(LIST_MARKER_RE.sub("", text)))
    notes = []
    if not headings:
        notes.append("No headings found; give each decision its own heading so it can be found and checked.")
    if numbers < 5:
        notes.append(f"Only {numbers} numbers; add tuning values (speeds, timings, costs, counts) the build can use.")
    if platform == "roblox" and RANDOM_ITEM_RE.search(text) and not PERCENT_RE.search(text):
        notes.append("Random items are mentioned but no odds are given. If players pay for them, list every outcome "
                     "with odds summing to 100% (roblox-forge check_odds verifies them).")
    shown_vague, _ = _capped(vague)
    return {"ok": not missing and not vague and not unfinished and numbers >= 5, "sections": sections,
            "missing": missing, "vague": shown_vague, "unfinished": unfinished[:MAX_FINDINGS], "numbers": numbers,
            "notes": notes}


# ---------------------------------------------------------------------------------------------
def concept_seeds(count: int = 3, seed: int | None = None, genre: str | None = None) -> dict:
    """Random, reproducible concept prompts (verb, twist, setting, feeling) for brainstorming past the first idea."""
    if not 1 <= count <= 10:
        return {"ok": False, "error": "count must be between 1 and 10"}
    seed = secrets.randbelow(2**31) if seed is None else seed
    rng = random.Random(seed)
    verbs, twists, settings = rng.sample(VERBS, count), rng.sample(TWISTS, count), rng.sample(SETTINGS, count)
    concepts = [{"verb": verbs[i], "twist": twists[i], "setting": settings[i], "feeling": rng.choice(FEELINGS)}
                for i in range(count)]
    use = ("Treat each as a constraint set, not a finished idea. For each, write one sentence of what the player "
           "does in the first ten seconds. Keep the one with the clearest verb and the strongest twist, then drop or "
           "replace the parts that don't fit the user's request.")
    if genre:
        use += f" Fit it to the requested genre: {genre}."
    return {"ok": True, "seed": seed, "concepts": concepts, "how_to_use": use}
