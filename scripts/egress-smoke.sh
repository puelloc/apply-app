#!/usr/bin/env bash
# Smoke-test the egress proxy's core behavior BEFORE writing the full N suite.
# Run on the Pi (needs docker + internet). Verifies the four things that matter most:
#   - HTTPS tunnels through CONNECT
#   - HTTP is forwarded
#   - a private IP is denied
#   - a loopback host (localtest.me -> 127.0.0.1) is denied (DNS-rebinding defense)
# Leaves the container running so you can `docker logs egress-proxy-smoke` to see the domain audit.
set -uo pipefail

IMG="egress-proxy-smoke"
CT="egress-proxy-smoke"
PROXY="http://127.0.0.1:3128"

echo "Building $IMG ..."
docker build -t "$IMG" ./services/egress-proxy || { echo "build failed"; exit 1; }

docker rm -f "$CT" >/dev/null 2>&1 || true
docker run -d --name "$CT" -p 3128:3128 "$IMG"
sleep 2

check() {  # check <desc> <expected-http-code> <url>
  local code
  code="$(curl -sS -o /dev/null -m 15 -w '%{http_code}' -x "$PROXY" "$3")"
  if [ "$code" = "$2" ]; then
    echo "PASS: $1 -> $code"
  else
    echo "FAIL: $1 -> got $code, expected $2"
  fi
}

check "HTTPS CONNECT (example.com)"      200 "https://example.com"
check "HTTP forward   (example.com)"     200 "http://example.com"
check "private IP denied (192.168.1.1)"  403 "http://192.168.1.1"
check "loopback denied (localtest.me)"   403 "http://localtest.me"

echo
echo "Container left running. Inspect the domain audit with:  docker logs $CT"
echo "Remove it with:  docker rm -f $CT"
