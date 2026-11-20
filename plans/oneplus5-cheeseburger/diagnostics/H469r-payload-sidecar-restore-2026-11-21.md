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
