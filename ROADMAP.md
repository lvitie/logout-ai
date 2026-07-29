# Logout AI roadmap

This roadmap orders the outcomes required by [SPEC.md](SPEC.md). Detailed work
for the active phase belongs in [TASKS.md](TASKS.md).

## Status and completion rules

- **Planned:** Scope is documented but implementation has not started.
- **In progress:** Work is active and incomplete.
- **Blocked:** A named dependency prevents progress.
- **Complete:** Exit criteria and required validation have passed.

A phase moves to **Complete** only after its validation evidence is recorded in
`TASKS.md` or the associated pull request. New requirements belong in
`SPEC.md` before roadmap or task work is added.

## Phase 1: Portable Codex foundation

**Status:** Complete

### Outcome

Portable global instructions, configuration, rules, local-model profiles, and
skills install without replacing private Codex runtime state.

### Specification coverage

`REQ-INSTALL-01` through `REQ-INSTALL-06`, `REQ-VALIDATE-01`, `AC-01`, and
`AC-02`.

### Included work

- Add user-scoped Linux, macOS, and Windows installers.
- Link managed portable files and render machine-specific trust entries.
- Add dry-run behavior, timestamped backups, and idempotent link handling.
- Reject private runtime state and malformed portable configuration.

### Dependencies and risks

- Symbolic-link behavior varies by platform and host permissions.
- Generated trust entries must use exact project paths rather than globs.
- Backup and replacement logic can destroy state if target ownership is
  resolved incorrectly.

### Exit criteria

- Managed portable files install into isolated target directories.
- Dry runs make no changes.
- Existing managed targets are backed up before replacement.
- Repeated installation preserves already-correct links.
- Private Codex runtime state remains unmanaged.

### Validation

- **Automated:** Run `./scripts/validate.sh` and the platform installer
  integration tests.
- **Manual:** Review a dry-run plan and a replaced-target backup on a supported
  host when installer behavior changes materially.

## Phase 2: Workflow alignment

**Status:** Complete

### Outcome

The repository and reusable skills encode a consistent planning,
implementation, review, manual-testing, and merge workflow.

### Specification coverage

`REQ-PLUGIN-01`, `REQ-PLUGIN-02`, `REQ-WORKFLOW-01`,
`REQ-VALIDATE-01`, `REQ-VALIDATE-02`, and `AC-03` through `AC-07`.

### Included work

- Add repository planning documents and reusable project templates.
- Separate project planning from pull-request readiness.
- Add cross-platform installer integration tests and pull-request CI.
- Add Dependabot coverage, dependency review, and pull-request evidence
  prompts.
- Align Claude routing and workflow documentation.
- Add explicit, cross-platform installation for selected Codex plugins.
- Render exact trust entries for every Git worktree beneath the configured
  project directory.

### Dependencies and risks

- Windows symbolic-link behavior can differ by permissions and host policy.
- Plugin tests must not contact a live marketplace.
- Workflow documentation can drift from the actual validation and review gates.

### Exit criteria

- Planning, implementation, review, and merge responsibilities have distinct
  documented workflows.
- Plugin installation is opt-in and its dry run is side-effect free.
- Linux and macOS installer tests pass locally.
- Windows installer tests pass in CI.
- Pull requests run validation and applicable dependency review.

### Validation

- **Automated:** Run `./scripts/validate.sh` locally and the complete CI matrix
  on a pull request.
- **Manual:** Compare `AGENTS.md`, `docs/WORKFLOW.md`, and the reusable planning
  assets for conflicting instructions.

## Phase 3: Luca's portable baseline

**Status:** Complete

### Outcome

The repository reflects Luca's identity, project layout, and recurring
technical-art, web development, Graphify, and Unreal Engine workflows without
carrying inherited paths or branding.

### Specification coverage

`REQ-INSTALL-02`, `REQ-WORKFLOW-02`, `REQ-WORKFLOW-03`, `AC-02`, and `AC-05`.

### Included work

- Replace inherited user-facing and installer branding with Logout AI.
- Discover trusted Git worktrees beneath `~/Projects`.
- Remove inherited machine-specific trusted-project entries.
- Manage Codex-native Graphify and Unreal MCP skills.
- Manage focused Unreal C++, Unreal materials, Qt C++, Qt Python, and
  host-specific DCC Python skills.
- Manage focused Rust and Go web-server skills plus an HTMX frontend skill.
- Keep installers, documentation, and skill validation cross-platform.

### Dependencies and risks

- Host-specific skills can duplicate shared Qt or Python guidance.
- External tools such as Graphify and the Unreal MCP server are separately
  installed and may be unavailable during local validation.
- Personal paths or inherited branding can leak into portable configuration.

### Exit criteria

- No inherited user names or paths remain in managed configuration or
  documentation.
- Linux installer tests cover nested Git repositories beneath `~/Projects`.
- Every managed skill has valid metadata and a documented external dependency
  where applicable.
- Repository configuration, documentation, scripts, and skills validate.

### Validation

- **Automated:** Run `./scripts/validate.sh` and `./scripts/test-install.sh`.
- **Manual:** Review the skill inventory for overlap, missing host coverage,
  and undocumented external-tool assumptions.

## Phase 4: Enforced repository governance

**Status:** Planned

### Outcome

Hosted repository settings enforce the review, validation, and security gates
documented by the repository.

### Specification coverage

`REQ-GOVERN-01`, `REQ-GOVERN-02`, and `AC-08`.

### Included work

- Require pull requests and successful validation checks.
- Require conversation resolution.
- Require an independent approval when repository ownership makes that
  practical.
- Confirm secret scanning, push protection, Dependabot, and dependency review.

### Dependencies and risks

- Final CI check names must exist on the default branch before a ruleset can
  require them.
- Repository ownership may make independent approval unavailable.
- An incorrect ruleset can block legitimate maintenance or emergency recovery.

### Exit criteria

- The default-branch ruleset requires pull requests, current validation checks,
  and conversation resolution.
- Independent approval is required or its ownership limitation is documented.
- Applicable security controls are enabled.
- The documented merge gate matches the hosted repository settings.

### Validation

- **Automated:** Query hosted repository settings and required check names when
  an authenticated repository API is available.
- **Manual:** Inspect the effective default-branch ruleset and security settings,
  then record evidence in `TASKS.md` or the associated pull request.
- **Rollback:** Preserve the previous ruleset configuration and restore it if
  required checks prevent normal repository recovery.
