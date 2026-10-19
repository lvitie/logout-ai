"""The original example config (examples/unreal-p4) still loads and yields the source project's pipelines."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import teamcfg  # noqa: E402


class Example(unittest.TestCase):
    def test_loads(self):
        cfg = teamcfg.load(ROOT.parent / "examples/unreal-p4/team.toml")
        self.assertEqual(cfg["vcs"]["kind"], "p4")
        import team
        team.init(ROOT.parent / "examples/unreal-p4/team.toml")
        self.assertEqual(team.pipeline("hard", "code")[-1], ("review", "director"))
        self.assertEqual(team.pipeline("simple", "level")[0], ("implement", "leveldesigner"))
        self.assertEqual(team.pipeline("custom:mid", "code"), [("implement", "mid"), ("review", "architect")])
        self.assertIn("Bash(p4 submit:*)", team.deny_rules())

    def test_codex_writer_reaches_p4_and_its_edits_join_the_changelist(self):
        import tempfile
        from unittest import mock
        import team
        team.init(ROOT.parent / "examples/unreal-p4/team.toml")
        net = "sandbox_workspace_write.network_access=true"
        self.assertIn(net, team.agent_cmd("codex", "m", "high", False, "out.md"))
        self.assertNotIn(net, team.agent_cmd("codex", "m", "high", True, "out.md"))
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp).resolve()
            (ws / "old.txt").write_text("x")
            (ws / "new.txt").write_text("y")
            vcs = mock.Mock()
            vcs.prepare_edit.return_value = vcs.add.return_value = (True, "")
            with mock.patch.object(team, "WS", ws), mock.patch.object(team, "VCS", vcs):
                team.track_codex_edits({"id": "t001", "change": "7"}, {"type": "item.completed", "item": {
                    "type": "file_change", "changes": [{"path": "old.txt", "kind": "update"},
                                                       {"path": "new.txt", "kind": "add"},
                                                       {"path": "../outside.txt", "kind": "update"}]}})
            vcs.prepare_edit.assert_called_once_with(ws / "old.txt", "7")
            self.assertEqual([c.args for c in vcs.add.call_args_list], [(ws / "old.txt", "7"), (ws / "new.txt", "7")])
            vcs.prepare_edit.return_value = (False, "p4 edit failed: locked by another client")
            with mock.patch.object(team, "WS", ws), mock.patch.object(team, "VCS", vcs):
                failed = team.track_codex_edits({"id": "t001", "change": "7"}, {"type": "item.completed", "item": {
                    "type": "file_change", "changes": [{"path": "old.txt", "kind": "update"}]}})
            self.assertEqual(failed, ["old.txt: p4 edit failed: locked by another client"])




if __name__ == "__main__":
    unittest.main()
