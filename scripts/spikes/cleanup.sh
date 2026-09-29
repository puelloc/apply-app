#!/usr/bin/env bash
# Remove what the spike installed on the HOST. Run AFTER the spike is done.
# The spike now runs in Docker (run-spike.sh), so the host artifacts below are no longer needed.
set -uo pipefail

echo "This removes spike artifacts from the Pi host:"
echo "  ~/apply-spikes/venv        (Python venv with browser-use/workflow-use)"
echo "  ~/.cache/ms-playwright     (Playwright Chromium download)"
echo "  ~/apply-spikes             (fixtures/logs/lockfile scratch)"
echo
echo "The committed files in the repo (scripts/spikes/*, docs/spikes/runs/*) are NOT touched."
read -r -p "Continue? [y/N] " ans
case "$ans" in
  y|Y) ;;
  *) echo "aborted"; exit 0 ;;
esac

rm -rf ~/apply-spikes/venv ~/.cache/ms-playwright ~/apply-spikes
echo "Removed venv, playwright cache, and ~/apply-spikes scratch."

echo
echo "Note: OS libraries installed by 'playwright install-deps' (libnss3, libatk, libgbm, ...)"
echo "are left in place — they're standard packages and harmless. To also remove them:"
echo "  sudo apt-get autoremove --purge"
