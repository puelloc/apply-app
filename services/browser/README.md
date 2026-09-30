# browser service

The headed Chromium container (Xvfb + KasmVNC) with the page-level **submit guard**. This is where
the "never submit" non-negotiable is enforced, independently of browser-use/adapters.

## Files

- `guard.js` — the submit guard, injected as a Playwright init script into every page. Blocks submit
  events, Enter-key submits, and `form.submit()`/`requestSubmit()`; records each block on
  `window.__submitGuard`.
- `s2_submit_guard.py` — the S2 test (zero submits reach the mock server, every attempt logged).

## Why it covers adapters + workflow replays

The guard is injected once per browser context *before any page script runs*, so every page the
browser loads — via an adapter or a workflow replay — has it active. No per-path opt-in needed.

## Still to build (step 5b)

The Docker image (Chromium + Xvfb + KasmVNC), the CDP relay (worker-only access to the browser), and
the per-job domain-allowlist wiring into the egress proxy.
