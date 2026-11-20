# H469 unaligned UFS observation repair (2026-11-21)

## Triggering evidence

H468 reached XNU, initialized and published the UFS/display services, and read
the GPT before stopping with:

```text
NATIVE_PANIC_STR: Unaligned kernel data abort.
pc=0xfffffff0079d6090 lr=0xfffffff0079d3328
```

Mapping those addresses with the matching H468 kernel and prelink dSYM gives:

```text
pc -> ufsSubmit() NativeUfsProbe.cpp:2776
lr -> ufsCommand() NativeUfsProbe.cpp:2907
```

H468 object disassembly at that source location contains:

```text
ldur w8, [x8, #0x12]
rev  w8, w8
```

The `#0x12` offset is CDB byte 18. A 4 KiB-aligned UCD therefore gives address
`base + 18`, which is `2 mod 4`, while the generated instruction performs a
four-byte load. This is a direct source/binary/runtime match.

## Single change

H469 changes only the LBA observation loads:

- keep the UFS timeout, recovery, lock, request ordering, display and watchdog
  scheduling behavior unchanged;
- retain the watchdog-thread H469 status report from H468;
- read CDB bytes 18 through 21 through a `volatile const uint8_t` pointer and
  assemble the big-endian LBA explicitly.

The volatile byte accesses should prevent the compiler from folding the four
observation reads back into an unaligned wide load.

## Static gate

```text
python3 plans/oneplus5-cheeseburger/diagnostics/H469-ufs-unaligned-check.py
H469 unaligned-observer static gate: PASS
H469 marker: H469
H469 volatile CDB bytes: 18,19,20,21
H469 status path: watchdog thread
H469 UFS timeout/recovery/order changes: none
```

## Build gate

A build is not accepted from source inspection alone. Before packaging:

1. verify the H469 kernel marker and changed kernel hash;
2. inspect the H469 `NativeUfsProbe` object disassembly and require four byte
   loads for CDB bytes 18 through 21;
3. reject any `ldur w8, [x8, #0x12]`, 16-bit or 32-bit load covering CDB bytes
   18 through 21;
4. verify prelink, payload kernel round-trip and boot-argument length;
5. record kernel, payload and boot hashes in `STATUS.md`.

## Device gate

Only after all build checks pass, boot once on serial `16149951`. The direct
result to seek is that the previous GPT-path unaligned data abort no longer
occurs. A longer run must then reach the `NATIVE_H469_STATUS` watchdog sample.

Reaching the first status row would establish that the status path executes.
It would not yet establish that the earlier UTRD stall completed or that lock
waiting decreased; those require matching terminal/recovery and lock counters.

## Unverified until device run

- Whether unaligned byte 18 was the sole cause of the H468 abort.
- Whether H469 reaches the 30-second watchdog status sample.
- Whether UFS requests complete normally under the corrected observation.
- Whether display-driver transfer corresponds to any SpringBoard product frame.

H468 remains a failed candidate. Do not relabel it as a watchdog or UFS result.
