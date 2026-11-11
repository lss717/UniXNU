# 构建环境与启动约束（H236ck–H236cm，2026-11-10）

这份记录只收“会重复踩”的坑：每一条都对应一次真实的失败和一次已经验证的修正。
构建顺序、打包和安全约束仍以 `AGENTS.md` 与 `STATUS.md` 为准。

---

## 1. macOS 内核构建脚本

`~/run-h103n-build.sh` 现在是仓库内 `scripts/macos-build-kernel.sh` 的安装副本，
旧脚本备份为 `~/run-h103n-build.sh.bak-20261110`。

脚本自动决定 bootstrap 还是复用：

- `.cache/xnu-work/.git` 不存在，或 `bsd/kern/kern_exec.c` 不含补丁标记
  `H82_DATA_WAIT` → 删除并重新 `git clone --shared refer/xnu`，
  然后 `XNU_SKIP_PATCH_LOOP=0` 完整打补丁；
- 否则复用已打补丁的树，`XNU_SKIP_PATCH_LOOP=1`。

### 坑 1：未打补丁的新树 + `XNU_SKIP_PATCH_LOOP=1`

H236ck 时为了应用新补丁删除了 `.cache/xnu-work`，但 wrapper 仍然
`export XNU_SKIP_PATCH_LOOP=1`。结果是新 clone **一个补丁都没打**，
编译报出一堆看似“源码坏了”的错误：

```text
osfmk/arm/pmap/pmap.h:476:7: error: duplicate member 'reserved10'
bsd/net/necp_client.c:71:10: fatal error: 'CodeSignature/Entitlements.h' file not found
```

这两条都是**未打补丁的基线源码**在新 SDK 下的表现，不是补丁冲突。
判断方法：`grep -c H82_DATA_WAIT .cache/xnu-work/bsd/kern/kern_exec.c`
应为 1。

修复：`bash ~/run-h103n-build.sh --clean`（完整重新 clone + 打补丁），
日常增量构建直接 `bash ~/run-h103n-build.sh`。

### 坑 2：Xcode 26.2 不再带 `availability.pl`

```text
Unable to locate /Applications/Xcode.app/.../iPhoneOS26.2.sdk//usr/local/libexec/availability.pl
make[5]: *** [_symbol_aliasing.h] Error 1
```

`bsd/sys/make_symbol_aliasing.sh` 需要 SDK 的
`usr/local/libexec/availability.pl`；Xcode 26.2 的 SDK 已删除该文件。
`_symbol_aliasing.h` 只依赖 XNU 自己的头文件，所以脚本在没有
SDK / `.cache/fakeroot` 副本时，保留上一次构建生成的
`build/xnu/ios-obj/bsd/sys/_symbol_aliasing.h` 并 `touch` 到比
生成脚本新，从而跳过重新生成。

注意：这个 `touch` 必须发生在 clone 之后（clone 会刷新生成脚本的
mtime），所以脚本自己先 clone，再回退。

---

## 2. 内核窗口基址必须带 2 MiB 内的 0x4000 偏移

XNU 的 `start_first_cpu` 用 2 MiB block 建初始页表，要求
**物理基址**与 Mach-O `__TEXT` 虚拟地址在 2 MiB 内的偏移一致
（`__TEXT` 是 `0x...4000`）。

- 错误：窗口放在 `0xA0000000`；
- 正确：`0xA0004000`（= `ALIGN_VALUE(base, 2 MiB) + (Kernel->Base & (2 MiB - 1))`）。

症状：内核执行到 `msr SCTLR_EL1, x0` 之前（品红带）后完全静默，
`arm_init` 从不执行；入口复位探针 `--reset-at _arm_vm_init` 也不触发。

H236cj 验证：把 `AllocateWindow()` 的固定候选也加上该偏移后，
`_arm_vm_init` 入口的复位探针**立即触发重启**，问题消失。

---

## 3. sidecar（ramdisk/addon/policy）必须留在内核窗口内

`osfmk/arm64/arm_vm_init.c` 直接用 boot_args 设置物理范围：

```c
gPhysBase = args->physBase;
gPhysSize = ((gPhysBase + args->memSize) & ~PAGE_MASK) - gPhysBase;
```

现在 `physBase=0xA0004000`、`memSize=192 MiB`，所以内核管理的物理范围
只有 `0xA0004000–0xAC004000`。`NativeRamBlock::start()` 会拒绝范围外的
ramdisk（`physical < gPhysBase || ... || physical - gPhysBase > gPhysSize - bytes`）。

H236cc 曾把 ramdisk 放到低 4 GiB（约 `0xF9xxxxxx`），于是：

```text
NATIVE_H82_DATA_WAIT: 550
NATIVE_H82_DATA: status=2 stage=0 ro=-1 dev=-1 size=0
panic(cpu 0 ...): offline scratch Data mount failed: 2 @kern_exec.c:8688
```

等 55 秒也等不到卷，因为驱动根本没接受 seed，不是时序问题。

修正：192 MiB 窗口时 sidecar 放窗口内（H236bw 的行为，`Used` 约 96 MiB，
放得下）；只有 192 MiB 分配失败、回退 128 MiB 时才用低 4 GiB 布局。
H236cl 已按此改回。

配套的内核侧修改：`native_owner_data_prepare()` 对 seed 卷做有限重试
（600 × 100 ms），避免 load_init_program 早于 NativeRamBlock/APFS 发布
（旧日志：load_init_program ~20 s，NativeRamBlock online ~33 s，
Data 卷发布 ~37 s）。重试只是保险，范围检查才是硬约束。

---

## 4. 日志与照片判读

- h103 ring 从约 30 秒才开始写（`NATIVE_BUILD` 那一行的时间戳）。
  20 秒前的探针/panic 不会落库，别再指望从 `userdata_ios` 拉早期日志。
- H236cc 的照片只截到屏幕中段，顶部 1/16 的绿条和探针 band 1 都不在画面里，
  差点得出“XNU 没执行”的错误结论。凡是要看颜色带，必须拍**完整屏幕**。
- 入口探针默认把 stage 1 放在 band 1（顶部第二格），容易被裁掉；
  用 `--band 8` 放到屏幕正中。

---

## 5. 生成的脚本目录不是软链

`out/cheeseburger/tree/scripts/` 是 `unixnu defconfig` 时**复制**的。
改了 `../UniXNU-cheeseburger/scripts/patch-xnu-entry-probe.py` 之后，
要么重新 `./unixnu defconfig cheeseburger_defconfig -D ../UniXNU-cheeseburger`，
要么手动把脚本复制进 `out/.../tree/scripts/`，否则运行的是旧版本
（H236cj 的 `--band` 一开始就是这样“不存在”的）。

---

## 6. 入口探针工具的两个修正

- 本内核 `_start` 之后的固定 padding 已被占用，工具现在会在同一
  file-backed segment 里向后找全零区，并保证每个 stage 用不同的 cave；
- `--band N` 可把 stage 1 的色带放到指定 1/16 带（8 = 屏幕正中）。

---

## 7. 本轮产物

```text
firmware 5a728a3e9c99807367ec94c9d680210c600ab5d1d4bdf5cb7c9aa2336694e36c  (192 MiB + 窗口内 sidecar)
kernel   ce7d7bb6cdbbe9a3cd0de06f4c53a7b4c6e909ee00ad21a07f0bd1cec0f45f72  (Data wait + ready/bytes 诊断)
kernel   c3fd801369ac3e2ee89bdd09ae4ffbca1775b4cdb852aa4732b6892039376f0e  (Data wait，无 ready 诊断)
boot     d444465f9cc87dde28b10064109e7387954118a592b4a3856a623abb2d0d15b9  boot-H236cm.img
boot     af2f54bd87a1f38f9af732e7460aedf908822f618f7989bbb116e20b3b8383f6  boot-H236cl.img
```

---

## 8. packed ramdisk 的长度必须精确（H236cn）

`NativeRamBlock::ramPackedLayout()` 最后要求 `cursor == n`：传入的字节数必须
**正好等于** DBRDISK1 的编码长度。窗口内布局原来按页对齐：

```c
RamdiskBytes = ALIGN_VALUE (KeepPacked ? Request->RamdiskSize : RamdiskExpandedSize, EFI_PAGE_SIZE);
```

3,219,600 → 3,223,552，`ramPackedLayout` 失败 → `NativeRamBlock::start()`
返回 false → `ready=0` → `native_owner_data_prepare` 等到超时后
`offline scratch Data mount failed: 2`。

修正：packed seed 用 `Request->RamdiskSize` 原样传递，只有 dense 才页对齐；
`TrustCacheAddress` 单独 `ALIGN_VALUE(..., 16 KiB)`。

## 9. 内存预算：不要把 `boot_args->memSize` 当成窗口大小（H236cp/cs）

三处叠加造成了内存回归：

1. `WindowSize > 192 MiB` 被砍到 192 MiB（`board.toml` 要的是 4 GiB）；
2. `Used` 检查；
3. 临时的 512 MiB `ManagedSize` 上限。

`H236co` 的 `memorystatus_jetSam_thread: no victim available pages:2306`
就是 H78/H103ay 那个 jetsam 问题回来了：XNU 只管理 192 MiB。

约束与修正：

- `arm_vm_init()` 用 `gPhysBase = args->physBase`、`gPhysSize = args->memSize`，
  并且只把 **`[topOfKernelData, gPhysBase+memSize)`** 当空闲页；
- 因此 `TopOfKernelData = Address + WindowSize`（把整个窗口保留），
  `MemorySize = MemorySizeActual = ManagedSize`（窗口所在的连续 DRAM run 末尾 − Address）；
- `ManagedEnd` 必须只取**紧贴窗口结尾**的那个 conventional run；取“最大的
  conventional 末尾”会选中 4 GiB 以上的高内存（8 GB 机器），把含空洞的
  7 GiB 范围交给 XNU，内核在 console 之前挂死（H236cp 绿条卡住）；
- ZAP 放到窗口顶部（`TopOfKernelData` 覆盖它），并且必须**向下**对齐：
  `ALIGN_VALUE(Address + WindowSize - 2 MiB, 1 MiB)` 会向上取整到窗口外
  （0xABF00000..0xAC100000），要用
  `(Address + WindowSize - 2 MiB) & ~(1 MiB - 1)`；
- `Used` 检查要给 ZAP 留 2 MiB：
  `Used > WindowSize - BLOCK_SIZE - 2 MiB` 才算失败。

结果：H236cs（完整 run，约 1.5 GiB）不再 jetsam，用户态进程能起来
（`backboardd`/`lockdownd`/`sharingd`/`imagent`）。

## 10. Undefined kernel instruction = 预链接归档不匹配（H236ct）

H236cs 在用户态起来后又 panic：

```text
Undefined kernel instruction: pc=0xfffffff0074c7c00 instr=807ff080 @sleh.c:1674
```

与 H170/H173 同签名：pc 落在合法代码段，但镜像里该地址不是这条指令 → 间接
跳转/PAC 目标不对，不是真的执行坏指令。

隔离方法：**新固件 + H174 payload（旧 kernel/prelink）** 启动 → 完整到
launchd 并运行 1182 s，`Undefined kernel instruction` 为 0 → 固件没问题。

修正：在 Mac 上重新执行 `scripts/build-op5-legacy-display.py`（重建
`libNativeLegacyDisplay.late.a`），再重编内核 + prelink；
`Undefined kernel instruction` 消失，内核到 launchd。

`scripts/macos-build-kernel.sh` 现在会检查
`build/native-legacy-display/libNativeLegacyDisplay.late.a`：只要
`drivers/NativeMobileDisplay` 有更新的文件，就先重建归档再编内核。

产物：

```text
firmware abf2adb574d4b5513b3972be38841e80c64775da0c75881c5779d5025d2d8e3c  (完整 run + ZAP 顶部)
kernel   e30750dc1e934e56393d3d3a0bb94fee2526a60f64964c7d02176dfb270c0429  (重编 display 归档)
boot     c1c823a751c34ed48176a6095a3767872dbdc35df5ae273c3301304f2f504b17  boot-H236ct.img
```

---

## 11. `zap-base` 追不进去：命令行已经 997 字符（H236cv）

`NativeA540C3` 用 `PE_parse_boot_argn("zap-base", …)` 读物理地址，loader 负责
在命令行末尾追加。旧代码：

```c
if (AsciiStrLen (CommandLine) + 32 < sizeof (CommandLine)) { … }
```

payload 的 args 已经是 **997** 字符，997+32=1029 > 1024，所以 `zap-base`
从来没被追加，C3 打印 `zap-base missing or invalid: 0`。

修正：先把参数格式化进临时缓冲，再按**实际长度**判断并 `CopyMem`。

## 12. ZAP 的 mdt/image 必须用可缓存映射（H236cw）

`zap shutdown rc=0` 之后立刻：

```text
Unaligned kernel data abort. at pc _bzero+0x44, lr zap_load+0x144
far=0xfffffff1f0284040  x0=0xfffffff1f0284000  x2=0x1f80
```

`zap_load()` 的第一句是 `memset(c.zapHeader.cpu, 0, bytes)`；ZAP 的
`.mdt`/`.b02` 是 DarwinBoot 在普通 DRAM 里预留的 WB 内存，但 `mapWindow()`
一直用 `kIOMapInhibitCache`（Device-nGnRnE）。Device 内存不支持
memset/memcpy 的 16 字节存储 → 对齐中止。

修正：`mapWindowFlags()` 增加缓存参数，ZAP 的两块窗口用
`kIOMapCopybackCache`；`cleanDcache()` 仍在每次 SMC 前把数据刷到 PoC。
MMIO（GCC/GPU/SMMU）继续 `kIOMapInhibitCache`。

产物（H236cw）：

```text
firmware ac56ddbd542cb3dbfeab1d84ad67eb6f76da13dac6dc0b28473232300af9fca4
kernel   7e71d1be1b384143950fd79244230cfc1cc77475061478fd4cf6c5025526e137
boot     8bbfa67a29c370dde56d26b376284e736808646d04bfb7ba8cf5ad42b449ca4e  boot-H236cw.img
```

---

## 13. A540 ZAP 的 PAS 布局：只认 `.mdt` 的 PT_LOAD（H236cx/cy）

`a540_zap.elf` 和 `a540_zap.mdt` 都是 **ELF32**，各 3 个 program header：

```text
#0  type 0  paddr 0x0000  filesz 0x94    memsz 0        (b00, header)
#1  type 0  paddr 0x7000  filesz 0x1988  memsz 0x2000   (b01, hash, flags 0x2200000)
#2  type 1  paddr 0x5000  filesz 0x1334  memsz 0x1334   (b02, PT_LOAD, flags 0x8000007, align 1 MiB)
```

按 sagit `AdrenoFirmware.h::MDTImage` 的规则（只取 `type == 1 && memsz` 的段，
跳过 hash 段）：

```text
metadata  = mdt[0x94] + mdt[0x94..0x1a1c] = 整份 .mdt (0x1a1c)
first     = 0x5000
extent    = 0x2000          (.b02 0x1334，页对齐)
image     = .b02 放在偏移 0
alignment = 1 MiB，relocate = 1（flags bit 27）
```

所以原来 `.b02@0 / 0x2000 / metadata=.mdt` 的布局**是对的**。H236cy 把
“所有 file-backed phdr 拼成 0x9000”交给 PAS，`zap auth` 立刻 `-68`
（与 H236bc 用整份 ELF 文件同因：非 PT_LOAD 段也在镜像里）。

`scripts/check-zap-layout.py --firmware ~/.cache/firmware/a540` 可以离线复核
这套推导（只读 blob，不提交）。

## 14. `CP_SET_SECURE_MODE(0)` 后 trust 仍为 1（H236cw/cz/da）

已经排除的因素（都有实测）：

- PAS 镜像布局（见 §13）；
- ZAP 地址/对齐（`0xABE00000/0xABF00000`，低 4G、1 MiB 对齐）；
- GPMU 顺序：把 `gpmu_load` 挪到 `zap_unsecure` 之前，`GPMUReady=0xbabeface`
  之后发 `CP_SET_SECURE_MODE(0)`，`rptr=3134/3134 done=1`，trust 仍是
  `00000001`（H236cz）。

剩下与 sagit `AdrenoSubmit::Engine::start` 的差异只有：它在
`CP_SET_SECURE_MODE(0)` + `CP_WAIT_FOR_IDLE` 之后**紧跟真实 timestamp**
（`CP_EVENT_WRITE(CACHE_FLUSH_TS|IRQ)`），并以“timestamp 退休 + trust==0”
为成功判据。H236da 按此实现（2 s 轮询 trust，日志追加 `ts=lo:hi`），
镜像 `boot-H236da.img` 待上机。

产物：

```text
firmware ac56ddbd542cb3dbfeab1d84ad67eb6f76da13dac6dc0b28473232300af9fca4
kernel   7210df9f803ae1de0b6170968c20f43d0a77ed7ca06d44f326427398118771c8
payload  5eeb2d1c90274a64a6838fa1d305da0147f9092b10a80c0e187e98ea818af294
boot     86348bcac054cf6e3627a4344e83378597961b3c0be15f51ccaab08ccdb42ab7  boot-H236da.img
```

---

## 15. CP secure 位：三条路径的实测（H236da–dc）

对照下游 kgsl `adreno_a5xx.c`：

```text
a5xx_rb_start: microcode_load -> ME_HALT=0 -> ME_INIT -> a5xx_set_unsecured_mode -> gpmu_init
a5xx_set_unsecured_mode:
    if (ADRENO_CONTENT_PROTECTION)  CP_SET_SECURE_MODE(0)      // a5xx 专用 opcode
    else                            RBBM_SECVID_TRUST_CNTL = 0 // AP 直写
a5xx_regulator_enable: 同样的直写，发生在 GPU 上电时
_me_init_ucode_workarounds(): A540v1 = 0x0A（我们原来传 0）
```

本端口实测：

| 版本 | 做法 | 结果 |
| --- | --- | --- |
| H236cw | `CP_SET_SECURE_MODE(0)+WAIT_FOR_IDLE`，GPMU 之后 | `trust=1`，`ts=0` |
| H236da | 追加 `CACHE_FLUSH_TS` 时间戳 + 2 s 轮询 | `trust=1`，`ts=0`（时间戳没写回） |
| H236db | ME_INIT workaround 0x0A + kgsl 顺序（unsecure 在 GPMU 前） | `trust=1`，`ts=0` |
| H236dc | `gpu reset` 后立即 AP 直写 `TRUST_CNTL=0` | **挂总线**（只打出 `old=1`，没有 `new=`） |
| H236dd | 不再清零 `RBBM_SECVID_TSB_*`（保留固件值）+ `ADDR_MODE_CNTL=1` | `trust=1`，`ts=0` |

结论：

- AP 直写在任何时机都不可用（H236az 是 ~68 s，H236dc 是 reset 后，均挂死）；
- CP 的 `CP_SET_SECURE_MODE(0)` 被执行（RPTR 追上）但 trust 位不变，
  且 secure 模式下 `CACHE_FLUSH_TS` 不落内存；
- 尚未验证的差异：`cp_init` 的寄存器表把
  `RBBM_SECVID_TSB_CNTL/TRUSTED_BASE_LO/HI/SIZE`（0x3e00c/0x3e000/0x3e004/0x3e008）
  全部写成 0，等于禁用 secure TSB。a540 若有 content protection，TSB 可能需要
  真实配置后 secure 转换才会被接受。

下一步候选（按风险从低到高）：

1. 读 `A5XX_RBBM_SECVID_TSB_*` 的复位值并保留，而不是清零；
2. 用 `CP_WIDE_REG_WRITE`（a4xx 风格）让 **CP** 去写 trust 寄存器；
3. 确认 a540 的 `ADRENO_CONTENT_PROTECTION`（DT/gpudev）；若没有，厂商路径就是
   上电直写，需要把直写放到 TZ 锁寄存器之前（我们在 reset 后写仍然挂）。

---

## 16. 两个并行镜像：trust 语义 vs CP 写寄存器（H236de/df）

用户要求把 §15 的两个假设分别做成镜像：

### A（H236de）：先验证 trust=1 是否真的阻塞数据写

改动：`zap_unsecure` 在 `trust != 0` 时只打印
`zap unsecure continuing with trust=…`，**不再 fail**，继续 GPMU + submit probe。

实测（H236de）：

```text
zap unsecure rptr=17/17 done=1 trust=00000001 ts=00000000:00000000
zap unsecure continuing with trust=00000001
gpmu load
fail step 21 (gpmu packets)
```

→ trust=1 **确实**挡住 CP：GPMU 包都发不进去。假设 2（trust=1 可接受）排除。

### B（H236df）：让 CP 写 trust 寄存器（a4xx 风格）

改动：把 `CP_SET_SECURE_MODE(0)` 换成 kgsl a4xx `cp_secure_mode()` 的序列：

```text
CP_SET_PROTECTED_MODE(1) = 0
CP_WIDE_REG_WRITE(2) = [0x0000F400 (RBBM_SECVID_TRUST_CNTL dword), 0]
CP_SET_PROTECTED_MODE(1) = 1
CP_WAIT_FOR_IDLE
+ CACHE_FLUSH_TS 时间戳 + 2 s trust 轮询
```

实测（H236df）：

```text
zap unsecure rptr=22/22 done=1 trust=00000001 ts=00000000:00000000
fail step 44 (zap unsecure)
```

CP 执行了 `CP_SET_PROTECTED_MODE(0) → CP_WIDE_REG_WRITE(0xF400,0) →
CP_SET_PROTECTED_MODE(1)`（RPTR 从 17 到 22），但 trust 位不变。
→ `RBBM_SECVID_TRUST_CNTL` 对 AP 和 CP 都是 secure-only，只有安全世界
（TZ/PAS）能改。两条最便宜的路径都排除，下一步必须解决 PAS 是否真的认证成功。

产物：

```text
A kernel 2e2c4dbb091fbd58876be9617368495f8d1315e71cb2d2ad8d3a6eef461030fa
A boot   ef9cd84209dedfcab7cae56c1da3568b8d5153aa7870555b7ec1f38584e5751f  boot-H236de.img
B kernel ea5ff5d55737143551eea267710e5092de1b376170a07ad12d5fa774bc0134b8
B boot   69005908bd5ed6f6be74c18bc0f4a857dcb51ce740978643e539a27eaeebd16b  boot-H236df.img
```

---

## 17. 真正的 0x66 与后续（H236di–dn）

| 版本 | 改动 | 结果 |
| --- | --- | --- |
| H236di | `PAS_MEM_SETUP` 之后再写 `.b02`（Linux/A 线顺序） + 内存回读 | `after setup=0`（TZ 确实清零），auth rc=0，`mem=0` |
| H236dj | `0x66` 后直接 `CP_MEM_WRITE` 探针，不以 trust 失败 | `mem=00000000`，GPMU 包失败 |
| H236dk | 按 kgsl：CP 基址 → ZAP → ME_INIT → 0x66 | 同上 |
| H236dl | 按 sagit：先 GPMU(BABEFACE) → 停 ME/VBIF → 发布 `0x66`+`CP_WAIT_FOR_IDLE`+探针 → 释放 | 同上 |
| H236dm | 坏 metadata 调 `PAS_INIT_IMAGE` + `PAS_IS_SUPPORTED` | `support rc=0 answer=0`；**`corrupt init rc=-9`** |
| H236dn | 读 `SECVID/TSB` 寄存器（0xf000/0xf800..） | **挂总线**（黑屏、无日志）——该块连读都不可用 |

### 结论

1. **PAS 是真的**：坏 metadata 返回 -9，说明 TZ 在验证签名；好镜像 rc=0 是真实认证。
2. `0x66` 被 CP 接受（`cpint/hwfault=0`），但 `RBBM_SECVID_TRUST_CNTL` 不变，
   `CP_MEM_WRITE`/`CACHE_FLUSH_TS` 的数据写全部被丢。
3. **type4 寄存器写（GPMU 固件、AGC 消息）在 trust=1 下可以成功**（BABEFACE），
   所以 CP 并不是完全被 secure 挡住——**只有经 SMMU 的内存写被丢**。
4. AP 对 `TRUST_CNTL` 的写、以及对 SECVID/TSB 块的读都会挂总线：
   这些寄存器要么是 TZ 独占，要么是只写/只读寄存器（读未实现）。
5. kgsl 在 `adreno_start`/`adreno_reset` 里由 AP **写** `RBBM_SECVID_TSB_CNTL/
   TRUSTED_BASE/SIZE`（`_set_secvid()`，仅当 `mmu.secured`），发生在 ZAP 之前。
   我们从未写过它们，且读它们会挂——下一候选是用**写**而不是读去配置 TSB。

### 下一步候选

1. 仿 `_set_secvid()`：`TSB_CNTL=0`、`TSB_TRUSTED_BASE=<一个合法页表基址>`、
   `TSB_TRUSTED_SIZE=<size>`、`TSB_ADDR_MODE_CNTL=1`（只写，不读），再试 0x66。
   需要确定 secure page table 的合法基址（kgsl: `KGSL_IOMMU_SECURE_BASE`）。
2. 调 SCM SIP BOOT `0x0A`（args `{0,13}`）——kgsl 在 ZAP 保留时用它把 ZAP 基址
   写回寄存器，也许我们的“新鲜认证”路径同样需要。
3. 把 ZAP 镜像放进独立的 reserved carveout（A 线用 DT 预留区），而不是内核窗口。

---

## 18. TSB 可信窗口、ZAP resume、窗口 A/B（H236do–dq）

| 版本 | 改动 | 结果 |
| --- | --- | --- |
| H236do | `gpu_reset` 后、CP 启动前写 `TSB_CNTL=0`、`TRUSTED_BASE=0xE8000000`、`SIZE=0x10000000`、`ADDR_MODE=1`（不读回） | 5 条全部写完不挂；`0x66` 仍 trust=1、`mem=0` |
| H236dp | `zap_load` 成功后、`cp_start` 前发 SCM `SIP BOOT 0xA {0,13}`（kgsl 的 ZAP resume） | `rc=0 answer=0`；无效果 |
| H236dq | 在 SMMU 加一页 `0xE9000000`（可信窗口内），CP 同时写窗口内/外 | `win=00000000`、`mem=00000000` |

