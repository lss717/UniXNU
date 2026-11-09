# H236bi–H236bu：低 4G ZAP 的固件窗口分配记录（2026-11-09）

本文记录 2026-11-09 这一轮从“XNU 运行时分配低 4G + 1 MiB 对齐 ZAP 镜像”
改为“DarwinBoot 在固件阶段预留”的全部尝试、屏幕判读、失败原因和踩过的坑。
设备：OnePlus 5（cheeseburger / MSM8998 / Adreno 540），
OS：iPad7,1 / iPadOS 17.7.11 / 21H461。

结论先行：

1. **C3 的 RBBM/SMMU/CP/GPMU 和 ZAP/PAS 调用本身已经通过**：
   `zap init/mem setup/auth rc=0`，GPMU 到 `BABEFACE`，CP `idle=1`。
   仍然缺的是：ZAP 镜像必须位于**低 4 GiB、1 MiB 对齐**的物理地址，
   而 XNU 运行时无法提供；所以改由 DarwinBoot 预留并写进 `zap-base`。
2. **固件拒绝单次 256 MiB 的 `AllocatePages`**，与地址、内存类型
   （`EfiLoaderCode` / `EfiLoaderData`）、`AllocateAddress` /
   `AllocateMaxAddress` 都无关。同一固件下 76 MiB 的 `AllocatePool`
   （payload）可以成功，128 MiB 的 `AllocatePages` 也可以成功。
   因此 256 MiB 是这一轮真正的墙，不是“没有足够大的空闲 run”。
3. **H236bu 首次让 128 MiB 固定窗口分配成功**：
   屏幕出现 `DARWINBOOT: fixed window type=0 base=0x…`（固定表第一项
   `0xA0000000`，`type=0` 即 `EfiLoaderCode`）。随后在
   `0x0000000017ABAC58` 触发同步异常，说明窗口外的 ramdisk / addon /
   policy 不能简单留在 UniXNU 的 pool 地址里。
4. **菜单/logo 已经达标**：`OnePlus 5 IOS`、`ios 17.7.11`、`Restart`、
   `Shut down` 三项可见，UniXNU logo 保留；`[ui] title` 仍是 `UniXNU`。

---

## 1. 目标、约束和已知基线

### 1.1 目标

让 A540 的 ZAP/PAS 在 **低 4 GiB、1 MiB 对齐** 的物理缓冲区上执行，
使 `CP_SET_SECURE_MODE(0)` 真正清掉 `RBBM_SECVID_TRUST_CNTL`，
从而让 AP 能写 CP 的 secure 寄存器，进入 C4/C5（ME_INIT、ring、submit）。

### 1.2 为什么必须由 boot 阶段给

- ZAP 运行时镜像只有 `.b02`：它是 `PT_LOAD`，大小 `0x2000`，
  `p_align=0x100000`；`.mdt` 是元数据，`.b01` 是 hash。
  参考 `mdt_loader.c`、sagit 的 `MDTImage`/`stageZap`。
- XNU 运行时拿到的页不保证低 4 GiB，也不保证 1 MiB 对齐；
  `IOMallocContiguous`/`AllocatePages` 在这条 B 线里没有可靠的低地址保证。
- 所以 `zap-base` 由 DarwinBoot 解析，ZAP 镜像必须在 boot 阶段放入
  `zap-base` 指向的物理窗口；内核只读这个地址。

### 1.3 当前 payload 规模

| 项目 | 大小 |
| --- | --- |
| `payload.img`（FAT，作为 ramdisk） | 76 MiB |
| XNU kernel（H236bi） | 52.5 MiB |
| `kernel.macho.gpuaddon` | 12 MiB |
| `scratch-data.img`（payload 内） | 3 MiB |
| trust cache | 60 KiB |
| `.vroot` policies | ~1 MiB |
| ZAP 窗口 | 2 MiB |
| args + ADT | ~20 KiB |

kernel + payload 就已经 128.5 MiB，超过 128 MiB。
`gpuaddon` 和 policy 再把总量推到 ~143 MiB。

### 1.4 关键参考

- `sagit-ios-port/boot/bridge/gpu_handoff.cpp` 的 `stageZap`/PAS 模型；
- `sagit-ios-port/drivers/gpu/QcomGPU/AdrenoFirmware.h` 的 `MDTImage`
  1 MiB 对齐和 `imageInto`；
- `sagit-ios-port/drivers/security/QcomSCM/SCMPAS.h` 的 PAS 参数格式；
- Linux `mdt_loader.c` 的 a5xx `.mdt` 语义；
- XNU `arm_vm_init`：`avail_start = TopOfKernelData`，
  `avail_end = PhysicalBase + MemorySize`，TrustCache 要落在可映射区域；
- H236be 的 C3 日志：`zap auth rc=0` 后
  `zap unsecure rptr=12/12 done=1 trust=00000001`，`fail step 44`。

---

## 2. 时间线：H236bi → H236bu

> 所有镜像都只通过 `fastboot boot` 启动，没有写 boot/userdata/GPT。
> 内核固定为 H236bi `53cedef9…`；后续只改 firmware / payload / boot image。

