"""Launcher startup and package-manager paths with fake installs and dashboard."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from cfgutil import config_text

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def run_launcher(self, missing=False, fail=False, missing_cli=False, bad_checksum=False, cli_fail=False,
                     architecture='x86_64', args=(), vcs='git', missing_git=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / 'project with spaces'
            project.mkdir()
            fake = root / 'bin'
            fake.mkdir()
            launcher = (ROOT / 'templates/team.sh').read_text().replace('@@LOGOUT_AI_ROOT@@', shlex.quote(str(ROOT.parent)))
            (project / 'team.sh').write_text(launcher)
            (project / 'team.toml').write_text(config_text('codex', vcs))
            log = root / 'calls'
            (fake / 'codex').write_text('#!/bin/sh\nexit 99\n')
            (fake / 'codex').chmod(0o755)
            (fake / 'zellij').write_text('#!/bin/sh\nprintf "zellij %s\\n" "$*" >> "$MOCK_LOG"\n'
                                        'case "$1" in list-sessions) exit 1;; esac\n')
            (fake / 'zellij').chmod(0o755)
            (fake / 'node').write_text('#!/bin/sh\nexit 0\n')  # the launcher installs nodejs when node is missing
            (fake / 'node').chmod(0o755)
            harness = r'''
command() {
  if [[ $1 == -v && $2 == zellij && $MOCK_MISSING == 1 && ! -x $HOME/.local/bin/zellij ]]; then
    return 1
  fi
  if [[ $1 == -v && $2 == codex && $MOCK_CLI_MISSING == 1 && ! -f $MOCK_CLI_READY ]]; then
    return 1
  fi
  if [[ $1 == -v && $2 == git && $MOCK_GIT_MISSING == 1 && ! -f $MOCK_READY ]]; then
    return 1
  fi
  builtin command "$@"
}
dnf() {
  printf 'dnf %s\n' "$*" >> "$MOCK_LOG"
  [[ $MOCK_FAIL == 0 ]] || return 19
  touch "$MOCK_READY"
}
sudo() { "$@"; }
npm() {
  printf 'npm %s\n' "$*" >> "$MOCK_LOG"
  [[ $MOCK_CLI_FAIL == 0 ]] || return 29
  touch "$MOCK_CLI_READY"
}
curl() {
  printf 'curl %s\n' "$*" >> "$MOCK_LOG"
  [[ $MOCK_FAIL == 0 ]] || return 19
}
sha256sum() {
  builtin command cat >> "$MOCK_LOG"
  [[ $MOCK_BAD_CHECKSUM == 0 ]] || return 1
}
tar() {
  builtin command cp "$MOCK_BIN/zellij" "$4/zellij"
}
uname() {
  if [[ $1 == -m ]]; then printf '%s\n' "$MOCK_ARCH"; else builtin command uname "$@"; fi
}
export -f command dnf sudo npm curl sha256sum tar uname
exec bash "$@"
'''
            env = dict(os.environ, HOME=str(root), PATH=f'{fake}:{os.environ["PATH"]}',
                       MOCK_LOG=str(log), MOCK_READY=str(root / 'ready'), MOCK_MISSING=str(int(missing)),
                       MOCK_BIN=str(fake), MOCK_BAD_CHECKSUM=str(int(bad_checksum)),
                       MOCK_CLI_MISSING=str(int(missing_cli)), MOCK_CLI_READY=str(root / 'cli-ready'),
                       MOCK_CLI_FAIL=str(int(cli_fail)), MOCK_GIT_MISSING=str(int(missing_git)),
                       MOCK_ARCH=architecture,
                       MOCK_FAIL=str(int(fail)), XDG_STATE_HOME=str(root / 'state'),
                       TEAM_CONFIG='/incorrect/config', LOGOUT_AI_ROOT=str(ROOT.parent))
            env.pop('ZELLIJ', None)
            result = subprocess.run(['bash', '-c', harness, 'harness', str(project / 'team.sh'), *args],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=20)
            calls = log.read_text() if log.exists() else ''
            layout = project / '.agent-team/team.kdl'
            return result, calls, layout.read_text() if layout.exists() else ''

    def test_start_without_installing(self):
        result, calls, layout = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('dnf', calls)
        self.assertIn('--session myproject-team', calls)
        self.assertIn(str(ROOT / 'chat'), layout)

    def test_start_without_vcs_does_not_need_git(self):
        for vcs in ('none', 'p4'):
            with self.subTest(vcs=vcs):
                result, calls, _ = self.run_launcher(vcs=vcs, missing_git=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('dnf', calls)
                self.assertIn('--session myproject-team', calls)
        result, calls, _ = self.run_launcher(missing_git=True)  # control: a git project installs missing git
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('dnf install -y git', calls)
        self.assertIn('--session myproject-team', calls)

    def test_install_missing_zellij(self):
        digests = {
            'x86_64': '40bcc2e03f5d5ae8e054e39f676081fe12ab70871506996ba595834c3718eefc',
            'aarch64': '05f0802afadd53f8db9514e7cae53c9ae8432fed1b35b8294aa816ee3044a16b',
        }
        for architecture, digest in digests.items():
            with self.subTest(architecture=architecture):
                result, calls, _ = self.run_launcher(missing=True, architecture=architecture)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'/v0.45.1/zellij-{architecture}-unknown-linux-musl.tar.gz', calls)
                self.assertIn(digest, calls)
                self.assertNotIn('dnf', calls)
                self.assertIn('--session myproject-team', calls)

    def test_install_failure_stops_launch(self):
        result, calls, _ = self.run_launcher(missing=True, fail=True)
        self.assertEqual(result.returncode, 19, result.stderr)
        self.assertNotIn('--session', calls)

    def test_help_does_not_install_or_launch(self):
        result, calls, _ = self.run_launcher(missing=True, args=('--help',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, '')
        self.assertIn('Usage:', result.stdout)

    def test_missing_cli_installs_for_user(self):
        result, calls, _ = self.run_launcher(missing_cli=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('npm install --global --prefix ', calls)
        self.assertIn('/.local @openai/codex', calls)
        self.assertNotIn('dnf', calls)
        self.assertIn('--session myproject-team', calls)

    def test_checksum_failure_stops_launch(self):
        result, calls, _ = self.run_launcher(missing=True, bad_checksum=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn('--session', calls)

    def test_cli_install_failure_stops_launch(self):
        result, calls, _ = self.run_launcher(missing_cli=True, cli_fail=True)
        self.assertEqual(result.returncode, 29, result.stderr)
        self.assertNotIn('--session', calls)
