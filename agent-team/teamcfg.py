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
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOMAIN_STAGES = ("plan", "plan_review", "implement", "review")
STAGE_KINDS = DOMAIN_STAGES + ("plan_implement",)  # plan_implement: one agent plans, then implements, in one run
ROUTE_ALIASES = {"simple": "direct"}  # old route names still load; state and rules are read through canon_route
LIGHT_ROUTES = ("direct", "bundled", "planned")
UPGRADE = {"direct": "planned", "bundled": "planned", "planned": "complex"}  # route a failed review retries on
SKIPPABLE = ("plan", "plan_review")  # the review gate is never skipped; plan implies plan_review
AGENT_NAME = re.compile(r"^[a-z0-9_]+$")  # it becomes a file name and the `NN-kind-<agent>` stem
SKILL_NAME = re.compile(r"^[a-z0-9_-]+$")  # it becomes the file name skills/<name>.md
AGENT_KEYS = ("name", "scope", "model", "effort", "pin", "skill")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
EFFORT_ORDER = ("minimal",) + EFFORTS  # one total order over Claude and Codex effort words
CLI_EFFORTS = {"claude": EFFORT_ORDER[1:], "codex": EFFORT_ORDER[:-1]}  # what each cli accepts
RISKS, SIZES = ("low", "medium", "high"), ("small", "medium", "large")
HEURISTIC_STAGES = ("route",) + STAGE_KINDS
USAGE_STATES = ("low", "claude", "codex", "mixed")  # [[heuristic.rule]] when.usage
MCP_MODES = ("none", "write", "all")
CODEX_SANDBOXES = ("workspace-write", "user")  # [agents] codex_sandbox: user = writers follow ~/.codex/config.toml  # Claude runs: which stages load the user's MCP servers
CANONICAL_ROLES = ("producer", "mid", "senior", "architect", "director")
DEFAULTS = {
    "project": {"name": "project", "root": ".", "state_dir": ".agent-team", "templates_dir": "", "team_setup": "",
                "docs": ["AGENTS.md", "SPEC.md", "ROADMAP.md", "TASKS.md", "docs/"],
                "queue_file": "queue.txt", "planning_file": "TASKS.md"},
    "vcs": {"kind": "git", "guard_names": ["git"], "deny": {}, "deny_flags": {}},
    "agents": {"deny_extra": [], "mcp": "write", "user_skills": False, "codex_sandbox": "workspace-write"},
    "locks": {"names": [], "default": []},
    "routing": {"max_rounds": 2, "max_parallel": 3, "long_stage_min": 120, "domains": ["code"], "review_extra_domains": [],
                "extra_review_role": "", "extra_review_routes": [], "domain_roles": {}, "domain": {},
                "pipeline": {}, "skip": {}, "side_task_reviewer": "architect", "side_task_roles": [],
                "side_task_domains": {}, "takeover": {}, "after_impl_fails": {}, "capacity_fallback": {},
                "usage": {"enabled": False}},
    "queue": {"refill": True, "low_water": 1, "batch": 3, "daily_cap": 10, "pause_needs_you": 2, "cooldown_min": 30},
    "prompts": {"readonly_note": "Read-only stage: use tools only to inspect, never to change."},
    "notify": {"review_cadence": "task", "review_cadence_rule": "", "app_name": "", "sound_dir": "",
               "sound_normal": "message.oga", "sound_urgent": "alarm-clock-elapsed.oga"},
    "probes": {},
    "usage": {"claude_endpoint": False, "extra_module": ""},
}
USAGE_DEFAULTS = {"claude_fallback": {}, "limits": {"5h": 90.0, "7d": 95.0}, "scoped_limit": {},
                  "surplus_swap": {}, "burst_swap": {}, "burst_file": "", "cheap_first": [],
                  "no_burst_effort": {}, "escalation_gate": {}}


def canon_route(route):
    return ROUTE_ALIASES.get(route, route)


def norm_kind(kind):
    """Stage kind as the author of its work: plan_implement is the implement stage (and the plan author)."""
    return "implement" if kind == "plan_implement" else kind


