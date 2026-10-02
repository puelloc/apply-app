#!/usr/bin/env bash
# Step 7e: browser-based account flow (signup fill -> verify -> apply). Linux/Pi only (needs Ollama).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="apply-worker"

docker build -q -t "$IMAGE" -f "$REPO/services/worker/Dockerfile" "$REPO" || { echo "build failed"; exit 1; }

docker run --rm --network host \
  -v "$REPO:/spike" \
  -e OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-https://ai.siggy-lab.org}" \
  -e QWEN38_TAG="${QWEN38_TAG:-qwen38-q3-64k:latest}" \
  -e BASE_EMAIL=jobs@example.invalid \
  "$IMAGE" python3 -u /spike/scripts/step7e_account.py
