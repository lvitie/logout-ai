#!/usr/bin/env python3
"""Claude hook for team runs: `pre` opens a tracked file in the task's change before an edit (VCS adapter
prepare_edit); `post` adds files a Write created. Config from $TEAM_CONFIG, change from $TEAM_CHANGE."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import teamcfg  # noqa: E402
import vcs  # noqa: E402

data = json.load(sys.stdin)
inp = data.get("tool_input", {})
path = inp.get("file_path") or inp.get("notebook_path")
change = os.environ.get("TEAM_CHANGE")
if not path or not change:
    sys.exit(0)
cfg = teamcfg.load()
f = Path(path).resolve()
if cfg["root"] not in f.parents:
    sys.exit(0)
adapter = vcs.make(cfg, os.environ.get(f"TEAM_REAL_{cfg['vcs']['kind'].upper()}"))
if sys.argv[1] == "pre":
    if f.exists():
        ok, msg = adapter.prepare_edit(f, change)
        if not ok:
            print(msg, file=sys.stderr)
            sys.exit(2)
elif sys.argv[1] == "post" and f.exists():
    adapter.add(f, change)
