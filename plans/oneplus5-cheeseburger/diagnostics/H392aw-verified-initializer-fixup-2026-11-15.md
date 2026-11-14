# H392aw verified initializer fixup / 初始化修正对照

The actual H392 ADT has no chosen/text-fixups. Same-profile merlinx board.toml includes the upstream sheng da9fab9 AW initializer repair. The original 21H461 SystemOS cache file dyld_shared_cache_arm64.15 at offset 0x421e8bc contains 28ad1bb0008544f9, verified read-only on Mac. Extracted AttentionAwareness disassembly resolves this to +[AWAttentionAwarenessConfiguration initialize], whose body tail-calls initializePreferences. These establish applicability of the original-byte guard, not proof that our current LS waiting chain is the AW deadlock.

实际ADT缺失该规则；同配置merlinx使用上游AW修正，已核对原始缓存字节与函数。此证据确认规则可匹配，不证明当前LS等待就是AW互锁。

Device commit b99e798 adds one payload.text_fixups rule. Mac pulled main 42f9e9111 and device b99e798 before packaging. H392aw clones actual H392 payload and changes only chosen/text-fixups in its ADT. Original ADT roundtrip was byte-identical; removing the added property from the result reproduces the original exactly. Kernel compares byte-for-byte with H392; CPU rendering, cpus=2, Data seed, sheng-data-persist=1, cheeseburger-usb=1 and all boot arguments remain unchanged. Worst-case args 990/1024. No new kernel compilation is needed for an ADT-only change. Internal build string remains H392; identify the run by boot ID and hashes.

只修改实际payload内ADT，内核及功能参数不变。已验证ADT其余内容逐字节一致、包内内核一致及参数长度。内部标识仍为H392，通过轮次与哈希区分。本轮不写Data区域。

- Kernel SHA-256: 13b330dac4c288511a1d08dc9fe47b91b7a991217dd1b85c009806fb3ffc723a
- ADT SHA-256: e9728a1a035a010aff1596bccf46a765f948bd2afd9d383f8b28630217ba4f9f
- Payload SHA-256: 6a95c64dd616795ff48fb4a22509d309c9e1c0f87ffa1e787c9f99d02e7df668
- Boot SHA-256: 87e4ad9f3735213333703fb4139ff09d381a1175d2fec502e08cad735af68ba0

Device validation pending. Look for text-fixup applied output and changes in SpringBoard/lsd wait chains and val/xf/fr. A missing application record is not evidence that the patch failed: the ring or validation path may omit it. Do not claim a desktop fix without actual frames.

真机待验证，检查规则应用、等待链和真实帧；未见应用日志需区分覆盖与校验路径，不能直接判定成功或失败。
