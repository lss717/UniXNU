#!/bin/bash
# Build the OnePlus 5 (cheeseburger) 4 KiB XNU kernel on the macOS builder.
#
# This is the tracked copy of the host-local ~/run-h103n-build.sh wrapper. It
# carries two lessons that cost H236ck/H236cm a full build each:
#
# 1. XNU_SKIP_PATCH_LOOP=1 only makes sense on an ALREADY PATCHED xnu-work
#    tree. After deleting .cache/xnu-work the baseline script clones the feed
#    and, with the skip flag set, never applies patches/xnu. The unpatched
#    source then fails on unrelated-looking errors (duplicate pmap fields,
#    missing <CodeSignature/Entitlements.h>). Decide the flag from the tree,
#    not from a constant.
#
# 2. Xcode 26.2's iPhoneOS SDK no longer ships
#    usr/local/libexec/availability.pl, so the bootstrap rule that regenerates
#    bsd/sys/_symbol_aliasing.h fails ("Unable to locate ...availability.pl").
#    The header only depends on XNU's own headers and the previous build left
#    a good copy in build/xnu/ios-obj, so keep that copy and make it newer
#    than the generator script after the clone.
#
# 3. The prelinked kernel is extremely sensitive to the Legacy display archive
#    contents (H173/H174, repeated at H236ct): a kernel built against a stale or
#    half-rebuilt libNativeLegacyDisplay.late.a can take an "Undefined kernel
#    instruction" in an unrelated text address before launchd. Rebuild the
#    archive whenever its sources are newer.
#
# Usage: bash macos-build-kernel.sh [--clean]
#   --clean   delete .cache/xnu-work first (full re-bootstrap with patches)

set -e

# The compile is CPU bound; the baseline script falls back to -j4, which halves the
# throughput of this 8-core builder. Nine builds in November used JOBS=1 only while
# the non-booting builds were being isolated, and H269 showed the cause was a missing
# kit patch, not the job count.
export JOBS="${JOBS:-8}"

TREE="$HOME/UniXNU/out/cheeseburger/tree"
WORK="$TREE/.cache/xnu-work"
FEED="$TREE/refer/xnu"
GEN="$TREE/build/xnu/ios-obj/bsd/sys/_symbol_aliasing.h"
PATCH_MARKER="H82_DATA_WAIT"   # added by patches/xnu/offline-owner-systemos-mount.patch

if [ "${1:-}" = "--clean" ]; then
  rm -rf "$WORK"
fi

