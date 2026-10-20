# Analytics and telemetry
## When to use
- Designing telemetry events, dashboards, funnels, retention and balance analysis, A/B tests, development telemetry (crash, performance, heatmaps).
- Not for: progression and live-event design → `live-ops-progression`; privacy law review → `legal-ratings` (consult for any personal data).
## Inputs
- Questions the team needs answered, the telemetry pipeline and schema, privacy and consent requirements per region and platform, existing dashboards.
## Method
1. Start from questions ("where do players quit the tutorial?"), then define events that answer them; no event without a question.
2. Event schema: name, version, timestamp (server time), session and build ID, anonymized player ID, parameters with units; document in a data dictionary.
3. Respect consent: no collection before consent where required; minimal data; retention period defined.
4. Batch and send asynchronously; survive offline and crash (persist and retry); cap volume.
5. Analysis: define metrics (DAU, D1/D7/D30 retention, funnel conversion, win rates) and segments; compare against a baseline or control group.
6. Development telemetry: performance and crash data per build to catch regressions early.
## Checks
- Events validated in a test build end-to-end (fired, received, schema-valid, visible in the dashboard).
- No personal data beyond the approved fields; consent off sends nothing.
- A/B tests have a hypothesis, sample size estimate and stop rule before launch.
## Pitfalls
- Logging everything (cost, noise) and nothing that answers the question.
- Client clock timestamps; event names changed without version bump, breaking dashboards.
- Reading correlation as cause; peeking at A/B results early.
## Engine notes
- Unreal: Analytics provider interface (`FAnalytics`, `IAnalyticsProvider`) with plugins for specific backends, Unreal Insights and CSV profiler for development telemetry.
- Unity: Unity Analytics (UGS) with custom events, or third-party SDKs.
- Godot: no built-in analytics; send batched JSON with HTTPRequest to the backend.
