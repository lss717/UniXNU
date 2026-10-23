# OnePlus 5（cheeseburger）UniXNU B 线适配计划

> 线路：**B — UniXNU / 4K**
> 设备：OnePlus 5（cheeseburger，MSM8998 / Snapdragon 835）
> 最终目标：**iPhone10,2 / iOS 16.7.16（20H392）手机形态**
> 临时基线：iPad7,1 / iPadOS 17.7.11（21H461），只用于隔离变量，**不是交付形态**
> 计划建立：2026-10-22
> 基线提交：UniXNU `e95b37d`（main）
> 进度文件：`plans/oneplus5-cheeseburger/STATUS.md`

---

## 0. 计划摘要

B 线是“UniXNU 原生引导链 + 4K XNU”的移植，不走 ios-sweet 的 shim/16K 路线。

最终形态：

```
Android ABL
  -> BootShim + UEFI 固件卷
     -> UniXNU 菜单
        -> DarwinBoot
           -> XNU 4K（xnu-8796 / iOS 16 目标）
              -> UFS 2.1 -> APFS root -> launchd -> SpringBoard
```

关键判断：

- **iPhone10,2 是最终身份**：1080×1920、Home 键、手机 UI，和 OnePlus 5 匹配。
- **iPad7,1 只是 B3 的临时测试夹具**：复用 sheng 已验证的 prelink/4K 基线，先把 MSM8998 平台和引导链跑通；B6 必须切到 iPhone10,2，不能把 iPad 形态当交付。
- **UFS 2.1 是关键路径**：显示和触摸可以后做，没有 UFS 就没有 root/userland。
- **首期不做 GPU**：Adreno 540 与 sheng 的 Adreno 740 差距太大；先 CPU 渲染。
- **不混用 IPSW**：kernelcache、DeviceTree、trust cache、OS/SystemOS/AppOS、dyld cache 必须来自同一份 IPSW。

---

## 1. 目标与非目标

### 1.1 目标（按顺序）

1. OnePlus 5 能通过 `fastboot boot` 进入 UEFI。
2. UniXNU 菜单出现，能读取 payload FAT 卷。
3. DarwinBoot 校验 kernel/ADT/trust cache 并跳入 XNU。
4. XNU 4K 在 MSM8998 上到达平台专家，CPU/GIC/timer 工作。
5. UFS 2.1 发布 userdata，XNU 挂载 root 并启动 `launchd`。
6. 切到 iPhone10,2 / iOS 16.7.16，进入锁屏/桌面。
7. 触摸、Home/音量键、基础电源工作，CPU 渲染 UI。
8. 文档、设备页、构建/启动命令、已知问题完善。

### 1.2 非目标（首期）

- Metal / Adreno 540 GPU。
- 相机、音频、WiFi、蓝牙、蜂窝、传感器、GPS。
- 充电、温控、suspend/resume、SEP/Face ID、数据保护。
- App Store、Apple ID、日常主力机。
- 把 A 线（ios-sweet/16K）的代码合并进来。

---

## 2. 已冻结的决策

| ID | 决策 | 理由 |
| --- | --- | --- |
| D1 | 选择 B 线（UniXNU / 4K） | 保持 UniXNU 的模块化设备仓库、UEFI 引导器、DarwinBoot、APFS/trust cache 模型 |
| D2 | 最终身份 iPhone10,2 / iOS 16.7.16（20H392） | 1080×1920 与 OnePlus 5 完全一致，手机 UI + Home 键 |
| D3 | iPad7,1 17.7.11 只作 B3 临时基线 | 复用 sheng 已验证的 prelink/4K，先隔离 MSM8998 平台问题 |
| D4 | 不混用 IPSW | kernelcache/ADT/trust cache/OS/AppOS/dyld cache 必须同源 |
| D5 | UEFI 基于 `edk2-msm8998` 的 `cheeseburger` target | 已有 OnePlus 5 UEFI 端口、ACPI、GOP、UFS 块设备 |
| D6 | 固件先用 `edk2-msm8998/build.sh`，不强接 `unixnu build firmware` | 它使用 GCC5 + 自有 DSC/FDF；直接套 CLANGPDB/Mu-Silicium 布局风险高 |
| D7 | boot image 用设备仓库的 `make-bootimg.py` 打包 | `unixnu bootimg` 假设 BootShim + 无头 FV，和 edk2-msm8998 的 FD 布局不同 |
| D8 | 内核在 macOS / GitHub Actions 构建 | 内核步骤需要 Xcode、`hdiutil`、`diskutil` |
| D9 | B5 的 UFS 移植是关键路径 | 没有 UFS 就没有可用的 root；没有便宜的替代 |
| D10 | 首期不做 GPU | A5xx 与 A7xx 驱动栈不兼容；CPU 渲染已验证可行 |

