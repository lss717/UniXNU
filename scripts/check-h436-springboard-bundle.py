#!/usr/bin/env python3
"""Validate the H436 SpringBoard app-bundle wrapper packaging plan."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/build-h436-springboard-bundle.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    text = BUILD.read_text(encoding="utf-8")
    for marker in (
        "cache.get(\"LaunchDaemons\")",
        '"/System/Library/LaunchDaemons/com.apple.SpringBoard.plist"',
        '"/System/Library/LaunchDaemons/com.apple.lsd.plist"',
        '"/System/Library/CoreServices/SpringBoard.app/SpringBoard"',
        'environment["DYLD_INSERT_LIBRARIES"]',
        '"/private/var/ngpu/lib/SpringBoardSceneObserver.dylib"',
        'environment["DYLD_FORCE_FLAT_NAMESPACE"] = "1"',
        "plistlib.FMT_BINARY",
        '("xpc/launchd.plist"',
        "launchd cache changed unrelated job",
        '("springboard/SpringBoard"',
        '("springboard/SpringBoard.real"',
        '("xpc/lsdwrap"',
        '("xpc/lsd.real"',
        '("lib/LsdRecoveryAsync.dylib"',
        '"/System/Library/xpc/lsdwrap"',
        'b"build=H545"',
        'b"H540_LS"',
        'b"h541_did_finish_enter"',
        'b"h541_application_state"',
        'b"h542_status_server_bypass_enter"',
        'b"h542_after_did_finish"',
        'b"h543_mc_wait_bypass_enter"',
        'b"h545_cloud_config_ui_bypass"',
        'b"methods installed add=independent state="',
        'b"application enumeration skipped"',
        'b"current process proxy skipped"',
        'b"application proxy identifier skipped"',
        'b"application proxy URL skipped"',
        'b"ls_installer sample="',
        '"scripts/add-macho-load-dylib.py"',
        '"/private/var/ngpu/lib/LsdRecoveryAsync.dylib"',
        '"lsd_source_sha256"',
        '"observer_cdhash"',
        '"bootstrap_cdhash"',
        '"lsd_bootstrap_cdhash"',
        '"lsd_recovery_cdhash"',
    ):
        require(marker in text, f"H436 addon builder missing: {marker}")
    require('("daemons/' not in text,
            "H436 must not install LaunchDaemons source files")
    require("fastboot" not in text, "build script must not touch the device")
    require("partition" not in text, "build script must not touch a partition")
    require('"/bin/sh"' not in text, "H436 must not use a shell trampoline")
    print("H436 SpringBoard bundle wrapper packaging gate: PASS")


if __name__ == "__main__":
    main()