### 结论

- `RBBM_SECVID_TSB_*` 对 AP **可写**（不像 `TRUST_CNTL`），按 kgsl `_set_secvid()` 写入正确窗口值也不改变 `0x66` 的结果。
- SCM BOOT 0xA（ZAP resume）被 TZ 接受但同样不改变 CP 的 secure 状态。
- secure 模式下 CP 的内存写**在可信窗口内也失败**，说明限制不在 kgsl 的 TSB 窗口，而在
  secure 访问使用的 **SMMU secure context（CB2 / TZ 的表）**——AP 侧无法参与。
- 目前唯一还没排除的是 ZAP 镜像的物理位置/carveout（成本高，且 PAS 已被证明消费了镜像）。

### 剩余方向

1. 找到 TZ 侧把 GPU 从 secure 切走的接口（SCM 或 ZAP 的 mailbox），而不是让 CP 自己切。
2. 若没有该接口，则必须让 ZAP “真正运行”；需要证据表明它当前没有运行（例如 ZAP 的执行痕迹/
   GPMU 状态），再决定 carveout。

---

## 19. 上游 msm 顺序、PIL 与 secure SID（H236dr–ds）

从上游 Linux（`drivers/gpu/drm/msm/adreno/a5xx_gpu.c` v5.2）查到的关键事实：

- `a5xx_hw_init()` 写 **`TSB_CNTL=0`、`TRUSTED_BASE/SIZE=0`**（“we don't support secure
  memory rendering”），**不是** kgsl 的 0xE8000000 窗口；然后 `ME_INIT`，之后才
  `a5xx_zap_shader_init()`（PAS），最后 `CP_SET_SECURE_MODE(0)`。
- `zap_shader_load_mdt()` 要求 DT 的 `zap-shader` 子节点 + `memory-region`；但 vendor
  PIL（`peripheral-loader.c`）用 `dma_alloc_attrs` 分配普通 DMA 内存（OnePlus 5 的
  `kgsl-hyp` 节点没有 memory-region），所以 **carveout 不是必须的**。
- 工作设备的日志：`kgsl-hyp: a540_zap: loading from 0xf6500000 to 0xf6502000`
  —— ZAP 就是普通低 4G 物理页。
- `SCM SIP BOOT 0x0A {0,13}` 只在“ZAP 已保留、本次重新上电”时由 kgsl 调用。

实测：

| 版本 | 做法 | 结果 |
| --- | --- | --- |
| H236dr | 上游顺序：TSB=0 → ME_INIT → PAS/ZAP → 0x66 → GPMU | trust=1，mem=0，GPMU 失败 |
| H236ds | ZAP/PAS 在 `smmu_setup` **之前**（避免重配 SMMU 破坏 secure 路径） | 同样失败 |

### 新证据：secure SID

OnePlus 5 的 `msm8998-gpu.dtsi`：

```text
kgsl_msm_iommu: qcom,kgsl-iommu {
    qcom,secure_align_mask = <0xfff>;
    qcom,hyp_secure_alloc;
    gfx3d_secure { iommus = <&kgsl_smmu 2>; };   // secure 流 = SID 2
};
```

secure GPU 访问绑定在 **SID 2** 的 TZ 管理 context 上；我们的 CB0/SID0 配置天然覆盖不到它。
如果 ZAP 没完成，CP 的写会落到 secure 流并被丢（读 ring 仍走 SID0，所以 RPTR 正常）——
这和“只有内存写失败、寄存器写正常”完全一致。

下一步候选：确认 SID 2 的 secure context 在 XNU 启动链里是否由 ABL/TZ 配置；
需要时让 DarwinBoot 保留/恢复 bootloader 留下的 SMMU secure stream，而不是只建 CB0。

---

## 20. secure SMMU 配置探测（H236dt/du/dv）

按厂商 `arm-smmu.c` 的 static-CB 路径做探测：

```text
micro-MMU ctrl = SMMU base + 0x6000 (qcom,micro-mmu-control)
  bit2 = LOCAL_HALT_REQ, bit3 = IDLE
halt/resume 必须经 TZ: scm_io_write(SVC_IO=5, cmd=2, phys, value)  (atomic)
secure 配置恢复: scm_restore_sec_cfg(SVC_MP=0xC, cmd=2, device_id, 0)
```

| 版本 | 做法 | 结果 |
| --- | --- | --- |
| H236dt | SMMU 运行中直接 `restore_sec_cfg(TZ_DEVICE_GPU=18)` | `rc=-2 answer=-4` |
| H236du | 先用 `scm_io_write` 停 micro-MMU（`idle=1`）再 restore | **仍 `rc=-2 answer=-4`**；resume 正常 |
| H236dv | 遍历 device id 0–31 找 TZ 认的编号 | `id=18` 仍是 -4；**`id=19` 的 SMC 不再返回**，显示/ USB 挂死（系统其余部分仍在跑） |

结论：

- 这个 TZ 不接受 GPU 的 `RESTORE_SEC_CFG`（即使 SMMU 已 halt），要么该调用不适用于
  GPU SMMU，要么 device id 编号与内核头文件不同；
- **不要遍历 device id**：某些 id（显示/UFS 相关）会让 SMC 永久阻塞，代价是黑屏；
- 厂商路径里 `arm_smmu_is_static_cb()` 为假时根本不会调用它，Android 的成功并不能
  证明该调用对 GPU 有效。

secure SMMU 这条线到此为止；后续如果还要走，需要 TZ 固件侧的 device id/调用语义，
而不是继续在 AP 侧猜。

---

## 21. ZAP 归属与 GPMU 先行（H236dw/dx）

| 版本 | 做法 | 结果 |
| --- | --- | --- |
| H236dw | auth 之后 `invalidate` 再读 ZAP 镜像首字 | **读挂总线**（日志停在 `zap post-auth read begin`）——TZ 已接管镜像，PAS 是真实消费 |
| H236dx | 先 GPMU 到 BABEFACE，再 auth ZAP，再 0x66 | GPMU 在 auth 后仍为 `babeface`；`0x66` 仍 trust=1、`mem=0` |

结论：

- TZ 在 auth 后把镜像页收走（读会挂），说明 ZAP 确实被安全世界加载，PAS 链路没有假成功；
- “ZAP 在 GPMU 上执行”的假设也不成立（GPMU 先行 + auth 后仍 babeface，仍不生效）；
- AP 侧能控制的机制（0x66 的位置/时机、TSB 窗口、顺序、resume、SMMU 配置）已经全部试过，
  剩下的差异只在 TZ/安全世界内部，AP 没有可观测入口。

---

## 22. C3 收尾：镜像清单（2026-11-10）

本轮（H236dg–dx）产生的镜像，全部只做 `fastboot boot`：

| 版本 | 目的 | kernel | boot |
| --- | --- | --- | --- |
| dg | 真 0x66 + cpint/hwfault 诊断 | `75dfedc7…` | `c4143620…` |
| dh | PAS auth 后 AP 直写 TRUST_CNTL | `d6b0e810…` | `b4af3571…` |
| di | `MEM_SETUP` 后再写 `.b02` | `61d40e5d…` | `3c09cbe8…` |
| dj | 0x66 后 `CP_MEM_WRITE` 探针 | `fc8c4dc7…` | `ee31583e…` |
| dk | kgsl 顺序（基址→ZAP→ME_INIT） | `3dccce55…` | `5e65248a…` |
| dl | sagit 停管线转换 | `a34c164d…` | `b1fdf315…` |
| dm | 坏 metadata / PAS 支持查询 | `1fbadd8b…` | `63b87763…` |
| dn | SECVID/TSB 读（挂） | `a8b02ad3…` | `3487ffa4…` |
| do | TSB 窗口 0xE8000000 | `2144149b…` | `b4015b58…` |
| dp | ZAP resume SCM | `adfb1450…` | `dabbadd6…` |
| dq | 可信窗口 A/B | `1e9dfb6f…` | `1419fe74…` |
| dr | 上游 msm 顺序 | `65e33b81…` | `09eade35…` |
| ds | ZAP 先于 SMMU | `4c08951f…` | `873422d6…` |
| dt | `RESTORE_SEC_CFG(18)` | `f866253e…` | `1497aa08…` |
| du | halt + restore + resume | `14d4a470…` | `d3ed852b…` |
| dv | device id 扫描（id=19 挂死） | `94f690c9…` | `9e4dce4f…` |
| dw | auth 后读镜像（挂） | `a08458d0…` | `679165e2…` |
| dx | GPMU 先行 → ZAP → 0x66 | `ab5c914d…` | `42edaac3…` |

**不要重跑**：dn（读 SECVID 挂）、dv（id 扫描挂）、dw（auth 后读镜像挂）。

基线仍用 H236db（kgsl 顺序 + `0x0A`）：kernel `87da966b…`、boot `7778cf6f…`，
它能把 C3 跑到 `zap unsecure` 且不挂总线。

---

## 23. P2/P1 探针、V1 顺序与 TZ 日志（H236dy–ee）

### 23.1 P2：`AUTH_AND_RESET` 不复位 GPU

先后在两种状态下各拍了一次 auth 前后的 CP/RBBM 快照：

| 版本 | auth 时 ME | pre-auth | post-auth |
| --- | --- | --- | --- |
| dy（GPMU 已在跑） | 运行 (`me=00000000`) | `me=0 rb=01000000 prot=7 am=1 ahb2=3f trust=1` | **一字不差** |
| ea（kgsl 冷顺序） | 停机 (`me=00000303`) | `me=303 rb=01000000 prot=7 am=1 ahb2=3f gpmu_rst=1 trust=1` | **一字不差** |

结论：PAS 的 `AUTH_AND_RESET` 不碰 AP 可见的 CP/RBBM 状态，与 kgsl 把 PAS 放在
`microcode_load`（写完 INSTR/RB 基址、ME 仍停机）里的用法一致。

### 23.2 P1：auth 之后 `TRUST_CNTL` 立刻就是 1

dy/ea 两次都在 auth 返回后**立刻**读 `0xF400*4`（中间只有一个 `GPMU_GENERAL0` 读）：

```
trust after auth=00000001
```

结论：TZ 在 auth 时**没有**清 trust。`trust=1` 不是“被我们后面的启动步骤改回去的”。

### 23.3 V1（PAS 先、reset 后）：无效，且实现有缺陷

| 版本 | 结果 |
| --- | --- |
| dz | `smmu → PAS → reset → ME_INIT → GPMU → 0x66`：reset 后 `trust=1`，0x66 后仍 `1`、`mem=0` |

缺陷：PAS 跑在 `gpu_reset()` 之前，而**时钟是 `gpu_reset()` 才打开的**，所以 auth
前后的 CP/RBBM 读数全是 `ffffffff`（不可信）。sagit 的 EFI 桥做 PAS 时 GPU 是上电的，
要真正复刻 V1 必须先把时钟打开。本轮没有做这一步，V1 只能算“未充分测试”。

### 23.4 TZ / hyp 日志：可以读，但 qsee 环形缓冲是加密的

- `tz-log@146BF720` 的 `+0x410/+0x414` 给出 hyp 日志的物理地址和长度：本轮
  `ptr=0x85997000 size=0x2000`；
- **hyp 日志是明文**，8 KiB 里只有启动内容：

```
HYP Version Info: QC_IMAGE_VERSION_STRING=TZ.BF.4.0.6-00161
IMAGE_VARIANT_STRING=RAGAANAAA
OEM Version Info: OEM_IMAGE_VERSION_STRING=CRM
SMMU Info: VMID 4 not support
SMMU Info: VMID 4 not support
Initializing PIL
```

  之后再无任何条目 —— hyp 没有参与/记录本次 PAS。
- `0x146BF720` 起的 0x3000 是 qsee 环形缓冲，内容高熵（`tzdbg_t` 里带 key/nonce/tag），
  **不能直接读成文本**；
- `0x14692000`（tz 区第一个字指向的地址）是 TZ 的**中断/诊断表**，明文但只有
  `SPI XPU / CB ISR / Glb Cln / RPM->TZ` 这类条目。

### 23.5 SMMU secure 上下文的非安全视图（只读）

```
cb0 sctlr=00000000 ttbr=00000000 |
cb2 sctlr=00000000 ttbr=00000000/00000000 cba2r=00000000 s2cr=000200ff smr=00000000
```

`0x200ff` 就是驱动自己的注释里记的 FAULT 编码。但 secure CB 在非安全侧通常读作
RAZ/WI，所以这**不能**证明安全流不存在，只能作为记录。

### 23.6 新增镜像

| 版本 | 内容 | kernel | boot |
| --- | --- | --- | --- |
| dy | P2 快照 + P1（GPMU 先） | `e2b1faba…` | `ccf22459…` |
| dz | V1：PAS 先、reset 后 | `42b6ff84…` | `ef2f73ef…` |
| ea | kgsl 冷顺序 + CB2 survey | `9fa5255f…` | `558faafc…` |
| eb | tzlog 探针提前 | `ba38e4d2…` | `e3e7b8f3…` |
| ec | hyp 日志文本 dump | `e3af39a6…` | `523516ee…` |
| ed | tzring/tzptr 文本 dump（**挂**） | `e7b424e7…` | `33acc418…` |
| ee | 压缩 dump（可用） | `0497a513…` | `1c05f0de…` |

### 23.7 坑

1. **PAS 前必须先把 GPU 时钟打开**（`gpu_reset()` 里的 GCC 段），否则 CP/RBBM 读全是
   `ffffffff`，P2/P1 数据无效。
2. 一次性 `IOLog` 上百行 99 字符、只在末尾 flush，会在日志路径里**整段丢失**
   （H236ed 的 `tzring` 一行都没留下，连 `hyplog ptr` 都丢了）。要压缩输出
   （零区长串折叠、跳过无内容行、每行 flush、每窗口限 48 行）。
3. 读 `0x146BF720` 前 0x50 字节没问题，但整段 0x3000 逐字节读会让设备挂死
   （表现为黑屏，重启后日志完好）。

---

## 24. Android 侧参考态（同机、已 root，2026-11-10）

设备回到 Android（LineageOS，Magisk root）后取的**同一台机器上的成功参照**。

### 24.1 kgsl 的 ZAP 加载（成功）

```
[7.425] ueventd: firmware: loading 'a540_zap.mdt' .../soc:qcom,kgsl-hyp/firmware/a540_zap.mdt
[7.430] subsys-pil-tz soc:qcom,kgsl-hyp: a540_zap: loading from 0x00000000f6900000 to 0x00000000f6902000
[7.461] ueventd: firmware: loading 'a540_zap.b02'
[7.471] subsys-pil-tz soc:qcom,kgsl-hyp: a540_zap: Brought out of reset
```

- 和我们 iOS 侧的 `a540_zap: loading from 0xf6500000 to 0xf6502000` 结构完全相同；
- `subsys-pil-tz` 对 `kgsl-hyp` 只有 `invalid resource` / `Failed to iomap base register`（没有
  reset 控制寄存器），也就是说 **Android 的 ZAP 也完全是 SCM/PAS 驱动的，没有任何 AP 侧
  GPU 寄存器操作** —— 我们缺的不是“多一步寄存器”。

### 24.2 hyp 日志与 iOS 完全一致

Android 的 `tzdbg/hyp_log`：

```
HYP Version Info: QC_IMAGE_VERSION_STRING=TZ.BF.4.0.6-00161
HYP Version Info: IMAGE_VARIANT_STRING=RAGAANAAA
OEM Version Info: OEM_IMAGE_VERSION_STRING=CRM
(0)
SMMU Info: VMID 4 not support
SMMU Info: VMID 4 not support
Initializing PIL
```

与 iOS 侧逐字相同 → **`VMID 4 not support` 是这台机器的正常输出**，不是故障线索（此前
怀疑的“secure VMID 分配失败”可以正式排除）。

### 24.3 寄存器参考态取不到

- `CONFIG_DEVMEM is not set`：内核没有 `/dev/mem`，`mknod` 出来的节点打不开（SELinux
  permissive 下仍 EACCES）；`/proc/kcore` 也不存在；
- kgsl `snapshot/` 目录存在但 `faultcount=0`，没有可读的寄存器快照；
- 因此**无法**从 Android 用户态拿到 `TRUST_CNTL` / SMMU CB2 / TSB 的参考值。

### 24.4 可用的 TZ 调试接口

`/sys/kernel/debug/tzdbg/`：`boot / general / hyp_general / hyp_log / interrupt / log /
qsee_log / reset / vmid`。

- `general`：`Version 0x90001`、`Magic Number 0x747a6461`、8 CPUs；
- `log`：TZ 的**调用轨迹**，格式 `[TZ 地址](代码 参数...)`，无符号表无法翻译；
- `vmid`：读取为空；
- 注意 `log` 是“自上次读取以来的新增条目”，读一次即消费。

### 24.5 一个未解释的差异（新线索）

Android 的 `tzdbg/general` 在 `0x146BF720` 读到 magic `0x747a6461`；我们 iOS 侧在**同一物理
地址**读到的是 `0x14692000`（后续字节也不同），但 `+0x410/+0x414` 的 hyp 指针/长度、以及
hyp 日志内容都完全正确。

也就是说：**TZ diag 表头在我们这条启动链上被改过**（不是全零，是别的数据）。这不影响已知
结论，但值得单独查一次：如果我们的 boot 链（UEFI/DarwinBoot）碰了 IMEM，那是一个应该修的
问题。验证方法：在**尽可能早**的位置（DarwinBoot 内）读一次 `0x146BF720` 的 magic，与 C3
线程（约 58 s）读到的值对比。

### 24.6 现场恢复

Android 侧临时 `setenforce 0` 已恢复为 `Enforcing`，临时的 `/data/local/tmp/mem` 已删除。

---

## 25. 与 Android 的逐项 A/B（2026-11-10）

用同机 Android（LineageOS + Magisk root，kgsl 工作正常）作为参照，把“我们喂给 PAS 的东西”
和“Android 喂给 PAS 的东西”逐项对比。

### 25.1 参数与固件

| 项 | Android | 我们 | 结论 |
| --- | --- | --- | --- |
| DT `qcom,pas-id` | `0x0d` (13) | `kPasGpu = 13` | 相同 |
| DT `qcom,firmware-name` | `a540_zap` | `a540_zap` | 相同 |
| DT 节点属性 | 只有 `compatible/firmware-name/pas-id` | — | 没有额外时钟/电源/reg 要求 |
| `a540_zap.b00` sha256 | `5302ecf8…` | `5302ecf8…` | **相同** |
| `a540_zap.b02` sha256 | `99793376…` | `99793376…` | **相同**（真正执行的代码） |
| `a540_zap.mdt` sha256 | `2d17e0b2…` | `530c0a89…` | 不同（见 25.2） |
| `a540_zap.b01` sha256 | `1d71345f…` | `31ffe885…` | 不同（见 25.2） |
| PAS 镜像大小 | `0x2000`（日志 `loading from …f6900000 to …f6902000`） | `0x2000` | 相同 |

### 25.2 mdt / b01 的差异不影响装载

解析两个 mdt 的 ELF 头与程序头（`entry=0x5000`、`e_phnum=3`）：

```
ph0: type=0 (PT_NULL)  off=0x0     paddr=0x0     filesz=0x94   flags=0x07000000
ph1: type=0 (PT_NULL)  off=0x1000  paddr=0x7000  filesz=0x1988 flags=0x02200000  <- HASH 段(b01)
ph2: type=1 (PT_LOAD)  off=0x3000  paddr=0x5000  filesz=0x1334 flags=0x08000007  <- 代码(b02)
```

- 两个文件的程序头**完全一致**（含 `paddr=0x5000`、`filesz=0x1334`=4916）；
- mdt 内嵌的 **b00 与 b02 哈希也完全一致**；
- 差异集中在三段 256 字节的**签名/证书块**和 b01（HASH 段）的哈希；
- b01 对应 `PT_NULL` + `flags` 的 type 字段 = `HASH`，`mdt_loader` 只装载 `PT_LOAD`
  （这也是 Android 日志里 mem_setup 只有 `0x2000` 的原因），**b01 从不进镜像**。

所以：**实际执行的那段代码与 Android 逐字节相同**，签名块不同只说明两份 mdt 来自不同的
签名批次（都能通过验签，我们 rc=0 也证明了这一点）。

### 25.3 启动路径

| 项 | Android | 我们 |
| --- | --- | --- |
| PAS 调用方 | `subsys-pil-tz`（**纯 SCM**，对 `kgsl-hyp` 连 base 寄存器都没有） | 手写 SCM |
| 顺序 | power → mmu → `_set_secvid` → a5xx hw init → RB/INSTR 基址 → **PAS**（ME 停）→ ME 释放 → ME_INIT → `0x66` → GPMU | H236ea 已按此顺序实测 |
| 冷启动是否 RBBM 软复位 | 是（`regulators_left_on` → `_soft_reset`，含 `RBBM_SW_RESET`） | 是（`gpu_reset`） |
| `0x66` 报文 | `CP_SET_SECURE_MODE(1 dword)=0` | 相同 |
| ME_INIT 载荷 | `0x2f,3,0x20000000,0,0,0x0A,0,0` (a540v1) | 相同 |
| CP_PROTECT 表 | 含 `{0xf800,4}`、`{0xf400,1}`，编码 `0x60000000|l2<<24|base<<2` | 相同 |
| hyp 日志 | `TZ.BF.4.0.6-00161 / RAGAANAAA / CRM / SMMU Info: VMID 4 not support ×2 / Initializing PIL` | **逐字相同** |

### 25.4 结论

AP 侧能给 TZ 的输入已经**逐项对齐**到可执行代码级别，Android 的成功路径里也没有任何我们
缺失的 AP 侧寄存器操作。剩下的差异只可能在安全世界内部（ZAP 的执行与其完成信号），
而 AP 侧没有可观测入口（SECVID 读会挂、CB2 在非安全侧读作 RAZ、qsee 日志加密）。

---

## 26. hw-init 全量复刻（H236ef/eg，2026-11-10）

选项 2：把 mainline/vendor `a5xx` 的 hw-init 全部复刻后再做 PAS。

### 26.1 逐项核对

| hw-init 项 | 来源 | 状态 |
| --- | --- | --- |
| VBIF 事务表 (`ROUND_ROBIN_QOS_ARB`, `GATE_OFF_WRREQ_EN`) | `a540_vbif[]` | 已有（`0xc124`/`0xc0a8`） |
| RBBM perfctr / AHB_CNTL0/1/2 / hang int / UCHE / CP 阈值 / PC_DBG_ECO | `a5xx_hw_init` | 已有 |
| CP_PROTECT 全表（含 SECVID） | `a5xx_protect_init` | 已有且逐条一致 |
| TSB_CNTL/BASE/SIZE=0、各块 ADDR_MODE=1 | `a5xx_hw_init` | 已有 |
| ME_INIT 载荷 | `a5xx_send_me_init` | 已有 |
| LM（AGC 36 payload + 电压/功耗阈值） | `a540_lm_setup` | **已有**（`gpmu_load` 内） |
| SP/TP power collapse (`PWR_COL_*` 4 个) | `a5xx_pc_init` | **已有**（`gpmu_load` 内） |
| GPMU 固件（type4/IB + CM3_SYSRESET=0 + BABEFACE） | `a5xx_gpmu_ucode_init/start` | 已有 |
| **hwcg 时钟门控表（95 条）** | `a540_hwcg_regs` | **本次新增**（H236ef） |

hwcg 表由 `a5xx_reg.h` 的 dword 索引机械换算成字节偏移后写入 `cp_configure`。

### 26.2 结果（H236ef）

```
pre-auth   me=303 rb=01000000/0 prot=7 am=1 ahb2=3f gpmu_rst=1 trust=1
auth       rc=0 answer=0
post-auth  与 pre-auth 一字不差
trust after auth = 00000001
cp start   idle=1 (rptr=9)
trust before 0x66 = 00000001
0x66       rptr=25/25 done=1  trust=00000001  ts=0:0  mem=0  win=0
```

**没有任何变化。** 补齐 hwcg 之后 CP 依旧不离开 secure 模式。

### 26.3 副产物：TZ diag 区整段读取会挂总线

H236ed/ee/ef 里对 `0x146BF720`(0x3000) 和 `0x14692000`(0x1000) 的文本 dump 会在读到
某处时挂死（本次表现为黑屏，系统其余部分仍跑到 1549 s）。H236eg 已把这两段遍历删掉，
只保留 `tzlog` 头部 20 个字 + hyp 日志指针/长度（这两项读起来是可靠的）。

### 26.4 最终基线

| 版本 | 内容 | kernel | boot |
| --- | --- | --- | --- |
| ef | hwcg 全表 + P2/P1 探针 | `83fd023e…` | `606638b6…` |
| **eg** | ef 去掉危险 TZ dump（**基线**） | `ca13c26c…` | `26f0c53f…` |

---

## 27. 证据判别力复核与 C3 边界修正（2026-11-10）

前面 §23–§26 的结论需要收窄。逐条复核：