def skip_set(cfg, route, domain):
    """Stage kinds the config skips for route/domain: [routing.skip] <route> plus [routing.domain.<name>] skip.
    Never on hard or custom routes, never review; skipping plan also skips plan_review."""
    route = canon_route(route)
    R = cfg["routing"]
    if route == "hard" or (route or "").startswith("custom:"):
        return frozenset()
    kinds = set(R["skip"].get(route, ())) | set(R["skip"].get("simple" if route == "direct" else route, ())) \
        | set(R["domain"].get(domain, {}).get("skip", ()))
    return frozenset(kinds | ({"plan_review"} if "plan" in kinds else set()))


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
    raw = tomllib.loads(path.read_text())
    cfg = _merge(DEFAULTS, raw)
    cfg["notify"] = {**cfg["notify"]}
    cfg["notify"]["review_cadence_set"] = bool(str(raw.get("notify", {}).get("review_cadence", "")).strip())
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
    if cfg["agents"]["mcp"] not in MCP_MODES:
        raise ValueError(f"team.toml [agents] mcp must be one of {', '.join(MCP_MODES)}")
    if cfg["agents"]["codex_sandbox"] not in CODEX_SANDBOXES:
        raise ValueError(f"team.toml [agents] codex_sandbox must be one of {', '.join(CODEX_SANDBOXES)}")
    pipes = cfg["routing"]["pipeline"]
    for alias, route in ROUTE_ALIASES.items():  # direct is canonical, simple the old name
        if route not in pipes and alias in pipes:
            pipes[route] = pipes[alias]
        elif alias not in pipes and route in pipes:
            pipes[alias] = pipes[route]
    for route in ("direct", "complex", "hard"):
        if route not in pipes:
            raise ValueError(f"team.toml [routing.pipeline] needs {route} (or simple)")
    for route, stages in pipes.items():
        for kind, role in stages:
            if role not in roles or kind not in STAGE_KINDS:
                raise ValueError(f"team.toml pipeline {route}: bad stage {kind}/{role}")
    _light_routes(pipes)
    _check_skip(cfg)
    cfg["heuristic"] = _load_heuristic(cfg, raw.get("heuristic"))
    cfg["agent_defs"] = _load_agents(cfg)
    _domain_tables(cfg)
    _check_side_tasks(cfg)
    _check_locks(cfg)
    _check_escalation(cfg)
    _check_pins(cfg)
    _check_floors(cfg)
    for where, role in _role_refs(cfg["routing"]):
        if role not in roles:
            raise ValueError(f"team.toml {where} references unknown role {role!r}")
    _check_apex(cfg)
    _check_scoped_limit(cfg)
    return cfg


def _check_scoped_limit(cfg):
    """[routing.usage.scoped_limit]: label + threshold; with role it diverts that role, without it guards the apex tier."""
    sc = cfg["routing"]["usage"]["scoped_limit"]
    if not sc:
        return
    if not isinstance(sc.get("label"), str) or not isinstance(sc.get("threshold"), (int, float)):
        raise ValueError("team.toml [routing.usage.scoped_limit] needs label (a usage key) and threshold (percent)")
    if not sc.get("role") and apex_rank(cfg["heuristic"]) is None:
        raise ValueError("team.toml [routing.usage.scoped_limit] without role guards the apex tier: add an apex "
                         "[heuristic.tiers] rank or name a role")


def _light_routes(pipes):
    """bundled and planned come from direct and complex unless the config defines them."""
    direct = pipes["direct"]
    impl = next((r for k, r in direct if k in ("implement", "plan_implement")), None)
    rev = next((r for k, r in direct if k == "review"), None)
    if "bundled" not in pipes and impl and rev:
        pipes["bundled"] = [["plan_implement", impl], ["review", rev]]
    if "planned" not in pipes:
        pipes["planned"] = [list(x) for x in pipes["complex"] if x[0] != "plan_review"]


def _check_skip(cfg):
    """[routing.skip] route -> stage kinds to skip; refused for hard and for review (the gate stays)."""
    R = cfg["routing"]
    for route, kinds in R["skip"].items():
        where = f"team.toml [routing.skip] {route}"
        if route not in R["pipeline"] or canon_route(route) == "hard":
            raise ValueError(f"{where}: not a route that may skip stages (hard never skips)")
        if not isinstance(kinds, list) or any(k not in SKIPPABLE for k in kinds):
            raise ValueError(f"{where} must be a list of {', '.join(SKIPPABLE)} (the review gate is never skipped)")


