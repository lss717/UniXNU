#!/bin/sh
# Dump the OnePlus 5 partitions that fastboot cannot read.
#
# Run this with the phone booted into TWRP (fastboot boot twrp-*.img; nothing is flashed).
# TWRP's adbd runs as root, so plain dd is enough.  Everything lands in the output directory,
# with sizes and SHA-256 in SHA256SUMS.
#
#   sh plans/oneplus5-cheeseburger/tools/backup-cheeseburger.sh [OUTPUT_DIR]
#
# The default output is .cache/firmware/backups/<timestamp>/ in the UniXNU checkout
# (gitignored).  Keep a copy outside the repository.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
OUT=${1:-"$ROOT/.cache/firmware/backups/$(date +%Y%m%d-%H%M%S)"}

command -v adb >/dev/null 2>&1 || { echo 'adb not found' >&2; exit 1; }

adb wait-for-device
STATE=$(adb shell getprop ro.twrp.version 2>/dev/null | tr -d '\r')
if [ -z "$STATE" ]; then
  echo 'This does not look like TWRP (ro.twrp.version is empty); boot TWRP first.' >&2
  exit 1
fi
echo "TWRP $STATE"

mkdir -p "$OUT"
adb shell 'ls -l /dev/block/by-name' > "$OUT/by-name.txt" 2>&1 || true
adb shell 'cat /proc/partitions' > "$OUT/proc-partitions.txt" 2>&1 || true

# The primary GPT of the whole disk, then every named partition that exists.
adb exec-out 'dd if=/dev/block/sda bs=4096 count=8 2>/dev/null' > "$OUT/gpt-primary.bin" || true
SECTORS=$(adb shell 'blockdev --getsz /dev/block/sda' 2>/dev/null | tr -d '\r' || true)
if [ -n "${SECTORS:-}" ] && [ "$SECTORS" -gt 64 ]; then
  SKIP=$((SECTORS / 8 - 8))
  adb exec-out "dd if=/dev/block/sda bs=4096 skip=$SKIP count=8 2>/dev/null" > "$OUT/gpt-backup.bin" || true
fi

for name in persist modem modemst1 modemst2 fsg fsc devcfg devinfo boot recovery dtbo abl xbl tz keymaster; do
  if adb shell "[ -e /dev/block/by-name/$name ]" 2>/dev/null; then
    echo "dumping $name"
    adb exec-out "dd if=/dev/block/by-name/$name bs=1048576 2>/dev/null" > "$OUT/$name.img"
  else
    echo "skip $name (not present)"
  fi
done

( cd "$OUT" && for file in *.img *.bin; do
    [ -f "$file" ] || continue
    printf '%s  %s\n' "$(sha256sum "$file" | cut -d' ' -f1)" "$file"
  done > SHA256SUMS )

echo
echo "backups in $OUT"
ls -lh "$OUT"
