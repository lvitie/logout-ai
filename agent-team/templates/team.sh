#!/usr/bin/env bash
# Start the development team from Linux/WSL, installing missing dependencies.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export PATH="/usr/bin:/bin:$HOME/.local/bin:$PATH"
export TEAM_CONFIG="$project_root/team.toml"
default_logout_root=@@LOGOUT_AI_ROOT@@
logout_root="${LOGOUT_AI_ROOT:-$default_logout_root}"

fail() {
  printf 'team.sh: %s\n' "$*" >&2
  exit 1
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  printf 'Usage: %s ["task request"]\nStarts the dashboard; a request starts a team task instead.\nMissing dependencies are installed automatically (sudo may prompt).\n' "$0"
  exit 0
fi
[[ $(uname -s) == Linux ]] || fail 'Run this script in Linux/WSL.'
[[ -f "$TEAM_CONFIG" ]] || fail "Missing config: $TEAM_CONFIG"
[[ -x "$logout_root/agent-team/bin/team-up" ]] || fail 'Logout AI checkout missing. Set LOGOUT_AI_ROOT to its location.'

install_packages() {
  local privilege=()
  if ((EUID != 0)); then
    command -v sudo >/dev/null 2>&1 || fail "sudo is required to install: $*"
    privilege=(sudo)
  fi
  printf 'Installing missing system dependencies: %s\n' "$*"
  if command -v dnf >/dev/null 2>&1; then
    "${privilege[@]}" dnf install -y "$@"
  elif command -v apt-get >/dev/null 2>&1; then
    "${privilege[@]}" apt-get update
    "${privilege[@]}" apt-get install -y "$@"
  else
    fail "No supported package manager (dnf or apt-get). Install manually: $*"
  fi
  hash -r
}

missing=()
for dependency in python3 git; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    missing+=("$dependency")
  fi
done
if ((${#missing[@]})); then
  install_packages "${missing[@]}"
fi
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || fail 'Python 3.11+ is required. Upgrade your distribution Python and retry.'
# Reject a broken or Windows Git wrapper before handing it to the coordinator.
git --version >/dev/null || fail 'Linux Git is not working.'

install_zellij() (
  # Official v0.45.1 release asset SHA-256 digests, pinned at implementation.
  local architecture checksum temporary dependency
  case "$(uname -m)" in
    x86_64)
      architecture=x86_64
      checksum=40bcc2e03f5d5ae8e054e39f676081fe12ab70871506996ba595834c3718eefc
      ;;
    aarch64 | arm64)
      architecture=aarch64
      checksum=05f0802afadd53f8db9514e7cae53c9ae8432fed1b35b8294aa816ee3044a16b
      ;;
    *) fail 'Automatic Zellij installation supports x86_64 and aarch64 Linux.' ;;
  esac
  missing=()
  for dependency in curl tar sha256sum install; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
      case "$dependency" in
        sha256sum | install) missing+=(coreutils) ;;
        *) missing+=("$dependency") ;;
      esac
    fi
  done
  if ((${#missing[@]})); then
    install_packages "${missing[@]}"
  fi
  [[ ! -e "$HOME/.local/bin/zellij" && ! -L "$HOME/.local/bin/zellij" ]] || fail 'Existing ~/.local/bin/zellij is not executable; fix it before retrying.'
  temporary="$(mktemp -d)"
  trap 'rm -rf -- "$temporary"' EXIT
  printf 'Installing Zellij 0.45.1 from its verified upstream release for this user.\n'
  curl --fail --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 10 --max-time 180 \
    "https://github.com/zellij-org/zellij/releases/download/v0.45.1/zellij-$architecture-unknown-linux-musl.tar.gz" \
    --output "$temporary/zellij.tar.gz"
  sha256sum --check <<<"$checksum  $temporary/zellij.tar.gz"
  tar -xzf "$temporary/zellij.tar.gz" -C "$temporary" zellij
  mkdir -p -- "$HOME/.local/bin"
  install -m 755 "$temporary/zellij" "$HOME/.local/bin/zellij"
)
if ! command -v zellij >/dev/null 2>&1; then
  install_zellij
  hash -r
fi

agent_clis="$(python3 -I -B - "$logout_root/agent-team" "$TEAM_CONFIG" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import teamcfg
config = teamcfg.load(sys.argv[2])
print('\n'.join(sorted({role['cli'] for role in config['roles'].values()})))
PY
)"
while IFS= read -r cli; do
  if command -v "$cli" >/dev/null 2>&1; then
    continue
  fi
  if ! command -v npm >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
    install_packages nodejs npm
  fi
  case "$cli" in
    codex) package=@openai/codex ;;
    claude) package=@anthropic-ai/claude-code ;;
    *) fail "Unsupported agent CLI: $cli" ;;
  esac
  printf 'Installing missing agent CLI for this user: %s\n' "$cli"
  npm install --global --prefix "$HOME/.local" "$package"
  hash -r
  command -v "$cli" >/dev/null 2>&1 || fail "Installation did not provide $cli on PATH."
done <<< "$agent_clis"

for dependency in python3 git zellij; do
  command -v "$dependency" >/dev/null 2>&1 || fail "Installation did not provide $dependency on PATH."
done
cd -- "$project_root"
exec "$logout_root/agent-team/bin/team-up" "$@"
