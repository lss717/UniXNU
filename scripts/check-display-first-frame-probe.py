#!/usr/bin/env python3
"""Validate the read-only first-frame gate instrumentation."""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
PATCH = ROOT / "patches/xnu/log-process-state.patch"
TARGET_PATCH = ROOT / "patches/xnu/springboard-lsd-target-port.patch"
SIGNAL_PATCH = ROOT / "patches/xnu/sigbus-ring.patch"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text()
    patch = PATCH.read_text()
    target_patch = TARGET_PATCH.read_text()
    signal_patch = SIGNAL_PATCH.read_text()

    build = re.search(r'#define H103_BUILD "(H[0-9]+)"', driver)
    require(build and int(build.group(1)[1:]) >= 420,
            "expected a post-H420 build tag")
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
    require("NATIVE_TARGETPORT:" in target_patch,
            "target receive-port record missing")
    require("NATIVE_TARGETWAIT:" in target_patch,
            "target receive-waiter record missing")
    require("target.port == native_sb_target_port" in target_patch,
            "target send/receive port identity comparison missing")
    require('strncmp(p->p_comm, "SpringBoard", 11) != 0' in signal_patch,
            "SpringBoard signal filter still excludes signals other than SIGABRT")
    signal_sites = (
        "native_sigbus_probe(p, signum, OS_REASON_NULL",
        "native_sigbus_probe(p, signum, signal_reason",
        "native_sigbus_probe(p, SIGKILL, signal_reason",
    )
    for marker in signal_sites:
        require(marker in signal_patch,
                f"signal wrapper coverage missing: {marker}")

    # The probe must remain observation-only: these files are the behavioral
    # boundary and are deliberately untouched from H420 onward.
    display = ROOT / "drivers/NativeMobileDisplay"
    require(display.is_dir(), "display submodule missing")
    print(f"{build.group(1)} display first-frame gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-display-first-frame-probe: {error}")
