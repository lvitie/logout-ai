#!/usr/bin/env python3
"""Agent team coordinator: runs Claude and Codex agents one at a time per task. Config: team.toml (see docs/AGENT_TEAM.md)."""
import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import teamcfg  # noqa: E402
import vcs as vcsmod  # noqa: E402

CLIP = 6000  # max chars of any hand-off inlined into a prompt
_usage = {"t": 0.0, "low": False, "mode": "mixed"}
H, P_MAX_X, WASTE, HIST_KEEP_S = 168.0, 2.5, 20.0, 72 * 3600
CFG = WS = RUNS = LIVE = ROLES = VCS = HIST = MODE = ROUTE_LOCK = None
MAX_ROUNDS, MAX_PARALLEL, ROUTES, DOMAINS = 2, 3, set(), set()


def init(config_path=None):
    """Load team.toml and derive the module globals (tests call this with a temp project's config)."""
    global CFG, WS, RUNS, LIVE, ROLES, MAX_ROUNDS, MAX_PARALLEL, ROUTES, DOMAINS, VCS, HIST, MODE, ROUTE_LOCK
    CFG = teamcfg.load(config_path)
    WS, RUNS = CFG["root"], CFG["state"]
    LIVE = RUNS / "live.log"
    R = CFG["routing"]
    MAX_ROUNDS, MAX_PARALLEL = R["max_rounds"], R["max_parallel"]
    # role: (name, cli, model, effort)
    ROLES = {k: (r["name"], r["cli"], r["model"], r["effort"]) for k, r in CFG["roles"].items()}
    ROUTES, DOMAINS = set(R["pipeline"]), set(R["domains"])
    os.environ["TEAM_CONFIG"] = CFG["config_path"]
    VCS = vcsmod.make(CFG, shutil.which(CFG["vcs"]["kind"], path=_clean_path()))
    journal = teamcfg.codex_journal()  # shared by every project using the same CODEX_HOME
    HIST, MODE, ROUTE_LOCK = journal / "usage_hist.jsonl", journal / "route_mode.json", journal / ".lock-route"


def _guard_dir():
    return RUNS / "guard-bin"


def _clean_path():
    guard = str(_guard_dir()) if RUNS else ""
    return os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and p != guard)


KILL_SHIM = ("#!/bin/sh\necho \"agent team: $(basename \"$0\") is not allowed. Kill only a PID you started and "
             "recorded (kill \\$MYPID).\" >&2\nexit 1\n")


def ensure_guards():
    """Symlink vcs-guard under each [vcs].guard_names entry; those names shadow the real tools for agents. Windows
    symlinks need extra privileges, so there each name gets a .cmd shim (PowerShell, cmd) and an sh one (Git Bash).
    pkill and killall get refusing shims: killing by name took down the user's dashboard."""
    _guard_dir().mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        for name in ("pkill", "killall"):
            _put(_guard_dir() / name, text=KILL_SHIM, mode=0o755)
    guard = HERE / "bin/vcs-guard"
    for name in CFG["vcs"]["guard_names"]:
        link = _guard_dir() / name
        if os.name != "nt":
            _put(link, target=guard)
            continue
        py = Path(sys.executable)
        _put(link, text=f'#!/bin/sh\nTEAM_GUARD_TOOL={name} exec "{py.as_posix()}" -X utf8 "{guard.as_posix()}" "$@"\n',
             newline="\n")
        _put(_guard_dir() / f"{name}.cmd",
             text=f'@echo off\nsetlocal\nset "TEAM_GUARD_TOOL={name}"\n"{py}" -X utf8 "{guard}" %*\nexit /b %errorlevel%\n')


def _put(path, text=None, target=None, mode=None, newline=None):
    """Write a file (text) or symlink (target) unless it is already right, swapping it in atomically: parallel runs
    share guard-bin, and an agent must never find a guard name missing (it would reach the real tool)."""
    try:
        if (os.readlink(path) == str(target)) if target is not None else (path.read_text() == text):
            return
    except OSError:  # missing, or not a symlink
        pass
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.unlink(missing_ok=True)
    if target is not None:
        tmp.symlink_to(target)
    else:
        tmp.write_text(text, newline=newline)
        if mode:
            tmp.chmod(mode)
    os.replace(tmp, path)


def noun():
    return teamcfg.change_noun(CFG)


def fmt(text):
    ordered = sorted(DOMAINS, key=CFG["routing"]["domains"].index)
    return (text.replace("{project}", CFG["project"]["name"]).replace("{change_noun}", noun())
            .replace("{domains}", "|".join(ordered)).replace("{docs}", ", ".join(CFG["project"]["docs"]))
            .replace("{state_dir}", CFG["project"]["state_dir"]))


def pipeline(route, domain):
    R = CFG["routing"]
    if route and route.startswith("custom:"):  # parallel side task: one named role implements, a reviewer checks
        return [("implement", route.split(":", 1)[1]), ("review", R["side_task_reviewer"])]
    stages = [tuple(x) for x in R["pipeline"][route if route in R["pipeline"] else "hard"]]
    if R["extra_review_role"] and (route in R["extra_review_routes"] or domain in R["review_extra_domains"]):
        stages.append(("review", R["extra_review_role"]))
    owner = R["domain_roles"].get(domain)  # dedicated role plans and builds this domain; reviewers stay as routed
    if owner:
        stages = [(k, owner if k in ("plan", "implement") else r) for k, r in stages]
    return stages


