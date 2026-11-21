# H103 Preboot/Cryptex 布局审计（2026-11-01）

 - 说明：H102 文档原建议的 H103 是“快照入口 panic”。本轮先做更直接的 Preboot/Cryptex 布局审计；快照入口实验顺延到后续编号。
- 目的：用本机已有的 21H461 iPad7,1 OS/SystemOS 原始镜像，核对 `/System/Cryptexes`、`/private/preboot` 和 SystemOS 内容，确认 H96a18/`driverkitd` 停点是否只是布局问题。
- 边界：只读分析；没有刷写设备，没有修改 OS/SystemOS/AuthAPFS/Image4 验证。
- 参考：`/tmp/opencode/sagit-ios-port`（小米 6、同 SDM835、已进 SpringBoard）。

## 1. 输入

OS 窗口来自本项目已记录的 userdata：

```text
/mnt/data_2048/project/ios_data/userdata/userdata-root.img
OS offset 0x104400（APFS 对象起点；userdata-root.json 的 0x100000 少了 0x4400 头部）
OS size   6,077,580,800
OS SHA-256 e5634d04a8ac35f024845f583394e0a35deb26a04cb0c00286a8674e25a9a4f2
```

SystemOS：

```text
/mnt/data_2048/tmp/opencode/systemos.img
SHA-256 b4908cde41d23e6bc05e6af51a2c9eeb00cf0f863a6a18b1600c96a3fd70414f
UUID    8846FE78-2910-4297-AF97-D59BB6F8FC16
```

## 2. OS 根卷的实际布局

从 OS 窗口挂载/解析得到：

```text
/System/Cryptexes/OS
  -> ../../private/preboot/Cryptexes/OS

/System/Cryptexes/App
  -> ../../private/preboot/Cryptexes/App

/private/preboot         空目录

/System/Library/Caches  存在
/System/Library/Caches/com.apple.dyld  不存在

/usr/standalone/firmware  存在
/usr/standalone/firmware/Cryptex1  不存在
```

这解释了 H39/H40 的 `ENOENT`：

- `/System/Cryptexes/OS` 不是普通目录，而是指向 `/private/preboot/Cryptexes/OS` 的符号链接；
- `/private/preboot` 没有 Preboot 卷内容，链接目标不存在；
- `/System/Library/Caches/com.apple.dyld` 也没有建立。

## 3. SystemOS 的实际内容

SystemOS 是单卷 sealed APFS，根下只有：

```text
/System
/usr
```

其中有：

```text
/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64
/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64.01 ... .52
/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64.symbols
/System/Library/Frameworks/...             378 项
/System/Library/PrivateFrameworks/...      1681 项
/usr/lib/...                               9 项
```

**SystemOS 根下没有 `OS` 子目录。** 因此不能把 SystemOS 挂到 `/private/preboot/Cryptexes` 后还指望 `/System/Cryptexes/OS` 解析到它；挂载点必须是：

```text
/private/preboot/Cryptexes/OS
```

AppOS 同理，挂载点应是：

```text
/private/preboot/Cryptexes/App
```

## 4. launchd 的硬编码路径

从 OS 的 `sbin/launchd` 和 `System/Library/xpc/launchd.plist` 读到：

```text
mount-phase-1
mount-phase-2
/System/Cryptexes/OS/System/Library
/System/Cryptexes/App/System/Library
/private/preboot/Cryptexes/OS/System/Library
/private/preboot/Cryptexes/App/System/Library
cryptex1.boot.os
cryptex1.boot.app
cryptex1.safari-downlevel0*
```

这证实：

1. launchd 同时使用 `/System/Cryptexes/...` 和 `/private/preboot/Cryptexes/...`。
2. `/private/preboot/Cryptexes/OS` 和 `/private/preboot/Cryptexes/App` 是实际挂载点。
3. `cryptex1.boot.os` / `cryptex1.boot.app` 是 Preboot 元数据中的 cryptex 名称。

## 5. Cryptex 元数据

从 IPSW `iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw` 的 j120ap Erase 身份提取：

| 组件 | 路径 | 大小 | SHA-256 |
| --- | --- | ---: | --- |
| `Cryptex1,SystemOS` | `044-76034-038.dmg` | 3,303,014,400 | `b4908cde...` |
| `Cryptex1,SystemVolume` | `Firmware/044-76034-038.dmg.root_hash` | 229 | `adb214bf...` |
| `Cryptex1,SystemTrustCache` | `Firmware/044-76034-038.dmg.trustcache` | 1,871 | `9742f3d5...` |
| `Cryptex1,AppOS` | `044-75188-038.dmg` | 10,485,760 | `52e568e1...` |
| `Cryptex1,AppVolume` | `Firmware/044-75188-038.dmg.root_hash` | 229 | `bd60eb41...` |
| `Cryptex1,AppTrustCache` | `Firmware/044-75188-038.dmg.trustcache` | 767 | `5d9bf23c...` |

SystemTrustCache 的原始 module：

```text
version 2
uuid    fd99dff6-55d8-4340-9c99-803d70fdeeeb
entries 76
bytes   1848
sha256  d121ba89167e03aafd00fa687c30cd8ebc4ccafd10c1408adb2ba3de12403651
```

该 module 已经是 H91 原始 TrustCache bundle 的第二段（`d121ba89...`），所以 **SystemOS trust cache 不是当前缺失项**。

## 6. 结论

H96a18 的 `cryptexd`/`driverkitd` 停点很可能不是“等真实 IM4M”，而是：

```text
SystemOS 已启动
  + /System/Cryptexes/OS 符号链接存在
  + /private/preboot/Cryptexes/OS 没有内容
  + /private/preboot/cryptex1/current 没有内容
  -> launchd/cryptexd 找不到 cryptex 挂载/元数据
  -> driverkitd / launchd 后续服务停住
```

H62 的 `/private/preboot` 挂载和 H96 的 `/` union 都没有命中 `/private/preboot/Cryptexes/OS`，所以都没有解决这条路径。

## 7. 下一步

1. 新增一个 **Preboot overlay**（可来自 Data 卷 `/private/var/preboot`）：
   ```text
   cryptex1/current/os.dmg
   cryptex1/current/os.dmg.root_hash
   cryptex1/current/os.dmg.trustcache
   cryptex1/current/app.dmg...
   Cryptexes/OS/
   Cryptexes/App/
   ```
2. 用 bindfs 把 Data 的 `/private/var/preboot` union 到 `/private/preboot`。
3. SystemOS 改挂到 `/private/preboot/Cryptexes/OS`。
4. `DYLD_SHARED_CACHE_DIR` 改为 `/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld`。
5. 先不依赖 `imageboot-attach`：systemos 已由现有 UFS/APFS 路径按 UUID 挂载，`os.dmg` 只作为 Preboot 元数据占位；如果 launchd 坚持打开 DMG，再补 AppOS/SystemOS 文件后端。
6. 不在这一轮新增 skip，不改 AuthAPFS/Image4/TrustCache 验证。

## 8. 工具

新增 `scripts/prepare-preboot-overlay.py`：

```sh
python3 scripts/prepare-preboot-overlay.py \
  --ipsw /path/to/iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw \
  --output build/preboot-overlay
```

它只提取 root hash / trust cache 和创建 `cryptex1/current`、`Cryptexes/{OS,App}`，不复制 3.3 GiB SystemOS，不改 APFS。

## 9. 已落地的实验代码

本轮已经准备好一个默认关闭的 H103 实验，不改变现有 H91/H96 基线：

- `scripts/prepare-preboot-overlay.py`
  - 从本地或远程 IPSW 只读取 `BuildManifest.plist`、SystemOS/AppOS 的 root hash 与 trust cache；
  - 生成 `cryptex1/current/{os,app}.dmg.{root_hash,trustcache}` 和 `Cryptexes/{OS,App}`；
  - 校验 BuildManifest 摘要；
  - 不复制 3.3 GiB SystemOS。
- `scripts/prepare-owner-data-fixture.py --preboot-overlay DIR`
  - 把 overlay 放到 Data seed 的 `/private/preboot` 对应位置（Data 根即 `/private/var`，目录名为 `preboot`）。
- `patches/xnu/owner-preboot-layout.patch`
  - 新增 `XNU_OWNER_PREBOOT_LAYOUT=1`；
  - 在 Data mount 之后、SystemOS mount 之前，用 bindfs 把 `/private/var/preboot` union 到 `/private/preboot`；
  - SystemOS 挂到 `/private/preboot/Cryptexes/OS`；
  - `DYLD_SHARED_CACHE_DIR=/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld`；
  - 不启用 `XNU_OWNER_UNION_SYSTEMOS`，避免继续把 SystemOS 挂到 `/`。
- `.github/workflows/macos-cheeseburger.yml`
  - 新增 `preboot_layout` workflow_dispatch 布尔输入；
  - 为 true 时自动准备 Preboot overlay 和 Data seed。

构建约束由 `scripts/build-xnu-4k-baseline.sh` 检查：

```text
XNU_OWNER_PREBOOT_LAYOUT=1
  requires XNU_OWNER_CACHE_MOUNT=1
  requires XNU_OWNER_CACHE_STARTUP=1
  requires XNU_OWNER_DATA_MOUNT=1
  requires XNU_NATIVE_RAM_BLOCK=1
  requires XNU_OWNER_UNION_SYSTEMOS=0
```

对应 boot 图像仍然是 `fastboot boot`，不写 userdata/GPT。

## 10. 仍需验证

1. `/private/preboot` bindfs union 是否成功，`NATIVE_PREBOOT: status=0 stage=5` 是否出现。
2. SystemOS 是否成功挂到 `/private/preboot/Cryptexes/OS`，`NATIVE_H82_DATA`/`NATIVE_ENV` 是否正常。
3. `cryptexd` 是否仍启动但不再阻塞，launchd 是否能继续到 `backboardd`/`SpringBoard`。
4. `os.dmg` 当前是指向 OS 卷 `/usr/standalone/firmware/Cryptex1/SystemOS.dmg` 的符号链接，而本项目的 21H461 OS 根没有 `Cryptex1` 目录。若 launchd/cryptexd 坚持打开这个文件，需要再加 SystemOS 文件后端或占位方案。
5. AppOS 只准备了 `Cryptexes/App` 目录和元数据，没有挂载 AppOS；Safari/WebKit 相关 job 可能仍失败，但不应阻塞主屏。

## 11. 远程 macOS 构建结果（2026-11-01）

构建机：`lss@192.168.10.103`（macOS 15.8.2 / Xcode 26.3 / Python 3.12）。

关键配置：

```text
XNU_OWNER_PREBOOT_LAYOUT=1
XNU_OWNER_UNION_SYSTEMOS=0
XNU_OWNER_CACHE_MOUNT=1
XNU_OWNER_CACHE_STARTUP=1
XNU_OWNER_CACHE_CARRIER=1
XNU_OWNER_DATA_MOUNT=1
XNU_NATIVE_RAM_BLOCK=1
XNU_OWNER_CRYPTEX_FILES=0
XNU_OWNER_BOOT_MANIFEST=0
XNU_OWNER_DATA_VOLATILE=1
```

Data seed：

```text
UUID       95BE5FCF-BCA7-49C2-80C5-A7BE97DEF40A
packed     ~/h103/owner-data-fixture/owner-data.dbr
sha256     911932c26f4195058d22dc196e0bc928c46b0afb750ade4d8f60f12714be0615
```

引导参数沿用 H96a18 基线，只增加本实验的挂载布局；没有新增 skip：

```text
cpus=2 allow-root-hash-mismatch=1 sheng-pmgr=2
native-trace-amfi-syscall=1 native-trace-trust-cache=1
sheng-disable-jobs=com.apple.nsurlsessiond,com.apple.routined,
com.apple.nehelper,com.apple.chronod,com.apple.accountsd,
com.apple.alsd,com.apple.pfd
```

产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `kernel.macho` | 52,088,832 | `979260df84f1922726c4e9ce6ac540d023543a16fddee33d50d2f32d86b378fe` |
| `payload-H103-preboot.img` | 79,691,776 | `5bb75401ea53a2144798f15a917b85b15d74ad33f443088ee195acc0552a74da` |
| `boot-H103-preboot.img` | 81,147,904 | `aed7e8d8cf2d7af1402a88dfa46183607325a843f8455961293c6dd8fa2ae287` |
| payload ADT | — | `4b6d2cc33de8af2cc945a3472474ce34d0423bbd48b86e42c00aa1e53775f4d3` |

本地产物：

```text
/home/ls/UniXNU-cheeseburger/out/cheeseburger/boot/boot-H103-preboot.img
/home/ls/UniXNU-cheeseburger/out/cheeseburger/boot/payload-H103-preboot.img
```

内核中已确认包含：

```text
NATIVE_PREBOOT: status=%d stage=%d
/private/preboot/Cryptexes/OS
DYLD_SHARED_CACHE_DIR=/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld
```

已上机：

```text
fastboot boot out/cheeseburger/boot/boot-H103-preboot.img
Sending 'boot.img' (79246 KB)  OKAY
Booting                        OKAY
Finished. Total time: 11.848s
```

设备随后离开 fastboot/USB，没有自动回到 fastboot。最终屏幕内容尚未采集，需要现场确认。

观察目标：`NATIVE_PREBOOT: status=0 stage=5`、`NATIVE_H82_DATA: status=0 stage=4`、`NATIVE_ENV`，以及 launchd 是否越过 `driverkitd is active`。

## 12. H103 首次上机结果（2026-11-01）

最终屏关键日志：

```text
NATIVE_H81_SR: setup pid=1 files=54 mappings=62 ...
NATIVE_H81_SR: cache mount differs from root mount, checking preboot
NATIVE_H81_SR: preboot lookup error=0 cache_mount=... preboot_mount=...
shared_region: ... [1(launchd)] map(... 'dyld_shared_cache_arm64'):
  not on process' root volume nor preboot volume
NATIVE_H81_SR: setup error=-1
shared_region: ... vm_shared_region_start_address() failed
dyld[1]: dyld cache '(null)' not loaded: syscall to map cache into shared region failed
dyld[1]: DYLD_SHARED_CACHE_DIR=/System/Cryptexes/OS/System/Library/Caches/com.apple.dyld
dyld[1]: Library not loaded: /usr/lib/libSystem.B.dylib
```

结论：

1. **Preboot overlay 和 SystemOS 挂载已经生效**：`preboot lookup error=0`，`preboot_mount` 非空；`DYLD_SHARED_CACHE_DIR` 已是新的 `/System/Cryptexes/OS/...`。
2. 失败点不是挂载，而是 `native_owner_shared_cache_carrier()`：
   - 它硬编码 `directory = "/private/preboot/System/Library/Caches/com.apple.dyld"`；
   - 当前 cache 实际在 `/private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld`；
   - 因此 `owner_carrier=false`，随后 `preboot_vp` 的 mount 与 cache mount 不同，shared region 拒绝映射。
3. 其余 launchd 退出是 dyld cache 失败的直接后果，不是新的独立错误。

## 13. H103b 修复与构建

修复：

```c
#if defined(XNU_OWNER_PREBOOT_LAYOUT) && XNU_OWNER_PREBOOT_LAYOUT
	const char *directory = "/private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld";
#else
	const char *directory = "/private/preboot/System/Library/Caches/com.apple.dyld";
#endif
```

同时：

- `vm_unix.o` 增加 `-DXNU_OWNER_PREBOOT_LAYOUT`；
- `vm_unix.o` 的 stamp 包含 preboot layout，切换时强制重编；
- `owner-preboot-layout.patch` 加入 `LATE_PATCH` 反应用列表，避免先反 `shared-region-cache-bypass` 后破坏本补丁上下文。

H103b 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `399ecaa2fec9ecfab5021df2d7e85cff1017b6d309f8e036e1849881b99ba816` |
| payload | `d3d7df410cde3134e4bc97469c9a8d2449cf631f6bbca7358443b2f6929596d0` |
| boot | `3a0f6f196482c382bcb9c82dbf162a046a4dc2d8261682adde8a1fb7329c7566` |

本地路径：

```text
/home/ls/UniXNU-cheeseburger/out/cheeseburger/boot/boot-H103b-preboot.img
/home/ls/UniXNU-cheeseburger/out/cheeseburger/boot/payload-H103b-preboot.img
```

下一次上机重点：确认 `owner_carrier` 放行后 shared region 映射成功，dyld 能加载 `/usr/lib/libSystem.B.dylib`。

## 14. H103b 上机结果（2026-11-01）

H103b 成功越过 dyld cache：

```text
msuearlyboottask: doing boot task
com.apple.xpc.launchd: Doing boot task
FIPSPOST_USER ... all tests PASSED
launchd boot tasks: fsck, mount-phase-1, data-protection,
  finish-obliteration, detect-installed-roots, commit-boot-mode,
  mount-phase-2, init-with-data-volume, fixup-mobile-tap,
  MSEarlyBootTask, fips, keybag, useragentd, dirs_cleaner,
  xpcroleaccountd, init_featureflags, auerlyboot
```

说明：

- shared region / dyld cache 不再报 `not on process' root volume nor preboot volume`；
- `/usr/lib/libSystem.B.dylib` 的 `no dyld cache` 错误消失；
- launchd 已经进入标准 boot task 序列。

新停点：

```text
tzinit: Unable to locate data; resetting to system partition
tzinit: Last resort force_system_dataset() failed: No such file or directory
pid 17 exited -- no exit reason available -- (signal 0, exit 2)
Please go to https://panic.apple.com
```

原因是 Data skeleton 缺少：

```text
/private/var/db/timezone/zoneinfo
```

OS root 的 `/usr/share/zoneinfo` 是指向 `/var/db/timezone/zoneinfo` 的符号链接；Data 挂到 `/private/var` 后，OS root 的 `/private/var/db/timezone` 被隐藏，而 Data seed 没有补这个目录，所以 `tzinit` 找不到时区数据。

## 15. H103c 修复与构建

`scripts/prepare-owner-data-fixture.py` 的 skeleton 模式新增：

- `db/timezone` 目录；
- 从 OS mount 的 `usr/share/zoneinfo.default` 复制 602 个文件到 `db/timezone/zoneinfo`（约 364 KiB）；
- `db/timezone/localtime -> /var/db/timezone/zoneinfo/US/Pacific`。

新 Data seed：

```text
UUID    9E4EDD86-20C5-44A5-A964-35D291D7D956
packed  bc0f10d4650fc322ce69d0eb7b7190428f93305292bd0bd03f21588da8c79253
```

H103c 产物（内核沿用 H103b）：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `399ecaa2fec9ecfab5021df2d7e85cff1017b6d309f8e036e1849881b99ba816` |
| payload | `1318aa1b723f909946440f52c0a3ad6c7620ff725f1063d18985f1edc57a4216` |
| boot | `4c86ac177500f21b72fc14d41ebf4a2c253922addd69c1142e1f2f2fd85a5333` |

本地产物：

```text
/home/ls/UniXNU-cheeseburger/out/cheeseburger/boot/boot-H103c-preboot.img
```

下一步上机确认 `tzinit` 不再退出，并记录下一个 boot task。


## 16. 设备连接环境变更（2026-11-01）

- 构建机不变：`lss@192.168.10.103`（macOS）。
- 设备改接到 Windows：`ls@192.168.10.225`，使用该机 PATH 中的 `fastboot.exe`。
- 镜像存放目录：`D:\Users\ls\Documents\OnePlus5_ios`。
- 后续每轮：macOS 构建 → HTTP/文件传输到 Windows 目录 → Windows 上 `fastboot boot`。
- 不在仓库记录 Windows 密码。

## 17. H103c 上机结果与 H103d 修复（2026-11-01）

H103c 已经越过 root/launchd 前置阶段，但 Data mount 失败：

```text
NATIVE_ROOT_BYPASS: auth=80
NATIVE_H82_DATA: status=2 stage=0 ro=-1 dev=-1 size=0
panic: offline scratch Data mount failed: 2
```

`status=2` 是 `ENOENT`，`stage=0` 表示还没进入设备查找。原因是 H103c 只重新打了 payload/Data seed，内核仍编译旧 UUID：

```text
kernel: 95BE5FCF-BCA7-49C2-80C5-A7BE97DEF40A
Data:   9E4EDD86-20C5-44A5-A964-35D291D7D956
```

H103d 修复：

- 内核 `XNU_OWNER_DATA_VOLUME_UUID` 改为 `9E4EDD86-20C5-44A5-A964-35D291D7D956`；
- 强制重编 `kern_exec.o`；
- 继续使用 H103c 的 timezone Data seed。

H103d 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `2fcb8b5f2173e8b39403ed3f80075e984b0baaaeb4eadf728782d646e8514224` |
| payload | `79240916039008f433b631e1b37575a46a6dae99103a61f89afc966fd71c5692` |
| boot | `219236da0e7b7336b691e831fd71e844126221b857bbc0d4e37bb998cd130e75` |

Windows 目录：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103d-preboot.img
```

已在 Windows 上执行：

```text
fastboot boot "D:\Users\ls\Documents\OnePlus5_ios\boot-H103d-preboot.img"
Sending ... OKAY
Booting   OKAY
```

等待最终屏幕确认 Data mount 和 tzinit。

## 18. H103d 上机结果与 H103e 诊断（2026-11-01）

H103d 已经不再报 Data UUID mismatch，launchd 继续执行 boot task；新 `tzinit` 错误变为：

```text
tzinit: Unable to locate data; resetting to system partition
tzinit: Unable to create directory with attributes: Read-only file system
tzinit: Last resort force_system_dataset() failed: Read-only file system
pid 17 exited -- no exit reason available -- (signal 0, exit 2)
```

Data seed 中已确认存在：

```text
db/timezone/zoneinfo      （602 个文件）
db/timezone/localtime -> /var/db/timezone/zoneinfo/US/Pacific
```

因此问题收窄为两种可能：

1. `/private/var` 在 tzinit 运行时不是 Data 的 RW 挂载，而是 OS root 的只读目录；
2. Data 是 RW，但 tzinit 期望的 `/var/db/timezone` 数据集布局（`tz/`、`tz_latest`、`icutz`）不存在，它回退写系统目录时撞上只读。

H103e 只增加诊断，不改变行为：

- `log-data-snapshot.patch`；
- 在 `tzinit` 退出时打印：
  ```text
  NATIVE_H103_DATA: status=... ro=... dev=...
  NATIVE_H103_VAR: flags=... fstype=...
  ```

H103e 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `0ef659ae57587396e24af61699e2d84c5f3854752a689d1500ce35247cf80b73` |
| payload | `24601447421f6577023506dea68698512bcc04959461a48ac17e99d9ff7d36f2` |
| boot | `45e5a3ca42db952e30d3291119e6ee7e37860cdccfdbb46aacb251c52fc25bc9` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103e-preboot.img
```

## 19. H103f：tzinit 数据集布局 + Data 诊断（2026-11-01）

H103d 的 `tzinit` 报：

```text
tzinit: Unable to create directory with attributes: Read-only file system
tzinit: Last resort force_system_dataset() failed: Read-only file system
```

为一次拿到两件事的证据，H103f 在 H103e 诊断内核基础上，把 Data seed 的时区布局改成 tzinit 期望的版本化数据集：

```text
/private/var/db/timezone/
  tz/44l/zoneinfo/...
  tz_latest -> tz/44l
  zoneinfo -> tz_latest/zoneinfo
  icutz -> /usr/share/icu
  localtime -> /var/db/timezone/zoneinfo/US/Pacific
```

数据来自 OS root 的 `/usr/share/zoneinfo.default`（602 个文件，`+VERSION` = `44l`）。

H103f Data seed：

```text
UUID    1A4CE9DF-34B6-4B52-9744-5052A9D20B23
packed  699c39b26147386d7cd8adcf7d549d3db318ff4d52512dca00cffa8adb70ca54
```

H103f 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `509800409818abf4ae9ed9c19e694b5c6170bb99d826e668c6da8967c2263275` |
| payload | `ede0771652453e29fcef0d13c5b86bd68fb7c3a0e0003169ef2bbbe6ed70adfc` |
| boot | `5b4ed54041d13e27dfa3f69c637087ba0414c1a23ec4c2f918489354337cd613` |

已从 Windows boot：

