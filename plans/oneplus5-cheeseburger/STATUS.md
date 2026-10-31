# OnePlus 5（cheeseburger）B 线状态

- 计划：`plans/oneplus5-cheeseburger/PLAN.md`
- 线路：B — UniXNU / 4K
- 路线/目标：iPad7,1 / iPadOS 17.7.11（21H461）
- 当前阶段：**B5 用户态入口。H81 已让 system-wide shared cache 映射成功并越过 per-process jetsam；launchd 停在 `OS_REASON_LIBXPC` assertion（`namespace 7 subcode 0x1`）。H82f 已用 16 MiB Data skeleton / 76 MiB payload 构建并启动，当前未回 fastboot；等待 `NATIVE_H82_DATA` 屏幕确认 Data mount 状态。**
- 当前 gate：**G1 通过（2026-10-22）；B3 已到 BSD/IOKit；B5 root 已挂载（bring-up）**
- 基线提交：UniXNU `e95b37d`（main）
- 当前代码提交：UniXNU `810ac08`；设备仓库 `dcff488`；fork 子模块 `lss717/RamBlock` `bc079a5`
- 远程仓库：
  - UniXNU `https://github.com/lss717/UniXNU`（`main`）
  - UEFI fork `https://github.com/lss717/edk2-msm8998`（分支 `unixnu-cheeseburger`）
  - 设备仓库 `https://github.com/lss717/UniXNU-cheeseburger`（`main`，`f09609c`）
  - NativeRamBlock fork `https://github.com/lss717/RamBlock`（submodule 路径仍为
    `drivers/NativeRamBlock`，fork 提交 `bc079a5`；`upstream` 指回 `UniXNU/RamBlock`）
- UEFI 分支：`edk2-msm8998` 的 `unixnu-cheeseburger`，提交 `0471194`、`708fa06`、`7f34479`、`91e17a8`、`8ef28f1`、`1ffb934`
- 最近更新：2026-10-28

> 本文件是 B 线（UniXNU / 4K）唯一的计划与状态记录。A 线（在 OP5 上用
> 自建 shim 引导 16K XNU）是另一个独立项目，与本线没有代码依赖。

## G1 设备实测（2026-10-22）

`fastboot boot out/cheeseburger/b1b/boot-op5-b1b-safe.img` 被 ABL 接受（`Booting OKAY`），设备随后从 USB 消失。屏幕确认：

- [x] UEFI 启动，有屏幕输出。
- [x] UniXNU 菜单出现：标题 `OnePlus 5 B1`、条目 `Exit to firmware`、倒计时可见。
- [x] payload 卷挂载成功（菜单来自 `\EFI\UniXNU\unixnu.toml`），说明 `CheeseburgerBootMemoryDxe` 的 DTB 地址 `0x83300000`、`/chosen/linux,initrd-*` 解析和 FAT 栈都工作。
- [x] `fastboot boot` 的 35 MiB boot image 与 `0x10000000/0x12000000/0x14000000` 布局被 ABL 接受。
- [x] DTB 地址 `0x83300000`、`/chosen/linux,initrd-*`、只读 BlockIo、FAT、`unixnu.toml` 全部工作。
- [x] 按键：Qualcomm `ButtonsDxe` 三个键都正常——音量上/下移动高亮，电源键选中（等价 Enter）。
- [x] UniXNU、DarwinBoot、BlockIo 都在：`CheeseburgerInfo` 查到 `UniXNULoader` 协议 `Success`（DarwinBoot 驱动已加载），并枚举到 8 个 BlockIo（没有用 Shell，等价于 `drivers`/`dh`）。
- [x] `UNIXNU:` 日志上屏：`console = "none"` 的 b1h 实测，`SerialDxe` + `FrameBufferSerialPortLib` 把 `UNIXNU:` 行写在屏幕上。

`fastboot getvar all` 已保存到 `.cache/firmware/op5-getvar.txt`（不提交）：hw-revision 20001、unlocked yes、userdata `0x1C4D8BB000`、boot `0x4000000`、没有 A/B slot。

### 诊断镜像 b1c（采集 B0 数据）

固件与 b1b 完全相同（FD `3b7a4c60…`），只换了 payload：加入 `EFI/UniXNU/Info.efi`（`CheeseburgerInfo`），并把 `unixnu.toml` 的默认项设为 `Board info`。该程序在屏上打印内存总量、GOP 模式、整盘 BlockIo 的逻辑块大小和 GPT 的 userdata 边界，停留 180 秒后重启。

G1 现场照片在 `assets/`：`g1-b1c-info-scrolled.jpg`（首版滚屏）、`g1-b1d-info-compact.jpg`（紧凑信息屏）、`g1-b1f-loader.jpg`（DarwinBoot 协议）、`g1-b1h-log.jpg`（`UNIXNU:` 日志）。

## B0 设备数据（2026-10-22 实测）

由 payload 里的 `CheeseburgerInfo.efi` 打印，数值与 `fastboot getvar` 交叉验证。

| 项目 | 值 |
| --- | --- |
| RAM | **8 GB**（UEFI 内存图 7039 MiB / 51 descriptors） |
| UFS 逻辑块 | **4096 B** |
| UFS 主 LUN | 29,763,584 块 = 116,264 MiB |
| `userdata` | `first_lba = 0x14F40` (85,824)，`last_lba = 0x1C627FA` (29,763,578)，29,677,755 块 = 115,928 MiB |
| `userdata` 交叉验证 | 29,677,755 × 4096 = `0x1C4D8BB000`，等于 `fastboot getvar partition-size:userdata` |
| GOP | 1080×1920，stride 1080，fmt 1（BGRX），base `0x9D400000`，size `0x7E9000` |
| 其他 LUN | 4 MiB ×2、128 MiB、4096 MiB、1536 MiB（带 GPT：toolsfv/logfs/sti/…/vendor/reserve3） |
| 无 A/B | `getvar current-slot` 不存在；`unlocked: yes`；`hw-revision: 20001` |

`userdata` 末尾 5 块是 GPT 备份表/头；`FirstUsableLBA` 在 `0x14F40` 之前留给主 GPT。

## B2 进展（2026-10-22）

本地仓库 `/home/ls/UniXNU-cheeseburger`（`main`，当前提交 `a18192e`）：

- `board.toml`：iPad7,1 / 17.7.11 路线、实测 userdata/RAM/GOP 值、`[payload]`；
- `configs/cheeseburger_defconfig`：计划里的最小内核配置；
- `scripts/make-bootimg.py`：调 edk2-msm8998 的 `mkbootimg.py`，地址 `0x10000000/0x12000000/0x14000000`，输出 JSON 报告；已用当前固件实测生成并预检通过；
- `scripts/check-cheeseburger.py`：B1 预检工具的仓库版本，默认读 edk2 构建产物；
- `scripts/make-cheeseburger-adt.py`：从 `make-sheng-adt.py` 改出，MSM8998 常量（GICD `0x17a00000`、GICR `0x17b00000`/stride `0x20000`、19.2 MHz、4×A73 + 4×A53、UFS 节点）；生成 13 KiB Apple 格式树；
- `scripts/check-adt.py`：解析 Apple DT 格式并检查 `/cpus`、`/arm-io/intc`、`/chosen`、`/defaults`、`/options`、`/buttons`、`/product`，生成结果全部通过。

GitHub Actions：`UniXNU/.github/workflows/macos-cheeseburger.yml`（kernel + payload，artifact 上传；固件仍由 edk2-msm8998 单独构建）。

设备仓库的 B3 内核暂时不含 legacy display / boot-progress（sheng 的两个 builder 绑定了它的 Adreno/触摸/背光探针）。这不影响 B3 看 panic：DarwinBoot 把 GOP framebuffer 放进 `boot_args->Video`，XNU 自己的 verbose/panic 控制台直接画到面板；legacy display 是 B7 给 `IOMobileFramebuffer`/SpringBoard 用的。

IPSW 缓存（`unixnu ipsw fetch`，HTTP range，只取需要的成员）：

- `out/ipsw/21H461/DeviceTree.j120ap.im4p`（35 KB）
- `out/ipsw/21H461/044-76040-038.dmg.trustcache`（59 KB）
- 副本在设备仓库 `.cache/firmware/17.7.11/`（不提交）
- `KernelCache` 是 LZFSE，`unixnu ipsw fetch` 需要 macOS `compression_tool`；在本机用 `pylib` 的 lzfse 解开了 DeviceTree 的 `bvx2` 流做校验，但内核/prelink 仍按计划走 macOS 或 GitHub Actions。

## B3 探针可信度（2026-10-23）

复核 `payload-stage3b.img` 里的 stage 3 cave：它等待 `384,000,000` 个
`CNTPCT_EL0` tick，19.2 MHz 下是 **20 秒**，然后执行 PSCI `SYSTEM_RESET`。
STATUS 里“挂几秒再重启”与这个 20 秒不一致，必须先分清那次重启是：

- 约 20 秒后的探针复位 → **stage 3 已执行，MMU 已过**，后面的问题在 C 初始化；
- 明显早于 20 秒的 crashdump/watchdog → 没到 stage 3；
- 没有重启 → 也可能是 PSCI reset 本身不可用，不能反推 MMU 失败。

为此新增一个只验证复位路径的对照镜像（**不写 SCTLR**，只画 stage 1 蓝条，
等待 8 秒后 PSCI 复位）：

| 文件 | SHA-256 |
| --- | --- |
| `out/cheeseburger/boot/boot-psci-control.img` | `b674019d7ed09e1e4e597ecbb2d40d02e091d3412c19ec07aa485b5c299e13b0` |
| `out/cheeseburger/boot/payload-psci-control.img` | `264156038b5795be205292df8714427d0a7cc7a4b2e502f70956081ac9dd2c40` |
| 修改后的内核 `kernel-psci-control.macho` | `b8a08bb17cbffc194c97a8fdbbb8c2941a6c5d22d853f66ecd27c919b4d6643a` |

生成方式（设备仓库）：

```sh
python3 scripts/patch-xnu-entry-probe.py kernel.macho --reset-before-mmu --reset-delay 8
python3 scripts/make-bootimg.py \
  --payload out/cheeseburger/boot/payload-psci-control.img \
  --out out/cheeseburger/boot/boot-psci-control.img
```

判读：

- 约 8 秒后重启 → PSCI reset 可用；stage 3/4 的“无复位”才有诊断意义。
- 不重启或延迟远超 8 秒 → 先修复位路径，不要把“无复位”当成 MMU 失败证据。

复核工具（设备仓库 `scripts/check-kernel-bases.py`）会从 Mach-O 重新计算
`physBase`、2 MiB 对齐和复位延时：

```sh
scripts/check-kernel-bases.py kernel.macho --address 0x1B007C000
# physBase 0x1b2e04000, 2 MiB offset congruent: yes
# reset probes: ... 384000000 ticks 20.000 s
```

## B3 MMU 实测结论（2026-10-23）

**MMU 已过。** 证据不是色带，而是把“复位延时”当成时钟：

| 镜像 | 探针位置 | 延时 | Android 出现 | 反推 kernel_start |
| --- | --- | ---: | ---: | ---: |
| `boot-psci-control.img` | MMU 前 | 8 s | 49.56 s | 未测 |
| `boot-psci-control-30.img` | MMU 前 | 30 s | 71.61 s | 未测 |
| `boot-psci-control-20.img` | MMU 前 | 20 s | 61.73 s | **+52.90 s** |
| `boot-physbase.img` | MMU 后 stage 3 | 20 s | 67.99 s | **+53.42 s** |

- 8 s → 30 s 对照：Android 出现时间相差 22.05 s，正好等于延时差 22 s，
  证明复位由探针控制，不是 watchdog。
- 20 s pre-MMU 对照与 `boot-physbase.img` 的 kernel_start 只差 **0.52 s**，
  说明 stage 3 cave 确实在 MMU 使能后执行并按时复位。
- Android 出现时间（61.73 vs 67.99）受 Android 自身启动速度影响，不能用来判
  MMU；`kernel_start = 主机时间 - /proc/uptime` 才是可靠指标。

因此：

- `PhysicalBase` / `VirtBase` 修正有效；
- 4 KiB bootstrap 页表、TCR/TTBR、SCTLR 切换都已通过；
- 当前卡点移到 **`arm_init` / 第一次 C 初始化**，不是 MMU。

## B3 根因：prelink 段在 bootstrap KVA 映射之外（2026-10-23）

二分链（stage 4 reset-after，10 s 复位；复位=越过该点）：

| 检查点 | 结果 |
| --- | --- |
| `_arm_set_kernel_tbi` 返回 | PASS |
| `_PE_init_platform(FALSE)` 返回 | PASS |
| `_cpu_bootstrap` 返回 | PASS |
| `_arm_vm_init` 返回 | **HANG** |
| `_vm_set_page_size` 返回 | PASS |
| `_arm_vm_prot_init` 返回 | **HANG** |
| 无条件调用 #4 `arm_vm_page_granular_RWNX(segPRELINKTEXTB, segSizePRELINKTEXT, ...)` 之前 | PASS |
| 同一调用返回后 | **HANG** |
| 把该调用 `size` 改成 0 | PASS |
| 把该调用 `size` 改成 4 KiB / 4 MiB / 2 MiB 对齐 | **HANG** |

结论：不是循环次数，而是 helper 访问 `segPRELINKTEXTB` 的第一页就失败。

`start.s` 的 KVA bootstrap 映射从 `VM_KERNEL_LINK_ADDRESS` 开始：

- `VM_KERNEL_LINK_ADDRESS = 0xfffffff007004000`（`__TEXT`）
- 当前 `__PRELINK_TEXT = 0xfffffff00427c000`，在 `__TEXT` **下方** 0x2d88000
- 映射只从 `__TEXT` 向上，`__PRELINK_TEXT` 不在 KVA bootstrap 表里
- `arm_vm_prot_init` 先保护 `__PRELINK_TEXT`，第一次 `arm_kva_to_tte`/TTE 访问就落到未映射页，表现为挂住

因此 `size=0` 能返回；4 KiB 也要访问第一页，照样挂。

进一步实测：

- `mapfix2-stage3`（把 bootstrap KVA 映射起点下移到 `__PRELINK_TEXT`）：
  **PASS**，kernel_start `+53.24 s` → 映射修复本身没有破坏 MMU。
- `mapfix2-prot4`（同样映射修复 + 调用 #4 返回后复位）：**HANG**。

剩余阻塞是 `arm_vm_page_granular_helper` 里的断言：

```c
assert((start - gVirtBase + gPhysBase - pa_offset) >= gPhysBase);
```

当前 `start = __PRELINK_TEXT = 0x427c000`，`gVirtBase = __TEXT = 0x7004000`，
`gPhysBase = Address + 0x2d88000`，代入得到 `Address >= Address + 0x2d88000`，
恒为假。XNU 假定 prelink 段在 kernel link 之上；只修映射不够。

修复方向（需要重建内核，不是再上机二分）：

1. **改 prelink 布局（首选）**：让 `__PRELINK_TEXT`/`__PLK_*` 落在
   `VM_KERNEL_LINK_ADDRESS`（`__TEXT`）之上，并避免与 native `__TEXT_EXEC`/
   `__DATA`/`__LINKEDIT` 重叠；需要原始 iPad7,1 `KernelCache` 与 macOS/CI
   来确认原始段地址和正确的 `slide`。
