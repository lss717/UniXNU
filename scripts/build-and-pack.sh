#!/bin/bash
# H270a: the tracked build+pack wrapper for the cheeseburger port.
#
# It exists because of P19 (gpu-display-pitfalls): a failed prelink used to
# leave the previous kernel.macho in place and the packaging step happily put
# it into a boot image, which then looked like "the new kernel does not boot".
# Four rounds (H263-H269) were spent on that.
#
# Rules this wrapper enforces:
#   1. prelink runs here and a non-zero exit aborts the whole wrapper;
#   2. the packaged kernel must be *newer* than the newest built object, and the
#      kernel sha256 is printed and written next to the image;
#   3. --kernel is explicit here (make-bootimg.py keeps its own default, but this
#      wrapper always passes one);
#   4. after packaging, the kernel is read back out of the payload and compared
#      byte for byte with the input.
#
# Usage:
#   scripts/build-and-pack.sh <payload-base.img> <out-boot.img> [--payload-out out.img]
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEVICE=${DEVICE:-$ROOT/../UniXNU-cheeseburger}
EDK2=${EDK2_MSM8998:-$ROOT/../edk2-msm8998}
JOBS=${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || echo 4)}
PAYLOAD_BASE=${1:?usage: build-and-pack.sh <payload-base.img> <out-boot.img>}
OUT_BOOT=${2:?usage: build-and-pack.sh <payload-base.img> <out-boot.img>}
PAYLOAD_OUT=${3:-$ROOT/out/cheeseburger/boot/payload.img}

fail() { echo "build-and-pack: $*" >&2; exit 1; }

echo "== 1/4 kit patches (NativePrelink)"
cd "$ROOT/out/cheeseburger/tree/.cache/xnu-work" || fail "no xnu tree"
for patch in "$ROOT"/kits/NativePrelink/patches/*.patch; do
  if git apply --reverse --check "$patch" >/dev/null 2>&1; then
    echo "   already applied: $(basename "$patch")"
  elif git apply "$patch"; then
    echo "   applied: $(basename "$patch")"
  else
    fail "cannot apply $(basename "$patch")"
  fi
done

echo "== 2/4 kernel (JOBS=$JOBS)"
cd "$ROOT" || fail "no repo"
JOBS="$JOBS" bash scripts/macos-build-kernel.sh || fail "kernel build failed"

echo "== 3/4 prelink"
NEWEST_OBJECT=$(find out/cheeseburger/tree/build/xnu -name 'mach.development.*.unstripped*' -o -name 'mach.development.*' 2>/dev/null | xargs ls -t 2>/dev/null | head -1)
[ -n "$NEWEST_OBJECT" ] || fail "no built object found under tree/build/xnu"
~/.local/bin/python3.12 ./unixnu build prelink -D "$DEVICE" || fail "prelink failed"
KERNEL=out/cheeseburger/kernel/kernel.macho
[ -f "$KERNEL" ] || fail "prelink left no $KERNEL"

if [ "$KERNEL" -ot "$NEWEST_OBJECT" ]; then
  fail "$KERNEL is older than $NEWEST_OBJECT (stale product; P19)"
fi
KSHA=$(shasum -a 256 "$KERNEL" | cut -d' ' -f1)
echo "   kernel sha256 $KSHA"
echo "$KSHA  $KERNEL" > "$KERNEL.sha256"

echo "== 4/4 package"
cp "$PAYLOAD_BASE" "$PAYLOAD_OUT" || fail "cannot copy payload base"
mcopy -o -i "$PAYLOAD_OUT" "$KERNEL" ::/EFI/UniXNU/Payloads/kernel.macho || fail "mcopy kernel"
rm -f /tmp/p19-roundtrip.macho
mcopy -o -i "$PAYLOAD_OUT" ::/EFI/UniXNU/Payloads/kernel.macho /tmp/p19-roundtrip.macho || fail "payload read-back failed"
cmp -s /tmp/p19-roundtrip.macho "$KERNEL" || fail "payload kernel differs from the built kernel (P19)"
echo "   payload round-trip ok"

cd "$DEVICE" || fail "no device repo"
EDK2_MSM8998="$EDK2" python3 scripts/make-bootimg.py \
  --kernel "$EDK2/workspace/uefi-cheeseburger.img.gz-dtb" \
  --payload "$PAYLOAD_OUT" --out "$OUT_BOOT" || fail "make-bootimg failed"

BSHA=$(shasum -a 256 "$OUT_BOOT" | cut -d' ' -f1)
echo "   boot  sha256 $BSHA"
echo "boot=$BSHA kernel=$KSHA payload=$PAYLOAD_OUT" > "$OUT_BOOT.txt"
echo "== done"
