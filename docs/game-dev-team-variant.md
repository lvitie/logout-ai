# Game-development agent team variant

## Status and boundary

Design proposal only. The Producer/user creates and maintains the separate
variant branch; this task changes only this document. No runtime, configuration,
role prompts, installation defaults, VCS state, or existing tasks change here.
The untracked `team/` directory is unrelated and must remain untouched.

The variant separates discipline ownership from execution model selection.
A technical artist remains a technical artist when a stronger model is needed.
Keep the existing serial stage executor and Markdown handoffs; do not introduce
a general workflow graph or autonomous agent spawning.

## Current constraints and proposed changes

Source paths below describe the current checkout. All new keys, metadata,
profiles, and paths explicitly marked proposed are future branch work.
`team.toml` means the installed project config; its bundled source is
[`agent-team/templates/team.toml`](../agent-team/templates/team.toml).

| File / symbol or setting | Current behavior | Proposed variant behavior | Main-branch compatibility |
| --- | --- | --- | --- |
| `agent-team/teamcfg.py`: `CANONICAL_ROLES`, `load` | All five keys `producer`, `mid`, `senior`, `architect`, `director` are mandatory. Extra roles are already allowed; every role needs `name`, `cli`, `model`, `effort`. | Require only the coordinator key `producer`; validate every referenced role and stage capability. Retain the four role fields and supported CLI validation. Require independent review coverage rather than legacy job titles. | Keep the legacy schema as default. Enable the new rules only for a proposed explicit `project.team_variant = "game-dev-v1"`; legacy configs keep their current errors and defaults. |
| `agent-team/teamcfg.py`: `load`; template `[routing.pipeline]` | Pipelines are configurable ordered pairs, not fixed sequences. `simple`, `complex`, `hard` must exist; only `plan`, `plan_review`, `implement`, `review` are accepted stage kinds. | Keep these route names and stage kinds initially. Validate nonempty sequences, review after implementation, and a preceding retry target for each review. Allow discipline roles in every eligible slot. No new stage kinds are needed for design/audio/art work. | Existing pairs continue to load unchanged. Any future named routes need versioned prompt/parser changes, not a loader-only relaxation. |
| `agent-team/team.py`: `pipeline`; template `[routing.domain_roles]` | A string domain owner replaces both `plan` and `implement` roles after pipeline selection; reviewers remain unchanged. `custom:<role>` returns early with one implement/review pair. | Add proposed per-domain stage bindings, separating planner, implementer, plan reviewer and final reviewer. Resolve explicit bindings before choosing execution profiles. Leave unspecified stages as routed. Forbid conflicting old/new bindings for the same domain. Validate side tasks too. | Keep `domain_roles` string semantics for legacy tasks/configs. Use the new bindings only in the variant; do not silently reinterpret existing strings. |
| `agent-team/team.py`: `step`; template `[routing.takeover.<role>]` | Takeover is already configurable for any role. `to`, `after_reviews`, `after_attempt` choose another implementation role; review count or a prior attempt triggers it. It runs after domain ownership. | First raise the execution profile within the same discipline. Only an explicitly configured compatible specialist may take over afterward. Reject automatic takeover to a reviewer who already reviewed this task. Count actual failed verdicts; do not escalate merely because an attempt exists. | Preserve current takeover behavior in legacy mode. Convert no active task implicitly; new variant tasks store their escalation policy version. |
| `agent-team/teamcfg.py`: `_role_refs` | Validates references in takeover, usage swaps, domain owners, side tasks and capacity fallback. It does not check discipline suitability or independence. | Extend reference enumeration for new stage bindings and profile-policy role references. Separately validate profile references, capabilities, domain coverage, fallback cycles and reviewer eligibility. | Preserve all existing reference checks and diagnostic locations; new checks apply to new schema fields. |
| `agent-team/team.py`: `_select_agent_role`, `run_agent`, `_run_agent_once`; template `[routing.usage]`, `capacity_fallback`, `after_impl_fails` | Budget, override, repeated failure and capacity rules can change the role; model/effort then come from that role, with `no_burst_effort` applied at launch. | Select a stable discipline role plus a separate execution profile. Apply one eligibility/floor check after every override, usage or capacity fallback. Budget/capacity changes must preserve role prompt, tools and independent reviewer identity. | Leave the existing role-swap path intact for legacy mode. No budget-driven reinterpretation of old history or counters. |

