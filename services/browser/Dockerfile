# Browser service: headed Chromium under Xvfb + KasmVNC (human viewing for review), CDP on the
# internal browser_net (never published). KasmVNC is the review UI's view of the same parked browser.
#
# Build + verify via scripts/browser-smoke.sh (Linux/Pi).

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      dbus \
      socat \
      xvfb \
      x11-xserver-utils \
      openbox \
    && rm -rf /var/lib/apt/lists/*

# KasmVNC (review viewing). The .deb URL is the KasmVNC GitHub release; VERIFY the exact tag/arch on
# the Pi before relying on it (first build is the check).
ARG TARGETARCH
ARG KASMVNC_VERSION=1.3.3
RUN apt-get update \
 && curl -fsSL "https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_bookworm_${KASMVNC_VERSION}_${TARGETARCH}.deb" -o /tmp/kasmvnc.deb \
 && apt-get install -y --no-install-recommends /tmp/kasmvnc.deb \
 && rm -rf /var/lib/apt/lists/* /tmp/kasmvnc.deb

# Pin playwright exactly (rule 10). --with-deps installs Chromium's system libraries via apt.
RUN python3 -m venv /venv \
 && /venv/bin/pip install --no-cache-dir "playwright==1.58.0" \
 && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright /venv/bin/playwright install --with-deps chromium \
 && chmod -R a+rX /ms-playwright

ENV PATH="/venv/bin:${PATH}" \
    HOME=/tmp \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    ANONYMIZED_TELEMETRY=false \
    DISPLAY=:99

WORKDIR /app
COPY entrypoint.sh cdp_relay.py ./
RUN chmod +x entrypoint.sh

EXPOSE 9222 8443

CMD ["./entrypoint.sh"]
