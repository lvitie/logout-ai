"""Apex guard (role-less [routing.usage.scoped_limit]) and the user burst (burst_file, `team burst`). Run with python3 -I."""
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_heuristic import BASE, ROLES, TIERS, team, state  # noqa: E402

APEX_ROLES = ROLES + ('[roles.fable]\nname = "Apex"\ncli = "claude"\nmodel = "fb"\neffort = "high"\n'
                      '[roles.capex]\nname = "Apex (Codex)"\ncli = "codex"\nmodel = "c3"\neffort = "xhigh"\n')
USAGE = '''[routing.usage]
enabled = true
claude_fallback = { senior = "csenior" }
cheap_first = ["senior"]
burst_file = "burst_until"
[routing.usage.surplus_swap]
cmid = "mid"
[routing.usage.burst_swap]
csenior = "senior"
'''
GUARD = '[routing.usage.scoped_limit]\nlabel = "7d Fable"\nthreshold = 85.0\n'


class ApexGuard(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "tpl/agents").mkdir(parents=True)
        for p in (mock.patch.object(team, "usage_input", return_value=(None, "test")),
                  mock.patch.object(team, "claude_low", side_effect=lambda: team._usage["low"])):
            p.start()
            self.addCleanup(p.stop)

    def init(self, codex_apex=False, guard=GUARD):
        apex = 'apex = { claude = "fable"%s }\n' % (', codex = "capex"' if codex_apex else "")
        p = self.d / "team.toml"
        p.write_text(BASE % (USAGE + guard) + TIERS + apex + APEX_ROLES)
        team.init(p)
        team.RUNS.mkdir(parents=True, exist_ok=True)
        team.task_dir("t001").mkdir(parents=True, exist_ok=True)

    def usage(self, pct=0.0, low=False, mode="mixed", burst=False):
        team._usage.update(t=time.time(), ok_t=time.time(), fail=False, low=low, mode=mode,
                           scoped_pct=pct, scoped_high=pct >= 85.0)
        f = team.RUNS / "burst_until"
        f.unlink(missing_ok=True)
        if burst:
            f.write_text(f"{time.time() + 3600}\n")

    def at_apex(self, s=None):
        """(assignment, task) for an implement stage stepped up to the apex tier; assignment None = not launched."""
        s = s or state(launches=[], stepped=[{"kind": "implement", "agent": "mid", "rank": 3, "rules": ["severity major"]}])
        launched = []
        with mock.patch.object(team, "_run_agent_once", side_effect=lambda s_, k, a, r, b, ctx=None: (
                launched.append(team._assignment(ctx, r, b)) or ("out", "text"))):
            team.run_agent(s, "implement", "mid", "mid")
        return (launched[0] if launched else None), s

    def test_below_threshold_spends_apex(self):
        self.init()
        self.usage(pct=84.0)
        got, s = self.at_apex()
        self.assertEqual(got[:2], ("claude", "fb"))
        self.assertEqual(s["status"], "running")

    def test_guard_without_codex_apex_goes_to_the_user_and_approve_spends_it(self):
        self.init()
        self.usage(pct=85.0)
        got, s = self.at_apex()
        self.assertIsNone(got)
        self.assertEqual((s["status"], s["capped"]), ("escalated", "implement"))
        self.assertIn("7d Fable at 85% >= 85%", s["reason"])
        with mock.patch.object(team, "load", return_value=s), mock.patch.object(team, "advance"):
            team.cmd_approve(SimpleNamespace(id="t001", note=""))
        self.assertTrue(s["apex_approved"])
        self.assertEqual([e["rank"] for e in s["stepped"]], [3])  # retried at apex
        s["status"] = "running"
        got, s = self.at_apex(s)
        self.assertEqual(got[:2], ("claude", "fb"))
        with mock.patch.object(team, "load", return_value=s), mock.patch.object(team, "advance"):
            team.cmd_redo(SimpleNamespace(id="t001", note="start over"))
        self.assertNotIn("apex_approved", s)  # the guard applies again after a redo

    def test_guard_with_codex_apex_runs_the_codex_profile(self):
        self.init(codex_apex=True)
        self.usage(pct=90.0)
        got, s = self.at_apex()
        self.assertEqual(got, ("codex", "c3", "xhigh", "capex"))
        self.assertEqual(s["status"], "running")

    def test_burst_lifts_the_guard_but_not_the_claude_limits(self):
        self.init()
        self.usage(pct=99.0, burst=True)
        self.assertEqual(self.at_apex()[0][:2], ("claude", "fb"))
        self.usage(pct=10.0, low=True, burst=True)  # 5h/7d limits reached: still guarded
        got, s = self.at_apex()
        self.assertIsNone(got)
        self.assertIn("Claude usage low", s["reason"])

    def test_guard_is_config_gated(self):
        self.init(guard="")
        self.usage(pct=99.0)
        self.assertEqual(self.at_apex()[0][:2], ("claude", "fb"))
        with self.assertRaisesRegex(ValueError, "guards the apex tier"):
            p = self.d / "team.toml"
            p.write_text(BASE % (USAGE + GUARD) + TIERS + APEX_ROLES)
            team.teamcfg.load(p)
        with self.assertRaisesRegex(ValueError, "needs label"):
            self.init(guard='[routing.usage.scoped_limit]\nthreshold = 85.0\n')

    def test_burst_moves_codex_roles_to_claude_and_skips_cheap_first(self):
        self.init()
        h = lambda s: team.ladder(s, "implement")  # noqa: E731
        for burst, cmid, senior in ((False, "cmid", "csenior"), (True, "mid", "senior")):
            self.usage(mode="mixed", burst=burst)
            s = state(launches=[])
            self.assertEqual(team._select_tiered(s, "implement", "mid", "cmid", h(s))[1], cmid, burst)
            s = state(launches=[])
            self.assertEqual(team._select_tiered(s, "implement", "senior", "senior", h(s))[1], senior, burst)
            s = state(launches=[])
            self.assertEqual(team._select_tiered(s, "implement", "senior", "csenior", h(s))[1], senior, burst)

    def test_team_burst_writes_the_deadline_and_status_shows_it(self):
        self.init()
        self.usage()
        with redirect_stdout(StringIO()):
            team.cmd_burst(SimpleNamespace(hours=2))
        self.assertTrue(team.burst_active())
        self.assertAlmostEqual(float((team.RUNS / "burst_until").read_text()), time.time() + 7200, delta=5)
        out = StringIO()
        with redirect_stdout(out):
            team.cmd_status(SimpleNamespace(metrics=False, id=None, reverse=False))
        self.assertIn("burst: active until", out.getvalue())
        with redirect_stdout(StringIO()):
            team.cmd_burst(SimpleNamespace(hours=0))
        self.assertFalse(team.burst_active())
        self.assertEqual(team.burst_line(), "")


if __name__ == "__main__":
    unittest.main()