| 证据 | 判别力 | 说明 |
| --- | --- | --- |
| P2：auth 前后 CP/RBBM 快照一字不差 | **中性** | mainline 的 `a5xx_zap_shader_init()` 本来就在 ME 已释放、ME_INIT/power_init 完成之后调 PAS，随后继续用同一个 ring 发 `0x66` 并 idle。若 `AUTH_AND_RESET` 会清 AP 可见的 CP 状态，这条路根本走不通，而它在 OP5 上能跑 GPU。**只排除了“TZ 复位 GPU”这一支，推不出 ZAP 没跑。** |
| P1：auth 后 trust 立刻为 1 | **信息不足** | kgsl 的注释是 “GPU comes up in secured mode, make it unsecured by default”；sagit 的判据是 `TrustControl > 1` 才算错、`0x66` 之后才要求 0 —— 都暗示 auth 时刻为 1 是正常的。**我们从未在 Android 上量过这台机器的 trust**，所以既不能证实也不能证伪。 |
| hyp 日志无 GPU/PAS 记录 | **误读** | PAS 走 TZ/QSEE，不走 hyp。hyp 日志里没有 PAS 记录是**必然**，不构成“TZ 没记录”。 |
| 与 Android 逐项 A/B | **只对齐了“内容 + 调用序列”，没对齐“归属”** | 验签只看内容，执行还要看内存/电源/NoC 归属。Android 的载荷来自预留池、电源/时钟/NoC 由 RPM+GPUCC+CPR 驱动；我们的是 DarwinBoot 从 DRAM 切的窗口 + 直接写 GCC 位。内容相同、仍然不跑，正是“归属未对齐”的典型形态。 |
| hw-init 全量复刻（含 a540 hwcg 95 条） | **最强的一条** | 它排除了“寄存器内容没对齐”这一整类，但只有这一类。 |

### 27.1 修正后的表述

C3 冻结在**寄存器内容层已对齐**：PAS 参数、ZAP 镜像字节、CP/RBBM hw-init（含 a540 hwcg
95 条）、启动顺序均与同机 Android 一致；`AUTH_AND_RESET` 不复位 AP 可见状态、auth 后
trust 恒为 1、`0x66` 被接受但不生效。

**未验证项（均为 AP 可执行，故不构成“外部依赖”）**：

1. **正例 Android 的 SECVID 读数**（trust / TSB_CNTL / TSB base）；
2. **无 PAS 的 `0x66` 对照**（`0x66` 是在实现 PAS 之后才引入的，这条从未测过）；
3. **坏载荷负控制**（合法 metadata + 故意改坏的 `.b02`）；
4. **ZAP 内存的 cache 属性与固定保留区归属**（uncached 回退；放到与 Android 同类的地址）；
5. **同机型 mainline 正例**（`fastboot boot` mainline/postmarketOS，读同一个 trust）。

**真正的外部依赖**：QSEE 日志解密/符号、TZ/hyp 调试固件，或 QCOM 对
“`CP_SET_SECURE_MODE` 在 TZ 侧的前置条件”的说明。

### 27.2 正例读数：地址与前提更正

寄存器是 **dword 索引 ×4**，对应 GPU 块（基址 `0x05000000`）的字节地址：

| 寄存器 | dword | 字节地址 |
| --- | --- | --- |
| `RBBM_SECVID_TRUST_CNTL` | `0xF400` | **`0x0503D000`** |
| `RBBM_SECVID_TSB_TRUSTED_BASE_LO` | `0xF800` | `0x0503E000` |
| `..._HI` | `0xF801` | `0x0503E004` |
| `..._SIZE` | `0xF802` | `0x0503E008` |
| `..._CNTL` | `0xF803` | `0x0503E00C` |

（此前的 `0x050F4000` 写法是 dword 索引当作字节用，偏大 4 倍。）

**前提问题**：本机 LineageOS 内核 `CONFIG_DEVMEM is not set`、无 `/proc/kcore`，所以
Android 用户态**无法**用 `devmem` 读这些地址。可行路径只有：
(a) `fastboot boot` 一份打开了 `CONFIG_DEVMEM` 的 mainline/postmarketOS 镜像（只 boot）；
(b) 在 kgsl/其它驱动里找可读寄存器的 debugfs 入口（本机 `kgsl-3d0/` 下只有 `isdb`，
读出来是 0，未验证可用）。

### 27.3 TZ 日志的“消费者”前提

`0x146BF720` 在我们环境里遍历会挂，但那时 AP 还没有作为“日志消费者”和 TZ 建立关系；
Android 的 `tzbsp` 驱动能读它。未试过：**失败启动后不断电重启回 Android**，再读
`/sys/kernel/debug/tzdbg/log`（本机的节点名）。若缓冲区不清零，就能看到 TZ 对那次
PAS/`0x66` 的记录。这比“找带调试的 TZ 固件”便宜两个数量级。

---

## 28. 三个负控制/对照实验（H236eh–ej，2026-11-10）

### 28.1 A：完全不跑 PAS，直接 `0x66`（H236eh）

只把 `zap_load()` 从流程里摘掉，其余不变（`0x66` 是 H236ba 之后才引入的，这条从未测过）。

```
PAS SKIPPED (control)
cp start          idle=1 (rptr=9)
trust before 0x66 = 00000001
0x66              rptr=25/25 done=1  trust=00000001  ts=0:0  mem=0  win=0
```

**与有 PAS 时完全一致。** 含义：

- `0x66` 失效**不是** PAS 的顺序或交互造成的（全新的 CP、从未调用 PAS，行为一样）；
- “ZAP 是 `0x66` 生效的唯一前置条件”这个假设**至少不完整**——要么 ZAP 在两种情况下都没跑，
  要么 `0x66` 的失效还有别的共同原因。

### 28.2 B：合法 metadata + 改坏的 `.b02`（H236ei）

metadata 不动，只把代码段第 `0x40` 个 dword 翻转一个 bit：

```
zap image CORRUPTED word[0x40]=8a01fcfd
zap auth call b02=4916
zap auth rc=-61 answer=0
fail step 43 (zap auth and reset)
```

**auth 被拒绝（`-61`）。** 这保护了核心前提：

- TZ **确实在验载荷内容**，不是只验 metadata 的签名；
- 之前“好镜像 `rc=0`”确实代表“这段代码被 TZ 接受”。

### 28.3 C：auth 前 clean + invalidate（H236ej）

`cleanDcache` 之后再 `invalidateDcache` + `dsb`，杜绝 TZ 接管后仍有脏 cache 行回写。

```
zap auth rc=0
trust after auth = 00000001
trust before 0x66 = 00000001
0x66  rptr=25/25 done=1  trust=00000001  mem=0
```

**无变化。** ZAP 页的 cache 归属不是原因；该维护保留（属于正确做法）。

### 28.4 镜像

| 版本 | 内容 | kernel | boot |
| --- | --- | --- | --- |
| eh | 无 PAS 的 `0x66` 对照 | `c229847c…` | `02f19d1a…` |
| ei | 坏 `.b02` 负控制（auth `-61`） | `8d2c3e80…` | `1792c6a8…` |
| ej | clean+invalidate 后 auth | `5713443e…` | `847e6326…` |

### 28.5 仍未做的两项（都卡在同一个前提上）

- **正例 SECVID 读数**（Android 的 trust / TSB）：本机 LineageOS `CONFIG_DEVMEM is not set`，
  `/proc/kcore` 也不存在 → 用户态读不到；
- **同机型 mainline 正例**：同样需要一个能读物理内存的内核。

两者都指向同一个可行做法：`fastboot boot` 一份打开了 `CONFIG_DEVMEM` 的 mainline/pmOS
镜像（只 boot 不 flash），一次拿到 `0x0503D000` / `0x0503E000` 的读数，并且顺便验证
“没有 secure CB、没有 CPZ、没有 hyp_assign 的 AP 能不能把 trust 变成 0”。

---

## 29. 正例读数：Android 工作态 SECVID（2026-11-10）

### 29.1 方法（可复用）

本机 LineageOS 内核 `CONFIG_DEVMEM is not set`、`CONFIG_MODULE_SIG_FORCE=y`、无 `/proc/kcore`，
Android 用户态没有任何寄存器读取口。可行路径是 **kgsl snapshot**：

1. a5xx 的 snapshot 寄存器表（`adreno_a5xx_snapshot.c:362`）包含
   `0xF400, 0xF400, 0xF800, 0xF807`；
2. 用一个小工具（`/data/local/tmp/kgslfault`，静态 ARM64）走
   `DRAWCTXT_CREATE(flags=PREAMBLE|NO_GMEM_ALLOC)` → `GPUMEM_ALLOC_ID` → `mmap(id<<12)`
   → `GPU_COMMAND`（cmdlist 里一条 `CP_MEM_WRITE` 到未映射地址，`obj.flags=CMDLIST_IB`）
   触发 GPU fault；
3. kgsl 自动 snapshot（`faultcount=1`，dmesg：`snapshot created at pa … size 818424`）；
4. `cp /sys/class/kgsl/kgsl-3d0/snapshot/dump /data/local/tmp/snap.txt` 拉出**二进制**转储；
5. 解析：`{u16 magic=0xABCD, u16 id, u32 size}` 的 section，`id=0x0201` 为寄存器段，
   载荷是 `{u32 count}` + count 组 `{u32 dword_offset, u32 value}`。

### 29.2 读数（Android，kgsl 正常工作）

```
TRUST_CNTL       0xF400 = 0x00000000      <- 工作态 trust 是 0
TSB_TRUSTED_BASE 0xF800 = 0x00000000
                 0xF801 = 0x00000000
TSB_TRUSTED_SIZE 0xF802 = 0x00000000
TSB_CNTL         0xF803 = 0x00000000
CP_ADDR_MODE_CNTL 0x860 = 1
CP_PROTECT_CNTL   0x8A0 = 7
CP_ME_CNTL        0x832 = 0x00000400
CP_RB_BASE        0x800 = 0xfc060000
RBBM_STATUS       0x4F5 = 0x800001c1
```

### 29.3 结论

1. **`trust=0` 是工作态**，我们的 `trust=1` 确实是“仍在 secure 模式”——此前“trust=1 可能
   是正常态”的怀疑可以关闭；
2. **Android 的 TSB 全零**，说明本机 `mmu.secured == false`，`_set_secvid()` 什么都不写。
   我们一直写 0 是对的；H236do 试 `0xE8000000/0x10000000` 是错误方向；
3. 由此可以排除“TSB 窗口配置不同”这一类假设（此前只是“试过”，现在是有正例对照的排除）；
4. 另外获得 4145 个寄存器的**工作态全量参考**，可用于后续逐寄存器 diff。

### 29.4 现场

`/data/local/tmp/kgslfault`（可重跑）与 `/data/local/tmp/snap.txt` 留在设备上；
一次故障会让 kgsl 复位 GPU，属正常恢复，不影响 Android。

---

## 30. 与 Android 工作态的逐寄存器 diff（H236ek–en，2026-11-10）

### 30.1 做法

把 kgsl snapshot 的寄存器清单（`adreno_a5xx_snapshot.c: a5xx_registers[]`，4145 个 offset）
原样搬到 C3 里逐个读（排除会挂的 SECVID 区 `0xF001-0xF8FF`，保留 `0xF400`），与 Android 的
工作态 dump 逐值比较。第一次实现有个 bug：把 dword 索引直接喂给按字节取值的 `rd()`
（内部又除以 4），整份数据错位，已在 H236el 修正为 `rd(off * 4)`。

### 30.2 结果

| 类别 | 结论 |
| --- | --- |
| **CP / RBBM 配置** | **与 Android 逐值一致**（CP_ADDR_MODE=1、CP_PROTECT_CNTL=7、CP_ME_CNTL=0x400、CP_RB_BASE 等），差异只有性能计数器（Android 运行久了有累积值）和 `TRUST_CNTL`（A=0 / O=1） |
| hwcg (`RBBM_CLOCK_*`) | Android 的 snapshot 里是 0，但 `sysfs hwcg=1` —— 说明 0 是**挂起时清零**的状态，不是“hwcg 关闭”。kgsl 醒着时会写 a540 使能表，所以我们的表（H236ef）与之相符；H236em 的清零是误改，已恢复 |
| GPUCC / 频率 | 两边 CX/GX GDSC 都 `on=1`，PLL L=53 → 257 MHz；Android `gpuclk=257000000`，与我们的 RCG 一致 |
| **3D 上下文块 `0xE000-0xEFFF`** | 我们读出来是**每次都不一样的高熵垃圾**；Android 在同一位置是结构化值 |
| **`0x0EC0` (`SP_DBG_ECO_CNTL`)** | **读它会挂死总线**（`0xE000` 之后继续 dump 时挂在这里）；Android 在故障快照里读它没问题 |

### 30.3 结论与新线索

- AP 侧**没有发现任何配置差异**（除 `TRUST_CNTL` 本身）。这进一步把问题从“寄存器没配对”
  推向“块级电源/时钟状态”。
- **新线索**：a540 的 ZAP 是**着色器**，而我们的 `SP`/3D 块读出来是漂浮值、且
  `SP_DBG_ECO_CNTL` 一读就挂 —— 与“着色器块未上电/未开时钟”一致（对比：Android 在故障时刻
  能正常读）。但这也可能只是“空闲 vs 活动”的差异（块在空闲时被 power collapse），尚未定论。

### 30.4 镜像

| 版本 | 内容 | kernel | boot |
| --- | --- | --- | --- |
| ek | 首次 dump（offset 错位） | `ab52f06d…` | `1ac5e345…` |
| el | 修正 `off*4` + 块标记 | `9251933b…` | `3a8c4b42…` |
| em | hwcg 清零（误改） | `cef37b52…` | `208eab1d…` |
| **en** | 恢复 hwcg、移除 dump（**基线**） | `fa149af7…` | `f6bf7668…` |

---

## 31. SP/3D 块可达性判定（H236eo，2026-11-10）

### 31.1 做法

按“写已知图案再读回”的思路做三步判定（每一步读/写前都落日志）：

1. 对照：`CP_MEQ_THRESHOLDS`(0x2094) 写 `0x5A5A5A5A` 再读回（已知可写）；
2. `0xE140`（RB CTX0，dump 里读出来是漂浮值）写图案再读回；
3. `0xEC0`（`SP_DBG_ECO_CNTL`，dump 到此必挂）写图案再读回。

### 31.2 结果

- **`spprobe` 的 5 行日志全部被日志路径丢弃**（此前也多次出现：成组短突发会被丢）；
- 但时间戳给出了结论性信息：`tzlog/hyp` 在 **61.93 s** 结束，`gpmu load` 在 **64.54 s** 才开始
  —— 即 `sp_probe()` 耗时约 **2.6 秒**，这是 **访问 SP 块时的总线超时**；
- 随后设备黑屏（与之前 dump 到 `0x0EC0` 时的挂死一致）。

### 31.3 判读

- **SP/3D 块在我们这边访问会停总线**；Android 在故障时刻的 snapshot 里可以正常读同一批寄存器。
- 尚未定论的是“原因”：可能是这些块在空闲时被 power collapse（正常现象，我们的 GPU 从未跑过
  3D 作业），也可能是我们这边的块级电源/时钟确实没配上（GX GDSC 与 gfx3d RCG 都已确认 on）。
- 要判定，需要 (a) 把探针结果放进不会被丢的通道（C3 的 record/heartbeat），并 (b) 先尝试
  显式把 SP/3D 块拉起来（GPMU `SP_POWER_CNTL` / 关掉 SPTP 塌陷）再测。

### 31.4 现场

探针已从源码移除，源码回到 `98e518c`；基线镜像仍是 H236en
（kernel `fa149af7…`、boot `f6bf7668…`，已验证稳定）。

---

## 32. C3 突破：缺失的 RBCCU/SP GDSC 上电（H236eq，2026-11-10）

### 32.1 根因

kgsl 的 `a5xx_regulator_enable()` 在**每次上电**时都会通过 GPMU 打开两个 GDSC，并轮询
状态位 20（`_poll_gdsc_status`，`PWR_RETRY=100`）：

```c
kgsl_regwrite(device, A5XX_GPMU_RBCCU_POWER_CNTL, 0x778000);   // SW_COLLAPSE=0
udelay(3);
_poll_gdsc_status(..., A5XX_GPMU_RBCCU_PWR_CLK_STATUS, 1);
kgsl_regwrite(device, A5XX_GPMU_SP_POWER_CNTL, 0x778000);
_poll_gdsc_status(..., A5XX_GPMU_SP_PWR_CLK_STATUS, 1);
// 关/开 SP 时钟 + hwcg
kgsl_regrmw(device, A5XX_GPMU_GPMU_SP_CLOCK_CONTROL, CNTL_IP_CLK_ENABLE(=BIT(0)), 0);
a5xx_hwcg_set(adreno_dev, true);
kgsl_regrmw(device, A5XX_GPMU_GPMU_SP_CLOCK_CONTROL, CNTL_IP_CLK_ENABLE, 1);
```

我们**从来没有做过这一步**。后果：着色器（SP/SPTP）块一直处于塌陷状态 —— 这正是
§30/§31 观察到的“`0xE000+` 读出来是漂浮垃圾、`0x0EC0` 一读就挂总线、探针耗时 2.6 s”。

而 a540 的 ZAP 是**跑在着色器上的**：SP 块没电 → TZ 无法执行 ZAP → `CP_SET_SECURE_MODE(0)`
不被授权 → trust 恒为 1 → 经 SMMU 的内存写全部被丢。

### 32.2 修改

在 `gpu_reset()` 里、GCC 时钟打开之后，按上面的顺序加入：

```c
wr(0xa887 * R, 0x00778000u);   /* GPMU_RBCCU_POWER_CNTL */
poll rd(0xa88d * R) & (1u << 20);
wr(0xa881 * R, 0x00778000u);   /* GPMU_SP_POWER_CNTL */
poll rd(0xa88b * R) & (1u << 20);
wr(0xa880 * R, rd(0xa880 * R) & ~1u);   /* SP 时钟 */
wr(0xa880 * R, rd(0xa880 * R) | 1u);
```

### 32.3 结果（H236eq）

```
gdsc rbbu=00140000(1) sp=00140000(1)        <- 两个 GDSC 的 bit20 都置起
sp clk ctl=00008ff1
zap auth rc=0 answer=0
trust after auth=00000001
trust before 0x66=00000001
zap unsecure rptr=25/25 done=1 trust=00000000 ts=00a540c3:00000000 mem=deadbeef win=ea57beef
gpmu load -> GPMU firmware reached BABEFACE trust=00000000
```

**关键变化**：

- `trust` 从恒为 1 变成 **0**（`0x66` 终于生效）；
- `CP_MEM_WRITE` 在 scratch 页落地：`mem=deadbeef`；
- 可信窗口内的写也落地：`win=ea57beef`;
- `CACHE_FLUSH_TS` 时间戳落地：`ts=00a540c3`；
- GPMU 固件首次到达 `BABEFACE`（此前一直 `fail step 21`）。

### 32.4 遗留

`submit_probe` 仍然 `fail step 30`：它自己那条 `CACHE_FLUSH_TS`/`CP_MEM_WRITE` 序列没有落地
（读到的 ts 还是上一步的 `0xa540c3`），但同一时刻 `zap_unsecure` 的写是成功的。属于探针自身
的问题（protected-mode 包裹/顺序），不影响结论：**secure 位已解除，数据通路已打通**。

---

## 33. C3 完成（H236et，2026-11-10）

在 §32 的 GDSC 上电基础上，把提交冒烟测试放到 `gpmu_load` **之前**（原因见 33.2），C3 全流程通过：

```
gdsc rbbu=00140000(1) sp=00140000(1)
zap auth rc=0
zap unsecure rptr=25/25 done=1 trust=00000000 ts=00a540c3 mem=deadbeef win=ea57beef
submit write rptr=35/35 ts=00000000beef1234 value=c0ffee11 done=1
submit diag cpint=00000000 hwfault=00000000 fsr=00000400 rbbm=00000001 trust=00000000 me=00000000
submit test ok
GPMU firmware reached BABEFACE trust=00000000
```

判据全部满足：

- `RBBM_SECVID_TRUST_CNTL = 0`（CP 已离开 secure 模式）；
- `CP_MEM_WRITE` 在 scratch 页落地（`0xC0FFEE11`）且 `CACHE_FLUSH_TS` 时间戳落地
  （`0xBEEF1234`）——**经 SMMU 的数据通路可用**；
- 可信窗口（`0xE9000000`）内的写也落地（`0xEA57BEEF`）；
- GPMU 固件到达 `BABEFACE`；
- `cpint/hwfault = 0`，无错误。

### 33.1 根因回顾

C3 从 H236s 起卡了几十个镜像，真正缺的只有一件事：**没有像 kgsl
`a5xx_regulator_enable()` 那样，在上电时通过 GPMU 打开 RBCCU 与 SP(SPTP) 的 GDSC**
（`0x778000` + 轮询状态位 20 + SP 时钟开关）。着色器块没电 → a540 的 ZAP（跑在着色器上）
无法执行 → `CP_SET_SECURE_MODE(0)` 不被授权 → `trust` 恒为 1 → 经 SMMU 的内存写全被丢。

§30/§31 观察到的“`0xE000+` 漂浮读值、`0x0EC0` 一读就挂、探针 2.6 s”都是这个根因的**症状**，
不是独立问题。

### 33.2 发现的副作用（留给 C4）

`gpmu_load` 之后，CP 仍会推进 RPTR，但它写出的内容**不再落地**（H236es：`value` 读到的是
上一步的旧值、时间戳不更新）。所以冒烟提交必须放在 `gpmu_load` 之前。kgsl 的顺序是
`0x66 → gpmu_init → 提交`，说明我们的 `gpmu_load` 之后还缺一步 CP 重新初始化/恢复 —— C4
提交真实作业前必须先查清。

### 33.3 镜像

| 版本 | 内容 | kernel | boot |
| --- | --- | --- | --- |
| eq | 加 RBCCU/SP GDSC 上电（突破） | `9ccfc4ca…` | `de9938ec…` |
| es | 提交探针简化（写落地但 GPMU 后失效） | `638b4de2…` | `fbeb472e…` |
| **et** | 提交放在 GPMU 之前（**C3 完成**） | `e8868290…` | `b0493767…` |

---

## 34. 更正：“GPMU 之后 CP 写失效”是探针问题（H236eu–ez，2026-11-10）

§33.2 把“`gpmu_load` 之后 CP 写不落地”记成了一条真实副作用。H236eu–ez 排除了这个结论。

### 34.1 排查过程

| 版本 | 做法 | 结果 |
| --- | --- | --- |
| eu | GPMU 之后直接做写探针 | `rptr` 前进但两个写都不落地、`rbbm=1` |
| ev | 加一条 type4 寄存器写 | 内存写落地一个、另一个不落，`rbbm=e00001c3`（一直 busy） |
| ew | 加 `CP_WAIT_MEM_WRITES` + 等 RBBM 空闲 + 20 ms | `mem=a5a50001`、`ts=5a5a0002` **都落地**，`rbbm=1` |
| ey | 把 `submit_probe` 放回 GPMU 之后（kgsl 顺序）但没等空闲 | 读到旧值（读太早） |
| **ez** | 同上 + 等空闲 | `ts=beef1234`、`value=c0ffee11`、**`submit test ok`** |

### 34.2 两个真正的教训

1. **`RPTR` 前进只代表“取指”，不代表“执行完成”**。回读前必须等
   `RBBM_STATUS & 0x7e` 清零（实测 1 ms 内），再给 20 ms 让写落到内存；
   否则读到的是上一轮的旧值。
2. **H236ev 的 type4 探针写错了地址**：它用的是 dword `0x2094`，而
   `CP_MEQ_THRESHOLDS` 在我们的表里是**字节**偏移 `0x2094`（= dword `0x825`）。
   写到未实现地址会把 CP 留在 busy 状态。

### 34.3 结论

- `0x66 → gpmu_load → 提交`（kgsl 顺序）**可以正常工作**，C4 没有“GPMU 之后 CP 失效”
  这个阻塞；
- 之前的 `submit_probe` 失败是读得太早；
- 新基线：**H236ez** kernel `451c7d7c…`、boot `b936e889…`（kgsl 顺序 + 完成性等待）。

---

## 35. C4-B 第一步：真实 BO + 间接缓冲提交（H236fa/fb，2026-11-10）

### 35.1 做法

在 C3 的 SMMU 表里加入两页真实 GPU 缓冲区（`kIbIova=0x2000000`、
`kTgtIova=0x2001000`，各 4 KiB，`IOBufferMemoryDescriptor` 物理连续），然后：

1. 在 IB 页写入三条 `CP_MEM_WRITE`（目标为 `kTgtIova+0/4/8`）；
2. 目标页预填 `0xdeadbeef`；
3. 内核 ring 里提交 `CP_INDIRECT_BUFFER_PFE`(0x3F, 3 dwords: iova lo/hi/count)
   → `CACHE_FLUSH_TS` → `CP_WAIT_MEM_WRITES`；
4. 等 RPTR + RBBM 空闲 + 20 ms，invalidate 后回读目标页。

### 35.2 结果（H236fb）

```
bo submit done=1 rptr=3167/3167 ib0=703d8003 tgt=0adc0de1/feed0002/600d0003 t3=deadbeef hits=4
```

- 间接缓冲从 BO 读取并执行 ✔
- 三条 `CP_MEM_WRITE` 全部落到目标 BO ✔
- 未触碰的字保持 `0xdeadbeef`（hits=4，说明写是精确的、没有越界）✔
- 全链路 `fail step 0`（C3 + C4-B step 1）

### 35.3 踩到的坑

`ArmSmmu4KBuild` 要求 **IOVA 升序且不重叠**。第一次把两个 BO 的 range 排在
`0xE9000000` 之后，直接 `ArmSmmu4KOverlap`（`fail step 4`）。按升序插入即可。

### 35.4 下一步（C4-B step 2）

把这条路径接到用户态：`NativeA540AcceleratorProbe.cpp` 的 user client 实现
`BoAlloc/BoMap/BoCpuMap/BoFree/Submit/WaitFence`，并用 `clientMemoryForType`
把 BO 映射给调用者；现有 `NativeAdrenoUserTest.h` 的调用序列（Query →
BoAlloc×2 → BoMap → BoCpuMap → 写 IB → Submit → WaitFence → 校验）可直接作为验收。

---

## 36. C4-B step 2：用户态 ABI 端到端通过（H236fc/fd，2026-11-10）

