# H469r payload sidecar restoration (2026-11-21)

## Findings

H469 proved that the unaligned observer repair works, then timed out waiting for
the Data seed provider:

```text
NATIVE_H82_DATA_WAIT: 550 ready=0 bytes=0
NATIVE_H82_DATA: status=60 stage=0 ro=-1 dev=-1 size=0
offline scratch Data mount failed: 60
```

The failure occurs before `stage=1`: NativeRamBlock did not publish the requested
Data UUID. This is distinct from H415's mountpoint-readiness race.

Comparing the payload contents explains the regression:

```text
                         H466  H467  H468  H469
scratch-data.img         yes   no    no    no
kernel.macho.gpuaddon    yes   no    no    no
```

The missing files account for the payload size drop. The H466 source for both
sidecars remains available in its verified payload.

## Candidate

H469r keeps the H469 kernel, trust cache and boot arguments unchanged. The only
packaging change is:

- restore `scratch-data.img`;
- restore `kernel.macho.gpuaddon`;

using the H466 payload copies.

```text
scratch-data.img         fed3a0e6bb39974da339bf7f9155b282dfb0438c454c00f0df7a94b5995c03a4
kernel.macho.gpuaddon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
kernel                   700b50d93379bc804c955c29db0eb77451d1d3353cf1c0a7ad484bfa9a7d849c
payload                  fd340fee7633ec3ac5e694703790b3476fe0d71b7e007a7909c7a4425297512a
boot                     8536911ce79b0f074029d3958dc619a87dcc6c89637cf347e8bca3b51b8f4dc3
```

The payload contains all four expected files:

```text
kernel.macho
kernel.macho.adt
kernel.macho.trustcache
scratch-data.img
kernel.macho.gpuaddon
```

The kernel readback is byte-identical. Boot arguments are 992 bytes and pass the
1020/1024 worst-case check.

## Device gate

The expected change is that `NATIVE_H82_DATA_WAIT` no longer continues to
`ready=0`, and that the scratch Data mount progresses past `stage=0`. A successful
mount should also preserve the H469 result: no unaligned abort and status rows
with `seq==done`.

Do not treat H469r as a display candidate. Its display bytes and arguments are
unchanged from H469.

## Device result

One `fastboot boot` on serial `16149951` returned `Sending OKAY` and
`Booting OKAY`. CDC appeared as COM8
(`USB\VID_1209&PID_0001\OP5CDCH408`). The run lasted about 39 minutes before
the system reset back to Android. H103 identifies:

```text
slot_build         H469
slot_boot          21ad9a9a
last ring uptime   2070.196070 s
live CDC tail      2265.165742 s
Data               state=1 loaded=1 writes=0 errors=0
unaligned abort    none
```

The sidecar restoration fixed the H469 Data-provider blocker. The volume
remained mounted while launchd, SpringBoard, backboardd, lsd,
containermanager, installd, data migration, iconservices, WebKit and many
other userland services executed.

The UFS status rows also improved to a long-window result. Nineteen rows span
125.957374 through 2070.196070 seconds. The last retained rows report:

```text
seq=283944 done=283944 timeout=0 ocs_err=0 dbto=0 recover=0 recovered=0
flight=0 lock_timeout=0 lock_wait_max_ms=25235 lock_waiters=1
```

Short `flight=1` samples return to completion. No OCS timeout, recovery,
read-failure storm or selected-lock timeout appears. This proves the observed
requests finish and that lock timeouts stay zero. It does not prove lock waits
decreased: cumulative `lock_wait_ms` reaches 9,177,351 and later live samples
show `lock_wait_max_ms=27272`.

SpringBoard reaches the real userland LaunchServices boundary:

```text
NATIVE_SBCHAIN: sb=27 n=4
rcv=SpringBoard q=0 sr=1 so=1
req=18951/95/lsd q=0 sr=1 so=1
ld_out=669983 ld_in=671285 ld_reply=0
```

The final `NATIVE_DISPLAY_GATE` remains
`s345=0/0/0 val=0 xf=0 fr=0`. No SpringBoard product frame was submitted.
This remains distinct from any synthetic display-driver transfer.

No retained panic is present. The cause of the reset at the end of the run is
therefore not established. The log does not support calling it watchdog
recovery. Transport decoding remained clean with zero CRC errors, sequence
gaps, boot switches and truncated frames, while the producer reported roughly
100-190 KB of dropped log bytes over the long run.

Evidence:

```text
main-route/display-first-frame/logs/H469r/device/20261121-025236/
H469r-tail32.bin  889e58a31f2e409927afb04d7e9311ebdc78a4cdeddf41bf5dd8118a43bc2214
H469r-h103.txt    c4c1fb7f8a0ec631e43574a880b2bbaa3b95fd90307344f2bbfb23bcbafdc7b0
```

Classification:
`H469r-userland-reached-lsd-scan-incomplete-reset-before-desktop`.

## Next blocker

An offline read-only mount of the 1 GiB seed found that it contains none of:

```text
db/lsd
containers/Shared/SystemGroup/systemgroup.com.apple.lsd.iconscache
containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache
mobile/Library/Caches/com.apple.LaunchServices
mobile/Library/Caches/com.apple.IconsCache
```

At runtime, `iconservicesagent` reports:

```text
Sandbox: no system group container path found for group
"systemgroup.com.apple.lsd.iconscache" ...
```

The same run starts `com.apple.datamigrator` at least eight times between
334.100394 and 2255.631337 seconds. iOS 17 uses
`mobile/Library/Preferences/com.apple.DataMigration.plist`; the existing seed
creator writes the old lowercase `com.apple.migration.plist` name.

The next candidate should keep H469's kernel, boot arguments, display path and
GPU addon unchanged, and change only the Data seed topology described above.
