---
name: houdini-python
description: Build, refactor, test, and troubleshoot SideFX Houdini Python tools using the Houdini Object Model. Use for hou APIs, node networks, parameters, HDAs, shelf tools, Python states and panels, callbacks, Solaris and USD workflows, hython or hbatch automation, cooking, file paths, or Houdini PySide6 interfaces. Use qt-python for shared Qt architecture and binding concerns.
---

# Houdini Python

## Establish context

1. Identify the Houdini build, edition, bundled Python and Qt versions,
   `HOUDINI_PATH`, package configuration, license requirements, and whether the
   task runs in the UI, `hython`, or batch.
2. Locate the HIP file, HDA definitions, node type libraries, scripts, packages,
   startup hooks, callbacks, and existing tests.
3. Identify the network context such as OBJ, SOP, DOP, LOP, TOP, or COP and
   distinguish authored definitions from instances.
4. Read `references/docs-map.md` before using version-sensitive HOM APIs.

## Implement safely

- Separate pure pipeline logic from the `hou` adapter.
- Use explicit node paths and validate node types, categories, editable state,
  locked assets, and parameter existence before mutation.
- Group interactive changes with `hou.undos.group()` and keep non-undoable
  operations explicit.
- Preserve selection, current node, pane, frame, take, desktop, and modified
  HIP state when temporarily changing them.
- Edit HDA definitions only when the request targets the definition. Avoid
  unintentionally changing every instance.
- Treat cooking as a side effect. Minimize recooks and avoid repeated geometry
  extraction inside Python loops when HOM offers bulk access.
- Keep USD layer ownership and edit targets explicit in Solaris workflows.
- Register and unregister callbacks, viewer states, panels, and event handlers
  symmetrically.

## UI and execution

- Use `qt-python` for PySide architecture, models, and worker coordination.
- Create Houdini panels and widgets on the main application thread and reuse
  the host event loop.
- Use `hython` for deterministic non-UI automation and state when it consumes a
  batch or FX license.
- Do not assume interactive pane or desktop APIs exist in headless execution.

## Validate

1. Test pure Python logic outside Houdini.
2. Run focused `hython` tests against disposable HIP or HDA fixtures.
3. Exercise locked assets, missing nodes, different takes, invalid parameters,
   interrupted cooks, undo/redo, repeated reload, and headless execution.
4. Validate UI and viewer-state behavior interactively.
5. Confirm that generated nodes, callbacks, temporary files, and undo groups
   are cleaned up on both success and failure.

## Guardrails

- Work on copies of valuable HIP and HDA files during destructive tests.
- Ask before saving HIP files, modifying shared HDA libraries, changing package
  files, consuming farm licenses, or launching expensive cooks.
- Do not call Houdini UI or scene APIs from arbitrary background threads.
- Do not alter global `HOUDINI_PATH` or bundled Python packages casually.
