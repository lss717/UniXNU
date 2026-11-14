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


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    first = last = None
    counts = {
        "NATIVE_UFS_DBTO": 0,
        "NATIVE_UFS_RECOVER": 0,
        "NATIVE_UFS_STALL_LOG": 0,
        "NATIVE_UFS_LOG_FAIL": 0,
        "NATIVE_UFS_GPT: OCS timeout": 0,
        "NATIVE_UFS_RETRY": 0,
        "NATIVE_UFS_SLOT": 0,
    }
    start_fail = 0
    ring_last = None
    counters = {}
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

    if first is None:
        print("verdict: no timestamped lines, wrong file?")
        return
    ran_long = (last or 0) >= 300
    refused_storm = start_fail > 20
    ring_alive = ring_last is not None and ring_last > 0.8 * (last or 1)
    print("verdict: %s (ran %.0f s, refused=%d, ring=%s)"
          % ("PASS" if ran_long and not refused_storm and ring_alive else "CHECK",
             last - first, start_fail, "alive" if ring_alive else "stalled"))


if __name__ == "__main__":
    main()
