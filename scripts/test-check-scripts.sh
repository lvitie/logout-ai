#!/usr/bin/env bash
# Offline fixtures for check-hosted-settings.sh and check-required-checks.sh.
# A stub gh with canned output replaces the real one; no network, no gh auth.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
failures=0

mkdir "$tmp/stub" "$tmp/nogh"
cat >"$tmp/stub/gh" <<'STUB'
#!/usr/bin/env bash
# Canned gh. Env: GH_AUTH_RC, GH_API_RC, STUB_ENFORCEMENT, STUB_TYPES, STUB_CHECKS,
# STUB_SCAN, STUB_PUSH, STUB_DEPSEC, STUB_ALERTS, STUB_DEPFILE.
if [[ "$1" == auth ]]; then exit "${GH_AUTH_RC:-0}"; fi
[[ "$1" == api ]] || exit 1
((${GH_API_RC:-0} == 0)) || { echo '{"message":"Not Found","status":"404"}'; exit "$GH_API_RC"; }
shift
args="$*"
case "$args" in
*/vulnerability-alerts*) echo "HTTP/2.0 ${STUB_ALERTS:-204} stub" ;;
*/contents/.github/dependabot.yml*) [[ "${STUB_DEPFILE:-1}" == 1 ]] && echo .github/dependabot.yml ;;
*/check-runs*) printf '%s\n' "${STUB_CHECKS:-}" ;;
*/rulesets/1*)
  case "$args" in
  *enforcement*) echo "${STUB_ENFORCEMENT:-active}" ;;
  *"| join"*) echo "${STUB_TYPES:-deletion,non_fast_forward,pull_request,required_status_checks}" ;;
  *context*) printf '%s\n' "${STUB_CHECKS:-}" ;;
  esac ;;
*/rulesets*) echo 1 ;;
*default_branch*) echo main ;;
*secret_scanning_push_protection*) echo "${STUB_PUSH:-enabled}" ;;
*dependabot_security_updates*) echo "${STUB_DEPSEC:-enabled}" ;;
*secret_scanning*) echo "${STUB_SCAN:-enabled}" ;;
esac
STUB
chmod +x "$tmp/stub/gh"

# PATH with the tools the scripts need but no gh.
for tool in dirname sed sort tr diff head cat; do
  ln -s "$(command -v "$tool")" "$tmp/nogh/$tool"
done

# shellcheck disable=SC2016
checks="$(sed -n 's/^|.*| `\([^`]*\)` |$/\1/p' "$repo_root/docs/REQUIRED_CHECKS.md" | sort -u)"
[[ -n "$checks" ]] || { echo "no check names in docs/REQUIRED_CHECKS.md" >&2; exit 1; }

# run <name> <expected rc> <expected output substring> <command...>
run() {
  local name="$1" want="$2" needle="$3" out rc=0
  shift 3
  out="$("$@" 2>&1)" || rc=$?
  if [[ "$rc" != "$want" || "$out" != *"$needle"* ]]; then
    echo "FAIL: $name (rc=$rc, want $want, expected output '$needle')" >&2
    printf '%s\n' "$out" | sed 's/^/  | /' >&2
    failures=$((failures + 1))
  else
    echo "ok: $name"
  fi
}

hosted="$repo_root/scripts/check-hosted-settings.sh"
required="$repo_root/scripts/check-required-checks.sh"
with_stub() { env PATH="$tmp/stub:$PATH" STUB_CHECKS="$checks" "$@"; }

# check-hosted-settings.sh
run "hosted: pass" 0 "all controls pass" with_stub bash "$hosted" o/r
run "hosted: gh missing" 0 "SKIP: gh not installed" env PATH="$tmp/nogh" "$(command -v bash)" "$hosted" o/r
run "hosted: gh unauthenticated" 0 "SKIP: gh not authenticated" with_stub GH_AUTH_RC=1 bash "$hosted" o/r
run "hosted: ruleset not enforced" 1 "enforcement 'disabled'" with_stub STUB_ENFORCEMENT=disabled bash "$hosted" o/r
run "hosted: rule type missing" 1 "ruleset rules" with_stub STUB_TYPES=deletion bash "$hosted" o/r
run "hosted: required check missing" 1 "required checks differ" with_stub STUB_CHECKS="Dependency review" bash "$hosted" o/r
run "hosted: push protection off" 1 "push protection: disabled" with_stub STUB_PUSH=disabled bash "$hosted" o/r
run "hosted: alerts disabled" 1 "Dependabot alerts" with_stub STUB_ALERTS=404 bash "$hosted" o/r
run "hosted: dependabot.yml missing" 1 "dependabot.yml: not found" with_stub STUB_DEPFILE=0 bash "$hosted" o/r
run "hosted: API error" 1 "control(s) failed" with_stub GH_API_RC=1 bash "$hosted" o/r

# check-required-checks.sh
run "required: usage" 2 "usage:" with_stub bash "$required"
run "required: pass" 0 "check names match" with_stub bash "$required" o/r main
run "required: default ref lookup" 0 "check names match" with_stub bash "$required" o/r
run "required: missing hosted check" 1 "mismatch" with_stub STUB_CHECKS="Dependency review" bash "$required" o/r main
run "required: API error" 1 "" with_stub GH_API_RC=1 bash "$required" o/r main

if ((failures > 0)); then
  echo "$failures check-script test(s) failed" >&2
  exit 1
fi
echo "check-script tests passed"