2. **改 `start.s` + 断言**：映射下移后，还要放宽
   `arm_vm_page_granular_helper` 的 `start >= gVirtBase` 假设；改动更大，
   不推荐先做。
3. 不建议只跳过 `__PRELINK_TEXT` 的保护；后续 kext/绑定仍会访问 prelink 段。

## B3 prelink 布局修复（2026-10-23 晚）

CI run `39951630215`（`macOS build (cheeseburger)`，success）用设备仓库
`07503a9` 的 `slide = "0x4100000"` 重建内核：

| 段 | 地址 |
| --- | --- |
| `__TEXT` / Base / VirtBase | `0xfffffff007004000` |
| `__PRELINK_INFO` | `0xfffffff0082ec000` |
| `__PRELINK_TEXT` | `0xfffffff00937c000` |
| `__PLK_TEXT_EXEC` | `0xfffffff009a20000` |
| `__PLK_DATA_CONST` | `0xfffffff00ada0000` |
| `__PRELINK_DATA` | `0xfffffff00bbdc000` |

所有 prelink 段都在 `__TEXT` 之上，且不与 native 段重叠；Base 与 VirtBase
相同（delta 0）。上机结果：

| 镜像 | 检查点 | 结果 |
| --- | --- | --- |
| `slide-prot4` | `arm_vm_prot_init` 的无条件调用 #4 返回 | **PASS**（kernel_start `+42.93 s`） |
| `slide-vmret` | `_arm_vm_init` 返回 | **PASS**（kernel_start `+45.23 s`） |
| `slide-pe1` | `_PE_init_platform(TRUE)` 返回 | **crashdump `05c6:900e`** |
| `slide-pe1-before` | `_PE_init_platform(TRUE)` 调用前 | **crashdump `05c6:900e`** |

因此崩溃在 `_arm_vm_init` 返回之后、`_PE_init_platform(TRUE)` 调用之前。该窗口
依次调用：

`_PE_consistent_debug_inherit` → `_serial_init` →
`_kernel_startup_initialize_upto` → `_PE_create_console` → `_PE_init_printf` →
`_cpu_machine_idle_init` → `_PE_init_platform(TRUE)`

下一步用 stage 4 检查点逐个测这段窗口；第一个 crashdump 的调用就是新的
阻塞点。设备仍只做 `fastboot boot`，不刷写。

## B3 收尾：XNU 进入 BSD/IOKit（2026-10-23 深夜）

在上面的 prelink 修复之后，又按顺序解决了三个启动阻塞：

1. **BCM2837 panic log 地址错误**：`PE_create_console` 先执行
   `PLATFORM_PANIC_LOG_PADDR=0x3c0fc000`，MSM8998 上无效。
   打开 `CONFIG_XNU_DT_PANIC_REGION=y` 后改走 ADT 的 `pram` 路径（我们的
   ADT 没有 `pram`，安全返回）。CI run `39956257439`。
2. **source corecrypto 的 FIPS POST**：prelink 后 HMAC 失效。改为
   `CONFIG_XNU_CRYPTO_BOOTSTRAP="source"`（CI `39960247193`），并在
   **prelink 之后**用 `scripts/seal-source-crypto-kernel.py` 重新封印。
   `sealed-panic` 的 FIPS 失败消失。
3. **trust cache runtime 过早初始化**：`CONFIG_XNU_TRUST_CACHE_RUNTIME`
   在 `img4if`/`amfi` 注册前调用 `trust_cache_runtime_init()`，panic
   `image4 interface not available @kern_trustcache.c:472`。B3 先关闭
   （CI `39968985568`），留到 B5/B6 做 root/AMFI 时再开。

stage 4 实测（全部 PASS）：

- `_kernel_bootstrap`：`printf`、`scale_setup`、`vm_mem_bootstrap`、
  第二次 `kernel_startup_initialize_upto`、`console_init`、`stackshot_init`、
  `sched_init`、`mac_policy_init`、`machine_init`、`clock_init`、`task_init`、
  `thread_init`、`kernel_thread_create`
- `_kernel_bootstrap_thread` 入口
- `_bsd_init` 入口
- `_IOKitBSDInit` 入口，**以及返回**

结论：MMU、prelink、crypto、DT panic、平台专家、IOKit 初始化都已越过。
普通启动没有可见控制台输出（只有 panic screen 能画），但没有 panic；
下一次阻塞应在 **root device/UFS**（B5）或控制台 `kprintf` 的显示状态。

另外：DarwinBoot 的 `ADT ...` 大标题已从诊断补丁移除；新固件 FD
`6da8ee30…`，无标题镜像 `boot-sourcecrypto-sealed-notitle.img`
`1c25c29a…`。大标题改动保存在
`plans/oneplus5-cheeseburger/patches/darwinboot-virtbase-physbase.patch`；
`drivers/DarwinBoot` 子模块保持干净，重建固件前先 apply 该补丁。

### 普通控制台输出（2026-10-23）

`console_init` 之后普通 `kprintf` 不上屏，但 panic screen 能画。原因是
`initialize_screen(kPEAcquireScreen)` 会 `gc_enable(FALSE)`，把 graphics
console 的 `gc_enabled` 清掉；`console_is_serial()` 因此返回 true。

在 `console_init` 返回后调用 `gc_enable(TRUE)`，普通 XNU 日志立即上屏。
测试镜像 `boot-console-fix.img`（`8d08d3b6…`）实测输出：

```text
standard timeslicing quantum is 10000 us
...
debug_log_init: Error!! gPanicBase is still not initialized
...
Kext com.apple.kec.Libm module start pointer is outside of kext range
  (start 0xfffffff0035b2e - kext starts at 0xfffffff00949b680)
...
lockdown_mode: lockdown mode in nvram is off
```

当前新的阻塞：**`emit_prelink.py` 没有把 `kmod_info` 的 start/stop
（+180/+188）随 slide 写入**，只写了 kmod address（+156）。
`Libm`/`corecrypto` 的 start 仍在 slide 前地址，OSKext 校验范围失败。
修复方向：在 `kits/NativePrelink/emit_prelink.py` 里同时写
`start + slide`/`stop + slide`。上游 `UniXNU/NativePrelink` 只有读权限，
需要在设备仓库放一个同名 kit 覆盖，或走 fork/上游 PR。

已做：

- 设备仓库同名 kit 写 start/stop + slide，并扩展 `kmod_info.size`
  （`aee6b08`，CI `39978443505`）。字段层面 start 已在
  `address..address+size` 内。
- 但 OSKext 仍走 **`LC_SEGMENT_SPLIT_INFO` 的 segment 遍历**，继续报
  `outside of kext range`。
- 试验把 19 个组件的 `LC_SEGMENT_SPLIT_INFO` 改成 `LC_NOTE`：
  内核 panic `kalloc_type_view_parse: No support for non-split seg KCs`
  ——不能去掉 split 信息。

进一步离线核对输出布局：

- `__PRELINK_INFO`：`0xfffffff00833c000..0xfffffff008381000`
- `__PRELINK_TEXT`：`0xfffffff00937c000` 起
- `__PLK_TEXT_EXEC`：`0xfffffff009a20000` 起
- `__PRELINK_DATA`：`0xfffffff00bbdc000..0xfffffff00bd30000`

`arm_vm_init` 在非 fileset 情况下把 `vm_kernel_slid_top` 设为
`vm_prelink_einfo`（`0xfffffff008381000`），因此
`ml_static_slide()` 判定所有组件段（`>= 0xfffffff00937c000`）
**不是 slid 地址并返回 0**；`OSKext::slidePrelinkedExecutable()`
随后把每个组的 segment `vmaddr` 清成 0，导致 start 指针全部越界。
这也解释了为什么 start/address 打印值已经是 slide 后的最终值，
但范围检查仍失败。

修复：`patches/xnu/native-prelink-slid-top.patch` 把
`vm_kernel_slid_top` 扩到 `MAX(vm_prelink_einfo, vm_prelink_etext,
vm_prelink_edata)`，覆盖所有 coalesced prelink 段。已提交
`707fde9`；CI `39987525491` 上机后 **kext 范围错误已消失**，
CoreAnalytics 等 kext 开始真正执行。

新阻塞：`corecrypto` 通过 source-corecrypto 早启动已经调用过
`corecrypto_kext_start()`，prelinked `com.apple.kec.corecrypto`
再次 start 时触发：

```
prng_random.c:267 Assertion failed: !prng_ready
```

修复已合并进设备侧
`kits/NativePrelink/patches/xnu-10063.141.1-security-init.patch`
（避免第二轮构建时 security-init patch 无法 reverse）：当
`source_corecrypto14_status == KERN_SUCCESS` 时，只跳过 prelinked
`com.apple.kec.corecrypto` 的第二次 `startfunc`，仍保留
`OSRuntimeInitializeCPP` 和 started 状态，依赖它的 kext 不受影响。
设备仓库提交 `17dd668`；CI `40056309030` success。

PRNG 修复分两步：

- `patches/xnu/zzz-prng-idempotent.patch`（`29e4e88`）：重复调用
  `register_and_init_prng()` 时直接返回，避免断言。
- source bootstrap 增加 `prng_ready` 早退保护，并合并进
  `source-corecrypto14-bootstrap.patch`（`8c30e45`），避免第二次初始化
  覆盖 prelinked corecrypto 的 PRNG 上下文。

上机 `boot-prng-sourceguard-panic.img`（SHA `400fe389…`）后：

- `prng_random.c` 断言和 `pc=0` 空回调都消失。
- XNU 进入 BSD/IOKit：`CoreAnalyticsHub` start 完成，
  `AppleFSCompressionTypeZlib`、`apfs_module_start`（v2236.140.6）启动，
  `apfs_sysctl_register` 完成。
- 最后停在：

```text
Waiting on <dict ... IOProviderClass IOMedia ...
  Content Apple_APFS>
```

即 **B5：没有 UFS 块设备/IOMedia，APFS 等不到 root**。
`NativeUfs` 目前是 sheng SM8550 版本，`CONFIG_XNU_NATIVE_UFS` 仍未打开；
下一步是 MSM8998 UFS host/PHY/GCC/SMMU 与 root publication 移植。
当前构建还带临时 `zzz-kext-debug.patch`，验证后删除。

### B5 只读 UFS 探针（2026-10-24）

独立 `drivers/NativeUfsProbe` + `native-ufs-probe=20`，只映射
`0x1da4000` 并读 HC 寄存器，不写 MMIO、不提交命令、不碰分区。
上机结果：

```text
NATIVE_UFS_PROBE MSM8998 read-only
hc=0xfffffff7a520f000 cap=1587001f ver=00000210
is=00000400 hcs=0000100f hce=00000001
utrlba=ffffe000 utrldbr=00000000
uecpa=00000001 uecdl=00000000 uecpr=fffff000 uecdme=00000000
```

结论：

- `VER=0x210`：UFS 2.1 HC。
- `HCS bit0=1`：UTRL ready；`HCE bit0=1`：controller enabled。
- UEFI 已把控制器/链路留在可 handoff 状态，**不必先重做 PHY/GCC 初始化**。
- 下一步：handoff 模式复用 firmware 请求列表/SMMU，先做只读 GPT/LUN 探测；
  完整 root 需要 APFS 镜像写入 userdata，属于破坏性操作，必须单独确认/备份。

相关提交：`drivers/NativeUfsProbe`、`d1a4eb6`；截图
`assets/b5-ufs-probe-readonly.jpg`。

### B5 UTRD 命令类型对照（2026-10-24）

上机日志已经把问题缩到 **UFS UTP 请求描述符（UTRD）的命令类型位**：

- UIC `DME_GET` 成功（`get=1 mode=0x11`），`AHIT=0`；
- GCC `0x82028=1`，UFS AGGRE1 AXI 时钟本来就在运行；
- firmware `0xffffe000` 低页写入后回读为 0，cache clean 生效；
- anoc1/anoc2 SMMU 没有启用的 SMR，DT 也没有 UFS `iommus`，暂不按 SMMU
  翻译处理；
- 但 UTP doorbell 后没有完成，且 CPU 读 `UTRLDBR/IS` 会挂住。

对照 OnePlus 5（MSM8998）vendor 内核 `drivers/scsi/ufs` 后确认了当前探针的
结构性错误：**之前沿用 P11 的 `0x10000000`（UTP native UFS，CT=1）发送
SCSI 命令和 NOP，和 Qualcomm Android 代码不一致。**

`ufshci.h`：

```c
UTP_CMD_TYPE_SCSI       = 0
UTP_CMD_TYPE_UFS        = 1
UTP_CMD_TYPE_DEV_MANAGE = 2
UTP_SCSI_COMMAND        = 0x00000000
UTP_NATIVE_UFS_COMMAND  = 0x10000000
UTP_REQ_DESC_INT_CMD    = 0x01000000
UTP_DEVICE_TO_HOST      = 0x04000000
```

`ufshcd_prepare_req_desc_hdr()` 的 DW0 组包：

```c
dword_0 = data_direction | (command_type << 28);
if (intr_cmd)
    dword_0 |= UTP_REQ_DESC_INT_CMD;
```

正确值：

| 命令 | DW0 |
| --- | --- |
| SCSI TEST UNIT READY | `0x01000000` |
| SCSI READ CAPACITY / READ(10) | `0x05000000` |
| NOP OUT | `0x21000000` |

直接证据：UEFI 留在 firmware 请求槽里的 UTRD 是 `05000000/00000000`，即
**SCSI + DEVICE_TO_HOST + INT**，而当前探针 CAP/READ 发的是
`0x10000000 | (2 << 25) = 0x14000000`（CT=1），NOP 发的是 `0x10000000`。
这解释了为什么 firmware 低页、cache clean 和 UIC 都正常时 UTP 仍不完成。

**2026-10-24 上机验证（CT 修正 + OCS-only 轮询 + 4 KiB data）**：
NOP、READ CAPACITY(16)、LBA1 GPT header 和 entries 全部完成。实机输出：

```text
NATIVE_UFS_GPT warm-link read-only
cap=1587001f ver=00000210 is=00000400 hcs=0000100f hce=00000001
queue=ffffe000 ucd=ffffe100 data=187b15000 cap=1000

L0 st=00 last=1c627ff bs=1000
L1 st=00 last=3ff     bs=1000
L2 st=00 last=3ff     bs=1000
L3 st=00 last=7fff    bs=1000
L4 st=00 last=fffff   bs=1000
L5 st=00 last=5ffff   bs=1000

GPT hdr=6bf93f53 ent=2b0de4e9 n=32 esz=128
cur=1 bak=1c627ff usable=6..1c627fa
persist  8-2007       32M
cache    2000-12007   256M
misc     12000-12107  1M
userdata 14f40-1c627fa 115928M
partitions=32 listed=4
```

结论：

- UTRD CT 修正是根因：SCSI 必须 CT=0（CAP/READ `0x05000000`），NOP 必须
  CT=2（`0x21000000`），不能用 P11 的 `0x10000000`。
- 修正后即使 GPT data 在高地址 `0x187b15000`，DMA 也能完成，说明此前
  own-DMA 失败不是高地址不可达，而是错误 UTRD 类型让 UTP 挂死。
- LUN0 为 4096 字节块、最后 LBA `0x1c627ff`；GPT 当前/备份 LBA 为
  `1`/`0x1c627ff`，可用区 `6..0x1c627fa`。
