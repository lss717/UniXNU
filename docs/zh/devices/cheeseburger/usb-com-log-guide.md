# 一加 5（cheeseburger）USB CDC 串口日志与普通重启使用说明

本页面向使用 Windows 电脑通过 USB 连接 OnePlus 5 的 Format 1（H410）镜像，查看
实时日志并用同一 COM 口发送普通重启命令的读者。

> 结论先行：镜像在 USB CDC ACM 数据端点上传送的是二进制 **UXL1** 帧，不是纯文本。
> 直接用 PuTTY、TeraTerm、`mode`、`Get-Content COMx` 等把串口当文本读，通常会看到
> 二进制乱码或直接卡住。请使用本仓库的工具 `tools/h410-cdc-console.ps1`（实时解码 +
> 可选重启命令），或 `tools/capture-h408-cdc.ps1`（先落盘再解码）。

## 1. 适用镜像与工具版本

| 项目 | 值 |
| :--- | :--- |
| 镜像候选 | H410（见 `main-route/artifacts/H410/` 的 manifest） |
| 设备侧 USB 驱动 | `drivers/CheeseburgerUsb/CheeseburgerUsb.cpp`，build 标签 `H410` |
| 实时解码 / 命令工具 | `UniXNU-cheeseburger/tools/h410-cdc-console.ps1` |
| 落盘解码工具 | `UniXNU-cheeseburger/tools/capture-h408-cdc.ps1` |
| 静态契约检查 | `UniXNU-cheeseburger/tools/check-h408-cdc.py` |
| USB 设备 ID | `USB\VID_1209&PID_0001`（CDC ACM，PnP 串仍为 OP5CDCH408） |
| 核心源码 | UniXNU `h410-usb-status`，基于 `5e204e7d984aac66af3c57c9961926a8d4080062` |
| 设备源码 | UniXNU-cheeseburger `h410-usb-status`，基于 `001e694cc5211c79d283151a2c2204e443d72277` |
| 显示子模块 | GopFramebuffer `cc31bd33e2209e0f261720babb7b4a9dc6b1b0c2` |
| 平台子模块 | ArmDTPlatform `4d057d020124012e545853f6f75a2a6c202d3171` |
| Boot 镜像 | `a4201dbc7825166b3724b47f2be8b94c64b41a094f91392e19841201876a4fbe` |
| 内核 | `9c7640f149018af39e70f7b8eeff4231d7347c45cd1d349125596987edf01873` |
| Payload | `20587408e4315a840feea6e4a9890d27e2978c12c26a855b2d9583bbc1612383` |
| UEFI FD | `e9135e17397165425d0794e8e64c0a4ae63575ce222b06b80305fcde6b16f1b3` |
| 真机 Boot ID / build | `549D06A5` / `H410` |

以上值来自本轮实际构建和真机回归；完整清单见
`main-route/artifacts/H410/H410-manifest.json` 和 `STATUS.md`。如果工具或镜像已更新，请
重新执行 `check-h408-cdc.py --self-test`。

## 2. 前端准备

1. 手机通过 USB 连到 Windows 本机，镜像已启动且 USB CDC 已枚举。
2. 打开“设备管理器”，在“端口（COM 和 LPT）”下应看到一个由 VID `1209`、PID `0001`
   枚举的设备（`usbser` 驱动），并记下它的 `COMx`。示例里的 `COM8` 只是示例，不能
   当成固定端口。
3. 确认设备管理器里该设备没有黄色感叹号；若 `usbser` 未安装或报错，先修复驱动。
4. 只保留一个可能打开该 COM 的程序。PuTTY、TeraTerm、串口调试助手、另一个
   `h410-cdc-console.ps1` 等都会独占端口；本工具用 `CreateFile(..., share=0)` 独占
   打开，其他程序占用时会报 `CreateFile` 错误。

也可以在 PowerShell 里列出端口：

```powershell
Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.PNPDeviceID -match '^USB\\VID_1209&PID_0001' } |
  Select-Object Name, Caption, PNPDeviceID, Status
```

## 3. 串口参数

- CDC ACM 的线路编码（line coding）由设备返回一个名义值，当前镜像里是
  **115200 baud、8 数据位、无校验、1 停止位、无流控**。这只是名义参数，真实吞吐走
  USB Bulk 传输，不受 115200 限制。
- **必须置位 DTR 和 RTS**：设备只有在 `dtr == true` 时才会发送 UXL1 日志帧。工具会
  在打开端口后自动 `SetDTR` / `SetRTS`（`EscapeCommFunction`）。
- 不是所有终端软件都会自动置位 DTR/RTS。若你的终端只能读、没有数据，先在软件里
  找到 DTR/RTS 并在打开端口后勾选。