def _parse_agent(path):
    """Frontmatter (name, scope, optional model/effort pin) plus the instructions body of one agents/<name>.md."""
    text = path.read_text()
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)(.*)", text, re.S)
    if not m:
        raise ValueError(f"agent {path.name} needs a frontmatter block (--- name, scope ---)")
    meta, skill_lines = {}, []
    for line in m[1].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, sep, v = line.partition(":")
        k = k.strip()
        if not sep or k not in AGENT_KEYS:
            raise ValueError(f"agent {path.name}: unknown frontmatter line {line.strip()!r}")
        if k == "skill":  # repeatable; `#` stays part of the when-to-use line
            skill_lines.append(v.strip())
            continue
        v = re.sub(r"\s+#.*$", "", v).strip().strip("\"'")
        if k in meta:
            raise ValueError(f"agent {path.name}: duplicate {k}")
        if k == "pin":
            if v not in ("true", "false"):
                raise ValueError(f"agent {path.name}: pin must be true or false")
            v = v == "true"
        meta[k] = v
    for k in ("name", "scope"):
        if not meta.get(k):
            raise ValueError(f"agent {path.name} needs {k}")
    if not AGENT_NAME.match(meta["name"]) or meta["name"] != path.stem:
        raise ValueError(f"agent {path.name}: name {meta['name']!r} must be [a-z0-9_]+ and equal the file name")
    if "effort" in meta and meta["effort"] not in EFFORTS:
        raise ValueError(f"agent {meta['name']}: effort must be one of {', '.join(EFFORTS)}")
    for k in ("model", "effort"):
        if k in meta and not meta[k]:
            raise ValueError(f"agent {meta['name']}: {k} is empty")
    if meta.get("pin") and not ({"model", "effort"} & meta.keys()):
        raise ValueError(f"agent {meta['name']}: pin needs a model or effort")
    if not m[2].strip():
        raise ValueError(f"agent {meta['name']} has no instructions")
    skills = [_parse_skill(meta["name"], path, i, v) for i, v in enumerate(skill_lines, 1)]
    if skills:
        meta["skills"] = skills
    return {**meta, "instructions": m[2].strip()}


def _parse_skill(agent, path, n, value):
    """`skill: name | path | when` -> {name, path (absolute), when}. The path is tried next to the declaring file, then
    in the bundled agents/ dir, so a copied agent still finds the bundled ../skills/ files."""
    f = [x.strip() for x in value.split("|")]
    if len(f) != 3 or not all(f):
        raise ValueError(f"agent {agent}: skill {n} needs `name | path | when to use` (3 non-empty fields)")
    name, rel, when = f
    if not SKILL_NAME.match(name):
        raise ValueError(f"agent {agent}: skill {n} name {name!r} must be [a-z0-9_-]+")
    tried = [(base / rel).resolve() for base in (path.parent, HERE / "templates/agents")]
    for t in tried:
        if t.is_file() and t.read_text().strip():
            return {"name": name, "path": str(t), "when": when}
    raise ValueError(f"agent {agent}: skill {n} file not found or empty: {rel} (tried {', '.join(map(str, tried))})")


def _load_agents(cfg):
    """name -> agent. Lookup: templates_dir agents/ > templates_dir roles/ > bundled agents/ > bundled roles/. A [roles]
    key without a file is still an agent (instructions "": the generic prompt line)."""
    dirs = []
    if cfg["project"].get("templates_dir"):
        base = cfg["root"] / cfg["project"]["templates_dir"]
        dirs += [(base / "agents", True), (base / "roles", False)]
    dirs += [(HERE / "templates/agents", True), (HERE / "templates/roles", False)]
    agents = {}
    for d, front in dirs:
        for p in sorted(d.glob("*.md")) if d.is_dir() else []:
            if front:
                a = _parse_agent(p)
            elif p.stem in ("common", "coordinator"):
                continue
            else:  # legacy prompt: the whole file is the instructions
                a = {"name": p.stem, "scope": "", "instructions": p.read_text().strip()}
            agents.setdefault(p.stem, a)
    for key in cfg["roles"]:
        agents.setdefault(key, {"name": key, "scope": "", "instructions": ""})
    for a in agents.values():  # without [heuristic] model/effort stay exact; with it only `pin = true` is exact
        a["pinned"] = bool(("model" in a or "effort" in a) and (a.get("pin") or cfg["heuristic"] is None))
    return agents


