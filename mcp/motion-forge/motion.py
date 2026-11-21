"""motion-forge tool logic: a catalog of dependency-free Web Components for motion-rich web UI (WebGL, 3D,
scroll, tactile, and text effects), a showcase builder, and an audit for motion code that janks, ignores
reduced motion, or takes over scrolling.

Standard library only, so every function is testable without the MCP SDK. server.py exposes these as MCP
tools. Results are compact dicts: "ok", then the data, then short notes. The audit is a heuristic with
fixed patterns; it finds likely problems for the agent to judge, not proof.
"""
from __future__ import annotations

import difflib
import functools
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPONENTS = HERE / "components"
EXAMPLES = HERE / "examples"
SHOWCASE_NAME = "motion-showcase.html"
SHOWCASE_MARK = '<meta name="generator" content="motion-forge showcase">'
HERO_PARTS = ("shader-gradient", "text-scramble", "split-text", "magnetic")

FRAMEWORKS = (
    "Plain Web Components: import the module once in the browser and use the tag in HTML, React 19+, Vue, Svelte, "
    "or Angular. Attributes are strings, and a boolean attribute is on when present. React 18: write a boolean "
    'as glare="" and leave it out to turn it off. Vue: set compilerOptions.isCustomElement for tags starting with '
    "mf-. Angular: add CUSTOM_ELEMENTS_SCHEMA. Importing during server rendering is safe; elements upgrade in the "
    "browser."
)


@functools.lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))


def _entries() -> dict[str, dict]:
    return {c["name"]: c for c in _catalog()["components"]}


def _unknown(name: str) -> str:
    close = difflib.get_close_matches(name, list(_entries()), n=3)
    hint = f"did you mean {', '.join(close)}?" if close else "list_components shows every component."
    return f"unknown component '{name}'; {hint}"


def _select(names: list[str] | None) -> tuple[list[str], str | None]:
    """Names in catalog order; None, [] or ["all"] mean every component."""
    entries = _entries()
    if not names or names == ["all"]:
        return list(entries), None
    for name in names:
        if name not in entries:
            return [], _unknown(name)
    return [n for n in entries if n in names], None


def list_components(category: str | None = None) -> dict:
    cats = _catalog()["categories"]
    if category is not None and category not in cats:
        return {"ok": False, "error": f"unknown category '{category}'; use one of: {', '.join(cats)}"}
    items = [{k: c[k] for k in ("name", "tag", "category", "summary")}
             for c in _catalog()["components"] if category in (None, c["category"])]
    return {"ok": True, "categories": cats, "components": items,
            "next": "get_component returns a component's attributes, example, and source."}


def get_component(name: str, include_source: bool = True) -> dict:
    entry = _entries().get(name)
    if entry is None:
        return {"ok": False, "error": _unknown(name)}
    result = {"ok": True, **entry, "file": f"{name}.js",
              "usage": f'<script type="module" src="./components/{name}.js"></script>  or  import "./components/{name}.js";',
              "frameworks": FRAMEWORKS,
              "example": (EXAMPLES / f"{name}.html").read_text(encoding="utf-8")}
    if include_source:
        result["source"] = (COMPONENTS / f"{name}.js").read_text(encoding="utf-8")
    return result


def install_components(names: list[str], out: str, overwrite: bool = False) -> dict:
    if not names:
        return {"ok": False, "error": 'name the components to install, or pass ["all"]'}
    chosen, error = _select(names)
    if error:
        return {"ok": False, "error": error}
    dest = Path(out).expanduser().resolve()
    if dest.exists() and not dest.is_dir():
        return {"ok": False, "error": f"not a folder: {dest}"}
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    for name in chosen:
        source = (COMPONENTS / f"{name}.js").read_text(encoding="utf-8")
        target = dest / f"{name}.js"
        if target.exists():
            if target.read_text(encoding="utf-8", errors="replace") == source:
                files.append({"file": str(target), "status": "unchanged"})
                continue
            if not overwrite:
                files.append({"file": str(target), "status": "skipped: exists and differs; pass overwrite to replace it"})
                continue
            status = "replaced"
        else:
            status = "written"
        target.write_text(source, encoding="utf-8")
        files.append({"file": str(target), "status": status})
    return {"ok": not any(f["status"].startswith("skipped") for f in files), "out": str(dest), "files": files,
            "imports": [f'import "./{name}.js";' for name in chosen],
            "next": "get_component returns each component's example markup and attributes."}


