#!/usr/bin/env python3
"""Static gate for the H422 read-only LaunchServices filesystem probe."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
H422_PATCH = next((ROOT / "patches/xnu").glob("*-h422-ls-fs-probe.patch"))
H421_PATCH = next((ROOT / "patches/xnu").glob("*-h421-ls-gate.patch"))
H421_CHECKER = ROOT / "scripts/check-h421-launchservices-gate.py"
DISPLAY_CHECKER = ROOT / "scripts/check-display-first-frame-probe.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text(encoding="utf-8")
    patch = H422_PATCH.read_text(encoding="utf-8")

    require(H422_PATCH.name > H421_PATCH.name,
            "H422 patch must sort after H421 in the apply series")
    require('#define H103_BUILD "H422"' in driver or
            '#define H103_BUILD "H423"' in driver or
            '#define H103_BUILD "H424"' in driver,
            "H422-or-later kernel build tag missing")

    changed = {
        line.split()[2][2:]
        for line in patch.splitlines()
        if line.startswith("diff --git ")
    }
    expected = {
        "bsd/sys/vnode_internal.h",
        "bsd/vfs/vfs_syscalls.c",
        "bsd/vfs/vfs_vnops.c",
        "bsd/vfs/vfs_xattr.c",
    }
    require(changed == expected,
            f"unexpected H422 source set: {sorted(changed)}")

    for marker in (
        "NATIVE_LSD_FS_OPEN = 1",
        "NATIVE_LSD_FS_READ",
        "NATIVE_LSD_FS_WRITE",
        "NATIVE_LSD_FS_FSYNC",
        "NATIVE_LSD_FS_GETXATTR",
        "opens=%llu reads=%llu writes=%llu",
        "fsyncs=%llu xattrs=%llu active=%llu",
        "slow50=%llu slow500=%llu",
        "slow5000=%llu max_ms=%llu errors=%llu",
        "NATIVE_LS_GATE_SLOT:",
        "vnode=0x%llx active=%u offset=%lld requested=%llu",
        "residual=%llu ms=%llu result=%d name=%s path=%s",
        "op < NATIVE_LSD_FS_OPEN",
        "thread_tid(current_thread())",
    ):
        require(marker in patch, f"H422 marker missing: {marker}")

    for op in ("OPEN", "READ", "WRITE", "FSYNC", "GETXATTR"):
        require(
            f"native_lsd_fs_begin(NATIVE_LSD_FS_{op}" in patch,
            f"H422 begin hook missing for {op}",
        )
        require(
            f"native_lsd_fs_end(NATIVE_LSD_FS_{op}" in patch,
            f"H422 end hook missing for {op}",
        )

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
    gate_body = patch[gate_start:]

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
                    f"H422 {name} hot path contains {forbidden}")

    require("printf(" in gate_body, "H422 sampler gate does not print")
    require("strlcpy(slot->path" not in gate_body,
            "H422 sampler gate mutates slot paths")

    subprocess.run([sys.executable, str(H421_CHECKER)],
                   check=True, cwd=ROOT)
    subprocess.run([sys.executable, str(DISPLAY_CHECKER)],
                   check=True, cwd=ROOT)

    print("H422 LaunchServices filesystem progress gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h422-ls-fs-probe: {error}")
