#!/usr/bin/env python3
"""Agent team coordinator: runs Claude and Codex agents one at a time per task. Config: team.toml (see docs/AGENT_TEAM.md)."""
import argparse
import hashlib
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
import tomllib
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import teamcfg  # noqa: E402
import tokens  # noqa: E402
import vcs as vcsmod  # noqa: E402

CLIP = 6000  # max chars of any hand-off inlined into a prompt
RESUME_KINDS = ("plan", "plan_review", "implement", "plan_implement", "review")  # [agents] resume: rounds continue a session
LEARN_MAX = 20  # bullets kept in learnings.md
RESUME_LINE = "Next round of the same task; only what changed since your last turn follows."
_usage = {"t": 0.0, "ok_t": 0.0, "fail": True, "low": False, "mode": "mixed"}  # ok_t: last good fetch
H, P_MAX_X, WASTE, HIST_KEEP_S = 168.0, 2.5, 20.0, 72 * 3600
CFG = WS = RUNS = LIVE = ROLES = AGENTS = VCS = HIST = MODE = ROUTE_LOCK = None
MAX_ROUNDS, MAX_PARALLEL, ROUTES, DOMAINS = 2, 3, set(), set()


def init(config_path=None):
    """Load team.toml and derive the module globals (tests call this with a temp project's config)."""
    global CFG, WS, RUNS, LIVE, ROLES, AGENTS, MAX_ROUNDS, MAX_PARALLEL, ROUTES, DOMAINS, VCS, HIST, MODE, ROUTE_LOCK
    CFG = teamcfg.load(config_path)
    WS, RUNS = CFG["root"], CFG["state"]
    LIVE = RUNS / "live.log"
    R = CFG["routing"]
    MAX_ROUNDS, MAX_PARALLEL = R["max_rounds"], R["max_parallel"]
    # role: (name, cli, model, effort)
    ROLES = {k: (r["name"], r["cli"], r["model"], r["effort"]) for k, r in CFG["roles"].items()}
    AGENTS = CFG["agent_defs"]  # name -> {name, scope, instructions, optional model/effort pin}
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
    _put(_guard_dir() / "root", text=f"{WS}\n")  # the guard lets git run in repos outside the root
    _put(_guard_dir() / "config", text=f"{CFG['config_path']}\n")
    for name in CFG["vcs"]["guard_names"]:
        link = _guard_dir() / name
        if os.name != "nt":
            _put(link, target=guard)
            continue
        py = Path(sys.executable)
        _put(link, text=f'#!/bin/sh\nTEAM_GUARD_TOOL={name} TEAM_GUARD_ROOT="{WS.as_posix()}" '
                  f'TEAM_GUARD_CONFIG="{Path(CFG["config_path"]).as_posix()}" exec "{py.as_posix()}" -X utf8 "{guard.as_posix()}" "$@"\n',
             newline="\n")
        _put(_guard_dir() / f"{name}.cmd",
             text=f'@echo off\nsetlocal\nset "TEAM_GUARD_TOOL={name}"\nset "TEAM_GUARD_ROOT={WS}"\n'
                  f'set "TEAM_GUARD_CONFIG={CFG["config_path"]}"\n"{py}" -X utf8 "{guard}" %*\nexit /b %errorlevel%\n')


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


def domain_guide(ordered):
    """One line per domain: its name and the scope of the agent that implements it (the complex route's role if unset)."""
    R = CFG["routing"]
    default = next((r for k, r in R["pipeline"]["complex"] if k == "implement"), "")
    lines = []
    for d in ordered:
        scope = AGENTS.get(R["domain"].get(d, {}).get("implement", default), {}).get("scope", "")
        lines.append(f"- {d}: {scope}" if scope else f"- {d}")
    return "\n".join(lines)


def fmt(text):
    ordered = sorted(DOMAINS, key=CFG["routing"]["domains"].index)
    if "{domain_guide}" in text:
        text = text.replace("{domain_guide}", domain_guide(ordered))
    return (text.replace("{project}", CFG["project"]["name"]).replace("{change_noun}", noun())
            .replace("{domains}", "|".join(ordered)).replace("{docs}", ", ".join(CFG["project"]["docs"]))
            .replace("{state_dir}", CFG["project"]["state_dir"]))


def is_impl(kind):
    """True for the stages that change files: implement and plan_implement."""
    return teamcfg.norm_kind(kind) == "implement"


def kinds_of(stages):
    """Stage kinds a pipeline runs; plan_implement counts as both plan and implement."""
    ks = {k for k, *_ in stages}
    return ks | ({"plan", "implement"} if "plan_implement" in ks else set())


def _entries(route, domain, no_skip=False):
    """[(kind, agent, profile role)] of a route for a domain: domain agents applied, skipped stages dropped (never
    review; no_skip, set when a failed review upgraded the task, keeps them), the extra review appended."""
    R = CFG["routing"]
    if route and route.startswith("custom:"):  # parallel side task: one named role implements, a reviewer checks
        return [("implement", route.split(":", 1)[1], "mid"), ("review", R["side_task_reviewer"], R["side_task_reviewer"])]
    skip = frozenset() if no_skip else teamcfg.skip_set(CFG, route, domain)
    over = R["domain"].get(domain, {})  # [routing.domain.<name>]: agent per stage kind; unset = the route's role
    out = []
    for k, r in R["pipeline"][route if route in R["pipeline"] else "hard"]:
        if k not in skip:
            out.append((k, over.get("implement" if k == "plan_implement" else k, r), r))
    if R["extra_review_role"] and (route in R["extra_review_routes"] or domain in R["review_extra_domains"]):
        out.append(("review", R["extra_review_role"], R["extra_review_role"]))
    return out


def pipeline(route, domain, no_skip=False):
    return [(k, a) for k, a, _ in _entries(route, domain, no_skip)]


def task_stages(s):
    return pipeline(s["route"], s["domain"], s.get("no_skip"))


def skipped_kinds(s):
    """Stage kinds of the full cycle (plan, plan_review, implement, review) this task's route does not run."""
    if not s.get("route") or s["route"].startswith("custom:"):
        return []
    have = kinds_of(task_stages(s))
    return [k for k in teamcfg.DOMAIN_STAGES if k not in have]


def stage_profile(route, domain, i, no_skip=False):
    """The [roles] entry (cli, model, effort) stage i starts on: its agent's own, else the route's role for that stage."""
    _, agent, role = _entries(route, domain, no_skip)[i]
    return agent if agent in ROLES else role


def hist_entries(s):
    """(kind, agent, profile) of each finished stage: from the launch records, else from the stem (tasks from before them)."""
    by = {x["stem"]: x for x in s.get("launches", [])}
    out = []
    for h in s["history"]:
        m = re.match(r"\d+-(\w+?)-(\w+)$", h)
        old = m[2] if m else ""
        out.append((m[1] if m else "", by[h]["agent"] if h in by else old, by[h]["profile"] if h in by else old))
    return out


def pin_fits(agent, profile):
    """A pinned model only runs on a cli that serves it (profile swaps that change the cli are skipped). A floor
    (model without `pin = true` under [heuristic]) is a rank, not a cli: it never blocks a swap."""
    a = AGENTS.get(agent, {})
    pin = a.get("model") if a.get("pinned") else None
    return not pin or ROLES[profile][1] in {r["cli"] for r in CFG["roles"].values() if r["model"] == pin}


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
    text = re.sub(r"^\s*\**(STATUS|VERDICT|ROUTE|DOMAIN|TITLE|SKILLS|RISK|SIZE|SEVERITY|ESCALATE):.*$", "", text, flags=re.M).strip()
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


def read_state(d):
    """The task state in folder d, or None when it has none or it is unreadable."""
    try:
        s = json.loads((d / "state.json").read_text())
    except (OSError, ValueError):
        return None
    return s if isinstance(s, dict) and "id" in s else None


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


def role_text(agent):
    text = AGENTS[agent]["instructions"]
    return fmt(text) if text else f"You are the {ROLES[agent][0] if agent in ROLES else agent} of the {CFG['project']['name']} agent team."


def agent_skills_table(agent, task_skills=()):
    """'## Skills you have' table (name, path, when): paths only, the agent reads a file when it applies. Rows already
    attached to the task (same name or same file) are dropped: the task skill is inlined."""
    task_paths = {str((d / f"{n}.md").resolve()) for n, _ in task_skills for d in teamcfg._skill_dirs(CFG)}
    task_names = {n for n, _ in task_skills}
    rows = [k for k in AGENTS[agent].get("skills", []) if k["name"] not in task_names and k["path"] not in task_paths]
    if not rows:
        return ""
    return "## Skills you have\nRead a skill file when its situation applies; do not read the rest.\n" + \
        "\n".join(f"- {k['name']} | {k['path']} | {k['when']}" for k in rows)


def stage_skills(s, kind):
    """[(name, text)] of the task skills attached to this task for stage `kind` (ValueError when one cannot load)."""
    if kind in ("route", "refill", "learn"):
        return []
    out = {}
    for k in s.get("skills", []):
        if k["stage"] in ("", kind, *(("plan", "implement") if kind == "plan_implement" else ())) and k["name"] not in out:
            out[k["name"]] = teamcfg.load_skill(CFG, k["name"])
    return list(out.items())


def attach_skills(s, refs, who, pl=None):
    """Add (name, stage) refs to the task, deduped; warn about long texts and stages the pipeline does not run."""
    have = {(k["name"], k["stage"]) for k in s.setdefault("skills", [])}
    for name, stage in refs:
        if (name, stage) in have:
            continue
        have.add((name, stage))
        s["skills"].append({"name": name, "stage": stage})
        if len(teamcfg.load_skill(CFG, name)) > CLIP:
            live(f"[{s['id']}] warning: skill {name} is over {CLIP} chars")
        if stage and pl is not None and stage not in kinds_of(pl):
            live(f"[{s['id']}] warning: skill {name}@{stage} ({who}) never runs: no {stage} stage in this pipeline")


def diff_summary(path, limit=40):
    """'- file +added -removed' per file of a git or p4 diff, so a reviewer reads the right hunks (not all of changes.diff)."""
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return ""
    files, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"diff --git a/(.+?) b/|==== (\S+?)(?:#\d+)? - |^Index: (.+)$", line)
        if m:
            cur = files.setdefault(next(g for g in m.groups() if g), [0, 0])
        elif cur is not None and line[:1] in "+-" and line[:3] not in ("+++", "---"):
            cur[line[0] == "-"] += 1
    rows = [f"- {f} +{a} -{d}" for f, (a, d) in list(files.items())[:limit]]
    return "\n".join(rows + ([f"- ... {len(files) - limit} more"] if len(files) > limit else []))


def learnings_file():
    return RUNS / "learnings.md"


def learnings_note(kind):
    """## Learnings from earlier tasks (<state_dir>/learnings.md) for every stage but refill."""
    try:
        text = learnings_file().read_text().strip() if kind != "refill" else ""
    except OSError:
        text = ""
    return f"## Learnings from earlier tasks\n{text}" if text else ""


def rounds_line(s):
    return (f"plan rounds {s['plan_rounds']}, failed implementations {s.get('impl_fails', 0)}, review verdicts "
            f"{s.get('review_rounds_total', 0)}, first review passed: {s.get('first_pass', 'n/a')}, escalations "
            f"{s.get('escalations', 0)}, route upgrades {s.get('upgrades', 0)}, user notes {len(s['notes'])}")


def eventful(s):
    """Whether a finished task taught anything: a failed first review or plan, an escalation, an upgrade or a note."""
    return (s.get("first_pass") is False or s["plan_rounds"] or s.get("impl_fails") or s.get("escalations")
            or s.get("upgrades") or s["notes"])