PAGE_CSS = """
:root { color-scheme: dark; --mf-page-bg: #05090b; --mf-page-fg: #e8f1ef; --mf-page-muted: #8aa29d; --mf-page-line: rgb(255 255 255 / .08); --mf-page-accent: #8fd694; }
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; background: var(--mf-page-bg); color: var(--mf-page-fg); font: 16px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; -webkit-font-smoothing: antialiased; }
.mf-page { width: min(1120px, 100% - 32px); margin-inline: auto; padding-block: 16px 160px; }
.mf-page-header { padding-block: 72px 24px; }
.mf-page-hero { display: grid; align-items: end; min-height: min(86vh, 820px); padding: clamp(1.5rem, 6vw, 5rem); border-radius: 28px; color: #f4f1de; }
.mf-page-hero__copy { display: grid; gap: 1.25rem; max-width: 46rem; }
.mf-page-hero__kicker { margin: 0; font: 500 .85rem/1.4 ui-monospace, "SF Mono", Menlo, monospace; letter-spacing: .08em; text-transform: uppercase; color: var(--mf-page-accent); }
.mf-page-hero__title { margin: 0; font-size: clamp(3rem, 10vw, 7.5rem); line-height: .92; letter-spacing: -.04em; }
.mf-page-hero__lede { margin: 0; max-width: 34rem; font-size: clamp(1rem, 2vw, 1.25rem); color: rgb(244 241 222 / .82); }
.mf-page-hero__cta { display: inline-block; padding: 1rem 1.6rem; border-radius: 999px; background: #f4f1de; color: #04131a; font-weight: 600; text-decoration: none; }
.mf-page-hero__cta:focus-visible { outline: 2px solid var(--mf-page-accent); outline-offset: 4px; }
.mf-page-title { margin: 0; font-size: clamp(2rem, 6vw, 3.5rem); letter-spacing: -.03em; }
.mf-section { padding-block: 72px; border-top: 1px solid var(--mf-page-line); }
.mf-page-header + .mf-section, .mf-page-hero + .mf-section { margin-top: 72px; }
.mf-section__meta { display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; }
.mf-section__category { color: var(--mf-page-muted); font-size: .78rem; letter-spacing: .12em; text-transform: uppercase; }
.mf-section__name { margin: 0; font-size: 1.5rem; letter-spacing: -.01em; }
.mf-section__tag { color: var(--mf-page-accent); font: .9rem ui-monospace, "SF Mono", Menlo, monospace; }
.mf-section__summary { max-width: 44rem; margin: 8px 0 32px; color: var(--mf-page-muted); }
.mf-section__hint { margin: 0 0 16px; color: var(--mf-page-muted); font-size: .9rem; }
.mf-code { margin-top: 32px; }
.mf-code summary { cursor: pointer; color: var(--mf-page-muted); font-size: .9rem; }
.mf-code summary:focus-visible { outline: 2px solid var(--mf-page-accent); outline-offset: 4px; }
.mf-code pre { overflow-x: auto; margin: 12px 0 0; padding: 20px; border: 1px solid var(--mf-page-line); border-radius: 12px; background: #091216; font: .82rem/1.6 ui-monospace, "SF Mono", Menlo, monospace; color: #c9d8d4; }
"""

HINTS = {
    "shader-gradient": "Move the pointer across the field.",
    "tilt-card": "Hover the card with a mouse or pen.",
    "parallax": "Scroll past the scene.",
    "scroll-scene": "Scroll: the stage pins while the story plays.",
    "reveal": "Scroll the cards into view.",
    "magnetic": "Bring the pointer near the button, then click.",
    "spotlight": "Sweep the pointer across the cards, or tab through them.",
    "text-scramble": "Scroll the line into view.",
    "split-text": "Scroll the headline into view.",
}


def _hero(count: int) -> str:
    return f"""<mf-shader-gradient class="mf-page-hero" colors="#04131a, #0d3b4f, #1f7a6d, #8fd694, #f4f1de">
  <div class="mf-page-hero__copy">
    <p class="mf-page-hero__kicker"><mf-text-scramble trigger="load">motion-forge · {count} components</mf-text-scramble></p>
    <h1 class="mf-page-hero__title"><mf-split-text>Northlight tonight</mf-split-text></h1>
    <p class="mf-page-hero__lede">Web Components for WebGL, 3D, scroll, tactile, and text motion, shown as an aurora forecast. Every section has its markup.</p>
    <div><mf-magnetic><a class="mf-page-hero__cta" href="#shader-gradient">See each component</a></mf-magnetic></div>
  </div>
</mf-shader-gradient>"""


