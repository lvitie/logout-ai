#!/usr/bin/env python3
"""Opt-in Codex reset. A consume restarts the 7-day window at that moment;
run only when Codex is at the cap. --limit-hit bypasses only the usage threshold.
Usage: python3 codex_reset_consume.py --yes [--limit-hit]
Exit 0: reset/already redeemed; 2: refused; 1: unknown outcome (retry uses saved UUID).
No automatic invocation. Reads usage_tui --json --fresh-codex, never stale data. State: ${XDG_STATE_HOME}/agent-team/codex/<key>/.
Protocol: https://developers.openai.com/codex/app-server (local JSON schema for consume).
"""
import argparse
import importlib.machinery
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import teamcfg  # noqa: E402

STATE = teamcfg.codex_journal() / "codex_reset_log.json"  # per CODEX_HOME, shared by projects
COOLDOWN = 6 * 3600
OUTCOMES = {"reset", "nothingToReset", "noCredit", "alreadyRedeemed"}


class Refused(Exception):
    pass


def atomic_json(path, value):
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
            tmp = f.name
            json.dump(value, f, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if os.name == "nt":  # directories cannot be opened for fsync on Windows
            return
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def read_usage():
    try:
        p = subprocess.run([sys.executable, str(HERE / "usage_tui"), "--json", "--fresh-codex"],
                           capture_output=True, text=True, timeout=20, check=True)
        u = json.loads(p.stdout)
        if not isinstance(u, dict):
            raise ValueError()
    except (OSError, ValueError, subprocess.SubprocessError):
        raise Refused("fresh app-server evidence unavailable") from None
    now = time.time()
    stamp = u.get("codex_fetched_at")
    if (u.get("codex_source") != "app-server" or not number(stamp)
            or not now - 60 < stamp <= now):
        raise Refused("fresh app-server usage required")
    count = u.get("codex_reset_available_count")
    if type(count) is not int or count < 0:
        raise Refused("fresh credit count required")
    duration, reset = u.get("codex_7d_window_duration_mins"), u.get("codex_7d_resets_at")
    if (type(duration) is not int or duration != 10080 or type(reset) is not int
            or not now < reset <= now + 604800):
        raise Refused("valid 10080-minute window and future reset epoch in seconds required")
    pct = u.get("codex_7d")
    if pct is not None and (not number(pct) or not 0 <= pct <= 100):
        raise Refused("invalid usage")
    return u


def consume(key):
    loader = importlib.machinery.SourceFileLoader("reset_usage", str(HERE / "usage_tui"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    usage = importlib.util.module_from_spec(spec)
    loader.exec_module(usage)
    return usage._cx_request("account/rateLimitResetCredit/consume", {"idempotencyKey": key}, 15)


def load_state():
    if not STATE.exists():
        return {"version": 1, "attempts": []}
    try:
        state = json.loads(STATE.read_text())
        if state["version"] != 1 or not isinstance(state["attempts"], list):
            raise ValueError()
        keys = set()
        for i, row in enumerate(state["attempts"]):
            key = row["idempotencyKey"]
            uuid.UUID(key)
            if key in keys or not number(row["time"]) or not 0 < row["time"] <= time.time():
                raise ValueError()
            keys.add(key)
            if row["outcome"] not in OUTCOMES | {"pending", "failed", "unknown"}:
                raise ValueError()
            if row["outcome"] in {"pending", "failed", "unknown"} and i != len(state["attempts"]) - 1:
                raise ValueError()
            if not isinstance(row["before"], dict) or not (row["after"] is None or isinstance(row["after"], dict)):
                raise ValueError()
        return state
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Refused("invalid reset state; inspect before retrying") from None


def attempt(limit_hit):
    state = load_state()
    rows = state["attempts"]
    pending = rows[-1] if rows and rows[-1]["outcome"] in {"pending", "failed", "unknown"} else None
    if any(time.time() - row["time"] < COOLDOWN for row in rows if row is not pending):
        raise Refused("last consume is less than 6 hours ago")
    before = read_usage()
    row = pending
    if row is None:
        if before["codex_reset_available_count"] == 0:
            raise Refused("no available reset credits")
        pct = before.get("codex_7d")
        if not limit_hit and (pct is None or pct < 95):
            raise Refused("Codex 7d must be at least 95%; use --limit-hit only at a limit")
        row = {"idempotencyKey": str(uuid.uuid4()), "time": time.time(), "outcome": "pending",
               "before": before, "after": None}
        rows.append(row)
    else:
        row["reconciliation"] = before
    row["time"] = time.time()
    row["outcome"] = "pending"
    atomic_json(STATE, state)  # Persist the key before any possibly successful send.
    for retry in range(2):
        try:
            result = consume(row["idempotencyKey"])
            outcome = result["outcome"]
            if outcome not in OUTCOMES:
                raise ValueError("unknown consume outcome")
            break
        except Exception:
            row["outcome"] = "unknown"
            row["unknown_since"] = row.get("unknown_since", time.time())
            atomic_json(STATE, state)
            if retry == 1:
                return 1, "unknown outcome; attempt saved, retry uses the same idempotency key"
            row["reconciliation"] = read_usage()
            atomic_json(STATE, state)
    row["outcome"] = outcome
    row["time"] = time.time()
    atomic_json(STATE, state)  # A post-read failure must never cause another consume.
    try:
        row["after"] = read_usage()
        row.pop("after_error", None)
    except Exception:
        row["after_error"] = "usage refresh failed"
    atomic_json(STATE, state)
    return (0 if outcome in {"reset", "alreadyRedeemed"} else 2), outcome + ("; after usage unavailable" if row.get("after_error") else "")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--limit-hit", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.yes:
            raise Refused("--yes required")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with STATE.with_suffix(".json.lock").open("a") as lock:
            try:
                teamcfg.lock(lock, blocking=False)
            except BlockingIOError:
                raise Refused("another reset attempt is running") from None
            code, message = attempt(args.limit_hit)
    except Refused as e:
        code, message = 2, "refused: " + str(e)
    except Exception:
        code, message = 1, "failed; check local state and app-server availability"
    print("Codex reset: " + message)
    return code


if __name__ == "__main__":
    sys.exit(main())
