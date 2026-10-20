"""Review severity, tier step-up, the cap, user escalation and the takeover / after_impl_fails mapping. Run with python3 -I."""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import teamcfg  # noqa: E402
from test_heuristic import BASE, ROLES, TIERS, team, state  # noqa: E402



def verdict(v="FAIL", sev=None, esc=None):
    return "Findings.\n" + (f"SEVERITY: {sev}\n" if sev else "") + (f"ESCALATE: {esc}\n" if esc else "") + f"VERDICT: {v}\n"


class Escalation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "tpl/agents").mkdir(parents=True)
        self.out = str(self.d / "02-review-architect.md")
        Path(self.out).write_text("Findings.\n")

    def cfg(self, extra="", tiers=TIERS, pre=""):
        p = self.d / "team.toml"
        p.write_text(BASE % (pre + "\n" + extra) + tiers + ROLES)
        return p

    def init(self, extra="", **kw):
        team.init(self.cfg(extra, **kw))
        team.RUNS.mkdir(parents=True, exist_ok=True)
        team.task_dir("t001").mkdir(parents=True, exist_ok=True)

    def task(self, rank=0, **kw):
        """A simple-route task whose implementation ran at `rank` and now sits at the review stage."""
        s = state(stage=1, history=["01-implement-mid"], impl_fails=0, **kw)
        s["heuristic"] = team.json.loads(team.json.dumps(team.CFG["heuristic"])) if team.CFG["heuristic"] else None
        s["launches"] = [{"stem": "01-implement-mid", "agent": "mid", "profile": "mid",
                          "heuristic": {"kind": "implement", "rank": rank}}]
        return s

    def review(self, s, text):
        """One review stage returning `text`; the task is moved back to the review stage first."""
        s["stage"] = 1
        with mock.patch.object(team, "run_agent", return_value=(self.out, text, "architect", "architect")):
            team.step(s, team.pipeline(s["route"], s["domain"]))

    def fail_review(self, s, sev=None, esc=None):
        self.review(s, verdict("FAIL", sev, esc))
        if s["status"] == "running":  # as advance() would: the implement stage ran again at the stepped tier
            s["launches"].append({"stem": f"{len(s['launches']) + 1:02d}-implement-mid", "agent": "mid", "profile": "mid",
                                  "heuristic": {"kind": "implement", "rank": max([0] + [e["rank"] for e in s.get("stepped", [])])}})

    # --- parsing ---
    def test_parse_severity_and_escalate(self):
        self.assertEqual(team.tag(verdict(sev="Critical."), "SEVERITY")[0], "critical")
        self.assertEqual(team.tag(verdict(esc="yes needs the director"), "ESCALATE"), ("yes", "needs the director"))
        stripped = team.body(verdict("FAIL", "major", "yes why"))
        self.assertNotIn("SEVERITY", stripped)
        self.assertNotIn("ESCALATE", stripped)
        self.assertNotIn("VERDICT", stripped)

    def test_missing_or_bad_severity_on_a_fail_is_major(self):
        self.init()
        for sev in (None, "huge"):
            s = self.task()
            self.fail_review(s, sev)
            self.assertEqual([e["rank"] for e in s["stepped"]], [1], sev)
            self.assertNotIn("diagnose", s)  # major: one tier, no diagnosis

    def test_pass_with_escalate_counts_as_a_fail(self):
        self.init()
        s = self.task()
        self.review(s, verdict("PASS", esc="yes risky area"))
        self.assertEqual((s["stage"], s["review_rounds"], s["diagnose"]), (0, 1, "implement"))
        self.assertEqual(s["stepped"][0]["rules"], ["severity major", "recommended: risky area"])

    def test_pass_moves_on_and_clears_the_diagnosis(self):
        self.init()
        s = self.task()
        s["diagnose"] = "implement"
        self.review(s, verdict("PASS"))
        self.assertEqual((s["stage"], "diagnose" in s), (2, False))

    def test_no_verdict_fails_the_task(self):
        self.init()
        s = self.task()
        self.review(s, "SEVERITY: major\n")
        self.assertEqual(s["status"], "failed")

    # --- minor ---
    def test_minor_never_steps_and_stops_at_max_rounds(self):
        self.init()
        s = self.task()
        for n in (1, 2):
            self.fail_review(s, "minor")
            self.assertEqual((s["status"], s["stage"], s["minor_rounds"]["implement"]), ("running", 0, n))
        self.fail_review(s, "minor")
        self.assertEqual(s["status"], "escalated")
        self.assertIn("minor", s["reason"])
        self.assertNotIn("stepped", s)

    def test_major_rounds_are_not_limited_by_max_rounds(self):
        self.init()
        s = self.task()
        self.fail_review(s, "major")  # low -> high; the cap test covers the end of the ladder
        self.assertEqual((s["status"], s.get("minor_rounds")), ("running", None))

    # --- step-up, the cap, the user ---
    def test_major_steps_one_tier_and_critical_adds_a_diagnosis(self):
        self.init()
        s = self.task()
        self.fail_review(s, "major")
        self.assertEqual(s["stepped"][0]["rank"], 1)
        self.assertNotIn("diagnose", s)
        self.fail_review(s, "critical")
        self.assertEqual((s["stepped"][-1]["rank"], s["diagnose"]), (2, "implement"))
        with mock.patch.object(team, "env_status", return_value=""):
            self.assertIn("## Diagnosis required", team.build_prompt({**s, "request": "r", "spec": None}, "implement", "mid"))
            self.assertNotIn("## Diagnosis required", team.build_prompt({**s, "request": "r", "spec": None}, "review", "architect"))

    def test_step_up_is_applied_at_launch(self):
        self.init(tiers=TIERS)
        s = self.task()
        s["stepped"] = [{"kind": "implement", "agent": "mid", "rank": 1, "rules": ["severity major"]}]
        s.pop("launches")
        a, role, _, ctx = team._select_tiered(s, "implement", "mid", "mid", team.ladder(s, "implement"))
        self.assertEqual((ctx["record"]["tier"], ctx["rank"], ctx["record"]["decided_by"]), ("high", 1, "step-up"))
        self.assertNotEqual(team._select_tiered(s, "review", "architect", "architect", team.ladder(s, "review"))[3]["record"]["decided_by"], "step-up")

    def test_cap_goes_to_the_user_and_approve_retries_at_the_cap(self):
        self.init()
        s = self.task(rank=2)  # the strongest of the three tiers
        self.fail_review(s, "major")
        self.assertEqual(s["status"], "escalated")
        self.assertIn("strongest tier (top)", s["reason"])
        self.assertNotIn("stepped", s)
        team.reset_escalation(s)  # `team approve`
        self.assertEqual([(e["kind"], e["rank"]) for e in s["stepped"]], [("implement", 2)])
        self.assertNotIn("capped", s)
        s["status"] = "running"
        self.fail_review(s, "major")  # the next major failure goes to the user again
        self.assertEqual(s["status"], "escalated")

    def test_recommendation_at_the_cap_goes_to_the_user(self):
        self.init()
        s = self.task(rank=2)
        self.fail_review(s, "minor", "yes needs a human")
        self.assertEqual(s["status"], "escalated")
        self.assertEqual(s["diagnose"], "implement")

    def test_no_ladder_pin_or_override_goes_to_the_user(self):
        self.init(tiers="")
        s = self.task()
        self.fail_review(s, "major")
        self.assertEqual(s["status"], "escalated")
        self.assertIn("no tier ladder", s["reason"])
        self.init()  # a pinned agent or a role_override launch has no rank in its record
        s = self.task()
        s["launches"][0]["heuristic"] = {"kind": "implement", "decided_by": "pin", "rules": []}
        self.fail_review(s, "critical")
        self.assertEqual(s["status"], "escalated")

    def test_plan_review_failures_step_the_plan(self):
        self.init()
        s = state(route="complex", stage=1, history=["01-plan-architect"], impl_fails=0)
        s["heuristic"] = team.json.loads(team.json.dumps(team.CFG["heuristic"]))
        s["launches"] = [{"stem": "01-plan-architect", "agent": "architect", "profile": "architect",
                          "heuristic": {"kind": "plan", "rank": 0}}]
        with mock.patch.object(team, "run_agent", return_value=(self.out, verdict("FAIL", "major"), "director", "director")):
            team.step(s, team.pipeline("complex", "code"))
        self.assertEqual((s["stage"], s["stepped"][0]["kind"], s["stepped"][0]["rank"], s["impl_fails"]), (0, "plan", 1, 0))

    # --- takeover and after_impl_fails ---
    def test_takeover_without_to_steps_the_same_agent_once(self):
        self.init("[routing.takeover.mid]\nafter_reviews = 2")
        s = self.task()
        self.fail_review(s, "minor")
        self.assertNotIn("stepped", s)  # 1 failed review < after_reviews
        self.fail_review(s, "minor")
        self.assertEqual([(e["kind"], e["agent"], e["rank"], e["rules"]) for e in s["stepped"]], [("implement", "mid", 1, ["takeover"])])
        s["status"] = "running"
        self.fail_review(s, "minor")
        self.assertEqual(len(s["stepped"]), 1)  # once

    def test_takeover_after_attempt(self):
        self.init("[routing.takeover.mid]\nafter_reviews = 5\nafter_attempt = true")
        s = self.task()
        self.fail_review(s, "minor")
        self.assertEqual(s["stepped"][0]["rules"], ["takeover"])

    def test_takeover_with_to_reassigns_and_must_not_be_the_reviewer(self):
        self.init('[routing.takeover.mid]\nto = "senior"\nafter_reviews = 1')
        s = {"id": "t001", "route": "simple", "domain": "code", "stage": 0, "review_rounds": 1, "history": []}
        with mock.patch.object(team, "run_agent", return_value=(None, None, "senior", "senior")) as run:
            team.step(s, team.pipeline("simple", "code"))
        self.assertEqual(run.call_args.args[2:], ("senior", "senior"))
        with self.assertRaisesRegex(ValueError, "reviews this work"):
            teamcfg.load(self.cfg('[routing.takeover.mid]\nto = "architect"'))
        with self.assertRaisesRegex(ValueError, "takes only"):
            teamcfg.load(self.cfg('[routing.takeover.mid]\nroles = "senior"'))

    def test_after_impl_fails_steps_once_at_the_count(self):
        self.init("[routing.after_impl_fails]\nfails = 2")
        s = self.task()
        self.fail_review(s, "minor")
        self.assertNotIn("stepped", s)
        self.fail_review(s, "minor")
        self.assertEqual([e["rules"] for e in s["stepped"]], [["after_impl_fails"]])
        s["minor_rounds"] = {}
        self.fail_review(s, "minor")
        self.assertEqual(len(s["stepped"]), 1)

    def test_one_failure_gives_one_step(self):
        self.init("[routing.takeover.mid]\nafter_reviews = 1\n[routing.after_impl_fails]\nfails = 1")
        s = self.task()
        self.fail_review(s, "critical", "yes deeper")
        self.assertEqual(len(s["stepped"]), 1)
        self.assertEqual(s["stepped"][0]["rank"], 1)
        self.assertEqual(s["stepped"][0]["rules"],
                         ["severity critical", "recommended: deeper", "takeover", "after_impl_fails"])

    def test_after_impl_fails_role_is_ignored_with_a_warning(self):
        with self.assertWarnsRegex(UserWarning, "role is ignored"):
            cfg = teamcfg.load(self.cfg('[routing.after_impl_fails]\nfails = 2\nrole = "senior"'))
        self.assertEqual(cfg["routing"]["after_impl_fails"]["fails"], 2)
        with self.assertRaisesRegex(ValueError, "fails"):
            teamcfg.load(self.cfg("[routing.after_impl_fails]\nrole = \"senior\""))
        self.init("[routing.after_impl_fails]\nfails = 1")  # the old swap is gone
        s = self.task()
        s["impl_fails"] = 1
        self.assertEqual(team._reassign(s, "implement", "mid", "mid"), ("mid", "mid", False))

    # --- approve and redo ---
    def test_redo_and_approve_clear_the_escalation_state(self):
        self.init()
        for cmd in ("approve", "redo"):
            s = self.task()
            s.update(stepped=[{"kind": "implement", "agent": "mid", "rank": 1, "rules": []}], diagnose="implement",
                     minor_rounds={"implement": 2}, status="escalated", reason="x", route="simple", notes=[])
            with mock.patch.object(team, "advance"), mock.patch.object(team, "load", return_value=s):
                getattr(team, f"cmd_{cmd}")(mock.Mock(id="t001", note="n"))
            self.assertTrue(all(k not in s for k in ("stepped", "diagnose", "minor_rounds")), cmd)

    def test_approve_after_the_cap_retries_there_and_redo_starts_over(self):
        self.init()
        for cmd, stepped in (("approve", [{"kind": "implement", "agent": "", "rank": 2,
                                            "rules": ["approved at the cap"]}]), ("redo", None)):
            s = self.task()
            s.update(stepped=[{"kind": "implement", "agent": "mid", "rank": 2, "rules": []}], capped="implement",
                     status="escalated", reason="x", route="simple", notes=[])
            with mock.patch.object(team, "advance"), mock.patch.object(team, "load", return_value=s):
                getattr(team, f"cmd_{cmd}")(mock.Mock(id="t001", note="n"))
            self.assertEqual(s.get("stepped"), stepped, cmd)
            self.assertNotIn("capped", s, cmd)


