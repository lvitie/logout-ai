"""[heuristic] tier ladder and rule table: validation, resolve(), floors and pins, usage input, snapshot. Run with python3 -I."""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import teamcfg  # noqa: E402
from cfgutil import TOML  # noqa: E402

_TMP = tempfile.mkdtemp()
for var, sub in (("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache"), ("CODEX_HOME", "codex")):
    os.environ[var] = os.path.join(_TMP, sub)
spec = importlib.util.spec_from_loader("team_heur", importlib.machinery.SourceFileLoader("team_heur", str(ROOT / "team.py")))
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)

# role: (cli, model, effort)
PROFILES = {"producer": ("claude", "s1", "low"), "mid": ("claude", "s1", "medium"), "senior": ("claude", "o1", "high"),
            "architect": ("claude", "o1", "high"), "director": ("claude", "f1", "high"), "cmid": ("codex", "c1", "medium"),
            "csenior": ("codex", "c2", "high"), "artist": ("claude", "x1", "low")}
ROLES = "".join(f'[roles.{k}]\nname = "{k.title()}"\ncli = "{c}"\nmodel = "{m}"\neffort = "{e}"\n' for k, (c, m, e) in PROFILES.items())
BASE = '''[vcs]
kind = "none"
[project]
templates_dir = "tpl"
[routing]
domains = ["code", "art"]
%s
[routing.pipeline]
simple = [["implement", "mid"], ["review", "architect"]]
complex = [["plan", "architect"], ["plan_review", "director"], ["implement", "mid"], ["review", "architect"]]
hard = [["plan", "director"], ["plan_review", "architect"], ["implement", "senior"], ["review", "architect"]]
'''
TIERS = '''[heuristic.tiers]
low = { claude = "mid", codex = "cmid" }
high = { claude = "senior", codex = "csenior" }
top = { claude = "director" }
'''


def rule(name, when, **mn):
    return f'[[heuristic.rule]]\nname = "{name}"\nwhen = {when}\nmin = {{ {", ".join(f"{k} = {json.dumps(v)}" for k, v in mn.items())} }}\n'


RULES = (rule("hard", '{ route = "hard" }', tier="high", effort="xhigh")
         + rule("risky", '{ risk = "high", size = ["medium", "large"] }', tier="high")
         + rule("art", '{ domain = "art" }', effort="high")
         + rule("retry", '{ failures_min = 2 }', tier="top")
         + rule("scarce", '{ usage = "low" }', tier="high")
         + rule("plan", '{ stage = "plan_review" }', tier="high")
         + rule("side", '{ route = "custom" }', tier="low", effort="low"))


def state(**kw):
    s = {"id": "t001", "request": "r", "change": "c", "route": "simple", "domain": "code", "stage": 0, "n": 0,
         "status": "running", "reason": "", "plan_rounds": 0, "review_rounds": 0, "notes": [], "plan_reviews": [],
         "reviews": [], "history": [], "risk": "low", "size": "small"}
    return {**s, **kw}