## 4. 实时解码 + 保存日志（推荐）

在 `UniXNU-cheeseburger/tools` 目录运行（把 `COM8` 换成你的端口）：

```powershell
cd C:\path\to\UniXNU-cheeseburger\tools
powershell -NoProfile -ExecutionPolicy Bypass -File .\h410-cdc-console.ps1 `
  -Port COM8 `
  -Seconds 600 `
  -TextOutput .\H410-live.log `
  -FrameOutput .\H410-live.frames.bin
```

- 工具会在控制台按 UXL1 帧边界实时打印解码后的 payload（也就是内核日志文本），同时把
  文本追加写入 `H410-live.log`，把完整帧写入 `H410-live.frames.bin`。
- `-Seconds 0` 表示一直运行；`Ctrl+C` 停止。停止后仍会打印汇总：
  `H410 frames=... payload_bytes=... crc_errors=... sequence_gaps=... boot_switches=...`。
- 想边跑边看文件，可在另一个窗口执行 `Get-Content .\H410-live.log -Wait`；但请只让
  `h410-cdc-console.ps1` 打开 COM 口，`Get-Content -Wait` 只读文件，不碰串口。

不传 `-Port` 时，工具会自动在同型号 USB 设备中寻找唯一的 `COMx`；找到多个候选会
报错，不会随便挑一个。

## 5. 用同一个 COM 口发送普通重启命令

先确认日志已经保存，再发送命令（普通重启，不做 recovery 标记，也不做槽位适配）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\h410-cdc-console.ps1 `
  -Port COM8 `
  -Reboot `
  -RequestId 12345 `
  -Seconds 120 `
  -TextOutput .\H410-reboot.log `
  -FrameOutput .\H410-reboot.frames.bin
```

- `-Reboot` 会在打开端口、置位 DTR/RTS 后，通过 Bulk-OUT 发送一个 16 字节的
  **UXC1** 命令帧；随后继续用同一个句柄读取日志，因此不会出现“第二个进程抢串口”。
- `-RequestId` 可省略，省略时用当前时间生成一个非零值。设备会在解码文本中回一条
  `NATIVE_USB_CMD: ack req=<id> op=reboot`；随后设备在安全的内核 worker 线程里执行
  `halt_all_cpus(TRUE)`，走上已有的 PSCI `SYSTEM_RESET` 重启路径。
- 只有 USB 和内核仍然工作时命令才有效；如果系统已经黑屏、内核 hang 或 USB 已经
  掉线，命令不会送达。普通重启后如需进 recovery，请等 Android 起来后再
  `adb reboot recovery`。

### UXC1 命令帧格式（16 字节，小端）

| 偏移 | 长度 | 含义 |
| :--- | :--- | :--- |
| 0..3 | 4 | ASCII `UXC1` |
| 4 | 1 | 版本，当前 `1` |
| 5 | 1 | 操作码，`1` = 普通重启 |
| 6..7 | 2 | payload 长度，必须为 `0` |
| 8..11 | 4 | 请求 ID，必须非零 |
| 12..15 | 4 | 对字节 0..11 的 CRC32（与 UXL1 相同的多项式/初值） |

设备只接受**恰好 16 字节**、magic/version/opcode/payload/CRC 全部正确的帧；它不接受
任意文本、shell、任意内存或寄存器写入。重连后请求 ID 可以复用，但在同一驱动实例里
已经 armed 的重启请求不会重复调度。

## 6. 先落盘再解码（备用流程）

不想实时显示、只想保存完整原始字节时：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\capture-h408-cdc.ps1 `
  -Port COM8 -Seconds 300 `
  -TextOutput .\H410-capture.log `
  -FrameOutput .\H410-capture.frames.bin
```

该工具会在结束后把 UXL1 帧解析成文本，并打印 CRC、序号、boot switch 统计。它同样
独占 COM 口、置位 DTR/RTS。

## 7. 日志健康指标

- `frames`：成功解析的 UXL1 帧数。
- `payload_bytes`：payload 总字节数（不含 32 字节帧头）。
- `crc_errors`：必须为 0。
- `sequence_gaps`：同一 boot 内序号跳变次数，正常为 0；换 boot 会重置序号。
- `boot_switches`：一次抓取里出现多个 boot（说明中间重启过）。
- `last_sequence`：最近一帧的序号。
- 每帧头部还带 `boot=`、`build=`、`dropped=`；`build` 应为 `H410`，`dropped` 增长说明
  内存 ring 在 USB 发送前丢过字节。

## 8. 屏幕上的第五个状态块

左上角原有四块（CPU 频率、A540、心跳、H103 磁盘写）保持不变，H410 在
`x=80, y=0` 追加第五块：

| 颜色 | 含义 |
| :--- | :--- |
| 深灰 `#404040` | USB 驱动未启动（例如没有加 `cheeseburger-usb=2`） |
| 黄 `#FFFF00` | 驱动已启动，但主机尚未配置 CDC 数据端点（未连接电脑） |
| 绿 `#00FF00` | 已连接电脑，当前空闲 |
| 绿/白交替 | 已连接，且 Bulk-IN 日志帧正在实际完成传输 |

