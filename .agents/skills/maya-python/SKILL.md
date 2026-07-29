---
name: maya-python
description: Build, refactor, test, and troubleshoot Autodesk Maya Python tools and pipeline integrations. Use for maya.cmds, maya.api.OpenMaya API 2.0, DAG and dependency graph work, scene and reference management, import/export, callbacks, plug-in commands, mayapy, Maya batch, workspaceControl docking, or Maya PySide6 tools. Use qt-python for shared Qt architecture and binding concerns.
---

# Maya Python

## Establish context

1. Identify the Maya release, bundled Python and PySide versions, execution
   mode, loaded plugins, workspace, and scene format.
2. Inspect existing package paths, startup hooks, shelves, modules, callbacks,
   tests, and host adapter patterns.
3. Choose the lowest-level API justified by the task:
   - `maya.cmds` for ordinary scene and UI operations.
   - `maya.api.OpenMaya` for performance, iterators, data access, or plug-ins.
   - Existing PyMEL only when the repository already depends on it.
4. Read `references/docs-map.md` for version-specific APIs.

## Implement safely

- Separate pure Python logic from the Maya adapter so most behavior can be
  tested outside the host.
- Resolve DAG paths, namespaces, references, instancing, and duplicate short
  names explicitly. Do not assume a short node name is unique.
- Preserve selection, current time, active tool, namespace, evaluation mode,
  and modified scene state when the tool temporarily changes them.
- Group user-visible scene edits into an undo chunk with `try/finally`.
- Prefer API 2.0 consistently within a code path; do not interchange API 1.0
  and API 2.0 wrapper objects.
- Track callback IDs and remove them during unload or tool teardown.
- Keep file operations explicit about references, namespaces, load depth, file
  type, overwrite behavior, and whether the current scene is modified.

## UI and execution

- Use `qt-python` for widget design, threading, models, and binding behavior.
- Parent PySide widgets to Maya's main window, retain modeless instances, give
  them stable object names, and use `workspaceControl` for dockable tools.
- Reuse Maya's application and event loop; never create another application.
- Use `mayapy` or Maya batch for non-UI integration checks and interactive Maya
  for UI, viewport, selection, and callback behavior.

## Validate

1. Test pure logic with ordinary Python.
2. Run focused host tests in the same Maya version as production.
3. Exercise empty scenes, namespaces, references, instanced DAG paths, locked
   nodes, unloaded plugins, undo/redo, repeated tool reload, and scene close.
4. Verify batch behavior separately from interactive behavior.
5. Confirm that callbacks, widgets, temporary nodes, and undo chunks are
   cleaned up after failures.

## Guardrails

- Work on copies of valuable `.ma` and `.mb` files during destructive tests.
- Do not force-open, force-save, import, reference, delete, or rename scene
  content without explicit task authorization.
- Do not install packages into Maya's interpreter without confirming its Python
  ABI and deployment policy.
- Do not mutate Maya scene or UI state from a background thread.
