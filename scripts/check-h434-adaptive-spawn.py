#!/usr/bin/env python3
"""Validate the H434 adaptive cached-launchd wrapper packaging plan."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/build-h434-adaptive-spawn.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    text = BUILD.read_text(encoding="utf-8")
    for marker in (
        "cache.get(\"LaunchDaemons\")",
        '"/System/Library/LaunchDaemons/com.apple.SpringBoard.plist"',
        'job["ProgramArguments"] = [',
        'job["POSIXSpawnType"] = "Adaptive"',
        '"/private/var/ngpu/bin/scenebootstrap"',
        '"--launch-springboard"',
        'environment["DYLD_INSERT_LIBRARIES"]',
        '"/private/var/ngpu/lib/SpringBoardSceneObserver.dylib"',
        'environment["DYLD_FORCE_FLAT_NAMESPACE"] = "1"',
        "plistlib.FMT_BINARY",
        '("xpc/launchd.plist"',
        "launchd cache changed unrelated job",
        '"observer_cdhash"',
        '"bootstrap_cdhash"',
    ):
        require(marker in text, f"H434 addon builder missing: {marker}")
    require('("daemons/' not in text,
            "H433 must not install LaunchDaemons source files")
    require("fastboot" not in text, "build script must not touch the device")
    require("partition" not in text, "build script must not touch a partition")
    print("H434 adaptive-spawn wrapper packaging gate: PASS")


if __name__ == "__main__":
    main()
