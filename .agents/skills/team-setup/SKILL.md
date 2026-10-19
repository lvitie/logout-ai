---
name: team-setup
description: Tailor the Logout AI agent team to a project. Interview the user about the project, propose project-specific agents (roles, models, domains, routing, locks, probes, shared rules) and write team.toml and role prompt files only after the user confirms. Use when asked to set up, configure, tailor, or reconfigure the agent team, add, change, or remove team agents or roles, or when team.toml still holds the generic setup preset. Not for running tasks (team new) or installing the team into a project (scripts/setup-agent-team.sh).
---

# Team Setup

Works the same from the Claude Code and Codex coordinator chats. The output is
an edited `team.toml` plus prompt files under its `templates_dir`; nothing is
written before the user confirms the proposal.

## Inputs

- The project's `team.toml`: `$TEAM_CONFIG`, else the nearest one above the
  working directory. If there is none, stop and tell the user to run
  `scripts/setup-agent-team.sh` (`setup-agent-team.ps1` on Windows) from the
  Logout AI checkout first.
- The agent team source: `$LOGOUT_AI_ROOT/agent-team`, else the `agent-team/`
  directory next to the `.agents/` folder that holds this skill. Read
  `templates/team.toml` (every key, commented), `templates/roles/*.md`,
  `templates/jobs/route.md`, `write_config.py` (model presets), and the Config
  section of `docs/AGENT_TEAM.md`.

## Workflow

1. Inspect before asking. Read the current `team.toml`, any files already in
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

   Cover only what step 1 left open:
   - **Work:** what the project is and which kinds of work the team will get.
     These become the `[routing].domains`, for example `code`, `ui`, `docs`,
     `data`, `infra`, `assets`.
   - **Specialists:** areas that need a dedicated agent, such as a frontend,
     database, shader, or docs writer. Ask whether each one should own a domain
     (`domain_roles`: it plans and builds that domain) or take side tasks
     (`side_task_roles`, used by `team new --role`).
   - **Agents and budget:** `claude`, `codex`, or both, and cost versus
     quality. This sets `cli`, `model`, and `effort` per role. Use only model ids
     that are already in `team.toml` or the `write_config.py` presets, unless
     the user names others.
   - **Shared resources:** what two tasks must not use at once, such as a dev
     server, editor, GPU, database, or emulator (`[locks]`), how many tasks may
     run together (`max_parallel`), and local services the agents depend on
     (`[probes]`, name = URL).
   - **Rules:** build, test, and lint commands, areas agents must not touch,
     standing approvals (what agents may decide without a gate), and decisions
     that always need the user. These go into `roles/common.md`.
   - **Review:** which domains or routes get an extra review
     (`review_extra_domains`, `extra_review_routes`, `extra_review_role`), and
     how many failed review rounds to allow before escalating (`max_rounds`).
3. Propose everything in one message:
   - A roles table with key, name, CLI, model, effort, and what the role owns.
   - Each domain with a one-line meaning and its owner.
   - Pipeline, takeover, and review changes, and the locks, probes, and
     `max_parallel` settings.
   - The project rules for `common.md`, written out in full.
   - Every file to create or change. The default `templates_dir` is `team/`.

   Ask the user to confirm or adjust. Revise and ask again until the user says
   yes. If the user declines, change nothing.
4. Write only what was confirmed:
   - Edit `team.toml` in place. Keep the keys and comments you do not change.
     Keep the canonical roles `producer`, `mid`, `senior`, `architect`, and
     `director`. Give new roles lowercase keys. Every role named under
     `[routing]` must exist.
   - `<templates_dir>/roles/<key>.md` for each new or retuned role. Write one
     paragraph, "You are the <name> of the {project} agent team: <scope>.",
     then the expertise, tools, and method lines that matter for the role.
   - `<templates_dir>/roles/common.md`: copy the bundled `common.md`, keep all
     of its rules (they are the team protocol), and append the project rules.
   - `<templates_dir>/roles/producer.md`: the bundled Producer line plus one
     line per domain saying what work belongs to it, so the Producer can route.
   - Use the placeholders `{project}`, `{change_noun}`, `{state_dir}`, `{docs}`,
     and `{domains}` instead of hard-coding those values.
   - Do not override `jobs/` or `vcs/` unless the user asked for it. The
     STATUS, VERDICT, ROUTE, DOMAIN, and TITLE lines are parsed by the team.
5. Validate:
   - Run `team status`. It loads `team.toml` and rejects unknown role names in
     `[routing]`; fix any error it reports.
   - Check that every configured CLI is on `PATH`.
   - Check that no file contains leftover template text.
   - Show the user the result: `git diff` for tracked files, or the file list
     and contents for new ones.
6. Tell the user when the changes take effect. Each new task run reads
   `team.toml`. Restart `team-up` so the dashboard panes and the coordinator
   (when the Producer changed) pick them up.

## Boundaries

- Change only `team.toml` and files under its `templates_dir`. Never edit the
  agent team source, the CLIs' own configuration, or credentials.
- Never start tasks during setup. Validation must not use `team new`.
- Keep `state_dir` out of version control. Commit or submit only when the user
  asks.
