# Character art pipeline (concept to in-engine)
## When to use
- Character and creature concept, sculpt, retopology, UVs, baking, texturing, hair/groom, LODs, skin weights handoff, outfits and modular parts.
- Not for: rig controls and animation → `animation`; master materials → `material-authoring`; environment assets → `environment-props`.
## Inputs
- Concept or brief (silhouette, faction, readability goals), style guide, poly/texture/bone budgets per platform and LOD, the shared skeleton, naming and folder conventions.
## Method
1. Concept: silhouette and value studies first, then turnarounds (front, side, back) with callouts for materials and functional parts.
2. High-poly sculpt; low-poly retopo with edge loops at deforming joints; UVs with consistent texel density.
3. Bake normals, AO, curvature with a cage; texture in the project's PBR workflow and texture set count.
4. LODs: generated or hand-made per budget; set screen sizes; check silhouette at each LOD.
5. Skin to the shared skeleton; test deformation with the rig's range-of-motion clip.
6. Import with the project presets (scale, axis, normals, texture groups); assign material instances from the masters.
## Checks
- Poly, texture memory, material slots and bone influences within budget at each LOD.
- Range-of-motion test shows no tearing or major volume loss; no baking artifacts (seams, skewing).
- Reads at gameplay camera distance and in the darkest and brightest lighting setups.
- Verify visually in the editor and name the asset paths touched.
## Pitfalls
- Too many material slots (draw calls); unique textures for parts that could share a trim or atlas.
- Mirrored UVs with baked normal seams; inconsistent texel density between outfit parts.
- Skeleton changes that break shared animations.
## Engine notes
- Unreal: Skeletal Mesh LOD settings and Skeletal Mesh Reduction, Groom (Alembic hair), Chaos Cloth, MetaHuman for realistic humans, Mutable/Customizable Object for modular characters, Nanite for skeletal meshes where enabled.
- Unity: Model Import Settings (Rig: Humanoid/Generic), LOD Group, HDRP hair shader.
- Godot: glTF import (preferred), import scene LODs, Skeleton3D retarget profiles.
