# Data persistence audit / Data 持久化检查

User requirement: add `cheeseburger-usb=1` to the actual payload kernel arguments on the next package/build; check argument length after modifying the payload. 用户要求下次打包加入此参数，必须验证最终 payload。

Current build exports XNU_NATIVE_UFS=0 and XNU_NATIVE_RAM_BLOCK=1. NativeRamBlock defines weak persistence functions returning mode=0; the strong implementations live in NativeUfs.cpp, excluded from this build. A persistence boot argument alone cannot activate this path. Do not enable a competing controller driver as a shortcut.

当前持久化接口是关闭状态的弱占位实现，单加参数无效；不能直接开启另一套驱动争用控制器。

Read-only device inspection: userdata_ios size=52840607744 bytes, 12900539 blocks of 4096 bytes. For the current 1 GiB seed, overlay size is 262153 blocks, default tail reserve 262144 blocks; candidate relative start=12376242. Read 9 blocks there through TWRP. The entire first block is zero, with no SHNGDATA header. This rules out a valid overlay at this particular default location, not at every historical size/reserve combination. No device data was written or cleared.

只读检查默认布局的候选持久化头，首块全零，无 SHNGDATA。仅排除此位置的有效覆盖层，不能排除其他历史布局。未写入或清零手机数据。

Next implementation decision: evaluate exposing a bounded store window through the already active NativeUfsProbe controller, keeping partition/root/log bounds and seed identity checks. Before writable testing, back up the exact chosen window and obtain explicit Data-write authorization. Persistence remains a hypothesis for avoiding repeated initialization, not a proven desktop fix.

下一步评估由当前活动驱动提供有边界的存储窗口，保留分区、系统镜像、日志边界及种子匹配检查。实际写入前需备份与明确授权。持久化仍非已证明的桌面修复。
