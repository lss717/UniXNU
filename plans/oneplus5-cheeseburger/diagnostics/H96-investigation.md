# H96 只读调查：AMFI TrustCache 拒绝路径与 UFS 诊断分离

- 日期：2026-10-31
- 范围：H91/H95 基线之后的只读调查；未刷写设备、未改 userdata、未改正式签名策略。
- 基线：`plans/oneplus5-cheeseburger/BASELINE.md`。
- 目标：回答 `_check_cdhash_in_trustcache` 循环究竟卡在“可信数据缺失”、
  “注册/加载失败”、“查询未命中”还是“调用方权限拒绝”。

## 1. 结论摘要

1. **当前循环的直接拒绝点是 AMFI 的调用方权限门，不是 TrustCache 查询未命中。**
   原始 iPad7,1 21H461 kernelcache 中，AMFI 的
   `_check_cdhash_in_trustcache()` 对应 MAC policy syscall selector `0x5f`。
   它在读取 cdhash、调用 XNU `query_trust_cache()` 之前，先检查调用进程是否
   具有 `com.apple.private.amfi.can-check-trust-cache`。检查失败时打印
   `%s: Only allowed processes can check the trustcache` 并返回 `13`
   （`EACCES`）。这和 STATUS 中观察到的循环文本完全一致。
2. 因此，**继续改 TrustCache blob、继续加 boot-args、或直接把查询改成
   “永不拒绝”都不能解释当前循环**。下一步必须先确认调用方是谁，以及它的
   code signing/entitlement 状态为什么不可用。
3. 原始 SystemOS 镜像中，`com.apple.private.amfi.can-check-trust-cache` 及
   `Unable to find AMFI`、`Unable to connect to AMFI`、
   `cdhash: %@ is not in trust cache` 等字符串位于
   `/System/Library/Frameworks/ExtensionFoundation.framework/ExtensionFoundation`
   （Mach-O 起始偏移 `0x1785b000`，UUID
   `28968ac0-0ace-360e-83e3-c8e7ad996871`）。循环的候选调用方是加载
   ExtensionFoundation 的宿主/服务进程（例如 `pkd`/`extensiond` 一类），
   但在没有 H96a 运行日志前不能把具体进程名当成已证实事实。
4. H91 的 payload 确实携带 `kernel.macho.trustcache`（61,356 字节），
   DarwinBoot 会把它填入 `/chosen/memory-map/TrustCache`；H91 也没有触发
   “missing external trust caches” panic。因此“完全没有交付 TrustCache”
   不是当前循环的首要解释，但静态 cache 是否覆盖目标进程仍需单独验证。
5. H90d 的 `HCS=0x10` 不是“另一种 idle/live 编码”。按 UFSHCI 的 HCS 定义，
   bit 4 是 `HOST_ERROR_INDICATOR`；`HCS & 3 == 0` 表示
   `DEVICE_PRESENT` 和 `UTP_TRANSFER_REQ_LIST_READY` 都未置位。把
   `(HCS & 3) == 3` 放宽并不会让控制器进入可运行状态；应先解释并清除
   host error/控制器未 ready 的原因。UFS 与 TrustCache 必须继续分开。

## 2. 本轮读取与核验

### 2.1 仓库

- 主仓 `UniXNU`：`main` / `93c7fb6`，工作区干净。
- 设备仓 `UniXNU-cheeseburger`：`main` / `5ad54e2`，工作区干净。
- 关键子模块：`NativeUfs 43a4bc7`、`NativeRamBlock f3cffc9`、
  `DarwinBoot d099354`、`VerifiedRoot 2854c61`、`NativePrelink 2b6ffb5`。
- 没有执行 `git reset --hard`、`git clean -fdx`，没有覆盖任何未提交文件。

### 2.2 H91 产物

- boot：`cd81c5b8ec91f103f3e3c0fd7de7bfb26633f4fbabecd34490e5627dd6f3ff9b`
- payload：`e7fa5cdff58217886ebf269b30683c78da83c409ae179c356650f69869f08942`
- payload 内 `kernel.macho`：
  `7f02891c32825b75fcb76f2969ea2c1a541662d4c369d29fc85732b19f0e532d`
- payload 内 `kernel.macho.adt`：
  `83d733d770a9ec6961f60c1af13f4eeeb8552c776098241c0c536d13f810e54a`
- payload 内 `kernel.macho.trustcache`：
  `7416ca4f8377146626bb284e2133c76bee6cb4e3ee0af5d648b186235a7323a7`

H91 的 payload 启动参数已从 FAT 卷内 `unixnu.toml` 原样读出，见
`BASELINE.md` 第 3 节。当前 H91 是 Probe/窗口 UFS + 真实 PMGR
（`sheng-pmgr=2`），没有 `native-ufs-root=1`。

### 2.3 原始 iPad7,1 21H461 kernelcache

从 IPSW 的 `kernelcache.release.ipad7` 解出 46,415,900 字节 Mach-O；
其中的 AMFI kext 是原始未修改代码，用来对照当前 H91 内核里的同一段
AMFI。分析只读取二进制，不运行、不修改。

## 3. 实际启动链路与证据

| 阶段 | 现有证据 | 缺失证据 |
| --- | --- | --- |
| UEFI / DarwinBoot | G1 已实测菜单、按键、payload、DarwinBoot、屏幕日志；H91 payload 含 `kernel.macho`、ADT、TrustCache、Data seed | H91 本次启动的完整串口/屏幕日志 |
| XNU 进入 BSD/IOKit | H91 `kernel.macho` 可启动到用户态；STATUS H91 记录 | 精确构建提交、CFLAGS、kernel.json |
| NativeRamBlock / UFS | H91 为 Probe；STATUS 记录 SystemOS 读持续完成、无 `NATIVE_UFS_STALL` | 请求级 ID/OCB/OCS/中断日志 |
| APFS root | H87a 成功挂载；H89b 过 `mount-phase-1`；H91 沿用 | 本次挂载的 UUID/manifest 校验明细 |
| launchd / boot tasks | H87c/H89b/H91 已到 launchd 和 `mount-phase-1` | 任务退出码、等待点、失败任务名 |
| FileSet KC / driverkitd | `KextLog: Loading FileSet KC(s)`、`KextLog: driverkitd is active` | driverkitd 之后的首个失败点、Cryptex1 挂载结果 |
| AMFI / TrustCache | 循环文本 `_check_cdhash_in_trustcache ... Only allowed processes`；H91 payload 有静态 TrustCache | 调用方 PID/进程名、entitlement 状态、cdhash、返回码 |
| display / WindowServer | 未到达 | 任何显示初始化证据 |

关键判断：H91 的 UFS 读没有硬卡死；`FileSet KC`/`driverkitd` 是当前最后的
可见阶段。不要把 H89b/H90d 的 UFS 停住当成 H91 当前根因，也不要用 UFS
问题解释 AMFI 循环。

## 4. 关键发现：AMFI selector `0x5f` 的权限门

### 4.1 原始 AMFI 二进制中的位置

原始 21H461 kernelcache 中 AMFI kext：

- `_PrelinkExecutableLoadAddr`：`0xfffffff0052db6c0`
- `_PrelinkExecutableSize`：`0xb153`
- AMFI `__TEXT_EXEC,__text`：`0xfffffff005aaa000`，大小 `0x1fa90`
- AMFI `__TEXT,__cstring`：`0xfffffff0052dbd68`，大小 `0x9247`

`_check_cdhash_in_trustcache()` 的 MAC policy syscall dispatcher 在
`0xfffffff005ab72a8`。它以 `w1 - 0x5a` 查 13 项跳表
（`0xfffffff0052e5e40`），selector `0x5f` 跳到
`0xfffffff005ab73a8`。

### 4.2 selector `0x5f` 的执行顺序

从反汇编可直接读出：

```text
0xfffffff005ab73a8  adrp/add  x1, "com.apple.private.amfi.can-check-trust-cache"
0xfffffff005ab73b4  bl        0xfffffff005ab138c        ; 查询进程 entitlement
0xfffffff005ab73b8  tbz       w0, #0, 0xfffffff005ab75cc ; 无权限 -> 拒绝
0xfffffff005ab73bc  ...       copyin 32 bytes from user arg
0xfffffff005ab73f0  bl        0xfffffff005aad100        ; query type 1
0xfffffff005ab7410  bl        0xfffffff005aad100        ; query type 2
0xfffffff005ab7424  ...       copyout 32 bytes
0xfffffff005ab75cc  ...       print rejection message
0xfffffff005ab75e4  mov       w19, #0xd                 ; EACCES
```

拒绝路径使用的字符串：

```text
0xfffffff0052e18ad  "%s: Only allowed processes can check the trustcache\n"
0xfffffff0052e18e2  "int _check_cdhash_in_trustcache(struct proc *, user_addr_t)"
```

权限字符串：

```text
0xfffffff0052dc597  "com.apple.private.amfi.can-check-trust-cache"
```

这条路径在 XNU `query_trust_cache()` 之前结束。也就是说：

- 如果日志只出现 `Only allowed processes...`，**XNU 的 TrustCache
  查询根本没有被调用**；
- 这时看到的是调用方身份/entitlement 问题，不是 cdhash 不在静态/加载
  trust cache 中的问题；
- 只有权限检查通过后，selector `0x5f` 才会 copyin 32 字节参数并向
  XNU 查询 type 1/2，随后把结果位图 copyout。

这解释了为什么 H93 修改 `cryptexd` 后循环重新出现：被修改的二进制不再
具有可信签名/entitlement，调用 AMFI 时在权限门就被拒绝，而不是因为
SystemOS trust cache 内容不对。

### 4.3 调用方候选

在原始 SystemOS 镜像中搜索
`com.apple.private.amfi.can-check-trust-cache`，命中
`/System/Library/Frameworks/ExtensionFoundation.framework/ExtensionFoundation`
（Mach-O 起始 `0x1785b000`，UUID
`28968ac0-0ace-360e-83e3-c8e7ad996871`；entitlement 字符串约在
`0x178e3fxx`）。同一二进制包含：

```text
Unable to find AMFI
Unable to connect to AMFI [%ld]
cdhash: %@ is not in trust cache
Unknown error (%ld) checking cdhash %@
com.apple.private.amfi.can-check-trust-cache
```

因此循环的调用方很可能是使用 ExtensionKit 的宿主/服务进程（`pkd`、
`extensiond` 一类），而不是 XNU 或 APFS 本身。**具体进程名尚未证实**；
必须用 H96a 的 `pid/comm` 日志确定。

### 4.4 H91 的 TrustCache 状态

- `kernel.macho.trustcache` 存在且为 61,356 字节，DarwinBoot 的
  `ValidTrustCaches` 会校验并填入 ADT 的 16 字节 `TrustCache` 属性。