def learn(s):
    """At done: a cheap read-only Producer call folds what this task taught into learnings.md (at most 20 short
    bullets), under a lock so parallel tasks do not lose each other's updates. Never changes the task's outcome."""
    if not eventful(s):
        return
    status, reason = s["status"], s["reason"]
    with (RUNS / ".lock-learnings").open("a") as f:
        teamcfg.lock(f)
        try:
            out, text, _, _ = run_agent(s, "learn", "producer")
        except Exception as e:  # noqa: BLE001 - a learning is never worth a failed task
            out, text = None, None
            live(f"[{s['id']}] learn failed: {e}")
        if out:
            bullets = [" ".join(ln.strip().split()[:26]) for ln in body(text).splitlines() if ln.strip().startswith("- ")]
            if bullets and not body(text).strip().startswith("UNCHANGED"):
                _atomic_write(learnings_file(), "\n".join(bullets[:LEARN_MAX]) + "\n")
                live(f"[{s['id']}] learnings: {len(bullets[:LEARN_MAX])} items")
        elif s["status"] != status:
            live(f"[{s['id']}] learn stage gave nothing ({s['reason']}); learnings unchanged")
    s["status"], s["reason"] = status, reason


def tidy(s):
    """Fold the task's raw agent logs into state.json `runs` (token rows for `team tokens`) and delete them with the
    prompt copies. The stage hand-offs, changes.diff and state stay: the review page and `team redo` need them."""
    d = task_dir(s["id"])
    for k, v in task_times(s).items():  # tasks from before the time fields date themselves by their prompt files
        if k not in s and v is not None:
            s[k] = v
    runs = {r["stem"]: r for r in s.get("runs", [])}  # a redone task keeps the rows of its earlier rounds
    runs.update({r["stem"]: r for r in tokens.log_runs(d)})
    if runs:
        s["runs"] = sorted(runs.values(), key=lambda r: int(r["stem"].split("-", 1)[0]))
    freed = 0
    for f in [*(d / "logs").glob("*.jsonl"), *(d / "logs").glob("*.prompt.md")]:
        try:
            freed += f.stat().st_size
            f.unlink()
        except OSError:
            pass
    s.pop("sessions", None)
    return freed


def lock_note():
    """The shared-resource rule for stages that run commands: lease a [locks] resource only while it is in use."""
    names = [n for n in CFG["locks"]["names"] if n != "none"]
    if not names:
        return ""
    cmd = f'"{Path(sys.executable).as_posix()}" "{(HERE / "team.py").as_posix()}"'
    return (f"## Shared resources\nLocks: {', '.join(names)}. Hold one only while you use it:\n"
            f"- before starting it: `{cmd} lock <name> --wait 540` (exit 3: still busy; run it again, or report BLOCKED);\n"
            f"- as soon as you stop it: `{cmd} unlock <name>`. Your locks are freed anyway when the task's run ends.")


def prompt_parts(s, kind, agent, skills=()):
    """The prompt as [(key, text)] sections in order; a resumed session gets only the sections it has not seen."""
    d = task_dir(s["id"])
    probes = env_status()
    parts = [("role", role_text(agent)),
             ("skills", agent_skills_table(agent, skills) if kind not in ("route", "refill", "learn") else ""),
             ("common", fmt(teamcfg.template(CFG, "roles/common.md"))),
             ("vcs", fmt(teamcfg.template(CFG, f"vcs/{CFG['vcs']['kind']}.md"))),
             ("learnings", learnings_note(kind)),
             ("locks", lock_note() if is_impl(kind) else ""),
             ("task", f"Task {s['id']} | {noun()} {s['change']} | folder {d} | {s.get('route')}/{s.get('domain')}"
              + (f" | {probes}" if probes else "")),
             ("request", "## Request\n" + s["request"])]
    parts = [p for p in parts if p[1]]
    parts += [(f"skill:{n}", f"## Skill: {n}\n{x}") for n, x in dict(skills).items()]
    for label, key in (("Spec", "spec"), ("Plan", "plan"), ("Report", "report")):
        if s.get(key) and kind != "route" and not (key == "plan" and s.get("plan") == s.get("report")):  # plan_implement: one handoff
            parts.append((key, f"## {label}\n" + body(Path(s[key]).read_text())))
    if kind == "review" and (summary := diff_summary(d / "changes.diff")):
        parts.append(("changed", f"## Changed files ({d / 'changes.diff'})\n" + summary))
    feedback = s["plan_reviews"] + (s["reviews"] if kind == "plan" else []) if kind in ("plan", "plan_review") else s["reviews"]
    if kind != "route":
        parts += [(f"findings:{Path(r).stem}", f"## Earlier findings ({Path(r).stem})\n" + body(Path(r).read_text()))
                  for r in feedback]
    if kind != "route" and s.get("diagnose") == kind:
        parts.append(("diagnose", "## Diagnosis required\nA reviewer rated the last failure critical or recommended "
                      "escalation. Before changing anything, state the root cause and why the earlier attempt missed it, "
                      "then fix that."))
    if kind == "learn":
        parts.append(("rounds", "## How it went\n" + rounds_line(s)))
    if not is_impl(kind) and CFG["prompts"]["readonly_note"]:
        parts.append(("readonly", CFG["prompts"]["readonly_note"]))
    if s["notes"]:
        parts.append(("notes", "## User notes\n" + "\n".join(f"- {n}" for n in s["notes"])))
    job = fmt(teamcfg.template(CFG, f"jobs/{kind}.md"))
    if kind == "route":
        job = job.replace("{skills}", "\n".join(f"- {n}: {x}" for n, x in teamcfg.list_skills(CFG).items()) or "(none)")
    parts.append(("job", "## Job\n" + job))
    return parts


def build_prompt(s, kind, agent, skills=()):
    return "\n\n".join(t for _, t in prompt_parts(s, kind, agent, skills))


def section_hashes(parts):
    return {k: hashlib.sha1(t.encode()).hexdigest()[:12] for k, t in parts}


def own_sections(kind, stem, text):
    """The prompt sections a stage's own output becomes in later rounds: its session has them in context already."""
    if kind in ("review", "plan_review"):
        return [(f"findings:{stem}", f"## Earlier findings ({stem})\n" + body(text))]
    return [("plan" if kind == "plan" else "report", f"## {'Plan' if kind == 'plan' else 'Report'}\n" + body(text))]


def resume_prompt(parts, seen):
    """A resumed round: the sections whose text changed since the session last saw them, then the job."""
    new = [t for k, t in parts if k != "job" and seen.get(k) != section_hashes([(k, t)])[k]]
    return "\n\n".join([RESUME_LINE, *new, parts[-1][1]])


def slim(ev):
    """The event as stored in the raw log: tool output (already in the agent's context, often the bulk of the log) is
    kept as its size, and the Claude init event as its ids; None: store the line unchanged."""
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        return {k: ev[k] for k in ("type", "subtype", "session_id", "model") if k in ev}
    if t == "user":
        ev = dict(ev)
        ev.pop("tool_use_result", None)  # a second copy of the tool result
        msg = ev.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), list):
            ev["message"] = dict(msg, content=[dict(b, content={"chars": len(str(b.get("content")))})
                                               if isinstance(b, dict) and b.get("type") == "tool_result" else b
                                               for b in msg["content"]])
        return ev
    item = ev.get("item")
    if isinstance(item, dict) and isinstance(item.get("aggregated_output"), str):  # Codex command output
        return dict(ev, item=dict(item, aggregated_output={"chars": len(item["aggregated_output"])}))
    return None


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


def agent_cmd(cli, model, effort, readonly, out, session=None, resume=False):
    """The CLI argv for one stage. session: the Claude session id to create (or, with resume, the Claude session or
    Codex thread to continue); a fresh Codex run reports its thread id in its events."""
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
        # user MCP servers and plugin skills are re-sent every turn (82k vs 6k tokens on a read-only stage): skip them
        if CFG["agents"]["mcp"] == "none" or (readonly and CFG["agents"]["mcp"] == "write"):
            cmd += ["--strict-mcp-config"]
        if not CFG["agents"]["user_skills"]:
            cmd += ["--disable-slash-commands"]
        if session:
            cmd += ["--resume" if resume else "--session-id", session]
        return cmd
    # `exec resume` has no -C (Popen runs in WS anyway) and no -s (the sandbox goes in as sandbox_mode)
    cmd = ["codex", "exec", *(["resume"] if resume else []), "-m", model, "-c", f'model_reasoning_effort="{effort}"',
           *([] if resume else ["-C", str(WS)]), "--skip-git-repo-check", "--json", "-o", str(out)]  # Perforce and other non-git workspaces
    if CFG["agents"]["mcp"] == "none" or (readonly and CFG["agents"]["mcp"] == "write"):
        cmd += codex_mcp_off()
    if not readonly and VCS.sandbox_network:  # p4 edit/add must reach the server from the sandbox
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    # [agents] codex_sandbox for writers, whatever the user's Codex config says: danger-full-access (default) runs
    # without a sandbox (editors, GPU, WSL interop) and sends what Codex asks to approve to its automatic reviewer, like
    # Claude's auto mode; workspace-write keeps writes inside the workspace and .git read-only; user = the user's own
    # Codex config. Read-only stages always run -s read-only.
    tail = [session, "-"] if resume else ["-"]
    sandbox = CFG["agents"]["codex_sandbox"]
    if not readonly and sandbox == "user":
        return cmd + tail
    mode = "read-only" if readonly else sandbox
    if mode == "danger-full-access":
        cmd += ["-c", 'approval_policy="on-request"', "-c", 'approvals_reviewer="auto_review"']
    return cmd + (["-c", f'sandbox_mode="{mode}"'] if resume else ["-s", mode]) + tail



def codex_mcp_off():
    """-c overrides disabling every Codex MCP server for one run. Codex merges `-c mcp_servers={}` into the user's
    table instead of replacing it and has no --strict-mcp-config, so each configured server gets enabled=false
    (Codex splits the -c path on every dot and keeps quotes, so names are passed bare). features.apps=false also
    drops the built-in ChatGPT apps connector server (codex_apps)."""
    names = set()
    for f in (Path(teamcfg.codex_home()) / "config.toml", WS / ".codex" / "config.toml"):
        try:
            names |= set(tomllib.loads(f.read_text()).get("mcp_servers", {}))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return ["-c", "features.apps=false"] + [a for n in sorted(names) for a in ("-c", f"mcp_servers.{n}.enabled=false")]

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
            sc = U["scoped_limit"]  # a model-scoped weekly limit (own window): diverts one role, or guards the apex tier
            _usage["scoped_pct"] = u.get(sc["label"], 0) if sc else 0
            _usage["scoped_high"] = bool(sc) and _usage["scoped_pct"] >= sc["threshold"]
            _usage["low"] = any(u.get(k, 0) >= v for k, v in U["limits"].items())
            _usage["mode"] = route_mode(u)
            _usage["ok_t"], _usage["fail"] = time.time(), False
        except Exception:
            _usage["fail"] = True  # unknown usage: keep the last answer for balancing, but the heuristic ignores it
    return _usage["low"]


def usage_input():
    """(state, why) for the heuristic's `usage` input: low | claude | codex | mixed from a fresh successful read of the
    usage data, else (None, why): stale or missing data never matches a rule."""
    if not CFG["routing"]["usage"]["enabled"]:
        return None, "usage balancing is disabled"
    if _usage["fail"]:
        return None, "the last usage read failed"
    if time.time() - _usage["ok_t"] > 120:
        return None, "usage data is older than 120s"
    return ("low" if _usage["low"] else _usage["mode"]), ""


def burst_active():
    """[routing.usage].burst_file in state_dir holds an epoch deadline: user-requested spend of a scarce budget."""
    name = CFG["routing"]["usage"]["burst_file"]
    try:
        return bool(name) and time.time() < float((RUNS / name).read_text().strip())
    except (OSError, ValueError):
        return False


