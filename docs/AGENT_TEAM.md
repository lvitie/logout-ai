# Agent team

A game-development coordinator (the game-dev variant of this branch) that runs Claude Code and Codex CLI agents as a small team: a Producer routes a
task, then plan / implement / review stages run one agent at a time per task, with hand-offs as Markdown (`.md`) files. HTML pages are only for user reviews and blockers, never agent-to-agent handoffs. Extracted
from a larger game project; everything project-specific lives in one `team.toml` plus optional templates. The setup preset ships the game-dev
defaults (see [Game-dev defaults](#game-dev-defaults)); `team-setup` confirms and tailors them.

Requirements: Linux or Windows, Python 3.11 or newer (`tomllib`), `claude` and/or `codex` on `PATH`, `git` (or `p4`,
or another adapter). The dashboard uses Zellij on Linux and Windows Terminal on Windows. Locks use `fcntl` on Linux and `msvcrt` on Windows. The unit tests
use Linux fakes, so `scripts/validate.sh` runs them on Linux only; Windows CI runs `scripts/test-setup-agent-team.ps1`.
The dashboard's alerts pane (`notifier`) opens the HTML review page whenever a task needs the user or finishes,
notifies through `notify-send` (Linux, `notify`) or a tray balloon (Windows), and runs the task queue. Nothing here is installed by
`scripts/install.sh`; use the setup script below. The README has a step-by-step setup guide.

## Install

```bash
./scripts/setup-agent-team.sh --dry-run /path/to/project
./scripts/setup-agent-team.sh /path/to/project
```

```powershell
.\scripts\setup-agent-team.ps1 -TargetPath C:\path\to\project -DryRun
.\scripts\setup-agent-team.ps1 -TargetPath C:\path\to\project
```

The scripts are additive. The bash script writes `team.toml` and an executable `team.sh` into the project (kept if
present) and links `team` and `team-up` into `~/.local/bin` (`--bin-dir DIR` to change). The PowerShell script writes
`team.toml` and `team.ps1`, and generates `team.cmd`, `team-up.cmd` and an extensionless `team` shim for Git Bash in
`~/.local/bin` (`-BinDir DIR`), because Windows symlinks need Developer Mode or admin rights. The shims record the
Python interpreter found at setup; rerun setup after removing them if that interpreter moves. Both scripts share
`agent-team/write_config.py`. When they write a new `team.toml` they ask which agent CLIs to use:

- `claude`: Claude Code for every role.
- `codex`: Codex CLI for every role.
- `both`: Claude produces, plans `complex` work and reviews; Codex implements `direct`/`bundled`/`planned`/`complex` work, plans `hard`
  work and does the extra `hard` review, so each CLI reviews the other's output.

Then which version control the project uses:

- `git`: the built-in adapter (setup swaps in the git guard and deny lists); tasks share the working tree and the guard refuses commits, staging and history edits.
- `p4` (the template default, for Unreal projects): the Perforce adapter; each task gets a changelist, the guard refuses submit/revert/shelve/sync and the like,
  and git is denied entirely (the `[vcs]` block of `examples/unreal-p4/team.toml`).
- `none`: no version control; no guard, no deny rules, no submit step, and no git exclude entry. The edit hook lists
  the files agents write in `<state_dir>/<task>/touched.txt`; there is no diff, so reviewers read the files directly.

Pass `--agents claude|codex|both` and `--vcs git|p4|none` (`-Agents`, `-Vcs`) to skip the questions; without a terminal
setup picks what is on `PATH` (both, else codex, else claude) and detects the VCS (git for a git repository, else
p4 when installed, else git). Usage balancing (`[routing.usage]`) stays off in every preset. For a git project that
is already a repository, setup also adds the state directory (`.agent-team/`) to `.git/info/exclude`; otherwise add
it to the project's ignore list (or `P4IGNORE` file) yourself. The git adapter leaves the state directory out of `opened` and `diff` either
way. Then, from the project:

```bash
team new "add a stamina bar"      # create a change, route, run the pipeline
team new --no-run "later"         # create only; start with `team run <id>`
team new --skill tdd --skill perf-capture@review "..."  # task skills for this task (all stages, or one)
team new "..." --route direct     # override the Producer's route (direct|bundled|planned|complex|hard)
team status [id]                  # `-r` newest first; with an id also tokens, cost and skipped stages
team status --metrics             # per-route tokens, wall time, first-pass rate, rounds, upgrades, escalations
team tokens [ids] [--runs]        # tokens, cost, time per stage kind, agent and task
team approve <id> ["note"]        # pass a gate or retry after escalation/failure
team redo <id> "feedback"         # send back to the implementer (or Producer)
team drop <id> ["note"]           # abandon a task (its raw logs are tidied)
team tidy [ids]                   # delete raw logs and prompt copies of done/dropped tasks; token rows stay
team review [id ...]              # build and open the HTML review page (default: the latest done tasks)
team queue [--once]               # start queued tasks as capacity frees up (the alerts pane does this)
team hold [--res a,b] [--hours N] # lease [locks] to your own session (editor, GPU); agents' `team lock` waits
team burst <hours>                # spend Claude for N hours (0 ends it): writes [routing.usage] burst_file
team release                      # end the hold
team wait [--no-block]            # block until a task needs attention or finishes, print it, exit
team refill                       # ask the Producer for the next tasks now (pNNN lines in queue.txt)
team promote <key ...>|all        # queue planned queue.txt lines (proposals or your own) as tasks
team reject <key ...> [--why ..]  # drop planned lines; the Producer will not propose them again
team-up                           # dashboard: usage, focus, live log, tasks, alerts, coordinator chat
team-up "request"                 # same as team new
./team.sh                         # install missing dependencies and open the dashboard
.\team.ps1                        # the same on Windows
```

Review cadence (`[notify] review_cadence`; unset: the coordinator asks at session start and writes it, team-setup
asks it too): `task` opens a review page for each done task (default), `milestone` when every `- [ ]` item of the
planning file's `## Current phase` section is checked or its heading changes (items marked `Owner: user` or `user-only` do not count, so mark
user-owned open items that way, e.g. `TASKS.md:10`; with no such section it behaves like `task`), `daily` for the done
tasks of the day's first pass, and `custom` never opens them automatically: the coordinator follows
`review_cadence_rule` (free text, e.g. "every 3 done tasks"), keeping the last reviewed id in `decisions.md`. Under
`task`, `milestone` and `daily` the alerts pane (`notifier`) alone opens done-task pages, remembering unreported done
tasks in `<state_dir>/review_cadence.json`; the coordinator never runs `team review` for them. Gates, blocked, escalated
and failed tasks always reach you at once with their own page (except the coordinator's one env auto-retry). An invalid
value falls back to `task`. Hand-offs
stay Markdown; the review page is HTML for you only.

`team.sh` works from any directory and selects Linux Git before user wrappers.
On Fedora (`dnf`) or Debian/Ubuntu (`apt-get`), it installs missing Python, Git (only for `[vcs] kind = "git"`),
download utilities and, when a configured agent CLI is missing, Node/npm.
Missing Zellij is installed under `~/.local/bin` from the official 0.45.1
Linux x86_64/aarch64 release, verified against pinned SHA-256 digests; no extra
package repository is added. Agent CLIs are
installed with npm under `~/.local`; existing installations are kept. System
package installation may request sudo. Setup itself installs no dependencies;
running `team.sh` opts into these installations. Python must be 3.11 or newer.
The launcher records the Logout AI checkout location; set `LOGOUT_AI_ROOT` if
that checkout moves. CLI sign-in remains interactive and is never copied.
The dashboard coordinator uses the Producer's configured CLI, model and effort.

`team.ps1` is the Windows counterpart. It installs missing Python 3.13, Git for Windows, Node.js LTS and Windows
Terminal with `winget`, and missing agent CLIs with `npm install --global`. It refreshes `PATH` before detecting
dependencies and runs `team-up` with UTF-8 mode on. Each launch opens a fresh Windows Terminal window with native
console panes, so the coordinator has working terminal input and all panes resize with the window. The installed
Terminal executable is resolved from its package when `wt.exe` is an app-execution alias. Pane startup binds the
project explicitly and refreshes PATH, including when Terminal was already running before dependencies installed.
Both dashboards keep usage/focus and the log on the left, with alerts at the top right, then tasks and coordinator.
On Windows the coordinator runs npm-installed CLIs through their node script rather than the `.cmd` shim, because
`cmd.exe` re-parses arguments and cuts multi-line prompts. VCS guards become `.cmd` and Git Bash shims under
`guard-bin/` instead of symlinks.

When `new`, `approve`, `redo` or `run` finds no free slot (`max_parallel`), it saves the task as `new` and queued
with a `queued: ...` reason (notes and stage kept) and exits 0. Every 10 s the alerts pane, a waiting `team wait`
(every 5 s) or `team queue` starts queued tasks in `queue.txt` order, then by id, while slots are free; a task whose
queue line says `(after t003)` waits until t003 is done
(and is reported as held if t003 is dropped). `--no-run` tasks are
never started by the queue. Queue runs are detached from the dashboard, log to `<task>/logs/queue-run.log` and
recheck under the task's run lock that it is still queued, so two runners cannot run it twice. `team wait` is how the coordinator chat learns about
gate, blocked, escalated, failed and done tasks, stale ones (marked running, no process holds the run lock), slow
ones (a stage running longer than `[routing].long_stage_min`, 120 by default, 0 = never) and held ones; the alerts
pane notifies on the same events. It
remembers what it reported in `.wait-seen.json`, so changes between two waits are reported by the next one. The
first wait reports what needs attention but not tasks that were already done. Claude Code wakes the coordinator
when its background `team wait` exits; a CLI without that runs `team wait --no-block` at the start and end of each
turn. The coordinator never ends a turn without a `team wait` running: it acts on each exit, restarts the wait, then
replies. It stops only for the user's input (gates, decisions, escalations) and handles environment trouble itself,
once per task per session: a stale task gets `team run`; a failed task whose reason is "exited ... with no result",
"gave no STATUS line", "gave no VERDICT line" or "Producer gave ROUTE=... DOMAIN=..." gets
`team approve <id> "auto-retry: env (coordinator, not a user decision)"`, unless the task's `notes` already hold
`auto-retry: env` or its raw log shows an auth, usage-limit or missing-CLI error (then it reports to the user).
Every other failure, and gates, escalations and blocked tasks, wait for the user. Its first reply in a session
(after the setup question) states the project root, VCS and branch so a wrong workspace is caught early.
`docs/COORDINATOR_REVIEW.md` records the reasoning and the code changes proposed on top.

The coordinator chat may edit the team config, its role prompts, the hand-edited state inputs and planning docs
itself; project work still goes through `team new`. To tailor the team, ask the coordinator to set it up: it
follows the `team-setup` skill (`.agents/skills/team-setup/SKILL.md`, passed to both CLIs by path), which
interviews you about the project, proposes roles, models, domains, routing, locks, probes and shared rules, and
writes `team.toml`, `<templates_dir>/agents/*.md` and, for a non-default queue autonomy,
`<templates_dir>/coordinator-policy.md` only after you confirm. It records the date in
`[project] team_setup`; while that is empty, the coordinator's first reply in a session asks whether to run the setup
now (Yes/No) instead of answering.

Queue refill (`[queue]`, on by default): when queued tasks plus planned `queue.txt` lines drop below `low_water`
(1) and a slot is free, a queue pass starts `team refill` in the background. The Producer (read-only) reads the
planning file's current phase, then `ROADMAP.md`, and proposes up to `batch` (3) tasks, skipping user-owned items
and everything done, in flight, pending or rejected (it is shown that list). Proposals are appended as
`pNNN: <request>` lines; nothing runs until `team promote` turns lines into queued tasks in place (order and
`(after tNNN)` notes kept) or `team reject` drops them. The Producer ends a proposal with `(needs user: <why>)` when
it is not from the current phase or needs a user decision first. On `refill proposed` the coordinator promotes that
event's pNNN lines without the suffix and shows the rest to the user; it never auto-promotes lines you wrote. An
`## Auto-promote policy` section in `<templates_dir>/coordinator-policy.md` (read only by the coordinator) overrides
that default. When you approve a suffixed line, the coordinator deletes the suffix before `team promote` unless a
refill is running; the Producer does not route a task `ask` for the suffix alone. `team wait` and the alerts pane
report `refill proposed`, `refill empty` (no planned work left; the coordinator tells you what to add),
`refill failed` and `refill stale` (both retried after the cooldown without asking). Refill pauses while `pause_needs_you` (2) tasks wait for
the user, after `daily_cap` (10) proposals a day, for `cooldown_min` (30) between runs, after an empty result until
the planning file, `ROADMAP.md` or the number of done tasks changes, and while Claude usage is low.

`team` finds the config through `--config <path>` (before the subcommand), else `$TEAM_CONFIG`, else the nearest `team.toml` above the current directory. `teamcfg.load` rejects unknown role names anywhere in `[routing]`.

## Agent skills

An agent file may list skills it always has, one repeatable frontmatter line each: `skill: <name> | <path> | <when to use>`
(`name` is `[a-z0-9_-]+`; all three fields are required; `#` in the last field is kept). The prompt gets a short
`## Skills you have` table (name, absolute path, when) after the agent text; the agent reads a file when its situation
applies. The content is never inlined.

- The path is tried relative to the agent file, then relative to the bundled `agent-team/templates/agents/`, so a copied
  agent still finds bundled `../skills/<name>.md`. A missing or empty file fails `teamcfg.load` with the agent, the
  skill number and both tried paths.
- Skipped for the route and refill prompts and for agents without the line (legacy `roles/` files, `[roles]`-only keys).
- A row is dropped when a task skill (below) has the same name or resolves to the same file; the task skill stays inlined.
- Bundled: every discipline agent and `director` list their skills; `agent-team/templates/skills/INDEX.md` maps each
  skill to its AAA roles and agents (generated from the frontmatter, checked by `test_skill_library.py`).

## Task skills

A task skill is a Markdown file `<templates_dir>/skills/<name>.md` (`[a-z0-9_-]+`; bundled fallback in
`agent-team/templates/skills/`: the 41 game-dev skills listed in `INDEX.md`, researched in `docs/GAME_DEV_ROLES.md`; Blender skills in `docs/BLENDER_SKILLS.md`). It is extra instructions for one task, not part
of an agent and not tied to a domain.

- Attach with `team new --skill name[@stage]` (repeatable or comma list; stage is `plan`, `plan_review`, `implement` or
  `review`, default all). An unknown name or stage is rejected before the task is created. The Producer may add
  `SKILLS: name[@stage], ...` to its spec (`route.md` lists the available ones); unknown names and bad stages are
  dropped with a warning in the live log.
- The names are stored in the task's `state.json` (`skills`). The text is read at each launch and appended as
  `## Skill: <name>` after the request, only to that task's matching stages (never the route or refill prompts).
  Editing a skill file affects tasks still running; a deleted file fails the stage (restore it or edit `skills`).
- A warning is logged for a skill over 6000 characters or one attached to a stage the task's pipeline does not run.
  Queue lines and `team promote` have no skill syntax.

## Adaptive pipeline

The full plan -> plan_review -> implement -> review cycle runs only when the task needs it. The Producer picks the
lightest route that keeps the quality bar (criteria in `templates/jobs/route.md`):

| route | stages | when |
|---|---|---|
| `direct` (old `simple`) | implement, review | small, low risk, one file or clear spec, no design choice, reversible |
| `bundled` | plan_implement, review | like direct, but a short plan helps; the plan is the first section of the report |
| `planned` | plan, implement, review | plan matters, low/medium risk, reviewer catches design errors in the diff |
| `complex` | plan, plan_review, implement, review | design choices, medium/high size |
| `hard` | plan, plan_review, implement, review (+ extra review) | ambiguous, very hard; never skips |

- The review gate and the acceptance checks are identical on every route; a bundled report is reviewed for plan and change.
- Always plan + plan_review (complex/hard) for: high risk, schema/API/protocol changes, shared or hard-to-undo
  changes, ambiguity, earlier failed attempts. `route_task` raises a lighter pick to `complex` on high risk or earlier
  failures; a forced lighter route (`team new --route`) over a `hard` verdict stays `hard`.
- `plan_implement` is a stage kind for pipeline lists: one agent plans, then implements, in one run. It is the author
  of both plan and implement (reviewer-independence checks, `@plan`/`@implement` skills, the domain `implement` agent)
  and writes `plan` and `report` in the task state. Existing pipelines without it are unchanged; `simple` in state,
  config or rules is read as `direct`, and a stored `simple` task keeps its old behaviour (no upgrade).
- Skip defaults: `[routing.skip] complex = ["plan_review"]` and `skip = ["plan"]` in `[routing.domain.<name>]` drop those
  stages from non-hard routes (`plan` implies `plan_review`; `review` and `hard` are refused at load).
- Upgrade on failure: a failed review on a route without its plan retries one route up (`direct`/`bundled` -> `planned`,
  `planned` -> `complex`, a configured skip is dropped via `no_skip`) at the plan stage, which receives the review
  findings. The failed review counts once for `failures_min` (as an implementation failure; the upgrade adds nothing), and `redo` keeps `no_skip`.
- Tiers: `direct` and `planned` run on the roles of their stages (the cheap `mid` implementer; none of the
  hard/high-risk rules match). A `bundled` run starts on the implementer role, and the `bundled-implementer` rule gives it at least
  tier `mid` at medium/high risk. Escalation steps are kept when `plan_implement` becomes `implement`.

Metrics (defined before the routes; counters in `state.json` are cumulative and survive redo/approve): tokens per task
(`tokens.collect`), wall time (created to `first_finish`), first-pass review pass rate (`first_pass`, set by the first
review verdict only), review rounds (`review_rounds_total`, every review verdict), upgrades (`upgrades`), escalations
(`escalations`: tier step-ups and hand-offs to the user), skipped stage count, grouped by the route first chosen
(`route_initial`). `team status --metrics`, the focus panel (ROUTES) and the review page (Route metrics) show them;
skipped stages show as `skipped: plan,plan_review` in `team status <id>`, the focus rows and the review cards. Tune the
skip criteria from data: a route with a low first-pass rate or frequent upgrades should be used less.

## Layout

| Path | Purpose |
| --- | --- |
| `agent-team/team.py` | orchestrator (pipeline, role selection, locks, task state) |
| `agent-team/tokens.py` | `team tokens`: tokens, cost and time per stage kind, agent and task from the stage logs (or `state.json` `runs` once tidied) |
| `agent-team/winexec.py` | WSL: Windows programs for sandboxed Codex agents through a file spool (`[agents] windows_exec`) |
| `agent-team/teamcfg.py` | `team.toml` loader, XDG/agent-home helpers, template lookup |
| `agent-team/windows_dashboard.py` | native Windows Terminal layout and project-bound console panes |
| `agent-team/vcs.py`, `vcs_p4.py` | VCS adapter interface, git adapter, Perforce adapter |
| `agent-team/bin/` | `team`, `team-up` (Python, both platforms), `vcs-guard` |
| `agent-team/write_config.py` | writes a new `team.toml` from the agent and VCS presets (used by both setup scripts) |
| `agent-team/hooks/vcs_open.py` | Claude hook: opens files in the task change before edits |
| `agent-team/hooks/bash_guard.py` | Claude hook: denies killing processes by name, pattern or process group |
| `agent-team/usage_tui`, `codex_reset_consume.py`, `statusline_hook` | usage panel, opt-in Codex reset, Claude statusline dump |
| `agent-team/focus_tui`, `log_tui`, `tasks_tui`, `chat`, `notifier`, `notify` | dashboard panes, alerts and notifications |
| `agent-team/review_page`, `view_model`, `model_viewer/` | HTML review page (`team review`), local 3D model viewer |
| `agent-team/templates/` | `team.toml`, `team.sh`, `team.ps1`, `team.kdl`, `jobs/`, `agents/`, `roles/`, `skills/`, `vcs/` prompt templates |
| `examples/unreal-p4/` | the original Unreal + Perforce config and role files (examples only) |
| `agent-team/tests/` | unit and smoke tests |

## Config (`team.toml`)

`templates/team.toml` is a commented starting point; `examples/unreal-p4/team.toml` shows a large setup.
The template ships the game-dev defaults; setup (`write_config.py`) only rewrites the project name, the role
profiles, the `# --- ladder` rows and, for `git`/`none`, the `[vcs]` block.

- `[project]`: `name`, `root` (relative to the file), `state_dir`, `docs` (told to the Producer), `queue_file`,
  `planning_file`, optional `templates_dir` (overrides `jobs/`, `agents/`, `roles/`, `skills/`, `vcs/` files by relative path).
- `[vcs]`: `kind` (`git`, `none` or any `X` with `agent-team/vcs_X.py`), `guard_names`, `deny` (tool -> denied
  subcommands, `"*"` = whole tool), `deny_flags` (tool -> subcommand -> refused flags).
- `[agents].deny_extra`: extra Claude `Bash(...)` deny rules. Rules from `[vcs.deny]` are added automatically.
- `[agents].mcp` (`write` default, `none`, `all`): which stages load the user's MCP servers (read-only stages skip them by default).
  Claude gets `--strict-mcp-config`; Codex gets `-c mcp_servers.<name>.enabled=false` for every server in
  `$CODEX_HOME/config.toml` and `<workspace>/.codex/config.toml`, plus `-c features.apps=false` (Codex has no strict flag
  and merges `-c mcp_servers={}` into the user's table instead of replacing it);
  `[agents].user_skills` (default false): load the user's own skills/slash commands. See `docs/TOKEN_EFFICIENCY.md`.
  `[agents].codex_sandbox` (`workspace-write` default, `user`): `user` drops `-s workspace-write` for Codex writers so
  they follow the user's own `$CODEX_HOME/config.toml` (needed for editors, containers, GPU); read-only stages stay `-s read-only`.
  `[agents].resume` (default true): the plan, plan_review, implement, plan_implement and review stages continue the
  CLI session their kind and agent last ran on (`state.json` `sessions`, Claude `--session-id`/`--resume`, Codex
  `exec resume`) while the cli and model stay the same; a step to another tier, a takeover or a usage swap starts
  fresh. A resumed round gets one line, then only the prompt sections that changed since that session last saw them
  (new findings, report, notes, diagnosis), then the job. A resume the CLI refuses before any output is retried once
  fresh (`resume failed, fresh session` in `live.log`). Done and dropped tasks clear their sessions. Set false if
  resumed reviewers anchor on their earlier view.
  `[agents].windows_exec` (default `[]`, WSL only): Windows programs Codex writers may run, as file names
  (`["cmd.exe", "powershell.exe", "p4.exe"]`). WSL starts a `.exe` over an AF_VSOCK socket, which Codex's Linux sandbox
  refuses (`UtilBindVsockAnyPort: socket failed 1`, even with network access), so these go through `winexec.py`: the
  agent runs a listed program by bare name (a guard-bin shim) or `winexec <path> [args]`, the request lands in
  `<task>/winexec/`, and the team process runs it outside the sandbox and streams stdout, stderr and the exit code
  back (no stdin). Implement stages get the rule in their prompt. A listed program runs with the user's rights, so
  list only what agents need (`cmd.exe` can do anything). Read-only Codex stages cannot use it, and Claude agents
  (no sandbox) run the programs directly through the same shims.
- `[locks]`: `names` are shared resources (editor, GPU, build) that an agent leases only while it uses one:
  implement stages get the rule and the exact commands, `team lock <name> [--wait S]` before starting it (exit 3
  while another task or `team hold` has it) and `team unlock <name>` as soon as it stops. A lease lives in
  `<state_dir>/lease-<name>.json` and only counts while its task's run lock (or the hold process) is alive, and the
  run frees every lease of its task when it ends, so a forgotten or crashed lease never blocks others. Tasks no
  longer wait for resources to start; only `max_parallel` caps concurrent runs. `[locks.<name>]` may set
  `min_free_mib`, `probe_cmd` (prints free MiB first) and `skip_if_holds`: `team lock` refuses while the probe
  reports too little, skipped when the probe binary is missing or the task holds the `skip_if_holds` lock.
  `default` and `team new --res` still load for old configs and scripts but gate nothing. `team status` prints a
  `locks:` line while any lease is held.
- `[probes]`: `name = url`, reported to agents as `name up|down`. Empty by default.
- `[roles.<key>]`: `name`, `cli` (`claude`|`codex`), `model`, `effort`. `producer`, `mid`, `senior`, `architect`,
  `director` are required; others are free.
- `[routing]`: `pipeline.direct|bundled|planned|complex|hard` (stage kind + role lists; `simple` is the old name of `direct`; `bundled` and `planned` derive from `direct`/`complex` unless set), `skip` (see Adaptive pipeline), `domains`, `review_extra_domains`,
  `extra_review_routes`, `extra_review_role`, `domain.<name>`, `side_task_*`, `takeover.<role>`,
  `after_impl_fails`, `capacity_fallback`, `max_rounds` (minor failed review rounds per target before escalating to the user), `max_parallel`, `long_stage_min`.
- Agents: `agents/<name>.md` with frontmatter `name` (`[a-z0-9_]+`, equals the file name), `scope`, optional `model` and
  `effort` (an exact pin; `model` must be a `[roles]` model whose cli fits the agent) and the prompt as body. Lookup:
  `<templates_dir>/agents` > `<templates_dir>/roles` (plain prompt, legacy) > bundled `agents` > bundled `roles`. The
  names are the agent files plus the `[roles]` keys; a key without a file gets the generic prompt line. An agent
  without a `[roles]` entry runs on the route's role for that stage (cli, model, effort). `producer`, `mid`, `senior`,
  `architect`, `director` ship as bundled generic agents. Each launch is recorded in the task state (`launches`: stem
  `NN-kind-<agent>`, agent, profile, cli, model, effort, and for resumable stages `session` and `resumed`) before it starts. Without `[heuristic]` the frontmatter `model`
  and `effort` are exact; with it they are a floor (see below), and `pin = true` makes them exact again.
- `[heuristic]` (optional, the model/effort heuristic): `[heuristic.tiers]` is the ladder, weakest first, each tier
  naming a `[roles]` profile per cli (`low = { claude = "mid", codex = "mid_codex" }`; the shipped ladder is in `docs/MODEL_LADDER.md`; a tier may have one cli).
  `[[heuristic.rule]]` entries (`name`, `when`, `min`) are evaluated top to bottom. `when` keys (all must match; a list
  is any-of): `route` (`direct|bundled|planned|complex|hard|custom`; `simple` = `direct`), `domain`, `risk` (`low|medium|high`), `size`
  (`small|medium|large`), `stage` (`route|plan|plan_review|implement|plan_implement|review`; a `plan_implement` run matches `plan` and `implement` rules), `failures_min` (rejected plans plus
  implementations of this task) and `usage` (`low|claude|codex|mixed`). `min` has `tier` and/or `effort`. A rule sets
  a minimum only (there is no exact-tier key, a settled choice): the highest tier minimum wins (the first rule
  reaching it decides), no matching rule gives the weakest tier, and the effort is the highest of the profile's effort,
  the rules' effort minimum and the agent's floor effort, clamped to what the cli accepts (`minimal < low < medium <
  high < xhigh < max`). The stage's own `[roles]` profile is a floor too: up to its rank (the rank naming that role,
  else the lowest rank running its model, else the weakest) the stage runs that profile unchanged and usage swaps as
  without a ladder (never below the rules' tier); only a rule, floor or step-up above it picks the tier's profile.
  A ladder without rules changes nothing until an escalation steps a stage up; the shipped rules (below) raise the tier. `risk` and `size` come from the Producer's `RISK:`/`SIZE:` lines (side tasks: `team new
  --risk --size`); a missing or invalid value is `high`/`large` with a warning. The route stage itself runs before
  they are known, so no `risk` or `size` rule matches it.
  - Agent `model`/`effort` is applied after the rules as a floor: the tier never drops below the lowest rank whose
    profile runs that model (on any cli; at load a floor model must be on some rank), the effort never below the floor
    effort. `pin = true` runs exactly that model and effort (it needs only be a `[roles]` model that fits the cli) and
    skips the rules; a `role_override.json` entry also runs exactly its role and logs `override`.
  - `[routing.usage]` still balances plans, but only chooses the cli of the tier: `cheap_first`, `claude_fallback`,
    the Codex-first branch, `surplus_swap` and `burst_swap` switch to the tier's profile on the other cli (skipped
    with a log line when the tier has none). `escalation_gate` and `capacity_fallback` targets must sit on a rank at
    or above the tier or are skipped (a capacity retry with nothing left blocks the task). `no_burst_effort` lowers
    the effort only down to the rules' and floor minimum. `enabled`, `limits`, `scoped_limit` and `burst_file` are
    inputs only (a role-less `scoped_limit` also picks the cli at apex: the apex guard below). A `takeover.<role>.to` reassigns the agent (its profile then comes from the heuristic); otherwise
    escalation keeps the same agent (see Escalation).
  - The `usage` input is only taken from a fresh, successful read (under 120 s old); disabled, failed or stale data
    never matches a `usage` rule, and the launch log says why.
  - Each launch logs `heuristic <stage>: <tier> via <rule> (rules: ...) -> <profile> <cli> <model> <effort>` in
    `live.log` and records inputs, matched rules, tier and assignment in `launches[].heuristic`. The first decision
    snapshots the ladder and rules into the task's `state.json` (`heuristic`): later stages and a config edit use the
    snapshot, and a resumed unfinished launch reuses its tier. The refill run never uses the table.
- Escalation (needs the `[heuristic.tiers]` ladder; `scripts/setup-agent-team` writes one per agent preset in the
  `# --- ladder` block of `team.toml`). Reviewers (`review`, `plan_review`) end with `VERDICT:` and, on FAIL,
  `SEVERITY: minor|major|critical` and optionally `ESCALATE: yes <reason>` (a PASS with `ESCALATE` counts as a fail).
  A FAIL without a valid `SEVERITY` is major. The retry of the failed target (plan or implement) runs the same agent:
  - minor: no step; counts against `max_rounds` (minor failed rounds per target), then the task goes to the user.
  - major: steps the target up one tier (recorded in `state.json` `stepped`, applied as a floor under the rules).
  - critical or `ESCALATE: yes`: one tier plus a `## Diagnosis required` prompt section (root cause first) until the
    review passes.
  - Already at the strongest tier, or no ladder, a `pin = true` agent or a `role_override`: the task is `escalated`
    to the user. `team approve` then retries at the strongest tier (the next major failure escalates again);
    `team redo` clears the steps, diagnosis and minor rounds.
  - `[routing.takeover.<role>]` (`after_reviews`, `after_attempt`): without `to`, steps the same agent up once the
    condition is met; with `to`, that other agent takes over (it must not review the work, checked at load).
  - `[routing.after_impl_fails]` `fails = N`: steps up once at the Nth failed implementation (`role` is ignored with a
    warning).
  - One review failure gives at most one step, whichever rules fired.
- `[routing.domain.<name>]` (optional, name must be in `domains`): `plan`, `plan_review`, `implement`, `review` name
  agents; unset = the route's role. `plan_review` must differ from `plan`, `review` from `implement`. Unknown agent
  or stage fails at load. `[routing.domain_roles]` is
  deprecated (= `plan` and `implement` set to that role; the explicit table wins) and prints a note on the CLI.
- `[queue]`: `refill`, `low_water`, `batch`, `daily_cap`, `pause_needs_you`, `cooldown_min` (see above).
- `[routing.usage]`: optional Claude/Codex plan balancing (`enabled = false` by default): `claude_fallback`,
  `limits`, `scoped_limit`, `surplus_swap`, `burst_swap`, `burst_file`, `cheap_first`, `no_burst_effort`,
  `escalation_gate`. Needs both CLIs and `usage_tui` data.
  - `scoped_limit = { label, threshold, role? }`: a model-scoped usage window (`usage_tui --json` key, e.g.
    `"7d Fable"`). With `role`, that role falls back via `claude_fallback` at or above the threshold. Without `role`
    it is the apex guard (needs an apex tier): a stage stepped up to apex whose tier profile is Claude runs the apex
    tier's codex profile instead, or, without one, goes to the user (`escalated`; `team approve` lets that task spend
    apex, `team redo` drops it). The guard also applies while the Claude `limits` are reached, burst or not.
  - Burst: while `burst_file` (under `state_dir`) holds a future epoch deadline (`team burst <hours>`), routing acts
    as in Claude surplus: `cheap_first` and the Codex-first branch are off, `surplus_swap` plus `burst_swap` move
    Codex roles to Claude, and the apex guard's threshold is ignored. The Claude `limits` still apply.
    `team status` shows `burst: active until ...`.
- `[prompts]`, `[notify]`, `[usage]`: read-only stage note, notification `review_cadence`, `review_cadence_rule`,
  app name and sound dir, `claude_endpoint` and `extra_module` (empty by default: a root-relative Python file whose
  `rows(cfg, compact)` returns `(drop_tier, line)` panel rows and `json(cfg, timeout)` returns extra `--json` keys; it
  gets `usage_tui`'s namespace as `ui` for `bar`/`compact_row`; errors there never break the panel).

Prompt templates use `{project}`, `{change_noun}`, `{domains}`, `{docs}` and `{state_dir}`.

## VCS adapters

A change is a string id. Interface: `new_change(desc, hint)`, `set_description(change, desc)`,
`opened(change)`, `opened_files(change)`, `diff(change)`, `others_opened(change)`,
`prepare_edit(path, change) -> (ok, msg)`, `add(path, change) -> (ok, msg)`, `pending_changes()`, `changed_files(change)`.
Adapters never submit, commit, stage, revert or shelve.

- git: change id = task id, the description lives in task state only, all tasks share the working tree,
  `opened` = `git status --porcelain -uall`, `diff` = `git diff HEAD` plus `git diff --no-index` for untracked
  files, nothing is staged. Run one writing task at a time, or give parallel tasks separate worktrees.
- none: change id = task id; the hook records each written file (root-relative, state dir skipped) in
  `<state_dir>/<task>/touched.txt`, `opened` lists them, `diff` is empty. `submit_step = False` drops the "user submits it"
  wording; `guard_names = []` installs no guard.
- p4: a numbered pending changelist per task; the hook opens files with `p4 edit -c` and moves default-changelist
  strays into the task changelist.

`bin/vcs-guard` is symlinked by `team.py` under each `guard_names` entry in `<state_dir>/guard-bin/` (on Windows:
`<name>.cmd` and a Git Bash `<name>` shim that set `TEAM_GUARD_TOOL`), which is put first on the agents' `PATH` (`TEAM_REAL_<TOOL>` holds the real binary; without it the guard takes the first
non-guard match on `PATH`). It refuses `[vcs.deny]` subcommands and `[vcs.deny_flags]` flags for both Claude and
Codex agents, including when reached through a git alias (`-c alias.x=...` or configured), and refuses git shell
aliases (`!...`). `git` is exempt when the working directory is a repo outside the project root (temp-dir test
fixtures, so `./scripts/validate.sh` and the unit tests run inside an agent): `team.py` writes `guard-bin/root` and
`guard-bin/config` (and the Windows shims pass `TEAM_GUARD_ROOT`/`TEAM_GUARD_CONFIG`), and the guard checks
`git rev-parse --show-toplevel --git-common-dir` (symlinks resolved, `-C`/`--git-dir`/`GIT_DIR` honoured, only at
the point a denial would fire, so aliases are covered). `push` is never exempt. Anything inside the root, a worktree
sharing the root's repo, a failed probe, missing guard files (old installs, until the next `team.py` run) or a non-git `[vcs].kind`
stays denied. The guard is a guardrail against accidental commits, not a security boundary: an agent can still
run the real binary by absolute path. The hard limit for Codex writers is its `workspace-write` sandbox, which keeps
`.git` read-only (network access follows `[sandbox_workspace_write]` in the Codex config, off by default, except for
writers when the adapter sets `sandbox_network = True`, as p4 and custom adapters do by default: `p4 edit`/`add` must
reach the server; git and none keep it off); Claude agents get the same subcommands as
`Bash(...)` deny rules. Codex has no edit hook, so the files its `file_change` events report are opened (`prepare_edit`)
or added in the task's change as they arrive; a file that cannot be opened (e.g. locked elsewhere) blocks the task
with the file named, and deletions are left to the agent.
Codex runs with `--skip-git-repo-check`, so Perforce and other non-git workspaces work.

Agents may kill only a PID they started and recorded: killing by name once took down the user's dashboard.
`guard-bin/` holds refusing `pkill` and `killall` shims (POSIX), `hooks/bash_guard.py` denies Claude Bash commands
that kill by name or pattern (`pgrep ... | xargs kill`, `kill $(pidof x)`, `taskkill /IM`, `Stop-Process -Name`) or
signal PID <= 0 or a process group, and `codex-home/rules/default.rules` forbids the simple forms for Codex. The team
itself starts each agent in its own session (POSIX) and kills that process group after the run, so background shells an
agent left behind cannot hold the run open. A model counts as at capacity only when the CLI's own errors (stderr,
`error`/`turn.failed`/error `result` events) say 503, at capacity, Service Unavailable or overloaded; a fallback cycle in
`capacity_fallback` stops after each role was tried once.

The focus pane shows the planning focus, running tasks (stage, planned and actual role, model and effort, round,
elapsed time, the agent's last line), lease holders, what needs you (gates, blocked, escalated, failed and corrupt
tasks, tasks marked running whose process is gone, user-owned planning items, pending changes), the queue with why
each task waits, and today's finished tasks. A task counts as running only while a team process holds its
`.lock-run`.

## State and runtime inputs

Per project, under `state_dir`: `live.log`, `tNNN/` task folders (`state.json`, `.lock-run` held while it runs, hand-offs, `logs/`, `opened.txt`,
`changes.diff`, `user_opened.txt`, `packet/`), `.lock-*`, `lease-<name>.json`, `learnings.md`, `.wait-seen.json`, `refill/` (refill runs and the proposal log), `guard-bin/`, `team.kdl`, `review/`. Optional inputs you
create by hand: `queue.txt` (`tNNN: title` lines; their order and `(after tNNN)` notes drive the queue), `decisions.md` (shown by `review_page`), `role_override.json`
(`{"t012": {"review": "director", "implement": "senior", "after_failed_reviews": 1}}`) and the `burst_file`
(epoch deadline).

End of a task. When a task reaches done, two quick steps run before the run ends:
- Learnings: if anything went wrong (a failed first review or plan, an escalation, a route upgrade or a user note), one
  cheap read-only Producer call (`jobs/learn.md`, no skills or heuristic) folds the lesson into
  `<state_dir>/learnings.md`: at most 20 bullets of at most 25 words, merged and pruned, or `UNCHANGED`. The file is
  not committed. Every stage prompt but refill carries it as `## Learnings from earlier tasks`; edit or delete it by
  hand at any time. A failing learn call never changes the task.
- Tidy: the token rows of the task's stage logs go into `state.json` `runs` (so `team tokens`, `--metrics` and the
  review page keep working), then `logs/*.jsonl` and `logs/*.prompt.md` are deleted (about 85% of the state size) and
  the agent sessions are cleared. Hand-offs, `changes.diff` and `state.json` stay. `team drop` tidies too;
  `team tidy` does it for older tasks.

