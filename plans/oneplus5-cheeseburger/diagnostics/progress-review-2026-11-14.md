# OnePlus 5 进度复核与实验调整

## H387 容器管理器等待链采样

CPU385 的日志窗口持续到约 494.5 秒。SpringBoard 末尾请求转为 `peer=92/lsd`，lsd 的 tid491 在 `_LSInstallProgressService performJournalRecovery` 内同步等待 dispatch ownership，tid493 和 tid680 等待同一个安装或数据库恢复 group。tid664 则在 InstalledContentLibrary 完成目录与 bundle 校验后，转入 `container_xpc_send_sync_message`，说明 lsd 初始化仍有阶段推进，单轮证据不能认定为进程内死锁。

源码复核发现 `native_sb_name` 为 `containermanager` 时，旧比较使用完整 16 字符长度；进程 `p_comm` 被截为 `containermanage`，所以该服务此前一直未命中。H387 将进程名比较限制在 16 字节字段内，按 `proc_name` 的前缀匹配；每次采样开始把 pid 重置为 -1，避免失败时沿用上一进程身份。

新增 `native_sb_pc_sample_instance()`，允许按匹配实例编号采样。驱动在每轮 CPU 低开销 burst 中分别采集第 0、1 个 containermanager 实例，sample id 保持 30 的倍数以取得帧链。每个样本只持有一个匹配任务，避免 system 与用户服务实例混入同一用户内存读取。

本轮保持 CPU 路线：不使用 GPU addon，`offline-accelerator=0`，`sheng-gpu-addon=0`，无 `sheng-gpu-power`。H387 只增加容器服务观测，不改变桌面启动逻辑。

## 并行复核与日志修复预编译

用户授权并行后，日志代理完成slot/header静态缓冲复用（132KiB BSS）和可选slot线程CAS入口修复，提交e0b60c6。Mac拉取后构建和prelink成功，包内内核逐字节核验通过。独立LOG386沿用CPU385的无GPU上电参数，kernel SHA-256为 `0b2b502654e341f6696f2f9ad39b2ed7eb10f82faee24fdc4f08c0cfe1c00497`，payload为 `8378b5e9e7cca8ec951fd45881498f75e8716bd2c87891ce2ff151e102441fb7`，boot为 `c88ea4bac4b88f3da614d3a68cf88aa0e8087d87c1eae6508d331addc3f07c64`。该产物在CPU385运行期间预编译，尚未上机。

CPU主线只读复核H384符号：SpringBoard栈为_BKSDisplayGetMainScreenInfo、_BKSDisplayServicesGetMainScreenInfo、BKSDisplayServicesStart、BKSSystemShellService _activateServerConnectionWithIdleSleepInterval:、FBSystemShell _initWithOptions:，当前候选门槛为BackBoard主屏RPC/check-in。backboardd在208秒已有CA::Render::Server::server_thread与CA::WindowServer::IOMFBServer::thread_body，不应单凭IOAcceleratorES匹配失败宣布CPU回退被阻塞。另一个初始化线程停在AnalyticsConfigurationObserver对象构造，cpu=0 st=0x49，是初始化或页入等待候选，尚待同轮持续采样确认。

历史H318关于proc_selfname遍历进程链表并取锁的解释与当前实际构建源码不符：bsd/kern/kern_proc.c中的proc_selfname直接从current_proc读取p_name。保留历史记录，但不能直接照搬其根因结论。STATUS H190已做nil插件稳定运行但零帧实验，当前CPU路线避免重复该组合。

## CPU385 纯CPU参数对照

用户确认当前主线为先用CPU进入桌面。历史STATUS H333/H334明确纯CPU配置应移除gpu-power。H384虽关闭accelerator和addon，却仍带sheng-gpu-power=7；该参数由heartbeat独立调用，可进入SPMI及A540初始化。CPU385沿用H384全部产物，仅从实际payload参数删除该项，保留cpus=1、accelerator=0、addon=0。内核日志build仍为H384，必须配合boot ID及镜像哈希辨别。本轮不合入独立代理的日志静态缓冲修复。

Mac先拉取后打包，boot_args最坏882/1024字节。payload SHA-256为 `5cf4f400076d1a6b09741a392f6f2b039fdb49132d4fc25742dd54b1165ecec1`，boot为 `2ec0e2364e85afce4d7d811305a546b46ff76c501d96382ec6c4b49e3d502453`。先前准备的GPU385包未启动。

