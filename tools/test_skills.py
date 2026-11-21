"""Tests for tools/skills.py. Run: uv run --with pyyaml python -m unittest discover -s tools"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("skills", Path(__file__).with_name("skills.py"))
skills = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skills)

GOOD = """---
name: {name}
description: Builds things. Use when the user asks to build things.
---

# Body

Read [the guide](references/guide.md).
"""


class SkillTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make(self, name="demo", skill_md=None, files=None) -> Path:
        skill = self.root / name
        skill.mkdir(parents=True, exist_ok=True)
        files = {"references/guide.md": "# Guide\n", **(files or {})}
        for rel, content in files.items():
            path = skill / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (skill / "SKILL.md").write_text(GOOD.format(name=name) if skill_md is None else skill_md)
        return skill

    def frontmatter(self, fields: str, body="# Body\n\nDo it.\n") -> str:
        return f"---\n{fields}\n---\n\n{body}"

    def assertValid(self, skill):
        r = skills.validate_skill(skill)
        self.assertEqual(r.errors, [])
        return r

    def assertError(self, skill, fragment):
        r = skills.validate_skill(skill)
        self.assertTrue(any(fragment in e for e in r.errors), f"no error containing {fragment!r} in {r.errors}")


class ValidateTests(SkillTestCase):
    def test_good_skill(self):
        r = self.assertValid(self.make())
        self.assertEqual(r.warnings, [])

    def test_missing_skill_md(self):
        skill = self.root / "demo"
        skill.mkdir()
        self.assertError(skill, "missing SKILL.md")

    def test_frontmatter_must_start_on_line_one(self):
        self.assertError(self.make(skill_md="\n" + GOOD.format(name="demo")), "line 1")

    def test_unclosed_frontmatter(self):
        self.assertError(self.make(skill_md="---\nname: demo\n"), "line 1")

    def test_invalid_yaml(self):
        self.assertError(self.make(skill_md=self.frontmatter("name: [demo")), "invalid YAML")

    def test_name_required(self):
        self.assertError(self.make(skill_md=self.frontmatter("description: Does x. Use when y.")), "'name' is required")

    def test_description_required(self):
        self.assertError(self.make(skill_md=self.frontmatter("name: demo")), "'description' is required")

    def test_name_must_match_directory(self):
        self.assertError(self.make(skill_md=GOOD.format(name="other")), "must match directory")

    def test_bad_names(self):
        for name in ("Demo", "-demo", "demo-", "de--mo", "de_mo", "a" * 65):
            with self.subTest(name=name):
                self.assertError(self.make(name=name), "name")

    def test_reserved_name(self):
        self.assertError(self.make(name="synced"), "reserved")

    def test_non_string_name(self):
        self.assertError(self.make(name="123", skill_md=self.frontmatter("name: 123\ndescription: x")), "must be a string")

    def test_description_too_long(self):
        md = self.frontmatter("name: demo\ndescription: " + "a" * 1025)
        self.assertError(self.make(skill_md=md), "max 1024")

    def test_description_angle_brackets(self):
        md = self.frontmatter("name: demo\ndescription: Use for <tag> files.")
        self.assertError(self.make(skill_md=md), "'<' or '>'")

    def test_todo_placeholders(self):
        self.assertError(self.make(skill_md=self.frontmatter("name: demo\ndescription: TODO.")), "TODO")
        self.assertError(self.make(skill_md=self.frontmatter("name: demo\ndescription: x", "TODO: steps\n")), "TODO")

    def test_empty_body(self):
        self.assertError(self.make(skill_md="---\nname: demo\ndescription: x\n---\n\n"), "no instructions")

    def test_unknown_key(self):
        self.assertError(self.make(skill_md=self.frontmatter("name: demo\ndescription: x\nversion: 1")), "unknown key 'version'")

    def test_claude_only_key_warns(self):
        r = self.assertValid(self.make(skill_md=self.frontmatter("name: demo\ndescription: x\ndisable-model-invocation: true")))
        self.assertTrue(any("only works in claude" in w for w in r.warnings))

    def test_platform_key_allowed_for_that_platform(self):
        skill = self.make(skill_md=self.frontmatter("name: demo\ndescription: x\neffort: high"))
        self.assertEqual(skills.validate_skill(skill, "claude").warnings, [])
        self.assertTrue(any("only works in claude" in w for w in skills.validate_skill(skill, "codex").warnings))

    def test_optional_spec_fields(self):
        md = self.frontmatter(
            'name: demo\ndescription: x\nlicense: MIT\ncompatibility: Requires git\n'
            'allowed-tools: Bash(git:*) Read\nmetadata:\n  author: me\n  version: "1.0"'
        )
        self.assertValid(self.make(skill_md=md))

    def test_metadata_values_must_be_strings(self):
        md = self.frontmatter("name: demo\ndescription: x\nmetadata:\n  version: 1.0")
        self.assertError(self.make(skill_md=md), "metadata")

    def test_compatibility_too_long(self):
        md = self.frontmatter("name: demo\ndescription: x\ncompatibility: " + "a" * 501)
        self.assertError(self.make(skill_md=md), "max 500")

    def test_broken_link(self):
        md = self.frontmatter("name: demo\ndescription: x", "See [missing](references/nope.md).\n")
        self.assertError(self.make(skill_md=md), "broken link")

    def test_link_outside_skill(self):
        md = self.frontmatter("name: demo\ndescription: x", "See [readme](../README.md).\n")
        self.assertError(self.make(skill_md=md), "outside the skill")

    def test_links_ignored_in_code_urls_and_anchors(self):
        body = (
            "[web](https://example.com) [top](#steps) [ok](references/guide.md#intro)\n"
            "`[x](missing.md)`\n\n```\n[y](missing.md)\n```\n"
        )
        self.assertValid(self.make(skill_md=self.frontmatter("name: demo\ndescription: x", body)))

    def test_broken_link_in_reference_file(self):
        self.assertError(self.make(files={"references/guide.md": "[x](nope.md)\n"}), "references/guide.md: broken link")

    def test_large_body_warns(self):
        r = self.assertValid(self.make(skill_md=self.frontmatter("name: demo\ndescription: x", "line\n" * 600)))
        self.assertTrue(any("lines" in w for w in r.warnings))
        r = self.assertValid(self.make(skill_md=self.frontmatter("name: demo\ndescription: x", "a" * 21000)))
        self.assertTrue(any("tokens" in w for w in r.warnings))

    def test_script_without_exec_bit_warns(self):
        skill = self.make(files={"scripts/run.sh": "#!/bin/sh\necho hi\n"})
        r = self.assertValid(skill)
        self.assertTrue(any("not executable" in w for w in r.warnings))
        os.chmod(skill / "scripts/run.sh", 0o755)
        self.assertEqual(skills.validate_skill(skill).warnings, [])


class OpenAIYamlTests(SkillTestCase):
    def with_yaml(self, text, extra=None):
        return self.make(files={"agents/openai.yaml": text, **(extra or {})})

    def test_valid(self):
        text = (
            'interface:\n  display_name: "Demo"\n  icon_small: "./assets/icon.svg"\n'
            "policy:\n  allow_implicit_invocation: false\n"
            'dependencies:\n  tools:\n    - type: "mcp"\n      value: "docs"\n      url: "https://x.test/mcp"\n'
        )
        self.assertValid(self.with_yaml(text, {"assets/icon.svg": "<svg/>"}))

    def test_unknown_section_and_key(self):
        self.assertError(self.with_yaml("extras: {}\n"), "unknown section 'extras'")
        self.assertError(self.with_yaml("interface:\n  title: x\n"), "unknown key 'interface.title'")

    def test_missing_icon(self):
        self.assertError(self.with_yaml('interface:\n  icon_large: "./assets/big.png"\n'), "file not found")

    def test_policy_must_be_bool(self):
        self.assertError(self.with_yaml('policy:\n  allow_implicit_invocation: "no"\n'), "true or false")

    def test_tool_requires_type_and_value(self):
        self.assertError(self.with_yaml("dependencies:\n  tools:\n    - type: mcp\n"), "'value' is required")

    def test_invalid_yaml(self):
        self.assertError(self.with_yaml("interface: [\n"), "invalid YAML")


class CommandTests(SkillTestCase):
    def setUp(self):
        super().setUp()
        self.skills_dir = self.root / "repo" / "skills"
        self.cat = self.skills_dir / "cat"
        self.cat.mkdir(parents=True)
        (self.cat / "README.md").write_text("# cat\n\nDemo skills.\n")
        repo = self.skills_dir.parent
        self._orig = (skills.REPO, skills.SKILLS_DIR, skills.PLATFORMS_DIR, skills.DIST_DIR)
        skills.REPO, skills.SKILLS_DIR, skills.PLATFORMS_DIR, skills.DIST_DIR = (
            repo, self.skills_dir, repo / "platforms", repo / "dist")
        self.home = self.root / "home"

    def tearDown(self):
        skills.REPO, skills.SKILLS_DIR, skills.PLATFORMS_DIR, skills.DIST_DIR = self._orig
        super().tearDown()

    def write(self, rel, content):
        path = self.skills_dir.parent / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def shared(self, name="demo", extra=""):
        self.write(f"skills/cat/{name}/SKILL.md", f"---\nname: {name}\ndescription: Shared.\n{extra}---\n\nShared body.\n")

    def run_cli(self, *argv) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return skills.main(list(argv))

    def test_new_scaffold_fails_validation_until_filled(self):
        self.assertEqual(self.run_cli("new", "demo", "-c", "cat"), 0)
        r = skills.validate_skill(self.cat / "demo")
        self.assertTrue(any("TODO" in e for e in r.errors))
        self.assertFalse(any("name" in e for e in r.errors))
        self.assertEqual(self.run_cli("new", "demo", "-c", "cat"), 1)
        self.assertEqual(self.run_cli("new", "Bad_Name", "-c", "cat"), 1)

    def test_validate_exit_codes(self):
        self.assertEqual(self.run_cli("validate"), 0)
        (self.cat / "demo").mkdir()
        (self.cat / "demo" / "SKILL.md").write_text(
            "---\nname: demo\ndescription: x\ndisable-model-invocation: true\n---\n\nDo it.\n"
        )
        self.assertEqual(self.run_cli("validate"), 0)
        self.assertEqual(self.run_cli("validate", "--strict"), 1)
        (self.cat / "demo" / "SKILL.md").write_text("no frontmatter\n")
        self.assertEqual(self.run_cli("validate"), 1)

    def test_install_and_uninstall(self):
        skill = self.cat / "demo"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n\nDo it.\n")
        self.assertEqual(self.run_cli("install", "--project", str(self.home)), 0)
        for sub in (".claude/skills/demo", ".agents/skills/demo"):
            link = self.home / sub
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), skill.resolve())
        self.assertEqual(self.run_cli("install", "--project", str(self.home)), 0)  # idempotent
        self.assertEqual(self.run_cli("uninstall", "-p", "codex", "--project", str(self.home)), 0)
        self.assertFalse((self.home / ".agents/skills/demo").exists())
        self.assertTrue((self.home / ".claude/skills/demo").is_symlink())

    def test_install_never_overwrites(self):
        skill = self.cat / "demo"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n\nDo it.\n")
        existing = self.home / ".claude/skills/demo"
        existing.mkdir(parents=True)
        (existing / "SKILL.md").write_text("mine")
        self.assertEqual(self.run_cli("install", "-p", "claude", "--project", str(self.home)), 1)
        self.assertEqual((existing / "SKILL.md").read_text(), "mine")
        self.run_cli("uninstall", "-p", "claude", "--project", str(self.home))
        self.assertTrue(existing.is_dir())

    def test_install_refuses_invalid_or_unknown(self):
        (self.cat / "demo").mkdir()
        (self.cat / "demo" / "SKILL.md").write_text("bad\n")
        self.assertEqual(self.run_cli("install", "--project", str(self.home)), 1)
        self.assertFalse((self.home / ".claude/skills/demo").exists())
        self.assertEqual(self.run_cli("install", "nope", "--project", str(self.home)), 1)

    # Platform variants

    def built_frontmatter(self, platform, name="demo"):
        built = skills.build_skill(platform, name, self.root / "out")
        raw, body = skills.split_frontmatter((built / "SKILL.md").read_text())
        return built, skills.yaml.safe_load(raw), body

    def test_frontmatter_patch_merges_and_removes(self):
        self.shared(extra="license: MIT\n")
        self.write("platforms/claude/skills/cat/demo/frontmatter.yaml", "effort: high\nlicense:\n")
        built, data, body = self.built_frontmatter("claude")
        self.assertEqual(data, {"name": "demo", "description": "Shared.", "effort": "high"})
        self.assertEqual(body, "\nShared body.\n")
        r = skills.validate_skill(built, "claude")
        self.assertEqual((r.errors, r.warnings), ([], []))

    def test_override_files_replace_and_add(self):
        self.shared()
        self.write("skills/cat/demo/references/guide.md", "shared guide\n")
        self.write("platforms/codex/skills/cat/demo/SKILL.md", "---\nname: demo\ndescription: Codex.\n---\n\nG.\n")
        self.write("platforms/codex/skills/cat/demo/references/extra.md", "extra\n")
        built, data, _ = self.built_frontmatter("codex")
        self.assertEqual(data["description"], "Codex.")
        self.assertEqual((built / "references/guide.md").read_text(), "shared guide\n")
        self.assertTrue((built / "references/extra.md").is_file())
        self.assertFalse((built / "frontmatter.yaml").exists())

    def test_override_errors(self):
        self.write("platforms/codex/skills/cat/ghost/frontmatter.yaml", "description: x\n")
        self.shared()
        self.write("platforms/claude/skills/cat/demo/frontmatter.yaml", "model: inherit\n")
        self.write("platforms/claude/skills/cat/demo/SKILL.md", "---\nname: demo\ndescription: x\n---\n\nx\n")
        self.write("platforms/windsurf/skills/demo/SKILL.md", "x")
        with tempfile.TemporaryDirectory() as tmp:
            reports = dict(skills.validate_all(Path(tmp)))
        self.assertIn("does not exist", reports["codex/ghost"].errors[0])
        self.assertIn("keep one", reports["claude/demo"].errors[0])
        self.assertIn("not a supported platform", reports["windsurf"].errors[0])
        self.assertEqual(self.run_cli("validate"), 1)

    def test_validate_checks_variants_with_platform_keys(self):
        self.shared()
        self.write("platforms/claude/skills/cat/demo/frontmatter.yaml", "effort: high\n")
        self.assertEqual(self.run_cli("validate", "--strict"), 0)
        self.write("platforms/codex/skills/cat/demo/frontmatter.yaml", "effort: high\n")
        self.assertEqual(self.run_cli("validate", "--strict"), 1)

    def test_platform_only_skill(self):
        self.shared()
        self.assertEqual(self.run_cli("new", "solo", "-c", "cat", "-p", "codex"), 0)
        self.assertTrue((skills.PLATFORMS_DIR / "codex/skills/cat/solo/SKILL.md").is_file())
        self.assertEqual(self.run_cli("new", "demo", "-c", "cat", "-p", "codex"), 1)
        self.assertEqual(skills.platform_skill_names("codex"), ["demo", "solo"])
        self.assertEqual(skills.platform_skill_names("claude"), ["demo"])

    def test_install_links_variants_to_dist(self):
        self.shared()
        self.write("platforms/codex/skills/cat/solo/SKILL.md", "---\nname: solo\ndescription: x\n---\n\nx\n")
        self.assertEqual(self.run_cli("install", "-p", "codex", "-p", "claude", "--project", str(self.home)), 0)
        codex, claude = self.home / ".agents/skills", self.home / ".claude/skills"
        self.assertEqual((codex / "demo").resolve(), (self.cat / "demo").resolve())
        self.assertEqual((codex / "solo").resolve(), (skills.DIST_DIR / "codex/solo").resolve())
        self.assertFalse((claude / "solo").exists())
        # Adding an override later re-points the existing link at the built variant.
        self.write("platforms/codex/skills/cat/demo/frontmatter.yaml", "license: MIT\n")
        self.assertEqual(self.run_cli("install", "-p", "codex", "--project", str(self.home)), 0)
        self.assertEqual((codex / "demo").resolve(), (skills.DIST_DIR / "codex/demo").resolve())

    def test_install_all_uses_each_platform_folder(self):
        self.shared()
        self.assertEqual(self.run_cli("install", "-p", "all", "--project", str(self.home)), 0)
        for cfg in skills.PLATFORMS.values():
            self.assertTrue((self.home / cfg["project"] / "demo").is_symlink(), cfg["project"])

    def test_uninstall_all_removes_only_repo_links(self):
        self.shared()
        self.run_cli("install", "-p", "claude", "--project", str(self.home))
        target = self.home / ".claude/skills"
        foreign = self.root / "elsewhere"
        foreign.mkdir()
        (target / "theirs").symlink_to(foreign, target_is_directory=True)
        self.assertEqual(self.run_cli("uninstall", "-p", "claude", "--project", str(self.home)), 0)
        self.assertFalse((target / "demo").is_symlink())
        self.assertTrue((target / "theirs").is_symlink())


    # Categories

    def test_install_and_uninstall_by_category(self):
        self.shared()
        self.write("skills/other/README.md", "# other\n\nOther skills.\n")
        self.write("skills/other/extra/SKILL.md", "---\nname: extra\ndescription: x\n---\n\nx\n")
        self.assertEqual(self.run_cli("install", "-p", "claude", "-c", "other", "--project", str(self.home)), 0)
        target = self.home / ".claude/skills"
        self.assertTrue((target / "extra").is_symlink())
        self.assertFalse((target / "demo").exists())
        self.assertEqual(self.run_cli("install", "-p", "claude", "--project", str(self.home)), 0)
        self.assertEqual(self.run_cli("uninstall", "-p", "claude", "-c", "cat", "--project", str(self.home)), 0)
        self.assertFalse((target / "demo").exists())
        self.assertTrue((target / "extra").is_symlink())
        self.assertEqual(self.run_cli("install", "-c", "nope", "--project", str(self.home)), 1)
        self.assertEqual(self.run_cli("install", "-c", "other", "demo", "--project", str(self.home)), 1)

    def test_layout_errors(self):
        self.shared()
        self.write("skills/flat/SKILL.md", "---\nname: flat\ndescription: x\n---\n\nx\n")
        self.write("skills/zbare/demo/SKILL.md", "---\nname: demo\ndescription: x\n---\n\nx\n")
        self.write("platforms/codex/skills/undefined/solo/SKILL.md", "---\nname: solo\ndescription: x\n---\n\nx\n")
        self.write("platforms/claude/skills/wrong/demo/frontmatter.yaml", "effort: high\n")
        self.write("skills/wrong/README.md", "# wrong\n\nWrong.\n")
        with tempfile.TemporaryDirectory() as tmp:
            reports = dict(skills.validate_all(Path(tmp)))
        self.assertIn("outside any category", reports["skills/flat"].errors[0])
        self.assertIn("missing README.md", reports["skills/zbare"].errors[0])
        self.assertTrue(any("must be unique" in e for r in reports.values() for e in r.errors))
        self.assertIn("not defined", reports["platforms/codex/skills/undefined"].errors[0])
        self.assertIn("move it to platforms/claude/skills/cat/demo", reports["claude/demo"].errors[0])
        self.assertEqual(self.run_cli("validate"), 1)

    def test_new_creates_category_readme_with_todo(self):
        self.assertEqual(self.run_cli("new", "fresh", "-c", "tools"), 0)
        self.assertTrue((self.skills_dir / "tools/fresh/SKILL.md").is_file())
        with tempfile.TemporaryDirectory() as tmp:
            reports = dict(skills.validate_all(Path(tmp)))
        self.assertIn("TODO", reports["skills/tools"].errors[0])
        self.assertEqual(self.run_cli("new", "fresh", "-c", "cat"), 1)  # names are unique across categories

    def test_list_groups_by_category(self):
        self.shared()
        self.write("platforms/codex/skills/cat/solo/SKILL.md", "---\nname: solo\ndescription: Solo. More.\n---\n\nx\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(skills.main(["list"]), 0)
        self.assertEqual(out.getvalue(), "cat — Demo skills.\n  demo: Shared.\n  solo [codex only]: Solo.\n\n")

if __name__ == "__main__":
    unittest.main()
