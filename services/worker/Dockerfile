# Worker image: browser-use + workflow-use + Chromium + the API client + the vault.
# Build context is the repo root (see compose.yaml), so it can COPY services/api/app/vault.py.
# Mirrors the spike image recipe (rule 10: pinned, telemetry off, --with-deps for Chromium's libs).

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/worker/requirements.txt ./
RUN python3 -m venv /venv \
 && /venv/bin/pip install --no-cache-dir -r requirements.txt \
 && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright /venv/bin/playwright install --with-deps chromium \
 && chmod -R a+rX /ms-playwright

COPY services/worker/*.py ./
# The vault is shared with the api (single source in services/api/app/vault.py); consolidate into a
# shared package in a later cleanup. The submit guard is injected by the worker via browser-use's CDP.
COPY services/api/app/vault.py vault.py
COPY services/browser/guard.js guard.js

ENV PATH="/venv/bin:${PATH}" \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    XDG_CONFIG_HOME=/tmp/.config \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    BROWSER_USE_CONFIG_DIR=/tmp/.browseruse \
    BROWSER_USE_BROWSER_ARGS="--no-sandbox --disable-gpu --disable-dev-shm-usage" \
    ANONYMIZED_TELEMETRY=false \
    BROWSER_USE_VERSION_CHECK=false

CMD ["python3", "-u", "main.py"]
