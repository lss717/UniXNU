# H254：SpringBoard Scene / 前台激活链路诊断报告

- 日期：2026-11-12
- 设备：OnePlus 5（cheeseburger，MSM8998 / A540）
- 目标系统：iPad7,1 / iPadOS 17.7.11（21H461）
- 基线：HEAD `976d659`（H253 文档），工作区干净
- 本轮性质：**只构建，不刷写**。运行观测待用户决定后执行。

---

## 1. H254 修改摘要

H254 不改任何被观测系统的行为（SpringBoard、FrontBoard、RunningBoard、AMFI、
TrustCache、激活状态、UFS/启动链均未触碰），只做三件事：

1. **修 H253 的两个探针 bug**（端口对象 vs 端口名、静默路径漏放 task 引用）；
2. **补齐等待状态与端口统计**（`NATIVE_SB_WAIT`）；
3. **新增 Scene/前台链路的双向 IPC 采集**（`NATIVE_SBPEER`）与
   **mobileactivation 陷落点采集**（`NATIVE_EXC`）。

## 2. 修改文件与关键代码位置

| 文件 | 位置 | 目的 |
|---|---|---|
| `osfmk/kern/task.c` | `native_sb_probe_name()` | 端口字段读取语义修正；`qcount` 标记 unavailable |
| `osfmk/kern/task.c` | `native_sb_pc_sample()` | **P0**：静默路径统一走 `sbport_release:` 释放 task 引用 |
| `osfmk/kern/task.c` | `struct native_sb_send` / `native_sb_note()` | 端口字段改存 **`ipc_port` 对象**（64 位），不再与端口名混用 |
| `osfmk/kern/task.c` | `native_sb_send_dump()` | `MATCH` 改为 **port 对象指针相等**比较 |
| `osfmk/kern/task.c` | `native_sb_peer_dump()`（新增） | SpringBoard 全部进出消息的双向记录 |
| `osfmk/kern/task.c` | `native_sb_pc_sample()` 的 bootstrap 段 | 扫描条件改为 **`to == launchd(1)`**，不再依赖 `msgh_id` |
| `osfmk/kern/task.c` | `native_xpc_emit()` | 增加 `produced / consumed / pending`（环形缓冲统计） |
| `osfmk/kern/task.c` | `native_exc_probe()`（新增） | mobileactivation 的陷落 `pc/lr/tid/exc` |
| `osfmk/kern/exception.c` | `exception_deliver()` 入口 | 调用 `native_exc_probe()`（只读，不改投递行为） |

补丁：`patches/xnu/zzzzzzzzzzzz-h254-scene-probe.patch`（317 行，含 `task.c` 与 `exception.c`）。

## 3. 探针修复前后的验证结果

| 项 | 修复前（H253） | 修复后（H254） |
|---|---|---|
| `msgh_local_port` 语义 | 当作 Mach port name，与 `0xa03` 比较 → 永不命中 | 当作 **`ipc_port` 对象指针**（`0x1628da60` 形态），与接收端口对象比较 |
| `MATCH` | 恒不命中 | 命中时输出 `MATCH` |
| 静默模式 task 引用 | 跳过端口探针 → `task_deallocate()` 从不执行 → **引用泄漏** | 统一 `sbport_release:` 路径，**任何模式都释放一次** |
| `rcv=` | 恒为 `0x0` | 正常模式下为真实端口名/对象 |
| bootstrap 服务名 | 依赖 `msgh_id==0x40000324/325` → 0 行 | 扫描**所有** SpringBoard→launchd 消息 |

**静态检查**（不刷机）：

- `git apply` 在全新 worktree 上依次应用
  `h103 → h251 → h252 → h253 → h254` 全部成功；
- 应用后 `osfmk/kern/task.c` 与 `osfmk/kern/exception.c` 与构建树**逐字节一致**；
- 内核 `.macho` 内 `NATIVE_SBPEER / NATIVE_SB_WAIT / NATIVE_EXC / NATIVE_SBSEND`
  字符串均存在（`NATIVE_SB_WAIT`、`NATIVE_EXC` 各 1 处）。

**未做的检查（需要刷机）**：引用计数随时间的实际增减、目标 task 不存在时、
目标 port 已失效时的行为、多次采样是否仍泄漏。这些在 §11 里登记为待确认。

## 4. 端口等待状态统计（探针定义）

`NATIVE_SB_WAIT` 每轮详细采样输出一行：

```text
NATIVE_SB_WAIT: sample= pid= tid= wait_type=mach_msg2 rcv=0x.. port=0x.. recv_pid= recv_comm= sr= ms= q=
```