```text
fastboot boot "D:\Users\ls\Documents\OnePlus5_ios\boot-H103f-preboot.img"
Sending ... OKAY
Booting   OKAY
```

若 `tzinit` 仍失败，屏幕会出现：

```text
NATIVE_H103_DATA: status=... ro=... dev=...
NATIVE_H103_VAR: flags=... fstype=...
```

据此可直接判断是 Data 挂载问题还是 tzinit 路径问题。

## 20. H103f 上机结果：tzinit 通过，回到 driverkitd（2026-11-01）

H103f 最终屏不再出现 `tzinit` 错误，launchd boot task 序列继续；最后可见：

```text
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... lastWin=OS/SystemOS ...
```

没有 panic，没有自动回到 fastboot。说明：

- Preboot/Cryptex 布局 + owner carrier + dyld cache + tzinit 都已通过；
- 新停点回到旧的 `FileSet KC` / `driverkitd is active`；
- 当前内核没有 `NATIVE_EXEC` 日志，无法确认 `cryptexd`/`eligibilityd` 是否启动、是否退出。

H103f 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `509800409818abf4ae9ed9c19e694b5c6170bb99d826e668c6da8967c2263275` |
| payload | `ede0771652453e29fcef0d13c5b86bd68fb7c3a0e0003169ef2bbbe6ed70adfc` |
| boot | `5b4ed54041d13e27dfa3f69c637087ba0414c1a23ec4c2f918489354337cd613` |

## 21. H103g：进程/退出观测（2026-11-01）

新增 `log-process-snapshot.patch`：

- `NATIVE_EXEC: pid=... ppid=... comm=... argv0=... argv1=...`
- 对 `cryptexd`/`eligibilityd`/`launchd`/`xpcproxy`/`driverkitd`/`backboardd` 记录：
  ```text
  NATIVE_EXIT: pid=... ppid=... comm=... status=... ns=... code=...
  ```

H103g 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `397637af7df6841a50f67e841b471d632f56b6e5c67db06980ddf5b11b60d910` |
| payload | `eef3bea8407ed55d9c8722947cbb3f10f513edb91c19c658b784117ef74710b9` |
| boot | `7b60d3fdd4d876e69cfd324f562bf87db614fb2d46a6ac8c2de96ee6370e1aa5` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103g-preboot.img
```

下一步 boot H103g，确认：

1. `cryptexd`、`eligibilityd` 是否出现 `NATIVE_EXEC`；
2. 是否出现 `NATIVE_EXIT`；
3. `driverkitd` 是否在等某个 `FileSet KC` kext。

## 22. H103g 上机结果与 H103h 进程快照（2026-11-01）

H103g 已经能看到完整 exec 序列：

```text
NATIVE_EXEC: pid=65 ppid=1 comm=driverkitd
NATIVE_EXEC: pid=70 ppid=1 comm=AppleCredentialManager...
NATIVE_EXEC: pid=73 ppid=1 comm=rapportd
NATIVE_EXEC: pid=74 ppid=1 comm=useractivityd
NATIVE_EXEC: pid=76 ppid=1 comm=fseventsd
NATIVE_EXEC: pid=77 ppid=1 comm=IOHFB_FDR_Loader
NATIVE_EXEC: pid=82 ppid=1 comm=xpcproxy argv1=com.apple.logd_helper
NATIVE_EXEC: pid=84 ppid=1 comm=logd_helper
```

之后屏幕停止刷新，停在：

```text
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... winFlight=1 lastWin=SystemOS/OS
```

可见窗口内没有 `cryptexd`/`eligibilityd`，也没有 `NATIVE_EXIT`/panic。判断：

- `driverkitd` 已启动，launchd 继续拉起一批 daemon；
- 但 `cryptexd`/`eligibilityd` 之前就停住；
- 停点仍是 `driverkitd` / `FileSet KC`，需要确认是 launchd 等 driverkitd，还是 UFS 读停住。

H103h 增加一个 **thread_call 进程快照**：

- 在 `launchd`/`driverkitd` exec 时调度；
- 90 秒后打印：
  ```text
  NATIVE_PROC_BEGIN
  NATIVE_PROC: pid=... ppid=... comm=...
  ...
  NATIVE_PROC_END
  ```

H103h 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `f9b73b9c4d268df4224dfd38aa13b50ae048f32ff216b91b76c12f64da7f60c2` |
| payload | `61198f9d00366b4d1c21156984a255f5cf152934040f8fabdb4bd9ac1cba0953` |
| boot | `a86c5a6a360cbb3055539141f2ca6165c81e6c2ffff041766dd1c073092aa143` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103h-preboot.img
```

已在 Windows boot。下一步等待 90 秒后的 `NATIVE_PROC` 输出，确认 `cryptexd`/`eligibilityd`/`driverkitd` 的实际 PID 和父进程。

## 23. H103h 进程快照结果（2026-11-01）

H103h 的 `thread_call` 快照没有在最终屏出现；屏幕在 3 分钟内只持续输出：

```text
NATIVE_UFS_WINDOW: SystemOS ...
NATIVE_UFS_PROGRESS: ... lastWin=SystemOS ... winBytes≈3.2 GiB ... winFlight=1
```

没有 `NATIVE_PROC_BEGIN`/`NATIVE_PROC_END`/panic。可能原因：

- `thread_call` 没有在这个停点执行（或输出被刷掉）；
- 或系统停在 UFS 读，快照线程也无法输出。

H103g 的 exec 日志已经确认：

```text
driverkitd
AppleCredentialManager
rapportd
useractivityd
fseventsd
IOHFB_FDR_Loader
xpcproxy/logd_helper
logd_helper
```

之后没有 `cryptexd`/`eligibilityd`，也没有 `NATIVE_EXIT`。

## 24. H103i：一次性跳过 driverkitd 的诊断（2026-11-01）

为了判断 launchd 是否卡在 `driverkitd`，H103i 只改 payload，不重建内核：

```text
sheng-disable-jobs=...,com.apple.driverkitd
```

内核仍是 H103h：

```text
kernel f9b73b9c4d268df4224dfd38aa13b50ae048f32ff216b91b76c12f64da7f60c2
```

H103i 产物：

| 文件 | SHA-256 |
| --- | --- |
| payload | `2aefb03b484878d159ed3cb097818c9f1357401f9102b18483d65c2208b1b721` |
| boot | `7129e8b85a340a0f3ee2eb353486b1041f54f089009e2fb46994e7b54a1a6646` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103i-skipdk.img
```

这是**一次性诊断**，不是修复。判读：

- 若跳过 driverkitd 后出现 `cryptexd`/`eligibilityd`，说明 launchd 在等 driverkitd；
- 若更早 panic/停止，说明 driverkitd 是必需服务，回到 UFS/FileSet KC 路径；
- 无论结果，后续都不把该 skip 当作最终方案。

## 25. H103i 结果：跳过 driverkitd 会继续，但仍无 cryptexd（2026-11-01）

H103i（唯一变量：`sheng-disable-jobs=...,com.apple.driverkitd`）的最终屏：

```text
NATIVE_EXEC: pid=93 ppid=1 comm=livedriven
NATIVE_EXEC: pid=94 ppid=1 comm=xpcproxy argv1=com.apple.coresymbolicationd
NATIVE_EXEC: pid=95 ppid=1 comm=xpcproxy argv1=com.apple.donotdisturbd
NATIVE_EXEC: pid=97 ppid=1 comm=donotdisturbd
NATIVE_EXEC: pid=99 ppid=1 comm=... datanator / dataaccess
NATIVE_H66_FCNTL ...
NATIVE_CACHE_SIG: ...
NATIVE_UFS_PROGRESS ...
```

结论：

- 跳过 `driverkitd` 后 launchd 确实继续启动了一批服务（`coresymbolicationd`、`donotdisturbd`、`datanator` 等）；
- 但仍没有 `cryptexd`/`eligibilityd`；
- 这更像 **cryptexd 依赖 driverkitd**，而不是跳过 driverkitd 能解决问题；
- H103i 只作为对照，不作为最终方案。

## 26. H103j：Preboot 挂载 + SystemOS root union（2026-11-01）

H96a18 曾用 `XNU_OWNER_UNION_SYSTEMOS=1` 把 SystemOS union 到 `/`，到达 cryptexd；H103 只挂到 `/private/preboot/Cryptexes/OS`，launchd/dyld 路径正确，但 driverkitd 可能仍需要 root 上的 `/System/DriverKit` 视图。

H103j 保留 H103 的 Preboot/Cryptex 布局，同时增加一次 **SystemOS root union**：

```c
if (!error) {
    struct mount_args root_request = request;
    root_request.flags = MNT_RDONLY | MNT_UNION;
    copyout("/", root_request.path, 2);
    root_error = mount(p, &root_request, &root_result);
    printf("NATIVE_H103_ROOT_UNION: %d\n", root_error);
}
```

构建开关：

```text
XNU_OWNER_PREBOOT_LAYOUT=1
XNU_OWNER_PREBOOT_ROOT_UNION=1
```

boot args 不使用 `com.apple.driverkitd` skip，恢复 driverkitd。

H103j 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `e71fe93c3bb882f1d64868b4630046612da7b0294487d05de48fb300961eb7c5` |
| payload | `b44703e035cd86a912efb871b6150a2b7242080966426c99bf243d8a40d26953` |
| boot | `59c5ec427b300081e310f98d266c5b73f500b27a12425c122f042fd31de906eb` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103j-rootunion.img
```

已 boot。判读：

- `NATIVE_H103_ROOT_UNION: 0` 且 driverkitd 不再 stall、cryptexd 出现 → root union 是缺失项；
- root union 失败或 driverkitd 仍 stall → 需要转向 FileSet KC/UFS 读路径。

## 27. H103j 失败原因与 H103k 修复（2026-11-02）

H103j 上机停在：

```text
NATIVE_H82_DATA: status=2 stage=0 ro=-1 dev=-1 size=0
panic: offline scratch Data mount failed: 2
```

原因仍是 UUID：远程 `run-h103-build.sh` 中 `XNU_OWNER_DATA_VOLUME_UUID` 被恢复成旧值：

```text
95BE5FCF-BCA7-49C2-80C5-A7BE97DEF40A
```

而 Data seed 是：

```text
1A4CE9DF-34B6-4B52-9744-5052A9D20B23
```

H103k 修复：

- 内核 UUID 改为 `1A4CE9DF-34B6-4B52-9744-5052A9D20B23`；
- 强制重编 `kern_exec.o`；
- 保留 `XNU_OWNER_PREBOOT_ROOT_UNION=1`。

H103k 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `ca2f40bf8d5e96c0d2619098fd11eb62461e15d4e860f1adab148fedae1c809f` |
| payload | `0fdf0f4d630d6ff3c13c9c41851cbcb8d99cc90f894fb7024a6ddc59ae6ea760` |
| boot | `235bdd25e322c3f6f086f741d4dda429ee06fab02a6c8db0e4215fe038044882` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103k-rootunion.img
```

已 boot，等待：

```text
NATIVE_H103_ROOT_UNION: 0
```

## 28. H103k/H103l：root union 改为 bindfs（2026-11-02）

H103k（APFS 二次 mount 到 `/` + MNT_UNION）仍然停在：

```text
KextLog: Building FileSet KC(s)
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
```

`NATIVE_H103_ROOT_UNION` 没有出现在最终可见窗口，无法区分是 mount 失败还是成功但 driverkitd 仍卡。因此 H103l 改为 **bindfs root union**，不再次挂 APFS：

```c
source = "/private/preboot/Cryptexes/OS";
mount("bindfs", "/", MNT_RDONLY | MNT_UNION, source);
```

这样 `/System/DriverKit`、`/System/Library/...` 等路径从已挂载的 SystemOS 视图叠加到 root，同时保留 Preboot/Cryptex 布局。

H103l 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `eaa1dbd6060a597af4c910b22475a687a37323a7eb9498333ac1bb86d0fae787` |
| payload | `fb84ee1102735a1cb64735393cca522ab3d7dd78a5adf71509e1b6a358d5dbd2` |
| boot | `b9163e77b30bd473ace944225663ed3467da38387508836944e1b20bda92f2fa` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103l-rootbindfs.img
```

已 boot。判读：

- `NATIVE_H103_ROOT_UNION: 0` 且 driverkitd 不再 stall → root bindfs 是缺失项；
- 非 0 → bindfs mount 失败，查 entitlement/源路径；
- 0 但仍 stall → driverkitd 的 FileSet KC 不是 root 视图问题，转 UFS/FileSet KC 调用链。

## 29. H103l 失败：bindfs root union 破坏 dyld/launchd（2026-11-02）

H103l 没有出现 `NATIVE_H103_ROOT_UNION`，而是 launchd 直接退出：

```text
NATIVE_LAUNCHD_ABORT_DESC: Library not loaded: /usr/lib/libSystem.B.dylib
  Referenced from: <...>/sbin/launchd
  Reason: tried: '/usr/lib/libSystem.B.dylib' (no such file, no dyld cache)
NATIVE_EXIT: pid=1 ppid=0 comm=launchd status=0x6 ns=6 code=0x1
pid 1 exited -- exit reason namespace 6 subcode 0x1
```

结论：

- **bindfs root union 不可用**：它破坏了 root `/usr/lib` / dyld cache 的可见性或 root 卷判断；
- H103l 是回归，不能作为后续基线；
- 回退到 H103f/H103g（Preboot/Cryptex 挂载，不做 root union）。

H103l 产物仅保留作失败记录：

```text
kernel eaa1dbd6060a597af4c910b22475a687a37323a7eb9498333ac1bb86d0fae787
boot   b9163e77b30bd473ace944225663ed3467da38387508836944e1b20bda92f2fa
```

## 30. 后续方向

root union 两条路都失败：

- APFS 二次 mount：driverkitd 仍停在 FileSet KC；
- bindfs root union：launchd 找不到 libSystem/dyld cache。

当前应回到 **无 root union 的 H103g 基线**，集中解决：

1. `driverkitd` 的 FileSet KC 到底在等哪个文件/服务；
2. 为什么它持续读 SystemOS/OS UFS 而没有新的 exec；
3. `cryptexd` 是否依赖 driverkitd 的 Mach service。

下一步只做读/追踪，不改变挂载布局：

- 在 `NativeUfsProbe::readWindowBulk`/`NATIVE_UFS_WINDOW` 增加调用者 PID/comm；
- 或在 driverkitd exec 后调度一个 **panic 进程快照**，确保输出不被滚屏；
- 不再尝试 root union、不再新增 cryptexd/eligibilityd skip。

## 31. H103m2：UFS 调用者 PID/comm 追踪（2026-11-02）

回到 H103g 无 root union 基线，给 `NativeUfsProbe` 的窗口日志加调用者：

```text
NATIVE_UFS_WINDOW: ... caller=<comm>/<pid>
```

首次构建时 archive 是旧的（`build/native-ufs-probe` 未重建），预链接内核里仍是旧格式；H103m2 手工执行：

```sh
python3 scripts/build-arm-driver.py NativeUfsProbe
```

后重新链接，预链接内核已包含 `caller=%s/%d`。

H103m2 产物：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `b0fb38e9116c7c941b41ee77bac89f5ed704e58f4acb65a75063f5c35baf77d1` |
| payload | `3276752c39055a14013bf1e5ca59f00714349a60f9a1a8cc62b1184739cae153` |
| boot | `45163f34c59447802c97826eba48f53ec49e73d2adda114f1842ad72732ffa36` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103m2-ufscaller.img
```

已 boot。判读：

- 若持续 SystemOS 读的 `caller=driverkitd/<pid>`，说明 driverkitd 在扫描/加载 FileSet KC；
- 若 `caller=launchd/<pid>`，说明 launchd 在等文件；
- 若 `caller=kernel_task/0`，说明是 pagein/内核预读，不是用户态主动读。

## 32. H103m2 结果：UFS 调用者确认是 driverkitd（2026-11-02）

H103m2 最终屏出现了 caller 字段：

```text
NATIVE_UFS_WINDOW: SystemOS req=53248 block=c4ea8 count=8 abs=17f540000 lba=19f715 caller=driverkitd/62
NATIVE_UFS_WINDOW: SystemOS req=53248 done=4096 ok=1 ticks=86
  read=0 write=73 abs=17f540000 lba=19f715 caller=driverkitd/62

KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
NATIVE_UFS_PROGRESS: ... winBytes=3233879040 winFlight=1 lastWin=SystemOS
```

同时还能看到：

```text
caller=MobileGestaltHelper/86
```

结论：

- **持续读 SystemOS 的是 `driverkitd`（PID 62）**，不是 launchd/kernel_task；
- `driverkitd` 正在加载 FileSet KC，读的是 SystemOS 窗口；
- `driverkitd is not active -> Loading FileSet KC(s) -> driverkitd is active` 说明它在 FileSet KC 流程中；
- 之后没有 `cryptexd`/`eligibilityd`，launchd 很可能在等 FileSet KC/ driverkitd 完成。

H103m2 产物：

```text
kernel b0fb38e9116c7c941b41ee77bac89f5ed704e58f4acb65a75063f5c35baf77d1
boot   45163f34c59447802c97826eba48f53ec49e73d2adda114f1842ad72732ffa36
```

下一步：

- 若 UFS 读仍在推进，等待 FileSet KC 完成；
- 若停住，需要 UFS 请求级 stall/panic 或定位 FileSet KC 的具体路径/文件；
- 不再尝试 root union。

## 33. H103m2 的关键结论与下一步（2026-11-02）

H103m2 直接证明了：

```text
NATIVE_UFS_WINDOW: SystemOS ... caller=driverkitd/62
```

并出现：

```text
KextLog: driverkitd is not active
KextLog: Loading FileSet KC(s)
KextLog: driverkitd is active
```

同时没有 `NATIVE_UFS_STALL`/panic；心跳线程没有触发 UFS stall。说明：

- 持续读 SystemOS 的是 **driverkitd**；
- 不是 launchd 随机等待，也不是单纯内核 pagein；
- driverkitd 正在处理 FileSet KC；
- launchd 在 cryptexd 之前停住。

`driverkitd` 二进制字符串显示它会加载：

```text
BootKernelCollection.kc
AuxiliaryKernelCollection.kc
SystemKernelCollection
```

而当前 OS root 没有：

```text
/System/Library/KernelCollections
```

SystemOS 也没有 KernelCollections。因此下一步的最高优先级是：

1. 只读确认 driverkitd 的 `KernelPath`/`BootKernelCollection` 配置和它实际打开的文件；
2. 如果确实缺 `BootKernelCollection.kc`/`AuxiliaryKernelCollection.kc`，考虑从原始 kernelcache 派生一个窄 overlay，只覆盖 `/System/Library/KernelCollections`，不要再次 root union；
3. 不跳过 driverkitd、不新增 cryptexd/eligibilityd skip。

H103m2 是当前最好的诊断基线：

```text
kernel b0fb38e9...
boot   45163f34...
```

## 34. H103m3：补齐 driverkitd Data 目录（2026-11-02）

`driverkitd` 二进制配置要求：

```text
ThirdPartyDriverKitStagingDirectory = /private/var/db/driverkitd/SystemExtensions
ApprovalsDatabasePath               = /private/var/db/driverkitd/driver-approvals.plist
ApplicationCachePath                = /private/var/db/driverkitd/applications.plist
KernelExtensionManagement Staging   = /private/var/db/KernelExtensionManagement/Staging
```

原 Data skeleton 没有 `db/driverkitd` 和 `db/KernelExtensionManagement`。H103m3 在不改变 Data UUID 的前提下，直接把下面目录加进 `owner-data-fixture3` 的 APFS：

```text
/private/var/db/driverkitd/SystemExtensions
/private/var/db/KernelExtensionManagement/Staging
/private/var/tmp/com.apple.driverkitd/DriverExtensions
```

新 packed Data seed：

```text
sha256 af96cfdf13e41bd74c71810da8fe4a1338393d3b766ab39faf0e1bc2402cd475
```

H103m3 产物（内核沿用 H103m2）：

| 文件 | SHA-256 |
| --- | --- |
| kernel | `b0fb38e9116c7c941b41ee77bac89f5ed704e58f4acb65a75063f5c35baf77d1` |
| payload | `29fde9c74340df404f6d2e65c2cd6bed475cb3e947e9cf02a3f0edb065d297c5` |
| boot | `62ce9ab467427a8f99ee2f67aeca9b9a689fe972878b8f8a787dfff32edcc435` |

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103m3-dkdirs.img
```

已 boot。判读：driverkitd 是否不再反复 FileSet KC，或是否出现新的 approvals/state 错误。

## 35. H103m3 结果：driverkitd Data 目录后用户态明显前进（2026-11-02）

H103m3 最终屏出现大量新的 `NATIVE_EXEC`，包括一批此前没有的服务（截图可辨识的有 `pkd`、`securityd`、`authd`、`ctkd`、`cloudpaird`、`mobileassetd`、`distnoted` 等），同时仍有：

```text
NATIVE_UFS_WINDOW: SystemOS ... caller=driverkitd/62
```

说明：

- 补 `/private/var/db/driverkitd`、`KernelExtensionManagement/Staging`、`tmp/com.apple.driverkitd/DriverExtensions` 后，launchd 明显继续启动更多用户态服务；
- `driverkitd/62` 仍在读 SystemOS，FileSet KC 可能仍在后台完成；
- 最终是否停住、cryptexd 是否出现，需要下一张更清晰的屏幕确认。

H103m3 产物：

```text
kernel b0fb38e9116c7c941b41ee77bac89f5ed704e58f4acb65a75063f5c35baf77d1
payload 29fde9c74340df404f6d2e65c2cd6bed475cb3e947e9cf02a3f0edb065d297c5
boot   62ce9ab467427a8f99ee2f67aeca9b9a689fe972878b8f8a787dfff32edcc435
```

## 36. H103m3 最终结果：SpringBoard 已启动（2026-11-02）

最终屏关键行：

```text
NATIVE_UFS_WINDOW: SystemOS req=33792 block=f8320 count=8
  abs=17f540000 lba=19d5a4 caller=SpringBoard/27
NATIVE_UFS_WINDOW: SystemOS req=33792 done=4096 ok=1
  ticks=93 read=0 write=82 abs=17f540000 lba=19d5a4 caller=SpringBoard/27

NATIVE_UFS_WINDOW: SystemOS req=34816 ...
  caller=driverkitd/62
```

同时可见大量服务已经 exec，包括：

```text
SpringBoard/27
logd_helper
distnoted
...
```

结论：

- **H103m3 首次到达 SpringBoard**，已经越过 H96a18 的 cryptexd/eligibilityd 停点；
- `driverkitd` 仍在后台读 SystemOS，但不再是唯一停点；
- 当前没有 UI/桌面，因为构建仍是：
  ```text
  XNU_NATIVE_MOBILE_DISPLAY=0
  XNU_NATIVE_ADRENO=0
  ```
  且 legacy display 未启用；
- 下一步是显示/WindowServer/backboardd 链路，而不是继续 cryptexd。

H103m3 是当前最远基线：

```text
kernel b0fb38e9...
payload 29fde9c7...
boot   62ce9ab4...
```

## 37. H103m3 最终结果：SpringBoard 已启动（2026-11-02）

最终屏明确出现：

```text
NATIVE_UFS_WINDOW: SystemOS req=33792 block=f8320 count=8
  abs=17f540000 lba=19d5a4 caller=SpringBoard/27

NATIVE_UFS_WINDOW: SystemOS req=33792 done=4096 ok=1
  ticks=93 read=0 write=82 abs=17f540000 lba=19d5a4 caller=SpringBoard/27
```

同时还有：

```text
NATIVE_UFS_WINDOW: SystemOS ... caller=driverkitd/62
```

结论：

- **H103m3 首次到达 SpringBoard**，已经越过 H96a18 的 cryptexd/eligibilityd 停点；
- `driverkitd` 仍在后台读 SystemOS，但不再是唯一停点；
- 最终没有桌面/UI，是因为当前构建仍关闭显示：
  ```text
  XNU_NATIVE_MOBILE_DISPLAY=0
  XNU_NATIVE_ADRENO=0
  XNU_NATIVE_LEGACY_DISPLAY=0
  ```
- 下一步从 cryptexd/FileSet KC 转向 **显示/WindowServer/backboardd**。

H103m3 是当前最远基线：

