"""Token/cost/time report for agent-team runs (`team tokens`): reads <state_dir>/tNNN/logs/*.jsonl, the stage
files and state.json. Handles Claude (`result` event; falls back to the last usage of each assistant message when
a run was cut off) and Codex (`turn.completed`, summed; cost n/a). Log lines that are not JSON are skipped."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

STAGE = re.compile(r"^(\d+)-([a-z_]+)-([a-z_0-9]+)\.jsonl$")
READ_TOOLS = {"Read", "cat", "sed", "head", "tail"}


def _events(path):
    for line in Path(path).read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            yield ev


def run_stats(path):
    """One stage run -> dict(cli, fresh, cached, written, out, cost, ms, turns, tools, rereads, big, complete)."""
    r = dict(cli="", fresh=0, cached=0, written=0, out=0, cost=None, ms=0, turns=0, tools=Counter(), rereads=0, big=0,
             complete=False)
    msgs, seen, first = {}, Counter(), None
    for ev in _events(path):
        t = ev.get("type")
        if t == "result":  # Claude final event: totals for the whole run
            u = ev.get("usage") or {}
            r.update(cli="claude", complete=True, fresh=u.get("input_tokens", 0), written=u.get("cache_creation_input_tokens", 0),
                     cached=u.get("cache_read_input_tokens", 0), out=u.get("output_tokens", 0),
                     cost=ev.get("total_cost_usd"), ms=ev.get("duration_ms", 0), turns=ev.get("num_turns", 0))
        elif t == "assistant":
            m = ev.get("message") or {}
            if m.get("usage"):
                msgs[m.get("id") or len(msgs)] = m["usage"]
                first = first or m["usage"]
            for b in m.get("content") or []:
                if b.get("type") == "tool_use":
                    r["tools"][b.get("name")] += 1
                    i = b.get("input") or {}
                    if b.get("name") == "Read" and i.get("file_path"):
                        seen[i["file_path"]] += 1
        elif t == "user":
            for b in (ev.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and len(str(b.get("content"))) > 20000:
                    r["big"] += 1
        elif t == "turn.completed":
            u = ev.get("usage") or {}
            r["cli"] = "codex"
            r["complete"] = True
            r["fresh"] += max(0, u.get("input_tokens", 0) - u.get("cached_input_tokens", 0))
            r["cached"] += u.get("cached_input_tokens", 0)
            r["out"] += u.get("output_tokens", 0)
            r["turns"] += 1
        elif t == "item.completed" and (ev.get("item") or {}).get("type") == "command_execution":
            r["tools"]["Bash"] += 1
    if not r["complete"] and msgs:  # cut off: sum what each assistant message reported
        r["cli"] = "claude"
        for u in msgs.values():
            r["fresh"] += u.get("input_tokens", 0)
            r["written"] += u.get("cache_creation_input_tokens", 0)
            r["cached"] += u.get("cache_read_input_tokens", 0)
            r["out"] += u.get("output_tokens", 0)
        r["turns"] = len(msgs)
    r["rereads"] = sum(n - 1 for n in seen.values())
    r["first_input"] = sum((first or {}).get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return r


def collect(state_dir, ids=None):
    """[dict] one row per stage run: task, n, kind, agent + run_stats + prompt_chars."""
    rows = []
    for td in sorted(Path(state_dir).glob("t[0-9]*")):
        if ids and td.name not in ids:
            continue
        for f in sorted((td / "logs").glob("*.jsonl")):
            m = STAGE.match(f.name)
            if not m:
                continue
            row = run_stats(f)
            p = f.with_name(f.name[:-6] + ".prompt.md")
            row.update(task=td.name, n=int(m[1]), kind=m[2], agent=m[3], prompt_chars=p.stat().st_size if p.exists() else 0)
            rows.append(row)
    return rows


def quality(state_dir, ids=None):
    """{task: dict(plan_rounds, review_rounds, impl_fails, status)} from state.json."""
    out = {}
    for td in sorted(Path(state_dir).glob("t[0-9]*")):
        if ids and td.name not in ids:
            continue
        try:
            s = json.loads((td / "state.json").read_text())
        except (OSError, ValueError):
            continue
        out[td.name] = {k: s.get(k, 0) for k in ("plan_rounds", "review_rounds", "impl_fails")} | {"status": s.get("status")}
    return out


def total(r):
    return r["fresh"] + r["cached"] + r["written"]


def hit(rows):
    """Cache read share of all input tokens."""
    t = sum(total(r) for r in rows)
    return sum(r["cached"] for r in rows) / t if t else 0.0


def human(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(int(n))


def group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g


def table(rows, key, title):
    lines = [f"{title:18} {'runs':>4} {'input':>8} {'avg in':>8} {'out':>7} {'avg out':>8} {'cache%':>6} {'cost$':>7} {'min':>6}"]
    for k, g in sorted(group(rows, key).items(), key=lambda kv: -sum(total(r) for r in kv[1])):
        i, o = sum(total(r) for r in g), sum(r["out"] for r in g)
        cost = sum(r["cost"] or 0 for r in g)
        mins = sum(r["ms"] for r in g) / 60000
        lines.append(f"{str(k):18} {len(g):4} {human(i):>8} {human(i / len(g)):>8} {human(o):>7} {human(o / len(g)):>8} "
                     f"{hit(g) * 100:5.0f}% {cost:7.2f} {mins:6.1f}")
    return lines


def report(state_dir, ids=None, detail=False):
    rows = collect(state_dir, ids)
    if not rows:
        return ["No stage logs yet."]
    out = table(rows, lambda r: r["kind"], "stage kind") + [""] + table(rows, lambda r: r["agent"], "agent")
    out += ["", f"tools per run: {sum(sum(r['tools'].values()) for r in rows) / len(rows):.1f}; repeated Reads {sum(r['rereads'] for r in rows)}; "
            f"tool results >20k chars {sum(r['big'] for r in rows)}; runs cut off (no result) {sum(not r['complete'] for r in rows)}"]
    q = quality(state_dir, ids)
    tasks = group(rows, lambda r: r["task"])
    out += ["", f"{'task':6} {'status':9} {'runs':>4} {'input':>8} {'out':>7} {'cost$':>7} {'plan_r':>6} {'rev_r':>5} {'fails':>5}"]
    for t, g in sorted(tasks.items()):
        s = q.get(t, {})
        out.append(f"{t:6} {str(s.get('status', '')):9} {len(g):4} {human(sum(total(r) for r in g)):>8} "
                   f"{human(sum(r['out'] for r in g)):>7} {sum(r['cost'] or 0 for r in g):7.2f} "
                   f"{s.get('plan_rounds', 0):6} {s.get('review_rounds', 0):5} {s.get('impl_fails', 0):5}")
    if detail:
        out += ["", "per run: task n kind agent | input out turns first-turn | prompt chars | tools"]
        for r in rows:
            out.append(f"{r['task']} {r['n']:02d} {r['kind']}/{r['agent']} | {human(total(r))} {human(r['out'])} {r['turns']} "
                       f"{human(r['first_input'])} | {r['prompt_chars']} | {dict(r['tools'].most_common(4))}")
    return out
