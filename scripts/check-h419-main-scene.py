#!/usr/bin/env python3
"""Static gate for the H419 BKS focus ring and main-scene observation."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
PATCH = ROOT / "patches/xnu/springboard-bks-focus.patch"
EVENT_PATCH = ROOT / "patches/xnu/ipc-event-ring.patch"
NATIVE_DEFAULT = ROOT / "drivers/NativeMetal/A540TracePlugin.mm"
NATIVE_CHECKER = ROOT / "drivers/NativeMetal/tools/check-h419-main-scene.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text(encoding="utf-8")
    patch = PATCH.read_text(encoding="utf-8")
    event_patch = EVENT_PATCH.read_text(encoding="utf-8")

    require('#define H103_BUILD "H419"' in driver, "H419 kernel build tag missing")
    require("NATIVE_DISPLAY_GATE:" in driver, "display gate missing")
    require("a540DisplayGate (6000 + sample * 30);" in driver,
            "late display sampler binding changed")

    for marker in (
        "NATIVE_BKS_EVENT_RING 512",
        "NATIVE_BKS_MSG_ID 0x5b9173u",
        "native_bks_peer",
        "native_bks_event_note",
        "native_bks_focus_set",
        "native_bks_focus_emit",
        "NATIVE_BKS_FOCUS:",
        "NATIVE_BKS_EVT:",
        "queue=0x%llx",
        "remote=0x%llx",
        "local=0x%llx",
        "tid=%llu result=0x%x",
    ):
        require(marker in patch, f"BKS focus marker missing: {marker}")
    require("native_ipc_event_note('S', kmsg, port" in event_patch,
            "send event is not recorded")
    require("'Q'" in event_patch and "'D'" in event_patch and
            "'R'" in event_patch,
            "queue/delivery/receive event kinds missing")
    require("native_bks_event_note(kind, kmsg, port" in patch,
            "generic IPC event path does not feed the BKS ring")
    require("native_bks_focus_set(remote_port, local_port, msg_id);" in patch,
            "dynamic request/reply focus binding missing")
    require("written >= NATIVE_BKS_EVENT_RING" in patch and
            "native_bks_events_lost" in patch,
            "dedicated ring loss accounting missing")

    event_start = patch.index("native_bks_event_note(")
    event_end = patch.index("native_bks_focus_set(", event_start)
    event_body = patch[event_start:event_end]
    require("printf(" not in event_body,
            "IPC path contains direct logging")
    require("IOMalloc" not in event_body and "IOFree" not in event_body,
            "IPC path allocates memory")

    source = Path(os.environ.get("H419_NATIVE_SOURCE", NATIVE_DEFAULT)).resolve()
    environment = dict(os.environ)
    environment["H419_NATIVE_SOURCE"] = str(source)
    subprocess.run([sys.executable, str(NATIVE_CHECKER)], check=True,
                   env=environment, cwd=ROOT)

    print("H419 BKS focus and main-scene observation gate: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h419-main-scene: {error}")
