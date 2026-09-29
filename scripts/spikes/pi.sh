#!/usr/bin/env bash
# Spike P1-P5 — run ON THE RASPBERRY PI 5 (8GB).
# Needs: docker, docker compose, vcgencmd (raspberrypi-utils), python3 (for P3/P4 mock page).
#
# Paste back, for the agent:
#   1) the final "=== SUMMARY ===" block, AND
#   2) the full output of any section that printed "FAIL" or a traceback.
#
# NOTE: P5 (bot-detection page) is a THIRD-PARTY site. Per the plan's rule 8, do NOT run P5
# until the agent has asked and you have approved the specific URL. P3 is mock-first for the
# same reason; the "real ATS pages" variant is also gated behind approval.
set -uo pipefail

MACHINE=pi

# ---- logging + auto-commit: tee output to a timestamped log, then commit+push it to the repo ----
LOG_DIR="${APPLY_LOG_DIR:-$HOME/apply-spikes/logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${MACHINE}-$(date +%Y%m%d-%H%M%S).log"

commit_results() {
  local repo="${APPLY_REPO:-}"
  if [ -z "$repo" ]; then
    repo="$(git -C "$(cd "$(dirname "$0")" 2>/dev/null && pwd)" rev-parse --show-toplevel 2>/dev/null || true)"
  fi
  if [ -z "$repo" ]; then
    repo="$HOME/apply-app"
    if [ ! -d "$repo/.git" ]; then
      git clone https://github.com/puelloc/apply-app.git "$repo" >/dev/null 2>&1 || {
        echo "COMMIT SKIPPED: no repo at $repo and clone failed. Log saved at $LOG"; return 0; }
    fi
  fi
  git -C "$repo" config user.email >/dev/null 2>&1 || git -C "$repo" config user.email "spike-bot@localhost"
  git -C "$repo" config user.name  >/dev/null 2>&1 || git -C "$repo" config user.name  "spike-bot"
  local dest="$repo/docs/spikes/runs/$MACHINE"
  mkdir -p "$dest"
  cp "$LOG" "$dest/$(basename "$LOG")"
  export GIT_TERMINAL_PROMPT=0
  if git -C "$repo" add "docs/spikes/runs/$MACHINE/$(basename "$LOG")" 2>&1 \
     && git -C "$repo" commit -q -m "spike($MACHINE): results $(basename "$LOG")" 2>&1 \
     && git -C "$repo" push origin main 2>&1; then
    echo "RESULTS COMMITTED + PUSHED: $repo/docs/spikes/runs/$MACHINE/$(basename "$LOG")"
  else
    echo "COMMIT/PUSH FAILED — log saved at $LOG (and staged in $repo). Fix git credentials on this machine to auto-push."
  fi
}

PASS=0; FAIL=0; FAILED_IDS=()
pass() { PASS=$((PASS+1)); printf 'RESULT: %-3s PASS\n' "$1"; }
fail() { FAIL=$((FAIL+1)); FAILED_IDS+=("$1"); printf 'RESULT: %-3s FAIL\n' "$1"; }
say()  { printf '\n########## %s ##########\n' "$1"; }