```text
kernel b0fb38e9...
payload 29fde9c7...
boot   62ce9ab4...
```

## 38. H103n：OP5 原始 Legacy Framebuffer 首次编入内核（2026-11-02）

### ABI 审计结果

OP5 21H461 原始 kernelcache 中的 `com.apple.iokit.IOMobileGraphicsFamily`：

```text
__TEXT_EXEC 0xfffffff00676c000 size 0x36f74
SHA-256    2e044ee68c1650397e1435234ca6459206262e4c7ed709cb7131c6f664f9bd9b
```

该 executable 与 sheng 参考中的 family 完全相同；OP5 的 prelink slide 为
`0x5000000`，因此 native kernel 中的地址为原始地址 + `0x5000000`：

```text
Legacy constructor 0xfffffff0067865d8 -> 0xfffffff00b7865d8
Legacy vtable      0xfffffff006f38560 -> 0xfffffff00bf38560
gMetaClass         0xfffffff007b35940 -> 0xfffffff00cb35940
abstract slots     211,213,245,246,306,307,337,338,345
instance bytes     0x18a0
```

### 新增构建

- `board.toml` roots 增加 `com.apple.iokit.IOMobileGraphicsFamily`；prelink 自动拉入
  `IOSurface`、`IOAVFamily`、`AppleM2ScalerCSCDriver`，共 29 个 component。
- `scripts/audit-mobile-graphics-legacy-op5.py`：从 21H461 kernelcache 定位
  constructor/vtable/abstract slots。
- `scripts/build-op5-legacy-display.py`：生成 `OriginalLegacyFramebufferABI.h`，
  编译 `NativeLegacyDisplay`/`NativeGOPPresenter`/`LegacyDisplayProbe`，绑定原始
  family/IOSurface 符号，产出 `libNativeLegacyDisplay.late.a`。
- `XNU_NATIVE_LEGACY_DISPLAY=1` 链接该 archive。
- H103n 启动参数新增：
  ```text
  offline-mobile-graphics-load=1
  offline-legacy-gop=1
  offline-legacy-phase=4
  offline-legacy-register=1
  offline-legacy-validate=1
  offline-legacy-transfer=1
  offline-legacy-retire=1
  offline-legacy-pm=1
  ```

### H103n 产物

```text
kernel  e3b3c356ff18c98a0365d2fd0b0c225496c181595a77ad87858e9bf8890a395c
payload f66dcdec71bf1d34ba6b5a22c0876df6e1e19a30b4a779274b7d223feaf02acf
boot    05e184d1e64a4a2a0a2295d0c1ade10b66e3d82785c98bde62dc9cdb1d58bc21
archive 0326dcadb64d515b03ecaaf8344dbb593d5dc9afa0ce46477369f94201c42260
```

boot 镜像已传至 Windows `D:\Users\ls\Documents\OnePlus5_ios\boot-H103n-legacy.img`，
并已 `fastboot boot`。下一步看屏幕是否出现 `NativeLegacyDisplay` stage、
`backboardd`/`WindowServer`，或 display guard panic。

## 39. H103w–H103ad：cpus=1、GOP 自检与显示客户端诊断（2026-11-02）

### H103w：cpus=1 对照

H103v 同内核，只把 payload 的 `cpus=2` 改为 `cpus=1`。

结果：

- 每次都能到达：
  ```text
  KextLog: driverkitd is active
  ```
- 说明之前概率性停在 KextLog 之前主要是 SMP/早期启动时序竞态。
- 但 userland 显示客户端仍不稳定：
  - 有时 `display calls=0`；
  - 有时 `display calls=1`，但 `NATIVE_LEGACY_CLIENTS: C0 calls=0`。

产物：

```text
boot 79dc3a1720c5e552194f79a709ecf810205c395d331c2fcb9d69f7055d6e51aa
```

### H103x：GOP 自检图案

在 `NativeLegacyDisplay::startDisplay` 成功后，UFS 心跳每 10 秒在右上角画
256×256 品红色块。

结果：

- H103y/H103z/aa 均可见品红色块；
- 证明：
  ```text
  GOP mapping -> framebuffer -> 屏幕
  ```
  完全打通。

### H103y/H103z/H103aa 的状态行

新增：

```text
NATIVE_LEGACY_STATE: load=... stage=... reg=... surface=... probe=... dt=... start=... calls=... pattern=...
```

H103y：

```text
load=0 stage=10 reg=1 surface=0/1 probe=1 dt=1 start=1 calls=0 pattern=1
```

H103z 去掉显式 `registerService()` 与 `IOClass` 后：

```text
load=0 stage=10 reg=1 ... calls=0 pattern=1
```

说明 base `start` 自己会注册服务，显式注册不是必要动作。

H103aa 只设置：

```text
IOClass = IOMobileFramebufferLegacy
```

结果稳定为：

```text
load=0 stage=10 reg=1 surface=0/1 probe=1 dt=1 start=1 calls=1 pid=78 status=0 pattern=1
NATIVE_LEGACY_CLIENTS:
C0 pid=78 calls=0 fails=0 regs=0
```

结论：`IOClass=IOMobileFramebufferLegacy` 能稳定让 userland 找到并打开服务。

### H103ab：禁用 IOMFB loader jobs（失败）

payload 在 `sheng-disable-jobs` 中加入：

```text
com.apple.iomfb_fdr_loader
com.apple.iomfb_bics_daemon
```

结果：

- panic：
  ```text
  sheng watchdog timeout failed: 222
  ```
- 不能同时禁用这两个 job；该对照作废。

### H103ac：sheng-vsync=120（失败）

H103aa 同内核，payload 加：

```text
sheng-vsync=120
```

结果：

```text
display calls=0 pid=0 status=ffffffff pattern=1
```

- `IOMFBDisplayRefresh`/vsync 不是当前阻塞点；
- 该参数反而改变启动时序，使显示客户端不再打开；
- 回到 H103aa 配置。

### H103ad：恢复 H103aa 基线

无 `sheng-vsync`，保持 `IOClass=IOMobileFramebufferLegacy`、`cpus=1`。

结果：

```text
display calls=1 pid=70 status=0
NATIVE_LEGACY_CLIENTS:
C0 pid=70 calls=0 fails=0 regs=0
```

同时 UFS caller 可见：

```text
caller=SpringBoard/27
caller=backboardd/55
```

说明：

- `SpringBoard/27` 和 `backboardd/55` 都活着；
- 但打开显示的是 **pid 70**，不是 backboardd/55；
- pid 70 很可能是 `IOMFB_FOR_Loader`；
- 该客户端打开后没有发起任何 selector（`C0 calls=0`）；
- backboardd 可能被 loader 挡住，尚未自己打开显示。

### 当前基线

```text
kernel  b6e6653c44b1fce84534b6cf7186a3748411d096d6d05e5fabd2e949d95b8d8e
payload 965999e770257c244f1db83a97efc8b91ff8d8398b203de95743f1bb81fc9948
boot    7c0032f0994fc215aa9963de5e73b5c9d47a564514c86706eb37499ec309b2b9
cpus    1
IOClass IOMobileFramebufferLegacy
```

### 下一步 H103ae

H103aa 同内核，只禁用：

```text
com.apple.iomfb_fdr_loader
```

保留 `com.apple.iomfb_bics_daemon`，观察：

- `calls=1` 的 pid 是否从 70 变成 55（backboardd）；
- `C0 calls` 是否开始增长；
- 是否出现 `swap/xfer`。

## 40. H103ae–H103af：IOMFB loader 与客户端身份（2026-11-02）

### H103ae：只禁用 iomfb_fdr_loader（失败）

H103aa 同内核，payload 在 `sheng-disable-jobs` 中只加入：

```text
com.apple.iomfb_fdr_loader
```

保留 `com.apple.iomfb_bics_daemon`。

结果仍然 panic：

```text
panic(cpu 0 caller ...): sheng watchdog timeout failed: 222
  @kernel_exec.c:...
Hardware strut ... initialized
```

结论：

- 不能禁用 `com.apple.iomfb_fdr_loader`；
- H103ab 同时禁用 fdr_loader 与 bics_daemon 的 panic 不是叠加问题，单独禁用 fdr_loader 也会触发；
- 该 job 是启动必需路径的一部分，不能通过 disable-jobs 绕过。

产物：

```text
kernel  b6e6653c44b1fce84534b6cf7186a3748411d096d6d05e5fabd2e949d95b8d8e
payload b165da287833646a0ae26c7bfac28e18b62e5c55bfa31d741ce9bf332fbab600
boot    0b421b37b4e453245f5277f877aa0dc176339e5b11bbedbe94946557a690f113
```

### H103af：客户端进程名诊断

在 H103aa/H103ad 基线上增加：

- `native_legacy_client_comm[64]`；
- `native_legacy_client_enter` 通过 `proc_name(pid,...)` 记录客户端进程名；
- `NATIVE_LEGACY_STATE` 增加 `comm=...`；
- `NATIVE_LEGACY_CLIENTS` 的 `C0 ... comm=...`。

配置保持：

```text
cpus=1
IOClass=IOMobileFramebufferLegacy
无 sheng-vsync
不修改 sheng-disable-jobs 的 IOMFB 项
```

产物：

```text
kernel  a90a4190970e8f33c81afa027e1bad68939ccb68e84502e1d9d148eecbf77234
payload 454d37fd201bc8ad9fad883978d0ba9086260c85fe45474b14d7a6ac7a37afd4
boot    221ec5e155fa480ed1087eb9e03e45aa031e1289779acbba38da881f70074986
```

Windows 路径：

```text
D:\Users\ls\Documents\OnePlus5_ios\boot-H103af-comm.img
```

### 当前判断

- H103aa/H103ad 已证明显示后端工作：
  ```text
  load=0 stage=10 reg=1 start=1 calls=1 pattern=1
  ```
- 客户端能稳定打开（`calls=1`），但 `C0 calls=0`，从未发起 selector。
- H103ad 中客户端 pid 为 70，而 `backboardd` 是 55、`SpringBoard` 是 27。
- H103af 用 `comm=` 确认 pid 70 的真实身份。
- 若确认是 `IOMFB_FOR_Loader`，下一步不能禁 job，只能考虑：
  - 只拒绝该 loader 的显示 user client（按 comm/pid），让 backboardd 接手；
  - 或提供 loader 期望的显示固件路径；
  - 或延迟/绕过 loader，而不触发 watchdog。

## 41. Userdata 一分为二：Android 64 GiB + iOS 49.2 GiB（2026-11-02）

### 分区前审计

临时启动 TWRP（未刷入 recovery）：

```text
fastboot boot twrp.img
```

GPT 关键信息：

```text
UFS LUN0: 119,054,336 KiB ≈ 113.2 GiB
logical sector: 4096 bytes
userdata: /dev/block/sda13
start LBA: 0x14f40
end LBA:   0x1c627fa
size:      29,677,755 sectors ≈ 113.2 GiB
```

原始 GPT 已备份到 Windows：

```text
D:\Users\ls\Documents\OnePlus5_ios\gpt-primary.bin
D:\Users\ls\Documents\OnePlus5_ios\gpt-backup-full.bin
```

### 新 GPT

```text
userdata       Android   0x14f40  .. 0x1014f3f   64.0 GiB
userdata_ios   iOS       0x1014f40 .. 0x1c627fa   49.2 GiB
```

- 新 `userdata_ios` 类型设置为 Apple APFS；
- primary/backup GPT 的 entries CRC、header CRC 均重新计算并读回校验一致；
- 通过 TWRP `dd` 写回 `/dev/block/sda`；
- 重启 TWRP 后内核识别新分区。

确认：

```text
/dev/block/by-name/userdata      -> /dev/block/sda13
/dev/block/by-name/userdata_ios  -> /dev/block/sda14

blockdev --getsize64 userdata      = 68719476736   # 64 GiB
blockdev --getsize64 userdata_ios  = 52840607744   # 49.2 GiB
```

### Android userdata

Android 的 64 GiB `userdata` 已重新格式化为 ext4：

```text
Filesystem UUID: 33c9e7ae-b978-430c-900a-a10074a9f0dc
16777216 个 4K block
```

重启后 **Android 成功进入系统**。

现在：

- Android 使用标准 `userdata`；
- Android 的 `fastboot -w` / recovery 只影响 Android 的 64 GiB；
- iOS 的 49.2 GiB 保留为 `userdata_ios`，暂未格式化 APFS；
- H103 当前 iOS Data 仍使用 payload 中的 RAM seed（`XNU_OWNER_DATA_VOLATILE=1`），不依赖 `userdata`。

### 待验证

- 分区后 H103 iOS 是否仍能启动；
- 如果 `RootLayout`/`NativeUfsWarm` 仍硬编码 `userdata`，需要改成优先 `userdata_ios` 或加回退；
- 后续要做 iOS 持久化 Data 时，再在 `userdata_ios` 上创建 APFS container。

## 42. Userdata 拆分的修正：iOS SHNGROOT 恢复到 userdata_ios（2026-11-02）

### 根因

拆分后 H103ad/H103af 都停在：

```text
skip attaching fse to iOS using legacy IO matching ...
UUID 04769D26-2CA0-4825-B443-E2E5F88300F2
```

原因是把 `userdata` 当成了普通 iOS Data 分区。实际上 `userdata` 是
iOS 的 SHNGROOT 容器：

```text
0x000000  manifest
0x100000  OS window
0x16a600000 SystemOS window
```

Android 的 64 GiB `userdata` 格式化后，iOS 的 OS/SystemOS 窗口被覆盖，
所以根 UUID 匹配失败。

### 恢复

用 `unixnu build userdata` 从原 IPSW DMG 重新生成：

```text
OS       6,077,580,800 bytes @ 0x100000
SystemOS 3,303,014,400 bytes @ 0x16a600000
image    9,382,658,048 bytes (8.74 GiB)
```

镜像：

```text
D:\Users\ls\Documents\OnePlus5_ios\userdata-root.img
```

已由用户手动刷入：

```text
fastboot flash userdata_ios userdata-root.img
```

### 代码修改

- `drivers/NativeUfs/RootLayout.h` / tree `scripts/RootLayout.h`：
  ```text
  wanted = "userdata_ios"
  ```
- `drivers/NativeUfsProbe/NativeUfsProbe.cpp`：
  - GPT 扫描时捕获 `userdata_ios` 的 first/last LBA；
  - SHNGROOT manifest 从 `rootFirst` 读取，不再硬编码 `0x14f40`；
  - OS/SystemOS window 的绝对地址改为 `rootFirst * 4096 + offset`。

### H103ag 结果

H103ag 使用新的 UFS probe，`userdata_ios` 上的 SHNGROOT 被识别，iOS 再次启动到：

```text
KextLog: driverkitd is active
```

显示后端状态：

```text
NATIVE_LEGACY_STATE: load=0 stage=10 reg=1 surface=0/1 probe=1 dt=1 start=1 calls=0 pattern=1
```

- 品红色 GOP 自检块正常；
- iOS OS/SystemOS 恢复；
- Android 的 64 GiB `userdata` 未被触碰；
- 本次启动显示客户端 `calls=0`，仍需继续查 backboardd/SpringBoard 的显示连接。

产物：

```text
kernel 3f459752543807b06a2da151799ac6eb984d5188eb771b04ddaf13a24846cbc4
boot   503a0d567ccec5d999b6d9967d044b76a8cd16f4e4b46d8b7064c5ab6be2d359
```

## 43. H103ao–H103at：backboardd 启动确认与 Legacy 显示边界（2026-11-03）

### H103ao：SpringBoard exec 确认

在 `kern_exec` 中对 `SpringBoard` 做目标 panic。

结果：

```text
NATIVE_EXEC: pid=27 ppid=1 comm=SpringBoard
  argv0=/System/Library/CoreServices/SpringBoard.app/SpringBoard
panic: NATIVE_EXEC_TARGET: pid=27 comm=SpringBoard
```

结论：launchd 已经能拉起 SpringBoard。

### H103ap：backboardd exec 确认

只对 `backboardd` 做目标 panic。

结果：

```text
NATIVE_EXEC: pid=55 ppid=1 comm=backboardd
  argv0=/usr/libexec/backboardd
panic: NATIVE_EXEC_TARGET: pid=55 comm=backboardd
```

结论：backboardd 也能被 launchd 拉起。

### H103aq/H103as/H103at：显示打开路径

- H103aq：恢复干净配置，不拒绝 loader，不 panic；
  - 某些启动能到 backboardd；
  - `display calls=0`；
  - 没有 `NATIVE_DISPLAY_OPEN`。
- H103as：改为拒绝真实 loader 名：
  ```text
  IOMFB_FDR_Loader
  ```
  同时 `NativeSandboxGrantProcess=backboardd`；
  - backboardd 已 exec；
  - 仍未出现 `NATIVE_DISPLAY_OPEN`；
  - `display calls=0`。
- H103at：`IOClass=IOMobileFramebuffer`（基类）；
  - backboardd 已 exec；
  - 显示客户端仍是：
    ```text
    calls=1 pid=78 comm=IOMFB_FDR_Loader status=e00002c7
    ```
  - `status=e00002c7` 是拒绝 loader 返回的错误；
  - backboardd 仍然没有打开显示。

### 结论

Legacy framebuffer 后端已经完成：

```text
load=0 stage=10 reg=1 surface=0/1 probe=1 dt=1 start=1 pattern=1
```

GOP 自检色块可见，说明：

```text
IOMobileFramebuffer -> GOP -> 屏幕
```

完全打通。

但：

```text
backboardd 已经启动
却没有调用 IOServiceOpen 打开 Legacy display
```

因此继续调以下内容没有意义：

- `IOClass`
- `IOProviderClass`
- `NativeSandboxGrantProcess`
- `IOMFB_FDR_Loader` 拒绝
- `newUserClient`

下一步转向：

```text
backboardd / CoreAnimation / IOAccelerator / IOGPU / Metal
```

最可能的情况是 backboardd/CoreAnimation 进入 headless 模式，等待 GPU/Metal 设备。

### 产物

```text
H103ao kernel b974cebd86409f471c94071ce50cc8c1ccbd5906dd39e4393981ec6a61f0a542
H103ao boot   6463b0aead15c1d4edb0f4e101971627af2ce32a1f6d50f7ca70f07f1573ac4d

H103ap kernel 725edf18a32c0e1b2ece243ad0c16c08bd728ce571fc2e14aea3ea1ed147feff
H103ap boot   23dfa2b0d0169e93ae67873663f437fa097cc7e1ca6d0c9ef7840715457992e5

H103aq kernel df417f413bfeae02e5fd9b627342d7670adc1d7ff15437d14baf616db98ae5d1
H103aq boot   1e75019ea0a27d731947b826242431692eeeef5ff5aceaabcbf13096ad094f76

H103as kernel 37bf0159ca93fad2e538312ec6192966d46a533ef4f56b30e71f8d3de8854a50
H103as boot   96688b26148d912a238ac43328a39c7ae7567b792cd9cfd524b2b3035e114784

H103at kernel c93b972ce48207ae941b57bb3476e59cc456f1081934fdd723e275113de9ac69
H103at boot   9e363bef3ee556dd1a3dc6e61509612a10459c09f823592d67acc5908ddf6e43

## 44. H103au–H103bg：启动随机性、Data/内存/AMFI 对照与颜色状态面板（2026-11-03）

本轮把 H103at 之后的失败从“显示后端”进一步拆成三类，并加入了不依赖
滚屏日志的右上角颜色状态面板。所有镜像仍使用同一台 OnePlus 5、同一份
21H461 iPad7,1 OS/SystemOS 和 `userdata_ios` SHNGROOT；未修改 Android
`userdata`、AuthAPFS/Image4/TrustCache 验证或原始 userland。

### 44.1 H103au：client probe 对照

- 变量：H103at 内核不变，payload 仅追加
  `offline-mobile-graphics-client=1`。
- 结果：`display calls=0`、`pid=0`、`comm=`；backboardd 已 exec 但未
  打开显示。
- 结论：client probe 不能替代 backboardd 的显示初始化。

产物：

```text
H103au boot 2a263cce4b0ed4fdb7c35ef0e0ae35d39d36ebeef9143b9061865adac1f56288
```

### 44.2 H103av：心跳线程与 cpus=1/2 对照

- 在 NativeUfsProbe 中加入独立 `NATIVE_ALIVE` 线程，使用同一 H103at
  内核构造 cpus=1 与 cpus=2 两个 payload。
- cpus=1/2 都能到 `driverkitd is active`，但屏幕没有 `NATIVE_ALIVE`；
  不能再用“缺少心跳”证明内核死亡。
- 之后 H103aw 进一步加入 `NATIVE_UFS_THREAD: alive rc=...` 和
  `heartbeat rc=...`，确认线程创建路径必须单独记录；屏幕上仍未稳定
  显示这两行，说明心跳线程的启动/调度本身还需要独立诊断。

产物：

```text
H103av cpus1 payload efa95f92b33029365d5dae5d9149573e49f4ad9ccc2b97639e7044fd76742fba
H103av cpus2 payload 536247d449ea3e047e174fcac11265d0d6dea8519fc5e7142d292c1a885fb13c
H103av cpus1 boot    b59bfe2682691d6f03378a12cdb769a97c6fa94acc15a42fbe140a3b471cf2ed
H103av cpus2 boot    07886c18c0ccfd406573b8108fd6315c99c07272b65a33bd15f934ad2cd647a4
```

### 44.3 H103ax-1g：Data seed 1 GiB 对照

- 变量：H103aw 内核不变，Data seed 从 512 MiB 扩到 1 GiB，UUID
  `1A4CE9DF-34B6-4B52-9744-5052A9D20B23` 保持不变。
- 3 次启动仍有不同前沿：
  - 2 次 `calls=0`，最后是 `logd_helper/83` / `driverkitd`；
  - 1 次 `calls=1`，`IOMFB_FDR_Loader` 打开显示；
  - 未观测到 ENOSPC。
- 结论：1 GiB Data 不能单独消除 run-to-run 差异；Data 容量不是唯一原因。

产物：

```text
H103ax-1g kernel  a476ac6839e9ef93b3c4129a570ac19e22f2841ea849375ec125982fc9faf2ac
H103ax-1g payload f4a18517888c77fcf49fa4ee95edc008a00e93dab6a7d424f9346613d3f826b1
H103ax-1g boot    73cf3927771e3191f38ae8cf89daaf10a883e3d35ecdd9ef4780699c0297f84e
```

### 44.4 H103ay-4g：4 GiB owned memory 对照

- 变量：Data 仍为 1 GiB；`owned_memory_size` 从 `0x40000000`（实际
  1 GiB）改为 `0x100000000`（4 GiB）。注意 board.toml 原注释写 4 GiB，
  但值实际只有 1 GiB。
- 结果：
  - 1 次 `calls=0`，trustcache 循环，`driverkitd`；
  - 1 次 `calls=1`，出现 `backboardd/55`、`SpringBoard`、
    `DataMigrator`/`IMDPersistence`；
  - 1 次 `calls=0`，`eligibilityd`/`driverkitd`；
  - 仍无 ENOSPC。
- 结论：4 GiB 能让个别 boot 多走一段，但不能稳定让 backboardd
  打开 Legacy display。

产物：

```text
H103ay-4g payload 06daedf1f5246fe66beeebcf06faee265b4a5f6b2e1dfc8b464d912b8fe2c195
H103ay-4g boot    f148919d96db01302a53d72d6061445a89cfe652a9ca33fdc14f61a1ba41cd3e
```

### 44.5 H103az：AMFI gate 一次性 NOP（仅构建，未单独判定）

- 在 H103ay 内核的 AMFI 拒绝分支把
  `VM 0xfffffff00aab73b8` 的 `0x360010a0`（`tbz`）改为
  `0xd503201f`（`nop`），只跳过
  `com.apple.private.amfi.can-check-trust-cache` 权限门。
- 这是受控诊断，不是默认策略；后续 H103be 将该绕过与颜色面板一起上机。

产物：

```text
H103az kernel  8cf5f2e90000eff100f5672b17237829fcef5c38350b5a6b92af3423bee7153d
H103az payload 75ab9dcf96ff00b93c0982ac249360f92dba1bf12b53ce401a2a96a8c09969f4
H103az boot    3bb5b2bebe792d0b45ba9823d1e7bbc7adb78ca7adb040d47f63723e327990c5
```

### 44.6 H103ba–H103bd：右上角颜色状态面板

为避开滚屏日志，在 `NativeLegacyDisplay::drawTestPattern()` 把原来的
纯品红方块改成右上角 2×2 面板，由 UFS 心跳每 10 秒重绘：

- 左上：用户态前沿 / 显示阶段；
- 右上：显示客户端；
- 左下：client calls 计数；
- 右下：swap/transfer；
- 右下角另有 16×16 心跳闪烁块。

H103bd 的最终颜色语义：

```text
左上：
  红   还没有关键进程 / 早期
  黄   只有 logd_helper
  橙   只有 driverkitd
  青   只有 backboardd
  绿   SpringBoard 启动、没有 backboardd
  白   SpringBoard + backboardd 都启动
  紫   SpringBoard 已退出
  品红 backboardd 已退出

