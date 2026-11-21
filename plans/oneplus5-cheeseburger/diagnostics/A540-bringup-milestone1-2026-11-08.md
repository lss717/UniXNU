# A540（a5xx）GPU 路线阶段文档 —— 里程碑 1

日期：2026-11-08
设备：OnePlus 5（cheeseburger / MSM8998 / Adreno 540）
OS 目标：iPad7,1 / iPadOS 17.7.11 / 21H461

## 1. 目标

为 CoreAnimation/backboardd 提供一个**真正的 Metal 设备**：

```
CA → IOAcceleratorES 服务 → MetalPluginName → /System/Library/Extensions/<name>.bundle
   → NSPrincipalClass(_MTLDevice 子类) → initWithAcceleratorPort:
   → 插件（metal2vulkan + Turnip）→ IOKit user client → 内核 GPU 驱动
```

本阶段（里程碑 1）只要求：**用户态能成功 `IOServiceOpen` 内核提供的 AGX/Adreno user client，
并让 ABI 隧道（Query/GetDeviceInfo/SetMetadata）跑通**，不做真正渲染。

## 2. 背景：仓库里的 GPU 驱动是 A740 的

`drivers/NativeAdreno` + `kits/AdrenoFirmware` + `kits/AdrenoPM4` + `kits/ArmSmmu4K`
是上游 “sheng” 的 **Adreno 740（a6xx）** 原生 XNU 实现：

- 寄存器/包格式/固件接口按固定版本从 Linux msm（`ianchb/sm8550-mainline` @ `42f3b40c`）
  逐条核对（代码注释明确写 “taken from the pinned Linux source, not guessed”）；
- 固件：`a740_sqe.fw`、`gmu_gen70200.bin`、`a740_zap.mbn`；
- 驱动/kit 中 `a6xx`/`A740` 引用 38 个文件，`a5xx`/`A540` 引用 **0** 个。

因此本机不能简单打开 `XNU_NATIVE_ADRENO=1`，需要按 a5xx 重做；里程碑 1 先用一个
**最小、独立的 accelerator 服务 + ABI 子集**验证整条链路。

## 3. 本阶段完成的工作

### 3.1 用户态投送链路（已完整打通并验证）

| 环节 | 结果 |
| --- | --- |
| GPU addon（`NGPUADD2`）安装到 Data volume | ✔ `addon=8/8/0/0/0/1` |
| `/System/Library/Extensions` union mount | ✔ `ext=4/2` |
| `/System/Library/LaunchDaemons` union mount | ✔ `dm=5/0`（本阶段新打通） |
| 4 KiB 页 ad-hoc 签名 + owner trust cache | ✔（plugin/daemon/Turnip 三个 CDHash） |
| CA 加载 `NativeAdreno.bundle` 并调用 `initWithAcceleratorPort:` | ✔（H188/H189 用退出码证明） |

### 3.2 真实 Adreno 插件构建

在 Intel Mac（macOS 15.8.2）上从零补齐工具链并构建：

- Python 3.12 / meson / ninja / cmake、bison 3.8.2、glslang、shaderc（glslc/spirv-val）；
- Mesa 稀疏克隆（pin `85fda3b3640`）+ 8 个记录补丁 → Turnip（ios + host）；
- Rust 1.98.0 + `aarch64-apple-ios`，metal2vulkan（pin `720ef1ce`）+ 5 个补丁 → bridge；
- `build-adreno-metal-plugin.py` 产物：plugin/daemon/Turnip 4 KiB 签名。

已知工具链限制：`gen-turnip-replay.py` 需要 arm64 主机（把 AArch64 内核源码编到主机运行），
Intel Mac 上改为降级构建（`TurnipReplay.h` 本来就是可选的）。

### 3.3 内核侧里程碑 1（`NativeA540AcceleratorProbe.cpp`）

- 服务：`AGXAccelerator : IOAcceleratorES`，`MetalPluginName` 由 UFS 驱动按 boot-arg 注入；
- user client 类名改为 **`AGXDeviceUserClient`**（原版沙箱只放行这个类名）；
- `externalMethod()` 支持隧道头 `'NTNL'`（0x4e544e4c）：
  - `kProbe`（selector 探测）一律返回成功；
  - `Query` → `abi_version=1`、VA 32 位、PA 40 位、单 BO ≤ 256 MiB；
  - `GetDeviceInfo` → `chip_id=0x05040000`（A540 占位）、VA 窗口 `0x10000000+0x10000000`；
  - `GetStatus` / `GetTimestamp` / `SetMetadata`（`SetMetadata` 文本直接进内核日志）；
  - `BoAlloc` 及之后返回 `kIOReturnUnsupported`；
