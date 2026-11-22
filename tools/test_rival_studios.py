"""Tests for harnesses/rival-studios/rival.py, with a fake agent in place of Claude Code or Codex.

Run: python3 -m unittest tools/test_rival_studios.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harnesses" / "rival-studios"
spec = importlib.util.spec_from_file_location("rival", HARNESS / "rival.py")
rival = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rival)

# Stands in for an agent: builds a page as a studio, answers a verdict as the judge, and notes the merge.
FAKE_AGENT = textwrap.dedent("""\
    import json, os, re, sys
    from pathlib import Path
    prompt, cwd, last = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if os.environ.get("FAKE_PROMPTS"):
        log = Path(os.environ["FAKE_PROMPTS"])
        log.mkdir(exist_ok=True)
        (log / f"{len(list(log.iterdir()))}.txt").write_text(prompt)
    role = prompt.split("\\n", 1)[0]
    if role == "Role: studio":
        if os.environ.get("FAKE_FAIL") and os.environ["FAKE_FAIL"] in prompt:
            sys.exit(3)
        (cwd / "index.html").write_text("<h1>" + prompt.split("\\n")[4][:40] + "</h1>\\n")
        (cwd / "RIVAL.md").write_text("Open index.html.\\n")
    elif role == "Role: judge":
        ids = re.search(r"Use these entry ids exactly: (.+)", prompt).group(1).split(", ")
        bad = os.environ.get("FAKE_BAD_JUDGE") and "could not be used" not in prompt
        scores = {i: dict.fromkeys(["works", "hook", "feel", "originality", "polish"], 9 if i == ids[0] else 5)
                  for i in ids}
        verdict = {"winner": "nope" if bad else ids[0], "scores": scores,
                   "steal": [{"from": i, "idea": "the coin sparkle"} for i in ids[1:]], "reason": "It plays best."}
        last.write_text("Played both.\\n```json\\n" + json.dumps(verdict) + "\\n```\\n")
    elif role == "Role: merge":
        with (cwd / "RIVAL.md").open("a") as f:
            f.write("Took: the coin sparkle\\n")
    print("fake agent finished", role)
