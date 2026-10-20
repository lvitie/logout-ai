# Blender animation: slotted actions, F-curves, NLA, baking, root motion and clip export
## When to use
- Authoring, scripting, cleaning, baking or exporting animation in Blender: actions and slots, keyframes and F-curves, Graph Editor work, NLA clips, pose assets, loops, root motion, camera/shot animation, retarget-ready clips for Unreal or Unity.
- Not for: building the rig, weights, drivers → `blender-rigging`; in-engine anim blueprints, state machines, montages and retarget assets → `animation`; cutscene direction and Sequencer → `lighting-cinematics`; simulations → `blender-vfx`.
## Inputs
- Blender version (checked against 5.2 LTS; the action API changed in 4.4 and 5.0), the rig, the clip list (name, frame range, loop or one-shot, root-motion policy), project frame rate, target engine and its skeleton/retarget setup.
## Method
1. Headless: `blender -b anim.blend --python-exit-code 1 --python clips.py -- --out //export/`. Set the frame with `scene.frame_set(f)` (updates the depsgraph); run operators inside `with bpy.context.temp_override(active_object=rig, object=rig, selected_objects=[rig]):` (3.2+; context dicts were removed in 4.0; call `.logging_set(True)` on the override to see which members an operator reads). No undo headless: work on copies (`act.copy()`) and save to a new file.
2. Slotted actions (4.4+; in 5.0 `Action.fcurves`, `Action.groups`, `Action.id_root` were removed). An action holds slots; F-curves live in a channelbag per slot:
```python
import bpy
from bpy_extras import anim_utils
rig = bpy.data.objects["RIG_Hero"]
ad = rig.animation_data_create()
act = bpy.data.actions.new("A_Hero_Walk_Fwd")
slot = act.slots.new("OBJECT", "RIG_Hero")  # same slot name on every clip -> swapping clips keeps the match
ad.action, ad.action_slot = act, slot  # set the slot explicitly or the rig may stay unanimated
cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)  # 5.0+
# 4.4-4.5: act.fcurve_ensure_for_datablock(rig, path, index=i, group_name=g) (action must be assigned)
path = 'pose.bones["pelvis"].location'
for i, keys in enumerate(([(1, 0.0), (17, 0.0), (33, 0.0)], [(1, 0.0), (17, 0.02), (33, 0.0)], [(1, 0.0), (9, -0.03), (17, 0.0), (25, -0.03), (33, 0.0)])):
    fc = cb.fcurves.ensure(path, index=i, group_name="pelvis")  # 5.0 renamed action_group= to group_name=
    for f, v in keys:
        k = fc.keyframe_points.insert(f, v, options={"FAST"})
        k.interpolation = "BEZIER"; k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"
    fc.modifiers.new("CYCLES")  # Graph Editor > Channel > Extrapolation Mode > Make Cyclic does the same
    fc.update()  # sort keys and recalculate handles after FAST inserts
act.use_frame_range = True; act.frame_start, act.frame_end = 1, 32  # 3.1+: exporters and NLA use this
act.use_cyclic = True
act.use_fake_user = True
```
   Version-safe alternative for simple keys: `pose_bone.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)` builds layer, strip, slot and channelbag itself on every version. Read curves on any 4.4+ version with `anim_utils.action_get_channelbag_for_slot(act, slot)` (None if empty).
