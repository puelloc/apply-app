#!/usr/bin/env bash
# Spike O1-O6 — run ON THE OLLAMA BOX (the machine hosting Ollama + the GPU).
# Needs: curl, python3. If python3 is missing, install it first and re-run.
#
# Set your model tag once (or export it before running):
#   export QWEN38_TAG="<your qwen3.8 tag>"   # e.g. qwen3.8-27b:q4_K_M
#
# Paste back, for the agent:
#   1) the final "=== SUMMARY ===" block, AND
#   2) the full output of any section that printed "FAIL" or a traceback.
set -uo pipefail

TAG="${QWEN38_TAG:-}"
OLLAMA="http://localhost:11434"
PASS=0; FAIL=0; FAILED_IDS=()

say()  { printf '\n########## %s ##########\n' "$1"; }
pass() { PASS=$((PASS+1)); printf 'RESULT: %-3s PASS\n' "$1"; }
fail() { FAIL=$((FAIL+1)); FAILED_IDS+=("$1"); printf 'RESULT: %-3s FAIL\n' "$1"; }

command -v curl    >/dev/null || { echo "curl is required"; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required"; exit 2; }

if [ -z "$TAG" ]; then
  echo "QWEN38_TAG is not set. Export it (export QWEN38_TAG=...) and re-run."
  exit 2
fi

# ---------------- O1: version + model loads ----------------
say "O1 version and model"
ollama --version || true
ollama show "$TAG" >/tmp/o1_show.txt 2>&1 && { pass O1; } || { fail O1; }
sed -n '1,40p' /tmp/o1_show.txt

# ---------------- O2: num_ctx 65536, VRAM headroom ----------------
say "O2 num_ctx 65536"
curl -sS "$OLLAMA/api/generate" -d "{\"model\":\"$TAG\",\"prompt\":\"ping\",\"stream\":false,\"options\":{\"num_ctx\":65536}}" >/tmp/o2.json 2>/tmp/o2.err
if [ -s /tmp/o2.json ] && python3 -c "import json,sys; d=json.load(open('/tmp/o2.json')); print('response ok:', d.get('response','')[:40])" 2>/dev/null; then
  pass O2a_generate
else
  echo "O2 generate failed:"; cat /tmp/o2.err; head -c 400 /tmp/o2.json; echo; fail O2a_generate
fi
echo "--- ollama ps (model should be loaded, note SIZE) ---"; ollama ps
echo "--- nvidia-smi (note VRAM used/free) ---"; nvidia-smi 2>&1 | sed -n '1,20p'
echo "CHECK: does nvidia-smi show the model in VRAM with headroom? Paste the lines above."

# ---------------- O3: ~60k tokens, no silent truncation ----------------
say "O3 60k-token prompt_eval_count"
python3 - "$TAG" <<'PY'
import json, sys, urllib.request
tag = sys.argv[1]
# ~60k tokens of English text (approx 4 chars/token => 240k chars).
para = ("The quick brown fox jumps over the lazy dog and the project ships reliable software. "
        "Remote-friendly engineering with careful review and steady progress. ") 
text = (para * 8000)[:250000]
est_tokens = len(text)//4
req = urllib.request.Request("http://localhost:11434/api/generate",
    data=json.dumps({"model": tag, "prompt": text, "stream": False,
                     "options": {"num_ctx": 65536}}).encode(),
    headers={"Content-Type": "application/json"})
try:
    d = json.load(urllib.request.urlopen(req, timeout=600))
    pe = d.get("prompt_eval_count"); ec = d.get("eval_count")
    print(f"input_chars={len(text)} est_tokens~{est_tokens}")
    print(f"prompt_eval_count={pe} eval_count={ec}")
    print("PASS" if (pe and pe >= 40000) else "CHECK: prompt_eval_count looks low -> possible truncation")
except urllib.error.HTTPError as e:
    print("HTTP error", e.code, e.read()[:500])
PY

# ---------------- O4: 50 JSON-schema + 50 tool-call chats ----------------
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

# ---------------- O5: think toggle + throughput ----------------
say "O5 think on/off"
python3 - "$TAG" <<'PY'
import json, sys, time, urllib.request
tag = sys.argv[1]
def gen(options, think):
    body = {"model": tag, "stream": False, "options": options,
            "prompt": "In one short sentence, name a planet."}
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
        d, dt = gen({"num_ctx": 65536}, think)
        ec = d.get("eval_count"); ed = d.get("eval_duration", 0)
        tps = (ec / (ed/1e9)) if ed else 0
        print(f"{label}: eval_count={ec} eval_duration_ns={ed} tok/s={tps:.1f} wall={dt:.2f}s")
        print(f"   response: {d.get('response','')[:60]!r}")
    except Exception as e:
        print(f"{label}: ERROR {e}")
print("CHECK: does think:false change eval_count/timing? Record which knob is honored.")
PY

# ---------------- O6: keep_alive + firewall ----------------
say "O6 keep_alive"
curl -sS "$OLLAMA/api/generate" -d "{\"model\":\"$TAG\",\"prompt\":\"hi\",\"stream\":false,\"keep_alive\":\"30m\"}" >/dev/null && echo "keep_alive set to 30m"
echo "After ~2 min of idle, run: ollama ps   (model should STILL be listed, not unloaded)"

say "O6 firewall (ufw) — allow ONLY the Pi"
echo "Run these, replacing <PI_LAN_IP> with the Pi's LAN IP:"
echo "  sudo ufw allow from <PI_LAN_IP> to any port 11434 proto tcp"
echo "  sudo ufw deny 11434"
echo "  sudo ufw status verbose"
echo "Then test from the Pi:       curl -sS -m 5 http://ai.siggy-lab.org:11434/api/tags   (should succeed)"
echo "Then test from ANOTHER host: curl -sS -m 5 http://ai.siggy-lab.org:11434/api/tags   (should time out/fail)"

say "SUMMARY"
echo "passed=$PASS failed=$FAIL"
[ ${#FAILED_IDS[@]} -gt 0 ] && echo "failed_ids: ${FAILED_IDS[*]}"