右上：
  黑   没有 client
  黄   IOMFB_FDR_Loader
  青   backboardd
  紫   其他 client

左下：黑 0；蓝 1–9；绿 10–99；橙 ≥100
右下：黑 无；紫 有 swap validation；白 有 transfer
```

上机结果：

- H103ba（2×2 初版，左上仅表示 display 后端）：3 次都只有左上绿，
  后代仍无显示客户端。
- H103bb（左上加入 logd_helper/driverkitd/backboardd/SpringBoard 位）：
  4 次中 1 次左上绿 + 右上黄 + 左下蓝，其余只有左上绿。
- H103bc（左上白色表示 SpringBoard+backboardd）：3 次都只有左上绿，
  说明这 3 次 backboardd 根本没有 exec。
- H103bd（加入 SpringBoard/backboardd 退出标志）：2 次只有左上绿；
  1 次左上白、右上黄、左下蓝。白色那次 `backboardd/55` 和
  `SpringBoard/27` 都在，但显示客户端仍只有 FDR loader；等待 10 分钟
  颜色不变。
- 结论：`backboardd` 启动本身有 run-to-run 差异；即使启动，也不会调用
  Legacy display 的 `newUserClient`。

产物：

```text
H103ba kernel  aaac1722f29b6ad38df7f1b0ebe12e09a70340e8aaadb62b76fc14f207028428
H103ba payload 048dd55afa428fdb1d3ccad933957490c7f7ee4c1feb57bdbe6916d58ade2652
H103ba boot    3195072d616d9be0411d73903c6468b9d6aac40423c3d92c342ad807cd8190f2

H103bb kernel  11e9655709e8dde6fe4fc3bf731d308776b7ac3841709281eb7f8db3c8086bb7
H103bb payload b67a54036d8891bab32ea421b59e275196aa46cda938c22d907469d8c267da36
H103bb boot    d9b91fc6a29ecb90822da84c31923539b5160b57927ccd1cc60cd24e0b1b2130

H103bc kernel  060689dc87083eafd3c10127bc569ae079bfadeb47dadae5e497a11578404d9b
H103bc payload ebfda045e4e44192fe590bb244576be7d9b37bc796e0671005815215fe23b948
H103bc boot    e5349527c74df987e5e21bcd670febe7be8eac41260a9556e719c34a458a42c6

H103bd kernel  51cffbc25e890be9a8d4b9ca44ca7e1895197ed89cced9e6edb6c865c6664c66
H103bd payload 29ef1f470870fca6061863a31a151bd56bc44e8467a89f8709a79425b378ccce
H103bd boot    8284f2616412cea7e98cdb9d929802b4b2cdd6bb7b8af536210a38c08c9910f3
```

### 44.7 H103be：AMFI gate NOP + 颜色面板

- 变量：H103bd 内核的 AMFI 权限门 NOP；其他与 H103bd 相同。
- 3 次结果：1 次左上白、右上黄、左下蓝；另外 2 次只有左上绿。
- 右上始终没有青色，说明 AMFI gate NOP 没有让 backboardd 打开显示。
- 结论：AMFI/trustcache 权限门不是 backboardd 不 open 的根因；H103be
  的 `Only allowed processes...` 循环消失，但显示客户端仍然只有 FDR
  loader。

产物：

```text
H103be kernel  ee38baaf27e395420b78eb9e43f95a89290a11b42ec5f1d8974e190d3f26c535
H103be payload 8fc8cc373aa7d923ed6a8d9508d507c78dc91ada7a512f1887db7dc234ad9d26
H103be boot    6ce2a1e2584055903edcb383432da9cc6eb478e7f44b21ec3e5059db7a4694ae
```

### 44.8 H103bf：DinnerABC 显示参数 parity

- 只改 payload，追加：
  `offline-mobile-graphics-client=1`、
  `offline-legacy-cpu-present=1`、
  `offline-legacy-unit-scale=2`、
  `sheng-vsync=60`、`sheng-vsync-fixed=1`。
- 3 次结果仍为 1 次左上白、2 次左上绿；右上没有青色。
- 结论：DinnerABC 的 CPU display 参数不能单独让本项目 backboardd 打开
  display；服务注册/display provider 差异仍需处理。

产物：

```text
H103bf kernel  51cffbc25e890be9a8d4b9ca44ca7e1895197ed89cced9e6edb6c865c6664c66
H103bf payload 1e2cb3e4b9c65903d3ac2389216e3b95c072d4ffead84b814369029aaf376a15
H103bf boot    768f8eb8c01995df59d6cd8eb24d7080d4dd29d0e41400bd2857193f6262aced
```

### 44.9 H103bg：BackBoard/CoreAnimation 软件渲染偏好

- 在 1 GiB Data seed 的 mobile/root `Library/Preferences` 中写入：
  `CAEnableDeepFramebuffer=false`、
  `CAEnableFramebufferCompression=false`、
  `CAEnableIOSurfaceCompression=false`、
  `CAForceSoftwareRendering=true`。
- 结果：右上仍无青色；backboardd 仍未打开 Legacy display。
- 结论：这组软件渲染偏好不足以把 backboardd 从 headless 状态拉回来。

产物：

```text
H103bg kernel  51cffbc25e890be9a8d4b9ca44ca7e1895197ed89cced9e6edb6c865c6664c66
H103bg payload 437a54dd94e52ed8104e96d7e7aaefe1f4673c307ca45ae8ec3dbc51ef4d78dd
H103bg boot    ae9c39268b5cd4e49ee1dcf4cdbb0e933b673ea63c4016995ab23fd50677e0a6
```

### 44.10 只读分析：backboardd 进入 headless 的路径

对 `/tmp/opencode/os-mnt/usr/libexec/backboardd` 做只读字符串/导入分析：

- 导入 `IOMobileFramebuffer`、`Metal`、`IOSurface`；
- 有 `BKDisplayStartWindowServer`、`BKDisplayIsHeadless`、
  `StartWindowServer: headless (display:%d/server:%d)`、
  `IOServiceOpen failed for class ...`；
- 使用 `CADisplay` / `CAWindowServerDisplay` / `CAContext`；
- 不能从日志证明它已经到达 `IOMobileFramebufferOpen`。

因此当前最符合证据的解释是：

```text
Legacy framebuffer 后端正常
  -> FDR loader 能打开
  -> backboardd 不把它当作可用 CADisplay/display provider
  -> BKDisplayStartWindowServer 走 headless
```

这不是继续调整 `newUserClient`、`IOClass`、`NativeSandboxGrantProcess`
或 TrustCache 能解决的问题。

### 44.11 当前结论与下一步

已排除的低成本变量：

- Data 512 MiB/1 GiB、4 GiB owned memory；
- AMFI selector 0x5f 权限门；
- `offline-mobile-graphics-client`；
- `offline-legacy-cpu-present`、`sheng-vsync`、`unit-scale`；
- Legacy `newUserClient` 拒绝路径；
- BackBoard/CoreAnimation 软件渲染偏好。

下一步只剩两条路线：

1. **移植 DinnerABC 的 CPU display provider/注册路径**，重点对比
   `package/BoardRuntime/LegacyDisplayProbe.cpp`、
   `NativeLegacyDisplay.cpp` 与 `NativeMobileDisplay` 的 service 注册、
   IORegistry 属性和 `CADisplay` 提供方式；DinnerABC 曾在 CPU 路径
   达到 `backboardd calls=77/97`。
2. 如果 provider 路径仍 headless，则提供 **IOAccelerator/IOGPU/Metal**
   服务，或走 QcomGPU A540 路线。

不再继续增加 boot-arg、`sheng-disable-jobs`、Data 容量或 AMFI 诊断。

## 45. A 线：H103cg provider 对齐计划（2026-11-04）

H103cg 仍是唯一接受的稳定基线：

```text
NATIVE_LEGACY_STATE:
  load=0 stage=10 reg=1 surface=0/1 probe=1 dt=1 start=1 calls=0 pattern=1
boot: 4560ac5b64662aa321348d530617894ef85bf27252eae04396f8a2048b1cea8a
```

A 只读对照（sagit / HackiOS / DinnerABC）结论：

- `sagit` 的 iOS 18 显示路径依赖物理 DPU 节点、`device_type=display-subsystem`、
  `canvas-width/height` 和 `registerService()` 前的完整 display 属性；
- `HackiOS` 显式发布 `TimingElements`/`ColorElements`、`/arm-io` 显示节点
  和空 `IOAcceleratorES`；
- `DinnerABC` 与 H103cg 同 OS，但 **不设置** `IOClass`、
  `NativeSandboxGrantProcess`、`IOFBDependentID`；H103at 已排除
  `IOClass`/`NativeSandboxGrantProcess`，`IOFBDependentID` 仍未单独验证；
- H103cg **没有发布 `IOAcceleratorES`**：`native_a540_accelerator_probe()`
  有定义但全树无调用点，`native_a540_accel_state` 为 0；
- H103cg 服务上几乎只有 `IOMFB Debug Info` + `IOFBDependentID`，
  没有 sagit 的 `DisplayWidth/Height`、`RowBytes`、`IOMFBDisplayRefresh`
  等属性。

执行顺序：

1. **A1**：发布最小裸 `IOAcceleratorES`（不设置 `MetalPluginName`/
   `MetalPluginClassName`），单变量验证 headless 是否由 accelerator 缺失导致；
2. **A2**：A1 不足时补最小 display 属性，不改 timing；
3. **A3**：仍不足时才做 `IOFBDependentID=0` / 去掉
   `NativeSandboxGrantProcess` / `IOClass` override；
4. **A4**：最后才补父节点 `compatible`/`canvas-width/height`。

完整差异表、验收标准和回退规则见
[A-provider-parity-plan-2026-11-04.md](A-provider-parity-plan-2026-11-04.md)。

下一步：A1。任何 display archive 改动仍可能触发 Data/APFS IOMedia race；
若停在 `Waiting on IOMedia UUID 04769D26-...`，记录后回退，不据此判定
provider 失败。

## 46. A1 结果：pre-root 裸 accelerator 不可行（2026-11-04）

候选 `boot-H103cw-a1.img`：

```text
boot:    43f831fb07fe5ad9f639a4147a26137d51f7972cb7fb74c4041639422245e28c
kernel:  4950bfa6c93a248f3e584b05f60e93705c0603f9eb366827004f8fcedaa99d19
payload: 3ac218e47edc83a80d2e746ea8ff75e320d6930c1826f7772eada4a925e82342
```

上机 panic：

```text
NATIVE_LEGACY: late probe enter
Can't load kext com.apple.iokit.IOGPUFamily - requests to user space are disabled.
OSMetaClass::preModLoad() wasn't called for class NativeA540AcceleratorProbe
```

原因：

- `NativeA540AcceleratorProbe` 的
  `OSKextLoadKextWithIdentifier("com.apple.iokit.IOGPUFamily")` 返回值
  判断写反，失败后继续 `static_init()`；
- pre-root late probe 阶段无法加载 `IOGPUFamily`，原始
  `IOAcceleratorES` 基类不可用。

结论：A1（pre-root 裸 `IOAcceleratorES`）不可行；A540 源码已回退，
H103cg 仍是唯一稳定基线。后续二选一：

1. **A2**：最小 display 属性（不依赖 IOGPUFamily）；
2. **A1b**：把 `IOGPUFamily` 放进 prelink roots，或 post-root publication
   （改变 prelink 布局/时序，风险更高，暂不执行）。

详见 [A-provider-parity-plan-2026-11-04.md](A-provider-parity-plan-2026-11-04.md)。

## 47. A2 结果：display 属性发布，但 archive 增大触发 root race（2026-11-04）

候选 `boot-H103cx-a2.img`：

```text
boot:    571d77b74176a89c60f773bca36b364ec90172b782ce142cb948360a79cbc822
kernel:  4fbd7673243bc9aae455017d7d8258a6dcb37d028808ce26343a9849689c526c
payload: 9a6efa2eb7cd371941b225590a9901c6c8ba9240204e49d7545356317732cf53
```

上机：

```text
NATIVE_LEGACY: display properties 1080x1920 row=4320
NATIVE_LEGACY: registerService object=...
NATIVE_LEGACY: base start ok primary=1 ...
NATIVE_LEGACY: phase=4 dt=1 probe=1 attach=1 start=1 reg=1

Waiting on <dict ... IOProviderClass=IOMedia ... UUID=04769D26-...>
```

结论：A2 属性已在服务上发布，但 Legacy archive 变大再次触发 Data/APFS
IOMedia 发布 race；未到 backboardd，`calls` 无法评估。A2 镜像不可用，
H103cg 保持。

下一步 A2c：保留 A2 属性，移除未使用的 A540 对象和 `drawTestPattern()`
里的 accel 引用，改用 5 成员 builder，把 Legacy archive 缩到
layout-sensitive 阈值以下，再评估 `calls`。若仍 root wait，则不是单纯
archive size，转向 runtime property injection 或修复 race。

## 48. A2/A2c 停止：边界恢复（2026-11-04）

用户指出 A2/A2c 违反了“不再做方块/灰条/display 时序/ordering 实验”的
边界：

- A2 修改了 display 属性和 `IOMFBDisplayRefresh`；
- A2c 移除了 `drawTestPattern()` 的 accel 方块，并改变 Legacy archive
  成员；
- 两者都属于 display archive/诊断实验，不属于已接受的 H103cg 基线。

已恢复：

- `NativeLegacyDisplay.cpp`、`LegacyDisplayProbe.cpp`、
  `NativeA540AcceleratorProbe.cpp` 回到 H103cg；
- macOS 源和 `scripts/build-op5-legacy-display.py` 回到 7 成员 builder；
- A1/A2/A2c 镜像均不使用；H103cg 是唯一稳定基线。

后续除用户明确要求外，不再做 display archive、方块/灰条、display
timing 或 ordering 实验。

## 49. H103cg-1：仅移动三个 fill 坐标仍 root wait（2026-11-04）

候选 `boot-H103cg-1.img`（boot `e1fb98d4...`、kernel `7edeaf8e...`、
payload `105c0c08...`）：

- 基线为 H103cg `5f29dde`；`LegacyDisplayProbe.cpp`/`NativeA540...`
  与 H103cg 完全一致；builder 为 H103cg 的 7 成员版本；
- 唯一源码差异是 `NativeLegacyDisplay.cpp` 中三个 16×16 指示块的坐标：
  ```text
  fill(w-16,h-16) -> fill(8,8)
  fill(w-40,h-16) -> fill(32,8)
  fill(w-64,h-16) -> fill(56,8)
  ```

上机仍然停在：

```text
Waiting on <dict ... IOProviderClass=IOMedia ... UUID=04769D26-...>
```

结论：即使只改三个坐标常量，display archive 的二进制/布局变化仍会触发
Data/APFS IOMedia 发布 race。H103cg exact 是唯一稳定点。源码已回退到
H103cg；`boot-H103cg-1.img` 不使用。

指示块不能通过“改 display archive 再重编”来移动。后续如果还要移动，
只能从 display archive 外部做覆盖/绘制，或先修复 Data/APFS race。

## 50. H103cg-2/H103cg-3 对照：源码可重复，二进制不可重复（2026-11-04）

对照：

| 包 | 内容 | boot | 结果 |
| --- | --- | --- | --- |
| H103cg-2 | H103cg 原镜像逐字节拷贝 | `4560ac5b...` | 可用 |
| H103cg-3 | H103cg 同源码 clean rebuild | `d9e3322b...` | 停在 `IOMedia UUID 04769D26` |

H103cg-3 的源码与 H103cg 完全一致（submodule `5f29dde`，
`NativeLegacyDisplay`/`LegacyDisplayProbe`/`NativeA540` 哈希一致，
7 成员 builder），但构建输出不同：

```text
              H103cg 原版      H103cg-3
kernel        7b5d4ae1...      fe155269...
ADT           d98d9522...      158ebdb6...
payload       a12f5fc9...      9d8fb9b7...
boot          4560ac5b...      d9e3322b...
```

结论：

- H103cg 的**源码逻辑**可重复，但**二进制不可重复**；
- ADT/kernel 构建期差异会改变精确布局/时序，足以触发 Data/APFS
  IOMedia 发布 race；
- H103cg 原二进制是唯一稳定点；H103cg-2 是它的逐字节拷贝，可用；
- H103cg-3 不使用；不再把“同源码重编译”当作无改动包。

后续若要改显示行为，只能从 display archive 外部做覆盖/运行时注入，
或先修复 Data/APFS race；不能再通过重编 display archive/kernel 实现。

## 51. H103cg-6：重编译可稳定过 root（2026-11-04）

候选 `boot-H103cg-6.img`：

```text
boot:    1201d68379dedd8f08a3a01cdadccde9caf6009b9304e2dae5f4a8f410a4ac7f
kernel:  76634aa5e4104d97b53526dfa0d33b212846a959951525fc31935dfc52982e6e
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: c9f841e6f7612bd58dc3e96eb1227a5a165f540f8eca8aea6251dcf62911fdb6
```

结果：**通过 root，可用**。

根因：macOS 构建树里的 `NativeUfsProbe.cpp` 仍是旧 Android 逻辑：

- GPT 选择 `"userdata"`，不是 `"userdata_ios"`；
- root manifest 和 OS/SystemOS window 的绝对地址硬编码 `0x14f40 * 4096`。

H103cg 原版 probe 是：

- GPT 查找 `userdata_ios` 的 first LBA；
- manifest 从该 first LBA 读取；
- window 绝对地址 = `rootFirst * 4096 + rootOffset`。

H103cg-6 的两处修复：

```text
1) GPT 分区选择/日志改为 userdata_ios，rootFirst/rootLast 从 GPT 取；
2) window absolute 从 0x14f40*4096 改为 rootFirst*4096。
```

H103cg-5 只修了第 1 处，window 仍指向 Android `userdata`，所以仍停在
`04769D26`；H103cg-6 修了第 2 处后通过。

结论：

- 重编译内容可以稳定过 root；H103cg-6 是可用重编译基线；
- H103cg-2（原镜像逐字节拷贝）仍是原版可用对照；
- 之前 H103cg-3/4/5 的 `04769D26` 是 probe 分区/window 错误，不是
  display archive 或 kernel 时序；
- display provider 仍是 `calls=0`，无 UI；本次没有移动心跳指示块；
- 后续若移动指示块，可以直接在 H103cg-6 的 probe 修复基础上重编，
  不再受 `04769D26` 阻塞。

## 52. H103da：H103cg-6 + 三个心跳块移到左上角（2026-11-04）

候选 `boot-H103da.img`：

```text
boot:    997f5cd88d42fbbe4c8f0f8bd8d4abf42b3b6aa74c4f4ab044c446a9316c7a53
kernel:  f8a238140fdaf0ee0082e4c77ed7389c6b50efa536230a7e16762a468ee1d6c3
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 9ebfe2ec3dbc7ae578d7683d376a3b4e9b583268690e8566dfed6b053ec1944e
```

基线是 H103cg-6（`userdata_ios` probe + window 修复），display 只改三个
16×16 指示块坐标：

```text
fill(w-16,h-16) -> fill(8,8)
fill(w-40,h-16) -> fill(32,8)
fill(w-64,h-16) -> fill(56,8)
```

其他 display archive、timing、ordering、boot 参数均未改。ADT 与 H103cg
完全一致（`d98d9522...`）。

上机结果：**root 通过，`calls=0`，左上角三个指示块没有出现**。

原因：当前 `NativeUfsProbe` 的 heartbeat 没有调用
`native_legacy_test_pattern()`。H103cg 原镜像的 probe 有周期重绘调用；
clean rebuild 的 probe archive 丢失了该调用，因此 `drawTestPattern()`
从未执行。H103da 只是把三个 `fill()` 坐标编译进 archive，并没有改变
“谁来画”。

下一步 H103db：在 UFS heartbeat 恢复
`native_legacy_test_pattern()` 调用，让左上角三个块周期性重绘；root
修复（H103cg-6）保持不变。display provider 仍是 `calls=0`，UI 仍未出现。

## 53. H103db：恢复 heartbeat 周期重绘（2026-11-04）

候选 `boot-H103db.img`：

```text
boot:    efc4bc2fbb5bc6721982046cc9b837b8182af55f4ee409b5035c8110e0849f21
kernel:  d559aef221fbf554db6994e75d609dffb49d9e5d730596feabfec99bed0f8713
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 3d0a464f0b082d5d413f2193aa89c95fa809f499febb5fd450d31c2e3a239d51
```

基线 H103da。`NativeUfsProbe` 的 heartbeat 每 10 秒调用
`native_legacy_test_pattern()`（weak import，display archive 提供实现），
恢复 H103cg 原 probe 的周期重绘。display archive 仍是 H103da 的左上角
三个块，root 修复（H103cg-6）不变。

上机：**右上角和左上角都没有方块**。用 H103cg 原 kernel 反汇编确认原
heartbeat 顺序是：

```text
IOLog(...)  ->  native_legacy_test_pattern()
```

H103db 把调用放在 `IOLog` 之前，heartbeat 日志又把图案盖掉；因此不是
坐标问题，是绘制顺序问题。H103dc 把调用移到 `IOLog` 之后。

## 54. H103dc：把 test pattern 调用移到 IOLog 之后（2026-11-04）

候选 `boot-H103dc.img`：

```text
boot:    909bb8998f5f9c06e3a1ab5e43fb404673560e82ced026c072e45c70cd1ab5f5
kernel:  1c1032a4dfad07a3cc0331c5cb4b5bb561923e4378f06a374b79f0952910462f
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 5caa2c9ceb4461fbec201d337eddaca1394d88629cadd440bb2e5327ced060a9
```

H103cg 原 `heartbeatThread` 反汇编：

```text
fffffff0079b17d4  bl _IOLog
fffffff0079b17d8  bl _native_legacy_test_pattern
```

H103dc 按这个顺序：

```text
IOLog(NATIVE_UFS_ALIVE...)
native_legacy_test_pattern()
```

display archive 仍是 H103da 的左上角三个块，root 修复不变。

上机：**仍然没有方块**。H103cg 原 heartbeat 是直接
`bl _native_legacy_test_pattern`；H103dc 用的是
`weak_import` + `if (symbol)`，weak 符号在 kernel link 里绑定为空，
整段调用被跳过。H103dd 去掉 weak，改为和原代码一样的直接调用。

## 55. H103dd：直接调用 test pattern（2026-11-04）

候选 `boot-H103dd.img`：

```text
boot:    571b00917dceb81f478e59ce070bf278311775af739f174f858a8ae563b5f4ff
kernel:  971f37ee5330129b116e315c01ff678aeed00f0d9647fbe42160376019462c9c
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 310053dbc060c32d5c20ac13ce9edbe24a616ab888e71d0037b19f4aaeb02335
```

H103dd 的 `heartbeatThread` 反汇编已确认是：

```text
fffffff0079b1640  bl _IOLog
fffffff0079b1644  bl _native_legacy_test_pattern
```

与 H103cg 原 kernel 的 `IOLog -> native_legacy_test_pattern` 直接调用一致。
display archive 仍是 H103da 的左上角三个块；root 修复不变。结果待上机；
预期右上 2×2 和左上三个块可见；`calls=0` 不变。

## 56. H103de：sheng-log 持久化日志快照（2026-11-04）

候选 `boot-H103de.img`：

```text
boot:    c21879d16a8351ebfcd0dd0f11dcace35241af9c88a2c0d32007fa914b80be0c
kernel:  1476ba31c9c0ecb6ceb9eb5145e3291a577821328b9a50f5d040745c967b3846
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: e777c4e1fc6f0aaf5d0d353ac309683781398ccc3d7ccc73e8a1b4f01eafd30c
```

移植内容：

- `NativeUfsProbe` 增加只写 `userdata_ios` 末尾 32 MiB 的日志窗口：
  ```text
  logFirst = rootLast + 1 - 8192
  logBlocks = 8192
  ```
- 窗口内写 `SHLOG001` v3 头 + 1 MiB kernel msgbuf（blocks 1..256）；
- 用 probe 自己的 UFS queue 发送 WRITE(10) + SYNCHRONIZE CACHE，只在 `sheng-log=1` 时启用；
- 日志线程在 probe start 后等待 20 秒（root 完成）再写一次快照；
- 不碰 Android `userdata`，不碰 display archive/root 修复；
- 新增 `scripts/h103-log-pull.py`：TWRP 里只读 `userdata_ios` 最后 32 MiB，解析 `SHLOG001` 并输出报告。

上机步骤：

1. 启动 H103de，等待约 30 秒；
2. 重启到 TWRP（仍然只 `fastboot boot`，不安装）；
3. 在 TWRP 的 adb 环境运行：
   ```sh
   python scripts/h103-log-pull.py --adb adb
   ```
4. 把生成的 `h103-log-*.txt` 发回；重点查 `NATIVE_LEGACY`/`NATIVE_UFS_ALIVE`。

结果待上机；若窗口是空的，说明 WRITE10/窗口校验失败，脚本会报 no SHLOG001。

## 57. H103df：log 写自检（2026-11-04）

H103de 拉回的 32 MiB `userdata_ios` 窗口是**全 0**，payload 确实带
`sheng-log=1`，说明 body 一个块都没写。H103df 在写 body/header 前先做
单块写+读回：

```text
write block 0 = "H103TEST" + lba/wrote/read
read block 0 back
IOLog("NATIVE_UFS_LOG: write test wrote=%u read=%u lba=%llx")
失败时 IOSleep(30000) 停屏，便于拍照
```

`scripts/h103-log-pull.py` 现在也识别 `H103TEST`：

- 看到 `H103TEST`：写路径/窗口 offset 正常，问题在 body/header；
- 没有 `H103TEST`：线程没跑、窗口 offset 不对，或 WRITE10 失败。

候选：

```text
boot:    2a998098c4c2c147d0d52ad71997e98d67eb3cbc75616a76c1ebd43daaafe4f3
kernel:  87aff456682aaa40b8aaff49d6606268fd578c9310fdbab9bb3ecb8cae5a2eaa
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: faed19554139fd3457b566715963a5b752175b1041a38700ce83569557afb70b
```

上机：启动后等 60 秒，进 TWRP 拉窗口；若脚本打印
`H103 write self-test block present`，把 `wrote/read` 发回。

H103df 上机仍然没有 `H103TEST`。H103dg 追加：

```text
NATIVE_UFS_LOG: setup mode=%u first=%llx blocks=%u root=%llx..%llx image=%llx
IOSleep(30000)              // 停屏拍照
H103TEST 同时写 block 0 和窗口最后一块
puller 扫描整个 32 MiB 窗口找 H103TEST
```

候选：

```text
boot:    94040dc74ea2b20f2ba9b8655b92b1dc9d3bf81502a95884f94145c1d5aa9685
kernel:  f1bd6e7cba37a50b73df7b57fdf18bd5ec032ba1962a29af9c3e8ae7d4f21d2e
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: f637a087a016b84c505a1b4edffbd52e56b54b0b1dc9d9b1b2cdb75df5b480a9
```

关于 `userdata`：

- H103 的 `userdata` 是 Android 64 GiB ext4；直接写末尾 32 MiB 可能破坏
  Android 文件系统；
- 现在日志窗口在 `userdata_ios` 的未使用尾部（SHNGROOT 镜像约
  9.38 GiB，分区约 49.2 GiB），是安全位置；
- `H103TEST` 没出现更可能是写线程/写命令，不是分区；
- 如果最终必须用 Android `userdata`，先读 ext4 superblock 的
  `s_blocks_count`/`s_log_block_size`，确认末尾 32 MiB 在文件系统之外，
  并在 TWRP 只读校验后再写，不能盲写。

## 58. H103dh：把停屏点移到启动后的 heartbeat（2026-11-04）

H103dg 上机反馈“启动后没有停留”。检查 H103dg 内核，
`NativeUfsProbe::start` 里确实有 `IOSleep(30000)`，但它位于 probe start
末尾、UI 之前，属于早期启动阶段；用户在系统起来后才观察，看到的是已经
继续启动的状态。

H103dh 改为：

```text
NativeUfsProbe::start 只记录 setup 参数，不再停屏
gH103LogMode/gH103LogFirst/gH103RootFirst/gH103RootLast 保存到全局
heartbeatThread 启动后 45 秒：
  IOLog("NATIVE_UFS_LOG: late mode=%u first=%llx root=%llx..%llx")
  IOSleep(30000)          // 此时 UI 已起来，屏幕明显冻结
