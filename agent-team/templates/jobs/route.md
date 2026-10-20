Read only what you need ({docs}). Change nothing.
Write a spec, max 120 words, bullets: goal, scope, out of scope, acceptance checks.
Pick the lightest route that keeps the quality bar; every route ends in the same review gate and acceptance checks.
direct = implement, review (Mid Dev). bundled = one agent plans and implements in one run (plan first in its report), review.
planned = plan, implement, review (no plan review). complex = plan, plan review, implement, review. hard = ambiguous or very hard.
Skip the plan (direct, bundled) only if ALL hold: SIZE small, RISK low, one file or a clear spec, no design choice, easy to undo.
Use bundled over direct when a short plan helps but a separate plan stage is not worth it (small-medium, clear approach).
Use planned when the plan matters but is low risk and reversible: SIZE medium, RISK low or medium, design choices a reviewer can catch in the diff.
Always use complex or hard (plan + plan review) for: RISK high, schema, API or protocol changes, shared systems, hard to undo,
ambiguity, or when earlier attempts failed. hard = also needs the strongest planner. When unsure, go one route up.
End with:
TITLE: <max 8 words>
ROUTE: direct|bundled|planned|complex|hard|ask
DOMAIN: {domains}
RISK: low|medium|high (blast radius if wrong: data loss, shared systems, hard to undo = high)
SIZE: small|medium|large (amount of work)
ask = a user decision is needed first; put the question in the spec. Use ask only when the files cannot answer it
and a wrong guess is costly to undo; otherwise pick the likeliest option and state the assumption in the spec.
A `(needs user: ...)` suffix on the request is not a reason for ask: the user promoted the task.
Optional: add `SKILLS: name[@stage], ...` to attach task skills (extra instructions for this task only).
Only when the task needs one; a stage is plan|plan_review|implement|review (default: all stages; a bundled run counts as plan and implement). Available:
{skills}