def apex_guard(s, ctx, role, burst):
    """[routing.usage.scoped_limit] without a role guards the apex tier's claude profile: while the scoped window is at
    or above its threshold (unless a burst is active) or the Claude limits are reached, a stage stepped up to apex runs
    the tier's codex profile instead (ctx["prefer"]), or, without one, returns why it goes to the user. `team approve`
    on that hand-off lets the task spend the apex tier."""
    sc, h = CFG["routing"]["usage"]["scoped_limit"], ctx.get("h") if ctx else None
    top = teamcfg.apex_rank(h)
    if not sc or sc.get("role") or top is None or ctx["rank"] != top or ctx["rank"] <= ctx["own"] or s.get("apex_approved"):
        return None
    t, cli = h["tiers"][top], ROLES[role][1]
    if (t[cli] or t["codex" if cli == "claude" else "claude"])["cli"] != "claude":
        return None
    low = claude_low()
    if not low and (burst or not _usage.get("scoped_high")):
        return None
    why = "Claude usage low" if low else f"{sc['label']} at {_usage.get('scoped_pct', 0):.0f}% >= {sc['threshold']:.0f}%"
    if t["codex"]:
        ctx["prefer"] = "codex"
        live(f"[{s['id']}] apex guard ({why}): {t['claude']['role']} -> {t['codex']['role']} (Codex)")
        return None
    return (f"apex guard ({why}): the step up to {t['claude']['role']} needs the user; `team approve` spends it on this "
            f"task, `team burst <hours>` lifts the guard")


def ladder(s, kind):
    """The task's heuristic snapshot ({tiers, rules}), taken from the config at its first decision so that a later
    config edit cannot change a task in flight. None: no table (and the refill pseudo-task never uses one)."""
    if kind in ("refill", "learn"):  # learn: one cheap read-only call at the end, on its own profile
        return None
    if "heuristic" not in s and CFG["heuristic"]:
        s["heuristic"] = json.loads(json.dumps(CFG["heuristic"]))
    return s.get("heuristic")


def run_agent(s, kind, agent, profile=None):
    """Run one stage; returns (out, text, agent, profile) with the agent and [roles] profile it finally used."""
    h = ladder(s, kind)
    ctx = None
    if h:
        agent, role, burst, ctx = _select_tiered(s, kind, agent, profile or agent, h)
        why = apex_guard(s, ctx, role, burst)
        if why:  # the apex tier is guarded and has no codex profile: the user decides
            s["capped"], s["apex_guard"] = kind, True  # `team approve` retries at the apex tier
            s["escalations"] = s.get("escalations", 0) + 1
            s["status"], s["reason"] = "escalated", why
            return None, None, agent, role
    else:
        agent, role, burst = _select_agent_role(s, kind, agent, profile or agent)
    capacity = CFG["routing"]["capacity_fallback"]  # a model reporting 503 / "at capacity" is retried on another role
    tried = [role]
    while True:
        out, text = _run_agent_once(s, kind, agent, role, burst, ctx)
        if out or s["status"] != "failed" or role not in capacity or not capacity_error(s["reason"].rsplit("see ", 1)[-1]):
            return out, text, agent, role
        if capacity[role] in tried:  # a fallback cycle: every role in it is unavailable
            s["reason"] += f" (capacity: {' -> '.join(tried)} all unavailable)"
            return out, text, agent, role
        nxt = _move(ctx, s, agent, role, capacity[role], clamped=True)
        if not nxt:
            if ctx and ctx.get("h"):  # the heuristic never retries below the tier
                s["status"], s["reason"] = "blocked", s["reason"] + f" (capacity: no profile at or above tier {ctx['h']['tiers'][ctx['tier']]['name']} left to retry)"
            else:
                s["reason"] += f" (capacity: {agent} is pinned to a model that {capacity[role]} cannot run)"
            return out, text, agent, role
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


def _move(ctx, s, agent, role, new, clamped=False):
    """`new` when a swap role -> new is allowed, else None. Without a heuristic context only a pinned model can refuse.
    Under a heuristic the swap may not drop below the tier: a replaced swap (usage balancing) only picks the cli of the
    current rank, a clamped one (gate, capacity) needs a profile on a rank >= the tier. A stage at its own profile's
    rank (no rule, floor or step above it) swaps as without a heuristic, but not below the rules' tier."""
    if not ctx or not ctx.get("h"):
        return new if pin_fits(agent, new) else None
    h, tier = ctx["h"], ctx["h"]["tiers"][ctx["tier"]]["name"]
    if ctx["rank"] <= ctx["own"]:
        r = teamcfg.own_rank(h, new, ROLES[new][2], ROLES[new][3])
        if r < ctx["tier"] or not pin_fits(agent, new):
            live(f"[{s['id']}] heuristic: {role} -> {new} skipped, it is below tier {tier}")
            return None
        ctx["rank"] = ctx["own"] = r
        return new
    if clamped:
        r = teamcfg.role_rank(h, new)
        if r is None or r < ctx["tier"]:
            live(f"[{s['id']}] heuristic: {role} -> {new} skipped, it is below tier {tier}")
            return None
        ctx["rank"] = max(ctx["rank"], r)
    elif not h["tiers"][ctx["rank"]][ROLES[new][1]]:
        live(f"[{s['id']}] heuristic: {role} -> {new} skipped, tier {h['tiers'][ctx['rank']]['name']} has no {ROLES[new][1]} profile")
        return None
    return new


def _reassign(s, kind, agent, role):
    """Per-task role_override entries: (agent, role, forced); forced = an override applied."""
    forced = False
    try:  # per-task overrides run after automatic role selection
        ov = json.loads((RUNS / "role_override.json").read_text()).get(s["id"], {})
        if kind in ("plan", "plan_review", "review") and ov.get(kind) in ROLES:
            live(f"[{s['id']}] Override: {role} -> {ov[kind]}")
            agent = role = ov[kind]
            forced = True
        if is_impl(kind) and ov.get("implement") in ROLES and s["review_rounds"] >= ov.get("after_failed_reviews", 1):
            live(f"[{s['id']}] Override after failed review: {role} -> {ov['implement']}")
            agent = role = ov["implement"]
            forced = True
    except (OSError, ValueError):
        pass
    return agent, role, forced


def _swap_roles(s, kind, agent, role, ctx=None):
    """(role, burst) after usage balancing. ctx: heuristic context (None = legacy pin_fits rules)."""
    R = CFG["routing"]
    U = R["usage"]
    # Cheap roles implement, expensive ones review: [routing.usage].cheap_first roles start on their fallback unless a
    # previous attempt failed.
    failed = s.get("failed") or s["plan_rounds"] >= 1 or s["review_rounds"] >= 1
    claude_low()  # refreshes _usage
    burst = burst_active()  # a user-requested burst spends Claude like a surplus
    surplus = _usage.get("mode") == "claude" or burst  # Claude has the longer runway or is about to lose budget: spend it, save Codex
    codex_first = _usage.get("mode") == "codex" and not burst and role in U["claude_fallback"]  # Codex has the longer runway
    cheap_first = role in U["cheap_first"] and not failed and not surplus
    if surplus and not claude_low():  # swap Codex roles to Claude to conserve Codex
        swap = dict(U["surplus_swap"], **(U["burst_swap"] if burst else {}))
        new = _move(ctx, s, agent, role, swap[role]) if role in swap else None
        if new:
            live(f"[{s['id']}] Claude surplus: {role} -> {new}")
            role = new
    new = _move(ctx, s, agent, role, U["claude_fallback"][role]) if codex_first else None
    if new:
        live(f"[{s['id']}] Codex first: {role} -> {new} (Codex)")
        role = new
    gate = U["escalation_gate"]  # scarce top role only after cheaper rounds failed
    if gate and role == gate["role"] and not burst and not s.get("failed") and max(s["plan_rounds"], s["review_rounds"]) < gate.get("after_rounds", 2):
        if kind == "review" and s["history"] and hist_entries(s)[-1][::2] == ("review", gate["first"]):
            # second review right after a passing first review: an independent opinion from another provider
            swapped = gate["second_review"]
            msg = f"Second review: {role} -> {swapped} ({gate['first']} already passed it)"
        else:
            swapped, msg = gate["first"], f"{gate['first']} first: {role} -> {gate['first']}"
        if _move(ctx, s, agent, role, swapped, clamped=True):
            live(f"[{s['id']}] {msg}")
            role = swapped
    scoped = U["scoped_limit"]
    if ROLES[role][1] == "claude" and role in U["claude_fallback"] and (
            cheap_first or codex_first or claude_low() or (scoped and role == scoped.get("role") and _usage.get("scoped_high"))):
        new = _move(ctx, s, agent, role, U["claude_fallback"][role])
        if new:
            live(f"[{s['id']}] {'Codex first' if cheap_first or codex_first else 'Claude usage low'}: {role} -> {new} (Codex)")
            role = new
    return role, burst


def _select_agent_role(s, kind, agent, role):
    """(agent, profile, burst). A role_override or takeover `to` reassigns agent and profile; usage swaps only the profile."""
    role, burst = _swap_roles(s, kind, agent, role)
    agent, role, _ = _reassign(s, kind, agent, role)
    return agent, role, burst


def _select_tiered(s, kind, agent, profile, h):
    """(agent, profile, burst, ctx) under [heuristic]: the tier for this stage comes from the rule table, usage
    balancing only picks the cli (and clamped swaps stay at or above the tier). A pinned agent or a role_override keeps
    its exact profile, model and effort. ctx carries the ladder and the decision record to _run_agent_once."""
    agent, profile, forced = _reassign(s, kind, agent, profile)
    a = AGENTS[agent]
    if forced or a["pinned"]:
        why = "override" if forced else "pin"
        role, burst = (profile, burst_active()) if forced else _swap_roles(s, kind, agent, profile)
        return agent, role, burst, {"h": None, "record": {"kind": kind, "decided_by": why, "rules": []}}
    claude_low()  # refreshes _usage
    state, why = usage_input()
    known = kind != "route"  # routing decides risk and size: no risk or size rule matches the route stage itself
    inp = {"route": s.get("route"), "domain": s.get("domain"), "risk": s.get("risk", "high") if known else None,
           "size": s.get("size", "large") if known else None, "stage": kind, "failures": s.get("impl_fails", 0) + s["plan_rounds"], "usage": state}
    res = teamcfg.resolve(h, inp, a.get("model"), a.get("effort"))
    notes = []
    if state is None and any("usage" in r["when"] for r in h["rules"]):
        notes.append(f"usage ignored: {why}")
    floor = max([e["rank"] for e in s.get("stepped", []) if teamcfg.norm_kind(e["kind"]) == teamcfg.norm_kind(kind) and e["rank"] < len(h["tiers"])], default=None)
    if floor is not None and floor > res["rank"]:  # an escalation step (see escalate) raises the tier
        res = {**res, "rank": floor, "tier": h["tiers"][floor]["name"], "decided_by": "step-up"}
        notes.append(f"step-up: {kind} retried at tier {res['tier']}")
    last = (s.get("launches") or [{}])[-1]
    prev = last.get("heuristic") or {}
    if prev.get("tier_rank") is not None and last.get("stem") not in s["history"] and prev.get("kind") == kind \
            and last.get("agent") == agent and prev["tier_rank"] < len(h["tiers"]):
        res = {**res, "rank": prev["tier_rank"], "tier": h["tiers"][prev["tier_rank"]]["name"], "decided_by": "resume"}
        notes.append("resume: reused the tier of the unfinished launch")
    # the stage's own [roles] profile is a floor: at its rank (see teamcfg.own_rank) it runs that profile itself, so only a
    # rule, floor or step above it changes the model; "tier" keeps the rules' minimum for swaps
    tier, own = res["rank"], teamcfg.own_rank(h, profile, ROLES[profile][2], ROLES[profile][3])
    if own > res["rank"]:
        res = {**res, "rank": own, "tier": h["tiers"][own]["name"], "decided_by": "profile"}
    ctx = {"h": h, "tier": tier, "rank": res["rank"], "own": own, "effort_min": res["effort_min"],
           "record": {"kind": kind, "inputs": inp, "tier": res["tier"], "tier_rank": res["rank"], "rules": res["rules"],
                      "decided_by": res["decided_by"], "notes": notes}}
    role, burst = _swap_roles(s, kind, agent, profile, ctx)
    return agent, role, burst, ctx