### 36.1 实现

C3 侧（`NativeA540C3.cpp`）把单次流程扩成可复用的引擎：

- 8 个 4 KiB 真实 BO 槽（`0x2000000 + i*0x1000`，SMMU 一次建成，IOVA 升序）；
- 导出 `native_a540_gpu_ready / bo_iova / bo_bytes / bo_slots / bo_descriptor /
  submit_bo / wait_fence`；
- `submit_bo`：clean BO → `CP_INDIRECT_BUFFER_PFE`（IB 来自 BO）→ `CACHE_FLUSH_TS`
  （单调 fence）→ `CP_WAIT_MEM_WRITES` → 等 RPTR + RBBM 空闲 + 20 ms。

用户客户端（`NativeA540AcceleratorProbe.cpp`）：

- `BoAlloc/BoMap/BoCpuMap/BoCpuUnmap/BoFree/Submit/WaitFence` 全部实现；
- `clientMemoryForType(token)` 返回对应 BO 槽的 `IOMemoryDescriptor`；
- `GetDeviceInfo` 报告 BO 窗口（`va_start=0x2000000`，`va_size=8*4KiB`）。

### 36.2 踩到的坑

**引擎就绪晚于用户态测试**：backboardd 的 ABI 测试在 ~35 s 就发起 `BoAlloc`，而 C3 在 ~70 s
才完成，于是拿到 `kIOReturnNotReady`（报告 `s2 ee00002c7`）并放弃。
H236fd 给 `BoAlloc` 与 `clientMemoryForType` 加了**有界等待**（50 ms × 2400 = 120 s，
引擎就绪即放行）。

### 36.3 结果（H236fd）

用户态（backboardd）报告：

```
NATIVE_A540_ABI: report backboard s34 e0 v4/4      [172.1 s]
```

- `s34`：34 步全部完成（Query → GetDeviceInfo → BoAlloc×2 → BoMap → BoCpuMap →
  写 IB → Submit → WaitFence → 回读校验）；
- `e0`：无错误；
- `v4/4`：4 个校验字全部符合（3 个写入值 + 1 个未触碰的 `0xdeadbeef`）。

C3 侧的 `bo submit done=1 ... hits=4` 同样保持通过。

### 36.4 镜像

| 版本 | 内容 | kernel | boot |
| --- | --- | --- | --- |
| fc | ABI 方法实现（就绪不等待） | `82350417…` | `ee1b13f9…` |
| **fd** | 加就绪有界等待（**通过**） | `0f245b1b…` | `a285866e…` |

### 36.5 下一步

C4-B 的接口层已通。剩余：每连接/多队列隔离、BO 动态扩容（预映射池）、fence 语义与故障隔离，
然后进入 **C5（Fill32/Barrier/Copy32 回读）**。

---

## 37. C5a：Fill32 整页填充（H236fe–fj，2026-11-10）

### 37.1 做法

用 BO 槽 2 作 IB、槽 3 作目标（各 4 KiB，SMMU 已映射）：

1. IB 里放 `CP_MEM_WRITE` 包，把 `0xF1E2xxxx` 模式写进目标；
2. `native_a540_submit_bo(2, words, &fence)`：`CP_INDIRECT_BUFFER_PFE` 从 BO 取 IB
   → `CACHE_FLUSH_TS`（单调 fence）→ `CP_WAIT_MEM_WRITES` → 等 RPTR + 空闲 + 20 ms；
3. `wait_fence` 后 `dc ivac`，逐字回读。

### 37.2 结果

```
fill32 words=1024 hits=1024 untouch=1 fence=4 cpint=00000000 hwfault=00000000 fsr=00000400
```

- 4 KiB 目标全部命中（1024/1024）；
- 范围外的第一个字保持未写（`untouch=1`）；
- 4 次提交的 fence 递增到 4；
- 无 CP 中断/硬件故障。

### 37.3 发现的 IB 尺寸约束

| IB dwords | 结果 |
| --- | --- |
| 64（16 包） | 通过 |
| 256（64 包） | 通过 |
| **1024（256 包，正好一整页）** | **不执行**（fence 落地、目标全 0、无 fault） |

先用 256 字/次 ×4 次提交完成整页，作为 C5a 的验收。**1024 字 IB 为何不跑未定论**
（可能是 CP 预取越过 4 KiB BO 边界；后续可把 IB BO 扩到 8 KiB 再测）。

### 37.4 镜像

| 版本 | 内容 | kernel | boot |
| --- | --- | --- | --- |
| fe/ff | fill32 首测（就绪标志/大 IB） | `b7c226bd…` / `b3b54634…` | `409c0322…` / `fb77c69a…` |
| fg | 诊断（cpint/hwfault/fsr） | `e8021dfc…` | `b238b594…` |
| fh | 16 字 IB（通过） | `9b5ce31a…` | `0722813f…` |
| fi | 256 字 IB（通过） | `edd4f03c…` | `7c24f915…` |
| **fj** | 4×256 字 = 整页（**通过**） | `cd6f3e08…` | `ea9bc45a…` |

### 37.5 下一步（C5b）

C5 还剩 **Copy32**：a5xx 没有 2D/拷贝引擎，真正的 Copy32 需要一次 blit（着色器或
Mesa `fd5_blitter` 路径）。下一步是决定用最小 blit shader（自建 PM4 + 着色器）还是先接受
"Fill32+Barrier+fence" 作为 C5 的第一段验收，把 Copy32 推到 C6 前端之后。

---

## 38. C5 结项与 C6a 入口（2026-11-10）

### 38.1 C5 验收（按“Fill32 段”结项）

| 项 | 结果 |
| --- | --- |
| Fill32（`CP_MEM_WRITE`） | ✅ 1024/1024 字整页校验（H236fj） |
| Barrier（`CP_WAIT_MEM_WRITES`） | ✅ |
| 真实 fence（`CACHE_FLUSH_TS`） | ✅ 递增到 4，`WaitFence` 轮询 |
| GPU 写回、CPU 可读 | ✅ `dc ivac` 后全量比对 |
| Copy32 | ⏸ **移交 C6a** |

**Copy32 移交理由**：a5xx 的 PM4 没有内存到内存的拷贝命令；同 SoC 正例（sagit）的
`Copy32` 最终落到内置 `blit_copy_words` 着色器程序（`QcomGPUNative.cpp` 的
`encoder.copy()`），即必须走 3D/blit 管线。真正的阻塞点是 **a5xx 着色器 ISA 工具链**
（Mesa ir3 需离线编译，或手写 ISA），与 C6a 的“最小 3D 管线”是同一件事，重复拆开做没有收益。

### 38.2 C6a 入口现状

- CA/backboardd 已经会打开我们的 `IOAcceleratorES` 并发起 ABI 调用
  （日志里多种 `user client type=…` 的 open，以及 `report backboard s34 e0 v4/4`）；
- 但 `MetalPluginName` 当前指向 `NativeAdreno`（metal2vulkan → Turnip），而 Turnip
  **没有 a5xx 后端**，所以 Metal 设备创建不可能在这条路上成功；
- 因此 C6a 的第一件事不是写代码，而是**定前端路线**：
  1. 自建 Metal 前端（sagit `QcomMTL` 量级，~9k 行）；
  2. 让 CA 走 GL 渲染器（需要确认这版 CA 的开关与可用性）；
  3. 其它（不推荐移植 Turnip）。

### 38.3 建议的最小实验（C6a-0）

在**不改渲染栈**的前提下，先确认 CA 在找不到可用 Metal 设备时是否回退到 GL：

1. 把 `_offline-accelerator-plugin` 置空/指向不存在的插件，观察 CA 的日志与
   `CA::Render` 的选择；
2. 若存在 `CA_ENABLE_OGL`/`CA_DISPLAY_TYPE` 一类的偏好开关（历史研究见 STATUS 的
   ios-sweet 段），测试其是否被这版 iOS 接受；
3. 只有确认 GL 路线可行，C6b 才需要真正的渲染器移植；否则 C6 只能走自建 Metal 前端。

这一步是只读/配置级实验，不需要 GPU 代码，是 C6a 最便宜的起点。

---

## 39. C6a-0：Metal 插件开关实验（H236fk / H236fl，2026-11-10）

### 39.1 实验设置

在 `payload` 的 `unixnu.toml` 里改 `_offline-accelerator-plugin`，其余 args 与 kernel（`cd6f3e08…`，C5a）不变：

| 版本 | boot-arg | boot.img |
| --- | --- | --- |
| **fk** | 删除该参数 | `fb7b93ce…` |
| **fl** | `_offline-accelerator-plugin=NoMetalX`（不存在的 bundle） | `719dd204…` |

### 39.2 结果

| 版本 | `MetalPluginName` | 锁屏 | 打开我们的加速器 | ABI 调用 |
| --- | --- | --- | --- | --- |
| fj（参考，NativeAdreno） | `NativeAdreno source=arg` | ❌ | ✅ 174 s 起 | ✅ `report backboard s34 e0 v4/4` |
| **fk**（删除参数） | **`AGXMetalA10 source=default`** | ❌ | 未捕获（窗口止于 168 s） | — |
| **fl**（不存在的 bundle） | `NoMetalX source=arg` | ❌ | ❌ 0 次 | ❌ 0 次 |

### 39.3 结论（已修正）

> 初版把 fk 现场反馈误读成“进了锁屏”，据此推断“插件可加载时 CA 走软件渲染”。
> 实际三种配置**都没有锁屏**：当前 UI 的阻塞点仍是 backboardd 拿不到 display
> provider（屏幕只有 GOP 测试图案），与 GPU 无关。因此“锁屏是否出现”不能用来
> 判断插件行为。以下为修正后的结论。

1. 删掉参数**不是“没有插件”**：`NATIVE_UFS_ACCEL` 会回落到默认值 `AGXMetalA10`
   （`source=default`）。
2. CA 访问我们的 `IOAcceleratorES` **只经由 `MetalPluginName` 指定的插件 bundle**：
   插件可加载（fj）时 174 s 起有 `NATIVE_A540_ACCEL` 打开与 ABI 调用；插件不存在
   （fl）时 0 次。没有第二条到达加速器的路径。
3. “CA 回退到 GL”既未证实也未证伪：内核日志看不到 CA 内部的渲染器选择，而 UI
   本来就不出帧，所以这条不能用现场表现来判定；它也不构成可依赖的捷径。
4. 本次实验**没有改变**当前 gate：帧通路（display provider）和 GPU 前端是两条
   独立的待办。

### 39.4 下一步

两条并行：

1. **帧通路**：查 backboardd 为何不取/不用我们的 Legacy display provider（这是
   “frames>0”的直接阻塞，和 GPU 无关）；
2. **GPU 前端**：做一个只记录不实现的 tracing stub 插件（`MetalPluginName` 指向它），
   枚举 CA 实际调用的 MTL 选择器与参数，用来给自研 Metal 前端定范围。

---

## 40. 帧通路追踪（H236fm/fn，2026-11-10）

### 40.1 先更正两条记录

1. **selector 6 不是 swap**。按 H163 的对照，真正的交换是 selector **3/4/5**
   （SwapBegin/SetLayer/SwapEnd），6 只是 swap id/选项。§39 里“CA 真的 swap 了”
   不成立。
2. **fl/fk 两次启动只跑到 155 s / 168 s**（心跳最后一次在 146/158 s），
   fj 的加速器阶段在 174 s 才开始。所以那两次“没有锁屏、没打开加速器”只是
   **没等够时间**，不能作为结论；重跑（fm）到 279.9 s、fn 到 393.2 s 才有效。

### 40.2 新增追踪

`NativeLegacyDisplay.cpp` 加了两处有界日志（各前 8 次）：

- `kickSwapQueue()` 入口：`NATIVE_LEGACY_SWAP: kick transferred=… pending=…`
- `kickOnce()` 的 guard：`skip en/tr/pm/map/pri`、`skip req/valid`

内核 `3ecc7160…`，boot `e08eb125…`（payload 仍为 `NoMetalX`）。

### 40.3 结果（fn，393 s）

```
[155.08] client enter pid=55 comm=backboardd
[155.22] selector=8 → 438,780；29 struct=8；79 struct=1580；74 struct=64
[160.08] selector=6 in=0,80000003,0 status=0      ← 只是 swap id
NATIVE_FRAME: event=5 client=2 xfer=0 frames=0
NATIVE_LEGACY_SWAP: 0 条
selector=3/4/5: 0 次
```

- `kickSwapQueue` 从未被调用 → 不是我们的 kick/guard 丢帧；
- 3/4/5 从未出现 → CA 根本没有提交交换；
- 期间 backboardd 仍打开一次 `AGXAccelerator type=1` 并调用 `sel=2`。

### 40.4 结论

**帧通路的 gate 在 CA/userland 侧：拿不到可用的 CADisplay，就不会走
SwapBegin/SetLayer/SwapEnd**。这和有没有 Metal 插件无关（fj 与 fn 都没有 3/4/5），
也不是我们 kick 路径的 guard 问题。display 握手（8/29/79/74）与 swap id（6）都已完成，
说明缺的是更上层“显示对象成立”的条件。

下一步应围绕“CA 为什么不建 CADisplay”取证，而不是继续改 swap 实现。

---

## 41. 显示客户端取证（H236fo，2026-11-10）

### 41.1 目的

围绕“CA 为什么不建可用的 CADisplay / 不提交交换”取证：记录通知端口注册、
每个客户端的选择器直方图，并把统计塞进每 10 s 的心跳行。

### 41.2 构建注意（踩坑）

`LegacyDisplayProbe.cpp` 的改动会生效（`NATIVE_LEGACY: reg` 字符串已进内核），
但 **`NativeUfsProbe.cpp` 的改动不会**：内核链接的是预编译归档
（`scripts/build-arm-driver.py NativeUfsProbe`），
`run-h103n-build.sh` 只会按需重建 legacy display 归档，不会重建 UfsProbe 归档。
所以本轮心跳行**没有** `dpy=` 字段，显示统计留给下一次（先重建 UfsProbe 归档）。

### 41.3 结果（fo，NoMetalX，336 s）

- `NATIVE_LEGACY: reg` **0 条** → backboardd 从未注册显示通知端口；
- 选择器轨迹与 fm 相同：`88/57/15/22/8(438,780)/29/33/79/74/12/6/27/17/84/50`；
- `selector 3/4/5` **0 次**，`kickSwapQueue` 0 次，`xfer=0 frames=0`；
- `AGXAccelerator` 只打开 1 次（type=1）+ `sel=2`。

### 41.4 判读

display 侧的“握手 + swap id”都完成了，但 CA 既没注册通知端口，也没提交交换；
`kickSwapQueue`/传输/帧计数全 0 说明这**不是我们丢帧**。要么 CA 认为这个显示
不可用（但握手已过），要么它在等一个渲染器（没有可提交的内容）。

仅凭内核日志无法区分这两者：CA 的决定发生在 userland，而我们对 userland 的可见性
只有少数落到 dmesg 的字符串（历史上 SpringBoard 的
`failed to find the main CADisplay` 是以 `NATIVE_TRAP_STR` 形式出现的，且属于更早的启动）。

### 41.5 下一步选项

1. 重建 `NativeUfsProbe` 归档，让心跳带上 `dpy=`（每客户端 calls/fails/sel6/regs/3/4/5），
   至少能在 UI 静默期持续观察；
2. 若仍无法区分，则按“渲染器缺失”处理，回到 GPU 前端（stub/自研 Metal）。

---

## 42. dot-pitch 扫参实验（H236fq/fr，2026-11-10）

### 42.1 动机

参考实现（sagit，同为 A540）的 CADisplay 是 **1080×1920、pointScale=3、60 Hz**；
我们的 `selector=8` 返回 **438×780**，怀疑是点数换算，于是把 `dot-pitch` 做成
boot-arg（`offline-legacy-dot-pitch`，默认 401）试扫。

### 42.2 结果（fr，`dot-pitch=163`，281 s）

- `selector=8` 仍是 **438,780**，未随 dot-pitch 变化；
- `dpy=3/18/0/1/0`、`s345=0/0/0`、`xf=0 fr=0`，与 fp 完全一致；
- 新加的 `NATIVE_LEGACY: dot-pitch=…` 行未出现（该打印位于 nub 创建路径，
  日志窗口未覆盖），但内核确为 `0c578859…`（含参数字符串）。

### 42.3 结论

**438×780 不是由 dot-pitch 推导的**，几何换算假设关闭。修改点数不会让 CA
多走一步（18 次调用后依旧静止）。

### 42.4 附带踩坑

这次 args 加到 1022 字节，`check-bootargs-fit.py` 报 `+ zap-base` 后 1042 > 1024
（超 18 字节）。**args 必须留出 ~30 字节给 `zap-base=0x…`**，否则 ZAP 基址会被截断。
本次只做 display 实验，GPU 侧不受影响。

### 42.5 复测（H236fs，args 修正后）

fr 的 args 超限，日志里出现 `zap-base missing or invalid`，追加在末尾的
`offline-legacy-dot-pitch=163` 很可能被截断，所以 42.2 不能作为结论。

fs 版把 `sheng-disable-jobs=…` 移除（省 ~150 字节），args 874 字节，
`+ zap-base` 902/1024 通过；C3 正常（`fill32 words=1024 hits=1024`，说明 args 完整）。

结果：`selector=8` **仍是 438,780**，`dpy=3/18/0/1/0 s345=0/0/0 xf=0 fr=0` 不变。

**结论（这次有效）**：438×780 与 dot-pitch 无关，点数换算假设关闭。

---

## 43. C6a 阶段小结：display 侧暂停，转回 GPU 前端（2026-11-10）

### 43.1 本轮镜像与结果

| 版本 | 变量 | kernel | boot | 结果 |
| --- | --- | --- | --- | --- |
| fk | 删除 `_offline-accelerator-plugin` | `cd6f3e08…` | `fb7b93ce…` | 回落到默认 **AGXMetalA10**；只跑到 168 s |
| fl | `NoMetalX`（不存在的 bundle） | `cd6f3e08…` | `719dd204…` | 只跑到 155 s（等待不足，结论作废） |
| fm | 同上，重跑等 5 分钟 | `cd6f3e08…` | `719dd204…` | 到 279.9 s；`selector 6` 一次（swap id，不是交换） |
| fn | swap kick / guard 追踪 | `3ecc7160…` | `e08eb125…` | `kickSwapQueue` 0 次、3/4/5 0 次、`xfer=0 frames=0`，到 393 s |
| fo | 通知端口注册日志 | `02f80582…` | `981b3bc2…` | `NATIVE_LEGACY: reg` 0 条；到 336 s |
| fp | 重建 UfsProbe 归档 + display 心跳 | `2dbddebe…` | `eb3b6f26…` | `dpy=3/18/0/1/0 s345=0/0/0`，345→415 s 完全静止 |
| fr | dot-pitch=163（args 超限） | `0c578859…` | `2bef009e…` | **无效**：`zap-base missing`，参数被截断 |
| fs | dot-pitch=163（args 修正） | `0c578859…` | `0833d08e…` | 仍 438×780 → dot-pitch 与尺寸无关 |

### 43.2 站得住的结论

1. **`MetalPluginName` 是 CA 访问我们加速器的唯一通道**：插件可加载时 174 s 起有
   `NATIVE_A540_ACCEL` 与 ABI 调用；插件不存在时 0 次。
2. 删掉参数会回落到**默认 `AGXMetalA10`**，不是“无插件”。
3. **CA 从不提交交换**：`selector 3/4/5` 在所有配置下都是 0 次；`kickSwapQueue`
   与传输/帧计数也全为 0——不是我们丢帧。
4. display 客户端在握手后**永久静默**（18 次调用、0 次通知端口注册），
   说明 CA 主动放弃了该显示，而不是在等渲染器/轮询。
5. `selector=8` 报 **438×780**（canvas 1080×1920），与 dot-pitch 无关。
6. 参考实现（sagit）的关键 gate 是 **MobileGestalt 的屏幕记录**（其旧缓存
   `1080,1920,429,scale=0` 会让 FBS 拒绝；删缓存重算 scale=3 后 CADisplay 正常）。
   我们的 Data 是每次重建的 RAM disk，MG 理论上每次重算，但**结果在 userland 不可见**。

### 43.3 已排除 / 作废

- “删插件会让 CA 回退 GL”（现场无锁屏，无法判定，且 UI 本来就不出帧）；
- “CA 在没有插件时会走软件渲染并交换”（fm 证明 `selector 6` 不是交换）；
- “dot-pitch 决定报告尺寸”（fs 有效复测）；
- fl/fk 的“没打开加速器”（等待时间不足，非结论）。

### 43.4 决定

display 侧暂停，转回 **GPU 前端**：内核可见信号已用尽，而 GPU 前端有自研 ABI，
每一步可度量。display 的未解问题原样记录：

- 报告尺寸 438×780 的来源（与 canvas/dot-pitch 均无关）；
- MobileGestalt 屏幕记录的实际值（需要 userland 可见性）；
- 通知端口从不注册的原因。

---

## 44. GPU 前端第一探：现有插件的 publish 模式（H236ft，2026-11-10）

### 44.1 做了什么

`drivers/NativeMetal/NativeAdrenoMetalPlugin.mm` 的 principal class
`NativeAdrenoMetalDevice` 有两条路：

- 默认（无标记）：跑共享 ABI 自测后**返回 nil**——这就是 CA 反复重开加速器的原因；
- publish（`/System/Library/Extensions/NativeAdrenoMetal.publish` 存在）：返回真正的
  Metal 设备（metal2vulkan → Turnip）。

`pack-adreno-addon.py` 增加 `addons/NativeAdrenoMetal.publish`（`addons/` 由
`zzy-native-gpu-addon-mount` 挂到 `/System/Library/Extensions`），重打 addon
（12,125,860 B），payload 只换 `Payloads/kernel.macho.gpuaddon` 与插件名
（`NativeAdreno`），内核不变（`0c578859…`）。boot `07205fb6…`。

### 44.2 结果（ft，360 s）

```
open request ×378        （160→351 s，约 2 次/秒，持续重试）
ABI method=1 (Query) + method=15 (GetDeviceInfo) ×14 对，之后无 BoAlloc/Submit
dpy=8/56/0/0/0  s345=0/0/0  xf=0 fr=0
```

- publish 模式生效：插件真的打开了加速器并查询了设备信息（默认模式只有一次自测）；
- 但查完就放弃并重试——**Turnip 没有 a5xx 后端**，Metal 设备创建仍然失败；
- display 侧客户端数升到 8、调用 56 次，但依然没有 3/4/5。

### 44.3 结论

现有 metal2vulkan/Turnip 通路在 a5xx 上走不通，publish 模式只能把失败点从
“返回 nil”推进到“查完设备信息后放弃”。**GPU 前端只能自研**：自己实现
`_MTLDevice` 子类，直接接我们的 ABI，或给 Turnip 加 a5xx 后端。

---

## 45. A1 追踪设备（H236fu，2026-11-10）

### 45.1 已落地

- **内核日志通道**：ABI 新增 `NativeAdrenoMethodLog = 17`
  （`NativeAdrenoAbiLog{bytes,reserved,text[184]}`），分发到
  `IOLog("NATIVE_MTL: %s")`，换行被替换、最多 1200 行；内核 `3f29aec7…`。
- **插件追踪设备**：`A540TraceDevice : _MTLDevice`，由
  `NativeAdrenoMetal.trace` 标记启用；把 CA 的 `name/registryID/maxBufferLength/
  supportsFeatureSet:/supportsFamily:/newCommandQueue/newBufferWithLength:options:/
  newTextureWithDescriptor:/newRenderPipelineStateWithDescriptor:error:/…`
  逐条写进内核日志（`MTL#<seq> <class> <selector> <detail>`，预算 600 行）。
- **打包**：`pack-adreno-addon.py --trace`（标记）、`--publish`（旧路径），
  并容忍缺失的 `adrenoprobed`/daemon plist。

### 45.2 首次结果（fu，298 s）：追踪设备没有跑起来

- `NATIVE_MTL` **0 行**；`NATIVE_A540_ACCEL: open request` 仅 **1** 次、
  无 ABI 调用；`dpy=3/18/0/1/0`、`accel=1/1/1/2` —— 与“插件不存在”时完全一致。
- 判断：重编译的 bundle **缺少 `libvulkan_freedreno.dylib`**（旧 bundle 里有），
  dlopen 失败 → CA 拿不到任何 Metal 设备，行为退回无插件状态。

### 45.3 下一步（A1 收尾）

1. 把 `build/mesa-tu-ios/src/freedreno/vulkan/libvulkan_freedreno.dylib` 复制进
   bundle（或改为 trace 模式不需要它再做一次编译开关）；
2. 重新签名、`pack-adreno-addon.py --trace`、换 payload 的 gpuaddon；
3. 启动后应出现 `NATIVE_MTL: MTL#…` 行：即产出物 1（方法清单/顺序）与
   产出物 2（参数形状）；最后一行就是产出物 3（放弃点）。

### 45.4 第二次尝试（H236fv）：补回 dylib 后仍不加载

- 用 `-Os`（去掉 `-g`）重编插件、strip、补回 `libvulkan_freedreno.dylib`、
  重新签名；addon 12,103,700 B（与旧可用 addon 12,125,780 B 同量级），
  boot 81,149,952 B（与历史一致，未超窗）。
- 结果与 fu 完全相同：`NATIVE_MTL` 0 行、`open request` 1 次、ABI 0 次、
  `accel=1/1/1/2`、`dpy=3/18/0/1/0` —— 仍然是“插件不存在”的行为；
  内核自身正常（C3/fill32 都在跑）。

结论：**重打的 bundle 没有被 CA 当作可用插件加载**。两个候选原因：

1. addon 内容结构变了（新 blob 里没有 `bin/adrenoprobed` 与 `daemons/*.plist`，
   旧 blob 有），内核侧的 addon 挂载/校验可能因此跳过或拒绝；
