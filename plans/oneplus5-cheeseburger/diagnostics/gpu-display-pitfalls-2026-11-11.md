# GPU 前端 / 显示链路的踩坑记录（2026-11-11，H236ho → H236ia）

本文件只记**会让人白跑一轮上机**的坑。每条都写：症状 → 根因 → 正确做法 → 这次浪费了几轮。
实验结论本身仍然记在 `build-environment-2026-11-10.md`（§45.x）与 `STATUS.md`。

---

## P1 信任缓存：只能串加，不能替换

**症状**：`NATIVE_MTL` 日志**零行**，心跳 `accel=1/1/1/2 abi=0/0/0`，屏幕上没有任何变化。

**根因**：`scripts/add-owner-trust-hash.py BASE HASH OUT` 是 **BASE → OUT** 的复制式注入。
拿 `trust-base.bin` 当 BASE、只加新算子（例如 cadprobe）的哈希，就把**上一版插件的 CDHash 覆盖掉了**。
插件是 ad-hoc 签名，CDHash 不在信任缓存里就被 AMFI 拒绝加载。

**正确做法**：每加一个哈希都以上一步的输出为 BASE：

```sh
python3 scripts/add-owner-trust-hash.py /tmp/opencode/trust-base.bin <plugin-cdhash>   /tmp/opencode/trust-1.bin
python3 scripts/add-owner-trust-hash.py /tmp/opencode/trust-1.bin     <cadprobe-cdhash> /tmp/opencode/trust-2.bin
mcopy -o -i payload.img /tmp/opencode/trust-2.bin ::/EFI/UniXNU/Payloads/kernel.macho.trustcache
```

注入后自检（本机即可，不必上机）：

```sh
python3 - <<'PY'
from pathlib import Path
h = Path('/tmp/opencode/trust-2.bin').read_bytes().hex()
for w in ('<plugin-cdhash>', '<cadprobe-cdhash>'):
    print(w[:10], w in h)
PY
```

**代价**：hx、hy 两轮（各约 5 分钟）完全白跑。

---

## P2 真正被加载的插件在 **payload**，不在 Data seed

**症状**：和 P1 一样（零 `NATIVE_MTL`），但信任缓存里明明有哈希。

**根因**：`Payloads/kernel.macho.gpuaddon` 是内核在开机时写入 addons 目录的那份
（日志 `NATIVE_GPU_ADDON: blob … count=3 files=3 written=3 same=0`）。
只更新 `scratch-data.img`（`ngpu/addons`）而不更新 payload 里的 `.gpuaddon`，跑的还是**旧插件**，
于是旧 CDHash 不在新信任缓存里 → AMFI 拒绝。

**正确做法**：**每次改插件，payload 三件套一起换**：

```sh
cp payload-old.img payload-new.img
mcopy -o -i payload-new.img /tmp/opencode/A540TraceX.gpuaddon ::/EFI/UniXNU/Payloads/kernel.macho.gpuaddon
mcopy -o -i payload-new.img /tmp/opencode/seed-traceX.img  ::/EFI/UniXNU/Payloads/scratch-data.img
mcopy -o -i payload-new.img /tmp/opencode/trust-X.bin      ::/EFI/UniXNU/Payloads/kernel.macho.trustcache
mdir -i payload-new.img ::/EFI/UniXNU/Payloads | grep -E "gpuaddon|trustcache|scratch"   # 打包前自检
```

自检同样可以在本机做：`mdir` 能列出三个文件且大小对，再打包。

**代价**：hx、hy、hz 三轮；其中 hz 之后还误打包了一次（见 P3）。

---

## P3 打包前必须确认 payload 真的换了（sha256 是唯一证据）

`mcopy` 失败（源文件不在本机，例如 `.gpuaddon` 只在 Mac 上）时，脚本不会中断，
只是把一个**没改过的 payload** 又打包了一遍。结果 `boot-*.img` 的 sha256 与上一轮**完全相同**，
等于把同一张坏镜像又跑了一遍。

**正确做法**：打包后立刻比对 `sha256sum boot-*.img`；与上一轮相同就说明 payload 没变，停下检查。

---

## P4 怎么区分“插件没加载”和“插件加载了但没日志”

插件里的 `emit()` 在拿不到加速器连接时**静默返回**（这是设计缺陷，见 P8），所以“零日志”有两种含义。
用内核侧的两个计数判断：

