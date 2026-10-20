"""The model/effort ladder written per preset (docs/MODEL_LADDER.md): five tiers, allowed ids, apex is escalation only."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import teamcfg  # noqa: E402
from cfgutil import ROOT, config_text  # noqa: E402

TIERS = ["low", "mid", "high", "top", "apex"]
ALLOWED = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1", "gpt-6.1-sol", "gpt-6-astra"}


def load(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "team.toml"
        p.write_text(text)
        return teamcfg.load(p)


class Ladder(unittest.TestCase):
    def test_five_tiers_per_preset_with_allowed_ids(self):
        for agents in ("claude", "codex", "both"):
            cfg = load(config_text(agents, "none"))
            h = cfg["heuristic"]
            self.assertEqual([t["name"] for t in h["tiers"]], TIERS, agents)
            for t in h["tiers"]:
                profs = [t[c] for c in ("claude", "codex") if t[c]]
                self.assertTrue(profs, (agents, t["name"]))
                for p in profs:
                    self.assertIn(p["model"], ALLOWED)
                    self.assertNotEqual(p["effort"], "max")
            for r in cfg["roles"].values():
                self.assertIn(r["model"], ALLOWED)
                self.assertNotEqual(r["effort"], "max")

    def test_expected_profiles(self):
        want = {"claude": ("claude-sonnet-5-5", "medium"), "codex": ("gpt-6.1-sol", "medium")}
        for agents in ("claude", "codex", "both"):
            h = load(config_text(agents, "none"))["heuristic"]
            for cli, (model, eff) in want.items():
                if h["tiers"][0][cli]:
                    self.assertEqual((h["tiers"][0][cli]["model"], h["tiers"][0][cli]["effort"]), (model, eff))
            if agents != "codex":
                self.assertEqual(h["tiers"][4]["claude"]["model"], "claude-fable-5-1")
                self.assertEqual(h["tiers"][4]["claude"]["effort"], "high")
            if agents != "claude":
                self.assertEqual((h["tiers"][4]["codex"]["model"], h["tiers"][4]["codex"]["effort"]), ("gpt-6-astra", "xhigh"))
                self.assertEqual((h["tiers"][3]["codex"]["model"], h["tiers"][3]["codex"]["effort"]), ("gpt-6-astra", "high"))

    def test_codex_preset_has_no_claude_role_and_architect_ranks_top(self):
        cfg = load(config_text("codex", "none"))
        self.assertEqual({r["cli"] for r in cfg["roles"].values()}, {"codex"})
        a = cfg["roles"]["architect"]
        self.assertEqual(teamcfg.own_rank(cfg["heuristic"], "architect", a["model"], a["effort"]), 3)

    def test_default_ladder_equals_the_template(self):
        raw = __import__("tomllib").loads((ROOT / "templates/team.toml").read_text())
        self.assertEqual(raw["heuristic"]["tiers"], teamcfg.DEFAULT_LADDER)
        self.assertEqual(list(teamcfg.load(ROOT / "templates/team.toml")["heuristic"]["tiers"][4]), ["name", "claude", "codex"])

    def test_example_with_a_three_tier_ladder_loads(self):
        teamcfg.load(ROOT.parent / "examples/unreal-p4/team.toml")

    def test_template_has_no_rule_naming_apex(self):
        self.assertNotIn('tier = "apex"', config_text("claude", "none"))


class ApexIsEscalationOnly(unittest.TestCase):
    base = config_text("claude", "none")

    def bad(self, text, msg):
        with self.assertRaisesRegex(ValueError, msg):
            load(text)

    def test_rule_min_tier(self):
        self.bad(self.base + '[[heuristic.rule]]\nname = "x"\nwhen = { risk = "high" }\nmin = { tier = "apex" }\n',
                 "escalation only")

    def test_pipeline_stage(self):
        self.bad(self.base.replace('hard = [["plan", "director"]', 'hard = [["plan", "apex"]'), "apex tier")

    def test_side_task_role(self):
        self.bad(re.sub(r'side_task_roles = \[', 'side_task_roles = ["apex", ', self.base), "apex tier")

    def test_role_reference(self):
        self.bad(self.base.replace("capacity_fallback = {}", 'capacity_fallback = {mid = "apex"}'), "apex tier")
        self.bad(self.base.replace('extra_review_role = "director"', 'extra_review_role = "apex"'), "apex tier")

    def test_domain_stage(self):
        self.bad(self.base.replace('[routing.domain.gameplay]\nplan = "gameplay"', '[routing.domain.gameplay]\nplan = "apex"'),
                 "apex tier")

    def test_unpinned_floor_model(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tpl/agents").mkdir(parents=True)
            (Path(d) / "tpl/agents/fab.md").write_text("---\nname: fab\nscope: x\nmodel: claude-fable-5-1\n---\nbody\n")
            p = Path(d) / "team.toml"
            p.write_text(self.base.replace('templates_dir = ""', 'templates_dir = "tpl"'))
            with self.assertRaisesRegex(ValueError, "apex tier"):
                teamcfg.load(p)


if __name__ == "__main__":
    unittest.main()
