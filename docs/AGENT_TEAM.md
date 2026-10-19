# Agent team

A project-agnostic coordinator that runs Claude Code and Codex CLI agents as a small team: a Producer routes a
task, then plan / implement / review stages run one agent at a time per task, with hand-offs as Markdown (`.md`) files. HTML pages are only for user reviews and blockers, never agent-to-agent handoffs. Extracted
from a larger game project; everything project-specific lives in one `team.toml` plus optional templates.

Requirements: Linux or Windows, Python 3.11 or newer (`tomllib`), `claude` and/or `codex` on `PATH`, `git` (or `p4`,
or another adapter). The dashboard uses Zellij on Linux and Windows Terminal on Windows. Locks use `fcntl` on Linux and `msvcrt` on Windows. The unit tests
use Linux fakes, so `scripts/validate.sh` runs them on Linux only; Windows CI runs `scripts/test-setup-agent-team.ps1`.
The dashboard's alerts pane (`notifier`) opens the HTML review page whenever a task needs the user or finishes, and
notifies through `notify-send` (Linux, `notify`) or a tray balloon (Windows). Nothing here is installed by
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
- `both`: Claude produces, plans `complex` work and reviews; Codex implements `simple`/`complex` work, plans `hard`
  work and does the extra `hard` review, so each CLI reviews the other's output.

Then which version control the project uses:

- `git`: the built-in adapter; tasks share the working tree and the guard refuses commits, staging and history edits.
- `p4`: the Perforce adapter; each task gets a changelist, the guard refuses submit/revert/shelve/sync and the like,
  and git is denied entirely (the `[vcs]` block of `examples/unreal-p4/team.toml`).

Pass `--agents claude|codex|both` and `--vcs git|p4` (`-Agents`, `-Vcs`) to skip the questions; without a terminal
setup picks what is on `PATH` (both, else codex, else claude) and detects the VCS (git for a git repository, else
p4 when installed, else git). Usage balancing (`[routing.usage]`) stays off in every preset. For a git project that
is already a repository, setup also adds the state directory (`.agent-team/`) to `.git/info/exclude`; otherwise add
it to the project's ignore list (or `P4IGNORE` file) yourself. The git adapter leaves the state directory out of `opened` and `diff` either
way. Then, from the project:

```bash
team new "add a stamina bar"      # create a change, route, run the pipeline
team new --no-run "later"         # create only; start with `team run <id>`
team status [id]                  # `-r` newest first
team approve <id> ["note"]        # pass a gate or retry after escalation/failure
team redo <id> "feedback"         # send back to the implementer (or Producer)
team drop <id> ["note"]
team review [id ...]              # build and open the HTML review page (default: the latest done tasks)
team-up                           # dashboard: usage, focus, live log, tasks, alerts, coordinator chat
team-up "request"                 # same as team new
./team.sh                         # install missing dependencies and open the dashboard
.\team.ps1                        # the same on Windows
```

`team.sh` works from any directory and selects Linux Git before user wrappers.
On Fedora (`dnf`) or Debian/Ubuntu (`apt-get`), it installs missing Python, Git,
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

`team` finds the config through `--config <path>` (before the subcommand), else `$TEAM_CONFIG`, else the nearest `team.toml` above the current directory. `teamcfg.load` rejects unknown role names anywhere in `[routing]`.

## Layout

| Path | Purpose |
| --- | --- |
| `agent-team/team.py` | orchestrator (pipeline, role selection, locks, task state) |
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
| `agent-team/templates/` | `team.toml`, `team.sh`, `team.ps1`, `team.kdl`, `jobs/`, `roles/`, `vcs/` prompt templates |
| `examples/unreal-p4/` | the original Unreal + Perforce config and role files (examples only) |
| `agent-team/tests/` | unit and smoke tests |

## Config (`team.toml`)

`templates/team.toml` is a commented starting point; `examples/unreal-p4/team.toml` shows a large setup.

