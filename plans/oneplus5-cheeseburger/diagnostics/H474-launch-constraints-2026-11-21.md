# H474 SpringBoard launch-constraints bypass (2026-11-21)

## Trigger

H473 fixed the GPU addon v2 parser and passed the install gate:

```text
addon=7/5/2/0/0/0
owner=4/0 ext=4/2 dm=5/0 wp=5/0
```

However every SpringBoard exec was rejected:

```text
AMFI: Launch Constraint Violation (enforcing),
  error info: c[8]p[1]m[1]e[6], (Constraint not matched)
NATIVE_EXIT: comm=SpringBoard status=0x9
```

This was deterministic from about 276 seconds and reached the corpse
limit. The verified H465 profile used `sheng-no-lc=1`.

## Single behavior change

H474 keeps the H473 kernel, Data seed, trust cache and GPU addon. It
enables only:

```text
sheng-no-lc=1
```

`offline-accelerator` remains zero. The redundant duplicate
`h103-log-secs=60` is collapsed to one occurrence only to keep the
command line within budget; the value and cadence do not change.

## Payload

```text
kernel       4577d3bc93a48dec1c910e76d4262e8ceda64869f6b370a2ee3ff42556364b00
trust cache  cd754067b9587960d336715b35c933cfb50b29f3b5b7b48feb0d8988092541cf
GPU addon    88251c35d6a1b6b6df2c761c2c136f04a9090e1361f16fdaceac798ba6da5dee
Data seed    7522c2b803bac371190e5f316bacc825d1dd3c964ef3a3ab6ffd75bf0f9bae79
ADT          f5ac162d313d9d9c46847080ee3a405c3e9bae056e6990abb545e2bf00ede93b
unixnu.toml  4166c00899ff757d4548f81ce90033533e1307573ff5cc533289644ea658f7f1
payload      b3bde11fd3a25e28c63b7c9c51c84d2e8e14a0b0190ce87881a1f4f47f48ecb7
```

The payload kernel round-trip is byte-identical. The command line is
989 bytes, 1009 bytes with the real `zap-base`, and 1017/1024 bytes in
the worst case.

## Boot

```text
UEFI    9e6608c42e7fc7fc66d399e6f9193a00648bab8aff10d446d3fcc0fc486b17a6
payload b3bde11fd3a25e28c63b7c9c51c84d2e8e14a0b0190ce87881a1f4f47f48ecb7
boot    7d1dcaafdf7b95c592a92c990e519d56eff280873c396697f6521dbe4580b5fe
```

## Device gate

Required:

- `addon=7/5/2/0/0/0`;
- `ext=4/2 dm=5/0 wp=5/0`;
- SpringBoard exec survives AMFI launch constraints;
- no new AMFI `Constraint not matched` exit loop;
- UFS remains `seq==done` with no OCS, recovery or lock timeout;
- `NATIVE_MTL=0`, because the accelerator remains disabled.

Only after this pass may H475 change the accelerator controls together
as one feature: `offline-accelerator=1` and
`_offline-accelerator-plugin=A540Trace`.

Evidence directory:
`display-first-frame/builds/H474/`.

## Device result

One local `fastboot boot` on serial `16149951` returned `Sending OKAY`
and `Booting OKAY`. CDC appeared about 249 seconds after the boot
command. Runtime boot ID was `2234f4d3`.

The expected gates passed:

```text
addon=7/5/2/0/0/0
owner=4/0 ext=4/2 dm=5/0 wp=5/0
accel=0/0/0/0
```

SpringBoard survived the launch constraint. At 343.107224 seconds the
sampler saw a live process with nine threads:

```text
NATIVE_SBCHAIN:
  sb=27 n=9
  req=11275/1/launchd q=1 sr=0 so=3
```

No `Constraint not matched` restart loop or SpringBoard `NATIVE_EXIT`
appeared. UFS reached `seq==done` samples with no OCS, recovery or
window-lock timeout. The bounded observation stopped after about 403
seconds once the launch gate had remained stable.

```text
H474-live.log
  f70ca97d336427743e119c9ccac960d28e1ac232c1d28c3721ef4256a5c9efbb
H474-tail32.bin
  d4e9885f7167249b280c3cf2ddbeeebbe89c3772c90174231543b50d84fa879
H474-h103.txt
  cce368240f98260f7cf5ac4b702befbf2dc6a273c429423d236c53721accd8d5
```

Classification:
`H474-launch-constraint-bypass-pass/addon-mounted`.
