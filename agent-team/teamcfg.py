#!/usr/bin/env python3
"""Agent team config loader (team.toml) and shared path helpers. Needs Python >= 3.11 (tomllib).

CLI for shell scripts: `teamcfg.py --shell` prints quoted KEY=value lines (eval them);
`teamcfg.py --get a.b.c` prints one value."""
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANONICAL_ROLES = ("producer", "mid", "senior", "architect", "director")
DEFAULTS = {
    "project": {"name": "project", "root": ".", "state_dir": ".agent-team", "templates_dir": "", "team_setup": "",
                "docs": ["AGENTS.md", "SPEC.md", "ROADMAP.md", "TASKS.md", "docs/"],
                "queue_file": "queue.txt", "planning_file": "TASKS.md"},
    "vcs": {"kind": "git", "guard_names": ["git"], "deny": {}, "deny_flags": {}},
    "agents": {"deny_extra": []},
    "locks": {"names": [], "default": []},
    "routing": {"max_rounds": 2, "max_parallel": 3, "long_stage_min": 120, "domains": ["code"], "review_extra_domains": [],
                "extra_review_role": "", "extra_review_routes": [], "domain_roles": {},
                "pipeline": {}, "side_task_reviewer": "architect", "side_task_roles": [],
                "side_task_domains": {}, "takeover": {}, "after_impl_fails": {}, "capacity_fallback": {},
                "usage": {"enabled": False}},
    "queue": {"refill": True, "low_water": 1, "batch": 3, "daily_cap": 10, "pause_needs_you": 2, "cooldown_min": 30},
    "prompts": {"readonly_note": "Read-only stage: use tools only to inspect, never to change."},
    "notify": {"app_name": "", "sound_dir": "", "sound_normal": "message.oga", "sound_urgent": "alarm-clock-elapsed.oga"},
    "probes": {},
    "usage": {"claude_endpoint": False},
}
USAGE_DEFAULTS = {"claude_fallback": {}, "limits": {"5h": 90.0, "7d": 95.0}, "scoped_limit": {},
                  "surplus_swap": {}, "burst_swap": {}, "burst_file": "", "cheap_first": [],
                  "no_burst_effort": {}, "escalation_gate": {}}


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) and base[k] else v
    return out


def find_config(start=None):
    env = os.environ.get("TEAM_CONFIG")
    if env:
        return Path(env).resolve()
    d = Path(start or os.getcwd()).resolve()
    for p in (d, *d.parents):
        if (p / "team.toml").is_file():
            return p / "team.toml"
    sys.exit("No team.toml found (set TEAM_CONFIG or run inside a project that has one).")


def load(path=None):
    path = Path(path) if path else find_config()
    cfg = _merge(DEFAULTS, tomllib.loads(path.read_text()))
    cfg["routing"]["usage"] = _merge(USAGE_DEFAULTS, cfg["routing"]["usage"])
    cfg["config_path"] = str(path.resolve())
    base = path.resolve().parent
    root = (base / cfg["project"]["root"]).resolve()
    cfg["root"] = root
    cfg["state"] = (root / cfg["project"]["state_dir"]).resolve()
    roles = cfg.get("roles") or {}
    missing = [r for r in CANONICAL_ROLES if r not in roles]
    if missing:
        raise ValueError(f"team.toml [roles] must define: {', '.join(missing)}")
    for key, r in roles.items():
        for f in ("name", "cli", "model", "effort"):
            if f not in r:
                raise ValueError(f"team.toml [roles.{key}] needs {f}")
        if r["cli"] not in ("claude", "codex"):
            raise ValueError(f"team.toml [roles.{key}] cli must be claude or codex")
    cfg["roles"] = roles
    pipes = cfg["routing"]["pipeline"]
    for route in ("simple", "complex", "hard"):
        if route not in pipes:
            raise ValueError(f"team.toml [routing.pipeline] needs {route}")
    for route, stages in pipes.items():
        for kind, role in stages:
            if role not in roles or kind not in ("plan", "plan_review", "implement", "review"):
                raise ValueError(f"team.toml pipeline {route}: bad stage {kind}/{role}")
    for where, role in _role_refs(cfg["routing"]):
        if role not in roles:
            raise ValueError(f"team.toml {where} references unknown role {role!r}")
    return cfg


