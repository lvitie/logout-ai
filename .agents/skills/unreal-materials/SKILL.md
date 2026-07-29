---
name: unreal-materials
description: Design, implement, debug, and profile Unreal Engine 5.8 materials and shaders. Use for Material Graphs, Material Functions and Instances, Substrate, Custom HLSL nodes, .usf and .ush files, global and compute shaders, shader permutations, Render Dependency Graph passes, rendering artifacts, shader compilation failures, platform compatibility, or GPU cost analysis. Use unreal-cpp for general native gameplay or plugin code.
---

# Unreal Materials and Shaders

## Select the correct layer

1. Identify the engine version, render path, target platform, RHI, feature
   level, material domain, blend mode, shading model, and Substrate usage.
2. Choose the least invasive implementation:
   - Material expressions for standard operations.
   - Material Functions for reusable graph logic.
   - Material Instances and parameters for artist-facing variation.
   - Custom expressions only for HLSL the graph cannot express well.
   - Plugin `.usf` or `.ush` files and global shaders for custom render passes.
   - RDG for scheduled render or compute work with managed resources.
3. Inspect neighboring materials, shader files, module startup, virtual shader
   path mappings, permutations, and render passes.
4. Read `references/docs-map.md` before version-sensitive shader work.

## Implement materials

- Preserve parameter names, ranges, channel conventions, color spaces, UV
  spaces, tangent basis, texture sampler types, and instance contracts.
- Prefer built-in expressions and shared Material Functions. Use static
  switches only when the permutation cost is justified.
- Move work between vertex and pixel stages only after checking interpolation,
  precision, and visual consequences.
- Keep graphs readable for artists with named parameters, grouped controls,
  comments, sensible defaults, and reusable functions.

## Implement HLSL and render passes

- Give Custom expression nodes explicit inputs, outputs, types, and defines.
  Do not depend on undocumented engine-private includes without pinning the
  engine version.
- Remember that Custom nodes can prevent constant folding; compare their
  instruction cost with an equivalent built-in graph.
- Store plugin shaders beneath the plugin's `Shaders/` directory and follow
  existing virtual path and shader-type registration patterns.
- Define shader parameters through Unreal parameter structs and declare RDG
  reads, writes, render targets, and pass flags accurately.
- Keep shader permutations bounded with explicit compile predicates.
- Write cross-RHI HLSL unless the feature is intentionally platform-specific.

## Validate

1. Compile the material or shader and read the complete first compiler error.
2. Compare against a visual reference in representative lighting and content.
3. Test relevant quality levels, feature levels, RHIs, and target platforms.
4. Inspect Material Stats, Platform Stats, Shader Complexity, instruction and
   sampler counts, overdraw, permutations, and GPU timing as appropriate.
5. For RDG work, enable validation and add useful event scopes for profiling.
6. Save and re-open affected assets, then verify cooked or packaged behavior
   when shader cooking is in scope.

## Guardrails

- Preserve unsaved assets and use `unreal-mcp-workflow` for live Material
  Editor or asset mutations.
- Ask before triggering broad shader recompilation, changing shared master
  materials, invalidating a Derived Data Cache, or altering project render
  settings.
- Do not edit generated shader code or engine shaders unless engine-source
  modification is explicitly required.
- Treat visual correctness and measured GPU cost as separate acceptance
  criteria.
