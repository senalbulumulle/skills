"""Tests for platforms/codex/hooks/discover.py, which reads the hook surface compiled into Codex.

Run: python3 -m unittest tools/test_codex_discover.py
"""
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "platforms" / "codex" / "hooks"
sys.path.insert(0, str(HOOKS))
import discover  # noqa: E402


def schema(title: str, props: dict, definitions: dict = None) -> str:
    return json.dumps({"$schema": "http://json-schema.org/draft-07/schema#", "title": title,
                       "properties": props, "definitions": definitions or {}}, indent=2)


class Discover(unittest.TestCase):
    BLOB = ("junk\x00" + schema("pre-tool-use.command.input", {
        "hook_event_name": {"const": "PreToolUse"}, "tool_input": True,
        "turn_id": {"type": "string", "description": "Codex extension: turn id"}})
        + "\x00" + schema("pre-tool-use.command.output", {
            "decision": {"allOf": [{"$ref": "#/definitions/D"}]},
            "hookSpecificOutput": {"allOf": [{"$ref": "#/definitions/S"}]}},
            {"D": {"enum": ["approve", "block"]},
             "S": {"properties": {"hookEventName": {}, "permissionDecision": {"enum": ["allow", "deny"]}, "updatedInput": {}}}})
        + "PreToolUse hook returned unsupported permissionDecision:askPreToolUse hook returned updatedInput without "
          "permissionDecision:allowxx: prompt hooks are not supported yet\x00").encode()

    def test_analyze(self):
        r = discover.analyze(self.BLOB)
        e = r["events"]["PreToolUse"]
        self.assertEqual(e["codex_extensions"], ["turn_id"])
        self.assertEqual(e["output_enums"], {"decision": ["approve", "block"], "permissionDecision": ["allow", "deny"]})
        self.assertEqual(e["hookSpecificOutput"], ["hookEventName", "permissionDecision", "updatedInput"])
        self.assertEqual(r["rejected_outputs"], ["PreToolUse: permissionDecision:ask",
                                                 "PreToolUse: updatedInput requires permissionDecision:allow"])
        self.assertEqual(r["skipped_handler_types"], ["prompt"])

    def test_diff(self):
        old = discover.analyze(self.BLOB)
        new = json.loads(json.dumps(old))
        new["events"]["Interrupt"] = {"input": ["cwd"]}
        new["rejected_outputs"] = []
        self.assertEqual(discover.diff(old, new), ["+ event Interrupt",
                                                   "- rejected_outputs: PreToolUse: permissionDecision:ask",
                                                   "- rejected_outputs: PreToolUse: updatedInput requires permissionDecision:allow"])
        self.assertEqual(discover.diff(old, old), [])

    def test_snapshot_is_current_for_installed_codex(self):
        exe = shutil.which("codex")
        snap = HOOKS / "snapshots" / "codex-0.163.0.json"
        if not exe:
            self.skipTest("codex not installed")
        r = discover.report(Path(os.path.realpath(exe)))
        if r["codex_version"] != "0.163.0":
            self.skipTest(f"installed codex is {r['codex_version']}")
        self.assertEqual(discover.diff(json.loads(snap.read_text()), r), [])


if __name__ == "__main__":
    unittest.main()
