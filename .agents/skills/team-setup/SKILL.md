---
name: team-setup
description: Tailor the Logout AI agent team to a project. Start from the bundled game-development defaults (discipline agents, game domains, task skills, heuristic rules, p4/Unreal VCS and editor/GPU/build locks), confirm and tailor them with the user (models, domains, locks, probes, shared rules) and write team.toml and prompt files only after the user confirms. Use when asked to set up, configure, tailor, or reconfigure the agent team, add, change, or remove team agents, domains or roles, or when team.toml still holds the untouched setup preset. Not for running tasks (team new) or installing the team into a project (scripts/setup-agent-team.sh).
---

# Team Setup

Works the same from the Claude Code and Codex coordinator chats. The output is
an edited `team.toml` plus prompt files under its `templates_dir`; nothing is
written before the user confirms the proposal.

This branch is the game-dev variant. The setup preset already ships a complete
team, so the interview confirms and tailors it, it does not design one from
scratch:

- Agents (discipline identity, no model): `producer`, `designer`, `gameplay`,
  `engine`, `tools`, `technical_artist`, `audio`, `qa`, `build_release`,
  `director`, the side-task agents `narrative`, `vfx`, `ui` (no domain stage
  table uses them; offer them as stage owners of a domain, for example a new
  `ui` domain, if the user wants), plus the generic `mid`, `senior`, `architect`.
- Domains with full stage tables: `gameplay`, `engine`, `tools`, `technical_art`,
  `audio`, `design`, `build`. Model and effort come from the route's `[roles]`
  profile and `[heuristic]` (tiers low/mid/high/top/apex, rules `hard-route`, `high-risk`,
  `repeat-failures`), not from the agent.
- Task skills: 41 game-dev skills covering AAA studio roles, listed with their
  roles and agents in `agent-team/templates/skills/INDEX.md` (research:
  `docs/GAME_DEV_ROLES.md`).
- VCS `p4` (Unreal/Perforce) and locks `editor` (default), `gpu`, `build`.

## Inputs

- The project's `team.toml`: `$TEAM_CONFIG`, else the nearest one above the
  working directory. If there is none, stop and tell the user to run
  `scripts/setup-agent-team.sh` (`setup-agent-team.ps1` on Windows) from the
  Logout AI checkout first.
- The agent team source: `$LOGOUT_AI_ROOT/agent-team`, else the `agent-team/`
  directory next to the `.agents/` folder that holds this skill. Read
  `templates/team.toml` (every key, commented), `templates/agents/*.md`, `templates/skills/*.md`,
  `templates/roles/common.md`, `templates/jobs/route.md`, `write_config.py`
  (model presets), and the Config section of `docs/AGENT_TEAM.md`.

## Workflow

1. Inspect before asking. Do not look for a VCS (no `git status`, no
   `.git` probe); the user answers that. Read the current `team.toml`, any files already in
   its `templates_dir`, the project docs it lists, the README, and the repository
   layout and build, test, and lint commands. Note which CLIs are on `PATH`
   (`claude`, `codex`). Never ask for something you can read.
