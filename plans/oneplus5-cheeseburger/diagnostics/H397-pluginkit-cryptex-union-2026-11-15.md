# H397 PlugInKit Cryptex composition / PlugInKit Cryptex 组合

H396clean ran to1848s with zero frames. The retained window showed `pkd` repeatedly exiting because `/System/Library/PrivateFrameworks/PlugInKitDaemon.framework/PlugInKitDaemon` was missing. The exact 21H461 images show complementary content: OS has the framework Info.plist and signature directory, while SystemOS has the executable. SystemOS is correctly mounted at `/private/preboot/Cryptexes/OS`; the missing piece is nested Cryptex path composition.

H397 adds a read-only `bindfs` union only at the exact `PlugInKitDaemon.framework` directory before launchd. It looks up the executable before and after mounting and reports failure; it does not skip pkd or fabricate service completion. Source `17df40a82`, device `0c66d9998`; clean kernel build and prelink passed. CPU2, GPU-off and quiet desktop arguments remain unchanged.

H396clean运行到1848秒后暴露pkd缺库循环。H397仅把OS侧元数据/签名与SystemOS侧真实二进制在该framework目录只读组合，不跳过pkd，不伪造完成状态。

- Kernel: `5bb8057873d2f68d73ebcba1e64d1bed836e1b29f34affd88b0bf62784626e2d`
- Payload: `f946e19aa37904c1f4408d90a5740b67fd5870b31728daece0b0709032ed0866`
- Boot: `253e04fcfab6e89fab0702ec2b3edb7faf5115fa1e5074afa1617f4528feca8c`
