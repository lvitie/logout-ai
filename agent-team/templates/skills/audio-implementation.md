# Audio implementation and audio programming
## When to use
- Hooking sounds and music into the game: middleware events, parameters, buses, mixes, attenuation, occlusion, dialogue playback, lip sync, audio code and audio performance.
- Not for: creating sounds, music or recording VO → `sound-music`.
## Inputs
- Event list from sound design, middleware project (Wwise/FMOD) or engine audio assets, bus and mix structure, voice/memory budgets per platform, trigger points in gameplay.
## Method
1. Keep assets and events named per the project's convention; one event per gameplay moment, variation inside the event.
2. Drive behavior with parameters (RTPC/game parameters, switches, states) from gameplay, not separate events per variant.
3. Route through buses and classes instead of per-asset volume hacks; ducking and side-chain via the mixer.
4. Spatialization: attenuation presets, occlusion/obstruction, reverb zones; listener on camera or player per design.
5. Memory and streaming: bank or chunk layout by level; stream long files; set voice limits and priorities.
6. Dialogue: play by line ID, subtitles from the same ID, lip sync data generated in the pipeline.
## Checks
- Verify by listening in-game or in the editor preview and say which events and levels were checked.
- Voice count, memory and CPU within budget in the busiest scene; profiler capture attached.
- Mix check at low and high volume, on headphones and TV speakers; no clipping on the master bus.
- Pause, slow-motion, level transitions and save/load stop or resume sounds correctly.
## Pitfalls
- Events posted every frame or never stopped (leaked looping voices).
- Bank loaded too late (first-play silence) or never unloaded.
- Mix balanced at one listening level only; dialogue masked by music and SFX.
## Engine notes
- Unreal: MetaSounds and Sound Cues, Sound Classes and Submixes, Sound Concurrency, Audio Modulation (Control Buses), attenuation and occlusion settings; Wwise and FMOD Unreal integrations; `au.Debug` commands and Audio Insights.
- Unity: AudioSource/AudioMixer, or Wwise/FMOD integrations; Audio Random Container (Unity 2023+).
- Godot: AudioStreamPlayer nodes, AudioServer buses and effects, AudioStreamInteractive and AudioStreamPlaylist for adaptive music (4.3+).
