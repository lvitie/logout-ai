# Game-development agent team variant

## Status and boundary

All five phases are implemented; Phase 5 makes the game-dev preset the default of this branch. Keep the serial stage executor, the `simple`/`complex`/`hard` routes, the four
stage kinds (`plan`, `plan_review`, `implement`, `review`) and Markdown handoffs.
No workflow graph, no autonomous spawning.

Tooling note: the `team` command resolves to the main checkout's `agent-team/`.
Changes made in a worktree take effect only after they are merged into the main
checkout; test them in the worktree by running its `agent-team/` directly.

## 1. Agents

An agent is a Markdown file with frontmatter at `<templates_dir>/agents/<name>.md`
(lookup: `agents/` > `roles/` in `templates_dir`, then the bundled ones;
`name` is `[a-z0-9_]+` and equals the file name; `[roles]` keys without a file are
agents with the generic prompt line).

```markdown
---
name: technical_artist        # unique; referenced by routing
scope: materials, shaders, rigs, VFX, asset budgets
model: gpt-6.1-sol            # optional
effort: high                  # optional
---
Instructions (the agent prompt body).
```

- `name`, `scope`, instructions (the body) are required; `model`/`effort` are optional.
- `model`/`effort`, when set, are a floor under `[heuristic]` and exact without it;
  `pin: true` makes them exact (Phase 3, open question 1).
- The fixed `producer`, `mid`, `senior`, `architect`, `director` roles become the
  generic built-in agents, shipped as the default agent files. They stay usable
  as route defaults; the producer remains the routing/coordinator agent.
- A game project adds discipline agents (designer, gameplay, engine, tools,
  technical_artist, audio, qa, build_release) beside them. Agents are discipline identity
  (prompt, scope); model/effort is chosen separately (section 3).

## 2. Per-domain stage routing

`domains = [...]` stays the list of domain names. Each domain may add a
`[routing.domain.<name>]` table (singular `domain`):

```toml
[routing.domain.technical_art]
plan        = "technical_artist"
plan_review = "engine"
implement   = "technical_artist"
review      = "qa"
```

- Keys: `plan`, `plan_review`, `implement`, `review`; each names an agent.
- An unset stage uses the route's default agent for that stage.
- Validate agent names at load; reject stages absent from the selected route.
- Reviewer independence: a review/plan_review agent must differ from the
  author of the artifact it reviews, tracked in task state.
- Replaces the deprecated `[routing.domain_roles]` table; the `custom:<role>`
  side-task route is unchanged.

## 3. Heuristic for model and effort

A heuristic assigns model and effort per task and per stage from: route, domain,
risk, size, past review failures, and usage balance. It is an inspectable rule
table in config (not code), evaluated top to bottom:

```toml
[[heuristic.rule]]
name = "hard-route"
when = { route = "hard" }
min  = { tier = "high", effort = "high" }
```

The hard route keeps one tier of headroom (`high`, not `top`), so its first major
failure can still step up before going to the user.

- Tiers are an ordered ladder (`[heuristic.tiers]`, each rank naming a `[roles]`
  profile per cli); rules set a minimum tier (and/or effort), the highest applicable
  minimum wins. Settled: a rule sets a minimum only, there is no exact-tier key.
- Inputs: route and domain from routing; risk (low/medium/high) and size
  (small/medium/large) recorded at routing, missing = high/large; failures are
  task-local counts of rejected plans/implementations, not runtime errors;
  usage from existing headroom data, stale or missing disables balancing.
- Agent frontmatter `model`/`effort` is a floor (default) or, with `pin = true`, a
  pin, applied after the rules (open question 1, settled as the default below).
- Usage balance only picks an approved equivalent at or above the chosen tier;
  it never lowers a floor.
- Each launch records inputs, matched rules, resulting tier and reason in task
  state before launch, so resume reproduces it and the decision is auditable.

## 4. Skills

Agent skills (frontmatter `skill: name | path | when`) are listed in a
"Skills you have" table of paths in the prompt and read on demand, not inlined.
Bundled: `technical_artist` gets `material-authoring`, `shaders`, `animation`;
`engine` gets `shaders`, `optimization`, `perf-capture`; `gameplay` gets
`animation`; `designer` gets `level-design`, `balancing`. A row duplicated by a
task skill is dropped. The rest of this section is about task skills.

Task skills are task-specific Markdown files, not domain-bound.

