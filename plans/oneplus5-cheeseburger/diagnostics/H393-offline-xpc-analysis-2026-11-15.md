# H393 offline XPC analysis / 离线调用链分析

H392aw cache slide is 0x13c04000, derived from libsystem_kernel runtime base 0x1df383000 against known base 0x1cb77f000. SpringBoard main tid292 frames resolve to synchronous NSXPC invocation. Port samples 6000/6030/6060 consistently identify req=0x7403 and peer=91/lsd, q=1 (queue nonempty, not a message count). Existing eight-frame limit ends at Foundation sendSelector, before the caller specifying the application request, so the exact selector cannot be inferred from these records.

主线程同步等待lsd的证据连续成立，但八层栈被截断在通用XPC发送层，无法从现有现场推出具体selector。

lsd tid605 at sample7020 is a separate synchronous RPC, not idle. Frames +0x17c24/+0x17f54/+0xb1cc map to libmis. Disassembly of unslid 0x1dd9eeb9c loads service string at 0x1dd9f3d2d: com.apple.online-auth-agent.xpc, and calls through libxpc (stub GOT target maps to libxpc+0xdcf0). The same sample's port record confirms rport0x7803 -> pid119/online-auth-agen. This closes service identity using both static and runtime evidence. Thread605 is absent from the two later recorded thread lists (lsd n=4), so this sample does not establish a persistent auth-agent deadlock. No reason to disable this service was found.

反汇编与同轮端口记录共同确认libmis正在请求online-auth-agent。该线程后续未被列出，不能称为永久阻塞，也不能据此禁用服务。

lsd's main remains in performJournalRecovery waiting on a dispatch queue. Two workers wait on the same seeding group via LSDatabaseBlockingFetchClient and restoreInactiveInstalls. CoreServices createAndSeedLocalDatabase dispatches a rebuilding block using LSDBExecutionContext syncWrite. The completion block invokes setSeedingComplete, which clears seeding-in-progress, marks seeded/completed, commits and saves immediately. Current logs capture waiters, not the rebuild block reaching or failing to reach completion.

数据库完成路径已定位，但日志仍未捕获真正的重建任务如何退出；不能通过强设完成标记掩盖未完成的注册。

AW fixup source applies only after successful page signature validation, with matching vnode name, file page range and original bytes. native-skip-exec-signature clears exec MAC/reason failures; it does not itself remove this page-validation hook. No application record survives in H392aw, so parse/application counters are needed rather than assuming success or failure.

AW规则须满足页面校验及名字/偏移/字节匹配；exec逃生参数本身不等于跳过该钩子。缺失日志不能判断应用结果。

H393 changes diagnostics only: SpringBoard and lsd frame limit 8->24, other processes remain8; existing low-frequency Data status now includes text=parsed/applied. H392aw's actual ADT, seed and functional boot arguments must remain unchanged. This enables the next sample to expose the actual caller/initializer chain and validate the fixup, without modifying IPC, scheduling, Data writes or database completion state.

H393仅补观测，保留AW对照参数，不改功能行为。根因尚未确定。

Mac pulled da82c0ae9 and device b99e798 before building, with clean tracked driver sources (untracked Python cache retained). Kernel build/prelink passed; applied task.c contains the 24-frame loop. Both cs_text_fixup counters are present in the linked kernel. Actual payload kernel equality and boot-argument check passed, 990/1024 worst case. Built from H392aw payload, preserving its ADT and arguments. Device result pending.

构建与实际产物检查通过，保留原对照功能参数；真机结果待验收。

- Kernel: f9393e30176bebaad0e89d398e20e0be987eb85af28072067fe6342d1d6d9f79
- Payload: 2543565d13ee6ab9c04f632a08392788cba91f4e45276a6204e93f51ccff50d1
- Boot: 290d2cfaca0a244d892a4ed7427c1e59f90490827f20c1b2ff9d39b3300226d4
