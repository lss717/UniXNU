# H394 kernel-object lock / 内核对象锁

Goal remains first real desktop frames with CPU rendering. No persistent Data writes or new functional bypasses.

主线仍为CPU首次桌面出帧，不扩展Data写回或功能绕过。

H393 lsd tid515 at344s is opening /Applications/PaperBoard.app/PlugIns with wait event0xfffffff007bc6849. Linked H393 kernel's kernel_object_default constant contains0xfffffff007bc6840 (read from the Mach-O segment, not guessed from the nearest symbol). vm_object.o DWARF places vm_object.Lock at offset8; lock_rw.c defines LCK_RW_WRITER_EVENT(lock) as lock+1. Thus this exact wait event is kernel_object_default->Lock's writer event. This identifies a sampled contended lock, not a proven permanent deadlock or the root cause of the entire boot. The subsequent container records indicate other initialization progress.

通过实际内核常量指针、DWARF字段偏移和锁源码三方对应，确认该次采样等待kernel_object写锁。不能由一个快照认定永久死锁。

H394 adds a read-only snapshot before each existing late sampler pass: object/event addresses, atomic raw lock word and owner compact ID. It uses task_lock_try on kernel_task; only if acquired does it inspect up to1024 kernel threads, copy a matching thread's stable scalar identity/state/wait/continuation and release the task lock before printing. It never locks the contended vm_object, dereferences ctid_get_thread, wakes a thread or changes lock state. Separate fields can change during the snapshot; a missing match can mean transient owner, a non-kernel-task owner, busy task lock or scan limit. Shared-mode locks may have no exclusive owner.

快照只读、不获取争用锁，不通过可能回收的ctid直接解引用线程；线程列表只尝试锁且有扫描上限。未匹配持有者不等于持有者不存在，各字段不是原子事务。

An initial one-context patch was rejected by plain git apply --check before compilation. Replaced with full context in240c83178; plain check then succeeded. Build candidate must use this commit or later, preserve H393 ADT/arguments/seed, and pass prelink plus changed kernel/payload checks. Runtime owner evidence remains pending.

初版补丁在编译前被普通检查拦住，补齐上下文后通过；后续产物须验证实际构建版本，真机锁持有者待确认。

Mac build/prelink passed at240c83178 with device b99e798. Linked kernel exports native_kernel_object_sample. Kernel changed from H393, extracted payload kernel compares equal, and actual args pass990/1024 worst-case. Payload clones H393, preserving CPU route, AW ADT rule, Data seed and USB argument. Device result pending.

构建及包内校验通过，功能参数不变，真机结果待验证。

- Kernel: 6d1fbc09742a11ff376b9cf76e8cfa3de5d5ed1474df778ecb4bd6e3b6415e24
- Payload: 2b25f0845c62c7776c1e857873f3ca17322b8bb2052fefd8cc6a7743289f23cf
- Boot: e497d32d3e69ed65da1cda309ab1be3bfa656205e6a96470c554fc7e08b348b0

The completed long run retained665.6--807.9s and stayed alive with zero frames. At685.528s and754.880s the snapshots were identical: `object=0xfffffff007bc6840 event=0xfffffff007bc6849 word=0x420000 owner_ctid=0`. The low16-bit shared-reader count is zero, and no writer/upgrade waiter bit is set. H393 therefore captured transient contention, not a persistent `kernel_object` lock owner; forced unlock is rejected.

SpringBoard still synchronously waited for lsd, while lsd had an active worker and new application/plugin container records continued through800s. The desktop gate is now the very slow LaunchServices system-content scan. H395 stops periodic kernel-object sampling and measures lsd `vn_open_modflags` latency: 50ms slow rows include path/error and are bounded to96, while every256 opens reports total count, slow count and maximum latency.

长时间真机结果排除了`kernel_object`长期持锁。LaunchServices仍在推进但速度异常，H395转为量化lsd打开路径的耗时与总量，不做强制解锁。
