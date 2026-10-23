# OnePlus 5（cheeseburger）B 线状态

- 计划：`plans/oneplus5-cheeseburger/PLAN.md`
- 线路：B — UniXNU / 4K
- 最终目标：iPhone10,2 / iOS 16.7.16（20H392）
- 当前阶段：**B0 — 准备与基线冻结**
- 当前 gate：**G0**
- 基线提交：UniXNU `e95b37d`（main）
- 最近更新：2026-10-22

## 下一步

1. 确认机型是 OnePlus 5（cheeseburger）还是 5T（dumpling）。
2. 解锁/确认 bootloader 状态，备份 `persist`、`modem`、`efs`、`boot`、`recovery`。
3. TWRP/postmarketOS 下 dump GPT：`sgdisk -p /dev/block/sda`，记录 userdata 的 `first_lba`/`last_lba`/`lba_bytes`。
4. `fastboot getvar all`，确认 RAM 容量和分区大小。
5. 安装主机缺失工具（clang/lld/dtc/mtools/acpica/nasm/bison/flex），然后初始化 `edk2-msm8998` 子模块并构建 `cheeseburger` target。
6. 下载并校验 iPhone10,2 16.7.16（20H392）和 iPad7,1 17.7.11（21H461）IPSW。

## 已完成

- [x] 选定 B 线（UniXNU / 4K），最终身份 iPhone10,2。
- [x] 确认使用 `edk2-msm8998` 的 `cheeseburger` UEFI target。
- [x] 确认 iPad7,1 17.7.11 只作 B3 临时基线。
- [x] 计划落盘：`plans/oneplus5-cheeseburger/PLAN.md`。
- [x] 主机环境初步检查（Linux，缺 clang/dtc/mtools/iasl/nasm/bison/flex）。
- [x] 初始化 UniXNU 子模块（21 个 driver/kit）。
- [x] clone `edk2-msm8998` 到 `/home/ls/edk2-msm8998`（shallow，未初始化子模块）。

## 待实测

- [ ] RAM：6 GB / 8 GB
- [ ] userdata `first_lba` / `last_lba`
- [ ] `lba_bytes`（UFS 逻辑块）
- [ ] GOP framebuffer 地址/大小/stride
- [ ] 触摸 I2C 总线号和地址

## 环境检查（2026-10-22）

主机：Linux x86_64，Ubuntu 24.04，Python 3.12.13，git 2.43.0，fastboot 37.0.1。

| 工具 | 状态 |
| --- | --- |
| `aarch64-linux-gnu-gcc` | 可用（13.3.0） |
| `python3` / `git` / `make` | 可用 |
| `fastboot` | 可用 |
| `clang` / `ld.lld` | 缺失 |
| `dtc` / `fdtput` / `fdtget` | 缺失 |
| `mtools`（`mcopy` / `mformat`） | 缺失 |
| `iasl` / `nasm` / `bison` / `flex` | 缺失 |
| `xcodebuild` | 缺失（内核步骤需 macOS 或 GitHub Actions） |

## 阻塞

- 等待设备侧备份和 GPT 采集结果。
- 等待 IPSW 下载/校验结果。
- 主机缺少 clang/dtc/mtools/iasl/nasm/bison/flex；需要安装后才能跑 `unixnu` 的 payload/UEFI 步骤。

## 工作日志

| 日期 | 阶段 | 内容 | 结果 |
| --- | --- | --- | --- |
| 2026-10-22 | B0 | 建立 B 线计划与状态文件 | 完成 |
| 2026-10-22 | B0 | 主机环境检查 | 缺 clang/dtc/mtools/iasl/nasm/bison/flex |
| 2026-10-22 | B0 | 初始化 UniXNU 子模块 | 完成 |
| 2026-10-22 | B0 | clone edk2-msm8998 | 完成（shallow，未初始化子模块） |

## 更新规则

每次工作结束追加一行日志，并更新“当前阶段/下一步/待实测/阻塞”。构建产物哈希、日志路径和失败现象记录在日志里；私有文件只放 `.cache/firmware/`，不提交。
