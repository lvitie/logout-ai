---
name: qt-cpp
description: Design, implement, test, package, and troubleshoot native C++ applications and libraries with Qt 6. Use for CMake integration, Qt Widgets, Qt Quick and QML backends, QObject ownership, signals and slots, model/view, resources, plugins, threading, Qt Test, deployment, or Qt 5 to Qt 6 migration. Do not use for Python bindings; use qt-python instead.
---

# Qt C++

## Establish context

1. Identify the Qt, compiler, CMake, C++ standard, platform, and deployment
   targets used by the repository.
2. Inspect `CMakeLists.txt`, linked Qt components, target ownership, resources,
   `.ui` or QML files, and existing tests.
3. Determine whether the UI uses Widgets, Qt Quick, or a hybrid.
4. Read `references/docs-map.md` for version-sensitive Qt behavior.

## Build with modern CMake

- Prefer target-based CMake with `find_package(Qt6 REQUIRED COMPONENTS ...)`,
  `qt_standard_project_setup()`, `qt_add_executable()` or
  `qt_add_library()`, and imported `Qt6::` targets.
- Link dependencies `PRIVATE` unless their Qt types appear in public headers.
- Keep Qt's generated moc, uic, rcc, and QML outputs in the build directory.
- Preserve the project's C++ standard when it satisfies the pinned Qt version;
  Qt 6 requires at least C++17.
- Model optional Qt modules as explicit build options rather than unconditional
  dependencies.

## Implement Qt code

- Use QObject parent ownership for QObject trees and RAII smart pointers for
  non-QObject resources. Avoid double ownership.
- Add `Q_OBJECT` only when meta-object features are required and ensure the
  containing target is processed by automoc.
- Prefer typed signal and slot connections. Make connection lifetime and
  queued versus direct delivery intentional.
- Use model/view abstractions for shared or substantial data instead of
  item-based widgets.
- Keep business logic out of widgets and QML-facing adapter classes.
- Register custom queued-connection and QVariant types deliberately.

## Threading and event loops

- Keep GUI objects on the main thread.
- Move worker QObjects to threads or use the project's selected Qt concurrency
  primitive; do not put work slots on a QThread object that lives elsewhere.
- Define cancellation, shutdown ordering, and ownership before starting work.
- Communicate across threads with queued signals or posted events and protect
  any directly shared state.

## Validate

1. Configure and build the smallest affected CMake target.
2. Run focused Qt Test and CTest targets, including model tests where relevant.
3. Exercise creation, destruction, focus, resize, high DPI, translation, empty
   data, cancellation, and shutdown paths.
4. Run sanitizer or static-analysis configurations already supported by the
   project.
5. Validate platform deployment with the project's packaging workflow and
   inspect missing Qt plugins or runtime libraries on a clean target.

## Guardrails

- Do not mix Qt 5 and Qt 6 libraries or plugins in one process.
- Do not hand-edit generated moc, uic, rcc, or QML cache output.
- Do not block the GUI thread with I/O, process waits, or long computation.
- Ask before changing public ABI, plugin interfaces, deployment layout, or
  application-wide event handling.
