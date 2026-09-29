#!/usr/bin/env bash
# Spike O1-O6 — run ON THE OLLAMA BOX. Tests each model in MODELS (or a single model via
# QWEN38_TAG). Each model gets its own timestamped log (never overwrites), and results are
# auto-committed to docs/spikes/runs/ollama/ and pushed as they finish.
#
# Default mode also builds a Q3-at-64k model from the local Q3 weights (no download), guarded by
# an existence check, then tests it too. This is fallback option (C) for Open question #6.
#
#   ./ollama.sh                        # build q3-64k + test the default list
#   QWEN38_TAG=<tag> ./ollama.sh       # test just one model (skips the q3-64k build)
set -uo pipefail

MACHINE=ollama
OLLAMA="http://localhost:11434"

# ---- models to test: the Qwen3.8-27B variants relevant to the VRAM fallback decision ----
# qwen3.8-27b-64k:latest was already tested (O1-O5 recorded); these are the remainder.
if [ -n "${QWEN38_TAG:-}" ]; then
  MODELS=( "$QWEN38_TAG" )
  BUILD_Q3_64K=0
else
  MODELS=(
    qwen38-q3-32k:latest        # Q3, 13 GB, 32k — fallback (B)
    batiai/qwen3.8-27b:q3       # Q3, 13 GB — fallback (B) variant
    qwen3.8-27b-120k:latest     # Q4_K_M, 17 GB, 120k — context ceiling probe
    qwen-32k:latest             # 17 GB, 32k — Q4 at lower context (O1 reveals what it is)
  )
  BUILD_Q3_64K=1
fi

if [ -n "${QWEN38_TAG:-}" ]; then
  echo "MODE: single-model (QWEN38_TAG is set in your environment). Testing: ${MODELS[*]}"
  echo "  To run the full sweep instead, unset it first:  unset QWEN38_TAG && ./ollama.sh"
else
  echo "MODE: full sweep. Will build q3-64k (if absent) then test: ${MODELS[*]}"
fi

# Q3-at-64k (fallback C): rebase the local Q3 weights with num_ctx 65536. No GGUF download.
Q3_64K="qwen38-q3-64k:latest"
Q3_SRC="${Q3_SRC:-qwen38-q3-32k:latest}"

# ---- logging: one timestamped file per model, so runs never overwrite each other ----
LOG_DIR="${APPLY_LOG_DIR:-$HOME/apply-spikes/logs}"
mkdir -p "$LOG_DIR"

say()  { printf '\n########## %s ##########\n' "$1"; }
pass() { PASS=$((PASS+1)); printf 'RESULT: %-3s PASS\n' "$1"; }
fail() { FAIL=$((FAIL+1)); FAILED_IDS+=("$1"); printf 'RESULT: %-3s FAIL\n' "$1"; }

command -v curl    >/dev/null || { echo "curl is required"; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required"; exit 2; }

commit_results() {
  local logfile="$1"; local safe="$2"
  local repo="${APPLY_REPO:-}"
  if [ -z "$repo" ]; then
    repo="$(git -C "$(cd "$(dirname "$0")" 2>/dev/null && pwd)" rev-parse --show-toplevel 2>/dev/null || true)"
  fi
  if [ -z "$repo" ]; then
    repo="$HOME/apply-app"
    if [ ! -d "$repo/.git" ]; then
      git clone https://github.com/puelloc/apply-app.git "$repo" >/dev/null 2>&1 || {
        echo "COMMIT SKIPPED: no repo at $repo and clone failed. Log saved at $logfile"; return 0; }
    fi
  fi
  git -C "$repo" config user.email >/dev/null 2>&1 || git -C "$repo" config user.email "spike-bot@localhost"
  git -C "$repo" config user.name  >/dev/null 2>&1 || git -C "$repo" config user.name  "spike-bot"
  local dest="$repo/docs/spikes/runs/$MACHINE"
  mkdir -p "$dest"
  cp "$logfile" "$dest/$(basename "$logfile")"
  export GIT_TERMINAL_PROMPT=0
  if git -C "$repo" add "docs/spikes/runs/$MACHINE/$(basename "$logfile")" 2>&1 \
     && git -C "$repo" commit -q -m "spike($MACHINE/$safe): results $(basename "$logfile")" 2>&1 \
     && git -C "$repo" push origin main 2>&1; then
    echo "RESULTS COMMITTED + PUSHED: $dest/$(basename "$logfile")"
  else
    echo "COMMIT/PUSH FAILED — log saved at $logfile (staged in $repo). Fix git credentials on this machine to auto-push."
  fi
}

