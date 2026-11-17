# 一加 5（cheeseburger）显示测试图案颜色含义

`NativeLegacyDisplay` 在 framebuffer 右上角画一块 2×2 面板，用来在不依赖用户态的情况下
指示启动推进到哪一步、显示客户端有没有建立、帧有没有提交。本页说明每个格子的每种颜色
到底代表什么。

- 实现：`drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp` 的 `drawTestPattern()` 与
  `drawHeartbeatCell()`；
- 重绘调度：`drivers/NativeUfsProbe/NativeUfsProbe.cpp`；
- 标志位：`patches/xnu/zzzzzzzz-h103-boot-flags.patch`、
  `patches/xnu/zzzzzzzzz-h103-exit-flags.patch`、
  `patches/xnu/zzzzzzzzzz-h103-iokit-trace.patch`。

> USB CDC 实时串口日志、UXL1 解码和普通重启命令见
> [USB CDC 串口日志与普通重启使用说明](usb-com-log-guide.md)。

![测试图案色卡](/panel-colors.svg)

> 上图为面板实际使用的像素值。颜色以十六进制为准；正文里的颜色名称只用于阅读。

## 位置与重绘

| 项目 | 取值 |
| :--- | :--- |
| 位置 | framebuffer 右上角，`x0 = w - 2 × panel`，`y0 = 0` |
| 面板尺寸 | 每格 128×128；右下格再水平对半切成 128×64 |
| 分辨率不足时 | `panel = min(128, w/2, h/2)` |
| 重绘 | 默认在 UFS 心跳线程里：backboardd 未 exec 时约每 1 秒，`h107GateOpen()` 之后约每 10 秒；backboardd exec 之后只在 `native_boot_flags & 0xfff` 变化时重绘一次 |
| 1 Hz 重绘 | `h103-hb-timer=1`（`IOTimerEventSource`）或 `h103-hb-timer=2`（`timer_call`） |
| 关闭面板 | `h103-skip-pattern=1` |

> ⚠️ 任何用户客户端提交第一帧后，面板会被帧内容覆盖，而且默认不再恢复。
> 屏上看不到面板、或颜色停在旧值，都不代表显示后端停止工作；精确结论要看
> `plans/oneplus5-cheeseburger/STATUS.md` 和持久日志。

## 2×2 主面板

### 左上格：用户态启动推进

按下列顺序判读，命中即停。`0x20`、`0x40` 是粘滞位：一旦置位，进程之后重启也不会回落。

| 颜色 | 像素值 | 标志位 | 含义 |
| :--- | :--- | :--- | :--- |
| 紫 | `#8000FF` | `& 0x20` | SpringBoard 已退出（`kern_exit` 钩子，不区分是否崩溃） |
| 品红 | `#FF00FF` | `& 0x40` | backboardd 已退出（SpringBoard 未退出时可见） |
| 白 | `#FFFFFF` | `0x08` 且 `0x04` | backboardd 与 SpringBoard 都 exec 过，且都未退出 |
| 绿 | `#00FF00` | `& 0x08` | 仅 SpringBoard exec 过 |
| 天蓝 | `#0080FF` | `& 0x04` | 仅 backboardd exec 过（SpringBoard 尚未 exec） |
| 橙 | `#FF8000` | `& 0x02` | 仅 driverkitd exec 过 |
| 黄 | `#FFFF00` | `& 0x01` | 仅 logd_helper exec 过 |
| 红 | `#FF0000` | 以上均无 | 用户态尚未推进；面板能出现即说明 GOP 显示后端本身正常 |

### 右上格：显示客户端与 IOKit 匹配

有客户端时，这一格显示**最近一次** `newUserClient` 的调用者；没有客户端时才回落到
backboardd 的 IOKit 匹配标志。

**已有客户端（`native_legacy_client_calls > 0`）**

| 颜色 | 像素值 | 含义 |
| :--- | :--- | :--- |
| 黄 | `#FFFF00` | comm 以 `IOMFB_FDR` 开头（FDR loader） |
| 天蓝 | `#0080FF` | comm 以 `backboard` 开头（backboardd） |
| 品红 | `#FF00FF` | 其它进程 |

**没有客户端（回落到 `native_boot_flags`）**

| 颜色 | 像素值 | 标志位 | 含义 |
| :--- | :--- | :--- | :--- |
| 紫 | `#8000FF` | `0x400` | backboardd 查询含 `IOMobile` 的字典，未匹配 |
| 蓝 | `#0000FF` | `0x200` | backboardd 查询含 `IOMobile` 的字典，匹配成功（同时置 `0x1000`） |
| 橙 | `#FF8000` | `0x080` | backboardd 调用过任意 IOService matching，但从未记录到含 `IOMobile` 的查询 |
| 深灰 | `#404040` | 无 | backboardd 完全没有向 IOKit 查询过 |

