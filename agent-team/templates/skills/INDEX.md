# Game-dev skills index

41 bundled task skills: skill -> AAA roles it serves -> bundled agents that list it in their `skill:` frontmatter.
Research, sources and the full role table: `docs/GAME_DEV_ROLES.md`. This file is uppercase so `list_skills` ignores it.

Each skill file has `# <Title>` (the summary the Producer sees) and the sections `## When to use`, `## Inputs`,
`## Method`, `## Checks`, `## Pitfalls`, `## Engine notes` (Unreal first, Unity/Godot where they differ), under 60 lines
and 450 words (`blender-*` DCC skills: 200 lines and 1,800 words; research and versions in `docs/BLENDER_SKILLS.md`). The "Not for" column is the boundary each skill states in its "When to use" section.
`tests/test_skill_library.py` checks that the Agents column matches the agent files.

| Skill | Roles | Agents | Not for |
| --- | --- | --- | --- |
| `accessibility` | Accessibility designer/specialist, UX designer, QA accessibility tester | designer, qa, ui | general UX flows → ux-ui-design |
| `ai-behavior` | AI programmer, technical designer (AI) | gameplay | encounter layout → level-design; combat tuning → combat-design |
| `analytics-data` | Data analyst, game analyst, telemetry engineer | designer | live-event design → live-ops-progression |
| `animation` | Animator, rigger, technical animator, animation programmer | gameplay, technical_artist | mesh/UV/bake → character-art-pipeline; cutscenes → lighting-cinematics |
| `anti-cheat-security` | Security/anti-cheat engineer, server programmer | engine | replication → netcode; services → online-backend |
| `audio-implementation` | Audio programmer, technical sound designer, audio implementer | audio | creating sounds, music, VO → sound-music |
| `balancing` | Systems designer, economy designer, balance designer | designer | combat feel → combat-design; season cadence → live-ops-progression |
| `blender-animation` | Animator, technical animator (Blender DCC) | technical_artist | in-engine anim graphs and retargeting → animation; rig building → blender-rigging |
| `blender-geometry-nodes` | Technical artist (procedural), environment/VFX artist (Blender DCC) | technical_artist, vfx | in-engine scatter and foliage → environment-props; sims → blender-vfx |
| `blender-rigging` | Rigger, technical animator (Blender DCC) | technical_artist | clips and NLA → blender-animation; in-engine skeleton setup → animation |
| `blender-vfx` | VFX artist, technical artist FX (Blender DCC) | technical_artist, vfx | in-engine Niagara/VFX Graph → vfx; game physics → physics |
| `build-ci-release` | Build/release engineer, DevOps, release manager | build_release, tools | cert rules → platform-cert; editor tools → tools-pipeline |
| `character-art-pipeline` | Concept artist (characters), character artist, creature artist, outsourcing art manager | technical_artist | rigs and animation → animation; master materials → material-authoring |
| `combat-design` | Combat designer, technical designer (combat) | designer | stat curves → balancing; layout → level-design; AI logic → ai-behavior |
| `engine-core-streaming` | Engine/core programmer, streaming/memory programmer | engine | GPU passes → rendering; one hot path → optimization |
| `environment-props` | Concept artist (environments), environment artist, prop artist, world builder | technical_artist | layout → level-design; lighting → lighting-cinematics |
| `gameplay-systems` | Gameplay programmer, technical designer/scripter | gameplay | AI → ai-behavior; replication → netcode; widgets → ui-programming-input |
| `legal-ratings` | Legal/compliance, ratings coordinator, release manager | build_release, director, narrative, qa | technical platform requirements → platform-cert |
| `level-design` | Level designer, encounter designer, world designer, quest designer (placement) | designer, narrative | final art → environment-props; AI logic → ai-behavior |
| `lighting-cinematics` | Lighting artist, cinematic designer/artist, camera designer | technical_artist | render features → rendering; gameplay camera code → gameplay-systems |
| `live-ops-progression` | Progression designer, live-ops designer/producer, community manager, monetization designer | designer | number tuning → balancing; telemetry → analytics-data |
| `localization` | Localization producer/coordinator, localization engineer, LQA tester | audio, narrative, qa, tools, ui | source text → narrative-dialogue; VO recording → sound-music |
| `material-authoring` | Technical artist (materials), material artist | technical_artist, vfx | shader code → shaders; lighting → lighting-cinematics |
| `narrative-dialogue` | Narrative designer, writer, quest designer | narrative | VO recording → sound-music; translation → localization |
| `netcode` | Network programmer, multiplayer gameplay programmer | engine, gameplay | services → online-backend; anti-cheat → anti-cheat-security |
| `online-backend` | Online/backend engineer, server engineer, platform services engineer | engine | replication → netcode; live-event design → live-ops-progression |
| `optimization` | Performance engineer, engine programmer (optimization) | engine | measure only → perf-capture |
| `perf-capture` | Performance engineer, QA performance tester, any discipline measuring a budget | audio, engine, qa, technical_artist, vfx | changing code for speed → optimization |
| `physics` | Physics programmer, vehicle programmer, technical artist (destruction/cloth) | gameplay | movement feel → gameplay-systems |
| `platform-cert` | Platform/console engineer, certification QA, release manager | build_release, engine, qa | ratings → legal-ratings; build mechanics → build-ci-release |
| `production-scheduling` | Producer, project manager, development director | director | test plans → qa-test-planning; release execution → build-ci-release |
| `qa-test-planning` | QA tester, QA lead, SDET/test automation engineer | qa | unit tests for a change → tdd; platform requirements → platform-cert |
| `rendering` | Rendering/graphics programmer | engine | one material's shader cost → shaders; scene lighting → lighting-cinematics |
| `shaders` | Graphics programmer, technical artist (shaders) | engine, technical_artist, vfx | artist materials → material-authoring; pipeline features → rendering |
| `sound-music` | Sound designer, composer, music supervisor, VO director/producer | audio | middleware hookup and audio code → audio-implementation |
| `tdd` | Any programmer (gameplay, engine, tools) | gameplay, tools | test plans and manual QA → qa-test-planning |
| `tools-pipeline` | Tools programmer, pipeline TD, technical artist (pipeline) | tools | build farm and packaging → build-ci-release |
| `ui-programming-input` | UI programmer, input programmer | gameplay, ui | mockups and UI art → ux-ui-design |
| `unreal-review` | Senior programmer/reviewer, QA (Unreal projects) | engine, qa, tools | performance work → optimization |
| `ux-ui-design` | UX designer, UI designer, UI artist, motion designer (UI) | ui | widget code → ui-programming-input |
| `vfx` | VFX artist, technical artist (FX) | technical_artist, vfx | shader cost → shaders; destruction physics → physics |