---

## 3. 硬件基线

> 以下地址来自 mainline MSM8998 / OnePlus 5 DTS 和 `edk2-msm8998`，作为起点；标“待实测”的必须在设备上确认。

| 项目 | 值 | 状态 |
| --- | --- | --- |
| SoC | MSM8998（Snapdragon 835），4×Kryo 280 Gold + 4×Silver | 已确认 |
| GPU | Adreno 540 | 已确认 |
| RAM | 6 GB 或 8 GB，DRAM base `0x80000000` | 容量待实测 |
| 屏幕 | 1080×1920 AMOLED | 已确认 |
| Framebuffer 参考 | `0x9d400000`，大小 `0x2400000`，stride `1080*4` | 待 UEFI 实测 |
| UFS HC | `0x1da4000`，大小 `0x2500`，IRQ GIC SPI 265 | 待实测 |
| UFS PHY | `0x1da7000`，大小 `0x1000` | 待实测 |
| UFS 逻辑块 | 通常 4096 | 待实测 |
| GICD | `0x17a00000`，大小 `0x10000` | 参考值 |
| GICR | `0x17b00000`，大小 `0x100000`，stride `0x20000` | 参考值 |
| Timer | 19.2 MHz | 参考值 |
| CPU MPIDR | `0,1,2,3,0x100,0x101,0x102,0x103` | 参考值 |
| Touch | Synaptics RMI4，I2C `0x20` | 待实测 |
| PMIC | PM8998 + PMI8998 + PM8005 | 已确认 |
| UEFI FD | base `0xd0000000`，size `0x600000`，FV 在 `+0x8000` | 已确认 |
| Boot image | header v1，kernel/ramdisk/tags offset 全 0 | 已确认 |
| 设备代号 | cheeseburger；5T 是 dumpling，不要混用 | 待确认机型 |

### 3.1 必须在 B0 补齐的值

- [ ] 实际 RAM：6 GB 还是 8 GB。
- [ ] userdata GPT 的 `first_lba`、`last_lba`。
- [ ] `lba_bytes`（UFS 逻辑块大小）。
- [ ] 实际 framebuffer 地址/大小/stride（UEFI GOP 日志）。
- [ ] 触摸 I2C 总线号和地址（后续 B7 用）。

采集命令（设备侧）：

```sh
# TWRP / postmarketOS root shell
sgdisk -p /dev/block/sda
# 或
parted /dev/block/sda unit s print

# fastboot
fastboot getvar all
```

---

## 4. 仓库与文件布局

### 4.1 新增仓库

| 仓库 | 作用 |
| --- | --- |
| `uefi-cheeseburger` | 基于 `edk2-msm8998`，加入 UniXNU、DarwinBoot、initrd 块设备驱动、framebuffer 日志 |
| `UniXNU-cheeseburger` | `board.toml`、defconfig、ADT 生成器、payload/bootimg 脚本、后续 UFS/触摸驱动 |

### 4.2 设备仓库骨架

```text
UniXNU-cheeseburger/
  board.toml
  board.iphone10-2.toml          # B6 目标 profile；先保留，不直接使用
  configs/
    cheeseburger_defconfig
  scripts/
    make-cheeseburger-adt.py     # 支持 --identity ipad7,1|iphone10,2
    make-bootimg.py              # 包装 edk2-msm8998 的 mkbootimg
    check-cheeseburger.py        # 固件/DTB/payload 预检
    select-target.py             # 切换 board.toml profile（可选）
  package/                       # 设备 kit，首期可为空
  drivers/                       # B5/B7 再添加
  patches/                       # B6 再添加
  .cache/firmware/               # 私有输入，不提交
```

### 4.3 UEFI 仓库改动

```text
uefi-cheeseburger/
  Config/cheeseburger.conf
  Platforms/Msm8998Pkg/Device/oneplus/cheeseburger/
    cheeseburger.dsc
    cheeseburger.fdf
    ...
  Platforms/Msm8998Pkg/Device/oneplus/cheeseburger/
    Drivers/CheeseburgerBootMemoryDxe/
      CheeseburgerBootMemoryDxe.c
      CheeseburgerBootMemoryDxe.inf
    Drivers/CheeseburgerGopLogDxe/       # 从 ShengGopLogDxe 移植/改名
    Drivers/CheeseburgerKeyInputDxe/     # 从 ShengKeyInputDxe 移植/改名
```

