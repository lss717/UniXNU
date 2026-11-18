# H421 LaunchServices progress gate

Date: 2026-11-19

H420 closed the BKS request/reply and showed that the next SpringBoard main
thread consumer is `CCSModuleRepository`. Offline symbolication of the same
boot resolves that consumer through `LSApplicationRecord` and
`_LSContextInitCommon` to a synchronous mach message whose peer is `lsd`.
At the same timestamp, `lsd` is scanning system content through
`LSRebuildStatisticsGatherer`, `MILaunchServicesDatabaseGatherer` and
`MIExecutableBundle` code-signing paths.

## Unique observation

H421 keeps every H420 behavior input and adds only a low-frequency read of
fixed storage:

- count `vn_open_modflags` completions made by processes named `lsd`;
- count how many of those opens are currently in flight;
- count completions slower than 50 ms and retain a 64-bit maximum;
- retain the latest eight bounded paths in fixed slots;
- print `NATIVE_LS_GATE` and up to eight `NATIVE_LS_GATE_SLOT` rows only from
  the existing low-frequency kernel sampler when it samples `lsd`.

The probe does not print in the new accounting or completion helpers. It does
not allocate, sleep, take a new lock, change an open result, call LaunchServices,
hook SpringBoard, create a scene/drawable, or call display/GPU code.

## Classification target

```text
opens increasing before first OCS
  -> LaunchServices scan is progressing; the main-thread wait is unfinished work

opens and active slots frozen before first OCS
  -> identify the held path/slot and inspect the corresponding vnode or service

lsd exits or is killed before the gate samples
  -> bind the exit/trap time and preserve UFS/corpse evidence as a separate fault
```

The result must be interpreted with the first OCS timeout, not after the later
corpse storm. No behavior change is authorized by this candidate.

## Static gates

```text
check-h421-launchservices-gate.py
H421 XNU patch applies with plain git apply --check
drivers/NativeMetal/tools/check-h420-main-scene.py
```

The patch must remain ordered after the H395 open measurement and the H420 BKS
repair. Build, device, and recovery status are appended only after a bounded
run.

## Static build result

The final source tree was pulled on `mac` at
`37ae68ee11eef749051f3de05ad4ff78e7d06255`. Two PMGR passes completed:

```text
source kernel stub  a9a42afdf6c8dd41588bb4399a80aeab6676393f7da5d917fe3358e32559d4ee
stub prelink        b4a4bf8d79b08c6075e9f1eb25a83b1fc3782a39c5233c754d39672def06efd4
stub PMGR           b8dbb622bdefebc094cb645cf5a5304cf6f5c8395108c5dbfd98feb3f3b4b2ad
source kernel real  4c46d873c74386fd84cab1b36c4b262409d34f239f55c1d431b7b0c725c19f8d
real PMGR           b8f4b8bf3bed783278696c0bc06c48ac27881f8cb03f923b0f1ec0635ea1a82c
final kernel        06415c05fc3c2b839232c07a5b6eb4638b88ea6b4a40d7b522e28a0749727d74
payload             337858312cd53e815e1c3187cc3e57e45f0e39897373abdc6ab2587b1db4df34
boot                2282441f210430cd9e3fa77de2be24b91b425d5bdd53b71209e129bcf45e9947
ADT                 b8eb10f81c8e1c80cd37cacc4715b8291f89639c802a7c4024f4a0dd4be5b8d1
```

The payload retains H420's Data seed, A540 addon, owner trust and 995-byte
command line. `verify_h421.py` passed boot-to-payload-to-kernel reverse
extraction, UEFI gzip/FDT, FAT sidecars, ADT, addon/trust, and the
`1023/1024` worst-case bootargs check. The final kernel contains
`NATIVE_LS_GATE:` and `NATIVE_LS_GATE_SLOT:`.

Classification:
`launchservices-progress-gate-package-statically-verified`. Device testing is
still pending.