2. Interview the user in rounds of at most four grouped questions. Wait for
   the answers before the next round, and never answer for the user.
   - In Claude Code, use the AskUserQuestion tool. Offer concrete options and
     put the recommended one first.
   - In Codex, use `request_user_input` when it is available. Otherwise send
     one message with numbered questions and suggested defaults, then end the
     turn and wait for the reply.

   Present the defaults above as the proposal and ask only what step 1 left open or
   what the user may want to change:
   - **Workspace:** in the first round, show the project root read in step 1
     (`[project].root`) and have the user confirm it; a wrong workspace
     invalidates every later answer.
   - **Version control:** always ask in the first round: `git`, `p4`
     (Perforce) or `none`. Never infer it from `.git`, `.p4config`, the
     existing `[vcs].kind` or any other file (a p4 project can also contain
     `.git`), and never skip the question; show the current `[vcs].kind` only
     as the suggested default.
   - **Work:** what the game is (engine, platforms, team size) and which of the
     seven default domains to keep. Offer to add a domain (for example `ui` or
     `live_ops`) with its own stage table. Removing a domain means dropping every
     reference or the config no longer loads: its name in `routing.domains`, its
     `[routing.domain.X]` table, its entry in `review_extra_domains`, any
     `[routing.side_task_domains]` value pointing at it, and any
     `[[heuristic.rule]]` with `when.domain = X`. Remove the disciplines that no
     remaining domain, side task or reviewer uses only if the user wants.
   - **Specialists:** areas that need a dedicated agent, not covered by the bundled disciplines, such as localization,
     live ops, or cinematics. Ask whether each one should own stages of a
     domain (`[routing.domain.<name>]`) or take side tasks (`side_task_roles`,
     used by `team new --role`).
   - **Domain stages:** show the shipped `[routing.domain.<name>]` tables of
     the kept domains as the proposal and ask only for changes. A new domain
     needs its own table: the plan reviewer must differ from the planner and the
     reviewer from the implementer. `domain_roles` is deprecated.
   - **Task skills:** recurring instructions that apply to some tasks only
     (for example a test-first routine, a performance capture, an engine review
     checklist), not to a whole domain. Ask which the project wants.
   - **Agents and budget:** `claude`, `codex`, or both, and cost versus
     quality. This sets `cli`, `model`, and `effort` per role. Use only model ids
     that are already in `team.toml` or the `write_config.py` presets, unless
     the user names others.
   - **Shared resources:** the defaults are `editor` (every task holds it, so tasks
     run one at a time), `gpu` (GPU captures or renders; free-memory check skipped
     while `editor` is held) and `build` (standalone compiles, cooks, packaging).
     Tasks pick others with `team new --res gpu|build|none` (`none` = read-only or
     tool-only work); ask which areas may run in parallel and what else must not
     be shared (`[locks]`), how many tasks may
     run together (`max_parallel`), and local services the agents depend on
     (`[probes]`, name = URL).
   - **Rules:** build, test, and lint commands, areas agents must not touch,
     standing approvals (what agents may decide without a gate), and decisions
     that always need the user. These go into `roles/common.md`.
   - **Plan:** only when the planning file (`[project].planning_file`) has no
     unchecked items under "## Current phase" or ROADMAP.md is missing or empty:
     the project goal, the first milestone, and 3-8 first work items. Draft
     them from the README and the answers above; ask only what those leave open.
     Also say that with the default `editor` lock tasks run one at a time,
     and ask which areas can run in parallel (`--res`, narrower `default`).
   - **Queue autonomy:** which Producer refill proposals the coordinator may
     queue without asking. Default: those without a `(needs user: ...)`
     suffix (current-phase work); alternatives: every proposal, or none.
   - **Review cadence:** when finished (done) tasks open a review page for
     the user: `task` (each one, recommended), `milestone` (when the current
     phase is done), `daily` (once a day) or `custom` (ask for a free-text
     rule, for example "every 3 done tasks"). Gates, blocked, escalated and
     failed tasks always open at once. Written as `[notify] review_cadence`
     (and `review_cadence_rule` for `custom`) in `team.toml`.
   - **Review:** which domains or routes get an extra review
     (`review_extra_domains`, `extra_review_routes`, `extra_review_role`), and
     how many minor failed review rounds to allow before escalating to the user (`max_rounds`); major/critical
     failures step the tier ladder instead.
3. Propose everything in one message:
   - A roles table with key, name, CLI, model, effort, and what the role owns.
   - Each domain with a one-line meaning and its stage agents (the defaults, and
     the changes).
   - Pipeline, takeover, and review changes, and the locks, probes, and
     `max_parallel` settings.
   - The project rules for `common.md`, written out in full.
   - The auto-promote policy for `coordinator-policy.md`, when it differs from
     the default.
   - Every file to create or change. The default `templates_dir` is `team/`.

   Ask the user to confirm or adjust. Revise and ask again until the user says
   yes. If the user declines, change nothing.
