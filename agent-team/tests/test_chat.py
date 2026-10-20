"""Coordinator CLI routing without real agents or network calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cfgutil import config_text

ROOT = Path(__file__).resolve().parents[1]


class ChatTests(unittest.TestCase):
    def test_configured_cli_and_prompt(self):
        for cli in ('claude', 'codex'):
            with self.subTest(cli=cli), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project = root / 'project with spaces'
                project.mkdir()
                fake = root / 'bin'
                fake.mkdir()
                config = config_text(cli)
                (project / 'team.toml').write_text(config)
                for name in ('claude', 'codex'):
                    path = fake / name
                    path.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                                    'print(json.dumps({"cli": os.path.basename(sys.argv[0]), '
                                    '"args": sys.argv[1:], "cwd": os.getcwd()}))\nsys.exit(23)\n')
                    path.chmod(0o755)
                env = dict(os.environ, PATH=f'{fake}:{os.environ["PATH"]}',
                           TEAM_CONFIG=str(project / 'team.toml'))
                result = subprocess.run([sys.executable, str(ROOT / 'chat'), 'request with spaces'],
                                        cwd=root, env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 23, result.stderr)
                record = json.loads(result.stdout)
                self.assertEqual(record['cli'], cli)
                self.assertEqual(record['cwd'], str(project))
                self.assertEqual(record['args'][-1], 'request with spaces')
                self.assertIn({'claude': 'claude-sonnet-5-5', 'codex': 'gpt-6.1-sol'}[cli], record['args'])
                if cli == 'codex':
                    self.assertEqual(record['args'][:2], ['-s', 'danger-full-access'])  # `team` needs it
                    options = dict(arg.split('=', 1) for arg in record['args'] if '=' in arg)
                    self.assertEqual(json.loads(options['model_reasoning_effort']), 'low')
                    prompt = json.loads(options['developer_instructions'])
                else:
                    self.assertIn('--effort', record['args'])
                    prompt = record['args'][record['args'].index('--append-system-prompt') + 1]
                self.assertIn('myproject agent team', prompt)
                self.assertIn('team new', prompt)
                skill = ROOT.parent / '.agents/skills/team-setup/SKILL.md'
                self.assertIn(str(skill), prompt)  # both CLIs reach the setup skill by path
                self.assertTrue(skill.is_file())
                self.assertIn(str(project / 'team.toml'), prompt)
                self.assertNotIn('{', prompt)
                self.assertIn('You have not ran `team-setup` in this workspace, do you want to do that now?', prompt)

    def test_no_setup_offer_after_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / 'bin'
            fake.mkdir()
            (root / 'team.toml').write_text(config_text()
                                            .replace('team_setup = ""', 'team_setup = "2026-10-19"'))
            (fake / 'claude').write_text(f'#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
            (fake / 'claude').chmod(0o755)
            env = dict(os.environ, PATH=f'{fake}:{os.environ["PATH"]}', TEAM_CONFIG=str(root / 'team.toml'))
            result = subprocess.run([sys.executable, str(ROOT / 'chat')], env=env, capture_output=True, text=True,
                                    timeout=15)
            args = json.loads(result.stdout)
            prompt = args[args.index('--append-system-prompt') + 1]
            self.assertNotIn('You have not ran `team-setup`', prompt)

    def test_invalid_config_does_not_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / 'chat')],
                                    env=dict(os.environ, TEAM_CONFIG=str(Path(tmp) / 'missing.toml')),
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('FileNotFoundError', result.stderr)
