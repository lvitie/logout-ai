Review against the spec and plan: <task folder>/opened.txt, changes.diff, the
report, and for visual work the packet/ renders and numbers. Read added files directly.
Max 8 bullets, must-fix issues only, each with file and fix. If earlier findings are
listed, check they are fixed.
End with VERDICT: PASS or VERDICT: FAIL. On FAIL also add SEVERITY: minor|major|critical
(minor = small fixes the same agent can make; major = wrong approach or missed requirement, needs a stronger
model; critical = fundamentally broken or unsafe). Add ESCALATE: yes <reason> only when this needs a stronger
model or the user regardless of severity (a PASS with ESCALATE counts as a fail).
