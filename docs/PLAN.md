# Summary: local job-application agent (v3)

## What I want to build
A single-user, fully open-source system in my home lab, run with Docker Compose. It works through a queue of job applications in the background, fills the forms, and parks each job on the final page. I come back later to an inbox of ready applications, submit the ones I approve, and skip the rest. It never clicks submit. Everything is exposed through a versioned API. I manage and diagnose it through an **MCP server** with my AI assistant, and I can add a UI later.

## Hardware and language
- **Raspberry Pi 5 (8GB) with SSD** runs everything except the model. All images must be arm64.
- **Separate machine runs Ollama** with **Qwen3.8-27B** (dense vision-language), `num_ctx` 64k pinned in a Modelfile, and `keep_alive` set so the model isn't unloaded between jobs. The worker reaches it over the LAN at **`ai.siggy-lab.org:11434`**, and it's firewalled to accept only the Pi. The browser can't reach it. The Ollama box is Ubuntu with an **AMD Radeon RX 7900 XT (20 GB VRAM, ROCm)**.
- **Python for everything.** Go or Rust only later, if the relay, proxy, or vault becomes a concrete problem. A future UI can be TypeScript generated from the OpenAPI schema.
- **Stack:** browser-use and workflow-use vendored at pinned commits with a lockfile and telemetry off, FastAPI, SQLite (WAL, Alembic), FastMCP, and Chromium with a persistent profile separate from my everyday browser.
- **Already verified:** Chromium, Playwright, and browser-use run headless on the Pi. Headed mode, Qwen3.8 via Ollama, and workflow-use are still unverified.

## Model configuration (Qwen3.8-27B)
- Thinking is on by default. Use thinking off or low effort for deterministic mapping and simple fills. Use higher effort only for the fallback agent and open-ended answers.
- Vision is available, but screenshots cost context and latency and are a leak surface.
- KV cache is cheap thanks to linear-attention layers. The Q4_K_M build measures **19 GB** and at 64k it does **not** fit in 20 GB VRAM (93% used, ~24% CPU offload). The **Q3_K_M build fits 100% on-GPU at 64k** (84% VRAM) and is ~2–3× faster, so Q3_K_M at 64k is the working model; Q3 drops the vision projector (see Decision log).
- The model gets only the profile fields the current form needs, never the whole profile.
- Large forms (Workday) can blow the 64k window, so the fallback agent needs DOM pruning.
- To verify: Ollama support for the architecture, the thinking controls, JSON and tool-call reliability, and whether browser-use passes parameters through.

## Docker Compose services
- **api**: the source of truth, owning the DB. The MCP server and any UI are its clients.
- **mcp**: FastMCP over streamable HTTP, calling the api with a scoped token.
- **worker**: a single worker running the queue, agents, vault, and IMAP poller, with leases and heartbeats.
- **browser**: Chromium (headed under Xvfb with KasmVNC by default), a persistent profile volume, and CDP reachable only from the worker through a relay.
- **egress-proxy**: the browser's only route out.
- **backup** (optional): restic sidecar.
- No reverse-proxy service. My existing Nginx Proxy Manager (NPM) fills that role.

**Practices:**
- Images pinned by digest, non-root, `cap_drop: ALL`, `no-new-privileges`, read-only root filesystems where possible.
- Healthchecks with `depends_on: service_healthy`, `restart: unless-stopped`, memory limits, and log rotation.
- Named volumes on the SSD for `db`, `vault`, `workflows`, `artifacts`, `browser-profile`, and a read-only `uploads` volume for resumes and cover letters.
- Docker secrets for IMAP credentials and token hashes.
- Profiles for `dev`, `test` (mock ATS sites), and `prod`.

**Networks:**
- `backend` (internal): api, mcp, and worker, plus a route to the Ollama box.
- `browser_net` (internal): worker, browser, and egress-proxy. The worker listens on nothing here.
- `egress` (non-internal): only the egress-proxy. Docker internal networks have no route out, so the proxy needs this.
- `proxy`: only the api, mcp, and KasmVNC endpoints, for NPM.
- Chromium is forced through the proxy with no bypass. It can't reach Ollama, the api, the DB, or the LAN. CDP is never published.
- If NPM runs on another machine, publish only the three proxy ports on the Pi's LAN interface, firewalled to NPM's IP.

