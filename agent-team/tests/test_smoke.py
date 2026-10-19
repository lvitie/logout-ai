"""Smoke tests: temp git project, config load, task creation, status, VCS guard, adapters, shared journal, review page.
No network and no real agents: HOME/XDG/GIT_CONFIG_GLOBAL are redirected, probes are empty, and fake claude/codex
binaries that exit 99 sit first on PATH so any agent spawn fails loudly. Run with python3 -I."""
import html
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import teamcfg  # noqa: E402
import vcs  # noqa: E402

TOML = (ROOT / "templates/team.toml").read_text()


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
        (self.proj / "team.toml").write_text(TOML.replace('name = "myproject"', 'name = "demo"'))
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
        (self.proj / "typo.toml").write_text(TOML.replace('# fails = 3\n# role = "senior"', 'fails = 3\nrole = "senoir"'))
        with self.assertRaisesRegex(ValueError, "after_impl_fails.*senoir"):
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
        self.assertEqual((state["change"], state["status"], state["res"]), ("t001", "new", ["shared"]))
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
        self.assertIn("DOMAIN: code", prompt)
        self.assertNotIn("{", prompt.split("## Job")[1])
        self.assertTrue((self.proj / ".agent-team/guard-bin/git").is_symlink())

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
        with mock.patch.object(team, "os", nt):
            team.ensure_guards()
        guard = self.proj / ".agent-team/guard-bin"
        self.assertFalse((guard / "git").is_symlink())
        self.assertIn('set "TEAM_GUARD_TOOL=git"', (guard / "git.cmd").read_text())
        self.assertIn("vcs-guard", (guard / "git").read_text())
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


if __name__ == "__main__":
    unittest.main()
