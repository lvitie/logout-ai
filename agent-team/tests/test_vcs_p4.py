"""Perforce adapter against a fake p4 on disk (logs argv, canned output). No server, no network. Run with python3 -I."""
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

    def test_opened_parsing(self):
        self.assertEqual(self.a.opened_files("7"), ["//depot/a.txt", "//depot/b.txt"])
        self.assertEqual(self.a.others_opened("7"), "42|//depot/c.txt\ndefault|//depot/d.txt")


if __name__ == "__main__":
    unittest.main()