def _assignment(ctx, role, burst):
    """(cli, model, effort, ladder role) the tiered stage runs on, and the record of it in ctx."""
    no_burst = CFG["routing"]["usage"]["no_burst_effort"]
    cap = no_burst.get(role) if not burst else None  # high effort only during a user-requested burst
    if ctx["rank"] <= ctx["own"]:  # not raised above the stage's own profile: it runs unchanged
        _, cli, model, effort = ROLES[role]
        effort = teamcfg.bound_effort(cli, effort, cap, ctx["effort_min"])
        prof = role
    else:
        cli, prof, model, effort = teamcfg.assign(ctx["h"], ctx["rank"], ctx.get("prefer") or ROLES[role][1], cap, ctx["effort_min"])
    ctx["record"].update(rank=ctx["rank"], tier_final=ctx["h"]["tiers"][ctx["rank"]]["name"], assigned=prof,
                         cli=cli, model=model, effort=effort)
    return cli, model, effort, prof


def _run_agent_once(s, kind, agent, role, burst, ctx=None):
    """One launch. A work or review stage continues the session its kind/agent pair last ran on the same cli and model
    ([agents] resume), sending only the prompt sections that changed; a resume the CLI refuses starts fresh once."""
    name, cli, model, effort = ROLES[role]
    if ctx and ctx.get("h"):  # the tiered profile decides cli, model and effort
        cli, model, effort, _ = _assignment(ctx, role, burst)
    else:
        if not burst and role in CFG["routing"]["usage"]["no_burst_effort"]:
            effort = CFG["routing"]["usage"]["no_burst_effort"][role]  # high effort only during a user-requested burst
        pin = AGENTS[agent]
        if pin["pinned"]:
            model, effort = pin.get("model", model), pin.get("effort", effort)  # the agent's pin is exact
        if ctx:
            ctx["record"].update(cli=cli, model=model, effort=effort, assigned=role)
    name = ROLES[agent][0] if agent in ROLES else agent
    d = task_dir(s["id"])
    try:  # before the launch record: a missing skill file fails the stage without a launch
        skills = stage_skills(s, kind)
    except ValueError as e:
        s["status"], s["reason"] = "failed", f"{e}: restore skills/<name>.md or remove it from {d / 'state.json'} `skills`"
        return None, None
    s["n"] += 1
    stem = f"{s['n']:02d}-{kind}-{agent}"
    launch = {"stem": stem, "agent": agent, "profile": role, "cli": cli, "model": model, "effort": effort}
    key = f"{kind}/{agent}" if CFG["agents"]["resume"] and kind in RESUME_KINDS else None
    prev = (s.get("sessions") or {}).get(key) if key else None
    resume = bool(prev and prev["cli"] == cli and prev["model"] == model)
    sid = prev["id"] if resume else (str(uuid.uuid4()) if key and cli == "claude" else None)
    if key:
        launch.update(session=sid, resumed=resume)
    if ctx:
        launch["heuristic"] = dict(ctx["record"])  # inputs, rules, tier and assignment: audited, and a resume reuses its tier
    s.setdefault("launches", []).append(launch)  # saved before the launch: readers see what runs now
    if kind != "refill":  # the refill log is merged under its own lock
        save(s)
    out, raw = d / f"{stem}.md", d / "logs" / f"{stem}.jsonl"
    raw.parent.mkdir(exist_ok=True)
    if kind not in ("route", "refill", "learn"):
        write_snapshot(s)
    parts = prompt_parts(s, kind, agent, skills)
    text = resume_prompt(parts, prev["seen"]) if resume else "\n\n".join(t for _, t in parts)
    (d / "logs" / f"{stem}.prompt.md").write_text(text)
    ensure_guards()
    env = dict(os.environ, TEAM_TASK=s["id"], TEAM_CHANGE=str(s["change"]), TEAM_ROLE=agent, TEAM_STAGE=stem,
               TEAM_CONFIG=CFG["config_path"], PATH=f"{_guard_dir()}{os.pathsep}{_clean_path()}")
    for tool in CFG["vcs"]["guard_names"]:  # used by the edit hook; the guard falls back to a PATH search
        real = shutil.which(tool, path=_clean_path())
        if real:
            env[f"TEAM_REAL_{tool.upper()}"] = real
        else:
            env.pop(f"TEAM_REAL_{tool.upper()}", None)
    cmd = teamcfg.command(agent_cmd(cli, model, effort, not is_impl(kind), out, sid, resume), path=env["PATH"])

    if ctx:
        r = ctx["record"]
        live(f"[{s['id']}] heuristic {kind}: {r.get('tier_final') or r.get('tier') or r['decided_by']} via {r['decided_by']}"
             f" (rules: {', '.join(r['rules']) or 'none'}) -> {r['assigned']} {cli} {model} {effort}"
             + "".join(f"; {n}" for n in r.get("notes", [])))
    live(f"[{s['id']}] {name} ({model}, {effort}): {kind}" + (" (resumed)" if resume else ""))
    final = timer = got = None
    spoke = False  # any assistant output: a failed resume without it is retried fresh
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
                try:
                    ev = json.loads(line)
                    msg, result = summarize(cli, ev)
                except (json.JSONDecodeError, AttributeError):
                    ev, msg, result = None, line.strip() or None, None
                small = slim(ev) if isinstance(ev, dict) else None
                rawf.write(line if small is None else json.dumps(small) + "\n")  # CLI errors and the rest: as is
                rawf.flush()
                if msg:
                    live(f"[{name}] {msg[:600]}")
                if result is not None:
                    final = result
                if isinstance(ev, dict):
                    got = ev.get("thread_id") if ev.get("type") == "thread.started" else ev.get("session_id") or got
                    spoke = spoke or ev.get("type") in ("assistant", "item.completed")
                if cli == "codex" and is_impl(kind) and isinstance(ev, dict):
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
        if resume and not spoke:  # the CLI could not continue the session (pruned, expired): start over once
            live(f"[{s['id']}] resume failed, fresh session")
            s["sessions"].pop(key)
            return _run_agent_once(s, kind, agent, role, burst, ctx)
        s["status"], s["reason"] = "failed", f"{name} exited {rc} with no result; see {raw}"
        return None, None
    if key and (got or sid):
        seen = dict(prev["seen"]) if resume else {}
        s.setdefault("sessions", {})[key] = {"cli": cli, "model": model, "id": got or sid,
                                             "seen": seen | section_hashes(parts + own_sections(kind, stem, text))}
        launch["session"] = got or sid
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
    out, text, _, _ = run_agent(s, "route", "producer")
    if not out:
        return
    s["spec"] = out
    route, _ = tag(text, "ROUTE")
    domain, _ = tag(text, "DOMAIN")
    _, title = tag(text, "TITLE")
    set_risk_size(s, tag(text, "RISK")[0], tag(text, "SIZE")[0])
    s["title"] = title or s["request"].splitlines()[0][:60]
    route = teamcfg.canon_route(route)
    route = lighter_guard(s, route)
    if route in ROUTES and domain in DOMAINS:
        suggest_skills(s, text, route, domain)
    VCS.set_description(s["change"], f"[team {s['id']}] {s['title']}")
    if route == "ask":
        s["status"], s["reason"] = "blocked", f"Producer needs a decision; see `team review {s['id']}`, then `team redo`."
    elif route not in ROUTES or domain not in DOMAINS:
        s["status"], s["reason"] = "failed", f"Producer gave ROUTE={route} DOMAIN={domain}"
    else:
        s["route"], s["domain"], s["stage"] = route, domain, 0
        s.setdefault("route_initial", route)
        s["skipped"] = skipped_kinds(s)
        live(f"[{s['id']}] routed {route}/{domain}: {s['title']}" + (f" (skipped: {', '.join(s['skipped'])})" if s["skipped"] else ""))


def lighter_guard(s, route):
    """The Producer's route, or the `team new --route` one, raised when a lighter route is unsafe: high risk or earlier
    failed attempts -> complex; a lighter forced route over a hard verdict stays hard. ask is never changed."""
    forced = teamcfg.canon_route(s.get("route_forced") or "")
    if forced in ROUTES and route != "ask":
        if route == "hard" and forced in teamcfg.LIGHT_ROUTES:
            s["notes"].append(f"Route {forced} refused: the Producer rated the task hard.")
            live(f"[{s['id']}] route {forced} refused, kept hard")
        else:
            route = forced
    if route not in teamcfg.LIGHT_ROUTES:
        return route
    why = ("high risk" if s.get("risk") == "high" else
           "earlier failed attempts" if s.get("impl_fails") or s.get("plan_rounds") or s.get("no_skip") else "")
    if why:
        live(f"[{s['id']}] route {route} raised to complex: {why}")
        s["notes"].append(f"Route {route} raised to complex: {why}.")
        return "complex"
    return route


def set_risk_size(s, risk, size):
    """Record the task's risk and size for the heuristic. A missing or invalid value keeps an earlier one, else
    defaults to high/large (the strongest assumption), with a warning when a [heuristic] table would use it."""
    for key, val, ok, default in (("risk", risk, teamcfg.RISKS, "high"), ("size", size, teamcfg.SIZES, "large")):
        if val in ok:
            s[key] = val
        elif key not in s:
            s[key] = default
            if CFG["heuristic"]:
                live(f"[{s['id']}] warning: no valid {key.upper()} ({val or 'missing'}), using {default}")


def suggest_skills(s, text, route, domain):
    """The Producer's `SKILLS:` line: unknown names, bad stages and repeats are dropped with a warning."""
    refs = []
    for tok in teamcfg.skill_tokens(" ".join(x for x in tag(text, "SKILLS") if x)):
        try:
            name, stage = teamcfg.parse_skill_ref(tok)
            teamcfg.load_skill(CFG, name)
        except ValueError as e:
            live(f"[{s['id']}] warning: Producer skill {tok} dropped: {e}")
            continue
        refs.append((name, stage))
    attach_skills(s, refs, "Producer")
    stages = {k for k, _ in pipeline(route, domain)}  # the user's `--skill name@stage` faces the routed pipeline too
    for k in s.get("skills", []):
        if k["stage"] and k["stage"] not in stages:
            live(f"[{s['id']}] warning: skill {k['name']}@{k['stage']} never runs: no {k['stage']} stage in this pipeline")


