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
