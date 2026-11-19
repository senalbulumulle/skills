"""Tests for mcp/creative-director/director.py (tool logic; the MCP transport is covered by tools/mcp_smoke.py).

Run: python3 -m unittest tools/test_creative_director.py
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp" / "creative-director"))
import director  # noqa: E402

# Built from pieces so this test file never matches the rules it tests.
FILLER = "lor" + "em ipsum dolor"
TODO = "// TO" + "DO: implement the boss fight"

GOOD_DESIGN = """# Tidecaller

## Fantasy
You are a lighthouse keeper who bends the tide to guide ships through a storm.

## Core loop
Read the waves, raise or lower the tide, and bank each ship that docks for 10 coins.

## Hook
The tide you raise for one ship strands the next one.

## Controls
- Mouse wheel: raise or lower the tide by 0.5 m.
- Space: ring the bell to slow every ship by 30% for 3 s.

## Win and fail
Dock 12 ships before dawn to win; lose when 3 ships wreck.

## First minute
One ship, calm water, a single rock. The bell is introduced on ship 3.

## Feedback
Foam bursts on each tide change, the bell rings, and ships flash red within 2 m of a rock.

## Progression
Every 4 ships adds a rock and raises wave speed by 10%.

## Scope
First build: one night, one harbor. Later: fog, cargo types.
"""


class FindSlop(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def rules(self, result: dict) -> list:
        return sorted((Path(f["path"]).name, f["line"], f["rule"]) for f in result["findings"])

    def test_finds_each_rule(self):
        self.write("src/game.js", "\n".join([
            f'const intro = "{FILLER}";', TODO, 'throw new Error("Not ' + 'implemented");',
            'document.title = "My ' + 'Game";', 'label.textContent = "Insert ' + 'name here";']))
        self.write("README.md", "An immersive " + "experience with stunning " + "visuals.\n")
        result = director.find_slop([str(self.tmp)])
        self.assertFalse(result["ok"])
        self.assertEqual(self.rules(result), [
            ("README.md", 1, "vague-phrase"), ("README.md", 1, "vague-phrase"),
            ("game.js", 1, "filler-text"), ("game.js", 2, "todo-stub"), ("game.js", 3, "stub"),
            ("game.js", 4, "generic-title"), ("game.js", 5, "placeholder-text")])

    def test_clean_code_and_skipped_paths(self):
        self.write("src/game.py", "# TO" + "DO: tune after playtesting\nclass Base:\n    def run(self):\n"
                   "        raise NotImplementedError\n")
        self.write("node_modules/pkg/index.js", f'"{FILLER}"')
        self.write("tests/test_ui.py", f'"{FILLER}"')
        self.write("art/logo.png", "\0binary")
        result = director.find_slop([str(self.tmp)])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["files_scanned"], 1)
        self.assertEqual(len(director.find_slop([str(self.tmp)], include_tests=True)["findings"]), 1)

    def test_vague_phrases_only_in_prose(self):
        self.write("src/copy.ts", 'export const tagline = "an immersive ' + 'experience";\n')
        self.assertTrue(director.find_slop([str(self.tmp / "src")])["ok"])

    def test_missing_paths_and_caps(self):
        result = director.find_slop([str(self.tmp / "nope")])
        self.assertEqual(result["missing"], [str(self.tmp / "nope")])
        self.assertFalse(result["ok"])
        self.write("big.md", "\n".join([FILLER] * (director.MAX_FINDINGS + 5)))
        result = director.find_slop([str(self.tmp / "big.md")])
        self.assertEqual(len(result["findings"]), director.MAX_FINDINGS)
        self.assertEqual(result["more"], 5)

    def test_the_server_source_is_clean(self):
        result = director.find_slop([str(REPO / "mcp"), str(REPO / "platforms" / "codex"),
                                     str(REPO / "skills" / "roblox-scripting" / "assets")])
        self.assertTrue(result["ok"], result["findings"])


class ReviewDesign(unittest.TestCase):
    def test_complete_design_passes(self):
        result = director.review_design(text=GOOD_DESIGN)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["sections"]["hook"], "Hook")
        self.assertGreaterEqual(result["numbers"], 5)

    def test_reports_gaps_and_vague_lines(self):
        doc = ("# Space Game\n\n## Concept\nA fun and " + "engaging adventure with stunning " + "visuals.\n\n"
               "## Gameplay loop\nFly and shoot.\n")
        result = director.review_design(text=doc)
        self.assertFalse(result["ok"])
        missing = [m["section"] for m in result["missing"]]
        self.assertEqual(missing, ["hook", "controls", "win_fail", "first_minute", "feedback", "progression", "scope"])
        self.assertEqual([v["line"] for v in result["vague"]], [4, 4])
        self.assertTrue(any("numbers" in n for n in result["notes"]))

    def test_list_markers_are_not_tuning_numbers(self):
        result = director.review_design(text="## Steps\n1. Jump\n2. Land\n3. Repeat\n")
        self.assertEqual(result["numbers"], 0)

    def test_path_and_argument_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "design.md"
            path.write_text(GOOD_DESIGN, encoding="utf-8")
            self.assertTrue(director.review_design(path=str(path))["ok"])
        self.assertIn("exactly one", director.review_design()["error"])
        self.assertIn("exactly one", director.review_design(text="x", path="y")["error"])
        self.assertIn("cannot read", director.review_design(path="/no/such/file.md")["error"])


ROBLOX_BRIEF = """# Lantern Relay

