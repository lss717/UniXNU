# Format 1 XNU patch-series migration (2026-11-22)

This work is independent of the H522/H523 first-frame experiments. It changes
how the Format 1 XNU patch set is named and applied without changing any patch
contents.

## Baseline

- XNU source: `d8b80295118ef25ac3a784134bcf95cd8e88109f`
  (`xnu-10063.141.1`).
- Original application order: shell glob order over
  `patches/xnu/*.patch`, followed by
  `kits/NativePrelink/patches/*.patch`.
- Patch count: 134 XNU patches and 2 NativePrelink patches, 136 total.
- Original series manifest SHA-256:
  `AEC6856B60AEDAAB9A09C41FCF566BD11147A57518897D88CB741D1D72454078`.
- Final XNU series SHA-256:
  `71D6BC07C6D520D797AAB90C946DA75B8BDB95DC52737735FB28C8362078AB62`.
- NativePrelink series SHA-256:
  `AFBCDD303D80105B5934CE56D6AD05FFDF2753C9C8C94F1B8D039623AE5D3297`.
- Original order was applied to a clean shared clone of the pinned XNU feed.
  After staging every change, `git write-tree` returned:
  `d472b9e76667a67d3e6194ca8c1b761cacf6db8a` (85 changed paths).

## Series manifests

The authoritative manifests are:

```text
patches/xnu/series
kits/NativePrelink/patches/series
```

The XNU manifest has 134 entries. The NativePrelink manifest has two entries.
`scripts/apply-patch-series.py` rejects:

- duplicate entries;
- listed patch files that do not exist;
- `.patch` files that exist in the directory but are not listed;
- absolute paths, directory paths, and non-`.patch` entries.

The build, prelink, patch-generator and library-pthread paths use those
manifests. The Mac device repository carries its own copy of the
NativePrelink manifest because `unixnu tree` may override the superproject
submodule with the device repository kit.

## Rename

The migration renamed 84 patches from alphabetical ordering prefixes to
functional names. Fifty additional filenames were already functional.

Git records all 84 changes as 100% renames:

```text
rename count: 84
R100 count:   84
```

Patch contents and file modes are unchanged. `patches/xnu/README.md` records
the ordering dependencies, including:

- `native-gpu-addon-mount.patch` before
  `native-gpu-addon-log.patch` and the later `addon-*.patch` files;
- `log-process-state.patch` before `ipc-event-ring.patch` and the BKS/target
  port consumers;
- `data-mount-ready.patch` before the LaunchServices filesystem and stable-gate
  probes;
- `springboard-late-union.patch` (historically H437) last because it edits the
  same late `kern_exec.c` region as multiple earlier patches.

## Equivalence result

The final manifests were applied to a second clean clone of the same XNU feed.
After all 136 patches:

```text
final applied count: 136
final tree SHA:      d472b9e76667a67d3e6194ca8c1b761cacf6db8a
baseline tree SHA:   d472b9e76667a67d3e6194ca8c1b761cacf6db8a
```

The identical tree SHA includes file content, executable bits, and all source
files created by the patches.

## Normal Mac entry

The normal Mac entry

```sh
JOBS=8 OP5_A540_FIRMWARE=/Users/lss/display-first-frame/inputs/a540 \
  bash scripts/macos-build-kernel.sh
```

applied the explicit series and completed:

```text
applied: 134 XNU patches
applied:   2 NativePrelink patches
filtered compile errors: 0
build log:
  /Users/lss/h468-build/h523-series-build-3.log
```

The final prelink completed after confirming the sparse-prelink ABI patch was
present:

```text
kernel SHA-256:
  4a6027c94321545740e86a2f335f6a56e78e0d4b42fad4098ca507bd8529e02c
```

## Revisions

```text
UniXNU manifest commit:
  853461e build(xnu): apply patches from ordered series
UniXNU rename commit:
  0a1d899 refactor(xnu): name patches by function and use series order
UniXNU explicit two-stage apply fix:
  ef8b6d7 fix(build): apply XNU and Prelink series explicitly
NativePrelink series:
  84aa36d build: add ordered XNU patch series
device repository NativePrelink series:
  0e97aed build: require ordered NativePrelink patch series
drivers/NativeMobileDisplay comment reference:
  80a7126 docs: update kernel patch reference
```
