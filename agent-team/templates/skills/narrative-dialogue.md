# Narrative, quests and dialogue
## When to use
- Writing or structuring story, quests, branching dialogue, barks, item and lore text, or the data that drives them.
- Not for: VO recording and audio → `sound-music`; translation pipeline → `localization`; level layout → `level-design`.
## Inputs
- Story bible and character sheets, quest list and dependencies, dialogue system format, character and line-length limits, rating target, localization constraints.
## Method
1. Outline the quest as states and transitions (start, steps, fail, complete, abandoned) with the world facts each reads and writes.
2. Write dialogue in the project's tool or format with a stable unique line ID per line; speaker, context note and emotion for VO and translators.
3. Branching: track every flag a choice sets and where it is read; avoid branches that never reconverge unless intended.
4. Barks: write variants per trigger with cooldown and priority; keep them short.
5. Hand off: line IDs, speaker, context and max duration to audio; strings to localization.
## Checks
- Every quest state is reachable and has an exit; no soft-locks when the player sequence-breaks or reloads.
- No orphaned flags or lines; every line ID unique and referenced.
- Line lengths fit the UI at the longest supported language (allow about 30 percent growth).
- Content matches the rating target (language, violence descriptors).
## Pitfalls
- Hard-coded strings or concatenated sentences (untranslatable grammar).
- Changing a recorded line's text without flagging re-record and re-translation.
- Quest logic depending on load order or save data that older saves lack.
## Engine notes
- Unreal: String Tables and FText for all player-facing text, Dialogue Wave and Dialogue Voice assets, StateTree or custom quest subsystems; common third-party tools: articy:draft, Yarn Spinner, Ink.
- Unity: Localization package string tables, Yarn Spinner or Ink integrations, Timeline for scripted scenes.
- Godot: translation CSV/PO with `tr()`, Dialogue Manager or similar add-ons, Resources for quest data.