{
# ---------------- P1: hardware sanity ----------------
say "P1 hardware"
echo "uname -m:"; uname -m
echo "docker compose version:"; docker compose version
echo "vcgencmd get_throttled (want 0x0 at idle):"; vcgencmd get_throttled
[ "$(uname -m)" = "aarch64" ] && pass P1_arch || fail P1_arch
THROTTLED="$(vcgencmd get_throttled | awk '{print $1}')"
[ "$THROTTLED" = "throttled=0x0" ] && pass P1_throttled || { echo "note: throttled=$THROTTLED (check PSU/cooling)"; fail P1_throttled; }

# ---------------- P2: headed Chromium under Xvfb + KasmVNC (arm64) ----------------
say "P2 KasmVNC arm64 image"
echo "Discovering arm64 manifests for kasmweb/chromium:"
docker manifest inspect kasmweb/chromium:1.16.1 2>&1 | grep -E '"architecture"|"os"' | sort -u || \
  echo "(manifest inspect failed — paste this; the tag may be wrong, I'll pin the correct arm64 tag)"
echo "Running headed Chromium (Xvfb + KasmVNC) on host port 6901:"
docker rm -f kasmvnc-spike >/dev/null 2>&1 || true
docker run -d --name kasmvnc-spike \
  --shm-size=1g \
  -p 6901:6901 \
  -e VNC_PW=spikepw \
  --restart unless-stopped \
  kasmweb/chromium:1.16.1
sleep 8
echo "--- container logs (tail) ---"
docker logs kasmvnc-spike 2>&1 | tail -15
docker ps --filter name=kasmvnc-spike --format '{{.Status}}' | grep -q Up && pass P2_start || fail P2_start
echo "Connect in a browser to https://<PI_LAN_IP>:6901 (user: kasm_user, password: spikepw)."
echo "Pass only when you can open it THROUGH NPM with WebSockets (jobs-review.<domain>) — that is D3 later."

# ---------------- P3: RAM per tab (mock-first) ----------------
say "P3 RAM per tab (mock page, NOT a real ATS)"
mkdir -p /tmp/mock && cat >/tmp/mock/form.html <<'HTML'
<!doctype html><html><head><meta charset="utf-8"><title>Mock Application</title></head>
<body><h1>Mock Application</h1><form id="app" onsubmit="return false">
<label>Full name <input name="full_name" type="text"></label><br>
<label>Email <input name="email" type="email"></label><br>
<label>Phone <input name="phone" type="tel"></label><br>
<label>Years of experience <input name="years" type="number"></label><br>
<label>Cover letter <textarea name="cover_letter" rows="8"></textarea></label><br>
<label>LinkedIn <input name="linkedin" type="url"></label><br>
<label>Website <input name="website" type="url"></label><br>
<button type="submit">Submit Application</button></form>
<p>Mock fixture — no real data leaves this Pi.</p></body></html>
HTML
(cd /tmp/mock && nohup python3 -m http.server 8123 >/tmp/mock/http.log 2>&1 & echo $! >/tmp/mock/pid)
echo "Mock form served at http://<PI_LAN_IP>:8123/form.html"
echo "In the KasmVNC session from P2, open 1 tab, then 3, then 5 tabs to that URL."
echo "After EACH count, run the two lines below and note the numbers:"
echo "  docker stats kasmvnc-spike --no-stream"
echo "  free -h"
echo "PASS if total used RAM stays under ~6GB at 5 tabs with no swap thrash (si/so ~0 in 'free -h' / vmstat 1)."

# ---------------- P4: browser-use headed vs headless on mock form ----------------
say "P4 browser-use headed vs headless (needs Ollama reachable + the venv from workflow-use.sh)"
echo "First confirm Ollama is reachable from the Pi (O6 Pi-side check):"
OLLAMA_IP="${OLLAMA_IP:-ai.siggy-lab.org}"
curl -sS -m 5 "http://$OLLAMA_IP:11434/api/tags" >/dev/null && pass P4_ollama || fail P4_ollama
echo "(Ollama at $OLLAMA_IP; O6 firewall must already allow the Pi.)"
echo "P4 runs a browser-use fill of the mock form, headless then headed, and records time + RAM + throttled."
echo "Run it inside the venv created by workflow-use.sh:"
echo "  source ~/apply-spikes/venv/bin/activate && python3 /tmp/mock/p4_browseruse.py"
cat >/tmp/mock/p4_browseruse.py <<'PY'
import os, subprocess, time, sys
OLLAMA = os.environ.get("OLLAMA_IP", "127.0.0.1")
FORM_URL = os.environ.get("FORM_URL", "http://127.0.0.1:8123/form.html")
def free_kb():
    out = subprocess.check_output(["free", "-k"]).decode()
    return int([l for l in out.splitlines() if l.startswith("Mem:")][0].split()[2])
def throttled():
    try: return subprocess.check_output(["vcgencmd","get_throttled"]).decode().strip()
    except Exception: return "n/a"
for mode in ("headless", "headed"):
    before = free_kb()
    t0 = time.time()
    print(f"=== {mode} ===")
    print(f"ram_before_kb={before} throttled={throttled()}")
    # Placeholder: the actual browser-use Agent call is filled in once the venv + API are confirmed.
    print("TODO(browser-use agent): drive the mock form fill here (see workflow-use.sh for the pinned setup).")
    time.sleep(1)
    after = free_kb()
    print(f"ram_after_kb={after} ram_delta_kb={after-before} wall_s={time.time()-t0:.1f} throttled={throttled()}")
PY
echo "P4 is a measurement scaffold; I will finalize the exact Agent call after W1 confirms the pinned browser-use API."

# ---------------- P5: bot-detection page (GATED) ----------------
say "P5 bot-detection baseline (DO NOT RUN WITHOUT APPROVAL)"
echo "P5 visits a public bot-detection page, which is a third-party site (rule 8)."
echo "Pause here and tell me: which bot-detection URL you approve (or 'none yet')."
echo "I will then pin the exact URL + command before you run it."

say "SUMMARY"
echo "passed=$PASS failed=$FAIL"
[ ${#FAILED_IDS[@]} -gt 0 ] && echo "failed_ids: ${FAILED_IDS[*]}"
} 2>&1 | tee "$LOG"
commit_results "$MACHINE"
