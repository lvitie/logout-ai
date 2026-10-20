#!/usr/bin/env bash
# Read-only: compare hosted check-run names with docs/REQUIRED_CHECKS.md.
# Usage: check-required-checks.sh <owner/repo> [ref]
#        check-required-checks.sh --local   (offline: docs vs rulesets vs workflow jobs)
# Use a pull request head SHA/branch as ref: "Dependency review" only runs on pull requests.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Last column of table rows whose last cell is a backticked name.
# shellcheck disable=SC2016
doc_names() { sed -n 's/^|.*| `\([^`]*\)` |$/\1/p' "$repo_root/docs/REQUIRED_CHECKS.md" | sort -u; }

ruleset_names() {
  grep -h -o '"context": *"[^"]*"' "$repo_root"/docs/rulesets/*.json |
    sed 's/.*: *"\(.*\)"/\1/' | sort -u
}

# Job names from the workflow; expands ${{ matrix.os }} from the os list.
workflow_names() {
  awk '
    function flush(  i, n, m) {
      if (id == "") return
      n = (name == "" ? id : name)
      if (n ~ /\$\{\{ *matrix\.os *\}\}/) {
        for (i = 1; i <= nos; i++) { m = n; gsub(/\$\{\{ *matrix\.os *\}\}/, os[i], m); print m }
      } else print n
      id = ""; name = ""; nos = 0
    }
    /^jobs:/ { injobs = 1; next }
    injobs && /^[^ #]/ { flush(); injobs = 0 }
    injobs && /^  [A-Za-z0-9_-]+:[ ]*$/ { flush(); id = $1; sub(/:$/, "", id); inos = 0; next }
    injobs && /^    name:/ { v = $0; sub(/^    name:[ ]*/, "", v); gsub(/^["\x27]|["\x27]$/, "", v); name = v; next }
    injobs && /^        os:/ { inos = 1; next }
    injobs && inos && /^ *- / { v = $0; sub(/^ *- */, "", v); os[++nos] = v; next }
    injobs && inos { inos = 0 }
    END { flush() }
  ' "$repo_root/.github/workflows/validate.yml" | sort -u
}

if [[ "${1:-}" == "--local" ]]; then
  docs="$(doc_names)"
  rules="$(ruleset_names)"
  wf="$(workflow_names)"
  if [[ -z "$docs" || -z "$rules" || -z "$wf" ]]; then
    echo "empty check set (docs/REQUIRED_CHECKS.md, docs/rulesets/*.json or validate.yml parsed no names)" >&2
    exit 1
  fi
  rc=0
  for pair in "REQUIRED_CHECKS.md:docs:rulesets/*.json:rules" "REQUIRED_CHECKS.md:docs:validate.yml:wf" "rulesets/*.json:rules:validate.yml:wf"; do
    IFS=: read -r an av bn bv <<<"$pair"
    a="${!av}"; b="${!bv}"
    while IFS= read -r x; do
      [[ -n "$x" ]] && { echo "check '$x' is in $bn but missing from $an" >&2; rc=1; }
    done < <(comm -13 <(printf '%s\n' "$a") <(printf '%s\n' "$b"))
    while IFS= read -r x; do
      [[ -n "$x" ]] && { echo "check '$x' is in $an but missing from $bn" >&2; rc=1; }
    done < <(comm -23 <(printf '%s\n' "$a") <(printf '%s\n' "$b"))
  done
  [[ $rc -eq 0 ]] && echo "check names agree across docs, rulesets and workflow"
  exit $rc
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <owner/repo> [ref] | --local" >&2
  exit 2
fi

repo="$1"
ref="${2:-}"

if [[ -z "$ref" ]]; then
  ref="$(gh api "repos/$repo" --jq .default_branch)"
fi

expected="$(doc_names)"
hosted="$(gh api --paginate "repos/$repo/commits/$ref/check-runs?per_page=100" --jq '.check_runs[].name' | sort -u)"

if [[ -z "$expected" ]]; then
  echo "no check names parsed from docs/REQUIRED_CHECKS.md" >&2
  exit 2
fi

if diff -u --label "docs/REQUIRED_CHECKS.md" --label "hosted:$repo@$ref" \
  <(printf '%s\n' "$expected") <(printf '%s\n' "$hosted"); then
  echo "check names match"
else
  echo "mismatch: '-' only documented, '+' only hosted" >&2
  exit 1
fi
