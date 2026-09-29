#!/usr/bin/env bash
# Move Docker's data-root (/var/lib/docker) from the SD card to the SSD.
#
#   sudo ./move-docker-to-ssd.sh /srv/dev-disk-by-uuid-XXXX/docker
#
# Safe by construction:
#   - refuses if the target is on the SAME device as the current root (i.e. still the SD),
#   - refuses if the target is inside /var/lib/docker (recursive),
#   - checks free space,
#   - uses rsync (preserves the cached images, so no rebuild),
#   - merges data-root into /etc/docker/daemon.json instead of clobbering it,
#   - does NOT delete the old /var/lib/docker (you do that yourself after verifying).
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo $0 <ssd-target-dir>"
  exit 1
fi

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "Usage: sudo $0 <ssd-target-dir>"
  echo
  echo "Find your SSD mount point first:"
  echo "  mount | grep sda1"
  echo
  echo "Candidate block devices on this host:"
  lsblk -o NAME,SIZE,TYPE,MOUNTPOINT 2>/dev/null | grep -Ev 'loop|sr0' || true
  exit 1
fi
TARGET="${TARGET%/}"   # strip trailing slash

# --- safety: target must be a genuinely different filesystem ---
case "$TARGET" in
  /var/lib/docker)     echo "ERROR: target is already the Docker root"; exit 1 ;;
  /var/lib/docker/*)   echo "ERROR: target is INSIDE /var/lib/docker — abort"; exit 1 ;;
esac

mkdir -p "$TARGET"
ROOT_DEV="$(df --output=source /var/lib/docker | tail -1)"
TGT_DEV="$(df --output=source "$TARGET" | tail -1)"
if [ "$ROOT_DEV" = "$TGT_DEV" ]; then
  echo "ERROR: $TARGET is on the SAME device as /var/lib/docker ($ROOT_DEV)."
  echo "That means it's still the SD card. Point it at the SSD mount instead."
  exit 1
fi

NEED_MB="$(du -s --block-size=1M /var/lib/docker 2>/dev/null | awk '{print $1}')"
HAVE_MB="$(df --output=avail -BM "$TARGET" | tail -1 | tr -dc '0-9')"
echo "Current Docker root: $ROOT_DEV  (/var/lib/docker)"
echo "Target:              $TGT_DEV  ($TARGET)"
echo "Docker data ~${NEED_MB:-?} MB | target free ~${HAVE_MB:-?} MB"
if [ -n "${HAVE_MB:-}" ] && [ -n "${NEED_MB:-}" ] && [ "$HAVE_MB" -lt "$NEED_MB" ]; then
  echo "ERROR: not enough free space on target"; exit 1
fi

read -r -p "Stop Docker and rsync /var/lib/docker -> $TARGET ? [y/N] " ans
case "$ans" in y|Y) ;; *) echo "aborted"; exit 0 ;; esac

# --- stop docker (and any socket unit) ---
systemctl stop docker docker.socket 2>/dev/null || true

echo "rsyncing /var/lib/docker/ -> $TARGET/ ..."
rsync -a --info=progress2 /var/lib/docker/ "$TARGET/"

# --- merge data-root into daemon.json (backup first, don't clobber other settings) ---
DAEMON=/etc/docker/daemon.json
if [ -s "$DAEMON" ]; then
  cp -a "$DAEMON" "$DAEMON.bak.$(date +%Y%m%d%H%M%S)"
  python3 - "$TARGET" "$DAEMON" <<'PY'
import json, sys
target, path = sys.argv[1], sys.argv[2]
cfg = json.load(open(path))
cfg["data-root"] = target
json.dump(cfg, open(path, "w"), indent=2)
print("updated data-root in", path)
PY
else
  mkdir -p /etc/docker
  printf '{\n  "data-root": "%s"\n}\n' "$TARGET" > "$DAEMON"
fi

# --- restart + verify ---
systemctl start docker
echo
echo "Docker Root Dir now:"
docker info 2>/dev/null | grep -i "docker root dir" || echo "(could not read docker info — check 'systemctl status docker')"
echo
echo "Old data at /var/lib/docker is UNTOUCHED. After confirming images/containers work, remove it:"
echo "  sudo rm -rf /var/lib/docker"
