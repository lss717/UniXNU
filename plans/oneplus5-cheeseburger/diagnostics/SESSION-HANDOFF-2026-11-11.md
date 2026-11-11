# 会话交接（2026-11-11，H236ho → H236it）

本页是给下一个会话的**唯一入口**：现状、已证实的结论、已排除项、下一步怎么做（含代码落点）、
以及不踩坑所需的所有操作细节。实验细节仍看 `build-environment-2026-11-10.md`（§45.x）；
流程坑看 `gpu-display-pitfalls-2026-11-11.md`（P1–P16）。

---

## 1. 当前 gate（一句话）

**SpringBoard 卡在一次同步 Mach 调用（`mach_msg2_trap`）上，对端不回复，所以它不建 UI、不连渲染服务器。**
渲染服务器这一侧是好的：backboardd 的 CA 拿到了 `LCD/primary 1080x1920`（+5 个 wireless），
能建队列/纹理/管线，但**只做清屏（18 个 render pass、0 条 draw 指令）**，因此 0 swap、0 帧。

不是 Metal 设备问题，不是 IOMFB 应答问题，不是 display 服务可见性问题。

---

## 2. 已证实（可复现的实测）

| 结论 | 证据位置 |
|---|---|
| 插件被 Metal 接受并驱动 CA：18 render pass、5 blit、23 纹理、0 draw、0 commit、0 iosurface | il 日志（`il-clean.txt`），§45.46 |
| `+[CADisplay displays]` = 6，`list[0] name=LCD device=primary bounds=1080x1920`，`px=0x0`、`hz=60`、`pointScale=0` | `ca#N probe/mode/scale` 行，§45.51/§45.66 |
| SpringBoard 只有**一个**异常线程：`mach_msg2_trap`（lr 在 `mach_msg2_internal`）；其余是 workq 挂起/等锁；10 次采样 pc 完全不动 | `NATIVE_SBPC` + 符号化，§45.77 |
| SpringBoard 从不连接渲染服务器（强制重启后也一样） | 重启前后没有任何 `dev#/cmdbuf` 合成活动，§45.57/§45.82 |
| 所有候选 Mach 服务都在：runningboard、lsd.xpc、lsd.open、containermanagerd(.system)、mobile.usermanagerd.xpc、frontboard.systemappservices、CARenderServer、distributed_notifications | `svc#N lookup … kr=0x0`，§45.81 |
| `0x44c`（NOT_PRIVILEGED）= backboardd 沙箱拒绝，不是缺少服务 | 同上 + `Sandbox: backboardd deny mach-lookup …` |
| `persona.kb` 缺失 → 已按参考实现补入 seed（133 B）→ **行为无变化** | §45.81/§45.82 |
| 本机只有一个 launchd：SpringBoard 与 backboardd 同命名空间 | §45.60 |

## 3. 已排除（不要重复）

1. **默认 surface 链**：`create_default_fb_surface`（`0xfffffff006793694`）在整个镜像里**无人调用**；
   取默认 surface 的入口是 user client 的 **selector 3**，而 CA **从未调用 selector 3**；
   `surface_complete()` 本来就会在首帧后释放它 → 不是第一帧的前提（§45.75）。
2. **MobileGestalt**：C 字符串键 → SIGSEGV；CFString 键 → **把线程挂死**。探针里禁用（P11）。
3. **MG 持久缓存**：四个候选路径全部 `absent`（本机 scratch Data 不落盘）（§45.73）。
4. **`default_fb_surface` 注册表属性**：它只存在于 ivar，不是属性；整字典读 IORegistry 会挂死（P13）。
5. **缺少服务**：见上表，全部 `0x0`。注意 `com.apple.lsd` **不是**服务名（真实名来自
   `com.apple.lsd.plist`：mapdb/modifydb/xpc/open/installation/personaobserver/…），
   曾因此误判一轮。
6. **persona manifest**：补上后行为不变。
7. **会话/命名空间**：只有一个 launchd。

## 4. 下一步（唯一剩下的方向）