def live(msg, echo=True):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    if echo:
        print(line, flush=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    with LIVE.open("a") as f:
        f.write(line + "\n")


def tag(text, key):
    found = re.findall(rf"^\s*(?:[-*>]\s+)?\**{key}:\**\s*(\S+)[ \t]*(.*)$", text, re.M)
    return (found[-1][0].strip("*.,;:!`").lower(), found[-1][1].strip()) if found else (None, "")  # "pass." too


def body(text):
    """Hand-off text without the protocol lines and clipped, to keep prompts small."""
    text = re.sub(r"^\s*\**(STATUS|VERDICT|ROUTE|DOMAIN|TITLE):.*$", "", text, flags=re.M).strip()
    return text if len(text) <= CLIP else text[:CLIP] + "\n[clipped]"


def up(url):
    try:
        urllib.request.urlopen(url, timeout=1)
    except urllib.error.HTTPError:
        pass
    except (OSError, ValueError):
        return False
    return True


def env_status():
    """[probes] name = url: reachability of local services the agents depend on."""
    return ", ".join(f"{n} {'up' if up(u) else 'down'}" for n, u in CFG["probes"].items())


def task_dir(tid):
    return RUNS / tid


def load(tid):
    path = task_dir(tid) / "state.json"
    if not path.exists():
        sys.exit(f"No task {tid}.")
    return json.loads(path.read_text())


def save(s):
    (task_dir(s["id"]) / "state.json").write_text(json.dumps(s, indent=2))


def task_times(s):
    """Read timing fields, with task-local file times for pre-timestamp tasks."""
    times = {key: s.get(key) for key in ("created", "stage_started", "finished")}
    terminal = s["status"] in ("done", "dropped")
    if "created" not in s or "stage_started" not in s or (terminal and "finished" not in s):
        d = task_dir(s["id"])
        try:
            modified = (d / "state.json").stat().st_mtime
        except OSError:
            try:
                modified = LIVE.stat().st_mtime
            except OSError:
                modified = None
        prompts = []
        for path in (d / "logs").glob("*.prompt.md"):
            try:
                prompts.append(path.stat().st_mtime)
            except OSError:
                pass
        if "created" not in s:
            times["created"] = min(prompts + ([modified] if modified is not None else []), default=None)
        if "stage_started" not in s and s["status"] != "new":
            times["stage_started"] = max(prompts, default=modified)
        if terminal and "finished" not in s:
            times["finished"] = modified
    return times


def format_task_timing(s, now=None):
    """Compact c(reated), s(tage), f(inished), +current-stage elapsed, in local time."""
    now = time.time() if now is None else now
    times = task_times(s)
    fields = [("c", times["created"]), ("s", times["stage_started"])]
    if times["finished"] is not None:
        fields.append(("f", times["finished"]))
    dates = {datetime.fromtimestamp(t).date() for _, t in fields if t is not None}
    today = datetime.fromtimestamp(now).date()
    shared_date = next(iter(dates)) if len(dates) == 1 and today not in dates else None
    parts = [shared_date.strftime("%m-%d")] if shared_date else []
    for label, stamp in fields:
        dt = datetime.fromtimestamp(stamp) if stamp is not None else None
        fmt_ = "%m-%d/%H:%M" if dt and dt.date() != today and not shared_date else "%H:%M"
        parts.append(label + (dt.strftime(fmt_) if dt else "-"))
    if s["status"] == "running" and times["stage_started"] is not None:
        seconds = max(0, int(now - times["stage_started"]))
        minutes, hours, days = seconds // 60, seconds // 3600, seconds // 86400
        elapsed = (f"{days}d{hours % 24:02}h" if days else f"{hours}h{minutes % 60:02}m" if hours
                   else f"{minutes}m" if minutes else f"{seconds}s")
        parts.append("+" + elapsed)
    return " ".join(parts)


def write_snapshot(s):
    d = task_dir(s["id"])
    (d / "opened.txt").write_text(VCS.opened(s["change"]))
    (d / "changes.diff").write_text(VCS.diff(s["change"]))
    (d / "user_opened.txt").write_text(VCS.others_opened(s["change"]))


def role_text(role):
    text = teamcfg.template(CFG, f"roles/{role}.md")
    return fmt(text) if text else f"You are the {ROLES[role][0]} of the {CFG['project']['name']} agent team."


def build_prompt(s, kind, role):
    d = task_dir(s["id"])
    probes = env_status()
    parts = [role_text(role), fmt(teamcfg.template(CFG, "roles/common.md")),
             fmt(teamcfg.template(CFG, f"vcs/{CFG['vcs']['kind']}.md")),
             f"Task {s['id']} | {noun()} {s['change']} | folder {d} | {s.get('route')}/{s.get('domain')}"
             + (f" | {probes}" if probes else ""),
             "## Request\n" + s["request"]]
    parts = [p for p in parts if p]
    for label, key in (("Spec", "spec"), ("Plan", "plan"), ("Report", "report")):
        if s.get(key) and kind != "route":
            parts.append(f"## {label}\n" + body(Path(s[key]).read_text()))
    feedback = s["plan_reviews"] if kind in ("plan", "plan_review") else s["reviews"]
    if kind != "route":
        parts += [f"## Earlier findings ({Path(r).stem})\n" + body(Path(r).read_text()) for r in feedback]
    if kind != "implement" and CFG["prompts"]["readonly_note"]:
        parts.append(CFG["prompts"]["readonly_note"])
    if s["notes"]:
        parts.append("## User notes\n" + "\n".join(f"- {n}" for n in s["notes"]))
    parts.append("## Job\n" + fmt(teamcfg.template(CFG, f"jobs/{kind}.md")))
    return "\n\n".join(parts)


def summarize(cli, ev):
    """Return (live line or None, final text or None) for one JSON event."""
    if cli == "claude":
        if ev.get("type") == "assistant":
            lines = []
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "text" and b["text"].strip():
                    lines.append(b["text"].strip())
                elif b.get("type") == "tool_use":
                    inp = b.get("input", {})
                    arg = inp.get("command") or inp.get("file_path") or inp.get("pattern") or json.dumps(inp)
                    lines.append(f"> {b['name']} {arg}")
            return "\n  ".join(lines) or None, None
        if ev.get("type") == "result":
            return f"done, ${ev.get('total_cost_usd', 0):.2f}", ev.get("result", "")
        return None, None
    item = ev.get("item", {})
    if ev.get("type") == "item.completed":
        kind = item.get("type")
        if kind == "agent_message":
            return item.get("text", "").strip(), None
        if kind == "command_execution":
            return f"> {item.get('command')} (exit {item.get('exit_code')})", None
        if kind == "file_change":
            return "> edit " + ", ".join(c.get("path", "") for c in item.get("changes", [])), None
        if kind == "mcp_tool_call":
            return f"> {item.get('server')}.{item.get('tool')}", None
    if ev.get("type") == "turn.completed":
        u = ev.get("usage", {})
        return f"done, {u.get('input_tokens', 0)} in / {u.get('output_tokens', 0)} out tokens", None
    if ev.get("type") in ("error", "turn.failed"):
        return f"error: {ev.get('message') or ev.get('error')}", None
    return None, None


def deny_rules():
    """Claude permission deny list: [vcs].deny per tool ("*" = whole tool) plus [agents].deny_extra."""
    rules = []
    for tool, subs in CFG["vcs"]["deny"].items():
        rules += [f"Bash({tool}:*)" if sub == "*" else f"Bash({tool} {sub}:*)" for sub in subs]
    return rules + [f"Bash({c}:*)" for c in CFG["agents"]["deny_extra"]]


def agent_cmd(cli, model, effort, readonly, out):
    if cli == "claude":
        py = f'"{Path(sys.executable).as_posix()}"'
        hook = f'{py} "{(HERE / "hooks/vcs_open.py").as_posix()}"'
        guard = f'{py} "{(HERE / "hooks/bash_guard.py").as_posix()}"'  # denies kill by name (pkill, pgrep | kill)
        settings = {
            "hooks": {
                "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit",
                                "hooks": [{"type": "command", "command": f"{hook} pre"}]},
                               {"matcher": "Bash", "hooks": [{"type": "command", "command": guard}]}],
                "PostToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": f"{hook} post"}]}],
            },
            "permissions": {"deny": deny_rules()},
        }
        cmd = ["claude", "-p", "--model", model, "--effort", effort, "--output-format", "stream-json",
               "--verbose", "--permission-mode", "auto", "--permission-prompts", "none",
               "--settings", json.dumps(settings)]
        if readonly:
            cmd += ["--tools", "Read,Glob,Grep"]
        return cmd
    cmd = ["codex", "exec", "-m", model, "-c", f'model_reasoning_effort="{effort}"', "-C", str(WS),
           "--skip-git-repo-check", "--json", "-o", str(out)]  # Perforce and other non-git workspaces
    if not readonly and CFG["vcs"]["kind"] != "git":  # p4 edit/add must reach the server from the sandbox
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    # workspace-write keeps writes inside the workspace and .git read-only, whatever the user's Codex config says
    return cmd + ["-s", "read-only" if readonly else "workspace-write", "-"]


