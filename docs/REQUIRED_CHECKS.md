# Required CI checks

Phase 5 prerequisite for the default-branch ruleset. Source:
[`.github/workflows/validate.yml`](../.github/workflows/validate.yml), the only
workflow file. Its workflow name is `Validate`.

Use these check-run names as the required-checks list once CI has run remotely:

| Workflow name | Job id | Job `name:` | Exact check-run name |
| --- | --- | --- | --- |
| `Validate` | `unix` | `Validate (${{ matrix.os }})` | `Validate (ubuntu-latest)` |
| `Validate` | `unix` | `Validate (${{ matrix.os }})` | `Validate (macos-latest)` |
| `Validate` | `windows` | `Validate (windows-latest)` | `Validate (windows-latest)` |
| `Validate` | `dependency-review` | `Dependency review` | `Dependency review` |

The `unix` matrix expands to the two names above; no additional matrix suffix
is appended to its explicit job name. The workflow name is separate from the
check-run name. Step names are not separate required checks.

## Triggers

- `pull_request`: all four checks run. No branch or path filters are configured.
- `push` to `main`: the Ubuntu, macOS, and Windows validation checks run.
  `Dependency review` is skipped because its job condition is
  `github.event_name == 'pull_request'`.
- `workflow_dispatch`: the Ubuntu, macOS, and Windows validation checks run;
  `Dependency review` is skipped by the same condition.

These names are derived from the workflow and are only valid for ruleset
selection once CI has run remotely and GitHub has registered them. Before
configuring the ruleset, confirm the names against remote CI, including a pull
request run for `Dependency review`, after the workflow exists on the default
branch. Remote check registration and hosted settings have not been queried or
changed for this inventory. The Phase 5 ruleset task remains incomplete.

## Review gate

A pull request author cannot approve their own pull request. With a single
owner, requiring approvals would block every merge, so independent approval is
unavailable until a second maintainer exists.

Fallback gate for a single-owner repository:

- Pull request required.
- The four checks above pass.
- Conversation resolution required.
- Zero required approvals.

Require an independent approval only once a second maintainer exists. The
check names above are unchanged by this gate. Hosted settings have not been
changed.
