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
    m = load("game-dev/game-level-design/scripts/check_level.py")

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
    m = load("game-dev/game-balance/scripts/balance.py")

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
    m = load("game-dev/game-art/scripts/palette_check.py")

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
    m = load("roblox/roblox-scripting/scripts/new_project.py")

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
    m = load("game-dev/game-prototype/scripts/check_html.py")

    def test_template_is_clean(self):
        code, out = run(self.m, ["check_html.py", str(SKILLS / "game-dev/game-prototype/assets/canvas-template.html")])
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


class StoryTests(unittest.TestCase):
    m = load("roblox/roblox-narrative/scripts/story.py")
    EXAMPLE = SKILLS / "roblox" / "roblox-narrative" / "assets" / "example"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def docs(self, dialogue: dict[str, str], characters: str | None = None, story: str | None = None) -> Path:
        d = self.tmp / "docs"
        (d / "dialogue").mkdir(parents=True)
        (d / "characters.md").write_text(characters if characters is not None else
                                         "# Characters\n\n## Mara Quell\n- id: mara\n- role: keeper\n- wants: light\n"
                                         "- voice: dry\n- vo: alto\n")
        if story is not None:
            (d / "story.md").write_text(story)
        for name, text in dialogue.items():
            (d / "dialogue" / f"{name}.md").write_text(text)
        return d

    def where(self, result):
        return {(f["where"], f["severity"]) for f in result["findings"]}

    def test_example_is_clean_and_committed_outputs_are_current(self):
        result = self.m.review(self.EXAMPLE / "docs")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["findings"], [])
        self.assertEqual((result["conversations"], result["lines"], result["choices"]), (2, 9, 8))
        story, _ = self.m.load(self.EXAMPLE / "docs")
        build = self.EXAMPLE / "build"
        self.assertEqual((build / "Dialogue.luau").read_text(), self.m.render_module(story, build / "Dialogue.luau"))
        self.assertEqual((build / "voiceover.md").read_text(), self.m.render_voiceover(story))
        self.assertEqual((build / "localization.csv").read_text(), self.m.render_localization(story, ["es", "pt-br"]))

    def test_types_match_dialogue_runner(self):
        runner = (SKILLS / "roblox" / "roblox-narrative" / "assets" / "DialogueRunner.luau").read_text()
        self.assertIn(self.m.LUAU_TYPES, runner)

    def test_findings(self):
        d = self.docs({
            "shop": "# Shop\n- npc: mara\n- start: greet\n\n"
                    "## greet\n"
                    "mara (dry): Hello.\n"  # 6
                    "bob: Who are you?\n"  # 7: no character sheet
                    "- [Go](#nowhere)\n"  # 8: missing target
                    "- [Secret](#end) | needs key_found\n"  # 9: flag never set
                    "- [Rest](#end) | needs !tired\n"  # 10: never set, always passes
                    "\n## lost\n"  # 12: unreachable
                    "mara: " + "word " * 25 + "\n"  # 13: too long for a phone
                    "-> end | sets gossip\n"  # 14: checked by the stuck node, so no finding
                    "\n## stuck\n"  # 16: unreachable, and every choice is conditional
                    "- [Only with a key](#end) | needs gossip\n"
                    "\n## empty\n",  # 19: dead end
            "Bad-Name": "# x\n",
        })
        result = self.m.review(d)
        self.assertFalse(result["ok"])
        self.assertEqual(self.where(result), {
            ("dialogue/Bad-Name.md", "high"), ("dialogue/shop.md:7", "high"), ("dialogue/shop.md:8", "high"),
            ("dialogue/shop.md:9", "high"), ("dialogue/shop.md:10", "low"), ("dialogue/shop.md:12", "medium"),
            ("dialogue/shop.md:13", "low"), ("dialogue/shop.md:16", "medium"),
            ("dialogue/shop.md:19", "medium"), ("dialogue/shop.md:19", "high"), ("story.md", "medium")})
        self.assertEqual([f["severity"] for f in result["findings"]][0], "high", "most severe first")

    def test_parse_errors_and_character_sheets(self):
        d = self.docs({"talk": "# Talk\n- npc: mara\n- start: a\nstray text\n\n## a\n"
                               "Mara: capitalised speaker\n"
                               "- [x](#end) | sets Bad-Flag\n"
                               "- [y](#end) maybe\n"
                               "-> end\n"  # 10: valid, since the broken choices above were rejected
                               "### deeper\n"},
                      characters="# Characters\n\n## Mara\n- id: mara\n- role: r\n- wants: w\n- voice: v\n\n"
                                 "## Twin\n- id: mara\n\n## Quiet\n- id: quiet\n- role: r\n- wants: w\n- voice: v\n")
        result = self.m.review(d)
        where = self.where(result)
        for line in (4, 7, 8, 9, 11):
            self.assertIn((f"dialogue/talk.md:{line}", "high"), where, line)
        self.assertIn(("characters.md:9", "high"), where, "duplicate id")
        self.assertIn(("characters.md:9", "medium"), where, "missing fields")
        self.assertNotIn(("dialogue/talk.md:10", "high"), where)
        self.assertIn(("characters.md:3", "low"), where, "Mara never speaks: her only line failed to parse")
        self.assertIn(("characters.md:12", "low"), where, "Quiet never speaks")

    def test_choices_shown_at_once(self):
        five = "".join(f"- [c{i}](#end)\n" for i in range(5))
        exclusive = "".join(f"- [c{i}](#end) | needs !f{i}\n" for i in range(3)) + \
            "- [a](#end) | needs f0, f1\n- [b](#end) | needs f2\n"
        d = self.docs({"many": f"# M\n- npc: mara\n- start: a\n\n## a\nmara: hi\n{five}",
                       "some": f"# S\n- npc: mara\n- start: a\n\n## a\nmara: hi\n{exclusive}"},
                      story="# T\n\n## Premise\nP.\n\n## Acts\n\n### One\n- goal: g\n\n## Flags\n- f0: x\n- f1: x\n"
                            "- f2: x\n")
        result = self.m.review(d)
        self.assertEqual([f["where"] for f in result["findings"] if "show at once" in f["issue"]],
                         ["dialogue/many.md:5"])

    def test_build_refuses_broken_docs_and_foreign_files(self):
        d = self.docs({"shop": "# Shop\n- npc: ghost\n- start: a\n\n## a\nmara: hi\n-> end\n"})
        refused = self.m.build(d, self.tmp / "out" / "Dialogue.luau")
        self.assertFalse(refused["ok"])
        self.assertIn("high findings", refused["error"])
        self.assertFalse((self.tmp / "out").exists())
        (d / "dialogue" / "shop.md").write_text("# Shop\n- npc: mara\n- start: a\n\n## a\nmara: hi\n-> end\n")
        mine = self.tmp / "Mine.luau"
        mine.write_text("return {}\n")
        self.assertFalse(self.m.build(d, mine)["ok"])
        self.assertEqual(mine.read_text(), "return {}\n", "never overwrites a file it didn't write")
        out = self.tmp / "src" / "Dialogue.luau"
        self.assertTrue(self.m.build(d, out)["ok"])
        self.assertTrue(self.m.build(d, out)["ok"], "rebuilds its own file")
        self.assertIn("-- Docs: ../docs (sha256 " + self.m.docs_hash(d) + ")", out.read_text())

    def test_luau_strings_and_keywords(self):
        d = self.docs({"then": '# T\n- npc: mara\n- start: end_\n\n## end_\nmara: She said "go\\\\stop" é\x07\n'
                                "-> end\n"})
        out = self.tmp / "D.luau"
        self.assertTrue(self.m.build(d, out)["ok"])
        text = out.read_text()
        self.assertIn('["then"] = {', text)
        self.assertIn(r'text = "She said \"go\\\\stop\" é\007"'.replace(r"é", "é"), text)
        if shutil.which("luau"):
            import subprocess
            runner = self.tmp / "run.luau"
            runner.write_text('local d = require("./D")\nprint(d.conversations["then"].nodes.end_.lines[1].text)\n')
            proc = subprocess.run(["luau", str(runner)], capture_output=True, text=True)
            self.assertEqual(proc.stdout, 'She said "go\\\\stop" é\x07\n', proc.stderr)

    def test_voiceover_and_localization(self):
        d = self.docs({"shop": "# Shop\n- npc: mara\n- start: a\n\n## a\nmara (wry): One | two, three.\n"
                               "narrator: The bell rings.\n- [Leave, now](#end)\n"},
                      story="# Bell Tower\n\n## Premise\nP.\n\n## Acts\n\n### One\n- goal: g\n")
        vo = self.tmp / "vo.md"
        self.assertTrue(self.m.voiceover(d, vo)["ok"])
        text = vo.read_text()
        self.assertIn("# Voiceover script: Bell Tower", text)
        self.assertIn("| `shop.a.1` | One \\| two, three. | wry | 4 | 1.6 |", text)
        self.assertIn("## Narrator (`narrator`)", text)
        self.assertIn("Total: 2 lines", text)
        csv_out = self.tmp / "loc.csv"
        self.assertFalse(self.m.localization(d, csv_out, ["Spanish"])["ok"])
        result = self.m.localization(d, csv_out, ["es"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(csv_out.read_text().splitlines(), [
            "Key,Context,Example,Source,es", "characters.mara.name,,,Mara Quell,", "shop.a.1,,,\"One | two, three.\",",
            "shop.a.2,,,The bell rings.,", "shop.a.choice1,,,\"Leave, now\","])
        self.assertTrue(self.m.localization(d, csv_out)["ok"], "rewrites its own CSV")
        other = self.tmp / "other.csv"
        other.write_text("Key,Context,Example,Source\nMy Key,,,x\n")
        self.assertFalse(self.m.localization(d, other)["ok"])

    def test_cli(self):
        code, out = run(self.m, ["review", str(self.EXAMPLE / "docs")])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])
        code, _ = run(self.m, ["review", str(self.tmp / "missing")])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
