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

## Build result

The H469 source commit is `66ff03ec85830b262ac21569d5633c962d55cba0`.
Both kernel passes, prelink, payload packaging and boot-image packaging passed.

```text
tree kernel          65853e3945cc18f27e71bd15b2bce74ffb8957ac1eebc559db208209494106ec
NativeUfsProbe.o     2635b6e7ecb153ba0f7e32f25c1be629a43aa88af7eefbf01a802b63b58941c8
kernel               700b50d93379bc804c955c29db0eb77451d1d3353cf1c0a7ad484bfa9a7d849c
payload              593ad3a363d90a3b3f100ac8684f0c84710de4275181d321c7916f314b257b4e
boot                 f2d25dd20487c27c878ac07497bd4a65db918f8422354460da4a9e0684f20495
ADT                  d97c6b8140c6745d6871fbdb771c5d55f8cc1be3d0d51452af4ad758e28bf36e
owner trust          cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
PMGR archive         5c59361277e7d479313e7f880e1c742d234abf9fed72d6d0088126f53117d097
```

The payload kernel round-trip passed. Boot arguments remain 992 bytes, and the
worst-case `zap-base` form is 1020/1024 bytes.

The compiled `NativeUfsProbe.o` contains:

```text
ldrb w10, [x8, #0x12]
ldrb w11, [x8, #0x13]
ldrb w11, [x8, #0x14]
ldrb w8,  [x8, #0x15]
```

The object has zero `ldur w*, [x*, #0x12]` instructions. The final kernel has
exactly one `H469` tag and one `NATIVE_H469_STATUS` string, with no H468 status
string.

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
