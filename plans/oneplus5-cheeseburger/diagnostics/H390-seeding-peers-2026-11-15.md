# H390: database seeding peers / 数据库初始化服务

H389f raw ring has one boot ID `220ce7d8` across 247 slots; retained body timestamps are 520.7–671.4 seconds. Frames remain zero. No retained controller timeout, recovery or refused block request; one LOG_FAIL exists at 618.47 seconds and log errors reach 66. PerfPowerService crashes at least twice in the retained window. Do not describe the boot as error-free.

H389f 单轮日志保留 520.7–671.4 秒，桌面帧数为零。未见控制器超时、恢复、块请求拒绝；有一次 LOG_FAIL，累计 errors=66，PerfPowerService 至少崩溃两次，不能称本轮完全稳定。

The corrected frame sampler worked. Both 545 and 620 second samples show lsd pid=93 main thread tid=500 in `_dispatch_sync_f_slow` through `performJournalRecovery` and `beginListening`. Threads 641 and 668 wait on the same dispatch group in database seeding / restoreInactiveInstalls. This identifies waiting callers, not the owner performing seeding, and does not establish deadlock while container paths continue to change.

完整栈链修正生效。两次采样主线程均经 journal recovery 等待同步队列；两个工作线程等待同一初始化组。它们是等待者，尚未找到初始化执行者，不能在容器路径仍变化时认定死锁。

The sampler currently selects only the first process matching lsd. H390 adds ordinal 1 for lsd and an installd sample to the same once-per-minute late pass, with IDs divisible by 30. Ordinal does not imply user identity; report the discovered PID each pass. An absent second lsd is a valid negative result. This is a diagnostic change, not a functional desktop fix. Existing rendering, CPU and launch-job arguments stay unchanged; persistent Data writes are not enabled.

H390 在原每分钟一次的后期采样中补充第二个 lsd 实例和 installd，编号均满足输出栈链条件。实例顺序不代表用户身份，以每次输出 PID 为准；第二实例不存在也是有效结果。功能参数保持原样，不启用持久化 Data。这是观测改动，尚未修复桌面。

Before building, pull the committed source and pinned submodules on Mac and check driver status; verify prelink, changed kernel hash, payload kernel equality and argument length. Before boot, back up and clear only the authorized 32 MiB log ring. Use fastboot boot only. Observe approximately ten minutes to retain two or more complete late passes.

构建前拉取并核对代码及子模块，检查 prelink、内核哈希、包内内核一致性与参数长度。启动前备份并清零已授权日志区，仅临时启动，观察约十分钟。
