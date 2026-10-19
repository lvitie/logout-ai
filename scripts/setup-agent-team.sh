#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
team_root="$repo_root/agent-team"
dry_run=false
target_path=""
bin_dir="${HOME}/.local/bin"
agents=""
added_count=0
skipped_count=0

usage() {
  printf 'usage: %s [--dry-run] [--bin-dir DIR] [--agents claude|codex|both] [--] PROJECT_PATH\n' "$(basename "$0")"
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

detected_agents() {
  local has_claude=false has_codex=false

  command -v claude >/dev/null 2>&1 && has_claude=true
  command -v codex >/dev/null 2>&1 && has_codex=true
  if $has_claude && $has_codex; then
    printf 'both\n'
  elif $has_codex; then
    printf 'codex\n'
  else
    printf 'claude\n'
  fi
}

ask_agents() {
  local default reply

  default="$(detected_agents)"
  if [[ ! -t 0 ]]; then
    agents="$default"
    printf 'agents: %s (detected on PATH; pass --agents to choose)\n' "$agents"
    return
  fi

  printf 'Which agent CLIs should the team use?\n'
  printf '  1) claude  Claude Code for every role\n'
  printf '  2) codex   Codex CLI for every role\n'
  printf '  3) both    mixed roles: Claude and Codex review each other\n'
  while true; do
    read -r -p "Choice [$default]: " reply || reply=""
    case "${reply:-$default}" in
      1 | claude) agents=claude ;;
      2 | codex) agents=codex ;;
      3 | both) agents=both ;;
      *)
        printf 'enter 1, 2, 3, claude, codex or both\n'
        continue
        ;;
    esac
    break
  done
}

# Writes the template with the project name and the role preset for the chosen agents.
write_config() {
  python3 -I -c '
import sys
from pathlib import Path

src, dst, name, agents = sys.argv[1:]
CLAUDE = {"producer": ("claude", "claude-sonnet-5-5", "low"), "mid": ("claude", "claude-sonnet-5-5", "medium"),
          "senior": ("claude", "claude-opus-5-5", "high"), "architect": ("claude", "claude-opus-5-5", "high"),
          "director": ("claude", "claude-opus-5-5", "high")}
CODEX = {"producer": ("codex", "gpt-6.1-sol", "low"), "mid": ("codex", "gpt-6.1-sol", "medium"),
         "senior": ("codex", "gpt-6.1-sol", "high"), "architect": ("codex", "gpt-6-astra", "high"),
         "director": ("codex", "gpt-6-astra", "high")}
# Codex implements simple and complex work and Claude reviews it; hard work is planned by Codex, built by Claude.
BOTH = {"producer": CLAUDE["producer"], "mid": CODEX["mid"], "senior": CLAUDE["senior"],
        "architect": CLAUDE["architect"], "director": CODEX["director"]}
NAMES = {"producer": "Producer", "mid": "Mid Dev", "senior": "Senior Dev", "architect": "Architect",
         "director": "Tech Director"}
preset = {"claude": CLAUDE, "codex": CODEX, "both": BOTH}[agents]
roles = "".join(f"[roles.{k}]\nname = \"{NAMES[k]}\"\ncli = \"{c}\"\nmodel = \"{m}\"\neffort = \"{e}\"\n"
                for k, (c, m, e) in preset.items())
text = Path(src).read_text()
start = text.index("\n", text.index("# --- roles:")) + 1
end = text.index("# --- end roles ---")
text = text[:start] + roles + text[end:]
Path(dst).write_text(text.replace("name = \"myproject\"", f"name = \"{name}\"", 1))
' "$@"
}

# Keeps the state dir out of `git add -A` when the project is already a git repository.
exclude_state_dir() {
  local exclude pattern

  git -C "$target_path" rev-parse --git-dir >/dev/null 2>&1 || return 1
  exclude="$(git -C "$target_path" rev-parse --path-format=absolute --git-path info/exclude)"
  pattern="/$(git -C "$target_path" rev-parse --show-prefix).agent-team/"
  if [[ -f "$exclude" ]] && grep -qxF -- "$pattern" "$exclude"; then
    printf 'kept existing: %s in %s\n' "$pattern" "$exclude"
    skipped_count=$((skipped_count + 1))
    return 0
  fi
  if $dry_run; then
    printf '+ append %s to %q\n' "$pattern" "$exclude"
  else
    mkdir -p -- "$(dirname "$exclude")"
    printf '%s\n' "$pattern" >>"$exclude"
  fi
  printf 'added: %s to %s\n' "$pattern" "$exclude"
  added_count=$((added_count + 1))
}