## H384 限频与启动前清理

用户指出HANDOFF要求每轮启动前清零日志环。此前各轮未执行清零，已通过boot ID分组解码。本轮用户明确授权后，确认userdata_ios大小52840607744字节，清零末尾32MiB（4096字节块，seek=12892347，count=8192），完整读回验证全零。H383日志已备份。

H384将burst内SpringBoard采样从80次降至4次，间隔50ms改为1000ms，每个burst只采样一次其他服务，30秒间隔内的launchd/runningboardd采样各从30次降为1次。其他日志源尚未全面限频，启动参数保持H383配置。

Mac拉取3b2bbed后构建与prelink成功，包内内核逐字节比较通过，参数最坏900/1024字节。kernel SHA-256为 `223009ed13735cbc754327806f537b5ce717ece59107436483e74a3b14c1c822`，payload为 `a10d75daccd2d2a37e29472ebffed32145bdc392e763ef10d58bfb4df2f8a3cc`，boot为 `c1202316885fa324f8703af5c401447adc240e294cd17efe31603d3a84f3198c`。日志清零和采样限频在同一轮实施，效果需要进一步对照区分。

## H382 延长运行与 H383 观测修复

同一 H382 镜像于北京时间约 20:19:40 再次启动，用户在运行中反馈仍有日志输出且没有 panic，约 20:35 返回 TWRP。新 boot=21d39521，有效槽226个，另有上轮遗留槽21个，解码已按新轮次筛选。正文仅覆盖29.6–236.4秒，末尾显示dpy=0、SpringBoard仍为launchd代持端口q=1，未记录到lsd exec。窗口内无OCS timeout、恢复或块请求拒绝。该轮没有覆盖15分钟后半段，不能用它判断seeding最终完成与否。

当前构建XNU_NATIVE_UFS=0、XNU_NATIVE_RAM_BLOCK=1，启动参数未启用sheng-data-persist。NativeRamBlock在该组合下使用volatile Data，跨重启从同一种子重新开始，因此需要考虑每轮重新建立数据库的开销。

源码复核发现h103FlushNow在h103SlotWrite失败后仍将gH103LastSlotMsgX推进到当前游标，丢弃尚未落盘的字节，busy标志也通过非原子读写保护多个刷新入口。H383使用CAS串行化slot/header刷新，仅在每个slot及其header成功后推进游标，并由独立watchdog线程每秒调用刷新入口。沿用H382的单核、AKS和显示参数，先验证长时间观测可靠性。

Mac 拉取8919cfa后完成H383内核构建和prelink，包内内核逐字节核验通过。boot_args最坏900/1024字节。kernel SHA-256为 `6f6fdee01ac8803cab390c204316620e919bb1ce1d84d22f2cff45e89b4f4686`，payload为 `d920ca9d18235546aa44a2c53ce1a8d4139652806d997805b898dee45dfaf9a1`，boot为 `6ef1e5baf055ccf4f27aebca5893e8fed8997c3940f8e9e34b09d621754620fb`。

## H382 真机日志与符号化结果

从 TWRP 取回原始环 assets/log-review/h103log-H382.bin。247 个有效槽均为 boot=24bde90f、build=H382。正文覆盖约 82.3–441.1 秒，早期记录已被环覆盖。窗口内 OCS timeout、DBTO、RECOVER、块请求拒绝和 UFS stall 均为零，UFS 命令数在 326–405 秒由 38106 增至 44109，累计读取约 3.78 GB。相较 H381 有改善，仍需重复验证。

LOG_STAT 的 errors 累计到 68，存在日志丢写，脚本输出 CHECK。该计数也包含 try-lock 失败，不能直接解释成 68 次磁盘命令失败。保留块为 H382 的 stall，uptime=213、hbago=10，但正文之后持续到 441 秒，说明这个历史心跳延迟标记不能当作最终停机时刻。

使用本轮 NATIVE_SBPC_IMAGE 的 slide=0x1ddcc000、base=0x19ddcc000，在 Mac 对同一系统共享缓存提取文件符号化。SpringBoard 主线程末尾栈如下。

```text
mach_msg2_trap
mach_msg_overwrite
mach_msg
_dispatch_mach_send_and_wait_for_reply
dispatch_mach_send_with_result_and_wait_for_reply$VARIANT$mp
xpc_connection_send_message_with_reply_sync
__NSXPCCONNECTION_IS_WAITING_FOR_A_SYNCHRONOUS_REPLY__
-[NSXPCConnection _sendInvocation:orArguments:count:methodSignature:selector:withProxy:]
```