---

## 5. 目标 profile

### 5.1 最终目标：iPhone10,2 / 16.7.16

```toml
[ipsw]
product = "iPhone10,2"
version = "16.7.16"
build = "20H392"
device_class = "d21ap"
chip_id = 0x8015
board_id = 4
url = "https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-76738/B6C604B4-548E-401F-BBFF-916E3FFDF235/iPhone_5.5_P3_16.7.16_20H392_Restore.ipsw"
# sha256: b3882291a92ecf8763239a026813b3bafae66b7e317dee67011d90c202ccafef
fetch = ["KernelCache", "DeviceTree", "StaticTrustCache", "Cryptex1,SystemTrustCache"]

[userdata]
first_lba = 0x000000       # B0 填充
last_lba  = 0x000000       # B0 填充
lba_bytes = 4096           # B0 确认
windows = [
  { name = "OS", component = "OS" },
  { name = "SystemOS", component = "Cryptex1,SystemOS" },
  { name = "AppOS", component = "Cryptex1,AppOS" },   # iOS 16 可能需要，先用 `ipsw info` 确认
]
```

ADT 身份：

```text
compatible = "D21AP\0iPhone10,2\0oneplus,cheeseburger\0qcom,msm8998\0AppleARM\0"
model = "iPhone10,2"
target-type = "D21"
target-sub-type = "D21AP"
chip-id = 0x8015
```

`/product` 和 `/buttons` 不从 sheng 的 iPad 模板抄，**从真实 iPhone10,2（D21AP）DeviceTree 复制**，再按 OnePlus 5 的按键集调整。

### 5.2 临时基线：iPad7,1 / 17.7.11

B3 使用 sheng 的 `board.toml` 作为参考：

- `product = "iPad7,1"`
- `version = "17.7.11"`
- `build = "21H461"`
- `device_class = "j120ap"`
- `chip_id = 0x8011`
- `board_id = 12`
- prelink 的 `slide`、`early_security_init`、`roots`、trust cache 哈希先用 sheng 的值。

**注意**：B3 只验证引导链和 MSM8998 平台，不做设备页、不写“支持 iPadOS”的结论。

---

## 6. 阶段计划

### B0 准备与基线冻结（预计 2–3 天）

**目标**：设备可恢复、硬件事实齐全、构建环境可用、两套 IPSW 就位。

任务：

- [ ] 确认机型是 OnePlus 5（cheeseburger）而不是 5T（dumpling）。
- [ ] 解锁 bootloader；备份 `persist`、`modem`、`efs`、`boot`、`recovery`，有条件整盘备份。
- [ ] `fastboot getvar all`，记录分区大小、RAM、slot 信息。
- [ ] TWRP/postmarketOS 下 dump GPT，记录 userdata 的 `first_lba`/`last_lba`/`lba_bytes`。
- [ ] 确认 RAM 容量、UFS 逻辑块大小。
- [ ] macOS + Xcode 或 GitHub Actions 可用；Linux 侧安装 Python 3.11+、git、make、dtc、mtools、LLVM/lld。
- [x] `git submodule update --init --recursive` 初始化 UniXNU 子模块。
- [x] clone `edk2-msm8998` 到 `/home/ls/edk2-msm8998`（upstream shallow；`uefi-cheeseburger` fork 待建）。
- [ ] 下载并校验 iPhone10,2 16.7.16 IPSW 和 iPad7,1 17.7.11 IPSW。
- [ ] 提取并缓存 `KernelCache`、`DeviceTree`、`StaticTrustCache`、`Cryptex1,SystemTrustCache`；放在 `.cache/firmware/`，不提交。
- [ ] 记录基线提交、工具版本、IPSW 哈希到 `STATUS.md`。

验收（G0）：

- `fastboot devices` 正常。
- GPT/RAM/UFS 值写入本计划第 3 节。
- 两份 IPSW 的 SHA-256 校验通过。
- `edk2-msm8998/build.sh --help` 正常，UniXNU 子模块已初始化。

风险：

- 解锁会清数据；先备份。
- edk2-msm8998 对部分机型有 UFS 清空警告；只 `fastboot boot`，不 `flash`。
- 没有 UART；B0 先准备 framebuffer 日志/panic screen 方案。

---

### B1 UEFI 固件与 UniXNU 集成（预计 1–2 周）

**目标**：OnePlus 5 能启动带 UniXNU/DarwinBoot 的 UEFI，菜单出现，payload FAT 卷可读。

任务（2026-10-22 进展）：