- H91 内核字符串包含 `NATIVE_TRUSTCACHE_LOAD_START`、
  `NATIVE_TRUSTCACHE_PROP`、`NATIVE_TRUSTCACHE: missing external trust
  caches`。反汇编 H91 的 `_load_static_trust_cache` 可见：range 长度为 0
  会走 panic cold path，静态 module `loadModule` 失败也会走 panic cold
  path。H91 能启动到 `driverkitd`，因此这次启动中静态 TrustCache range
  非零且静态 module 至少成功加载。
- 但 H91 的完整日志没有保存，静态 module 的 cdhash 列表是否覆盖目标
  进程仍未验证。这仍是 H3 假设，不是当前循环的直接原因。

## 5. 根因假设（按置信度排序）

### H1（高）：调用方权限门拒绝，不是 TrustCache 查询未命中

`_check_cdhash_in_trustcache` 在 selector `0x5f` 的入口检查
`com.apple.private.amfi.can-check-trust-cache`，调用方没有该 entitlement
（或 AMFI 无法从它的 code signature 取得 entitlement 对象）时直接返回
`EACCES`，用户态循环重试。

**区分方法**：H96a 同时记录
`NATIVE_AMFI_SYSCALL ... call=0x5f` 和 `NATIVE_TC_QUERY`。若循环期间只有
前者、没有后者，且 `entitled=0`，H1 成立。

### H2（中）：调用方本身处于“能运行但签名状态不可信”的 bring-up 状态

当前 H91 使用 permissive AMFI（`amfi_get_out_of_my_way=1`、
`amfi=0x94`、`amfi_allow_any_signature=1`、
`native-skip-exec-signature=1`）。这些开关可能让进程越过 exec 拒绝，
但进程的 `CS_VALID`/`CS_SIGNED`/entitlements 并未按正常路径建立；或者
调用方来自 SystemOS cryptex，而对应的 `Cryptex1,SystemTrustCache` 尚未
加载。结果是进程能跑，但 AMFI 不承认它的 entitlement。

**区分方法**：H96a 日志中的 `csflags`、`blob`、`platform`、`entitled`
四个字段：

- `blob=NULL` 或 `csflags` 缺 `CS_VALID`：签名/entitlement 没有被保留；
- `blob!=NULL`、`platform=0`、`entitled=0`：签名在，但未被当作可信
  platform binary；
- `entitled=1` 但 AMFI 仍拒绝：AMFI 内部的 entitlement 查询与 XNU
  查询不一致，需继续追 AMFI 的 proc/cred 路径。

### H3（低，但对最终 boot 仍重要）：静态 TrustCache 不覆盖 SystemOS/Cryptex 调用方

H91 的静态 cache 来自 `kernel.macho.trustcache`，主要覆盖 OS root；
SystemOS/Cryptex1 有独立的 `Cryptex1,SystemTrustCache`。即使 H1/H2 的
权限门被正确满足，目标 cdhash 仍可能在 XNU 查询中 miss，导致
`driverkitd`/FileSet KC 无法继续。

**区分方法**：权限门通过后，看 H96a 的 `NATIVE_TC_QUERY` 是否出现、
`ret` 是否为 `KERN_NOT_FOUND`，以及静态/SystemOS cache 的 module 数与
目标 cdhash 是否匹配。不要在权限门未通过时用 H3 解释循环。

## 6. H96a 最小诊断补丁

### 6.1 补丁

`patches/xnu/trustcache-amfi-trace.patch`

修改两个文件，全部由 boot arg 控制，默认关闭：

1. `security/mac_base.c`
   - 在 `__mac_syscall()` 入口，对
     `com.apple.driver.AppleMobileFileIntegrity` 的 selector `0x5a..0x66`
     打点。
   - selector `0x5f` 最多记录 64 次；其他 selector 每个只记录第一次。
   - 记录：`pid`、`comm`、`call`、`arg`、`proc_getcsflags(p)`、
     `csproc_get_blob(p)`、`csblob_get_platform_binary(blob)`、
     `IOCurrentTaskHasEntitlement("com.apple.private.amfi.can-check-trust-cache")`、
     以及 copyin 的 20 字节 cdhash。
   - boot arg：`native-trace-amfi-syscall=1`。
2. `bsd/kern/kern_trustcache.c`
   - 在 `query_trust_cache()` 返回前记录调用方 pid/comm、query type、
     完整 20 字节 cdhash 和返回值；最多 64 次。
   - boot arg：`native-trace-trust-cache=1`。

没有修改 AMFI 二进制，没有改变 trust cache 注册/查询逻辑，没有改变
AMFI 策略、签名校验、root auth 或 VerifiedRoot。默认 boot arg 缺失时
两个函数都立即返回。

### 6.2 构建集成

`scripts/build-xnu-4k-baseline.sh` 会自动应用
`patches/xnu/*.patch`，新补丁无需额外 CFLAGS。已用干净的
`xnu-10063.141.1` 源树执行：

```text
git apply --check patches/xnu/trustcache-amfi-trace.patch  -> PASS
```

本机没有 macOS/Xcode 内核工具链，**尚未完成实际 XNU 编译**；这属于
本轮未完成项，不能把“补丁 apply 成功”当成“已能启动”。

构建后必须检查产物确实包含两处诊断字符串（不是只看补丁文件）：

```sh
strings build/.../kernel.macho | grep -F 'NATIVE_AMFI_SYSCALL'
strings build/.../kernel.macho | grep -F 'NATIVE_TC_QUERY'
strings build/.../kernel.macho | grep -F 'native-trace-amfi-syscall'
strings build/.../kernel.macho | grep -F 'native-trace-trust-cache'
```

四条都存在，才说明 `security/mac_base.c` 和 `bsd/kern/kern_trustcache.c`
的改动进入了最终链接产物；任何一条缺失都先查 object 是否被缓存跳过或
被后续 CFLAGS 覆盖，不要上机。

### 6.3 H96a 启动参数

在 H91 的 payload 参数基础上，只追加：

```text
native-trace-amfi-syscall=1 native-trace-trust-cache=1
```

其余 H91 参数、ADT、TrustCache、Probe/PMGR 配置保持不变。不要同时改
UFS、AMFI 策略或 root auth。

### 6.4 预期日志与判定

权限门拒绝（H1）：

```text
NATIVE_AMFI_SYSCALL: pid=<N> comm=<name> call=95 arg=0x... csflags=0x... blob=0x... platform=... entitled=0 cdhash=... cdhash_valid=1
_check_cdhash_in_trustcache: Only allowed processes can check the trustcache
```

随后循环重复，但**不应出现** `NATIVE_TC_QUERY`。

权限门通过、查询 miss（H3）：

```text
NATIVE_AMFI_SYSCALL: ... call=95 ... entitled=1 ...
NATIVE_TC_QUERY: pid=<N> comm=<name> type=... cdhash=... ret=<...>
```

两条日志的 `pid` 必须一致，才能把“同一调用方的 0x5f 调用”和
“XNU 查询”对应起来；不要只看全局是否出现过 `NATIVE_TC_QUERY`。

若 `ret` 为 `KERN_NOT_FOUND`，再比较静态 cache module 与 cdhash；
若 `ret=0`，问题在 AMFI 之后的策略/调用方逻辑。

判定：

- 出现 `call=95` 且 `entitled=0`：H1 成立，停止改 TrustCache blob，
  转向“调用方为什么没有 entitlement / 签名状态为什么不可信”。
- 出现 `call=95` 且 `entitled=1`，但 AMFI 仍拒绝：需要继续反汇编/对照
  AMFI 的 entitlement 查询路径；不要通过删除检查来推进。
- 完全没有 `call=95`：当前循环不是这条 AMFI 路径，重新核对日志来源，
  不要继续按 H1 处理。

### 6.6 H96a 构建记录（2026-10-31）

构建机：`192.168.10.103`（macOS 15.8.2 / Xcode 26.3），使用 H91 的
`out/cheeseburger/tree` 对象树，源版本 `xnu-10063.141.1`（`d8b8029`）。
构建前已把 H91 的 `kernel.macho`、`kernel.json`、`payload.img`、
`payload.json` 和 raw kernel 备份到 `~/h96-backup/`。

使用的关键环境（从 H91 对象树的 stamp 反推并匹配）：

```text
XNU_TRUST_CACHE_RUNTIME=0
XNU_OWNER_CACHE_MOUNT=1
XNU_OWNER_CACHE_STARTUP=1
XNU_OWNER_CACHE_CARRIER=1
XNU_NATIVE_CS_HASH_CACHE=1
XNU_OWNER_UNION_SYSTEMOS=1
XNU_BRINGUP_CACHE_MOUNT=1
XNU_OWNER_DATA_MOUNT=1
XNU_OWNER_BOOT_MANIFEST=0
XNU_OWNER_DATA_VOLATILE=1
XNU_OWNER_CRYPTEX_FILES=0
XNU_NATIVE_UFS=0
XNU_NATIVE_UFS_PROBE=1
XNU_OWNER_ROOT_AUDIT=0
XNU_VERIFIED_ROOT_PROBE=0
XNU_NATIVE_VIRTIO_BLOCK=0
XNU_SOURCE_CORECRYPTO14=1
XNU_NATIVE_RAM_BLOCK=1
XNU_NATIVE_MOBILE_DISPLAY=0
XNU_NATIVE_AES=0
XNU_NATIVE_ADRENO=0
XNU_ARM_DT_PLATFORM=1
XNU_ARMCPU=1
XNU_SOURCE_PTHREAD=1
XNU_NATIVE_ARCH_TIMER=1
XNU_DT_PANIC_REGION=1
XNU_BOOT_PROGRESS=0
XNU_SOURCE_MOCKFS=1
XNU_CRYPTO_BOOTSTRAP=source
XNU_OWNER_DATA_VOLUME_UUID=D312EFB3-1335-4E03-87C3-D78A298BB0B1
XNU_SHENG_PMGR=1
```

预链接参数沿用 H91：

```text
--slide=0x5000000
--prelinked out/ipsw/21H461/kernelcache.decompressed
--root ...（与 H91 的 15 个 root 完全相同）
--early-security-init com.apple.driver.AppleMobileFileIntegrity=0xfffffff005ab4ae0
```

产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| H96a raw kernel | 19,445,640 | `92e55a7076cac782429d7ca3c60e88fabbf44d8d55e3d1b5ccb9647683160045` |
| `H96a-kernel.macho` | 52,088,832 | `f5dbbe1c6a15a8f6fbfbccbb7cbf562edc385769a30845c68112bc9e324e466c` |
| `H96a-payload.img` | 79,691,776 | `8c92f8c85ccaed52ced0693242c5acd98285ae857cfc15f7d8859c6d4f7be14e` |
| `boot-H96a-amfitrace.img` | 81,147,904 | `790de81156545c2fa64c4271f92207ade01d0019ca8af35ca538f5d6fbeb98b5` |

