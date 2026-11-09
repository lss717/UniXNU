# OnePlus 5（cheeseburger）B 线状态

- 计划：`plans/oneplus5-cheeseburger/PLAN.md`
- 线路：B — UniXNU / 4K
- 路线/目标：iPad7,1 / iPadOS 17.7.11（21H461）
- 当前阶段：**C3 完成（2026-11-09）。ZAP/PAS 全部 rc=0，但 CP secure 状态
  未解除；对照 sagit 后确认 ZAP 镜像必须低 4 GiB 且 1 MiB 对齐，H236bh 按此
  实现分配。**
  PM8005 S1（FTS426）经 SPMI 在 752 mV 使能 → GX GDSCR PWR_ON → Fabia PLL
  1028 MHz 锁定 → gfx3d 根 257 MHz → 分支使能 → RBBM 可读
  （`0x00010042 / 0xb5f00000`）。C3 的内存/CP/GPMU 代码已就位；A540 的
  `qcom,smmu-v2` 已按厂商 `arm-smmu.c` 路径核对。H236x 的只读 survey 已确认
  SMMU 几何（3 个 CB、8 个寄存器页、36 位 PA），H236y 用修正后的 kit 参数执行
  C3（CB0 + SID0 映射 + CP/GPMU）。H236z–H236am 已把 CP halt/VBIF drain、
  configure、INSTR/RB base 全部读回通过，SMMU 无 fault，但 ME_INIT 不消费；
  RBBM 软复位在写 1 处挂住。H236an 把脉冲两次写之间的 UFS log flush 去掉，
  用来区分“复位本身挂总线”和“flush 排在未完成的复位写之后”。基线见
  `diagnostics/A540-C1-C2-baseline-2026-11-09.md`，SMMU 路径见
  `diagnostics/A540-C3-smmu-vendor-path-2026-11-09.md`。
- 当前 gate：**H236bh 的 1 MiB 对齐 ZAP 镜像。** sagit 的 `MDTImage::imageInto`
  要求 `.b02` 的 `p_align=0x100000`，`stageZap` 在低 4 GiB 内做内部对齐。
  H236bh 用低 4G mask `0xffffffff`、多分配并对齐到 1 MiB。通过后
  `CP_MEM_WRITE` 应能落内存，再进入 C4/C5。SMMU 几何和 CP 配置已固定：
  ID0=48016403、ID1=20008003、ID2=00007511。
- 基线提交：C1/C2 基线 kernel `8147dc53…`、boot `4dd225e2…`（见 H236g）
- 当前代码提交：本地 UniXNU `main`（H236an 提交）；NativeMobileDisplay H236an
  （无 flush 的 RBBM 脉冲）；设备仓库 `main` 未变
- 远程仓库：
  - UniXNU `https://github.com/lss717/UniXNU`（`main`）
  - UEFI fork `https://github.com/lss717/edk2-msm8998`（分支 `unixnu-cheeseburger`）
  - 设备仓库 `https://github.com/lss717/UniXNU-cheeseburger`（`main`，`5ad54e2`）
  - NativeRamBlock fork `https://github.com/lss717/RamBlock`（submodule 路径仍为
    `drivers/NativeRamBlock`，fork 提交 `bc079a5`；`upstream` 指回 `UniXNU/RamBlock`）
- UEFI 分支：`edk2-msm8998` 的 `unixnu-cheeseburger`，提交 `0471194`、`708fa06`、`7f34479`、`91e17a8`、`8ef28f1`、`1ffb934`
- 最近更新：2026-11-09

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

### H93：cryptexd AuthAPFS stub patch（破坏性，未成功）

- 恢复原始 `cryptexd`，把 `_cryptex_core_image_authapfs_enabled` 的
  symbol stub（`0x3fce8`）改成 `mov w0,#0; ret`，强制 AuthAPFS disabled。
- 重建 userdata：OS 窗口 sha `5fae7a80...`，image sha `5b780d89...`，
  再次 `fastboot flash userdata` 成功（350 秒）。
- 启动后 APFS/launchd/PMGR 继续，但 `_check_cdhash_in_trustcache`
  “Only allowed processes can check the trustcache” 循环再次出现，随后仍是
  `FileSet KC` / `driverkitd`。修改后的 OS 二进制不再受 AMFI/trustcache 信任，
  这是 patch 系统 daemon 的直接副作用。
- `check_cdhash_in_trustcache` 在原始 Apple AMFI kext/预链接代码里，不在
  当前 XNU 源码中；继续 bypass 需要 patch AMFI/trustcache 或真实签名/权限。

结论：补真实 IM4M 不可得；patch `cryptexd` 又会触发 AMFI/trustcache 完整性
循环。当前设备 userdata 是 H93 修改版，UI 仍未到达。建议恢复原始 userdata
并停在 H91；若继续，只能进入预链接 AMFI/trustcache 的二进制 patch。

### H94：恢复原始 userdata，停在 H91

- 用原始 OS/SystemOS DMG 重建 userdata：
  OS 窗口 sha `e5634d04a8ac35f024845f583394e0a35deb26a04cb0c00286a8674e25a9a4f2`，
  SystemOS 窗口 sha `b4908cde41d23e6bc05e6af51a2c9eeb00cf0f863a6a18b1600c96a3fd70414f`，
  image sha `fd43ee7035ce185ce4215ac93fdc006fd784a54b3b7442e21457c226cbe03093`。
- `fastboot flash userdata` 成功（12 个 sparse 块，354 秒）。
- `fastboot boot` H91 成功，设备回到 Probe 基线（原 OS + PMGR + auth blob +
  48 字节 boot-manifest-hash）；H92/H93 修改版已从设备上移除。
- Data 已在 H92/H93 覆盖中丢失，用户已批准。

最终状态：H91 是当前最佳 Probe 镜像；剩余阻塞是 SystemOS Cryptex1 /
FileSet KC 的真实 owner IM4M/AMFI-trustcache，当前输入无法生成。完整
`startRoot()` 仍黑屏。

### H95：仓库收尾与当前产物

- 已删除项目根目录 183 个 `*.jpg`，以及
  `plans/oneplus5-cheeseburger/assets/`；后者的 Git 删除已提交。
- `drivers/NativeUfs` 子模块指针更新到 `43a4bc7`（已推送到
  `lss717/NativeUfs` fork）。
- VerifiedRoot 的 8 字节 digest bring-up 改动（`4c43a01`）因上游
  `UniXNU/VerifiedRoot` push 403，保存为
  `patches/verified-root-truncated-hash.patch`；应用方式：
  `git -C kits/VerifiedRoot am patches/verified-root-truncated-hash.patch`。
  父仓库不指向未推送的子模块 commit。
- 设备仓库新增 warm-link `NativeUfsWarm.cpp`、`CheeseburgerPlatformPower.cpp`、
  PMGR/AuthAPFS glue、ADT auth blob/boot-manifest-hash 属性、policy 生成脚本；
  这些是 bring-up 代码，默认 board 配置仍保持 Probe 基线。
- 远端测试 board 的差异（slide `0x5000000`、runtime/PMGR archive、payload
  `size_mib=76`、1 GiB 内存/AMFI placeholder）保留在远端 board.toml，未提交到
  干净基线。
- 当前设备：原始 userdata（OS `e5634d04...`、SystemOS `b4908cde...`）+
  H91 内核；停在 `FileSet KC` / `driverkitd` + `_check_cdhash_in_trustcache`
  循环。H91 boot `cd81c5b8...` 是当前最佳镜像。

最终恢复真实 owner boot manifest、VerifiedRoot/AMFI/TrustCache，移除 ADT 占位。

### H96：AMFI selector 0x5f 权限门定位与独立诊断补丁（只读调查）

- 新增 `plans/oneplus5-cheeseburger/BASELINE.md`：记录 H91 boot/payload/
  kernel/ADT/TrustCache 哈希、payload 原始启动参数、仓库/子模块状态和缺口。
- 新增 `plans/oneplus5-cheeseburger/diagnostics/H96-investigation.md`：
  启动链路、证据表、3 个根因假设、H96a/H96u 区分实验和缺失证据。
- 从 H91 payload 内 FAT 卷直接读出 `kernel.macho`
  `7f02891c...`、`kernel.macho.adt` `83d733d7...`、
  `kernel.macho.trustcache` `7416ca4f...` 和完整 boot args；H91 的
  kernel/ADT/TrustCache 哈希与 STATUS 原有记录一致。
- 对原始 iPad7,1 21H461 kernelcache 的 AMFI kext 做只读反汇编：
  `_check_cdhash_in_trustcache` 的 MAC syscall selector 为 `0x5f`；
  入口在 `0xfffffff005ab73a8` 检查
  `com.apple.private.amfi.can-check-trust-cache`，失败直接打印
  `%s: Only allowed processes can check the trustcache` 并返回 `13`
  (`EACCES`)，发生在 XNU `query_trust_cache()` 之前。当前循环因此是
  调用方权限/签名状态问题，不是 TrustCache 查询未命中。
- 原始 SystemOS 中该 entitlement 及 `Unable to find AMFI`、
  `cdhash ... is not in trust cache` 字符串位于
  `/System/Library/Frameworks/ExtensionFoundation.framework/ExtensionFoundation`
  （Mach-O `0x1785b000`，UUID `28968ac0-0ace-360e-83e3-c8e7ad996871`）；
  循环候选调用方是加载该框架的宿主/服务进程，具体 PID/comm 仍需 H96a
  运行日志确认。
- H90d `HCS=0x10`：按 UFSHCI，bit 4 是 `HOST_ERROR_INDICATOR`，
  `HCS & 3 == 0` 表示 `DEVICE_PRESENT` 与
  `UTP_TRANSFER_REQ_LIST_READY` 都未置位；不是 idle/live 编码差异。
  放宽 `(HCS & 3) == 3` 不解决问题，H96u 需先清 error/重建队列。
- 新增诊断补丁 `patches/xnu/zzzz-trustcache-amfi-trace.patch`：
  - `native-trace-amfi-syscall=1`：在 `__mac_syscall()` 记录 AMFI
    selector `0x5a..0x66` 的 pid/comm/csflags/blob/platform/entitled/
    cdhash；selector `0x5f` 限 64 次。
  - `native-trace-trust-cache=1`：在 `query_trust_cache()` 记录调用方
    pid/comm、query type、20 字节 cdhash、返回值和限频。
  - 默认 boot arg 缺失时两个函数立即返回；不改变 AMFI、TrustCache、
    root auth 或 VerifiedRoot 策略。
- H96 调查/补丁提交：`6102287`（父提交 `93c7fb6`）。
- 验证：补丁已对干净的 `xnu-10063.141.1` 源树通过
  `git apply --check`；本机无 macOS/Xcode 内核工具链，**尚未实际编译**，
  也**未上机**。H91 产物未覆盖。
- H96a 构建完成（macOS 15.8.2 / Xcode 26.3，H91 对象树 +
  `xnu-10063.141.1`）：raw kernel `92e55a70...`、kernel.macho
  `f5dbbe1c...`、payload `8c92f8c8...`、boot
  `790de811...`。payload/ADT/TrustCache/Data seed 沿用 H91，只替换
  kernel 与两个 trace boot arg。
- 第一次 H96a `fastboot boot` 返回 `Booting OKAY`，但停在 UEFI Shell：
  用 `mcopy` 覆盖 8.3 短名时丢失 VFAT 长名 `unixnu.toml` /
  `kernel.macho`，UniXNU 找不到配置/内核。已删除旧目录项并用长名重建
  payload；修正版 boot `790de811...` 等待再次上机。
- H96a 修正版已进入 XNU：屏幕可见 `NATIVE_UFS_PROGRESS`、
  `_check_cdhash_in_trustcache ... Only allowed processes` 循环、
  `KextLog: driverkitd is active`；未看到 `NATIVE_AMFI_SYSCALL`。
  可能是 64 次 trace 已滚屏，或 boot arg 未被解析。
- H96a2（强制 trace，不依赖 boot arg）已构建：kernel
  `918cdbe1...`、payload `da268d87...`、boot `8c58b138...`；
  仅构建树把 trace 默认打开并把限频提高到 100000/4096，仓库默认补丁
  仍保持 boot-arg 关闭。等待再次上机。
- H96a2 屏幕出现多次 `NATIVE_TC_QUERY ... ret=0`（UserEventAgent/
  launchd/spracy），说明 XNU TrustCache 查询和命中正常；仍无
  `NATIVE_AMFI_SYSCALL`。原因是 `__mac_syscall` trace 的 target 过滤用了
  bundle ID，而 AMFI 的 MAC policy 名很可能是
  `AppleMobileFileIntegrity`。旧 trace 还调用了
  `IOCurrentTaskHasEntitlement()`，可能提前初始化 entitlement，构成副作用。
- H96a3 取消 target 过滤、打印实际 target、删除 entitlement 查询调用：
  kernel `b36ec3a8...`、payload `d5030ee5...`、boot
  `98192bb0...`。等待再次上机。
- H96a3 仍无 `NATIVE_AMFI_SYSCALL`，但 `NATIVE_TC_QUERY ... ret=0`
  正常；说明 AMFI 检查不是从 XNU `__mac_syscall` 进入的，而不是 boot arg
  或滚屏问题。
- H96a4 一次性诊断镜像：把 AMFI 拒绝分支
  `VM 0xfffffff00aab73b8` 的 `tbz` 改成 `nop`，只跳过权限门，TrustCache
  查询仍执行；用于获取 `Process %d` 调用方和 query hit/miss。kernel
  `86a7e63a...`、payload `6d6f4935...`、boot
  `f745b54f...`。这是受控诊断绕过，不是默认配置或最终修复。
- H96a5（B 方案：拒绝即 panic 并打印调用方）已构建：在 AMFI 拒绝分支
  `VM 0xfffffff00aab75d8` 跳到代码洞，读取 `proc->p_pid`/`p_comm` 后
  `panic("H96_AMFI_REJECT: func=%s pid=%d comm=%s")`。kernel
  `2994ae9d...`、payload `2ed839d3...`、boot
  `c2a18350...`。这是诊断 panic，不改变 AMFI 策略/权限门。
- H96a5 panic 确认拒绝方：`pid=63 comm=driverkitd`，selector `0x5f`，
  `platform=1`、`blob` 非空、`csflags=0x2202331`。原版 iPad7,1 17.7.11
  `/usr/libexec/driverkitd` 是 adhoc 签名，entitlements 中**没有**
  `com.apple.private.amfi.can-check-trust-cache`；因此 AMFI 拒绝符合策略，
  真正问题是 driverkitd 为什么走了这个未授权的 MAC syscall 路径
  （可能缺少 AMFI IOKit user client/SystemOS 路径而回退）。
- H96a6（跳过权限门 + panic 查询结果）已构建：kernel `d06f6e69...`、
  payload `aec14df7...`、boot `3ac690a0...`；`mask=0` 表示命中，
  `mask=3` 表示两次查询都 miss。等待上机。
- H96a6 panic 结果：`pid=63 driverkitd target=AMFI call=95`，目标
  cdhash `7bb1e532...`；panic `mask=0x1`。按 AMFI 代码的失败位语义，
  这表示 type 1（static）miss、type 2（loadable）hit；目标 driver 已在
  loadable TrustCache 中。照片中紧随的 `NATIVE_TC_QUERY` type1/2 用的是
  另一个 cdhash `1fc19a...`，不能当作 AMFI 目标的查询结果。
- 结论：不是 TrustCache 完全缺失；driverkitd 自身没有
  `com.apple.private.amfi.can-check-trust-cache`，却走了未授权的
  `__mac_syscall("AMFI",0x5f,...)` 路径；目标 driver 已在 loadable
  cache 命中，下一步优先查 AMFI IOKit user client / amfid / XPC 路径
  为什么不可用或未被 driverkitd 使用，而不是继续补 blob。
- H96a7 已构建（AMFI IOKit service/user client 打点）：kernel
  `0befa003...`、payload `0313ac79...`、boot
  `413e2b50...`。driverkitd 调用 0x5f 时 panic 输出
  `H96_AMFI_PATH: ... service=<0/1> uc_calls=<N>`，用于判断 AMFI
  IOService/UserClient 是否可用。等待上机。
- H96a7 panic 结果：`H96_AMFI_PATH: pid=63 comm=driverkitd target=AMFI
  service=1 uc_calls=0`。AMFI IOService 已注册，但
  `AppleMobileFileIntegrityUserClient` 从未被调用；同屏 `amfid[47]`
  存在。driverkitd 直接走 `__mac_syscall("AMFI",0x5f,...)`，而原版
  driverkitd 没有该 entitlement，因此循环与 TrustCache 内容无关。
- 下一步用 H96a4（全局跳过 entitlement 门的诊断镜像）确认该 gate 是否
  是当前唯一阻塞，并观察 driverkitd 之后的下一个阶段。
- H96a4（全局跳过 AMFI gate）已上机：AMFI 拒绝循环消失，系统继续
  SystemOS 读取，最后停在 `NATIVE_UFS_PROGRESS ... winBytes=329618936`
  附近，无 `NATIVE_UFS_ALIVE` heartbeat、无 stall panic。说明 AMFI gate
  是 driverkitd 阶段阻塞；跳过后的新停点需要独立 UFS 诊断。
- H96a8（H96a4 + `cpus=2`，只改 CPU 数）已构建：payload
  `5c9a4005...`、boot `53f8cfcf...`；用于让 heartbeat/stall
  watchdog 运行并捕获停点快照。
- H96a8（H96a4 + `cpus=2`）已上机：越过 AMFI gate 和早期 UFS 停点，
  到 `KextLog: driverkitd is active`、SystemOS 读取约 3.22 GB 后日志
  停止；无 `NATIVE_UFS_STALL`，但未见后续服务。新阻塞点在 driverkitd/
  FileSet KC 之后，需定位最后 exec/等待任务。
- H96a9（H96a8 + `NATIVE_EXEC` trace + gate bypass）已构建：kernel
  `84312b76...`、payload `0e714fa8...`、boot
  `697536ff...`；用于显示最后执行的进程。等待上机。
- H96a9 已上机：最后 exec 为 `containermanagerd`/`MobileGestaltHelper`，
  之后 `driverkitd is active`，SystemOS 读取约 3.21 GB 后停止；无新
  exec/KextLog，无 UFS stall。停点在 driverkitd/FileSet KC 之后。
- H96a10（UFS 请求内超时 panic）已构建：kernel
  `fe684b31...`、payload `93d052bf...`、boot
  `bd3069c2...`；若 UFS 等待超时会直接 panic 并给出 LBA/长度/UTRD/
  寄存器；若仍无 panic，则停点在上层。等待上机。
- H96a10 已上机：系统启动到 configd/keybagd/amfid/mobileassetd/
  storageproxyd/fseventsd/IOMFB_FDR_Loader/xpcproxy 等大量用户态服务；
  未出现 `NATIVE_UFS_TIMEOUT`/`NATIVE_UFS_STALL`。最后停在 xpcproxy
  的 dyld cache 注册（`NATIVE_CACHE_SIG`）后，尚未出现 backboardd/
  SpringBoard。
- H96a11（exec trace 增加 argv0/argv1 + UFS timeout + gate bypass +
  cpus=2）已构建：kernel `b12e0480...`、payload `20751860...`、boot
  `d225ad4b...`；用于确认最后 xpcproxy 的目标服务。等待上机。
- H96a11 已上机：最后 `NATIVE_EXEC pid=90 comm=xpcproxy
  argv1=com.apple.nsurlsessiond`；目标服务未 exec，系统停在启动
  `com.apple.nsurlsessiond` 这一步；无 UFS timeout。
- H96a12 复用 H96a11 kernel，仅追加
  `sheng-disable-jobs=com.apple.nsurlsessiond`：payload
  `bd9a85b3...`、boot `90812e49...`。用于跳过该服务并观察是否继续到
  backboardd/SpringBoard。等待上机。
- H96a12 已上机：跳过 nsurlsessiond 后启动到 `backboardd`、`sharingd`、
  `imagent`、`lockdownd`，随后停在第二次 `driverkitd is active`，未到
  SpringBoard/WindowServer；无 UFS timeout。当前最远用户态进度。
- H96a13（同时跳过 nsurlsessiond 和 driverkitd job）已构建：payload
  `34573fe9...`、boot `3c5fe707...`；用于判断第二次停点是 launchd job
  还是内核 kext/驱动加载。等待上机。
- H96a13（跳过 nsurlsessiond+driverkitd job）已上机：停在
  `nehelper`，未到 backboardd；说明禁用 driverkitd job 不是正确方向，
  H96a12（只跳 nsurlsessiond，保留 driverkitd）仍是最远路径。
- H96a14（H96a12 参数 + 只记录 driverkitd AMFI 检查目标）已构建：
  kernel `ede3f2b8...`、payload `aa06e6c0...`、boot
  `06bc78c6...`；用于获取第二次 driverkitd 检查的 cdhash。等待上机。
- H96a14 本次运行停在 `routined`（未到第二次 driverkitd trace），与
  H96a12 到达 backboardd 存在 run-to-run 差异；`routined` 是新的同步
  等待候选。
- H96a15 复用 H96a14 kernel，payload 跳过
  `nsurlsessiond,routined,nehelper`：payload `4fed1175...`、boot
  `0b55644d...`。用于排除网络/位置服务同步等待并稳定到达
  backboardd/SpringBoard。等待上机。
- H96a15 已上机：越过第二次 driverkitd，启动到 `chronod`，UFS 约
  3.27 GB 后停住；无 UFS timeout，未到 SpringBoard/WindowServer。
  跳过 routined/nehelper 有效，chronod 是新的停在候选。
- H96a16 在 skip 列表加入 `com.apple.chronod`：payload
  `646bdae0...`、boot `49fc80be...`。用于观察下一服务。等待上机。
- H96a16 已上机：越过 chronod，启动到 `IOMFB_FDR_Loader`、
  `distnoted`、`log_helper` 后停住；无 UFS timeout。最后停点继续在
  routined/chronod/log_helper 之间漂移，说明是某类同步 XPC/launchd
  等待，不是单一 daemon。
- H96a17 扩大 skip 列表（nsurlsessiond,routined,nehelper,chronod,
  log_helper,accountsd,alsd,pfd）：payload `9fdc58c0...`、boot
  `6906c32e...`；用于一次性排除已观察 daemon。等待上机。
- H96a17 启动 panic：`sheng watchdog launchd policy failed: 22 @
  kern_exec.c:8294`。根因是 `sheng-disable-jobs` 字符白名单不允许
  `_`，列表中的 `com.apple.log_helper` 触发 EINVAL；不是用户态服务
  问题。H96a16 无下划线所以能启动到 log_helper。
- H96a18 移除 log_helper，skip 列表改为
  `nsurlsessiond,routined,nehelper,chronod,accountsd,alsd,pfd`：
  payload `c58640e1...`、boot `301d8edd...`。等待上机。
- H96a18 已上机：启动到 `cryptexd`/`eligibilityd`，fseventsd 线程数
  达高水位；之后 5 分钟无变化，无 UFS timeout，未到 SpringBoard。
  系统已进入 cryptexd/SystemOS 路径，可能再次撞上原始
  Cryptex1/AuthAPFS/owner manifest 依赖。
- H96a19 在 skip 列表加入 eligibilityd：payload `995d247c...`、boot
  `0bd34abf...`；用于观察 cryptexd 后下一跳。若仍停在
  cryptexd/SystemOS，则停止靠 skip 推进，转回 owner manifest/AuthAPFS
  或显示依赖。等待上机。
- H96a19 已上机：driverkitd 连续 4 次 AMFI 检查后进入
  `FileSet KC`，随后 cryptexd/eligibilityd 启动并停住。四个 cdhash
  前缀均不在 H91 `kernel.macho.trustcache`、OS DriverExtensions 或
  已检查的 .kext 中（trace 只打印 16 字节，需补完整 20 字节再定案）。
- 结论：继续加 skip 不能解决；问题回到 SystemOS/Cryptex1/FileSet KC
  的真实 trust cache/owner manifest。下一步应打印完整 cdhash 并确认
  来源 cache，或做一次性 AuthAPFS/cryptexd 受控诊断，不得当作最终修复。
- H96a20（完整 32 字节 AMFI 输入/返回 trace）已构建：kernel
  `e7538cb9...`、payload `bef11b85...`、boot
  `9a409302...`；用于确认 driverkitd 检查的完整 20 字节 cdhash 和
  AMFI 返回位图。等待上机。
- H96a20 已上机：多组 driverkitd `NATIVE_AMFI_SYSCALL`/`RESULT`，
  `ret=0`；`out` 前 20 字节与 `in` 相同，尾部为 `aaaa/0` 类值，用户
  缓冲区不能作为干净 mask 来源。H96a20 确认 FileSet KC 前有多次
  driverkitd 检查，但真实 mask 仍需在 AMFI 内部 `[sp+0x58]` 打点。
- 当前剩余阻塞仍是 SystemOS/Cryptex1/FileSet KC 信任链；不再扩大
  boot-arg/skip 列表。下一步只建议小型 AMFI 内部 panic 诊断（完整
  20 字节 cdhash + mask）。
- H96a21 已构建并启动：在 AMFI 成功路径通过二进制 cave 调用
  `native_amfi_tc_diag`，对 driverkitd 打印完整 20 字节 cdhash 与
  `[sp+0x58]` 真实 mask，第 4 次 panic 固定屏幕。kernel
  `b9cd4c9b...`、payload `bc3ea90e...`、boot
  `f7e9a2f0...`；等待 panic 照片。
- H96a21 已上机并 panic：四次 driverkitd 检查均为 `mask=0x1`，
  即静态 miss、loadable hit；目标 cdhash：
  `1fc191a7fbb1e532b54ca15befb83d7efe9ab3e1`、
  `0d6972a904236c9c4bea8297c2d8bdacbeb1167a`、
  `d4c8a0514d5952c89dc24039d9efd4a26e0c87ef`、
  `d599af53ba5c1d66a0a0c9135c5756f9d3713284`。
  因此 AMFI/这些 driver 的 trust-cache 检查已通过，不是当前阻塞；
  H96a19 “不在 H91 侧车”是 trace 截断/侧车范围造成的误判。
- 当前阻塞回到 FileSet KC 之后的 cryptexd/SystemOS/launchd 等待。
  下一步最小诊断：H96a22 只跳过 `com.apple.security.cryptexd` job
  （一次性诊断，不是最终修复），观察是否到 backboardd/SpringBoard；
  或在 cryptexd/launchd 路径加日志。
- H96a22 已构建：沿用 H96a20 无 panic 内核，只在 skip 列表加入
  `com.apple.security.cryptexd`；payload `7e2c37c9...`、boot
  `1b76aac0...`。用于一次性判断 cryptexd 自身等待还是更深层
  SystemOS/AuthAPFS；不是最终修复。等待 fastboot 上机。
- H96a22 已上机：跳过 cryptexd 后反而停在 `driverkitd is active`，
  没有 cryptexd/eligibilityd、没有 backboardd/SpringBoard，3 分钟无
  变化；说明 cryptexd/eligibilityd 不是可跳过的 daemon。结合 H96a19
  屏幕也停在 driverkitd active，确认 **H96a18（不跳过
  eligibilityd/cryptexd）才是目前最远路径**，可达 cryptexd/
  eligibilityd 后停住。skip 迭代到此为止。
- 当前剩余阻塞回到 SystemOS Cryptex1/AuthAPFS/owner manifest。仅剩：
  (1) 真实 `Cryptex1,SystemVolume` owner manifest/IM4M（不可得）；
  (2) 一次性 kernel-side AuthAPFS/Image4 诊断绕过（非最终修复）；
  (3) 停在 H96a18/H91。当前安全边界不允许重新 flash 修改后的 OS/
  userdata，H93 的直接 patch cryptexd 二进制方案不再采用。
- H96a22 的基线已跳过 eligibilityd，不能隔离“只跳 cryptexd”；因此
  另建 H96a23：H96a18 skip 列表（保留 eligibilityd）+ 只加
  `com.apple.security.cryptexd`，使用 H96a20 无 panic 内核。payload
  `23b29bda...`、boot `4d23038e...`。等待 fastboot 上机。
- H96a23 已上机：保留 eligibilityd、只跳过 cryptexd，仍停在
  `driverkitd is active`，无 cryptexd/eligibilityd、无 SpringBoard，
  2 分钟无变化。说明 cryptexd 是后续 launchd 阶段必需服务，不是可跳
  过的 gate；H96a18（不跳 eligibilityd/cryptexd）仍是唯一到达
  cryptexd/eligibilityd 的路径。skip 迭代结束。
- 当前阻塞回到 cryptexd/SystemOS Cryptex1/AuthAPFS/owner manifest。
  可选：真实 owner manifest/IM4M（不可得）、一次性 kernel-side
  AuthAPFS/Image4 诊断绕过（非最终修复）、或停在 H96a18/H91。
- H96a18/H96a21/H96a22/H96a23 的屏幕日志已采集；完整串口日志、SHNGROOT SystemOS offset 和 cryptexd/AuthAPFS syscall 级证据仍缺。
- 上述 H96a 任务已由 2026-10-31 只读源码审计取代；审计报告：
  `diagnostics/H96-readonly-source-audit-2026-10-31.md`。在完成真实
  owner/VerifiedRoot 路径或 cryptexd/AuthAPFS 只读跟踪前，不再叠加
  boot-args、skip 或 TrustCache/完整性验证修改。

## H96 只读源码审计（2026-10-31）

- 报告：`plans/oneplus5-cheeseburger/diagnostics/H96-readonly-source-audit-2026-10-31.md`
- 审计边界：只读源码/日志；未修改完整性验证逻辑，未新增 launchd skip，未刷写设备。
- 结论：H96a21 的四个 driverkitd 检查均为 loadable hit，AMFI/这些
  cdhash 的 TrustCache 命中不是当前阻塞；H96a18 是最远路径，H96a19/
  H96a22/H96a23 的 skip 更早停在 `driverkitd is active`。
- 关键源码发现：H96 使用 NativeUfsProbe 的
  `native_verified_block_root_authorized()` 桩（仅检查 `device != NODEV`），
  不链接完整 VerifiedRoot；H96 的 `XNU_OWNER_BOOT_MANIFEST=0`，
  ADT `boot-manifest-hash` 是 `make-cheeseburger-adt.py` 写入的 48 字节
  全零占位，内核不生成真实 hash。
- `winBytes` 是所有 NativeUfsWindow 共享的累计上层请求字节，不是
  磁盘位置/实际 UFS 字节；H96a23 的 `315523184` 约 300.9 MiB，最后
  成功 UFS 命令为 `lba=0x1b1bca, bytes=0x20000`，没有
  `NATIVE_UFS_TIMEOUT`/`NATIVE_UFS_STALL`。
- 材料区分：SHNGROOT 是 UniXNU 用户态容器；owner boot manifest 是
  VerifiedRoot/SHA-384 派生；Image4/IM4M 是 Apple personalization；
  TrustCache 是 cdhash allowlist。当前 `Cryptex1,SystemTrustCache`
  实际加载 module 和 cryptexd 的 IM4M/AuthAPFS 要求仍为“待确认”，
  不能按源码证明标记为缺失。历史 H92/H93 的“不可得”是当时输入结论，
  本次审计将其降级为“待确认（强二进制证据）”。
- 下一步只读检查：补 SHNGROOT `window[1]=SystemOS off=...` 日志、
  launchd job/exit 观测、cryptexd syscall/mach wait 跟踪；不要直接
  patch cryptexd、改 userdata 或继续 skip。

## H98b 用户态 / UFS / owner 诊断（2026-10-31）

- 报告：`plans/oneplus5-cheeseburger/diagnostics/H98b-process-ufs-diagnosis-2026-10-31.md`
- H98b 最终屏（`221.jpg`）：
  - `NATIVE_UFS_WINDOW: SystemOS ... abs=17f540000 lba=187bc5`；
  - `NATIVE_UFS_PROGRESS ... lastWin=SystemOS abs=17f540000 ... ufsWin=SystemOS base=17f540000`；
  - 最后完成 `SystemOS block=0x43420 count=8 done=4096 ok=1`；
  - 最后可见 `NATIVE_EXEC alsd pid=63 ppid=1`，随后 `driverkitd is active`；
  - **没有 cryptexd/eligibilityd，也没有 `NATIVE_EXIT`/`H97_SNAPSHOT`。**
- H96a18 曾创建 `cryptexd` PID 80、`eligibilityd` PID 87（xpcproxy 87/88），但旧日志没有 ppid/退出/快照；因此其运行/退出状态仍未知。
- H98b 与 H96a18 使用同一 skip 列表却未到 cryptexd/eligibilityd，说明存在 run-to-run 差异；不能把 H96a18 的进程集合当稳定结果。
- UFS 映射：H98b 确认 SystemOS 基址 `0x17f540000`；H96a23 `lba=0x1b1bca` 对应偏移 `0x3268a000`，但旧日志 `lastWin=0x93450`（偏移 `0x1268a000`）不一致，旧日志无法精确归因该 UFS 请求；H96a22 最后有标签读为 `block=0x13fcf0` / 偏移 `0x27f9e000` / `done=4096`。
- owner 信任链：H98b 仍是 `XNU_OWNER_BOOT_MANIFEST=0`、`XNU_OWNER_ROOT_TRUST=0`、`XNU_VERIFIED_ROOT_PROBE=0`、`XNU_NATIVE_VIRTIO_BLOCK=0`、`XNU_NATIVE_UFS_PROBE=1`；NativeUfsProbe root 授权桩只检查设备；ADT `boot-manifest-hash` 仍为 48 字节全零；不是真实VerifiedRoot/owner 认证。
- IM4M/AuthAPFS：H98b 未到 cryptexd，未观测 AuthAPFS/Image4 调用；IPSW 只有 229-byte IM4P root-hash，`personalized_im4m_present=False`；cryptexd 字符串只作线索，当前 **未知**，不能标记为已证明根因。
- 下一步建议 H99：修复/确认 H98b 快照触发，重复 H96a18 路径确认 cryptexd/eligibilityd 到达稳定性，并增加 launchd job/exit 与 cryptexd syscall/mach wait 观测；不再增加 skip，不修改完整性验证。

## H99 快照 / UFS 诊断（2026-10-31）

- 报告：`plans/oneplus5-cheeseburger/diagnostics/H99-snapshot-diagnosis-2026-10-31.md`
- 产物：H99 kernel `512b5f90...`、boot `eab1ff4a...`。
- H99 最终屏（`222-1.jpg`、`222-2.jpg`）：
  - `lastWin=OS abs=15040000 ... ufsWin=OS base=15040000`；
  - `lastWin=SystemOS abs=17f540000 ... ufsWin=SystemOS base=17f540000`；
  - 最后完成 `SystemOS block=0x4e200 count=8 done=4096 ok=1`，偏移 `0x9c40000`，绝对 LBA `0x190190`；
  - 最后可见 `NATIVE_EXEC alsd pid=94 ppid=1`，随后 `driverkitd is active`；
  - **没有 cryptexd/eligibilityd、没有 `NATIVE_EXIT`、没有 `H99_SNAPSHOT`/`H99_PROC`。**
- H99 的 UFS 基址确认了 H96a23 `lba=0x1b1bca` 属于 SystemOS 地址范围（相对 SystemOS 偏移 `0x3268a000`，806.5 MiB；相对 OS 超出 OS 大小），但旧 `lastWin=0x93450` 偏移 `0x1268a000` 与它不一致，旧日志无法精确归因到具体请求。
- H96a18 曾创建 cryptexd PID 80、eligibilityd PID 87；H99 同 skip 列表仍未创建，说明 run-to-run 差异；旧 H96a18 没有 ppid/退出/快照，目标进程运行状态仍未知。
- H99 没有观测到 AuthAPFS/Image4 调用；owner 链仍是 bring-up：`XNU_OWNER_BOOT_MANIFEST=0`、`XNU_OWNER_ROOT_TRUST=0`、`XNU_VERIFIED_ROOT_PROBE=0`、`XNU_NATIVE_VIRTIO_BLOCK=0`、`XNU_NATIVE_UFS_PROBE=1`，ADT `boot-manifest-hash` 仍为 48 字节全零。IM4M/AuthAPFS 是否是后续根因仍未知。
- 下一项 H100：先确认 `h97_start_snapshot` 是否被调用、`PE_parse_boot_argn("h97-snapshot")` 是否成功、线程是否启动；再用短周期/exec 触发快照，重复 H96a18 路径确认 cryptexd/eligibilityd 是否稳定出现。不得新增 skip，不修改完整性验证。

## H100 无 skip 对照（2026-10-31）

- 报告：`plans/oneplus5-cheeseburger/diagnostics/H100-noskip-control-2026-10-31.md`
- 产物：H100 payload `c325a545...`、boot `f831d259...`；kernel 沿用 H99 `512b5f90...`。
- 变量：只移除 H96a18 的 7 项 `sheng-disable-jobs`，保留 `sheng-lite=1`、`h97-snapshot=360` 和其他参数。
- 结果：最终停在 `pfd`/`accountsd`/`nsurlsessiond`/`routined` 一带，更早于 H99 的 `driverkitd is active`；没有 cryptexd/eligibilityd，没有 `NATIVE_EXIT`，没有 `H99_SNAPSHOT` 输出。
- 结论：
  - 跳过 eligibilityd/cryptexd 仍已证明会造成更早停止；
  - 7 项 skip 在掩盖 pfd/accountsd/nsurlsessiond/routined 的上游等待，不是 cryptexd 缺失的唯一原因；
  - H99 与 H96a18 的差异仍有 run-to-run/未观测成分，不能归因于单一 skip。
- 下一步 H101：不增加 skip；修复快照（无条件打印入口/参数解析/线程启动），在 cryptexd/eligibilityd exec 时触发短快照；逐项记录 pfd/accountsd/nsurlsessiond/routined 的等待对象。

## H101/H102 快照调试（2026-10-31）

- 报告：`plans/oneplus5-cheeseburger/diagnostics/H102-snapshot-debug-result-2026-10-31.md`
- H101（`h97-snapshot=120` + `H101_ARM_ENTER/PARSE/THREAD_START`）和 H102（无条件启动 180 秒快照）最终屏都没有 `H101_`/`H102_`、`H10x_PROC` 或 panic；都停在 `driverkitd active`。
- H102 无条件启动仍无结果，排除了“`h97-snapshot` boot-arg 解析失败”作为唯一解释；但不能从屏幕区分入口未执行、线程启动失败、线程未唤醒或输出被滚动覆盖。
- 因此 cryptexd/eligibilityd 是否运行/退出仍未确认；不能把“最终屏没有 cryptexd”当作完整进程集合。
- 产物：H101 kernel `9990f955...`、boot `39f21579...`；H102 kernel `80c30288...`、boot `fe08ad87...`。
- 下一步 H103：在 `h97_start_snapshot()` 入口直接 panic（或不可滚动标记）确认调用；若入口正常，改为在 `NATIVE_EXEC` 的 cryptexd/eligibilityd/alsd 分支直接 `panic` + `proc_iterate`，绕过线程/定时器。不得新增 skip，不修改完整性验证。

## 设备与构建主机（2026-11-01 起）

- 内核/镜像构建：`lss@192.168.10.103`（macOS 15.8.2 / Xcode 26.3）。
- 设备连接：手机已改接到 Windows 主机 `ls@192.168.10.225`，该机 PATH 中有 `fastboot.exe`。
- Windows 镜像目录：`D:\\Users\\ls\\Documents\\OnePlus5_ios`。
- 后续流程：macOS 构建 → 把 boot/payload/kernel 放到上述 Windows 目录 → 在 Windows 上 `fastboot boot`。
- 不在仓库记录主机密码。

## H103 Preboot/Cryptex 布局审计（2026-11-01）

- 报告：`plans/oneplus5-cheeseburger/diagnostics/H103-preboot-layout-audit-2026-11-01.md`
- 说明：H102 文档原建议的 H103 是快照入口 panic；本轮先做 Preboot/Cryptex 布局审计，快照入口实验顺延。
- 用本机 21H461 OS 窗口和 SystemOS 原始镜像只读核对：
  - `/System/Cryptexes/OS -> ../../private/preboot/Cryptexes/OS`；
  - `/System/Cryptexes/App -> ../../private/preboot/Cryptexes/App`；
  - `/private/preboot` 为空；
  - `/System/Library/Caches/com.apple.dyld` 不存在；
  - SystemOS 根下只有 `System`/`usr`，包含 `System/Library/Caches/com.apple.dyld`、378 个 Frameworks、1681 个 PrivateFrameworks。
- 结论：H62 挂 `/private/preboot`、H96 `XNU_OWNER_UNION_SYSTEMOS=1` 挂 `/` 都没有命中 launchd 的 `/private/preboot/Cryptexes/OS`；这比“cryptexd 等真实 IM4M”更符合现有证据。
- SystemOS trust cache module `d121ba89...` 已经在 H91 bundle 中，不是当前缺失项。
- 已准备默认关闭的 H103 实验：
  - `scripts/prepare-preboot-overlay.py`；
  - `scripts/prepare-owner-data-fixture.py --preboot-overlay`；
  - `patches/xnu/zzzz-owner-preboot-layout.patch`（`XNU_OWNER_PREBOOT_LAYOUT=1`）；
  - workflow input `preboot_layout`。
- H103 实验路径：Data mount → bindfs `/private/var/preboot` 到 `/private/preboot` → SystemOS 挂到 `/private/preboot/Cryptexes/OS` → `DYLD_SHARED_CACHE_DIR=/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld`。
- 已在远程 macOS 构建 `XNU_OWNER_PREBOOT_LAYOUT=1` 镜像；尚未上机：
  - kernel `979260df...`
  - payload `5bb75401...`
  - boot `aed7e8d8...`
  - 本地产物 `out/cheeseburger/boot/boot-H103-preboot.img`
- 已执行 `fastboot boot out/cheeseburger/boot/boot-H103-preboot.img`，ABL 接受并离开 fastboot；最终屏幕待确认。下一步检查 `NATIVE_PREBOOT: status=0 stage=5`、`NATIVE_H82_DATA`、`NATIVE_ENV`，以及 launchd 是否越过 `driverkitd`/cryptexd 等待。
- 约束：`XNU_OWNER_PREBOOT_LAYOUT=1` 需要 `OWNER_CACHE_MOUNT=1`、`OWNER_CACHE_STARTUP=1`、`OWNER_DATA_MOUNT=1`、`NATIVE_RAM_BLOCK=1`、`OWNER_UNION_SYSTEMOS=0`。不新增 skip，不修改 AuthAPFS/Image4/TrustCache 验证。

## H103au–H103bg：启动前沿、显示参数与颜色面板（2026-11-03）

详细记录见
`plans/oneplus5-cheeseburger/diagnostics/H103-preboot-layout-audit-2026-11-01.md`
第 44 节。本段只保留结论和关键产物。

### 对照结果

- **H103au**：H103at + `offline-mobile-graphics-client=1`；
  `display calls=0`，backboardd 已 exec 但不打开显示。client probe 无效。
- **H103av**：加入 `NATIVE_ALIVE` 心跳；cpus=1/2 都停在
  `driverkitd is active`，屏幕没有 `NATIVE_ALIVE`。心跳线程启动/调度
  本身仍需独立诊断。
- **H103ax-1g**：Data 512 MiB → 1 GiB；3 次仍为 2 次 `calls=0`、
  1 次 FDR loader `calls=1`，无 ENOSPC。Data 容量不是唯一原因。
- **H103ay-4g**：`owned_memory_size` 从实际 1 GiB 改为 4 GiB；
  1 次出现 `backboardd/55` + `SpringBoard`，但 backboardd 仍不 open；
  另 2 次停在 driverkitd/eligibilityd 一带。内存也不是稳定修复。
- **H103az/H103be**：AMFI 权限门 `0x5f` 的 `tbz` NOP；H103be 上机
  1 次白色、2 次绿色，右上始终没有 backboardd 青色。AMFI 不是
  backboardd 不 open 的根因。
- **H103bf**：追加 DinnerABC 的
  `offline-mobile-graphics-client=1`、`offline-legacy-cpu-present=1`、
  `unit-scale=2`、`sheng-vsync=60/fixed=1`；仍无 backboardd client。
- **H103bg**：Data seed 写 BackBoard/CA 软件渲染偏好
  （`CAEnableDeepFramebuffer=false`、`CAEnableFramebufferCompression=false`、
  `CAEnableIOSurfaceCompression=false`、`CAForceSoftwareRendering=true`）；
  仍无右上青色。

### 颜色面板结论

H103ba–H103bd 在 `NativeLegacyDisplay::drawTestPattern()` 增加右上角
2×2 颜色面板，避免依赖滚屏日志：

- 左上：用户态前沿/退出（H103bd：绿=SpringBoard、白=SpringBoard+backboardd、
  紫=SpringBoard 退出、品红=backboardd 退出）；
- 右上：黑=无 client、黄=FDR loader、青=backboardd；
- 左下：client calls；
- 右下：swap/transfer；
- 右下角 16×16 心跳闪烁。

上机结果：

- H103bc：3 次都只有左上绿，backboardd 没有 exec；
- H103bd：2 次左上绿；1 次左上白、右上黄、左下蓝，等待 10 分钟不变；
- H103be/bf：最好也只有左上白 + 右上黄，没有右上青。

因此当前不是“backboardd 打开显示失败后立刻退出”，而是：

```text
backboardd 有时根本不启动
即使启动，也不调用 Legacy display 的 newUserClient
```

### 只读 backboardd 分析

`/usr/libexec/backboardd` 导入 `IOMobileFramebuffer`、`Metal`、
`IOSurface`，包含 `BKDisplayStartWindowServer`、
`BKDisplayIsHeadless`、`StartWindowServer: headless (display:%d/server:%d)`、
`IOServiceOpen failed for class ...`、`CADisplay`/`CAWindowServerDisplay`。
最符合证据的解释是 backboardd 没有拿到它认可的 CADisplay/display
provider，进入 headless，而不是 Legacy `newUserClient` 的问题。

### 当前阻塞与下一步

已排除：Data 512 MiB/1 GiB、4 GiB 内存、AMFI gate、client probe、
`offline-legacy-cpu-present`、`sheng-vsync`、unit-scale、Legacy
`newUserClient` 路径、BackBoard/CA 软件渲染偏好。

下一步按 A 线 provider 对齐计划执行（详见
`diagnostics/A-provider-parity-plan-2026-11-04.md`）：

1. **A1**：发布最小裸 `IOAcceleratorES`（不设置
   `MetalPluginName`/`MetalPluginClassName`），验证 backboardd 是否
   因为没有 accelerator 而 headless；
2. **A2**：A1 不足时，补最小 display 属性
   （`DisplayWidth/Height`、`RowBytes`、`PixelFormat`、
   `IOMFBDisplayRefresh`），不改 timing；
3. **A3**：仍不足时，才做 `IOFBDependentID=0` /
   去掉 `NativeSandboxGrantProcess` / `IOClass` override 的 identity parity；
4. **A4**：最后才补父节点 `compatible`/`canvas-width/height`。

不再增加 boot-arg、`sheng-disable-jobs`、Data 容量或 AMFI 诊断；
不再做 display timing/ordering/delay/pump 实验。

### A1 结果（2026-11-04）

`boot-H103cw-a1.img`（boot `43f831fb...`、kernel `4950bfa6...`、
payload `3ac218e4...`）上机 **panic**：

```text
Can't load kext com.apple.iokit.IOGPUFamily - requests to user space are disabled.
OSMetaClass::preModLoad() wasn't called for class NativeA540AcceleratorProbe
```

- `NativeA540AcceleratorProbe` 的 `OSKextLoadKextWithIdentifier()`
  返回值判断写反；
- pre-root late probe 阶段无法加载 `IOGPUFamily`，原始
  `IOAcceleratorES` 基类不可用。

结论：**A1 作为 pre-root 裸 accelerator stub 不可行**，源码已回退，
H103cg 仍是唯一稳定基线。下一步建议 **A2（最小 display 属性，不依赖
IOGPUFamily）**；A1b（prelink `IOGPUFamily` / post-root publication）
会改变 prelink 布局，暂不执行。详见
`diagnostics/A-provider-parity-plan-2026-11-04.md`。

### A2 结果（2026-11-04）

`boot-H103cx-a2.img`（boot `571d77b7...`、kernel `4fbd7673...`、
payload `9a6efa2e...`）：

```text
NATIVE_LEGACY: display properties 1080x1920 row=4320
NATIVE_LEGACY: phase=4 dt=1 probe=1 attach=1 start=1 reg=1
Waiting on <dict ... IOProviderClass=IOMedia ... UUID=04769D26-...>
```

- A2 属性已在显示服务上发布；
- 但 Legacy archive 变大再次触发 Data/APFS IOMedia race；
- 未到 backboardd，`calls` 无法评估；A2 镜像不可用，H103cg 保持。

**A2/A2c 已停止（2026-11-04，越界）**：用户指出 A2 改了 display
属性/refresh，A2c 又移除了 `drawTestPattern()` 的 accel 方块并改变
archive 成员，违反“不再做方块/灰条/display 时序/ordering 实验”的边界。
已恢复 H103cg 源码和 7 成员 builder；A1/A2/A2c 镜像均不使用。后续除用户
明确要求外，不再做 display archive、方块/灰条、display timing 或
ordering 实验。

### H103cg-1 结果（2026-11-04）

`boot-H103cg-1.img`（boot `e1fb98d4...`、kernel `7edeaf8e...`、
payload `105c0c08...`）按 H103cg 源码重打，仅把三个 16×16 指示块从
右下角移到左上角：

```text
fill(w-16,h-16) -> fill(8,8)
fill(w-40,h-16) -> fill(32,8)
fill(w-64,h-16) -> fill(56,8)
```

上机仍然停在：

```text
Waiting on <dict ... IOProviderClass=IOMedia ... UUID=04769D26-...>
```

结论：即使只改三个坐标常量，display archive 的二进制/布局变化仍会触发
Data/APFS race；H103cg exact 是唯一稳定点。源码已回退；H103cg-1 不使用。
指示块只能从 display archive 外部覆盖/绘制，或先修复 race，不能再通过
重编 display archive 移动。

### H103cg-2/H103cg-3 对照（2026-11-04）

| 包 | 内容 | boot | 结果 |
| --- | --- | --- | --- |
| H103cg-2 | H103cg 原镜像逐字节拷贝 | `4560ac5b...` | 可用 |
| H103cg-3 | H103cg 同源码 clean rebuild | `d9e3322b...` | 停在 `IOMedia UUID 04769D26` |

H103cg-3 源码与 H103cg 完全一致（submodule `5f29dde`、7 成员 builder），
但 kernel/ADT/payload 构建输出不同：

```text
H103cg:   kernel 7b5d4ae1...  ADT d98d9522...  payload a12f5fc9...
H103cg-3: kernel fe155269...  ADT 158ebdb6...  payload 9d8fb9b7...
```

结论：**H103cg 源码可重复，二进制不可重复**；精确布局/时序变化会触发
Data/APFS race。H103cg 原二进制是唯一稳定点，H103cg-2 是可用拷贝；
H103cg-3 不使用，不再把“同源码重编译”当作无改动包。后续只能从
display archive 外部覆盖/注入，或先修 race。

### H103cg-6 成功（2026-11-04）

`boot-H103cg-6.img`：

```text
boot:    1201d68379dedd8f08a3a01cdadccde9caf6009b9304e2dae5f4a8f410a4ac7f
kernel:  76634aa5e4104d97b53526dfa0d33b212846a959951525fc31935dfc52982e6e
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: c9f841e6f7612bd58dc3e96eb1227a5a165f540f8eca8aea6251dcf62911fdb6
```

H103cg-6 通过 root，可用。根因是 macOS 构建树的
`NativeUfsProbe.cpp` 仍是旧 Android 逻辑：GPT 选 `"userdata"`、root
manifest/window 绝对地址硬编码 `0x14f40*4096`。H103cg-6 恢复为
H103cg 的 `userdata_ios` first LBA，并修正：

```text
rootFirst = GPT 中 userdata_ios 的 first LBA
manifest  = rootFirst
window    = rootFirst * 4096 + rootOffset
```

H103cg-5 只修了 partition，window 仍用 `0x14f40`，所以仍失败；H103cg-6
修正 window 后通过。

结论：

- 重编译内容可以稳定过 root；H103cg-6 是可用重编译基线；
- H103cg-2 是原镜像逐字节拷贝，仍可用作原版对照；
- 之前 H103cg-3/4/5 的 `04769D26` 是 UFS probe 分区/window 错误，
  不是 display archive 或 kernel 时序；
- display provider 仍 `calls=0`，无 UI；本次未移动心跳指示块。

### H103da 候选（2026-11-04）

`boot-H103da.img`：

```text
boot:    997f5cd88d42fbbe4c8f0f8bd8d4abf42b3b6aa74c4f4ab044c446a9316c7a53
kernel:  f8a238140fdaf0ee0082e4c77ed7389c6b50efa536230a7e16762a468ee1d6c3
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 9ebfe2ec3dbc7ae578d7683d376a3b4e9b583268690e8566dfed6b053ec1944e
```

基线 H103cg-6（`userdata_ios` probe + window 修复）；display 只把三个
16×16 指示块移到左上角 `(8,8)/(32,8)/(56,8)`，其他不变。

上机：**root 通过，`calls=0`，左上角三个块没有出现**。当前
`NativeUfsProbe` heartbeat 没有调用 `native_legacy_test_pattern()`，
clean rebuild 丢失了 H103cg 的周期重绘调用，`drawTestPattern()` 从未
执行；坐标本身已编译进 archive。

### H103db 候选（2026-11-04）

```text
boot:    efc4bc2fbb5bc6721982046cc9b837b8182af55f4ee409b5035c8110e0849f21
kernel:  d559aef221fbf554db6994e75d609dffb49d9e5d730596feabfec99bed0f8713
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 3d0a464f0b082d5d413f2193aa89c95fa809f499febb5fd450d31c2e3a239d51
```

`NativeUfsProbe` heartbeat 每 10 秒调用 `native_legacy_test_pattern()`
（weak import），恢复 H103cg probe 的周期重绘。display 仍是 H103da 左上角
三个块；root 修复不变。

上机：右上和左上都没有方块。H103cg 原 kernel 反汇编确认 heartbeat 顺序是
`IOLog -> native_legacy_test_pattern`；H103db 在 `IOLog` 前调用，日志把
图案盖掉。H103dc 把调用移到 `IOLog` 后。

### H103dc 候选（2026-11-04）

```text
boot:    909bb8998f5f9c06e3a1ab5e43fb404673560e82ced026c072e45c70cd1ab5f5
kernel:  1c1032a4dfad07a3cc0331c5cb4b5bb561923e4378f06a374b79f0952910462f
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 5caa2c9ceb4461fbec201d337eddaca1394d88629cadd440bb2e5327ced060a9
```

按 H103cg 原 heartbeat 顺序，在 `IOLog` 后调用
`native_legacy_test_pattern()`；display 仍是 H103da 左上角三个块。

上机：仍然没有方块。H103cg 原 heartbeat 是直接
`bl _native_legacy_test_pattern`；H103dc 的 `weak_import + if (symbol)`
在 kernel link 里绑定为空，调用被跳过。H103dd 改为直接调用。

### H103dd 候选（2026-11-04）

```text
boot:    571b00917dceb81f478e59ce070bf278311775af739f174f858a8ae563b5f4ff
kernel:  971f37ee5330129b116e315c01ff678aeed00f0d9647fbe42160376019462c9c
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 310053dbc060c32d5c20ac13ce9edbe24a616ab888e71d0037b19f4aaeb02335
```

反汇编已确认 `IOLog -> native_legacy_test_pattern` 直接调用，和 H103cg
原 kernel 一致。结果待上机。

### H103de 候选（2026-11-04）

```text
boot:    c21879d16a8351ebfcd0dd0f11dcace35241af9c88a2c0d32007fa914b80be0c
kernel:  1476ba31c9c0ecb6ceb9eb5145e3291a577821328b9a50f5d040745c967b3846
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: e777c4e1fc6f0aaf5d0d353ac309683781398ccc3d7ccc73e8a1b4f01eafd30c
```

`NativeUfsProbe` 增加 `sheng-log=1` 持久化快照：写 `userdata_ios` 末尾
32 MiB 的 `SHLOG001` v3 头 + 1 MiB kernel msgbuf；probe start 后等待 20 秒
（root 完成）写一次；WRITE(10)+SYNCHRONIZE CACHE；不碰 Android
`userdata`/display archive。新增 `scripts/h103-log-pull.py` 从 TWRP 只读
拉取并解析。结果待上机。

### H103df 候选（2026-11-04）

H103de 的 32 MiB 窗口全 0；H103df 在 body/header 前先写一个
`H103TEST` 块并读回，失败时停屏 30 秒。puller 识别 `H103TEST`。

```text
boot:    2a998098c4c2c147d0d52ad71997e98d67eb3cbc75616a76c1ebd43daaafe4f3
kernel:  87aff456682aaa40b8aaff49d6606268fd578c9310fdbab9bb3ecb8cae5a2eaa
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: faed19554139fd3457b566715963a5b752175b1041a38700ce83569557afb70b
```

结果待上机。

### H103dg 候选（2026-11-04）

H103df 仍无 `H103TEST`；H103dg 增加：

- `NATIVE_UFS_LOG: setup ...` 后停屏 30 秒；
- `H103TEST` 同时写窗口 block 0 和最后一块；
- puller 扫描整个 32 MiB 窗口找 `H103TEST`。

```text
boot:    94040dc74ea2b20f2ba9b8655b92b1dc9d3bf81502a95884f94145c1d5aa9685
kernel:  f1bd6e7cba37a50b73df7b57fdf18bd5ec032ba1962a29af9c3e8ae7d4f21d2e
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: f637a087a016b84c505a1b4edffbd52e56b54b0b1dc9d9b1b2cdb75df5b480a9
```

日志仍在 `userdata_ios` 未使用尾部；Android `userdata` 是 64 GiB ext4，
不能盲写末尾 32 MiB，若必须用需先校验 ext4 文件系统边界。

### H103dh 候选（2026-11-04）

H103dg 的 30 秒停屏在 probe start 末尾、UI 之前，上机反馈“启动后没有
停留”。H103dh 把停屏移到 heartbeat 启动后 45 秒，并打印 setup 参数：

```text
NATIVE_UFS_LOG: late mode=%u first=%llx root=%llx..%llx
IOSleep(30000)
```

log 线程仍在 20 秒写 `H103TEST`（首块/末块）和 `SHLOG001`。

```text
boot:    d35d87a2a744f749078a06c5d3d41ec0e78ffbae8cd7491a8b31332bcc05dc46
kernel:  3bfb18374e43aeda3ce94d44f7a0a20d89112c64c71091ebd629e10a6ca7f896
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 5a123ca1658860d6a315595b0524d6096ae3b8726268cd1bab30d4cf3ea6883c
```

### H103di 候选（2026-11-04）

H103dh 确认 boot 哈希正确，但启动后仍无 45 秒停屏，说明 heartbeat 不可靠。
H103di 把日志写入从 heartbeat 解耦：

- `NativeUfsProbe::start` 同步写一次 `H103TEST` + `SHLOG001`；
- `NativeUfsWindow::doAsyncReadWrite` 累计 64 MiB 后触发第二次快照并停屏 30 秒；
- `logThread` 先写测试，不再因首块非空提前返回；
- 打印所有 `kernel_thread_start` 返回值；
- heartbeat 改用 50 秒计数停屏；
- payload 加 `h103-skip-pattern=1`，本轮不画 2×2。

```text
boot:       e025ea4f401e1fca990ae160c300058775e2c8a5b1b3b852de1b2694297e9f0a
kernel pre: a59dd74d8ca950d2dc0e462e78182d56999384c8219d570fa79fef2593b889b7
kernel:     171185264ec4c0eae82722164b45094045860d657f490bd982d6179390e66cc0
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    d046fc95e76e648a707f131ea6e15c77634079e8ef5a35ad4cb969b45d3e8763
```

H103di 上机在 `start snapshot begin` 后 panic。原因是
`start` 栈帧 0x2360 加 `h103Snapshot` 栈帧 0x20e0（`test[4096]` +
`check[4096]`）超过 16 KiB 内核栈。H103dj 把 test/check 移到
`IOMallocAligned`，`h103Snapshot` 栈帧降到 0x120。

```text
H103dj boot:       4a9de88e2c884506b75bcfeb14ea82a2e2ee09c8afa2711fe14a622d267d2047
H103dj kernel pre: 77134eed24d453e1653666613b397a7d591e08755726eb34a69f72dbf1527d06
H103dj kernel:     276f9927225058e5d7a0fab702a0af6150af0edac16614159fd4c778642a38b2
H103dj payload:    4a8321c68e55f9bd373f0ada49d8396a99331c6e6400efc9827b4b5f5d600897
```

H103dj 栈修复生效，但仍在 `start snapshot begin` 后 panic，PC/LR 在读路径
附近。H103dl 把所有快照的读回关掉，只写 `H103TEST`/body/header，由
puller 验证。

```text
H103dl boot:       491301d0755278baf94c6253c85d2f00306321a96cd39e0e269871094829889b
H103dl kernel pre: 6c0c1f3c55cf9fc5c7590c8f164c4efe2cdaf3c13b492e99f1688d96ab941e16
H103dl kernel:     79646a830126c3aa88afa44ffc90475737e67da6d0de53e8c6de4c210b695ed6
H103dl payload:    9db662466cf4e3ac3dedea4094ab6e704713fd55780595b16d2b86f43b6ad797
```

H103dl 仍 panic 在 start snapshot begin，PC/LR 在 readBlocks/readWindowBulk
附近。H103dm 删除 start 快照和 logThread，只保留 root 之后 64 MiB 窗口读
触发的一次快照，写 H103TEST/body/header，不读回，停屏 30 秒。

```text
H103dm boot:       6de47089a78519b1f239850ec11c9476397bbfc0f2b4df7f578d7e2b93e730cb
H103dm kernel pre: 8676eae81e20f71ddb3e42776e26604e59498e6b658e4b034bed98291fad8d49
H103dm kernel:     5e88804355076fa0231afc2cd8ab4b3906736c637933733053e20c0d6bf41014
H103dm payload:    dc2ae7b63c084cc68762bc4a42ac1b0316c93bb24f8a22a0495faf3bf5323350
```

H103dm 进入用户态，但 `window trigger bytes=67695616` 后仍 panic。H103dn
增加独立的可写 log DMA 缓冲，`logWrite()` 临时替换 `fQueue.data`，避免
CPU 写 live readData；快照仍只在 root 后 64 MiB 窗口读触发，不读回。

```text
H103dn boot:       f6d4e0dcc574a6c1a37f6281caa30d99b40007c819817cfa9772ce907c14aefb
H103dn kernel pre: 0abc16afdfdf987ecfd69f684194cba5c7a0a279ab610516eb4e594d90e03b19
H103dn kernel:     2a86871c25939305e32bcfb72dd2c75d25baf8914a57f262ddf29a2fed20b650
H103dn payload:    8700cc6deb106c3697fcab7bfb12e0074c51955be060c247ce0f66f27d5e4b6e
```

H103dn 仍在 window trigger 后 panic，无 `write test`。H103do 只做单块
WRITE(10)，不写 body/header，不读回，用于隔离写命令本身。

```text
H103do boot:       7c9c92d6fcbc0ee4ada709dbe991974dd632bb1496e0786de71ee5b3f3190235
H103do kernel pre: d5a08ec5023c0e3b3a0b8cf51392400497137e40c1bf2dcaf1a049135c18ae3a
H103do kernel:     7d4d9969d65d9d478a02f6b03be69fa3ff920b3089bb39149d477f37c3f7d097
H103do payload:    8ee9f42772bfa247c9f6cbf2138d503533c7b6e994806061fe450d4f3fc5fd92
```

H103do 单块写开始后 panic，确认单块 WRITE(10) 就崩。H103dp 用
`fLogDma->writeBytes()` 填 DMA，并让 `ufsWriteCommand()` 的 `src` 等于
`q->data`，跳过内部 memcpy；仍只写单块。

```text
H103dp boot:       89e1ea912460ce161b2d58297f767e5a0f8bcd8ba1522f5d9754d02540c085a3
H103dp kernel pre: c0a274cb2e0c4f5c230c0817187a9545a532e09ecbba35e2820f6f59b455695d
H103dp kernel:     4b5ca54dddef09acad19e03a3b7965f6edf5f1cf0cfb25eb85502c8bca3b7f60
H103dp payload:    fe6de668a05e4b4b83dd0a7f5ca91170a0adef4119d963bd5f88c048ef40542f
```

H103dp 在 `fLogDma->writeBytes()` 触发 `kIOMemoryPreparedReadOnly` 断言，
因为 log DMA 用了 `kIODirectionOut`。H103dq 改成 `kIODirectionIn`，仍只写
`userdata_ios` 窗口首块。

```text
H103dq boot:       6f6ffb9148f947a7097e25cdba0b29d9a53764c9dce91688aae7d314fc5879e0
H103dq kernel pre: 664888302c4e39d9fc3418fef47f50d03c179d034d016cc50b3f89b318bceba7
H103dq kernel:     f100195bb7fa93a7f8ec2ed51ce29cf63a971f2ccb60c6c5451c5f93016be97e
H103dq payload:    9fb582e3d250d6ec5de36e38ced8b0a77e62f1ea1d3345be4aa5d76f2bc03d52
```

H103dq 单块写成功；TWRP 拉到 `H103TEST`。H103dr 恢复窗口触发的完整
`SHLOG001` 快照，仍只写 `userdata_ios`，不读回。

```text
H103dr boot:       9d566a4ceea7243ecde98f7442265deafc5f96e1a93c0011bedde4122d99beb3
H103dr kernel pre: 09733c6e1b0d7baf4497454d5194c32f8acfd34268054015a2447dc3f99c5c0a
H103dr kernel:     a5c0a9ead8ea24ba3ce49a8a8e1976226211abf9879f47fff6f8ee196490e8ee
H103dr payload:    c12852ab4ac428385f91594774f611d44176326b5bd98689598d43f3c67943d5
```

H103dr 的 SHLOG001 成功，但 64 MiB 快照停在 launchd/dyld cache。H103ds 在
heartbeat 第 12 tick 增加 late 快照，并去掉 `h103-skip-pattern=1` 恢复 2×2。

```text
H103ds boot:       5f6bfd17c9ad87a3070de1da27a56f907b58bdbef12d838e030ed261531388ec
H103ds kernel pre: e0f57cb61db08be3685de2d8b8cb50f2eeed58006836b3082ca5223c6b4c3080
H103ds kernel:     22e1aa5980149bef455326e3c5d83def80fff98db18b6652294d807822be814c
H103ds payload:    39194bd3cdfb27df875b076ae1a5e28aa1bcfe83c9e9749f34da43d680edae8b
```

H103ds 屏幕停在 `write test`；日志已有有效 SHLOG001，卡点是 header 后的
`logSync()`/SYNCHRONIZE CACHE。H103dt 删除 logSync，WRITE10 用 FUA；
早期 window 快照 pause=0，late heartbeat 快照 pause=1，保留 2×2。

```text
H103dt boot:       d4c770df3ade2f3a7990daa673e58aa3cc77d9f974710ac20f17a70fe1977486
H103dt kernel pre: 50958392dfcd669560aae3ce3ccde2bae1fbc7cc9795f4049b3eb86f34099a7e
H103dt kernel:     1cfdae53833c10286e1f202f46a9a6ad48e24df679648c7a727c92d70e334935
H103dt payload:    f7e1792c50851f052e87f1dbe867c247ad478099266511a5a8d72e1cf29f8fa6
```

H103dt 屏幕继续但 TWRP 文件仍是 64 MiB 早期快照。H103du 增加 1 GiB
`late-window` 快照，两个窗口快照都不停屏；puller 增加
`blockdev --flushbufs` 和 `dd iflag=direct` 回退。

```text
H103du boot:       ba2c1f0a0c75e3e380d794d4794455853b86e6dfa70fcb5833d88857aec4f76c
H103du kernel pre: 495beb9382fbec52b0eefe65dba8b6a3232cd2b407f55b667fc7aaafe6c51178
H103du kernel:     2e660304ece04bfff8638583841be9629ce4517fd950f95b69557aa17db3f854
H103du payload:    c1e7d4a2a77cea2e088da84f8951b739fc40d8435314076c33578208e80d3c59
```

H103du 仍在 late-window 的 1 MiB body/header 处停住。H103dv 改为
heartbeat 每 2 秒写 128 KiB slot，关闭窗口大快照；puller 读最新 slot。
显示侧增加 `NATIVE_LEGACY_PATTERN` 打点。

```text
H103dv boot:       4ed5ce91831621d2b4868f3d88b290d3421c50e61dcb6647b69162a8c1589676
H103dv kernel pre: 441f56c0d14157736532afeace2b2a892ab79acac229f14fdc58d62060fb0b69
H103dv kernel:     593be1065ebfc7f3e0633c66ed0e826178c4b66a2b8ee8062eec71e568962c32
H103dv payload:    ad3b2e80ddd06480261db84ec1698a3c39d39ad64eb1af52fd85044bf76db364
display:           03fa715 (GopFramebuffer display-op5)
```

H103dv 的 display archive 没链入/console 刷屏。H103dw 回到 H103bd 的
`5f29dde` 2×2 颜色面板，保留 2 秒 slot，`gH103Quiet=1` 关闭周期 UFS 日志，
payload 去掉 `-v`/debug/boot-progress。

```text
H103dw boot:       99307b5f99a7154a7212b5e9ff3e0ef562b5fc89e98d4bf334c42c28cde7fcc4
H103dw kernel pre: 57122244f4a55f1e37d02753b094c8f812f163b18478b4a81e4aa38eff235bc8
H103dw kernel:     61603873ad954ef895b3ffefebf722bb3bde3e9ef4fca3f06827b20997628374
H103dw payload:    ff3a13661b3fbccbe38a42633865b84b51cfd57dd8b7f2ba4db218a096462217
display:           5f29dde
```

H103dx 只改顺序：先 `native_legacy_test_pattern()`，后 `h103SlotWrite()`；
仍静默、2 秒 slot、`5f29dde` 2×2。

```text
H103dx boot:       7c4f4e6dde4f55a971dd8abb92e7715d8fdcc9a457670977692e9aed76b21211
H103dx kernel pre: cb65784262dbdc70c6a868664cf58a5f2f7885c85e9ce926fc9c5ae604cc058c
H103dx kernel:     5addf7cd16d56c698344a93af59b33ddb504b6043e29b5ee1721cbcf094fafd5
H103dx payload:    a339391de2d8ba325efd693fa7e5c5a96bd2e8a352f50540d8bec5eae6f435de
```

H103dx 上机 2×2 和 slot 都没有更新。H103dy 完全移除 slot，只保留
heartbeat 2×2，用于判断 heartbeat 是否运行。

```text
H103dy boot:       5bc2f835a73f93c5b0c7717f6d8987fc2ea457bd6c5ef9799bafaa012bf35cef
H103dy kernel pre: a324abf0ea174d95b272ee2cf72400d3adefcab9909bdf71b24169cd57b98335
H103dy kernel:     9cda2b9a65a211ea1b84835b42db7111d08eb13068186cecc95167e4b637b1e1
H103dy payload:    116b6885483c2139e0eff3fa0739c0e511471cb981c9d3f33119d30ee1ca9dd5
display:           5f29dde
```

H103dz 用 H103bd 的 payload 参数（-v/debug=0x14e/boot-progress=2）配
H103dy 的“只画 2×2、不写 slot”内核。

```text
H103dz boot:    4fecce628a60ae0ce0bbf39923931b92f3f4152d5f07b25205caca661f9803c8
H103dz kernel:  9cda2b9a65a211ea1b84835b42db7111d08eb13068186cecc95167e4b637b1e1
H103dz payload: 06c4e71bac2bc1f727de45dedd566c888d99564de11268b9a922b91eaa304749
```

H103ea 回到 H103bd 的心跳节奏：`IOSleep(10000)`、先打印
`NATIVE_UFS_ALIVE`、再调用 `native_legacy_test_pattern()`；`gH103Quiet=0`
恢复周期日志。2 秒 slot 移到独立线程，只在测试图案之外写
`userdata_ios`，不改变心跳顺序。payload 沿用 H103dz 的 H103bd 参数
（含 `sheng-log=1`），display 仍是 `5f29dde`。

```text
H103ea XNU:     32d9bf03ef5a76b64ea4d1f76d38879b150beea8b98a69904ff916b7e9a56166
H103ea kernel:  560571229630b8edd2e235d7c8104ca57cf9fd320e1efe2ec041f7a5cda62e61
H103ea ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
H103ea payload: 4da9f3c04fc867713badd6ca243c20797ad5f7def0ca39b23fd3219d669c6665
H103ea boot:    a07fe2567b43edcf7cbd58a86a8d4474cae49ac84e79b667e074205e1b4e2f5e
display:         5f29dde
```

上机判读：

- 右上 2×2 出现：H103bd 的心跳/日志顺序 + slot 线程可以共存；
- 2×2 仍不出现：display archive 与 H103bd 的差异（其内核含
  `NATIVE_LEGACY_STATE/CLIENTS`，当前 `5f29dde` 不含）或独立 slot 线程
  是最后两个变量，下一步回退到 H103bd 精确镜像；
- TWRP 应能读到每 2 秒更新一次的 `SHLOG001` 最新 slot。

H103ea 上机后右上仍没有 2×2；换成 H103bd 原始 payload 参数
（无 `sheng-log`、无 `native-cpufreq-early`）的 `boot-H103ea-bdargs.img`
也没有。直接对比 H103bd 内核后发现：H103bd 的 **UFS 完成路径**在
`(gUfsCommands & 63) == 0` 时先调用 `native_legacy_test_pattern()`，再打印
PROGRESS/STATE；当前源码只在 10 秒心跳里调用。H103eb 恢复这条 UFS
完成路径重绘，仍用 H103bd 原始参数：

```text
H103eb XNU:     7c4af02f609ae748b4f2e71fcb3b0efb40d660e7bde8bec90412a03dcf61d14d
H103eb kernel:  91959feaa38bf249f91cfe6b534968b00498817cc5d704bffe377169d00ba691
H103eb payload: 32963f1f9e9f4e90af00fa1cbb3cef829cd143fbf0e7c986902253f53959cfc1
H103eb boot:    614c83a5d912ca4c5ab815190e95122a30a2f972518d89fcee1fc73763ea1f59
```

H103eb-bdargs 上机确认右上 2×2 出现。H103ec 保持同一个 H103eb 内核，
只把 H103bd payload 参数加一项 `sheng-log=1`，让独立的 2 秒 slot 线程
真正写入 `userdata_ios`：

```text
H103ec kernel:  91959feaa38bf249f91cfe6b534968b00498817cc5d704bffe377169d00ba691
H103ec payload: 6160640a420c170ab779af16af94e41bea58fe531e2d8f67b763c021b0330424
H103ec boot:    a03f380ded8ff9a3519f217abf0e4f966ca782bf027665e86ce04ae22a20ae1a
```

上机判读：2×2 仍在且 TWRP 能读到持续更新的 `SHLOG001` 最新 slot，就说明
H103bd 面板 + 2 秒持久日志可以共存。

H103ed 把右下角三个 16×16 状态块移到左上角（CPU 频率 x=0、A540 x=20、
心跳 x=40），并在 payload 里补上 `native-cpufreq-early=2`。当前内核
（H103eb）其实已经链入了 `NATIVE_CPUFREQ_EARLY` 代码，只是 H103bd 参数
没有这个 boot arg；H103cz 当时传了，所以频率块是绿色。

```text
H103ed XNU:     ed750931b794ebe206e1fd5aada71d5459fba0268b77e597b33c010de5e4fdb9
H103ed kernel:  fec7abd797ce920211cae12f9135ae5e05b3ac9cca70e91392123cdb3f4fbc40
H103ed payload: 0d0a2176c87ee724b9a3c17c546e9d0708fddfbd4c3b17331b927235c5622b4d
H103ed boot:    59908da2f8804aa2723b1d10ad57254001356129e38effca9bcdeb0850c4c059
display:        adf38de
```

注意：`NATIVE_CPUFREQ_EARLY` 目前只存在于 Mac 构建缓存里的
`build/sheng-platform-power/ShengPlatformPowerGlue.o` /
`libShengPlatformPower.a`（11 月 4 日 15:57），当前设备仓库的
`ShengPlatformPowerGlue.cpp` 已被覆盖成短版本。重建该 archive 前必须先把
早期 CPUFREQ 源码恢复，否则会丢失 `native-cpufreq-early=2` 的实际编程。

H103ed 上机后 TWRP 读到的 `SHLOG001` 仍是 snapshot 写的
（`state=2`、`rounds=1`、`slots_written=0`），slot 线程没有更新 header。
H103ee 加诊断：slot 线程启动前后各打一条 `NATIVE_UFS_HB: slot ...`；
`h103SlotWrite` 前 8 次尝试打印 ready/lock/dma、body 写结果和 header 写结果；
`h103Snapshot` 不再把 `slots_written` 清零。

```text
H103ee kernel:  96321f31312d788dca3410eea773b9a4bad638351256061767df3f6d6124443f
H103ee payload: efa7b4ff54af63d3c7392dbf68e02e5a929dd398078cb7442aee3094b5dbaedb
H103ee boot:    b742d928fea5eb7dbc7e4f92245dcacbd0969584462fabf192957783c708e34a
```

H103ff 在左上角增加第 4 个 16×16 slot 状态块，不再依赖 TWRP 判断线程：
黑=未就绪，黄=窗口就绪但写失败，绿=slot+header 写成功。UFS 侧导出
`native_h103_slot_state`，display 侧读取。

```text
H103ff kernel:  4bd10ad1b1d3d205e4edb5661102e581bf4c8c551615104985bd3743e1b852f8
H103ff payload: 4692224ecbe160d584fab0bcb8b3d18f6e6d1076c53c7b42df202610fc077057
H103ff boot:    cccf4fad7c75a430ac15bf59538bcfc17432bebefeb5cb3388dcc24dc5902489
```

H103fg 把第 4 块改成始终可见：红=线程未进入，蓝=线程已进入但窗口未就绪，
黄=窗口就绪但写失败，绿=写成功；第 3 块心跳改为白/橙交替，避免黑块看不见。

```text
H103fg kernel:  79a653767ab035a9c69068a810d96e0e4bdf781e3a7200734168262ace4556df
H103fg payload: 61b46a19fe95f018b6214f16c6d19f076a7c73c23e4b8ba5b1a973d3429771f3
H103fg boot:    e456efd8a12681b40131affe0d026c09bc8506cabc76fd13745b9c1c91c33b2a
```

H103fg 第 4 块为蓝色，证明 slot 线程已进入但一直停在 `IOSleep`；日志里也
没有心跳的周期性 `NATIVE_UFS_ALIVE` 和 20 秒 `logThread` snapshot。H103fh
把 2 秒 slot 计时移到 UFS 完成路径（2×2 重绘本来就是这条路径），不再依赖
线程唤醒。

```text
H103fh kernel:  f21ee606da951562994a75c0c243990ba096c14894ec3af33ac66838b5579feb
H103fh payload: 9953381de226ca1b1ceb5fb61c2a8aa12895d63f1557b89d062c96110a8629e3
H103fh boot:    36f6938ee1de01756706c7adbdb312e8fcb5de8702994b712c56bcd2a3410dfa
```

H103fh 上机停在 UEFI：slot tick 放在 `ufsCommand` 完成路径，而 `readBlocks`
仍持有 `fLock`，`h103SlotWrite()` 再拿 `fLock` 造成自死锁。H103fi 把 tick
移到 `readBlocks` / `readWindowBulk` 的 `IOLockUnlock` 之后。

```text
H103fi kernel:  b868e9007b5b93e7a3e287c00a828bbe5640bda2ae33153a931b1b13757146a5
H103fi payload: 90e6c1fc2b9926128dcc69bb6e292d3d31e05628e9ec8d0c76a2af9fd04b4f3c
H103fi boot:    cf87300170090acb019b5cdfc5f76157724824befef3e5dd1bf985f8eabbb393
```

H103fi 上机成功：`slots_written=109`、`state=3`、`write_errors=0`，slot body
是最新的 65s–264s 日志。H103fj 做静默：`gH103Quiet=1`，payload 去掉
`-v`、`debug=0x14e`、`boot-progress=2`，保留 2×2（已与 quiet 解耦）和
UFS 读路径上的 2 秒 slot。

```text
H103fj kernel:  d0b0089b5f53f8e720ce575a3f00aa3b637b959dac5468b8d636e10277a9516e
H103fj payload: c1da6c3ffc7f9fb2b7db57f59ac927db4c0725c864fb2c240612520ac65de444
H103fj boot:    85c34f005809eada4d6eb02284cc26bd9d540d232024e26388333120158fcf35
```

H103fk 把 slot 节流从 2 秒降到 500 ms，并只在 `msgbufp->msg_bufx` 变化时
写；slot 历史约 2 分钟（247 × 0.5 s）。

```text
H103fk kernel:  90ed23031b45f195fca40f631cd7e9e7bfd45985e322fe7c88def7e8fce1d6cc
H103fk payload: 17b7894192bfaffdd91e40b21eb02b1b160a0cb51c12daeeb83dc918a508a8ed
H103fk boot:    f3c461aeb8510db31bb6d5e9c22dedb99c84e7e550dad100bdc1008cfb749626
```

H103fk 上机日志停在 `KextLog: driverkitd is active`，左上第 3 块（UFS 活动
心跳）同时停止。H103fj（2 秒 slot）在同一位置停下，说明 500 ms 不是根因。
第 3 块由每 64 条 UFS 命令的 `drawTestPattern()` 驱动，10 秒心跳线程从不
醒来，所以 I/O 空闲时它本来就会停，不能证明内核死机。

H103fl 在 UFS 驱动里加 1 Hz `IOTimerEventSource`（不改 display archive），
用 `h103-hb-timer=1` 开启；`h103-slot=0/1/2` 选择无 slot / 500 ms / 2 秒；
`logWrite` 改为 2 秒锁超时；header 的 `uptime_s`/`write_errors` 现在有值。

```text
H103fl kernel:  44cea2a033539590f0e357cba95908471122d2f278f5d0f38011c0d35a83cf44
H103fl payload: cfa7f7fb916e17f0882a5515b9cc019235282a386721727bfb0059de1565b6a7
H103fl boot:    625be88506e2b4b8a06eeec2f4ac92a08a7852815b0bdc885171bc122c4d7b4e

H103fl-noslot payload: c5985776b6c248aa2fdf27e4f1b759f8237c1a240fe36aa2c0d6002f14776465
H103fl-noslot boot:    e9fdecefef16fe6020da360b2f960e31ca38197f00380888014fa73415512d94
```

H103fl 上机：`IOTimerEventSource` 的 `start` 成功，但日志里没有一条
`fire=`；1 Hz 定时器从未触发，所以第 3 块静止不能说明内核死机。
header `uptime_s=167` 与最后一条日志 `1667.5`（UFS 起点 1500.2）一致，
slot 写入一直正常到停点，`write_errors=0`。

H103fl-noslot 的串口最后停在 `logd_helper`，但 H103fl 的 msgbuf 继续到
`driverkitd active`，两者不是同一停点；noslot 只是控制台输出先停。

H103fm 做两个 UFS-only 诊断（不改 display archive）：

- `h103-hb-timer=2`：用 `timer_call`（定时器中断上下文）而不是 workloop
  线程，尝试真正的 1 Hz 心跳；
- 消息不变时每 2 秒只重写 header，`uptime_s` 继续前进就证明停点之后
  UFS 读路径还活着；
- header 的 `export_*` 改名 `diag_*`：`diag_cmds`、`diag_last_lba`、
  `diag_last_bytes`、`diag_flags`（bit0/1=in-flight，bit8+=timer fires）、
  `diag_loops`。

```text
H103fm kernel:  8b6da448afb00e64868bcee1c0f7bd49026a72f860663e0dfaf0c77fd9b52698
H103fm payload: 8bb388f503fe8ff97ca5a27db30eff6ff5bc2877ed009f02893b58f04c47fd58
H103fm boot:    fd9c21497e22d95381ee661c7cc5a1067014d673f100de0e0839910cf46d2e92
```

H103fm 上机：`timer_call` 也没有触发（前 8 次 slot 都是 `fires=0`），
说明 kernel thread/timer 唤醒在这套 bring-up 里整体不可用；第 3 块不能
作为死机指示。日志实际继续到 `eligibilityd`（1077.4，UFS 起点 907.7），
header `uptime_s=169`、`diag_cmds=31170`，说明停点之后 UFS 读路径还活着。
`diag_flags=2` 表示最后一次 header 写入时有一个 window read 在飞，但日志
继续，不能据此判 stall。

H103fn 做 post-root `IOGPUFamily` 加载测试（不改 display archive）：
`h103-load-iogpu=1`，在 `native_boot_flags & 8`（SpringBoard exec）后从
UFS 读路径调用一次 `OSKextLoadKextWithIdentifier`，只记录返回码。

```text
H103fn kernel:  98117070e625c96591991b0c61198192a15cbe89686f08619b1ba5fb17fa8190
H103fn payload: 3edc860a3a7008efce00d4601bcdc49738ac8d47a766e020c3fdc68701d023e1
H103fn boot:    7ba4b9a64256f7ed7825d82ffedbcd0e229a16ae0218765ebd8abefd37d163ac
```

H103fn 证明 post-root 也无法用 `OSKextLoadKextWithIdentifier` 加载
`IOGPUFamily`：`rc=dc00800a`（`kOSKextReturnDisabled`），因为内核按
`NO_KEXTD` 构建，`sKernelRequestsEnabled=false`。

P1 只改 prelink roots（Mac 设备仓库 `board.toml` 加
`com.apple.iokit.IOGPUFamily`），不改 display archive。prelink report：

```text
components 29 -> 30
new component: com.apple.iokit.IOGPUFamily
IOGPUFamily __TEXT/__TEXT_EXEC/__DATA_CONST/__DATA 合计增加 223,097 B
现有组件 VA 不变
```

```text
H103fo kernel:  69885c070e883b7b1f8a156afe649b71fc6230c250277a632bf28e3cfb1f03d1
H103fo payload: 04f2fcee81bb27bdf05bd948050c83556764f5a05fec54aab51b4d8932e97077
H103fo boot:    bc34cb8e49fe81ee82f4c8ba7aefe6e25d6626f4a14a65eebf27db079171cfff
```

H103fo 上机：`NATIVE_IOGPU_LOAD: rc=0 flags=8`。prelinked `IOGPUFamily`
已注册，`OSKextLoadKextWithIdentifier` 命中已加载路径，`NO_KEXTD` 不再
阻挡。

H103fp 开始 P2：A540 类在 display probe 的同一个
`preModLoad`/`postModLoad` 窗口里注册，随后发布裸
`IOAcceleratorES`；移除了旧的 `OSKextLoadKextWithIdentifier` 调用和
`MetalPluginName`/`MetalPluginClassName`。

```text
H103fp kernel:  12d7513a347bb4315ba46f6c1f663bc6db35e4fd61c83989c567df704d2375c4
H103fp payload: 8d6bf887c1af74c9f36dddc57d377d866c8c32ce720e4bc8b4eb4dde239b94e8
H103fp boot:    24bc548352aa0dfc991cfbcad14643c87aa382bcfb1dd4647c4522007cc1b8e6
```

H103fp 上机 panic：`far=0xfffffff006aeb698`，正好是旧
`ioaccelerator-base-abi.json` 的 `metaclass+0x10`。旧 JSON 来自 candidate
`da673101...`，当前 prelink 是 `12d7513a...`；旧地址不在当前 IOGPUFamily
区间，简单加 slide 落在 `__PLK_TEXT_EXEC` 的未映射空洞，仍然 abort。

H103fq 用新脚本 `scripts/audit-target-accelerator-base-current.py` 从**当前**
prelinked kernel 静态推导 ABI：

```text
metaclass    0xfffffff00caeb688
vptr         0xfffffff00bd439a0
C2 aliases   0xfffffff00abd3b20 / 0xfffffff00abd3b40
D2           0xfffffff00abd3b64
getMetaClass 0xfffffff00abd3bac
```

重建 display archive 后 accelerator bindings 指向这些地址，再重建 kernel/prelink。

```text
H103fq kernel:  0cc2ec0454595b44bbc2f6541a345f8e9de8d567f749c1a7dab94e99c7a902fc
H103fq payload: 75ff3251ca43b457a2c7e8fde36ae7f273b6def2dbf75474dbf0057430158a4e
H103fq boot:    a7a240200c7fdc96a9ca3e369e3f1be073d61f40ff72c53bccf6e91bc41b484a
```

H103fq 在 UFS probe 阶段就 panic：`OSMetaClass::addInstance`，
`x0=0xfffffff00caeb600`，`far=0`。原因是新的 accelerator 绝对符号
`IOAcceleratorES::gMetaClass=0xfffffff00caeb688` 落在 prelinked
IOGPUFamily 数据里，作为 `.globl` 绝对符号被 prelink/符号表当成 kernel
target，早期 UFS 对象的 metaclass 指针被错误绑定。

H103fr 把 accelerator bindings 改成 `.private_extern`，让它们只参与本
次链接、不进入 kernel 导出/prelink 绑定表（`nm` 中已从 `A` 变成 `a`），
地址仍是新 ABI 的 `0xfffffff00caeb688` 等。

```text
H103fr kernel:  0922e9d182674e9bc014c79611efd170667910a3b5c32518bfe82b4873b79268
H103fr payload: 455fd32c07acc61619824fb32e9b5a769bd99624ac1111cde3b1cb53cbd22d99
H103fr boot:    ec0d60362c3cd17d5d776fbe2c5a05be60530f43dc3607f5f96eb03a81eddeb1
```

H103fs 改为 property-only stub：`NativeA540AcceleratorProbe` 直接继承
`IOService`，只设 `IOClass=IOAcceleratorES`。不再引用 `IOAcceleratorES`
基类；final kernel 的 `nm` 里已经没有 `IOAcceleratorES` 绝对符号，
accelerator bindings 对象不会被链接。

```text
H103fs kernel:  ae7b40a74143a86712d45221a76d6609a70a22c1c0ef886edaf024fb5892144c
H103fs payload: 90e6802e44c124b898f5dff3a4bdc65f700ca8da6ebf4d32bef67f8050842b6e
H103fs boot:    09c31cc705e32a2c37a5c7a2bf29735d3a7e3d8edfdd11e4a3482bcdfb7fcb39
```

H103fs 上机：A540 服务在 16.9s 发布，A540 块变绿；右上 2×2 左上角绿、
其余三块灰。日志里 SpringBoard/27 已 exec，但只有
`xpcproxy ... backboardd`，没有 `comm=backboardd` 的实际 exec；最后一行是
`KextLog: driverkitd is not active`。说明提前发布假
`IOClass=IOAcceleratorES` 服务把 driverkitd/backboardd 的交接拖住了。

H104a 保留 A540 类注册在 display probe 的 pre/post 窗口，但把服务发布移到
UFS 读路径，只在 `native_boot_flags & 4`（backboardd 实际 exec）之后调用
`native_a540_accelerator_probe()`。

```text
H104a kernel:  c5023e1e481488852a1f83ed9bd632976c146a45cbdf47a34adede6b95f082cb
H104a payload: 58d7463c2dcc0bbebc5e37a3e3aa89a4059b5da115df31adc6cfef4c5364c3a2
H104a boot:    72a06e3965a012139e50f61546f1729afbd9e49c605ae5f07764b0af34fed78b
```

H104a 上机：没有 `NATIVE_A540_PUBLISH`，也没有 `comm=backboardd` 的实际
exec；日志仍停在 `KextLog: driverkitd is not active`（199.3s），2×2 左上
仍是绿色。延迟服务发布没有解决问题，说明差异来自 **A540 类在 display
probe 的 pre/post 窗口注册**，而不是服务发布。

H104b 完全移除 A540 static init/类注册，回到 H103fo 的 display archive
行为；A540 对象仍在 archive 中但不再注册。

```text
H104b kernel:  5ec6ddd29fe941883fb3777e15d5a27040c910ae4569bdc24610f943c3fa0e40
H104b payload: 4dda07372741ebc7b65a0f6cf873c974fc9c670b8f167f4ca55eeebb68ee84dd
H104b boot:    8cc632f2f1fc12714fd7a05fae6a76face35ac73714962db5f2b19171688dcec
```

H104b 上机恢复到已知显示关口：

```text
519.691 backboardd/55 实际 exec
526.480 NATIVE_DISPLAY_OPEN service=NativeLegacyDisplay
        process=IOMFB_FDR_Loader grant=backboardd match=0
526.505 NATIVE_LEGACY: client enter pid=78 comm=IOMFB_FDR_Loader
531.238 KextLog: driverkitd is active
```

2×2：左上白（SpringBoard+backboardd）、右上黄（IOMFB_FDR client）、
左下蓝（calls<10）、右下灰（无 transfer/swap/IKit match）。A540 块黑是
预期。结论：backboardd 已起来，但先打开显示的是 IOMFB_FDR_Loader；
backboardd 仍未打开显示。

H104c 在 display client 的 externalMethod wrapper 里打印前 16 次
`selector/status`，用来定位 FDR loader 停在哪个 selector。

```text
H104c kernel:  365f6f6eb22bb2331a386d7b179a113bb57bb55bf219a917fa7475ef2206a22b
H104c payload: fc455727471d8c5be0e006029741fed79b6e59a1d792ffac91a14b7dca7f6d22
H104c boot:    e3ba65d79b7c8f62c24e8d0ef2a62c983517df979e478a550b0b5bb3e3fd80ef
```

H104c 第二次上机（16:33 日志）：

```text
189.199 NATIVE_DISPLAY_OPEN service=NativeLegacyDisplay
        process=IOMFB_FDR_Loader grant=backboardd match=0
189.226 NATIVE_LEGACY: client enter pid=78 comm=IOMFB_FDR_Loader type=0
189.251 NATIVE_LEGACY: client observed status=0
189.276 / 189.303 另外两次 IOServiceOpen
199.026 KextLog: driverkitd is not active
199.466 KextLog: driverkitd is active
```

没有 `NATIVE_LEGACY: client sel`：FDR loader 只 open 了显示服务，**没有
调用任何 externalMethod selector**。所以 selector 日志不是当前阻塞点。

2×2：左上白、右上黄、左下蓝；右下上半灰（无 transfer/swap），下半**橙**
（`native_boot_flags & 128`）：backboardd 已经开始做 IOKit matching，但
匹配的不是 IOMobile* 类。

H104d 增强 IOKit trace，打印 backboardd 前 32 个 matching dictionary 的
`IOClass` / `IOProviderClass` / `IONameMatch`。

```text
H104d kernel:  009631ae5ed1e6c72ce7d4855374a2a1f74b960c2f42d1e72921ea807559af12
H104d payload: 88de84fdf0b90bde8e6440d5568a9e6cdae673f1d173fe1fa79ff8f94861ce14
H104d boot:    9a7afb45b214a1db31e3099aba6615219a9504bf55c593a383b7e859d7a5cbbb
```

H104d 多次上机都到不了左上白：左上变绿（只有 SpringBoard）后停住，
`NATIVE_IOKIT_MATCH` 从未打印。H104d 的 kernel text/layout 改动把
backboardd 之前的停点带回来了，停止使用 H104d；恢复 H104c 的旧 IOKit
trace（只置 bit 128）。

离线检查 21H461 的 OS cryptex 字符串：

```text
Metal:    MTLRegisterDevices ... IOAcceleratorES
QuartzCore: CAEnableMetalWhippet ... IOAcceleratorES
```

确认 backboardd/CoreAnimation 匹配的是 **IOAcceleratorES**，不是
IOMobile*。之前只设 `IOClass=IOAcceleratorES` 属性的 stub 被忽略，因为它
不是真正的 `IOAcceleratorES` 实例。

H104e 不再注册本地子类，也不在 kernel matching 路径打印日志；它用
prelinked 的真实类：

```text
native_iogpu_accel_probe()
  OSMetaClass::allocClassWithName("IOGPU")
    fallback "IOAcceleratorES"
  attach(IOService::getResourceService())
  registerService()
  h103-iogpu-start=1 时才调用 start()
```

只在 backboardd 实际 exec（bit 4）后调用一次。A540 状态块：
绿=已注册，红=alloc/attach/start 失败，黑=未运行。

```text
H104e kernel:  bdb070e20c8cd55b6e4d7577d14c625464354fd06325c79316103bf96ddce50a
H104e payload: e15f7962d99069be89f35a73cf99554c8d62fc8b5025765272d90de429d4a67c
H104e boot:    108a5181ec655665fc9bead733c6674fe328ee538c7feb84db2674c215c21130
```

H104e 上机仍是左上绿，A540 黑（backboardd 未 exec，探针未运行）。检查
H104b/H104c/H104d 的日志后确认这是 **launchd 启动顺序 race**：

```text
成功:
  driverkitd 实际 exec -> IOMFB_FDR_Loader exec -> backboardd 实际 exec
  -> loader 在 backboardd 之后 open 显示

失败:
  IOMFB_FDR_Loader exec -> driverkitd 实际 exec -> backboardd 永不 exec
```

H104d-green 的 loader 比 driverkitd 早 0.26s；成功时 driverkitd 早约
1.0–1.1s。H104b 也多数停在绿，说明不是某张镜像的独立回归，而是 loader
抢跑后占住显示、backboardd 无法 exec。

先做两个只改 boot args 的 H104b 对照：

```text
boot-H104b-slot0.img    h103-slot=0        关闭持久化日志/slot 写入
boot-H104b-noiogpu.img  h103-load-iogpu=0  不加载 IOGPUFamily
```

```text
H104b-slot0 boot:   1aa9829522cf7f79713dc8ce577c084f83c564485c5f41aa35025ee2556e7fc0
H104b-noiogpu boot: 90b8d14229944b5308d0995b5371472a4abaab2fc233b39e6685ab141f455aae
```

H104b-slot0 上机：**能稳定左上白**。确认早期 slot/UFS 写入让 driverkitd
输掉 launchd race；noiogpu 不必再测。

H104f 把 slot/header 写入推迟到 `native_boot_flags & 4`（backboardd 实际
exec）之后；IOGPUFamily load 和真实 accelerator 探针保持原样。消息缓冲区
在等待期间继续累积，第一次 post-backboardd 写入仍会把早期启动日志落盘。
心跳线程/2×2 不受影响。

```text
H104f kernel:  fbbc84592a7b099e27c68627917433d471da53a5c74acb86d04f451245209fde
H104f payload: bf806aa279e88b3ed0dcc872826218515be8f71cae39caa5b0bc449da5accd48
H104f boot:    7a76334f2ff0d43d7f6ee087d7132c88926716d87f1b151ce081a67c9f543232
```

H104f 上机：左上稳定白，slot gate 成功；backboardd 之后日志恢复。关键行：

```text
204.481 backboardd 实际 exec
204.521 NATIVE_IOGPU_ACCEL: class=IOAcceleratorES object=0 service=0
204.543 NATIVE_IOGPU_PUBLISH: rc=0 flags=f
```

`IOGPU` 和 fallback `IOAcceleratorES` 的 `alloc` 都返回 0，说明它们是抽象
类或不可分配。H104g 逐个探测 `IOGPU`、`IOGPUDevice`、`AGXAccelerator`、
`IOAcceleratorES`、`IOGPUFamily`，分别打印 metaclass/obj/service，寻找
真正可分配的 concrete 类。

```text
H104g kernel:  26956e603bb39ad001738b3b79a373409737bb00367d90ef8f30ba8c2306bb90
H104g payload: 4946a49a82ba03ed53f554b09cd62004f3ecd89cc00e0356dc1bfcffcb4ebf6f
H104g boot:    c2574fe9f71574839cd24a630eb725573b22067e12f093efab73f557f2ef459a
```

H104g 上机仍停在 backboardd 之前（左上绿）；多类 probe 没有运行，说明
archive/kernel 布局变化又输掉了 pre-backboardd race。放弃 H104g，H104f 仍
是稳定白基线。

新增组合对照：

```text
boot-H104b-slot0-noiogpu.img   h103-slot=0 + h103-load-iogpu=0
SHA-256: 7928c93baab2727ebdba8db9454e573e7b889a4a42ccbaa62aca6af172a4cd5a
```

无持久化日志，2×2/心跳仍运行；用于判断白之后的显示 open 是否受 slot
写入或 IOGPUFamily load 影响。

H104b-slot0-noiogpu 上机：左上白，右上/右下灰；白之后等了约 10 分钟
仍无显示 open。`slot` 和 `IOGPUFamily load` 都关掉仍复现，所以白之后的
卡点与两者无关。控制台还能继续到 `datamigrator` 等，loader/backboardd
没有 `NATIVE_EXIT`，是活着但被阻塞。

H104i 加一个只读的进程状态 dump：

```text
osfmk/kern/task.c: native_proc_state_dump()
  IOMFB_FDR_Loader 78
  backboardd 55
  driverkitd 63
  launchd 1
  每个线程: tid/state/wait_event/continuation/parameter/options
```

由 UFS 心跳线程在 backboardd 实际 exec 后 30–40 秒调用一次；镜像仍用
`h103-slot=0 h103-load-iogpu=0`，无持久化日志，dump 直接打印在控制台。

```text
H104i kernel:  b68d99796e1496c3b9b45b183498a5e11892b77423fb23884a181f2778cddfc3
H104i payload: d99ad12648e7603b4f566ef68f5d258ec11a74f3016f7ca93bc9d4f12ad8d4a3
H104i boot:    4647216c5ddb03c43d5118b9db577402250a630d0382460b5b034600e20278e1
```

判读：看 `NATIVE_PROC_DUMP` / `NATIVE_PROC_THREAD`。重点比较 loader 和
backboardd 的 `state`/`wait_event`/`continuation`：
- 都在等同一个地址/continuation：找到该等待点；
- loader 在 mach/IOKit 等待：查对应 service；
- 两者已运行但没 open：查用户态/launchd 依赖。

H104i 上机：左上白，2×2 右上黄、左下蓝，日志出现

```text
NATIVE_DISPLAY_OPEN: service=NativeLegacyDisplay process=IOMFB_FDR_Loader grant=backboardd match=0
NATIVE_LEGACY: client enter pid=78 comm=IOMFB_FDR_Loader
```

说明 loader 这次成功打开了显示。但 10 分钟后仍没有 `NATIVE_PROC_DUMP`：
心跳线程没有继续打印 ALIVE，说明它在 2×2 draw 或 dump 的 `task_lock` 上
停住了。

H104j 调整：

```text
dump 移到 native_legacy_test_pattern() 之前
backboardd 实际 exec 后不再 draw 2×2（避免 loader open 持有显示锁时卡住）
task_lock -> task_lock_try，失败打印 task lock busy
dump 增加 begin/find/end 日志
```

```text
H104j kernel:  7e85bc444764676f410ba0481826044eaf9056962386f35727f75a627fdf04c3
H104j payload: e2033722ca0ca18a4575e481c14ff69a58240dba38e9ef3be216e7504c959dfb
H104j boot:    3f161865f038d47891ab9724b70fb98f111ea627590b9585b91dea6388ef9f35
```

判读：左上白后 30–40 秒应出现 `NATIVE_PROC_DUMP: begin/find/...`。2×2 可能
停在 backboardd 之前的状态，这是预期；以控制台 dump 为准。

判读：看 `NATIVE_IOGPU_ACCEL: name=... mc=... obj=... service=...`。
- 某个 `obj/service` 非 0：真实 concrete 类可分配，attach/register 后看
  A540 绿和 CA 反应。
- 全部为 0：IOGPUFamily 在当前 prelink/设备上没有可分配 concrete 类，
  下一步要么做安全的本地 `IOAcceleratorES` 子类，要么提供 provider。

判读：左上应稳定白；backboardd 之后持久化日志开始写入，应包含
`NATIVE_IOGPU_ACCEL` 和 A540 状态。若第一次大块 dump 影响 loader 打开
显示，下一步把 dump 拆成小块/限速。

判读：如果 `slot0` 能稳定白，说明 slot 写入/UFS 争用让 driverkitd 输掉
race；如果 `noiogpu` 能稳定白，说明 IOGPUFamily load 影响时序。两者都无效
则做 H104f：在 `newUserClient` 里把 FDR loader 的 open 延迟到 backboardd
实际 exec 之后。

判读：先看 H104e 是否恢复到左上白（backboardd 实际 exec）。然后看
`NATIVE_IOGPU_ACCEL: class=... object=... service=...` 和 A540 块：
- alloc 返回 0：真实类不可用/抽象；
- attach/register 成功：真实服务已发布，观察 CA 是否接受；
- 如果仍然只有橙/灰、显示器不打开，下一步补真实 accelerator 属性/ABI，
  或尝试其它真实类。

判读：看 `NATIVE_IOKIT_MATCH: class=... provider=... name=...`。如果
class 是 `IOGPU`/`IOAcceleratorES`，下一步提供对应服务；如果是
`IOMobileFramebuffer`/`IOFramebuffer`，调整匹配/属性；如果全是 `-`，
下一版打印完整 matching dictionary XML。

判读：看 `NATIVE_LEGACY: client sel pid=78 selector=... status=...`。
若某个 selector 返回非 0 或之后没有新 selector，下一步实现/补该 selector
或检查 FDR loader 等待的 kext/数据。若 selector 正常但 backboardd 仍不
打开显示，转向 backboardd/CoreAnimation 的 provider 等待。

判读：应恢复到 `driverkitd is active`、`comm=backboardd` 实际 exec、2×2
左上变白；A540 块会变黑（没有 probe）。若仍停 `driverkitd not active`，
说明 A540 类注册也不是原因，需要查 H103fo→H103fs 之间的其他差异。

判读：应看到 `NATIVE_EXEC ... comm=backboardd`、2×2 左上角变白，然后
`NATIVE_A540_PUBLISH: rc=... flags=4`；再看 client 块是否变化。若仍停在
`driverkitd is not active`，说明提前发布不是唯一原因，需要查 display
archive/IOKit 匹配。

判读：先确认不再在 UFS L5 后 panic；若出现
`NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)`，看 A540 块和
2×2 client 是否变化。property stub 可能被 CA 忽略；若被忽略，下一步只能做
运行时真实基类解析。

H103fr 仍然在 UFS probe 的 L5 后 panic，`OSMetaClass::addInstance`，
`x0=0xfffffff00caeb680`、`x21=0xfffffff00caeb600`。`.private_extern`
没有解决问题，说明不是导出符号/prelink 绑定表的问题；A540 的绝对
`IOAcceleratorES` 基类绑定本身在早期 IOGPUFamily 类元数据/实例登记里
造成了破坏。

结论：本地 `IOAcceleratorES` 子类 + 绝对基类地址的方案在当前 prelink
下不可行。下一步只能改成不绑定基类的 property-only `IOService` stub，
或在运行时解析真实基类；H103fo 仍是可用回退。

判读：应出现 `NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)`，
A540 块变绿；若仍 data abort，核对 `far` 是否等于 `0xcaeb698`。

判读：日志应出现 `NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)`，
A540 块变绿；然后看 backboardd/2×2 client 是否变化。若停在
`Waiting on IOMedia UUID 04769D26`，是 display archive 改动触发 race，回退
H103fo。

判读：若 `IOMobileGraphicsFamily` 的先例成立，prelinked 的
`IOGPUFamily` 应让 `NATIVE_IOGPU_LOAD: rc=0`；这验证 prelink 注册，不改
display archive。若 rc 仍非 0，先查 prelink 注册，不要动 A540。

设备仓库已整理提交：`2400c54`（config）、`19d46d6`（ufs）、
`6fef5db`（power）、`9ad41b0`（adt）、`2bf3c61`（patch tool）、
`097d00c`（lock + bring-up inputs）。origin/main 原本已在 `5ad54e2`
跟踪 11 个 DinnerABC 文件、`SystemVolume.im4p` 和 `cpu-tables.h`；本地
H103 线已 merge origin/main（`1ca9258`），这些文件不再被忽略。设备仓库
`main` 已 push 到 GitHub（`c1e91be..1ca9258`）；`GopFramebuffer` 的
`53f5d20` 也已 push 到分支 `h103-a540`，供 H103fp 的 submodule 指针使用。

### 关键产物

```text
H103au boot      2a263cce4b0ed4fdb7c35ef0e0ae35d39d36ebeef9143b9061865adac1f56288
H103ax-1g boot   73cf3927771e3191f38ae8cf89daaf10a883e3d35ecdd9ef4780699c0297f84e
H103ay-4g boot   f148919d96db01302a53d72d6061445a89cfe652a9ca33fdc14f61a1ba41cd3e
H103az boot      3bb5b2bebe792d0b45ba9823d1e7bbc7adb78ca7adb040d47f63723e327990c5
H103ba boot      3195072d616d9be0411d73903c6468b9d6aac40423c3d92c342ad807cd8190f2
H103bb boot      d9b91fc6a29ecb90822da84c31923539b5160b57927ccd1cc60cd24e0b1b2130
H103bc boot      e5349527c74df987e5e21bcd670febe7be8eac41260a9556e719c34a458a42c6
H103bd boot      8284f2616412cea7e98cdb9d929802b4b2cdd6bb7b8af536210a38c08c9910f3
H103be boot      6ce2a1e2584055903edcb383432da9cc6eb478e7f44b21ec3e5059db7a4694ae
H103bf boot      768f8eb8c01995df59d6cd8eb24d7080d4dd29d0e41400bd2857193f6262aced
H103bg boot      ae9c39268b5cd4e49ee1dcf4cdbb0e933b673ea63c4016995ab23fd50677e0a6
H103ea boot      a07fe2567b43edcf7cbd58a86a8d4474cae49ac84e79b667e074205e1b4e2f5e
```

## H104k 上游对照（2026-11-05）

对照 `UniXNU/UniXNU` `main` `13e5973`、`UniXNU/GopFramebuffer` `main`
`e47c1b8` 与上游设备记录（alioth / sirius / sm-t970），完整记录见
`diagnostics/H104k-upstream-display-gate-2026-11-05.md`。要点：

- 上游没有“让 backboardd 取 display provider”的补丁；同症状（`CLIENT
  calls=4`、`SWAP calls=0`）在 alioth 上的结论是“先让 backboardd 起来，
  再给一个可打开的 accelerator”，display 是链路末段。
- sirius 与本板同 OS profile（21H461 / Legacy / 无 GPU）：display、client、
  power 1、SWAP 全 accepted + 全 CPU copy 都成立时画面仍黑；上游同样未解。
- A540 stub 的问题不是属性而是缺 `newUserClient`；`scripts/data/
  ioaccelerator-base-abi.json` 的 `candidate_sha256` 是 `12d7513a…`，
  与 H104j kernel `7e85bc44…` 不符，这解释了 H103fp/fq/fr 的
  `OSMetaClass::addInstance` abort。
- 本次只并入上游 `zzwb-native-sandbox-grant-set-properties.patch`：把
  `NativeSandboxGrantProcess` 授权扩展到 `setProperties`（backboardd 的
  `FadePeriod` 会被沙箱拒绝）。已在 `xnu-10063.141.1` 的原始
  `iokit/Kernel/IOUserClient.cpp` 上按名字顺序验证可应用（`zzw` 之后
  `offset -12`）。
- 未并入：`native-work-interval-instance`、`native-union-lower-directory`、
  `native-lookup-trace`、`zzyb-native-cryptex-os-view`、
  `zzyc-owner-skip-launch-constraints`，以及 GopFramebuffer 的 13 个
  GPU/direct-scanout 提交（CPU 路径修复基座已含）。
- 影响：新增补丁会改变内核文本布局，下一次 kernel/prelink/boot 必须重新
  记录哈希，不能沿用 H104f/H104j。
- 远端：本仓库已加 `upstream` remote（`https://github.com/UniXNU/UniXNU`），
  与上游 merge-base `e95b37d`（2026-10-22），落后 561 / 领先 431 个提交；
  整体 merge 会把 GPU/Turnip/Metal/baseband/Wi-Fi 组件一并拉入，暂不做。

## H105 心跳线程不唤醒导致 dump 永不执行（2026-11-05）

H104j 上机没有任何 `NATIVE_PROC_DUMP`。复查本机保存的 9 份
`h103-log-*.txt`（`153658`/`155325`/`160954`/`162153`/`163306`/`165109`/
`172713`/`190513`/`194941`），每份都只有一行 `NATIVE_UFS_HB: enter`，
**没有任何一行 `NATIVE_UFS_ALIVE`**：`heartbeatThread()` 进入循环后停在
`IOSleep(10000)` 上不再返回。H104i/H104j 把 dump 放在这个循环里，所以
`gH104BackboarddTicks` 从未赋值，dump 永远不会执行；H104j 的"移到 draw
之前"因此没有效果。2×2 一直能画，是因为它由 UFS 完成路径每 64 条命令
重绘，与心跳线程无关。

最后一份日志（`194941`）的时序也解释了"30–40 秒"这个窗口：

```text
227.664  NATIVE_EXEC: ... comm=backboardd        （flags |= 4）
227.721  NATIVE_IOGPU_ACCEL: class=IOAcceleratorES object=0
231.477  日志结束（backboardd 后约 3.8 s）
```

即使心跳线程正常，30 秒后的 dump 也落在这份采集窗口之外。

H105 只改 `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：

- 把触发器移到 UFS 完成路径的 `(gUfsCommands & 63) == 0` 分支，并放在
  2×2 重绘之前——显示 open 阻塞 draw 时也不会挡住 dump；
- backboardd 实际 exec 后记录基准，`+2 s` 打第一次、`+12 s` 打第二次，
  覆盖 loader 打开显示前后的两个状态；
- 每次先打印 `NATIVE_PROC_DUMP: trigger stage=… flags=… cmds=…
  elapsed_ms=…`，再接 `NATIVE_PROC_DUMP: begin/find/…/end`；
- backboardd exec 后不再重绘 2×2（沿用 H104j 的意图）；
- 心跳线程保留原样，但不再承担任何必须发生的动作。

判读：左上白之后约 2 s 应出现 `trigger stage=1`，再过约 10 s 出现
`trigger stage=2`。看 `NATIVE_PROC_THREAD` 的 `state`/`wait`/`cont`：

- backboardd 的线程都停在 mach/IOKit 等待：按 `cont` 找等待点；
- 只有 loader 有显示 client 且 backboardd 无 client：结合 accelerator
  open 记录（`NATIVE_IOKIT_MATCH`）判断 ；
- 出现 `pid=… not found`：pid 与 H104i 不同，按 `comm` 重新登记。

### H105 构建结果（2026-11-05）

```text
H105 kernel:  75546e700157a63be8eca9ac0b9ca4c3c9c3db559afe7d807deb23e488978e08
H105 payload: e462dfc082025f1363da0bb6a9116df57335f3594891422dbe94359eeb9ba385
H105 boot:    abd0c569b346735c82fc47b23047422785eed67088536fd07d61a2d261f17afa
```

基线是 `boot-H104b-slot0-noiogpu.img`（`7928c93b…`，稳定白基线）：payload、
ADT、trust cache、scratch-data、args 全部沿用，只替换
`EFI/UniXNU/Payloads/kernel.macho`；boot image 的 firmware 字段
（`163917aa…`）也与它相同，因此 H105 与该基线的差异只有 kernel。
该基线的 `unixnu.toml`（`4cbe8cbd…`，含 `h103-slot=0 h103-load-iogpu=0`、
无 `-v debug=0x14e boot-progress=2`）和 ADT（`e78e9857…`）与 H104j 相同。

镜像位置：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H105.img`（已在
Windows 上核对 SHA-256 与长度 81,147,904 B）；Mac `~/h103/boot-H105.img`；
本仓库 `out/cheeseburger/boot/boot-H105.img`。
H104j kernel 备份（Mac）：`~/UniXNU/out/cheeseburger/kernel/kernel-H104j.macho`
（`7e85bc44…`）。

构建方式（Mac mini，`/Users/lss/UniXNU`）：

- `.cache/xnu-work` 先 `git checkout -- . && git clean -fd` 回到 `d8b8029`
  （原状态里 late patches 已部分回退，直接重跑会在 `bsd_init.c:987` 失败）；
- `scripts/build-arm-driver.py NativeUfsProbe` 重建 NativeUfsProbe archive
  （`SDKROOT=$(xcrun --sdk iphoneos --show-sdk-path)`，否则报
  `using sysroot for 'MacOSX' but targeting 'iPhone'`）；
- `bash ~/run-h103n-build.sh`（H104 的同一套 XNU_* 环境，含
  `XNU_NATIVE_LEGACY_DISPLAY=1`）；
- prelink 由 `kits/NativePrelink/emit_prelink.py` 直接执行（Mac 上
  `./unixnu` 因 Python 3.9 无 `tomllib` 不可用），参数取自 `board.toml`
  `[kernel.prelink]`，slide `0x5000000`。

payload 与 boot image：

- payload 以 **`boot-H104b-slot0-noiogpu.img` 内的 payload 为基线**，只替换
  `EFI/UniXNU/Payloads/kernel.macho`。核对结果：`unixnu.toml`（args）、
  `kernel.macho.adt`（`e78e9857…`）、trust cache、scratch-data 与该基线
  完全一致，仅 kernel 不同；
- 打包过程中走过两个作废版本：先用 H103ea 的 payload（boot `23f66e5e…`），
  其 args 多 `-v debug=0x14e boot-progress=2`、缺 `h103-slot=0
  h103-load-iogpu=0`，ADT 也是旧的 `d98d9522…`；再用 H104j 的 payload
  （boot `15d5377c…`）。两者都不要上机；
- boot image 用 `scripts/make-bootimg.py` 打包，firmware 字段与基线
  相同（`163917aa…`），因此与基线的差异只有 payload 内的 kernel。

判读：左上白后约 2 s 应出现 `NATIVE_PROC_DUMP: trigger stage=1`，再过约
10 s 出现 `stage=2`；随后是 `begin/find/pid=…/threads=…/NATIVE_PROC_THREAD`
和 `end`。四个 pid 与该基线日志一致（launchd=1、backboardd=55、
driverkitd=63、IOMFB_FDR_Loader=78）。

## H106 日志写入改成 ios-sweet 的批量模型（2026-11-05）

H105 的镜像用 `h103-slot=0`，等于没有持久化日志；而恢复原来的 slot 写入
（0.5 s 一次、固定 32 块）又会在 launchd 竞争窗口里抢 UFS，容易停在左上绿。
参照 `ios-sweet` 的 `0047`/`0069`（`sweet-log` 环 + `SWEET_LOG_SECS=10` 的
批量 flush），改 `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：

- 间隔从 0.5 s 改为默认 10 s（`h103-log-secs=1..60`；`h103-slot=2` 保留 2 s
  对照）；
- 只写自上次以来新增的字节：`delta = msg_bufx − 上次游标`，写
  `ceil(delta/4096)+1` 块（上限 32），不再固定 128 KiB；
- 内核安静时不写数据，只按同一间隔刷新一次 header（`uptime_s` 仍可判断读
  路径是否还活着）；
- 仍然只在 `native_boot_flags & 4`（backboardd 实际 exec）之后写，H105 的
  +2 s/+12 s dump 触发不变。

与 ios-sweet 的差异：它的 flush 线程用 `tsleep(hz * 10)` 唤醒；本移植的内核
线程不醒（见 H105），所以仍由 UFS 完成路径驱动，但保留同样的"增量 + 10 秒
+ 空闲不写"三条约束。

```text
H106 kernel:  1d9b58b11c23f60e3953352970c0b458b810aa59da642f35c4ecbb75c42cee33
H106 payload: 616bcd2686f921c407014cd5b5797ccf0398ce7dfa41b96495056945719e2af6
H106 boot:    4ffdb641f0b9f75e74c5699c3148130c1bd291f115f75ce5c452d82de38936fb
```

payload 仍以 `boot-H104b-slot0-noiogpu.img` 为基线，与它只有两处不同：
`Payloads/kernel.macho` 与 `unixnu.toml` 的 args（`h103-slot=0` 改为
`h103-slot=1`，并加入 `h103-log-secs=10`）。ADT（`e78e9857…`）、trust cache、
scratch-data、firmware（`163917aa…`）逐字节相同。

镜像位置：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H106.img`（已核对
SHA-256 与 81,147,904 B）、Mac `~/h103/boot-H106.img`、仓库
`out/cheeseburger/boot/boot-H106.img`。

判读：

- 左上白后应出现 `NATIVE_UFS_HB: slotMode=1 logSecs=10 …`；
- `NATIVE_UFS_SLOT` 约每 10 秒一条，`blocks=` 通常 1–3，`delta=` 是新增
  字节数；内核安静时不再出现；
- 拉 `h103log.bin` 后应能搜到 `NATIVE_PROC_DUMP: trigger stage=1/2` 与
  `NATIVE_PROC_THREAD`。

## H107 dump 覆盖绿阶段并强制落盘（2026-11-05）

H106 上机两次，两份日志的来源不同：

| 文件 | boot_id | msg_bytes | slots | 结论 |
| --- | --- | --- | --- | --- |
| `h103-log-20261105-231341.txt` | `4459027769` | 131072（旧格式） | 8 | 与 `194941` 那份逐字节相同，是 19:49 启动的旧内容；第一次 H106 停在绿阶段，门槛没开，没有写入 |
| `h103-log-20261105-232033.txt` | `3776623905` | 102400（25 块） | 1 | 第二次启动到白（`comm=backboardd` 186.35 s，`flags=f`），H106 增量写入成功，`write_errors=0` |

第二次启动的 dump 落盘了 stage=1，符号化后：

| 进程 | 线程 | 等待点 |
| --- | --- | --- |
| backboardd (55) | 1 | `ipc_mqueue_receive_continue` |
| IOMFB_FDR_Loader (78) | 2 | `ulock_wait_continue`、`ipc_mqueue_receive_continue` |
| driverkitd (63) | 2 | `thread_preempted`、`workq_unpark_continue` |
| launchd (1) | 6 | `semaphore_wait_continue`、`_sleep_continue`、`clock_delay_until` 等 |

即 backboardd exec 后 2 秒只有一条线程、停在 mach 消息接收上；控制台在
196.6 s 后安静。stage=2 没落盘：dump 只挂在 64 条命令的完成路径上，
196–230 s 没有完成事件，而 flush 又可能先于 dump 拷贝。

H107 的改动（`drivers/NativeUfsProbe/NativeUfsProbe.cpp`、
`patches/xnu/zzzzzzzzzzz-h103-proc-state.patch`）：

- dump 触发移进读路径的 `h103SlotTick()`（完成路径保留），不再依赖 64 条
  命令；
- 阶段改为 +2 s / +12 s / +60 s；
- 每次 dump 当次强制 flush，绕过 10 秒间隔；
- 门槛增加兜底：`native_boot_flags & 4`（backboardd）**或** SpringBoard
  exec 后 60 秒，绿阶段也能留下 dump 和一次增量日志；
- dump 进程列表加入 SpringBoard(27)。

```text
H107 kernel:  6acb0d39af24bfe38071bb90020b2450dc39b5603304b2f7fec2c626b409ff54
H107 payload: 7189630e8d14f74c25e3101fc9d17d5a98afaa94b654aa2c2aced8445863539a
H107 boot:    30d3de7397865499bdd84b9c805c06c89b1a3a14719e80048902d6c9e5fd2949
```

payload 以 H106 的为基线，只有 `kernel.macho` 不同；args、ADT、trust
cache、scratch-data、firmware 全部沿用。镜像在 Windows
`D:\Users\ls\Documents\OnePlus5_ios\boot-H107.img`（已核对）、Mac
`~/h103/boot-H107.img`、仓库 `out/cheeseburger/boot/boot-H107.img`。

判读：

- 白阶段：`trigger stage=1/2/3`，每阶段后紧跟一次 `NATIVE_UFS_SLOT`
  写入，`NATIVE_PROC` 行应完整落在日志里；
- 绿阶段：SpringBoard 后 60 秒出现 `trigger stage=1 … fallback`，同样
  带完整 `NATIVE_PROC_THREAD`，用于查 backboardd 为什么没起来。

## H108 独立心跳、1 Hz 诊断线程与进程摘要（2026-11-06）

H107 的 +2 s dump 给出了阻塞点：`wait=0xfffffff007ae0320` 符号化后是
`ipc_mqueue_full`（`IPC_MQUEUE_FULL`，端口的 send turnstile）。backboardd
唯一的线程和 FDR loader 的一条线程都堵在"向已满端口发送"上，此后没有
UFS 读，所以 stage 2/3 和之后的日志都写不下来。

H108 的改动：

- 新增 1 Hz 诊断线程 `h108TickThread`，用 `tsleep(…, hz)` 睡眠（`IOSleep`
  已证明不醒）。每秒（1）翻转独立的 16×16 心跳格，（2）门槛打开且 dump
  阶段到期时打印并强制 flush。启动打印 `NATIVE_TICK: thread rc=…`，前
  5 秒和每 30 秒打印 `NATIVE_TICK: sec=…`；第一次上机就能验证 `tsleep`
  在这个移植上是否会醒。
- display archive 新增 `native_legacy_heartbeat_cell()`：只重画 (40,0) 的
  16×16 格，不重画整块 2×2、不取锁，由 1 Hz 线程驱动，白之后仍持续闪烁。
- dump 增强：线程行在 `wait_event == &ipc_mqueue_full` 时追加
  `send-block`；新增 `NATIVE_PROC_SUM: pid=… comm=… threads=… runnable=…`
  每进程一行（`proc_iterate`，上限 160），用来找"队列满却不读"的接收者。
- flush 统一由 `h103FlushNow()` 完成（读路径与 1 Hz 线程共用，busy 标志和
  游标只在这一处更新）。
- payload 的 `h103-log-secs` 从 10 改为 5。

```text
H108 kernel:  fb2a302a09610f157d3a1559c8adfb78a1367d3044cd9c8316e5665402daa95e
H108 payload: ca53e0c29a67cf2056d8e9a32a1d2d8d9f4d0bc5c81a103f475e8c474d0676bf
H108 boot:    03c23f719636ae56173867eb10fcd9ed48325d0c3cc4f4efd387881300fab818
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H108.img`（已核对）、
Mac `~/h103/boot-H108.img`、仓库 `out/cheeseburger/boot/boot-H108.img`。
payload 以 H107 的为基线，只换 `kernel.macho` 与 `unixnu.toml`（log-secs=5），
ADT/trust cache/scratch-data/firmware 不变。

判读：

- `NATIVE_TICK: sec=1..5` 出现 → `tsleep` 可用，之后 stage 2/3 不再依赖
  UFS 读；只有 `NATIVE_TICK: thread rc=0` 而没有 sec 行 → 退回 timer_call；
- 左上第 3 格在白之后应继续每秒白/橙翻转（独立心跳）；
- `NATIVE_PROC_SUM` 里找 `runnable=0` 且线程都停在非 `send-block` 的进程，
  那就是队列满的接收者。

### H108-cpu2 对照（2026-11-06）

只改 payload 的 args：`cpus=1` → `cpus=2`。内核、ADT、trust cache、
scratch-data、firmware 与 H108 逐字节相同（kernel 仍为 `fb2a302a…`）。

```text
H108-cpu2 payload: a5b1d999c90d2de73383cd137f083b4f320f14d842bbea7abc6edc6eb153c466
H108-cpu2 boot:    a60a4eb1ec16c438188286db5aa4e30910ed41216385189f9a67e9e351550423
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H108-cpu2.img`（已核
对）、Mac `~/h103/boot-H108-cpu2.img`、仓库
`out/cheeseburger/boot/boot-H108-cpu2.img`。

判读：

- `send-block` 消失、stage 2/3 落盘、日志越过 backboardd → 之前是单核把
  接收者饿死（driverkitd 的 TH_RUN 线程）；
- 同一位置仍 `send-block` → 真正的端口死锁，与核数无关，下一步查满队列的
  owner；
- 在 `KextLog` 之前就挂 → 只能当作辅核启动观察，不能作为对照结论。

## H109 timer_call 心跳与 PROC_NOWAITTRANS（2026-11-06）

H108-cpu2 日志（`h103-log-20261106-004029.txt`）确认三件事：

- `NATIVE_TICK` 只有 `thread rc=0` 一行，没有 `sec=` → **`tsleep` 也不醒**，
  线程定时在这个移植上整体不可用；
- cpu2 到白（`comm=backboardd` 187.7 s，dump `flags=f`），UFS 锁失败只有
  4 条且都是精确 2.0 s（`ticks=38400003`），没有 cpu1 那种 20 s 放大 →
  cpu1 的锁死循环是**单核饿死**；
- dump 打完 5 个进程、15 条线程后卡住：没有 `NATIVE_PROC_SUM`、没有
  `end`，2.2 s 后 SystemOS 读拿不到锁、`disk4` 超时、`navd` pagein 失败。
  原因是 `proc_iterate()` 默认对每个进程 `proc_transwait(p, 0)` 无限等待
  exec 过渡，而 dump 正跑在 UFS 读路径线程上，与需要读 SystemOS 的 exec
  互相锁死。

H109 改动：

- `timer_call` 每秒（定时器中断）：翻 16×16 心跳格、`gH109Ticks++`、需要时
  `thread_wakeup` 唤醒 worker，然后重装；不用任何线程超时；
- 新增 `h109WorkerThread`：`assert_wait` + `thread_block` 等显式唤醒，
  被唤醒后执行 dump + flush；
- 读路径保留 dump 兜底，并在 `h103SlotTick` 每 30 秒打印
  `NATIVE_TICK: sec=…`，屏幕不可见时也能证明 timer_call 在走；
- `proc_iterate` 改为 `PROC_ALLPROCLIST | PROC_NOWAITTRANS`（`1U | 4U`）；
- 删除 H108 的 tsleep 线程。

```text
H109 kernel:  265425cc223dcd71b37440ec1281812186163c77bbc0c0b3ea10b76743d0f427
H109 payload: 5f3e022472fbe6e9ae3ed5de7a171c14dd101fc7da6fb743fe5fcf133aed20e0
H109 boot:    f03c895cad7c956f2b329ef4eaee7c995a5b03c55f745d3f35773bfbcf2f21d4
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H109.img`（已核对）、
Mac `~/h103/boot-H109.img`、仓库 `out/cheeseburger/boot/boot-H109.img`。
payload 以 H108 为基线，只换 kernel（args 仍为 `cpus=1 h103-slot=1
h103-load-iogpu=0 h103-log-secs=5`）。

判读：

- 白之后左上第 3 格应**每秒独立翻转**，与日志速度无关 → `timer_call` 可用；
- 日志每 30 秒出现一次 `NATIVE_TICK: sec=…`；
- `NATIVE_PROC_SUM` 应完整出现且不再卡住，stage 2/3 应能落盘；
- 若心跳仍随日志闪、也没有 `sec=` 行 → `timer_call` 也不触发，下一步只剩
  arch timer 中断直挂。

## H110 timer 观测与 notick 对照（2026-11-06）

H109（cpu1）在 FileSet KC / `driverkitd is active` 之后硬停，没有写盘；心跳
停止无法区分"内核死了"还是"timer_call 从未触发"。H110 只加观测，不改行为：

- `timer_call` 回调里直接打印 `NATIVE_TICK: fire=N flags=…`（前 3 次、之后
  每 10 秒），控制台可见，不依赖落盘；
- worker 每次被唤醒打印 `NATIVE_TICK: worker wake=N`；
- 新增 boot arg `h109-tick=0/1`（默认 1）关掉 timer_call，同一颗内核可以
  A/B；
- 两张镜像都用 `cpus=2`（H108-cpu1 的锁风暴已证明是单核忙等放大，主诊断
  移到双核）。

```text
H110 kernel:        a7744d145b000d49cfa2a5cd400e2dfd5ce80d0bc681dd9ca5d763746a342005
H110 payload:       217e169f7e6f8f3e8845386fe0e2fd62be6a791b6039879282512526e763ead3
H110 boot:          9ff8dacfe3504841dbbd82c3a5e8b2dfd99d1c92af283b6fc8922ab0ac7b30c0
H110-notick payload: ad068fc4d9c23aef0e19eddce53f3c8b9dca5dd60643eb5f78cd3328b441919e
H110-notick boot:    9139d03eb63bd40c805250da62dc55b567353cdcb26c4b8e254128fb6fc7ab99
```

两张镜像的 args 只差 `h109-tick=1/0`，kernel/ADT/trust cache/scratch-data/
firmware 相同。镜像在 Windows `D:\Users\ls\Documents\OnePlus5_ios\`、Mac
`~/h103/`、仓库 `out/cheeseburger/boot/`。

判读：

- 主版出现 `fire=1/2/3` → `timer_call` 可用；冻在 `fire=N` 就知道停在第几秒；
- 主版没有 `fire=` → 回调根本不触发，独立心跳要改挂 arch timer；
- 主版冻、`notick` 不冻 → 冻结由 timer 回调引入（中断里跨 archive 调
  `drawHeartbeatCell`，或 `thread_wakeup`/重装 timer 的用法）；
- 两版都冻在同一位置 → 与 timer 无关，回到 gate 之前的启动路径继续查
  （FileSet KC / trustcache 一段）。

## H111 arch timer 中断计数（2026-11-06）

H110 两版（tick/notick）停在同一位置，且日志显示 dump 已完整跑完（67 行
`NATIVE_PROC_SUM`，`PROC_NOWAITTRANS` 修复有效）、没有任何 UFS 锁错误，
最后一行是 197.766 s 的 `ACCHWComponentAuthService` exec；之后控制台、
日志、flush 全部停止，backboardd(2 线程)/SpringBoard(2 线程) 全部
`runnable=0`。

把四个现象串起来（`IOSleep` 不醒、`tsleep` 不醒、`timer_call` 不触发、
单核锁等待 2 s→20 s、各 daemon 等超时永不到期）指向同一个怀疑：**arch
timer 中断根本没投递**。

H111 只加一条诊断，在 UFS 读路径每 30 秒打印：

```text
NATIVE_IRQ: timer=<armcpu_timer_interrupts> cntv_ctl=<..> tval=<..> flags=.. tick=<gH109Ticks>
```

`armcpu_timer_interrupts` 是 ArmCpu 在 INTID 27 分支里累加的计数（调
`rtclock_intr` 之前），`CNTV_CTL` 的 bit0/1/2 分别是 ENABLE/IMASKED/
ISTATUS。

```text
H111 kernel:  55f36abb7f9391c573c91b201ca78e4673a450cd108cfde25ca02c46ad3dc66a
H111 payload: 30c1baf7be0ffd75a07cdfc17c0372ef6a21474893678c6d5337aa9a059361cc
H111 boot:    8f90ac816c41a2937f4bc53f1b427b711545d55dcb9ea80ff149569014139259
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H111.img`（已核对）、
Mac `~/h103/boot-H111.img`、仓库 `out/cheeseburger/boot/boot-H111.img`。
args 与 H110 主版相同（`cpus=2 h103-slot=1 h103-load-iogpu=0
h103-log-secs=5 h109-tick=1`）。

判读：

- `timer=0` 且 `cntv_ctl` 的 ENABLE=0 或 IMASKED=1 → 内核没有真正打开虚拟
  定时器，需在 ArmDTPlatform / `machine_routines` 补初始化（根因）；
- `timer=0` 但 `cntv_ctl=1` 且 tval 在变化 → 定时器在跑但 PPI 27 没投递，
  查 redistributor 使能/优先级/亲和；
- `timer` 在增长 → 中断正常，问题在 `rtclock_intr`/`timer_call` 的接线。

## H112 5 秒 IRQ 采样与 120 秒强制落盘（2026-11-06）

H111 上机同样没有写出日志（导出的 `h103log.bin` 与 H110 的 `boot_id`
相同 = 旧内容），最后一次 `NATIVE_IRQ` 在 ~190 s，正好滚出最后一屏；冻结
点在 ~197 s，早于所有门槛（backboardd 未 exec，SpringBoard+60 s 兜底
≈225 s）。H112 只加诊断：

- `NATIVE_IRQ` 采样间隔 30 s → **5 s**，保证冻结时最后一屏必有一条；
- 新增**绝对时间兜底**：UFS 启动后 120 s 强制做一次 `NATIVE_PROC_DUMP` +
  flush，不依赖任何 exec flag，保证 197 s 冻结前一定有一份落盘记录
  （120 s 时系统正常，cpu2 无锁风暴）；
- SpringBoard 兜底仍保持 +60 s 不变（避免在 launchd 竞争窗口里提前写盘）。

```text
H112 kernel:  a3c901002d1a7019a39a0a12e1b0e2334356d241f99e8f7a2c4db66b1d6934fc
H112 payload: 2836a566cb0f91a1d503e7fa974e7a1335ca7f34e207fa5eaccf1d32b42091e7
H112 boot:    d1540e00f47d3550df6256a50eb132a7e338d2d4ccb5fc6ae7925e222f77cf75
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H112.img`（已核对）、
Mac `~/h103/boot-H112.img`、仓库 `out/cheeseburger/boot/boot-H112.img`。
args 与 H111 相同（`cpus=2 h103-slot=1 h103-load-iogpu=0 h103-log-secs=5
h109-tick=1`）。

判读：

- 最后一屏的 `NATIVE_IRQ: timer=…`：`timer=0` → arch timer 中断从未投递；
  结合 `cntv_ctl`（ENABLE/IMASKED）区分"没开"和"没投递"；
- 拉 `h103log.bin` 应有 `NATIVE_TICK: forced dump at uptime 120 s` 及之后
  的进程/线程快照，`boot_id` 应与 H110/H111 不同。

## H113 中断/DAIF/GIC 状态采样（2026-11-06）

H112 的日志终于落盘（`boot_id 7422465753`、`slots_written=5`），关键行：

```text
[376.953] NATIVE_IRQ: timer=0 cntv_ctl=fffffff007bb7000 tval=5b8d800 flags=f tick=0
[381.958] NATIVE_IRQ: timer=0 cntv_ctl=fffffff007bb7000 tval=5b8d800 flags=f tick=0
[384.526] NATIVE_PROC_DUMP: trigger stage=2 flags=f cmds=31992 elapsed_ms=12030
```

- **`timer=0` 持续到 381 s**：ArmCpu 的 INTID 27 计数从未增加 →
  虚拟定时器中断从未投递；
- `tick=0`：`timer_call` 同样从未触发；
- `flags=f`：这次到了白（backboardd ~372 s exec），stage 2 正常触发；
- 之前的"197 s 冻结"要修正为"控制台安静 + 没有 flush"，内核仍在跑（本日志
  写到 386 s）；
- 进程摘要显示"全员等待"：backboardd 1 线程 `runnable=0`、SpringBoard
  4 线程 `runnable=0`，几乎全部 `runnable=0`。

H112 里 `cntv_ctl` 读出来是内核地址（`fffffff007bb7000`），内联汇编不可信。
H113 改用 XNU `machine_routines.c` 同款 builtin，并补上三项状态：

```c
uint64_t ctl = __builtin_arm_rsr64("CNTV_CTL_EL0");
uint64_t tval = __builtin_arm_rsr64("CNTV_TVAL_EL0");
mrs daif / icc_pmr_el1 / icc_igrpen1_el1
```

输出：

```text
NATIVE_IRQ: timer=.. ipi=.. daif=.. pmr=.. grp1=.. ctl=.. tval=.. flags=.. tick=..
```

```text
H113 kernel:  f76fe585d2c6ff17589bbefe87772bc0a818c312b7b5f71d7fcb79ed79fef7b6
H113 payload: 6633f759310cea787448e0466e0504414328794c74dda38e47f107d968ab518e
H113 boot:    85e8640359e51c7c4764e69d5a8078c0ea1afefed9bbb37fcb111b354ff450ec
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H113.img`（已核对）、
Mac `~/h103/boot-H113.img`、仓库 `out/cheeseburger/boot/boot-H113.img`。
args 与 H112 相同（`cpus=2 h103-slot=1 h103-load-iogpu=0 h103-log-secs=5
h109-tick=1`）。

判读：

| 观察 | 结论 |
| --- | --- |
| `daif` 的 I 位=1 | 中断全局未开，系统一直在轮询；找平台里该开中断的位置 |
| I=0、`ipi>0`、`timer=0` | GIC 能送 IPI，PPI 27 没使能/分组/优先级不对 |
| I=0、`ipi=0`、`timer=0` | 所有中断都没送，查 vector/ICC_SRE/DAIF |
| `timer` 在涨 | 定时器正常，问题在 `rtclock_intr`/`timer_call` 接线 |

## H114 PPI 27 的 redistributor 状态（2026-11-06）

H113 读数：`timer=0 ipi=0 daif=200 pmr=f0 grp1=1 ctl=5 tval=ffff7d8e tick=0`。
`ctl=5` = ENABLE + **ISTATUS**、IMASKED=0，说明虚拟定时器**一直在拉中断**；
`daif` 的 I=0（IRQ 未屏蔽），`grp1=1`、`pmr=0xf0` 也正常；但定时器和 IPI
的计数都是 0 → 一条中断都没进过 EL1，系统一直在协作式/轮询运行。

断点只剩两处：GIC 没转发，或者异常被 EL2/EL3 截走。H114 补两行采样：

```text
NATIVE_IRQ: … el=.. vbar=.. h1=<ICC_HPPIR1> h0=<ICC_HPPIR0> rpr=..
NATIVE_GIC: typer=<GICR_TYPER> isen=<ISENABLER0> igrp=<IGROUPR0> ipend=<ISPENDR0> ipri=<IPRIORITYR[27]>
```

`armcpu_probe_ppi27()` 由 ArmCpu 子模块 `f3633d2` 导出（记录 `wakeRedistributor`
选中的本核 frame，读取上述五个寄存器）。

```text
H114 kernel:  d725bb5d81b9c7ebaf6042de2c0b3b4e1e97e01123e999b660d2476e019ee1e1
H114 payload: 84359be3737a76739dba91f6049a2a3c0971ac1209f0281fb8221c004178577b
H114 boot:    d340af9c06e34eb9e4293f7c7ea3daeb128537cc32197df8d615c1f6514d08c7
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H114.img`（已核对）、
Mac `~/h103/boot-H114.img`、仓库 `out/cheeseburger/boot/boot-H114.img`。

判读：

| 观察 | 结论 |
| --- | --- |
| `h1=27`（HPPIR1 报 27） | GIC 已在向本核报 27；若仍不进中断，是异常路由（EL2/EL3）或向量问题 |
| `h1=3ff`（1023） | GIC 没转发，看 `isen`/`igrp`/`ipend` 的 bit27 |
| `isen` bit27=0 | 该 PPI 在本核 frame 上没使能（redistributor 选错或写入丢失） |
| `igrp` bit27=0 | 被分到 Group 0（FIQ），而 ArmCpu 只处理 Group 1（IRQ） |
| `ipend` bit27=1 且 `h1=3ff` | 已挂起但被优先级/使能挡住 |
| `ipri` ≥ 0xf0 | 优先级被 PMR 挡住 |

## H115 显示事件即时落盘与帧内容（2026-11-06）

H114 上机到 backboardd 查询 `IOMobileFramebuffer` 之后直接黑屏，拉出来的
`h103log.bin` 仍是 H113 的 `boot_id`（一次成功 flush 都没有）。照片里的
`NATIVE_IOKIT_MATCH` 只对 backboardd 打印，说明它确实在查显示服务；黑屏
可能发生在"第一次落盘之前"（backboardd 用第一帧覆盖控制台，或该路径崩溃）。

H115 改动：

- `zzzzzzzzzz-h103-iokit-trace.patch`：backboardd 成功匹配 `IOMobile*` 时置
  `native_boot_flags |= 0x1000`；
- `NativeUfsProbe` 增加**事件驱动 flush**：首次出现
  `flags&4`（backboardd exec）、`flags&0x1000`（显示匹配成功）、
  `native_legacy_client_calls`（显示 user client 打开）、
  `native_legacy_transfer_calls`（第一帧拷贝）时立即 flush 一次，绕过 5 秒
  间隔；
- 每次 flush 前打印客户端帧的扫描结果
  `NATIVE_FRAME: frames=.. kind=.. nonblack=.. bbox=..`，
  `nonblack=0` 即"帧内容是黑的"；
- `panic_screen` 暂不做：`patch-xnu-entry-probe.py --panic-screen` 使用基础
  内核的固定 cave 地址，已 prelink 的 `kernel.macho` 需要另行推导。

```text
H115 kernel:  a8fa2828e728e3c255457073b3f86d14585f661a268151d99cc630dd93b154f5
H115 payload: 555f873a2ac9e8507cc27a561eb2a1cfad8b9fc8cb52e5968ae5da7b162b25ea
H115 boot:    5c5b118dea383609738a8d78ce2229e546b072875497d9f4200041145685d389
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H115.img`（已核对）、
Mac `~/h103/boot-H115.img`、仓库 `out/cheeseburger/boot/boot-H115.img`。
args 与 H114 相同（`cpus=2 h103-slot=1 h103-load-iogpu=0 h103-log-secs=5
h109-tick=1`）。

判读（黑屏后拉日志）：

- `NATIVE_FRAME: event=2/4/8 …` → 相应事件已发生并落盘；
- `NATIVE_FRAME: frames>=1 … nonblack=0` → 客户端帧是黑的（CA 无 GPU），
  黑屏属"正常但黑"；
- `nonblack>0` 但屏幕黑 → 帧有内容，问题在扫描/背光；
- 没有 `NATIVE_FRAME` → 事件之前就停了，看最后一条 `NATIVE_IRQ` 与 exec。

## H116 显示路径触发落盘（2026-11-06）

H115 的事件驱动 flush 同样没有写盘（拉到的仍是最初 H113 的 `boot_id`）。
事件触发器全部挂在 UFS 读路径上，而黑屏发生在 backboardd 第一帧拷贝覆盖
控制台之后；那时读路径已经没有 tick，触发器不会被检查。

H116 反过来：由**显示路径直接调用** UFS 的落盘钩子。

- `NativeUfsProbe` 新增导出：

  ```c
  extern "C" void native_log_flush_hook(void) { if (gH103Probe) h103FlushNow(); }
  ```

- display archive（`LegacyDisplayProbe.cpp`）弱引用该符号，并在
  `native_legacy_client_enter()`（显示 user client 打开）和
  `native_legacy_transfer_observed()`（首帧拷贝成功，之后每 16 帧）调用它。

这样即使控制台被覆盖、读路径停摆，黑屏瞬间的 msgbuf 也会被强制写进
userdata_ios 的日志窗口。

```text
H116 kernel:  10a1bb08ba37894276e453b9ab898afb2ff89329e57feb6511093b6f7b489ba2
H116 payload: cecf64d1692ae59691405d6ed4498bade17224c87e43ae5cdb14c712c08dfd07
H116 boot:    0dc6a0e8247f799fff1261766184147572c0f4e77f01dff596aa182088b8c2f7
```

子模块 `drivers/NativeMobileDisplay` 提交 `6d27403`（分支 `h103-a540`，已
推送）。镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H116.img`、
Mac `~/h103/boot-H116.img`、仓库 `out/cheeseburger/boot/boot-H116.img`。

判读：

- `boot_id` 变了、日志含 `NATIVE_LEGACY: client …` / `NATIVE_FRAME: frames=…`
  → 拿到黑屏瞬间记录，看 `nonblack` 判断帧是否全黑；
- `boot_id` 仍不变 → 写盘本身失败（队列 poisoned / 命令超时），下一步查
  UFS 写路径；
- 若在 `native_log_flush_hook` 里加锁失败，会出现 `NATIVE_UFS_LOCK: logWrite`
  或 `write_errors` 增长，同样说明写路径有问题而不是没触发。

## H117 panic 落盘与 GIC 采样 A/B（2026-11-06）

H116 的 `boot_id` 仍然不变。检查过符号链：`native_log_flush_hook` 已定义在
内核里（`S fffffff0079b1108`），显示侧引用正常，所以不是弱绑定成 NULL。
剩下两种可能：钩子没被调用，或调用后写盘失败。

H117 加两件事：

1. **panic 路径落盘**
   新增 `patches/xnu/zzzzzzzzzzzz-h103-panic-flush.patch`：在
   `panic_trap_to_debugger()` 入口调用 `native_panic_flush()`；后者先打印
   `NATIVE_PANIC: flags=.. client=.. xfer=.. frames=..`，再做一次强制 flush。
   panic 文本在 `ml_panic_trap_to_debugger()` 里才打印，所以这份记录至少能
   证明"发生过 panic"以及 panic 前最后的现场。
2. **GIC 采样开关**
   `h114-gic=0/1`（默认 1）：关掉 H114 的 redistributor/ICC 读取。用于验证
   "H113→H114 的改动是否导致崩溃"：同一颗内核两次启动即可对比。

```text
H117 kernel:       116d1581bb311e313e5ad87465d2544947724eb7ab949b35a6c3e35068b96b99
H117 payload:      1030fd0b973ae873468a94bb7cc7e03970587e65a5d69402fdc00fe762905505
H117 boot:         802a96fcb6a474a92a325d6bc22bbaa6c44483d608dfc40d8ec6af179ad16da0
H117-nogic payload: 0d9ee465e4b7fe656f9cd6ebb277d9160b29d1a677b22a8c7a5ff2cccd318bdf
H117-nogic boot:    22b5b806ebf8f6826e0f0fe42773b5f980762defe5114b5ee117ed5d9ed08042
```

两张镜像只差 `h114-gic=1/0`。镜像在 Windows
`D:\Users\ls\Documents\OnePlus5_ios\`、Mac `~/h103/`、仓库
`out/cheeseburger/boot/`。

判读：

- 带 GIC 采样黑屏、`nogic` 不黑 → 确认是 H114 的读取导致；
- 两者都黑 → 与 H114 无关，看下一项；
- 日志出现 `NATIVE_PANIC:`（或 `boot_id` 更新）→ 确实 panic，且拿到了
  panic 前的现场；没有 `NATIVE_PANIC` 且 `boot_id` 仍不变 → 连 panic 钩子
  都没机会执行，问题在写盘或更早的路径。

## H118 GIC 状态改为初始化缓存（2026-11-06）

H117 的 A/B 结论：`boot-H117.img`（GIC 采样开）黑屏，`boot-H117-nogic.img`
（`h114-gic=0`）正常启动，日志 `boot_id 3796218264`、`slots_written=4`、
`write_errors=0`，`NATIVE_IRQ: timer=0 … ctl=5 tick=0` 依旧是核心问题。
所以 H114 新增的**运行期 GIC/ICC 读取**确实是黑屏原因（用户怀疑成立）。

H118 把 GIC 读取挪到初始化、并拆开两个开关：

- ArmCpu 在 `enableGic()` 写完 `kSgiPpiEnable` 之后**回读一次**
  `GICR_TYPER/ISENABLER0/IGROUPR0/ISPENDR0/IPRIORITYR[27]`，存进
  `armcpu_ppi_probe[]`；`armcpu_probe_ppi27()` 变成空操作，运行期不再做
  GIC MMIO；
- `h114-gic=0/1`：是否打印缓存值（默认 1，安全）；
- `h114-icc=0/1`：是否读 `ICC_HPPIR1/HPPIR0/RPR`（默认 0，H114 的另一个
  嫌疑，单独做对照）。

```text
H118 kernel:       d3ac7d09ed4d51696ea5e0968951a025ac5252665690c020552100c9585c6532
H118 payload:      792198fa710a440f5734b004199cc38f862851f0190b0bbc1762ea7c6e90be1b
H118 boot:         44da43d3bcc7c1490d69f23b9da1007767cf4d418e3ed0499f088b0089f6fc2f
H118-icc payload:  a3f307dc07b7704dfc1086a6658bdc71058912a3b09db31b7f8e8157289993af
H118-icc boot:     b491d9c815abc130874562512980f1055b1c42e9d11c7bc45c6416eb31981d99
```

子模块 `drivers/ArmCpu` 提交 `b2ece97`（分支 `h118-gic-cache`，已推送）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\`、Mac `~/h103/`、仓库
`out/cheeseburger/boot/`。

判读（先刷默认 `boot-H118.img`）：

- `NATIVE_GIC: … isen=…` 若 bit27=1、`igrp` bit27=1、`ipri=0x80` →
  redistributor 配置正确，中断没到是 CPU/异常路由问题；
- `isen` bit27=0 → ArmCpu 的使能写没落到这块 frame；
- `igrp` bit27=0 → 被分到 Group 0（FIQ），ArmCpu 只处理 Group 1；
- 默认镜像不再黑屏（同 nogic）即可确认运行期 MMIO 是崩溃源；
- 需要时再用 `boot-H118-icc.img` 单独验证 ICC 读取。

## H119 GICR_IPRIORITYR 非对齐读修复（2026-11-06）

H118 默认镜像一启动就 panic：

```text
panic(cpu 0 …): Unaligned kernel data abort
pc 0xfffffff0079afb00  ← atos: ArmCpu::enableGic() (ArmCpu.cpp:347)
esr 0x96000021         ← data abort, DFSC=0x21 alignment fault
far 0xfffffff8debc5241b ← 末位 b，正是 0x400 + 27
```

根因：GICv3 的 `GICR_IPRIORITYR<n>` 是**按字节编址**（0x400 + n），H118 用
`read32(..., 0x400 + 27)` 做了 32 位非对齐读。这也解释了 H114–H116 的运行期
probe 黑屏：同一句读取在第一次 `h103SlotTick`（读路径起来，约 190 s）执行时
崩溃。

H119 只改这一行：

```c
- armcpu_ppi_probe[4] = read32 (redist + 0x10000, 0x400 + 27);
+ armcpu_ppi_probe[4] = *reinterpret_cast<volatile uint8_t *> (redist + 0x10000 + 0x400 + 27);
```

```text
H119 kernel:       a390c2fc8d36eae5a43c6b8524993736607a853b92819e613c32c69c1ed48506
H119 payload:      caf5d0bfc3f26ff84e19228a404db804451823cbeb451f5db7d83a3772eda244
H119 boot:         fd2cb95e43ec4742647db862bfef6a0e6ccafc0fd86a81693e97c192d0ea7819
H119-icc payload:  05063042c8a791b79529f40ee505193e5623741f926cc25568e8d2a2947dde53
H119-icc boot:     24fc419614fd96e4a857820c3c84a12082ac455284c3b79398ca3e89679750b3
```

子模块 `drivers/ArmCpu` 提交 `a984efc`（分支 `h118-gic-cache`，已推送）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\`、Mac `~/h103/`、仓库
`out/cheeseburger/boot/`。

判读（先刷 `boot-H119.img`）：

- 不再 panic，`NATIVE_GIC: typer=… isen=… igrp=… ipend=… ipri=…` 给出真实值；
- `isen` bit27=1、`igrp` bit27=1、`ipri=0x80` → redistributor 配置正确，
  中断没到是 CPU 侧/异常路由问题；
- `isen` bit27=0 → 使能写没落到本核 frame；
- `igrp` bit27=0 → 被分到 Group 0（FIQ）；
- `boot-H119-icc.img`（`h114-icc=1`）用于单独确认 ICC 读取是否也会崩。

## H120 GIC 安全态/唤醒状态快照（2026-11-06）

H119 默认镜像正常运行，GIC 读数：

```text
NATIVE_GIC: typer=1 isen=80000ff igrp=0 ipend=40280000 ipri=80
```

即 PPI 27 **已使能（bit27）且 pending**、优先级 0x80 能过 PMR 0xf0、
`grp1=1`、`daif` 的 I/F 都为 0，唯一异常是 `igrp=0`（全部 Group 0）。
另外 `boot-H119-icc.img` 与 H114 一样黑屏 → `ICC_HPPIR1/HPPIR0/RPR` 的读取
本身也是崩溃源，必须停掉。

H120：

- 删除运行期 ICC 读取（`h114-icc` 代码移除）；
- `ArmCpu::enableGic()` 在同一安全上下文里再缓存
  `GICD_CTLR`（DS 位）、`GICD_TYPER`、`GICR_WAKER`、`ICC_IGRPEN0`，并重写一次
  `IGROUPR0=0xffffffff` 后回读，用于区分"只读/写丢失"与"单安全态 RAZ"；
- `NATIVE_GIC2: dctl=.. gtyper=.. waker=.. grp0=.. igrp2=..`。

```text
H120 kernel:  c5a1117db41607a3bade49b58458af88dfcf65baadbd81df6dd6fa1d03b5bcec
H120 payload: 0363f9ed8051994d46c8585962092828f6e31ff713543d67a75f2c536b381caf
H120 boot:    01a7156450af8b0cf2bd15873a67abc534c348b7b6f13201115bd98e291d630f
```

子模块 `drivers/ArmCpu` 提交 `21a9487`（分支 `h118-gic-cache`，已推送）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H120.img`（已核对）、
Mac `~/h103/boot-H120.img`、仓库 `out/cheeseburger/boot/boot-H120.img`。

判读：

- `dctl` 的 bit6（DS）=1 → `igrp=0` 只是 RAZ，中断本来都是 Group 1，
  问题在 CPU 接口/redistributor 唤醒或亲和；
- DS=0 且 `igrp2` 仍为 0 → IGROUPR0 写不进去（secure-only），说明映射的是
  非安全态不可写的 frame；
- `waker` 的 ProcessorSleep/ChildrenAsleep 位若未清零 → redistributor 没真正
  唤醒；
- `grp0`=0 且 `igrp=0` 若确为 Group 0 → 需要打开 IGRPEN0 并处理 FIQ，
  工作量大，暂不做。

## H121 移除 IGRPEN0 采样（2026-11-06）

H120 在 `ArmCpu::enableGic()` 之前的位置直接黑屏（`IOCPUInterruptController:
not registry member` 之后），与 H118 的 panic 同一停点。新增的读取里只有
`ICC_IGRPEN0_EL1` 属于 Group 0 寄存器，和 H119-icc 里读 `HPPIR0` 一样会让
启动挂住。

H121 只把这一项去掉（`armcpu_ppi_probe[7]` 固定为 0），保留
`GICD_CTLR / GICD_TYPER / GICR_WAKER` 和 IGROUPR0 重写回读。

```text
H121 kernel:  353cde096200147110597e4fe855de9c7551b1aff3a67e4b883538d07d453fbc
H121 payload: e854d922d4636edafb914ad388c5220d01365e58ccb5713d7832f3f5e5bb2f19
H121 boot:    49de3eabb728f160373b9b839d72b7464e10e643a744fa90e6e7fd75503ba686
```

子模块 `drivers/ArmCpu` 提交 `e036c49`（分支 `h118-gic-cache`，已推送）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H121.img`（已核对）、
Mac `~/h103/boot-H121.img`、仓库 `out/cheeseburger/boot/boot-H121.img`。

判读：`NATIVE_GIC2: dctl=.. gtyper=.. waker=.. grp0=0 igrp2=..`

- `dctl` bit6（DS）=1 → `igrp=0` 只是 RAZ，中断本来就是 Group 1，问题在
  CPU 接口/redistributor 唤醒或亲和；
- DS=0 且 `igrp2` 仍为 0 → IGROUPR0 写不进去（frame 安全态问题）；
- `waker` 的 ProcessorSleep/ChildrenAsleep 未清零 → redistributor 没唤醒。

## H122 验证 GIC 写入与 PPI 27 分组（2026-11-06）

H121 正常启动，读数：

```text
NATIVE_GIC : typer=1 isen=80000ff igrp=0 ipend=40280000 ipri=80
NATIVE_GIC2: dctl=12 gtyper=7b04f3 waker=0 grp0=0 igrp2=0
```

`dctl=0x12` → EnableGrp1NS=1、ARE_NS=1、**DS=0（双安全态）**；`waker=0`
说明 redistributor 已唤醒；`igrp2=0` 说明写了两次 `IGROUPR0=0xffffffff`
都不生效。结合 `ipend=0x40280000`（PPI 27 与 30 都 pending）和
`timer=0/ipi=0`，指向"PPI 已被安全世界划为 Group 0，非安全态改不了"。

H122 加三组写-读回做定性：

- `ICENABLER0` 清 bit27 → 读回（`isen_off`）；
- `ISENABLER0` 置 bit27 → 读回（`isen_on`）；
- `IGROUPR0` 只写 `1<<27` → 读回（`grp27`）。

```text
H122 kernel:  eb2be3661dab038855d895293a5a4c703456f3845526a97ed3a30c24cf645e1e
H122 payload: 6be3188d705248841b7b8c712cee78ab05ed9b39eb96c42fe864814ca898f6e0
H122 boot:    699fae5d46fa3c592ed1e1e27805c3b27f92899987e455f4cf1e6f18f77534d0
```

子模块 `drivers/ArmCpu` 提交 `3ec9409`（分支 `h118-gic-cache`，已推送）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H122.img`（已核对）、
Mac `~/h103/boot-H122.img`、仓库 `out/cheeseburger/boot/boot-H122.img`。

判读：

- `isen_off` bit27=0 且 `isen_on` bit27=1 → MMIO 写正常；此时
  `grp27=0` 即证明 PPI 27 被安全世界占为 Group 0，XNU 侧无解，需在
  固件/安全世界把 PPI 27/30 划成 Group 1 NS（下一步查 `edk2-msm8998` 的
  GIC 初始化与 TZ 的初始分组）；
- 若连 `ISENABLER0` 也写不动 → 我们映射/选错了 redistributor 帧，需要
  重新核对 DT 描述与 stride。

## H123 全进程等待图（2026-11-06）

H122 已确认 PPI 27/30 被安全世界固定为 Group 0、非安全态改不了，定时器/中断
这条线转固件侧（`edk2-msm8998`，DS=0 时需要安全世界把 PPI 划成 Group 1 NS），
内核侧不再加 GIC 采样。本轮把主线拉回"绿不变白"：不再碰 GIC，改为在停滞瞬间
dump **全进程等待图**，定位 H107 看到的 `IPC_MQUEUE_FULL` 接收方。

改动只在 `patches/xnu/zzzzzzzzzzz-h103-proc-state.patch`（`osfmk/kern/task.c`）：

- 保留原有 5 个进程（loader/backboardd/driverkitd/SpringBoard/launchd）的逐线程明细；
- 新增 `native_proc_wait_graph()`，用 `proc_iterate(PROC_ALLPROCLIST|PROC_NOWAITTRANS)`
  遍历全部进程，每个进程输出一行：

```text
NATIVE_WAIT: pid=55 comm=backboardd threads=2 run=0 sb=1 tid=358 st=1 wait=... cont=...
```

`run` 是非等待线程数，`sb` 是 `wait_event == &ipc_mqueue_full` 的线程数；
`tid/st/wait/cont` 取最小 tid（主线程）的那条线程。打印在收集完成后进行，
不持 proc 锁；约 70–100 行、~10 KB，单次 flush 上限（32 块 = 128 KiB）足够。

```text
H123 kernel:  deba005d217433dc753014544d9018936e47c7857f8e5f64dd3848dcf1830858
H123 payload: 8ecad3d1ea75bb1fba64ca398268b9b213a62e7b133088a914077944baf82d76
H123 boot:    389edf630a52bc3e2995f63f4fdde2b3068d0d463277488ff9b23f7cc2aaa99c
H123 patch:   5073a29dfcebfd9991b8ddfcc638bca6b22bdeefd9ed967fa5174cd3235522f1
```

构建于 Mac `~/UniXNU`（`h123-build.log`，rc=0，`.cache/xnu-work` 先重置），
预链接 `~/prelink-h105.sh`；固件沿用 `fw-H103ea.img.gz-dtb`（`163917aa…`），
payload 由 `payload-H122.img` 只替换 `EFI/UniXNU/Payloads/kernel.macho`，
boot image 布局与 H122 逐字节一致（`ANDROID!`，page 2048，hdr 1，同 size 81147904）。
args 不变：`cpus=2 h103-slot=1 h103-load-iogpu=0 h103-log-secs=5 h109-tick=1 h114-gic=1`。

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H123.img`（已核对）、
Mac `~/h103/boot-H123.img`、仓库 `out/cheeseburger/boot/boot-H123.img`。

判读（`cont`/`wait` 用 `atos` 对 dSYM 符号化）：

- `ipc_mqueue_receive_continue` → 等消息（空闲）；
- `wait = &ipc_mqueue_full` → 发送方被满队列挡住；
- `ulock_wait_continue` / `semaphore_wait_continue` / `workq_unpark_continue` /
  `_sleep_continue` / `clock_delay_until` → 其它等待。

分支：有 `sb>0` 且某进程 `run=0`、主线程停在 receive/其它等待 → 该进程就是接收方，
继续查它为何不出队；所有进程都在 receive/空闲且无人 `sb` → 停滞不是满队列，
回到启动顺序（launchd/SpringBoard 依赖）；backboardd 不在 `NATIVE_WAIT` 里 →
停滞仍在 exec 之前。

## H123 结果与 H124（2026-11-06）

H123 日志：`/home/ls/UniXNU/h123-log-20261106-141018.txt`（67 个进程，
`NATIVE_PROC_DUMP: trigger stage=1 flags=f`，时间 206 s）。`cont`/`wait`
用 dSYM 符号化：

```text
0xfffffff0072761f0 ipc_mqueue_receive_continue
0xfffffff0072d8908 semaphore_wait_continue
0xfffffff0076c8004 workq_unpark_continue
0xfffffff007719e38 _sleep_continue
0xfffffff007749a54 ulock_wait_continue
0xfffffff007ae0320 ipc_mqueue_full
```

判读：

- 11 个进程的主线程停在 `ipc_mqueue_full`（backboardd、lockdownd、nfcd、
  sharingd、imagent、misd、audioaccessoryd、containermanagerd、cfprefsd、
  MobileGestaltHelper），backboardd 当时只有 1 条线程（tid 359）；
- **但满队列只是瞬时状态**：H122 在 428 s 的同类 dump 里 backboardd 已有
  2 条线程且停在 `workq_unpark_continue`（空闲），同一时刻系统还在继续
  `NATIVE_EXEC`（435 s 的 pid 89）；
- 23 个进程（xpcproxy 桩）停在 `vm_fault` 的 `PAGE_ASSERT_WAIT`（页忙等待，
  且 event 地址按创建顺序递增 = vm_page 数组 / 内核栈），只有 driverkitd
  有可运行线程 —— 这是 launchd 批量 spawn 时的 VM 压力，不是永久死锁；
- 因此 H107 的"满队列接收方不出队"不是 UI 的 gate。

**真正的 gate（新证据）**：`native_boot_flags` 的 bit 0x80 表示
"backboardd 调用过任意 IOService matching"，在 204 s / 206 s / 432 s 的
所有采样里都 **未置位**，同时 `client=0 xfer=0 frames=0`。即 backboardd
从未向 IOKit 查询过任何服务，也就没有打开 Legacy display，§44.10 的
"headless" 结论得到直接证据。

**顺带发现的诊断 bug**：UFS 完成路径在 `native_boot_flags & 4`
（backboardd exec）之后停止重画 2×2 面板（H104j 的原意是避免和 backboardd
抢屏），而心跳线程走 `IOSleep`、`IOTimerEventSource` 都依赖定时器中断，
没有中断时都不会再触发。于是面板永远停在"只有 SpringBoard"时的绿色，
即使 `flags=f`（两者都已 exec、本应白）。**"左上一直绿"是旧颜色，
backboardd 其实早已 exec。**

H124（本轮）：

1. 扩展 `zzzzzzzzzz-h103-iokit-trace.patch`：记录前 24 次
   `op=match/open/deny`，带 `comm`、`IOClass`、`IOProviderClass`，
   并把 `main_port != main_device_port` 单独记成 `d=badmaster`，第一次把
   "没调用"与"调用没到内核（master port/sandbox）"区分开；
2. 2×2 面板在 gate 位变化时重画一次（先白，再按 ikColor 反映 matching
   结果），不再冻结在旧颜色；
3. `native_proc_state_dump()` 去掉重复的全进程 summary；完整等待图改为
   由驱动在 stage≥2（+12 s / +60 s）和 120 s 强制 dump 时调用，+2 s 只保留
   5 个关键进程的线程明细，给 IOKit 日志留出日志窗口。

```text
H124 kernel:  5f8350f1dffcb1e136d0c657f8cb81ff029981704b66bb2464e8f7d0e7e482c1
H124 payload: a2ede5dd40a811f2ac92fa2ad3329c91ecefdc56a0d87fc7b79240cf11ad39e8
H124 boot:    9384572844ce56b06da5e1badca231d60dde7ab86ba75a20620825aa9a14f747
```

NativeUfsProbe archive 用 `scripts/build-arm-driver.py NativeUfsProbe`
（`SDKROOT=$(xcrun --sdk iphoneos --show-sdk-path)`）重建并通过 -Werror；
boot image 布局与 H122/H123 相同（81147904 B）。args 不变：
`cpus=2 h103-slot=1 h103-load-iogpu=0 h103-log-secs=5 h109-tick=1 h114-gic=1`。

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H124.img`（已核对）、
Mac `~/h103/boot-H124.img`、仓库 `out/cheeseburger/boot/boot-H124.img`。

判读：先看左上是否变白（gate 已到），再看
`NATIVE_IOKIT: op=match comm=... cls=... d=- ok=1`：

- 有 `comm=backboardd` 的 match → 看它要的 `cls`，把 Legacy 服务按该类
  发布/匹配即可；
- 只有 `d=badmaster` → 用户态拿不到 IOKit master port（bootstrap/sandbox），
  要修的是 MASTER 通道，而不是 display provider；
- 完全没有 backboardd 的 IOKit 行、但别的进程有 → backboardd 在查询前就
  决定了 headless，下一步追它的 MobileGestalt/launchd 输入。

## H125 定时器 PPI 对照（27 vs 19）（2026-11-06）

TWRP 对照（`/tmp/twrp-gic-probe.out`、`/tmp/twrp-gic-probe2.out`）：

```text
[0.000000] Architected cp15 and mmio timer(s) running at 19.20MHz (virt/virt).
3: ... GICv3 19 Edge arch_timer     (CPU0 30370→30504，1 s 内)
5: ... GICv3 39 Level arch_mem_timer (未用)
```

- `(virt/virt)` = Linux 用的是**虚拟定时器**；它注册的 PPI 是 **GICv3 hwirq 19**；
- 原厂 DT（`msm8998.dtsi` 805 行）：`timer { interrupts = <GIC_PPI 1>,<2>,<3>,<0> }`，
  GIC 驱动对 PPI `+16` → **INTID 17/18/19/16**，Linux 实际用 **19**；
- DT `intc` 的 `reg`/`redistributor-stride` 与我们的 ADT 一致（`17a00000/10000`、
  `17b00000/100000`、stride `20000`）；
- TWRP 内核没有 `/dev/mem`，`mknod /dev/mem c 1 1` 后 `toybox devmem` 仍被
  `CONFIG_STRICT_DEVMEM` 挡住，所以 GICR 寄存器没读到（这一步不影响上面的结论）。

因此"XNU 用 PPI 27、SoC 的定时器在 19"成为首要假设；XNU 里 27/30 pending
与 Linux 用 19 的矛盾用同一次上机区分。

H125 改动（`drivers/ArmCpu/ArmCpu.cpp`）：

- `kSgiPpiEnable = 0xffff | (1<<19) | (1<<27)`，两者都使能；
- 分发器对 19 和 27 都调 `rtclock_intr(0)`，并分别计数
  `armcpu_timer19_interrupts` / `armcpu_timer27_interrupts`；
- 新增写-读测试：`IGROUPR0` 写 `(1<<19)|(1<<27)`、`ISENABLER0` 清/置 19、
  再取一次 `ISPENDR0`、尝试 `GICD_CTLR |= 1<<6`（DS）、读 `GICD_IGROUPR1`；
- `NativeUfsProbe` 的 `NATIVE_IRQ` 增加 `t19=`/`t27=`，并新增一行：

```text
NATIVE_GIC4: grp1927=.. isen19_off=.. isen19_on=.. pend2=.. dctl_ds=.. dgrp1=..
```

```text
H125 kernel:  01457a274e1602a9b4b742df2229cbe83620480f9304c4c17ddc654fcf519a3a
H125 payload: c5e0550f8f4ef986607887cde8736a97b5ece3bd3745d63320b6d4527c8d3a23
H125 boot:    dde2b6adce82bd30bd0144daa5ed54107f184f5e0826c4b3588432c861e51371
```

子模块 `drivers/ArmCpu` 提交 `01d2902`（分支 `h118-gic-cache`，已推送）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H125.img`（已核对）、
Mac `~/h103/boot-H125.img`、仓库 `out/cheeseburger/boot/boot-H125.img`。
args 不变（`cpus=2 h103-slot=1 h103-load-iogpu=0 h103-log-secs=5 h109-tick=1 h114-gic=1`）。

判读：

- `t19 > 0` → 这台 SoC 的定时器就是 INTID 19；把 27 去掉、保留 19 即可，
  定时器/抢占/超时全部恢复，不需要改固件；
- `t27 > 0` → 27 才是定时器，回到 Group/帧问题（看 `grp1927` 与 `dctl_ds`）；
- 两者都是 0 → 看 `grp1927`（19 能否进 Group 1）、`dctl_ds`（NS 能否置 DS）、
  `pend2`（19 是否 pending），再决定帧布局或固件路线。

## H125 上机结果与 H125spi（2026-11-06）

**H125 内核卡死在早期启动**：屏幕停在

```text
NATIVE_UFS_LOG: deferred snapshot to window read
NATIVE_UFS_HB: enter
```

之后 10 分钟无变化，且 TWRP 里的持久日志与上一次完全相同（`NativeUfsProbe`
窗口从未被重写）→ 卡点在 `NativeUfsProbe::start()` 之后、第一次文件系统读之前。

与 H124 的差异只有 `ArmCpu` 里三处：`kSgiPpiEnable` 加 `1<<19`、分发器接受 19、
以及早期 `enableGic()` 里的 `IGROUPR0` 写和 `GICD_CTLR |= DS(1<<6)` 写。最可疑的
是后两个**带副作用的写测试**放在了早期启动路径（上游 `uefi-sheng` 的
`Gic-Spurious.patch` 正是处理"无 handler 的电平中断刷爆 CPU"）。尚未二分。

**H125spi（零构建实验，当前候选镜像）**：不改内核，沿用 H124 内核
（`5f8350f1…`），只把 payload 的 `unixnu.toml` 的 args 追加
`armcpu-spi-ipi=1`，用来测 **GICD_IGROUPR**（distributor 侧分组）是否可写、
SPI IPI 是否可投递——H122 只测过 redistributor 侧的 `GICR_IGROUPR0`。

```text
H125spi kernel:  5f8350f1dffcb1e136d0c657f8cb81ff029981704b66bb2464e8f7d0e7e482c1 (H124)
H125spi payload: fb32df8c5f36ce4c6d5e6938f56a009b953c4bc3200072b722f6dd9945bbaa66
H125spi boot:    c6eadde17a68c43aeeefbc44e9b17a57a50778382bd25c778d3fa472ddf94aa4
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H125spi.img`（已核对）、
Mac `~/h103/boot-H125spi.img`、仓库 `out/cheeseburger/boot/boot-H125spi.img`。
其余 args 与 H124 完全一致。

判读：`NATIVE_IRQ: ... ipi=N`

- `ipi > 0` → SPI 属于 NS 且可投递：中断空间不是全锁死；下一步可评估用
  `arch_mem_timer`（TWRP `/proc/interrupts` 里的 `GICv3 39`，SPI）作为 tick 源；
- `ipi = 0` → PPI+SGI+SPI 都归安全世界，中断只能走固件线；
- 卡死/panic → 记录 `armcpu_spi_unhandled` 与屏幕尾部，回退到 H124。

另：TWRP 实测 `arch_timer = GICv3 19`（`dmesg` 为 `(virt/virt)`），说明正常
启动链下安全世界**至少把定时器那条 PPI 交给了 NS**；Group 0 是本次启动链的
交接结果，不是硬件常量。上游对比报告里"只能由安全世界写死"的表述需要按此修正。

## H125b：PPI 19 推迟使能 + 中断风暴保护（2026-11-06）

H125 的教训是把"写 GIC"放在 `enableGic()` 早期路径上。H125b 只做两件事：

1. **早期恢复 H124 行为**：`kSgiPpiEnable` 回到 `0xffff | (1<<27)`；删掉早期
   `IGROUPR0` 写、`ISENABLER0` 清/置 19、`GICD_CTLR |= DS` 写；只保留只读采样
   （`NATIVE_GIC4: grp/isen/pend/pend2/dctl/dgrp1`）。
2. **PPI 19 推迟到 120 s**：新增 `armcpu_enable_ppi19()`，由 `NativeUfsProbe`
   在 120 s 强制 dump 前调用（此时系统已跑 2 分钟，日志/中断上下文稳定），
   并打印 `NATIVE_PPI19: done=.. isen_before=.. isen_after=.. pend=..`。
3. **风暴保护**：`ArmCpu::interrupt()` 单次调用里摘取超过 32 个中断时，
   直接 `ICENABLER` 掉该 INTID（PPI 用 redistributor，SPI 用 distributor），
   记录 `armcpu_irq_storm_id/count` 后返回。上游 `uefi-sheng` 的
   `Gic-Spurious.patch` 正是处理同一类问题。
4. `NATIVE_IRQ` 增加 `first=`（第一次取到的 INTID）、`storm=`/`sn=`。

```text
H125b kernel:  5f18e46865ead282ed3ed90af1ec4474955a98defb7a5e1107cf291dc8b4d472
H125b payload: 153678fe7a9f8b13558c2c4a1907cfbd972b810beb5d32ad585e5300dc057d3d
H125b boot:    2e8a5399190db3057574994aca37b846d36dc71c557202048056eb287e60dd1b
```

子模块 `drivers/ArmCpu` 提交 `d9c0b1a`（分支 `h118-gic-cache`，已推送）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H125b.img`（已核对）、
Mac `~/h103/boot-H125b.img`、仓库 `out/cheeseburger/boot/boot-H125b.img`。
args 与 H124 相同（不含 `armcpu-spi-ipi`，与 H125spi 互不影响）。

判读：

- 先看能否正常启动到 120 s 并打印 `NATIVE_PPI19`；
- `t19 > 0` 且 `timer` 开始增长 → 定时器确实在 INTID 19，接下来把它设为默认
  定时器源并去掉 27；
- `storm=19` → 19 是一条无消费者的电平线，被风暴保护关掉，说明 19 不是定时器；
- `first=..` 是这台机器上第一次真正取到的 INTID，可作为"中断到底有没有进来"的
  第一手证据。

## H125b 废弃与 H125spi2（2026-11-06）

**H125b 废弃**：该镜像连续三次停在同一位置，屏幕最后是成片的

```text
dyld[1]: 0x1D725C000->0x1D729FFFF init=5, max=5 __TEXT_STUBS
dyld[1]: ... __TEXT / __DATA_CONST / __DATA / __LINKEDIT ...
```

这段输出**不是错误**：`patches/xnu/offline-owner-systemos-mount.patch` 会给 launchd
注入 `DYLD_PRINT_SEGMENTS=1` / `DYLD_PRINT_LIBRARIES=1` /
`DYLD_PRINT_TO_FILE=/dev/console`，dyld 因此把共享缓存的每个 region 权限打到
console；平时被后续 `NATIVE_*` 顶掉，挂住时才留在屏幕上。

同一时间 `boot-H124.img` 正常启动，所以**设备与 Data/preboot 状态没问题**，问题在
H125b 内核。H125b 早期路径与 H124 的差异只有：`enableGic()` 里新增的 6 次 MMIO
只读（`IGROUPR0/ISENABLER0/ISPENDR0×2/GICD_CTLR/GICD_IGROUPR1`）、风暴保护、
以及 120 s 才调用的 `armcpu_enable_ppi19()`（卡点在 ~40 s，未执行到）。H118 已
证明"在别的上下文读 GIC 寄存器会挂"，因此后续任何 PPI 19 实验只保留**一条**
最小读，不再一次加一整套。**不再使用 boot-H125b.img。**

**H125spi 结论：不确定，不能当否定**。`H125spi-log-20261106-163311.txt` 里

```text
[195.06] NATIVE_IRQ: timer=0 ipi=0 ... ipend=40280000
[200.27] NATIVE_IRQ: timer=0 ipi=0 ...
```

`ipi=` 是**收到**的 IPI 数，日志里没有"发送过多少 IPI"的计数；`armcpu-spi-ipi=1`
只改变 `signalCPU()` 的实现，如果内核一次都没调用，就不会有 SPI 发出。

**H125spi2（当前候选，零构建）**：H124 内核不变，payload 的 args 追加
`armcpu-spi-ipi=1 armcpu-self-ipi=1`。`armcpu-self-ipi` 会让 `initCPU` 尾部强制
发一次自 IPI（走 SPI 1008+core），保证"一定发过一次"，`ipi=` 才有判读意义。

```text
H125spi2 kernel:  5f8350f1dffcb1e136d0c657f8cb81ff029981704b66bb2464e8f7d0e7e482c1 (H124)
H125spi2 payload: 05fcf287404402b135a6f3507eea0e64f3c8b473b83237579fb366d0f0efa8a4
H125spi2 boot:    83d37ffab0328799167a982dba0cac521f0cadb95ef6f7f5588cbb29c2ca687c
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H125spi2.img`（已核对）、
Mac `~/h103/boot-H125spi2.img`、仓库 `out/cheeseburger/boot/boot-H125spi2.img`。

判读 `NATIVE_IRQ: ... ipi=N`：

- `ipi > 0` → SPI 可写可投递，中断空间不是全锁死；下一步评估用
  `arch_mem_timer`（TWRP `/proc/interrupts` 的 `GICv3 39`，SPI）做 tick 源；
- `ipi = 0` → SPI 也归安全世界或路由写不进，SPI 线关闭；中断只剩
  "PPI 19 交接/固件"两条路；
- panic/卡死 → 记录屏幕尾部与 `armcpu_spi_unhandled`，回退 H124。

## H124-2（15 分钟运行）与 B4 中断结论（2026-11-06）

`H124-2-log-20261106-174445.txt`（同一 `boot-H124.img`，等 15 分钟后导出）：

- 日志最后一条 `[196.875] NATIVE_CACHE_SIG`，头部 `uptime_s: 172`；
- 控制台最后是 `pid=92 countryd / pid=91 cryptexd / pid=90 eligibilityd`，同在这一带；
- `NATIVE_IOKIT ... comm=backboardd`：**0 条**（全部 IOKit 行只有 UserEventAgent、
  containermanager）。

结论：**"启动太慢、backboardd 还没轮到"不成立**——这次系统在 ~200 s 就停住了。
无中断时用户态会在 200 s 附近随机停住（H122/H125spi2 能到 400 s+，H124-2 只有 ~197 s），
等更久只是等同一个停点。

**证据链（B4 / 中断）：**

| 层 | 结论 | 依据 |
| --- | --- | --- |
| SGI/PPI | 全部 Group 0，NS 写不进 | H122：`IGROUPR0` 写 `1<<27` 回读 0 |
| SPI | 自 IPI 也投递不到 | H125spi2：`armcpu-self-ipi=1` 强制发 SPI 1008，`ipi` 仍 0 |
| 对照 | 同设备、同 `fastboot boot` 的 TWRP/Linux 定时器正常 | TWRP：`arch_timer = GICv3 19`，计数在涨 |
| 差异 | 只在 ABL→edk2→DarwinBoot 这条链 | TWRP 是 ABL→Linux 内核直启 |
| 后果 | 用户态 ~200 s 停住，backboardd 到不了显示初始化 | H122/H124/H124-2/H125spi2 |

**决定：内核侧 GIC 实验全部停止**（H125/H125b 已证明会挂死），只保留
`boot-H124.img` 作为稳定基线。唯一剩下的路线是固件侧：在 edk2 里做**只读** GIC dump，
确认 Group 0 是进入 UEFI 前就有（TZ/ABL 交接），还是 UEFI 期间被改的（可修）。

## H126：UEFI 侧 GIC 交接快照（2026-11-06）

背景：H124-2 证明"等更久"无效（~197 s 停住、无 `comm=backboardd`），H122/H125spi2
证明内核侧拿不到任何中断（PPI/SGI 分组写不进、SPI 自 IPI 也到不了），而 TWRP/Linux
在同设备、同 `fastboot boot` 下定时器正常。因此只剩"启动链交接"一个变量，需要看
**进入 UEFI 时 GIC 是什么状态**。

改动（`edk2-msm8998` fork，提交 `c2d06c2`，分支 `unixnu-cheeseburger`，已推 `fork`）：

- `Platforms/Msm8998Pkg/Device/oneplus/cheeseburger/Drivers/CheeseburgerBootMemoryDxe`：
  驱动进入时、以及 ExitBootServices 事件各打印一次 GIC 快照（`Print` 到 UEFI console）；
- `Common/edk2/ArmPkg/Drivers/ArmGic/GicV3/ArmGicV3Dxe.c`：在**任何写之前**打印一次；
  vendored edk2 的改动另存为 `Patches/h126-gic-snapshot.patch`（1002 行 diff）；
- 输出：

```text
UNIXNU-GIC[-entry|-exit]: CTLR=%08x DS=%d ARE=%d TYPER=%08x%08x IGROUPR0=%08x ISENABLER0=%08x ISPENDR0=%08x WAKER=%08x
```

构建（本机 Linux，1m52s）：

```sh
cd edk2-msm8998
UNIXNU_TREE=/mnt/data_2048/project/ios/UniXNU ./build.sh --device cheeseburger --skip-rootfs-gen
```

产物：`workspace/uefi-cheeseburger.img.gz-dtb` `635e735a7a0a0576d74b5e812b184596c4294a0018ad9b6a55ac3bcf830e88b5`

```text
H126-gic boot: 62aa3a430e4d24c320339f72a4e18c25f2bbe0beabc501533a00fd8d6ff6bded
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H126-gic.img`（已核对）、
Mac `~/h103/boot-H126-gic.img`、仓库 `out/cheeseburger/boot/boot-H126-gic.img`。
payload 用 H124 的（内核未改），只换 firmware 字段。

判读：

- `UNIXNU-GIC`（ArmGicDxe，最早）就已经 `DS=0` 且 `IGROUPR0=00000000`
  → 安全世界/ABL 在进入 UEFI 前就这样交接；内核侧彻底无解，只能继续查 ABL/TZ
  为什么对 Linux 镜像与对我们镜像不同；
- 若最早处是 `DS=1` 或 `IGROUPR0=ffffffff`、而 `-exit` 变了
  → 变化发生在我们能控制的 UEFI/DarwinBoot 链里，可以定位到具体驱动；
- 三处都一样且都是 Group 0 → 同上，属交接问题。

## H126b：把 GIC 快照钉在屏幕上（2026-11-06）

H126 上机后 `boot-H126-gic.img` 在 UEFI 阶段没有留下可读的 `UNIXNU-GIC` 行
（早于菜单/内存图被滚掉），并且这次还撞上 DarwinBoot 的 256 MB 窗口分配失败：

```text
NO WINDOW 10000000 BIG RUN FCC C0000 @ 180000
DARWINBOOT: boot refused: ...; firmware retained
```

`WINDOW_SIZE = SIZE_256MB`（`DarwinBoot.c:20`），而这次最大的连续 conventional
run 只有 `0xFCC0000`（252.5 MB），差 4 MB → `EFI_OUT_OF_RESOURCES`，内核没启动，
所以也拿不到 `-exit` 那一行。

另外对比发现：本次重建的 firmware 与 `fw-H103ea.img.gz-dtb` 解压后
（都是 6,291,456 B）有 **1,000,022 字节不同**，说明 H103ea 不是用当前这棵树/同一
构建模式产出的（很可能是 DEBUG 构建）。因此重建固件不能当作"只多了打印"的等价物，
`boot-H124.img` 里的旧固件仍是唯一能稳定进系统的固件。

H126b 改动：

1. `ArmGicV3Dxe`：打印 GIC 快照后 `gBS->Stall (10 秒)`，给拍照留出窗口；
2. `CheeseburgerBootMemoryDxe`：注册 1 秒周期事件，反复打印同一组
   `UNIXNU-GIC-loop`，保证屏幕最后一行永远是它；
3. `drivers/DarwinBoot`：`WINDOW_SIZE` 临时改为 `SIZE_128MB + SIZE_64MB`（192 MB），
   绕开 252.5 MB < 256 MB 的窗口失败（**这是诊断用改动，最终要回到 `SIZE_256MB`
   或修好固件内存图**）。

```text
H126b firmware: 6e697c5bc64bd35d38e1b680820f049aa04348bf44341f1ccf23b466e61f4940
H126b boot:     78de391f7ed571656f2013142e12158655e8f169c6e47a39d4e91d281eb25872
```

edk2-msm8998 提交 `21f5243`（分支 `unixnu-cheeseburger`，已推 `fork`）；
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H126b-gic.img`（已核对）、
Mac `~/h103/boot-H126b-gic.img`、仓库 `out/cheeseburger/boot/boot-H126b-gic.img`。

判读：屏幕底部的 `UNIXNU-GIC-loop:`（以及更早的 `UNIXNU-GIC:` / `-entry`）：

- 三处都 `DS=0`、`IGROUPR0=00000000` → 安全世界/ABL 在进 UEFI 前就这样交接；
- 若最早 `UNIXNU-GIC:` 是 `DS=1` 或 `IGROUPR0=ffffffff`、后面变了 → 变化在 UEFI 链里。

## H126c：用 DiagDraw 把 GIC 状态画到屏幕上（2026-11-06）

H126b 上机后屏幕与 H126 完全一致，进一步定位到两个事实：

1. **窗口大小来自 payload 的 ADT，不是固件宏**。`kernel.macho.adt` 的
   `chosen/darwinboot-memory-size` 是 `0x1_0000_0000`（4 GiB）；
   `DarwinBoot` 只在 ADT 没有该属性时才用 `WINDOW_SIZE`。所以 H126b 把宏改成
   192 MB 完全无效，屏幕仍是 4 GiB 窗口 + 最大连续 run `0xFCCC0000`（3.94 GiB），
   差 64 MB → `NO WINDOW`。H124 能启动是因为旧固件 `fw-H103ea` 留下的内存图里
   那块连续区刚好 ≥ 4 GiB，重建固件多占约 64 MB 后就不够了。
2. **`Print`（UEFI console）在 UniXNU 菜单接管屏幕后不可见**。屏幕上能看到的
   `NO WINDOW` / `FREE` 是 `DiagDraw` 直接写 framebuffer 画的；H126/H126b 的
   `UNIXNU-GIC` 全是 `Print`，所以一直看不到。

H126c 改动：

- `drivers/DarwinBoot`：新增 `GicRead32` / `DiagGic`，在 `Boot()` 开头用
  `DiagDraw` 在屏幕第 9 行画一行：
  ```text
  GIC CTLR=........ DS=. ARE=. IGROUPR0=........ ISEN=........ ISPEND=........ WAKER=........
  ```
- 去掉 ArmGicDxe 的 10 秒 `Stall`、`CheeseburgerBootMemoryDxe` 的 1 秒轮询
  （都不可见），`WINDOW_SIZE` 恢复 `SIZE_256MB`（ADT 存在时它本来就不生效）。
- **ADT 不动**：保持 4 GiB 窗口，让启动继续停在 UEFI，屏幕保持不动便于拍照。

```text
H126c firmware: 15e529be48b0726dfc3f53f7c735d8a2cfb4f2937637819783108eb38fb216be
H126c boot:     c3b0842a797d7bd3524b629fe7c2043c529d2af32f19ae9496d120005c07ec24
```

edk2-msm8998 提交 `02a1ace`（分支 `unixnu-cheeseburger`，已推 `fork`）；
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H126c-gic.img`（已核对）、
Mac `~/h103/boot-H126c-gic.img`、仓库 `out/cheeseburger/boot/boot-H126c-gic.img`。

判读（屏幕第 9 行）：

| 读数 | 结论 |
| --- | --- |
| `DS=0` 且 `IGROUPR0=00000000` | 进入 UEFI 时就已经是 Group 0 → 安全世界/ABL 交接问题 |
| `DS=1` 或 `IGROUPR0=ffffffff` | 交接是正常的，问题在别处（需再查） |

后续（H126d）：把 ADT 的 `darwinboot-memory-size` 降到 2 GiB 重打 payload，
即可让内核重新启动（无需重建固件）。

## H127：按 UEFI 交接数据改用 PPI 19 / 全 PPI 观察（2026-11-06）

H126c 在 UEFI 交接处画出的 GIC 状态（`boot-H126c-gic.img`）：

```text
GIC CTLR=00000012 DS=0 ARE=1 IGROUPR0=00000000 ISEN=240C0000 ISPEND=40200000 WAKER=00000000
```

解码：

- `CTLR=0x12`：EnableGrp1NS + ARE_NS，**DS=0**；
- `IGROUPR0=0`：**从非安全态读这个寄存器是 RAZ/WI**，读 0 并不代表 Group 0
  （此前 H122 的"全 Group 0"结论据此作废）；
- `ISEN=0x240C0000`：非安全视角能看到 **PPI 29/26/19/18 已使能** → 它们是 Group 1 NS；
  其中 **19 正是 TWRP/Linux 的 arch_timer INTID**；
- `ISPEND=0x40200000`：PPI 30（物理定时器）在拉高但未使能；
- `WAKER=0`：redistributor 已唤醒。

问题因此改写为：`ArmCpu::wakeRedistributor()` 里的 `ICENABLER0=0xffffffff`
把这 4 个已交给 NS 的 PPI 全关了，然后只重开 SGI 0-7 和 **PPI 27**（不在 NS 集合里），
所以 `timer=0`。

H127 改动（在 H124 基线上）：

- `kSgiPpiEnable = 0xffff | 0xffff0000`（SGI + 全部 PPI 16–31）；
- 分发器：`16..31` 全部记入 `armcpu_ppi_seen`（bit = INTID-16）后 EOI，不再 panic；
  其中 19 与 27 调 `rtclock_intr(0)` 并分别计数；
- 保留 H125b 的风暴保护（单次 drain > 32 就关掉该 INTID 并记录）；
- `NATIVE_IRQ` 增加 `seen=%llx`。

```text
H127 kernel:  9b82687044bb21feecfbec1fde4b441cb9e2f3d70d7ad658078827cf519a2abc
H127 payload: 82e2cad0bf49d14fd0db9514c9286688354571ae4302b39983fbf236521b4475
H127 boot:    d6c17b02c2b83f92d5902e3e762d058185e86ac67db55d556286ebdb45cd6bee
```

firmware 用回可启动的 `fw-H103ea.img.gz-dtb`（`163917aa…`），只换 payload 里的
kernel。子模块 `drivers/ArmCpu` 提交 `cc5f7d9`（分支 `h118-gic-cache`，已推送），
父仓库 `f016756`。

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127.img`（已核对）、
Mac `~/h103/boot-H127.img`、仓库 `out/cheeseburger/boot/boot-H127.img`。

判读 `NATIVE_IRQ: ... t19=.. t27=.. seen=....`：

- `seen` 出现 bit19（`0x8xxxx`）→ 定时器就是 PPI 19，`t19`/`timer` 应开始增长；
- 出现 bit18/26/29 → NS 还能收到这些，可作备选；
- `seen=0` 且 `storm=` 有值 → 某条线在风暴，被保护关掉，看 `storm=` 的 ID。

## H127b：最小改动——只多使能 PPI 19（2026-11-06）

H127（使能全部 PPI 16–31）两次都确定性卡在
`NATIVE_LEGACY: IOSurface status=0 found=0` 之后，比 H124 的正常停点早得多。
把它和 H125（19+27+分组/DS 写）、H125b（27 + 6 次额外 MMIO 读）对齐后唯一的共同点：
**只有"只开 27、没有任何额外 GIC 读"的 H124 能启动**；那 6 次额外读是 H125b 加的
（`IGROUPR0/ISENABLER0/ISPENDR0/GICD_CTLR/GICD_IGROUPR1`），H118 已记录过从别的上下文
读 GIC 会挂。

H127b 因此回到 **H122/H124 的 `ArmCpu.cpp` 原样**，只做三件事：

1. `kSgiPpiEnable = 0xffff | (1<<19) | (1<<27)`（只多一个 19）；
2. 分发器：19 与 27 都调 `rtclock_intr(0)`，分别计数 `t19`/`t27`；
3. 最小风暴保护：单次 drain > 32 就 `ICENABLER` 掉该 INTID 并记录 `storm=`;
4. **不加**任何额外 GIC 读/写（无 `IGROUPR0` 写、无 DS 写、无 `pend/dgrp` 读）。

`NativeUfsProbe` 回到 H124 版本，只在 `NATIVE_IRQ` 里追加
`t19=.. t27=.. storm=.. sn=..`。

```text
H127b kernel:  f0750abd6a67afe0166172062252ffa7824e6583d45262396e4dc20b2a8a511c
H127b payload: 2ae45a80826a59d13183d21d008a9268a4faaca0acfc89d6f2c026dc1f261ff2
H127b boot:    b303462f89bb8a2a6abe8427f0a3531105259af1bc1608241520dd8f91c7f54c
```

firmware 继续用可启动的 `fw-H103ea`（`163917aa…`）。子模块 `drivers/ArmCpu` 提交
`4ca3706`（分支 `h118-gic-cache`，已推送），父仓库 `148d073`。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127b.img`（已核对）、
Mac `~/h103/boot-H127b.img`、仓库 `out/cheeseburger/boot/boot-H127b.img`。

判读 `NATIVE_IRQ`：

- `t19 > 0` → 定时器就是 PPI 19，抢占/超时恢复；
- `storm=19`（或 27）→ 该线确实到达但电平未消（没被重新装载），风暴保护关掉了它，
  下一步把 `rtclock_intr` 的调用时机/重装逻辑接对；
- `t19=0`、`storm=0` → 19 仍不可投递，回到 H124 结论。

## H127c：PPI 19 只计数、不驱动时钟（2026-11-06）

H127b（19+27，19 送 `rtclock_intr`）上机后停在同一带：

```text
NATIVE_UFS_LOG: deferred snapshot to window read
NATIVE_UFS_HB: enter
NATIVE_UFS_IO: ...        <- 第一笔 UFS I/O 之后不动
```

对齐后的规律：**只要 PPI 19 被使能，就会在第一笔 I/O 前后停住**（H125、H127、H127b），
只开 27 的 H124/H125b 不会。说明 19 的中断确实会到 EL1，但在那个时刻驱动
`rtclock_intr(0)` 会把时钟/定时器子系统弄坏。

H127c 只改一处：19 计数后直接 EOI，**不再调 `rtclock_intr`**；27 保持原路径；
风暴保护保留（19 若是电平线，33 次后会被 `ICENABLER` 掉并记 `storm=19`，系统应能继续）。

```text
H127c kernel:  35351aef38f642fca8920914e12289fa9d568a355b7a0fa4acf143e8d64a1478
H127c payload: 1e6292d6da32700971e770fcfa5b2545ed1225d0afb88aa1f3b1c88c5cc307da
H127c boot:    fd1228cda3dcca37bb96f9db0d2df383daa38cdc53f0d514895e53b84184763b
```

firmware 仍用可启动的 `fw-H103ea`（`163917aa…`）。子模块 `drivers/ArmCpu` 提交
`HEAD`（分支 `h118-gic-cache`）。
镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127c.img`（已核对）、
Mac `~/h103/boot-H127c.img`、仓库 `out/cheeseburger/boot/boot-H127c.img`。

判读：

- 能越过第一笔 I/O、跑到 197 s 写出日志，且 `t19 > 0`（通常 `storm=19`）→ 19 确实送达；
- 下一版把 19 在**时钟就绪之后**（例如 UFS 路径 120 s 处）再接进 `rtclock_intr`，
  并确保重装 CNTV；
- 若仍停在原位 → 使能 19 本身破坏了某条线，改为只读方案。

## H127c 结果与 H127d（2026-11-06）

**H127c 上机确认：PPI 19 就是这颗 SoC 的定时器中断，而且确实送达 EL1。**

```text
NATIVE_IRQ: timer=434919119 ipi=0 ... t19=434919119 t27=0 storm=ffffffff sn=0
```

- `t19` 一路上涨、`t27` 恒 0 → 定时器在 **INTID 19**（与 TWRP/Linux 的 arch_timer 一致）；
- 系统跑到 500 s，进程/IOKit/launchd 都在动；
- 因为只计数、没有重新装载 CNTV，电平一直拉着，中断率约 **40 万/秒**
  （`t19`/时间），CPU 大量耗在中断里；
- 风暴保护没有触发（`storm=ffffffff sn=0`）。

H127b（19 直接接 `rtclock_intr`）在第一笔 UFS I/O 处挂 → 早期就让定时器打断存储/驱动
初始化不安全，所以 H127d 采用分阶段：

1. 120 s 之前：19 只计数（等同 H127c，已验证可启动）；
2. 120 s 的 UFS dump 点把 `armcpu_timer_dispatch` 置 1，并打印
   `NATIVE_TIMER_DISPATCH: on t19=.. t27=..`；
3. 之后 19 的每次中断：调 `rtclock_intr(0)`，然后主动
   `CNTV_TVAL = 192000`（10 ms @19.2 MHz）+ `CNTV_CTL = 1`，把电平消掉、中断率降到 100 Hz；
4. 27 保持原路径；仍然没有任何额外 GIC 读/写。

```text
H127d kernel:  616e71dc7d81ef79fe4bb9e788f2b24e1b0b9aec2dc5359cf7d628a2e9090898
H127d payload: c36deccb5f975d6eddb8d5cdc607b4354845ad8a96ced011aff8dbd92f2bdc19
H127d boot:    2cfd7e1cb738cc6408b14ebf7c3750e8361674b9246fe766c933a85a94196eeb
```

firmware 仍用可启动的 `fw-H103ea`（`163917aa…`）。子模块 `drivers/ArmCpu` 与父仓库
均已提交并推送。镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127d.img`（已核对）、
Mac `~/h103/boot-H127d.img`、仓库 `out/cheeseburger/boot/boot-H127d.img`。

判读：

- `NATIVE_IRQ` 的 `timer`/`t19` **增量速率**应从 ~40 万/秒降到 ~100/秒；
- 若随后系统能越过 200 s 的停点、出现更多 `NATIVE_EXEC`/`NATIVE_IOKIT`，说明定时器
  已经把超时/抢占带回正轨；
- 若 120 s 之后立刻挂，说明 `rtclock_intr` 在这条路径上不安全，下一版只重装 CNTV
  并自己数 tick。

### H127e：只验证 CNTV 重装，不调用 `rtclock_intr`（2026-11-06）

H127d 日志 `/home/ls/UniXNU/h126d-log-20261106-210032.txt` 是 8 KiB 环形消息区，
已到 uptime 2183 s，120 s 时的一次性 dispatch 标记可能已被覆盖；所以不能判断
`armcpu_timer_dispatch` 是否置位。仍可确认：

```text
[2143.55] NATIVE_IRQ: timer=971151029 ... t19=971151029 t27=0 ... tick=0
[2211.80] NATIVE_IRQ: timer=1001202864 ... t19=1001202864 t27=0 ... tick=0
```

`t19` 在约 68 s 增长约 30 M，即 **~440k/s**，与 H127c 的 count-only 速率相当；
`tick=0`，采样 `CNTV_TVAL` 仍显示已到期的负值。结论：H127d 没有证实重装有效，可能是
dispatch 未触发/日志标记已被覆盖，也可能是 `rtclock_intr` 与固定 TVAL 重装互相覆盖。

H127e 只做分离实验：

- 120 s 前仍 count-only；120 s 后 PPI 19 **只写** `CNTV_TVAL=192000`（10 ms），
  不调用 `rtclock_intr`，也不写 `CNTV_CTL`；PPI 27 保持原处理；
- `NATIVE_IRQ` 每次周期采样都带 `dispatch=` 与 `rearm=` 累计数，解决一次性标记会被
  环形日志覆盖的问题；现有 `ctl/tval` 保留作为状态读数；
- 若 `dispatch=1`、`rearm` 增长、`tval` 落入约 0..192000 且 `t19` 增量降到约 100/s，
  说明重装有效；之后再单独把 `rtclock_intr` 接入（不再用固定 TVAL 覆盖 XNU deadline）；
- 若 `dispatch=0`，120 s 切换没触发；若 `dispatch=1` 而 `t19` 仍高速增长且 `tval`
  仍负值，则重装没有控制此中断源，暂停时钟接线并进一步查 timer/PPI 对应关系。

```text
H127e kernel:  7b785c00cd825d404cc4667a2dd1c6926eea22fe116ceb8b10256c757fdd2f01
H127e payload: b76321ab62d9e3efa3cb15305d988451ea75318be3fe76d3a72c3e7cc1e9004e
H127e boot:    8cdf3648bdb493b679f6ac244fd38859e527fc2b6b4f5dd63b13e4b47fc8ba5e
```

firmware 仍用可启动的 `fw-H103ea`。子模块 `drivers/ArmCpu` 提交 `0d06524`，父仓库
代码提交 `38b1b38`、文档提交 `32e6524`（均已推送）；镜像 Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127e.img`
（已核对）、Mac `~/h103/boot-H127e.img`、仓库 `out/cheeseburger/boot/boot-H127e.img`。

H127e 上机结果：日志 `/home/ls/UniXNU/h127e-log-20261106-213856.txt` 的环形区只保留
到 151.9 s（在 120 s 切换点附近），显示切换前 `dispatch=0 rearm=0`；屏幕后续采样
显示 `dispatch=1 rearm=16087`，并可辨认出 `CNTV_CTL=1`（ENABLE=1、ISTATUS=0）。这证明
H127e 的重装分支确实运行，且至少采样时 timer status 已清；但日志文件缺少切换后的
周期样本，无法计算长期速率，也无法确认是否最终稳定在 ~100 Hz。`tick=0` 是预期的，
因为 H127e 刻意没有调用 `rtclock_intr`。

### H127f：PPI 19 晚期调用 rtclock，不手动覆盖 deadline

H127e 的“只重装”测试没有发现 CNTV_TVAL 写入失败，因此 H127f 保留 120 s 延迟切换，
但将 PPI 19 分支改为调用 `rtclock_intr(0)`，**移除手动 `CNTV_TVAL` 写入**，让 XNU 自己
设置下一个 deadline。`NATIVE_IRQ` 的 `rearm=` 改为 `clock19=`（rtclock 调用计数），
切换行改为 `NATIVE_TIMER_CLOCK`。

```text
H127f kernel:  7332e4ec1c98b9fef45476d7f9e8f2e427996d5e061931c135d572f085809403
H127f payload: 2d2c43ef66e976f1dad333c765c1e7c0b923dd15e1fd169d435cad427f4cc497
H127f boot:    59b4a4fbe70b3cad407a8e3afb847348f7fd3a7c19c3279c5cf6f9b3e3afbcec
```

子模块 `drivers/ArmCpu` 提交 `3ad455d`（分支 `h118-gic-cache`，已推送）；父仓库源码提交
`a2fe4d1`、文档提交 `6343fa3`（均已推送）。镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127f.img`
（已核对）、Mac `~/h103/boot-H127f.img`、仓库 `out/cheeseburger/boot/boot-H127f.img`。

判读：`dispatch=1` 后若 `clock19` 与 `t19` 同步增长、`tval` 不再长期过期且 `tick`
开始增长，说明 XNU 的 timer-deadline 路径接管成功；若中断风暴/系统挂起，说明
`rtclock_intr` 在该晚期路径仍不安全，应回到 H127e 的 rearm-only 行为。

### H127g：PPI 19 一相到底 + 自纠正重装（2026-11-06）

H127e/H127f 上机后确认了两点：

- H127e 截图里 `dispatch=1 rearm=16087` 与“10 ms 重装 = 100 Hz”吻合（16087 ≈ 160 s × 100），
  说明**手动重装确实能把风暴压下去**，只是没有驱动 XNU 时钟（`tick=0`）；
- H127f 的两次卡屏都是 `dispatch=0 clock19=0`：120 s 切换标志写在
  `h103SlotTick()`（UFS 读路径）里，启动一旦在 dyld 停滞，回调不再发生，切换永远不触发。
  所以“按墙钟 120 s 切换”的设计不成立。

H127g 去掉延迟门控与 UFS 依赖，PPI 19 从**第一个中断**开始就：

1. `rtclock_intr(0)`；
2. 读 `CNTV_CTL`，若 ISTATUS 仍为 1（XNU 没武装下一个 deadline），写
   `CNTV_TVAL = 192000`（10 ms）并累加 `armcpu_timer19_forced_count`；
3. 27 保持原路径；不新增任何 GIC MMIO 读写。

`NATIVE_IRQ` 用 `clock19=`/`forced=` 取代 `dispatch=`/`rearm=`：
`forced` 很小说明 XNU 自己武装；按 ~100/s 增长说明走的是兜底 tick。

```text
H127g kernel:  59519748c1e79dbded8ba6d39695f5a49a361e92342549fe210c50ee997ed881
H127g payload: 83b02325548dd7d610eec23f4b1af2046b6add0b0eb8d3897ff3d37d96c03703
H127g boot:    8325ad4197b4d70a4fd7bf3d4788fafd981e79494a50822c757bddb80a5bb594
```

firmware 仍用可启动的 `fw-H103ea`。子模块 `drivers/ArmCpu` 提交 `3933470`，父仓库
`d103962`。镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127g.img`（已核对）、
Mac `~/h103/boot-H127g.img`、仓库 `out/cheeseburger/boot/boot-H127g.img`。

判读：

- 启动速度回到 H124 水平、`tick` 开始增长 → 时钟接管成功，接着看 200 s 停点是否消失；
- `forced` 按 ~100/s 增长但 `tick` 仍 0 → CNTV 被兜底重装，但 XNU 的 timer_call 没被驱动，
  需要查 `rtclock_intr` 的上下文/参数；
- 早期挂死 → `rtclock_intr` 在第一个中断就调用不安全，退回 H127e 行为（只重装）并改为
  由内核线程轮询。

### H127h：去掉诊断 timer_call，验证 rtclock 是否安全（2026-11-06）

H127g 上机卡在与 H127b 完全相同的位置（`NATIVE_UFS_IO` 之后、第一笔 I/O 处），
而 H127c/H127e（不调 `rtclock_intr`）都能跑，因此问题落在 `rtclock_intr` 路径。

查 `osfmk/arm64/sleh.c`：`sleh_irq()` 只做 prologue + `cdp->interrupt_handler(...)`
（就是我们的 `ArmCpu::dispatch`），**不会**替我们调 `rtclock_intr`（那是 FIQ/PMI 路径），
所以“由 CPU 驱动自己处理定时器”是正确用法，prologue 也已经由 sleh 完成。

最可疑的是：启动参数里有 `h109-tick=1`，它会在**定时器上下文**里每秒 `IOLog` 一行；
第一笔 UFS I/O 同时在大量打日志，两边争用 console 锁，很容易在中断上下文里死锁。

H127h 不重建内核（沿用 H127g，`59519748…`），只在 payload 的 `unixnu.toml` 里把
`h109-tick=1` 改成 `h109-tick=0`：

```text
H127h kernel:  59519748c1e79dbded8ba6d39695f5a49a361e92342549fe210c50ee997ed881 (H127g)
H127h payload: 9645d21067767e28ba7a25fb30f808812c7ebca357d79417db4d868e7bc6c073
H127h boot:    1aa05378fd5e9c1667a4223d43a72e40a605267c971ea4c06042f054a3547861
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127h.img`（已核对）、
Mac `~/h103/boot-H127h.img`、仓库 `out/cheeseburger/boot/boot-H127h.img`。

判读：

- 能越过 `NATIVE_UFS_IO` 继续启动 → 诊断 `timer_call` 在中断里打日志导致死锁，
  `rtclock_intr` 本身没问题；下一步把诊断日志改成只计数、由 UFS 路径打印；
- 仍停在同一位置 → `rtclock_intr`（或其触发的其它 timer_call）在此上下文不安全，
  退回 H127e 的 rearm-only 行为，`tick` 问题另行处理。

### H127h 初步观察（2026-11-06，待日志确认）

用户实测：**H127h 在 dyld 共享缓存加载阶段明显比 H127g 快**，说明去掉
`h109-tick=1`（定时器上下文里的 `IOLog`）确实缓解了中断上下文与 UFS 日志的
console 锁争用，`rtclock_intr` 本身很可能没有问题。

需要注意：用户随后提供的一张屏幕照片与 H127f 卡住那张逐字相同
（`timer=61270801 t19=61270801 tval=0493ee6d dispatch=0 clock19=0`），
那是 H127f 的格式与数值，不是 H127h；H127h 的 `NATIVE_IRQ` 字段是
`clock19=` / `forced=`（没有 `dispatch=`）。**因此 H127h 的 `clock19`/`forced`
走向仍待日志确认。** 另：`tick` 是 `h109-tick` 的计数，本轮已关掉，`tick=0`
不能用来判断时钟是否接管。

待确认项：

1. `clock19` 是否随 `t19` 增长、`forced` 是小值（XNU 自己武装）还是 ~100/s（兜底 tick）；
2. 启动是否能越过 200 s 附近的历史停点，`NATIVE_EXEC` 是否继续增加；
3. `vm_shared_region_start_address() failed`（dyld 共享区）是否仍出现——它是与定时器
   独立的另一条线索。

判据与后续：

- `clock19` 增长、`forced` 小、启动继续 → 时钟接管成功；下一步把诊断日志彻底移出
  定时器上下文，并观察 200 s 停点是否消失；
- `forced` ~100/s → 兜底 tick 生效，XNU 未自行武装 deadline，需要单独查
  `set_timer_deadline` 为何没有生效；
- 仍卡在同一位置 → 退回 H127e 的 rearm-only（速度已知可恢复）。

### H127h 结果与日志拉取改进（2026-11-06）

`h127h-log-20261106-231958.txt`（4.7 KB）里 `NATIVE_IRQ` 稳定为：

```text
timer=211811 ... ctl=1 tval=1366c t19=211811 t27=0 clock19=211811
forced=0 storm=ffffffff sn=0 flags=ef tick=0
```

- **`clock19 == t19`、`forced=0`、`ctl=1`** → PPI 19 完全由 XNU 接管，XNU 自己武装
  deadline，不需要兜底 tick，也没有风暴；中断率约 85/s；
- `uptime_s: 2180`、最后一条 2505 s → **连续运行 42 分钟**，是目前最长的一次；
- `NATIVE_UFS_ALIVE` 正常出现 → `IOSleep` 现在真的会醒；
- **`flags=ef`** = logd_helper + driverkitd + backboardd + SpringBoard 均 exec，
  **SpringBoard 已退出 (0x20)**、**backboardd 已退出 (0x40)**，且
  **backboardd 调用过 IOKit matching (0x80)**（首次出现，但未带 IOMobile 关键字，
  0x200/0x400 未置）。

新出现的故障是**压缩页读失败的死循环**（屏幕可见）：

```text
dpage_pager_compressed: (private): err 94          (EBADMSG)
... Verification failed with error 94 (0x5e) ...
Failed to send exception EXC_CORPSE_NOTIFY. error code: 308
NATIVE_EXEC: ... ReportCrash / NATIVE_EXIT: ... status=0xb
```

即某个压缩文件在读时解压失败（反复同一 `disk1s1` 偏移），AMFI 拒绝该页、进程被杀，
launchd 拉起下一个 XPC 又碰到同一文件 → 循环。我们的补丁里**没有改过 decmpfs 压缩页
路径**，iOS 原生是 16 KiB 页，这条线疑似 4 KiB 与压缩页/校验的交互，待定位到具体文件。

**日志为什么只有 4.7 KB**：写盘是 delta 环，每次 flush 只把 msgbuf 的尾部快照写进一个
32 块（128 KB）槽，全局头里的 `msg_bytes` 只记录**最后一次**的 delta 大小（这次 4096）。
`slots_written: 1291` 说明盘上其实有 1291 份快照，只是拉取工具只读最新那一个。

因此 `scripts/h103-log-pull.py` 新增 `--slots N`：把最后 N 个槽一起解码、按
`[ timestamp ]` 去重排序合并。整个槽环（247×32 块 ≈ 31.6 MB）本来就在 32 MiB 窗口里，
所以同一块盘不用重跑就能取出更长历史：

```sh
python3 scripts/h103-log-pull.py --adb ~/.local/bin/adb --slots 120
```

### H127h 合并日志结论与 H127i（2026-11-06）

`h127-2-log-20261106-233158.txt`（`--slots` 合并，681 KB，66 s → 2505 s）确认：

- **定时器完全正常**：`clock19 == t19`、`forced=0`、`ctl=1`，速率约 80/s，连续运行 42 分钟；
- 系统 exec 571 次、backboardd 被反复拉起；`flags` 一路到 `0xef`；
- **backboardd 反复崩溃 `status=0xa`**（`Too many corpses being created`）；
- 根因是 **SystemOS 读超时**：

```text
NATIVE_UFS_LOCK: window SystemOS blocked req=... 
IOBlockStorageDriver: executeRequest: request failed to start!
disk4: I/O timeout.
_vnode_dev_read: disk4 *** got err 60 reading blknum ... (num read errs: 93..96)
apfs_collect_hash_records: disk4s1 ... Operation timed out(60)
```

`err 60` = ETIMEDOUT；它连锁出 `dpage_pager_compressed: err 94`、AMFI
`Verification failed with error 94` 和进程崩溃。也就是说 backboardd 的 0xa 是**读不到
SystemOS 数据**的症状，不是它自身的缺陷。

嫌疑：我们的 UFS 窗口/日志写入路径在高并发读时抢锁（`executeRequest` 根本没能启动）。
无中断时 I/O 少、问题不明显；定时器恢复后并发读变多，窗口路径成了瓶颈。

H127i 是零构建对照：沿用 H127h 内核，只把 payload 的 `h103-log-secs` 从 5 改成 30，
把 flush 频率降 6 倍：

```text
H127i kernel:  59519748c1e79dbded8ba6d39695f5a49a361e92342549fe210c50ee997ed881 (H127h)
H127i payload: 189567210f55a563e3391e66737d70f189ca8d830bbfc147b7235ddea9a094cb
H127i boot:    7513677f572dc4bef7c53dd7da6220d0fdb649ac51f2766c571f550ba01c847b
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127i.img`（已核对）、
Mac `~/h103/boot-H127i.img`、仓库 `out/cheeseburger/boot/boot-H127i.img`。

判读：

- `disk4: I/O timeout` / `err 60` 明显减少、backboardd 不再 0xa → 是日志窗口争用，
  下一步把 flush 改成真正的后台线程 + 更小窗口；
- 超时照旧 → 是 UFS 窗口设备在高并发下的锁/队列问题（`readWindowBulk`），单独查。

### H127i 结果：日志频率就是 I/O 超时的放大器（2026-11-06）

日志 `h127i-log-20261106-234932.txt`（163 KB，`--slots 120` 合并）：

| 指标 | H127h（`h103-log-secs=5`） | H127i（`h103-log-secs=30`） |
| --- | --- | --- |
| `disk4: I/O timeout` | 93–96 次 | **2 次** |
| `err 60`（ETIMEDOUT） | 93+ | **2** |
| `backboardd` 0xa 崩溃 | 多次 | 0（本次还没 exec） |

即：**之前 SystemOS 读超时是日志 flush 频率过高、在窗口路径上抢锁造成的**；把 flush
降到 30 秒一次后，存储错误回落到可忽略水平。

本次启动的定时器依旧完全正常（只认带 `clock19=` 的行）：

```text
[156.4] NATIVE_IRQ: ... ctl=1 tval=5c33  t19=14403 t27=0 clock19=14403 forced=0 ... flags=0
[217.0] NATIVE_IRQ: ... ctl=1 tval=15d2e t19=22266 t27=0 clock19=22266 forced=0 ... flags=b
[523.9] NATIVE_IRQ: ... ctl=1 tval=3765  t19=24153 t27=0 clock19=24153 forced=0 ... flags=2b
```

`clock19 == t19`、`forced=0`、`ctl=1`，速率约 26/s；`uptime` 到 **820 s** 仍在运行，
`SpringBoard`（pid 33）有 2 条线程可运行；期间 SpringBoard 崩过几次（518/522 s 的
`Corpse allowed`）并被 launchd 重新拉起。`flags=0x2b` 表示 **SpringBoard 已 exec、
backboardd 尚未 exec**（缺 `0x4`）。

**日志内容的一个坑**：`slots_written: 4`，但每个槽是 msgbuf 的尾部快照，开机第一次
flush 会把环形缓冲区里残留的**上一次启动文本**一起拷入，所以同一份合并日志会出现两种
`NATIVE_IRQ` 格式（带 `clock19=` 的是本次，736–775 s 那批不带的是旧启动）。
分析时只认带 `clock19=` 的行；彻底解决需要写槽时带 boot id（工具/写入侧改进）。

结论与后续：

- **把 `h103-log-secs=30` 定为新的日志基线**（保留诊断能力，I/O 干扰降 6 倍）；
- 继续观察 `boot-H127i.img`：`err 60` 是否保持个位数、backboardd 是否 exec
  （`flags` 出现 `0x4`）、若又崩是否仍为 `err 60/94`；
- 日志不再是瓶颈后，主线回到显示：backboardd 为什么不查 `IOMobileFramebuffer`。

### H127i-2：`memcpy` 数据异常 panic（2026-11-07）

`h127i-2-log-20261107-000642.txt`（349 KB）里超时又回到 100+ 次，并最终 panic：

```text
panic(cpu 0 caller 0xfffffff007a7114): Kernel data abort
  pc 0xfffffff007a88ed4 = memcpy + 100
  esr 0x96000007  (translation fault, level 3, 写)
  far 0xfffffff1a6362000
```

用 H127g 的 dSYM 符号化：`pc` 落在 `memcpy`（写方向），`far` 是未映射的内核地址。
结合上下文里的 `dpage_pager_compressed: (private): err 94`、
`descpfs_...`、AMFI `Verification failed with error 94`，判断为**读失败后的次生崩溃**：
解压失败导致目标缓冲区无效或尺寸异常，随后 `memcpy` 写入未映射地址。

该次启动的存储错误样本：

```text
disk4: I/O timeout
_vnode_dev_read:907: disk4 *** got err 60 reading blknum 779768 (num read errs: 101..103)
NATIVE_UFS_LOCK: window SystemOS blocked req=91078 block=3a1e50 count=96
IOBlockStorageDriver: executeRequest: request failed to start!
```

要点：**SystemOS 的全部 I/O 都走我们发布的 window 设备**。`count=96` 的窗口读与
`executeRequest: request failed to start!` 说明该设备在并发下会拒绝/阻塞请求，真实读写
被拖到超时；`h103-log-secs=30` 只是把必然超时降为偶发，负载高时仍会回到 100+ 次。

H127j 是零构建对照：沿用同一内核，只把 `h103-log-secs` 从 30 再提高到 60
（flush 频率再降一半）：

```text
H127j kernel:  59519748c1e79dbded8ba6d39695f5a49a361e92342549fe210c50ee997ed881 (H127g/H127h/H127i 同一内核)
H127j payload: 952ff3df9aab71e5c697e546429d7414c437a07a7b26f80050e54201652c2f38
H127j boot:    a58e59319be4efe1a69ca8f44b2e39471f468433cc24e0c46aca6ba9dcee2cde
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127j.img`（已核对）、
Mac `~/h103/boot-H127j.img`、仓库 `out/cheeseburger/boot/boot-H127j.img`。

判读：

- `err 60` 次数继续下降且不再 panic → 日志写入确实是主要竞争者，下一步做“后台线程 +
  小块可丢弃队列”的写入器，并让 window 设备支持并发排队；
- 仍然 100+ 次或仍 panic → 日志不是唯一来源，需要直接查 window 设备在高并发下的
  队列/锁行为（`executeRequest` 被拒绝）；
- 同时应给读失败路径加防护：`memcpy` 前校验目标缓冲区和长度，避免升级成内核 panic。

### H127j 结果与 H127k（2026-11-07）

`h127j-log-20261107-002401.txt`（286 KB，139–782 s）说明**提高日志间隔并没有改善 I/O**：

| 指标 | H127i（`log-secs=30`） | H127j（`log-secs=60`） |
| --- | --- | --- |
| `err 60` | ~100 | **131** |
| `disk4 / disk5: I/O timeout` | 93 / — | 62 / 88 |
| `executeRequest: request failed to start!` | 多 | **151** |
| `NATIVE_UFS_LOCK: window ... blocked` | 有 | **329** |

定时器依旧正常（`clock19 == t19`、`forced=0`、`ctl=1`）。因此主因不是日志频率。

代码层面定位到根因：`NativeUfsWindow::doAsyncReadWrite()` 是**同步单锁**实现，
`lockWithTimeout(lock, ..., 38400000)` 只有 **2 秒**（19.2 MHz），超时即返回
`kIOReturnTimeout`，于是出现 `executeRequest: request failed to start!` 和 `err 60`。
SystemOS 的所有 I/O 都经过这个设备，一次较长的窗口读（日志里见过 `count=96`）期间
其它请求排队，超过 2 秒就被判死。

H127k 只改锁上限：新增 `UFS_DATA_LOCK_TICKS = 384000000`（20 秒），用于
`readBlocks` 与窗口设备；日志路径（`logWrite`/`logSync`）仍保留 2 秒，避免卡死时拖住系统。
payload 沿用 H127j 的 `h103-log-secs=60`。

```text
H127k kernel:  712864f00970b7a36dfa528ab6a5690ad01d8f71ec2c9ccf4b04ac44d0c3cb1c
H127k payload: 61fe24d48b2aa36a6784638563d2e3f1d4f4c2aeca9bf1471afe2b160c9acd49
H127k boot:    0699e3920825b0c80af0207249dab3c547f4e1f9b977f640671398a6a393a437
```

镜像：Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H127k.img`（已核对）、
Mac `~/h103/boot-H127k.img`、仓库 `out/cheeseburger/boot/boot-H127k.img`。

判读：

- `executeRequest: request failed to start!` 与 `err 60` 大幅下降、崩溃减少 →
  锁超时是主因；下一步把窗口设备改成异步 + 请求队列；
- 仍大量超时 → 单次窗口读真的超过 20 秒，要查 `readBlocks` 的命令轮询/重试上限。

### H128：把诊断移出存储路径（2026-11-07）

H127k（20 秒锁上限）没有改善：`err 60` 131→151、`executeRequest` 151→170、
`NATIVE_UFS_LOCK` 329→357、崩溃 54→73。日志里 `OCS timeout` = **0**、
`bad response` = **0**，每次 `NATIVE_UFS_ALIVE` 都是 `ufsFlight=0`——**没有一次
UFS 命令失败**，20 秒的等待完全是软件造成的。

代码定位（`drivers/NativeUfsProbe/NativeUfsProbe.cpp`）：

1. `ufsSubmit()` 每 64 条命令调 `h105DumpTick()` → `native_proc_state_dump()` /
   `native_proc_wait_graph()`：`proc_iterate()` 取进程列表锁并 `printf` 上百行，
   而且是在 `fLock` 之内执行的。
2. `readBlocks()` / `readWindowBulk()` 调 `h103SlotTick()` → `h103FlushNow()` →
   `h103SlotWrite()`：`IOMallocAligned(128 KiB)` + 拷贝 msg buffer + 两条 UFS
   写命令。`readWindowBulk()` 的调用者 `NativeUfsWindow::doAsyncReadWrite()`
   在整个请求期间持有窗口设备 `lock`，所以这段诊断跑在窗口锁内部。
3. `lockWithTimeout()` 是纯自旋（`IOLockTryLock` + ARM `yield`，不让出 CPU）。
   基线 `cpus=2`（H127i/j/k 的 payload 都是 `cpus=2`），自旋者会把持有者挤住，
   2 秒的等待被拉长成 20 秒，所以 2→20 秒只是把"快速失败"换成"长时间失败"。
4. `h103SlotThread`（2 秒槽线程）无视 `h103-log-secs`，每次启动写约 170 个
   16 KiB 槽，而且 delta 游标不前进，重复写同样的内容。

H128 改动：

- `ufsSubmit()`：删除 `h105DumpTick()` 与 2x2 重绘，只保留 `NATIVE_UFS_PROGRESS`
  计数行；
- `readBlocks()`：`fLock` 改为**每块命令加放一次**（原来一次请求跨整段多块循环
  一直持有全局锁），并删除 `h103SlotTick()`；
- `readWindowBulk()`：删除 `h103SlotTick()`；
- `h103SlotTick()` 改由 `heartbeatThread()`（10 秒，`IOSleep` 已能返回）驱动，
  进程 dump、120 秒强制 dump、持久日志 flush 全部回到线程上下文；
- 2x2 重绘也移到心跳（gate 位变化时重绘）；
- `lockWithTimeout()`：自旋 64 次后改 `IOSleep(1)`，不再饿死持有者；
- `UFS_DATA_LOCK_TICKS` 退回 2 秒（路径干净后只需覆盖一条命令）；
- 2 秒槽线程改为 `h103-slot-thread=1` 才启动（默认关闭）。

payload 沿用 H127k（`cpus=2 h103-slot=1 h103-log-secs=60 h109-tick=0`）。

```text
H128 kernel:  7c229371b059b724bf2ad3383f90e296dba8fdeca5d59b2830f669f45720a7eb
H128 payload: 60e57fbcd457bad42c3df31b18dda27655cede98dd8f19c426582e44c431b756
H128 boot:    783e60e7eb1e3de79f5efbc965070dfadb1b01a2271a24a1d3c8b23461525d87
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H128.img`（已核对）、
Mac `~/h103/boot-H128.img`、仓库 `out/cheeseburger/boot/boot-H128.img`。

判读：`err 60` / `executeRequest: request failed to start!` / `NATIVE_UFS_LOCK`
应接近零，`winReq` 恢复数百/秒；若仍有超时，则问题在 `readBlocks` 的块大小或
窗口设备本身，再按 H127k 的判读往下查。

### H128 结果：存储路径修好，UI 仍不出现（2026-11-07）

`h128-log-20261107-012700.txt`（560 KB，57–901 s）：

| 指标 | H127k | **H128** |
| --- | --- | --- |
| `err 60` | 151 | **12** |
| `executeRequest: request failed to start!` | 170 | **5** |
| `NATIVE_UFS_LOCK` | 357 | **10** |
| `disk4 / disk5: I/O timeout` | 62 / 105 | **4 / 1** |
| `err 94` / panic | 7 / — | **0 / 0** |
| 运行时长 | 538 s | **901 s** |
| `NATIVE_UFS_ALIVE` 的 `winFlight` | 长期 1 | **72/75 为 0** |

`NATIVE_PROC_DUMP`（74 行）与 `NATIVE_WAIT`（184 行）恢复输出，说明 dump 已经跑在
心跳线程的上下文里。结论：**诊断代码离开存储路径后，存储不再是瓶颈**。

#### 仍然不出现 UI 的直接原因

- SpringBoard 每次 exec 后 **0.6–8 秒**就被 launchd 记为 corpse，共 13+ 次
  （pid 26/27/87/88/92/93/96/97/113/125/130/172/190/219…），722 s 后 launchd 不再拉起；
- 同期 powerd / liveactivitiesd / contextstored / sharingd / mobileactivation /
  assistantd 也各崩 14–16 次，总计 131 次 corpse；
- 全程 `IOMobileFramebuffer` 用户客户端一次未打开（`NATIVE_FRAME … client=0
  xfer=0 frames=0`）。

两个日志假象：

- `NATIVE_IOKIT: op=open … ok=0` 的 `ok` 在 patch 里写死为 0，**不代表打开失败**；
- match/open 日志各只记前 24 条且为全局计数，backboardd 后续查询不落盘。但 boot flag
  位 512/1024 不受限制：`flags=af` 只有位 7（128 = backboardd 调过 matching），
  **没有 512/1024**，说明 backboardd 的 matching 字典从未出现 `IOMobile*`。

#### 残留毛刺是参数排序错误

剩余 5 次 2 秒超时全部命中同一 LBA（`block=5b17b0`，333/335/337/542 s），
`ticks≈38400000`（正好 2 秒）。`UFS_DATA_LOCK_TICKS` = 2 s，而
`UFS_TIMEOUT_TICKS` = 5.2 s：命令还在合法执行期内，锁已经判死。
H129 把数据锁上限改为 **6 s**（略大于 5.2 s）。

#### H129 计划

1. `UFS_DATA_LOCK_TICKS` 2 s → 6 s；
2. `native_trace_process_exit()` 加入 `SpringBoard`，打印 `status/ns/code`
   （信号 = `rv & 0x7f`）；
3. IOKit trace 对 backboardd / SpringBoard 取消 24 条上限，并记录每次
   `IOClass/IOProviderClass/IONameMatch` 与结果，直接回答"backboardd 找没找显示服务"。

### H129：测量 SpringBoard 的死因与 backboardd 的 matching（2026-11-07）

三处改动，都不改变正常行为：

1. `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：`UFS_DATA_LOCK_TICKS`
   2 s → **6 s**（115200000）。原来数据锁上限（2 s）比 `UFS_TIMEOUT_TICKS`
   （5.2 s）还短，命令仍在合法执行期内锁就判死；H128 残留的 5 次 2 秒超时
   全部命中同一 LBA `0x5b17b0`，正是这个顺序问题。
2. `patches/xnu/zzzzzzzzzzzzz-h129-diag.patch`：`native_trace_process_exit()`
   把 `SpringBoard` 加入过滤列表，打印 `status/ns/code`（信号 = `rv & 0x7f`）。
   同时顺手去掉了 H103 补丁里多出来的行首 `+`（一元加号，能编译但没意义）。
3. 同一补丁：`native_iokit_log()` 对 `backboardd` / `SpringBoard` **取消 24 条上限**，
   并让 `native_match_trace()` 在没有 `IOClass` 时回退打印 `IONameMatch`。
   这样"backboardd 到底向内核要哪个类、成功与否"会完整落盘。

```text
H129 kernel:  5902d441bc23cd93f4365ce236f58a9f0c19cef8f4f92674520cc77a1bdc4a88
H129 payload: 3f39041073287530c13db1154c4be3d5a0d684afcd8f875051bf25b4977ce397
H129 boot:    dcb30d4db8c24fcc0d59d85120f77b7e1a733a5afc605ac0cb52b12a5a75e410
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H129.img`（已核对）、
Mac `~/h103/boot-H129.img`、仓库 `out/cheeseburger/boot/boot-H129.img`。

判读要点：

- `NATIVE_EXIT: … comm=SpringBoard status=0x…` 的 `status & 0x7f` 是信号
  （11=SIGSEGV、6=SIGABRT、4=SIGILL、9=SIGKILL），`ns` 是 `os_reason` 命名空间
  （jetsam/crash/codesigning），`code` 是具体代码；
- `NATIVE_IOKIT: op=match comm=backboardd cls=… d=… ok=…` 首次出现即说明
  backboardd 开始找显示服务，`ok=1` 表示注册表里能匹配到；
- `err 60` 应归零；若 6 秒仍不够，说明单次命令确实超过 6 秒，要查 UFS 设备侧。

### H129 结果：存储归零，SpringBoard 是 ObjC 异常（2026-11-07）

`h129-log-20261107-015227.txt`（370 KB，57–775 s）：

| 指标 | H128 | **H129** |
| --- | --- | --- |
| `err 60` | 12 | **0** |
| `executeRequest: request failed` | 5 | **0** |
| `NATIVE_UFS_LOCK` | 10 | **0** |

存储路径彻底干净。`UFS_DATA_LOCK_TICKS` = 6 s > `UFS_TIMEOUT_TICKS` 5.2 s
之后，同一 LBA 的重复超时消失。

SpringBoard 共 16 次退出，**签名完全一致**：

```text
NATIVE_EXIT: pid=… comm=SpringBoard status=0x6 ns=8 code=0x1
```

`status=0x6` 是 SIGABRT；`ns=8` 在 `bsd/sys/reason.h` 中是 **`OS_REASON_OBJC`**，
即 `objc_exception_throw` → `abort_with_payload()`，不是段错误、不是 jetsam。

backboardd 的 matching 全记录（H129 取消上限后）：

```text
match comm=backboardd cls=-              d=-                      ok=0
match comm=backboardd cls=aop-smart-cover d=-                     ok=0
match comm=backboardd cls=multi-touch     d=-                     ok=0
match comm=backboardd cls=mtp-transport   d=-                     ok=0
match comm=backboardd cls=-              d=IOPlatformExpertDevice ok=1
open  comm=backboardd cls=IOPMrootDomain
```

**没有任何一次 `IOMobileFramebuffer` / `IOFramebuffer` 查询**，配合
`IOMobileFramebufferLegacy::start: provider was not AppleARMIODevice`（65 s）
和 `NATIVE_FRAME … client=0 frames=0`，说明 backboardd 的显示初始化从未开始。

### H130：打印异常描述串（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzz-h130-exit-desc.patch`：

- `native_trace_process_exit()` 先取 `ns/code`，再决定是否过滤，因此**任何
  `ns != 0` 的退出都会被记录**（ObjC 异常、dyld abort、jetsam、exec 失败）；
- 追加 `NATIVE_EXIT_DESC` 行，内容来自现成的 `exit_reason_get_string_desc()`
  （`kern_exit.c:1305`，launchd panic 用的是同一个访问器），截断到 320 字符；
- 描述为空时回退打印 kcdata 缓冲区的可打印字节（`NATIVE_EXIT_RAW` 同格式）。

```text
H130 kernel:  9bbe0ff2bfb143eb7d725ec39092dcf929540df2e20f80024fdd1de07e9aa708
H130 payload: 6e92ef1d9e8e120ec764aceaabb375a3b0e9e54eb139b8c84d953a2167c48b41
H130 boot:    f42d020fe3ae06c450a23baaf67c15e38729177c4af7454b9f3dfe7d7c31c7b9
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H130.img`（已核对）、
Mac `~/h103/boot-H130.img`、仓库 `out/cheeseburger/boot/boot-H130.img`。

判读：`NATIVE_EXIT_DESC: … comm=SpringBoard …` 里的异常名与 reason 决定下一步——
若是显示/BackBoard 断言，修的是 `IOMobileFramebufferLegacy::start()` 的 provider
判定；若是无关的缺类/缺服务，直接按描述定位。

### H130 结果：SpringBoard 死于缺 libobjc-trampolines（2026-11-07）

`h130-log-20261107-021306.txt`（573 KB，51–775 s，`err 60` 仍为 0）：

98 条 `NATIVE_EXIT_DESC` 中有 **62 条完全相同**：

```text
couldn't dlopen libobjc-trampolines.dylib:
dlopen(/usr/lib/libobjc-trampolines.dylib, 0x0106):
tried: '/usr/lib/libobjc-trampolines.dylib' (no such file, not in dyld cache)
```

受影响：SpringBoard 16、powerd 16、contextstored 15、sharingd 7、assistantd 4、
imagent 3、mobiletimerd 1，全部 `ns=8`（`OS_REASON_OBJC`）、`status=0x6`
（SIGABRT）。**ObjC 运行时装不上 trampolines，所有 ObjC 进程一起 abort**，
这才是 SpringBoard 0.6 秒就死的直接原因；backboardd 只是被拖着没机会做显示初始化。
次级崩溃：PerfPowerService `ns=2 sig=6`、liveactivitiesd/mobileactivationd `ns=2 sig=5`。

#### 根因：`/usr/lib` 缺 cryptex 那一层

在 Mac 上挂载原始 DMG 逐项核对：

| 来源 | `/usr/lib` |
| --- | --- |
| `044-76040-038.dmg`（OS 卷，6.1 GB） | 19 项：dyld、libRPAC、libz、asan…，**无** `libobjc-trampolines.dylib` |
| `044-76034-038.dmg`（SystemCryptex，3.3 GB） | 9 项：`libobjc-trampolines.dylib`、`libffi-trampolines.dylib`、`libstdc++.6.0.9.dylib`、`libglInterpose`、`libLogRedirect`、`libCoreLSKD`、符号链接与 `swift/` |

**两边零重叠**：cryptex 的 `/usr/lib` 只做补充，不会覆盖 OS 卷的 `dyld` 等文件。
当前内核只把 cryptex 挂在 `/private/preboot/Cryptexes/OS`
（`/System/Cryptexes/OS` 是指向它的符号链接），**没有 union**，所以 `/usr/lib`
只解析到 OS 卷。

### H131：只 union `/usr/lib`（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzz-h131-usrlib-union.patch`：

- 在 `native_owner_cache_prepare()`（SystemOS 挂载）之后新增
  `native_cryptex_usrlib_prepare()`；
- 用仓库已有的同一套机制：
  `mount("bindfs", "/usr/lib", MNT_RDONLY|MNT_UNION, "/private/preboot/Cryptexes/OS/usr/lib")`；
- 挂载前后各做一次 `vnode_lookup("/usr/lib/libobjc-trampolines.dylib")`；
- 失败只记录、不 panic。

预期日志：`NATIVE_CRYPTEX_USRLIB: before=2 mount=0 result=0 after=0`
（ENOENT → 成功）。若 union 层本身有问题，回退 `boot-H130.img`；也可以退一步改成
内核里对 `/usr/lib/*` 的单点重定向。

```text
H131 kernel:  98ccafd6a2743d2fbafc4d76b46f65325865c252c080b911410657e2dbcb7d7c
H131 payload: 00147955814bf095c13e2fb51c238a6c028cf712eeede819441f05116e4d8101
H131 boot:    17e50f6f10e4cf3e53291dd7ec78bc9f779e76670588c7d878ca15c7c106cb0b
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H131.img`（已核对）、
Mac `~/h103/boot-H131.img`、仓库 `out/cheeseburger/boot/boot-H131.img`。

### H131 结果：union 生效，ObjC 恢复，停点变成 SIGTRAP（2026-11-07）

`h131-log-20261107-023749.txt`。**注意 header `uptime_s: 317`**：317 s 之后的条目是
上一次启动残留的 msgbuf 尾巴（`slots_written=6`，delta 只保留尾部），不能算进本次。

按时间戳过滤后的干净窗口（≤317 s）：

| 指标 | H130 | **H131** |
| --- | --- | --- |
| `libobjc-trampolines` abort | 62 | **0** |
| SpringBoard 退出 | 16，全是 `ns=8`（ObjC） | 13，全是 `ns=2 sig=5` |
| liveactivitiesd | `ns=2 sig=5` | 仍 `ns=2 sig=5` |
| PerfPowerService | `ns=2 sig=6` | 仍 `ns=2 sig=6` |

日志里 323/328/330 s 那 3 条 trampolines 是 **H130 残留**，不是本次启动。
即 `/usr/lib` 的 cryptex union 生效，`libobjc-trampolines.dylib` 能加载，
**ObjC 运行时这一层已经过去**。

新停点：SpringBoard 死于 **SIGTRAP**（`status=0x5`、`ns=2`=`OS_REASON_SIGNAL`），
payload 里的 "exc handler" 来自 `bsd/kern/kern_sig.c:1813`
`build_signal_reason(signum, "exc handler")`，由 `bsd/uxkern/ux_exception.c:180`
的 `threadsignal(thread, ux_signal, code, TRUE)` 触发：某个进程执行了 `BRK`
（`EXC_BREAKPOINT`），典型是 libdispatch 的 `_dispatch_assert_queue_fail`、
XPC 的 `xpc_api_misuse` 或 dyld 的 `halt()`。

### H132：记录 Mach 异常与 union 状态（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzz-h132-trap-diag.patch`：

1. `handle_ux_exception()` 增加一行
   `NATIVE_TRAP: pid=… comm=… exc=… code=… sub=… sig=…`；对
   `EXC_BREAKPOINT`，`sub` 就是触发 PC，可按 dyld 共享缓存反查所属镜像；
2. `native_cryptex_usrlib_prepare()` 把结果写进 `native_boot_flags`：
   `0x2000` 挂载成功、`0x4000` 挂载后能看到 trampolines、`0x8000` 失败
   （`bits 16-23` = errno）。这样即使早期日志被 delta 截断，
   每条 `NATIVE_IRQ … flags=…` 仍带着证据（预期 `flags=60af`）。

```text
H132 kernel:  a0c1744ff12c81d4bcd07ad7be19f44cbf0598073cdbe55021a7376b5234b19e
H132 payload: 94d8900a6a0e90e9d530014c7e12b75eab315c0d825bdc4b8bc9f126fd1ac6fa
H132 boot:    a861d43c794af7c5938862b0171232955d61785f09f9c87d94bee231ccbd14ee
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H132.img`（已核对）、
Mac `~/h103/boot-H132.img`、仓库 `out/cheeseburger/boot/boot-H132.img`。

判读：`flags=60af` 确认 union；`NATIVE_TRAP … sub=0x…` 的镜像归属决定下一步
（SpringBoard 自身断言 / libdispatch / XPC / dyld）。

### H132 结果：SpringBoard 固定在同一个 PC 上 BRK（2026-11-07）

`h132-log-20261107-025234.txt`。union 的硬证据在每条 IRQ 里：

```text
NATIVE_IRQ: … flags=60af      ← 0x2000 挂载成功 + 0x4000 文件可见
NATIVE_FRAME: event=1 flags=600f client=0 xfer=0 frames=0
```

`NATIVE_TRAP` 是 H132 独有符号，29 条全部属于本次启动，按地址只有两种：

```text
NATIVE_TRAP: pid=… comm=SpringBoard     exc=6 code=0x1 sub=0x1aa1b32ec sig=5  （14 次同一地址）
NATIVE_TRAP: pid=… comm=liveactivitiesd exc=6 code=0x1 sub=0x1cc6ca4f8 sig=5  （15 次同一地址）
```

`exc=6` = `EXC_BREAKPOINT`，`code=0x1` = `EXC_ARM_BREAKPOINT`，而
`osfmk/arm64/sleh.c:1241` 用 `get_saved_state_pc(state)` 填 `codes[1]`，
所以 `sub` 就是触发 PC。每次运行都落在同一地址 → 确定性断言（`brk #1`），
不是随机内存错误。日志里同时间戳的 `libobjc-trampolines` 条目是上一轮残留：
H132 的干净窗口里 ObjC 已正常。

### H133：报出异常地址所属镜像（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzz-h133-trap-image.patch`：

- `handle_ux_exception()` 在 `exception == EXC_BREAKPOINT` 时调用
  `native_report_trap_image(p, subcode)`；
- 新函数从 `task_get_all_image_info_addr()` 取 dyld 的
  `dyld_all_image_infos`（前三个字段 version/count/infoArray 自 iOS 4 稳定），
  `copyin` 遍历每项 `{imageLoadAddress, imageFilePath, modDate}`，
  取 `loadAddress <= addr` 中最大者，打印：

```text
NATIVE_TRAP_IMAGE: pid=… comm=… addr=0x… base=0x… off=0x… <path>
```

失败分支分别打印 `no-dyld-info` / `no-image-array` / `no-match`，纯只读，
不改变任何行为。拿到 `<path>`+`off` 后即可定位到框架与函数。

```text
H133 kernel:  f26bd9b8f4ac83adbcef47729ae278cba192972746bbdaf9360b259bd855e421
H133 payload: 0f18c022e4d9876e889b28d6ee514ea42557ef9630c0a9aa4bbb3d64761ffae2
H133 boot:    44b356bf25e8f15f457ec9b993f857c82c51601e7646ef4e6380e4566b0ceebb
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H133.img`（已核对）、
Mac `~/h103/boot-H133.img`、仓库 `out/cheeseburger/boot/boot-H133.img`。

### H133 结果：镜像查找执行成功但全部 no-match（2026-11-07）

`h133-log-20261107-030945.txt`：

```text
NATIVE_TRAP_IMAGE: pid=26 comm=SpringBoard     addr=0x1bd14b2ec no-match count=1235
NATIVE_TRAP_IMAGE: pid=91 comm=liveactivitiesd addr=0x1df6624f8 no-match count=413
```

`count` 分别是 1235 / 413，都是合理镜像数 → `dyld_all_image_infos` 的头字段读对了；
但 1235 条里没有一条 `imageLoadAddress <= addr`。同一次启动内 PC 固定
（SpringBoard 14 次全在 `0x1bd14b2ec`），跨启动不同（H132 是 `0x1aa1b32ec`），
说明 ASLR 开启，必须靠镜像归属定位。

两种可能待区分：数组指针读错（每行都是垃圾值），或地址确实落在匿名映射
（objc trampoline RWX 页、JIT、cache 头区域）。

### H134：让镜像列表自证（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzz-h134-image-attest.patch`：`native_report_trap_image()`
追加 `version`、成功 `copyin` 的行数、`min_base`/`max_base`，并在无匹配时打印最近
的两个“低于 addr”候选和一个“高于 addr”候选：

```text
NATIVE_TRAP_IMAGE: pid=… addr=0x… version=… rows=…/… min=0x… max=0x…
NATIVE_TRAP_IMAGE_ROW: pid=… base=0x… delta=0x… above=0/1 <path>
```

- `rows` 正常且 `min/max` 是合理地址、addr 仍在区间外 → PC 在匿名映射，
  下一步打印 `lr`/`sp` 反推调用者；
- `rows` 为 0 或 `min/max` 是垃圾 → 结构偏移不对，按样本修正。

```text
H134 kernel:  5b9a7017c32d1bfe70dc88c6d8f0c39c01f6082b46d929f55b550d5011dc9ecf
H134 payload: 019281a8fe6e90a5a5812a42e519f987af03eb4aefc7e703b3f6018ca32ace73
H134 boot:    40df985f7fc7921082616f70ae4bd3b59bc3afda9c2033dd3d0db1d6e7910da7
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H134.img`（已核对）、
Mac `~/h103/boot-H134.img`、仓库 `out/cheeseburger/boot/boot-H134.img`。

### H134 结果：读到的是代码，偏移错了（2026-11-07）

`h134-log-20261107-032226.txt`：

```text
NATIVE_TRAP_IMAGE: pid=26 comm=SpringBoard addr=0x1b001b2ec version=17 rows=1235/1235
                   min=0xd65f03c0 max=0xfd46bd0090000288
```

`version=17`、`rows=1235/1235`、`count=1235` 都正常，说明 `dyld_all_image_infos`
的地址与头字段是对的；但 `min=0xd65f03c0` 正是 ARM64 的 `ret` 指令，
`max=0xfd46bd0090000288` 是两条相邻指令（`adrp` + `ldr d0`）被当成一个 64 位
指针读出。

原因：`version`/`infoArrayCount` 各 4 字节，`infoArray` 在 **+8**；H133/H134 写成了
`2 * sizeof(user_addr_t)` = +16，取到的是 `notification`（`dyld_image_notifier`
函数指针），于是按 24 字节步长读出来全是指令。

### H135：修正 infoArray 偏移（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzzz-h135-image-offset.patch`：

```c
copyin((user_addr_t)infos + 2 * sizeof(uint32_t), &array, sizeof(array))
```

其余诊断（`version/rows/min/max`、`NATIVE_TRAP_IMAGE_ROW`）保留。
预期 `min` 回到 `0x100000000` 级别、`max` 落在共享缓存区域，并直接打印出
SpringBoard / liveactivitiesd 那个 PC 所属的框架与 `off`。

```text
H135 kernel:  a652405b14605ba3a6261f218dd6f41e5e9517cb088dcda54926523c537228d6
H135 payload: 169689228ab9efb9780726cff43b20c4cfcbbe0953abbab7a7ed70bf2cf00bc0
H135 boot:    8e8fdec88adc714a83d03ab26e67a7ae59ffcc55c810870a6ad77dbe4c711ffb
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H135.img`（已核对）、
Mac `~/h103/boot-H135.img`、仓库 `out/cheeseburger/boot/boot-H135.img`。

### H135 结果：锁定到具体框架与偏移（2026-11-07）

`h135-log-20261107-033238.txt`：

```text
SpringBoard     addr=0x1a2bff2ec base=0x1a2be1000 off=0x1e2ec
                /System/Library/PrivateFrameworks/FrontBoardServices.framework/FrontBoardServices
liveactivitiesd addr=0x1c51164f8 base=0x1c50f9000 off=0x1d4f8
                /System/Library/PrivateFrameworks/SessionSyncEngine.framework/SessionSyncEngine
```

`min=0x100e1d000`、`max=0x22cb73000` 说明镜像数组这次读对了。
两个偏移都落在各自镜像 `__TEXT` 约 120 KB 处，位置很靠前，更像构造函数 /
`+load` / 静态初始化期间的断言。两个框架都只在 dyld 共享缓存里，OS 卷上没有实体文件。

### H136：抓 BRK 寄存器并读出断言字符串（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzzzz-h136-brk-strings.patch`：

1. `osfmk/arm64/sleh.c`：`ESR_EC_BRK_AARCH64` 的用户分支先
   `native_record_user_brk(state)`，把 `pc/lr/x0..x7` 存进全局并打印
   `NATIVE_BRK:`；`native_report` 侧用 `task` 指针与 `pc` 双重校验归属。
2. `bsd/uxkern/ux_exception.c`：`NATIVE_TRAP` 之后对这些寄存器里落在用户地址
   范围的指针做 `copyin`（160 字节上限、最多 3 个、仅打印可打印串），
   输出 `NATIVE_TRAP_STR: pid=… comm=… xN="…"`。

AArch64 的 `brk #1` 之前通常已经把断言文本放进 `x0/x1`（Swift `fatalError`、
libdispatch `BUG IN CLIENT`、dyld `halt` 都是这个模式），所以这一步预期直接
拿到断言原文。

```text
H136 kernel:  282f91894fb7527503d1a9df0783f9a8c892e291baaa57675d44fcb2a8fc5a39
H136 payload: a978eb25e463bc3820ba3d0513b04eac37e334ebac3274e541c7922768fecd74
H136 boot:    5f826d78860f7de30420af63139f993fffe74e2b10b77f7ec1dc4ed896da59e8
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H136.img`（已核对）、
Mac `~/h103/boot-H136.img`、仓库 `out/cheeseburger/boot/boot-H136.img`。

### H137：trust cache 初始化不再 panic（2026-11-07）

H136 上机时撞到启动 panic（屏幕照片）：

```text
panic(cpu 0 caller 0xfffffff007a41d94): NATIVE_TRUSTCACHE: img4=0 amfi=0 @kern_trustcache.c:477
```

（照片里读成 `len=0`，实际是 `img4=0`。）

调用链：`osfmk/kern/startup.c:762` → `trust_cache_runtime_init()` →
`bsd/kern/kern_trustcache.c:475`（`PMAP_CS_PPL_MONITOR` 关掉时的 `#else` 分支）。
`amfi` 由 AMFI 内建 kext 在 `mpo_policy_init` 填充，**先后顺序取决于预链接内核里
kext 的启动顺序**，所以这是启动期竞态：

- H135 正常：`calling mpo_policy_init for AMFI` → `Security policy loaded: AMFI`
  → `NATIVE_TRUSTCACHE_LOAD_START … amfi=0xfffffff00bcfc690 version=3`；
- 这次：`calling mpo_policy_init for vnguard` 之后立刻 panic，AMFI 尚未注册。

同一 panic 在 2026-10-23 出现过（当时是关掉 `CONFIG_XNU_TRUST_CACHE_RUNTIME` 绕过的）。
H136 只改了 `sleh.c` 与 `ux_exception.c`，与本路径无关，属于**概率性启动失败**。

而且原注释写的是“不要初始化锁，让查询干净地失败”，代码却直接 panic；后半段的
`trust_cache_ready` 保护已经写好，所以去掉 panic 是安全的。

`patches/xnu/zzzzzzzzzzzzzzzzzzzzz-h137-trustcache-race.patch`：

```c
	if (img4if == NULL || amfi == NULL) {
		printf("NATIVE_TRUSTCACHE: not ready img4=%p amfi=%p\n", img4if, amfi);
		return;      /* trust_cache_ready 保持 false，所有查询提前返回 */
	}
```

AMFI 正常注册的启动行为不变；撞上竞态时只是这一轮不加载静态 trust cache
（本端口的 AMFI/签名路径本来就是旁路的）。

```text
H137 kernel:  8e7a4bc630dd1cc37ee793fa9abc6f6467c621ef9eba00812307a203f454b499
H137 payload: 70f8aa9f683de19956bdfafcde44d2337630256db6ffe2d29c0a110727ba5a4d
H137 boot:    b5357eb00dab591ad3e3d4557041fb0e3ff550df4954de2d110cdc7ca84ea3f7
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H137.img`（已核对）、
Mac `~/h103/boot-H137.img`、仓库 `out/cheeseburger/boot/boot-H137.img`。

### H136 结果：SpringBoard 断言的是“找不到 CADisplay”（2026-11-07）

`h137-log-20261107-035921.txt`（H136 内核 + H137 trust cache 修复）：

```text
NATIVE_BRK: pc=0x1a34032ec lr=0x1a34032ec x0=… x1=0x8000100 …
NATIVE_TRAP_IMAGE_ROW: base=0x1a33e5000 delta=0x1e2ec FrontBoardServices
NATIVE_TRAP_STR: pid=26 comm=SpringBoard x0="failed to find the main CADisplay"
```

断言原文拿到了：**“failed to find the main CADisplay”**。liveactivitiesd
（`SessionSyncEngine + 0x1d4f8`）的寄存器里没有可打印串，属次级问题。
H137 的 trust cache 修复也生效，日志里没有 `NATIVE_TRUSTCACHE` panic。

当前完整链条：

```text
IOMobileFramebufferLegacy 服务（已注册）
   → backboardd 不取用 → 没有 display
   → 没有 CADisplay 发布给 CoreAnimation
   → SpringBoard: "failed to find the main CADisplay" → brk #1 → SIGTRAP 循环
```

显示驱动本身是起来的：

```text
NATIVE_LEGACY: nub attach=1 start=1
IOMobileFramebufferLegacy::start: provider was not AppleARMIODevice.（基类返回 false）
NATIVE_LEGACY: startHardware gop=1 … valid=1
NATIVE_LEGACY: registerService object=0xfffffff5f5be9000
NATIVE_LEGACY: base start ok primary=1 mapping=…
```

但 backboardd 的 IOKit 调用只有 `aop-smart-cover`、空字典、`IOPlatformExpertDevice`
和 `IOPMrootDomain`，从未出现 `IOMobile*`；其中 `cls=- d=- ok=0` 的空字典匹配
因为 trace 只记录三个键而无法辨认。

### H138：证明服务是否可被匹配 + 打印完整匹配字典（2026-11-07）

1. `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：心跳里一次性探测

```text
NATIVE_IOMFB_PROBE: name=IOMobileFramebuffer match=1 service=0x… class=…
NATIVE_IOMFB_PROBE: name=IOMobileFramebufferLegacy match=… service=… class=…
```

   找到说明注册表正常、问题在 backboardd 侧；找不到说明服务没有以可匹配的
   类/属性发布，需要改发布方式。

2. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzz-h138-iokit-dict.patch`：
   `native_match_trace()` 对 `backboardd` / `SpringBoard` 打印完整匹配字典
   （最多 6 个键值）：`NATIVE_IOKIT_DICT: comm=… count=… key=value`。

```text
H138 kernel:  92a8db9e8464389f91c0bc6a18c786fa9b78a5bb7f0adb91ce14531532acc9fc
H138 payload: f12bdaed6e967af9bb39c5d3e26c1ddecb34c38f1cdbf06db3b267920c0cbe8c
H138 boot:    a6c86d30881e3ba42686e2cb41ee28521e2d43f8f49ea7961110058a7969f9eb
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H138.img`（已核对）、
Mac `~/h103/boot-H138.img`、仓库 `out/cheeseburger/boot/boot-H138.img`。

### H138 结果：backboardd 只注册服务通知，从不查显示（2026-11-07）

`h138-log-20261107-041242.txt`。完整匹配字典终于可见（`IOServiceNotificationUser`
说明这些是**通知注册**而不是一次性查询）：

```text
NATIVE_IOKIT_DICT: comm=backboardd count=2 IOPropertyMatch=(non-string)
NATIVE_IOKIT_DICT: comm=backboardd count=2 IONameMatch=aop-smart-cover
NATIVE_IOKIT_DICT: comm=backboardd count=2 IOProviderClass=IOPlatformExpertDevice
NATIVE_IOKIT_DICT: comm=backboardd count=2 IOProviderClass=IOAccessoryManager
```

仍然没有一次 `IOMobileFramebuffer`；`IOPropertyMatch` 的嵌套字典因只打印一层而未展开。

`NATIVE_IOMFB_PROBE` 一行未出现：代码确实编进内核（`strings kernel-H138.macho`
可查到），同一函数的 120 秒强制 dump 也正常执行，说明探针在 ~117 秒触发时正好
落在 dyld 缓存批量打开（115–121 s）的刷屏区间，被持久日志“只保留 delta 尾部”裁掉。

### H139：探针结论进 boot flags + 展开嵌套字典（2026-11-07）

1. `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：探针改为每 60 秒一次，并把结论写进
   `native_boot_flags`（每条 `NATIVE_IRQ … flags=` 都会打印，不会被裁掉）：

   - `0x20000` = `serviceMatching("IOMobileFramebuffer")` 能找到服务
   - `0x40000` = `serviceMatching("IOMobileFramebufferLegacy")` 能找到服务

2. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzz-h139-nested-dict.patch`：对
   `backboardd`/`SpringBoard` 的匹配字典，值是 `OSDictionary` 时再展开一层
   （最多 3 项），打印 `key.{inner}=value`。

```text
H139 kernel:  742e2b34b3b8d52a3403ddf6fa293e9479844ba3fa3dee09dda5bebf960129e2
H139 payload: 86f1905eb099a48f586087f97c0579e02f5a202d0b99dc44aefaaa3fd01fc7f2
H139 boot:    df24845234f5554dc07082af5efc8c7adb133c036566b6bd08531eb9b5cc0da5
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H139.img`（已核对）、
Mac `~/h103/boot-H139.img`、仓库 `out/cheeseburger/boot/boot-H139.img`。

判读：`NATIVE_IRQ … flags=` 里是否出现 `2`/`4` 位决定服务是否可匹配；
`NATIVE_IOKIT_DICT … IOPropertyMatch.{…}` 决定 backboardd 在等什么。

### H139 结果：探针 service=0，backboardd 在等 `backlight-control`（2026-11-07）

`h139-log-20261107-042511.txt`：

```text
NATIVE_IOMFB_PROBE: name=IOMobileFramebuffer       match=1 service=0 class=- flags=6000
NATIVE_IOMFB_PROBE: name=IOMobileFramebufferLegacy match=1 service=0 class=- flags=6000
NATIVE_IOKIT_DICT: comm=backboardd IOPropertyMatch.{backlight-control}=(non-string)
NATIVE_IOKIT_DICT: comm=backboardd IONameMatch=aop-smart-cover
NATIVE_IOKIT_DICT: comm=backboardd IOProviderClass=IOPlatformExpertDevice
NATIVE_IOKIT_DICT: comm=backboardd IOProviderClass=IOAccessoryManager
```

- 探针这次打出来了（周期性 + `flags=6000` 持久化有效），但 `service=0`；
- 注意 `IOService::serviceMatching(name)` 在 XNU 里是把 **`IOProviderClass = name`**
  写进字典（`iokit/Kernel/IOService.cpp:6704`），所以 `service=0` 不能直接等同于
  “服务不存在”，需要对照组；
- 真正的新线索是 `IOPropertyMatch.{backlight-control}`：backboardd 注册通知在等
  一个带 `backlight-control` 属性的服务。我们的 Legacy display 没发布它，
  通知永不触发，显示初始化也就一直没开始——这正好解释“从不查
  IOMobileFramebuffer”。

### H140：发布 backlight-control + 对照组 + 值类型（2026-11-07）

1. `drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp` 的 `registerService()`
   在 `IOService::registerService()` 之前 `setProperty("backlight-control",
   kOSBooleanTrue)`，让 backboardd 的 `IOPropertyMatch` 通知能够命中；
2. 探针增加对照组 `"IOPlatformExpertDevice"`（backboardd 自己匹配 ok=1 的对象），
   结果置 `native_boot_flags` 的 `0x80000`：
   - 对照组命中、`IOMobileFramebuffer` 不命中 → 探针语义有效；
   - 两者都不命中 → `serviceMatching` 语义不是“按类名找服务”，探针结论作废；
3. IOKit 字典打印追加值的类名（`OSBoolean`/`OSNumber`/`OSData`），
   便于在类型不对时立即改用正确类型。

判读：backboardd 的 `backlight-control` 通知触发后，应出现对显示服务的
`op=match comm=backboardd …` 或 `open`（`NATIVE_LEGACY: client enter`），
`NATIVE_FRAME … client=` 变为非 0。

### H140：发布 backlight-control、对照探针与值类型（2026-11-07）

1. `drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp` 的 `registerService()`
   在 `IOService::registerService()` 之前发布
   `setProperty("backlight-control", kOSBooleanTrue)`，让 backboardd 的
   `IOPropertyMatch.{backlight-control}` 通知能够命中；
2. `drivers/NativeUfsProbe/NativeUfsProbe.cpp` 探针增加对照组
   `"IOPlatformExpertDevice"`（backboardd 自己匹配 ok=1 的对象），结果置
   `native_boot_flags` 的 `0x80000`；
3. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzz-h140-typed-dict.patch`：字典打印追加
   值的类名（`OSBoolean`/`OSNumber`/`OSData`），类型不对时可立即修正。

注意：修改 `NativeLegacyDisplay.cpp` 后必须重新生成 owned Legacy 归档
（`scripts/build-op5-legacy-display.py`），否则内核链接会以
`Rebuild the owned Legacy archive after changing …` 拒绝。

```text
H140 kernel:  ea9c82af4acce862568b9eb68e045d1e277a998de1b6ec7908288b4ace2e91be
H140 payload: 53d9a719d6016341b0d64be6cab3f020f07515f114fffd1aaf949b5980b21b45
H140 boot:    dcf631ed37e44a6712cbbe2e1ea6c0a08a4c3932944904f70456d1149aeb5758
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H140.img`（已核对）、
Mac `~/h103/boot-H140.img`、仓库 `out/cheeseburger/boot/boot-H140.img`。

### H140 结果：探针有效，但显示服务按类名查不到（2026-11-07）

`h140-log-20261107-102006.txt`：

```text
NATIVE_IOMFB_PROBE: name=IOMobileFramebuffer        service=0            flags=86000
NATIVE_IOMFB_PROBE: name=IOMobileFramebufferLegacy  service=0            flags=86000
NATIVE_IOMFB_PROBE: name=IOPlatformExpertDevice     service=0xfffffff8f9080e80 class=IOPlatformExpertDevice
```

对照组命中（`flags & 0x80000`），说明探针有效。`IOService::matchInternal`
（`iokit/Kernel/IOService.cpp`）对 `serviceMatching()` 写入的 `IOProviderClass`
用 `metaCast(str)` 比较，**支持子类**；因此“按类名查不到”是一个真结论：
`NativeLegacyDisplay` 实例在注册表里无法用 `IOMobileFramebuffer*` 命中。

驱动侧日志显示它确实注册了两次（52 s、57 s 各一套 probe → start → reg=1）：

```text
NATIVE_LEGACY: registerService object=0xfffffff5f5be9000
NATIVE_LEGACY: phase=4 dt=1 probe=1 attach=1 start=1 reg=1
```

`backlight-control` 发布后 backboardd 没有新动作（`NATIVE_FRAME … client=0`）。

### H141：显示驱动自证注册与类匹配（2026-11-07）

`NativeLegacyDisplay::registerService()` 在 `IOService::registerService()` 之后：

```text
NATIVE_LEGACY: self inactive=… ioclass=… provider=…
NATIVE_LEGACY: self-match name=IOMobileFramebuffer       -> %p same=…
NATIVE_LEGACY: self-match name=IOMobileFramebufferLegacy -> %p same=…
NATIVE_LEGACY: self-match name=NativeLegacyDisplay       -> %p same=…
```

UFS 探针增加具体类名 `"NativeLegacyDisplay"`（置 `0x100000`）。
判读：三者都查不到 → 没真正进注册表；只有具体类名能查到 → 归档类
`OSMetaClass` 名字/层级问题；都能查到而 UFS 模块看不到 → 跨模块可见性。

（另注：`IOService` 在这版 XNU 没有 `isRegistered()`，改用 `isInactive()`。）

```text
H141 kernel:  edc8e2cfae0f53f1271a33afd59ded72911533996d00d40e821dd097042e2940
H141 payload: fe7342fd41af73d8298f3e118a491d6a2a64c43b8047dc9f70b73bf4348fa94e
H141 boot:    94faa47ef6bc9281ed93d66ca575fa02920011b9065fd33844f1f6b0c3ae593c
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H141.img`（已核对）、
Mac `~/h103/boot-H141.img`、仓库 `out/cheeseburger/boot/boot-H141.img`。

### H142：把显示改成 personality 驱动（2026-11-07，依据参考项目与 XNU）

#### 根因（XNU 源码 + 参考项目一致）

`iokit/Kernel/IOService.cpp`：

```c
IOService::getMatchingServices( matching )   // 用户态 IOServiceGetMatchingServices
{ iter = copyExistingServices( matching, kIOServiceMatchedState ); }

IOService::copyMatchingService( matching )   // 内核探针
{ service = copyExistingServices( matching, kIOServiceMatchedState, kIONotifyOnce ); }
```

两者都只返回 **`kIOServiceMatchedState`** 的服务；该状态只有在服务被**驱动
personality 匹配并启动**时才会置上（`registerService()` 末尾是
`startMatching(options)`）。H103 起的 `NativeLegacyDisplay` 是
`LegacyDisplayProbe` 里 `new`/手工 `attach`+`start`+`registerService` 出来的：
**registered 但从未 matched**，所以内核探针和 backboardd 都看不见它。
H141 的 `metaCast` 自检本来就通过（`init=1 … parent=1`），不是类层级问题。

参考项目用的是正确姿势：

- **ios-sweet**（`NOTES.md:396/408/428`、`xnu/patches/0046-sweet-iosurface-iomfb.patch`）：
  逆向确认“框架不匹配 AppleCLCD 这个名字，任何已注册的 IOMobileFramebuffer
  子类都行”；`CAWindowServer _detectDisplays` 只认
  `IOMobileFramebufferCreateDisplayList()`；显示数量 = `/arm-io` 下
  `device_type` 以 `display-subsystem` 开头的子节点数；显示以 KernelConfigTable
  personality 发布（`IOClass=AppleCLCD; IOProviderClass=IOPlatformDevice;
  IONameMatch='sweet,display'`），nub 由平台专家 `createNubs()` 生成。
- **sagit-ios-port**：`QcomDisplay : IOMobileFramebufferLegacy` 同样是 personality
  驱动，`start()` 里 `registerService()`。
- XNU 自己的 `IODTPlatformExpert::createNubs()` 结尾就是 `nub->registerService()`。

#### 改动

1. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzz-h142-display-personality.patch`：新增
   personality
   `IOClass=NativeLegacyDisplay; IOProviderClass=IOPlatformDevice;
   IONameMatch='NativeGOPFramebuffer'; IOProbeScore=1000`。
2. `LegacyDisplayProbe`：不再手工创建/启动显示对象；保留 nub（GOP 内存段、
   `IOFBDependentID/Index`、`/arm-io` 的 `device_type=display-subsystem` 节点），
   改为 `nub->registerService()` 让 IOKit 匹配并实例化。
3. `NativeLegacyDisplay::probe()` 重写：对有设备内存的 provider 直接返回 `this`，
   避免继承来的 Apple 检查否决。
4. 移除已不再使用的 `activeLegacyDisplay`。

预期：`NATIVE_IOMFB_PROBE` 的 `IOMobileFramebuffer`/`NativeLegacyDisplay` 非 0；
backboardd 匹配到并 `open` 显示服务，`NATIVE_FRAME … client=` 非 0。

```text
H142 kernel:  3e14159a73e26e5d2c393e3926cfe35b7d5589f422dab33b09e74af3acc14b5c
H142 payload: 123cbd3d427d959318455e6c81d62e1c2362bd5c42bc7a9721c867f2dfc70596
H142 boot:    a5baef9d07af809994f0514241aa295f78b9b130a09876b60821ae0e8668dade
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H142.img`（已核对）、
Mac `~/h103/boot-H142.img`、仓库 `out/cheeseburger/boot/boot-H142.img`。

### H142 结果：无法判定，早期日志仍是上一轮残留（2026-11-07）

`h142-log-20261107-111107.txt` 里所有 `NATIVE_LEGACY` 行仍是旧路径痕迹
（`nub attach=1 start=1`、`phase=4 … attach=1 start=1 reg=1`），时间戳与之前几轮
逐微秒相同，属于 msgbuf 尾巴；H142 新增的 `nub-registered` 一行都没有。本轮新鲜
证据只有每 60 秒的探针：166 s / 227 s 仍是

```text
IOMobileFramebuffer=0  IOMobileFramebufferLegacy=0  NativeLegacyDisplay=0  IOPlatformExpertDevice=✓
```

因此无法判断这次显示模块是否运行、nub 是否注册、personality 是否匹配。

### H143：用 boot flags 给显示链路打点（2026-11-07）

显示模块新增 4 个位（`NATIVE_IRQ … flags=` 不会丢）：

| 位 | 位置 | 含义 |
| --- | --- | --- |
| `0x1000000` | `native_legacy_display_late_probe()` 入口 | late probe 跑了 |
| `0x2000000` | `nub->registerService()` 之后 | nub 已注册（触发匹配） |
| `0x4000000` | `NativeLegacyDisplay::start()` 入口 | personality 匹配并实例化 |
| `0x8000000` | `startDisplay()` 内 `IOService::registerService()` 之后 | 显示服务注册完成 |

判读：只有 `0x1000000` → 前置条件没满足；`0x1000000|0x2000000` 无 `0x4000000`
→ personality 没匹配；有 `0x4000000` 无 `0x8000000` → `startDisplay` 提前返回；
四个都有而探针仍为 0 → 匹配/注册链路本身有问题。

```text
H143 kernel:  f994e5bace1211be9a9fa2da80f449d214c2030cd2b2801bb4a61c0afa816a53
H143 payload: f2913aa21b1f9d7eedcf71841592f0af5fc9ba4f09460af6e1d2f5b648619fb4
H143 boot:    49c5d6669b29f3502e6caccbbc5147ae5d7a173f219426a746bbffecc079e048
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H143.img`（已核对）、
Mac `~/h103/boot-H143.img`、仓库 `out/cheeseburger/boot/boot-H143.img`。

### H143 结果：late probe 进了，但没到注册 nub（2026-11-07）

`h143-log-20261107-112526.txt`：`flags=10860af`（537 s、601 s 一致），解码：

| 位 | 状态 |
| --- | --- |
| `0x01000000` late probe 入口 | ✅ |
| `0x0002000000` nub 注册 | ❌ |
| `0x04000000` personality 实例化 | ❌ |
| `0x08000000` 显示服务注册 | ❌ |

显示模块确实运行了，但卡在 late probe 内部、尚未走到 `nub->registerService()`。

### H144：给 late probe 的三个前置条件打点（2026-11-07）

| 位 | 位置 | 含义 |
| --- | --- | --- |
| `0x10000000` | 早期 probe 暂存 `pendingLegacyDisplay` | 显示对象已暂存 |
| `0x20000000` | late probe 取到非空 `display` | 通过 pending 门槛 |
| `0x40000000` | `native_legacy_surface_found` | IOSurface 找到 |
| `0x80000000` | `PE_current_console` 校验通过、进入 nub 分支 | GOP 参数合法 |

判读：缺 `0x10000000` → 早期 probe 没存对象；有 `0x10000000` 无 `0x20000000`
→ late probe 先到或被清空；有 `0x20000000` 无 `0x40000000` → IOSurface 没等到；
有 `0x40000000` 无 `0x80000000` → GOP 参数校验没过。

```text
H144 kernel:  1bea41cd1b2947a8bc860010917b46a0b90700c3a44cc0061f769d8a9798c9e6
H144 payload: 9c1f745807c88724bf266203eb7a4750cdc6089d3d59b6f0ccc8dea99d05ebd6
H144 boot:    a3c11ee6cc04202e0b7d9d8b86b89b15b4282d6a2ebaf474261bc17ad08ad007
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H144.img`（已核对）、
Mac `~/h103/boot-H144.img`、仓库 `out/cheeseburger/boot/boot-H144.img`。

### H144 结果：卡在 IOSurface 前置条件（2026-11-07）

`h144-log-20261107-113810.txt`：`flags=310860af`，解码后

| 位 | 状态 |
| --- | --- |
| `0x10000000` 早期 probe 暂存显示对象 | ✅ |
| `0x20000000` late probe 取到该对象 | ✅ |
| `0x01000000` late probe 入口 | ✅ |
| `0x40000000` IOSurface 找到 | ❌ |
| `0x80000000` GOP 参数通过 | ❌ |

即 late probe 卡在：

```c
native_legacy_surface_status = OSKextLoadKextWithIdentifier("com.apple.iokit.IOSurface");
surface = waitForMatchingService(nameMatching("IOCoreSurfaceRoot"), 5 s);
native_legacy_surface_found = surface != nullptr;
```

旧日志里的 `IOSurface status=0 found=1` 是更早启动的残留。

### H145：把 IOSurface 这一步的三个结果分开打点（2026-11-07）

| 位 | 含义 |
| --- | --- |
| `0x00010000` | IOSurface kext 加载返回 0 |
| `0x00200000` | `IOCoreSurfaceRoot` 5 秒内匹配到 |
| `0x00400000` | `PE_current_console(&video)` 成功 |

判读：缺 `0x10000` → kext 没加载成功；有 `0x10000` 缺 `0x200000` → 5 秒内没匹配到
（时序）；两者都有缺 `0x400000` → 控制台参数取不到。

```text
H145 kernel:  6ef804f591997f7f14aa70ef56d87fad7811fad3f4deb2a226052b97db46281e
H145 payload: b97c766fa1d75a20d4b232a990b86483ddb349376ce93c55c01943edbf242b33
H145 boot:    fb9ee488756eab69f7b982e294690b7b5156f5c9784b705f6e1f5322430d1e99
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H145.img`（已核对）、
Mac `~/h103/boot-H145.img`、仓库 `out/cheeseburger/boot/boot-H145.img`。

### H145 结果：IOCoreSurfaceRoot 没在 5 秒内出现（2026-11-07）

`h145-log-20261107-115324.txt`：`flags=314960af`，解码：

| 位 | 状态 |
| --- | --- |
| `0x00010000` IOSurface kext 加载返回 0 | ✅ |
| `0x00400000` `PE_current_console` 成功 | ✅ |
| `0x10000000 / 0x20000000 / 0x01000000` | ✅ |
| `0x00200000` `IOCoreSurfaceRoot` 匹配到 | ❌ |

即 `IOService::waitForMatchingService(nameMatching("IOCoreSurfaceRoot"), 5 s)`
没等到服务，整个 nub 分支被跳过，显示永远不发布。日志里
`IOSurfaceRoot::installMemoryRegions()` / `IOSurface status=0 found=1`（65.22 s）
与旧启动时间戳相同，是残留。

### H146：surface 等待重试 + 显示发布与 surface 解耦（2026-11-07）

参考 ios-sweet：主显示的枚举只看 `/arm-io` 的 `display-subsystem` 节点与
IOMobileFramebuffer 服务，**不依赖** IOSurface 是否就绪；surface 是 swap 期依赖。

1. `waitForMatchingService` 改为最多 4 次 × 5 秒（共 20 秒），每次失败打印
   `NATIVE_LEGACY: IOSurface wait attempt=N`；
2. 显示发布条件去掉 surface 要求，只保留 `consoleOk` + GOP 参数校验；
   未命中时置 `0x800000`，命中时仍置 `0x200000`/`0x40000000`。

预期：若 surface 只是来得晚，这次能等到；若始终没有，显示仍会通过
`nub->registerService()` 发布，`NATIVE_IOMFB_PROBE` 的 `IOMobileFramebuffer`
应变成非 0，backboardd 也就能开始匹配。

```text
H146 kernel:  c0c0b160c8e42e22d00d8b12f3bf25b0d547fc19ed13fa67ab4a13fa13f88496
H146 payload: ebcaabfc9bfef0e455606403f7b7bcba5934053fae06d0893474d26381baae37
H146 boot:    fa20cd0ea2562b0f8ee752acaee37f6c898ccf96917f4ca4063cda24b8c6f6ea
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H146.img`（已核对）、
Mac `~/h103/boot-H146.img`、仓库 `out/cheeseburger/boot/boot-H146.img`。

### H146 结果：surface 重试成功，但匹配阶段 panic（2026-11-07）

`h146-log-20261107-120817.txt`（panic 前的持久日志，`NATIVE_PANIC` 正常落盘）：

```text
NATIVE_LEGACY: IOSurface status=0 found=1                 ← 第 2 次重试等到了
NATIVE_LEGACY: nub attach=1 start=1
NATIVE_LEGACY: phase=4 dt=1 nub-registered name=NativeGOPFramebuffer
Waiting on <dict …IOProviderClass=IOMedia…UUID=0476…>
NATIVE_PANIC: flags=f3610000
```

`flags=f3610000`：surface 找到 ✅、GOP 有效 ✅、nub 已注册 ✅，但
`0x4000000`（personality 实例化）未置 —— panic 发生在
`registerService → startMatching` 过程中。

dSYM 反查 panic caller `0xfffffff007850640` →
`OSMetaClass::serializeClassDictionary()`。XNU 源码里这是 retail 内核的死路径：

```c
bool OSMetaClass::serialize(OSSerialize *s) const { panic("OSMetaClass::serialize(): Obsoleted"); }

bool IOKitDiagnostics::serialize(OSSerialize *s) const
{
	…
	OSMetaClass::serializeClassDictionary(dict);   // 唯一调用者
```

而 `IOKitDiagnostics` 在 `IOStartIOKit.cpp:121` 被挂成 **root 服务属性**
（`kIOKitDiagnosticsKey`），任何对 root/含该属性的对象序列化都会 panic。
此前不触发是因为 nub 从未注册、匹配机制没跑。

### H147：去掉这条 retail 死路径（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzz-h147-iokitdiag.patch`：在
`IOKitDiagnostics::serialize()` 中移除 `OSMetaClass::serializeClassDictionary(dict)`
调用，保留分配计数。只是不再输出类统计，不影响驱动行为。

```text
H147 kernel:  128453eec52fc869052d64613a0ec8efe5a2d09d3175612f2f8cb34e3ceca384
H147 payload: 0d5c0c1d1e2c34f497f56fccf636e7e2f522ca7ba5192df3e7ebebf2b13d242e
H147 boot:    040b8383f9aaf8e3b001fab6da42dd052c73cde88b4f365e070675d1ef0776c3
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H147.img`（已核对）、
Mac `~/h103/boot-H147.img`、仓库 `out/cheeseburger/boot/boot-H147.img`。

判读：`flags` 出现 `0x4000000`（personality 实例化）即通过匹配阶段；
`NATIVE_IOMFB_PROBE` 的 `IOMobileFramebuffer` 应为非 0。

### H147 结果：panic 仍在，且与 H146 完全同相（2026-11-07）

`h147-log-20261107-122243.txt`：

```text
[23.706216] NATIVE_LEGACY: phase=4 dt=1 nub-registered name=NativeGOPFramebuffer
[23.721046] NATIVE_PANIC: flags=f3610000
```

`flags=f3610000`：surface 找到、GOP 有效、nub 已注册，`0x4000000`（personality
实例化）仍未置，2 ms 后 panic。反汇编 H147 的 `kernel.macho` 确认
`IOKitDiagnostics::serialize` 已不再调用 `serializeClassDictionary`，因此还有
**另一条**序列化路径把 `OSMetaClass` 对象送进 `OSSerialize`，撞上
`panic("OSMetaClass::serialize(): Obsoleted")` 桩。屏幕上的 caller 地址不可信：
内核经 prelink，dSYM 与运行时布局不一致。

另记录一条同源现象：`IOCPUInterruptController: not registry member at
registerService()` —— 本端口本来就有服务因父链不在 IOService plane 而注册失败。

### H148：把 OSMetaClass::serialize 桩改为记录并跳过 + 构建标记（2026-11-07）

1. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzz-h148-meta-serialize.patch`：
   `OSMetaClass::serialize()` 不再 panic，改为最多 8 次
   `NATIVE_META: serialize skipped for <class>` 后返回 false，序列化继续；
2. `drivers/NativeUfsProbe`：`start()` 打印 `NATIVE_BUILD: H148`，此后每份日志
   都能自证内核版本（前几轮已两次被上一轮残留日志误导）。

```text
H148 kernel:  04a4136b16656907e06f75ba7b5e457bb87196cbdf374361ef140b716c687a17
H148 payload: 800158905c20fc24cb2419dd2a95f14222ce629be897050378619a9cadc98787
H148 boot:    9bdf16be199d36f1b110cc933e9756cdd3426a462ccf21d42dad9b951defda5f
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H148.img`（已核对）、
Mac `~/h103/boot-H148.img`、仓库 `out/cheeseburger/boot/boot-H148.img`。

判读：不再 panic；`NATIVE_META: serialize skipped for …` 指出被序列化的类；
`flags` 应出现 `0x4000000`；`NATIVE_IOMFB_PROBE` 的 `IOMobileFramebuffer` 应为非 0。

### H148 结果：序列化 panic 消失，改成 preemption 断言（2026-11-07）

`h148-log-20261107-123426.txt`：

```text
panic(cpu 0 caller 0xfffffff0079dec44):
  Attempt to take mutex 0xfffffff00762cc40 with preemption disabled (1) @lock_rtx.c:194
```

位置与 H147 相同（`IOCPUInterruptController: not registry member` →
`IOSurface wait attempt=1` → `nx_mount` → panic）。原因是我在 H148 里给
`OSMetaClass::serialize()` 加的 `printf`：该回调在 IOKit 注册表/匹配锁内、
**preemption 已禁用**，而 `printf` 会去取 msgbuf 的 mutex。

即：诊断代码又一次在错误上下文里做 I/O（与 H128 的教训同类）。

### H149：把这段日志延迟到线程上下文（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzz-h149-meta-deferred.patch`：

- `OSMetaClass::serialize()` 只做无锁写：
  `native_meta_serialize_count++`，首次记录 `native_meta_serialize_class`；
- `drivers/NativeUfsProbe`：心跳（线程上下文）检测计数变化后打印一次
  `NATIVE_META: serialize skipped n=… first=<class>`。

```text
H149 kernel:  b2958744e345c1a6841664728a2d57830dd82d202d7558ac6774e57067ca4309
H149 payload: 82ca9e3964996de1cd6bb875b1cb5d2cfadf1481ed0593f7b10d947468ed2260
H149 boot:    23e04aef97c96d6638b4803b6a464f09c4dfd5053fa107f8cb7066bfb4c118d2
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H149.img`（已核对）、
Mac `~/h103/boot-H149.img`、仓库 `out/cheeseburger/boot/boot-H149.img`。

### H149 结果：换成 trust cache 的 NULL 解引用（2026-11-07）

屏幕：

```text
NATIVE_TRUSTCACHE: not ready img4=0 amfi=0          ← H137 的早退生效
NATIVE_TRUSTCACHE_LOAD_START: rt=… amfi=0 version=0
panic(cpu 0 caller …): Kernel data abort. at pc 0x…739554
  esr: 0x96000005  far: 0x0000000000000118
```

`amfi=0` 又撞上启动期 kext 注册顺序竞态。H137 让 `trust_cache_runtime_init()`
早退是对的，但紧随其后的 `load_static_trust_cache()` 只判了
`trust_cache_rt`、没判 `amfi`：

```c
	if (amfi->TrustCache.version < 1) {   // amfi == NULL → NULL+0x118
```

`far=0x118` 正是 `offsetof(amfi->TrustCache.version)`。

### H150：给 load_static_trust_cache 补同样的保护（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h150-trustcache-null.patch`：

```c
	if (amfi == NULL || !trust_cache_ready) {
		printf("NATIVE_TRUSTCACHE: static cache skipped amfi=%p ready=%d\n",
		    amfi, trust_cache_ready ? 1 : 0);
		return;
	}
```

另外把 UFS 探针的构建标记更新为 `NATIVE_BUILD: H150`。

```text
H150 kernel:  030b4d0866498d2bb15a5ce85f9aca1f29837f37474ac518d201dc11d5bf5ab0
H150 payload: b1bcc321ccb3676153c2a0419820067ca8adeccc9fa5cf69e82ad1518b2f0a72
H150 boot:    aeb060190eb570a7d52e6b126067997c55447dfbcbd8149fc95faf6761ee4f54
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H150.img`（已核对）、
Mac `~/h103/boot-H150.img`、仓库 `out/cheeseburger/boot/boot-H150.img`。

### H150 结果：trust cache 修好，panic 前出现匹配线索（2026-11-07）

`h150-log-20261107-125331.txt`：

```text
[453.957369] NATIVE_LEGACY: phase=4 dt=1 nub-registered name=NativeGOPFramebuffer
[453.971373] Waiting on <dict …IOProviderClass=IOMedia…UUID=0476…>
[453.973189] Couldn't alloc class "AppleARMFabricTrace"
[453.973349] NATIVE_PANIC: flags=f3610000
```

- H150 生效：`trust cache` 的 NULL 解引用不再出现；
- panic 前多了一条明确线索：`Couldn't alloc class "AppleARMFabricTrace"`
  （`IOService.cpp:4045`，匹配循环里对缺失类的正常跳过）。我们把
  `IOPlatformDevice` nub 注册进服务平面后，IOKit 会拿**所有**
  `IOProviderClass=IOPlatformDevice` 的 personality（含 Apple 自己的
  AppleARMIODevice 家族）来试配，其中某个类的 `init()` 在拿到非 Apple 的
  nub 时崩掉；
- `flags=f3610000` 说明还没走到我们的 `start()`（`0x4000000` 未置）。

panic 原文没有进持久日志：`native_panic_flush()` 在 panic 文本打印之前执行
（H117 的设计），日志只有 `NATIVE_PANIC` 标记。

### H151：把 panic 原文写进持久日志（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h151-panic-string.patch`：
`panic_trap_to_debugger()` 入口在调用 `native_panic_flush()` 之前，用
`va_copy` + `vsnprintf` 把 panic 文本格式化成
`NATIVE_PANIC_STR: <原文>` 写入 msgbuf 再刷盘（`vsnprintf` 在 debug.c:132 已声明，
panic 上下文里 `printf` 已在用）。

```text
H151 kernel:  2080d80f47462cc1b4942699fd3d0fd72eec0c8bdb981b30840efb7c54c65135
H151 payload: 420d926020a1855ef934b45dd820b5dc690ba5f2eda327697a11aa8bf84e4c0e
H151 boot:    574157f718aaa87aecdee3dc67ff9d75efeff202dae454e9dd624c06c5197cf0
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H151.img`（已核对）、
Mac `~/h103/boot-H151.img`、仓库 `out/cheeseburger/boot/boot-H151.img`。

### H151 结果：panic 原文到手，是 UFS 探针的硬断言（2026-11-07）

`h151-log-20261107-130442.txt`：

```text
[466.524474] Waiting on <dict …IOProviderClass=IOMedia…UUID=0476…>
[466.526249] Couldn't alloc class "AppleARMFabricTrace"
[466.526412] NATIVE_PANIC_STR: NATIVE_UFS_GPT: qcom,ufshc ADT node not matched @NativeUfsProbe.cpp:2480
```

`NativeUfsProbe::start()` 里有：

```c
  if (!compatibleContains (compatible, "qcom,ufshc")) {
    panic ("NATIVE_UFS_GPT: qcom,ufshc ADT node not matched");
  }
```

我们把 `IOPlatformDevice` 的 GOP nub 注册进服务平面后，`registerService → startMatching`
会让 IOKit 拿**所有** `IOProviderClass = IOPlatformDevice` 的 personality 来试配这个新
nub；`NativeUfsProbe` 也在其中，于是它的 `start()` 被调用，而我们的 nub 没有
`qcom,ufshc` 的 `compatible`，这条硬 panic 直接打死机器。

### H152：UFS 探针对非本节点改为优雅拒绝（2026-11-07）

`drivers/NativeUfsProbe/NativeUfsProbe.cpp`：先校验 `compatible` 与
`p8,msm8998-direct-dma` profile，**再**调用 `IOService::start()`；不匹配时打印
`NATIVE_UFS_GPT: not the UFS node provider=… skipping` 并 `return false`，
不再 panic。

```text
H152 kernel:  cb03ef4e0659d643270d63a8250fd719d07bba0459dd408928c3169be99ec740
H152 payload: 315da7efc556bb6bdf4c67f1475f8a8959d57ff4f67954dc68d9321b35cdc053
H152 boot:    e0dd680c0a48b84ecc21f38cd4acb3a7120c0d4b667e2fc6471a25d3f501ee60
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H152.img`（已核对）、
Mac `~/h103/boot-H152.img`、仓库 `out/cheeseburger/boot/boot-H152.img`。

判读：不再出现该 panic；同一批匹配里 `NativeLegacyDisplay` 应被实例化，
`flags` 出现 `0x4000000`/`0x8000000`，`NATIVE_IOMFB_PROBE` 的
`IOMobileFramebuffer` 应为非 0。

### H152 结果：校验过早，UFS 探针把真节点也拒了（2026-11-07）

H152 上机后持久日志正文没有更新（三次导出文件均 37878 字节，md5 只差文件头时间戳），
说明这次启动**没有向槽里写任何东西**。原因是 H152 把
`compatible`/`p8,msm8998-direct-dma` 校验挪到了 `IOService::start(provider)` **之前**：

```c
  OSData *compatible = provider ? provider->getProperty ("compatible") : nullptr;
  if (!compatibleContains (compatible, "qcom,ufshc") ...) return false;   // 属性还没就绪
```

provider 的这些属性是在 `IOService::start(provider)` 过程中才可用的，于是真正的 UFS
节点也被拒绝 → 存储驱动不启动 → 日志窗口不存在 → 既无日志也无从判断。

### H153：恢复原顺序，只把 panic 换成拒绝（2026-11-07）

```c
  if (!IOService::start (provider)) return false;
  OSData *compatible = ...getProperty ("compatible");
  OSData *profile = ...;
  if (!compatibleContains (...) || !profile || ...) {
    IOLog ("NATIVE_UFS_GPT: not the UFS node provider=%s, skipping\n", provider->getName ());
    return false;      // 不再 panic
  }
```

真 UFS 节点行为与 H151 完全一致；GOP nub 被匹配时只是返回 false。

```text
H153 kernel:  aa76eadeea40219cf800342676eddadfe775ce9b9c4a918f294098567cb5724b
H153 payload: 2fe4b7620d5ec8fe98a6f9d66aa73bcbefe4757d84139a0a8dba61ba8b32355c
H153 boot:    84804f7c48d23e4b3646ce4c3b6456eb8ac05a5628766f602adafde0f0eba89b
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H153.img`（已核对）、
Mac `~/h103/boot-H153.img`、仓库 `out/cheeseburger/boot/boot-H153.img`。

### H153 结果：进展很大，但 panic 钩子自己被 mutex 断言打死（2026-11-07）

屏幕显示 H153 已越过很多关卡：

```text
NATIVE_LEGACY: phase=4 dt=1 nub-registered name=NativeGOPFramebuffer
NATIVE_UFS_GPT: not the UFS node provider=NativeGOPFramebuffer, skipping   ← H153 拦截生效
apfs: 成功挂载 Data / SystemCryptex 等卷
NATIVE_H67_OPEN: … dyld_shared_cache_arm64 …  shared_region_start_address() failed
NATIVE_UFS_ALIVE: winFlight=0 ufsFlight=0 cmds=1731 …
panic(cpu 0 …): Attempt to take mutex 0xfffffff00762cc40 with preemption disabled (1) @lock_rtx.c:194
```

但持久日志**完全没更新**（`boot_id`/`slots_written` 与 H151 相同）。原因是 H151 的 panic 钩子
在 `panic_trap_to_debugger()` 入口做 `printf`（取 msgbuf mutex）并调用
`native_panic_flush()`（取 `fLock`）。当真正的 panic 发生在**禁用抢占**的上下文里
（例如持有自旋锁或在锁内出错），钩子会立刻引发二次 panic，掩盖原始原因，而且
flush 也永远写不出去 —— 与“屏幕只见 mutex panic、磁盘日志不变”完全一致。

### H154：panic 钩子先检查抢占级别（2026-11-07）

`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h154-panic-guard.patch`：

```c
	{
		extern int get_preemption_level(void);
		extern void native_panic_flush(void);
		if (get_preemption_level() == 0) {
			va_copy(…); vsnprintf(…);
			printf("NATIVE_PANIC_STR: %s\n", msg);
			native_panic_flush();
		}
		/* 抢占被禁时不做任何加锁动作，让原始 panic 原样输出 */
	}
```

构建标记更新为 `NATIVE_BUILD: H154`。

```text
H154 kernel:  61142f9389944234b91a3a947e6973eedc0e11dade6deb1fb4df32c5cf5f3388
H154 payload: 7c18cbb8c1afbe423eb96e6102ce0c58f342b6c5770578e0b34d9900cf7ba12a
H154 boot:    741ded6f1a3f2d8acbc3777b4d8c31f46e98932e2aac0526559d4ddbe5f0b415
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H154.img`（已核对）、
Mac `~/h103/boot-H154.img`、仓库 `out/cheeseburger/boot/boot-H154.img`。

判读：若仍在“禁用抢占”上下文 panic，屏幕会显示**原始** panic 文本（需拍照）；
若抢占正常，日志里会有 `NATIVE_PANIC_STR` 且槽会更新。

### H154 结果：panic 钩子不再自伤，露出真正的 data abort（2026-11-07）

屏幕（`h154` 启动）：

```text
shared_region: … vm_shared_region_start_address() failed
NATIVE_UFS_ALIVE: winFlight=0 ufsFlight=0 cmds=1731 …
panic(cpu 0 caller 0xfffffff007a17f08): Kernel data abort. at pc 0xfffffff007b25a08,
  lr 0xfffffff007b25a08
  esr: 0x96000006  far: 0x0000000000000008
  x0=0 x1=0 x2=0xfffffff007734e20 x3=0xfffffff9c3f520 …
```

- H154 生效：不再出现“禁用抢占取 mutex”的二次 panic，露出了原始 data abort；
- `far=0x8`、`x0=0` → 空指针 +8 解引用；
- `pc` 落在 `__common`(BSS) 区（`kernel.macho` 的 `__text` 到 `0x…a89384` 为止），
  说明预链接后的地址布局与 dSYM 不一致，无法可靠符号化；
- 持久日志仍**没有更新**（`boot_id`/`slots_written` 与 H151 相同）：panic 时
  `h103FlushNow()` 很可能因为心跳线程正持有 `fLock` 而超时失败，所以连
  `NATIVE_PANIC_STR` 也没落盘。

### H155：日志间隔 60 s → 10 s（2026-11-07，仅改 payload）

既然 panic 时刻的 flush 不可靠，就让日志“平时就几乎是最新的”：把
`h103-log-secs=60` 改为 `h103-log-secs=10`，这样即使 panic flush 失败，最多也只丢
最后 10 秒。内核不变，仅重打 payload。

```text
H155 kernel:  61142f9389944234b91a3a947e6973eedc0e11dade6deb1fb4df32c5cf5f3388（沿用 H154）
H155 payload: c23e8bbcf3b3cd2d42452ace6c68f137e7e6f8efd6ef39af0b097335ec610567
H155 boot:    39c9f94e5c043e368ad670a41bde0cd36e5aea3123a30c3dec9ff0d21232626c
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H155.img`（已核对）、
Mac `~/h103/boot-H155.img`、仓库 `out/cheeseburger/boot/boot-H155.img`。

### H155 结果：日志仍然为空，因为刷盘被 h107 gate 挡住（2026-11-07）

`h155-log-20261107-135905.txt` 的 header 仍与 H151 相同（`boot_id: 8958133734`、
`slots_written: 1`），但屏幕上明明有 `NATIVE_UFS_HB: slotMode=1`、
`NATIVE_UFS_LOG: setup …`、`NATIVE_UFS_HB: enter`。

原因在 `h103SlotTick()`：

```c
  if (!h107GateOpen ()) return;    // 没有 backboardd/SpringBoard exec 就直接返回
  …按 h103-log-secs 刷 slot
```

`h107GateOpen()` 需要 `native_boot_flags & 4`（backboardd exec）。这几轮都是
launchd 的 shared region 映射失败 → backboardd 从未 exec → gate 永不打开 →
周期刷盘一次也没发生；而 panic 时刻的 `native_panic_flush()` 又因为这次 data abort
发生在禁用抢占的上下文里，被 H154 的保护跳过。

### H156：gate 之前也按间隔刷盘（2026-11-07）

`h103SlotTick()` 中在 `h107GateOpen()` 之前加：

```c
  if (!h107GateOpen ()) {
    static uint64_t lastEarlyFlush;
    uint64_t now = mach_absolute_time ();
    uint64_t interval = (uint64_t) gH103LogSecs * 19200000ULL;
    if (interval && (!lastEarlyFlush || now - lastEarlyFlush >= interval)) {
      lastEarlyFlush = now;
      h103FlushNow ();
    }
    return;
  }
```

即“gate 之前”也按 `h103-log-secs`（当前 10 秒）刷一次 slot。这样 launchd 阶段就崩
的启动至少能留下最后 10 秒的完整日志。

```text
H156 kernel:  e396a99f3a2fdad009a7d77eb208caf0fd9bb94f17014d2b3eebb607c16416ef
H156 payload: 535c2463876fd77571d46a50f9ecc3f99c8d930b429ff5c3eb42dd8deb19667b
H156 boot:    b7c58a8c08eb5771e8c7e095777af1e90dd2b53ab86b13c30762a0f9083c5cc7
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H156.img`（已核对）、
Mac `~/h103/boot-H156.img`、仓库 `out/cheeseburger/boot/boot-H156.img`。

### H157：心跳在前门未开时按 1 秒节拍并每次刷盘（2026-11-07）

H153–H156 的屏幕都显示系统在 launchd 阶段几秒内就崩，而持久日志一直是 H151 的旧内容。
原因不是工具缓存（`--adb` 每次重新 dd），而是：

- 周期刷盘挂在 10 秒心跳上，第一次 tick 就在崩溃之后；
- panic 时刻的 `native_panic_flush()` 又因为这次 data abort 属于“禁用抢占”上下文，
  被 H154 的保护跳过。

H157 把观测点前移：

1. `heartbeatThread()` 在 `h107GateOpen()` 为假时按 **1 秒**节拍（门开后恢复 10 秒），
   `NATIVE_UFS_ALIVE` 仍只在第 1 拍和每 10 拍打印；
2. `h103SlotTick()` 的“门未开”分支改为**每拍都 `h103FlushNow()`**（不再受
   `h103-log-secs` 限制）；
3. 构建标记 `NATIVE_BUILD: H157`。

```text
H157 kernel:  4965c1b113ba53d70a5ecf8577ef24bbbd7035497b57190417f3395183eb21b3
H157 payload: 8292d473cc2c5199d0a16f63ef34b92533e811999f514a022635d960c628b23a
H157 boot:    3b22fd414048e43b1fadb778f845a8d16b9d98c587237c92f6dba1cbbdccbf57
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H157.img`（已核对）、
Mac `~/h103/boot-H157.img`、仓库 `out/cheeseburger/boot/boot-H157.img`。

判读：只要这次启动跑过 UFS 启动后 1 秒，日志 header 的 `boot_id`/`slots_written`
就应该变化，并出现 `NATIVE_BUILD: H157` 与崩溃前最后 1~2 秒的内容。

### H157 结果：确认崩溃点，地址落在内核 BSS（2026-11-07）

H157 的屏幕首次显示 `logSecs=10`（说明新内核确实运行），崩溃与之前一致：

```text
panic(cpu 0 caller 0xfffffff007a1f028): Kernel data abort.
  at pc 0xfffffff007b25a08, lr 0xfffffff007b25a08
  esr: 0x96000006  far: 0x0000000000000008
```

用 H157 的 `kernel.macho` 逐段解析：

```
0xfffffff007b25a08 -> __DATA,__common 段内（offset 0x45a08）
```

即保存的 pc/lr 指向内核**未初始化数据段**，配合 `far=0x8`、`x0=0`，更像是
“跳进了一个未初始化的函数指针/vtable”后取数崩溃，而不是普通空指针调用。
崩溃发生得太早（心跳第一拍 1 秒之前或附近），所以日志仍然来不及落盘。

时间线对照（STATUS 历史）：

- H130–H135：显示是**手工** `probe/attach/start/registerService`，系统能跑到
  userland，SpringBoard 因缺 CADisplay 崩溃，**内核没有 data abort**；
- H142 起：显示改为 **KernelConfigTable personality**，内核在 launchd 阶段 data abort。

H142 让 `nub->registerService()` 触发 IOKit 用**所有** `IOProviderClass =
IOPlatformDevice` 的 personality 去试配 GOP nub，其中包含 force-load 的 Apple
家族（`IOMobileGraphicsFamily`、`AppleARMPlatform` 等）；某个驱动被实例化后在
其 `start/probe` 里把 provider 当作 `AppleARMIODevice` 使用（`NULL + 8`），
随后通过未初始化 vtable 调用而崩溃。日志中的
`Couldn't alloc class "AppleARMFabricTrace"` 是同一批匹配里被跳过的另一条。

### H158：移除 display personality，恢复手工启动（因果验证，2026-11-07）

1. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h158-drop-personality.patch`：
   把 H142 加入的 `NativeLegacyDisplay` personality 用 `#if 0` 关掉；
2. `drivers/NativeMobileDisplay/LegacyDisplayProbe.cpp`：恢复 H141 的手工路径
   （`display->probe/attach/start`，并保留 `activeLegacyDisplay`），不再
   `nub->registerService()`；
3. 其余（日志节拍、UFS 拒绝、trust cache、panic 钩子、OSMetaClass）全部保留。

```text
H158 kernel:  60cf5f50378377bb432351bec051e687099c6fe9b8e6d11955a8a9ec00856fb0
H158 payload: 3e81cd7fa1669c3ec8801a798362e1a1c6859d8548fac978759aee31d81ec22c
H158 boot:    b4c4c8276b6995cd905b2efba670b83dad193a9a0472ab5f93048b193f237e59
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H158.img`（已核对）、
Mac `~/h103/boot-H158.img`、仓库 `out/cheeseburger/boot/boot-H158.img`。

判读：若内核 data abort 消失、系统回到“SpringBoard 因缺 CADisplay 崩溃”的状态，
即确认 personality 是触发源；下一步再设计不会触发全局匹配的显示发布方式。

### H158 结果：显示手工路径恢复；SystemOS 卷查找出现时序失败（2026-11-07）

`h158-log-20261107-144948.txt`（首次拿到本轮新日志，`boot_id 5554932097`）：

1. **显示手工路径工作**，并直接证实 matched-state 结论：

```text
NATIVE_LEGACY: self inactive=0 ioclass=IOMobileFramebufferLegacy provider=IOPlatformDevice
NATIVE_LEGACY: self-match name=IOMobileFramebuffer       -> 0 same=0
NATIVE_LEGACY: self-match name=IOMobileFramebufferLegacy -> 0 same=0
NATIVE_LEGACY: self-match name=NativeLegacyDisplay       -> 0 same=0
```

   连精确类名都查不到，因为 `copyMatchingService()` 只返回
   `kIOServiceMatchedState`；手工 start 的服务永远没有这一位。

2. 内核 data abort 未出现，但卡在更早处：

```text
287.5  nx_mount: disk3 checkpoint search: largest xid 14 …
288.4  nx_mount: disk3 stable checkpoint indices …
（没有 disk3s1 的 handle_mount / mount-complete）
289.3  NATIVE_PANIC_STR: offline owner SystemOS mount failed: 80 @kern_exec.c:8456
```

`EAUTH(80)` 来自 `native_owner_cache_prepare()`：它按 UUID
`8846FE78-…` 用 `getMatchingServices` **一次性**查找 SystemOS 卷的 IOMedia，
而这一轮该 media 尚未发布（disk3 容器只做了 checkpoint search），于是
`goto done`。对照历史记录（H96 §4.3、H130/H151）该路径一直是成功的，
**这个问题以前没有出现过**。

### H159：SystemOS 卷查找加有界重试与失败原因（2026-11-07）

1. `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：把一次性查找拆成
   `native_volume_lookup_once()`，外层最多 10 次 × 200 ms 重试，每次打印
   `NATIVE_SYSTEMOS_WAIT: attempt=N matches=M`，命中时打印
   `NATIVE_SYSTEMOS_WAIT: found after N attempts`；UUID/BSD name/唯一匹配校验不变。
2. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h159-owner-mount-diag.patch`：
   `native_owner_cache_prepare()` 的两处失败点打印具体原因
   （`NATIVE_OWNER_MOUNT: root not authorized …` /
   `NATIVE_OWNER_MOUNT: SystemOS media not found stage=…`）。

```text
H159 kernel:  fa6af7c67878561cb68bea1ff5307f8f376fc0b1164b2e9d618e719c4046e82b
H159 payload: 5181bead860ea076d5576de9a3ef21e2b96b37e95ebc5c2799a91dc435517087
H159 boot:    9838468c5c54e51c9f6045341bda06c90f4771ced51003051dd3636f64118643
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H159.img`（已核对）、
Mac `~/h103/boot-H159.img`、仓库 `out/cheeseburger/boot/boot-H159.img`。

### H159 结果：backboardd 打开显示，SpringBoard 撞到 FBSDisplayMode（2026-11-07）

`h159-log-20261107-152005.txt`（`boot_id 13330234246`，运行到 662 s）：

1. **SystemOS 卷挂载成功**（`disk4s1 vol-uuid: 8846FE78-…`，37.9 s），H159 的有界重试
   生效，之前的 EAUTH panic 未再出现。
2. **显示服务已经可被匹配**（这轮首次出现）：

```text
NATIVE_IOMFB_PROBE: name=IOMobileFramebuffer … service=0xfffffff499435000 class=NativeLegacyDisplay
NATIVE_DISPLAY_OPEN: service=NativeLegacyDisplay process=backboardd grant=backboardd match=1
NATIVE_LEGACY: client enter pid=55 comm=backboardd type=0
NATIVE_FRAME: event=5 flags=fd7f600f client=2 xfer=0 frames=0
```

   即“显示可见性”这一关通过：backboardd 找到并打开了 `IOMobileFramebuffer`。
3. SpringBoard 的崩溃点前移到下一个已知关卡：

```text
NATIVE_TRAP_STR: pid=27 comm=SpringBoard
  x0="FBSDisplayMode cannot be configured as requested :
      <FBSDisplayMode: 0x301fa88c0; infxinf@0x (1242x2208/0) 60Hz p3 SDR>"
```

   与 ios-sweet NOTES:396 记录的一致：`FBSDisplayMode` 要求
   `preferredScale > 0`、`refreshRate != 0` 等；当前 **scale = 0**。

4. 残余：`liveactivitiesd` 仍在 `SessionSyncEngine + 0x1d4f8` BRK
   （`x3/x5 = "T transaction_Purging_1"`），属次级问题；560 s 有一次
   `NATIVE_PANIC flags=ef` 没有 `NATIVE_PANIC_STR`（panic 发生在禁用抢占上下文）。

#### scale 的来源

payload 里 `offline-legacy-unit-scale=0`，而
`LegacyDisplayProbe.cpp:448` 的实现是：`enabled<1 || enabled>3` 时直接返回，
**不会把 `display-scale` 写进 `/chosen`**。于是系统拿到的 UI scale 是 0，
正好对上 `FBSDisplayMode (…/0)`。

### H160：只改 payload，打开 unit-scale（2026-11-07）

`offline-legacy-unit-scale=0` → **`=3`**（1080×1920 扫描、逻辑 360×640 pt）；
内核/驱动沿用 H159，不重建。

```text
H160 kernel:  fa6af7c67878561cb68bea1ff5307f8f376fc0b1164b2e9d618e719c4046e82b（沿用 H159）
H160 payload: e4b487212842a15f4554f5b42d4cbd1d21a08d0deb20e0155ed4e7b46625d03d
H160 boot:    2c8c561089c61f53ef831d1a17e9b6e2bbdbfaae496a2dac33fcc4e91d38cb4a
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H160.img`（已核对）、
Mac `~/h103/boot-H160.img`、仓库 `out/cheeseburger/boot/boot-H160.img`。

判读：模式串应变成 `(…/3)`；若 `FBSDisplayMode` 断言消失、SpringBoard 继续运行，
说明 scale 就是这一关；若像素尺寸仍是 1242×2208，则尺寸另有来源（MobileGestalt /
getDisplaySize），下一轮再查。

### H160 结果：unit-scale=3 未改变 mode（2026-11-07）

`h160-log-20261107-153920.txt`（`boot_id 10800627368`，533 s）：

```text
x0="FBSDisplayMode cannot be configured as requested :
    <FBSDisplayMode: 0x302fa6350; infxinf@0x (1242x2208/0) 60Hz p3 SDR>"
```

`unit-scale=3` 对 mode 没有影响，仍是 `(1242x2208/0)`。两种可能：策略没通过它
的前置条件（**静默返回**，无日志），或 `FBSDisplayMode` 的 scale 不从 `/chosen` 读。

另外，该日志里 `NATIVE_UFS_LOCK` 又大量出现（窗口内 276 次、`err 60` 131 次），
H159 更是 462 次 / 205 次；H128–H135 时是 0。与 H155（`h103-log-secs` 60→10）、
H157（门未开时每 1 秒刷盘）的日志写入量增加一致；`readWindowBulk()` 的锁上限
仍是硬编码 2 s（小于 5.2 s 的命令超时）。

### H161：打印 unit-scale 的执行结果（2026-11-07，只加日志）

`drivers/NativeMobileDisplay/LegacyDisplayProbe.cpp` 的
`native_legacy_gop_mapping_observed()` 中，unit-scale 策略的每个退出点都加日志：

```text
NATIVE_LEGACY: unit-scale rejected enabled=3 phase=4 used=0 console=1 geom=1 phys=1 w=.. h=..
NATIVE_LEGACY: unit-scale publish failed chosen=.. scale_added=.. rot_added=..
NATIVE_LEGACY: unit-scale readback missing scale=.. rotation=..
NATIVE_LEGACY: unit-scale status=0 requested=3 chosen=3 rot=0
```

判读：`status=0 chosen=3` 说明 `/chosen` 里确实写入了 `display-scale=3`，而 mode 仍为 0
则说明 scale 来自 MobileGestalt；若是 `rejected`，日志会指出具体是哪一条前置条件。

```text
H161 kernel:  b50d6343f31ef7e3478fc9ca2e37ada91b5c847ad938368a7e79f6b0b391487d
H161 payload: 12a02fa34429a798812c71da42db34c3b523a8c1f2e91f6380acbecc38e7db71
H161 boot:    d7b934bc1c314c525977ed7681b4d14355a2d2e10ee7f174a29febbc4bb05ecd
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H161.img`（已核对）、
Mac `~/h103/boot-H161.img`、仓库 `out/cheeseburger/boot/boot-H161.img`。

### H161 结果：日志正文是旧的，头部是新的（2026-11-07）

`h161-log-20261107-155803.txt` 里：

- **没有 `NATIVE_BUILD`**（H148 起才有），也没有任何 `unit-scale` 行；
- 心跳行是 `NATIVE_UFS_HB: slotMode=1 hbTimer=0 loadIogpu=0`，**缺 `logSecs=` 字段**
  —— 写这段内容的 kernel 比当前源码旧；
- 显示相关行的时间戳（`28.044186`、`35.756568`、`214.163440`）与 H159/H160 **逐微秒相同**。

而 header 是新的（`boot_id 7578000580`、`slots_written 195`、`uptime_s 371`）。
这说明 **slot 正文写入失败、header（单块 4 KB）偶尔成功**，与日志里已有的
`NATIVE_UFS_LOCK: logWrite timeout` 一致：UFS 锁竞争严重时刷盘写被判超时。
所以 H161 的 unit-scale 日志没能落盘，之前的判断依据全部失效。

### H162：恢复存储的干净基线（2026-11-07）

1. payload：`h103-log-secs` 10 → **60**；
2. `readWindowBulk()` 的锁上限 `38400000`（2 s）→ `UFS_DATA_LOCK_TICKS`（6 s），
   与 5.2 s 的 UFS 命令超时对齐（H128 之后只改了 readBlocks 与窗口锁，漏了这里）；
3. 刷盘前检查 `gWindowInFlight`：有窗口请求在飞就跳过本次写，下一拍再试；
   门未开时的早期刷盘也从“每 1 秒”改为“每 10 秒”；
4. 构建标记 `NATIVE_BUILD: H162`。

```text
H162 kernel:  90a7117f1f83a04244499eb04d54ea690d7c90e1660b35bf704888179595d9cc
H162 payload: 47476b7ac26c96be0c8bfe281bd0ef433fe863df272210243dcdc2dad743956f
H162 boot:    4809fc8b31d239c4e37ab4b0f41baf4ef7e6a500abab1e46e760089fa0c4a3ae
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H162.img`（已核对）、
Mac `~/h103/boot-H162.img`、仓库 `out/cheeseburger/boot/boot-H162.img`。

判读：`NATIVE_UFS_LOCK` / `err 60` 应回到 H128–H135 的零水平；随后日志正文才会更新，
届时 H161 的 `unit-scale …` 行会随早期启动一起落盘。

### H162 结果：日志通路恢复，卡点前移到 CADisplay（2026-11-07）

`h162-log-20261107-161530.txt`（内容到 901 s）：

1. **H162 的三条修改生效**：`NATIVE_UFS_LOCK` 103 次、`err 60` 41 次
   （H160 为 276/131，时长 533 s），`logWrite timeout` 只剩 1 次；
2. **H161 的 unit-scale 日志终于落盘**：
   `NATIVE_LEGACY: unit-scale status=0 requested=3 chosen=3 rot=0`，
   确认 `/chosen/display-scale=3` 写入成功；
3. **FBSDisplayMode 断言消失**，SpringBoard 改为
   `x0="failed to find the main CADisplay"`（17 次）；
4. backboardd 打开显示后（`client enter pid=55`）的调用序列：

```text
client io  pid=55 selector=8  status=0          (GetDisplaySize)
client io  pid=55 selector=29 status=e00002c7   (GetDisplayArea, unsupported)
client io  pid=55 selector=74 status=e00002c7   (SupportedFrameInfo)
client io  pid=55 selector=79 status=e00002c7   (GetBlock)
client io  pid=87 selector=28 status=e00002f0   (GetDotPitch, not found)
NATIVE_FRAME: event=5 … frames=0
```

   随后每 ~0.1 秒重复 `op=match comm=backboardd d=IOAcceleratorES ok=0`。

#### 与 H136 同一断言的关系

`failed to find the main CADisplay` 首次出现在 H136；当时的处置链是
H139（backlight-control 通知）→ H141/H142（只有 `kIOServiceMatchedState`
的服务可见，改用 personality）→ H158（personality 触发 data abort，改回手工
`probe/attach/start`）→ H159（backboardd 实际打开，`match=1`）。
本轮 `match=1`、`client enter pid=55 comm=backboardd` 都在，**旧的可见性原因
已经排除**。新证据指向下一道墙，与 H104k 上游对照、ios-sweet 0052n/0053s
记录一致：backboardd 打开显示后卡在 accelerator/renderer 选择
（`IOAcceleratorES` 永远 `ok=0`，`frames=0`），窗口服务器不发布 display，
SpringBoard 因此拿不到 CADisplay。

### H163：日志身份、客户端 I/O 与尺寸来源（2026-11-07，只加诊断）

1. `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：每个 slot 正文前加文本戳

```text
SHLOGS v1 boot=<本次boot固定id> seq=<序号> build=H163 uptime=<秒> bytes=<块字节>
```

   并以本次 boot 的 `h103LogTicks()` 生成一次 id（mountroot 重试导致的二次
   start 不再改变它）；`NATIVE_BUILD` 行改为 `%s boot=%llx`。
2. `scripts/h103-log-pull.py`：读取每个 slot 的戳，按 boot id 分组，只合并
   **锚点 slot（header 指向的最新 slot）所属 boot** 的 slot；无戳的旧镜像
   仍走原来的 header 相对窗口。这样 header 滞后时不会再混入旧 boot 内容。
3. `drivers/NativeMobileDisplay/LegacyDisplayProbe.cpp`：客户端 interposer 对
   `3/4/5/6/7/8/28/29/57/72/74/79/83` 每个选择器前 5 次打印完整
   `in/out/ni/no/struct`，其余仍按原来的前 16 条；用于确认 `GetDisplaySize`
   的真实返回值以及 backboardd 是否调用 swap。
4. `drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp`：`startHardware` 打印
   `dims WxH canvas=<有无>:W,H dotpitch=<有无>:P`，确认框架能读到的几何来源。

```text
H163 kernel:  4b9660c83086e920c8e288758234a238d259588f03e888459aea141e14cf5fbe
H163 payload: fcf160fad3b54866514e31de58647e9b1d3585224db6cdc3d02b09ce8b059e96
H163 boot:    c6fa9a2815c865b142d2e7a42773d18d47bfe2861e5aac5a738569666106810f
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H163.img`（已核对）、
Mac `~/h103/boot-H163.img`、仓库 `out/cheeseburger/boot/boot-H163.img`。
payload 仍为 `offline-legacy-unit-scale=3`、`h103-log-secs=60`。

判读：

- 日志头部出现 `slot_boot=… slot_build=H163 slot_seq_max=…`，且不再混入
  `logSecs=` 缺失等旧内核的行；
- `client io … selector=8` 的输出若是 1080×1920 → 1242×2208 来自
  MobileGestalt/UIKit；若是 1242×2208 → 来自 IOMFB 自身；
- `client io … selector=3/4/5/6` 出现 → CA 已进入 swap；不出现 → 卡在
  renderer/accelerator（对应 `IOAcceleratorES ok=0`）。

### H163 结果：尺寸来源确认，卡在客户端返回策略（2026-11-07）

`h163-log-20261107-170521.txt`。注意：报告 header 里没有 `slot_boot`/`slot_build`
字段，说明这次用的仍是旧版抓取脚本，slot 仍然混了两次 boot 的内容（最早的
51.8 s、60/65 s 那段与 H162 日志逐微秒相同，且没有 H163 新增的 `dims` 行；
真正的 H163 显示启动在 544.6 s）。**下一份日志请用本仓库/ Mac 上已更新的
`scripts/h103-log-pull.py` 抓取**，header 里应出现 `slot_boot=…`。

H163 新增日志的结论（这些行只有 H163 内核才会打印）：

```text
NATIVE_LEGACY: dims 1080x1920 canvas=0:0,0:0 dotpitch=0:0
client io pid=55 selector=8  status=0          out=438,780   (1080x1920)
client io pid=87 selector=8  status=0          out=438,780
client io pid=87 selector=28 status=e00002f0   (GetDotPitch, not found)
client io pid=55 selector=29 status=e00002c7   struct=8      (GetDisplayArea)
client io pid=55 selector=57 status=e00002c7
client io pid=55 selector=79 status=e00002c7   struct=1580 / 44  (GetBlock)
client io pid=55 selector=6  status=0          in=0,80000003
```

- **`FBSDisplayMode` 的 1242×2208 不是 IOMFB 给的**：`GetDisplaySize` 明确返回
  1080×1920，1242×2208（=1080×1920×1.15）是 MobileGestalt/UIKit 对
  “1080×1920 面板”的 iPhone 6/8 Plus 级下采样结果；
- backboardd **从未调用 3/4/5**（SwapBegin/SetLayer/SwapEnd），只在 816 s 调了
  一次 `6`（swap id 0）；`NATIVE_FRAME … frames=0`；
- `IOAcceleratorES` 匹配 `ok=0` 88 次、`AGXAccelerator` 2 次、`AppleCLCD` 1 次；
- 存储：`NATIVE_UFS_LOCK` 113、`err 60` 46、`logWrite timeout` 1（与 H162 同量级）；
- 仍无 `FBSDisplayMode`，SpringBoard 17 次全部是
  `"failed to find the main CADisplay"`。

对照参考实现（`ios-sweet/xnu/patches/0046-sweet-iosurface-iomfb.patch` 的
`IOMobileFramebufferUserClient::externalMethod`）：它只实现
`3/4/5/6/7/8/18/28/72`，**其余选择器一律返回成功并清零输出**
（`default: break;` 后把 `scalarOutput` 和 `structureOutput` 全部置 0）。
我们这一族对 `29/57/79`（以及 `74`）返回 `kIOReturnUnsupported`，是当前唯一
可指认的行为差异；而 ios-sweet 在同样没有 GPU 的机器上 CADisplay 是存在的
（0052n/0053s）。

### H164：按参考客户端返回策略答复未实现选择器（2026-11-07）

1. `drivers/NativeMobileDisplay/LegacyDisplayProbe.cpp` 的客户端 interposer：
   原方法返回 `kIOReturnUnsupported` 时，清零 `scalarOutput` 与
   `structureOutput`（无 descriptor 时）并改为 `kIOReturnSuccess`，每个客户端
   最多打印 24 行 `NATIVE_LEGACY: client fixup pid=… selector=… unsupported->0`。
   原方法本身不改动。
2. 显示 nub 发布真实面板几何：
   `canvas-width=1080`、`canvas-height=1920`、`dot-pitch=401`
   （5.5" 1080×1920 面板，`sqrt(1080²+1920²)/5.5 = 401 ppi`）；
   这样 `GetDotPitch(28)` 由 `kIOReturnNotFound` 变为成功，框架也能读到 canvas。
3. 构建标记 `NATIVE_BUILD: H164`（slot 戳里的 `build=` 同步）。

```text
H164 kernel:  c5f529dc2a88dd6dc1a01fbc43b5e218ab529f91db51b6c911bae9a5de34d12e
H164 payload: 562d103511a4fe8eac32ea09efbe45109432daadfe641fa2647ac1c50c0a2378
H164 boot:    b63de91347dd2230e68c817327b38f99ef75d302c5393654eba3c61b9c0c10d9
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H164.img`（已核对）、
Mac `~/h103/boot-H164.img`、仓库 `out/cheeseburger/boot/boot-H164.img`。

判读：`client fixup … selector=29/57/74/79` 应出现；若 backboardd 由此建立
display，应看到 `selector=3/4/5`（swap）或 CADisplay 断言消失；若仍在
`IOAcceleratorES ok=0` 循环，则下一步按 H104k 的结论补一个可匹配的
`IOAcceleratorES` 服务（窄 personality，不再重犯 H142 的全局匹配）。

### H164 结果：每次启动都在 PMGR 处 panic（2026-11-07）

H164 在每台机器上都停在同一处（屏幕照片）：

```text
calling mpo_policy_init for vnguard
Security policy loaded: Guarded vnode policy (vnguard)
NATIVE_TRUSTCACHE: not ready img4=0 amfi=0
NATIVE_TRUSTCACHE: static cache skipped amfi=0 ready=0
using 9996 buffer headers and 7046 cluster IO buffer headers
Can't load kext com.apple.driver.ApplePMGR - requests to user space are disabled.
panic(cpu 0 …): P11 PMGR: original dependency not loaded @CheeseburgerPlatformPower.cpp:135
```

对照 H163 的正常启动（`AppleImage4 → AMFI → Sandbox → vnguard`，随后
`amfi=0xfffffff00bcfc690`、`P11 PMGR: original ApplePMGRNub registered`）可以判定：
**这一轮所有预链接 kext 都没进 `sKextsByID`**（AMFI/AppleImage4/Sandbox/APFS/PMGR
全部是预链接 kext，只有编进内核的 vnguard 注册了）。PMGR 只是第一个撞上的；
即使跳过它，APFS 也加载不了。

静态核对（全部相同，无法解释）：

- `boot-H164.img` 的 ramdisk 就是 `payload-H164.img`（`562d10…`），其中 kernel 为
  `c5f529dc…`；payload 的 `unixnu.toml` 与 H163 逐字节相同；
- 两份内核的段布局、`__PRELINK_TEXT`/`__PRELINK_INFO` 地址与大小、
  `__DATA_CONST/__mod_init_func` 98 项、`record_startup_extensions_function`
  符号地址全部相同；
- `__PRELINK_INFO` 的 38 个 kext 顺序与字典内容相同，唯一差异是每次构建都变的
  `_PrelinkKCID`（同为 24 字符 base64）。

因此需要直接观测 `readStartupExtensions()` 是否执行、在哪一步停下。

### H165：预链接引导路径打点（2026-11-07，诊断版）

1. `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h165-prelink-diag.patch`
   （只加全局变量与赋值，不改行为）：

   - `iokit/Kernel/IOStartIOKit.cpp` 定义四个持久段全局
     `native_prelink_{section_size,parse_ok,kext_count,fn_set}`（放在这里而不是
     `libsa/bootstrap.cpp`，因为后者所在的 bootstrap 段在 `bsd_init` 之前就被
     `OSKextRemoveKextBootstrap` 释放）；
   - `libsa/bootstrap.cpp` 在 `getsectbynamefromheader`、
     `OSUnserializeXML`、`_PrelinkInfoDictionary` 三处记录实际结果；
   - `IOStartIOKit.cpp` 在调用 `record_startup_extensions_function` 前记录其是否为空。
2. 设备仓库 `scripts/CheeseburgerPlatformPower.cpp`：`cheeseburger_pmgr_startup()`
   先打印

```text
P11 PMGR: prelink fn=%d sect=%x parse=%d kexts=%d load=%d
```

   失败时打印 `P11 PMGR: original dependency unavailable; continuing without the
   ApplePMGR nub` 并**返回**，不再 panic（这样后续 APFS 是否同样缺失、以及持久
   日志是否还能落盘都能看到）。
3. 构建标记 `NATIVE_BUILD: H165`。

```text
H165 kernel:  a405c81f7a5b45c46d083fc4571ad0da13c921fbe68deded1c69c65ea480ac86
H165 payload: 3d4cf4ce7fab8652a911a8d2bdf5587ed140fcd32a1762f585df0f6595b83b9c
H165 boot:    9e11e11eda79714ee31836ece0bddfd0912b9d197e3a819ce2d5b85d03e0bb0c
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H165.img`（已核对）、
Mac `~/h103/boot-H165.img`、仓库 `out/cheeseburger/boot/boot-H165.img`。

判读：

- `fn=0` → 静态构造没跑，`record_startup_extensions_function` 为空；
- `sect=0` → `__PRELINK_INFO` 段没被找到；
- `parse=0` → 内核 XML 解析器拒绝了该 plist；
- `kexts=-2/0` → 解析成功但 kext 数组为空；
- `kexts=38` 且 `load=0` → 预链接正常，问题在 H164 那张产物本身，需要给构建加
  产物自检；`kexts=38` 但仍在别处失败 → 按后续日志继续定位。

### H165 结果：能启动、H164 显示改动生效，但日志被上一轮 boot 污染（2026-11-07）

`h165-log-20261107-181312.txt`：

1. **H165 正常启动并长期运行**：APFS、AMFI、Sandbox、PMGR nub 都正常，内容一直到
   2426 s，daemon 持续拉起；H164 那种“预链接 kext 全部未注册”的 panic 没有复现。
2. **slot 戳生效**：24 个 slot 全部是
   `SHLOGS v1 boot=7e08b0130 seq=0..23 build=H165`。
3. **H164 的显示改动确实在工作**：

```text
client io pid=88 selector=8  status=0 out=438,780     → GetDisplaySize = 1080x1920
client io pid=88 selector=28 status=0 out=191         → GetDotPitch = 401（此前 NotFound）
client fixup pid=55 selector=57/22/33/79/74 unsupported->0
NATIVE_FRAME: event=5 … client=2 frames=0
```

   仍未 swap（`frames=0`）；SpringBoard 的 15 次断言仍是
   `"failed to find the main CADisplay"`（501–798 s）。
4. **但日志仍混入上一轮 boot 的文本**：出现 H155 之前的
   `NATIVE_UFS_HB: slotMode=1 hbTimer=0 loadIogpu=1`（缺 `logSecs=`）、没有
   `NATIVE_BUILD`、没有 `P11 PMGR: prelink fn=…`，而且 slot 戳的 uptime 只到
   664 s 却包含 2426 s 的正文。

根因：暖重启不清 DRAM，内核消息环也没有清零；`h103CopyMsgbufTail()` 拷贝
“以写指针结尾的最后 N 字节”时，在写指针尚未绕满一圈的情况下**回卷到环尾**，
而那部分仍是上一次 boot 写下的旧文本。于是每个 slot 都掺入旧内核输出，
H165 的 PMGR 诊断行正好被挤掉。

### H166：日志槽只拷贝本次 boot 的字节（2026-11-07）

`drivers/NativeUfsProbe/NativeUfsProbe.cpp` 的 `h103CopyMsgbufTail()`：

1. 用静态的 `lastX`/`laps` 跟踪消息环是否绕满一圈；
2. `laps == 0`（本次 boot 还没绕圈）→ 有效区间是 `[0, msg_bufx)`，从
   `valid - n` 线性拷贝，**绝不回卷**；
3. `laps > 0`（整圈都是本次 boot 的数据）→ 才使用原来的回卷公式；
4. 构建标记 `NATIVE_BUILD: H166`。

```text
H166 kernel:  7f226526d8e19b4da4af1f05f8e4f2c2da74c5b1040951015ec4769ec93de984
H166 payload: 14531cf615ed160d350807f46e455bc8e13b25098f4bd32a1818fff345c55c3f
H166 boot:    3098df94e66b8d2786eeadd8d862030e601acf523c31e08cf263a75c5002e1d3
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H166.img`（已核对）、
Mac `~/h103/boot-H166.img`、仓库 `out/cheeseburger/boot/boot-H166.img`。

判读：每个 slot 只应包含本次 boot 的字节；报告中应能第一次看到
`NATIVE_BUILD: H166 boot=…` 和
`P11 PMGR: prelink fn=… sect=… parse=… kexts=… load=…`。
另：H164 的 panic 在 H165 上没有复现，待用 `boot-H164.img` 再启动一次留档，
以区分“产物损坏”与“启动期竞态”。

### H166 结果：预链接路径健康，但槽尾仍掺旧内容（2026-11-07）

`h166-log-20261107-183846.txt`：

```text
P11 PMGR: prelink fn=1 sect=76000 parse=1 kexts=38 load=0
NATIVE_BUILD: H166 boot=278eafa7
header: slot_boot=278eafa7 slot_build=H166 slot_seq_max=18
```

H165 的打点结论明确：静态构造已执行、`__PRELINK_INFO` 段存在、XML 解析成功、
38 个 kext 全部登记、`OSKextLoadKextWithIdentifier(ApplePMGR)` 成功。
另有用户复测：H164 仍稳定出现 vnguard-first + PMGR panic，**H164 那张产物损坏**
（与源码无关）。

但报告仍混旧内容：`NATIVE_UFS_LOG: setup` 出现 3 次（34.8 s 本次、59.4/64.7 s
另一套），其中 59.3 s 的 `NATIVE_UFS_HB: slotMode=1 hbTimer=0 loadIogpu=1`
**缺 `logSecs=`**——该格式只存在于 H155 之前的内核，而 `kernel-H166.macho` 里只有
一种 `slotMode=%d logSecs=%u …` 格式串。

根因不在消息环回卷（H166 已修），而在槽本身：`h103SlotWrite()` 只写 `blocks`
块（1–32），32 块槽区**未写的部分仍是上一次 boot 的槽内容**；当 payload 塞满写入区
时没有 NUL 填充可供截断，pull 工具按 32 块读整槽就把旧文本接在了后面。

### H167：槽自带精确长度（2026-11-07）

1. `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：槽开头改为固定 128 字节的
   `SHLOGS v2 boot=… seq=… build=H167 uptime=… bytes=<payload 长度>`，
   payload 从偏移 128 开始；`bytes` 记录本次实际拷贝的字节数（不再是槽容量）。
2. `scripts/h103-log-pull.py`：识别 `v2` 时只解码 `body[128:128+bytes]`；
   `v1`/无戳的旧槽维持原逻辑。
3. 构建顺序补充：内核布局变化时先重跑 `scripts/build-sheng-pmgr.py`
   （H164 用的是 11 月 4 日的旧归档），本次已重建。
4. 构建标记 `NATIVE_BUILD: H167`。

```text
H167 kernel:  c427dbb9a1e12932dfece45b9786cdb1bd5022687d331378e7867ea1e3f75863
H167 payload: a22b354329c47e57ea6e0fe95f9b585f4e21f047e3d5a06fa7bb5e46ca31584b
H167 boot:    712d104f9ea7f5c6858d0e08f13c2319d5232103671951f62474fa5d645feaf1
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H167.img`（已核对）、
Mac `~/h103/boot-H167.img`、仓库 `out/cheeseburger/boot/boot-H167.img`。

判读：报告里每一行都应属于本次 boot（不再出现缺 `logSecs=` 的心跳行、也不会出现
与 slot 戳 uptime 不一致的正文），`NATIVE_BUILD: H167 boot=…` 与 slot 戳一致。

### H167 结果：日志终于干净，CADisplay 断言消失（2026-11-07）

`h167-log-20261107-185716.txt`：

```text
header: slot_boot=18469fd43 slot_build=H167 slot_seq_max=15
P11 PMGR: prelink fn=1 sect=76000 parse=1 kexts=38 load=0
NATIVE_BUILD: H167 boot=18469fd43
NATIVE_UFS_HB: slotMode=1 logSecs=60 hbTimer=0 loadIogpu=0      （仅一条）
NATIVE_UFS_LOG: setup …                                        （仅一条）
```

1. 时间戳 335–628 s 连续，没有旧内核的行；`write_errors=1`；
   存储 `NATIVE_UFS_LOCK` **1** 次、`err 60` **0** 次。
2. **整个日志 `NATIVE_TRAP_STR` 计数为 0**：SpringBoard 426.5 s exec 后一直存活
   （526 s 还在做 AppleKeyStore / IOPMrootDomain 查询），不再有
   `"failed to find the main CADisplay"`。H164 的“未实现选择器返回成功并清零”
   加上 `canvas=1080×1920`、`dotpitch=401`（`dims 1080x1920 canvas=1:1080,1:1920
   dotpitch=1:401`）让 CA 接受了这个显示。
3. 新的卡点：`op=match comm=backboardd d=IOAcceleratorES ok=0` 共 **257** 次，
   `AGXAccelerator ok=0` 2 次，`NATIVE_FRAME` 只有 `event=1 client=0 frames=0`，
   没有 `event=5`、没有 swap。
4. 屏幕诊断面板与日志一致：右上 2×2 = 白（backboardd+SpringBoard 均已 exec 且未退出）
   / 品红（最后客户端非 backboardd/FDR）/ 蓝（客户端 <10 次）/ 深灰（无 swap）
   / 橙（backboardd 在查其他 IOKit 类，即 accelerator）。

### H168：可被匹配的 IOAcceleratorES 桩（2026-11-07）

`drivers/NativeMobileDisplay/NativeA540AcceleratorProbe.cpp`：

1. 由 `IOService` 改为 **真正的 `IOAcceleratorES` 子类**（`OriginalAcceleratorABI.h`，
   基类构造/析构/metaclass 用 `original-accelerator-bindings.o` 的
   `private_extern` 绝对绑定）。`IOServiceMatching("IOAcceleratorES")` 按
   IOProviderClass 的类层次匹配，属性 `IOClass` 是无效的（H103fs 的教训）。
2. 实现 `newUserClient`（4 参数与 5 参数两个重载）+ 最小
   `NativeAcceleratorClient : IOUserClient`，打开成功即返回（H103 的结论是桩缺
   的正是这一项）。
3. `LegacyDisplayProbe.cpp`：boot-arg `offline-accelerator=1` 时，
   在 `preModLoad` 前先 `OSKextLoadKextWithIdentifier("com.apple.iokit.IOGPUFamily")`
   （父类 metaclass 必须已存在），把它加入同一批静态构造注册，然后
   `native_a540_accelerator_probe()` 把实例 attach 到 resource service 并发布。
   失败只记录，不影响显示路径。

```text
H168 kernel:  55586fe826b967e1a5ad9e251400ec31943a11f40a5484dd6dad42b260d411b9
H168 payload: 513818fd216970eeb250cb329ac530483dd70677fd79d03e6066c8b7a5368b7e
H168 boot:    3893902a39295d1266e85125653138ab5664f8d61cabcf22139d30cc401e9b41
```

payload 的 args 末尾加了 `offline-accelerator=1`（其余不变）。
镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H168.img`（已核对）、
Mac `~/h103/boot-H168.img`、仓库 `out/cheeseburger/boot/boot-H168.img`。

判读：

- `NATIVE_LEGACY: iogpu load status=0` / `postModLoad status=0` /
  `NATIVE_A540_ACCEL: published IOAcceleratorES` 出现 → 类注册与发布成功；
- backboardd 的 `op=match … IOAcceleratorES` 变为 `ok=1` → 匹配这关通过；
- 随后看是否出现 `NATIVE_A540_ACCEL: user client … granted`，以及
  `NATIVE_FRAME … frames>0` / `selector=3/4/5`；
- 若 `iogpu load status≠0`，说明 pre-root 阶段仍不能加载 IOGPUFamily，需要把
  accelerator 的注册挪到 post-root（后续版本）。

### H168 结果：accelerator 匹配成功，轮询停止（2026-11-07）

`h168-log-20261107-192607.txt`：

```text
200.759  NATIVE_LEGACY: iogpu load status=0 accelerator=1
200.764  NATIVE_LEGACY: postModLoad status=0
200.766  NATIVE_A540_ACCEL: started provider=0xfffffff2d1b88fc0
200.769  NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)
200.771  NATIVE_LEGACY: accelerator publish=1
304.948  NATIVE_IOGPU_ACCEL: name=IOAcceleratorES mc=0xfffffff00caeb688 …
312.379  op=match comm=backboardd d=IOAcceleratorES ok=1
312.470  op=match comm=backboardd d=IOAcceleratorES ok=1
```

1. 预链接里能加载 `IOGPUFamily`（`iogpu load status=0`），accelerator 类随同一批
   `postModLoad` 注册成功（`status=0`），实例发布成功（`publish=1`）；
2. `IOAcceleratorES` 的 metaclass 地址 `0xfffffff00caeb688` 与
   `scripts/data/ioaccelerator-base-abi.json` 的 `metaclass` 一致，说明
   `private_extern` 绝对绑定有效；
3. **backboardd 的 `IOAcceleratorES` 匹配变成 `ok=1`，此前 257 次的轮询在 312 s 停止**；
   紧接着 314.3 s 打开 `IOSurfaceRoot`，314.97 s 出现 `NATIVE_FRAME: event=5 client=2`；
4. 仍然 `frames=0`：没有任何 swap（`client io` 里 `3/4/5` 从未出现），
   也没有 `NATIVE_A540_ACCEL: user client` 行——CA 只是“看见”了 accelerator，
   没有打开它；
5. SpringBoard 全程存活（无 CADisplay 断言）；存储 `NATIVE_UFS_LOCK` 0、`err 60` 0。

### H169：记录 accelerator 被查询的内容（2026-11-07，只加日志）

`drivers/NativeMobileDisplay/NativeA540AcceleratorProbe.cpp`：

1. 覆盖 `copyProperty(const OSSymbol*/OSString*/char*)`，记录 CA 的每次 registry
   属性查询（前 40 条，`NATIVE_A540_ACCEL: read key=…`）——用户态
   `IORegistryEntryCreateCFProperty` 正是走这个虚函数；
2. `newUserClient` 入口打印 `NATIVE_A540_ACCEL: open request type=%u`，确认它是否
   尝试打开。

```text
H169 kernel:  e5cc5a20a15de0de6a8ecd4e489fd79115080c6af53e999efdf32afcd046442f
H169 payload: 509ed83dfcf6a14508f6c6beb7c64d5872ff6a9d5918a36836033e56f3615761
H169 boot:    1450ebc11644bffe9a1c9cbec71b1b0aa9df706c726a95b9ecb35753ada9354a
```

payload 仍带 `offline-accelerator=1`。
镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H169.img`（已核对）、
Mac `~/h103/boot-H169.img`、仓库 `out/cheeseburger/boot/boot-H169.img`。

判读：

- 出现 `read key=MetalPluginName` / `IOGLBundleName` → 下一步是插件名与
  `/System/Library/Extensions/<name>.bundle` 的选择；
- 出现 `open request type=…`（成功或失败）→ 卡点转到 accelerator user client 协议；
- 两者都没有 → CA 只把匹配当作“有 accelerator”，真正的卡点在显示模式数据
  （`GetBlock(79)` / `SupportedFrameInfo(74)` 目前都是“成功+清零”）。

### H169 结果：CA 在要 Metal 插件名（2026-11-07）

`h169-log-20261107-194703.txt`：

```text
367.620  op=match comm=backboardd d=IOAcceleratorES ok=1
369.034  NATIVE_A540_ACCEL: read key=IOClassNameOverride
369.034  NATIVE_A540_ACCEL: read key=IOUserServiceProperties
369.718  NATIVE_A540_ACCEL: read key=MetalPluginName
377.232  NATIVE_A540_ACCEL: read key=MetalPluginName     （7.5 秒一次，反复重试）
384.420  NATIVE_A540_ACCEL: read key=IONameMatch
384.443  NATIVE_A540_ACCEL: read key=IOUserServiceProperties
```

没有任何 `open request`，仍 `frames=0`；SpringBoard 全程存活，存储干净。
对照 `scripts/audit-target-metal-discovery.py` 审计过的原始发现链：

```text
IOServiceMatching("IOAcceleratorES")
  → 服务属性 MetalPluginName（+ 可选 MetalPluginClassName）
  → "/System/Library/Extensions" + <name> + ".bundle"
  → NSPrincipalClass 必须是 _MTLDevice 子类
  → initWithAcceleratorPort: → IOGPUDeviceCreateWithAPIProperty → IOServiceOpen(type 1)
```

即 accelerator 匹配之后，CA 还需要一个 **Metal 驱动插件**；没有插件名它就每
7.5 秒重试一次，永远不进入绘制。而 `NativeAdrenoMetalPlugin.mm` 的注释写明：
插件返回 nil 时“**original software rendering keeps running unchanged**”——
即 CA 有软件渲染路径，只是要被 Metal 发现流程“放行”。

### H170：给 accelerator 一个 MetalPluginName（2026-11-07）

1. `NativeA540AcceleratorProbe::start()`：解析 boot-arg
   `_offline-accelerator-plugin=<name>`（下划线前缀在 `PE_parse_boot_argn` 里
   强制字符串拷贝，上限 16 字符），非空时 `setProperty("MetalPluginName", name)`。
2. payload args 追加 `_offline-accelerator-plugin=AGXMetalA10`——先指向目标
   rootfs 里**原本就存在**的 Apple 插件（`AGXMetalA10.bundle`，
   `NSPrincipalClass=AGXPrincipalDevice`，审计已确认）。若它在非 Apple GPU 上
   初始化失败并返回 nil，CA 应回落到软件渲染。

```text
H170 kernel:  e9292f3e9eff58db2de0098c71385ee08b3591c75cf24aeda5227e6feb20bc88
H170 payload: 9ca8e059cd2585ecb869405a129b61c34aecd86af9ba0ff216b35bd992929002
H170 boot:    6593079d6ae4befb3c900b9bc06006921304b3adc8c74277cc3b44b207d3ea7d
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H170.img`（已核对）、
Mac `~/h103/boot-H170.img`、仓库 `out/cheeseburger/boot/boot-H170.img`。

判读：

- `NATIVE_A540_ACCEL: MetalPluginName=AGXMetalA10` 出现；
- 出现 `NATIVE_A540_ACCEL: open request type=1`（Metal 打开设备）→ Apple 插件被
  真正加载并尝试使用我们的 accelerator；
- 若 backboardd 崩溃/重启 → 换成“自己的最小插件，principal class 是
  `_MTLDevice` 子类但直接返回 nil”，走既有的 Data seed 注入
  （`add-gpu-plugin-data.py` + `sheng-gpu-addon=1`），不需要 Turnip；
- 若出现 `frames>0` 或 `selector=3/4/5` → 软件渲染通路打通。

### H170 结果：每次启动都在 APFS 里 trap（2026-11-07）

屏幕照片：

```text
userdata_ios 1014f40..1c627fa 50392M
partitions=32 listed=4
NATIVE_UFS_ROOT: userdata_ios LBA 1014f40..1c627fa
vm_page_find_contiguous(num=32,low=1048575): found 0 pages … wired count is 36997
vm_page_find_contiguous: zone_gc called … wired count is 36997
vm_page_find_contiguous(num=32,low=1048575): found 0 pages … wired count is 36999
NATIVE_PANIC_STR: Undefined kernel instruction: pc=0xfffffff00b6bd000 instr=807ff000 @sleh.c:1874
…
panic(cpu 0 caller 0xfffffff007a19774): Undefined kernel instruction … @sleh.c:1874
```

1. `pc=0xfffffff00b6bd000` 落在 **`com.apple.filesystems.apfs` 的
   `__TEXT_EXEC`**（段基址 `0xfffffff00b640000`，偏移 `0x7d000`）；该地址在镜像里
   是 `0x52800008`（`mov w8,#0`），与报告的 `instr=807ff000` 不符，属于运行时
   取指错误（野跳/坏数据），不是静态代码问题。
2. **不是**旧的 userdata/userdata_ios 分区 bug：`userdata_ios LBA
   1014f40..1c627fa`、`partitions=32 listed=4` 与 H167/H169 的正常启动完全一致。
3. 真正的线索是紧随其后的
   `vm_page_find_contiguous(num=32, low=1048575): found 0 pages`：这正是
   `NATIVE_UFS_ROOT: userdata_ios LBA …` 之后那次 **128 KB（32 页）低 4 GB
   物理连续 DMA 分配**（`readDma`，`UFS_DATA_MAX=0x20000`）失败。旧代码失败后
   回退到 `inTaskWithOptions(…, 4096)`（可能落在 4 GB 以上），而控制器这里按
   `0xffffffff` 掩码寻址；随后 APFS 读到坏数据并 trap。
4. 对照：H169（同一份 accelerator/display 代码，只少 `MetalPluginName` 和约
   40 字节 args）稳定启动；H170 每次都失败——差异是 payload/args 变化带来的
   低内存布局，不是分区或时序。

### H171：低内存 DMA 分级回退，绝不越过 4 GB（2026-11-07）

`drivers/NativeUfsProbe/NativeUfsProbe.cpp`：

1. 新增 `allocLowContiguous()`：按 128K→64K→32K→16K→8K→4K 依次尝试
   `inTaskWithPhysicalMask(kernel_task, kIOMemoryPhysicallyContiguous, size,
   0xffffffff)`，每次都校验 `phys < 4 GB`、4K 对齐、`contiguous >= size`，
   并打印 `NATIVE_UFS_DMA: low size=… phys=… cont=…`；
2. `readDma` 用它，`queue.dataCapacity` 设为**实际**容量（`readBlocks` /
   `readWindowBulk` 本来就按 `dataCapacity/blockSize` 分块）；全部失败则
   `panic("no low read DMA buffer")`，不再使用 4 GB 以上的缓冲；
3. `logDma` 同样用它，新增 `fLogCapacity`；`logWrite` 把 `blocks` 截到
   `fLogCapacity/4096` 并把 `fQueue.dataCapacity` 设为实际容量；
4. 构建标记 `NATIVE_BUILD: H171`。

```text
H171 kernel:  b04829d1b0eb5e0da7bb7121f5d67b55984d14855630c48bfbe81b558b05c5ca
H171 payload: f8e8e32133c6bdcc880ee2e73377bf6417de9e2a87d896ce71d812ea25e1f7d9
H171 boot:    24533d499f86124334583f8adde5e70faa2dc042b517a73436bb21d018af6732
```

payload 仍带 `offline-accelerator=1` 与 `_offline-accelerator-plugin=AGXMetalA10`。
镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H171.img`（已核对）、
Mac `~/h103/boot-H171.img`、仓库 `out/cheeseburger/boot/boot-H171.img`。

判读：

- `NATIVE_UFS_DMA: low size=20000 unavailable` 后出现较小的
  `low size=10000/8000/…` → 分级回退生效，挂载应能通过；
- `NATIVE_UFS_GPT: read DMA cap=…` 显示实际容量；
- 若出现 `no low read DMA buffer` panic → 低内存确实耗尽，下一步在 display
  probe 之前预留缓冲。

### H171 结果：APFS 不再 trap，但窗口读全部失败（2026-11-07）

`H171-log-20261107-203706.txt`（`slot_build=H171`）：

```text
NATIVE_UFS_ROOT: published window[0]=OS …
NATIVE_UFS_ROOT: published window[1]=SystemOS …
NATIVE_UFS_WINDOW: SystemOS req=4 block=0 count=1
NATIVE_UFS_BULK: lba=117f540 blocks=32 lock=2 cmd=16 unlock=1 ok=0
NATIVE_UFS_WINDOW: SystemOS req=4 done=0 ok=0 ticks=276 read=269 write=0
NATIVE_UFS_WINDOW: SystemOS req=5/6/7 … ok=0
…
Still waiting for root device
NATIVE_PANIC_STR: Failed to mount root device @IOKitBSDInit.cpp:804
```

1. APFS 的 `Undefined kernel instruction` 不再出现——H171 的低内存分级回退生效；
2. 但 `readWindowBulk()` 仍然一次发 **32 块 = 128 KB**（`blocks=32`），而 H171 可能
   只拿到较小的低内存 DMA 缓冲；`ufsCommand()` 里 `bytes > q->dataCapacity`
   直接返回失败，`ticks=276`（~14 µs）说明命令瞬间被拒，不是超时；
3. 于是窗口读全部 `ok=0`，APFS 拿不到任何数据，mountroot 超时
   `Failed to mount root device`。

### H172：窗口批量读按 DMA 容量分块（2026-11-07）

`NativeUfsProbe::readWindowBulk()`：

1. `chunkBlocks = fQueue.dataCapacity / 4096`（为 0 直接失败）；
2. 把一次 32 块的 READ(10) 拆成 `chunkBlocks` 大小的多条命令，每条各拿一次
   `fLock`（保持 H128 的“一条命令一个锁”），成功后
   `dst += bytes; at += chunk; remaining -= chunk`；
3. 日志改为
   `NATIVE_UFS_BULK: lba=… blocks=32 chunk=… calls=… lock=… cmd=… ok=…`；
4. 构建标记 `NATIVE_BUILD: H172`。

```text
H172 kernel:  f60ba4ef6d2ffa66f13ae42815c27c06b185e35a53aad6322a6028ee9e46a060
H172 payload: 99493d3b4fb4b522adb05f7931ce4ae03dbe290c6bb9c6cdb3ee5a3eedebf705
H172 boot:    ecd62a6723ecd412393b39532658b1c23de8112bf20f0868c9b082f9525c0596
```

payload 仍带 `offline-accelerator=1` 与 `_offline-accelerator-plugin=AGXMetalA10`。
镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H172.img`（已核对）、
Mac `~/h103/boot-H172.img`、仓库 `out/cheeseburger/boot/boot-H172.img`。

判读：`NATIVE_UFS_BULK … chunk=<实际容量/4096> calls=N ok=1`、
`NATIVE_UFS_WINDOW … done=1 ok=1`，随后应出现 `Got boot device`、`BSD root: …`、
`mount-complete`。

### H172 结果：完整启动成功（2026-11-07）

`h172-log-20261107-210236.txt`（`slot_build=H172`）：

```text
Got boot device = …NativeUfsWindow…          （60.3 s）
BSD root: disk5s1
mount-complete DawnUpdate21H461…OS / OwnerData / SystemCryptex   （60–62 s）
SpringBoard[27] exec（344.9 s，之后存活）
NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)
op=match comm=backboardd d=IOAcceleratorES ok=1
NATIVE_UFS_LOCK 0、err 60 0
```

即 H171/H172 的 UFS DMA 修复链完成：低内存分级回退 + 窗口读按容量分块后，
挂载恢复正常，系统长期运行。

但 `MetalPluginName` 没生效：日志里只有 CA 的
`NATIVE_A540_ACCEL: read key=MetalPluginName`，没有我们自己的
`MetalPluginName=…` 行——说明 `PE_parse_boot_argn("_offline-accelerator-plugin", …)`
在运行时返回了 false（而同一串里更靠前的 `offline-accelerator=1` 解析成功，
accelerator 已发布、`ok=1`）。因此 CA 没有加载
`/System/Library/Extensions/AGXMetalA10.bundle`，也没有 `open request`，`frames=0`。

### H173：确认 boot args 并让插件名有默认值（2026-11-07）

`drivers/NativeMobileDisplay/NativeA540AcceleratorProbe.cpp`：

1. `MetalPluginName` 解析失败时回落到默认值 `AGXMetalA10`，并记录来源：

```text
NATIVE_A540_ACCEL: MetalPluginName=AGXMetalA10 source=arg|default
```

2. 打印内核实际拿到的 boot args 长度与最后 96 字节：

```text
NATIVE_A540_ACCEL: bootargs len=… tail=…offline-accelerator=1 _offline-accelerator-plugin=AGXMetalA10
```

3. 构建标记 `NATIVE_BUILD: H173`。

```text
H173 kernel:  bac58eb476d022c22caf37ad6066e282285d20acb366a28621aaa7555234e222
H173 payload: c291c811fae30f56348f1fed6caecfb5978ffc59ef761a7dd6796bdc530f2ee0
H173 boot:    9c8103a12cbb3cbfba44d34aaa8f885050b369c77e44a7878100eaf222dbb152
```

payload 仍带 `offline-accelerator=1` 与 `_offline-accelerator-plugin=AGXMetalA10`。
镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H173.img`（已核对）、
Mac `~/h103/boot-H173.img`、仓库 `out/cheeseburger/boot/boot-H173.img`。

投放：手机原处于 TWRP 3.4.0（cheeseburger），已 `adb reboot bootloader` →
`fastboot boot boot-H173.img` 成功（只 boot，未写任何分区）。

判读：

- `source=arg` → 参数解析正常；`source=default` → 解析失败但插件名仍然生效；
- 随后是否出现 `NATIVE_A540_ACCEL: open request type=1`（Metal 打开设备）；
- 是否出现 swap（`frames>0`）或 backboardd 崩溃。

### H173 结果：稳定 panic 在 AppleM2ScalerCSCDriver（2026-11-07）

两次启动都在同一处（屏幕照片）：

```text
ktriage_register_subsystem_strings: set subsystem 8 strings
NATIVE_PANIC_STR: Undefined kernel instruction:
    pc=0xfffffff00b134000 instr=807ff000 @sleh.c:1874
panic(cpu 0 caller 0xfffffff007a1995c): Undefined kernel instruction … @sleh.c:1874
```

- `pc=0xfffffff00b134000` 属于 **`com.apple.driver.AppleM2ScalerCSCDriver`
  的 `__TEXT_EXEC`**（基址 `0xfffffff00b0ed000`，偏移 `0x47000`）；
- 与 H170 的 APFS panic 同签名（pc 在某个预链接 kext 内、`instr` 都是
  `807ff000`，而镜像里该地址是合法指令）。arm64e 的 **PAC 认证失败**在 XNU 里
  就表现为 `ESR_EC_UNKNOWN` → “Undefined kernel instruction”，pc 是被跳转的目标，
  因此更像某个间接调用指针被认证失败/写坏，而不是真的执行到坏指令；
- 时间点在 `native_mobile_graphics_load_probe()` 的
  `OSKextLoadKextWithIdentifier("com.apple.iokit.IOMobileGraphicsFamily")`
  内部，**早于**我们的 accelerator 代码（`postModLoad` 之后才跑）。

构建确定性检查：用**完全相同的源码**重建一次，内核
`bac58eb4…` → `8cb90022…`、再换源码前又得到 `8cb9…` 系列，段对比只有
`__TEXT` 16 字节、`__PRELINK_INFO` 22 字节（KCID）和 `__LINKEDIT` 不同，
`__TEXT_EXEC/__PRELINK_TEXT/__PLK_TEXT_EXEC/__PLK_DATA_CONST` 完全一致，
`IOLog/kprintf/OSKextLoadKextWithIdentifier/IOService::start` 等被 kext 引用的
内核符号地址也相同——所以**不是构建不确定**，而是这次 display archive 的内容/布局
导致的产物差异。

### H174：回退 accelerator 的 H173 诊断改动（2026-11-07）

按 H174 计划的第 2 步：把
`drivers/NativeMobileDisplay/NativeA540AcceleratorProbe.cpp` 恢复到 H170 版本
（去掉 H173 加的 boot-args 日志/默认插件名，保留 H168–H170 的 accelerator 功能），
其余不变，构建标记 `NATIVE_BUILD: H174`。

```text
H174 kernel:  8ba9992cd6574bd59645abc3298b8fe629b719445d2240eda95b7e80c0ab1bc8
H174 payload: 93f314d7895decccf73e8418445fea6d9309d4b8ac494d289e58c1be0d4d4aa4
H174 boot:    2aad7b39726eba782e2e1a124b09014183a4d9dcaaa655338e0e8d3114df0679
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H174.img`（已核对）、
Mac `~/h103/boot-H174.img`、仓库 `out/cheeseburger/boot/boot-H174.img`。
已用 `fastboot boot` 启动（未写任何分区）。

判读：

- 若能正常启动 → 就是 H173 那段 accelerator 改动触发的（尽管执行时间在后），
  以后把 boot-args/默认插件名诊断放到 UFS 驱动侧实现；
- 若仍在 `pc=0xfffffff00b134000` panic → 说明是 display archive 重建本身导致
  预链接产物差异，需要给 `emit_prelink` 增加产物一致性校验。

### H174 结果：回退后正常启动（2026-11-07）

`h174-log-20261107-214856.txt`：

- `Got boot device` 60.4 s、`BSD root: disk5s1`、OS/OwnerData/SystemCryptex 全部
  mount-complete；
- SpringBoard 存活（无 CADisplay 断言），`NATIVE_UFS_ALIVE` 里
  `winReq=1930 winBytes=1010922496`，`NATIVE_UFS_LOCK` 0、`err 60` 0；
- accelerator 在 365.2 s 发布，backboardd 匹配 `IOAcceleratorES ok=1`；
- 但 369.7 s 的 `read key=MetalPluginName` 仍为空，`frames=0`。

即：回退 H173 的 accelerator 源码后产物恢复正常，问题确实锁在那次 display
archive 的再编译上。

### H175：从 UFS 心跳注入 MetalPluginName（2026-11-07）

不碰 display archive（保持 H174 的 `.a`）：

1. `drivers/NativeUfsProbe/NativeUfsProbe.cpp` 新增
   `h103MaybeSetAcceleratorPlugin()`，心跳线程每拍调用一次；
2. 仅当 `offline-accelerator=1` 时启用；`IOService::serviceMatching
   ("IOAcceleratorES")` → `copyMatchingService`，找到后
   `setProperty("MetalPluginName", name)` 一次，并打印
   `NATIVE_UFS_ACCEL: service=… MetalPluginName=… source=arg|default set=…`；
3. 名字取 `_offline-accelerator-plugin`（解析失败用默认 `AGXMetalA10`）；
4. 构建标记 `NATIVE_BUILD: H175`。

```text
H175 kernel:  e920ff0d12cd124fa2ea3bdd659ea5eee8607f753716979b9b0b57406b34db42
H175 payload: 5d40815f33b6a81cff30dacd60bfc0721e56c1fec12b7e36776af908c104be65
H175 boot:    f1a183eef0a363a5525041673c316022ca50da7a8378316a8953e46a54ea7a05
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H175.img`（已核对）、
Mac `~/h103/boot-H175.img`、仓库 `out/cheeseburger/boot/boot-H175.img`。
手机原在 TWRP，`adb reboot bootloader` → `fastboot boot` 启动（未写分区）。

判读：

- `NATIVE_UFS_ACCEL: … MetalPluginName=AGXMetalA10 …` 出现；
- 随后 `NATIVE_A540_ACCEL: read key=MetalPluginName` 之后是否出现
  `open request type=1`；
- `frames>0` / `selector=3/4/5` 或 backboardd 崩溃。

### H175 结果：MetalPluginName 生效，CA 转而找 AGXAccelerator（2026-11-07）

`H175-log-20261107-220639.txt`：

```text
50.608  NATIVE_UFS_ACCEL: service=0xfffffff3a82fa3e0 MetalPluginName=AGXMetalA10 source=arg set=1
266.477  NATIVE_A540_ACCEL: read key=MetalPluginName
266.505  NATIVE_A540_ACCEL: read key=MetalPluginClassName
816.171  op=match comm=backboardd d=AGXAccelerator ok=0
816.456  op=match comm=backboardd d=AGXAccelerator ok=0
```

1. UFS 心跳注入生效，`source=arg` 说明 boot-arg 解析成功（H173 的 panic 与参数无关）；
2. CA 读到了非空的 `MetalPluginName`，并且 **Apple 的 AGX 插件被加载**（否则不会有
   后面的 `AGXAccelerator` 查询）；
3. 插件按类名找 `AGXAccelerator`，而桩类名是 `NativeA540AcceleratorProbe`，
   `metaCast("AGXAccelerator")` 失败 → `ok=0`，Metal 拿不到设备，仍 `frames=0`，
   也没有软件渲染回退。

### H176：桩类改名为 AGXAccelerator（2026-11-07）

`drivers/NativeMobileDisplay/NativeA540AcceleratorProbe.cpp`：

1. 类 `NativeA540AcceleratorProbe` → **`AGXAccelerator`**（仍是 `IOAcceleratorES`
   子类，宏/方法作用域/`new`/`gMetaClass` 全部同步）；
2. 实例名改为 `AGXAccelerator`；
3. `native_iogpu_accel_probe()` 的候选类列表去掉 `"AGXAccelerator"`，避免它把
   我们这个类再分配/发布一次；
4. `NATIVE_BUILD: H176`。

```text
H176 kernel:  89c2bfd722ed82b269b406579e75fe9775ef710ef576c47913f446bad034307e
H176 payload: 56775c7f6a063bed1447b9f20e4b5ef5d0c296db26c98bacb574beeffa4c0c84
H176 boot:    8551b71ad86f595f982c51e091f06ecdc83c26b18634be03da39da8163e13f77
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H176.img`（已核对）、
Mac `~/h103/boot-H176.img`、仓库 `out/cheeseburger/boot/boot-H176.img`。
手机在 TWRP，`adb reboot bootloader` → `fastboot boot` 启动（未写分区）。

判读：

- `op=match … AGXAccelerator ok=1`；
- `NATIVE_A540_ACCEL: open request type=1`（Apple 的 AGX 用户态打开桩）；
- 之后若返回 nil → CA 可能回退软件渲染（`frames>0`）；若崩溃 → 改为自写 nil 插件。

### H176 结果：日志窗口再次丢失（2026-11-07）

`H176-log-20261107-222617.txt`：

- 注入生效：`41.446 NATIVE_UFS_ACCEL: … MetalPluginName=AGXMetalA10 source=arg set=1`；
- 但 240–345 s 的新鲜窗口里 **没有一条** `op=match comm=backboardd`，
  唯一的 `AGXAccelerator` 行是 H175 的残留（时间戳 `357.685793` 与上一份完全相同），
  365–372 s 的 `Got boot device`/mount 也来自上一轮 H169；
- 屏幕仍是内核控制台在滚，即 backboardd 仍未提交帧。

根因：槽内容仍是“消息环最后 N 字节”（tail）。本次 boot 写入量不足 N、且内核消息环
跨暖重启不清零时，拷贝会伸进上一轮 boot 的文本，正好把最关键的那段挤掉。

### H177：槽内容改为真正的 delta（2026-11-07）

`drivers/NativeUfsProbe/NativeUfsProbe.cpp`：

1. `h103CopyMsgbufTail()` 换成 `h103CopyMsgbufDelta(out, cap, previous, cursor)`：
   - `delta = cursor >= previous ? cursor - previous : size - previous + cursor`；
   - 只拷贝 `[cursor - delta, cursor)` 这段（环形）字节；
   - `delta > cap`（游标被重置/跳变）时保留最新 `cap` 字节；
   - 首次刷盘 `previous = 0` → 拷贝本次 boot 到目前为止的全部输出；
2. 槽内的 `SHLOGS v2 … bytes=` 现在就是这段 delta 的真实长度；
3. 构建标记 `NATIVE_BUILD: H177`。

```text
H177 kernel:  978b1c0d3dd7ab048659a30acea3b7373bfda93d897cabaf967eb576e5bcf737
H177 payload: 06fffcbd90a33390499f6b762adf5e7a2ea1ba302030a1122cb640436d57e577
H177 boot:    5d24f8954d8c1dde666b808875efc5ae5446c93d4337ebb13b156a5162db7d27
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H177.img`（已核对）、
Mac `~/h103/boot-H177.img`、仓库 `out/cheeseburger/boot/boot-H177.img`。
手机在 TWRP，`adb reboot bootloader` → `fastboot boot` 启动（未写分区）。

判读：日志里每一行都应属于本次 boot；应能看到此前被挤掉的
`op=match comm=backboardd d=AGXAccelerator ok=?`、`open request type=?`、
`frames=?`。

## 近期结果汇总（H167–H177，2026-11-07）

本节把最近十轮的结论收在一处；逐轮细节见下面各小节。

### 已经打通的部分

1. **存储/挂载**（H166–H172、H177）：
   - 暖重启残留字节不再混入日志（H166 tail 修复、H167 `SHLOGS v2` 精确长度、
     H177 改为真正的刷盘 delta）；
   - 低内存物理连续 DMA 改为 128K→4K 分级回退（H171），窗口读按实际容量
     分块（H172）——`Got boot device` / `BSD root: disk5s1` / OS、OwnerData、
     SystemCryptex 三个卷的 `mount-complete` 在 60 s 左右完成；
   - `NATIVE_UFS_LOCK`、`err 60` 稳定为 0。
2. **显示可见性 / CADisplay**（H159–H167）：
   - `IOMobileFramebufferLegacy` 服务可被 backboardd 打开（`match=1`）；
   - H164 的“未实现选择器返回成功并清零 + canvas/dot-pitch”之后，
     SpringBoard 不再撞 `"failed to find the main CADisplay"`，可长期存活；
   - 显示服务报告 `GetDisplaySize = 1080x1920`、`dotpitch = 401`、
     `canvas = 1080x1920`。
3. **accelerator 发现链**（H168–H176）：
   - 裸 `IOAcceleratorES` 子类 + `newUserClient` 让 backboardd 的
     `IOServiceMatching("IOAcceleratorES")` 变为 `ok=1`，此前 257 次的轮询停止；
   - UFS 心跳注入 `MetalPluginName=AGXMetalA10`（H175）后，Apple 的 AGX 插件被
     加载，CA 转而查询 `AGXAccelerator`（H176 已把桩类改名为 `AGXAccelerator`）。

### 仍未打通的部分

- **没有一帧 swap**：`NATIVE_FRAME … frames=0`、`selector 3/4/5` 从未出现，
  屏幕始终是内核控制台（控制台只在第一帧 swap 时让出）；
- backboardd 的窗口服务器已打开 IOMFB、启用帧信息通知，但渲染器没有产出。

### 已知的坑

- **display archive 再编译有风险**：H173 仅给 `NativeA540AcceleratorProbe::start()`
  增加了 boot-args 日志/默认插件名，产物就稳定 panic 在
  `AppleM2ScalerCSCDriver`（`pc=0xfffffff00b134000`，PAC 认证失败形态）；
  H174 回退后立即恢复正常。此后 accelerator 侧改动尽量放到 UFS 驱动（H175 起）。
- H164 的预链接产物曾经“每次启动都不注册任何 kext”，重建后消失；
  这类产物级差异目前只能靠“构建后实机启动”验证。
- `liveactivitiesd` 仍在 `SessionSyncEngine + 0x1d4f8` BRK（次级问题，未处理）。

### 下一步（按优先级）

1. 用 H177 的干净日志确认 H176 的真实结果：
   `op=match … AGXAccelerator ok=?`、`open request type=?`、`frames=?`；
2. 若 `ok=1` 且 Metal 打开设备后仍不渲染 → 转“自写最小 `_MTLDevice` nil 插件
   + Data seed 注入”（`add-gpu-plugin-data.py` + `sheng-gpu-addon=1` 通道），
   目标是让 CA 回退软件渲染并出第一帧；
3. 若要真正用 GPU，则进入 Adreno 主线：内核 Adreno 驱动 + Turnip/Mesa 的
   Metal/Vulkan 用户态插件（`drivers/NativeAdreno`、`build-adreno-metal-plugin.py`），
   需要先构建 Turnip，属于独立的大工程。

### H177 结果：delta 仍未消除旧文本，根因是环游标起点（2026-11-07）

`H177-log-20261107-224329.txt`：

- header 正常（`slot_boot=2e071d92 slot_build=H177 slot_seq_max=24`）；
- 但正文仍在 368 s 出现 H170 时代的
  `NATIVE_UFS_GPT: read DMA low failed; high fallback`（该字符串在当前内核里
  已不存在），并且 **没有任何** `NATIVE_UFS_DMA` / `chunk=` / `NATIVE_BUILD: H177`
  行——说明这些槽的内容不是本次 boot 的。

根因：暖重启不清内核消息环，且环的写游标不一定从 0 开始。`gH103LastSlotMsgX`
初始为 -1，首次刷盘用 `previous=0`，于是把 `[0, cursor)` 整段（包含上一次 boot
留下的文本）都写进了第一个槽。

### H178：首次刷盘从“探针启动时的游标”开始（2026-11-07）

`drivers/NativeUfsProbe/NativeUfsProbe.cpp`：

1. 在 `start()` 里记录当前 `msgbufp->msg_bufx` 到 `gH103LastSlotMsgX`，
   并打印 `NATIVE_UFS_LOG: base cursor=%d size=%d`；
2. 首个槽因此只包含探针启动之后新产生的字节（代价是 0–40 s 的早期启动日志
   不再进入槽，这些内容其它轮次已有记录）；
3. 构建标记 `NATIVE_BUILD: H178`。

```text
H178 kernel:  4f94e3997004085208be08b4f78e0fcf2dd86aad35c1c2d7eb2451fc26282a36
H178 payload: ec973ed18828cea013b9878feb866ae67e2229b3fb4cf425bdd1485a507ea4d4
H178 boot:    fc7c2df5fa2e54b2514b2b905a5a446f7c6b0464e0ab061269e759d12e5702b9
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H178.img`（已核对）、
Mac `~/h103/boot-H178.img`、仓库 `out/cheeseburger/boot/boot-H178.img`。
手机在 TWRP，`adb reboot bootloader` → `fastboot boot` 启动（未写分区）。

判读：日志里应出现 `base cursor=… size=…`，并且 **不再出现**
`read DMA low failed`（H170 的字符串）或 `NATIVE_BUILD: H169`；
随后才能看到 `op=match … AGXAccelerator ok=?`、`open request type=?`、`frames=?`。

### H178 结果：日志干净了，但出现“内容空洞”（2026-11-07）

`H178-log-20261107-225812.txt`：

```text
40.075  NATIVE_UFS_LOG: base cursor=54388 size=131072
40.118  NATIVE_BUILD: H178 boot=2de92930
41.316  NATIVE_UFS_ACCEL: … MetalPluginName=AGXMetalA10 source=arg set=1
255.039 NATIVE_DISPLAY_OPEN: … process=backboardd … match=1
368.784 op=match comm=backboardd d=IOAcceleratorES ok=1
369.718 NATIVE_A540_ACCEL: read key=MetalPluginName
```

- 证实了 H177 的推断：暖重启后消息环写游标在 **54388**（环大小 131072），
  所以 `previous=0` 首次刷盘会把上一轮 boot 的整段文本写进槽；
- H178 从 `base cursor` 起算后，全篇 **0 条** `read DMA low failed`、
  0 条 `NATIVE_BUILD: H169`，旧文本问题解决；
- 但日志出现**空洞**：mount（57–62 s）、display probe/accelerator publish（~230–250 s）
  等整段缺失。原因是单个槽上限 32 块（128 KB），一次刷盘的 delta 超过上限时
  只保留最后 128 KB，前面的内容被丢弃；
- 因此仍看不到 `AGXAccelerator ok=?` / `open request`，`frames=0`。

### H179：大 delta 拆成多个连续槽（2026-11-07）

`NativeUfsProbe::h103SlotWrite()`：

1. 计算 `delta` 后按每槽 `chunkPayload = 32*4096 - 128` 分块，**依次写多个连续槽**
   （每块写槽体 + 槽头，`gH103SlotCursor` 递增，`seq` 连续），不再截断；
2. 保留 H178 的 `base cursor` 起点（只含本次 boot 产生的字节）；
3. 槽体仍用 `SHLOGS v2 … bytes=` 精确长度，pull 工具按 `seq` 拼接；
4. 构建标记 `NATIVE_BUILD: H179`。

```text
H179 kernel:  d6e14d3aac357a61214f450bf956641b92ee8fc2fd41f885be8c25ea2258a67a
H179 payload: 3bacd002715aaac57722d8e5999bf815b0ee4cc6258ac85ed2dee14fdc007319
H179 boot:    cd2bf397dad5aa20b3b397cb98e327661b904c03ff92921f521d3615c025f11d
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H179.img`（已核对）、
Mac `~/h103/boot-H179.img`、仓库 `out/cheeseburger/boot/boot-H179.img`。
手机在 TWRP，`adb reboot bootloader` → `fastboot boot` 启动（未写分区）。

判读：日志应完整覆盖 mount、display probe、accelerator publish、backboardd 匹配；
重点看 `op=match comm=backboardd d=AGXAccelerator ok=?`、`open request type=?`、
`frames=?`。

### H179 结果：日志空洞修复，AGX 仍然 ok=0（2026-11-07）

`h179-log-20261107-231807.txt`：

```text
40.074  NATIVE_UFS_LOG: base cursor=54630 size=131072
41.316  NATIVE_UFS_ACCEL: service=0xfffffff7a2d002e0 MetalPluginName=AGXMetalA10 source=arg set=1
60.368  Got boot device … / 60.9–62.3 三个卷 mount-complete     （空洞已修复）
257.004 NATIVE_DISPLAY_OPEN: … backboardd … match=1
257.489 op=match comm=backboardd d=IOAcceleratorES ok=1
257.537 NATIVE_A540_ACCEL: read key=MetalPluginName
370.847 op=match comm=backboardd d=AGXAccelerator ok=0
463.925 op=match comm=backboardd d=IOAcceleratorES ok=0
```

1. 多槽拆分生效，mount/display probe 不再丢；
2. 但注入发生在 **41.3 s**，早于我们自己的 accelerator 发布（display probe 约 60 s），
   匹配到的 `0xfffffff7a2d002e0` 可能不是我们的实例；
3. 尽管 H176 已把类更名为 `AGXAccelerator`，Apple 插件的类匹配仍 `ok=0`；
4. 463.9 s 起 `IOAcceleratorES ok=0`，说明该服务此时已不在（或不再可匹配）。

### H180：UFS 侧自检 accelerator 服务身份（2026-11-07，只加日志）

`drivers/NativeUfsProbe/NativeUfsProbe.cpp`：

1. 新增 `h103NoteAcceleratorService(tag, service)`，打印
   `class=<metaclass 名> name=<实例名> agx=<metaCast("AGXAccelerator")> refs=<retain>`；
2. 注入时先打印 `inject` 一行（确认 `MetalPluginName` 到底设到了哪个实例）；
3. 心跳每 10 拍调用 `h103ProbeAcceleratorService()` 打印一次 `probe`
   （约 10 s，门开后约 100 s），用于观察实例何时消失；
4. 构建标记 `H180`。

```text
H180 kernel:  c060e74ffaf4f6d272f225ee3e6373d4bbc44f92157d1b4992bbd4be63271842
H180 payload: 490e823a39ff8a7302adef0a7a6aa8de07285348af0915ddb69fb686009b79d9
H180 boot:    6417abe4ad2f0656e360d7ba6b524081ff63b9427130be740c06d689d192f259
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H180.img`（已核对）、
Mac `~/h103/boot-H180.img`、仓库 `out/cheeseburger/boot/boot-H180.img`。
手机在 TWRP，`adb reboot bootloader` → `fastboot boot` 启动（未写分区）。

判读：

- `inject class=… name=…` 若是 `IOGPU`/别的类，说明属性设错了对象；
- 若 `class=AGXAccelerator agx=1` 而 Apple 仍 `ok=0`，问题在插件的匹配字典
  （可能还要求 `IONameMatch` 或某个属性）；
- 若 `probe none` 在 460 s 左右出现，说明实例被释放，需要在发布后持有引用。

### H180 结果：服务身份正确，但 Apple 插件仍不匹配（2026-11-07）

`h180-log-20261107-233519.txt`：

```text
41.498  NATIVE_UFS_ACCEL: inject class=AGXAccelerator name=AGXAccelerator agx=1 refs=4
41.540  service=0xfffffff9e6704880 MetalPluginName=AGXMetalA10 source=arg set=1
41.58–192  probe class=AGXAccelerator name=AGXAccelerator agx=1 refs=4   （每 ~10 秒）
258.7  op=match … d=IOAcceleratorES ok=1 / read MetalPluginName + MetalPluginClassName
370.8  op=match … d=AGXAccelerator ok=0
371.4  op=match … d=AGXAccelerator ok=0
```

- 注入确实打在我们自己的实例上（class/name=`AGXAccelerator`、`metaCast=1`、refs=4 稳定存活）；
- 内核侧 `serviceMatching("IOAcceleratorES")` 每次都能找到它；
- 但 Apple 插件按 `IOProviderClass=AGXAccelerator` 的匹配始终 `ok=0`——同一个对象用
  `IOAcceleratorES` 能匹配、用 `AGXAccelerator` 不能。不是服务身份问题，而是该用户态
  发现路径与我们不兼容。继续在这条路上补属性收益很低。

### H181：路线 B —— 最小 nil Metal 插件（2026-11-07）

按 `NativeAdrenoMetalPlugin.mm` 注释描述的语义：插件不注册设备（返回 nil）时，
CoreAnimation 会继续使用原来的软件渲染。

1. 新增 `drivers/NativeMetal/NativeNilMetalPlugin.mm`：principal class
   `NativeNilMetalDevice : _MTLDevice`，`initWithAcceleratorPort:` 直接 `return nil`；
2. 新增 `scripts/build-nil-metal-plugin.py`：编译为 bundle、ad-hoc 签名，输出
   `build/adreno-metal-plugin/NilMetal.bundle` 与 `trust.json`（`cdhashes` 列表）；
3. 新增 `scripts/make-nil-gpu-addon.py`：把 bundle 打成 `NGPUADD2` GPU addon；
4. 新增 `scripts/add-owner-trust-hash.py`：在没有 IPSW 的机器上，把插件 CDHash 加进
   payload 现有的 trust bundle（owner 模块重建，两个 Apple 模块原样保留）；
5. payload 增加 `Payloads/kernel.macho.gpuaddon`（2600 B）与新的
   `Payloads/kernel.macho.trustcache`（61408 B）；args 改为
   `_offline-accelerator-plugin=NilMetal sheng-gpu-addon=1`；
6. 内核侧 `sheng-gpu-addon=1` 会把 `/private/var/ngpu/addons` union 到
   `/System/Library/Extensions`，CA 会加载 `NilMetal.bundle` 并拿到 nil 设备。

```text
H181 kernel:      c90532add5b930ead26c7bbb31bf2a25380af4847649e5adb7cb8d4aaf11ddc0
H181 payload:     3df7c688edd87ba5c3b8f978f42988d33dc052c25b9124d3e7c5874f1a049e0e
H181 boot:        b9bb2d918807b07c49b724311eb4e4271e696652bc6a7fe54888b18f4ce82e64
插件 CDHash:      262afd9e55b5020f4d5edbdd6376287c7e3fde9f
GPU addon:        5e6bc5990e944058787e5c77185642ebf4d979a859c7974b34207d8cda73bf46
trust bundle:     baeaf9e2a5e47fcf69581ab17bf0e593d0d9bab330f3d848b95cf30ce2757118
```

镜像：Windows `D:\\Users\\ls\\Documents\\OnePlus5_ios\\boot-H181.img`（已核对）、
Mac `~/h103/boot-H181.img`、仓库 `out/cheeseburger/boot/boot-H181.img`。
手机在 TWRP，`adb reboot bootloader` → `fastboot boot` 启动（未写分区）。

判读：

- `NATIVE_UFS_ACCEL: MetalPluginName=NilMetal`，以及 CA 之后是否读到插件
  （`read key=MetalPluginName` / principal class）；
- 若插件按预期返回 nil → CA 回退软件渲染，出现 `frames>0` / `selector=3/4/5`；
- 若加载失败（AMFI/签名）→ 日志会出现对应拒绝；若仍无帧 → 软件渲染路径也不可用，
  转 Turnip 主线。
- 注意：`zzy-native-gpu-addon-mount.patch` 只维护 `native_gpu_addon_*` 全局量，
  **不打印任何日志**，所以日志里不会有 `NATIVE_GPU_ADDON*` 行；addon 是否落地只能
  间接判断（插件是否被 CA 加载）。

### H181 上机：停在 UEFI，loader 拒绝 payload（2026-11-08）

`fastboot boot boot-H181.img` 返回 `Booting OKAY`，但进不了内核，停在 UEFI
（edk2）界面。日志窗口未写出，属于 loader 阶段拒绝，不是内核崩溃。

根因：ADT 的 `/chosen/memory-map` 里没有 `GpuAddon` 占位符，而 payload 里新增了
`Payloads/kernel.macho.gpuaddon`。`DarwinBoot.c` 的校验是：

```c
ReadFile(<kernel>.gpuaddon, ...);
if (Addon != NULL) {
  if ((AddonOffset == MAX_UINTN) || ...) { Status = EFI_COMPROMISED_DATA; goto Fail; }
}
Fail: Print(L"DARWINBOOT: boot refused: %r; firmware retained\n", Status);
```

即“文件存在但 ADT 没有占位符”= `EFI_COMPROMISED_DATA`，直接回到 UEFI 菜单。
H180 能启动是因为当时 payload 里还没有 addon 文件（`Addon == NULL` 走另一分支）。
占位符由设备仓库 `make-cheeseburger-adt.py --gpu-addon` 生成（提交 `9ad41b0`），
但投放用的 ADT 是在该选项之前生成的，从未重新生成过。

已核对（不是猜测）：

- 现有 ADT `kernel.macho.adt` 只有 `PackedRAMDisk`/`TrustCache` 占位符；
- 用 `--dram-size 0x200000000 --owned-memory-size 0x100000000 --cpu-regs
  0,1,2,3,0x100,0x101,0x102,0x103 --ipad-identity --packed-data-ramdisk
  --trust-cache --gpu-addon --root-match-volume-uuid 04769D26-...` 重新生成后，
  与旧 ADT 的结构化 diff **只有** `/chosen/memory-map` 新增 `GpuAddon`
  （random-seed 保留旧值，其余字节一致）；
- 新 trustcache 用 loader 的 `ValidTrustCaches` 规则逐条验证通过（3 模块，
  模块内 hash 严格升序）；addon 头部 `NGPUADD2`/总长/条目也符合 loader 与内核的校验。

顺带修正：之前 H96a 也出现过“停在 UEFI Shell”，原因是 `mcopy -o` 覆盖文件丢了
VFAT 长名；这次用 `mdir -/` 检查过 `kernel.macho`、`kernel.macho.adt`、
`kernel.macho.gpuaddon`、`kernel.macho.trustcache`、`unixnu.toml` 长名都在，
不是同一个问题。

### H181a：补上 GpuAddon 占位符（2026-11-08）

payload/ADT 重新打包（kernel 未变）：

```text
H181a ADT:        ce338d45ab863b17b5528fe39c0d6bb153ee4ffaf76f1f509063fdef99185703
H181a payload:    7398546624e659aeb06313de1d26e15430c4327692bf8f0b189f0c736ae52b6c
H181a boot:       61d825160ec21384220c197fed17af19d951819a00634b46320a833b7ed2ad8a
```

设备仓库同时加了防回归检查：

- `scripts/check-adt.py --require PackedRAMDisk --require TrustCache --require GpuAddon`
  检查 `/chosen/memory-map` 占位符；
- `README.md` 的 ADT 步骤改为实际使用的参数（含 `--gpu-addon`），并注明缺占位符
  会让 DarwinBoot 报 `boot refused: Compromised Data`。

### H181a 结果：进入内核，但插件路径没被看到（2026-11-08）

`H181a-log-20261108-001601.txt`（build=H181，uptime 583 s，窗口覆盖 59–967 s）：
H181a 正常进入内核并跑到用户态（SpringBoard、runningboardd、containermanager 等都在），
说明补 `GpuAddon` 占位符的判断正确。

```text
66.5   NATIVE_UFS_ACCEL: service=… MetalPluginName=NilMetal source=arg set=1
284.7  NATIVE_A540_ACCEL: read key=MetalPluginName
286.6  NATIVE_A540_ACCEL: read key=MetalPluginName
369.7  NATIVE_A540_ACCEL: read key=MetalPluginName
```

与 H180 对比，关键差异是**没有** `read key=MetalPluginClassName`，也没有
`NATIVE_IOGPU_ACCEL` / `NATIVE_FRAME`。按 `audit-target-metal-discovery.py` 审计出的
原始发现链（先读 `MetalPluginName` → 组 `/System/Library/Extensions/<name>.bundle`
→ 读 `MetalPluginClassName` → bundle/principal class），只读到插件名就停，说明
`NilMetal.bundle` 这条路径对发现流程不可见：要么 addon 文件没写进 Data，
要么 union mount 没成功。

H181a 的 payload 里没有任何可用诊断（`zzy-native-gpu-addon-mount.patch` 只维护
`native_gpu_addon_*` 全局量，不打印）。另外 298 s 有一次 SystemOS 读超时
（`disk6 … err 60`），发生在发现流程（284 s）之后，不能解释这次失败。

### H181b：给 addon 安装/union mount 加启动日志（2026-11-08）

新增 `patches/xnu/zzz-native-gpu-addon-log.patch`（在 `zzy-native-gpu-addon-mount`
之后应用，只加日志，不改行为）：

- `native_gpu_addon_install()`：拿不到 loader 的 addon 时把 `native_gpu_addon_files`
  置为 `-2`（区分“没有 handoff”和“解析失败”）；
- `native_gpu_addon_prepare()` 末尾打印一行：

```text
NATIVE_GPU_ADDON: plugin=<arg> info=<err> files=<n> written=<n> same=<n> failed=<n> error=<err> ext=<stage>/<status> daemons=<stage>/<status> wallpaper=<stage>/<status>
```

其中 `ext/daemons/wallpaper` 的 stage 含义：1=源目录查找失败、2=源目录存在、
3=mount 成功、4=封印层文件可见、5=owner 自己的文件可见；`status` 是最后错误码。
`info` 是按 `_offline-accelerator-plugin` 拼出的
`/System/Library/Extensions/<plugin>.bundle/Info.plist` 的查找结果。

```text
H181b kernel:  2472605d614744a844e82acdbca1812e5e8e24766a4b980ce61cd502ff053c5d
H181b payload: 4f801d9fb30fd786cafe3ea9f016643af95d626de7156d01b59d1d50c686a285
H181b boot:    65988f937f22bbdbe7f3862bbea163957e10c4fa968e4ed48d773778361379e8
```

判读：`files=3 written=3` 说明 addon 落地；`ext=3/0` 说明 union 生效；`info=0`
说明 CA 要的 Info.plist 在挂载后可见。若 `files=-2` → loader handoff 断了；
若 `ext=1/2` → `/private/var/ngpu/addons` 没建出来（安装失败）；若 `ext=3/2` →
mount 后看不到封印层；`info≠0` 且 `ext≥3` → union 可见但插件路径仍不对。

### H181b 结果：addon 代码根本没被执行（2026-11-08）

`H181b-log-20261108-003028.txt`（build=H181b，41–680 s）：

- `61.78  NATIVE_H82_DATA: status=0 stage=4 ro=0` → `native_owner_data_prepare()`
  成功，紧接着的 `native_gpu_addon_prepare()` 确实被调用；
- 但整份日志里**没有** `NATIVE_GPU_ADDON` 行；
- 与 H181a 对比，61.04–61.78 s 的几十行（root auth、PMRD、disk6、spec_open…）
  时间戳逐微秒完全相同。如果新增的 printf 执行过，这条时间线不可能不变。

结论：`native_gpu_addon_prepare()` 在第一行就返回了，即
`PE_parse_boot_argn("sheng-gpu-addon", &enabled, 4)` 拿到值不等于 1。
也就是说 H181/H181a 的“插件路径不可见”其实是 **addon 从未安装**。

### 根因：command line 末尾的数值参数被当成字符串

`pexpert/gen/bootargs.c` 的 `getval()`：

```c
intval = *s++ - '0';
switch (*s) {
default:
    if (!issep(*s)) { return STR; }   /* isargsep 只认空格和 tab */
}
```

我们的 args 末尾是 `… _offline-accelerator-plugin=NilMetal sheng-gpu-addon=1`，
`=1` 后面直接是字符串结束符 `'\0'`，不是分隔符 → `getval()` 返回 `STR`，
于是走 `argstrcpy2()` 把 ASCII `"1"` 写进 `uint32_t enabled`，`enabled = 0x31 = 49`，
`enabled != 1`，addon 安装与三个 union mount 全部跳过。

`_offline-accelerator-plugin=NilMetal` 之所以正常，是因为它是字符串参数（下划线
强制字符串拷贝），且字符串参数不依赖结尾分隔符。此前所有位于末尾的参数都是字符串，
所以这个坑一直没暴露。

### H182：把数值参数移到字符串参数之前（2026-11-08）

payload 的 args 末尾改为：

```text
... offline-accelerator=1 sheng-gpu-addon=1 _offline-accelerator-plugin=NilMetal
```

`sheng-gpu-addon=1` 后面是空格 → 走 NUM；字符串参数放最后不受影响。
内核保留 H181b 的 `NATIVE_GPU_ADDON` 诊断日志，只把 build 标记改为 H182。

```text
H182 kernel:  97f019808ce16bfb4ad0bf9dc53db40d1c7ba0d52162ba26222acd1d79b2a94d
H182 payload: d4c5e29d4effda069843721a9adf7efa975e8927d5723136194a1753cb4f37bb
H182 boot:    6b09328db56339723699a1f86bd291c5111199c8b6953612537a6dc503491ab7
```

判读（预期）：

```text
NATIVE_GPU_ADDON: plugin=NilMetal info=0 files=3 written=3 same=0 failed=0 error=0 ext=4/2 daemons=1/2 wallpaper=1/2
```

- `files/written=3`：addon 三个文件写进 Data；
- `info=0`：`/System/Library/Extensions/NilMetal.bundle/Info.plist` 在 union 后可见；
- `ext=4/2`：union 成功且封印层可见，2 是 `NativeAdrenoMetal.bundle` 自检路径（我们叫
  NilMetal），属预期；
- `daemons=1/2`、`wallpaper=1/2`：这两个 overlay 的源目录本就不存在，属预期。

之后看 CA 是否继续读 `MetalPluginClassName`、是否出现 `frames>0` / `selector=3/4/5`。

### H182b 结果：日志窗口本身不可靠（2026-11-08）

H182b 的 `probe` 行同样没有出现，但这次逐槽核对后发现**不能据此下结论**：

- 窗口里 `mount-complete volume OwnerData` 出现 118 次，大量文本逐字节重复；
- header 的 `msg` 区（blocks 1..256）与 H182 的窗口**完全一致**（722 个时间戳、
  首尾 `467.819743`/`527.258917` 都相同），说明该区没有随这次启动重写；
- H182b 的 22 个槽中，槽 0..20 是本次启动的增量（含本次独有的
  `service=0xfffffff60dd00ac0`），但**没有任何 OwnerData/H82 行**；槽 21 的
  97 KB 大块只含旧文本（不含本次独有指针），却被并入报告——报告里的
  “61.78 s H82”就是这类旧数据；
- 槽 0..20 一路到 508 s 都有 launchd 子进程、backboardd、SpringBoard，
  说明系统确实起来了，但 Data mount 那一刻的 console 输出没有被增量捕获。

结论：`h103-log-pull.py` 的增量槽在这几次启动里会漏掉 Data mount 附近的整段
console（同时把旧槽当成本次启动），所以“没有 `NATIVE_GPU_ADDON`”**不能**证明
addon 代码没跑。需要一条不依赖 mount 时 console 的通道。

### H183：用 UFS 心跳读取 addon 状态（2026-11-08）

- 内核补丁 `zzz-native-gpu-addon-log.patch` 增加 `native_gpu_addon_calls`，
  在 `native_gpu_addon_prepare()` 入口自增（其余诊断保留）；
- UFS 驱动 `NativeUfsProbe` 的心跳行 `NATIVE_UFS_ALIVE` 追加：

```text
addon=<files>/<written>/<same>/<failed>/<error>/<calls>
owner=<stage>/<status>
ext=<stage>/<status> dm=<stage>/<status> wp=<stage>/<status>
```

心跳行在每次抓取里都稳定出现（43 s 起约每 10–60 s 一条），不再依赖 Data mount
时刻的 console 是否被写入槽。

```text
H183 kernel:  c6143f2df39ebb0c1602195e7a04face0ecc7711875b5bc0e2fa8bfbeba6433d
H183 payload: 830cb0cf16e7b8ef9061a8741e5dcaddb2f47adbaaee6253968d12d975fc6681
H183 boot:    01d72c8f1b38477f0043c79ce1bcafbbea67c022955abc66a8a60e1809761722
```

判读：`calls=0` → 函数没被调用；`calls≥1, files=-2` → loader handoff 断了；
`files=3, written=3` → addon 落地；`ext=4/2` → union 生效（2 是
`NativeAdrenoMetal` 自检路径，属预期）；`files=3` 且 `ext=2/...` → mount 失败。

### H183 结果：心跳通道定位到真正的失败点（2026-11-08）

心跳行给出了确定答案：

```text
NATIVE_UFS_ALIVE: ... addon=3/0/0/3/2/1 owner=4/0 ext=1/2 dm=1/2 wp=1/2
```

按 `addon=<files>/<written>/<same>/<failed>/<error>/<calls>` 展开：

- `calls=1`：`native_gpu_addon_prepare()` 被调用；
- `files=3`：**boot-arg 门禁通过了**，addon 安装流程真的开始执行（H182 把
  `sheng-gpu-addon=1` 移到字符串参数之前是有效的）；
- `written=0 same=0 failed=3 error=2 (ENOENT)`：三个文件全部写失败；
- `owner=4/0`：Data volume 正常挂载（stage 4、status 0）；
- `ext=1/2 dm=1/2 wp=1/2`：三个 union mount 都停在 stage 1（源目录
  `vnode_lookup` 失败），status 2 = `ENOENT`。

根因：Data volume 里**没有 `/private/var/ngpu` 目录**，而
`native_gpu_addon_parents()` 的循环从
`sizeof("/private/var/ngpu/") - 1` 开始，只创建 `ngpu` **下面**的目录，从不创建
`ngpu` 本身；于是写文件 ENOENT，`/private/var/ngpu/addons` 也不存在，union mount
的源目录查找同样 ENOENT。

### H184：连同 /private/var/ngpu 一起创建（2026-11-08）

`zzy-native-gpu-addon-mount.patch` 的父目录循环起点改为
`sizeof("/private/var/") - 1`，即把 `/private/var/ngpu` 也纳入创建；注释同步说明
这次 H183 心跳的失败码。诊断（probe/汇总 printf、calls 计数、心跳字段）保留。

```text
H184 kernel:  f307023e766f8ee102214185c4cb59214e0abcde0a33da13d2b926c76cbe0fff
H184 payload: 9cf47e31110e70f711dfd3262d5d465fc09c719952b552d7ba47efb805a14cf3
H184 boot:    8f9ee990ce9f35795d2f1133ef264c7a14e781e18773db8b2965c4efb047179c
```

判读：预期心跳变为
`addon=3/3/0/0/0/1 … ext=4/2 dm=1/2 wp=1/2`（`ext` 的 status 2 是
`NativeAdrenoMetal.bundle` 自检路径，属预期）。若 `ext=3/...` 则 mount 本身被拒，
需要看 bindfs 的返回码。

### H184 结果：addon 与 union mount 都成功，但 backboardd 崩了（2026-11-08）

心跳：

```text
addon=3/3/0/0/0/1  owner=4/0  ext=4/2  dm=1/2  wp=1/2
```

- `files=3 written=3 failed=0 error=0`：三个文件成功写进 Data volume；
- `ext=4/2`：`/System/Library/Extensions` 的 union mount 生效（stage 4 =
  封印层可见；status 2 是 `NativeAdrenoMetal` 自检路径，属预期）；
- `dm/wp=1/2`：这两个 overlay 的源目录本就不存在，属预期。

随后 CA 的发现流程第一次走到了插件：

```text
248.10  read key=MetalPluginName
248.13  read key=MetalPluginClassName
248.16  read key=IOUserServiceProperties
248.21  NATIVE_H66_FCNTL / NATIVE_CACHE_SIG（新镜像被处理）
248.32  NATIVE_TRAP: pid=55 comm=backboardd exc=1 code=0x1 sig=11
```

backboardd 在读完类名后约 80 ms **SIGSEGV**，并从 248 s 起反复崩溃重启
（357/375/394/407/431/457/488/529/566/649 s）。对照 H180（Apple 插件、无 union）
在同样读取 `MetalPluginClassName` 后**没有崩溃**，H181–H183（插件不可见）也没有
backboardd trap。所以崩溃发生在“从 union 加载我们自己的插件”这一步。

两种可能：(1) 插件代码/返回 nil 导致；(2) dyld 从 bindfs union mmap 可执行文件
失败。H185 用 stderr 轨迹区分。

### H185：插件加载/初始化轨迹（2026-11-08）

`NativeNilMetalPlugin.mm` 增加：

- `__attribute__((constructor))`：`NILMETAL: ctor pid=…`
- `initWithAcceleratorPort:`：`NILMETAL: init port=… self=…`

插件的 CDHash 变为 `1f684178cf193da5ee2db557106184aa68001259`，trustcache 用
`add-owner-trust-hash.py` 在 H184 的 bundle 基础上重建 owner 模块（两个 Apple
模块原样保留）。内核未变（标记仍是 H184）。

```text
H185 payload: 48356ad26c9ca9e4c5c448b0c9cdf02f04a8349b047585a341974c05d6c7f99e
H185 boot:    34ebf2bef94429eb526aace32cae11e47899a3bf925b452f6eb8acfd6b6eaae4
GPU addon:    94266978487d150486fc90074ce6b1c7c82ac515aac42a22bdd3646e432d4522
trust bundle: 5653a354b2ea82cae14a4700b6faf82edd75a1c00407e3b69bdf074734cb89b1
插件 CDHash:  1f684178cf193da5ee2db557106184aa68001259
```

判读：日志里出现 `NILMETAL: ctor` → 镜像已映射；再出现 `NILMETAL: init` → 我们的
方法被调用。若只有 ctor、没有 init → 崩溃在 `principalClass`/类检查；
若两条都没有 → 崩溃在 dlopen/mmap（bindfs 加载可执行文件的问题）。

### H185 结果：插件在进入代码前就崩了（2026-11-08）

`h103log-h185.bin`：整份日志里 **`NILMETAL: ctor` / `NILMETAL: init` 都没有**
（连 constructor 都没跑），但 backboardd 仍有 5 次 `sig=11`，`MetalPluginClassName`
读到 1 次。说明崩溃发生在 dlopen/mmap/AMFI 阶段，既不是我们的方法，也不是“返回 nil”。

对照 `build-adreno-metal-plugin.py` 找到差异：参考脚本签名时带
`--pagesize 4096` 并断言 `Page size=4096`；`build-nil-metal-plugin.py` 当时只用了
`codesign -s -`。签名页大小不匹配时，AMFI 会判定代码页无效并在入口前让进程崩，
正好对应“没有 ctor、只有 SIGSEGV”。

### H186：插件按 4 KiB 页签名（2026-11-08）

`build-nil-metal-plugin.py` 改为：

```sh
codesign --force --sign - --pagesize 4096 --identifier org.blu-sharky.NilMetal NilMetal.bundle
codesign --verify --strict NilMetal.bundle
# 断言 codesign -d --verbose=4 输出 Page size=4096
```

新 CDHash `d25aceb59a2fd6420a0f49209f3ec0dde574b696`；trustcache 与 addon 随之重建。
内核未变（标记仍是 H184）。

```text
H186 payload: 59edbb4e42f4cf0018ba1224d58a5ac079f098df61ddf42c9cf62c6b71925e35
H186 boot:    c61ab9ef38bec63dda88b8558d2dbf651b4d210d51d04d2944c6f29dbf8b622a
GPU addon:    a4358d9574507640b6671e727d8ae78386336bcb837d018e7e5c54d361857a60
trust bundle: 701bebaa4d2cc324b88ba06e882c2db6af91d2ef3cecbefa5c2f72ba26dde023
插件 CDHash:  d25aceb59a2fd6420a0f49209f3ec0dde574b696
```

判读：出现 `NILMETAL: ctor` → 页大小就是原因；只有 ctor 没有 init → 崩溃在
principalClass/类检查；两条都没有 → 需要改用自建 daemon 从 APFS 路径 dlopen 同一
bundle 做对照（排除 bindfs 只读联合挂载的 mmap 问题）。

### H186 结果：仍无 ctor，但 stderr 不可见（2026-11-08）

H186 换成 4 KiB 页签名后，backboardd 的崩溃位置不变（260.82 s、`sig=11`，紧跟在
`NATIVE_CACHE_SIG: blob=66384 size=18816` 之后），日志里仍没有 `NILMETAL` 字样。
但这里有一个观测陷阱：launchd 默认把作业的 stderr 丢到 `/dev/null`，所以
“没有 ctor”**不能**证明镜像没加载。需要把轨迹写到内核控制台。

### H187：插件直接写 /dev/console（2026-11-08）

插件改为 `fopen("/dev/console","w")` 输出：

```text
NILMETAL: ctor pid=…
NILMETAL: init port=… self=…
```

这样输出必然进入启动日志。签名仍是 4 KiB 页（CDHash
`91c0b2df6af26eb0575b2953160b431c410d428a`），trustcache/addon 已重建，内核未变。

```text
H187 payload: 0511c0976bdeb3d2c379d96d994d9f31f70037459f24f84cf67ebc8e6bcffbc1
H187 boot:    200caf5076f5e68ed401377e830aaca4d1e2c80bfd190f0abef5ad56248ad948
插件 CDHash:  91c0b2df6af26eb0575b2953160b431c410d428a
```

判读：有 `ctor` → 镜像加载成功，崩溃在返回 nil 之后（CA/Metal 侧）；有 `ctor` 没有
`init` → 崩溃在 principalClass/类检查；两者都没有 → dyld/mmap 阶段失败，下一步用
自建 daemon 分别从 APFS 路径和 union 路径 dlopen 同一 bundle 做对照。

### H187 结果：/dev/console 也不可见（2026-11-08）

H187 用 `fopen("/dev/console")` 输出，日志里仍没有 `NILMETAL`。但这个移植里
用户态的 `/dev/console` 写入不进入内核 msgbuf（日志里的用户态内容都是 os_log 或
内核消息），所以仍不能证明插件没执行。需要一条**内核一定记录**的通道。

### H188：用退出码证明 constructor 是否执行（2026-11-08）

插件 constructor 直接 `_exit(42)`：

- 镜像真的被 dlopen 并执行 → 内核记录
  `NATIVE_EXIT: pid=55 comm=backboardd status=0x2a`；
- 仍然只有 `NATIVE_TRAP … sig=11`、没有 `status=0x2a` → 镜像在 dyld/mmap/AMFI
  阶段就死了，代码从未执行。

```text
H188 payload: 1f0020327648418ee7162f00a9e5f3150412ec99b88b24e94ad739279b32c4e4
H188 boot:    ad288bf1cd477b3dc875d3c02e1a08f757fed640bf4091f4cc25845845c94b01
插件 CDHash:  009e238a432bb9805dfbf32d881767be940e606d
```

这是纯诊断镜像：无论结果如何，backboardd 都会在加载插件时退出，系统不会进入可用的
图形状态。

### H188 结果：镜像确实被加载并执行（2026-11-08）

日志里出现：

```text
NATIVE_EXIT: pid=55 ppid=1 comm=backboardd status=0x2a00 ns=0 code=0x0
```

`status=0x2a00`、`ns=0` 就是 constructor 里的 `_exit(42)`；随后每个 backboardd
实例（131、137、143…）都在加载插件时以 42 退出。**这证明**：

- union 挂载、trust cache、4 KiB 页签名都正常；
- 插件 bundle 的镜像被 dlopen 且 constructor 执行；
- H184–H186 的 `sig=11` 发生在插件代码开始执行**之后**，不是 dyld/mmap 或签名问题。

### H189：把退出码移进 initWithAcceleratorPort（2026-11-08）

constructor 正常返回，`initWithAcceleratorPort:` 一进入就 `_exit(43)`：

- 出现 `status=0x2b00` → 类检查和消息发送都通过，H184–H186 的崩溃发生在返回
  nil **之后**（CA/Metal 不接受 nil 设备），路线 B 到此为止；
- 没有 `0x2b00`、仍是 `sig=11` → 崩溃在 constructor 与 init 之间
  （`principalClass` / `classNamed:` / `isSubclassOfClass:`），是可修的类声明问题。

```text
H189 payload: 9ff5b70ecdb456f4d175b0b530a123b95fd399cd11d553c8c280e39cdb4aa90e
H189 boot:    c5a3c3c55b9737a6df03a7e692b7e513be310df6100c1d4200be2000a3707005
插件 CDHash:  0932f6fad2eae877f800cc5bdac14a78aec81bf0
```

### H189 结果：设备请求确实被调用（2026-11-08）

```text
NATIVE_EXIT: pid=55 ppid=1 comm=backboardd status=0x2b00 ns=0 code=0x0
```

`0x2b00` 是 `initWithAcceleratorPort:` 里的 `_exit(43)`（共 12 次），而且这次启动
**`backboardd exc=1` 为 0**。结合 H188（constructor 执行）可以确定链路：

1. 镜像加载 ✔
2. constructor 执行 ✔
3. `initWithAcceleratorPort:` 被调用 ✔
4. H184–H186 的 `sig=11` 在其后

H189 在 `[self release]` 之前退出，所以剩下的可疑点是：`[self release]` 会调用
`_MTLDevice` 的 `-dealloc`，而我们的实例从未执行 `[super init]`，Metal 的 dealloc
可能访问未初始化的内部字段。

### H190：返回 nil 但不释放对象（2026-11-08）

`initWithAcceleratorPort:` 直接 `return nil;`，不调用 `[self release]`
（每次泄漏一个实例，可接受）。若崩溃消失，则确认是 `_MTLDevice` 的 dealloc；
随后观察 CA 是否继续执行、是否出现 `frames>0`。

```text
H190 payload: 9c0f8e772540f068cf90474d604048c73937612a82d511a1b6309324738d6897
H190 boot:    83dee6404131b18a02d9ada579735c1cfcf97fbe6dd4ef3ef622b21a3196bfb9
插件 CDHash:  efe1dc125d4a5b471ca02628017f806effb1266b
```

### H190 结果：崩溃消失，但仍无帧（2026-11-08）

按本次启动（boot id `28a79573`，uptime 5–756 s）的**新鲜槽**统计：

```text
addon=3/3/0/0/0/1 owner=4/0 ext=4/2 dm=1/2 wp=1/2
comm=backboardd exc=1 : 0
status=0x2b00          : 0     （日志里的 0x2b00 全部来自 H189 的旧槽）
MetalPluginClassName   : 1
NATIVE_FRAME           : 1  → event=5 flags=fd7f600f client=1 xfer=0 frames=0
NATIVE_DISPLAY_OPEN    : 13（backboardd match=1）
NATIVE_LEGACY: client enter pid=55 comm=backboardd type=0
selector=3/4/5         : 0
frames>0               : 0
```

结论：

1. **崩溃根因确认**：`[self release]` 会调用 `_MTLDevice` 的 `-dealloc`，而我们的实例
   从未执行 `[super init]`；改为直接 `return nil`（不释放）后 backboardd 不再崩溃，
   系统稳定跑到 1000 s 以上。
2. 路线 B 到此为止：插件返回 nil 后 CA 保持存活、能拿到显示 provider 的用户客户端，
   但 `frames=0`、没有 `selector=3/4/5`。**nil 设备并不会让 CA 回退到能出帧的软件
   渲染路径**。
3. 仍然有效的成果：GPU addon 安装、`/System/Library/Extensions` union mount、
   4 KiB 页 ad-hoc 签名 + trust cache 注入、插件在 backboardd 内的加载与类调用，
   这条链路已经全部打通，可直接用于真正的 Metal 驱动。

后续方向：路线 C —— 用仓库里已有的 `NativeAdrenoMetalPlugin` + Turnip/Mesa 构建真实
的 Metal 设备（`build-adreno-metal-plugin.py` 已有完整流程），通过同一条 addon/union
通道投放。

### 路线 C：真实 Adreno Metal 插件构建成功并投放（2026-11-08）

H190 之后转向路线 C，用仓库已有的 `NativeAdrenoMetal` + Turnip/Mesa 构建真实 Metal 设备。
Mac 构建机（13th Gen Intel i5，macOS 15.8.2）原本缺少整套工具链，本次补齐：

- Python 3.12（uv 安装到 `.cache/mesa-venv`）+ meson/ninja/cmake + packaging/mako/pyyaml；
- bison 3.8.2（pin 的 tarball，装到 `.cache/mesa-tools`）；
- glslang（vulkan-sdk-1.4.328.1）与 shaderc/SPIRV-Tools（glslc、spirv-val），装到 `.cache/mesa-tools`；
- Mesa 稀疏克隆到 `.cache/mesa-work`，checkout pin `85fda3b3640` 并应用 8 个记录补丁；
- rustup + Rust 1.98.0（含 `aarch64-apple-ios` target）；metal2vulkan 克隆到
  `.cache/gpu-reference/metal2vulkan`（pin `720ef1ce`，`core.abbrev=7` 才能通过源码校验）。

构建结果：

```text
Turnip (ios)   build/mesa-tu-ios/src/freedreno/vulkan/libvulkan_freedreno.dylib  17,886,640 B
Turnip (host)  build/mesa-tu/src/freedreno/vulkan/libvulkan_freedreno.dylib
bridge (ios)   build/native-metal-bridge/ios/libnative_metal_bridge.a
plugin CDHash  cf9d9f4626d0644d3fc0a227f8fbabd8fbac5826
daemon CDHash  0b158329cb994b71f60f8eabaf3133d3d1760435
turnip CDHash  39a625607e3f916d6763f964fc61da74bf3895d1
```

两个构建脚本的改动：

- `build-adreno-metal-plugin.py`：`gen-turnip-replay.py` 需要 **arm64 主机**（它把 AArch64
  内核源码编到主机上并运行）。Intel Mac 上改为失败降级——`TurnipReplay.h` 本来就是可选
  （`__has_include`），插件照常构建；
- 新增 `scripts/pack-adreno-addon.py`：`make-gpu-addon.py` 把目录名写死为
  `NativeAdrenoMetal.bundle`（17 字符），而 `_offline-accelerator-plugin` 最多拷贝 16 字符，
  所以投放目录改用 `NativeAdreno.bundle`，bundle 内 `CFBundleExecutable` 仍是
  `NativeAdrenoMetal`。

payload 组装：

- addon 12,125,208 B：`addons/NativeAdreno.bundle/**`（含 `libvulkan_freedreno.dylib`）、
  `bin/adrenoprobed`、`daemons/*.plist`；
- trust bundle 同时加入 plugin/daemon/turnip 三个 CDHash（两个 Apple 模块原样保留）；
- args：`_offline-accelerator-plugin=NativeAdreno`（其余不变）；
- 内核沿用 H184 构建（带 addon 心跳诊断）。

```text
H191 payload: 5c1f697b9fa7ea401beab08290bdafb72197be82e1dc2b9e4cd3923840b0d5dd
H191 boot:    9f08a70a7056385273ca7488e57090a7af5e43ca71e2913d7fe9862ec80288cb
```

判读：心跳 `addon=8/8/0/0/0/1 ext=4/2` 表示插件/daemon/Turnip 已落地；随后看
CA 是否加载 `NativeAdreno.bundle`、是否出现 `NILMETAL` 之外的插件日志，以及
backboardd 是否打开 AGX user client、是否出现帧。

### H191 结果：真实插件已投放，但设备仍未建立（2026-11-08）

按本次启动（boot id `88c649c3`，uptime 5–712 s）的新鲜槽统计：

```text
addon=8/8/0/0/0/1  owner=4/0  ext=4/2  dm=5/0  wp=1/2
comm=backboardd exc=1 : 0
MetalPluginClassName   : 1
MetalPluginName=NativeAdreno source=arg set=1
NATIVE_FRAME           : event=5 client=1 xfer=0 frames=0
adrenoprobed           : 0   （daemon 无 IOLog，无法从内核日志判断是否启动）
```

- 8 个 addon 文件全部落地（bundle + Turnip dylib + advert daemon + 3 个 plist）；
- `ext=4/2`：Extensions overlay 正常；**`dm=5/0`：LaunchDaemons overlay 也到了
  stage 5**（我方自己的 plist 可见），这是这次新打通的一条通道；
- backboardd 不崩，CA 读到了类名，但没有任何 `op=open ... AGX` 记录，也没有帧。

结论：**用户态半边已经完整**（插件、Turnip、签名、trust cache、addon、两个 overlay），
但 `initWithAcceleratorPort:` 里真正的 `IOGPUDeviceCreateWithAPIProperty` 需要内核
提供一个能 `IOServiceOpen` 的 AGX/Adreno user client；当前内核里只有
`NATIVE_UFS_ACCEL` 注入的 `AGXAccelerator` 影子服务（没有 user client 实现），
所以设备建立失败，CA 仍然没有 Metal 设备。

### 下一里程碑：内核侧 NativeAdreno（未开始）

仓库里已有完整驱动（`drivers/NativeAdreno`，构建开关 `XNU_NATIVE_ADRENO=1`，
归档 `build/native-adreno/libNativeAdreno.a`），但在 cheeseburger 上被关闭。启用需要：

1. GPU 固件（`scripts/data/adreno-inputs.json` 的 `firmware`，用
   `fetch-adreno-inputs.py` 拉取）；
2. GPU 电源/时钟域（Sheng PMGR 的 CX/GX；ADT 生成器的 `--gpu` 目前只是引用节点，
   不做硬件初始化）；
3. SMMU（`kits/ArmSmmu4K`）与 GMU 冷启动（`NativeAdrenoGmuContextBringup`）；
4. 在板级 probe 里按顺序调用，并通过 addon 已打通的通道验证。

这是独立的大里程碑，不是本轮能顺手完成的改动。

### H192：A540 路线里程碑 1 —— accelerator user client 应答 ABI（2026-11-08）

按 A540（a5xx）重做的第一个里程碑：不改服务发布流程，只把
`NativeA540AcceleratorProbe.cpp` 里的 `NativeAcceleratorClient` 从空壳换成能应答
native-Adreno ABI 子集的实现：

- `externalMethod()` 识别隧道头 `'NTNL'`（0x4e544e4c），对 `kProbe` 返回成功，
  让用户态测试的 selector 探测通过（selector 0 被选中）；
- `Query`：`abi_version=1`、GPU VA 32 位、PA 40 位、单 BO ≤ 256 MiB；
- `GetDeviceInfo`：`chip_id=0x05040000`（A540/a5xx 族，占位值）、VA 窗口
  `0x10000000`+`0x10000000`；
- `GetStatus` / `GetTimestamp` / `SetMetadata`：`SetMetadata` 的文本直接
  `IOLog("NATIVE_A540_ABI: report %s")`，这样用户态测试的每一步结果都能从启动日志读到；
- `BoAlloc` 及之后的方法返回 `kIOReturnUnsupported`，让测试停在“已到驱动”的位置而不是
  打开就失败。

构建注意：accelerator 对象属于 legacy display 归档（H173 的敏感路径），本次
`build-op5-legacy-display.py` 正常重建并通过归档哈希资格检查；为防 H173 式 PAC panic，
保留 H191 镜像作为回退。

```text
H192 kernel:  a50fb8ff3ac8f28d3b48769f21a347d8e0b1fd1339e989e06d1daf9bbaad8e99
H192 payload: ee0337eecda00c6cb0c389311226d065481f40246eca95b07ed65e543b76fa2a
H192 boot:    e05516fd3475a7bb964ace5b6a67c6bb53eb13af4aebd0aeaabf0c0b5d50b01b
```

判读：日志应出现 `NATIVE_A540_ACCEL: user client type=16711 granted`
（0x4147）与 `NATIVE_A540_ABI: report <进程> s<步骤> e<错误> …`；只要 report 行出现，
就证明 `IOServiceOpen` + 隧道 + Query/GetDeviceInfo + SetMetadata 全线打通。

### H192 结果：镜像已加载，但测试线程没启动（2026-11-08）

按本次启动（boot `2b938e4f`，uptime 5–526 s）的新鲜槽统计：

```text
addon=8/8/0/0/0/1 owner=4/0 ext=4/2 dm=5/0 wp=1/2
backboardd exc=1 : 0            （没有 H173 式 panic）
MetalPluginClassName : 2        （261.69、263.10 两轮）
NATIVE_CACHE_SIG: blob=21529520 size=186512   （261.79，插件镜像被 dlopen）
NATIVE_A540_ABI: report : 0
NATIVE_A540_ACCEL: open request / user client : 0
```

也就是说：accelerator 服务正常、插件镜像被成功映射、CA 读到了类名并调用
`initWithAcceleratorPort:`，但用户态测试线程没有发出任何 `IOServiceOpen`。

根因：Adreno 插件（与 nil 插件不同）在 `initWithAcceleratorPort:` 里先执行
`self = [super init];`，而 `_MTLDevice` 的 `-init` 不是 NSObject 初始化；对插件自建
实例返回 nil，方法因此在启动测试线程之前就返回了。

### H193：测试路径跳过 `[super init]`（2026-11-08）

该对象只用于承载调用、从不作为 device 使用，所以测试路径直接跳过 superclass init
（published 路径不变）。插件/daemon/Turnip 重新 4 KiB 签名，CDHash：

```text
plugin  280cbf8ce6e11ab491a5a9eaa8db004645469ca6
daemon  f8b5856743c5cff102970637a48eacf8a260cb05
turnip  39a625607e3f916d6763f964fc61da74bf3895d1
```

```text
H193 payload: 835f00e629eb6d0646c723b64d87ed39534970074d666fc7bf680c671425ea4b
H193 boot:    b340d85ae878317e37590782fe34fcf743d05c58538b075f65bb33a327190297
```

内核沿用 H192 构建（标记 H192）。判读：应出现
`NATIVE_A540_ACCEL: open request type=16711`、`user client … granted` 以及
`NATIVE_A540_ABI: report …`。

### H193 结果：init 往下走了，但线程/端口保活崩溃（2026-11-08）

去掉 `[super init]` 后（boot `2b9e96d3`）：

- 插件镜像仍在 274.21 s 被 dlopen（`NATIVE_CACHE_SIG blob=21529520`）；
- 但 **`backboardd exc=1` 出现 9 次**，首次在 274.226 s（镜像映射后约 16 ms），
  `sig=11`；
- 仍然没有 `IOServiceOpen`，也就是崩溃发生在上游测试路径的
  `IOObjectRetain` + `pthread_create` + 线程内重新查找服务这一段，尚未到 `gpu.mark(1)`。

### H194：测试改为在 init 内联运行（2026-11-08）

我们的里程碑 1 驱动所有 ABI 方法立即返回、不会阻塞，所以不需要上游那套
“后台线程 + 额外端口引用 + 线程内重新查找”结构。测试路径改为直接
`adrenoUserTest(port, getprogname())`，published 路径不变。

```text
plugin  cea22be3cd1a0220dc7dd9c998b91e74ad266238
daemon  38b3fd827565e631cd67270f0db76ff62fb98067
H194 payload: 67696b84070f1bac06545bf277745902c61858fb4bb4af9c0f7da4aabd8c0597
H194 boot:    7a6a40d485b6e23bf30b1654c9c3e951e3cc334784f9288f49bc9b68cc93c8be
```

内核沿用 H192（标记 H192）。判读：应出现 `NATIVE_A540_ACCEL: open request type=16711`
与 `NATIVE_A540_ABI: report …`；若仍崩溃，崩溃点就已经进入测试本身（selector 探测/ABI
调用），可从 ABI 行定位。

### H194 结果：内联测试跑起来了，但 MACF 按类名拒绝（2026-11-08）

boot `2b9cc4c2`：`open request` / `user client … granted` 共 23 次，说明内联测试
真的打开了服务并开始探测（marks 1/2 都出现了），但随后：

```text
266.211  IOUC NativeAcceleratorClient failed MACF in process pid 55, backboardd
266.386  NATIVE_A540_ACCEL: open request type=16711
266.412  NATIVE_A540_ACCEL: user client type=16711 granted
266.439  IOUC NativeAcceleratorClient failed MACF in process pid 55, backboardd
266.582  NATIVE_A540_ACCEL: open request type=1095192321   (mark 0x4f01 = 打开失败)
```

内核侧 `newUserClient` 成功，但**沙箱 MACF 按用户客户端类名拒绝**，所以用户态
`IOServiceOpen` 失败。上游 `NativeAdrenoPublish.cpp` 正是因此把连接类命名为
`AGXDeviceUserClient`（原版 profile 只放行这个类名；探针 daemon 的 entitlement 也是它）。

### H195：A540 用户客户端改名 AGXDeviceUserClient（2026-11-08）

`NativeAcceleratorClient` → `AGXDeviceUserClient`（9 处），display 归档正常重建，
内核标记 H195。

```text
H195 kernel:  8c06aba56d6def317fa1e18e21ac23c9027dfbc5bd1e8d5eeee41fd342c8ea88
H195 payload: 9d4152ebff8575f8bdf450f4d8c25d3fd828fe1b69b98fe40ef937b57d12a048
H195 boot:    d0605972f5d2bdbd311e2dbeb12266351c056963ab6f5b3e71f5f5484b9ce84c
```

判读：`failed MACF` 应消失；`IOServiceOpen(0x4147)` 返回成功，测试进入 selector
探测，随后出现 `NATIVE_A540_ABI: report …`。

### H195 结果：backboardd 的 open 没到 newUserClient（2026-11-08）

boot `2b9a5a37`：

- MACF 拒绝只剩 `mediaserverd`（7 次），**backboardd 不再被 MACF 拒绝**；
- backboardd 在 266.65 s 完成匹配/读键/映射插件（`blob=21529504`），326.234 s 有一次
  `op=open comm=backboardd cls=AGXAccelerator`，但**没有对应的 `open request` 内核日志**
  —— 也就是说这次 open 没有走到我们的 `newUserClient`；
- 没有 `NATIVE_A540_ABI: report`。

日志噪声（槽合并/截断）让判断困难，需要进程级入口日志。

### H196：记录请求者与 ABI 方法入口（2026-11-08）

`NativeA540AcceleratorProbe.cpp`：

- `makeClient` 打印 `open request type=… comm=<进程名>`（`proc_selfname`）；
- `externalMethod` 前 24 次打印 `method=… selector=… in=… comm=<进程名>`。

这样一次启动就能确定：backboardd 的 open 是否到达内核、隧道方法是否被调用。

```text
H196 kernel:  550344009317f0abcd305f63440cd2097b2b9f1aa90cf67033303a410582aa3a
H196 payload: 55e4b26546a9cc38072647975056bedd34ef6f8d3307c2f35542de7fbd574c9d
H196 boot:    12d4de02c7c514a6007a3098482bfd66726b50d3d5dfe9ede32e05dc9e465eff
```

### H196 结果：open 到了内核，但 MACF 仍拒绝 backboardd（2026-11-08）

新入口日志（boot？H196，日志窗口）：

```text
268.126  NATIVE_A540_ACCEL: open request type=1095229440 comm=backboardd
268.250  IOUC AGXDeviceUserClient failed MACF in process pid 55, backboardd
340.502  open request type=16711 comm=backboardd          （主连接，0x4147）
340.502  IOUC AGXDeviceUserClient failed MACF … backboardd
NATIVE_A540_ABI: method= : 0
```

- backboardd 的 open **确实到达内核并创建了客户端**；
- 但 MACF `iokit-open-user-client` 仍然拒绝（14 次），用户态 open 返回失败，
  `externalMethod` 一次都没被调用。

名字本身不是充分条件；仓库里已有 `patches/xnu/zzw-native-adreno-sandbox-grant.patch`：
服务带 `NativeSandboxGrantProcess` 属性且进程名匹配时绕过该 MACF 判定。

### H197：accelerator 服务授予 backboardd 用户客户端（2026-11-08）

stub 的 `start()` 增加 `setProperty("NativeSandboxGrantProcess", "backboardd")`
（与上游 render server 授权一致）。

```text
H197 kernel:  7085d8b6b89bac3c33418428bd625e8ca5fe492e60c7dca0c03e3dbd1bb197fe
H197 payload: b5bb0e193c78a4a9d806805f925837de1c67dc8a2580ef0f9488f2c61748ca95
H197 boot:    6a190864c2f795f38c61fb7179f97dacd4b5f0d45db3f762e004db7e7527d64c
```

判读：`failed MACF … backboardd` 应消失，`NATIVE_A540_ABI: method=…` 应出现，
随后是 `NATIVE_A540_ABI: report …`。

### H197 结果：授权只覆盖了部分实例（2026-11-08）

`NativeSandboxGrantProcess=backboardd` 生效但只覆盖部分打开：

```text
256/260/401 s  NATIVE_DISPLAY_OPEN: service=AGXAccelerator process=backboardd grant=backboardd match=1
260.100        open request type=1095172097 comm=backboardd → 无 MACF 拒绝
340/349 s      IOUC AGXDeviceUserClient failed MACF … backboardd（这些时刻没有 grant 日志）
```

也就是被打开的是**另一个 AGXAccelerator 实例**（服务被重新发布过），它没有该属性；
`NATIVE_A540_ABI: method=` 仍为 0。

### H198：在 UFS 注入点同样设置授权（2026-11-08）

UFS 驱动本来就会对 CA 会匹配到的 service 设置 `MetalPluginName`；同一处再设置
`NativeSandboxGrantProcess=backboardd`，保证“实际被打开的那个实例”一定带授权。

```text
H198 kernel:  83d73118383b084b1da4d6ddfbb64f971e1c1819382bdc3b2f62541ac4c3eb5c
H198 payload: 1db4a9445b9d4f4c63500e2ef8288fc661ed26c9ada69ef8a3376b3cd3f1eaa3
H198 boot:    431c306d089fe1a9a071b6ecc22d6f93d60c20d065adc912bfe23ca1d79b584b
```

判读：backboardd 的 `failed MACF` 应完全消失，`NATIVE_A540_ABI: method=…` 与
`report …` 应出现。

### H198 结果：授权覆盖不完整（2026-11-08）

```text
388.7-389.0  service=AGXAccelerator process=backboardd grant=backboardd match=1（多次）
401.040      open request mark1 → granted
401.041      IOUC AGXDeviceUserClient failed MACF … backboardd（这次没有 grant 日志）
401.0416     open request type=16711（主连接）→ granted
401.0418     IOUC … failed MACF
401.042      open request 0x4f01（打开失败标记）
406.4        grant match=1 又出现
```

部分实例带授权、部分不带，主连接时好时坏；`NATIVE_A540_ABI: method=` 仍为 0。
另外确认：探针 daemon `adrenoprobed` 从未 exec（日志里 0 次），原版
`IOMFB_FDR_Loader` 仍在运行（310 次），说明 launchd 用的是封印卷里的 plist，
没有使用 overlay 中同名替换的版本。

阶段文档：`plans/oneplus5-cheeseburger/diagnostics/A540-bringup-milestone1-2026-11-08.md`。

### H199：init 设置授权并记录实例（2026-11-08）

- `AGXAccelerator::init()` 覆盖并设置 `NativeSandboxGrantProcess=backboardd`
  （覆盖所有发布路径创建的实例）；
- `newUserClient` 打印 `self=<实例指针> grant=<属性值>`，用于确认缺授权的实例来源。

```text
H199 kernel:  ce6a651e490c6d9138b092c48f903c8c1f26ebcf8e8e1adb5e7e4612a2ebaa1f
H199 payload: 0e165694a5450f78ede122eaec93d65d3ea4c07ba83a310796fdae35d1917e5f
H199 boot:    9a63913e2c5bcbf896b0a4d3833779bffc549bb54497c8dfa043d8a3c7782581
```

### H199 结果：backboardd 不再被 MACF 拒绝，但主连接卡在服务检查（2026-11-08）

```text
MACF by process: backboardd 0, mediaserverd 8
347.491  op=open comm=backboardd cls=AGXAccelerator
347.491  NATIVE_DISPLAY_OPEN: service=AGXAccelerator process=backboardd grant=backboardd match=1
347.491  open request type=0x41470001 → granted
347.492  open request type=0x41470002 → granted
347.492  op=open comm=backboardd cls=AGXAccelerator   ← 主连接（type 0x4147）
         （没有 grant 日志、没有 open request、没有 MACF 日志）
NATIVE_A540_ABI: method= : 0
```

mark 打开成功、grant 匹配；但主连接的打开命中了**没有授权属性的服务实例**，卡在
`mac_iokit_check_open_service` 这一层（既没有 grant 日志也没有 newUserClient）。
服务会被重复发布，逐个实例补属性不稳定。

### H200：沙箱授权加服务类回退（2026-11-08）

新增补丁 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h200-sandbox-grant-class.patch`
（在 `zzw-native-adreno-sandbox-grant.patch` 之后应用）：`native_sandbox_grant()`
在属性缺失时，若服务类名是 `AGXAccelerator` 且调用进程是 `backboardd`，同样放行，
并打印 `grant=class match=1`。只影响这一个类与这一个进程。

```text
H200 kernel:  11862b03a85aaeaecc314b9a67431ef77f5076a6e3f0e79b0ab6bd03d14776d1
H200 payload: bb8e354183805ba5832720b3f4037469d611bc311989c1155ee3646c22945b7a
H200 boot:    35b435d8cb3bf286ca4c6e401a1c5b59e3c8ec04d2f8dc7b029bc351ff2370c0
```

判读：主连接应出现 `open request type=16711 comm=backboardd` 与
`NATIVE_A540_ABI: method=1/15/9 …`，随后是 `report …`。

### H200 第一次取日志：窗口太早（2026-11-08）

新鲜槽（boot `2b95df21`，header uptime 354）里只有 259 s 的插件加载与 mediaserverd
的一次打开；backboardd 的插件发现/主连接尚未发生（H199 在 347 s，H198 在 401 s），
所以这一窗口不能判断类回退是否生效。需要更长的运行时间再取。

（说明：同一次取到的 `msg`/旧槽里仍有 H199 的 347/358/368/380 s 打开记录，
分析时必须按 boot id 取新鲜槽。）

### H200 第二次启动结果：主连接、探测、Query 全部打通（2026-11-08）

新鲜槽（boot `2abcf390`，uptime 到 1047 s）：

```text
262.100  open request type=0x41470003       （主连接 0x4147 成功）
262.100  open request type=0x41471100       （probe 完成，admitted=256）
262.100  NATIVE_A540_ABI: method=4294967295 selector=0..23 in=8 comm=backboardd
262.100  open request type=0x41473001       （Query 成功，step=1）
NATIVE_A540_ABI: report : 0
backboardd traps : 0
```

也就是说：

- `IOServiceOpen(0x4147)` 成功（沙箱授权生效）；
- 用户态 selector 探测通过（256 个 selector 全部被承认）；
- 隧道头 `'NTNL'` 被识别，**Query 返回成功**（step=1）。

但之后没有 step=2 的标记、也没有 `SetMetadata` 的 report 行。ABI 入口日志的前 24 条
被探测本身消耗，后续真实方法没有日志可看。

### H201：只记录真实 ABI 方法（2026-11-08）

入口日志改为：探测只记一行（`probe selector=…`），非探测方法最多记 32 条。用于确认
`GetDeviceInfo`/`BoAlloc`/`SetMetadata` 是否被调用、返回值如何。

```text
H201 kernel:  c2753c728154a7c8973b3fd8dde184fa6cc407c2e1eaa96a7df7758dc1d7327a
H201 payload: 5124c133c2445089813000ce2b0ec9cbc62c0cf7cca594e85aa8049dffe0da08
H201 boot:    ebafa20f49333c227b8e9474ee88aa0b1c650ef18ca397f26220ad0aeb09624b
```

### H201 结果：间歇性竞态（2026-11-08）

新鲜槽（boot `24444a61`，31–1355 s）：backboardd 只做了 mark 1/2（250.7/433.3/591.2 s），
主连接 `open(0x4147)` 一次都没到内核；mediaserverd 反而打开了两次主连接。没有
backboardd 崩溃、没有 ABI 行。与 H200 第二次启动（主连接+探测+Query 全成功）对比，
说明剩下的是**端口/服务实例的时序竞态**：discovery 传入的 accelerator port 在测试执行
期间会失效或被重新发布。

### H202：测试前重新查找服务并重试（2026-11-08）

`NativeAdrenoUserTest.h`：在打开 0x4147 之前先
`IOServiceGetMatchingService("IOAcceleratorES")` 取一个新鲜的 port；若第一次打开仍失败，
再用重新查到的 port 重试一次（与上游线程内重新查找的做法一致，但保持内联）。

```text
plugin  ee40b192ba28a76a7b394caa0967b65abda8b4e2
daemon  08b8944448a21b3d4e6b7b261799e3332cb23c74
H202 payload: 4bb701337461b244801c42effaccdebd5eef9992010350ed3c208fbc13c784c2
H202 boot:    c9c47f94d4e14a7db04dbb867d842364b1ffdaa179b6ef317fac4361b162ded2
```

内核沿用 H201（标记 H201）。

### H202 结果：又是抓取时机（2026-11-08）

新鲜槽（boot `2b9bd7cf`，到 514 s）里没有 `MetalPluginClassName`、没有 `blob=215`、
没有 open 请求——这次启动到 514 s 还没到插件发现。按时间抓日志对这件事太脆弱。

### H203：ABI 状态进入 UFS 心跳（2026-11-08）

`NativeA540AcceleratorProbe.cpp` 导出：

```c
volatile int native_a540_abi_calls, native_a540_abi_last_method, native_a540_abi_reports;
char native_a540_abi_report[64];
```

`externalMethod` 每次自增/记录 method，`SetMetadata` 把文本存进 `native_a540_abi_report`。
`NATIVE_UFS_ALIVE` 心跳追加：

```text
abi=<calls>/<last method>/<reports> rep=<最近一次 SetMetadata 文本>
```

这样无论什么时候取日志，只要 ABI 被调用过就能看到，不再依赖发现时刻是否落在窗口里。

```text
H203 kernel:  a18224330a51dcf07064ac589283032a72bbd1f66fd02c76999040b95278000f
H203 payload: 3d63ae5d5d943bf8ad04f6dc57c7ef5caeb23b1bb1fd72d1aba9706ea8ff7599
H203 boot:    d612d2336ff65fbc4f13cf082c139639a83207b81549ad82a5df9a5e6df2e8ae
```

### H203 第一次取日志（2026-11-08）

新鲜槽（boot `2b92e63c`，到 402 s）：

```text
addon=8/7/0/1/22/1  owner=4/0 ext=4/2 dm=5/0 wp=1/2
abi=0/0/0 rep=
```

- 到 402 s 为止 ABI 尚未被调用（这次启动的插件发现比平时更晚，前几次在 250–400 s）；
- addon 安装这次是 `8/7/0/1`，有一个文件写入失败 `EINVAL(22)`（此前是 8/8/0/0）。
  下一轮需要确认是哪个文件；如果是插件可执行文件或 Turnip dylib，会直接影响加载。

心跳已经持久化（`abi=`/`rep=`），下一次取日志只需让设备跑足够久（≥12 分钟）。

### H203 第二次启动结果：ABI 未执行，addon 稳定少一个文件（2026-11-08）

新鲜槽（boot `2b9ec64b`，到 1253 s）：

```text
addon=8/7/0/1/22/1 owner=4/0 ext=4/2 dm=5/0 wp=1/2
abi=0/0/0 rep=
```

- 12 分钟以上 ABI 从未被调用；
- addon 稳定为 `8/7`，一个文件写入失败 `EINVAL(22)`（主机侧验证 addon 8 个文件
  全部可正常解压，所以是内核侧特定文件/写入路径的问题，不是打包问题）。

失败的若是 bundle 的 `Info.plist`/可执行文件，CA 拿不到 principal class，
自然永远不会进入 `initWithAcceleratorPort:` —— 与 `abi=0` 一致。

### H204：记录 addon 安装失败的文件名（2026-11-08）

新增补丁 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h204-addon-fail-log.patch`：
在 `native_gpu_addon_install` 的失败分支打印
`NATIVE_GPU_ADDON: failed <path> error=<errno> size=<size>`。

```text
H204 kernel:  7b47e2421725d9744dd36c6c92ef135e63b7269bdd5a577145b3383f493b8748
H204 payload: 239617ac426a7798ad28e16013f522d22280cb76ce13195f13b9e61696696c43
H204 boot:    1dc626feab3665f5230c2c7a47a50c6e7fa010f4f9d585569a4f336166a59e5e
```

（本轮构建遇到一次 `prepare-xnu-source.py` 的 `http.client.RemoteDisconnected`，
清掉 `.cache/xnu-work` 后重新构建即通过，属已知间歇问题。）

### H204 结果：失败的是插件可执行文件本身（2026-11-08）

```text
38.730  NATIVE_GPU_ADDON: failed /private/var/ngpu/addons/NativeAdreno.bundle/NativeAdrenoMetal
        error=22 (EINVAL) size=21716016
```

- 失败文件是 **21.7 MB 的插件可执行文件**，发生在 launchd 启动之前；
- bundle 缺可执行文件 → CA 拿不到 principal class → `abi=0`；
- 心跳 `addon=8/7/0/1/22/1`、`abi=0/0/0` 与之吻合；
- H191/H193 曾成功安装同样大小的文件，嫌疑集中在“已存在旧文件时的
  `O_TRUNC` + `IO_UNIT` 整块写入”路径（见路线 C 计划 §7.1）。

### 参考项目调研（2026-11-08）

已 `git fetch` 最新代码：

- `sagit-ios-port`（小米 6 / MSM8998 / A540，同 SoC/GPU）：完整 A540 GPU kext、
  QcomMTL、内核侧上电计划、平台策略（RPM/GPUCC/PM8005/OPP/ZAP/IOVA）、固件清单；
- `ios-sweet`（OnePlus 5）：无 GPU 时 CA 渲染器不启动（与我们一致），
  以及 CA::OGL::SW 等渲染器研究；
- `hackios-xnu-kernel`：RedwoodGPU（Linux msm DRM ABI）+ OnePlus 5 a5xx 移植说明；
- `DinnerABC/UniXNU-cheeseburger`：GPU 不可用，A740 实现不适用于 MSM8998。

路线 C 的完整计划：`plans/oneplus5-cheeseburger/diagnostics/A540-route-C-plan-2026-11-08.md`
（内核侧上电、原生 IOGPU 服务与 type-1 客户端、entitlement 准入、C0–C6 里程碑）。

### 原厂 ROM 提取（2026-11-08）

来源：`cheeseburger_rom/OnePlus5Hydrogen_23_OTA_065_all_2012030353_f743fd2428a00.zip`。

- `boot.img`（页 4096）里的 kernel 在偏移 13,179,047 处带单一 DTB（421,383 B），
  `dtc` 解出完整设备树；
- `vendor.new.dat` + `vendor.transfer.list`（v4，范围 `[start,end)`）重建出
  1,004,351,488 B 的 ext4 `vendor.img`，`/firmware/` 内含全部 A540 固件；
- 关键设备树数据已写入路线 C 计划 §4.5：
  - `kgsl-3d0@5000000`：chipid `0x5040001`、IRQ 300、`a540_gpmu.fw2`、`a540_zap`、
    7 档 OPP（710/670/596/515/414/342/257 MHz）、8 个时钟、vddcx + PM8005 S1；
  - `gfxcc@5065000` 的 `gfxfreq-speedbin0`/`mx-speedbin0`（频率-角-电压）；
  - `smmu-kgsl@5040000`：`qcom,smmu-v2`、三个中断、三个时钟、完整
    `attach-impl-defs` 寄存器表；
  - 固件清单与 SHA-256（a530_pm4/pfp、a540_gpmu.fw2、a540_zap.mdt/b00/b01/b02/elf）。

固件不提交仓库，放本地 cache，运行时经 GPU addon 投放并由驱动做 SHA-256 校验。

### H205：addon 分块写入 + 分步错误日志（C0，2026-11-08）

新增补丁 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h205-addon-chunked-write.patch`：

- `native_gpu_addon_write` 改为 **1 MiB 分块写入**，去掉 `IO_UNIT`
  （H204 的 21.7 MB 插件可执行文件在整块写入路径返回 `EINVAL`）；
- 每个失败步骤单独打印：`open/chmod/fsync` 与
  `write <path> at=<off>/<size> error=<errno> resid=<n>`；
- `install` 里 inflate 失败单独打印 `inflate <path> size=… packed=… error=…`，
  用于区分“解压失败”和“写入失败”。

```text
H205 kernel:  aa3ccd05a252150e9043445dc6f927d8b173541798b9160ac416046f85c887fa
H205 payload: 001cce791c8c1b9c7ea46da68615c4caf1648f974ec0fa9d0bcd5142f2298d79
H205 boot:    56f27d938c2bea324a0e6ebd05201f47bfebb9f11b3d13cc4020000e10548b19
```

判读：心跳 `addon=8/8/0/0` 表示修复成功，随后看 `abi=`/`rep=`；
若仍失败，新的分步日志会给出确切步骤与 errno。

### H205 判读：失败点是 inflate，不是写入（2026-11-08）

H205 的分步日志（boot `2ba5a2a7`，uptime 38.7 s）给出确定结论：

```text
NATIVE_GPU_ADDON: inflate /private/var/ngpu/addons/NativeAdreno.bundle/NativeAdrenoMetal
                  size=21716016 packed=9040949 error=22
addon=8/7/0/1/22/1
```

- 21.7 MB 插件可执行文件在 `native_gpu_addon_inflate` 返回 `EINVAL`；
- 主机解析同一个 `adreno-h202.gpuaddon`，每一条都能被 **内核自带的 zlib 1.2.3**
  （`libkern/zlib`，同一份源码编译）正确解出：
  `result=1 total_out=21716016 avail_in=0`，其余 7 条同样正确；
- 因此压缩流、addon 布局、分块写入都没有问题；失败发生在内核环境里。

推断：旧写入路径为每个文件 `kalloc_data(整个文件大小)`；21.7 MB 的一次性分配
很可能落在 bootloader 交接的 addon 内存块上，而 `kalloc_data` 会清零，于是
解压前输入已被自己覆盖（这也解释为什么只有最大的插件失败、之后 3 MB 的 Turnip
和尾部小文件都正常）。

### H206：流式解压 + 分块写，去掉整文件分配（C0，2026-11-08）

新增补丁 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h206-addon-stream-write.patch`：

- `native_gpu_addon_store`：固定 1 MiB 缓冲，`inflate(..., Z_NO_FLUSH)` 流式解压，
  每块用 `vn_rdwr` 按偏移写入，**不再分配整个文件的输出缓冲**；
- `packed == size` 的条目按原样分块写入（原样存储格式），供不适合压缩的条目使用；
- 失败时打印 inflate 的 `result/total_in/total_out/avail_in` 或具体写偏移；
- 安装结束后做一次性探针：分配"最大条目大小"（21.7 MB）并按地址判断是否与
  addon 交接块重叠，打印 `probe alloc=... blob=... overlap=0|1`，用于确认上述推断。

```text
H206 kernel:  a6e328fd834cd04eff968b974d5c585bbab00187be6426c5f24a6a8dd1b31b46
H206 payload: 35363bc148e288fe5d602d3f8d5e86c979630b25a557c471fc7fd8e0bfa47792
H206 boot:    50be3f3a51546fdd597554e3420606c2da2ae0663efc18868493073c7966db00
```

判读：`addon=8/8/0/0` 表示插件已写入；`probe ... overlap=1` 证实 H205 的失败原因。
随后看 `abi=`/`rep=` 是否非零（插件加载与 ABI 探测）。

### H206 判读：流式写入可用，但输入流在内核里被改写了（2026-11-08）

```text
NATIVE_GPU_ADDON: inflate result=-3 total_in=9040949/9040949
                  total_out=21716048/21716016 avail_in=0
NATIVE_GPU_ADDON: probe alloc=0xfffffff85d2e3000 size=21716016 blob=0xfffffff00cf58000 overlap=0
addon=8/7/0/1/22/1
```

- `result=-3` 是 `Z_DATA_ERROR`，`avail_in=0`（输入全部消费），`total_out` 比条目
  声明的 `size` **多 32 字节**——内核看到的压缩流与文件里的不是同一份数据；
- 探针的 `overlap=0` 无意义：`kalloc` 返回内核堆虚拟地址（`0xfffffff8…`），addon 是
  静态映射地址（`0xfffffff0…`），两者本来就不会落在同一区间；
- 已核对：payload 里的 `kernel.macho.gpuaddon` 与本地验证文件 SHA-256 完全一致，
  所以 FAT/打包没有问题；
- 主机用**内核同一份 zlib 1.2.3**、同样的 1 MiB 流式 `Z_NO_FLUSH` 调用解压同一
  addon，8 个条目全部 `result=Z_STREAM_END`（插件 21 次调用，`total_out` 精确）；
- 尾部 4 字节损坏只会得到 `total_out = size` + `incorrect data check`，与内核的
  `size + 32` 不符。

`DarwinBoot.c` 里 `Args->TopOfKernelData = Address + Used` 已覆盖 addon，理论上
VM 不会分配这块物理内存，因此需要直接确认运行时的字节。

### H207：addon 源数据校验和诊断（C0，2026-11-08）

新增补丁 `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-h207-addon-source-fnv.patch`：
对 `packed >= 1 MiB` 的条目打印源数据的 FNV-1a、首尾 4 字节，并对插件按 1 MiB
分块打印 9 个校验和。主机端同一文件的期望值：

```text
NativeAdrenoMetal  off=464      packed=9040949 fnv=30ad5e1b head=78daecbd tail=e9e55dfc
  chunks a4c47b8b 6ddf9b97 ddcb1a57 edf29cb0 92675356 3941162e 43bcb43d 5123d802 94cc5623
libvulkan_freedreno.dylib off=9042112 packed=3066332 fnv=2fc21ad9
```

判读：若 FNV 与上表一致 → 运行时数据完好，问题在内核 zlib 的使用/环境；若某一
分块不一致 → 直接定位被改写的物理区段。

```text
H207 kernel:  e58aae6aca8417a7aa1de1485e06e5663a470e53ef07e13d91203cc48bc05829
H207 payload: 2cc080c864bca0326ac6cffd4f1e5708d04d4a5e1f1e3e60b6782c79097dc5a4
H207 boot:    ddd9a9b3f2e19c7fe7485466c2779b2aa5cd7d725c520579e36a7d07e584ae74
```

### H208：条目 CRC32 + 原样存储，插件绕开 zlib（C0，2026-11-08）

H207 只抓到 dylib 的源校验和（`fnv=2fc21ad9`，与主机一致）；插件的诊断行没有进入
日志环，但 `inflate`/`failed` 行仍在。为了一次拿到确定结论并尽量解除 C0：

- addon 条目头从 24 B 扩到 32 B：`name_bytes, mode, size, packed, crc32, flags`；
  `flags` bit0 = 原样存储。blob magic 仍是 `NGPUADD2`（loader 只校验 magic/总长）；
- 内核在写入/解压前用 `z_crc32` 校验**存储字节**，不匹配就打印
  `crc <path> got=.. want=..` 并返回 `EILSEQ`；
- `pack-adreno-addon.py`：大于 20 MiB 的条目**原样存储**（当前只有 Metal 插件），
  这样解压路径完全不参与该文件的投送；
- `NativeRamBlock` 导出 `native_ram_block_gpu_addon_physical`，安装时打印
  `blob <va> paddr=<phys> bytes=.. count=..`，可对照 `TopOfKernelData`/VM 区间；
- 诊断改为短行：每条目一行 `e%u off/packed/crc/stored`，之后每 1 MiB 一行校验和。

新的 addon（24,800,808 B）关键值：

```text
plugin  e1 off=480      packed=21716016 crc=32bf9d33 stored=1
turnip  e3 off=21717208 packed=3066332  crc=eed78f81 stored=0
```

payload 从 76 MiB 扩到 **84 MiB**（内容 80,533,512 B，剩余 6.8 MiB），
`ramdisk_end = 0x17400000 < tags 0x18000000`。

```text
H208 kernel:  b3d104e6289dfdd07a232e3aa1e356edef8ff013e2d9198d8b292c579892100f
H208 payload: df6933118de33f2a474b58836f547c85c7211f157a45c866e95ba2e234cc3968
H208 boot:    ca1759bc986ec04ddb68782bd219991a03b365695942d225492aa00d1a304c75
```

判读：
- `crc ... got == want` 且 `addon=8/8/0/0` → 源数据完好，插件已按原样写入，C0 完成；
- `crc ... got != want` → 交接块在内核读它之前已被改写，下一步按 `paddr` 定位并
  改为早期副本/保留物理页。

### H208 上机：boot image 超过 81 MB，UEFI 未启动（2026-11-08）

为了让插件完全绕开 zlib，H208 把 >20 MiB 的条目改为原样存储（addon 24.8 MB），
payload 从 76 MiB 扩到 84 MiB，boot image 89,536,512 B。结果：**停在 OnePlus
logo，UEFI 菜单都没出现**。

与文档中 H86f 的现象一致（`STATUS` §H86：32 字节 policy 时 boot image 135 MB，
停在 OnePlus logo，UEFI 根本没起来，确认是镜像过大；截断后回到 81,147,904 B
即可启动）。已知可启动的最大镜像就是 **81,147,904 B（76 MiB payload）**，
84 MiB payload 超出上限。

结论：**原样存储的大 addon 无法经 payload 投送**（12.67 MB 增量装不进 76 MiB）。
`board.toml` 的 `size_mib` 保持 76。

### H209：压缩投送 + 条目 CRC32（C0，2026-11-08）

回退原样存储，保留 H208 的格式改动：

- addon 条目头 32 B：`name_bytes, mode, size, packed, crc32, flags`，
  `flags` bit0 = 原样存储（当前不触发）；
- 内核在写入/解压**之前**用 `z_crc32` 校验存储字节，不匹配打印
  `crc <path> got=.. want=..` 并返回 `EILSEQ`；
- 保留短行诊断：`blob <va> paddr=<phys> bytes= count=`、
  `e%u off/packed/crc/stored`、每 1 MiB 一行校验和。

```text
H209 addon:   12,125,744 B（plugin packed=9,040,949 crc=? stored=0）
H209 kernel:  4f56c8b7f8664edca5cd2dfb1ee5499b92e0726c26e4a9b105f2c59d507437c1
H209 payload: ceb2cbe20189990fe15d1fc2510192b7359504c2b4c98141d5586331f4e8e2d4
H209 boot:    e80d60f952668c009a54220873ee8e50725facf239075a757c489d62f755eea2
             81,147,904 B — 与已知可启动上限完全一致
```

判读：这是**决定性一次**——`crc got == want` 说明交接块数据完好（问题在内核 zlib
使用环境），`got != want` 说明数据在被读取前已被改写（下一步按 `paddr` 处理）。

### H209 结果：CRC 不匹配，交接块数据在安装前已被改写（2026-11-08）

```text
addon=8/7/0/1/92/1        ← 92 = EILSEQ
plugin=NativeAdreno info=0 files=8 written=7 same=0 failed=1 error=92
```

- `error=92` 是 `EILSEQ`，由 H208 新增的 CRC 校验返回：插件条目的**存储字节与
  打包文件不一致**；
- Turnip 条目（紧跟其后、off≈9.04 MB）CRC **通过**，小文件全部通过；
- 主机核对 `adreno-h209.gpuaddon` 的 8 条 CRC 全部正确 → 问题不在打包；
- 结论：**内核读到的 addon 块前 ~9 MB 在安装前已被改写**，与 H205–H207 的
  `Z_DATA_ERROR`（多解出 32 字节）完全吻合。

日志行丢失的原因也定位了：安装发生在日志写入器做快照（`deferred snapshot to
window read`）后的 ~150 ms 内，这段时间内 `printf` 的行不会进入日志环
（H206/H207 的 `src` 行、H209 的 `crc`/`blob` 行都是这样丢的）。

### H210：addon 早期副本 + 实时 CPU 频率格（2026-11-08）

投送修复：

- `NativeRamBlock::start()` 一开始就调用 `native_ram_block_gpu_addon_snapshot()`：
  用 `IOMalloc` 复制整个 addon 块并缓存，之后 `native_ram_block_gpu_addon`
  返回这份副本；内核安装时不再读可能已被改写的 loader 交接块；
- 打印 `NativeRamBlock: gpu addon snapshot bytes=.. paddr=..`；
- 心跳新增 `gpup=<物理地址> crcbad=<次数>`（`NATIVE_UFS_ALIVE` 行长不受快照影响）；
- 安装结束后补打 `NATIVE_GPU_ADDON: late blob=.. paddr=.. crc_bad=..`，若 CRC
  失败再补打该条目的每 1 MiB 校验和（快照窗口之后，行不会再丢）。

显示：

- `sheng_cpufreq_probe()` 只映射一次 OSM 窗口，新增 `sheng_cpufreq_tick()`；
- 1 Hz 心跳在重绘心跳格前先 `sheng_cpufreq_tick()`，并按最新状态重绘**左上 CPU 格**
  ——CPU 频率指示从"开机一次性采样"变为**实时**（红 <1 GHz/未使能，绿 ≥1 GHz）。

```text
H210 kernel:  f9351c7f40e5d4c52644a7ca03a6848cd8bf7eb82f3f73450612052e3c0ad830
H210 payload: 466a9df1833e174b2ad8a25cbf8e0270951ea8ed8151dfaabbe29bc3b951002d
H210 boot:    0f1cef6a5e28bed003b1bb8def1d9ea4c2eb68de2b62c796723911aaa1b78f6e
              81,147,904 B
```

判读：`crcbad=0` 且 `addon=8/8/0/0` → 早期副本完好，C0 完成；若 `crcbad>0`，
说明副本也已被改写，`late c*` 行会指出被改写的位置。

### H210 结果：只有 7–8 MiB 那一段被改写（2026-11-08）

```text
NATIVE_GPU_ADDON: late blob=0xfffffff78966e000 paddr=6542426112 bytes=12125744 crc_bad=1
NATIVE_GPU_ADDON: late crc_bad source=0xfffffff78966e1e0 bytes=9040949 off=480
NATIVE_GPU_ADDON: late c0 a4c47b8b   … c6 43bcb43d   c7 3ef50fb0   c8 94cc5623
addon=8/7/0/1/92/1 … gpup=185f58000 crcbad=1
```

- addon 物理地址 **0x185f58000**（6.09 GiB），不是之前推测的低地址；
- 主机期望值：`… c6 43bcb43d  c7 5123d802  c8 94cc5623`；
- 内核实测：只有 **c7** 不符（插件流 7–8 MiB），其余 8 个 1 MiB 块**完全一致**；
- 即被改写的是 addon 偏移 7,340,512 起（物理约 `0x1866581e0`）的一小段，
  范围 < 1 MiB；
- 早期副本（`NativeRamBlock::start` 的快照）里就已经是坏的 → 损坏发生在
  快照之前，不是安装期的缓冲区踩踏。
- 心跳字段 `gpup=`/`crcbad=` 不受日志快照影响，已确认可用。

### H211：副本 vs 交接块逐字节比较（C0，2026-11-08）

- `NativeRamBlock` 新增 `native_ram_block_gpu_addon_block()`（直接返回 loader
  交接块）与 `native_ram_block_gpu_addon_copy_info()`（副本的虚拟/物理地址），
  快照日志增加 `copy=.. copyphys=..`；
- `kern_exec` 在 CRC 失败时比较**副本**与**交接块**，打印首个不同偏移
  `diff=` 以及该处两侧各 16 字节，并把定位粒度细化为 **64 KiB**（`late f<off>`）。

判读：
- `diff` 与 64 KiB 分段能指出被改写的确切范围；
- `block`/`copy` 两侧字节可对照主机文件，判断写入者的内容特征（全 0、ASCII、
  像素值等），从而定位写入者。

```text
H211 kernel:  007de9cb57ab46debd4cc8f51cfcaf3f8bf18acbbafe4edd22e374a7cb15c7a0
H211 payload: b255c1d8c19dea5ff4fb8cf079fbb5d9066408092bea781143914aa2438e45f7
H211 boot:    0c453ce98e14026df85d24743a59035331d79c6aaf46d6e11937ed93449a467b
              81,147,904 B
```

### H211 结果：`ml_static_vtop` 用于堆地址导致 panic（2026-11-08）

```text
NATIVE_PANIC_STR: ml_static_vtop: illegal VA: 0xfffffff896613000;
                  virt base 0xfffffff007004000, size 0x80000000 @arm_vm_init.c:425
```

- 诊断代码在安装末尾调用 `ml_static_vtop((vm_offset_t)copy)`，但 `copy` 是
  `IOMalloc` 的**内核堆地址**，不在静态映射窗口内，`ml_static_vtop` 直接 panic；
- 与 GPU/投送无关，是本轮诊断代码的缺陷；
- 说明：安装确实走到了末尾诊断（`late blob`/64 KiB 分段已打印），只是随后崩溃。

### H212：去掉 `ml_static_vtop`，保留内容比较（C0，2026-11-08）

- 快照日志只打印 `copy=<虚拟地址>`，不再求物理地址；
- `native_ram_block_gpu_addon_copy_info()` 的 `phys` 固定返回 0；
- 其余不变：`kern_exec` 在 CRC 失败时比较**副本 vs 交接块**，打印 `diff=` 与
  两侧各 16 字节，并输出 64 KiB 粒度校验和。

```text
H212 kernel:  59fa0e0fd32fe63d53799cefa5f09ab7807ca0e1f8e44cf0d3a819435c3fd69b
H212 payload: ae8bcfccb0422091c2aefe518853367566739f93dcf0ae131c2e6e36b0878fc9
H212 boot:    e16725f483fdb76473a9b4b0dec95caf84ff655fca563d91ae6b6281d515de9c
              81,147,904 B
```

判读：`diff=identical` 或很小的偏移 → 交接块在快照时就已经是坏的；
`diff` 指向 `copy` 与 `block` 不同的位置 → 副本之后又被写过。

### H212 结果：捕获窗口不够，但已确认 0–5 MiB 完全一致（2026-11-08）

- `late f*` 共打印 144 行（64 KiB 粒度），但日志窗口只保留了前 82 行（到 0x510000）；
- 这 82 个分块与主机**逐块一致**，因此 0–5 MiB 未被改写；
- 出问题的 7–8 MiB 段与最后的 `diff=` 行都被截断 → 需要**减少输出**。

### H213：精简诊断 + CPU 频率格不再误报红（2026-11-08）

投送诊断（`zzzz…h213-addon-diff-report.patch`）：

- 先打印 `diff=`（副本 vs 交接块首个不同字节）和两侧 16 字节；
- 只打印 9 行 1 MiB 校验和 + 16 行 64 KiB（`0x700000..0x800000`），
  总共 ~28 行，避免再被日志窗口截断。

CPU 频率格（`NativeLegacyProbeSupport.cpp` / `NativeLegacyDisplay.cpp`）：

- H211/H212 的 console 显示两组 cluster 全是 `enable=0 desired=0 raw=0`、
  APCS 时钟 `cmd/cfg=0 status=00100000` → OSM 在本内核里根本没有被初始化，
  旧逻辑因此永远 `any=false` → 判红；
- 改为：**只有确实读到"已使能 cluster 且 <1 GHz"才红**；一个都没读到 → 新状态
  6（灰 0xff808080），不再是误导性的红；
- 新增一次性寄存器转储 `NATIVE_CPUFREQ_OSM`（cluster 0/1 的 0x0/0x4/0x1000/
  0x1004/0x1f10/0x1f14）与 `NATIVE_CPUFREQ_APCS`（PLL L 值、CFG_RCGR），
  用于下一步推导真正的当前频率来源；
- 厂商 DTS 已提供 OSM/APCS 的权威布局：
  `qcom,cpu-clock-8998@179c0000`（osm/pwrcl_pll/perfcl_pll/apcs_common）、
  `qcom,apcs-cmd-rcgr=<0x17911050 0x17811050>`、
  `qcom,apcs-cfg-rcgr=<0x17911054 0x17811054>`、
  `qcom,apm-ctrl-status=<0x179d000c 0x179d0018>`、
  以及 pwrcl/perfcl 的 speedbin0 频率表。

```text
H213 kernel:  8d4b3a0ca8d1bd5727f9c80a4d022db8de3c4277eb04e4d6ef7f635990910462
H213 payload: f79214be3704272f9b23742a9f4ea38984dc841a8670412cd98917bf15ad2a2a
H213 boot:    1967ddb4dfd8994f8679a6156a97d0ae029bdcbc9601bd5cecc92bcb65937010
              81,147,904 B
```

### H213 结果：副本与交接块逐字节相同，损坏在 64 KiB 内精确定位（2026-11-08）

```text
late blob=… paddr=6542426112 bytes=12125744 crc_bad=1
late crc_bad source=… bytes=9040949 off=480
late copyvirt=fffffffbb86b1000 copybytes=12125744 block=0xfffffff00cf58000
     blockbytes=12125744 diff=12125744
late m0..m6 = 主机一致；m7 3ef50fb0（期望 5123d802）；m8 一致
```

- `diff == 总长` → **早期副本与 loader 交接块完全相同**；既然副本本身已坏，
  损坏发生在 `NativeRamBlock::start()` 复制**之前**，不是安装期被踩；
- 64 KiB 粒度（`0x700000..0x800000` 共 16 块，全部打印成功）显示：
  **只有 `0x7b0000..0x7c0000` 这一块不符**，其余 15 块与主机完全一致；
- 对应 addon 偏移 `0x7b01e0..0x7c01e0`，物理地址约
  `0x1867081e0..0x1867181e0`（约一个 64 KiB 页范围）。

### H214：打印坏块内容（C0，2026-11-08）

- 保留 `late blob` / `late crc_bad` / `diff=` / 9 行 1 MiB 校验和；
- 对已知坏块 `0x7b0000..0x7c0000` 每 4 KiB 打印 32 字节（16 行），
  用内容特征判断写入者（全 0、ASCII 日志、DMA 描述符、或文件另一段的拷贝）。

```text
H214 kernel:  88791801ff4646be3ab94663b0e73d14c45f0860079085c7c51f0bbdd8b01b04
H214 payload: 706cf4fdaefeb6900b7324600b5475903e5ad1bbeb7b24f0898762a9b12ee848
H214 boot:    010ab231f7c513ecfc834dcdcc81ecd87abd0ff5a797f7305a0e600f1bb14a68
              81,147,904 B
```

### H214 结果：坏块内容在页首与文件一致，写入小于一页（2026-11-08）

- 16 个采样点（`0x7b0000 + k*0x1000`，每点 32 字节）**全部与文件一致**；
- 但该 64 KiB 块的 FNV 与主机不同 → 差异位于页内、不在页首，写入范围 < 4 KiB；
- 同时核对：payload 里的 addon 与本地验证文件 **SHA-256 完全相同**，8 条 CRC 全部
  正确 → 不是打包问题，损坏发生在 RAM。

### H215：1 KiB 粒度扫描（C0，2026-11-08）

- 在已知坏块 `0x7b0000..0x7c0000` 上按 1 KiB 打印 64 个校验和；
- 下一步只需把命中的 1 KiB 内容打印出来即可识别写入者。

```text
H215 kernel:  d8eaa6e3a4324f6d7bdfca58085f3038271b9c3cb92440674b4986ecc45f5aa3
H215 payload: b8f67fd4548aad43a52fda702b2acffca7e031b4acddc6f5d2366440a7fb7225
H215 boot:    080467a82d667d6c12ae73b2b7ff36b730fae7215474e07b1c3b74683d6578b0
              81,147,904 B
```

### H215 结果：损坏收敛到单个 1 KiB 块（2026-11-08）

64 个 1 KiB 校验和全部打印成功，与主机比对后**只有一个块不同**：

```text
0x7b9000 ok   0x7b9400 got 22ece2a5 want 0d6b2f07  ← BAD   0x7b9800 ok   0x7b9c00 ok
```

- 插件流 `0x7b9400..0x7b9800` → addon 偏移 `0x7b95e0..0x7b99e0`
  → 物理地址 `0x1867115e0..0x1867119e0`（同一个 4 KiB 页内）；
- 即一次 **≤1 KiB、页内非对齐**的写入；
- 该窗口已连续 4 次启动稳定命中同一位置。

### H216：打印这 1 KiB 的内容（C0，2026-11-08）

按 64 字节一行打印 `0x7b9400..0x7b9800`（16 行），用内容特征识别写入者。

```text
H216 kernel:  e6123788efd688080cb8da48a8be40a5985a6792aa1e74d18ef1e44cf3ef4862
H216 payload: e76b710268bf1491c39aefc7b60578fbff8e649880818f12f010fdcf0efc87e7
H216 boot:    3bf3b748a904bb472cae0d0fe9a7ac7641837258bce01a404419bdec419a8619
              81,147,904 B
```

### H216 结果：损坏是 8 字节的 64 位写入（2026-11-08）

1 KiB 内容逐 64 字节比对后，**只有 8 个字节不同**：

```text
addon 偏移 0x7b9800（= 插件条目存储数据 0x1e0 + 流偏移 0x7b9620）
物理地址 0x186711800
原文 fd 88 a3 31 fa 61 d5 e8
被写 00 f0 7f 80 00 00 00 00   (= 0x00000000807ff000，8 字节对齐)
```

注意：H213-H215 的偏移都是**相对条目存储数据**（起点 0x1e0），H216 里我误按 0x480
换算出 0x7b9aa0，实际 addon 偏移是 **0x7b9800**。

### H217：addon 自带"已知损坏修复表"（C0 解除，2026-11-08）

写入者尚未定位，但损坏是确定性的，先让投送不再被它卡住：

- blob 头第 12 字节（原本保留）改为 `repair_off`，指向末尾的修复表；
- 修复表记录 `<offset u64, length u32, flags u32, 观察到的错误字节, 原始字节>`；
- 内核在**任何校验/写入之前**应用：仅当该偏移的当前字节**完全等于**记录的
  "错误字节"时才恢复原文，并打印 `NATIVE_GPU_ADDON: repaired off=... len=...`；
- 这样重建 addon（内容变化）时不会误修。

本次记录：

```text
repair 0x7b9800: 00f07f8000000000 <- fd88a331fa61d5e8
addon: 12,125,780 B（+36 B 修复表）
```

```text
H217 kernel:  e686df836927e2d8c33dd6afdac70c25176e339c7971e439e97b33115dee38b4
H217 payload: b81a43a633be28c7028bd135e20038f49ea46cdb4e0e35a2e8e8b8e7d406e137
H217 boot:    a22deeef19b7ce7a1a0e315cb7ea2e3f4041553de6dc172c285fb8129e0602ba
              81,147,904 B
```

判读：出现 `repaired off=32112640 len=8`（0x7b9800）+ `addon=8/8/0/0` + `abi≠0`
→ C0 完成；若 `repaired` 不出现而 CRC 仍失败，说明损坏位置变了。

### H217 结果：C0 投送完成，backboardd 首次打开 AGXAccelerator（2026-11-08）

```text
NATIVE_GPU_ADDON: plugin=NativeAdreno info=0 files=8 written=8 same=0 failed=0 error=0
addon=8/8/0/0/0/1 … crcbad=0
late blob=… bytes=12125780 crc_bad=0
```

- 8 个文件全部写入，**没有任何 CRC 失败**：修复表（H217）把已知的 8 字节损坏
  恢复后，插件条目校验通过；
- `repaired`/`blob` 两行又落在日志快照窗口内被吞掉，但 `crcbad=0`、`written=8`
  已足以证明修复生效（若未命中，插件条目仍会 `EILSEQ`）。

更重要的变化：**backboardd 开始打开加速器服务**：

```text
NATIVE_IOKIT: op=open comm=backboardd cls=AGXAccelerator d=- ok=0
NATIVE_A540_ACCEL: open request type=0x41470001 comm=backboardd … granted
NATIVE_A540_ACCEL: user client type=0x41470001 granted
NATIVE_A540_ACCEL: open request type=0x41470002 comm=backboardd … granted
NATIVE_A540_ACCEL: user client type=0x41470002 granted
```

在此之前（H190–H216）backboardd 从未打开过该服务；这是插件真正投送成功后才出现
的行为。

仍未完成的部分：`abi=0/0/0`，日志里没有任何 `NATIVE_A540_ABI` 报告，即用户态
尚未调用 Query/GetDeviceInfo 等 ABI 方法。按路线 C 计划，C0 的第二个验收点
（`abi` 出现 Query/GetDeviceInfo）还需要下一轮。

下一步候选：
1. 先确认插件是否被 Metal 真正加载（`NativeAdrenoMetal` 的 dyld/初始化痕迹）；
2. 或在既有 ABI 上补齐 backboardd 打开 0x41470001/0x41470002 后立即调用的方法；
3. 同时可以开始 C1（ADT 打开 `gpu@5000000`/`gpucc`、按 §4.2 上电）。

```text
H217 kernel:  e686df836927e2d8c33dd6afdac70c25176e339c7971e439e97b33115dee38b4
H217 payload: b81a43a633be28c7028bd135e20038f49ea46cdb4e0e35a2e8e8b8e7d406e137
H217 boot:    a22deeef19b7ce7a1a0e315cb7ea2e3f4041553de6dc172c285fb8129e0602ba
              81,147,904 B
```

### H217 判读：插件测试确实在 backboardd 里跑起来了，但卡在 H202 的服务重查（2026-11-08）

C0 投送成功后第一次真正跑到了插件路径。H217 日志里的两次/三次打开是**我们自己测试的
进度标记**，不是插件的真实 ABI：

```text
open request type=0x41470001 (mark 1)   → granted
open request type=0x41470001 (mark 1)   → granted   （第二次实例）
open request type=0x41470002 (mark 2)   → granted
NATIVE_IOKIT: op=match comm=backboardd d=IOAcceleratorES ok=1   ← 到此为止
```

- `adrenoUserTest()` 只在插件里被调用（`NativeAdrenoMetalPlugin.mm` 的
  `-initWithAcceleratorPort:` 内联执行），所以**插件确实被加载并在 backboardd 里运行**；
- `mark(1)`、`mark(2)` 都到了，说明 dlsym 全部成功；
- 之后再也没有 `open request type=16711`（真实 ABI 的 `0x4147` 打开），也没有失败标记
  `0x4f01` → 卡在 `mark(2)` 与真实 open 之间，也就是 H202 新增的
  `IOServiceGetMatchingService(IOAcceleratorES)` 预查。

死锁原因：匹配过程会持有 IOKit 注册表锁并调用 `AGXAccelerator::copyProperty`
（H169 为观察渲染器而加的日志），而该 override 在锁内直接 `IOLog` → 与日志锁
形成死锁。H200 当时没有这段预查，所以能走到 Query。

### H218：去掉锁内日志 + 记录真实 ABI selector（2026-11-08）

- `notePropertyRead()` 不再 `IOLog`，只保留计数（避免注册表锁内的日志死锁）；
- `AGXDeviceUserClient::externalMethod` 顶部新增 selector 记录：每个**不同**的
  selector 打一行
  `NATIVE_A540_ABI: sel=<n> in=<scalar>/<struct> out=<scalar>/<struct> comm=<进程>`，
  并附前 4 个 scalar 与前 2 个结构体字；最多 32 个不同 selector；
- 插件二进制未改，因此不需要重建信任缓存/插件。

```text
H218 kernel:  a9708e384cf6001854ae3c10c12f25a3d443ed21c4e8cb4ff1c5d321c8a21e67
H218 payload: ab758206d24d14d3a508e8e96bd1fc012ad9862c213bacb92fac7f45e843e48a
H218 boot:    e78cacaa6286976fc1210b6f5577d0a6a01f374bc807be839b94532d48b69835
              81,147,904 B
```

判读：若死锁解除，应看到 `open request type=16711` → `user client type=16711 granted`
→ 随后 `NATIVE_A540_ABI: sel=…` 行（插件真正调用的 selector 及其参数形状）。

### H218 结果：日志窗口混入旧 slot，结论需用心跳复核（2026-11-08）

- H218 启动里仍然没有 `open request type=16711`，也没有任何
  `NATIVE_A540_ABI: sel=` 行；
- 但发现报告里出现**上一轮启动的旧行**（例如 `NATIVE_A540_ACCEL: read key=…`
  在 369.034694，与 H217 报告的时间戳完全相同），而当前内核二进制里已经没有
  这个字符串。原因是 H103 窗口的 247 个 slot 覆盖多次启动，合并时并非所有旧
  slot 都被 boot id 过滤掉。
- 结论：**不能用合并文本判断"本轮是否发生过某事件"**，只能用心跳行
  （由当前启动的状态写入）或原始 slot 的 boot 戳。

### H219：把加速器打开/selector 计数写进心跳（2026-11-08）

- `NativeA540AcceleratorProbe.cpp` 新增全局计数：
  `native_a540_open_count/open_type`（`newUserClient` 每次调用）与
  `native_a540_sel_count/sel_last`（`externalMethod` 每次调用）；
- 心跳行追加 `accel=<open_count>/<open_type>/<sel_count>/<sel_last>`，
  每 11 秒刷新，只反映**当前启动**；
- 这样能明确回答两件事：
  1. 真实 ABI 打开（type `0x4147` = 16711）有没有发生；
  2. 插件到底调用了哪个 selector（tunnel 之外的原始 selector）。

```text
H219 kernel:  63b7cfc8498a2e804eb5de89b2b7758dad9892840adf3264bd8e973252d706c5
H219 payload: 62354bfdc397d752ef5aa6f8dc18d7719423ff6f138e98a944cd45aca5bddc09
H219 boot:    f83676ee7d51042e0263a348457c6c4e31cf628bcfaaae8db320bfb6998ae100
              81,147,904 B
```

判读：`accel=` 的第二个数字若变成 16711 → 真实打开成功；第四个数字给出
最后一个 selector。

### H219 判读：日志窗口混入多次启动，但本轮数据证明插件 ABI 已在跑（2026-11-08）

按 slot 戳逐条解析后（本轮 boot `2c39e48b`，H219，共 28 个 slot，到 322 s）：

```text
266.08 … 267.88  NATIVE_A540_ABI: sel=10..31 w=4e544e4c ("NTNL") comm=backboardd
267.97           NATIVE_A540_ACCEL: open request type=0x41470000 comm=backboardd … granted
```

- 之前看到的 700/866/1068 s 心跳其实来自 **H214** 的旧 slot（msgbuf 残留文本会带进
  新 slot），所以 `accel=0/0/0/0` 只代表 266 s 之前；
- **266 s 起插件在 backboardd 里跑完了 selector 探测**，用的是我们测试的 `NTNL`
  隧道，`sel=10..31`、`in=0/8`、`w=4e544e4c` 全部命中 → 真实 ABI 连接
  （`IOServiceOpen(0x4147)`）其实已经成功，只是那一行正好落在被截断/交错的
  日志区间里。

结论：C0 的第二个验收点（插件建立真实 ABI 连接并调用方法）**已经达成**；
剩下的是"补齐插件真正需要的方法语义"。

### H220：独立的加速器状态短行（2026-11-08）

- 心跳里新增每拍一行短日志：
  `NATIVE_ACCEL_HB: accel=<open>/<type>/<sel>/<last> abi=<calls>/<method>/<reports> rep=<text>`
- 长 `NATIVE_UFS_ALIVE` 行在 slot 里会被截断，短行保证 `abi=`/`rep=` 一定可读。

```text
H220 kernel:  ebaf460392b46893fe6a6fea7e985cec57f8e35d5a62d14183b283fcee039159
H220 payload: d5d7fb5f4cee83df592c3631c83470957b7ca14b31811e030ebbab19d620953a
H220 boot:    a022b4404833621795eb40373d1a1217f4418710ce9322ac42d99dee24c2d0d3
              81,147,904 B
```

判读：`abi=` 的第二个数字即插件最后调用到的方法编号；`rep=` 是测试写入的报告文本
（`s<step> e<error> v<verified>`）。

### H220 结果：C0 完成（Query + GetDeviceInfo 均成功）（2026-11-08）

本轮短心跳（boot `2c3dbc8f`，H220）首次把 ABI 状态完整写出来：

```text
NATIVE_ACCEL_HB: accel=57/1095192831/1300/0 abi=1300/9/5 rep=backboard s2 ee00002c7 v-1/-2 t…
```

- `accel=57/…/1300/0`：`newUserClient` 57 次、`externalMethod` 1300 次（selector 探测反复执行）；
- `abi=1300/9/5`：隧道调用 1300 次，最后方法 9（`SetMetadata`，即报告本身），5 条报告；
- `rep=backboard s2 ee00002c7 v-1/-2`：测试 **2 步成功**后失败，错误
  `0x2c7 = kIOReturnUnsupported`。

对照 `NativeAdrenoABI.h` 的方法编号，测试顺序与结果：

| 步 | 方法 | 编号 | 结果 |
| --- | --- | --- | --- |
| 1 | Query | 1 | 成功 |
| 2 | GetDeviceInfo | 15 | 成功 |
| 3 | BoAlloc | 2 | `kIOReturnUnsupported`（驱动未实现） |

**C0 的两个验收点全部达成**：
1. `addon=8/8/0/0`（投送，H217 起稳定）；
2. 插件在 backboardd 里建立真实 ABI 连接，并成功完成 Query + GetDeviceInfo。

下一道门是 `BoAlloc`：它需要真正的 GPU 缓冲区/IOVA 分配，属于 C3（SMMU + CP）
范畴，不是 ABI 层面的桩。

```text
H220 kernel:  ebaf460392b46893fe6a6fea7e985cec57f8e35d5a62d14183b283fcee039159
H220 payload: d5d7fb5f4cee83df592c3631c83470957b7ca14b31811e030ebbab19d620953a
H220 boot:    a022b4404833621795eb40373d1a1217f4418710ce9322ac42d99dee24c2d0d3
              81,147,904 B
```

### H221：C1 起点，GPUCC 只读基线（2026-11-08）

C0 已收尾（H220）。C1 的第一步是建立 GPU 时钟控制器的基线读数：

- `sheng_gpu_power_probe()` 映射 `0x5065000`（GPUCC，0x9000，只读、cache-inhibit），
  打印前 `0x1000` 范围内的非零寄存器（最多 48 行）并输出
  `NATIVE_GPUCC: survey tested=… shown=…`；
- 不写任何寄存器，也不读 GPU 内部 RBBM（未上电时可能挂总线）；
- 与 sagit 的只读探测对齐（GPU 关闭时 GPUCC 可读：`gfx3d_clk_src` 9.6 MHz、
  domain 1/2 关闭）。

本端口没有 RPM/SPMI/GCC 驱动，因此 C1 的后续顺序确定为：

1. 用本次 dump 定位 GPUCC 的 branch clock / GDSC / 状态寄存器；
2. 实现 GPUCC 分支时钟与 GX 根时钟；
3. 实现 GDSC（CX/GX）上电与 reset；
4. 实现 RPM（msm8998 RPM message RAM）域/时钟投票与 PM8005 S1（SPMI）；
5. 之后才读 RBBM 版本并进 C2（固件/ZAP）。

```text
H221 kernel:  1aa2acdbf5aa7ee1cdf66c8d2cddf422c57bc33877a00cf498d89b6776d98681
H221 payload: 783b5d43c15b04f210bc62a553895c871f4778b64926d9127738e5071078e8b2
H221 boot:    3fb008527f04ed2b3deae6d1660d512bfc4b318394636340bb99c393a3475b4d
              81,147,904 B
```

### H221 结果：GPUCC 前 0x78 可读，之后总线挂死（2026-11-08）

扫描结果（写进日志、屏幕可见）：

```text
NATIVE_GPUCC: [0004]=0000001a  [0008]=0000001a  [000c]=00009187
NATIVE_GPUCC: [0010]=00004005  [0014]=20405699  [0018]=00002067
NATIVE_GPUCC: [001c]=40000000  [0030]=0000c555
NATIVE_GPUCC: [0044]=0000001a  [0048]=0000001a  [004c]=00000107
NATIVE_GPUCC: [0050]=00004805  [0054]=20405699  [0058]=00002067
NATIVE_GPUCC: [005c]=40000000  [0078]=0000c555
```

- `0x0000..0x0078` 可读，呈现**两组对称的 PLL 寄存器**（0x00–0x3C、0x40–0x7C，
  每组含 `20405699` 这样的 Fabia PLL 值）；
- 读到 `0x0078` 之后**总线挂死**（屏幕黑掉、无 panic 文本、adb/fastboot 均无响应）
  → 不能对该块做整段扫描；未上电时部分子块不可访问。

同轮还拿到 CPU 侧的真实读数（之前一直是 0）：

```text
NATIVE_CPUFREQ_OSM: c0/c1 全 0
NATIVE_CPUFREQ_APCS: cluster=0 pll_l=00000051 rcgr=00000301
NATIVE_CPUFREQ_APCS: cluster=1 pll_l=00000020 rcgr=00000403
```

### H222：GPUCC 定点读取（只读主线驱动实际访问的寄存器）（2026-11-08）

改用主线 `drivers/clk/qcom/gpucc-msm8998.c` 的寄存器表（msm8998 与 A540 同一块）：

| 名称 | 偏移 | 说明 |
| --- | --- | --- |
| gpupll0 | 0x0000..0x0020 | Fabia PLL（L 值/配置/状态） |
| gx_clamp_io | 0x0130 | GX clamp |
| cx_bcr / cx_gdscr / cx_gds_hw_ctrl | 0x1000 / 0x1004 / 0x1008 | CX 电源域 |
| cxo_branch | 0x1020 | XO 分支（关键时钟） |
| rbcpr_rcg / rbcpr_bcr / rbcpr_branch | 0x1030 / 0x1050 / 0x1054 | RBCPR |
| gfx3d_rcg / gx_bcr / gx_gdscr / gfx3d_branch | 0x1070 / 0x1090 / 0x1094 / 0x1098 | GX 域与 3D 时钟 |
| rbbmtimer_rcg / rbbmtimer_branch | 0x10b0 / 0x10d0 | RBBM 定时器 |
| isense_rcg / isense_bcr / isense_branch | 0x1100 / 0x1120 / 0x1124 | 电流感应 |

这些是时钟驱动必须能访问的寄存器（否则无法上电），定点读取应避免 H221 的挂死。

```text
H222 kernel:  c3a658ee34569daa6f01f99c5370a481c72bd6adb43d1c60c4158dc7f8a1955e
H222 payload: b9383d0a58133df8d94f18598d3473f440c240637d05ac425bcab15342b0dc23
H222 boot:    56212a70c55616165c84158391184d35ed473930d91c5725444d51176e0b5462
              81,147,904 B
```

### C1 基线读数完成（H222–H226，2026-11-08）

日志窗口的三种失败模式都踩过一遍，最终用"心跳行 + 寄存器序号"拿到完整读数
（`NATIVE_ACCEL_HB: … gc=<index>:<value>`，每拍一个）：

| 寄存器 | 偏移 | 值 | 含义 |
| --- | --- | --- | --- |
| gpupll0_lval | 0x0000 | 0x00000000 | Fabia PLL 未使能 |
| gpupll0_config | 0x0004 | 0x0000001a | |
| gpupll0_config_ctl | 0x0008 | 0x0000001a | |
| gpupll0_user_ctl | 0x000c | 0x00000107 | |
| gpupll0_user_ctl_u | 0x0010 | 0x00004805 | |
| gpupll0_state | 0x0014 | 0x20485699 | |
| gpupll0_status | 0x0020 | 0x00000000 | |
| gx_clamp_io | 0x0130 | 0x00000001 | **GX clamp 生效** |
| cx_bcr | 0x1000 | 0x00000000 | |
| cx_gdscr | 0x1004 | 0x00222001 | **bit0=1 → CX 域 collapsed** |
| cx_gds_hw_ctrl | 0x1008 | 0x00005ff4 | |
| cxo_branch | 0x1020 | 0x00000001 | XO 分支已开（bit31=0） |
| rbcpr_rcg | 0x1030 | 0x80000000 | 根时钟关闭 |
| rbcpr_bcr | 0x1050 | 0x00000000 | |
| rbcpr_branch | 0x1054 | 0x80000000 | 分支关闭（bit31=1） |
| gfx3d_rcg | 0x1070 | 0x80000000 | 根时钟关闭 |
| gx_bcr | 0x1090 | 0x00000000 | |
| gx_gdscr | 0x1094 | 0x00222001 | **bit0=1 → GX 域 collapsed** |
| gfx3d_branch | 0x1098 | 0x80000620 | **bit31=1 → 3D 时钟关** |
| rbbmtimer_rcg | 0x10b0 | 0x80000000 | 关闭 |
| rbbmtimer_branch | 0x10d0 | 0x80000000 | 关闭 |
| isense_rcg | 0x1100 | （H226 未捕获，H225 为 0x80000000） | 关闭 |
| isense_bcr | 0x1120 | （未捕获） | |
| isense_branch | 0x1124 | （未捕获） | |

结论与 sagit 的记录一致：**GPU 从未上电**——CX/GX 两个 GDSC 都是 collapse 状态、
GX clamp 生效、gfx3d 根时钟与分支全关，因此不能直接读 GPU 内部（RBBM）寄存器。

日志抓取经验（后续复用）：

1. 晚探针（~35 s）早于日志 ring 起点（~40 s）→ 打在晚探针的输出拉不到；
2. 一次打印 24 行（H223）会被写入器快照整批丢弃；
3. 缓慢分散打印（H224）会被 371 s 的窗口重置吞掉中段；
4. **把值放进心跳行 + 带序号**（H226）是唯一稳定的方式。

### H227：第一次 GPU 上电尝试（C1b，`sheng-gpu-power=1`，2026-11-08）

基线（H226）显示 CX/GX 两个 GDSC 都处于 collapse、GX clamp 生效、gfx3d 根时钟与
分支全关。H227 按最小序列尝试上电，**每个 beat 只做一步**（避免日志爆发被丢，
也让挂死位置可见）：

| 步 | 动作 | 寄存器 |
| --- | --- | --- |
| 0 | 打印初始状态 | 0x0130 / 0x1004 / 0x1094 / 0x1070 |
| 1 | 解除 GX clamp | 0x0130 = 0 |
| 2 | CX GDSC 上电 | 0x1004 bit0 清零并轮询 |
| 3 | gfx3d_clk_src ← XO（19.2 MHz） | 0x1074 = 0，0x1070 |= 1 |
| 4 | 打开 gfx3d 分支时钟 | 0x1098（bit0，另按 msm8998 probe 置 bit13） |
| 5 | GX GDSC 上电 | 0x1094 bit0 清零并轮询 |
| 6 | GX reset 脉冲 + 读 RBBM | 0x1090 → 0x5000000/0x0、0x4、0x210 |

用 `sheng-gpu-power=1` 门控（已写进 payload 的 `unixnu.toml`），默认启动行为不变。

风险：第 5/7 步进入 GX 域，而本端口还没有 RPM 的 CX/GX 电压投票；若在那些步骤挂死，
日志最后一行就是停点。

```text
H227 kernel:  014d8abb8a3794f3bf6d4f1192e392ef68ba2d49a00fa8e77d9a32e1b5cf7eaa
H227 payload: c581228a40e5a9c3497602987fcb7982487ed007422dc1576a2e4a85d914eb9b
H227 boot:    b243da94629202401ee9446eb3869542e3e76a5bdcb05877398291158a07aec7
              81,147,904 B
```

### H227/H228 结果：GDSC 已解除 collapse，但时钟不起、RBBM 全 0（C1b，2026-11-08）

H227（每 beat 一步）实测：

```text
start  clamp=00000001 cx=00222001 gx=00222001 gfx3d_rcg=80000000
step1  clamp now=00000000                 ← GX clamp 解除
step2  cx=18222000  collapsed=0           ← CX GDSC 的 SW_COLLAPSE 已清
step3  gfx3d_rcg=80000000 cfg=00000000    ← ROOT_OFF(bit31) 仍在
step4  gfx3d_branch=80002621 running=0    ← 分支 CLK_OFF(bit31) 未清
step5  gx=08222000  collapsed=0           ← GX GDSC 的 SW_COLLAPSE 已清
```

H228（清 ROOT_OFF + 轮询）结果相同，且 RBBM 三个字（hw_version/hw_release/status，
经 `gc=24/25/26` 通道输出）**全为 0**。

判读：

- 两个 GDSC 的 `SW_COLLAPSE` 位已清零，说明**时钟控制器层面已接受"上电"**；
- 但 `gfx3d_rcg`/`gfx3d_branch` 的 bit31 一直为 1，时钟没有真正输出；
- RBBM 读回 0（不是挂死），说明 GPU 域仍未被真正供电/授时。

下一步（C1c）需要按主线的 GDSC/RCG 语义补齐，而不是继续猜：

1. `gpu_cx_gdsc`/`gpu_gx_gdsc` 是 **VOTABLE** 类型，主线在 `gdsc.c` 里除清
   `SW_COLLAPSE` 外还要写 `gds_hw_ctrl`(0x1008) 的 vote 位；本端口只清了 bit0；
2. `gfx3d_clk_src` 的根需要由**父时钟**（gpupll0 输出或 XO 分支）真正产生；
   目前 `cxo_branch` 虽为 1，但根仍 off，需要确认 `CMD_RCGR` 的 bit31 语义
   （ROOT_OFF 还是只读状态）；
3. GX 域的电压来自 **RPM 的 CX/GX 投票**，本端口尚无 RPM 驱动——这很可能是
   "GDSC 显示已上电但时钟不跑、GPU 读回 0"的根本原因。

```text
H227 boot: b243da94629202401ee9446eb3869542e3e76a5bdcb05877398291158a07aec7
H228 boot: 119d1b59c6ed0c0d3fcbe7f40ee897c289a7a985940b66eddebf9dc69322a78f
          kernel eb5f04f9a2ee01232327ac4b46762706145638096a4c1b602a72c5bd7c2111df
```

### H229：GDSC 按主线 `gdsc.c` 语义重做（C1c-1，2026-11-08）

H227/H228 只清了 `SW_COLLAPSE`，没有读真正的电源状态位。按主线 `gdsc.c`：

- `PWR_ON = BIT(31)`；有 `gds_hw_ctrl` 的 GDSC（`gpu_cx_gdsc` = 0x1008）从该寄存器读，
  没有的（`gpu_gx_gdsc`）从自身 GDSCR（0x1094）读；
- 使能时还要写等待字段（EN_REST=2 @23:20、EN_FEW=8 @19:16、CLK_DIS=2 @15:12），
  并清 `HW_CONTROL`(bit1) 与 `SW_OVERRIDE`(bit2)；
- `SW_COLLAPSE = BIT(0)`，清 0 后延时 ≥1 µs 再轮询状态。

H229 的 `gpuGdscOn()` 完整实现上述步骤，并打印
`<name> gdscr <before>-><after> status[<reg>]=<value> on=<0|1>`。判读：`on=0` 说明
GDSC 没有真正上电（缺电压/投票），而不是"我们没清位"。

```text
H229 kernel:  90d86e92d3c9239a6539d4993edf44b5c3768b7117bc8d6d2d120754ce601a34
H229 payload: 581b44bb359c9f9e6cffb4f9b7aa33c9c2301a19226cb40eff7c923ea2f4784e
H229 boot:    e164c98340cdac6998654a6220607aa58a623078d8a1fbd3cb8e3150fed413b4
              81,147,904 B
```

### H229 结果：CX 域上电成功，GX 域缺电压投票（C1c-1，2026-11-08）

```text
start  clamp=00000001 cx=00222001 gx=00222001 gfx3d_rcg=80000000
step1  clamp now=00000000
step2  cx gdscr 00222001->a0282000 status[1008]=80001fe0 on=1   ← CX 真正上电
step3  gfx3d_rcg=80000000 cfg=00000000
step4  gfx3d_branch=80002621 running=0
step5  gx gdscr 00222001->08282000 status[1094]=08282000 on=0   ← GX 未上电
```

按主线 `gdsc.c` 的 `PWR_ON = BIT(31)` 判读：

- **CX 域成功**：`gds_hw_ctrl[0x1008]` 的 bit31 已置位（`0x80001fe0`），说明写序列
  （等待字段 + 清 HW_CONTROL/SW_OVERRIDE + 清 SW_COLLAPSE）是正确的；
- **GX 域失败**：`gdscr[0x1094]` 的 bit31 一直为 0，尽管 SW_COLLAPSE 已清。
  这与 msm8998 的供电结构一致：GX 轨由 **RPM** 投票供电，本端口还没有 RPM 驱动，
  所以 GDSC 的电源状态机等不到 "power up complete"。

因此 C1 的剩余工作明确为：**实现 RPM（msm8998 的 RPM message RAM + SMD/SMEM）
以完成 CX/GX 轨电压投票**，之后 gfx3d 根时钟（父时钟/ PLL）才有意义。

```text
H229 kernel:  90d86e92d3c9239a6539d4993edf44b5c3768b7117bc8d6d2d120754ce601a34
H229 payload: 581b44bb359c9f9e6cffb4f9b7aa33c9c2301a19226cb40eff7c923ea2f4784e
H229 boot:    e164c98340cdac6998654a6220607aa58a623078d8a1fbd3cb8e3150fed413b4
```

### H230：SMEM 只读探测返回全 0（C1d 第一步，2026-11-08）

按厂商 DTS 的 `qcom,smem@86000000`（2 MiB）做只读探测，结果经 `gc=30..35` 通道输出：

```text
gc=30/31/32 = 00000000    SMEM 头三字
gc=33/34/35 = 00000000    未找到 "COMM" 分区表魔数
```

- 映射成功（`IODeviceMemory` + cache-inhibit + 只读），读回 0 而不是挂死 →
  说明**该物理地址在本端口这次启动下没有 SMEM 内容**，而不是访问方式错误；
- 同轮 `gc=25/26` 有值（RBBM 由 step6 读取），说明探测代码确实执行了；
- 可能性：ABL 交给我们的 SMEM 基址与厂商内核看到的 `0x86000000` 不同，
  或 `fastboot boot` + 自有 ADT 的启动路径下 SMEM 未被放置在该地址。

下一步（C1d-2）：
1. 先确认映射机制本身可靠——用同样的方法读一个**已知内容**的 RAM 地址
   （例如 GPU addon 的 `0x185f58000`），若读出正确则说明 SMEM 地址确实不对；
2. 从启动时由 ABL 传入的 device tree（`PE_state.deviceTreeHead` 指向的原始 DT）
   里读 `qcom,smem` 节点，而不是用厂商 DTS 的静态值；
3. 找到真正的 SMEM 基址后，再解析分区表、定位 `rpm_requests` 的 GLINK 通道。

```text
H230 kernel:  21daac83c29de8f03ef267e3c01972c9566a662494d387ac7c698b78b3c98209
H230 payload: eaba1411c0be656423acbf03b9110b5966ccea0431263f6410bdf4c70540c9d1
H230 boot:    4a1dc266fb61229a14324b7cd3cfcaa9159f1c941affc1d62f47272fa504f489
```

### H231：映射机制验证通过，SMEM 区段为空（C1d-2，2026-11-08）

同一段代码、同一种映射（`IODeviceMemory` + cache-inhibit + 只读）读两个地址：

```text
gc=36/37/38 = 5550474e / 32444441 / 00000008   ← GPU addon 头 "NGPU" "ADD2" size=8 ✓
gc=30..35   = 00000000                          ← SMEM 头与 "COMM" 分区表全 0
```

结论：

1. **映射机制正确**：已知 RAM 读出了精确的 `NGPUADD2` 头，所以不是 device/cacheable
   属性问题；
2. **`0x86000000` 上的 SMEM 确实为空**。最可能的解释是该区段没有被 boot_args 的
   内存映射标记为保留，内核早期把它当可用 DRAM 使用/清零了（本端口没有 RPM 驱动，
   也从未与 RPM 通信，所以之前没人发现）。

下一步（C1d-3）有三个方向，都需要改**内存预留**，而不是继续读寄存器：

- **A**：在 boot_args 的内存映射里把 SMEM carveout（`0x86000000`+2 MiB）标为保留，
  让内核不碰它，然后重新探测 SMEM 是否恢复；
- **B**：若 ABL 在本启动路径下根本没有放置 SMEM，则需要像 Android 内核那样由
  bootloader 初始化 SMEM/RPM 握手，代价很大；
- **C**：绕开 RPM：确认 GX 是否还有其它上电路径（例如 GPUCC 内部 GDSC 的 votable
  位 + PM8005 S1 的 SPMI 直写），但这仍需要 SPMI 驱动。

```text
H231 kernel:  6a1966def36de08cea520ec5ef82f8c186c23667a2ee2f93807b8f367cc62f2a
H231 payload: 1d138ecf8d3a2fc7ab1e7d8b8824524461402fc6aa7bd879e172c511cc5b4113
H231 boot:    727aea72610c22bddf990511bd2d8e74bc3b6f8da80b533ebb3a28e85abf54dc
```

### C1d-3 方案 A 的可行性核查（2026-11-08）

查 `drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c`：loader **不构造**
`boot_args->MemoryMap`，`GetMemoryMap` 只用于给 `ExitBootServices` 取 Key：

```c
Status = gBS->GetMemoryMap (&MapSize, Map, &Key, &Stride, &Version);
...
Status = gBS->ExitBootServices (mImage, Key);
```

而 `osfmk/arm64/arm_vm_init.c` 里也没有任何 `MemoryMap` 的使用。也就是说本端口
给 XNU 的可用 DRAM 是"连续区间"（`gPhysBase` + ADT 的 `owned_memory_size`），
`0x86000000`（2.1 GiB）正落在区间内 → 被当作空闲内存使用/清零。

因此方案 A 不能只改 loader，需要在下面二者之一动手：

- **A1（内核侧）**：在 `arm_vm_init` 里把 SMEM carveout 从可用内存中挖掉
  （在建立空闲页之前标记为已用），需要确认 arm64 空闲页来源的确切代码路径；
- **A2（loader + 内核侧）**：loader 在 `/chosen/memory-map` 里加一个 `SMEM` 条目，
  内核在 `arm_vm_init` 里认识并保留它（与 TrustCache 同样的处理方式）。

两者都要改 `arm_vm_init.c`（敏感文件），建议先只做"读 + 打印"确认空闲页来源，
再决定挖洞位置。

### H232：VM 内存区间是 [6 GiB, 8 GiB)，SMEM 不在其中（C1d-3 探针，2026-11-08）

`arm_vm_init` 在交给 VM 前导出的四个数：

```text
gPhysBase   = 0x1_8000_4000     (6 GiB)
mem_size    = 0x8000_0000       (2 GiB)
avail_start = 0x1_8708_a000
avail_end   = 0x2_0000_4000     (8 GiB)
```

**结论修正**：VM 的空闲页区间是 `[0x18708a000, 0x200004000)`，SMEM 的
`0x86000000`（2.1 GiB）**远在区间之外**，因此"内核把 SMEM 当可用内存清零"的
推断不成立。

那 H230/H231 读到全 0 的原因只剩两种：

1. **SMEM 不在 `0x86000000`**（厂商 DTS 的地址不适用于本机 ABL / 本启动路径）；
2. 该地址虽在 DRAM 物理范围内，但本启动路径下 ABL 没有初始化 SMEM 内容。

低地址映射本身是可用的（显示后端的 framebuffer 就在 `0x9d400000`，一直正常），
所以不是"低内存读不到"。

下一步（C1d-4）验证哪一种：

- 用同样的探针读 **framebuffer 0x9d400000**（已知有开机画面内容）作为低内存对照组；
- 若对照组非 0 → 低内存可读，SMEM 确实不在该地址，需要从 ABL 的 DT 或其它来源
  取真实地址；
- 若对照组也是 0 → 说明本内核配置下只有 `[gPhysBase, avail_end)` 内的地址可读，
  低内存需要特殊映射。

```text
H232 kernel:  bb34d79f286c1ba10008950ac4f43bf9b44b66077d62bfe66ecff749fa0148d5
H232 payload: 0182e7b2060e384b404330486c20f425c3138bb590bec5fe60130621b9b472d6
H232 boot:    c5f080633a63318885323105eddf7bded7faa74fd595491121af2c8e8ddcdd15
```

### H233：低内存可读，SMEM 在 `0x86000000` 确实为空（C1d-4，2026-11-08）

三组对照读数（同一映射方式）：

```text
gc=36/37/38 = 5550474e / 32444441 / 00000008   ← GPU addon 头 "NGPU" "ADD2" ✓
gc=48/49/50 = ff808080 ff808080 ff808080        ← framebuffer 左上角 = 我们画的灰色 CPU 格 ✓
gc=30..35   = 00000000                          ← SMEM 头与 "COMM" 分区表为空
```

- **低物理内存可读**：framebuffer `0x9d400000` 读到的正是内核自己写进去的 `0xff808080`
  （OSD 灰色格），说明映射与总线访问都正常；
- 因此 SMEM 全 0 不是访问问题，而是**该地址在本启动路径下没有 SMEM 内容**；
- 结合 H232（VM 只有 `[6 GiB, 8 GiB)`），"内核占用/清零"的假设已排除。

结论：要在本端口用 RPM/GLINK，需要**真实的 SMEM 基址**，而它来自 ABL 的 device tree
——我们用的是自建 ADT，没有那份信息。

下一步的三个选项：

| 选项 | 内容 | 代价 |
| --- | --- | --- |
| D1 | 从 ABL 的 DT 取 SMEM 基址（需要让 loader 保留/转发 ABL DT 的相关节点） | 中 |
| D2 | 扫描低 DRAM 找 SMEM 头（`0x53544554`），失败则说明未初始化 | 低（可试） |
| D3 | 放弃 RPM，改用 GPUCC votable + PM8005 S1 的 SPMI 直写 | 大（新写 SPMI 驱动） |

```text
H233 kernel:  4edce4d234d9779b15829ea29d64a45dbac9ea1f06d86ed7d44f8f30213ff754
H233 payload: f0558a3a36754f32634317eb214f70604efefffb8c9591b664852b43c9df1353
H233 boot:    e96c22c67f15cc76f67ffbf1eeb4a4c214b0a8adfa340c7f0d09cf1e612b17bd
```

### H234：SMEM carveout 存在但全零（C1d-4b，2026-11-08）

扫描 `0x80000000`–`0xA0000000`（2 MiB 步进，命中 4 个即停）：

```text
gc=60     = 4                                  命中数
gc=61/62  = 80000000 / ffffffff
gc=63/64  = 80200000 / ffffffff
gc=65/66  = 80400000 / ffffffff
gc=67/68  = 80600000 / ffffffff
```

判读（重要区别）：

- `0x80000000` 一带读出 **`0xffffffff`** = 该段没有内存（未实现的 DRAM 窗口）；
- `0x86000000`（厂商 DTS 的 SMEM 基址）读出的是 **`0`**，不是 `0xffffffff`
  → 该段**有内存、内容全零**；
- 结合 H233（framebuffer `0x9d400000` 读到我们自己画的像素）与 H232（VM 只拥有
  `[6 GiB, 8 GiB)`）：SMEM carveout 存在，但在本启动路径下**没有被初始化**。

结论：RPM/GLINK 需要 SMEM 里由 ABL 建立的分区表与 GLINK FIFO，而本启动路径下
这份内容不存在（我们用的是自建 ADT，没有走 Android 内核那条 SMEM 初始化/握手的
启动链）。因此：

- D1（取 ABL DT 的 SMEM 信息）**不足以**解决问题——真正缺的是初始化；
- **建议转为 D3**：绕开 RPM，用 GPUCC 的 votable GDSC 位 + **PM8005 S1 的 SPMI 直写**
  给 GX 供电；SPMI 是纯寄存器接口，不依赖 SMEM。

```text
H234 kernel:  b26177e083e8462f881a6bb7aab84ea812e596dfeaf2ff7e9217a563bc174b56
H234 payload: fc4aa30a1f26c42bc2d827bceaf9be09e5c8b87cf4c0fd0216e3a45a1f825a1e
H234 boot:    173fd5448de0758485f8b17f5ca2147b5ce02a53b5420edb6ebb388f5aa3508c
```

### C1e 起点：SPMI 与 PM8005 的权威坐标（2026-11-08）

厂商 DTS（`cheeseburger.dts`）给出：

```text
qcom,spmi@800f000  compatible = "qcom,spmi-pmic-arb"
  core   = 0x0800f000  (0x1000)
  chnls  = 0x08400000  (0x1000000)     # 每个 slave 的通道页
  obsrvr = 0x09400000  (0x1000000)
  intr   = 0x0a400000  (0x220000)
  cnfg   = 0x0800a000  (0x3000)
  qcom,ee = 0 ; qcom,channel = 0 ; qcom,reserved-chan = 0x1ff
  interrupts = <0 0x146 0>

qcom,pm8005@5  (SPMI slave id 5)
  regulator@1400  regulator-name = "pm8005_s1"
    regulator-min-microvolt = 0x07dfa0 (515,000 µV)
    regulator-max-microvolt = 0x109a00 (1,088,768 µV)
    qcom,enable-time = 0x1f4 (500 µs)
```

GPU 的 `vdd`（第二路供电）就是 `pm8005_s1`；路线 C 计划 §4.2 也记为
`id=1 / sid=5 / 524000..1100000 µV`。

**实现要点（下一步 C1e-1）**：msm8998 的 SPMI 是 `spmi-pmic-arb`，不是直接内存映射，
写入要走 **APID 通道 + CMD/DATA 寄存器**（参考主线 `drivers/spmi/spmi-pmic-arb.c`）：

1. 由 SID=5 与 PMIC 寄存器地址 0x1400 算出 APID（arbiter 的 PPID 映射）；
2. 通过 `chnls` 里对应的通道页写 `CMD`，再从 `DATA`/`CMD` 写数据；
3. 读回校验；
4. 设定目标电压（S1 的最小档 515 mV 起步），再回到 GX GDSC 重试
   （`gx_gdscr[0x1094]` 的 bit31 应置位）。

这一步不依赖 SMEM/RPM，是当前唯一可推进的 GX 供电路径。

### H235：SPMI arbiter 可访问（C1e-1，2026-11-08）

只读探测 `qcom,spmi@800f000`（core）与 `0x800a000`（cnfg）各 4 个字：

```text
gc=70 (core+0x0) = 30000000
gc=77 (cnfg+0xc) = 0000ffff
```

- 读到的是**非零、非 0xffffffff** 的值 → SPMI PMIC arbiter 在本启动路径下**可访问**，
  不需要额外的 GCC 时钟使能就能读；
- 其余 6 个字被日志窗口吞掉（beat 丢失），但"控制器存在且可读"这一点已经确定；
- 后续写入需要 **APID 通道 + CMD/DATA**（`chnls` = 0x8400000，SID=5 的通道页），
  并遵守 EE/channel 仲裁与 TID 完成握手（参考主线 `drivers/spmi/spmi-pmic-arb.c`）。

C1e-2 的计划：

1. 由 SID=5、PMIC 地址 0x1400（pm8005_s1）算 APID；
2. 通过通道页写 CMD/DATA，读回校验（先写一个已使能位或已知的 CTRL 寄存器验证通路）；
3. 设定 S1 电压（515 mV 起步）→ 重试 GX GDSC（`0x1094` bit31 应置位）；
4. 成功后回到 GPUCC：Fabia PLL → 257 MHz → gfx3d 根/分支 → 读 RBBM → 进 C2。

```text
H235 kernel:  a6f3f5127141dad084e674586f06f0684f143957b6e4254154dafa6ce02d1780
H235 payload: c0afd4fd20192f159e0db44602376c68450a6f60d9f2d67b2a9f85a02bc48f1e
H235 boot:    19f1160d9f0bb48f19681d0a3e9176c0892f2f1267ab8fcf5a8382e0ca027da3
```

### H236：C1e-2 的 SPMI 传输与 PM8005 S1 实现（2026-11-08）

H235 读到 `core+0x0 = 0x30000000`，按厂商 `spmi-pmic-arb.c` 的版本判定这是 **v3**
（`>= PMIC_ARB_VERSION_V3_MIN`）。v3 的 PPID 映射、通道偏移和 CMD 格式与 v2 共用同一套
实现，因此下面按 v2 数据通路实现：

```text
PPID       = (sid << 8) | (addr >> 8)        sid=5, addr=0x1400 -> 0x514
通道页     = 0x8000 * apid                   (EE 0；EE n 再加 0x1000*n)
CMD        = (opcode << 27) | ((addr & 0xff) << 4) | (byte_count - 1)
             opcode 14 = 写，15 = 读
读         = obsrvr + 页 + {CMD 0x00, STATUS 0x08, RDATA0 0x18}
写         = chnls  + 页 + {WDATA0 0x10, CMD 0x00, STATUS 0x08}
STATUS     = bit0 DONE；bit1 FAILURE，bit2 DENIED，bit3 DROPPED
APID 映射  = core + 0x800 + 4*apid，PPID 位于 [19:8]（掩码 0xfff）
写拥有者   = cnfg + 0x700 + 4*apid，[2:0] 必须等于 EE 0
```

PM8005 S1（SID 5，外设基址 0x1400，`qcom,qpnp-regulator` 的公共寄存器布局）：

```text
0x1401 REV      0x1404 TYPE      0x1405 SUBTYPE
0x1440 RANGE    0x1441 VSET      0x1445 MODE (bit7=HPM)
0x1446 ENABLE (bit7=1)           0x1461 STEP_CTRL
电压 = 375000 + 12500 * VSET      (RANGE 0；RANGE 1 为 1550000 + 25000*VSET)
```

板级下限 `regulator-min-microvolt = <524000>`，12.5 mV 网格上第一个可选点是 **525000 µV
（RANGE 0 / VSET 12）**。`PM8005 S1 + S4 = 2 phase VDD_GFX`，本轮只驱动 S1 这一相。

新增的 `sheng-gpu-power` 取值（原有 `=1` 的 C1b/C1c 序列保持逐字节不变）：

| 值 | 行为 |
| --- | --- |
| 2 | 只读：APID/owner + S1 的 8 个身份/电压寄存器 |
| 3 | 在 2 的基础上，把 ENABLE 原值写回一次（验证 CMD/DATA 通路） |
| 4 | 在 3 的基础上，写 RANGE/VSET=525 mV → MODE HPM → ENABLE → GX GDSC → gfx3d 根/分支 → RBBM |

安全闸门：只有 8 个 S1 寄存器全部读成功、APID 的 owner 为 EE 0、TYPE/SUBTYPE 为
SMPS（0x03/0x08 或 0x09）、且 GX GDSC 仍处于 collapse 时，才会写 PMIC。任一条件不满足
都会在 `gc` 里留下 `0xdea000xx` 标记并停止。

结果从心跳行的 `gc=<index>:<value>` 输出，索引 **80..111**，按产生顺序优先于 GPUCC
的 24 个读数，因此即使日志窗口只保留心跳也能看到本次结果。索引分配：

```text
80 版本        81 PPID        82 APID        83 owner
84 clamp       85 cx_gdscr
86 rev         87 type        88 subtype     89 range
90 vset        91 mode        92 enable      93 step
94 当前电压µV    95 写通路状态    96 写回 enable
97 电压写/保持    98 range|vset<<8 99 mode写状态
100 enable写状态 101 enable回读  102 vset回读   103 mode回读
104 GX GDSCR    105 rcg 0x1070  106 cfg 0x1074 107 branch 0x1098
108 GX BCR      109 RBBM 0x0000 110 RBBM 0x0004 111 RBBM 0x0210
```

判读：`gc=80:30000000`、`gc=81:00000514`、`gc=83:00000000` 是通路成立的前提；
`gc=87:00000003`、`gc=88:00000008` 确认 PM8005 SMPS；`gc=104` 的 bit31 为 1 才表示
GX 真正上电。

**H236 构建（Mac `lss@192.168.10.103`，2026-11-08）**：`build-op5-legacy-display.py`
按 `-Werror` 重建 `libNativeLegacyDisplay.late.a`，`run-h103n-build.sh` 的环境
（含 `XNU_NATIVE_LEGACY_DISPLAY=1`、`XNU_OWNER_DATA_MOUNT=1`）完成内核链接，prelink
输出 `kernel.macho`。首轮编译暴露并修复了 `gSpmi2Count++` 在 C++20
`-Wdeprecated-volatile` 下的错误（改为局部计数再写回）。

构建机上 `build-xnu-4k-baseline.sh` 的补丁循环对已打补丁的树不是幂等的（`native-aes`
等 35 个 patch 在二次运行时冲突），所以本轮先 `git reset --hard d8b8029 && git clean -fdx`，
由 bootstrap 一次性应用全部 114 个 patch，再用 `XNU_SKIP_PATCH_LOOP=1` 跑最终构建；
`xnu-work` 的改动已备份在 Mac `~/h236-backup/`。这是构建机工作流问题，不是 C1e-2 代码问题。

产物（payload 以 H235 的 76 MiB FAT 为基线，只替换 `kernel.macho` 并把
`sheng-gpu-power=1` 改成 `2`；firmware 与 H235 相同，`fw-H103ea` 0x163917aa…）：

```text
H236 kernel  b2f8e50b7fb4f1cc0cd82250503176f3f5d135b1f52896adac0abe97ac35cbf5
H236 payload 971adcfee953bc630c1bbeb592f1ca557e273846cac0a10bacf245dcffb80c7e
H236 boot    ec605b344bc180c9c0bee2ae60c7f41f88b4c6fda972cff6c457d55987bcf9f0
```

同一打包方式重打 H235 得到 `19f1160d…`，与 STATUS 的 H235 boot 哈希一致，说明
boot 头/地址/固件基线与上一轮完全相同。

启动参数分别用：

```text
第一轮  sheng-gpu-power=2    只读 survey
第二轮  sheng-gpu-power=3    写通路验证
第三轮  sheng-gpu-power=4    525 mV + S1 使能 + GX 重试
```

每轮只改 payload 的 `unixnu.toml`（`kernel_args`）并重新打包 payload，不需要重新构建内核。
镜像已放到 Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H236.img`，手机当前在 TWRP
（adb `16149951 recovery`），待执行 `fastboot boot`。

### H236 结果：SPMI 读通路成立，S1 是 FTS426 而不是 GP_CTL SMPS（2026-11-08）

第一轮 `sheng-gpu-power=2`（只读）成功落盘，`NATIVE_BUILD: H236`，
`gc=80..94`：

```text
80 30000000   版本（v3 数据通路）
81 00000514   PPID（sid=5, addr>>8=0x14）
82 00000001   APID = 1
83 00000000   owner = EE 0（可写）
86 00000000   rev
87 0000001c   TYPE  = 0x1c  ← FTS，不是 BUCK/GP_CTL
88 0000000a   SUBTYPE = 0x0a ← FTS426
89 000000f0   0x1440 = 0xf0（16 位电压的低字节）
90 00000002   0x1441 = 0x02 → 0x02f0 = 752 mV
91 00000006   MODE = 6（common2 AUTO）
92 00000000   ENABLE = 0x00（未使能）
93 00000081   STEP_CTRL = 0x81
94 ffffffff   旧 8 位 RANGE/VSET 解码失败（range=0xf0 非法）
```

判读：

- **APID 映射/通道/EE 仲裁全部正确**：`0x514 → APID 1 → owner 0`，8 个读事务
  全部 `rc=0`；
- PM8005 S1 是 **FTS426（type 0x1c/subtype 0x0a，FTSMPS2）**，使用 common2 布局：
  `0x40/0x41` 是 16 位小端电压（mV），`MODE 0x45` 是 3 位 AUTO/HPM 选择，
  **不是** 8 位 RANGE/VSET；因此旧解码得到 `0xffffffff` 是预期结果，不是读失败；
- 当前寄存器已存 **752 mV**，MODE=AUTO(6)，ENABLE=0（轨未开）。

据此修正 mode 4：FTS426 走 `pm8005Voltage()`（16 位 mV）与 MODE=7(HPM)；
若已存电压在 500–1100 mV 内就**保留 752 mV**，只补 MODE/ENABLE，不再写电压。

根卷验证：干净重建漏掉了 `zzz-root-auth-bypass.patch`（`native-skip-root-auth`
不生效，`bsd_init.c:1103` panic）。补上该 patch 后重建得到 H236b
（kernel `1d452686…`），启动日志出现
`NATIVE_ROOT_AUTH_BYPASS: autherr=80`，不再提前 panic；H236b boot
`80618feb…`。这是构建补丁状态问题，与 SPMI 代码无关。

下一步：`sheng-gpu-power=3` 验证写通路（ENABLE 原值写回），再 `=4`
（保留 752 mV → MODE HPM → ENABLE → GX GDSC）。

### H236f：EXT_WRITEL 写通路成立，GX 首次 PWR_ON（2026-11-08）

PM8005 的 QPNP 寄存器用 **16 位寄存器号**（0x1446），厂商 regmap 走
`spmi_ext_register_writel`，对应仲裁器 **opcode 0（EXT_WRITEL）**。标准写
（14）和 8 位扩展写（2）都会返回 `STATUS DONE`，但 PMIC 不更新寄存器；这就是
H236d/H236e 里 `MODE 06->07`、`ENABLE 00->80` 读回仍是 6/0 的原因。

改用 opcode 0 后（kernel `6304a821…`，payload `cc3a44b9…`，boot `4d0e6697…`）：

```text
gc=99  00000007   MODE 写
gc=100 00000080   ENABLE 写
gc=101 00000080   enable 回读  ← bit7=1
gc=102 00000002   vset 回读（752 mV）
gc=103 00000007   mode 回读（HPM）
gc=104 a0282000   GX GDSCR，bit31=1  ← GX PWR_ON
gc=105 80000000   gfx3d_rcg（根仍 off）
gc=106 00000000   gfx3d cfg（XO）
gc=107 80002621   gfx3d_branch（写后；后续 GPUCC survey 读到 00002621）
gc=108 00000000   GX BCR
gc=109 00010042   RBBM 0x0000
gc=110 b5f00000   RBBM 0x0004
gc=111 00000000   RBBM 0x0210
```

结论：

- **C1e-2 完成**：S1 在 752 mV 使能，GX GDSC 首次置 PWR_ON，RBBM 能读；
- `gfx3d_branch` 的 bit31 最终清掉（GPUCC survey 的 0x1098 = 0x00002621），
  但 `gfx3d_rcg`(0x1070) 仍是 0x80000000；根时钟的父时钟（gpupll0/Fabia）
  `lval=0`、`status=0`，仍未起振；
- 下一步 C2：Fabia PLL → 257 MHz、gfx3d_clk_src 分频、根时钟使能，再读 RBBM
  确认 A540 ID 并进入 GMU/CP。

### H236g：Fabia PLL 与 gfx3d 根/分支时钟（C2，2026-11-08）

H227 只清了 `CMD_RCGR` 的 **bit31**（这是只读的 ROOT_STATUS），没有置 **bit1**
（ROOT_ENABLE），所以根时钟一直显示 `0x80000000`。正确语义是：

```text
0x1070 CMD_RCGR : bit0 = CONFIG_UPDATE，bit1 = ROOT_ENABLE，bit31 = ROOT_STATUS (RO)
0x1074 CFG_RCGR : [4:0] div，[10:8] src（1 = gpu_pll0 的 even 输出）
```

C2 序列（kernel `8147dc53…`，payload `93a7ce42…`，boot `4dd225e2…`）：

1. Fabia PLL：L=53、alpha=0x8aab → VCO 1028 MHz；USER_CTL_LO 的 even post-div=1
   （/2）→ 514 MHz；置 RESET_N、OPMODE=RUN，等 LOCK；置 OUTCTRL；
2. RCG：CFG=0x101（even 源、div 1 → 257 MHz），CMD 先 update 再置 ROOT_ENABLE；
3. branch：0x1098 bit0+bit13；4. GX reset + RBBM。

实测：

```text
gc=105 d0000005   PLL MODE：bit31 lock=1，bit30 active=1，bit0 outctrl=1
gc=106 00000035   PLL L=53
gc=107 00000002   RCG：ROOT_ENABLE=1，ROOT_STATUS=0
gc=108 00000101   CFG：even 源、div 1
gc=109 80002621   branch 写后立即读（bit31 仍 1）
gc=110 00000000   GX BCR
gc=111..113       RBBM 00010042 / b5f00000 / 00000000
```

后续 GPUCC survey（同一 boot）：

```text
gc=15 00000002    gfx3d_rcg 根已开
gc=18 00002621    gfx3d_branch 已开（bit31=0）
gc=17 a0282000    GX GDSCR PWR_ON
```

结论：**C2 的供电+时钟链路打通**：S1 752 mV → GX GDSCR PWR_ON → Fabia PLL 锁定
→ gfx3d 根 257 MHz → 分支使能 → RBBM 可读。RBBM 身份为 `0x00010042 /
0xb5f00000`。下一步 C3：从 RBBM/GMU 读 GPU ID，启动 GMU/CP。

### H236h：C3 第一步，只读 A5xx CP/GPMU survey（2026-11-09）

新增 `sheng-gpu-power=5`：先跑完 C2（S1→GX→PLL→根/分支），再只读 A5xx 的
CP/GPMU/RBBM 寄存器。寄存器偏移按 `a5xx_reg.h` 的 **dword 索引 ×4**：

```text
0x2000 cp_rb_base        0x2008 cp_rb_cntl      0x2018 cp_rb_rptr
0x201c cp_rb_wptr        0x20c8 cp_me_cntl      0x20d4 cp_pfp_instr_base
0x1384 rbbm_int0_status  0x13d4 rbbm_status      0x14c0 rbbm_status3
0x2a360 gpmu_cm3_sysreset 0x2a380 gpmu_general0  0x2a384 gpmu_general1
0x22000 gpmu_inst_ram0
```

结果接在 C2 的 `gc=113` 之后：`gc=114..126`，每个心跳一个寄存器。没有写任何
CP/GPMU 寄存器；如果某块未授时钟，读会挂住，最后一个 `gc` 就是停点。

产物（未上机；手机已断开）：

```text
H236h kernel  f9f4e043c0ee32a0a82e3de099e55920b4c14f5bbf49ef6d1511df38845edd02
H236h payload fd190a4269fd89e4d99d57a85f3df1a91960babdf7824010aadc0532c334220d
H236h boot    bf2faa24f2ac892dbb2213549a907535d2c2ada81b5e950b4e1e8bb7afb3f298
```

镜像已放到 Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H236h.img` 和
Mac `~/h103/boot-H236h.img`，明天直接 `fastboot boot`。

C3 后续（已查厂商 kgsl）：

- A540 的 chip ID 来自 DT `qcom,chipid = <0x05040000>`；固件为
  `a540_gpmu.fw2`（GPMU 3.0）、`a530_pm4.fw`、`a530_pfp.fw`、`a540_zap`；
- GPMU 固件不是 CPU 直接写入，而是由 **CP** 用 type4 包写进
  `A5XX_GPMU_INST_RAM_BASE`；所以顺序必须是 RBBM/CP 复位 → PM4/PFP 微码 →
  ringbuffer → GPMU 固件 → `GPMU_CM3_SYSRESET=0`，等
  `GPMU_GENERAL_0 == 0xBABEFACE`；
- 这比 C1/C2 大一个量级，下一步先看 H236h 的 13 个读数确认 CP/GPMU 窗口可访问，
  再写 RBBM/CP 复位。

### H236k/H236m：热复位修复与 CP 块写入（C3 第二步，2026-11-09）

连续 `fastboot boot` 后出现早期卡住：新 boot 只写 1–2 个 slot，停在 S1 的
`0x1440` 读之前。原因是上一轮把 S1 留在使能状态，FTS426 在带电时的电压寄存器读
不可靠。修复：在 APID/owner 确定后、读 S1 之前先 **写 ENABLE=0** 关掉 S1；同时把
C2 做成幂等（PLL 已锁定在 L=53 时跳过重配；重配前先关根/分支）。

H236k（mode 5，kernel `7ec9a479…`，boot `aeec61ef…`）验证修复：

```text
s1 pre-disable rc=0 status=1
s1 rev/type/subtype/range/vset/mode/enable/step 全部 rc=0
c3 cp_rb_base..gpmu_inst_ram0 13 个读数完整
```

H236m（mode 6，kernel `c199d40a…`，boot `52e4af15…`）做 **不带软复位的 CP
块写入测试**：

```text
c3 reset skipped rbbm=00000001 cp=00000303
c3 cp thresholds cp=00000303          ← 4 个 A540 阈值写入未挂总线
c3 state rbbm=1 cm3=1 gen0=0 cp=0x303
```

结论：

- CP/GPMU 窗口可读可写，写入阈值不会挂总线；
- **不要单独发 `RBBM_SW_RESET_CMD`**：厂商的 `_soft_reset` 会复位整个 GPU 逻辑，
  必须紧跟完整的 a5xx 重启（电源状态、VBIF、微码、ringbuffer）；单独复位后读
  总线会挂（H236l 已实测）；
- 下一步 C3：GPU 可见内存 + SMMU 映射 + CP ringbuffer + `a530_pm4/pfp` 微码，
  再加载 `a540_gpmu.fw2`。这部分在离线实现，不再盲写寄存器。

### H236o/H236p/H236q：C3 四块代码上线，SMMU context 待调（2026-11-09）

新增文件：

- `drivers/NativeMobileDisplay/NativeA540C3.cpp`：GPU 可见内存（IOBufferMemoryDescriptor）、
  A540 SMMUv2（ArmSmmu4K kit）、CP ring/`a530_pm4/pfp` 微码、`a540_gpmu.fw2` 加载；
- `scripts/gen-a540-firmware.py`：从 `.cache/firmware/a540/` 生成
  `A540FirmwareBlobs.h`（厂商固件不提交）；
- `scripts/build-op5-legacy-display.py`：生成固件头、编译 C3 源和 ArmSmmu4K kit，
  并把对象加入 late archive（archive 成员集因此变化）。

`sheng-gpu-power=7` 在 C2 之后运行 C3。H236o 先加入 **C2 preclean**（拉 clamp、
关 root/branch/PLL、collapse GX），修复了热复位后 PLL/RCG 卡住的问题；H236o/p
的 C2 完整走到 `pll d0000005 / rcg 00000002 / branch 00002621 / rbbm`。

H236p 的 C3 结果（boot `2e9c1415`）：

```text
tables/ring 分配成功
SMMU ID0=00188c41  ID1=00188c81  ID2=48016403
ArmSmmu4KProgramDisabledContext -> 失败（step 5, smmu context）
```

H236q（kernel `8fe04d61…`，boot `cf35be9b…`）在失败点记录
`status/phase/fault_status/sCR0`，已放到 Windows `192.168.8.58`。
下一步先看这四个值：最可能是 A540 SMMU 的 ID0 能力位、bank0 已被固件使能，
或 sCR0 策略与 kit 的 `0x406` 要求不一致；确认后调整 context 或改用只读
`ObserveOwnedContext` 复用固件留下的映射。

### H236r：C3 跑到 SMMU，kit 的 ID 假设与 A540 不符（2026-11-09）

C3 改到独立内核线程后，心跳不再被阻塞；H236r（kernel `9d85ae9d…`）完整记录：

```text
NATIVE_GPU_C3: thread start
NATIVE_GPU_C3: alloc tables
NATIVE_GPU_C3: alloc ring
NATIVE_GPU_C3: smmu setup
NATIVE_GPU_C3: smmu context status=6 phase=1 fault=00000000 scr0=00200626
NATIVE_GPU_C3: fail step 5 (smmu context)
```

- `status=6` = `ArmSmmu4KUnsupported`，`phase=1`：失败在 `ArmSmmu4KEncodeContext` 的
  ID 能力检查，**还没写任何 SMMU 寄存器**；
- 读到的 `ID0=00188c41`（bit30=0）、`ID1=00188c81`、`ID2=48016403`（bit12=0）；
  ArmSmmu4K 要求 ID0 bit30 与 ID2 bit12，这是 sheng 的 MMU-500 的假设，msm8998
  的 `qcom,smmu-v2` 不满足；
- `sCR0=00200626`：`(sCR0&0x407)==0x406` 成立，全局策略本身没问题；
- 分配（table pool/ring/ucode/GPMU）和 SMMU 表构建都已通过。

结论：C3 的内存、CP、GPMU 代码都已就位，当前唯一阻塞是 **A540 SMMU 的 context
编码**。下一步先做只读 SMMU 布局 survey（global 0x0..0x100 与 CB0 0x6000..0x6100），
确认 Qualcomm 版的 ID/CB 偏移，再按厂商 `attach-impl-defs` 直接写 CB0；不再依赖
ArmSmmu4K 的 ID 检查。

### H236s/H236t：直接 SMMU 编程仍卡住（2026-11-09）

- H236s（线程版 + 直接 SMMU）：C3 线程启动后没有第一条日志，疑似
  `kernel_thread_start`/kevent 上下文不稳；
- H236t（同步版 + 直接 SMMU）：C2 完整通过，C3 调用把心跳阻塞约 70 秒
  （日志 slot 从 67 s 直接跳到 139 s），随后系统继续到 launchd/backboardd；
  没有 `NATIVE_GPU_C3` 行，说明直接写 CB0（GR1=0x1000、CB0=0x8000、
  SMR/S2CR=0x800/0xC00）在总线/寄存器层面卡住或不返回。

结论：C3 的内存/CP/GPMU 代码已就位，但 **A540 的 qcom,smmu-v2 不能按
ARM MMU-500 的 CB0 布局盲写**。下一步必须先把厂商 `drivers/iommu/arm-smmu.c`
的 msm8998 路径（`qcom,skip-init`、`attach-impl-defs`、CB 偏移、secure/ATS）
移植/对照清楚，再做只读 survey；在拿到 CB0 实际偏移和使能状态前，不再写
SMMU 寄存器。

### H236u：msm8998 GPU SMMU 厂商路径对照与只读 survey（2026-11-09）

新增诊断文档 `diagnostics/A540-C3-smmu-vendor-path-2026-11-09.md`，把 H236t 之后
的三个问题一次查清：

1. **谁驱动 A540 的 SMMU**：本地 ROM DTB 里同时存在 `qcom,kgsl-iommu`
   （`qcom,kgsl-smmu-v2`）和 `arm,smmu-kgsl@5040000`（`qcom,smmu-v2`）。
   `qcom,kgsl-iommu` 的子节点 `iommus` 指向后者（phandle `0x1b5`），所以寄存器
   由 `drivers/iommu/arm-smmu.c` 驱动；kgsl 只通过 IOMMU API 建 domain。
2. **真实布局**：`GR1 = base + 0x1000`、`CB0 = reg_size/2 = 0x8000`、
   `CBn = 0x8000 + n*0x1000`、`SMR = 0x800+4n`、`S2CR = 0xc00+4n`、
   `CBA2R = GR1 + 0x800 + 4n`、`IMPL_DEF1 = base + 0x6000`。H236t 的 CB 偏移
   本身没有错。
3. **写之前必须知道的状态**：DT 给 GPU SMMU 标了
   `qcom,skip-init` + `qcom,dynamic` + `qcom,register-save`。`dynamic` 路径下
   `arm-smmu.c` **不写 SMR/S2CR**，即 SID 0 → CB0 的映射由 bootloader/TZ 预留；
   `attach-impl-defs` 写入前厂商会先 `arm_smmu_halt()`（0x6000 bit2，等 bit3）。
   对已 enabled 的 bank 写 `CBA2R/CBAR` 是 architecturally unpredictable，
   与 H236t 的 70 秒心跳阻塞吻合。

ID 读数仍异常：`ID1=00188c81` 解出 NUMCB=129 > 页数=2，`ID2=48016403` 的 OAS=0
且保留位被置；这组值不能当真实 ID。H236u 因此加入 **只读 survey**：

- `sheng-gpu-power=8`，C2 之后每个心跳只读一个寄存器，经 `gc=80+k` 输出；
  即使某个读卡住，之前的值已在上一拍打印；
- 读 GR0 `0x000/0x020..0x02c/0x048`、`+0x400` NS 别名、SMR/S2CR 0..2、
  CBAR0/CBA2R0、`0x2000`、`0x6000`、CB0 `0x8000..0x8058`、CB1/CB2 SCTLR，
  并把 `ID0`/`CB0.SCTLR` 各重复读一次；
- `smmu_direct()` 先读 `CB0.SCTLR`，bit0=1 时直接 `fail step 9 (cb0 enabled)`，
  不再触碰 enabled bank。

构建（Mac `lss@192.168.10.103`）：

```text
H236u kernel  8f35f4d8302b2071bae43c828f75cc71d99b47bbc4569459112b4fe345f74d6a
H236u payload 9f3ba3c8fca1dec50f9b47b328a53b9d136bb92f3da7a9f10414bd7a81a24d37
H236u boot    8aba74fd41e9f1f48d9c6cb0da223a3268d37be94b86ff2ce99c1508f960d83a
```

payload 的 `unixnu.toml` 已加入 `sheng-gpu-power=8`（payload 重新打包后哈希
如上），镜像已放到 Windows `192.168.8.58` 的
`D:\Users\ls\Documents\OnePlus5_ios\boot-H236u.img`。

判读：看 `NATIVE_ACCEL_HB: ... gc=80:<value>` 到 `gc=111`，对照诊断文档 §7 的
表格；关键四个值是 `cb0_sctlr`(gc=100)、`smr0`(gc=90)、`s2cr0`(gc=93) 和
`micro_mmu_ctrl`(gc=99)。

### H236v/H236w/H236x/H236y：SMMU 几何确认、survey 与 C3 重新执行（2026-11-09）

H236u 之后连续踩了两个构建/打包问题，先把它们记下来：

- **H236u(u1) panic**：直接用 `unixnu build payload` 默认参数重建，payload 里只剩
  `kernel.macho` 和 `kernel.macho.adt`，丢了 H236t 的
  `kernel.macho.trustcache`、`scratch-data.img`、`kernel.macho.gpuaddon`；
  内核在 `kern_trustcache.c:1051` 报 `property lookup failed -1`。**以后必须从
  H236t 的 payload 复制后只替换 kernel/toml，或显式传三个输入。**
- **H236u(u2) panic**：最早一次 `./unixnu build kernel` 跑 patch loop 时在
  `KernelConfigTables.cpp:61` 失败；失败前 loop 已把 10 个 `zzz*/zzy*` 后置
  patch 反向卸掉，随后一直用 `XNU_SKIP_PATCH_LOOP=1` 构建，导致
  `NATIVE_ROOT_AUTH_BYPASS` 不存在，在 `bsd_init.c:1103` panic。修法：删掉
  `.cache/xnu-work`，从干净 XNU 重新 clone 并完整应用 patch，再全量编译。
- **H236v**：干净树重编，`strings` 确认 `NATIVE_ROOT_AUTH_BYPASS` 存在；但
  重建环境漏了 `XNU_OWNER_CACHE_CARRIER=1`，H236x 又在 launchd 阶段报
  `Library not loaded: /usr/lib/libSystem.B.dylib (no such file, no dyld cache)`。
  `offline-owner-cache-carrier.patch` 没有这个 define 时整段被编译掉，正是
  文档 B5 里的旧 `no dyld cache` 现象；H236y 已补上
  `XNU_OWNER_CACHE_CARRIER=1` / `..._WRONG_UUID=0`。

survey 结果（H236x，`sheng-gpu-power=8`，每心跳读一个寄存器）：

```text
sCR0 = 00200626
ID0  = 48016403   S1TS=1 SMS=1 CTTW=1 NUMSMRG=3
ID1  = 20008003   PAGESIZE=4K, NUMPAGENDXB=2 -> 8 页 (size=0x10000),
                  NUMCB=3, NUMS2CB=0
ID2  = 00007511   IAS=36, OAS=36, UBS=48, PTFS=4K/16K/64K
sGFSR= 00000000
SMR0..2  = 00000000   (invalid)
S2CR0..2 = 000200ff   (type=FAULT, cbndx=0xff)
CBAR0    = 00000000
CB0 TTBR0/TTBCR/CONTEXTIDR/FSR = 00000000
CB1/CB2 SCTLR = 00000000
```

结论：

1. **CB0 = 0x8000 由 ID1 几何直接确认**（8 页，size/2）；
2. **bootloader 没有留下任何映射**：SMR 全 invalid、S2CR 全 FAULT、CB0 关，
   所以不能“复用固件映射”，必须自己写 CB0 + SMR/S2CR；
3. ID0 bit30 与 ID2 bit12 都满足，`ArmSmmu4K` 现在会通过 ID 检查；之前
   H236r 的 Unsupported 是当时读到 `00188c41/48016403` 的错误值造成的；
4. H236w 在读完 ID2 后读 `0x02c (ID3)` 把总线挂死（黑屏）：这个 SMMU 只有
   ID0..ID2，ID3 未实现。H236x 已把 `0x02c`、`0x400` NS 别名、`0x2000`/
   `0x6000` 从未验证地址中删除。

H236y 的 C3 修改：

- `ArmSmmu4KConfig.output_bits = 36`（原 40 超过 ID2.OAS）；
- 先把 `S2CR0` 写成纯 `0x00020000`（FAULT），满足 kit 的 attach 前置条件；
- 写 `CB0 ACTLR = 0x70000000`（vendor `SMMU_MODEL_QCOM_V2`，kit 不含 ACTLR）；
- 用 `ArmSmmu4KAttachStreams` 发布 SID 0 → CB0；
- 编译环境补 `XNU_OWNER_CACHE_CARRIER=1`。

产物：

```text
H236x kernel  d0df547ffa547886ead9342c827514fd4a54530431606a1a73897becb74ed35a
H236x boot    ad3b72fc06ece6e87fbaff2684ede87109a9abdbd9a797df8d5cba1997364133
H236y kernel  4c217f92db7bae6bb7ecb918e5a0bd814fc181c9520511632217864274822543
H236y payload fc092afd883c98ddf5a7baffc4c0966ec66b42a6004653a100d0e15085b7bb98
H236y boot    9fc64a864ec364331b3bada40f4410f2db86b2e42ea1bc3c740c260034ee5204
```

H236y 用 `sheng-gpu-power=7`（C3），已在 `2026-11-09` 启动；下一步看 C3 是否
越过 SMMU 进入 `cp me init` 和 GPMU `BABEFACE`。

### H236z-H236am：C3 的 CP 启动与平台复位限制（2026-11-09）

在 H236y 把 SMMU context/route 打通之后，C3 继续推进到 CP：

- `ArmSmmu4KAttachStreams` 在这个 SMMU 上返回 Busy：FAULT 类型的 S2CR 读回
  `0x000200ff`（cbndx=0xff），kit 要求“正好 FAULT”。改为手工发布
  `S2CR0=0`（translation → CB0）和 `SMR0=0x80000000|SID0`，读回校验通过。
- CP `ME_INIT` 一直不消费（RPTR=0）。逐项排除：
  - 队列阈值（MEQ/MERCIU/ROQ）已补，无效；
  - SMMU 侧无 fault：`sGFSR=0`、`CB0.FSR=0x400`、`FAR=0`，CP 根本没发起取指；
  - `CP_ME_CNTL` 写 0 后读回 `0x404`，ME 未进入运行空闲态。
- 按 sagit 参考补上 reset/configure 语义（只按寄存器语义重写）：
  - `CP_ME_CNTL=0x303` + `VBIFHalt=0xf` 均能 ACK（`me=0303 ok=1`、
    `vbif=000f000f ok=1`）；
  - `RBBM_SW_RESET_CMD` 写 1 就挂总线：用 `native_log_flush_hook()` 逐步落盘后，
    最后一行稳定是 `reset w1`，dummy read 之前就断；去掉 dummy read 也一样；
  - 块复位（`RBBM_BLOCK_SW_RESET_CMD=0xffdffc0`）同样挂；
  - 跳过复位时 CP 仍然不取指（`gfsr=0` 证明不是 SID/映射）。
- 发现 GCC GPU 内存分支被 bootloader 关闭：`gcc_bimc_gfx_clk`（0x46040）
  读 `0x80000000`（bit31=halt，bit0=0），置位后读回 `0x00000001`；
  `gpu_cfg_ahb`/`gpu_bimc_gfx`/`bimc_gfx_src` 本来就在跑。H236am 已在 reset 前
  使能并打印，但 `RBBM_SW_RESET_CMD` 仍然一写就挂。

结论：**从 XNU（AP 非安全侧）不能对这个 OP5 的 A540 发 RBBM 软复位**。sagit 的
实现是在 **EFI 阶段**（ExitBootServices 之前）完成真实复位和 GPU/CP/GPMU 启动，
XNU 只接管已运行的引擎；这与当前现象一致，也说明下一步必须把
`reset → configure → CP/GPMU` 移到 `edk2-msm8998` 的桥/loader 里，或者先查清
OP5 的 GPU XPU/TZ 是否把 `RBBM_SW_RESET_CMD` 保护为仅 secure 可写（若是则需
SCM/PIL 路径）。

同时保留的成果：

- C3 的 GPU 内存（32 KiB ring、PM4/PFP/GPMU buffer、RPTR）和 SMMU 表/context/route
  已完整可用；
- `sheng-gpu-power=8` 的只读 survey 可复用；
- 复位/启动链每一步都有 `native_log_flush_hook()` 落盘，后续任何实验都能看到
  最后成功的步骤。

产物（供下轮复现）：

```text
H236am kernel  9f10f87d2585d0043ccab4328fb852f64339e571e4aeba05c87c08318f296624
H236am boot    ac3a9670ab5dde1059730d69ac8a6adea6aebe49a1821b3b590ae83a9c9c944b
```

### H236an：去掉 reset 脉冲之间的 log flush（2026-11-09）

H236am 的结论是“写 1 就挂总线”，但代码里 `wr(1)` 和 `wr(0)` 之间还有
`IOLog("reset w1 done")` 和 `native_log_flush_hook()`。落盘的最后一行恰好是
flush 之前的 `reset w1`，而 flush 是 UFS 的 DMA/设备写；它可以排在尚未完成的
复位写之后，所以“挂住”的可能不是 `RBBM_SW_RESET_CMD`，而是这次 flush。
H236al 的“去掉 dummy read”版本仍然保留了这条 flush，因此不能区分两者。

H236an 的改动（`NativeA540C3.cpp`）：

- `wr(RBBM_SW_RESET_CMD, 1)` → CPU-only `yield` 延时 → `wr(..., 0)` → 延时，
  中间不 log、不 flush、不读寄存器；
- 释放后才落盘 `reset writes done`，再读回 `RBBM_SW_RESET_CMD` 并打印
  `reset pulse released rst=%08x`；读回非 0 直接失败；
- 因此最后一行停在哪里就是明确的判据：
  - 停在 `reset pulse begin`：脉冲本身（或它造成的 NoC 停滞）挂总线；
  - 看到 `reset writes done` / `reset pulse released rst=00000000`：之前的
    “挂”是 flush 排在未完成的复位写之后，复位可用。

产物（firmware 沿用 `fw-H103ea.img.gz-dtb`，sha256 `163917aa…`；payload 以
H236am 的 76 MiB FAT 为基线，只替换 `kernel.macho`，`sheng-gpu-power=7` 不变）：

```text
H236an kernel  db750a0f6bd48dab199f6b7fda5f102f729c9d4d22083016fcbff135bc33fc9d
H236an payload 211d12e75b0af4d3d97c51892bb9f4144dd33c195ffeddd300181a39acb3af45
H236an boot    736eabecafbd132201d5c1c192bbb1b9f4f13f9a5ec19ad414558895f736ed5a
```

镜像在 `/tmp/opencode/boot-H236an.img`（`boot-H236an.json` 为打包报告），
待 `fastboot boot` 实测。若复位通过，C3 后续仍要解决 ME_INIT 不消费；若复位
仍挂，再把 `reset → SMMU → configure → CP/GPMU` 移到 UEFI，或先查 secure/XPU。

**Mac 构建注意（H236an 起固定）**：`build-xnu-4k-baseline.sh` 的 patch 循环对
已打补丁的 `.cache/xnu-work` 不是幂等的，会在 `iokit/KernelConfigTables.cpp`
上失败；失败时它可能已经反向卸掉 `zzz*` 后置 patch（H236v/H236an 都踩过）。
因此：

```sh
# 正常重建（xnu-work 已经是完整 patch 状态）
XNU_SKIP_PATCH_LOOP=1 bash ~/run-h103n-build.sh

# 只有在需要重新应用全部 patch 时，才先删树再完整跑一次（不带 SKIP）
rm -rf ~/UniXNU/out/cheeseburger/tree/.cache/xnu-work
```

`~/run-h103n-build.sh` 已加入 `export XNU_SKIP_PATCH_LOOP=1`。本轮旧树备份在
`~/UniXNU/out/cheeseburger/tree/.cache/xnu-work.partial-h236an`，不要直接再用。

### H236an 结果与 H236ao：补齐 sagit 的 GPUCC/GCC 时钟（2026-11-09）

H236an 实测（`sheng-gpu-power=7`）：

```text
[ 60.670206] reset halt write me=00000303 vbif=000f0000
[ 60.754403] reset halt me=00000303 ok=1
[ 60.836878] reset vbif=000f000f ok=1
[ 60.919525] reset pulse begin
（之后无 reset writes done）
```

去掉了两次写之间的 log/flush 后仍然停在 `reset pulse begin`，所以“写 1 挂总线”
不是 flush 造成的假象；H236am 的结论成立。

但和 sagit 的 EFI 启动相比，我们的 C2 只开了 gfx3d，缺少 sagit
`PowerStartup::start()` 里的 GPUCC 时钟：

- `gpucc_cxo_clk`（0x1020 bit0）
- `rbcpr_clk`（0x1054 bit0）
- `rbbmtimer_clk`（0x10d0 bit0）
- CX/RBCPR reset 解除（0x1000=0、0x1050=0）
- GCC `gcc_gpu_gpll0_clk`（0x5200c bit4）

H236ao 在 C2 的 step 22 和 C3 的 `gpu_reset()` 里补齐这些并使能后读回记录。
如果 RBBM reset 的握手依赖其中某个时钟，这一步会解开；否则才把整条链搬到 UEFI。

产物（firmware `fw-H103ea` 不变，payload 以 H236an 为基线只换 kernel）：

```text
H236ao kernel  5d7ef0e87094adf00b59b31cd710128aeb35d56a071f407176984792631a2336
H236ao payload 399cffc25215c899b74d331ceea61c24f7d2c7ecdee7f2771304d63de1fc6475
H236ao boot    208bbf773641e3b8e2d49dc3a200eb8534e873748016ff9655ee2e968ff684bd
```

镜像在 `/tmp/opencode/boot-H236ao.img`。若日志出现
`gpucc ... cxo=... rbcpr=... rbtimer=...` 且 reset 释放，则继续 C3 的 ME_INIT；
若仍停在 `reset pulse begin`，下一步进入 UEFI 侧 `reset → SMMU → configure → CP/GPMU`。

### H236ao 结果与 H236ap：CP 已经取指，等待时间补足（2026-11-09）

H236ao 日志：

```text
[ 67.274709] NATIVE_GPU_PWR: c1e2 gpucc cxrst=00000000->00000000
             rbcrprst=00000000->00000000 cxo=00000001->00000001
             rbcpr=80000000->00000001 rbtimer=80000000->00000001
[ 69.026583] NATIVE_GPU_C3: reset pulse begin
[ 69.111677] NATIVE_GPU_C3: reset writes done
[ 69.169200] NATIVE_GPU_C3: reset pulse released rst=00000000
[ 69.197855] NATIVE_GPU_C3: gpu reset ok
[ 69.251305] NATIVE_GPU_C3: cp init
[ 69.277149] NATIVE_GPU_C3: cp configure done
[ 69.303936] NATIVE_GPU_C3: cp rptr=00000009 rbbm=c00001c1 me=00000400
             wptr=00000009 ints=00000000 cpints=00000000 gfsr=00000000
             fsr=00000400 far=00000000 idle=0
[ 69.361289] NATIVE_GPU_C3: fail step 11 (cp me init)
```

判读：

- `cxo` 本来就在跑；`rbcpr`/`rbtimer` 之前是 halt（bit31），补上后读回 1。
- **RBBM reset 已释放，CP 已经把 ME_INIT 的 9 个 dword 全部读走**（rptr = wptr = 9）。
- `idle=0` 不是因为 CP 没跑，而是我们的轮询只有约 10–20 ms；vendor
  `adreno_ringbuffer_submit_spin` 等 2000 ms。`rbbm=c00001c1` 表示 ME 仍在忙。

H236ap 改动：

- ME_INIT 等待改为 2000 次 `IOSleep(1)`；
- GPMU 固件包完成等待改为 2000 ms；
- `GPMU_GENERAL_0 == 0xBABEFACE` 等待改为 5000 ms（vendor
  `GPMU_FW_INIT_RETRY=5000`）。

产物：

```text
H236ap kernel  46b3fd7f26e76e8abd1c3f419944dbd07376b2774bea0b598921030cf8fdcf0c
H236ap payload bb9acc298cfb70da4b56e3daa0deb81e66ac22e4560218c9edb5e8d5c841f432
H236ap boot    bb5c5a25b8b734ab1130c160597cc5b3692f32bfacc71a10ed72e2df1a8de9bf
```

镜像在 `/tmp/opencode/boot-H236ap.img`，待实测。若 GPMU 回 `BABEFACE`，C3 的
reset/SMMU/CP/GPMU 链就完整成立；若卡在 `gpmu packets` 或 `gpmu handshake`，
再按 vendor 的 GPMU 初始化顺序补。UEFI 迁移暂时不再是必须项。

### H236ap 结果与 H236aq：先等满 2 s，并采集 CP fault（2026-11-09）

H236ap 的 `cp init` 仍然在 `cp configure done` 之后约 61 ms 就结束，而不是等满
2 s：

```text
[ 69.631070] cp configure done
[ 69.692362] cp rptr=00000009 rbbm=c00001c1 me=00000400 wptr=00000009
             ints=00000000 cpints=00000000 ... idle=0
[ 69.749811] fail step 11 (cp me init)
```

说明循环是在某一拍看到了 `ints & 0x7e` 或 `cpints & 0x3f` 后 `break` 的；最后
一次读到的是已经被读清的 0。`RBBM_STATUS=0xc00001c1` 按 a5xx XML 展开：

```text
bit31 GPU_BUSY_IGN_AHB      bit30 GPU_BUSY_IGN_AHB_CP
bit8  GPU_BUSY_IGN_AHB_HYST bit7  CP_BUSY_IGN_HYST
bit6  CP_BUSY               bit0  HI_BUSY
（bit1 CP_ME_BUSY、bit2 CP_PFP_BUSY 都是 0）
```

`rptr == wptr == 9` 已经证明 ME_INIT 被取走；剩下的是 ME/CP 的聚合 busy 位。

H236aq：

- 不再在第一个错误位 `break`，按 vendor `adreno_ringbuffer_submit_spin` 等满
  2000 ms；
- 记录第一次出现错误位的 `ms/ints/cpints/rbbm`；
- 同时打印 `CP_HW_FAULT`(0x0b1a)、`CP_PROTECT_STATUS`(0x0b1c)、
  `CP_ME_STAT_DATA`(0x0b14)、`CP_INTERRUPT_STATUS`(0x0b18) 和 `RBBM_STATUS3`。

产物：

```text
H236aq kernel  1121b41fc60822a24a1ad5ddffa261705b2fdb4fd0d3cec3304f28e06bc852e8
H236aq payload 29f036769d0c549148cbf2f98a2cd7f98daf8d6a9502d06974a8a287678e8b2b
H236aq boot    9d13e2ca2250ce1e0c4ee88a18c441b63257de3fa6b4026c414a803fe7356b2b
```

镜像在 `/tmp/opencode/boot-H236aq.img`。下一步按 `first_*` 和 `hwfault` 判读：
若是 ME 还在跑，等满 2 s 后应能进入 GPMU；若是 CP fault，再按 fault 位修
configure/ring。

### H236aq 结果与 H236ar：C3 线程不能在 IOSleep 里等（2026-11-09）

H236aq 的日志停在：

```text
[ 67.872251] NATIVE_GPU_C3: cp configure done
（之后没有 cp rptr / cp diag）
```

但系统仍在继续（272 s 的 GIC/UFS、371 s 的 APFS 都正常），所以不是 GPU 挂死，
而是 C3 线程卡在 2000 次 `IOSleep(1)` 里没有返回。H236ap 只睡了约 61 次就
break，没暴露这个问题。

H236ar 把 `IOSleep(1)` 换成基于 `mach_absolute_time()`/`absolutetime_to_nanoseconds`
的有界忙等 `spinMs(1)`；ME_INIT 仍等 2 s，GPMU 包 2 s，`BABEFACE` 5 s。忙等会
占用唯一 CPU，但不会让线程永久停在 sleep 上，日志会在等待结束后落盘。

产物：

```text
H236ar kernel  71f48e5989619d41ac873262270c645aa1426e29a67415fa0237c6569b0516d1
H236ar payload e46e7f9e20b9d4ea42b1f554a706bc5678c91ea38b7a65c754dbd1c749e05bd0
H236ar boot    15dc9341be249f1b29d9656f43ec783c2de53ba23e7c74be08e901896d2e04fb
```

镜像在 `/tmp/opencode/boot-H236ar.img`。若 2 s 后仍 busy，`cp diag` 会给出
`first_ints/first_cpints/first_rbbm`、`CP_HW_FAULT`、`CP_PROTECT_STATUS`、
`CP_ME_STAT_DATA` 和 `RBBM_STATUS3`，再据此修 CP。

### H236ar 结果与 H236as：PM4 头缺奇偶校验位（2026-11-09）

H236ar 等满 2 s 后拿到：

```text
[ 72.060804] cp rptr=00000009 rbbm=c00001c1 me=00000400 wptr=00000009
             ints=00000000 cpints=00000000 ... idle=0
[ 72.118206] cp diag first_ms=1 first_ints=00000000 first_cpints=00000001
             first_rbbm=c00001c1 hwfault=00000000 protect=00000000
             mestat=000000fe cpint=00000000 status3=00100000
```

`CP_INTERRUPT_STATUS` 的 bit0 在 1 ms 就置起，`CP_HW_FAULT`/`CP_PROTECT_STATUS`
都是 0，说明是 **CP opcode error**，不是取指 fault。

根因是 C3 里的 PM4 头格式错了：

```c
// 旧：缺 parity，type7 还写 count-1
type4 = 0x40000000 | ((count-1)<<16) | addr
type7 = 0x70000000 | (opcode<<16) | (count-1)
```

vendor `adreno_pm4types.h` 的 A5xx 格式：

```c
type4 = 0x40000000 | cnt | parity(cnt)<<7  | (addr&0x3ffff)<<8 | parity(addr)<<27
type7 = 0x70000000 | cnt | parity(cnt)<<15 | (opcode&0x7f)<<16 | parity(opcode)<<23
```

所以 ME_INIT（opcode 0x48）被 CP 直接判成 opcode error，ME 从未执行。
H236as 修正 `type4()`/`type7()`，加入奇偶校验并改正 count；GPMU 的 type4
也会随之正确。

产物：

```text
H236as kernel  a05a4ae376acd451cffaa664db3da5a705d4f4416ae81bd64bfd2ddf6b1e6c3f
H236as payload e61f869972f4f034925e7dac795c4e8a3a840828122da23283d0edb6738c172f
H236as boot    c00dd01bae7f6092ff05f4bd811f149896d7d0d8d9e65e0404bfeb63775b12d5
```

镜像在 `/tmp/opencode/boot-H236as.img`，待实测。若 ME_INIT 通过，应该看到
`gpmu load` 以及 `GPMU firmware reached BABEFACE`；否则 `cp diag` 的
`first_cpints`/`hwfault` 会告诉下一步。

### H236as 结果与 H236at：CP 已 idle，余下是 GPU busy 位（2026-11-09）

H236as 的修正生效：

```text
[ 69.331589] cp configure done
[ 71.919786] cp rptr=00000009 rbbm=c0000101 me=00000000 wptr=00000009
             ints=00000000 cpints=00000000 gfsr=00000000 fsr=00000400
             far=00000000 idle=0
[ 71.977232] cp diag first_ms=4294967295 first_ints=00000000
             first_cpints=00000000 hwfault=00000000 protect=00000000
             mestat=0000002e cpint=00000000 status3=00100000
```

- `cpints` 的 opcode error 消失，`CP_ME_CNTL=0`（ME 已运行）；
- `RBBM_STATUS` 的 CP busy 位（1/2/4/6）全为 0，只剩 bit31/30/8：
  `GPU_BUSY_IGN_AHB`、`GPU_BUSY_IGN_AHB_CP`、`GPU_BUSY_IGN_AHB_HYST`；
- 这些是 3D 块未做 power collapse 时的全局 busy 指示，不是 CP 的 idle 判据。

H236at 把 idle 判据从 `status & ~1` 改为 `status & 0x7e`（CP_ME/PFP/ETS/
CRASH/GPMU_MASTER/CP_BUSY），并保留 `RBBM_STATUS3` bit24 的 SMMU stall 检查。

产物：

```text
H236at kernel  df61d739af41aec0ac61663601107d4f696e4fab424dffe0116538d01257b98a
H236at payload 7a83738093b2b7a94f873a9b92018422d6360e9773b50e8b827f1fcd7bb209de
H236at boot    b509271587ecff85b83a3096a678ce336a1c970fc936856e6c8b0a14a7b42bf9
```

镜像在 `/tmp/opencode/boot-H236at.img`，待实测。期望看到 `gpmu load` 和
`GPMU firmware reached BABEFACE`。

### H236at 结果与 H236au：GPMU 缺 AGC 初始化（2026-11-09）

H236at 的 ME_INIT 通过：

```text
[ 69.094697] cp rptr=00000009 rbbm=c0000101 me=00000000 ... idle=1
[ 69.212514] gpmu load
[ 75.631403] fail step 22 (gpmu handshake)
```

GPMU 固件包被 CP 消费（没有 fail step 21），但释放 CM3 后 5 s 内
`GPMU_GENERAL_0` 没有回 `BABEFACE`。对比 sagit 的 `gpmu()`，我们在
`GPMU_CM3_SYSRESET=0` 之前少了：

- `GPMU_GPMU_VOLTAGE=0x80000000`、`GPMU_GPMU_PWR_THRESHOLD=0x80000000|6000`；
- AGC 初始化消息（`0x9800+7`，payload 36 dwords：5448、1、752 mV、257 MHz、
  `(1<<24)|(1<<17)|(2<<8)`、`~0x303`）；
- `AGC_INIT_MSG_MAGIC=0xBABEFACE`；
- `PWR_COL_INTER_FRAME_CTRL=0x7f`、`BINNING_CTRL=0`、
  `INTER_FRAME_HYST=0xa0080`、`STAGGER_DELAY=0x600040`。

H236au 补上这些，并在握手失败时打印 `general0/general1/voltage/threshold/
magic/cm3`。

产物：

```text
H236au kernel  de5539b5eaddf188dcc9a35a24c074cb9b32d6b3693eed87dac237a922e52a1c
H236au payload c6c82e3fb21061ac8989e3931434c72ad13e329cd77347595d13609873c49ce4
H236au boot    4324e2c546b19d2517d75ceb3f400d8adcc5a63bcf63da029ec161ec06dda4b3
```

镜像在 `/tmp/opencode/boot-H236au.img`，待实测。

### H236au 结果：C3 全链打通（2026-11-09）

```text
[ 69.188471] cp rptr=00000009 rbbm=c0000101 me=00000000 ... idle=1
[ 69.306196] gpmu load
[ 69.335214] gpmu general0=babeface general1=00000000 voltage=00000000
             threshold=80001770 magic=babeface cm3=00000000
[ 69.367215] GPMU firmware reached BABEFACE
```

**C3 完成**：RBBM reset、SMMUv2（3 CB / 8 页 / 36 位 PA / CB0 + SID0）、
CP configure、ME_INIT、GPMU 固件加载与 `BABEFACE` 握手全部通过。之前卡住的
三个真实缺陷分别是：

1. GCC/GPUCC 的 CXO/RBCPR/RBBMTIMER 与 `gcc_gpu_gpll0_clk` 未开，RBBM reset
   写 1 挂总线；
2. PM4 `type4`/`type7` 头缺奇偶校验位，CP 把 ME_INIT 判成 opcode error；
3. 释放 CM3 前缺 AGC 初始化消息与电压/功率阈值，GPMU 不写 `BABEFACE`。

H236au 的 kernel/payload/boot 哈希见上一节。下一轮做最小提交验证：
CP `CP_MEM_WRITE` 写 `0xDEADBEEF` 到 GPU 可见内存，CPU 读回；通过后进入 C4/C5。

### H236av：CP_MEM_WRITE 最小提交（2026-11-09）

在 GPMU `BABEFACE` 之后追加一个 CP 提交：

1. 清 `rptr` scratch 页（`kRptrIova=0x1400000`，SMMU 读写映射）；
2. ring 写 `CP_MEM_WRITE(0x3d, 3)` + 64 位地址 + `0xDEADBEEF`；
3. 紧跟 `CP_WAIT_MEM_WRITES(0x12, 0)`，确保写完成顺序；
4. 推 WPTR，等 `CP_RB_RPTR` 到新位置（2 s）；
5. `dc ivac` 失效 CPU cache 后读 scratch 页，要求值等于 `0xDEADBEEF`。

这一步验证的是 CP → SMMU SID0/CB0 → VBIF → 内存的真实数据通路，不只是
“包被取走”。

产物：

```text
H236av kernel  2cb846d0f2eefb42ed709f9ecb27a2833b6e9b574d09305c19e4522a36b6b926
H236av payload e79c96fe4512ef355ef901a538f15a29d2ced8ebe61556040cb98d38a4876b46
H236av boot    7392523978f07d8ed369e53786f808a0a0b615afd49861e0664e821ae69b1c23
```

镜像在 `/tmp/opencode/boot-H236av.img`，待实测。期望日志：

```text
NATIVE_GPU_C3: submit probe
NATIVE_GPU_C3: submit write rptr=<n>/<n> value=deadbeef done=1
NATIVE_GPU_C3: submit test ok
```

### H236av 结果与 H236aw：提交包被消费但写值为 0（2026-11-09）

H236av：

```text
[ 70.070799] submit probe
[ 70.098317] submit write rptr=3136/3136 value=00000000 done=1
[ 70.127670] fail step 30 (cp mem write)
```

CP 的 RPTR 已经推进到包尾（3136/3136），说明 `CP_MEM_WRITE` +
`CP_WAIT_MEM_WRITES` 被消费；但 CPU 读回 scratch 是 0。需要区分：

1. 写真的没发生（CP 丢弃/secure/地址不对）；
2. 写发生了，但 CPU 读到旧 cache 行。

H236aw 同时提交两个独立探针：

- 标准 `CP_EVENT_WRITE(0x46,4)` + `CACHE_FLUSH_TS` + IRQ，向 `kRptrIova`
  写 64 位时间戳；
- `CP_MEM_WRITE` 向 `kRptrIova+8` 写 `0xDEADBEEF`；
- 之后 `CP_WAIT_MEM_WRITES`，再 `dc ivac` 读回；
- 打印 `ts`、`value`、`CP_INTERRUPT_STATUS`、`CP_HW_FAULT`、`CB0.FSR`、
  `RBBM_STATUS`。

产物：

```text
H236aw kernel  400cda7bdb7dcffe4a6c255fb87f0be62e67a7abaaae386754145c1e26ee7771
H236aw payload 5476f724767719adb9c064c18aea5a693b61292f57d95ca29c7db1cc88688b75
H236aw boot    e44833d55dfe175b3b9ac870f68d6c04cc1ca1ca5973001c7717fb17f79f8e6c
```

镜像在 `/tmp/opencode/boot-H236aw.img`，待实测。若 `ts` 非 0，说明 CP→内存
通路成立，问题只在 `CP_MEM_WRITE`/cache；若两者都是 0，则检查 secure 状态或
数据地址映射。

### H236aw 结果与 H236ax：时间戳和写值都是 0（2026-11-09）

H236aw：

```text
[ 68.786258] submit probe
[ 68.813815] submit write rptr=3141/3141 ts=0000000000000000 value=00000000 done=1
[ 68.844288] submit diag cpint=00000000 hwfault=00000000 fsr=00000400 rbbm=e0c801c1
[ 68.875007] fail step 30 (cp mem write)
```

CP 消费了 `CACHE_FLUSH_TS` 和 `CP_MEM_WRITE`，但两者都没有落内存；没有
CP interrupt、没有 `CP_HW_FAULT`，`CB0.FSR` 仍是 0x400（MULTI 位，之前一直
存在）。这更像数据写权限/地址映射问题，而不是 CP 执行错误。

H236ax 增加第三个写入目标：`kRingIova + 0x7000`。这一页是 ring 缓冲区的一部分，
CP 自己就在读它，映射必然可用；把同一个 `CP_MEM_WRITE` 写到这里，再读回
`0xCAFEBABE`。若 ring 页能写而 `rptr` 页不能，就是 `rptr` range 的写入权限/映射；
若两者都不能写，说明 CP 的 data write 被 secure/protected 状态丢弃。

产物：

```text
H236ax kernel  7996a37106c20190b2c32481e01c5093f4399a689a5eed3e2198da354d39f614
H236ax payload 640d2c811affff20f6f79ca293d02984a7a414614bd3b7186f86a08316494c35
H236ax boot    f0574cb2d9f96e3cf4a7808700b1aa4547eebdc53a134edd534b488672076123
```

镜像在 `/tmp/opencode/boot-H236ax.img`，待实测。

### H236ax 结果与 H236ay：ring 页也写不进（2026-11-09）

H236ax：

```text
[ 69.341378] submit write rptr=3145/3145 ts=0000000000000000 value=00000000
             ring=00000000 done=1
[ 69.372622] submit diag cpint=00000000 hwfault=00000000 fsr=00000400 rbbm=e0c801c1
```

连 ring 缓冲区自己的空闲页都写不进，且没有 CP fault，说明不是 `rptr` 映射的
写权限问题，而是 GPMU 之后 CP 的 data-write 被丢弃/未执行。两个候选：

1. `CP_SET_PROTECTED_MODE(1)` 状态（GPMU 包最后一条）仍在阻止写；
2. CP 进入 secure 模式，非安全数据写被丢弃。

H236ay 在提交里显式包上 `CP_SET_PROTECTED_MODE(0)` / `(1)`，并打印
`RBBM_SECVID_TRUST_CNTL`(0xf400)、`CP_ME_CNTL`、`CP_ME_STAT_DATA`，用来判断
是 protected 状态还是 secure 状态。

产物：

```text
H236ay kernel  52214ef9977a10477aab9537f5633b1f19436d493999be83f0ee6062c27d4190
H236ay payload 052b2fd5ed093a15b96890acedc35b710a37932a57f8ec9b88c73d43563be0a6
H236ay boot    7fd1b6814e0f0043258ff45f126d6cc9cce5423f7b90212309e32c7090553203
```

镜像在 `/tmp/opencode/boot-H236ay.img`，待实测。

### H236ay 结果与 H236az：CP 仍在 secure 模式（2026-11-09）

H236ay：

```text
[ 70.152213] submit write rptr=3149/3149 ts=0 value=0 ring=0 done=1
[ 70.183409] submit diag cpint=0 hwfault=0 fsr=400 rbbm=e0c801c1
             trust=00000001 me=00000000 mestat=70928000
```

`RBBM_SECVID_TRUST_CNTL=1`：CP 在 secure 模式，非安全数据写被丢弃，这解释了
“包被消费、无 fault、但两处写都是 0”。GPMU 的寄存器写和 ring/微码读不受影响。

H236az 先做最便宜的尝试：从 AP 侧写 `RBBM_SECVID_TRUST_CNTL(0xf400)=0`，
写前后落盘并读回。若读回 0 且数据写成功，secure 状态可由 host 解除；若读回
仍是 1（或被 TZ 忽略），下一步必须走 ZAP/PAS：
`a540_zap.mdt/b00/b01/b02` + SCM PAS init/auth + ZAP + `CP_SET_SECURE_MODE(0)`。

产物：

```text
H236az kernel  cdcee3233800a30354645c92a741963929ec1cfe3fa92c8f4d26eebe080aa94b
H236az payload 67033d2daefb21bad34c41ac08339611a7dfa39b2d4fef126f62859f7da40b12
H236az boot    d51d180285f57a7b33a4dcc720f177771a7a8929dbc4b2615a0690f06a0262ad
```

镜像在 `/tmp/opencode/boot-H236az.img`，待实测。若写 0 直接挂总线，最后一行会是
`trust write begin`。

### H236az 结果与 H236ba：ZAP/PAS 实现（2026-11-09）

H236az：

```text
[ 68.130725] submit probe
[ 68.158257] trust write begin old=00000001
（没有 trust write done）
```

从 AP 非安全侧写 `RBBM_SECVID_TRUST_CNTL` 直接挂总线，寄存器是 secure-only。
CP 的 secure 状态只能通过 ZAP/PAS 解除。

H236ba 按 A 线 `redwood_adreno.c` 的 SCM 调用和 sagit 的
`CP_SET_SECURE_MODE(0)` 流程实现：

1. `PAS_SHUTDOWN(13)`；
2. `PAS_INIT_IMAGE(13, a540_zap.mdt)`（`.mdt` 放在低 4G、物理连续的 8 KiB buffer）；
3. `PAS_MEM_SETUP(13, image_phys, 0x2000)`；
4. 把 `a540_zap.b02` 写进 image buffer，`dc cvac`；
5. `PAS_AUTH_AND_RESET(13)`；
6. ring 提交 `CP_SET_SECURE_MODE(0x66)=0` + `CP_WAIT_FOR_IDLE(0x26)`；
7. 读回 `RBBM_SECVID_TRUST_CNTL`，要求为 0；
8. 再跑 `CACHE_FLUSH_TS` + `CP_MEM_WRITE` 双探针。

`a540_zap.mdt`/`.b02` 已加入 `scripts/gen-a540-firmware.py` 的校验表（SHA-256
与 H236 计划一致，blob 仍只从 `.cache/firmware/a540/` 读取，不提交）。

产物：

```text
H236ba kernel  b4a5ad39dad2fb90f7078bb0c2bfdc2a3a775fe90efc929bf44d77b7c961047d
H236ba payload 1624f262a23f45870d0e39ab2921003152294099300446aa4a4f770afbd74d74
H236ba boot    731fa9a9df58cf70caa74c1099f40214fcbcb5570f94c8ae14b8721927885ef2
```

镜像在 `/tmp/opencode/boot-H236ba.img`，待实测。期望顺序：
`zap shutdown` → `zap init` → `zap mem setup` → `zap auth` → `zap unsecure
... trust=00000000` → `submit ... value=deadbeef ring=cafebabe`。

### H236bb 结果与 H236bc：ZAP 签名通过，镜像不完整（2026-11-09）

H236bb（225 上重跑）：

```text
[ 71.549178] zap shutdown call
[ 71.577644] zap shutdown rc=0 answer=0
[ 71.606422] zap init call mdt=188c86000/6684
[ 71.663059] zap init rc=0 answer=0
[ 71.692474] zap mem setup call image=188c88000/8192
[ 71.721687] zap mem setup rc=0 answer=0
[ 71.751253] zap auth call b02=4916
[ 71.781384] zap auth rc=0 answer=0
[ 71.837529] zap unsecure rptr=3134/3134 done=1 trust=00000001
```

TrustZone 的 `PAS_INIT_IMAGE`/`PAS_MEM_SETUP`/`PAS_AUTH_AND_RESET` 全部返回 0，
签名通过；但 `CP_SET_SECURE_MODE(0)` 后 trust 仍是 1。根因是 ZAP 镜像不完整：
a540 的 `.mdt` 段表是 3 段，`.b00`/`.b01`/`.b02` 分别在镜像偏移 0/0x1000/0x3000，
完整拼接就是 `a540_zap.elf`（17,204 B）。H236bb 只把 `.b02` 拷到偏移 0，且
`PAS_MEM_SETUP` 只有 8 KiB。

H236bc：

- `a540_zap.elf` 加入 generator（`efac89c5…`）；
- `zapImage` 扩到 32 KiB，整份 `.elf` 放入；
- `PAS_MEM_SETUP` 传 0x5000（覆盖 0x0..0x4334 的三段）；
- `PAS_INIT_IMAGE` 仍用 `.mdt` 签名头。

产物：

```text
H236bc kernel  809ee8a3fd4035875f68049d878c38bb907f0e72c850b68469682184f0951ad4
H236bc payload e91d23bd5dc4f2051eb1bc1e5d75d4f7c5bd9ee43a1ab48aacd2198095f92407
H236bc boot    1156d219c50a0af87b4c22b749e0903ef11b79c4a1f2aab4e05e1243c838fbff
```

镜像在 `/tmp/opencode/boot-H236bc.img`，待实测。成功后应看到
`zap unsecure ... trust=00000000` 和 `submit ... value=deadbeef ring=cafebabe`。

### H236bc 结果与 H236bd：PAS_AUTH 的尺寸（2026-11-09）

H236bc 把完整 `.elf` 放入镜像后：

```text
zap init rc=0 answer=0
zap mem setup rc=0 answer=0 image=.../20480
zap auth call elf=17204
zap auth rc=-68 answer=0
fail step 43 (zap auth and reset)
```

`PAS_INIT_IMAGE` 和 `PAS_MEM_SETUP` 都接受，但 `PAS_AUTH_AND_RESET` 返回
`-68`。H236bb 只放 `.b02` 时 auth 能过，说明 TZ 对镜像布局/尺寸敏感；最可能
是 `PAS_MEM_SETUP` 传了 0x5000，而 `.elf` 的实际大小是 0x4334。

H236bd 只改一处：`PAS_MEM_SETUP` 的 size 用 `a540_fw_zap_elf_size`（17204 =
0x4334），不再取整到 0x5000。

产物：

```text
H236bd kernel  3bbbe1813b501817aca5383e6160a43aab4969775a63211a2deb86088946551e
H236bd payload ae4aba4627140b1643a074b7103fcc868c707d10ced4498cf8e392a0696e6c39
H236bd boot    69b47c979bd9d929ba6a98db5ed388e782568a8fccb9b51f9b1173a2c3cd3ae5
```

镜像在 `/tmp/opencode/boot-H236bd.img`，待实测。若仍是 -68，下一步彻底断电
冷启动一次（TZ 可能保留 H236bb 已认证的 ZAP），再重试。

### H236bc/H236bd 结果与 H236be：ZAP 顺序（2026-11-09）

冷启动后 H236bc（完整 `.elf` + 0x5000）仍然是：

```text
zap init rc=0
zap mem setup rc=0
zap auth rc=-68
```

H236bd（完整 `.elf` + 精确 0x4334）在 `PAS_MEM_SETUP` 就返回 -32。对照 Linux
v6.12 `drivers/soc/qcom/mdt_loader.c`：

- `mdt_phdr_valid()` 只接受 `p_type == PT_LOAD` 且不是 hash 段；
- a540 的 `.mdt` 三个 program header 中只有 `.b02` 是 PT_LOAD
  （`p_paddr=0x5000`、`p_memsz=0x1334`、relocatable），所以镜像大小是
  `ALIGN(0x5000+0x1334,4K)-0x5000 = 0x2000`，`.b02` 放在偏移 0；
- `.b01` 是 hash 段，不进入运行时镜像；完整 `.elf` 不是 `PAS_MEM_SETUP` 的
  期望布局。

H236be 回到 `.b02`-only / 0x2000，并调整顺序为 vendor `a5xx_rb_start` 的语义：

```text
reset → SMMU → ZAP/PAS(auth) → CP ME_INIT → CP_SET_SECURE_MODE(0)
      → GPMU → submit
```

之前 ZAP 放在 GPMU 之后，CP 的 secure 状态可能已经在 ME_INIT 时锁定。

产物：

```text
H236be kernel  e82dd1765e644e1d04c7a85fa6ae97556b53be535f9669c0cc6fb99250d740ea
H236be payload 4d6471cb384389eaef22ade294c0a7092fe23a4c07fc04f413c68dfe5790d819
H236be boot    44a7b6752cf5e1009446678afaf9bb920fb7a9e89eb21ea937bd9ec4feb52c1e
```

镜像在 `/tmp/opencode/boot-H236be.img`，待实测。

### H236be 结果与 H236bf：ZAP 内存在 4 GiB 以上（2026-11-09）

H236be（`.b02`-only，ZAP 在 ME_INIT 前，secure-mode 在 GPMU 前）：

```text
zap init rc=0
zap mem setup rc=0
zap auth rc=0
cp init ... idle=1
zap unsecure rptr=12/12 done=1 trust=00000001
fail step 44
```

PAS 全部成功，但 CP 仍在 secure。检查地址发现 ZAP 的两个 buffer 在

```text
mdt=188c41000
image=188c43000
```

都**超过 4 GiB**。SCM/PAS 的物理地址参数是 32 位的，TZ 会把 0x188c43000
截断；route C 计划也要求 ZAP memory 在低 4 GiB、4 KiB 对齐。

H236bf 给 `Alloc::init` 增加 `physicalMask` 参数，ZAP header/image 用
`0x00000000fffff000`（低 4G）分配，其余 GPU buffer 仍用原来的 36 位掩码。

产物：

```text
H236bf kernel  eb102b954688cefd5bc43c178c881daa6e1d5d2740f0f27aba9df1640ca895d0
H236bf payload 0c9a1245addf3988bd1d9218f08c56a967e4baab99585d3a8d75297cfcc9d927
H236bf boot    066c75c0bc8f2c2553687d4e6fcd81abc6cf86e52e79cf792dc02a2e39c73c94
```

镜像在 `/tmp/opencode/boot-H236bf.img`，待实测。

### H236bf 结果与 H236bg：低 4G 分配处日志缺失（2026-11-09）

H236bf 的持久日志里完全没有 `NATIVE_GPU_C3: thread start`，也没有
`c3 full run`。说明 C3 在最早的 `zapHeader/zapImage` 低 4G 分配处就停住，
且停在首次 flush 之前。低 4G 的 `IOBufferMemoryDescriptor` 在这台内核上可能
直接阻塞或失败。

H236bg：

- 分配前后加 `IOLog` + `native_log_flush_hook()`；
- 低 4G 分配失败时回退到原来的 36 位物理掩码，保证 C3 继续并打印真实地址；
- `smmu setup` 后、`zap load` 前也补 flush。

产物：

```text
H236bg kernel  141dcb2a68f7f75e5a613775da03017f63151dedcf02b5b281f97d4f3f745e24
H236bg payload 3750ab13283073ea3bdc066ccf4091dd41e6635d6fb2f4cc47035f6d72431fc6
H236bg boot    37f08f3ea37aa475f0de7f6caaf7e75ad1f066c1bc2ab741e3e2b8132d790aa7
```

镜像在 `/tmp/opencode/boot-H236bg.img`，待实测。若看到
`zap low4g failed`，说明低 4G 分配不可用；需要改用启动阶段预留的低内存，
而不是运行时分配。

### H236bg 结果与 H236bh：ZAP 镜像必须 1 MiB 对齐（2026-11-09）

H236bg：

```text
zap alloc mdt=188bfd000 image=188c40000
zap init rc=0
zap mem setup rc=0
zap auth rc=0
zap unsecure ... trust=00000001
```

低 4G 的 `physicalMask=0xfffff000` 并没有把地址压到 4 GiB 以下（XNU 的
`IOBufferMemoryDescriptor` 在这条路径上忽略了该限制），所以 ZAP 仍在
0x188c40000。

对照 sagit 的 `AdrenoFirmware.h::MDTImage` 和 `gpu_handoff.cpp::stageZap`：

- a540 的 `.b02` `p_align = 0x100000`；
- `imageInto()` 要求 `physical & (imageAlignment()-1) == 0`，即 ZAP 镜像物理
  基址必须 **1 MiB 对齐**；
- `stageZap()` 先按 `imageAlignment()` 预留额外空间，再在分配内部对齐；
  EFI 分配上限 `UINT32_MAX`，即低 4 GiB；
- `PAS::setup()` 用 `PAS_MEM_SETUP(13, imagePhys, imageBytes)`，镜像内容按
  `p_paddr - low` 放到偏移 0。

H236bh 按这个实现改 `Alloc::init`：

- 增加 `alignment` 参数，多分配 `alignment - 4096` 并在内部对齐物理地址；
- ZAP header：低 4G mask `0xffffffff` + 4 KiB 对齐；
- ZAP image：低 4G mask `0xffffffff` + **1 MiB 对齐**，大小 0x2000；
- 其余 GPU buffer 保持原 36 位掩码/4 KiB 对齐。

产物：

```text
H236bh kernel  de635097b94d1568bbd255258c96dbaa4fb13430e08f05ba2afa1c4fa32f9d48
H236bh payload d6a4a3bbacf04775179c8deba976f88fe69008592e06a87a89b0fa6ef7b52d1e
H236bh boot    8b1f57f064c41b9336ac93d131a09125e810493494b02db94b427150d4b1da62
```

镜像在 `/tmp/opencode/boot-H236bh.img`，待实测。

## 更新规则

每次工作结束追加一行日志，并更新“当前阶段/下一步/待实测/阻塞”。构建产物哈希、日志路径和失败现象记录在日志里；私有文件只放 `.cache/firmware/`，不提交。
