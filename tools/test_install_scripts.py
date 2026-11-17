"""Tests for the Codex install scripts in scripts/, run against a throwaway HOME.

Run: python3 -m unittest tools/test_install_scripts.py  (needs bash, uv, and python3 3.9+)
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
SKILLS = sorted(p.name for p in (REPO / "skills").iterdir() if (p / "SKILL.md").is_file())


@unittest.skipUnless(shutil.which("uv") and shutil.which("bash"), "needs uv and bash")
class InstallScripts(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.home / ".codex")}

    def tearDown(self):
        shutil.rmtree(self.home)

    def run_script(self, name, *args, env=None):
        return subprocess.run(["bash", str(SCRIPTS / name), *args], env=env or self.env,
                              capture_output=True, text=True, timeout=300)

    def skills_dir(self) -> Path:
        return self.home / ".agents" / "skills"

    def hooks(self) -> dict:
        return json.loads((self.home / ".codex" / "hooks.json").read_text())["hooks"]

    def test_install_everything_then_uninstall(self):
        other = self.skills_dir() / "someone-elses"
        other.mkdir(parents=True)
        write = self.home / ".codex" / "hooks.json"
        write.parent.mkdir(parents=True)
        mine = {"type": "command", "command": "echo mine"}
        write.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [mine]}]}}))

        for _ in range(2):  # re-running is safe
            proc = self.run_script("install-codex.sh")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        installed = sorted(p.name for p in self.skills_dir().iterdir() if p.is_symlink())
        self.assertEqual(installed, SKILLS)
        for name in SKILLS:
            self.assertTrue((self.skills_dir() / name / "SKILL.md").is_file(), name)
        # Codex variants come from dist/ and carry agents/openai.yaml.
        self.assertTrue((self.skills_dir() / "roblox-scripting" / "agents" / "openai.yaml").is_file())
        hooks = self.hooks()
        self.assertEqual(sorted(hooks), ["PostToolUse", "PreToolUse", "SessionStart", "Stop"])
        self.assertIn(mine, [h for g in hooks["Stop"] for h in g["hooks"]])
        self.assertEqual(sum("game_hooks.py" in h["command"] for g in hooks["Stop"] for h in g["hooks"]), 1)

        proc = self.run_script("uninstall-codex.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual([p.name for p in self.skills_dir().iterdir()], ["someone-elses"])
        self.assertEqual(self.hooks(), {"Stop": [{"hooks": [mine]}]})

    def test_partial_installs(self):
        proc = self.run_script("install-codex.sh", "--hooks-only")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.skills_dir().exists())
        self.assertIn("PreToolUse", self.hooks())
        proc = self.run_script("install-codex.sh", "--skills-only")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.skills_dir() / "game-feel").is_symlink())
        proc = self.run_script("install-codex-skills.sh", "game-art")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("exists", proc.stdout)

    def test_dry_run_writes_nothing(self):
        proc = self.run_script("install-codex-hooks.sh", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('"PreToolUse"', proc.stdout)
        self.assertFalse((self.home / ".codex" / "hooks.json").exists())

    def test_bad_options_and_conflicts(self):
        for args in (["--bogus"], ["--skills-only", "--hooks-only"]):
            proc = self.run_script("install-codex.sh", *args)
            self.assertEqual(proc.returncode, 1, args)
            self.assertIn("error:", proc.stderr)
        self.assertFalse((self.home / ".codex").exists())
        proc = self.run_script("install-codex.sh", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--skills-only", proc.stdout)

    def test_a_failed_step_does_not_stop_the_other(self):
        foreign = self.skills_dir() / "game-feel"
        foreign.mkdir(parents=True)  # not ours: the skills step reports it and fails
        proc = self.run_script("install-codex.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not from this repo", proc.stderr)
        self.assertIn("PreToolUse", self.hooks())
        self.assertTrue(foreign.is_dir() and not foreign.is_symlink())

    def test_warns_when_codex_hooks_are_off(self):
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "codex"
        fake.write_text("#!/bin/sh\necho 'hooks                stable             false'\n")
        fake.chmod(0o755)
        env = {**self.env, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        proc = self.run_script("install-codex-hooks.sh", "--dry-run", env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("codex features enable hooks", proc.stderr)
        fake.write_text("#!/bin/sh\necho 'hooks                stable             true'\n")
        self.assertNotIn("turned off", self.run_script("install-codex-hooks.sh", "--dry-run", env=env).stderr)

    def test_missing_tool_fails_before_changing_anything(self):
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        for tool in ("bash", "dirname", "awk", "python3"):  # everything except uv
            os.symlink(shutil.which(tool), bin_dir / tool)
        proc = self.run_script("install-codex.sh", env={**self.env, "PATH": str(bin_dir)})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("uv is required", proc.stderr)
        self.assertFalse((self.home / ".codex").exists())
        self.assertFalse(self.skills_dir().exists())


if __name__ == "__main__":
    unittest.main()
