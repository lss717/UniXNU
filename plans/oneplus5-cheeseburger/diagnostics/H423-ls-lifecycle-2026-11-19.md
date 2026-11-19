# H423 LaunchServices early-operation timeline

Date: 2026-11-19

H422 showed that the lsd process exposed to the sampler had already reached a
terminating state after only three reads and twelve getxattr calls. The limited
ring retained only the last eight operations, so the earliest sequence could
not be reconstructed.

H423 keeps all H422 counters and behavior and changes only storage semantics:

- retain the first 32 operations instead of the last eight;
- add `sequence`, `pid`, `start_abs` and `end_abs` to each slot;
- never overwrite a retained early slot;
- print the same aggregate gate followed by up to 32 chronological slots.

The hot path remains limited to fixed atomics, fixed copies and timestamps. It
does not print, allocate, sleep, acquire a new lock, resolve a full path or
change an IOReturn.

## Build

Source: `175eee878ec20de44eb17a04e0087bfc3c25e4ad`.

```text
previous kernel       ef78c085e4372f230aacdfd3b140839cfda4785dd711eb057feb2b5d94b0b4df
source kernel pass 1  be43e71dc6210d9a0211bf4c689d068b67479d68d65bccbb35158bf83683a420
prelink pass 1        2c102dd4535f153de72dc0ade67fc8a7bc472dbaf0c999a3522b75231592b3b4
PMGR pass 1           4499f15f4a22c5ba01868d829c86984f64948553c6843dd234f0a85efe1d1b3f
source kernel final   61437346afcd4a9920fef005a3cca354f97a9dd3c99e353aad624e02c6414782
PMGR final            6e795897953fffd0651ca3c248e95abe77f80b05b40d5c60f46aea0b4c06cf63
final kernel          8991916fb58d1dcacaae5d01e46c7019458a90cc5009bee472d97378961bf32f
payload               34fe891446985c798c7a1172478ac85bcec4b1d09a414e02c8d0d548c3dce104
boot                  041d0f1a6581ac0e562ec5d6816c7758cee04cbd6a150230b6abd050f3928467
ADT                   e867a0f058397455578a1af04630fba63e38e7f65ab61192428f001941eb2d2f
```

The 995-byte kernel argument string is identical to H421. `verify_h423.py`
passes boot-to-payload-to-kernel reverse extraction, UEFI/FDT, FAT sidecars,
ADT identity, trust/addon, Data seed and H423 marker checks.

Pre-device classification:
`launchservices-early-operation-timeline-package-statically-verified`.

## First device attempt

One `fastboot boot` of SHA
`041d0f1a6581ac0e562ec5d6816c7758cee04cbd6a150230b6abd050f3928467`
was accepted on `y9000x` serial `16149951`.

The capture helper waited 420 seconds for H410 CDC. No COM port appeared.
After the timeout, ADB, Fastboot and the USB PnP device were all absent. This
means the phone did not reach USB enumeration in this attempt; it is not a
partial or corrupt capture.

The attempt is classified
`device-usb-not-enumerated-before-cdc-timeout`. A physical power-cycle is
required before another attempt. Do not repeat `fastboot boot` until the phone
is back in TWRP and the same unique serial is rechecked.

## Successful retry

After the user power-cycled the phone and confirmed TWRP, one retry was accepted
at `2026-11-19T12:15:55+08:00`. CDC COM3 appeared after 223 seconds. The bounded
480-second capture produced:

```text
frames=14679 payload_bytes=2324301 crc_errors=0 sequence_gaps=0
boot_switches=0 last_sequence=14678
decoded uptime=360.003056-839.989925 s
```

The decoded stream is clean. The first accepted boot produced no CDC and no
partial log, so only the retry is treated as H423 device evidence.

## Earliest operation burst

The first decisive lsd gate was at `369.400451 s`:

```text
NATIVE_LS_GATE: sample=7020 opens=0 reads=8 writes=0 fsyncs=0 xattrs=18
active=0 slow50=3 slow500=1 slow5000=0 max_ms=1082 errors=2 first_ops=26
```

The visible slots show one short burst:

- sequences 1-8: size/value `getxattr` pairs for
  `com.apple.system.Security`;
- sequence 15: 4,096-byte read, residual 1,080;
- sequence 16: 574-byte read;
- sequence 17: `com.apple.FinderInfo`, result 93, residual 32;
- sequences 18-19: `com.apple.decmpfs` size/value lookups;
- sequence 20: 160,631-byte read, 154 ms;
- sequence 21: 160,631-byte read, 1,082 ms;
- sequence 22: another `FinderInfo` ENOATTR;
- sequence 27: another `FinderInfo` ENOATTR;
- sequences 28-31: more `com.apple.decmpfs` metadata;
- sequence 32: 1,276-byte read.

All observed operations ended successfully except the three `FinderInfo`
lookups returning 93. That is `ENOATTR`; the probe requested 32 bytes and
reported residual 32, so these are routine "attribute absent" results rather
than failed content reads. The two 160,631-byte reads are the only 500-ms-plus
latencies.

`start_abs` and `end_abs` are raw `mach_absolute_time()` values. They are
useful for ordering and tick deltas, but must not be labeled nanoseconds. The
patch converts only the per-operation duration. The burst is visibly older
than the first live gate, but the absolute uptime cannot be reconstructed
without the boot's timebase ratio.

## Slot-publication race

This was not a ring overwrite failure. The gate header loads
`gNativeLsdNextOp` before entering the 32-slot print loop. The header therefore
said `first_ops=26` while lsd continued publishing records during the loop.

The live log contains 22 well-formed slot rows:

```text
1-8, 15-22, 27-32
```