| 镜像 | 目的 | 结果 | firmware / boot |
| --- | --- | --- | --- |
| H236bi | 4 GiB kernel window，ZAP 放窗口内低地址 | 停在 UniXNU 菜单 | `362f68e9…` / `554f7782…` |
| H236bj | 允许 window 跨 4 GiB，强制低起点 | 仍停在菜单 | `979b7682…` / `0673f344…` |
| H236bk | 继续修低窗口/ZAP 起点 | 仍停在菜单 | `86994141…` / `42ecf2aa…` |
| H236bl | 低窗口 + ZAP；菜单三项、英文动作、logo 关 | 菜单可见，boot 后回菜单 | — / `d44791aa…` |
| H236bm | 高 4 GiB kernel window + `AllocateMaxAddress` 低 4 GiB ZAP | boot 后回菜单 | `5afa4290…` / `b3816456…` |
| H236bn | H236bm + 完整菜单 | boot 后回菜单 | — / `034a702c…` |
| H236bo | 加可见的 15 秒错误诊断，恢复 logo | 屏见 `NO WINDOW 10000000 …` / `NO KERNEL WINDOW Out of Resources` | `05951cf1…` / `36904d05…` |
| H236bp | 逐 run `AllocateAddress` + `AllocateMaxAddress` + `EfiLoaderData` | 仍 `Out of Resources` | `b1647519…` / `d7e1fd2b…` |
| H236bq | `AllocateMaxAddress` 回退；`[ui] title=UniXNU`、logo 恢复、条目 `OnePlus 5 IOS` | 菜单确认可见，boot 后回菜单 | `e0a0e039…` / `de27ee09…` |
| H236br | 固定地址 `0xA0000000`/高 4 GiB 等 | 256 MiB 仍失败 | `2db31eed…` / `601b42b2…` |
| H236bs | 固定地址 + `EfiLoaderCode`/`EfiLoaderData` 两类型 | 仍失败 | `5828e119…` / `44578508…` |
| H236bt | 固定地址 + 类型 + 低 4 GiB 回退 | 仍失败 | `27e5447c…` / `9c2c9157…` |
| H236bu | **128 MiB** window；ramdisk/addon/policy 留在 pool，不进 window | 128 MiB 固定分配成功；随后 `Synchronous Exception at 0x17ABAC58` | `519f7663…` / `bf73e82b…` |

### 2.1 H236bi–H236bk：4 GiB window 的误区

`board.toml` 里有：

```toml
owned_memory_size = "0x100000000"   # 4 GiB
```

但实际 payload 的 ADT 没有把这个属性带进 `WindowSize`；DarwinBoot 读到的
`WindowSize` 是默认的 **256 MiB**（H236bp 屏幕 `NO WINDOW 10000000` 已证明）。
H236bi 按 4 GiB 去找“低 4 GiB + 整体窗口 + ZAP”，
`Candidate + WindowSize <= 4 GiB` 永远不成立；H236bj/bk 把窗口改成可跨 4 GiB、
强制低起点，仍然没有可用的连续 4 GiB run。

**坑**：不要从 `board.toml` 推断 `WindowSize`。在 DarwinBoot 里把实际值
画出来；`owned_memory_size` 只是 ADT 生成器的输入，旧 payload 里可能没有这个节点。

### 2.2 H236bl–H236bn：窗口内 / 窗口外 ZAP 的拆分

- H236bl：把 ZAP 放在低窗口内，菜单三项可见，但 boot 后回到菜单。
- H236bm：把 kernel window 固定到高 4 GiB，另用 `AllocateMaxAddress`
  在低 4 GiB 分配 1 MiB 对齐 ZAP。这是 sagit `stageZap` 的思路，
  但 `AllocateMaxAddress` 也被固件拒绝。
- H236bn：把菜单和 logo 固化为 `OnePlus 5 IOS` / `ios 17.7.11` /
  `Restart` / `Shut down`，boot 后仍回菜单。

此时还不知道是“没有空间”还是“分配被拒”；H236bo 加诊断。

### 2.3 H236bo–H236bq：把失败变成可读的屏幕

H236bo 在 `AllocateWindow` / `AllocateZapWindow` 失败点画 15 秒诊断：

```text
NO WINDOW 10000000 BIG RUN FCC00000 @ 180000
NO KERNEL WINDOW Out of Resources size=0x1000
FREE 180000000 + FCC0000
FREE 100000000 + 6F310000
FREE 180000000 + FCC0000
```

判读：

- `WindowSize = 0x10000000` = **256 MiB**，不是 4 GiB；
- 低地址 `0x180000` 有一条 4.2 GiB 的 run，高地址 `0x180000000`
  还有 264 MiB 的 run；
- 精确 `AllocateAddress` 256 MiB 仍然返回 `EFI_OUT_OF_RESOURCES`；
- `NO KERNEL WINDOW size=0x1000` 是屏幕宽度截断的 `0x10000000`，
  不是 4 KiB。