Per Codex account, shared by every project using the same `$CODEX_HOME`:
`${XDG_STATE_HOME:-~/.local/state}/agent-team/codex/<sha1(realpath $CODEX_HOME)[:12]>/` holds `usage_hist.jsonl`,
`route_mode.json`, `codex_resets.json` (cache), `codex_resets.txt` (manual count, optional),
`codex_push.json` (optional `{"target": 95, "until": "<ISO time with zone>"}`) and `codex_reset_log.json`. Claude
rate limits dumped by `statusline_hook` go to `${XDG_CACHE_HOME:-~/.cache}/agent-team/claude/<key>/`. To use the
dump, set it as Claude Code's `statusLine` command.

## Credentials and network

- Agents run `claude -p` and `codex exec` with the user's own logins; the team never reads or copies them.
- The Codex coordinator chat runs with `-s danger-full-access`, like the unsandboxed Claude one: `team` starts agents
  that need network and write outside the project. Approval prompts follow the user's Codex config.
- Claude runs with `--permission-mode auto`; read-only stages are limited to `Read,Glob,Grep`. Codex runs with
  `-s read-only` for read-only stages and `-s workspace-write` for implementers, whatever `$CODEX_HOME/config.toml`
  sets (unless `[agents] codex_sandbox = "user"`).