def reap(pid):
    """Kill what is left of an agent run. On POSIX the agent leads its own session, so its process group also holds
    background shells that were reparented after it exited; the group id stays reserved while any member lives."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


# --- Claude/Codex routing (shared per-account journal in ${XDG_STATE_HOME}/agent-team/codex/<key>/) ---

def _hist_rows():
    """(t, c7, x7) rows of the history file; bad lines are skipped one at a time."""
    rows = []
    try:
        lines = HIST.read_text(errors="ignore").splitlines()
    except OSError:
        return rows
    for ln in lines:
        try:
            r = json.loads(ln)
            rows.append((float(r["t"]), float(r["c7"]), float(r["x7"])))
        except (ValueError, KeyError, TypeError):
            continue
    return rows


def pace(key, used, left_h):
    """%/h burned: sum of rises in our own samples over 72h (drops = resets are skipped); with < 24h of
    samples, used / elapsed. Floor 0.2 %/h."""
    now = time.time()
    i = {"c7": 1, "x7": 2}[key]
    rows = sorted((r[0], r[i]) for r in _hist_rows() if now - r[0] < HIST_KEEP_S)
    span = (now - rows[0][0]) / 3600 if rows else 0
    burn = sum(max(0, b - a) for (_, a), (_, b) in zip(rows, rows[1:]))
    return max(0.2, burn / span if span >= 24 else used / max(24, 168 - left_h))


def _prev_mode():
    try:
        m = json.loads(MODE.read_text())["mode"]
        return m if m in ("claude", "mixed", "codex") else "mixed"
    except (OSError, ValueError, KeyError, TypeError):
        return "mixed"


def _atomic_write(path, text):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _codex_push_target():
    try:
        push = json.loads((MODE.parent / "codex_push.json").read_text())
        target = push["target"]
        until = datetime.fromisoformat(push["until"].replace("Z", "+00:00"))
        if (type(target) in (int, float) and math.isfinite(target) and 0 < target <= 100
                and until.tzinfo is not None and until.timestamp() > time.time()):
            return target
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        pass
    return None


def route_mode(u):
    """-> "claude" | "mixed" | "codex" for flexible roles. Never consumes a Codex reset (read-only inputs).
    Missing c7, x7 or the reset list: keep the previous mode and write no history row."""
    c7, x7, exp = u.get("7d"), u.get("codex_7d"), u.get("codex_reset_exp_h")
    if c7 is None or x7 is None or exp is None:
        return _prev_mode()
    c5, c7h, x7h = u.get("5h", 100), u.get("7d_resets_in_h", 168), u.get("codex_7d_resets_in_h", 168)
    exp = sorted(e for e in exp if e > 0)  # expired / bogus entries ignored
    MODE.parent.mkdir(parents=True, exist_ok=True)
    with ROUTE_LOCK.open("a") as lk:
        teamcfg.lock(lk)  # prev read, history append and mode write form one critical section
        now = time.time()
        keep = [r for r in _hist_rows() if now - r[0] < HIST_KEEP_S] + [(now, float(c7), float(x7))]
        _atomic_write(HIST, "".join(json.dumps({"t": t, "c7": a, "x7": b}) + "\n" for t, a, b in keep))
        p_c, p_x = pace("c7", c7, c7h), pace("x7", x7, x7h)
        usable = []  # reset k opens only after draining the window and k earlier resets
        for e in exp:
            if (100 - x7) + 100 * len(usable) <= P_MAX_X * e:
                usable.append(e)
        s_c = (95 - c7) + 95 * max(0, H - c7h) / 168
        s_x = (100 - x7) + 100 * max(0, H - x7h) / 168 + sum(100 * min(1, H / e) for e in usable)
        r_c, r_x = max(0.1, s_c / p_c), max(0.1, s_x / p_x)  # runway hours; s <= 0 -> 0.1h (drives the other provider)
        q = r_c / r_x
        w_c = (95 - c7) - p_c * c7h
        w_x = max(0, (100 - x7) - p_x * x7h) + 100 * sum(((100 - x7) + 100 * k) / e > p_x for k, e in enumerate(usable))
        prev = _prev_mode()
        if max(w_c, w_x) >= WASTE:
            mode = "claude" if w_c > w_x else "codex"
        elif q < (0.87 if prev == "codex" else 0.70):
            mode = "codex"
        elif q > (1.15 if prev == "claude" else 1.43):
            mode = "claude"
        else:
            mode = "mixed"
        target = _codex_push_target()
        reached = target is not None and x7 >= target
        if reached:
            mode = "claude"
        elif target is not None and c5 < 70 and c7 < 90:
            mode = "codex"
        if x7 >= (target + 1 if target is not None else 92):
            mode = "claude"
        if mode == "claude" and (c5 >= 70 or c7 >= 90):
            mode = "mixed"
        if reached:
            try:
                announced = json.loads(MODE.read_text()).get("push_target_reached") == target
            except (OSError, ValueError, AttributeError):
                announced = False
            if not announced:
                live("Codex push target reached")
        _atomic_write(MODE, json.dumps({"push_target_reached": target if reached else None, "mode": mode, "q": round(q, 2), "p_c": round(p_c, 3), "p_x": round(p_x, 3), "usable": len(usable)}))
        if mode != prev:
            live(f"Routing {prev} -> {mode}: runway Claude {r_c:.0f}h / Codex {r_x:.0f}h, waste {w_c:.0f}/{w_x:.0f}")
    return mode


def claude_low():
    """True when the Claude plan is nearly used up (checked at most every 2 minutes; needs [routing.usage] enabled)."""
    U = CFG["routing"]["usage"]
    if not U["enabled"]:
        return False
    if time.time() - _usage["t"] > 120:
        _usage["t"] = time.time()
        try:
            out = subprocess.run([sys.executable, str(HERE / "usage_tui"), "--json"], capture_output=True, text=True, timeout=30).stdout
            u = json.loads(out or "{}")
            sc = U["scoped_limit"]  # a model-scoped weekly limit (own window) that diverts one role early
            _usage["scoped_high"] = bool(sc) and u.get(sc["label"], 0) >= sc["threshold"]
            _usage["low"] = any(u.get(k, 0) >= v for k, v in U["limits"].items())
            _usage["mode"] = route_mode(u)
        except Exception:
            pass  # unknown usage: keep the last answer
    return _usage["low"]


def burst_active():
    """[routing.usage].burst_file in state_dir holds an epoch deadline: user-requested spend of a scarce budget."""
    name = CFG["routing"]["usage"]["burst_file"]
    try:
        return bool(name) and time.time() < float((RUNS / name).read_text().strip())
    except (OSError, ValueError):
        return False


def run_agent(s, kind, role):
    role, burst = _select_agent_role(s, kind, role)
    capacity = CFG["routing"]["capacity_fallback"]  # a model reporting 503 / "at capacity" is retried on another role
    tried = [role]
    while True:
        out, text = _run_agent_once(s, kind, role, selection=(role, burst))
        if out or s["status"] != "failed" or role not in capacity or not capacity_error(s["reason"].rsplit("see ", 1)[-1]):
            return out, text
        if capacity[role] in tried:  # a fallback cycle: every role in it is unavailable
            s["reason"] += f" (capacity: {' -> '.join(tried)} all unavailable)"
            return out, text
        live(f"[{s['id']}] {role} model unavailable (capacity/503): retrying as {capacity[role]}")
        s["status"], s["reason"], role = "running", "", capacity[role]
        tried.append(role)


def capacity_error(raw):
    """True when the CLI's own errors in a raw agent log (stderr lines, error/failed/result-error events) say the model
    is unavailable. Tool output inside other events is ignored: a test log saying "HTTP 503" is not an outage."""
    try:
        lines = Path(raw).read_text(errors="ignore").splitlines()
    except OSError:
        return False
    errors = []
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            errors.append(ln)
            continue
        if isinstance(ev, dict) and (ev.get("type") in ("error", "turn.failed") or
                                     (ev.get("type") == "result" and ev.get("is_error"))):
            errors.append(json.dumps(ev))
    blob = "\n".join(errors[-20:])
    return any(k in blob for k in ("at capacity", "503", "Service Unavailable", "overloaded"))


def _select_agent_role(s, kind, role):
    R = CFG["routing"]
    U = R["usage"]
    # Cheap roles implement, expensive ones review: [routing.usage].cheap_first roles start on their fallback unless a
    # previous attempt failed.
    failed = s.get("failed") or s["plan_rounds"] >= 1 or s["review_rounds"] >= 1
    claude_low()  # refreshes _usage
    surplus = _usage.get("mode") == "claude"  # Claude has the longer runway or is about to lose budget: spend it, save Codex
    codex_first = _usage.get("mode") == "codex" and role in U["claude_fallback"]  # Codex has the longer runway
    cheap_first = role in U["cheap_first"] and not failed and not surplus
    burst = burst_active()
    if surplus and not claude_low():  # swap Codex roles to Claude to conserve Codex
        swap = dict(U["surplus_swap"], **(U["burst_swap"] if burst else {}))
        if role in swap:
            live(f"[{s['id']}] Claude surplus: {role} -> {swap[role]}")
            role = swap[role]
    if codex_first:
        live(f"[{s['id']}] Codex first: {role} -> {U['claude_fallback'][role]} (Codex)")
        role = U["claude_fallback"][role]
    gate = U["escalation_gate"]  # scarce top role only after cheaper rounds failed
    if gate and role == gate["role"] and not burst and not s.get("failed") and max(s["plan_rounds"], s["review_rounds"]) < gate.get("after_rounds", 2):
        if kind == "review" and s["history"] and s["history"][-1].endswith(f"-review-{gate['first']}"):
            # second review right after a passing first review: an independent opinion from another provider
            live(f"[{s['id']}] Second review: {role} -> {gate['second_review']} ({gate['first']} already passed it)")
            role = gate["second_review"]
        else:
            live(f"[{s['id']}] {gate['first']} first: {role} -> {gate['first']}")
            role = gate["first"]
    scoped = U["scoped_limit"]
    if ROLES[role][1] == "claude" and role in U["claude_fallback"] and (
            cheap_first or codex_first or claude_low() or (scoped and role == scoped["role"] and _usage.get("scoped_high"))):
        live(f"[{s['id']}] {'Codex first' if cheap_first or codex_first else 'Claude usage low'}: {role} -> {U['claude_fallback'][role]} (Codex)")
        role = U["claude_fallback"][role]
    try:  # per-task overrides run after automatic role selection
        ov = json.loads((RUNS / "role_override.json").read_text()).get(s["id"], {})
        if kind in ("plan", "plan_review", "review") and ov.get(kind) in ROLES:
            live(f"[{s['id']}] Override: {role} -> {ov[kind]}")
            role = ov[kind]
        if kind == "implement" and ov.get("implement") in ROLES and s["review_rounds"] >= ov.get("after_failed_reviews", 1):
            live(f"[{s['id']}] Override after failed review: {role} -> {ov['implement']}")
            role = ov["implement"]
    except (OSError, ValueError):
        pass
    af = R["after_impl_fails"]  # repeated failed implementations go to a stronger role
    if kind == "implement" and af and s.get("impl_fails", 0) >= af["fails"] and role != af["role"]:
        live(f"[{s['id']}] {s['impl_fails']} failed implementations: {role} -> {af['role']}")
        role = af["role"]
    return role, burst


def _run_agent_once(s, kind, role, *, selection=None):
    role, burst = selection if selection is not None else _select_agent_role(s, kind, role)
    name, cli, model, effort = ROLES[role]
    if not burst and role in CFG["routing"]["usage"]["no_burst_effort"]:
        effort = CFG["routing"]["usage"]["no_burst_effort"][role]  # high effort only during a user-requested burst
    d = task_dir(s["id"])
    s["n"] += 1
    stem = f"{s['n']:02d}-{kind}-{role}"
    out, raw = d / f"{stem}.md", d / "logs" / f"{stem}.jsonl"
    raw.parent.mkdir(exist_ok=True)
    if kind != "route":
        write_snapshot(s)
    text = build_prompt(s, kind, role)
    (d / "logs" / f"{stem}.prompt.md").write_text(text)
    ensure_guards()
    env = dict(os.environ, TEAM_TASK=s["id"], TEAM_CHANGE=str(s["change"]), TEAM_ROLE=role,
               TEAM_CONFIG=CFG["config_path"], PATH=f"{_guard_dir()}{os.pathsep}{_clean_path()}")
    for tool in CFG["vcs"]["guard_names"]:  # used by the edit hook; the guard falls back to a PATH search
        real = shutil.which(tool, path=_clean_path())
        if real:
            env[f"TEAM_REAL_{tool.upper()}"] = real
        else:
            env.pop(f"TEAM_REAL_{tool.upper()}", None)
    cmd = teamcfg.command(agent_cmd(cli, model, effort, kind != "implement", out), path=env["PATH"])

    live(f"[{s['id']}] {name} ({model}, {effort}): {kind}")
    final = timer = None
    untracked = []  # Codex edits that could not join the task's change
    session = {} if os.name == "nt" else {"start_new_session": True}  # its own process group, reaped as a whole
    with raw.open("w") as rawf, subprocess.Popen(cmd, cwd=WS, env=env, text=True, stdin=subprocess.PIPE,
                                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **session) as proc:
        try:
            try:
                proc.stdin.write(text)
                proc.stdin.close()
            except BrokenPipeError:  # it exited before reading the prompt (crash, auth error): its exit code says so
                pass
            for line in proc.stdout:
                rawf.write(line)
                rawf.flush()
                try:
                    ev = json.loads(line)
                    msg, result = summarize(cli, ev)
                except (json.JSONDecodeError, AttributeError):
                    ev, msg, result = None, line.strip() or None, None
                if msg:
                    live(f"[{name}] {msg[:600]}")
                if result is not None:
                    final = result
                if cli == "codex" and kind == "implement" and isinstance(ev, dict):
                    untracked += track_codex_edits(s, ev)
                if timer is None and (result is not None or (isinstance(ev, dict) and ev.get("type") == "turn.completed")):
                    # the last event: reap stray background shells that hold stdout open
                    timer = threading.Timer(30, reap, (proc.pid,))
                    timer.daemon = True
                    timer.start()
            rc = proc.wait()
        except BaseException:  # Ctrl+C or a crash: the agent's own session does not get the signal
            reap(proc.pid)
            raise
    if timer:
        timer.cancel()
    if os.name != "nt":
        reap(proc.pid)  # leftovers that do not hold stdout
    if cli == "claude":
        out.write_text(final or "")
    text = out.read_text() if out.exists() else ""
    if rc != 0 or not text.strip():
        s["status"], s["reason"] = "failed", f"{name} exited {rc} with no result; see {raw}"
        return None, None
    if untracked:  # the change would silently miss these files: the user resolves it (e.g. a lock), then approves
        s["status"], s["reason"] = "blocked", f"{name} changed files that are not in {noun()} {s['change']}: " + \
            "; ".join(untracked)[:500]
        return None, None
    s["history"].append(stem)
    return str(out), text


def track_codex_edits(s, ev):
    """Codex has no edit hook: open or add the files a completed file_change reports in the task's change (p4 edit
    on an already writable file keeps its content). Deleted files are left to the agent. Returns the failures."""
    item, failed = ev.get("item", {}), []
    if ev.get("type") != "item.completed" or item.get("type") != "file_change":
        return failed
    for c in item.get("changes", []):
        path = (WS / c.get("path", "")).resolve()
        if WS not in path.parents or not path.is_file():
            continue
        ok, msg = (True, "") if c.get("kind") == "add" else VCS.prepare_edit(path, s["change"])  # strays move in
        if ok:  # then add: a no-op for opened files, and it picks up untracked ones (Codex has no post-write hook)
            ok, msg = VCS.add(path, s["change"])
        if not ok:
            live(f"[{s['id']}] {msg}")
            failed.append(f"{path.relative_to(WS)}: {msg}")
    return failed


def route_task(s):
    out, text = run_agent(s, "route", "producer")
    if not out:
        return
    s["spec"] = out
    route, _ = tag(text, "ROUTE")
    domain, _ = tag(text, "DOMAIN")
    _, title = tag(text, "TITLE")
    s["title"] = title or s["request"].splitlines()[0][:60]
    VCS.set_description(s["change"], f"[team {s['id']}] {s['title']}")
    if route == "ask":
        s["status"], s["reason"] = "blocked", f"Producer needs a decision; see `team review {s['id']}`, then `team redo`."
    elif route not in ROUTES or domain not in DOMAINS:
        s["status"], s["reason"] = "failed", f"Producer gave ROUTE={route} DOMAIN={domain}"
    else:
        s["route"], s["domain"], s["stage"] = route, domain, 0
        live(f"[{s['id']}] routed {route}/{domain}: {s['title']}")


def step(s, stages):
    kind, role = stages[s["stage"]]
    tk = CFG["routing"]["takeover"].get(role)  # [routing.takeover.<role>]: to, after_reviews, after_attempt
    if kind == "implement" and tk and (
            s["review_rounds"] >= tk.get("after_reviews", 1)
            or (tk.get("after_attempt") and any(h.endswith(f"-implement-{role}") for h in s["history"]))):
        role = tk["to"]
    out, text = run_agent(s, kind, role)
    if not out:
        return
    if kind in ("plan", "implement"):
        s["plan" if kind == "plan" else "report"] = out
        status, reason = tag(text, "STATUS")
        if status == "done":
            s["stage"] += 1
        elif status in ("gate", "blocked"):
            s["status"], s["reason"] = status, f"{ROLES[role][0]}: {reason}"
        else:
            s["status"], s["reason"] = "failed", f"{ROLES[role][0]} gave no STATUS line"
        return
    verdict, _ = tag(text, "VERDICT")
    feedback = "plan_reviews" if kind == "plan_review" else "reviews"
    if verdict == "pass":
        s["stage"] += 1
        return
    if verdict != "fail":
        s["status"], s["reason"] = "failed", f"{ROLES[role][0]} gave no VERDICT line"
        return
    rounds, target = ("plan_rounds", "plan") if kind == "plan_review" else ("review_rounds", "implement")
    s[feedback] = [out]  # only the latest findings travel forward
    s[rounds] += 1
    if kind != "plan_review":
        s["impl_fails"] = s.get("impl_fails", 0) + 1  # cumulative, survives escalation retries
    if s[rounds] > MAX_ROUNDS:
        s["failed"] = True
        s["status"], s["reason"] = "escalated", f"{target} failed review {s[rounds]} times; see {out}"
    else:
        s["stage"] = next(i for i, (k, _) in enumerate(stages) if k == target)
        live(f"[{s['id']}] review failed, back to {target} (round {s[rounds]})")


def resource_ok(name):
    """[locks.<name>] min_free_mib + probe_cmd (prints free MiB first): skipped when the probe binary is missing."""
    lc = CFG["locks"].get(name)
    if not isinstance(lc, dict) or not lc.get("probe_cmd") or not shutil.which(lc["probe_cmd"][0]):
        return True
    try:
        out = subprocess.run(lc["probe_cmd"], capture_output=True, text=True, timeout=15).stdout
        return int(out.split()[0]) >= lc.get("min_free_mib", 0)
    except Exception:
        return True


def take_capacity(res, held):
    """A slot under max_parallel and the [locks] in res, appended to held; returns why the run must wait, or None."""
    for name in [f"slot{i}" for i in range(MAX_PARALLEL)]:  # global concurrency cap
        f = (RUNS / f".lock-{name}").open("a")
        try:
            teamcfg.lock(f, blocking=False)
            held.append(f)
            break
        except BlockingIOError:
            f.close()
    else:
        return f"{MAX_PARALLEL} team runs are already in progress"
    for r in res:
        f = (RUNS / f".lock-{r}").open("a")
        try:
            teamcfg.lock(f, blocking=False)
        except BlockingIOError:
            f.close()
            return f"resource '{r}' is busy with another team run"
        held.append(f)
    return resource_low(res)


def resource_low(res):
    """Why the [locks] probes refuse a run holding res, or None."""
    for r in res:
        lc = CFG["locks"].get(r)
        if isinstance(lc, dict) and lc.get("skip_if_holds") not in res and not resource_ok(r):
            return f"not enough free resource '{r}' (< {lc.get('min_free_mib')} MiB) to run next to other jobs"
    return None


def advance(s, from_queue=False):
    """Run a task. Tasks that need different resources ([locks]) run in parallel; the same resource is exclusive.
    Without capacity the task is saved as new and queued (notes and stage kept); the queue runner starts it later."""
    RUNS.mkdir(parents=True, exist_ok=True)
    res = [r for r in s.get("res") or CFG["locks"]["default"] if r != "none"]
    held = []
    try:
        f = run_lock(s["id"], patience=1)  # first: only the lock holder may save the state below
        if not f:
            sys.exit(f"{s['id']} is already running.")
        held.append(f)
        if from_queue:
            s = load(s["id"])  # another runner may have started it since the dispatcher looked
            if s["status"] != "new" or not s.get("queued"):
                return
        wait = take_capacity(res, held)
        if wait:
            s["status"], s["reason"], s["queued"] = "new", f"queued: {wait}", True
            save(s)
            live(f"[{s['id']}] queued: {wait}; the queue runner (dashboard alerts pane or `team queue`) starts it")
            return
        if "created" not in s:
            s["created"] = task_times(s)["created"] or time.time()
        s["finished"] = None
        if stage_label(s) != "end":
            s["stage_started"] = time.time()
        s["status"], s["reason"] = "running", ""
        s.pop("queued", None)
        save(s)
        while s["status"] == "running":
            previous_stage = s["stage"]
            if s["stage"] < 0:
                route_task(s)
            else:
                stages = pipeline(s["route"], s["domain"])
                if s["stage"] >= len(stages):
                    s["status"], s["reason"] = "done", f"Review {noun()} {s['change']} (`team review {s['id']}`); the user submits it."
                    s["finished"] = time.time()
                else:
                    step(s, stages)
            if s["status"] == "running" and s["stage"] != previous_stage and stage_label(s) != "end":
                s["stage_started"] = time.time()
            save(s)
    finally:
        for f in held:
            f.close()
    live(f"[{s['id']}] {s['status']}: {s['reason']}")


def run_lock(tid, patience=0.0):
    """The task's run lock as an open file, held by the process advancing it; None when another process holds it.
    patience retries for that many seconds: status probes (dashboard, wait, queue) hold it for an instant."""
    deadline = time.time() + patience
    while True:
        f = (task_dir(tid) / ".lock-run").open("a")
        try:
            teamcfg.lock(f, blocking=False)
            return f
        except BlockingIOError:
            f.close()
            if time.time() >= deadline:
                return None
            time.sleep(0.05)


def all_tasks():
    """Task states in id order; folders without a readable state.json are skipped."""
    found = []
    for d in sorted(RUNS.glob("t[0-9]*")):
        try:
            s = json.loads((d / "state.json").read_text())
        except (OSError, ValueError):
            continue
        if isinstance(s, dict) and "id" in s:
            found.append(s)
    return found


def run_held(tid):
    """True while a team process holds the task's run lock (the probe takes it for an instant when free)."""
    f = run_lock(tid)
    if f:
        f.close()
    return f is None


