# H432 SpringBoard launch-wrapper and launchd cache audit

Date: 2026-11-19

Candidate: H432

Classification:
`launchd-cache-bypasses-overlaid-springboard-job-no-first-frame`

## Conclusion

H432 tested one question: whether launchd consumes an overlaid
`com.apple.SpringBoard.plist` whose `ProgramArguments` point at a signed wrapper.
It does not.

The persistent ring shows:

```text
142.084173 s  NATIVE_EXEC launchd_cache_loader
145.358106 s  NATIVE_EXEC SpringBoard
              argv0=/System/Library/CoreServices/SpringBoard.app/SpringBoard
```

It also contains zero records for:

```text
scenebootstrap exec
H432_SBWRAP
H432_SBSCENE
SpringBoardSceneObserver path
```

The observer therefore still never ran. The earliest active breakpoint is now
the launchd job-cache boundary: the union-mounted SpringBoard job is not the job
definition launchd uses. No conclusion can yet be drawn about FBWorkspace,
scene activation or the SpringBoard layer tree.

## Source and package

H432 preserves the H424 kernel, H430 ADT, H425 Data seed, 995-byte bootargs,
NativeMobileDisplay, IOMFB, IOSurface, IOGPU submission and scanout behavior.
Relative to H430, the payload changes only:

```text
kernel.macho.gpuaddon
kernel.macho.trustcache
```

The addon changes only:

- `com.apple.SpringBoard.plist` now selects
  `/private/var/ngpu/bin/scenebootstrap --launch-springboard`.
- the separate `com.apple.bluetoothd` and
  `com.unixnu.scenebootstrap` jobs from H431 are removed.
- the wrapper writes `H432_SBWRAP`, sets the observer environment in its own
  process and `execv`s the original SpringBoard binary.

```text
core branch / commit    h432-springboard-wrapper / f1de7b9a19b119c5c9737414e696f9773f34c3dc
NativeMetal commit      22deaca80f72c074c2bb9d8b4044da8770cbb1d9
kernel                  c6de727f25604217d668793392aad279af284e34f9477b136294685a76cf585b
payload                 13f0547fefddbec6a1923f3cc7aa525b664c5441804e4d56ffe0d0868a7371ee
boot                    e41b77fda30a4cedc97620d8d32c78f61dda7963f27d56abab16bf75383d886f
ADT                     9e4b51b777cb653ebe9412b964849aa24730f1f8fe2a4217816f9d024f2de655
owner trust             fd14ed73cd7ef8076ea42286de8d6803681e57f4faac10a141e1b2a5eff9c84b
GPU addon               faed608474d04abe9582091810eca97ab2c745569e44d5161459889b9d88f8cb
```

The package verifier reverses the boot and payload, compares the payload to
H430, parses the addon and trust cache, checks the modified plist, confirms the
fixed ADT identity and checks the argument set. It reports only the two expected
FAT changes and `995/1024` base arguments with a `1023` worst case.

## Boot and capture

TWRP again cleared only the final 32 MiB of `userdata_ios`; the readback was
all zero with SHA-256:

```text
83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302
```

One `fastboot boot` on the local serial `16149951` returned `Sending OKAY` and
`Booting OKAY`. The persistent-ring boot id is `5127883077` (`0x131a54945`).

COM8 appeared 288 seconds after the capture helper started. The 480-second
window produced 3,218 frames / 502,608 bytes with zero CRC errors, sequence gaps
or boot switches. Logged uptime is `279.237526-721.736308 s`.

## Event chain

| Uptime | Event | Meaning |
| --- | --- | --- |
| 142.084173 s | `launchd_cache_loader` execs | Launchd selects its cached job definitions. |
| 145.358106 s | Original SpringBoard execs directly | The overlaid wrapper selection is not consumed. |
| 281.761747 s | Display gate: `dpy=3/11/0/0/0` | The normal boot continues into userland. |
| 292.101037 s | `NATIVE_MTL: builder#2 build H432` | The H432 plugin is active in `mediaserverd`. |
| 354.972832 s | Display gate: accelerator reaches `2/0/229/0` | The accelerator path remains reachable. |
| 468.439279 s | Gate reaches `dpy=3/18/0/1/0`; `s345=0/0/0` | No display handoff exists. |
| 478.986046 s | `mediaserverd pid=29 SIGBUS` | The first renderer service exits. |
| 519.558828 s | H432 plugin loads into a new `mediaserverd` | The app/runtime restarts the plugin. |
| 531.074230 s | Second `mediaserverd` SIGBUS | Failure is repeatable. |
| 571.724952 s | H432 plugin loads into a third `mediaserverd` | Another restart occurs. |
| 596.193100 s | Third `mediaserverd` SIGBUS | No draw work reaches submission. |
| 677.025744 s | Last captured display gate | Counters remain `s345=0/0/0`. |