2. 手工 `codesign` 的 bundle 与官方脚本产物的签名/权限不同，dlopen 被拒。

下一步（按成本排序）：

1. 先把 `adrenoprobed` 与 daemon plist 重新生成并放回 addon（恢复旧的文件集合），
   重打后只观察“是否加载”（有 `NATIVE_MTL` 即成功）；
2. 若仍不加载，改用官方 `build-adreno-metal-plugin.py` 产出（需要在宿主机装
   `glslc`，或临时跳过 smoke shader / bridge 重建两步）；
3. 二者都可时，再继续 A1 的三份产出物。

### 45.5 第三次尝试（H236fw）：恢复完整文件集合后日志窗口过短

- addon 恢复为 9 个条目（bundle + `adrenoprobed` + 3 个 daemon plist + trace 标记），
  12,119,420 B；boot 81,149,952 B。
- 内核正常：`fill32 words=1024 hits=1024`、C3 全通。
- 但合并日志只到 **163 s**（`NATIVE_FRAME: event=1 … client=0 xfer=0 frames=0` 之后即止），
  **未覆盖 174 s 起的加速器阶段**，因此这一轮对“插件是否加载”**不可判定**。

下一步：重跑同一镜像并确认日志窗口能到 300 s 以上（或改用 `h103-log-secs`/更长等待），
再看 `NATIVE_MTL` 是否出现。若窗口仍短，先查 H103 写盘窗口为何在部分启动里只到 ~160 s。

### 45.6 现场观察：左上角面板第 4 格变色

fw 这轮现场看到左上角 2×2 面板的“第 4 格”不再是绿色后才重启。面板语义
（`NativeUfsProbe.cpp` 顶部三格 + `NativeLegacyDisplay.cpp` 的 2×2）：

| 位置 | 含义 |
| --- | --- |
| 左上三小格（从左到右） | CPU 频率 / A540 加速器 / 心跳 |
| 2×2 左上 | 启动阶段 |
| 2×2 右上 | 显示客户端 |
| 2×2 左下（上下两半） | swap 校验（紫）/ 传输（白）/ 未传输（黑） |
| 2×2 右下（上下两半） | IOKit 匹配状态（紫/蓝/橙/黑） |

“第 4 格变色”若指的是加速器格，说明这一轮的加速器状态与之前不同（可能插件
真的打开了加速器），但合并日志只到 163 s，没有覆盖到那一段 → 需要重跑并确保
日志窗口 ≥300 s 才能判定。

### 45.7 更正：左上角是四格，第 4 格 = 持久日志写入器

按 `docs/zh/devices/cheeseburger/display-colors.md`，左上角 `(0,0)/(20,0)/(40,0)/(60,0)`
四格依次是：CPU 频率、A540 加速器 probe、心跳、**H103 持久日志 slot 写入器**。
第 4 格“绿”= 至少成功写过一个 slot 与 header；红=写入分支未进入；蓝=2 秒 slot
线程已进入但写窗口未就绪；黄=窗口就绪但尚未写成功。

现场看到第 4 格**不是绿色**再重启 → 说明这轮的持久日志**没有正常写入**，
这正好解释 fk/fl/fu/fv/fw 几轮日志窗口只到 155–168 s：**是日志写盘的问题，
不是系统停在那个时刻**。

因此之前的“窗口过短，不可判定”应改为“写盘失败，需要先修写入器”。
下一步：确认第 4 格的具体颜色（红/蓝/黄），对应检查
`fLogFirst/fLogBlocks/fLogDma/fReady/fLock` 的就绪条件，再复跑 A1。

### 45.8 fw 重跑（日志正常，411 s）：确认插件未加载

第 4 格（日志写入器）= 绿，合并日志到 **411 s**，结论可以定了：

```
NATIVE_MTL:        0 行
open request:      1 次
ABI method:        0 次
```

即：**窗口够长时，重打的 bundle 依然没有被加载**。之前 fu/fv/fw 的短日志确实是
写入器故障（第 4 格非绿），与插件问题无关。

剩余两个候选（按排查成本排序）：

1. **addon 未被挂载/白名单校验拒绝**：验证方法——保留**原始可用 addon**，只在 addon
   里加一个 `addons/NativeAdrenoMetal.trace` 标记（不改代码）；若启动后出现 ABI 自测
   调用（原插件会跑测试路径），说明挂载正常、问题在重打的二进制/签名；若仍 0 次，
   说明问题在 addon 挂载这一层。
2. **二进制/签名**：用官方 `build-adreno-metal-plugin.py` 全流程产出（需 `glslc`，
   或临时跳过 smoke shader 与 bridge 重建两步），与手工编译产物对比。

### 45.9 判别结果（fx）：addon 机制没问题，是**重打的 bundle 不加载**

- fx 用“原始 bundle + publish/trace 两个标记”的 addon（手工在 ft 的 blob 后追加条目），
  结果 `MTL 0 / opens 1 / abi 0` —— 与“无插件”一致；
- 但 **ft**（packer 正常产出、只有 publish 标记、12,125,860 B）当时是**成功加载**的
  （378 次 open + Query/GetDeviceInfo 成对）。

所以：

| 结论 | 依据 |
| --- | --- |
| addon 挂载/替换机制可用 | ft 用同一路径成功加载了插件 |
| 失败的是**重打的 bundle 本身** | fu/fv/fw（重编译的 trace bundle）全部表现为“无插件” |
| fx 不可作证据 | 手工追加条目的 blob 很可能格式不合法（追加后 repair 段/尺寸需同步） |

下一步聚焦“重打的 bundle 为何不加载”：

1. 对比 ft 的 bundle 与 fu 的 bundle：文件集合（旧的有 `adrenoprobed`/`libvulkan`/`_CodeSignature`）、
   `codesign -d --entitlements` 输出、`Info.plist` 字节；
2. 用官方 `build-adreno-metal-plugin.py` 全流程产出（装 `glslc` 或临时跳过两步），
   再把 trace 代码合进去，确保签名/权限与 ft 一致。

### 45.10 官方全流程构建（fy）：仍然不加载 → 问题在“重打的二进制”

- 用官方 `build-adreno-metal-plugin.py` 完整构建（对 `glslc` / 桥接归档缺失做容错），
  产出 4K 签名 bundle + daemon + trust.json，packer `--trace` 打 addon（12,127,340 B）。
- 结果依旧：`NATIVE_MTL 0 / opens 1 / abi 0`（281 s）。

对照：

| 二进制来源 | 是否加载 |
| --- | --- |
| ft：11-08 的原始 bundle | ✅（378 open + Query/GetDeviceInfo） |
| fu/fv/fw：手工编译（含/不含 dylib） | ❌ |
| fy：官方脚本重建 | ❌ |

结论：**addon 与签名链路都正常，是重编译出的可执行文件本身没被加载**（主类方法从未被调用，
连 ABI 自测都没跑）。

下一步（下轮首选）：做**独立的最小 trace 插件**——新 bundle 名（如 `A540Trace`）、
**不链接 bridge/Turnip**、只含 `A540TraceDevice` + ABI Log 调用；`MetalPluginName=A540Trace`。
这样排除所有第三方依赖后，若仍不加载，问题就在“bundle 被 CA 接受的条件”本身；
若加载，则 A1 的三份产出物即可拿到。

### 45.11 独立最小插件（ga/gb）：仍不加载，指向“Data seed 才是真正的插件来源”

- ga：独立 `A540Trace.bundle`（只依赖 Foundation/IOKit/Metal，86 KB），
  `MetalPluginName=A540Trace`，addon 仅 4,832 B → `MTL 0 / opens 1 / abi 0`（277 s）。
- gb：改为使用 Metal 传入的 accelerator 端口，不再自己 `IOServiceOpen` →
  仍然 `MTL 0 / opens 1 / abi 0`（410 s，窗口正常）。

结合 ft（原始 bundle + publish 标记 → 378 次 open、插件确实运行）：

**最可能的解释**：addon 挂载只让“标记文件”生效，而 **bundle 本体来自 Data seed**
（`add-gpu-plugin-data.py` 写入 `/private/var/ngpu/addons`，再由 mount 覆盖到
`/System/Library/Extensions`）。ft 之所以成功，是因为它用的就是 seed 里那份旧 bundle；
我们换掉 addon 里的 bundle 并没有换掉 seed 里的那份。

下一步（下轮直接做）：

1. 在 Mac 上用 `add-gpu-plugin-data.py`（或等价流程）把**新的 A540Trace.bundle**
   写进 payload 的 `scratch-data.img`（Data seed）；
2. `MetalPluginName=A540Trace`，addon 里只放标记/不需要的旧 bundle 都可以；
3. 启动后应出现 `NATIVE_MTL: dev#…`，即 A1 三份产出物。

### 45.12 Data seed 更新（下一步的第一步，遇到体积问题）

- 从 `payload-H236ga.img` 取出 `Payloads/scratch-data.img`（3,219,600 B），
  在 Mac 上跑 `scripts/add-gpu-plugin-data.py ~/seed-ga.img ~/seed-trace.img`
  → 输出 **42,087,728 B**（因为要写入 `NativeAdrenoMetal.bundle` 的 21.7 MB 可执行文件
  与 17 MB `libvulkan_freedreno.dylib`）。
- payload 镜像当前只剩 ~11 MB 余量、boot image 已到 81,149,952 B，直接换 seed 会**超限**。

下一步（按顺序）：

1. trace 路径并不需要 Turnip：把 `libvulkan_freedreno.dylib` 从
   `NativeAdrenoMetal.bundle` 里去掉（或单独准备一个不含它的 bundle 目录）后重跑 seed 更新；
2. 若仍超限，则精简 payload 其它内容或按设备仓库的 payload 布局扩容；
3. seed 换进去后用 `MetalPluginName=NativeAdreno` 启动，确认 `NATIVE_MTL`。

这条路径是目前唯一还没试过的“换对地方”：addon 只提供标记、bundle 由 seed 提供。

### 45.13 去掉 libvulkan 后仍超预算；改用 86 KB 的独立 bundle 进 seed

- 去掉 `libvulkan_freedreno.dylib` 并重签后，seed 从 42,087,728 B 降到
  **25,162,032 B**，但 payload 只剩 ~11 MB、boot image 已顶到 81,149,952 B，
  仍然放不下。
- 另有一个命名约束：seed 里的目录名是 `NativeAdrenoMetal.bundle`（21 字符），
  超过 `_offline-accelerator-plugin` 的 16 字符上限，所以 seed 里的这个名字
  **本来就无法用 boot-arg 指到**。

结论：seed 路线要用**独立的最小 bundle**——我们的 `A540Trace.bundle` 只有 86 KB
（`build/a540-trace/A540Trace.bundle`），把它按 `A540Trace.bundle` 放进 seed，
`MetalPluginName=A540Trace`，seed 几乎不增长，完全放得下。

下一步实现：给 `add-gpu-plugin-data.py` 加一个“把指定 bundle 目录按指定名字写进
seed”的模式（或写个同构的小脚本），然后：

1. seed 写入 `ngpu/addons/A540Trace.bundle`；
2. payload 换 seed、`MetalPluginName=A540Trace`；
3. 启动看 `NATIVE_MTL`。

### 45.14 根因：AMFI 拒绝 ad-hoc bundle（信任缓存里没有它的 CDHash）

gc 的日志第一次给出明确原因（之前所有"插件没被加载"其实是**加载被拒**）：

```
AMFI: '/System/Library/Extensions/A540Trace.bundle/A540Trace' is adhoc signed.
AMFI: ... unsuitable CT policy 0 for this platform/device, rejecting signature.
Library Validation failed: Rejecting '.../A540Trace' (Team ID: none, platform: no)
  for process 'backboardd(56)' (Team ID: N/A, platform: yes),
  reason: mapping process is a platform binary, but mapped file is not
```

boot 镜像里一直带着 `Payloads/kernel.macho.trustcache`（61,456 B，module 0 = 自建 owner 模块
+ 两个原始 Apple 模块）。**ft 之所以能加载，就是因为那份缓存里有原始插件的 CDHash**；
我们后来重打的 bundle 换了 CDHash，缓存里没有，于是被拒。

新增 `scripts/add-owner-trust-hash.py BASE HASH OUTPUT`：把新 CDHash 插进 owner 模块并重排
（不改 Apple 模块，格式按 DarwinBoot `ValidTrustCaches` 自检）。构建机上没有
`build/original-static-system-trust/original-static-system.bundle`，所以不能重跑
`make-owner-trust-bundle.py`，只能增量插入。

### 45.15 addon 与 Data seed 都成立，但两者必须是同一份构建

`NATIVE_GPU_ADDON: plugin=A540Trace files=3 written=3` 说明 addon 会**覆盖** seed 里的同名 bundle，
所以信任缓存里的 CDHash、seed 里的可执行文件、addon 里的可执行文件三者必须字节一致，
否则又是"签名不匹配"。本轮把 seed 与 addon 都从同一个 `build/a540-trace/A540Trace.bundle` 生成。

### 45.16 独立插件正式加载成功（gf）

```
NATIVE_MTL: +load tunnel=1 selector=0   ×12
```

bundle 被 dlopen（每条 +load 都是新进程），ABI 通道可写（tunnel=1），
但 Metal 从没实例化主类。原因在 gh/gm 才看清。

### 45.17 +load 里调 ABI 会杀掉 backboardd（gg）

`+load` 后紧跟 `NATIVE_EXIT: pid=56 comm=backboardd status=0x6 ns=2 code=0x6`（SIGABRT）。
把 ABI 调用移到 `+initialize` 后仍然 exit 6 → 不是 ABI 调用本身。

### 45.18 真正崩溃点：返回未初始化的 `_MTLDevice`（gj/gl）

gi/gj 的日志（`+alloc`、`-doesNotRecognizeSelector:` 追踪）给出完整序列：

```
dev#1 initialize loaded=1
cls#2 alloc
dev#3 initWithAcceleratorPort: port=0x8007     ← 方法确实被调用
（随后 backboardd SIGABRT，约 50 ms 后）
```

- `+alloc` 改成 `class_createInstance` 后一样崩 → 崩点不在 `_MTLDevice +alloc`。
- `initWithAcceleratorPort:` 里**只记一行、不碰端口**也崩（gk）→ 崩点在方法返回之后。
- 结论：`_MTLDevice` 带有 Metal 自己的内部状态；直接分配/初始化的桩实例交回 Metal 后，
  Metal 立刻在自身代码里中止。

### 45.19 原插件的写法就是答案（gm）

`NativeAdrenoMetal.mm` 的注释（H193）已经写过同一件事：`_MTLDevice -init` 对插件自建实例
返回 nil。把 `initWithAcceleratorPort:` 改成**记完就 `return nil`**（与原插件一致）后：

```
dev#1 initialize loaded=1
cls#2 alloc
dev#3 initWithAcceleratorPort: port=0x8107
dev#4 dealloc                     ← Metal 放手，不再崩在自身代码里
（9 次；backboardd 退出次数从 15 降到 9；accel opens=27 abi=45）
```

### 45.20 A1 的第三份产出物：放弃点已确定

Metal 对插件设备的调用顺序是：

1. `NSBundle` 载入 → `+load`
2. `NSClassFromString(NSPrincipalClass)` → `+initialize`
3. `+alloc`
4. `-initWithAcceleratorPort:(unsigned)` ← **唯一一个带参调用**
5. 若从此方法拿不到**可用的**设备实例，就 `-dealloc` 并放弃（不会调用 `name`、
   `registryID`、`newCommandQueue`、`newBufferWithLength:options:` 等任何方法）

所以 A1 的"放弃点"是第 4 步本身的返回值，而不是某个 GetDeviceInfo/属性查询；
这解释了为什么之前所有"让桩设备返回 nil 以外的东西"的尝试都会把 backboardd 打死。
要拿到方法清单，必须交回一个 Metal 真正认的设备（即 C6a 的正路），
桩设备只能证明"发现路径已经走到这里"。

### 45.21 `_MTLDevice` 没有 `-initWithAcceleratorPort:`（gn）

插件声明该方法后调用 `[super initWithAcceleratorPort:port]`：

```
dev#3 initWithAcceleratorPort: port=0x690b
dev#4 doesNotRecognize: initWithAcceleratorPort:
dev#5 initWithAcceleratorPort: super=nil
```

→ 真实 `_MTLDevice` **没有**这个实现；设备必须由插件自己造。返回 nil 时进程安然无恙
（backboardd 退出 0 次）。

### 45.22 纯 NSObject 设备停在 `+initialize`（go/gp）

去掉 `_MTLDevice` 继承后，两次启动都只有 `dev#1 initialize`，**没有 `+alloc`**：
Metal 在实例化前就用类做了一次检查（很可能是协议/父类检查），不通过就不分配。

### 45.23 abort 的真正原因：设备类必须同时声明 `MTLDevice` 和 `MTLDeviceSPI`（gq）

`NativeBridgeMetalFrontend.mm:1488` 里发布路径的写法就是答案：

```
Class base = objc_getClass("_MTLDevice");
if (class_getInstanceSize(base) != 536) return nil;      // iPadOS 17.7.11 ABI
Class cls = objc_allocateClassPair(base, "NativeBridgeMetalDevice", 0);
… 拷贝方法表 …
class_addProtocol(cls, @protocol(MTLDevice));
if (Protocol *spi = objc_getProtocol("MTLDeviceSPI")) class_addProtocol(cls, spi);
objc_registerClassPair(cls);
gDeviceObject = [cls new];
```

源码注释写得很直白：**"The original registration (`_MTLAddDevice`) asserts that a plugin's
device conforms to Metal's private device protocol as well"** —— 我们此前交回的静态
`_MTLDevice` 子类没有声明 `MTLDeviceSPI`，注册断言就是以 SIGABRT 结束的。

trace 插件已按同样方式改造：运行时在 `_MTLDevice` 上派生 `A540TraceRuntimeDevice`，
拷贝日志方法，加上两个协议，再由 `initWithAcceleratorPort:` 返回 `[cls new]`。
未实现的 selector 会落进 `-doesNotRecognizeSelector:`，正好就是 A1 的方法清单。

（gq 那次启动窗口偏短，只到 `dpy=2/18`，还没走到实例化，需要再跑一次确认。）

### 45.24 A1 达成：插件设备被 Metal 接受，方法清单与放弃点拿到了（gs）

把静态主类改回 `_MTLDevice` 子类，并在 `+load` 里 `class_addProtocol` 补上
`MTLDevice` 与 `MTLDeviceSPI` 之后（H236gs），Metal 完整地驱动了这个桩设备：

```
dev#1 initialize loaded=1
dev#2 cls alloc
dev#3 initWithAcceleratorPort: port=0x5e0f
dev#4 initWithAcceleratorPort: device=returned
dev#5 doesNotRecognize: featureProfile
dev#6 maxBufferLength
dev#7 doesNotRecognize: featureProfile
dev#8 doesNotRecognize: featureProfile
dev#9 newCommandQueue            ← 返回 nil，Metal 放弃
```

14 次重复，全部序列一致；`ABI: method=17` 共 31 条，`accel=27/0/140/0`。

**A1 产出物 1（方法清单与首次调用顺序）**：设备建立阶段 Metal 只问 4 个消息——

| 顺序 | selector | 类型 | 说明 |
| --- | --- | --- | --- |
| 1 | `-featureProfile` | 私有 SPI 属性 | 连问 3 次（第一次在 `maxBufferLength` 之前，两次在其后） |
| 2 | `-maxBufferLength` | 公开 | 只问一次 |
| 3 | `-newCommandQueue` | 公开 | 唯一带副作用的创建调用 |

**A1 产出物 3（放弃点）**：`-newCommandQueue` 返回 nil → Metal 立刻放弃整个设备，
不会继续问 `newBufferWithLength:options:`、`newRenderPipelineStateWithDescriptor:`
或任何设备属性。之前所有"在 GetDeviceInfo 阶段放弃"的推测都不成立：真正卡住的是一个
**命令队列**，而不是设备信息。

**A1 产出物 2（参数形状）**：`newCommandQueue` 与 `maxBufferLength` 都不带参数；
`featureProfile` 也不带参数（返回的是 SPI 字典）。带参调用要等到队列建立之后才会出现，
所以下一步是把这两步做实：
1. `-featureProfile` 返回一个包含 Metal 私有所需键的 `NSDictionary`（可先返回空字典看它是否接受）；
2. `-newCommandQueue` 返回一个同样是"运行时 `_MTLDevice`…不，是队列对象"的桩，并对它
   记 `-commandBuffer`、`-setLabel:`、`-insertDebugCaptureBoundary` 等后续调用。

这样放弃点会一步步向后推，直到出现 `newBufferWithLength:options:` 与
`newRenderPipelineStateWithDescriptor:` 的形状记录。

### 45.25 A1 完整清单（逐步推进）：设备 → 队列 → 深度模板 → 能力查询

每接受一个私有 setter，放弃点就后退一步（每轮 13 次重复，顺序完全一致）：

| 版本 | 新增实现 | 新的放弃点 |
| --- | --- | --- |
| gs | — | `newCommandQueue` 返回 nil |
| gu | `newCommandQueue` 返回桩队列 | `queue -setLabel:` 之后 `-setSubmissionQueue:` |
| gv | `-setSubmissionQueue:` | `-setCompletionQueue:` |
| gw | `-setCompletionQueue:`（及同类 void setter） | 队列建立完成，回到设备：`-newDepthStencilStateWithDescriptor:` → `-supportsFamily:1001` ×2 后进程退出 |

gw 的完整序列（14 个消息，5 次重复）：

```
dev  +initialize
dev  +alloc
dev  -initWithAcceleratorPort:(port)
dev  -featureProfile                  (nil，3 次)
dev  -maxBufferLength                (一次性)
dev  -newCommandQueue                → 桩队列
queue -setLabel:
queue -setSubmissionQueue:           (私有：IO 提交队列)
queue -setCompletionQueue:           (私有：IO 完成队列)
queue -device                        (回指)
dev  -newDepthStencilStateWithDescriptor:   （带 descriptor，返回 nil）
dev  -supportsFamily: 1001 ×2        (Apple1；桩返回 YES)
```

**A1 产出物 2（参数形状）**已经有两条：
- `-newDepthStencilStateWithDescriptor:` 接受一个 descriptor 对象（非 nil）；
- `-supportsFamily:` 的参数是 `MTLGPUFamily` 枚举，render server 先问 **1001（Apple1）**。

`-featureProfile` 若返回空字典，Metal 反而更早放弃（gt）；必须先保持"未实现=返回 nil"，
它才会走到 `maxBufferLength` 与队列创建。

现在最后一个失败点在 `supportsFamily:1001` 之后：桩对所有 family 都回 YES，
Metal 随后进入只有真设备才有的内部路径并以 SIGABRT 结束（每轮恰好 1 次 backboardd 退出）。
下一步：让 `supportsFamily:` 只对**已知为空**的 family 回 NO，看 Metal 走兼容回退时还会问什么。

### 45.26 `supportsFamily:` 改为回 NO（gx，待上机验证）

gw 的最后一次崩溃发生在 `supportsFamily:1001` 之后：桩对所有 family 都回 YES，
Metal 于是进入只有真设备才有的内部路径并以 SIGABRT 结束（每轮恰好 1 次 backboardd 退出）。
gx 让 `supportsFamily:` 一律回 **NO**，预期 renderer 走兼容回退分支，把询问继续下去。

镜像：`/tmp/opencode/boot-H236gx.img`（81,149,952 B，sha256 `59f9d426be972425b6628ce24691ef16…`），
插件 cdhash `3933175c1ad4676963c18209d8a281ce82c495e7` 已写入信任缓存。**尚未上机。**

### 45.27 下一台设备主机：192.168.8.58（重要）

手机上机的宿主主机从 `ls@192.168.10.225`（Windows/PowerShell）换成 **`192.168.8.58`**。
需要同步调整：

- `/tmp/opencode/rssh.sh` / `rscp.sh` 指向的是 Mac（`192.168.10.103`），**不变**；
- `/tmp/opencode/rwin`、`askpass-win.sh`、`known_hosts_win` 用的是 10.225，**换成 8.58**；
- 部署/抓日志的三段式不变：
  1. scp `boot-H236*.img` 到手机宿主的 `D:/Users/ls/Documents/OnePlus5_ios/`（或新主机上的同一路径，
     上机前先确认路径与 fastboot/adb 可执行文件位置）；
  2. `adb reboot bootloader` → `fastboot boot <img>`；
  3. TWRP 下 `blockdev --flushbufs` + `dd` 拉 `userdata_ios` 的日志区，再用 `scripts/h103-log-pull.py` 解析。
- 用户会在**手机连好 8.58 之后通知**，收到通知再部署，不要提前假设在线。

上机后要做的第一件事：确认 gx 的 `NATIVE_MTL` 序列是否出现新的 selectors
（预期在 `supportsFamily:1001` 之后继续，且不再每轮 SIGABRT）。

### 45.28 设备主机切换的落地状态（2026-11-11）

- `192.168.8.58` 的 SSH **在线**，但用旧主机的账号/口令（`ls` / askpass 里的口令）
  认证失败：`Permission denied (publickey,password,keyboard-interactive)`。
  上机前需要用户确认：用户名、口令、以及手机镜像目录（旧主机是
  `D:/Users/ls/Documents/OnePlus5_ios/`）与 adb/fastboot 路径。
- 已把本地助手改成可切换主机（都在 `/tmp/opencode`，不在仓库里）：
  - `rwin`：读 `WIN_HOST`（默认 192.168.10.225）；
  - `rwin8`：`WIN_HOST=192.168.8.58` 的包装；
  - `rwscp LOCAL REMOTE`：按同一主机把文件推到宿主的 `REMOTE`。
  认证凭据确认后只需改 `askpass-win.sh`，无需改命令。