- `[project]`: `name`, `root` (relative to the file), `state_dir`, `docs` (told to the Producer), `queue_file`,
  `planning_file`, optional `templates_dir` (overrides `jobs/`, `roles/`, `vcs/` files by relative path).
- `[vcs]`: `kind` (`git` or any `X` with `agent-team/vcs_X.py`), `guard_names`, `deny` (tool -> denied
  subcommands, `"*"` = whole tool), `deny_flags` (tool -> subcommand -> refused flags).
- `[agents].deny_extra`: extra Claude `Bash(...)` deny rules. Rules from `[vcs.deny]` are added automatically.
- `[locks]`: `names`, `default`; `[locks.<name>]` may set `min_free_mib`, `probe_cmd` (prints free MiB first) and
  `skip_if_holds`; the check is skipped when the probe binary is missing. Different locks run in parallel, the
  same lock is exclusive, `max_parallel` caps concurrent runs.
- `[probes]`: `name = url`, reported to agents as `name up|down`. Empty by default.
- `[roles.<key>]`: `name`, `cli` (`claude`|`codex`), `model`, `effort`. `producer`, `mid`, `senior`, `architect`,
  `director` are required; others are free.
- `[routing]`: `pipeline.simple|complex|hard` (stage kind + role lists), `domains`, `review_extra_domains`,
  `extra_review_routes`, `extra_review_role`, `domain_roles`, `side_task_*`, `takeover.<role>`,
  `after_impl_fails`, `capacity_fallback`, `max_rounds`, `max_parallel`.
- `[routing.usage]`: optional Claude/Codex plan balancing (`enabled = false` by default): `claude_fallback`,
  `limits`, `scoped_limit`, `surplus_swap`, `burst_swap`, `burst_file`, `cheap_first`, `no_burst_effort`,
  `escalation_gate`. Needs both CLIs and `usage_tui` data.
- `[prompts]`, `[notify]`, `[usage]`: read-only stage note, notification app name and sound dir, and
  `claude_endpoint`.

Prompt templates use `{project}`, `{change_noun}`, `{domains}`, `{docs}` and `{state_dir}`.

## VCS adapters

A change is a string id. Interface: `new_change(desc, hint)`, `set_description(change, desc)`,
`opened(change)`, `opened_files(change)`, `diff(change)`, `others_opened(change)`,
`prepare_edit(path, change) -> (ok, msg)`, `add(path, change)`, `pending_changes()`, `changed_files(change)`.
Adapters never submit, commit, stage, revert or shelve.

- git: change id = task id, the description lives in task state only, all tasks share the working tree,
  `opened` = `git status --porcelain -uall`, `diff` = `git diff HEAD` plus `git diff --no-index` for untracked
  files, nothing is staged. Run one writing task at a time, or give parallel tasks separate worktrees.
- p4: a numbered pending changelist per task; the hook opens files with `p4 edit -c` and moves default-changelist
  strays into the task changelist.

`bin/vcs-guard` is symlinked by `team.py` under each `guard_names` entry in `<state_dir>/guard-bin/` (on Windows:
`<name>.cmd` and a Git Bash `<name>` shim that set `TEAM_GUARD_TOOL`), which is put first on the agents' `PATH` (`TEAM_REAL_<TOOL>` holds the real binary; without it the guard takes the first
non-guard match on `PATH`). It refuses `[vcs.deny]` subcommands and `[vcs.deny_flags]` flags for both Claude and
Codex agents, including when reached through a git alias (`-c alias.x=...` or configured), and refuses git shell
aliases (`!...`). The guard is a guardrail against accidental commits, not a security boundary: an agent can still
run the real binary by absolute path. The hard limit for Codex writers is its `workspace-write` sandbox, which keeps
`.git` read-only (network access follows `[sandbox_workspace_write]` in the Codex config, off by default); Claude agents get the same subcommands as `Bash(...)` deny rules.
Codex runs with `--skip-git-repo-check`, so Perforce and other non-git workspaces work.