def _role_refs(R):
    """(location, role) for every role name referenced outside [roles] and the pipeline."""
    U = R["usage"]
    refs = [("routing.side_task_reviewer", R["side_task_reviewer"]), ("routing.extra_review_role", R["extra_review_role"])]
    refs += [("routing.side_task_roles", r) for r in R["side_task_roles"]]
    refs += [(f"routing.takeover.{k}", r) for k, t in R["takeover"].items() for r in (k, t.get("to"))]
    refs += [("routing.after_impl_fails.role", R["after_impl_fails"].get("role"))] if R["after_impl_fails"] else []
    refs += [("routing.usage.scoped_limit.role", U["scoped_limit"].get("role"))] if U["scoped_limit"] else []
    refs += [("routing.usage.cheap_first", r) for r in U["cheap_first"]]
    refs += [("routing.domain_roles", r) for r in R["domain_roles"].values()]
    refs += [("routing.side_task_domains", r) for r in R["side_task_domains"]]
    refs += [("routing.capacity_fallback", r) for kv in R["capacity_fallback"].items() for r in kv]
    refs += [("routing.usage.no_burst_effort", r) for r in U["no_burst_effort"]]
    for key in ("claude_fallback", "surplus_swap", "burst_swap"):
        refs += [(f"routing.usage.{key}", r) for kv in U[key].items() for r in kv]
    gate = U["escalation_gate"]
    refs += [("routing.usage.escalation_gate", gate.get(k)) for k in ("role", "first", "second_review") if gate]
    return [(w, r) for w, r in refs if r]


def account_key(directory):
    """Stable short key for an agent home (CODEX_HOME / CLAUDE_CONFIG_DIR): hash of its realpath, no secrets read."""
    return hashlib.sha1(os.path.realpath(directory).encode()).hexdigest()[:12]


def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")


def claude_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def xdg(var, default):
    return Path(os.environ.get(var) or os.path.expanduser(default))


def codex_journal():
    """Usage history, route mode, reset cache/log for one Codex account, shared by every project using it."""
    d = xdg("XDG_STATE_HOME", "~/.local/state") / "agent-team" / "codex" / account_key(codex_home())
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir():
    d = xdg("XDG_CACHE_HOME", "~/.cache") / "agent-team"
    d.mkdir(parents=True, exist_ok=True)
    return d


def claude_rate_file():
    d = cache_dir() / "claude" / account_key(claude_home())
    d.mkdir(parents=True, exist_ok=True)
    return d / "claude_rate_limits.json"


def template(cfg, rel):
    """Project templates_dir overrides the bundled templates."""
    override = cfg["project"].get("templates_dir")
    if override:
        p = cfg["root"] / override / rel
        if p.is_file():
            return p.read_text().strip()
    p = HERE / "templates" / rel
    return p.read_text().strip() if p.is_file() else ""


def lock(f, blocking=True):
    """Exclusive lock on an open file, held until it is closed; non-blocking raises BlockingIOError when taken."""
    if os.name != "nt":
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return
    import msvcrt
    f.seek(0)
    while True:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if not blocking:
                raise BlockingIOError("file is locked") from None
            time.sleep(0.1)


def command(argv, path=None):
    """argv with the program resolved on PATH. On Windows an npm .cmd shim is bypassed for its node script, because
    cmd.exe re-parses the arguments (quotes, |, &) and cuts them at the first newline."""
    exe = shutil.which(argv[0], path=path)
    if not exe:
        return list(argv)
    if os.name == "nt" and exe.lower().endswith(".cmd"):
        try:
            m = re.search(r'"%dp0%\\([^"]+\.js)"', Path(exe).read_text(errors="ignore"))
        except OSError:
            m = None
        base = Path(exe).parent
        node = base / "node.exe" if (base / "node.exe").is_file() else shutil.which("node", path=path)
        script = base / m.group(1).replace("\\", "/") if m else None
        if script and node and script.is_file():
            return [str(node), str(script), *argv[1:]]
    return [exe, *argv[1:]]


def change_noun(cfg):
    import vcs
    return vcs.adapter_class(cfg["vcs"]["kind"]).noun


def _get(cfg, dotted):
    cur = cfg
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def main():
    cfg = load()
    if sys.argv[1:2] == ["--get"]:
        v = _get(cfg, sys.argv[2])
        print(v if isinstance(v, str) else json.dumps(v, default=str))
        return
    p = cfg["roles"]["producer"]
    out = {"TEAM_CONFIG": cfg["config_path"], "TEAM_ROOT": str(cfg["root"]), "TEAM_STATE": str(cfg["state"]),
           "TEAM_NAME": cfg["project"]["name"], "TEAM_PRODUCER_CLI": p["cli"],
           "TEAM_PRODUCER_MODEL": p["model"], "TEAM_PRODUCER_EFFORT": p["effort"],
           "TEAM_NOTIFY_APP": cfg["notify"]["app_name"] or cfg["project"]["name"],
           "TEAM_NOTIFY_SOUND_DIR": cfg["notify"]["sound_dir"], "TEAM_NOTIFY_SOUND": cfg["notify"]["sound_normal"],
           "TEAM_NOTIFY_SOUND_URGENT": cfg["notify"]["sound_urgent"]}
    for k, v in out.items():
        print(f"{k}={shlex.quote(v)}")


if __name__ == "__main__":
    main()
