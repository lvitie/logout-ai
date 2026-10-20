# End-to-end smoke checklist

Manual run of the agent team with real Claude Code and Codex CLIs. Covers two TASKS.md items:
"Run a real Claude/Codex task end to end" (Part A) and "Run `team-setup` interactively" (Part B).
Reference: `docs/AGENT_TEAM.md`. Nothing here is automated.

**Needs your logins.** `claude` and `codex` must be signed in (`claude` once interactively, `codex login`).
The run spends real usage on both accounts. Sign-in is never copied or installed by the scripts.
Stop and report if a step shows an auth, usage-limit or missing-CLI error.

Set `LOGOUT_AI=<path to this checkout>` first. Use `--agents both` so each CLI is exercised.

## Part A: real task in a scratch git project

### A1. Scratch project

```bash
export LOGOUT_AI=/path/to/logout-ai
SCRATCH=$(mktemp -d)/smoke && mkdir -p "$SCRATCH" && cd "$SCRATCH"
git init -q && git config user.name smoke && git config user.email smoke@example.invalid
printf '# smoke\n' > README.md && git add README.md && git commit -qm init
```

- Expect: no output; `git status --short` is empty.

### A2. Setup

```bash
"$LOGOUT_AI/scripts/setup-agent-team.sh" --dry-run .
"$LOGOUT_AI/scripts/setup-agent-team.sh" --agents both --vcs git --bin-dir "$SCRATCH/bin" .
```

- Expect: dry run lists what it would write and changes nothing.
- Expect after the real run: `team.toml` and an executable `team.sh` in the project; `team` and `team-up` linked in
  `$SCRATCH/bin`; `.agent-team/` listed in `.git/info/exclude`.
- Then `export PATH="$SCRATCH/bin:$PATH"` and check `command -v team` is that link.

### A3. Launch the dashboard

```bash
./team.sh
```

- Expect: missing dependencies are installed (may ask for sudo), then Zellij opens with usage/focus, live log,
  alerts, tasks and coordinator panes.
- Expect: while `[project].team_setup` is empty, the coordinator's first reply is only the question "You have not
  ran `team-setup` in this workspace, do you want to do that now?" with Yes/No. Answer No here (Part B does it).
- Expect: the next reply states project root, VCS (`git`) and branch in one line, then answers your message.
- Headless fallback: skip A3 and use A4/A5 from a plain shell. Then the alerts pane is not running, so
  `team wait` or `team queue` must be running for queued tasks to start.

### A4. Queue one task per CLI

```bash
team new "add hello.py that prints hello world"                 # Producer routes it
team new --role <role> "add a LICENSE file with the MIT text"   # optional; roles: team.toml [routing].side_task_roles
team status
```

- Expect: `team new` prints the task id (`t001`, then `t002`) and routes it (`simple`/`complex`/`hard`, domain).
  With `--agents both`, Claude produces and reviews, Codex implements `simple`/`complex` work.
- Expect: `team status` lists each task with stage and state, advancing plan, implement, review. A task that
  cannot start shows `queued: ...` and starts on its own while `team wait`, `team queue` or the alerts pane runs.
- Use `team new --no-run "..."` then `team run <id>` to start a task by hand.

### A5. Wait for the result

```bash
team wait
```

- Expect: blocks, then prints one event (`done`, `gate`, `blocked`, `escalated`, `failed`, `stale`, ...) and exits.
  Re-run until every task is `done`. Act on gates with `team approve <id> ["note"]`, on a `failed` env error with
  one `team approve <id> "retry"`, and on review feedback with `team redo <id> "note"`.
- Expect: no commit was made. `git log --oneline` still shows only `init`.

### A6. Inspect the output

```bash
git status --short
git diff HEAD            # plus untracked files: git status shows them
ls .agent-team/t001/     # state.json  changes.diff  opened.txt  logs/  hand-offs (.md)
team review t001         # opens the HTML review page
```

- Expect: `hello.py` (and `LICENSE`) in the working tree, uncommitted; `.agent-team/` absent from `git status`.
- Expect: `.agent-team/t001/changes.diff` matches the task's share of `git diff HEAD`; hand-offs are `.md`.
- Expect: `team status t001` shows status, `<route>/<domain>`, the current stage and the hand-off paths
  (`NN-<stage>-<role>.md`). Take the role per stage from those names and its CLI from `team.toml`
  `[roles.<role>].cli`; the raw CLI output is `.agent-team/t001/logs/NN-<stage>-<role>.jsonl`.

### A7. Guard refusal

Show that routed agents cannot change history. Either read the logs of a task that tried, or force it:

```bash
team new "run 'git add -A && git commit -m x' and report the exact error, then stop"
team wait
grep -l "is not allowed" .agent-team/t0*/logs/* | head
```

