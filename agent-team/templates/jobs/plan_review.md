Review the plan against the spec, AGENTS.md, and the code. Max 8 bullets,
real problems only, one per line as `- step/file: problem -> fix`; no praise or restated plan.
End with VERDICT: PASS or VERDICT: FAIL. On FAIL also add SEVERITY: minor|major|critical
(minor = small fixes the same agent can make; major = wrong approach or missed requirement, needs a stronger
model; critical = fundamentally broken or unsafe). Add ESCALATE: yes <reason> only when this needs a stronger
model or the user regardless of severity (a PASS with ESCALATE counts as a fail).
