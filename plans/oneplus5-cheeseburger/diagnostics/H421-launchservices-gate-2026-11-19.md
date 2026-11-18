# H421 LaunchServices progress gate

Date: 2026-11-19

H420 closed the BKS request/reply and showed that the next SpringBoard main
thread consumer is `CCSModuleRepository`. Offline symbolication of the same
boot resolves that consumer through `LSApplicationRecord` and
`_LSContextInitCommon` to a synchronous mach message whose peer is `lsd`.
At the same timestamp, `lsd` is scanning system content through
`LSRebuildStatisticsGatherer`, `MILaunchServicesDatabaseGatherer` and
`MIExecutableBundle` code-signing paths.

## Unique observation

H421 keeps every H420 behavior input and adds only a low-frequency read of
fixed storage:

- count `vn_open_modflags` completions made by processes named `lsd`;
- count how many of those opens are currently in flight;
- count completions slower than 50 ms and retain a 64-bit maximum;
- retain the latest eight bounded paths in fixed slots;
- print `NATIVE_LS_GATE` and up to eight `NATIVE_LS_GATE_SLOT` rows only from
  the existing low-frequency kernel sampler when it samples `lsd`.

The probe does not print in the new accounting or completion helpers. It does
not allocate, sleep, take a new lock, change an open result, call LaunchServices,
hook SpringBoard, create a scene/drawable, or call display/GPU code.

## Classification target

```text
opens increasing before first OCS
  -> LaunchServices scan is progressing; the main-thread wait is unfinished work

opens and active slots frozen before first OCS
  -> identify the held path/slot and inspect the corresponding vnode or service

lsd exits or is killed before the gate samples
  -> bind the exit/trap time and preserve UFS/corpse evidence as a separate fault
```

The result must be interpreted with the first OCS timeout, not after the later
corpse storm. No behavior change is authorized by this candidate.

## Static gates

```text
check-h421-launchservices-gate.py
H421 XNU patch applies with plain git apply --check
drivers/NativeMetal/tools/check-h420-main-scene.py
```

The patch must remain ordered after the H395 open measurement and the H420 BKS
repair. Build, device, and recovery status are appended only after a bounded
run.

## Static build result

The final source tree was pulled on `mac` at
`37ae68ee11eef749051f3de05ad4ff78e7d06255`. Two PMGR passes completed:

```text
source kernel stub  a9a42afdf6c8dd41588bb4399a80aeab6676393f7da5d917fe3358e32559d4ee
stub prelink        b4a4bf8d79b08c6075e9f1eb25a83b1fc3782a39c5233c754d39672def06efd4
stub PMGR           b8dbb622bdefebc094cb645cf5a5304cf6f5c8395108c5dbfd98feb3f3b4b2ad
source kernel real  4c46d873c74386fd84cab1b36c4b262409d34f239f55c1d431b7b0c725c19f8d
real PMGR           b8f4b8bf3bed783278696c0bc06c48ac27881f8cb03f923b0f1ec0635ea1a82c
final kernel        06415c05fc3c2b839232c07a5b6eb4638b88ea6b4a40d7b522e28a0749727d74
payload             337858312cd53e815e1c3187cc3e57e45f0e39897373abdc6ab2587b1db4df34
boot                2282441f210430cd9e3fa77de2be24b91b425d5bdd53b71209e129bcf45e9947
ADT                 b8eb10f81c8e1c80cd37cacc4715b8291f89639c802a7c4024f4a0dd4be5b8d1
```

The payload retains H420's Data seed, A540 addon, owner trust and 995-byte
command line. `verify_h421.py` passed boot-to-payload-to-kernel reverse
extraction, UEFI gzip/FDT, FAT sidecars, ADT, addon/trust, and the
`1023/1024` worst-case bootargs check. The final kernel contains
`NATIVE_LS_GATE:` and `NATIVE_LS_GATE_SLOT:`.

Build-time classification:
`launchservices-progress-gate-package-statically-verified`.

## Device result

The one bounded local `fastboot boot` used unique TWRP serial `16149951`.
The runtime marker was:

```text
NATIVE_DISPLAY_GATE: build=H421 boot=37270052 sample=6000
```

CDC opened as COM8 after 289.8 seconds and then carried a 480-second live
window. The capture contained 4,203 frames and 588,716 payload bytes with zero
CRC errors, sequence gaps, boot switches or truncation. Decoded uptime spans
291.677341 through 771.819909 seconds.

The BKS main-screen reply was already complete in this boot. The response
`0x5b91d7` was delivered directly to SpringBoard thread 293 at
`time_ns=377795729895`. At the next sampled step, sample 6030 no longer showed
the BKS launchd request. It was not replaced by a healthy main-scene path:
samples 6060, 6090, 6120 and 6150 all showed SpringBoard's main thread waiting
on pid 91/lsd with `reply=0`.

All six open-gate samples were zero:

```text
292.805059  sample=7020  opens=0 active=0 slow=0 max_ms=0
445.048404  sample=7050  opens=0 active=0 slow=0 max_ms=0
527.941850  sample=7080  opens=0 active=0 slow=0 max_ms=0
605.713525  sample=7110  opens=0 active=0 slow=0 max_ms=0
676.662458  sample=7140  opens=0 active=0 slow=0 max_ms=0
748.006484  sample=7170  opens=0 active=0 slow=0 max_ms=0
```

`NATIVE_LS_GATE_SLOT` was absent. This is not a missing gate record: it means
the sampled `lsd` threads had not entered the instrumented
`vn_open_modflags` path. They were earlier in LaunchServices installation and
database setup.

## Offline symbolication

`NATIVE_SBPC_IMAGE` reported the same-boot dyld slide `0x1e758000`. Offline
symbolication against the 21H461 SystemOS cache and matching Mach-O images
resolved the following paths.

The journal-recovery thread, sampled as tid 522 from samplers 7050 through
7170, remained in:

```text
libsystem_kernel _kevent_id+0x8
  <- libdispatch __dispatch_event_loop_wait_for_ownership$VARIANT$mp
  <- libdispatch __DISPATCH_WAIT_FOR_QUEUE__
  <- libdispatch __dispatch_sync_f_slow
  <- CoreServices -[_LSInstallProgressService performJournalRecovery]
  <- CoreServices ___43+[_LSInstallProgressService beginListening]_block_invoke
  <- CoreServices __LSServerMain
```

The inactive-install thread, tid 913, remained in:

```text
libsystem_kernel __ulock_wait+0x8
  <- libdispatch __dispatch_group_wait_slow
  <- CoreServices -[_LSInstallProgressService restoreInactiveInstalls]
  <- libdispatch __dispatch_call_block_and_release
  <- libdispatch __dispatch_client_callout
```

Other alive `lsd` workers were not frozen in the same edge. They were
enumerating built-in system content and performing container lookups through:

```text
libsystem_containermanager container_get_class
  <- MIMCMContainer _doInitWithContainer:error:
  <- MIContainer containerWithIdentifier:forPersona:ofContentClass:...
  <- MIDataContainer dataContainerForExecutableBundle:...
  <- MILaunchServicesDatabaseGatherer scanExecutableBundle:...
  <- MIFileManager enumerateURLsForItemsInDirectoryAtURL:...
  <- MIFilesystemScanner _scanAppsDirectory:withError:
  <- MILaunchServicesDatabaseGatherer performGatherWithError:
  <- ICLWorkspace enumerateBuiltInSystemContentWithBlock:error:
```

The correct reading is therefore "LaunchServices recovery is still in
progress" rather than "the open probe failed" or "lsd is fully stalled".
The current open-only counter starts too late for the first blocking edge:
the process is already waiting in installation-progress recovery when it first
gets sampled.

## Downstream state

The two display-bound contexts were first observed at 426.223058 and
426.536658 seconds:

```text
0x54c4bf7c  display=0x1 mask=0xffffffff nodes=4 contents=0
0x4e0f5b30  display=0x1 mask=0xffffffff nodes=4 contents=0
```

