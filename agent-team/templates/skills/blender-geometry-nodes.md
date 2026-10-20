# Blender geometry nodes: procedural assets, scatter, simulation zones and bakes for engines
## When to use
- Building or fixing a Geometry Nodes modifier or node group in Blender (scripted or UI): procedural props/kits, scatter, instancing, attributes for shaders, simulation zones, baking results to meshes, Alembic or USD, packaging node groups as assets.
- Not for: in-engine scatter, foliage and PCG → `environment-props`; Blender fluid/cloth/particle sims → `blender-vfx`; engine material cost → `shaders`; rig and weights → `blender-rigging`.
## Inputs
- Blender version (`blender --version`; checked against 5.2 LTS, notes for 4.2–5.1), the .blend and the target object/modifier, the engine and its import path (FBX, glTF, USD, Alembic), budgets (tris, instances, draw calls), which attributes the engine shader reads.
## Method
1. Work headless and reproducibly: `blender -b scene.blend --python-exit-code 1 --python build.py -- --out //out/` (args after `--` are yours, read `sys.argv[sys.argv.index("--")+1:]`). Use `bpy.data` (no selection, no operator context) over `bpy.ops`; when an operator is unavoidable wrap it in `with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):` (3.2+). Headless has no undo stack: save to a new path, never over the source.
2. Create the group and its interface (4.0+ API; `tree.inputs/outputs` are gone; 5.2 `new_socket` is keyword-only after `name`):
```python
import bpy
ng = bpy.data.node_groups.new("GN_ScatterRocks", "GeometryNodeTree")
ng.is_modifier = True  # 4.0+: listed in Add Modifier when marked as an asset
ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
dens = ng.interface.new_socket("Density", in_out="INPUT", socket_type="NodeSocketFloat")
dens.default_value, dens.min_value = 5.0, 0.0
ng.interface.new_socket("Instance", in_out="INPUT", socket_type="NodeSocketObject")
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
N, L = ng.nodes, ng.links
gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
dist = N.new("GeometryNodeDistributePointsOnFaces")
info = N.new("GeometryNodeObjectInfo"); info.transform_space = "RELATIVE"
inst = N.new("GeometryNodeInstanceOnPoints")
join = N.new("GeometryNodeJoinGeometry")
L.new(gi.outputs["Geometry"], dist.inputs["Mesh"])
L.new(gi.outputs["Density"], dist.inputs["Density"])
L.new(gi.outputs["Instance"], info.inputs["Object"])
L.new(dist.outputs["Points"], inst.inputs["Points"])
L.new(info.outputs["Geometry"], inst.inputs["Instance"])
L.new(dist.outputs["Rotation"], inst.inputs["Rotation"])  # field: evaluated per point, aligns to the surface
L.new(gi.outputs["Geometry"], join.inputs["Geometry"])
L.new(inst.outputs["Instances"], join.inputs["Geometry"])
L.new(join.outputs["Geometry"], go.inputs["Geometry"])
for i, n in enumerate((gi, dist, info, inst, join, go)):
    n.location = (i * 220, 0)
```
   Socket names repeat (multi-type nodes such as Random Value, Compare); 5.2 changed some identifiers. Print `[(s.name, s.identifier, s.type) for s in node.outputs]` and link by identifier on those nodes. Node bl_idnames: `GeometryNodeMeshGrid`, `GeometryNodeSetPosition`, `GeometryNodeCaptureAttribute`, `ShaderNodeMath`, `ShaderNodeCombineXYZ`, `FunctionNodeRandomValue`; bundles/closures (5.0+) use `NodeCombineBundle`, `NodeEvaluateClosure`.
