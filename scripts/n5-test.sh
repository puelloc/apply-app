#!/usr/bin/env bash
# N5: the browser can't bypass the egress proxy — no direct TCP, no UDP (WebRTC). Linux/Pi only.
# Runs n5_checks.py inside the browser image on the INTERNAL browser_net, with the egress proxy.
set -uo pipefail

BROWSER_NET="apply-browser-net"
EGRESS_NET="apply-egress-net"
PROXY_CT="apply-egress-proxy"
IMG="apply-browser"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

docker network create "$BROWSER_NET" --internal >/dev/null 2>&1 || true
docker network create "$EGRESS_NET" >/dev/null 2>&1 || true
docker build -q -t apply-egress ./services/egress-proxy || { echo "build failed"; exit 1; }
docker rm -f "$PROXY_CT" >/dev/null 2>&1 || true
docker run -d --name "$PROXY_CT" --network "$BROWSER_NET" apply-egress >/dev/null
docker network connect "$EGRESS_NET" "$PROXY_CT" >/dev/null
sleep 2

echo "Building the browser image (used as the check container) ..."
docker build -q -t "$IMG" "$REPO/services/browser" || { echo "build failed"; exit 1; }

docker run --rm --network "$BROWSER_NET" --entrypoint python3 \
  -e EGRESS_PROXY="http://$PROXY_CT:3128" \
  -v "$REPO:/repo" \
  "$IMG" /repo/scripts/n5_checks.py

echo "Cleanup: docker rm -f $PROXY_CT; docker network rm $BROWSER_NET $EGRESS_NET"
