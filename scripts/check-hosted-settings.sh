#!/usr/bin/env bash
# Read-only: compare hosted repo settings with docs/SECURITY_CONTROLS.md.
# Usage: check-hosted-settings.sh [owner/repo]
# Only GET requests via gh api. Exits 0 with SKIP when gh is missing or unauthenticated.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v gh >/dev/null 2>&1; then
  echo "SKIP: gh not installed"
  exit 0
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "SKIP: gh not authenticated"
  exit 0
fi

repo="${1:-}"
if [[ -z "$repo" ]]; then
  repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" || {
    echo "SKIP: cannot determine repository; pass owner/repo"
    exit 0
  }
fi

failures=0
pass() { echo "PASS: $1"; }
fail() {
  echo "FAIL: $1" >&2
  failures=$((failures + 1))
}
# Print the response only on success: on 4xx gh skips --jq and prints the error body.
get() {
  local out
  out="$(gh api "$@" 2>/dev/null)" || return 0
  printf '%s\n' "$out"
}

# Ruleset (docs/RULESET_RUNBOOK.md) and its required checks (docs/REQUIRED_CHECKS.md).
# shellcheck disable=SC2016
expected="$(sed -n 's/^|.*| `\([^`]*\)` |$/\1/p' "$repo_root/docs/REQUIRED_CHECKS.md" | sort -u)"
ruleset_id="$(get "repos/$repo/rulesets" --jq '[.[] | select(.name == "default-branch")][0].id // empty')"
if [[ -z "$ruleset_id" ]]; then
  fail "ruleset default-branch: not found"
  fail "ruleset required checks: no ruleset"
else
  ruleset="repos/$repo/rulesets/$ruleset_id"
  enforcement="$(get "$ruleset" --jq '.enforcement // empty')"
  if [[ "$enforcement" == "active" ]]; then
    pass "ruleset default-branch: active"
  else
    fail "ruleset default-branch: enforcement '${enforcement:-unknown}', expected active"
  fi
  types="$(get "$ruleset" --jq '[.rules[]?.type] | sort | join(",")')"
  want_types="deletion,non_fast_forward,pull_request,required_status_checks"
  if [[ "$types" == "$want_types" ]]; then
    pass "ruleset rules: $types"
  else
    fail "ruleset rules: '$types', expected '$want_types'"
  fi
  hosted="$(get "$ruleset" --jq '.rules[]? | select(.type == "required_status_checks") | .parameters.required_status_checks[].context' | sort -u)"
  if [[ -n "$expected" && "$hosted" == "$expected" ]]; then
    pass "ruleset required checks match docs/REQUIRED_CHECKS.md"
  else
    fail "ruleset required checks differ from docs/REQUIRED_CHECKS.md (hosted: $(tr '\n' ';' <<<"$hosted"))"
  fi
fi

check_status() { # label field
  local value
  value="$(get "repos/$repo" --jq ".security_and_analysis.$2.status // \"unavailable\"")"
  if [[ "$value" == "enabled" ]]; then
    pass "$1: enabled"
  else
    fail "$1: ${value:-unavailable}, expected enabled"
  fi
}
check_status "secret scanning" secret_scanning
check_status "push protection" secret_scanning_push_protection
check_status "Dependabot security updates" dependabot_security_updates

# Dependabot alerts enabled: 204 on success, 404 when disabled.
first="$(gh api "repos/$repo/vulnerability-alerts" --include 2>&1 | head -n 1 || true)"
if [[ "$first" == *" 204"* ]]; then
  pass "Dependabot alerts: enabled"
else
  fail "Dependabot alerts: '${first:-no response}', expected 204"
fi

if [[ -n "$(get "repos/$repo/contents/.github/dependabot.yml" --jq .path)" ]]; then
  pass "dependabot.yml present"
else
  fail "dependabot.yml: not found on default branch"
fi

if ((failures > 0)); then
  echo "$failures control(s) failed" >&2
  exit 1
fi
echo "all controls pass"