- `userdata` 为 `0x14f40..0x1c627fa`（约 115928 MiB），与主机侧备份
  几何一致。

主机侧 `gpt-primary-sda.bin` 逐项核对：

```text
header_crc=6bf93f53  entries_crc=2b0de4e9
cur=1  bak=0x1c627ff  first=6  last=0x1c627fa  n=32  esz=128
persist  0x8..0x2007
cache    0x2008..0x12007
misc     0x12008..0x12107
userdata 0x14f40..0x1c627fa
```

LUN 容量也与备份 `lun-sizes.txt` 全部一致：

| LUN | 实机 last LBA | 备份字节数 |
| --- | --- | --- |
| 0 | `0x1c627ff` | 121911640064 |
| 1 | `0x3ff` | 4194304 |
| 2 | `0x3ff` | 4194304 |
| 3 | `0x7fff` | 134217728 |
| 4 | `0xfffff` | 4294967296 |
| 5 | `0x5ffff` | 1610612736 |

**B5 只读 UFS/GPT 访问已打通并完成主机备份核对，未执行任何分区写入。**
完整 B5 root 仍需 APFS/userdata 写入（破坏性），必须单独批准并保留当前完整
备份；本阶段到此停止，不发送 WRITE/UNMAP/FORMAT，也不刷写、擦除或修改
任何分区。

### B5 只读 IOBlockStorageDevice / IOMedia（2026-10-24）

在 GPT 探测通过后，把探针扩展为只读 `NativeUfsLun : IOBlockStorageDevice`：

- `NativeUfsLun` 只实现读方向；`doAsyncReadWrite` 对非
  `kIODirectionIn` 返回 `kIOReturnNotWritable`，`reportWriteProtection=true`，
  没有任何 WRITE/UNMAP/FORMAT 命令。
- 使用 IoStorage 的独立 128 KiB DMA 区（实机回退到高地址
  `0x106c02000`），每个 READ10 最多 32 个 4096B 块。
- list/UCD 的 firmware 低页映射提升为 probe 成员，避免 `start()` 返回后
  `OSSharedPtr<IOMemoryMap>` 释放、后续 IOMedia 读盘访问已卸载地址。
- `NativeUfsLun` 的 190 个 vtable 槽位绑定到原始 IOStorageFamily ABI；
  binding 表在设备仓库
  `scripts/data/IOStorageFamily-bindings.json`，生成/校验脚本为
  `scripts/bind-native-ufs-storage.py`。

实机结果：

```text
NATIVE_UFS_GPT: read DMA low failed; high fallback
NATIVE_UFS_GPT: read DMA phys=106c02000 size=20000; publishing LUN0
NATIVE_UFS_GPT: published LUN0 last=1c627ff bs=1000 read-only
NATIVE_UFS_GPT: ring type=05000000 dir=2 bytes=4096
NATIVE_UFS_GPT: done type=05000000 rsp=21/00 tag=1
...（连续 4096B 读）
```

发布后 IOStorageDriver 已匹配并连续读取 4096 字节块，说明只读 block-device
路径已经成立；没有新的 data abort 或 panic。IOMedia 自动创建的日志没有直接
打印出来（快照线程会被同步读盘饿死；第 4 次请求快照为 `total=0`），因此
**IOMedia 存在性只算间接证据，不再继续为打印 IOMedia 反复构建**。

### B5 只读收尾（A，2026-10-24）

决定停止 IOMedia 日志验证循环，冻结 B5 只读里程碑：

- **已验证**：UFS warm-link、NOP/CAP16/READ10、GPT header/entries、6 个 LUN
  容量、LUN0 只读 `IOBlockStorageDevice` 发布、IOStorageDriver 连续 4 KiB
  读、与主机备份的 GPT/容量逐项一致。
- **未直接验证**：IOMedia 自动创建及其 `Content`；root matcher 仍等待
  `IOMedia Content=Apple_HFS`。
- **不视为失败**：当前 LUN0 的 `userdata` 是 Android 分区，不是 APFS/HFS
  根卷；即使 IOMedia 出现，也不会凭空匹配 Apple 根卷。
- **不再做**：为打印 `NATIVE_UFS_MEDIA` 继续构建/启动；继续调快照阈值或
  registry 枚举。该验证投入产出比低，不改变 root 结论。
- **边界**：本阶段全程只读，没有 WRITE/UNMAP/FORMAT，没有刷写、擦除或
  修改任何分区。

下一阶段 B5 root 必须写入 userdata/APFS 根卷，属于破坏性操作；在执行前需要
单独批准、当前完整备份，以及可验证的 APFS 根卷输入。

### B5 root（B：破坏性规划，未执行）

前置条件（当前只完成第 1 项）：

1. 当前系统完整备份存在且已校验：
   `/home/ls/UniXNU/.cache/firmware/backups/20261024-125857/`。
2. 明确批准写入 `userdata`；写入前不得有任何自动刷写/擦除。
3. 有可验证的 APFS 根卷输入（根 UUID、卷结构、与目标 iOS 版本匹配）；
   当前尚未确认这类输入存在。
4. UFS 驱动需要增加受控 WRITE10 路径；现有探针/只读 block device 没有写
   命令，不能直接复用。

计划草案：

1. 校验备份 SHA256，并记录 userdata 当前绝对范围
   `0x14f40..0x1c627fa`、块大小 4096。
2. 在离线环境构建/验证 APFS root 镜像与根 UUID；先做完整回读校验。
3. 增加隔离的写入工具/测试，只允许写 userdata 窗口，禁止其他 LUN/分区。
4. 执行前再次确认备份可恢复；写入后完整回读并比较哈希。
5. 启动 XNU，验证 IOMedia/APFS 根卷匹配和后续 AMFI/Trust Cache。
6. 失败时只使用已校验备份恢复；不重试盲写。

**当前不执行第 2 步以后的任何写操作。** 先确认 APFS 输入与用户批准。

### B5 root 可行性检查（B，2026-10-24）

用户确认：Android 系统是初始状态、没有个人数据，**不需要个人数据备份**；
B5 使用 **iPad7,1 / iPadOS 17.7.11（21H461）** 作为唯一路线。当前系统完整
备份仍保留，作为误写/回滚保护。

只读检查结果：

- 完整备份校验：`SHA256SUMS` 共 84 项，**84 成功、0 失败**。
- 实机 userdata 几何与 `board.toml` 一致：
  `first_lba=0x14f40`、`last_lba=0x1c627fa`、`lba_bytes=4096`。
- 仓库内没有现成的 `userdata-root.img`、APFS 根卷或 SHNGROOT 镜像。
- B5 使用 `board.toml` 的 iPad7,1 / 17.7.11 profile；IPSW/哈希/prelink/ADT
  都以这一份 fixture 为准。
- `NativeUfsProbe`/`NativeUfsLun` 只有 READ10；没有 WRITE10、UNMAP、
  FORMAT 或任何写工具。
- XNU 侧还缺 SHNGROOT 窗口发布/APFS root UUID 匹配；仅写入镜像不会让
  root matcher 自动完成。

第一轮阻塞点：

1. 构建并校验 iPad fixture 的 `userdata-root.img`；
2. 把镜像写入 userdata（需要明确的 fastboot/写入批准）；
3. 在 XNU 侧发布 SHNGROOT 的 OS/SystemOS 窗口，并配置 APFS 根 UUID。

**写入 userdata 是破坏性操作。** 用户已确认无个人数据、无需个人数据备份；
但执行前仍应保留当前系统完整备份，并只写 userdata 分区，不碰其他 LUN/
分区。

### B5 root 挂载成功（2026-10-25）

iPad7,1 / iPadOS 17.7.11 fixture 的 `userdata-root.img` 已写入并校验；XNU
现在能完成 **UFS 窗口发布、APFS 容器挂载、根卷 UUID 匹配**。

关键结果：

- userdata 写入/回读：SHNGROOT `magic=474e4853/544f4f52`，OS/SystemOS
  窗口偏移和 SHA256 全部匹配主机镜像。
- `NativeUfsWindow` 以 512B 逻辑块发布 OS/SystemOS；UFS 侧最多 128 KiB
  合并读。
- 根 UUID 来自 OS APFS 卷：
  `04769D26-2CA0-4825-B443-E2E5F88300F2`，通过 `/chosen/root-matching`
  匹配成功。
- APFS 已打印 `dev_init`/`nx_mount`；根卷挂载完成。
- 最后停点：
  ```text
  rootvp not authenticated after mounting @bsd_init.c:1100
  ```
  这是未封印 restore OS 的 `FSIOC_KERNEL_ROOTAUTH` 拒绝，不是 mount
  失败。

重要回归修复：

- `IODelay`/`IOSleep` 在此内核阶段会永久挂住；UFS NOP/心跳/超时已经全部
  改为 `mach_absolute_time` 忙等或纯轮询。
- 逐条 UFS 命令日志会严重拖慢 I/O；已关闭，仅保留进度/错误/窗口相位。

当前测试镜像：

- `out/cheeseburger/boot/boot-ufsH7-panic.img`
- CI run `40155569182`，commit `drivers: remove timer waits from UFS probe`

下一步（临时 bring-up，非最终安全形态）：

1. 加 boot arg `native-skip-root-auth=1`，仅在 root auth 拒绝时继续；
2. 目标进入 launchd/AMFI，记录下一批用户空间阻塞；
3. 之后用 `VerifiedRoot` 替换旁路，恢复真实 root 认证。

## 下一步

当前（2026-10-26）：

1. **H53 上机**：确认 16 KiB cache 预读 `resid=0`，文件/目录模式正常。
2. 若仍 `no dyld cache`：优先把 SystemOS union mount 到标准路径
   `/System/Library/Caches/com.apple.dyld`，或做 kernel-side bind；
   不要先换 root/cache。
3. 核对 cache mapping/slide 的 4 KiB 可表示性；必要时在 `shared_region`
   里拆分或重映射。
4. `launchd` 稳定后恢复 root auth/AMFI/trust cache，移除 bring-up 旁路。
5. 继续到 `configd`/SpringBoard，记录第一个用户态阻塞。
6. 更新 `STATUS.md` 并提交文档。

## 已完成

- [x] 选定 B 线（UniXNU / 4K），路线固定为 iPad7,1 / iPadOS 17.7.11。
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
- [x] 屏幕日志：RELEASE 也加入 `SerialDxe`，`UNIXNU:` 日志经 `FrameBufferSerialPortLib`（`0x9d400000`）输出到屏幕；`DEBUG` 与 UniXNU 共用同一控制台。
- [x] 删除内嵌 Linux 镜像 `LinuxSimpleMassStorage`（6.9 MiB），压缩 FV 从 2.60 MiB 降到 1.00 MiB，FD 空闲 4.97 MiB。
- [x] 重新构建并打包 b1b boot image（UEFI + UniXNU + 32 MiB payload）。
- [x] 按键输入沿用镜像里已有的 Qualcomm `ButtonsDxe`（depex 依赖 `SimpleTextIn`），不再新增驱动；b1e 实测通过。
- [x] 预检工具 `plans/oneplus5-cheeseburger/tools/check-cheeseburger.py`：b1b 全部通过（FD 空闲 4.97 MiB、模块齐全、boot image 无重叠、payload 可读），b1 也通过（3.35 MiB）。

## B3 调试断点（2026-10-22 晚，2026-10-23 已修正）

> **2026-10-23 更新：本节的“卡在 MMU 使能”结论已被对照实验推翻。**
> stage 3 的复位时刻与 20 s pre-MMU 对照一致，说明 MMU 已开；卡点移到
> `arm_init` / 第一次 C 初始化。以下保留为当时的推理记录。

当时的最后结论：stage 2（MMU 使能前）色带出现，stage 3（MMU 后）不出现 → 当时判为内核卡在 **MMU 使能**，不是 `arm_vm_init`。`VirtualBase` 已改为 `__TEXT`（`0xfffffff007004000`），但 `PhysicalBase` 仍指向窗口起点（`__PRELINK_TEXT` 对应的物理地址），两者相差 `VirtBase - Base ≈ 0x2D88000`，MMU 开启后第一条取指就会落到错误的物理页。

已编译但**尚未上机**的修正：

- 固件：`Address + (VirtBase - Base)` 作为 `boot_args->physBase`；FD `b59f2e49b1b0d6d5914310f5c9a9f9df038b51c0fa2d7d5ee124136c1834d69b`
- 镜像：`/home/ls/UniXNU-cheeseburger/out/cheeseburger/boot/boot-physbase.img`（`4847be5f393b1442980bb3e7331718f571f2557e83976f7d499f886c209b6b49`），payload `payload-stage3b.img`（`1d1b8fd4d055a2c6decc2775504abfaa43eb8cdb96799aee6571b29ca1017934`，stage 3 + 8 GiB ADT）
- DarwinBoot 补丁：`patches/darwinboot-virtbase-physbase.patch`（子模块已还原干净；重建固件前先 `git -C drivers/DarwinBoot apply`）

明天的第一步：

```sh
fastboot boot /home/ls/UniXNU-cheeseburger/out/cheeseburger/boot/boot-physbase.img
```

- 约 20 秒后由 stage 3 探针复位 → MMU 已过，换 panic 内核（`payload-ci.img`）继续。
- 没有在 20 秒左右重启 → 看 TTBR/TCR（stage 4 探针 `_set_mmu_ttb`）或 QEMU 隔离。

## B0 备份与存储映射（2026-10-24 重做）

当前系统已由用户重写刷写，2026-10-22 的旧备份无法对应/启动，已删除。
2026-10-24 用 TWRP `3.4.0-1`（`fastboot boot`，未 flash）重新 dump：

`/home/ls/UniXNU/.cache/firmware/backups/20261024-125857/`（gitignored；4.7 GB）

范围：除 `userdata`（约 113 GB）和可重建的 `cache` 外的**全部命名分区**，
包含 `system`、`vendor`、`boot`、`recovery`、`modem`、`persist`、`keymaster`
以及 `sda–sdf` 的主/备 GPT。每个文件都做了尺寸校验；关键分区另外与设备
原始分区做了远程 SHA-256 对比，全部一致。完整清单见目录内 `SHA256SUMS`
和 `partition-sizes.txt`。

| 关键分区 | 大小 | SHA-256 |
| --- | --- | --- |
| `boot` | 64 MiB | `b3f8c0b470c9c9b93a4a8e18ffcdacd104df66eb5e0cdc94fde40b4759325453` |
| `recovery` | 64 MiB | `f6625f1350d8b6655a49cf89edcd93d2a8884886f5fb0863ecaeee66cb4bd2a7` |
| `system` | 3 GiB | `acb4a6217aa4390eb6e2da2f514e93588b6dee83ab918e871d01924b3b4eb892` |
| `vendor` | 1 GiB | `dbe1e60b7de6de93e20fc287a40dfa313a1861151af60a6708a8f1e30f4a3660` |
| `persist` | 32 MiB | `69c67d371854280e6846dc69818cf9c84364a9cae93b8f70ca6f17461872a8ca` |
| `modem` | 110 MiB | `2e89843d24f9aa8c6c9287781482d982f435456b34e0049c93b3c895f0bb7729` |
| `modemst1` | 2 MiB | `e2bcc4531b24e20f1a23988440d3bd9772692ba8e2f7c488c3845123918e9eb2` |
| `modemst2` | 2 MiB | `1fc7abb2e03c498bff273e3ae5a465a1eaf06485b06d5ac8d46f0a35e1d4044d` |
| `keymaster` | 512 KiB | `72283e73c873ffb3421d7866bfa02622906df99730652e419cbfeb0c87a45ada` |
| `abl` / `xbl` / `tz` / `devcfg` / `devinfo` | 4–8 MiB | 见 `SHA256SUMS` |
| GPT 主/备（sda–sdf） | 32 KiB × 12 | 见 `SHA256SUMS` |