H236bp 把逐 run 的 `AllocateAddress` 和 `AllocateMaxAddress` 都改成
`EfiLoaderData`，仍然失败。H236bq 加了 `AllocateMaxAddress` 回退，
并把 `[ui] title` 回到 `UniXNU`、`logo = true`，只保留条目
`OnePlus 5 IOS`。菜单三项已经确认可见。

**坑**：`DiagDraw`/`Print` 画在 GOP 上，菜单随后会覆盖/重绘；
15 秒 `Stall` 是必要的。`size=0x1000` 这种截断很容易被误读为 4 KiB，
要看同一行的 `NO WINDOW 10000000` 或完整串口日志。

### 2.4 H236br–H236bt：256 MiB 是硬上限

H236br/bs/bt 依次尝试：

- `0xA0000000`、`0xA0004000`、`0x100000000`、`0x180000000`；
- `EfiLoaderCode` 和 `EfiLoaderData`；
- `AllocateAddress` 与 `AllocateMaxAddress`；
- 2 MiB/16 KiB 对齐。

全部返回 `EFI_OUT_OF_RESOURCES`。而同一固件：

- 76 MiB 的 `AllocatePool`（payload 读取）成功；
- 128 MiB 的 `AllocatePages` 在 H236bu 成功（见下）。

**结论**：这个 EDK2/固件对单次 `AllocatePages` 的上限落在
**128 MiB 和 256 MiB 之间**（更具体是 128 还是 192 还未测）。
继续在 256 MiB 上换地址/类型没有意义。

**坑**：`EfiLoaderCode`/`EfiLoaderData` 不是问题；`AllocateAddress`
不是问题；`Kernel.Base & (BLOCK_SIZE - 1) = 0x4000` 也不是唯一问题
（固定 2 MiB 地址同样失败）。

### 2.5 H236bu：128 MiB window + 窗口外 sidecar

源码改动（`drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c`）：

1. `WindowSize` 超过 128 MiB 时截到 128 MiB；
2. kernel、args、ADT、TrustCache、ZAP 放窗口内：
   - `ArgsAddress = ALIGN(Address + kernel_size, 16 KiB)`；
   - `TreeAddress = ArgsAddress + 4 KiB`；
   - `TrustCacheAddress = ALIGN(TreeAddress + TreeSize, 16 KiB)`；
   - `ZapAddress = ALIGN(TrustCacheAddress + TrustCacheSize, 1 MiB)`；
   - `Used = ALIGN(ZapAddress + 2 MiB, 16 KiB) - Address` ≈ 55 MiB；
3. ramdisk、addon、policy **不复制**，直接把 UniXNU pool 地址写进 ADT：
   - `RamdiskAddress = (UINT64)(UINTN)Request->Ramdisk`；
   - `AddonAddress = (UINT64)(UINTN)Addon`；
   - `PolicyAddress = (UINT64)(UINTN)Policies`；
4. 不再 `FreePool(Addon)` / `FreePool(Policies)`（成功路径）；
5. `(VOID)CopyRamdisk;` 只为压掉 `-Werror=unused-function`；
6. 固定表仍是 `0xA0000000`、`0xA0004000`、`0x100000000`、
   `0x180000000`，类型 `EfiLoaderCode`/`EfiLoaderData`。

屏幕结果（`417.jpg`）：

```text
Synchronous Exception at 0x0000000017ABAC58
UNiXNU: menu: shown 3 entries, default 0 'xnu', timeout 3000 ms, input yes, rotate 0 ms
UNiXNU: menu: timeout, booting default 0
UNiXNU: boot: entry 'xnu' (OnePlus 5 IOS)
UNiXNU: xnu: handing off 0 staged kext(s) to loader
...
DARWINBOOT: fixed window type=0 base=0x…   ← 屏幕右侧被菜单框/屏幕边缘截断
Synchronous Exception at 0x0000000017ABAC58
...
OnePlus 5 IOS
ios 17.7.11
Restart
Shut down
```

判读：

- `type=0` 是固定表的 `EfiLoaderCode`，第一项是 `0xA0000000`；
  屏幕只显示到 `base=0x0`，是因为长行被菜单框/屏幕右缘截断。
  **这是第一次看到 `AllocateWindow` 的固定分配成功行**，说明
  128 MiB `AllocatePages` 可行。
- 紧接着的 `Synchronous Exception at 0x0000000017ABAC58` 是
  **UEFI 异常处理器**打印的；`0x17ABAC58` 约 6.3 GiB，
  正好是 UniXNU 在 4 GiB 以上分配的 pool 区域（payload/addon/policy
  或 kernel image）。H236bu 把 ramdisk/addon/policy 留在这些 pool 里，
  是最大嫌疑。
- 菜单本身还在屏幕上，是因为 UniXNU 菜单不主动清屏；不能因为看到菜单
  就认为 boot 没开始。`UNiXNU: boot: entry 'xnu'` 和
  `DARWINBOOT: fixed window` 已经证明 DarwinBoot 跑到了窗口分配之后。
- 没有 adb/fastboot 只能说明设备既不在 Android 也不在 bootloader/TWRP，
  不能区分“卡在 DarwinBoot / 早期 XNU”和“已经进入 XNU 但显示未切换”。