Retain `producer` deliberately: `teamcfg.main` reads its launch fields and
`team.py:route_task` invokes it by key. Removing even that key would require
additional launcher/coordinator changes. `agent-team/write_config.py` also emits
the five legacy roles through its presets; variant installation must eventually
offer a separate preset rather than replacing those presets.

### Pipeline contract for the variant

Use these proposed stage bindings, where specialist means the selected primary
domain owner and independent specialist means a fresh reviewer invocation with
the required discipline knowledge and no authorship of the reviewed work:

| Route | Ordered stages |
| --- | --- |
| `simple` | implement: specialist; review: QA |
| `complex` | plan: designer for mechanics, otherwise specialist; plan_review: independent specialist; implement: specialist; review: QA |
| `hard` | plan: engine/technical for architecture, designer for mechanics; plan_review: independent specialist; implement: specialist; review: independent specialist; review: QA |

QA must have the relevant domain capability; an unqualified general QA role
cannot be the only reviewer of rendering, replication or audio changes. Add a
qualified specialist review to `simple`/`complex` when QA lacks that coverage.
The same discipline key can supply planner and plan reviewer only through
separate identities, with the reviewer excluded from authorship of that plan.
Represent these identities in task state; fresh prompts alone do not establish
independence if the same invocation authored the artifact.

Keep retries unambiguous: one `plan` and one `implement` target per pipeline;
multiple final reviews are allowed. `step` currently retries the first matching
target using `next(...)`; validate that invariant rather than adding arbitrary
stage sequences. After a failed final review and a new implementation, rerun all
final reviews. Reviewer eligibility must be checked again after takeover,
manual overrides, usage balancing and capacity fallback.

## Proposed game role files

Proposed project override root: `game-team/`, selected by the existing
`project.templates_dir`. The files below do not exist yet and are not created
by this task. Existing `teamcfg.template`, `team.py:role_text` and `build_prompt`
already load `roles/<key>.md`, common rules and stage jobs. Share boundaries in
proposed `game-team/roles/common.md`; put discipline rules in each role file.

Defaults below copy model identifiers from `agent-team/write_config.py:CODEX`.
They are proposed local policy, not claims about current price, availability or
comparative capability. Verify account support and accepted effort values in
the implementation phase. All listed defaults use `cli = "codex"`.

| Key / proposed file under `game-team/roles/` | Scope and tools, when installed and authorized | Default model / effort | Review responsibility |
| --- | --- | --- | --- |
| `designer` / `designer.md` | Mechanics, progression, encounters, tuning specs, measurable playtest criteria. Read design docs, data tables, engine inspection and existing playtest evidence; edit design/data only as assigned. | `gpt-6.1-sol` / high | Check intent, edge cases, player comprehension and testable outcomes; flag subjective judgments for playtesting. |
| `gameplay` / `gameplay.md` | Gameplay code, abilities, input, AI and replication within approved architecture. Engine compiler, unit/automation tests, editor/PIE through available integration. | `gpt-6.1-sol` / medium | Check authority, state lifetime, interactions, save compatibility and player-facing behavior. |
| `engine` / `engine.md` | Engine integration, architecture, rendering/native systems, platform builds and crash diagnosis. Engine source, debugger, build tools, profilers and live editor inspection. | `gpt-6-astra` / high | Review architecture, threading, memory, networking and platform risks; measure performance without unsolicited optimization. |
| `tools` / `tools.md` | Editor tools, DCC automation, import/export and build scripts. Python/C++/Qt, Blender/Maya/Houdini or other project DCC APIs, batch jobs and focused tests. | `gpt-6.1-sol` / medium | Review repeatability, error recovery, file ownership, data conversion and real DCC behavior. |
| `technical_artist` / `technical_artist.md` | Materials, shaders, rigs, animation integration, VFX and asset budgets. Material editor, shader compiler, DCC tools, approved generation pipeline, GPU capture and model viewer. | `gpt-6.1-sol` / high | Inspect actual-character/editor renders, deformation and shader compatibility; record asset and performance evidence. |
| `audio` / `audio.md` | Audio implementation, events, mixing and reversible source assets. DAW/audio utilities, middleware/editor, waveform and loudness analysis, playback; generation only with authorized services. | `gpt-6.1-sol` / medium | Check event coverage, looping, clipping, mix and listening evidence; generated files alone do not establish acceptance. |
| `qa` / `qa.md` | Reproduction, regression coverage, packaged builds, input-based playthroughs and acceptance evidence. Test runner, editor, capture/playback and platform logs; fixes require a separate implementation assignment. | `gpt-6.1-sol` / high | Independent final verification, evidence provenance and missing manual/platform gates; no sign-off based solely on an implementer's report. |
| `producer` / `producer.md` | Route work, maintain scope, dependencies, locks, acceptance criteria and review packets. Coordinator/status/queue tools, planning docs and resource probes; no game implementation during routing. | `gpt-6.1-sol` / low | Check complete evidence and unresolved decisions; reserve submission, publication and branch operations for the authorized coordinator/user. |

