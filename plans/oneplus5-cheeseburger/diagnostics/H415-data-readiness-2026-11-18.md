# H415 bounded Data mountpoint readiness

Date: 2026-11-18

## Scope

H415 is a single behavior experiment derived from `main@158e74312c78c0a20d0ab244d122f7d2793fc6ed`
and device `main@481fcfe73a1e73ed9c9bb7eef6ceb7ddffe3ce91`.

It does not include the rejected H414 focused IPC implementation. The H413
read-only display/IPC probes already present on main remain unchanged.

## Observed prerequisite gap

`load_init_program()` calls `native_owner_data_prepare()` before launchd exec.
The existing H82 code waits for `native_ram_block_volume_seed()` and then calls:

```text
mount("apfs", "/private/var", scratch_data_device)
```

H414 run C returned `ENOENT` from that call at `stage=2`. The Data provider was
already readable, but the existing wait covered only provider publication.
Successful H413/A/B rings show root SystemOS mount-complete before their Data
store/mount sequence. H414 provenance is confounded by PMGR stub/real and
cache/no-cache differences, so this sequence is motivation for a controlled
test, not proof that mount ordering alone caused every failure.

## Change

After the RAM Data provider is qualified and before constructing the original
APFS mount request, H415 performs a bounded vnode lookup of the existing root
mountpoint:

```text
/private/var
```

Rules:

- only `ENOENT` is retried;
- every other lookup error is returned immediately;
- provider and mountpoint polling share one 600 x 100 ms budget;
- timeout returns `ETIMEDOUT`;
- each lookup drops its vnode before sleeping;
- no vnode lock is held while sleeping;
- the original APFS mount, post-mount lookup, device/read-only validation,
  GPU-addon preparation and staged-app preparation remain the same;
- no Preboot or SystemOS wait is added. In the current call order, those stages
  depend on the scratch Data mount and waiting for them here would create a
  cycle.

New status records:

```text
NATIVE_H82_DATA_PATH_WAIT: <poll> seed=<n> root=<0/1> err=<errno>
NATIVE_H82_DATA_PATH: status=0 seed=<n> mount=<n> root=<1>
NATIVE_H82_DATA_PATH: status=<errno> seed=<n> mount=<n> root=<0/1> err=<errno>
```

## Build and device gate

H415 completed the required order from clean, matching source revisions:

```text
core                 h415-data-ready@95588b3d
device               h415-data-ready@481fcfe7
core tree            f1250d6bcac52b7a288952c5eedfaa3227d301cf
device source diff   0
out/feeds            independent directory, not a link
device unixnu.lock  0bbf113d5be71b4c7141f67a82ffeee03ce03e578d03802d5fcca5ecfe0da1a9
stub build/prelink   PASS
real PMGR/prelink    PASS
payload + boot       PASS
static verification  PASS
```

The verified artifact chain is:

```text
source kernel  3e1ffa3d2a3db3b43c42576932534834efdf1d20d9db0db9b97241a4c2901dc8
stub prelink   4a6d9ef1498ddfee32a5154e3557f7f336efc85ea73c0201871a5b1d269b120d
real PMGR      58a2f001e93ba192b31d45da20080a5aef5a5d73311ad29aec4ced86f8b2d13c
final kernel   11e3f82e41f83bd310255c25f3aef72b6a8c4fafca120dac1373322edc6c4ac8
payload        e5085448a19401ccaf8d09234c4cfb5f2425e59f07e5c2e8cfbb5c24290bb563
boot           75c8a5043ff2a017d3d9d870c3ff7cf928da531ca336eb401f402a95deb46d39
static report  bc4f893849a3a157254151b550b13693ae71e251d20298988fa7ce80212f39ac
```

The final kernel contains H415 and the Data-path wait strings, excludes all H414
focused-IPC symbols, and is the real-PMGR kernel. The H415 source, display gate,
ADT, kernel-base, H408 CDC/UXC1 and H410 producer/status checks pass.

The H410 checker hard-codes its `DEVICE` and `USB` paths from the historical
`display-first-frame/UniXNU-cheeseburger` sibling. In this multi-worktree setup
that sibling is the older `display-first-frame@c4f84bbc`, so the unmodified
invocation fails even though the H415 device worktree contains the producer.
The recorded PASS explicitly bound `USB` to
`UniXNU-cheeseburger-h415-data-ready@481fcfe7`; no checker or device source was
changed. This is a tooling-path limitation for the next branch and should not
be reported as an H410 regression.

## Device result

The phone moved back to the local workstation. On unique TWRP target
`16149951` (`cheeseburger`, `ONEPLUS A5000`, TWRP 3.4.0_9-10-mauronofrio),
Fastboot reported product `msm8998`, variant `MSM UFS`, unlocked `yes`. The
H415 boot hash was verified and `fastboot boot` was sent exactly once:

```text
boot accepted     2026-11-18T19:09:52+08:00
boot SHA-256      75c8a5043ff2a017d3d9d870c3ff7cf928da531ca336eb401f402a95deb46d39
CDC ready         19:14:09 COM8
capture           360 seconds
transport         9,977 UXL1 frames / 1,258,491 payload bytes
sequence          0..9976
CRC/gap/truncate  0/0/0
boot switches     0
```

The persistent H103 ring retained the early H415 records:

```text
31.041506 NATIVE_BUILD: H415 boot=23861096
33.457015 NATIVE_DATA_STORE: mode=1 open=1 first=1be27f2
          blocks=262153 reason=read-only
33.487381 NATIVE_H82_DATA_PATH: status=0 seed=0 mount=0 root=1
34.257516 NATIVE_H82_DATA: status=0 stage=4 ro=0
          dev=16777240 size=1073741824
```

The mountpoint was resolvable on the first lookup, so `mount=0` and the bounded
retry branch was not exercised. The test proves that H415 reaches Data stage 4
without a startup regression; it did not force the H414-C delayed
mountpoint/`ENOENT` condition.

At sample 6000 the same boot reached SpringBoard and retained:

```text
NATIVE_SBCHAIN: sb=27 n=3 msg=0x5b9173 rcv=SpringBoard
  req=launchd q=1 sr=0 so=3 ld_reply=0

NATIVE_DISPLAY_GATE: build=H415 boot=23861096
  accel=0/0/0/0 dpy=3/11/0/0/0 s345=0/0/0 val=0 xf=0 fr=0
```

The live capture contains 11,041 `NATIVE_SBSEND` records and 194
`backboardd -> IOAcceleratorES` matches, all with `ok=0`; there were zero
`ok=1` matches. IOMFB probes continued to find `NativeLegacyDisplay`. No
panic, `Too many corpses`, or OCS timeout occurred in the 360-second capture.

After capture, UXC1 request `424416` was sent once and ACKed. CDC disappeared,
Android reached `sys.boot_completed=1`, and authorized `adb reboot recovery`
returned the phone to TWRP.

The device classification is
`data-readiness-device-smoke-pass-no-first-frame`. It is not a first-frame
fix, and because the H415 wait count was zero it is not direct proof that the
new retry loop repairs a delayed mountpoint.

## Non-goals

This candidate does not claim a first-frame fix. It does not change IOMFB,
IOSurface, IOGPU, accelerator, NativeMobileDisplay, copy, scanout, launchd
delegate behavior or the H413 focused-event implementation.