- [x] 用上游 `edk2-msm8998` 构建 `cheeseburger` 基线，确认 FD 生成和 `boot-cheeseburger.img` 打包。
- [ ] 在设备上验证屏幕输出、UEFI shell、`map -r` 能看到 UFS 分区。
- [x] 建本地分支 `unixnu-cheeseburger`；GitHub fork 待建。
- [x] 移植 `ShengBootMemoryDxe` -> `CheeseburgerBootMemoryDxe`：
  - edk2-msm8998 用 `PcdDeviceTreeStore = 0x83300000` 保存 live DTB 指针，首版直接读该地址；
  - 解析 `/chosen/linux,initrd-start` 和 `/chosen/linux,initrd-end`；
  - 安装只读 `EFI_BLOCK_IO_PROTOCOL`，让 `PartitionDxe`/`FatPkg` 挂载 payload；
  - 首版不做 `AddMemory`，沿用 edk2-msm8998 的内存图。
- [ ] 移植/改名 `ShengGopLogDxe` 为 framebuffer 日志；无 UART 时靠屏幕看 `UNIXNU:`/`DARWINBOOT:`。
- [ ] 移植/改名 `ShengKeyInputDxe`，映射 OnePlus 5 的电源/音量键，供 UniXNU 菜单使用。
- [x] 在 cheeseburger DSC/FDF 加入：
  - `UniXNUPkg/Application/UniXNU/UniXNU.inf`
  - `UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf`
  - `DarwinBootPkg/Driver/DarwinBoot.inf`
  - `CheeseburgerBootMemoryDxe.inf`
- [x] DSC 补 `FdtLib`、`UniXNULib`、`PACKAGES_PATH`（`{tree}/package`、`{tree}/drivers/DarwinBoot`）。
- [x] 用 GCC5 构建成功；本轮加了三个兼容修补：
  - `ArmPlatformLibMem.c` 的 `MemoryTable` 改为 `STATIC`，绕开 GCC 13 的 `-Werror=dangling-pointer`；
  - 旧 edk2 缺 `<Library/FdtLib.h>`，加一个映射到 `libfdt` 的兼容头；
  - 旧 edk2 缺 `<AsmMacroLib.h>`，加一个最小 `ASM_FUNC` 兼容头。
- [ ] 写 `scripts/check-cheeseburger.py` 预检：FD size `0x600000`、FD base `0xd0000000`、DTB、payload。
- [x] 准备只含 `unixnu.toml` 的 32 MiB `OP5ESP` payload，并打包测试 boot image；待设备验证菜单和卷。

本轮发现：

- **FV 空间很紧**：从 FDF 移除 `SimpleInitMain`（8.4 MB）和 `LogoDxe`（6.2 MB）后，`FVMAIN` 仍是 100% 满（压缩 FV 约 43%，剩余约 3.5 MB）。再加 GopLog/KeyInput 时可能需要继续删模块或增大 FD。
- **非空 ramdisk 不能用 offset 0**：`build.sh` 默认 `kernel_offset=ramdisk_offset=tags_offset=0`，只适合空 ramdisk。测试镜像改用 `ramdisk_offset=0x02000000`、`tags_offset=0x04000000`，避免 32 MiB payload 覆盖 3 MB 内核。
- `CheeseburgerBootMemoryDxe` 首版硬编码 `PcdDeviceTreeStore=0x83300000`；设备上需要确认该地址和 `/chosen` 属性。

验收（G1）：

- 屏幕/UEFI 日志出现 `UNIXNU:`。
- 菜单列出至少一个 entry。
- `OP5ESP` FAT 卷可见，`\EFI\UniXNU\unixnu.toml` 可读。
- `drivers`/`dh` 能看到 UniXNU、DarwinBoot、BlockIo。

命令参考：

```sh
cd /home/ls/edk2-msm8998
UNIXNU_TREE=/home/ls/UniXNU bash build.sh --device cheeseburger --release RELEASE
fastboot boot /home/ls/UniXNU/out/cheeseburger/b1/boot-op5-b1-safe.img
```

风险：

- GCC5 vs CLANGPDB：本轮已用 GCC5 编过 UniXNU/DarwinBoot；后续新增驱动仍要过 GCC 13。
- edk2-msm8998 的 DTB 存储是固定地址，不是 sheng 的 HOB：`CheeseburgerBootMemoryDxe` 需要设备实测确认。
- 输入：edk2-msm8998 的按键映射可能不满足 UniXNU 菜单，需要移植 KeyInput。

---

### B2 设备仓库、ADT、payload（预计 1–2 周）

