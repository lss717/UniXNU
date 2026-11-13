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
JOBS=8 bash scripts/macos-build-kernel.sh    # records, archives, display archive, link
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
7. `unixnu build payload` without `--trust-cache` writes a payload with no
   `kernel.macho.trustcache`. DarwinBoot then publishes no `chosen/memory-map:TrustCache`
   property and the kernel panics at `NATIVE_TRUSTCACHE: property lookup failed -1`
   (`kern_trustcache.c:1095`) before any kext loads. Take the 3-module bundle out of a
   known-good payload (`mcopy -i payload.img ::/EFI/UniXNU/Payloads/kernel.macho.trustcache`)
   and pass it as `--trust-cache`.
8. The first build of a fresh tree can only use the sheng PMGR stub, because
   `build-sheng-pmgr.py` reads the AON vtable from an already prelinked `kernel.macho`.
   Build the kernel a second time once `out/<board>/kernel/kernel.macho` exists; the stub
   leaves the boot stalled right after `NATIVE_UFS_HB: enter`.

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
- **Some `drivers/` entries are submodules** (`drivers/NativeMobileDisplay` is
  `lss717/GopFramebuffer`, and the same is true of the other renamed forks). A
  change there is only a dirty worktree until it is committed and pushed in the
  submodule; the superproject commit then records the new pointer, and the
  builder needs `git submodule update --init --remote` before it sees the file.
  H315 lost two builds to this: the driver grew a weak reference to
  `native_legacy_panic_paint` while the archive still came from the old
  submodule commit, so the link failed with an undefined symbol and the
  payload step quietly packed the previous kernel.
- Kernel patches live in `patches/xnu/`. Edit the applied source in
  `out/<board>/tree/.cache/xnu-work` after a first kernel build, generate the
  diff, add it to `patches/xnu/`, then rebuild kernel + prelink. Patch names
  encode apply order; late patches use `zzy-`/`zzz-` prefixes. Do not reorder
  or rename unrelated patches.
- **Edit source with a text editor (`edit`) or `sed`, never with a script that
  rewrites files in bulk.** A Python heredoc doing multi-line replacements is
  what produced two "corrupt patch at line N" failures and one duplicated
  declaration in November 2026: the edits looked right, the diffs did not.
  For a `.patch`, prefer regenerating it from the worktree (`git -C
  .cache/xnu-work diff`, as above) over editing its hunks by hand; when a
  one-line `sed -i` really is the change, re-run
  `git apply --check <patch>` on a clean series before committing.
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

- backboardd **does** obtain the legacy display provider and submits swaps
  (`NATIVE_DISPLAY_OPEN … process=backboardd match=1`, then `selector=4` → `selector=5`).
  The old "no provider / no first frame" gate is closed (H273g, STATUS).
- What it submits is a **two-plane `'b3a8'` wide-colour surface**, not single-plane BGRA:
  `w=1080 h=1920 planes=2 stride=1088(px) alloc=10444800 = plane0 + alpha plane`.
  The validator must accept that format and convert its pixel stride to bytes, otherwise
  every submission returns `kIOReturnNotPermitted` and the desktop never reaches scanout
  (H274/H275, `NativeMobileDisplay 5f520f6`).
- The GPU is powered and reachable (`NATIVE_GPU_PWR`, `AGXAccelerator`, `NATIVE_ACCEL_HB`),
  but `drawPrimitives`/`dispatchThreads`/`commit` stay zero while the render pipelines are
  nil; that is the C6a-MTL line, separate from the display path.
- Boot arguments decide the stage. The `board.toml [payload] kernel_args` defaults are an
  early baseline; the current stage needs the argument set of the last working image
  (`offline-mobile-graphics-load=1`, `offline-legacy-phase=4`, `…-register/validate/transfer/
  retire=1`, `sheng-gpu-addon=1`, `sheng-pmgr=2`, `h103-log-secs=1`). Always copy the
  argument set from a known image of the same stage.
- `sheng-pmgr=2` requires the real PMGR archive. A build with the PMGR stub boots to
  userspace and then panics `AMFI: No PMGR7 @ConfigurationSettings.cpp:235`.
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

## Bring-up tooling: traps that cost a boot each (November 2026)

These are ordered by how much time they wasted, not by how likely they are.

### Verifying a build before it reaches the device

- **The kernel hash must change before you pack an image.** A build that fails
  still leaves the previous `out/<board>/kernel/kernel.macho` in place, and
  `unixnu build payload` happily packs it. Compare `sha256sum` of
  `kernel/kernel.macho` before/after, and treat "unchanged" as failure.
  `unixnu build prelink` is the one guard that already refuses
  (`…noctf not found; run "unixnu build kernel" first`) — never bypass it.
- **Every remote build or package command starts with a pull.** A packaging step
  run on its own (`unixnu build payload`, `make-bootimg.py`, the archive
  scripts) sees whatever the builder's checkout happens to contain, and a
  forgotten pull silently ships the previous kernel or the previous addon. The
  only safe shape is one command that begins with
  `cd ~/UniXNU && git pull -q origin main && git submodule update --init --recursive`
  and then builds, so the pull and the build cannot come from different trees.
  `scripts/macos-build-kernel.sh` itself can still exit **0** when an archive
  compile failed (H310: a missing forward declaration in the driver), so the
  script's status says nothing; only the kernel hash and prelink's refusal do.
