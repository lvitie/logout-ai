# Test first: write the failing test before the change
## When to use
- A code change with testable behavior: game rules, systems, tools, pipelines, bug fixes with a reproducible case.
- Not for: test plans, regression passes and manual QA → `qa-test-planning`.
## Inputs
- The requested behavior or bug repro, the existing test framework and how to run it, the module under change.
## Method
1. Write or extend a test that fails for the requested behavior; run it and confirm it fails for the right reason.
2. Make the smallest change that passes, then run the affected tests and the full suite once before finishing.
3. Keep tests deterministic: fixed seeds, fixed time step, no dependency on frame rate or wall clock.
## Checks
- The new test failed before and passes after; the full suite passes once at the end.
- Report the test names added and the before/after result.
## Pitfalls
- Tests that need a full map load or the editor when a unit test of the logic would do.
- Flaky tests from timing, async loading or random spawns; marking them skipped instead of fixing.
## Engine notes
- Unreal: Automation tests (`IMPLEMENT_SIMPLE_AUTOMATION_TEST`, Automation Spec), Functional Test actors for in-level checks, run headless with `-ExecCmds="Automation RunTests <filter>" -nullrhi -unattended`.
- Unity: Unity Test Framework (EditMode and PlayMode tests), run with `-runTests -batchmode`.
- Godot: GUT or GdUnit4 (third-party add-ons); run headless with `--headless`.