class LadderKeepsDefaults(unittest.TestCase):
    """The ladder setup writes (and the unreal example's) only matters on a step-up: every stage of every route and
    domain runs the model and effort it ran with no ladder."""
    def configs(self, d):
        tpl, wc = ROOT / "templates" / "team.toml", ROOT / "write_config.py"
        for preset in ("claude", "codex", "both"):
            dst = d / preset / "team.toml"
            dst.parent.mkdir()
            subprocess.run([sys.executable, "-I", str(wc), str(tpl), str(dst), "p", preset, "none"], check=True)
            # the shipped rules (hard-route ...) raise tiers on purpose; this checks the ladder alone
            dst.write_text(re.sub(r"\[\[heuristic\.rule\]\]\n(?:(?!\[).*\n)*", "", dst.read_text()))
            yield preset, dst
        dst = d / "unreal" / "team.toml"
        dst.parent.mkdir()
        shutil.copy(ROOT.parent / "examples" / "unreal-p4" / "team.toml", dst)
        yield "unreal", dst

    def plain(self, s, kind, agent, profile):
        a, role, burst = team._select_agent_role(s, kind, agent, profile)
        _, cli, model, effort = team.ROLES[role]
        cap = team.CFG["routing"]["usage"]["no_burst_effort"]
        return cli, model, cap[role] if not burst and role in cap else effort

    def test_default_assignments_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(team, "claude_low", return_value=False), \
                mock.patch.object(team, "usage_input", return_value=(None, "test")), \
                mock.patch.object(team, "burst_active", return_value=False):
            for name, path in self.configs(Path(tmp)):
                team.init(path)
                h = team.CFG["heuristic"]
                self.assertTrue(h, name)
                for route in team.ROUTES:
                    for domain in team.DOMAINS:
                        stages = [("route", "producer", "producer")] + [
                            (k, a, team.stage_profile(route, domain, i)) for i, (k, a) in enumerate(team.pipeline(route, domain))]
                        for kind, agent, profile in stages:
                            s = state(route=route, domain=domain, risk="high", size="large", launches=[])
                            a, role, burst, ctx = team._select_tiered(s, kind, agent, profile, h)
                            got = team._assignment(ctx, role, burst)[:3]
                            self.assertEqual(got, self.plain(s, kind, agent, profile), f"{name} {route}/{domain} {kind} {agent}")

    def test_a_step_above_the_profile_runs_the_tier_profile(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(team, "usage_input", return_value=(None, "test")):
            path = next(self.configs(Path(tmp)))[1]  # claude: the architect (opus high) sits on rank high by model
            team.init(path)
            s = state(route="complex", launches=[], stepped=[{"kind": "plan", "agent": "architect", "rank": 3, "rules": []}])
            a, role, burst, ctx = team._select_tiered(s, "plan", "architect", "architect", team.CFG["heuristic"])
            self.assertEqual((ctx["own"], ctx["rank"]), (2, 3))
            self.assertEqual(team._assignment(ctx, role, burst)[1:], ("claude-opus-5-5", "xhigh", "director"))


if __name__ == "__main__":
    unittest.main()