- `usage_tui` reads `$CODEX_HOME/sessions/**/*.jsonl` (only `rate_limits` lines), `$CLAUDE_CONFIG_DIR/projects/**/*.jsonl`
  (token counts) and spawns `codex app-server` for reset credits. It never reads `auth.json`.
- Only with `[usage] claude_endpoint = true` does `usage_tui` read `$CLAUDE_CONFIG_DIR/.credentials.json` and
  call Claude's usage endpoint with that token. Off by default.
- `[usage] extra_module` runs project code inside `usage_tui`; what it reads or calls is that project's business.
- `codex_reset_consume.py --yes` is opt-in, spends a Codex reset credit and is never called automatically.
- `[probes]` URLs are the only other network access (1 s HTTP GET).

## Game-dev defaults

What `templates/team.toml` and the setup preset ship, and what `team-setup` confirms and tailors:

- Agents (`templates/agents/`): `producer`, `designer`, `gameplay`, `engine`, `tools`, `technical_artist`, `audio`, `qa`,
  `build_release`, `director`, the side-task agents `narrative`, `vfx`, `ui` (no domain stage table uses them;
  `side_task_domains` maps them to `design`, `technical_art`, `gameplay`), plus the generic `mid`, `senior`, `architect`. An agent is discipline identity (prompt,
  scope), not a model: the bundled files carry no `model`/`effort`. The model and effort of each stage come from the
  route's `[roles]` profile and `[heuristic]`, and an agent without a `[roles]` entry runs on the profile of the
  route's role for that stage.
