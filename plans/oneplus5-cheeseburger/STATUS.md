# OnePlus 5（cheeseburger）B 线状态

- 计划：`plans/oneplus5-cheeseburger/PLAN.md`
- 线路：B — UniXNU / 4K
- 最终目标：iPhone10,2 / iOS 16.7.16（20H392）
- 当前阶段：**B1 — UEFI 固件与 UniXNU 集成**
- 当前 gate：**G1（等待设备实测）**
- 基线提交：UniXNU `e95b37d`（main）
- 本地提交：UniXNU `c8a5eeb`（计划）、`18f3020`（package）、`270ea4b`（B1 记录）
- UEFI 分支：`edk2-msm8998` 的 `unixnu-cheeseburger`，提交 `0471194`、`708fa06`
- 最近更新：2026-10-22

## 下一步

1. **设备实测**：`fastboot boot out/cheeseburger/b1/boot-op5-b1-safe.img`，确认 UEFI 输出、UniXNU 菜单、`OP5ESP` 卷。
2. 如果菜单不出现：先确认 `CheeseburgerBootMemoryDxe` 的 DTB 地址 `0x83300000` 和 `/chosen/linux,initrd-start/-end`；再补 framebuffer 日志驱动。
3. 设备侧补齐：备份、GPT、RAM、UFS 逻辑块大小（B0 剩余项）。
4. 然后补 `CheeseburgerGopLogDxe` / `CheeseburgerKeyInputDxe`，再做 B2 设备仓库。

## 已完成

- [x] 选定 B 线（UniXNU / 4K），最终身份 iPhone10,2。
- [x] 计划与状态文件落盘并提交（`c8a5eeb`）。
- [x] 主机工具安装：clang-20/lld-20、dtc、mtools、acpica-tools、nasm、bison、flex、uuid-dev、python3-pil、python3-git、gettext、abootimg。
- [x] 初始化 UniXNU 21 个子模块。
- [x] clone `edk2-msm8998` 并初始化其子模块。
- [x] 构建上游 `cheeseburger` baseline（GCC5，RELEASE）。
- [x] 建本地分支 `unixnu-cheeseburger`。
- [x] 修复 GCC 13 `-Werror=dangling-pointer`：`ArmPlatformLibMem.c` 的 `MemoryTable` 改为 `STATIC`。
- [x] 旧 edk2 兼容层：
  - `MdePkg/Include/Library/FdtLib.h`（映射到旧 `libfdt`）；
  - `MdePkg/Include/AsmMacroLib.h`（最小 `ASM_FUNC`）。
- [x] `UniXNULib.inf` 增加 `EmbeddedPkg/EmbeddedPkg.dec`（`gFdtTableGuid`）。
- [x] `build.sh` 支持 `UNIXNU_TREE`，把 UniXNU `package/` 和 `drivers/DarwinBoot/` 加入 `PACKAGES_PATH`。
- [x] cheeseburger DSC/FDF 加入 UniXNU、UniXNUDxe、DarwinBoot、CheeseburgerBootMemoryDxe。
- [x] 从 FDF 移除 `SimpleInitMain` 和 `LogoDxe`，为 UniXNU 腾空间。
- [x] 实现 `CheeseburgerBootMemoryDxe`：读 `0x83300000` 的 live DTB，发布 initrd 为只读 BlockIo。
- [x] 构建成功：`MSM8998PKG_UEFI.fd` + 带 UniXNU/DarwinBoot 的 boot image。
- [x] 准备 32 MiB `OP5ESP` 测试 payload 和 `boot-op5-b1-safe.img`。

## 本地产物

| 文件 | SHA-256 |
| --- | --- |
| `out/cheeseburger/b1/boot-op5-b1-safe.img` | `d2bd409a29ffdf7e5dca31cd1d896ec330faab4b543bb544b35e7ed5ab72b41c` |
| `out/cheeseburger/b1/MSM8998PKG_UEFI.fd` | `06002711daadb5fac38697341c2a03e9565afaf455cea90f373fd108d53c5221` |
| `out/cheeseburger/b1/op5-payload.img` | `3bc1ded555d0cd787d11c8531d2c2c60658bc4088d2842a68c042046e352b159` |

