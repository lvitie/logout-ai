# Rendering and graphics programming
## When to use
- Render pipeline features, passes, lighting and shadow tech, post-processing, LOD and culling systems, GPU memory, scalability settings, graphics API and driver issues.
- Not for: shader code cost of one material → `shaders`; artist lighting of a scene → `lighting-cinematics`; material authoring → `material-authoring`.
## Inputs
- GPU budget per platform and quality tier, captures (GPU profiler, RenderDoc/PIX), the pipeline configuration, target resolutions and upscaler.
## Method
1. Capture a GPU frame on the target hardware and attribute cost per pass before changing anything.
2. Prefer engine scalability settings and existing features over custom passes; custom passes go in a plugin.
3. Define the feature per quality tier (low to epic) and per platform; document the cvars or settings.
4. Check GPU memory: render targets, virtual texture pools, shadow maps; record before and after.
5. Validate on each graphics API the project ships (DX12, Vulkan, Metal, console).
## Checks
- GPU time per pass before and after on the lowest and highest tier; no visual regression in a reference capture set.
- Works with the shipping upscaler/anti-aliasing and at minimum and maximum resolution.
- No GPU validation-layer errors; no new PSO hitches (pipeline state cache updated).
## Pitfalls
- Optimizing on a high-end GPU only; console and min-spec behave differently.
- PSO compilation hitches on first use in packaged builds.
- Temporal artifacts (ghosting, disocclusion) missed in still screenshots; check motion.
## Engine notes
- Unreal: Nanite, Lumen, Virtual Shadow Maps, TSR, scalability groups (`sg.*`), Render Dependency Graph (RDG) for custom passes, `ProfileGPU`, `stat GPU`, Unreal Insights GPU track, PSO precaching and bundled PSO cache.
- Unity: URP/HDRP with Scriptable Render Features or Custom Passes, SRP Batcher, Frame Debugger, GPU Resident Drawer (Unity 6).
- Godot: Forward+, Mobile and Compatibility renderers; RenderingDevice for custom compute; CompositorEffect for custom passes (4.3+).
