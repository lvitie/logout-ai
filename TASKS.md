# Logout AI tasks

## Current phase: Project bootstrapping

- [x] Add additive Bash and PowerShell project setup scripts.
- [x] Preserve existing project documents and partial skill contents.
- [x] Support dry runs and explicit stack-skill selection.
- [x] Add the project-bootstrap requirements and skill-selection workflow.
- [x] Run repository, Bash, configuration, and skill validation.
- [ ] Run the PowerShell setup integration test on Windows.
- [x] Inspect the final diff for only project-bootstrapping changes.

## Agent team extraction

- [x] Copy and abstract the agent team into `agent-team/` (config, VCS adapters, templates, launcher).
- [x] Add `scripts/setup-agent-team.sh` with `--dry-run` and its integration test.
- [x] Add unit and smoke tests and wire them into `validate.sh`.
- [ ] Run a real Claude/Codex task end to end in a scratch git project (needs the user's logins).
- [x] Ask for claude, codex or both during setup; harden the git guard; pin the Codex writer sandbox.
- [x] Review and commit.
- [x] Generate an additive `team.sh` launcher with missing-dependency installation
  and select the configured CLI for coordinator chat. Verified with 44 unit
  tests, setup integration, repository validation and independent review;
  actual x86_64 Zellij 0.45.1 download, SHA-256 and version check passed.
  Interactive dashboard and real agent tasks remain outside these checks.
- [x] Make the coordinator Windows compatible: portable locks and process
  cleanup, Python `team-up` and `chat`, Windows guard shims, `setup-agent-team.ps1`
  and a `team.ps1` launcher (winget, pinned Zellij 0.45.1 Windows zip). Verified on
  Linux with 46 unit tests (one pre-existing launcher test needs node/npm on PATH),
  setup integration, full validation with ShellCheck and pwsh parsing, a real Zellij
  session from the new layout, and the PowerShell setup run under pwsh on Linux.
- [x] Run `scripts/test-setup-agent-team.ps1` and `team.ps1` on a real Windows
  machine. Use native Windows Terminal consoles instead of native Zellij;
  visually verify resizing and alerts above tasks and the coordinator on the
  right. Local validation passed: 61 Python tests, Linux and native Windows
  setup integration, and `scripts/validate.sh` (25 skills).
- [ ] Verify the Windows setup integration test on Windows CI.
- [x] Ask for git or p4 during setup (`--vcs`/`-Vcs`, detected without a terminal).
- [x] Port the Inferno fixes: no killing by name (PATH shims, Claude Bash hook,
  Codex rules), `--skip-git-repo-check` for Codex, `team status` skipping folders
  without state, p4 `-b/-L/-v` options and the `integ` synonym, and the richer focus
  pane (run-lock based, so it works on Windows too).
- [x] Queue busy runs instead of refusing them, start queued tasks from the alerts
  pane (`team queue`, queue-file order and `after tNNN`), and let the coordinator
  wait for attention events with `team wait` instead of polling.
- [x] Let the coordinator edit team config and docs, and add the `team-setup`
  skill: an interactive interview (Claude and Codex) that proposes
  project-specific agents and writes them after confirmation.
- [ ] Run `team-setup` interactively from a real Claude and Codex coordinator.
- [x] Fix the agent-team review findings: atomic guard-bin, race-free task ids,
  capacity detection from CLI errors only with cycle-safe fallback, retrying the
  implementation after an escalated review, process-group reaping and signal
  cleanup, p4 edits on writable files and Codex writers (network, tracked edits),
  Windows usage probe, queue deps and held/slow alerts, punctuation-tolerant
  verdicts, run-lock patience, and review page sanitizing.
- [x] Refill the queue: when it runs low the Producer proposes tasks from the plan
  (`team refill`), which the user promotes or rejects. Run the Codex coordinator
  unsandboxed so `team` works under default Codex configs (WSL report).
- [x] Offer `team-setup` on the coordinator's first message until
  `[project] team_setup` records that it ran.

## Next phase: Enforced repository governance

- [ ] Configure a default-branch ruleset after CI check names exist remotely.
- [ ] Require pull requests, successful validation, and conversation resolution.
- [ ] Require an independent approval when repository ownership permits it.

## Completion rule

Move current-phase tasks to completed only after their acceptance criteria and
required validation pass. Keep external GitHub settings pending until verified
through the live repository.