3. F-curve hygiene: `CONSTANT` for stepped blocking, `BEZIER` with `AUTO_CLAMPED` handles for final (no overshoot), `LINEAR` for mechanical. `fc.extrapolation` is `CONSTANT`/`LINEAR`; cycles come from the modifier. Bake modifiers into keys before export (`fc.bake(start, end, step=1.0)` or the exporter's sampling). Rotation mode: quaternions on deform bones (no gimbal flips, engines store quats); Euler only where artists need it on controls. 5.1+: Gaussian Smooth F-curve modifier must be first in the stack.
4. Loops: for a 32-frame cycle at frame 1, keys at 1 and 33 are identical and the clip range is 1–32 for engines that wrap (frame 33 = frame 1), or 1–33 with the engine told the last frame duplicates the first. Pick one rule per project and state it in the clip list; Unity's Loop Pose and Unreal's looping both expect the pose to match across the seam.
5. NLA for clip lists: push each action down or create strips explicitly:
```python
for act in (bpy.data.actions["A_Hero_Walk_Fwd"], bpy.data.actions["A_Hero_Idle"]):
    tr = ad.nla_tracks.new(); tr.name = act.name
    st = tr.strips.new(act.name, int(act.frame_start), act)
    st.action_slot = act.slots[0]  # 4.4+: each strip needs a slot its own action owns
    st.extrapolation, st.blend_type, st.mute = "NOTHING", "REPLACE", False
ad.action = None  # leave no active action, or it is layered on top of every strip
```
   `bpy.ops.nla.action_pushdown(track_index=-1)` does the same from the UI context. Strips have `blend_in/out`, `repeat`, `scale`, `use_reverse`; keep export strips at scale 1, repeat 1.
6. Pose library: pose assets (the pre-3.0 pose library was removed in 3.5): `bpy.ops.poselib.create_pose_asset(pose_name="hand_fist_l", catalog_path="Hero/Hands")` with the pose bones selected; apply with `poselib.apply_pose_asset` / `blend_pose_asset`. Use them for blocking and hand poses, not as exported clips.
7. Bake constraints, IK and Rigify controls to the export skeleton:
```python
with bpy.context.temp_override(active_object=exp, object=exp, selected_objects=[exp]):
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.nla.bake(frame_start=1, frame_end=33, step=1, only_selected=True, visual_keying=True,
                     clear_constraints=True, use_current_action=False, clean_curves=False,
                     bake_types={"POSE"}, channel_types={"LOCATION", "ROTATION", "SCALE"})
```
   `clear_constraints` is only correct with `visual_keying=True`. Operator-free path: `anim_utils.bake_action(obj, action=..., frames=range(1, 34), bake_options=anim_utils.BakeOptions(...))`. Do one action per clip (rename the result to the clip name).
8. Root motion: animate the `root` bone (child of nothing, at the origin), never the armature object; the pelvis carries the bob/sway, root carries ground-plane travel and yaw. In-place clips: root stays at the origin. Bake motion from pelvis to root with a script that copies the pelvis X/Y (and Z yaw) to root per frame and subtracts it from the pelvis.
9. Cameras and shots: `scene.camera = cam`; bind cameras to markers for cuts (`m = scene.timeline_markers.new("SH010", frame=1); m.camera = cam`, or `bpy.ops.marker.camera_bind()`); animate focal length (`cam.data.lens`) and DOF; export cameras via FBX (`object_types={"CAMERA"}`), glTF (`export_cameras=True`) or USD (`export_animation=True`, render frame range).
10. Frame rate and range: `scene.render.fps = 30; scene.render.fps_base = 1.0` (real rate = fps / fps_base) set before keying; match the engine import rate. Scene range covers the longest clip; per-clip range comes from `act.frame_range`.
11. Export clips:
```python
bpy.ops.export_scene.fbx(filepath=bpy.path.abspath("//export/A_Hero.fbx"), use_selection=True,
    object_types={"ARMATURE"}, use_armature_deform_only=True, add_leaf_bones=False,
    bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=True,
    bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True,
    bake_anim_step=1.0, bake_anim_simplify_factor=0.0)
bpy.ops.export_scene.gltf(filepath=bpy.path.abspath("//export/A_Hero.glb"), use_selection=True,
    export_animation_mode="NLA_TRACKS", export_def_bones=True, export_force_sampling=True,
    export_anim_slide_to_zero=True, export_frame_step=1)
```
   FBX: every non-muted NLA strip becomes its own take; `bake_anim_use_all_actions=True` (the default) instead attaches every compatible action in the file to every object. `simplify_factor=0` keeps every sampled key (no drift on foot contacts). glTF `ACTIONS` mode exports only actions that are active, stashed or on NLA tracks; fake-user-only actions are skipped. One file per clip (`A_<Char>_<Clip>.fbx`) is simplest for engine reimport.
## Checks
- Data: for each clip, `act.frame_range`, key count per channel, no NaN values, first == last pose on loops (compare `fc.evaluate(start)` and `fc.evaluate(end + 1)` per channel within 1e-4), quaternion channels not flipping sign between adjacent keys.
- Root motion: root bone translation per clip equals the intended travel (e.g. 1.6 m per walk cycle); root X/Y is 0 for in-place clips.
- Visual: render a playblast headless (`blender -b anim.blend -E BLENDER_EEVEE -o //pb/A_Hero_Walk_#### -F PNG -s 1 -e 33 -a`; engine id `BLENDER_EEVEE` in 5.0+, `BLENDER_EEVEE_NEXT` in 4.2–4.5) and name the frames reviewed.
- Re-import the export (`bpy.ops.wm.fbx_import` creates one slotted action per take) or into the engine: same take names, lengths, rate, no extra `Take 001`, feet locked.
## Pitfalls
- 4.x scripts using `action.fcurves` raise AttributeError on 5.0+; `fcurves.new(action_group=)` became `group_name=`.
- Assigning an action without a matching slot: the rig looks unanimated. 5.0 Python FBX/BVH imports name every slot "Slot".
- An active action left on the rig while exporting NLA strips (it is added on top of every clip).
- Default FBX `bake_anim_use_all_actions` exporting every action in the file onto every object.
- Non-integer clip ranges or `fps_base` != 1: Unreal does not import non-whole end frames correctly.
- Euler rotations wrapping (use quaternions or `bpy.ops.graph.euler_filter()` on controls).
- Animating the armature object for locomotion: no root motion in-engine.
## Engine notes
- Unreal: FBX import into the existing Skeleton; Animation Length = Exported Time (uses the action frame range), set a custom sample rate matching `scene.render.fps` (Use Default Sample Rate means 30 fps). Root motion: per sequence Enable Root Motion and Root Motion Root Lock; the Anim Blueprint's Root Motion Mode decides extraction (from Everything or Montages Only). Looping is set on the player (Sequence Player loop) or in the state machine. Retargeting: clips authored on a skeleton matching the Mannequin names, or an IK Retargeter with aligned retarget poses (A vs T).
- Unity: per-clip Loop Time, Loop Pose, Cycle Offset; root motion through Root Transform Rotation / Position (Y) / Position (XZ) with Bake Into Pose and Based Upon, and Animator "Apply Root Motion"; Generic rigs need the Root Node set; Humanoid clips retarget across Humanoid avatars (T-pose, at least 15 bones).
- Godot: glTF import, AnimationPlayer per action; set loop mode in the import dock.