| 观察 | 含义 |
|---|---|
| `NATIVE_MTL` 零行 **且** `NATIVE_ACCEL_HB: accel=<opens>/<type>/<sels>/<last>` 里 `opens≤1`、`sels≤1` | 插件**没被 dyld 加载**（P1/P2） |
| `NATIVE_MTL` 有 `slide=` 但后续很少 | 插件加载了，ABI 通道有问题 |
| `accel=<几十>/0/<几百>/<n>` 且 `abi=` 有计数 | 正常 |

另外两条**不能**作为“已加载”的证据：

- `NATIVE_UFS_ACCEL: service=… MetalPluginName=A540Trace … set=1` —— 只证明**属性写上了**；
- `op=match comm=backboardd d=IOAcceleratorES ok=1` —— 只证明 Metal **匹配到了服务**。

---

## P5 LaunchDaemon 的 plist 必须 root 属主；覆盖层还要 sentinel

**症状**：`NATIVE_GPU_ADDON: … daemons=4/2`，日志里**没有**目标程序的 `NATIVE_EXEC`。

**根因**：`/System/Library/LaunchDaemons` 要求 **root:wheel**。staging 以构建用户（uid 501）写文件，
launchd 直接忽略；`status=2`（ENOENT）来自覆盖层里缺少 sentinel
`org.blu-sharky.adrenoprobed.plist`（脚本会清空 `ngpu/daemons` 再重建）。

**正确做法**（本机目前拿不到 root，所以此路暂时不通）：要么以 root 写 plist 并 `chown 0:0`，
要么保留 sentinel 文件，要么改由内核在开机时以 root 写文件。

---

## P6 这个 port **没有 per-user launchd**，`~/Library/LaunchAgents` 不会被扫描

**症状**：把 plist 放到 `mobile/Library/LaunchAgents/`，仍然没有任何 `NATIVE_EXEC`。

**根因**：全日志只有一个 `launchd`（pid=1）；没有 per-user 实例，用户 home 下的 LaunchAgents 不生效。

**推论（很重要）**：SpringBoard 是 pid=1 的子进程，**与 backboardd 同一个 bootstrap 命名空间**。
参考实现（sagit，iOS 18）里“系统会话看不到、用户会话才看得到 render server”的分野在这里**不存在**，
所以在 backboardd 内量到的 `+[CADisplay displays] list=6 / LCD primary` **就是** SpringBoard 会拿到的答案。
—— 不要再往“会话/命名空间”方向查。

---

## P7 Mac 构建环境会随机器状态漂移（内核构建当天不可用）

| 症状 | 处置 |
|---|---|
| `ModuleNotFoundError: tomllib` | 用 `~/.local/bin/python3.12 ./unixnu …`（`#!/usr/bin/env python3` 在非交互 shell 里是 3.9） |
| `cmake not found` / `ninja not found` | Homebrew 已被清空；MacPorts 的在 `/opt/local/bin`，`export PATH=/opt/local/bin:$PATH` |
| `PermissionError: unlink …/tree/refer/libdispatch` | `refer/` 下有几个是**真实目录**（旧 treecopy 残留），`_link()` 只会 unlink 链接 → 组装中断 |
| `patch does not apply: iokit/KernelConfigTables.cpp` | 工作树已是打过补丁的状态 → `XNU_SKIP_PATCH_LOOP=1` |
| `NativeRamBlock requires … prelink closure` | `XNU_OWNER_DATA_MOUNT=1 XNU_OWNER_DATA_VOLATILE=1 XNU_OWNER_DATA_VOLUME_UUID=1A4CE9DF-…` |
| 归档步骤 `nm: bsd_init.o No such file` | 内核对象被删过：先单独跑一遍脚本生成对象，再跑完整流程 |
| 链接 `Undefined _proc_iterate` | C++ 里 `#include <sys/proc_internal.h>` 需要 `extern "C"` 包裹 |
| 链接 `Undefined _native_a540_*` | `libNativeLegacyDisplay.late.a` 没进链接集（bootstrap pass 本来就不带归档） |

**没有 sudo**：`sudo -n true` 需要密码，所以任何“以 root 写文件”的做法都做不了。

---

## P8 插件 `emit()` 静默失败（待修）

`A540TracePlugin.mm` 的 `emit()` 在 `connectAccelerator()` 失败时直接 return，**不留任何痕迹**。
这就是 P1/P2 那几轮“看起来什么也没发生”的原因。

**建议改法**：首次失败时用另一条**不依赖 ABI** 的通道留个记号（例如调用
`-[NSUserDefaults …]` 写一个偏好，或 `os_log`），至少能在系统日志里看到“插件加载了但连不上”。
在这条没做之前，**每次上机前先按 P4 的自检确认插件真的会加载**。

