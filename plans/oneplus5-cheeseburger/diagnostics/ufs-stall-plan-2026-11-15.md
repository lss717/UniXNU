# UFS 卡死治理计划（2026-11-15，H359 之后）

## 1 现象与责任归属

H358 打开 AppleKeyStore 后系统明显走得更远（keybagd/containermanagerd 终于匹配到
`AppleKeyStore`，backboardd 线程到 5 个，`dpy=2/11`），但磁盘负载随之上升，暴露了
`drivers/NativeUfsProbe` 自己的三个结构性问题：

| # | 我们的做法（现状） | 后果 |
| --- | --- | --- |
| 1 | `ufsSubmit()` 提交后**轮询**等完成，调用者持有块请求 | 一条慢命令吃掉整个请求的时间预算 |
| 2 | `ufsCommand()` 在 `UTRLDBR != 0` 时**直接拒绝**新命令 | 一条卡住的命令让后续 I/O 全部 `request failed to start!` |
| 3 | 一次 OCS 超时 `q->poisoned = true`，所有后续命令立刻 EIO | APFS page-in 失败，进程被杀 |
| 4 | 重试路径 `ufsCommandRetry()` 对**写**也重发 | 失败写重放会破坏数据 |
| 5 | 持久日志 slot 写入走**同一个 UFS 队列** | 队列一堵，停机记录也写不进去（`NATIVE_UFS_SLOT … fires=0`） |
| 6 | 10 秒看门狗直接 `panic()` | 把本可自恢复的启动打死（已改为 60 秒） |

结论：**根因在我们，属于实现方式欠债，不是本轮新引入的 bug**。H290/H323 的注释里早就记过
"doorbell 未清即拒绝 → EIO → page-in 失败 → 进程被杀"和"一次超时毒化整个 boot"。

## 2 参考实现

### 2.1 同路线完整实现（`/tmp/opencode/sagit-ios-port/docs/ufs.md`，SDM845/835，iOS 18）

可直接借用、且正好对上我们痛点的条目：

- 「使用 CAP 发现并使用全部硬件槽，最多 32 个，按 LUN 的队列深度限流；支持乱序完成。
  **UTRLDBR 只写新请求的单个 W1S 位**，避免用过期 doorbell 值重发已完成的写入。」
- 「**中断负责正常完成，10 ms watchdog 同时按 doorbell 回收丢失 IRQ 的完成**并检查 30 秒请求期限。」
- 「错误响应、链路/总线错误或超时会**关闭 admission**，停止控制器并确认 HCE disable，
  然后失败完成请求。**不会重放失败的写操作**。」
- 「无法确认 DMA 静止时 panic，不能释放仍可能被 DMA 写入的调用方内存。」
- 「UTRD/UCD/UTMRD 使用独立、常驻映射的无缓存内存，避免两个 32 字节 UTRD 共享 cache line
  时的回写/失效竞争；数据缓存同步在提交前和完成后进行。」
- 「DMA 准备在调用线程执行；异步请求移交 thread_call 准备；DMA 解除映射、complete 和
  客户端回调在 gate 外执行。」
- 「SYNCHRONIZE CACHE 实施控制器级顺序屏障；FUA 转 SCSI FUA；短传输不报完整成功。」
- 失败的边界：本版**保持 offline**，不自动重建控制器（明确划出"不做什么"）。

### 2.2 Linux `ufshcd`（GitHub `torvalds/linux` 主线）的对应机制

- 正常完成走中断；轮询只用于错误路径。
- 有专门的 **doorbell timeout** 判定：门铃写入后控制器没有消费命令，视为 DB timeout。
- 错误处理是**分级升级**：abort task → LUN reset → host reset（`ufshcd_reset_and_restore`）。
- 上游已知坑：任务管理命令本身超时会把恢复流程带死（lkml "Fix UFS task management command
  timeout"），所以恢复不能依赖 TM 命令。

**差异总结**：参考实现是"多槽 + 中断 + 10 ms doorway 回收 + admission 关闭"，
我们是"单槽 + 轮询 + 拒绝 + 毒化"。计划就是把我们往前者靠，但不要求在一步里做到中断驱动。

## 3 分阶段计划

### 阶段 A：止血（改动小、当天可验证）

