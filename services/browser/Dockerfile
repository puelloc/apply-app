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

# KasmVNC (review viewing). Version + sha256 pinned (rule 10); the .deb is the KasmVNC GitHub release.
ARG TARGETARCH
ARG KASMVNC_VERSION=1.5.0
RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) SUM="770fd3df51510beecc89666879d82faf411276e68c6e11df612f736b891b5f71" ;; \
      arm64) SUM="aa83a1a6c9069d1a02239988b07a3a2a082a433042b4d4ee2b9e9f6b2df9643c" ;; \
      *) echo "unsupported arch $TARGETARCH"; exit 1 ;; \
    esac; \
    apt-get update; \
    curl -fsSL "https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_bookworm_${KASMVNC_VERSION}_${TARGETARCH}.deb" -o /tmp/kasmvnc.deb; \
    echo "$SUM  /tmp/kasmvnc.deb" | sha256sum -c -; \
    apt-get install -y --no-install-recommends /tmp/kasmvnc.deb; \
    rm -rf /var/lib/apt/lists/* /tmp/kasmvnc.deb

# KasmVNC user: kasmvncserver refuses to run without a user with write access (interactive prompt).
# Home on /tmp so it stays writable under the read-only rootfs.
RUN useradd -m -d /tmp/kasm-user -s /bin/bash kasm-user

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
RUN mkdir -p /etc/kasmvnc
COPY kasmvnc.yaml /etc/kasmvnc/kasmvnc.yaml
RUN chmod +x entrypoint.sh

EXPOSE 9222 8443

CMD ["./entrypoint.sh"]