def step(s, stages):
    kind, agent = stages[s["stage"]]
    profile = stage_profile(s["route"], s["domain"], s["stage"], s.get("no_skip"))
    tk = CFG["routing"]["takeover"].get(agent)  # [routing.takeover.<role>]: optional explicit `to` agent
    if is_impl(kind) and tk and tk.get("to") and takeover_due(s, agent, tk):
        agent = profile = tk["to"]
    out, text, agent, role = run_agent(s, kind, agent, profile)
    if not out:
        return
    who = ROLES[agent][0] if agent in ROLES else agent
    if kind in ("plan", "implement", "plan_implement"):
        if kind != "implement":  # plan_implement: the plan is the first section of its report
            s["plan"] = out
        if kind != "plan":
            s["report"] = out
        status, reason = tag(text, "STATUS")
        if status == "done":
            s["stage"] += 1
        elif status in ("gate", "blocked"):
            s["status"], s["reason"] = status, f"{who}: {reason}"
        else:
            s["status"], s["reason"] = "failed", f"{who} gave no STATUS line"
        return
    verdict, _ = tag(text, "VERDICT")
    sev, _ = tag(text, "SEVERITY")
    esc, esc_why = tag(text, "ESCALATE")
    esc = esc == "yes"
    feedback = "plan_reviews" if kind == "plan_review" else "reviews"
    rounds, target = ("plan_rounds", "plan") if kind == "plan_review" else ("review_rounds", "implement")
    if kind == "review" and verdict in ("pass", "fail"):
        s["review_rounds_total"] = s.get("review_rounds_total", 0) + 1
        s.setdefault("first_pass", verdict == "pass" and not esc)  # decided once, by the first review verdict
    if verdict == "pass" and not esc:
        if s.get("diagnose") == target:
            s.pop("diagnose")
        s["stage"] += 1
        return
    if verdict not in ("pass", "fail"):
        s["status"], s["reason"] = "failed", f"{who} gave no VERDICT line"
        return
    if sev not in SEVERITIES:  # a failing review without a valid severity counts as major
        sev = "major"
    s[feedback] = [out]  # only the latest findings travel forward
    s[rounds] += 1
    if kind != "plan_review":
        s["impl_fails"] = s.get("impl_fails", 0) + 1  # cumulative, survives escalation retries
    if kind == "review" and upgrade(s, out, sev, esc, esc_why):
        return
    ti = next(i for i, (k, _) in enumerate(stages) if teamcfg.norm_kind(k) == target)
    severe = esc or sev in ("major", "critical")  # minor: no step
    reasons = ([f"severity {sev}"] if sev != "minor" else []) + ([f"recommended: {esc_why}"] if esc else [])
    if target == "implement":
        reasons += count_triggers(s, stages[ti][1])
    refused = escalate(s, stages, ti, reasons) if reasons else None
    if esc or sev == "critical":
        s["diagnose"] = target
    if not (severe and refused):
        s.pop("capped", None)  # only a refused severe step marks the cap for `team approve`
    if severe and refused:  # a major failure that cannot step up goes to the user
        s["failed"] = True
        s["escalations"] = s.get("escalations", 0) + 1
        s["status"], s["reason"] = "escalated", f"{target} failed review ({sev}{', escalation recommended' if esc else ''}): {refused}; see {out}"
        return
    if not severe:
        n = s.setdefault("minor_rounds", {})
        n[target] = n.get(target, 0) + 1
        if n[target] > MAX_ROUNDS:
            s["failed"] = True
            s["escalations"] = s.get("escalations", 0) + 1
            s["status"], s["reason"] = "escalated", f"{target} failed review {n[target]} times (minor); see {out}"
            return
    s["stage"] = ti
    live(f"[{s['id']}] review failed ({sev}), back to {target} (round {s[rounds]})")


SEVERITIES = ("minor", "major", "critical")


def upgrade(s, out, sev, esc, esc_why):
    """A failed review on a route that skipped its plan retries on a fuller pipeline: direct/bundled -> planned,
    planned -> complex, a configured skip -> dropped (no_skip). The retry restarts at the plan stage with the review
    findings. It counts as a heuristic failure (see _select_tiered) and as an upgrade in the route metrics. Returns
    True when it took over the retry. hard, custom and legacy simple routes never upgrade."""
    route = s["route"]  # a stored legacy "simple" keeps its old behaviour: only the new route names upgrade
    new = teamcfg.UPGRADE.get(route)
    if not new and (s.get("no_skip") or not teamcfg.skip_set(CFG, route, s["domain"])):
        return False
    old = stage_label(s)
    s["no_skip"] = True
    if new:
        s["route"] = new
    for e in s.get("stepped", []):
        e["kind"] = teamcfg.norm_kind(e["kind"])
    stages = task_stages(s)
    s["stage"] = next(i for i, (k, _) in enumerate(stages) if k == "plan")
    s["upgrades"] = s.get("upgrades", 0) + 1
    s["skipped"] = skipped_kinds(s)
    s.pop("capped", None)
    if esc or sev == "critical":
        s["diagnose"] = "plan"
    live(f"[{s['id']}] review failed ({sev}) on a skipped-plan route: upgraded {route} -> {s['route']}, "
         f"back to plan (was {old}); findings {out}")
    return True


def takeover_due(s, agent, tk):
    """[routing.takeover.<role>]: the failed-review or first-attempt condition."""
    return s["review_rounds"] >= tk.get("after_reviews", 1) or bool(
        tk.get("after_attempt") and ("implement", agent) in [(teamcfg.norm_kind(e[0]), e[1]) for e in hist_entries(s)])


def count_triggers(s, agent):
    """Reasons from the failure-count rules for the implement stage that just failed: a [routing.takeover.<role>]
    without `to` (once per run of the task) and [routing.after_impl_fails] (exactly at `fails`)."""
    R, out = CFG["routing"], []
    tk = R["takeover"].get(agent)
    if tk and not tk.get("to") and takeover_due(s, agent, tk) \
            and not any("takeover" in e["rules"] for e in s.get("stepped", []) if teamcfg.norm_kind(e["kind"]) == "implement"):
        out.append("takeover")
    af = R["after_impl_fails"]
    if af and s.get("impl_fails", 0) == af["fails"]:
        out.append("after_impl_fails")
    return out


def escalate(s, stages, ti, reasons):
    """Step the retry of stage ti up one tier (one entry per failure, however many rules fired). Returns why it
    cannot (no ladder, a pin or role_override, already at the strongest tier), else None."""
    kind, agent = stages[ti]
    h = s.get("heuristic")
    last = next((x for x in reversed(s.get("launches", []))
                 if teamcfg.norm_kind((x.get("heuristic") or {}).get("kind")) == teamcfg.norm_kind(kind)), None)
    rank = ((last or {}).get("heuristic") or {}).get("rank")
    if not h or rank is None:
        return "no tier ladder applies (no [heuristic], a pinned agent or a role_override)"
    if rank >= len(h["tiers"]) - 1:
        s["capped"] = kind  # `team approve` retries here at the cap
        return f"already at the strongest tier ({h['tiers'][rank]['name']})"
    s.setdefault("stepped", []).append({"kind": kind, "agent": agent, "rank": rank + 1, "rules": reasons})
    s["escalations"] = s.get("escalations", 0) + 1
    live(f"[{s['id']}] escalation ({', '.join(reasons)}): {kind} retries at tier {h['tiers'][rank + 1]['name']}")
    return None


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


def take_slot(held):
    """A slot under max_parallel, appended to held; returns why the run must wait, or None."""
    for name in [f"slot{i}" for i in range(MAX_PARALLEL)]:  # global concurrency cap
        f = (RUNS / f".lock-{name}").open("a")
        try:
            teamcfg.lock(f, blocking=False)
            held.append(f)
            return None
        except BlockingIOError:
            f.close()
    return f"{MAX_PARALLEL} team runs are already in progress"


# --- Resource leases: an agent (or the user's `team hold`) holds a [locks] resource only while it uses it ---

def _lease_file(name):
    return RUNS / f"lease-{name}.json"


def read_lease(name):
    try:
        lease = json.loads(_lease_file(name).read_text())
    except (OSError, ValueError):
        return None
    return lease if isinstance(lease, dict) else None


def lease(name):
    """The live lease on resource name ({task, stage, owner, since}); None when free or its holder is gone (the
    task's run ended, or the `team hold` process exited), so a crashed run never keeps a resource."""
    cur = read_lease(name)
    if not cur:
        return None
    try:
        alive = hold_active() if cur.get("owner") == "user" else bool(cur.get("task")) and run_held(cur["task"])
    except OSError:  # e.g. the owner's task folder is gone
        alive = False
    return cur if alive else None


def leases():
    """{name: live lease} for the configured [locks]."""
    return {n: cur for n in CFG["locks"]["names"] if (cur := lease(n))}


def lease_text(name, cur):
    who = "the user (`team hold`)" if cur.get("owner") == "user" else f"{cur['task']}, {cur.get('stage') or '?'}"
    return f"{name} ({who}, since {time.strftime('%H:%M', time.localtime(cur.get('since', 0)))})"


def probe_refuses(name, task):
    """Why the [locks.<name>] probe refuses the lease (too little free MiB), or None; skipped while the task holds
    the lock named by skip_if_holds (e.g. the editor already accounts for the GPU it uses)."""
    lc = CFG["locks"].get(name)
    if not isinstance(lc, dict):
        return None
    other = lc.get("skip_if_holds")
    if other and (cur := lease(other)) and cur.get("task") == task:
        return None
    return None if resource_ok(name) else f"not enough free {name} (< {lc.get('min_free_mib')} MiB) next to other jobs"


def take_lease(name, task, stage="", owner="agent"):
    """Lease resource name to task (owner agent) or to the user (task "user"); None, or why it is not free now."""
    RUNS.mkdir(parents=True, exist_ok=True)
    if owner == "agent" and (why := probe_refuses(name, task)):
        return why
    with (RUNS / f".lock-{name}").open("a") as f:
        teamcfg.lock(f)  # an instant: check and write as one step
        cur = lease(name)
        if cur and (cur.get("owner"), cur.get("task")) != (owner, task):
            return f"busy: {lease_text(name, cur)}"
        _atomic_write(_lease_file(name), json.dumps({"task": task, "stage": stage, "owner": owner, "since": time.time()}))
    return None


def drop_leases(task, names=None, owner="agent"):
    """Free the leases task holds (all, or names); returns the names freed."""
    freed = []
    for n in names or CFG["locks"]["names"]:
        with (RUNS / f".lock-{n}").open("a") as f:
            teamcfg.lock(f)
            cur = read_lease(n)
            if cur and (cur.get("owner"), cur.get("task")) == (owner, task):
                _lease_file(n).unlink(missing_ok=True)
                freed.append(n)
    return freed


def lease_line():
    """`locks: ...` while any resource is leased, else ''."""
    cur = leases()
    return "locks: " + ", ".join(lease_text(n, cur[n]) for n in cur) if cur else ""


def hold_active():
    """True while a `team hold` process keeps .lock-hold."""
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / ".lock-hold").open("a") as f:
        try:
            teamcfg.lock(f, blocking=False)
        except BlockingIOError:
            return True
    return False


