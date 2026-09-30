#!/usr/bin/env bash
# N1, N2, N3, N6 — network isolation + egress-proxy checks. Run on the Pi (needs docker + internet).
#
# Sets up the same topology the compose stack will use: an INTERNAL `browser_net` (no route out)
# plus a non-internal `egress` network that only the egress proxy is attached to. A curl container
# stands in for the browser.
#
# Deferred (need services not built yet):
#   N4 (CDP port unreachable) and N5 (Chromium can't bypass the proxy) -> browser service (step 5).
#   D1-D5 (NPM/DNS/cert/access-list) -> api/mcp/browser behind NPM.
set -uo pipefail

BROWSER_NET="apply-browser-net"
EGRESS_NET="apply-egress-net"
PROXY_CT="apply-egress-proxy"
CURL_IMG="curlimages/curl"          # test-only ephemeral image, not a pinned prod dependency
PASS=0; FAIL=0

expect() {  # expect <desc> <want-code> <got-code>
  if [ "$3" = "$2" ]; then echo "PASS: $1 ($3)"; PASS=$((PASS+1));
  else echo "FAIL: $1 (got $3, want $2)"; FAIL=$((FAIL+1)); fi
}

expect_unreachable() {  # expect_unreachable <desc> <got-code>  (000/7/28/52 = couldn't reach)
  case "$2" in 000|7|28|52) echo "PASS: $1 (unreachable, $2)"; PASS=$((PASS+1));;
    *) echo "FAIL: $1 (got $2, expected unreachable)"; FAIL=$((FAIL+1));; esac
}

# Run one curl inside the browser_net container. Output: the HTTP status code (000 on failure).
curl_browser() { docker run --rm --network "$BROWSER_NET" "$CURL_IMG" -sS -o /dev/null -w '%{http_code}' "$@"; }

# ---- setup: networks + proxy ----
docker network create "$BROWSER_NET" --internal >/dev/null 2>&1 || true
docker network create "$EGRESS_NET" >/dev/null 2>&1 || true
docker build -q -t apply-egress ./services/egress-proxy || { echo "build failed"; exit 1; }
docker rm -f "$PROXY_CT" >/dev/null 2>&1 || true
docker run -d --name "$PROXY_CT" --network "$BROWSER_NET" apply-egress >/dev/null
docker network connect "$EGRESS_NET" "$PROXY_CT" >/dev/null
sleep 2

# ---- N2: public site direct (must fail) vs through the proxy (must work) ----
echo "=== N2 ==="
direct="$(curl_browser -m 8 https://example.com)"
expect_unreachable "N2 direct https://example.com" "$direct"
via="$(curl_browser -m 20 -x "http://$PROXY_CT:3128" https://example.com)"
expect "N2 via proxy https://example.com" "200" "$via"

# ---- N1: browser_net is internal (cannot reach LAN / metadata) ----
echo "=== N1 ==="
for ip in 169.254.169.254 192.168.1.1; do
  code="$(curl_browser -m 6 "http://$ip")"
  expect_unreachable "N1 reach $ip" "$code"
done

# ---- N3: DNS-rebinding defense through the proxy ----
echo "=== N3 ==="
for url in http://localtest.me http://10.0.0.1; do
  code="$(curl_browser -m 15 -x "http://$PROXY_CT:3128" "$url")"
  expect "N3 deny $url" "403" "$code"
done

# ---- N6: domain allowlist + logging ----
echo "=== N6 ==="
ALLOW_CT="apply-egress-allow"
docker rm -f "$ALLOW_CT" >/dev/null 2>&1 || true
docker run -d --name "$ALLOW_CT" --network "$BROWSER_NET" -e EGRESS_ALLOWLIST=example.com apply-egress >/dev/null
docker network connect "$EGRESS_NET" "$ALLOW_CT" >/dev/null
sleep 2
ok="$(curl_browser -m 15 -x "http://$ALLOW_CT:3128" http://example.com)"
expect "N6 allow example.com" "200" "$ok"
no="$(curl_browser -m 15 -x "http://$ALLOW_CT:3128" http://neverssl.com)"
expect "N6 deny neverssl.com" "403" "$no"
logged="$(docker logs "$ALLOW_CT" 2>&1 | grep -c 'neverssl.com' || true)"
if [ "${logged:-0}" -gt 0 ]; then echo "PASS: N6 denied domain logged ($logged line(s))"; PASS=$((PASS+1));
else echo "FAIL: N6 denied domain not logged"; FAIL=$((FAIL+1)); fi

echo
echo "N SUMMARY: pass=$PASS fail=$FAIL"
echo "Cleanup: docker rm -f $PROXY_CT $ALLOW_CT; docker network rm $BROWSER_NET $EGRESS_NET"
