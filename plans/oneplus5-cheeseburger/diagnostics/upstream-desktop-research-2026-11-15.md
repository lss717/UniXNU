# Upstream desktop research / 上游桌面问题调研

Read-only research on 2026-11-15. No kernel, image or device data changed during this research.

## Branch coverage / 分支范围

UniXNU/UniXNU advertised main=0c1bac3d51a3009dca1708b15a5198f4b43d057a, feat/macos=2bbb39dcee0cada3b04e41f0256d678e80667c5b, rponeawa/macos-memory-diagnostics-run139=2b545eae50733c62a18f175214c34e7122f82422. Fetched all three read-only. `git diff --quiet` found no difference in patches/xnu (the relevant older kernel patch directory) between main and either additional branch. This is scoped evidence, not a claim that the whole branches are identical. Historical merged feature branches were traced through PRs and UniXNU-sheng history.

上游当前三个分支的旧XNU补丁目录相同，两个额外分支偏向macOS，未找到该目录下独有的桌面修复。已继续查历史合并分支和设备仓库。

## Findings / 发现

1. Same-build SpringBoard class-initializer deadlock. [PR35](https://github.com/UniXNU/UniXNU/pull/35), [sheng da9fab9](https://github.com/UniXNU/UniXNU-sheng/commit/da9fab96aea0b5dcdb3bef730b10397276514dac). On 21H461, AWClientPreferences and AWAttentionAwarenessConfiguration initializers wait on each other, main versus Siri's SASMyriadController thread. The board used an original-byte-checked signed-text fixup making the latter initializer return. Later [6eaa074](https://github.com/UniXNU/UniXNU-sheng/commit/6eaa074956351e86b53814eba1f18417857527fa) moved rules into ADT chosen/text-fixups. Our tree contains the mechanism, but board.toml search did not find configured rules. Actual packaged ADT and applied counters still need inspection. Our captured LS waiting stacks do not prove this specific AW cycle; do not copy offsets blindly.

同版本确有初始化互锁修复，但当前捕获的LS等待不是该互锁的直接证据。须查实际ADT、原始字节和应用计数。

2. Persistence is not a prerequisite for first UI. [nabu record](https://unixnu.com/devices/nabu-zzweiqing) explicitly reports interactive SpringBoard with volatile RAM Data and no persistent Data. This board has GPU compositing, so it does not prove our CPU rendering path. [merlinx record](https://raw.githubusercontent.com/UniXNU/UniXNU/main/docs/devices/merlinx.md) uses the same iPad7,1/21H461 target and reports lsd completing its first database build and Lock Screen/Dock, while userland GPU remains incomplete. Its hardware transport differs; inspect its original seed and display setup before borrowing changes.

RAM Data可达UI，不能把“未持久化”当桌面阻塞的充分解释。merlinx同系统版本尤其值得对照，但不同硬件不得混用。

3. A persistent LS database can itself be wrong. [sheng 5ef4821](https://github.com/UniXNU/UniXNU-sheng/commit/5ef48217d479bdf3adaf909032bc3d56d410b7de) drops LS stores every boot after forced reboot lost lazy database writes and left only Settings. The iPadOS27 bring-up patch also explains databases seeded before /System/Cryptexes/OS resolves omit content, and searches lsd's UUID Data containers for stores. These are newer-OS fixes, not a recommendation to delete databases on this phone. Preserve mount ordering and inspect actual root/Data topology first.

错误数据库持久化也会阻塞应用注册，不能以开启写回替代挂载顺序和数据库正确性检查。

4. Page-in self-deadlock. [upstream patch](https://github.com/UniXNU/UniXNU/blob/0c1bac3d51a3009dca1708b15a5198f4b43d057a/patches/xnu-12377/native-4k-shared-region-slide.patch) releases the source/placeholder busy pages before sliding another 4 KiB part of a 16 KiB shared-cache slide page. Its comment describes APFS integrity page-in requesting a whole verification block and waiting on a page held by the same thread, observed under vm_page_sleep/apfs_pagein_with_verification. Our older tree did not match the corresponding source-page identifiers. H389c2's prewarm byte-load sample makes this worth checking, but saved user PC does not prove a kernel page-in deadlock. Obtain kernel-side wait/backtrace before adapting this newer-XNU patch.

4K分页自锁是需要优先核对的机制候选；必须先取得初始化工作线程的内核等待栈，不能直接移植新XNU补丁。

## Adjusted mainline / 调整主线

Keep CPU rendering, current seed and USB argument. Stop extending persistence as the presumed desktop fix. First inspect packaged ADT/text-fixup counters and compare same-build merlinx seed/mount/display policy. Then identify kernel wait stacks for the seeding workload, especially busy-page/APFS waits. Apply only a verified, minimal repair; return to Data write-through after identifying whether it helps the actual blockage. Neither more waiting nor copying all upstream patches is justified by this research.

保持CPU路线，先查同版本种子、挂载与签名文本修正规则，再取初始化任务内核栈。持久化降为辅助，不再作为已确定主因推进。