交替在现有约 1 Hz 的面板重绘节奏下进行；最后一次成功传输后，驱动侧 500 ms 活动
窗口结束，下一帧重绘回到绿色。黑色/旧颜色可能只是用户态第一帧覆盖了面板，不能只
凭屏幕判断 USB 是否有日志，要看串口和 `STATUS.md`。

## 9. USB 正常后磁盘日志暂停

为避免反复写 `userdata_ios` 末尾 32 MiB 日志窗，H410 在 USB 日志**确实健康**后
自动暂停 H103 磁盘 sink：

- 暂停条件：USB 已连接 + 在约 2 秒窗口内至少有 8 次真实的 Bulk-IN 完成，并持续
  保持活动（不是单次提交 TRB，也不是单纯 SET_CONFIGURATION/DTR）。
- 暂停效果：只跳过 H103 的 slot/header 磁盘写；内存 ring 和 USB UXL1 数据源继续
  工作；普通 UFS/APFS 读写完全不受影响。
- 恢复条件：断开、取消配置、驱动 fault、传输错误或约 1.5 秒无新完成时，恢复持久
  磁盘日志；切换由心跳/日志 worker 处理，不在 USB 完成或中断热路径直接写盘。
- 恢复时沿用原有环格式和偏移，不清零分区，也不触碰 32 MiB 以外的 `userdata_ios` 数据。
- 暂停期间第四块（H103 slot 写入器）显示青色 `#00FFFF`，第五块仍按 USB 状态显示；
  不要把青色误判成 USB 未启动。

## 10. 常见问题

| 现象 | 检查 |
| :--- | :--- |
| 设备管理器没有 COM 口 | 先看 PnP 是否有 `VID_1209&PID_0001`；确认镜像确实启动了 CDC 模式（`cheeseburger-usb=2`）；换数据线/USB 口。 |
| `CreateFile \\.\COMx failed` | 端口号写错，或设备还没枚举。用第 2 节的命令重新确认 `COMx`。 |
| `CreateFile` 返回“拒绝访问”/共享冲突 | 另一个程序占了 COM 口。关闭 PuTTY、TeraTerm、串口助手和其他 `h410-cdc-console.ps1`。 |
| `SetDTR/SetRTS failed` 或没有数据 | 终端软件没有置位 DTR/RTS；本工具会自动置位，若仍失败检查驱动。 |
| 一直有字节但看不到日志文本 | 你很可能在用纯文本终端读二进制 UXL1。改用本仓库解码工具。 |
| `CRC mismatch` 较多 | 检查 USB 线/口、是否被其他程序抢读、是否有驱动 reset；必要时重新抓取。 |
| `sequence gap` 增长 | 抓取期间中断过，或内存 ring 丢帧；看 `dropped=` 是否同时增长。 |
| 日志突然断流 | 看第五块是否回到黄/灰，`STATUS.md` 是否有 USB fault；黑屏不等于串口没日志，也不等于日志一定在。 |
| 发 `-Reboot` 后没有重启 | 确认解码文本里出现 `NATIVE_USB_CMD: reboot armed`；只有 USB/内核仍工作时有效。 |

## 11. 黑屏不等于串口无日志

用户态第一帧会覆盖左上角状态面板；面板消失或颜色停在旧值，不能说明显示或 USB
停止。判断 USB 是否仍在工作，应该：

1. 看 `h410-cdc-console.ps1` 是否还在持续输出 UXL1 帧；
2. 看 `frames`/`last_sequence` 是否增长；
3. 看第五状态块和 `STATUS.md`/持久日志。

## 12. 证据与限制

- UXL1 是二进制帧协议，不是 REPL；不要用原始终端发任意文本，也不要把日志文本当命令。
- 普通重启只走已有的 PSCI `SYSTEM_RESET` 路径；不做 recovery/槽位标记。需要 recovery
  时，先普通重启进 Android，再 `adb reboot recovery`。
- 已知 UFS 长时 25 timeout / 26 retry / 25 recover 与进程 corpse 问题仍未宣称全绿；
  H410 的验收记录会单独列出。
