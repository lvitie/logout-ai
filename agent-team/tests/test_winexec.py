"""winexec: Windows programs for sandboxed agents on WSL, run by the team process through a file spool."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import winexec  # noqa: E402


class Winexec(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = Path(tmp.name)
        self.bin, self.spool = self.t / "bin", self.t / "spool"
        self.bin.mkdir()
        exe = self.bin / "fake.exe"
        exe.write_text('#!/bin/sh\necho "out $* in $(pwd)"\necho err >&2\nexit 7\n')
        exe.chmod(0o755)
        self.path = f"{self.bin}{os.pathsep}{os.environ['PATH']}"

    def client(self, *argv, spool=True, pickup=None):
        code = "import sys, winexec; " + (f"winexec.PICKUP = {pickup}; " if pickup else "") + "winexec.client(sys.argv[1:])"
        env = dict(os.environ, PATH=self.path)
        env.pop("TEAM_WINEXEC", None)
        if spool:
            env["TEAM_WINEXEC"] = str(self.spool)
        return subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r}); {code}", *argv],
                              cwd=self.t, env=env, capture_output=True, text=True, timeout=30)

    def test_spooled_run_returns_output_and_exit_code(self):
        with winexec.serving(self.spool, ["fake.exe"], self.path):
            r = self.client("fake", "a", "b")  # .exe is optional
        self.assertEqual((r.returncode, r.stdout, r.stderr), (7, f"out a b in {self.t}\n", "err\n"))
        self.assertEqual(list(self.spool.iterdir()), [])

    def test_unlisted_program_is_refused(self):
        with winexec.serving(self.spool, ["fake.exe"], self.path):
            r = self.client(str(self.bin / "other.exe"))
        self.assertEqual(r.returncode, 126)
        self.assertIn("not in [agents] windows_exec (fake.exe)", r.stderr)

    def test_without_a_spool_the_program_runs_directly(self):
        r = self.client("fake.exe", "x", spool=False)
        self.assertEqual((r.returncode, r.stdout), (7, f"out x in {self.t}\n"))

    def test_request_nobody_serves_fails(self):
        self.spool.mkdir()
        r = self.client("fake.exe", pickup=0.3)
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing picked up the request", r.stderr)
        self.assertEqual(list(self.spool.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