- Attached per task or per stage: `team new --skill name[@stage]` (repeatable)
  or a `SKILLS:` line from the producer at routing. No stage = every stage.
- Appended to the prompt (`## Skill: <name>`, after the request) only for that
  task and stage; never part of an agent definition or applied to every task of
  a domain. Never applied to the route and refill stages.
- Referenced by name; looked up in `<templates_dir>/skills/<name>.md`, then the
  bundled `agent-team/templates/skills/`.
- Unknown skills: the user's `--skill` is rejected at attach time (no task is
  created); a producer suggestion with an unknown name or stage is dropped with
  a warning. A skill file deleted after attach fails that stage with a reason.

## 5. Escalation

- Escalation keeps the same agent definition and steps model/effort up one tier
  on the ladder.
- Capped at the strongest configured tier; if the failure persists there,
  escalate to the user (HTML blocker).
- Reviewers end with `SEVERITY: minor|major|critical`, or an explicit
  escalation recommendation with a reason. The heuristic reads it: minor = no
  step, major = one tier, critical or explicit recommendation = one tier plus a
  diagnosis requirement.
- Existing mechanisms map onto these rules:
  - `[routing.takeover.<role>]` (`after_reviews`, `after_attempt`) becomes a
    tier step-up for the same agent; `to` (a different agent) remains only as an
    explicit, validated reassignment.
  - `[routing.after_impl_fails]` becomes the failure-count rule that steps up a
    tier after N rejected implementations.
- Phase 4 behavior: steps are recorded per task (`stepped`) and apply as a floor;
  one failure gives at most one step; `takeover` without `to` and
  `after_impl_fails` (`role` ignored) step the same agent; a pin, a
  `role_override` or a missing ladder goes straight to the user; `max_rounds`
  counts minor rounds only. The stage's own `[roles]` profile is a floor: a ladder
  without rules changes no model until a step-up. Setup writes the ladder plus
  the `hard-route`, `high-risk` and `repeat-failures` rules.
- Never lower a floor on retry; never reuse the author as its own reviewer.

## Open questions

1. Floor versus pin (settled in Phase 3): a flag. `model`/`effort` are a
   floor, `pin = true` makes them exact.
2. Where does the tier ladder live (`[heuristic.tiers]`) and who validates model
   availability per account?
3. Severity lines (settled in Phase 4): `SEVERITY:` and `ESCALATE: yes <reason>`
   are parsed like `VERDICT:`; a missing or invalid severity on a failing review
   is major.
4. Per-stage skills: task state only (`team new --skill name@stage`, producer
   `SKILLS:`), not in `[routing.domain.<name>]`. Decided in Phase 2.
5. Migration of `domain_roles`, `takeover` and `after_impl_fails` configs:
   deprecate with warnings, or convert once on `team setup`?
6. Do in-flight tasks keep their snapshotted pipeline/heuristic decisions after
   a config edit? Default: yes.

## Implementation plan

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| 1. Agents and per-stage selection | Agent loader for `<templates_dir>/agents/*.md`; built-in generic agents; `[routing.domain.<name>]`; validation; legacy `domain_roles` still loads | Legacy configs load unchanged; unit tests for frontmatter, unknown names, reviewer independence |
| 2. Skills (done) | Per-task/stage skill attach, append-only prompt assembly | Skill appears only in the attached task's prompt; unknown skill rejected |
| 3. Heuristic (done) | Config rule table, tier ladder, input recording, usage balance, per-launch decision record | Table-driven tests per rule and precedence; floor/pin honored; stale usage ignored |
| 4. Escalation (done) | Severity parsing, tier step-up, cap then user escalation; map `takeover` and `after_impl_fails` | Tests for minor/major/critical, cap, explicit recommendation, legacy mappings |
| 5. Game-dev preset (done) | Bundled discipline agents (designer, gameplay, engine, tools, technical_artist, audio, qa, build_release), seven domain stage tables, six task skills, ladder and rules, p4/Unreal VCS and editor/gpu/build locks in `templates/team.toml`; `team-setup` confirms and tailors them | Raw template and preset x VCS matrix load; prompts per domain; dry-run install; removal of a domain leaves no reference |

After each phase run `python3 -I -m unittest discover agent-team/tests`,
`./scripts/test-setup-agent-team.sh` and `./scripts/validate.sh`. Remember the
worktree/main-checkout note above when testing.
