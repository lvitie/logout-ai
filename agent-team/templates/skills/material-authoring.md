# Material authoring
## When to use
- Authoring or changing a material, master material, material function, layer or instance.
- Not for: hand-written shader code or render-pass cost → `shaders`; lighting setup → `lighting-cinematics`.
## Inputs
- Target platform and quality tier, budget (instructions, samplers, texture memory), reference art, existing master materials and naming.
## Method
1. Name the target (platform, quality tier) and budget (instructions, samplers, texture memory) first; record the numbers before and after.
2. Build a master material with parameters and author variants as instances; reuse material functions instead of copying graphs.
3. Keep static switches and permutations few; share texture samplers and pack masks into channels (ORM-style) where the engine allows.
4. Match the existing naming, parameter groups and texture import settings (sRGB, compression, mips); name the asset paths touched.
5. Physically plausible values: base color albedo within PBR range, metallic 0 or 1 except transitions.
## Checks
- Verify visually in the editor or a capture on the lowest supported tier.
- Instruction and sampler counts within budget per tier; shader permutation count not increased without reason.
- Instances reparented correctly; no orphaned or duplicated masters.
## Pitfalls
- A new master per asset (permutation and compile-time explosion).
- Normal maps or masks imported as sRGB; wrong texture group causing over-budget mips.
- Translucency and masked opacity where opaque works (overdraw, no early-Z).
## Engine notes
- Unreal: Material Instances (Constant vs Dynamic), Material Functions, Material Layers, Substrate where enabled, Shader Complexity and Quad Overdraw view modes, `Platform Stats` window.
- Unity: Shader Graph with Material Variants (URP/HDRP); keep keywords low (`shader_feature` over `multi_compile`).
- Godot: ShaderMaterial with uniforms, StandardMaterial3D for simple cases; visual shaders.
