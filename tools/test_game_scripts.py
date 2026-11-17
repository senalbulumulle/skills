"""Tests for the Python scripts shipped inside skills. Run: python3 -m unittest discover -s tools"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"


def load(rel):
    spec = importlib.util.spec_from_file_location(Path(rel).stem, SKILLS / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(module, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = module.main(argv)
        except SystemExit as e:  # argparse errors
            code = e.code
    return code, out.getvalue()


class CheckLevelTests(unittest.TestCase):
    m = load("game-level-design/scripts/check_level.py")

    def analyze(self, text, **kw):
        return self.m.analyze(self.m.parse(text), **kw)

    def test_key_and_door(self):
        r = self.analyze("##########\n#a..S..A.G#\n##########", keys="a")
        self.assertTrue(r["ok"])
        self.assertEqual(r["shortest_path"], 11)  # back for the key, then through the door
        self.assertEqual(r["unreachable_tiles"], 0)  # ragged rows are padded with wall

    def test_unreachable_goal(self):
        r = self.analyze("#####\n#S#G#\n#####")
        self.assertFalse(r["ok"])
        self.assertIn("unreachable", r["problems"][0])

    def test_door_without_key_blocks(self):
        r = self.analyze("#######\n#S.A.G#\n#######", keys="a")
        self.assertFalse(r["ok"])
        self.assertTrue(any("not placed" in p for p in r["problems"]))

    def test_letters_are_floor_without_keys(self):
        self.assertTrue(self.analyze("#######\n#S.E.G#\n#######")["ok"])

    def test_comments_skipped_and_diagonal(self):
        text = "; legend\n####\n#S##\n##G#\n####"
        self.assertFalse(self.analyze(text)["ok"])
        self.assertTrue(self.analyze(text, diagonal=True)["ok"])

    def test_start_and_goal_required(self):
        self.assertFalse(self.analyze("#..#")["ok"])

    def test_cli_rejects_bad_keys(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("#S.G#\n")
        try:
            self.assertEqual(run(self.m, [f.name])[0], 0)
            self.assertEqual(run(self.m, [f.name, "--keys", "s"])[0], 2)
            self.assertEqual(run(self.m, [f.name, "--keys", "A"])[0], 2)
        finally:
            Path(f.name).unlink()


class BalanceTests(unittest.TestCase):
    m = load("game-balance/scripts/balance.py")

    def json(self, argv):
        code, out = run(self.m, argv + ["--json"])
        self.assertEqual(code, 0)
        return json.loads(out)

    def test_exp_curve(self):
        rows = self.json(["curve", "--type", "exp", "--base", "100", "--growth", "1.15", "--levels", "3"])
        self.assertAlmostEqual(rows[2]["value"], 132.25)
        self.assertAlmostEqual(rows[2]["cumulative"], 347.25)

    def test_logistic_midpoint(self):
        rows = self.json(["curve", "--type", "logistic", "--base", "1000", "--growth", "1", "--levels", "5"])
        self.assertAlmostEqual(rows[2]["value"], 500)

    def test_ttk(self):
        rows = self.json(["ttk", "--hp", "100", "--damage", "30", "--rate", "2"])
        self.assertEqual(rows[0]["hits"], 4)
        self.assertAlmostEqual(rows[0]["seconds"], 1.5)

    def test_drops(self):
        r = self.json(["drops", "--chance", "0.05", "--tries", "10", "--pity", "60"])
        self.assertAlmostEqual(r["within"]["10"], 1 - 0.95 ** 10)
        self.assertEqual(r["tries_for"], {"50%": 14, "90%": 45, "99%": 90})
        self.assertAlmostEqual(r["pity"]["expected_tries"], (1 - 0.95 ** 60) / 0.05)

    def test_rejects_bad_probability(self):
        self.assertEqual(run(self.m, ["drops", "--chance", "1.5"])[0], 2)


class PaletteTests(unittest.TestCase):
    m = load("game-art/scripts/palette_check.py")

    def test_reference_contrasts(self):
        c = lambda a, b: self.m.contrast(self.m.luminance(a), self.m.luminance(b))
        self.assertAlmostEqual(c((0, 0, 0), (255, 255, 255)), 21.0)
        self.assertAlmostEqual(c((0x77,) * 3, (255, 255, 255)), 4.48, places=2)

    def test_template_palette_passes(self):
        code, _ = run(self.m, ["bg=#1b1b2f", "player=#f4d35e", "enemy=#ee6c4d", "pickup=#4361ee",
                               "text=#f5f5f5", "ui-dim=#8d8daa"])
        self.assertEqual(code, 0)

    def test_similar_gameplay_colors_fail(self):
        code, out = run(self.m, ["bg=#1b1b2f", "player=#f4d35e", "pickup=#5fd068"])
        self.assertEqual(code, 1)
        self.assertIn("player vs pickup", out)

    def test_low_text_contrast_fails(self):
        self.assertEqual(run(self.m, ["bg=#fff", "text=#777"])[0], 1)

    def test_missing_background(self):
        self.assertEqual(run(self.m, ["player=#fff"])[0], 2)


class NewRobloxProjectTests(unittest.TestCase):
    m = load("roblox-scripting/scripts/new_project.py")

    def test_creates_project_with_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "game"
            files = self.m.create(dest, "Sky Garden")
            self.assertIn("default.project.json", files)
            self.assertIn("src/server/PlayerData.luau", files)
            self.assertEqual(json.loads((dest / "default.project.json").read_text())["name"], "Sky Garden")

    def test_refuses_non_empty_folder_and_bad_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "keep.txt").write_text("x")
            with self.assertRaises(ValueError):
                self.m.create(Path(tmp), "Game")
            with self.assertRaises(ValueError):
                self.m.create(Path(tmp) / "new", "1bad")

    @unittest.skipUnless(shutil.which("rojo"), "Rojo not installed")
    def test_template_builds_with_rojo(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "game"
            self.m.create(dest, "Build Test")
            result = subprocess.run(["rojo", "build", "-o", "build.rbxlx"], cwd=dest, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            place = (dest / "build.rbxlx").read_text()
            for cls, name in [("Script", "Main"), ("LocalScript", "Main"), ("ModuleScript", "PlayerData"),
                              ("ModuleScript", "RemoteGuard"), ("RemoteEvent", "ClaimDaily")]:
                self.assertRegex(place, rf'<Item class="{cls}"[^>]*>\s*<Properties>\s*<string name="Name">{name}</string>')


@unittest.skipUnless(shutil.which("node"), "Node.js not installed")
class CheckHtmlTests(unittest.TestCase):
    m = load("game-prototype/scripts/check_html.py")

    def test_template_is_clean(self):
        code, out = run(self.m, ["check_html.py", str(SKILLS / "game-prototype/assets/canvas-template.html")])
        self.assertEqual(code, 0, out)

    def test_reports_syntax_error_line_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "bad.html"
            page.write_text('<html><body>\n<img src="missing.png">\n<script>\nlet x = ;\n</script>\n'
                            '<script type="application/json">{"not": js}</script>\n</body></html>\n')
            code, out = run(self.m, ["check_html.py", str(page)])
        self.assertEqual(code, 1)
        self.assertIn("bad.html:4", out)
        self.assertIn("missing file 'missing.png'", out)
        self.assertIn("2 problem(s)", out)


if __name__ == "__main__":
    unittest.main()
