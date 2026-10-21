"""`team tokens` log parsing, Claude/Codex launch flags that keep MCP/skills out of read-only stages, diff summary and prompt prefix
stability. Run with python3 -I."""
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_skills as ts  # noqa: E402  (loads team.py once and gives the shared config)

team, teamcfg = ts.team, ts.teamcfg
import tokens  # noqa: E402

CLAUDE = [
    {"type": "system", "subtype": "init"},
    {"type": "assistant", "message": {"id": "m1", "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/a"}}],
                                      "usage": {"input_tokens": 2, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 0, "output_tokens": 5}}},
    {"type": "assistant", "message": {"id": "m2", "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/a"}}],
                                      "usage": {"input_tokens": 2, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 100, "output_tokens": 7}}},
]
RESULT = {"type": "result", "total_cost_usd": 0.5, "duration_ms": 60000, "num_turns": 3,
          "usage": {"input_tokens": 4, "cache_creation_input_tokens": 110, "cache_read_input_tokens": 100, "output_tokens": 12}}


def write(path, events, junk=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) for e in events]
    path.write_text("\n".join(lines + (["2026-01-01 ERROR not json"] if junk else [])) + "\n")


class Tokens(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)

    def test_claude_result_codex_turns_and_cut_off_run(self):
        write(self.d / "t001/logs/01-implement-mid.jsonl", CLAUDE + [RESULT])
        write(self.d / "t001/logs/02-review-architect.jsonl", CLAUDE)  # no result event: summed from assistant messages
        write(self.d / "t002/logs/01-implement-mid.jsonl", [
            {"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 900, "output_tokens": 50}},
            {"type": "turn.completed", "usage": {"input_tokens": 2000, "cached_input_tokens": 1500, "output_tokens": 10}}])
        (self.d / "t001/state.json").write_text(json.dumps({"plan_rounds": 1, "review_rounds": 2, "impl_fails": 2, "status": "done"}))
        rows = {(r["task"], r["n"]): r for r in tokens.collect(self.d)}
        a, b, c = rows[("t001", 1)], rows[("t001", 2)], rows[("t002", 1)]
        self.assertEqual((a["fresh"], a["written"], a["cached"], a["out"], a["cost"], a["complete"]), (4, 110, 100, 12, 0.5, True))
        self.assertEqual(a["rereads"], 1)
        self.assertFalse(b["complete"])
        self.assertEqual((b["fresh"], b["written"], b["cached"], b["out"], b["turns"]), (4, 110, 100, 12, 2))
        self.assertEqual((c["cli"], c["fresh"], c["cached"], c["out"], c["cost"]), ("codex", 600, 2400, 60, None))
        self.assertEqual(tokens.quality(self.d)["t001"]["review_rounds"], 2)
        self.assertEqual([r["task"] for r in tokens.collect(self.d, {"t002"})], ["t002"])

    def test_report_survives_empty_and_garbled_logs(self):
        self.assertEqual(tokens.report(self.d), ["No stage logs yet."])
        (self.d / "t003/logs").mkdir(parents=True)
        (self.d / "t003/logs/01-plan-mid.jsonl").write_text("garbage\n\n{broken\n")
        (self.d / "t003/logs/notes.jsonl").write_text("x")  # not a stage log
        out = "\n".join(tokens.report(self.d, detail=True))
        self.assertIn("plan", out)
        self.assertIn("runs cut off (no result) 1", out)


class Flags(unittest.TestCase):
    def init(self, agents=""):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        (d / "team.toml").write_text(ts.CONFIG + ts.ROLES + agents)
        team.CFG = None
        team.init(d / "team.toml")
        return d

    def test_defaults_drop_mcp_for_read_only_and_user_skills_everywhere(self):
        self.init()
        ro, rw = team.agent_cmd("claude", "m", "low", True, "o"), team.agent_cmd("claude", "m", "low", False, "o")
        self.assertIn("--strict-mcp-config", ro)
        self.assertNotIn("--strict-mcp-config", rw)
        self.assertIn("--disable-slash-commands", ro + rw)
        self.assertIn("Read,Glob,Grep", ro)  # the read-only tool list is unchanged

    def test_config_switches(self):
        d = self.init()
        cfg = (d / "team.toml").read_text()
        for mcp, rw_flag in (("none", True), ("all", False)):
            (d / "team.toml").write_text(cfg + f'\n[agents]\nmcp = "{mcp}"\nuser_skills = true\n')
            team.CFG = None
            team.init(d / "team.toml")
            ro, rw = team.agent_cmd("claude", "m", "low", True, "o"), team.agent_cmd("claude", "m", "low", False, "o")
            self.assertEqual("--strict-mcp-config" in rw, rw_flag)
            self.assertEqual("--strict-mcp-config" in ro, mcp == "none")
            self.assertNotIn("--disable-slash-commands", ro)

    def test_codex_read_only_stages_disable_mcp(self):
        d = self.init()
        home = d / "codex_home"
        home.mkdir()
        (home / "config.toml").write_text('[mcp_servers.my-srv]\ncommand = "x"\n[mcp_servers.other]\nurl = "http://h"\n')
        with unittest.mock.patch.dict("os.environ", {"CODEX_HOME": str(home)}):
            ro, rw = team.agent_cmd("codex", "m", "low", True, "o"), team.agent_cmd("codex", "m", "low", False, "o")
        for arg in ("mcp_servers.my-srv.enabled=false", "mcp_servers.other.enabled=false", "features.apps=false"):
            self.assertIn(arg, ro)
            self.assertNotIn(arg, rw)

    def test_bad_mcp_mode_is_refused(self):
        d = self.init()
        (d / "team.toml").write_text((d / "team.toml").read_text() + '\n[agents]\nmcp = "some"\n')
        with self.assertRaisesRegex(ValueError, "mcp must be one of"):
            teamcfg.load(d / "team.toml")


class Prompts(unittest.TestCase):
    def test_diff_summary_git_and_p4(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "changes.diff"
            p.write_text("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n-old\n+new\n+more\n"
                         "==== //depot/y.cpp#3 - /ws/y.cpp ====\n+a\n-b\n-c\n")
            self.assertEqual(team.diff_summary(p), "- x.py +2 -1\n- //depot/y.cpp +1 -2")
            self.assertEqual(team.diff_summary(Path(tmp) / "none.diff"), "")
            self.assertIn("... 1 more", team.diff_summary(p, limit=1))

    def test_prefix_is_identical_across_tasks_and_review_lists_changed_files(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        (d / "team.toml").write_text(ts.CONFIG + ts.ROLES)
        team.CFG = None
        team.init(d / "team.toml")
        a, b = (team.load(team.create_task(r)["id"]) for r in ("first", "second"))
        pa, pb = team.build_prompt(a, "implement", "mid"), team.build_prompt(b, "implement", "mid")
        cut = lambda s, p: p[:p.index("Task " + s["id"])]  # noqa: E731  (everything before the per-task line)
        self.assertEqual(cut(a, pa), cut(b, pb))
        self.assertNotIn("## Changed files", pa)
        (team.task_dir(a["id"]) / "changes.diff").write_text("diff --git a/q b/q\n+1\n")
        self.assertIn("- q +1 -0", team.build_prompt(a, "review", "architect"))
        self.assertNotIn("## Changed files", team.build_prompt(a, "plan_review", "director"))


if __name__ == "__main__":
    unittest.main()
