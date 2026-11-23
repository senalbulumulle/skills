"""Checks the harnesses/<name>/ layout. Run: python3 -m unittest discover -s tools"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESSES = sorted(p for p in (REPO / "harnesses").iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


class HarnessLayout(unittest.TestCase):
    def test_each_harness_has_readme_prompts_test_and_index_row(self):
        self.assertTrue(HARNESSES)
        index = (REPO / "harnesses" / "README.md").read_text(encoding="utf-8")
        for h in HARNESSES:
            with self.subTest(h.name):
                self.assertRegex(h.name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertTrue((h / "README.md").is_file(), f"{h.name} has no README.md")
                self.assertTrue(list((h / "prompts").glob("*.md")), f"{h.name} has no prompts/*.md")
                self.assertTrue(list(h.glob("*.py")), f"{h.name} has no script")
                self.assertTrue((REPO / "tools" / f"test_{h.name.replace('-', '_')}.py").is_file(),
                                f"tools/test_{h.name.replace('-', '_')}.py is missing")
                self.assertIn(f"]({h.name}/README.md)", index, f"harnesses/README.md does not list {h.name}")


if __name__ == "__main__":
    unittest.main()
