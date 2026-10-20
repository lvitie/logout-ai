# Combat design
## When to use
- Designing or tuning player and enemy combat: movesets, abilities, hit reactions, enemy archetypes, weapons, encounter difficulty, game feel.
- Not for: economy and stat curves → `balancing`; encounter layout in a space → `level-design`; enemy decision logic → `ai-behavior`.
## Inputs
- Combat pillars, player verbs and controls, enemy roster, frame data or timing targets, difficulty targets (TTK, damage taken per encounter), reference clips.
## Method
1. Write each move as data: startup, active, recovery frames; damage; hit stun; cancel windows; resource cost; range and hitbox.
2. Define enemy archetypes by the question they ask the player (rush, ranged, shield, swarm) and their tells (anticipation time, audio cue).
3. Feel pass: hit stop, camera shake, VFX/SFX, controller rumble, animation cancel; tune with the animation and audio owners.
4. Build a test arena with every archetype and a dummy that logs damage and frame data.
5. Difficulty: tune by tells, aggression and enemy count before raw health/damage.
## Checks
- Every attack has a readable tell and a counterplay; no unavoidable damage unless intended.
- Frame data in data assets matches the animation (hitbox active frames align with the clip).
- Input buffering and cancel windows feel consistent at 30 and 60 fps (frame-rate independent).
- Playtest notes: time to kill, deaths per encounter, most-used move (dominance check).
## Pitfalls
- Hitboxes tied to animation bones that move with LOD or root motion differences on the network.
- Difficulty via health inflation (spongy enemies) instead of behavior.
- Feel effects stacked so much that the readability of tells drops.
## Engine notes
- Unreal: Gameplay Ability System (abilities, Gameplay Effects, Gameplay Tags, Gameplay Cues for feel), anim notify states for hit windows, `UAbilityTask` for timing.
- Unity: ScriptableObject move data, Animation Events or a timeline-driven hitbox system.
- Godot: AnimationPlayer method tracks for hit windows, Area3D hitboxes, Resources for move data.
