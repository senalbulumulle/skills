"""Tests for the roblox-forge MCP tool logic (mcp/roblox-forge/forge.py). Standard library only."""
from __future__ import annotations

import importlib.util
import json
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

FORGE_DIR = Path(__file__).resolve().parent.parent / "mcp" / "roblox-forge"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, FORGE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


forge = _load("forge")
studio_catalog = _load("studio_catalog")
narrative = _load("narrative")
EXAMPLE_DOCS = FORGE_DIR.parents[1] / "skills" / "roblox-narrative" / "assets" / "example" / "docs"


class ForgeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def project(self, tree: dict, files: dict | None = None) -> Path:
        d = self.root / "proj"
        d.mkdir(exist_ok=True)
        (d / "default.project.json").write_text(json.dumps({"name": "P", "tree": tree}))
        for rel, text in (files or {}).items():
            f = d / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        return d


class CreateAndCheckTests(ForgeTestCase):
    def test_template_project_is_clean(self):
        dest = self.root / "game"
        created = forge.create_project(str(dest), "Game")
        self.assertTrue(created["ok"])
        result = forge.check_project(str(dest))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["scripts"], {"server": 1, "client": 1, "module": 4})
        self.assertEqual(result["rojo_build"], "ok" if shutil.which("rojo") else "rojo not installed")
        self.assertFalse(forge.create_project(str(dest))["ok"], "refuses a non-empty folder")

    def test_scripts_mapped_where_they_dont_run(self):
        d = self.project({
            "$className": "DataModel",
            "ReplicatedStorage": {"$className": "ReplicatedStorage", "Shared": {"$path": "src/shared"}},
            "ServerScriptService": {"$className": "ServerScriptService", "Server": {"$path": "src/server"}},
        }, {
            "src/shared/Oops.server.luau": "print(1)",
            "src/server/Ui.client.luau": "print(1)",
            "src/server/Ok.server.luau": "print(1)",
        })
        warnings = forge.check_project(str(d), build=False)["warnings"]
        self.assertTrue(any("Oops.server.luau" in w and "will not run" in w for w in warnings))
        self.assertTrue(any("Ui.client.luau" in w and "will not run" in w for w in warnings))
        self.assertFalse(any("Ok.server.luau" in w for w in warnings))

    def test_client_scripts_run_in_starter_player_scripts(self):
        d = self.project({
            "$className": "DataModel",
            "StarterPlayer": {"$className": "StarterPlayer",
                              "StarterPlayerScripts": {"$className": "StarterPlayerScripts", "Client": {"$path": "src/client"}}},
        }, {"src/client/Main.client.luau": "print(1)"})
        self.assertEqual(forge.check_project(str(d), build=False)["warnings"], [])

    def test_missing_path_init_conflict_duplicates(self):
        d = self.project({
            "$className": "DataModel",
            "ServerScriptService": {"$className": "ServerScriptService",
                                    "Server": {"$path": "src/server"}, "Gone": {"$path": "src/missing"}},
        }, {
            "src/server/init.server.luau": "",
            "src/server/init.luau": "",
            "src/server/Thing.luau": "",
            "src/server/Thing/Child.luau": "",
        })
        r = forge.check_project(str(d), build=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("does not exist" in p for p in r["problems"]))
        self.assertTrue(any("more than one init script" in p for p in r["problems"]))
        self.assertTrue(any("duplicate instance name 'Thing'" in w for w in r["warnings"]))

    def test_library_project_skips_location_checks(self):
        d = self.project({"$path": "src"}, {"src/Main.server.luau": "print(1)"})
        r = forge.check_project(str(d), build=False)
        self.assertTrue(r["ok"])
        self.assertFalse(any("will not run" in w for w in r["warnings"]))

    def test_invalid_json_and_missing_file(self):
        d = self.root / "bad"
        d.mkdir()
        (d / "default.project.json").write_text("{nope")
        self.assertIn("invalid JSON", forge.check_project(str(d))["problems"][0])
        self.assertFalse(forge.check_project(str(self.root / "none"))["ok"])


