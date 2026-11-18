#!/usr/bin/env python3
"""Validate the inherited H415 Data wait and H416 build marker."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / (
    "patches/xnu/"
    "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-"
    "h415-data-ready.patch"
)


def require(condition, message):
    if not condition:
        raise SystemExit(f"check-h416-data-ready: {message}")


def main():
    patch = PATCH.read_text()
    require(
        patch.count("--- a/") == 1
        and "--- a/bsd/kern/kern_exec.c" in patch
        and "+++ b/bsd/kern/kern_exec.c" in patch,
        "inherited Data wait is not the H415 single-file patch",
    )
    require(
        "native_owner_data_mountpoint_wait" in patch
        and "native_owner_data_mountpoint_status" in patch,
        "mountpoint readiness counters missing",
    )
    require(
        'vnode_lookup("/private/var", 0, &mountpoint' in patch,
        "bounded /private/var lookup missing",
    )
    require("error != ENOENT" in patch, "non-ENOENT errors are not terminal")
    require(
        "seed_wait + mountpoint_wait >= 600" in patch,
        "shared bounded wait missing",
    )
    require("error = ETIMEDOUT" in patch, "explicit timeout error missing")
    require("IOSleep(100)" in patch, "100 ms sleep interval missing")

    driver = (ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp").read_text()
    require('#define H103_BUILD "H416"' in driver, "H416 build tag missing")
    print("H416 inherited Data readiness and build tag: PASS")


if __name__ == "__main__":
    main()
