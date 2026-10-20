# Level, encounter and world design
## When to use
- Laying out or changing a level, space, encounter, open-world region or quest location; blockout through to handoff to environment art.
- Not for: final environment art → `environment-props`; lighting → `lighting-cinematics`; enemy AI logic → `ai-behavior`.
## Inputs
- Level brief (player goal, beats, pacing curve, metrics: jump height, run speed, cover height, door width), existing level conventions, streaming and memory budgets, enemy and pickup roster.
## Method
1. State the player goal, flow and pacing of the space first; sketch a beat chart (tension/rest) and the critical path.
2. Blockout with metric-correct primitives; keep sightlines, scale and traversal consistent with the existing levels.
3. Encounters: define entry, combat space, cover, flanks, escape, and the reward; place spawns out of view.
4. Guide the player with landmarks, light and composition before using UI markers.
5. Respect streaming, world partition and lighting-build rules; list actors and sublevels touched, and avoid changes to levels another change has opened.
6. Keep placeholders obvious and named; leave final art passes to their owners.
## Checks
- Playtest the golden path and one failure path; check navigation, triggers and checkpoints.
- Nav mesh covers every intended route; no AI or player stuck spots; no out-of-bounds exploits.
- Streaming: no hitches or pop-in on the critical path at target speed.
- Respawn/checkpoint and save/load mid-level work.
## Pitfalls
- Building art-complete before the blockout is fun; art then blocks iteration.
- Metrics drift (doors or jumps sized differently from character abilities).
- One-way gates without a soft-lock check; triggers that fail on load from save.
## Engine notes
- Unreal: World Partition (cells, Data Layers, HLOD), Level Instances / Packed Level Actors, One File Per Actor (fewer lock conflicts), PCG for scatter, Nav Mesh Bounds; edit via the cell or data layer the task names.
- Unity: scenes plus additive loading, ProBuilder for blockout, AI Navigation package for NavMesh.
- Godot: scenes as rooms/chunks, CSG for blockout, NavigationRegion3D.
