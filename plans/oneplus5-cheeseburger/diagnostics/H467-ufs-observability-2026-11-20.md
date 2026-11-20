# H467 UFS observability candidate (2026-11-20)

## Scope

H466 demonstrated one short UTRD stall in each of two same-image boots. The
existing record was insufficient to decide whether the stalled request
completed or whether lock wait time fell. H467 changes observation only:

- monotonically accounts each submitted UTRD;
- records exactly one terminal category among done, OCS timeout, OCS error, and
  doorbell timeout;
- freezes LBA, byte count, direction, and submit time;
- accumulates lock success/failure wait ticks and maximum wait; and
- records watchdog loop progress separately from watchdog recovery.

The timeout, recovery, lock, request, display, scene, and watchdog scheduling
controls remain unchanged.

## Source state and provenance

The patch was generated from the verified H466 `NativeUfsProbe.cpp`
SHA-256 `f6b27d5ec26a799e66c8be9d2890119350636df6b7d50582fc602b6022167b97`.

The current git worktree is based on commit `4efd1f5c` and was initially
materialized from the H466 file. It is not a Git commit of the H466 baseline.
Before this patch is committed for a build, apply it to the corresponding H466
source history, or commit the H466 baseline and H467 patch together with the
provenance hashes in the commit message. Do not treat the H436 base commit
alone as the H467 package source.

The H467 diagnostic patch is
`H467-ufs-observability.patch`; the checker is
`H467-ufs-observability-check.py`.

## Static gates

```text
python3 plans/oneplus5-cheeseburger/diagnostics/H467-ufs-observability-check.py
H467 UFS observation static gate: PASS
H467 marker: H467
H467 status record: unique
H467 terminal accounting: unique updates
H467 device behavior changed: no
```

The status record is emitted every 30 heartbeat ticks and reports:

```text
NATIVE_H467_STATUS: seq done timeout ocs_err dbto flight age_ms
  lba bytes dir lock_ok lock_timeout lock_wait_ms lock_wait_max_ms
  lock_waiters watchdog_seen
```

For a stalled sample, acceptance is `seq - (done + timeout + ocs_err + dbto)
== 0` only when the record says the terminal class; a nonzero difference with
`flight=1` is an open request, not a completion. A lock outcome is only accepted
from the lock counters; no per-request assumption may replace them.

## Build and device gates

Before any boot:

1. sync only through Git; do not copy source across machines;
2. ensure the H466 baseline and H467 patch apply to the builder checkout;
3. run the checker and the existing repository static checks;
4. build on Mac with the documented stage-specific PATH/toolchain;
5. verify changed kernel hash, prelink refusal behavior, payload kernel equality,
   bootargs fit, addon and trust cache; and
6. only then perform a bounded `fastboot boot`.

The H467 device run must retain both the CDC capture and the final 32 MiB H103
window. It should compare completion accounting and lock wait statistics before
deciding whether the H466 stall is resolved. A run without a stalled sample is
a control, not a watchdog pass.

## Current status

`static-gated-candidate-not-built`, `device-tested=false`.
