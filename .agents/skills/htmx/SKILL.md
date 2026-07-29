---
name: htmx
description: Design, implement, debug, test, and review server-driven web interfaces built with HTMX 2.x, HTML templates, and minimal JavaScript. Use for hx-* attributes, HTML fragment responses, swaps and targets, out-of-band updates, boosted navigation, forms and validation, history, HX request or response headers, events, extensions, progressive enhancement, accessibility, caching, CSP, CSRF, and HTMX integration with any backend. Use the relevant backend skill as well for server implementation.
---

# HTMX Frontend

## Establish the interaction contract

1. Read the templates, routes, layout, partials, CSS, JavaScript, HTMX version,
   and content-security policy.
2. Identify the canonical full-page response, the fragment response, the
   triggering element, target, swap strategy, and browser-history behavior.
3. Trace validation and failure responses as carefully as the success path.
4. Read `references/docs-map.md` for current HTMX attributes, headers, and
   events.

## Implement

- Treat HTML as the application response format. Keep partials derived from the
  same view model and templates as full-page responses.
- Preserve direct navigation and refresh. Every history URL must return a
  complete page when requested normally.
- When response content varies on `HX-Request`, set `Vary: HX-Request` and
  ensure history restoration cannot cache a fragment as a full document.
- Choose `hx-target` and `hx-swap` deliberately. Use out-of-band swaps only for
  independent regions such as notices, counters, or shared navigation.
- Return useful validation markup with the correct status and retained user
  input. Keep focus, labels, error relationships, and keyboard behavior intact.
- Prefer semantic HTML, links, and forms that remain meaningful before adding
  `hx-boost` or more specialized attributes.
- Keep custom JavaScript small and event-driven. Reinitialize third-party
  widgets after swaps and clean them up before history snapshots.
- Keep CSRF enforcement on the server. Escape untrusted content, avoid raw HTML,
  apply a restrictive CSP, and disable HTMX processing or history caching
  around sensitive injected content when required.
- Use `$rust-web` or `$go-web` alongside this skill when those backends own the
  routes and fragment rendering.

## Validate

1. Test ordinary navigation, direct URLs, refresh, back and forward history,
   and the no-JavaScript fallback promised by the design.
2. Test HTMX requests through the real server route, including expected
   `HX-*`, cache, CSRF, validation, redirect, and error behavior.
3. Verify swap targets, focus, keyboard navigation, loading indicators, double
   submission, slow responses, and concurrent request behavior in a browser.
4. Check the browser console, network requests, response fragments, history
   state, and accessibility tree.
5. Use the repository's configured browser automation for regression coverage;
   otherwise record the manual browser paths exercised.

## Guardrails

- Do not return JSON merely to reconstruct server-owned HTML in JavaScript.
- Do not make an HTMX-only endpoint the sole representation of a navigable
  history URL.
- Do not send `HX-*` response headers on a `3xx` and expect HTMX to process
  them; use the response behavior documented for the intended transition.
- Do not put sensitive data in HTMX history snapshots or expose CSRF tokens to
  untrusted origins.
- Do not replace a working server-rendered interaction with a client-side state
  system without a concrete requirement.
