#!/usr/bin/env bash
# Spike W1-W3 — run on the Pi (or any box with python3 + Chromium/Playwright).
# Verifies whether workflow-use can record a run with placeholders (W1), replay it with a
# different profile (W2), and survive a broken selector via the agent fallback (W3).
#
# This is a DISCOVERY harness: it pins versions into a lockfile and prints the real public API,
# because workflow-use is young and its exact API is unverified. Paste back the lockfile + the
# introspection output, and I will finalize the exact record/replay calls for that API.
#
# Paste back, for the agent:
#   1) the final "=== SUMMARY ===" block,
#   2) ~/apply-spikes/spikes-lock.txt, AND
#   3) the full "=== W-introspection ===" output (even if some imports FAIL — that's evidence).
set -uo pipefail

MACHINE=workflow-use

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

say() { printf '\n########## %s ##########\n' "$1"; }

{
say "W0 setup + version pinning"
mkdir -p ~/apply-spikes && cd ~/apply-spikes
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
BU_SPEC="browser-use"
[ -n "${BROWSER_USE_VER:-}" ] && BU_SPEC="browser-use==${BROWSER_USE_VER}"
WU_SPEC="workflow-use"
[ -n "${WORKFLOW_USE_VER:-}" ] && WU_SPEC="workflow-use==${WORKFLOW_USE_VER}"
echo "Installing $BU_SPEC and $WU_SPEC (pin via BROWSER_USE_VER/WORKFLOW_USE_VER)"
pip install "$BU_SPEC" 2>&1 | tail -3
pip install "$WU_SPEC" 2>&1 | tail -3
if pip show workflow-use >/dev/null 2>&1; then
  echo "W1 NOTE: workflow-use package installed (pip name confirmed)."
else
  echo "W1 NOTE: workflow-use is NOT pip-installable — W1 blocked; plan fallback = build a thin recorder."
fi
pip install playwright -q 2>&1 | tail -1
python3 -m playwright install chromium 2>&1 | tail -2
pip freeze > spikes-lock.txt
echo "Lockfile written to ~/apply-spikes/spikes-lock.txt (paste it back so I can pin the vendored commits)."

say "W-introspection (the real API)"
python3 - <<'PY'
for m in ("workflow_use", "workflowuse", "workflow", "workflow_use.recorder", "workflow_use.replay"):
    try:
        mod = __import__(m, fromlist=["*"])
        print(f"IMPORT OK: {m} -> version={getattr(mod,'__version__','?')}")
        names = [n for n in dir(mod) if not n.startswith('_')]
        print(f"  public ({len(names)}): {names[:50]}")
    except Exception as e:
        print(f"IMPORT FAIL: {m} -> {type(e).__name__}: {e}")
try:
    import browser_use
    print("browser_use version:", getattr(browser_use, "__version__", "?"))
except Exception as e:
    print("browser_use import fail:", e)
PY

say "W-fixture: mock Greenhouse form + placeholder profile + canary values"
mkdir -p ~/apply-spikes/fixture
cat > ~/apply-spikes/fixture/mock-greenhouse.html <<'HTML'
<!doctype html><html><head><meta charset="utf-8"><title>Mock Greenhouse Application</title></head>
<body><h1>Apply — Mock Greenhouse</h1>
<form id="application" method="post" action="/apply" onsubmit="return false">
  <fieldset>
    <label>First name <input name="first_name" type="text" required></label><br>
    <label>Last name  <input name="last_name"  type="text" required></label><br>
    <label>Email      <input name="email"      type="email" required></label><br>
    <label>Phone      <input name="phone"      type="tel"></label><br>
    <label>LinkedIn   <input name="linkedin"   type="url"></label><br>
    <label>Website    <input name="website"    type="url"></label><br>
  </fieldset>
  <fieldset>
    <label>Years of experience <input name="years" type="number"></label><br>
    <label>Work authorization
      <select name="work_auth"><option value="">--</option>
        <option>I am authorized to work in the US</option>
        <option>I require sponsorship</option></select></label><br>
    <label>Cover letter <textarea name="cover_letter" rows="6"></textarea></label><br>
  </fieldset>
  <button type="submit" id="submit">Submit Application</button>
</form>
<p>Mock Greenhouse fixture — no real data leaves this Pi.</p></body></html>
HTML
# Placeholder profile (used for RECORD): every value is a {{placeholder}}, never a real value.
cat > ~/apply-spikes/fixture/profile-placeholder.json <<'JSON'
{"first_name": "{{first_name}}", "last_name": "{{last_name}}", "email": "{{email}}",
 "phone": "{{phone}}", "linkedin": "{{linkedin}}", "website": "{{website}}",
 "years": "{{years}}", "work_auth": "{{work_auth}}", "cover_letter": "{{cover_letter}}"}
JSON
# Second profile (used for REPLAY, W2): different but still fake canary values.
cat > ~/apply-spikes/fixture/profile-replay.json <<'JSON'
{"first_name": "CANARY-Replay-First", "last_name": "CANARY-Replay-Last",
 "email": "canary-replay@example.invalid", "phone": "555-0001",
 "linkedin": "https://example.invalid/in/canary-replay", "website": "https://example.invalid",
 "years": "9", "work_auth": "I am authorized to work in the US",
 "cover_letter": "CANARY cover letter body for replay."}
JSON
# Canary secrets: the W1 grep must find ZERO of these in any recording/log/artifact.
cat > ~/apply-spikes/fixture/canary.txt <<'TXT'
CANARY-secret-pw-9f3a
canary@example.invalid
CANARY-Replay-First
TXT
echo "Fixture files written under ~/apply-spikes/fixture/"

say "W1: record with placeholders, then grep for leaks"
echo "Serve the fixture:"
echo "  cd ~/apply-spikes/fixture && python3 -m http.server 8124"
echo "W1 record step is finalized from the W-introspection output (the exact recorder call)."
echo "Once a recording file exists (path from the recorder), run this leak check:"
cat > ~/apply-spikes/fixture/check-leaks.sh <<'SH'
#!/usr/bin/env bash
set -uo pipefail
REC="${1:?usage: check-leaks.sh <recording_or_artifact_path>}"
hits=0
while IFS= read -r canary; do
  n=$(grep -R --fixed-strings -c "$canary" "$REC" 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
  if [ "$n" -gt 0 ]; then echo "LEAK: '$canary' found $n time(s)"; hits=$((hits+n)); fi
done < ~/apply-spikes/fixture/canary.txt
[ "$hits" -eq 0 ] && echo "W1 PASS: no real/canary values in $REC" || echo "W1 FAIL: $hits leak(s)"
SH
chmod +x ~/apply-spikes/fixture/check-leaks.sh
echo "Leak checker written to ~/apply-spikes/fixture/check-leaks.sh"

say "W2/W3 scaffolding"
echo "W2 (replay with profile-replay.json, stop before submit) and W3 (break a selector,"
echo "fallback fixes it, workflow updated) are finalized from the W-introspection output."

say "SUMMARY"
echo "Next: paste back spikes-lock.txt + W-introspection output so I can write the exact record/replay calls."
} 2>&1 | tee "$LOG"
commit_results "$MACHINE"