def queue_notes():
    """{key: line} from the queue file in file order, comments skipped."""
    try:
        text = (RUNS / CFG["project"]["queue_file"]).read_text()
    except OSError:
        return {}
    notes = {}
    for ln in text.splitlines():
        if ln.strip() and not ln.lstrip().startswith("#"):
            notes.setdefault(ln.split(":", 1)[0].strip(), ln.strip())
    return notes


def queue_deps(note):
    """Task ids in a queue line's "(after t003, t004)" note."""
    m = re.search(r"\(after ([^)]*)\)", note)
    return re.findall(r"\bt\d+\b", m[1]) if m else []


_spawned = {}  # tid -> Popen of runs this process started, so a run that is still starting is not started twice


def dispatch():
    """One queue pass: start queued tasks (refused for capacity, not `--no-run` ones) in queue-file order, then by id,
    while slots and their [locks] are free and the tasks named in an `after tNNN` note are done. Runs are detached,
    log to <task>/logs/queue-run.log and recheck under the run lock that the task is still queued."""
    for tid in [t for t, p in _spawned.items() if p.poll() is not None]:
        del _spawned[tid]
    tasks = {s["id"]: s for s in all_tasks()}
    active = {t for t, s in tasks.items() if s["status"] == "running" and run_held(t)} | set(_spawned)
    busy = {r for t in active if t in tasks for r in tasks[t].get("res") or CFG["locks"]["default"]}
    notes = queue_notes()
    rank = {k: i for i, k in enumerate(notes)}
    started = []
    for s in sorted((s for t, s in tasks.items() if s["status"] == "new" and s.get("queued") and t not in active),
                    key=lambda s: (rank.get(s["id"], len(rank)), s["id"])):
        if len(active) >= MAX_PARALLEL:
            break
        if any(tasks.get(t, {}).get("status") != "done" for t in queue_deps(notes.get(s["id"], ""))):
            continue
        res = {r for r in s.get("res") or CFG["locks"]["default"] if r != "none"}
        if res & busy or resource_low(res):  # a probe-blocked task must not take the slot of a runnable one
            continue
        logs = task_dir(s["id"]) / "logs"
        logs.mkdir(exist_ok=True)
        detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                  if os.name == "nt" else {"start_new_session": True})  # survives the dashboard closing
        with (logs / "queue-run.log").open("a") as out:
            _spawned[s["id"]] = subprocess.Popen(
                [sys.executable, str(HERE / "team.py"), "--config", CFG["config_path"], "run", "--queued", s["id"]], cwd=WS,
                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **detach)
        live(f"[{s['id']}] queue: starting", echo=False)
        active.add(s["id"])
        busy |= res
        started.append(s["id"])
    return started