UFS LUN / GPT 映射（4096 B 逻辑块）：

| 设备 | 容量 | 内容 |
| --- | --- | --- |
| `sda` | 113.5 GiB | `ssd`、`persist`、`cache`、`misc`、`keystore`、`frp`、`oem_*`、`param`、`reserve1/2`、`config`、**`userdata` `0x14F40..0x1C627FA`** |
| `sdb` | 4 MiB | `xbl` |
| `sdc` | 4 MiB | `xblbak` |
| `sdd` | 128 MiB | `reserve`、`cdt`、`ddr` |
| `sde` | 4 GiB | `rpm`、`tz`、`hyp`、`pmic`、`modem`、`dsp`、`abl`、`boot`、`system`（3 GiB）、`recovery`、`devcfg`、`logdump`… |
| `sdf` | 1.5 GiB | `modemst1/2`、`fsg`、`fsc`、`vendor`（1 GiB）、`reserve3` |

## B3 产物（2026-10-22 首次）

macOS run `39769403554`（kernel + payload 全部通过）：

| 文件 | SHA-256 / 说明 |
| --- | --- |
| `b3/kernel/kernel.macho` | `8ee3ae2db93cf4925d81b3c0063baee4377b816257b7258bdfd727f7865b5b16`（51.6 MB） |
| `b3/payload/payload.img` | `b4755de7117eff6cc13e835e56437a5637c8fba5286702c1752f008cb82d52e7`（64 MiB） |
| ADT `kernel.macho.adt` | `644992b7966577b3ff7d232a9f7d35c75c35ee81a11904628934058a0e95a5dd` |
| `out/cheeseburger/b3/boot-op5-b3.img` | `9c120a0faf0631d806425063e23c929a0905f4f34b5668049bfd13912494061d`（65.4 MiB） |

boot image：kernel `0x10000000`、ramdisk `0x12000000` + 64 MiB、tags `0x18000000`。
内核参数：`-v debug=0x14e boot-progress=2 offline-legacy-gop=1 offline-legacy-unit-scale=1`。
prelink 自动带入了 `ApplePMGR`、`CoreAnalyticsFamily`、`IOReportFamily` 等依赖；B4 再裁。

## B3 首次上机结果（2026-10-22）

`fastboot boot` 接受 65.4 MiB 镜像；UniXNU 菜单自动选 `xnu`，DarwinBoot 日志：

```text
DARWINBOOT: ARM64 va=0xFFFFFFF00427C000 pa=0x1B007C000 args=0x1B4134000 entry=0x1831EC400 owned=0x00000000
DARWINBOOT: video base=0x9D400000 display=1 row=4320 width=1080 height=1920 depth=32
DARWINBOOT: inputs validated; exiting boot services
```

- 内核 Mach-O：`__TEXT` `0xfffffff007004000`，最低段 `__PRELINK_TEXT` `0xfffffff00427c000`；DarwinBoot 用最低段当 `Kernel.Base`。
- 录像里出现绿/蓝/品红三条早期探针色条 → 内核入口代码确实执行；随后设备进入 `05c6:900e` crashdump 并重启，**没到视频控制台，panic screen 没机会运行**。
- `owned=0` 与 ADT 里的 `darwinboot-memory-size=0x80000000` 不一致（ADT 本地解析确认值正确），需要给 DarwinBoot 加诊断打印确认它是没读到还是被清零。
- **已确认**：`boot_args->virtBase` 原先取最低段 `__PRELINK_TEXT`（`0xfffffff00427c000`），而 `__TEXT` 在 `0xfffffff007004000`。改为 `__TEXT` 后，内核不再硬崩进 crashdump，而是挂住——MMU 阶段很可能已通过，卡在更后面的早期初始化。
- 下一层：用 patcher 的 stage 3（MMU 后画条并延时复位）确认 MMU 是否真的开成功，再定位挂住的 symbol。
- stage 3 探针：只有绿/蓝/品红三段，随后挂几秒再重启 → 当时判为未到达 MMU 之后。注意：`payload-stage3b` 的 stage 3 cave 实际是 20 秒后 PSCI 复位（见“B3 探针可信度”）；需要按录像计时重新判读，不能直接沿用旧结论。
- 关键嫌疑：DarwinBoot 的 2 GiB 窗口被分配到物理 `0x18007C000`，而 ADT 的 `dram-size=0xF0000000` 只到 `0x170000000`，窗口在“内核认为不存在”的物理区间；已改为 `0x200000000`（8 GiB）重测。
- 8 GiB 结果：**仍是三段后挂住**，窗口高度不是唯一原因；MMU 仍未过。
- 下一批实验（按成本）：① 把窗口强制到 256 MiB，看能否落在 4 GiB 以下；② 给 `arm_vm_init`/pmap 加早图画点（stage 4 reset-after 符号）；③ QEMU 跑同一内核隔离 prelink/内核问题。
- 256 MiB 结果：低地址候选（`0x9007C000`…）分配失败，回退到 `0x17A...` 的洞，UEFI 抛 `Synchronous Exception at 0x17ABB13E8`；而 2 GiB 窗口落在 `0x18007C000` 时可访问（内核入口色条出现）。
- 结论：窗口物理位置不是 MMU 挂住的根因；`0x17A000000–0x180000000` 是 firmware 内存图的洞（记录给后续）。MMU 挂住需用 stage 4 在 `arm_vm_init` 里二分。

## 本地产物

### b1d（当前固件 + B0 数据采集，2026-10-22）

| 文件 | SHA-256 |
| --- | --- |
| `out/cheeseburger/b1d/boot-op5-b1d-info.img` | `3709f7d2e9c1c7fde4641afd85dcffa0088753d2a4120f17ec73fe6af78650d3` |
| `out/cheeseburger/b1d/MSM8998PKG_UEFI.fd` | `217c48fad447d92c80a10bec867e651f670c0fd102b1bd85c64771b7670a4b86` |
| `out/cheeseburger/b1d/op5-info-payload.img` | `d6442196cee68440282c30e3569f5cba5e2a4b863cdc893f9bb77c6586ad6176` |

固件变化：移除 `TerminalDxe`（它绑定 `SerialIo`，把每行 `ConOut` 在 framebuffer 上重复画一遍）。`CheeseburgerInfo` 只在 `[Components]` 里构建，不进 FV。

同一固件（FD `217c48fa…`）的 payload 变体：

| 镜像 | 用途 | SHA-256 |
| --- | --- | --- |
| `out/cheeseburger/b1e/boot-op5-b1e-keys.img` | 双条目菜单，按键测试 | `a4654ec5be146f34f8211acb852872fbed51e4150e6582f5e69cd0768dac1cd4` |
| `out/cheeseburger/b1f/boot-op5-b1f-check.img` | DarwinBoot `UniXNULoader` 检查 | `3b70f69d2a800a8039ffa1cedb8ac11f976829108dc2a2d4a2145ac55c8af1ce` |
| `out/cheeseburger/b1g/boot-op5-b1g-log.img` | `console = "none"`，验证屏上日志 | `2ca7d5cc019beee441dbe728e59d8bbaafd592060d6fcdc2ce1cbb6131578fe2` |

### b1c（上一版数据采集镜像，已被 b1d 取代）

| 文件 | SHA-256 |
| --- | --- |
| `out/cheeseburger/b1c/boot-op5-b1c-info.img` | `61875356ff4f4264d80c4c287d2c20979f9429293ccd03280ef57c9f240de35f` |
| `out/cheeseburger/b1c/MSM8998PKG_UEFI.fd` | `3b7a4c601506b036d46ed4baaba4ef5e99e9e4e4e90ee4a1fa2b721af17d4bff` |
| `out/cheeseburger/b1c/op5-info-payload.img` | `593f2928e4e0d0bbb73b3589837bbc3b7ab5e1c4349f0745551860ea17f8ac4a` |

### b1b（G1 测试镜像，2026-10-22 重建）

| 文件 | SHA-256 |
| --- | --- |
| `out/cheeseburger/b1b/boot-op5-b1b-safe.img` | `ea89a9c75d193b3216bc731ba60e3c303621f5f743c71c03763755f49eccabc3` |
| `out/cheeseburger/b1b/MSM8998PKG_UEFI.fd` | `3b7a4c601506b036d46ed4baaba4ef5e99e9e4e4e90ee4a1fa2b721af17d4bff` |
| `out/cheeseburger/b1b/op5-payload.img` | `3bc1ded555d0cd787d11c8531d2c2c60658bc4088d2842a68c042046e352b159` |

`boot-op5-b1b-safe.img`：kernel `0x10000000`（`0x1641df` B），ramdisk `0x12000000`（32 MiB），tags `0x14000000`，header v1，page size 2048。

### b1（首个构建，保留作回退）

| 文件 | SHA-256 |
| --- | --- |
| `out/cheeseburger/b1/boot-op5-b1-safe.img` | `d2bd409a29ffdf7e5dca31cd1d896ec330faab4b543bb544b35e7ed5ab72b41c` |
| `out/cheeseburger/b1/MSM8998PKG_UEFI.fd` | `06002711daadb5fac38697341c2a03e9565afaf455cea90f373fd108d53c5221` |
| `out/cheeseburger/b1/op5-payload.img` | `3bc1ded555d0cd787d11c8531d2c2c60658bc4088d2842a68c042046e352b159` |

## FD 空间

- FD 固定 `0x600000`（6.00 MiB），数据区在 `+0x8000`。
- `FVMAIN` 在 FDF 里是 `NumBlocks = 0`（按内容定长），所以构建日志里的 `EFI_FV_TAKEN == TOTAL` 是设计结果，不是“没有余量”。
- 真正的余量在 FD 层。2026-10-22 实测：`FVMAIN_COMPACT` 用 `1,050,320 B`，**空闲 `5,208,368 B`（4.97 MiB）**。
- 复测方法：解析 FD 的 FV 头，累加 FFS 文件大小，用 `0x5F8000 - 已用` 得到 FV 内空闲。

## 已知问题

- **非空 ramdisk 不能用 offset 0**：32 MiB payload 会覆盖内核；设备脚本必须显式设置 ramdisk/tags offset。
- `CheeseburgerBootMemoryDxe` 的 `PcdDeviceTreeStore=0x83300000` **已确认**：payload 卷能挂载说明 DTB/initrd 解析正确。
- UFS 的 6 个 LUN 都会出现在 UEFI 里；B5 必须按容量选主 LUN（116,264 MiB），不能按枚举顺序。
- 删除 `LinuxSimpleMassStorage` 后，`PlatformBootManagerLib` 仍会注册一个指向缺失 FV 文件的 “USB Attached SCSI” 启动项（`ENABLE_LINUX_SIMPLE_MASS_STORAGE` 在 family `.dsc.inc` 里）。`UniXNUDxe` 把 UniXNU 放在 `BootOrder` 首位，正常不会走到它。
- 按键映射已实测：音量上/下 = Up/Down，电源 = Enter。
- 还没有在 OnePlus 5 上实测。

## 待实测

- [x] RAM：**8 GB**（7039 MiB 可用）
- [x] userdata `first_lba` / `last_lba`：`0x14F40` / `0x1C627FA`
- [x] `lba_bytes`：**4096**
- [x] GOP framebuffer：`0x9D400000`，1080×1920，stride 1080，BGRX，`0x7E9000`
- [ ] 触摸 I2C 总线号和地址
- [x] live DTB 的 `PcdDeviceTreeStore` 和 `/chosen/linux,initrd-*`
- [x] `boot-op5-b1*-safe.img` 的 load address 被 ABL 接受
- [x] `ButtonsDxe` 的电源/音量键驱动 UniXNU 菜单（b1e 实测）
- [ ] `UNIXNU:` 日志是否出现在屏幕上

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

- **当前卡点**：`launchd` 已 exec，但 dyld 不使用 shared cache，报
  `Library not loaded: /usr/lib/libSystem.B.dylib (no such file, no dyld cache)`。
- 已排除：cache 文件缺失、嵌套路径错误、`/usr/lib/dyld` 架构/版本错误。
  H49 读到 `491520 B` 的主 cache（magic `dyld`）；H52 读到
  `/usr/lib/dyld` 为 arm64，`platform=2`，`minos/sdk=0x110700`。
- 仍待确认：dyld 是否忽略 `DYLD_SHARED_CACHE_DIR`、4K 内核能否映射
  16K 构建的 cache、以及 cache signature/AMFI 的影响。
