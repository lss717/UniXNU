#!/usr/bin/env python3
"""Validate the H431 SpringBoard addon packaging plan."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/build-h431-scene-addon.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    text = BUILD.read_text(encoding="utf-8")
    for marker in (
        'environment["DYLD_INSERT_LIBRARIES"]',
        '"/private/var/ngpu/lib/SpringBoardSceneObserver.dylib"',
        'environment["DYLD_FORCE_FLAT_NAMESPACE"] = "1"',
        "com.apple.SpringBoard.plist",
        "com.unixnu.scenebootstrap.plist",
        "com.apple.bluetoothd.plist",
        "org.blu-sharky.adrenoprobed.plist",
        '"observer_cdhash"',
        '"bootstrap_cdhash"',
    ):
        require(marker in text, f"H431 addon builder missing: {marker}")
    require("fastboot" not in text, "build script must not touch the device")
    require("partition" not in text, "build script must not touch a partition")
    print("H431 scene addon packaging gate: PASS")


if __name__ == "__main__":
    main()