3. Attach and drive it. Inputs are keyed by the interface socket identifier (`Socket_2`), not the label; 5.2 moved them from IDProperties to `mod.properties`:
```python
ob = bpy.data.objects["Ground"]
mod = ob.modifiers.new("Scatter", "NODES")
mod.node_group = ng
ids = {s.name: s.identifier for s in ng.interface.items_tree if s.item_type == "SOCKET" and s.in_out == "INPUT"}
def set_input(mod, ident, value):
    if bpy.app.version >= (5, 2, 0):
        getattr(mod.properties.inputs, ident).value = value
    else:  # 4.0-5.1; since 4.2 the IDProperty type is fixed (no float into an int input)
        mod[ident] = value
set_input(mod, ids["Density"], 12.0)
set_input(mod, ids["Instance"], bpy.data.objects["Rock_A"])
ob.update_tag(); bpy.context.view_layer.update()  # re-evaluate before reading results
```
4. Fields and domains: a field is a function evaluated on the node it ends in, on that node's domain (point, edge, face, face corner, curve, instance). Use Capture Attribute to freeze a value before topology changes; use Store Named Attribute (`GeometryNodeStoreNamedAttribute`, `data_type`, `domain`) for anything the engine must read. UVs must be `FLOAT2` on `CORNER`; vertex colors `FLOAT_COLOR`/`BYTE_COLOR` on `POINT` or `CORNER`.
5. Instances vs realized geometry: instances are cheap references and render/viewport fast; Realize Instances (`GeometryNodeRealizeInstances`) copies them into one mesh and is needed before per-vertex edits or for exporters that drop instances. Realize as late as possible; for engines prefer exporting points + an instance list (USD point instancer, glTF `EXT_mesh_gpu_instancing`) over one realized mesh.
6. Simulation zone (3.6+): add the input/output pair and pair them; state passes between frames, the zone only advances on frame change:
```python
si = N.new("GeometryNodeSimulationInput"); so = N.new("GeometryNodeSimulationOutput")
si.pair_with_output(so)
so.state_items.new("FLOAT", "Age")  # extra state besides Geometry
```
   Zones run only in the modifier (not in node tools); anonymous attributes are dropped unless added to the state. Bake before export or farm use: the modifier's Bake panel or a Bake node (`GeometryNodeBake`, 4.1+). Packed into the .blend is the default since 4.3 (`mod.bake_target = "DISK"` plus `mod.bake_directory = "//bakes/"` for external). The .blend must be saved first. Scripted: `for b in mod.bakes: bpy.ops.object.geometry_node_bake_single(session_uid=ob.session_uid, modifier_name=mod.name, bake_id=b.bake_id)`; all sims: `bpy.ops.object.simulation_nodes_cache_bake(selected=False)`. Bake files are a Blender cache, not an interchange format, and may not load in other versions.
7. Bake to a real mesh for handoff (keeps modifier on the source):
```python
dg = bpy.context.evaluated_depsgraph_get()
me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
baked = bpy.data.objects.new(ob.name + "_baked", me); bpy.context.scene.collection.objects.link(baked)
```
   `new_from_object` realizes instances; without `preserve_all_data_layers=True` UVs and vertex groups are lost. 5.1+: Realize Instances writes curve attributes to the curve domain; `realize_to_point_domain` restores 5.0 behavior. Only 8 nested instance levels display. `bpy.ops.object.convert(target="MESH")` applies destructively.
