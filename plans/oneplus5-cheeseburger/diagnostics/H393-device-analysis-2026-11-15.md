# H393 result / 真机结果

Raw h103log-H393.bin is 32 MiB, one boot=2326177e across247 valid slots. Retained body283.3–411.0s. Marker alive, frames0. No retained UFS timeout/recovery/refused/LOG_FAIL. Data mode1 remains blank read-only, writes0/errors0. No claim of full-boot error absence.

本轮单一轮次，正文283.3–411秒，显示帧仍零；保留窗口未见控制器错误。只读Data状态不变。

AW counters at293.56s and357.94s are text=1/0: one rule parsed, no application counted. H392aw/H393 cannot be described as a successfully applied AW repair. The reason remains open: target code page may not have reached the hook, page validation may have taken another path, or matching could fail. Do not force patch a live page without identifying which condition fails.

AW规则已解析但未应用，不能以本轮无桌面判断上游修复无效。

H393 shared-cache slide0x8c90000 derives from libsystem_kernel runtime1d440f000 versus1cb77f000. At340–341s SpringBoard tid292 stack resolves to CCSRemoteServiceProvider sharedInstance -> CCSModuleRepository initialization/update -> filterModuleMetadataByAssociatedBundleAvailability -> LSApplicationRecord initWithBundleIdentifier -> LSContextInitCommon. This exposes an actual desktop startup consumer waiting for LS, beyond Foundation's generic send layer. It is not an AW initializer stack.

桌面主线程在控制中心模块初始化中查询应用可用性，等待LS数据库。当前等待链不是AW初始化互锁证据。

At344s lsd tid515 is the system-content scanner: LSRebuildStatisticsGatherer performSystemContentScan -> ICLWorkspace enumerateBuiltInSystemContentWithBlock -> MILaunchServicesDatabaseGatherer performGather/scanExecutableBundle -> MIFilesystemScanner scanAppsDirectory -> MIBundle appExtensionBundles/pluginKitBundles -> MIFileManager directory enumeration -> TraverseDirectoryWithPostTraversal -> GetContinuationFD -> open. x0 string is /Applications/PaperBoard.app/PlugIns. Its saved user PC resolves to __open+8 and the wait event maps only to merged kernel globals, not a named lock or page wait. Do not infer page-in self-deadlock from that event.

已找到实际扫描执行者，采样时正在open PaperBoard的PlugIns目录。等待地址只能映射到内核合并全局区，不能据此认定分页自锁。

At373s a new cache entry appears for com.apple.PaperBoard.LegacyPoster, and388.89s for com.apple.ClarityPhotos. This is evidence of continuing container initialization after the open snapshot, consistent with progressing scan. It does not prove the exact open returned or provide its latency, because records lack a per-request correlation key. One snapshot cannot identify a permanently blocked file.

后续PaperBoard扩展与其他应用仍生成容器记录，支持初始化继续推进，但没有请求关联与耗时，不能声称该open确定耗时29秒或永久卡住。

Next desktop work: measure path-operation latency and the system scan's progress/completion, separate actual kernel I/O/locking delays from directory enumeration and registration work. Investigate AW hook application conditions independently; do not substitute Data persistence for the scanner investigation or force the seeding-complete marker. No new image or device writes were performed during this analysis.

下一步量化系统扫描与路径操作耗时，定位实际慢点；AW钩子应用条件单独核查。不开Data写回，不强制数据库完成，不把快照当根因。
