# Unreal review checklist
- Blueprint/C++ boundary: UPROPERTY/UFUNCTION specifiers, replication, and garbage-collection safety (raw UObject pointers).
- Asset hygiene: no binary assets edited outside the task's change; naming prefixes (BP_, M_, SK_, SM_) and redirectors.
- Hot paths: no per-tick allocations, heavy casts or hard asset references; check for ticking actors that need not tick.
- Build: headers compile with the module's includes, no editor-only code in runtime modules.