- H53 已构建 16 KiB 预读诊断，尚未上机。
- trust cache runtime 仍关闭；root auth/AMFI 仍是 bring-up 旁路。
- DarwinBoot 的 `owned=0` 未解释，暂不影响 BSD/IOKit 阶段。

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
| 2026-10-22 | B1 | 复核 FD 空间（解析 FD 头） | 实际空闲 3.35 MiB；“FVMAIN 100% 满”是 `NumBlocks=0` 的假象 |
| 2026-10-22 | B1 | `SerialDxe` 进 RELEASE + 删除内嵌 Linux | 成功；压缩 FV 1.00 MiB，FD 空闲 4.97 MiB；UEFI `7f34479` |
| 2026-10-22 | B1 | 重建并打包 b1b | 完成；FD `3b7a4c60…`，boot `ea89a9c7…`；待设备实测 |
| 2026-10-22 | B1 | **G1 设备实测** | `fastboot boot` 成功；UEFI 启动，UniXNU 菜单、payload 卷、倒计时均正常 |
| 2026-10-22 | B1 | 诊断程序 `CheeseburgerInfo` 采集 B0 数据 | 8 GB RAM、4 KiB UFS、userdata `0x14F40..0x1C627FA`、GOP `0x9D400000` 1080×1920 |
| 2026-10-22 | B1 | 移除重复的 `TerminalDxe` 控制台 | 成功；新 FD `217c48fa…`，空闲 4.97 MiB |
| 2026-10-22 | B1 | 按键实测（b1e，双条目菜单） | 音量上/下移动高亮，电源键选中；不需要移植 KeyInput |
| 2026-10-22 | B1 | DarwinBoot 协议检查（b1f） | `UniXNULoader` 协议 `Success`；8 个 BlockIo；GOP 1080×1920 stride 1080 |
| 2026-10-22 | B1 | 屏上日志（b1h，`console=none`，600 s） | `UNIXNU:` 行出现在屏幕；`SerialDxe` 方案成立 |
| 2026-10-22 | B1 | **G1 全项通过** | 启动、菜单、payload、按键、DarwinBoot、BlockIo、日志、B0 数据全部确认 |
| 2026-10-22 | B2 | 建立 `UniXNU-cheeseburger` 骨架 | 本地 `a67972c`；board/defconfig/bootimg/check 完成 |
| 2026-10-22 | B2 | 取 iPad7,1 DeviceTree / StaticTrustCache | `unixnu ipsw fetch` range 请求成功；KernelCache 需 macOS 的 LZFSE |
| 2026-10-22 | B2 | MSM8998 ADT 生成器 + 校验 | 生成 13 KiB 树；`check-adt.py` 全项通过；设备仓库 `31f2bf7` |
| 2026-10-22 | B2 | macOS workflow + B3 配置裁剪 | `macos-cheeseburger.yml`；内核先不带 display/boot-progress kit |
| 2026-10-22 | B2 | 推送三个仓库 | UniXNU `main`、UEFI fork `unixnu-cheeseburger`、设备仓库 `main` |
| 2026-10-22 | B3 | 首次 macOS 构建失败 | `BINDM_FORCE_ROOT` 未定义：`c4af0f0` 删了定义和消费代码，漏删设置 |
| 2026-10-22 | B3 | 修复 XNU 补丁并重跑 | `7aa5b33`；workflow run `39765227392` |
| 2026-10-22 | B3 | 第二次失败：GitHub API 403 | `prepare-xnu-source.py` 加 token/重试；`91cf813`；run `39765521269` |
| 2026-10-22 | B3 | 第三次失败：`native_legacy_display_probe` 未定义 | 补丁缺 config 保护；`b741db8`；run `39766641560` |
| 2026-10-22 | B3 | **XNU 4K 内核构建成功** | run `39766641560` 的 Build kernel 8m18s 通过；payload 因缺 sheng 私有 panic 脚本失败 |
| 2026-10-22 | B3 | 关闭可选 panic screen | 设备仓库 `6e4b487`；run `39768255111` |
| 2026-10-22 | B3 | payload 49 MiB 超过 32 MiB 卷 | 卷改 64 MiB，tags 挪到 `0x18000000`；设备仓库 `79f5a27`；run `39769403554` |
| 2026-10-22 | B3 | **kernel + payload 构建通过** | run `39769403554`；本地组装 `boot-op5-b3.img` 并通过预检 |
| 2026-10-22 | B3 | 首次 B3 上机 | `fastboot boot` 成功；设备进入 Qualcomm crashdump 后重启，说明 XNU 执行并崩溃；panic 只显示几秒，没拍到 |
| 2026-10-22 | B3 | 移植 panic screen | 设备仓库 `233f283`；`patch-xnu-entry-probe.py` + `xnu-panic-screen.c` + `Font.h`；run `39771381162` |
| 2026-10-22 | B3 | panic 补丁找不到 `ld.lld` | 工具查找加 Homebrew keg/versioned 回退；本地已对 4K 内核验证补丁成功；`057a378`；run `39772620480` |
| 2026-10-22 | B3 | **首次 4K 内核上机** | 内核入口执行（早期色条），随后硬件级崩溃；未到控制台；DarwinBoot window 读到 0，待插桩 |
| 2026-10-22 | B0 | TWRP 备份 + 存储映射 | 291 MB，16 个分区 + GPT；`persist` 在 sda2，`userdata` sda13；`e83df1d` 修 adb recovery 状态；该旧备份已失效并删除 |
| 2026-10-24 | B0 | **当前系统重新备份（旧备份已删除）** | TWRP 3.4.0-1；4.7 GB，全部命名分区（除 `userdata`/`cache`）+ sda–sdf 主/备 GPT；关键分区远程 SHA-256 一致；`.cache/firmware/backups/20261024-125857/` |
| 2026-10-22 | B3 | CI 流水线首次全绿 | run `39776627855`：kernel + payload（含 panic screen）+ 上传全部成功；payload `551fa561…` |
| 2026-10-22 | B3 | DarwinBoot 窗口诊断 | 临时固件 `cb47dfe6…` 打印 ADT 属性和解析值，待上机读数 |
| 2026-10-22 | B3 | 诊断：ADT 值正确，`WindowSize` 仍 0 | 大字号确认 `darwinboot-memory-size=0x80000000`；强制 2 GiB 仍崩 → 窗口不是根因 |
| 2026-10-22 | B3 | **`VirtualBase` 修正** | DarwinBoot 原先传最低段（`__PRELINK_TEXT`），改为 `__TEXT`；行为从“硬崩进 crashdump”变为“挂住不重启”，MMU 阶段可能已过 |
| 2026-10-22 | B3 | 诊断补丁存档 | `patches/darwinboot-virtbase-physbase.patch`（诊断打印、强制 2 GiB、VirtBase、PhysicalBase 修正） |
| 2026-10-22 | B3 | stage 4 探针 / MMU 定位 | stage 2 出现、stage 3 不出现 → 卡在 MMU 使能；`PhysicalBase` 偏移假设，已编译待测（`boot-physbase.img`） |
| 2026-10-23 | - | 产物归档 + 状态同步 | B3 的 kernel/payload/CI 日志从 `/tmp/opencode` 归档到 `~/UniXNU/.cache/firmware/b3/`（含 `README.md` 哈希表）；下一步收敛为上机 `boot-physbase.img`；未上机 |
| 2026-10-23 | B3 | stage 3 计时复核 + PSCI 对照镜像 | `payload-stage3b` 的 stage 3 实际是 20 秒后复位，旧“几秒”记录需重判；给 `patch-xnu-entry-probe.py` 加 `--reset-before-mmu`，生成 `boot-psci-control.img`（蓝条 + 8 秒复位，不写 SCTLR）；预检通过，未上机 |
| 2026-10-23 | B3 | PSCI 复位路径上机验证 | 8 s 对照 Android 49.56 s、30 s 对照 71.61 s，差 22.05 s ≈ 延时差 22 s；复位由探针控制，不是 watchdog |
| 2026-10-23 | B3 | **MMU 已过** | 20 s pre-MMU 对照 kernel_start `+52.90 s`，`boot-physbase.img` stage 3 `+53.42 s`，差 0.52 s；stage 3 已执行，MMU 切换成功；下一步转 `arm_init` / C 初始化 |
| 2026-10-23 | B3 | stage 4 二分到 `_arm_vm_init` | `_arm_set_kernel_tbi`、`_PE_init_platform(FALSE)`、`_cpu_bootstrap` 均返回；`_arm_vm_init` 不返回；`_vm_set_page_size` 返回、`_arm_vm_prot_init` 不返回 |
| 2026-10-23 | B3 | **根因：prelink 段在 KVA 映射外** | 无条件调用 #4 `arm_vm_page_granular_RWNX(segPRELINKTEXTB, ...)` 返回点不复位；`size=0` 通过，4 KiB/4 MiB/2 MiB 对齐均挂；`start.s` 从 `__TEXT` 向上映射，`__PRELINK_TEXT` 在其下方 0x2d88000，首次 TTE 访问即未映射；需重建内核修 prelink/start.s |
| 2026-10-23 | B3 | 映射修复验证 | `mapfix2-stage3`（KVA 映射起点下移到 `__PRELINK_TEXT`）PASS，kernel_start `+53.24 s`；MMU 仍正常。`mapfix2-prot4` 仍挂，剩余阻塞是 helper 的 `assert(start >= gVirtBase)`：prelink 在 `__TEXT` 下方，断言恒假 |
| 2026-10-23 | B3 | **prelink 布局修复** | 设备仓库 `07503a9`：`slide = 0x4100000`，CI run `39951630215` success；新布局 `__PRELINK_TEXT` `0x937c000` 在 `__TEXT` 之上，无重叠；`slide-prot4` PASS `+42.93 s`，`_arm_vm_init` PASS `+45.23 s` |
| 2026-10-23 | B3 | 新 crash 窗口 | `_PE_init_platform(TRUE)` 返回/调用前均 crashdump `05c6:900e`；崩溃在 `arm_vm_init` 返回后、PE1 调用前；待测控制台初始化窗口 |
| 2026-10-23 | B3 | DT panic region | `CONFIG_XNU_DT_PANIC_REGION=y`；CI `39956257439`；`PE_create_console` 不再访问 BCM2837 `0x3c0fc000` |
| 2026-10-23 | B3 | source corecrypto + 重新封印 | `CONFIG_XNU_CRYPTO_BOOTSTRAP="source"`；CI `39960247193`；prelink 后用 `seal-source-crypto-kernel.py` 重新封印，FIPS POST 通过；`_kmem_crypto_init`/crypto ctx PASS |
| 2026-10-23 | B3 | trust cache runtime 延后 | `img4if`/`amfi` 未注册导致 `image4 interface not available @kern_trustcache.c:472`；关闭 `CONFIG_XNU_TRUST_CACHE_RUNTIME`；CI `39968985568` |
| 2026-10-23 | B3 | **XNU 进入 BSD/IOKit** | `_kernel_bootstrap` 早期、`_kernel_thread_create`、`_kernel_bootstrap_thread`、`_bsd_init`、`_IOKitBSDInit` 入口/返回全部 PASS；普通控制台无输出，panic screen 可用；下一阶段 B5 UFS/root |
| 2026-10-23 | B3 | DarwinBoot 大标题移除 | 删除 `AdtNode` 的 `UnicodeSPrint`/`DiagDraw`；保留小字 ADT 日志；新 FD `6da8ee30…`，无标题镜像 `1c25c29a…`；补丁已提交，子模块干净 |
| 2026-10-23 | B3 | **普通控制台输出恢复** | `initialize_screen(kPEAcquireScreen)` 会 `gc_enable(FALSE)`；在 `console_init` 后调用 `gc_enable(TRUE)`，XNU 日志/panic 均上屏；测试镜像 `boot-console-fix.img` `8d08d3b6…` |
| 2026-10-23 | B3 | **新阻塞：kmod start/stop 未 slide** | 日志显示 `Libm`/`corecrypto` start 指针在 `0xfffffff003…`，kext 在 `0xfffffff009…`；`emit_prelink.py` 只写 kmod address（+156），没有写 start/stop（+180/+188）；需修 prelink kit |
| 2026-10-25 | B5 | **root 挂载成功** | 写入/校验 SHNGROOT userdata；OS/SystemOS 窗口发布；APFS `nx_mount`；根 UUID `04769D26-2CA0-4825-B443-E2E5F88300F2` 匹配；停在 `rootvp not authenticated after mounting @bsd_init.c:1100` |
| 2026-10-25 | B5 | **修复 UFS 定时等待** | `IODelay`/`IOSleep` 会永久挂住；NOP/超时/轮询改为 `mach_absolute_time` 忙等；128 KiB 窗口合并读；镜像 `boot-ufsH7-panic.img`，CI `40155569182` |
| 2026-10-25 | B5 | **root auth bring-up** | 增加 boot arg `native-skip-root-auth=1` 的临时旁路；仅用于继续到 launchd/AMFI，最终替换为 VerifiedRoot |
| 2026-10-25 19:37 | B5 | **修正 boot 镜像打包** | `payload.img` 是 64 MiB FAT，不是 boot image；正确格式必须是 `make-bootimg.py` 生成的 68,564,992 B Android bootimg（UEFI kernel + payload + tags）。H23/H47 均为此格式；直接把 payload 当 bootimg 会停在 OnePlus logo/fastboot |
| 2026-10-25 | B5 | **SystemOS state / 主 cache** | H26：`stage=6 status=0 union=1 dev=/dev/disk4s1 err=0 dyld=8`；H27：主 cache `size=491520 lookup=0 stat=0`，magic `dyld_v1   arm64` |
| 2026-10-25 | B5 | **split cache 完整** | H29/H34：main 491520；`.01`–`.09` 分别 114720768/49152/114229248/229376/115458048/327680/75857920/245760/112934912；`.symbols` 68517856；主头 `cacheType=2 subCacheArrayCount=52 img=624/3354 subtype=1` |
| 2026-10-25 | B5 | **52 个 subcache 预检通过** | H37：使用 arm64 三空格 magic 和每文件 16 KiB pread，`ok=52 fail=0`；H35：主头 `cs=475136+16384==size=491520`、`prot=5/5`、`os=0x110700`、mapping 有效 |
| 2026-10-25 | B5 | **mount / env / ADT 诊断** | H39 `/System/Cryptexes/OS` 与 H40 `.../Caches/com.apple.dyld` 均 ENOENT；H41/H42 改挂 `/System/Library/Caches` 成功。ADT 增加 `/chosen/asmb`（`lp-sip0=0x6f` u64，`lp-sip1=1` u32）；H45 union + asmb 仍未改变 `no dyld cache`，且无 `shared_region`/trust-cache 报错 |
| 2026-10-26 00:18 | B5 | **env / 路径已证实** | H46：`envp=1500 err=0 env0=1400 env='DYLD_SHARED_CACHE_DIR=/System/Library/Caches/System/Library/Caches/com.apple.dyld'`；H47：`eperr=0 estat=0 esize=1792 etype=2`，c0–c4 全部 0 → 嵌套目录及父目录都存在，但尚未验证 `com.apple.dyld/dyld_shared_cache_arm64` 文件本身 |
| 2026-10-26 11:12 | B5 | **H48 launchd 实跑** | 移除 H47 `NATIVE_PATH` panic，保留 `DYLD_PRINT_SEGMENTS=1`；launchd 仍报 `Library not loaded: /usr/lib/libSystem.B.dylib (no dyld cache)`；CI run `40262171826` |
| 2026-10-26 12:09 | B5 | **H49 cache/dyld 文件确认** | `boot-ufsH49-file.img`：嵌套 cache 文件存在，`copen=0`、`csize=491520`、`ctype=1`、magic `dyld`；`/usr/lib/dyld` 存在，`size=937056`、arm64、`ncmds=18`。路径和文件层排除 |
| 2026-10-26 12:22 | B5 | **H50 private region 试验** | `boot-ufsH50-dyldlog.img`：加 `DYLD_SHARED_REGION=private`/额外打印 env；SystemOS mount 失败 `14 @kern_exec.c:8040`，没有拿到 dyld 日志 |
| 2026-10-26 12:42 | B5 | **H51 修 env 槽位** | `boot-ufsH51-private.img`：修正 private-region 的 env 向量槽位；launchd 仍 `no dyld cache` |
| 2026-10-26 13:27 | B5 | **H52 dyld 身份** | `boot-ufsH52-dyldver.img`：`/usr/lib/dyld` `magic=feedfacf`、`cputype=0x0100000c`（arm64）、`platform=2`、`minos/sdk=0x110700`、UUID `3b1e2a…`；架构/构建版本基本排除 |
| 2026-10-26 13:49 | B5 | **H53 16K 预读诊断** | `boot-ufsH53-16k.img`（SHA `fad6304c…`）：已上机，`cerr=0 cstat=0 copen=0 cread=0 resid=0 size=491520`；16 KiB pread 正常，数据读取层排除；`mode`/`dirmode` 因 panic 格式 `%o` 未显示 |
| 2026-10-26 | B5 | **H54 全 mapping 预检** | `boot-ufsH54-map.img`：`NATIVE_H54: ok=52 fail=0 main=512/1/491520 mc34=2 lmax34=1 mc52=2 lmax52=1`；52 个 subcache 的 mapping、连续性、重叠、TEXT/LINKEDIT 权限全部符合 dyld `preflightCacheFile`，mapping 候选排除 |
| 2026-10-26 | B5 | **H55 env/AMFI 首次验证** | `dyld_flags=0xA` + `DYLD_AMFI_FAKE=0xffffffff` + `DYLD_PRINT_TO_FILE=/dev/console`；仍无 dyld 日志、无 `NATIVE_CACHE_SIG`，final error 不变 |
| 2026-10-26 | B5 | **H58 env 栈证据** | `NATIVE_H58: argc=1 envc=8 cache=1 amfi=1 print=1 env=/System/Library/Caches/System/Library/Caches/com.apple.dyld`；env 确实进入新进程栈，排除“dyld 没拿到 env” |
| 2026-10-26 | B5 | **H59 devfirm/internalInstall** | dyld 的 iOS `internalInstall()` 读 commpage `_COMM_PAGE_DEV_FIRM`，不是 `os_variant`。H59 强制该位为 1，使 `DYLD_AMFI_FAKE`/testMode 真正生效；移除 H58 panic 和 os_variant 补丁 |

