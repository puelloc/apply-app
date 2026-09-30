#!/usr/bin/env bash
# Build the browser image and run the S2 submit-guard suite in Docker (matching deployment).
# Linux (Pi) only; --network host so the container's Chromium reaches the mock form on 127.0.0.1.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="apply-browser"

echo "Building $IMAGE ..."
docker build -t "$IMAGE" "$SCRIPT_DIR/services/browser" || { echo "build failed"; exit 1; }

echo "Running S2 in Docker ..."
docker run --rm --network host \
  -v "$SCRIPT_DIR:/app" \
  "$IMAGE" python3 -u services/browser/s2_submit_guard.py