`H96a-kernel.macho` 已用 `strings` 确认包含
`NATIVE_AMFI_SYSCALL`、`NATIVE_TC_QUERY` 和两个 trace boot arg 字符串。
payload 从 H91 payload 复制，只替换 `Payloads/kernel.macho` 和
`unixnu.toml` 的 args；ADT、TrustCache、Data seed 均沿用 H91。
boot image 从 H91 boot image 复制，只在 ramdisk 偏移 `1456128` 处
替换为同尺寸的 H96a payload；UEFI kernel 和 header 未改。

第一次 `fastboot boot` 返回 `Booting OKAY`，但设备停在 UEFI Shell，未进入
UniXNU/XNU。原因：用 `mcopy` 覆盖 `UNIXNU~1.TOM` / `KERNEL~1.MAC` 时
指定了 8.3 短名，导致 VFAT 长名 `unixnu.toml` / `kernel.macho` 丢失；
UniXNU 按长名查找配置/内核失败，回到 shell。已删除旧目录项并用长名重新
写入，修正后 payload/boot 哈希为上表值。raw kernel 和 kernel.macho 未变。

注意：构建脚本在本次重编译了 12 个 object（trace 两处，加上它每次都会
重新应用的 late patches 所触及的对象）。环境变量按 H91 stamp 匹配，但
尚未做“去掉 trace 补丁后重建并比对 H91 哈希”的严格 control。H96a 的
结论只应归因于 trace 两处，除非后续 control 证明其他 object 未改变。

### 6.7 H96a 首次 XNU 结果与 H96a2 强制 trace

H96a（修正长名后）成功进入 XNU，屏幕可见：

```text
NATIVE_UFS_PROGRESS: ...
NATIVE_UFS_WINDOW: SystemOS ...
_check_cdhash_in_trustcache(struct proc *, user_addr_t): Only allowed processes can check the trustcache
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
```

这确认了三点：

1. H96a 的 XNU/payload 链正常，长名修复有效；
2. UFS 仍在持续完成 SystemOS 读，没有 `NATIVE_UFS_STALL`；
3. AMFI 的 `_check_cdhash_in_trustcache` 拒绝循环在 `driverkitd` 阶段真实存在。

但该帧没有看到 `NATIVE_AMFI_SYSCALL`。两种解释：

- 64 次 trace 预算在截图前已经滚出屏幕；
- `native-trace-amfi-syscall=1` 没有被 `PE_parse_boot_argn` 解析到。

因此构建 H96a2：**强制打开 trace**，不依赖 boot arg，并把 selector
`0x5f` 预算提高到 100000、query 预算提高到 4096，使屏幕任意时刻都应能
看到 trace 与 AMFI 拒绝行交替出现。H96a2 只用于诊断；仓库默认补丁仍
保持 boot-arg 关闭。

H96a2 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a2-kernel.macho` | 52,088,832 | `918cdbe11a638e7a603b902850b4aa3372543a941e5596971eef654629303a18` |
| `H96a2-payload.img` | 79,691,776 | `da268d87a7c0bd267a4b09d92f7c27bbb03afb5cb910bdbf71fda85bf05c019e` |
| `boot-H96a2-amfitrace.img` | 81,147,904 | `8c58b13832c14d6bf2a8f27fcc6a98aad4323ef1aebb03ae00db427883bc062d` |

H96a2 源码差异（仅构建树）：

```diff
-static int native_amfi_syscall_trace = -1;
+static int native_amfi_syscall_trace = 1;
-static int native_trace_tc_query = -1;
+static int native_trace_tc_query = 1;
```

并分别把 `0x5f`/query 的限频从 64 提高到 100000/4096。除 trace 外，
H96a2 的配置、ADT、TrustCache、Data seed 与 H96a/H91 相同。

### 6.8 H96a2 结果与 H96a3 修正

H96a2 屏幕可见 `NATIVE_TC_QUERY` 多次成功返回：

```text
NATIVE_TC_QUERY: pid=24 comm=UserEventAgent type=1 cdhash=... ret=0
NATIVE_TC_QUERY: pid=1 comm=launchd type=0 cdhash=34f3216e... ret=0
NATIVE_TC_QUERY: pid=80 comm=spracy type=0/1 cdhash=... ret=0
KextLog: driverkitd is active
```

说明 XNU 的 TrustCache 查询本身工作，且能命中；但这帧仍没有
`NATIVE_AMFI_SYSCALL`。原因已定位：`__mac_syscall` 的 target 过滤写成了
bundle ID `com.apple.driver.AppleMobileFileIntegrity`，而 AMFI 注册的
MAC policy 名更可能是 `AppleMobileFileIntegrity`，导致 trace 直接 return。

另外，旧 trace 在 `printf` 参数里调用 `IOCurrentTaskHasEntitlement()`。
这不仅是只读观测，可能提前初始化/缓存调用方的 entitlement，从而改变
AMFI 后续判断。H96a2 中没有再看到 `Only allowed` 循环，不能排除这个
副作用。

因此 H96a3：

- 取消 target 过滤，`0x5a..0x66` 的调用都会记录，并打印实际 `target`；
- 删除 `IOCurrentTaskHasEntitlement()` 调用，只保留 pid/comm/target/
  csflags/blob/platform/cdhash，避免改变策略状态；
- `0x5f` 仍强制、限频 100000；query trace 强制、限频 4096。

H96a3 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a3-kernel.macho` | 52,088,832 | `b36ec3a89e05f4fa9e364b7f7a3191951c9bb0c60bd21dffd6eed99fed0e648e` |
| `H96a3-payload.img` | 79,691,776 | `d5030ee552dc9627a000d6ddc8d2eaa9ccd6310ac3c4b6dfc062f5a152d9887d` |
| `boot-H96a3-amfitrace.img` | 81,147,904 | `98192bb07988871506eaa49a1a43c98644ef562243853923b0c277be84fa22e1` |

### 6.9 H96a3 结果与 H96a4 受控绕过

H96a3 屏幕可见多次 `NATIVE_TC_QUERY ... ret=0`（UserEventAgent、
launchd、xpcproxy），但仍完全没有 `NATIVE_AMFI_SYSCALL`。H96a3 已强制
trace 并取消 target 过滤，因此结论是：**AMFI 的
`_check_cdhash_in_trustcache` 检查不是从 XNU `__mac_syscall` 进入的**
（至少 H96a3 的可见窗口内没有 `0x5a..0x66` 调用），而不是 boot arg 或
滚屏问题。

为直接拿到拒绝点的调用方和查询结果，制作 H96a4 一次性诊断镜像：

- 在 H96a3 prelinked kernel 的 AMFI 拒绝分支，把
  `VM 0xfffffff00aab73b8` 的 `tbz w0, #0, reject` 改成 `nop`；
- 只跳过 `com.apple.private.amfi.can-check-trust-cache` 的权限门，
  TrustCache 查询本身仍然执行；
- 预期 AMFI 自己的 `Process %d is checking...` 日志会打印调用方 PID，
  同时 `NATIVE_TC_QUERY` 会给出 cdhash 和 hit/miss。

这是**受控诊断绕过**，只存在于独立镜像 H96a4，不是仓库默认配置，也不是
最终修复；它没有把任意 hash 无条件加入 TrustCache，也没有永久关闭 AMFI。

H96a4 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a4-kernel.macho` | 52,088,832 | `86a7e63abf3e32725e5665c3c538bc21c541845a542d2a9fbcfb9194a4e0feb6` |
| `H96a4-payload.img` | 79,691,776 | `6d6f49355ca1b1f09e70f39ded35fdeda7ba0064d5ceac29db89501f45a22ec0` |
| `boot-H96a4-tcbypass.img` | 81,147,904 | `f745b54f551ab6473fe8e6aeee68951d592e8d128ed5eb7facce5308bf3f6be0` |

### 6.10 H96a5：首个 AMFI 拒绝即打印调用方并 panic（B 方案）

按用户选择 B，H96a5 不再依赖滚屏，而是在 AMFI 的拒绝分支做一次
**只读诊断 panic**：

- 在 H96a3 prelinked kernel 的 AMFI 拒绝分支
  `VM 0xfffffff00aab75d8` 改成跳到代码洞
  `VM 0xfffffff00a96b318`；
- 代码洞读取 `proc->p_pid`（`+0x60`）和 `proc->p_comm`（`+0x5bc`），
  拼接原函数名后调用 `panic()`：
  ```text
  H96_AMFI_REJECT: func=%s pid=%d comm=%s
  ```
- `panic` 会停住系统并保留屏幕，不再继续刷屏；这是一次性诊断，
  不改变 AMFI 策略、不跳过权限门、不修改 TrustCache。

H96a5 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a5-kernel.macho` | 52,088,832 | `2994ae9d7f7dae99d84f597ce3edf4a3a05a962de7fbbf922ddb2893022150cb` |
| `H96a5-payload.img` | 79,691,776 | `2ed839d356e313a520733963e25965af3c9d30bf2b982e0fe9e83dc15690d9a2` |
| `boot-H96a5-paniclog.img` | 81,147,904 | `c2a183500c2cff77c3331751e862c5b5487b937d256e49608add075ab81361cc` |

预期屏幕（只出现一次，然后停在 panic）：

```text
H96_AMFI_REJECT: func=int _check_cdhash_in_trustcache(struct proc *, user_addr_t) pid=<PID> comm=<NAME>
```

拿到 PID/comm 后即可判断拒绝方是 launchd、amfid、pkd、xpcproxy 还是其他
进程；随后沿该进程的签名/entitlement 来源继续，而不是继续改 TrustCache。

### 6.11 H96a5 结果：拒绝方是 driverkitd，且原版 driverkitd 本就没有该 entitlement

H96a5 panic 屏幕给出：

```text
NATIVE_AMFI_SYSCALL: pid=63 comm=driverkitd target=AppleF... call=95
  csflags=0x2202331 blob=0xfffffff6dfe23050 platform=1 cdhash=... cdhash_valid=1

H96_AMFI_REJECT: func=int _check_cdhash_in_trustcache(struct proc *, user_addr_t)
  pid=63 comm=driverkitd
```

因此调用方确定为 **driverkitd（PID 63）**，selector 为 95（0x5f），
`platform=1`、`blob` 非空、`csflags=0x2202331`，说明它的 code signing
blob 是被 AMFI 识别为 platform binary 的；但 entitlement 门仍然拒绝。

