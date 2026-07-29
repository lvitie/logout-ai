---
name: substance-painter-python
description: Build, refactor, test, and troubleshoot Adobe Substance 3D Painter Python plugins and pipeline automation. Use for the substance_painter API, plugin lifecycle, projects, texture sets, layer stacks, resources, baking, importing, exporting textures, events, UI extensions, remote control, or Painter-to-DCC integrations. Use qt-python for shared PySide interface architecture.
---

# Substance Painter Python

## Establish context

1. Identify the Painter release, bundled Python and Qt versions, platform,
   project template, color management, renderer workflow, and plugin location.
2. Inspect the plugin entry points, registration and teardown, event
   subscriptions, UI objects, resources, export presets, and existing tests.
3. Distinguish an in-process Python plugin from remote-control automation and
   preserve the repository's chosen model.
4. Read `references/docs-map.md` for the matching Painter API.

## Implement safely

- Keep core naming, path, manifest, and export logic independent from
  `substance_painter` so it can be unit-tested normally.
- Check that a project is open and that required texture sets, stacks,
  channels, resources, and selections exist before accessing them.
- Treat resource identifiers, usages, versions, and shelf locations as stable
  contracts; do not rely on display labels alone.
- Keep export configuration explicit about texture sets, stacks, UDIMs, color
  spaces, bit depth, file naming, overwrite policy, and output directories.
- Register events, callbacks, actions, menus, and widgets once and remove all
  of them during plugin teardown.
- Keep long operations interruptible where the API permits and surface errors
  in Painter's log with actionable context.
- Preserve the current project, selection, and layer-stack state unless the
  requested operation intentionally changes them.

## UI and execution

- Use `qt-python` for PySide ownership, models, signals, threading, and tests.
- Reuse Painter's Qt application and main window; never create another
  application object or nested event loop.
- Keep Painter project and UI API calls on the main thread. Perform only
  isolated computation or I/O in workers and marshal results back.
- Keep plugin reload idempotent so development reloads do not duplicate menus,
  callbacks, or dock widgets.

## Validate

1. Unit-test pure path, naming, configuration, and manifest logic.
2. Load, unload, and reload the plugin repeatedly in the target Painter version.
3. Test no project, unsaved project, multiple texture sets, UDIMs, missing
   resources, invalid presets, read-only paths, export collisions, and cancel.
4. Validate outputs in the target renderer or engine, including channel
   packing, normals, color space, bit depth, and naming.
5. Confirm teardown removes every event connection and UI object.

## Guardrails

- Work on copies of valuable Painter projects during destructive tests.
- Ask before modifying layer stacks, rebaking, overwriting exports, changing
  project settings, or importing resources into shared shelves.
- Do not assume Designer's Python API is available in Painter.
- Do not install a conflicting Qt binding into Painter's interpreter.
