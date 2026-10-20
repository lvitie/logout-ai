# Production and scheduling
## When to use
- Breaking a milestone or feature into tasks, estimating, sequencing dependencies, risk tracking, scope cuts, milestone reviews, outsourcing handoffs.
- Not for: test planning → `qa-test-planning`; release execution → `build-ci-release`.
## Inputs
- Milestone goals and definition of done, feature list with priorities, team capacity per discipline, dependencies (tech, art, audio, external vendors, platform dates), risk register.
## Method
1. Define done per milestone stage (prototype, vertical slice, alpha: feature complete, beta: content complete, release candidate) in testable terms.
2. Break features into tasks small enough to finish in days; one owner each; name cross-discipline handoffs explicitly.
3. Sequence by dependency and risk: unknowns and long-lead items (mocap, VO, outsourcing, cert dates) first.
4. Estimate as ranges; keep a buffer; track actuals against estimates.
5. Track risks with likelihood, impact, owner, mitigation; review each milestone.
6. Cut scope early by priority (must, should, could) rather than slipping dates silently.
## Checks
- Every task has an owner, an estimate and an acceptance test; no task depends on an unscheduled one.
- Critical path identified; long-lead and external items have dates and contacts.
- Milestone review records what was planned, what shipped, and what moved.
## Pitfalls
- Planning content before the tech it depends on is proven.
- Hidden integration work between disciplines (art-to-engine, audio hookup, localization) left unscheduled.
- Crunch as a plan; buffers spent in the first month.
## Engine notes
- Unreal: plan around engine upgrade windows, shader and cook times, and editor lock conflicts on shared maps (One File Per Actor reduces them).
- Unity: plan for package and editor version upgrades and Addressables content build times.
- Godot: plan for minor-version upgrades and add-on compatibility.