def _stage_agents(cfg, route, dom):
    """kind -> agents of one route's stages for a domain with its explicit stage table applied."""
    over = cfg["routing"]["domain"].get(dom, {})
    out = {}
    for kind, role in cfg["routing"]["pipeline"][route]:
        if kind == "plan_implement":  # one agent authors both: the domain's implement agent
            out.setdefault("plan", []).append(over.get("implement", role))
            out.setdefault("implement", []).append(over.get("implement", role))
        else:
            out.setdefault(kind, []).append(over.get(kind, role))
    return out


def _check_escalation(cfg):
    """[routing.takeover.<role>] (`to` optional: without it the same agent steps up a tier) and
    [routing.after_impl_fails] (`fails`; `role` is ignored, escalation keeps the same agent)."""
    R = cfg["routing"]
    for agent, tk in R["takeover"].items():
        where = f"team.toml [routing.takeover.{agent}]"
        if not isinstance(tk, dict) or set(tk) - {"to", "after_reviews", "after_attempt"}:
            raise ValueError(f"{where} takes only to, after_reviews, after_attempt")
        to = tk.get("to")
        if not to:
            continue
        reviewers = {R["extra_review_role"], R["side_task_reviewer"]} if R["extra_review_role"] else {R["side_task_reviewer"]}
        for route in R["pipeline"]:  # never reuse the author as its own reviewer
            for dom in R["domains"]:
                got = _stage_agents(cfg, route, dom)
                if agent in got.get("implement", ()) and to in set(got.get("review", ())) | reviewers:
                    raise ValueError(f"{where} to = {to!r} reviews this work (route {route}, domain {dom})")
    af = R["after_impl_fails"]
    if af:
        if not isinstance(af, dict) or type(af.get("fails")) is not int or af["fails"] < 1 or set(af) - {"fails", "role"}:
            raise ValueError("team.toml [routing.after_impl_fails] needs fails = <integer >= 1>")
        if "role" in af:
            warnings.warn("team.toml [routing.after_impl_fails] role is ignored: the same agent steps up a tier", stacklevel=2)


def _domain_tables(cfg):
    """Fold the deprecated domain_roles into the unset plan/implement of [routing.domain.<name>], then validate."""
    R = cfg["routing"]
    R["domain"] = {d: (dict(t) if isinstance(t, dict) else t) for d, t in R["domain"].items()}  # never mutate DEFAULTS
    in_routes = {norm_kind(k) for stages in R["pipeline"].values() for k, _ in stages}
    in_routes |= {"plan" for stages in R["pipeline"].values() for k, _ in stages if k == "plan_implement"}
    cfg["deprecated_domain_roles"] = bool(R["domain_roles"])
    for dom, role in R["domain_roles"].items():
        tbl = R["domain"].setdefault(dom, {})
        if isinstance(tbl, dict):
            for k in ("plan", "implement"):
                if k in in_routes:
                    tbl.setdefault(k, role)
    for dom, tbl in R["domain"].items():
        where = f"team.toml [routing.domain.{dom}]"
        if dom not in R["domains"]:
            raise ValueError(f"{where} is not listed in routing.domains")
        if not isinstance(tbl, dict):
            raise ValueError(f"{where} must be a table")
        skip = tbl.get("skip", [])
        if not isinstance(skip, list) or any(k not in SKIPPABLE for k in skip):
            raise ValueError(f"{where} skip must be a list of {', '.join(SKIPPABLE)} (the review gate is never skipped)")
        for k, name in tbl.items():
            if k == "skip":
                continue
            if k not in DOMAIN_STAGES:
                raise ValueError(f"{where} has unknown stage {k!r} (use {', '.join(DOMAIN_STAGES)})")
            if k not in in_routes:
                raise ValueError(f"{where} stage {k} is in no route")
            if not isinstance(name, str) or name not in cfg["agent_defs"]:
                raise ValueError(f"{where} {k} references unknown agent {name!r}")
        for route in R["pipeline"]:  # a reviewer must not review its own work
            got = _stage_agents(cfg, route, dom)
            for review, author in (("plan_review", "plan"), ("review", "implement")):
                if (review in tbl or author in tbl) and set(got.get(review, ())) & set(got.get(author, ())):
                    raise ValueError(f"{where} route {route}: {review} agent must differ from the {author} agent")


