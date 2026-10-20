#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT

fail() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

project="$tmp/My Project"
bin="$tmp/bin"
export HOME="$tmp/home"
export GIT_CONFIG_GLOBAL="$tmp/gitconfig"
export XDG_STATE_HOME="$tmp/state" XDG_CACHE_HOME="$tmp/cache" CODEX_HOME="$tmp/codex"
mkdir -p "$HOME"
unset TEAM_CONFIG

dry_output="$("$repo_root/scripts/setup-agent-team.sh" --dry-run --bin-dir "$bin" "$project")"
grep -q 'dry run complete' <<<"$dry_output" || fail "dry run did not finish"
[[ ! -e "$project" && ! -e "$bin" ]] || fail "dry run created files"

"$repo_root/scripts/setup-agent-team.sh" --vcs git --bin-dir "$bin" "$project" >/dev/null
[[ -f "$project/team.toml" ]] || fail "team.toml was not created"
[[ -x "$project/team.sh" ]] || fail "team.sh was not created or is not executable"
bash -n "$project/team.sh" || fail "team.sh has invalid syntax"
"$project/team.sh" --help | grep -q 'Missing dependencies' || fail "launcher help failed"
grep -q '^name = "My-Project"' "$project/team.toml" || fail "project name was not substituted"
[[ -L "$bin/team" && -L "$bin/team-up" ]] || fail "launchers were not linked"

second="$("$repo_root/scripts/setup-agent-team.sh" --bin-dir "$bin" "$project")"
grep -q '0 item(s) added' <<<"$second" || fail "second run was not idempotent"
printf '# preserved launcher\n' >>"$project/team.sh"
"$repo_root/scripts/setup-agent-team.sh" --bin-dir "$bin" "$project" >/dev/null
tail -n 1 "$project/team.sh" | grep -qx '# preserved launcher' || fail "existing launcher overwritten"

git -C "$project" init -q
(cd "$project" && "$bin/team" new --no-run "setup check" >/dev/null && "$bin/team" status | grep -q 'chg:t001') ||
  fail "installed team command did not create and list a task"

if "$repo_root/scripts/setup-agent-team.sh" --bogus "$project" >/dev/null 2>&1; then
  fail "unknown option accepted"
fi
if "$repo_root/scripts/setup-agent-team.sh" --agents gemini "$tmp/other" >/dev/null 2>&1; then
  fail "unknown --agents value accepted"
fi
if "$repo_root/scripts/setup-agent-team.sh" --vcs svn "$tmp/other" >/dev/null 2>&1; then
  fail "unknown --vcs value accepted"
fi

# Perforce: the p4 adapter and guard are configured and no git exclude entry is written.
git init -q "$tmp/repo-p4"
"$repo_root/scripts/setup-agent-team.sh" --agents claude --vcs p4 --bin-dir "$bin" "$tmp/repo-p4" >/dev/null 2>&1
vcs_kind="$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import teamcfg
c = teamcfg.load(sys.argv[2])["vcs"]; print(c["kind"], *c["guard_names"], *c["deny"]["git"])' \
  "$repo_root/agent-team" "$tmp/repo-p4/team.toml")" || fail "p4 preset does not load"
[[ "$vcs_kind" == "p4 p4 git *" ]] || fail "p4 preset has vcs: $vcs_kind"
! grep -qxF '/.agent-team/' "$tmp/repo-p4/.git/info/exclude" || fail "git exclude written for a p4 project"

# Perforce dry run: names the p4 preset and writes nothing.
p4_dry="$("$repo_root/scripts/setup-agent-team.sh" --dry-run --agents claude --vcs p4 --bin-dir "$bin" "$tmp/dry-p4" 2>&1)"
grep -q 'vcs=p4' <<<"$p4_dry" || fail "p4 dry run did not name the vcs"
[[ ! -e "$tmp/dry-p4" ]] || fail "p4 dry run created files"

