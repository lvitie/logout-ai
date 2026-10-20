# Blender VFX: Mantaflow, particles, physics sims, renders and caches for game engines
## When to use
- Making effect source data in Blender: Mantaflow smoke/fire/liquid, particle systems and hair, rigid body, cloth and soft body, force fields, EEVEE/Cycles renders, compositor passes, and baking them to caches (point cache, OpenVDB, Alembic, USD), flipbooks or vertex animation for Unreal or Unity.
- Not for: in-engine Niagara/VFX Graph systems and effect budgets → `vfx`; gameplay physics, ragdolls, destruction runtime → `physics`; effect shader cost → `shaders`; procedural geometry and GN simulation zones → `blender-geometry-nodes`.
## Inputs
- Blender version (checked against 5.2 LTS; render and compositor API changed in 5.0), the .blend (saved to disk: disk caches need a path), effect brief and reference, target (flipbook size and frame count, VDB grid budget, vertex count for VAT/Alembic), frame range and rate, engine and import path.
## Method
1. Headless: build and bake with `blender -b fx.blend --python-exit-code 1 --python bake.py`, render with `blender -b fx.blend -E CYCLES -o //render/fx_#### -F PNG -s 1 -e 64 -a` (`-a`/`-f` last: arguments run in order; `--cycles-device OPTIX` or `CUDA`, `HIP`, `METAL`, `ONEAPI`, `CPU`). Sims only compute inside their cache frame range and only forward; set the scene range first. Save before baking (`bpy.ops.wm.save_mainfile()`); relative cache paths (`//cache/`) keep the handoff portable.
2. Mantaflow smoke/fire domain (still in 5.2, no new features planned; 5.0 changed vorticity scaling, so 4.x bakes do not match):
```python
import bpy
dom = bpy.data.objects["FX_SmokeDomain"]; src = bpy.data.objects["FX_Emitter"]
m = dom.modifiers.new("Fluid", "FLUID"); m.fluid_type = "DOMAIN"
ds = m.domain_settings
ds.domain_type = "GAS"; ds.resolution_max = 128
ds.cache_directory = "//cache/smoke"; ds.cache_type = "ALL"  # REPLAY needs "Play Every Frame"; use ALL headless
ds.cache_frame_start, ds.cache_frame_end = 1, 96
ds.cache_data_format = "OPENVDB"; ds.openvdb_cache_compress_type = "BLOSC"
ds.use_noise = False; ds.use_adaptive_domain = True
f = src.modifiers.new("Fluid", "FLUID"); f.fluid_type = "FLOW"
fs = f.flow_settings; fs.flow_type = "BOTH"; fs.flow_behavior = "INFLOW"  # SMOKE, FIRE, BOTH, LIQUID
bpy.ops.wm.save_mainfile()
with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom]):
    bpy.ops.fluid.bake_all()  # or bake_data / bake_noise / bake_mesh for modular caches
```
   VDB grids written: `density`, `flame`, `fuel`, `react`, `temperature`, `velocity`, `color_r/g/b`, `shadow` (names from the fluid source; check them with the Volume object's grids). Quick start: `bpy.ops.object.quick_smoke(style="FIRE")` / `quick_liquid()` on a selected mesh. Liquid: `domain_type = "LIQUID"`, `use_mesh = True`, `cache_mesh_format` for the surface mesh (export it via Alembic).
3. Particles and hair: legacy particle systems still exist; the particle hair system is "end of life", use Curves hair objects (3.3+) and `bpy.ops.object.quick_fur()`. Particle/cloth/soft body share the point cache: set `psys.point_cache.frame_start/end`, `use_disk_cache = True` (needs a saved file), then `bpy.ops.ptcache.bake_all(bake=True)`. 5.0 removed LZO/LZMA cache compression (ZSTD always): rebake old caches.
4. Rigid body debris, baked to keys for engines:
```python
scn = bpy.context.scene
if scn.rigidbody_world is None:
    bpy.ops.rigidbody.world_add()
rbw = scn.rigidbody_world; rbw.substeps_per_frame = 10; rbw.solver_iterations = 10
rbw.point_cache.frame_start, rbw.point_cache.frame_end = 1, 120
pieces = [o for o in bpy.data.collections["FX_Debris"].objects if o.type == "MESH"]
for o in pieces:
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
        bpy.ops.rigidbody.object_add(type="ACTIVE")
    o.rigid_body.mass, o.rigid_body.collision_shape = 1.0, "CONVEX_HULL"
with bpy.context.temp_override(selected_objects=pieces, active_object=pieces[0]):
    bpy.ops.rigidbody.bake_to_keyframes(frame_start=1, frame_end=120, step=1)
```
   Cloth/soft body: `o.modifiers.new("Cloth", "CLOTH")` (`.settings`, `.collision_settings`, `.point_cache`), `"SOFT_BODY"`, colliders `"COLLISION"` (`o.collision`). 5.2 adds experimental Geometry Nodes cloth/hair dynamics (XPBD); do not ship pipelines on it yet. Force fields: `bpy.ops.object.effector_add(type="WIND")` or `TURBULENCE`, `VORTEX`, `FORCE`, `DRAG`; tune `obj.field.strength`, `flow`, `noise`, `shape`.
5. Render engine choice: EEVEE (`scene.render.engine = "BLENDER_EEVEE"` in 5.0+, `"BLENDER_EEVEE_NEXT"` in 4.2–4.5) for fast flipbooks and previews; Cycles (`"CYCLES"`) for volumes with correct scattering, fire emission and motion-vector passes. For game textures set `scene.render.film_transparent = True`, `scene.view_settings.view_transform = "Standard"` (AgX is the default since 4.0 and tone-maps the colors; 5.0 adds a per-file working space, keep Rec.709 for sRGB textures), `scene.render.image_settings.color_mode = "RGBA"`, fixed camera, orthographic for sprites.
6. Compositor (5.0+: `scene.node_tree` removed; `scene.use_nodes` does nothing; toggle with `scene.render.use_compositing`):
```python
scn = bpy.context.scene
tree = bpy.data.node_groups.new("COMP_Flipbook", "CompositorNodeTree")
scn.compositing_node_group = tree
tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = tree.nodes.new("CompositorNodeRLayers"); out = tree.nodes.new("NodeGroupOutput")
tree.links.new(rl.outputs["Image"], out.inputs["Image"])
scn.render.use_compositing = True
```
   4.x: `scn.use_nodes = True; tree = scn.node_tree` with a `CompositorNodeComposite`. File Output node in 5.0 uses `directory`, `file_name`, `file_output_items` (not `base_path`/`file_slots`). Many Compositor* nodes became Shader* nodes (e.g. `ShaderNodeGamma`); check bl_idnames per version.
7. Flipbooks: render N frames at the cell size, then pack them into a grid atlas (Blender has no atlas packer; script it):
```python
import bpy, math
cols, frames, cell = 8, 64, 256
rows = math.ceil(frames / cols)
atlas = bpy.data.images.new("T_FX_Smoke_SubUV", cols * cell, rows * cell, alpha=True)
px = [0.0] * (cols * cell * rows * cell * 4)
for i in range(frames):
    img = bpy.data.images.load(bpy.path.abspath(f"//render/fx_{i + 1:04d}.png"))
    src = img.pixels[:]; cx, cy = i % cols, rows - 1 - i // cols  # row 0 at the top, pixels start bottom-left
    for y in range(cell):
        d = ((cy * cell + y) * cols * cell + cx * cell) * 4
        px[d:d + cell * 4] = src[y * cell * 4:(y + 1) * cell * 4]
    bpy.data.images.remove(img)
atlas.pixels.foreach_set(px)
atlas.filepath_raw = bpy.path.abspath("//export/T_FX_Smoke_SubUV.png"); atlas.file_format = "PNG"; atlas.save()
```
   Render normals/motion vectors as separate passes when the engine shader uses motion-vector flipbook blending.
8. Vertex animation textures: no first-party Blender VAT exporter. Fixed-topology meshes (cloth, rigid pieces, deform): script a bake that writes per-frame vertex offsets (and normals) into float textures, one column per vertex, one row per frame, with a second UV channel indexing the column; Unreal's AnimToTexture plugin (experimental) bakes skeletal meshes in-engine instead. Changing topology (liquid meshes): use Alembic → Geometry Cache, not VAT.
9. Caches out: Alembic `bpy.ops.wm.alembic_export(filepath="//export/FX_Debris.abc", start=1, end=120, selected=True, uvs=True, normals=True, face_sets=True, triangulate=True, export_hair=False, export_particles=False, evaluation_mode="RENDER")` (5.0 removed `visible_objects_only`); USD `bpy.ops.wm.usd_export(..., export_volumes=True, export_points=True, export_animation=True)` writes volumes as UsdVol referencing the VDB files; VDB sequences are the cache directory's `data/*.vdb` files.
10. Naming: objects `FX_<Effect>_<Part>`, caches `//cache/<effect>/`, renders `//render/<effect>_####`, textures `T_FX_<Effect>_<Map>` (SubUV, Normal, MV), VDB/Alembic `FX_<Effect>.vdb`/`.abc`. Record frame count, grid layout (cols x rows), fps and resolution in the asset description or a sidecar `.md`.
## Checks
- Bake complete: cache folder has one file per frame for the range (`len(glob.glob(bpy.path.abspath("//cache/smoke/data/*.vdb")))`), `point_cache.is_baked` true, no missing frames at the start.
- Values: flipbook alpha edges clean (no black fringe; premultiplied vs straight alpha matches the engine material), atlas size power of two, frame order left-to-right top-to-bottom; VDB loads as a Volume object with the expected grids and voxel size.
- Visual: render 3 stills (start, peak, end) and the atlas; name the files. Compare EEVEE preview against the final Cycles look if both are used.
- Budgets recorded: resolution, voxel count or VDB size on disk, Alembic vertex count and file size, atlas memory.
- Re-import into the engine: playback speed matches fps, scale correct (1 m = 100 UU), pivot where gameplay spawns it.
## Pitfalls
- 4.x scripts on 5.x: `scene.node_tree`, `BLENDER_EEVEE_NEXT` and compositor node names fail.
- AgX/Filmic view transform baked into textures (washed colors); not using Standard.
- Unsaved .blend or absolute cache paths: bakes go nowhere or break on another machine.
- REPLAY cache headless (frames skipped); baking from mid-range (sims start at the cache start).
- Resolution too high for the effect size on screen: huge VDBs that the engine converts down anyway.
- Alembic without face sets (no materials in Unreal) or with n-gons (import fails).
- Expecting legacy hair or old LZO caches to carry forward.
## Engine notes
- Unreal: flipbooks → Niagara Sprite Renderer Sub UV (Sub Image Size = cols x rows) with the Sub UV Animation module; the Niagara Flipbook Baker can bake in-engine instead. VDB → Sparse Volume Textures (experimental; Windows editor, DX11/12, no mobile; numbered sequences become animated SVTs; double-precision grids unsupported). Alembic → Geometry Cache (needs face sets, triangulated; the Sequencer track is experimental). Baked rigid-body keys → FBX as animated static meshes or a skeletal mesh with one bone per piece. VAT → a material reading the offset texture in World Position Offset.
- Unity: flipbooks → Particle System Texture Sheet Animation (Grid, tiles X/Y) or VFX Graph flipbook player; no built-in VDB import (VFX Graph reads `.vf` vector fields as 3D textures); Alembic via `com.unity.formats.alembic` (meshes, points, curves, cameras; Windows/macOS/Linux); VAT via a Shader Graph vertex stage.
- Godot: flipbooks via particle materials' animation frames (h/v frames); Alembic not supported natively, use glTF baked keys.
