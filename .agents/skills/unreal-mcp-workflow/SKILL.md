---
name: unreal-mcp-workflow
description: Safely inspect, edit, and validate a running Unreal Engine 5.8 editor through Epic's Unreal MCP server. Use when a request requires live editor state or actions involving actors, levels, assets, Blueprints, materials, Slate, PIE, or automation tests via the `unreal-mcp` MCP server.
---

# Unreal MCP Workflow

Use Epic's official Unreal MCP server at `http://127.0.0.1:8000/mcp`. It is live
editor control, not a substitute for source control or a build.

## Preflight

1. Confirm that `unreal-mcp` is connected. If unavailable, ask the user to open
   the editor and start `ModelContextProtocol.StartServer` or enable auto-start;
   do not pretend to inspect live state.
2. Save affected assets before a multi-asset or destructive change. Preserve
   the user's unsaved work.
3. Check whether PIE, shader compilation, Live Coding, or a C++ build is active.
   Wait for compilation; do not overlap editor tool calls with it.

## Discover tools on demand

Epic MCP normally uses tool-search mode. Do not assume tool names beyond the
meta-tools.

1. Call `list_toolsets` to find relevant capabilities.
2. Call `describe_toolset` only for the needed toolset.
3. Call the chosen operation through `call_tool`.
4. Make MCP calls sequentially. Every call runs on the editor game thread;
   never parallelize them.

Also query `AgentSkillToolset.ListSkills` when beginning unfamiliar project
work. Load only skills relevant to the request with
`AgentSkillToolset.GetSkills`; project instructions take precedence over
generic guidance.

## Edit safely

- Inspect before modifying. Report the current actor, asset, Blueprint, or
  component state that justifies the edit.
- Keep each mutation narrow and reversible. Ask before deleting, bulk-renaming,
  replacing references, recompiling many Blueprints, or changing project-wide
  settings.
- Avoid editor-only asset operations while PIE is active. Stop PIE only when
  the task requires it and the user's request authorizes the change.
- After modifying assets, save them and compile or validate the affected
  Blueprint, material, or level when the relevant tools are available.

## Verify and report

Use a live inspection or an automation test to confirm the requested outcome.
State exactly what was checked, any warnings that remain, and whether a restart
is required for native C++ or plugin changes.
