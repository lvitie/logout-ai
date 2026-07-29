---
name: go-web
description: Design, implement, debug, test, and operate Go web servers and HTTP APIs using net/http and the project's existing router or framework. Use for handlers, middleware, request contexts, authentication, database integration, templates, server-rendered HTML, observability, graceful shutdown, httptest coverage, concurrency, performance, or production deployment. Use htmx as well when the interface uses HTMX attributes, fragments, or HX headers.
---

# Go Web Servers

## Establish context

1. Read repository instructions, `go.mod`, `go.sum`, the configured Go
   toolchain, and existing build or generation commands.
2. Identify the router or framework, middleware chain, handler conventions,
   configuration source, persistence layer, template system, and deployment
   target.
3. Trace requests from routing through handlers, services, storage, templates,
   responses, and error handling before editing.
4. Read `references/docs-map.md` for standard-library and security guidance.

## Implement

- Preserve the existing router and architecture. Prefer `net/http` interfaces
  and explicit dependencies when they fit the project.
- Keep handlers focused on HTTP concerns and domain logic in ordinary,
  independently testable Go types and functions.
- Pass request-scoped cancellation and deadlines through `r.Context()`. Do not
  replace it with a background context inside request work.
- Configure an explicit `http.Server` with appropriate header, read, write, and
  idle timeouts for the service and streaming requirements.
- Bound request bodies before decoding, validate input, reject trailing
  unexpected data when appropriate, and use parameterized storage APIs.
- Use `html/template` for HTML. Do not bypass contextual escaping for
  user-controlled content.
- Make middleware order explicit. Recover panics at the boundary, preserve
  cancellation, and emit structured logs with request correlation.
- Avoid unbounded goroutines, queues, retries, and fan-out. Make ownership and
  shutdown of background goroutines explicit.
- Shut down with a bounded context and wait for owned background work to stop.
- When returning HTMX fragments or using `HX-*` headers, also apply `$htmx`.

## Validate

```bash
gofmt -d .
go vet ./...
go test ./...
go test -race ./...
```

1. Use `httptest` through the real router or middleware chain.
2. Cover success, malformed input, authorization, missing resources, conflict,
   timeout, cancellation, panic recovery, and internal failure paths.
3. Exercise startup, readiness, graceful shutdown, and migrations when those
   paths change.
4. Run benchmarks or focused load tests when concurrency, allocation, locking,
   pooling, or streaming behavior changes.

## Guardrails

- Do not replace the router or add a framework without a demonstrated need.
- Do not copy request contexts into long-lived state.
- Do not start goroutines without defining cancellation, error reporting, and
  ownership.
- Do not expose internal errors, secrets, SQL details, or panic output to
  clients.
- Do not make destructive schema changes without an explicit rollout and
  rollback plan.
