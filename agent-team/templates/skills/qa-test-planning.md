# QA and test planning
## When to use
- Writing test plans, test cases, smoke and regression suites, bug reports, compatibility and soak testing, automation strategy, playtest coordination.
- Not for: writing unit tests for a code change → `tdd`; platform requirement checks → `platform-cert`.
## Inputs
- Spec and acceptance criteria, change list for the build, risk areas, supported platforms and hardware matrix, previous bug database and regressions.
## Method
1. Reproduce before judging: list steps, expected result, actual result; separate confirmed defects from suspicions.
2. Test plan per feature: scope, risks, test cases (happy path, edge, negative), platforms, entry and exit criteria.
3. Smoke suite for every build (boot, menu, load level, save/load, quit); regression suite for touched areas; full pass at milestones.
4. Bug report: title with area and symptom, build ID, platform, steps, frequency (for example 3/5), expected vs actual, attachments (video, log, crash dump), severity and priority.
5. Automate stable, repetitive checks; keep exploratory testing for new features.
6. Coverage matrix: features x platforms x languages; mark gaps.
## Checks
- Every acceptance criterion maps to at least one test case with a result on the named build.
- Check the edge cases the change touches (save/load, multiplayer or replication, platform, performance) and whether tests or automation cover them.
- Crash and soak runs done for the milestone build; repro rate recorded for every crash.
## Pitfalls
- Bugs without build ID or repro rate; duplicates not linked.
- Testing only in the editor; missing min-spec and long-session tests.
- Automation that is flaky and ignored.
## Engine notes
- Unreal: Session Frontend Automation tab, Functional Tests, Gauntlet for device and soak runs, `-ExecCmds` and `-unattended` for scripted runs, crash reports from CrashReportClient.
- Unity: Unity Test Framework PlayMode tests, Cloud Diagnostics for crash reports.
- Godot: headless test runs with GUT or GdUnit4; `--debug-collisions` and remote debugger for repro.
