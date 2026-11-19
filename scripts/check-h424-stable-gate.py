#!/usr/bin/env python3
"""Static gate for H424 stable LaunchServices and crash-image probes."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
PATCH = next((ROOT / "patches/xnu").glob("*-h424-stable-gate.patch"))
H423_PATCH = next((ROOT / "patches/xnu").glob("*-h423-ls-lifecycle.patch"))
H423_CHECKER = ROOT / "scripts/check-h423-ls-lifecycle.py"
METAL = ROOT / "drivers/NativeMetal/A540TracePlugin.mm"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text(encoding="utf-8")
    patch = PATCH.read_text(encoding="utf-8")
    metal = METAL.read_text(encoding="utf-8")

    require(PATCH.name > H423_PATCH.name,
            "H424 patch must sort after H423 in the apply series")
    require('#define H103_BUILD "H424"' in driver,
            "H424 kernel build tag missing")

    changed = {
        line.split()[2][2:]
        for line in patch.splitlines()
        if line.startswith("diff --git ")
    }
    require(changed == {"bsd/vfs/vfs_vnops.c", "osfmk/kern/task.c"},
            f"unexpected H424 source set: {sorted(changed)}")

    for marker in (
        "static uint32_t gNativeLsdGateEmitted;",
        "static uint32_t gNativeLsdGatePending;",
        "NATIVE_LS_GATE_PENDING:",
        "first_ops=%u stable=1",
        "NATIVE_LS_GATE_SLOT:",
        "stable=1",
        "native_lsd_gate(sample);",
        "label=lsd count=%u",
        "NATIVE_SBPC_IMAGE:",
    ):
        require(marker in patch, f"H424 marker missing: {marker}")

    begin_start = patch.index("native_lsd_gate(uint32_t sample)")
    gate_body = patch[begin_start:]
    for forbidden in (
        "IOSleep(",
        "IOMalloc",
        "kalloc",
        "lck_mtx_",
        "msleep(",
        "wakeup(",
    ):
        require(forbidden not in gate_body,
                f"H424 sampler gate contains {forbidden}")

    for marker in (
        "report_signal_image(const char *tag",
        "_dyld_image_count()",
        "_dyld_get_image_header(index)",
        "_dyld_get_image_vmaddr_slide(index)",
        "LC_SEGMENT_64",
        "slide=0x%llx base=0x%llx off=0x%llx",
        "report_signal_image(\"pc\", pc);",
        "report_signal_image(\"lr\", lr);",
        "report_signal_image(tag, ret);",
    ):
        require(marker in metal, f"H424 NativeMetal marker missing: {marker}")

    subprocess.run([sys.executable, str(H423_CHECKER)],
                   check=True, cwd=ROOT)
    print("H424 stable LaunchServices and crash-image gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h424-stable-gate: {error}")