**读 SpringBoard 那条同步消息的 `msgh_id`。** 它直接是 MIG/XPC 的例程编号，可指认对端。

落点：`osfmk/kern/task.c: native_sb_pc_sample()`（已有，见
`patches/xnu/zzzzzzzzzzz-h103-proc-state.patch`）。改动很小：

```c
/* 只对 pc 落在 mach_msg2_trap 的线程做：x[0] 是 mach_msg2 头指针，x[1] 是选项 */
if (pc == <mach_msg2_trap 的 runtime 地址>) {     /* 或按 lr 在 mach_msg2_internal 判断 */
    uint64_t header = 0, size = 0;
    if (copyin((user_addr_t)(uintptr_t)state->x[0], &header, sizeof header) == 0) { … }
    /* header 的高 32 位是 msgh_bits，低 32 位是 msgh_size；msgh_id 在 +0x14 */
    copyin((user_addr_t)(uintptr_t)state->x[0] + 0x14, &msgh_id, 4);
}
```

打印 `tid / msgh_id / bits / size`，然后按 `msgh_id` 查 XPC（`0x1xxxxxxx` 段）或 MIG 例程。

风险：**内核构建近期不可复现**（§45.79：同源码两次构建 sha 不同，且 im/in/io 三版都在
`OSMetaClass::addInstance` 崩）。构建失败就换回 `il` 的内核（已知可用）继续用用户态手段。

---

## 5. 可用的镜像与内核（都在 `/tmp/opencode`）

| 镜像 | sha256（前 8） | 内容 | 状态 |
|---|---|---|---|
| `boot-H236il.img` | `fce46cb5` | 内核 `0e432507…`（**带** SpringBoard 采样、**不带** persona/服务探测） | ✅ 稳定可启动 |
| `boot-H236is.img` | `17f69ff7` | il 内核 + 插件（svc/persona 探测，persona 创建被沙箱挡） | ✅ 可启动 |
| `boot-H236it.img` | `0532e3ec` | il 内核 + seed 内 133 B `persona.kb` | ⚠️ 一次偶发停滞@194 s，重跑正常到 355 s |
| `payload-H236il.img` | — | 上述镜像的 payload 基座（内核 = il） | — |

**不要**再用 `im/in/io` 的内核（`OSMetaClass` panic）。

---

## 6. 操作细节（下次直接用）

### 设备（Windows 控制机）
```sh
ls@192.168.10.225           # PowerShell（不是 cmd）
密码                        # /tmp/opencode/askpass-win.sh → 3211
/tmp/opencode/ps225  "<PowerShell 脚本>"     # base64 -EncodedCommand，绕开引号
/tmp/opencode/rscp225 <本地文件> 'ls@192.168.10.225:D:/Users/ls/Documents/OnePlus5_ios/'
adb/fastboot                # C:\Users\ls\AppData\Local\Android\Sdk\platform-tools
```
刷机（**只用 fastboot boot**）：
```sh
./ps225 "Set-Location 'C:\Users\ls\AppData\Local\Android\Sdk\platform-tools'; .\adb.exe reboot bootloader; Start-Sleep -Seconds 14; .\fastboot.exe boot 'D:\Users\ls\Documents\OnePlus5_ios\boot-XXX.img'"
```
拉日志（TWRP 里）：
```sh
./ps225 "… .\adb.exe shell 'blockdev --flushbufs /dev/block/by-name/userdata_ios'; .\adb.exe shell 'dd if=/dev/block/by-name/userdata_ios of=/tmp/h103log.bin bs=4096 skip=12892347 count=8192'; .\adb.exe pull /tmp/h103log.bin 'D:\…\h103log-XXX.bin'"
# 然后 scripts/h103-log-pull.py 的 merge_slots 解析
```