`boot-op5-b1-safe.img`：kernel `0x10000000`，ramdisk `0x12000000`（32 MiB），tags `0x14000000`，header v1，page size 2048。

## 已知问题

- **FVMAIN 100% 满**：移除 SimpleInitMain/LogoDxe 后仍无空闲（压缩 FV 约 43%，剩余约 3.5 MiB）。加 GopLog/KeyInput 时可能需要继续删模块或增大 FD。
- **非空 ramdisk 不能用 offset 0**：32 MiB payload 会覆盖内核；设备脚本必须显式设置 ramdisk/tags offset。
- `CheeseburgerBootMemoryDxe` 首版硬编码 `PcdDeviceTreeStore=0x83300000`，待设备确认。
- 还没有 framebuffer 日志和按键输入驱动；菜单可能可见，但 `UNIXNU:` 日志只能走串口。
- 还没有在 OnePlus 5 上实测。

## 待实测

- [ ] RAM：6 GB / 8 GB
- [ ] userdata `first_lba` / `last_lba`
- [ ] `lba_bytes`（UFS 逻辑块）
- [ ] GOP framebuffer 地址/大小/stride
- [ ] 触摸 I2C 总线号和地址
- [ ] live DTB 的 `PcdDeviceTreeStore` 和 `/chosen/linux,initrd-*`
- [ ] `boot-op5-b1-safe.img` 的 load address 是否被 ABL 接受

## 主机环境

Linux x86_64 / Ubuntu 24.04：

| 工具 | 状态 |
| --- | --- |
| `python3` / `git` / `make` / `fastboot` | 可用 |
| `aarch64-linux-gnu-gcc` 13.3.0 | 可用 |
| `clang` / `clang++` / `ld.lld` / `llvm-objcopy` | 可用（LLVM 20.1.2，已软链到 `/usr/local/bin`） |
| `dtc` / `mcopy` / `mformat` / `iasl` / `nasm` / `bison` / `flex` | 可用 |
| `xcodebuild` | 缺失（内核步骤需 macOS 或 GitHub Actions） |

## 阻塞

- 等待设备实测 `boot-op5-b1-safe.img`。
- 等待设备侧备份、GPT、RAM、UFS 逻辑块大小。
- 内核/prelink/userdata 需要 macOS 或 GitHub Actions。

## 工作日志

| 日期 | 阶段 | 内容 | 结果 |
| --- | --- | --- | --- |
| 2026-10-22 | B0 | 建立 B 线计划与状态文件 | 完成 |
| 2026-10-22 | B0 | 主机环境检查 | 缺 clang/dtc/mtools/iasl/nasm/bison/flex |
| 2026-10-22 | B0 | 初始化 UniXNU 子模块 | 完成 |
| 2026-10-22 | B0 | clone edk2-msm8998 | 完成（shallow，后补子模块） |
| 2026-10-22 | B0 | 安装主机工具 | 完成（LLVM 20；clang-18 依赖冲突，改用 clang-20） |
| 2026-10-22 | B0 | 初始化 edk2-msm8998 子模块 | 完成 |
| 2026-10-22 | B1 | 构建 upstream cheeseburger baseline | 成功；GCC 13 dangling-pointer 需修 |
| 2026-10-22 | B1 | 修复 ArmPlatformLibMem + 建分支 | 成功，提交 `0471194` |
| 2026-10-22 | B1 | 加入 UniXNU/DarwinBoot/initrd 驱动并构建 | 成功；FVMAIN 100% 满 |
| 2026-10-22 | B1 | 打包 32 MiB 测试 payload + safe boot image | 完成，待设备实测 |
| 2026-10-22 | B1 | 提交 UniXNU/UEFI 改动 | `18f3020`、`270ea4b`；UEFI `708fa06` |

## 更新规则

每次工作结束追加一行日志，并更新“当前阶段/下一步/待实测/阻塞”。构建产物哈希、日志路径和失败现象记录在日志里；私有文件只放 `.cache/firmware/`，不提交。
