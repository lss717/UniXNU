#!/usr/bin/env python3
"""Static gate for H467 UFS submit, lock, and watchdog accounting."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    require('#define H103_BUILD "H467"' in text, "H467 marker missing")
    require("NATIVE_H467_STATUS:" in text, "H467 status line missing")
    require(text.count("NATIVE_H467_STATUS:") == 1, "status line not unique")
    for field in ("seq=", "done=", "timeout=", "ocs_err=", "dbto=", "flight=",
                  "age_ms=", "lba=", "bytes=", "dir=", "lock_ok=",
                  "lock_timeout=", "lock_wait_ms=", "lock_wait_max_ms=",
                  "lock_waiters=", "watchdog_seen="):
        require(field in text, f"status field missing: {field}")
    for update in ("gUfsSubmitSeq = gUfsSubmitSeq + 1;",
                   "gUfsDoneCount = gUfsDoneCount + 1;",
                   "gUfsTimeoutCount = gUfsTimeoutCount + 1;",
                   "gUfsOcsErrorCount = gUfsOcsErrorCount + 1;",
                   "gUfsDbTimeoutCount = gUfsDbTimeoutCount + 1;",
                   "gLockOkCount = gLockOkCount + 1;",
                   "gLockTimeoutCount = gLockTimeoutCount + 1;",
                   "gWatchdogSeen = gWatchdogSeen + 1;"):
        require(text.count(update) == 1, f"unexpected count: {update}")
    require("gUfsFrozenLba = gUfsLastLba;" in text, "LBA freeze missing")
    require("gUfsFrozenBytes = gUfsLastBytes;" in text, "byte freeze missing")
    require("gUfsFrozenDir = direction;" in text, "direction freeze missing")
    require("gUfsStartedTicks = mach_absolute_time ();" in text, "start tick missing")
    for token in ("#define UFS_TIMEOUT_TICKS 153600001ULL",
                  "#define UFS_DATA_LOCK_TICKS  (576000001ULL)",
                  "getMatchingService ()", "waitForService", "presentSurface:",
                  "setBackgroundGPUPriority:"):
        require(token not in text, f"behavior-change token present: {token}")
    print("H467 UFS observation static gate: PASS")
    print("H467 marker: H467")
    print("H467 status record: unique")
    print("H467 terminal accounting: unique updates")
    print("H467 device behavior changed: no")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"H467 UFS observation static gate: FAIL: {error}")
