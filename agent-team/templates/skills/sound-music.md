# Sound design, music and VO content
## When to use
- Creating sound effects, ambiences, Foley, adaptive music, stingers; VO casting, recording, editing and delivery; audio asset specs.
- Not for: middleware events, mixing in-engine and audio code → `audio-implementation`.
## Inputs
- Audio direction and references, event list from design, animation and cinematic timings, music cue sheet, VO script with line IDs and context, loudness and format specs, license constraints.
## Method
1. Sound design: layer each sound (transient, body, tail); design variations to avoid repetition; name by the event list.
2. Music: write in stems and segments that can switch by game state (exploration, tension, combat, victory); define transition points and tempo/key map.
3. VO: casting brief, session scripts with line IDs, context and emotion; record with pickups planned; edit, de-noise and master to spec.
4. Deliver to the asset spec: sample rate, bit depth, channels, loudness target, naming; source files archived.
5. Track licenses for libraries, licensed music and performer agreements.
## Checks
- Loudness and peak within the project target; consistent levels across a category.
- Every event in the list has an asset or a noted gap; every VO line ID delivered for every language in scope.
- Music transitions play cleanly at each defined point in the running game.
- Listened in context (in-game or against the capture), not only in the DAW.
## Pitfalls
- Over-long tails and stereo assets where mono is spatialized (memory, positioning).
- VO line text changed after recording without re-record; missing pickups before the actor's contract ends.
- Licensed music blocked for streaming or certain regions.
## Engine notes
- Unreal: import WAV per project settings; MetaSounds for procedural sounds; Quartz for music-synced timing; Dialogue Wave assets for VO per culture.
- Unity: import settings per clip (load type, compression); adaptive music via middleware or custom scheduling with `AudioSource.PlayScheduled`.
- Godot: AudioStreamInteractive and AudioStreamSynchronized for adaptive music (4.3+); OGG for music, WAV for short SFX.
- Middleware: Wwise interactive music hierarchy, FMOD timeline with parameters and transition markers.