def advance(s, from_queue=False):
    """Run a task: [locks] resources are not taken here, the agent leases them while it uses them (`team lock`).
    Without a free slot the task is saved as new and queued (notes and stage kept); the queue runner starts it later.
    When the run ends, however it ends, the task's leases are freed."""
    RUNS.mkdir(parents=True, exist_ok=True)
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
        wait = take_slot(held)
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
                stages = task_stages(s)
                if s["stage"] >= len(stages):
                    s["status"], s["reason"] = "done", (f"Review {noun()} {s['change']} (`team review {s['id']}`); the user submits it." if VCS.submit_step
                                                         else f"Review the {noun()} (`team review {s['id']}`).")
                    s["finished"] = time.time()
                    s.setdefault("first_finish", s["finished"])  # `finished` moves on a redo; this one does not
                    learn(s)
                    tidy(s)  # also clears the sessions: a redo starts new ones
                else:
                    step(s, stages)
            if s["status"] == "running" and s["stage"] != previous_stage and stage_label(s) != "end":
                s["stage_started"] = time.time()
            save(s)
    finally:
        if held:  # this process holds the run lock: free what the agents forgot to unlock
            freed = drop_leases(s["id"])
            if freed:
                live(f"[{s['id']}] run ended: freed {', '.join(freed)}")
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
    return [s for s in map(read_state, sorted(RUNS.glob("t[0-9]*"))) if s]


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
    while slots are free and the tasks named in an `after tNNN` note are done. Runs are detached, log to
    <task>/logs/queue-run.log and recheck under the run lock that the task is still queued."""
    for tid in [t for t, p in _spawned.items() if p.poll() is not None]:
        del _spawned[tid]
    tasks = {s["id"]: s for s in all_tasks()}
    active = {t for t, s in tasks.items() if s["status"] == "running" and run_held(t)} | set(_spawned)
    notes = queue_notes()
    rank = {k: i for i, k in enumerate(notes)}
    started = []
    for s in sorted((s for t, s in tasks.items() if s["status"] == "new" and s.get("queued") and t not in active),
                    key=lambda s: (rank.get(s["id"], len(rank)), s["id"])):
        if len(active) >= MAX_PARALLEL:
            break
        if any(tasks.get(t, {}).get("status") != "done" for t in queue_deps(notes.get(s["id"], ""))):
            continue
        logs = task_dir(s["id"]) / "logs"
        logs.mkdir(exist_ok=True)
        with (logs / "queue-run.log").open("a") as out:
            _spawned[s["id"]] = subprocess.Popen(
                [sys.executable, str(HERE / "team.py"), "--config", CFG["config_path"], "run", "--queued", s["id"]], cwd=WS,
                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **detach_kw())
        live(f"[{s['id']}] queue: starting", echo=False)
        active.add(s["id"])
        started.append(s["id"])
    if not refill_blocker(tasks, active):
        logs = RUNS / "refill" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / "refill-run.log").open("a") as out:
            _spawned["refill"] = subprocess.Popen(
                [sys.executable, str(HERE / "team.py"), "--config", CFG["config_path"], "refill"], cwd=WS,
                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **detach_kw())
        live("[refill] queue low: asking the Producer for the next tasks", echo=False)
    return started


def detach_kw():
    """Popen options that keep a background run alive when the dashboard or shell that started it closes."""
    return ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
            if os.name == "nt" else {"start_new_session": True})


# --- Queue refill: the Producer proposes the next tasks from the plan; the user promotes or rejects them ---

def refill_state():
    """The refill pseudo-task in <state_dir>/refill/state.json: agent-run fields plus the proposal log."""
    try:
        s = json.loads((RUNS / "refill" / "state.json").read_text())
    except (OSError, ValueError):
        s = {}
    base = {"id": "refill", "change": "-", "request": "", "title": "queue refill", "route": None, "domain": None,
            "status": "idle", "reason": "", "n": 0, "plan_rounds": 0, "review_rounds": 0, "notes": [],
            "plan_reviews": [], "reviews": [], "history": [], "last": 0, "empty_sig": None, "proposals": [],
            "last_keys": [], "next_key": 1}
    return {**base, **s} if isinstance(s, dict) else base


def plan_signature():
    """Changes when the plan or the finished work changes: an empty refill is retried only then."""
    stamps = []
    for name in (CFG["project"]["planning_file"], "ROADMAP.md"):
        try:
            stamps.append((WS / name).stat().st_mtime)
        except OSError:
            stamps.append(None)
    return [stamps, sum(s["status"] == "done" for s in all_tasks())]


def refill_blocker(tasks, active):
    """Why a refill should not start now, or None. tasks: {id: state}; active: ids running or starting."""
    Q = CFG["queue"]
    if not Q["refill"]:
        return "refill is off"
    if "refill" in _spawned:
        return "a refill is running"
    queued = sum(s["status"] == "new" and bool(s.get("queued")) for s in tasks.values())
    planned = sum(not re.fullmatch(r"t\d+", k) for k in queue_notes())  # proposals or lines waiting for the user
    if queued + planned >= Q["low_water"]:
        return "the queue is not low"
    if len(active) >= MAX_PARALLEL:
        return "every slot is busy"
    if sum(s["status"] in ATTENTION for s in tasks.values()) >= Q["pause_needs_you"]:
        return "tasks are waiting for the user"
    r = refill_state()
    now = time.time()
    if refill_allowance(r) <= 0:
        return "daily proposal cap reached"
    if now - r["last"] < Q["cooldown_min"] * 60:
        return "cooling down"
    if r["empty_sig"] is not None and r["empty_sig"] == plan_signature():
        return "no planned work left"
    if claude_low():
        return "Claude usage is low"
    return None


def refill_allowance(r):
    """Proposals one refill may make: the batch, capped by what is left of today's daily_cap."""
    Q = CFG["queue"]
    today = datetime.now().date()
    made = sum(datetime.fromtimestamp(p["t"]).date() == today and not p.get("user") for p in r["proposals"])
    return min(Q["batch"], Q["daily_cap"] - made)


def refill_request(r):
    """What the Producer needs to avoid repeats: tasks, pending, promoted and rejected proposals."""
    Q = CFG["queue"]
    lines = [f"Propose up to {refill_allowance(r)} next tasks for the team. Sources, in order: unchecked items in the current "
             f"phase of {CFG['project']['planning_file']}, then the next outcomes in ROADMAP.md. Skip items owned by "
             "the user (\"Owner: user\", \"user-only\") and anything listed below as done, in flight, proposed or "
             "rejected.", "", "Tasks:"]
    tasks = all_tasks()
    keep = [s for s in tasks if s["status"] not in ("done", "dropped")] + tasks[-60:]
    for s in sorted({s["id"]: s for s in keep}.values(), key=lambda s: s["id"]):
        lines.append(f"- {s['id']} {s['status']}: {' '.join((s['title'] or s['request']).split())[:160]}")
    planned = [ln for k, ln in queue_notes().items() if not re.fullmatch(r"t\d+", k)]  # proposals and the user's
    if planned:
        lines += ["", f"Planned in {CFG['project']['queue_file']}:"] + [f"- {ln}" for ln in planned]
    rejected = [p for p in r["proposals"] if p["status"] == "rejected"][-40:]
    if rejected:
        lines += ["", "Rejected:"] + [f"- {p['request']}" + (f" (why: {p['why']})" if p.get("why") else "")
                                      for p in rejected]
    return "\n".join(lines)


def _queue_file_lock():
    f = (RUNS / ".lock-queue-file").open("a")
    teamcfg.lock(f)  # blocking: refill appends and promote/reject rewrite the same file
    return f


def cmd_refill(a):
    """One refill: the Producer reads the plan and proposes tasks, appended to the queue file as pNNN lines."""
    (RUNS / "refill").mkdir(parents=True, exist_ok=True)
    lk = (RUNS / ".lock-refill").open("a")
    try:
        teamcfg.lock(lk, blocking=False)
    except BlockingIOError:
        sys.exit("A refill is already running.")
    held = [lk]
    try:
        if refill_allowance(refill_state()) <= 0:  # capped is not exhausted: record nothing
            sys.exit("Daily proposal cap reached; the refill runs tomorrow.")
        if take_slot(held):  # the Producer run counts against max_parallel like any other
            sys.exit("Every team slot is busy; the refill runs later.")
        _refill()
    finally:
        for f in held:
            f.close()


def _refill():
    """The Producer run of a refill and its result, with the refill and slot locks held."""
    r = _update_refill(lambda r: r.update(status="running", reason="", last=time.time(), request=refill_request(r)))
    allowance, sig = refill_allowance(r), plan_signature()  # the plan as the Producer reads it
    new = []
    try:
        out, text, _, _ = run_agent(r, "refill", "producer")
    except Exception as e:  # e.g. the CLI is missing: a running state left behind would hide the failure
        out, text = None, None
        r["status"], r["reason"] = "failed", f"Producer could not run: {e}"

    def finish(cur):  # merge into the current log: promote/reject may have run meanwhile
        cur.update(status=r["status"], reason=r["reason"], n=r["n"], history=r["history"],
                   last_keys=[p["key"] for p in new], next_key=int(new[-1]["key"][1:]) + 1 if new else r["next_key"],
                   empty_sig=sig if r["status"] == "done" and not new else None)
        cur["proposals"] += new
    if not out:
        _update_refill(finish)
    else:
        tagged = [m.strip() for m in re.findall(r"^\s*(?:[-*]\s+)?\**TASK:\**\s*(.+)$", text, re.M)]
        found = [f for f in tagged if f.lower().strip(".`*") != "none"][:max(0, allowance)]
        if not tagged:  # only an explicit "TASK: none" means the plan is exhausted; this stays retryable
            r["status"], r["reason"] = "failed", f"Producer gave no TASK lines; see {out}"
            _update_refill(finish)
            live(f"[refill] {r['status']}: {r['reason']}")
            return
        with _queue_file_lock():  # lines and records appear together for promote/reject
            path = RUNS / CFG["project"]["queue_file"]
            old = path.read_text() if path.exists() else ""
            used = {ln.split(":", 1)[0].strip() for ln in old.splitlines()} | {p["key"] for p in refill_state()["proposals"]}
            n = r["next_key"]
            for req in found:  # skip keys already in the queue file or the log (hand-written, interrupted refill)
                while f"p{n:03d}" in used:
                    n += 1
                new.append({"key": f"p{n:03d}", "request": req, "t": time.time(), "status": "proposed"})
                n += 1
            if new:
                _atomic_write(path, old + ("" if not old or old.endswith("\n") else "\n")  # dispatch reads unlocked
                              + "".join(f"{p['key']}: {p['request']}\n" for p in new))
            r["status"], r["reason"] = "done", (f"proposed {', '.join(p['key'] for p in new)}" if new
                                                else "no planned work left")
            _update_refill(finish)
    live(f"[refill] {r['status']}: {r['reason']}")


def _update_refill(fn):
    """Locked read-modify-write of the refill state; returns the state written."""
    (RUNS / "refill").mkdir(parents=True, exist_ok=True)
    with (RUNS / ".lock-refill-log").open("a") as lk:
        teamcfg.lock(lk)
        r = refill_state()
        fn(r)
        _atomic_write(RUNS / "refill" / "state.json", json.dumps(r, indent=2))
    return r


def _rewrite_queue(keys, change):
    """Apply change(key, request, after_note) -> new line or None (drop) to the queue file's non-task lines in keys
    ("all" = every one). Returns the keys handled."""
    done = []
    with _queue_file_lock():
        path = RUNS / CFG["project"]["queue_file"]
        lines = path.read_text().splitlines() if path.exists() else []
        out = []
        for ln in lines:
            key, _, rest = ln.partition(":")
            key = key.strip()
            if (ln.strip() and not ln.lstrip().startswith("#") and rest and not re.fullmatch(r"t\d+", key)
                    and ("all" in keys or key in keys)):
                after = re.search(r"\s*\(after [^)]*\)", rest)
                new = change(key, (rest[:after.start()] + rest[after.end():] if after else rest).strip(),
                             after[0].strip() if after else "")
                done.append(key)
                if new is not None:
                    out.append(new)
            else:
                out.append(ln)
        _atomic_write(path, "\n".join(out) + ("\n" if out else ""))
    return done


def _mark_proposals(updates):
    """{key: fields} merged into the refill log's proposals."""
    _update_refill(lambda r: [p.update(updates.get(p["key"], {})) for p in r["proposals"]])


def cmd_promote(a):
    """Turn planned queue lines (proposals or your own) into queued tasks, in place, so order and after-notes hold."""
    made, errors = [], []  # (key, task id): a hand-written key may repeat

    def promote(key, request, after):
        try:
            s = create_task(request)  # not queued yet: the runner must see its queue line and after-note first
        except SystemExit as e:  # e.g. no change could be created: keep the line, carry on with the others
            errors.append(f"{key}: {e}")
            return f"{key}: {request}" + (f" {after}" if after else "")
        made.append((key, s["id"]))
        return f"{s['id']}: {request}" + (f" {after}" if after else "")
    done = _rewrite_queue(set(a.keys), promote)
    for _, tid in made:
        s = load(tid)
        s.update(queued=True, reason="queued")
        save(s)
    _mark_proposals({k: {"status": "promoted", "task": tid} for k, tid in made})
    for k, tid in made:
        print(f"{k} -> {tid} (queued)")
    missing = set(a.keys) - set(done) - {"all"}
    if missing:
        errors.append(f"Not a planned line in the queue file: {', '.join(sorted(missing))}")
    if errors:
        sys.exit("\n".join(errors))


def cmd_reject(a):
    """Drop planned queue lines; rejected proposals are shown to the Producer so it does not propose them again."""
    requests = {}
    done = _rewrite_queue(set(a.keys), lambda key, request, after: requests.update({key: request}))  # None: drop

    def reject(r):
        known = {p["key"] for p in r["proposals"]}
        for p in r["proposals"]:
            if p["key"] in requests:
                p.update(status="rejected", why=a.why)
        r["proposals"] += [{"key": k, "request": req, "t": time.time(), "status": "rejected", "why": a.why, "user": True}
                           for k, req in requests.items() if k not in known]  # your own lines are remembered too
    _update_refill(reject)
    for k in done:
        print(f"{k} rejected")
    missing = set(a.keys) - set(done) - {"all"}
    if missing:
        sys.exit(f"Not a planned line in the queue file: {', '.join(sorted(missing))}")