**目标**：`UniXNU-cheeseburger` 能构建 payload 和 boot image，ADT 通过解析。

任务：

- [ ] 创建 `UniXNU-cheeseburger` 骨架（见 4.2）。
- [ ] 写 `board.toml`，B3 用 iPad7,1 临时 profile；同时保留 `board.iphone10-2.toml`。
- [ ] 写 `configs/cheeseburger_defconfig`，首期最小集：
  - `CONFIG_XNU_BUILD_ARCHIVES=y`
  - `CONFIG_XNU_SOURCE_CORECRYPTO14=y`
  - `CONFIG_XNU_SOURCE_PTHREAD=y`
  - `CONFIG_XNU_ARM_DT_PLATFORM=y`
  - `CONFIG_XNU_ARMCPU=y`
  - `CONFIG_XNU_NATIVE_ARCH_TIMER=y`
  - `CONFIG_XNU_NATIVE_CS_HASH_CACHE=y`
  - `CONFIG_XNU_TRUST_CACHE_RUNTIME=y`
  - `CONFIG_XNU_BOOT_PROGRESS=y`
  - `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`
  - `CONFIG_XNU_SOURCE_MOCKFS=y`
  - `CONFIG_XNU_CRYPTO_BOOTSTRAP="prelinked"`
  - 暂不打开：UFS、Adreno、PMGR、PAN、MobileDisplay。
- [ ] 从 `make-sheng-adt.py` 改出 `make-cheeseburger-adt.py`：
  - MSM8998 常量：GICD `0x17a00000`，GICR `0x17b00000`，stride `0x20000`，timebase `19200000`；
  - CPU regs `0,1,2,3,0x100..0x103`；
  - UFS 节点 `qcom,msm8998-ufshc`（首版只用于匹配，地址用驱动常量）；
  - 支持 `--identity ipad7,1` 和 `--identity iphone10,2`；
  - iPhone 模式下复制真实 D21AP `/product`、`/buttons`。
- [ ] 写 `scripts/make-bootimg.py`：
  - 输入：`workspace/uefi-cheeseburger.img.gz-dtb`、`payload.img`；
  - 调用 edk2-msm8998 的 `mkbootimg.py`；
  - header v1，`--kernel_offset 0 --ramdisk_offset 0 --tags_offset 0`；
  - 输出 `out/cheeseburger/boot/boot.img` 和 JSON 报告。
- [ ] 写 `scripts/check-cheeseburger.py`：FD/DTB/payload/ADT 预检。
- [ ] `unixnu defconfig`、`unixnu fetch`、`unixnu build payload`。
- [ ] 可选：QEMU 里跑一遍 UniXNU/DarwinBoot 快速验证。

验收（G2 前半）：

- `unixnu build payload` 成功，payload report 哈希一致。
- `make-bootimg.py` 生成的 boot image 可解包，ramdisk 字节一致。
- ADT 可被解析，`/cpus`、`/arm-io`、`/chosen`、`/defaults`、`/options` 齐全。

命令参考：

```sh
./unixnu defconfig cheeseburger_defconfig -D ../UniXNU-cheeseburger
./unixnu fetch
./unixnu build payload
```

QEMU 可选：

```sh
python3 scripts/qemu-entry/make-dt.py --armvirt --armcpu --smp 2 \
  --owned-memory-size 0x20000000 --output build/qemu.dtb
python3 package/Scripts/stage-esp.py -o out/esp \
  package/UniXNUPkg/Test/Qemu/esp \
  --put out/cheeseburger/package/Build/Out/UniXNU.efi=EFI/BOOT/BOOTAA64.EFI
python3 package/Scripts/qemu-run.py out/esp \
  --log out/qemu.log --screenshot out/qemu.png \
  --expect "UNIXNU: menu: shown" --expect "DARWINBOOT:"
```

风险：

- iOS 16 的 `AppOS` 组件名/窗口要先用 `unixnu ipsw info` 确认。
- ADT 的 `dram-size` 先按固件可见上限，不要直接写 6/8 GB。
- `unixnu bootimg` 不能直接用，必须走设备脚本。

---

### B3 4K XNU 引导链验证（iPad7,1 临时基线，预计 1–2 周，硬性 time-box）

**目标**：在 MSM8998 上验证 UniXNU -> DarwinBoot -> XNU 4K 的完整跳转；不追求 iPhone 形态。

任务：

- [ ] 以 sheng 的 iPad7,1 17.7.11 prelink 为基线，构建最小内核：
  - archives 只保留 `ArmDTPlatform`、`ArmCpu`、corecrypto、pthread、boot-progress、NativeLegacyDisplay、mockfs；
  - 不包含 NativeUfs、NativeAdreno、NativeMobileDisplay、sheng PMGR。