All six `NATIVE_DISPLAY_GATE` samples remained
`s345=0/0/0 val=0 xf=0 fr=0`. There were no `drawPrimitives`,
`dispatchThreads`, command-buffer commit, `nextDrawable`, real
`presentSurface`, legacy validation/transfer or frame records.

The window also recorded no UFS OCS timeout, no `NATIVE_TRAP:` and no kernel
panic or undefined instruction. A single late mediaserverd
`Too many corpses being created` event occurred at 667.564499 seconds, after
the LaunchServices wait and empty-context observations. UFS OCS therefore
cannot be a necessary condition for this failure.

## Ranked conclusion

1. **LaunchServices database/installation recovery is not ready when
   SpringBoard needs it.** Confidence is high. The same boot shows
   `performJournalRecovery`, `restoreInactiveInstalls`, and active
   InstalledContentLibrary enumeration, while SpringBoard waits on lsd.
2. **ControlCenterServices performs the LaunchServices lookup synchronously on
   SpringBoard's main queue.** Confidence is high. This explains why an
   unfinished LaunchServices setup stops main-scene completion rather than only
   delaying a background feature.
3. **Missing or cold LaunchServices/container state is the most likely reason
   the recovery takes this long.** Confidence is medium. The current trace
   proves active setup, not the specific missing record or journal entry.
4. **`cpus=1` and general filesystem latency are amplifiers.** Confidence is
   medium-low. There was no observed UFS OCS failure in this run, but the
   single-CPU baseline may serialize otherwise concurrent recovery work.
5. **Empty main-scene contents and zero renderer submissions are downstream.**
   Confidence is high. Both CA contexts exist and are display-bound; neither
   ever receives a drawable-bearing content update.
6. **IOMFB selector 4/5, IOSurface validation/copy and MSM8998 scanout are not
   reached.** Confidence is high. No submitted surface exists to exercise them.
7. **BKS reply, AKS, display publication and accelerator-provider presence are
   excluded as current first cause.** Each has a successful same-boot marker.

## Next minimum probe

Do not change renderer, IOMFB, IOSurface or scanout. Extend the existing
sampler-gated `lsd` instrumentation to count `vn_read`, `vn_write`, `vn_fsync`
and `getxattr` alongside open, with bounded in-flight/slow/path/result/thread
slots. Keep all printing in the low-frequency sampler and keep the filesystem
hot path free of allocation, sleep and a new lock.

That probe should answer three questions in one boot:

1. Is journal recovery blocked on a concrete filesystem operation, or waiting
   for a group that other `lsd` workers are advancing?
2. Which path or attribute operation is first and repeatedly slow?
3. Does the system-content worker eventually complete, or does it preserve the
   same group dependency until SpringBoard is blocked indefinitely?

Only after that result should a behavior variable such as offline database
seeding, a controlled empty LaunchServices store, or changing the
ControlCenterServices init ordering be considered.

## Recovery

UXC1 request `424422` was sent once and acknowledged at uptime
`793.640943` seconds. Android reported `sys.boot_completed=1`; one authorized
`adb reboot recovery` followed. The final read-only check at
`2026-11-19T02:28:12.5195225+08:00` found:

```text
16149951 recovery product:omni_cheeseburger model:ONEPLUS_A5000
ro.product.device=cheeseburger
ro.product.name=omni_cheeseburger
ro.twrp.version=3.4.0_9-10-mauronofrio
uptime=766.95
```

The H421 run exposed one recovery-helper race: the first TWRP `getprop`
immediately after the ADB state changed returned `device not found`, while the
same recovery target was ready moments later. The helper is therefore retained
in this branch as `scripts/reboot-uxc1-poll-recovery.ps1` and now:

- polls for Android and requires `sys.boot_completed=1` before one
  `adb reboot recovery`;
- polls for the recovery state rather than accepting a single transition;
- retries `ro.product.device` and `ro.twrp.version` for a bounded 20 seconds
  before declaring failure;
- records the number of property attempts in the recovery state file.

No flash, erase, format, dd, GPT or partition write was performed.
