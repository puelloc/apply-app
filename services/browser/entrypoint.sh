#!/bin/sh
# Start Xvfb + headed Chromium with CDP on 9222 (reachable only on the internal browser_net).
set -e

Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT

CHROME=$(python3 - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
EOF
)

exec dbus-run-session -- "$CHROME" \
  --remote-debugging-address=0.0.0.0 \
  --remote-debugging-port=9222 \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --user-data-dir=/profile \
  --no-first-run \
  --no-default-browser-check \
  about:blank
