#!/bin/sh
# Start Xvnc (KasmVNC's Xvnc serves the review web UI) + headed Chromium, then run the CDP relay so
# the worker can reach Chromium's loopback CDP over the browser_net.
#
# We launch Xvnc directly rather than the `kasmvncserver` Perl wrapper: the wrapper refuses to run
# non-interactively without a KasmVNC user ("No users configured and prompting is prohibited").
# Xvnc runs fine as root and accepts local X clients with no XAUTHORITY.
set -e

# /tmp is a tmpfs, so the X socket dir must be created at runtime.
mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

Xvnc :99 \
  -geometry 1920x1080 -depth 24 \
  -interface 0.0.0.0 \
  -websocketPort 8443 \
  -httpd /usr/share/kasmvnc/www \
  -sslOnly 0 \
  -disableBasicAuth \
  -SecurityTypes None \
  -AlwaysShared \
  >/tmp/xvnc.log 2>&1 &
XVNC_PID=$!

# Wait for the X socket instead of racing Chromium.
for _ in $(seq 1 50); do
  [ -S /tmp/.X11-unix/X99 ] && break
  kill -0 "$XVNC_PID" 2>/dev/null || { echo "Xvnc died:"; cat /tmp/xvnc.log; exit 1; }
  sleep 0.2
done
[ -S /tmp/.X11-unix/X99 ] || { echo "Xvnc socket never appeared"; cat /tmp/xvnc.log; exit 1; }

export DISPLAY=:99
openbox >/dev/null 2>&1 &

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
