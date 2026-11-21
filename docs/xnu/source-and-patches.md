# Source and patches

UniXNU builds XNU from the pinned Apple source and applies patches in the
explicit order recorded in each series file.

## Source

`feeds.toml` pins the source:

| Source | Tag | Purpose |
| --- | --- | --- |
| `xnu` | `xnu-10063.141.1` | Kernel source |
| `libplatform` | `libplatform-316.100.10` | Platform headers |
| `libdispatch` | `libdispatch-1477.100.9` | Dispatch headers |
| `AvailabilityVersions` | `AvailabilityVersions-141.1` | Availability macros |
| `libpthread` | `libpthread-519.120.4` | Source pthread component |
| `corecrypto-2023` | commit `11fba65` | Source corecrypto component |
| `IOStorageFamily` | commit `e45fbe3` | Public storage headers for the block drivers |
| `edk2` | `release/202608` | EDK II base for the package and firmware |

The XNU entry also carries:

```toml
darwin = "23.6.0"
version = "10063.141.1"
driverkit_tag = "xnu-10063.121.3"
trustcache_tag = "xnu-8796.101.5"
```

`driverkit_tag` supplies `iokit/DriverKit` headers that the current tag omits. `trustcache_tag` supplies `EXTERNAL_HEADERS/TrustCache`.

## Patch application

`scripts/build-xnu-4k-baseline.sh` applies patches to `.cache/xnu-work`:

1. Reverse the patches that overlap earlier contexts, when they are present:
   - `patches/xnu/boot-progress.patch`
   - `patches/xnu/native-gpu-addon-mount.patch`
2. Validate and apply every entry in `patches/xnu/series`.
3. Validate and apply every entry in `kits/NativePrelink/patches/series`.
4. Skip a patch that is already applied.
5. Run `prepare-xnu-source.py` to restore omitted headers.

The series files are authoritative. They reject duplicate entries, listed
patches that are missing, and `.patch` files that were not listed. Filenames
describe the change and do not control order. The cross-patch ordering reasons
are recorded in `patches/xnu/README.md`.

A patch is idempotent through the shared series checker:

```sh
python3 scripts/apply-patch-series.py --root patches/xnu apply \
  --worktree .cache/xnu-work --skip-applied
```

`--check` stops the build before a partial application.

## Patch layout

| Directory | Contents |
| --- | --- |
| `patches/xnu/` | Kernel patches |
| `patches/libpthread/` | Source pthread patches |
| `patches/mesa/` | Turnip and Mesa build patches |
| `kits/NativePrelink/patches/` | Prelink ABI patches |

A device repository can add `patches/` modules. The build tree links them
under `tree/patches/`, and every added `.patch` must be listed in that module's
series file.

## Add a patch

1. Build the kernel once so `.cache/xnu-work` exists.
2. Edit the source in `.cache/xnu-work`.
3. Generate the patch:

```sh
git -C .cache/xnu-work diff -- <paths> > patches/xnu/my-change.patch
```

4. Add `my-change.patch` at the required position in `patches/xnu/series`.
5. Run `unixnu build kernel` again. The series checker rejects the unlisted
   file until step 4 is complete.

A patch that adds a build option follows the pattern in `native-aes-personality.patch`:

```c
#if defined(XNU_MY_OPTION) && XNU_MY_OPTION
    "   ,{"
    "     'IOClass'         = MyDriver;"
    "     'IOProviderClass' = IOPlatformDevice;"
    "   }"
#endif
```

The matching `-DXNU_MY_OPTION=1` comes from `EXTRA_MAKE_ARGS` in the kernel script.

## Build flags

The kernel build uses these switches:

| Switch | Value |
| --- | --- |
| `SDKROOT` | `iphoneos` |
| `ARCH_CONFIGS` | `ARM64` |
| `MACHINE_CONFIGS` | `BCM2837` |
| `KERNEL_CONFIGS` | `DEVELOPMENT` |
| `ARM64_LINK_ADDR` | `0xfffffff007004000` |
| `ARM64_PLKSEG_ADDR` | `0xfffffff004004000` |
| `DEPLOYMENT_TARGET_FLAGS` | `-miphoneos-version-min=17.0 -DXNU_TARGET_OS_IOS` |
| `BUILD_LTO` | `0` |
| `BOUND_CHECKS` | `0` |

`BCM2837` carries the 4 KiB page layout. `BUILD_LTO=0` keeps the object files and the compile records readable and link-compatible with the external archives.

## Defconfig mapping

Each `CONFIG_XNU_<NAME>` becomes `XNU_<NAME>`:

| Defconfig value | Build value |
| --- | --- |
| `y` | `1` |
| `n` | `0` |
| `"text"` | `text` |
| `123` | `123` |
| `{tree}` in a string | Build tree path |

The kernel script reads the variables and adds object flags, archives and link inputs.

## Source tree

```
out/<board>/tree/
  refer/xnu/                 pinned source
  .cache/xnu-work/           working clone
  .cache/fakeroot/           kernel SDK root
  .cache/sources/            restored header manifests
  build/xnu/ios-obj/         objects and compile records
  build/xnu/ios-sym/         symbols
  build/xnu/ios-dst/         install headers
  patches/xnu/               linked patches
  kits/NativePrelink/        prelink tool and patches
```

## Updating the source

1. Set a new `ref` and `commit` in `feeds.toml`.
2. Update `darwin`, `version`, `driverkit_tag` and `trustcache_tag`.
3. Rebase the patches onto the new tag.
4. Update the archive builders in `[kernel] archives` for the new compile records.
5. Rebuild the prelink and re-qualify the kernelcache pin.

The prelink output depends on the original kernelcache ABI. A new source version can require a new kernelcache pin and new roots.

## Next steps

- [Four-kilobyte pages](/xnu/four-k-page-tables)
- [Patch reference](/xnu/patch-reference)
- [Build the kernel](/guide/build-kernel)
