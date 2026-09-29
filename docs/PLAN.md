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
- KV cache is cheap thanks to linear-attention layers. The Q4_K_M build measures **19 GB** (not the ~17 GB assumed), and at 64k context it does **not** fit in the card's **20 GB VRAM** — O2 measured 93% VRAM used with ~24% of layers offloaded to CPU (see Decision log for the fallback options).
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

## Verification log

| Test | Status | Date | Evidence |
| --- | --- | --- | --- |
| O1 | pass | 2026-09-28 | `ollama --version` = 0.33.3; `ollama show qwen3.8-27b-64k:latest` → architecture `qwen35`, 27.3B, Q4_K_M, context 262144, capabilities include vision/tools/thinking. |
| O2 | fail | 2026-09-28 | `num_ctx:65536` accepted (`CONTEXT 65536`, "response ok: pong") — context clause OK. Headroom clause failed: `rocm-smi` VRAM 93% used (20.08 GB / 21.46 GB) and `ollama ps` PROCESSOR `24%/76% CPU/GPU` (~24% offloaded to CPU). Model = 19 GB Q4_K_M. |
| O3 | pass | 2026-09-28 | Re-run with denser input: `prompt_eval_count=60791` for 360k-char input (~60k tokens), no truncation — 60k confirmed. (First run: 42220 for 42k.) |
| O4 | pass | 2026-09-28 | 50/50 valid JSON-schema outputs and 50/50 valid tool-call outputs (100%, above the 98% bar). |
| O5 | pass | 2026-09-28 | `think` toggle honored: `think:false` → eval_count 7, 17.4 tok/s, 0.92s wall; `think:true` → eval_count 31, 14.3 tok/s, 9.06s wall. |
| O6 | untested | 2026-09-28 | `keep_alive:30m` was set; the "still loaded after idle" check and the ufw firewall + cross-host curl (Pi ok / other host fail) are not yet evidenced. |
| P1 | pass | 2026-09-28 | `uname -m` = `aarch64`; `docker compose version` = v5.4.0; `vcgencmd get_throttled` = `throttled=0x0`. |
| P2 | pass | 2026-09-28 | `kasmweb/chromium:1.16.1` has an arm64 manifest; image pulled; container `kasmvnc-spike` Up (`P2_start PASS`). "Connect through NPM with WebSockets" leg not yet evidenced — deferred to D3. |
| P3 | untested | | |
| P4 | untested | | |
| P5 | untested | | |
| N1 | untested | | |
| N2 | untested | | |
| N3 | untested | | |
| N4 | untested | | |
| N5 | untested | | |
| N6 | untested | | |
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
| W1 | untested | | |
| W2 | untested | | |
| W3 | untested | | |
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
5. **workflow-use feasibility.** W1–W3 verify record/replay with placeholders. If it fails, the plan already names the fallback (build a thin recorder). No decision until W1–W3 evidence is in.
6. **VRAM fallback (from O2 fail).** Choose: (a) keep Q4_K_M 64k + ~24% CPU offload (~2x slower decode, ~2–3x prefill), (b) use the already-local Q3 32k (`qwen38-q3-32k:latest`, 13 GB, full GPU but 32k context), or (c) build a Q3_K_M at 64k (~13 GB, full GPU, 64k). L1 eval decides Q3 vs Q4 quality.

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
