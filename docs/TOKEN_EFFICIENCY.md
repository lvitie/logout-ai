# Token efficiency of the agent team

Task t032. Goal: fewer input/output tokens and less wall time per task without lowering quality (first-pass review
pass rate, review rounds, escalations, test results). Verification and review gates are unchanged.

Measure with `team tokens [ids] [--runs]` (tokens, cache hit, cost, minutes per stage kind, agent and task, plus plan/review
rounds from `state.json`) and `team status <id>` (one `tokens:` line). Source: `<state_dir>/tNNN/logs/*.jsonl` (Claude `result`
event; Codex `turn.completed`, summed, cost n/a; cut-off runs are summed from assistant messages). Code: `agent-team/tokens.py`.

## Baseline (t001-t031 plus t032 so far; 251 stage runs)

| stage kind | runs | input (incl. cache reads) | avg input/run | output | cache hit | cost $ | min |
| --- | --- | --- | --- | --- | --- | --- | --- |
| plan_review | 56 | 53.8M | 961k | 397k | 96% | 36.6 | 77 |
| implement | 53 | 52.3M | 988k | 469k | 95% | 25.8 | 121 |
| review | 48 | 46.2M | 962k | 190k | 95% | 29.7 | 40 |
| plan | 58 | 9.0M | 155k | 69k | 88% | 6.4 | 12 |
| route | 31 | 3.9M | 125k | 20k | 82% | 3.3 | 5 |
| total | 251 | 171M | | 1.22M | | 108.8 | 270 |

By agent: director 54.6M / $37.3, architect 45.4M / $29.0, mid 39.1M / $16.0, senior 22.2M / $16.2, producer 3.9M / $3.3.
Only 4 runs were Codex; all findings below are Claude. Quality baseline: first `review` verdict per task 13 PASS / 16 FAIL, first
`plan_review` 3 PASS / 13 FAIL; 17 review rounds, 21 plan rounds, 5 tasks flagged failed/escalated, 29 of 33 tasks done.

## Where the input goes

- First API call of every read-only run (route, plan, plan_review, review): median 83-85k tokens. Our prompt is 4-10k chars
  (~1-3k tokens). The rest is the user's Claude environment, loaded into every headless run: 4 MCP servers
  (homarr, comfy-mcp, Claude Docs, Qt docs; ~180 tool schemas) and 58 skills / 95 slash commands.
- `--tools Read,Glob,Grep` limits built-in tools only; MCP tools stayed callable (a "read-only" reviewer could call
  `mcp__homarr__app_delete`). With write stages the schemas are deferred (first call 36k).
- Each turn re-sends the whole context, so that fixed block is paid on every turn (median 11-14 turns for reviews) as cache
  read, plus a 1 h cache write (2x price) per run: 6.4M cache-write tokens in read-only runs alone.
- Read-only runs are 114.6M of 171M input tokens and $78.5 of $108.8.
- Prompt text itself: role + skills table + common.md + job is ~2-3k tokens; spec/plan/report/findings add 1-3k. Findings
  already carry only the latest review (`s[feedback] = [out]`) and the skills table is paths only (no inlined skills unless
  attached). Not a lever.
- Tool use: 9.5 tool calls per run on average; 114 repeated `Read` of the same file; 46 tool results over 20k chars.
- Output: 1.22M tokens in total. Final handoff text is ~530k chars (~130k tokens, ~11%); narration between tool calls ~19k chars
  (~0.4%); the rest is tool-call inputs (edits/writes in implement: 830k chars) and thinking at the role's effort. Handoffs
  already have word caps (plan 200, review 8 bullets, report 120); they are not the waste.

## Findings

| # | cause | measured size | fix | expected saving | risk | status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | User MCP servers + plugin skills loaded into every Claude run | 83-85k first call on read-only runs vs ~6.5k without (measured `claude -p`, same tools); 33k vs 21k on write runs | `[agents].mcp = "write"` (read-only stages get `--strict-mcp-config`), `user_skills = false` (`--disable-slash-commands`) | read-only input per call about -85% (sample: 43k -> 13k), est. total cost about -50% | game-dev write stages keep MCP (unreal-mcp); set `mcp = "all"` if a reviewer needs MCP, `user_skills = true` for user skills | done |
| 2 | Reviewer reads all of `changes.diff` blindly | 46 tool results over 20k chars; 114 re-reads | "Changed files" list (`diff_summary`, git and p4, files +added -removed, 40 max) in review prompts; Tool-use rule in `common.md` (Grep then Read with offset/limit, no re-reads, batch calls, trim command output) | smaller tool results and fewer turns; not yet measured separately | rule is advisory; a reviewer can still read everything | done |
| 3 | Output text | ~11% of output tokens is handoff text | job templates: `- file: problem -> fix` lines, no praise or restated plan/spec, no narration (`common.md`) | small (handoffs are already ~750 tokens) | none: findings keep file + fix | done |
| 4 | Earlier findings and skills carried forward | latest findings only; skills table = paths | none needed | 0 | | already in place |
| 5 | Prompt prefix and cache | prefix (role, skills table, common, VCS note) is identical across tasks and precedes the task line; cache hit 82-96% | test that two tasks share the prefix | none beyond test | | verified |
| 6 | Effort | output is 1.2M tokens (~7% of cost); director `xhigh` plan_review averages 7k out | not lowered: review/verification effort stays; no evidence that plan (1k out) or implement effort is wasteful | 0 | quality | rejected |
| 7 | Plan_review first-pass fail rate | 13 of 16 first plan reviews failed; each extra round costs plan + plan_review (~$1-1.5) | queue line below | large, unproven | quality | follow-up |
| 8 | Visibility | none before | `team tokens`, `team status <id>` | enables measuring all of the above | none | done |

