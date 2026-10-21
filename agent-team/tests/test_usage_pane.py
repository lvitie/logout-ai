"""usage_tui panel fit and the [usage] extra_module hook (rows/json from a project file). Offline. Run with python3 -I."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from cfgutil import TOML  # noqa: E402

loader = importlib.machinery.SourceFileLoader("usage_tui_pane", str(ROOT / "usage_tui"))
spec = importlib.util.spec_from_loader(loader.name, loader)
usage = importlib.util.module_from_spec(spec)
loader.exec_module(usage)

EXTRA = '''
def rows(cfg, compact=False):
    return [(0, ui.compact_row("Extra", "7d", 40, 0) if compact else "Extra   7d " + ui.bar(40)), (1, "extra detail")]


def json(cfg, timeout=0):
    return {"extra_7d": 40, "extra_root": str(cfg["root"])}
'''


class UsagePane(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = self.dir / "team.toml"
        self.cfg.write_text(TOML)
        (self.dir / "extra.py").write_text(EXTRA)
        (self.dir / "broken.py").write_text("def rows(:\n")
        self.env = patch.dict(os.environ, {"TEAM_CONFIG": str(self.cfg)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def use(self, module):
        self.cfg.write_text(TOML.replace('extra_module = ""', f'extra_module = "{module}"'))

    def json_out(self):
        env = dict(os.environ, PATH="/nonexistent")  # no codex: --json must still work
        out = subprocess.run([sys.executable, "-I", str(ROOT / "usage_tui"), "--json"], env=env,
                             capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout)

    def _draw(self, columns, rows):
        now = 1_800_000_000
        with patch.object(usage.shutil, "get_terminal_size", return_value=os.terminal_size((columns, rows))), \
             patch.object(usage.time, "time", return_value=now), \
             patch.object(usage, "codex", return_value=({
                 "primary": {"window_minutes": 300, "used_percent": 5, "resets_at": now + 3600},
                 "secondary": {"window_minutes": 10080, "used_percent": 61, "resets_at": now + 86400}}, "")), \
             patch.object(usage, "codex_resets", return_value=(3, "x", None)), \
             patch.object(usage, "claude_plan", return_value=([
                 ("5h", 12, now + 9600), ("7d", 52, now + 86400), ("7d Fable", 3, now + 86400)], "fixture")), \
             patch.object(usage, "claude", return_value=(0, 0)), \
             patch.object(usage, "team_spend", return_value=(0, 0)), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            usage.draw()
        return usage.re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out.getvalue())

    def test_no_extra_module_by_default(self):
        self.assertEqual(usage._extra()[1], None)
        self.assertNotIn("extra_7d", self.json_out())

    def test_extra_module_rows_and_json(self):
        self.use("extra.py")  # relative to the project root
        self.assertEqual(self.json_out()["extra_7d"], 40)
        full = self._draw(100, 24)
        self.assertIn("Extra   7d ", full)
        self.assertIn("extra detail", full)
        self.assertIn("Extra", self._draw(40, 24))  # compact row through ui.compact_row

    def test_broken_extra_module_is_ignored(self):
        for module in ("broken.py", "missing.py"):
            with self.subTest(module=module):
                self.use(module)
                self.assertNotIn("extra_7d", self.json_out())  # still valid JSON
                self.assertIn("Codex   7d", self._draw(100, 24))

    def test_pane_fit_keeps_weekly_bars_and_scoped_label(self):
        self.use("extra.py")
        for columns in (66, 100):
            for rows in (10, 12):
                with self.subTest(columns=columns, rows=rows):
                    lines = self._draw(columns, rows).splitlines()
                    self.assertLessEqual(len(lines), rows - usage.BORDER)
                    self.assertTrue(all(len(line) <= columns for line in lines))
                    for label in (r"Codex +7d", r"Claude +5h", r"Claude +7d", r"Fable +7d", r"Extra +7d"):
                        self.assertTrue(any(usage.re.match(label, line) for line in lines), label)
        full = self._draw(100, 24)
        self.assertNotIn("7d Fable", full)
        for text in ("resets left", "Team agents", "Codex   5h"):
            self.assertIn(text, full)
        compact = self._draw(40, 24)  # narrow: compact rows with the team summary folded into one line
        self.assertIn("team 0 runs", compact)
        self.assertTrue(all(len(line) <= 40 for line in compact.splitlines()))


if __name__ == "__main__":
    unittest.main()
