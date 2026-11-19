#!/usr/bin/env python3
"""Static gate for the H421 read-only LaunchServices progress probe."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
H420_PATCH = ROOT / "patches/xnu/zzzzzzzzzzzzzz-h420-bks-timestamp.patch"
H421_PATCH = next(
    (ROOT / "patches/xnu").glob("*-h421-ls-gate.patch")
)
NATIVE_CHECKER = ROOT / "drivers/NativeMetal/tools/check-h420-main-scene.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text(encoding="utf-8")
    h420_patch = H420_PATCH.read_text(encoding="utf-8")
    patch = H421_PATCH.read_text(encoding="utf-8")

    require('#define H103_BUILD "H421"' in driver or
            '#define H103_BUILD "H422"' in driver or
            '#define H103_BUILD "H423"' in driver,
            "H421-or-later kernel build tag missing")
    require("NATIVE_DISPLAY_GATE:" in driver, "display gate missing")
    require("event->event_time = mach_absolute_time();" in h420_patch,
            "H420 BKS timestamp repair missing")

    for marker in (
        "#define NATIVE_LSD_TRACK_SLOTS 8",
        "void native_lsd_gate(uint32_t sample);",
        "native_lsd_account(uint64_t ns)",
        "native_lsd_end(uint32_t slot)",
        "native_lsd_gate(uint32_t sample)",
        "NATIVE_LS_GATE:",
        "NATIVE_LS_GATE_SLOT:",
        "native_lsd_account(native_lsd_ns);",
        "native_lsd_end(native_lsd_slot_index);",
        'if (native_sb_pid > 0 && strncmp(name, "lsd", 3) == 0) {',
        "native_lsd_gate(sample);",
    ):
        require(marker in patch, f"H421 marker missing: {marker}")

    account_start = patch.index("native_lsd_account(uint64_t ns)")
    account_end = patch.index("native_lsd_end(uint32_t slot)", account_start)
    account_body = patch[account_start:account_end]
    require("printf(" not in account_body, "open-accounting path prints")
    require("IOMalloc" not in account_body and "kalloc" not in account_body,
            "open-accounting path allocates memory")

    end_start = account_end
    end_finish = patch.index("native_lsd_gate(uint32_t sample)", end_start)
    end_body = patch[end_start:end_finish]
    require("printf(" not in end_body, "open-completion path prints")
    require("IOMalloc" not in end_body and "kalloc" not in end_body,
            "open-completion path allocates memory")

    source = Path(os.environ.get("H421_NATIVE_SOURCE",
                  ROOT / "drivers/NativeMetal/A540TracePlugin.mm")).resolve()
    environment = dict(os.environ)
    environment["H420_NATIVE_SOURCE"] = str(source)
    subprocess.run([sys.executable, str(NATIVE_CHECKER)], check=True,
                   env=environment, cwd=ROOT)

    print("H421 LaunchServices progress gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h421-launchservices-gate: {error}")