**Hook:** Your whole server carries one lantern up a mountain, and whoever holds it lights the path for everyone.
**Devices:** phone, PC, console · **Party size:** server-wide (up to 12) · **Session:** 15 minutes

## First minute
| Time | Player sees | Player does | Reward |
| --- | --- | --- | --- |
| 0-10 s | the lantern glowing at camp | walks to it | a spark trail |
| 10-60 s | the first dark ledge | passes the lantern | 5 embers |

## Loops
Short: pass the lantern every 20 s. Session: reach the summit. Long: unlock 3 lantern colors.

## Social hook
Nobody climbs alone: the path is lit only within 8 studs of the lantern.

## Controls
| Action | Touch | Keyboard / mouse | Gamepad |
| --- | --- | --- | --- |
| Pass | big button | E | X |

## Closest existing experiences
| Experience | Shared | Different |
| --- | --- | --- |
| Tower climbs | climbing | one shared light |

## Monetization
Lantern skins for 50 Robux; no power for sale.

## MVP
1. One mountain, one lantern.
"""


class ReviewRobloxBrief(unittest.TestCase):
    def test_complete_brief_passes(self):
        result = director.review_design(text=ROBLOX_BRIEF, platform="roblox")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["sections"]["hook"], "Hook")  # a **Label:** line counts as a heading
        self.assertEqual(result["sections"]["devices"], "Devices")
        self.assertEqual(result["sections"]["social"], "Party size")

    def test_gaps_and_odds(self):
        doc = "# Pet Hatch\n\n## Loops\nHatch eggs for 100 Robux each and collect 30 pets in 5 worlds.\n"
        result = director.review_design(text=doc, platform="roblox")
        self.assertFalse(result["ok"])
        self.assertEqual([m["section"] for m in result["missing"]],
                         ["hook", "first_minute", "social", "devices", "controls", "comparables", "monetization",
                          "scope"])
        self.assertTrue(any("no odds" in n for n in result["notes"]))
        with_odds = doc + "\nOdds: Common 90%, Rare 10%.\n"
        self.assertFalse(any("no odds" in n for n in director.review_design(text=with_odds, platform="roblox")["notes"]))
        self.assertIn("platform must be", director.review_design(text=doc, platform="unity")["error"])

    def test_the_shipped_brief_template_has_every_section(self):
        template = REPO / "skills" / "roblox-game-design" / "assets" / "roblox-brief.md"
        self.assertEqual(director.review_design(path=str(template), platform="roblox")["missing"], [])


class RobloxRules(unittest.TestCase):
    def test_fake_asset_ids_and_default_labels(self):
        asset = "rbxasset" + "id://"
        lines = [f'img.Image = "{asset}0"', f'sound.SoundId = "{asset}123456789"', f'icon.Image = "{asset}"',
                 'button.Text = "Butt' + 'on"', "label.Text = 'Lab" + "el'"]
        fine = [f'img.Image = "{asset}1234598765"', f'img.Image = "{asset}" .. iconId', f'img.Image = `{asset}{{id}}`',
                'box.PlaceholderText = "Lab' + 'el"', 'button.Text = "Claim 100 coins"']
        rules = [f["rule"] for line in lines for f in director.scan_text(line, prose=False)]
        self.assertEqual(rules, ["fake-asset-id"] * 3 + ["default-ui-text"] * 2)
        self.assertEqual([f for line in fine for f in director.scan_text(line, prose=False)], [])


class ConceptSeeds(unittest.TestCase):
    def test_reproducible_and_distinct(self):
        a = director.concept_seeds(5, seed=42)
        self.assertEqual(a, director.concept_seeds(5, seed=42))
        self.assertEqual(len({c["verb"] for c in a["concepts"]}), 5)
        self.assertEqual(len({c["twist"] for c in a["concepts"]}), 5)
        self.assertNotEqual(a["concepts"], director.concept_seeds(5, seed=43)["concepts"])

    def test_random_seed_is_returned_and_genre_is_used(self):
        result = director.concept_seeds(genre="Roblox obby")
        self.assertEqual(result, director.concept_seeds(seed=result["seed"], genre="Roblox obby"))
        self.assertIn("Roblox obby", result["how_to_use"])

    def test_count_limits_and_list_quality(self):
        self.assertFalse(director.concept_seeds(0)["ok"])
        self.assertFalse(director.concept_seeds(11)["ok"])
        for items in (director.VERBS, director.TWISTS, director.SETTINGS, director.FEELINGS):
            self.assertEqual(len(items), len(set(items)))
            self.assertGreaterEqual(len(items), 10)


if __name__ == "__main__":
    unittest.main()
