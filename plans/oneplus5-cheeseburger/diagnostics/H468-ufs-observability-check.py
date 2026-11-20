#!/usr/bin/env python3
"""Static gate for H468 UFS submit, lock, and watchdog accounting."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    require('#define H103_BUILD "H468"' in text, "H468 marker missing")
    require("NATIVE_H468_STATUS:" in text, "H468 status line missing")
    require(text.count("NATIVE_H468_STATUS:") == 1, "status line not unique")
    for field in ("seq=", "done=", "timeout=", "ocs_err=", "dbto=", "recover=",
                  "recovered=", "flight=", "age_ms=", "lba=", "bytes=", "dir=", "lock_ok=",
                  "lock_timeout=", "lock_wait_ms=", "lock_wait_max_ms=",
                  "lock_waiters=", "watchdog_seen="):
        require(field in text, f"status field missing: {field}")
    for update in ("gUfsSubmitSeq = gUfsSubmitSeq + 1;",
                   "gUfsDoneCount = gUfsDoneCount + 1;",
                   "gUfsTimeoutCount = gUfsTimeoutCount + 1;",
                   "gUfsOcsErrorCount = gUfsOcsErrorCount + 1;",
                   "gUfsDbTimeoutCount = gUfsDbTimeoutCount + 1;",
                   "gUfsRecoverAttempts = gUfsRecoverAttempts + 1;",
                   "gLockOkCount = gLockOkCount + 1;",
                   "gLockTimeoutCount = gLockTimeoutCount + 1;",
                   "gWatchdogSeen = gWatchdogSeen + 1;"):
        require(text.count(update) == 1, f"unexpected count: {update}")
    require("gUfsFrozenLba = (ucd[0] == 1 &&" in text, "current CDB LBA freeze missing")
    require("gUfsFrozenBytes = bytes;" in text, "current command byte freeze missing")
    require("gUfsFrozenDir = direction;" in text, "direction freeze missing")
    require("gUfsStartedTicks = mach_absolute_time ();" in text, "start tick missing")
    require(text.index("static volatile uint64_t gWatchdogSeen;") < text.index("gWatchdogSeen = gWatchdogSeen + 1;"), "watchdog declaration precedes use")
    watchdog = text.index("nativeWatchdogThread (void *, wait_result_t)")
    hb_timer = text.index("NativeUfsProbe::hbTimerTick (IOTimerEventSource *sender)")
    status = text.index("NATIVE_H468_STATUS:")
    require(watchdog < status < hb_timer, "status must be in the executing watchdog thread, before hbTimerTick")
    require("if (!gH103StallRecorded && (seconds % 30) == 0) {" in text, "status must survive after a recorded UFS stall")
    for token in ("#define UFS_TIMEOUT_TICKS 153600001ULL",
                  "#define UFS_DATA_LOCK_TICKS  (576000001ULL)",
                  "getMatchingService ()", "waitForService", "presentSurface:",
                  "setBackgroundGPUPriority:"):
        require(token not in text, f"behavior-change token present: {token}")
    print("H468 UFS observation static gate: PASS")
    print("H468 marker: H468")
    print("H468 status record: unique")
    print("H468 terminal accounting: unique updates")
    print("H468 device behavior changed: no")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"H468 UFS observation static gate: FAIL: {error}")