- [ ] `payload.adt` 用 iPad 临时 profile；`ipad_identity=true` 只用于让 MobileGestalt 走通，B3 不做 UI。
- [ ] 内核参数最小化：`-v`、`debug=0x14e`、`boot-progress=2`、`offline-legacy-gop=1`、`offline-legacy-unit-scale=1`。
- [ ] 启动，确认 `DARWINBOOT:` 日志、XNU 版本、framebuffer 输出。
- [ ] 记录 panic：如果 panic 点名缺失的 provider，这是 B3 的成功信号，不是失败。
- [ ] 2 周内没有到达 XNU 控制台，停止并复盘（不要无限期卡在 B3）。

验收（G2/G3）：

- `DARWINBOOT:` 打印 virtual/physical/entry、framebuffer。
- XNU 打印版本和 boot-args。
- 到达平台专家，或 panic 明确点名缺失的 platform/storage provider。

风险：

- sheng 的 `roots` 里 AppleARMPlatform/ApplePMGR 可能与 MSM8998 冲突；逐个裁剪。
- 4K 代码签名补丁在 iPad7,1 17.7.11 上已验证，B3 不要改它。
- 没有 UART，只能靠 GOP 日志/panic screen。

---

### B4 MSM8998 平台专家（预计 3–5 天）

**目标**：XNU 平台专家、CPU、GIC、timer 在 MSM8998 上工作。

任务：

- [ ] 确认 `/cpus` 8 核、MPIDR `0,1,2,3,0x100..0x103`、`/psci` method `smc`。
- [ ] 确认 `ArmCpu` 的 GICv3 初始化、SPI/IPI、arch timer。
- [ ] 校准 `timebase-frequency=19200000`。
- [ ] 确认 `/arm-io` 的 `ranges` 覆盖 GIC；UFS 低于窗口，用驱动常量。
- [ ] 补 `/chosen` 的 NVRAM proxy、`dram-base`、`dram-size`、`crypto-hash-method`。
- [ ] 处理 `sleep-disabled`、`kern.maxvnodes`。
- [ ] 裁剪 prelink roots：移除与 MSM8998 冲突的 Apple 平台组件，保留原生 `ArmDTPlatform`。
- [ ] 打开 `XNU_NATIVE_PAN` 前先确认 Kryo 280 支持；默认先关。

验收（G3/G4）：

- IOKit registry 起来。
- 平台专家 `configure()` 成功。
- 8 核可见（或至少 boot CPU + 1 secondary）。
- panic 转向存储 provider，而不是平台 provider。

---

### B5 UFS 2.1 与 root（预计 4–8 周，关键路径）

**目标**：UFS 发布 userdata，XNU 挂载 root，`launchd` 启动。

任务：

- [ ] 在 mockfs / RAM block 上先验证块栈，避免把块栈问题和 UFS 问题混在一起。
- [ ] 移植 `NativeUfs`：
  - HC `0x1da4000`/`0x2500`，PHY `0x1da7000`/`0x1000`，IRQ 265；
  - GCC UFS 时钟/复位、RPM 参考时钟、PM8998/PMI8998 电源轨；
  - MSM8998 QMP UFS PHY 初始化（参考 mainline `qcom,msm8998-qmp-ufs-phy`）；
  - UFS 2.1 HC 的命令队列、UIC、power mode；
  - SMMU：MMU-500，4K；先试 `ArmSmmu4K`，不匹配就新写 context bank。
- [ ] 第一版用“handoff 模式”：UEFI 已初始化 HC/PHY/时钟，XNU 只接管命令提交；SMMU 先旁路/复用 UEFI 映射。
- [ ] 填 `userdata` 的 GPT LBAs，`lba_bytes` 用实测值。
- [ ] 用 B3 的 iPad 临时 root 先验证 OS/SystemOS 窗口和 root UUID。
- [ ] 备份后 flash userdata；确认 `OS`/`SystemOS` 媒体出现。
- [ ] 确认 root UUID 匹配，`launchd` 启动。

验收（G4）：

- UFS 日志出现 link speed、命令队列、LUN。
- `OS`/`SystemOS` 媒体发布。
- root UUID 匹配，`launchd` 运行。
- 至少到达用户态第一个进程。

风险：