def build_showcase(out: str, names: list[str] | None = None) -> dict:
    chosen, error = _select(names)
    if error:
        return {"ok": False, "error": error}
    target = Path(out).expanduser().resolve()
    if target.suffix.lower() != ".html":
        target = target / SHOWCASE_NAME
    if target.exists() and SHOWCASE_MARK not in target.read_text(encoding="utf-8", errors="replace"):
        return {"ok": False, "error": f"{target} exists and is not a motion-forge showcase; choose another path"}
    hero = all(n in chosen for n in HERO_PARTS)
    entries, cats = _entries(), _catalog()["categories"]
    sources = [(COMPONENTS / f"{n}.js").read_text(encoding="utf-8").replace("</script", "<\\/script") for n in chosen]
    scripts = "\n".join(f'<script type="module">\n{s}</script>' for s in sources)
    sections = []
    for name in chosen:
        c = entries[name]
        example = (EXAMPLES / f"{name}.html").read_text(encoding="utf-8")
        sections.append(f"""<section class="mf-section" id="{name}" aria-labelledby="{name}-title">
  <div class="mf-section__meta">
    <span class="mf-section__category">{html.escape(cats[c["category"]])}</span>
    <h2 class="mf-section__name" id="{name}-title">{html.escape(name)}</h2>
    <code class="mf-section__tag">&lt;{c["tag"]}&gt;</code>
  </div>
  <p class="mf-section__summary">{html.escape(c["summary"])}</p>
  <p class="mf-section__hint">{html.escape(HINTS.get(name, ""))}</p>
  <div class="mf-demo">
{example}
  </div>
  <details class="mf-code"><summary>Markup</summary><pre><code>{html.escape(example)}</code></pre></details>
</section>""")
    top = _hero(len(_entries())) if hero else (
        '<header class="mf-page-header"><h1 class="mf-page-title">motion-forge components</h1></header>')
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{SHOWCASE_MARK}
<link rel="icon" href="data:,">
<title>motion-forge showcase</title>
<style>{PAGE_CSS}</style>
{scripts}
</head>
<body>
<main class="mf-page">
{top}
{chr(10).join(sections)}
</main>
</body>
</html>
"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return {"ok": True, "path": str(target), "components": chosen, "hero": hero,
            "next": "Open the file in a browser; it is self-contained and works offline. Serve it over http "
                    "(for example python3 -m http.server) to test it with browser automation."}


# --- audit_motion -------------------------------------------------------------------------------------

MAX_FINDINGS = 80
MAX_FILE_BYTES = 1_000_000
SKIP_DIRS = {".git", "node_modules", "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", ".output", ".astro",
             ".vercel", ".turbo", ".cache", "coverage", "vendor", "__pycache__", ".venv", "venv"}
STYLE_SUFFIXES = {".css", ".scss", ".sass", ".less"}
SCRIPT_SUFFIXES = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"}
MARKUP_SUFFIXES = {".html", ".htm", ".vue", ".svelte", ".astro"}
SUFFIXES = STYLE_SUFFIXES | SCRIPT_SUFFIXES | MARKUP_SUFFIXES

LAYOUT_PROP = (r"(?:width|height|top|right|bottom|left|inset(?:-[a-z-]+)?|margin(?:-[a-z-]+)?|padding(?:-[a-z-]+)?"
               r"|(?:min|max)-(?:width|height)|font-size|letter-spacing|line-height|border(?:-[a-z]+)?-width"
               r"|flex-basis|grid-template-(?:rows|columns))")
LAYOUT_PROP_RE = re.compile(LAYOUT_PROP, re.I)
TRANSITION_RE = re.compile(r"(?<![\w-])transition(?:-property)?\s*:\s*([^;}\n]+)", re.I)
KEYFRAMES_RE = re.compile(r"@(?:-webkit-)?keyframes\s+[\w-]+\s*\{")
KEYFRAME_LAYOUT_RE = re.compile(rf"(?<![\w-])({LAYOUT_PROP})\s*:", re.I)
MOTION_RE = re.compile(
    r"@(?:-webkit-)?keyframes\b|\brequestAnimationFrame\b|\.animate\(|\bgsap\.(?:to|from|fromTo|timeline)\b"
    r"|from\s+[\"'](?:framer-motion|motion|motion/react)[\"']|(?<![\w-])animation(?:-name)?\s*:\s*(?!none\b)[\w-]"
    r"|(?<![\w-])transition(?:-property)?\s*:[^;}\n]*\b(?:transform|translate|scale|rotate)\b")
