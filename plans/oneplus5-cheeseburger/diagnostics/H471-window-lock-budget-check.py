#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
text = SOURCE.read_text()


def require(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)


require('#define H103_BUILD "H471"' in text, "H471 build marker")
require(
    "#define UFS_TIMEOUT_TICKS 153600000ULL" in text,
    "UFS command timeout must remain 8 seconds",
)
require(
    "#define UFS_DATA_LOCK_TICKS  (576000000ULL)" in text,
    "global UFS command lock must remain 30 seconds",
)
require(
    "#define UFS_WINDOW_LOCK_TICKS (2304000000ULL)" in text,
    "window lock budget must be 120 seconds",
)
require(
    text.count("UFS_WINDOW_LOCK_TICKS") == 2,
    "the new window budget must have one definition and one use",
)
require(
    "lockWithTimeout (lock, label, UFS_WINDOW_LOCK_TICKS, true)" in text,
    "only NativeUfsWindow acquisition uses the expanded budget",
)
require(
    "lockWithTimeout (lock, label, UFS_DATA_LOCK_TICKS, true)" not in text,
    "old 30 second window budget must be absent",
)
require(
    text.count("UFS_DATA_LOCK_TICKS") == 5,
    "the four global lock uses remain unchanged",
)
print("H471 window-lock static gate: PASS")
print("H471 marker: H471")
print("UFS command timeout: 8 s")
print("global UFS lock budget: 30 s")
print("NativeUfsWindow lock budget: 120 s")
