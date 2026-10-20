Read only what you need ({docs}). Change nothing.
Pick the next tasks from the plan, best first. When the planning file has no open items in its current phase,
split the next ROADMAP.md outcome into tasks and mark them `(needs user: not current phase)`. Each one is a self-contained request the Producer can route on its
own: what to build or fix and how to check it, max 40 words, naming the planning item it comes from.
The coordinator queues tasks without asking unless the line ends with a `(needs user: <why>)` suffix. Add
`(needs user: not current phase)` to a task that is not from the current phase of the planning file, and
`(needs user: <why>)` to one that needs a user decision before it can start. No parentheses inside <why>; the
suffix goes before any `(after tNNN)` note.
End with one line per task:
TASK: <request> [(needs user: <why>)]
If nothing qualifies, end with exactly: TASK: none
