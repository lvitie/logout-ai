---
name: graphify
description: Build, update, query, and inspect persistent Graphify knowledge graphs for code, documents, papers, images, and cross-repository research. Use when the user invokes Graphify, asks for a knowledge graph, wants architecture or relationship analysis backed by `graphify-out/graph.json`, or asks a project question where an existing Graphify graph can provide focused context.
---

# Graphify

Use the `graphify` CLI to create and query persistent knowledge graphs. Treat
the graph as an orientation and retrieval aid, then verify implementation
claims against the source files before changing code.

## Choose the operation

1. Check for `graphify-out/graph.json` in the working directory.
2. For a natural-language project question with an existing graph, query it
   before broad repository reads:

   ```sh
   graphify query "<question>"
   ```

3. Use `graphify explain "<node>"` for one concept or `graphify path "<A>"
   "<B>"` for a relationship trace.
4. Use `graphify update <path>` for an explicitly requested incremental code
   refresh.
5. Use `graphify extract <path>` only when the user asks to build or rebuild a
   graph. Select an explicit backend when more than one configured provider is
   plausible.
6. Use `graphify clone <github-url>` and `graphify merge-graphs` only when the
   user asks for remote or cross-repository analysis.

## Expected outputs

A full extraction writes its results under `<path>/graphify-out/`, including:

- `graph.json` for machine-readable graph data and later queries.
- `graph.html` for interactive exploration when visualization is enabled.
- `GRAPH_REPORT.md` for a plain-language audit report.

Report which graph and operation were used. For queries, summarize the relevant
nodes and edges instead of pasting the entire traversal.

## Guardrails

- If `graphify` is unavailable, report that first. Ask before installing
  `graphifyy`; package installation changes external state.
- Do not create a new graph merely because the skill triggered for a project
  question. Fall back to normal source inspection when no graph exists and the
  user did not request extraction.
- Tell the user which semantic backend will run before an extraction that can
  consume paid API tokens or send corpus content to an external model.
- Treat `graphify-out/` as user-owned generated data. Do not delete, purge, or
  force-overwrite it without explicit authorization.
- Do not treat inferred graph edges as verified facts. Check the relevant
  source, documentation, or artifact before implementation.
- Use `graphify --help` as the source of truth when installed CLI behavior
  differs from these examples.
