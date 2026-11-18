#!/usr/bin/env python3
"""Validate the read-only first-frame gate instrumentation."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
PATCH = ROOT / "patches/xnu/zzzzzzzzzzz-h103-proc-state.patch"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text()
    patch = PATCH.read_text()

    require('#define H103_BUILD "H418"' in driver, "H418 build tag missing")
    require("NATIVE_DISPLAY_GATE:" in driver, "display gate record missing")
    require("native_legacy_client_stats (" in driver, "display client counters not consumed")
    require("val=%u xf=%u fr=%u" in driver, "validation/transfer/frame fields missing")
    require("s345=%u/%u/%u" in driver, "selector 3/4/5 fields missing")
    require("a540DisplayGate (6000 + sample * 30);" in driver,
            "late sampler does not bind display state to SpringBoard sample")
    require("a540DisplayGate (sample);" in driver,
            "general sampler does not bind display state to SpringBoard sample")

    require("NATIVE_SBCHAIN:" in patch, "SpringBoard chain record missing")
    require('(sample % 30) == 0' in patch, "SpringBoard gate is not rate-limited")
    require("msg=0x%x hdr=%d" in patch, "message id/header validity missing")
    require("svc=%s rcv=%u/%d/%s q=%d sr=%u so=%u" in patch,
            "service/receiver/port state missing")
    require("req=%u/%d/%s q=%d sr=%u so=%u" in patch,
            "request port queue/send-once state missing")
    require("ld_out=%llu ld_in=%llu ld_reply=%llu ld_other=%llu" in patch,
            "launchd request/reply counters missing")

    # The probe must remain observation-only: these files are the behavioral
    # boundary and are deliberately untouched in H418.
    display = ROOT / "drivers/NativeMobileDisplay"
    require(display.is_dir(), "display submodule missing")
    print("H418 display first-frame gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-display-first-frame-probe: {error}")
