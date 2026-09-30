#!/usr/bin/env bash
# End-to-end (step 6d): generate secrets -> compose up (test profile) -> seed a mock-ATS job -> watch.
# The API is not published to the host (prod fronts it via NPM), so the job is seeded from inside
# the api container. Linux (Pi) only.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# 1. Generate the API tokens + worker token (fake/canary-safe; never commit real values).
mkdir -p secrets
[ -s secrets/worker_api_token.txt ] || openssl rand -hex 32 > secrets/worker_api_token.txt
for f in api_admin_token_hash api_diagnose_token_hash mcp_api_token_hash; do
  if [ ! -s "secrets/$f.txt" ]; then
    tok=$(openssl rand -hex 32)
    printf '%s' "$tok" | sha256sum | awk '{print $1}' > "secrets/$f.txt"
  fi
done
# The worker uses the ops token; its hash is what the api compares against.
printf '%s' "$(cat secrets/worker_api_token.txt)" | sha256sum | awk '{print $1}' > secrets/api_ops_token_hash.txt
[ -s secrets/imap_user.txt ] || echo "canary@example.invalid" > secrets/imap_user.txt
[ -s secrets/imap_pass.txt ] || echo "CANARY-imap-pass" > secrets/imap_pass.txt

# 2. Compose up (test profile adds mock-ats). Exclude `mcp` (its image lands in step 9).
echo "Starting the stack (test profile) ..."
docker compose --profile test up -d --build api worker browser egress-proxy mock-ats

# 3. Seed a job pointing at the mock Greenhouse form.
echo "Waiting for the api ..."
for _ in $(seq 1 30); do
  docker compose exec -T api python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" >/dev/null 2>&1 && break
  sleep 2
done

OPS_TOKEN=$(cat secrets/worker_api_token.txt)
docker compose exec -T api python3 -c "
import urllib.request, json
body = json.dumps({'company_name':'Acme','title':'Engineer','listing_url':'http://mock-ats:8000/greenhouse.html','application_url':'http://mock-ats:8000/greenhouse.html','ats':'greenhouse'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/jobs', data=body, headers={'Authorization':'Bearer $OPS_TOKEN','Content-Type':'application/json'}, method='POST')
print('seeded job:', urllib.request.urlopen(req).read().decode())
"

echo
echo "Watch the worker: docker logs -f $(docker compose ps -q worker)"
echo "Check step events (after the run):"
echo "  docker compose exec api python3 -c \"import urllib.request,json; r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/jobs/1/step-events', headers={'Authorization':'Bearer $OPS_TOKEN'})); print(json.dumps(json.load(r), indent=2))\""
