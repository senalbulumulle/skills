"""Tests for the roblox-forge MCP tool logic (mcp/roblox-forge/forge.py). Standard library only."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parent.parent / "mcp" / "roblox-forge" / "forge.py"
_spec = importlib.util.spec_from_file_location("forge", FORGE)
forge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(forge)


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
        self.assertEqual(result["scripts"], {"server": 1, "client": 1, "module": 3})
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
        self.assertEqual(remote["fired"], ["src/client/Main.client.luau:34 (FireServer)"])
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
