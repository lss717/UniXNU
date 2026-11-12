# H240 / H241 lsd IPC 审计（2026-11-11）

调查对象：`/usr/libexec/lsd`（Launch Services）在启动后长时间等待，以及 backboardd 对
`com.apple.lsd.modifydb`、`com.apple.iconservices`、`com.apple.iconservices.store` 的 Mach lookup 被拒。

本轮只做静态源码/镜像审计、日志关联和符号解析；未改源码、未改 policy、未刷写新镜像。
镜像基线：

| 镜像 | boot sha256（前 8） | 内核 sha256（前 8） | 用途 |
|---|---|---|---|
| H240 | `234ee539` | `513a0b29` | SpringBoard 端口快照（port set 守卫后） |
| H241 | `9053d015` | `9897c1c5` | 增加 lsd 每轮采样 |

标记：**[已证实]** 有本轮可直接复现的证据；**[推断]** 由证据支持但未直接验证；**[待确认]** 无证据。

---

## 0. 结论摘要

1. **[已证实]** SpringBoard 的 `mach_msg2` 是**纯接收**（`bits=0`、`ssz=0`、16 KB、无超时），
   接收端口是它自己的回复端口（`SEND|RECEIVE`、`sr=1`），而缓冲区里残留的消息头远端端口属于 **lsd**。
2. **[已证实]** lsd 本身健康：6 条线程全部是正常空闲/接收，**没有死锁**；但它同样停在一次纯接收上，
   其缓冲区残留头远端端口属于 **containermanager(62)** —— 这是一条**嵌套的同步 XPC 链**。
3. **[已证实]** `Protobox` 不是我 fork 新加的：原版 iPad kernelcache 里就有 `(apply-protobox)`、
   `protobox collection`、`sandbox.protobox.index`，`osfmk/kern/zalloc.h` 在 xnu-work 里 `git diff` 为空。
   因此三条 deny 的**策略来源是 Apple 原生 profile**，而不是我们改过的规则。

---

## 1. 时间线

| 时间 | 事件 | 证据 |
|---|---|---|
| 139.6 s（H240）/ 144.3 s（H241） | `lsd` 由 launchd 启动，pid=92 | `NATIVE_EXEC: comm=lsd argv0=/usr/libexec/lsd` |
| 140.1 s | lsd 容器路径解析成功 | `ustate: caching container path {'com.apple.lsd' : '/private/var/containers/Data/System/D1606350-…'}` |
| 161.4 s | lsd `threads=4 run=1` | `NATIVE_WAIT: pid=92 comm=lsd …` |
| 201.8 s | 采样器第一次看到 lsd（n=2） | `NATIVE_SBPC: sample=0 comm=lsd n=2` |
| 201.8 s | lsd tid 642 位于 `InstalledContentLibrary -[MIDaemonConfiguration …]` | `pc=0x1bdf1c104 lr=0x1bdf1c0e4` → 符号化见 §3 |
| 218.8 s | lsd n=6，tid 642 进入 `mach_msg2` | `NATIVE_SBPC: sample=1 comm=lsd n=6` |
| 282–333 s | SpringBoard / lsd 的 `SBPORT` 三行稳定不变 | §4 |
| 301.4 s | `systemgroup.com.apple.lsd` 容器解析成功 | `ustate: caching container path {'systemgroup.com.apple.lsd' : …}` |

---

## 2. P0：`fffffff007bbd909` 符号化

**[已证实]** 该地址不属于任何函数：它落在 **`__MergedGlobals`**（内核数据段）内部，偏移 `+0x49`：

```
0xfffffff007bbd8c0 _object_bypasses / __MergedGlobals   ← 区间起点
0xfffffff007bbdcf0 _last                                ← 区间终点
0xfffffff007bbd909 → __MergedGlobals + 0x49
```

对照符号：

```
_ipc_mqueue_full     = 0xfffffff007b00320   (D/S)
_ipc_mqueue_receive  = 0xfffffff0072862a4
```

**[已证实]** 它既不是 `_ipc_mqueue_full`，也不是 `_ipc_mqueue_receive_continue`（后者
`0xfffffff0072861f0`，正是同一轮里 SpringBoard tid 290 的 `continuation` 值，说明快照的
`continuation` 字段读取是正确的）。

**[已证实]** 产生该值的字段是 `th->wait_event`，类型 `event64_t`（`osfmk/kern/thread.h:392`
`event64_t wait_event; /* wait queue event */`）——所以它是一个**事件值**，不是返回地址，也不是指令地址。

**[待确认]** 该事件值低 3 位为 `001`，不是对齐指针，因此**不能**仅凭符号表把它命名为某个具体 waitq/event；
需要额外打印 `th->waitq`、`th->wq_state` 或改用 `waitq` 相关符号才能定性。本轮不猜测。

---

## 3. P1：lsd 的四/六条线程（H241 实测）

