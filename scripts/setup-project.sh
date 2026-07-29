#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template_root="$repo_root/.agents/skills/ai-project-manager/assets/project-docs"
dry_run=false
target_path=""
requested_skills=()
added_count=0
skipped_count=0

usage() {
  printf 'usage: %s [--dry-run] [--skill NAME]... [--] TARGET_PATH\n' "$(basename "$0")"
}

fail() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

ensure_directory() {
  local directory="$1"

  if [[ -d "$directory" ]]; then
    return
  fi

  if [[ -e "$directory" || -L "$directory" ]]; then
    fail "path exists and is not a directory: $directory"
  fi

  if $dry_run; then
    printf '+ mkdir -p %q\n' "$directory"
  else
    mkdir -p -- "$directory"
  fi
}

copy_missing_file() {
  local source="$1"
  local destination="$2"

  if [[ -e "$destination" || -L "$destination" ]]; then
    printf 'kept existing: %s\n' "$destination"
    skipped_count=$((skipped_count + 1))
    return
  fi

  ensure_directory "$(dirname "$destination")"
  if $dry_run; then
    printf '+ cp -p %q %q\n' "$source" "$destination"
  else
    cp -p -- "$source" "$destination"
  fi
  printf 'added: %s\n' "$destination"
  added_count=$((added_count + 1))
}

copy_missing_tree() {
  local source_root="$1"
  local destination_root="$2"
  local source_path
  local relative_path

  ensure_directory "$destination_root"

  while IFS= read -r -d '' source_path; do
    relative_path="${source_path#"$source_root"/}"
    ensure_directory "$destination_root/$relative_path"
  done < <(find "$source_root" -mindepth 1 -type d -print0)

  while IFS= read -r -d '' source_path; do
    relative_path="${source_path#"$source_root"/}"
    copy_missing_file "$source_path" "$destination_root/$relative_path"
  done < <(find "$source_root" -mindepth 1 -type f -print0)
}

skill_was_requested() {
  local expected="$1"
  local candidate

  for candidate in "${requested_skills[@]}"; do
    [[ "$candidate" == "$expected" ]] && return 0
  done
  return 1
}

while (($# > 0)); do
  case "$1" in
    --dry-run)
      dry_run=true
      shift
      ;;
    --skill)
      (($# >= 2)) || fail "--skill requires a skill name"
      [[ "$2" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "invalid skill name: $2"
      if ! skill_was_requested "$2"; then
        requested_skills+=("$2")
      fi
      shift 2
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    --)
      shift
      (($# == 1)) || fail "expected exactly one target path after --"
      target_path="$1"
      shift
      ;;
    -*)
      fail "unknown option: $1"
      ;;
    *)
      [[ -z "$target_path" ]] || fail "expected exactly one target path"
      target_path="$1"
      shift
      ;;
  esac
done

[[ -n "$target_path" ]] || {
  usage >&2
  exit 2
}

if printf '%s' "$target_path" | LC_ALL=C grep -q '[[:cntrl:]]'; then
  fail "target path contains unsupported control characters"
fi

[[ -d "$template_root" ]] || fail "project templates do not exist: $template_root"

base_skills=("ai-project-manager" "project-bootstrap")
for skill_name in "${base_skills[@]}" "${requested_skills[@]}"; do
  [[ -d "$repo_root/.agents/skills/$skill_name" ]] ||
    fail "skill does not exist in Logout AI: $skill_name"
done

if [[ -e "$target_path" || -L "$target_path" ]]; then
  [[ -d "$target_path" ]] || fail "target exists and is not a directory: $target_path"
  target_absolute="$(cd "$target_path" && pwd -P)"
  [[ "$target_absolute" != "$repo_root" ]] || fail "target cannot be the Logout AI repository"
fi

ensure_directory "$target_path"

for document in AGENTS.md SPEC.md ROADMAP.md TASKS.md; do
  copy_missing_file "$template_root/$document" "$target_path/$document"
done

skills_to_copy=()
for skill_name in "${base_skills[@]}" "${requested_skills[@]}"; do
  duplicate=false
  for existing_skill in "${skills_to_copy[@]}"; do
    if [[ "$existing_skill" == "$skill_name" ]]; then
      duplicate=true
      break
    fi
  done
  $duplicate || skills_to_copy+=("$skill_name")
done

for skill_name in "${skills_to_copy[@]}"; do
  copy_missing_tree \
    "$repo_root/.agents/skills/$skill_name" \
    "$target_path/.agents/skills/$skill_name"
done

if $dry_run; then
  printf 'dry run complete: %d file(s) would be added, %d existing file(s) kept\n' \
    "$added_count" "$skipped_count"
else
  printf 'project setup complete: %d file(s) added, %d existing file(s) kept\n' \
    "$added_count" "$skipped_count"
fi