**H236bu 的结论**：128 MiB 分配问题解决了，但“把大 sidecar 留在
4 GiB 以上的 pool、只把地址写进 ADT”不可用。下一步必须保证
这些 sidecar 在 XNU 早期页表能映射的范围内，或者重新回到窗口内。

### 2.6 H236bv：按 sagit `stageZap` 把 ZAP 移出 XNU arena（2026-11-09）

用户给出的 sagit-ios-port（`e23decf`）`boot/bridge/gpu_handoff.cpp:423`
`stageZap()` 是同一块板（MSM8998 + A540）的真机配方。它和我们失败点的逐条对应：

| sagit `stageZap` | 我们之前的失败 |
| --- | --- |
| `AllocateMaxAddress(EfiLoaderData, limit=UINT32_MAX)`（L449–452） | H236bf/bg 用 XNU `IOBufferMemoryDescriptor` + physical mask，XNU 直接忽略 mask；H236bm 的精确低 4G 分配也失败 |
| `total = usable + alignment - 4096`，多分配再内部对齐（L447–449） | H236bh 的“低 4G + 1 MiB 内部对齐”失败，差的就是“多分一块” |
| 分配后 `physicalConflict()` 检查已映射页表/旧 GPU 映射；冲突就 `FreePages` 并把 limit 压到冲突地址以下重试（L410–419、453–458） | 我们完全没做这一步；固件的 `Out of Resources` 很可能就是压到了已占用页 |
| 分配后 `FlushDataCache(writeback+invalidate)`，再 `SetMemoryAttributes(UC\|XP)`；失败还原 WB 再释放（L461–472） | 我们只做了 `dc cvac`，没有切 UC |
| 注释明确 “All pages stay outside the advertised XNU arena” | 我们反过来想把 ZAP 塞进 kernel window，才引出一堆 256 MiB/窗口分配问题 |
| 支持 DT carveout `qcom,gpu-zap-memory`（16 B LE64/LE64；>=0x80000000、4 KiB 对齐、<4 GiB、`EfiReservedMemoryType`+UC、无 RP/WP/RO/runtime，L477–500） | 这是“厂商已预留一块”的借用路径，我们没有；OP5 原厂 DT 只有 `qcom,zap-shader = "a540_zap"` |
| `docs/gpu/hardware-submission.md:127–160`：PAS 认证前不读、不 flush、不释放 ZAP 内存；只有 `trust=0` + fence 真写回 + ring 空闲才算成功；未进入 PAS 的准备失败要撤销普通分配 | 我们的 `zap_load` 在 PAS 前写入 `.mdt`/`.b02` 并 `cleanDcache`；认证后没有释放；这部分需要保持 |
| `boot/bridge/firmware_image.h` / `AdrenoFirmware.h::MDTImage`：PT_LOAD 且非 hash 段、`p_align`、按 `p_paddr` 偏移、BSS/空洞清零、4/16/32 MiB 上限 | H236bd 自己推的“.b02-only + 0x2000”与它一致；但内核的 `zap size` 检查误用了 `.elf` 的 17,204 B |
| `AdrenoStartup.h` / `QcomGPUSecure.*`：`CP_SET_SECURE_MODE(0)` + `WAIT_FOR_IDLE` + 真实 timestamp | 我们已经在用 opcode `0x66`；形态可以对比 |

上游语义也解释了为什么必须低 4 GiB：

- `drivers/firmware/qcom_scm.c` 的 PAS `init_image`/`auth_and_reset` 参数是
  **32 位物理地址**；H236be 的 `0x188c43000` 被截断就是这个 ABI 约束，
  不是我们的偏好。
- `drivers/soc/qcom/mdt_loader.c` 的 `qcom_mdt_pas_init()` 段规则与
  `MDTImage` 一致。
- `drivers/gpu/drm/msm/adreno/a5xx_gpu.c` 的 `a5xx_zap_shader_load()` 走
  `qcom_scm` 而不是 PIL；可对照参数打包。
- 下游 kgsl `adreno_a5xx.c` 的 `a5xx_microcode_load()` 用
  `subsystem_get("zap")`，ZAP 内存来自 DT 预先声明的 reserved carveout，
  由 bootloader/TZ 分配。原厂和 sagit 都是“启动阶段预留一块，OS 只借用”，
  从来没有“OS 自己找低内存给 ZAP”这条路。

**H236bv 实现**（`drivers/DarwinBoot`）：

1. 新增 `AllocateLow()`，严格按 sagit：
   - `AllocateMaxAddress`、`EfiLoaderData`、`limit=0xFFFFFFFF`；
   - `Total = Usable + Alignment - 4096`，在预留块内向上对齐；
   - 对齐后若越界或跨 4 GiB，`FreePages` 并把 `Limit = Raw - 1` 重试
     （最多 64 次）；
   - `FlushDataCache(WB-invalidate)`，再
     `SetMemoryAttributes(UC|XP)`；失败还原 `WB` 并释放。
2. ZAP 在 **kernel window 之外** 用 `AllocateLow(2 MiB, 1 MiB, UC|XP)`
   预留，`zap-base` 指向它；`Used`/`Args->MemorySize` 不再包含 ZAP。