采样样本（sample=11，333.6 s），用的 cache slide 由同轮
`NATIVE_TRAP_IMAGE_ROW base=0x1c73f5000 / SessionSyncEngine vmaddr=0x1c18d9000` 推出：

| tid | pc | lr | 状态结论 |
|---|---|---|---|
| 480 | `_kevent_id +0x8` | `__dispatch_kq_poll +0xe4` | libdispatch 事件循环在 kqueue 上等待（**[已证实]** 空闲） |
| 638 | `___ulock_wait +0x8` | `__dlock_wait +0x34` | dispatch 锁等待（**[已证实]** 空闲） |
| 641 | `___ulock_wait +0x8` | `__dlock_wait +0x34` | 同上 |
| 642 | `_mach_msg2_trap +0x8` | `_mach_msg2_internal +0x4c` | XPC 接收等待（**[已证实]**） |
| 1008 | `___workq_kernreturn +0x8` | `__pthread_wqthread +0x168` | 空闲 workqueue worker（**[已证实]**） |

补充（**[已证实]**）：

- 201.8 s 时 lsd 只有 2 条等待线程，其中 tid 642 在
  `InstalledContentLibrary` 的 `-[MIDaemonConfiguration …]` 内（`pc=…+0x1f104`，`lr=…+0x1f0e4`）；
  218.8 s 起才转入 `mach_msg2`。**lsd 不是启动即卡死**，它先做了实际初始化工作。
- 全部线程均为"等待/空闲"，没有互斥锁互相持有的迹象；`__dlock_wait` 与
  `__dispatch_kq_poll` 是 libdispatch 的正常空转形态。**[已证实]** 无死锁证据。
- **[待确认]** 线程调用栈：当前快照只取 pc/lr，没有用户栈；要回答"哪一行代码发起这次接收"需要
  额外用 `vm_map_read_user()` 读栈（下一轮可加）。

> 注意：H240 里 lsd 主线程是 tid=472，H241 里是 tid=480 —— 跨轮次 tid 会变，不能直接套用旧值。

---

## 4. P2：SpringBoard → lsd 的同步请求链

**SpringBoard 侧（H240 sample 7–11 / H241 sample 11，数值稳定）[已证实]**

```
comm=SpringBoard buf=0x16f604120 hdr=1 bits=0x0 size=0 rport=0x5803 lport=0 vport=0 id=0
rcv name=0x2103 set=0 ie=0x3030001 sr=1 ms=1 peer=120/SpringBoard
req name=0x5803 set=0 ie=0x3610001 sr=2 ms=0 peer=92/lsd
```

- 接收端口 `0x2103` 的**持有者是 SpringBoard 自己**（`ie=0x3030001` 含 `MACH_PORT_TYPE_SEND|RECEIVE`，
  `sr=1` 表示有 1 个发送权在别人手里）→ 这是典型的"同步调用带出去的回复端口"。
- 缓冲区里残留头的远端端口 `0x5803` 的接收者是 **lsd（pid 92）**，端口仍然存活（`sr=2`）。
- **[已证实]** 不是端口集（`set=0`），因此不是"运行循环在端口集上空等"。

**lsd 侧（H241 sample 11）[已证实]**

```
comm=lsd buf=0x16f385ae0 hdr=1 bits=0x0 size=0 rport=0x5e0b lport=0 vport=0 id=0
rcv name=0x221f set=0 ie=0x1f030001 sr=1 ms=1 peer=92/lsd
req name=0x5e0b set=0 ie=0xbe10001 sr=1 ms=0 peer=62/containermanager
```

**链条**

```
SpringBoard ──(port 0x5803)──▶ lsd(92) ──(port 0x5e0b)──▶ containermanager(62) ──▶ …
```

**[推断]** 每一层都是 libxpc 的同步调用：先发出请求（把回复端口作为发送权带过去），
然后在**自己的回复端口**上做纯接收。三层的 `opt` 完全相同（`0x40700420e`：`MACH_RCV_MSG` +
`MACH_RCV_LARGE` + 16 KB 缓冲 + 无超时），符合同一段 libxpc 代码。

**逐项回答审计要求**

| 问题 | 结论 |
|---|---|
| 请求的 Mach Service 名称 | **[待确认]** 只能确定目的**端口**属于 lsd；具体服务名（`lsd.mapdb`/`lsd.open`/…）无法从残留头得到 |
| 对应的 XPC 接口/消息类型 | **[待确认]** 残留头 `bits=0/ssz=0/id=0`，`msgh_id` 已被覆盖为 0，取不到 |
| lookup 是否成功 | **[已证实]** 本轮日志里 lsd 侧对 `com.apple.lsd.xpc`/`lsd.open` 的 lookup 返回 `kr=0x0`（H240:184.1 s、184.6 s）；SpringBoard 侧**没有**任何 lsd 相关的 sandbox deny |
| 请求是否真正送达 lsd | **[待确认]** 端口仍在 lsd 的 IPC 空间里（`peer=92/lsd`），但"缓冲区里有残留头"只能证明**曾经准备/发送过**该目的端口，不能证明投递与出队 |
| lsd 是否进入请求处理 | **[待确认]**（需要 lsd 侧的用户栈或 XPC 回调断点） |
| lsd 是否发送 reply | **[待确认]** |
| 最后可证实的阶段 | **[已证实]** SpringBoard 停在纯接收、lsd 停在向 containermanager 的纯接收、containermanager 尚未采样 |

