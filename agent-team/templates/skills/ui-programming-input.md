# UI programming and input
## When to use
- Implementing menus, HUD, widgets, data binding, focus/navigation, input mapping, rebinding, controller/keyboard/touch handling, platform button glyphs.
- Not for: layouts, mockups and UI art → `ux-ui-design`; accessibility requirements → `accessibility` (apply both).
## Inputs
- Annotated mockups with states, the flow map, input action list per context, supported devices and platforms, localization and accessibility requirements.
## Method
1. Separate view from model: widgets read from a view-model or events; game code never reaches into widgets.
2. Define input as actions per context (gameplay, menu, vehicle) with priorities; UI consumes input only when focused.
3. Focus and navigation: explicit default focus per screen, restore focus on back, controller navigation on every interactive element.
4. Device switching: swap glyphs and prompts on last-used device; hide the mouse cursor on gamepad.
5. Text: all strings from localization tables; auto-size or wrap; no fixed-width assumptions.
6. Performance: avoid per-frame bindings for static data; invalidate or cache layout; pool list entries.
## Checks
- Every screen usable with each supported device, including hot-swapping mid-screen.
- Rebinding persists, detects conflicts and cannot unbind required actions (pause, back).
- Longest language and largest text-size setting fit; safe zone honored.
- UI CPU cost in the heaviest screen recorded.
## Pitfalls
- Input leaking through UI to gameplay (firing while a menu is open).
- Lost focus after popups, streaming or controller disconnect.
- Ticking widgets and bindings re-evaluated every frame for unchanged values.
## Engine notes
- Unreal: UMG with Common UI (activatable widget stacks, input routing, platform glyph data), Enhanced Input (Input Actions, Mapping Contexts, player-mappable keys), MVVM plugin for view-models, Invalidation and Retainer boxes for cost.
- Unity: UI Toolkit (UXML, USS, runtime binding) or uGUI with EventSystem; Input System with action maps and rebinding API.
- Godot: Control nodes, focus neighbors, Theme; InputMap with actions and `InputEvent` handling; `_unhandled_input` for gameplay.