- 沙箱授权：服务设置 `NativeSandboxGrantProcess=backboardd`（配合仓库已有的
  `native-adreno-sandbox-grant.patch`），UFS 注入点也设置同一属性。

### 3.4 关键调试经验（可复用）

1. **用户态 stderr 不可见**：launchd 作业 stderr 到 `/dev/null`；`/dev/console` 写入也不进
   msgbuf。可靠通道是：内核 `IOLog`、退出码（`_exit(42/43)`）、`SetMetadata`。
2. **日志窗口会混入旧启动的槽**：判断“有没有某行”必须按 boot id 过滤 slot，并注意
   `msg` 区可能整段是上一次启动的内容。
3. `_MTLDevice` 的 `-init` 不是 NSObject 初始化；插件自建实例不要调用 `[super init]`。
4. `[self release]` 会调用 `_MTLDevice` 的 `-dealloc`，未初始化的实例会崩；返回 nil 时不要释放。
5. display 归档（legacy display）重建在 H173 曾导致 PAC panic；本阶段多次重建均正常，
   但仍保留旧镜像作为回退。

## 4. 当前状态与阻塞

最新验证（H198）：

```text
NATIVE_DISPLAY_OPEN: service=AGXAccelerator process=backboardd grant=backboardd match=1   （多次）
NATIVE_A540_ACCEL: open request type=16711 comm=backboardd → user client granted
IOUC AGXDeviceUserClient failed MACF … backboardd                                        （部分打开）
NATIVE_A540_ABI: method= : 0                                                              （隧道未被调用）
```

规律：**部分 accelerator 实例带 `NativeSandboxGrantProcess`（open 成功），部分不带
（MACF 拒绝）**，所以主连接时好时坏。需要保证所有实例都带该属性。

另外：探针 daemon `adrenoprobed` 从未 exec（0 次），launchd 似乎仍执行了原版
`com.apple.iomfb_fdr_loader` 而不是 overlay 中的替换 plist，需单独排查。

## 5. 下一步（H199）

1. `AGXAccelerator::init()` 也设置 `NativeSandboxGrantProcess`；`newUserClient` 打印
   实例指针与属性值，定位缺属性的实例来源；
2. 排查 daemon 未启动（launchd 对 overlay plist 的枚举/缓存问题）；
3. 打通后确认 `NATIVE_A540_ABI: method=…` 与 `report …`，里程碑 1 完成；
4. 里程碑 2：a5xx 的 SMMU/BO/VM（`kits/ArmSmmu4K` + 4 KiB 页表），BO 分配/映射；
5. 里程碑 3：a5xx GMU/HFI 冷启动（固件、电源投票）；
6. 里程碑 4：CP 环 + 第一条 IB + fence；
7. 里程碑 5：最小 PM4 绘制 + scanout。

## 6. 产物与镜像索引

| 版本 | 用途 | boot sha256 |
| --- | --- | --- |
| H191 | 真实 Adreno 插件首次投放 | `9f08a70a…` |
| H192 | ABI 子集应答（display 归档重建） | `e05516fd…` |
| H193 | 跳过 `[super init]` | `b340d85a…` |
| H194 | 测试内联运行 | `7a6a40d4…` |
| H195 | user client 改名 `AGXDeviceUserClient` | `d0605972…` |
| H196 | 请求者/ABI 入口日志 | `12d4de02…` |
| H197 | `NativeSandboxGrantProcess` 授权 | `6a190864…` |
| H198 | UFS 注入点也设置授权 | `431c306d…` |

完整哈希、参数与每次判读见 `plans/oneplus5-cheeseburger/STATUS.md` 的 H190–H198 节。

## 7. 相关文件

- 内核侧：`drivers/NativeMobileDisplay/NativeA540AcceleratorProbe.cpp`
- 用户态：`drivers/NativeMetal/NativeAdrenoMetalPlugin.mm`、`NativeAdrenoUserTest.h`
- 构建：`scripts/build-adreno-metal-plugin.py`、`scripts/build-turnip-darwin.py`、
  `scripts/pack-adreno-addon.py`、`scripts/add-owner-trust-hash.py`
- 沙箱授权：`patches/xnu/native-adreno-sandbox-grant.patch`
- 诊断：`scripts/h103-log-pull.py`（按 boot id 过滤 slot）
