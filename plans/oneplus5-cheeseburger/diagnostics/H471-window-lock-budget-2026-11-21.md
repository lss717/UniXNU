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

Payload:

```text
kernel       6a9f064a85d3ba44b7fe3fac48c8a9b77de6f59f78f8642dfdabbceaad1d5a59
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
Data seed    7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
ADT          bcd878eac10ea377b77df96fc10a2eece6bb8732ec8beadd7dba829886b7a59f
unixnu.toml  c64e6ffb9c09df96eafbb2689851cefbfceeb718d3069379063d8d61004c072d
payload      924d162ff2dd33583e2dd13e31969f87ba6b5ce7c65dbd8c782736d310bddb82
```

The payload kernel round-trip is byte-identical. The argument string is still
992 bytes, with worst-case `zap-base` usage 1020/1024.

Boot:

```text
UEFI    9e6608c42e7fc7fc66d399e6f9193a00648bab8aff10d446d3fcc0fc486b17a6
payload 924d162ff2dd33583e2dd13e31969f87ba6b5ce7c65dbd8c782736d310bddb82
boot    827b699f964f88dde03bd29977f2920051a8b2a75b3ddaf301981110ba097d5a
```

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

## Device result

One local `fastboot boot` on serial `16149951` returned
`Sending OKAY` and `Booting OKAY`; the runtime boot ID was `212bb495`.
Ring preclear and readback both succeeded before boot. CDC appeared about
285 seconds after the boot command.

The H470r failure window was crossed without the previous terminal cascade:

```text
2277.995474 s
seq=348374 done=348374 timeout=0 ocs_err=0 dbto=0
recover=0 recovered=0 flight=0
lock_ok=923543 lock_timeout=0
lock_wait_ms=15895409 lock_wait_max_ms=38114 lock_waiters=7
```

The one `NATIVE_UFS_STALL_LOG` was at 1942.850879 seconds:

```text
req=99030/8 cmds=276953 winBytes=5322675200
lastCmd=11f2f72/262144 ufsFlight=1 waited=206086825
```

It was a bounded 8-block window stall, not one of H470r's 38
`NativeUfsWindow` timeout records. The block path returned no `errno 60`,
there was no `apfs_slurp_file_data` failure, and no data abort appeared.

The result proves that a valid request can wait longer than 30 seconds and
still finish. Maximum window-lock wait grew from 16.742 seconds to 27.063
seconds at 2186.958650 seconds, then 38.114 seconds at 2277.995474 seconds.
It does not prove lower lock latency or watchdog recovery.

The waiter counter underflowed to `4294967293` from 2920.038862 seconds.
`gLockWaiters` is a volatile `uint32_t` with non-atomic increment and
decrement, so this is an observation defect. Do not use that field for
quantitative H472 comparisons until it is atomic.

Userland advanced. SpringBoard grew from four threads to at least 13, and
continued through `corecaptured`, `nearbyd`, `assetsd`,
`installcoordinationd`, `fileproviderd` and other first-boot services.
The earliest display-client submission was:

```text
2645.960247 s selector=4 pid=56/backboardd
2646.039415 s NATIVE_LEGACY_COPY bytes=8294400 us=69182
2646.039491 s NATIVE_LEGACY_READBACK tl=ff000000 c=ff000000 br=ff000000 q=ff000000
2646.040328 s transfer status=0
2646.040388 s retirement observed
```

By 3257.070285 seconds the gate had advanced to
`s345=1/209/209 val=209 xf=209 fr=0`. Readbacks remained black almost
everywhere, with isolated non-black center pixels `ffaeaeae` and
`ff282828` around 3269 seconds. This is a real backboardd client surface,
but no SpringBoard product frame.

The latest sample inspected before this record was 3386.395635 seconds:

```text
seq=442170 done=442170 timeout=0 ocs_err=0 dbto=0
recover=0 recovered=0 flight=0
lock_ok=1153588 lock_timeout=0 lock_wait_max_ms=38114
```

No `NATIVE_MTL`, `NATIVE_FRAME frames>0`, watchdog event, SIGBUS, or panic
was present. Classification:
`H471-window-lock-budget-passes-apfs-abort/no-product-frame`.

Live evidence:
`display-first-frame/logs/H471/device/20261121-044208/H471-live.log`.
