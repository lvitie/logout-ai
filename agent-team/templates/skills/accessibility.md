# Accessibility
## When to use
- Designing, implementing or reviewing features for players with motor, vision, hearing, cognitive or speech needs; any new UI, control scheme, audio cue or difficulty setting.
- Not for: general UX flows → `ux-ui-design` (use both together).
## Inputs
- Target guidelines (Game Accessibility Guidelines, Xbox Accessibility Guidelines, platform requirements), the feature spec, input map, UI style guide, audio cue list.
## Method
1. Audit the feature against the target guidelines; list gaps by category (motor, vision, hearing, cognitive).
2. Motor: full remapping (including mouse buttons), hold-to-toggle options, no required rapid pressing, adjustable timing windows.
3. Vision: scalable text and UI, contrast, no color-only information, colorblind-safe palettes, screen reader or narration for menus where supported.
4. Hearing: subtitles with speaker names, size and background options; captions for important sounds; visual cues for directional audio.
5. Cognitive: objective reminders, difficulty and assist options, pause anywhere in single player, reduced motion and camera shake options.
6. Expose options in the settings menu with clear descriptions and safe defaults; persist them per profile.
## Checks
- Playable start to finish with each option set (for example one-handed remap, subtitles on and sound off).
- Text size and contrast meet the target; colorblind simulation reviewed.
- Settings persist across restart and profile switch.
## Pitfalls
- Options added late as toggles that break layout or are not saved.
- Subtitles too long for reading speed or missing speaker labels; QTEs without alternatives.
- Remapping that misses menu or debug-only bindings, or conflicts with platform system buttons.
## Engine notes
- Unreal: Enhanced Input with player-mappable keys, Common UI, subtitles from Dialogue Waves and Sound Waves (`FSubtitleManager`), Set Color Vision Deficiency Type for simulation, Slate screen reader support for menus.
- Unity: Input System rebinding UI, Accessibility module (screen reader APIs for mobile in Unity 2023.2+), UI Toolkit scaling.
- Godot: InputMap remapping at runtime, Theme font sizes, `DisplayServer` TTS API for narration.