ATTENTION = ("gate", "blocked", "escalated", "failed")


def first_seen():
    """Seen map for a new watcher: finished tasks are old news, everything that needs attention gets reported."""
    return {s["id"]: [s["status"], s.get("n", 0)] for s in all_tasks() if s["status"] in ("done", "dropped")}


def wait_events(seen):
    """[(id, status, text)] for tasks that changed since seen ({id: [status, agent runs]}, updated in place) into an
    attention state, done, stale (marked running, no process), slow (a stage past [routing].long_stage_min) or held
    (queued after a dropped task)."""
    events, tasks, notes = [], all_tasks(), queue_notes()
    by_id = {s["id"]: s for s in tasks}
    limit = CFG["routing"]["long_stage_min"] * 60
    for s in tasks:
        st, text = s["status"], s["reason"] or s["title"] or s["request"].splitlines()[0]
        if st == "running":
            f = run_lock(s["id"])
            if f:
                with f:  # nobody holds it: reread under the lock, the run may have saved its result since
                    s = load(s["id"])
                st, text = s["status"], s["reason"] or text
                if st == "running":
                    st, text = "stale", f"marked running but its process is gone; resume with `team run {s['id']}`"
            elif limit and s.get("stage_started") and time.time() - s["stage_started"] > limit:
                st = "slow"
                text = (f"{stage_label(s)} has run {int(time.time() - s['stage_started']) // 60} min; "
                        f"check the live log")
        elif st == "new" and s.get("queued"):
            gone = [t for t in queue_deps(notes.get(s["id"], "")) if by_id.get(t, {}).get("status") == "dropped"]
            if gone:
                st = "held"
                text = (f"queued after {', '.join(gone)}, which was dropped; edit {CFG['project']['queue_file']} "
                        f"or drop it")
        key = [st, s.get("n", 0)]  # the run count tells a repeated failure from the one already reported
        if seen.get(s["id"]) == key:
            continue
        seen[s["id"]] = key
        if st in ATTENTION or st in ("done", "stale", "slow", "held"):
            events.append((s["id"], st, " ".join(text.split())))
    return events


