# Blender rigging: armatures, constraints, drivers, weights, shape keys and game-skeleton export
## When to use
- Building, fixing or scripting a character/prop rig in Blender: armature and bone orientation, bone collections, IK/FK, constraints, drivers, skinning and weight transfer, shape keys, Rigify, and exporting a clean deform skeleton for Unreal or Unity (including retarget prep).
- Not for: keyframing, NLA and clip export → `blender-animation`; in-engine skeletons, anim graphs and retarget assets → `animation`; mesh, UV and LOD work → `character-art-pipeline`; ragdoll/physics assets → `physics`.
## Inputs
- Blender version (checked against 5.2 LTS; notes back to 4.0), the .blend, mesh(es) to bind, the target skeleton spec (engine reference skeleton such as the UE Mannequin or a Unity Humanoid, joint list, naming, max influences), deform vs control needs, the export format.
## Method
1. Headless and repeatable: `blender -b char.blend --python-exit-code 1 --python rig.py`. Edit bones exist only in Edit Mode, so set the active object and switch modes; never keep `EditBone` references (or their `head`/`tail` vectors) after leaving Edit Mode (Blender can crash). Re-fetch by name. No undo headless: save to a new file with `bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)`.
2. Build the skeleton (4.0+ collections; layers and bone groups are gone):
```python
import bpy
arm = bpy.data.armatures.new("SKEL_Hero")
rig = bpy.data.objects.new("RIG_Hero", arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.edit_bones
def bone(name, head, tail, parent=None, deform=True, roll=0.0):
    b = eb.new(name); b.head, b.tail, b.roll = head, tail, roll
    b.parent, b.use_deform = (eb[parent] if parent else None), deform
    return b.name
bone("root", (0, 0, 0), (0, 0.3, 0))  # at the origin, Y forward, deforms nothing but must export
bone("pelvis", (0, 0, 1.0), (0, 0, 1.1), "root")
bone("thigh_l", (0.1, 0, 1.0), (0.1, 0.02, 0.55), "pelvis")
bone("calf_l", (0.1, 0.02, 0.55), (0.1, 0, 0.1), "thigh_l")
eb["calf_l"].use_connect = True
bone("ik_foot_l", (0.1, 0, 0.1), (0.1, 0.2, 0.1), "root", deform=False)
bone("pole_knee_l", (0.1, -0.5, 0.55), (0.1, -0.6, 0.55), "root", deform=False)
for n in ("thigh_l", "calf_l"):
    eb[n].select = True
arm.edit_bones.active = eb["calf_l"]
bpy.ops.armature.calculate_roll(type="GLOBAL_POS_Y")  # consistent knee roll on the selected chain
bpy.ops.object.mode_set(mode="OBJECT")
deform = arm.collections.new("DEF"); ctrl = arm.collections.new("CTRL")
for b in arm.bones:
    (deform if b.use_deform else ctrl).assign(b)
    b.color.palette = "THEME04" if not b.use_deform else "DEFAULT"
```
   Bone roll: Blender bones point down +Y; `roll` spins around it. Keep one rule per chain (knees and elbows bend around the same local axis on both sides) so mirrored animation and engine IK agree. `arm.collections` lists only top-level collections (4.1+ hierarchy, `collections.new(name, parent=...)`); use `arm.collections_all` to search. In 5.0+ selection/visibility live on pose bones (`pose.bones[n].select`, `.hide`) and `Bone.select` is gone; use `EditBone.select` in Edit Mode as above.
