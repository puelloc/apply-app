# Spike image: browser-use + workflow-use + Chromium, for the W1-W3 and P4 drivers.
# Mirrors jobs-app's worker recipe (python:3.12-slim + playwright install --with-deps chromium),
# so the spike runs the same way it will deploy — in Docker, not on the bare host.
#
# Build + run via run-spike.sh (mounts this dir at /spike and uses --network host).

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin the exact versions discovered in the spike (rule 10). Python 3.12 is required:
# workflow-use pins faiss-cpu==1.10.0, which has no Python 3.14 wheel.
RUN python3 -m venv /venv \
 && /venv/bin/pip install --no-cache-dir \
      "playwright==1.58.0" \
      "browser-use==0.13.10" \
      "workflow-use==0.2.11" \
 && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright /venv/bin/playwright install --with-deps chromium \
 && chmod -R a+rX /ms-playwright

ENV PATH="/venv/bin:${PATH}" \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    XDG_CONFIG_HOME=/tmp/.config \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    BROWSER_USE_CONFIG_DIR=/tmp/.browseruse \
    BROWSER_USE_BROWSER_ARGS="--no-sandbox --disable-gpu --disable-dev-shm-usage" \
    ANONYMIZED_TELEMETRY=false \
    BROWSER_USE_VERSION_CHECK=false

WORKDIR /spike
