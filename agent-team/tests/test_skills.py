"""Task-level skills: lookup, attach, route suggestions and prompt assembly. Run with python3 -I."""
import argparse
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import teamcfg  # noqa: E402

_TMP = tempfile.mkdtemp()
for var, sub in (("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache"), ("CODEX_HOME", "codex")):
    os.environ[var] = os.path.join(_TMP, sub)
spec = importlib.util.spec_from_loader("team_skills", importlib.machinery.SourceFileLoader("team_skills", str(ROOT / "team.py")))
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)

ROLES = "".join(f'[roles.{k}]\nname = "{k.title()}"\ncli = "claude"\nmodel = "m1"\neffort = "low"\n'
                for k in teamcfg.CANONICAL_ROLES)
CONFIG = '''[vcs]
kind = "none"
[project]
templates_dir = "tpl"
[routing]
domains = ["code"]
[routing.pipeline]
simple = [["implement", "mid"], ["review", "architect"]]
complex = [["plan", "architect"], ["plan_review", "director"], ["implement", "mid"], ["review", "architect"]]
hard = [["plan", "director"], ["plan_review", "architect"], ["implement", "senior"], ["review", "architect"]]
'''


class Skills(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "tpl/skills").mkdir(parents=True)
        (self.d / "team.toml").write_text(CONFIG + ROLES)
        team.init(self.d / "team.toml")
        self.live = mock.patch.object(team, "live")
        self.warn = self.live.start()
        self.addCleanup(self.live.stop)

    def skill(self, name, text):
        (self.d / "tpl/skills" / f"{name}.md").write_text(text)

    def task(self, **kw):
        s = team.create_task("do it", **kw)
        return team.load(s["id"])

    def new(self, *skills, role=None):
        a = argparse.Namespace(request="do it", res="", role=role, skill=list(skills), no_run=True)
        team.cmd_new(a)

    def test_bundled_and_override(self):
        cfg = team.CFG
        self.assertIn("tdd", teamcfg.list_skills(cfg))
        self.assertIn("Test first", teamcfg.load_skill(cfg, "tdd"))
        self.skill("tdd", "# Mine\nown text")
        self.assertEqual(teamcfg.load_skill(cfg, "tdd"), "# Mine\nown text")
        self.assertEqual(teamcfg.list_skills(cfg)["tdd"], "Mine")
        self.skill("extra", "# Extra\nx")
        self.assertIn("extra", teamcfg.list_skills(cfg))

    def test_unknown_and_bad_names(self):
        with self.assertRaisesRegex(ValueError, r"unknown skill 'nope'.*tdd"):
            teamcfg.load_skill(team.CFG, "nope")
        with self.assertRaisesRegex(ValueError, "bad skill name"):
            teamcfg.load_skill(team.CFG, "../team")
        self.skill("empty", " \n")
        with self.assertRaisesRegex(ValueError, "is empty"):
            teamcfg.load_skill(team.CFG, "empty")

    def test_parse_refs(self):
        p = teamcfg.parse_skill_refs
        self.assertEqual(p("tdd, `perf-capture@review`. none"), [("tdd", ""), ("perf-capture", "review")])
        self.assertEqual(p("NONE."), [])
        self.assertEqual(p(""), [])
        for bad in ("tdd@route", "tdd@refill", "tdd@nope", "a/b"):
            with self.subTest(bad), self.assertRaises(ValueError):
                p(bad)

    def test_new_stores_and_dedupes(self):
        self.new("tdd", "tdd,tdd@review", "tdd@review")
        s = team.load("t001")
        self.assertEqual(s["skills"], [{"name": "tdd", "stage": ""}, {"name": "tdd", "stage": "review"}])

    def test_new_bad_name_leaves_no_folder(self):
        for bad in ("nope", "tdd@route"):
            with self.subTest(bad), self.assertRaises(SystemExit):
                self.new(bad)
        self.assertEqual(list(team.RUNS.glob("t[0-9]*")), [])

    def test_side_task_warns_for_missing_stage(self):
        self.new("tdd@plan", role="mid")
        self.assertTrue(any("never runs" in str(c) for c in self.warn.call_args_list))

    def test_long_skill_warns(self):
        self.skill("big", "x" * (team.CLIP + 1))
        self.new("big")
        self.assertTrue(any("over" in str(c) for c in self.warn.call_args_list))

    def test_prompt_stage_filter_dedupe_and_isolation(self):
        a = self.task(skills=[("tdd", ""), ("perf-capture", "review"), ("tdd", "review")])
        b = self.task()
        a.update(route="simple", domain="code")
        sk = team.stage_skills(a, "implement")
        self.assertEqual([n for n, _ in sk], ["tdd"])
        self.assertEqual([n for n, _ in team.stage_skills(a, "review")], ["tdd", "perf-capture"])
        text = team.build_prompt(a, "review", "architect", team.stage_skills(a, "review"))
        self.assertEqual(text.count("## Skill: tdd"), 1)
        self.assertLess(text.index("## Request"), text.index("## Skill: tdd"))
        b.update(route="simple", domain="code")
        self.assertNotIn("## Skill:", team.build_prompt(b, "implement", "mid", team.stage_skills(b, "implement")))

    def test_old_state_and_refill_have_no_skills(self):
        s = self.task()
        s.pop("skills", None)
        self.assertEqual(team.stage_skills(s, "implement"), [])
        s["skills"] = [{"name": "tdd", "stage": ""}]
        self.assertEqual(team.stage_skills(s, "refill"), [])
        self.assertEqual(team.stage_skills(s, "route"), [])
        self.assertNotIn("## Skill:", team.build_prompt(s, "refill", "producer"))

    def test_deleted_skill_fails_without_launch(self):
        s = self.task()
        s["skills"] = [{"name": "gone", "stage": ""}]  # attached earlier, the file was deleted since
        s.update(route="simple", domain="code", stage=0)
        n = s["n"]
        with mock.patch.object(team.subprocess, "Popen") as popen:
            out, text = team._run_agent_once(s, "implement", "mid", "mid", False)
        self.assertEqual((out, text, s["status"], s["n"]), (None, None, "failed", n))
        self.assertNotIn("launches", s)
        self.assertIn("restore skills/<name>.md", s["reason"])
        popen.assert_not_called()

    def route(self, reply):
        s = self.task(skills=[("tdd", "plan")])
        with mock.patch.object(team, "run_agent", return_value=("o.md", reply, "producer", "producer")), \
                mock.patch.object(team.VCS, "set_description"):
            team.route_task(s)
        return s

    def test_route_parses_skills(self):
        self.skill("custom", "# C\nc")
        s = self.route("spec\nSKILLS: `tdd`, custom@review nope perf-capture@route custom@review.\n"
                       "TITLE: t\nROUTE: simple\nDOMAIN: code\nRISK: low\nSIZE: small\n")
        self.assertEqual(s["route"], "direct")  # simple is the old name of direct
        self.assertEqual(s["skills"], [{"name": "tdd", "stage": "plan"}, {"name": "tdd", "stage": ""},
                                       {"name": "custom", "stage": "review"}])
        msgs = " ".join(str(c) for c in self.warn.call_args_list)
        self.assertIn("nope", msgs)
        self.assertIn("perf-capture@route", msgs)
        self.assertIn("tdd@plan", msgs)  # the user's plan skill has no plan stage in `simple`

    def test_route_none_and_missing_line(self):
        for line in ("SKILLS: none.\n", ""):
            s = self.route(f"spec\n{line}TITLE: t\nROUTE: simple\nDOMAIN: code\n")
            self.assertEqual(s["skills"], [{"name": "tdd", "stage": "plan"}])

    def test_body_strips_skills_line(self):
        self.assertNotIn("SKILLS", team.body("keep\nSKILLS: tdd\nmore"))

    def test_route_prompt_lists_skills(self):
        s = self.task()
        text = team.build_prompt(s, "route", "producer")
        self.assertIn("- tdd:", text)
        self.assertNotIn("{skills}", text)


if __name__ == "__main__":
    unittest.main()
