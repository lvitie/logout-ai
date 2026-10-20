# Balancing: systems, economy and tuning
## When to use
- Changing tuning tables, curves, drop rates, prices, XP or damage numbers; designing or auditing an economy (sources, sinks, currencies).
- Not for: combat feel and moveset design → `combat-design`; season and live-event cadence → `live-ops-progression`.
## Inputs
- Design goal (player-facing), current data tables and curves, telemetry or playtest data if any, target metrics (time-to-kill, time-to-level, currency per hour).
## Method
1. Change data (tables, curves, data assets), not code, and change as few values as the goal allows.
2. Model first: a spreadsheet or script that computes the target metric from the data (DPS, TTK, XP/hour, net currency flow per hour per player segment).
3. Map sources and sinks per currency; every source needs a sink that scales with it.
4. Apply the change; rerun the model; then playtest or simulate the critical path.
5. Keep a short rollback note with the previous values.
## Checks
- Show the numbers: old value, new value, the intended effect, and the simulation or play evidence behind it.
- Neighbors checked: progression pacing, economy sinks and sources, and counters to the changed element.
- No dominant strategy introduced: compare the changed option against its top two alternatives.
- Edge segments checked: new player, average, top 1 percent / max level.
## Pitfalls
- Tuning against averages while the top percentile breaks the economy (inflation, farming loops).
- Changing several coupled values at once so the effect cannot be attributed.
- Rounding and integer truncation in data that compounds over levels.
## Engine notes
- Unreal: Data Tables and Curve Tables (CSV/JSON import), Data Assets, Gameplay Ability System attribute sets and Gameplay Effects; reimport rather than hand-edit binary assets.
- Unity: ScriptableObjects or imported CSV/JSON; Remote Config for live values.
- Godot: custom Resources (.tres) or JSON/CSV loaded at startup.
