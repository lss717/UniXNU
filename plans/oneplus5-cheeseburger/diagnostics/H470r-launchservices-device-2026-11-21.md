# H470r LaunchServices seed device result (2026-11-21)

## Scope

H470r changed only `scratch-data.img`. H469's kernel, boot arguments, UEFI,
trust cache and GPU addon stayed unchanged.

The seed added the LaunchServices/MobileGestalt Data directories and both
capitalized and legacy DataMigration preference names. It also wrote system and
uid-501 launchd disabled plists for
`com.apple.iconservices.iconservicesagent`.

```text
seed encoded SHA-256   7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
seed logical SHA-256   09e540bf07775d94371c8c73ad25e26a144caaf8510437cb7837b57e73b4b578
payload                9791328f6c271871ff74d342921bf70cb1e55af89e7ebe01572b4a89f129478b
boot                   860fa9f6a3284bd15227e1f94347aad4ef05e0ad686da37816097c1ca2a86d25
```

## Device run

One `fastboot boot` ran on unique serial `16149951`. The pre-authorized final
32 MiB ring was cleared and read back all zero before boot. No partition, GPT,
Android `userdata`, or boot partition was written.

CDC appeared as COM8 at approximately 285 seconds of uptime. Data remained
mounted:

```text
NATIVE_DATA_STATUS: requested=1 state=1 loaded=1 writes=0 errors=0
```

The former `systemgroup.com.apple.lsd.iconscache` sandbox error was absent.
lsd executed at 298.671457 seconds and remained alive while its output/input IPC
counts grew to 702,080 / 703,462.

SpringBoard initially waited on lsd. At 2221.470193 seconds the request peer
changed to cfprefsd:

```text
rcv=102151/27/SpringBoard q=0 sr=1 so=1
req=4099/85/cfprefsd q=1 sr=1 so=2
```

This proves the Data seed advanced SpringBoard past the lsd wait. It is not a
first-frame result. Every retained display gate through 2221.567614 seconds
still reported:

```text
s345=0/0/0 val=0 xf=0 fr=0
```

No `NATIVE_MTL` and no SpringBoard product frame appeared.

## Failure sequence

The command path had no OCS timeout, doorbell timeout, retry, recovery, or
`NATIVE_UFS_READFAIL`. A per-window read remained in flight long enough for the
stall observer:

```text
2250.000827 s
NATIVE_UFS_STALL_LOG: req=d21fa/8 cmds=337136 winBytes=5752370176
lastCmd=11eb9ea/262144 ufsFlight=1 waited=196719051
```

The next observable failure was a burst of `NativeUfsWindow` lock timeouts.
The budget was 30 seconds. Forty-six to seventy-two callers were waiting on the
OS/SystemOS volume locks, and the owner changed among live user processes:

```text
2255.462885 s holder=OS owner=sharingd waiters=71
2259.329289 s holder=OS owner=sharingd held_ms=22967 waiters=57
2263.615458 s holder=SystemOS owner=ind held_ms=89 waiters=54
2264.670478 s holder=OS owner=accountsd held_ms=54 waiters=46
```

Each window timeout returned `kIOReturnTimeout` before reaching the UFS command
retry/recovery path. The block layer consequently reported:

```text
IOBlockStorageDriver; executeRequest: request failed to start!
disk6: I/O timeout.
_vnode_dev_read: got err 60
apfs_slurp_file_data: Cannot read ... - Operation timed out(60)
```

The repeated failures affected `disk6s1` and `disk3s1`, SystemOS and OS. At
2266.526421 seconds the kernel stopped:

```text
NATIVE_PANIC_STR: Kernel data abort.
pc=0xfffffff007ab7ab4
lr=0xfffffff00b68971c
x0=0xfffffff0c2dd4000
x1=0xfffffffac6ead000
x2=0x0000000000001fe0
```

The PC maps to `memmove+0x64`. The LR maps into
`com.apple.filesystems.apfs` `__TEXT_EXEC` at offset `0x48971c`. The source
argument `x1=0xfffffffac6ead000` is outside the normal kernel address range.
The sequence therefore passes a corrupted or uninitialized source pointer into
an 8,160-byte `memmove` after repeated APFS read errors.

The panic is not the H468 alignment observer fault, and it is not a watchdog
recovery.

## Classification

```text
H470r-userland-crossed-lsd-wait-then-window-lock-timeout-apfs-data-abort
```

The next single variable is a larger budget only for the per-window lock. The
8-second UFS command timeout, 30-second global command lock, recovery behavior,
request ordering, display path and Data seed remain unchanged.

## Evidence

```text
logs/H470r/device/20261121-034421/
  H470r-live.log
    0b8f9d74f0b67fd83b7f1df0f94b175d4127a42841a63044b0e8363e21145d68
  H470r-h103.txt
    4a055f0d302ace67ffee0949f6f6b02479ed10670261d6d4e05ada981dcadf99
  H470r-tail32.bin
    e94b3577e604dad0a80c54a3842f0d9f0c25b847ab0b7685773194dbd3330592
  H470r-preclear-ring32.bin
    889e58a31f2e409927afb04d7e9311ebdc78a4cdeddf41bf5dd8118a43bc2214
  H470r-clear-readback32.bin
    83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302
```

H103's writer stopped at about 237 seconds, so the extracted ring covers only
the early boot. The live trace is the authoritative record for the 2221–2266
second sequence. The CDC capture process was interrupted after the device had
already reset, so the final frame container was not finalized.
