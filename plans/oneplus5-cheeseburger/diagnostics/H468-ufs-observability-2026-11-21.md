# H468 UFS observability follow-up (2026-11-21)

## Why H468 exists

H467 changed UFS observation only and was built and booted on the unique local serial 16149951. The retained H103 slot records carry the H467 marker and the kernel reached 168 seconds, but they contain no NATIVE_H467_STATUS record. The boot argument line reports hbTimer=0. The H467 status emission was placed inside NativeUfsProbe::hbTimerTick(), which is only armed when h103-hb-timer=1. That timer was disabled by the tested image. Consequently, the first H467 run neither showed a successful UFS request nor a lock wait. It also did not exercise watchdog recovery.

The H467 image also froze request identity from gUfsLastLba and gUfsLastBytes, which are assigned by the outer read/write helper before submission. Copying them from the submit path after a later command could describe an earlier command. H468 corrects that observation defect and moves status emission to the watchdog thread that the H467 log proves runs.

## Single-variable change

H468 keeps every H467 UFS timeout, recovery, lock, request-order, display, scene, and watchdog scheduling control unchanged. It changes only:

- the build marker from H467 to H468;
- status emission from the unarmed work-loop timer to the running watchdog thread;
- status cadence to every 30 seconds of that thread;
- current READ(10) LBA extraction from the submitted CDB and current byte count from the submit call;
- recovery-attempt accounting alongside the already existing recovery-success accounting; and
- status emission continues after a recorded UFS stall, because that is when the request-level result matters.

The recovery attempt counter increments after the existing one-second recovery rate gate accepts an attempt. It does not alter that gate or make an extra attempt.

This is a diagnostic-only change. It does not prove that the H467 request completed or that lock waiting fell. A no-anomaly H468 control run is still not a watchdog validation.

## Source provenance

H468 is based on tested H467 source commit 080beaaeb7baa281852dded02737ecd4e465479e.

plans/oneplus5-cheeseburger/diagnostics/H468-ufs-observability.patch
plans/oneplus5-cheeseburger/diagnostics/H468-ufs-observability-check.py

The patch is a delta from H467 and must apply with plain git apply --check. The source file, patch, and resulting build hashes are recorded in the build manifest. Do not reuse the H467 boot hash for an H468 result.

## Status record

NATIVE_H468_STATUS: seq done timeout ocs_err dbto recover recovered flight age_ms lba bytes dir lock_ok lock_timeout lock_wait_ms lock_wait_max_ms lock_waiters watchdog_seen

For a stalled sample:

- seq is submitted UTRDs.
- done + timeout + ocs_err + dbto are terminal outcomes.
- recover/recovered are accepted recovery attempts and successful controller recoveries.
- flight=1 with nonzero age_ms identifies an open request.
- lba, bytes, and dir identify the current submitted command.
- lock status comes only from lock_ok, lock_timeout, and wait counters.

A later status row whose stable request advances while flight returns to zero is evidence that I/O continued. An exact completion claim requires either a terminal-counter increment for the same tracked request or an explicit matching completion record. Do not infer a timeout merely because a request is visible in flight.

## H467 first device run

Run directory: E:\WindowsData\Project\ios\main-route\display-first-frame\logs\H467\device\20261121-003000

H467 boot image SHA-256: 2700249705d428691cad658f84a5b17511923ec591a656ac765c61ef883d41bc. The image was rechecked immediately before fastboot boot, which returned Sending OKAY and Booting OKAY.

The H103 ring retained boot id 7b371778, build H467, 120 slots, and 168 seconds of messages. It contains NATIVE_BUILD: H467. It does not contain H467 status, GPU addon, Metal, frame, UFS lock timeout, OCS, recovery, read-failure, stall, panic or watchdog records.

The CDC port never published. After the capture timeout, Android returned with boot_completed=1; a later authorized recovery reboot reached TWRP 3.4.0_9-10-mauronofrio. The device spontaneously rebooted, but the cause is not established by the retained record. Classify the run as H467-boot-spontaneous-reboot-before-CDC-and-before-status-observation. Do not call this a watchdog pass or a delayed watchdog recovery.

The H467 tail SHA-256 is a0c31ba06cce2de0da1a96cf8aec045e20daa517586650c003dffe93c9739299. The pre-reboot and post-reboot tails are byte-identical. Re-reading the tail after Android/TWRP did not produce a new H467 boot id or additional H103 slots.

## H465/H466 comparison

H465 Metal heap result is heap-return-and-texture-contract-smoke-partial-pass: a readable A540Trace__MTLHeap, two successful texture-contract checks, a self-completing command buffer, and a missing third heap-contract success followed by UFS read failures. It is not a complete heap ABI or object lifetime validation.

H466 run 2 has a short UTRD stall at 559.626816 seconds while request 89d1aa/8 remains in flight. No OCS, lock timeout, recovery, read failure, SIGBUS or panic was logged. I/O later continued and ufsFlight returned to zero, but the exact completion of that request was not retained. H466 run 1 had no stall and is a watchdog-not-exercised-control, not a watchdog pass.

Synthetic display transfer/frame counts and a SpringBoard product frame must be recorded separately. H465/H466 display gate evidence proves the display driver accepted transfer and selector activity; SpringBoard still reported workspace=0 class=nil and an empty layer. That evidence does not establish a product first frame.

## Build and device gates for H468

1. Sync the H468 commit to the Mac by Git and confirm the source commit and clean driver sources on both machines.
2. Run the H468 checker and patch replay check.
3. Build with the documented toolchain and verify that the kernel, payload and boot SHA each differ from H467.
4. Verify payload kernel equality, bootargs fit, and the unchanged trust-cache, addon, and display controls.
5. If no new evidence requires a source change, run at most one bounded H468 boot after identity and process ownership checks.
6. Retain both CDC capture and final 32 MiB H103 window. Do not claim completion without a matching counter transition or completion record.
7. If a second run is needed to test reproducible variance, change only the run number, not the image or any other variable.