- **`grep -c "error: "` is not a compile check.** Kernel logs contain string
  literals such as `"(kcdata_memcpy error: %d…)"`, so 15 "errors" can be noise
  while a real `error: use of undeclared identifier` sits unnoticed. Filter
  `error: (use of|unknown|no member|implicit)`.
- **Editing a `.patch` by hand almost always gets the hunk counts wrong** and
  `git apply` then says `corrupt patch at line N`. Recompute the header from
  the body (`context+added` on the new side, `context+removed` on the old) or
  regenerate the patch from a worktree; do not eyeball it.

### Plugin and addon delivery

- **The addon is installed only after the Data volume mount validates**
  (`native_owner_data_prepare` → `native_gpu_addon_prepare`). When the mount
  fails, no addon is written and the device keeps running the bundle already in
  `/private/var/ngpu`, with no error in the log. H293/H294/H297 all ran a stale
  plugin this way.
- **Print a build id from the plugin itself** (`NATIVE_MTL: builder#N build
  Hxxx`). Without it, "the plugin behaves differently" and "the old plugin is
  still loaded" are indistinguishable. Bump the string in the same commit as
  the behaviour change — H296 forgot and the log still said H295.
- **A new bundle needs its CDHash in the owner trust cache**, or it will not
  load: `scripts/add-owner-trust-hash.py <base> <cdhash> <out>`, then
  `unixnu build payload --trust-cache <out> --gpu-addon <addon>`.
- **`/tmp` on the builder is cleaned without warning.** Losing
  `trust-H272r.bin` / `scratch-data.img` / the addon makes the payload step
  fail or, worse, silently fall back to the previous payload. Keep those inputs
  somewhere durable and re-upload them after a cleanup.

### Reaching the device

- **Never `fastboot flash`.** Only `fastboot boot`. The Data partition is the
  Android side; `userdata_ios` needs explicit approval.
- **PowerShell is the Windows default shell** (`ls@192.168.10.225`). Use
  `/tmp/opencode/ps225 "<script>"` (base64 `-EncodedCommand`); plain quoted
  `cmd` style commands die with `ParserError`. The backup host
  `192.168.8.58` is `cmd.exe` with `rwin8`/`rscp8`.
- `fastboot boot` right after `adb reboot bootloader` often fails with
  `< waiting for any device >` or `Write to device failed (Invalid argument)`:
  wait longer, re-check `fastboot devices`, and retry. It is a timing problem,
  not a bad image.
- **TWRP can come back `offline`** in `adb devices` after a panic-reboot.
  Restarting the adb server does not help; reboot the phone into recovery again.

### Reading the persistent kernel log

- The ring lives at the **end** of `userdata_ios`:
  `dd if=/dev/block/by-name/userdata_ios of=/tmp/x bs=4096 skip=<blocks-8192>
  count=8192`, then `scripts/h103-log-pull.py --slots 256`. Recompute `skip`
  when the partition size changes. TWRP's `dd` does not accept `iflag=direct`.
- **The ring stops early and silently** (observed at 187 s, 196 s, 258 s, 532 s
  and 1115 s across boots). Adding `NATIVE_UFS_LOG_STAT` / `NATIVE_UFS_LOG_FAIL`
  showed no write failures, and `UFS_LOG_STAT rounds=1` showed the flush was
  simply never called again. A sampler-driven `native_log_flush_hook()` every
  second is what finally kept logs alive past 1000 s.
- **Start any probe early.** The SpringBoard sampler originally waited 150 s
  and the Metal plugin loads around 210 s, while the ring often died before
  that: the probes existed but never made it to disk. Sampling now starts at
  60 s.

### Interpreting what the device says

- **`pid` cannot separate our probe from CoreAnimation.** The Metal plugin runs
  inside `backboardd`, so a `presentSurface:` issued by the probe and one issued
  by CA both appear as `client io pid=56`. Silencing the probe took the swap
  validation count from 47 to 0 — every earlier "CA submits frames" reading was
  the probe.
- **Shared-cache addresses need the region base, not a guess.** `pc` lives in
  the dyld cache and slides per boot; subtracting `task_shared_region_slide`
  gave `SymptomEvaluator`, while `pc - sr_base_address` (via
  `vm_shared_region_start_address`) gave the truth: `libsystem_kernel + 0x1b58`.
  Print the base.
- **A probe that never fires looks like a passing test.** `native_sb_alln` was
  zero on the sampler path, so an image-resolver block never ran and printed
  nothing for three boots. Make every probe print its own inputs before it
  decides anything.
- **`stride` units differ per pixel format.** The desktop composites into a
  two-plane `'b3a8'` surface whose stride is in *pixels* (1088) while the bounds
  check wants *bytes*; requiring single-plane BGRA refused 46 of 47 submissions
  with `kIOReturnNotPermitted` and looked exactly like "CA refuses to commit".
