"""Agent-level skills (`skill: name | path | when` in agent frontmatter) and the "Skills you have" prompt table. Run with python3 -I."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_skills as ts  # noqa: E402  (loads team.py once and gives the shared config)

team, teamcfg = ts.team, ts.teamcfg


def agent(name, *skill, extra=""):
    lines = "".join(f"skill: {s}\n" for s in skill)
    return f"---\nname: {name}\nscope: s\n{extra}{lines}---\nBody.\n"


class AgentSkills(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "tpl/agents").mkdir(parents=True)
        (self.d / "tpl/skills").mkdir()
        (self.d / "tpl/skills/mine.md").write_text("# Mine\n- step\n")
        (self.d / "team.toml").write_text(ts.CONFIG + ts.ROLES)

    def put(self, name, *skill, extra=""):
        (self.d / f"tpl/agents/{name}.md").write_text(agent(name, *skill, extra=extra))

    def load(self):
        return teamcfg.load(self.d / "team.toml")

    def bad(self, msg):
        with self.assertRaisesRegex(ValueError, msg):
            self.load()

    def init(self):
        team.CFG = None
        team.init(self.d / "team.toml")

    def test_table_lists_paths_not_content(self):
        self.put("mid", "mine | ../skills/mine.md | when X", "other | ../skills/mine.md | when Y # 12")
        self.init()
        text = team.build_prompt(team.load(team.create_task("do it")["id"]), "implement", "mid")
        path = str((self.d / "tpl/skills/mine.md").resolve())
        self.assertIn("## Skills you have", text)
        self.assertIn(f"- mine | {path} | when X", text)
        self.assertIn("when Y # 12", text)  # `#` survives
        self.assertNotIn("- step", text)  # not inlined

    def test_no_skills_no_table_and_route_skips_it(self):
        self.init()
        s = team.load(team.create_task("do it")["id"])
        self.assertNotIn("Skills you have", team.build_prompt(s, "implement", "mid"))
        self.put("producer", "mine | ../skills/mine.md | w")
        self.init()
        self.assertNotIn("Skills you have", team.build_prompt(s, "route", "producer"))
        self.assertNotIn("Skills you have", team.build_prompt(s, "refill", "producer"))

    def test_errors(self):
        cases = {"file not found": "x | ../skills/none.md | w", "3 non-empty": "x | ../skills/mine.md",
                 "3 non-empty ": "x | ../skills/mine.md | ", "must be": "X | ../skills/mine.md | w"}
        for msg, line in cases.items():
            with self.subTest(line):
                self.put("mid", line)
                self.bad(msg.strip())
        (self.d / "tpl/skills/empty.md").write_text("  \n")
        self.put("mid", "e | ../skills/empty.md | w")
        self.bad("not found or empty")

    def test_pin_and_model_next_to_skill(self):
        self.put("mid", "mine | ../skills/mine.md | w", extra="model: m1\npin: true\n")
        a = self.load()["agent_defs"]["mid"]
        self.assertEqual((a["model"], a["pinned"], len(a["skills"])), ("m1", True, 1))

    def test_dedupe_with_task_skill(self):
        self.put("mid", "mine | ../skills/mine.md | w", "keep | ../skills/mine.md | w2", "tdd | ../skills/tdd.md | w3")
        (self.d / "tpl/skills/tdd.md").write_text("# tdd\n")
        self.init()
        by_name = team.agent_skills_table("mid", [("mine", "x")])
        self.assertNotIn("- mine |", by_name)
        self.assertNotIn("- keep |", by_name)  # same file as the task skill
        self.assertIn("- tdd |", by_name)
        self.assertEqual(team.agent_skills_table("mid", [("mine", ""), ("tdd", "")]), "")

    def test_copied_agent_still_loads(self):
        shutil.copy(ROOT / "templates/agents/technical_artist.md", self.d / "tpl/agents")
        a = self.load()["agent_defs"]["technical_artist"]
        self.assertTrue(a["skills"] and all(Path(k["path"]).is_file() for k in a["skills"]))

    def test_legacy_role_has_no_table(self):
        (self.d / "tpl/roles").mkdir()
        (self.d / "tpl/roles/mid.md").write_text("Legacy.")
        self.init()
        self.assertNotIn("Skills you have", team.build_prompt(team.load(team.create_task("do it")["id"]), "implement", "mid"))

    def test_bundled_skills_resolve(self):
        defs = self.load()["agent_defs"]
        want = {"technical_artist": "material-authoring", "engine": "optimization", "gameplay": "animation", "designer": "level-design"}
        for ag, sk in want.items():
            self.assertIn(sk, [k["name"] for k in defs[ag]["skills"]], ag)
        for a in defs.values():
            for k in a.get("skills", []):
                self.assertTrue(Path(k["path"]).read_text().strip(), k)
                self.assertTrue(k["when"])


if __name__ == "__main__":
    unittest.main()
