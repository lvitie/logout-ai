"""vcs-guard lets git run in repos outside the project root (temp-dir fixtures) and still denies inside it."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "bin/vcs-guard"
TOML = (ROOT / "templates/team.toml").read_text()


class GuardScope(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        t = Path(tmp.name).resolve()
        self.t, self.proj, self.out = t, t / "proj", t / "out"
        self.guard = t / "guard-bin"
        for d in (self.proj, self.out, self.guard, t / "home"):
            d.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("TEAM_", "GIT_"))}
        self.env.update(HOME=str(t / "home"), GIT_CONFIG_GLOBAL=str(t / "home/.gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        self.real = next(c for d in self.env["PATH"].split(os.pathsep)  # skip an agent's own guard-bin
                         if Path(d).name != "guard-bin" and (c := shutil.which("git", path=d)))
        self.cfg = self.proj / "team.toml"
        self.write_cfg(TOML)
        (self.guard / "git").symlink_to(GUARD)
        (self.guard / "root").write_text(f"{self.proj}\n")
        (self.guard / "config").write_text(f"{self.cfg}\n")
        self.env.update(TEAM_REAL_GIT=self.real, PATH=f"{self.guard}:{self.env['PATH']}")
        for d in (self.proj, self.out):
            self.git(d, "init", "-q")
        (self.proj / "a.txt").write_text("a")
        self.git(self.proj, "config", "alias.sv", "add", real=True)

    def write_cfg(self, text):
        self.cfg.write_text(text.replace('name = "myproject"', 'name = "demo"'))

    def git(self, cwd, *a, real=False, cmd=None, env=None):
        exe = self.real if real else "git"
        return subprocess.run(cmd or [exe, *a], cwd=cwd, env=env or self.env, capture_output=True, text=True, timeout=20)

    def assertDenied(self, r):
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not allowed", r.stderr)

    def test_fixture_outside_root_passes(self):
        for argv in (["config", "user.name", "t"], ["config", "user.email", "t@x"], ["add", "-A"]):
            r = self.git(self.out, *argv)
            self.assertEqual(r.returncode, 0, r.stderr)
        empty = self.t / "empty"
        empty.mkdir()
        self.assertEqual(self.git(empty, "init", "-q").returncode, 0)

    def test_sh_shim_outside_root_passes(self):
        shim = self.t / "shim"
        shim.write_text(f'#!/bin/sh\nTEAM_GUARD_TOOL=git TEAM_GUARD_ROOT="{self.proj}" TEAM_GUARD_CONFIG="{self.cfg}" '
                        f'exec "{sys.executable}" "{GUARD}" "$@"\n')
        r = self.git(self.out, cmd=["sh", str(shim), "add", "-A"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertDenied(self.git(self.proj, cmd=["sh", str(shim), "add", "-A"]))

    def test_denied_inside_root(self):
        self.assertDenied(self.git(self.proj, "add", "-A"))
        self.assertDenied(self.git(self.proj, "config", "user.name", "x"))
        self.assertDenied(self.git(self.proj, "sv", "a.txt"))  # alias
        self.assertDenied(self.git(self.out, "-c", "alias.ci=commit", "-C", str(self.proj), "ci", "-m", "x"))

    def test_denied_via_symlinked_cwd(self):
        link = self.t / "link"
        link.symlink_to(self.proj)
        self.assertDenied(self.git(link, "add", "-A"))

    def test_denied_when_pointed_into_root(self):
        self.assertDenied(self.git(self.out, "-C", str(self.proj), "add", "-A"))
        self.assertDenied(self.git(self.out, "--git-dir", str(self.proj / ".git"), "add", "-A"))
        env = dict(self.env, GIT_DIR=str(self.proj / ".git"))
        self.assertDenied(self.git(self.out, "add", "-A", env=env))
        env["GIT_WORK_TREE"] = str(self.proj)
        self.assertDenied(self.git(self.out, "add", "-A", env=env))

    def test_denied_with_stacked_c(self):
        self.assertDenied(self.git(self.out, "-C", "/", "-C", str(self.proj).lstrip("/"), "add", "-A"))

    def test_denied_in_shared_worktree(self):
        self.git(self.proj, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "a", "--allow-empty", real=True)
        wt = self.t / "wt"
        r = self.git(self.proj, "worktree", "add", "-q", str(wt), real=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertDenied(self.git(wt, "add", "-A"))
        self.assertDenied(self.git(wt, "commit", "-m", "x"))

    def test_push_denied_outside_root(self):
        clone = self.t / "clone"
        self.git(self.proj, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "a", "--allow-empty", real=True)
        r = self.git(self.t, "clone", "-q", str(self.proj), str(clone))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertDenied(self.git(clone, "push"))
        self.assertDenied(self.git(clone, "-c", "alias.up=push", "up"))
        self.assertDenied(self.git(self.out, "push", str(self.proj)))

    def test_p4_stays_denied(self):
        fake = self.t / "fake"
        fake.mkdir()
        (fake / "p4").write_text("#!/bin/sh\nexit 0\n")
        (fake / "p4").chmod(0o755)
        (self.guard / "p4").symlink_to(GUARD)
        vcs = '[vcs]\nkind = "p4"\nguard_names = ["git", "p4"]\n[vcs.deny]\ngit = ["*"]\np4 = ["submit"]\n\n'
        self.write_cfg(re.sub(r"\[vcs\].*?(?=\[agents\])", lambda m: vcs, TOML, flags=re.S))
        env = dict(self.env, TEAM_REAL_P4=str(fake / "p4"))
        self.assertDenied(self.git(self.out, cmd=["p4", "submit"], env=env))
        self.assertDenied(self.git(self.out, "status"))  # git under a p4 project stays denied everywhere

    def test_missing_root_file_keeps_denying(self):
        (self.guard / "root").unlink()
        self.assertDenied(self.git(self.out, "add", "-A"))


if __name__ == "__main__":
    unittest.main()