class AuditRemotesTests(ForgeTestCase):
    def test_template_handlers_are_wrapped(self):
        dest = self.root / "game"
        forge.create_project(str(dest), "Game")
        r = forge.audit_remotes(str(dest))
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["handlers"], r["wrapped"]), (1, 1))

    def test_flags_unwrapped_invokeclient_and_trusted_values(self):
        src = self.root / "src"
        src.mkdir()
        (src / "a.server.luau").write_text(
            "Remotes.Buy.OnServerEvent:Connect(function(player, item, price)\nend)\n"
            "Remotes.Ask.OnServerInvoke = function(player) end\n"
            "local answer = Remotes.Poll:InvokeClient(player)\n"
            "-- Remotes.Old.OnServerEvent:Connect(function() end)\n")
        (src / "b.client.luau").write_text("Remotes.Buy:FireServer(itemId, price)\nRemotes.Equip:FireServer(slot)\n")
        r = forge.audit_remotes(str(src))
        self.assertFalse(r["ok"])
        self.assertEqual(r["handlers"], 2, "commented-out handler ignored")
        issues = [f["issue"] for f in r["findings"]]
        self.assertEqual(sum("without a validation wrapper" in i for i in issues), 2)
        self.assertEqual(sum("InvokeClient" in i for i in issues), 1)
        self.assertEqual(sum("server should compute" in i for i in issues), 1)

    def test_wrapper_on_next_line_counts(self):
        f = self.root / "c.luau"
        f.write_text("Remotes.X.OnServerEvent:Connect(\n\tRemoteGuard.wrap({}, function(player) end)\n)\n")
        self.assertTrue(forge.audit_remotes(str(f))["ok"])


class OddsAndBudgetTests(unittest.TestCase):
    def test_exact_odds(self):
        r = forge.check_odds([{"name": "Common", "percent": 70}, {"name": "Rare", "percent": 25},
                              {"name": "Epic", "percent": 5}])
        self.assertTrue(r["ok"])
        self.assertEqual(r["display"], ["Common: 70%", "Rare: 25%", "Epic: 5%"])
        self.assertFalse(r["disclaimer_required"])

    def test_rounded_odds_need_flag_and_disclaimer(self):
        thirds = [{"name": n, "percent": 33.3} for n in "ABC"]
        self.assertFalse(forge.check_odds(thirds)["ok"])
        r = forge.check_odds(thirds, rounded=True)
        self.assertTrue(r["ok"])
        self.assertTrue(r["disclaimer_required"])
        self.assertFalse(forge.check_odds([{"name": "A", "percent": 90}], rounded=True)["ok"])

    def test_bad_outcomes(self):
        r = forge.check_odds([{"name": "A", "percent": 50}, {"name": "A", "percent": 50},
                              {"name": "", "percent": True}, {"name": "B", "percent": -1}])
        self.assertFalse(r["ok"])
        text = " ".join(r["problems"])
        self.assertIn("duplicate", text)
        self.assertIn("missing name", text)
        self.assertIn("above 0", text)
        self.assertFalse(forge.check_odds([])["ok"])

    def test_datastore_budget(self):
        r = forge.datastore_budget(10, autosave_seconds=60, joins_per_minute=2)
        self.assertEqual(r["budget_per_minute"], 460)
        self.assertEqual(r["estimated_writes_per_minute"], 14.0)  # 10 autosaves + 2 loads + 2 releases
        self.assertEqual(r["status"], "comfortable")
        over = forge.datastore_budget(1, autosave_seconds=0.5, joins_per_minute=0)
        self.assertFalse(over["ok"])
        self.assertEqual(over["status"], "over budget")
        self.assertFalse(forge.datastore_budget(0)["ok"])