- UFS 是整个计划最容易超期的部分；如果 handoff 模式可行，优先它。
- MSM8998 是 UFS 2.1，不能直接照搬 sheng 的 UFS 3.x/4.x 代码。
- SMMU 4K 上下文可能需新写；先旁路，后补。
- 没有 UFS 就没有 root；不要用“RAM 装完整根卷”这种不现实方案。

---

### B6 切换 iPhone10,2 / iOS 16.7.16（预计 3–5 周）

**目标**：从 iPad 临时基线切到最终 iPhone10,2 手机形态。

任务：

- [ ] 冻结 B3–B5 的可用结果，打 tag/记录。
- [ ] 把 UniXNU 4K 补丁回移到 xnu-8796（iOS 16）：
  - 逐条 `git apply --check`；
  - 列出不能直接应用的补丁，按 4K 页表、代码签名、平台、存储分类重写；
  - 先只保留“能 boot 到平台专家”的最小补丁集，逐步加回。
- [ ] 用 iPhone10,2 20H392 的 kernelcache 重新 prelink：
  - 计算 `kernelcache_sha256`；
  - 确定 `slide`、`roots`、`early_security_init`；
  - 重新计算 trust cache 哈希；
  - 不能复用 sheng/iPad 的任何地址或哈希。
- [ ] 更新 ADT：
  - `model=iPhone10,2`，`target-type=D21`，`target-sub-type=D21AP`；
  - 从真实 D21AP DeviceTree 复制 `/product`、`/buttons`；
  - `chip-id=0x8015`；
  - 显示 1080×1920，逻辑 414×736@3x，按真机 downsample；
  - Home 键类型用 D21AP 真实值，不要用 sheng 的 2。
- [ ] 更新 userdata：
  - 加 `AppOS` 窗口（如 `ipsw info` 确认需要）；
  - 重新读取 iPhone10,2 的 root volume UUID；
  - 重新构建 userdata 镜像。
- [ ] 切 `board.toml` 到 iPhone10,2 profile，重建 payload/boot image。
- [ ] 启动到锁屏；先不要追求 App Store/Apple ID。
- [ ] 决策门：如果 4K 回移成本超出预算，回退为“iPad7,1 17.7.11 的 UniXNU 端口”，把 iPhone10,2 作为后续独立项目；不要中途混用 IPSW。

验收（G5）：

- iPhone10,2 身份被 MobileGestalt 识别为手机。
- 1080×1920 锁屏出现。
- `launchd`/SpringBoard 运行。
- 无 iPad 形态残留（product/artwork/idiom 正确）。

风险：

- 4K 补丁回移到 8796 是本阶段最大风险；需要逐条适配，不是改版本号。
- iPhone10,2 kernelcache 的 prelink 元数据与 iPad 不同；`early_security_init` 要重新定位。
- iOS 16 可能需要 `AppOS` 窗口；先用 `unixnu ipsw info` 确认。
- 如果 4K 路线成本过高，考虑 B6 的 fallback 或另开 A 线，不要硬拼。

---

### B7 显示、触摸、电源、UI（预计 4–8 周）

**目标**：CPU 渲染的手机 UI 可用，触摸/按键工作。

任务：

- [ ] 显示：先用 `NATIVE_LEGACY_DISPLAY` + GOP framebuffer；能出控制台/panic/锁屏。
- [ ] 面板：OnePlus 5 是 Samsung S6E3FA5 DSI；需要 MDSS/DSI PHY 初始化，参考 mainline panel driver。
- [ ] 触摸：Synaptics RMI4 over I2C；需要 QUP I2C 控制器 + RMI4 协议；参考 sheng 的 Novatek 驱动结构。
- [ ] 按键：电源/音量通过 PMIC/GPIO；先做 HID consumer keys。
- [ ] 电源：PM8998/PMI8998；首期不做充电/suspend，保持 UEFI 电源轨，`sleep-disabled`，关 watchdog。
- [ ] UI 性能：CPU 渲染，目标锁屏/桌面可用；不追求 60fps。
- [ ] 记录已知问题：无 WiFi/BT/音频/相机/传感器/GPU。

验收（G6）：

- 锁屏出现，能解锁。
- 桌面出现，能打开 Settings。
- 触摸和 Home/音量键工作。
- 连续运行 10 分钟不 watchdog/panic。

风险：

- 触摸和面板是设备特定工作，可能比 UFS 更耗时。
- 没有 GPU，部分动画/应用会慢。
- 电源/温控缺失，长时间高负载可能不稳定。

---

### B8 文档、上游、收尾（预计 1 周）

任务：

