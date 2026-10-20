# Anti-cheat and game security
## When to use
- Cheat prevention and detection, server validation of player actions, anti-tamper, secure communication, exploit fixes, protecting accounts and player data in the client.
- Not for: replication design → `netcode`; backend service design → `online-backend` (security review applies to both).
## Inputs
- Threat model (what a cheater gains: competitive advantage, currency, griefing), authority model, chosen anti-cheat middleware, known exploits and reports, platform rules.
## Method
1. Threat model first: list assets (currency, ranking, other players' experience) and attack surfaces (memory editing, packet tampering, speed hacks, botting, modified files).
2. Server-authoritative validation: check rates, ranges, cooldowns, line of sight and resource costs on the server; log rejections with context.
3. Integrate client anti-cheat middleware per its docs; keep it isolated so it can be updated without game changes.
4. Integrity: sign or hash content packages; validate save data from the network; do not trust client-reported results.
5. Detection to action: telemetry for anomalies, review queue, ban waves (delayed to hide detection signals), appeal path.
6. Never put secrets (API keys with write access, private keys) in the client.
## Checks
- Each validated action tested with a crafted bad input (too fast, out of range, wrong state) and rejected without crashing the server.
- Anti-cheat runs in shipping builds on every supported platform (including Linux/Steam Deck if offered) without blocking legitimate players.
- No secrets in the shipped binary (string scan of the packaged build).
## Pitfalls
- Security by obscurity in the client; trusting client hit detection without server checks.
- False positives banning legitimate players (overlays, accessibility tools).
- Debug commands or cheat managers left reachable in shipping builds.
## Engine notes
- Unreal: server RPC validation (`WithValidation`), `UCheatManager` stripped in Shipping, pak signing and encryption keys (kept out of the repo), Easy Anti-Cheat via Epic Online Services.
- Unity: server-authoritative Netcode checks; IL2CPP over Mono raises reverse-engineering cost; third-party anti-cheat (EAC, BattlEye) integrations.
- Godot: validate in `@rpc` handlers on the server; encrypted PCK export with a key kept out of the repo.
