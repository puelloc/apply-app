#!/usr/bin/env bash
# Step 6c (standalone): build the worker image and run the fill driver (submit guard + reasoning
# capture) against the mock ATS + Ollama. Linux (Pi) only.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="apply-worker"

echo "Building $IMAGE ..."
docker build -t "$IMAGE" -f "$SCRIPT_DIR/services/worker/Dockerfile" "$SCRIPT_DIR" || { echo "build failed"; exit 1; }

echo "Running step-6c fill in Docker ..."
docker run --rm --network host \
  -v "$SCRIPT_DIR:/spike" \
  -e OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-https://ai.siggy-lab.org}" \
  -e QWEN38_TAG="${QWEN38_TAG:-qwen38-q3-64k:latest}" \
  "$IMAGE" python3 -u /spike/scripts/step6c_fill.py