Sequences 9-14 and 23-26 were not yet visible when the loop reached those
slots. Sequence 26 appears as a partial line whose prefix was interleaved with
another console record. The header value is a next-operation counter, not a
completed-operation count. A later stable snapshot is required before treating
the set as complete.

## lsd lifecycle correction

`NATIVE_SBPC` at `374.987616 s` found pid 91/lsd with two threads. Tid 524 was
in sleep state `0x9`:

```text
pc=0x1964cf658 lr=0x1966a59b0 wait=0xfffffff007b195e0
```

`NATIVE_SBPC_IMAGE` was not emitted, so this PC cannot yet be assigned to a
dyld image from the live capture alone.

The same boot later records:

```text
426.668997 s  AppleKeyStore open from lsd
486.921795 s  AMFI syscall from pid 91/lsd
488.352350 s  trust query from pid 91/lsd
488.478719 s  trust query from pid 91/lsd
```

One later sampler reported `pid=-1 n=0` for lsd, but the later pid-91 activity
shows that line is not proof of process death. H423 therefore does **not**
reproduce H422's observed lsd termination, and it also does not show a live lsd
filesystem operation at the decisive display gate.

## Same-boot display and BKS state

At sample 6000, immediately before the ls gate:

```text
NATIVE_DISPLAY_GATE: build=H423 boot=85dee953 sample=6000
accel=2/0/194/0 dpy=3/11/0/0/0 s345=0/0/0 val=0 xf=0 fr=0
```

SpringBoard had three threads. Its request port still pointed at launchd
(`q=1 sr=0 so=5`), launchd replies were zero, and the focused BKS request
`0x5b9173` showed only `S/Q` pairs from pids 26 and 89. `emitted=0`,
`responder=0`, and `response=0`. H421 previously closed the BKS reply and still
had no first frame, so this missing reply is the H423 per-boot earliest gate,
not a universal necessary condition across every boot.

Accelerator heartbeats continue to `800.660308 s` and grow from
`2/0/194/0` to `6/0/487/0`; the AGX provider is therefore reachable. Every
heartbeat keeps selectors 3/4/5 and `val/xf/fr` at zero.

## Renderer abort after Metal command-queue creation

`mediaserverd` reached Metal command-queue creation three times and each child
process self-terminated with signal 6 at the same PC:

| pid | newCommandQueue | SIGABRT/exit | corpse quota |
| --- | --- | --- | --- |
| 29 | 384.645509 s | 394.085175 s | allowed 1 of 5 |
| 102 | 448.387406 s | 448.551327 s | allowed 2 of 5 |
| 112 | 541.062280 s | 541.242011 s | allowed 3 of 5 |

The fault address is `0x1d0b72f74`; with the emitted dyld slide
`0x7fc000`, the unslid address is `0x1d0376f74`. All three backtraces contain
the same six return addresses. There was no `Too many corpses` message in the
window, and a fourth `mediaserverd` started at `571.874917 s`.

The CA observer at 483/486 seconds saw:

```text
displays=6 main=0x1 bounds=1080x1920 renderer=3
display-0 context=0 bind=skipped-observer-only
```

This is after the first two renderer failures. It confirms that window-server
metadata and the renderer count exist, while the display-to-context binding and
drawable-bearing scene do not. No `drawPrimitives`, `dispatchThreads`, commit,
`nextDrawable`, `presentSurface`, selector 4/5, IOSurface transfer or scanout
appears.

## UFS and recovery

There is no OCS timeout, retry or recovery in this live capture. A frozen UFS
flight is reported by 178 `NATIVE_UFS_STALL_NOPANIC` lines from `661.737881 s`
to `839.920536 s`; this starts almost 300 seconds after the decisive display
gate and is therefore a downstream/system-wide amplifier.

UXC1 request `424424` was acknowledged at `1059.837926 s`. Android reported
`sys.boot_completed=1`; the polling recovery helper sent exactly one
`adb reboot recovery`, and verified TWRP
`3.4.0_9-10-mauronofrio`, product `cheeseburger`.

## Interpretation and minimum next probe

H423 rules out three tempting shortcuts:

1. the `FinderInfo` result-93 values are routine `ENOATTR`, not a broken content
   read;
2. lsd was not blocked in an unfinished read at the display gate and did not
   terminate in this boot; and
3. IOMFB, IOSurface and scanout never received a frame, so they are downstream
   of the observed scene/renderer failure.

The earliest same-sample break is the SpringBoard launchd/BKS reply path. The
next independent break is repeated `mediaserverd` SIGABRT after command-queue
creation. LaunchServices state remains a plausible upstream dependency because
the first SpringBoard wait happens before a content-bearing scene exists.

The minimum H424 probe should make no display behavior change:

1. Snapshot lsd only after `gNativeLsdNextOp >= 33`, wait for two sampler
   observations with the same counter, and print only slots whose completion
   fields are stable. This removes the H423 publication race without adding a
   hot-path lock.
2. Record BKS `S/Q/delivery/reply/destruction` with the responder pid so the
   `0x5b9173` path can be classified per boot.
3. Print `NATIVE_SBPC_IMAGE` and the dyld base for the sampled lsd thread and
   for the `mediaserverd` abort PC; add the last Metal selector before the
   repeated SIGABRT.
4. Leave NativeMobileDisplay validation/transfer, IOMFB selector handling,
   IOSurface and scanout unchanged until a drawable-bearing scene reaches the
   renderer gate.

## Evidence

```text
main-route/display-first-frame/builds/H423/
main-route/display-first-frame/logs/H423/device/20261119-115809/H423-device-state.txt
main-route/display-first-frame/logs/H423/device/20261119-121627/
main-route/display-first-frame/builds/H423/H423-device-verification-20261119.json
```