| 步骤 | 改动 | 文件/函数 | 验收 |
| --- | --- | --- | --- |
| A1 | 持久日志在 UFS 忙时**直接丢弃，不重试**，且不进入数据 admission | `h103FlushNow()` / `h103SlotTick()` 调用点，`NATIVE_UFS_SLOT` 分支 | 日志不再出现 `attempt=5 … fires=0`；停机仍能靠保留块判定 |
| A2 | **写操作永不重放**：`ufsCommandRetry()` 只对读重试，写失败即失败 | `ufsCommandRetry()` | 代码审查 + 失败写路径日志 `NATIVE_UFS_WFAIL` |
| A3 | doorbell 改为 **W1S 单 bit**：`write32(UTRLDBR, 1u << slot)`，不再写常量 1 | `ufsSubmit()` | 同一 boot 不出现"已完成的写被重发" |
| A4 | 去掉 `read32(UTRLDBR) != 0` 的一刀切拒绝，改为**按槽位**判断占用 | `ufsCommand()` / `ufsWriteCommand()` 入口 | 不再出现连续 `request failed to start!` |

A 阶段不改完成模型，只把"一堵就全堵"变成"堵一个槽"。

### 阶段 B：完成模型（核心）

| 步骤 | 改动 | 验收 |
| --- | --- | --- |
| B1 | 引入 `struct UfsSlot { tag, inUse, startTicks } slots[32]`，提交进不同槽位，按 CAP 的槽数上限工作 | 多请求并发时槽位不冲突 |
| B2 | **10 ms doorbell 回收**：扫描 `UTRLDBR`/`IS`，槽位 bit 已清→正常完成；10 ms 仍置位→判 DB timeout | 单条命令的最坏等待从 10 s 量级降到 10 ms 量级 |
| B3 | 超时/链路错误：**关闭 admission** → HCE disable → 确认 → 清 `UTRLDBR` → 失败完成该请求；用现有 **NOP OUT** 探测通过后再开 admission | 一次超时只影响一条请求，后续请求在恢复后继续 |
| B4 | 30 秒总期限（按请求），到期限则按 B3 失败完成，绝不无限挂 | 不再出现"请求持有超过 60 秒" |
| B5 | 缓存一致性：UTRDL/UCD 各自独占 cache line（64 字节对齐），提交前 clean、完成后 invalidate；数据在提交前/完成后同步 | 消除短传输读到旧数据的风险（参考 2.1 的 `__ARM_COHERENT_IO__` 教训） |

### 阶段 C：结构（可以与 B 并行验证，但落地晚一步）

| 步骤 | 改动 | 收益 |
| --- | --- | --- |
| C1 | UFS 命令执行搬到**专职工作线程**，块请求只做入队；`complete()` 在 gate 外调用 | 慢命令不再持有块请求，`gWindowInFlight` 不再代表"磁盘卡死" |
| C2 | 发布 `IOMaximumBlockCountRead/Write`、`IOMaximumSegmentCount*` 等属性，让 IOStorageFamily 按我们的能力拆分 | 单请求更小，锁持有更短 |
| C3 | 用中断（PPI 3 / INTID 19，参考 2.1）替代轮询作为正常完成路径，轮询只保留在错误路径 | 与参考实现同构，CPU 占用下降 |

## 4 观测与判定

新增/沿用计数（打印在 `NATIVE_UFS_ALIVE` 与保留块标记里）：

- `dbTimeouts`：doorbell 10 ms 未消费次数 → 若常态 >0，说明控制器/时钟层还有问题；
- `recovered`：B3 恢复成功次数；
- `failedReads` / `failedWrites`：失败完成计数（写失败必须为"失败即停"，不允许重放）；
- `admissionClosedSeconds`：admission 关闭累计时长；
- 保留块标记新增 `ufsstall` / `ufsrecover`，保证"日志写不进去"时仍有记录。

**通过标准**：在 `sheng-aks-publish=1` 基线下连续 10 分钟不出现
`IOBlockStorageDriver … request failed to start!` 风暴、无请求持有超过 30 秒、
持久日志环持续可写。

## 5 明确不做的事

- 不自动重建控制器后重放**写**（参考 2.1 明确"本版失败后保持 offline"）。
- 不在无法确认 DMA 静止时释放调用方内存。
- 不在 B/C 未验证前改动用户态（SpringBoard/backboardd 侧已查明，等存储稳定后再回去）。
- 不把 `dma-coherent` 一类属性当作绕过缓存问题的办法（参考 2.1 的结论）。

## 6 与既有结论的关系

- H358 证明 AKS 必须保留（`sheng-aks-publish=1`），它是 keybag/容器链的入口；
- H359 证明"日志与数据同队列"会先于一切失效，所以 A1 排在最前；
- 用户态因果链（SpringBoard → backboardd system shell → launchd user session）已查清，
  存储稳定后应回到这条链继续推进桌面。