3. kernel window 先试 **192 MiB**；如果固件的单次上限仍是 128 MiB，
   回退到 128 MiB，并用同一个 `AllocateLow()` 把 ramdisk/addon/policy
   放到低 4 GiB。192 MiB 成功时则把这些 sidecar 放回窗口内（`Used` ≈141.5 MiB，
   留约 50 MiB VM）；128 MiB 时 `Used` ≈52.6 MiB，留约 75 MiB VM。
4. 修正内核 `NativeA540C3.cpp` 的 ZAP 大小检查：
   `.elf`（17,204 B）只是回归参考，运行时镜像必须用 `.b02`（4,916 B）；
   `zapImage.bytes` 仍是 `0x2000`。
5. TrustCache 始终留在窗口内；ZAP 在窗口外低 4G；ramdisk/addon/policy
   在 192 时窗口内、128 时低 4G。
6. Legacy 归档：补 `ArmSmmu4K.o`/`ArmSmmu4KProgram.o`/`ArmSmmu4KMmio.o`/
   `ArmSmmu4KStreams.o`/`ArmSmmu4KContext.o`；A 线
   `AGXAccelerator`/`IOAcceleratorES` 探针不链接，改用
   `NativeA540AcceleratorStub.cpp` 提供 `native_a540_*`、
   `native_a540_accelerator_probe`、`native_iogpu_accel_probe` 和空的
   `__GLOBAL__sub_I_NativeA540AcceleratorProbe.cpp`；`NativeA540C3.cpp`
   仍保留完整 C3。

H236bv 产物：

```text
firmware 4dd964a8bfc87775f134954418cb9b77d182d9e5926890311dd6c42837074052
kernel   453d668bd8f983d84c33099856b4208fe53d0c1a91629bb292a43c3dcf36a9f2
payload  4a30ad17b1c465e5cf77c24d4b1d1bb3491d66b9623022ceb13a97d0230c1349
boot     8149ba01e032a05bfea16a441db202717030c87015aebaa61354ed3b0ccb0a81
```

设备现在没有 adb/fastboot，需要手动重启到 bootloader/TWRP，
再 `fastboot boot boot-H236bv.img`。实测时要看：

```text
DARWINBOOT: low alloc base=… raw=… total=…      (zap)
DARWINBOOT: fixed window type=… base=…          (192 或 128)
NATIVE_GPU_C3: zap alloc mdt=… image=…
NATIVE_GPU_C3: zap auth rc=0
NATIVE_GPU_C3: zap unsecure … trust=00000000
```

### 2.7 H236bv 实测：0x17ABAC18，以及 H236bw（2026-11-09）

H236bv `fastboot boot` 返回 OKAY，但屏幕在菜单条目下给出：

```text
Synchronous Exception at 0x0000000017ABAC18
```

没有看到 `DARWINBOOT: low alloc`/`fixed window` 行。`0x17A` 仍是 4 GiB 以上的
Image/Addon pool（H236bu 是 `0x17ABAC58`）。这说明：

- 128/192 窗口和低 4G ZAP 本身未必失败；
- H236bv 新增的 `AllocateLow(..., UC|XP)` / `SetMemoryAttributes` 是相对
  H236bi/H236be 的新变量；
- Image/Addon 的 `CopyMem` 在 H236bi/H236be 的 256 MiB 窗口里是成功的，
  现在异常落在同一个 >4G 池，最可能是 `SetMemoryAttributes` 之后从该池的
  复制不可访问，或源池本身没有按预期映射。

H236bw：

- ZAP `AllocateLow` 改为 `Attributes=0`（WB/normal），boot 阶段不再调
  `SetMemoryAttributes(UC|XP)`；内核 `mapWindow` 仍用 `kIOMapInhibitCache`，
  `.mdt`/`.b02` 写入后 `cleanDcache`。
- 屏上加 4 行诊断：`ZAP LOW`、`WIN`、`IMG/ADD/POL/RAM`、`COPY DONE`。
- 产物：firmware `d02b3812…`、boot `4f0a892a…`、payload `4a30ad17…`、
  kernel `453d668b…`。
- 判读：如果 `IMG`/`COPY DONE` 出现后异常，下一步把 Image/Addon/Policies
  复制到低 4G 再进窗口；如果 `ZAP LOW`/`WIN` 就异常，查 `AllocateLow`/窗口。

---

## 3. 踩过的坑（按重要性排序）

### 3.1 不要把 `owned_memory_size` 当成实际窗口

`board.toml` 的 `owned_memory_size = "0x100000000"` 没有出现在旧 payload
的 ADT 里；实际 `WindowSize` 是 256 MiB。任何“4 GiB 低窗口”的推理都会
从第一步就错。以 DarwinBoot 打印的 `WindowSize` 为准。

### 3.2 256 MiB `AllocatePages` 是固件上限，不是地址问题

