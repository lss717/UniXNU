# H104k 上游对照：backboardd 与 display provider（2026-11-05）

- 说明：H104 系列停在“backboardd 不打开/不使用 display provider，没有第一帧”。本轮不再改代码，先对照上游仓库与上游设备记录，判断这个 gate 的性质，以及哪些上游内容值得进入本仓库。
- 目的：确认（1）上游是否有“让 backboardd 取 display provider”的修法；（2）我们当前 H104 结论里哪些成立、哪些需要修正；（3）哪些上游提交/补丁可以直接合并。
- 边界：只读对照上游（克隆到 `/tmp/opencode`），不改内核、不改设备仓库、不上机；本仓库只新增一个已核对可应用的 XNU 补丁及文档。
- 上游基线：`UniXNU/UniXNU` `main` `13e5973`（2026-11-05）、`UniXNU/GopFramebuffer` `main` `e47c1b8`；本仓库 `main` `1143c98`（H104j），与上游 merge-base 为 `e95b37d`（2026-10-22），落后 561 个提交、领先 431 个提交。
- 参考设备记录：`docs/devices/alioth.md`、`docs/devices/sirius-huajifruit.md`、`docs/devices/sm-t970.md`（均在 `13e5973`）。

## 1. 结论

1. **上游没有“让 backboardd 拿到 display provider”的补丁。** 上游设备记录把同一症状直接归因到 renderer：先让 backboardd 起来、再给它一个可打开的 accelerator，否则 compositor 不会走到 open/swap。
2. **两个与本板同构的上游记录逐字对应我们的现象**：`CLIENT calls=4 class=IOMobileFramebufferUserClient`、`SWAP calls=0`、`SB waits for BackBoard screen info`。
3. **我们的 A540 stub 结构上不可能被 open**：`NativeA540AcceleratorProbe` 只是 `IOService` + `IOClass=IOAcceleratorES` 属性，`newUserClient` 仍是 `IOService` 默认实现。上游是一个真的 `IOAcceleratorES` 子类，只额外重写 `newUserClient`。
4. **本仓库的 accelerator ABI 记录已过期**：`scripts/data/ioaccelerator-base-abi.json` 的 `candidate_sha256` 是 `12d7513a…`（H103fp kernel），而 H104j kernel 是 `7e85bc44…`。上游同一套“绝对地址 + late archive”做法要求审计地址与当次 prelink 严格一致，脚本在 hash 不符时拒绝继续；这可以解释 H103fp/fq/fr 连续三次 `OSMetaClass::addInstance` abort。
5. **上游也没有解决“无 GPU 时出可见 UI”**：最接近我们的 sirius（同 21H461 / iPadOS 17.7.11 / Legacy GOP / 无 GPU）已经做到 display 启动、backboardd 打开 client、power state 1、SWAP 全 accepted 且全 CPU copy，画面仍然是黑的，GPU 一栏仍为 `planned`。

## 2. 证据

### 2.1 alioth（Redmi K40）：同症状与解锁路径

| 位置 | 内容 |
| --- | --- |
| `docs/devices/alioth.md:342` | `DISPLAY stage=10 with CLIENT calls=4 class=IOMobileFramebufferUserClient, and SWAP calls=0: a client connects but no frame is submitted.` |
| `docs/devices/alioth.md:338` | Next action：*"Get backboardd to start before investigating frame submission: with no render server there is no client that could call Swap."* |
| `docs/devices/alioth.md:437` | accelerator 绑定三个原始 import（构造函数 alias `0xfffffff004bd3b20`、析构 `0xfffffff004bd3b64`、metaclass `0xfffffff006aeb688`），`__mod_init_func` 剥离、initializer globalize，在 IOGPUFamily 之后执行 |
| `docs/devices/alioth.md:438` | *"the same image with the accelerator but without the plugin bundle … shows no crash at all, which is the software-rendering fallback the plan predicts."* |
| `docs/devices/alioth.md:457` | backboardd 打开 `type 1`（IOAcceleratorES client）、`0x4147`、`0x4148`；sandbox 拒绝 `0xe00002e2`，grant 仍放行 |
| `docs/devices/alioth.md:321` | 解锁后 `SWAP calls=7 ok=7 rej=0`，锁屏稳定 |

### 2.2 sirius（Mi 8 SE）：同 OS profile、Legacy、无 GPU

| 位置 | 内容 |
| --- | --- |
| `docs/devices/sirius-huajifruit.md:423` | Legacy 显示 51.1 s 注册；189.2 s `IOMobileFramebufferUserClient` type 0 打开；221.5 s power 1；`default_fb_surface: No Default FB Surface found` |
| `docs/devices/sirius-huajifruit.md:414` | *"Frames reach the GOP buffer but are black … with no GPU offers, so nothing renders content into the surfaces backboardd presents."* |
| `docs/devices/sirius-huajifruit.md:427` | SWAP `14954/14954` 全部 accepted，全部 CPU 全帧拷贝 |
| `docs/devices/sirius-huajifruit.md:419` | 未解问题：backboardd 是否能软件回退、`default_fb_surface` miss 是否有影响 |

### 2.3 sm-t970：同类等待链

- `docs/devices/sm-t970.md:940`：`SB still waits for BackBoard screen info, swap0`。
- `docs/devices/sm-t970.md:1044`：`BackBoard sampled in grayscale mutex wait and SwapEnd`。

## 3. 与 H104 既有结论的对照

