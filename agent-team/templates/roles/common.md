Rules (agent team; AGENTS.md also applies):
- Write agent-to-agent handoffs in Markdown (.md). HTML is only for user reviews and blockers; never use it as an agent handoff.
- Output is read by another model: terse bullets, no prose, no restating inputs, stay under the word cap.
- Work goes in the task's {change_noun}; leave submission to the coordinating Producer/user after review. Routed agents never submit, commit, push, revert, shelve or sync (the PATH guard refuses them).
- You may edit any file the task needs, including ones listed in user_opened.txt; the VCS note says how to treat files in other changes.
- Do not repeat work: before building, capturing or generating anything, check whether a valid result already exists (task folders under {state_dir}, logs). Reuse it unless its inputs changed.
- Tests and builds: if a suite or build already passed and neither the code nor assets it covers changed since, do not re-run it; cite the earlier result. Re-run only the affected tests after a change, and the full suite once before finishing.
- Never end your turn while waiting for background work: the run is torn down after your result. Start long jobs detached, then wait inline in a bounded loop (max ~9 min per call) until they finish. Only then write your report.
- Do not report BLOCKED for something the project already approves; BLOCKED is only for things you truly cannot do (missing credentials, paid API, forbidden VCS actions).
- Performance: measure and record only. Do not optimize unless the task says so.
