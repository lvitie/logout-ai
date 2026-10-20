Rules (agent team; AGENTS.md also applies):
- Write agent-to-agent handoffs in Markdown (.md). HTML is only for user reviews and blockers; never use it as an agent handoff.
- Output is read by another model: terse bullets, no prose, no restating the request/spec/plan/findings, no preamble or narration between tool calls; stay under the word cap.
- Work goes in the task's {change_noun}; leave submission to the coordinating Producer/user after review. Routed agents never submit, commit, push, revert, shelve or sync (the PATH guard refuses them).
- You may edit any file the task needs, including ones listed in user_opened.txt; the VCS note says how to treat files in other changes.
- Do not repeat work: reuse a valid existing result (task folders under {state_dir}, logs) unless its inputs changed. A suite or build that
  already passed with no change to what it covers is not re-run: cite it. After a change re-run the affected tests only, the full suite once at the end.
- Tool use: every tool result is re-sent each turn. Read a file once (Grep first, then Read with offset/limit; never cat a whole large file or
  changes.diff when the changed-files list shows where to look), do not re-read what you just wrote, batch independent calls in one turn, pipe
  noisy command output through head/tail/grep.
- Never end your turn while waiting for background work: the run is torn down after your result. Start long jobs detached, then wait inline in a bounded loop (max ~9 min per call) until they finish. Only then write your report.
- Do not report BLOCKED for something the project already approves; BLOCKED is only for things you truly cannot do (missing credentials, paid API, forbidden VCS actions).
- Performance: measure and record only. Do not optimize unless the task says so.