因此同步等待成立。单独看到 ssz=0 的 receive 阶段不足以判断其外层是否同步 RPC，必须结合栈。此时缓冲的 rport=0x5a0f 被探针关联到 pid91/lsd，但当前消息 ID 和头部均为零，目标关联仍需发送时的事件确认。

lsd 在 257.8 秒 exec。316 秒栈包含 _LSCreateRegistrationDataForDirectoryNode、_LSCreateRegistrationData、_LSServerCreateBundleDataAndRegister、_LSDispatchRegistration、_LSRegisterDirectoryNode、_LSRegisterBundleNode、_LSFindOrRegisterBundleNode、_LSDatabaseClean，表明它正在执行注册和数据库清理。

422.6 秒 tid814 栈如下。

```text
_dispatch_group_wait_slow
__LAUNCH_SERVICES_CLIENTS_ARE_WAITING_FOR_THE_DATABASE_TO_FINISH_SEEDING__
-[LSDatabaseBlockingFetchClient getServerStoreBlockingWithCompletionHandler:]
__NSXPCCONNECTION_IS_CALLING_OUT_TO_EXPORTED_OBJECT_S1__
-[NSXPCConnection _decodeAndInvokeMessageWithEvent:reply:flags:]
```

另一工作线程还出现 -[_LSInstallProgressService restoreInactiveInstalls]。当前最具体的候选阻塞为 LaunchServices 数据库 seeding 尚未完成。尚无法证明它是死锁，也无法把 SpringBoard 的等待直接关联到这条服务调用。

下一轮优先使用同一 H382 产物延长观察至 15 分钟，记录数据库 seeding 的工作线程、注册路径和 I/O 进展，核实 Data 种子是否使每轮都重新初始化。保留现有单核、AKS 和显示参数。若工作进展停滞，再针对其等待组及执行队列补充诊断。显示 val/xf/fr 仍为零，第一帧待验收。

## H381 失败与 H382 修复

H381 原始日志已从 TWRP 提取，NATIVE_BUILD 为 H381，boot=24aaf3ab，正文约 32–213 秒。保留块为 logstop，记录日志在崩溃前已经停止。用户照片显示锁等待超时、块请求拒绝、OCS timeout、hcs=8 ready=0、backboardd SIGBUS，最终 ipc_space.h:173 断言，与 H360 的级联故障相似。当前证据不足以单独归因于单核。

源码审查发现紧急 logMarker 在没有 fLock 的情况下修改 fQueue 的 DMA 数据指针，清除 poisoned 状态，并尝试重发同一写请求最多 50 次。该路径被早期 boot/alive、logstop 和 stall 调用，可与正常 I/O 竞争同一槽和 DMA 缓冲。H382 将所有 marker 路径改为 try-lock 保护，包含静态标记缓冲的填充，忙时直接放弃，保留 poisoned 状态，写入仅尝试一次。该修复消除已确认的共享状态竞争，控制器恢复能力仍待验证。

同时更正 H361 注释。仓库内 EDK2 UfsPassThruHci.h 定义 HCS.DP=BIT0、HCS.UCRDY=BIT3。现有 hcs & 1 的判定实际检查设备存在，照片 hcs=8 仅表示 UIC 就绪。本轮保留恢复谓词，完整链路重建需单独设计和验证。

H382 在 Mac 拉取 b07327f 后完成构建和 prelink，包内内核逐字节比较通过，标识 H382。沿用 H381 的 cpus=1 和其他全部启动参数、固件及 payload 侧文件，boot_args 最坏 900/1024 字节。kernel SHA-256 为 `dabd3360aaa7d2c8f832fd5233bb302643f5e24432df3885fa4b2635eaa87322`，payload 为 `e44ade9a7e57a88374269d7d68a0b5efe651e022f3e8ea5fae5d94fec9514f51`，boot 为 `8a5a6099ae4ee4a09689a165e2def26e0412c97c09028a4bca282b3e6c3e2ad7`。真机恢复及稳定性待本轮日志验证。

## H381 构建与单核对照产物

