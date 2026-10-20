# Shaders and render cost
## When to use
- Editing shader code, custom nodes, compute shaders, or material graph cost; shader compile and permutation issues.
- Not for: authoring artist materials → `material-authoring`; render pipeline features, passes and lighting tech → `rendering`.
## Inputs
- Target platform and quality tier, budget (instruction count, samplers, texture memory, GPU ms), the shader or graph files, current permutation count.
## Method
1. Name the target (platform, quality tier) and the budget (instruction count, samplers, texture memory) before editing; record the numbers before and after.
2. Prefer material functions, parameters and instances over duplicated graphs; keep permutations low.
3. Move work from pixel to vertex or to precomputed textures where quality allows; avoid dynamic branching on divergent data.
4. Use half precision where the platform supports it and banding is not visible.
## Checks
- Check precision, branching and overdraw on the lowest supported tier; no per-pixel work that can move to vertex or a texture.
- Permutation count and shader compile time not increased without a reason; DDC/shader cache warm-up noted.
- Verify visually in the editor or a capture and name the asset or shader files touched.
## Pitfalls
- New static switches or keywords multiplying permutations across every material that uses the function.
- Platform compile differences (HLSL to SPIR-V/Metal/console) caught only in packaged builds.
- Derivatives inside branches; NaNs from normalize(0) or divide-by-zero.
## Engine notes
- Unreal: `.usf`/`.ush` in a plugin or project shader directory, Custom node sparingly, `r.ShaderDevelopmentMode=1` for compile errors, `recompileshaders changed`, ShaderCompileWorker; check Shader Complexity view.
- Unity: HLSL in ShaderLab, Shader Graph custom functions; strip variants with `IPreprocessShaders`; check the Frame Debugger.
- Godot: Godot shading language (`.gdshader`), visual shaders; no permutation keywords, use uniforms and separate shaders.