8. Export. Static result: glTF `bpy.ops.export_scene.gltf(filepath=..., export_apply=True, export_gpu_instances=True, export_attributes=True)` (`EXT_mesh_gpu_instancing`; only attributes named `_name` export; `export_gn_mesh` for GN instances is experimental). Animated/simulated: cache, not per-frame meshes: `bpy.ops.wm.alembic_export(filepath="//out/rocks.abc", start=1, end=120, evaluation_mode="RENDER", use_instancing=True, face_sets=True)`; `bpy.ops.wm.usd_export(filepath="//out/rocks.usdc", export_animation=True, use_instancing=True, evaluation_mode="RENDER")` (instancing is experimental: GN instances become a `UsdGeomPointInstancer`, partly supported; realize for complex cases; `rename_uvmaps` writes `st`).
9. Package as an asset: `ng.asset_mark(); ng.asset_generate_preview()`; set `ng.asset_data.description`, `ng.asset_data.tags.new("scatter")`, `ng.asset_data.catalog_id` (UUID from the library's `blender_assets.cats.txt`; the catalog path becomes the Add Modifier submenu; 5.2 skips a top-level "Geometry Nodes" catalog). Save the .blend in a folder registered as a library (`bpy.ops.preferences.asset_library_add(directory=...)` or Preferences > File Paths). `ng.is_modifier = True` for modifiers, `ng.is_tool = True` plus `is_mode_*`/`is_type_*` for node tools (5.1: re-save older tools). Expose only the inputs artists touch, with min/max and descriptions; group them with `ng.interface.new_panel("Scatter")`.
10. Name things: `GN_<Purpose>` groups, `<Attr>` names in lower_snake that match the engine shader parameter, objects `SM_`/`SK_` prefixes only on the exported result. Save with `bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)` so the session keeps the source path.
## Checks
- Data checks in the script, not by eye: evaluated counts `len(ob.evaluated_get(dg).data.vertices)`, instance count via the Spreadsheet or `dg.object_instances`, attribute present `"uv_wear" in me.attributes` with the expected `domain` and `data_type`.
- Timing: enable the modifier timings overlay (node editor overlay > Timings) and record the slowest node; record evaluated tris and instance count against the budget.
- Visual: headless screenshot via `bpy.ops.render.opengl(write_still=True)` (needs a GPU context; with `-b` use an EEVEE or Cycles render to `//out/check.png` instead) and name the file.
- Re-import the exported file into a clean scene or the engine and compare counts, bounds, scale and UV/attribute names.
- Bakes exist on disk and the .blend opens without the add-ons that produced it.
## Pitfalls
- `bpy.ops` calls failing headless with `poll() failed, context is incorrect`: use `bpy.data` or `temp_override`.
- Setting `mod["Density"]` (label) instead of the identifier, or `mod["Socket_N"]` on 5.2+ instead of `mod.properties`; positional `new_socket(name, in_out, type)` fails on 5.2.
- Forgetting that fields evaluate where they are consumed: random values change when topology changes upstream; capture or store them first. Seed random nodes explicitly for reproducibility.
- Realizing early (memory and time explode); exporting instances to FBX, which realizes or drops them depending on settings.
- Simulation results not baked: renders on a farm or exports start from frame 1 state; scrubbing backwards resets the sim.
- Named attributes lost on export: FBX has no generic-attribute option (UVs and colors only); custom attributes need glTF (`_` prefix) or USD primvars. For USD the modifier must output only the object's own geometry type.
- Linked assets break when the library path changes; append (not link) for shipping .blend handoffs, or keep libraries at a stable path.
- Version drift: a group saved in 5.x may not open in 4.x; record the version in the asset description.
## Engine notes
- Unreal: baked meshes → Static Mesh via FBX or glTF (1 UU = 1 cm; keep Blender in meters, scene unit scale 1.0, and let the importer's Convert Scene Unit scale it; FBX default axes -Z forward / Y up are converted on import). USD via the USD Stage for point instancers. Animated output: Alembic → Geometry Cache (needs `face_sets=True` for materials; triangulate, n-gons fail). The material reads vertex colors and UV channels, so pack custom attributes there; per-instance data → ISM/HISM Per Instance Custom Data or PCG point attributes.
- Unity: FBX with `apply_scale_options="FBX_SCALE_ALL"` (1 unit = 1 m, no 100x root) and the importer's Bake Axis Conversion; glTF via a glTF importer package; Alembic via `com.unity.formats.alembic` (Windows/macOS/Linux). Instances become prefabs placed from an exported point list (positions, rotations as a JSON/CSV or a point mesh).
- Godot: glTF is the native path; instancing via MultiMesh from an exported point list.
