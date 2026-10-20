# Build, CI and release management
## When to use
- Build scripts, cook and packaging, CI jobs, build farm, versioning, branching and release checklists, patches and hotfixes, symbol storage and crash reporting setup.
- Not for: platform certification rules → `platform-cert`; editor tools → `tools-pipeline`.
## Inputs
- Target platforms and configs (Development, Test, Shipping), branch strategy, version scheme, CI system, signing requirements (never the secrets), release calendar.
## Method
1. Builds are slow and shared: reuse an existing valid build, run long jobs detached and wait in a bounded loop.
2. Keep configuration reproducible (pinned tool and SDK versions, no machine-local paths); never touch credentials or signing secrets.
3. Pipeline stages: compile, cook, package, smoke test, upload; fail fast with the first error surfaced.
4. Version every build (changelist or commit plus build number) and stamp it in the binary and crash reports; archive symbols.
5. Release: release-candidate branch, code freeze rules, go/no-go checklist (cert, ratings, store assets, known issues), rollback plan.
6. Patches: keep patch size within platform limits; verify delta patching from the previous live build.
## Checks
- Report the exact command, the target, the result and where the logs are.
- Clean build from a fresh workspace succeeds; incremental build matches.
- Smoke test boots to menu and into one level on each target; crash reporter receives a test crash with symbols.
- Release checklist items have evidence (links to cert reports, rating certificates, store build IDs).
## Pitfalls
- Shipping a build with development cheats, logging or debug console enabled.
- Cooked content out of sync with code (stale derived data); patch built against the wrong baseline.
- Secrets in CI logs or scripts.
## Engine notes
- Unreal: UAT `RunUAT BuildCookRun`, BuildGraph scripts, Unreal Build Tool, Zen/DDC shared cache, Horde for build distribution, pak/IoStore chunking and patch release versions (`-createreleaseversion`, `-basedonreleaseversion`), CrashReportClient with symbols.
- Unity: BuildPipeline / Build Profiles, batch mode builds, Unity Build Automation or any CI, Addressables content builds and update restrictions.
- Godot: export presets and `--export-release` headless, export templates per platform, PCK patches.
