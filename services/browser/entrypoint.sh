#!/bin/sh
# Start Xvfb + headed Chromium, then run the CDP relay so the worker can reach Chromium's loopback
# CDP over the browser_net (Chrome 136+ rejects non-localhost Host headers and reports a 127.0.0.1
# WebSocket URL — the relay rewrites both).
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
# Internal browser_net hosts (the mock ATS in the test profile) are reached directly, not via the
# egress proxy (which correctly blocks private ranges).
BYPASS_ARGS=""
if [ -n "${BROWSER_PROXY_BYPASS:-}" ]; then
  BYPASS_ARGS="--proxy-bypass-list=$BROWSER_PROXY_BYPASS"
fi

dbus-run-session -- "$CHROME" \
  --remote-debugging-port=9221 \
  --remote-allow-origins=* \
  $PROXY_ARGS \
  $BYPASS_ARGS \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --user-data-dir=/profile \
  --no-first-run \
  --no-default-browser-check \
  about:blank &

# CDP relay (replaces socat): rewrites Host + ws URL, tunnels the WebSocket.
exec python3 cdp_relay.py
