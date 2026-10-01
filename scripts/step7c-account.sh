#!/usr/bin/env bash
# Step 7c: account-flow chain (signup -> verify -> confirm) against the mock IMAP. Linux/Pi only.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="apply-worker"

docker build -q -t "$IMAGE" -f "$REPO/services/worker/Dockerfile" "$REPO" || { echo "build failed"; exit 1; }

docker run --rm --network host \
  -v "$REPO:/spike" \
  -e JOB_ID=1 -e BASE_EMAIL=jobs@example.invalid \
  "$IMAGE" python3 -u /spike/scripts/step7c_account.py
