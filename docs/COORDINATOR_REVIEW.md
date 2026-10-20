# Coordinator review: keep the queue moving

Goal: the coordinator chat coordinates. The queue keeps running unless it is
blocked on the user's input (a gate, a decision, an escalation). This review
covers `agent-team/templates/roles/coordinator.md`, the Producer templates, the
`team-setup` skill, the queue, refill and wait logic in `agent-team/team.py`,
and `docs/AGENT_TEAM.md`. Line numbers refer to `team.py` at the time of the
review.

Fixes 1–6 are in the prompts and docs. The code proposals at the end are not
implemented; a prompt-only fix covers each goal.

## 1. Restarting `team wait`

- **Finding:** the prompt said to restart `team wait` after reporting, but
  nothing said the turn must not end without one. A coordinator that answered a
  user question, or stopped to ask one, could leave the queue runner off. While
  no `team wait` (or alerts pane) runs, `dispatch` does not run and queued tasks
  do not start.
- **Fix (`coordinator.md`):** never end a turn without a background
  `team wait` running. On every exit, act on the events, restart the wait, then
  reply. CLIs whose background jobs do not wake the chat (Codex) run
  `team wait --no-block` at the start and end of each turn.

## 2. Environment-blocked tasks

- **Finding:** every `failed` and `stale` event went to the user, including
  failures with no user decision in them:
  - "`<agent>` exited `<rc>` with no result; see `<raw>`" (`:645`): a crashed or
    killed CLI.
  - "`<role>` gave no STATUS line" (`:711`) and "gave no VERDICT line" (`:719`):
    a truncated answer.
  - "Producer gave ROUTE=… DOMAIN=…" (`:687`): a malformed route.
  - stale: marked running, but no process holds the run lock (`:1206`).

  Restarting without a cap could loop forever (a run killed by OOM goes stale
  again). `team status <id>` does not print `notes` (`:1388-1398`), so a cap has
  to be read from `state.json`.
- **Fix (`coordinator.md`):**
  - stale: `team run <id>` once per task per session; if it goes stale again,
    report it.
  - failed with one of the reasons above:
    `team approve <id> "auto-retry: env (coordinator, not a user decision)"`.
    `cmd_approve` stores `Approved (<reason>): <note>` (`:1335`), and later
    prompts show it under "User notes", so the note says it was not the user.
  - report to the user instead when `{state_dir}/<id>/state.json` `notes`
    already holds `auto-retry: env`, or when the raw log shows an auth or login,
    usage or rate limit, or missing-CLI error.
  - `slow` events are information only.
  - Gates, escalations, `blocked` and every other failure still need the user.
    The old "approve gates only when the user says so" line now names the
    failed-task retry as its one exception.
- **Risk:** an env failure gets misclassified. The cap of one retry per task
  limits the cost to one extra agent run.

## 3. Keeping slots full

- **Finding:** slots already fill from the queue: `new`/`approve`/`redo`/`run`
  queue a task when capacity is short, and `dispatch` (`:886`) starts queued
  tasks while slots and locks are free. Slots run empty when no `team wait` is
  running (finding 1), when tasks are made with `--no-run` (never started by the
  queue), and when proposals wait on the user (finding 4).
- **Fix (`coordinator.md`):** do not hold work back or use `--no-run` unless the
  user asks; keep `team wait` running; auto-promote proposals (finding 4).

## 4. Refill and promotion policy

- **Finding:** the prompt said to promote or reject only what the user says, so
  every refill stalled the queue until the user answered. Nothing said which
  proposals are safe to queue. Also:
  - `refill failed` and `refill stale` retry by themselves after the cooldown
    (`refill_blocker`, `:960-985`; a failed refill leaves `empty_sig` unset,
    `:1057`), but the coordinator had no rule for them and could ask about them.
  - Planned queue lines include the user's own hand-written lines
    (`:968`, `:1007`), not only pNNN proposals.
  - The coordinator cannot tell a proposal's phase: refill reads the current
    phase and then `ROADMAP.md` (`:999-1000`), and proposals carry no source.
  - `_rewrite_queue` strips only `(after …)` (`:1112`), so any other suffix
    becomes part of the task request.
  - `queue_deps` reads `\(after ([^)]*)\)` (`:879`), so a `)` inside a suffix
    placed after `(after …)` would break it.
