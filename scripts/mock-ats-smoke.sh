#!/usr/bin/env bash
# Smoke-test the mock-ats server: serve fixtures + record a POST (the S1/S2 surface).
# Run on the Pi (needs docker). Leaves the container running.
set -uo pipefail

IMG="mock-ats-smoke"
CT="mock-ats-smoke"
PORT="8000"
BASE="http://127.0.0.1:$PORT"

docker build -q -t "$IMG" ./services/mock-ats || { echo "build failed"; exit 1; }
docker rm -f "$CT" >/dev/null 2>&1 || true
docker run -d --name "$CT" -p "$PORT:8000" "$IMG" >/dev/null
sleep 2

get="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/greenhouse.html")"
if [ "$get" = "200" ]; then echo "PASS: GET greenhouse.html ($get)"; else echo "FAIL: GET greenhouse.html ($get)"; fi

# POST a signup with the canary password; confirm it is recorded (the S1 receipt).
curl -sS -o /dev/null -X POST --data "name=Test&email=canary@example.invalid&password=CANARY-secret-pw-9f3a" "$BASE/signup"
logged="$(docker exec "$CT" grep -c 'CANARY-secret-pw-9f3a' /app/submissions.log 2>/dev/null || true)"
if [ "${logged:-0}" -gt 0 ]; then echo "PASS: POST /signup recorded ($logged line(s))"; else echo "FAIL: POST /signup not recorded"; fi

echo
echo "Fixtures:  $BASE/greenhouse.html  $BASE/lever.html  $BASE/ashby.html  $BASE/signup.html"
echo "Container left running. Remove with: docker rm -f $CT"
