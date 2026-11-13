# AGENTS.md

## What this tree is

- This is the `lss717/UniXNU` fork for the **OnePlus 5 (cheeseburger, MSM8998)**,
  B line: UEFI + DarwinBoot + 4 KiB XNU.
- The only supported OS profile is **iPad7,1 / iPadOS 17.7.11 / 21H461**. Never
  mix a kernelcache, DeviceTree, OS/SystemOS image, dyld cache, or trust cache
  from another IPSW.
- The board profile, defconfig, ADT generator, boot arguments, and boot-image
  packaging live in the sibling device repository
  `../UniXNU-cheeseburger`, not here. Firmware lives in `../edk2-msm8998`.
- Do not import DinnerABC files, its `patches/p10`, or its records. Do not
  copy the `ios-sweet`/16K A-line or the `sagit-ios-port` layout. They are
  read-only references at most.
- `plans/oneplus5-cheeseburger/STATUS.md` and
  `plans/oneplus5-cheeseburger/diagnostics/H103-preboot-layout-audit-2026-11-01.md`
  are the canonical bring-up record. Read the latest appended section (currently
  §106) before display work; do not infer the current gate from old sections.

## Build and verification

### Building from a brand-new clone (the only sequence that works today)

A fresh checkout has none of the generated state the scripts silently assume. In
November 2026 this cost several failed builds, each failing at a different step:

```sh
./unixnu defconfig cheeseburger_defconfig -D ../UniXNU-cheeseburger
./unixnu fetch   -D ../UniXNU-cheeseburger   # then CONFIRM out/feeds/xnu-0b4b910d exists:
                                             # a "successful" fetch has been seen to skip xnu
./unixnu tree    -D ../UniXNU-cheeseburger
JOBS=1 bash scripts/macos-build-kernel.sh    # records, archives, display archive, link
./unixnu build prelink -D ../UniXNU-cheeseburger
```

Known traps on a fresh tree, in the order they bite:

1. `out/<board>/tree` does not exist until `unixnu tree` runs;
2. `tree/refer/*` is only populated by `tree`, and only after `fetch` filled
   `out/feeds/` — running `tree` first leaves `refer/` empty;
3. `scripts/build-arm-driver.py` reads the compiler recipe from
   `tree/build/xnu/ios-obj/.../IOPlatformExpert.cpo.json`, and the link needs the
   archives (`$CRYPTO_ARCHIVE`, the drivers, `libpthread`), which only the archive
   builders produce. Both come from one XNU pass, so `macos-build-kernel.sh` now runs
   a bootstrap pass (`XNU_BOOTSTRAP=1`) and then the board archive list itself; running
   `build-xnu-4k-baseline.sh` alone on a fresh tree dies at `test -f "$CRYPTO_ARCHIVE"`;
4. `OP5_A540_FIRMWARE` must point at a real A540 firmware cache, or the display archive
   step aborts with "A540 firmware cache not found";
5. `scripts/macos-build-kernel.sh` cloned `.cache/xnu-work` from `tree/refer/xnu`
   **before** creating that symlink, so an empty `refer/` died with
   `fatal: repository '…/refer/xnu' does not exist` even when the feed was present.
   The script now links `out/feeds/*` into `tree/refer/` first and stops with a
   readable message when a feed is missing; `unixnu tree` itself never touches
   `refer/`.
6. A patch that was generated from an already-patched tree applies with fuzz and
   silently duplicates declarations. The series must apply with plain `git apply`
   and no `-F`; check after adding a patch. `patches/xnu/experimental/` holds the
   H251-H254 probe patches until they are rebased onto the current line, with
   `zzzz…-h25x-probe-stubs.patch` keeping the UFS probe's symbols linkable.

The driver is `./unixnu`. Device modules override base modules with the same
name; `./unixnu status` shows the resolved origin of every module.

```sh
# One-time layout: UniXNU, UniXNU-cheeseburger and edk2-msm8998 side by side.
git clone --recurse-submodules https://github.com/lss717/UniXNU
git clone https://github.com/lss717/UniXNU-cheeseburger

./unixnu defconfig cheeseburger_defconfig -D ../UniXNU-cheeseburger
./unixnu fetch -D ../UniXNU-cheeseburger
./unixnu build kernel -D ../UniXNU-cheeseburger    # macOS + Xcode only
./unixnu build payload -D ../UniXNU-cheeseburger
```

- The kernel/prelink/userdata steps need macOS (`xcodebuild`, `hdiutil`,
  `diskutil`, `compression_tool`). Linux can run `status`, `defconfig`,
  `tree`, package-only work, and offline scripts.
- Do **not** run bare `./unixnu build` on this port: its default set includes
  firmware. Do **not** use `unixnu build firmware` or `unixnu bootimg`; both
  assume the UniXNU/Mu-Silicium boot layout. Build firmware with
  `edk2-msm8998/build.sh` and pack the Android boot image with the device
  repository's `scripts/make-bootimg.py`.
- CI `.github/workflows/macos-cheeseburger.yml` builds kernel/payload
  (and optionally userdata); it does not build firmware or the boot image.
