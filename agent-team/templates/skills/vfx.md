# Visual effects
## When to use
- Gameplay and environment effects: impacts, abilities, explosions, weather, ambient FX, UI effects; particle systems, flipbooks, simulation caches.
- Not for: shader code cost → `shaders`; general materials → `material-authoring`; destruction physics → `physics`.
## Inputs
- Effect brief (gameplay readability, timing, color language per team or element), reference video, budget (particle count, overdraw, GPU ms, memory), the event that triggers it.
## Method
1. Design for readability first: anticipation, impact, dissipation; shape and color tell the player what it is and whose it is.
2. Block timing with simple sprites against the animation or gameplay event; then add detail.
3. Build reusable modules or emitters; parameterize color, scale and duration for variants.
4. Set scalability per tier: spawn rate, particle cap, distance culling, LOD, fixed bounds.
5. Prefer GPU simulation for large counts and CPU where gameplay needs collision or events back.
6. Pool and recycle systems that spawn often (impacts, muzzle flashes).
## Checks
- Overdraw and GPU time checked in the worst case (many effects at once, close to camera) on the lowest tier.
- Readable against dark and bright backgrounds and for colorblind players (shape, not only hue).
- No effect left running after the owner dies or the level unloads; bounds correct (no popping).
- Verify visually in the editor or a capture and name the asset paths touched.
## Pitfalls
- Large translucent sprites close to camera (overdraw spikes).
- Unbounded spawn from gameplay spam; systems that never deactivate.
- Effects that hide enemy tells or the player character.
## Engine notes
- Unreal: Niagara (systems, emitters, modules, scalability and effect types, fixed bounds, data interfaces), Niagara Debugger, component pooling via the Pooling Method of Spawn System calls, Niagara Fluids for sims.
- Unity: VFX Graph (GPU) and Particle System (Shuriken, CPU).
- Godot: GPUParticles3D/2D with ParticleProcessMaterial, CPUParticles for low-end.