```

原有 log 线程仍在 start 后 20 秒写 `H103TEST`（窗口首块 + 末块）和
`SHLOG001`，所以这次既能拍照确认 setup 参数，也能在 TWRP 拉窗口验证写路径。

候选：

```text
boot:    d35d87a2a744f749078a06c5d3d41ec0e78ffbae8cd7491a8b31332bcc05dc46
kernel:  3bfb18374e43aeda3ce94d44f7a0a20d89112c64c71091ebd629e10a6ca7f896
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 5a123ca1658860d6a315595b0524d6096ae3b8726268cd1bab30d4cf3ea6883c
```

上机：从 `fastboot boot` 开始观察，启动完成后约 45 秒屏幕应冻结 30 秒，
拍下 `NATIVE_UFS_LOG: late ...`；随后进 TWRP 拉 `userdata_ios` 最后
32 MiB。若 45 秒后仍不停屏，说明 heartbeat 线程没有运行或 probe 未启动，
需要回到更早的 start 入口确认。

## 59. H103di：不再依赖 heartbeat，start 窗口读双写（2026-11-04）

H103dh 确认 boot 哈希 `d35d87a2...`，但启动后仍完全没有停屏。H103
历史上 heartbeat/`NATIVE_UFS_ALIVE` 一直不稳定（H103av/H103aw，H103ba–bd
的 2×2 也是 run-to-run），因此 H103di 把持久化日志从 heartbeat 解耦：

```text
NativeUfsProbe::start 同步执行一次 h103Snapshot("start")
  - 写 H103TEST 到窗口首块
  - 读回校验
  - 写 H103TEST 到窗口末块
  - 写 SHLOG001 v3 + 1 MiB msgbuf

NativeUfsWindow::doAsyncReadWrite 完成后
  - gWindowBytes >= 64 MiB 时触发一次 h103Snapshot("window")
  - 该路径是 root/SystemOS 已证明会走的读路径
  - 快照后 IOSleep(30000) 停屏

logThread 只调用 h103Snapshot("thread")，不再因首块非空提前 return
heartbeat 改为 50 秒计数停屏，不再用 mach_absolute_time
h103-skip-pattern=1 时跳过 native_legacy_test_pattern()
所有 kernel_thread_start 返回值都打印
```

H103di 的 2×2 面板本轮故意不画（`h103-skip-pattern=1`），用于先确认日志
和写路径；不是显示回归。

候选：

```text
boot:       e025ea4f401e1fca990ae160c300058775e2c8a5b1b3b852de1b2694297e9f0a
kernel pre: a59dd74d8ca950d2dc0e462e78182d56999384c8219d570fa79fef2593b889b7
kernel:     171185264ec4c0eae82722164b45094045860d657f490bd982d6179390e66cc0
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    d046fc95e76e648a707f131ea6e15c77634079e8ef5a35ad4cb969b45d3e8763
```

上机后 TWRP 拉窗口，重点看：

- `H103TEST ... tag=start` 或 `tag=window`：裸 UFS 写路径正常；
- `SHLOG001`：日志已落盘，直接解析正文；
- `NATIVE_UFS_LOG: start snapshot result=...` / `window trigger bytes=...`：
  只能通过窗口里的正文看到，若没有正文则说明 start 写也失败。

## 60. H103dj：修复 start 快照的内核栈溢出（2026-11-04）

H103di 上机在 `NATIVE_UFS_LOG: start snapshot begin` 后立刻 panic：

```text
Kernel data abort
pc 0xfffffff0079b0442 ...
```

反汇编确认不是 UFS 写失败，而是栈溢出：

```text
NativeUfsProbe::start frame       0x2360  (9056 bytes)
NativeUfsProbe::h103Snapshot frame 0x20e0  (8416 bytes)
                                  ------
                                  0x4440  (17472 bytes) > 16 KiB kernel stack
```

`h103Snapshot` 里的 `uint8_t test[4096]` + `uint8_t check[4096]` 共 8 KiB
叠在 `start` 的 9 KiB 栈帧上，第一条 `WRITE(10)` 之前就踩穿内核栈。

H103dj 把 `test`/`check` 改为 `IOMallocAligned(4096, 4096)`，栈帧：

```text
h103Snapshot 0x120 (288 bytes)
```

其余逻辑不变：start 同步快照、64 MiB 窗口读快照、`H103TEST` 先写后读、
`h103-skip-pattern=1` 不画 2×2。

候选：

```text
boot:      4a9de88e2c884506b75bcfeb14ea82a2e2ee09c8afa2711fe14a622d267d2047
kernel pre: 77134eed24d453e1653666613b397a7d591e08755726eb34a69f72dbf1527d06
kernel:     276f9927225058e5d7a0fab702a0af6150af0edac16614159fd4c778642a38b2
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    4a8321c68e55f9bd373f0ada49d8396a99331c6e6400efc9827b4b5f5d600897
```

H103di（`e025ea4f...`）会 panic，不再使用。

## 61. H103dl：去掉快照读回，只写 H103TEST/header（2026-11-04）

H103dj 的栈修复生效（`h103Snapshot` 帧降到 0x120），但上机仍在
`NATIVE_UFS_LOG: start snapshot begin` 后立刻 panic。panic 的 PC/LR 落在
读路径（`readWindowBulk`/`readBlocks` 附近），因此第一嫌疑变成
`h103Snapshot` 里的：

```text
bool testWrite = logWrite (0, 1, test);
bool testRead  = testWrite && readWindow4k (fLogFirst, check) && ...
```

也就是说，写测试块可能已经成功，紧接着的 4 KiB 读回触发了 data abort。

H103dl 把所有快照的 `verify` 参数设为 0：

```text
start  : 写 H103TEST 首块/末块 + 1 MiB body + SHLOG001 header，不读回
thread : 同上，不读回
window : 同上，不读回
```

写入是否成功改由 TWRP 的 puller 验证。这样如果 H103dl 不再 panic，就可以
确认是读回路径；如果仍 panic，则第一块 WRITE(10) 本身有问题。

候选：

```text
boot:       491301d0755278baf94c6253c85d2f00306321a96cd39e0e269871094829889b
kernel pre: 6c0c1f3c55cf9fc5c7590c8f164c4efe2cdaf3c13b492e99f1688d96ab941e16
kernel:     79646a830126c3aa88afa44ffc90475737e67da6d0de53e8c6de4c210b695ed6
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    9db662466cf4e3ac3dedea4094ab6e704713fd55780595b16d2b86f43b6ad797
```

H103dj（`4a9de88e...`）仍会 panic，不再使用。

## 62. H103dm：把快照完全挪到 root 之后的窗口读（2026-11-04）

H103dl 去掉读回后**仍在** `NATIVE_UFS_LOG: start snapshot begin` 后
panic。panic 的 PC/LR 仍在 `readBlocks`/`readWindowBulk` 附近，说明
`start()` 里同步写 1 MiB 会和早期 LUN/root 读竞争，不能作为日志入口。

H103dm 改动：

```text
start() 只记录 setup/first/root/safe，不写任何块，也不启动 logThread
remove start snapshot
NativeUfsWindow 累计读 64 MiB 后，在 storage 读完成回调里执行一次
  h103Snapshot("window", pause=1, verify=0)
  - 写 H103TEST 首块/末块
  - 写 1 MiB body
  - 写 SHLOG001 header
  - 不读回
  - IOSleep(30000) 停屏
heartbeat 仍然 h103-skip-pattern=1，不画 2×2
```

候选：

```text
boot:       6de47089a78519b1f239850ec11c9476397bbfc0f2b4df7f578d7e2b93e730cb
kernel pre: 8676eae81e20f71ddb3e42776e26604e59498e6b658e4b034bed98291fad8d49
kernel:     5e88804355076fa0231afc2cd8ab4b3906736c637933733053e20c0d6bf41014
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    dc2ae7b63c084cc68762bc4a42ac1b0316c93bb24f8a22a0495faf3bf5323350
```

上机判读：

- 不再在 start snapshot 处 panic：早期写竞争确认；
- 启动后约 64 MiB 窗口读时停 30 秒，屏幕应有 `window trigger bytes=...`；
- TWRP 能拉到 `H103TEST`/`SHLOG001`：root 之后写路径正常；
- 在 `window trigger` 后 panic：写路径本身有问题，需要单独隔离 WRITE10。

## 63. H103dn：独立 log DMA 缓冲，避免写 live readData（2026-11-04）

H103dm 上机已经进入用户态（launchd/dyld cache 都在跑），但在：

```text
NATIVE_UFS_LOG: window trigger bytes=67695616
```

之后立刻 panic，仍然在 UFS 命令路径。此时 start 未写、readback 已关，
剩下的共同点是 `logWrite()` 直接把数据 `memcpy` 到 live 的
`fQueue.data`（readData）上，而这个缓冲同时是 root/SystemOS 读 DMA。

H103dn 增加一个独立的、`kIODirectionOut` 的可写 log DMA 缓冲：

```text
start: 分配 fLogDma = IOBufferMemoryDescriptor(kIODirectionOut, 128 KiB)
logWrite:
  IOLockLock(fLock)
  保存 fQueue.data/dataPhys/dataCapacity
  临时换成 fLogData/fLogDataPhys
  ufsWriteCommand(...)
  恢复 readData
  IOLockUnlock
```

快照仍只在 root 之后 64 MiB 窗口读触发一次；不读回；停屏 30 秒；
`h103-skip-pattern=1`。

候选：

```text
boot:       f6d4e0dcc574a6c1a37f6281caa30d99b40007c819817cfa9772ce907c14aefb
kernel pre: 0abc16afdfdf987ecfd69f684194cba5c7a0a279ab610516eb4e594d90e03b19
kernel:     2a86871c25939305e32bcfb72dd2c75d25baf8914a57f262ddf29a2fed20b650
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    8700cc6deb106c3697fcab7bfb12e0074c51955be060c247ce0f66f27d5e4b6e
```

若 H103dn 仍在 `window trigger` 后 panic，则问题不在 readData 的 CPU
写，而在 `ufsWriteCommand`/`ufsSubmit` 的 WRITE(10) 本身；下一步只写一个
块到窗口首块，不再写 1 MiB body/header。

## 64. H103do：单块 WRITE(10) 隔离（2026-11-04）

H103dn 仍在 `window trigger bytes=67695616` 后 panic，没有出现
`write test`。独立 log DMA 没有解决问题，说明故障在单块 WRITE(10) 本身
或它之后的 UFS 状态，而不是 1 MiB body/header。

H103do 把窗口触发后的动作缩到最小：

```text
单块 gH103Test[4096]（4 KiB 对齐静态缓冲）
IOLog("NATIVE_UFS_LOG: single write begin lba=...")
logWrite(0, 1, gH103Test)   // 只写窗口首块
IOLog("NATIVE_UFS_LOG: single write result=0/1 lba=...")
IOSleep(30000)
```

不写第二块、不写末块、不写 body、不写 header、不读回。

候选：

```text
boot:       7c9c92d6fcbc0ee4ada709dbe991974dd632bb1496e0786de71ee5b3f3190235
kernel pre: d5a08ec5023c0e3b3a0b8cf51392400497137e40c1bf2dcaf1a049135c18ae3a
kernel:     7d4d9969d65d9d478a02f6b03be69fa3ff920b3089bb39149d477f37c3f7d097
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    8ee9f42772bfa247c9f6cbf2138d503533c7b6e994806061fe450d4f3fc5fd92
```

判读：

- 有 `single write begin` 后 panic：单块 WRITE(10) 本身故障；
- 有 `single write result=1`：单块写成功，TWRP 应能看到 `H103TEST`；
- `single write result=0`：WRITE10 返回失败，查响应/窗口；
- 连 `single write begin` 都没有：64 MiB 触发或 `h103SingleWrite` 没走到。

## 65. H103dp：用 writeBytes 填 log DMA，跳过 ufsWriteCommand memcpy（2026-11-04）

H103do 上机在：

```text
NATIVE_UFS_LOG: single write begin lba=1c607fb
```

后直接 panic，没有 `single write result`，确认是单块 WRITE(10) 就崩。
H103dm 写 readData、H103dn/do 写独立 logDma，三者共同点都是
`ufsWriteCommand()` 里：

```c
if (src != q->data) memcpy(q->data, src, bytes);
```

而 `getBytesNoCopy()` 返回的 DMA 映射在这里不是 CPU 可写路径。

H103dp 改为：

```text
fLogDma->writeBytes(0, src, bytes)
  返回值必须等于 bytes，否则打印 short 并返回

ufsWriteCommand(&fQueue, 0, cdb, bytes, fLogData)
  此时 q->data == src == fLogData，跳过 memcpy
```

仍然只写单块 `H103TEST`，不写 body/header，不读回，停屏 30 秒。

候选：

```text
boot:       89e1ea912460ce161b2d58297f767e5a0f8bcd8ba1522f5d9754d02540c085a3
kernel pre: c0a274cb2e0c4f5c230c0817187a9545a532e09ecbba35e2820f6f59b455695d
kernel:     4b5ca54dddef09acad19e03a3b7965f6edf5f1cf0cfb25eb85502c8bca3b7f60
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    fe6de668a05e4b4b83dd0a7f5ca91170a0adef4119d963bd5f88c048ef40542f
```

判读：

- `single write result=1`：DMA CPU 写是根因，单块写成功；
- 出现 `log DMA writeBytes short`：`writeBytes` 也不行，需要换 CPU 可写源 + 独立物理 DMA；
- `single write begin` 后仍 panic：不是 memcpy，问题在 WRITE10/PRDT/UTRD 或设备写保护。

## 66. H103dq：log DMA 改为 kIODirectionIn（2026-11-04）

H103dp 在 `fLogDma->writeBytes()` 触发：

```text
IOMemoryDescriptor.cpp:2261
Assertion failed: !(kIOMemoryPreparedReadOnly && _flags)
```

说明 H103dp 把 log DMA 建成 `kIODirectionOut`，描述符被 prepare 成
read-only，`writeBytes()` 在真正发 UFS 命令前就断言。UFS WRITE(10) 是
设备从内存读数据，缓冲应为 CPU 可写方向。

H103dq 只改这一处：

```text
logOptions = kIODirectionIn | PhysContiguous | MapperNone
```

保留：

```text
fLogDma->writeBytes(0, src, bytes)
ufsWriteCommand(..., src = fLogData)  // src == q->data，跳过 memcpy
```

仍只写 `userdata_ios` 窗口首块，不写 body/header，不读回，停屏 30 秒。

候选：

```text
boot:       6f6ffb9148f947a7097e25cdba0b29d9a53764c9dce91688aae7d314fc5879e0
kernel pre: 664888302c4e39d9fc3418fef47f50d03c179d034d016cc50b3f89b318bceba7
kernel:     f100195bb7fa93a7f8ec2ed51ce29cf63a971f2ccb60c6c5451c5f93016be97e
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    9fb582e3d250d6ec5de36e38ced8b0a77e62f1ea1d3345be4aa5d76f2bc03d52
```

判读：

- `single write result=1` + TWRP 看到 `H103TEST`：方向问题解决；
- 仍断言 read-only：改 `kIODirectionInOut` 或显式 `prepare(kIODirectionIn)`；
- 断言消失但 UFS/data abort：问题转到 WRITE10/PRDT/UTRD；
- `writeBytes short`：缓冲仍不可写。

## 67. H103dr：恢复 SHLOG001 header/body（2026-11-04）

H103dq 上机后 TWRP 拉到了：

```text
H103 write self-test
H103TEST
```

说明单块写入 `userdata_ios` 窗口成功，`kIODirectionIn` + `writeBytes()` +
`ufsWriteCommand(src=fLogData)` 路径可用。

H103dr 把窗口触发从单块测试恢复成完整快照：

```text
h103WindowRead -> h103Snapshot("window", pause=1, verify=0)
  - H103TEST 首块/末块
  - 1 MiB kernel msgbuf
  - SHLOG001 v3 header
  - 不读回
  - IOSleep(30000)
```

仍只操作 `userdata_ios` 最后 32 MiB，不改 Android `userdata`。

候选：

```text
boot:       9d566a4ceea7243ecde98f7442265deafc5f96e1a93c0011bedde4122d99beb3
kernel pre: 09733c6e1b0d7baf4497454d5194c32f8acfd34268054015a2447dc3f99c5c0a
kernel:     a5c0a9ead8ea24ba3ce49a8a8e1976226211abf9879f47fff6f8ee196490e8ee
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    c12852ab4ac428385f91594774f611d44176326b5bd98689598d43f3c67943d5
```

上机拉窗口：

- `SHLOG001`：日志落盘，解析正文；
- 只有 `H103TEST`：单块写正常，body/header 失败；
- 什么都没有：64 MiB 触发或快照没执行。

成功后去掉 `h103-skip-pattern=1`，恢复 2×2。

## 68. H103ds：late 快照 + 恢复 2×2（2026-11-04）

H103dr 的 `SHLOG001` 成功（`msg_bytes=43562`），但 64 MiB 触发的快照停在
320.751，只到 launchd/dyld cache，没有 `backboardd`/`SpringBoard`/显示
客户端。日志里已经确认：

```text
NATIVE_LEGACY: IOMobileFramebufferLegacy::start
NATIVE_LEGACY: startHardware gop=1
NATIVE_LEGACY: video=9d400000 1080x1920 row=4320 display=1
NATIVE_LEGACY: mapping=0xfffffff799610540
NATIVE_LEGACY: valid=1 phys=0 len=0
NATIVE_LEGACY: base start ok primary=1
NATIVE_LEGACY: phase=4 dt=1 probe=1 attach=1 start=1 reg=1
NATIVE_UFS_HB: enter
```

H103ds 增加 heartbeat 第 12 tick（约 120 秒 + 50 秒停屏之后）的 late 快照，
并从 payload 去掉 `h103-skip-pattern=1`，恢复 heartbeat 的 2×2 重绘：

```text
heartbeat tick >= 12:
  NATIVE_UFS_LOG: late snapshot tick=...
  gH103Probe->h103Snapshot("late", pause=1, verify=0)
  IOSleep(30000)

