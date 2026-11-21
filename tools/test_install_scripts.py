"""Tests for the Codex install scripts in scripts/codex/, run against a throwaway HOME and a fake codex.

Run: python3 -m unittest tools/test_install_scripts.py  (needs bash, uv, and python3 3.9+)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts" / "codex"
SKILLS = sorted(p.name for p in (REPO / "skills").iterdir() if (p / "SKILL.md").is_file())
SERVER = str(REPO / "mcp" / "creative-director" / "server.py")
FORGE = str(REPO / "mcp" / "roblox-forge" / "server.py")
MOTION = str(REPO / "mcp" / "motion-forge" / "server.py")

# Emulates the codex subcommands the scripts use. MCP registrations live in $CODEX_HOME/fake-mcp.json.
FAKE_CODEX = textwrap.dedent(f"""\
    #!{sys.executable}
    import json, os, sys
    from pathlib import Path
    state = Path(os.environ["CODEX_HOME"]) / "fake-mcp.json"
    servers = json.loads(state.read_text()) if state.is_file() else {{}}
    args = sys.argv[1:]
    if args[:2] == ["features", "list"]:
        print("hooks                stable             " + os.environ.get("FAKE_HOOKS", "true"))
    elif args[:2] == ["debug", "models"]:
        print(json.dumps({{"models": [
            {{"slug": "gpt-6-luna", "visibility": "list", "supported_reasoning_levels": [{{"effort": "high"}}]}},
            {{"slug": "gpt-6-astra", "visibility": "list", "supported_reasoning_levels": [{{"effort": "high"}}]}}]}}))
    elif args[:2] == ["mcp", "get"]:
        if args[2] not in servers:
            sys.exit(1)
        print(json.dumps({{"name": args[2], "transport": servers[args[2]]}}))
    elif args[:2] == ["mcp", "add"]:
        command = args[args.index("--") + 1:]
        servers[args[2]] = {{"type": "stdio", "command": command[0], "args": command[1:]}}
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(servers))
    elif args[:2] == ["mcp", "remove"]:
        servers.pop(args[2], None)
        state.write_text(json.dumps(servers))
    else:
        sys.exit(f"fake codex: unsupported {{args}}")
    """)


@unittest.skipUnless(shutil.which("uv") and shutil.which("bash"), "needs uv and bash")
class InstallScripts(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.codex_home = self.home / ".codex"
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "codex"
        fake.write_text(FAKE_CODEX)
        fake.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.codex_home),
                    "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def tearDown(self):
        shutil.rmtree(self.home)

    def run_script(self, name, *args, env=None):
        return subprocess.run(["bash", str(SCRIPTS / name), *args], env=env or self.env,
                              capture_output=True, text=True, timeout=300)

    def skills_dir(self) -> Path:
        return self.home / ".agents" / "skills"

    def hooks(self) -> dict:
        return json.loads((self.codex_home / "hooks.json").read_text())["hooks"]

    def mcp(self) -> dict:
        state = self.codex_home / "fake-mcp.json"
        return json.loads(state.read_text()) if state.is_file() else {}

    def test_install_everything_then_uninstall(self):
        other = self.skills_dir() / "someone-elses"
        other.mkdir(parents=True)
        mine = {"type": "command", "command": "echo mine"}
        my_role = self.codex_home / "agents" / "my-role.toml"
        my_role.parent.mkdir(parents=True)
        my_role.write_text('name = "my-role"\n')
        (self.codex_home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [mine]}]}}))

        for _ in range(2):  # re-running is safe
            proc = self.run_script("install-codex.sh")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("already registered", proc.stdout)
        installed = sorted(p.name for p in self.skills_dir().iterdir() if p.is_symlink())
        self.assertEqual(installed, SKILLS)
        for name in SKILLS:
            self.assertTrue((self.skills_dir() / name / "SKILL.md").is_file(), name)
        # Codex variants come from dist/ and carry agents/openai.yaml.
        self.assertTrue((self.skills_dir() / "roblox-scripting" / "agents" / "openai.yaml").is_file())
        hooks = self.hooks()
        self.assertEqual(sorted(hooks), ["PostToolUse", "PreToolUse", "SessionStart", "Stop", "UserPromptSubmit"])
        self.assertIn(mine, [h for g in hooks["Stop"] for h in g["hooks"]])
        self.assertEqual(sum("game_hooks.py" in h["command"] for g in hooks["Stop"] for h in g["hooks"]), 1)
        profile = (self.codex_home / "game.config.toml").read_text()
        self.assertIn('model = "gpt-6-astra"', profile)
        self.assertEqual(sorted(p.name for p in (self.codex_home / "agents").iterdir()),
                         ["game-critic.toml", "game-designer.toml", "my-role.toml", "narrative-designer.toml",
                          "roblox-polisher.toml"])
        self.assertEqual(self.mcp()["creative-director"]["args"], ["run", "--quiet", "--script", SERVER])
        self.assertEqual(self.mcp()["roblox-forge"]["args"], ["run", "--quiet", "--script", FORGE])
        self.assertEqual(self.mcp()["motion-forge"]["args"], ["run", "--quiet", "--script", MOTION])

        proc = self.run_script("uninstall-codex.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual([p.name for p in self.skills_dir().iterdir()], ["someone-elses"])
        self.assertEqual(self.hooks(), {"Stop": [{"hooks": [mine]}]})
        self.assertFalse((self.codex_home / "game.config.toml").exists())
        self.assertEqual([p.name for p in (self.codex_home / "agents").iterdir()], ["my-role.toml"])
        self.assertEqual(self.mcp(), {})

    def test_only_installs_the_listed_components(self):
        proc = self.run_script("install-codex.sh", "--only", "hooks")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.skills_dir().exists())
        self.assertFalse((self.codex_home / "game.config.toml").exists())
        self.assertIn("PreToolUse", self.hooks())
        proc = self.run_script("install-codex.sh", "--only=skills,mcp")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.skills_dir() / "game-feel").is_symlink())
        self.assertIn("creative-director", self.mcp())
        self.assertFalse((self.codex_home / "game.config.toml").exists())
        proc = self.run_script("install-codex-skills.sh", "game-art")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("exists", proc.stdout)

    def test_dry_runs_write_nothing(self):
        proc = self.run_script("install-codex-hooks.sh", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('"UserPromptSubmit"', proc.stdout)
        proc = self.run_script("install-codex-profile.sh", "--dry-run", "--model", "gpt-6-luna")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('model = "gpt-6-luna"', proc.stdout)
        self.assertFalse(self.codex_home.exists())

    def test_bad_options(self):
        for args in (["--bogus"], ["--only", "skills,nope"], ["--only"], ["--only", ","]):
            proc = self.run_script("install-codex.sh", *args)
            self.assertEqual(proc.returncode, 1, args)
            self.assertIn("error:", proc.stderr)
        proc = self.run_script("install-codex-mcp.sh", "--bogus")
        self.assertEqual(proc.returncode, 1)
        proc = self.run_script("install-codex-profile.sh", "--model", "gpt-unknown")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not in this Codex's model list", proc.stderr)
        self.assertFalse(self.codex_home.exists())
        proc = self.run_script("install-codex.sh", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--only", proc.stdout)

    def test_a_failed_step_does_not_stop_the_others(self):
        foreign = self.skills_dir() / "game-feel"
        foreign.mkdir(parents=True)  # not ours: the skills step reports it and fails
        my_profile = self.codex_home / "game.config.toml"
        my_profile.parent.mkdir()
        my_profile.write_text('model = "mine"\n')  # not ours either: the profile step refuses it
        proc = self.run_script("install-codex.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not from this repo", proc.stderr)
        self.assertIn("was not installed by this script", proc.stderr)
        self.assertEqual(my_profile.read_text(), 'model = "mine"\n')
        self.assertFalse((self.codex_home / "agents").exists())  # the profile step changes nothing on refusal
        self.assertIn("PreToolUse", self.hooks())
        self.assertIn("creative-director", self.mcp())
        self.assertTrue(foreign.is_dir() and not foreign.is_symlink())

    def test_mcp_name_taken_by_another_server(self):
        self.codex_home.mkdir()
        other = {"creative-director": {"type": "stdio", "command": "node", "args": ["other.js"]}}
        (self.codex_home / "fake-mcp.json").write_text(json.dumps(other))
        proc = self.run_script("install-codex-mcp.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("runs something else", proc.stderr)
        self.assertIn("roblox-forge", self.mcp())  # the other server is still registered
        proc = self.run_script("install-codex-mcp.sh", "--uninstall")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("left alone", proc.stderr)
        self.assertEqual(self.mcp(), other)

    def test_warns_when_codex_hooks_are_off(self):
        env = {**self.env, "FAKE_HOOKS": "false"}
        proc = self.run_script("install-codex-hooks.sh", "--dry-run", env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("codex features enable hooks", proc.stderr)
        self.assertNotIn("turned off", self.run_script("install-codex-hooks.sh", "--dry-run").stderr)

    def test_missing_tool_fails_before_changing_anything(self):
        bin_dir = self.home / "minimal-bin"
        bin_dir.mkdir()
        for tool in ("bash", "dirname", "awk", "tr", "python3"):  # everything except uv and codex
            os.symlink(shutil.which(tool), bin_dir / tool)
        env = {**self.env, "PATH": str(bin_dir)}
        proc = self.run_script("install-codex.sh", env=env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("uv is required", proc.stderr)
        os.symlink(shutil.which("uv"), bin_dir / "uv")
        proc = self.run_script("install-codex.sh", env=env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("codex is required", proc.stderr)
        self.assertFalse(self.codex_home.exists())
        self.assertFalse(self.skills_dir().exists())


if __name__ == "__main__":
    unittest.main()
