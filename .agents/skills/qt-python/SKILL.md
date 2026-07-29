---
name: qt-python
description: Build, refactor, test, and troubleshoot Python user interfaces with PySide6, PySide2, PyQt6, PyQt5, Qt Widgets, Qt Quick, and embedded DCC panels. Use for signals and slots, model/view code, Designer .ui files, QML integration, event loops, QObject lifetime, threading, docking, binding compatibility, pytest-qt, or deployment. Pair with a host-specific Python skill for Maya, Houdini, Blender, 3ds Max, Substance Painter, or Substance Designer integration.
---

# Qt for Python

## Establish the Qt environment

1. Identify the host, Python version, Qt version, binding, and whether the UI is
   standalone or embedded.
2. Reuse the repository's chosen binding and import style. Do not mix PySide
   and PyQt objects in one process.
3. Inspect the application entry point, parent widget, ownership strategy,
   Designer or QML workflow, and existing tests.
4. Read `references/docs-map.md` for current binding and deployment guidance.

## Design and implement

- Create exactly one application object in standalone programs. In a DCC host,
  reuse its application and event loop.
- Use explicit widget parents, stable object names, and retained Python
  references for modeless tools whose lifetime must outlive a function call.
- Keep domain and pipeline logic outside widgets. Put reusable data behind
  models and use `QAbstractItemModel` for non-trivial tables or trees.
- Define signals at class scope and use typed slots where the binding supports
  them. Keep connections one-way and disconnect long-lived global callbacks
  during teardown.
- Choose one `.ui` workflow per project: generate Python code at build time or
  load the file at runtime. Do not combine both accidentally.
- Add a binding compatibility layer only when the project genuinely supports
  multiple bindings; centralize enum, signal, slot, and API differences there.

## Threading and responsiveness

- Keep all QWidget, QWindow, and QML object mutation on the GUI thread.
- Move non-UI work into a worker object or task and return results through
  queued signals.
- Define worker ownership, cancellation, shutdown, and error propagation.
- Never update a DCC scene from a background thread unless that host explicitly
  documents the operation as thread-safe.
- Prefer chunked or deferred main-thread work when host APIs must remain on the
  UI thread.

## Validate

1. Run focused unit tests for models and non-UI logic.
2. Use the project's Qt test harness or `pytest-qt` when already adopted.
3. Exercise creation, repeated opening, closing, reload, cancellation, and host
   shutdown to catch lifetime and callback leaks.
4. Test high DPI, keyboard focus, resizing, empty data, long-running work, and
   error paths relevant to the tool.
5. For standalone applications, validate packaging with the project's existing
   deployment method; use `pyside6-deploy` only when PySide6 is the chosen
   binding.

## Guardrails

- Do not switch between PySide and PyQt without checking licensing, host
  support, generated code, plugins, and binary compatibility.
- Do not install a different Qt binding into a DCC's bundled interpreter unless
  the host vendor supports it.
- Do not start a nested application event loop inside a DCC host.
- Preserve the host's main window ownership and docking conventions by using
  the matching host-specific skill.
