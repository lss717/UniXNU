# H470r LaunchServices Data seed (2026-11-21)

## Triggering evidence

H469r proved that restoring `scratch-data.img` fixes the H469 provider timeout.
The phone then remained in userland for about 39 minutes. Data stayed mounted,
UFS requests completed, and SpringBoard reached its real LaunchServices wait:

```text
NATIVE_SBCHAIN: sb=27 n=4
req=18951/95/lsd q=0 sr=1 so=1
ld_out=669983 ld_in=671285 ld_reply=0
```

The final display gate remained `s345=0/0/0 val=0 xf=0 fr=0`. This is not a
SpringBoard product frame.

Two Data-side defects are directly visible in the same run:

```text
376.097663 s  Sandbox: no system group container path found for group
              "systemgroup.com.apple.lsd.iconscache"

334.100394-2255.631337 s  com.apple.datamigrator starts at least eight times
```

An offline read-only inspection of H469r's 1 GiB packed seed found these paths
absent:

```text
db/lsd
containers/Shared/SystemGroup/systemgroup.com.apple.lsd.iconscache
containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache
mobile/Library/Caches/com.apple.LaunchServices
mobile/Library/Caches/com.apple.IconsCache
```

The merlinx 21H461 bring-up record independently documents both mechanisms.
`lsd` synchronously requests `iconservicesagent` while building its database,
and iOS 17 reads the capitalized
`mobile/Library/Preferences/com.apple.DataMigration.plist`. The existing seed
creator writes only the legacy lowercase `com.apple.migration.plist` name.

Reference:
`Dracen-W/UniXNU-merlinx:bringup-quirks-and-pitfalls.md`, branch
`merlinx-work`.

## Single variable

H470r preserves the H469 kernel, all boot arguments, trust cache, H466 GPU
addon, UEFI and display path. It changes only `scratch-data.img`.

The reproducible transform is
`scripts/seed-data-launchservices-readiness.py`. It:

- creates `db/lsd`;
- creates the lsd icon cache and MobileGestalt system-group containers,
  including their `Library/Caches` directories;
- creates the user LaunchServices and icon cache directories;
- writes both `com.apple.DataMigration.plist` and the legacy
  `com.apple.migration.plist` with the 21H461 completion state;
- writes `db/com.apple.xpc.launchd/disabled.plist` and
  `disabled.501.plist`, preserving existing entries and disabling only
  `com.apple.iconservices.iconservicesagent`.

The original Data volume UUID is unchanged. The encoded seed remains
`DBRDISK1`, expands to 1 GiB, and mounts as the same APFS Data volume.

## Seed result

```text
base encoded SHA-256      fed3a0e6bb39974da339bf7f9155b282dfb0438c454c00f0df7a94b5995c03a4
base logical SHA-256      584ead3c2c469c2b950cffd66753f6f2c5bdf115fa357f2345376407ef8c5bf9
H470r encoded SHA-256     7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
H470r logical SHA-256     09e540bf07775d94371c8c73ad25e26a144caaf8510437cb7837b57e73b4b578
H470r encoded size        4714752 bytes
```

The transform completed the read-write mount, wrote every postcondition,
detached cleanly, verified `NXSB` at the APFS container offset, and repacked
without changing the logical size.

## Payload result

The payload was rebuilt from:

```text
kernel       700b50d93379bc804c955c29db0eb77451d1d3353cf1c0a7ad484bfa9a7d849c
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
```

Payload readback:

```text
kernel       700b50d93379bc804c955c29db0eb77451d1d3353cf1c0a7ad484bfa9a7d849c
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
Data seed    7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
ADT          6e1225183284519ae88fda0cc1492c4c771b6bbc21094b6c13e8fd5d52edac04
payload      9791328f6c271871ff74d342921bf70cb1e55af89e7ebe01572b4a89f129478b
```

The ADT hash differs from H469 because the board ADT is coupled to the packed
Data seed identity. The kernel, launch arguments and other payload sidecars are
unchanged.

The packaged argument string remains 992 bytes. `check-bootargs-fit.py`
reports 1012/1024 after the current `zap-base` and 1020/1024 in the worst-case
16-digit form.

## Device gate

The only behavior question is whether the corrected seed lets `lsd` finish
LaunchServices initialization and reply to SpringBoard:

```text
ld_reply > 0
req queue drains
SpringBoard advances past the synchronous lsd wait
```

The UFS acceptance remains separate:

```text
seq == done
timeout=0 recovery=0 read-failure storm absent
```

Lock waiting and watchdog recovery remain unverified until separately measured
or exercised. A synthetic display transfer does not count as a SpringBoard
product frame.
