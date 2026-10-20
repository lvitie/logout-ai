# UX and UI design and UI art
## When to use
- Designing menus, HUD, flows, onboarding and tutorials; wireframes, mockups, UI art, icons and style guide.
- Not for: implementing widgets and input code → `ui-programming-input`; accessibility audit → `accessibility` (apply it alongside).
## Inputs
- Player goals per screen, information hierarchy, target platforms and input devices, resolutions and safe zones, style guide, localization and accessibility requirements.
## Method
1. Map the flow: every screen, its entry and exit, back/cancel behavior and the controller focus path.
2. Wireframe first (grey boxes), test with a click-through, then visual design.
3. Style guide: type scale, color tokens with contrast ratios, icon grid, spacing, states (normal, focused, pressed, disabled, selected).
4. UI art: export at the target scale with nine-slice margins; atlas by screen; vector or SDF where scaling matters.
5. HUD: show only what the player needs now; test readability at TV distance (10-foot UI) and on handheld.
6. Hand off: annotated mockups with states, animations, sounds and data bindings to UI programming.
## Checks
- Every screen reachable and escapable with controller, keyboard and mouse (and touch if supported).
- Text fits at the longest language; safe-zone respected at 4:3, 16:9, 21:9 if supported.
- Contrast and minimum text size meet the project's accessibility targets.
- Usability test or heuristic review notes recorded.
## Pitfalls
- Designing for mouse only; focus traps or lost focus after popups.
- Icons that rely on color alone; text baked into images (untranslatable).
- Platform-specific terms and button glyphs wrong for the platform (cert risk).
## Engine notes
- Unreal: UMG with Common UI (input routing, activatable widgets, platform glyphs via controller data), Widget Animations, safe-zone widget, texture groups for UI.
- Unity: UI Toolkit (UXML/USS) or uGUI; Canvas Scaler for resolution.
- Godot: Control nodes with Theme resources, containers for layout, focus neighbors.
