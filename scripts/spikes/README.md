# Step-0 spikes (P1–P5, O1–O6, W1–W3)

One self-contained copy-paste script per machine. Run them in this order and paste back the
evidence requested. Status for every test is tracked in `docs/PLAN.md` → Verification log.

**Known hosts:** Ollama = `ai.siggy-lab.org:11434` · jobs-app API = `https://jobapp.siggy-lab.org/` · domain = `siggy-lab.org`.

> **Rule 8 gate:** nothing here may visit a real job site or third-party site yet. P3 is mock-first,
> and **P5 (bot-detection page) is paused until you approve a specific URL** — tell the agent which
> URL (or "none yet") and it will pin the exact command.

## Ollama box — `ollama.sh` (O1–O6)

**Run on:** the machine hosting Ollama + the GPU. Needs `curl` + `python3`.

```bash
export QWEN38_TAG="<your qwen3.8 tag>"   # e.g. qwen3.8-27b:q4_K_M
bash ollama.sh
```

**Paste back:** (1) the `=== SUMMARY ===` block, (2) any section that printed `FAIL` or a traceback,
(3) for O2 the `ollama ps` + `nvidia-smi` lines, (4) for O6 the `sudo ufw status verbose` output.

| Test | Pass criterion |
| --- | --- |
| O1 | `ollama --version` prints; `ollama show <tag>` prints the model/Modelfile with no error (architecture supported). |
| O2 | `/api/generate` with `num_ctx:65536` succeeds; `ollama ps` shows the model; `rocm-smi` shows VRAM with headroom (AMD RX 7900 XT, 20 GB). |
| O3 | `prompt_eval_count` ≈ 60k (no silent truncation); no "context length exceeded" error. |
| O4 | ≥49/50 valid JSON-schema outputs **and** ≥49/50 valid tool-call outputs (record the failures). |
| O5 | `think:false` vs `think:true` shows a real difference in `eval_count`/latency; tokens/sec recorded (note which knob is honored). |
| O6 | `keep_alive` keeps the model loaded after idle; firewall allows only the Pi (Pi curl succeeds, other-host curl fails). |

## Raspberry Pi — `pi.sh` (P1–P5)

**Run on:** the Pi 5. Needs `docker`, `docker compose`, `vcgencmd`, `python3`.

```bash
bash pi.sh
```

**Paste back:** (1) the `=== SUMMARY ===` block, (2) any `FAIL`/traceback, (3) for P3 the
`docker stats` + `free -h` numbers at 1/3/5 tabs, (4) for P4 the headless-vs-headed timing/RAM/throttled lines.

| Test | Pass criterion |
| --- | --- |
| P1 | `uname -m` = `aarch64`; `docker compose version` prints; `vcgencmd get_throttled` = `0x0` at idle. |
| P2 | `kasmvnc-spike` container is `Up`; you can open it (and later through NPM with WebSockets). |
| P3 | 5 tabs of the mock form keep total used RAM under ~6GB with no swap thrash. |
| P4 | No throttling during the fill; the headed-vs-headless numbers are recorded so we pick headed vs hybrid. |
| P5 | **Blocked pending your approval of the bot-detection URL.** Result recorded as a baseline when run. |

## Pi (or dev box) — `workflow-use.sh` (W1–W3)

**Run on:** the Pi (same stack that already runs browser-use) or any dev box with `python3` + Chromium.

```bash
bash workflow-use.sh
```

**Paste back:** (1) the `=== SUMMARY ===` block, (2) `~/apply-spikes/spikes-lock.txt`, (3) the full
`=== W-introspection ===` output — **even the `IMPORT FAIL` lines are evidence**.

| Test | Pass criterion |
| --- | --- |
| W1 | Recording file contains only `{{placeholders}}`, zero canary/real values (`check-leaks.sh` prints W1 PASS). |
| W2 | Replay with `profile-replay.json` fills correctly and stops before submit. |
| W3 | A broken selector diverges, the agent fallback fixes it, and the workflow is updated. |

> The exact `record`/`replay` calls depend on workflow-use's real API, which the introspection
> reveals. Paste the lockfile + introspection back and the agent will write the finalized W1–W3 driver.
> If workflow-use cannot install or record with placeholders, the plan's fallback (a thin recorder of
> our own) is triggered — recorded in the Decision log.