""")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class RivalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "game"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "README.md").write_text("A game.\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("Build a one-screen coin game with {{curly}} braces kept.\n")
        fake = self.tmp / "fake_agent.py"
        fake.write_text(FAKE_AGENT)
        self.agent = ["--agent-cmd", json.dumps([sys.executable, str(fake), "{prompt}", "{cwd}", "{last}"]),
                      "--repo", str(self.repo)]
        self.env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rival.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def start(self, *extra):
        code, out, err = self.cli("start", str(self.brief), "--repo", str(self.repo), "--seed", "1", *extra)
        self.assertEqual(code, 0, err)
        folder = sorted((self.repo / ".rival").iterdir())[-1]
        return folder, json.loads((folder / "run.json").read_text())


class StartTests(RivalCase):
    def test_creates_one_worktree_and_branch_per_studio(self):
        folder, run = self.start("--studios", "3")
        self.assertEqual(len(run["entries"]), 3)
        self.assertEqual(len({e["stance"] for e in run["entries"]}), 3)
        for e in run["entries"]:
            self.assertRegex(e["id"], r"^entry-[0-9a-f]{4}$")
            self.assertTrue((Path(e["path"]) / "README.md").is_file())
            self.assertEqual(git(self.repo, "rev-parse", e["branch"]), run["base"])
        self.assertIn("/.rival/", (self.repo / ".git" / "info" / "exclude").read_text())
        self.assertEqual(git(self.repo, "status", "--porcelain"), "", "runs stay out of git status")
        self.start()  # a second run in the same second gets its own folder, and no second exclude line
        self.assertEqual(len(list((self.repo / ".rival").iterdir())), 2)
        self.assertEqual((self.repo / ".git" / "info" / "exclude").read_text().count("/.rival/"), 1)

    def test_refuses_bad_input(self):
        self.assertEqual(self.cli("start", str(self.tmp / "none.md"), "--repo", str(self.repo))[0], 1)
        self.assertIn("not a git repository", self.cli("start", str(self.brief), "--repo", str(self.tmp))[2])
        self.assertIn("--studios", self.cli("start", str(self.brief), "--repo", str(self.repo), "--studios", "1")[2])
        empty = self.tmp / "empty"
        empty.mkdir()
        git(empty, "init", "-q")
        self.assertIn("no commits", self.cli("start", str(self.brief), "--repo", str(empty))[2])
        self.assertEqual(self.cli("build", "nope", *self.agent)[0], 1)
        self.assertEqual(self.cli("build", "x", "--agent-cmd", '"not a list"')[0], 2)


class FullRunTests(RivalCase):
    def test_build_judge_merge(self):
        os.environ["FAKE_PROMPTS"] = str(self.tmp / "prompts")
        code, out, err = self.cli("run", str(self.brief), "--seed", "2", *self.agent)
        self.assertEqual(code, 0, err)
        folder = sorted((self.repo / ".rival").iterdir())[-1]
        run = json.loads((folder / "run.json").read_text())
        verdict = json.loads((folder / "verdict.json").read_text())
        ids = [e["id"] for e in run["entries"]]
        self.assertEqual(rival.validate_verdict(verdict, ids), [])
        self.assertTrue(all(e["build"]["ok"] and e["build"]["commits"] == 1 for e in run["entries"]))
        winner = next(e for e in run["entries"] if e["id"] == verdict["winner"])
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s", winner["branch"]),
                         "rival: take ideas from rival studios")
        self.assertIn("Took: the coin sparkle", git(self.repo, "show", f"{winner['branch']}:RIVAL.md"))
        self.assertIn(f"git merge {winner['branch']}", out)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), run["base"], "your branch is untouched")

        prompts = {p.read_text().split("\n", 1)[0]: p.read_text() for p in (self.tmp / "prompts").iterdir()}
        self.assertIn("{{curly}} braces kept", prompts["Role: studio"])
        judge = prompts["Role: judge"]
        for e in run["entries"]:  # blind: no stance, branch, or direction text reaches the judge
            stance = next(s for s in rival.STANCES if s["name"] == e["stance"])
            for secret in (e["stance"], e["branch"], stance["direction"]):
                self.assertNotIn(secret, judge)

        code, out, _ = self.cli("status", run["id"], "--repo", str(self.repo))
        self.assertIn("<- winner", out)
        self.assertIn("merged", out)
        code, out, _ = self.cli("clean", str(folder))
        self.assertEqual(code, 0)
        self.assertFalse((folder / "entries").exists())
        self.assertEqual(len(git(self.repo, "branch", "--list", f"rival/{run['id']}/*").splitlines()), 2)

    def test_failed_studio_is_left_out_and_lone_survivor_wins(self):
        folder, run = self.start()
        failing = next(s for s in rival.STANCES if s["name"] == run["entries"][0]["stance"])
        os.environ["FAKE_FAIL"] = failing["direction"]
        self.assertEqual(self.cli("build", run["id"], *self.agent)[0], 0)
        run = json.loads((folder / "run.json").read_text())
        self.assertEqual([e["build"]["error"] for e in run["entries"]], ["exit code 3, no changes", ""])
        code, out, err = self.cli("judge", run["id"], *self.agent)
        self.assertEqual(code, 0, err)
        self.assertIn(run["entries"][1]["id"], out)
        self.assertEqual(self.cli("merge", run["id"], *self.agent)[0], 0)

    def test_every_studio_failing_is_an_error(self):
        folder, run = self.start()
        os.environ["FAKE_FAIL"] = "Role: studio"
        code, _, err = self.cli("build", run["id"], *self.agent)
        self.assertEqual(code, 1)
        self.assertIn("every studio failed", err)
        self.assertIn("run build first", self.cli("judge", run["id"], *self.agent)[2])

    def test_judge_gets_a_second_chance(self):
        folder, run = self.start()
        self.cli("build", run["id"], *self.agent)
        os.environ["FAKE_BAD_JUDGE"] = "1"
        os.environ["FAKE_PROMPTS"] = str(self.tmp / "prompts")
        code, _, err = self.cli("judge", run["id"], *self.agent)
        self.assertEqual(code, 0, err)
        self.assertIn('"winner": "nope"', (folder / "logs" / "judge-1.last.txt").read_text())
        retry = sorted((self.tmp / "prompts").iterdir())[-1].read_text()
        self.assertIn("winner 'nope' is not one of", retry)
        verdict = json.loads((folder / "verdict.json").read_text())
        self.assertEqual(rival.validate_verdict(verdict, [e["id"] for e in run["entries"]]), [])
        self.assertIn("run judge first", self.cli("merge", self.start()[1]["id"], *self.agent)[2])

    def test_merge_refuses_a_verdict_from_another_run(self):
        folder, run = self.start()
        (folder / "verdict.json").write_text(json.dumps({"winner": "entry-0000", "steal": []}))
        self.assertIn("aren't in this run", self.cli("merge", run["id"], *self.agent)[2])

    def test_timeout_kills_the_agent(self):
        folder, run = self.start()
        slow = ["--agent-cmd", json.dumps([sys.executable, "-c", "import time; time.sleep(30)"]),
                "--repo", str(self.repo), "--timeout", "1"]
        code, _, err = self.cli("build", run["id"], *slow)
        self.assertEqual(code, 1)
        run = json.loads((folder / "run.json").read_text())
        self.assertTrue(all(e["build"]["error"] == "timed out, no changes" for e in run["entries"]))


class VerdictTests(unittest.TestCase):
    IDS = ["entry-aaaa", "entry-bbbb"]

    def verdict(self, **change):
        good = {"winner": "entry-aaaa",
                "scores": {"entry-aaaa": dict.fromkeys(rival.CRITERIA, 8), "entry-bbbb": dict.fromkeys(rival.CRITERIA, 6)},
                "steal": [{"from": "entry-bbbb", "idea": "the dash trail"}], "reason": "Tighter controls."}
        good.update(change)
        return good

    def test_good_verdict(self):
        self.assertEqual(rival.validate_verdict(self.verdict(), self.IDS), [])
        self.assertEqual(rival.validate_verdict(self.verdict(steal=[]), self.IDS), [])

    def test_problems(self):
        low = {"entry-aaaa": dict.fromkeys(rival.CRITERIA, 2), "entry-bbbb": dict.fromkeys(rival.CRITERIA, 6)}
        cases = {
            "is not one of": self.verdict(winner="entry-cccc"),
            "below the top total": self.verdict(scores=low),
            "exactly these entries": self.verdict(scores={"entry-aaaa": dict.fromkeys(rival.CRITERIA, 8)}),
            "must score exactly": self.verdict(scores={**low, "entry-aaaa": {"works": 9}}),
            "numbers from 0 to 10": self.verdict(scores={**low, "entry-aaaa": dict.fromkeys(rival.CRITERIA, 11)}),
            "other than the winner": self.verdict(steal=[{"from": "entry-aaaa", "idea": "x"}]),
            "needs an 'idea'": self.verdict(steal=[{"from": "entry-bbbb", "idea": " "}]),
            "reason": self.verdict(reason=""),
        }
        for expected, verdict in cases.items():
            with self.subTest(expected):
                self.assertTrue(any(expected in p for p in rival.validate_verdict(verdict, self.IDS)),
                                rival.validate_verdict(verdict, self.IDS))
        self.assertEqual(rival.validate_verdict([], self.IDS), ["the verdict is not a JSON object"])
        bools = {**low, "entry-aaaa": dict.fromkeys(rival.CRITERIA, True)}
        self.assertTrue(rival.validate_verdict(self.verdict(scores=bools), self.IDS))

    def test_extract_json_takes_the_last_verdict(self):
        text = 'Notes {not json} {"x": 1}\n```json\n{"winner": "a"}\n```\nThen {"winner": "b", "scores": {}}'
        self.assertEqual(rival.extract_json(text), {"winner": "b", "scores": {}})
        self.assertIsNone(rival.extract_json("no verdict here"))


class AgentCommandTests(unittest.TestCase):
    def test_builtin_agents(self):
        cwd, last = Path("/w/entry-1"), Path("/w/last.txt")
        self.assertEqual(rival.agent_argv("claude", "edits", "P", cwd, last, [Path("/w/entry-2")]),
                         ["claude", "-p", "--permission-mode", "acceptEdits", "--output-format", "text",
                          "--add-dir", "/w/entry-2", "P"])
        self.assertIn("bypassPermissions", rival.agent_argv("claude", "full", "P", cwd, last, []))
        self.assertEqual(rival.agent_argv("codex", "edits", "P", cwd, last, []),
                         ["codex", "exec", "-C", "/w/entry-1", "-s", "workspace-write", "--skip-git-repo-check",
                          "-o", "/w/last.txt", "P"])
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", rival.agent_argv("codex", "full", "P", cwd, last, []))
        self.assertEqual(rival.agent_argv("codex", "edits", "P", cwd, last, [], model="m1")[4:8],
                         ["-s", "workspace-write", "-m", "m1"])
        self.assertEqual(rival.agent_argv("claude", "edits", "P", cwd, last, [], model="opus")[6:8], ["--model", "opus"])
        self.assertEqual(rival.agent_argv("x", "edits", "P", cwd, last, [], ["a", "{cwd}", "{prompt}", "{last}"]),
                         ["a", "/w/entry-1", "P", "/w/last.txt"])
        with self.assertRaises(rival.RivalError):
            rival.agent_argv("gemini", "edits", "P", cwd, last, [])

    def test_prompts_fill_every_placeholder(self):
        for name, values in {"studio.md": ["brief", "stance"], "judge.md": ["brief", "entries", "ids", "criteria"],
                             "merge.md": ["brief", "ideas"]}.items():
            text = rival.render(name, **dict.fromkeys(values, "X"))
            self.assertNotIn("{{", text, name)
            self.assertTrue(text.startswith("Role: " + name[:-3]), name)
        with self.assertRaises(rival.RivalError):
            rival.render("judge.md", brief="X")

    def test_stances_are_distinct(self):
        names = [s["name"] for s in rival.STANCES]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(s["direction"].strip() for s in rival.STANCES))


if __name__ == "__main__":
    unittest.main()
