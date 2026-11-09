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