| 字段 | 来源 | 说明 |
|---|---|---|
| `pid` / `tid` | 采样器 | 被观测进程与停在 `mach_msg2` 的线程 |
| `rcv` | `x5` 高位 | 接收端口名 |
| `port` | `ipc_entry->ie_object` | 端口对象，**不是名字** |
| `recv_pid` / `recv_comm` | `ipc_port_get_receiver_task()` | 持有接收权的进程 |
| `sr` / `ms` | `ip_srights` / `ip_mscount` | 发送权计数；**不是**未完成 RPC 数 |
| `q` | `ip_messages.imq_msgcount` | **本轮标记 unavailable（`0xffffffff`）**：端口锁 API 在该文件不可见，按要求不越权读取、不猜 |

解释限制（写进判据）：

- `sr > 0` 只说明"存在发送权"，**不能**推出"欠回复"；
- `q == 0` 只说明"队列当前为空"，**不能**推出"没人会发"；
- 判定必须结合 `NATIVE_SBSEND`（谁发了、`loc`/`rem` 是哪个对象）与
  `NATIVE_SBPEER`（谁收、有没有回）。

## 5. SpringBoard bootstrap 服务查询结果

采集方式改为：`from == SpringBoard && to == launchd(1)` 的**所有**消息都扫描
`com.apple.` 前缀串，输出：

```text
NATIVE_BOOTSTRAP: sample= name=<服务名> id=0x..
```

- **本轮未执行**（只构建）。
- 已知限制：`bootstrap_look_up` 的请求体里服务名是内联 `string_t`；
  若该次查找走 OOL 描述符，仍会漏采。H254 未改变这一点，报告中按 `unknown` 处理。

## 6. FrontBoard / RunningBoard IPC 交互记录

`NATIVE_SBPEER` 采集 **SpringBoard 作为发送方或接收方的全部消息**（不限服务名），
每轮突发打印最新 14 条：

```text
NATIVE_SBPEER: burst= seq= <from_pid>/<comm> -> <to_pid>/<comm> id=0x.. size= bits=0x..
```

设计理由：**不预设 FrontBoard/RunningBoard 的服务名**。它们的 pid 一旦出现在
SpringBoard 的收发表里，就会带着 comm 名一起出现；服务名与 pid 的对应关系
以实测为准，不用推断值。

- **本轮未执行**。可区分的阶段（报告口径）：
  - `service_lookup`: 由 §5 的 `NATIVE_BOOTSTRAP` 行判定；
  - `service_ipc`: 由 `NATIVE_SBPEER` 是否有对应 pid 的进出记录判定；
  - 两者**不互相等同**。

## 7. Scene 创建证据

本探针**不直接观察 Scene 对象**，只提供 IPC 层证据：

- 若 `NATIVE_SBPEER` 中出现 SpringBoard ↔ RunningBoard/FrontBoard 的**请求/响应成对**
  记录（同一对 pid、方向相反、时间相邻），记为 `scene: creation_requested`；
- 只有拿到 RunningBoard 侧的正面应答（回到 SpringBoard 的消息）才记为 `responded`；
- **不会**因为 IPC 条数增加就写 `created`。

`scene: created` 需要 Scene 对象/会话层面的证据，当前工具**不具备**，按
`unknown` 记录——除非未来能读 `runningboardd` 的 Scene 表。

## 8. 前台激活证据

判据同 §7：`foreground: activation_requested` 仅由 IPC 方向/成对关系支持；
`active` 需要前台状态变化的正面证据（本探针不提供），记为 `unknown`。

## 9. CoreAnimation / GPU 观测结果

保留原有能力，未改动：

- `NATIVE_DISPLAY_OPEN`（显示设备打开，按进程）；
- `NATIVE_ACCEL_HB accel=/abi=/s345=`（加速器打开与用户态 ABI 计数）；
- `NATIVE_MTL`（插件侧的 Metal 调用轨迹）。

**本轮未执行**。H253 已证实：`mediaserverd` 反复打开 `AGXAccelerator`，
SpringBoard 一次也没有——H254 保持该观测点不变，用于对照。

## 10. mobileactivation SIGTRAP 分析

新增 `NATIVE_EXC`（只在 `comm` 前缀为 `mobileactivation` 时输出，且按
`(pid, tid, pc)` 去重）：

```text
NATIVE_EXC: pid= comm=mobileactivation tid= exc= pc=0x.. lr=0x..
```

