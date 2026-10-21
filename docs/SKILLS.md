# Skills

## Purpose

A skill is a reusable workflow with focused instructions, optional references,
and optional scripts.

Use a skill for knowledge that is:

- reused across repositories
- independent of one project's requirements
- specific enough to have a reliable trigger
- too detailed for global or repository instructions

## Discovery locations

Use the current documented locations:

```text
repository/.agents/skills/<skill-name>/SKILL.md
~/.agents/skills/<skill-name>/SKILL.md
```

Codex scans repository skill directories from the working directory up to the
repository root. The installer links this repository's skills into the user
location so they are available in other repositories.

## Required layout

```text
.agents/skills/skill-name/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
└── scripts/
```

Only `SKILL.md` is required. It must start with YAML front matter containing a
clear `name` and `description`.

## Authoring rules

- Keep each skill focused on one workflow.
- Put trigger terms and boundaries in the description.
- Write imperative steps with explicit inputs, outputs, and validation.
- Load references only when the task needs them.
- Prefer instructions over scripts unless deterministic automation is useful.
- Keep project requirements in project documentation, not reusable skills.
- Use `agents/openai.yaml` only for useful UI metadata or dependencies.

## Repository skills

Skills for your own Codex session, under `.agents/skills/` and linked into `~/.agents/skills/` by the installer
(Claude Code does not read that folder; the coordinator passes `team-setup` to either CLI by path):

- `3dsmax-python`: 3ds Max tools with pymxs and PySide6
- `ai-project-manager`: planning documents, phased plans, approval checkpoints and task status
- `bash-scripting`: Bash and POSIX sh scripts: portability, quoting, failure handling
- `blender-python`: Blender Python scripts, add-ons, extensions and background automation
- `go-web`: Go web servers and HTTP APIs on net/http
- `graphify`: persistent Graphify knowledge graphs of code, documents and media
- `homelab-admin`: homelab networking, DNS, storage, NFS and reverse proxies
- `houdini-python`: Houdini Python tools with the Houdini Object Model
- `htmx`: server-driven web interfaces with HTMX 2.x and HTML templates
- `linux-sysadmin`: Linux hosts, services, packages, permissions, SELinux, firewalls and SSH
- `maya-python`: Maya Python tools and pipeline integrations
- `mdbook`: mdBook projects and mdBook-based KDP manuscripts
- `podman-operator`: Podman containers and Quadlet services, rootless deployment
- `pr-readiness`: changes and pull requests through merge readiness: local gates, Codex review, CI
- `project-bootstrap`: seed a project with instructions, planning documents and the matching skills
- `python-ai`: Python AI applications: model APIs, local LLMs, retrieval, tools and agents
- `qt-cpp`: native C++ applications and libraries with Qt 6
- `qt-python`: Python UIs with PySide or PyQt, Qt Widgets and QML
- `rust-cli`: Rust command-line applications with Cargo and clap
- `rust-web`: Rust web servers and HTTP APIs
- `substance-designer-python`: Substance 3D Designer plugins and graph automation
- `substance-painter-python`: Substance 3D Painter plugins and pipeline automation
- `team-setup`: tailor the agent team (`team.toml`, agents, skills, locks) to a project
- `unreal-cpp`: Unreal Engine 5.8 C++ projects and plugins
- `unreal-materials`: Unreal Engine 5.8 materials and shaders
- `unreal-mcp-workflow`: a running Unreal Engine 5.8 editor through Epic's Unreal MCP server

Run `./scripts/validate.sh` after adding or changing a skill. Validation fails
when this list and the skill directories drift apart.

## Agent team skills

The agent team (`agent-team/`, see `docs/AGENT_TEAM.md`) has its own skills: plain Markdown files whose text or path
goes into an agent's prompt. Its Claude agents skip the user's skills (`--disable-slash-commands`) unless
`[agents] user_skills = true`; its Codex agents can still discover `~/.agents/skills` on their own.

- **Task skills**: `<templates_dir>/skills/<name>.md`, falling back to the 41 bundled game-dev skills in
  `agent-team/templates/skills/`. They are attached to one task with `team new --skill name[@stage]` or by the
  Producer's `SKILLS:` line, and inlined into that task's matching stages. `agent-team/templates/skills/INDEX.md` maps
  each one to its roles and agents. See "Task skills" in `docs/AGENT_TEAM.md`.
- **Agent skills**: `skill: <name> | <path> | <when>` lines in an agent file's frontmatter. The agent gets a
  `## Skills you have` table and reads a file only when it applies. See "Agent skills" in `docs/AGENT_TEAM.md`.

### Task skills

The bundled task skills, with the title the Producer sees:

- `accessibility`: Accessibility
- `ai-behavior`: AI behavior and navigation
- `analytics-data`: Analytics and telemetry
- `animation`: Animation: rigs, clips, state machines and animation code
- `anti-cheat-security`: Anti-cheat and game security
- `audio-implementation`: Audio implementation and audio programming
- `balancing`: Balancing: systems, economy and tuning
- `blender-animation`: Blender animation: slotted actions, F-curves, NLA, baking, root motion and clip export
- `blender-geometry-nodes`: Blender geometry nodes: procedural assets, scatter, simulation zones and bakes for engines
- `blender-rigging`: Blender rigging: armatures, constraints, drivers, weights, shape keys and game-skeleton export
- `blender-vfx`: Blender VFX: Mantaflow, particles, physics sims, renders and caches for game engines
- `build-ci-release`: Build, CI and release management
- `character-art-pipeline`: Character art pipeline (concept to in-engine)
- `combat-design`: Combat design
- `engine-core-streaming`: Engine core, memory and streaming
- `environment-props`: Environment and prop art
- `gameplay-systems`: Gameplay systems programming
- `legal-ratings`: Legal, compliance and age ratings
- `level-design`: Level, encounter and world design
- `lighting-cinematics`: Lighting, cinematics and camera
- `live-ops-progression`: Progression, live ops and community
- `localization`: Localization and internationalization
- `material-authoring`: Material authoring
- `narrative-dialogue`: Narrative, quests and dialogue
- `netcode`: Netcode and replication
- `online-backend`: Online services and backend
- `optimization`: Optimization
- `perf-capture`: Performance: measure and record only
- `physics`: Physics and collision
- `platform-cert`: Platform certification and compliance
- `production-scheduling`: Production and scheduling
- `qa-test-planning`: QA and test planning
- `rendering`: Rendering and graphics programming
- `shaders`: Shaders and render cost
- `sound-music`: Sound design, music and VO content
- `tdd`: Test first: write the failing test before the change
- `tools-pipeline`: Tools and content pipeline
- `ui-programming-input`: UI programming and input
- `unreal-review`: Unreal review checklist
- `ux-ui-design`: UX and UI design and UI art
- `vfx`: Visual effects

### Overlap

Where the two kinds overlap, the repository skill is for scripting the tool in your own session and the task skill is
for an agent doing that kind of work in a pipeline. For example, `blender-python` scripts Blender, while the
`blender-*` task skills cover rigging, animation, geometry nodes and VFX work (research in `docs/BLENDER_SKILLS.md`).
Likewise, `unreal-materials` sits next to the `material-authoring` and `shaders` task skills (research in
`docs/GAME_DEV_ROLES.md`).

To add a task skill, follow the section layout in `INDEX.md`, add its row there and to the agents that should list it,
add it to the list above, then run `./scripts/validate.sh` (it fails when the list and `agent-team/templates/skills/`
drift apart) and `python3 -I -B -m unittest discover agent-team/tests` (`test_skill_library.py` checks the index
against the agent files).
