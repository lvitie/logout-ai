"""Smoke tests: temp git project, config load, task creation, status, VCS guard, adapters, shared journal, review page.
No network and no real agents: HOME/XDG/GIT_CONFIG_GLOBAL are redirected, probes are empty, and fake claude/codex
binaries that exit 99 sit first on PATH so any agent spawn fails loudly. Run with python3 -I."""
import html
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
import teamcfg  # noqa: E402
import vcs  # noqa: E402

from cfgutil import TOML  # noqa: E402


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.home, self.proj, fake = t / "home", t / "proj", t / "fakebin"
        for d in (self.home, self.proj, fake):
            d.mkdir()
        self.fake = fake
        for name in ("claude", "codex"):
            (fake / name).write_text("#!/bin/sh\necho fake %s >&2\nexit 99\n" % name)
            (fake / name).chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("TEAM_", "CODEX_", "CLAUDE_", "XDG_"))}
        self.env.update(HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                        PATH=f"{fake}:{os.environ['PATH']}", TEAM_CONFIG=str(self.proj / "team.toml"),
                        XDG_STATE_HOME=str(t / "state"), XDG_CACHE_HOME=str(t / "cache"), CODEX_HOME=str(t / "codex"))
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        (self.proj / "team.toml").write_text(TOML.replace('name = "myproject"', 'name = "demo"')
                                             .replace("refill = true", "refill = false"))  # refill tests opt in
        (self.proj / "README.md").write_text("hello\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.proj, env=self.env, capture_output=True, text=True, check=True).stdout

    def team(self, *a, ok=True):
        r = subprocess.run([sys.executable, "-I", str(ROOT / "team.py"), *a], cwd=self.proj, env=self.env,
                           capture_output=True, text=True, timeout=60)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_config_loader(self):
        cfg = teamcfg.load(self.proj / "team.toml")
        self.assertEqual(cfg["project"]["name"], "demo")
        self.assertEqual(cfg["state"], (self.proj / ".agent-team").resolve())
        self.assertEqual(set(teamcfg.CANONICAL_ROLES) - set(cfg["roles"]), set())
        bad = TOML.replace("[roles.director]", "[roles.other]")
        (self.proj / "bad.toml").write_text(bad)
        with self.assertRaisesRegex(ValueError, "director"):
            teamcfg.load(self.proj / "bad.toml")
        (self.proj / "typo.toml").write_text(TOML.replace("# fails = 3", "fails = 0"))
        with self.assertRaisesRegex(ValueError, "after_impl_fails.*fails"):
            teamcfg.load(self.proj / "typo.toml")

    def test_config_flag_beats_env(self):
        alt = self.proj / "alt"
        alt.mkdir()
        (alt / "team.toml").write_text(TOML.replace('name = "myproject"', 'name = "alt"').replace('root = "."', 'root = ".."'))
        self.env["TEAM_CONFIG"] = str(self.proj / "missing.toml")
        self.team("--config", str(alt / "team.toml"), "new", "--no-run", "via flag")
        self.assertIn("via flag", self.team("--config", str(alt / "team.toml"), "status", "t001").stdout)

    def test_new_status_and_failed_run(self):
        r = self.team("new", "--no-run", "add a thing\nmore detail")
        self.assertIn("t001", r.stdout)
        state = json.loads((self.proj / ".agent-team/t001/state.json").read_text())
        self.assertEqual((state["change"], state["status"], state["res"]), ("t001", "new", ["editor"]))
        listing = self.team("status").stdout
        self.assertIn("t001", listing)
        self.assertIn("chg:t001", listing)
        self.assertIn("add a thing", self.team("status", "t001").stdout)
        # running it spawns the fake claude (Producer), which exits 99: the task must fail loudly, not hang
        self.team("run", "t001")
        state = json.loads((self.proj / ".agent-team/t001/state.json").read_text())
        self.assertEqual(state["status"], "failed")
        self.assertIn("exited 99", state["reason"])
        prompt = (self.proj / ".agent-team/t001/logs/01-route-producer.prompt.md").read_text()
        self.assertIn("working-tree changes t001", prompt)
        self.assertIn("simple|complex|hard|ask", prompt)
        self.assertIn("DOMAIN: gameplay|engine|tools|technical_art|audio|design|build", prompt)
        self.assertIn("- technical_art: technical art", prompt)
        self.assertNotIn("{", prompt.split("## Job")[1])
        self.assertTrue((self.proj / ".agent-team/guard-bin/git").is_symlink())

    def test_status_skips_folders_without_state(self):
        self.team("new", "--no-run", "real task")
        (self.proj / ".agent-team/t050").mkdir()  # e.g. a hand-off folder synced from the depot
        (self.proj / ".agent-team/t051").mkdir()
        (self.proj / ".agent-team/t051/state.json").write_text("{not json")
        listing = self.team("status").stdout
        self.assertIn("real task", listing)
        self.assertNotIn("t050", listing)

    def test_second_task_id_and_drop(self):
        self.team("new", "--no-run", "one")
        self.team("new", "--no-run", "two")
        self.assertIn("t002", self.team("status").stdout)
        self.team("drop", "t002", "not needed")
        self.assertIn("dropped", self.team("status", "t002").stdout)

    def test_run_lock_blocks_drop_and_second_run(self):
        self.team("new", "--no-run", "busy")
        with (self.proj / ".agent-team/t001/.lock-run").open("a") as held:
            teamcfg.lock(held, blocking=False)  # stands in for the process advancing t001
            self.assertIn("is running", self.team("drop", "t001", ok=False).stderr)
            self.assertIn("already running", self.team("run", "t001", ok=False).stderr)
        self.team("drop", "t001")

    def state(self, tid):
        return json.loads((self.proj / f".agent-team/{tid}/state.json").read_text())

    def until_status(self, tid, status):
        deadline = time.time() + 30
        while self.state(tid)["status"] != status:
            self.assertLess(time.time(), deadline, f"{tid} never became {status}: {self.state(tid)}")
            time.sleep(0.2)

    def test_busy_run_is_queued_and_dispatched(self):
        self.team("new", "--no-run", "first")
        self.team("new", "--no-run", "already running")
        self.set_state("t002", status="running")
        with (self.proj / ".agent-team/t002/.lock-run").open("a") as run, \
                (self.proj / ".agent-team/.lock-editor").open("a") as editor:
            teamcfg.lock(run, blocking=False)  # stand in for the process advancing t002 with the default lock
            teamcfg.lock(editor, blocking=False)
            r = self.team("new", "third")
            self.assertIn("queued: resource 'editor' is busy", r.stdout)
            self.assertEqual(self.state("t003")["status"], "new")
            self.set_state("t001", status="gate", reason="Senior Dev: confirm the API")
            self.team("approve", "t001", "go ahead")
            s = self.state("t001")
            self.assertEqual(s["status"], "new")
            self.assertIn("go ahead", s["notes"][-1])  # the approval survives queueing
            self.assertEqual(self.team("queue", "--once").stdout, "")  # t002 holds the lock
        self.set_state("t002", status="done")
        (self.proj / ".agent-team/queue.txt").write_text("# order\nt001: first (after t003)\n")
        self.assertIn("started t003", self.team("queue", "--once").stdout)  # t001 waits for t003
        self.until_status("t003", "failed")  # the fake Producer exits 99
        self.assertIn("exited 99", self.state("t003")["reason"])
        self.assertEqual(self.state("t001")["status"], "new")
        self.set_state("t003", status="done")
        self.assertIn("started t001", self.team("queue", "--once").stdout)
        self.until_status("t001", "failed")
        self.assertIn("queue: starting", (self.proj / ".agent-team/live.log").read_text())

    def test_queue_leaves_deferred_tasks_and_rechecks_claims(self):
        self.team("new", "--no-run", "start it myself")
        self.assertEqual(self.team("queue", "--once").stdout, "")  # --no-run waits for `team run`
        self.set_state("t001", queued=True, status="failed")  # a second runner's stale pick: already ran and failed
        self.team("run", "--queued", "t001")
        self.assertEqual((self.state("t001")["status"], self.state("t001")["n"]), ("failed", 0))

    def test_queue_skips_probe_blocked_tasks(self):
        cfg = self.proj / "team.toml"
        cfg.write_text(cfg.read_text().replace("min_free_mib = 9000", "min_free_mib = 100")
                       .replace('probe_cmd = ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"]',
                                'probe_cmd = ["echo", "10"]')
                       .replace("max_parallel = 3", "max_parallel = 1"))
        self.team("new", "--no-run", "--res", "gpu", "needs the gpu")
        self.team("new", "--no-run", "plain")
        for tid in ("t001", "t002"):
            self.set_state(tid, queued=True)
        self.assertIn("started t002", self.team("queue", "--once").stdout)  # t001 must not hold the only slot
        self.until_status("t002", "failed")
        self.assertEqual(self.state("t001")["status"], "new")

    def test_hold_reserves_locks_until_release(self):
        st = self.proj / ".agent-team"
        self.team("new", "--no-run", "needs the editor")
        self.set_state("t001", queued=True)
        self.assertIn("no active hold", self.team("release", ok=False).stderr)
        holder = subprocess.Popen([sys.executable, "-I", str(ROOT / "team.py"), "hold", "--res", "editor"],
                                  cwd=self.proj, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(holder.kill)
        deadline = time.time() + 30
        while "held for the user" not in (st / "live.log").read_text() if (st / "live.log").exists() else True:
            self.assertLess(time.time(), deadline, "hold never took the editor lock")
            time.sleep(0.2)
        with (st / ".lock-editor").open("a") as f:
            self.assertRaises(BlockingIOError, teamcfg.lock, f, False)
        self.assertEqual(self.team("queue", "--once").stdout, "")  # held: not started
        self.assertIn("already active", self.team("hold", ok=False).stderr)
        self.assertIn("hold ends", self.team("release").stdout)
        self.assertEqual(holder.wait(timeout=30), 0)
        self.assertIn("hold: released", (st / "live.log").read_text())
        self.assertFalse((st / "hold.json").exists())
        (st / "hold.json").write_text('{"locks": ["editor"]}')  # stale: its process is gone
        self.assertIn("started t001", self.team("queue", "--once").stdout)
        self.until_status("t001", "failed")

    def test_release_ends_a_hold_still_waiting_for_a_running_task(self):
        st = self.proj / ".agent-team"
        st.mkdir(exist_ok=True)
        with (st / ".lock-editor").open("a") as busy:
            teamcfg.lock(busy, blocking=False)  # stands in for a running task holding the editor
            holder = subprocess.Popen([sys.executable, "-I", str(ROOT / "team.py"), "hold", "--res", "editor"],
                                      cwd=self.proj, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(holder.kill)
            deadline = time.time() + 30
            while "waiting for 'editor'" not in ((st / "live.log").read_text() if (st / "live.log").exists() else ""):
                self.assertLess(time.time(), deadline, "hold never started waiting")
                time.sleep(0.2)
            self.assertIn("hold ends", self.team("release").stdout)
            self.assertEqual(holder.wait(timeout=15), 0)  # ends while the task still runs
        self.assertIn("hold: released", (st / "live.log").read_text())

    def test_wait_reports_each_change_once(self):
        for request in ("broken", "finished"):
            self.team("new", "--no-run", request)
        self.set_state("t001", status="failed", reason="Producer gave ROUTE=None")
        self.set_state("t002", status="done")
        first = self.team("wait", "--no-block").stdout
        self.assertIn("t001 failed: Producer gave ROUTE=None", first)
        self.assertNotIn("t002", first)  # finished before the first wait: old news
        self.assertEqual(self.team("wait", "--no-block").stdout, "")
        self.set_state("t001", status="running", n=1)  # no process holds its run lock
        self.assertIn("t001 stale: marked running but its process is gone", self.team("wait", "--no-block").stdout)
        self.set_state("t001", status="failed", n=2)  # failed again after a retry: a new event
        self.assertIn("t001 failed", self.team("wait", "--no-block").stdout)
        waiter = subprocess.Popen([sys.executable, "-I", str(ROOT / "team.py"), "wait"], cwd=self.proj, env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(waiter.kill)
        time.sleep(1)
        self.assertIsNone(waiter.poll())  # nothing new: it blocks
        self.set_state("t002", status="gate", reason="Architect: pick a save format", n=3)
        out, err = waiter.communicate(timeout=30)
        self.assertEqual((waiter.returncode, out), (0, "t002 gate: Architect: pick a save format\n"), err)

    def test_wait_flags_slow_and_held_tasks(self):
        for request in ("long", "base", "follow-up"):
            self.team("new", "--no-run", request)
        self.team("wait", "--no-block")
        self.set_state("t001", status="running", stage_started=time.time() - 3 * 3600, route="simple", stage=0)
        self.set_state("t002", status="dropped")
        self.set_state("t003", queued=True)
        (self.proj / ".agent-team/queue.txt").write_text("t003: follow-up (after t002)\n")
        with (self.proj / ".agent-team/t001/.lock-run").open("a") as run:
            teamcfg.lock(run, blocking=False)  # alive, just slow
            out = self.team("wait", "--no-block").stdout
        self.assertIn("t001 slow: implement/mid has run 180 min", out)
        self.assertIn("t003 held: queued after t002, which was dropped", out)
        self.assertEqual(self.state("t003")["status"], "new")  # never started

    def fake_claude(self, body):
        (self.fake / "claude").write_text("#!/bin/sh\n" + body)

    def test_capacity_fallback_cycle_stops(self):
        cfg = self.proj / "team.toml"
        cfg.write_text(cfg.read_text().replace("capacity_fallback = {}", 'capacity_fallback = {producer = "mid", mid = "producer"}'))
        self.fake_claude("echo '503 Service Unavailable' >&2\nexit 1\n")
        self.team("new", "outage")  # must end: producer -> mid -> producer is a cycle
        s = self.state("t001")
        self.assertEqual((s["status"], s["n"]), ("failed", 2))
        self.assertIn("producer -> mid all unavailable", s["reason"])

    def test_agent_exiting_before_reading_the_prompt_fails_the_task(self):
        self.fake_claude("exec 0<&-\nexit 3\n")  # closes stdin at once: the prompt write hits a broken pipe
        self.team("new", "x " * 50000)  # larger than a pipe buffer, below the argv limit
        s = self.state("t001")
        self.assertEqual(s["status"], "failed")
        self.assertIn("exited 3", s["reason"])

    def test_capacity_error_reads_only_cli_errors(self):
        import team
        raw = Path(self.tmp.name) / "raw.jsonl"
        tool = {"type": "assistant", "message": {"content": [{"type": "text", "text": "tests: HTTP 503 at line 503"}]}}
        raw.write_text(json.dumps(tool) + "\n")
        self.assertFalse(team.capacity_error(raw))
        raw.write_text(json.dumps(tool) + '\n{"type": "result", "is_error": true, "result": "API Error: 529 overloaded"}\n')
        self.assertTrue(team.capacity_error(raw))
        raw.write_text("Error: 503 Service Unavailable\n")
        self.assertTrue(team.capacity_error(raw))

    def test_verdict_tolerates_punctuation(self):
        import team
        self.assertEqual(team.tag("notes\nVERDICT: **pass**.\n", "VERDICT")[0], "pass")
        self.assertEqual(team.tag("STATUS: done.", "STATUS")[0], "done")
        self.assertEqual(team.queue_deps("t009: hud (after t007, t008) unlike t002"), ["t007", "t008"])

    def test_approve_escalated_review_retries_the_implementation(self):
        self.team("new", "--no-run", "x")
        self.set_state("t001", route="simple", domain="gameplay", stage=1, status="escalated", review_rounds=3,
                       reason="implement failed review 3 times")
        self.team("approve", "t001", "try again")
        self.assertTrue((self.proj / ".agent-team/t001/logs/01-implement-gameplay.prompt.md").exists())

    def test_agent_leftovers_are_reaped(self):
        pidfile = Path(self.tmp.name) / "bg.pid"
        self.fake_claude(f"sleep 300 >/dev/null 2>&1 &\necho $! > {pidfile}\n"
                         "echo '{\"type\": \"result\", \"result\": \"no tags\"}'\n")
        self.team("new", "leftover")
        pid = int(pidfile.read_text())
        deadline = time.time() + 10
        while Path(f"/proc/{pid}").exists() and Path(f"/proc/{pid}/stat").read_text().split(") ")[1][0] != "Z":
            self.assertLess(time.time(), deadline, "background sleep survived the agent run")
            time.sleep(0.1)

    def test_terminating_a_run_stops_its_agent(self):
        pidfile = Path(self.tmp.name) / "agent.pid"
        self.fake_claude(f"echo $$ > {pidfile}\nexec sleep 300\n")
        run = subprocess.Popen([sys.executable, "-I", str(ROOT / "team.py"), "new", "slow"], cwd=self.proj, env=self.env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(run.kill)
        deadline = time.time() + 20
        while not pidfile.exists() or not pidfile.read_text().strip():
            self.assertLess(time.time(), deadline, "the agent never started")
            time.sleep(0.1)
        pid = int(pidfile.read_text())
        run.terminate()  # e.g. `timeout`, or the pane that started it closing
        run.wait(timeout=20)
        deadline = time.time() + 10
        while Path(f"/proc/{pid}").exists() and Path(f"/proc/{pid}/stat").read_text().split(") ")[1][0] != "Z":
            self.assertLess(time.time(), deadline, "the agent outlived its team run")
            time.sleep(0.1)
        with (self.proj / ".agent-team/t001/.lock-run").open("a") as f:
            teamcfg.lock(f, blocking=False)  # released: raises BlockingIOError if the dead run still held it

    def test_new_skips_an_id_claimed_meanwhile(self):
        from types import SimpleNamespace
        from unittest import mock
        import team
        team.init(self.proj / "team.toml")
        (self.proj / ".agent-team/t001").mkdir(parents=True)  # another `team new` claimed t001 after our listing
        with mock.patch.object(Path, "glob", return_value=[]), mock.patch("os.environ", self.env):
            team.cmd_new(SimpleNamespace(request="second", res="", role=None, no_run=True, skill=[]))
        self.assertEqual(self.state("t002")["request"], "second")
        self.assertFalse((self.proj / ".agent-team/t001/state.json").exists())

    def test_guards_are_rewritten_in_place(self):
        import team
        team.init(self.proj / "team.toml")
        team.ensure_guards()
        guard = self.proj / ".agent-team/guard-bin"
        before = (guard / "git").lstat().st_ino
        team.ensure_guards()  # already right: untouched, so a parallel run never finds it missing
        self.assertEqual((guard / "git").lstat().st_ino, before)
        self.assertEqual(os.readlink(guard / "git"), str(ROOT / "bin/vcs-guard"))
        self.assertEqual([p.name for p in guard.iterdir() if p.name.startswith(".")], [])

    def test_run_lock_waits_out_a_probe(self):
        import threading
        import team
        team.init(self.proj / "team.toml")
        self.team("new", "--no-run", "x")
        probe = (self.proj / ".agent-team/t001/.lock-run").open("a")
        teamcfg.lock(probe, blocking=False)
        threading.Timer(0.3, probe.close).start()
        f = team.run_lock("t001", patience=2)
        self.assertIsNotNone(f)
        f.close()

    def producer_proposes(self, *tasks):
        result = "Next tasks:\n" + "".join(f"TASK: {t}\n" for t in tasks)
        self.fake_claude(f"cat > /dev/null\necho {json.dumps(json.dumps({'type': 'result', 'result': result}))}\n")

    def test_refill_keys_do_not_collide(self):
        (self.proj / ".agent-team").mkdir()
        (self.proj / ".agent-team/queue.txt").write_text("p001: mine\n")
        self.producer_proposes("from the plan")
        self.team("refill")
        self.assertEqual((self.proj / ".agent-team/queue.txt").read_text(), "p001: mine\np002: from the plan\n")
        out = self.team("promote", "all").stdout
        self.assertIn("p001 -> t001", out)
        self.assertIn("p002 -> t002", out)
        self.assertTrue(self.state("t001")["queued"] and self.state("t002")["queued"])

    def test_refill_proposes_promote_and_reject(self):
        self.team("new", "--no-run", "already here")
        self.set_state("t001", status="done", title="already here")
        self.producer_proposes("add a settings page", "write the setup docs")
        self.team("refill")
        queue = (self.proj / ".agent-team/queue.txt").read_text()
        self.assertEqual(queue, "p001: add a settings page\np002: write the setup docs\n")
        prompt = (self.proj / ".agent-team/refill/logs/01-refill-producer.prompt.md").read_text()
        self.assertIn("t001 done: already here", prompt)
        self.assertIn("TASK: <request>", prompt)
        out = self.team("wait", "--no-block").stdout
        self.assertIn("refill proposed: p001, p002 in queue.txt", out)
        self.assertIn("p001 -> t002 (queued)", self.team("promote", "p001").stdout)
        self.assertTrue(self.state("t002")["queued"])
        self.team("reject", "p002", "--why", "docs come later")
        self.assertEqual((self.proj / ".agent-team/queue.txt").read_text(), "t002: add a settings page\n")
        self.assertIn("Not a planned line", self.team("promote", "p009", ok=False).stderr)
        from types import SimpleNamespace
        from unittest import mock
        import team
        team.init(self.proj / "team.toml")
        with (self.proj / ".agent-team/queue.txt").open("a") as q:
            q.write("a1: first\na2: second\n")
        real, calls = team.VCS.new_change, []

        def flaky(desc, hint):  # the second change cannot be created
            calls.append(hint)
            if len(calls) == 2:
                raise RuntimeError("server down")
            return real(desc, hint)
        with mock.patch.object(team.VCS, "new_change", flaky), mock.patch("os.environ", self.env), \
                self.assertRaises(SystemExit):
            team.cmd_promote(SimpleNamespace(keys=["a1", "a2"]))
        queue = (self.proj / ".agent-team/queue.txt").read_text()
        self.assertIn("t003: first", queue)  # kept and queued despite the later failure
        self.assertIn("a2: second", queue)
        self.assertTrue(self.state("t003")["queued"])
        self.team("reject", "a2", "--why", "not this quarter")
        self.assertIn({"key": "a2", "request": "second", "status": "rejected", "why": "not this quarter", "user": True},
                      [{k: v for k, v in p.items() if k != "t"} for p in team.refill_state()["proposals"]])
        with (self.proj / ".agent-team/queue.txt").open("a") as q:
            q.write("mine: tidy the logs\n")
        self.producer_proposes("none")
        self.team("refill")
        prompt = (self.proj / ".agent-team/refill/logs/02-refill-producer.prompt.md").read_text()
        self.assertIn("write the setup docs (why: docs come later)", prompt)  # rejected: not proposed again
        self.assertIn("- mine: tidy the logs", prompt)  # planned by the user: not proposed again
        self.assertIn("refill empty: no planned work left", self.team("wait", "--no-block").stdout)

    def test_refill_needs_a_slot_and_tagged_output(self):
        self.fake_claude("cat > /dev/null\necho '{\"type\": \"result\", \"result\": \"could not read the plan\"}'\n")
        self.team("refill")
        self.assertIn("refill failed: Producer gave no TASK lines", self.team("wait", "--no-block").stdout)
        import team
        team.init(self.proj / "team.toml")
        self.assertIsNone(team.refill_state()["empty_sig"])  # still retryable after the cooldown
        held = [(self.proj / f".agent-team/.lock-slot{i}").open("a") for i in range(3)]
        for f in held:
            teamcfg.lock(f, blocking=False)
        r = self.team("refill", ok=False)
        self.assertIn("Every team slot is busy", r.stderr)
        self.assertEqual(team.refill_state()["n"], 1)  # no second Producer run
        for f in held:
            f.close()
        (self.fake / "claude").unlink()  # the Producer CLI cannot start; no real claude may be found either
        self.env["PATH"] = f"{self.fake}:/usr/bin:/bin"
        self.team("refill")
        self.assertIn("refill failed: Producer could not run", self.team("wait", "--no-block").stdout)
        team._update_refill(lambda r: r.update(status="running", n=9))  # a refill killed mid-run
        self.assertIn("refill stale: the last refill was interrupted", self.team("wait", "--no-block").stdout)

    def test_refill_triggers_only_when_due(self):
        import team
        cfg = self.proj / "team.toml"
        cfg.write_text(cfg.read_text().replace("refill = false", "refill = true"))
        team.init(cfg)
        team._spawned.clear()
        self.assertIsNone(team.refill_blocker({}, set()))
        self.assertIsNone(team.refill_blocker({"t001": {"status": "new"}}, set()))  # --no-run: no queued field
        (self.proj / ".agent-team").mkdir(exist_ok=True)
        (self.proj / ".agent-team/queue.txt").write_text("p001: waiting for the user\n")
        self.assertEqual(team.refill_blocker({}, set()), "the queue is not low")
        (self.proj / ".agent-team/queue.txt").write_text("")
        gates = {f"t00{i}": {"status": "gate"} for i in (1, 2)}
        self.assertEqual(team.refill_blocker(gates, set()), "tasks are waiting for the user")
        self.assertEqual(team.refill_blocker({}, {"t1", "t2", "t3"}), "every slot is busy")
        nine = [{"key": f"p{i:03d}", "request": "x", "t": time.time(), "status": "rejected"} for i in range(9)]
        team._update_refill(lambda r: r.update(proposals=nine))
        self.assertEqual(team.refill_allowance(team.refill_state()), 1)  # 10 a day, not 9 + a batch of 3
        team._update_refill(lambda r: r.update(proposals=nine + [dict(nine[0], key="p009")]))
        self.assertIn("Daily proposal cap", self.team("refill", ok=False).stderr)
        self.assertIsNone(team.refill_state()["empty_sig"])  # capped is not "no planned work left"
        team._update_refill(lambda r: r.update(proposals=[]))
        team._update_refill(lambda r: r.update(last=time.time()))
        self.assertEqual(team.refill_blocker({}, set()), "cooling down")
        team._update_refill(lambda r: r.update(last=0, empty_sig=team.plan_signature()))
        self.assertEqual(team.refill_blocker({}, set()), "no planned work left")
        (self.proj / "TASKS.md").write_text("## Current phase\n- [ ] new item\n")  # the plan changed
        self.assertIsNone(team.refill_blocker({}, set()))
        self.producer_proposes("from the queue pass")
        self.team("queue", "--once")  # dispatch starts the refill in the background
        deadline = time.time() + 30
        while "p001" not in ((self.proj / ".agent-team/queue.txt").read_text()):
            self.assertLess(time.time(), deadline, "the queue pass never refilled")
            time.sleep(0.2)

    def test_windows_shims(self):
        """npm .cmd shims are bypassed for their node script; guard names get .cmd and sh shims, not symlinks."""
        from types import SimpleNamespace
        from unittest import mock
        nt = SimpleNamespace(name="nt")  # only os.name is read on these paths; pathlib keeps the host flavour
        bindir = Path(self.tmp.name) / "npm"
        script = bindir / "node_modules/@openai/codex/bin/codex.js"
        script.parent.mkdir(parents=True)
        script.write_text("")
        (bindir / "node.exe").write_text("")
        shim = bindir / "codex.cmd"
        shim.write_text('@ECHO off\r\nendLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
                        '"%dp0%\\node_modules\\@openai\\codex\\bin\\codex.js" %*\r\n')
        with mock.patch.object(teamcfg, "os", nt), mock.patch.object(teamcfg.shutil, "which", return_value=str(shim)):
            argv = teamcfg.command(["codex", "exec", "line one\nline two"])
        self.assertEqual(argv[0], str(bindir / "node.exe"))
        self.assertEqual(Path(argv[1].replace("\\", "/")), script)
        self.assertEqual(argv[2:], ["exec", "line one\nline two"])
        (bindir / "plain.cmd").write_text("@exit /b 99\r\n")
        with mock.patch.object(teamcfg, "os", nt), mock.patch.object(teamcfg.shutil, "which", return_value=str(bindir / "plain.cmd")):
            self.assertEqual(teamcfg.command(["plain", "x"]), [str(bindir / "plain.cmd"), "x"])

        import team
        team.init(self.proj / "team.toml")
        nt_files = SimpleNamespace(name="nt", getpid=os.getpid, readlink=os.readlink, replace=os.replace)
        with mock.patch.object(team, "os", nt_files):  # ensure_guards swaps files in atomically
            team.ensure_guards()
        guard = self.proj / ".agent-team/guard-bin"
        self.assertFalse((guard / "git").is_symlink())
        self.assertIn('set "TEAM_GUARD_TOOL=git"', (guard / "git.cmd").read_text())
        self.assertIn("vcs-guard", (guard / "git").read_text())
        self.assertIn("TEAM_GUARD_ROOT=", (guard / "git").read_text())
        self.assertIn('set "TEAM_GUARD_CONFIG=', (guard / "git.cmd").read_text())
        self.assertEqual((guard / "root").read_text().strip(), str(self.proj.resolve()))
        sh = subprocess.run(["sh", str(guard / "git"), "commit", "-qm", "x"], cwd=self.proj, env=self.env,
                            capture_output=True, text=True, timeout=10)
        self.assertIn("not allowed", sh.stderr)
        self.assertEqual(self.git("rev-list", "--count", "HEAD").strip(), "1")

    def test_guard_denies_and_forwards(self):
        self.team("new", "--no-run", "x")
        guard = self.proj / ".agent-team/guard-bin"
        ok = self.team("run", "t001", ok=False)  # creates guard-bin
        self.assertTrue(guard.exists(), ok.stderr)
        env = dict(self.env, PATH=f"{guard}:{self.env['PATH']}")
        deny = subprocess.run(["git", "commit", "-qm", "x"], cwd=self.proj, env=env, capture_output=True, text=True)
        self.assertNotEqual(deny.returncode, 0)
        self.assertIn("not allowed", deny.stderr)
        deny = subprocess.run(["git", "-C", ".", "push"], cwd=self.proj, env=env, capture_output=True, text=True)
        self.assertIn("not allowed", deny.stderr)
        fwd = subprocess.run(["git", "status", "--porcelain"], cwd=self.proj, env=env, capture_output=True, text=True)
        self.assertEqual(fwd.returncode, 0, fwd.stderr)
        for tool in ("pkill", "killall"):  # killing by name is refused for agents
            deny = subprocess.run([tool, "-f", "nothing-matches-this"], cwd=self.proj, env=env, capture_output=True,
                                  text=True)
            self.assertEqual((deny.returncode, "is not allowed" in deny.stderr), (1, True), tool)
        self.git("config", "alias.sv", "add")  # aliases set before the run (agents may not run `git config`)
        self.git("config", "alias.sh", "!git commit")
        for argv in (["-c", "alias.ci=commit", "ci", "-qm", "x"], ["sv", "README.md"], ["sh"],
                     ["config", "user.name", "x"], ["branch", "-df", "main"], ["branch", "--delete", "--force", "main"]):
            deny = subprocess.run(["git", *argv], cwd=self.proj, env=env, capture_output=True, text=True)
            self.assertNotEqual(deny.returncode, 0, argv)
            self.assertIn("not allowed", deny.stderr, argv)
        self.assertEqual(self.git("rev-list", "--count", "HEAD").strip(), "1")
        fwd = subprocess.run(["git", "branch", "--list"], cwd=self.proj, env=env, capture_output=True, text=True)
        self.assertEqual(fwd.returncode, 0, fwd.stderr)
        # No TEAM_REAL_GIT and the guard dir on PATH under a second spelling: still finds the real git, no loop.
        alias_dir = Path(self.tmp.name) / "guard-alias"
        alias_dir.symlink_to(guard)
        env2 = {k: v for k, v in env.items() if k != "TEAM_REAL_GIT"}
        env2["PATH"] = f"{alias_dir}:{env['PATH']}"
        fwd = subprocess.run(["git", "--version"], cwd=self.proj, env=env2, capture_output=True, text=True, timeout=10)
        self.assertEqual(fwd.returncode, 0, fwd.stderr)

    def test_codex_writer_sandbox(self):
        argv_file = Path(self.tmp.name) / "codex-argv"
        (self.fake / "codex").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{argv_file}"\nexit 99\n')
        mid = '[roles.mid]\nname = "Mid Dev"\ncli = "claude"'
        self.assertIn(mid, TOML)
        (self.proj / "team.toml").write_text(TOML.replace(mid, mid.replace("claude", "codex")))
        self.team("new", "--no-run", "--role", "mid", "side task")
        self.team("run", "t001", ok=False)
        args = argv_file.read_text().splitlines()
        self.assertEqual(args[args.index("-s") + 1], "workspace-write")
        self.assertIn("--skip-git-repo-check", args)  # Perforce workspaces are not git repos
        cfg = (self.proj / "team.toml").read_text()
        self.assertIn('codex_sandbox = "workspace-write"', cfg)
        (self.proj / "team.toml").write_text(cfg.replace('codex_sandbox = "workspace-write"', 'codex_sandbox = "user"'))
        self.team("run", "t001", ok=False)
        self.assertNotIn("-s", argv_file.read_text().splitlines())  # the writer follows the user's Codex config
        (self.proj / "team.toml").write_text(cfg.replace('codex_sandbox = "workspace-write"', 'codex_sandbox = "User"'))
        with self.assertRaisesRegex(ValueError, "codex_sandbox must be one of"):
            teamcfg.load(self.proj / "team.toml")

    def test_git_adapter(self):
        a = vcs.Git(self.proj)
        self.assertEqual(a.new_change("desc", "t007"), "t007")
        self.assertEqual(a.opened("t007"), "")
        self.assertEqual(a.pending_changes(), [])
        (self.proj / "README.md").write_text("changed\n")
        (self.proj / "new.txt").write_text("fresh\n")
        self.assertEqual(sorted(a.opened_files("t007")), ["README.md", "new.txt"])
        d = a.diff("t007")
        self.assertIn("+changed", d)
        self.assertIn("+fresh", d)
        self.assertEqual(a.pending_changes(), ["work"])
        self.assertEqual(a.others_opened("t007"), "")
        self.assertEqual(a.prepare_edit(self.proj / "README.md", "t007"), (True, ""))
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")  # never stages
        state = self.proj / ".agent-team"
        (state / "t001").mkdir(parents=True)
        (state / "t001/changes.diff").write_text("old diff\n")
        a.state_dir = state.resolve()
        self.assertEqual(sorted(a.opened_files("t007")), ["README.md", "new.txt"])
        self.assertNotIn("old diff", a.diff("t007"))

    def test_subcommand_parser(self):
        opts = vcs.Git.arg_opts
        self.assertEqual(vcs.subcommand(opts, ["-C", "x", "-c", "a=b", "commit", "-m", "m"]), ("commit", ["-m", "m"]))
        self.assertEqual(vcs.subcommand(opts, ["--version"]), ("", []))

    def test_codex_journal_shared_by_codex_home(self):
        with_env = lambda home: self._journal(home)  # noqa: E731
        a, b, c = with_env("/tmp/ch1"), with_env("/tmp/ch1"), with_env("/tmp/ch2")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(a.parent.name, "codex")
        self.assertEqual(a.parent.parent.name, "agent-team")

    def _journal(self, home):
        old = dict(os.environ)
        os.environ.update(CODEX_HOME=home, XDG_STATE_HOME=self.env["XDG_STATE_HOME"])
        try:
            return teamcfg.codex_journal()
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_review_page_escapes(self):
        self.team("new", "--no-run", "<script>alert(1)</script>")
        sp = self.proj / ".agent-team/t001/state.json"
        s = json.loads(sp.read_text())
        s.update(title="<script>alert(1)</script>", status="done")
        sp.write_text(json.dumps(s))
        r = subprocess.run([sys.executable, "-I", str(ROOT / "review_page"), "t001"], cwd=self.proj, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        page = (self.proj / ".agent-team/review/review.html").read_text()
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn(html.escape("<script>alert(1)</script>"), page)

    def set_state(self, tid, **fields):
        sp = self.proj / f".agent-team/{tid}/state.json"
        s = json.loads(sp.read_text())
        s.update(fields)
        sp.write_text(json.dumps(s))

    def test_review_page_next_steps_and_diff(self):
        self.team("new", "--no-run", "needs a call")
        self.set_state("t001", status="gate", reason="Architect: pick a save format")
        (self.proj / ".agent-team/t001/changes.diff").write_text("+added <line>\n")
        (self.proj / ".agent-team/t100").mkdir()
        (self.proj / ".agent-team/t100/state.json").write_text(json.dumps(dict(
            json.loads((self.proj / ".agent-team/t001/state.json").read_text()), id="t100", status="done")))
        (self.proj / ".agent-team/t101").mkdir()  # a packet folder without task state is skipped
        r = subprocess.run([sys.executable, "-I", str(ROOT / "review_page"), "t001"], cwd=self.proj, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        page = (self.proj / ".agent-team/review/review.html").read_text()
        self.assertIn("Architect: pick a save format", page)
        self.assertIn("team approve t001", page)
        self.assertIn(html.escape("+added <line>"), page)
        r = subprocess.run([sys.executable, "-I", str(ROOT / "review_page")], cwd=self.proj, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("id=t100", (self.proj / ".agent-team/review/review.html").read_text())

    def test_notifier_opens_review_page(self):
        opened = Path(self.tmp.name) / "opened"
        browser = self.fake / "browser"
        browser.write_text(f"#!{sys.executable}\nimport sys\nopen({str(opened)!r}, 'a').write(sys.argv[1] + '\\n')\n")
        browser.chmod(0o755)
        env = dict(self.env, BROWSER=str(browser), PATH=f"{self.fake}:/usr/bin:/bin")  # no notify-send
        for request in ("waiting", "finished"):
            self.team("new", "--no-run", request)
        self.set_state("t001", status="gate", reason="Senior Dev: confirm the API")
        self.set_state("t002", status="done")
        r = subprocess.run([sys.executable, "-I", str(ROOT / "notifier"), "--once"], cwd=self.proj, env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("t001 gate: Senior Dev: confirm the API", r.stdout)
        self.assertNotIn("t002", r.stdout)  # done before the dashboard started: not re-announced
        self.assertTrue(opened.read_text().strip().endswith("review/review.html"))
        page = (self.proj / ".agent-team/review/review.html").read_text()
        self.assertIn("id=t001", page)
        self.assertNotIn("id=t002", page)

    def test_notifier_cadence_custom_skips_done_but_opens_attention(self):
        opened = Path(self.tmp.name) / "opened"
        browser = self.fake / "browser"
        browser.write_text(f"#!{sys.executable}\nimport sys\nopen({str(opened)!r}, 'a').write(sys.argv[1] + '\\n')\n")
        browser.chmod(0o755)
        (self.proj / "team.toml").write_text((self.proj / "team.toml").read_text()
                                             .replace('# review_cadence = "task"', 'review_cadence = "custom"'))
        env = dict(self.env, BROWSER=str(browser), PATH=f"{self.fake}:/usr/bin:/bin")
        for request in ("one", "two", "three"):
            self.team("new", "--no-run", request)
        run = lambda: subprocess.run([sys.executable, "-I", str(ROOT / "notifier"), "--once"], cwd=self.proj, env=env,
                                     capture_output=True, text=True, timeout=30)
        self.assertEqual(run().returncode, 0)
        self.set_state("t001", status="done")
        self.set_state("t002", status="blocked", reason="needs a key")
        r = run()
        self.assertIn("t002 blocked", r.stdout)
        self.assertNotIn("t001 done", r.stdout)
        page = (self.proj / ".agent-team/review/review.html").read_text()
        self.assertIn("id=t002", page)
        self.assertNotIn("id=t001", page)
        self.assertEqual(json.loads((self.proj / ".agent-team/review_cadence.json").read_text())["pending"], [])


if __name__ == "__main__":
    unittest.main()