在 macOS 构建机上挂载原版 iPad7,1 17.7.11 OS DMG，
`/usr/libexec/driverkitd` 的签名是 **adhoc**，CDHash
`2811f83446d213b1b14a8f7b0e81b79063fadf77`，entitlements 只有：

```text
com.apple.private.kernel.get-kext-info
com.apple.private.sandbox.profile:embedded = com.apple.driverkitd
com.apple.private.security.iocatalog-management
com.apple.private.security.kext-collection-management
com.apple.private.security.storage.driverkitd
com.apple.private.spawn-driver
com.apple.private.xpc.launchd.job-manager = com.apple.driverkitd
com.apple.runningboard.launch_dexts
```

**没有** `com.apple.private.amfi.can-check-trust-cache`。所以在当前
签名状态下，AMFI 拒绝 driverkitd 是符合策略的；问题变成：
**driverkitd 为什么在本次 bring-up 中会走到这个未授权的 AMFI MAC
syscall 路径？**

最可能的解释不再是“TrustCache blob 缺失”，而是：

1. driverkitd 正常应该通过 DriverKit/AMFI 的 IOKit user client 或
   SystemOS/Cryptex 信任链处理 driver approval；当前环境中该路径不可用，
   于是回退到 `__mac_syscall`，而 driverkitd 没有该 entitlement；
2. driverkitd 被错误的 launchd/SystemOS 状态或被注入的
   ExtensionFoundation/Security 路径带入了 trust-cache 查询；
3. 当前 AMFI 的 IOKit service/user client 未启动或未匹配，导致回退。

这些都需要在 H96a6 中进一步区分。

### 6.12 H96a6：跳过权限门并打印 TrustCache 查询结果

H96a6 在 H96a3 基础上做两个二进制诊断改动：

- 把 AMFI 权限门的 `tbz`（`VM 0xfffffff00aab73b8`）改成 `nop`，让
  driverkitd 的请求进入实际查询；
- 在 AMFI 查询完成、copyout 之前（`VM 0xfffffff00aab7424`）跳到代码洞，
  读取 `p_pid`、`p_comm`、查询结果位图 `[sp+0x58]` 和 cdhash
  `[sp+0x40..0x50]`，然后 `panic()`：
  ```text
  H96_TC_RESULT: pid=%d comm=%s mask=0x%llx cdhash=%016llx%016llx
  ```

`mask=0` 表示 AMFI 的两次查询都命中；`mask=3` 表示两次都 miss。
这能区分“driverkitd 只是没有 entitlement，但它要查的 cdhash 已在
TrustCache 中”与“cdhash 本身也不在 TrustCache 中”。

H96a6 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a6-kernel.macho` | 52,088,832 | `d06f6e695cc21093c8ffb0acc4dec0d3458738bf69ed2359c7f430d9d139026e` |
| `H96a6-payload.img` | 79,691,776 | `aec14df75054b80832399301ef2289a9902fe2c0f07e5732d492163975db7881` |
| `boot-H96a6-tcresult.img` | 81,147,904 | `3ac690a0e083202668173215e68b942eb94310118f098169c1646af616dbd46b` |

### 6.13 H96a6 结果：目标 cdhash 在静态 cache 命中，loadable 查询 miss

H96a6 panic 屏幕给出：

```text
NATIVE_AMFI_SYSCALL: pid=63 comm=driverkitd target=AMFI call=95
  arg=0x16f23b710 csflags=0x22002301 blob=0xfffffff... platform=1
  cdhash=7bb1e5321fc19a7efbb83d7eb54ca15b cdhash_valid=1

NATIVE_TC_QUERY: pid=63 comm=driverkitd type=1
  cdhash=1fc19a7... ret=0
NATIVE_TC_QUERY: pid=63 comm=driverkitd type=2
  cdhash=1fc19a7... ret=56

H96_TC_RESULT: pid=63 comm=driverkitd mask=0x3
  cdhash=7bb1e5321fc19a7efbb83d7eb54ca15b
```

判读：

- `target=AMFI`：实际 MAC policy 名是 `AMFI`，不是 bundle ID；这解释了
  H96a2/H96a3 旧 target 过滤为什么没有日志。
- type 1 查询 `ret=0`：目标 cdhash 已在**静态 TrustCache** 命中。
- type 2 查询 `ret=56`：`KERN_NOT_FOUND`，loadable/SystemOS 侧没有
  该 cdhash。
- 更清晰照片显示 `mask=0x1`。按 AMFI 查询分支的代码语义：
  bit0 在 type 1 返回非 0 时置位，bit1 在 type 2 返回非 0 时置位；
  因此 `mask=0x1` 表示 **type 1（静态）miss、type 2（loadable）hit**。
  目标 driver 在 loadable TrustCache 中，静态 miss 对 DriverKit driver
  是预期结果。
- `cdhash=7bb1...` 是 driverkitd 请求检查的**目标**（driver/kext），
  不是 driverkitd 自身 cdhash；原版 driverkitd 自身是 adhoc
  `2811f834...` 且没有 trust-cache entitlement。
- 照片中紧随其后的两条 `NATIVE_TC_QUERY pid=63 type=1/2` 使用的是
  另一个 cdhash `1fc19a...`，不能直接当作 AMFI 目标 `7bb1...` 的查询
  结果；AMFI 内部查询可能不经过 XNU `query_trust_cache` trace。

这进一步确认：**当前循环不是“TrustCache 完全缺失”**。按 `mask=0x1`
的代码语义，目标 driver 已在 **loadable TrustCache** 命中；静态查询
miss 对 DriverKit driver 是正常。真正的阻塞是：
1. driverkitd 自身没有 `com.apple.private.amfi.can-check-trust-cache`，
   却被带进了 `__mac_syscall("AMFI", 0x5f, ...)` 路径；
2. 因此 AMFI 在返回 loadable hit 之前就拒绝了调用方；
3. 需要在 driverkitd 正常使用的 AMFI IOKit user client / amfid / XPC
   路径上找为什么它回退到了未授权的 MAC syscall。

下一步应优先回答：**为什么 driverkitd 会走这个未授权的 MAC syscall，
而不是正常的 AMFI IOKit user client/DriverKit 路径？** 这比继续补
TrustCache blob 更能解释循环。

### 6.14 H96a7：AMFI IOKit service / user client 路径打点

H96a7 在 XNU 源码层增加：

- `IOService::registerService()`：当类名为
  `AppleMobileFileIntegrity` 时置 `h96_amfi_service_registered=1` 并打印
  `H96_AMFI_SERVICE: registered`；
- `IOUserClient::externalMethod()`：当类名为
  `AppleMobileFileIntegrityUserClient` 时累加 `h96_amfi_uc_calls`，
  前 8 次打印 `H96_AMFI_UC: selector=...`；
- `security/mac_base.c` 的 AMFI syscall trace：当
  `pid=... comm=driverkitd` 且 `call=0x5f` 时 panic：
  ```text
  H96_AMFI_PATH: pid=%d comm=%s target=%s service=%d uc_calls=%u
  ```

这能区分：

- `service=0`：AMFI IOService 从未注册/发布，driverkitd 只能回退；
- `service=1, uc_calls=0`：service 在，但 user client 从未被调用或打开失败；
- `service=1, uc_calls>0`：user client 路径被使用过（可能由 amfid/其他
  进程），driverkitd 仍选择 MAC syscall，需要继续看 open 返回/调用条件。

H96a7 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a7-kernel.macho` | 52,088,832 | `0befa003cccd1642f6581fa1c96818f81681b47a336a7093c83635307dba0322` |
| `H96a7-payload.img` | 79,691,776 | `0313ac797d974c0ce968f1aecbf2718f3c70abd309c350a43372eba34a9e7336` |
| `boot-H96a7-amfipath.img` | 81,147,904 | `413e2b50e0708827292aedd84b81b0243cea718f5160d6adbff11e203d3589b6` |

### 6.15 H96a7 结果：AMFI service 已注册，但 user client 从未被调用

H96a7 panic 给出：

```text
H96_AMFI_PATH: pid=63 comm=driverkitd target=AMFI
  service=1 uc_calls=0
```

判读：

- `service=1`：`AppleMobileFileIntegrity` IOService 已注册/发布；
- `uc_calls=0`：`AppleMobileFileIntegrityUserClient::externalMethod` 从未
  被调用；
- 同屏还出现 `amfid[47] triggered unnest ...`，说明 **amfid 进程存在**；
- 因此 driverkitd 没有走 AMFI user client 路径（或 open 在
  `externalMethod` 之前就失败），而是直接调用了
  `__mac_syscall("AMFI", 0x5f, ...)`；该调用要求
  `com.apple.private.amfi.can-check-trust-cache`，而原版 driverkitd
  没有该 entitlement。

这解释了为什么“TrustCache 里有目标 cdhash”仍然循环：卡在调用路径和
entitlement，而不是 cache 内容。

下一步实验 H96a4：使用已经构建的“全局跳过 AMFI entitlement 门”的
一次性诊断镜像，观察 driverkitd 的 check 返回成功后系统是否能越过
driverkitd，以及下一个阻塞点是什么。H96a4 不是最终修复，也不进入默认
配置；它只用于确认 gate 是否是当前唯一阻塞。

### 6.16 H96a4 结果：跳过 AMFI gate 后进入新的 UFS/后续停点

H96a4（全局跳过 AMFI entitlement 门）启动后：

- 可见的 `_check_cdhash_in_trustcache ... Only allowed` 循环消失；
- 系统继续执行大量 `NATIVE_UFS_WINDOW` / `NATIVE_UFS_PROGRESS`，
  最后一次可见进度约为 `winBytes=329618936`，随后日志不再变化；
- 没有 `NATIVE_UFS_ALIVE` heartbeat，也没有 `NATIVE_UFS_STALL` panic；
- 最后一条窗口请求为 `SystemOS req=... block=2f1ea8 ...`，进度行
  `winFlight=1`。

这说明 AMFI gate 是 driverkitd 阶段的阻塞点；跳过它后，系统进入
SystemOS 读取/后续阶段，然后停在一个新的 UFS 或上层等待点。由于当前
`cpus=1`，heartbeat 线程无法在卡住的 CPU 上运行，stall watchdog 也就
没有机会打印。

