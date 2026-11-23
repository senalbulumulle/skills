"""Tests for platforms/codex/models/export_models.py.

Run: python3 -m unittest tools/test_codex_models.py
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CODEX = Path(__file__).resolve().parent.parent / "platforms" / "codex"
sys.path.insert(0, str(CODEX / "models"))
import export_models  # noqa: E402

SECRET = "Unique instruction text that must never be printed."


def model(slug: str, template: str, **extra) -> dict:
    return {"slug": slug, "display_name": slug.upper(), "description": f"{slug} model", "visibility": "list",
            "priority": 1, "default_reasoning_level": "medium",
            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}], "context_window": 272000,
            "input_modalities": ["text"], "experimental_supported_tools": [],
            "model_messages": {"instructions_template": template, "approvals": {"never": None},
                               "token_budget": {"enabled": False, "reminder_message_template": SECRET}},
            **extra}


CATALOG = {"client_version": "9.9.9", "models": [
    model("gpt-luna", f"# Personality\n{SECRET}\n\n## Writing style\nShort.\n"),
    model("gpt-astra", f"# Personality\n{SECRET}\n\n## Writing style\nLonger and different.\n# Coding Style\nRead.\n",
          context_window=500000, supported_reasoning_levels=[{"effort": "high"}, {"effort": "ultra"}]),
]}


class ExportModels(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.catalog = self.tmp / "catalog.json"
        self.catalog.write_text(json.dumps(CATALOG))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_main(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = export_models.main(["--catalog", str(self.catalog), *args])
        return code, out.getvalue()

    def test_summary_never_contains_instruction_text(self):
        for args in ((), ("--json",), ("--compare", "gpt-luna", "gpt-astra"), ("--compare", "gpt-luna", "gpt-astra",
                                                                               "--json")):
            code, out = self.run_main(*args)
            self.assertEqual(code, 0, args)
            self.assertNotIn(SECRET, out, args)

    def test_summary_shape(self):
        code, out = self.run_main("--json")
        data = json.loads(out)
        self.assertEqual(data["client_version"], "9.9.9")
        astra = data["models"][1]
        self.assertEqual(astra["settings"]["reasoning_levels"], ["high", "ultra"])
        self.assertEqual([s["heading"] for s in astra["instructions"]["sections"]],
                         ["# Personality", "## Writing style", "# Coding Style"])
        self.assertEqual(astra["messages"]["token_budget.enabled"], {"value": False})
        self.assertNotIn("approvals.never", astra["messages"])

    def test_compare(self):
        code, out = self.run_main("--compare", "gpt-luna", "gpt-astra", "--json")
        diff = json.loads(out)
        self.assertEqual(diff["settings"]["context_window"], [272000, 500000])
        self.assertEqual(diff["sections_only_in"], {"gpt-luna": [], "gpt-astra": ["# Coding Style"]})
        self.assertEqual([c["heading"] for c in diff["sections_changed"]], ["## Writing style"])
        self.assertFalse(diff["same_instructions"])
        self.assertEqual(diff["messages_differ"], [])

    def test_errors(self):
        self.assertEqual(self.run_main("--compare", "gpt-luna", "gpt-nope")[0], 1)
        self.catalog.write_text("{}")
        with self.assertRaises(SystemExit):
            self.run_main()

    def test_snapshots_hold_no_instruction_text(self):
        for snapshot in (CODEX / "models" / "snapshots").glob("*.json"):
            data = json.loads(snapshot.read_text())
            for m in data["models"]:
                self.assertEqual(set(m), {"slug", "settings", "instructions", "messages"}, snapshot.name)
                for section in m["instructions"]["sections"]:
                    self.assertEqual(set(section), {"heading", "chars", "sha"})


if __name__ == "__main__":
    unittest.main()
