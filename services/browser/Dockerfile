# Browser service: headed Chromium under Xvfb, CDP on the internal browser_net (never published).
# KasmVNC (human viewing) is deferred to the review UI (step 8) — this image is the automation
# browser the worker drives over CDP.
#
# Build + verify via scripts/browser-smoke.sh (Linux/Pi).

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      dbus \
      xvfb \
      x11-xserver-utils \
    && rm -rf /var/lib/apt/lists/*

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
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 9222

CMD ["./entrypoint.sh"]
