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
#
# userdata is intentionally excluded: it is much larger than the important system
# partitions and is not part of the current system package.  cache is rebuildable.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
OUT=${1:-"$ROOT/.cache/firmware/backups/$(date +%Y%m%d-%H%M%S)"}

command -v adb >/dev/null 2>&1 || { echo 'adb not found' >&2; exit 1; }

# TWRP's adbd reports state "recovery", which "adb wait-for-device" never accepts.
if ! adb devices | grep -qE '^[0-9A-Za-z]+[[:space:]]+(device|recovery)$'; then
  echo 'no adb device in device/recovery state; boot TWRP first.' >&2
  exit 1
fi
STATE=$(adb shell getprop ro.twrp.version 2>/dev/null | tr -d '\r')
if [ -z "$STATE" ]; then
  echo 'This does not look like TWRP (ro.twrp.version is empty); boot TWRP first.' >&2
  exit 1
fi
echo "TWRP $STATE"

mkdir -p "$OUT"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/backup-date.txt"
adb shell getprop > "$OUT/getprop.txt" 2>&1 || true
adb shell 'ls -l /dev/block/by-name' > "$OUT/by-name.txt" 2>&1 || true
adb shell 'cat /proc/partitions' > "$OUT/proc-partitions.txt" 2>&1 || true

# Dump the primary and backup GPT of every UFS LUN.  The GPT search/backup
# structures are 4 KiB blocks on this device.
: > "$OUT/lun-sizes.txt"
for lun in sda sdb sdc sdd sde sdf; do
  if ! adb shell "[ -b /dev/block/$lun ]" >/dev/null 2>&1; then
    continue
  fi
  bytes=$(adb shell "blockdev --getsize64 /dev/block/$lun" 2>/dev/null | tr -d '\r')
  case "$bytes" in
    ''|*[!0-9]*) echo "cannot read size of $lun" >&2; exit 1 ;;
  esac
  printf '%s %s\n' "$lun" "$bytes" >> "$OUT/lun-sizes.txt"
  echo "dumping $lun GPT ($bytes bytes)"
  adb exec-out "dd if=/dev/block/$lun bs=4096 count=8 2>/dev/null" > "$OUT/gpt-primary-$lun.bin"
  skip=$((bytes / 4096 - 8))
  adb exec-out "dd if=/dev/block/$lun bs=4096 skip=$skip count=8 2>/dev/null" > "$OUT/gpt-backup-$lun.bin"
  for file in "gpt-primary-$lun.bin" "gpt-backup-$lun.bin"; do
    if [ "$(stat -c %s "$OUT/$file")" -ne 32768 ]; then
      echo "short GPT dump: $file" >&2
      exit 1
    fi
  done
done
# Keep the historical sda names for compatibility with older restore notes.
cp "$OUT/gpt-primary-sda.bin" "$OUT/gpt-primary.bin"
cp "$OUT/gpt-backup-sda.bin" "$OUT/gpt-backup.bin"

# Back up every named partition except userdata and cache.  This includes the
# whole Android boot chain, vendor, system, modem/firmware and persistent data.
: > "$OUT/partition-sizes.txt"
names=$(adb shell 'ls /dev/block/by-name' 2>/dev/null | tr -d '\r')
for name in $names; do
  case "$name" in
    userdata|cache) echo "skip $name (excluded)"; continue ;;
  esac
  path=/dev/block/by-name/$name
  bytes=$(adb shell "blockdev --getsize64 $path" 2>/dev/null | tr -d '\r')
  case "$bytes" in
    ''|*[!0-9]*) echo "cannot read size of $name" >&2; exit 1 ;;
  esac
  printf '%s\t%s\n' "$name" "$bytes" >> "$OUT/partition-sizes.txt"
  echo "dumping $name ($bytes bytes)"
  if ! adb exec-out "dd if=$path bs=1048576 2>/dev/null" > "$OUT/$name.img"; then
    echo "dump failed for $name" >&2
    exit 1
  fi
  actual=$(stat -c %s "$OUT/$name.img")
  if [ "$actual" -ne "$bytes" ]; then
    echo "size mismatch for $name: expected $bytes, got $actual" >&2
    exit 1
  fi
done

( cd "$OUT" && for file in *.img *.bin; do
    [ -f "$file" ] || continue
    printf '%s  %s\n' "$(sha256sum "$file" | cut -d' ' -f1)" "$file"
  done > SHA256SUMS )

echo
echo "backups in $OUT"
ls -lh "$OUT"
du -sh "$OUT"
