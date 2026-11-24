#!/usr/bin/env python3
"""Summarise a pulled kernel log against the UFS pass/fail criteria.

Usage:  scripts/h103-ufs-report.py /tmp/opencode/h360-log.txt

The criteria come from plans/oneplus5-cheeseburger/diagnostics/ufs-stall-plan-2026-11-15.md:
no request held past thirty seconds, no storm of refused block requests, and the persistent
ring still accepting writes late in the boot.
"""

import re
import sys

STAMP = re.compile(r"^\[\s*([0-9.]+)\]")
START_FAIL = "request failed to start"
# H635: the kernel now prints which logWrite site refused a write, cumulatively, so the
# distribution survives a window in which no slot reached the disk at all.
LOG_STAT = re.compile(
    r"NATIVE_UFS_LOG_STAT:.*pre=(?P<pre>\d+) buf=(?P<buf>\d+) clamp=(?P<clamp>\d+) "
    r"lock=(?P<lock>\d+) dmashort=(?P<dmashort>\d+) io=(?P<io>\d+) "
    r"paused=(?P<paused>\d+) backoff=(?P<backoff>\d+)"
)
REASON_NAMES = {1: "precondition", 2: "no DMA buffer", 3: "clamp empty",
                4: "try-lock busy", 5: "DMA short", 6: "I/O failed"}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    first = last = None
    counts = {
        "NATIVE_UFS_DBTO": 0,
        "NATIVE_UFS_RECOVER": 0,
        "NATIVE_UFS_STALL_LOG": 0,
        "NATIVE_UFS_STALL_NOPANIC": 0,
        "NATIVE_UFS_STALL:": 0,
        "NATIVE_UFS_LOG_FAIL": 0,
        "NATIVE_UFS_GPT: OCS timeout": 0,
        "NATIVE_UFS_RETRY": 0,
        "NATIVE_UFS_SLOT": 0,
    }
    start_fail = 0
    ring_last = None
    counters = {}
    reasons = {}
    histogram = None
    with open(sys.argv[1], errors="ignore") as handle:
        for line in handle:
            match = STAMP.match(line)
            if match:
                when = float(match.group(1))
                first = when if first is None else first
                last = when
            for key in counts:
                if key in line:
                    counts[key] += 1
            if START_FAIL in line:
                start_fail += 1
            if "NATIVE_UFS_LOG_STAT" in line or "NATIVE_UFS_SLOT" in line:
                ring_last = last
            if "NATIVE_UFS_LOG_FAIL" in line:
                found = re.search(r"\breason=(\d+)", line)
                if found:
                    code = int(found.group(1))
                    reasons[code] = reasons.get(code, 0) + 1
            found = LOG_STAT.search(line)
            if found:
                histogram = {k: int(v) for k, v in found.groupdict().items()}
            found = re.search(r"dbto=(\d+) rec=(\d+) wfail=(\d+)", line)
            if found:
                counters = {
                    "dbto": int(found.group(1)),
                    "rec": int(found.group(2)),
                    "wfail": int(found.group(3)),
                }

    print("window      %.1f .. %.1f s" % (first or 0, last or 0))
    for key, value in counts.items():
        print("%-30s %d" % (key, value))
    print("%-30s %d" % ("block requests refused", start_fail))
    print("ring last write            %s s" % ("-" if ring_last is None else "%.1f" % ring_last))
    if counters:
        print("counters                   dbto=%d rec=%d wfail=%d"
              % (counters["dbto"], counters["rec"], counters["wfail"]))
    if histogram:
        print("logWrite refusals by site (cumulative)")
        for key in ("pre", "buf", "clamp", "lock", "dmashort", "io"):
            print("  %-10s %d" % (key, histogram[key]))
        print("  flush skipped: paused=%d backoff=%d"
              % (histogram["paused"], histogram["backoff"]))
    elif counts["NATIVE_UFS_LOG_FAIL"]:
        print("logWrite refusals by site: no H635 histogram in this log")
    if reasons:
        print("reason= on FAIL lines")
        for code in sorted(reasons):
            print("  %d %-16s %d" % (code, REASON_NAMES.get(code, "?"), reasons[code]))

    if first is None:
        print("verdict: no timestamped lines, wrong file?")
        return
    ran_long = last - first >= 300
    refused_storm = start_fail > 20
    ring_alive = ring_last is not None and ring_last > 0.8 * (last or 1)
    storage_errors = any(counts[key] for key in (
        "NATIVE_UFS_DBTO", "NATIVE_UFS_RECOVER", "NATIVE_UFS_STALL_LOG",
        "NATIVE_UFS_STALL_NOPANIC", "NATIVE_UFS_STALL:",
        "NATIVE_UFS_LOG_FAIL", "NATIVE_UFS_GPT: OCS timeout", "NATIVE_UFS_RETRY",
    )) or any(counters.values())
    print("verdict: %s (ran %.0f s, refused=%d, ring=%s)"
          % ("PASS" if ran_long and not refused_storm and ring_alive and not storage_errors else "CHECK",
             last - first, start_fail, "alive" if ring_alive else "stalled"))


if __name__ == "__main__":
    main()
