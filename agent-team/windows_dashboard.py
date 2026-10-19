"""Native Windows Terminal dashboard: each pane gets its own ConPTY console."""
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import teamcfg

HERE = Path(__file__).resolve().parent
PANES = {"coordinator": "chat", "focus": "focus_tui", "live-log": "log_tui",
         "alerts": "notifier", "usage": "usage_tui", "tasks": "tasks_tui"}


def terminal_executable():
    terminal = shutil.which("wt.exe")
    if not terminal or Path(terminal).parent.name.lower() != "windowsapps":
        return terminal
    # App-execution aliases can return success without starting a window from a WSL-launched process.
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if shell:
        result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command",
                                 "(Get-AppxPackage Microsoft.WindowsTerminal).InstallLocation"],
                                capture_output=True, text=True, timeout=15)
        location = result.stdout.strip()
        if result.returncode == 0 and location:
            executable = Path(location) / "WindowsTerminal.exe"
            if executable.is_file():
                return str(executable)
    raise SystemExit("team-up: cannot resolve Windows Terminal's installed executable; repair its installation")


def command(cfg, terminal, python):
    """Build argv directly; no cmd.exe/PowerShell parsing of project paths or arguments."""
    root, config = str(cfg["root"]), cfg["config_path"]

    def pane(kind, title, *split):
        return [kind, *split, "--title", f"{cfg['project']['name']} | {title}", "--suppressApplicationTitle", "-d", root,
                python, "-X", "utf8", str(HERE / "windows_dashboard.py"), config, title]

    # Match the Linux dashboard: usage/focus and log on the left, alerts/tasks/chat on the right.
    result = [terminal, "--window", "-1", "--maximized"]
    for args in (pane("new-tab", "usage"),
                 pane("split-pane", "alerts", "-V", "-s", "0.45"),
                 pane("split-pane", "tasks", "-H", "-s", "0.88"),
                 pane("split-pane", "coordinator", "-H", "-s", "0.6"),
                 ["move-focus", "left"],
                 pane("split-pane", "live-log", "-H", "-s", "0.72"),
                 ["move-focus", "up"],
                 pane("split-pane", "focus", "-V", "-s", "0.42")):
        if len(result) > 4:
            result.append(";")
        result.extend(args)
    result.extend([";", "move-focus", "right", ";", "move-focus", "down", ";", "move-focus", "down"])
    return result


def pane(config, name):
    if name not in PANES:
        raise SystemExit(f"Unknown dashboard pane: {name}")
    cfg = teamcfg.load(config)
    os.environ["TEAM_CONFIG"] = cfg["config_path"]
    paths = [str(HERE / "bin"), str(Path.home() / ".local/bin")]
    if os.name == "nt":
        import winreg
        # An already-open Windows Terminal can have a stale PATH after installing Node/npm.
        for hive, key in ((winreg.HKEY_CURRENT_USER, "Environment"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    paths.append(os.path.expandvars(winreg.QueryValueEx(handle, "Path")[0]))
            except OSError:
                pass
    paths.append(os.environ.get("PATH", ""))
    os.environ["PATH"] = os.pathsep.join(paths)
    os.chdir(cfg["root"])
    sys.argv = [str(HERE / PANES[name])]
    if name == "live-log":
        print(f"{cfg['project']['name']} - live log\nWaiting for team activity...", flush=True)
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: windows_dashboard.py CONFIG PANE")
    pane(sys.argv[1], sys.argv[2])
