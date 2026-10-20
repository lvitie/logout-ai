# Progression, live ops and community
## When to use
- Designing player progression (levels, unlocks, battle pass, seasons), live events, retention loops, store offers, patch notes and community-facing changes.
- Not for: raw number tuning → `balancing`; telemetry design → `analytics-data`; backend services → `online-backend`.
## Inputs
- Progression goals (session length, days to cap, churn points), content calendar, economy model, telemetry, community feedback, platform and store rules.
## Method
1. Draw the progression curve: time-to-unlock per reward for casual and core players; mark where content runs out.
2. Live event spec: goal, duration, entry rules, rewards, server-side config keys, kill switch and rollback.
3. Prefer server-configurable data over client patches for timed content.
4. Store and monetization: list price points, what is random, and disclosure rules per region.
5. Communicate: player-facing patch notes and known issues; plan the community response for nerfs and outages.
6. Define success metrics before launch and the dashboard that shows them.
## Checks
- Event start and end tested with time travel or server time override, including time zones and daylight saving.
- Kill switch works without a client patch; rewards granted once (idempotent) even on retry or reconnect.
- Random-reward odds disclosed where required; minors and regional rules checked with `legal-ratings`.
## Pitfalls
- Client-side clocks deciding event windows (exploitable, timezone bugs).
- FOMO-heavy design that burns out players; rewards that inflate the economy.
- Patch notes that disagree with the actual data change.
## Engine notes
- Unreal: data-driven content via Primary Data Assets and Game Feature plugins, chunked downloads; backend config through the project's online service (EOS, PlayFab or custom).
- Unity: Remote Config and Cloud Content Delivery (Unity Gaming Services), Addressables remote catalogs.
- Godot: no built-in live-ops service; fetch JSON config over HTTPRequest and load PCK patches.
