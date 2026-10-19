#!/usr/bin/env python3
"""Unit tests for the Claude/Codex route_mode math and usage_tui's codex reset reader (ported from the source project).
Runs entirely in a tempdir: team.RUNS/HIST/MODE/ROUTE_LOCK are redirected and team.live is stubbed.
Paces: scenarios 1-3, 5, 6 inject the stated base pace (Claude 0.875, Codex 1.26 %/h), scenario 2 Claude 0.44,
scenario 4 uses the real fallback pace (used / max(24, 168 - left)), scenario 7 the 0.2 floor (Claude runway 783h,
q=3.93; the design table's 846h skipped the floor, decision unchanged)."""
import importlib.machinery, importlib.util, json, os, stat, sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent.parent
_TMP = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = os.path.join(_TMP, "state")  # usage_tui/team import create the journal dir
os.environ["XDG_CACHE_HOME"] = os.path.join(_TMP, "cache")
os.environ["CODEX_HOME"] = os.path.join(_TMP, "codex")


def load(name, path):
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, str(path)))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


team = load("team_under_test", HERE / "team.py")
usage = load("usage_tui_under_test", HERE / "usage_tui")

BASE = {"5h": 28, "7d": 21, "7d_resets_in_h": 144.6, "codex_7d": 50, "codex_7d_resets_in_h": 141, "codex_reset_exp_h": [155, 321, 518]}


