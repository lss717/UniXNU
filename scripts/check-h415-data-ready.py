#!/usr/bin/env python3
"""Validate the H415 bounded Data mountpoint readiness patch."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / "patches/xnu/data-mount-ready.patch"


def require(condition, message):
    if not condition:
        raise SystemExit(f"check-h415-data-ready: {message}")


def main():
    patch = PATCH.read_text()
    require(
        "--- a/bsd/kern/kern_exec.c" in patch
        and "+++ b/bsd/kern/kern_exec.c" in patch,
        "late patch does not target kern_exec.c",
    )
    require(patch.count("--- a/") == 1, "late patch must modify one source file")
    require(
        "native_owner_data_mountpoint_wait" in patch
        and "native_owner_data_mountpoint_status" in patch,
        "mountpoint readiness counters missing",
    )
    require(
        'vnode_lookup("/private/var", 0, &mountpoint' in patch,
        "bounded /private/var lookup missing",
    )
    require("if (rootvnode != NULLVP)" in patch, "rootvnode gate missing")
    require("error != ENOENT" in patch, "non-ENOENT errors are not terminal")
    require(
        "seed_wait + mountpoint_wait >= 600" in patch,
        "total bounded wait missing",
    )
    require("error = ETIMEDOUT" in patch, "explicit timeout error missing")
    require("IOSleep(100)" in patch, "sleep interval missing")
    require(
        "mount(p, &request, &result)" not in patch,
        "late patch duplicates the original mount implementation",
    )
    require(
        patch.index("vnode_lookup(\"/private/var\"")
        < patch.index("strlcpy(native_owner_data_device_path"),
        "mountpoint lookup is not before original mount preparation",
    )

    series = subprocess.check_output(
        [sys.executable, ROOT / "scripts/apply-patch-series.py",
         "--root", ROOT / "patches/xnu", "list"],
        text=True,
    ).splitlines()
    tree_text = "\n".join(Path(path).read_text(errors="ignore") for path in series)
    for forbidden in (
        "NATIVE_IPC_PORT_RING",
        "NATIVE_IPC_DELEGATE_RING",
        "native_ipc_focus_store",
        "native_ipc_focus_set",
        "native_xpc_tasks",
    ):
        require(forbidden not in tree_text, f"H414 focused IPC code leaked: {forbidden}")

    driver = (ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp").read_text()
    require('#define H103_BUILD "H415"' in driver, "H415 build tag missing")
    print("H415 bounded Data mountpoint readiness: PASS")


if __name__ == "__main__":
    main()
