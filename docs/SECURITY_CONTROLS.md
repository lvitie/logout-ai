# Security controls verification

Phase 5 checklist. Status: documented, not confirmed. Run the queries against the
live repository, then record results in the evidence tables. Do not mark the
ROADMAP Phase 5 line confirmed until every control has a passing row or a
recorded exception.

All queries are read-only `GET` requests through `gh api`. They use the
authenticated `gh` session; never paste tokens, headers, or alert secret values
into this file. Replace `{owner}/{repo}` with the repository slug. The caller needs
admin access for `security_and_analysis` and push access for alert lists.

Automated subset (ruleset, required checks, secret scanning, push protection,
Dependabot alerts, security updates, `dependabot.yml`):
[`scripts/check-hosted-settings.sh`](../scripts/check-hosted-settings.sh) `[owner/repo]`
prints PASS/FAIL per control, exits 1 on any FAIL, and prints SKIP (exit 0) when
`gh` is missing or unauthenticated. A SKIP is not a pass.

## 1. Secret scanning

```sh
gh api repos/{owner}/{repo} --jq '.security_and_analysis.secret_scanning.status'
```

- Expected: `enabled`.

## 2. Push protection

```sh
gh api repos/{owner}/{repo} --jq '.security_and_analysis.secret_scanning_push_protection.status'
```

- Expected: `enabled`.

## 3. Secret scanning alerts

```sh
gh api "repos/{owner}/{repo}/secret-scanning/alerts?state=open" --jq 'length'
```

- Expected: HTTP 200 and `0` open alerts, or each open alert triaged. Record
  only the count and alert numbers, not secret values.
- HTTP 404 means secret scanning is disabled or unavailable (see below).

## 4. Dependabot alerts

```sh
gh api repos/{owner}/{repo}/vulnerability-alerts --include 2>&1 | head -n 1
gh api "repos/{owner}/{repo}/dependabot/alerts?state=open" --jq 'length'
```

- Expected: first query `HTTP/2.0 204` (alerts enabled; 404 means disabled);
  second query HTTP 200 with `0` open alerts, or each alert triaged.

## 5. Dependabot security updates

```sh
gh api repos/{owner}/{repo} --jq '.security_and_analysis.dependabot_security_updates.status'
```

- Expected: `enabled`.

## 6. Dependabot version updates (`dependabot.yml`)

```sh
gh api repos/{owner}/{repo}/contents/.github/dependabot.yml --jq '.path'
gh api "repos/{owner}/{repo}/pulls?state=all&per_page=100" --jq '[.[] | select(.user.login == "dependabot[bot]")] | length'
```

- Expected: first query prints `.github/dependabot.yml` on the default branch.
  The file currently configures the `github-actions` ecosystem weekly. The second
  query is informational: a count above `0` shows the config has produced PRs.

## 7. Dependency review

The job `Dependency review` in
[`validate.yml`](../.github/workflows/validate.yml) runs on pull requests only
(see [REQUIRED_CHECKS.md](REQUIRED_CHECKS.md)). It needs the dependency graph.

```sh
gh api repos/{owner}/{repo}/contents/.github/workflows/validate.yml --jq '.path'
gh api "repos/{owner}/{repo}/commits/{ref}/check-runs" --jq '.check_runs[] | select(.name == "Dependency review") | {name, conclusion}'
```

- Expected: workflow file present; for a pull request head SHA as `{ref}`, the
  `Dependency review` check-run has conclusion `success`. It is absent on
  `main` pushes by design.

## When a feature is unavailable

- Private repository: secret scanning, push protection, and dependency review
  need GitHub Advanced Security (or Secret Protection / Code Security) on
  private repos. On public repos they are free.
- Plan limits or disabled feature: queries return `null` fields in
  `security_and_analysis` or HTTP 403/404. Do not treat that as a pass.
- Record the result as `unavailable`, with the HTTP status or `null` field and
  the reason (plan, private repo, permission). Do not change settings from this
  checklist.
- Then either get explicit owner approval to enable the feature or plan, or
  record an accepted exception with owner and date, and note a compensating
  control (for example local secret scanning before push).
- A 403 may be a missing permission; rerun with an admin account before
  recording `unavailable`.

## Evidence

Result values: `pass`, `fail`, `unavailable`. Link to a run log, screenshot, or
issue; do not embed raw output with secrets.

| Control | Date | Who | Result | Link |
| --- | --- | --- | --- | --- |
| Secret scanning | | | | |
| Push protection | | | | |
| Secret scanning alerts | | | | |
| Dependabot alerts | | | | |
| Dependabot security updates | | | | |
| `dependabot.yml` | | | | |
| Dependency review | | | | |