- 已经打包好、**只等上机**的镜像：`/tmp/opencode/boot-H236gx.img`
  （81,149,952 B，sha256 `59f9d426…`，插件 cdhash `3933175c…` 已在信任缓存中）。

### 45.29 gx 的真正失败原因是缺四个 `_MTLAddDevice` 初始化器（gz）

gx 的日志把崩溃点钉死了：

```
dev#15 supportsFamily: family=1001
dev#16 supportsFamily: family=1001
NATIVE_TRAP: pid=56 comm=backboardd exc=1 code=0x1 sub=0x0 sig=11
NATIVE_EXIT: pid=56 ... status=0xb ns=2 code=0xb
```

既不是"selector 没答"（`doesNotRecognize:` 一行都没有），也不是 `supportsFamily:` 返回值的
问题（回 YES 和回 NO 都是同一个崩点）。

答案在**我们自己的桥**里（`NativeBridgeMetalFrontend.mm:1243`）：

> "The original discovery (`_MTLAddDevice`) runs these four on every device it registers."
> `-initLimits` / `-initFeatureQueries` / `-initGPUFamilySupport` / `-initWorkarounds`

目标机的这四个实现会从 `featureProfile` 和 Apple GPU 表里**填基类的 limits/feature 表**。
桩设备没有实现它们 → 走 `_MTLDevice` 基类实现 → 基类读它自己未初始化的表 →
`supportsFamily:` 时 SIGSEGV。桥设备把这四个实现成空体，正是为了避开这件事。

gz 的做法：`_MTLDevice` 基类 + 四个空初始化器（并各记一行），`supportsFamily:` 仍回 NO。
这是有据可依的修复，不是试错。

镜像：`/tmp/opencode/boot-H236gz.img`（81,149,952 B，sha256 `aee8ac9d…`，
插件 cdhash `94e43329…` 已入信任缓存）。

### 45.30 gz：四个初始化器让注册走通了，但 Metal 仍在"设备内部状态"上 SIGSEGV

gz 的序列（16 次重复，完全一致）：

```
dev#1  +initialize
dev#2  +alloc
dev#3  -initWithAcceleratorPort: port=0x470b
dev#4  -initWithAcceleratorPort: device=returned
dev#5  -initLimits empty
dev#6  -initFeatureQueries empty
dev#7  -initWorkarounds empty
dev#8  -newCommandQueue queue=stub
queue#9  -setLabel:
queue#10 -setSubmissionQueue:
queue#11 -setCompletionQueue:
queue#12 -device
dev#13 -newDepthStencilStateWithDescriptor: descriptor=1
（38 ms 后）NATIVE_TRAP: pid=56 comm=backboardd exc=1 code=0x1 sub=0x0 sig=11
```

要点：

1. **四个初始化器确实被 `_MTLAddDevice` 调用**（`initLimits` / `initFeatureQueries` /
   `initWorkarounds` 各一次；`initGPUFamilySupport` 在 featureProfile 为空时不会被调用）。
   这解释并修正了 gx 的判断。
2. 有了它们之后，Metal **不再问** `featureProfile` / `maxBufferLength` / `supportsFamily:`
   ——注册阶段直接通过，随后去建队列、建深度模板状态。
3. 崩点只是**向后移动**了：`-newDepthStencilStateWithDescriptor:` 返回 nil 之后 38 ms，
   仍然是 backboardd 的 `sig=11`，而且全过程**没有一条 `doesNotRecognize:`**。
   也就是说，崩溃发生在 Metal 自己内部（读设备的功能/限制表），不是我们能回答的消息。

**结论（A1 收尾）**：桩设备能走到的最远处就是这里。Metal 在设备注册之后要求设备具备真实的
功能表（limits/features，来自 `featureProfile` 与 Apple GPU 表）；没有它，Metal 自己的代码
就会解引用空表。继续用桩去"答消息"不会前进——A1 的方法清单已经完整，剩下的属于 C6a 本体
（真正实现设备/队列/命令缓冲，而不是桩）。

数据来源补记：`featureProfile` 的键表在目标机的 Metal（dyld shared cache 内）里，
本地只有 `os-mnt` 的资源文件，缓存本身没有提取，所以暂时无法离线解析这个字典。

### 45.31 A 计划（离线分析目标机 Metal）进展与边界

已完成的部分（全部离线，零上机）：

1. 从本地 IPSW 取出 `044-76040-038.dmg`（5.1 GB）→ Mac `hdiutil attach`，确认它是
   **系统根卷**，其 `System/Cryptexes/OS` 是指向 preboot 的符号链接（该 dmg 里没有 cryptex）。
2. 真正带 **dyld shared cache** 的是另一张盘：Mac 上已有的 `~/h96/044-76034-038.dmg`
   （3.3 GB）。挂到 `/tmp/osvol2` 后得到
   `System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64{,.01..}` 共 54 个分片。
3. `dyld_info` 能对缓存列导出符号：`_MTLAddDevice` 位于
   `System/Library/Frameworks/Metal.framework/Versions/A/Metal`，镜像内偏移 `0x2110`；
   `initLimits` / `initFeatureQueries` / `initGPUFamilySupport` / `initWorkarounds` /
   `featureProfile` 的 selector 字符串也都在缓存里（与 gz 的实测一致）。

边界：`dyld_info -objc` 对共享缓存直接报
`cannot print live objc info from dylibs in dyld shared cache`，系统也没有随附
`dsc_extractor`。要继续反汇编 `_MTLAddDevice` 必须先用 dyld 源码
（`/tmp/opencode/dyld-src`，含 `other-tools/dsc_extractor.cpp`）在 Mac 上自建提取器，
再从缓存里导出 Metal 镜像。

收益评估：即使拿到 `featureProfile` 的键表，桩设备仍要为 A540 **编造**功能数值——
这与 turnip 的死结同类（声明了不支持的能力，后续绘制必然失败）。因此 A 计划到此为止，
不再投入反汇编时间；结论与 §45.30 一致：桩设备的上限就是 Metal 自己的设备表。

### 45.32 目标机 Metal 的反汇编结论（子代理，离线）

在 Mac 上用 Xcode 自带的 `dsc_extractor.bundle`（`dyld_shared_cache_extract_dylibs_progress`）
把 `/tmp/osvol2` 的缓存整份导出，Metal 变成真正的 Mach-O（4 MB，18,711 个符号）后反汇编。
Metal 镜像基址 `0x187A78000`。要点：

1. **发现流程**（`_MTLRegisterDevices` `0x187AA48E8`）：
   `IOMasterPort` → `IOServiceMatching("IOAcceleratorES")` → 逐个
   `getMetalPluginClassForService` → `objc_alloc(cls)` → `[cls initWithAcceleratorPort:svc]`
   → `MTLAddDevice(dev)`。传入的是**原始 io_object_t**。
2. **类名解析**（`getMetalPluginClassForService` `0x187AA49D8`）：先读注册表属性
   `MetalPluginName` / `MetalPluginClassName`（CFString），拼成
   `/System/Library/Extensions/<name>.bundle`，取 `classNamed:`；**取不到才回退**
   `principalClass`，然后 `[cls isSubclassOfClass:<0x1E648E70 的类>]` 作为闸门。
3. **注册顺序**（`_MTLAddDevice` `0x187AA4B7C`）：
   `conformsToProtocol:MTLDevice` → `conformsToProtocol:MTLDeviceSPI`（各有断言）→
   `initLimits` → `initFeatureQueries` → `initWorkarounds` → `_deviceWrapper` →
   `_deviceArray addObject:`。它自己**不写**任何 `_MTLDevice` ivar。
4. **`featureProfile` 是 NSUInteger（profile 位掩码），不是字典**。Metal 没有它的实现，
   由插件提供；`initLimits`/`initFeatureQueries`/`initGPUFamilySupport` 都读它。
   `initWorkarounds` 是裸 `ret`。
5. **`-[_MTLDevice supportsFamily:]`（`0x187A813AC`）直接
   `ldr x9,[x0,#0x110]; ldp x8,x9,[x9]; ...`** —— 走 ivar+0x110 的内联
   `std::vector<MTLGPUFamily>`，**没有空指针检查**。向量由
   `initFeatureQueries`→`initGPUFamilySupport` 填充；我们之前把这两个做成空体，
   正是 gx/gz/hd 崩溃（sig=11）的原因。
6. `newCommandQueueWithDescriptor:` 在基类里就是 `return nil`；参考实现是
   `-[MTLIOAccelDevice newCommandQueueWithDescriptor:]` `0x187B67290`。

### 45.33 B 线：插件自己在 backboardd 里跑通了 ABI 到 GPU 的大部分路径

hb/hc/hd/he 连续四版，把“插件能不能真正驱动 GPU”这件事一条条测出来：

| 步骤 | 结果 |
| --- | --- |
| `Query` | ✅ `abi=0x1 in=32 out=40 maxbo=268435456` |
| `GetDeviceInfo` | ✅ `chip=0x5040000 gmem=0 va=0x2000000+0x8000` |
| `BoAlloc` ×2 | ✅ |
| `BoMap` ×2 | ✅ |
| `BoCpuMap` ×2 | ✅ |
| `IOConnectMapMemory64` | ❌ 传 0 时失败；改成 `kIOMapAnywhere|kIOMapInhibitCache` **✅（ib=4096 target=4096）** |
| `Submit`（CP_MEM_WRITE ×3 的 48 字节 IB） | ✅ 返回 fence |
| `WaitFence` | ❌ **超时**（约 1 s） |
| 回读校验 | 未到达 |

也就是说：**backboardd 的沙箱允许完整的 BO 分配/映射/提交路径**，唯一卡住的是 CP 不推进。
下一版在超时分支里补记 `GetTimestamp`（前后两次）与 `GetStatus`（faults/suspends），
用来判断是“CP 根本没跑（GPU 掉电/环未启动）”还是“fence 语义不符”。

注意：本节的 map 选项是实测结论，之前 `IOConnectMapMemory64(..., 0)` 失败并不是沙箱拒绝。

### 45.34 崩溃点定位方法：信号处理器 + slide + 导出缓存（hi）

插件在 `+load` 里装 SIGABRT/SIGSEGV/SIGILL 处理器，把 `pc / lr / sp / fp 链`
经 ABI Log 写进内核日志，并记录 `_dyld_get_image_vmaddr_slide(0)`（同一进程所有镜像共用）。
离线用 `scripts/macho-resolve.py`（新增，读缓存导出目录的 Mach-O `__TEXT` vmaddr）
把运行时地址换算成“镜像+偏移”：

```
signal=6 pc=0x1d1adef74 → libsystem_kernel.dylib + 0xbf74      (abort)
frame → Metal + 0x14ef54  = _MTLReportFailure.cold.1
frame → Metal + 0xa3e4    = +[MTLLoader sliceIDForDevice:legacyDriverVersion:airntDriverVersion:]
```

### 45.35 断言真相：`[device targetDeviceArchitecture]` 为 nil（hk）

反汇编 `+[MTLLoader sliceIDForDevice:…]`（hk 前那一版崩溃的调用点）：

```arm64
bl 0x187c79060 <_objc_msgSend$targetDeviceArchitecture>
cbz x0, 0x187b783d0        ; nil → _MTLReportFailure(第 666 行)
```

CA 在读预编译 metallib（MTLBinaryArchive）时用这个 SPI 选 slice。多请求场景下
插件实现 `-targetDeviceArchitecture`，返回以 `MTLTargetDeviceArchitecture` 为基类的
运行时子类（`cpuType=CPU_TYPE_ARM64`、`subType`、`driverVersion`、`versionCombined`）。
**断言消失，Metal 继续往下走。**

### 45.36 从此开始的通用转发（hl/hm/hn）

之后 Metal 送的是一串没人文档化的消息，逐个实现不可持续，于是插件改为：

- `-methodSignatureForSelector:`：对任何**尚未实现**、且带参数的 selector，
  按“冒号个数 = 参数个数”合成 `v@:@@@…` 的签名；
- `-forwardInvocation:`：记一行 `forward: <selector>` 后正常返回。

这条在 hl 上第一次生效：`setGPUPriority:` 之后不再 SIGILL。
hm 上继续越过并首次进入渲染路径：

```
dev#18 newDepthStencilStateWithDescriptor:
dev#19 targetDeviceArchitecture → arch cpuType/subType/driverVersion/versionCombined
queue#35 forward: setGPUPriority:
dev#36 newCommandQueue          ← CA 建了第二个队列
queue#37 commandBuffer          ← 第一次拿到命令缓冲
dev#38..#40 newTextureWithDescriptor:   ← drawable 纹理
cmdbuf#51 renderCommandEncoderWithDescriptor: → encoder endEncoding (×3)
cmdbuf#60 blitCommandEncoder
encoder#61 copyFromTexture:…   ← 下一个未实现项
```

hn：把转发器扩展到“任意带参数 selector”，预期越过 blit 拷贝、出现
`presentDrawable:` 与 `commit`。

注意：hm/hl 两次运行结束时屏幕停在 `panic: initproc exited`，但同一段日志窗口里
没有 panic 记录（`grep panic` 为空），launchd 的 `NATIVE_EXIT` 也只有早期正常那次；
初步判断是跑完之后系统收尾，暂不作为插件回归。

### 45.37 子代理第二轮：为什么第三个编码器之后静默

反汇编确认（Metal 镜像内**没有**这些实现，它们是驱动方法）：

- `-renderCommandEncoderWithDescriptor:`、`-commandBuffer`、`-device` 在 Metal 里都不存在实现；
- `_MTLCommandBuffer` 的 `_queue`（ivar 0x20）**只在**
  `-initWithQueue:retainedReferences:synchronousDebugMode:` `0x187A7C318` 里写入；
  `_queue == nil` 时 `commit`/`enqueue` 是**静默 no-op**；
- `-waitUntilCompleted` `0x187AC6180` 在 `_status`(0x108) 上等条件变量，只有真实提交才会置 2；
  CA 有三帧缓冲，耗尽后永久等待 —— 这正好解释“无消息、无退出”。
- 命令缓冲/纹理/编码器**没有类身份闸门**（整个 Metal 里 0 处 `isKindOfClass:`），
  但 `commitCommandBuffer:wake:` 会校验 `[queue device] == [cmdbuf device]`。

### 45.38 ho：自完成命令缓冲让整条渲染管线跑起来了

ho 让命令缓冲**自完成**（`-commit` 记一行、`-status` 返回 2、`-waitUntilCompleted` 立即返回），
并显式实现 `-device`/`-commandQueue`/`-error`。结果（`bb exits 0`，全程无崩溃）：

```
newTextureWithDescriptor: ×N
renderCommandEncoderWithDescriptor: → endEncoding → dealloc   (反复多次)
blitCommandEncoder
  forward: copyFromTexture:sourceSlice:…            ×16
  forward: generateMipmapsForTexture:               ×3
forward: replaceRegion:mipmapLevel:slice:withBytes:… ×3
forward: supportsVertexAmplificationCount:          ×10
```

也就是说 CA **已经在跑真正的合成流程**（离屏纹理、render pass、blit 拷贝、mipmap 生成、
区域上传）。目前仍未看到 `commit`/`presentDrawable`。

### 45.39 通用转发器的边界

`supportsVertexAmplificationCount:` 这类**返回标量**的 selector 也落进了通用转发，
被当成 `v@:@`（void、一个对象参数）——返回值是垃圾。所以：

- 转发器只适合真正 void 的 SPI；
- 所有返回 BOOL/NSUInteger/id 的 selector 必须显式实现（`-device`、`-status`、`-error`、
  `-width`、`-height`、`-pixelFormat`、`supportsVertexAmplificationCount:` …）。

### 45.40 下一步（有据可依，不需要再盲试）

1. 按子代理给出的链路做**真正的队列/命令缓冲**：
   - 队列：`_MTLCommandQueue` 子类 + `-initWithDevice:descriptor:`；
   - 命令缓冲：`-initWithQueue:retainedReferences:synchronousDebugMode:`（这样 `_queue` 才会被写），
     实现 `-device`，并在我们自己的提交点之后调用
     `-commandBufferDidComplete:startTime:completionTime:error:` `0x187A8A380`，让 `_status`→2；
   - 编码器：`-renderCommandEncoderWithDescriptor:` 里创建 `_MTLRenderCommandEncoder` 子类并调用
     `-[_MTLCommandEncoder initWithCommandBuffer:]`，这样 `endEncoding` 才会把当前编码器清掉。
2. 把返回标量的 selector 从转发器里摘出来，逐个显式实现。
3. 之后再谈“把 commit 接到我们驱动的 Submit”——那时才是第一帧真正进入 GPU 的时刻。

### 45.41 ho 归档与后续顺序（2026-11-11，权威前沿）

- 镜像：`/tmp/opencode/boot-H236ho.img`（81,149,952 B），
  sha256 `f18a290466f214fec78dcbfcb703c233a90c618cf9fae1fba90e3044f093656f`；
  插件 cdhash `8ece0bfc8624a34c4c6c74174b2d193a864f4de9`（已在 boot 信任缓存中）。
- 原始日志：Windows 宿主 `D:/Users/ls/Documents/OnePlus5_ios/h103log-H236ho.bin`
  （Linux 侧 `/tmp/opencode/h103log-H236ho.bin`，解析文本 `/tmp/opencode/ho-clean.txt`）。
- 代码：`NativeMetal` `f18ec59`（超级仓库指针同步提交），`UniXNU` 见本提交。
- ho 的实测计数（200 行窗口，`bb exits 0`）：18 个 render pass、5 个 blit、
  23 张纹理、3 个 272 B buffer、`copyFromTexture:` ×16、`generateMipmapsForTexture:` ×3、
  `replaceRegion:` ×3；**8 次 `newRenderPipelineStateWithDescriptor:error:` 全 nil**；
  **零 `commit`/`presentDrawable:`**；**零 `newTextureWithDescriptor:iosurface:plane:`**。

**顺序修正（采纳评审意见）**：先消掉“不可信返回值”这个变量，再谈提交语义。

1. 显式标量访问器（成本最低）：`trace_object_of()` 目前只把 `A540TraceObject` 的方法拷到
   运行时子类上（转发器/dealloc/commit/status/device），**没有** `width`/`height`/
   `pixelFormat`/`length`/`contents`/`gpuAddress`；这些走真实基类实现，读的是从未初始化的
   ivar → 返回 0 或垃圾，且不经过转发器（所以 ho 里一行日志都没有）。
   做法：在 `newTextureWithDescriptor:`/`newBufferWithLength:options:` 里把这些值从
   descriptor 存到桩对象上，并显式实现访问器。
2. 打印 pipeline descriptor 的真实内容（函数是否 nil、`-name`、`colorAttachments[0].pixelFormat`、
   `sampleCount`）——这一步决定“着色器是不是现在就挡路”。
3. 再做真队列/命令缓冲（§45.40）。注意 `-commandBufferDidComplete:startTime:completionTime:error:`
   的两个 double 签名**必须从反汇编确认**（缓存已导出、`macho-resolve.py` 可用），猜错是静默无效。

**耦合关系（必须记）**：ho 里 `newTextureWithDescriptor:iosurface:plane:` 一次都没出现、
`presentDrawable:` 也没有 → CA 连“可呈现表面”都没建。这与显示侧“CA 从不提交 swap
（selector 3/4/5 = 0）”是同一件事的两面：Metal 的 present 与 display 的 swap 卡在同一个判断上。
因此 queue/cmdbuf 做到真提交也不等于有帧上屏——两条线应作为**同一个 gate** 设计。

### 45.42 hp（待上机）：显式标量访问器 + pipeline descriptor 内容

按 §45.41 的顺序做了前两步：

- 桩对象（纹理/缓冲/管线/编码器）的标量回答改为**侧表**（`TraceStorage`）：
  `newTextureWithDescriptor:` 把 `width/height/pixelFormat/textureType/storageMode/
  mipmapLevelCount/sampleCount/usage/arrayLength` 存进去，`newBufferWithLength:options:`
  存 `length`；访问器 `-width/-height/-pixelFormat/-length/-contents/-gpuAddress…` 从侧表读，
  不再落到未初始化的真实基类实现上（这正是 ho 里"返回值不可信且无日志"的来源）。
- `newRenderPipelineStateWithDescriptor:error:` 现在打印
  `vs=<函数名|nil> fs=<函数名|nil> fmt0=<附件0像素格式> samples=<光栅采样数>`，
  直接判定着色器是不是当前的拦路点。

镜像：`/tmp/opencode/boot-H236hp.img`，sha256 见提交记录；插件 cdhash
`dc2c6689…` 已写入信任缓存。**尚未上机。**

### 45.43 `-commandBufferDidComplete:startTime:completionTime:error:` 的真实签名（已反汇编确认）

```
-[_MTLCommandQueue commandBufferDidComplete:startTime:completionTime:error:]  0x187A8A380
187a8a394: mov x21, x5      ; error            (第 4 个对象参数)
187a8a398: mov x22, x4      ; completionTime   ← 整数寄存器
187a8a39c: mov x23, x3      ; startTime        ← 整数寄存器
187a8a3a0: mov x20, x2      ; commandBuffer
```

两个时间参数走 **x 寄存器**，所以是 `uint64_t`，**不是 `double`**（double 会走 d0/d1）。
下一版做真队列/命令缓冲时按此签名写：

```objc
- (void)commandBufferDidComplete:(id)buffer
                       startTime:(unsigned long long)start
                  completionTime:(unsigned long long)completion
                           error:(id)error;
```

（`§45.40` 里写的“两个 double”据此更正。）

### 45.44 hr：描述符与着色器都正常，卡点是“没有可呈现表面”

hr（自完成缓冲 + 侧表标量 + 描述符日志）实测，`bb exits 0`：

```
newTextureWithDescriptor: 776x24 fmt=115 type=2 samples=1 mips=10 usage=0x5
newRenderPipelineStateWithDescriptor:error:
  vs=path_blit_vert_lph            fs=attachment_clear_frag_lph   fmt0=80 samples=1
  vs=downsample_blur_vert_lph      fs=downsample_4_frag_lph       fmt0=80 samples=1
  vs=downsample_blur_vert_lph      fs=narrow_blur_15_frag_lph     fmt0=80 samples=1
  …（共 8 条，函数名与附件格式都正常）
```

结论（把 §45.41 的三个假设排除了两个）：

1. **着色器不是拦路点**：CA 送来的是真实函数名，`fmt0=80`（BGRA8Unorm）、`samples=1` 也正常；
2. **不是我们答错描述符**：纹理尺寸/格式/usage 现在都是真值（776×24、fmt=115、usage=0x5）；
3. **仍然零 `commit`、零 `presentDrawable:`、零 `newTextureWithDescriptor:iosurface:plane:`**。

也就是说 CA 已经把离屏合成跑完（pass/blit/纹理/管线），但没有为我们的设备建立**可呈现的 surface**，
于是永远走不到 commit。这与显示侧记录的“CA 从不提交 swap（selector 3/4/5 = 0）”是同一个判断的两面，
**必须按同一个 gate 去解**：让 CA 认为这块 A540 设备拥有一个可提交的显示表面（IOSurface + 显示服务），
而不是继续在 Metal 侧加桩。

### 45.45 hs：可呈现表面（iosurface 纹理 + presentDrawable），并且 ho 的 render pass 里没有一次 draw

按 §45.44 的顺序做了第一步，同时把 ho 的完整计数补齐（此前只统计了 `forward:` 行）：

- `-newTextureWithDescriptor:iosurface:plane:`：**新实现**。返回 `_MTLTexture` 运行时子类，
  侧表记录 `width/height/pixelFormat/iosurface/plane`，日志带 `IOSurfaceGetID/…` 的真实值
  （`IOSurfaceGet*` 用 `dlsym` 取，bundle 不链接 IOSurface 框架）。
- `-iosurface` / `-iosurfacePlane` / `-bytesPerRow` 从侧表回答（此前落到未初始化的真实基类上）。
- `-presentDrawable:`、`-presentDrawable:atTime:`、`-presentDrawable:afterMinimumDuration:`：
  记录 drawable 的 surface（`[drawable texture]` → `-iosurface`），**每启动一次**向显示侧
  GPU 交接探一次（tunnel `0x7000` MODE、`0x7001` PRESENT），然后把结果写进日志，最后按
  `uint64_t` 签名调队列的 `-commandBufferDidComplete:startTime:completionTime:error:`。
- 工具函数 `abi_call_rc()` 返回原始 `IOReturn`（原来的 `abi_call()` 只给 0/-1），
  交接的拒绝原因现在可读。

**ho 的完整计数（此前漏掉的）**：18 个 `renderCommandEncoderWithDescriptor:` 之后，
**没有任何一次 `setRenderPipelineState:` / `drawPrimitives:`**——转发器只收到
`copyFromTexture:`×16、`supportsVertexAmplificationCount:`×10、`replaceRegion:`×3、
`generateMipmapsForTexture:`×3、`setGPUPriority:`×1。也就是说渲染服务器虽然建了 18 个
render pass，**编码进去的绘制指令是 0**，18 个 pass 全是清屏/空 pass，真正的像素只经过 blit。
这与“场景里没有客户端的可见层”一致：`SpringBoard`（pid 27）从未向我们的设备建过队列，
backboardd 的合成器拿到的是一个空图层树。

镜像：`/tmp/opencode/boot-H236hs.img`，sha256 `16c8accf…`；插件 cdhash `1a319fef…`。

### 45.46 hs 实测：CA 从不 present，可呈现表面这一步“实现完毕但未被调用”

hs（§45.45 的可呈现表面代码）`bb exits 0`，MTL 行 160。结果与 hr 完全一致的那部分：

```
dev#13 newCommandQueue process=backboardd
dev#36 newCommandQueue process=backboardd
18 × renderCommandEncoderWithDescriptor: 后接 endEncoding      （draw 指令 0 条）
 5 × blitCommandEncoder（copyFromTexture: ×16、replaceRegion: ×3、generateMipmaps ×3）
16 × newTextureWithDescriptor:            （无一张 iosurface）
 0 × newTextureWithDescriptor:iosurface:plane:
 0 × presentDrawable:
 0 × display 交接探测（因为 present 从未发生）
```

