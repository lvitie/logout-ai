# Performance: measure and record only
## When to use
- You need a baseline or after-change measurement, a budget check, or evidence for a performance claim.
- Not for: changing code to gain performance → `optimization` (only when the task says so).
## Inputs
- The metric named in the request (frame time, memory, load time, hitch count, bandwidth), the scenario, build configuration and hardware, and the budget if one exists.
## Method
1. Check task folders and logs for a valid earlier capture with the same build and scenario; reuse it if inputs did not change.
2. Fix the scenario: map, spawn point, camera path or replay, resolution, quality settings, warm-up time, duration.
3. Capture a baseline before the change and a result after, with the same scenario, build and hardware.
4. Record numbers (frame time, memory, load time or the metric named in the request), the capture command and where the raw output is saved in the task folder.
5. Do not optimize unless the request says so; report findings and suspected hotspots as bullets.
## Checks
- Same build config, hardware, settings and scenario for both captures; at least median and worst-case (p95/p99 or max) reported.
- Raw capture files saved in the task folder and named with the build and scenario.
## Pitfalls
- Comparing captures from different builds, drivers or thermal states; first-run shader compile hitches counted as steady state.
- Capturing in the editor when the budget applies to a packaged build.
## Engine notes
- Unreal: `-trace=cpu,gpu,frame,memory,loadtime` with Unreal Insights, `stat unit`, `stat fps`, `memreport -full`, CSV profiler (`-csvprofile`) for automated runs, Gauntlet for repeatable scenarios.
- Unity: Profiler (attach to a Development build), Memory Profiler snapshots, Profile Analyzer for comparisons.
- Godot: Debugger profiler and Monitors; `--print-fps`; export a release build with debug symbols for capture.