- 源码提交为 `62e260a`，Mac 在拉取并更新子模块后构建，正式内核和 prelink 成功，包内内核逐字节比较一致，日志 build 标识为 H381。
- Mac 设备仓库原有 unixnu.lock 增加 edk2 引用，已保留并备份至 `~/op5-h381/existing-device-lock.diff`，本轮沿用 H380 固件。
- 基底采用从实际 boot-H380.img 提取的 ramdisk。独立 payload-H380.img 携带早期配置，与启动镜像内配置不同。真实 H380 参数已确认是 cpus=2，H381 仅将其切换为 cpus=1，并替换本轮新内核。
- boot_args 最坏长度为 900/1024 字节，长度检查通过。
- kernel SHA-256 为 `ef7fea49b2e25ad31660743b9d283096c971f77a6f0f3b5e2079c30c8fa64337`。
- payload SHA-256 为 `c4bc694ceea9b25463c73966870e40f9934b6c46300c4266596593a912a267c5`。
- boot SHA-256 为 `e49df846fefdefca95427d612565d4140f91b3532cb4845a2ec0408691d5ae67`。
- 启动前已备份设备现有日志环为 assets/log-review/pre-H381-log.bin。后续日志需要按新的 boot ID 分组。

本次复核依据当前工作树、HANDOFF.md、STATUS.md 末尾 H378、H380 探针、assets 启动配置与 UFS 报告脚本。assets 只有镜像和配置，没有各轮原始日志。本次没有构建或真机复测。历史记录含 2026-11-15 日期，本文保留其 H 编号，时间顺序仍需以 boot ID 和产物记录核对。

更新：随后从用户指定的 192.168.10.127 `/tmp/opencode` 获取 52 份 h3*-log.txt，并下载 H366/H378/H380 原始日志环，保存于根目录 assets/log-review。以下结论以原始环重新解码为依据。

## 原始日志复核结果

| 轮次 | slot boot ID | 有效槽数 | 槽 uptime 区间 | 观测 |
| --- | --- | --- | --- | --- |
| H366 | 32692708 | 247 | 85–476 s | 请求目标在多个服务之间变化，存在 13 次 peer=92/lsd 采样，显示 val/xf/fr 仍为 0 |
| H378 | 326e537f | 247 | 24–385 s | lsd 有非零线程采样，末尾请求 peer=1/launchd，无法把整轮归结为 lsd 空闲 |
| H380 | 327f5a08 | 219 | 1–223 s | lsd 采样均为 n=0，末尾 SpringBoard req 为 peer=1/launchd、q=1 |

三份原始环中识别出的有效槽各自只有一个 boot ID。三份槽 build 标签均为 H236，不能用它区分 H366/H378/H380 内核。槽 uptime 与正文时间戳采用不同起点，应分别记录。

H380 的 SpringBoard 为 pid 27。观察到的 dst=-1 消息 ID 为 0xd4d、0xc8、0xce、0xd5a、0x1f40，大小为 44–124 字节。末尾等待快照为 id=0x5b9173、rport=0x3a03、peer=1/launchd、q=1。两组记录缺少同一请求的关联证据，不能据此断言 SpringBoard 等待的请求发到了死端口。H380 输出还出现 lsd_pid=1，这个标签不能作为 lsd 的实际身份。

远端 `/tmp/opencode/xnu-src/osfmk/ipc/ipc_port.c` 2414–2434 行显示 helper 默认返回 -1，仅对处在普通用户空间中的端口返回 task pid。它明确排除了 ipc_space_kernel 和 ipc_space_reply，因此 dst=-1 也可能对应内核服务端口。该源码是远端参考树，尚未通过构建记录证明与 H380 二进制完全一致。

对 H358–H380 已找到的 21 份文本日志使用修正后脚本复评，结果均为 CHECK。这个结果包含运行窗口不足、日志停写和日志写入丢弃等情况，不能等同于 21 次控制器故障。例如 H362 记录了 LOG_FAIL，H366 累计 errors=64，但当前 logWrite 在 IOLockTryLock 失败时也直接返回 false。需要将锁竞争丢弃与实际命令失败拆开计数，才能判断是否应继续修改 UFS 控制器。

目前优先执行顺序进一步收敛为：确认 H380 真实产物与配置，验证 launchd 代持的 rport=0x3a03 对应服务及其 check-in 生命周期，再选择有 lsd 非零线程的轮次关联请求。保留单核对照，并独立验证第一帧。暂停基于 dst=-1 改动死端口发送语义的方向。

## 进度判定