Agents may kill only a PID they started and recorded: killing by name once took down the user's dashboard.
`guard-bin/` holds refusing `pkill` and `killall` shims (POSIX), `hooks/bash_guard.py` denies Claude Bash commands
that kill by name or pattern (`pgrep ... | xargs kill`, `kill $(pidof x)`, `taskkill /IM`, `Stop-Process -Name`) or
signal PID <= 0 or a process group, and `codex-home/rules/default.rules` forbids the simple forms for Codex.

The focus pane shows the planning focus, running tasks (stage, planned and actual role, model and effort, round,
elapsed time, the agent's last line), lock holders, what needs you (gates, blocked, escalated, failed and corrupt
tasks, tasks marked running whose process is gone, user-owned planning items, pending changes), the queue with why
each task waits, and today's finished tasks. A task counts as running only while a team process holds its
`.lock-run`.

## State and runtime inputs

Per project, under `state_dir`: `live.log`, `tNNN/` task folders (`state.json`, `.lock-run` held while it runs, hand-offs, `logs/`, `opened.txt`,
`changes.diff`, `user_opened.txt`, `packet/`), `.lock-*`, `guard-bin/`, `team.kdl`, `review/`. Optional inputs you
create by hand: `queue.txt` (`tNNN: title` lines), `decisions.md` (shown by `review_page`), `role_override.json`
(`{"t012": {"review": "director", "implement": "senior", "after_failed_reviews": 1}}`) and the `burst_file`
(epoch deadline).

Per Codex account, shared by every project using the same `$CODEX_HOME`:
`${XDG_STATE_HOME:-~/.local/state}/agent-team/codex/<sha1(realpath $CODEX_HOME)[:12]>/` holds `usage_hist.jsonl`,
`route_mode.json`, `codex_resets.json` (cache), `codex_resets.txt` (manual count, optional),
`codex_push.json` (optional `{"target": 95, "until": "<ISO time with zone>"}`) and `codex_reset_log.json`. Claude
rate limits dumped by `statusline_hook` go to `${XDG_CACHE_HOME:-~/.cache}/agent-team/claude/<key>/`. To use the
dump, set it as Claude Code's `statusLine` command.

## Credentials and network

- Agents run `claude -p` and `codex exec` with the user's own logins; the team never reads or copies them.
- Claude runs with `--permission-mode auto`; read-only stages are limited to `Read,Glob,Grep`. Codex runs with
  `-s read-only` for read-only stages and `-s workspace-write` for implementers, whatever `$CODEX_HOME/config.toml`
  sets.
- `usage_tui` reads `$CODEX_HOME/sessions/**/*.jsonl` (only `rate_limits` lines), `$CLAUDE_CONFIG_DIR/projects/**/*.jsonl`
  (token counts) and spawns `codex app-server` for reset credits. It never reads `auth.json`.
- Only with `[usage] claude_endpoint = true` does `usage_tui` read `$CLAUDE_CONFIG_DIR/.credentials.json` and
  call Claude's usage endpoint with that token. Off by default.
- `codex_reset_consume.py --yes` is opt-in, spends a Codex reset credit and is never called automatically.
- `[probes]` URLs are the only other network access (1 s HTTP GET).

## Tests

```bash
python3 -I -m unittest discover agent-team/tests
./scripts/test-setup-agent-team.sh
```

On Windows (CI): `./scripts/test-setup-agent-team.ps1` runs setup, the installed `team.cmd`, a task run against
fake `.cmd` agents that exit 99, and the `git.cmd` guard.

The smoke test builds a temp git project with `HOME`, `GIT_CONFIG_GLOBAL` and the XDG directories redirected,
empty probes and fake `claude`/`codex` that exit 99, then checks config loading, task creation, status, the guard,
the adapters, the shared journal and `review_page` escaping. No network and no real agents. `test_bash_guard.py`
covers the kill hook and `test_focus_tui.py` renders the focus pane from fixture state.

## Porting a project

Copy `agent-team/templates/team.toml` (or the example), set `[vcs]`, roles and locks, put project rules in
`<templates_dir>/roles/common.md` and per-role files next to it, and run `team-up`. The original project's roles
are in `examples/unreal-p4/roles/`.
