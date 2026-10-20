# Agent team UX review (t018)

Goal: after setup the queue runs until the roadmap is done and stops only for a gate, decision, escalation or
missing credentials. Priorities: P0 stalls the queue, P1 needs the user needlessly, P2 friction.
Status: **done** (file), **queued** (follow-up in `TASKS.md` "Next phase: Unattended queue") or **needs user**.

| Stage | Stall / friction | Pri | Fix | Status |
|---|---|---|---|---|
| Team-up | `team-up` must keep running: it is the only queue runner besides `team wait`; closed terminal = silent stall | P1 | Documented; coordinator tells the user to keep it open. A headless runner is a follow-up | queued (Q1) |
| Coordinator first message | Workspace line, setup offer and cadence question could stack three questions | P2 | Cadence is asked only when setup did not set it (`coordinator.md`) | done |
| Team-setup interview | Never seeded a plan: a fresh project got `refill empty` and an idle queue | P0 | New "Plan" question and "Plan seed" write (ROADMAP.md, "## Current phase"), then `team refill` (`team-setup/SKILL.md`) | done |
| Team-setup interview | Default `[locks]` has one `shared` lock, so `max_parallel = 3` is really 1 | P1 | Skill asks which areas can run in parallel; `team.toml` comment | done |
| Queue runner | Starts only while an alerts pane or `team wait` runs | P1 | See team-up | queued (Q1) |
| Refill / auto-promote | `TASKS.md` "## Current phase: Project bootstrapping" is stale: its only open item is the Windows PowerShell test, so refill finds nothing and tags the "Next phase" items (incl. Q1-Q3) `(needs user: not current phase)`; they are never auto-promoted | P0 | User decides: close or move the Windows item and make the next phase current (heading left unchanged here) | needs user |
| Refill / auto-promote | Promotion is done by the coordinator chat; proposals sit while the chat is closed or busy | P1 | Move auto-promote of unsuffixed `pNNN` lines into the queue pass (policy file still honoured) | queued (Q2) |
| Refill / auto-promote | When the current phase is done, refill returned only `none`/not-current-phase lines, a stop at every phase change | P2 | Refill splits the next ROADMAP outcome into tasks (suffixed, so the phase change stays a user decision) | done |
| Environment retries | Auto-retry (`auto-retry: env`) lives in the coordinator prompt; no chat = no retry | P1 | Move into `team.py`: one retry, only the `rc!=0`/no-result failure (not no-STATUS/no-VERDICT/ROUTE, auth, rate-limit or missing CLI); one `[routing]` cap key, `auto-retry: env` marker, unit test per branch | queued (Q3) |
| Escalation after failed plan review | Every escalation went to the user, including reviewer findings the planner could fix | P1 | Coordinator retries once per task (`auto-retry: plan`) when no finding asks the user a question | done |
| Router `ask` | Producer used `ask` for choices it could decide, blocking tasks | P1 | `route.md`: ask only when files cannot answer and a wrong guess is costly; else state the assumption | done |
| Review pages and cadence | Cadence unset until the coordinator asked; milestone/daily depend on the notifier staying up | P2 | Skill asks it during setup (already); `custom` stays coordinator-only | done (earlier tasks) |
| Notifier | Pops one page per pass for all attention items, fine; but it also is the queue runner (see team-up) | P2 | none beyond Q1 | queued (Q1) |
| Locks and parallelism | Probe-blocked or lock-held tasks wait silently | P2 | `team status` shows why; no change | none |
| Roadmap complete | Nothing said when all work is done | P2 | Coordinator says the roadmap is done on `refill empty` when plan files are complete | done |

## Planning stage evaluation

Existing: `team-setup` already interviews the user (goal, work kinds, rules); refill already reads the planning file
and ROADMAP.md and writes `pNNN` lines. Missing: nothing writes ROADMAP/planning items for a new project.

Option A, separate planning agent as a routed task: adds a route, a plan, a gate and a review before any
implementation, to restate answers the skill already holds. Option B, a Plan step in `team-setup` (done): the skill
drafts ROADMAP.md and the first phase from the answers, the user confirms in the same proposal, then `team refill`
seeds the queue. Cost: one extra question round, no new agent, no new gate.

**Recommendation:** B. Revisit a planning agent only for large greenfield scopes where the user wants an
architect-grade SPEC; that is a `team new --role architect` task, not a pipeline stage.

## Follow-ups (queue lines)

For the coordinator to run after review; the `TASKS.md` items are the main path. `team new` starts the task at once.

- Q1 `team new "Add a headless queue runner: team queue as a detached service (systemd user unit / Windows task) with a team-up check that warns when no runner is alive"`
- Q2 `team new "Auto-promote unsuffixed pNNN refill proposals inside the queue pass (team.py), honouring coordinator-policy.md and [queue] settings, with unit tests"`
- Q3 `team new "Move environment-failure auto-retry into team.py: one retry per task, only for the rc!=0/no-result failure (not no-STATUS, no-VERDICT, bad ROUTE, auth, rate-limit or missing-CLI), marked auto-retry: env, one [routing] cap key, unit test per branch"`