## H60–H79 用户态突破记录（2026-10-26/27）

| 阶段 | 结果 |
| --- | --- |
| **H60** | 用 launchd 进程的 `vfs_context` 直接 lookup/open nested cache：`dir=0/0 dmode=0x41ed file=0/0 fmode=0x81ed size=491520`。证明路径和权限层正常。 |
| **H61** | 用 bindfs 把 `SystemOS/System/Library/Caches` 叠到 `/System/Library/Caches`；仍未加载 cache。bindfs 不是最终方案。 |
| **H62** | 改挂 SystemOS 到 `/private/preboot`，启用 `XNU_OWNER_CACHE_CARRIER=1`；路径符合 `offline-owner-cache-carrier` 的 canonical 目录，但仍无 cache。 |
| **H63** | 加 `early_security_init=com.apple.driver.AppleMobileFileIntegrity=0xfffffff005ab4ae0`；prelink 接受，AMFI early init 运行，但仍无 cache。 |
| **H64** | 试 `amfi_get_out_of_my_way=0x1`、`amfi=0x80`、`DYLD_AMFI_FAKE=0x7f`；仍无。 |
| **H65** | `platform=2 min=110700 sdk=110700`，`argc=1 envc=8 cache=1 amfi=1 print=1 env=/private/preboot/System/Library/Caches/com.apple.dyld`；平台/env 排除。 |
| **H66/H67** | 主机确认实际 `/usr/lib/dyld` 含 `DYLD_SHARED_CACHE_DIR`/`DYLD_AMFI_FAKE`/`DYLD_PRINT_ENV`，937056 B；launchd 也是 platform 2。H67 open trace：`dir=-2 path=/private/preboot/... ->0`、`dir=1 path=dyld_shared_cache_arm64 ->0`、`F_ADDFILESIGS_RETURN cmd=0x61`；cache 已真正打开并进入 preflight。 |
| **H68/H69/H70** | 真实 fcntl 被 AMFI 拒绝：`cache ... is adhoc signed`、`unsuitable CT policy 0`。H69 恢复 `amfi=0x94` 无效；H70 的 `MAC_VNODE_CHECK_DYLD_SIM` 也无效。 |
| **H71/H72/H73** | H71 忽略 MACF 拒绝继续 attach blob，但报 `disallowing unsupported code signature page shift: 14`（4 KiB 内核 vs 16 KiB cache 签名）。H72 启用 `XNU_NATIVE_CS_HASH_CACHE=1` 未生效，因为 `ubc_subr.o` 的 CFLAGS 被重复覆盖；H73 合并 `-DXNU_NATIVE_CS_HASH_CACHE` + `-DXNU_NATIVE_CACHE_SIGNATURE_BYPASS` 后 page-shift 消失。 |
| **H74/H75** | H74 去掉 dyld_sim flag，仍 `first page not mmap()able`；H75 加 `CS_PLATFORM_BINARY`，mmap 仍被 AMFI 拒绝。 |
| **H76** | 在 `kern_mman.c` 忽略 `mac_file_check_mmap` 的 MACF 错误；**shared cache 首次成功映射**：dyld 日志出现 `Using mapping in dyld cache for /usr/lib/swift/libswiftDarwin.dylib` 等；随后 `Setting up kernel page-in linking for /sbin/launchd` 并出现 `userspace stack not initialized` panic。 |
| **H77** | `dyld_flags=0x8A`（加 0x80 disablePageInLinking）；page-in linking panic 消失，但 launchd 退出：`pid 1 exited -- exit reason namespace 1 subcode 0x7`。namespace 1 = JETSAM，subcode 7 = `JETSAM_REASON_MEMORY_PERPROCESSLIMIT`。 |
| **H78** | 把 `owned_memory_size` 从 2 GiB 提到 4 GiB；仍是同一个 per-process jetsam，不是物理内存总量。 |
| **H79（待确认）** | 把 `DYLD_SHARED_REGION=private` 改为 `system`，避免 1.5 GB cache 计入 launchd 的单进程内存上限；CI `40517795790` 成功，镜像 `boot-ufsH79-system.img` 已生成/启动，**结果尚未确认**。 |

### 当前生效的临时 bring-up 配置

- 主仓：UniXNU `949d1a0`；设备仓：UniXNU-cheeseburger `67dda64`。
- SystemOS 挂载点：`/private/preboot`。
- `XNU_OWNER_CACHE_CARRIER=1`、`XNU_NATIVE_CS_HASH_CACHE=1`、`XNU_OWNER_CACHE_STARTUP=1`。
- `DYLD_SHARED_CACHE_DIR=/private/preboot/System/Library/Caches/com.apple.dyld`。
- `dyld_flags=0x0000008A`（testMode + skipIgnition + disablePageInLinking）。
- `DYLD_SHARED_REGION=system`（H79 起；H77/H78 是 private）。
- `DYLD_AMFI_FAKE=0x7f`；`amfi_get_out_of_my_way=1`、`amfi=0x94`、`amfi_allow_any_signature=1`、`cs_enforcement_disable=1`、`native-skip-root-auth=1`、`native-skip-exec-signature=1`、`launchd_unsecure_cache=1`。
- 临时签名/mmap bypass：`zzz-cache-signature-bypass.patch` 忽略 MACF signature/mmap，设置 `CS_VALID|CS_SIGNED|CS_PLATFORM_BINARY`；最终必须移除。
- `panic_screen=false`：新增诊断代码占用了 `patch-xnu-entry-probe.py` 的固定 panic cave；H77–H79 用普通内核控制台输出。最终要恢复。
- CI 临时改用 `macos-15-intel` + Xcode 26.3 + `-Wno-unknown-warning-option`，因为 macOS 26 runner 容量长期排队；最终要恢复 `macos-latest`/Xcode 26.6。

### 主机侧只读确认

- OS APFS 窗口已只读挂载于 `/tmp/opencode/mnt-os`。
- `/usr/lib/dyld` 实际 937056 B，包含 `DYLD_SHARED_CACHE_DIR`、`DYLD_AMFI_FAKE`、`DYLD_PRINT_ENV`。
- `/sbin/launchd` `LC_BUILD_VERSION platform=2 minos/sdk=0x110700`。
- `/private/preboot` 和 `/System/Library/Caches` 在 OS root 存在；`/System/Library/Caches/com.apple.dyld` 在挂载前不存在。

### 下一步（历史 H79 条目，已被下方 H80–H82 记录取代）

- H79 的 per-process jetsam 已在 H81 通过 system-wide shared region 绕过；
  当前问题已变成 H81 的 `OS_REASON_LIBXPC` assertion 和 H82 的 Data skeleton 构建。
- 详细顺序见“H80–H82 记录”末尾。不要删除 `lock_rw.c` 的 panic assertion；修 caller。

## H80–H82 记录（2026-10-28）

### H80：private cache + PID1 footprint

- 回到 `DYLD_SHARED_REGION=private`，在 `native_owner_cache_prepare()` 里调用
  `task_set_phys_footprint_limit_internal(proc_task(p), -1, ...)`。
- `-1` 实际会回落到 `max_task_footprint`，不是无限；H80 仍出现
  `pid 1 exited -- exit reason namespace 1 subcode 0x7`，即
  `JETSAM_REASON_MEMORY_PERPROCESSLIMIT`。
- 结论：private cache 把约 1.5 GB cache 计入 launchd 的 per-process footprint，
  单靠 PID1 的 task limit 清理没有解决。
- H80 镜像：`boot-ufsH80-tasklimit.img`，CI `40526638185`，sha256
  `c6d32463b84d05392325b61c3bb92e1a2d5fd0a1ffca832710a74d96dd9920de`。

### H81：system-wide shared cache 成功

- 改回 `DYLD_SHARED_REGION=system`。
- `vm_shared_region_start_address()` 的 “failed” 只是共享区为空时的正常提示；
  真正失败点是 `shared_region_map_and_slide_np()` 的 AMFI/CS 检查。
- 新增 `zzz-shared-region-cache-bypass.patch`：
  - 在 `bsd/vm/vm_unix.c` 的 `mac_file_check_mmap()` 上临时忽略 AMFI；
  - 对共享区映射的 `ubc_cs_is_range_codesigned()` 检查临时放过；
  - 打印 `NATIVE_H81_SR: setup/root check/preboot/map_file` 诊断。
- `vm_unix.o` 增加 `-DXNU_NATIVE_CACHE_SIGNATURE_BYPASS=1`。
- **H81 上机结果：system-wide cache 映射成功，launchd 不再被 jetsam 杀掉。**
- H81 镜像：`boot-ufsH81-shared-region.img`，CI `40688172208`，sha256
  `4fdf7e8baf2986e61e2f64345172916d27313b6adda7e7d0609c7799cb85317d`。
- 但 launchd 很快以
  `pid 1 exited -- exit reason namespace 7 subcode 0x1`
  退出；namespace 7 = `OS_REASON_LIBXPC`，描述为
  `assertion failed: 992399: launchd + 338744 [48525932-8C69-315E-A51A-CC943E4E5051]: 0x1`。
- 结合 launchd 依赖 `/private/var/db/com.apple.xpc.launchd`、`/private/var/tmp`、
  `/private/var/run`，判断为 **没有可写 Data 卷 `/private/var`**，进入 H82。

### H82：Data skeleton + fork RamBlock（已构建，启动返回 fastboot）

- 新增 `prepare-owner-data-fixture.py --skeleton --size-mib 64`：
  - CI 上用 `hdiutil` 创建 64 MiB APFS Data skeleton；
  - 只创建 `/private/var` 所需目录（`db`、`db/com.apple.xpc.launchd`、`log`、
    `run`、`tmp`、`keybags`、`mobile/*`、`containers` 等），不复制 OS 的 400+ MB var；
  - 输出 `build/owner-data-fixture/seed.json` 和 `owner-data-32.cdr`；
  - workflow 从 `seed.json` 取 `volume_uuid`，写入 `XNU_OWNER_DATA_VOLUME_UUID`。
- board payload 当前为 76 MiB；payload 加 `--data-ramdisk`。
- 临时内核配置：
  - `XNU_OWNER_DATA_MOUNT=1`
  - `XNU_NATIVE_RAM_BLOCK=1`
  - `XNU_OWNER_BOOT_MANIFEST=0`（仅为当前 volatile Data bring-up）
  - `XNU_OWNER_CACHE_MOUNT=1`、`XNU_OWNER_CACHE_STARTUP=1`、
    `XNU_OWNER_CACHE_CARRIER=1`、`XNU_NATIVE_CS_HASH_CACHE=1`
- 构建失败与修复：
  1. `40693595648`：bootstrap pass 被
     `NativeRamBlock requires the qualified original storage/AES prelink closure`
     挡住。已在 bootstrap pass 关闭 `XNU_NATIVE_RAM_BLOCK`，并给 volatile Data
     加临时豁免。
  2. `40695589323`：最终链接缺 `native_ufs_store_*` 和
     `native_verified_block_manifest_sha384`。已临时关闭 boot manifest；store
     符号改为在 fork 的 `RamBlock` 子模块里提供 weak no-op fallback，不再放进
     XNU `kern_exec.c`。
  3. `40699122544`：CI fetch XNU 网络超时，与代码无关。
  4. `40701763118`：owner patch 插入 weak stubs 后 hunk 行数未更新，
     `corrupt patch at ...:345`。本地已重算 hunk 计数并提交，**尚未重新构建**。
- **H82 构建成功：** CI `40712047295`，payload 160 MiB，镜像
  `boot-ufsH82-data.img`，sha256
  `5069bad1f910d753e3b8c6bd8220ce29e5a7c445ddf58f475cdcd5f4320d00a1`。
- **H82 启动结果：** `fastboot boot` 接受并显示 `Booting OKAY`，但 30 秒后设备
  又回到 fastboot；尚未看到 UEFI/内核屏幕。可能是 160 MiB ramdisk 与 Android
  tags 的布局问题，或 UEFI/DarwinBoot 对 tags 地址的假设；Data/launchd 尚未验证。
- 为避开 160 MiB payload 与 `tags_offset=0x08000000` 重叠，本次镜像把 tags
  移到 `0x0c000000`（绝对地址 `0x1c000000`）；这本身也可能是启动失败原因。

### 当前临时配置（H81/H82）

- `DYLD_SHARED_REGION=system`。
- `XNU_OWNER_DATA_MOUNT=1`；当前 16 MiB APFS Data skeleton；`/private/var` 可写。
- `XNU_NATIVE_RAM_BLOCK=1`，无 NativeUfs 持久化；store fallback 为 fork
  `lss717/RamBlock`（submodule `drivers/NativeRamBlock`，提交 `bc079a5`）里的
  weak no-op。
- 主仓 `.gitmodules` 的 `drivers/NativeRamBlock` 已改指
  `https://github.com/lss717/RamBlock.git`；submodule 本地 `origin` 指 fork，
  `upstream` 指 `UniXNU/RamBlock`。
- `XNU_OWNER_BOOT_MANIFEST=0`：**当前 Data 未经过 authenticated owner boot manifest**。
- `max_task_pmem=0`：全局 task footprint 上限临时移除。
- `zzz-cache-signature-bypass.patch` + `zzz-shared-region-cache-bypass.patch`：
  AMFI/cache/CS/mmap 的临时 bring-up bypass；最终必须移除。
- `panic_screen=false`：固定 panic cave 被诊断代码占用；最终恢复。
- CI 仍为 `macos-15-intel` + Xcode 26.3；最终恢复 macOS 26 / 正常 runner。

### 下一步（按顺序）

1. 确认 H82 启动失败发生在哪一层：先看屏幕/UEFI 日志；若仍回 fastboot，
   优先怀疑 tags 地址或 160 MiB ramdisk 的装载布局。
2. 回退到 H81 镜像验证设备仍可进入内核；再试更小的 32/64 MiB Data seed，
   保持默认 `tags_offset=0x08000000`，或修正 UEFI/DarwinBoot 的 tags 处理。
3. 启动成功后观察 Data mount 是否通过、launchd 的 `namespace 7 subcode 0x1`
   是否消失；若 Data mount 失败，看
   `offline scratch Data mount failed: <errno>`、seed UUID、RAMDisk handoff。
4. 若 launchd 继续，进入 watchdog/tzinit、launchd job、`/private/var/db` 初始化。
5. 最终恢复 `XNU_OWNER_BOOT_MANIFEST=1`、VerifiedRoot/AMFI/TrustCache；
   用 qualified NativeUfs/AES store 替换 fork 里的 weak no-op fallback，并移除
   Data skeleton、AMFI/CS/mmap bypass、`panic_screen=false`。

### H82b–H82f 结果（2026-10-29）

