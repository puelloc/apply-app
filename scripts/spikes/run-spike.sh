#!/usr/bin/env bash
# Build the spike image and run a driver inside Docker (matching deployment; no host pollution).
#
#   ./run-spike.sh w1w3.py            # W1-W3 record/replay/break
#   ./run-spike.sh p4_browseruse.py   # P4 headed-vs-headless fill
#
# Uses --network host so the container reaches Ollama (https://ai.siggy-lab.org) via the host's
# DNS and the mock form it serves on 127.0.0.1. Linux (the Pi) only.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DRIVER="${1:-w1w3.py}"
IMAGE="apply-spike"

case "$DRIVER" in
  w1w3.py|p4_browseruse.py) ;;
  *) echo "usage: $0 {w1w3.py|p4_browseruse.py}"; exit 2 ;;
esac

echo "Building $IMAGE ..."
docker build -t "$IMAGE" "$SCRIPT_DIR" || { echo "build failed"; exit 1; }

echo "Running $DRIVER in Docker ..."
docker run --rm --network host \
  -v "$SCRIPT_DIR:/spike" \
  -e OLLAMA_HOST="${OLLAMA_HOST:-https://ai.siggy-lab.org}" \
  -e QWEN38_TAG="${QWEN38_TAG:-qwen38-q3-64k:latest}" \
  -e ANONYMIZED_TELEMETRY=false \
  "$IMAGE" python3 "/spike/$DRIVER"
