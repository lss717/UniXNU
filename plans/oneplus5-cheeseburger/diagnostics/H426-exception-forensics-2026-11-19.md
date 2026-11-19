# H426 renderer exception forensics and command-queue contract

## Scope

H426 keeps the H424 kernel, ADT, Data seed, kernel command line and display/IOMFB/
IOSurface/scanout behavior unchanged. The only device-path change is the standalone
`A540Trace` plugin and its owner-trust entry.

The probe records four boundaries:

- libobjc's exception preprocessor, before the first Objective-C throw unwinds;
- Foundation's uncaught-exception handler, after the exception escapes;
- `std::terminate`, including the currently registered C++ exception type;
- `SIGABRT`, `SIGSEGV` and `SIGILL`, with 16 bounded frame-pointer entries.

Every Objective-C and C++ hook saves and invokes its predecessor. The signal reporter
restores and re-raises the previous disposition. No handler swallows an exception or
returns success to the renderer.

The plugin also records, at `newCommandQueue`, the selected method encoding, returned
object class, `MTLCommandQueue` protocol conformance and caller return address. Unknown
queue selectors are reported with the synthesized `NSMethodSignature` encoding.

## Source and package

```text
core commit             174e6cf0693e49ed54f8f621124e6675571be1f4
NativeMetal commit      ce6533205e25a64d5da6c4c67731d0e2f30915bf
kernel                  c6de727f25604217d668793392aad279af284e34f9477b136294685a76cf585b
payload                 54e49ee5e34d9dc9e34263e17917ab934c7f671b423534abad37e661a65673b0
boot                    a0c3a8063d2d8054c2b5fc1770aa08eba9642a79ffb9348a851e0a9481196151
A540Trace addon         944df8dc8a54be421f5076538da3364f4289153d67648457c1c6d3f57578cf6e
owner trust             1f4935b7a8590c911f5a2025fade884e7ee508a671eb3fa6fe3e0647100c8e0f
plugin                  9d7e7f161a4bc28dbb16fe5bcc2f16fc04e02dbed7d89984efc196218bfe6b20
plugin CDHash           3c4eabbb315ee4703344bf0d4d92b9fbf4acd825
```

The payload was copied from the verified H425 payload and only
`kernel.macho.gpuaddon` and `kernel.macho.trustcache` were replaced. A file-by-file
FAT comparison found exactly those two changed files. The embedded kernel, ADT, Data
seed, `unixnu.toml`, UEFI blob and 995-byte argument set match H425.

## Preboot ring clearing

Before the boot, TWRP resolved `/dev/block/by-name/userdata_ios` to
`/dev/block/sda14`. Its size was 52,840,607,744 bytes. The final 32 MiB was cleared at
byte offset 52,807,053,312 (`seek=12892347`, `count=8192`, 4096-byte blocks) and read
back as 32 MiB of zeros with SHA-256:

```text
83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302
```

No other partition range was written.

## Device run

One `fastboot boot` was sent. fastboot reported `Sending OKAY` and `Booting OKAY`.
The runtime boot ID was `22617165`; the kernel marker remained H424 and the recovered
ring contains the H426 plugin marker.

COM3 appeared 180 seconds after the always-running capture helper started. It captured
2,773 frames / 437,760 bytes with zero CRC errors, sequence gaps or boot switches, over
uptime `273.380446-753.663825 s`.

The console window started too late for the first plugin burst, so it contains zero
`NATIVE_MTL` lines. The 32 MiB persistent ring was recovered after UXC1 reboot. Its
clean window hash is:

```text
ce3ea0f59362b47d665d454cbaef39f40a1a6ac7e0375dd44ddda6b4b37a07a0
```

The ring supplies 183 `NATIVE_MTL` lines. It begins too late for every pre-247-second
boot event but covers the H426 plugin load and queue creation.

## What H426 proved

At `247.185384 s`, `backboardd` loaded the plugin and printed:

```text
NATIVE_MTL: builder#1 load comm=backboardd observe_seconds=0,30,120,300
NATIVE_MTL: builder#2 build H426
```