H96a8：只把 H96a4 的启动参数 `cpus=1` 改成 `cpus=2`，用于让
`NATIVE_UFS_ALIVE`/`NATIVE_UFS_STALL` 有机会运行并给出停点快照。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a8-payload.img` | 79,691,776 | `5c9a40056dcd10b477a52c7236c610fcd8fa5d6d849e765d9f0af63baa5ace12` |
| `boot-H96a8-cpus2.img` | 81,147,904 | `53f8cfcf8a9c71fa051c9a85e6d53d2d91bb1b36de7f426494e153b5ffa36d6c` |

### 6.17 H96a8 结果：cpus=2 消除早期停点，但仍停在 driverkitd 之后

H96a8（H96a4 + `cpus=2`）屏幕显示：

```text
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... winBytes=3222082432 winFlight=1
NATIVE_TC_QUERY: pid=35 comm=xpcproxy ...
NATIVE_TC_QUERY: pid=1 comm=launchd ...
NATIVE_TC_QUERY: pid=80 comm=xpcproxy ...
```

随后日志不再变化：

- 没有 `NATIVE_UFS_STALL` panic；
- 没有继续出现新的 `KextLog` 服务；
- SystemOS 读取到约 3.22 GB 后停止；
- heartbeat 是否打印仍需确认，但至少没有硬 UFS stall 证据。

因此 H96a4 的早期停点与 `cpus=1` 调度有关；`cpus=2` 后系统越过了
AMFI gate 和早期 UFS 停点，停在 **driverkitd/FileSet KC 之后**。新的
阻塞点不在 AMFI entitlement，也不一定是 UFS 传输本身，需要看
`launchd` 最后尝试启动/等待哪个服务。

H96a9：在 H96a8 基础上加入 `NATIVE_EXEC` trace（`set_proc_name()` 里
打印 pid/comm），并保留 AMFI gate 跳过；预期最后屏幕显示最后执行的
进程，从而定位 driverkitd 之后停住的 userland 任务。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a9-kernel-gatebypass.macho` | 52,088,832 | `84312b766832e5f63ad786a4fa5576a8940b2abbffb0f2c9c60e8275c387412c` |
| `H96a9-payload.img` | 79,691,776 | `0e714fa8a08ec1c07591cf9a6f7aac5312e91ae7b9f0af5483c9a58bc0459105` |
| `boot-H96a9-exectrace.img` | 81,147,904 | `697536ff2e60feccf0d37238593579196570ce0f93b58fc280d41d1d8c1bfa8a` |

### 6.18 H96a9 结果：driverkitd 之后最后 exec 是 MobileGestaltHelper

H96a9（H96a8 + `NATIVE_EXEC` trace）最后可见：

```text
NATIVE_EXEC: pid=85 comm=containermanagerd
NATIVE_EXEC: pid=87 comm=MobileGestaltHel[per]
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... winBytes=3213053696 winFlight=1
```

之后没有新的 `NATIVE_EXEC`、`KextLog` 或错误行：

- driverkitd 已 active；
- `containermanagerd`、`MobileGestaltHelper` 已启动；
- 最后仍是 SystemOS 读取约 3.21 GB，`winFlight=1`；
- 没有 `NATIVE_UFS_STALL` panic。

所以当前停点在 driverkitd/FileSet KC 之后，可能是 driverkitd 等待某个
driver/kext 处理，也可能是 UFS/上层等待。需要把 UFS 超时从“heartbeat
线程”移到请求本身，才能在 `cpus=1/2` 下都给出证据。

### 6.19 H96a10：UFS 请求内超时 panic

H96a10 在 `NativeUfsProbe.cpp` 的 `ufsSubmit` 超时分支直接把
`NATIVE_UFS_GPT: OCS timeout` 改成 panic：

```text
NATIVE_UFS_TIMEOUT: lba=%llx bytes=%u type=%08x ocs=%x loops=%u
  db=%x is=%x hcs=%x hce=%x ucd0=%x cdb=...
```

这不再依赖 heartbeat 线程；如果停点确实在 UFS 请求等待，5.2 秒内
一定会 panic 并给出 LBA/长度/UTRD/寄存器。若仍无 panic，则停点在上层
（driverkitd/FileSet KC/launchd），不是 UFS 传输。

H96a10 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a10-kernel-gatebypass.macho` | 52,088,832 | `fe684b31987da19e6ab65c79cd0453bfeb231ec5e4a9ad841c71d8880b703481` |
| `H96a10-payload.img` | 79,691,776 | `93d052bf7b55047d083dafdb2a168931d94f9b20f8fa0cbdbe580a65e3532413` |
| `boot-H96a10-ufstimeout.img` | 81,147,904 | `bd3069c27fa1c849b4cb2127d68a742579a0d21419c98cb09d9ea650f578e616` |

### 6.20 H96a10 结果：多服务已启动，停在 xpcproxy，未见 UFS 超时

H96a10（UFS 请求内超时 panic + cpus=2 + gate bypass）屏幕显示大量
`NATIVE_EXEC`：

```text
logd, UserEventAgent, mediaserverd, configd, removed, keybagd, amfid,
DumpPanic, mobileassetd, thermalmonitord, tzc, containermanager,
driverkitd, sleepd, AppleCredentiald, rapportd, storageproxyd,
fseventsd, IOMFB_FDR_Loader, distnoted, xpcproxy, ptpd, log_helper ...
```

最后停在若干 `xpcproxy` 进程，最后可见 `NATIVE_H66_FCNTL` /
`NATIVE_CACHE_SIG`（xpcproxy 的 dyld cache 注册）；没有
`NATIVE_UFS_TIMEOUT`/`NATIVE_UFS_STALL`，说明 UFS 请求没有超时，停点在
上层 xpcproxy/服务启动。

这比之前大幅前进：configd/keybagd/amfid/mobileassetd/storageproxyd/
fseventsd/IOMFB_FDR_Loader 都已启动，但还没有 `backboardd`/SpringBoard。

H96a11：在 H96a10 基础上把 `NATIVE_EXEC` 扩展为打印 `argv0`/`argv1`，
用于确认最后卡住的 `xpcproxy` 实际要启动的目标服务。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a11-kernel-gatebypass.macho` | 52,088,832 | `b12e048003d688c3dec3128812a3a09e1e7024b4397234fbfa332e598d8a3288` |
| `H96a11-payload.img` | 79,691,776 | `20751860174d85f75c59f36d71006a89a764666f810b5de395e17b98903dbb5b` |
| `boot-H96a11-exargv.img` | 81,147,904 | `d225ad4bcea345d4310acb37f227fbadbdda524d51fdef3b3ef81310cf6ceeb4` |

### 6.21 H96a11 结果：最后卡在 xpcproxy 启动 com.apple.nsurlsessiond

H96a11 屏幕最后：

```text
NATIVE_EXEC: pid=82 comm=routined argv0=/usr/libexec/routined argv1=LAUNCHED_BY_LAUNCHD
NATIVE_EXEC: pid=89 comm=accountsd argv0=/System/Library/Frameworks/Accounts.framework/accountsd argv1=
NATIVE_UFS_PROGRESS: ... winBytes=3220086528
NATIVE_EXEC: pid=90 comm=xpcproxy argv0=xpcproxy argv1=com.apple.nsurlsessiond
NATIVE_UFS_PROGRESS: ... winBytes=3224810496 ...
```

之后没有新的 `NATIVE_EXEC`、`KextLog` 或错误行；没有 UFS timeout。
因此当前停点是 launchd/xpcproxy 启动 **`com.apple.nsurlsessiond`**
这一步，目标服务还没有真正 exec 出来。

H96a12：复用 H96a11 kernel，只在 payload 参数追加：

```text
sheng-disable-jobs=com.apple.nsurlsessiond
```

用于跳过这个已知卡住的服务，观察系统是否能继续到后面的服务
（尤其是 backboardd/SpringBoard）。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a12-payload.img` | 79,691,776 | `bd9a85b3377e2dd7fa0e5fa423bcb4026c82a23ebe79809d76defa7207b48e30` |
| `boot-H96a12-no-nsurl.img` | 81,147,904 | `90812e490461cb0040619b419779e1f8bbbafde9864de4050c375ff641621204` |

### 6.22 H96a12 结果：跳过 nsurlsessiond 后到达 backboardd，但停在第二次 driverkitd

H96a12（`sheng-disable-jobs=com.apple.nsurlsessiond`）屏幕显示：

```text
NATIVE_EXEC: pid=55 comm=backboardd argv0=/usr/libexec/backboardd
NATIVE_EXEC: pid=58 comm=sharingd
NATIVE_EXEC: pid=60 comm=imagent
NATIVE_EXEC: pid=67 comm=lockdownd
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
```

随后不再变化：

- 已经启动 `backboardd`（显示后端）和 `sharingd`/`imagent`/`lockdownd`；
- 但还没有 `SpringBoard`/`WindowServer`；
- 停在第二次 `driverkitd is active` 之后，没有 UFS timeout。

这说明跳过 `nsurlsessiond` 有效，系统继续到 backboardd；新的停点是
**第二次 driverkitd/FileSet KC 阶段**。需要判断它是 launchd 的
`com.apple.driverkitd` job 在等待，还是内核 kext/DriverKit 驱动加载。

H96a13：复用 H96a11 kernel，只把 `sheng-disable-jobs` 扩展为：

```text
com.apple.nsurlsessiond,com.apple.driverkitd
```

如果跳过后能继续到 SpringBoard，说明第二次停点是 driverkitd job；
如果仍在同样的 `KextLog` 处停住，则是内核 kext/驱动加载，需要转去
driverkitd/AMFI 的第二目标。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a13-payload.img` | 79,691,776 | `34573fe97814299d5b46be40692ba96be590f05c5a51a91c3d52e2201c07cdf6` |
| `boot-H96a13-no-driverkitd.img` | 81,147,904 | `3c5fe7076238fb8794deaf752bedcb28e5ac3d5095fc49be64757a4762f9c697` |

### 6.23 H96a13 结果：跳过 driverkitd job 反而停在 nehelper

H96a13（同时跳过 `nsurlsessiond` 和 `driverkitd` job）屏幕最后：

```text
NATIVE_EXEC: routined
NATIVE_EXEC: xpcproxy argv1=com.apple.accountsd
NATIVE_EXEC: accountsd
NATIVE_EXEC: xpcproxy argv1=com.apple.nehelper
NATIVE_EXEC: nehelper
```

之后无变化；没有到 backboardd。说明简单禁用 driverkitd job 不是正确
方向，且会改变启动顺序，暴露另一个网络 helper（nehelper）等待。
H96a12 的路径（只禁用 nsurlsessiond，保留 driverkitd）仍是目前最远。

### 6.24 H96a14：只记录 driverkitd 的 AMFI 检查目标

H96a14 复用 H96a12 的启动参数（只跳过 nsurlsessiond），内核层只对
`comm=driverkitd` 且 `call=0x5f` 的 AMFI 调用打印：

```text
NATIVE_AMFI_SYSCALL: pid=... comm=driverkitd target=AMFI call=95
  arg=... csflags=... blob=... platform=... cdhash=...
```

不再 panic，也不再打印其他 AMFI/trust-cache 调用。这样在系统到达第二次
`driverkitd is active` 停住时，最后屏幕会显示第二次检查的目标 cdhash。