def _check_side_tasks(cfg):
    """Side-task roles are agents (a [roles] key or an agent file); domain lists must name routing.domains."""
    R = cfg["routing"]
    for where, name in [("routing.side_task_roles", r) for r in R["side_task_roles"]] + \
            [("routing.side_task_domains", r) for r in R["side_task_domains"]]:
        if name not in cfg["agent_defs"]:
            raise ValueError(f"team.toml {where} references unknown agent {name!r}")
    for where, doms in (("routing.review_extra_domains", R["review_extra_domains"]),
                        ("routing.side_task_domains", list(R["side_task_domains"].values()))):
        bad = [d for d in doms if d not in R["domains"]]
        if bad:
            raise ValueError(f"team.toml {where} {bad[0]!r} is not listed in routing.domains")


def _check_locks(cfg):
    bad = [n for n in cfg["locks"]["default"] if n not in cfg["locks"]["names"]]
    if bad:
        raise ValueError(f"team.toml [locks] default {bad[0]!r} is not listed in names")


def _check_pins(cfg):
    """A model pin names a model some role runs; every profile the agent starts on must use that model's cli."""
    R = cfg["routing"]
    for name, a in cfg["agent_defs"].items():
        if "model" not in a or not a["pinned"]:
            continue
        clis = {r["cli"] for r in cfg["roles"].values() if r["model"] == a["model"]}
        if not clis:
            raise ValueError(f"agent {name}: pinned model {a['model']!r} is not the model of any [roles] entry")
        starts = {name} & set(cfg["roles"])
        for tbl in R["domain"].values():
            for stages in R["pipeline"].values():
                starts |= {role for kind, role in stages if tbl.get(kind) == name and name not in cfg["roles"]}
        bad = [r for r in starts if cfg["roles"][r]["cli"] not in clis]
        if bad:
            raise ValueError(f"agent {name}: pinned model {a['model']!r} does not fit the cli of {', '.join(sorted(bad))}")


def effort_rank(effort):
    return EFFORT_ORDER.index(effort)


def clamp_effort(cli, effort):
    """effort moved to the nearest word the cli accepts (claude has no minimal, codex no max)."""
    ok = CLI_EFFORTS[cli]
    return effort if effort in ok else (ok[0] if effort_rank(effort) < effort_rank(ok[0]) else ok[-1])


# The ladder bundled in templates/team.toml; unmodified, it adapts to configs whose roles run on another cli.
DEFAULT_LADDER = {"low": {"claude": "mid"}, "mid": {"claude": "mid_high"}, "high": {"claude": "senior"},
                  "top": {"claude": "director"}, "apex": {"claude": "apex"}}