payload 不再带 h103-skip-pattern=1
心跳每次 tick 调 native_legacy_test_pattern()
```

64 MiB 的早期 `window` 快照保留；late 快照会覆盖 header/body，TWRP 最终
读到 late 日志。

候选：

```text
boot:       5f6bfd17c9ad87a3070de1da27a56f907b58bdbef12d838e030ed261531388ec
kernel pre: e0f57cb61db08be3685de2d8b8cb50f2eeed58006836b3082ca5223c6b4c3080
kernel:     22e1aa5980149bef455326e3c5d83def80fff98db18b6652294d807822be814c
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    39194bd3cdfb27df875b076ae1a5e28aa1bcfe83c9e9749f34da43d680edae8b
```

上机：启动后约 2.5 分钟会停屏 30 秒，此时 2×2 应已出现；随后进 TWRP 拉
窗口，重点看 `backboardd`、`SpringBoard`、`IOMobileFramebufferLegacy`
user client 和 late 日志。

## 69. H103dt：去掉 logSync 卡点，WRITE10 用 FUA（2026-11-05）

H103ds 上机后屏幕停在：

```text
NATIVE_UFS_LOG: write test tag=window verify=0 wrote=1 read=0 end=1
```

几分钟不动。日志文件已经有有效 `SHLOG001`、`msg_bytes=43573`，说明
body/header 已经写入；卡点在 header 之后的：

```c
if (ok) {
  ok = logSync ();   // SYNCHRONIZE CACHE, CDB 0x35
}
```

`logSync()` 持有 `fLock` 发 `SYNCHRONIZE CACHE`。该命令不返回时：
late heartbeat 快照拿不到 `fLock`，2×2 也不会继续。`IOSleep(30000)` 排在
`logSync()` 之后，还没走到，不是停住的原因。

H103dt 改动：

```text
logWrite CDB: cdb[1] = 0x08 (FUA)
h103Snapshot: 删除 logSync()
window 早期快照: pause=0
late heartbeat 快照: pause=1，保留 30 秒停屏
payload 不带 h103-skip-pattern，保留 2×2
```

这样写命令自身提交到介质，不再依赖可能卡死的 SYNCHRONIZE CACHE。

候选：

```text
boot:       d4c770df3ade2f3a7990daa673e58aa3cc77d9f974710ac20f17a70fe1977486
kernel pre: 50958392dfcd669560aae3ce3ccde2bae1fbc7cc9795f4049b3eb86f34099a7e
kernel:     1cfdae53833c10286e1f202f46a9a6ad48e24df679648c7a727c92d70e334935
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    f7e1792c50851f052e87f1dbe867c247ad478099266511a5a8d72e1cf29f8fa6
```

上机判读：

- 早期 `write test` 后继续出现 `snapshot tag=window`：不再卡 `logSync`；
- 约 2.5 分钟出现 `late snapshot tick=12` 和 30 秒停屏：heartbeat 正常；
- TWRP 拉到 late 时间戳的日志：FUA 写有效；
- 如果 FUA 被拒绝：还需要单独处理写缓存，但不会再卡 fLock。

## 70. H103du：1 GiB late-window 快照 + puller flush/direct（2026-11-05）

H103dt 屏幕已经继续，但 TWRP 读到的文件还是 64 MiB 的早期快照。两个原因：

1. heartbeat 第 12 tick 的 late 快照可能还没执行；
2. TWRP `dd` 走页缓存，之前拉过早期窗口后，late 写入的块可能仍返回旧页。

H103du 增加 **window 字节 late 快照**，不再依赖 heartbeat：

```text
gWindowBytes >= 64 MiB   -> h103Snapshot("window", pause=0, verify=0)
gWindowBytes >= 1 GiB    -> h103Snapshot("late-window", pause=0, verify=0)
```

两个快照都不停屏，避免卡住存储线程；heartbeat 的 late 和第 12 tick 仍保留。

puller 同时改为先 flush block cache，再尝试 `dd iflag=direct`，失败则回退普通 `dd`：

```text
blockdev --flushbufs /dev/block/sda14
dd ... iflag=direct
```

候选：

```text
boot:       ba2c1f0a0c75e3e380d794d4794455853b86e6dfa70fcb5833d88857aec4f76c
kernel pre: 495beb9382fbec52b0eefe65dba8b6a3232cd2b407f55b667fc7aaafe6c51178
kernel:     2e660304ece04bfff8638583841be9629ce4517fd950f95b69557aa17db3f854
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    c1e7d4a2a77cea2e088da84f8951b739fc40d8435314076c33578208e80d3c59
```

上机后看：

- 屏幕出现 `late-window trigger bytes=...`：1 GiB 快照触发；
- TWRP 拉到 `SHLOG001` 且时间戳到 1 GiB 之后：late 窗口成功；
- 如果文件仍是早期快照，先确认 puller 是否用了新脚本的 flush/direct；
- 仍只写 `userdata_ios`，不碰 Android `userdata`。

## 71. H103dv：2 秒 slot 实时日志 + 2×2 绘制打点（2026-11-05）

H103du 仍然在 `write test tag=late-window` 后停住，因为窗口快照还要写
1 MiB body/header。H103dv 改成真正的实时写入：

```text
heartbeat 改成 2 秒
每 2 秒：
  h103SlotWrite()
  拷贝最新 128 KiB msgbuf 到 slot
  写 slot_first + slot * slot_blocks
  更新 header slots_written/rounds/state=3
  不写 1 MiB body
  不调用 logSync，WRITE10 继续 FUA
```

窗口读的 64 MiB/1 GiB 大快照全部关闭；heartbeat every 2s 同时重绘 2×2。

显示侧增加最小诊断日志：

```text
NATIVE_LEGACY_PATTERN: enter base=... w=... h=... stride=...
NATIVE_LEGACY_PATTERN: panel=... x0=... y0=... stage=... client=... calls=...
NATIVE_LEGACY_PATTERN: exit blink=...
```

如果调用执行但屏幕还是空白，就能区分是坐标/framebuffer/stride 问题，还是
后续 backboardd 覆盖。

puller 现在优先读最新 slot：

```text
slot = (slots_written - 1) % slot_count
读取 slot_first + slot * slot_blocks
回退到 msg_first body
```

候选：

```text
boot:       4ed5ce91831621d2b4868f3d88b290d3421c50e61dcb6647b69162a8c1589676
kernel pre: 441f56c0d14157736532afeace2b2a892ab79acac229f14fdc58d62060fb0b69
kernel:     593be1065ebfc7f3e0633c66ed0e826178c4b66a2b8ee8062eec71e568962c32
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    ad3b2e80ddd06480261db84ec1698a3c39d39ad64eb1af52fd85044bf76db364
display:    03fa715 (GopFramebuffer display-op5)
```

上机：每 2 秒应能看到 `NATIVE_LEGACY_PATTERN` 三条日志，屏幕右上 2×2 和
左上三块应重绘；TWRP puller 应读到 `slot=... slots_written=...` 的最新
128 KiB 日志。仍只写 `userdata_ios`。

## 72. H103dw：回到 H103bd 颜色面板，静默 2 秒 slot（2026-11-05）

核对 11 月 3 日的提交：`8946733`/`77cbf26` 指向的 `bfa9a0d` 只是
**纯品红 256×256** 测试块，不是右上 2×2。真正的 H103bd 2×2 颜色面板在
`5f29dde`，当前源码也仍然保留同一套 `stageColor/clientColor/callsColor`
代码；后来只是增加了左上三块和日志。

H103dw 的取舍：

```text
显示 source 回到 5f29dde（H103bd 2×2 颜色面板，无 PATTERN 日志）
heartbeat 2 秒 slot 保留
gH103Quiet=1，关闭 NATIVE_UFS_ALIVE / PROGRESS / WINDOW / IO / BULK 周期日志
payload 去掉 -v、debug=0x14e、boot-progress=2
puller 继续 flush + direct + 最新 slot
```

这样屏幕不再被 console 每 2 秒刷掉，2×2 画完后没有日志覆盖；日志只在
`userdata_ios` slot 里。

候选：

```text
boot:       99307b5f99a7154a7212b5e9ff3e0ef562b5fc89e98d4bf334c42c28cde7fcc4
kernel pre: 57122244f4a55f1e37d02753b094c8f812f163b18478b4a81e4aa38eff235bc8
kernel:     61603873ad954ef895b3ffefebf722bb3bde3e9ef4fca3f06827b20997628374
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    ff3a13661b3fbccbe38a42633865b84b51cfd57dd8b7f2ba4db218a096462217
display:    5f29dde
```

上机：屏幕右上应保留 2×2，不再持续滚动；TWRP 拉到最新 slot 即可。

## 73. H103dx：先画 2×2，再写 slot（2026-11-05）

对比 3 号 `8946733`：当时 heartbeat 只有 `NATIVE_UFS_ALIVE`，根本没有
`native_legacy_test_pattern()`；H103bd 镜像的 2×2 是后来直接在 heartbeat
里调用的。H103dw 把 128 KiB slot 写放在绘制之前，slot 写要拿 `fLock`，
会拖住后面的 2×2。

H103dx 只改顺序：

```text
heartbeat 2s:
  native_legacy_test_pattern()   // 先画 2×2
  h103SlotWriteThunk()           // 再静默写 slot
  不打印 console
```

保留：

- `5f29dde` H103bd 2×2 颜色面板；
- 2 秒 slot；
- `gH103Quiet=1`；
- payload 无 `-v/debug/boot-progress`。

候选：

```text
boot:       7c4f4e6dde4f55a971dd8abb92e7715d8fdcc9a457670977692e9aed76b21211
kernel pre: cb65784262dbdc70c6a868664cf58a5f2f7885c85e9ce926fc9c5ae604cc058c
kernel:     5addf7cd16d56c698344a93af59b33ddb504b6043e29b5ee1721cbcf094fafd5
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    a339391de2d8ba325efd693fa7e5c5a96bd2e8a352f50540d8bec5eae6f435de
display:    5f29dde
```

判读：右上 2×2 出现说明 slot 写阻塞是原因；仍不出现则与 slot 无关，
下一步只保留 heartbeat 绘制、完全关闭 slot 做对照。

## 74. H103dy：只画 2×2，完全关闭 slot（2026-11-05）

H103dx 上机后 2×2 和 slot 都没有更新，日志还是旧的。两者都由 heartbeat
驱动，因此先排除 slot：H103dy 完全移除 `h103SlotWriteThunk()`，heartbeat
只做：

```text
IOSleep(2000)
native_legacy_test_pattern()
stall check
```

保留 `5f29dde` H103bd 2×2、`gH103Quiet=1`、payload 无 verbose。

候选：

```text
boot:       5bc2f835a73f93c5b0c7717f6d8987fc2ea457bd6c5ef9799bafaa012bf35cef
kernel pre: a324abf0ea174d95b272ee2cf72400d3adefcab9909bdf71b24169cd57b98335
kernel:     9cda2b9a65a211ea1b84835b42db7111d08eb13068186cecc95167e4b637b1e1
ADT:        d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload:    116b6885483c2139e0eff3fa0739c0e511471cb981c9d3f33119d30ee1ca9dd5
display:    5f29dde
```

判读：

- 2×2 出现：H103dx 的 slot 写入阻塞 heartbeat；
- 2×2 仍不出现：heartbeat 没启动或 display archive 没链入；
- 本次不写 slot，TWRP 日志不会更新是预期的。

## 75. H103dz：H103bd payload 参数 + 只画 2×2（2026-11-05）

H103dy 仍看不到 2×2，slot 已完全移除。H103bd 镜像（`8284f261...`）能出
2×2，其 payload 参数包含 `-v`、`debug=0x14e`、`boot-progress=2`；H103dy
为了安静把这些都去掉了。H103dz 只用 H103bd 的 payload 参数，内核仍是
H103dy 的“只画 2×2、不写 slot”版本：

```text
kernel: 9cda2b9a... (H103dy, heartbeat native_legacy_test_pattern only)
payload args: H103bd 原样 (-v debug=0x14e boot-progress=2 ...)
display: 5f29dde
```

候选：

```text
boot:    4fecce628a60ae0ce0bbf39923931b92f3f4152d5f07b25205caca661f9803c8
kernel: 9cda2b9a65a211ea1b84835b42db7111d08eb13068186cecc95167e4b637b1e1
payload: 06c4e71bac2bc1f727de45dedd566c888d99564de11268b9a922b91eaa304749
```

判读：

- 2×2 出现：H103dy 的 quiet payload 参数把显示路径关掉了；
- 仍不出现：H103dy 内核/display archive 与 H103bd 内核不同，需直接对比两个内核。

## 76. H103ea：恢复 H103bd 心跳，2 秒 slot 独立线程（2026-11-05）

H103dy/H103dz 都看不到右上 2×2。直接对比两个内核后确认：

- H103bd 的 heartbeat 是 `IOSleep(10000)`，先打印
  `NATIVE_UFS_ALIVE: ...`，再无条件调用
  `native_legacy_test_pattern()`；
- H103dy/H103dz 把心跳改成 2 秒、去掉了 `NATIVE_UFS_ALIVE` 行，并把
  `gH103Quiet` 设为 1；
- H103bd 内核还带有 `NATIVE_LEGACY_STATE/CLIENTS` 和更长的
  `NATIVE_UFS_PROGRESS` 字符串，当前 `5f29dde` display archive 没有这些
  日志，但 `native_legacy_test_pattern()` 的绘制指令两边一致。

H103ea 只做三件事：

```text
heartbeat: IOSleep(10000) -> IOLog(NATIVE_UFS_ALIVE) -> native_legacy_test_pattern()
gH103Quiet = 0（恢复 H103bd 周期日志）
2 秒 slot 放入独立 h103SlotThread，不再插在 10 秒心跳里
payload: 沿用 H103dz 的 H103bd 参数（含 sheng-log=1）
display: 5f29dde，不改
```

构建路径：

```text
build-arm-driver.py NativeUfsProbe     # 先重编驱动 archive
build-xnu-4k-baseline.sh               # 重编 XNU
unixnu build prelink                   # 生成 out/.../kernel/kernel.macho
把 kernel.macho 写回 H103dz payload 的 Payloads/kernel.macho
用 H103dz boot image 的 UEFI kernel 重新拼 ramdisk
```

候选：

```text
XNU:     32d9bf03ef5a76b64ea4d1f76d38879b150beea8b98a69904ff916b7e9a56166
kernel:  560571229630b8edd2e235d7c8104ca57cf9fd320e1efe2ec041f7a5cda62e61
ADT:     d98d9522451a66bd380a3e45e0f8d5b7df417b8d5a8fd2c4a847b6a21d695fef
payload: 4da9f3c04fc867713badd6ca243c20797ad5f7def0ca39b23fd3219d669c6665
boot:    a07fe2567b43edcf7cbd58a86a8d4474cae49ac84e79b667e074205e1b4e2f5e
display: 5f29dde
```

判读：

- 2×2 出现：H103bd 的心跳/日志顺序可与 2 秒 slot 共存，H103eb 再静默；
- 2×2 仍不出现：只剩 display archive 差异（H103bd 内核的
  `NATIVE_LEGACY_STATE/CLIENTS`）或独立 slot 线程两个变量，下一步停止
  在 H103dy 上继续改，改用 H103bd 精确镜像做对照。

## 77. H103eb：恢复 UFS 完成路径的 2×2 重绘（2026-11-05）

H103ea 和 `boot-H103ea-bdargs.img`（H103bd 原始 payload 参数，无
`sheng-log`）都没有右上 2×2。对比 H103bd 内核的调用点后发现关键差异：

```text
H103bd:
  ufsCommand completion
    if ((gUfsCommands & 63) == 0)
      native_legacy_test_pattern()   // 先重绘 2×2
      print PROGRESS / NATIVE_LEGACY_STATE

当前源码:
  ufsCommand completion
    if (!quiet && (gUfsCommands & 63) == 0)
      print NATIVE_UFS_PROGRESS        // 没有重绘
  native_legacy_test_pattern() 只在 10 秒心跳里
```

H103bd 的 2×2 能持续可见，是因为 UFS 完成路径每 64 条命令就重绘一次，
而不是只靠 10 秒心跳。H103eb 在 `ufsCommand` 的 PROGRESS 分支里、打印
之前补回 `native_legacy_test_pattern()`：

```text
heartbeat: 10 秒 + ALIVE + pattern（保持 H103ea）
UFS completion: (gUfsCommands & 63) == 0 时先 pattern，再 PROGRESS
quiet: 0
slot: 独立 2 秒线程（H103bd 参数下 sheng-log 未开，线程空转）
display: 5f29dde
payload: H103bd 原始参数（无 sheng-log / native-cpufreq-early）
```

候选：

```text
XNU:     7c4af02f609ae748b4f2e71fcb3b0efb40d660e7bde8bec90412a03dcf61d14d
kernel:  91959feaa38bf249f91cfe6b534968b00498817cc5d704bffe377169d00ba691
payload: 32963f1f9e9f4e90af00fa1cbb3cef829cd143fbf0e7c986902253f53959cfc1
boot:    614c83a5d912ca4c5ab815190e95122a30a2f972518d89fcee1fc73763ea1f59
```

判读：

- 2×2 出现：UFS 完成路径重绘就是 H103bd 保持面板的原因；H103ec 再加
  `sheng-log=1` 和 slot；
- 仍不出现：H103bd display archive 的 `NATIVE_LEGACY_STATE/CLIENTS` 版本
  还有别的行为，必须找回那份 archive。

## 78. H103ec：UFS 重绘 + `sheng-log=1` + 2 秒 slot（2026-11-05）

`boot-H103eb-bdargs.img` 上机后右上 2×2 出现，确认 H103bd 的面板可见性
来自 **UFS 完成路径每 64 条命令重绘**，不是 10 秒心跳单独维持。

H103ec 不重编内核，只把 H103bd payload 参数加一项 `sheng-log=1`：

```text
kernel: 91959fea... (H103eb, UFS 完成路径先 pattern 再 PROGRESS)
payload: H103bd 原始参数 + sheng-log=1
slot: 独立 h103SlotThread，每 2 秒写 userdata_ios
display: 5f29dde
```

候选：

```text
kernel:  91959feaa38bf249f91cfe6b534968b00498817cc5d704bffe377169d00ba691
payload: 6160640a420c170ab779af16af94e41bea58fe531e2d8f67b763c021b0330424
boot:    a03f380ded8ff9a3519f217abf0e4f966ca782bf027665e86ce04ae22a20ae1a
```

上机验证：

- 右上 2×2 仍在；
- `NATIVE_UFS_ALIVE` 每 10 秒一条；
- TWRP 读 `userdata_ios` 最后 32 MiB 的最新 slot，`slots_written`
  应持续增长。

若 `sheng-log=1` 再次让 2×2 消失，说明问题在日志窗口/早期窗口读，而不是
slot 线程本身；下一步只在 `sheng-log` 打开时延迟窗口初始化。

## 79. H103ed：三个状态块移到左上，恢复 CPUFREQ early（2026-11-05）

H103ec 上机后 2×2 和 slot 都正常。用户要求：

1. 把右下角三个 16×16 状态块移到屏幕左上角；
2. CPU 频率块之前是红色，H103cz 时是绿色，恢复正常的 CPU 频率。

代码改动：

```text
NativeLegacyDisplay::drawTestPattern()
  CPU 频率块:  (0,0,16,16)
  A540 块:     (20,0,16,16)
  心跳块:      (40,0,16,16)
```

频率块的红色不是测量错误：H103cz 的 payload 带 `native-cpufreq-early=2`，
会触发内核里的 `NATIVE_CPUFREQ_EARLY` 代码去编程 OSM；H103bd 参数没有
这个 arg，OSM 保持 bootloader 的低频，`sheng_cpufreq_probe()` 于是读到
`<1 GHz`，状态为红。H103ed 在 H103ec 的 payload 上只补：

```text
sheng-log=1 native-cpufreq-early=2
```

内核仍包含 `NATIVE_CPUFREQ_EARLY`（`strings` 可见 7 处），无需改源码。
但注意该代码目前来自 Mac 构建缓存 `build/sheng-platform-power/` 的
11 月 4 日 archive；设备仓库当前 `ShengPlatformPowerGlue.cpp` 是短版本，
重建 archive 前必须先恢复早期 CPUFREQ 源码。

候选：

```text
XNU:     ed750931b794ebe206e1fd5aada71d5459fba0268b77e597b33c010de5e4fdb9
kernel:  fec7abd797ce920211cae12f9135ae5e05b3ac9cca70e91392123cdb3f4fbc40
payload: 0d0a2176c87ee724b9a3c17c546e9d0708fddfbd4c3b17331b927235c5622b4d
boot:    59908da2f8804aa2723b1d10ad57254001356129e38effca9bcdeb0850c4c059
display: adf38de
```

上机判读：

- 左上三个块出现，最左边 CPU 块应为绿色；
- 右上 2×2 仍在；
- TWRP slot 继续更新。

## 80. H103ee：slot 线程诊断（2026-11-05）

H103ed 上机后右上 2×2 正常，但 TWRP 读到的 header 是 snapshot 写的：

```text
first_lba=29755387 window_blocks=8192 slot_count=247
slots_written=0 rounds=1 state=2 msg_bytes=69343
```

日志里只有：

```text
NATIVE_UFS_HB: start rc=0 skipPattern=0
NATIVE_UFS_LOG: setup mode=1 first=1c607fb blocks=8192 ... safe=1
NATIVE_UFS_HB: enter
NATIVE_UFS_LOG: snapshot tag=window ok=1 ...
```

没有 `NATIVE_UFS_HB: slot rc`，也没有 slot 写日志。H103ee 只加诊断：

```text
start():    "NATIVE_UFS_HB: slot start" -> kernel_thread_start -> "slot rc=%x"
h103SlotWrite(): 前 8 次尝试打印 wait/ready/lock/dma、slot/lba/body 结果、
                 header 结果和 cursor
h103Snapshot(): slots_written = gH103SlotCursor，state 按 cursor 选 2/3，
                不再清零
```

候选：

```text
kernel:  96321f31312d788dca3410eea773b9a4bad638351256061767df3f6d6124443f
payload: efa7b4ff54af63d3c7392dbf68e02e5a929dd398078cb7442aee3094b5dbaedb
boot:    b742d928fea5eb7dbc7e4f92245dcacbd0969584462fabf192957783c708e34a
```

判读：

- 出现 `slot start` 但没有 `slot rc`：线程创建路径异常；
- 出现 `slot rc`，随后 `wait` 一直 ready=0：日志窗口初始化顺序/字段问题；
- 出现 `attempt ... body=0`：128 KiB UFS 写失败；
- `body=1`、`header=0`：header 单块写失败；
- `body=1`、`header=1`、cursor 增长：slot 正常，TWRP 应看到
  `slots_written` 增长。

## 81. H103ff：左上 slot 状态块（2026-11-05）

H103ee 拉到的日志 `boot_id=10124572351` 与 H103ed 完全相同，说明新内核
没有被真正启动，不能据此判断 slot 线程。左上/右上块在 H103ed 已经存在，
也无法区分 H103ed 和 H103ee。

H103ff 增加一个屏幕上可见的 slot 状态块，放在左上角第 4 格（x=60）：

```text
黑    slot 窗口未就绪 / 线程没跑
黄    fLogFirst/fLogBlocks/fReady/fLock/fLogDma 就绪，写盘未成功
绿    至少一次 slot body + header 写成功（gH103SlotCursor++）
```

实现：

```text
NativeUfsProbe.cpp:  extern "C" volatile uint32_t native_h103_slot_state
                     h103SlotWrite(): ready 后置 1，header 成功后置 2
NativeLegacyDisplay.cpp: 读取该符号，fill(60,0,16,16,color)
```

候选：

```text
kernel:  4bd10ad1b1d3d205e4edb5661102e581bf4c8c551615104985bd3743e1b852f8
payload: 4692224ecbe160d584fab0bcb8b3d18f6e6d1076c53c7b42df202610fc077057
boot:    cccf4fad7c75a430ac15bf59538bcfc17432bebefeb5cb3388dcc24dc5902489
```

判读：

- 看到第 4 个块：证明 H103ff 内核在跑；
- 第 4 块黑：slot 线程/窗口未就绪；
- 黄：窗口就绪但写失败，按 console 的 `NATIVE_UFS_SLOT: attempt` 定位；
- 绿：slot 写成功，TWRP 应能看到 `slots_written` 增长。

## 82. H103fg：slot 块改成始终可见的状态色（2026-11-05）

H103ff 的第 4 块在 state=0 时是黑色，和第 3 块心跳的暗色一起看不见。
H103fg 改成：

```text
第 3 块心跳：白 / 橙交替（不再用黑）
第 4 块 slot：红 = 线程未进入（state 0）
              蓝 = 线程已进入但窗口未就绪（state 3）
              黄 = 窗口就绪但写失败（state 1）
              绿 = slot body + header 写成功（state 2）