3. IK with a pole, and an FK/IK switch driven by a custom property:
```python
pb = rig.pose.bones["calf_l"]
ik = pb.constraints.new("IK")
ik.target, ik.subtarget = rig, "ik_foot_l"
ik.pole_target, ik.pole_subtarget = rig, "pole_knee_l"
ik.pole_angle, ik.chain_count = -1.5708, 2  # radians; tune until the knee does not flip at rest
rig["ik_fk_l"] = 1.0  # 1 = IK, 0 = FK
fc = ik.driver_add("influence")
d = fc.driver; d.type = "AVERAGE"
v = d.variables.new(); v.name = "sw"; v.type = "SINGLE_PROP"
v.targets[0].id, v.targets[0].data_path = rig, '["ik_fk_l"]'
```
   For a full FK/IK rig keep three chains: DEF (deforms), FK and IK (controls), with `COPY_TRANSFORMS` constraints on DEF bones whose `influence` is driven. Use Child Of (`set_inverse_pending`) for props swapping hands, Damped Track (`track_axis`) for aim/eye bones.
4. Drivers for correctives: `fc = key.key_blocks["knee_bend_l"].driver_add("value")` with a `TRANSFORMS` variable named `rot` (`v.name = "rot"`, `targets[0].bone_target = "calf_l"`, `transform_type = "ROT_X"`, `transform_space = "LOCAL_SPACE"`) and `d.type = "SCRIPTED"`, `d.expression = "max(0, rot / 1.57)"`. Keep expressions "simple" (`d.is_simple_expression` true): only simple expressions run when Python auto-run is off, which is the default and the norm on farms. 4.4+: deleting a modifier/constraint/shape key also deletes its drivers; 5.1+: renaming a bone keeps its drivers.
5. Bind and weight:
```python
body = bpy.data.objects["SK_Hero_Body"]
for o in bpy.context.selected_objects:
    o.select_set(False)
body.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")  # bone heat; groups only for deform bones, overwrites same-named groups
bpy.context.view_layer.objects.active = body
bpy.ops.object.vertex_group_limit_total(group_select_mode="BONE_DEFORM", limit=4)
bpy.ops.object.vertex_group_normalize_all(group_select_mode="BONE_DEFORM", lock_active=False)
bpy.ops.object.vertex_group_clean(group_select_mode="BONE_DEFORM", limit=0.01)
```
   Manual weights from code: `vg = body.vertex_groups.new(name="calf_l"); vg.add([i, j], 1.0, "REPLACE")`. Transfer weights from a skinned source (clothes, LOD, new topology): Data Transfer modifier (`use_vert_data=True`, `data_types_verts={"VGROUP_WEIGHTS"}`, `vert_mapping="POLYINTERP_NEAREST"`, `layers_vgroup_select_src="ALL"`, `layers_vgroup_select_dst="NAME"`), run `bpy.ops.object.datalayout_transfer(modifier=mod.name)` to create the groups, then apply the modifier before the Armature modifier in the stack; re-limit and normalize afterwards.
6. Shape keys: `body.shape_key_add(name="Basis", from_mix=False)` first, then `sk = body.shape_key_add(name="blink_l", from_mix=False)` and edit `sk.data[i].co`; set `sk.relative_key` and `sk.vertex_group` (masking) as needed. Names are the engine morph-target names: keep them stable, ASCII, no spaces. 5.1+ has Apply to Basis and the FBX exporter writes shape-key normals.
7. Rigify: core add-on, still bundled in 5.2 (enable in Preferences > Add-ons or `bpy.ops.preferences.addon_enable(module="rigify")`). Add a metarig, fit it, `bpy.ops.pose.rigify_generate()` with the metarig active. Output bones: `ORG-` (metarig copies), `MCH-` (mechanism), `DEF-` (deform, in the DEF collection), controls unprefixed; assumes 1 unit = 1 m. DEF bones are parented to ORG/MCH bones, so a deform-only export drags in parents or breaks the hierarchy. For games, build a separate export skeleton: plain deform bones in one clean hierarchy under `root`, each with `COPY_TRANSFORMS` to its `DEF-` bone, then bake (see `blender-animation`).
8. Export the game skeleton (FBX exporter is still the Python add-on in 5.2; the importer is C++ `bpy.ops.wm.fbx_import` since 5.0):
```python
bpy.ops.export_scene.fbx(
    filepath=bpy.path.abspath("//export/SK_Hero.fbx"), use_selection=True,
    object_types={"ARMATURE", "MESH"}, use_armature_deform_only=True, add_leaf_bones=False,
    primary_bone_axis="Y", secondary_bone_axis="X", armature_nodetype="NULL",
    apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE", global_scale=1.0,
    use_mesh_modifiers=False, mesh_smooth_type="FACE", use_tspace=True, bake_anim=False)
```
   `use_mesh_modifiers=True` drops shape keys; `bake_space_transform` is documented as broken with armatures. glTF: `bpy.ops.export_scene.gltf(export_def_bones=True, export_influence_nb=4, export_leaf_bone=False, export_rest_position_armature=True)`.
