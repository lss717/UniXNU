# H418 AppleKeyStore return-value probe

Date: 2026-11-18

## Competing hypotheses

H417 reached the correct CA ABI observations but did not directly record the
`AppleKeyStore::newUserClient` result.  The entry trace
`NATIVE_IOKIT: op=open ... ok=0` is emitted before the provider is called and
cannot distinguish success from `kIOReturnNotReady`.

Two hypotheses remain:

1. `sheng-aks=1` enables the state client, and the next missing gate is
   SpringBoard/CoreAnimation main-scene completion.
2. The consumer still receives an error from `newUserClient` or a required
   key-state selector, so the main-scene chain remains blocked at AKS.

## Unique variable

H418 keeps the H417 kernel arguments, UEFI, Data seed, accelerator, A540Trace
observer, IOMFB path and device repository unchanged.  It adds observation only
to `NativeKeyStoreEvents.cpp`:

- log the parsed `sheng-aks` value once;
- log the caller, request type and exact `IOReturn` of every bounded
  `newUserClient` attempt, capped at 32 lines;
- aggregate selector calls/errors by selector in fixed storage;
- log the caller, selector and exact result on the first call and on result
  transitions, capped at eight transitions per selector.

No return value, state answer, service registration, selector payload or
display behavior changes.

## Required result

Use one bounded H418 boot to classify the branch before adding another scene
probe:

```text
open rc != 0
  -> identify caller/type/error and fix only that AKS path

open rc == 0, required selector rc != 0
  -> identify caller/selector/error and fix only that selector

open rc == 0, selectors succeed
  -> stop adding AKS probes; trace SpringBoard main-scene completion and
     definesDisplayBounds in the next candidate
```

The existing layer subtree remains supporting evidence only.  It does not by
itself prove that every private scene layer is non-drawable.  A selector 4 must
appear before IOSurface, IOMFB copy or scanout work is allowed.

## Static gates

```text
check-h418-aks-return.py
check-display-first-frame-probe.py
verify_h418.py
```

Build and device status are appended after the bounded run.

## Build and device result

```text
core              4a141e827e86b3320e9700464a28f11c7a5a2fea
AppleKeyStore     2305bad9a525abd467ca3caae046d272fcb27655
NativeMetal       75f3f65cb21a40fa7dfa85f7d092b70fb50cf115
device            481fcfe73a1e73ed9c9bb7eef6ceb7ddffe3ce91
source stub       6d6d255e2184cdb1a9553651bea3a3e4bb2891710a2e7c2a90b22df4380ad5e6
stub prelink      fa38805f5d713789cf7d197c2a439471a0730c2794ede26979290de8e9c693fe
source real       eff75d5baa1c1d4259b41c23634299b1d1a920d62f7e94fc19dd94c0ca43141d
real PMGR         8541b24c3c876e06f286420f84a71f8dc232e2760a08a27e081ebcd2e59a4725
kernel            4b3f4bd4e3c09732635050685e9eab9f74810d00c0db50de9fac4bb853413e07
payload           69cfde5fd3dc5a38fb52f3bd1d5f65372b9a7aa6d07c013f48ecbce1ced084b8
boot              670fd5b95cd391897a7741650d67a3ba3d969bd5674ebdf125548bc39f712a4f
```

The runtime marker was `build=H418 boot=26c3386d`. The unchanged H417 plugin
reported `build H417`. A 360-second CDC capture carried 4,694 frames / 737,949
bytes with zero CRC errors, sequence gaps, boot switches or truncation.

AKS returned success:

```text
382.440967  open comm=SpringBoard type=0 rc=0x0 calls=16 errors=0
382.441184  call comm=SpringBoard sel=35 rc=0x0 calls=1 errors=0
391.759105  call comm=securityd sel=14 rc=0x0 calls=1 errors=0
```

Thirteen AKS open attempts were observable from aggregate call numbers 4
through 16; every captured attempt returned `0x0`, including liveactivitiesd
and SpringBoard. The first three opens happened before CDC attachment.

The BKS main-screen path was also identified from the H418 stack:

```text
mach_msg2_trap
  -> mach_msg
  -> BKSDisplayGetMainScreenInfo
  -> BKSDisplayServicesGetMainScreenInfo
  -> BKSDisplayServicesStart
  -> BKSSystemShellService _activateServerConnectionWithIdleSleepInterval:
  -> BKSSystemShellService initWithConfigurator:
  -> FBSystemShell _initWithOptions:
  -> FBSystemShell _createSingletonWithOptions:
  -> FBSystemShellInitialize
  -> SBSystemAppMain
```

The `0x5b9173` request remained queued at sample 6000 (`277.635 s`) and was gone
by sample 6030 (`376.214 s`), while SpringBoard moved to a generic receive.
This rules out a permanent hold on that specific message. It does not yet prove
where the reply was delivered.

All four display gate samples remained zero:

```text
277.688  sample=6000 accel=1/0/176/0 dpy=3/11/0/0/0 s345=0/0/0 val=0 xf=0 fr=0
376.355  sample=6030 accel=4/1/369/0 dpy=3/18/0/1/0 s345=0/0/0 val=0 xf=0 fr=0
542.877  sample=6060 accel=5/0/495/0 dpy=3/18/0/1/0 s345=0/0/0 val=0 xf=0 fr=0
608.149  sample=6090 accel=5/0/495/0 dpy=3/18/0/1/0 s345=0/0/0 val=0 xf=0 fr=0
```

The typed observer saw one display-bound `CAContext` (`0x59dbd835`) at
`358.538 s`; the server count reached two by `424.468 s`, and the second
context (`0x1535709d`) was visible at `480.022 s`. Both full-screen context
trees remain contentless in the bounded read. The first OCS timeout was at
`474.935 s`, so the sample-6030 display gate and the second-context state are
still healthy evidence; the `480.022 s` tree dump is supporting evidence only.

UXC1 request `424419` was ACKed at `663.100590 s`. The script's 240-second
Android wait expired just before ADB returned at `22:58:14 +08:00`; Android
then reported `sys.boot_completed=1`, and TWRP
`3.4.0_9-10-mauronofrio` was verified at `22:58:52 +08:00`. There was no panic
or undefined instruction.

H418 closes the AKS hypothesis. The next candidate must stop adding AKS
telemetry and trace the SpringBoard main-scene completion and
`definesDisplayBounds` path. It should also preserve a dedicated focused
request/reply record for `0x5b9173`, because the generic ring still loses
unrelated events. Renderer work remains conditional on the scene path; selector
4 remains the gate for IOSurface and scanout work.

Evidence:

```text
display-first-frame/logs/H418/device/20261118-224229/
display-first-frame/builds/H418/
```

Tracked experiment record:

```text
plans/oneplus5-cheeseburger/H418-manifest-20261118.json
plans/oneplus5-cheeseburger/diagnostics/H418-device-verification-20261118.json
```