| H104 结论 | 对照结果 |
| --- | --- |
| “backboardd 没有取 display provider，所以没有第一帧” | **口径需修正**：更准确的说法是“没有 renderer（accelerator/Metal），compositor 走不到 open/swap”；alioth 的 CLIENT=4/SWAP=0 就是该形态 |
| A540 绝对基类绑定不可行（H103fr） | **不是普适结论**：上游用同一技术并成功；失败点是 ABI 记录与当次 candidate 不匹配，以及 `.globl` 绝对符号进入 prelink 绑定表 |
| property-only `IOClass=IOAcceleratorES` stub | **结构上不可能被 open**：缺的不是属性，是 `newUserClient` |
| 左上白 = display 链路 OK | **成立**，但与出 UI 无因果关系；sirius 可到 swap 全通仍黑屏 |
| H104f slot gate 修复 launchd race | **成立且必要**，对应 alioth 的“get backboardd to start”前置条件 |

## 4. 上游 diff 中的可采纳项

`e95b37d..13e5973` 内 `patches/xnu` 的净变化：

```text
M	patches/xnu/native-4k-signature-hash-cache.patch
A	patches/xnu/native-lookup-trace.patch
A	patches/xnu/native-union-lower-directory.patch
A	patches/xnu/native-work-interval-instance.patch
M	patches/xnu/offline-component-load-probes.patch
M	patches/xnu/offline-owner-systemos-mount.patch
M	patches/xnu/native-adreno-sandbox-grant.patch
A	patches/xnu/native-sandbox-grant-set-properties.patch
M	patches/xnu/native-gpu-addon-mount.patch
A	patches/xnu/zzyb-native-cryptex-os-view.patch
A	patches/xnu/zzyc-owner-skip-launch-constraints.patch
```

本轮只采纳 `native-sandbox-grant-set-properties.patch`：

- 它把 `NativeSandboxGrantProcess` 的授权从“打开 user client”扩展到 `setProperties`。
- 触发场景是 backboardd 的配置拒绝 `FadePeriod`（CoreBrightness 每次调亮度都会发），属于后续背光/显示链路必经点。
- 与我们的 `zzw`（单进程 + `NATIVE_DISPLAY_OPEN` 观测）互补，不改动 H104 已观测的 open 行为。

未采纳及原因：

| 补丁 | 原因 |
| --- | --- |
| `native-work-interval-instance`（已停用的历史补丁） | 只影响音频 workgroup interval 的 6/7/8 操作，与当前 gate 无关 |
| `native-union-lower-directory`（已停用的历史补丁） | 与 `log-root-union.patch` 的本地 root union 实现重叠，需单独适配 |
| `native-lookup-trace`（已停用的历史补丁） | 纯观测，且与本轮 gate 无关 |
| `zzyb-native-cryptex-os-view`（已停用的历史补丁） | Safari/WebKit 扩展，当前用不到 |
| `zzyc-owner-skip-launch-constraints`（已停用的历史补丁） | 新增 `sheng-no-lc` boot arg；当前 gate 不涉及 launch constraint，先不引入 |
| GopFramebuffer `c031d88..e47c1b8`（13 个提交） | direct scanout / GPU fence / half-float / event ring，属 GPU/DPU 路径；CPU 路径修复（`72cebda`、`eb9c949`、`c031d88`）我们基座已含 |

## 5. 应用性验证

`zzwb` 的 hunk 与我们现有的 `zzw` 及 `log-iokit-trace` 不冲突。用 xnu `xnu-10063.141.1`（`d8b8029`）的原始 `iokit/Kernel/IOUserClient.cpp` 逐补丁验证：

```text
OK   offline-component-load-probes.patch
OK   native-adreno-sandbox-grant.patch
OK   native-sandbox-grant-set-properties.patch
OK   log-iokit-trace.patch
```

`zzwb` 在 `zzw` 之后应用时会带 `offset -12`（`zzw` 在自己的 hunk 之后增加了行），`git apply` 能按上下文定位，构建脚本 `scripts/build-xnu-4k-baseline.sh` 的幂等循环（`--reverse --check` 后跳过）同样成立。

## 6. 后续（不改代码的判读顺序）

1. 先上机 H104j，确认 `NATIVE_PROC_DUMP` 能输出 backboardd / IOMFB_FDR_Loader 的 `state` / `wait_event` / `continuation`。
2. 用现有 `NATIVE_IOKIT_MATCH` 与 `NATIVE_DISPLAY_OPEN` 判断 backboardd 是“没找 accelerator”还是“找到了但开不了”；两者对应完全不同的下一步。
3. 只有第 2 步显示 CA 主动尝试 open 时，才进入“真 `IOAcceleratorES` 子类 + 最小 user client”方案；进入前必须用 `scripts/audit-target-accelerator-base-current.py` 重新生成与当前 candidate 一致的 ABI JSON，替换过期的 `scripts/data/ioaccelerator-base-abi.json`。

## 7. 风险

- 无 GPU 的天花板：sirius 的实测表明 display + client + swap 全通仍可能黑屏，上游把这列为未解问题。
- 新增 `zzwb` 会改变内核文本布局，下一次 kernel/prelink/boot 的哈希必须重新记录，不能沿用 H104f/H104j 的哈希。
- 绝对 ABI 的时序窗口：任何 archive 变化都可能让地址漂移；上游用 recorded JSON + `candidate_sha256` / `original_iogpu_text_sha256` 双校验卡住，我们不能例外。
