Review against the spec and plan: <task folder>/opened.txt, changes.diff, the
report, and for visual work the packet/ renders and numbers. Read added files directly. On a bundled run the report starts with the plan: check it as well; the bar is the same on every route.
Max 8 bullets, must-fix issues only, one per line as `- file: problem -> fix`; no praise or
summary of what passed. If earlier findings are listed, check they are fixed. Use the changed-files
list to read only the hunks you need.
End with VERDICT: PASS or VERDICT: FAIL. On FAIL also add SEVERITY: minor|major|critical
(minor = small fixes the same agent can make; major = wrong approach or missed requirement, needs a stronger
model; critical = fundamentally broken or unsafe). Add ESCALATE: yes <reason> only when this needs a stronger
model or the user regardless of severity (a PASS with ESCALATE counts as a fail).
