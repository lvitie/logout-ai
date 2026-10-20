# Environment and prop art
## When to use
- Environment concept, set dressing, modular kits, props, terrain/landscape, foliage, trim sheets and decals; turning a level blockout into final art.
- Not for: layout and gameplay space → `level-design`; lighting → `lighting-cinematics`; characters → `character-art-pipeline`.
## Inputs
- Approved blockout, environment concept and mood boards, metrics (door, cover, step heights), budgets (triangles, draw calls, texture memory per area), streaming layout, asset library.
## Method
1. Concept: key art per area with lighting intent; paintovers of the blockout.
2. Kit first: modular pieces on the grid with matching pivots; trim sheets and tiling materials over unique bakes.
3. Props: categorize hero, mid, and background; budget detail accordingly; reuse with material variation.
4. Dress in passes (large forms, mid, small detail, decals); keep the gameplay metrics and nav intact.
5. Terrain and foliage: layer materials, procedural scatter with art-directed overrides; density per platform.
6. Collision: simple collision for props; check with gameplay and AI owners.
## Checks
- Gameplay readability: paths, cover and interactables still read; level designer signs off on the critical path.
- Per-area draw calls, triangles and texture memory within budget; streaming cells within memory.
- No floating or interpenetrating assets on the camera path; collision matches visuals.
- Verify visually in the editor and name the asset paths touched.
## Pitfalls
- Unique assets everywhere (memory, iteration time); kit pieces off-grid.
- Dressing that blocks navigation or hides gameplay affordances.
- Foliage overdraw and shadow cost on low tiers.
## Engine notes
- Unreal: Nanite meshes, Landscape with layer blending, Foliage and Procedural Foliage, PCG framework, Runtime Virtual Texturing for terrain blending, Packed Level Actors for reusable sets, decals and Mesh Decals.
- Unity: Terrain tools, ProBuilder, Prefab variants, GPU instancing.
- Godot: Terrain via add-ons (for example Terrain3D), MultiMeshInstance3D for scatter, GridMap for modular kits.
