# H413 IPC correlation result (2026-11-18)

## Scope and classification

H413 is a read-only diagnostic package for the OnePlus 5 (`cheeseburger`) and
iPad7,1 / iPadOS 17.7.11 (21H461) Format 1 route. It adds process/thread state,
bounded queue-head inspection, and a fixed IPC event ring to the existing H411
first-frame sampler. It does not alter scene creation, CoreAnimation, IOGPU,
IOMFB, IOSurface, `NativeLegacyDisplay`, copy, DPU or scanout behavior.

H413 was built, statically verified, booted once with `fastboot boot`, captured
through CDC, exercised through one UXC1 reboot, and returned through Android to
TWRP. It still produced no first frame. These results validate an observation
tool and refine the earliest visible wait; they do not identify or claim a
display fix.

## Source and artifacts

- Base core: `947a88b3cc5a264b5e9ba6b67ad228eb107b281f`
- H413 code commit: `942fc7420591d36750cc6d4d9c6790e140735b95`
- Code tree: `adeaf95d60d4908baaaf24fde344fd1b9164ad1f`
- Code patch SHA-256: `5511e721d960f01236f23cf8b8b1741f129634e9f081c7a43da5389ebbe5cd9`
- Device base: `481fcfe73a1e73ed9c9bb7eef6ceb7ddffe3ce91`
- Boot SHA-256: `e55082d1762d9e38d590fe00cf3386a2969e84af0fa3d4925fa1886b5a6fd04e`
- Kernel SHA-256: `da87cb526067cc15e72f6b5fc9679fff482f889b218e96dfaf066e6643800b05`
- Payload SHA-256: `f44c7ddbd06f57896c85c3f99d759393ecabea094e7ce45ba464bcdd0bdaf0b1`

The immutable submodule pins are recorded in `H413-manifest-20261118.json`.
Format 2 branches, nested private inputs and the 32 MiB device ring are excluded
from the code commit.

## Event chain

The retained boot and probe order is:

```text
UEFI / GOP retained framebuffer
  -> XNU boot
  -> launchd and SpringBoard execute
  -> SpringBoard enters BKSDisplayGetMainScreenInfo
      -> BKSDisplayServicesGetMainScreenInfo
      -> BKSDisplayServicesStart
      -> BKSSystemShellService
  -> SpringBoard sends BKS request 0x5b9173 to launchd
  -> launchd queue contains the request
  -> SpringBoard waits on its reply port
  -> no focused dequeue/direct-delivery or reply observed in the captured window
  -> IOMFB selector 3/4/5, registration, validation, transfer and frame remain zero
```

H403, H403-cp and H407 established the same downstream boundary. Their
SpringBoard processes started at 138.91 s, 142.67 s and 135.97 s; backboardd
started at 179.26 s, 190.61 s and 216.96 s. Various samples showed SpringBoard
waiting in Mach receive while no `NativeLegacyDisplay` client or swap appeared.
H407 still had the same message ID at 279.1 s and 344.0 s before later samples
showed a generic receive at 411.7/479.1 s. None of these boots reached IOMFB
selector 3/4/5 or produced a frame.

H410-display supplied the first same-sample binding: SpringBoard had seven
threads, the sampled request port targeted `lsd`, and the display gate remained
`accel=0/0/0/0 dpy=3/18/0/1/0 s345=0/0/0 val=0 xf=0 fr=0`. H411 moved to
fixed H410 USB main and saw SpringBoard with three threads, a `launchd` queue
count of one, zero launchd replies, and the same zero display counters.

H413 now distinguishes the two ports and correlates queue events:

```text
NATIVE_SBPORT sample=6000
  rcv  0xa03 peer=27/SpringBoard q=0 sr=1 so=1
  req  0x3903 peer=1/launchd q=1 cnt=2 qlim=6 so=0
  local 0xa03 peer=27/SpringBoard cnt=0 qlim=5 seq=28
  both queued heads: 0x5b9173/537989649/32

NATIVE_SBWAIT sample=6000 tid=292
  th_state=0x1 ith_state=0x10004001 ith_kmsg=0 ith_rname=0 ith_seq=0

NATIVE_IPC_FOCUS sample=6000 id=0x5b9173
  remote=0xfffffff81592e2a0 local=0xfffffff8159134c0
  written=6009 lost=4985

NATIVE_IPC_EVT serial=5133 kind=S from=89/SpringBoard to=1/launchd
NATIVE_IPC_EVT serial=5134 kind=Q from=89/SpringBoard to=1/launchd

NATIVE_SBCHAIN sample=6000
  msg=0x5b9173 req=14595/1/launchd q=1 sr=0 so=5
  ld_out=789 ld_in=753 ld_reply=0

NATIVE_DISPLAY_GATE build=H413 boot=2f288db0 sample=6000
  accel=0/0/0/0 dpy=3/11/0/0/0 s345=0/0/0 val=0 xf=0 fr=0
```

