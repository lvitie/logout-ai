# Logout AI specification

## Purpose

Logout AI is the source of truth for Luca's portable Codex configuration,
reusable skills, and durable coding-agent instructions. It provides a safe,
repeatable baseline without treating private Codex runtime state as portable
configuration.

## Problem

Codex installations mix portable configuration with credentials, sessions,
caches, and other machine-local state. Coding agents also need consistent
instructions and reusable workflows without replacing project-specific
requirements.

## Goals

- Install the same reviewed Codex baseline on Linux, macOS, and Windows.
- Keep portable configuration separate from credentials and machine-local
  runtime state.
- Make installation previewable, recoverable, and safe to repeat.
- Provide focused workflows for recurring development, technical-art,
  publishing, and infrastructure work.
- Seed new or existing projects with additive project-local instructions,
  planning documents, and stack-specific skills.
- Keep repository and installer behavior verifiable locally and in CI.

## Users and environments

The primary user is Luca, a technical artist and developer who works primarily
on Linux. The baseline supports work across Unreal Engine, DCC Python
automation, Qt, Python AI, Rust, Go, HTMX, publishing, Graphify, and self-hosted
infrastructure.

macOS and Windows are supported installation targets for the same portable
baseline. Project-specific repositories remain responsible for their own
requirements and instructions.

## Requirements

### Portable installation

- **REQ-INSTALL-01:** Install global Codex instructions, configuration, rules,
  local-model profiles, and reusable skills from this repository.
- **REQ-INSTALL-02:** Trust the current user's `~/Projects` directory and each
  Git worktree discovered recursively beneath it.
- **REQ-INSTALL-03:** Support a dry run that reports intended actions without
  changing the target system.
- **REQ-INSTALL-04:** Preserve replaced managed targets in timestamped backups.
- **REQ-INSTALL-05:** Support repeated installation without replacing
  already-correct links.
- **REQ-INSTALL-06:** Leave credentials, sessions, history, caches, plugin
  state, and runtime databases untouched except for plugin installation
  explicitly requested under `REQ-PLUGIN-01`.

### Optional plugin installation

- **REQ-PLUGIN-01:** Install only the explicit plugin selectors recorded in
  `codex-plugins.txt`, and only when the user opts in.
- **REQ-PLUGIN-02:** A plugin dry run must not invoke Codex or mutate plugin
  state.

### Reusable workflows

- **REQ-WORKFLOW-01:** Provide project-planning templates and keep planning
  separate from pull-request readiness. Local review uses the built-in
  `codex review --uncommitted` loop, with validation and review repeated after
  each actionable fix.
- **REQ-WORKFLOW-02:** Provide focused skills for the recurring domains listed
  under [Users and environments](#users-and-environments), including
  Codex-native Graphify and live Unreal Editor workflows.
- **REQ-WORKFLOW-03:** Skills that depend on external applications or services
  must document those dependencies instead of silently installing them.
- **REQ-WORKFLOW-04:** Provide non-destructive Bash and PowerShell project setup
  scripts plus a conversational workflow that selects required skills and
  creates focused project-local skill coverage when none exists.

### Validation and governance

- **REQ-VALIDATE-01:** Validate repository structure, configuration syntax,
  skill metadata, documentation consistency, and installer behavior.
- **REQ-VALIDATE-02:** Run Linux, macOS, and Windows validation for pull
  requests and default-branch pushes.
- **REQ-GOVERN-01:** Protect the default branch with pull requests, required
  validation, and conversation resolution once the hosted repository exposes
  the final check names.
- **REQ-GOVERN-02:** Enable applicable repository security controls and give CI
  workflows only the permissions they require.

## Architecture and ownership

| Path | Responsibility |
| --- | --- |
| `codex-home/` | Portable files installed into `CODEX_HOME` |
| `.agents/skills/` | Reusable workflows installed into `AGENTS_HOME` |
| `scripts/install.sh` | User-scoped Bash installer for Linux and macOS |
| `scripts/install.ps1` | User-scoped PowerShell installer for Windows |
| `scripts/setup-project.*` | Additive project document and skill seeding |
| `codex-plugins.txt` | Plugin selectors used only by explicit plugin installation |
| `scripts/validate.sh` | Repository and platform-appropriate local validation |
| `scripts/test-install.*` | Isolated installer integration tests |
| `AGENTS.md` | Durable repository maintenance instructions |
| `SPEC.md` | Requirements, boundaries, and acceptance criteria |
| `ROADMAP.md` | Ordered outcomes, risks, and phase exit criteria |
| `TASKS.md` | Current reviewable work and validated completion status |

The installers render `config.toml` with machine-specific exact trust entries
and link the other managed files. Credentials, sessions, history, caches,
plugin state, and runtime databases remain outside repository ownership.

## Security and privacy

- Never track authentication files, session history, caches, logs, or runtime
  databases.
- Do not require administrator privileges for normal installation.
- Keep destructive actions narrowly scoped and require explicit authorization.
- Give GitHub Actions the minimum permissions required by each job.
- Pin third-party actions and let Dependabot keep those pins current.

## Compatibility

- The shell installer targets Bash on Linux and macOS.
- The PowerShell installer targets supported Windows environments capable of
  creating symbolic links.
- Optional validation tools must not become installation dependencies unless
  the installer explicitly manages them.

## Non-goals

- Mirroring the complete Codex home directory.
- Managing credentials, authentication, sessions, history, caches, logs, or
  runtime databases.
- Installing plugins without explicit opt-in.
- Replacing project-specific `AGENTS.md` files or product requirements.
- Installing Codex or Claude Code through the baseline installer or project
  seeding. The explicitly invoked agent-team `team.sh` and `team.ps1` launchers
  may install missing configured CLIs and dashboard dependencies.
- Installing third-party review CLIs, local model servers, Graphify, or the
  Unreal MCP server.
- Installing project dependencies or initializing version control as part of
  project seeding.
- Adding security scanners that do not support the repository's languages.

## Acceptance criteria

- **AC-01:** `./scripts/validate.sh` passes from a clean checkout.
- **AC-02:** Linux and macOS installer integration tests verify dry-run safety,
  timestamped backups, preserved machine-local configuration state, correct
  links, exact generated trust entries, and idempotence in isolated temporary
  directories.
- **AC-03:** Windows CI verifies the equivalent PowerShell installer behavior.
- **AC-04:** Installer tests verify plugin opt-in and dry-run behavior without
  contacting a live marketplace.
- **AC-05:** Validation rejects tracked private runtime state, malformed
  portable configuration, invalid skill front matter, and a skill inventory
  that differs from the actual directories.
- **AC-06:** Pull requests and default-branch pushes run the platform validation
  matrix; pull requests also run dependency review.
- **AC-07:** Workflow documentation covers planning, implementation, review,
  manual testing, and merge gates. The pull-request readiness workflow
  requires a clean Codex review loop and does not depend on a third-party
  review service.
- **AC-08:** Hosted repository settings match `REQ-GOVERN-01` and
  `REQ-GOVERN-02`, with any unavailable independent-approval requirement
  documented.
- **AC-09:** Project setup tests on Unix and Windows verify new targets,
  additive merges, existing-file preservation, dry-run safety, selected-skill
  copying, missing-skill errors, and idempotence.

## Open questions

- **OPEN-01:** Should a future installer optionally manage user-wide Claude
  Code instructions in addition to repository-local `CLAUDE.md` routing?
