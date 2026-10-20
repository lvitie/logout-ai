# Netcode and replication
## When to use
- Touching replicated state, RPCs, prediction, lag compensation, relevancy or network bandwidth in the game client/server.
- Not for: backend services, matchmaking, accounts, stores → `online-backend`; cheat protection beyond server authority → `anti-cheat-security`.
## Inputs
- The authority model, the state and events involved, tick/update rates, bandwidth budget per client, target latency and loss, player count.
## Method
1. State the authority model for each piece of state touched (server, owning client, simulated proxy) and what is replicated, when and how often.
2. Prefer replicated state over reliable RPCs for persistent facts; use unreliable for cosmetic and high-frequency data.
3. Predict locally only what the owning client controls; reconcile on server correction without visible snapping.
4. Check bandwidth, relevancy, ordering and join-in-progress; prefer server-validated actions over trusting the client.
## Checks
- Test with a listen server plus a client, and with simulated latency and packet loss where available.
- Late joiner sees correct state; host migration or reconnect behavior as specified.
- Bandwidth per client measured against budget at max player count.
- Record what was tested and what was not (dedicated server, high latency).
## Pitfalls
- Reliable RPC spam saturating the reliable buffer; state changed by RPC only (late joiners miss it).
- Logic gated on `HasAuthority` in the wrong place, running twice on listen servers.
- Floating-point or timing differences in predicted code paths.
## Engine notes
- Unreal: property replication with conditions and RepNotify, Push Model, Iris replication system (opt-in), Network Prediction / Character Movement prediction, GAS prediction keys; Network Profiler and `net.PktLag`/`net.PktLoss` emulation.
- Unity: Netcode for GameObjects (NetworkVariable, RPCs) or Netcode for Entities (prediction); Multiplayer Play Mode and the Network Simulator.
- Godot: MultiplayerSynchronizer, MultiplayerSpawner, `@rpc` annotations; test with multiple debug instances.
