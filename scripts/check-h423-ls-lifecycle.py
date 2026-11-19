#!/usr/bin/env python3
"""Static gate for the H423 early LaunchServices operation timeline."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
H423_PATCH = next((ROOT / "patches/xnu").glob("*-h423-ls-lifecycle.patch"))
H422_PATCH = next((ROOT / "patches/xnu").glob("*-h422-ls-fs-probe.patch"))
H422_CHECKER = ROOT / "scripts/check-h422-ls-fs-probe.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text(encoding="utf-8")
    patch = H423_PATCH.read_text(encoding="utf-8")

    require(H423_PATCH.name > H422_PATCH.name,
            "H423 patch must sort after H422 in the apply series")
    require('#define H103_BUILD "H423"' in driver,
            "H423 kernel build tag missing")

    changed = {
        line.split()[2][2:]
        for line in patch.splitlines()
        if line.startswith("diff --git ")
    }
    require(changed == {"bsd/vfs/vfs_vnops.c"},
            f"unexpected H423 source set: {sorted(changed)}")

    for marker in (
        "#define NATIVE_LSD_TRACK_SLOTS 32",
        "uint32_t sequence;",
        "uint32_t pid;",
        "uint64_t end_abs;",
        "static uint32_t gNativeLsdNextOp;",
        "sequence = __atomic_add_fetch(&gNativeLsdNextOp, 1",
        "sequence <= NATIVE_LSD_TRACK_SLOTS",
        "slot->pid = (uint32_t)proc_getpid(p);",
        "slot->end_abs = end;",
        "first_ops=%u",
        "seq=%u pid=%u",
        "start_abs=%llu end_abs=%llu",
    ):
        require(marker in patch, f"H423 marker missing: {marker}")

    begin_start = patch.index(
        "native_lsd_fs_begin(enum native_lsd_fs_op op, vnode_t vp"
    )
    end_start = patch.index(
        "native_lsd_fs_end(enum native_lsd_fs_op op, uint32_t slot_index",
        begin_start,
    )
    gate_start = patch.index("native_lsd_gate(uint32_t sample)", end_start)
    begin_body = patch[begin_start:end_start]
    end_body = patch[end_start:gate_start]

    for name, body in (("begin", begin_body), ("end", end_body)):
        for forbidden in (
            "printf(",
            "IOMalloc",
            "kalloc",
            "lck_mtx_",
            "msleep(",
            "wakeup(",
            "copyinstr(",
            "vnode_getpath",
        ):
            require(forbidden not in body,
                    f"H423 {name} hot path contains {forbidden}")

    subprocess.run([sys.executable, str(H422_CHECKER)],
                   check=True, cwd=ROOT)
    print("H423 LaunchServices early-operation timeline gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h423-ls-lifecycle: {error}")
