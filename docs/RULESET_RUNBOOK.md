# Default-branch ruleset runbook

Ruleset: [`rulesets/default-branch.json`](rulesets/default-branch.json). Check
names: [required CI checks](REQUIRED_CHECKS.md). These commands are documented
only; nothing here has been run against a hosted repository. Replace
`OWNER/REPO`. Applying needs admin rights on the repository.

## Preconditions

- `validate.yml` is on the default branch and has run remotely.
- Check names match the docs. `Dependency review` runs only on pull requests, so
  pass a pull request head SHA or branch as the ref:

  ```sh
  scripts/check-required-checks.sh OWNER/REPO <pr-head-sha>
  ```

  Exit 0 means the names match. Exit 1 prints a diff. Do not apply on mismatch.
- No existing ruleset or branch protection conflicts:
  `gh api repos/OWNER/REPO/rulesets`.

## Apply

```sh
gh api -X POST repos/OWNER/REPO/rulesets \
  --input docs/rulesets/default-branch.json
```

Record the returned `id` as `RULESET_ID`.

## Verify

```sh
gh api repos/OWNER/REPO/rulesets/RULESET_ID \
  --jq '{name, enforcement, rules: [.rules[].type]}'
```

- Expect `enforcement: active` and `pull_request`, `required_status_checks`,
  `non_fast_forward`, `deletion`.
- Open a test pull request: merging is blocked until the four checks pass and
  conversations are resolved.
- A direct push or force-push to the default branch is rejected.

## Rollback

Disable (keeps the definition):

```sh
gh api -X PUT repos/OWNER/REPO/rulesets/RULESET_ID \
  --input <(jq '.enforcement = "disabled"' docs/rulesets/default-branch.json)
```

Remove:

```sh
gh api -X DELETE repos/OWNER/REPO/rulesets/RULESET_ID
```

## Notes

- Zero required approvals matches the single-owner fallback gate. The
  independent-approval rule is a separate task.
- `bypass_actors` is empty; add admins only deliberately.