---

## 5. P3：三条 Sandbox deny

### 5.1 服务注册者 **[已证实]**

从本机 IPSW（`044-76040-038.dmg`，21H461）的 LaunchDaemons 里直接读取：

| 服务 | 注册者 | 证据 |
|---|---|---|
| `com.apple.lsd.modifydb` | `/usr/libexec/lsd` | `com.apple.lsd.plist` 的 `MachServices`（共 13 个：icons/rebuild/diagnostics/plugin/extensions/xpc/openurl/**modifydb**/mapdb/personaobserver/installation/advertisingidentifiers/open） |
| `com.apple.iconservices` | `iconservicesagent` | `com.apple.iconservices.iconservicesagent.plist` 的 `MachServices` 只有这一项 |
| `com.apple.iconservices.store` | **无 plist 注册** | 在 `System/Library/LaunchDaemons`、`LaunchAgents` 中 grep 无结果 → **[待确认]** 运行时 `bootstrap_check_in` 或由 lsd 内部创建 |

### 5.2 策略来源：`Protobox` 是 Apple 原生机制 **[已证实]**

```
$ git -C out/cheeseburger/tree/.cache/xnu-work diff --stat -- osfmk/kern/zalloc.h
（空）
$ strings -a out/ipsw/21H461/kernelcache.decompressed | grep -i protobox
(apply-protobox)
Protobox
protobox
sandbox.protobox.index
protobox collection
"failed to initialize protobox collection: %d" @%s:%d
```

- `zalloc.h` 里有 `ZC_RO_ID_PROTOBOX` / `ZONE_ID_PROTOBOX`，且**没有本地改动**；
- 原版 kernelcache 里就带全部 `protobox` 字符串；
- 日志里的 `(apply-protobox)` 紧贴在 `NATIVE_EXEC:` 之前、同一行内，是 sandbox kext 在 exec
  时打印的（无换行），不是我们驱动打印的。

**[推断]** 因此 backboardd / lsd 上的 "Sandbox:" 与 "Protobox:" 两种前缀，是 Apple 在同一台设备上
对不同 profile 的日志前缀；这三条 deny **不是**本 fork 新增的 allow/deny 规则差异。

### 5.3 deny 统计（H241，整轮）

```
37 × Sandbox: backboardd(56) deny
35 × Sandbox: mediaserverd(29) deny
 6 × Protobox: lsd(92) deny(1) syscall-mig …（63 / 139）
```

- **backboardd** 被拒的主要是 `mach-lookup`：`com.apple.iconservices`、`com.apple.iconservices.store`、
  `com.apple.lsd.modifydb`、`com.apple.mobile.keybagd`、`com.apple.springboard.services`、
  `com.apple.UIKit.keyboard-management-service`。
  **[推断]** 其中 `iconservices*` 与图标渲染直接相关（backboardd 的合成器要画图标），属于
  "可能有正当需求但未被 profile 允许"；`lsd.modifydb` 是写 Launch Services 数据库，backboardd 不应需要。
- **mediaserverd** 被拒的关键一条：`iokit-open-user-client AGXDeviceUserClient`（MACF 拒绝），
  与 GPU 侧直接相关，记入下一轮参考，不在本审计范围内展开。
- **[待确认]** `Protobox: lsd(92) deny(1) syscall-mig 63 / 139` 的具体含义：XNU 的 mach trap 表里
  `/* 63 */` 是 `kern_invalid`，而 139 超出 `mach_trap_table` 范围，说明这两个数字**不是**直接用
  mach trap 编号，可能来自 sandbox 内部的 MIG 分类表；要做结论必须静态分析 sandbox kext 的映射表。
- **[待确认]** 这三条 deny 在**同版本真机**上是否同样出现。本轮只能证明策略来自原版镜像，
  不能证明"原版行为一致"，因为 entitlements/容器状态可能不同。

**约束遵守**：本轮没有添加任何 `mach-lookup` 通配 allow，也没有修改任何 `.sb`/plist。

---

## 6. P4：lsd 的初始化依赖