H96a14 产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a14-kernel-gatebypass.macho` | 52,088,832 | `ede3f2b803113ec9921a3faae052bced060ee32f50e7656436889e2d6355ef3a` |
| `H96a14-payload.img` | 79,691,776 | `aa06e6c0515f5431cbea4c41c6db26f71230ce1cc68a0e39be07f04b93cd58c8` |
| `boot-H96a14-driverkitdtrace.img` | 81,147,904 | `06bc78c6f14e5a1819c668fb551040c39643c109d083d55521451e14f1adad62` |

### 6.25 H96a14 结果：本次停在 routined，未看到第二次 driverkitd trace

H96a14 本次运行最后：

```text
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... winBytes=3215934464 ...
NATIVE_EXEC: pid=55 comm=alsd ...
NATIVE_EXEC: xpcproxy argv1=com.apple.accountsd
NATIVE_EXEC: accountsd
NATIVE_EXEC: pid=32 comm=routined
```

之后 5 分钟无变化；没有可见的 `NATIVE_AMFI_SYSCALL ... comm=driverkitd`
（第二次 driverkitd 目标未到达或未打印）。与 H96a12 到达 backboardd
相比，本次运行停在更早的 `routined`，说明启动顺序/等待点存在
run-to-run 差异；`routined` 是当前新的同步等待候选。

H96a15：复用 H96a14 kernel，payload 同时跳过：

```text
com.apple.nsurlsessiond,com.apple.routined,com.apple.nehelper
```

用于排除网络/位置服务的同步等待，观察能否稳定到 backboardd/SpringBoard。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a15-payload.img` | 79,691,776 | `4fed1175ec016d610d3dc8d8bf9b37a581bd53a7140cb645ad83cc2a1ec1acb9` |
| `boot-H96a15-skipjobs.img` | 81,147,904 | `0b55644d33e4fa848e6c458e0450bd2854e754986941c889198f063006ac4aec` |

### 6.26 H96a15 结果：越过第二次 driverkitd，停在 chronod

H96a15（跳过 nsurlsessiond/routined/nehelper）屏幕显示：

```text
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... winBytes=3266626560 ...
NATIVE_EXEC: pid=90 comm=xpcproxy argv1=com.apple.chronod
NATIVE_EXEC: pid=90 comm=chronod argv0=/System/Library/PrivateFrameworks/ChronoCore.framework/Support/chronod
NATIVE_UFS_PROGRESS: ... winBytes=3272483840 ...
```

随后 3 分钟无变化：

- 第二次 driverkitd 阶段已越过；
- `chronod` 已启动；
- 没有 UFS timeout；
- 尚未出现 SpringBoard/WindowServer。

所以跳过 routined/nehelper 有效，当前新的停在 `chronod` 或其依赖。
H96a16 在 skip 列表中再加入 `com.apple.chronod`，观察下一服务。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a16-payload.img` | 79,691,776 | `646bdae098cdea2b18f01121c58abc9caa3ba6c073cae9cad86b10f771e39d7c` |
| `boot-H96a16-skipchronod.img` | 81,147,904 | `49fc80be16dd61a60a0cddbf745359a7f1039360eedf295b77326052c0e17126` |

### 6.27 H96a16 结果：停在 log_helper，启动点仍在漂移

H96a16 最后可见：

```text
NATIVE_EXEC: IOMFB_FDR_Loader
NATIVE_EXEC: distnoted
NATIVE_EXEC: xpcproxy argv1=com.apple.log_helper
NATIVE_EXEC: log_helper
NATIVE_UFS_PROGRESS: ... winBytes=3138565120 ...
```

之后无变化；没有 UFS timeout。与 H96a14/H96a15 的 routined/chronod
相比，最后停点继续漂移，说明不是单一 daemon，而是某类同步 XPC/
launchd 等待。

H96a17：扩大 skip 列表到：

```text
nsurlsessiond,routined,nehelper,chronod,log_helper,accountsd,alsd,pfd
```

用于一次性排除已观察到的网络/位置/日志 daemon，观察是否能稳定到
backboardd/SpringBoard。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a17-payload.img` | 79,691,776 | `9fdc58c01dd4cfa53e76684e300f2ab0f88e096427c6b1fc7d5301181366f589` |
| `boot-H96a17-broadskip.img` | 81,147,904 | `6906c32e2bab290b08a4e0b767904515f4251fed1260f9a5e7bffea6c2ffa997` |

### 6.28 H96a17 panic：sheng-disable-jobs 不允许下划线

H96a17 启动时 panic：

```text
panic(cpu 0 ...): sheng watchdog launchd policy failed: 22 @ kern_exec.c:8294
```

根因不是用户态服务，而是诊断策略的参数校验：`sheng_boot_watchdog_policy`
的 `jobs` 字符白名单只允许字母、数字、`.`、`-`、`,`，**不允许下划线**。
H96a17 的 skip 列表包含 `com.apple.log_helper`，其中 `_` 触发
`EINVAL(22)`，`kern_exec.c` 在 launchd exec 处 panic。

这解释了为什么 H96a16（没有 `log_helper`）可以启动到 log_helper，而
H96a17 直接 panic。也说明当前 `sheng-disable-jobs` 不能跳过带 `_` 的
job；后续如果要跳过这类 job，需要把白名单加上 `_`（独立小修复）。

H96a18：移除带下划线的 `log_helper`，skip 列表改为：

```text
nsurlsessiond,routined,nehelper,chronod,accountsd,alsd,pfd
```

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a18-payload.img` | 79,691,776 | `c58640e146c4f7d2a97ceaa511bc88e2382256a44f3bd03a0469fe6b60bb74c7` |
| `boot-H96a18-skipno-underscore.img` | 81,147,904 | `301d8edd7f2c13b144f8c980fa4364ab1ed89141bac2e52325ea65826ad805b6` |

### 6.29 H96a18 结果：进入 cryptexd/eligibilityd，仍无 SpringBoard

H96a18 最后可见：

```text
NATIVE_EXEC: pid=87 comm=xpcproxy argv1=com.apple.eligibilityd
NATIVE_EXEC: pid=88 comm=xpcproxy argv1=com.apple.security.cryptexd
NATIVE_EXEC: pid=80 comm=cryptexd argv0=/usr/libexec/cryptexd
NATIVE_EXEC: pid=87 comm=eligibilityd argv0=/usr/libexec/eligibilityd
process fseventsd[76] crossed thread count high watermark (32), EXC_RESOURCE suppressed...
NATIVE_UFS_PROGRESS: ... winBytes=3230794752 ...
```

之后 5 分钟无变化；没有 UFS timeout，没有 SpringBoard/WindowServer。
此时系统已经进入 **cryptexd/SystemOS** 路径；`cryptexd` 是原始
Cryptex1/AuthAPFS 链路的一部分，可能再次撞上 H91/H95 记录的
owner IM4M/AuthAPFS 依赖，而不是一个可随意跳过的普通 daemon。

H96a19：在 skip 列表加入 `com.apple.eligibilityd`，观察 cryptexd
之后的下一跳；如果仍停在 cryptexd/SystemOS 链路，就不再靠 skip
推进，转回 owner manifest/AuthAPFS 或显示依赖。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a19-payload.img` | 79,691,776 | `995d247ce5dfe436bb25211cdf102f6b7256530072af8b042c8be9577694021a` |
| `boot-H96a19-skipeligibility.img` | 81,147,904 | `0bd34abf97c50979c0f24e58c1f1c1b2c816b74429b6e12d4e3940737ad2b7e9` |

### 6.30 H96a19 结果：driverkitd 四次 AMFI 检查后进入 FileSet KC，目标 cdhash 不在 H91 侧车

H96a19 最后可见四次 driverkitd AMFI 检查（trace 只打印 cdhash 的前
16 字节，完整 20 字节需要后续补打）：

```text
NATIVE_AMFI_SYSCALL: pid=62 comm=driverkitd target=AMFI call=95 ...
  cdhash=b2532db47f393f06a573bf3c2862f2d?
NATIVE_AMFI_SYSCALL: ... cdhash=4fcc8c8a2177269fc845778576bbf6a3
NATIVE_AMFI_SYSCALL: ... cdhash=ad7fba3b1986d98b18573584dce43d84
NATIVE_AMFI_SYSCALL: ... cdhash=86dab7a4fed9f4c976b75127beab4fcb
```

随后：

```text
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_EXEC: xpcproxy argv1=com.apple.security.cryptexd
NATIVE_EXEC: cryptexd
NATIVE_EXEC: xpcproxy argv1=com.apple.eligibilityd
NATIVE_EXEC: eligibilityd
```

之后 5 分钟无变化。

静态比对：

- 这四个 16 字节前缀都不在 H91 payload 的
  `kernel.macho.trustcache`（静态+System 侧车）中；
- 也不在 OS DMG 的 14 个 `/System/Library/DriverExtensions/*.dext`
  中；
- 也不在 OS/SystemOS 的 `.kext` 可执行文件中找到匹配。

注意：trace 目前只打印 16 字节，且 AMFI 32 字节参数的 cdhash 布局
可能需要从 offset 4 开始解析；这些前缀不能当作完整 20 字节 cdhash
定案。需要一次打印完整 20 字节并重新比对。

无论前缀是否精确，H96a19 已经把问题推回 **SystemOS/Cryptex1/
FileSet KC 的真实 trust cache/owner manifest** 方向：driverkitd 检查
的多个 driver/kext 不在当前交付的静态/System 侧车中，随后 cryptexd
启动并停住。继续增加 `sheng-disable-jobs` 不能解决这个信任链问题。

建议停止 skip 迭代，下一步二选一：

1. 打印完整 20 字节 cdhash，并确认它们属于哪个 SystemOS/DriverKit
   trust cache；若来自 `Cryptex1,SystemTrustCache`，需要把该 cache
   正确加载到内核侧车/AMFI runtime；
2. 作为一次性 bring-up 诊断，配合 AuthAPFS/cryptexd 的受控 patch
   验证 UI 路径，但必须明确不是最终安全方案。

> **H96a21 更正（见 6.34）**：H96a21 在 AMFI 内部读到四次检查的
> `mask=0x1`，按 AMFI 位语义是 **type 1（静态）miss、type 2
> （loadable）hit**，即四个目标都在运行时 loadable TrustCache 中。
> “不在 H91 静态+System 侧车”是 DriverKit driver 的正常结果，不能
> 作为 cache 缺失的证据。当前 AMFI/这些 driver 的 trust-cache 检查
> 已通过；剩余停点要从 FileSet KC 之后（cryptexd/SystemOS/launchd
> 等待）继续定位。