link_missing() {
  local source="$1"
  local destination="$2"

  if [[ -L "$destination" && "$(readlink -- "$destination")" == "$source" ]]; then
    printf 'kept existing: %s\n' "$destination"
    skipped_count=$((skipped_count + 1))
    return
  fi
  if [[ -e "$destination" || -L "$destination" ]]; then
    printf 'kept existing (different target): %s\n' "$destination"
    skipped_count=$((skipped_count + 1))
    return
  fi

  ensure_directory "$(dirname "$destination")"
  if $dry_run; then
    printf '+ ln -s %q %q\n' "$source" "$destination"
  else
    ln -s -- "$source" "$destination"
  fi
  printf 'added: %s\n' "$destination"
  added_count=$((added_count + 1))
}

while (($# > 0)); do
  case "$1" in
    --dry-run)
      dry_run=true
      shift
      ;;
    --bin-dir)
      (($# >= 2)) || fail "--bin-dir requires a directory"
      bin_dir="$2"
      shift 2
      ;;
    --agents)
      (($# >= 2)) || fail "--agents requires claude, codex or both"
      case "$2" in
        claude | codex | both) agents="$2" ;;
        *) fail "--agents must be claude, codex or both" ;;
      esac
      shift 2
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    --)
      shift
      (($# == 1)) || fail "expected exactly one project path after --"
      target_path="$1"
      shift
      ;;
    -*)
      fail "unknown option: $1"
      ;;
    *)
      [[ -z "$target_path" ]] || fail "expected exactly one project path"
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
  fail "project path contains unsupported control characters"
fi

[[ -f "$team_root/templates/team.toml" ]] || fail "agent team templates do not exist: $team_root/templates"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || fail "Python 3.11 or newer is required (tomllib)"

if [[ -e "$target_path" || -L "$target_path" ]]; then
  [[ -d "$target_path" ]] || fail "project path exists and is not a directory: $target_path"
  target_absolute="$(cd "$target_path" && pwd -P)"
  [[ "$target_absolute" != "$repo_root" ]] || fail "project path cannot be the Logout AI repository"
fi

ensure_directory "$target_path"

config="$target_path/team.toml"
if [[ -e "$config" || -L "$config" ]]; then
  printf 'kept existing: %s\n' "$config"
  skipped_count=$((skipped_count + 1))
else
  project_name="$(basename "$target_path")"
  [[ "$project_name" != "." ]] && project_name="$(basename "$(cd "$target_path" 2>/dev/null && pwd -P || printf '%s' "$target_path")")"
  project_name="${project_name//[^A-Za-z0-9._-]/-}"
  [[ -n "$agents" ]] || ask_agents
  for cli in claude codex; do
    if [[ "$agents" == "$cli" || "$agents" == both ]] && ! command -v "$cli" >/dev/null 2>&1; then
      printf 'warning: %s is not on PATH; install it before running the team\n' "$cli" >&2
    fi
  done
  if $dry_run; then
    printf '+ write %q (name=%s, agents=%s)\n' "$config" "$project_name" "$agents"
  else
    write_config "$team_root/templates/team.toml" "$config" "$project_name" "$agents"
  fi
  printf 'added: %s\n' "$config"
  added_count=$((added_count + 1))
fi

state_hint=", add .agent-team/ to the project ignore list"
exclude_state_dir && state_hint=""

launcher="$target_path/team.sh"
if [[ -e "$launcher" || -L "$launcher" ]]; then
  printf 'kept existing: %s\n' "$launcher"
  skipped_count=$((skipped_count + 1))
else
  if $dry_run; then
    printf '+ write %q (project launcher)\n' "$launcher"
  else
    python3 -I -c 'import pathlib, shlex, sys
source, destination, root = sys.argv[1:]
path = pathlib.Path(destination)
path.write_text(pathlib.Path(source).read_text().replace("@@LOGOUT_AI_ROOT@@", shlex.quote(root)))
path.chmod(path.stat().st_mode | 0o111)' "$team_root/templates/team.sh" "$launcher" "$repo_root"
  fi
  printf 'added: %s\n' "$launcher"
  added_count=$((added_count + 1))
fi

link_missing "$team_root/bin/team" "$bin_dir/team"
link_missing "$team_root/bin/team-up" "$bin_dir/team-up"

if $dry_run; then
  printf 'dry run complete: %d item(s) would be added, %d existing item(s) kept\n' \
    "$added_count" "$skipped_count"
else
  printf 'agent team setup complete: %d item(s) added, %d existing item(s) kept\n' \
    "$added_count" "$skipped_count"
fi
printf 'next: review %s%s, run ./team.sh from the project\n' "$config" "$state_hint"
