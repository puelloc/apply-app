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
# tmpfs profile = fresh each run (a reused named volume keeps Chromium's SingletonLock after a
# force-remove, which makes the next run refuse to start).
docker run -d --name "$CT" -p 127.0.0.1:9222:9222 --tmpfs /profile "$IMAGE" >/dev/null

# First launch is slow (profile init + DBus setup), so poll CDP for up to 30s.
ok=""
i=0
while [ "$i" -lt 30 ]; do
  version="$(curl -sS --max-time 2 http://127.0.0.1:9222/json/version 2>/dev/null || true)"
  if echo "$version" | grep -q '"Browser"'; then
    ok="$version"
    break
  fi
  i=$((i + 1))
  sleep 1
done

if [ -n "$ok" ]; then
  echo "PASS: CDP responds ($(echo "$ok" | grep -o '"Browser": *"[^"]*"'))"
else
  echo "FAIL: CDP did not respond within 30s"
  echo "--- from inside the container ---"
  docker exec "$CT" python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9222/json/version', timeout=3).read().decode()[:200])" 2>&1 || true
  echo "--- container logs ---"
  docker logs "$CT" 2>&1 | tail -30
  exit 1
fi

echo "Container left running. Remove: docker rm -f $CT"
