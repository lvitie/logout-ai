# Animation: rigs, clips, state machines and animation code
## When to use
- Rigging or skinning a character, authoring or importing clips (keyframe or mocap), retargeting, building anim graphs, montages, notifies, IK, procedural animation or animation runtime code.
- Not for: mesh sculpt/UV/bake → `character-art-pipeline`; cutscene direction and cameras → `lighting-cinematics`; gameplay rules behind an ability → `gameplay-systems`.
## Inputs
- Skeleton and reference mesh, rig spec (joint list, naming, deformation needs), clip list with frame ranges, root-motion policy, the anim graph or state machine, gameplay timing targets (frames to hit, cancel windows).
## Method
1. Identify the skeleton, the animation blueprint or state machine, and the assets involved before changing anything; do not retarget or re-export unless asked.
2. Rig: keep the deform skeleton shared across characters where possible; controls live in a separate rig layer; test extreme poses for candy-wrapping and volume loss.
3. Clips: agree on frame rate, root-motion vs in-place, loop points and foot-contact markers; name per convention.
4. Graph: keep transitions, blend times and notifies data-driven; prefer layered blends and linked layers over one giant graph.
5. Runtime code: compute on worker threads where the engine allows; no game-state queries inside the anim update.
## Checks
- Root motion, looping and foot-sync verified on each changed clip; no foot sliding at walk/run speeds.
- Notifies fire on the intended frame at every play rate; montages blend out cleanly when interrupted.
- Compression error, curve count and anim update cost recorded if they changed.
- Verified in play-in-editor or the animation preview; list the clips and states checked.
## Pitfalls
- Retargeting between skeletons with different proportions without fixing IK goals (hands miss props).
- Gameplay logic hidden in notifies that do not fire when a clip is skipped or the LOD drops update rate.
- Over-aggressive compression on hands/face; unit or axis mismatch on import (cm vs m, Y-up vs Z-up).
## Engine notes
- Unreal: Animation Blueprint with thread-safe update functions, Linked Anim Layers, Control Rig, IK Rig + IK Retargeter, Pose Search (motion matching), montages and anim notifies; profile with `stat anim` and Unreal Insights.
- Unity: Animator Controller, Playables API, Animation Rigging package; Humanoid avatars for retargeting.
- Godot: AnimationTree (state machine, blend spaces), SkeletonModifier3D / IK nodes, AnimationLibrary resources.