REDUCED_RE = re.compile(r"prefers-reduced-motion|useReducedMotion|reducedMotion|MotionConfig")
NON_PASSIVE_RE = re.compile(r"addEventListener\(\s*[\"'](wheel|mousewheel|touchstart|touchmove)[\"']")
SCROLL_LISTENER_RE = re.compile(r"addEventListener\(\s*[\"']scroll[\"']|\.on\(\s*[\"']scroll[\"']")
RAF_RE = re.compile(r"\brequestAnimationFrame\b")
LOOP_STOP_RE = re.compile(r"cancelAnimationFrame|IntersectionObserver|visibilitychange|document\.hidden|visibilityState")
WEBGL_RE = re.compile(r"getContext\(\s*[\"'](?:webgl2?|experimental-webgl)[\"']")
WEBGL_ANY_RE = re.compile(r"getContext\(\s*[\"'](?:webgl2?|experimental-webgl)[\"']|WebGLRenderer|setPixelRatio")
DPR_RE = re.compile(r"devicePixelRatio")
DPR_CAP_RE = re.compile(r"Math\.min|\bmin\(|clamp")
HOVER_MEDIA_RE = re.compile(r"\((?:any-)?hover:\s*(?:hover|none)\)")
HOVER_RE = re.compile(r":hover\b")
FOCUS_RE = re.compile(r":focus(?:-visible|-within)?\b")
WILL_CHANGE_RE = re.compile(r"will-change\s*:")
WILL_CHANGE_ALL_RE = re.compile(r"(?:^|[\s,}])\*\s*\{[^}]*will-change\s*:")
STYLE_WRITE_RE = re.compile(r"\.style\.(?:top|left|right|bottom|width|height|margin\w*|padding\w*)\s*=(?!=)")

BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
LINE_COMMENT_RE = re.compile(r"(?<![:\w\"'`/\\(=])//[^\n]*")


