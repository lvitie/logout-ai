# Optimization
- Capture a baseline first with the perf-capture steps: same scenario, build and hardware; record the command and the numbers.
- Touch only the hot path the request names; no drive-by cleanups or speculative changes.
- After the change capture the same scenario again and record before and after.
- Drop any change that shows no measurable gain, and say so in the report.
