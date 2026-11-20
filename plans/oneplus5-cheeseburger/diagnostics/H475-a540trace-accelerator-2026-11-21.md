# H475 A540Trace accelerator enablement (2026-11-21)

## Single feature

H474 established the prerequisite state:

```text
sheng-gpu-addon=1
sheng-no-lc=1
addon=7/5/2/0/0/0
ext=4/2 dm=5/0 wp=5/0
SpringBoard sb=27 n=9
offline-accelerator=0
```

H475 enables the already verified H465 accelerator profile:

```text
offline-accelerator=1
_offline-accelerator-plugin=A540Trace
```

The patch also drops `native-trace-amfi-syscall=1` and the already-zero
`h114-icc=0` only to keep the command line inside its hard limit.
UFS submission, lock budgets, addon parser, SpringBoard union, display
and scanout paths are unchanged.

## Payload

```text
kernel       4577d3bc93a48dec1c910e76d4262e8ceda64869f6b370a2ee3ff42556364b00
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
Data seed    7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
ADT          9fa9e5ba88b84546ef89f79b26bbd9a9cea5e881b8efebf2c2149d09259eb74d
unixnu.toml  dd6f80f19f74931600aa5cd83543245cac09db82fb5cf3da3457b8e065f01e81
payload      8bef2a7991f1e6164074d44398006cf7f8fc09648dc58f3663190710e30712bf
```

The kernel round-trip is byte-identical. The command line is 988 bytes,
1008 bytes with the real `zap-base`, and 1016/1024 bytes in the
worst case.

## Boot

```text
UEFI    9e6608c42e7fc7fc66d399e6f9193a00648bab8aff10d446d3fcc0fc486b17a6
payload 8bef2a7991f1e6164074d44398006cf7f8fc09648dc58f3663190710e30712bf
boot    43f709eb4f796881e586bd3ff6694b96056f4c46fd94f9bb0b08e48251530dc5
```

## Device gates

Accelerator registration:

```text
NATIVE_UFS_ACCEL: MetalPluginName=A540Trace source=arg
```

The addon and SpringBoard prerequisites must remain:

```text
addon=7/5/2/0/0/0
ext=4/2 dm=5/0 wp=5/0
SpringBoard alive without an AMFI constraint loop
```

UFS must remain `seq==done`, with no OCS, recovery or window-lock timeout.

Display/desktop evidence must distinguish:

- a `NATIVE_MTL` plugin/device load;
- CA draw, dispatch, commit and present;
- NativeMobileDisplay selector 4/5 and accepted validation;
- a non-black backboardd surface copy;
- a real SpringBoard product frame.

A synthetic transfer or accepted swap alone does not close the desktop
gate.

Evidence directory:
`display-first-frame/builds/H475/`.