def _blank(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def _strip_comments(text: str, suffix: str) -> str:
    text = HTML_COMMENT_RE.sub(_blank, text) if suffix in MARKUP_SUFFIXES else text
    text = BLOCK_COMMENT_RE.sub(_blank, text)
    return text if suffix in STYLE_SUFFIXES else LINE_COMMENT_RE.sub(_blank, text)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _call_text(text: str, start: int, limit: int = 600) -> str:
    """The text of a call from `start` through its closing parenthesis (or `limit` characters)."""
    open_at = text.find("(", start)
    depth = 0
    for i in range(open_at, min(len(text), open_at + limit)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i + 1]
    return text[start:start + limit]


def _block(text: str, open_brace: int) -> str:
    depth = 0
    for i in range(open_brace, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[open_brace:i + 1]
    return text[open_brace:]


def _files(paths: list[str]) -> tuple[list[tuple[Path, Path]], str | None]:
    found: list[tuple[Path, Path]] = []
    for raw in paths:
        root = Path(raw).expanduser().resolve()
        if not root.exists():
            return [], f"not found: {root}"
        if root.is_file():
            found.append((root, root.parent))
            continue
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root)
            if (f.is_file() and f.suffix.lower() in SUFFIXES and ".min." not in f.name
                    and not any(part in SKIP_DIRS for part in rel.parts[:-1])):
                found.append((f, root))
    return found, None


def _audit_file(text: str, suffix: str, add) -> bool:
    """Adds findings for one file's comment-free text; returns whether the file has motion."""
    for m in TRANSITION_RE.finditer(text):
        for item in m.group(1).split(","):
            words = item.strip().strip("\"'`").split()
            if not words:
                continue
            prop = words[0].lower()
            if prop == "all":
                add("warn", "transition-all", m.start(), "transition: all animates every property that changes, layout included",
                    "list the properties, for example transition: opacity .2s, translate .2s")
            elif LAYOUT_PROP_RE.fullmatch(prop):
                add("warn", "layout-transition", m.start(), f"transitions {prop}, which re-lays out the page every frame",
                    "animate transform, translate, scale, opacity, or clip-path instead")
    for m in KEYFRAMES_RE.finditer(text):
        block = _block(text, m.end() - 1)
        for k in KEYFRAME_LAYOUT_RE.finditer(block):
            add("warn", "layout-keyframes", m.end() - 1 + k.start(), f"@keyframes animate {k.group(1)}, which re-lays out the page every frame",
                "animate transform, translate, scale, opacity, or clip-path instead")
    for m in NON_PASSIVE_RE.finditer(text):
        call = _call_text(text, m.start())
        if re.search(r"passive\s*:\s*false", call) and m.group(1) != "touchstart":
            add("warn", "scroll-jacking", m.start(), f"a non-passive {m.group(1)} listener can stop the page from scrolling normally",
                "let the browser scroll; drive effects from scroll position (mf-scroll-scene, mf-parallax) instead")
        elif "passive" not in call:
            add("warn", "non-passive-listener", m.start(), f"a {m.group(1)} listener without {{ passive: true }} delays scrolling",
                "pass { passive: true } unless the handler must call preventDefault()")
    rafs = list(RAF_RE.finditer(text))
    for m in SCROLL_LISTENER_RE.finditer(text):
        if not rafs and "IntersectionObserver" not in text:
            add("info", "unthrottled-scroll", m.start(), "a scroll handler runs work on every scroll event",
                "batch it in requestAnimationFrame, or use IntersectionObserver or CSS scroll-driven animations")
            break
    if rafs and not LOOP_STOP_RE.search(text):
        add("warn", "endless-loop", rafs[0].start(), "an animation loop with no way to stop keeps running offscreen and in background tabs",
            "stop it with cancelAnimationFrame when idle, and pause offscreen with IntersectionObserver and on visibilitychange")
    webgl = WEBGL_RE.search(text)
    if webgl and "webglcontextlost" not in text:
        add("warn", "webgl-context-loss", webgl.start(), "a WebGL canvas with no webglcontextlost handler goes blank for good when the GPU resets",
            "call preventDefault() on webglcontextlost and rebuild GL resources on webglcontextrestored")
    if WEBGL_ANY_RE.search(text):
        for m in DPR_RE.finditer(text):
            start = text.rfind("\n", 0, m.start()) + 1
            end = text.find("\n", m.end())
            if not DPR_CAP_RE.search(text[start:end if end != -1 else len(text)]):
                add("warn", "uncapped-dpr", m.start(), "WebGL renders at the full device pixel ratio; 3x screens draw 9x the pixels",
                    "cap it, for example Math.min(devicePixelRatio, 2), or 1.5 for full-screen shaders")
    if suffix in STYLE_SUFFIXES | MARKUP_SUFFIXES or "`" in text:
        hover = HOVER_RE.search(HOVER_MEDIA_RE.sub(lambda mm: " " * len(mm.group(0)), text))
        if hover and not FOCUS_RE.search(text):
            add("info", "hover-only", hover.start(), ":hover styles with no :focus-visible style leave keyboard users without the feedback",
                "give each hover effect a matching :focus-visible rule")
    changes = list(WILL_CHANGE_RE.finditer(text))
    universal = WILL_CHANGE_ALL_RE.search(text)
    if universal:
        add("warn", "will-change-overuse", universal.start(), "will-change on every element makes the browser keep a layer for each one",
            "set will-change only on elements that are about to animate")
    elif len(changes) > 8:
        add("info", "will-change-overuse", changes[8].start(), f"{len(changes)} will-change declarations in one file",
            "set will-change only on elements that are about to animate")
    if rafs or SCROLL_LISTENER_RE.search(text):
        for m in list(STYLE_WRITE_RE.finditer(text))[:3]:
            add("info", "layout-write", m.start(), "writes a layout property from an animation or scroll handler",
                "move it with style.translate or style.transform instead")
    return bool(MOTION_RE.search(text))


def audit_motion(paths: list[str]) -> dict:
    files, error = _files(paths)
    if error:
        return {"ok": False, "error": error}
    findings: list[dict] = []
    moving: list[tuple[str, int]] = []
    handles_reduced = False
    for f, root in files:
        try:
            if f.stat().st_size > MAX_FILE_BYTES:
                continue
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        suffix = f.suffix.lower()
        text = _strip_comments(source, suffix)
        rel = f.relative_to(root).as_posix()

        def add(severity, rule, pos, issue, fix, rel=rel, text=text):
            findings.append({"severity": severity, "rule": rule, "where": f"{rel}:{_line(text, pos)}", "issue": issue, "fix": fix})

        handles_reduced = handles_reduced or bool(REDUCED_RE.search(text))
        if _audit_file(text, suffix, add):
            moving.append((rel, _line(text, MOTION_RE.search(text).start())))
    if moving and not handles_reduced:
        for rel, line in moving:
            findings.append({"severity": "warn", "rule": "reduced-motion", "where": f"{rel}:{line}",
                             "issue": "animates, and nothing in the scanned files handles prefers-reduced-motion",
                             "fix": "add @media (prefers-reduced-motion: reduce) rules that remove movement, or check matchMedia in scripts"})
    findings.sort(key=lambda x: (x["severity"] != "warn", x["where"]))
    return {"ok": not any(x["severity"] == "warn" for x in findings), "files": len(files),
            "findings": findings[:MAX_FINDINGS], "truncated": len(findings) > MAX_FINDINGS,
            "notes": ["warn findings make ok false; info findings are suggestions.",
                      "Heuristic pattern checks: confirm each finding in context, and say why when one is intended."]}
