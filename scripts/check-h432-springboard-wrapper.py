#!/usr/bin/env python3
"""Validate the H432 SpringBoard launch-wrapper packaging plan."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/build-h432-springboard-wrapper.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    text = BUILD.read_text(encoding="utf-8")
    for marker in (
        'job["ProgramArguments"] = [',
        '"/private/var/ngpu/bin/scenebootstrap"',
        '"--launch-springboard"',
        'environment["DYLD_INSERT_LIBRARIES"]',
        '"/private/var/ngpu/lib/SpringBoardSceneObserver.dylib"',
        'environment["DYLD_FORCE_FLAT_NAMESPACE"] = "1"',
        "com.apple.SpringBoard.plist",
        "org.blu-sharky.adrenoprobed.plist",
        '"observer_cdhash"',
        '"bootstrap_cdhash"',
    ):
        require(marker in text, f"H432 addon builder missing: {marker}")
    require("com.unixnu.scenebootstrap.plist" not in text,
            "H432 must not depend on a second launchd job")
    require("com.apple.bluetoothd.plist" not in text,
            "H432 must not depend on a daemon alias")
    require("fastboot" not in text, "build script must not touch the device")
    require("partition" not in text, "build script must not touch a partition")
    print("H432 SpringBoard wrapper packaging gate: PASS")


if __name__ == "__main__":
    main()
