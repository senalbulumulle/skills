#!/usr/bin/env python3
"""Edit CLI config files for hybrid-llms registration (standard library only).

Subcommands (each writes a .bak backup before changing an existing file):
  codex-add    CONFIG_TOML BIN     add/replace [mcp_servers.hybrid]
  codex-remove CONFIG_TOML         remove [mcp_servers.hybrid] (and its subtables)
  gemini-add   SETTINGS_JSON BIN   add/replace mcpServers.hybrid
  gemini-remove SETTINGS_JSON      remove mcpServers.hybrid
  block-set    FILE BLOCK_FILE     add/replace the marked hybrid-llms block in FILE
  block-remove FILE                remove the marked block
"""
import json
import os
import re
import shutil
import sys

BEGIN = "<!-- hybrid-llms:begin -->"
END = "<!-- hybrid-llms:end -->"
TABLE_RE = re.compile(r'^\s*\[\s*mcp_servers\s*\.\s*(?:hybrid|"hybrid")\s*(?:\.[^\]]*)?\]\s*(?:#.*)?$')
HEADER_RE = re.compile(r"^\s*\[")


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def write(path, text, original):
    if original is not None and original == text:
        return
    if original is not None:
        shutil.copy2(path, path + ".bak")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def codex_strip(text):
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        if TABLE_RE.match(line):
            skipping = True
            continue
        if skipping and HEADER_RE.match(line):
            skipping = False
        if not skipping:
            out.append(line)
    return "".join(out).rstrip("\n") + ("\n" if out else "")


def codex_add(path, binary):
    original = read(path)
    text = codex_strip(original or "")
    block = (
        "[mcp_servers.hybrid]\n"
        f"command = {toml_str(binary)}\n"
        'args = ["mcp"]\n'
        'env_vars = ["HYBRID_LLMS_DEPTH", "HYBRID_LLMS_CONFIG"]\n'
        "startup_timeout_sec = 30\n"
        "tool_timeout_sec = 1800\n"
    )
    text = (text + "\n" if text.strip() else "") + block
    write(path, text, original)


def codex_remove(path):
    original = read(path)
    if original is None:
        return
    write(path, codex_strip(original), original)


def load_json(path):
    original = read(path)
    if original is None or not original.strip():
        return original, {}
    try:
        data = json.loads(original)
    except json.JSONDecodeError as e:
        sys.exit(f"hybrid_config: {path} is not plain JSON ({e}); edit it by hand")
    if not isinstance(data, dict):
        sys.exit(f"hybrid_config: {path} must contain a JSON object")
    return original, data


def gemini_add(path, binary):
    original, data = load_json(path)
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        sys.exit(f"hybrid_config: mcpServers in {path} is not an object")
    servers["hybrid"] = {"command": binary, "args": ["mcp"], "timeout": 1800000}
    write(path, json.dumps(data, indent=2) + "\n", original)


def gemini_remove(path):
    original, data = load_json(path)
    if original is None:
        return
    servers = data.get("mcpServers")
    if isinstance(servers, dict) and "hybrid" in servers:
        del servers["hybrid"]
        write(path, json.dumps(data, indent=2) + "\n", original)


def block_strip(text):
    pattern = re.compile(r"\n*" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
    return pattern.sub("\n", text).strip("\n")


def block_set(path, block_file):
    original = read(path)
    with open(block_file, encoding="utf-8") as f:
        block = f.read().strip("\n")
    text = block_strip(original or "")
    text = (text + "\n\n" if text else "") + BEGIN + "\n" + block + "\n" + END + "\n"
    write(path, text, original)


def block_remove(path):
    original = read(path)
    if original is None:
        return
    text = block_strip(original)
    write(path, text + "\n" if text else "", original)


COMMANDS = {
    "codex-add": (codex_add, 2),
    "codex-remove": (codex_remove, 1),
    "gemini-add": (gemini_add, 2),
    "gemini-remove": (gemini_remove, 1),
    "block-set": (block_set, 2),
    "block-remove": (block_remove, 1),
}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        sys.exit(__doc__)
    fn, nargs = COMMANDS[argv[1]]
    if len(argv) != 2 + nargs:
        sys.exit(f"usage: hybrid_config.py {argv[1]} " + " ".join(["ARG"] * nargs))
    fn(*argv[2:])


if __name__ == "__main__":
    main(sys.argv)
