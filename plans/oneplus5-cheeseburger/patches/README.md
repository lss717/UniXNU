# OnePlus 5 B 线：UEFI / edk2 兼容补丁

这些文件记录 2026-10-22 在 `edk2-msm8998` 的 `unixnu-cheeseburger` 分支上做出的最小改动。目标是先把 UniXNU + DarwinBoot + initrd 块设备跑起来，不是最终的上游形态。

## 补丁

| 文件 | 作用 |
| --- | --- |
| `0001-platform-static-memory-map.patch` | `ArmPlatformLibMem.c` 的 `MemoryTable` 改为 `STATIC`，绕开 GCC 13 的 `-Werror=dangling-pointer` |
| `0002-uefi-unixnu-integration.patch` | `build.sh` 的 `PACKAGES_PATH`、cheeseburger DSC/FDF、`CheeseburgerBootMemoryDxe` |
| `0003-unixnu-embeddedpkg-fdt.patch` | `UniXNULib.inf` 增加 `EmbeddedPkg/EmbeddedPkg.dec`（`gFdtTableGuid`） |
| `0004-release-framebuffer-log-and-drop-linux.patch` | RELEASE 也加 `SerialDxe`（屏幕日志）；删除内嵌 Linux `LinuxSimpleMassStorage` |
| `0005-drop-duplicate-terminal-console.patch` | 移除 `TerminalDxe`，避免 `ConOut` 在 framebuffer 上重复渲染 |
| `0006-board-info-app.patch` | `CheeseburgerInfo`：从 payload 启动，打印 RAM/GOP/BlockIo/GPT userdata |
| `0007-info-loader-protocol.patch` | `CheeseburgerInfo` 增加 DarwinBoot `UniXNULoader` 协议检查 |

## 旧 edk2 兼容头

`edk2-msm8998` 自带的 edk2 是 2023 年的旧树，缺少 UniXNU/DarwinBoot 使用的新 MdePkg 头文件。构建前把这两个文件复制到 edk2 子模块：

```sh
EDK2=/home/ls/edk2-msm8998/Common/edk2
cp patches/edk2/MdePkg/Include/Library/FdtLib.h "$EDK2/MdePkg/Include/Library/FdtLib.h"
cp patches/edk2/MdePkg/Include/AsmMacroLib.h    "$EDK2/MdePkg/Include/AsmMacroLib.h"
```

- `FdtLib.h` 把新的 `Fdt*` 名字映射到旧 `EmbeddedPkg/Library/FdtLib` 的 `libfdt` 符号，并补 `FDT_HEADER` 和 `FdtString`。
- `AsmMacroLib.h` 提供 DarwinBoot `Entry.S` 需要的 `ASM_FUNC` / `ASM_PFX`。

## UEFI 驱动

`uefi/CheeseburgerBootMemoryDxe.*` 是 `0002` 里新增驱动的副本，便于在 `uefi-cheeseburger` 仓库建立前保留源码：

- 从 `PcdDeviceTreeStore = 0x83300000` 读取 ABL 传入的 live DTB 地址；
- 解析 `/chosen/linux,initrd-start` 和 `linux,initrd-end`；
- 发布只读 `EFI_BLOCK_IO_PROTOCOL`，让 FAT 驱动挂载 `OP5ESP`。

## 构建

```sh
cd /home/ls/edk2-msm8998
# 先复制上面两个兼容头
UNIXNU_TREE=/home/ls/UniXNU bash build.sh --device cheeseburger --release RELEASE
```

产物：

- `workspace/Build/cheeseburger/RELEASE_GCC5/FV/MSM8998PKG_UEFI.fd`
- `boot-cheeseburger.img`（空 ramdisk）

带 payload 的测试镜像由 `mkbootimg.py` 另行打包，必须显式设置非重叠的 ramdisk/tags offset：

```sh
python3 mkbootimg.py \
  --kernel workspace/uefi-cheeseburger.img.gz-dtb \
  --ramdisk /path/to/op5-payload.img \
  --base 0x10000000 --kernel_offset 0 --ramdisk_offset 0x02000000 --tags_offset 0x04000000 \
  --header_version 1 -o boot-op5-b1-safe.img
```

## 待办

- 把这两个兼容头变成 `uefi-cheeseburger` 的正式 package，而不是复制到 edk2 子模块。
- 屏幕日志已由 `FrameBufferSerialPortLib`（`0x9d400000`）+ `SerialDxe` 提供，不需要 `CheeseburgerGopLogDxe`。
- 按键沿用镜像里的 Qualcomm `ButtonsDxe`；只有设备上不可用时才补 `CheeseburgerKeyInputDxe`。
- FD 空闲 4.97 MiB（`FVMAIN_COMPACT` 用 1,050,320 B）；`FVMAIN` 的 “100% 满” 是 `NumBlocks=0` 的设计结果。
- 设备实测 `0x83300000`、`/chosen/linux,initrd-*`、`0x9d400000` 已完成；按键映射仍待确认。
- `CheeseburgerInfo` 不进 FV：只加在 DSC 的 `[Components]`，由 payload 的 `Info.efi` 提供。