The system-side queue requests occurred at `249.004352 s` and `252.063336 s`:

```text
NATIVE_MTL: return#22 newCommandQueue sel=newCommandQueue types=@16@0:8 result=1 class=A540TraceQueue
NATIVE_MTL: return#23 queue_protocol class=A540TraceQueue commandQueueProtocol=0
NATIVE_MTL: dev#24 newCommandQueue process=backboardd
```

The first request happened before the observer's first 30-second delayed display probe,
so it is a system Metal/CoreAnimation call through the registered principal class, not
the delayed scene observer. The caller return address resolved to QuartzCore.

Queued selector tracing also observed:

```text
NATIVE_MTL: queue#46 signature sel=setGPUPriority: args=3 types=v@:@
```

This establishes two concrete facts:

1. `A540TraceQueue` returns a non-nil object from `newCommandQueue`.
2. That object does not conform to `MTLCommandQueue`. Unknown colon selectors are
   assigned a synthetic `void` signature regardless of the real return type.

This is a real diagnostic-stub contract violation. It is not yet proven to be the
exception that caused H425's `std::terminate`; H426 did not capture a throw reason or
caller for that abort.

## Why this boot did not capture the H425 exception

The observed ring and console windows contain zero H426 first-throw, uncaught,
terminate or signal-6 records. That is not a negative result for renderer exceptions.

The first UFS OCS timeout occurred at `280.417479 s`. The boot produced 55 OCS
timeouts, 58 retries, 55 recoveries and 33 kernel traps. At `335.693995 s`, the first
`mediaserverd` process exited with signal 10 (`SIGBUS`) before any H426 plugin load in
that process was recorded. The exit description contains the generic
`exc handler` text, but the kernel trap is SIGBUS and there is no H426 exception hook
evidence.

Thus the H425 common uncaught-exception path was not reached in the observed H426
window. The large UFS filesystem failure masked the target process and makes this boot
inconclusive for exception identity.

## Display gates

Seven display gates from `276.378393 s` through `731.204883 s` stayed at:

```text
accel=1/0/199/0 dpy=2/11/0/0/0 s345=0/0/0 val=0 xf=0 fr=0
```

The last accelerator heartbeat also remained `accel=1/0/199/0` with no draw, dispatch,
commit, present, selector 4/5, IOSurface transfer or frame. The display stack therefore
stopped receiving work before the downstream IOMFB/scanout stages.

## Updated ranking

1. The H425 renderer uncaught exception remains the strongest direct failure. H426 did
   not disprove it; the target process was masked by UFS `SIGBUS` before plugin load.
2. `A540TraceQueue` violating the `MTLCommandQueue` protocol and synthesizing arbitrary
   void method signatures is now a confirmed diagnostic-harness defect. Its causal role
   in H425 signal 6 still requires an exception reason or throw site.
3. UFS OCS storms remain a boot-dependent confounder. They are not required by H425's
   four signal-6 aborts, but they can suppress the renderer path entirely, as in H426.
4. BKS/LaunchServices can delay scene creation, but H424/H425 already show they are not
   sufficient explanations for the missing frame.
5. NativeMobileDisplay/IOMFB, IOSurface, IOGPU submission and MSM8992 scanout remain
   downstream of the absent renderer work.

## Next gate

Repeat the identical H426 binary once after reconnecting the device and clearing the
ring again. The purpose is to obtain a boot without the 55-timeout UFS storm and reach a
`mediaserverd` H426 load. Do not add another handler or swallow an exception.

If the clean boot records an exception name/reason or first-throw stack, fix that exact
ObjC/C++ failure. If it instead reaches the queue and fails without a throw, address the
confirmed `MTLCommandQueue` protocol/type-encoding contract with the smallest
conformance correction. If no `mediaserverd` load occurs even without UFS faults, audit
the Metal plugin discovery path before changing display code.

## Evidence

```text
main-route/display-first-frame/builds/H426/
main-route/display-first-frame/logs/H426/device/20261119-174350/
H426-device-verification-20261119.json
H426-ring-decoded.txt
```