---

## P9 日志窗口只有约 61 个快照，关键行会被冲掉

内核持久日志区是环形的，`h103-log-pull.py` 合并到的历史取决于已写快照数
（本轮 `slots_written=61`）。插件里 `+60s` 才写的那行 `ca#N restart` 正好落在窗口之外，
当时无法判断重启是 `kill` 成功还是被沙箱拒绝。

**做法**：把“必须有结论”的行**重复写**（不同时间点各一次），或把它挂在周期心跳上；
不要只在一个时间点写一次。

---

## P10 两条 iOS SDK 的小坑（编译期）

- `CGRectZero` 是外部符号：bundle 没链接 CoreGraphics 时链接失败。用
  `CGRect rect; memset(&rect, 0, sizeof rect);` 即可（只用到类型，不需要框架）。
- iOS SDK 里**没有** `servers/bootstrap.h` / `libproc.h`；`_XOPEN_SOURCE 700` 下
  `sys/sysctl.h` 的 `u_int` 也会消失。用 `extern "C"` 自己声明
  `bootstrap_look_up` / `proc_listpids` / `proc_name`，bootstrap 端口用
  `task_get_special_port(mach_task_self(), TASK_BOOTSTRAP_PORT, &port)` 取。

---

## 上机前的固定自检清单

1. `trust-*.bin` 里有**本镜像用到的全部** CDHash（插件 + 任何旁路工具）；
2. `payload.img` 里的 `kernel.macho.gpuaddon` 是**本次**构建的产物（`mdir` 看大小、`sha256sum boot-*.img` 与上一轮不同）；
3. `./unixnu` 用 `~/.local/bin/python3.12`；内核构建时 `PATH` 含 `/opt/local/bin`；
4. adb 侧：`adb kill-server && adb start-server`，`adb devices` 能看到 `recovery`；
5. 拉日志前先 `blockdev --flushbufs /dev/block/by-name/userdata_ios`；
6. 装机后第一眼先看 `NATIVE_MTL` 与 `NATIVE_ACCEL_HB`，确认插件真的加载，再谈结论。

---

## P11 MobileGestalt：C 字符串会崩，CFString 会挂

- `MGGetFloat32Answer(CFStringRef key, float def)` 的键是 **CFStringRef**。传 C 字符串 →
  callee 当 CFString 解引用 → `SIGSEGV`（`pc=0x19c33ec14`，backboardd 被崩、launchd 重建）。
- 改成 `CFSTR("MainScreenScale")` 之后不崩了，但 `dlopen`/调用**直接把线程挂住**：
  探针此后再无任何输出，而进程心跳照常。两种失败都不是“返回值不对”，而是“根本回不来”。

**做法**：探针里不要用 MobileGestalt。要 scale 就用 `CADisplay -pointScale`，并且把它排在
任何可能阻塞的调用**之前**，先打印再继续。

## P12 内核构建：镜像配置不在仓库里

`cheeseburger_defconfig` 里 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY` 与
`CONFIG_XNU_NATIVE_MOBILE_DISPLAY` 都是 **not set**，但跑在机器上的镜像显然包含
`NativeLegacyDisplay`。也就是说那批内核是用**仓库外的设置**构建的。

- 打开 `LEGACY_DISPLAY=y` 才能让 `libNativeLegacyDisplay.late.a` 被 `-force_load`
  （`_native_a540_*` 只在这个归档里）；
- `MOBILE_DISPLAY=y` 还要求一个并不存在的 `libNativeMobileDisplay.late.a`；
- 归档步骤需要 `bsd/*.o`，而对象由 XNU 构建产生，上一次失败会把对象清掉 → 循环依赖，
  只能靠 bootstrap pass 打破，而它当前又生成不了 `startup.o.json` 记录。

**做法**：先确认当初那套设置（问人/翻 Mac 的命令历史/以前录下来的 `out/cheeseburger/.config`），
再动内核；不要靠临时 `export` 猜。

## P13 `IORegistryEntryCreateCFProperties` 也会把 backboardd 卡住

想“从用户态读驱动属性”时用了 `IOServiceGetMatchingService` + 整字典
`IORegistryEntryCreateCFProperties`，结果是探针线程同样一去不回（没有 trap、没有日志）。

**做法**：只读需要的单个 key（`IORegistryEntryCreateCFProperty`），并在前后各打一个标记行，
这样卡住时能定位到具体是哪一步；整字典读取在 backboardd 里不要用。