| 依赖 | 证据 | 结论 |
|---|---|---|
| 容器路径（Data/System） | `ustate: caching container path {'com.apple.lsd' : '/private/var/containers/Data/System/D1606350-…'}`（H240:140.1 s） | **[已证实]** 解析成功 |
| 系统组容器 | `{'systemgroup.com.apple.lsd' : '/private/var/containers/Shared/SystemGroup/55659046-…'}`（H241:301.4 s） | **[已证实]** 解析成功（较晚） |
| AppleMobileFileIntegrity | `NATIVE_IOKIT: op=open comm=lsd cls=AppleMobileFileIntegrity ok=0`（H241:189.3 s） | **[待确认]** 我们的 IOKit trace 里 `ok=0` 表示"未匹配到该服务"，不等于打开失败 |
| 自身 MachServices | `lsd.xpc` / `lsd.open` lookup `kr=0x0` | **[已证实]** 服务名可用 |
| Launch Services 数据库文件 | 日志不覆盖 os_log 层，ring 里没有 lsd 的文件错误 | **[待确认]** |
| dyld / framework 加载 | 同上 | **[待确认]** |
| 实际工作痕迹 | 201.8 s 在 `InstalledContentLibrary -[MIDaemonConfiguration …]` | **[已证实]** 初始化确实在推进 |

---

## 7. 仍然未知

1. **链条终点**：`containermanager(62)` 在等谁？（这是当前最可能的根因方向）
2. 每层请求的 XPC 接口名 / `msgh_id`（残留头已被清零）。
3. SpringBoard 在 UI 之前为什么先走这条链（触发点）。
4. `syscall-mig 63/139` 的确切语义（需要 sandbox kext 的映射表）。
5. 任何线程的用户态调用栈（本轮没有采集）。

---

## 8. 下一轮最小化实验（H242）

只改采样名单，不改 policy、不加 allow、不动 plist：

1. 名单改为 `SpringBoard`、`lsd`、`containermanager`（每轮），其余保持首两轮；
2. 保持 `SBPORT` 三行输出，链条会自然延伸到下一层；
3. 若 `containermanager` 也在等下一层 → 继续沿链走；若它卡在锁/文件/syscall 上 → 直接定位；
4. 可选增强：给 `mach_msg2` 线程加 16 帧用户栈（`vm_map_read_user` + `pc/lr`），把"哪行代码发起调用"
   变成可证实的证据。

---

## 附录：本轮引用的原始日志行

```
[   144.333873]: /usr/libexec/lsd[92] ==> (apply-protobox)NATIVE_EXEC: pid=92 ppid=1 comm=lsd argv0=/usr/libexec/lsd argv1=
[   201.804123]: NATIVE_SBPC: sample=0 comm=lsd n=2 note=-
[   218.851122]: NATIVE_SBPC: sample=1 comm=lsd n=6 note=-
[   333.650306]: NATIVE_SBPC: sample=11 comm=lsd n=5 note=-
[   275.281241]: NATIVE_SBMSG2: sample=6 comm=lsd tid=642 opt=0x40700420e bits=0x0 ssz=0 rport=0x760b lport=0x0 vport=0x0 id=0x0 rcvname=0x221f rcvsz=16384 to=0
[   333.650165]: NATIVE_SBPORT: sample=11 comm=SpringBoard buf=0x16f604120 hdr=1 bits=0x0 size=0 rport=0x5803 lport=0x0 vport=0x0 id=0x0
[   333.650185]: NATIVE_SBPORT: sample=11 rcv name=0x2103 seen=1 set=0 ie=0x3030001 sr=1 ms=1 peer=120/SpringBoard
[   333.650201]: NATIVE_SBPORT: sample=11 req name=0x5803 seen=1 set=0 ie=0x3610001 sr=2 ms=0 peer=92/lsd
[   333.650420]: NATIVE_SBPORT: sample=11 comm=lsd buf=0x16f385ae0 hdr=1 bits=0x0 size=0 rport=0x5e0b lport=0x0 vport=0x0 id=0x0
[   333.650470]: NATIVE_SBPORT: sample=11 rcv name=0x221f seen=1 set=0 ie=0x1f030001 sr=1 ms=1 peer=92/lsd
[   333.650486]: NATIVE_SBPORT: sample=11 req name=0x5e0b seen=1 set=0 ie=0xbe10001 sr=1 ms=0 peer=62/containermanager
[   150.294011]: Protobox: DumpPanic(49) deny(1) syscall-mig 46
[   185.049125]: Sandbox: backboardd(56) deny(1) mach-lookup com.apple.lsd.installation
[   293.265178]: Protobox: lsd(92) deny(1) syscall-mig 139
```

---

## 9. H243 追加：本报告 §4 的「同步链」推断**已被推翻**

H243 在 `ipc_kmsg_send()` 里按**端口对象指针**跟踪了 SpringBoard 的接收端口与"请求端口"，
并给每个登记进程记了 `from`（发出）/`to`（收到）计数。结果：