Suggested domains: `design`, `gameplay`, `engine`, `tools`, `technical_art`,
`audio`, `qa`, `docs`. Route design to designer, technical art to technical
artist and other discipline domains to their matching role. Route docs by
subject, with producer as the fallback planner and tools as the default writer.
For cross-domain tasks, record secondary disciplines and required reviews;
split into dependent tasks if ownership or resource locks would conflict.

Tool lists are responsibilities, not grants of permissions or dependencies to
install. Preserve project rules, resource locks, guarded VCS and explicit stop
points. Editor/GPU/DCC locks serialize shared mutable sessions. A successful
headless build, generated media file or editor startup is evidence only for that
layer; live visual, listening, actual-input and target-platform gates remain
separate. Agent handoffs stay Markdown; user-facing reviews/blockers use HTML.
Perforce remains an existing adapter choice with project ownership rules; no
game-specific VCS changes are proposed here.

## Deterministic model and effort policy

### Inputs and profiles

Keep role defaults as fallback and expose a proposed opt-in execution policy.
At routing, store route/domain plus risk, size and secondary disciplines, with
the Producer's brief rationale. Validate enums rather than trusting free text.

- Risk: low = local/reversible and understood; medium = public interfaces,
  serialized assets or multi-system changes; high = replication authority,
  threading/native lifetime, save migration, platform/rendering architecture or
  potentially destructive asset conversion. Missing/invalid risk becomes high
  until clarified; it never becomes low automatically.
- Size: small = one bounded outcome in one subsystem; medium = coordinated
  changes within a discipline; large = several subsystems, migration or missing
  acceptance criteria. File count alone cannot downgrade risk. Missing size
  becomes large. Explicit estimates are advisory and recorded, not guarantees.
- Failure history: task-local `plan_rounds`, `review_rounds`, `impl_fails` and
  rejected findings for the artifact being retried. Do not infer failures from
  an attempt, elapsed time or unrelated tasks. Use max counts, not their sum,
  to avoid double-counting one rejected implementation.
- Usage: timestamped per-account headroom from existing usage machinery;
  capability registry and approved equivalent profiles are explicit config.
  Missing/stale usage (>5 minutes proposed) disables balancing for that launch.

Proposed profiles: P0 = `gpt-6.1-sol`/low, P1 = `gpt-6.1-sol`/medium,
P2 = `gpt-6.1-sol`/high, P3 = `gpt-6-astra`/high. Their ordering is a local
configured escalation ladder to validate with project outcomes. No assumption
that arbitrary provider models or effort labels are interchangeable is allowed.
Profile eligibility includes domain, stage, supported tools/context/modalities
and configured capability tier; model access must be verified before launch.

### Rule table and precedence

Apply rows 1-6 cumulatively: choose the highest minimum among applicable rows
and the role default. Then apply rows 7-9 in order. A review stage never receives
a lower profile tier than the artifact's most recent authoring stage.

