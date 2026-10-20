# Online services and backend
## When to use
- Accounts and identity, matchmaking, sessions and lobbies, dedicated server fleet, leaderboards, cloud saves, inventory/entitlements, stores and purchases, voice/text chat, backend APIs.
- Not for: in-game replication → `netcode`; cheat detection → `anti-cheat-security`; live-event design → `live-ops-progression`.
## Inputs
- Service provider (platform services, EOS, PlayFab, Steamworks, custom), API contracts, expected concurrency, regions, privacy requirements, platform rules on accounts and purchases.
## Method
1. Write the API contract first (request, response, errors, idempotency key, versioning); keep the client behind an interface so services can be faked in tests.
2. Treat the server as the source of truth for currency, inventory and entitlements; every grant is idempotent and logged.
3. Handle failure: timeouts, retries with backoff, offline mode, partial outages, rate limits; show the player a clear state.
4. Sessions: define host/dedicated model, region selection, backfill, reconnect window.
5. Privacy: minimal personal data, regional retention rules, account deletion path; no secrets in the client.
## Checks
- Tested against a local or staging backend with injected failures (timeout, 500, duplicate request).
- Load estimate or load test at target concurrency; cost per CCU noted.
- Purchases and grants reconcile with platform receipts; refunds and chargebacks handled.
- Credentials and keys come from deployment config, never the repo or the shipped client.
## Pitfalls
- Client-authoritative currency or inventory; trusting client timestamps.
- Retry storms after an outage (thundering herd); no jitter.
- Platform account linking edge cases (switching accounts, cross-progression merges).
## Engine notes
- Unreal: Online Subsystem (platform-specific: Steam, EOS, consoles) and the newer Online Services plugins, `UGameInstanceSubsystem` wrappers, HTTP module for custom REST; dedicated servers built as a Server target.
- Unity: Unity Gaming Services (Authentication, Lobby, Relay, Matchmaker, Cloud Save, Economy) or platform SDKs.
- Godot: HTTPRequest/HTTPClient and WebSocketPeer for custom backends; platform SDKs via GDExtension.