- 低 4.2 GiB run、高 264 MiB run 都存在；
- `0xA0000000`、`0xA0004000`、`0x100000000`、`0x180000000` 都失败；
- `EfiLoaderCode`/`EfiLoaderData` 都失败；
- `AllocateAddress`/`AllocateMaxAddress` 都失败；
- 76 MiB `AllocatePool` 成功，128 MiB `AllocatePages` 成功。

**不要再在 256 MiB 上换参数。** 要么 128 MiB（或最多 192 MiB，待测），
要么减少 payload/把 sidecar 放到可映射区域。

### 3.3 `NO KERNEL WINDOW size=0x1000` 是截断

`DiagDraw` 的字符串在屏幕宽度处被截断，`0x10000000` 可能只剩
`0x1000`。看到“4 KiB”先怀疑显示宽度，不要当成实际请求。

### 3.4 窗口外 sidecar 不等于“地址写进 ADT 就能用”

H236bu 证明：`Request->Ramdisk`（76 MiB）、`Addon`（12 MiB）、
`Policies`（1 MiB）留在 `AllocatePool` 的 4 GiB 以上地址，
只把地址写进 ADT 后，boot 在 `0x17ABAC58` 同步异常。
XNU 早期页表/`arm_vm_init` 只保证窗口和 TrustCache 等特定区域；
`RAMDisk`/`GpuAddon`/`RootPolicies` 的物理地址不能假设“UEFI 能访问，
XNU 就一定能访问”。

### 3.5 TrustCache 必须在窗口内（或至少可映射）

H236bu 把 TrustCache 放在窗口内（`TreeAddress` 之后），这是有意保留的；
`arm_vm_init` 对 TrustCache 的位置有要求。不要把它和 ramdisk 一起搬出去。

### 3.6 `CopyRamdisk`/`KeepPacked` 的 `-Werror`

移除窗口内 ramdisk 复制后，`PackedRamdisk.h` 里的静态 `CopyRamdisk`
变成未使用，GCC `-Werror=unused-function` 直接失败。要么保留一个真实的
fallback，要么 `(VOID)CopyRamdisk;`。`KeepPacked`/`RamdiskPacked`/
`RamdiskExpandedSize` 仍被 `AdtNode`/`RamdiskLayout` 的地址参数使用，
一般不会报未使用；但改布局时要用编译器确认。

### 3.7 菜单标题、条目、logo 是三层东西

- `board.toml` 的 `[ui] title` / `ui_title` 生成 payload 的
  `[ui] title`；这是**菜单/logo 标题**，最终保持 `UniXNU`；
- `[[payload.menu]]` 或 xnu 条目标题是**条目文字**；
  这里是 `OnePlus 5 IOS`（全大写 IOS）；
- `Ui.c` 的 type tag 是条目下面的 `ios 17.7.11`；
- `[ui] logo = true` 保留原有 logo。把 `[ui] title` 改成
  `OnePlus 5 IOS` 会把 logo/布局挤坏，也会改变用户要求保留的标题。

H236bu 屏幕已确认：`OnePlus 5 IOS`、`ios 17.7.11`、`Restart`、
`Shut down` 三项可见，UniXNU logo 保留。

### 3.8 菜单不会清屏，屏幕上的旧异常可能是上一次 boot 的

H236bu 屏幕顶部和条目下方各有一条
`Synchronous Exception at 0x0000000017ABAC58`；顶部那条在
`UNiXNU: menu` 日志之前，是旧的；条目下方那条在
`DARWINBOOT: fixed window` 之后，是新的。判断当前结果要看
**日志顺序和最后新出现的那条**，不能只看照片最上方。

### 3.9 `AllocatePool` 成功 ≠ `AllocatePages` 同尺寸成功

76 MiB payload 用 `AllocatePool` 成功；这不代表 128/256 MiB
`AllocatePages` 一定成功。H236bu 的 128 MiB 成功是单独验证的；
256 MiB 仍失败。

### 3.10 `fastboot boot` 后没有 adb/fastboot 不是“必然成功”

菜单、DarwinBoot 卡住、早期 XNU 卡住都可能没有 adb/fastboot。
要结合屏幕、15 秒诊断和（最好）串口日志判断。

### 3.11 内核 ZAP 大小检查曾误用 `.elf`

H236bi 内核的 `zap_load()` 用
`a540_fw_zap_elf_size > c.zapImage.bytes`（17,204 > 8,192）判断，
导致 `zap size` 在 step 40 必然失败；H236be 的 `zap auth rc=0` 是
`.elf` 加入之前的内核。运行时镜像只能是 `.b02`（4,916 B），
`.elf` 只是 `.mdt`+`.b00`+`.b01`+`.b02` 的回归参考。H236bv 已改为
`a540_fw_zap_b02_size`，并用 `(void)` 保持 `.elf` 的引用。

### 3.12 低 4G ZAP 的关键是“多分配 + limit 回退”

`AllocateMaxAddress(EfiLoaderData, limit=UINT32_MAX)` 不是只把
`limit` 设成 4 GiB 就够：

- 要分配 `usable + alignment - 4096`，再在块内向上对齐；
- 对齐后若跨 4 GiB，要 `FreePages` 并把 `limit` 压到 `raw - 1` 重试；
- 分配后 `FlushDataCache(WB-invalidate)`，再 `SetMemoryAttributes(UC|XP)`，
  失败还原 WB 再释放。

