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




if __name__ == "__main__":
    unittest.main()
