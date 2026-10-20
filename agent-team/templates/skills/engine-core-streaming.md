# Engine core, memory and streaming
## When to use
- Core engine work: memory management, allocators, threading and task systems, asset loading and streaming, file IO, platform abstraction, startup and load times.
- Not for: drawing and GPU passes → `rendering`; hot-path tuning of one system → `optimization`; replication → `netcode`.
## Inputs
- Memory and load-time budgets per platform, current captures, the module boundaries, asset reference graph, threading model.
## Method
1. State the invariant: ownership, lifetime and which thread may touch the data; write it in a code comment where it is not obvious.
2. Memory: tag allocations by category; set per-platform budgets; find the largest categories before changing allocators.
3. Streaming: convert hard references to soft ones for optional or large content; load asynchronously with priorities; define what must be resident.
4. Threading: use the engine task system; avoid locks on hot paths; no game-object access off the game thread unless the engine documents it safe.
5. Keep changes minimal and reversible; engine-source edits only when no plugin or project-level hook works.
## Checks
- Memory report before and after on the lowest-memory target platform; no new leaks over a long soak (level transitions repeated).
- Load and streaming: no hitch over the frame budget on the critical path; worst-case IO tested from slow storage if shipped there.
- Thread sanitizer or engine race checks clean where available; no deadlock under stress.
## Pitfalls
- Synchronous loads on the game thread (flush async loading) hidden inside convenience calls.
- Fragmentation on long sessions; budgets checked only after a fresh boot.
- Engine modifications that block engine upgrades; record every engine-source diff.
## Engine notes
- Unreal: Asset Manager and Primary Asset IDs, `TSoftObjectPtr` with `FStreamableManager`, World Partition streaming, IoStore/Zen loader, Low Level Memory tracker (`-llm`), Memory Insights, `memreport`, Tasks System (`UE::Tasks`), chunking with Primary Asset Labels.
- Unity: Addressables (async load, release), Memory Profiler, Jobs and Burst, `Resources` folder avoided for large content.
- Godot: `ResourceLoader.load_threaded_request`, background loading, `WorkerThreadPool`, PCK packs for chunks.