# Build qwen38-q3-64k from the local Q3 weights, only if it doesn't already exist.
ensure_q3_64k() {
  if ollama show "$Q3_64K" >/dev/null 2>&1; then
    echo "SKIP: $Q3_64K already exists — not rebuilding."
    return 0
  fi
  if ! ollama show "$Q3_SRC" >/dev/null 2>&1; then
    echo "ERROR: source model $Q3_SRC does not exist, so $Q3_64K cannot be built."
    return 1
  fi
  local mf="$LOG_DIR/q3-64k.Modelfile"
  cat > "$mf" <<EOF
FROM $Q3_SRC
PARAMETER num_ctx 65536
EOF
  echo "Creating $Q3_64K from $Q3_SRC (num_ctx 65536):"
  ollama create "$Q3_64K" -f "$mf" 2>&1 | tail -15
  if ollama show "$Q3_64K" >/dev/null 2>&1; then
    echo "CREATED: $Q3_64K"
  else
    echo "CREATE FAILED: $Q3_64K — see output above."
  fi
}

run_tests() {
  local TAG="$1"
  local safe; safe="$(printf '%s' "$TAG" | tr '/:' '__')"
  local LOG="$LOG_DIR/${MACHINE}-${safe}-$(date +%Y%m%d-%H%M%S).log"

  {
    PASS=0; FAIL=0; FAILED_IDS=()
    echo "===== MODEL: $TAG ====="

    # O1: version + model info (context length, quant, arch, capabilities, default num_ctx)
    say "O1 version and model"
    ollama --version || true
    ollama show "$TAG" >/tmp/o1_show.txt 2>&1 && { pass O1; } || { fail O1; }
    sed -n '1,45p' /tmp/o1_show.txt

    # O2: load at num_ctx 65536, then measure offload + VRAM. If 64k is refused, retry native
    # context so we still capture the offload/VRAM number for the model's real ceiling.
    say "O2 load at 64k + offload/VRAM"
    curl -sS "$OLLAMA/api/generate" \
      -d "{\"model\":\"$TAG\",\"prompt\":\"ping\",\"stream\":false,\"options\":{\"num_ctx\":65536}}" \
      >/tmp/o2.json 2>/tmp/o2.err
    if python3 -c "import json; d=json.load(open('/tmp/o2.json')); assert 'response' in d" 2>/dev/null; then
      pass O2_64k_load
    else
      echo "64k load returned no response (model max context likely < 64k):"
      head -c 250 /tmp/o2.json; echo; head -3 /tmp/o2.err
      echo "Retrying at native context to still capture offload/VRAM:"
      curl -sS "$OLLAMA/api/generate" -d "{\"model\":\"$TAG\",\"prompt\":\"ping\",\"stream\":false}" >/tmp/o2.json 2>/tmp/o2.err
      python3 -c "import json; d=json.load(open('/tmp/o2.json')); print('native response:', d.get('response','')[:40])" 2>/dev/null \
        || echo "native load also failed"
    fi
    echo "--- ollama ps (SIZE + PROCESSOR offload% + CONTEXT) ---"; ollama ps
    echo "--- rocm-smi vram (20 GB card) ---"; rocm-smi --showmeminfo vram 2>&1 | sed -n '1,15p'
    echo "CHECK: PROCESSOR '100% GPU' + VRAM < ~90% means it fits on-GPU. Paste the lines above."

    # O3: ~60k-token truncation check (models whose max context < 64k will error here — that IS the data point).
    say "O3 60k-token prompt_eval_count"
    python3 - "$TAG" <<'PY'
import json, sys, urllib.request
tag = sys.argv[1]
para = ("The quick brown fox jumps over the lazy dog and the project ships reliable software. "
        "Remote-friendly engineering with careful review and steady progress. ")
text = (para * 12000)[:360000]
req = urllib.request.Request("http://localhost:11434/api/generate",
    data=json.dumps({"model": tag, "prompt": text, "stream": False,
                     "options": {"num_ctx": 65536}}).encode(),
    headers={"Content-Type": "application/json"})
try:
    d = json.load(urllib.request.urlopen(req, timeout=600))
    pe = d.get("prompt_eval_count"); ec = d.get("eval_count")
    print(f"input_chars={len(text)} est_tokens~{len(text)//6}")
    print(f"prompt_eval_count={pe} eval_count={ec}")
    print("PASS" if (pe and pe >= 55000) else "CHECK: prompt_eval_count low -> possible truncation")
except urllib.error.HTTPError as e:
    print("HTTP error", e.code, e.read()[:300].decode('utf-8','replace'))
    print("NOTE: a context-length error here means the model's max context < 64k (expected for 32k models).")
PY

    # O4: JSON schema + tool calls (50 each)
    say "O4 JSON schema + tool calls (50 each)"
    python3 - "$TAG" <<'PY'
import json, sys, urllib.request
tag = sys.argv[1]
def chat(payload):
    req = urllib.request.Request("http://localhost:11434/api/chat",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))

schema = {"type": "object", "properties": {"name": {"type": "string"},
          "years": {"type": "integer"}}, "required": ["name", "years"]}
schema_ok = 0; schema_bad = []
for i in range(50):
    try:
        d = chat({"model": tag, "stream": False, "format": schema,
                  "messages": [{"role": "user",
                    "content": "Return {\"name\":\"Ada Lovelace\",\"years\":12} as JSON."}]})
        c = d["message"]["content"]
        json.loads(c); schema_ok += 1
    except Exception as e:
        schema_bad.append(str(e)[:120])

tool = {"type": "function", "function": {"name": "set_answer",
        "parameters": {"type": "object", "properties": {"field": {"type": "string"},
        "value": {"type": "string"}}, "required": ["field", "value"]}}}
tool_ok = 0; tool_bad = []
for i in range(50):
    try:
        d = chat({"model": tag, "stream": False, "tools": [tool],
                  "messages": [{"role": "user",
                    "content": "Set the city field to Denver."}]})
        tc = d["message"].get("tool_calls") or []
        args = tc[0]["function"]["arguments"] if tc else None
        if isinstance(args, str): json.loads(args)
        if tc: tool_ok += 1
        else: tool_bad.append("no tool_calls")
    except Exception as e:
        tool_bad.append(str(e)[:120])

print(f"schema_valid={schema_ok}/50  failures={len(schema_bad)}")
for b in schema_bad[:3]: print("  schema-fail:", b)
print(f"tool_valid={tool_ok}/50  failures={len(tool_bad)}")
for b in tool_bad[:3]: print("  tool-fail:", b)
print("PASS" if (schema_ok >= 49 and tool_ok >= 49) else "CHECK: below 98%")
PY

    # O5: think toggle + throughput (native context, so it works for every model)
    say "O5 think on/off"
    python3 - "$TAG" <<'PY'
import json, sys, time, urllib.request
tag = sys.argv[1]
def gen(think):
    body = {"model": tag, "stream": False, "prompt": "In one short sentence, name a planet."}
    if think is not None:
        body["think"] = think
    req = urllib.request.Request("http://localhost:11434/api/generate",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    d = json.load(urllib.request.urlopen(req, timeout=600))
    dt = time.time() - t0
    return d, dt
for label, think in [("think:true", True), ("think:false", False)]:
    try:
        d, dt = gen(think)
        ec = d.get("eval_count"); ed = d.get("eval_duration", 0)
        tps = (ec / (ed/1e9)) if ed else 0
        print(f"{label}: eval_count={ec} eval_duration_ns={ed} tok/s={tps:.1f} wall={dt:.2f}s")
        print(f"   response: {d.get('response','')[:60]!r}")
    except Exception as e:
        print(f"{label}: ERROR {e}")
print("CHECK: does think:false change eval_count/timing? Record which knob is honored.")
PY

    say "SUMMARY"
    echo "model=$TAG passed=$PASS failed=$FAIL"
    [ ${#FAILED_IDS[@]} -gt 0 ] && echo "failed_ids: ${FAILED_IDS[*]}"
  } 2>&1 | tee "$LOG"

  commit_results "$LOG" "$safe"
}

# ---- main ----
if [ "$BUILD_Q3_64K" = "1" ]; then
  CREATE_LOG="$LOG_DIR/${MACHINE}-create-q3-64k-$(date +%Y%m%d-%H%M%S).log"
  { ensure_q3_64k; } 2>&1 | tee "$CREATE_LOG"
  commit_results "$CREATE_LOG" "create-q3-64k"
  MODELS+=( "$Q3_64K" )   # test the model we just ensured exists
fi

prev=""
for m in "${MODELS[@]}"; do
  if [ -n "$prev" ]; then
    ollama stop "$prev" >/dev/null 2>&1 || true
    echo "Unloaded $prev so the next model loads into clean VRAM."
  fi
  run_tests "$m"
  prev="$m"
done

# O6 keep_alive: set it on the last-tested model, then leave it loaded for the idle check.
say "O6 keep_alive"
curl -sS "$OLLAMA/api/generate" -d "{\"model\":\"$prev\",\"prompt\":\"hi\",\"stream\":false,\"keep_alive\":\"30m\"}" >/dev/null \
  && echo "keep_alive=30m set on $prev"
echo "After ~2 min of idle, run: ollama ps   ($prev should STILL be listed, not unloaded)"

# O6 firewall instructions — model-agnostic, printed once.
say "O6 firewall — Ollama is proxy-fronted (https://ai.siggy-lab.org)"
echo "The reverse proxy reaches Ollama on :11434; the Pi reaches it via https://ai.siggy-lab.org."
echo "So the raw :11434 must be firewalled to ONLY the proxy (not LAN-exposed to the Pi or others)."
echo "Run these on this box, replacing <PROXY_LAN_IP> with the proxy's (NPM) LAN IP:"
echo "  sudo ufw allow from <PROXY_LAN_IP> to any port 11434 proto tcp"
echo "  sudo ufw deny 11434"
echo "  sudo ufw status verbose"
echo "Then verify:"
echo "  Pi (via proxy): curl -sS -m 5 https://ai.siggy-lab.org/api/tags   (should succeed)"
echo "  Pi (raw port):  curl -sS -m 5 http://<OLLAMA_LAN_IP>:11434/api/tags  (should FAIL — raw port not LAN-exposed)"