def cmd_wait(a):
    """Block until a task needs attention or finishes, print those tasks and exit; runs the queue while it waits.
    What was reported is kept in <state_dir>/.wait-seen.json, so changes between two waits are reported by the next."""
    path = RUNS / ".wait-seen.json"
    try:
        seen = json.loads(path.read_text())
    except (OSError, ValueError):
        seen = first_seen()
    while True:
        try:
            dispatch()  # queued tasks start without the dashboard too
        except (OSError, ValueError) as e:
            print(f"queue: {e}", file=sys.stderr)
        events = wait_events(seen)
        if events or a.no_block:
            break
        time.sleep(5)
    RUNS.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(seen))
    for tid, st, text in events:
        print(f"{tid} {st}: {text}")


def cmd_queue(a):
    """Queue runner: start queued tasks as capacity frees up (the dashboard alerts pane runs the same passes)."""
    while True:
        for tid in dispatch():
            print(f"{time.strftime('%H:%M')} started {tid}", flush=True)
        if a.once:
            return
        time.sleep(10)


def stage_label(s):
    if s["stage"] < 0:
        return "route/producer"
    stages = pipeline(s["route"], s["domain"])
    return "end" if s["stage"] >= len(stages) else "/".join(stages[s["stage"]])


def cmd_new(a):
    RUNS.mkdir(parents=True, exist_ok=True)
    n = max([int(p.name[1:]) for p in RUNS.glob("t[0-9]*") if p.name[1:].isdigit()] + [0]) + 1
    while True:  # the folder claims the id: two `team new` at once get different ones
        tid = f"t{n:03d}"
        try:
            task_dir(tid).mkdir()
            break
        except FileExistsError:
            n += 1
    try:
        change = VCS.new_change(f"[team {tid}] {a.request.splitlines()[0][:60]}", tid)
    except (RuntimeError, OSError) as e:
        task_dir(tid).rmdir()
        sys.exit(f"Could not create a change: {e}")
    names = CFG["locks"]["names"]
    res = [r for r in a.res.split(",") if r in names or r == "none"] if a.res else list(CFG["locks"]["default"])
    res = res or list(CFG["locks"]["default"])
    s = {"id": tid, "request": a.request, "change": str(change), "title": "", "route": None, "domain": None,
         "stage": -1, "status": "new", "reason": "", "n": 0, "plan_rounds": 0, "review_rounds": 0,
         "res": res, "notes": [], "plan_reviews": [], "reviews": [], "history": [],
         "created": time.time(), "stage_started": None, "finished": None}
    if a.role:  # parallel side task: skip routing, the named role implements
        s.update(route=f"custom:{a.role}", stage=0, title=a.request.splitlines()[0][:60],
                 domain=CFG["routing"]["side_task_domains"].get(a.role, CFG["routing"]["domains"][0]))
    save(s)
    live(f"[{tid}] created, {noun()} {s['change']}")
    if not a.no_run:
        advance(s)