H236bh 的“低 4G + 1 MiB 对齐”失败，差的就是“多分一块”和 limit 回退。

### 3.13 窗口外 sidecar 必须落在 XNU 能映射的范围

H236bu 把 ramdisk/addon/policy 留在 4 GiB 以上的 pool，只写 ADT；
boot 在 `0x17ABAC58` 同步异常。H236bv 对 128 MiB 分支用
`AllocateLow()` 把 sidecar 放到低 4G；192 MiB 分支则放回窗口内。
不要把“UEFI 能访问”当成“XNU 早期能访问”。

### 3.14 Legacy archive 的 A5403/SMMU/probe member

H236bv 重编 Legacy 归档时踩到：

- `NativeA540C3.o` 需要 `ArmSmmu4K.o`/`ArmSmmu4KProgram.o`/
  `ArmSmmu4KMmio.o`/`ArmSmmu4KStreams.o`/`ArmSmmu4KContext.o` 这些
  kit 对象，否则 `ArmSmmu4KBindMmio`/`Build`/`ProgramDisabledContext`
  未定义；
- `NativeA540AcceleratorProbe.o` 必须提供 `native_a540_*` 和
  `native_a540_accelerator_probe`；
- `build-report.json` 的 source hash 和 archive hash 会被
  `build-xnu-4k-baseline.sh` 校验；改源码后必须重编归档，不能只改报告；
- `(VOID)` 在 C++ 归档里未定义，要用 `(void)`。

### 3.15 Mac 构建树的 A-line AGX 探针

`NativeA540AcceleratorProbe.cpp` 里带 `AGXAccelerator : IOAcceleratorES`
（A 线）的发布探针；`LegacyDisplayProbe.cpp:24` 还按名字调用它的
`__GLOBAL__sub_I_NativeA540AcceleratorProbe.cpp`。B 线 H236bv 的 C3
不需要 AGX，也不需要 `IOAcceleratorFamily2`，所以链接会报
`IOAcceleratorES` 未定义。

H236bv 用 `NativeA540AcceleratorStub.cpp` 提供
`native_a540_abi_report(s)`、`open_count/type`、`sel_count/last`、
`native_a540_accel_state`、`native_a540_accelerator_probe()`、
`native_iogpu_accel_probe()` 和空的
`__GLOBAL__sub_I_NativeA540AcceleratorProbe.cpp`；`NativeA540C3.cpp`
仍保留完整 C3，Legacy 归档只链接 A540 C3 + Stub + `ArmSmmu4K` 对象。
这不会让 A-line AGX 路径“通过”，只是让 B-line C3 能链接和启动。

---

## 4. 当前产物

| 文件 | SHA-256 |
| --- | --- |
| H236bi kernel | `53cedef9…` |
| `payload-H236bq.img`（菜单/logo 最终版） | `4580eb1723ec47e24a5684351a4bff7b8d49776aa7451bf0330ac11668b5536d` |
| H236bu firmware `uefi-cheeseburger.img.gz-dtb` | `519f76638abcfd9f3118c53217a8f2fa5f57b78db9dccee1d749f1056c5c0af7` |
| `boot-H236bu.img` | `bf73e82bed5f5dde410d4d3190bd83676030c639527d2847af7071daf29e26fc` |
| H236bv firmware `uefi-cheeseburger.img.gz-dtb` | `4dd964a8bfc87775f134954418cb9b77d182d9e5926890311dd6c42837074052` |
| H236bv kernel `kernel.macho` | `453d668bd8f983d84c33099856b4208fe53d0c1a91629bb292a43c3dcf36a9f2` |
| H236bv payload | `4a30ad17b1c465e5cf77c24d4b1d1bb3491d66b9623022ceb13a97d0230c1349` |
| `boot-H236bv.img` | `8149ba01e032a05bfea16a441db202717030c87015aebaa61354ed3b0ccb0a81` |
| H236bw firmware `uefi-cheeseburger.img.gz-dtb` | `d02b38122a640807ca916599771302da1e93af4aac2110452dd8308f7b6933d6` |
| `boot-H236bw.img` | `4f0a892a53fcdf9859425b171b1ff8d3ee7411c46cbdc7205b4001311a4fada7` |

其他镜像的 boot 哈希（`/tmp/opencode/boot-H236b*.img`）：

