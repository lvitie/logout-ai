"""Agent files, [routing.domain.<name>] stage selection, pins and launch records. Run with python3 -I."""
import importlib.machinery
import importlib.util
import json
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
spec = importlib.util.spec_from_loader("team_agents", importlib.machinery.SourceFileLoader("team_agents", str(ROOT / "team.py")))
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)

MODELS = {"producer": "m1", "mid": "m1", "senior": "m1", "architect": "m1", "director": "m1", "artist": "x1", "codexer": "c1"}
ROLES = "".join(f'[roles.{k}]\nname = "{k.title()}"\ncli = "{"codex" if k == "codexer" else "claude"}"\nmodel = "{m}"\neffort = "low"\n'
                for k, m in MODELS.items())
BASE = '''[vcs]
kind = "none"
[project]
templates_dir = "tpl"
[routing]
domains = ["code", "art"]
extra_review_role = "director"
extra_review_routes = ["hard"]
%s
[routing.pipeline]
simple = [["implement", "mid"], ["review", "architect"]]
complex = [["plan", "architect"], ["plan_review", "director"], ["implement", "mid"], ["review", "architect"]]
hard = [["plan", "director"], ["plan_review", "architect"], ["implement", "senior"], ["review", "architect"]]
'''


def agent(name, body="Do the work.", **meta):
    fm = "".join(f"{k}: {v}\n" for k, v in {"name": name, "scope": "s", **meta}.items())
    return f"---\n{fm}---\n{body}\n"


