#!/bin/sh
# Start Xvfb + headed Chromium, then forward CDP to the container's external interface.
#
# Chrome 136+ removed --remote-debugging-address, so Chromium's CDP only binds 127.0.0.1. We run
# Chromium on loopback 9221 and socat-forward 0.0.0.0:9222 -> 127.0.0.1:9221 so the worker can reach
# CDP over the internal browser_net.
set -e

Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!

CHROME=$(python3 - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
EOF
)

# The browser's ONLY route out is the egress proxy (compose sets BROWSER_PROXY=http://egress-proxy:3128).
PROXY_ARGS=""
if [ -n "${BROWSER_PROXY:-}" ]; then
  PROXY_ARGS="--proxy-server=$BROWSER_PROXY"
fi

dbus-run-session -- "$CHROME" \
  --remote-debugging-port=9221 \
  $PROXY_ARGS \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --user-data-dir=/profile \
  --no-first-run \
  --no-default-browser-check \
  about:blank &

exec socat TCP-LISTEN:9222,bind=0.0.0.0,reuseaddr,fork TCP:127.0.0.1:9221