即：新加的入口**一次都没被调用**，不是实现有误——是 CoreAnimation 从来没有 drawable 可交给我们。
`server`、`present`、`display` 三条新日志一行都没有，说明“怎么把 surface 送到面板”这个问题
在本轮根本还没到。

**同一次启动的显示侧**（`NATIVE_ACCEL_HB` 末值）：

```
accel=49/0/215/2  abi=214/17/0  dpy=3/18/0/1/0  s345=0/0/0  xf=0 fr=0
```

- `dpy=3/18/0/1/0`：3 次 display 客户端打开、18 次调用、0 失败、selector 6 一次（swap id）、
  **registerNotificationPort 0 次**；
- `s345=0/0/0`：3/4/5（SwapBegin/SetLayer/SwapEnd）依然是 **0**，`xf=0 fr=0`；
- 但对照 H162：`op=match comm=backboardd d=AGXAccelerator ok=1` —— 加速器匹配**已经成功**，
  这不再是 `IOAcceleratorES ok=0` 的那道墙。

backboardd 的显示客户端 18 次调用（全部 status=0）为：

```
88 | 57(fixup→0, 1 scalar out) | 15 | 22(fixup) | 8(=1080x1920 via 438,780) | 29(struct=8)
   | 33(fixup) | 79(fixup, struct=1580, in=[77,0]) | 74(fixup, struct=64)
MobileGestaltHelper: 8(=1080x1920) | 28(=163)
```

其中 **57/22/33/79/74 是“未实现→清零输出→返回成功”**（H164 照抄 ios-sweet 0046 的策略）。
结论与 H103 §44.10 一致且更精确：**backboardd 在卖家探测阶段就判定这display不可用
（BKDisplayStartWindowServer 走 headless），于是既没有 drawable、也不建 display link、
更不会 swap**。Metal 侧的 present 与显示侧的 swap 是**同一个判决**的两面，本轮把这句话落到了
可复现的计数上。

镜像：`/tmp/opencode/boot-H236hs.img`，sha256 `16c8accf…`；日志
`D:/Users/ls/Documents/OnePlus5_ios/h103log-H236hs.bin`（Linux `/tmp/opencode/hs-clean.txt`）。

**因此下一轮不再加 Metal 桩**：要把 18 次探测里被清零的 57/22/33/79/74 按真实语义答复，
证据来源是 iPad7,1 kernelcache 里 `IOMobileFramebufferLegacy` 的 user client 分发表
（离线反汇编，正在做）。

### 45.47 离线反汇编：`IOMobileFramebufferLegacy` 的 user client 分发表（iPad7,1 kernelcache）

来源 `/tmp/opencode/h96/kernelcache.arm64`；kext `com.apple.iokit.IOMobileGraphicsFamily`
（`_PrelinkExecutableLoadAddr 0xfffffff0055f5780`，代码在 `__PLK_TEXT_EXEC`
≈`0xfffffff006767000`–`0xfffffff00678c000`）。

- 分发表 **`0xfffffff006f354c0`**（文件 `0x27094c0`），90 项 × 24 B，`index = selector`，**基址 0**；
  `IOMobileFramebufferUserClient::externalMethod` 在 `0xfffffff006778d40`，
  `subs w8,w8,#0x5a` 之后 `cset w8,lo` → selector ≥ 90 返回 `0xe0000001`。
- 条目布局（24 B）：`+0x00` handler、`+0x08` scalarIn、`+0x0c` structIn、`+0x10` scalarOut、
  `+0x14` structOut。
- **特例**：selector `0x44..0x55`（68…85）用跳转表 `0x6778f4c` 在调用前改写复制出来的条目；
  68/85 用 `args->scalarInputCount` / `structureInputSize`，**79 用 `scalarInputCount` 与
  `structureOutputSize`**（`0x6778e90`）。这就是表里 79 写 0/0、而运行期是 2/1580 的原因。
- 空槽：**59–65、70、71**；保留槽跳到 `0xfffffff00677af74`，打印
  `"IOMFB: WARNING: reserved user client function called"` 并返回 `0xe00002c7`。
- 每次调用前还有一道预检：provider 槽 **`+0x5b0`**（`0x6778dbc`，视为“是否 open/可用”），
  非零状态会原样返回给 0–89 的**每一个** selector。

backboardd 这轮实际调到的 9 个 selector：

| sel | handler | sIn | stIn | sOut | stOut | 备注 |
|---|---|---|---|---|---|---|
| 8 | `0xfffffff00677966c` | 0 | 0 | 2 | 0 | 写 `(1080,1920)`，与日志 `out=438,780` 一致 |
| 15 | `0xfffffff00677a014` | 2 | 0 | 1 | 0 | |
| 22 | `0xfffffff00677a2e4` | 1 | 0 | 0 | 0 | 转发 provider `+0x5b8`，只回状态 |
| 29 | `0xfffffff00677a5ac` | 0 | 0 | 0 | 8 | |
| 33 | `0xfffffff00677a770` | 1 | 0 | 0 | 0 | 转发 provider `+0x740`，只回状态 |
| 57 | `0xfffffff00677a200` | 0 | 0 | 1 | 0 | 转发 `+0x670`，**局部 u32 预置 6** |
| 74 | `0xfffffff00677a718` | 1 | 0 | 2 | 64 | 与日志 `struct=64` 一致 |
| 79 | `0xfffffff0067799b4` | 2* | 0 | 0 | 1580* | 转发 provider `+0x700`，输出整块缓冲 |
| 88 | `0xfffffff00677adb0` | 1 | 0 | 0 | 0 | |

（`*` 运行期由 `args` 改写。）另外 3/4/5 的条目确实存在（3 用 2 个 scalar in、4 用 0 个、
5 用 1288 字节 structIn），所以“没有 3/4/5”不是分发表缺项，而是客户端根本没调。

**这四个 handler 都不做 provider 类检查**：79/57/33/22 只是取 `this+0xd8` 的 provider 对象、
调它 vtable 上的一格。`"provider was not AppleARMIODevice"`（`0xfffffff0055fc213`）只在
`IOMobileFramebufferLegacy::start` 里，**只打印、不失败**；`"IOSurfaceRoot not available or of
the wrong class"` 同理。

**79 的 1580 字节结构无法离线取到**：常数 `0x62c` 在整份镜像里不存在（它是 backboardd 自己的
缓冲区大小，由 `args->structureOutputSize` 传进来），填充逻辑在 provider vtable `+0x700`，而
kext 的 `__PRELINK_DATA` 在缓存里约 83% 为零（bind fixup 在开机时做），vtable 内容读不到。
要拿到真实布局只能**运行期 hexdump** 一次；按 §45.46，清零是本族当前策略，而 79 不是“是否
headless”的唯一候选，所以先不动它。

### 45.48 离线反汇编：backboardd 的 headless 判决在 QuartzCore，不在 IOKit

对象 `/tmp/opencode/os-mnt/usr/libexec/backboardd`（1,220,560 B，arm64，stripped：
`LC_SYMTAB` 只剩 750 个 undefined + `__mh_execute_header`，函数身份靠代码恢复）。

**判决点只有一个**：`BKDisplayStartWindowServer`（`0x10003472c` 处的全局 block）在

```
0x100034888  +[CADisplay mainDisplay]              -> x21
0x1000348a4  -[CAWindowServer displayWithDisplayId:] -> x22
0x100034904  cbz x21, 0x100034cf4   ; CADisplay.mainDisplay == nil  -> headless
0x100034908  cbz x22, 0x100034cf4   ; 该 id 的 server display == nil -> headless
```

之后就 `__os_log_error_impl` 打出 `"StartWindowServer: headless (display:%{BOOL}u/server:%{BOOL}u)"`
（格式串 `0x1000d5c01`）。**没有** `IOServiceOpen`、没有注册表属性、没有 boot-arg、
没有 `IONotificationPort*` 参与这个判断。

`BKDisplayIsHeadless`（`0x100007e38`）只是读全局 `BKDisplayInfo`（`0x10010da10`，
`os_unfair_lock` `0x10010da18`）的 `-windowServerDisplay` 是否为 nil；若
`BKDisplayStartWindowServer` 还没跑过会直接 `NSAssert`（`"please invoke BKDisplayStartWindowServer
before BKDisplayIsHeadless"`，`BKDisplay.m:670`），不是返回 headless。

**backboardd 根本不匹配任何显示类服务**（全二进制只有 4 处 `IOServiceMatching`）：

| 站点 | 类名 | 用途 |
|---|---|---|
| `0x1000581f8` | `AppleTetheredDevice` | tether demo card |
| `0x100058930` | `AppleH1CLCD` | IOMFB *debug flags* |
| `0x100058950` | `AppleM2CLCD` | 同上 |
| `0x100058e10` | `IOEthernetInterface` | tether |

唯一的 `_IOMobileFramebufferOpen` 在 `0x100058980`，只有 `AppleH1CLCD`/`AppleM2CLCD` 匹配成功才
走到，用来 `IOMobileFramebufferSetDebugFlags(..., 0x20)`——我们的服务不叫这两个名字，**这条路
永远不执行**。整个二进制**没有** `IONotificationPortCreate` / `IOServiceAddMatchingNotification`
导入，所以 §45.46 里“registerNotificationPort = 0”本来就是正常的，不是缺陷。

真正的发现逻辑是纯 ObjC（`0x10005a45c`）：`+[CAWindowServer serverIfRunning]` →
`-[CAWindowServer displays]` → 空表就 `"We seeem to be headless"`（`0x1000d88be`）并返回空数组。
backboardd **只消费** QuartzCore 已经发布的 `+[CADisplay displays]`，自己不建 display。

**结论（诊断重心转移）**：那 3 次打开 / 18 次调用是 **backboardd 进程内的 QuartzCore** 通过
`IOMobileFramebuffer.framework` 发的；QuartzCore 拿到全部 `status=0`，却**一个 display 都没发布**。
因此这条 gate 不在 IOKit 服务可见性、不在类名、不在 sandbox、不在 boot-arg，而在
**QuartzCore 的 `CADisplay` 实例化条件**。下一步去反汇编 dyld 缓存里的 QuartzCore /
IOMobileFramebuffer.framework（Mac `~/dsc-work/ext` 已有导出），把 9 个 selector 的 API 名、
1580 字节结构的字段、以及放弃分支的判据都读出来。

### 45.49 离线反汇编：QuartzCore 里 9 个 selector 的真实身份，以及“谁也改不了 headless”

来源 Mac `~/dsc-work/ext`：`IOMobileFramebuffer`（私有框架，`0x1b63cf000`，94 208 B）、
`QuartzCore`（`0x189429000`，5 160 960 B）。

**selector → API**（`_kern_*` 是真正发 trap 的函数，公开 API 是 `IOMobileFramebufferOpen`
填进 vtable 的那一格）：

| sel | 公开 API | trap | in | out |
|---|---|---|---|---|
| 8 | `IOMobileFramebufferGetDisplaySize` | Scalar | 0 | 2 u64 → CGSize |
| 15 | `SetDebugFlags` | Scalar | 2 | 1 |
| 22 | `SetDisplayDevice` | Scalar | 1（idx ≤ 4，否则 `e00002c2`） | 0 |
| 29 | `GetDisplayArea` | **Struct** | 0 | 8 B = 2×float（mm） |
| 33 | `EnableDisableVideoPowerSavings` | Scalar | 1 | 0 |
| 57 | `GetColorRemapMode` | Scalar | 0 | 1 u64（库在出错时**代入 6**） |
| 74 | `SupportedFrameInfo` | IOConnectCallMethod | 1（mask=0） | 2 u64 + 64 B tag blob |
| 79 | **`GetBlock`** | IOConnectCallMethod | `{block_id, offset}` | 分块，`min(len-offset, 0x1000)` |
| 88 | （无公开 API，`IOMobileFramebufferOpenByName` 内联） | Scalar | 显示 id | 0，**返回值被丢弃** |

**79 = `GetBlock` 确认**，block id **0x4d = 77 = gamut-remap 配置块**，长度 0x62c = 1580，
调用点 `CA::WindowServer::IOMFBDisplay::IOMFBDisplay` `0x1896e7588`。ctor 里**根本不读这块内容**，
只把 IOReturn 存进 `this+0x888` 当“支持 gamut remap”的能力位；失败也**不致命**。
同处还有 block 74（2056 B）和 72（3164 B），只在 `this+0x258 & 0x1c00 == 0` 时才取——内屏带这两
位，所以我们只看到 77。

**headless 的判决链**：`+[CADisplay mainDisplay]` → `ensure_displays` → `query_displays`
`0x189549038`。**`query_displays` 一次都不碰 IOMobileFramebuffer**，它向渲染服务器要列表：

```
CARenderServerGetServerPort(0)  ← bootstrap 查 "com.apple.CARenderServer"
  w0 == 0  → 直接返回空表（0x189549070），无日志
__CASGetDisplays(...) → ret != 0 → "Unable to query displays from server (%d)"
每个字典：kCADisplayName 与 kCADisplayDeviceName 必须都非 NULL，否则跳过
mainDisplay = 第一个名叫 "LCD" 的
```

服务器侧 `CA::WindowServer::Server::get_displays` `0x1894bdf64` 每有一个 Server 就发一个字典
（`kCADisplayName`=`[[server+0x60]+0x8]`、id=`[[server+0x60]+0x10]`、
`kCADisplayDeviceName`=`[server+0x68]`）。

**因此结论是硬的**：9 个 selector 的返回值**没有任何一条**能让 `mainDisplay` 变 nil；能决定的是
①`com.apple.CARenderServer` 端口在查询时是否已注册，②服务器发布的字典是否两个名字都非空。
而 `+[CADisplay mainDisplay]` 为 nil 就等价于 `BKDisplayIsHeadless` 为真（§45.48）。

**provider 应答清单**（由这套代码反推，供以后核对）：8 必须 w,h ≥ 1（我们用 1080×1920）且返回
u64；29 必须写 8 B 两个 float；22 只接受 idx ≤ 4；88 的返回值被丢弃、不能让 open 失败；
74 返回 count 0 等价于“没有 frame-info tag”（不影响发布，只让 `frame_info_enabled` 为假）；
79 失败不致命。

### 45.50 ht：直接从插件里问 QuartzCore

因为上面两条都**高于 IOMFB ABI**，插件加了一个探针（`ca#N probe` 日志，设备 init 后
2/18/34/50 s 各一次）：

- `task_get_special_port(TASK_BOOTSTRAP_PORT)` + `bootstrap_look_up("com.apple.CARenderServer")`
  → 端口是否存在、`kr` 是多少；
- `+[CADisplay mainDisplay]`、`+[CADisplay displays].count`、`+[CAWindowServer serverIfRunning]`
  及其 `-displays.count`，全部经 `objc_msgSend` 调用并包在 `@try` 里。

一行就能区分：`port=0x0` 是“端口还没注册”（鸡生蛋），`port≠0 list=0` 是“服务器没发布 display”，
`list≥1 main=0` 是“发布的名字不叫 LCD / 缺 device name”。

镜像：`/tmp/opencode/boot-H236ht.img`，sha256 `2497e6de…`；插件 cdhash `bae5b179…`。

### 45.51 ht 实测：CA 里有 display，而且有 6 个 —— 问题变成“SpringBoard 起得太早”

`ht` 的 `ca#200..203 probe`（插件在 backboardd 内调用 QuartzCore）：

```
ca#200 probe timer class=1 main=1 list=6 server=6 port=0x8e07 kr=0x0
ca#201 probe timer class=1 main=1 list=6 server=6 port=0x8e07 kr=0x0
ca#202 probe timer class=1 main=1 list=6 server=6 port=0x8e07 kr=0x0
ca#203 probe timer class=1 main=1 list=6 server=6 port=0x8e07 kr=0x0
```

- `kr=0`、`port=0x8e07`：`com.apple.CARenderServer` **已注册**；
- `main=1`：`+[CADisplay mainDisplay]` **非 nil**；
- `list=6` / `server=6`：渲染服务器发布了 **6 个 display**。

也就是说 §45.48/§45.49 推断的“headless”**在 223 s 并不成立**：`BKDisplayIsHeadless` 此刻必然为假。
再结合本轮的进程次序：

```
126.47 s  SpringBoard pid=26 exec
130.48 s  xpcproxy com.apple.backboardd  pid=56
142.76 s  backboardd exec
150.10 s  backboardd 打开 NativeLegacyDisplay（第一次 IOMFB 客户端）
152.76 s  插件加载（Metal 设备）
223.4  s  probe：main=1 list=6
```

**SpringBoard 比 backboardd 早 16 s**。而 `query_displays` 在
`CARenderServerGetServerPort(0) == 0` 时**直接返回空表且不打印任何东西**（§45.49），所以
SpringBoard 在 126–142 s 之间问“主 display 在哪”时必然拿到 nil；如果这个空结果被
`ensure_displays` 缓存，它之后再也不会重试，于是：

```
SpringBoard 没有 display → 不建窗口 → 不提交图层
→ backboardd 合成空图层树 → 18 个 pass 全是清屏、0 条 draw
→ 没有可呈现内容 → 不 swap（s345=0/0/0）→ 没有帧
```

这一条把 §45.46–§45.50 的所有观察串成了一条因果链，而且**不再需要改 IOMFB 的答复**。

### 45.52 hu：验证“起得太早”这个假设

插件（`hu`）加了两件事，都只在 backboardd 内做：

1. `ca#N display`：把 6 个 display 的 `-name` / `-deviceName` 打出来（`mainDisplay` 是名叫
   `"LCD"` 的那个，所以名字能确认面板是否真在列表里，而不是只有 External/TV 条目）；
2. 设备 init 后 **+60 s**（约 212 s）用 `proc_listpids` 找到 `SpringBoard`，发 `SIGTERM`，
   然后在 +12/+28/+44/+60 s 再各探一次 `ca#N probe`。

判读：若重启后的 SpringBoard 拿到 display 并开始提交图层，我们会立刻看到
`newTextureWithDescriptor:iosurface:plane:`、`presentDrawable:`、`s345` 非零——那就同时证实了
因果链并给出了可用的规避方案（让 SpringBoard 在 backboardd 之后启动）。

镜像：`/tmp/opencode/boot-H236hu.img`，sha256 `0739918f…`；插件 cdhash `00ffc2f8…`。

### 45.53 hu 实测：display 列表确认是 “LCD/primary”，但 SpringBoard 的重启被沙箱挡住

`ca#N` 行（本轮）：

```
ca#200 probe timer class=1 main=1 list=6 server=6 port=0x621b kr=0x0
ca#201 display list[0] name=LCD       device=primary
ca#202 display list[1] name=Wireless  device=wireless0
ca#203..206 display list[2..5] name=Wireless-1..4 device=wireless1..4
```

- **`list[0] name=LCD device=primary`**：`mainDisplay` 就是这块面板，§45.51 的推断成立
  （其余 5 个是 Wireless 虚拟屏）；
- `list=6` 在 187 s / 219 s / 221 s / 234 s / 251 s 全部一致，是稳定状态，不是瞬时值。

重启实验失败在沙箱：

```
Sandbox: backboardd(56) deny(1) process-info-listpids
ca#228 restart restart springboard=none
```

`proc_listpids` 被拒绝，`springboard=none` 不是“没找到”，而是“根本不让枚举”。

### 45.54 hv：逐 pid 查询绕开 process-info-listpids，并在日志里带边界

- `find_process()` 改成对 pid 1..400 逐个调 `proc_name()`（不同的沙箱检查），
  **拒绝次数也写进日志**（`springboard=none refused=N`），所以下次能区分“被拒”和“没有该进程”；
- `ca#N display` 增加 `bounds`（经 KVC 取 `NSValue`，避开结构体返回 ABI），
  用来确认 LCD 这个 display 的尺寸不是 0×0——如果是 0，CA 不会往里画。

> 记录一个坑：`CGRectZero` 是外部符号，bundle 没有链接 CoreGraphics 会链接失败；
> 用 `memset` 清零本地 `CGRect` 即可，只用到类型不需要框架。

镜像：`/tmp/opencode/boot-H236hv.img`，sha256 `3fea6784…`；插件 cdhash `0ed22582…`。

### 45.55 离线反汇编：空 display 列表是**永久缓存**的（根因确认）

`QuartzCore` `ensure_displays`（`0x18948d294`）：

```
18948d2c8  ldrb w8, [x19, #0x4c0]     ; static bool displays_queried
18948d2cc  tbnz w8, #0x0, 0x18948d2dc ; 已查过 → 永久跳过
18948d2d0  bl   0x189549038           ; query_displays
18948d2d4  mov  w8, #1
18948d2d8  strb w8, [x19, #0x4c0]     ; 置位，进程内不会再查
```

`query_displays` 在 `CARenderServerGetServerPort(0) == 0` 时直接返回空表且**不打印任何日志**。
所以一个进程只要在渲染服务器存在之前问过一次 `+[CADisplay mainDisplay]`，它这一辈子都拿不到 display。

配合 §45.51 的进程次序（SpringBoard 115 s，backboardd 131 s，渲染服务器 ~150 s），
**这解释了我们从 C6a 到现在的全部现象**：

```
SpringBoard 先问 → 空表被缓存 → 没有 display → 不建窗口 → 不提交图层
→ backboardd 合成空图层树（18 pass、0 draw）→ 没有内容 → 不 swap（s345=0/0/0）→ 无帧
```

这不是 IOMFB 应答问题（§45.49 已排除），也不是 Metal 设备问题（§45.46 已排除）。

### 45.56 hv/hw 与构建环境：内核路线暂时走不通，改走框架 API

hv（逐 pid `proc_name`）的 `restart` 行落在日志窗口之外（内核环只留 61 个快照），
无法判定是否被拒；但可以确定 `proc_listpids` 是**被沙箱拒绝**的
（`Sandbox: backboardd(56) deny(1) process-info-listpids`）。

于是尝试了内核侧一次性 SIGTERM（`proc_iterate` + `psignal`，按 `p_comm` 匹配），
**但 Mac 的构建环境当前不完整，内核重建做不出来**，记录如下（下次先修环境）：

| 症状 | 处置 |
|---|---|
| `ModuleNotFoundError: tomllib` | 用 `~/.local/bin/python3.12` 跑 `./unixnu` |
| `cmake not found` / `ninja not found` | MacPorts 在 `/opt/local/bin`，`PATH` 前置即可（Homebrew 已被清空） |
| `PermissionError: unlink .../tree/refer/libdispatch` | `refer/` 下有几个是**真实目录**（旧 treecopy 残留），`_link()` 只会 unlink 链接 → 组装中断 |
| `patch does not apply: iokit/KernelConfigTables.cpp` | 工作树已是打过补丁的状态 → `XNU_SKIP_PATCH_LOOP=1` |
| `NativeRamBlock requires ... prelink closure` | 需要 `XNU_OWNER_DATA_MOUNT=1 XNU_OWNER_DATA_VOLATILE=1 XNU_OWNER_DATA_VOLUME_UUID=1A4CE9DF-…` |
| 归档步骤 `nm: bsd_init.o No such file` | 内核对象被删过，先跑一遍脚本生成对象，再跑完整流程 |
| 链接 `Undefined _proc_iterate` | C++ 里需要 C 链接（`extern "C"` 包住 `proc_internal.h`） |
| 链接 `Undefined _native_a540_*` / `_native_legacy_client_calls` | 归档没有进入链接集，属环境问题，未解决 |

因为这条路线当天不可用，**hw 改为纯插件方案**：backboardd 有系统框架的权限，
用 `dlopen` 载入 `FrontBoardServices`，调
`-[FBSSystemService terminateApplication:forReason:andReport:withDescription:]`
（`com.apple.springboard`，reason 1）重启 SpringBoard；每次尝试都写一行 `ca#N restart`，
并先打 `scan=<pid> refused=<n>` 说明 `proc_name` 扫描的结果。
若框架调用也不成，下一轮再回到内核路线并先修上表。

镜像：`/tmp/opencode/boot-H236hw.img`，sha256 `a6ac043d…`；插件 cdhash `e3fdadca…`。

### 45.57 hw 实测：SpringBoard 重启成功，但它依然没连上渲染服务器

```
[126.61] SpringBoard[27] exec
[141.16] backboardd[56] exec
[218.74] NATIVE_EXIT: pid=27 comm=SpringBoard status=0xf ns=2 code=0xf   ← SIGTERM，我们的重启生效
[219.23] SpringBoard[117] exec                                          ← launchd 立即重启
```

重启确实发生了（不管走的是 `kill` 还是 FrontBoardServices），而重启时刻渲染服务器**已经在发布**
`LCD/primary 1080x1920`（`ca#221 probe … list=6`，218.36 s）。但之后：

- **219 s 之后再也没有任何 `NATIVE_MTL` 行**——backboardd 的 CoreAnimation 完全没有新动作，
  说明新 SpringBoard **没有连上渲染服务器**，也没有提交图层；
- `s345=0/0/0`、`fr=0` 不变，仍然零 swap；
- 新 SpringBoard（pid 117）只做了 `IOServiceMatching("AppleKeyStore")`（`ok=0`，注册表里没有这个
  服务）×若干，然后安静下来。

也就是说：**“CADisplay 被缓存成空表”这个根因成立，但重启 SpringBoard 并不能解决**——它在
更早的一步就停住了，根本没走到 display 查询。

### 45.58 参考资料（`/tmp/opencode/sagit-ios-port/docs/display/README.md`，同一路线、iOS 18）

这份记录里有几条与我们现在状态**逐字对应**的事实：

1. **同一组 display**：`+[CADisplay displays]` 返回 **6 个对象，主显示 `LCD primary`**，
   另有 5 个未连接的 wireless —— 与我们 `ca#N display` 的输出完全一致。所以“6 个 display”是这条
   Legacy 路线的正常形态，不是异常。
