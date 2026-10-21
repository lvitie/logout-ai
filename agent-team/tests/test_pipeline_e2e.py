"""End-to-end pipeline runs through `advance` with a scripted fake claude: happy path, gate and approve, minor-round
escalation, redo and drop, approve while queued, a stage killed mid-run then resumed, and resumed agent sessions.
Run with python3 -I."""
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
from team import RESUME_LINE  # noqa: E402


ROUTE = "Spec.\nTITLE: thing\nROUTE: complex\nDOMAIN: gameplay\nRISK: low\nSIZE: small\n"
DONE, PASS = "Did it.\nSTATUS: DONE\n", "Fine.\nVERDICT: PASS\n"
FIXED = "Fixed the nit.\nSTATUS: DONE\n"
MINOR = "Nit.\nSEVERITY: minor\nVERDICT: FAIL\n"
HAPPY = [ROUTE, DONE, PASS, DONE, PASS]  # route, plan, plan_review, implement, review


class EndToEnd(unittest.TestCase):
    """A temp git project whose fake claude answers each launch with the next scripted reply (rN files) and saves
    that launch's argv (argsN, one per line) and prompt (inN)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        t = Path(tmp.name)
        self.home, self.proj, self.fake, self.replies = t / "home", t / "proj", t / "fakebin", t / "replies"
        for d in (self.home, self.proj, self.fake, self.replies):
            d.mkdir()
        r = self.replies
        (self.fake / "claude").write_text(
            f"#!/bin/sh\nn=$(($(cat {r}/count 2>/dev/null || echo 0) + 1)); echo $n > {r}/count\n"
            f"cat > {r}/in$n\nprintf '%s\\n' \"$@\" > {r}/args$n\n[ -f {r}/r$n.fail ] && exit 1\n"
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
        """Queue the next fake claude replies; hang: the first of them sleeps until killed instead. A None reply
        fails at once with no output (a CLI that cannot resume the session)."""
        for i, text in enumerate(texts):
            self.n += 1
            if text is None:
                (self.replies / f"r{self.n}.fail").touch()
                continue
            (self.replies / f"r{self.n}").write_text(json.dumps({"type": "result", "result": text}) + "\n")
            if hang and i == 0:
                (self.replies / f"r{self.n}.hang").touch()

    def call(self, n):
        """(argv, prompt) of fake claude launch n."""
        return (self.replies / f"args{n}").read_text().splitlines(), (self.replies / f"in{n}").read_text()

    def session(self, n):
        """('--session-id' or '--resume', id) of launch n."""
        args = self.call(n)[0]
        flag = next(a for a in args if a in ("--session-id", "--resume"))
        return flag, args[args.index(flag) + 1]

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
        self.assertNotIn("learn", " ".join(x["stem"] for x in s["launches"]))  # nothing went wrong: no learn stage
        self.assertEqual(list((self.proj / ".agent-team/t001/logs").glob("*.jsonl")), [])  # tidied at done
        self.assertEqual(len(s["runs"]), 5)
        out = self.team("status")
        self.assertIn("t001  done", out)
        self.assertIn("end", out)
        self.assertIn("5 ", self.team("tokens", "t001"))

    def test_learnings_reach_the_next_task(self):
        self.script(ROUTE, DONE, PASS, DONE, MINOR, FIXED, PASS, "Notes.\n- Run the linter before the review.\n")
        self.team("new", "picky")
        self.assertEqual(self.call(8)[0][self.call(8)[0].index("--tools") + 1], "Read,Glob,Grep")
        self.assertIn("## How it went", self.call(8)[1])
        learned = (self.proj / ".agent-team/learnings.md").read_text()
        self.assertEqual(learned, "- Run the linter before the review.\n")
        self.script(ROUTE, "STATUS: GATE stop\n")
        self.team("new", "next")
        self.assertIn("## Learnings from earlier tasks\n- Run the linter before the review.", self.call(9)[1])
        self.assertIn("Run the linter", self.call(10)[1])
        self.script("UNCHANGED\n")
        self.team("drop", "t002")
        self.assertEqual(self.state("t002")["status"], "dropped")  # drop tidies, it does not learn
        self.assertEqual(list((self.proj / ".agent-team/t002/logs").glob("*.jsonl")), [])
        self.assertEqual((self.proj / ".agent-team/learnings.md").read_text(), learned)

    def test_tidy_command(self):
        self.script(*HAPPY)
        self.team("new", "old task")
        logs = self.proj / ".agent-team/t001/logs"
        (logs / "05-review-qa.jsonl").write_text('{"type": "result", "usage": {"input_tokens": 9}}\n')  # from before tidy
        (logs / "05-review-qa.prompt.md").write_text("x" * 100)
        self.assertIn("tidied 1 tasks", self.team("tidy"))
        self.assertEqual(sorted(p.name for p in logs.iterdir()), [])
        row = next(r for r in self.state()["runs"] if r["stem"] == "05-review-qa")
        self.assertEqual((row["fresh"], row["prompt_chars"]), (9, 100))

    def test_gate_then_approve_from_another_process(self):
        self.script(ROUTE, "Which one?\nSTATUS: GATE pick A or B\n")
        self.team("new", "gated")
        s = self.state()
        self.assertEqual((s["status"], s["stage"]), ("gate", 0))
        self.script(DONE, PASS, DONE, PASS)
        self.team("approve", "t001", "use A")
        s = self.state()
        self.assertEqual((s["status"], s["n"]), ("done", 7))  # 7: the learn stage (a note), unscripted: it fails
        self.assertEqual(s["launches"][-1]["stem"], "07-learn-producer")  # and the task stays done
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
        self.assertEqual((s["status"], s["review_rounds"], s["n"], s["impl_fails"]), ("done", 0, 12, 3))  # 12: learn
        self.assertNotIn("minor_rounds", s)

    def test_redo_done_task_and_drop_gated_task(self):
        self.script(*HAPPY)
        self.team("new", "first")
        self.script(DONE, PASS)
        self.team("redo", "t001", "also do B")
        s = self.state()
        self.assertEqual((s["status"], s["n"]), ("done", 8))  # 8: learn after the redo note
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

    def test_retry_and_re_review_resume_their_sessions(self):
        self.script(ROUTE, DONE, PASS, DONE, MINOR, FIXED, PASS)  # 4 implement, 5 review, 6 retry, 7 re-review
        self.team("new", "picky once")
        s = self.state()
        self.assertEqual((s["status"], s["n"]), ("done", 8))  # 8: learn
        impl, rev = self.session(4), self.session(5)
        self.assertEqual([impl[0], rev[0]], ["--session-id", "--session-id"])
        self.assertEqual(self.session(6), ("--resume", impl[1]))
        self.assertEqual(self.session(7), ("--resume", rev[1]))
        retry, rereview = self.call(6)[1], self.call(7)[1]
        for text in (retry, rereview):
            self.assertTrue(text.startswith(RESUME_LINE))
            self.assertNotIn("## Request", text)
            self.assertIn("## Job", text)
        self.assertIn("Nit.", retry)  # the new findings
        self.assertNotIn("Did it.", retry)  # its own report is in its context
        self.assertIn("Fixed the nit.", rereview)  # the new report; its own findings are already in its context
        self.assertNotIn("## Earlier findings", rereview)
        self.assertIn("## Request", self.call(4)[1])
        self.assertEqual([x["resumed"] for x in s["launches"][3:7]], [False, False, True, True])
        self.assertNotIn("sessions", s)  # done: a redo starts new sessions

    def test_gate_resumes_unless_the_model_changed(self):
        self.script(ROUTE, "STATUS: GATE pick\n", "STATUS: GATE again\n")
        self.team("new", "gated")
        self.team("approve", "t001", "use A")
        self.assertEqual(self.session(3), ("--resume", self.session(2)[1]))
        self.assertIn("use A", self.call(3)[1])
        s = self.state()
        (key,) = s["sessions"]
        s["sessions"][key]["model"] = "an-older-model"  # as after an escalation to another tier
        (self.proj / ".agent-team/t001/state.json").write_text(json.dumps(s))
        self.script(DONE, PASS, DONE, PASS)
        self.team("approve", "t001", "go")
        self.assertEqual(self.session(4)[0], "--session-id")
        self.assertIn("## Request", self.call(4)[1])
        self.assertEqual(self.state()["status"], "done")

    def test_refused_resume_falls_back_to_a_fresh_session(self):
        self.script(ROUTE, DONE, PASS, DONE, MINOR, None, FIXED, PASS)  # 6: the resumed retry fails at startup
        self.team("new", "pruned session")
        s = self.state()
        self.assertEqual(s["status"], "done")
        self.assertEqual(self.session(6)[0], "--resume")
        self.assertEqual(self.session(7)[0], "--session-id")
        self.assertIn("## Request", self.call(7)[1])
        self.assertEqual(self.session(8), ("--resume", self.session(5)[1]))
        self.assertIn("resume failed, fresh session", (self.proj / ".agent-team/live.log").read_text())


if __name__ == "__main__":
    unittest.main()