9. Naming and data conventions: object `RIG_<Char>` (or the name the engine pipeline expects), armature data `SKEL_<Char>`, mesh `SK_<Char>_<Part>`; bones lower_snake with `_l`/`_r` suffix (Blender's mirror tools also understand `.L/.R`, the engine does not care; pick what the target skeleton uses). Apply object scale and rotation on rig and mesh before binding (`bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)`), rest pose = engine reference pose.
## Checks
- Data checks: every vertex has 1–4 deform influences summing to 1.0 (loop `v.groups` over `body.data.vertices`), no vertex groups without a matching deform bone, no deform bone with zero weights unless intended (root, twist placeholders), bone count and names equal the target joint list.
- Hierarchy: one top root at the origin with identity rotation; no non-deform bone between deform bones after `use_armature_deform_only`.
- Deformation: pose a range-of-motion test (90° knee/elbow, arms up, twist) via `pose.bones[n].rotation_euler` and render stills `blender -b rom.blend -o //rom_ -F PNG -f 1..N`, or inspect in the viewport; check volume loss and candy-wrapping.
- Re-import the FBX/glTF (`bpy.ops.wm.fbx_import` into a clean file, or the engine) and compare bone count, rest pose, scale (character ~1.8 units tall in Blender = 180 cm in Unreal) and shape-key names.
## Pitfalls
- Kept `EditBone` references after a mode switch (crash or stale data); expecting `BoneCollection.bones` to update in Edit Mode (it syncs on exit).
- Unapplied object scale on the rig (non-1 scale exports scaled armatures that some importers reject).
- Leaf bones (`add_leaf_bones=True` default) adding `_end` joints the engine skeleton does not have.
- Rigify DEF bones exported straight (ORG parents leak or the chain breaks).
- Python driver expressions failing silently when auto-run is off; drivers on bones that no longer exist after a rename before 5.1.
- Exporting with modifiers applied (shape keys gone); more than 4 (glTF/mobile) or 8 influences.
- Mismatched bone roll between sides: mirrored clips twist joints in-engine.
## Engine notes
- Unreal: 1 UU = 1 cm; with Blender in meters and unit scale 1.0, enable Convert Scene Unit (or set Import Uniform Scale) on import. The skeletal mesh pivot is the root bone, so put `root` at the origin. Retargeting: match the Mannequin joint names/hierarchy where you can, or build an IK Rig (chains, retarget root = pelvis) and an IK Retargeter; Auto Retarget matches chains by name keywords and the Biped template covers UE4/UE5 Mannequins. Align the retarget pose (A-pose vs T-pose). Morph targets need Import Morph Targets on the FBX import. The "name the armature object `Armature` to avoid an extra root bone" advice is community lore, not documented by Epic or Blender; verify on re-import.
- Unity: Humanoid needs at least 15 bones in a human hierarchy, a T-pose (Enforce T-Pose fixes the warning) and recognizable names for Automap; Generic only needs the Root node set. Use the importer's Bake Axis Conversion for axis fixes and `apply_scale_options="FBX_SCALE_ALL"` for 1 unit = 1 m without a 100x root; Blend Shapes import from shape keys.
- Godot: glTF with `export_def_bones=True`; a Skeleton3D with a BoneMap/SkeletonProfileHumanoid handles retargeting.
