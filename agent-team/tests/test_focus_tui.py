"""Focus panel on a fixture state dir: no team runs, no VCS calls, no network. Run with python3 -I."""
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import team  # noqa: E402
import teamcfg  # noqa: E402

loader = importlib.machinery.SourceFileLoader("focus_tui", str(ROOT / "focus_tui"))
spec = importlib.util.spec_from_loader(loader.name, loader)
focus = importlib.util.module_from_spec(spec)
loader.exec_module(focus)

NOW = time.mktime((2026, 10, 18, 17, 0, 0, 0, 0, -1))
from cfgutil import TOML  # noqa: E402


def plain(lines):
    return "\n".join(re.sub(r"\033\[[0-9;]*m", "", ln) for ln in lines)


class FocusTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.proj = Path(tmp.name)
        env = {k: os.environ.get(k) for k in ("CODEX_HOME", "XDG_STATE_HOME", "TEAM_CONFIG")}
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in env.items()])
        os.environ.update(CODEX_HOME=str(self.proj / "codex"), XDG_STATE_HOME=str(self.proj / "xdg"))
        (self.proj / "team.toml").write_text(TOML.replace('name = "myproject"', 'name = "demo"'))
        (self.proj / "TASKS.md").write_text("## Current phase\n\nShip the save system.\n\n## Tasks\n\n"
                                            "- [ ] Approve the art style\n  Owner: user\n- [ ] Write loader\n")
        team.init(self.proj / "team.toml")
        self.runs = team.RUNS
        self.task("t001", status="running", route="simple", stage=0, review_rounds=1, title="hook fix",
                  created=NOW - 3600, stage_started=NOW - 600)
        self.write("t001/logs/01-implement-senior.prompt.md", "")
        self.write("t001/logs/01-implement-senior.jsonl", json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "checking\nthe diff"}]}}) + "\n")
        os.utime(self.runs / "t001/logs/01-implement-senior.prompt.md", (NOW - 590, NOW - 590))
        self.write("role_override.json", json.dumps({"t001": {"implement": "senior"}}))
        self.task("t002", status="running", route="simple", stage=1, title="crashed one", stage_started=NOW - 60)
        self.task("t003", status="gate", route="complex", stage=1, title="combat", reason="Architect: pick a format")
        self.write("t004/state.json", '{"id": "t004", "status": "runn')  # corrupt
        (self.runs / "t005").mkdir()  # no state.json: not a task
        self.task("t006", status="new", title="queued work")
        self.write("lease-editor.json", json.dumps({"task": "t001", "stage": "02-implement-mid", "owner": "agent"}))
        self.task("t007", status="done", title="finished today", finished=NOW - 900)
        self.task("t008", status="done", title="yesterday", finished=NOW - 86400)

    def write(self, rel, text):
        p = self.runs / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def task(self, tid, **kw):
        self.write(f"{tid}/state.json", json.dumps({"id": tid, "change": tid, "request": kw.get("title", ""),
                                                    "res": ["editor"], **kw}))

    def test_frame_sections(self):
        text = plain(focus.frame(NOW, 140, 60, pending=["work"], running_ids={"t001"}))
        self.assertIn("FOCUS Ship the save system.", text)
        self.assertRegex(text, r"t001 +hook fix .*editor .*implement +mid→senior ov .* r2/3 10m/1h00m t001")
        self.assertIn("checking the diff", text)
        self.assertIn("running 1/3", text)
        self.assertIn("editor:t001", text)
        self.assertRegex(text, r"t002 +stale .*team run t002")
        self.assertRegex(text, r"t003 +gate +Architect: pick a format")
        self.assertRegex(text, r"t004 +corrupt")
        self.assertNotIn("t005", text)
        self.assertIn("you       Approve the art style", text)
        self.assertNotIn("Write loader", text)
        self.assertIn("pending: work", text)
        self.assertRegex(text, r"1\. t006 +queued work  ready, not started")
        self.assertIn("finished today", text)
        self.assertNotIn("yesterday", text)

    def test_short_and_narrow_panes(self):
        lines = focus.frame(NOW, 60, 8, pending=None, err="p4 not found", running_ids={"t001"})
        self.assertLessEqual(len(lines), 8)
        text = plain(lines)
        self.assertIn("RUNNING", text)
        self.assertRegex(text, r"NEEDS YOU \d+ · QUEUE 1 · DONE 1")
        self.assertIn("pending check unavailable", text)
        self.assertTrue(all(len(ln) <= 60 for ln in text.splitlines()))

    def test_latest_launch_gives_agent_model_and_effort(self):
        self.task("t009", status="running", route="simple", domain="code", stage=0, title="pinned", stage_started=NOW - 60,
                  launches=[{"stem": "01-implement-qa_bot", "agent": "qa_bot", "profile": "mid", "cli": "claude",
                             "model": "pin-model", "effort": "xhigh"}])
        self.write("t009/logs/01-implement-qa_bot.prompt.md", "")
        os.utime(self.runs / "t009/logs/01-implement-qa_bot.prompt.md", (NOW - 30, NOW - 30))
        s = {**json.loads((self.runs / "t009/state.json").read_text()), "dir": self.runs / "t009"}
        self.assertEqual(focus.stage_info(s, NOW), ("implement", "mid", "qa_bot", "xhigh"))
        self.assertIn("mid→qa_bot", plain(focus.frame(NOW, 140, 60, pending=[], running_ids={"t009"})))
        self.assertIn("pin-model", plain(focus.frame(NOW, 140, 60, pending=[], running_ids={"t009"})))

    def test_run_lock_probe(self):
        d = self.runs / "t001"
        self.assertFalse(focus.holds_run_lock(d))
        with (d / ".lock-run").open("a") as held:
            teamcfg.lock(held, blocking=False)
            self.assertTrue(focus.holds_run_lock(d))
            self.assertIn("hook fix", plain(focus.frame(NOW, 140, 60, pending=[])).split("RESOURCES")[0])
        self.assertRegex(plain(focus.frame(NOW, 140, 60, pending=[])), r"t001 +stale")


if __name__ == "__main__":
    unittest.main()