| 镜像 | 配置 | 大小 | 结果 |
| --- | --- | --- | --- |
| `H82b` | 32 MiB seed / 96 MiB payload / 默认 tags | 102,119,424 B | fastboot，未进 UEFI |
| `H82c` | 同 payload / tags=`0x1c000000` | 102,119,424 B | 曾到 OnePlus 第一屏，UEFI 未起；重试不稳定 |
| `H82d` | 手工 90 MiB payload（32 MiB seed）/ 默认 tags | 95,827,968 B | fastboot |
| `H82-kernelonly-64` | H82 内核、无 Data seed、64 MiB payload | 68,564,992 B | **进入内核**，panic `offline scratch Data mount failed: 2` |
| `H82e` | 8 MiB seed / 64 MiB payload | 68,564,992 B | **进入内核**；launchd 仍 `namespace 7 subcode 0x1`；Data 状态未知 |
| `H82f` | 16 MiB seed / 76 MiB payload | 81,147,904 B | 已启动，未回 fastboot；等待屏幕 |

结论：

- H82 内核、fork RamBlock、UEFI/ADT 都能工作；`kernelonly-64` 已证明。
- 98 MiB / 95.8 MiB boot image 不能稳定启动；68.56 MiB 可以。77.4 MiB 正在验证，
  bootloader 上限大致在这两者之间。
- `H82e` 的 launchd assertion 与 H81 完全相同；8 MiB Data 可能未成功挂载，或
  容量/骨架不足，需要在 H82f 看新增的 `NATIVE_H82_DATA`。
- `H82f` 的状态行会打印：
  `NATIVE_H82_DATA: status=<errno> stage=<n> ro=<0/1> dev=<dev> size=<bytes>`。
  `status=0, stage=4, ro=0` 才表示 Data 挂载成功。

镜像：

- H82e：`boot-ufsH82e-8m.img`，sha256
  `5a83b98c565826912e9d92bf61256cbf06f89b07824608c72f5d6b97e100a8cc`
- H82f：`boot-ufsH82f-16m.img`，sha256
  `e636336d8e7cb9aec9ab6fbc5ce1ebfeaf757f0d5cff227e8ee143ecba300038`
- H82f CI：`40797926609`；Artifact `12864254042`。

### fork 接入

- 上游实际仓库：`UniXNU/RamBlock`（旧 `NativeRamBlock` URL 重定向）。
- fork：`lss717/RamBlock`，提交 `bc079a5`
  （`ram: provide weak volatile-store fallbacks`）。
- 主仓路径保持 `drivers/NativeRamBlock`；`.gitmodules` URL 改为
  `https://github.com/lss717/RamBlock.git`。
- 子模块 `origin` 指 fork，`upstream` 指 `UniXNU/RamBlock`。
- `NativeRamBlock` 的 weak no-op store fallback 已在 fork 中，不再放在 XNU
  `kern_exec.c`。
- device 仓库补了 base `IOBlockStorageDevice` 绑定：
  `27a6e70 storage: bind base IOBlockStorageDevice metadata`。

### H82f 之后

1. 等 H82f 屏幕，读取 `NATIVE_H82_DATA`。
2. 若 `status=0 stage=4`，launchd assertion 就不是 Data 挂载本身；继续查
   `/private/var/db`、bootstrap、libxpc。
3. 若 Data mount 失败，优先看 errno、seed UUID、16 MiB APFS 容量。
4. 若 77.4 MiB 启动不稳定，回退 68.56 MiB 尺寸，另找 Data 持久化/外置方案。
5. 最终恢复 `XNU_OWNER_BOOT_MANIFEST=1`、VerifiedRoot/AMFI/TrustCache，
   替换 weak UFS fallback，移除 bypass。


### H82g–H83c：launchd `namespace 7` 逐项排除（2026-10-29/30）

已用临时 `fastboot boot` 验证，均未写分区：

| 候选 | 配置 | 结果 |
| --- | --- | --- |
| H82j | 256 MiB packed Data | core dump ENOSPC，launchd 仍 `namespace 7 subcode 0x1` |
| H82k | sheng watchdog/job policy | 同 |
| H82l | `cpus=1` + 关闭 core + launchd 退出寄存器 | 同；`cpus=1` 无效 |
| H82m | 只加 StaticTrustCache | AMFI 仍报 adhoc，launchd/dyld 被 SIGKILL |
| H82n | `UNION_SYSTEMOS=1` | 同 |
| H82o | abort 入口打印描述/栈 | `assertion failed: 992999: launchd + 338744 [4B525992-...]: 0x1`，ns=7 code=0x1 |
| H82q | Static+System 完整 trust bundle | AMFI 仍 adhoc/CT policy 0 |
| H82r | 全线程 PC/帧 | abort 线程 tid=243，245 已 `pc=0`，主线程现场丢失 |
| H82s | 去 `launchd_unsecure_cache`/`dyld_flags`/lite | 同 |
| H82v | 1 GiB Data + 1 GiB window | 同 |
| H82w | 最小 AMFI 绕过 | 同 |
| H82x | `XNU_OWNER_DATA_MOUNT=0`、无 NativeRamBlock/Data | 同，Data 不是原因 |
| H83a | `XNU_TRUST_CACHE_RUNTIME=1` + 完整 trust | 未触发 AMFI/Image4 缺失 panic |
| H83b | `load_static_trust_cache` 缺 range 即 panic | 未触发，旧固件确实交付了 TrustCache range；但 AMFI 仍 adhoc |
| H83c | H83b + `amfi=0x94` | 同 |
| H83d | H83b + ADT `amfi-only-platform-code=0` | 同；AMFI 仍 adhoc/CT policy 0 |

关键文件/事实：

- 原始 `/sbin/launchd` 已从 21H461 OS DMG 提取，sha256
  `8cec9a3c44a443b08e977ccc5d577850316ad428c575dc01f09b018dbd5b6a25`，
  UUID `4B525992-8C69-315E-A51A-CC9433E45B51`，与 panic 描述一致。
- 完整 static+system trust bundle sha256
  `7416ca4f8377146626bb284e2133c76bee6cb4e3ee0af5d648b186235a7323a7`，
  与 DinnerABC 原始 bundle 一致；`audit-target-userspace.py` 可验证 launchd/dyld
  cdhash 在 StaticTrustCache 中。
- H82r 的 launchd 栈只含 libxpc/exit；主线程在 abort 前已退出。
  `launchd + 338744` 是 Swift error thunk，单独不能定位原始 XPC 调用。
- 新固件（当前 `drivers/DarwinBoot` 重新构建）不可用：RELEASE 报
  `Out of Resources`，随后 `Synchronous Exception at 0x...17A0B1258`；旧固件
  已恢复为测试基线。旧固件能给 kernel 提供 TrustCache range，但 AMFI 仍把
  launchd/dyld 判为 adhoc；不要重复把新固件当作已验证候选。
- 已排除：`cpus=1`、SystemOS union、Data mount、1 GiB Data/内存窗口、
  `launchd_unsecure_cache`、`dyld_flags`、AMFI 参数组合、lite policy；
  H83d 也排除了 `amfi-only-platform-code=0`。

下一步（仅剩高价值方向）：

1. 对照 DinnerABC 的 `patches/p10` AMFI/Image4/TrustCache 与 `amfi.c`/
   `interface.c` 注册路径，确认我们的 AMFI 是否真正把 loaded TrustCache 用于
   cdhash 查询；当前 `amfi`/`img4` 非空、range 存在，但 AMFI 仍拒绝。
2. 修复新固件 FV/UniXNU 的 `Out of Resources`/UEFI exception，才能重测
   TrustCache 侧车；旧固件只可作为绕过基线。
3. launchd Swift 主线程在 abort 前退出的现场仍缺失；在拿到真实 AMFI trust
   路径前，继续加 boot args 不会改变 `namespace 7`。


### H83g–H84b：launchd 突破与新的 UFS 读阻塞（2026-10-30）

关键突破：`namespace 7 subcode 0x1` 不是 Data/CPU/union/AMFI 参数导致的，而是
`startup.c` 里的 TrustCache 初始化被 `XNU_NATIVE_TRUST_CACHE` 条件编译掉了；
`load_static_trust_cache()` 从未执行。

- `patches/xnu/native-trust-cache-runtime.patch` 已改为无条件执行
  `trust_cache_runtime_init()` + `load_static_trust_cache()`。
- H83g 在入口 panic 证明函数执行：`amfi` 非空、`TrustCache.version=53`。
- H83h 放开入口后，launchd 真正运行并打印
  `com.apple.xpc.launchd ... Doing boot task`，`namespace 7` 消失。
- H83j 在 ADT `/chosen` 加入 48 字节 `boot-manifest-hash` 占位后，
  `mount-phase-1/2`、`data-protection`、`keybag`、`usermanagerd` 等 boot task 通过。
- H83j 新首错是 `tzinit` 找不到 `/private/var/db/timezone`（exit 22）。
- H83k 把原 OS 的 `/private/var/db/timezone` 注入 256 MiB packed seed
  （UUID 不变，encoded sha256 `e94a0683...`）；`tzinit` 不再 panic。
- H84a 启用 `XNU_NATIVE_MOBILE_DISPLAY=1`；H84b 仅把 payload 改成 `cpus=8`。
  两者都停在 `NativeUfsProbe` 的 UFS 读进度：最后一条 `OS req=...` 没有 `done`，
  `winBytes` 约 3.1 GiB，`winFlight=1`。这不是“写盘”，是 launchd/用户态读取
  SystemOS/OS 时的一个 UFS 请求没有返回；display 尚未真正执行。

当前可用镜像/哈希：

| 镜像 | sha256 | 说明 |
| --- | --- | --- |
| H83h | `de61bce881d355bcb0ed68b6363f20887b17726708c46e59e2f16d58b499f6d9` | launchd 首次越过 namespace7；无 Data |
| H83j | `5086999bb9dcf6489b65c6f863e5660097dad9568e39a1ef642ec7038ee47207` | mount/manifest 占位通过；tzinit exit22 |
| H83k | `54ba38bb291cb1637c8da702ade288696ea4c1afddea008f192be1f66a1771f3` | 补 timezone；tzinit 通过；UFS 读停住 |
| H84a | `d922af097dd71250adfe6522c4cfcc5edda3688ef69052084ba80a353e786254` | + NativeMobileDisplay；UFS 读停住 |
| H84b | `a811fec2fc9c6c56759c8eaae55803c0a4206269a38012cc96c69a6884c1ac20` | + cpus=8；UFS 读停住 |
| H85c | `6a7e83ac9554e5c486c85ac4f656f60ab974cbda8860af2bbb90ade6ffb55296` | 实际仍是 NativeUfsProbe；UFS 大读停住 |
| H85g | `c21a87c58fc9d1ed51643795d37023548a3593893702c58f23a005e3b2dbdfab` | personality 写成 NativeUfs，但 class 未链接；启动报 `Couldn't alloc class "NativeUfs"` |
| H85h | 无最终镜像 | 清 `build/xnu` 后 bootstrap 正常产出记录，但外层误带 `XNU_BOOTSTRAP=1`，最终链接仍按 bootstrap 模式失败 |
| H85i | 无最终镜像 | `.config` 修好后首次真正链接 `libNativeUfs.a`；暴露 VerifiedRoot/IOStorageFamily 依赖 |

### H85g–H85h 根因：`.config` 陈旧，配置从未生效

H85g 的 `KernelConfigTables` 已经显示 `IOClass = NativeUfs`，但 `nm kernel.macho`
只有 `NativeUfsProbe` 的 class 符号，没有 `NativeUfs`。根因不是补丁，也不是 archive：

- `unixnu` 构建时读取的是 `out/cheeseburger/.config`，不是
  `configs/cheeseburger_defconfig`；该 `.config` 停留在 10 月 29 日。
- 因此 `xnu_env()` 实际导出 `XNU_NATIVE_UFS=0`、`XNU_NATIVE_UFS_PROBE=1`，
  覆盖了 `run-h82-build.sh` 里的同名 export。
- 结果：personality 被临时补丁强制为 `NativeUfs`，但链接器只 force-load 了
  `libNativeUfsProbe.a`，`libNativeUfs.a` 从未进入内核，启动即
  `Couldn't alloc class "NativeUfs"`。
- H85h 另外把 `XNU_BOOTSTRAP=1` 带进了最终 pass，导致最终链接仍跳过 archive。

修复（H85i 起点）：先执行 `./unixnu defconfig cheeseburger_defconfig` 重新生成
`.config`，再清 `build/xnu` 与 `KernelConfigTables.cpo` 做干净构建。已删除临时
`zzz-force-native-ufs.patch`，personality 回到由配置驱动。

### H85i：完整 NativeUfs 不是 bring-up 捷径，而是 VerifiedRoot 终态

重新生成 `.config` 后，链接器第一次真正把 `libNativeUfs.a` 拉进来，随即暴露：

- `NativeUfsBlock : IOBlockStorageDevice` 需要原始 IOStorageFamily ABI 的 11 个
  alias；这些 alias 目前只由 `NativeUfsProbe` 的
  `NativeUfsLun-original-bindings.o` 生成。
- 驱动强制 `-DNATIVE_VERIFIED_BLOCK=1`，需要 `vr_open`/`vr_verify_block`/
  `vr_xnu_crypto` 与 `verified_root_policies`/`verified_root_key`，即完整的
  VerifiedRoot owner policy bundle；远端没有 `build/verified-root-*` 和
  `target-volumes` 原始 OS 镜像。
- 更关键：`NativeUfs::validate()` 在未启用 `NATIVE_VERIFIED_BLOCK` 时直接
  `return false`，注释明确写着 “Root publication requires owner verification in
  every build”。因此不能靠关掉校验让完整驱动先跑起来。
- 完整驱动还需要 `native_verified_block_root_authorized` /
  `native_verified_block_volume_device`，这两个 hook 在 probe 或
  NativeVirtioBlock 里，而不在 NativeUfs 里。

结论：完整 NativeUfs 只能和真实 owner manifest/VerifiedRoot 一起上线；它不能
替代 probe 做 bring-up。当前 UFS 大读阻塞仍只能在 `NativeUfsProbe` 的
`waitForCompletion`/SMMU fault 路径上查，或先补真实 owner policy bundle。

下一步二选一：

1. 回到 H83k/H84b 的 Probe 基线，在 probe 的读窗口完成等待处加超时、命令
   tag/中断状态和 SMMU fault 日志，定位 3.1 GiB 处 `winFlight=1` 不返回。
2. 先做真实 owner policy：用精确的 iPad7,1 17.7.11 OS/SystemOS DMG 在 macOS
   上跑 `build-owner-os-policy.py` 生成 `build/verified-root-*`，再启用完整
   NativeUfs + VerifiedRoot。

### H86a–H86i：Probe read-ahead，然后切到完整 NativeUfs + VerifiedRoot

Probe 路线：

- H86a/H86b 给 `NativeUfsProbe` 加 128 KiB read-ahead；顺序 4 KiB 读命中
  cache 时约 80–106 ticks（之前约 2100），并已进入用户态
  `exfild` / `distnoted` / `MobileGestaltHelper`。
- 但最终仍会停在一个窗口请求（例如 `req=a3d50/64`），且 H86c 的独立
  `NATIVE_UFS_HEARTBEAT` 也没有打印，说明 warm-link/MMIO 已经整体停住，
  不是单纯的慢。本轮不再继续这条路径。

