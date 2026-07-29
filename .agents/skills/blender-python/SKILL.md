---
name: blender-python
description: Build, refactor, test, and troubleshoot Blender Python scripts, add-ons, extensions, and background automation. Use for bpy data and operators, registration, properties, panels, handlers, timers, dependency graph evaluation, scene and collection management, import/export, Blender command-line jobs, or API context errors. Use qt-python only when a project deliberately embeds an external Qt interface; Blender's native UI uses bpy types.
---

# Blender Python

## Establish context

1. Identify the Blender version, bundled Python, add-on or extension format,
   execution mode, enabled dependencies, and target platforms.
2. Inspect `bl_info` or extension metadata, registration functions, operators,
   panels, properties, handlers, timers, preferences, and tests.
3. Determine whether the task should use the data API, an operator, evaluated
   dependency graph data, BMesh, or a command-line workflow.
4. Read `references/docs-map.md` for the exact Blender API version.

## Implement safely

- Prefer direct `bpy.data` and RNA access for deterministic automation. Use
  `bpy.ops` when operator behavior, undo, or user interaction is required.
- Before calling an operator, verify its mode, area, region, active object,
  selection, and context requirements. Use a context override narrowly.
- Keep `register()` and `unregister()` symmetric and safe across enable,
  disable, reload, and startup.
- Store add-on state in registered properties or preferences rather than module
  globals when it must survive redraws or file changes.
- Preserve active object, selection, mode, frame, and modified file state when
  a tool temporarily changes them.
- Handle data-block users, linking, collections, evaluated versus original
  objects, and deletion explicitly.
- Remove handlers, timers, draw callbacks, and message-bus subscriptions during
  unregister.

## Responsiveness and headless use

- Keep Blender data and UI access on the main thread. Use timers or modal
  operators to schedule main-thread work.
- Keep background workers limited to isolated computation or I/O and marshal
  results back safely.
- Use `blender --background --python <script>` for headless integration checks
  and avoid APIs that require areas, regions, or windows there.

## Validate

1. Unit-test pure Python logic outside Blender.
2. Enable, disable, and reload the add-on repeatedly without duplicate classes
   or callbacks.
3. Test representative `.blend` fixture copies in interactive and background
   modes.
4. Exercise no selection, multiple selection, wrong mode, linked data,
   overrides, missing dependencies, undo/redo, save/reload, and version upgrade.
5. Confirm temporary objects, handlers, timers, properties, and registrations
   are cleaned up after exceptions.

## Guardrails

- Work on copies of valuable `.blend` files during destructive tests.
- Do not save, overwrite, purge orphan data, apply modifiers, convert objects,
  or alter linked libraries without explicit authorization.
- Do not use Python threads for Blender API access.
- Do not add Qt to a Blender tool when native Blender UI types satisfy the
  requirement.
