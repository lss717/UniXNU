#!/usr/bin/env python3
"""Static gate for the H420 BKS timing and main-scene observer repair."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
EVENT_PATCH = ROOT / "patches/xnu/ipc-event-ring.patch"
RING_PATCH = ROOT / "patches/xnu/springboard-bks-focus.patch"
FIX_PATCH = ROOT / "patches/xnu/springboard-bks-timestamp.patch"
NATIVE_DEFAULT = ROOT / "drivers/NativeMetal/A540TracePlugin.mm"
NATIVE_CHECKER = ROOT / "drivers/NativeMetal/tools/check-h420-main-scene.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text(encoding="utf-8")
    event_patch = EVENT_PATCH.read_text(encoding="utf-8")
    ring_patch = RING_PATCH.read_text(encoding="utf-8")
    fix_patch = FIX_PATCH.read_text(encoding="utf-8")

    require('#define H103_BUILD "H420"' in driver, "H420 kernel build tag missing")
    require("NATIVE_DISPLAY_GATE:" in driver, "display gate missing")
    require("NATIVE_BKS_EVENT_RING 512" in ring_patch,
            "H419 dedicated ring missing")

    for marker in (
        "uint64_t event_time;",
        "static int native_bks_responder_pid;",
        "static unsigned native_bks_reply_id;",
        "event->event_time = mach_absolute_time();",
        "absolutetime_to_nanoseconds(event->event_time, &event_ns);",
        "time_ns=%llu",
        "if (msg_id != NATIVE_BKS_MSG_ID)",
        "Only a SpringBoard sample",
        "from_pid == __atomic_load_n(&native_bks_responder_pid",
        "event->from == responder && event->to == springboard",
    ):
        require(marker in fix_patch, f"H420 fix marker missing: {marker}")

    require("native_ipc_event_note('S', kmsg, port" in event_patch,
            "send event is not recorded")
    require("'Q'" in event_patch and "'D'" in event_patch and
            "'R'" in event_patch, "queue/delivery/receive kinds missing")
    require("native_bks_event_note(kind, kmsg, port" in ring_patch,
            "BKS ring is not fed by the generic IPC event path")

    event_start = ring_patch.index("native_bks_event_note(")
    event_end = ring_patch.index("native_bks_focus_set(", event_start)
    event_body = ring_patch[event_start:event_end]
    require("printf(" not in event_body, "IPC path contains direct logging")
    require("IOMalloc" not in event_body and "IOFree" not in event_body,
            "IPC path allocates memory")

    source = Path(os.environ.get("H420_NATIVE_SOURCE", NATIVE_DEFAULT)).resolve()
    environment = dict(os.environ)
    environment["H420_NATIVE_SOURCE"] = str(source)
    subprocess.run([sys.executable, str(NATIVE_CHECKER)], check=True,
                   env=environment, cwd=ROOT)

    print("H420 BKS time and main-scene observer fix gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h420-main-scene: {error}")