def cmd_run(a):
    advance(load(a.id), from_queue=a.queued)


def cmd_approve(a):
    s = load(a.id)
    if s["status"] not in ("gate", "blocked", "escalated", "failed"):
        sys.exit(f"{a.id} is {s['status']}; nothing to approve.")
    s["notes"].append(f"Approved ({s['reason']})" + (f": {a.note}" if a.note else ""))
    if s["status"] == "escalated":
        s["plan_rounds"] = s["review_rounds"] = 0
        stages = pipeline(s["route"], s["domain"])
        kind = stages[s["stage"]][0] if 0 <= s["stage"] < len(stages) else None
        if kind in ("plan", "plan_review", "review"):  # retry the work that failed review, not the review
            target = "plan" if kind != "review" else "implement"
            s["stage"] = next(i for i, (k, _) in enumerate(stages) if k == target)
    advance(s)


def cmd_drop(a):
    s = load(a.id)
    f = run_lock(a.id, patience=1)
    if not f:
        sys.exit(f"{a.id} is running; stop it first.")
    f.close()
    s["notes"].append("Dropped by the user" + (f": {a.note}" if a.note else ""))
    s["status"], s["reason"] = "dropped", a.note or "dropped"
    s["finished"] = time.time()
    save(s)
    print(f"{a.id} dropped.")