The focused request port is the same object in the sampler and sender event,
and the local reply port is the receive name on which SpringBoard is blocked.
The queue still contains the request while `ith_kmsg=0`, so this sample did not
catch a direct delivery into SpringBoard. No `D` or `R` event was printed for
either focused port. The event ring reported 4,985 overwritten global events;
therefore absence of a `D/R` across the whole boot is not provable. The live
snapshot and queue state do prove that the request was still outstanding at
that instant and no first frame existed at the same sample.

## Earliest breakpoint

The earliest same-boot evidence now sits at the launchd/service boundary:

1. SpringBoard is running and blocked on the reply port for
   `BKSDisplayGetMainScreenInfo`.
2. Its request (`0x5b9173`) has been sent and is queued by launchd.
3. The request has not been answered in the captured interval; launchd's reply
   counter is zero.
4. The same sampler sees zero accelerator activity and zero IOMFB selector
   3/4/5, notification registration, validation, transfer and frame counts.

Thus the earliest *observed* actionable breakpoint is before
`NativeLegacyDisplay`, while the request waits in the launchd/service path.
The earliest *causal* breakpoint remains unknown: launchd may be waiting on a
service, that service may be waiting on backboardd, and backboardd may be
blocked on the disabled/unavailable accelerator. Those dependencies can form
a feedback loop.

## Root-cause ranking

1. **User-session/display service check-in does not complete (highest priority,
   observed edge).** The BKS main-screen request is queued and SpringBoard is
   waiting for a reply while display submission remains zero. The exact
   launchd handler/delegate, reply dispatch, and why it does not run remain to
   be established.
2. **Renderer/accelerator availability gates the service chain (highest
   independent technical gate).** `offline-accelerator=0`,
   `h103-load-iogpu=0`, `sheng-gpu-addon=0`, and zero `IOAcceleratorES` matches
   are definite conditions in this image. Existing evidence does not establish
   whether this is the cause of the service wait or a parallel consequence of
   missing scene setup.
3. **IOMFB notification/refresh is never established (downstream).** No
   registration or selector 3/4/5 exists, so this may be a result of no
   drawable rather than a cause.
4. **IOSurface layout/validation is untested (conditional).** `val=0`; the
   validator has not executed. `'b3a8'`, stride, plane and alpha-layout defects
   cannot explain the current absence of a request.
5. **MSM8998 copy/scanout is not the observed breakpoint.** The GOP retained
   image works, but no user frame reaches transfer or scanout. Historical GOP
   scanout success is not evidence that current user-space composition works.

## Minimal probe plan

No additional fix should be layered on until the launchd queue-to-reply edge is
classified. In a future coordinated device slot:

1. Keep all display and accelerator behavior unchanged.
2. Replace the global 1,024-entry event ring with a bounded per-focused-port
   ring, or reserve slots for the request and reply ports, so unrelated IPC
   cannot evict `S/Q/D/R` for the BKS request.
3. Begin recording before the known request and continue for at least 60 s
   after sample 6000, logging dequeue/direct-delivery, receiver task/thread,
   reply send-once transition, and whether the request object is destroyed.
4. Correlate launchd’s handling thread and, if it delegates, the next receiver.
   Only then decide whether to probe backboardd's user-session/accessibility
   handshake or the renderer gate first.
5. Leave `NativeMobileDisplay`, IOMFB selector handling, IOSurface, DPU and
   scanout untouched until a real selector 4/transfer is observed.

## Validation limits

- H413 live CDC replay passed: 204 frames, 26,320 payload bytes, sequence
  `0..203`, and zero CRC, sequence-gap, boot-switch or truncation errors.
- The reboot capture passed: five frames, 2,491 payload bytes, no continuity
  error, and UXC1 request `424413` was ACKed and followed by `MACH Reboot`.
- The 32 MiB H413 ring contains boot/build `2f288db0/H413` but stops at about
  279.409 s. The disk sink paused while healthy USB was active, so this ring
  does not include sample 6000 and cannot extend the live evidence.
- The H411 USB transport loss around 326 s is a separate observed failure.
  H413 kept its CDC control path until the deliberate UXC1 reboot. This does
  not prove a general USB-transport-stage fix.
- The H410 fifth status cell, disk sink pause/resume behavior and H408 CDC
  framing remain preserved by the existing main and static checks.
