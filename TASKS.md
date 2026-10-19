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

## Next phase: Enforced repository governance

- [ ] Configure a default-branch ruleset after CI check names exist remotely.
- [ ] Require pull requests, successful validation, and conversation resolution.
- [ ] Require an independent approval when repository ownership permits it.

## Completion rule

Move current-phase tasks to completed only after their acceptance criteria and
required validation pass. Keep external GitHub settings pending until verified
through the live repository.
