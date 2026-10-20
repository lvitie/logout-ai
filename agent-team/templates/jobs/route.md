Read only what you need ({docs}). Change nothing.
Write a spec, max 120 words, bullets: goal, scope, out of scope, acceptance checks.
simple = routine, Mid Dev; complex = needs a plan, Senior Dev; hard = ambiguous or very hard.
End with:
TITLE: <max 8 words>
ROUTE: simple|complex|hard|ask
DOMAIN: {domains}
ask = a user decision is needed first; put the question in the spec. Use ask only when the files cannot answer it
and a wrong guess is costly to undo; otherwise pick the likeliest option and state the assumption in the spec.
A `(needs user: ...)` suffix on the request is not a reason for ask: the user promoted the task.