```
NATIVE_XPC: sample=4 ports=4 [SpringBoard/r p=0xfffffff5795101a0 f=94 t=37]
NATIVE_XPC: sample=5 ports=4 [SpringBoard/r p=0xfffffff5795101a0 f=97 t=37]
NATIVE_XPC: send from=lsd(92) to=SpringBoard/q bits=0x110011 size=92 id=0x402
NATIVE_XPC: send from=notifyd(82) to=SpringBoard/r bits=0x12 size=56 id=0x463
```

**[已证实]** 新事实：

1. SpringBoard **没有卡住**：它的发送计数在观测窗口内持续增长（94 → 97），且在 `r` 上收到 37 条外部消息；
2. 被 §4 当作"请求目的端口"的那个端口，实际收到来自 powerd / nfcd / thermalmonitord /
   backboardd / mediaserverd / liveactivitiesd / containermanager / lsd / wifid / timed /
   keybagd / cfprefsd 等 **十几个进程**的消息；lsd 发往它的 8 条消息 id 为
   `0x3f4/0x3f8/0x3ff/0x401/0x402`，与 notifyd 的 `0x463/0x465/0x458` 同属 **notify(3) 协议 id 段**。

**[推断]** 因此这个端口是 **SpringBoard 注册给 notifyd 的通知令牌端口**，
不是"lsd 请求的回复端口"；§4 里"SpringBoard → lsd"的链条建立在一个不可靠的信号上
（残留缓冲区里最后一条**已接收**消息的 `msgh_remote_port`，那是发送方的回复/通知端口，
并不是"即将发出的请求的目的地"）。

**结论修正**：`bits=0/ssz=0/16KB/无超时` 的纯接收是 **libnotify/libxpc 的正常空闲形态**；
H240/H241 的"嵌套同步 XPC 链"不成立。**SpringBoard 是活的、在正常收发消息，只是没有进入 UI 初始化。**

这不改变 §5/§6 的结论（它们不依赖 §4）。

### 9.1 下一步（H244，已实现）

改为在 `ipc_kmsg_send()` **持有目的端口锁之后**调用
`ipc_port_get_receiver_task_locked(port, NULL)` 取真实接收者 pid，只记录
"发送方或接收方属于 {SpringBoard, lsd, containermanager}" 的消息，
写入 512 项环形缓冲，采样时批量打印（`NATIVE_XPC2: from=… to=… bits=… size=… id=…`）。
这样得到的是**真实收发双方**，不再依赖任何残留缓冲区。

---

## 10. L1 / L2 / L3 分层结论（H244–H246）

### 10.1 L1：SpringBoard → backboardd —— **发生过（双向）** [已证实]

H244（`to`/`from` 由 `ipc_port_get_receiver_task_locked()` 在持锁的发消息路径上取得）：

```
27 → 56 : 7 条        56 → 27 : 9 条
27 → 56  bits=0x111211 size=48  id=0x9d28
56 → 27  bits=0x80000012 size=460 id=0x9d8c     ← 同一窗口内成对出现 6 次
27 → 1   : 29 条（id=0x40000324/0x40000325 = bootstrap 服务查找）
```

**[推断]** SpringBoard 确实连到了 backboardd（不是"从未连过"），并出现了重复的请求/回复；
`0x9d28/0x9d8c` 这对 id 的语义未确定（**[待确认]**）。

### 10.2 L2：是否进入 QuartzCore/CoreAnimation —— **无正面证据** [待确认]

H245/H246 对 SpringBoard 全部线程做了 `st/pc/lr` 采样（150–530 s，26 轮）：
**所有样本的 pc 只有 4 个不同值**，全部是 libsystem_kernel 的 stub
（`___workq_kernreturn`、`___ulock_wait2`、`_mach_msg2_trap`、`___ulock_wait`），
没有一次落在 QuartzCore / CoreAnimation / FrontBoard。

方法学限制：被采到的几乎都是阻塞线程（保存的是 trap 时刻的 pc），
**这个结果不能证明 L2 没发生**，只能说"没抓到它在 CA 里运行"。**[待确认]**

### 10.3 L3：是否使用 GPU / 显示 —— **没有发生** [已证实]

530 s 内驱动侧只记录到 3 次显示客户端进入：

```
MobileGestaltHelper / IOMFB_FDR_Loader / backboardd
```

**没有一次 `comm=SpringBoard`**；`NATIVE_A540_ACCEL: open request … comm=` 与
`NATIVE_DISPLAY_OPEN: process=` 也从未出现 SpringBoard。**[已证实]** SpringBoard 从未打开
显示设备或 GPU 加速器。

### 10.4 时间线与线程形态（H246）[已证实]