class MapRemotesTests(ForgeTestCase):
    def test_template_remote_is_declared_fired_and_handled(self):
        dest = self.root / "game"
        forge.create_project(str(dest), "Game")
        r = forge.map_remotes(str(dest))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["findings"], [])
        [remote] = r["remotes"]
        self.assertEqual((remote["name"], remote["class"]), ("ClaimDaily", "RemoteEvent"))
        self.assertEqual(remote["fired"], ["src/client/Main.client.luau:47 (FireServer)"])
        self.assertEqual(remote["handled"], ["src/server/Main.server.luau:52 (OnServerEvent)"])

    def test_mismatches(self):
        remotes = {"$className": "Folder", **{n: {"$className": c} for n, c in (
            ("Buy", "RemoteEvent"), ("Ask", "RemoteFunction"), ("Notify", "RemoteEvent"), ("Unused", "RemoteEvent"))}}
        d = self.project({"$className": "DataModel", "ReplicatedStorage": {
            "$className": "ReplicatedStorage", "Remotes": remotes, "Shared": {"$path": "src/shared"}}}, {
            "src/shared/Ping.model.json": json.dumps({"ClassName": "RemoteEvent"}),
            "src/server/Main.server.luau": (
                'local Remotes = game:GetService("ReplicatedStorage").Remotes\n'
                "Remotes.Buy.OnServerEvent:Connect(function(player) end)\n"
                "Remotes.Ask:FireClient(player)\n"
                'Remotes.Notify:FireAllClients("hi")\n'
                'local made = Instance.new("RemoteEvent")\n'
                'made.Name = "Made"\n'
                "made.OnServerEvent:Connect(function() end)\n"
                "-- Remotes.Ghost:FireServer()\n"),
            "src/client/Main.client.luau": (
                'local remotes = game:GetService("ReplicatedStorage"):WaitForChild("Remotes")\n'
                'local buy = remotes:WaitForChild("Buy") :: RemoteEvent\n'
                "buy:FireServer(1)\n"
                'remotes:WaitForChild("Ping"):FireServer()\n'
                "remotes.Typo:FireServer()\n"
                "self.remote:FireServer()\n"),
        })
        r = forge.map_remotes(str(d))
        self.assertFalse(r["ok"])
        found = {(f["severity"], f["remote"], f["issue"].split(" at ")[0].split(",")[0]) for f in r["findings"]}
        self.assertEqual(found, {
            ("high", "Ask", "declared as RemoteFunction but used with FireClient"),
            ("medium", "Ask", "fired to the client"),
            ("medium", "Notify", "fired to the client"),
            ("low", "Made", "has a server handler"),
            ("low", "Unused", "declared but never used"),
            ("high", "Ping", "fired to the server"),
            ("medium", "Typo", "fired to the server"),
            ("medium", "Typo", "used in code but not declared in a project or model file or by Instance.new"),
            ("low", None, "1 remote uses whose name couldn't be resolved"),
        })
        by_name = {x["name"]: x for x in r["remotes"]}
        self.assertNotIn("Ghost", by_name)  # commented out
        self.assertEqual(by_name["Buy"]["fired"], ["src/client/Main.client.luau:3 (FireServer)"])
        self.assertEqual(by_name["Ping"]["declared"], ["src/shared/Ping.model.json"])
        self.assertEqual(by_name["Made"]["declared"], ["src/server/Main.server.luau:5"])

    def test_remotes_created_in_a_loop_skip_the_undeclared_check(self):
        f = self.root / "Remotes.server.luau"
        f.write_text('for _, name in { "Buy", "Sell" } do\n\tremotes[name] = Instance.new("RemoteEvent")\nend\n'
                     "remotes.Buy.OnServerEvent:Connect(function() end)\n")
        r = forge.map_remotes(str(f))
        self.assertEqual([x["issue"] for x in r["findings"]],
                         ["has a server handler at Remotes.server.luau:4, but nothing fires it"])
        self.assertTrue(any("without a literal Name" in n for n in r["notes"]))
        self.assertFalse(forge.map_remotes(str(self.root / "missing"))["ok"])


