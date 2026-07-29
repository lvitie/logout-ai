#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task_test_root="$(mktemp -d "${TMPDIR:-/tmp}/logout-ai-project-setup-test.XXXXXX")"

cleanup() {
  if [[ -d "$task_test_root" && "$(basename "$task_test_root")" == logout-ai-project-setup-test.* ]]; then
    rm -rf -- "$task_test_root"
  fi
}
trap cleanup EXIT

fail() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

new_project="$task_test_root/new project"
"$repo_root/scripts/setup-project.sh" --skill rust-cli "$new_project" >/dev/null

for document in AGENTS.md SPEC.md ROADMAP.md TASKS.md; do
  [[ -f "$new_project/$document" ]] || fail "missing seeded document: $document"
done

for skill_name in ai-project-manager project-bootstrap rust-cli; do
  [[ -f "$new_project/.agents/skills/$skill_name/SKILL.md" ]] ||
    fail "missing seeded skill: $skill_name"
done

existing_project="$task_test_root/existing project"
mkdir -p "$existing_project/.agents/skills/ai-project-manager"
printf 'custom project instructions\n' >"$existing_project/AGENTS.md"
printf 'custom skill instructions\n' >"$existing_project/.agents/skills/ai-project-manager/SKILL.md"

"$repo_root/scripts/setup-project.sh" "$existing_project" >/dev/null

[[ "$(cat "$existing_project/AGENTS.md")" == "custom project instructions" ]] ||
  fail "existing project instructions were overwritten"
[[ "$(cat "$existing_project/.agents/skills/ai-project-manager/SKILL.md")" == "custom skill instructions" ]] ||
  fail "existing skill instructions were overwritten"
[[ -f "$existing_project/SPEC.md" ]] || fail "missing document added to existing project"
[[ -f "$existing_project/.agents/skills/ai-project-manager/agents/openai.yaml" ]] ||
  fail "missing skill content was not merged"

"$repo_root/scripts/setup-project.sh" "$existing_project" >/dev/null
[[ "$(cat "$existing_project/AGENTS.md")" == "custom project instructions" ]] ||
  fail "idempotent setup changed existing project instructions"

dry_run_project="$task_test_root/dry run project"
"$repo_root/scripts/setup-project.sh" --dry-run "$dry_run_project" >/dev/null
[[ ! -e "$dry_run_project" && ! -L "$dry_run_project" ]] ||
  fail "dry run created the target project"

file_target="$task_test_root/file target"
printf 'not a directory\n' >"$file_target"
if "$repo_root/scripts/setup-project.sh" "$file_target" >/dev/null 2>&1; then
  fail "setup accepted a file as the target"
fi

missing_skill_project="$task_test_root/missing skill project"
if "$repo_root/scripts/setup-project.sh" --skill does-not-exist "$missing_skill_project" >/dev/null 2>&1; then
  fail "setup accepted a missing skill"
fi
[[ ! -e "$missing_skill_project" ]] || fail "missing-skill failure created the target project"

printf 'project setup integration test passed\n'
