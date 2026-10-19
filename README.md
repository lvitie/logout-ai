# logout-ai

Portable Codex configuration, rules, and reusable skills.

## Install

Preview and install on Linux or macOS:

```bash
./scripts/install.sh --dry-run
./scripts/install.sh
```

On Windows, run the PowerShell installer from the repository root:

```powershell
.\scripts\install.ps1 -DryRun
.\scripts\install.ps1
```

Restart Codex after installation. Existing managed files are backed up under
`~/.codex/backups/`. Credentials, sessions, history, caches, and plugins are
not changed by default.

The installer manages:

- `codex-home/` configuration and rules in `~/.codex/`
- `.agents/skills/` into `~/.agents/skills/`

### Trust projects

Every installation renders `~/.codex/config.toml` with trusted-project entries
for that user's `~/Projects` directory and every Git worktree found recursively
beneath it. This includes repositories inside organization or grouping
subdirectories.

Codex trust entries match exact project roots rather than directory globs, so
the installer discovers each repository instead of relying on a parent or `*`
entry. Rerun the installer after creating or cloning repositories so new
worktrees are added. Common dependency and build directories are skipped during
discovery.

### Install recommended plugins

[Codex plugin](https://learn.chatgpt.com/docs/plugins) installation is opt-in
because plugins can add instructions, hooks, and connections to external
services. Preview or install the repository's selected plugins on Linux or
macOS with:

```bash
./scripts/install.sh --dry-run --plugins
./scripts/install.sh --plugins
```

On Windows:

```powershell
.\scripts\install.ps1 -DryRun -Plugins
.\scripts\install.ps1 -Plugins
```

The selected plugin IDs live in `codex-plugins.txt`. The initial selection is
`superpowers@openai-curated`. Start a new Codex session after installation so
its skills become available. The managed global instructions tell Codex to
skip the full Superpowers methodology for trivial, low-risk edits.

For GitHub-heavy projects, the broader priority order is:

1. **Superpowers plugin** for planning, TDD, debugging, and delivery workflows.
2. **GitHub plugin** for pull requests, issues, reviews, and repository
   operations.
3. **Context7 MCP server** for current framework and dependency documentation.
4. **Playwright or Chrome DevTools MCP server** for frontend testing and
   browser debugging.
5. **Codex Security plugin** for vulnerability analysis and remediation.
6. **Sentry plugin** for production debugging.

Only the entries in `codex-plugins.txt` are installed by `--plugins`. Context7,
Playwright, and Chrome DevTools are
[MCP servers](https://learn.chatgpt.com/docs/extend/mcp) rather than plugins and
require separate configuration. GitHub, Codex Security, and Sentry remain
opt-in until they are added to the manifest because they can require service
authorization or project-specific setup. Plugin directories do not provide
reliable public installation counts, so the ranking is based on fit for this
workflow rather than unverifiable popularity.

## Bootstrap a project

There are two ways to seed a new or existing project:

- Use the setup script when you already know which skills to copy.
- Use `$project-bootstrap` when you want Codex to gather requirements, choose
  the skills, and tailor the new project documents.

Both workflows are additive. They create missing directories and files but do
not overwrite anything already present, including files inside a partially
populated skill directory.

### Direct setup scripts

From a Logout AI clone, preview and then seed a project on Linux or macOS:

```bash
./scripts/setup-project.sh --dry-run /path/to/ProjectName
./scripts/setup-project.sh /path/to/ProjectName
```

On Windows:

```powershell
.\scripts\setup-project.ps1 -TargetPath C:\path\to\ProjectName -DryRun
.\scripts\setup-project.ps1 -TargetPath C:\path\to\ProjectName
```

The default setup adds:

- `AGENTS.md`
- `SPEC.md`
- `ROADMAP.md`
- `TASKS.md`
- `.agents/skills/ai-project-manager/`
- `.agents/skills/project-bootstrap/`

Select additional skills explicitly when the stack is already known:

```bash
./scripts/setup-project.sh --dry-run \
  --skill rust-web --skill htmx /path/to/ProjectName
./scripts/setup-project.sh \
  --skill rust-web --skill htmx /path/to/ProjectName
```

```powershell
.\scripts\setup-project.ps1 `
  -TargetPath C:\path\to\ProjectName `
  -DryRun `
  -Skill rust-web,htmx
.\scripts\setup-project.ps1 `
  -TargetPath C:\path\to\ProjectName `
  -Skill rust-web,htmx
```

The scripts copy the generic planning templates as-is. Use the skill when those
documents should be filled in from the project's actual requirements.

### Guided setup with `$project-bootstrap`

Install this repository first so the skill is available globally, or start
Codex from the Logout AI clone. Then invoke it with whatever context is already
known:

```text
$project-bootstrap create /path/to/ProjectName. It is a Rust Axum service with
PostgreSQL, HTMX, container deployment, and GitHub pull requests.
```

For an undecided stack, let the skill drive the requirements pass:

```text
$project-bootstrap help me seed /path/to/ProjectName and ask me for the stack,
requirements, constraints, and validation commands you need.
```

The skill collects any missing:

- project goal, users, and required behavior
- languages, frameworks, runtimes, tools, and deployment targets
- constraints, non-goals, security, and privacy boundaries
- setup, format, lint, type-check, test, build, run, and manual-test commands

It then:

1. Inspects the target and treats existing files as authoritative.
2. Inventories the available skills and selects only those matching actual
   requirements.
3. Previews the additive setup and reports which files will be preserved.
4. Runs the platform setup script with the selected skills.
5. Adapts only newly created project documents to the gathered requirements.
6. Validates the resulting instructions, skills, links, and documented project
   commands.

When no existing skill covers a required technology or workflow, the skill
creates a focused project-local skill under `.agents/skills/`. Project-specific
knowledge stays in `AGENTS.md`, `SPEC.md`, `ROADMAP.md`, or `TASKS.md` instead
of being turned into a reusable skill.

Project bootstrap does not install dependencies, initialize Git, deploy, or
perform destructive changes unless those actions are requested explicitly.

## Set up the agent team

The agent team (`agent-team/`) runs Claude Code and Codex CLI agents as a small
team inside one of your projects. A Producer routes each request, then plan,
implement, and review stages run one agent at a time, handing off through files.
Agents never commit, push, or submit; you review the result and commit it
yourself. See [docs/AGENT_TEAM.md](docs/AGENT_TEAM.md) for the full reference.

### Requirements

- Python 3.11 or newer and Git. On Windows, Git for Windows also provides the
  Git Bash shell that Claude Code uses.
- `claude`, `codex`, or both.
- `p4` for Perforce projects, with a working client for the project directory.

The setup script installs nothing. The project launcher it writes (`team.sh`
or `team.ps1`) installs whatever is missing the first time you run it.

### 1. Seed the project

On Linux or WSL:

```bash
./scripts/setup-agent-team.sh --dry-run /path/to/project
./scripts/setup-agent-team.sh /path/to/project
```

On Windows:

```powershell
.\scripts\setup-agent-team.ps1 -TargetPath C:\path\to\project -DryRun
.\scripts\setup-agent-team.ps1 -TargetPath C:\path\to\project
```

When it writes a new `team.toml`, setup asks two questions:

- **Agents**: `claude` for Claude Code in every role, `codex` for Codex CLI in
  every role, or `both` for mixed roles where each CLI reviews the other's
  output.
- **Version control**: `git`, where tasks share the working tree, or `p4`,
  where each task gets its own Perforce changelist and agents may not use git.

To skip the questions, pass `--agents claude|codex|both --vcs git|p4` (or
`-Agents` and `-Vcs` on Windows). Without a terminal, setup uses the CLIs found
on `PATH` and detects the VCS: git for a git repository, otherwise `p4` if it
is installed.

Setup is additive and keeps existing files. It writes:

- `team.toml` with the chosen roles and VCS.
- A project launcher: `team.sh` on Linux, `team.ps1` on Windows.
- The `team` and `team-up` commands in `~/.local/bin`, or in the directory
  given with `--bin-dir` / `-BinDir`. Linux gets symlinks. Windows gets
  `team.cmd`, `team-up.cmd`, and a `team` shim for Git Bash, because Windows
  symlinks need extra privileges.
- For a git repository, an entry that keeps the state directory
  (`.agent-team/`) out of git through `.git/info/exclude`. For Perforce, add
  `.agent-team/` to your `P4IGNORE` file yourself.

The agents and the coordinator need the bin directory on `PATH`. On Windows,
setup warns when it is not. To add it for your user:

```powershell
[Environment]::SetEnvironmentVariable('Path', "$HOME\.local\bin;" + [Environment]::GetEnvironmentVariable('Path', 'User'), 'User')
```

### 2. Review `team.toml`

Check the role models and effort levels, `[locks]` for exclusive resources
such as an editor or GPU, and `[probes]` for local services the agents depend
on. For project rules, set `templates_dir` and put them in
`<templates_dir>/roles/common.md`. The commented template documents every
option.

### 3. Sign in to the agent CLIs

Run `claude` and/or `codex` once interactively and sign in. The team uses
those logins and never copies credentials.

### 4. Start the team

```bash
cd /path/to/project
./team.sh                        # install missing dependencies, open the dashboard
./team.sh "add a stamina bar"    # start a task instead
```

```powershell
cd C:\path\to\project
.\team.ps1
.\team.ps1 "add a stamina bar"
```

On Fedora or Debian/Ubuntu, `team.sh` installs missing packages with
`dnf`/`apt-get`. On Windows, `team.ps1` installs Python, Git, and Node.js with
`winget`, including Windows Terminal for the native dashboard. Linux uses
Zellij 0.45.1 from its upstream release, verified against a pinned SHA-256.
Both install missing agent CLIs with npm. If PowerShell refuses to run local scripts, allow them for your user with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### 5. Work with the team

The dashboard (Zellij on Linux, native Windows Terminal panes on Windows) shows usage, focus, the live log, the task list, and an
alerts pane, and has a coordinator chat where you can ask for work in plain
language. Alerts sit at the top right, above tasks and the coordinator. When a task needs you (a gate, a question, a failure) or finishes,
the alerts pane sends a desktop notification and opens an HTML review page with
the reason, the commands for the next step, the summary, plan, diff, and media.
When every slot or lock is busy, a new or approved task is queued instead of
refused, and the alerts pane starts it once capacity frees up. The coordinator
keeps a `team wait` running, so it hears about gates, failures and finished
tasks without polling. The same actions are available as commands from the project directory:

```text
team new "add a stamina bar"     # create a task, route it, run the pipeline
team status [id]                 # all tasks, or one task in detail
team approve <id> ["note"]       # pass a gate, or retry after a failure
team redo <id> "feedback"        # send the work back with feedback
team drop <id> ["note"]          # abandon a task
team review [id ...]             # open the HTML review page
team queue                       # start queued tasks without the dashboard
team wait                        # wait for the next task that needs attention
```

When a task is `done`, review the working-tree diff (git) or the task's
changelist (Perforce), then commit or submit it yourself.

## Use

Start Codex normally to use the default configuration:

```bash
codex
```

Invoke a skill explicitly when needed:

```text
$linux-sysadmin diagnose this service failure
$project-bootstrap seed /path/to/project for its stack and requirements
$python-ai add an Ollama-backed model provider
$rust-cli add a new subcommand
$rust-web add a traced Axum endpoint with graceful shutdown
$go-web add a tested net/http service
$htmx turn this form into a progressively enhanced fragment update
$graphify query how configuration reaches the installer
$maya-python make this exporter namespace-safe
$3dsmax-python migrate this MAXScript tool to pymxs
$qt-python make this PySide panel reload-safe
$unreal-cpp add an editor-only plugin module
$unreal-materials profile this Custom HLSL material
$unreal-mcp-workflow inspect the active Unreal level
```

Codex can also select skills automatically based on their descriptions.

The Graphify skill expects the separately installed `graphify` CLI. Install it
with `uv tool install graphifyy`; the repository installer intentionally does
not install external developer tools. The Unreal workflow similarly expects
Epic's Unreal MCP server to be configured and running in the editor.

Technical-art workflows are split by host: Maya, Houdini, Blender, 3ds Max,
Substance Painter, and Substance Designer each have a dedicated Python skill.
Shared PySide/PyQt behavior lives in `$qt-python`; native Qt 6 development lives
in `$qt-cpp`.

Web workflows are split into Rust and Go server skills plus a backend-neutral
HTMX skill for server-rendered interaction design.

## AI development workflow

The reusable workflow separates planning from pull-request readiness:

- `$ai-project-manager` reads or creates `AGENTS.md`, `SPEC.md`, `ROADMAP.md`,
  and `TASKS.md`, pauses at plan-approval boundaries, and executes one
  reviewable phase at a time.
- `$project-bootstrap` seeds those files additively, selects stack-specific
  skills, and authors missing project-local skill coverage when necessary.
- `$pr-readiness` validates the final diff and selects built-in Codex review
  for uncommitted work, the actual target branch, or a commit. It resolves
  actionable findings, records manual testing, and verifies CI before merge.

Project-document templates live under
`.agents/skills/ai-project-manager/assets/project-docs/`. Adapt them to the
project instead of leaving placeholder requirements.

See [docs/WORKFLOW.md](docs/WORKFLOW.md) for the complete lifecycle.

## Local models

Local model profiles are optional and do not change the default provider.

Ollama:

```bash
ollama pull qwen3-coder
codex --profile ollama
```

llama.cpp:

```bash
llama-server --model /path/to/model.gguf --jinja --port 8080
codex --profile llamacpp
```

Override either profile's model with `--model`:

```bash
codex --profile ollama --model another-model
codex --profile llamacpp --model another-model
```

Local models need reliable structured tool calling for effective Codex use.
The llama.cpp profile expects a Responses-compatible endpoint at
`http://127.0.0.1:8080/v1`.

## Validate

```bash
./scripts/validate.sh
```

The validation includes an isolated Linux or macOS installer integration test.
GitHub Actions also exercises the PowerShell installer on Windows and runs
dependency review for pull requests.

## Repository layout

- `AGENTS.md`: instructions for maintaining this repository
- `SPEC.md`, `ROADMAP.md`, and `TASKS.md`: requirements, phase order, and
  validated task status
- `.agents/skills/`: reusable skills
- `codex-plugins.txt`: opt-in Codex plugin selections
- `codex-home/`: portable global instructions, configuration, profiles, and rules
- `agent-team/`: project-agnostic Claude/Codex agent team coordinator (`team`, `team-up`, TUIs); `examples/` holds a sample config
- `docs/`: reference documentation loaded only when explicitly requested
- `scripts/`: installation, project setup, integration tests, and validation

See [docs/CODEX_LAYOUT.md](docs/CODEX_LAYOUT.md) for detailed discovery and
configuration behavior. See [docs/AGENT_TEAM.md](docs/AGENT_TEAM.md) for the
agent team reference and [Set up the agent team](#set-up-the-agent-team) for
installation.
