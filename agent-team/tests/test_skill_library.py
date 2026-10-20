"""Bundled game-dev skill library: skill file format, INDEX.md agrees with the agent frontmatter, every agent skill path
exists, the role doc covers every skill. Run with python3 -I."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import teamcfg  # noqa: E402

SKILLS_DIR = ROOT / "templates/skills"
HEADINGS = ["## When to use", "## Inputs", "## Method", "## Checks", "## Pitfalls", "## Engine notes"]
NEW_AGENTS = {"narrative": "design", "vfx": "technical_art", "ui": "gameplay"}


def skill_files():
    return sorted(p for p in SKILLS_DIR.glob("*.md") if teamcfg.SKILL_NAME.match(p.stem))


def bundled_agents():
    return teamcfg.load(ROOT / "templates/team.toml")["agent_defs"]


def index_rows():
    """skill -> set of agents from the INDEX.md table."""
    rows = {}
    for line in (SKILLS_DIR / "INDEX.md").read_text().splitlines():
        m = re.match(r"^\| `([a-z0-9_-]+)` \|[^|]*\|([^|]*)\|", line)
        if m:
            rows[m.group(1)] = {a.strip() for a in m.group(2).split(",") if a.strip()}
    return rows


class SkillFiles(unittest.TestCase):
    def test_count_and_unique_names(self):
        names = [p.stem for p in skill_files()]
        self.assertTrue(25 <= len(names) <= 45, len(names))
        self.assertEqual(len({n.lower() for n in names}), len(names))
        titles = [p.read_text().splitlines()[0] for p in skill_files()]
        self.assertEqual(len(set(titles)), len(titles), "skill titles must be unique")

    def test_sections_and_cap(self):
        for p in skill_files():
            with self.subTest(p.stem):
                text = p.read_text()
                lines = text.splitlines()
                self.assertRegex(lines[0], r"^# \S")
                heads = [ln for ln in lines if ln.startswith("## ")]
                self.assertEqual(heads, HEADINGS)
                for h in HEADINGS:
                    body = text.split(h + "\n", 1)[1].split("\n## ", 1)[0]
                    self.assertTrue(body.strip(), f"{h} is empty")
                self.assertIn("Unreal", text.split("## Engine notes", 1)[1])
                max_lines, max_words = (200, 1800) if p.stem.startswith("blender-") else (60, 450)
                self.assertLessEqual(len(lines), max_lines)
                self.assertLessEqual(len(text.split()), max_words)

    def test_scope_lines_name_real_skills(self):
        names = {p.stem for p in skill_files()}
        for p in skill_files():
            when = p.read_text().split("## When to use\n", 1)[1].split("\n## ", 1)[0]
            with self.subTest(p.stem):
                self.assertIn("- Not for:", when)
                refs = set(re.findall(r"`([a-z0-9_-]+)`", when.split("- Not for:", 1)[1]))
                self.assertTrue(refs, "the Not for line names no skill")
                self.assertLessEqual(refs, names)
                self.assertNotIn(p.stem, refs)

    def test_index_is_not_a_skill(self):
        cfg = teamcfg.load(ROOT / "templates/team.toml")
        self.assertTrue((SKILLS_DIR / "INDEX.md").is_file())
        self.assertNotIn("INDEX", teamcfg.list_skills(cfg))
        with self.assertRaisesRegex(ValueError, "bad skill name"):
            teamcfg.load_skill(cfg, "INDEX")


class AgentWiring(unittest.TestCase):
    def setUp(self):
        self.agents = bundled_agents()

    def test_agent_skill_paths_exist_and_names_unique(self):
        for name, a in self.agents.items():
            names = [k["name"] for k in a.get("skills", [])]
            self.assertEqual(len(names), len(set(names)), name)
            for k in a.get("skills", []):
                with self.subTest(agent=name, skill=k["name"]):
                    path = Path(k["path"])
                    self.assertTrue(path.is_file())
                    self.assertEqual(path.resolve(), (SKILLS_DIR / f"{k['name']}.md").resolve())

    def test_index_matches_frontmatter(self):
        want = {}
        for name, a in self.agents.items():
            for k in a.get("skills", []):
                want.setdefault(k["name"], set()).add(name)
        rows = index_rows()
        self.assertEqual(set(rows), {p.stem for p in skill_files()}, "every skill appears in INDEX.md, nothing else")
        for skill, agents in rows.items():
            with self.subTest(skill):
                self.assertTrue(agents, "every skill is held by at least one bundled agent")
                self.assertEqual(agents, want.get(skill, set()))

    def test_new_department_agents(self):
        cfg = teamcfg.load(ROOT / "templates/team.toml")
        R = cfg["routing"]
        for name, dom in NEW_AGENTS.items():
            with self.subTest(name):
                self.assertTrue((ROOT / f"templates/agents/{name}.md").is_file())
                a = self.agents[name]
                self.assertTrue(a["scope"] and a["instructions"] and a["skills"])
                self.assertFalse({"model", "effort", "pin"} & a.keys())
                self.assertIn(name, R["side_task_roles"])
                self.assertEqual(R["side_task_domains"][name], dom)

    def test_role_doc_covers_every_skill(self):
        doc = (ROOT.parent / "docs/GAME_DEV_ROLES.md").read_text()
        table = doc.split("## Role table", 1)[1].split("\n## ", 1)[0]
        for p in skill_files():
            self.assertIn(f"`{p.stem}`", table, p.stem)
        self.assertIn("## Sources", doc)
        self.assertIn("## Caveats", doc)


if __name__ == "__main__":
    unittest.main()