| 时间 | 事件 |
|---|---|
| 131.3 s | SpringBoard pid=27 exec |
| 187.5 s | threads=4，pc 集合稳定在 4 个内核 stub |
| 206.2 s | threads=**10**（首次出现 `__dlock_wait` 工作线程） |
| 237.5 s | **插件主动重启**：pid=27 被 SIGTERM，237.6 s 起 pid=120 |
| 256–530 s | 新实例 threads 稳定在 4–5，pc 集合**再未变化**（`unchanged uniq=4`） |

**[推断]** 我们自己的"重启 SpringBoard"探针在 237 s 强行重置了启动流程；
之后新实例进入与旧实例相同的静止形态。要观察"自然启动"，必须关掉这个重启探针。

### 10.5 本轮的方法学缺陷（已知并已修复一半）

H246 的 `native_xpc_emit()` 只打印**聚合计数**、不再推进 `native_xpc_printed`，
导致环形缓冲在记录满 512 条后停止计数：

```
NATIVE_XPC3: sample=1 sb_out=205 sb_in=28 other=278 lost=206
（之后再无 XPC3 行）
```

**[已证实]** 206 s 之后的 IPC 数据缺失；L1 的结论只覆盖 150–206 s。
下一轮必须先修这个（丢弃时也要推进计数）。

### 10.6 下一轮最小实验（H247）

1. **关掉插件的重启探针**（`restart_springboard("restart")`，A540TracePlugin.mm:606），
   让 SpringBoard 自然启动并跑满 8 分钟；
2. 修 ring 计数（`lost` 也要推进），恢复 IPC 可见性；
3. **L2 的正面证据**：对 SpringBoard → launchd 的 bootstrap 查找
   （`msgh_id = 0x40000324/0x40000325`）只解析**服务名字符串**（不记录其它消息体），
   看是否出现 `com.apple.CARenderServer`、`com.apple.backboard.hid` 等图形服务名；
   出现即 L2 已发生，未出现即 UI 初始化前就停了。

---

## 11. H247：关掉重启后的自然启动观测（130–708 s）

配置：插件重启探针已关闭（`restart_springboard` → `caller("ca","restart","skipped-h247")`），
内核新增 bootstrap 服务名捕获，IPC 计数改为滑动窗口，采样 150 s 起 40 轮。
镜像 `boot-H247.img` = `50ffab1e…`，内核 `3f5d4da8…`，插件 CDHash `0fc26f08…`（信任缓存 6 项）。

### 11.1 已证实

| 观察 | 证据 |
|---|---|
| **SpringBoard 不再被我们杀掉** | 全日志只有一次 `NATIVE_EXEC: pid=26 comm=SpringBoard`（130.4 s），**没有** `NATIVE_EXIT`，`restart scan` 计数 0 |
| 插件本身正常加载并工作 | `NATIVE_ACCEL_HB: accel=167 abi=379`，`NATIVE_MTL` 67 行 |
| 观测窗口覆盖 130–708 s（约 10 分钟） | 日志末行 `[708.9]` |
| SpringBoard 线程形态**始终不变** | `NATIVE_SBTHR: unchanged threads=4–5 uniq=4`（到 507 s 仍如此），4 个 pc 全部是内核 stub |
| 显示/GPU 侧仍然**没有** SpringBoard | 驱动侧客户端仍只有 backboardd / IOMFB_FDR_Loader / MobileGestaltHelper |
| 后期仍有 IPC 活动 | `NATIVE_XPC3: sample=25 sb_out=7 sb_in=11 other=75` |

### 11.2 未达成：bootstrap 服务名捕获失败 [待确认]

`NATIVE_BOOTSTRAP` 行数为 **0**。内核里确有该字符串（`kernel.macho` 中 1 处），说明代码已编入，
但过滤条件没有命中。可能原因（按可能性排序）：

1. SpringBoard 的 bootstrap 查找集中在 **150 s 之前**（采样器 150 s 才开始设置 pid 表）；
2. 服务名不在消息体前 240 字节内联区（可能走 OOL 描述符）；
3. `msgh_id` 不是 `0x40000324/0x40000325`（那可能是 reply/其它例程）。

本轮**不猜测**：需要把过滤条件放宽（例如对所有 `to=launchd` 的消息扫描 `com.apple.` 前缀），
或在 **exec 时就**登记 SpringBoard 的 pid（而不是等第一次采样）。

### 11.3 当前最强结论

**在完全没有外部干扰的约 10 分钟里，SpringBoard 始终维持 4–5 条线程、停在 4 个内核 stub 上，
从未打开显示设备或 GPU 加速器。** 因此它不是"连上图形服务后卡住"，而是**从未推进到图形初始化**。
L2 的正面证据仍未取得（见 11.2），这是下一轮唯一要补的东西。

### 11.4 H248：放宽后的 bootstrap 捕获仍然 0 行 [已证实]

H248 修改：发送方按 comm 名或 pid 任一匹配、扫描**整个消息体**、结果带 `msgh_id`。
结果（130–712 s，无重启）：