```text
H236bi 554f77822c2796c840e7cb27ace456b491b1db4b730616a198a8dcc2e3a55584
H236bj 0673f344ff13908a8f0adf8699e69e3af2ae5edc5655d7c3abd49815928951ab
H236bk 42ecf2aa9d9f152124d2e901d6a8ab9bd7a22f603ca7477607431069eb989cad
H236bl d44791aa3416bc9311bdc8e50cacb9bd0f27d5c3c1ecb098a73ec504f6f9bdf8
H236bm b38164561405628cf27326908a5a41fa301c8e1df3244c7f801f71a62f9e2307
H236bn 034a702c06df14bec9d387296507b4e1f4875ee96261447d19985cb72fbb8e75
H236bo 36904d0502ed75184add71f2f452204cb0309de2c9fbccae0c1e5aae12d7c9ae
H236bp d7e1fd2bf8e18940747b745ef266a1c96f6a833eb47a9f6dd16b4ea13356df6b
H236bq de27ee09a6241e6c8a76fe9984caa6b666e49c3f06270a9fb1c41a2d4ccab566
H236br 601b42b2a6cc502b005aa42d26cf8c93cd5b94f1a7c7e03c3562b2181c202725
H236bs 44578508dabb49d03697fec134e2f20a737be42d1bb23901bec6000c8828a625
H236bt 9c2c915783dcea0975afc9828a04818f682fc907831300859f39944e81ca36d7
H236bu bf73e82bed5f5dde410d4d3190bd83676030c639527d2847af7071daf29e26fc
```

固件哈希（按记录，H236bu 用当前构建）：

```text
H236bi 362f68e9…
H236bj 979b7682…
H236bk 86994141…
H236bm 5afa4290…
H236bo 05951cf1…
H236bp b1647519…
H236bq e0a0e039…
H236br 2db31eed…
H236bs 5828e119…
H236bt 27e5447c…
H236bu 519f7663…
```

---

## 5. 构建/打包/启动命令

固件（Linux）：

```sh
cd /mnt/data_2048/project/ios/edk2-msm8998
UNIXNU_TREE=/mnt/data_2048/project/ios/UniXNU \
  ./build.sh -d cheeseburger -r RELEASE --skip-rootfs-gen
```

打包（Linux，用设备仓库的脚本）：

```sh
cd /mnt/data_2048/project/ios/UniXNU-cheeseburger
python3 scripts/make-bootimg.py \
  --edk2 /mnt/data_2048/project/ios/edk2-msm8998 \
  --kernel /mnt/data_2048/project/ios/edk2-msm8998/workspace/uefi-cheeseburger.img.gz-dtb \
  --payload /tmp/opencode/payload-H236bq.img \
  --out /tmp/opencode/boot-H236bu.img
```

启动（Windows host 连手机，只 boot 不 flash）：

```powershell
adb reboot bootloader
Start-Sleep -Seconds 10
fastboot boot D:\Users\ls\Documents\OnePlus5_ios\boot-H236bu.img
```

内核/prelink 仍在 macOS `lss@192.168.10.103` 上构建；payload 用
`./unixnu build payload` 生成。固件构建不包含 rootfs。

---

## 6. 下一步建议

H236bv 已经实现了 1–3 的核心；现在的顺序是：

1. **实测 H236bv**：
   - 屏幕先看 `DARWINBOOT: low alloc base=…`（ZAP 低 4G）、
     `fixed window type=… base=…`（192 或 128）；
   - 如果进 XNU，取 `NATIVE_GPU_C3: zap alloc mdt/image`、
     `zap init/mem setup/auth rc=0`、
     `zap unsecure … trust=00000000` 和 submit probe。
2. **192 MiB 成功时**：ramdisk/addon/policy 都在窗口内（`Used` ≈141.5 MiB），
   留约 50 MiB VM；ZAP 在窗口外低 4G。重点看 `trust` 是否清零；
   如果 VM 不足，再考虑减少 GpuAddon/scratch。
3. **192 MiB 失败、走 128 MiB 时**：ramdisk/addon/policy 由
   `AllocateLow()` 放到低 4G。重点看 `0x17ABAC58` 是否消失；
   如果低 4G 窗口外仍异常，说明 XNU 早期只映射了 kernel window，
   需要把 sidecar 重新塞回 128 MiB（缩 payload）或增大窗口。
4. **trust 仍为 1 时**：确认 `zap-base` 的 `base` 是 1 MiB 对齐、`base+2 MiB <= 4 GiB`、
   `.b02` 4916 B 写入的是 `base+1 MiB`；检查 `CP_SET_SECURE_MODE(0)` 后的
   `WAIT_FOR_IDLE`/fence/timestamp，而不是直接写 `SECVID_TRUST_CNTL`。
5. **可选 carveout 路径**：如果平台确实预留了
   `qcom,gpu-zap-memory`（16 B LE64/LE64、`EfiReservedMemoryType`+UC、
   无 RP/WP/RO/runtime），优先借用它；当前 OP5 ADT 只有
   `qcom,zap-shader = "a540_zap"`，没有 carveout，所以 H236bv 用
   `AllocateMaxAddress` 路径。
6. 不要动 TrustCache 的窗口内位置；不要把 `owned_memory_size`
   当成实际窗口；不要再用 256 MiB 单次 `AllocatePages`。

---

## 7. 一句话总结

H236bu 证明 256 MiB 是固件单次分配上限、128 MiB 可行；H236bv 按
sagit `stageZap` 把 ZAP 移到**窗口外的低 4 GiB**（多分配 + 对齐 + UC/XP），
并把内核 `.elf` 检查修回 `.b02`。下一步是实测 H236bv 的
`low alloc`/192-or-128 window/`zap auth`/`trust=0`，而不是继续调
256 MiB 窗口。