| Order | Signal | Concrete rule |
| --- | --- | --- |
| 1 | Route | `simple`: P1 floor for work stages; `complex`: P2 for plan/plan_review/review, P1 for implementation; `hard`: P3 for every work stage. Producer route/refill starts P0; unresolved high-risk routing escalates to P2 before deciding. |
| 2 | Domain | Engine architecture, rendering internals and replication authority: P3. Shader/rig/asset conversion, audio runtime integration, gameplay state and tool data migrations: at least P2. Simple design copy, audio metadata and bounded tooling: route/default floor. Use the strongest secondary-domain requirement. |
| 3 | Risk | Medium: P2; high: P3. Low adds no floor. |
| 4 | Size | Medium: P2 for planning/review. Large: P3 for planning/review and at least P2 for implementation; require a plan or split work before implementation. |
| 5 | Past review failures | First rejected plan: next plan/plan_review P3. First rejected implementation: next implementation/reviews P3. Runtime/tool failures do not count as rejected reviews; two confirmed implementation failures also trigger P3 and a diagnosis requirement. Never reset the floor on retry. |
| 6 | Review safety | Preserve required independent identities and domain coverage regardless of profile. If no eligible reviewer remains, stop for a concrete reassignment decision. Extra reviews are not substitutes for missing runtime evidence. |
| 7 | Explicit overrides | Apply validated task overrides after computing floors. Higher profile is allowed; lower-than-floor, unsupported or conflicting role/identity override is rejected with a reason. No automatic bypass of acceptance gates. |
| 8 | Usage balance | Only choose among approved equivalents at or above the selected tier, with identical discipline prompt/tools. At 90% of 5-hour or 95% of 7-day usage, move to an eligible alternate account/provider profile. Otherwise use the configured default; ties use stable profile-key order. Budget never reduces effort or capability floors. |
| 9 | Capacity failure | Retry each eligible equivalent profile at most once; record attempts and detect cycles. If all are unavailable, retain the task for retry and report the exact capacity blocker. Never switch to a generic implementation role just to obtain a model. |

Examples: a simple low-risk tools correction uses P1 and QA P2; a complex
gameplay-state change uses at least P2 throughout; a simple replication-authority
fix uses P3 despite its route. A failed audio implementation review retries as
audio/P3 with independent QA/P3. Usage pressure can select an approved P3
equivalent in the last two cases, never P1.

### Routing integration and audit

1. `agent-team/templates/jobs/route.md` currently emits only title, route and
   domain. Extend the variant prompt with risk/size/secondary-domain metadata;
   `team.py:route_task` validates and persists it. Keep `ask` as a user-decision
   result. Human overrides are explicit input, not instructions embedded in logs.
2. `team.py:pipeline` resolves discipline bindings, review identities, applicable
   extra reviews and stage capability requirements. Do this before selecting
   models. Add a plan for large tasks or refuse unsafe direct implementation.
3. `team.py:step` applies failure escalation to the execution requirement first,
   then compatible takeover only when necessary. Keep stage progression and
   verdict protocol; ensure retries invalidate dependent review passes.
4. `team.py:_select_agent_role` becomes the variant entry to selection of a
   structured role/identity/profile decision. It combines floors, validated
   overrides and fresh usage. It must not run the legacy role-swap chain as well.
5. `team.py:run_agent` handles capacity using profile alternatives, checking the
   same constraints for every retry. `_run_agent_once` consumes the resolved
   decision unchanged and passes its CLI/model/effort to `agent_cmd`; disable
   the legacy `no_burst_effort` mutation in variant mode.

Proposed task-state additions: schema/policy version, validated inputs, resolved
pipeline snapshot with stable stage IDs and reviewer identities, and per-launch
selection records. Record requested/resolved role, profile, model/effort, floor
rules, override source, usage timestamp/percentages, failure counters, fallback
reason and artifact/input revision. Put logs only in ignored task state; never
record tokens, auth payloads or secret paths. Save a decision before launch so
resume reproduces it; changed inputs create a new recorded decision. Fresh
usage may alter only an equivalent profile at the next launch boundary.

## Compatibility and operational risks

| Risk | Required treatment |
| --- | --- |
| Domain owner accidentally replaces architectural planning | Stage-specific bindings; engine/designer planning remains explicit. Detect overlapping legacy/new bindings at load. |
| Takeover or budget fallback removes specialization | Preserve discipline identity/prompt/tools during profile escalation; validate any role reassignment. |
| Reviewer evaluates its own work after fallback | Track authorship and review identities across every launch; select another eligible reviewer or request reassignment. Provider diversity is desirable, not proof of independence. |
| Usage-driven downgrades hide safety regression | Enforce floors after every selection path; fail visibly when no equivalent is available. |
| Config edit changes meaning of an in-flight stage index | Snapshot pipeline and policy for new variant tasks; never recompute their stage order from edited config during resume. |
| Existing tasks contain only legacy role/history fields | Run them through the legacy path with existing counters. Do not fabricate risk or reinterpret history suffixes. Require explicit migration of an idle task, with backup and preview of remaining stages, before using variant policy. |
| Old executable reads variant state | Version state and refuse unsupported versions. Rollback uses the prior executable/config plus preserved legacy state; variant tasks remain paused until a compatible executable returns. |

