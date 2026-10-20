"""Adaptive pipeline: light routes, skip defaults, plan_implement, upgrade on a failed review, route metrics and
back-compat of old pipelines. Run with python3 -I."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import teamcfg  # noqa: E402
from test_heuristic import BASE, ROLES, TIERS, rule, team, state  # noqa: E402

FAIL = "Findings.\nSEVERITY: minor\nVERDICT: FAIL\n"


class Adaptive(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "tpl/agents").mkdir(parents=True)
        self.out = str(self.d / "02-review-architect.md")
        Path(self.out).write_text("Findings.\n")

    def init(self, pre="", extra="", base=BASE, tiers=TIERS):
        p = self.d / "team.toml"
        p.write_text(base % pre + extra + tiers + ROLES)
        team.init(p)
        team.RUNS.mkdir(parents=True, exist_ok=True)
        team.task_dir("t001").mkdir(parents=True, exist_ok=True)
        return p

    def kinds(self, route, domain="code", no_skip=False):
        return [k for k, _ in team.pipeline(route, domain, no_skip)]

    def run_step(self, s, kind, agent, text):
        with mock.patch.object(team, "run_agent", return_value=(self.out, text, agent, agent)):
            team.step(s, team.task_stages(s))

    def at_review(self, route, **kw):
        s = state(route=route, **kw)
        s["stage"] = next(i for i, (k, _) in enumerate(team.task_stages(s)) if k == "review")
        return s

    # --- routes ---
    def test_light_routes_are_derived_and_simple_is_an_alias(self):
        self.init()
        self.assertEqual(self.kinds("direct"), ["implement", "review"])
        self.assertEqual(self.kinds("simple"), ["implement", "review"])
        self.assertEqual(self.kinds("bundled"), ["plan_implement", "review"])
        self.assertEqual(self.kinds("planned"), ["plan", "implement", "review"])
        self.assertEqual(self.kinds("complex"), ["plan", "plan_review", "implement", "review"])
        self.assertEqual(teamcfg.canon_route("simple"), "direct")

    def test_configured_light_route_overrides_the_derived_one(self):
        base = BASE.replace("hard = ", 'bundled = [["plan_implement", "senior"], ["review", "architect"]]\nhard = ')
        self.init(base=base)
        self.assertEqual(team.CFG["routing"]["pipeline"]["bundled"][0], ["plan_implement", "senior"])

    def test_direct_alone_loads_and_simple_follows(self):
        self.init(base=BASE.replace("simple =", "direct ="))
        self.assertEqual(self.kinds("simple"), ["implement", "review"])

    def test_every_pipeline_kind_still_validates(self):
        bad = BASE.replace('["review", "architect"]]\ncomplex', '["bogus", "architect"]]\ncomplex')
        with self.assertRaises(ValueError):
            self.init(base=bad)

    # --- skips ---
    def test_skip_defaults_by_route_and_domain(self):
        self.init(extra='[routing.skip]\ncomplex = ["plan_review"]\n[routing.domain.art]\nskip = ["plan"]\n')
        self.assertEqual(self.kinds("complex"), ["plan", "implement", "review"])
        self.assertEqual(self.kinds("complex", "art"), ["implement", "review"])  # plan implies plan_review
        self.assertEqual(self.kinds("complex", "art", no_skip=True), ["plan", "plan_review", "implement", "review"])
        self.assertEqual(self.kinds("hard", "art"), ["plan", "plan_review", "implement", "review"])  # hard never skips

    def test_review_and_hard_cannot_be_skipped(self):
        for extra in ('[routing.skip]\ncomplex = ["review"]\n', '[routing.skip]\nhard = ["plan_review"]\n',
                      '[routing.domain.art]\nskip = ["review"]\n', '[routing.domain.art]\nskip = ["implement"]\n'):
            with self.assertRaises(ValueError, msg=extra):
                self.init(extra=extra)

    def test_stage_profile_follows_the_skipped_list(self):
        self.init(extra='[routing.skip]\ncomplex = ["plan"]\n')
        self.assertEqual([team.stage_profile("complex", "code", i) for i in range(2)], ["mid", "architect"])
        self.assertEqual([team.stage_profile("complex", "code", i, True) for i in range(4)],
                         ["architect", "director", "mid", "architect"])

    def test_skipped_kinds_for_views(self):
        self.init()
        self.assertEqual(team.skipped_kinds(state(route="direct")), ["plan", "plan_review"])
        self.assertEqual(team.skipped_kinds(state(route="bundled")), ["plan_review"])
        self.assertEqual(team.skipped_kinds(state(route="planned")), ["plan_review"])
        self.assertEqual(team.skipped_kinds(state(route="complex")), [])
        self.assertEqual(team.skipped_kinds(state(route="custom:mid")), [])

    # --- the combined stage ---
    def test_plan_implement_writes_plan_and_report_and_advances(self):
        self.init()
        s = state(route="bundled", stage=0)
        self.run_step(s, "plan_implement", "mid", "## Plan\n1. x\nSTATUS: DONE\n")
        self.assertEqual((s["stage"], s["plan"], s["report"]), (1, self.out, self.out))

    def test_plan_implement_gate_and_domain_agent(self):
        self.init(extra='[routing.domain.art]\nimplement = "artist"\nreview = "architect"\n')
        self.assertEqual(team.pipeline("bundled", "art")[0], ("plan_implement", "artist"))
        s = state(route="bundled", stage=0)
        self.run_step(s, "plan_implement", "mid", "STATUS: GATE which API?\n")
        self.assertEqual(s["status"], "gate")

    def test_plan_implement_is_the_author_in_reviewer_checks(self):
        with self.assertRaises(ValueError):
            self.init(extra='[routing.domain.art]\nimplement = "artist"\nreview = "artist"\n')

    def test_plan_implement_matches_plan_and_implement_stage_rules(self):
        self.assertTrue(teamcfg._matches({"stage": "implement"}, {"stage": "plan_implement"}))
        self.assertTrue(teamcfg._matches({"stage": ["plan"]}, {"stage": "plan_implement"}))
        self.assertFalse(teamcfg._matches({"stage": "review"}, {"stage": "plan_implement"}))
        self.assertTrue(teamcfg._matches({"route": "simple"}, {"route": "direct"}))

    def test_task_skill_for_plan_or_implement_reaches_plan_implement(self):
        self.init()
        pl = team.pipeline("bundled", "code")
        self.assertEqual(team.kinds_of(pl), {"plan", "implement", "plan_implement", "review"})

    # --- route selection ---
    def test_forced_route_replaces_the_pick_but_never_lowers_risk_checks(self):
        self.init()
        s = state(route_forced="direct", risk="low")
        self.assertEqual(team.lighter_guard(s, "complex"), "direct")
        s = state(route_forced="direct", risk="high")
        self.assertEqual(team.lighter_guard(s, "complex"), "complex")
        self.assertTrue(s["notes"])
        s = state(route_forced="direct", risk="low")
        self.assertEqual(team.lighter_guard(s, "hard"), "hard")
        self.assertEqual(team.lighter_guard(state(route_forced="direct"), "ask"), "ask")

    def test_light_pick_is_raised_on_high_risk_or_earlier_failures(self):
        self.init()
        for kw in ({"risk": "high"}, {"risk": "low", "impl_fails": 1}, {"risk": "low", "no_skip": True}):
            self.assertEqual(team.lighter_guard(state(**kw), "bundled"), "complex", kw)
        self.assertEqual(team.lighter_guard(state(risk="low"), "planned"), "planned")
        self.assertEqual(team.lighter_guard(state(risk="high"), "hard"), "hard")

    # --- upgrade on a failed review ---
    def test_failed_review_upgrades_a_skipped_plan_route(self):
        self.init()
        for start, new, kinds in (("direct", "planned", ["plan", "implement", "review"]),
                                  ("bundled", "planned", ["plan", "implement", "review"]),
                                  ("planned", "complex", ["plan", "plan_review", "implement", "review"])):
            s = self.at_review(start)
            self.run_step(s, "review", "architect", FAIL)
            self.assertEqual((s["route"], s["stage"], s["no_skip"], s["upgrades"], s["impl_fails"]), (new, 0, True, 1, 1), start)
            self.assertEqual([k for k, _ in team.task_stages(s)], kinds)
            self.assertEqual(s["status"], "running")

    def test_upgrade_feeds_the_findings_to_the_plan_prompt(self):
        self.init()
        s = self.at_review("direct")
        self.run_step(s, "review", "architect", FAIL)
        self.assertEqual(s["reviews"], [self.out])
        s["stage"] = 0
        (self.d / "tpl/jobs").mkdir(parents=True, exist_ok=True)
        with mock.patch.object(team, "env_status", return_value=""):
            self.assertIn("Earlier findings", team.build_prompt(s, "plan", "architect"))

    def test_upgrade_counts_as_a_heuristic_failure(self):
        self.init(extra=rule("retry", '{ failures_min = 2 }', tier="high"))
        s = self.at_review("direct")
        self.run_step(s, "review", "architect", FAIL)
        self.assertEqual((s["impl_fails"] + s["plan_rounds"], s["upgrades"]), (1, 1))
        with mock.patch.object(team, "claude_low"), mock.patch.object(team, "usage_input", return_value=(None, "")), \
                mock.patch.object(team.teamcfg, "resolve", side_effect=RuntimeError) as res:
            with self.assertRaises(RuntimeError):
                team._select_tiered(s, "plan", "architect", "architect", team.CFG["heuristic"])
        self.assertEqual(res.call_args[0][1]["failures"], 1)  # one failed review, not counted again by the upgrade

    def test_review_prompt_after_plan_implement_has_the_handoff_once(self):
        self.init()
        s = self.at_review("bundled")
        h = self.d / "handoff.md"
        h.write_text("UNIQUE-HANDOFF-BODY\n")
        s["plan"] = s["report"] = str(h)
        (self.d / "tpl/jobs").mkdir(parents=True, exist_ok=True)
        with mock.patch.object(team, "env_status", return_value=""):
            prompt = team.build_prompt(s, "review", "architect")
        self.assertEqual(prompt.count("UNIQUE-HANDOFF-BODY"), 1)
        self.assertNotIn("## Plan\n", prompt)

    def test_configured_skip_is_dropped_on_failure(self):
        self.init(extra='[routing.skip]\ncomplex = ["plan_review"]\n')
        s = self.at_review("complex")
        self.run_step(s, "review", "architect", FAIL)
        self.assertEqual((s["route"], s["no_skip"], s["stage"]), ("complex", True, 0))
        self.assertEqual(self.kinds("complex", no_skip=True), ["plan", "plan_review", "implement", "review"])
        s["stage"] = next(i for i, (k, _) in enumerate(team.task_stages(s)) if k == "review")
        self.run_step(s, "review", "architect", FAIL)  # already full: the normal retry
        self.assertEqual((s["upgrades"], s["stage"]), (1, 2))

    def test_no_upgrade_for_full_hard_custom_and_legacy_simple_routes(self):
        self.init()
        for route in ("complex", "hard", "simple", "custom:mid"):
            s = self.at_review(route)
            self.run_step(s, "review", "architect", FAIL)
            self.assertEqual((s["route"], s.get("upgrades", 0), s.get("no_skip")), (route, 0, None), route)

    def test_redo_keeps_no_skip(self):
        self.init()
        s = self.at_review("direct")
        self.run_step(s, "review", "architect", FAIL)
        self.assertTrue(s["no_skip"])
        self.assertEqual(team.stage_label(s), "plan/architect")
        self.assertIn(("implement", "mid"), team.task_stages(s))

    def test_review_is_never_skipped(self):
        self.init(extra='[routing.skip]\ncomplex = ["plan", "plan_review"]\ndirect = ["plan"]\n')
        for r in ("direct", "bundled", "planned", "complex"):
            self.assertIn("review", self.kinds(r), r)

    # --- metrics ---
    def test_first_pass_and_review_rounds_total(self):
        self.init()
        s = self.at_review("direct")
        self.run_step(s, "review", "architect", "VERDICT: PASS\n")
        self.assertEqual((s["first_pass"], s["review_rounds_total"]), (True, 1))
        s = self.at_review("complex")
        self.run_step(s, "review", "architect", FAIL)
        s["stage"] = 3
        self.run_step(s, "review", "architect", "VERDICT: PASS\n")
        self.assertEqual((s["first_pass"], s["review_rounds_total"]), (False, 2))

    def test_escalations_count_user_handoffs(self):
        self.init()
        s = self.at_review("complex", heuristic=None)
        self.run_step(s, "review", "architect", "SEVERITY: major\nVERDICT: FAIL\n")
        self.assertEqual((s["status"], s["escalations"]), ("escalated", 1))

    def test_route_metrics_group_by_initial_route(self):
        self.init()
        rows = [state(id="t001", route="planned", route_initial="direct", status="done", created=100, first_finish=700,
                      finished=900, first_pass=False, review_rounds_total=2, upgrades=1, escalations=1, skipped=["plan"]),
                state(id="t002", route="simple", status="done", created=10, finished=70, first_pass=True,
                      review_rounds_total=1)]
        for r in rows:
            team.task_dir(r["id"]).mkdir(parents=True, exist_ok=True)
            (team.task_dir(r["id"]) / "state.json").write_text(json.dumps(r))
        m = team.route_metrics()
        self.assertEqual(m["direct"]["tasks"], 2)
        self.assertEqual((m["direct"]["upgrades"], m["direct"]["escalations"], m["direct"]["rounds"]), (1, 1, 3))
        self.assertEqual((m["direct"]["first_pass"], m["direct"]["wall"]), (0.5, (600 + 60) / 2))
        self.assertIn("direct", "\n".join(team.metrics_lines()))

    def test_cumulative_counters_survive_a_redo(self):
        self.init()
        s = state(route="planned", upgrades=1, review_rounds_total=3, escalations=2, first_pass=False)
        s["notes"] = []
        team.reset_escalation(s)
        s["plan_rounds"] = s["review_rounds"] = 0
        self.assertEqual((s["upgrades"], s["review_rounds_total"], s["escalations"], s["first_pass"]), (1, 3, 2, False))


if __name__ == "__main__":
    unittest.main()