ATTENTION = ("gate", "blocked", "escalated", "failed")


def first_seen():
    """Seen map for a new watcher: finished tasks and the last refill are old news, the rest that needs attention
    gets reported."""
    r = refill_state()
    seen = {s["id"]: [s["status"], s.get("n", 0)] for s in all_tasks() if s["status"] in ("done", "dropped")}
    pending = any(p["status"] == "proposed" and p["key"] in r["last_keys"] for p in r["proposals"])
    if pending or r["status"] == "failed":  # still needs the user, like a failed task
        return seen
    return {**seen, "refill": [r["status"], r["n"]]}


CADENCES = ("task", "milestone", "daily", "custom")


def normalize_cadence(v):
    """(cadence, valid): anything outside CADENCES falls back to "task"."""
    v = str(v or "").strip().lower()
    return (v, True) if v in CADENCES else ("task", False)


def current_phase(cfg=None):
    """(heading, open_count) of the "## Current phase" section of planning_file; open_count counts "- [ ]" items
    except the user's ("Owner: user", "user-only"). None when the file or the section is missing or unreadable."""
    cfg = cfg or CFG
    try:
        text = (cfg["root"] / cfg["project"]["planning_file"]).read_text()
    except (OSError, UnicodeError):
        return None
    head, n = None, 0
    for ln in text.splitlines():
        if ln.startswith("## "):
            if head is not None:
                break
            if ln.lower().startswith("## current phase"):
                head = ln[3:].strip()
        elif head is not None and re.match(r"\s*- \[ \]", ln) and not re.search(r"owner:\s*user|user-only", ln, re.I):
            n += 1
    return None if head is None else (head, n)


def review_due(cadence, state, today, phase):
    """Ids to open one review page for, or [] (state: {"pending": [...], "date": "YYYY-MM-DD", "phase": heading};
    phase heading recorded in place). Done tasks only: attention states always open and never come through here.
    phase: current_phase() result; None means unknown, so milestone behaves as task and the phase is kept. A heading
    change also ends the milestone, so a phase closed without a pass seeing 0 open items still gets its review."""
    pending = state.get("pending", [])
    moved = phase is not None and bool(state.get("phase")) and state["phase"] != phase[0]
    if phase is not None:
        state["phase"] = phase[0]
    if cadence == "custom":
        return []
    if cadence == "milestone" and phase is not None and phase[1] > 0 and not moved:
        return []
    if cadence == "daily" and state.get("date") == today:
        return []
    return pending[:]


def review_pass(cadence, state, done_ids, today, phase):
    """One notifier pass over the cadence state {"known_done", "pending", "date", "phase"} (updated in place).
    Done tasks not yet in known_done (also ones that finished while the notifier was down) join pending; returns the
    ids to open now, which then leave pending. A missing state ("known_done" absent) starts from all current done tasks."""
    if "known_done" not in state:
        state["known_done"] = sorted(done_ids)
    new = [t for t in sorted(done_ids) if t not in state["known_done"]]
    state["known_done"] += new
    # custom: the coordinator reviews, so nothing piles up to open at once after a switch to another cadence
    state["pending"] = [] if cadence == "custom" else [t for t in state.get("pending", []) if t in done_ids] + new
    due = review_due(cadence, state, today, phase)
    if due:
        state["pending"] = [t for t in state["pending"] if t not in due]
        state["date"] = today
    return due


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
    r = refill_state()
    st = r["status"]
    if st == "running":  # killed mid-run if nobody holds the refill lock
        try:
            with (RUNS / ".lock-refill").open("a") as lk:
                teamcfg.lock(lk, blocking=False)
                st = "stale"
        except (BlockingIOError, OSError):
            pass
    if st in ("done", "failed", "stale") and seen.get("refill") != [st, r["n"]]:
        seen["refill"] = [st, r["n"]]
        if st == "stale":
            events.append(("refill", "stale", "the last refill was interrupted; the next queue pass retries it after "
                           "the cooldown"))
        elif st == "failed":
            events.append(("refill", "failed", r["reason"]))
        elif r["last_keys"]:
            events.append(("refill", "proposed", f"{', '.join(r['last_keys'])} in {CFG['project']['queue_file']}: "
                           f"`team promote <key>|all` to queue them, `team reject <key> [--why \"...\"]` to drop"))
        else:
            events.append(("refill", "empty", f"no planned work left in {CFG['project']['planning_file']} or "
                           "ROADMAP.md; add items to refill the queue"))
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


def cmd_hold(a):
    """Lease [locks] to the user (e.g. their own editor session): agents' `team lock` waits from now on, and agents
    already holding one keep it until they unlock it or their run ends. Held until `team release`, Ctrl+C or --hours."""
    names = [r for r in (a.res.split(",") if a.res else CFG["locks"]["names"]) if r in CFG["locks"]["names"]]
    if not names:
        sys.exit(f"team hold: no [locks] to hold (known: {', '.join(CFG['locks']['names']) or 'none'})")
    RUNS.mkdir(parents=True, exist_ok=True)
    me = (RUNS / ".lock-hold").open("a")
    try:
        teamcfg.lock(me, blocking=False)
    except BlockingIOError:
        sys.exit("team hold: another hold is already active; `team release` ends it")
    path, end = RUNS / "hold.json", time.time() + a.hours * 3600
    try:
        _atomic_write(path, json.dumps({"locks": names, "since": time.time()}))  # `team release` deletes it
        for r in names:
            if take_lease(r, "user", owner="user"):
                live(f"hold: waiting for '{r}' (its agent unlocks it or its run ends)")
            while take_lease(r, "user", owner="user"):  # polled, so `team release` and --hours also end a waiting hold
                if not path.exists() or time.time() >= end:
                    return
                time.sleep(2)
        live(f"hold: {', '.join(names)} held for the user; `team release` frees them")
        while path.exists() and time.time() < end:
            time.sleep(2)
    finally:
        drop_leases("user", names, owner="user")
        path.unlink(missing_ok=True)
        live("hold: released")
        me.close()


def cmd_lock(a):
    """Agent side: lease a [locks] resource to the task in $TEAM_TASK before using it; exit 3 while it stays busy."""
    task = os.environ.get("TEAM_TASK")
    if a.name not in CFG["locks"]["names"]:
        sys.exit(f"team lock: unknown lock {a.name!r} (known: {', '.join(CFG['locks']['names']) or 'none'})")
    if not task:
        sys.exit("team lock: TEAM_TASK is unset; run it from a team stage")
    end = time.time() + a.wait
    while why := take_lease(a.name, task, os.environ.get("TEAM_STAGE", "")):
        if time.time() >= end:
            print(f"team lock: {a.name} {why}", file=sys.stderr)
            sys.exit(3)
        time.sleep(2)
    live(f"[{task}] locked {a.name}", echo=False)
    print(f"locked {a.name}")


def cmd_unlock(a):
    task = os.environ.get("TEAM_TASK")
    if not task:
        sys.exit("team unlock: TEAM_TASK is unset; run it from a team stage")
    if drop_leases(task, [a.name]):
        live(f"[{task}] unlocked {a.name}", echo=False)
        print(f"unlocked {a.name}")
    elif cur := lease(a.name):
        print(f"team unlock: {a.name} is held by {lease_text(a.name, cur)}, not {task}", file=sys.stderr)
        sys.exit(3)
    else:
        print(f"{a.name} was not locked")


def cmd_release(a):
    path = RUNS / "hold.json"
    if not hold_active():
        path.unlink(missing_ok=True)
        sys.exit("team release: no active hold")
    path.unlink(missing_ok=True)  # the hold process sees it within 2 s and frees its leases
    print("team release: hold ends")


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
    stages = task_stages(s)
    return "end" if s["stage"] >= len(stages) else "/".join(stages[s["stage"]])


def cmd_new(a):
    refs = []
    try:
        for ref in a.skill:
            refs += teamcfg.parse_skill_refs(ref)
        for name, _ in refs:
            teamcfg.load_skill(CFG, name)
    except ValueError as e:
        sys.exit(f"--skill: {e}")
    if getattr(a, "route", None) and a.role:
        sys.exit("--route and --role cannot be combined: a side task skips routing.")
    s = create_task(a.request, a.res, a.role, skills=refs, risk=getattr(a, "risk", None), size=getattr(a, "size", None),
                    route=getattr(a, "route", None))
    if not a.no_run:
        advance(s)


def create_task(request, res_arg="", role=None, queued=False, skills=(), risk=None, size=None, route=None):
    """A new task folder, change and state; queued ones are started by the queue runner."""
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
        change = VCS.new_change(f"[team {tid}] {request.splitlines()[0][:60]}", tid)
    except (RuntimeError, OSError) as e:
        task_dir(tid).rmdir()
        sys.exit(f"Could not create a change: {e}")
    names = CFG["locks"]["names"]
    res = [r for r in res_arg.split(",") if r in names or r == "none"] if res_arg else list(CFG["locks"]["default"])
    res = res or list(CFG["locks"]["default"])
    s = {"id": tid, "request": request, "change": str(change), "title": "", "route": None, "domain": None,
         "stage": -1, "status": "new", "reason": "", "n": 0, "plan_rounds": 0, "review_rounds": 0,
         "res": res, "notes": [], "plan_reviews": [], "reviews": [], "history": [],
         "created": time.time(), "stage_started": None, "finished": None}
    if route:  # the Producer still writes the spec; this route replaces its pick (see lighter_guard)
        s["route_forced"] = teamcfg.canon_route(route)
    if role:  # parallel side task: skip routing, the named role implements
        s.update(route=f"custom:{role}", route_initial="custom", skipped=[], stage=0, title=request.splitlines()[0][:60],
                 domain=CFG["routing"]["side_task_domains"].get(role, CFG["routing"]["domains"][0]))
    if risk:
        s["risk"] = risk
    if size:
        s["size"] = size
    if role:  # a side task skips routing: its risk/size are fixed now so a resume sees the same inputs
        set_risk_size(s, risk, size)
    if queued:
        s.update(queued=True, reason="queued")
    attach_skills(s, skills, "you", pipeline(s["route"], s["domain"]) if role else None)
    save(s)
    live(f"[{tid}] created, {noun()} {s['change']}")
    return s


def cmd_run(a):
    advance(load(a.id), from_queue=a.queued)


def reset_escalation(s):
    """Clear step-ups, the diagnosis and minor rounds. A task approved after hitting the strongest tier retries there
    (its next major failure goes to the user); `team redo` starts over."""
    capped = s.pop("capped", None)
    for k in ("stepped", "diagnose", "minor_rounds"):
        s.pop(k, None)
    h = s.get("heuristic")
    if capped and h:
        s["stepped"] = [{"kind": capped, "agent": "", "rank": len(h["tiers"]) - 1, "rules": ["approved at the cap"]}]


def cmd_approve(a):
    s = load(a.id)
    if s["status"] not in ("gate", "blocked", "escalated", "failed"):
        sys.exit(f"{a.id} is {s['status']}; nothing to approve.")
    s["notes"].append(f"Approved ({s['reason']})" + (f": {a.note}" if a.note else ""))
    if s["status"] == "escalated":
        if s.pop("apex_guard", None):
            s["apex_approved"] = True  # the user allowed the guarded apex tier for this task
        s["plan_rounds"] = s["review_rounds"] = 0
        reset_escalation(s)
        stages = task_stages(s)
        kind = stages[s["stage"]][0] if 0 <= s["stage"] < len(stages) else None
        if kind in ("plan", "plan_review", "review"):  # retry the work that failed review, not the review
            target = "plan" if kind != "review" else "implement"
            s["stage"] = next(i for i, (k, _) in enumerate(stages) if teamcfg.norm_kind(k) == target)
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
    tidy(s)
    save(s)
    print(f"{a.id} dropped.")