> `0x200` / `0x400` 每次 `IOMobile*` 匹配都会先清后置，只代表**最近一次**结果。
> `0x080` 是粘滞位，一旦置位永不归零，所以橙色只会在还没有任何 `IOMobile*` 查询时出现。

### 左下格：用户客户端创建计数

变量 `native_legacy_client_calls` 统计 `newUserClient` 被调用的次数，包含随后失败的尝试。

| 颜色 | 像素值 | 计数 |
| :--- | :--- | :--- |
| 深灰 | `#404040` | 0 |
| 蓝 | `#0000FF` | 1 到 9 |
| 绿 | `#00FF00` | 10 到 99 |
| 橙 | `#FF8000` | ≥ 100 |

### 右下格：帧交换与匹配状态

水平对半切分，上下两半独立判读。

**上半：帧交换进度（紫色优先）**

| 颜色 | 像素值 | 含义 |
| :--- | :--- | :--- |
| 紫 | `#8000FF` | 有 swap 校验调用（`swap_validation_calls > 0`，接受与拒绝都计数），会长期盖住白色 |
| 白 | `#FFFFFF` | 有 frame copy 调用（`transfer_calls > 0`），失败也计数 |
| 深灰 | `#404040` | 客户端从未提交过帧 |

**下半：backboardd 的 IOKit 匹配状态**

与右上格“没有客户端”的回落逻辑完全相同：紫 `0x400`、蓝 `0x200`、橙 `0x080`、
深灰 `#404040`。它与上半格互不影响，所以即使 FDR loader 持有客户端，也能读出匹配结果。

## 16×16 状态格

五格宽 16 px，左侧 x 坐标依次为 0、20、40、60、80，y 都为 0，原点在 framebuffer 左上角。前四格顺序不变；H410 的 USB 状态格追加在最后。

| 坐标 | 含义 | 颜色与状态值 |
| :--- | :--- | :--- |
| (0, 0) | CPU 频率观测（`sheng_cpufreq_probe`） | 深灰 `0`：未运行<br>红 `1`：至少一个启用的簇低于 1 GHz，或没有任何簇启用<br>绿 `2`：所有启用的簇都不低于 1 GHz<br>紫 `3`：OSM 映射失败<br>橙 `4` / 蓝 `5`：驱动中预留，当前 probe 不产生 |
| (20, 0) | A540 加速器 probe | 深灰 `#404040`：未尝试（`0`）<br>绿：服务已发布（`6`）<br>红：失败或中间态（`1` / `3` / `4` / `5`，对照 `NATIVE_A540` 日志） |
| (40, 0) | 心跳格 | 白 / 橙：1 Hz 翻转（`timer_call`，19 200 000 时基 tick）；2×2 重绘时也会被重画 |
| (60, 0) | H103 持久日志 slot 写入器 | 红 `0`：写入分支尚未进入<br>蓝 `3`：可选 slot 线程已进入，但写窗口未就绪<br>绿 `2` / 白 `4`：最近有成功的 slot 或 header 写入，两色每秒交替形成心跳<br>黄 `1`：超过 3 个日志间隔没有成功写入，或写入失败后停住<br>青 `#00FFFF`（状态 `5`）：USB 实时日志健康，磁盘 sink 主动暂停；不是 USB 未启动，也不是故障 |
| (80, 0) | H410 USB CDC 实时日志链路 | 深灰 `#404040`：USB 驱动未启动<br>黄 `#FFFF00`：驱动已启动，但主机尚未配置 CDC 数据端点（未连接电脑）<br>绿 `#00FF00`：已连接且空闲<br>绿/白交替：Bulk-IN 日志帧正在实际完成传输（约 1 Hz 面板重绘节奏交替；最后成功传输后约 500 ms 恢复绿色） |

## 快速卡点排查

1. **左上格**：SpringBoard 是否 exec、是否已经退出。停在红色说明连用户态都没起来。
2. **右上格**：没有客户端时看 `0x400`。紫色表示 backboardd 查询了 `IOMobile*` 却一个都没匹配上；橙色表示它连 `IOMobile*` 都没查过。
3. **右下格上半**：按“深灰、白、紫”的先后判断是完全没提交、拷贝被调用过，还是已经进入 swap 校验。
4. **左下格**：配合右上格区分“没有进程打开”和“打开了但不是 backboardd”。

> 第四个 16×16 格只重绘自身，不会覆盖用户帧。正常写入时绿、白交替；写入停止、失败或写入窗口停滞时，颜色固定为黄色；USB 日志健康、磁盘 sink 主动暂停时显示青色。颜色只是最后一次重绘时刻的采样。要定位具体失败点，仍需结合
> `plans/oneplus5-cheeseburger/STATUS.md`、`NATIVE_EXEC` / `NATIVE_IOKIT` /
> `NATIVE_LEGACY` 日志与持久日志 slot 判断。
