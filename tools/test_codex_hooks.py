"""Tests for platforms/codex/hooks: game_hooks.py, install.py, discover.py.

Run: python3 -m unittest tools/test_codex_hooks.py
The hook runs as a subprocess with JSON on stdin, exactly as Codex runs it.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "platforms" / "codex" / "hooks"
sys.path.insert(0, str(HOOKS))
import discover  # noqa: E402
import install as install_module  # noqa: E402

class install:  # noqa: N801  run the installer quietly
    @staticmethod
    def main(argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return install_module.main(argv)

UNREAL_GOOD = '''#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyActor.generated.h"

UCLASS()
class AMyActor : public AActor
{
    GENERATED_BODY()
};
'''


def write(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_unreal(root: Path, assoc: str = "5.4") -> Path:
    write(root, "MyGame.uproject", json.dumps({"FileVersion": 3, "EngineAssociation": assoc}))
    write(root, "Content/Maps/Main.umap")
    write(root, "Config/DefaultEngine.ini")
    return root


def make_unity(root: Path, version: str = "2022.3.10f1") -> Path:
    write(root, "ProjectSettings/ProjectVersion.txt", f"m_EditorVersion: {version}\n")
    write(root, "Assets/Scripts/Player.cs", "public class Player {}\n")
    write(root, "Assets/Scripts/Player.cs.meta", "guid: 123\n")
    return root


def make_godot(root: Path, major: int = 4) -> Path:
    if major == 4:
        write(root, "project.godot", 'config_version=5\n[application]\nconfig/features=PackedStringArray("4.3", "Forward Plus")\n')
    else:
        write(root, "project.godot", "config_version=4\n[application]\n")
    return root


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "game"
        self.root.mkdir()
        (self.root / ".git").mkdir()  # stop project search here, like a real repository

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_hook(self, event: str, payload: dict, raw: str = None):
        payload = {"hook_event_name": event, "cwd": str(self.root), **payload}
        proc = subprocess.run([sys.executable, str(HOOKS / "game_hooks.py"), event],
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def bash(self, command: str):
        return self.run_hook("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": command}})

    def patch(self, body: str, event: str = "PreToolUse"):
        return self.run_hook(event, {"tool_name": "apply_patch",
                                     "tool_input": {"command": f"*** Begin Patch\n{body}\n*** End Patch"}})

    def assertDenied(self, out, fragment: str = ""):
        self.assertIsNotNone(out, "expected a denial")
        spec = out["hookSpecificOutput"]
        self.assertEqual(spec["hookEventName"], "PreToolUse")
        self.assertEqual(spec["permissionDecision"], "deny")
        self.assertIn(fragment, spec["permissionDecisionReason"])
        self.assertFalse(spec["permissionDecisionReason"].endswith("."), "Codex appends its own period")

    def assertAllowed(self, out):
        if out is not None:
            self.assertNotIn("permissionDecision", out.get("hookSpecificOutput", {}), out)

    def context(self, out) -> str:
        self.assertIsNotNone(out, "expected additionalContext")
        return out["hookSpecificOutput"]["additionalContext"]


class Detection(HookCase):
    def start(self):
        return self.run_hook("SessionStart", {"source": "startup"})

    def test_engines_and_versions(self):
        cases = [
            (lambda r: make_unreal(r), "Unreal Engine 5.4"),
            (lambda r: make_unreal(r, "{1D2F-GUID}"), "Unreal Engine source build"),
            (lambda r: make_unity(r), "Unity 2022.3.10f1"),
            (lambda r: make_godot(r, 4), "Godot 4.3"),
            (lambda r: make_godot(r, 3), "Godot 3"),
            (lambda r: write(r, "Cargo.toml", '[dependencies]\nbevy = "0.14"\n'), "Bevy 0.14"),
            (lambda r: write(r, "Cargo.toml", '[dependencies]\nbevy = { version = "0.15", features = [] }\n'), "Bevy 0.15"),
            (lambda r: write(r, "game.project", "[project]\n"), "Defold"),
            (lambda r: write(r, "G.yyp", "{}"), "GameMaker"),
            (lambda r: write(r, "G.csproj", '<PackageReference Include="MonoGame.Framework.DesktopGL" />'), "MonoGame"),
            (lambda r: write(r, "main.lua", "function love.draw() end"), "LÖVE"),
            (lambda r: write(r, "package.json", json.dumps({"dependencies": {"phaser": "^3.80.0"}})), "Web game phaser ^3.80.0"),
            (lambda r: write(r, "requirements.txt", "pygame-ce==2.5\n"), "Pygame"),
        ]
        for build, expected in cases:
            with self.subTest(expected):
                for child in self.root.iterdir():
                    if child.name != ".git":
                        shutil.rmtree(child) if child.is_dir() else child.unlink()
                build(self.root)
                self.assertIn(expected + " project", self.context(self.start()))

    def test_not_a_game_is_silent(self):
        write(self.root, "package.json", json.dumps({"dependencies": {"react": "18"}}))
        write(self.root, "main.lua", "print('hi')")
        self.assertIsNone(self.start())

    def test_subdirectory_and_monorepo(self):
        make_unity(self.root / "client")
        make_godot(self.root / "server")
        text = self.context(self.start())
        self.assertIn("Unity", text)
        self.assertIn("Godot", text)
        self.root = self.root / "client" / "Assets"
        text = self.context(self.start())
        self.assertIn("Unity", text)
        self.assertNotIn("Godot", text)

    def test_bad_input_fails_open(self):
        self.assertIsNone(self.run_hook("PreToolUse", {}, raw="not json"))
        self.assertIsNone(self.run_hook("PreToolUse", {"tool_name": "Bash", "tool_input": "oops"}))
        proc = subprocess.run([sys.executable, str(HOOKS / "game_hooks.py"), "Nope"], input="{}",
                              capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))


class BashGuards(HookCase):
    def test_publishing_is_denied_everywhere(self):
        for cmd in ["cd build && steamcmd +login u +run_app_build app.vdf +quit",
                    "butler push dist me/game:web", "xcrun altool --upload-app -f g.ipa",
                    "sudo BuildPatchTool -mode=UploadBinary", "FOO=1 butler push dist me/game:web"]:
            with self.subTest(cmd):
                self.assertDenied(self.bash(cmd), "ask the user")

    def test_mentioning_a_publish_command_is_allowed(self):
        for cmd in ['grep -n "butler push" README.md', "butler status me/game", "echo butler push",
                    "steamcmd +login anonymous +quit"]:
            with self.subTest(cmd):
                self.assertAllowed(self.bash(cmd))

    def test_text_writes_into_binary_assets(self):
        for cmd in ["sed -i '' 's/a/b/' Content/Hero.uasset", "echo x > Maps/Main.umap",
                    "perl -pi -e 's/a/b/' Content/Level.umap", "cat a | tee model.blend", "printf x >> scene.blend"]:
            with self.subTest(cmd):
                self.assertDenied(self.bash(cmd), "Binary engine assets")
        for cmd in ["cp Content/A.uasset Content/B.uasset", "sed -n 1p notes.txt", "git checkout -- Main.umap",
                    "sed -i '' s/a/b/ notes.txt"]:
            with self.subTest(cmd):
                self.assertAllowed(self.bash(cmd))

    def test_unity_deletes(self):
        make_unity(self.root)
        for cmd in ["rm -rf Assets", "rm -rf ./Assets/", "rm -rf Assets/*", "rm -r ProjectSettings",
                    "rm Packages/manifest.json", "rm -rf .", "rm Assets/Scripts/Player.cs.meta",
                    "git rm Assets/Scripts/Player.cs.meta", "cd Assets && rm -rf ../ProjectSettings"]:
            with self.subTest(cmd):
                self.assertDenied(self.bash(cmd))
        for cmd in ["rm -rf Library Temp obj", "rm Assets/Scripts/Player.cs Assets/Scripts/Player.cs.meta",
                    "rm Assets/*.tmp", "rm -rf Assets/Old", "rm -f build.log"]:
            with self.subTest(cmd):
                self.assertAllowed(self.bash(cmd))

    def test_unreal_and_godot_deletes(self):
        make_unreal(self.root)
        self.assertDenied(self.bash("rm -rf Content"), "Content")
        self.assertDenied(self.bash("rm MyGame.uproject"), "MyGame.uproject")
        self.assertAllowed(self.bash("rm -rf Binaries Intermediate Saved DerivedDataCache"))
        self.assertAllowed(self.bash("rm Content/Maps/Main.umap"))
        (self.root / "MyGame.uproject").unlink()
        make_godot(self.root)
        self.assertDenied(self.bash("rm project.godot"), "project.godot")
        self.assertAllowed(self.bash("rm -rf .godot"))

    def test_outside_a_game_project_only_global_rules_apply(self):
        self.assertAllowed(self.bash("rm -rf Assets ProjectSettings"))
        self.assertDenied(self.bash("butler push dist me/game:web"))

    def test_unparsable_command(self):
        self.assertAllowed(self.bash("echo 'unterminated"))
        self.assertDenied(self.bash("echo 'x > Hero.uasset"), "Binary")


class PatchGuards(HookCase):
    def test_binary_assets(self):
        self.assertDenied(self.patch("*** Update File: Content/Hero.uasset\n@@\n-a\n+b"), "binary")
        self.assertDenied(self.patch("*** Add File: scene.blend\n+x"), "binary")
        self.assertAllowed(self.patch("*** Delete File: Content/Old.uasset"))

    def test_generated_folders(self):
        make_unreal(self.root)
        for rel in ["Intermediate/Build/x.h", "Source/MyGame/MyActor.generated.h", "Binaries/Mac/x.txt",
                    "Plugins/Tool/Binaries/x.txt", "Saved/Config/x.ini"]:
            with self.subTest(rel):
                self.assertDenied(self.patch(f"*** Add File: {rel}\n+x"), "generated")
        self.assertAllowed(self.patch("*** Add File: Source/MyGame/MyActor.cpp\n+x"))
        self.assertAllowed(self.patch("*** Delete File: Intermediate/old.txt"))

    def test_unity_meta_files(self):
        make_unity(self.root)
        self.assertDenied(self.patch("*** Delete File: Assets/Scripts/Player.cs.meta"), "GUID")
        self.assertAllowed(self.patch("*** Delete File: Assets/Scripts/Player.cs\n*** Delete File: Assets/Scripts/Player.cs.meta"))
        self.assertIn("Player.cs.meta", self.context(self.patch("*** Delete File: Assets/Scripts/Player.cs")))
        moved = self.patch("*** Update File: Assets/Scripts/Player.cs\n*** Move to: Assets/Game/Player.cs\n@@\n-a\n+a")
        self.assertIn("Move Player.cs.meta", self.context(moved))
        self.assertDenied(self.patch("*** Add File: Library/x.txt\n+x"), "Library")
        self.assertIn("Let Unity create it", self.context(self.patch("*** Add File: Assets/Scripts/New.cs.meta\n+guid: 1")))

class PostChecks(HookCase):
    def post(self, rel: str, text: str):
        write(self.root, rel, text)
        out = self.patch(f"*** Add File: {rel}\n+x", event="PostToolUse")
        return out["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_unreal_headers(self):
        make_unreal(self.root)
        self.assertEqual(self.post("Source/G/MyActor.h", UNREAL_GOOD), "")
        missing = self.post("Source/G/MyActor.h", UNREAL_GOOD.replace('#include "MyActor.generated.h"\n', ""))
        self.assertIn('add #include "MyActor.generated.h"', missing)
        late = UNREAL_GOOD.replace('#include "MyActor.generated.h"\n', "") .replace(
            "\nUCLASS", '#include "MyActor.generated.h"\n#include "Late.h"\n\nUCLASS')
        self.assertIn("must be the last #include", self.post("Source/G/MyActor.h", late))
        self.assertIn("GENERATED_BODY", self.post("Source/G/MyActor.h", UNREAL_GOOD.replace("GENERATED_BODY()", "")))
        self.assertEqual(self.post("Source/G/Plain.h", "// UCLASS()\n#pragma once\n"), "")
        warn = self.post("Source/G/X.cpp", "void F() { auto* O = new UThing(); auto* A = new AEnemy; }")
        self.assertIn("NewObject", warn)
        self.assertIn("SpawnActor", warn)

    def test_unity_scripts(self):
        make_unity(self.root, "6000.0.23f1")
        self.assertIn("error: UnityEditor", self.post("Assets/Scripts/Tool.cs", "using UnityEditor;\nclass Tool {}"))
        self.assertEqual(self.post("Assets/Editor/Tool.cs", "using UnityEditor;\nclass Tool {}"), "")
        self.assertEqual(self.post("Assets/Scripts/Tool.cs", "#if UNITY_EDITOR\nusing UnityEditor;\n#endif\nclass Tool {}"), "")
        write(self.root, "Assets/Tools/Tools.Editor.asmdef", json.dumps({"name": "T", "includePlatforms": ["Editor"]}))
        self.assertEqual(self.post("Assets/Tools/Tool.cs", "using UnityEditor;\nclass Tool {}"), "")
        self.assertIn("named Enemy.cs", self.post("Assets/Scripts/Foe.cs", "public class Enemy : MonoBehaviour {}"))
        self.assertEqual(self.post("Assets/Scripts/Base.cs", "public abstract class Unit : MonoBehaviour {}"), "")
        self.assertIn("FindFirstObjectByType", self.post("Assets/Scripts/Find.cs", "class Find { void A() { FindObjectOfType<Find>(); } }"))

    def test_unity_find_is_fine_before_2023(self):
        make_unity(self.root, "2022.3.10f1")
        self.assertEqual(self.post("Assets/Scripts/Find.cs", "class Find { void A() { FindObjectOfType<Find>(); } }"), "")

    def test_godot_versions(self):
        make_godot(self.root, 4)
        text = self.post("scripts/p.gd", 'extends Node\nonready var a = 1\nexport var b = 2\nfunc f():\n\tyield(get_tree(), "idle_frame")\n'
                                         '\tb.connect("pressed", self, "_on")\n\t# yield( in a comment\n\tprint("yield(")\n')
        self.assertEqual(text.count("error"), 4, text)
        self.assertIn("p.gd:2: error: use @onready", text)
        self.assertEqual(self.post("scripts/ok.gd", "extends Node\n@onready var a = $A\nfunc f():\n\tawait get_tree().process_frame\n"), "")
        make_godot(self.root, 3)
        self.assertIn("@onready is Godot 4 syntax", self.post("scripts/ok.gd", "@onready var a = 1\n"))

    def test_non_engine_files_are_ignored(self):
        self.assertEqual(self.post("notes.md", "wait(1)"), "")


class StopGate(HookCase):
    def test_blocks_once_on_errors_in_changed_files(self):
        shutil.rmtree(self.root / ".git")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        make_unity(self.root)
        self.assertIsNone(self.run_hook("Stop", {"stop_hook_active": False}))
        write(self.root, "Assets/Scripts/Tool.cs", "using UnityEditor;\nclass Tool {}")
        out = self.run_hook("Stop", {"stop_hook_active": False})
        self.assertEqual(out["decision"], "block")
        self.assertIn("Assets/Scripts/Tool.cs:1: error", out["reason"])
        self.assertIsNone(self.run_hook("Stop", {"stop_hook_active": True}))

    def test_warnings_do_not_block(self):
        shutil.rmtree(self.root / ".git")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        make_unity(self.root)
        write(self.root, "Assets/Scripts/Wrong.cs", "using UnityEngine;\nclass Player : MonoBehaviour {}\n")
        self.assertIsNone(self.run_hook("Stop", {"stop_hook_active": False}))


class CreativeBrief(HookCase):
    def prompt(self, text: str):
        return self.run_hook("UserPromptSubmit", {"prompt": text})

    def test_game_requests_get_the_brief_anywhere(self):
        for text in ("Make a roguelike about a lighthouse keeper", "build me a tycoon with 10 upgrades",
                     "Can you create a small platformer game in one HTML file?"):
            self.assertIn("Creative brief", self.context(self.prompt(text)), text)
            self.assertEqual(self.prompt(text)["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

    def test_other_requests_get_nothing(self):
        for text in ("add debug level logging to the API", "what does this game loop do?", "fix the failing test",
                     "make the log level configurable"):
            self.assertIsNone(self.prompt(text), text)

    def test_level_words_count_only_in_a_game_project(self):
        self.assertIsNone(self.prompt("add a new level with moving platforms"))
        make_godot(self.root)
        self.assertIn("Creative brief", self.context(self.prompt("add a new level with moving platforms")))
        self.assertIsNone(self.prompt("fix the crash in level 2"))  # no creative verb


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "codex"
        os.environ["CODEX_HOME"] = str(self.home)

    def tearDown(self):
        os.environ.pop("CODEX_HOME", None)
        shutil.rmtree(self.tmp)

    def config(self, path: Path) -> dict:
        return json.loads(path.read_text())

    def test_user_install_merges_and_is_idempotent(self):
        other = {"type": "command", "command": "echo mine"}
        write(self.home, "hooks.json", json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [other]}]}}))
        for _ in range(2):
            self.assertEqual(install.main(["--user"]), 0)
        hooks = self.config(self.home / "hooks.json")["hooks"]
        self.assertEqual(sorted(hooks), ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"])
        pre = [h for g in hooks["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(len(pre), 2)
        self.assertIn(other, pre)
        ours = [g for g in hooks["PreToolUse"] if g["matcher"] == "^(Bash|apply_patch)$"][0]["hooks"][0]
        self.assertTrue(ours["command"].endswith("game_hooks.py PreToolUse"))
        self.assertEqual(ours["timeout"], 30)
        self.assertEqual(install.main(["--user", "--uninstall"]), 0)
        self.assertEqual(self.config(self.home / "hooks.json"), {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [other]}]}})

    def test_uninstall_of_only_our_hooks_removes_the_file(self):
        install.main(["--user"])
        install.main(["--user", "--uninstall"])
        self.assertFalse((self.home / "hooks.json").exists())

    def test_project_install(self):
        project = self.tmp / "game"
        project.mkdir()
        self.assertEqual(install.main(["--project", str(project)]), 1)  # not a git root
        (project / ".git").mkdir()
        self.assertEqual(install.main(["--project", str(project)]), 0)
        self.assertTrue((project / ".codex" / "hooks" / "game_hooks.py").is_file())
        cmd = self.config(project / ".codex" / "hooks.json")["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertEqual(cmd, 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/game_hooks.py" Stop')
        self.assertEqual(install.main(["--project", str(project), "--uninstall"]), 0)
        self.assertFalse((project / ".codex" / "hooks" / "game_hooks.py").exists())
        self.assertFalse((project / ".codex" / "hooks.json").exists())

    def test_dry_run_and_bad_json(self):
        self.assertEqual(install.main(["--user", "--dry-run"]), 0)
        self.assertFalse((self.home / "hooks.json").exists())
        write(self.home, "hooks.json", "{ broken")
        self.assertEqual(install.main(["--user"]), 1)

    def test_installed_command_runs(self):
        install.main(["--user"])
        cmd = self.config(self.home / "hooks.json")["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        proc = subprocess.run(cmd, shell=True, input=json.dumps(
            {"hook_event_name": "PreToolUse", "cwd": str(self.tmp), "tool_name": "Bash",
             "tool_input": {"command": "butler push dist me/game:web"}}), capture_output=True, text=True)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


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
