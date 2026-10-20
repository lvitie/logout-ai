# Game-dev roles and the skill library

Research behind the bundled game-dev task skills (`agent-team/templates/skills/`). Each AAA role is mapped to its
responsibilities, deliverables and the skill that covers it. Roles share a skill when their responsibilities and workflow
overlap. A separate skill exists only where the workflow or tooling differs. The result is 41 skills: the 10 earlier ones,
extended, 27 new ones, plus 4 Blender DCC skills (`docs/BLENDER_SKILLS.md`). `agent-team/templates/skills/INDEX.md` maps each skill to its roles and bundled agents and
records the scope boundaries between skills.

Research was done on 2026-10-20 with web search, studio job boards, engine docs and ratings and platform pages. See the
Sources and Caveats sections below.

## Role table

| Department | Role | Responsibilities | Deliverables | Skill |
| --- | --- | --- | --- | --- |
| Design | Systems / economy / balance designer | Economy vision, resource inflow and outflow, math models, tuning | Economy model spreadsheets, tuning tables, balance change notes | `balancing` |
| Design | Combat designer | Movesets, enemy archetypes, weapons, difficulty, game feel | Move and frame data, archetype specs, test arena | `combat-design` |
| Design | Level / encounter / world designer | Owns a level from pitch to blockout to final, pacing, encounters, world layout | Beat charts, blockouts, encounter setups, streaming layout | `level-design` |
| Design | Narrative designer / writer / quest designer | Story, quest structure, branching dialogue, barks, quest implementation | Quest state docs, dialogue scripts with line IDs, in-engine quest data | `narrative-dialogue` |
| Design | UX / UI designer | Screen flows, HUD, onboarding, usability tests | Flow maps, wireframes, annotated mockups, style guide | `ux-ui-design` |
| Design | Progression / live-ops / monetization designer | Unlock curves, seasons, events, store offers | Progression curves, event specs with kill switch, patch notes | `live-ops-progression` |
| Design | Accessibility specialist | Motor, vision, hearing, cognitive and speech options, audits | Guideline audit, options spec, test checklist | `accessibility` |
| Programming | Gameplay programmer / technical designer | Game rules, abilities, interaction, save/load, game modes | Gameplay code, data assets, automation tests | `gameplay-systems`, `tdd` |
| Programming | Engine / core programmer | Memory, threading, loading, streaming, platform layer | Core systems, memory budgets, load-time reports | `engine-core-streaming` |
| Programming | Rendering / graphics programmer | Render pipeline, lighting tech, shaders, scalability, GPU memory | Render features, scalability settings, GPU captures | `rendering`, `shaders` |
| Programming | Physics programmer | Collision, rigid bodies, ragdolls, vehicles, destruction | Collision matrix, physics settings, physics code | `physics` |
| Programming | AI programmer | Decisions, perception, navigation, crowds | Behavior trees and state trees, nav setup, AI debug tools | `ai-behavior` |
| Programming | Animation programmer | Anim graphs, IK, procedural animation, animation runtime | Anim blueprints, runtime animation code | `animation` |
| Programming | Network programmer | Replication, prediction, bandwidth | Replicated systems, network test reports | `netcode` |
| Programming | Online / backend engineer | Accounts, matchmaking, sessions, stores, cloud saves | API contracts, services, load-test results | `online-backend` |
| Programming | Audio programmer | Audio engine, middleware integration, audio performance | Audio systems, middleware hookup, voice and memory budgets | `audio-implementation` |
| Programming | UI programmer | Widgets, data binding, focus and navigation | UI code, view-models, UI performance numbers | `ui-programming-input` |
| Programming | Input programmer | Action mapping, rebinding, device switching, glyphs | Input contexts, rebinding UI support | `ui-programming-input` |
| Programming | Tools / pipeline programmer | Editor tools, importers, validators, DCC pipelines | Tools, validators, pipeline docs | `tools-pipeline` |
| Programming | Build / CI / release engineer | Build farm, CI/CD, stable builds for QA, packaging, patches | Build scripts, CI jobs, versioned builds, release checklist | `build-ci-release` |
| Programming | Platform / console engineer | First-party requirements, lifecycle, save data, achievements | Requirement checklist, platform integrations | `platform-cert` |
| Programming | Localization engineer | Text pipeline, gather/export/import, fonts, RTL | Localization tooling, pseudo-localized builds | `localization` |
| Programming | Anti-cheat / security engineer | Threat model, server validation, anti-cheat middleware | Threat model, validation code, detection telemetry | `anti-cheat-security` |
| Programming | Performance engineer | Profiling, budgets, optimization | Captures, before/after reports, fixes | `perf-capture`, `optimization` |
| Art | Concept artist | Silhouettes, turnarounds, environment key art, paintovers | Concept sheets, turnarounds, key art | `character-art-pipeline` (characters), `environment-props` (environments) |
| Art | Character / creature artist | Sculpt, retopology, UVs, bakes, textures, LODs | In-engine skeletal meshes within budget | `character-art-pipeline` |
| Art | Environment artist / world builder | Kits, set dressing, terrain, foliage | Modular kits, dressed areas, terrain | `environment-props` |
| Art | Prop artist | Hero, mid and background props | Props with LODs and collision | `environment-props` |
| Art | VFX artist | Gameplay, ability and environment effects | Particle systems with scalability | `vfx`, `blender-vfx` (Blender sims, caches, flipbooks) |
| Art | Lighting artist | World and cinematic lighting, post-processing, grading | Lit levels, post settings, lighting captures | `lighting-cinematics` |
| Art | Rigger / technical animator | Skeletons, deformation, control rigs, retargeting | Rigs, skin weights, retarget setups | `animation`, `blender-rigging` (Blender) |
| Art | Animator | Gameplay and cinematic animation, mocap cleanup | Animation clips, montages | `animation`, `blender-animation` (Blender) |
| Art | Cinematic artist / camera designer | Cutscenes, cameras, sequencing | Sequences, camera rigs, renders | `lighting-cinematics` |
| Art | UI artist | Icons, UI skins, UI motion | UI textures and atlases, icon sets, animations | `ux-ui-design` |
| Art | Technical artist | Materials, shaders, art tools and pipeline, budgets | Master materials, shader work, budgets, tools | `material-authoring`, `shaders`, `tools-pipeline`, `blender-geometry-nodes` (Blender procedural) |
| Audio | Sound designer | SFX, ambience, Foley | Sound assets to the event list | `sound-music` |
| Audio | Composer / music designer | Adaptive music in stems and segments | Music stems, transition maps | `sound-music` |
| Audio | Technical sound designer / audio implementer | Middleware events, parameters, mixes | Middleware project, banks, mix snapshots | `audio-implementation` |
| Audio | VO / dialogue producer | Casting, recording, editing, localized VO integration | Recorded and mastered lines per language, line ID coverage | `sound-music`, `localization` |
| Production | Producer / project manager | Scheduling, dependencies, risks, scope | Milestone plans, risk register, milestone reviews | `production-scheduling` |
| Quality | QA tester / lead / SDET | Test plans, bug reporting, regression, automation | Test plans, bug reports, automation suites | `qa-test-planning`, `tdd` |
| Production | Release manager | Go/no-go, release branches, submissions | Release checklist with evidence | `build-ci-release`, `platform-cert` |
| Production | Localization producer / LQA | Vendors, glossary, LQA passes | Translated builds, LQA bug reports | `localization` |
| Production | Community / live-ops manager | Player communication, events, patch notes | Patch notes, event calendar, community responses | `live-ops-progression` |
| Production | Data analyst | Telemetry design, dashboards, A/B tests | Data dictionary, dashboards, analyses | `analytics-data` |
| Production | Legal / compliance / ratings | Ratings, disclosures, privacy, licenses | Rating questionnaires, notices, license inventory | `legal-ratings` |
| Any (Unreal) | Senior reviewer | Code and asset review | Review findings | `unreal-review` |

