# H391 read-only store bridge / 只读存储接口

NativeUfsProbe now supplies strong NativeRamBlock store functions, replacing the disabled weak defaults without enabling NativeUfs's second controller implementation. Only sheng-data-persist=1 is accepted. Mode 2, write and sync return failure; no Data writes are implemented.

当前驱动接通 RAM Data 的只读存储接口，不开启另一套控制器驱动。仅接受模式1；模式2、写入和同步均返回失败，尚无 Data 写入实现。

The window follows the existing NativeUfs layout: partition end minus tail reserve minus requested overlay blocks. Default reserve is 1024 MiB; accept only 288–16384 MiB, enough for log plus export. Reject zero sizes, oversized windows, root image overlap, less than 4 MiB guard, or reopening with changed geometry. Reads use subtraction-based bounds checks and the existing locked readWindowBulk path. GPT recheck returns unknown (0xff), not a false success.

窗口沿用现有布局，检查分区、尾部预留、镜像与4 MiB保护区边界，拒绝越界或改变已打开窗口尺寸。读取复用现有带锁路径；GPT复查明确输出未知，不能当作通过。

The old seed's default window header was observed blank from TWRP. A boot with mode1 should therefore report read-only window opening and keep Data volatile; it cannot make databases survive reboot. This stage validates wiring before implementing write-through, which still requires a verified backup and explicit write authorization.

此前默认位置头部为空，模式1预期只验证接口接线，Data仍为易失，不会让数据库跨重启保留。真正写入前仍需备份与明确授权。

Next payload must contain cheeseburger-usb=1 and sheng-data-persist=1, with CPU rendering and existing functional arguments retained. Validate the actual modified payload's argument length, kernel equality and changed hash. The remote USB wiring commit f82b23add was integrated alongside this bridge; do not pack the earlier USB-only build.

下次实际 payload 加入 USB 与只读参数，保持CPU路线，校验最终包；远端新增USB接线已合并，不能使用缺失此接口的中间构建。

Build verified: main 90285aff8, device 091714c. Pulled both repositories and regenerated the tree before the successful build. Earlier USB-only intermediate build failed and was not packaged. Kernel build/prelink, archive strong symbols, extracted payload kernel equality and actual argument fit (990/1024 worst case) passed. Only untracked Python cache files and the pre-existing device lock change were observed on the builder.

构建及包内校验通过，未使用失败的中间构建。真机只读窗口验证待完成。

- Kernel SHA-256: `2f574a758d9ef30ba2a7a24d2775979b295a5a7dc1076b8ee079b07394fe8eb5`
- Payload SHA-256: `151c138f8929116cf15ff60f3d888bef3fc1fa6d8e3ec8d050c13f5e2c828d22`
- Boot SHA-256: `a28ed0d003a3379d2377872389b16f98c7bc83af1b6e82572e2078bb84edc3ef`