- 采集点：`exception_deliver()` 入口。这里是内核把异常交给处理器的地方，
  崩溃线程的用户态保存状态仍然完整，`pc` 即陷落点；
- **不修改**异常投递行为，只读；
- 已知局限：`exception_deliver()` 对每个 action 调用一次，同一异常可能产生多行，
  已按 `(pid,tid,pc)` 去重；`exc` 是异常类型（`EXC_BREAKPOINT` = SIGTRAP 来源）。

**本轮未执行**，因此"是否同一 PC"、"是否同一调用路径"、"是否与激活/SetupAssistant
相关"全部记为 **待确认**。归因边界：即使多次 SIGTRAP 落在同一 PC，也只能说
"稳定的重复失败路径"，不能据此断言是激活状态错误。

## 11. 数据丢失与探针干扰说明

- **环形缓冲**：内核侧 IPC ring（512 条）本轮新增 `produced / consumed / pending`
  统计输出；`lost` 沿用原计数。**未验证**"溢出后能否恢复采集"——需要一次长跑。
- **driver 侧 h103 ring**（8 MB 窗口，256 slot）：未改动。H253 的运行出现过
  日志尾部截断，属于既有窗口特性，不是本轮引入。
- **采样开销**：突发仍为 5 轮 × 4 秒 × 50 ms；每轮结束有 1 次完整采样
  （会做 `vm_map_read_user` 与端口探测），只在采样线程上下文，不在 IPC 路径。
- **IPC 路径开销**：`native_xpc_note()` 新增一次 `native_sb_peers[]` 写入（无锁、
  无分配、无打印），只是几条整数赋值。
- **不重启 SpringBoard**：本轮的插件仍是 H247 的"重启探针已关闭"版本
  （CDHash `0fc26f08…`，信任缓存 6 项），SpringBoard 自然运行。

## 12. H254 结论

**已证实**（静态/构建层面）：

1. H253 的两个探针 bug 已修复，且修复后的补丁集可在全新工作树上**逐字节复现**
   构建树源码；
2. 端口字段的语义已按 `ipc_kmsg` 的真实类型（`ipc_port` 对象）处理，不再与
   端口名混用；
3. task 引用在任何路径（含静默路径）都只释放一次；
4. 新增的四类输出均已在生成的内核中确认存在。

**未观察到**（本轮未上机）：Scene / 前台链路的一切结论。
因此以下状态矩阵**全部为"未执行"**，不得填入任何观察结论：

```text
service_lookup:  not_executed
service_ipc:     not_executed
scene:           not_executed
foreground:      not_executed
rendering:       not_executed
```

## 13. H255 建议

1. **先跑本轮镜像**（8 分钟），只做观测，不改代码；按 §6 的
   `NATIVE_SBPEER` 判断 FrontBoard/RunningBoard 是否出现在 SpringBoard 的
   收发表里。
2. 若 `service_ipc: not_observed` → 说明停点在"服务查询"或更早，H255 转向
   bootstrap 名称采集的可靠性（OOL 描述符解析）与 `UIKitServices` 那条路径。
3. 若 `service_ipc: sent` 但 `responded: not_observed` → 转向 peer 侧
   （RunningBoard/FrontBoard 的采样），确认对端是否收到、是否处理。
4. `NATIVE_EXC` 拿到 mobileactivation 的 `pc/lr` 后，再用 `mach-o` 符号化定位
   断言点；**不要**先改激活状态。
5. 端口 `q` 字段若确有必要，再评估引入端口锁 API 的正确用法（需要确认该
   XNU revision 的锁封装），不要在 H255 里顺手改锁。

---

## 附：本轮产物

| 项 | 值 |
|---|---|
| 镜像 | `/tmp/opencode/boot-H254.img` |
| 镜像 SHA-256（前 16） | `24b02fb048b6254f` |
| 内核 SHA-256（前 16） | `e40856402c3452a5` |
| 补丁 | `patches/xnu/zzzzzzzzzzzz-h254-scene-probe.patch` |
| 内核构建命令 | `bash scripts/macos-build-kernel.sh` |
| prelink 命令 | `~/.local/bin/python3.12 ./unixnu build prelink -D ../UniXNU-cheeseburger` |
| 打包命令 | `python3 scripts/make-bootimg.py --edk2 ../edk2-msm8998 --kernel ../edk2-msm8998/workspace/uefi-cheeseburger.img.gz-dtb --payload payload-H254.img --out boot-H254.img` |
| 镜像大小 | 81,149,952 B（与 H250–H253 完全一致；这些镜像均已成功启动） |
| 刷写 | **未执行**，由用户决定 |