class Heuristic(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "tpl/agents").mkdir(parents=True)
        self.write_agent("artist", "Art.")

    def write_agent(self, name, body="Do it.", **meta):
        fm = "".join(f"{k}: {v}\n" for k, v in {"name": name, "scope": "s", **meta}.items())
        (self.d / f"tpl/agents/{name}.md").write_text(f"---\n{fm}---\n{body}\n")

    def cfg(self, extra="", tiers=TIERS, rules=RULES):
        p = self.d / "team.toml"
        p.write_text(BASE % extra + tiers + rules + ROLES)
        return p

    def init(self, **kw):
        team.init(self.cfg(**kw))
        team.task_dir("t001").mkdir(parents=True, exist_ok=True)
        team.RUNS.mkdir(parents=True, exist_ok=True)

    def bad(self, msg, **kw):
        with self.assertRaisesRegex(ValueError, msg):
            teamcfg.load(self.cfg(**kw))

    def resolve(self, **inp):
        h = teamcfg.load(self.cfg())["heuristic"]
        base = {"route": "simple", "domain": "code", "risk": "low", "size": "small", "stage": "implement", "failures": 0,
                "usage": None}
        return teamcfg.resolve(h, {**base, **inp})

    # --- validation ---
    def test_validation(self):
        for msg, kw in (
                ("needs at least one tier", {"tiers": "[heuristic.tiers]\n"}),
                ("not a \\[roles\\] profile running codex", {"tiers": '[heuristic.tiers]\na = { codex = "mid" }\n'}),
                ("not a \\[roles\\] profile running claude", {"tiers": '[heuristic.tiers]\na = { claude = "nobody" }\n'}),
                ("use \\{claude", {"tiers": '[heuristic.tiers]\na = { gemini = "mid" }\n'}),
                ("unknown when key", {"rules": rule("x", '{ color = "red" }', tier="low")}),
                ("when.risk must be", {"rules": rule("x", '{ risk = "extreme" }', tier="low")}),
                ("when.route 'weird'", {"rules": rule("x", '{ route = "weird" }', tier="low")}),
                ("when.domain 'ui'", {"rules": rule("x", '{ domain = "ui" }', tier="low")}),
                ("failures_min", {"rules": rule("x", '{ failures_min = 0 }', tier="low")}),
                ("when.usage must be", {"rules": rule("x", '{ usage = "maybe" }', tier="low")}),
                ("min.tier 'huge'", {"rules": rule("x", '{ route = "hard" }', tier="huge")}),
                ("min.effort", {"rules": rule("x", '{ route = "hard" }', effort="turbo")}),
                ("needs when", {"rules": rule("x", '{ route = "hard" }')}),
                ("takes only", {"rules": '[[heuristic.rule]]\nwhen = {}\nmin = { tier = "low" }\ntier = "low"\n'}),
                ("unique", {"rules": rule("x", "{}", tier="low") + rule("x", "{}", tier="high")})):
            with self.subTest(msg):
                self.bad(msg, **kw)

    def test_effort_must_fit_the_cli(self):
        p = self.cfg()
        p.write_text(p.read_text().replace('[roles.cmid]\nname = "Cmid"\ncli = "codex"\nmodel = "c1"\neffort = "medium"',
                                           '[roles.cmid]\nname = "Cmid"\ncli = "codex"\nmodel = "c1"\neffort = "max"'))
        with self.assertRaisesRegex(ValueError, "not a codex effort"):
            teamcfg.load(p)
        self.assertEqual(teamcfg.clamp_effort("codex", "max"), "xhigh")
        self.assertEqual(teamcfg.clamp_effort("claude", "minimal"), "low")
        self.assertEqual(teamcfg.clamp_effort("claude", "high"), "high")

    def test_bundled_ladder_skips_roles_on_another_cli(self):
        p = self.d / "team.toml"
        role = '[roles.%s]\nname = "%s"\ncli = "claude"'
        mid, senior = role % ("mid", "Mid Dev"), role % ("senior", "Senior Dev")
        self.assertIn(mid, TOML)
        p.write_text(TOML.replace(mid, mid.replace("claude", "codex")))
        tiers = teamcfg.load(p)["heuristic"]["tiers"]
        self.assertEqual([(t["name"], t["claude"], t["codex"]) for t in tiers][0], ("low", None, None))
        self.assertEqual(tiers[2]["claude"]["role"], "senior")
        # an empty upper tier would crash assign() on escalation: still refused
        p.write_text(TOML.replace(senior, senior.replace("claude", "codex")))
        with self.assertRaisesRegex(ValueError, "high: claude entry 'senior' is not a \\[roles\\] profile running claude"):
            teamcfg.load(p)
        # an edited ladder is the user's own: strict
        p.write_text(TOML.replace(mid, mid.replace("claude", "codex")).replace('top  = { claude = "director" }',
                                                                              'top  = { claude = "architect" }'))
        with self.assertRaisesRegex(ValueError, "low: claude entry 'mid' is not a \\[roles\\] profile running claude"):
            teamcfg.load(p)

    def test_no_table_loads_as_none(self):
        self.assertIsNone(teamcfg.load(self.cfg(tiers="", rules=""))["heuristic"])

    # --- resolve: one test row per rule, then precedence ---
    def test_each_rule(self):
        for name, inp, tier, effort, fired in (
                ("nothing matches", {}, "low", None, []),
                ("hard", {"route": "hard"}, "high", "xhigh", ["hard"]),
                ("risky", {"risk": "high", "size": "large"}, "high", None, ["risky"]),
                ("risky needs both", {"risk": "high", "size": "small"}, "low", None, []),
                ("art", {"domain": "art"}, "low", "high", ["art"]),
                ("retry", {"failures": 2}, "top", None, ["retry"]),
                ("retry below", {"failures": 1}, "low", None, []),
                ("scarce", {"usage": "low"}, "high", None, ["scarce"]),
                ("scarce needs the state", {"usage": "mixed"}, "low", None, []),
                ("plan", {"stage": "plan_review"}, "high", None, ["plan"]),
                ("side", {"route": "custom:mid"}, "low", "low", ["side"])):
            with self.subTest(name):
                got = self.resolve(**inp)
                self.assertEqual((got["tier"], got["effort_min"], got["rules"]), (tier, effort, fired))

    def test_precedence(self):
        got = self.resolve(route="hard", failures=3, domain="art")
        self.assertEqual((got["tier"], got["decided_by"]), ("top", "retry"))  # highest min wins, not the first rule
        self.assertEqual(got["rules"], ["hard", "art", "retry"])
        self.assertEqual(got["effort_min"], "xhigh")  # the highest effort min wins independently of the tier
        got = self.resolve(route="hard", risk="high", size="large")
        self.assertEqual(got["decided_by"], "hard")  # a tie: the first rule decides
        self.assertEqual(self.resolve()["decided_by"], "default")

    # --- floors and pins ---
    def test_floor_raises_and_never_lowers(self):
        h = teamcfg.load(self.cfg())["heuristic"]
        inp = {"route": "simple", "risk": "low", "size": "small", "stage": "implement"}
        got = teamcfg.resolve(h, inp, floor_model="o1")
        self.assertEqual((got["tier"], got["decided_by"]), ("high", "floor model o1"))
        got = teamcfg.resolve(h, {**inp, "route": "hard"}, floor_model="s1", floor_effort="medium")
        self.assertEqual((got["tier"], got["effort_min"], got["floor"]), ("high", "xhigh", False))  # rules already above
        got = teamcfg.resolve(h, inp, floor_effort="max")
        self.assertEqual((got["tier"], got["effort_min"]), ("low", "max"))
        self.assertEqual(teamcfg.floor_rank(h, "c2"), 1)  # a floor is a rank valid on any cli
        self.assertIsNone(teamcfg.floor_rank(h, "zz"))

    def test_floor_model_must_sit_on_a_rank(self):
        self.write_agent("artist", model="x1")  # x1 is a [roles] model but on no rank
        self.bad("floor model 'x1' is on no")
        self.write_agent("artist", model="x1", pin="true")  # a pin only needs to be a [roles] model
        self.assertTrue(teamcfg.load(self.cfg())["agent_defs"]["artist"]["pinned"])
        self.write_agent("artist", model="nope", pin="true")
        self.bad("not the model of any")
        self.write_agent("artist", model="o1")
        self.assertFalse(teamcfg.load(self.cfg())["agent_defs"]["artist"]["pinned"])

    def test_pin_frontmatter(self):
        self.write_agent("artist", pin="maybe", model="o1")
        self.bad("pin must be true or false")
        self.write_agent("artist", pin="true")
        self.bad("pin needs a model or effort")

    def test_floor_never_blocks_a_cli_swap_but_a_pin_does(self):
        self.write_agent("artist", model="o1")
        self.init()
        self.assertTrue(team.pin_fits("artist", "cmid"))
        self.write_agent("artist", model="o1", pin="true")
        self.init()
        self.assertFalse(team.pin_fits("artist", "cmid"))
        self.assertTrue(team.pin_fits("artist", "senior"))

    def test_without_table_model_is_still_exact(self):
        self.write_agent("artist", model="x1", effort="high")
        team.init(self.cfg(tiers="", rules=""))
        self.assertTrue(team.AGENTS["artist"]["pinned"])

    # --- the tiered selection ---
    def select(self, s, kind="implement", agent="mid", profile="mid"):
        h = team.ladder(s, kind)
        return team._select_tiered(s, kind, agent, profile, h)

    def assigned(self, s, kind="implement", agent="mid", profile="mid", burst=False):
        a, role, b, ctx = self.select(s, kind, agent, profile)
        cli, model, effort, prof = team._assignment(ctx, role, burst)
        return a, role, (cli, prof, model, effort), ctx

    def test_assignment_follows_the_rules_and_keeps_the_cli(self):
        self.init()
        self.assertEqual(self.assigned(state())[2], ("claude", "mid", "s1", "medium"))
        self.assertEqual(self.assigned(state(route="hard"))[2], ("claude", "senior", "o1", "xhigh"))  # tier + effort min
        self.assertEqual(self.assigned(state(domain="art"))[2], ("claude", "mid", "s1", "high"))  # effort only
        self.assertEqual(self.assigned(state(), agent="cmid", profile="cmid")[2], ("codex", "cmid", "c1", "medium"))
        self.assertEqual(self.assigned(state(impl_fails=2))[2], ("claude", "director", "f1", "high"))
        # the top tier has no codex profile: the rank's only cli
        self.assertEqual(self.assigned(state(impl_fails=2), agent="cmid", profile="cmid")[2][:2], ("claude", "director"))

    def test_floor_agent_gets_its_rank_and_effort(self):
        self.write_agent("artist", model="o1", effort="xhigh")
        self.init()
        self.assertEqual(self.assigned(state(), agent="artist", profile="mid")[2], ("claude", "senior", "o1", "xhigh"))

    def test_pin_is_exact_and_skips_the_rules(self):
        self.write_agent("artist", model="x1", effort="low", pin="true")
        self.init()
        s = state(route="hard")
        a, role, burst, ctx = self.select(s, agent="artist", profile="mid")
        self.assertEqual((a, role, ctx["record"]["decided_by"]), ("artist", "mid", "pin"))
        self.assertIsNone(ctx["h"])
        with mock.patch.object(team.subprocess, "Popen", side_effect=RuntimeError("stop")), \
                mock.patch.object(team, "ensure_guards"), self.assertRaises(RuntimeError):
            team._run_agent_once(s, "implement", a, role, burst, ctx)
        launch = json.loads((team.task_dir("t001") / "state.json").read_text())["launches"][0]
        self.assertEqual((launch["model"], launch["effort"], launch["heuristic"]["decided_by"]), ("x1", "low", "pin"))

    def test_override_acts_as_a_pin(self):
        self.init()
        (team.RUNS / "role_override.json").write_text(json.dumps({"t001": {"review": "architect"}}))
        a, role, _, ctx = self.select(state(route="hard"), kind="review", agent="director", profile="director")
        self.assertEqual((a, role, ctx["record"]["decided_by"]), ("architect", "architect", "override"))

    def test_after_impl_fails_no_longer_reassigns_the_agent(self):
        self.init(extra='[routing.after_impl_fails]\nfails = 1')
        a, role, _, ctx = self.select(state(impl_fails=1))
        self.assertEqual((a, team._assignment(ctx, role, False)[3]), ("mid", "mid"))  # escalation steps the tier instead

    def test_no_burst_effort_lowers_only_to_the_rule_minimum(self):
        self.init(extra='[routing.usage]\nno_burst_effort = { senior = "low" }')
        self.assertEqual(self.assigned(state(route="hard"), agent="senior", profile="senior")[2][3], "xhigh")
        self.assertEqual(self.assigned(state(), agent="senior", profile="senior")[2][3], "low")  # no rule minimum: lowered
        self.assertEqual(self.assigned(state(route="hard"), agent="senior", profile="senior", burst=True)[2][3], "xhigh")

    # --- usage ---
    def usage(self, ok_age=1.0, fail=False, low=False, mode="mixed"):
        now = time.time()
        team._usage.update(t=now, ok_t=now - ok_age, fail=fail, low=low, mode=mode)

    def test_usage_input_and_stale_data_is_ignored(self):
        self.init(extra='[routing.usage]\nenabled = true')
        self.usage(low=True)
        self.assertEqual(team.usage_input(), ("low", ""))
        self.assertEqual(self.assigned(state())[3]["tier"], 1)  # the usage rule fired
        for kw, why in (({"ok_age": 300}, "older than 120s"), ({"fail": True}, "failed")):
            with self.subTest(kw):
                self.usage(low=True, **kw)  # stale or failed: the cached "low" must not match
                got = self.assigned(state())[3]
                self.assertEqual(got["tier"], 0)
                self.assertIn(why, " ".join(got["record"]["notes"]))
                self.assertIsNone(got["record"]["inputs"]["usage"])
        self.usage(mode="claude")
        self.assertEqual(team.usage_input(), ("claude", ""))

    def test_failed_fetch_marks_usage_stale(self):
        self.init(extra='[routing.usage]\nenabled = true')
        self.usage(low=True)
        team._usage["t"] = 0  # due for a refresh
        with mock.patch.object(team.subprocess, "run", side_effect=OSError("no usage_tui")):
            team.claude_low()
        self.assertTrue(team._usage["fail"])
        self.assertEqual(team.usage_input()[0], None)

    def test_disabled_usage_never_matches(self):
        self.init()
        self.usage(low=True)
        self.assertEqual(team.usage_input(), (None, "usage balancing is disabled"))

    def test_usage_balancing_picks_the_cli_at_the_tier(self):
        self.init(extra='[routing.usage]\nenabled = true\nclaude_fallback = { mid = "cmid", senior = "csenior" }')
        self.usage(low=True)  # the Claude plan is nearly used up: claude_fallback picks Codex at the same rank
        got = self.assigned(state(route="hard"), agent="senior", profile="senior")
        self.assertEqual(got[2], ("codex", "csenior", "c2", "xhigh"))
        got = self.assigned(state(impl_fails=2), agent="senior", profile="senior")  # top has no codex profile: skipped
        self.assertEqual(got[2][:2], ("claude", "director"))

    def test_clamped_swaps_never_drop_below_the_tier(self):
        self.init(extra='[routing.usage]\nenabled = true\nescalation_gate = { role = "director", first = "mid", second_review = "architect" }')
        self.usage()
        with mock.patch.object(team, "burst_active", return_value=False):
            a, role, _, ctx = self.select(state(route="hard"), kind="review", agent="director", profile="director")
        self.assertEqual(role, "director")  # "mid" sits on rank 0, below the review's tier

    def test_capacity_retry_stays_at_or_above_the_tier(self):
        self.init(extra='capacity_fallback = { senior = "mid", director = "senior" }')
        s = state(route="hard", reason="x see /nope")
        a, role, burst, ctx = self.select(s, agent="senior", profile="senior")
        self.assertEqual(ctx["tier"], 1)
        results = [(None, None)]

        def once(s_, *a_):
            s_["status"], s_["reason"] = "failed", "boom see /nope"
            return results[0]
        with mock.patch.object(team, "_run_agent_once", side_effect=once), \
                mock.patch.object(team, "capacity_error", return_value=True):
            team.run_agent(s, "implement", "senior", "senior")
        self.assertEqual(s["status"], "blocked")  # mid is rank 0 < tier high: nothing left
        self.assertIn("no profile at or above tier high", s["reason"])

    # --- launch record, snapshot and resume ---
    def launch(self, s, kind="implement", agent="mid", profile="mid"):
        with mock.patch.object(team.subprocess, "Popen", side_effect=RuntimeError("stop")), \
                mock.patch.object(team, "ensure_guards"), self.assertRaises(RuntimeError):
            team.run_agent(s, kind, agent, profile)
        return json.loads((team.task_dir(s["id"]) / "state.json").read_text())

    def test_launch_logs_rule_and_records_it_in_state(self):
        self.init()
        got = self.launch(state(route="hard"))["launches"][0]
        h = got["heuristic"]
        self.assertEqual((h["tier"], h["decided_by"], h["rules"], h["assigned"]), ("high", "hard", ["hard"], "senior"))
        self.assertEqual(h["inputs"]["route"], "hard")
        self.assertEqual((got["cli"], got["model"], got["effort"]), ("claude", "o1", "xhigh"))
        log = team.LIVE.read_text()
        self.assertIn("heuristic implement: high via hard (rules: hard) -> senior claude o1 xhigh", log)

    def test_config_edit_does_not_change_a_task_in_flight(self):
        self.init()
        s = state(route="hard")
        first = self.launch(s)
        self.assertIn("heuristic", first)
        self.init(rules=rule("hard", '{ route = "hard" }', tier="top"))  # the edited config: hard now needs top
        self.assertEqual(team.CFG["heuristic"]["rules"][0]["min"]["tier"], "top")
        s = first
        s["history"].append(s["launches"][0]["stem"])
        got = self.launch(s)["launches"][1]["heuristic"]
        self.assertEqual(got["tier"], "high")  # resolved from the task's snapshot
        fresh = self.launch(state(id="t001", route="hard"))["launches"][0]["heuristic"]
        self.assertEqual(fresh["tier"], "top")  # a new task takes the edited table

    def test_resume_reproduces_the_tier_of_the_unfinished_launch(self):
        self.init()
        s = self.launch(state(route="hard"))
        self.assertEqual(s["launches"][0]["heuristic"]["tier"], "high")
        s["route"], s["risk"] = "simple", "low"  # what the rules read changed, the launch never finished
        got = self.launch(s)["launches"][1]["heuristic"]
        self.assertEqual((got["tier"], got["decided_by"]), ("high", "resume"))
        self.assertIn("resume", " ".join(got["notes"]))
        s = json.loads((team.task_dir("t001") / "state.json").read_text())
        s["history"] = [s["launches"][-1]["stem"]]  # the launch finished: the next stage resolves afresh
        s["stage"] = 1
        self.assertEqual(self.launch(s)["launches"][2]["heuristic"]["tier"], "low")

    def test_no_table_leaves_selection_and_launch_unchanged(self):
        self.init(tiers="", rules="")
        s = state(route="hard")
        self.assertIsNone(team.ladder(s, "implement"))
        self.assertEqual(team._select_agent_role(s, "implement", "mid", "mid")[:2], ("mid", "mid"))
        got = self.launch(s)
        self.assertNotIn("heuristic", got)
        self.assertNotIn("heuristic", got["launches"][0])
        self.assertEqual((got["launches"][0]["model"], got["launches"][0]["effort"]), ("s1", "medium"))

    def test_refill_never_uses_the_table(self):
        self.init()
        self.assertIsNone(team.ladder(state(id="refill"), "refill"))

    # --- risk and size inputs ---
    def test_side_task_defaults_are_fixed_at_creation(self):
        self.init(extra='side_task_roles = ["mid"]')
        s = team.create_task("do", role="mid")
        self.assertEqual((s["risk"], s["size"]), ("high", "large"))
        self.assertIn("no valid RISK", team.LIVE.read_text())
        s = team.create_task("do", role="mid", risk="low", size="small")
        self.assertEqual((s["risk"], s["size"]), ("low", "small"))
        self.assertEqual(self.assigned(s, agent="mid", profile="mid")[3]["tier"], 0)

    def test_route_stage_never_matches_risk_or_size_rules(self):
        self.init()
        s = state(route=None, stage=-1)
        del s["risk"], s["size"]
        ctx = self.select(s, kind="route", agent="producer", profile="producer")[3]
        self.assertNotIn("risky", ctx["record"]["rules"])
        self.assertEqual((ctx["record"]["inputs"]["risk"], ctx["record"]["inputs"]["size"]), (None, None))
        self.assertIn("risky", self.select(s)[3]["record"]["rules"])  # later stages keep the high/large default

    def test_route_reply_sets_risk_and_size(self):
        self.init()
        s = state(route=None, stage=-1)
        del s["risk"], s["size"]
        team.set_risk_size(s, "medium", "bogus")
        self.assertEqual((s["risk"], s["size"]), ("medium", "large"))
        team.set_risk_size(s, None, "small")  # a missing value keeps the earlier one
        self.assertEqual((s["risk"], s["size"]), ("medium", "small"))
        self.assertIn("no valid SIZE (bogus)", team.LIVE.read_text())
        self.assertEqual(team.tag("RISK: high\nSIZE: large", "RISK")[0], "high")
        self.assertNotIn("RISK", team.body("RISK: high\ntext"))


if __name__ == "__main__":
    unittest.main()