- 启动链、APFS、launchd 和部分用户态服务有历史成功记录。
- AppleKeyStore、容器链和显示客户端注册已有记录，完整桌面呈现尚未验收。
- UFS 已改善，但历史 PASS 的判定过宽。原脚本只检查最后时间戳、拒绝风暴和日志新鲜度，超时、恢复、写失败不影响结论，也漏计 STALL_NOPANIC。已修复这些判定，旧日志需要重新评估。
- SpringBoard 等待服务回复是当前候选阻塞链。根因仍待证实。lsd 空闲、q=0 和 so=1 的组合无法唯一确定请求被丢失，也无法确定等待的请求对象。
- H380 的 dst=-1 表示 helper 没有报告接收任务。确认死端口还需要同一次事件的 ip_active 状态及发送结果。当前树未包含该 helper 的 XNU 实现，不能直接确认所有返回 -1 的分支。

## 现有观测的局限

1. h103 的 native_xpc_note 记录所有进程最近 64 次发送，采样时只打印最后 16 条，且依赖 lsd 采样。没有事件时间、线程 ID、端口标识、发送返回值和请求关联键。记录中的目标不能直接当作 SpringBoard 正在等待的目标。
2. native_sb_send_n 与记录数组没有同步保护。端口锁只保护单个目标端口，不能保护跨端口的全局环。cpus=2 下存在并发覆盖及读取部分更新的风险。
3. 发送钩子位于 ip_mq_lock 后，记录的是发送处理阶段。最终是否入队、直接交付或失败需要另行记录。
4. 端口采样中的 queued 实际为队列非空布尔值，输出 q=1 不代表只有一条消息。队列、接收名和 send-once 数读取缺少同一端口锁下的一致快照。
5. assets/ref1-h358.toml 与 ref1-h347v.toml 均为 cpus=2，AGENTS.md 的基线为 cpus=1。h358 参数还关闭 gpu-addon 和 accelerator。该配置下的启动结果不能验收 Metal 渲染能力。

## 调整后的执行顺序

### 1. 固定产物和建立可重复启动基线

记录三个仓库及子模块提交、内核与 payload/boot 哈希、从实际 payload 提取的启动参数、Data 种子哈希及插件 build ID。外置 toml 与 payload 内置配置需要比较。

同一 H380 产物和 Data 状态至少重复三轮，记录 boot ID、日志区间、lsd exec、SpringBoard 等待端口、UFS 错误与显示提交数。对照实验保持 Data 初态可比，任何恢复写入仍遵守备份和授权要求。

先取得原 cpus=2 的重复性，再仅将 cpus 改为 1 做对照。检查修改后 payload 的 boot_args 长度。若单核稳定性改善，再审查 SMP、GIC、定时器与诊断共享状态。

### 2. 用证据闭合一次 IPC 请求

下一次内核诊断仅围绕按名称匹配的 SpringBoard 与 lsd。进程名在允许使用 proc_name 的层解析，生成当轮身份映射。

发送事件需要有单调时间、线程 ID、目标端口关联标识、active 状态、接收任务状态、消息 ID、回复端口关联标识和最终发送结果。关联标识必须考虑端口销毁后的地址复用。区分端口迁移/无接收空间、内核接收端口与失效端口。诊断结构需要并发保护，锁内只写有界数据，由采样线程输出。

同时记录匹配请求的接收事件及回复发送事件。仅当同一请求的发送、交付和回复关系建立后，才选择修复层。单个采样点的 q、so 和保存 PC 只作为辅助证据。

现阶段保留 XNU 的死端口发送语义。改变错误码前先验证调用方的清理、重连和重试行为。

### 3. 单独验收显示与渲染

保持服务启动基线，先做有明确标识的静态 IOSurface 显示实验，验证格式、stride、transfer、retire 和屏幕可见结果。再检查 backboardd 的真实提交，区分测试探针来源。

Metal 插件加载、pipeline 创建、命令提交、GPU 完成和最终 scanout 分别记录结果。当前关闭 GPU addon 的参数仅能覆盖其实际启用的显示路径。SpringBoard 能继续启动后仍需完成上述验收。

## 下一轮结束条件

产出同一配置三轮对照表，使用修正后的脚本复评 UFS，并拿到一条 SpringBoard 阻塞请求的可关联事件。根据结果选定存储、并发、服务初始化或 IPC 路径中的修复点。当前资料不足以确认“唯一主卡点”或宣布存储已完成。