Across the capture:

```text
H432_SBWRAP                          0
H432_SBSCENE                         0
drawPrimitives                       0
dispatchThreads                      0
command-buffer commit                0
presentDrawable/presentSurface       0
nextDrawable                         0
NativeMobileDisplay selector 4/5     0/0
validation / surface transfer        0 / 0
scanout frame                        0
```

The persistent ring adds earlier evidence. It has 159 `NATIVE_MTL` records and
many render-encoder create/end pairs, but every encoder still reports
`draws=0 dispatch=0`. No H432 observer record exists.

This boot saw 44 observed UFS lock timeouts and four traps. They are a later
confounder; the launchd decision that omitted the wrapper occurred at
`145.358106 s`, before the first observed lock timeout.

## Why H432 changes the diagnosis

H431 showed that its separate bootstrap alias did not run. One remaining
explanation was that launchd might still consume SpringBoard's existing job and
apply its modified environment. H432 rules that out: changing the job's
`ProgramArguments` to a wrapper still produces a direct original SpringBoard
exec.

The strongest supported explanation is:

```text
owner addon union mount
  -> launchd_cache_loader
  -> original cached launch-job set
  -> direct SpringBoard executable
```

This is consistent with the fact that `launchd_cache_loader` runs 3.27 seconds
before SpringBoard and with the unchanged original argv0. The logs prove the
cached job-set boundary; they do not identify the on-disk cache file that must
be changed for a future probe.

## Root-cause ranking

1. **High confidence: launchd uses a cached job set and ignores the overlaid
   SpringBoard/alias plist changes.** H432's direct original exec is direct
   evidence.
2. **Unknown: dyld injection.** The wrapper never ran, so H432 does not test
   AMFI, library validation or `DYLD_INSERT_LIBRARIES`.
3. **Unknown: SpringBoard FBWorkspace/FBScene state.** The observer was not
   delivered.
4. **Medium confidence: CA drawable and renderer submission remain active
   gaps.** Render encoders are created but no draw, dispatch, commit or present
   is observed; repeated mediaserverd SIGBUS events make the later window
   unstable.
5. **Low confidence for first-frame root cause: NativeMobileDisplay, IOMFB,
   IOSurface transfer, IOGPU submission or MSM8998 scanout.** They remain
   downstream and no frame reaches selector 4/5.

## Minimal next probe

H433 should stop modifying LaunchDaemon plists. The next probe must cross the
cache-loader boundary before SpringBoard:

1. Locate the exact launchd cache/job-set file used by
   `launchd_cache_loader` and add one read-only sentinel/open trace.
2. Prefer overlaying that cache or its containing directory with an identical
   copy whose SpringBoard job uses the signed wrapper. Preserve every unrelated
   job and verify a byte-level diff.
3. The wrapper must still print `H433_SBWRAP`, set
   `DYLD_INSERT_LIBRARIES=/private/var/ngpu/lib/SpringBoardSceneObserver.dylib`
   and exec the original SpringBoard.
4. Require wrapper, observer-load and first-scene-sample records in that order.
5. Do not change NativeMobileDisplay, IOMFB, IOSurface or scanout in H433.

If the cache file cannot be safely overlaid, the alternative is a pre-cache
wrapper that sets launchd's global environment before the cache loader and then
execs the original cache loader. That path must prove `NATIVE_EXEC` for both
stages and must not replace an essential daemon.

## Recovery

UXC1 request `424434` was sent once and acknowledged at `764.251987 s`. CDC
disappeared, Android reached `boot_completed=1`, and the polling helper made
one `adb reboot recovery` request. It verified TWRP
`3.4.0_9-10-mauronofrio` on serial `16149951`.

## Evidence

```text
main-route/display-first-frame/builds/H432/
main-route/display-first-frame/logs/H432/device/20261119-224837/
E:\Users\ls\Documents\OnePlus5_ios\H432\
plans/oneplus5-cheeseburger/H432-manifest-20261119.json
plans/oneplus5-cheeseburger/diagnostics/H432-device-verification-20261119.json
```
