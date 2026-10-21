"""End-to-end pipeline runs through `advance` with a scripted fake claude: happy path, gate and approve, minor-round
escalation, redo and drop, approve while queued, and a stage killed mid-run then resumed. Run with python3 -I."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import teamcfg  # noqa: E402
from cfgutil import TOML  # noqa: E402


ROUTE = "Spec.\nTITLE: thing\nROUTE: complex\nDOMAIN: gameplay\nRISK: low\nSIZE: small\n"
DONE, PASS = "Did it.\nSTATUS: DONE\n", "Fine.\nVERDICT: PASS\n"
MINOR = "Nit.\nSEVERITY: minor\nVERDICT: FAIL\n"
HAPPY = [ROUTE, DONE, PASS, DONE, PASS]  # route, plan, plan_review, implement, review


class EndToEnd(unittest.TestCase):
    """A temp git project whose fake claude answers each launch with the next scripted reply (rN files)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        t = Path(tmp.name)
        self.home, self.proj, self.fake, self.replies = t / "home", t / "proj", t / "fakebin", t / "replies"
        for d in (self.home, self.proj, self.fake, self.replies):
            d.mkdir()
        r = self.replies
        (self.fake / "claude").write_text(
            f"#!/bin/sh\ncat >/dev/null\nn=$(($(cat {r}/count 2>/dev/null || echo 0) + 1)); echo $n > {r}/count\n"
            f"[ -f {r}/r$n.hang ] && echo $$ > {r}/pid && exec sleep 300\ncat {r}/r$n 2>/dev/null || exit 99\n")
        (self.fake / "codex").write_text("#!/bin/sh\nexit 99\n")
        for name in ("claude", "codex"):
            (self.fake / name).chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("TEAM_", "CODEX_", "CLAUDE_", "XDG_"))}
        self.env.update(HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                        PATH=f"{self.fake}:{os.environ['PATH']}", TEAM_CONFIG=str(self.proj / "team.toml"),
                        XDG_STATE_HOME=str(t / "state"), XDG_CACHE_HOME=str(t / "cache"), CODEX_HOME=str(t / "codex"))
        for a in (("init", "-q"), ("config", "user.email", "t@example.com"), ("config", "user.name", "t")):
            self.git(*a)
        (self.proj / "team.toml").write_text(
            TOML.replace('name = "myproject"', 'name = "demo"').replace("refill = true", "refill = false"))
        (self.proj / "README.md").write_text("hello\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        self.n = 0

    def git(self, *a):
        subprocess.run(["git", *a], cwd=self.proj, env=self.env, capture_output=True, text=True, check=True)

    def script(self, *texts, hang=False):
        """Queue the next fake claude replies; hang: the first of them sleeps until killed instead."""
        for i, text in enumerate(texts):
            self.n += 1
            (self.replies / f"r{self.n}").write_text(json.dumps({"type": "result", "result": text}) + "\n")
            if hang and i == 0:
                (self.replies / f"r{self.n}.hang").touch()

    def team(self, *a):
        r = subprocess.run([sys.executable, "-I", str(ROOT / "team.py"), *a], cwd=self.proj, env=self.env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def state(self, tid="t001"):
        return json.loads((self.proj / f".agent-team/{tid}/state.json").read_text())

    def summary(self, s):
        return {k: s.get(k) for k in ("status", "route", "stage", "plan_rounds", "review_rounds", "n", "first_pass",
                                      "review_rounds_total", "escalations")} | {"history": len(s["history"])}

    def test_happy_path(self):
        self.script(*HAPPY)
        self.team("new", "add a thing")
        s = self.state()
        self.assertEqual(self.summary(s), {"status": "done", "route": "complex", "stage": 4, "plan_rounds": 0,
                                           "review_rounds": 0, "n": 5, "first_pass": True, "review_rounds_total": 1,
                                           "escalations": None, "history": 5})
        self.assertIsNotNone(s["first_finish"])
        out = self.team("status")
        self.assertIn("t001  done", out)
        self.assertIn("end", out)
        self.team("tokens", "t001")

    def test_gate_then_approve_from_another_process(self):
        self.script(ROUTE, "Which one?\nSTATUS: GATE pick A or B\n")
        self.team("new", "gated")
        s = self.state()
        self.assertEqual((s["status"], s["stage"]), ("gate", 0))
        self.script(DONE, PASS, DONE, PASS)
        self.team("approve", "t001", "use A")
        s = self.state()
        self.assertEqual((s["status"], s["n"]), ("done", 6))
        self.assertIn("Approved (gameplay: pick A or B): use A", s["notes"])

    def test_minor_rounds_escalate_then_approve_retries_implement(self):
        self.script(ROUTE, DONE, PASS, DONE, MINOR, DONE, MINOR, DONE, MINOR)
        self.team("new", "picky")
        s = self.state()
        self.assertEqual((s["status"], s["review_rounds"], s["escalations"]), ("escalated", 3, 1))
        self.assertIn("implement failed review 3 times (minor)", s["reason"])
        self.script(DONE, PASS)
        self.team("approve", "t001")
        s = self.state()
        self.assertEqual((s["status"], s["review_rounds"], s["n"], s["impl_fails"]), ("done", 0, 11, 3))
        self.assertNotIn("minor_rounds", s)

    def test_redo_done_task_and_drop_gated_task(self):
        self.script(*HAPPY)
        self.team("new", "first")
        self.script(DONE, PASS)
        self.team("redo", "t001", "also do B")
        s = self.state()
        self.assertEqual((s["status"], s["n"]), ("done", 7))
        self.assertIn("also do B", s["notes"])
        self.script(ROUTE, "STATUS: GATE stop here\n")
        self.team("new", "second")
        self.team("drop", "t002", "not needed")
        self.assertEqual(self.state("t002")["status"], "dropped")
        self.assertIn("t002  dropped", self.team("status"))

    def test_approve_while_queued_keeps_the_decision(self):
        self.script(ROUTE, "STATUS: GATE pick\n")
        self.team("new", "gated")
        with (self.proj / ".agent-team/.lock-slot0").open("a") as a, (self.proj / ".agent-team/.lock-slot1").open("a") as b, \
                (self.proj / ".agent-team/.lock-slot2").open("a") as c:
            for f in (a, b, c):
                teamcfg.lock(f, blocking=False)  # every slot busy: the approve is queued
            self.team("approve", "t001", "queued call")
            s = self.state()
            self.assertEqual((s["status"], s.get("queued")), ("new", True))
        self.script(DONE, PASS, DONE, PASS)
        self.team("run", "t001", "--queued")
        s = self.state()
        self.assertEqual(s["status"], "done")
        self.assertIn("Approved (gameplay: pick): queued call", s["notes"])

    def test_killed_stage_reruns_on_resume(self):
        self.script(ROUTE, DONE)
        self.script("unused", hang=True)  # plan_review hangs
        run = subprocess.Popen([sys.executable, "-I", str(ROOT / "team.py"), "new", "slow"], cwd=self.proj, env=self.env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(run.kill)
        deadline = time.time() + 30
        while not (self.replies / "pid").exists():
            self.assertLess(time.time(), deadline, "the plan review never started")
            time.sleep(0.1)
        run.terminate()
        run.wait(timeout=20)
        s = self.state()
        self.assertEqual((s["status"], s["stage"]), ("running", 1))  # reported as stale by `team wait`
        self.assertEqual(s["launches"][-1]["stem"].split("-")[1], "plan_review")  # saved before the agent started
        self.script(PASS, DONE, PASS)
        self.team("run", "t001")
        s = self.state()
        self.assertEqual((s["status"], s["stage"]), ("done", 4))
        self.assertEqual(len(s["history"]), 5)


if __name__ == "__main__":
    unittest.main()