### Mac 构建机
```sh
lss@192.168.10.103:~/UniXNU
python3                        # ~/.local/bin/python3.12（3.9 没有 tomllib）
export PATH=/opt/local/bin:/usr/local/bin:$PATH      # cmake/ninja 在 MacPorts

# 内核（会自行决定 XNU_SKIP_PATCH_LOOP；--clean 强制全量打补丁）
bash scripts/macos-build-kernel.sh [--clean]

# 改过驱动源码后必须先重建对应归档（wrapper 只重建 legacy display）
SDKROOT="$(xcrun --sdk iphoneos --show-sdk-path)" python3 scripts/build-arm-driver.py NativeUfsProbe

# prelink + payload（需要一个 tree.py 的本地补丁：refer/ 下真实目录时 _link 要跳过）
~/.local/bin/python3.12 ./unixnu build prelink payload -D ../UniXNU-cheeseburger
```

### 打包纪律（每次都做）
1. 信任缓存**串加**：`add-owner-trust-hash.py base <plugin-cdhash> tmp && … tmp <cadprobe> out`；
2. payload 里**三件一起换**：`kernel.macho`（要换内核时）、`kernel.macho.gpuaddon`（插件）、
   `scratch-data.img`（seed）、`kernel.macho.trustcache`；
   只改插件时**不要**动 `kernel.macho`；
3. `mdir -i payload.img ::/EFI/UniXNU/Payloads` 自检 + `sha256sum boot.img` 必须与上一轮不同；
4. **打包一次就提交一次**（超级仓库 + 子模块 + 设备仓库）。

### 符号化
- **内核 pc**：`xcrun nm -n -U out/cheeseburger/kernel/kernel.macho` 二分定位
  （`LC_FUNCTION_STARTS` 会误判，见 §45.78）；
- **用户态 pc**：先用**同一轮**日志里的 `NATIVE_TRAP_IMAGE_ROW: base=… <image>` 反推 cache slide
  （不要用插件打印的 `slide=`，那是主可执行文件的），再用
  `scripts/macho-resolve.py ~/dsc-work/ext <runtime_base> <known_vmaddr> <pc…>`；
  已知：`SessionSyncEngine base=0x1dc3e1000`、vmaddr `0x1c18d9000` → slide `0x1ab08000`（il 那轮）。

---

## 7. 关键源码位置

| 文件 | 作用 |
|---|---|
| `drivers/NativeMetal/A540TracePlugin.mm` | Metal 插件：device/queue/cmdbuffer 桩、显示探针、服务探测、SpringBoard 重启、persona 尝试 |
| `drivers/NativeUfsProbe/NativeUfsProbe.cpp` | 内核驱动：心跳、加速器服务注入、采样线程（调用 `native_sb_pc_sample`） |
| `osfmk/kern/task.c`（经 `patches/xnu/zzzzzzzzzzz-h103-proc-state.patch`） | `native_sb_pc_sample()`：按名采样等待线程的 pc/lr |
| `drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp` | Legacy 显示驱动（`/chosen/display-scale`、swap 校验、client interposer） |
| `drivers/NativeMobileDisplay/LegacyDisplayProbe.cpp` | 客户端 selector 追踪（`client io/sel/fixup`） |
| `scripts/add-gpu-plugin-data.py` | 打包 seed（插件 bundle、cadprobe、`--persona`） |
| `scripts/add-owner-trust-hash.py` | 信任缓存注入（**串加**） |
| `scripts/symbolicate-pc.py` | 用户态 pc → 函数（LC_FUNCTION_STARTS） |
| `scripts/macho-resolve.py` | 共享缓存 runtime pc → 镜像 + 偏移 |

---

## 8. 若决定换方向（备选）

- **A. 不再依赖 SpringBoard**：用插件在 backboardd 内建一个 `CAContext`+`CALayer`（带 IOSurface
  contents）并提交，验证“合成器到底能不能画/swap”。若可行，等于绕开 SpringBoard 拿到第一帧。
- **B. 先修内核构建的可复现性**（§45.79）：影响所有内核侧取证，但工作量大。
- **C. 深入 `lsd`/`containermanagerd`**：本机这两个服务都注册正常，除非有新证据，否则不值得再挖。
