# D-IO1：存储读超时是所有长跑观测的共同阻碍（2026-11-12）

> 独立诊断项。它不属于 C6a 显示链，但**决定了显示链能不能被观测**：
> 2026-11-12 的 6 次上机里，有 4 次在拿到探针数据之前就被 I/O 崩塌带走。

## 1. 现象（已证实）

### 1.1 屏幕（panic 文本，2026-11-12 一轮实测照片）

```
_nx_buf_bread:628: disk4 buf_blowait() failed, error = 60, b_error = 60,
    buf_flags_after_io = 0x101, crypto = {unencrypted }, get_blk_err = 0, buf_valid = 0
_vnode_dev_read:907: disk4 ### got err 60 reading blknum 339254 (num read errs: 51)
apfs_slurp_file_data:3237: disk4s1 Cannot read 16384 bytes from LBA 339254 — Operation timed out(60)
apfs_collect_hash_records:229: disk4s1 Cannot find data hash record for offset 58002176
    of data stream 74 — Input/output error(5)
apfs_nstream_read:805: disk5s1 namedstream ### obj-id 1152921500312157033/... retval 60
    filesize 154217 offset 154167
panic(cpu 0 caller 0xfffffff007a5f05c): initproc exited —
    exit reason namespace 2 subcode 0xa description: none
MACH Reboot
```

**链条（已证实）**：UFS 读超时 `err 60`（累计 **51 次**）→ APFS 读不到数据哈希记录 →
`EIO 5` → **launchd（initproc）退出** → `panic: initproc exited`。

注意 `crypto = {unencrypted}`、`get_blk_err = 0`、`buf_valid = 0`：不是解密失败、
不是块设备返回硬错误，而是**等待超时**（`buf_blowait`）。方向指向 UFS 请求完成
路径的延迟/丢完成，而不是介质损坏。

### 1.2 运行窗口（已证实）

| 轮次 | 日志最后时刻 | 结束位置 | 备注 |
| --- | --- | --- | --- |
| H272d 第 1 轮 | **157 s** | `NATIVE_IOGPU_PUBLISH` → `NATIVE_FRAME event=1 frames=0` | 无 panic 文本可查（ring 先停） |
| H272d 第 2 轮 | 341 s | 正常 | `disp#` 为 0 是**探针调度问题**，不是 I/O |
| H272e | **209 s** | `IOMFB_FDR_Loader` 打开 `NativeLegacyDisplay` | 老位置 |
| H272f | **190 s** | `NATIVE_WAIT: pid=0 comm=kernel_task` | |
| H272b | ~216 s | 同上 `IOMFB_FDR_Loader` | |
| H269（历史） | 590 s | 正常 | 同一镜像曾跑满 |

**统计（强推断）**：成功率约 1/3，失败窗口集中在 **157–216 s**，且与"跑了多久"
无关——H269 那次同内核跑到 590 s。说明这不是固定定时器，而是**间歇性 I/O 事件**。

### 1.3 与显示链的关系（已证实）

连续三轮（H272d/e/f）的探针**都排在 Metal 设备初始化之后**，而设备初始化发生在
**213–289 s**，正好落在死亡窗口内或其后——于是"没有 disp# 行"混合了两种原因：

1. 真·探针未被执行（调度点太晚）；
2. 系统已经死在 I/O 上。

**结论：不解决观测窗口，显示链的结论会被系统性污染。**

## 2. 影响（已证实）

- 任何依赖 **>210 s** 的观测（SpringBoard 活动起点 ~190 s、scene latch 的 burst 1+、
  `NATIVE_SBPC` 慢序列、显示探针）都处于**抽奖**状态；
- 每次失败要重刷一次镜像（约 4 分钟），实验成本翻倍；
- 更容易被误读成"探针坏了/功能没实现"——H272d/e/f 三轮都发生过。

## 3. 待确认项（下一批观测的判据）

| 编号 | 问题 | 观测手段 | 判据 |
| --- | --- | --- | --- |
| D-IO1-a | 超时是"偶发丢完成"还是"特定 LBA/流" | ring 日志里统计 `got err 60` 的 blknum 分布 | 集中在少数 blknum → 介质/映射问题；分散 → 完成路径延迟 |
| D-IO1-b | 是否与并发深度/队列深度相关 | 对比 `cpus=1` 与历史 `cpus=2` 的失败率 | cpus=1 明显更好 → 并发竞争 |
| D-IO1-c | 是否与我们的 UFS 探测驱动（NativeUfsProbe）采样有关 | 跑一版**不带探针**的内核，看失败率 | 失败率显著下降 → 探针干扰 I/O 路径 |
| D-IO1-d | 超时阈值在哪 | `buf_blowait` 的超时值 + UFS 命令超时配置 | 记录数值，再决定是否调 |
| D-IO1-e | launchd 退出是否可避免 | 退出码 `namespace 2 subcode 0xa` 的含义 | 若 APFS 侧可重试，则不 panic |

## 4. 建议顺序（成本从低到高）

1. **离线**：把已收集的 6 份 ring 日志全部扫一遍，统计 `err 60` 的出现次数与
   blknum、以及每次运行的前 5 个错误时间点 —— 零上机，先做 D-IO1-a；
2. **对照**：一版 `NATIVE_UFS_PROBE` 关闭的内核（只改 defconfig/boot-arg，
   已有开关 `native-ufs-probe=0`），对比失败率 —— 判定 D-IO1-c；
3. **只在需要长跑时**：把探针全部前移到 **<150 s**（H272f 已开始这样做），
   把长跑需求本身降下来，而不是等 I/O 修好。

## 5. 与 C6a 的关系

- 本项**不阻塞** C6a 的结论，但阻塞"长窗口观测"这一类实验；
- 规则：**任何 >210 s 的观测结论都必须标注本轮实际运行时长**，
  否则无法区分"没有观察到"和"没跑到"。
