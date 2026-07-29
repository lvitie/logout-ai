---
name: substance-designer-python
description: Build, refactor, test, and troubleshoot Adobe Substance 3D Designer Python plugins and graph automation. Use for Designer's Python API, application context, packages, graphs, nodes, properties, resources, callbacks, undo and redo, Explorer actions, QtForPython UI, SBS and SBSAR publishing, or Substance Automation Toolkit workflows. Use qt-python for shared PySide interface architecture.
---

# Substance Designer Python

## Establish context

1. Identify the Designer release, bundled Python and Qt versions, platform,
   color management, package format, plugin search path, and whether Automation
   Toolkit command-line tools are involved.
2. Inspect plugin metadata, lifecycle hooks, application context, package and
   graph access, callbacks, UI actions, logging, and tests.
3. Distinguish in-application graph editing from headless cooking or rendering.
4. Read `references/docs-map.md` and the matching in-application scripting
   reference before version-sensitive API work.

## Implement safely

- Keep naming, path, preset, and publishing logic independent from Designer's
  API where possible.
- Resolve packages, graphs, resources, nodes, properties, connectors, and
  selections explicitly. Do not depend on display labels when stable
  identifiers are available.
- Group user-facing graph mutations into Designer's undo mechanism and keep
  operations that cannot be undone explicit.
- Preserve the active package, graph, selection, Explorer state, and modified
  documents when temporarily changing them.
- Maintain graph type, node definition, property category, connection type,
  inheritance, and exposed parameter contracts.
- Separate authoring `.sbs` files from cooked `.sbsar` outputs and make publish
  destinations and overwrite policy explicit.
- Register application callbacks, Explorer actions, menus, and UI objects once
  and remove them during plugin teardown.

## UI and automation

- Use `qt-python` for QtForPython ownership, models, signals, and workers.
- Reuse Designer's application and event loop. Keep Designer API and UI calls
  on the main thread.
- Use Automation Toolkit tools only when the repository or request calls for
  headless cooking or rendering; record versions and license assumptions.
- Keep plugins reloadable without duplicate callbacks, actions, or widgets.

## Validate

1. Unit-test pure configuration, naming, and publishing logic.
2. Load, unload, and reload the plugin repeatedly in the target Designer build.
3. Test empty selections, missing definitions, read-only packages, graph
   variants, exposed parameters, undo/redo, invalid outputs, and cancel paths.
4. Cook representative `.sbsar` outputs and verify parameters, dependencies,
   output usage, bit depth, color space, and target-engine behavior.
5. Confirm temporary packages, callbacks, actions, and widgets are cleaned up.

## Guardrails

- Work on copies of valuable `.sbs` packages during destructive tests.
- Ask before editing shared packages, changing exposed interfaces, publishing
  over existing `.sbsar` files, or launching expensive batch cooks.
- Do not assume Painter's `substance_painter` API exists in Designer.
- Do not replace Designer's bundled QtForPython installation.