## Open questions and recommended defaults

| Decision | Recommended default for implementation |
| --- | --- |
| Single engine or reusable game template? | Engine-neutral discipline roles with project engine skills/tools referenced by path; qualify UE/DCC evidence only when those tools actually run. |
| Can one model serve several roles? | Yes; separate invocation identities and independent evidence matter. Prefer an eligible alternate provider for high-risk reviews when available. |
| Should producer also design or implement? | Keep routing read-only. Assign actual work through a specialist stage; producer can plan documentation but cannot independently approve its own artifact. |
| How to calibrate tiers and budgets? | Start with repository preset identifiers and the explicit table above; log outcomes and usage without automated tuning. Validate availability and equivalence before enabling swaps. |
| When to add new routes or stage kinds? | Defer until real tasks cannot fit plan/implement/review. Media generation and playtests are tools/evidence inside existing stages. |
| Existing task migration? | Finish active legacy tasks first; opt-in migration only for idle tasks after a reviewed preview. Never migrate on load. |
| Who approves subjective art/audio/design outcomes? | User or designated project owner; QA records rendered/listening/playtest evidence and unresolved judgments. |

These defaults permit implementation planning without blocking this document.
Runtime/configuration work requires a subsequent task and its authorized scope.

## Phased implementation plan

| Phase | Deliverable and touched areas (future work) | Exit criteria / verification |
| --- | --- | --- |
| 0. Branch and baseline | Producer/user creates separate branch; record legacy configuration/task fixtures and installed model support. Preserve unrelated work. | Review this design; choose any deviations from recommended defaults. Capture one valid unchanged baseline, not repeated builds/media. |
| 1. Versioned schema | Variant discriminator, role capabilities, stage bindings, profile registry and validation in `teamcfg.py`; separate preset handling in `write_config.py` and setup entrypoints. | Legacy configs still load identically; game config needs no mid/senior/architect/director aliases. Reject unknown references, incompatible roles, cycles, empty pipelines and orphan reviews. |
| 2. Discipline templates | Create the proposed eight role files plus common rules and variant route-job override; configure review coverage and resource locks. | Inspect generated prompts for all domains, direct side tasks, read-only stages and authorship boundaries. Template/installer dry runs preserve existing project files. |
| 3. Routing and selection | Implement versioned inputs/snapshots in `route_task`/`pipeline`; profile selection and takeover in `step`, `_select_agent_role`, `run_agent`, `_run_agent_once`. | Table-driven tests cover every rule, precedence ties, invalid overrides, stale/missing usage, capacity cycles, independent reviewer preservation and no legacy effort downgrade. |
| 4. Resume and regression | Persist policy decisions, version checks and explicit migration preview; legacy path remains available. | Test interrupted/resumed tasks, config edits mid-task, plan failures, implementation failures, multiple reviews, takeover, side tasks and rollback rejection. Use fake CLIs before real account runs. |
| 5. Acceptance | Run scratch design, gameplay, technical-art and audio tasks with installed tools and existing authorized accounts. | Reuse unchanged passing artifacts; record actual editor/visual/listening/packaged-platform acceptance separately. Missing tools or human acceptance remain explicit gaps. No publication/submission without authorization. |

For each runtime/config phase, run affected tests during iteration, then
`python3 -I -m unittest discover agent-team/tests`,
`./scripts/test-setup-agent-team.sh`, `./scripts/validate.sh` and
`git diff --check` for the final changed inputs. Reuse suite results already
included in the full gate when inputs match. Run Windows setup CI where setup
changes require it. After local gates, run built-in `codex review --uncommitted`,
resolve actionable findings and rerun affected checks; unavailable review is a
readiness blocker. Keep agent reports Markdown and user review packets HTML.

For this documentation task, acceptance is coverage of constraints, the eight
roles, deterministic policy, open questions and phases; existence of all cited
current paths/symbols; Markdown diff review; repository validation; and built-in
Codex review. Proposed files are labeled above and intentionally absent.
