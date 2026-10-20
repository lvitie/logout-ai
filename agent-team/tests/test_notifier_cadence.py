"""[notify] review_cadence: which done tasks open a review page. Pure helpers, no agents. Run with python3 -I."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import team  # noqa: E402
import teamcfg  # noqa: E402

from cfgutil import TOML  # noqa: E402
DAY1, DAY2 = "2026-10-20", "2026-10-21"
OPEN, SHUT = ("Phase 2", 1), ("Phase 2", 0)


class Cadence(unittest.TestCase):
    def run_pass(self, cadence, state, done, today=DAY1, phase=SHUT):
        return team.review_pass(cadence, state, set(done), today, phase)

    def test_invalid_value_falls_back_to_task(self):
        self.assertEqual(team.normalize_cadence("Daily "), ("daily", True))
        for bad in ("weekly", "", None):
            self.assertEqual(team.normalize_cadence(bad), ("task", False))

    def test_task_opens_each_done_task(self):
        st = {"known_done": ["t001"]}
        self.assertEqual(self.run_pass("task", st, ["t001", "t002"]), ["t002"])
        self.assertEqual(self.run_pass("task", st, ["t001", "t002", "t003"]), ["t003"])
        self.assertEqual(self.run_pass("task", st, ["t001", "t002", "t003"]), [])

    def test_milestone_waits_for_the_phase(self):
        st = {"known_done": []}
        self.assertEqual(self.run_pass("milestone", st, ["t001"], phase=OPEN), [])
        self.assertEqual(self.run_pass("milestone", st, ["t001", "t002"], phase=OPEN), [])
        self.assertEqual(self.run_pass("milestone", st, ["t001", "t002"], phase=SHUT), ["t001", "t002"])
        self.assertEqual(st["pending"], [])

    def test_milestone_opens_on_a_phase_change(self):
        st = {"known_done": []}
        self.assertEqual(self.run_pass("milestone", st, ["t001"], phase=OPEN), [])
        self.assertEqual(self.run_pass("milestone", st, ["t001"], phase=("Phase 3", 1)), ["t001"])
        self.assertEqual(st["phase"], "Phase 3")

    def test_task_finished_while_notifier_stopped_joins_the_milestone(self):
        st = {"known_done": ["t001"], "pending": []}  # saved by the notifier before it stopped
        self.assertEqual(self.run_pass("milestone", st, ["t001", "t002"], phase=OPEN), [])  # t002 finished while down
        self.assertEqual(self.run_pass("milestone", st, ["t001", "t002", "t003"], phase=SHUT), ["t002", "t003"])

    def test_missing_state_starts_from_current_done_tasks(self):
        st = {}
        self.assertEqual(self.run_pass("task", st, ["t001", "t002"]), [])
        self.assertEqual(st["known_done"], ["t001", "t002"])

    def test_missing_phase_behaves_like_task(self):
        st = {"known_done": []}
        self.assertEqual(self.run_pass("milestone", st, ["t001"], phase=None), ["t001"])
        st["phase"] = "Phase 2"
        self.run_pass("milestone", st, ["t001"], phase=None)
        self.assertEqual(st["phase"], "Phase 2")  # a half-saved file does not record a change

    def test_daily_opens_once_a_day(self):
        st = {"known_done": []}
        self.assertEqual(self.run_pass("daily", st, ["t001"]), ["t001"])
        self.assertEqual(self.run_pass("daily", st, ["t001", "t002"]), [])
        self.assertEqual(self.run_pass("daily", st, ["t001", "t002", "t003"], today=DAY2), ["t002", "t003"])

    def test_custom_never_opens(self):
        st = {"known_done": []}
        self.assertEqual(self.run_pass("custom", st, ["t001", "t002"]), [])
        self.assertEqual(self.run_pass("custom", st, ["t001", "t002"], phase=OPEN), [])
        self.assertEqual((st["known_done"], st["pending"]), (["t001", "t002"], []))
        self.assertEqual(self.run_pass("task", st, ["t001", "t002"]), [])  # a switch does not reopen reviewed tasks

    def test_current_phase_counts_open_items(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = {"root": root, "project": {"planning_file": "TASKS.md"}}
            self.assertIsNone(team.current_phase(cfg))  # missing file
            (root / "TASKS.md").write_text("# T\n\n## Other\n- [ ] x\n")
            self.assertIsNone(team.current_phase(cfg))  # no section
            (root / "TASKS.md").write_text(
                "# T\n\n## Current phase: Boot\n\n- [x] a\n- [ ] b\n- [ ] c (Owner: user)\n- [ ] d user-only\n"
                "\n## Next\n- [ ] later\n")
            self.assertEqual(team.current_phase(cfg), ("Current phase: Boot", 1))
            (root / "TASKS.md").write_text("## Current phase: Boot\n- [x] a\n## Next\n- [ ] later\n")
            self.assertEqual(team.current_phase(cfg), ("Current phase: Boot", 0))

    def test_config_default_and_set_flag(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "team.toml"
            p.write_text(TOML)
            n = teamcfg.load(p)["notify"]
            self.assertEqual((n["review_cadence"], n["review_cadence_set"]), ("task", False))
            p.write_text(TOML.replace('# review_cadence = "task"', 'review_cadence = "daily"'))
            n = teamcfg.load(p)["notify"]
            self.assertEqual((n["review_cadence"], n["review_cadence_set"]), ("daily", True))


if __name__ == "__main__":
    unittest.main()
