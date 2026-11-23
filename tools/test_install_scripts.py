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
SKILLS = sorted(p.parent.name for p in (REPO / "skills").glob("*/*/SKILL.md"))
MOTION = str(REPO / "mcp" / "web-dev" / "motion-forge" / "server.py")

# Emulates the codex subcommands the scripts use. MCP registrations live in $CODEX_HOME/fake-mcp.json.
FAKE_CODEX = textwrap.dedent(f"""\
    #!{sys.executable}
    import json, os, sys
    from pathlib import Path
    state = Path(os.environ["CODEX_HOME"]) / "fake-mcp.json"
    servers = json.loads(state.read_text()) if state.is_file() else {{}}
    args = sys.argv[1:]
    if args[:2] == ["mcp", "get"]:
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

    def mcp(self) -> dict:
        state = self.codex_home / "fake-mcp.json"
        return json.loads(state.read_text()) if state.is_file() else {}

    def test_install_everything_then_uninstall(self):
        other = self.skills_dir() / "someone-elses"
        other.mkdir(parents=True)

        for _ in range(2):  # re-running is safe
            proc = self.run_script("install-codex.sh")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("already registered", proc.stdout)
        installed = sorted(p.name for p in self.skills_dir().iterdir() if p.is_symlink())
        self.assertEqual(installed, SKILLS)
        for name in SKILLS:
            self.assertTrue((self.skills_dir() / name / "SKILL.md").is_file(), name)
        self.assertFalse((self.codex_home / "hooks.json").exists())
        self.assertFalse((self.codex_home / "agents").exists())
        self.assertEqual(sorted(self.mcp()), ["motion-forge"])
        self.assertEqual(self.mcp()["motion-forge"]["args"], ["run", "--quiet", "--script", MOTION])

        proc = self.run_script("uninstall-codex.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual([p.name for p in self.skills_dir().iterdir()], ["someone-elses"])
        self.assertEqual(self.mcp(), {})

    def test_only_installs_the_listed_components(self):
        proc = self.run_script("install-codex.sh", "--only", "mcp")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.skills_dir().exists())
        self.assertIn("motion-forge", self.mcp())
        for removed in ("hooks", "profile"):
            proc = self.run_script("install-codex.sh", "--only", removed)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn(f"unknown component: {removed}", proc.stderr)
        proc = self.run_script("install-codex.sh", "--only=skills,mcp")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(sorted(p.name for p in self.skills_dir().iterdir()), SKILLS)
        proc = self.run_script("install-codex-skills.sh", "no-such-skill")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no such skill", proc.stderr)

    def test_bad_options(self):
        for args in (["--bogus"], ["--only", "skills,nope"], ["--only"], ["--only", ","]):
            proc = self.run_script("install-codex.sh", *args)
            self.assertEqual(proc.returncode, 1, args)
            self.assertIn("error:", proc.stderr)
        proc = self.run_script("install-codex-mcp.sh", "--bogus")
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(self.codex_home.exists())
        proc = self.run_script("install-codex.sh", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--only", proc.stdout)

    def test_a_failed_step_does_not_stop_the_others(self):
        blocker = self.skills_dir()
        blocker.parent.mkdir(parents=True)
        blocker.write_text("not a folder\n")  # the skills step can't create its folder and fails
        proc = self.run_script("install-codex.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("finished with errors", proc.stderr)
        self.assertIn("motion-forge", self.mcp())  # the mcp step still ran
        self.assertEqual(blocker.read_text(), "not a folder\n")

    def test_mcp_name_taken_by_another_server(self):
        self.codex_home.mkdir()
        other = {"motion-forge": {"type": "stdio", "command": "node", "args": ["other.js"]}}
        (self.codex_home / "fake-mcp.json").write_text(json.dumps(other))
        proc = self.run_script("install-codex-mcp.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("runs something else", proc.stderr)
        self.assertEqual(self.mcp(), other)  # the other server is left alone
        proc = self.run_script("install-codex-mcp.sh", "--uninstall")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("left alone", proc.stderr)
        self.assertEqual(self.mcp(), other)

    def test_mcp_category_filter(self):
        proc = self.run_script("install-codex-mcp.sh", "-c", "web-dev")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(list(self.mcp()), ["motion-forge"])
        proc = self.run_script("install-codex-mcp.sh", "-c", "nope")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no such MCP category", proc.stderr)

    def test_mcp_moves_registrations_from_an_older_layout(self):
        old = str(REPO / "mcp" / "motion-forge" / "server.py")
        self.codex_home.mkdir(parents=True, exist_ok=True)
        (self.codex_home / "fake-mcp.json").write_text(json.dumps(
            {"motion-forge": {"type": "stdio", "command": "uv", "args": ["run", "--quiet", "--script", old]}}))
        proc = self.run_script("install-codex-mcp.sh", "-c", "web-dev")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.mcp()["motion-forge"]["args"], ["run", "--quiet", "--script", MOTION])

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