def cmd_tidy(a):
    """Tidy done and dropped tasks that are not running (default: all): raw logs out, token rows kept."""
    total = n = 0
    for s in all_tasks():
        if s["status"] not in ("done", "dropped") or (a.ids and s["id"] not in a.ids):
            continue
        f = run_lock(s["id"])
        if not f:
            continue
        try:
            s = load(s["id"])
            freed = tidy(s)
            save(s)
        finally:
            f.close()
        total, n = total + freed, n + 1
    print(f"tidied {n} tasks, freed {total / 1e6:.1f} MB")


def cmd_redo(a):
    s = load(a.id)
    s["notes"].append(a.note)
    s["plan_rounds"] = s["review_rounds"] = 0
    s.pop("capped", None)  # redo starts below the cap, unlike approve
    s.pop("apex_guard", None)
    s.pop("apex_approved", None)  # redo starts over: the guard applies again
    reset_escalation(s)
    s["stage"] = -1 if not s["route"] else next(
        i for i, (k, _) in enumerate(task_stages(s)) if is_impl(k))
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


def task_tokens(tid):
    """'in 1.2M (cache 95%) out 12k $1.23' for a task's stage logs, or ''."""
    rows = tokens.collect(RUNS, {tid})
    if not rows:
        return ""
    return (f"{len(rows)} runs, in {tokens.human(sum(map(tokens.total, rows)))} (cache {tokens.hit(rows) * 100:.0f}%) "
            f"out {tokens.human(sum(r['out'] for r in rows))} ${sum(r['cost'] or 0 for r in rows):.2f}")


def cmd_tokens(a):
    print("\n".join(tokens.report(RUNS, set(a.ids) or None, a.runs)))


def route_metrics(tids=None):
    """Per route (route_initial, aliases merged): tasks, done, tokens (in+out, from the stage logs), mean wall seconds
    of done tasks (created -> first finish), first-pass review pass rate, review rounds (all review verdicts), upgrades
    to a fuller pipeline, escalations (tier step-ups and hand-offs to the user) and skipped stage runs. The counters in
    state.json are cumulative: neither redo nor approve resets them."""
    rows = {}
    for r in tokens.collect(RUNS):
        rows.setdefault(r["task"], []).append(r)
    out = {}
    for d in sorted(RUNS.glob("t[0-9]*")):
        try:
            s = json.loads((d / "state.json").read_text())
            assert isinstance(s, dict) and "id" in s
        except (OSError, ValueError, AssertionError):
            continue
        if tids and s["id"] not in tids:
            continue
        key = teamcfg.canon_route(s.get("route_initial") or s.get("route") or "unrouted")
        key = "custom" if key.startswith("custom") else key
        m = out.setdefault(key, dict(tasks=0, done=0, tokens=0, wall=[], first_pass=[], rounds=0, upgrades=0, escalations=0,
                                     skipped=0))
        m["tasks"] += 1
        m["done"] += s["status"] == "done"
        m["tokens"] += sum(tokens.total(r) + r["out"] for r in rows.get(s["id"], ()))
        end = s.get("first_finish") or (s.get("finished") if s["status"] == "done" else None)
        if end and s.get("created"):
            m["wall"].append(end - s["created"])
        if "first_pass" in s:
            m["first_pass"].append(bool(s["first_pass"]))
        m["rounds"] += s.get("review_rounds_total", 0)
        m["upgrades"] += s.get("upgrades", 0)
        m["escalations"] += s.get("escalations", 0)
        m["skipped"] += len(s.get("skipped") or ())
    for m in out.values():
        m["wall"] = sum(m["wall"]) / len(m["wall"]) if m["wall"] else None
        m["first_pass"] = sum(m["first_pass"]) / len(m["first_pass"]) if m["first_pass"] else None
    return out


def metrics_lines(tids=None):
    """Text table of route_metrics for `team status --metrics`, the focus panel and the review page."""
    ms = route_metrics(tids)
    head = f"{'route':8} {'tasks':>5} {'done':>4} {'tok/task':>9} {'wall/task':>9} {'1st-pass':>8} {'rounds':>6} {'upgr':>4} {'esc':>3} {'skipped':>7}"
    lines = [head]
    for k, m in sorted(ms.items()):
        wall = f"{m['wall'] / 60:.0f}m" if m["wall"] is not None else "-"
        fp = f"{m['first_pass'] * 100:.0f}%" if m["first_pass"] is not None else "-"
        lines.append(f"{k:8} {m['tasks']:5} {m['done']:4} {tokens.human(m['tokens'] / m['tasks']):>9} {wall:>9} {fp:>8} "
                     f"{m['rounds']:6} {m['upgrades']:4} {m['escalations']:3} {m['skipped']:7}")
    return lines if ms else []


def burst_line():
    """`burst: ...` while [routing.usage].burst_file holds a future deadline, else ''."""
    name = CFG["routing"]["usage"]["burst_file"]
    try:
        end = float((RUNS / name).read_text().strip()) if name else 0.0
    except (OSError, ValueError):
        return ""
    if time.time() >= end:
        return ""
    return f"burst: active until {time.strftime('%Y-%m-%d %H:%M', time.localtime(end))} ({(end - time.time()) / 3600:.1f}h left)"


def cmd_burst(a):
    """Write (or with 0 hours end) the [routing.usage].burst_file deadline."""
    name = CFG["routing"]["usage"]["burst_file"]
    if not name:
        sys.exit("team burst: set [routing.usage] burst_file in team.toml first")
    RUNS.mkdir(parents=True, exist_ok=True)
    if a.hours <= 0:
        (RUNS / name).unlink(missing_ok=True)
        live("burst: ended by the user")
        return
    _atomic_write(RUNS / name, f"{time.time() + a.hours * 3600:.0f}\n")
    live(burst_line())


def cmd_status(a):
    if getattr(a, "metrics", False):
        print("\n".join(metrics_lines()) or "No tasks yet.")
        return
    if a.id:
        s = load(a.id)
        print(f"{s['id']}  {s['status']}  chg:{s['change']}  {s['route']}/{s['domain']}  at {stage_label(s)}")
        if sk := skipped_kinds(s):
            print(f"  skipped: {', '.join(sk)}" + (f"  upgrades: {s['upgrades']}" if s.get("upgrades") else ""))
        print(f"  {format_task_timing(s)}  (c=created s=stage f=finished +stage elapsed)")
        if used := task_tokens(s["id"]):
            print(f"  tokens: {used}")
        print(f"  {s['title'] or s['request'].splitlines()[0]}")
        if s["reason"]:
            print(f"  {s['reason']}")
        for h in s["history"]:
            print(f"  {task_dir(s['id']) / h}.md")
        print(VCS.opened(s["change"]).rstrip())
        return
    tasks = sorted(RUNS.glob("t[0-9]*"))
    for line in (burst_line(), lease_line()):
        if line:
            print(line)
    if a.reverse or under_watch():  # dashboard pane: newest task on top, always visible without scrolling
        tasks.reverse()
    if not tasks:
        print('No tasks yet. Start one with: team new "<request>"')
    now = time.time()
    for d in tasks:
        s = read_state(d)
        if not s:
            continue  # no or corrupt state.json (a folder synced from the depot, or mid-write)
        print(f"{s['id']}  {s['status']:9}  chg:{s['change']}  {str(s['route']):7} {str(s['domain']):8} "
              f"{stage_label(s):22} {(s['title'] or s['request'])[:50]}\t{format_task_timing(s, now)}")
        if s["reason"] and s["status"] != "running":
            print(f"      {s['reason']}")


def warn_deprecated():
    if CFG.get("deprecated_domain_roles"):
        print("team: [routing.domain_roles] is deprecated; use [routing.domain.<name>] plan/implement.", file=sys.stderr)


def main():
    if os.name != "nt":  # agents run in their own session: a TERM/HUP must unwind like Ctrl+C so they are reaped
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda n, _frame: sys.exit(128 + n))
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", help="team.toml path (default: $TEAM_CONFIG, else the nearest team.toml upwards)")
    g, rest = pre.parse_known_args()
    init(g.config)
    warn_deprecated()
    ap = argparse.ArgumentParser(prog="team", description=__doc__, parents=[pre])
    sub = ap.add_subparsers(required=True)
    p = sub.add_parser("new", help="create a task and run it")
    p.add_argument("request")
    p.add_argument("--role", choices=CFG["routing"]["side_task_roles"] or None,
                   help="parallel side task: skip routing, this role implements, the side-task reviewer reviews")
    p.add_argument("--route", choices=sorted(ROUTES), help="route override for the Producer's pick (high risk or "
                   "earlier failures still raise a lighter route to complex)")
    p.add_argument("--risk", choices=teamcfg.RISKS, help="heuristic input for a side task (default: high)")
    p.add_argument("--size", choices=teamcfg.SIZES, help="heuristic input for a side task (default: large)")
    p.add_argument("--res", default="", help="kept for old scripts: [locks] no longer gate a run, agents `team lock` them")
    p.add_argument("--skill", action="append", default=[], metavar="NAME[@STAGE]",
                   help="task skill (skills/<name>.md) added to this task's prompt, for one stage or all; repeatable")
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
    p = sub.add_parser("refill", help="ask the Producer to propose the next tasks from the plan (queue file pNNN lines)")
    p.set_defaults(func=cmd_refill)
    p = sub.add_parser("promote", help="queue planned lines from the queue file as tasks (pNNN, your own keys, or all)")
    p.add_argument("keys", nargs="+")
    p.set_defaults(func=cmd_promote)
    p = sub.add_parser("reject", help="drop planned lines; the Producer will not propose them again")
    p.add_argument("keys", nargs="+")
    p.add_argument("--why", default="", help="reason shown to the Producer")
    p.set_defaults(func=cmd_reject)
    p = sub.add_parser("wait", help="block until a task needs attention or finishes, print it and exit")
    p.add_argument("--no-block", action="store_true", help="report what changed since the last wait and exit")
    p.set_defaults(func=cmd_wait)
    p = sub.add_parser("hold", help="reserve [locks] for the user (own editor session) until `team release`")
    p.add_argument("--res", default="", help="comma list of [locks].names (default: all)")
    p.add_argument("--hours", type=float, default=4.0, help="release automatically after this long (default: 4)")
    p.set_defaults(func=cmd_hold)
    p = sub.add_parser("lock", help="agent stage: lease a [locks] resource while using it (exit 3 while busy)")
    p.add_argument("name", help="a [locks].names entry, e.g. editor")
    p.add_argument("--wait", type=float, default=0.0, help="seconds to keep trying while it is busy (default: 0)")
    p.set_defaults(func=cmd_lock)
    p = sub.add_parser("unlock", help="agent stage: free a [locks] resource this task leased")
    p.add_argument("name")
    p.set_defaults(func=cmd_unlock)
    p = sub.add_parser("release", help="end an active `team hold`")
    p.set_defaults(func=cmd_release)
    p = sub.add_parser("burst", help="spend Claude for a while: Codex roles move to Claude, the apex guard is lifted")
    p.add_argument("hours", type=float, help="duration in hours (0 ends an active burst)")
    p.set_defaults(func=cmd_burst)
    p = sub.add_parser("tidy", help="delete the raw logs and prompt copies of done and dropped tasks (token rows stay)")
    p.add_argument("ids", nargs="*", help="task ids (default: all done and dropped)")
    p.set_defaults(func=cmd_tidy)
    p = sub.add_parser("tokens", help="tokens, cost and time per stage kind, agent and task (from the stage logs)")
    p.add_argument("ids", nargs="*", help="task ids (default: all)")
    p.add_argument("--runs", action="store_true", help="also list every stage run")
    p.set_defaults(func=cmd_tokens)
    p = sub.add_parser("status", help="list tasks, or show one")
    p.add_argument("-r", "--reverse", action="store_true", help="newest task first")
    p.add_argument("--metrics", action="store_true", help="per-route tokens, wall time, first-pass rate, rounds, upgrades")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=cmd_status)
    a = ap.parse_args(rest)
    a.func(a)


if __name__ == "__main__":
    main()