class AuditFeelTests(ForgeTestCase):
    def test_template_button_gives_feedback(self):
        dest = self.root / "game"
        forge.create_project(str(dest), "Game")
        r = forge.audit_feel(str(dest))
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["actions"], r["with_feedback"]), (1, 1))

    def test_handlers_with_and_without_feedback(self):
        f = self.root / "Ui.client.luau"
        f.write_text("\n".join([
            "local Hud = require(script.Parent.Hud)",
            "local function pop(button)",
            "\tbutton.Size = UDim2.fromScale(0.3, 0.1)",
            "end",
            "local function onJump(_, state)",
            "\tif state == Enum.UserInputState.Begin then",
            "\t\tpop(jumpButton)",
            "\tend",
            "end",
            "local function quiet(x)",
            "\tlocal v = if x then 1 else 2",
            "\treturn v",
            "end",
            "a.Activated:Connect(function()",  # 14: only asks the server
            "\tremote:FireServer()",
            "end)",
            "b.Activated:Connect(function() pop(b) end)",  # 17: feedback through a local function
            'ContextActionService:BindAction("Jump", onJump, true, Enum.KeyCode.Space)',  # 18: callback reference
            "c.Activated:Connect(function() Hud.refresh(c) end)",  # 19: may happen in the module
            "d.Activated:Connect(quiet)",  # 20: the if-expression must not swallow the rest of the file
            'e.Activated:Connect(function() print("x.Visible = true") -- tween:Play()',  # 21: text and comments
            "end)",
            'f.Touched:Connect(function(hit) hit.Parent.Humanoid.Health = 0 end)',  # 23: damage is visible
            'g.Triggered:Connect(function() local s = Instance.new("Sound") s.Parent = g end)',  # 24
            "g.Visible = true",
        ]) + "\n")
        r = forge.audit_feel(str(f))
        self.assertFalse(r["ok"])
        self.assertEqual(r["actions"], 8)
        self.assertEqual(r["with_feedback"], 4)
        self.assertEqual([x["where"] for x in r["findings"]], ["Ui.client.luau:14", "Ui.client.luau:20",
                                                               "Ui.client.luau:21"])
        self.assertEqual(r["unverified"], [{"where": "Ui.client.luau:19", "action": "Activated",
                                            "feedback_may_be_in": ["Hud"]}])
        self.assertFalse(forge.audit_feel(str(self.root / "missing"))["ok"])


class StudioCatalogTests(ForgeTestCase):
    def fake_studio(self, classes: list[str]) -> Path:
        res = self.root / "Studio.app" / "Contents" / "Resources"
        (res / "content" / "api_docs").mkdir(parents=True)
        docs = {f"@roblox/globaltype/{c}": {"documentation": "text that must not be copied", "keys": {}}
                for c in classes}
        docs["@roblox/globaltype/ParticleEmitter"]["keys"] = {"Rate": "@roblox/globaltype/ParticleEmitter.Rate"}
        docs["@roblox/globaltype/GuiButton.Activated.Connect"] = {"documentation": "an event"}
        (res / "content" / "api_docs" / "en-us.json").write_text(json.dumps(docs))
        (res / "ReflectionMetadata.xml").write_text(
            '<roblox><Item class="ReflectionMetadataClasses"><Item class="ReflectionMetadataClass">'
            '<Properties><string name="Name">ParticleEmitter</string></Properties>'
            '<Item class="ReflectionMetadataProperties"><Item class="ReflectionMetadataMember"><Properties>'
            '<string name="Name">Rate</string><double name="UIMinimum">0</double><double name="UIMaximum">100.5'
            '</double></Properties></Item><Item class="ReflectionMetadataMember"><Properties>'
            '<string name="Name">Old</string><bool name="Deprecated">true</bool></Properties></Item></Item>'
            '</Item></Item></roblox>')
        for rel in ("textures/particles/spark.dds", "sounds/hit.ogg"):
            (res / "content" / rel).parent.mkdir(parents=True, exist_ok=True)
            (res / "content" / rel).write_bytes(b"")
        with (res.parent / "Info.plist").open("wb") as f:
            plistlib.dump({"CFBundleShortVersionString": "1.2.3"}, f)
        return res.parent.parent

    def test_extracts_names_ranges_and_paths_only(self):
        catalog = studio_catalog.extract(self.fake_studio(list(studio_catalog.PARENTS)))
        self.assertEqual(catalog["studio_version"], "1.2.3")
        emitter = catalog["classes"]["ParticleEmitter"]
        self.assertEqual((emitter["parent"], emitter["members"], emitter["ranges"], emitter["deprecated"]),
                         ("Instance", ["Rate"], {"Rate": [0, 100.5]}, ["Old"]))
        self.assertEqual(catalog["classes"]["GuiButton"]["members"], ["Activated"], "events come from own entries")
        self.assertEqual(catalog["builtin_assets"], {"particle_textures": ["rbxasset://textures/particles/spark.dds"],
                                                     "sounds": ["rbxasset://sounds/hit.ogg"]})
        self.assertNotIn("must not be copied", json.dumps(catalog))
        self.assertIn("| ParticleEmitter | Rate | 0 to 100.5 |", studio_catalog.reference(catalog))

    def test_missing_class_or_install_fails(self):
        with self.assertRaises(SystemExit):
            studio_catalog.extract(self.fake_studio(["Instance", "ParticleEmitter"]))
        with self.assertRaises(SystemExit):
            studio_catalog.extract(self.root / "nowhere")

    def test_committed_reference_matches_committed_catalog(self):
        catalog = json.loads(studio_catalog.CATALOG.read_text())
        self.assertEqual(studio_catalog.REFERENCE.read_text(), studio_catalog.reference(catalog))
        self.assertEqual(set(catalog["classes"]), set(studio_catalog.PARENTS))


