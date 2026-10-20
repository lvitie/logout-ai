"""[vcs] kind = "none": no tool, no guard, no deny rules; the adapter records written files. Run with python3 -I."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import teamcfg  # noqa: E402
import vcs  # noqa: E402


class NoneAdapter(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name).resolve()
        self.state = self.d / ".agent-team"
        self.a = vcs.NoneVcs(self.d)
        self.a.state_dir = self.state

    def test_class_and_flags(self):
        self.assertIs(vcs.adapter_class("none"), vcs.NoneVcs)
        self.assertFalse(vcs.NoneVcs.submit_step)
        self.assertFalse(vcs.NoneVcs.sandbox_network)
        self.assertTrue(vcs.Vcs.submit_step)
        self.assertEqual(self.a.new_change("d", "t001"), "t001")

    def test_records_written_files_once_without_git(self):
        (self.d / "sub").mkdir()
        for name in ("sub/b.txt", "a.txt", "sub/b.txt"):
            self.assertEqual(self.a.prepare_edit(self.d / name, "t001"), (True, ""))
        self.assertEqual(self.a.add(self.d / "a.txt", "t001"), (True, ""))
        self.assertEqual(self.a.opened_files("t001"), ["a.txt", "sub/b.txt"])
        self.assertEqual(self.a.opened("t001"), "a.txt\nsub/b.txt")
        self.assertEqual(self.a.changed_files("t001"), [self.d / "a.txt", self.d / "sub/b.txt"])
        self.assertEqual(self.a.opened_files("t002"), [])
        self.assertEqual(self.a.diff("t001"), "")
        self.assertEqual(self.a.pending_changes(), [])
        self.assertFalse((self.d / ".git").exists())

    def test_ignores_state_dir_and_outside_paths(self):
        self.a.add(self.state / "t001" / "x.md", "t001")
        self.a.add(self.d.parent / "elsewhere.txt", "t001")
        self.assertEqual(self.a.opened_files("t001"), [])


class NoneConfig(unittest.TestCase):
    def test_write_config_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "team.toml"
            subprocess.run([sys.executable, "-I", str(ROOT / "write_config.py"), str(ROOT / "templates/team.toml"),
                            str(dst), "demo", "claude", "none"], check=True)
            cfg = teamcfg.load(str(dst))
        self.assertEqual(cfg["vcs"]["kind"], "none")
        self.assertEqual(cfg["vcs"]["guard_names"], [])
        self.assertEqual(cfg["vcs"]["deny"], {})
        self.assertEqual(cfg["vcs"]["deny_flags"], {})
        self.assertEqual(teamcfg.change_noun(cfg), "changes")
        self.assertIn("none", (ROOT / "templates/vcs/none.md").read_text())


if __name__ == "__main__":
    unittest.main()
