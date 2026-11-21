# 源码与补丁

UniXNU 从固定版本的 Apple 源码构建 XNU，并按各 series 文件记录的显式顺序应用补丁。

## 源码

`feeds.toml` 固定源码：

| 源码 | tag | 用途 |
| --- | --- | --- |
| `xnu` | `xnu-10063.141.1` | 内核源码 |
| `libplatform` | `libplatform-316.100.10` | 平台头文件 |
| `libdispatch` | `libdispatch-1477.100.9` | dispatch 头文件 |
| `AvailabilityVersions` | `AvailabilityVersions-141.1` | availability 宏 |
| `libpthread` | `libpthread-519.120.4` | 源码 pthread 组件 |
| `corecrypto-2023` | commit `11fba65` | 源码 corecrypto 组件 |
| `IOStorageFamily` | commit `e45fbe3` | 块驱动的公开存储头文件 |
| `edk2` | `release/202608` | package 和固件的 EDK II 基础 |

XNU 条目还包含：

```toml
darwin = "23.6.0"
version = "10063.141.1"
driverkit_tag = "xnu-10063.121.3"
trustcache_tag = "xnu-8796.101.5"
```

`driverkit_tag` 提供当前 tag 缺失的 `iokit/DriverKit` 头文件，`trustcache_tag` 提供 `EXTERNAL_HEADERS/TrustCache`。

## 补丁应用

`scripts/build-xnu-4k-baseline.sh` 对 `.cache/xnu-work` 应用补丁：

1. 存在时反向应用与更早上下文重叠的补丁：
   - `patches/xnu/boot-progress.patch`
   - `patches/xnu/native-gpu-addon-mount.patch`
2. 校验并应用 `patches/xnu/series` 中的每一项。
3. 校验并应用 `kits/NativePrelink/patches/series` 中的每一项。
4. 已应用的补丁跳过。
5. 运行 `prepare-xnu-source.py` 恢复缺失头文件。

series 文件是唯一顺序来源。重复项、列出的缺失补丁和未列入 series 的 `.patch`
都会使构建失败。文件名描述功能，不再控制顺序；补丁之间的顺序依赖记录在
`patches/xnu/README.md`。

补丁通过统一 series 检查器实现幂等应用：

```sh
python3 scripts/apply-patch-series.py --root patches/xnu apply \
  --worktree .cache/xnu-work --skip-applied
```

`--check` 在部分应用前停止构建。

## 补丁目录

| 目录 | 内容 |
| --- | --- |
| `patches/xnu/` | 内核补丁 |
| `patches/libpthread/` | 源码 pthread 补丁 |
| `patches/mesa/` | Turnip 和 Mesa 构建补丁 |
| `kits/NativePrelink/patches/` | 预链接 ABI 补丁 |

设备仓库可以加入 `patches/` 模块，构建树把它链接到 `tree/patches/`。模块中每个
新增的 `.patch` 都必须列入该模块的 series 文件。

## 新增补丁

1. 构建一次内核，生成 `.cache/xnu-work`。
2. 编辑 `.cache/xnu-work` 中的源码。
3. 生成补丁：

```sh
git -C .cache/xnu-work diff -- <paths> > patches/xnu/my-change.patch
```

4. 在 `patches/xnu/series` 的正确位置加入 `my-change.patch`。
5. 再次运行 `unixnu build kernel`。未列入 series 的文件会被检查器拒绝。

新增构建选项的补丁参考 `native-aes-personality.patch`：

```c
#if defined(XNU_MY_OPTION) && XNU_MY_OPTION
    "   ,{"
    "     'IOClass'         = MyDriver;"
    "     'IOProviderClass' = IOPlatformDevice;"
    "   }"
#endif
```

对应的 `-DXNU_MY_OPTION=1` 来自内核脚本的 `EXTRA_MAKE_ARGS`。

## 构建开关

| 开关 | 值 |
| --- | --- |
| `SDKROOT` | `iphoneos` |
| `ARCH_CONFIGS` | `ARM64` |
| `MACHINE_CONFIGS` | `BCM2837` |
| `KERNEL_CONFIGS` | `DEVELOPMENT` |
| `ARM64_LINK_ADDR` | `0xfffffff007004000` |
| `ARM64_PLKSEG_ADDR` | `0xfffffff004004000` |
| `DEPLOYMENT_TARGET_FLAGS` | `-miphoneos-version-min=17.0 -DXNU_TARGET_OS_IOS` |
| `BUILD_LTO` | `0` |
| `BOUND_CHECKS` | `0` |

`BCM2837` 携带 4 KiB 页布局。`BUILD_LTO=0` 保持目标文件和编译记录可读，并与外部静态库链接兼容。

## defconfig 映射

每个 `CONFIG_XNU_<NAME>` 变成 `XNU_<NAME>`：

| defconfig 值 | 构建值 |
| --- | --- |
| `y` | `1` |
| `n` | `0` |
| `"text"` | `text` |
| `123` | `123` |
| 字符串中的 `{tree}` | 构建树路径 |

内核脚本读取这些变量并加入目标文件开关、静态库和链接输入。

## 源码树

```
out/<board>/tree/
  refer/xnu/                 固定源码
  .cache/xnu-work/           工作克隆
  .cache/fakeroot/           内核 SDK 根
  .cache/sources/            恢复头文件清单
  build/xnu/ios-obj/         目标文件和编译记录
  build/xnu/ios-sym/         符号
  build/xnu/ios-dst/         安装头文件
  patches/xnu/               链接的补丁
  kits/NativePrelink/        预链接工具和补丁
```

## 更新源码

1. 在 `feeds.toml` 中设置新的 `ref` 和 `commit`。
2. 更新 `darwin`、`version`、`driverkit_tag` 和 `trustcache_tag`。
3. 把补丁 rebase 到新 tag。
4. 按新的编译记录更新 `[kernel] archives` 中的静态库脚本。
5. 重建预链接并重新验证 kernelcache 固定。

预链接输出依赖原始 kernelcache ABI。新的源码版本可能需要新的 kernelcache 固定和 roots。

## 下一步

- [4 KiB 页表](/zh/xnu/four-k-page-tables)
- [补丁参考](/zh/xnu/patch-reference)
- [构建内核](/zh/guide/build-kernel)