class AuditPolishTests(ForgeTestCase):
    def test_template_is_clean(self):
        dest = self.root / "game"
        forge.create_project(str(dest), "Game")
        r = forge.audit_polish(str(dest))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["findings"], [])
        self.assertGreaterEqual(r["instances"], 6)

    def test_findings(self):
        f = self.root / "Fx.client.luau"
        f.write_text("\n".join([
            'local emitter = Instance.new("ParticleEmitter")',
            "emitter.Color = Color3.new(1, 0, 0)",  # 2: needs a ColorSequence
            "emitter.Lifetime = 2",  # 3: needs a NumberRange
            "emitter.Glow = 1",  # 4: no such member
            "emitter.LightEmission = 3",  # 5: outside 0 to 1
            'local s = Instance.new("Sound")',  # 6: no SoundId
            "s.Volume = 0.5",
            'local music: Sound = Instance.new("Sound")',  # 8: no SoundGroup
            'music.SoundId = "rbxasset://sounds/oof.ogg"',
            'local label = Instance.new("TextLabel")',  # 10: TextScaled without a size limit
            "label.TextScaled = true",
            "label.Font = Enum.Font.Legacy",  # 12: dated font
            "label.Draggable = true",  # 13: deprecated on GuiObject
            'local fx = Instance.new("ParticleEmitter")',  # 14: default look
            "fx.Parent = workspace",
            'local tex = "rbxasset://textures/particles/glow_main.dds"',  # 16: not a built-in file
            "local function other()",
            '\tlocal emitter = Instance.new("Beam")',  # the same name, now a Beam
            "\temitter.Width0 = 1",
            "\temitter.Color = ColorSequence.new(Color3.new(1, 1, 1))",
            "end",
            "-- emitter.Bogus = 1",
            'local unknown = Instance.new("IntValue")',  # not in the catalog: skipped
            "unknown.Anything = 1",
        ]) + "\n")
        r = forge.audit_polish(str(f))
        self.assertFalse(r["ok"])
        got = {(x["where"].split(":")[1], x["severity"]) for x in r["findings"]}
        self.assertEqual(got, {("2", "high"), ("3", "high"), ("4", "high"), ("5", "low"), ("6", "medium"),
                               ("8", "low"), ("10", "low"), ("12", "low"), ("13", "medium"), ("14", "low"),
                               ("16", "high")})
        self.assertEqual([x["severity"] for x in r["findings"]][:4], ["high"] * 4, "most severe first")
        self.assertFalse(forge.audit_polish(str(self.root / "missing"))["ok"])

    def test_names_follow_their_latest_declaration(self):
        f = self.root / "Ui.client.luau"
        f.write_text("\n".join([
            'local object = Instance.new("Frame")',
            "object.Size = UDim2.fromScale(1, 1)",
            "local function button(parent: Instance, object: TextButton, done: () -> ())",
            "\tobject.TextColor3 = Color3.new(1, 1, 1)",  # a parameter, not the Frame
            "end",
            "local object = UI.label(gui)",
            "object.TextSize = 14",  # rebound to something else
            "for _, object in labels do",
            "\tobject.Text = 'x'",  # a loop variable
            "end",
            "local a, object: TextLabel = 1, makeLabel()",
            "object.TextScaled = false",
        ]) + "\n")
        self.assertEqual(forge.audit_polish(str(f))["findings"], [])


