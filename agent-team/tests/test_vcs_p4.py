"""Perforce adapter against a fake p4 on disk (logs argv, canned output). No server, no network. Run with python3 -I."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import vcs_p4  # noqa: E402

FAKE = r"""#!/bin/sh
echo "$*" >> "$(dirname "$0")/argv.log"
case "$*" in
  "-F %change% opened "*stray*) echo default ;;
  "-F %change% opened "*other*) echo 42 ;;
  "-F %change% opened "*) echo "$5 - file(s) not opened on this client." >&2 ;;
  "-F %depotFile% opened -c 7") printf '//depot/a.txt\n//depot/b.txt\n' ;;
  "-F %change%|%depotFile% opened") printf '7|//depot/a.txt\n42|//depot/c.txt\ndefault|//depot/d.txt\n' ;;
esac
"""


class P4Adapter(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        p4 = self.d / "p4"
        p4.write_text(FAKE)
        p4.chmod(0o755)
        self.log = self.d / "argv.log"
        self.a = vcs_p4.Adapter(self.d, str(p4))

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_prepare_edit_opens_readonly_file(self):
        f = self.d / "ro.txt"
        f.write_text("x")
        f.chmod(0o444)
        self.assertEqual(self.a.prepare_edit(f, "7"), (True, ""))
        self.assertIn(f"edit -c 7 {f}", self.calls())

    def test_prepare_edit_reopens_default_and_skips_other(self):
        self.a.prepare_edit(self.d / "stray.txt", "7")
        self.assertIn(f"reopen -c 7 {self.d / 'stray.txt'}", self.calls())
        self.a.prepare_edit(self.d / "other.txt", "7")
        self.assertFalse([c for c in self.calls() if c.startswith(("edit", "reopen")) and "other" in c])

    def test_guard_parses_global_options(self):
        """-b/-L/-v take a value; `integ` is denied like `integrate`."""
        env = dict(os.environ, TEAM_CONFIG=str(ROOT.parent / "examples/unreal-p4/team.toml"),
                   TEAM_REAL_P4=str(self.d / "p4"), TEAM_GUARD_TOOL="p4")

        def guard(*args):
            return subprocess.run([sys.executable, "-I", str(ROOT / "bin/vcs-guard"), *args], cwd=self.d, env=env,
                                  capture_output=True, text=True, timeout=10)
        for argv in (["integ", "//a/...", "//b/..."], ["-b", "5", "submit"], ["-v", "net=1", "integrate", "x"]):
            r = guard(*argv)
            self.assertIn("not allowed", r.stderr, argv)
        self.assertEqual(self.calls(), [])
        r = guard("-L", "en", "-v", "net=1", "opened")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ["-L en -v net=1 opened"])

    def test_opened_parsing(self):
        self.assertEqual(self.a.opened_files("7"), ["//depot/a.txt", "//depot/b.txt"])
        self.assertEqual(self.a.others_opened("7"), "42|//depot/c.txt\ndefault|//depot/d.txt")


if __name__ == "__main__":
    unittest.main()