class Route(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        team.RUNS, team.HIST, team.MODE, team.ROUTE_LOCK = d, d / "usage_hist.jsonl", d / "route_mode.json", d / ".lock-route"
        self.logs = []
        team.live = self.logs.append
        self.real_pace = type(team.pace)(team.pace.__code__, team.pace.__globals__)

    def tearDown(self):
        team.pace = self.real_pace
        self.tmp.cleanup()

    def run_case(self, over, p_c=None, p_x=None, prev=None):
        if prev:
            team.MODE.write_text(json.dumps({"mode": prev}))
        if p_c is not None:
            team.pace = lambda key, used, left: p_c if key == "c7" else p_x
        u = dict(BASE, **over)
        mode = team.route_mode(u)
        info = json.loads(team.MODE.read_text())
        return mode, info

    def check(self, over, p_c, p_x, mode, q, prev=None):
        m, info = self.run_case(over, p_c, p_x, prev)
        self.assertEqual(m, mode)
        self.assertAlmostEqual(info["q"], q, delta=0.011)

    def test_1_today(self): self.check({}, 0.875, 1.26, "codex", 0.50)
    def test_2_claude_slow(self): self.check({}, 0.44, 1.26, "mixed", 1.00)
    def test_3_codex_95(self): self.check({"codex_7d": 95}, 0.875, 1.26, "claude", 0.61)
    def test_4_fallback_pace(self):
        m, info = self.run_case({"7d": 80, "7d_resets_in_h": 72, "codex_7d": 20, "codex_7d_resets_in_h": 72, "codex_reset_exp_h": []})
        self.assertEqual(m, "codex"); self.assertAlmostEqual(info["q"], 0.13, delta=0.01)
        self.assertAlmostEqual(info["p_c"], 80 / 96, places=2); self.assertAlmostEqual(info["p_x"], 20 / 96, places=2)
    def test_5_reset_10h_50(self): self.check({"codex_reset_exp_h": [10, 321, 518]}, 0.875, 1.26, "mixed", 0.83)
    def test_6_reset_10h_85(self): self.check({"codex_7d": 85, "codex_reset_exp_h": [10, 321, 518]}, 0.875, 1.26, "codex", 0.58)
    def test_7_claude_resets_6h(self):
        m, info = self.run_case({"7d": 30, "7d_resets_in_h": 6}, 0.2, 1.26)
        self.assertEqual(m, "claude"); self.assertAlmostEqual(info["q"], 3.93, delta=0.02)

    def test_hysteresis(self):
        # q ~0.8: enter codex needs < 0.70, stay codex up to 0.87
        over, p_c = {"codex_reset_exp_h": [10, 321, 518]}, 0.875  # scenario 5, q=0.83
        self.assertEqual(self.run_case(over, p_c, 1.26, prev="mixed")[0], "mixed")
        self.assertEqual(self.run_case(over, p_c, 1.26, prev="codex")[0], "codex")
        # q ~1.3: claude needs > 1.43 to enter, > 1.15 to stay
        over = {"codex_reset_exp_h": []}
        m, info = self.run_case(over, 1.3, 1.26, prev="mixed"); q = info["q"]
        self.assertTrue(1.15 < q < 1.43, q); self.assertEqual(m, "mixed")
        self.assertEqual(self.run_case(over, 1.3, 1.26, prev="claude")[0], "claude")

    def test_guards(self):
        self.assertEqual(self.run_case({"codex_7d": 95, "5h": 75}, 0.875, 1.26)[0], "mixed")   # claude 5h >= 70
        self.assertEqual(self.run_case({"codex_7d": 95, "7d": 91}, 0.875, 1.26)[0], "mixed")   # claude 7d >= 90

    def test_missing_keys_keep_prev_and_no_row(self):
        team.MODE.write_text(json.dumps({"mode": "codex"}))
        for drop in ("7d", "codex_7d", "codex_reset_exp_h"):
            u = {k: v for k, v in BASE.items() if k != drop}
            self.assertEqual(team.route_mode(u), "codex")
        self.assertFalse(team.HIST.exists())
        self.assertEqual(json.loads(team.MODE.read_text())["mode"], "codex")

    def test_zero_runway(self):
        u = {"5h": 10, "7d": 10, "7d_resets_in_h": 100, "codex_7d": 100, "codex_7d_resets_in_h": 168, "codex_reset_exp_h": []}
        self.assertEqual(team.route_mode(u), "claude")  # s_x = 0: no ZeroDivisionError, claude path
        u = dict(u, **{"7d": 99, "codex_7d": 10})
        self.assertEqual(team.route_mode(u), "codex")   # s_c < 0: codex path
        self.assertEqual(team.route_mode(dict(u, **{"7d": 99, "codex_7d": 100})), "mixed")  # both 0: q=1

    def test_expired_exp_ignored(self):
        a = self.run_case({"codex_reset_exp_h": [-5, 0, 155, 321, 518]}, 0.875, 1.26)
        self.assertEqual((a[0], a[1]["usable"]), ("codex", 3))

    def test_flip_logged_once(self):
        self.run_case({}, 0.875, 1.26, prev="mixed")
        self.assertEqual(len(self.logs), 1); self.assertIn("mixed -> codex", self.logs[0])
        team.route_mode(dict(BASE))
        self.assertEqual(len(self.logs), 1)  # file mode unchanged: no duplicate flip line

    def test_history_append_prune_malformed(self):
        now = time.time()
        team.HIST.write_text("garbage\n" + json.dumps({"t": now - 80 * 3600, "c7": 1, "x7": 1}) + "\n"
                             + json.dumps({"t": now - 3600, "c7": 5}) + "\n" + json.dumps({"t": now - 3600, "c7": 5, "x7": 6}) + "\n[1]\n")
        team.route_mode(dict(BASE))
        rows = [json.loads(l) for l in team.HIST.read_text().splitlines()]
        self.assertEqual(len(rows), 2)  # old row pruned, bad lines dropped, one new row appended
        self.assertEqual((rows[-1]["c7"], rows[-1]["x7"]), (21, 50))

    def push(self, target=95, until=None):
        from datetime import datetime, timezone
        if until is None:
            until = datetime.fromtimestamp(time.time() + 3600, timezone.utc).isoformat()
        (team.RUNS / "codex_push.json").write_text(json.dumps({"target": target, "until": until}))

    def test_push_on_off_expiry_and_malformed(self):
        self.assertEqual(self.run_case({"codex_7d": 93}, 0.875, 1.26)[0], "claude")
        self.push()
        self.assertEqual(self.run_case({"codex_7d": 93}, 0.875, 1.26)[0], "codex")
        self.push(until="2000-01-01T00:00:00Z")
        self.assertEqual(self.run_case({"codex_7d": 93}, 0.875, 1.26)[0], "claude")
        for target, until in ((True, None), (101, None), (0, None), (float("nan"), None),
                              ("95", None), (95, "tomorrow"), (95, "2099-01-01T00:00:00")):
            self.push(target, until)
            self.assertEqual(self.run_case({"codex_7d": 93}, 0.875, 1.26)[0], "claude")
        for value in ("[1]", "{}", "null", "broken"):
            (team.RUNS / "codex_push.json").write_text(value)
            self.assertEqual(self.run_case({"codex_7d": 93}, 0.875, 1.26)[0], "claude")

    def test_push_guard_and_target(self):
        self.push(97)
        self.assertEqual(self.run_case({"codex_7d": 96.9}, 0.875, 1.26)[0], "codex")
        self.assertEqual(self.run_case({"codex_7d": 97}, 0.875, 1.26)[0], "claude")
        self.assertEqual(self.run_case({"codex_7d": 98}, 0.875, 1.26)[0], "claude")
        self.assertEqual(self.logs.count("Codex push target reached"), 1)
        # Claude low keeps the existing mixed-mode guard, including at target+1.
        for over in ({"5h": 70}, {"7d": 90}, {"7d": 99}):
            for pct in (97, 98):
                self.assertEqual(self.run_case(dict(over, codex_7d=pct), 0.875, 1.26)[0], "mixed")
        self.push()
        self.assertEqual(self.run_case({"codex_7d": 94.9}, 0.875, 1.26)[0], "codex")
        self.assertEqual(self.run_case({"codex_7d": 95}, 0.875, 1.26)[0], "claude")

    def test_push_does_not_force_codex_when_claude_low(self):
        self.push()
        for over in ({"5h": 70}, {"7d": 90}):
            self.assertNotEqual(self.run_case(dict(over, codex_7d=94), 0.1, 10)[0], "claude")
        self.assertEqual(self.run_case({"codex_7d": 93, "5h": 70}, 0.1, 10)[0], "mixed")


    def test_pace_measured(self):
        now = time.time()
        rows = [{"t": now - 48 * 3600 + i * 3600, "c7": (i * 1.0) % 30 if i < 20 else i - 20, "x7": 2.0 * i} for i in range(0, 48)]
        team.HIST.write_text("".join(json.dumps(r) + "\n" for r in rows))
        p = self.real_pace("x7", 90, 100)
        self.assertAlmostEqual(p, 2.0 * 47 / 47.0, delta=0.1)   # measured, not the used/elapsed fallback
        self.assertGreaterEqual(self.real_pace("c7", 0, 168), 0.2)


class CodexReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name) / "bin"; self.bin.mkdir()
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{self.bin}:{self.old_path}"
        self.pidfile = Path(self.tmp.name) / "pid"
        usage.CX_CACHE = f"{self.tmp.name}/cx.json"
        usage.MANUAL_RESETS = f"{self.tmp.name}/none.txt"

    def tearDown(self):
        os.environ["PATH"] = self.old_path
        self.tmp.cleanup()

    def fake(self, body):
        f = self.bin / "codex"
        f.write_text("#!/usr/bin/env python3\nimport os,sys,json,time\nopen(%r,'w').write(str(os.getpid()))\n%s\n" % (str(self.pidfile), body))
        f.chmod(0o755)

    GOOD = """
sys.stdin.readline(); sys.stdout.write(json.dumps({"id":1,"result":{}})+"\\n"); sys.stdout.flush()
sys.stdin.readline(); sys.stdin.readline()
t=time.time()
sys.stdout.write(json.dumps({"id":2,"result":{"rateLimitResetCredits":{"availableCount":2,"credits":[{"status":"available","expiresAt":int((t+3600*100)*1000)},{"status":"available","expiresAt":int(t+3600*200)},{"status":"used","expiresAt":int(t+3600)}]}}}))
sys.stdout.flush(); time.sleep(0.2); sys.stdout.write("\\n"); sys.stdout.flush(); time.sleep(30)"""

    def alive(self):
        try:
            pid = int(self.pidfile.read_text()); os.kill(pid, 0); return True
        except (OSError, ValueError):
            return False

    def test_partial_line_ms_and_reap(self):
        self.fake(self.GOOD)
        n, how, exp = usage.codex_resets(time.monotonic() + 20)
        self.assertEqual(n, 2); self.assertEqual(how.split(",")[0], "live")
        self.assertAlmostEqual(exp[0], 100, delta=0.2); self.assertAlmostEqual(exp[1], 200, delta=0.2)  # ms normalised, "used" skipped
        self.assertTrue(all(0 < h < 10000 for h in exp))
        time.sleep(0.3); self.assertFalse(self.alive())  # child killed and reaped
        self.fake("raise SystemExit(7)")  # warm cache: no new spawn
        self.assertEqual(usage.codex_resets()[0:2][1].split(",")[0], "cached")

    def test_stalled_child_serves_manual_then_stale(self):
        self.fake("import time; time.sleep(60)")
        Path(usage.MANUAL_RESETS).write_text("3\n")
        t0 = time.monotonic()
        n, how, exp = usage.codex_resets(time.monotonic() + 2)
        self.assertLess(time.monotonic() - t0, 6)
        self.assertEqual((n, how, exp), (3, "manual file", [336, 336, 336]))
        time.sleep(0.3); self.assertFalse(self.alive())
        Path(usage.CX_CACHE + ".fail").unlink()
        Path(usage.CX_CACHE).write_text(json.dumps({"t": time.time() - 9999, "n": 1, "exp": [time.time() + 3600 * 50], "raw_expiresAt": []}))
        n, how, exp = usage.codex_resets(time.monotonic() + 2)
        self.assertEqual(n, 1); self.assertTrue(how.startswith("stale cache")); self.assertAlmostEqual(exp[0], 50, delta=0.2)

    def test_no_data(self):
        self.fake("raise SystemExit(1)")
        self.assertEqual(usage.codex_resets(time.monotonic() + 2), (None, "", None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
