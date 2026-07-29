---
name: 3dsmax-python
description: Build, refactor, test, and troubleshoot Autodesk 3ds Max Python tools with pymxs and PySide6. Use for pymxs.runtime, MAXScript interoperability, scene objects and files, materials, modifiers, animation, callbacks, 3ds Max Batch, PythonHost, qtmax docking, or migration from MaxPlus and MAXScript. Use qt-python for shared Qt architecture and binding concerns.
---

# 3ds Max Python

## Establish context

1. Identify the 3ds Max release, bundled Python and PySide versions, renderer,
   loaded plugins, project paths, and interactive versus batch execution.
2. Inspect package layout, startup scripts, menus, macros, callbacks, scene
   fixtures, and any MAXScript interoperability.
3. Prefer `pymxs` for supported 3ds Max Python integration. Preserve existing
   MAXScript only where it exposes behavior unavailable through pymxs.
4. Read `references/docs-map.md` for release-specific behavior.

## Implement safely

- Import `pymxs.runtime` with the project's established alias and keep host
  calls behind a small adapter.
- Remember the MAXScript boundary: some function arguments remain 1-based even
  when wrapped collections expose Python-style indexing.
- Compare pymxs scene wrappers by value or handle semantics, not Python object
  identity.
- Validate node existence, class, handle, references, layers, and instancing
  before mutation. Do not assume names are unique or stable.
- Preserve selection, current time, animate state, redraw state, command panel
  mode, and modified scene state when temporarily changing them.
- Group artist-facing changes into the documented undo mechanism and make
  operations that cannot be undone explicit.
- Register callbacks with stable identifiers and remove them during unload.
- Use `runtime.execute()` only for necessary MAXScript commands and keep the
  string boundary narrow and well-quoted.

## UI and execution

- Use `qt-python` for PySide design, models, and worker coordination.
- Reuse 3ds Max's application and main window. Use `qtmax` for supported
  docking and retain modeless widget instances.
- Use `3dsmax -U PythonHost` or `3dsmaxbatch.exe` according to the existing
  automation workflow and license constraints.
- Request viewport redraws intentionally rather than inside tight loops.

## Validate

1. Unit-test pure Python logic outside 3ds Max.
2. Run host integration tests against copied `.max` fixtures.
3. Exercise duplicate names, instancing, XRefs, missing plugins, materials,
   undo/redo, repeated reload, scene reset, and batch execution.
4. Test interactive UIs for repeated open/close, docking, Max shutdown, and
   callback cleanup.
5. Confirm no temporary nodes, globals, callbacks, redraw suppression, or undo
   state survives a failure.

## Guardrails

- Work on copies of valuable `.max` scenes.
- Do not force-open, save, reset, merge, delete, collapse modifiers, or convert
  objects without explicit authorization.
- Do not install binary packages into the bundled interpreter without matching
  its Python ABI.
- Do not create another Qt application or mutate 3ds Max state from a worker
  thread.