class VfxRecipeTests(ForgeTestCase):
    def test_every_recipe_matches_the_catalog_and_audits_clean(self):
        for effect in forge.RECIPES:
            with self.subTest(effect=effect):
                self.assertEqual(forge._check_recipe(effect), [])
                r = forge.vfx_recipe(effect)
                self.assertTrue(r["ok"], r)
                f = self.root / f"{effect}.luau"
                f.write_text(r["code"])
                audit = forge.audit_polish(str(f))
                self.assertEqual(audit["findings"], [], audit)
                builtin = forge._catalog()["builtin_assets"]["particle_textures"]
                self.assertTrue(set(r["builtin_textures"]) <= set(builtin))

    @unittest.skipUnless(shutil.which("luau-compile"), "luau-compile not installed")
    def test_recipes_compile(self):
        for effect in forge.RECIPES:
            f = self.root / f"{effect}.luau"
            f.write_text(forge.vfx_recipe(effect, "#123abc")["code"])
            proc = subprocess.run(["luau-compile", "--text", str(f)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{effect}: {proc.stderr}")

    def test_color_and_bad_input(self):
        code = forge.vfx_recipe("hit_spark", "#000000")["code"]
        self.assertIn("Color3.fromRGB(153, 153, 153)), ColorSequenceKeypoint.new(1, Color3.fromRGB(0, 0, 0))", code)
        self.assertFalse(forge.vfx_recipe("hit_spark", "red")["ok"])
        bad = forge.vfx_recipe("fireworks")
        self.assertFalse(bad["ok"])
        self.assertIn("magic_beam", bad["effects"])


class NarrativeTests(ForgeTestCase):
    def test_example_builds_with_runner(self):
        self.assertTrue(narrative.review_story(str(EXAMPLE_DOCS))["ok"])
        out = self.root / "src" / "shared" / "Dialogue.luau"
        built = narrative.build_dialogue(str(EXAMPLE_DOCS), str(out))
        self.assertTrue(built["ok"], built)
        runner = out.parent / "DialogueRunner.luau"
        self.assertEqual(runner.read_text(), narrative.RUNNER.read_text())
        runner.write_text("-- my changes\n")
        self.assertEqual(narrative.build_dialogue(str(EXAMPLE_DOCS), str(out))["runner"],
                         "kept the existing DialogueRunner.luau")
        self.assertEqual(runner.read_text(), "-- my changes\n")
        self.assertTrue(narrative.export_voiceover(str(EXAMPLE_DOCS), str(self.root / "vo.md"))["ok"])
        loc = narrative.export_localization(str(EXAMPLE_DOCS), str(self.root / "loc.csv"), ["es"])
        self.assertEqual(loc["rows"], 19)

    def test_unfinished_text_blocks_builds(self):
        docs = self.root / "docs"
        shutil.copytree(EXAMPLE_DOCS, docs)
        pip = docs / "dialogue" / "pier_kid.md"
        pip.write_text(pip.read_text().replace("See you, Pip.", "Lor" + "em ipsum dolor"))
        review = narrative.review_story(str(docs))
        self.assertFalse(review["ok"])
        self.assertEqual([(f["severity"], f["where"]) for f in review["findings"]],
                         [("high", "dialogue/pier_kid.md:11")])
        for result in (narrative.build_dialogue(str(docs), str(self.root / "D.luau")),
                       narrative.export_voiceover(str(docs), str(self.root / "vo.md")),
                       narrative.export_localization(str(docs), str(self.root / "loc.csv"))):
            self.assertFalse(result["ok"])
        self.assertEqual(list(self.root.glob("*.luau")) + list(self.root.glob("vo.md")), [])


@unittest.skipUnless(shutil.which("luau-analyze"), "luau-analyze not installed")
class LuauCheckTests(ForgeTestCase):
    def test_clean_and_broken_files(self):
        dest = self.root / "game"
        forge.create_project(str(dest), "Game")
        self.assertTrue(forge.luau_check([str(dest / "src/server/PlayerData.luau")])["ok"])
        bad = self.root / "bad.luau"
        bad.write_text("--!strict\nlocal x: number = 'text'\n")
        r = forge.luau_check([str(bad)])
        self.assertFalse(r["ok"])
        self.assertTrue(r["issues"])
        self.assertFalse(forge.luau_check([str(self.root / "missing.luau")])["ok"])


if __name__ == "__main__":
    unittest.main()