```

`h103SlotThread()` 进入时先置 `native_h103_slot_state = 3`，这样即使窗口
永远不就绪，也能从红色变成蓝色，直接证明线程是否启动。

候选：

```text
kernel:  79a653767ab035a9c69068a810d96e0e4bdf781e3a7200734168262ace4556df
payload: 61b46a19fe95f018b6214f16c6d19f076a7c73c23e4b8ba5b1a973d3429771f3
boot:    e456efd8a12681b40131affe0d026c09bc8506cabc76fd13745b9c1c91c33b2a
```

## 83. H103fh：2 秒 slot 改由 UFS 完成路径驱动（2026-11-05）

H103fg 上机第 4 块为**蓝色**：`native_h103_slot_state=3`，slot 线程已经
进入，但 `fLogFirst/fLogBlocks/fReady/fLock/fLogDma` 一直没有全部就绪，
所以没到 state=1。结合日志：

- 只有 `NATIVE_UFS_HB: enter`，没有每 10 秒的 `NATIVE_UFS_ALIVE`；
- 20 秒的 `logThread` snapshot 也没有出现；
- 但 UFS 路径的 `late-window` snapshot 和 2×2 重绘正常。

结论：`kernel_thread_start` 创建的线程能打印入口，但 `IOSleep` 在此内核
不会醒来；心跳、logThread、slot 三个线程都卡住。H103fh 不再依赖线程：

```text
ufsCommand completion:
  (gUfsCommands & 63) == 0:
    native_legacy_test_pattern()       // 2x2，和 quiet 解耦
    if (!quiet) PROGRESS
  every completion:
    if 2 s elapsed && !gH103SlotBusy:
      h103SlotWriteThunk()
```

`h103SlotWrite` 内部会再发 UFS 写，完成路径会重入；`gH103SlotBusy`
阻止递归 slot。slot 线程保留但只做 state=3 的入口标记，随后睡眠不再影响。

候选：

```text
kernel:  f21ee606da951562994a75c0c243990ba096c14894ec3af33ac66838b5579feb
payload: 9953381de226ca1b1ceb5fb61c2a8aa12895d63f1557b89d062c96110a8629e3
boot:    36f6938ee1de01756706c7adbdb312e8fcb5de8702994b712c56bcd2a3410dfa
```

判读：第 4 块应从蓝色变成黄/绿；绿色表示 slot+header 写成功，TWRP 的
`slots_written` 应开始增长。

## 84. H103fi：slot tick 移到 fLock 之外（2026-11-05）

H103fh 停在 UEFI。原因是 slot tick 放在 `ufsCommand` 的完成路径，而
`readBlocks` 在调用 `ufsCommand` 时仍持有 `fLock`；`h103SlotWrite()` ->
`logWrite()` 再次 `IOLockLock(fLock)`，非递归锁自死锁，第一次 UFS 读就
不返回。

H103fi 把 `h103SlotTick()` 从 `ufsCommand` 移除，改放在：

```text
readBlocks():     IOLockUnlock(fLock); h103SlotTick();
readWindowBulk(): IOLockUnlock(fLock); h103SlotTick();
```

slot 写内部的 UFS 命令完成路径不再调用 tick，`gH103SlotBusy` 仍防止
并发重入。

候选：

```text
kernel:  b868e9007b5b93e7a3e287c00a828bbe5640bda2ae33153a931b1b13757146a5
payload: 90e6c1fc2b9926128dcc69bb6e292d3d31e05628e9ec8d0c76a2af9fd04b4f3c
boot:    cf87300170090acb019b5cdfc5f76157724824befef3e5dd1bf985f8eabbb393
```

判读：能正常进系统；第 4 块应从蓝色变黄/绿；绿色后 TWRP 的
`slots_written` 应增长。

## 85. H103fj：静默 2×2 + 2 秒 slot（2026-11-05）

H103fi 上机确认 slot 成功：`slots_written=109`、`rounds=109`、`state=3`、
`write_errors=0`，slot body 是 65s–264s 的实时 msg，第 4 块绿色。

H103fj 只做静默：

```text
gH103Quiet = 1
payload 去掉 -v、debug=0x14e、boot-progress=2
保留 sheng-log=1、native-cpufreq-early=2、offline-legacy-gop=1
2x2 重绘已在 UFS 路径且不受 quiet 影响
2 秒 slot tick 在 readBlocks/readWindowBulk 解锁后运行
```

候选：

```text
kernel:  d0b0089b5f53f8e720ce575a3f00aa3b637b959dac5468b8d636e10277a9516e
payload: c1da6c3ffc7f9fb2b7db57f59ac927db4c0725c864fb2c240612520ac65de444
boot:    85c34f005809eada4d6eb02284cc26bd9d540d232024e26388333120158fcf35
```

判读：屏幕不再持续滚动，右上 2×2 和左上 4 块保持，第 4 块绿色；
TWRP 的 `slots_written` 继续增长。若静默后 2×2 消失，说明还有 console
依赖，但当前重绘已与 quiet 解耦。

## 86. H103fk：slot 500 ms + msg 变化判断（2026-11-05）

H103fj 静默版正常。H103fk 提高 slot 更新频率：

```text
h103SlotTick():
  节流 500 ms
  只有 msgbufp->msg_bufx 变化时才写
  仍从 readBlocks/readWindowBulk 解锁后触发
```

按 247 个 slot 计算，历史约 2 分钟。写入量约 256 KiB/s，对 UFS 读影响
可接受。

候选：

```text
kernel:  90ed23031b45f195fca40f631cd7e9e7bfd45985e322fe7c88def7e8fce1d6cc
payload: 17b7894192bfaffdd91e40b21eb02b1b160a0cb51c12daeeb83dc918a508a8ed
boot:    f3c461aeb8510db31bb6d5e9c22dedb99c84e7e550dad100bdc1008cfb749626
```

判读：TWRP 最新 slot 应明显更新更快；`slots_written` 增长更快；2×2、左上
4 块和静默 console 保持。

## 87. H103fl：1 Hz 定时心跳 + slot A/B（2026-11-05）

H103fk 日志（`/home/ls/UniXNU/h103-log-20261105-121155.txt`）的最后一行是：

```text
[  477.213103]: KextLog: driverkitd is active
```

同一份日志已经包含：

```text
442s launchd boot tasks
450s SpringBoard/27
454s backboardd/55
462s IOMFB_FDR_Loader/78
477s driverkitd active
```

没有 panic、没有 UFS OCS timeout、没有 `NATIVE_UFS_LOCK` 超时；
`slots_written=121`、`write_errors=0`。H103fj（2 秒 slot）也在同一位置
停下，因此 500 ms slot 不是根因。

左上第 3 块是 UFS 活动指示：`drawTestPattern()` 只在每 64 条 UFS 命令和
10 秒心跳线程里调用，而后者停在 `IOSleep`。I/O 空闲时该块停住是正常现象，
不能据此判断内核挂死。

H103fl 只改 UFS 驱动，不改 display archive：

```text
h103-hb-timer=1  在 UFS 驱动里建 IOWorkLoop + IOTimerEventSource，1 Hz
                 调用 native_legacy_test_pattern()，给第 3 块一个独立时基
h103-slot=0/1/2  0=关闭 slot tick，1=500 ms，2=2 秒
logWrite()       锁改成 2 秒 lockWithTimeout，避免被卡死的读拖住
header           uptime_s 填最后成功 slot 的时间，write_errors 计数
```

两个候选（同内核，只差 payload 参数）：

```text
H103fl        kernel 44cea2a0...
              payload cfa7f7fb... boot 625be885...
H103fl-noslot payload c5985776... boot e9fdecef...
```

判读：

- 停住时第 3 块仍以约 1 Hz 闪 → workloop/内核活着，当前是显示/FDR 关口，
  不是 UFS 死机；
- 第 3 块完全静止，且日志没有 `NATIVE_UFS_HB_TIMER: fire=` → 定时器未运行
  或内核已挂；
- 若出现 `NATIVE_UFS_HB_TIMER: stall ...` → 有 UFS 命令在飞超过 5 秒；
- 对比 `H103fl` 与 `H103fl-noslot` 可排除 slot 写入对停点的影响。

## 88. H103fl 的定时器结果与 H103fm（2026-11-05）

H103fl 日志 `/home/ls/UniXNU/h103-log-20261105-124046.txt`：

```text
1500.266 NATIVE_UFS_HB: slotMode=1 hbTimer=1
1500.266 NATIVE_UFS_HB_TIMER: start loop=0xfffffff3d7a8f060 timer=0xfffffff3d79ff0e0
```

之后**没有** `NATIVE_UFS_HB_TIMER: fire=1`。IOTimerEventSource 的 start
成功，但 1 Hz 定时器从未触发，和 `IOSleep` 一样依赖 kernel thread 唤醒。
因此：

- 第 3 块静止时，不能判定内核死机；
- 停点前 slot 一直正常：`slots_written=125`、`uptime_s=167`、
  `write_errors=0`；
- `uptime_s=167` 与最后一条 msg `1667.565`（UFS 起点 1500.18）吻合，
  说明最后一次 slot 写就发生在最后一条日志时。

H103fl-noslot 串口截图停在 `logd_helper`（1651.9），但 H103fl 的 msgbuf
继续到 `driverkitd active`（1667.5）；noslot 只是控制台输出更早停止，
不能据此说它更早挂死。

H103fm 只改 UFS 驱动：

```text
h103-hb-timer=2   timer_call_alloc/timer_call_enter，1 Hz，在定时器中断
                  上下文调用 native_legacy_test_pattern()
header liveness   msg 不变时每 2 秒只重写 header，uptime_s 继续前进即
                  证明停点后仍有完成的 UFS 读
diag_*            export_first/blocks/bytes/generation/below 改名并填值
                  diag_flags bit0/1=in_flight，bit8+=timer fires
```

候选：

```text
kernel:  8b6da448afb00e64868bcee1c0f7bd49026a72f860663e0dfaf0c77fd9b52698
payload: 8bb388f503fe8ff97ca5a27db30eff6ff5bc2877ed009f02893b58f04c47fd58
boot:    fd9c21497e22d95381ee661c7cc5a1067014d673f100de0e0839910cf46d2e92
```

判读：

- 第 3 块 1 Hz 闪 → timer_call 生效，内核活着；`diag_flags` 的 bit8+
  会增长；
- 第 3 块仍静止且没有 `timer_call start` 后的 fire → 定时器中断路径也
  不可用；
- 停点后 `uptime_s`/`diag_cmds` 继续增长 → 系统没有死，只是显示/FDR
  关口空闲；
- `diag_cmds`/`uptime_s` 停在最后一条 msg → 更可能是真挂死或完全无 I/O。

## 89. H103fm 结果与 H103fn 的 post-root IOGPU 测试（2026-11-05）

H103fm 日志 `/home/ls/UniXNU/h103-log-20261105-132425.txt`：

```text
907.785 NATIVE_UFS_HB_TIMER: timer_call start 0xfffffff4dd1c3780
909.044 NATIVE_UFS_SLOT: attempt=1 ... fires=0
...
913.112 NATIVE_UFS_SLOT: attempt=8 ... fires=0
```

`timer_call` 也没有触发，前 8 次 slot 的 `fires=0`。所以
`IOTimerEventSource`、`IOSleep`、`timer_call` 三条周期路径在这套内核上
都不可用；第 3 块不应再当作 liveness 指示。

日志实际继续到：

```text
1072.856 KextLog: driverkitd is active
1073.197 UserEventAgent crossed thread count high watermark
1073.261 ... containermanagerd.system
1073.341 ... analyticsd
1074.195 ... misd
1075.605 ... containermanagerd
1076.640 ... eligibilityd
1077.425 eligibilityd/89 exec
```

UFS 起点 907.7，最后日志 1077.4，即 169.7 s；header：

```text
slots_written=123
uptime_s=169
diag_cmds=31170
diag_last_lba=0x18303140
diag_last_bytes=131072
diag_flags=2
diag_loops=1661
```

`uptime_s=169` 与最后日志同一秒，`diag_cmds=31170` 说明读路径一直工作到
停点。`diag_flags=2` 是最后一次 header 写入时有一个 window read 在飞，
但日志继续到 eligibilityd，不能据此判 UFS stall。

结论：第 3 块静止是定时器不可用，不是死机。系统停在已知的显示/FDR
关口，下一步回到显示 provider，而不是继续调 UFS 或定时器。

H103fn 是一个不改 display archive 的最小 post-root 测试：

```text
h103-load-iogpu=1
  在 native_boot_flags & 8（SpringBoard 已 exec）之后，从 UFS 读路径
  调用一次 OSKextLoadKextWithIdentifier("com.apple.iokit.IOGPUFamily")
  只打印 NATIVE_IOGPU_LOAD: begin/rc，不调用 A540 probe，不发布服务
```

候选：

```text
kernel:  98117070e625c96591991b0c61198192a15cbe89686f08619b1ba5fb17fa8190
payload: 3edc860a3a7008efce00d4601bcdc49738ac8d47a766e020c3fdc68701d023e1
boot:    7ba4b9a64256f7ed7825d82ffedbcd0e229a16ae0218765ebd8abefd37d163ac
```

判读：

- `rc=0`：IOGPUFamily 可以在 post-root 加载；下一步才考虑修 A540 probe
  的反向返回值判断并发布最小 `IOAcceleratorES`（会改 display archive，
  失败即回退）；
- `rc!=0`：post-root 也加载不了，需要把 IOGPUFamily 放进 prelink roots
  或改用户态加载时序；
- `begin` 之后日志停住：加载请求阻塞在读线程，记录后回退 H103fm。

## 90. P1：把 IOGPUFamily 放进 prelink roots（2026-11-05）

H103fn 的 `NATIVE_IOGPU_LOAD` 在 post-root（SpringBoard 已 exec）仍返回：

```text
Can't load kext com.apple.iokit.IOGPUFamily - requests to user space are disabled.
NATIVE_IOGPU_LOAD: rc=dc00800a
```

`dc00800a` 是 `kOSKextReturnDisabled`。根因是 `config/MASTER` 的
`NO_KEXTD`：`OSKext.cpp` 中 `sKernelRequestsEnabled=false`，所以任何未
内置的 kext 都不能通过用户态请求加载，与 pre/post-root 无关。

P1 只加 prelink root，不改 UFS/display 源码：

```text
Mac: ~/UniXNU-cheeseburger/board.toml
  roots += "com.apple.iokit.IOGPUFamily"
```

prelink 规划（原始 21H461 kernelcache）：

```text
当前 16 roots -> 29 components
加 IOGPUFamily -> 30 components
新增组件只有 com.apple.iokit.IOGPUFamily
__TEXT +30,884; __TEXT_EXEC +156,964; __DATA_CONST +32,368; __DATA +2,881
合计 +223,097 B（约 218 KiB）
现有组件 VA 不变；payload 仍有 23.3 MB 空闲
```

候选（native kernel 仍是 H103fn，display archive 未动）：

```text
kernel:  69885c070e883b7b1f8a156afe649b71fc6230c250277a632bf28e3cfb1f03d1
payload: 04f2fcee81bb27bdf05bd948050c83556764f5a05fec54aab51b4d8932e97077
boot:    bc34cb8e49fe81ee82f4c8ba7aefe6e25d6626f4a14a65eebf27db079171cfff
```

判读：

- `NATIVE_IOGPU_LOAD: rc=0`：prelinked `IOGPUFamily` 已被
  `sKextsByID` 注册，`OSKextLoadKextWithIdentifier` 命中已加载路径；
  下一步才改 A540（preModLoad/postModLoad 窗口 + 修 `if (ret)`）。
- `rc` 仍非 0：prelink 注册没有生效，先查 `kmod_info`/`OSKext` 注册，
  不动 display archive。
- 启动停在 `Waiting on IOMedia UUID 04769D26`：prelink 大小变化触发了
  Data/APFS 发布 race，回退 H103fn/H103fm。

注意：Mac 设备仓库 `board.toml` 本来就有一批未提交改动（slide
0x5000000、IOMobileGraphicsFamily、archives 等），P1 只在其工作树上追加
IOGPUFamily 一行；没有把这些改动一起提交。

### 90a. 设备仓库整理提交（2026-11-05）

设备仓库 `UniXNU-cheeseburger` 的工作树已按区域整理提交：

```text
2400c54 config: enable the warm UFS runtime, PMGR and graphics prelink
19d46d6 ufs: add the warm-link runtime and original storage bindings
6fef5db power: add the guarded PMGR build and glue
9ad41b0 adt: add A540 nodes and deterministic/root-auth inputs
2bf3c61 build: add the panic and early-progress patch tool
aa9bc99 chore: pin fetched sources and ignore external bring-up inputs
```

用户随后明确要求：与 `~/DinnerABC` 逐字节相同、且被构建依赖的文件要
提交到 GitHub，不再忽略。检查发现 **origin/main 已经在 `5ad54e2` 中跟踪
这 11 个文件**（内容与本地副本逐字节相同），同时还跟踪
`scripts/data/SystemVolume.im4p` 和 `scripts/cpu-tables.h`。Mac 本地
`main` 是另一条 6-commit 线，并且把 11 个文件 ignore 了；直接 push 会把
它们从 origin 删除。

处理结果：

- 11 个 DinnerABC 文件和 `SystemVolume.im4p` 从 `.gitignore` 移除并跟踪；
- 把 `origin/main` merge 进本地 H103 线，merge commit `1ca9258`；
- 冲突只有 `scripts/ShengPlatformPowerGlue.cpp`，保留本地短版本；
- `board.toml`、`defconfig`、`IOStorageFamily-bindings.json`、
  `patch-panic-only.py`、`unixnu.lock` 保留本地 H103 版本；
- `runtime/RootAuth.cpp` 按 origin 删除；`scripts/RootAuth.cpp` 仍在；
- `backup/h103-local-six` 保留合并前的 6 个 commit。

合并后的 `main` 已 push 到 GitHub：`c1e91be..1ca9258`。主仓库
`UniXNU` 的 `ffdcf31` 指向 `drivers/NativeMobileDisplay` 的
`53f5d20`；该 commit 不在 origin/main 线上，已 push 到
`lss717/GopFramebuffer` 的分支 `h103-a540`，superproject 指针可解析。
Mac 的 `origin` 已切换为 SSH。

## 91. P2：A540 在 preModLoad 窗口注册并发布（2026-11-05）

H103fo（只加 prelink root）结果：

```text
1176.405 NATIVE_IOGPU_LOAD: begin flags=8
1176.436 NATIVE_IOGPU_LOAD: rc=0 flags=8
```

prelinked `IOGPUFamily` 已进入 `sKextsByID`，`OSKextLoadKextWithIdentifier`
返回 0。P1 成立。

H103fp 的 display archive 改动：

```text
LegacyDisplayProbe.cpp:
  preModLoad(handle)
  native_legacy_display_static_init()
  native_gop_presenter_static_init()
  native_a540_accelerator_static_init()   <-- 新增，同一个窗口
  postModLoad(handle)
  native_a540_accelerator_probe()         <-- 发布服务

NativeA540AcceleratorProbe.cpp:
  删除 OSKextLoadKextWithIdentifier 和反向判断
  删除 probe 里单独的 static_init
  删除 MetalPluginName/MetalPluginClassName（裸 stub）
```

A1 的 `OSMetaClass::preModLoad() wasn't called for class
NativeA540AcceleratorProbe` 由此解释：A540 的构造函数没有和 display 类放在
同一个 pre/post 窗口里，而不是 IOGPUFamily 缺失本身。

候选：

```text
kernel:  12d7513a347bb4315ba46f6c1f663bc6db35e4fd61c83989c567df704d2375c4
payload: 8d6bf887c1af74c9f36dddc57d377d866c8c32ce720e4bc8b4eb4dde239b94e8
boot:    24bc548352aa0dfc991cfbcad14643c87aa382bcfb1dd4647c4522007cc1b8e6
```

判读：

- `NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)` 且 A540 块
  绿色：服务已发布，下一步看 backboardd/CA 的 client。
- `NATIVE_A540_ACCEL: init/platform failed`：`getResourceService()` 或
  `init()` 失败，记录 state=3。
- `attach/start failed`：state=4/5，看 provider 生命周期。
- 停在 `Waiting on IOMedia UUID 04769D26`：display archive 改动触发
  Data/APFS 发布 race，回退 H103fo（prelink 版）。

## 92. H103fq：按当前 prelink 重新生成 accelerator ABI（2026-11-05）

H103fp panic：

```text
NATIVE_LEGACY: preModLoad handle=0xfffffff38d40f0a0
panic: Kernel data abort
pc  = 0xfffffff0074f04d4
far = 0xfffffff006aeb698
```

`far` 是旧 `scripts/data/ioaccelerator-base-abi.json` 的
`metaclass 0xfffffff006aeb688 + 0x10`。旧 JSON 的 `candidate_sha256` 是
`da673101...`，当前 H103fp prelink 是 `12d7513a...`。旧 metaclass 不在
当前 IOGPUFamily 区间；`+slide=0x5000000` 落在 `__PLK_TEXT_EXEC` 的未映射
空洞，不能靠简单 rebase 修复。

新增 `scripts/audit-target-accelerator-base-current.py`：读取当前
`kernel.macho` + `kernel.json`，在 IOGPUFamily data 里找到 168-entry
vtable（相对 IOService 只改 [0,1,7]），解码 `getMetaClass` 得到真实
metaclass，再扫描构造函数/析构函数。当前 H103fp 结果：

```text
candidate    12d7513a...  (H103fp)
metaclass    0xfffffff00caeb688
vptr         0xfffffff00bd439a0
C2 aliases   0xfffffff00abd3b20 / 0xfffffff00abd3b40
D2           0xfffffff00abd3b64
getMetaClass 0xfffffff00abd3bac
```

把这些地址写回 `scripts/data/ioaccelerator-base-abi.json`，重建 display
archive。新的 `original-accelerator-bindings.S`：

```text
gMetaClass = 0xfffffff00caeb688
C2         = 0xfffffff00abd3b20
D2         = 0xfffffff00abd3b64
```

重建 kernel + prelink 后 IOGPUFamily extents 不变：

```text
__TEXT       0xfffffff00a312a40
__TEXT_EXEC  0xfffffff00abb9000
__DATA_CONST 0xfffffff00bd3f040
__DATA       0xfffffff00caead40
```

候选：

```text
kernel:  0cc2ec0454595b44bbc2f6541a345f8e9de8d567f749c1a7dab94e99c7a902fc
payload: 75ff3251ca43b457a2c7e8fde36ae7f273b6def2dbf75474dbf0057430158a4e
boot:    a7a240200c7fdc96a9ca3e369e3f1be073d61f40ff72c53bccf6e91bc41b484a
```

判读：

- `NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)`：A540 stub
  发布成功，下一步看 backboardd/CA client。
- 仍 data abort：确认 `far` 是否 `0xfffffff00caeb698`；若不同，重新跑
  `audit-target-accelerator-base-current.py`（prelink 布局又变了）。
- `Waiting on IOMedia UUID 04769D26`：display archive 改动触发 race，回退
  H103fo。

## 93. H103fq 早期 OSMetaClass panic 与 H103fr（2026-11-05）

H103fq 在 UFS probe 的 L5 之后 panic：

```text
panic: Kernel data abort
pc  = 0xfffffff00784f3d0   OSMetaClass::addInstance +0x30
x0  = 0xfffffff00caeb600
far = 0x0
```

`x0` 不是 A540 的 static init 路径，而是早期 UFS 对象构造时拿到的
metaclass 指针，落在新 IOGPUFamily `__DATA` 附近。H103fq 把
`IOAcceleratorES::gMetaClass` 用 `.globl` 绝对符号定义在
`0xfffffff00caeb688`（真实 prelinked IOGPUFamily 数据内），prelink/符号表
把这个 kernel 绝对符号当成了可绑定 target，早期对象的 metaclass 指针被
错误绑定。

H103fr 只改 `scripts/build-op5-legacy-display.py`：accelerator bindings
用 `.private_extern` 而不是 `.globl`。符号仍能解析 A540 的未定义引用，
但不再作为 kernel 导出/prelink 绑定候选。`nm`：

```text
fffffff00caeb688 a __ZN15IOAcceleratorES10gMetaClassE
```

（小写 `a` = private/local absolute，而不是之前的大写 `A`。）

候选：

```text
kernel:  0922e9d182674e9bc014c79611efd170667910a3b5c32518bfe82b4873b79268
payload: 455fd32c07acc61619824fb32e9b5a769bd99624ac1111cde3b1cb53cbd22d99
boot:    ec0d60362c3cd17d5d776fbe2c5a05be60530f43dc3607f5f96eb03a81eddeb1
```

判读：

- 能过 UFS probe 并出现 `NATIVE_LEGACY: probe enter`：符号污染假设成立，
  再看 `NATIVE_A540_ACCEL: published`。
- 仍在 UFS L5 后 panic：`x0` 若仍是 `0xcaeb600`，说明 prelink 绑定并非
  由导出符号触发，需要改用运行时 ABI 查找/属性 stub。

## 94. H103fr 结果：private 绝对绑定仍破坏早期类登记（2026-11-05）

H103fr 把 accelerator bindings 改成 `.private_extern` 后仍在上机同一位置
panic：

```text
NATIVE_UFS_GPT: L5 st=00 last=5ffff bs=1000
panic: Kernel data abort
pc  = OSMetaClass::addInstance +0x30
x0  = 0xfffffff00caeb680
x21 = 0xfffffff00caeb600
far = 0x0
```

`.private_extern` 只把 `IOAcceleratorES::gMetaClass` 从导出符号变成私有
绝对符号，地址仍是 IOGPUFamily `__DATA` 的 `0xfffffff00caeb688`。早期
UFS 对象构造时拿到的 metaclass 指针落在这个 IOGPUFamily 数据区，说明
本地 `IOAcceleratorES` 子类的绝对基类绑定会破坏 prelinked IOGPUFamily
的类元数据/实例登记，而不是单纯的符号表导出问题。

因此 H103fp/H103fq/H103fr 都不能作为候选；H103fo（prelinked IOGPUFamily、
`rc=0`、不发布 A540）仍是当前可用基线。

下一步不再使用本地 `IOAcceleratorES` 子类 + 绝对地址，改为：

1. property-only `IOService` stub：只设 `IOClass=IOAcceleratorES`，
   完全不绑定 accelerator 基类；先验证 backboardd/CA 是否按属性发现。
2. 或在运行时解析真实 `IOAcceleratorES` 基类/metaclass，再构造服务。

## 95. H103fs：property-only accelerator stub（2026-11-05）

H103fr 的 private 绝对绑定仍然在早期 `OSMetaClass::addInstance` 破坏
IOGPUFamily 类元数据。H103fs 彻底去掉本地 `IOAcceleratorES` 基类：

```text
class NativeA540AcceleratorProbe : public IOService
  start(): setProperty("IOClass","IOAcceleratorES")
           setProperty("A540Probe","minimal-no-hardware")
