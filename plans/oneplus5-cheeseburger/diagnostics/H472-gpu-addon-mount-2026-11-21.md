# H472 verified GPU addon mount (2026-11-21)

## Single variable

H471 reached a real backboardd display-client submission while its payload
kept both GPU controls disabled:

```text
sheng-gpu-addon=0
offline-accelerator=0
```

H472 changes only the boot-time addon mount:

```text
sheng-gpu-addon=1
offline-accelerator=0, unchanged
```

The purpose is to separate addon installation from accelerator activation.
This round does not inject `A540Trace`, change the Metal plugin, alter the
display code, or change the H471 UFS window-lock budget.

The verified H471 kernel and Data seed are reused. The same owner trust cache
and GPU addon are packaged. H471 exposes the necessary counters even though
its reconstructed observation source no longer contains the old
`native_gpu_addon_calls++` statement: `addon=files/written/same/failed/error/calls`
and `ext/dm/wp` stages remain valid. In H471 those counters were
`addon=-1/0/0/0/0/0`, `ext=0/-1 dm=0/-1 wp=0/-1`; the missing calls increment
is an instrumentation omission, not proof that the preparation function was
not linked. The linked kernel contains the call to
`_native_gpu_addon_prepare` from `_load_init_program`.

## Payload

```text
kernel       6a9f064a85d3ba44b7fe3fac48c8a9b77de6f59f78f8642dfdabbceaad1d5a59
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
Data seed    7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
ADT          1d30e6395cc6d9151b5731b6887df1105d658f1d02311c42ef418b03f9ddee90
unixnu.toml  3618bc87a6da78ffc2c52f480fa119f4b709e0780ae325eb65e3f40be4a8a0c6
payload      1360be39242b16f431a55bdcd04e3104911702c59307bcb743d3ff2baa69bb8c
```

The payload kernel round-trip is byte-identical. The command line is 992 B;
`check-bootargs-fit.py` reports 1012 B with the real `zap-base` and
1020/1024 B in the 16-hex-digit worst case.

## Boot image

```text
UEFI    9e6608c42e7fc7fc66d399e6f9193a00648bab8aff10d446d3fcc0fc486b17a6
payload 1360be39242b16f431a55bdcd04e3104911702c59307bcb743d3ff2baa69bb8c
boot    a7e8f5f557524eadb448d2a5f8267a55e4136bc069c138dc253fe7b9063bfa2a
```

Static checks:

```text
H471 window-lock static gate: PASS
H471 display first-frame gate: PASS
payload kernel round-trip: byte-identical
bootargs fit: PASS
```

## Device gate

The payload is accepted only if the existing heartbeat changes to:

```text
NATIVE_UFS_ALIVE addon=7/7/0/0/<error>/<calls>
ext=4/2 dm=5/0 wp=5/0
```

The exact final three values are implementation observability, but a
successful same H465 addon profile requires seven files and the extension,
daemon and wallpaper mount stages to advance. UFS must remain
`seq==done`, with no OCS, recovery, window-lock timeout or APFS abort.

`NATIVE_MTL` should remain absent in H472 because `offline-accelerator=0`.
A black backboardd surface is not a SpringBoard product frame. Only after
mount success may H473 enable the `A540Trace` accelerator and plugin selector
as a separate variable.

Evidence directory:
`display-first-frame/builds/H472/`.

## Device result

One local `fastboot boot` on serial `16149951` returned
`Sending 'boot.img' OKAY` and `Booting OKAY`. CDC appeared at about
244 seconds. Runtime boot ID was `2681b67d`.

The UFS and Data baseline remained live:

```text
NATIVE_UFS_ALIVE:
  addon=-1/0/0/0/22/0
  owner=4/0 ext=4/2 dm=1/2 wp=1/2
  accel=0/0/0/0
```

The extension-level union mount reached stage 4/status 2, but
`native_gpu_addon_install` returned `files=-1` and error 22 (`EINVAL`).
The daemon and wallpaper mounts remained at stage 1/status 2. The same
addon SHA (`88251c...5dee`) installed seven files under H465, so the
artifact itself is unchanged and valid.

Root cause was a source/build-tree mismatch. The current kernel parser
read a 24-byte per-entry header, while `make-gpu-addon.py` writes the
version-2 32-byte header containing CRC-32 and the stored/compressed
flag. Reading the name at `+24` instead of `+32` fails validation with
`EINVAL` before any file is written.

The earliest failure was complete by the 280.376527-second heartbeat.
The capture was intentionally stopped after the deterministic addon
failure rather than spending the full 3600 seconds. It had reached
about 400 seconds, with no OCS, recovery, window-lock timeout or panic.
`NATIVE_MTL` remained absent, as expected with
`offline-accelerator=0`.

```text
H472-live.log                   dd37b2200c34a997bff93f752538aa81edc19efefd93e589feff581cd1a76362
H472-clear-readback32.bin       83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302
```

The 32 MiB clear was verified byte-for-byte as the SHA-256 of all-zero
32 MiB data. Classification:
`H472-addon-enabled-parser-v1-rejects-v2`.
