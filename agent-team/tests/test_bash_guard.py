"""Claude Bash hook for team runs: kill by PID is allowed, kill by name, pattern, or process group is denied."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
from bash_guard import denied  # noqa: E402

ALLOW = ["kill 12345", "kill -9 12345", "kill $MYPID", 'kill "$(cat job.pid)"', "pgrep -x node", "ps aux | grep foo",
         "echo skill", "setsid nohup x & echo $! > job.pid", "pgrep -x node; kill 12345", "kill -TERM 12345",
         "kill -s KILL 12345", "kill -- 12345", "kill %1", "kill $(cat job.pid)", "kill -9 $MYPID", "kill -0 12345",
         "taskkill /PID 1234 /T /F", "Stop-Process -Id 1234"]
DENY = ["pkill python3", "pkill -f blender", "killall -9 node", "sudo pkill x", "pgrep -x python3 | xargs -r kill",
        "ps aux | grep blender | awk '{print $2}' | xargs kill -9", "kill $(pgrep -x python3)", "kill `pidof zellij`",
        "fuser -k 8000/tcp", "lsof -t -i:8000 | xargs kill", "true && pkill x", "P=$(pgrep -x python3); kill $P",
        "MYPID=$(pgrep -x python3) && kill $MYPID", "for p in $(pgrep blender); do kill $p; done",
        # PID <= 0 or a process group
        "kill -9 -1", "kill -1", "kill 0", "kill -9 0", "kill -- -1234", "kill -9 -- -1234", "kill -s KILL -1",
        "kill -KILL -1", "true; kill -9 -1", "/usr/bin/kill -9 -1", "kill '-1'",
        # the pgrep and the kill in one string but not one segment
        "pgrep -x python3 | while read p; do kill $p; done", "pgrep x > f; kill $(cat f)",
        "pgrep -x python3 > p.txt\nkill -9 $(cat p.txt)", "lsof -t -i:8000 > f && kill $(< f)",
        "pgrep -x x; kill $MYPID", "xargs kill < pids.txt",
        # full paths and wrappers
        "/run/current-system/sw/bin/pkill -f blender", "/usr/bin/killall node", "command pkill x",
        # Windows
        "taskkill /IM node.exe /F", "taskkill //F //IM node.exe", "Stop-Process -Name node",
        "Get-Process node | Stop-Process"]


class BashGuard(unittest.TestCase):
    def test_lists(self):
        self.assertEqual([c for c in ALLOW if denied(c)], [])
        self.assertEqual([c for c in DENY if not denied(c)], [])

    def test_hook_exit_codes(self):
        def run(cmd):
            return subprocess.run([sys.executable, "-I", str(ROOT / "hooks/bash_guard.py")], capture_output=True,
                                  text=True, input=json.dumps({"tool_input": {"command": cmd}}), timeout=10)
        r = run("pkill -f node")
        self.assertEqual(r.returncode, 2)
        self.assertIn("recorded", r.stderr)
        self.assertEqual(run("kill 12345").returncode, 0)


if __name__ == "__main__":
    unittest.main()
