# H395 LaunchServices open latency / LaunchServices 打开耗时

H394 disproved persistent ownership of the sampled `kernel_object` lock. H395 keeps the verified CPU desktop route and replaces that completed periodic probe with bounded lsd open-latency measurement in `vn_open_modflags`.

Only `p_comm == "lsd"` is measured. Opens taking at least50ms print elapsed milliseconds, result and path, capped at96 rows. Every256 opens prints total opens, slow count and maximum latency. The probe does not change lookup/open results or persistent Data state.

H394已排除`kernel_object`长期持锁。H395保持双核CPU桌面路线，仅测量lsd打开路径耗时：超过50ms才记录，慢日志有上限，并周期输出总量；不改变文件系统结果或Data状态。

Mac pulled source c5470df56 and device4a8df7a before building. A clean-tree bootstrap initially reproduced the documented stale `ios-obj` mockfs trap; deleting both `xnu-work` and `build/xnu/ios-obj` fixed it. Kernel build and prelink then passed. The kernel hash changed, the extracted payload kernel compares equal, boot arguments pass990/1024 worst-case, and `cheeseburger-usb=1` remains present.

- Kernel: `65ac3eb16fbcc5a91fbc2746881751dd5651578eb5a041bf19eff235583a1204`
- Payload: `69e746695ba663749b3cadaabdde6de102d86f554aa4ffa43612c04b8902e812`
- Boot: `6c2462b6841fdbe2d8f9ece44486ee2fda48f48bba2485bb774f9bdc7b0ea7a1`

H395r pulled source `3bcee5d3a` and device `e7442276b` before rebuilding, thereby including the latest CheeseburgerUsb implementation. Build and prelink passed; the kernel changed to `c1a4ddaf8a5f767692cffa428ae81601796782c6f5c7f264eb483a47936fdf9a`. The candidate explicitly changes the requested argument to `cheeseburger-usb=2`; extracted configuration confirms no `=1`, arguments remain990/1024 worst-case, and the extracted kernel compares equal.

- H395r USB2 payload: `2ba6777de3db73e63b269c23f142de5caa931155e38371aa1a511456d41078d2`
- H395r USB2 boot: `e617d841f99d5140eddead2a159a7542ef197c5a304fdcc6e3b9683545670c45`