def _load_heuristic(cfg, raw):
    """[heuristic.tiers] (ranks weakest -> strongest, each naming a [roles] profile per cli) and [[heuristic.rule]] ->
    {"tiers": [{"name", "claude", "codex"}], "rules": [{"name", "when", "min"}]}, or None without a table. A tier's
    cli entries are resolved to {role, cli, model, effort}, so a task can snapshot the whole ladder."""
    if raw is None:
        return None
    where = "team.toml [heuristic"
    if not isinstance(raw, dict) or set(raw) - {"tiers", "rule"}:
        raise ValueError(f"{where}] takes only tiers and rule")
    roles, tiers, names = cfg["roles"], [], set()
    bundled = raw.get("tiers") == DEFAULT_LADDER
    for name, entry in (raw.get("tiers") or {}).items():
        if not isinstance(entry, dict) or not entry or set(entry) - {"claude", "codex"}:
            raise ValueError(f"{where}.tiers] {name}: use {{claude = \"<role>\", codex = \"<role>\"}}")
        tier = {"name": name}
        for cli in ("claude", "codex"):
            role = entry.get(cli)
            if role is None:
                tier[cli] = None
                continue
            if role not in roles or roles[role]["cli"] != cli:
                if bundled:
                    tier[cli] = None  # bundled default: skip entries this config's roles do not run on that cli
                    continue
                raise ValueError(f"{where}.tiers] {name}: {cli} entry {role!r} is not a [roles] profile running {cli}")
            if roles[role]["effort"] not in CLI_EFFORTS[cli]:
                raise ValueError(f"{where}.tiers] {name}: role {role} effort {roles[role]['effort']!r} is not a {cli} effort")
            tier[cli] = {"role": role, "cli": cli, "model": roles[role]["model"], "effort": roles[role]["effort"]}
        if tiers and not (tier["claude"] or tier["codex"]):
            # only the weakest tier may end up empty: assign() only runs on ranks above an agent's own
            cli, role = next(iter(entry.items()))
            raise ValueError(f"{where}.tiers] {name}: {cli} entry {role!r} is not a [roles] profile running {cli}")
        tiers.append(tier)
        names.add(name)
    if not tiers:
        raise ValueError(f"{where}.tiers] needs at least one tier (weakest first)")
    rules = []
    for i, r in enumerate(raw.get("rule") or []):
        label = f"{where}.rule] #{i + 1}"
        if not isinstance(r, dict) or set(r) - {"name", "when", "min"}:
            raise ValueError(f"{label} takes only name, when, min")
        when, mn = r.get("when", {}), r.get("min", {})
        if not isinstance(when, dict) or not isinstance(mn, dict) or not mn or set(mn) - {"tier", "effort"}:
            raise ValueError(f"{label} needs when = {{...}} and min = {{ tier and/or effort }}")
        for k, v in when.items():
            vals = {"route": None, "domain": None, "risk": RISKS, "size": SIZES, "stage": HEURISTIC_STAGES,
                    "usage": USAGE_STATES}
            if k == "failures_min":
                if type(v) is not int or v < 1:
                    raise ValueError(f"{label} when.failures_min must be an integer >= 1")
                continue
            if k not in vals:
                raise ValueError(f"{label} has unknown when key {k!r} (use route, domain, risk, size, stage, "
                                 "failures_min, usage)")
            items = v if isinstance(v, list) else [v]
            if not items or any(not isinstance(x, str) or (vals[k] and x not in vals[k]) for x in items):
                raise ValueError(f"{label} when.{k} must be {'one of ' + ', '.join(vals[k]) if vals[k] else 'a name'}")
            if k == "route":
                bad = [x for x in items if x not in cfg["routing"]["pipeline"] and not x.startswith("custom")]
                if bad:
                    raise ValueError(f"{label} when.route {bad[0]!r} is not a route (use {', '.join(cfg['routing']['pipeline'])}, custom)")
            if k == "domain":
                bad = [x for x in items if x not in cfg["routing"]["domains"]]
                if bad:
                    raise ValueError(f"{label} when.domain {bad[0]!r} is not listed in routing.domains")
        if mn.get("tier") == "apex":
            raise ValueError(f"{label} min.tier 'apex' is reached by escalation only")
        if "tier" in mn and mn["tier"] not in names:
            raise ValueError(f"{label} min.tier {mn['tier']!r} is not a tier ({', '.join(sorted(names))})")
        if "effort" in mn and mn["effort"] not in EFFORT_ORDER:
            raise ValueError(f"{label} min.effort must be one of {', '.join(EFFORT_ORDER)}")
        rules.append({"name": str(r.get("name") or f"rule{i + 1}"), "when": when, "min": mn})
    if len({r["name"] for r in rules}) != len(rules):
        raise ValueError(f"{where}.rule] names must be unique")
    return {"tiers": tiers, "rules": rules}


def tier_rank(h, name):
    return next(i for i, t in enumerate(h["tiers"]) if t["name"] == name)


def role_rank(h, role):
    """Lowest rank whose profile on either cli is `role`, or None when the role sits on no rank."""
    return next((i for i, t in enumerate(h["tiers"]) if role in [(t[c] or {}).get("role") for c in ("claude", "codex")]), None)


def floor_rank(h, model):
    """Lowest rank where some cli's profile runs `model` (a frontmatter floor is valid on any cli), or None."""
    return next((i for i, t in enumerate(h["tiers"]) if model in [(t[c] or {}).get("model") for c in ("claude", "codex")]), None)


