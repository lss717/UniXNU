#!/usr/bin/env python3
"""Static gate for H425 renderer crash attribution."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
METAL = ROOT / "drivers/NativeMetal/A540TracePlugin.mm"
H423_CHECKER = ROOT / "scripts/check-h423-ls-lifecycle.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text(encoding="utf-8")
    metal = METAL.read_text(encoding="utf-8")

    require('#define H103_BUILD "H424"' in driver,
            "H425 must keep the tested H424 kernel")
    for marker in (
        'caller("builder", "build", "H425");',
        "struct NativeDlInfo {",
        "const char *dli_fname;",
        "void *dli_fbase;",
        "const char *dli_sname;",
        "void *dli_saddr;",
        'extern "C" int dladdr(const void *, struct NativeDlInfo *);',
        "dladdr((const void *)(uintptr_t)pc, &info)",
        "symbol=%s symoff=0x%llx",
        'report_signal_image("pc", pc);',
        'report_signal_image("lr", lr);',
        "report_signal_image(tag, ret);",
    ):
        require(marker in metal, f"H425 marker missing: {marker}")
    for forbidden in ("_dyld_image_count()", "_dyld_get_image_header(index)"):
        require(forbidden not in metal, f"H425 retained flawed API: {forbidden}")

    subprocess.run([sys.executable, str(H423_CHECKER)],
                   check=True, cwd=ROOT)
    print("H425 renderer crash attribution gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h425-crash-attribution: {error}")
