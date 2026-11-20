#!/usr/bin/env python3
"""Static gate for the H469 unaligned-observer repair."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    require('#define H103_BUILD "H469"' in text, "H469 marker missing")
    require("NATIVE_H469_STATUS:" in text, "H469 status line missing")
    require(text.count("NATIVE_H469_STATUS:") == 1, "status line not unique")
    require("NATIVE_H468_STATUS:" not in text, "stale H468 status remains")
    for field in ("seq=", "done=", "timeout=", "ocs_err=", "dbto=", "recover=",
                  "recovered=", "flight=", "age_ms=", "lba=", "bytes=", "dir=",
                  "lock_ok=", "lock_timeout=", "lock_wait_ms=",
                  "lock_wait_max_ms=", "lock_waiters=", "watchdog_seen="):
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

    lba_start = text.index("gUfsFrozenLba = 0;")
    lba_end = text.index("gUfsFrozenBytes = bytes;", lba_start)
    lba_block = text[lba_start:lba_end]
    require("if (ucd[0] == 1 && static_cast<unsigned> (ucd[16]) == 0x28) {"
            in lba_block, "READ(10) observation gate missing")
    require("const volatile uint8_t *lbaBytes = q->ucd;" in lba_block,
            "volatile LBA source missing")
    for offset in (18, 19, 20, 21):
        require(f"lbaBytes[{offset}]" in lba_block,
                f"volatile CDB byte missing: {offset}")
        require(f"q->ucd[{offset}]" not in lba_block,
                f"non-volatile wide-load source remains: {offset}")

    require("gUfsFrozenBytes = bytes;" in text, "command byte freeze missing")
    require("gUfsFrozenDir = direction;" in text, "direction freeze missing")
    require("gUfsStartedTicks = mach_absolute_time ();" in text,
            "start tick missing")

    watchdog = text.index("nativeWatchdogThread (void *, wait_result_t)")
    hb_timer = text.index("NativeUfsProbe::hbTimerTick (IOTimerEventSource *sender)")
    status = text.index("NATIVE_H469_STATUS:")
    require(watchdog < status < hb_timer,
            "status must be in the executing watchdog thread")
    require("if (!gH103StallRecorded && (seconds % 30) == 0) {" in text,
            "status must survive after a recorded UFS stall")
    for declaration in ("gLockWaiters", "gLockOkCount", "gLockTimeoutCount",
                        "gLockWaitTicks", "gLockWaitMaxTicks"):
        if declaration == "gLockWaiters":
            declaration_at = text.index("static volatile uint32_t gLockWaiters;")
        else:
            declaration_at = text.index(
                f"static volatile uint64_t {declaration};")
        require(declaration_at < status,
                f"lock counter declared after watchdog status: {declaration}")

    for token in ("#define UFS_TIMEOUT_TICKS 153600001ULL",
                  "#define UFS_DATA_LOCK_TICKS  (576000001ULL)",
                  "getMatchingService ()", "waitForService", "presentSurface:",
                  "setBackgroundGPUPriority:"):
        require(token not in text, f"behavior-change token present: {token}")

    print("H469 unaligned-observer static gate: PASS")
    print("H469 marker: H469")
    print("H469 volatile CDB bytes: 18,19,20,21")
    print("H469 status path: watchdog thread")
    print("H469 UFS timeout/recovery/order changes: none")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"H469 unaligned-observer static gate: FAIL: {error}")