```
NATIVE_BOOTSTRAP 行数 = 0
NATIVE_SBTHR: sample=25 unchanged threads=4 uniq=4
NATIVE_XPC3:  sample=25 sb_out=0 sb_in=0 other=186 lost=3
```

**[已证实]** 这条取证路径在本机不可用：要么 `msgh_id 0x40000324/0x325` 的消息里不含内联的
`com.apple.` 串（服务名可能在 OOL 描述符指向的用户缓冲区里），要么这个 id 只是 bootstrap
协议的**回复**编号、请求编号不同。**不再在这条路径上投入新一轮。**

**[已证实]** 同一轮里 SpringBoard 仍然：只有一次 exec、无 exit、线程 4 条、pc 集合恒定 4 个。
也就是说"SpringBoard 从未推进到图形初始化"这一结论在 **H247 + H248 两次约 10 分钟的自然启动**中
都成立。

**下一步（H249）**：不再依赖服务名，改为**高频 pc 采样**——例如 20 ms 间隔连采 200 次
（4 s 窗口），把"运行中线程"的 pc 抓到的概率提高两个数量级；同时保留 10 s 一档的全线程快照。
若 4 s 高频窗口里 SpringBoard 的全部线程仍然只出现在 4 个内核 stub 上，就可以有把握地说
"它在观测期内没有执行任何用户态代码路径"，届时再上用户态栈回溯。

### 11.5 H249：突发采样**没有执行到**（排程错误）

突发段被放在 40 轮长序列之后；而长序列每轮 ~13.5 s（打印开销），
150 s 起 40 轮 ≈ 710 s，本轮日志只到 ~500 s（`NATIVE_SBPC: sample=25`），
所以 `NATIVE_SBPC: burst start` **一次都没有出现**（burst markers = 0）。

**结论：本轮没有拿到高频 pc 数据，不要把它当作"SpringBoard 从不执行用户态代码"的证据。**

修正（下一步）：把突发段放到**长序列之前**（150 s 后立刻执行 80×50 ms），
长序列缩短到 20 轮。注意：脚本化的"移动代码块"因缩进/转义不匹配而失败，
下一次要直接改文件而不是用字符串替换。

### 11.6 H250：50 ms 突发**成功**——SpringBoard 确实在跑用户态代码（L2 部分证据）

排程修正后（160 次快照集中在 150 s 之后 4 秒窗口），突发期间 `NATIVE_SBTHR` 出现
**12 个不同 pc、132 次变化**（此前 10 s 档只有 4 个内核 stub）。符号化结果：

| 运行地址 | 符号 | 说明 |
|---|---|---|
| `libobjc.A.dylib+0x143e8` | `list_array_tt<…>::iteratorImpl::skipEmptyLists` | objc 类/协议列表遍历 |
| `CoreFoundation+0xc00c` | `_CFHash` | CF 容器哈希（字典/集合） |
| **`UIKitServices+0x17a20`** | **`__getFBProcessManagerClass_block_invoke`** | **UIKitServices 在解析 FrontBoard 的 `FBProcessManager`** |
| `libsqlite3+0x4e8e4` | `sqlite3_progress_handler` 邻域 | SQLite 查询执行 |

**结论（已证实）**：SpringBoard **不是静止的**，它在执行 objc/CF 容器遍历、UIKitServices 的
`FBProcessManager` 类解析、以及 SQLite 查询——即**应用/场景注册查询阶段**。
**仍然没有** QuartzCore / CoreAnimation / Metal 的 pc，也没有任何显示/GPU 设备打开记录。

**停点定位（有证据支持）**：`UIKitServices → FrontBoard (FBProcessManager)` 这条进程/场景管理
路径，位于图形后端初始化之前。

**下一轮（H251）建议**：
1. 把突发窗口从 150 s 起延长/重复（例如每 60 s 一次 4 秒突发，共 5 次），观察这条路径**能走多远、
   在哪一步停下**；
2. 对 `FBProcessManager` 相关调用做定点取证：在突发中把**同一批 tid 的连续 pc 序列**记下来
   （当前每 4 秒只保留去重后的集合，丢掉顺序）；
3. 若 `FBProcessManager` 之后出现 `FrontBoard`/`QuartzCore` 的 pc，则转 H246 的"图形服务连接"路线。

### 11.7 H251：五次 4 秒突发 + 有序 pc 序列（已构建，待上机）

针对 §11.6 的三条建议，H251 只改"怎么采"，不改任何策略：

1. **突发重复 5 次**：150 s 起，每轮 4 s（80 × 50 ms），轮间隔 60 s → 窗口覆盖
   150–410 s；之后仍有 10 轮 10 s 的慢序列（其他守护进程）。
2. **保留顺序**：新增内核侧 `native_sb_seq[]`（`struct {tid, pc}`，1536 项），
   突发期间每次采样都按发生顺序追加；`native_sb_trace_dump(burst)` 按 tid 分组、
   用 **RLE（`pc*次数`）** 打印，一眼区分"推进"和"原地打转"。
