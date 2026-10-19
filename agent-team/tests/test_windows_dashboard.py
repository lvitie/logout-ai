"""Windows Terminal argument and pane startup contracts without launching a UI."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import windows_dashboard


class WindowsDashboardTests(unittest.TestCase):
    def test_console_commands_preserve_paths_and_cover_all_panels(self):
        cfg = {'root': r'C:\Projects\Mesh & Tools', 'config_path': r'C:\Projects\Mesh & Tools\team.toml',
               'project': {'name': 'Mesh'}}
        args = windows_dashboard.command(cfg, r'C:\Windows Apps\wt.exe', r'C:\Python Tools\python.exe')
        self.assertEqual(args[:4], [r'C:\Windows Apps\wt.exe', '--window', '-1', '--maximized'])
        chunks = []
        for value in args[4:]:
            if not chunks or value == ';':
                chunks.append([])
            if value != ';':
                chunks[-1].append(value)
        panels = [c for c in chunks if c[0] in ('new-tab', 'split-pane')]
        self.assertEqual([c[0] for c in panels], ['new-tab'] + ['split-pane'] * 5)
        self.assertEqual([c[-1] for c in panels], ['usage', 'alerts', 'tasks', 'coordinator', 'live-log', 'focus'])
        for pane in panels:
            self.assertIn(str(cfg['root']), pane)
            self.assertIn(r'C:\Python Tools\python.exe', pane)
            self.assertEqual(pane[-2], cfg['config_path'])
        self.assertEqual(chunks[-3:], [['move-focus', 'right'], ['move-focus', 'down'], ['move-focus', 'down']])

    def test_pane_binds_project_and_runs_known_script_in_current_console(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {'root': Path(tmp), 'config_path': str(Path(tmp) / 'team.toml')}
            try:
                with mock.patch.object(windows_dashboard.teamcfg, 'load', return_value=cfg), \
                     mock.patch.object(windows_dashboard.runpy, 'run_path') as run, \
                     mock.patch.dict(os.environ), mock.patch.object(sys, 'argv', ['wrapper']):
                    windows_dashboard.pane(cfg['config_path'], 'coordinator')
                    self.assertEqual(os.getcwd(), tmp)
                    self.assertEqual(os.environ['TEAM_CONFIG'], cfg['config_path'])
                    self.assertTrue(os.environ['PATH'].startswith(str(ROOT / 'bin') + os.pathsep))
                    run.assert_called_once_with(str(ROOT / 'chat'), run_name='__main__')
                    self.assertEqual(sys.argv, [str(ROOT / 'chat')])
            finally:
                os.chdir(original_cwd)

    def test_unknown_pane_rejected_before_loading(self):
        with mock.patch.object(windows_dashboard.teamcfg, 'load') as load:
            with self.assertRaisesRegex(SystemExit, 'Unknown dashboard pane'):
                windows_dashboard.pane('missing.toml', '../untrusted.py')
            load.assert_not_called()

    def test_resolves_app_alias_to_installed_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / 'Terminal Package' / 'WindowsTerminal.exe'
            executable.parent.mkdir()
            executable.touch()
            alias = root / 'WindowsApps' / 'wt.exe'
            with mock.patch.object(windows_dashboard.shutil, 'which', side_effect=[str(alias), 'powershell.exe']), \
                 mock.patch.object(windows_dashboard.subprocess, 'run', return_value=mock.Mock(
                     returncode=0, stdout=str(executable.parent) + '\n')):
                self.assertEqual(windows_dashboard.terminal_executable(), str(executable))

    def test_portable_terminal_does_not_query_app_package(self):
        with mock.patch.object(windows_dashboard.shutil, 'which', return_value='/portable/wt.exe'), \
             mock.patch.object(windows_dashboard.subprocess, 'run') as run:
            self.assertEqual(windows_dashboard.terminal_executable(), '/portable/wt.exe')
            run.assert_not_called()

    def test_unresolved_alias_reports_failure(self):
        with mock.patch.object(windows_dashboard.shutil, 'which', side_effect=['/WindowsApps/wt.exe', None, None]):
            with self.assertRaisesRegex(SystemExit, 'cannot resolve Windows Terminal'):
                windows_dashboard.terminal_executable()