- Useful checks:
  - `./unixnu status`
  - `cd ../UniXNU-cheeseburger && python3 scripts/check-cheeseburger.py`
  - `python3 scripts/check-zap-layout.py --firmware ~/.cache/firmware/a540`
    (verifies the A540 ZAP PAS layout: only `.b02` is PT_LOAD, `.b02@0`,
    extent 0x2000, metadata 0x1a1c)
  - `python3 scripts/check-bootargs-fit.py --payload <payload.img>`
    (the boot_args command line must leave room for ` zap-base=0x...`)
  - `python3 scripts/check-unixnu.py` (offline driver self-test; on this Linux
    host with GNU mtools 4.0.43 it currently stops at
    `FAIL: payload volume is reproducible` — confirm on macOS before treating
    that as a source regression)
- Wait for a build by letting the build command itself return. Run it in the
  foreground (an SSH call to the macOS host returns when the build ends), or
  if it must run in the background, read its log once at completion. Do not
  put `sleep`/polling loops or repeated status checks between commands: a
  `sleep` is not a completion signal, and every poll costs more wall time than
  reading the final log.
- Documentation: `cd docs && npm ci && npm run build`; keep `docs/` and
  `docs/zh/` pages and `docs/.vitepress/config.mts` in sync.

## Source and patch workflow

- **Never copy source files between machines with `scp`.** In November 2026 the two
  trees diverged silently (the Mac checkout stopped updating on 2026-10-31 while files
  kept being scp'd over it) and every build after that produced a kernel that stalled in
  UEFI. The only allowed direction is: **edit -> commit -> push -> `git pull` on the
  builder -> build**. If `git log --oneline -1` differs between the two machines, stop
  and fix that first.
- Before every build, check both ends agree: the same commit on the workstation and on
  the builder, and `git status --short` showing no modified driver sources.
- `out/<board>/tree` and `out/<board>/.cache` are generated. Edit the real
  source under `drivers/`, `kits/`, `scripts/`, or the device repository, not
  symlinks in the generated tree.
- Kernel patches live in `patches/xnu/`. Edit the applied source in
  `out/<board>/tree/.cache/xnu-work` after a first kernel build, generate the
  diff, add it to `patches/xnu/`, then rebuild kernel + prelink. Patch names
  encode apply order; late patches use `zzy-`/`zzz-` prefixes. Do not reorder
  or rename unrelated patches.
- Bring-up diagnostics are boot-argument-gated and often live in
  `zzzz...h103...` patches. Do not turn them into default behavior or add more
  boot arguments without reading the current STATUS gate.
- Submodules intentionally point at `lss717` forks under renamed repositories
  (`NativeMobileDisplay` → `GopFramebuffer`, `NativeAES` → `SoftwareAES`,
  `NativePrelink` → `XnuPrelink`, etc.). Do not restore upstream `UniXNU/...`
  URLs. If you change a submodule, commit and push to its `lss717` fork and
  update the superproject pointer.
- Never commit IPSW files, kernelcaches, disk images, trust caches, Data seeds,
  or vendor firmware. They are gitignored and belong in `.cache/` or external
  storage.

## Device and data safety

- Use **`fastboot boot` only**. Do not flash `boot`, `userdata`, GPT, or any
  firmware partition. A temporary TWRP image may be booted, never installed.
- `userdata` is the Android ext4 partition (64 GiB). `userdata_ios` is the
  iOS SHNGROOT partition (49.2 GiB) and is what `drivers/NativeUfs/RootLayout.h`
  reads. Never run `fastboot flash userdata` — it destroys the Android side.
  Writing `userdata_ios` or changing GPT requires explicit user approval and a
  verified backup.
- Keep the Android system bootable. The dual-boot menu is not implemented.

## Current display bring-up

- The Legacy display backend works (GOP test pattern, `start=1`); the blocker
  is that backboardd does not obtain/use a display provider, so no user client
  submits the first frame. H103 §44 lists the excluded hypotheses; do not
  repeat them.
- Keep the verified baseline: `cpus=1`, `IOClass =
  IOMobileFramebufferLegacy` on the service, and no `sheng-vsync`.
  `cpus=2` is nondeterministic before `KextLog`.
- Do not disable `com.apple.iomfb_fdr_loader` (alone or with bics_daemon); it
  produces a `sheng watchdog timeout failed: 222` panic.

## Commits and docs

- Follow `CONTRIBUTING.md`: one subject per commit, prefixes
  `feat(<area>):`, `fix(<area>):`, `docs:`, `build(<area>):`, `chore:`.
- **Commit after every successful build or package.** This is mandatory: once a
  build or packaged image is produced and verified (or designated as the
  candidate), commit all source, build-script, patch and documentation changes
  immediately — in this repository and in every affected sibling/submodule
  repository. Do not leave a successful build's inputs uncommitted. Record the
  boot/kernel/payload hashes in the commit message or the STATUS/diagnostic
  entry. Private images, IPSWs and kernels stay out of git.
- Keep English and Simplified Chinese documentation in sync. The documentation
  describes the resulting state; STATUS records the experiment history.
