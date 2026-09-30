#!/usr/bin/env bash
# S1 canary leak test: a fake password used in a signup must never appear in any leak surface.
#
# The canary VALUE is defined in services/mock-ats/fixtures/canary.txt; this script greps the
# *artifacts* (not the source) for it. Zero hits = pass.
#
# The browser-signup step and the browser-profile/screenshot/trace/DOM/agent-history/MCP targets
# are wired in later steps (5 and 9) as those surfaces come online. The mock server's own
# `submissions.log` is the EXPECTED receipt of the signup, so it is deliberately excluded.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANARY="$(cat "$ROOT/services/mock-ats/fixtures/canary.txt")"

# Leak surfaces to grep. Add paths as they exist:
#   step 5: browser profile volume, screenshots, DOM dumps, agent history
#   step 9: MCP responses, diagnostic bundles
TARGETS=(
  "$ROOT/docs/spikes/runs"          # spike run logs (committed)
  "${HOME:-/tmp}/apply-spikes"      # spike scratch (workflow files)
)

hits=0
for target in "${TARGETS[@]}"; do
  [ -e "$target" ] || continue
  while IFS= read -r f; do
    echo "LEAK: $f"
    hits=$((hits + 1))
  done < <(grep -R -l --fixed-strings "$CANARY" "$target" 2>/dev/null)
done

if [ "$hits" -eq 0 ]; then
  echo "S1 PASS: canary not found in any leak surface"
else
  echo "S1 FAIL: canary found in $hits file(s)"
  exit 1
fi
