#!/bin/sh
# Start KasmVNC (headed display + review viewing) + headed Chromium, then run the CDP relay so the
# worker can reach Chromium's loopback CDP over the browser_net.
set -e

# KasmVNC starts its own Xvfb on :99 and serves the review web UI on 8443. Grant kasm-user write
# access + a default password (auth is replaced by NPM auth_request in step 9), then start it.
echo -e 'kasm\nkasm\n' | kasmvncpasswd -u kasm-user -w >/dev/null 2>&1 || true
kasmvncserver :99 -geometry 1920x1080 -depth 24 >/tmp/kasmvnc.log 2>&1 &
KASMVNC_PID=$!

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

# Remove a stale profile lock left by a force-killed previous run (single-instance, so safe).
rm -f /profile/SingletonLock /profile/SingletonCookie /profile/SingletonSocket 2>/dev/null || true

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