def cmd_redo(a):
    s = load(a.id)
    s["notes"].append(a.note)
    s["plan_rounds"] = s["review_rounds"] = 0
    s["stage"] = -1 if not s["route"] else next(
        i for i, (k, _) in enumerate(pipeline(s["route"], s["domain"])) if k == "implement")
    advance(s)


def cmd_review(a):
    """Build the HTML review page for the given tasks (default: the latest done ones) and open it."""
    page = subprocess.run([sys.executable, str(HERE / "review_page"), *a.ids, "--open"])
    sys.exit(page.returncode)


def under_watch():
    """True when run by `watch` (the dashboard task pane): walk up the parent processes."""
    pid = os.getppid()
    for _ in range(4):
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
            if comm == "watch":
                return True
            pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return False
    return False


def cmd_status(a):
    if a.id:
        s = load(a.id)
        print(f"{s['id']}  {s['status']}  chg:{s['change']}  {s['route']}/{s['domain']}  at {stage_label(s)}")
        print(f"  {format_task_timing(s)}  (c=created s=stage f=finished +stage elapsed)")
        print(f"  {s['title'] or s['request'].splitlines()[0]}")
        if s["reason"]:
            print(f"  {s['reason']}")
        for h in s["history"]:
            print(f"  {task_dir(s['id']) / h}.md")
        print(VCS.opened(s["change"]).rstrip())
        return
    tasks = sorted(RUNS.glob("t[0-9]*"))
    if a.reverse or under_watch():  # dashboard pane: newest task on top, always visible without scrolling
        tasks.reverse()
    if not tasks:
        print('No tasks yet. Start one with: team new "<request>"')
    now = time.time()
    for d in tasks:
        try:
            s = json.loads((d / "state.json").read_text())
            assert isinstance(s, dict) and "id" in s
        except (OSError, ValueError, AssertionError):
            continue  # no or corrupt state.json (a folder synced from the depot, or mid-write)
        print(f"{s['id']}  {s['status']:9}  chg:{s['change']}  {str(s['route']):7} {str(s['domain']):8} "
              f"{stage_label(s):22} {(s['title'] or s['request'])[:50]}\t{format_task_timing(s, now)}")
        if s["reason"] and s["status"] != "running":
            print(f"      {s['reason']}")


def main():
    if os.name != "nt":  # agents run in their own session: a TERM/HUP must unwind like Ctrl+C so they are reaped
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda n, _frame: sys.exit(128 + n))
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", help="team.toml path (default: $TEAM_CONFIG, else the nearest team.toml upwards)")
    g, rest = pre.parse_known_args()
    init(g.config)
    ap = argparse.ArgumentParser(prog="team", description=__doc__, parents=[pre])
    sub = ap.add_subparsers(required=True)
    p = sub.add_parser("new", help="create a task and run it")
    p.add_argument("request")
    p.add_argument("--role", choices=CFG["routing"]["side_task_roles"] or None,
                   help="parallel side task: skip routing, this role implements, the side-task reviewer reviews")
    p.add_argument("--res", default="", help="locks used, comma list of [locks].names or none (default: [locks].default)")
    p.add_argument("--no-run", action="store_true", help="create the task only; start it later with `team run <id>`")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("run", help="resume a task")
    p.add_argument("id")
    p.add_argument("--queued", action="store_true", help=argparse.SUPPRESS)  # queue runner: only if still queued
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("approve", help="pass a gate, or retry after escalation or failure")
    p.add_argument("id")
    p.add_argument("note", nargs="?", default="")
    p.set_defaults(func=cmd_approve)
    p = sub.add_parser("drop", help="abandon a task (parked or stale); it stays listed as dropped")
    p.add_argument("id")
    p.add_argument("note", nargs="?", default="")
    p.set_defaults(func=cmd_drop)
    p = sub.add_parser("redo", help="send back to the implementer (or Producer) with a note")
    p.add_argument("id")
    p.add_argument("note")
    p.set_defaults(func=cmd_redo)
    p = sub.add_parser("review", help="open the HTML review page for tasks (default: the latest done ones)")
    p.add_argument("ids", nargs="*")
    p.set_defaults(func=cmd_review)
    p = sub.add_parser("queue", help="start queued (new) tasks as slots and locks free up; the alerts pane does this")
    p.add_argument("--once", action="store_true", help="one pass, then exit")
    p.set_defaults(func=cmd_queue)
    p = sub.add_parser("wait", help="block until a task needs attention or finishes, print it and exit")
    p.add_argument("--no-block", action="store_true", help="report what changed since the last wait and exit")
    p.set_defaults(func=cmd_wait)
    p = sub.add_parser("status", help="list tasks, or show one")
    p.add_argument("-r", "--reverse", action="store_true", help="newest task first")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=cmd_status)
    a = ap.parse_args(rest)
    a.func(a)


if __name__ == "__main__":
    main()