- Domains (`[routing.domain.<name>]`, each with all four stages; reviewer differs from author and none reviews with
  `director`, which `hard` routes and `review_extra_domains` add on top): `gameplay` (gameplay > engine, QA reviews),
  `engine` (engine > architect), `tools` (tools > architect, engine reviews), `technical_art` (technical_artist > engine,
  QA reviews), `audio` (audio > engine, QA reviews), `design` (designer > gameplay, QA reviews), `build` (build_release >
  engine, tools reviews). `technical_art` and `audio` also get the director review.
- The Producer prompt gets `{domain_guide}`: one line per configured domain with the scope of its implement agent, so
  removing a domain removes its line. Removing one means dropping `routing.domains`, `[routing.domain.X]`,
  `review_extra_domains`, `side_task_domains` values and `when.domain` rules; `teamcfg` rejects leftovers.
- Heuristic: ladder low/mid/high/top/apex (evidence and retuning: `docs/MODEL_LADDER.md`; apex is escalation-only) and rules `hard-route` (route hard: tier `high`,
  effort `high`), `high-risk` (risk high, size medium/large, route complex/hard: tier `high`) and `repeat-failures`
  (2+ rejected plans or implementations: tier `high`). Side tasks (`custom` routes) match none, so `team new --role
  gameplay` implements on `mid`.
