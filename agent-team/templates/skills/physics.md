# Physics and collision
## When to use
- Collision setup, rigid bodies, character movement collision, ragdolls, destruction, vehicles, cloth, physics queries (traces, overlaps) and physics performance.
- Not for: character movement feel as design → `gameplay-systems`; networked physics replication → `netcode` (use both).
## Inputs
- Collision channel/layer matrix, physics materials, simulation settings (substeps, solver iterations), object counts, target frame rate, network model.
## Method
1. Define collision channels and presets once; every new object uses a preset, not ad-hoc settings.
2. Use simple collision shapes (boxes, capsules, convex hulls) over per-poly collision for moving objects.
3. Choose the tick: fixed or substepped physics for stable simulation; keep gameplay that depends on physics in the physics step.
4. Queries: trace against the narrowest channel; batch or async traces when many per frame.
5. Destruction and ragdolls: cap active bodies, sleep thresholds and lifetime; pool debris.
## Checks
- Stability at the lowest supported frame rate and at high frame rate (no tunneling, jitter or explosions).
- Collision matrix reviewed: player, AI, projectiles, camera, vehicles, triggers.
- Physics cost (`stat physics` or equivalent) within budget in the heaviest scenario.
## Pitfalls
- Frame-rate-dependent forces applied outside the physics step.
- Mesh scale baked into collision with non-uniform scale; complex-as-simple collision on moving actors.
- Determinism assumed across platforms or clients (physics is generally not deterministic).
## Engine notes
- Unreal: Chaos physics (collision profiles, physics materials, substepping, async physics tick), Chaos Destruction (Geometry Collections), Chaos Vehicles, Chaos Cloth, Physics Asset Editor for ragdolls; Chaos Visual Debugger.
- Unity: PhysX-based 3D physics and Box2D 2D physics (layer collision matrix, FixedUpdate), Unity Physics/Havok for Entities.
- Godot: Godot Physics or Jolt (built-in option from 4.4); `_physics_process`, collision layers and masks.