- Expect: the agent reports the guard's refusal, e.g. `agent team: 'git commit' is not allowed; the user does this.`
  (same form for `git add`); the grep lists that task's log; `git log --oneline` is still only `init`;
  `git diff --cached --stat` is empty.
- Also try one refusal as yourself with `.agent-team/guard-bin` first on `PATH`: `PATH=$PWD/.agent-team/guard-bin:$PATH git commit --allow-empty -m x`
  must print `agent team: 'git commit' is not allowed; the user does this.` and exit non-zero. Do not leave a `git`
  commit behind.

### A8. Evidence to record in TASKS.md

Replace the item with `[x]` and a short note holding:

- Date, `claude --version`, `codex --version`, `--agents` preset, OS.
- Task ids run (e.g. `t001`, `t002`) and the role and CLI per stage (roles from the hand-off names in
  `team status <id>`, CLI from `team.toml` `[roles.<role>].cli`).
- Final states and any gates, escalations or retries, with the one-line reason.
- Working-tree diff: file names and line counts from `git diff HEAD --stat` (plus untracked files); confirm no commits.
- Guard refusals: the exact command refused and the refusal text (A7).
- Anything not exercised (e.g. headless fallback, no dashboard) and any defect found, as new TASKS.md items.

## Part B: `team-setup` interactively

Run once from a Claude coordinator and once from a Codex coordinator. Use a fresh copy of the scratch project each
time (repeat A1/A2 with `--agents claude`, then `--agents codex`), so the coordinator CLI is the one under test.
The coordinator uses the Producer's CLI; the preset decides which one that is.

### B1. Start

```bash
cd "$SCRATCH" && ./team.sh
grep -n team_setup team.toml     # [project] team_setup = ""  (empty before the run)
```

- Expect: the coordinator's first reply is only the Yes/No question about running `team-setup`. Answer Yes.
  (Or type: "set up the agent team", which loads `.agents/skills/team-setup/SKILL.md`.)
- Expect: the root/VCS/branch line comes in a later reply, after the question (see B2).

### B2. Interview

- Expect: the coordinator reads `team.toml`, templates and the repository before asking.
- Expect: rounds of at most four grouped questions, each waiting for your answer. Claude uses its question tool with
  options (recommended first). Codex uses `request_user_input` or one numbered list, then waits.
- Expect: the first round asks you to confirm workspace (root, VCS, branch).
- Cover: which default domains to keep (remove one and check `team status` still loads), specialists, agents and budget, locks/probes, rules, queue autonomy. Give concrete answers,
  including one specialist role and one lock.
- Expect: nothing is written yet. Check: `git status --short` and `git diff --stat team.toml` show no change.

### B3. Proposal and confirm

- Expect: a proposal that starts from the game-dev defaults (seven domains with their stage agents, the discipline agents, the
  `editor`/`gpu`/`build` locks, `p4`) and asks only what to confirm or change: roles (cli, model, effort), `domains`, `side_task_roles`, `[locks]`,
  `max_parallel`, `[probes]`, shared rules, and the files it will write. Ask for one change and check it is applied.
- Confirm. Expect writes to `team.toml`, `<templates_dir>/agents/*.md` and `roles/common.md` (the rules) and, for
  non-default queue autonomy, `<templates_dir>/coordinator-policy.md`.

### B4. Verify the result

```bash
grep -n team_setup team.toml          # now holds today's date
team status                            # config still loads; no error
team new --no-run "noop check"         # creates the task without routing (config-load check), then: team drop <id>
git status --short
```

- Expect: `team_setup` is a date; `team` loads the new config with no `teamcfg` error (unknown role names in
  `[routing]` are rejected, so this catches typos); new role files exist; your extra specialist is usable with
  `team new --role <name> --no-run "x"`.
- Expect: after a restart the first reply no longer asks about `team-setup`.
- Expect: a `team wait` is running again before the coordinator ends its turn.

### B5. Evidence to record in TASKS.md

Replace the item with `[x]` and a note per CLI:

- Date, coordinator CLI and version, preset.
- Number of question rounds, whether the question tool or the numbered fallback was used, and whether the
  workspace was confirmed first.
- Confirmation that nothing was written before you confirmed (B2 check).
- Files written (`git status --short` names) and the `team_setup` value.
- Result of the B4 commands (config loads, `--role` works), and the wait/first-reply behavior.
- Role and CLI per run: the coordinator is the Producer, so its CLI is `team.toml` `[roles.producer].cli`.
- Defects found as new TASKS.md items. Do not tick the box if a CLI was not run.

## Cleanup

```bash
team drop <id>                 # for leftover parked tasks
rm -rf "$SCRATCH"
```