- Side tasks: `side_task_roles` and `side_task_domains` name agents (an agent file or a `[roles]` key), and domain
  values must be in `routing.domains`.
- Locks: `editor`, `gpu` (free-memory probe, skipped while the task holds `editor`) and `build`, leased by the agent
  while in use (`team lock`). `locks.default` entries must be in `names`.
- Task skills: 41 grouped by workflow across design, programming, art, audio, production and quality (`INDEX.md`;
  `optimization` baselines with `perf-capture`, touches only the requested hot path, records before and after and drops
  changes without a gain). Each has `## When to use` (with a `Not for:` boundary), `## Inputs`, `## Method`,
  `## Checks`, `## Pitfalls`, `## Engine notes`, under 60 lines and 450 words.
- VCS: `p4` with the Perforce deny lists; this branch does not keep the generic `code`-only preset.

## Tests

```bash
python3 -I -m unittest discover agent-team/tests
./scripts/test-setup-agent-team.sh
```

On Windows (CI): `./scripts/test-setup-agent-team.ps1` runs setup, the installed `team.cmd`, a task run against
fake `.cmd` agents that exit 99, and the `git.cmd` guard.

The smoke test builds a temp git project with `HOME`, `GIT_CONFIG_GLOBAL` and the XDG directories redirected,
empty probes and fake `claude`/`codex` that exit 99, then checks config loading, task creation, status, the guard,
the adapters, the shared journal and `review_page` escaping. `test_gamedev.py` covers the game-dev defaults (agents, skills, domains,
locks, rules, the preset x VCS matrix); tests build their config with `tests/cfgutil.py` (the template as setup writes it). No network and no real agents. `test_bash_guard.py`
covers the kill hook and `test_focus_tui.py` renders the focus pane from fixture state.

See the [UX review](AGENT_TEAM_UX_REVIEW.md) for known stalls and the follow-up queue.

## Porting a project

Copy `agent-team/templates/team.toml` (or the example; it already holds the game-dev defaults), set `[vcs]`, roles and locks, put project rules in
`<templates_dir>/roles/common.md` and per-agent files in `<templates_dir>/agents/`, and run `team-up`. The original project's roles
are in `examples/unreal-p4/roles/`.
