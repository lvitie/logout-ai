# Optimization
## When to use
- The task asks for a performance or memory improvement, or fixes a budget regression (frame time, memory, load time, hitches, bandwidth).
- Not for: measuring only → `perf-capture`; streaming and memory architecture → `engine-core-streaming`.
## Inputs
- The named metric and budget, the scenario (map, camera path, save, player count), target hardware and build config, any earlier captures in task folders.
## Method
1. Capture a baseline first with the perf-capture steps: same scenario, build and hardware; record the command and the numbers.
2. Find the bound: game thread, render thread, GPU, memory, IO or network; attribute the cost to a system before touching code.
3. Touch only the hot path the request names; no drive-by cleanups or speculative changes.
4. Prefer doing less work (culling, LOD, caching, lower tick rate, batching) over micro-optimizing the same work.
5. After the change capture the same scenario again and record before and after.
## Checks
- Before and after numbers from the same scenario, build and hardware, with the capture files saved.
- No visual, gameplay or network behavior change unless the task accepts it; list any accepted quality loss.
- Drop any change that shows no measurable gain, and say so in the report.
## Pitfalls
- Profiling an editor or debug build and optimizing editor-only cost.
- Moving cost to another thread or frame (hitches) and calling it a gain.
- Averages hiding spikes: report percentiles or worst frames too.
## Engine notes
- Unreal: Unreal Insights (CPU, GPU, memory, loading traces), `stat unit`/`stat gpu`, `ProfileGPU`, significance manager and tick intervals, Nanite/Lumen scalability settings; measure in Development or Test builds, not the editor.
- Unity: Profiler and Profile Analyzer, Frame Debugger, Memory Profiler; Burst and Jobs for hot loops.
- Godot: built-in profiler and visual profiler, Monitors tab; RenderingServer stats.