### 6.31 H96a20：完整 32 字节 AMFI 参数与返回结果

H96a20 只改 trace，不 panic、不改 skip：

- `NATIVE_AMFI_SYSCALL` 对 driverkitd 的 `call=0x5f` 打印完整 32 字节
  输入参数，格式为 8 个 `%08x` 词：
  ```text
  ... in=wwwwwwwwwwwwwwww copied=1
  ```
  前 5 个词（20 字节）是待检查 cdhash，后 3 个词是元数据/结果位图。
- `NATIVE_AMFI_RESULT` 在 `__mac_syscall` 返回后再次 copyin 同一 32 字节
  并打印：
  ```text
  ... ret=<error> out=wwwwwwwwwwwwwwww copied=1
  ```
  这样可以确认 AMFI 实际返回的查询位图，而不是只看输入。

H96a20 使用 H96a19 的 skip 列表（能到达四次 driverkitd 检查）和
`cpus=2`，继续带 AMFI gate 跳过。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a20-kernel-gatebypass.macho` | 52,088,832 | `e7538cb9e022fcc5bad5241fb9e7610cd352dec0214c6fe7cdfc07afa398d90a` |
| `H96a20-payload.img` | 79,691,776 | `bef11b854700493c89dd51792700d00f0b46ce9c802fe044c415baae880c8792` |
| `boot-H96a20-fullcdhash.img` | 81,147,904 | `9a409302774277cf97c0209694104c7f08c2d16ed1df3193cb617f93ced59b88` |

### 6.32 H96a20 结果：full in/out words 可见，但用户缓冲区没有干净的 mask

H96a20 屏幕出现多组：

```text
NATIVE_AMFI_SYSCALL: pid=62 comm=driverkitd target=AMFI call=95 ...
  in=<8 words> copied=1
NATIVE_AMFI_RESULT: pid=62 comm=driverkitd ... ret=0
  out=<8 words> copied=1
```

观察：

- 所有检查 `ret=0`（MAC syscall 成功）；
- `out` 的前 5 个词（20 字节）与 `in` 相同，说明输入 cdhash 未被修改；
- 尾部词出现 `aaaa0000` / `00000000` 一类值，不能直接当作查询位图；
- 之前 H96a6 在 AMFI 内部 `[sp+0x58]` 读到 `mask=0x1`，但用户 32 字节
  返回缓冲区没有呈现同样干净的 mask。

因此 H96a20 证明了 driverkitd 确实在 FileSet KC 前连续检查多个
cdhash，但**用户缓冲区不是可靠的 mask 来源**；要拿到每次检查的真实
查询位图，必须在 AMFI 成功路径内部（`[sp+0x58]`）打点/panic，而不是
在 `__mac_syscall` 返回后 copyin 用户缓冲区。

结论不变：四次/多次 driverkitd 检查后进入 FileSet KC，随后
cryptexd/eligibilityd 停住；当前剩余阻塞是 SystemOS/Cryptex1 信任链，
不是 AMFI entitlement 循环。

下一步如果继续，只建议做一个很小的 AMFI 内部诊断：在成功路径对第 N 次
driverkitd 检查 panic，打印完整 20 字节 cdhash + `[sp+0x58]` mask；
不再扩大 boot-arg/skip 列表。

### 6.33 H96a21：AMFI 内部 panic，打印完整 cdhash 与真实 mask

H96a21 在 H96a20 源码基础上加入一个仅由二进制补丁调用的诊断函数：

```c
__attribute__((noinline, used))
void native_amfi_tc_diag(proc_t p, const uint8_t *cdhash, uint64_t mask);
```

- 函数只在 `p->p_comm == "driverkitd"` 时计数/打印；
- 从 AMFI 成功路径的 `sp+0x40` 读取完整 20 字节 cdhash；
- 从 `sp+0x58` 读取两次查询的真实结果位图；
- 前三次 `printf`，第四次 `panic`，使屏幕停留：

```text
H96A21_TC: n=1 pid=... comm=driverkitd mask=0x... cdhash=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
...
H96A21_TC: n=4 ...
panic: H96a21: fourth driverkitd trust-cache check
```

二进制补丁（相对 H96a21 原始内核）：

- gate：`0x1ac73b8` 的 `tbz w0,#0,reject` 改为 `nop`；
- 成功路径：`0x1ac7424` 的 `add x0,sp,#0x40` 改为
  `b 0x197b400`；
- code cave `0x197b400`：
  ```asm
  mov x0, x21              ; proc
  add x1, sp, #0x40        ; cdhash
  ldr x2, [sp, #0x58]      ; mask
  bl  native_amfi_tc_diag
  add x0, sp, #0x40
  b   0x1ac7428
  ```

注意：这是**诊断镜像**，不是最终修复；panic 只为固定屏幕取证。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a21-kernel.macho`（未打补丁） | 52,088,832 | `6c60e6e889eb5d1af9f9cf1527d4ecbe171926e16568f62ede117b5d08c2d69f` |
| `H96a21-kernel-gatebypass-hook.macho` | 52,088,832 | `b9cd4c9b44a0d5c977b50d1de8f861483797d4a362062e025d3fd8bce47b95d3` |
| `H96a21-payload.img` | 79,691,776 | `bc3ea90e8eb733e1658a4f5c6e170036b264550a65ca12e8b43a605ef70819f9` |
| `boot-H96a21-tcpanic.img` | 81,147,904 | `f7e9a2f051f6cc446d2a775d799b489bd2297f92ef043b516f40d7b9ee88eb67` |

H96a21 已通过 `fastboot boot` 启动，等待第四次 driverkitd 检查触发 panic 后拍照。

### 6.34 H96a21 结果：四次检查全部 loadable hit，AMFI 不是当前阻塞

H96a21 在第四次 driverkitd 检查处 panic，屏幕给出：

```text
H96A21_TC: n=1 pid=62 comm=driverkitd mask=0x1
  cdhash=1fc191a7fbb1e532b54ca15befb83d7efe9ab3e1
H96A21_TC: n=2 pid=62 comm=driverkitd mask=0x1
  cdhash=0d6972a904236c9c4bea8297c2d8bdacbeb1167a
H96A21_TC: n=3 pid=62 comm=driverkitd mask=0x1
  cdhash=d4c8a0514d5952c89dc24039d9efd4a26e0c87ef
H96A21_TC: n=4 pid=62 comm=driverkitd mask=0x1
  cdhash=d599af53ba5c1d66a0a0c9135c5756f9d3713284

panic(cpu 0 caller ...): H96a21: fourth driverkitd trust-cache check
```

判读：

- `mask=0x1`：bit0 表示 type 1（静态）查询 miss，bit1 未置位表示
  type 2（loadable）查询 hit；这是 DriverKit driver 的**正常**结果。
- 四次检查全部 `mask=0x1`，说明这四个目标都在运行时 loadable
  TrustCache 中，AMFI 检查本身没有失败。
- H96a19 只打印前 16 字节、且未在 H91 静态+System 侧车中找到匹配，
  是 trace 截断和侧车范围造成的误判；不能用它证明缺少 SystemOS
  trust cache。
- 每次启动 driverkitd 检查的目标集合可能不同（H96a19/H96a20/H96a21
  的 cdhash 不完全相同），但本次 H96a21 的四个目标均已 loadable hit。
- H96a21 的 panic 发生在检查阶段，因此看不到之后的日志；结合
  H96a19/H96a20，四次检查后仍进入 `FileSet KC`。但 H96a19 的屏幕实际
  停在 `KextLog: driverkitd is active`，没有 cryptexd/eligibilityd；
  这是因为 H96a19/H96a20/H96a21 的 skip 列表包含
  `com.apple.eligibilityd`。真正到达 cryptexd/eligibilityd 的是
  **H96a18**（skip 列表不含 eligibilityd/cryptexd）。**当前阻塞不在
  AMFI entitlement，也不在这四个 driver 的 trust-cache 命中；但也不能
  用 H96a19 的 skip 列表继续推进。**

下一步应把变量放在 FileSet KC 之后的 **cryptexd/SystemOS/launchd
等待**，而不是继续补 AMFI/静态 sidecar。可选的最小诊断：

1. H96a22：只把 `com.apple.security.cryptexd` job 加入
   `sheng-disable-jobs`（一次性诊断，不是最终修复），观察是否能越过
   cryptexd 到 backboardd/SpringBoard；
2. 若不跳过 cryptexd，则需要在 launchd/XPC 或 cryptexd 的
   SystemOS/AuthAPFS 路径上加日志，确认它等待的对象。

### 6.35 H96a22：只跳过 cryptexd job 的一次性诊断

H96a21 证明四次 driverkitd 检查全部 `mask=0x1`（loadable hit），因此
下一步不再改 AMFI。H96a22 用回 H96a20 的无 panic 内核（同一 gate
bypass），只改变 launchd skip 列表：

```text
sheng-disable-jobs=com.apple.nsurlsessiond,com.apple.routined,
com.apple.nehelper,com.apple.chronod,com.apple.accountsd,
com.apple.alsd,com.apple.pfd,com.apple.eligibilityd,
com.apple.security.cryptexd
```

目的：区分“cryptexd 自身同步等待/启动”与更深的 SystemOS/AuthAPFS
依赖。跳过 cryptexd 是**一次性诊断**，不是最终修复；如果系统仍不到
backboardd/SpringBoard，则说明 cryptexd 不是唯一阻塞，需转向
SystemOS/AuthAPFS 或显示依赖。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a22-payload.img` | 79,691,776 | `7e2c37c9c50203e7fa92a20b95a65c1bab4fbea2aa2415c2a4ee239323317801` |
| `boot-H96a22-skipcryptexd.img` | 81,147,904 | `1b76aac07fc3e68830a91069e18d98008b177c745345bab289e51acc16f728f9` |

内核沿用 `H96a20-kernel-gatebypass.macho`：
`e7538cb9e022fcc5bad5241fb9e7610cd352dec0214c6fe7cdfc07afa398d90a`。

### 6.36 H96a22 结果：跳过 cryptexd 反而停在 driverkitd active

H96a22 在 H96a19 skip 列表基础上再加
`com.apple.security.cryptexd`，使用 H96a20 无 panic 内核。屏幕最后：

```text
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_CACHE_SIG: ...
NATIVE_I66_FONT: ...
NATIVE_UFS_WINDOW: SystemOS req=52224 block=13fcf0 count=0
NATIVE_UFS_WINDOW: SystemOS req=52224 done=4096 ok=1 ticks=95 read=0 write=02
```

之后 3 分钟无变化；没有 cryptexd/eligibilityd 的 `NATIVE_EXEC`，也没有
`backboardd`/SpringBoard，没有 UFS stall/panic。

判读：

