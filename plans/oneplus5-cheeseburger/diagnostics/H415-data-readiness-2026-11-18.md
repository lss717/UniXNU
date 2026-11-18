# H415 bounded Data mountpoint readiness

Date: 2026-11-18

## Scope

H415 is a single behavior experiment derived from `main@158e74312c78c0a20d0ab244d122f7d2793fc6ed`
and device `main@481fcfe73a1e73ed9c9bb7eef6ceb7ddffe3ce91`.

It does not include the rejected H414 focused IPC implementation. The H413
read-only display/IPC probes already present on main remain unchanged.

## Observed prerequisite gap

`load_init_program()` calls `native_owner_data_prepare()` before launchd exec.
The existing H82 code waits for `native_ram_block_volume_seed()` and then calls:

```text
mount("apfs", "/private/var", scratch_data_device)
```

H414 run C returned `ENOENT` from that call at `stage=2`. The Data provider was
already readable, but the existing wait covered only provider publication.
Successful H413/A/B rings show root SystemOS mount-complete before their Data
store/mount sequence. H414 provenance is confounded by PMGR stub/real and
cache/no-cache differences, so this sequence is motivation for a controlled
test, not proof that mount ordering alone caused every failure.

## Change

After the RAM Data provider is qualified and before constructing the original
APFS mount request, H415 performs a bounded vnode lookup of the existing root
mountpoint:

```text
/private/var
```

Rules:

- only `ENOENT` is retried;
- every other lookup error is returned immediately;
- provider and mountpoint polling share one 600 x 100 ms budget;
- timeout returns `ETIMEDOUT`;
- each lookup drops its vnode before sleeping;
- no vnode lock is held while sleeping;
- the original APFS mount, post-mount lookup, device/read-only validation,
  GPU-addon preparation and staged-app preparation remain the same;
- no Preboot or SystemOS wait is added. In the current call order, those stages
  depend on the scratch Data mount and waiting for them here would create a
  cycle.

New status records:

```text
NATIVE_H82_DATA_PATH_WAIT: <poll> seed=<n> root=<0/1> err=<errno>
NATIVE_H82_DATA_PATH: status=0 seed=<n> mount=<n> root=<1>
NATIVE_H82_DATA_PATH: status=<errno> seed=<n> mount=<n> root=<0/1> err=<errno>
```

## Build and device gate

The candidate must be built in this order:

```text
committed/pushed core source
Mac fetch/check out the same core commit
clean device main@481fcfe7
clean submodule gitlinks
independent H415 feeds and lock hash
complete PMGR stub pass + prelink
complete real PMGR pass + final prelink
payload + boot
static source/archive/kernel/payload/boot provenance checks
one bounded device boot
```

The device boot is not allowed if the final build still reports
`final_pmgr_required=true`, if H415 feeds resolve through another worktree, or
if the source/archive/kernel/payload chain has an unknown intermediate.

## Non-goals

This candidate does not claim a first-frame fix. It does not change IOMFB,
IOSurface, IOGPU, accelerator, NativeMobileDisplay, copy, scanout, launchd
delegate behavior or the H413 focused-event implementation.