- **Fix:**
  - `jobs/refill.md`: the Producer ends a proposal with
    `(needs user: not current phase)` when it is not from the planning file's
    current phase, and `(needs user: <why>)` when it needs a user decision
    first. No parentheses inside `<why>`; the suffix goes before any
    `(after tNNN)`.
  - `coordinator.md` default: on `refill proposed`, `team promote` the event's
    pNNN keys whose line has no suffix, then tell the user. Show the suffixed
    ones; promote or reject them only on the user's word. Never auto-promote
    lines the user wrote.
  - Override: an `## Auto-promote policy` section in
    `<templates_dir>/coordinator-policy.md`. `team.py` never loads that file, so
    the policy does not reach routed agents (`roles/common.md` is added to every
    agent prompt, `:246`).
  - After the user approves a suffixed line, the coordinator deletes the suffix
    in `queue.txt`, then promotes. Refill appends under `_queue_file_lock`
    (`:1069-1081`) and a hand edit does not take it, so the coordinator skips
    the edit while `{state_dir}/refill/state.json` `status` is `running`.
  - `jobs/route.md`: the suffix alone is not a reason to route `ask`.
  - `refill failed` and `refill stale` are information only. `refill empty` is
    reported with the next step: add items to the current phase or
    `ROADMAP.md`.
- **Gate (resolved):** the user accepted the default (auto-promote
  current-phase proposals without a suffix).

The rule sits in `jobs/refill.md`, not `roles/producer.md`: the role line is
also used for routing, and team-setup writes a workspace `producer.md` that
overrides the bundled one, so a rule there would be lost.

## 5. Workspace up front

- **Finding:** nothing confirmed that the chat runs in the intended repo,
  branch or client. When `[project].team_setup` is empty, `chat` makes the
  first reply only the setup Yes/No question (`agent-team/chat:21-27`), so the
  check cannot go into that reply. team-setup never asked about the workspace.
- **Fix:**
  - `coordinator.md`: the first reply of a session, after the setup question
    when it was asked, states the project root, VCS kind and branch or client in
    one line. If a request names another repo or path, ask before `team new`.
  - team-setup: the first interview round shows the root, VCS and branch it
    read and has the user confirm them.

## 6. Avoidable questions

- **Finding:** "Approve gates only when the user says so" and "promote or reject
  only what the user says" made routine events into questions. Nothing told the
  coordinator to read before asking.
- **Fix (`coordinator.md`):** ask only when the answer changes what happens and
  cannot be read from the files, the config, the hand-offs or `team status`.
  Never ask permission for an action the rules allow, and never end a turn on
  such a question. The queue goal is stated as the first rule.

## Code proposals (not implemented)

- **Env failure class:** have `run_agent` and `step` tag allow-listed failures
  (for example `s["env"] = True`, or a stable reason prefix), and classify the
  raw log for auth, usage-limit and missing-CLI errors in code. The coordinator
  would then match a flag instead of reason text.
- **`[queue] auto_promote`:** a config key (`suffixless`, `all`, `none`) that
  `dispatch` applies under `_queue_file_lock`. Promotion would then not depend
  on a chat being open, and `coordinator-policy.md` could go.
- **Lock-safe suffix removal:** `team promote --clear-needs-user`, so the
  suffix is removed under the queue-file lock instead of by a hand edit.
- **`notes` in `team status <id>`:** print the notes so the retry cap can be
  read without opening `state.json`.
- **Bounded auto-restart in `team wait`:** a `--auto-retry` flag that restarts
  stale tasks once inside the wait loop, so the retry also happens while no
  chat is open.