## Egress policy
- The proxy denies private, link-local, and loopback ranges and checks the **resolved IP**, not just the hostname, to defeat DNS rebinding.
- A **per-job domain allowlist** (the job's domain plus known ATS, SSO, and CDN domains) is enforced in code, so an injected page can't send my data to an arbitrary site.
- All domains are logged.

## Reverse proxy and domain (Nginx Proxy Manager)
- NPM fronts the api, mcp, and KasmVNC over the `proxy` network. My domain is internal-only: **`siggy-lab.org`**.
- **Hostnames:** `jobs-api.siggy-lab.org`, `jobs-mcp.siggy-lab.org`, and `jobs-review.siggy-lab.org`, resolved by local DNS to NPM's LAN IP. The existing jobs-app source is already exposed separately at `jobapp.siggy-lab.org`.
- **TLS:** a Let's Encrypt wildcard cert via the DNS challenge. No port is opened to the internet.
- **Access:** an NPM access list restricted to LAN ranges, with the API's bearer tokens as the second layer.
- **Settings:** WebSockets on for KasmVNC. For MCP, proxy buffering off and a long read timeout.
- **KasmVNC access:** start with its own login plus the access list. Add an `auth_request` for short-lived tokens later.
- The API's Origin and CORS allowlists use these hostnames. It trusts `X-Forwarded-For` only from NPM's address.
- For remote access I use a VPN (WireGuard or Tailscale), never port-forwarding.

## Browser mode and Pi constraints
- **Default: headed under Xvfb + KasmVNC**, one code path, with a parked-tab cap of about 3 to 5.
- **Fallback: hybrid.** Runs happen headless (already known to work). Review and blockers happen in a headed browser that re-stages the job by replaying the workflow. The two modes can't share a profile, so the headed browser has its own profile and logs in through the vault. Each job then hits the site twice, and CAPTCHAs or one-time tokens tied to the first session may not carry over.
- Choose between them after measuring RAM per tab, page-load times, and throttling (tests P1 to P5).
- Headed Chromium under Xvfb on ARM is easy to fingerprint, so I expect some `needs_human` blockers, and I'll measure the rate.
- SSDs still fail, so backups matter. I need a good power supply and cooling.
- **Ollama is a dependency.** If it's offline, jobs wait in `queued` and I'm notified.

## Job intake
- URL normalization, ATS detection, dedupe, closed-posting checks, and job-board redirects (LinkedIn and Indeed links resolve to the employer's ATS where possible).
- Bulk import and single add, with per-domain rate limits and run windows.

## Pipeline
1. Lease a job (heartbeat, idempotent steps).
2. Check the vault: log in if an account exists, otherwise sign up. Reconcile if the state is unclear (see Accounts).
3. Extract the field schema, map it to my profile, and fill it deterministically.
4. Use per-ATS adapters for Greenhouse, Lever, and Ashby, with browser-use as the fallback.
5. Verify postconditions after each step, including resume-autoparse overwrites.
6. Stop on the final page.
7. Record a parameterized workflow, cached by ATS template and field schema and truncated before submit. Replay it next time and fall back to the agent only when a step breaks.
8. **Budgets:** per-job caps on steps, time, and tokens, loop detection, and a per-ATS circuit breaker that pauses an ATS after repeated failures.

## Files
- Each job records which resume version was used. Uploads reach the browser through the read-only `uploads` volume.
- Generated cover letters are flagged as generated in the diff.

## Async review
- Each job ends in `ready_for_review` with screenshots and a field diff (value, source, confidence, flags). In headed mode the tab is parked (TTL about 12 to 24 hours).
- I get a notification (ntfy, email, or webhook) and an optional daily digest.
- **Frozen answers:** the final answers are saved on the first run. Re-staging replays them and never regenerates them. Re-staging is the primary review path and parked tabs are an optimization.
- If the tab is gone (TTL, restart, reboot), the job becomes `stale` and re-stages when I pick it.
- `approve` means "I picked this job." It opens the review session (re-staging if needed) and never submits.
- When the parked-tab cap is hit, the queue pauses.
- `needs_human` works the same way. KasmVNC handles CAPTCHAs, phone verification, and the final submit click.
- **Post-submit record:** an immutable snapshot per application (final answers, resume version, job description, date, confirmation evidence).

## Queue states
`queued` → `running` → `awaiting_email` → `account_created` → `ready_for_review` → `submitted`

Side states: `needs_human`, `stale`, `restaging`, `skipped`, `cancelled`, `failed`, `submitted_unconfirmed`.

Submission is confirmed by a confirmation page or email, or by a manual "mark submitted" call.

## API (v1)
- OpenAPI schema, cursor pagination, filters (state, ATS, company), idempotency keys, and an audit log for every action.
- Scoped bearer tokens (hash stored, rotatable): `admin`, `ops`, and `diagnose` (read-only). Plus an Origin check and CORS allowlist.
- **Jobs:** create (single and bulk), list, get, cancel, retry, skip, requeue, restage, mark-submitted.
- **Review:** field diff and artifacts, approve, edit-answer-and-rerun, and a short-lived KasmVNC session link.
- **Blockers:** list, mark resolved, resume.
- **Profile and answers:** read and update. Only `admin` can change the profile and the answer policy.
- **Accounts:** metadata only. **No endpoint ever returns a password.**
- **Vault:** status, unseal, seal (admin only, CLI preferred).
- **Diagnostics:** job timelines, doctor, filtered logs, replay diffs, model stats, and bundle export.
- **Events:** SSE plus outbound webhooks.
- **System:** health (including Ollama), pause and resume, run windows, version.

## MCP server
- **Ops tools (about 10 to 15):** list and get jobs, enqueue, skip, retry, restage, get diff, resolve blocker, get the review link, system status, and `update_answer`, limited to **per-job overrides**. Profile and always-flag policy changes are never possible through MCP.
- **Diagnostic tools (read-only, `diagnose` scope):** `get_job_timeline`, `explain_failure`, `run_doctor`, `get_service_logs`, `get_workflow_replay_diff`, `get_model_stats`, `export_bundle`.
- **Never exposed:** vault seal or unseal, password access, token management, anything resembling submit, and no shell, Docker socket, or file access.
- Returned free text is truncated, sanitized, and marked as data. Destructive tools require confirmation. Every call is audit-logged.
- Deployed behind NPM with token auth. A local stdio server is an alternative if my assistant runs on my desktop.

## Diagnosability
- **Step events in the DB** (source of truth): job ID, run ID, step, adapter, action, postcondition result, duration, model call metadata, and a typed error code.
- **Error taxonomy:** `ollama_unreachable`, `vault_sealed`, `selector_missing`, `postcondition_failed`, `replay_diverged`, `email_timeout`, `blocker_captcha`, `submit_guard_blocked`, `budget_exceeded`, `domain_blocked`, and so on, each mapped to a cause and fix.
- Per-step screenshots and redacted DOM snippets. Structured JSON logs with correlation IDs and central redaction.
- **`doctor`:** Ollama reachable, model loaded, `num_ctx` correct, IMAP, vault state, CDP and browser, proxy, Pi memory, disk and throttling, stuck leases, migration version, and vendored commits vs the lockfile.
- A diagnostic bundle export (redacted config, versions, recent events, health).
- Debug mode is off by default. Prompt capture is time-limited and placeholders only.
- A **runbook** in the master skill maps each error code to its cause and fix.

## Accounts, vault, and email
- One alias per account on a catch-all, using a **dedicated alias subdomain or domain** with **public MX** pointing to a hosted mailbox with IMAP. My app hostnames stay internal-only.
- Codes and links are parsed deterministically from IMAP, never read by the model, with link domains allowlisted. Login codes use the same path.
- `awaiting_email` has timeouts and matches by alias and timestamp.
- **Employer replies:** map alias to application, separate verification mail from real replies, and notify me when a real reply arrives.
- The vault is encrypted with **seal/unseal**. The key is supplied at boot and lives only in worker memory. It re-seals on every reboot, so background work stalls until I unseal. I accept that trade-off. The passphrase is escrowed in my password manager.
- **Two-phase writes:** `pending` (fsynced) before signup, `confirmed` after verification or login. The exact submitted string is stored.
- **Reconcile path** for a leftover `pending` entry or "email already registered": try login, then password reset via the alias.
- Placeholders only in prompts, recordings, and logs.
- **Chromium's password manager, autofill, and sync are disabled.** The browser profile holds session cookies for every account, so it's treated as sensitive.

## Answer policy
- **Auto-fill** from my profile.
- **LLM-generate** only open-ended answers, and never invent experience.
- **Always flag** work authorization, EEO, salary, and "I certify" attestations.
- Every field records its source, shown in the diff.

## Safety, enforced in code
- **Submit guard at the page level**, not just on browser-use clicks. It blocks submit events, Enter-key submits, JS `form.submit()`, and the ATS's submit request, and it covers adapters and workflow replays. Recorded workflows are truncated before submit.
- Job pages, emails, and logs are untrusted (prompt-injection defense).
- CAPTCHAs, phone verification, and similar blockers go to `needs_human`. Nothing is bypassed.
- **Canary leak test:** sign up with a known fake password, then grep every volume, the browser profile, screenshots, traces, DOM dumps, agent history, container logs, diagnostic bundles, and MCP responses.
- Network isolation and the domain allowlist as above.

## Operations
- Optional Prometheus metrics, and a retention cron that purges screenshots and traces after N days.
- Vault, DB, workflow cache, and post-submit records are backed up on separate schedules. The restore drill includes restoring the vault and unsealing from the escrowed passphrase.
- Reboots and power cuts are handled by lease expiry, `stale` re-staging, and a sealed vault with a notification.
- A fixed eval set runs on the Ollama box before any model, quantization, thinking-mode, or `num_ctx` change. It includes sanitized snapshots of real forms, not just mocks.

## Master skill
It teaches my coding assistant to build, extend, operate, and diagnose the pipeline from the vendored source, using the runbook and diagnostic tools. It's generated from or tested against the pinned commits.

## Build order
0. **Spikes:** headed Chromium + KasmVNC on arm64 and RAM per tab (P1 to P5), Qwen3.8 on Ollama (O1 to O6), workflow-use record and replay with placeholders (W1 to W3). If workflow-use can't do it, build a thin recorder of my own.
1. Compose skeleton with the four networks, egress proxy, healthchecks, internal DNS, and NPM hosts (N and D tests).
2. Mock ATS fixtures plus sanitized real-form snapshots, and the canary leak test in CI.
3. DB schema, queue, leases, step events, error taxonomy, redacted logging, doctor, and the API skeleton with scoped auth.
4. Vault with seal/unseal, two-phase writes, and reconcile.
5. Page-level submit guard, domain allowlist, and the browser service with the CDP relay.
6. Greenhouse adapter end to end, with frozen answers, parked tabs, and re-staging.
7. Notifications, IMAP (alias domain and MX), the account flow, and employer-reply handling.
8. Workflow recording, replay, fallback, and budgets.
9. Review endpoints and KasmVNC links, then the MCP server, then more adapters.
10. Qwen eval set.
11. Backups and restore drill.
12. The master skill and runbook.
13. Optional later: a UI.

## Known risks
- ATS and job board ToS often prohibit automation (LinkedIn and Indeed actively ban it), so I need to pace requests.
- workflow-use is young and will break, so the agent fallback matters.
- Re-staging is the primary review path, so it must be as reliable as the first run.
- The Pi's 8GB may force the hybrid mode, and the Ollama box being offline blocks all work.
- Qwen3.8 is brand new, so Ollama and browser-use support may be rough.
- The MCP server is a prompt-injection path, so scopes and sanitizing matter.
- Workday, iCIMS, and Taleo per-tenant accounts are the hardest part.

---

# Verification tests

Each test has an ID so the agent can track it in the plan. Pass criteria are in brackets.

**Ollama box**
- **O1:** `ollama --version` and `ollama show <qwen3.8 tag>`. [Model loads, architecture supported.]
- **O2:** Call `/api/generate` with `num_ctx: 65536`, then `ollama ps` and `rocm-smi`. [Context is 64k and VRAM fits with headroom.]
- **O3:** Send about 60k tokens of text and compare `prompt_eval_count` with the input. [No silent truncation.]
- **O4:** Call `/api/chat` 50 times with a JSON schema in `format` and with a tool definition. [At least 98% valid. Record the failures.]
- **O5:** Try `think: false` and any effort levels, and compare token counts and latency. [Toggle is honored, and tokens per second is recorded.]
- **O6:** Test `keep_alive`, and firewalling: `curl` to `:11434` from the Pi and from another LAN host. [The Pi succeeds, the other host fails.]

**Raspberry Pi**
- **P1:** `uname -m`, `docker compose version`, and `vcgencmd get_throttled`. [aarch64, and throttled is 0x0 at idle.]
- **P2:** Run headed Chromium under Xvfb with the KasmVNC arm64 image. [Starts, and I can connect through NPM with WebSockets.]
- **P3:** Open 1, 3, and 5 tabs on real ATS pages and watch `docker stats` and `free -h`. [RAM stays under about 6GB with no swap thrash.]
- **P4:** Run browser-use with Qwen3.8 on a mock form headed vs headless and compare time, RAM, and `vcgencmd get_throttled`. [No throttling, and the decision on headed vs hybrid is recorded.]
- **P5:** Run a public bot-detection test page headed and headless. The agent asks me before visiting any third-party site. [The result is recorded as a baseline.]

**Network isolation (run from inside containers)**
- **N1:** From the browser container, reach Ollama, the api, the router, the NAS, and `169.254.169.254`. [All fail.]
- **N2:** From the browser container, reach a public site directly and through the proxy. [Direct fails, proxy works.]
- **N3:** A test hostname resolving to `127.0.0.1` or `10.x` requested through the proxy. [Blocked (rebinding defense).]
- **N4:** `nc` to the CDP port from the host, another container, and another LAN machine, and `ss -tlnp` in the worker. [Unreachable, and nothing listening on `browser_net`.]
- **N5:** Check that Chromium can't bypass the proxy, including WebRTC. [Traffic only via the proxy.]
- **N6:** A mock page instructs sending my profile to `evil.test`. [Blocked by the domain allowlist and logged.]

**NPM and DNS (some need me to run them)**
- **D1:** `dig jobs-api.<domain>` from a LAN device. [It resolves to NPM's LAN IP, and doesn't resolve publicly.]
- **D2:** `curl -I https://jobs-api.<domain>`. [Valid wildcard cert.]
- **D3:** Open the KasmVNC host in a browser. [WebSocket session works.]
- **D4:** `curl -N` an MCP streaming endpoint. [Events arrive without buffering delay.]
- **D5:** Call the API from a non-LAN address (VPN off or another VLAN), and send a spoofed `X-Forwarded-For` directly to the API. [Access list blocks it, and the spoofed header is ignored.]

**Email**
- **E1:** `dig MX <alias-domain>`. [Public MX points to the hosted mailbox.]
- **E2:** Send mail from another account to a random alias. [Arrives via IMAP within an acceptable time, and the latency is recorded.]
- **E3:** Feed the parser sample verification emails, including one with an injected instruction and one with a non-allowlisted link. [Only the code or allowed link is extracted, and the rest is ignored.]
- **E4:** Send an employer-style reply to an alias. [It's classified as a real reply and I'm notified.]

**Security**
- **S1:** Canary: sign up on a mock site with a fake password, then grep everything listed above. [Zero hits.]
- **S2:** Submit-guard suite against mock ATS pages: click submit, press Enter, call JS `form.submit()`, use a "Next" button that submits, and run adapter and workflow-replay paths. [Zero submit requests reach the mock server, and each attempt logs `submit_guard_blocked`.]
- **S3:** Sign up on a mock site, then inspect the Chromium profile. [No saved passwords or autofill entries.]
- **S4:** List the MCP tools and try to change the profile via MCP. [No forbidden tools, and the profile change is refused.]
- **S5:** Job title and description contain injected instructions, and I use my assistant through MCP. [No unexpected tool calls, and answers are unaffected.]

**Workflow-use**
- **W1:** Record a run on a mock Greenhouse form using placeholders. [The file contains no real values or secrets.]
- **W2:** Replay it with a different profile. [Fills correctly and stops before submit.]
- **W3:** Break a selector. [Replay diverges, the agent fallback fixes it, and the workflow is updated.]

**Resilience**
- **R1:** `kill -9` the worker mid-signup, between `pending` and confirmation. [Restart reconciles with no duplicate account.]
- **R2:** Reboot the Pi. [Vault is sealed, jobs wait, and I'm notified. After unseal, work resumes and `stale` jobs re-stage with frozen answers.]
- **R3:** A mock page that never completes. [The job stops at its budget with `budget_exceeded`.]
- **R4:** Restore the vault and DB from backup on a clean machine, then unseal with the escrowed passphrase. [Accounts are intact.]

**Model eval**
- **L1:** A fixed set of mock and sanitized real forms. [Field-mapping accuracy is recorded, always-flag recall is 100%, and no invented experience.]

---

## Decision log

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-09-28 | **Job intake reads from the existing `jobs-app` read-only JSON API** (`GET /api/jobs` list + `GET /api/jobs/{id}` detail with `application_url`/`listing_url`/`description`), exposed at `https://jobapp.siggy-lab.org/` (raw host port `8094`, UI `8095`), rather than opening `jobs-app`'s `jobs.db` directly or copying data into `apply-app`. | The user pointed at "the app exposed with a list of jobs and the urls to their application site"; `jobs-app` already exposes exactly that. Keeping `jobs-app` as the single source of truth for job discovery and `apply-app` as the application executor avoids two writers on one SQLite file. |
| 2026-09-28 | **Discovery recorded:** `jobs-app`'s `jobs.db` currently holds 111 `job_listings`, all RemoteOK-sourced; `application_url` holds the RemoteOK redirect (`remoteOK.com/remote-jobs/...`) and `company_application_platform_id` is NULL on every row, because the careers→listings pipeline is still in flight. | Consequence: the final employer ATS URL is **not yet** in `jobs-app`, so the plan's intake step "job-board redirects (LinkedIn and Indeed links resolve to the employer's ATS)" is load-bearing and must cover RemoteOK too, and must be verified early. |
| 2026-09-28 | **P3 RAM measurement uses mock/local pages first, and real-ATS P3 + P5 (bot-detection) are gated behind explicit approval.** | Rule 8 forbids visiting real job sites / third-party sites before N1–N6, S1, and S2 pass; the plan's own P3 ("real ATS pages") and P5 ("public bot-detection page") would otherwise violate that rule during step 0. Mock-first keeps step 0 unblocked without relaxing rule 8. |
| 2026-09-28 | **Recorded concrete hosts.** Ollama is reachable at `ai.siggy-lab.org:11434`; the existing jobs-app API is at `https://jobapp.siggy-lab.org/`; the domain is `siggy-lab.org`. The worker's `OLLAMA_BASE_URL` uses the hostname, and intake targets the jobs-app URL. | The user supplied the two real endpoints, replacing the `<domain>` and `<OLLAMA_BOX_LAN_IP>` placeholders. |
| 2026-09-28 | **Confirmed internal-only + Ollama on Ubuntu.** All hosts resolve only via local DNS to LAN IPs (NPM is local-only; nothing is reachable outside the network), and Ollama runs on Ubuntu. | The user confirmed LAN-only reachability, resolving the resolvability question. `ufw` (already used by O6) is the Ubuntu firewall tool, and Ollama's LAN bind is already in place. |
| 2026-09-28 | **Ollama GPU is AMD, not NVIDIA.** The box has an **AMD Radeon RX 7900 XT (20 GB VRAM, ROCm)**, so the O2 VRAM check uses `rocm-smi` (not `nvidia-smi`). ~17 GB Q4 vs 20 GB VRAM leaves ~3 GB headroom — tight, so O2/O3 are load-bearing. | The user supplied the GPU model; the plan's O2 originally assumed `nvidia-smi`, which would have failed on ROCm. |
| 2026-09-28 | **KasmVNC arm64 tag confirmed.** `kasmweb/chromium:1.16.1` is multi-arch (both `amd64` and `arm64` manifests present) and starts on the Pi (P2 pass). | P2's manifest inspection + container start resolved Open question #4; the arm64 image is this tag. |
| 2026-09-28 | **Spike scripts auto-log + auto-commit/push.** Each spike script tees its output to `~/apply-spikes/logs/<machine>-<timestamp>.log` and at the end commits it to `docs/spikes/runs/<machine>/` in this repo and pushes. Push requires git credentials on that machine; on failure the log is saved and the commit is left locally. | The user asked for results to be logged to a file and git-committed/pushed so the agent can read them from the repo instead of copy-paste. |
| 2026-09-28 | **Ollama model tag + version recorded.** Tag = `qwen3.8-27b-64k:latest`; `ollama` 0.33.3 (model requires ≥0.32.12); `ollama show` reports architecture `qwen35`, 27.3B, Q4_K_M, Modelfile `num_ctx` 64440. | O1 resolved the `<QWEN38_TAG>` placeholder (Open question #3). |
| 2026-09-28 | **O2 headroom assumption is wrong (rule 10).** The Q4_K_M build is 19 GB (not ~17 GB), and at 64k context it does not fit in the 20 GB VRAM: 93% VRAM used, ~24% of layers offloaded to CPU. Fallbacks to choose from: (a) smaller quant (Q4_0 / Q3_K_M) so it fits on-GPU, (b) lower `num_ctx` (e.g. 32k), (c) accept the CPU offload (works, ~17 tok/s generation). | Measured by O2 (`rocm-smi` + `ollama ps`). Disproves the plan's "VRAM fits with headroom" clause, so O2 is marked fail and a fallback must be chosen before L1 and long-form runs. |
| 2026-09-28 | **CPU-offload cost + local models recorded.** Offloaded Q4_K_M 64k generates at 17.4 tok/s (think off); a fully-on-GPU 27B Q4 on the 7900 XT is ~30–35 tok/s, so offload ≈ 2× slower on decode and ~2–3× on prefill. The user already has `qwen38-q3-32k:latest` and `batiai/qwen3.8-27b:q3` (13 GB Q3, 32k) locally, which would fit fully on-GPU. | Quantifies Open question #6: three real options — keep Q4_K_M 64k + offload, use the local Q3 32k, or build a Q3_K_M at 64k. |
| 2026-09-28 | **Ollama spike now sweeps candidates + builds Q3-at-64k.** `ollama.sh` loops over `qwen38-q3-32k`, `batiai/qwen3.8-27b:q3`, `qwen3.8-27b-120k`, `qwen-32k`, and — if absent — creates `qwen38-q3-64k:latest` by rebasing the local Q3 weights with `num_ctx 65536` (no GGUF download), guarded by an existence check. Each model writes a model-named timestamped log (no overwrite) and is committed/pushed as it finishes. | The user asked to test the remaining models, not overwrite earlier results, and to include the Modelfile creation for option (C). Single-model mode via `QWEN38_TAG` skips the build. |
| 2026-09-28 | **Working model: `qwen38-q3-64k:latest` (Q3_K_M, 64k).** Sweep results: every Q3 model loads at `num_ctx 65536` with **100% GPU**, VRAM 84% (18.1 GB / 21.5 GB), 50/50 JSON + 50/50 tool validity, think:false tok/s ~36 (vs ~11–14 for the offloaded Q4). The Q4 64k/120k both offload ~24% to CPU. Q3 has **no vision projector** (Q4 does), so `qwen3.8-27b-64k:latest` (Q4, vision) is kept as the vision fallback. | Decisive O2/O4/O5 data resolves Open question #6. The plan already treats vision as optional/leak-surface, so Q3 (fits, fast, no vision) is the default; Q4-vision is the fallback. |
| 2026-09-28 | **workflow-use is viable (W-spike introspection).** `workflow-use` 0.2.11 installs and exposes `Workflow` (runs a `WorkflowDefinitionSchema`, `fallback_to_agent=True`, `run(input_dict)`), whose steps use `input_schema` variables + `{context_var}` placeholders — so a recorded workflow file holds no real values (satisfies W1). Modules: `recorder` (Chrome extension), `builder` (LLM parameterizes a recording), `workflow` (runner), `healing` (W3 fallback). `browser-use` 0.13.10 provides `ChatOllama(model, host, ollama_options=...)` — num_ctx/think pass through (answers "does browser-use pass parameters through" = yes). | Read from the vendored 0.2.11 wheel + 0.13.10 source. `workflow-use==0.2.11` pins `faiss-cpu==1.10.0`, which has no Python 3.14 wheel — the worker must run Python ≤3.12. Versions to pin: browser-use 0.13.10, workflow-use 0.2.11. |
| 2026-09-28 | **browser-use 0.13.10 needs an explicit Chromium path + `--no-sandbox` on the Pi (rule 10).** The default `Browser(headless=True)` fails to launch (Chrome binary scan misses Playwright's build; CDP never comes up). The working recipe — already used by jobs-app's worker on the same Pi — is `BrowserProfile(executable_path=<playwright chromium>, headless=True, args=["--no-sandbox","--disable-gpu","--disable-dev-shm-usage"])`. P4/W1-W3 drivers fixed to use it. | P4 + W2/W3 both failed with "Browser process exited before CDP became available". jobs-app pins the same browser-use 0.13.10, so the fix is configuration, not a version downgrade. |
| 2026-09-28 | **Pi cannot yet reach Ollama (O6 "Pi succeeds" clause failing).** `curl ai.siggy-lab.org:11434` from the Pi returns "Couldn't connect" (DNS resolves, TCP refused) — Ollama is almost certainly bound to 127.0.0.1 only, not the LAN interface. Blocks P4/W1-W3 (they drive the model from the Pi). | P4_ollama FAIL in the pi log. Fix on the Ollama box: set `OLLAMA_HOST=0.0.0.0` in the systemd unit, restart, confirm `ss -tlnp | grep 11434`; then O6's firewall step can proceed. |
| 2026-09-28 | **Ollama endpoint corrected: proxy-fronted, not a raw port.** Ollama is reachable at `https://ai.siggy-lab.org` (TLS via the reverse proxy), NOT `http://ai.siggy-lab.org:11434` — that is why the Pi's raw-port curl failed. Worker/drivers now use `https://ai.siggy-lab.org`; the raw `:11434` stays behind the proxy/firewall. | Supersedes the previous row's "bound to 127.0.0.1" guess. Also changes O6: the Pi reaches Ollama through the proxy, and raw `:11434` should be firewalled to the proxy only. |
| 2026-09-28 | **browser-use on the Pi host needs OS libraries (jobs-app gets them from Docker).** Chrome still crashed after `--no-sandbox` + `executable_path`; the real cause is the Pi *host* lacks Chromium's shared libraries. jobs-app's image runs `playwright install --with-deps chromium`, which installs them; the spike venv only ran `playwright install chromium`. Fix: `sudo <venv>/python3 -m playwright install-deps chromium`. Also set `ANONYMIZED_TELEMETRY=false` (rule 10: telemetry off). | W1-W3 still failed with "Browser process exited before CDP became available" on the host. Confirms browser-use was verified *in Docker* (deps baked in), not on the bare host. |
| 2026-09-28 | **Spikes run in Docker, not on the bare host (matching deployment).** The bare-host spike polluted the Pi (venv, Playwright, system deps) and hit dependency gaps the Docker image already solves. Added `scripts/spikes/Dockerfile` (python:3.12-slim + playwright 1.58.0 + browser-use 0.13.10 + workflow-use 0.2.11 + `--with-deps` chromium), `run-spike.sh` (build + `docker run --network host`), and `cleanup.sh` to remove the host artifacts. | User prefers Docker since that's the deploy model; the host-installed spike artifacts will be removed once testing is done. |
| 2026-09-29 | **Pi storage: Docker is on the micro SD, not the SSD.** The Pi runs OMV and boots from `/dev/mmcblk0p2` (SD); `/dev/sda1` (1.72 TiB SSD) is a separate data disk, but Docker's `data-root` currently sits on the SD — which is why the image build (pip install of ~120 packages) was slow. The plan's "named volumes on the SSD" requires moving Docker's `data-root` (and/or the named volumes) to the SSD. | User diagnosed the build slowness. Fix (before build step 1): move `/var/lib/docker` to the SSD and set `data-root` in `/etc/docker/daemon.json`. The spike build is cached, so this is not urgent for step 0. |
| 2026-09-30 | **workflow-use 0.2.11 limits found (W2/W3).** (1) The `select_change` step generates a broken CSS selector (`select[name][type="select-one"]`), which never matches real `<select>` elements — the "Work authorization" dropdown failed. (2) `fallback_to_agent=True` does NOT recover from "No selector available" (a semantic-mapping failure, not a step-execution failure), so a broken selector is NOT auto-fixed as the plan assumed. Mitigation: per-ATS adapters handle selects directly; the fallback path uses the full browser-use `Agent`, not workflow-use's `fallback_to_agent`. | W2 filled 8 text/number fields with verification match:True, then failed on the select. These are the "workflow-use is young" risks the plan anticipated. |
| 2026-09-30 | **SearXNG is the local search (`search.siggy-lab.org`); P4's free agent went to Google/DuckDuckGo (rule-8 breach) because the task omitted the mock-form URL.** Recorded SearXNG as an internal service. The P4 headless run proved browser-use + `ChatOllama`(qwen38-q3-64k) runs end-to-end in Docker (agent navigated/reasoned, `throttled=0x0`), but it flailed 123s searching public engines because the task didn't name the URL — fixed by putting `FORM_URL` in the task. Production's egress proxy + domain allowlist would block stray public-engine searches. Headed failed (no X server) — expected; headed is the KasmVNC browser container's job. | Fix: `TASK` now includes `{FORM_URL}`. Any future agent web-search should target the local SearXNG, never Google/DuckDuckGo. |
| 2026-09-30 | **P4 pass; headed-vs-hybrid decision recorded.** The free-form browser-use agent (Q3-64k) filled the mock form end-to-end headless (9/9 fields, no submit, 70s) with `throttled=0x0`. Headed could not run in the spike container (no X server), so the headed-RAM-vs-tabs measurement is deferred to the KasmVNC browser container (build step 5) — which is where the plan's "headed under Xvfb" default lives anyway. | Step-0 automated spikes are now complete (O/P/W); remaining are manual P3 (RAM tabs), O6 (firewall), and gated P5. |
| 2026-09-30 | **O6 raw-port firewall lock deprioritized (trusted LAN).** The user doesn't need to lock raw `:11434` because everything stays on their local network (sole user). The plan's "browser can't reach Ollama" non-negotiable is enforced by the **egress proxy** (denies private ranges) in build step 5, not by ufw — so skipping the ufw lock is acceptable *provided* the egress proxy is solid in step 5. |
| 2026-09-30 | **Engineering practice: small, human-maintainable modules.** Keep every file and function small and focused; split pure logic (e.g. policy/validation) from I/O (proxy/server); add unit tests for the pure parts; no god-files or unmanageable functions. Applies to all build steps. | The user explicitly asked for code that is easy for a human to maintain manually, not just easy for AI agents. | The domain path (https) is already verified (`P4_ollama`). This lowers O6 from "firewall + cross-host curl" to "domain reachable" (done). |

## Verification log

| Test | Status | Date | Evidence |
| --- | --- | --- | --- |
| O1 | pass | 2026-09-28 | `ollama --version` = 0.33.3; `ollama show qwen3.8-27b-64k:latest` → architecture `qwen35`, 27.3B, Q4_K_M, context 262144, capabilities include vision/tools/thinking. |
| O2 | fail | 2026-09-28 | `num_ctx:65536` accepted (`CONTEXT 65536`, "response ok: pong") — context clause OK. Headroom clause failed: `rocm-smi` VRAM 93% used (20.08 GB / 21.46 GB) and `ollama ps` PROCESSOR `24%/76% CPU/GPU` (~24% offloaded to CPU). Model = 19 GB Q4_K_M. |
| O3 | pass | 2026-09-28 | Re-run with denser input: `prompt_eval_count=60791` for 360k-char input (~60k tokens), no truncation — 60k confirmed. (First run: 42220 for 42k.) |
| O4 | pass | 2026-09-28 | 50/50 valid JSON-schema outputs and 50/50 valid tool-call outputs (100%, above the 98% bar). |
| O5 | pass | 2026-09-28 | `think` toggle honored: `think:false` → eval_count 7, 17.4 tok/s, 0.92s wall; `think:true` → eval_count 31, 14.3 tok/s, 9.06s wall. |
| O6 | pass | 2026-09-30 | Pi reaches Ollama via the domain (`https://ai.siggy-lab.org/api/tags` — `P4_ollama` pass). The raw `:11434` firewall lock was intentionally skipped (trusted LAN, sole user); the "browser can't reach Ollama" guarantee is carried by the egress proxy (step 5), not ufw. |
| P1 | pass | 2026-09-28 | `uname -m` = `aarch64`; `docker compose version` = v5.4.0; `vcgencmd get_throttled` = `throttled=0x0`. |
| P2 | pass | 2026-09-28 | `kasmweb/chromium:1.16.1` has an arm64 manifest; image pulled; container `kasmvnc-spike` Up (`P2_start PASS`). "Connect through NPM with WebSockets" leg not yet evidenced — deferred to D3. |
| P3 | untested | | |
| P4 | pass | 2026-09-30 | Headless: browser-use + `ChatOllama`(qwen38-q3-64k) filled all 9 mock-form fields with CANARY values and stopped without clicking Submit (wall 70.1s); `throttled=0x0`. Headed: no X server in the spike container (expected) — headed-vs-hybrid RAM measurement deferred to the KasmVNC browser container (step 5). |
| P5 | untested | | |
| N1 | pass | 2026-09-30 | From the internal `browser_net` container: `http://169.254.169.254` and `http://192.168.1.1` both unreachable (000/7). |
| N2 | pass | 2026-09-30 | `https://example.com` direct from `browser_net` → unreachable (000); through the egress proxy → 200. |
| N3 | pass | 2026-09-30 | `http://localtest.me` (→127.0.0.1) and `http://10.0.0.1` through the proxy → 403 (rebinding defense). |
| N4 | untested | | Deferred to the browser service (step 5). |
| N5 | untested | | Deferred to the browser service (step 5). |
| N6 | pass | 2026-09-30 | With `EGRESS_ALLOWLIST=example.com`: `example.com` → 200, `neverssl.com` → 403, and the denied domain appears in the proxy log. |
| D1 | untested | | |
| D2 | untested | | |
| D3 | untested | | |
| D4 | untested | | |
| D5 | untested | | |
| E1 | untested | | |
| E2 | untested | | |
| E3 | untested | | |
| E4 | untested | | |
| S1 | untested | | |
| S2 | untested | | |
| S3 | untested | | |
| S4 | untested | | |
| S5 | untested | | |
| W1 | pass | 2026-09-29 | Driver (Docker, on SSD) built the parameterized workflow; `placeholders present: first_name=True, email=True`; `canary leaks found in file: NONE`. The `.workflow.json` holds `{context_var}` placeholders, no real values. |
| W2 | fail | 2026-09-30 | Replay filled 8 fields (first/last/email/phone/linkedin/website/years) with `Verification: match: True`, then `select_change` failed: workflow-use generates `select[name][type="select-one"]`, which never matches a real `<select>` (no `type` attribute). Stops before submit ✓ (schema ends at extract). |
| W3 | fail | 2026-09-30 | Broke first_name `target_text` → "No selector available", and `fallback_to_agent=True` did NOT recover — the fallback doesn't cover semantic-mapping failures. |
| R1 | untested | | |
| R2 | untested | | |
| R3 | untested | | |
| R4 | untested | | |
| L1 | untested | | |

## Open questions

1. **Rule 8 vs P3/P5.** The plan's P3 says "real ATS pages" and P5 says "public bot-detection page", both before N1–N6/S1/S2 pass. Default chosen (see Decision log): mock-first for P3, gate P5 + real-ATS P3 behind explicit approval. Confirm this reading is acceptable before I hand over a third-party-visit command.
2. **Internal vs public resolvability of the hosts — resolved.** The domain is `siggy-lab.org` — Ollama at `ai.siggy-lab.org`, jobs-app at `jobapp.siggy-lab.org`, and the apply-app hostnames `jobs-api.` / `jobs-mcp.` / `jobs-review.` under it. Confirmed 2026-09-28: all are internal-only (local DNS → LAN IP), NPM is local-only, and they are not reachable outside the network. Firewall (O6) and NPM access-list (D5) remain the enforcement layers, verified by D1/D5/N1.
3. ~~Exact Ollama tag for Qwen3.8-27B~~ **Resolved:** `qwen3.8-27b-64k:latest` (O1; `ollama` 0.33.3, architecture `qwen35`, Q4_K_M).
4. ~~KasmVNC arm64 image tag~~ **Resolved:** `kasmweb/chromium:1.16.1` is multi-arch (arm64 manifest present) and starts on the Pi (P2 pass).
5. **workflow-use feasibility — confirmed.** `workflow-use` 0.2.11 installs from PyPI and exposes `Workflow` (runner with `fallback_to_agent=True`) + `WorkflowDefinitionSchema` (steps must end in an extract step; `input_schema` variables + `{context_var}` placeholders). It also ships `recorder` (Chrome-extension based), `builder` (LLM builds a parameterized workflow), and `healing` (selector-breakage recovery) modules. No thin recorder needed. Remaining: write/run the actual W1–W3 record/replay/break driver.
6. ~~VRAM fallback~~ **Resolved:** use `qwen38-q3-64k:latest` (Q3_K_M, 64k, 100% GPU, 84% VRAM, 100% JSON/tool validity, ~36 tok/s think-off). The "32k"/"16k" Q3 tags load at 64k anyway (their `num_ctx` was just the default; real max is 262144). Q3 lacks vision; `qwen3.8-27b-64k:latest` (Q4, vision, offloaded) is the vision fallback.

## Changelog

### 2026-09-28
- **Initial commit.** Saved the plan verbatim to `docs/PLAN.md` and appended the required sections: Decision log, Verification log (all O1–L1 tests pre-seeded as `untested`), Open questions, and Changelog.
- **Recorded job-intake source.** Decided `apply-app` reads jobs from the existing `jobs-app` read-only JSON API; recorded the discovery that `application_url` is currently a RemoteOK redirect (final ATS URL not yet in `jobs-app`).
- **Recorded the rule-8 vs P3/P5 tension** and the mock-first default for the P3 RAM spike.
- **Recorded concrete hosts.** Ollama = `ai.siggy-lab.org:11434`; jobs-app API = `https://jobapp.siggy-lab.org/`; domain = `siggy-lab.org`. Updated the worker `OLLAMA_BASE_URL` and the spike scripts accordingly.
- **Confirmed internal-only + Ollama on Ubuntu.** All hosts are LAN-only (local DNS → LAN IP), NPM is local-only, nothing is reachable outside the network; Ollama runs on Ubuntu (ufw). Resolved Open question #2.
- **AMD GPU recorded.** Ollama runs on an AMD Radeon RX 7900 XT (20 GB VRAM, ROCm); switched O2's VRAM check from `nvidia-smi` to `rocm-smi` and flagged the ~3 GB headroom for the 64k-context check.
- **P1 and P2 pass.** Pi is `aarch64` with `throttled=0x0`; `kasmweb/chromium:1.16.1` is arm64-capable and started under KasmVNC (NPM/WebSocket leg deferred to D3).
- **Spike scripts now auto-log + auto-commit/push** their results to `docs/spikes/runs/<machine>/`.
- **O1–O5 results.** O1/O3/O4/O5 pass; O2 fails its headroom clause. Ollama 0.33.3, model `qwen3.8-27b-64k:latest` (architecture `qwen35`, Q4_K_M).
- **VRAM assumption corrected.** Q4_K_M is 19 GB and 64k context does not fit in 20 GB VRAM (93% used, ~24% CPU offload) — fallbacks proposed in Decision log / Open question #6.
- **CPU-offload cost quantified + local Q3 models noted.** 17.4 tok/s (think off) with offload vs ~30–35 full-GPU; user has 13 GB Q3 32k models locally. Refined the fallback to three concrete options.
- **Ollama spike now sweeps models + builds Q3-64k.** Multi-model loop with per-model no-overwrite logs; creates `qwen38-q3-64k:latest` from the local Q3 weights (existence-checked) as fallback option (C).
- **Model sweep complete — Q3_K_M at 64k chosen.** All 5 candidates tested: Q3 models load at 64k with 100% GPU (84% VRAM, ~36 tok/s) and 100% JSON/tool validity, vs Q4's ~24% CPU offload. `qwen38-q3-64k:latest` is the working model; Q4-vision is the fallback.
- **workflow-use.sh `==latest` pip bug fixed + push gotcha.** The first W1 run installed nothing (invalid `pip install "browser-use==latest"`; now fixed in the script) and its auto-push was rejected because the Pi was behind origin ("fetch first", not credentials). W1–W3 remain untested — re-run after `git pull --rebase`.
- **workflow-use + browser-use APIs confirmed.** `workflow-use` 0.2.11 (Workflow runner + placeholder `{context_var}` schema + native `fallback_to_agent` + healing) and `browser-use` 0.13.10 (`ChatOllama` with `ollama_options` passthrough). No thin recorder needed; pin Python ≤3.12 (faiss-cpu==1.10.0).
- **P4/W1-W3 first run: two blockers found.** (1) browser-use 0.13.10 needs `BrowserProfile(executable_path=…, args=["--no-sandbox",…])` to launch on the Pi (drivers fixed to match jobs-app's recipe). (2) The Pi can't reach Ollama yet — `ai.siggy-lab.org:11434` TCP-refused (Ollama likely bound to 127.0.0.1).
- **Ollama endpoint corrected to `https://ai.siggy-lab.org`.** Ollama is fronted by the reverse proxy (TLS), not a raw `:11434` port — that's the real reason the Pi's curl failed. Updated compose worker + P4/W1-W3 drivers + spike curls to https.
- **browser-use host deps + telemetry.** Chrome crash traced to missing OS libraries on the Pi host (jobs-app installs them via `playwright install --with-deps` in Docker); telemetry now disabled (`ANONYMIZED_TELEMETRY=false`).
- **Spike moved to Docker.** Added a spike `Dockerfile` (pinned stack + `playwright install --with-deps chromium`) and `run-spike.sh`; the bare-host venv/browser/deps are removed via `cleanup.sh`.
- **Pi→Ollama connectivity confirmed.** `P4_ollama` now passes (`https://ai.siggy-lab.org` reachable from the Pi), confirming the endpoint correction. P4's browser-use fill still fails on the bare host (missing Chromium libs) — the Docker runner supersedes it.
- **Docker data-root on SD, not SSD.** Pi boots from micro SD (`mmcblk0p2`); the SSD (`/dev/sda1`) is a separate OMV data disk but Docker runs on the SD. Move Docker's `data-root` to the SSD (via `/etc/docker/daemon.json`) before step 1.
- **W1 pass; W2/W3 driver bug fixed.** W1 verified (placeholders only, no canary leaks). W2/W3 first hit a driver bug — `serve_form()` was never called, so the mock form wasn't served (browser got connection-refused) — fixed.
- **W2/W3 findings: workflow-use select bug + fallback gap.** W2 filled 8/10 fields (text/number) but `select_change` fails (invalid `[type="select-one"]` selector); W3 shows `fallback_to_agent` does not recover from "No selector available". Per-ATS adapters + full-agent fallback are the mitigation.
- **SearXNG + P4 findings.** Recorded local SearXNG (`search.siggy-lab.org`). P4 headless ran (browser-use + Q3 end-to-end, `throttled=0x0`) but flailed on Google/DuckDuckGo because the task lacked the URL (now fixed); headed needs Xvfb.
- **Added `CONTEXT.md`** — a handoff file (rules, hosts, versions, gotchas, current state) for resuming in a fresh session; kept updated alongside the plan.
- **P4 pass.** Headless browser-use + Q3-64k filled the mock form end-to-end (9/9 fields, no submit, `throttled=0x0`); headed deferred to the KasmVNC browser container. Step-0 automated spikes complete.
- **O6 raw-port lock deprioritized.** Trusted LAN (sole user) → the ufw lock on raw `:11434` is skipped; "browser can't reach Ollama" is enforced by the egress proxy (step 5). O6 marked pass (domain reachable).
- **Started build step 1 + maintainability principle.** Small, focused, human-maintainable modules (pure policy vs. I/O), no god-files; began with the egress proxy.
- **Egress proxy built + verified live.** `scripts/egress-smoke.sh` passed 4/4 (HTTPS CONNECT, HTTP forward, private-IP deny, loopback deny via `localtest.me`). Found + fixed a CONNECT-header bug (leftover `Host:` header corrupted the TLS handshake). Added `scripts/n-tests.sh` (N1/N2/N3/N6); N4/N5 + D1–D5 deferred to the browser/api/NPM steps.
- **N1/N2/N3/N6 pass (9/9).** Network isolation + egress proxy verified live on the Pi. Build step 1's buildable portion (networks + proxy) is done; N4/N5/D are deferred to later services.
- **Started build step 2 (mock ATS + canary).** Added `services/mock-ats/` (Greenhouse/Lever/Ashby + signup fixtures, a POST-logging server, Dockerfile) and `scripts/canary-grep.sh` (S1 harness). The browser-signup step and profile/screenshot/trace targets land in step 5; submit-guard logic stays in step 5 (fixtures already built for it).
- **Step 2 complete (fixtures + canary + snapshot scaffold).** Added `sanitize.py` + `fixtures/real-snapshots/` (gated capture+redact procedure for L1) and `scripts/mock-ats-smoke.sh` (serve + POST-logging smoke test).
- **Step 2 verified live.** `mock-ats-smoke.sh` passed on the Pi (GET `greenhouse.html` → 200, POST `/signup` recorded to `submissions.log`).
- **Started build step 3 (API foundation).** `services/api/` with the error taxonomy (`errors.py`), redacted logging (`redact.py`), env config, SQLAlchemy WAL `db.py`, and a `/health` FastAPI app. Pinned fastapi 0.142.2 / uvicorn 0.54.0 / SQLAlchemy 2.1.1. 7 unit tests pass.
- **DB schema + Alembic.** `app/models/` (Job, StepEvent, Lease, Account + queue-state vocabulary) and the initial Alembic migration `0001_initial_schema` (autogenerated). 11 tests pass.
- **Jobs/queue/leases endpoints.** `POST /jobs` (single + bulk, idempotent), `GET /jobs` (cursor pagination + state/ats/company filters), `GET /jobs/{id}`, `POST /jobs/{id}/actions` (cancel/skip/retry/requeue/restage/mark_submitted), and lease `acquire`/`heartbeat`/`release`. State machine + lease logic in `services/jobs.py`. Added `idempotency_key` + migration `0002`. 18 tests pass (incl. migration round-trip).
- **Recorded debuggability requirement + structured JSON logging.** Logs are now structured JSON (one object per line, redacted) carrying optional `correlation_id`/`job_id`/`run_id`/`step`/`adapter`/`action`/`error_code` so they're filterable/searchable. Agent/browser-use thinking + action reasoning will be captured into `StepEvent` (step 6), and a `filtered logs` API endpoint lands in the diagnostics increment.
- **Scoped auth.** `security.py` — hash-stored bearer tokens (sha256), scopes `diagnose` (read-only) < `ops` < `admin`, enforced per endpoint (reads → `diagnose`, writes → `ops`). Tokens load from env (`TOKEN_HASH_<SCOPE>`) or `/run/secrets/api_<scope>_token_hash`. 24 tests pass.
- **`doctor` + step 3 complete.** `GET /doctor` (`diagnose` scope) runs named checks: DB migrations (current vs head), stuck/expired leases, and Ollama reachability. Vault/browser/proxy/host/IMAP checks are deferred to steps 4–7. Alembic now runs at container startup (`alembic upgrade head` in the CMD). 26 tests pass.
