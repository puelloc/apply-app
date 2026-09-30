# Browser service image: Chromium + Playwright, for the submit guard and the headed browser.
# Mirrors the spike image (python:3.12-slim + playwright install --with-deps chromium) so browser
# tests run the same way they deploy — in Docker, not on the bare host (which lacks libnspr4 etc.).
#
# Build + run via scripts/s2-submit-guard.sh (mounts the repo at /app, uses --network host).

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin playwright exactly (rule 10). --with-deps installs Chromium's system libraries (libnspr4,
# libnss3, ...) via apt.
RUN python3 -m venv /venv \
 && /venv/bin/pip install --no-cache-dir "playwright==1.58.0" \
 && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright /venv/bin/playwright install --with-deps chromium \
 && chmod -R a+rX /ms-playwright

ENV PATH="/venv/bin:${PATH}" \
    HOME=/tmp \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    ANONYMIZED_TELEMETRY=false

WORKDIR /app
