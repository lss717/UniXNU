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
