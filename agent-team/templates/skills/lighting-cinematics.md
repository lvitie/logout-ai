# Lighting, cinematics and camera
## When to use
- Scene lighting (dynamic, baked or hybrid), post-processing and color grading, reflections, time of day; cutscenes, in-game cinematics, camera work and sequencing.
- Not for: render pipeline features → `rendering`; gameplay camera code → `gameplay-systems`; character animation → `animation`.
## Inputs
- Lighting intent per area (mood, time of day, readability), color script, performance budget per tier, lighting method (fully dynamic, baked, mixed), script or storyboard for cinematics, animation and VO assets.
## Method
1. Lighting: establish key, fill and bounce; guide the player with light; check exposure range and eye adaptation limits.
2. Post: grade with the project LUT or settings; keep values consistent across areas; avoid per-area hacks.
3. Performance: limit shadow-casting dynamic lights and their radius; use lighting channels and distance fades.
4. Cinematics: storyboard, previs with blocked cameras, then final animation, lighting and VFX passes; lock edits before polish.
5. Camera: lens and composition rules per project; respect safe area and subtitles space.
6. In-engine cinematics stay skippable and survive pause, streaming and different aspect ratios.
## Checks
- Lighting reviewed on calibrated display and on the lowest tier; no light leaks or blown-out areas; readability of gameplay elements.
- Cinematic plays at target frame rate in-game; streaming ready before the cut; audio and subtitles in sync.
- Skip, pause and resume tested; works at 16:9 and any other supported aspect ratio.
- Verify visually with captures and name the asset paths touched.
## Pitfalls
- Lighting tuned only in the editor viewport with different exposure from the game.
- Baked lighting invalidated by later layout changes without a rebuild.
- Cutscenes depending on gameplay state that differs between saves.
## Engine notes
- Unreal: Lumen or baked lighting (GPU Lightmass), Post Process Volumes, Sky Atmosphere and Volumetric Clouds, Light Channels; Sequencer with Cine Camera Actor, Camera Rigs, Movie Render Queue for offline renders, Take Recorder.
- Unity: Adaptive Probe Volumes, baked GI with Progressive Lightmapper, Volume post-processing; Timeline and Cinemachine.
- Godot: SDFGI or LightmapGI, VoxelGI, WorldEnvironment; AnimationPlayer or Camera3D paths for cinematics.