4. Write only what was confirmed:
   - Set `[vcs]` from the VCS answer, replacing the whole `[vcs]` span up to
     `[agents]`:
     - `p4` (the template default): keep the block (`kind = "p4"` with the
       `vcs_p4.py` adapter, `guard_names = ["p4", "git"]`, its `[vcs.deny]` and
       `[vcs.deny_flags]`, git denied entirely).
     - `git`: use the `GIT` block of `write_config.py` (`kind = "git"`,
       `guard_names = ["git"]`, the git `[vcs.deny]` and `[vcs.deny_flags]`).
     - `none`: `kind = "none"`, `guard_names = []`, empty `[vcs.deny]` and
       `[vcs.deny_flags]`. No guard, no deny rules, no submit step.
   - Edit `team.toml` in place. Keep the keys and comments you do not change.
     Keep the canonical roles `producer`, `mid`, `senior`, `architect`, and
     `director`. Give new roles lowercase keys. Every role named under
     `[routing]` must exist.
   - `<templates_dir>/agents/<key>.md` for each new or retuned role: frontmatter
     (`name` equal to the file name, `[a-z0-9_]+`; `scope`; optional `model` and
     `effort` pin), then the body: one paragraph, "You are the <name> of the
     {project} agent team: <scope>.", then the expertise, tools, and method
     lines that matter for the role. A plain `roles/<key>.md` still works.
   - `<templates_dir>/roles/common.md`: copy the bundled `common.md`, keep all
     of its rules (they are the team protocol), and append the project rules.
   - `<templates_dir>/coordinator-policy.md`, only when the user chose a
     non-default queue autonomy: an `## Auto-promote policy` section stating
     which refill proposals the coordinator queues without asking. Only the
     coordinator reads this file; `roles/common.md` reaches every agent, so the
     policy does not go there.
   - `<templates_dir>/agents/producer.md` only if the user wants a different
     Producer prompt: keep the `{domain_guide}` placeholder, which the team fills with
     one line per configured domain (the scope of its implement agent), so the
     Producer can route. Do not write per-domain lines by hand.
   - `<templates_dir>/skills/<name>.md` for each confirmed task skill
     (`[a-z0-9_-]+`; first line a `# title`, then terse bullets). The bundled
     skills (see above) work without a copy; a file of
     the same name in `skills/` overrides them. They are task skills: users
     attach them with `team new --skill name[@stage]` and the Producer may
     suggest them; never put them in an agent file.
   - Use the placeholders `{project}`, `{change_noun}`, `{state_dir}`, `{docs}`,
     and `{domains}` instead of hard-coding those values.
   - Do not override `jobs/` or `vcs/` unless the user asked for it. The
     STATUS, VERDICT, ROUTE, DOMAIN, TITLE, and SKILLS lines are parsed by the team.
   - Plan seed, only when the Plan question was asked and confirmed: write
     ROADMAP.md (goal, milestones as outcomes) and the planning file's
     "## Current phase" with the first items as unchecked `- [ ]` lines, each
     self-contained (what to build, how to check it). Keep existing content;
     add, do not rewrite. This is the whole planning stage: the Producer's refill
     turns these items into queue lines, so no separate planning agent is used.
   - Set `[project] team_setup = "<today, YYYY-MM-DD>"` in `team.toml` (add the
     key when it is missing). It tells the coordinator that setup has run, so
     it stops offering it.
5. Validate:
   - Run `team status`. It loads `team.toml` and rejects unknown role names in
     `[routing]`; fix any error it reports.
   - Check that every configured CLI is on `PATH`.
   - Check that no file contains leftover template text.
   - Show the user the result: for `git`, `git diff` for tracked files and the
     file list and contents for new ones; for `p4` and `none`, only the file
     list and contents. Do not run any git command or check unless the answer
     was `git`.
6. Tell the user when the changes take effect. Each new task run reads
   `team.toml`. Restart `team-up` so the dashboard panes and the coordinator
   (when the Producer changed) pick them up. Then end setup watching events:
   - After the Plan seed, run `team refill` once (background) so the first
     proposals appear without waiting for the next queue pass.
   - Start `team wait` in the background. Where background jobs do not wake
     the chat, run `team wait --no-block` at the start and end of each turn.
   - Tell the user to keep `team-up` (its alerts pane) running; it starts
     queued tasks.
   - When `team wait` reports a blocked or escalated task, read its hand-offs
     unprompted and tell the user what it needs.

## Boundaries

- Change only `team.toml`, files under its `templates_dir`, and (Plan seed
  only) ROADMAP.md and the planning file. Never edit the
  agent team source, the CLIs' own configuration, or credentials.
- Never start tasks during setup. Validation must not use `team new`.
- Keep `state_dir` out of version control when the project has one (the
  chosen VCS only; for `none` there is nothing to do). Commit or submit only
  when the user asks.
- Only the chosen VCS applies: for `p4` and `none` skip git guard names, git
  deny rules, `git diff` and git change tracking.