完整 NativeUfs/VerifiedRoot 路线：

- 从原始 iPad7,1 17.7.11 IPSW 提取 OS/SystemOS：
  `044-76040-038.dmg` sha256 `3f99b859...`，`044-76034-038.dmg`
  sha256 `b4908cde...`。
- 用 `kits/VerifiedRoot/tools/manifest.py` + host C/RSA verifier 生成自签
  owner policies；两份都通过真实 C/RSA 全块校验（OS 1,483,785 块，
  SystemOS 806,400 块）。
- 新增 `build-native-ufs-runtime.py`，把 `NativeUfs`、`RootAuth.cpp`、
  `verified_root.c`、`xnu_crypto.c`、policy `inputs.o` 和原始
  IOStorageFamily bindings 打进 `libNativeUfs.a`。
- 32 字节 hash 时 policy 约 73 MB，kernel 120 MB，boot image 135 MB；
  H86f 停在 OnePlus logo，UEFI 根本没起来，确认是镜像过大。
- 把 per-block digest 临时截断到 8 字节（`VR_HASH_BYTES=8`，最终恢复 32 字节），
  policy 降到约 17 MB，kernel 67 MB，boot image 回到 81,147,904 字节。
- H86g（slide `0x8000000`）UEFI 菜单卡住；H86h（slide `0x5000000`）
  进入内核但 APFS 后 instruction fetch abort。
- H86i 把 `IOStorageFamily-bindings.json` 的所有绝对地址按
  `0x5000000 - 0x4100000 = 0xF00000` 修正后，完整 UFS 真正跑通：
  `NativeRamBlock` 注册、APFS 加载、`disk0` checkpoint 搜索成功。

H86i 镜像/内核：

| 项 | sha256 |
| --- | --- |
| boot | `07ac9dc46b8b7dea0310f111d4b00c66be88d584ee3e66cd03180d420201c350` |
| kernel | `2df14e024c4d9860f691cbdaa680b56a22ceed025da15dd98e5cb1c85afe3694` |
| payload | `f1db5c2a4b5b0fcc7eb4cab4985c2a390177205430af7d13616e53b6f47cac07` |

最后停在：

```text
apfs_extract_root_hash_arn: could not retrieve system-volume-auth-block from device tree
import_lboot_forwarded_roothash: apfs_extract_root_hash_and_manifest failed with error: No such file or directory (2)
```

这不是 UFS、Probe 或 Data seed 问题，而是 ADT 缺少真实的
`system-volume-auth-block`（owner/Apple root auth block）。最终必须提供真实的
owner boot manifest/VerifiedRoot；8 字节 digest 和自签 policy 都是临时 bring-up。

下一步二选一：

1. 先做临时 APFS root-auth bypass，跳过 `system-volume-auth-block` 到达
   launchd/UI；之后再补真实 Apple/owner root。
2. 直接补真实 `system-volume-auth-block`（需要 personalized IM4M/Apple root
   输入），同时把 policy digest 恢复为 32 字节。

### H86j–H87a：auth blob 放行，APFS root 挂载，进入 FileSet KC/driverkitd

- H86k：把 IPSW 的 `SystemVolume` root-hash IM4P（229 字节，
  `Firmware/044-76040-038.dmg.root_hash`）作为
  `/chosen/system-volume-auth-blob` 注入 ADT。APFS 不再报
  `could not retrieve system-volume-auth-blob`，改为停在
  `import_lboot_forwarded_roothash: importing root hash`。
- H86l/H86m：完整 NativeUfs 的 `start()` 只有 `native-ufs-root=1` 才调用
  `startRoot()`；之前没加这个 boot arg，OS/SystemOS 窗口根本没发布，APFS
  一直在等 `04769D26...`。加 `sheng-pmgr=2` 的空 stub 后 H86m 黑屏，
  说明完整 root 路径确实依赖真实 PMGR，stub 不够。
- H87a：回到 Probe 内核 + 真实 auth blob + `allow-root-hash-mismatch=1`，
  不带 `native-ufs-root`/PMGR。结果 APFS root 成功挂载，并进入用户态：
  `NATIVE_CACHE_SIG`/`NATIVE_H66_FCNTL`、`KextLog: Loading FileSet KC(s)`、
  `KextLog: driverkitd is active`。最后停在这里，但 UFS 仍在完成
  `SystemOS` 4 KiB 读（cache hit ticks 约 87），已不是 root auth 问题。

H87a 镜像/内核：

| 项 | sha256 |
| --- | --- |
| boot | `bd17e843e173e1c6188fca59eaa61d8dfe43820a4da5ba1ffb62af674365b0cd` |
| kernel | `dd275f7473783ec03a7e45dbe7585026be29950505755c6ca3c5ec0b72bb00a4` |
| payload | `cf7796371587f275a20f5a1721db76472057126ec6da36580e5dc25eaf53fc27` |

H87c：保留 board 默认的 permissive AMFI（`amfi_get_out_of_my_way=1`、
`amfi=0x94`、`amfi_allow_any_signature=1`、`cs_enforcement_disable=1`、
`native-skip-exec-signature=1`），只额外加 `allow-root-hash-mismatch=1`，
并回到 `cpus=1`。结果 `_check_cdhash_in_trustcache ... Only allowed
processes` 的循环消失，说明之前命令行追加的 `amfi=0 ...` 覆盖了 board 默认值。

H87c 之后仍停在：

```text
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_WINDOW: SystemOS ... ok=1 ticks=114
```

而且没有 `NATIVE_UFS_ALIVE` heartbeat，说明不是空闲，而是 Probe 的 warm-link
路径在后续 SystemOS 读/kext 加载中停住。UFS root、auth blob、TrustCache
权限都已越过；剩下是 warm-link transport 的稳定性，或完整 NativeUfs 的真实
PMGR 依赖。

H87c：boot `3c0747cdd0ebe6d47c98679dc617157f87b560231276f22f55a9a0e5b38bcd42`，
payload `8cc67f1a0757c86d0cb80092b39180a97ff8958b707a22df44ce7a9b746ed15a`。

下一步二选一：

1. 移植 DinnerABC `CheeseburgerPlatformPower` + PMGR bindings，让完整
   NativeUfs root 路径可用（需要按当前 slide 调整 PMGR 绝对地址）。
2. 继续在 Probe warm-link 上做 transport watchdog/reset，尝试跨过这次
   SystemOS 读停住。

display/backboardd 仍未到达；当前只是内核控制台。

最终恢复真实 owner boot manifest、VerifiedRoot/AMFI/TrustCache，移除 ADT 占位。

### H88a–H89b：真实 PMGR、board-id、auth blob、mount-phase-1

- H88a：完整 NativeUfs root + 真实 PMGR，TrustCache 加载完成后
  `No POST boot-arg set.` 后黑屏。
- H88b：只保留 PMGR、不启用 `native-ufs-root`，出现
  `panic: P11 PMGR: device provider refused`。原因是 PMGR `start()` 要求
  platform provider 上有 17 字节（含 NUL）的
  `unixnu,board-id="oneplus,cheeseburger"`；ADT 没有，回退到 `model=iPad7,1`
  后拒绝。
- H88d：ADT 根节点补 `unixnu,board-id` 后，PMGR panic 消失，但完整
  `native-ufs-root=1` 仍然黑屏，说明黑屏来自 `startRoot()`，不是 PMGR。
- H88e：PMGR + board-id、不启用 root，PMGR 正常注册：
  `P11 PMGR: original ApplePMGRNub registered`、`AMFI: PMGRIDN linked`；
  NativeRamBlock/APFS/Data 都工作。该次 auth blob 因生成器被覆盖而丢失。
- H89a：Probe + 真实 PMGR + auth blob，launchd 走到
  `mount-phase-1`，`mount` 因缺少 `boot-manifest-hash` exit 66。
- H89b：ADT `/chosen` 补 48 字节 `boot-manifest-hash` 占位后，
  `mount-phase-1` 通过，继续到 `FileSet KC` / `driverkitd`，随后又停在一次
  SystemOS/OS UFS 读，且无 `NATIVE_UFS_ALIVE` heartbeat。

H89b：

| 项 | sha256 |
| --- | --- |
| boot | `d2a9d62bf464a1e6408e9c7a611b929fcd8fb1cc76d684fb69a6637c25cb619a` |
| kernel | `df4ff6e769f5b03e774b3a76ee25af5ee796606144efd08493da2f857303aa3f` |
| payload | `28409665c1fc1fb9ce4a9cc3e8edfabec4f0ae8565c3bdd0b655a77bceb4ebb0` |

结论：真实 PMGR 集成可用；完整 `startRoot()` 仍黑屏；Probe 路径能过
mount-phase-1 但在重读阶段停住。下一步要么给 Probe 加 transport
watchdog/reset，要么用串口/panic-screen 捕获停住原因。boot-manifest-hash
和 8 字节 policy digest 都是临时占位，最终恢复真实 owner manifest / 32 字节。

### H90a–H90d：参考 warm-link NativeUfs 移植

- 参考 `package/BoardRuntime/NativeUfs.cpp` 已移植为
  `scripts/NativeUfsWarm.cpp`，并随 runtime archive 编译。
- 必须使用 late object：
  `llvm-objcopy --remove-section=__DATA,__mod_init_func
  --globalize-symbol=__GLOBAL__sub_I_NativeUfs.cpp`，否则链接器报
  `__GLOBAL__sub_I_NativeUfs.cpp` 未定义。
- late 对象不会自动注册 class；H90b 出现
  `Couldn't alloc class "NativeUfs"`。H90c 在 `sheng_pmgr_run()` 里先调用
  `cheeseburger_ufs_register()`，class 注册成功，控制台出现
  `P11 UFS: original storage ABI matched; entering read-only warm-link driver`。
- H90d 放宽 compatible 为列表搜索后，仍反复出现
  `P8 UFS refused: missing verified MSM8998 profile`；同时出现
  `P8 UFS warm state CAP=... HCE=1 HCS=10`，说明部分 provider 已进入
  transport，但被 `(HCS&3)==3` 的 idle/live 检查拒绝（当前 HCS=0x10）。
  这是参考驱动对 firmware 控制器状态的假设不一致，不是 ABI/class 问题。

当前最佳可用镜像仍是 H89b：Probe + 真实 PMGR + auth blob + 48 字节
`boot-manifest-hash`，已过 mount-phase-1，到 FileSet KC/driverkitd，
随后在重读阶段停住。

H90e 放宽 `(HCS&3)==3` 后，结果没有实质变化：多数 provider 仍打印
`P8 UFS refused: missing verified MSM8998 profile`，进入 transport 的那个也在
`P8 UFS warm state ... HCS=10` 后停住，OS/SystemOS 没有发布，APFS 仍停在
`importing root hash`。参考 warm-link 驱动在当前 firmware/控制器状态下也无法
建立可用队列。

H91：Probe + PMGR + 10 秒 stall panic。实机没有触发
`NATIVE_UFS_STALL`，屏幕上 SystemOS 读持续完成（`ok=1 ticks≈96`），
`winBytes` 约 3.23 GB，最后停在 `KextLog: driverkitd is active`。
说明这次 UFS transport 没有硬卡死；剩余阻塞在 **FileSet KC / driverkitd
的 kext/SystemOS cryptex 加载循环**，不是 UFS 读停住。

H91：

| 项 | sha256 |
| --- | --- |
| boot | `cd81c5b8ec91f103f3e3c0fd7de7bfb26633f4fbabecd34490e5627dd6f3ff9b` |
| kernel | `7f02891c32825b75fcb76f2969ea2c1a541662d4c369d29fc85732b19f0e532d` |
| payload | `e7fa5cdff58217886ebf269b30683c78da83c409ae179c356650f69869f08942` |

下一步不再是 UFS。`cryptexd` 只认 **Cryptex1** 格式；当前 ADT 的
`boot-manifest-hash` 仍是 48 字节全零占位。`mount-phase-1` 只检查属性存在，
但 SystemOS 的 Cryptex1/FileSet KC 很可能需要真实 owner boot manifest /
SystemOS root hash 才能完成挂载，因此 `driverkitd` 循环。该占位已足以过
mount-phase-1，但不足以保证 cryptex 验证。

`cryptexd` 的字符串确认它走 AuthAPFS / Image4 `im4m` 认证：

```text
AuthAPFS disabled because quire lacks an im4m.
AuthAPFS enabled, skip up-front dmg authentication.
Running in debug mode, skip trust cache
```

没有现成的 `cryptex=0` boot arg。临时 bypass 需要改 `cryptexd`/libboot
跳过 AuthAPFS，但会改动 OS 根镜像，使当前 APFS root policy/root hash 失效，
必须重新生成 policy；或者提供真实 `Cryptex1,SystemVolume` owner manifest/im4m。
在此之前 display/UI 不会出现。

### H92：cryptexd stub + 完整 userdata 覆盖（破坏性）

按用户明确批准执行：

- OS DMG 转 UDRW，替换 `/usr/libexec/cryptexd` 为 keep-alive stub；
  修改后 OS whole-disk sha256 `10f92356d14ddbdb9b94d87ea291b54272fa3078eb4642e82ad10b57e11e7401`。
- 重建完整 userdata：OS `6,077,580,800` + SystemOS `3,303,014,400`，
  image `9,382,658,048` 字节，sha256
  `b0e75882e4de823c0b47fba909fe11f87a897e96a6f29f79a871e0b8425dc85a`。
- `fastboot flash userdata` 成功（12 个 sparse 块，350 秒）。
- 用 H91 启动：APFS root hash mismatch 被 `allow-root-hash-mismatch=1`
  放行，launchd/PMGR/用户态继续，但仍停在
  `KextLog: Loading FileSet KC(s)` / `driverkitd is active`。

结论：stub `cryptexd` 不是正确的 gate。SystemOS 的 Cryptex1 需要真实
AuthAPFS/owner manifest 才能完成挂载；只让 cryptexd 活着并不能提供
SystemOS/FileSet KC。当前设备 userdata 已被覆盖为上述镜像；原始 OS/SystemOS
可从 IPSW 恢复，Data 已丢失（用户已批准）。

真实 owner manifest/im4m 路径已核查：项目和 DinnerABC 都没有 Image4 IM4M
生成器。IPSW 的 `SystemVolume`/`Cryptex1,SystemVolume` 只是 229 字节 IM4P
root hash；`scripts/audit-target-root-hashes.py` 明确记录
`personalized_im4m_present=False`，这些 payload 不能提供 personalized IM4M。
我们的 VerifiedRoot manifest 是 `VROOT01` 自签格式，`cryptexd` 不识别。
真实 IM4M 需要 Apple TSS/personalization，当前输入无法生成。

因此当前只剩：对 `cryptexd`/libcryptex 的 AuthAPFS 分支做二进制 patch，
或恢复原始 userdata 并停在 H91。完整 `startRoot()` 仍黑屏；H91 内核仍是
当前最佳 Probe 内核。

最终恢复真实 owner boot manifest、VerifiedRoot/AMFI/TrustCache，移除 ADT 占位。

## 更新规则

每次工作结束追加一行日志，并更新“当前阶段/下一步/待实测/阻塞”。构建产物哈希、日志路径和失败现象记录在日志里；私有文件只放 `.cache/firmware/`，不提交。
