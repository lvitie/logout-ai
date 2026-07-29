---
name: unreal-cpp
description: Design, implement, debug, and validate Unreal Engine 5.8 C++ projects and plugins. Use for UnrealBuildTool and UnrealHeaderTool issues, modules, Build.cs and Target.cs files, UObject reflection, gameplay framework code, replication, Slate editor tools, native plugins, automation tests, packaging failures, Live Coding problems, or engine-source API questions. Do not use for Material Graph or shader work; use unreal-materials instead.
---

# Unreal C++

## Establish context

1. Read project instructions and identify the exact engine version.
2. Locate the `.uproject` or `.uplugin`, relevant modules, `Build.cs`,
   `Target.cs`, and nearby callers.
3. Determine whether the change is runtime, editor-only, developer-only, or
   platform-specific.
4. Check whether the project uses an installed engine or source build and
   reuse its established build commands.
5. Read `references/docs-map.md` for version-sensitive Unreal guidance.

## Implement

- Keep public headers in `Public/` and implementation details in `Private/`.
  Add a public dependency only when its types appear in a public interface.
- Treat `Build.cs`, `Target.cs`, `.uproject`, and `.uplugin` files as part of
  the implementation. Do not fix missing dependencies with incidental includes.
- Follow the repository's Unreal reflection patterns. Keep the generated header
  include last and pair reflected declarations with the appropriate
  `UCLASS`, `USTRUCT`, `UENUM`, `UPROPERTY`, or `UFUNCTION` metadata.
- Respect UObject ownership, garbage collection, actor/component lifecycles,
  world availability, and editor/runtime boundaries.
- For networked code, state authority, ownership, replication conditions, RPC
  direction, and client prediction implications before changing behavior.
- Prefer existing engine and project abstractions over parallel systems.
  Confirm uncertain APIs in the matching engine source or 5.8 API reference.
- Keep editor modules and editor-only dependencies out of runtime and shipping
  targets.

## Build and validate

1. Build the smallest affected target and configuration with UnrealBuildTool.
2. Read the first complete compiler, linker, UHT, or UBT error before editing.
3. Run relevant native automation, low-level, functional, or editor tests.
4. Start the editor or commandlet when module loading, reflection, asset
   serialization, or runtime lifecycle behavior is involved.
5. Verify PIE, standalone, dedicated server, packaged, or target-platform
   behavior when the change depends on that execution mode.
6. Report the exact target, platform, configuration, tests, and remaining
   warnings.

## Guardrails

- Do not edit generated project files, `Intermediate/`, generated headers, or
  engine build products.
- Do not delete caches or regenerate every project file as a first response to
  a compile failure.
- Do not rely on Live Coding for reflected header, constructor layout, module,
  or serialization changes; perform a clean editor restart and normal build.
- Preserve unsaved editor work. Use `unreal-mcp-workflow` only when live editor
  inspection or asset mutation is required.
- Ask before changing engine source, public plugin APIs, serialization formats,
  replication contracts, or project-wide build settings.