# The generated config starts from the game-dev defaults: domains, locks, agents, skills and the heuristic rules.
defaults="$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import teamcfg
c = teamcfg.load(sys.argv[2]); R = c["routing"]
print(len(R["domains"]), len(R["domain"]), *c["locks"]["names"], *c["locks"]["default"], len(c["heuristic"]["rules"]),
      all(a in c["agent_defs"] for a in ("designer", "gameplay", "engine", "tools", "technical_artist", "audio", "qa", "build_release",
                                          "narrative", "vfx", "ui")),
      all(s in teamcfg.list_skills(c) for s in ("shaders", "animation", "level-design", "balancing", "netcode", "optimization",
                                                "gameplay-systems", "rendering", "vfx", "localization", "qa-test-planning")))' \
  "$repo_root/agent-team" "$tmp/repo-p4/team.toml")" || fail "game-dev defaults do not load"
[[ "$defaults" == "7 7 editor gpu build editor 4 True True" ]] || fail "game-dev defaults: $defaults"

# No VCS: kind none, no guard, no deny rules, and no git exclude entry even inside a git repository.
git init -q "$tmp/repo-none"
"$repo_root/scripts/setup-agent-team.sh" --agents claude --vcs none --bin-dir "$bin" "$tmp/repo-none" >/dev/null 2>&1
vcs_kind="$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import teamcfg
c = teamcfg.load(sys.argv[2])["vcs"]; print(c["kind"], len(c["guard_names"]), len(c["deny"]), len(c["deny_flags"]))' \
  "$repo_root/agent-team" "$tmp/repo-none/team.toml")" || fail "none preset does not load"
[[ "$vcs_kind" == "none 0 0 0" ]] || fail "none preset has vcs: $vcs_kind"
! grep -qxF '/.agent-team/' "$tmp/repo-none/.git/info/exclude" || fail "git exclude written for a project without VCS"

# Each preset loads and uses the chosen CLIs; an existing repo gets the state dir excluded once.
for agents in claude codex both; do
  repo="$tmp/repo-$agents"
  git init -q "$repo"
  "$repo_root/scripts/setup-agent-team.sh" --agents "$agents" --vcs git --bin-dir "$bin" "$repo" >/dev/null 2>&1
  clis="$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import teamcfg
print(" ".join(sorted({r["cli"] for r in teamcfg.load(sys.argv[2])["roles"].values()})))' \
    "$repo_root/agent-team" "$repo/team.toml")" || fail "$agents preset does not load"
  case "$agents" in
    both) [[ "$clis" == "claude codex" ]] ;;
    *) [[ "$clis" == "$agents" ]] ;;
  esac || fail "$agents preset uses: $clis"
  grep -qxF '/.agent-team/' "$repo/.git/info/exclude" || fail "state dir not excluded for $agents"
  # The escalation ladder: written per preset, loads without warnings, five tiers weakest first.
  tiers="$(python3 -I -W error -c 'import sys; sys.path.insert(0, sys.argv[1]); import teamcfg
print(" ".join(t["name"] for t in teamcfg.load(sys.argv[2])["heuristic"]["tiers"]))' \
    "$repo_root/agent-team" "$repo/team.toml")" || fail "$agents preset has no loadable tier ladder"
  [[ "$tiers" == "low mid high top apex" ]] || fail "$agents preset has tiers: $tiers"
done
"$repo_root/scripts/setup-agent-team.sh" --bin-dir "$bin" "$tmp/repo-both" >/dev/null 2>&1
[[ "$(grep -cxF '/.agent-team/' "$tmp/repo-both/.git/info/exclude")" == 1 ]] || fail "exclude entry duplicated"

mkdir "$tmp/repo-both/sub"
"$repo_root/scripts/setup-agent-team.sh" --agents claude --bin-dir "$bin" "$tmp/repo-both/sub" >/dev/null 2>&1
grep -qxF '/sub/.agent-team/' "$tmp/repo-both/.git/info/exclude" || fail "subdirectory state dir not excluded"

printf 'agent team setup test passed\n'