```

`LegacyDisplayProbe.cpp` 仍在同一个 `preModLoad`/`postModLoad` 窗口调用
`native_a540_accelerator_static_init()`，但现在是普通 IOService 子类；
`native_a540_accelerator_probe()` 只负责 attach/start/register。

由于 A540 对象不再引用 accelerator bindings，`original-accelerator-bindings.o`
不会被静态链接器拉入；final kernel `nm` 中已无 `IOAcceleratorES` 绝对符号。

候选：

```text
kernel:  ae7b40a74143a86712d45221a76d6609a70a22c1c0ef886edaf024fb5892144c
payload: 90e6802e44c124b898f5dff3a4bdc65f700ca8da6ebf4d32bef67f8050842b6e
boot:    09c31cc705e32a2c37a5c7a2bf29735d3a7e3d8edfdd11e4a3482bcdfb7fcb39
```

判读：

- 过 UFS probe、`NATIVE_LEGACY: probe enter`、`NATIVE_A540_ACCEL:
  published`：服务已发布；A540 块应变绿。
- 2×2 client 不变：CA 可能只按真实类匹配，property stub 不够；下一步
  才做运行时真实基类解析。
- 仍在 UFS L5 后 panic：说明不是 accelerator bindings，需回看 2×2
  改动本身的 archive 布局/早期类注册。

## 96. H103fs 结果与 H104a：延迟 A540 发布（2026-11-05）

H103fs 日志：

```text
16.893 NATIVE_LEGACY: probe enter
16.903 NATIVE_A540_ACCEL: published IOAcceleratorES (probe only)
163.540 SpringBoard/27 actual exec
167.782 NATIVE_EXEC pid=55 ... xpcproxy ... com.apple.backboardd
175.327 IOMFB_FDR_Loader
191.806 KextLog: driverkitd is not active
```

没有 `comm=backboardd` 的实际 exec；2×2 左上角是绿色（SpringBoard only），
其余三块灰色。说明 property-only A540 服务在 pre-root 阶段发布后，
driverkitd/backboardd 的交接停在 `driverkitd is not active`。

H104a 只改发布时机：

```text
LegacyDisplayProbe.cpp:
  preModLoad -> display/presenter/A540 static init -> postModLoad
  删除 native_a540_accelerator_probe() 的早期调用

NativeUfsProbe.cpp:
  h103SlotTick() 在 native_boot_flags & 4（backboardd exec）后
  调用一次 native_a540_accelerator_probe()
  IOLog("NATIVE_A540_PUBLISH: rc=%d flags=%x")
```

A540 类仍在 display probe 的 pre/post 窗口注册；服务在 backboardd 真正
exec 后才出现，不再干扰 driverkitd 的早期匹配。

候选：

```text
kernel:  c5023e1e481488852a1f83ed9bd632976c146a45cbdf47a34adede6b95f082cb
payload: 58d7463c2dcc0bbebc5e37a3e3aa89a4059b5da115df31adc6cfef4c5364c3a2
boot:    72a06e3965a012139e50f61546f1729afbd9e49c605ae5f07764b0af34fed78b
```

判读：

- `NATIVE_EXEC ... comm=backboardd` 出现、2×2 左上白：提前发布确实是
  阻塞点，H104a 修复了交接。
- 随后 `NATIVE_A540_PUBLISH: rc=6 flags=4` 且 client 块变化：property stub
  被发现。
- 仍停在 `driverkitd is not active`：不是提前发布导致，回到 display
  archive/IOKit 匹配排查。

## 97. H104a 结果与 H104b：移除 A540 类注册（2026-11-05）

H104a 日志：

```text
170.059 SpringBoard/27 actual exec
170.119 NATIVE_IOGPU_LOAD: begin flags=8
170.150 NATIVE_IOGPU_LOAD: rc=0 flags=8
182.196 driverkitd actual exec
183.236 IOMFB_FDR_Loader
199.295 KextLog: driverkitd is not active
```

没有 `NATIVE_A540_PUBLISH`（bit 4 从未置位），也没有 `comm=backboardd`
实际 exec；2×2 左上仍是绿色。延迟服务发布没有改变停点。

H103fo（prelinked IOGPUFamily，display archive 无 A540 static init）能到
`driverkitd is active`；H103fs/H104a 都在 display probe 的 pre/post 窗口
调用 `native_a540_accelerator_static_init()`。因此 H104b 移除这次调用：

```text
LegacyDisplayProbe.cpp:
  删除 native_a540_accelerator_static_init() 和 probe 声明
  只保留 display/presenter static init

NativeUfsProbe.cpp:
  删除 h103MaybePublishA540() 和调用
```

A540 对象仍在 display archive 里（archive 成员集合不变），但不再注册；
final kernel 里仍有未使用的类符号，但没有 `OSMetaClass` 注册/实例。

候选：

```text
kernel:  5ec6ddd29fe941883fb3777e15d5a27040c910ae4569bdc24610f943c3fa0e40
payload: 4dda07372741ebc7b65a0f6cf873c974fc9c670b8f167f4ca55eeebb68ee84dd
boot:    8cc632f2f1fc12714fd7a05fae6a76face35ac73714962db5f2b19171688dcec
```

判读：

- 恢复到 `driverkitd active`、`comm=backboardd`、2×2 左上白：A540 类
  注册确实是 driverkitd 交接的阻塞点。
- A540 块黑色是预期（没有 probe）；下一步要么做 post-userland 的
  独立类加载，要么先回到 backboardd/显示 provider。
- 仍停 `driverkitd not active`：A540 类注册也不是原因，需比较
  H103fo/H103fs 的其余 display archive 差异。

## 98. H104b 结果与 H104c：FDR client selector 跟踪（2026-11-05）

H104b 是 A540 类注册移除后的干净基线，恢复到已知显示关口：

```text
348.590 NATIVE_LEGACY: probe enter
495.270 SpringBoard/27
519.691 backboardd/55 实际 exec
526.480 NATIVE_DISPLAY_OPEN service=NativeLegacyDisplay
        process=IOMFB_FDR_Loader grant=backboardd match=0
526.505 NATIVE_LEGACY: client enter pid=78 comm=IOMFB_FDR_Loader type=0
526.527 NATIVE_LEGACY: client observed status=0
531.238 KextLog: driverkitd is active
```

2×2：白（SpringBoard+backboardd）/黄（IOMFB_FDR client）/蓝（calls<10）/
灰（无 transfer/swap/IKit match）。A540 块黑（未 probe）。

这说明：

- A540 类注册确实是 H103fs/H104a 的 driverkitd 交接阻塞点；
- 移除后 backboardd 能实际 exec，系统到 `driverkitd active`；
- 显示由 **IOMFB_FDR_Loader** 先打开，backboardd 仍未打开；
- loader 只做了少量 selector，没有 transfer。

H104c 在 `LegacyDisplayProbe.cpp` 的 `wrappedExternal` 里增加前 16 次
selector 日志：

```text
NATIVE_LEGACY: client sel pid=78 selector=<n> status=<x>
```

候选：

```text
kernel:  365f6f6eb22bb2331a386d7b179a113bb57bb55bf219a917fa7475ef2206a22b
payload: fc455727471d8c5be0e006029741fed79b6e59a1d792ffac91a14b7dca7f6d22
boot:    e3ba65d79b7c8f62c24e8d0ef2a62c983517df979e478a550b0b5bb3e3fd80ef
```

判读：

- 有 selector 非 0 或序列中断：定位到具体 FDR selector，下一步补实现/
  检查参数。
- selector 全 0 但不再增加：loader 在等外部 kext/数据，转查 FDR 依赖。
- selector 正常但 backboardd 仍不开显示：转 backboardd/CoreAnimation
  provider 等待，而不是继续 FDR selector。

## 99. H104c 第二次结果与 H104d：backboardd matching 跟踪（2026-11-05）

H104c 第二次上机（16:33 日志）已经越过上次的抓取点：

```text
189.199 NATIVE_DISPLAY_OPEN service=NativeLegacyDisplay
        process=IOMFB_FDR_Loader grant=backboardd match=0
189.226 NATIVE_LEGACY: client enter pid=78 comm=IOMFB_FDR_Loader type=0
189.251 NATIVE_LEGACY: client observed status=0
189.276 / 189.303 再次 IOServiceOpen
199.026 KextLog: driverkitd is not active
199.466 KextLog: driverkitd is active
```

关键结论：

- FDR loader 确实打开了 Legacy display，并创建了一个 user client；
- 但没有任何 `NATIVE_LEGACY: client sel`，即 loader **没有调用任何
externalMethod selector**；selector 日志不是当前阻塞点。
- 2×2 右下下半由灰变**橙**：`native_boot_flags & 128`，说明 backboardd
  已经开始做 IOKit matching，只是匹配的类不含 `IOMobile`。

H104c 之前 IOKit trace 只设置 bit 128，不打印匹配内容。H104d 在
`patches/xnu/log-iokit-trace.patch` 里增加前 32 次日志：

```text
NATIVE_IOKIT_MATCH: class=<IOClass> provider=<IOProviderClass>
    name=<IONameMatch> found=<0/1> count=<n>
```

候选：

```text
kernel:  009631ae5ed1e6c72ce7d4855374a2a1f74b960c2f42d1e72921ea807559af12
payload: 88de84fdf0b90bde8e6440d5568a9e6cdae673f1d173fe1fa79ff8f94861ce14
boot:    9a7afb45b214a1db31e3099aba6615219a9504bf55c593a383b7e859d7a5cbbb
```

判读：

- 出现 `class=IOGPU`/`IOAcceleratorES`/`IOAccelerator`：backboardd 在等
  加速器/GPU 服务，下一步提供该服务或让 CA 接受现有 provider。
- 出现 `class=IOMobileFramebuffer*`/`IOFramebuffer` 但 `found=0`：显示
  服务匹配/属性问题。
- 三个字段全是 `-`：matching dictionary 使用其他键，下一版打印完整 XML。

## 100. H104d 结果与 H104e：真实 IOAcceleratorES/IOGPU 服务（2026-11-05）

H104d 多次上机都停在同一处：左上绿色（SpringBoard 已 exec），始终不到
左上白（backboardd 实际 exec），`NATIVE_IOKIT_MATCH` 从未打印。H104d 的
kernel text/layout 改动把 backboardd 之前的停点带回来了；停止使用 H104d，
恢复 H104c 的 flag-only IOKit trace。

离线检查 21H461 OS cryptex 的字符串，确认目标类：

```text
Metal strings:      MTLRegisterDevices ... IOAcceleratorES
QuartzCore strings: CAEnableMetalWhippet ... IOAcceleratorES
```

所以 backboardd/CoreAnimation 找的是 `IOAcceleratorES`，不是 IOMobile*。
H104a 的 property-only stub 只把 `IOClass` 设成 `IOAcceleratorES`，不是
真正的类实例，被 CA 忽略是合理的。

H104e 用 prelinked 的真实类，不注册本地子类：

```text
NativeA540AcceleratorProbe.cpp:
  native_iogpu_accel_probe()
    OSMetaClass::allocClassWithName("IOGPU")
      fallback OSMetaClass::allocClassWithName("IOAcceleratorES")
    attach(IOService::getResourceService())
    registerService()
    h103-iogpu-start=1 才调用 start()

NativeUfsProbe.cpp:
  h103MaybePublishIogpu()，只在 native_boot_flags & 4 后调用一次
```

A540 状态块：绿=register 成功，红=alloc/attach/start 失败，黑=未运行。

```text
kernel:  bdb070e20c8cd55b6e4d7577d14c625464354fd06325c79316103bf96ddce50a
payload: e15f7962d99069be89f35a73cf99554c8d62fc8b5025765272d90de429d4a67c
boot:    108a5181ec655665fc9bead733c6674fe328ee538c7feb84db2674c215c21130
```

判读：

- 左上白恢复：H104d 的停点是 layout 回归，H104e 已回到 H104c 基线路。
- `NATIVE_IOGPU_ACCEL: class=IOGPU object=0`：真实 IOGPU 类不可分配
  （抽象/未注册），需要换类或补 provider。
- attach/register 成功但 CA 仍不打开：真实类已发布，但 CA 还需要
  accelerator 属性/ABI 或 user client；下一步补属性或检查 CA 的 open。
- 如果 H104e 又停在左上绿：说明新增 archive 代码也触发同一 layout
  停点，需要把探针拆到更晚的独立 kext/窗口。

## 101. 左上白的 launchd 顺序 race 与 H104b 对照（2026-11-05）

H104e 仍是左上绿；A540 黑，说明 backboardd 没 exec，真实 IOGPU 探针没有
运行。把成功和失败日志的启动顺序对齐：

```text
H104b 白:
  506.100 driverkitd actual
  508.025 IOMFB_FDR_Loader exec
  519.691 backboardd actual
  526.480 loader opens display

H104c 白:
  176.119 driverkitd actual
  177.183 IOMFB_FDR_Loader exec
  187.883 backboardd actual
  189.198 loader opens display

H104d 绿:
  283.818 IOMFB_FDR_Loader exec
  284.079 driverkitd actual
  (no backboardd actual)
```

失败时 loader 比 driverkitd 早 0.26s；成功时 driverkitd 早约 1.0–1.1s。
因此左上白不是显示颜色随机，而是 launchd 启动顺序的 race：loader 抢跑后
占住显示，backboardd 就卡在 exec 之前。H104b 也多数失败，说明不是
H104c/H104e 的独立回归。

两个仅改 boot args 的 H104b 对照：

```text
boot-H104b-slot0.img    h103-slot=0        关闭持久化日志/slot 写入
boot-H104b-noiogpu.img  h103-load-iogpu=0  不加载 IOGPUFamily
```

```text
slot0:   1aa9829522cf7f79713dc8ce577c084f83c564485c5f41aa35025ee2556e7fc0
noiogpu: 90b8d14229944b5308d0995b5371472a4abaab2fc233b39e6685ab141f455aae
```

判读：

- `slot0` 稳定白：slot 写入/UFS 争用让 driverkitd 输掉 race，先关闭/后移
  持久化日志。
- `noiogpu` 稳定白：IOGPUFamily load 影响时序，先不加载它，白稳定后再加回。
- 两者都绿：做 H104f，在 `NativeLegacyDisplay::newUserClient` 里对
  `IOMFB_FDR_Loader` 返回 `kIOReturnNotReady`，直到 `native_boot_flags & 4`，
  让 loader 在 backboardd 之后重试 open。

## 102. slot0 稳定白与 H104f：推迟 slot 写入（2026-11-05）

上机结果：`boot-H104b-slot0.img`（`h103-slot=0`）**能稳定左上白**。这确认
早期 slot/UFS 写入是 launchd race 的变量：写入让 driverkitd 输掉，
`IOMFB_FDR_Loader` 抢跑并占住显示，backboardd 不 exec。

H104f = H104e（真实 IOGPU/IOAcceleratorES 探针）+ slot 写入 gate：

```text
NativeUfsProbe.cpp:
  h103SlotTick:
    h103MaybeLoadIogpu();
    h103MaybePublishIogpu();
    if (!(native_boot_flags & 4)) return;   // no slot/header write yet
    ... original write path ...

  h103SlotThread:
    IOSleep(2000);
    if (native_boot_flags & 4) h103SlotWriteThunk();
```

心跳线程/2×2 不依赖 slot mode，继续运行。消息缓冲区在等待期间累积，第一次
post-backboardd 写入会把早期日志一起落盘。

```text
kernel:  fbbc84592a7b099e27c68627917433d471da53a5c74acb86d04f451245209fde
payload: bf806aa279e88b3ed0dcc872826218515be8f71cae39caa5b0bc449da5accd48
boot:    7a76334f2ff0d43d7f6ee087d7132c88926716d87f1b151ce081a67c9f543232
```

判读：

- 左上稳定白：race 解决，持久化日志恢复。
- 日志出现 `NATIVE_IOGPU_ACCEL`：看真实类是 alloc 成功还是失败、A540
  块绿/红。
- 如果 post-backboardd 的大块日志 dump 拖慢 loader open：把首次 dump 拆成
  多块或限制单次写入量。

## 103. H104f 结果与 H104g：真实类探测（2026-11-05）

H104f 上机：左上稳定白，slot 写入 gate 生效，持久化日志在 backboardd 之后
恢复。19:05 日志：

```text
181.469 SpringBoard actual
192.322 driverkitd actual
193.359 IOMFB_FDR_Loader exec
204.481 backboardd actual
204.521 NATIVE_IOGPU_ACCEL: class=IOAcceleratorES object=0 service=0
204.543 NATIVE_IOGPU_PUBLISH: rc=0 flags=f
207.863 NATIVE_UFS_SLOT: attempt=6 ...
```

`OSMetaClass::allocClassWithName("IOGPU")` 和 fallback
`"IOAcceleratorES"` 都返回 0。二者要么是抽象类，要么未注册为可分配类。
A540 块应为红。

H104g 逐个探测：

```text
IOGPU
IOGPUDevice
AGXAccelerator
IOAcceleratorES
IOGPUFamily
```

每次打印 `name/mc/obj/service`；找到第一个非空 `IOService` 后
attach(getResourceService()) + registerService()，`start()` 仍只在
`h103-iogpu-start=1` 时调用。

```text
kernel:  26956e603bb39ad001738b3b79a373409737bb00367d90ef8f30ba8c2306bb90
payload: 4946a49a82ba03ed53f554b09cd62004f3ecd89cc00e0356dc1bfcffcb4ebf6f
boot:    c2574fe9f71574839cd24a630eb725573b22067e12f093efab73f557f2ef459a
```

判读：

- 某个类 `obj/service` 非 0：真实 concrete 类可分配；attach/register 后
  看 A540 和 CoreAnimation 的反应。
- 全为 0：当前 prelink 的 IOGPUFamily 没有可分配 concrete 类；下一步转向
  安全的本地 `IOAcceleratorES` 子类或提供 provider，而不是继续找类名。

## 104. H104g 结果与 slot0+noiogpu 组合（2026-11-05）

H104g 照片/日志仍停在 `driverkitd is active`，左上绿，backboardd 没有实际
exec；多类 probe 没有运行。H104g 的多类代码/字符串再次改变了 archive/kernel
布局，输掉了 pre-backboardd race。放弃 H104g。

H104b-slot0 的照片显示：有时仍会停在左上绿，但也能到左上白；到白后
右上/右下仍灰，控制台停在 `driverkitd is active`，没有显示 open。因此
slot0 只解决 backboardd 之前的 race，白之后还有一个 driverkitd/FileSet
与显示 open 的 race。

新增组合对照：

```text
boot-H104b-slot0-noiogpu.img
h103-slot=0 h103-load-iogpu=0
SHA-256: 7928c93baab2727ebdba8db9454e573e7b889a4a42ccbaa62aca6af172a4cd5a
```

无持久化日志，2×2/心跳仍运行。判读：

- 白 + 显示 open（右上黄/深蓝、屏幕变化）：slot 写入和 IOGPUFamily load
  两条时序因素都相关，之后逐个加回。
- 白 + 仍灰/停 driverkitd active：post-white 卡点是 driverkitd/FileSet，
  与 slot/IOGPU 无关。
- 左上绿：pre-backboardd race 仍在，重试。

## 105. slot0+noiogpu 结果与 H104i 进程状态 dump（2026-11-05）

`boot-H104b-slot0-noiogpu.img` 上机：左上白，右上/右下灰；白后等约 10 分钟
不变，无显示 open。控制台继续到 `datamigrator` 等，loader/backboardd 没有
`NATIVE_EXIT`。因此白之后的卡点与 slot 写入、IOGPUFamily load 都无关；
loader/backboardd 是活着但被阻塞。

H104i 在 `osfmk/kern/task.c` 加只读 helper：

```c
void native_proc_state_dump(void);
```

它按 PID 找 78/55/63/1，dump 每个线程的 tid/state/wait_event/
continuation/parameter/options。UFS 心跳线程在 backboardd 实际 exec 后
30–40 秒调用一次。镜像继续 `h103-slot=0 h103-load-iogpu=0`，无持久化日志，
dump 打在控制台。

```text
kernel:  b68d99796e1496c3b9b45b183498a5e11892b77423fb23884a181f2778cddfc3
payload: d99ad12648e7603b4f566ef68f5d258ec11a74f3016f7ca93bc9d4f12ad8d4a3
boot:    4647216c5ddb03c43d5118b9db577402250a630d0382460b5b034600e20278e1
```

判读：

- loader/backboardd 的 state/wait_event/continuation 若相同：定位共同等待点；
- loader 在 IOKit/mach 等待：查对应 service；
- 两者 running 但未 open：查用户态/launchd 依赖。

## 106. H104i 结果与 H104j：dump 前置/非阻塞（2026-11-05）

H104i 上机：左上白，2×2 右上黄、左下蓝，日志出现

```text
NATIVE_DISPLAY_OPEN: service=NativeLegacyDisplay
        process=IOMFB_FDR_Loader grant=backboardd match=0
NATIVE_LEGACY: client enter pid=78 comm=IOMFB_FDR_Loader
```

说明 loader 这次成功打开了显示。但 10 分钟后没有 `NATIVE_PROC_DUMP`，也没有
后续 `NATIVE_UFS_ALIVE`，说明心跳线程停在 2×2 draw 或 dump 的
`task_lock` 上。

H104j：

- dump 移到 `native_legacy_test_pattern()` 之前；
- `native_boot_flags & 4` 后不再 draw 2×2，避免 loader open 持有显示锁时
  卡住心跳线程；
- `task_lock` 改为 `task_lock_try`，失败打印 `task lock busy`；
- dump 增加 begin/find/end 日志。

```text
kernel:  7e85bc444764676f410ba0481826044eaf9056962386f35727f75a627fdf04c3
payload: e2033722ca0ca18a4575e481c14ff69a58240dba38e9ef3be216e7504c959dfb
boot:    3f161865f038d47891ab9724b70fb98f111ea627590b9585b91dea6388ef9f35
```

判读：白后 30–40 秒应出现 `NATIVE_PROC_DUMP: begin/find/...`。2×2 可能停在
backboardd 之前的状态，这是预期；以控制台 dump 为准。