def own_rank(h, role, model, effort):
    """Rank a [roles] profile runs at unchanged: its role's rank, else the lowest rank running the same model and effort,
    else the lowest rank running its model, else 0."""
    r = role_rank(h, role)
    if r is None:
        r = next((i for i, t in enumerate(h["tiers"]) if any(
            p and (p["model"], p["effort"]) == (model, effort) for p in (t["claude"], t["codex"]))), None)
    if r is None:
        r = floor_rank(h, model)
    return r or 0


def apex_rank(h):
    """Rank of the tier named apex (reached by escalation only), or None."""
    return next((i for i, t in enumerate(h["tiers"]) if t["name"] == "apex"), None) if h else None


def _check_apex(cfg):
    """No rule, pipeline stage, domain, side task, role reference or unpinned floor may pick the apex tier."""
    h, R = cfg["heuristic"], cfg["routing"]
    top = apex_rank(h)
    if top is None:
        return

    def at_apex(role):
        r = cfg["roles"].get(role)
        return bool(r) and own_rank(h, role, r["model"], r["effort"]) == top

    for route, stages in R["pipeline"].items():
        for kind, role in stages:
            if at_apex(role):
                raise ValueError(f"team.toml pipeline {route}: {kind} role {role!r} runs at the apex tier (escalation only)")
    for dom, tbl in R["domain"].items():
        for kind, name in tbl.items():
            if at_apex(name):
                raise ValueError(f"team.toml routing.domain.{dom} {kind} {name!r} runs at the apex tier (escalation only)")
    for name in list(R["side_task_roles"]) + list(R["side_task_domains"]):
        if at_apex(name):
            raise ValueError(f"team.toml side-task role {name!r} runs at the apex tier (escalation only)")
    for where, role in _role_refs(R):
        if at_apex(role):
            raise ValueError(f"team.toml {where} references {role!r}, which runs at the apex tier (escalation only)")
    for name, a in cfg["agent_defs"].items():
        if "model" in a and not a["pinned"] and floor_rank(h, a["model"]) == top:
            raise ValueError(f"agent {name}: floor model {a['model']!r} is the apex tier's (escalation only; "
                             "pin = true is the explicit opt-out)")


def _check_floors(cfg):
    h = cfg["heuristic"]
    for name, a in cfg["agent_defs"].items():
        if h and "model" in a and not a["pinned"] and floor_rank(h, a["model"]) is None:
            raise ValueError(f"agent {name}: floor model {a['model']!r} is on no [heuristic.tiers] rank "
                             "(add a rank that runs it, or set pin = true)")
        if h and "effort" in a and a["effort"] not in EFFORT_ORDER:
            raise ValueError(f"agent {name}: effort must be one of {', '.join(EFFORT_ORDER)}")


def _matches(when, inp):
    for k, v in when.items():
        if k == "failures_min":
            if inp.get("failures", 0) < v:
                return False
            continue
        want, got = (v if isinstance(v, list) else [v]), inp.get(k)
        if k == "route":
            got, want = canon_route(got), [canon_route(x) for x in want]
            if str(got or "").startswith("custom:"):
                got = "custom"
        if k == "stage" and got == "plan_implement" and {"plan", "implement"} & set(want):
            continue  # a rule on either half applies to the combined stage
        if got not in want:
            return False
    return True


def resolve(h, inp, floor_model=None, floor_effort=None):
    """Pure heuristic decision. h: {"tiers", "rules"} (live config or a task snapshot); inp: route, domain, risk, size,
    stage, failures, usage (None = unknown or stale: `usage` rules never match). Rules are evaluated top to bottom and
    each sets a minimum, the highest wins (the first rule reaching it decides). The agent's frontmatter floor is
    applied afterwards and only raises. -> {"rank", "tier", "effort_min", "rules", "decided_by", "floor"}."""
    rank, by, emin, hit = 0, None, None, []
    for r in h["rules"]:
        if not _matches(r["when"], inp):
            continue
        hit.append(r["name"])
        if "tier" in r["min"] and (by is None or tier_rank(h, r["min"]["tier"]) > rank):
            rank, by = tier_rank(h, r["min"]["tier"]), r["name"]
        if "effort" in r["min"] and (emin is None or effort_rank(r["min"]["effort"]) > effort_rank(emin)):
            emin = r["min"]["effort"]
    floor = None
    if floor_model:
        fr = floor_rank(h, floor_model)
        if fr is not None and fr > rank:
            rank, floor = fr, f"floor model {floor_model}"
    if floor_effort and (emin is None or effort_rank(floor_effort) > effort_rank(emin)):
        emin = floor_effort
        floor = floor or f"floor effort {floor_effort}"
    return {"rank": rank, "tier": h["tiers"][rank]["name"], "effort_min": emin, "rules": hit,
            "decided_by": floor or by or "default", "floor": bool(floor)}


