#!/usr/bin/env bash
# Build the browser image and verify Xvfb + Chromium start and CDP answers (N4).
# CDP is published to 127.0.0.1 only for this smoke test — in compose it stays on the internal
# browser_net, never published. Linux/Pi only.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="apply-browser"
CT="browser-smoke"

echo "Building $IMAGE ..."
docker build -q -t "$IMAGE" "$SCRIPT_DIR/services/browser" || { echo "build failed"; exit 1; }

docker rm -f "$CT" >/dev/null 2>&1 || true
docker run -d --name "$CT" -p 127.0.0.1:9222:9222 -v browser-smoke-profile:/profile "$IMAGE" >/dev/null

sleep 5
version="$(curl -sS http://127.0.0.1:9222/json/version 2>/dev/null || true)"
if echo "$version" | grep -q '"Browser"'; then
  echo "PASS: CDP responds ($(echo "$version" | grep -o '"Browser": *"[^"]*"'))"
else
  echo "FAIL: CDP did not respond"
  docker logs "$CT" 2>&1 | tail -20
  exit 1
fi

echo "Container left running. Remove: docker rm -f $CT && docker volume rm browser-smoke-profile"