- 跳过 cryptexd 没有让系统越过它，反而让 launchd 更早停在
  `driverkitd is active`；
- 同样，H96a19 跳过 `com.apple.eligibilityd` 后也停在
  `driverkitd is active`，没有 cryptexd；
- **H96a18（不跳过 eligibilityd/cryptexd）才是目前最远路径**：它确实
  启动到 `cryptexd`/`eligibilityd`，然后停住；
- 因此 cryptexd/eligibilityd 不是可随意跳过的 daemon，skip 迭代到此
  为止。剩余问题回到 H92/H93 已记录的 SystemOS Cryptex1/AuthAPFS/
  owner manifest 链路。
- **实验设计说明**：H96a22 的基线 H96a19 已经跳过 eligibilityd，因此
  它相对 H96a19 只加了 cryptexd，但基线本身已经回退到
  `driverkitd is active`；H96a22 不能单独证明“只跳 cryptexd”的效果。
  为单变量隔离 cryptexd，另建 H96a23：H96a18 的 skip 列表（保留
  eligibilityd）+ 只加 `com.apple.security.cryptexd`。

下一步只有三类选择：

1. 提供真实 `Cryptex1,SystemVolume` owner manifest/IM4M（当前
   IPSW/仓库不可得，需要 Apple TSS/personalization）；
2. 做一次性的 **kernel-side** AuthAPFS/Image4 诊断绕过（不改 OS 镜像，
   但属于安全策略绕过，必须明确不是最终修复）；
3. 停在 H96a18/H91，保留当前诊断结论。

当前安全边界不允许重新 flash 修改后的 OS/userdata，因此 H93 那种
直接 patch `cryptexd` 二进制的方案不再采用。

### 6.37 H96a23：单变量隔离 cryptexd（H96a18 基线 + 只跳 cryptexd）

H96a22 的基线 H96a19 已跳过 eligibilityd，不能隔离“只跳 cryptexd”。
H96a23 回到 H96a18 的 skip 列表：

```text
nsurlsessiond,routined,nehelper,chronod,accountsd,alsd,pfd
```

只追加：

```text
com.apple.security.cryptexd
```

保留 eligibilityd，不跳过它；内核继续使用 H96a20 的无 panic gate
bypass 版本。这样如果系统停在 `driverkitd is active`，才能把原因归到
cryptexd；如果能继续到 backboardd/SpringBoard，说明 cryptexd 是当前
关键阻塞。

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `H96a23-payload.img` | 79,691,776 | `23b29bdaa78e9069a5a78c6d446472b8a68abe8f56796bcceefd79258f0af66b` |
| `boot-H96a23-skipcryptexd-only.img` | 81,147,904 | `4d23038ecc56823c391b04d31f913d7afb566cf34bcba2cc21df5ebbd451ce22` |

该实验仍是一次性诊断，不是最终修复；如果 cryptexd 不能跳过，则回到
H96a18 的 cryptexd/eligibilityd 停点，转向 owner manifest/AuthAPFS。

### 6.38 H96a23 结果：只跳 cryptexd 仍停在 driverkitd active

H96a23 保留 H96a18 的 skip 列表（**不跳过 eligibilityd**），只追加
`com.apple.security.cryptexd`。屏幕显示多组 driverkitd AMFI 检查
（`ret=0`），随后：

```text
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... winBytes=315523184 ...
```

之后 2 分钟无变化；没有 cryptexd/eligibilityd 的 `NATIVE_EXEC`，没有
backboardd/SpringBoard。

结论：

- 只跳过 cryptexd（保留 eligibilityd）仍然让 launchd 停在
  `driverkitd is active`；cryptexd 不是可跳过的普通 job，而是后续
  launchd 阶段需要的服务；
- H96a22（同时跳过 eligibilityd+cryptexd）和 H96a23（只跳 cryptexd）
  都没有带来进展；H96a18（不跳二者）仍是唯一到达
  cryptexd/eligibilityd 的路径；
- 因此 skip 迭代结束，继续加 skip 只会更早停住。

当前停点回到 H96a18 的 cryptexd/eligibilityd。结合 H92/H93，最可能的
根因仍是 SystemOS Cryptex1/AuthAPFS/owner manifest；下一步只能：
真实 owner manifest/IM4M（不可得）、一次性 kernel-side AuthAPFS/
Image4 诊断绕过（非最终修复），或停在 H96a18/H91。

### 6.5 回滚

- 不覆盖 H91 boot/payload/kernel。
- H96a 使用独立文件名，例如 `boot-H96a-amfitrace.img`。
- 回退：重新 `fastboot boot boot-H91-stallpanic.img`。
- 补丁默认关闭；即使留在树里，不带两个 trace boot arg 时行为与 H91
  相同（仅多出未执行的静态函数）。

## 7. UFS 独立诊断设计（H96u，不与 H96a 同镜像）

H91 没有 UFS 硬 stall，因此 UFS 不是当前第一优先；但 P2 要求可证伪的
请求级诊断，且不能把 H89b/H90d 的停住与 AMFI 混为一谈。

### 7.1 先解释 `HCS=0x10`

按 UFSHCI 的 HCS（Host Controller Status，0x30）定义：

| bit | 名称 |
| ---: | --- |
| 0 | `DEVICE_PRESENT` |
| 1 | `UTP_TRANSFER_REQ_LIST_READY` |
| 2 | `UTP_TASK_REQ_LIST_READY` |
| 3 | `UIC_COMMAND_READY` |
| 4 | `HOST_ERROR_INDICATOR` |
| 5 | `DEVICE_ERROR_INDICATOR` |
| 8..10 | `UIC_POWER_MODE_CHANGE_REQ_STATUS` |

因此 H90d 的 `HCS=0x10` 表示 **host error indicator 置位**，同时
`DEVICE_PRESENT`、`UTP_TRANSFER_REQ_LIST_READY` 都未置位；
`(HCS & 3) == 3` 为假不是“驱动假设错了”，而是控制器没有进入可运行
状态。H90e 放宽检查后仍无法建立队列，与这个解释一致。

正确方向不是删除 profile 校验或把任意 HCS 当成 ready，而是：

1. 读 `IS`/`IE`/`HCE`/`HCS`/`UIC` 错误位；
2. 确认是初始化顺序、时钟/电源、复位、还是此前 H89b/H90 的控制器
   残留状态导致 host error；
3. 在确认 DMA 停止后，按 UFSHCI 顺序清 error/重新 enable，并验证
   `UTP_TRANSFER_REQ_LIST_READY` 与 `UIC_COMMAND_READY`。

### 7.2 请求生命周期字段

在 `NativeUfsProbe`（当前 Probe 路径，不是 warm-link）中为每个请求记录：

- request ID、LUN、LBA、block count、byte count；
- UTRD slot/tag、UTRD/command descriptor 地址；
- PRDT 条目数、DMA buffer 地址/长度；
- submit 时间戳；
- doorbell 前后 `HCS`/`IS`/`IE`/`UTRLDBR` 快照；
- 中断或轮询是否观察到完成；
- OCS/transfer response/status；
- completion callback 是否执行；
- outstanding 数量变化；
- 超时后一次性限频快照，并进入可恢复 timeout/error 路径。

### 7.3 测试顺序

1. 单请求、同一 LBA 重复读；
2. 连续小块读；
3. 不同长度读；
4. 多 LUN 交替读；
5. 长时间重复读；
6. 最后才测并发/read-ahead。

每步用已知原始窗口 hash 校验读回数据；只统计“读到字节”不算正确性
证明。H96u 必须先独立构建、独立镜像，不要与 H96a 的 AMFI trace 混在
同一个 boot image 里。

## 8. 安全边界与风险

- H96a 只增加默认关闭的观测日志；不改变 AMFI 决策、不改变 TrustCache
  注册、不改变 root auth、不改变 VerifiedRoot digest。
- `IOCurrentTaskHasEntitlement` 是只读查询；不会授予权限。
- 不把 `entitled=0` 的检查删除或改成 `entitled=1`；不把 48 字节占位
  manifest 当成真实 owner manifest；不把 8 字节 digest 当成最终方案。
- 不自动刷写 userdata、GPT、ABL/XBL/modem/persist。
- 若 H96a 证明调用方是修改过的二进制，必须回到原始签名二进制或真实
  owner manifest/trust cache，而不是永久关闭 AMFI。

## 9. 缺失证据

1. H91 的完整启动日志和循环首发 PID/进程名。
2. H91 的精确构建提交、CI run、kernel.json、CFLAGS。
3. H91 静态 TrustCache 的 module 数、cdhash 列表，以及目标进程 cdhash
   是否在其中。
4. `Cryptex1,SystemTrustCache` 是否已加载、加载到哪一层。
5. AMFI 内部 entitlement 查询失败的具体原因（需要 H96a 的
   `csflags`/`blob`/`entitled` 组合）。
6. UFS 请求级日志；当前只能确认 H91 没有硬 stall。

## 10. 下一步唯一优先事项

**H96a：用 `native-trace-amfi-syscall=1` 和 `native-trace-trust-cache=1`
启动 H91 配置的独立诊断镜像，确认 `_check_cdhash_in_trustcache` 的调用方
PID/comm、`entitled`、`csflags`、`blob`、`platform` 和 cdhash，并确认
循环期间是否出现 `NATIVE_TC_QUERY`。**

在拿到这组日志前，不要：

- 继续叠加 amfi/boot-args；
- 修改 TrustCache blob；
- 修改 AMFI/trustcache 二进制；
- 把 UFS 问题与 AMFI 循环合并处理。

## 11. 需要用户执行的设备测试

先构建（用户/CI，不在本次自动执行）：

1. 使用与 H91 相同的构建配置，确认补丁已应用：
   ```sh
   git -C .cache/xnu-work apply --check patches/xnu/trustcache-amfi-trace.patch
   ```
2. 构建 H96a kernel/payload，payload 参数只追加：
   ```text
   native-trace-amfi-syscall=1 native-trace-trust-cache=1
   ```
3. 生成独立 boot image，例如
   `out/cheeseburger/boot/boot-H96a-amfitrace.img`，记录 boot/kernel/payload
   SHA-256。

上机（用户明确授权后）：

```sh
fastboot boot out/cheeseburger/boot/boot-H96a-amfitrace.img
```

只做 `fastboot boot`，不要 `fastboot flash userdata`，不要刷写固件分区。
采集：

- 屏幕/串口完整日志；
- 所有 `NATIVE_AMFI_SYSCALL` 行；
- 所有 `NATIVE_TC_QUERY` 行；
- AMFI `_check_cdhash_in_trustcache` 拒绝行；
- 最后到达的 `KextLog` 阶段。

若设备未授权或构建未完成，停在本文的只读结论，不要自行上机。
