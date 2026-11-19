# H431 SpringBoard scene observer delivery

Date: 2026-11-19

Candidate: H431

Classification:
`springboard-observer-job-not-delivered-ufs-confounded-no-first-frame`

## Conclusion

H431 did not reach the SpringBoard scene observer. The GPU addon was installed and
`A540Trace` loaded into `mediaserverd`, but neither the one-shot `scenebootstrap`
nor the injected `SpringBoardSceneObserver.dylib` produced a single record:

```text
H431_SBBOOT  = 0
H431_SBSCENE = 0
scene#       = 0
```

The persistent ring contains a natural SpringBoard exec at `145.399284 s`, but no
`scenebootstrap` exec and no open of the observer path. The first unsupported claim
would therefore be that SpringBoard has no scene. The tested fact is earlier:
H431's launchd delivery mechanism did not run its observer payload.

This is an H431 harness breakpoint, not evidence that FBSWorkspace, scene
activation, CoreAnimation, IOMFB or scanout is the current first failure.

## Package and provenance

H431 reuses the H424 kernel, H425 Data seed, H430 ADT and the tested 995-byte
boot-argument set. Relative to H430, the payload changes only
`kernel.macho.gpuaddon` and `kernel.macho.trustcache`.

```text
core branch / commit    h431-springboard-scene / 296c3c24466853db2ac02e08993025ed2f7636fe
NativeMetal commit      7e980ba271ea71044be3b022c197339e535e8530
kernel                  c6de727f25604217d668793392aad279af284e34f9477b136294685a76cf585b
payload                 56a1af1922b6f27749f5f05ce3a43bab509c23e1942fd7ebb972b0f6486f0eeb
boot                    853ab7d9bce4ae30d4a96b624f924f50136f34838cee1cbf787862d1b599cea5
GPU addon               e43bf2e8d56d8c01254e73544598128ca8403ae027010dc7e06ad6b5ddbbb027
owner trust             714848af13a574ea90f8fb34bd380b41b050c071d113c737ba89669f3515983f
```

The owner trust cache contains all three H431 CDHashes:

```text
A540Trace             047337564d4fb8f78f186d4392bd5ab8445fbb49
scene observer        3d7e3c0c8e2a192bdeb80b9a84193f960b01fc12
scenebootstrap       26e1f897dacc030a0a0258bfaafc90c7bb8fa7fb
```

The addon contains the expected SpringBoard, Bluetooth-daemon and
`com.unixnu.scenebootstrap` plists, the bootstrap executable, and the bounded
observer dylib. Static packaging checks therefore passed; the missing piece is
runtime delivery.

## Boot procedure

Before boot, only the final 32 MiB ring on `userdata_ios` was cleared:

```text
partition        /dev/block/sda14
partition bytes  52840607744
dd bs=4096 seek=12892347 count=8192
readback SHA256  83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302
```

The readback was all zero. One `fastboot boot` returned `Sending OKAY` and
`Booting OKAY`. No flash, erase, format, GPT change or other partition write was
performed.

The local COM8 capture started 276 seconds before CDC appeared. It then ran for
480 seconds:

```text
frames          13233
payload bytes   2037335
CRC errors      0
sequence gaps   0
boot switches   0
uptime window   281.1010186-761.278433 s
```

The persistent ring boot id is `5371096851`. It covers the early launch window;
the live CDC capture covers the later scene and process window.

## Event chain

