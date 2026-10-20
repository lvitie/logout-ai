"""Phase 5 game-dev defaults: bundled agents and skills, the shipped team.toml, setup presets, validation of the new
references. Run with python3 -I."""
import importlib.machinery
import importlib.util
import itertools
import os
import re
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import teamcfg  # noqa: E402
from cfgutil import config_text  # noqa: E402

_TMP = tempfile.mkdtemp()
for var, sub in (("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache"), ("CODEX_HOME", "codex")):
    os.environ[var] = os.path.join(_TMP, sub)
spec = importlib.util.spec_from_loader("team_gamedev", importlib.machinery.SourceFileLoader("team_gamedev", str(ROOT / "team.py")))
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)

DISCIPLINES = ("designer", "gameplay", "engine", "tools", "technical_artist", "audio", "qa", "build_release")
DOMAINS = ("gameplay", "engine", "tools", "technical_art", "audio", "design", "build")
SKILLS = ("shaders", "animation", "level-design", "balancing", "netcode", "optimization")
STAGES = ("plan", "plan_review", "implement", "review")


def load(text, **kw):
    """Config text written to a scratch dir and loaded with warnings as errors."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "team.toml"
        p.write_text(text)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            return teamcfg.load(p)


def state(**kw):
    s = {"id": "t001", "request": "r", "change": "c", "route": "simple", "domain": "gameplay", "stage": 0, "n": 0,
         "status": "running", "reason": "", "plan_rounds": 0, "review_rounds": 0, "notes": [], "plan_reviews": [],
         "reviews": [], "history": [], "risk": "low", "size": "small"}
    return {**s, **kw}


class Shipped(unittest.TestCase):
    def test_raw_template_loads(self):
        cfg = teamcfg.load(ROOT / "templates/team.toml")
        self.assertEqual(cfg["vcs"]["kind"], "p4")
        self.assertEqual(cfg["vcs"]["guard_names"], ["p4", "git"])
        self.assertEqual(cfg["vcs"]["deny"]["git"], ["*"])
        self.assertIn("submit", cfg["vcs"]["deny"]["p4"])
        self.assertEqual(tuple(cfg["routing"]["domains"]), DOMAINS)

    def test_agents_are_identity_only(self):
        agents = teamcfg.load(ROOT / "templates/team.toml")["agent_defs"]
        for name in DISCIPLINES + ("producer", "director"):
            a = agents[name]
            self.assertTrue(a["scope"] and a["instructions"], name)
            self.assertFalse({"model", "effort", "pin"} & a.keys(), f"{name} must not choose a model")
            self.assertTrue((ROOT / f"templates/agents/{name}.md").is_file(), name)

    def test_domain_tables_are_full_and_independent(self):
        cfg = teamcfg.load(ROOT / "templates/team.toml")
        R = cfg["routing"]
        self.assertEqual(set(R["domain"]), set(DOMAINS))
        for dom, tbl in R["domain"].items():
            self.assertEqual(set(tbl), set(STAGES), dom)
            self.assertNotEqual(tbl["plan"], tbl["plan_review"], dom)
            self.assertNotEqual(tbl["implement"], tbl["review"], dom)
            self.assertNotEqual(tbl["review"], R["extra_review_role"], dom)  # hard routes add that reviewer
            self.assertTrue(all(a in cfg["agent_defs"] for a in tbl.values()), dom)
        for role, dom in R["side_task_domains"].items():
            self.assertIn(dom, R["domains"], role)
        self.assertTrue(set(R["review_extra_domains"]) <= set(DOMAINS))

    def test_locks_and_ladder(self):
        cfg = teamcfg.load(ROOT / "templates/team.toml")
        self.assertEqual((cfg["locks"]["names"], cfg["locks"]["default"]), (["editor", "gpu", "build"], ["editor"]))
        self.assertEqual(cfg["locks"]["gpu"]["skip_if_holds"], "editor")
        h = cfg["heuristic"]
        self.assertEqual([t["name"] for t in h["tiers"]], ["low", "mid", "high", "top", "apex"])
        self.assertEqual([r["name"] for r in h["rules"]], ["hard-route", "high-risk", "repeat-failures"])

    def test_rules_resolve_to_a_tier(self):
        base = dict(route="simple", domain="gameplay", risk="low", size="small", stage="implement", failures=0, usage=None)
        for agents, vcs in itertools.product(("claude", "codex", "both"), ("git", "p4", "none")):
            h = load(config_text(agents, vcs))["heuristic"]
            for rule in h["rules"]:
                w = rule["when"]
                inp = {**base, **{k: (v[-1] if isinstance(v, list) else v) for k, v in w.items() if k != "failures_min"}}
                if "failures_min" in w:
                    inp["failures"] = w["failures_min"]
                got = teamcfg.resolve(h, inp)
                self.assertIn(rule["name"], got["rules"], (agents, vcs))
                self.assertEqual(got["tier"], rule["min"]["tier"], (agents, vcs, rule["name"]))
            self.assertEqual(teamcfg.resolve(h, base)["tier"], "low")

    def test_preset_vcs_matrix_loads(self):
        for agents, vcs in itertools.product(("claude", "codex", "both"), ("git", "p4", "none")):
            cfg = load(config_text(agents, vcs))
            self.assertEqual(cfg["vcs"]["kind"], vcs)
            self.assertEqual(tuple(cfg["routing"]["domains"]), DOMAINS, (agents, vcs))
            self.assertEqual(cfg["locks"]["default"], ["editor"])
            clis = {r["cli"] for r in cfg["roles"].values()}
            self.assertEqual(clis, {"claude", "codex"} if agents == "both" else {agents})
        self.assertEqual(load(config_text("claude", "git"))["vcs"]["deny"]["git"][0], "commit")
        self.assertIn("-D", load(config_text("claude", "git"))["vcs"]["deny_flags"]["git"]["branch"])
        vcs_block = lambda t: t[t.index("[vcs]"):t.index("[agents]")]  # noqa: E731
        self.assertEqual(vcs_block(config_text("claude", "p4")), vcs_block((ROOT / "templates/team.toml").read_text()))


class Validation(unittest.TestCase):
    def check(self, old, new, msg):
        text = config_text("claude", "none")
        self.assertIn(old, text)
        with self.assertRaisesRegex(ValueError, msg):
            load(text.replace(old, new, 1))

    def test_side_task_role_must_be_an_agent(self):
        self.check('"qa", "build_release"]', '"qa", "nobody"]', "side_task_roles references unknown agent 'nobody'")

    def test_side_task_domain_keys_and_values(self):
        self.check('audio = "audio"\n', 'nobody = "audio"\n', "side_task_domains references unknown agent 'nobody'")
        self.check('audio = "audio"\n', 'audio = "ghost"\n', "side_task_domains 'ghost' is not listed in routing.domains")

    def test_review_extra_domains_must_be_listed(self):
        self.check('review_extra_domains = ["technical_art", "audio"]', 'review_extra_domains = ["ghost"]',
                   "review_extra_domains 'ghost' is not listed in routing.domains")

    def test_lock_default_must_be_a_name(self):
        self.check('default = ["editor"]', 'default = ["edtior"]', "default 'edtior' is not listed in names")

    def test_removed_domain_leaves_nothing_behind(self):
        text = config_text("claude", "none")
        no_audio = text.replace('"audio", "design"', '"design"').replace('["technical_art", "audio"]', '["technical_art"]')
        no_audio = re.sub(r"\[routing\.domain\.audio\]\n(?:[a-z_]+ = .*\n)+", "", no_audio)
        with self.assertRaisesRegex(ValueError, "side_task_domains 'audio' is not listed in routing.domains"):
            load(no_audio)  # the side-task reference is the last one left
        no_audio = no_audio.replace('audio = "audio"\n', "")
        cfg = load(no_audio)
        self.assertNotIn("audio", cfg["routing"]["domains"])
        # a rule on the removed domain is the last reference
        rule = '[[heuristic.rule]]\nname = "audio-rule"\nwhen = { domain = "audio" }\nmin = { tier = "high" }\n'
        with self.assertRaisesRegex(ValueError, "when.domain 'audio' is not listed in routing.domains"):
            load(no_audio + "\n" + rule)

    def test_route_prompt_lists_only_configured_domains(self):
        text = config_text("claude", "none")
        no_audio = re.sub(r"\[routing\.domain\.audio\]\n(?:[a-z_]+ = .*\n)+", "",
                          text.replace('"audio", "design"', '"design"').replace('["technical_art", "audio"]', '["technical_art"]')
                          .replace('audio = "audio"\n', ""))
        for body, expect in ((text, True), (no_audio, False)):
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "team.toml").write_text(body)
                team.init(Path(d) / "team.toml")
                team.task_dir("t001").mkdir(parents=True, exist_ok=True)
                prompt = team.build_prompt(state(domain=None, route=None), "route", "producer")
                self.assertIn("DOMAIN: gameplay|engine|tools|technical_art|" + ("audio|" if expect else "") + "design|build", prompt)
                self.assertEqual("- audio:" in prompt, expect)
                self.assertIn("- gameplay: gameplay programming", prompt)
                self.assertIn("- technical_art: technical art", prompt)
                self.assertNotIn("{domain_guide}", prompt)


class Runtime(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "team.toml"
        p.write_text(config_text("claude", "none"))
        team.init(p)
        team.RUNS.mkdir(parents=True, exist_ok=True)

    def test_side_task_gameplay_implements_on_mid(self):
        pl = team.pipeline("custom:gameplay", "gameplay")
        self.assertEqual(pl, [("implement", "gameplay"), ("review", "architect")])
        self.assertEqual(team.stage_profile("custom:gameplay", "gameplay", 0), "mid")
        self.assertIn("gameplay", team.CFG["routing"]["side_task_roles"])
        # unrated (high/large) and rated side tasks both start on the mid profile: no shipped rule matches custom routes
        for kw in ({"risk": "high", "size": "large"}, {"risk": "low", "size": "small"}):
            s = state(route="custom:gameplay", **kw)
            with mock.patch.object(team, "claude_low", return_value=False), \
                    mock.patch.object(team, "usage_input", return_value=(None, "test")), \
                    mock.patch.object(team, "burst_active", return_value=False):
                agent, role, burst, ctx = team._select_tiered(s, "implement", "gameplay", "mid", team.CFG["heuristic"])
            self.assertEqual((agent, role, ctx["record"]["tier"]), ("gameplay", "mid", "low"), kw)

    def test_domain_implement_agents_run_on_the_route_profile(self):
        self.assertEqual(team.pipeline("simple", "technical_art"),  # review_extra_domains adds the director review
                         [("implement", "technical_artist"), ("review", "qa"), ("review", "director")])
        self.assertEqual(team.pipeline("simple", "gameplay"), [("implement", "gameplay"), ("review", "qa")])
        self.assertEqual(team.stage_profile("simple", "technical_art", 0), "mid")
        hard = team.pipeline("hard", "technical_art")
        self.assertEqual(hard[0], ("plan", "technical_artist"))
        self.assertEqual(hard[-1], ("review", "director"))
        self.assertEqual(team.stage_profile("hard", "technical_art", 2), "senior")

    def test_launch_prompt_carries_the_discipline(self):
        team.task_dir("t001").mkdir(parents=True, exist_ok=True)
        s = state(route="complex", domain="audio")
        for i, (kind, agent) in enumerate(team.pipeline("complex", "audio")):
            self.assertIn("agent team", team.build_prompt(s, kind, agent))
        self.assertIn("Audio specialist", team.build_prompt(s, "implement", "audio"))
        self.assertIn("QA Engineer", team.build_prompt(s, "review", "qa"))


class Skills(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "team.toml"
        p.write_text(config_text("claude", "none"))
        self.cfg = teamcfg.load(p)

    def test_bundled_skills_load(self):
        listed = teamcfg.list_skills(self.cfg)
        for name in SKILLS:
            self.assertIn(name, listed)
            self.assertGreater(len(teamcfg.load_skill(self.cfg, name)), 100, name)
        self.assertIn("perf-capture", listed)

    def test_optimization_differs_from_perf_capture(self):
        opt, cap = (teamcfg.load_skill(self.cfg, n) for n in ("optimization", "perf-capture"))
        self.assertNotEqual(opt, cap)
        self.assertIn("perf-capture", opt)
        self.assertIn("baseline", opt.lower())
        self.assertIn("before and after", opt)
        self.assertIn("no measurable gain", opt)
        self.assertIn("Do not optimize", cap)
        self.assertNotIn("Do not optimize", opt)

    def test_skill_refs_attach_by_stage(self):
        refs = teamcfg.parse_skill_refs("shaders@implement, optimization, netcode@review")
        self.assertEqual(refs, [("shaders", "implement"), ("optimization", ""), ("netcode", "review")])


if __name__ == "__main__":
    unittest.main()
