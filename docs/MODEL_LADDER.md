# Model/effort ladder

Five tiers per agent preset, weakest first: `low`, `mid`, `high`, `top`, `apex`. Written by
`agent-team/write_config.py` (`LADDER`, `PROFILES`) and mirrored by the claude ladder in `agent-team/templates/team.toml`
(`DEFAULT_LADDER` in `teamcfg.py` must equal it). Model ids used: those in the presets plus `claude-fable-5-1`.

## Ladder

| tier | claude | codex |
|---|---|---|
| low | sonnet-5-5 / medium | gpt-6.1-sol / medium |
| mid | sonnet-5-5 / high | gpt-6.1-sol / high |
| high | opus-5-5 / high | gpt-6-astra / medium |
| top | opus-5-5 / xhigh | gpt-6-astra / high |
| apex | claude-fable-5-1 / high | gpt-6-astra / xhigh (fallback, see below) |

- `both` carries both columns (claude entry and codex entry per tier); canonical roles keep their current cli
  (`mid`, `director` run codex; `senior`, `architect`, `producer` claude).
- Codex-only has no Claude model: its apex is the strongest codex profile, one effort step above `top`.
- Never use `max` effort: the fetched data shows little gain over `xhigh` at far higher cost.
- Apex is escalation only. No `[[heuristic.rule]]` may use `min.tier = "apex"`, and no pipeline stage, domain, side task,
  role reference or unpinned agent floor may run at the apex rank (`teamcfg._check_apex`). It is entered by review
  escalation (major/critical or `ESCALATE: yes`), `[routing.takeover]` and `[routing.after_impl_fails]`. At apex a major
  failure goes to the user. `pin = true` on an agent with the apex model is the explicit user opt-out.

## Evidence (fetched 2026-10-20)

| claim | source | value |
|---|---|---|
| Claude prices per MTok in/out | https://claude.com/pricing | Fable 5.1 $10/$50; Opus 5.5 $4/$20; Sonnet 5.5 $2/$10 |
| Fable price vs Opus | derived from the row above | 2.5x |
| GPT-6.1 Sol / GPT-6 Astra price per MTok | https://www.deeplearning.ai/the-batch/sol-nearly-eclipses-astra (secondary) | Sol $2/$10; Astra $10/$50 |
| Intelligence Index, Opus 5.5 | https://artificialanalysis.ai/models | max 58; xhigh 56; high 54 |
| Intelligence Index, Sonnet 5.5 | same | max 56 |
| Intelligence Index, Sol / Astra (max) | the-batch article citing Artificial Analysis | 52 / 53; cost per task $0.72 / $3.26 |
| Sol effort levels | the-batch article | low, medium (default), high, xhigh, max |
| Anthropic launch posts / system cards | UNVERIFIED (not fetched) | no numbers recorded |
| OpenAI launch posts (GPT-6.1 Sol, GPT-6 Astra) | UNVERIFIED (not fetched; only secondary write-ups read) | OpenAI-reported claims not used |
| Fable 5.1, Sol, Astra on artificialanalysis.ai | not on the fetched page | UNVERIFIED |

## Caveats

- Evidence is thin. No independent data for low/medium effort of any model; the ladder shape follows price and the few
  index points above, not measured per-task quality.
- `max` scores only 2 points above `xhigh` on the fetched index (Opus 5.5: max 58 vs xhigh 56) at a much higher cost per task; avoid it for cost. "`max` can score below `xhigh`" is UNVERIFIED: no fetched source shows it.
- Fable is ~2.5x Opus price and evidence for it beating Opus is mixed: hence escalation only.
- Claude escalation gains one step (low > mid > high > top > apex > user).
- Codex `hard-route` (min tier `high`, effort `high`) raises `csenior` (astra/medium) to astra/high, the same as `top`,
  so a codex hard implement escalating high > top repeats the same model and effort once. Kept as a known no-op.
- Roles named by the ladder beyond the canonical five: `mid_high`, `apex` (claude); `cmid_high`, `csenior`, `capex`
  (codex); `mid_claude`, `director_claude` (both). Codex `architect` and `director` are astra/high and rank as `top`.

## How to retune

1. Edit `PROFILES`/`LADDER` in `agent-team/write_config.py` and the claude ladder + `[roles.mid_high]`, `[roles.apex]`
   in `agent-team/templates/team.toml`; keep `DEFAULT_LADDER` in `teamcfg.py` equal to the template ladder.
2. Keep all five tiers per preset, no `max`, apex last, and only ids from the presets plus `claude-fable-5-1`.
3. Existing projects: edit `[roles.*]` and `[heuristic.tiers]` in their `team.toml` (a task keeps its snapshot).
4. Run `python3 -I -m unittest discover agent-team/tests`, `./scripts/test-setup-agent-team.sh`, `./scripts/validate.sh`.