---

# H254 运行结果（2026-11-12，`boot-H254.img` / 内核 `e4085640…`）

窗口 0–656 s，5 轮突发全部执行。SpringBoard pid=27、主线程 tid=290。

## 状态矩阵

```text
service_lookup:  not_observed      (NATIVE_BOOTSTRAP = 0 行)
service_ipc:     sent + received   (仅 runningboardd 一次往返)
scene:           not_observed
foreground:      not_observed
rendering:       not_observed      (SpringBoard 打开显示/AGX 次数 = 0)
```

## 1. 已证实：SpringBoard 与 runningboardd / backboardd 只有"一次"往返

`NATIVE_SBPEER` 全窗口共 420 条 SpringBoard 进出消息，其中与 Scene/前台相关的只有 3 条，
全部出现在 **burst 0（~191 s）**，此后再无一条：

```text
seq=268  27/SpringBoard   -> 26/runningboardd  id=0x40000000 size=200 bits=0x111211
seq=269  26/runningboardd -> 27/SpringBoard    id=0x20000000 size=52  bits=0x12
seq=272  56/backboardd    -> 27/SpringBoard    id=0x20000000 size=52  bits=0x12
```

- **SpringBoard → backboardd：0 条**（只有 backboardd 发给它）；
- 之后 ~465 s 内，runningboardd / backboardd 再未出现在 SpringBoard 的收发表里；
- 同一窗口的其余流量全部是 notifyd、wifid、sharingd、mediaserverd、chronod、followupd、launchd。

## 2. 已证实：等待不是"欠回复"

`NATIVE_SB_WAIT`（5 轮一致）：

```text
pid=27 tid=290 wait_type=mach_msg2 rcv=0x903 port=0xfffffff75ab74100
recv_pid=27 recv_comm=SpringBoard sr=1 ms=1 q=unavailable
```

`MATCH` 计数 **0**：窗口内没有任何已记录发送把该端口对象当作回复端口。
结合 §1 的空转形态，主线程是在等**事件**，不是等某个未回的答复。

## 3. 已证实：mobileactivation 是稳定的同一处失败

14 次 `NATIVE_EXC`，全部 `exc=6`（`EXC_BREAKPOINT` ⇒ SIGTRAP），
且 `pc` 的低 12 位**全部是 `0xac0`**（`0x100840ac0`、`0x100dabac0`、`0x1013cdac0` …），
`lr == pc`：

- **同一映像、同一偏移、同一线程路径**，仅 ASLR slide 不同 → **稳定的重复失败路径**；
- 具体映像与符号仍未定位（需要该进程自己的 image base），故**不归因**为激活状态错误。

## 4. 探针可靠性（验收 A 项）

| 检查 | 结果 |
|---|---|
| 端口对象匹配 | 端口对象为真实 64 位指针 `0xfffffff75ab74100`（H253 的 32 位假设被推翻，H254 已改 64 位） |
| 静默模式 task 引用 | 统一走 `sbport_release:`，`rcv=0x903` 正常采集（H253 恒为 `0x0`） |
| bootstrap 名称 | 仍为 0 行（SpringBoard→launchd 有 3 条消息，但内联区没有 `com.apple.` 串） |
| 环形缓冲 | `lost=2`（512 条窗口滑动丢弃 2 条）；`consumed=0` 是该缓冲的设计（只计数、不消费），`pending` 即窗口内条目数 |
| SpringBoard 自然运行 | 无 `NATIVE_EXIT`（全程未被杀），51 次退出全部是其它守护进程 |

## 5. 结论与 H255

**强推断**：停点在 **runningboardd 的第一次往返之后**——请求发出去了（200 B XPC），
对端也回了一条（52 B），但之后既没有后续 Scene 交互，也没有任何显示/AGX 打开。
即 `scene: not_observed`、`foreground: not_observed`、`rendering: not_observed`。

H255 建议：
1. 给 `NATIVE_EXC` 增加 **主映像 base**（`task->all_image_info_addr` 或 `proc_ro` 里的
   `p_uuid`/load address），把 mobileactivation 的 SIGTRAP 定位到具体符号；
2. 对 **runningboardd** 也开采样（同一套 `native_sb_pc_sample`）：看它在收到那 200 B 之后
   是否卡住、卡在哪；
3. 若 runningboardd 正常，再查那 200 B 消息的 `id=0x40000000` 在 libxpc 里对应哪种调用
   （需要用户态符号化，不要凭空命名）。