class Agents(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "tpl/agents").mkdir(parents=True)
        (self.d / "tpl/roles").mkdir()
        (self.d / "tpl/agents/artist.md").write_text(agent("artist", "Art body."))

    def cfg(self, extra=""):
        p = self.d / "team.toml"
        p.write_text(BASE % extra + ROLES)
        return p

    def init(self, extra=""):
        team.init(self.cfg(extra))

    def bad(self, msg, extra=""):
        with self.assertRaisesRegex(ValueError, msg):
            teamcfg.load(self.cfg(extra))

    def test_bundled_defaults_are_generic_agents(self):
        cfg = teamcfg.load(self.cfg())
        for k in teamcfg.CANONICAL_ROLES:
            self.assertTrue(cfg["agent_defs"][k]["instructions"], k)
            self.assertTrue(cfg["agent_defs"][k]["scope"], k)
            self.assertNotIn("model", cfg["agent_defs"][k])

    def test_frontmatter_errors(self):
        cases = {"needs a frontmatter": "plain", "needs scope": "---\nname: bad\n---\nbody",
                 "must be": agent("other"), "no instructions": agent("bad", ""),
                 "effort must": agent("bad", effort="turbo"), "duplicate": "---\nname: bad\nname: bad\nscope: s\n---\nb",
                 "unknown frontmatter": agent("bad", color="red")}
        for msg, text in cases.items():
            with self.subTest(msg):
                (self.d / "tpl/agents/bad.md").write_text(text)
                self.bad(msg)

    def test_name_charset(self):
        for n in ("tech-art", "Art", "a.b"):
            with self.subTest(n):
                (self.d / f"tpl/agents/{n}.md").write_text(agent(n))
                self.bad("must be")
                (self.d / f"tpl/agents/{n}.md").unlink()
        (self.d / "tpl/agents/x.md").write_text(agent("../x"))
        self.bad("must be")

    def test_lookup_precedence(self):
        (self.d / "tpl/roles/producer.md").write_text("Project producer line.")
        (self.d / "tpl/roles/mid.md").write_text("Legacy mid line.")
        (self.d / "tpl/agents/senior.md").write_text(agent("senior", "New senior."))
        (self.d / "tpl/roles/senior.md").write_text("Legacy senior.")
        self.init()
        self.assertEqual(team.role_text("producer"), "Project producer line.")  # roles/ beats the bundled agent
        self.assertEqual(team.role_text("mid"), "Legacy mid line.")
        self.assertEqual(team.role_text("senior"), "New senior.")  # agents/ beats roles/
        self.assertIn("Architect", team.role_text("architect"))  # bundled agent

    def test_role_without_file_keeps_generic_line(self):
        (self.d / "tpl/agents/artist.md").unlink()
        self.init()
        self.assertEqual(team.role_text("artist"), "You are the Artist of the project agent team.")

    def test_root_like_config_uses_project_producer_prompt(self):
        (self.d / "tpl/roles/producer.md").write_text("Domains: code, art.")
        self.init('[routing.domain_roles]\ncode = "mid"')
        self.assertIn("Domains:", team.AGENTS["producer"]["instructions"])
        self.assertEqual(team.pipeline("complex", "code"), [("plan", "mid"), ("plan_review", "director"),
                                                            ("implement", "mid"), ("review", "architect")])

    def test_domain_stage_selection(self):
        self.init('[routing.domain.art]\nplan = "artist"\nreview = "director"')
        self.assertEqual(team.pipeline("complex", "art"), [("plan", "artist"), ("plan_review", "director"),
                                                           ("implement", "mid"), ("review", "director")])
        self.assertEqual(team.pipeline("complex", "code")[0], ("plan", "architect"))
        self.assertEqual(team.pipeline("hard", "art")[-1], ("review", "director"))  # extra review stays
        self.assertEqual(team.pipeline("custom:mid", "art"), [("implement", "mid"), ("review", "architect")])
        self.assertEqual(team.stage_profile("complex", "art", 0), "artist")  # its own role
        self.assertEqual(team.stage_profile("complex", "art", 3), "director")

    def test_agent_without_role_rides_the_route_profile(self):
        (self.d / "tpl/agents/qa.md").write_text(agent("qa"))
        self.init('[routing.domain.art]\nreview = "qa"')
        self.assertEqual(team.pipeline("simple", "art")[-1], ("review", "qa"))
        self.assertEqual(team.stage_profile("simple", "art", 1), "architect")
        self.assertEqual(team.stage_profile("hard", "art", 4), "director")  # extra review role

    def test_domain_roles_folds_with_deprecation(self):
        self.init('[routing.domain_roles]\nart = "artist"\n[routing.domain.art]\nimplement = "senior"')
        self.assertTrue(team.CFG["deprecated_domain_roles"])
        got = dict(team.pipeline("complex", "art"))
        self.assertEqual((got["plan"], got["implement"]), ("artist", "senior"))

    def test_rejections(self):
        for msg, extra in (("unknown agent", '[routing.domain.art]\nplan = "nobody"'),
                           ("unknown stage", '[routing.domain.art]\nbogus = "mid"'),
                           ("unknown stage", '[routing.domain.art]\nskills = ["x"]'),
                           ("not listed", '[routing.domain.ui]\nplan = "mid"'),
                           ("unknown agent", '[routing.domain.art]\nplan = 3'),
                           ("must differ", '[routing.domain.art]\nplan = "mid"\nplan_review = "mid"'),
                           ("must differ", '[routing.domain.art]\nimplement = "architect"'),
                           ("must differ", '[routing.domain_roles]\nart = "architect"'),  # folded, then checked
                           ("unknown agent 'nobody'", '[routing.domain_roles]\nart = "nobody"')):
            with self.subTest(extra=extra):
                self.bad(msg, extra)

    def test_stage_absent_from_every_route(self):
        p = self.cfg('[routing.domain.art]\nplan_review = "mid"')
        p.write_text(p.read_text().replace('["plan_review", "director"], ', "").replace('["plan_review", "architect"], ', ""))
        with self.assertRaisesRegex(ValueError, "in no route"):
            teamcfg.load(p)

    def test_pin_validation(self):
        (self.d / "tpl/agents/artist.md").write_text(agent("artist", model="c1"))
        self.bad("does not fit")  # artist's own role is claude, c1 is a codex model
        (self.d / "tpl/agents/artist.md").write_text(agent("artist", model="nope"))
        self.bad("not the model of any")
        (self.d / "tpl/agents/artist.md").write_text(agent("artist", model="x1", effort="high"))
        self.assertEqual(teamcfg.load(self.cfg())["agent_defs"]["artist"]["effort"], "high")
        (self.d / "tpl/agents/qa.md").write_text(agent("qa", model="c1"))  # no role: starts on the route's claude profile
        self.bad("does not fit", '[routing.domain.art]\nreview = "qa"')

    def test_pin_blocks_cli_changing_swaps(self):
        (self.d / "tpl/agents/artist.md").write_text(agent("artist", model="x1"))
        self.init('[routing.usage]\nenabled = true\nclaude_fallback = {artist = "codexer"}\n')
        self.assertFalse(team.pin_fits("artist", "codexer"))
        self.assertTrue(team.pin_fits("artist", "mid"))
        self.assertTrue(team.pin_fits("mid", "codexer"))

    def test_launch_is_recorded_before_start_with_pin(self):
        (self.d / "tpl/agents/artist.md").write_text(agent("artist", model="x1", effort="high"))
        self.init()
        s = {"id": "t001", "request": "r", "change": "c", "route": "simple", "domain": "art", "stage": 0, "n": 0,
             "status": "running", "reason": "", "plan_rounds": 0, "review_rounds": 0, "notes": [], "plan_reviews": [],
             "reviews": [], "history": []}
        team.task_dir("t001").mkdir(parents=True)
        with mock.patch.object(team.subprocess, "Popen", side_effect=RuntimeError("stop")), \
                mock.patch.object(team, "ensure_guards"), self.assertRaises(RuntimeError):
            team._run_agent_once(s, "implement", "artist", "mid", True)
        got = json.loads((team.task_dir("t001") / "state.json").read_text())["launches"]
        self.assertEqual(got, [{"stem": "01-implement-artist", "agent": "artist", "profile": "mid", "cli": "claude",
                                "model": "x1", "effort": "high"}])

    def test_history_readers_fall_back_to_stems(self):
        self.init()
        s = {"history": ["01-route-producer", "02-implement-mid", "03-review-architect"],
             "launches": [{"stem": "03-review-architect", "agent": "qa", "profile": "architect"}]}
        self.assertEqual(team.hist_entries(s), [("route", "producer", "producer"), ("implement", "mid", "mid"),
                                                ("review", "qa", "architect")])

    def test_escalation_gate_compares_the_profile(self):
        self.init('[routing.usage]\nescalation_gate = {role = "director", first = "architect", second_review = "senior"}')
        s = {"id": "t001", "route": "hard", "domain": "code", "stage": 4, "review_rounds": 0, "plan_rounds": 0,
             "history": ["01-route-producer", "05-review-director"],
             "launches": [{"stem": "05-review-director", "agent": "director", "profile": "architect"}]}
        with mock.patch.object(team, "claude_low", return_value=False), mock.patch.object(team, "burst_active", return_value=False):
            self.assertEqual(team._select_agent_role(s, "review", "director", "director")[:2], ("director", "senior"))
            s["launches"][0]["profile"] = "director"  # the first review did not run on the gate's first role
            self.assertEqual(team._select_agent_role(s, "review", "director", "director")[:2], ("director", "architect"))

    def test_takeover_reassigns_agent_and_profile(self):
        self.init('[routing.takeover.mid]\nto = "senior"\nafter_reviews = 1')
        s = {"id": "t001", "route": "simple", "domain": "code", "stage": 0, "review_rounds": 1, "history": []}
        with mock.patch.object(team, "run_agent", return_value=(None, None, "senior", "senior")) as run:
            team.step(s, team.pipeline("simple", "code"))
        self.assertEqual(run.call_args.args[2:], ("senior", "senior"))

    def test_selection_has_no_after_impl_fails_swap(self):
        self.init('[routing.after_impl_fails]\nfails = 1\n[routing.usage]\nenabled = true\n'
                  'capacity_fallback = {}\nclaude_fallback = {}')
        s = {"id": "t001", "route": "simple", "domain": "code", "stage": 0, "review_rounds": 0, "plan_rounds": 0,
             "history": [], "impl_fails": 1}
        with mock.patch.object(team, "claude_low", return_value=False), mock.patch.object(team, "burst_active", return_value=False):
            self.assertEqual(team._select_agent_role(s, "implement", "artist", "mid")[:2], ("artist", "mid"))


if __name__ == "__main__":
    unittest.main()