# `unixnu tree` clears every symlink under tree/refer, and the bootstrap clone below reads
# $FEED, so the fetched checkouts must be linked before anything else touches refer/. On a
# brand-new tree the old placement (just before build-xnu-4k-baseline.sh) made the clone die
# with "fatal: repository '.../tree/refer/xnu' does not exist". Feeds are checked out as
# out/feeds/<module>-<8 hex>, so the link name is the module name.
mkdir -p "$TREE/refer"
for feed in "$HOME/UniXNU/out/feeds"/*/; do
  feed="${feed%/}"
  [ -d "$feed" ] || continue
  name="$(basename "$feed")"
  name="${name%-????????}"
  link="$TREE/refer/$name"
  if [ -e "$link/.git" ] || { [ -d "$link" ] && [ ! -L "$link" ]; }; then
    continue
  fi
  ln -sfn "$feed" "$link"
done
if [ ! -d "$FEED/.git" ]; then
  echo "missing $FEED: run \"unixnu fetch\" and confirm $HOME/UniXNU/out/feeds/xnu-* exists" >&2
  exit 1
fi

# Bootstrap decision: a tree is reusable only when it is a git checkout that
# already carries our patch set. Anything else is rebuilt from the feed.
# The series overlaps (a later patch rewrites a hunk an earlier one added), so an
# applied patch can fail its reverse check while still not applying forward. Reuse
# is only safe when every patch is either applied or applicable; otherwise rebuild.
if [ -d "$WORK/.git" ]; then
  for stale in "$HOME"/UniXNU/patches/xnu/*.patch "$HOME"/UniXNU/kits/NativePrelink/patches/*.patch; do
    git -C "$WORK" apply --reverse --check "$stale" >/dev/null 2>&1 && continue
    if git -C "$WORK" apply --check "$stale" >/dev/null 2>&1; then
      # Applicable but not applied: the archive builders compile from this worktree and
      # only build-xnu-4k-baseline.sh applies patches, so the archives would be built from
      # unpatched sources. A rebuild is the only state that is consistent for both.
      echo "worktree is behind $(basename "$stale"); rebuilding it from the feed"
    else
      echo "worktree cannot take $(basename "$stale"); rebuilding it from the feed"
    fi
    # The compile records live in build/xnu/ios-obj, not in the worktree. Deleting only
    # $WORK leaves them behind, the bootstrap pass is then skipped, and the archive
    # builders compile a freshly cloned, unpatched source tree.
    rm -rf "$WORK" "$TREE/build/xnu/ios-obj"
    break
  done
fi
NEED_PATCH=0
if [ ! -d "$WORK/.git" ]; then
  NEED_PATCH=1
elif ! grep -q "$PATCH_MARKER" "$WORK/bsd/kern/kern_exec.c" 2>/dev/null; then
  NEED_PATCH=1
fi
if [ "$NEED_PATCH" = 1 ]; then
  rm -rf "$WORK"
  # Pre-clone here so the generated-header fallback below runs after the clone
  # (the baseline script clones with the same command when the tree is absent).
  git clone --shared "$FEED" "$WORK"
  export XNU_SKIP_PATCH_LOOP=0
else
  export XNU_SKIP_PATCH_LOOP=1
fi

export PATH=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin:/opt/local/bin:/opt/local/libexec/llvm-20/bin:/opt/local/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer

cd "$TREE"
export XNU_TRUST_CACHE_RUNTIME=0
export XNU_OWNER_CACHE_MOUNT=1
export XNU_OWNER_CACHE_STARTUP=1
export XNU_OWNER_CACHE_CARRIER=1
export XNU_OWNER_CACHE_CARRIER_WRONG_UUID=0
export XNU_NATIVE_CS_HASH_CACHE=1
export XNU_OWNER_UNION_SYSTEMOS=0
export XNU_OWNER_PREBOOT_LAYOUT=1
export XNU_OWNER_PREBOOT_ROOT_UNION=0
export XNU_BRINGUP_CACHE_MOUNT=1
export XNU_OWNER_DATA_MOUNT=1
export XNU_OWNER_BOOT_MANIFEST=0
export XNU_OWNER_DATA_VOLATILE=1
export XNU_OWNER_CRYPTEX_FILES=0
export XNU_NATIVE_UFS=0
export XNU_NATIVE_UFS_PROBE=1
export XNU_OWNER_ROOT_AUDIT=0
export XNU_VERIFIED_ROOT_PROBE=0
export XNU_OWNER_ROOT_TRUST=0
export XNU_NATIVE_VIRTIO_BLOCK=0
export XNU_SOURCE_CORECRYPTO14=1
export XNU_NATIVE_RAM_BLOCK=1
export XNU_NATIVE_MOBILE_DISPLAY=0
export XNU_NATIVE_LEGACY_DISPLAY=1
export XNU_NATIVE_AES=0
export XNU_NATIVE_ADRENO=0
export XNU_ARM_DT_PLATFORM=1
export XNU_ARMCPU=1
export XNU_SOURCE_PTHREAD=1
export XNU_NATIVE_ARCH_TIMER=1
export XNU_DT_PANIC_REGION=1
export XNU_BOOT_PROGRESS=0
export XNU_SOURCE_MOCKFS=1
export XNU_CRYPTO_BOOTSTRAP=source
export XNU_OWNER_DATA_VOLUME_UUID="1A4CE9DF-34B6-4B52-9744-5052A9D20B23"
export XNU_SHENG_PMGR=1

# Keep the display archive in step with its sources. The A540 C3 / Legacy
# display objects are linked into the prelinked kernel; rebuilding only XNU
# after touching drivers/NativeMobileDisplay leaves a stale archive and the
# boot dies with a bogus "Undefined kernel instruction" (H236ct, H173/H174).
#
# A brand-new tree has no compile records yet, and every archive builder below
# (including this one) needs the recipe that only an XNU pass leaves behind.
# `unixnu build kernel` handles that with a bootstrap pass; this script is the
# qualified entry point for the port, so it does the same thing itself. Without
# it a fresh tree dies at "test -f \"$CRYPTO_ARCHIVE\"" in the baseline script.
RECORD="$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/startup.o.json"
if [ ! -f "$RECORD" ]; then
  echo "== bootstrap pass for the compile records (it may stop at the link)"
  XNU_BOOTSTRAP=1 XNU_BOOT_PROGRESS=0 bash scripts/build-xnu-4k-baseline.sh || true
  if [ ! -f "$RECORD" ]; then
    echo "bootstrap pass left no compile records at $RECORD" >&2
    exit 1
  fi
fi

# The bootstrap pass also restores the headers XNU omits (EXTERNAL_HEADERS/TrustCache),
# but it is skipped once the compile records exist, and scripts/ inside the tree is a copy
# made by "unixnu tree" that can predate a fix. Use the repository copy and require the
# result: a missing TrustCache/API.h otherwise surfaces much later, in the mockfs archive.
if [ ! -d "$WORK/EXTERNAL_HEADERS/TrustCache" ]; then
  echo "== restore omitted headers"
  ( cd "$TREE" && python3 "$HOME/UniXNU/scripts/prepare-xnu-source.py" )
  if [ ! -d "$WORK/EXTERNAL_HEADERS/TrustCache" ]; then
    echo "TrustCache headers were not restored; the archive step cannot compile" >&2
    exit 1
  fi
fi

# The storage ABI headers come from the IOStorageFamily reference and the archive
# builders (NativeVirtioBlock) need them; `unixnu build kernel` runs this before its
# archive list, so the wrapper does the same.
if [ -d "$TREE/refer/IOStorageFamily" ] && [ ! -d "$TREE/build/storage-abi/include/IOKit/storage" ]; then
  echo "== storage headers"
  python3 scripts/prepare-storage-headers.py
fi

# The board archive list of ../UniXNU-cheeseburger board.toml [kernel] archives,
# in order. `unixnu build kernel` runs this list; keep the two in step.
for ARCHIVE in \
  "scripts/build-corecrypto-14.py" \
  "scripts/build-corecrypto-14.py --namespace" \
  "scripts/build-arm-driver.py ArmDTPlatform" \
  "scripts/build-arm-driver.py ArmCpu" \
  "scripts/build-arm-driver.py NativeAES" \
  "scripts/build-arm-driver.py NativeVirtioBlock" \
  "scripts/build-arm-driver.py NativeRamBlock" \
  "scripts/build-arm-driver.py NativeUfsProbe" \
  "scripts/build-arm-driver.py NativeKeyStoreEvents" \
  "scripts/build-mockfs-fixture.py" \
  "scripts/build-libpthread-kernel.py"; do
  echo "== archive $ARCHIVE"
  # shellcheck disable=SC2086
  python3 $ARCHIVE
done

# The full sheng PMGR archive reads the AON vtable out of the *previously* prelinked
# kernel (out/<board>/kernel/kernel.macho), so it cannot run on a tree that has never
# been prelinked. The device repository ships a stub for exactly that case; the next
# build, which has a kernel.macho, replaces it with the real bindings.
if [ -f "$HOME/UniXNU/out/cheeseburger/kernel/kernel.macho" ]; then
  echo "== archive scripts/build-sheng-pmgr.py"
  python3 scripts/build-sheng-pmgr.py
else
  echo "== archive scripts/build-sheng-pmgr-stub.py (no prelinked kernel yet)"
  python3 scripts/build-sheng-pmgr-stub.py
fi

# build-native-ufs-runtime.py embeds the signed owner policies (built from the IPSW's
# OS/SystemOS disk images). build-xnu-4k-baseline.sh links its archive only when
# XNU_NATIVE_UFS=1, so a UFS-off build does not need those inputs. Turning UFS on later
# means running scripts/build-owner-os-policy.py and the systemos equivalent first.
if [ "${XNU_NATIVE_UFS:-0}" = 1 ]; then
  echo "== archive scripts/build-native-ufs-runtime.py"
  python3 scripts/build-native-ufs-runtime.py
else
  echo "== archive scripts/build-native-ufs-runtime.py skipped (XNU_NATIVE_UFS=0, the link does not use it)"
fi

DISPLAY_ARCHIVE="$TREE/build/native-legacy-display/libNativeLegacyDisplay.late.a"
if [ ! -f "$DISPLAY_ARCHIVE" ] || \
   [ -n "$(find -L "$HOME/UniXNU/drivers/NativeMobileDisplay" -type f -newer "$DISPLAY_ARCHIVE" -print -quit 2>/dev/null)" ]; then
  echo "rebuilding the legacy display archive (sources newer than $DISPLAY_ARCHIVE)"
  SDKROOT="$(xcrun --sdk iphoneos --show-sdk-path)" python3 scripts/build-op5-legacy-display.py
fi

# The SDK's availability.pl is gone in Xcode 26.2; the fakeroot build in
# build-xnu-4k-baseline.sh only runs when .cache/fakeroot lacks it. When both
# are missing, reuse the previous generated header (same XNU revision).
SDK_PL="$(xcrun --sdk iphoneos --show-sdk-path)/usr/local/libexec/availability.pl"
FAKE_PL="$TREE/.cache/fakeroot/usr/local/libexec/availability.pl"
if [ ! -x "$SDK_PL" ] && [ ! -x "$FAKE_PL" ] && [ -f "$GEN" ]; then
  touch "$GEN"
fi

# The bootstrap pass has applied the series by now, so the final invocation must not
# apply it again: the patches overlap and a second pass fails on a patch that is already
# there. Recompute the flag from the worktree instead of reusing the bootstrap decision.
cd "$TREE"
if grep -q "$PATCH_MARKER" "$WORK/bsd/kern/kern_exec.c" 2>/dev/null; then
  export XNU_SKIP_PATCH_LOOP=1
fi
exec bash scripts/build-xnu-4k-baseline.sh
