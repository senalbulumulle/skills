#!/usr/bin/env python3
"""Check an HTML game before opening it: syntax-check every inline and local script with
`node --check`, and confirm that local src/href files exist. Error line numbers match the HTML file.

Usage: check_html.py path/to/index.html
Exit codes: 0 clean, 1 problems found, 2 usage error or Node.js missing.
"""
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

JS_TYPES = {"", "text/javascript", "application/javascript", "module"}


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []  # dicts: line, module, parts
        self.refs = []     # (line, path)
        self._script = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        line = self.getpos()[0]
        if tag == "script":
            kind = (a.get("type") or "").strip().lower()
            if a.get("src"):
                self.refs.append((line, a["src"]))
            elif kind in JS_TYPES:
                self._script = {"line": line, "module": kind == "module", "parts": []}
        elif tag == "link" and a.get("href"):
            self.refs.append((line, a["href"]))
        elif tag in ("img", "audio", "video", "source") and a.get("src"):
            self.refs.append((line, a["src"]))

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append(self._script)
            self._script = None

    def handle_data(self, data):
        if self._script is not None:
            self._script["parts"].append(data)


def is_local(ref):
    parsed = urlparse(ref)
    return not parsed.scheme and not ref.startswith("//") and parsed.path != ""


def node_check(node, path, label):
    result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
    if result.returncode == 0:
        return None
    lines = []
    for line in (result.stderr or result.stdout).replace(str(path), label).splitlines():
        if line.startswith("    at ") or line.startswith("Node.js v"):
            break  # node's internal stack trace; not useful to the reader
        lines.append(line)
    return "\n".join(lines).strip()


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    html = Path(argv[1])
    if not html.is_file():
        print(f"error: {html} not found", file=sys.stderr)
        return 2
    node = shutil.which("node")
    if node is None:
        print("error: Node.js not found; install it or check the page in a browser console instead", file=sys.stderr)
        return 2

    collector = Collector()
    collector.feed(html.read_text(encoding="utf-8"))
    problems = []

    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name).resolve()  # node prints resolved paths (macOS: /private/var/...)
        for i, script in enumerate(collector.scripts):
            # Pad with newlines so node reports line numbers of the HTML file.
            code = "\n" * (script["line"] - 1) + "".join(script["parts"])
            path = tmp / f"inline-{i}.{'mjs' if script['module'] else 'js'}"
            path.write_text(code, encoding="utf-8")
            error = node_check(node, path, html.name)
            if error:
                problems.append(f"inline script at line {script['line']}:\n{error}")

    for line, ref in collector.refs:
        if not is_local(ref):
            continue
        target = (html.parent / urlparse(ref).path).resolve()
        if not target.exists():
            problems.append(f"line {line}: missing file '{ref}'")
        elif target.suffix in (".js", ".mjs"):
            error = node_check(node, target, ref)
            if error:
                problems.append(f"{ref}:\n{error}")

    for problem in problems:
        print(problem, end="\n\n")
    count = len(collector.scripts)
    print(f"{html}: {count} inline script(s), {len(collector.refs)} reference(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
