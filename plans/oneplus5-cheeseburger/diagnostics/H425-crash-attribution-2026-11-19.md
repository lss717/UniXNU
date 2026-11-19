# H425 renderer exception attribution

Date: 2026-11-19

## Scope

H425 keeps the complete H424 kernel/payload semantics. It changes only the
A540Trace plugin and the two payload files carrying that plugin:

- replace the incorrect dyld image-range scan with a manually declared Darwin
  `dladdr` ABI that the iPhoneOS SDK does not expose;
- bump the plugin's own marker from H420 to H425;
- keep all scene, display, IOMFB, IOSurface, GPU, IPC and filesystem behavior
  unchanged.

The kernel remains byte-identical to H424. This isolates renderer fault naming.

## Package

```text
kernel         c6de727f25604217d668793392aad279af284e34f9477b136294685a76cf585b
payload        3e8e18d1a1d33dd22ee7270a461131809dcfcb46be82cd39ffd6e13fcdf70d37
boot           2323c5256a8a9f14a1d8da7583fb815be995753ecdd4fbaeb196ef5e866e98be
ADT            9e4b51b777cb653ebe9412b964849aa24730f1f8fe2a4217816f9d024f2de655
owner trust    4919a06fd98f9f4c9437d5da2b840206026faa92c79d0f8ed52c5ca1a6a9ba23
GPU addon      1eb5e7fe85cae52228a0a6a332e3d02b2118ac65d6d4a9688a4c19f9510eb7ad
plugin          b424b4a2a92a4b21d5afdecb3a842de83dcb05b3ec85bd005bb2bfc4952f08b1
plugin CDHash   80de3be678dcf3c5ea440d78d9203baa3b882e8d
```

The payload was produced from the statically verified H424 payload by replacing
only `kernel.macho.gpuaddon` and `kernel.macho.trustcache`. The 995-byte bootargs,
Data seed and all other payload files are unchanged.

## Device and capture

The target remained on `y9000x` serial `16149951` in TWRP before the run. One
`fastboot boot` returned `Sending OKAY` and `Booting OKAY`. Runtime boot was
`2428d188`; the kernel marker stayed H424 and the plugin marker was H425, as
expected for this single-variable test.

The 480-second COM3 capture decoded uptime `274.641795-754.575032 s`:

```text
frames=13706 payload_bytes=1871163 crc_errors=0
sequence_gaps=0 boot_switches=0
```

## Renderer attribution

All four `mediaserverd` terminations show the same stack:

```text
libsystem_kernel.__pthread_kill +0x8
  <- libsystem_pthread.pthread_kill +0xd0
  <- libsystem_c.abort +0x68
  <- libc++abi.dylib (redacted) + offsets 0x13714 / 0x4e34
  <- libobjc.A.dylib (redacted) +0x288d8
  <- libc++abi.dylib (redacted) +0x12be4
  <- libc++abi.dylib._ZSt9terminatev +0x34
```

The successful resolution proves the earlier AudioToolbox attribution was a
probe defect. The repeated exits are an uncaught Objective-C/C++ exception
termination path, not a direct GPU/display error.

Events:

| pid | signal time | exit time | corpse |
| --- | --- | --- | --- |
| 29 | 301.107309 s | 303.069725 s | 1 of 5 |
| 100 | 338.183022 s | 338.363709 s | 2 of 5 |
| 108 | 454.439118 s | 454.603324 s | 3 of 5 |
| 130 | 559.083337 s | 559.084337 s | 4 of 5 |

Two abort sites are directly preceded by `newCommandQueue`; the first is
preceded by a texture copy. All four converge on the same terminate stack.

## Other gates

BKS `0x5b9173` remains pending throughout this capture:

```text
responder=0 response=0 response observed=false
```

The only display gate is at `276.496628 s`:

```text
accel=0/0/0/0 dpy=3/10/0/0/0 s345=0/0/0 val=0 xf=0 fr=0
```

Accelerator heartbeats later reach `6/0/608/0`, but no draw, dispatch, commit,
nextDrawable, presentSurface, selector 4/5, IOSurface transfer or frame appears.

No completed 32-slot LaunchServices gate was emitted in this scheduling window,
and no pending line appeared either. The absence must not be interpreted as a
failure of the H424 snapshot; H424 already proved that path.

## Fault isolation

There were no UFS OCS timeouts, retries, recoveries, NATIVE_TRAP records or kernel
panic in this capture. The same renderer termination therefore occurs without
the prior UFS fault cascade. UFS is an amplifier, not a prerequisite for the
renderer abort.

## Conclusion

H425 establishes three facts:

1. The corrected dyld attribution works and identifies the exact libSystem,
   libc++abi and libobjc frames.
2. `mediaserverd` dies through `std::terminate` after an uncaught
   Objective-C/C++ exception during renderer initialization.
3. This happens with the display/IOKit provider path otherwise unchanged and
   without UFS OCS faults.

The next probe should capture the exception name/reason and the first throw site.
It should also retain at least 16 frame-pointer entries and print the last
successful Metal selector. These remain observation-only changes. IOMFB,
IOSurface and scanout must remain untouched until a scene/drawable exists.

## Recovery

UXC1 request `424426` was sent once. The ACK line was not retained, but CDC
disappeared, Android reported `sys.boot_completed=1`, and the polling helper
verified TWRP `3.4.0_9-10-mauronofrio`.

## Evidence

```text
main-route/display-first-frame/builds/H425/
main-route/display-first-frame/logs/H425/device/20261119-154036/
```
