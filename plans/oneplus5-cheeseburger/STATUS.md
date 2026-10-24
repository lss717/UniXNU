# OnePlus 5（cheeseburger）B 线状态

- 计划：`plans/oneplus5-cheeseburger/PLAN.md`
- 线路：B — UniXNU / 4K
- 最终目标：iPhone10,2 / iOS 16.7.16（20H392）
- 当前阶段：**B3 完成；B5 只读 UFS/GPT 里程碑已冻结（LUN0 只读读盘路径成立；IOMedia 未直接打印）；下一阶段 B5 root 为破坏性写入，需单独批准**
- 当前 gate：**G1 通过（2026-10-22）**
- 基线提交：UniXNU `e95b37d`（main）
- 本地提交：UniXNU `c8a5eeb`（计划）、`18f3020`（package）、`270ea4b`（B1 记录）、`692d70f`（docs 记录）；本轮 B1 收尾见 `git log -- plans/oneplus5-cheeseburger`
- 远程仓库：
  - UniXNU `https://github.com/lss717/UniXNU`（`main`，`8193701`）
  - UEFI fork `https://github.com/lss717/edk2-msm8998`（分支 `unixnu-cheeseburger`）
  - 设备仓库 `https://github.com/lss717/UniXNU-cheeseburger`（`main`，`22742e3`）
- UEFI 分支：`edk2-msm8998` 的 `unixnu-cheeseburger`，提交 `0471194`、`708fa06`、`7f34479`、`91e17a8`、`8ef28f1`、`1ffb934`
- 最近更新：2026-10-24

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

本地仓库 `/home/ls/UniXNU-cheeseburger`（`main`，提交 `a67972c`，尚未推送）：

- `board.toml`：B3 的 iPad7,1 17.7.11 fixture、实测 userdata/RAM/GOP 值、`[payload]`；
- `board.iphone10-2.toml`：B6 目标 profile 的占位；
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

只读检查结果：

- 完整备份校验：`SHA256SUMS` 共 84 项，**84 成功、0 失败**。
- 实机 userdata 几何与 `board.toml` 一致：
  `first_lba=0x14f40`、`last_lba=0x1c627fa`、`lba_bytes=4096`。
- 仓库内没有现成的 `userdata-root.img`、APFS 根卷或 SHNGROOT 镜像。
- `board.toml` 当前 IPSW 是 **iPad7,1 / 17.7.11（21H461）**，仅作 B3
  fixture；不是最终 **iPhone10,2 / 16.7.16（20H392）** 根输入。
- `board.iphone10-2.toml` 仍是 TODO：IPSW URL/哈希、20H392 prelink、
  D21AP `/product`/`/buttons`、userdata 窗口都未完成。
- `NativeUfsProbe`/`NativeUfsLun` 只有 READ10；没有 WRITE10、UNMAP、
  FORMAT 或任何写工具。
- `unixnu build userdata` 需要 macOS `hdiutil` 和目标 IPSW；当前没有可
  验证的目标 APFS root 输入，不能生成有效根镜像。

因此 B 的阻塞点不是 UFS 读路径，而是：

1. 缺少目标 iPhone10,2 16.7.16 的可验证 root/APFS 输入；
2. 缺少 B6 profile 的 IPSW 哈希/prelink/ADT 数据；
3. 缺少受控的 userdata 写入路径。

**B 当前不执行。** 只有在前述输入齐备、并明确批准写入 userdata 后，才
进入备份校验后的实际写盘阶段；不盲目写入 iPad fixture 根镜像。

## 下一步

0. ~~先跑 PSCI 对照镜像~~（2026-10-23 已完成；8 s / 30 s / 20 s 三个对照都
   按预期复位，复位路径可信）。
1. ~~上机验证 `boot-physbase.img`~~（2026-10-23 已完成；stage 3 与 20 s
   对照的 kernel_start 只差 0.52 s，**MMU 已过**）。
2. ~~上机跑 panic 内核~~（2026-10-23 已完成：停在 stage 1/2 色带，没有
   panic；现已由 stage 4 二分解释为 `arm_vm_prot_init` 的未映射 prelink 段）。
3. ~~改 prelink 布局并重建内核~~（2026-10-23 已完成：CI run
   `39951630215`，`slide=0x4100000`；`prot4`、`_arm_vm_init` 均已 PASS）。
4. ~~测试控制台窗口~~（2026-10-23 已完成：`PE_init_printf`、PE1、
   `machine_startup`、`_kernel_bootstrap`、`_kernel_thread_create`、
   `_bsd_init`、`_IOKitBSDInit` 全部 PASS）。
5. **B5：UFS/root**（下一阶段关键路径）：XNU 已在 BSD/IOKit 初始化里等待
   root device；需要 NativeUfs/APFS/root UUID。没有 UFS 就不会继续到
   launchd。
6. ~~普通控制台输出~~（2026-10-23 已完成：`console_init` 后
   `gc_enable(TRUE)`，`boot-console-fix.img` 日志上屏）。
7. **修 prelink kext 范围**（当前动作）：
   `emit_prelink.py` 已补 start/stop slide 和 size；真正根因是
   `vm_kernel_slid_top` 仍取 `vm_prelink_einfo`，而 slide 后的
   prelink text/data 在它上面，`ml_static_slide()` 把组件段清 0。
   已提交 `native-prelink-slid-top.patch`（`707fde9`），待 CI/上机。
8. **重新启用 trust cache runtime**：等 `AppleImage4`/AMFI 的初始化顺序
   在 prelink 里确定后再打开；当前 B3 先关闭。
9. 解释 DarwinBoot 日志里的 `owned=0`（ADT 的 `darwinboot-memory-size`
   解析正确，诊断固件已编译）。
10. B6 时再实现 `--identity iphone10,2` 的真实 `/product`、`/buttons` 复制。

（1-5 的旧项——推仓库、dispatch workflow、TWRP 备份——已于 2026-10-22
完成，见下方日志。）

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

- 设备已接入（2026-10-23，adb/fastboot 可用）。
- **MMU 已过**：20 s stage 3 与 20 s pre-MMU 对照的 kernel_start 相差
  0.52 s；4 KiB 页表、TCR/TTBR、SCTLR 切换均已通过。
- 当前卡点：`emit_prelink.py` 没有把 `kmod_info` 的 start/stop（+180/+188）
  随 slide 写入；`com.apple.kec.Libm`/`corecrypto` 的 start 指针仍在
  slide 前地址，OSKext 范围校验失败。
- 普通控制台输出已解决：`console_init` 后调用 `gc_enable(TRUE)`；
  panic screen 和普通 `kprintf` 都能上屏。
- trust cache runtime 暂时关闭（img4if/amfi 未注册）；B5/B6 再补。
- 下一阶段是 B5 的 UFS/root；没有 root device 时内核会停在 BSD 初始化。
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

## 更新规则

每次工作结束追加一行日志，并更新“当前阶段/下一步/待实测/阻塞”。构建产物哈希、日志路径和失败现象记录在日志里；私有文件只放 `.cache/firmware/`，不提交。