2. **查询取决于会话/环境**：root Bash 里 `CARenderServer lookup` 返回 `0x44e`
   （`BOOTSTRAP_UNKNOWN_SERVICE`），CADisplay 为 nil；确认 user sessions 启用、前台 UID 501、
   **按用户 lookup 成功**，并且在首次查询前设置 `CA_SYSTEM_SESSION_CLIENT=1` 之后，
   原生 QuartzCore 才返回那 6 个 display。
3. **它们的 SpringBoard 死在 FBSDisplayMode 校验**：62 份崩溃都停在
   `preferredScale == 0` 时的 `BSFloatIsZero` 拒绝（保留尺寸 1242×2208，硬件是 1080×1920）。
   我们的 SpringBoard 没有崩溃循环（只有我们发的那一次 SIGTERM），所以这一点在我们这不成立。
4. 另有整条容器/persona 链（`/private/var/keybags/persona.kb` 缺失导致 containermanagerd 的
   Sandbox 容器 RPC 不返回、backboardd 卡在 Mach receive）。我们会话里 backboardd 是正常跑起来的，
   但 SpringBoard 可能卡在同类同步 XPC 上——这正是“先 AppleKeyStore、然后安静”的形态。

**由此得到的下一步**：必须拿到 **SpringBoard 自己那个会话里的 CADisplay/bootstrap 视图**，
而不是继续从 backboardd 里猜。最省事、不需要重建内核的办法是往 Data seed 里放一个
LaunchAgent（用户会话）和一个小探针程序，由它打印
`bootstrap_look_up("com.apple.CARenderServer")` 的结果与 `+[CADisplay displays]` 计数；
参照 §45.58 第 2 条，还可以在首次查询前设 `CA_SYSTEM_SESSION_CLIENT=1` 做对照。

### 45.59 hx：把探针放进系统会话（LaunchDaemon），量 SpringBoard 能看到的视图

按 §45.58 的结论做的探针，不重建内核：

- 源码 `drivers/NativeMetal/CadProbe.mm`，编译成 arm64 CLI（ad-hoc 签名，
  cdhash `8fded1a6…` 已写进 owner 信任缓存）；
- 由 `scripts/add-gpu-plugin-data.py` 一起送入 Data seed：`ngpu/bin/cadprobe` +
  `ngpu/daemons/com.unixnu.cadprobe.plist`（`RunAtLoad`）。`ngpu/daemons` 由
  `zzy-native-gpu-addon-mount` 联合挂载到 `/System/Library/LaunchDaemons`，所以它是一个
  **系统会话的 LaunchDaemon**；
- 输出走 A540 ABI 的 Log 方法（`NATIVE_MTL: cad …`），因为 Data 卷是 APFS，恢复环境读不到文件。

每次启动打印五行：

```
cad  uid/euid accel=…            身份与 ABI 通道是否打开
cad  system port=… kr=…          bootstrap_look_up("com.apple.CARenderServer")
cad  peruser uid=501/0 … kr=…    bootstrap_look_up_per_user(...)
cad  displays class=… list=N main=0/1
cad  first name=…
```

`+[CADisplay displays]` 在进程内**只算一次**（§45.55），所以每次采样都是新进程：
每轮 40 s、共 3 轮；第一串结束后以 `CA_SYSTEM_SESSION_CLIENT=1` 重跑同样 3 轮（前缀 `sys/`），
对应 §45.58 第 2 条里参考实现需要的那根开关。

判读表：

| 输出 | 含义 |
|---|---|
| `system kr=0x44e`（BOOTSTRAP_UNKNOWN_SERVICE） | 系统会话看不到渲染服务器 → SpringBoard 的失败是会话/命名空间问题 |
| `system kr=0x0` 但 `displays list=0` | 服务在，但该会话里 CA 拿不到 display |
| `system kr=0x0` 且 `list=6` | 系统会话完全正常 → SpringBoard 卡在更早的初始化（不是 display） |
| `sys/` 两串结果不同 | 证实 `CA_SYSTEM_SESSION_CLIENT` 就是分水岭 |

镜像：`/tmp/opencode/boot-H236hx.img`，sha256 `99b1531c…`。

### 45.60 hx/hy 复盘：信任缓存只放了 cadprobe，插件整个没加载（我的失误）

hx/hy 两轮的日志里 `NATIVE_MTL` **零行**，心跳是 `accel=1/1/1/2 abi=0/0/0`——说明
backboardd 根本没打开加速器、Metal 没加载插件。原因很直接：

```sh
# 错的：用 trust-base + cadprobe 生成，把上一版插件的 CDHash 覆盖掉了
add-owner-trust-hash.py trust-base.bin <cadprobe-cdhash> trust-a541t.bin
```

插件是 ad-hoc 签名，**它的 CDHash 必须在信任缓存里**（§45.14）。正确做法是串两步：

```sh
add-owner-trust-hash.py trust-base.bin  <plugin-cdhash>   tmp.bin
add-owner-trust-hash.py tmp.bin         <cadprobe-cdhash> out.bin
```

hz 已按此重建（`trust-a541v.bin`，owner 模块 5 项）。

**顺带排除了整条“会话/命名空间”假设**：本轮全日志里 **launchd 只有一个（pid=1）**，
SpringBoard（ppid=1）是它的直接子进程——也就是说 SpringBoard 与 backboardd **同一个
bootstrap 命名空间**。§45.58 里参考实现的“系统会话看不到、用户会话才看得到”在这里不成立，
backboardd 里量到的 `list=6 / LCD primary` **就是** SpringBoard 会看到的答案。

也因此：把 cadprobe 交给 launchd 的两条路都不通——
- **LaunchAgent**：本机没有 per-user launchd，`mobile/Library/LaunchAgents` 不会被扫描
  （hy 里没有任何 `comm=cadprobe` 的 exec）；
- **LaunchDaemon**：`/System/Library/LaunchDaemons` 要求 **root 属主**，而 staging 以构建用户
  （uid 501）写文件，Mac 上又没有 sudo 可以 chown；`NATIVE_GPU_ADDON: … daemons=4/2` 里的
  `status=2` 就是这个。

结论：**要再拿到一个新进程的测量，必须先有 root 写文件的手段**（内核侧写文件是唯一现成通道，
但内核构建当天不可用，见 §45.56）。

### 45.61 hz：直接问渲染服务器“有没有客户端”

既然会话假设被排除，剩下的问题只在 SpringBoard 内部。hz 的插件在 `ca#N clients` 里对
display[0] 用 `respondsToSelector:` 依次试 `contexts` / `contextIds` / `clients` 并打印其
`count`：

- 全是 0（或都不存在）→ 确认**从来没有客户端**连过窗口服务器；
- 非 0 → 客户端其实连上了，问题在合成器/present 一侧，方向要改。

镜像：`/tmp/opencode/boot-H236hz.img`，sha256 `a016586b…`；插件 cdhash `0c82a732…`。

### 45.62 踩坑记录独立成文

§45.60 之后又确认了一个更隐蔽的坑：**真正被加载的插件来自 payload 里的
`Payloads/kernel.macho.gpuaddon`，不是 Data seed 的 `ngpu/addons`**。hx/hy/hz 三轮只换了 seed，
payload 里仍是 hw 那一版的插件，其 CDHash 已不在新信任缓存里 → AMFI 拒绝 → 零日志。
再加上 hz 之后我发现 `mcopy` 源文件不在本机、等于把同一张镜像又打了一遍（sha256 相同），
这三轮的全部代价都来自打包流程，而不是实验设计。

这些流程性坑单独记在
`plans/oneplus5-cheeseburger/diagnostics/gpu-display-pitfalls-2026-11-11.md`（P1–P10 + 上机前自检清单），
本文件只保留实验结论。要点：

1. 信任缓存只能**串加**（P1）；
2. 插件在 payload 的 `.gpuaddon` 里（P2），每次三件套一起换；
3. 打包后必须比对 `sha256`，相同就说明 payload 没换（P3）；
4. 用 `NATIVE_MTL` + `NATIVE_ACCEL_HB` 的 `accel=` 计数区分“没加载”和“加载了没日志”（P4）；
5. LaunchDaemon 需要 root 属主、本机没有 per-user launchd、没有 sudo（P5/P6/P7）；
6. 日志窗口只有约 61 个快照，关键行要重复写（P9）。

### 45.63 ib：重启链路确认可用；ic 改为读 SpringBoard 自己的日志

ib（payload 里已换成新插件）恢复了全部日志（`NATIVE_MTL` 258 行，`accel=50/0/273/0 abi=272/17/0`），
并且这次 `ca#N restart` 落在日志窗口内，把 §45.56 的疑问一次答清：

```
ca#228 restart restart scan=27 refused=0     ← 逐 pid 的 proc_name 可用（拒绝数 0）
ca#229 restart restart kill pid=27 status=0  ← kill 成功
[218.35] NATIVE_EXIT: pid=27 comm=SpringBoard status=0xf   ← SIGTERM
[218.42] SpringBoard[119] exec                             ← launchd 立即重启
```

也就是说：**扫描、发信号、launchd 重启都没有问题**；新 SpringBoard（119）启动时渲染服务器
已经在发布 `LCD/primary 1080x1920`。但 230 s 之后依旧零 `NATIVE_MTL`、`s345=0/0/0`。

所以问题被完全逼进 **SpringBoard 自己的初始化**里，而我们看不到它的 stderr。
ic 因此加了两件事，都是插件侧、不改内核：

1. **`OSLogStore` 读 SpringBoard 的统一日志**（iOS 15+ 公开 API）：重启后 +30 s，
   `+[OSLogStore localStoreAndReturnError:]` → `entriesEnumeratorWithOptions:position:predicate:error:`，
   谓词 `process == "SpringBoard"`，最近 420 s，最多打印 48 条 `composedMessage`
   （`sblog#N sb …`），结尾再打 `total=/shown=` 和 `no-class/no-store/no-enumerator/exception`，
   失败也要留痕；
2. **客户端计数改问窗口服务器一侧**：`+[CADisplay displays]` 返回的是客户端对象（没有 `contexts`），
   §45.61 的探测因此什么都没打印。ic 改为取 `-[CAWindowServer serverIfRunning] -displays` 的第一个
   `CAWindowServerDisplay`，再试 `contexts`/`contextIds`/`clients`/`currentState`。

镜像：`/tmp/opencode/boot-H236ic.img`，sha256 `d0745f52…`（与上一张 `3ae6cf4a…` 确认不同）；
插件 cdhash `cd36bb18…`，cadprobe `8fded1a6…`（两者都在信任缓存里）。

### 45.64 ic 结果：两条探针都没输出，改用显示模式做判据

ic 的日志里：

```
ca#201 clients server none      ← CAWindowServerDisplay 不响应 contexts/contextIds/clients/currentState
sblog#250 oslog exception       ← OSLogStore 抛异常，没拿到 SpringBoard 的日志
```

即：窗口服务器一侧没有可直接读的客户端计数；统一日志的读取被拒（原因在异常里，下一版会打出来）。

于是按 §45.58 第 3 条换一个更有判据的输入：**显示模式本身**。参考端口（sagit）的 SpringBoard
正是死在 `FBSDisplayMode` 校验上——`preferredScale == 0`、保留尺寸 1242×2208 而硬件是 1080×1920。
如果我们的 `CADisplay` 也报 `refreshRate = 0` 或 `pointScale = 0`，那 SpringBoard 不建 UI 就有了
直接解释，而且这是**驱动侧可以修**的东西。

id 的 `ca#N mode` 用 KVC 读（不依赖私有类型）：

```
ca#N mode <w>x<h> px=<pw>x<ph> hz=<refreshRate> prefHz=<preferredMode.refreshRate> scale=<pointScale>
```

同时把 OSLogStore 的失败原因打全（`exception <name>: <reason>`、`no-enumerator <localizedDescription>`）。

镜像：`/tmp/opencode/boot-H236id.img`，sha256 `20e22b28…`；插件 cdhash `21128ef4…`，
cadprobe `8fded1a6…`，两者都在信任缓存里（已按 P1 串加、P2/P3 三件套一起换）。

### 45.65 id 结果：两个探针都“抛异常”，原因已定位（离线确认）

```
ca#201 mode exception
ca#202 clients server none
sblog#256 oslog exception NSInvalidArgumentException:
          +[OSLogStore localStoreAndReturnError:]: unrecognized selector sent to class 0x2043f3180
```

两条都不是权限问题，是**接口选错**：

1. **`OSLogStore` 的工厂**：拿本机 dyld 缓存里的
   `System/Library/Frameworks/OSLog.framework/OSLog` 查字符串，它只有
   `storeWithScope:error:` / `storeWithURL:error:` / `storeWithArchiveURL:`，
   **没有** `localStoreAndReturnError:`（那是 macOS 的写法），并且带有
   `"Invalid direct use of -[OSLogStore init] (use factory instead)"`。
   `+storeWithScope:` 的 scope 0 是系统存储，正好能读到别的进程。
2. **`CADisplay` 的 KVC**：iOS SDK 里根本没有公开的 `CADisplay.h`（只有
   `CADisplayLink.h`/`CAMetalDisplayLink.h`），KVC 走 `valueForKey:` 在这套私有类上会抛
   `NSException`。改成 `respondsToSelector:` + `objc_msgSend` 直接调
   `-currentMode` 以及 `CADisplayMode` 的 `width/height/pixelWidth/pixelHeight/refreshRate`，
   并把异常名与 reason 打进行里。

ie 已按这两条重写：`sblog` 先用 `+storeWithScope:error:`（scope 0），失败再退回
`localStoreAndReturnError:`；`ca#N mode` 改为直接 getter。镜像
`/tmp/opencode/boot-H236ie.img`，sha256 `23f4f640…`；插件 cdhash `0fb67058…`。

### 45.66 ie 结果：显示模式拿到了，`pixelWidth/pixelHeight = 0`

```
ca#201 mode 1080x1920 px=0x0 hz=60.000
```

- `width/height` = 1080×1920 —— 正确（= `IOMobileFramebufferGetDisplaySize` 的答复）；
- `refreshRate` = 60.0 —— 正确（Legacy timing 的 Q32.32 60 Hz = 71582788 路径是通的）；
- **`pixelWidth/pixelHeight` = 0×0** —— QuartzCore 手里没有像素尺寸。

这与 §45.58 里参考端口的失败形态同源：他们家在 `FBSDisplayMode` 校验里因为
`preferredScale == 0` 被 `BSFloatIsZero` 拒绝（保留尺寸 1242×2208，`pointScale`/`preferredScale`
都是 0），修法是让 **MobileGestalt/BKS 的 scale 变成 3**（发布 `/chosen/display-scale=3`）。

我们的驱动确实在跑这条策略（`NATIVE_LEGACY: unit-scale status=0 requested=3 chosen=3 rot=0`），
但 `bounds` 报的是 **1080×1920 点**且像素尺寸为 0，形态更像是 **QuartzCore 侧把 scale 当成了 1、
而像素信息完全缺失**。

`OSLogStore` 这次返回 `no-store`：`+storeWithScope:0`（系统存储）在这个进程里被拒/不可用，
所以还是拿不到 SpringBoard 的日志——读取统一日志这条路暂时封住。

### 45.67 if：直接问 MobileGestalt 和 CADisplay 要 scale

`ca#N scale` 用 `dlsym` 取 `libMobileGestalt.dylib` 的 `MGGetFloat32Answer`/`MGGetSInt32Answer`，
读 `MainScreenScale`、`MainScreenStaticScale`、`MainScreenClass`、`MainScreenOrientation`，
同时读 `CADisplay -pointScale`：

```
ca#N scale mg scale=… static=… class=… orientation=… displayScale=…
```

判读：

| 输出 | 含义 |
|---|---|
| `mg scale=3` + `displayScale=3` | scale 链路是通的，`pixel=0` 来自另一处（像素/表面信息缺失） |
| `mg scale=3` 但 `displayScale=0` | CADisplay 没把 MG 的 scale 用上 → 问题在 QuartzCore 读显示参数的那一段 |
| `mg scale=0/1` | 驱动 `unit-scale` 没真正进到 MG（或被缓存），要在驱动侧修 |

镜像：`/tmp/opencode/boot-H236if.img`，sha256 `1b091b3a…`；插件 cdhash `457bee9d…`。

### 45.68 if 结果：探针把 backboardd 打崩了（MG 的键必须传 CFStringRef）

if 的本意是读 scale，但日志里只有 `mode` 没有 `scale`，紧接着是：

```
ca#201 mode 1080x1920 px=0x0 hz=60.000
NATIVE_TRAP: pid=56 comm=backboardd exc=1 code=0x1 sub=0x36e696158 sig=11
NATIVE_MTL: signal=11 addr=0x36e696158 pc=0x19c33ec14 lr=0x1a40f6e80
NATIVE_EXIT: pid=56 comm=backboardd status=0xb
```

同一形态出现两次（186 s 与 264 s，第二次是重启后的新 backboardd）——**是我的探针崩的**，
不是系统本身：`MGGetFloat32Answer` 的键类型是 **CFStringRef**，我传了 C 字符串，callee 把它当
CFString 解引用 → SIGSEGV。

顺带说明两件事：
1. 插件的崩溃上报与内核的 `NATIVE_TRAP` 都好用，能直接把“谁崩的、崩在哪”落进日志；
2. backboardd 被崩掉后 launchd 会重建（194 s 有新 `slide=`），所以这种崩不会把机器搞坏，
   但会让同一轮里的 `dpy=` 计数看起来“变多”（那是新实例的）。

ig 已改为 `CFSTR("MainScreenScale")` 等 CFString 键。镜像 `boot-H236ig.img`，
sha256 `0afd79f9…`；插件 cdhash `94aee03f…`。

### 45.69 ig 结果：MG 调用把探针线程挂死（不是崩溃）

ig 把 MG 的键改成 `CFStringRef` 之后不再 SIGSEGV，但换成了更坏的一种失败：

```
[201.33] ca#200 probe timer class=1 main=1 list=6 server=6 port=0x8b07 kr=0x0
[201.73] ca#201 mode mode 1080x1920 px=0x0 hz=60.000
（之后没有任何 ca# 行；同进程的 NATIVE_ACCEL_HB 一直在打：abi=223/17）
```

`mode` 之后整个 `probe_displays` 就再也不返回了——`dlopen("/usr/lib/libMobileGestalt.dylib")`
或 `MGGetFloat32Answer` 在 backboardd 里**阻塞**（MG 可能要求主线程/联系服务端）。没有 trap、
进程没死，所以从外面看就是“探针突然不说话”。

结论：**MobileGestalt 这条读 scale 的路封掉**。下一版把 MG 整段删掉，`scale` 只用
`CADisplay -pointScale`（它必须排在任何可能阻塞的调用之前，先打印后探测）。

### 45.70 内核构建：症结已定位到“镜像用了仓库里没写的配置”

继续尝试后，内核仍然构建不出来，但原因已经很清楚：

1. `~/UniXNU-cheeseburger/configs/cheeseburger_defconfig` 里
   `# CONFIG_XNU_NATIVE_LEGACY_DISPLAY is not set`、`# CONFIG_XNU_NATIVE_MOBILE_DISPLAY is not set`
   ——**两份 `.config` 都是关的**，而跑在机器上的镜像显然包含 `NativeLegacyDisplay`。
   说明那批镜像是用**仓库外的设置**（shell 环境或临时改过的 config）构建的。
2. 把 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y` 打开后，链接缺的
   `_native_a540_*` 就不再报错（它们只在 `libNativeLegacyDisplay.late.a` 里，这个归档
   只在 `NATIVE_LEGACY_DISPLAY=1` 时被 `-force_load`）——这条已确认。
3. 再往后卡在**归档与内核对象的循环依赖**：
   `build_archives` 需要 `bsd/DEVELOPMENT/*.o`，而对象由 XNU 构建产生；上一次失败的链接把
   对象清掉了，于是 `archive-01-build-corecrypto-14.log` 报 `nm: bsd_init.o: No such file`。
   删掉 `startup.o.json` 让 unixnu 走 bootstrap pass 也没能生成该记录（`kernel-bootstrap.log`
   仍然停在 `build_all_bootstrap` 链接）。
4. `XNU_NATIVE_MOBILE_DISPLAY=1` 会额外要求 `libNativeMobileDisplay.late.a`，而该文件不存在
   （`build/native-mobile-display/` 只有普通 `.a`）——所以这个开关只能在 late 归档也构建出来
   之后再用。

**结论**：内核路线要恢复，得先拿到当初那套构建设置（或补一个能同时产出 late 归档、且先于
归档步骤生成对象的脚本）。在那之前不要再指望“临时 export 几个变量”就能构建成功。
Mac 上的 `out/cheeseburger/.config` 已按原样恢复，`scripts/unixnu/tree.py` 也已还原。

### 45.71 ih 结果：`displayScale = 0`，与驱动发布的 3 不一致

安全的探针给出两条数据：

```
ca#201 mode  1080x1920 px=0x0 hz=60.000        ← bounds 对、像素 0、刷新率对
ca#202 scale displayScale=0.000                ← CADisplay 自己的 pointScale
```

驱动侧在同一轮里发布的是：

```
NATIVE_LEGACY: dims 1080x1920 canvas=1:1080,1:1920 dotpitch=1:163
NATIVE_LEGACY: unit-scale status=0 requested=3 chosen=3 rot=0
```

也就是说 **驱动说 scale=3，QuartzCore 算出来是 0**。这两者正好构成
`pixelWidth = 0 → pointScale = 0` 这条链，而 §45.58 里参考端口的 SpringBoard 就是被
`preferredScale == 0` 的 `BSFloatIsZero` 拒绝掉的。**这很可能就是 SpringBoard 不建 UI 的直接原因。**

`ca#N props` 这一行没有出现——`IOServiceGetMatchingService` +
`IORegistryEntryCreateCFProperties` 读整个属性字典在 backboardd 里同样把线程卡住了
（与 MG 一样是“挂住”而不是报错）。下一版改为只读单个属性
（`IORegistryEntryCreateCFProperty`），并且放一个“进入/返回”标记，便于区分卡在哪一步。

`NATIVE_LEGACY_STATE` 这一轮没有打印，无法据此判断 `surface` 有无。

### 45.72 现在的判断：需要动驱动（=需要内核构建）

把证据串起来：

```
驱动发布 canvas=1080x1920 / unit-scale=3        （33.6 s）
   ↓
CADisplay: bounds 1080x1920、pixelWidth/Height = 0、refreshRate 60、pointScale 0
   ↓
SpringBoard 的 FBSDisplayMode 校验要求 preferredScale != 0（参考端口实测）
   ↓
SpringBoard 不建 UI → 不提交图层 → backboardd 合成空树（18 pass / 0 draw）→ 0 swap
```

`pointScale` 的来源在 backboardd 侧是 `BKDisplayInfo` / `BKSDisplayServicesGetScreenScale()`，
最终落到 MobileGestalt 的 `MainScreenScale`；我们的驱动虽然把 `/chosen/display-scale=3` 写进去了，
但 MG 的读取/缓存发生在 33.6 s 之前（或根本没读这条）。**这件事只能在驱动启动早期发布，
或者在驱动里直接把默认 surface 建出来供合成器使用——两者都是内核侧改动。**

参考端口（sagit）的解法是“让 MG/BKS/CADisplay 的 scale 变成 3”，代价也是改驱动 + 重建 MG 缓存。
我们的 Data seed 里**没有** MobileGestalt 缓存文件（已挂载检查，`count 0`），所以从用户态改缓存这条路不成立。

### 45.73 ii 结果：MG 缓存**不存在**，缓存理论被否证

插件直接看文件（不调用 MG）：

```
mgcache#244 systemgroup.com.apple.mobilegestaltcache absent
mgcache#245 com.apple.mobilegestalt.plist              absent
mgcache#246 com.apple.MobileGestalt.plist              absent
mgcache#247 …/mobilegestaltcache/Library/Caches        absent
```

`ca#204 scale displayScale=0.000` 依旧。

结合驱动侧的实测（`unit-scale status=0 requested=3 chosen=3`，写的是
`IORegistryEntry::fromPath("/chosen", gIODTPlane)`，读回 u32 = 3）：

- **“旧缓存里 scale=0 顶住了 `/chosen`”这条在我們这台不成立**——本机 scratch Data 上
  MG 根本不落盘，每次现读；
- 因此 `CADisplay.pointScale == 0` 不是缓存问题，也不是 `/chosen` 没写进去的问题。

剩下最合理的解释只有一个：`pointScale` 是 QuartzCore 从**像素尺寸**推出来的
（`pixelWidth/pixelHeight == 0` → `pointScale == 0`），而像素尺寸来自显示对象的
**默认 surface**。也就是说 §45.72 里的那条链仍然成立，只是起点是 surface 而不是 MG。

`NATIVE_LEGACY_STATE` 这一轮仍未打印，无法从驱动状态行判断 `surface` 有无，
所以下一步用离线反汇编确认 `IOMobileFramebufferLegacy::create_default_fb_surface`
需要什么、在什么时机被调用、失败时返回什么。

### 45.74 设备侧访问方式变更（记录）

手机改到 `ls@192.168.10.225`，远程 shell 是 **PowerShell**（不是 cmd），密码文件是
`/tmp/opencode/askpass-win.sh`。带引号的 cmd 风格命令会报 `ParserError`，
因此新增 `/tmp/opencode/ps225`：把 PowerShell 脚本用 UTF-16LE + base64 通过
`-EncodedCommand` 传过去，彻底绕开引号问题。

```sh
./ps225 "Set-Location 'C:\Users\ls\AppData\Local\Android\Sdk\platform-tools'; .\adb.exe devices"
```

`adb`/`fastboot` 在新机器上位于 `C:\Users\ls\AppData\Local\Android\Sdk\platform-tools`，
镜像目录仍是 `D:\Users\ls\Documents\OnePlus5_ios`。