- [ ] 新增 `docs/devices/cheeseburger.md` 和 `docs/zh/devices/cheeseburger.md`。
- [ ] 更新 `docs/devices/index.md`、`docs/zh/devices/index.md`、VitePress 导航。
- [ ] 记录：IPSW 身份、GPT、prelink、ADT、firmware、payload、boot 命令、已知问题。
- [ ] 把设备仓库/ UEFI 仓库的构建命令写进 README。
- [ ] 可选：给 `unixnu build firmware`/`bootimg` 增加 edk2-msm8998 布局支持。
- [ ] 提交前检查：不包含 IPSW/kernelcache/trust cache/Data seed/私有 blob。

验收（G7）：

- 文档能按步骤复现构建和启动。
- 设备页状态真实，不夸大。
- 仓库无私有二进制。

---

## 7. 时间线（按每周 10–15 小时估算）

| 阶段 | 内容 | 预计 | 累计 |
| --- | --- | --- | --- |
| B0 | 准备与基线 | 2–3 天 | 0.5 周 |
| B1 | UEFI + UniXNU | 1–2 周 | 2.5 周 |
| B2 | 设备仓库 + ADT | 1–2 周 | 4.5 周 |
| B3 | 4K 引导链（iPad 临时） | 1–2 周 | 6.5 周 |
| B4 | 平台专家 | 3–5 天 | 7.5 周 |
| B5 | UFS + root | 4–8 周 | 15.5 周 |
| B6 | iPhone10,2 切换 | 3–5 周 | 20.5 周 |
| B7 | 显示/触摸/UI | 4–8 周 | 28.5 周 |
| B8 | 文档/收尾 | 1 周 | 29.5 周 |

**结论**：到 XNU 控制台约 6–8 周；到 iPhone10,2 锁屏约 5 个月；到可用 UI 约 6–7 个月。UFS 和 4K 回移是最大变量。

---

## 8. 风险登记

| 风险 | 概率 | 影响 | 对策 |
| --- | --- | --- | --- |
| UFS 2.1 驱动移植 | 高 | 高 | handoff 模式、先 mockfs、参考 mainline/ios-sweet、先旁路 SMMU |
| 4K 补丁回移 xnu-8796 | 高 | 高 | 逐条 apply/重写；最小补丁集；B6 设决策门 |
| 没有 UART | 高 | 中 | framebuffer 日志、panic screen、boot-progress；UEFI GOP log |
| edk2-msm8998 只映射 4 GB | 中 | 高 | 先用 `dram_size=0xF0000000`、2 GB 窗口；稳定后改 MemoryInitPei |
| GCC5 vs CLANGPDB | 中 | 中 | 先用 GCC5；UniXNU/DarwinBoot 单独 CLANGPDB 出 EFI 再塞 FV |
| prelink ABI/kext 不匹配 | 中 | 高 | B3 用 sheng 已验证基线；B6 重新鉴定；逐个裁剪 roots |
| iPhone10,2 的 `/product`/`/buttons` 不匹配 | 中 | 中 | 从真实 D21AP DeviceTree 复制，不手写 |
| 触摸/面板驱动 | 中 | 中 | 首期 GOP console；UI 阶段再做；参考 mainline |
| bootloader 清盘/变砖 | 低 | 高 | 备份；只 `fastboot boot`；保留 stock boot |
| 私有 blob 入 git | 低 | 中 | `.cache/firmware/` + `.gitignore`；提交前检查 |

---

## 9. 验收与回滚

每个 gate 的通用检查：

- 构建产物哈希写入 `STATUS.md`。
- 串口/屏幕日志保存到 `plans/oneplus5-cheeseburger/logs/`（本地，不提交）。
- 失败时先回到上一个 gate，不要在失败状态上叠加新变量。

回滚：

- 所有启动都用 `fastboot boot`，不改 boot 分区。
- userdata flash 前必须备份；失败时恢复 stock userdata 或重刷 Android。
- UEFI 失败时重启回 stock bootloader，不影响已安装系统。

---

## 10. 进度记录

每次工作结束更新 `STATUS.md`：

- 当前阶段 / gate
- 完成项
- 下一步
- 阻塞
- 新增硬件事实/决策

---

## 11. 下一步（B0）

1. 确认机型（5 / 5T）并备份。
2. dump GPT，记录 userdata LBA 和逻辑块大小。
3. 确认 RAM 容量。
4. 初始化 UniXNU 子模块，构建 `edk2-msm8998` 的 `cheeseburger`。
5. 下载并校验两份 IPSW，提取 kernelcache/DeviceTree/trust cache。
6. 把结果填入本计划第 3 节和 `STATUS.md`。

完成 B0 后进入 B1：UEFI + UniXNU 集成。
