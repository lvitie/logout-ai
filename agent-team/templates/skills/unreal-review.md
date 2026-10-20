# Unreal review checklist
## When to use
- Reviewing or self-checking C++, Blueprint or asset changes in an Unreal project before handoff.
- Not for: performance work → `optimization`; certification rules → `platform-cert`.
## Inputs
- The change (diff or changelist), the modules and assets touched, the target platforms and build configs.
## Method
1. Blueprint/C++ boundary: UPROPERTY/UFUNCTION specifiers, replication, and garbage-collection safety (raw UObject pointers; use `TObjectPtr`, `TWeakObjectPtr` or `UPROPERTY`).
2. Asset hygiene: no binary assets edited outside the task's change; naming prefixes (BP_, M_, SK_, SM_) and redirectors fixed up.
3. Hot paths: no per-tick allocations, heavy casts or hard asset references; check for ticking actors that need not tick.
4. Build: headers compile with the module's includes, no editor-only code in runtime modules (`WITH_EDITOR` guards, editor modules split).
5. References: soft references for large or optional assets; check the Reference Viewer and Size Map for new hard chains.
## Checks
- Compiles in Development Editor and a non-editor config (Development or Shipping) for one target platform.
- Data Validation passes on touched assets; no new warnings in the cook log.
- Blueprint changes compile without warnings; no circular Blueprint dependencies.
## Pitfalls
- Constructor logic that depends on world state (runs on the CDO).
- `GetWorld()` or subsystem access during load or on the CDO; missing `Super::` calls in overrides.
- Unity build hiding missing includes (check with non-unity or IWYU builds).
## Engine notes
- Unreal first; for Unity review the equivalent: serialized field changes, `Update()` allocations, Addressables references, asmdef boundaries, editor code under `Editor/` folders.
- Godot: signal connections, `@export` changes, autoload dependencies, `.tscn` merge conflicts.