## Bundled agents

The departments map onto the bundled agents. `designer` covers design. `narrative`, `ui` and `vfx` are new side-task
agents. `gameplay`, `engine` and `tools` cover programming. `technical_artist` and `vfx` cover art. `audio` covers audio.
`qa`, `build_release` and `director` cover production and quality.

There is no separate producer agent for production work: the `producer` only routes tasks. `director` holds
`production-scheduling`. Art roles without an agent of their own (concept, character, environment, lighting) are
covered by `technical_artist`, which has those skills. `INDEX.md` lists each agent's skills.

## Sources

**[F]**: the page was opened and its content confirmed. **[S]**: the page was seen in search results only.

Career guides and org charts:

- [F] UK Home Office, "Games Occupations (Internal Caseworker Guidance)", 2008: <https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/438850/Gamesoccupations.pdf>. Department split and job descriptions for management, design, programming (engine, graphics, audio, network, gameplay, FX) and art. Old.
- [S] Bournemouth University, games career pathways 2023: <https://www.bournemouth.ac.uk/sites/default/files/asset/document/games-career-pathways-2023.pdf>. QA and gameplay designer duties.
- [F] Riot Games jobs, filtered by craft: <https://www.riotgames.com/en/work-with-us/jobs>. Discipline taxonomy including localization, live services, data, player community, compliance, legal and information security.
- ScreenSkills games job profiles and career map (<https://www.screenskills.com/job-profiles/browse/games/>): returned 403 and could not be read.

Studio job posts:

- [F] Naughty Dog job board: <https://job-boards.greenhouse.io/naughtydog/jobs/5706469004>. Technical/level designer, environment lighting artist, gameplay animator, VFX artist, SDET, research data analyst.
- [S] PlayStation / Naughty Dog, Senior Technical Artist: <https://careers.playstation.com/senior-technical-artist/job/5530804004>. Shaders, skin and cloth rendering, art tools and pipeline.
- [S] Riot Games, Senior Game Designer (Systems: Balancing and Economy): <https://www.riotgames.com/fr/j/8063875>. Economy vision, inflow and outflow models, math.
- [S] CD PROJEKT RED, Senior Quest Designer (post now removed): <https://www.cdprojektred.com/en/jobs/22114-senior-quest-designer>. Quest implementation in UE5, design documents.
- [S] Guerrilla Games level design and lighting postings: <https://job-boards.greenhouse.io/guerrilla-games/jobs/5579533004>. Level ownership from pitch to final, the world and cinematic lighting teams.
- [S] Ubisoft, Release and Build Specialist: <https://www.ubisoft.com/en-us/company/careers/search/744000048374875--the-division-resurgence-release-build-specialist>. Build farm, CI/CD, stable builds for QA, release management.
- [S] EA, Assistant Audio Artist (localization): <https://jobs.ea.com/en_US/careers/JobDetail/Asst-Audio-Artist/213124>. Localized VO integration, mastering, QA for each language.

Accessibility:

- [F] Game Accessibility Guidelines: <https://gameaccessibilityguidelines.com/full-list/>. Motor, cognitive, vision, hearing, speech and general categories in three tiers.
- [F] Xbox Accessibility Guidelines: <https://learn.microsoft.com/en-us/gaming/accessibility/guidelines>. Guidance for designers, developers and test teams; not a compliance tool.
- [S] Xbox Wire, "Xbox Accessibility Guidelines and testing": <https://news.xbox.com/en-us/2021/02/16/xbox-accessibility-guidelines-and-testing/>.
- [S] The Last of Us Part II accessibility talk, GAConf 2020: <https://gangles.ca/talks/>.

Platform certification and ratings:

- [F] Xbox Requirements (XRs): <https://devdocs.xbox.com/publishing/certification/xbox-requirements>. Public; failures come back as an FMA report.
- [S] Xbox certification overview: <https://devdocs.xbox.com/publishing/certification/overview>.
- [S] Nintendo Developer Portal, "The Process": <https://developer.nintendo.com/the-process>.
- [F] PlayStation Partners: <https://partners.playstation.net/>. TRC is behind a login.
- [F] ESRB ratings guide: <https://www.esrb.org/ratings-guide/>.
- [F] PEGI labels: <https://pegi.info/what-do-the-labels-mean>.
- [F] IARC: <https://www.globalratings.com/>.
- [S] USK: <https://usk.de/en/?p=63389896>.
- [S] CERO: <https://www.cero.gr.jp/en/publics/index/3/>.

Engine documentation:

- Unreal Engine, all on <https://dev.epicgames.com/documentation/en-us/unreal-engine/>. [F]: World Partition, Gameplay Ability System, Unreal Insights, MetaSounds, Gauntlet, Lumen, Nanite, Common UI, Enhanced Input, StateTree, Behavior Trees and Mass Entity. [S]: BuildGraph, Iris replication and the localization tools.
- [F] Unity: Profiler (<https://docs.unity3d.com/Manual/Profiler.html>), UI Toolkit (<https://docs.unity3d.com/Manual/UIElements.html>), Addressables (<https://docs.unity3d.com/Packages/com.unity.addressables@latest/>) and Netcode for GameObjects (<https://docs.unity3d.com/Packages/com.unity.netcode.gameobjects@latest/>).
- [F] Godot, "Internationalizing games": <https://docs.godotengine.org/en/stable/tutorials/i18n/internationalizing_games.html>.

Middleware, anti-cheat, telemetry and localization:

- [S] FMOD Studio concepts and event authoring: <https://www.fmod.com/docs/studio/fmod-studio-concepts.html>, <https://www.fmod.com/docs/studio/authoring-events.html>.
- Wwise overview (<https://www.audiokinetic.com/en/wwise/overview/>): returned 403. The Wwise notes in the skills come from general knowledge, not from that page.
- [S] Easy Anti-Cheat: <https://easy.ac/>. EOS anti-cheat on Linux, Mac and Steam Deck: <https://onlineservices.epicgames.com/en-US/news/epic-online-services-launches-anti-cheat-support-for-linux-mac-and-steam-deck>.
- [S] BattlEye: <https://www.battleye.com/about/>.
- [S] GDC Vault, "Development Telemetry in Video Games Projects" (BioWare, 2010): <https://gdcvault.com/play/1012434/Development-Telemetry-in-Video-Games>.
- [S] GDC Vault, "Building Buy-In: Creating Design Tools..." (2019): <https://gdcvault.com/play/1026306/Building-Buy-In-Creating-Design>.
- [S] Game Developer, "9 Game Localization Best Practices": <https://www.gamedeveloper.com/production/9-game-localization-best-practices>. Vendor content; weak support.

## Caveats

- Titles vary by studio, for example technical designer vs scripter, audio artist vs sound designer, or release and build
  specialist vs build engineer. The table describes role functions, not exact titles.
- Job posts expire within months: several of the posts above already return 404 or "removed". Treat them as dated
  evidence, not live links.
- PlayStation TRC and Nintendo guidelines are under NDA, so `platform-cert` lists common topics only and tells agents to
  read the current documents from the developer portal. Only the Xbox XRs are public, and they change between versions.
- Ratings differ by channel: IARC covers digital storefronts, while physical and console releases go through each ratings
  body. `legal-ratings` prepares evidence and flags questions for counsel. It does not give legal advice.
- Engine docs describe tools, not who owns them. Ownership comes from the job posts and career guides.
- Small teams merge roles that AAA studios split finely (lighting, VFX, tech art, rigging). The skills are grouped by
  workflow so one agent can hold several.
- Many GDC Vault videos need a membership; only the abstracts were read.
- Engine feature names were checked against the docs listed above where possible. Some notes come from general
  knowledge: Unity and Godot add-ons, Wwise, and console SDK specifics. Version-specific features carry their version
  (for example Godot 4.3+ and Unity 2023.2+).