| Uptime | Observation | Meaning |
| --- | --- | --- |
| 39.657212 s | `NATIVE_UFS_HB: slotMode=1 logSecs=60` | The tested H424 kernel and persistent log path are active. |
| 145.399284 s | `NATIVE_EXEC ... SpringBoard pid=27` | SpringBoard starts naturally. |
| pre-282 s | No `scenebootstrap` exec or observer open | H431's one-shot launch job was not delivered. |
| 254.913920 s | `NATIVE_MTL: builder#2 build H431` | The image is H431 and `A540Trace` is installed. |
| 284.838100 s | `IOMobileFramebuffer`, `IOMobileFramebufferLegacy`, and `NativeLegacyDisplay` each match one service | The legacy display provider exists. |
| 287.262432 s | `NATIVE_DISPLAY_OPEN ... process=mediaserverd` | The renderer obtains the accelerator service. |
| 299.809060 s | `IOSurfaceRoot` opens successfully | Surface service access is not blocked at open time. |
| 366.758634 s | `disp#295 root observer root=0 rootclass=-` | Display 0 still has no root layer at the first observed walk. |
| 411.052330 s | `disp#364 root observer root=0 rootclass=-` | The root remains absent before later contexts appear. |
| 414.497914 s | Context 0 has a 1080x1920 `CALayer` tree, all `contents=-` | A context and layer shell exist without drawable contents. |
| 414.887330 s | `ctx[0] id=0xd7986487 displayId=0x1 ... rootContents=- renderContext=-` | Context 0 is attached to display 1 but has no render context or contents. |
| 430.197740 s | `ctx[1] id=0x73e39bfe displayId=0x1 ... rootContents=-` | A second empty 1080x1920 context appears. |
| 453.986651 s | Two render encoders are created; both end with `draws=0 dispatch=0` | Metal command recording starts, but no draw work is submitted. |
| 455.423058 s | `mediaserverd pid=29 SIGBUS` | The renderer path is interrupted by a process fault. |
| 500.940935 s | First observed `NATIVE_UFS_LOCK ... timeout` | A system-wide UFS lock storm begins. |
| 500-759 s | 104 observed lock timeouts and 37 traps, including 35 SIGBUS events | The later runtime is heavily confounded by storage/process failures. |
| 668.067010 s | `SpringBoard pid=27 SIGBUS`, then exit | SpringBoard is lost during that storm. |
| 759.656093 s | Last display gate: `accel=3/1/552/0 dpy=3/18/0/1/0 s345=0/0/0 val=0 xf=0 fr=0` | No selector 4/5, validation, transfer or frame exists. |

The counts for actual output work remain zero throughout the capture:

```text
drawPrimitives                       0
dispatchThreads                      0
command-buffer commit                0
presentDrawable/presentSurface       0
nextDrawable                         0
NativeMobileDisplay selector 4/5     0/0
validation / IOSurface transfer      0 / 0
scanout frame                        0
```

The two render encoders do not change that conclusion. They create command
recording objects and then end without any draw, dispatch or commit.

## Earliest breakpoint

The earliest H431-specific breakpoint is launchd job delivery:

```text
packaged custom job
  -> launchd job selection
  -> scenebootstrap exec             <-- not observed
  -> launchctl setenv
  -> SpringBoard restart/re-exec
  -> dyld observer constructor       <-- not observed
  -> FBSWorkspace scene sample       <-- not executed
```

The ordinary SpringBoard process did not inherit the observer. H431 also modified
`com.apple.SpringBoard.plist` with `DYLD_INSERT_LIBRARIES`, but the running
SpringBoard emitted neither the constructor load line nor any scheduled sample.
The separate watchdog-style bootstrap was intended to restart SpringBoard after
setting launchd's global environment, but no bootstrap exec was present.

This can be explained by either:

1. launchd had already cached the original launch-job definitions and did not
   consume the union-mounted SpringBoard/alias changes; or
2. the selected alias job did not run during this boot, and the new
   `com.unixnu.scenebootstrap` label was not inserted into launchd's active job
   set.

The logs distinguish neither branch. They do support the earlier fact that the
bootstrap mechanism, as packaged, was not an automatically executed path.

## Layer-by-layer status

| Layer | H431 evidence | State |
| --- | --- | --- |
| UEFI / kernel / USB | One fastboot boot; complete live capture; no packet errors | Pass |
| Broadcast / launchd delivery | SpringBoard starts naturally; H431 bootstrap has zero exec records | Earliest active breakpoint |
| SpringBoard / FBScene | Observer never runs | Unknown, not negative |
| CAWindowServer | Two 1080x1920 contexts, layer trees present, all root contents absent | Context exists; no drawable contents |
| Metal renderer | H431 plugin loaded in `mediaserverd`; render encoders appear; no draw/commit | Recording begins, submission does not |
| NativeMobileDisplay | Display gate remains selector 3/4/5 `0/0/0` | Downstream and unreached |
| IOMobileFramebuffer | Legacy provider exists and polls match it | Service present; no swap handoff |
| IOSurface | `IOSurfaceRoot` opens; no transfer | Downstream |
| IOGPU / accelerator | `AGXAccelerator` opens in `mediaserverd`; ABI heartbeats advance | Powered/reachable; no submitted frame |
| MSM8998 scanout | No validation, transfer or frame | Downstream |

