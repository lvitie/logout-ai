#!/usr/bin/env python3
"""Claude PreToolUse hook (Bash) for team runs: denies killing processes by name or pattern.
Allowed: `kill 12345`, `kill $MYPID`. Denied: pkill, killall (also by full path), fuser -k, xargs kill, taskkill /IM,
Stop-Process -Name or piped from Get-Process, kill of PID <= 0 or a process group (kill -9 -1, kill 0, kill -- -N),
and any command that mixes pgrep/pidof/ps/lsof with kill anywhere (pipes, loops, PID files) unless every kill target
is a literal PID."""
import json
import re
import sys

MSG = ("agent team: killing by process name or pattern is not allowed (it can kill the user's dashboard and editors). "
       "Kill only a PID you started in this task, recorded when you started it "
       "(`cmd & echo $! > job.pid`, then `kill $(cat job.pid)`). "
       "(Name mentions are blocked too, even in grep; put the name in a variable.)")


def _kill_targets(cmd):
    """Target list of every `kill` invocation, signal options removed."""
    for m in re.finditer(r"\bkill\b([^;&|\n)`]*)", cmd):
        toks = m.group(1).split()
        if toks[:1] in (["-s"], ["-n"]):
            toks = toks[2:]
        elif toks and re.fullmatch(r"-\w+", toks[0]):
            toks = toks[1:] or (["-1"] if toks[0] == "-1" else [])  # bare `kill -1`
        yield [t for t in toks if t != "--"]


def denied(cmd):
    if re.search(r"(?<![\w.-])(pkill|killall)\b|\bfuser\b[^|;&\n]*\s-\w*k|\bxargs\b[^|;&\n]*\bkill\b", cmd):
        return True
    if re.search(r"\btaskkill\b[^|;&\n]*\s[/-]+im\b|\bstop-process\b[^|;&\n]*\s-name\b|\|\s*stop-process\b", cmd, re.I):
        return True
    targets = [t.strip("'\"") for ts in _kill_targets(cmd) for t in ts]
    if any(re.fullmatch(r"0|-\d+", t) for t in targets):  # kill -9 -1, kill 0, kill -- -N
        return True
    # anywhere in the string: while-read loops and PID files split the pgrep from the kill
    if re.search(r"\bkill\b", cmd) and re.search(r"\b(pgrep|pidof|ps|lsof)\b", cmd):
        return not (targets and all(re.fullmatch(r"\d+", t) for t in targets))
    return False


if __name__ == "__main__":
    c = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    if denied(c):
        print(MSG, file=sys.stderr)
        sys.exit(2)
