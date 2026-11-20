# H471 NativeUfsWindow lock budget (2026-11-21)

## Trigger

H470r crossed the LaunchServices wait, then failed after a burst of synthetic
block I/O timeouts:

```text
2250.000827 s
NATIVE_UFS_STALL_LOG: req=d21fa/8 cmds=337136 winBytes=5752370176
lastCmd=11eb9ea/262144 ufsFlight=1 waited=196719051
```

The UFS command layer recorded no OCS timeout, doorbell timeout, retry,
recovery, or read failure. The failures began in `NativeUfsWindow`'s separate
per-volume lock. Its 30-second acquisition budget expired while 46-72 valid
callers were queued behind changing live owners.

The resulting block I/O errors reached APFS. At 2266.526421 seconds the kernel
stopped in `memmove+0x64`, with an invalid source address
`0xfffffffac6ead000`, while the return address was inside
`com.apple.filesystems.apfs` `__TEXT_EXEC`.

## Single behavior change

H471 preserves:

- the 8-second UFS command timeout;
- the 30-second global UFS command lock;
- UFS submission, recovery and request ordering;
- read-ahead and the per-window lock's scope;
- H470r's Data seed;
- display, GPU addon, UEFI and boot arguments.

Only `NativeUfsWindow::doAsyncReadWrite` changes its acquisition budget:

```text
UFS_TIMEOUT_TICKS       153600000   8 s
UFS_DATA_LOCK_TICKS     576000000   30 s
UFS_WINDOW_LOCK_TICKS  2304000000   120 s
```

The purpose is to distinguish a genuinely stuck owner from a busy queue that
needs more than 30 seconds to drain. It does not increase the UFS command
timeout or conceal an OCS/recovery failure.

## Static gate

```text
python3 plans/oneplus5-cheeseburger/diagnostics/H471-window-lock-budget-check.py
H471 window-lock static gate: PASS
H471 marker: H471
UFS command timeout: 8 s
global UFS lock budget: 30 s
NativeUfsWindow lock budget: 120 s
```

The compiled call passes the immediate pair
`mov w2, #0x4000; movk w2, #0x8954, lsl #16`, which is
`0x89544000 = 2,304,000,000` ticks.

## Build

The existing patch worktree had to be reconstructed after the source pull. The
full overlapping series does not apply from a fresh feed using plain `git
apply`; the H467 script requires an already-patched tree. A backup was kept at
`/Users/lss/h468-build/xnu-work-before-h471-complete`.

Two build-chain repairs were needed:

- `zzzzzzzz...h437-late-springboard-union.patch` was re-anchored to the current
  late union function and now applies without fuzz.
- `zzz-native-gpu-addon-counters.patch` restores the two zero-initialized
  observation symbols `native_gpu_addon_calls` and
  `native_gpu_addon_crc_bad` referenced by `NativeUfsProbe`.

The first reconstructed link raced the final source timestamp and used an old
`kern_exec.o`. Rebuilding after the source update passed. The final object now
exports both symbols.

```text
source commit       3dbec14abfa03a648e32d30c23fbfb3cd1dddc23
source kernel       f06bc36cd41661f1d365cc79d8e5afc5ce304a2e68876375e378f03e292274d4
NativeUfsProbe.o    08f1706a457754cf9cb9da4d70d2232b39fcf7fc8d98cde8d542deca5fd535c3
prelink kernel      6a9f064a85d3ba44b7fe3fac48c8a9b77de6f59f78f8642dfdabbceaad1d5a59
```

The final kernel contains the `H471` marker, the H469 status ABI, and the H437
late SpringBoard union strings.

## Device gate

The candidate is accepted only if:

```text
window lock timeout burst absent
block requests complete instead of returning errno 60
APFS data abort absent
Data remains loaded
SpringBoard advances beyond cfprefsd
```

The UFS status still has to show `seq==done`, no OCS/recovery storm, and zero
lock timeouts. A longer successful wait is not a lock-wait decrease. It is
evidence that the previous 30-second budget was truncating valid queued work.

The display gate remains separate. A synthetic transfer is not a SpringBoard
product frame.