## Root-cause ranking

1. **High confidence: H431 observer delivery failed before SpringBoard code
   ran.** This is directly established by the absence of bootstrap exec,
   constructor load, and all observer samples alongside a naturally running
   SpringBoard.
2. **High confidence for this boot: UFS/process failures are a later
   confounder, not the H431 delivery cause.** The observer was already absent at
   SpringBoard's `145.399284 s` exec, while the first observed lock timeout is
   `500.940935 s`. The later storm makes process and renderer evidence after
   500 seconds unsuitable for causal conclusions.
3. **Medium confidence: the scene/root-layer gate remains real but is still
   unmeasured at SpringBoard.** H431 cannot decide whether FBSWorkspace has a
   scene, because its observer was never delivered.
4. **Medium confidence: drawable contents are absent in the observed CA
   contexts.** The context and layer shells exist, but root contents are nil and
   there are no draws. This moves the measurement boundary closer to
   CoreAnimation without proving who fails to create the drawable.
5. **Low confidence for the first-frame root cause: IOMFB, IOSurface, IOGPU
   submission, NativeMobileDisplay transfer and scanout.** These services exist
   and accelerator heartbeats advance, but no upstream frame reaches selector
   4/5. They remain downstream of the delivery and scene gates.

## Minimal next probe

H432 should preserve the H424 kernel, H430 ADT, H425 Data seed, boot arguments
and display behavior. It should change only how the observer is launched:

1. Change the SpringBoard launch job's `ProgramArguments` to a signed wrapper
   executable.
2. The wrapper must write its own load marker, set
   `DYLD_INSERT_LIBRARIES=/private/var/ngpu/lib/SpringBoardSceneObserver.dylib`
   in its process environment, and `execv` the original SpringBoard binary.
3. Remove the dependency on a second launchd job and on `launchctl setenv`.
4. Keep the observer read-only and bounded to 5/30/90/180/300/480 seconds.
5. Require three independent markers before interpreting scene data:

```text
H432_SBWRAP             launchd executed the overlaid SpringBoard job
H432_SBSCENE load       dyld loaded the observer into SpringBoard
H432_SBSCENE sample=... FBSWorkspace traversal actually ran
```

If `H432_SBWRAP` is absent, the overlay is not being consumed by launchd and the
next work belongs in the launchd/cache boundary. If the wrapper runs but the
observer does not, the fault is dyld/AMFI/library validation. If the observer
runs, its first sample will finally separate these cases:

```text
workspace missing
scene count zero
scene exists but is not drawable
context exists but root layer/contents are nil
CAMetalLayer exists but nextDrawable/commit/present is zero
```

Only after a drawable-bearing scene and a nonzero draw/commit/present should the
probe move to NativeMobileDisplay validation and transfer, then IOMFB selector
4/5 and MSM8998 scanout. IOMFB and scanout changes in H432 would again test the
wrong layer.

## Recovery

UXC1 request `424433` was sent once at `786.010785 s`. CDC disappeared, Android
reported `boot_completed=1`, and the polling recovery helper sent one
`adb reboot recovery`. It verified:

```text
serial   16149951
product  cheeseburger
state    recovery
TWRP     3.4.0_9-10-mauronofrio
```

## Evidence

```text
main-route/display-first-frame/builds/H431/
main-route/display-first-frame/logs/H431/device/20261119-220447/
E:\Users\ls\Documents\OnePlus5_ios\H431\
plans/oneplus5-cheeseburger/H431-manifest-20261119.json
plans/oneplus5-cheeseburger/diagnostics/H431-device-verification-20261119.json
```
