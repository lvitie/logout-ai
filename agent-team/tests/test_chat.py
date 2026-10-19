"""Coordinator CLI routing without real agents or network calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
                config = (ROOT / 'templates/team.toml').read_text().replace('cli = "claude"', f'cli = "{cli}"')
                (project / 'team.toml').write_text(config)
                for name in ('claude', 'codex'):
                    path = fake / name
                    path.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                                    'print(json.dumps({"cli": os.path.basename(sys.argv[0]), '
                                    '"args": sys.argv[1:], "cwd": os.getcwd()}))\nsys.exit(23)\n')
                    path.chmod(0o755)
                env = dict(os.environ, PATH=f'{fake}:{os.environ["PATH"]}',
                           TEAM_CONFIG=str(project / 'team.toml'))
                result = subprocess.run(['bash', str(ROOT / 'chat'), 'request with spaces'],
                                        cwd=root, env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 23, result.stderr)
                record = json.loads(result.stdout)
                self.assertEqual(record['cli'], cli)
                self.assertEqual(record['cwd'], str(project))
                self.assertEqual(record['args'][-1], 'request with spaces')
                self.assertIn('claude-sonnet-5-5', record['args'])
                if cli == 'codex':
                    options = dict(arg.split('=', 1) for arg in record['args'] if '=' in arg)
                    self.assertEqual(json.loads(options['model_reasoning_effort']), 'low')
                    prompt = json.loads(options['developer_instructions'])
                else:
                    self.assertIn('--effort', record['args'])
                    prompt = record['args'][record['args'].index('--append-system-prompt') + 1]
                self.assertIn('myproject agent team', prompt)
                self.assertIn('team new', prompt)

    def test_invalid_config_does_not_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(['bash', str(ROOT / 'chat')],
                                    env=dict(os.environ, TEAM_CONFIG=str(Path(tmp) / 'missing.toml')),
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('FileNotFoundError', result.stderr)
