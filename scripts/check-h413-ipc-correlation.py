#!/usr/bin/env python3
"""Validate the H413 fixed-ring IPC correlation patch without a device."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "drivers/NativeUfsProbe/NativeUfsProbe.cpp"
BASE_PATCH = ROOT / "patches/xnu/log-process-state.patch"
EVENT_PATCH = ROOT / "patches/xnu/ipc-event-ring.patch"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    driver = DRIVER.read_text()
    base = BASE_PATCH.read_text()
    event = EVENT_PATCH.read_text()

    require('#define H103_BUILD "H413"' in driver, "H413 build tag missing")
    require("NATIVE_DISPLAY_GATE:" in driver, "existing display gate missing")
    require("NATIVE_SBCHAIN:" in base, "existing SpringBoard chain trace missing")

    for marker in (
        "native_xpc_track_exec",
        "native_ipc_event_note",
        "NATIVE_SBQ:",
        "NATIVE_SBWAIT:",
        "NATIVE_IPC_FOCUS:",
        "NATIVE_IPC_EVT:",
        "ith_state=",
        "ith_kmsg=",
        "req_head0=",
        "local_head0=",
    ):
        require(marker in event, f"event correlation marker missing: {marker}")

    require("'S'" in event and "'Q'" in event and "'D'" in event and "'R'" in event,
            "send/post/dequeue event kinds missing")
    require("ipc_kmsg_queue_first" in event and "ipc_kmsg_queue_next" in event,
            "bounded queue-head inspection missing")
    require("NATIVE_IPC_EVENT_RING 1024" in event, "fixed event ring missing")
    require("osfmk/ipc/ipc_mqueue.c" in event, "IPC mqueue hunk missing")
    require("task_pid(get_threadtask(receiver))" in event and
            "task_pid(get_threadtask(thread))" in event,
            "thread-to-task helper mismatch")

    forbidden = ("0x5b9173", "0x2407", "16149951", "com.apple.backboard")
    for token in forbidden:
        require(token not in event, f"boot-local or service-specific token hardcoded: {token}")

    print("H413 IPC correlation probe: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        sys.exit(f"check-h413-ipc-correlation: {error}")