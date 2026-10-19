#!/usr/bin/env python3
"""Agent team coordinator: runs Claude and Codex agents one at a time per task. Config: team.toml (see docs/AGENT_TEAM.md)."""
import argparse
import json
import math
import os
import re
import shutil
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
            shim = _guard_dir() / name
            shim.write_text(KILL_SHIM)
            shim.chmod(0o755)
    guard = HERE / "bin/vcs-guard"
    for name in CFG["vcs"]["guard_names"]:
        link = _guard_dir() / name
        if link.is_symlink() or link.exists():
            link.unlink()
        if os.name != "nt":
            link.symlink_to(guard)
            continue
        py = Path(sys.executable)
        link.write_text(f'#!/bin/sh\nTEAM_GUARD_TOOL={name} exec "{py.as_posix()}" -X utf8 "{guard.as_posix()}" "$@"\n',
                        newline="\n")
        (_guard_dir() / f"{name}.cmd").write_text(
            f'@echo off\nsetlocal\nset "TEAM_GUARD_TOOL={name}"\n"{py}" -X utf8 "{guard}" %*\nexit /b %errorlevel%\n')


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


def live(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    with LIVE.open("a") as f:
        f.write(line + "\n")


def tag(text, key):
    found = re.findall(rf"^\s*(?:[-*>]\s+)?\**{key}:\**\s*(\S+)[ \t]*(.*)$", text, re.M)
    return (found[-1][0].strip("*").lower(), found[-1][1].strip()) if found else (None, "")


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
    # workspace-write keeps writes inside the workspace and .git read-only, whatever the user's Codex config says
    return cmd + ["-s", "read-only" if readonly else "workspace-write", "-"]


def reap(pid):
    """Kill an agent's leftover child processes, then the agent, once its result has been delivered."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    # the real pkill, not the guard shim (a team run started from an agent has guard-bin on its PATH)
    subprocess.run([shutil.which("pkill", path=_clean_path()) or "pkill", "-TERM", "-P", str(pid)], check=False)
    time.sleep(5)
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
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
            out = subprocess.run([str(HERE / "usage_tui"), "--json"], capture_output=True, text=True, timeout=30).stdout
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
    for _ in range(4):
        out, text = _run_agent_once(s, kind, role, selection=(role, burst))
        reason = s.get("reason", "")
        if out or s["status"] != "failed" or role not in capacity:
            return out, text
        raw = reason.rsplit("see ", 1)[-1]
        try:
            blob = open(raw, errors="ignore").read()
        except OSError:
            blob = ""
        if "at capacity" not in blob and "503" not in blob and "Service Unavailable" not in blob:
            return out, text
        live(f"[{s['id']}] {role} model unavailable (capacity/503): retrying as {capacity[role]}")
        s["status"], s["reason"], role = "running", "", capacity[role]
    return None, None


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
    final = None
    with raw.open("w") as rawf, subprocess.Popen(cmd, cwd=WS, env=env, text=True, stdin=subprocess.PIPE,
                                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        proc.stdin.write(text)
        proc.stdin.close()
        for line in proc.stdout:
            rawf.write(line)
            rawf.flush()
            try:
                msg, result = summarize(cli, json.loads(line))
            except (json.JSONDecodeError, AttributeError):
                msg, result = line.strip() or None, None
            if msg:
                live(f"[{name}] {msg[:600]}")
            if result is not None:
                final = result
                if cli == "claude":  # result is the last event: reap stray background shells that hold stdout open
                    threading.Timer(30, reap, (proc.pid,)).start()
        rc = proc.wait()
    if cli == "claude":
        out.write_text(final or "")
    text = out.read_text() if out.exists() else ""
    if rc != 0 or not text.strip():
        s["status"], s["reason"] = "failed", f"{name} exited {rc} with no result; see {raw}"
        return None, None
    s["history"].append(stem)
    return str(out), text


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


def advance(s):
    """Run a task. Tasks that need different resources ([locks]) run in parallel; the same resource is exclusive."""
    RUNS.mkdir(parents=True, exist_ok=True)
    res = s.get("res") or list(CFG["locks"]["default"])
    held = []
    try:
        for name in [f"slot{i}" for i in range(MAX_PARALLEL)]:  # global concurrency cap
            f = (RUNS / f".lock-{name}").open("a")
            try:
                teamcfg.lock(f, blocking=False)
                held.append(f)
                break
            except BlockingIOError:
                f.close()
        else:
            sys.exit(f"{MAX_PARALLEL} team runs are already in progress.")
        f = run_lock(s["id"])
        if not f:
            sys.exit(f"{s['id']} is already running.")
        held.append(f)
        res = [r for r in res if r != "none"]
        for r in res:
            f = (RUNS / f".lock-{r}").open("a")
            try:
                teamcfg.lock(f, blocking=False)
            except BlockingIOError:
                sys.exit(f"Resource '{r}' is busy with another team run.")
            held.append(f)
        for r in res:
            lc = CFG["locks"].get(r)
            if isinstance(lc, dict) and lc.get("skip_if_holds") not in res and not resource_ok(r):
                sys.exit(f"Not enough free resource '{r}' (< {lc.get('min_free_mib')} MiB) to run next to other jobs.")
        if "created" not in s:
            s["created"] = task_times(s)["created"] or time.time()
        s["finished"] = None
        if stage_label(s) != "end":
            s["stage_started"] = time.time()
        s["status"], s["reason"] = "running", ""
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


def run_lock(tid):
    """The task's run lock as an open file, held by the process advancing it; None when another process holds it."""
    f = (task_dir(tid) / ".lock-run").open("a")
    try:
        teamcfg.lock(f, blocking=False)
        return f
    except BlockingIOError:
        f.close()
        return None


def stage_label(s):
    if s["stage"] < 0:
        return "route/producer"
    stages = pipeline(s["route"], s["domain"])
    return "end" if s["stage"] >= len(stages) else "/".join(stages[s["stage"]])


def cmd_new(a):
    RUNS.mkdir(parents=True, exist_ok=True)
    n = max([int(p.name[1:]) for p in RUNS.glob("t[0-9]*") if p.name[1:].isdigit()] + [0]) + 1
    tid = f"t{n:03d}"
    try:
        change = VCS.new_change(f"[team {tid}] {a.request.splitlines()[0][:60]}", tid)
    except (RuntimeError, OSError) as e:
        sys.exit(f"Could not create a change: {e}")
    task_dir(tid).mkdir()
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
    advance(load(a.id))


def cmd_approve(a):
    s = load(a.id)
    if s["status"] not in ("gate", "blocked", "escalated", "failed"):
        sys.exit(f"{a.id} is {s['status']}; nothing to approve.")
    s["notes"].append(f"Approved ({s['reason']})" + (f": {a.note}" if a.note else ""))
    if s["status"] == "escalated":
        s["plan_rounds"] = s["review_rounds"] = 0
        stages = pipeline(s["route"], s["domain"])
        if 0 <= s["stage"] < len(stages) and stages[s["stage"]][0] in ("plan", "plan_review"):
            s["stage"] = next(i for i, (kind, _) in enumerate(stages) if kind == "plan")
    advance(s)


def cmd_drop(a):
    s = load(a.id)
    f = run_lock(a.id)
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
    p = sub.add_parser("status", help="list tasks, or show one")
    p.add_argument("-r", "--reverse", action="store_true", help="newest task first")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=cmd_status)
    a = ap.parse_args(rest)
    a.func(a)


if __name__ == "__main__":
    main()
