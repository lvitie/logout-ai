# Gameplay systems programming
## When to use
- Implementing game rules and player-facing behavior: characters, abilities, inventory, interaction, quests runtime, save/load, game modes, cameras in gameplay.
- Not for: enemy decision-making → `ai-behavior`; replication details → `netcode`; widgets and input plumbing → `ui-programming-input`.
## Inputs
- Design spec with rules, numbers and edge cases; the engine gameplay framework in use; save format; multiplayer requirements.
## Method
1. Map the feature onto the existing framework classes and patterns before adding new ones (components over deep inheritance).
2. Keep tunables in data assets or tables; designers must be able to change them without code.
3. Separate state, rules and presentation: rules decide, events notify, presentation (VFX, audio, UI) listens.
4. Define save data explicitly with a version number; plan migration for old saves.
5. Note replication or save-game impact when you touch state; write a test for the rule where the framework allows.
## Checks
- Verify in-game behavior (play-in-editor, automation test or log), not only that it compiles.
- Edge cases from the spec covered: death mid-action, pause, level transition, save/load mid-state, input during cutscene.
- No per-frame allocation or heavy work on the game thread; ticks disabled where events suffice.
## Pitfalls
- Gameplay logic in UI or animation code that breaks when those are skipped or changed.
- Order-of-initialization bugs (BeginPlay ordering, components not yet registered).
- Save data storing pointers or asset paths that move; no version field.
## Engine notes
- Unreal: Gameplay Framework (GameMode, GameState, PlayerController, Pawn/Character, PlayerState), Gameplay Ability System, Gameplay Tags, Enhanced Input, subsystems for global services, `USaveGame` with versioning, Game Features plugins for modular content.
- Unity: MonoBehaviour/ScriptableObject architecture or ECS (Entities) for scale; serialize saves with explicit versions.
- Godot: nodes and scenes with signals, autoloads for global services, Resources for data; `ResourceSaver` or JSON for saves.
