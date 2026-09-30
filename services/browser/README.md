# browser service

The headed Chromium container (Xvfb + KasmVNC) with the page-level **submit guard**. This is where
the "never submit" non-negotiable is enforced, independently of browser-use/adapters.

## Files

- `guard.js` — the submit guard, injected as a Playwright init script into every page. Blocks submit
  events, Enter-key submits, and `form.submit()`/`requestSubmit()`; records each block on
  `window.__submitGuard`.
- `s2_submit_guard.py` — the S2 test (zero submits reach the mock server, every attempt logged).
- `Dockerfile` + `entrypoint.sh` — headed Chromium under Xvfb, CDP on 9222 (internal browser_net).

## Why it covers adapters + workflow replays

The guard is injected once per browser context *before any page script runs*, so every page the
browser loads — via an adapter or a workflow replay — has it active. No per-path opt-in needed.

## CDP access (the "relay")

The browser's CDP (port 9222) is exposed only on the internal `browser_net`, which the worker also
joins — so only the worker can reach `browser:9222`. CDP is never published to the LAN. (A
dedicated auth/single-client relay is a step-6 refinement if browser-use needs it.)

## Deferred to step 8

KasmVNC (human viewing for the review flow) and the review-flow link.