Gating changes kept intact: same reviewers, same verdict/severity/escalation rules, same word caps, same test-rerun rule.
`common.md` grew about 250 chars (the tool-use rule); at cache-read price that is far below the saving of finding 1.

## Before / after

Controlled sample: the saved prompt of `t010/05-review-architect` (read-only review, ~8k chars) run twice with
`claude -p --model claude-haiku-5-5 --effort low --tools Read,Glob,Grep`, once with the old launch flags and once with
`--strict-mcp-config --disable-slash-commands`. Both ended `VERDICT: PASS`.

| | old flags | new flags |
| --- | --- | --- |
| API turns (`num_turns`, noisy) | 6 | 13 |
| input tokens in total | 261k | 173k |
| input per turn | 43.5k | 13.3k |
| cache-write tokens | 90.9k | 21.3k |
| cost | $0.022 | $0.009 |
| wall time | 17 s | 40 s (more turns; model-driven, not flag-driven) |

Smaller probes (same machine, one-word prompt, `--tools Read,Glob,Grep`): 82,088 -> 6,467 tokens on the first call;
write stage (all built-in tools) 33,423 -> 21,193.
Haiku was used to keep the sample cheap, so absolute numbers differ from the Opus/Sonnet runs; per-call overhead is model-independent.
The turn count varied between the two runs, so judge by input per turn and cost, not by totals.

Quality of the sample: same verdict. Quality over the real pipeline is not yet known (see follow-up 1).

## Sources

Not re-fetched in this task (no web access was used); check the pages before relying on exact prices.

- Anthropic, Prompt caching: cache reads are priced at 0.1x of input, writes 1.25x (5 min) or 2x (1 h); the prefix order is
  tools, system, messages, so anything that changes early invalidates the rest. https://docs.claude.com/en/docs/build-with-claude/prompt-caching
- Claude Code, Manage costs: MCP servers add tool definitions to every request; prefer fewer servers, clear/compact context,
  delegate verbose operations. https://docs.claude.com/en/docs/claude-code/costs
- Claude Code CLI reference: `--tools`, `--strict-mcp-config`, `--mcp-config`, `--disable-slash-commands`, `--bare`.
  https://docs.claude.com/en/docs/claude-code/cli-reference (flags also confirmed with `claude --help` on this machine).
- Anthropic, Agent Skills overview: progressive disclosure (metadata always loaded, body when needed, files on demand).
  https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview
- Anthropic, Extended thinking / effort: thinking and effort drive output tokens, which are billed. https://docs.claude.com/en/docs/build-with-claude/extended-thinking
- Anthropic, Context editing and tool-result clearing: https://docs.claude.com/en/docs/build-with-claude/context-editing
- OpenAI, Prompt caching: automatic for stable prefixes of 1024+ tokens; put static content first.
  https://platform.openai.com/docs/guides/prompt-caching
- OpenAI, Reasoning guide (`reasoning.effort`): lower effort means fewer reasoning tokens. https://platform.openai.com/docs/guides/reasoning
  Codex CLI `model_reasoning_effort`, `[mcp_servers]` in `config.toml`: https://github.com/openai/codex/blob/main/docs/config.md
  The team already passes `model_reasoning_effort` per stage; Codex MCP servers were not changed (only 4 Codex runs, no data).

## Follow-up queue lines

1. `Compare quality after the token changes: first-pass review pass rate, review/plan rounds, escalations over the next 10 tasks against the baseline in docs/TOKEN_EFFICIENCY.md (team tokens)`
2. `Cut plan_review first-pass failures (13 of 16 failed): read the failed plan reviews, tighten the plan job/spec template so the first plan passes, keep the review bar`
3. `Resume the same Claude session for the fix -> re-review loop (--resume) instead of a cold start, measure input and quality`
4. `Codex stages: measure with team tokens after 20+ Codex runs, then decide on MCP/config trimming and reasoning effort per stage`
5. `Inline small changes.diff (under ~3k chars) in review prompts instead of the changed-files list; measure tool calls and turns`
6. `Add a per-task token budget to team.toml with a live.log warning when a stage runs over N turns`
