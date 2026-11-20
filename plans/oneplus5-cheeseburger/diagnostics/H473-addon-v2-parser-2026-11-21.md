# H473 GPU addon v2 parser repair (2026-11-21)

## Trigger

H472 enabled only `sheng-gpu-addon=1` and kept
`offline-accelerator=0`. The device returned:

```text
NATIVE_UFS_ALIVE:
  addon=-1/0/0/0/22/0
  owner=4/0 ext=4/2 dm=1/2 wp=1/2
```

Error 22 is `EINVAL`. The same GPU addon SHA
`88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee`
installed seven files under H465.

The rebuilt H471 `xnu-work` retained an older parser. It expected a
24-byte per-entry header:

```text
name_bytes, mode, size, packed
```

The current `make-gpu-addon.py` writes version-2 entries with 32 bytes:

```text
name_bytes, mode, size, packed, crc32, flags
```

The old parser therefore treated the CRC/flags words as the beginning of
the path, failed whole-blob validation, and wrote no files.

## Single behavior change

H473 changes only the versioned entry parser:

- consume 32-byte entry headers;
- validate the stored/compressed flag;
- verify the packed-byte CRC-32;
- write stored entries directly;
- retain the existing inflate and write path for compressed entries.

It preserves:

- the H471 120-second window-lock budget;
- `sheng-gpu-addon=1`;
- `offline-accelerator=0`;
- the H472 Data seed, trust cache and GPU addon;
- display and scanout behavior.

Patch:
`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h473-addon-v2-parser.patch`.

## Build

The parser patch applied cleanly with `git apply --recount` to the
explicit H471 `xnu-work`. `kern_exec.o` was rebuilt after the source
timestamp changed. The build log contains no filtered compile errors.

```text
source commit       da78e9f
source kernel       e8b35199a3abb27c786b63f079c9b1e573c4b7b6af98396c9448604f1f2a160d
NativeUfsProbe.o    4f7dc3c648597b3f4b20859a1e242590be01c776749c737cc43edbde707ceb76
prelink kernel      4577d3bc93a48dec1c910e76d4262e8ceda64869f6b370a2ee3ff42556364b00
```

The kernel contains the `H473` marker and the
`NATIVE_GPU_ADDON: crc` diagnostic string.

## Payload

```text
kernel       4577d3bc93a48dec1c910e76d4262e8ceda64869f6b370a2ee3ff42556364b00
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
Data seed    7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
ADT          62e9130439cfdccf7dae8a72150924ae0f15c51fc2c52165cb7b451ff1fee7a5
unixnu.toml  3618bc87a6da78ffc2c52f480fa119f4b709e0780ae325eb65e3f40be4a8a0c6
payload      e236e6ddd866e9e2eec860e7b92acc625b25454a43d90ab8b542ba6fae775b48
```

The round-trip payload kernel equals the prelink kernel. The command
line is 992 bytes, 1012 bytes with the real `zap-base`, and 1020/1024
bytes in the 16-hex-digit worst case.

## Boot

```text
UEFI    9e6608c42e7fc7fc66d399e6f9193a00648bab8aff10d446d3fcc0fc486b17a6
payload e236e6ddd866e9e2eec860e7b92acc625b25454a43d90ab8b542ba6fae775b48
boot    8f5e42d7a72a64c21902f1ca637b56fdf0eb2a2455963bf3169911d6f668b36e
```

## Device gate

Required:

```text
native_gpu_addon_files == 7
native_gpu_addon_failed == 0
native_gpu_addon_crc_bad == 0
ext=4/2
dm=5/0
wp=5/0
```

UFS must remain `seq==done`, with no OCS timeout, recovery or window-lock
timeout. `NATIVE_MTL` is still expected to be absent because
`offline-accelerator=0`.

A successful H473 permits H474 to enable the already verified H465
A540Trace accelerator profile as the next single feature variable.

Evidence directory:
`display-first-frame/builds/H473/`.