def assign(h, rank, prefer, effort_cap=None, effort_min=None):
    """(cli, role, model, effort) for rank `rank`: the preferred cli when the rank has it, else the other. The effort
    is the profile's, lowered to effort_cap (never below effort_min), raised to effort_min, clamped to the cli."""
    t = h["tiers"][rank]
    p = t[prefer] or t["claude" if prefer == "codex" else "codex"]
    return p["cli"], p["role"], p["model"], bound_effort(p["cli"], p["effort"], effort_cap, effort_min)


def bound_effort(cli, eff, effort_cap=None, effort_min=None):
    """`eff` lowered to effort_cap (never below effort_min), raised to effort_min, clamped to the cli."""
    if effort_cap and effort_rank(effort_cap) < effort_rank(eff):
        eff = effort_cap
    if effort_min and effort_rank(effort_min) > effort_rank(eff):
        eff = effort_min
    return clamp_effort(cli, eff)


def _role_refs(R):
    """(location, role) for every role name referenced outside [roles] and the pipeline."""
    U = R["usage"]
    refs = [("routing.side_task_reviewer", R["side_task_reviewer"]), ("routing.extra_review_role", R["extra_review_role"])]
    refs += [(f"routing.takeover.{k}", r) for k, t in R["takeover"].items() for r in (k, t.get("to"))]
    refs += [("routing.usage.scoped_limit.role", U["scoped_limit"].get("role"))] if U["scoped_limit"] else []
    refs += [("routing.usage.cheap_first", r) for r in U["cheap_first"]]
    refs += [("routing.domain_roles", r) for r in R["domain_roles"].values()]
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


def _skill_dirs(cfg):
    dirs = []
    if cfg["project"].get("templates_dir"):
        dirs.append(cfg["root"] / cfg["project"]["templates_dir"] / "skills")
    return dirs + [HERE / "templates/skills"]


def list_skills(cfg):
    """name -> first line of every task skill: templates_dir skills/ first, then the bundled ones."""
    out = {}
    for d in _skill_dirs(cfg):
        for p in sorted(d.glob("*.md")) if d.is_dir() else []:
            if SKILL_NAME.match(p.stem) and p.stem not in out:
                lines = p.read_text().strip().splitlines()
                out[p.stem] = lines[0].lstrip("# ").strip() if lines else ""
    return out


def load_skill(cfg, name):
    """Text of task skill <name> (templates_dir skills/, then bundled). ValueError for a bad or unknown name."""
    if not SKILL_NAME.match(name):
        raise ValueError(f"bad skill name {name!r} (use [a-z0-9_-]+)")
    for d in _skill_dirs(cfg):
        if (d / f"{name}.md").is_file():
            text = (d / f"{name}.md").read_text().strip()
            if not text:
                raise ValueError(f"skill {name} is empty ({d / f'{name}.md'})")
            return text
    raise ValueError(f"unknown skill {name!r} (available: {', '.join(list_skills(cfg)) or 'none'})")


def skill_tokens(text):
    """Skill references in a free-text list: split on commas and spaces, lowercased, punctuation and `none` dropped."""
    toks = (t.strip("*.,;:!`").lower() for t in re.split(r"[,\s]+", text or ""))
    return [t for t in toks if t and t != "none"]


def parse_skill_ref(token):
    """`name` or `name@stage` -> (name, stage or ""). Stage must be a domain stage (not route or refill)."""
    name, sep, stage = token.partition("@")
    if not SKILL_NAME.match(name):
        raise ValueError(f"bad skill name {name!r} (use [a-z0-9_-]+)")
    if sep and stage not in DOMAIN_STAGES:
        raise ValueError(f"bad skill stage {stage!r} in {token!r} (use {', '.join(DOMAIN_STAGES)})")
    return name, stage


def parse_skill_refs(text):
    return [parse_skill_ref(t) for t in skill_tokens(text)]


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
