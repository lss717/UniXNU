# H389 CPU comparison / CPU 对照

## Evidence / 证据

- H389c2 changes only `cpus=1` to `cpus=2`; CPU rendering remains the goal. GPU addon and accelerator remain disabled.
- H389c2 只修改 CPU 数量，继续以 CPU 桌面为目标，不启用 GPU。
- Raw ring: `h103log-H389c2.bin`, 33554432 bytes, SHA-256 `2e8dd9d3a9bfb4455b544315357e6a98387488061b99b080f1a0089990a9800a`.
- All 247 valid slot stamps belong to boot `20ba4dfe`. Retained body timestamps are 771.3–903.5 seconds. These are a rolling window, not the whole boot duration.
- 247 个有效槽属于同一轮；正文保留 771.3–903.5 秒，不能把窗口长度当运行时长。
- No retained OCS timeout, recovery, refused block request or LOG_FAIL. Marker is alive; frame counters remain zero. LOG_STAT errors reach 74, so this does not establish lossless logging.
- 保留窗口内未见控制器超时、恢复、块请求拒绝或 LOG_FAIL；帧数仍为零。累计 errors=74，不能宣称日志无丢弃。

| Retained window / 保留窗口 | H389 cpus=1 | H389c2 cpus=2 |
| --- | --- | --- |
| Timestamped container entries / 带时间条目 | 33 in 1101.4–1244.6 s | 38 in 772.5–903.5 s |
| All distinct container identifiers / 全部不同标识 | 66 | 79 |
| Duplicate identifiers / 重复标识 | 0 | 0 |

The windows contain different packages at different boot ages. They cannot establish a CPU speedup. Both show ongoing initialization rather than a proven deadlock.

两个窗口的启动时段和包不同，不能由条目数量推算双核加速比；两轮均有初始化进展，不能认定死锁。

At 867.231699 s, lsd tid=506 has `st=0x9`, `cpu=74461`, PC `0x18a1282f0`, LR `0x18a1282dc`; its x0 probe starts with `bplist00`. State includes RUN and WAIT, consistent with a sampled wait transition, not proof of continuous execution. It contradicts the claim that every lsd worker is simply idle. Saved PC alone is not the current execution location.

867 秒的 lsd 线程状态包含 RUN 与 WAIT，可能处于等待转换，不能据此宣称持续运行。结合非零 CPU 值和不断新增的容器缓存，之前“所有线程都空闲”的说法不成立。保存 PC 本身不能证明当前执行位置。

Using the known libsystem_kernel text base `0x1cb77f000`, this boot's runtime base `0x1cdb33000` gives slide `0x23b4000`. PC and stack return addresses map to CoreServices using the existing cache segment map. Exact function symbolication remains pending; do not infer the specific parser or queue owner from the `bplist00` prefix.

使用已知缓存基址换算后，PC 与相关返回地址位于 CoreServices；具体函数待符号化，不能仅凭 bplist 前缀认定解析器或队列所有者。

## Next diagnostic / 下一步诊断

The kernel emits non-SpringBoard frame chains only when sample ID is divisible by 30. H389 used bases 7000 and 8000, so lsd and the first container instance never met that condition. Correct them to 7020 and 8010; retain the 60-second interval and all functional boot settings. This is an observation fix, not a desktop fix.

H389 的 lsd 与第一个容器实例编号不满足输出栈链条件，修正为 7020、8010，频率仍为每分钟一次。这是观测修复，尚未修复桌面。

Before another device run, symbolicate the retained CoreServices addresses and inspect the Data seed/cache initialization policy. Do not enable persistent Data writes without a verified backup and explicit authorization.

下一轮前先解析已有地址，并检查 Data 种子与数据库缓存初始化策略；持久化 Data 写入仍需备份与明确授权。

The Mac initially timed out, then became reachable after the user started it. Symbolication against the existing 21H461 cache resolves the sampled PC to `-[_LSDataBackedPropertyList prewarm] +196`; stack returns resolve to `-[_LSStringsFileContent prewarmAllLocalizationsWithBundle:forLocalizations:] +176` and `_LSStringLocalizerPrewarmAllLocalizations +76`. This is evidence of localization property-list prewarming during initialization, not proof of its total cost or the cause of all waiting clients. The rebuilt diagnostic kernel still needs device validation.

用户启动 Mac 后恢复连接。同版本缓存符号解析确认活跃线程位于属性列表预热，栈包含本地化字符串全量预热。此证据说明初始化在做什么，尚不能量化总耗时或解释全部客户端等待；修正后的诊断内核仍需真机验证。

## H389f candidate / 候选产物

Mac pulled `df1794a57` and initialized pinned submodules before building. Driver status was clean. Kernel build and prelink succeeded; the kernel extracted from the payload compares byte-for-byte with the build output. The payload is copied from H389c2, replacing only the kernel. Its internal build string remains H389; distinguish this run using its cleared ring, boot ID and artifact hashes. Boot arguments fit at 950/1024 bytes including worst-case zap-base.

Mac 拉取最新代码、核对子模块与源码状态后构建成功；包内内核逐字节校验一致。H389f 仅替换 H389c2 的内核，内部 build 字符串仍为 H389，须通过清零后的新轮次与产物哈希识别。启动参数长度检查通过。

- Kernel SHA-256: `73d4ccc26689df3f546669dd38b7d2d58ce84a6b876c8167b8d4fc052cf4a92b`
- Payload SHA-256: `1512ae1e8fadfdb3378838926a6cf032ed7743393e659a7acf23637333c025c6`
- Boot SHA-256: `0854bb6b933bca502efba37e1ec97685492dee2deff2b1f41654897df07572b3`

Device validation pending. Observe for approximately ten minutes and inspect late lsd frame chains, seeding progress and actual desktop frames; this image is diagnostic, not a claimed desktop fix.

待真机验证，观察约十分钟后检查 lsd 栈链、数据库初始化进展和桌面帧；此镜像是诊断修正，不能宣称已修复桌面。
