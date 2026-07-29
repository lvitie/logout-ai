# Logout AI tasks

## Current phase: Luca's portable baseline

- [x] Replace upstream names, paths, and backup prefixes with Logout AI
  equivalents.
- [x] Discover trusted Git worktrees beneath `~/Projects` on every platform.
- [x] Remove upstream machine-specific trust entries from portable config.
- [x] Add Codex-native Graphify and Unreal MCP skills.
- [x] Add focused Unreal C++, Unreal materials, Qt C++, and Qt Python skills.
- [x] Add host-specific Python skills for Maya, Houdini, Blender, 3ds Max,
  Substance Painter, and Substance Designer.
- [x] Add Rust and Go web-server skills plus an HTMX frontend skill.
- [x] Run repository, shell, installer, configuration, and skill validation.
- [x] Inspect the final diff for only personal-baseline changes.

## Next phase: Enforced repository governance

- [ ] Configure a default-branch ruleset after CI check names exist remotely.
- [ ] Require pull requests, successful validation, and conversation resolution.
- [ ] Require an independent approval when repository ownership permits it.

## Completion rule

Move current-phase tasks to completed only after their acceptance criteria and
required validation pass. Keep external GitHub settings pending until verified
through the live repository.