3. **静默模式**：突发期间关闭 `NATIVE_SBPC` 逐线程打印、`SBTHR unchanged` 行与
   `SBPORT` 的用户内存读取（每 50 ms 一次 `vm_map_read_user` 本就没必要），
   只保留"pc 集合变化"时的完整线程表，避免 400 次采样把环形日志冲掉。

新增输出行样例：

```
NATIVE_SBSEQ: burst=2 tid=301 n=80 runs=4 seq=1eb3888c0*37,1b5915a20*2,1a7a8500c*1,1eb388aec*40
```

- 镜像 `boot-H251.img` = `46d78eef…`，内核 `b6a5e674…`，插件与信任缓存不变（6 项）。
- 补丁：`patches/xnu/zzzzzzzzzzzz-h251-sbseq.patch`（**同时包含** H248 放宽后的
  bootstrap 捕获代码，使补丁集重新自洽；已验证：pinned xnu + h103 + h251 应用后
  与构建树 `osfmk/kern/task.c` 完全一致）。
- 判读：某 tid 的 RLE 序列在 5 轮之间**变长/出现新 pc** → 路径在推进；每轮都是
  同几条 `*40`/`*80` → 该线程整轮没动。

### 11.8 H251 结果：185 s 之后 SpringBoard **完全静止**（已证实）

五次突发中跑到 4 次（burst 0–3，185 / 252 / 316 / 380 s；日志在 387 s 结束，burst 4 未执行）。
`NATIVE_SBSEQ` 的有序序列非常干净：

| burst | 线程数 | 序列形态 |
|---|---|---|
| 0 (185 s) | 7 | tid 290 `mach_msg2_trap*2, kevent_id*17, mach_msg2_trap*32`；tid 579 序列里出现 **`libobjc realizeClassWithoutSwift`**；tid 587 `ulock_wait*2, ulock_wait2*25` |
| 1 (252 s) | 5 | **每个 tid 都是同一 pc × 80**（runs=1） |
| 2 (316 s) | 5 | 同 burst 1，**pc 完全相同** |
| 3 (380 s) | 5 | 同 burst 2（只是 workq 线程 tid 从 728/888 换成 1286/1349，pc 不变） |

符号化（slide 由 `NATIVE_TRAP_IMAGE_ROW` 反解，`delta=0x1d4f8`）：

| pc | 符号 |
|---|---|
| `0x1cbc1cb58` (tid 290, 主线程) | `mach_msg2_trap+0x8` |
| `0x1cbc1c8c0` (burst 0 内的 tid 290) | `_kevent_id+0x8` |
| `0x1cbc1c970` (tid 581) | `__ulock_wait2+0x8` |
| `0x1cbc22bdc` (tid 587) | `__ulock_wait+0x8` |
| `0x1cbc1c8e8` (两个 workq 线程) | `___workq_kernreturn+0x8` |
| `0x1805900f8` (burst 0, tid 579) | `libobjc realClassWithoutSwift+0x110` |

**结论**：SpringBoard 在 185 s 还在做 objc 类实现（`realizeClassWithoutSwift`），
到 252 s 已经**全部线程停住**：主线程永久停在 `mach_msg2_trap`，其余在 `ulock_wait`/`ulock_wait2`
/`workq_kernreturn`。此后 128 秒内**没有任何一次 pc 变化**（5 个 tid、各 80 次采样、runs=1）。

这与 H237 的结论互相印证：主线程的等待是**无超时的纯接收**（`bits=0`），
即"发出请求后等回复、而回复永远不来"。

### 11.9 H252：把"最后一次发送"钉出来（已构建并刷入）

既然它停在等回复上，就查它最后发了什么、发给谁：

- 内核新增 **SpringBoard 专用发送环**（`native_sb_sends[32]`，记录 `seq/to/id/size/bits`），
  在 `native_xpc_note()` 里对 `from==SpringBoard pid` 的消息登记（不打印、不加锁）；
- 每轮突发结束时 `native_sb_send_dump(burst)` 打印**最新的 8 条**，
  并在打印时（不在 IPC 路径里）用 `proc_name()` 把目的 pid 解析成进程名；
- 每轮突发后补一次**完整**（非静默）采样，保证被阻塞线程的 `mach_msg2` 参数
  （`opt/bits/ssz/rport/lport/id`）与端口归属始终在日志里；
- 突发期间不再输出 `NATIVE_XPC3` 计数行（原来每 50 ms 一行）。

镜像 `boot-H252.img` = `34dd7c4f…`，内核 `398b7fbf…`；
补丁 `patches/xnu/zzzzzzzzzzzz-h252-sb-sends.patch`（已验证：pinned + h103 + h251 + h252
应用后与构建树 `task.c` 一致）。
