---
name: rust-web
description: Design, implement, debug, test, and operate Rust web servers and HTTP APIs using the project's existing framework, commonly Axum, Actix Web, Tower, Hyper, and Tokio. Use for routing, extractors, application state, middleware, authentication, database integration, server-rendered HTML, observability, graceful shutdown, integration tests, performance, or production deployment. Use rust-cli instead for command-line-only applications and htmx for HTMX interaction design.
---

# Rust Web Servers

## Establish context

1. Read the workspace instructions, `Cargo.toml` files, lockfile, toolchain,
   Rust edition, and minimum supported Rust version.
2. Identify the existing HTTP framework, async runtime, middleware stack,
   configuration source, persistence layer, and deployment target.
3. Trace routes through extractors, handlers, domain services, persistence,
   response types, and error conversion before changing behavior.
4. Read `references/docs-map.md` for version-sensitive framework APIs.

## Implement

- Preserve the repository's framework and architectural boundaries. Keep
  handlers focused on HTTP translation and domain behavior in testable services.
- Model shared state explicitly. Prefer cheap clones of handles such as `Arc`
  rather than copying data or hiding mutable global state.
- Use typed extractors and response types. Define one deliberate mapping from
  domain failures to status codes and public error bodies.
- Propagate cancellation and deadlines. Do not block the async executor; use
  async clients or an appropriate blocking-task boundary.
- Apply middleware in a reviewed order. Include request IDs, structured
  tracing, body limits, timeouts, authentication, and compression only where
  the service needs them.
- Bound request bodies, queues, concurrency, and retries. Never retry
  non-idempotent work without an explicit idempotency design.
- Keep secrets out of source and logs. Validate untrusted input and use
  parameterized persistence APIs.
- Implement graceful shutdown so listeners stop accepting work and in-flight
  operations receive a bounded drain period.
- When returning HTMX fragments or using `HX-*` headers, also apply `$htmx`.

## Validate

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-features
```

1. Test handlers through the router or service boundary, not only as direct
   function calls.
2. Cover success, malformed input, authorization, missing resources, conflict,
   timeout, cancellation, and internal failure paths.
3. Exercise startup, readiness, graceful shutdown, and migration behavior when
   deployment or persistence changes.
4. Run focused load or concurrency checks when the change affects hot paths,
   pooling, locks, streaming, or backpressure.

## Guardrails

- Do not switch frameworks or async runtimes without a concrete requirement.
- Do not hold synchronous or async locks across `.await` unless the lock and
  critical section were designed for it.
- Do not expose internal errors, SQL details, secrets, or stack traces to
  clients.
- Do not make destructive schema changes without an explicit rollout and
  rollback plan.
