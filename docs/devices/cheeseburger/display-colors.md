# OnePlus 5 (cheeseburger) display test pattern colours

`NativeLegacyDisplay` paints a 2×2 panel in the top-right corner of the framebuffer so that
the boot stage, the state of the display user client and whether a frame has been submitted
are visible without user space. This page records what every colour in every cell means.

- Implementation: `drawTestPattern()` and `drawHeartbeatCell()` in
  `drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp`;
- Repaint scheduling: `drivers/NativeUfsProbe/NativeUfsProbe.cpp`;
- Flag bits: `patches/xnu/log-boot-flags.patch`,
  `patches/xnu/log-exit-flags.patch` and
  `patches/xnu/log-iokit-trace.patch`.

> USB CDC live serial logging, UXL1 decoding and the normal-reboot command are in
> [USB CDC log and normal-reboot console](usb-com-log-guide.md).

![Test pattern colour swatches](/panel-colors.svg)

> The image above shows the exact pixel values. The hexadecimal value is authoritative;
> the colour names are only there to make the tables readable.

## Position and repaint

| Item | Value |
| :--- | :--- |
| Position | top-right of the framebuffer, `x0 = w - 2 × panel`, `y0 = 0` |
| Cell size | 128×128 each; the bottom-right cell is split horizontally into two 128×64 halves |
| Small screens | `panel = min(128, w/2, h/2)` |
| Repaint | by the UFS heartbeat thread: about once per second before backboardd execs, about every 10 seconds once `h107GateOpen()` is true, and only when `native_boot_flags & 0xfff` changes after backboardd has exec'd |
| 1 Hz repaint | `h103-hb-timer=1` (`IOTimerEventSource`) or `h103-hb-timer=2` (`timer_call`) |
| Disable | `h103-skip-pattern=1` |

> ⚠️ As soon as a user client presents its first frame the panel is overdrawn by that frame
> and is not restored by default. A missing panel, or colours that stopped changing, do not
> mean the display backend stopped working; confirm with
> `plans/oneplus5-cheeseburger/STATUS.md` and the persistent log.

## The 2×2 panel

### Top-left: user-space frontier

Evaluate top to bottom and stop at the first match. `0x20` and `0x40` are sticky: once set,
they stay set even if the process is restarted.

| Colour | Pixel | Flag | Meaning |
| :--- | :--- | :--- | :--- |
| Purple | `#8000FF` | `& 0x20` | SpringBoard exited (the `kern_exit` hook does not distinguish crashes) |
| Magenta | `#FF00FF` | `& 0x40` | backboardd exited (visible while SpringBoard has not) |
| White | `#FFFFFF` | `0x08` and `0x04` | both backboardd and SpringBoard have exec'd and neither has exited |
| Green | `#00FF00` | `& 0x08` | only SpringBoard has exec'd |
| Sky blue | `#0080FF` | `& 0x04` | only backboardd has exec'd (SpringBoard has not) |
| Orange | `#FF8000` | `& 0x02` | only driverkitd has exec'd |
| Yellow | `#FFFF00` | `& 0x01` | only logd_helper has exec'd |
| Red | `#FF0000` | none of the above | user space has not advanced; the panel itself proves the GOP backend runs |

### Top-right: display client and IOKit matching

While a client exists this cell shows the caller of the **most recent** `newUserClient`.
Only when there is no client does it fall back to backboardd's IOKit match flags.

**A client exists (`native_legacy_client_calls > 0`)**

| Colour | Pixel | Meaning |
| :--- | :--- | :--- |
| Yellow | `#FFFF00` | comm starts with `IOMFB_FDR` (FDR loader) |
| Sky blue | `#0080FF` | comm starts with `backboard` (backboardd) |
| Magenta | `#FF00FF` | any other process |

**No client (falls back to `native_boot_flags`)**

| Colour | Pixel | Flag | Meaning |
| :--- | :--- | :--- | :--- |
| Purple | `#8000FF` | `0x400` | backboardd queried a dictionary containing `IOMobile` and nothing matched |
| Blue | `#0000FF` | `0x200` | backboardd queried a dictionary containing `IOMobile` and it matched (also sets `0x1000`) |
| Orange | `#FF8000` | `0x080` | backboardd has issued some IOService matching call, but no `IOMobile` query has been recorded |
| Dark gray | `#404040` | none | backboardd has not queried IOKit at all |

> `0x200` and `0x400` are cleared and re-set on every `IOMobile*` match, so they describe the
> **last** query only. `0x080` is sticky: orange therefore only shows while no `IOMobile*`
> query has ever been recorded.

### Bottom-left: user client creation count

`native_legacy_client_calls` counts how often `newUserClient` was called, including attempts
that failed afterwards.

| Colour | Pixel | Count |
| :--- | :--- | :--- |
| Dark gray | `#404040` | 0 |
| Blue | `#0000FF` | 1 to 9 |
| Green | `#00FF00` | 10 to 99 |
| Orange | `#FF8000` | ≥ 100 |

### Bottom-right: frame swap and matching state

Split horizontally; the two halves are read independently.

**Top half: frame swap progress (purple wins)**

| Colour | Pixel | Meaning |
| :--- | :--- | :--- |
| Purple | `#8000FF` | a swap validation was called (`swap_validation_calls > 0`; accepted and rejected both count), so this long-term hides white |
| White | `#FFFFFF` | a frame copy was called (`transfer_calls > 0`); failed copies count too |
| Dark gray | `#404040` | no client has ever submitted a frame |

**Bottom half: backboardd's IOKit matching state**

Identical to the "no client" fallback above: purple `0x400`, blue `0x200`, orange `0x080`,
dark gray `#404040`. It is independent of the top half, so the match result stays readable
even while the FDR loader holds the client.

## 16×16 status cells

The cells are 16 px wide at x = 0, 20, 40, 60 and 80, all at y = 0, measured from the top-left corner of the framebuffer. The first four keep their order; H410 appends the USB status cell.

| Position | Meaning | Colours and state values |
| :--- | :--- | :--- |
| (0, 0) | CPU frequency observation (`sheng_cpufreq_probe`) | dark gray `0`: not run<br>red `1`: an enabled cluster is below 1 GHz, or no cluster is enabled<br>green `2`: every enabled cluster is at or above 1 GHz<br>purple `3`: OSM mapping failed<br>orange `4` / blue `5`: reserved in the driver, never produced by the current probe |
| (20, 0) | A540 accelerator probe | dark gray `#404040`: not attempted (`0`)<br>green: service published (`6`)<br>red: failure or intermediate state (`1` / `3` / `4` / `5`; see the `NATIVE_A540` log) |
| (40, 0) | Heartbeat cell | white / orange: flips at 1 Hz (`timer_call`, 19 200 000 timebase ticks); the 2×2 repaint also repaints this cell |
| (60, 0) | H103 persistent-log slot writer | red `0`: the write branch has not been reached yet (the default `h103-slot-thread=0` commonly keeps it red)<br>blue `3`: the 2-second slot thread is running but the write window is not ready (missing `fLogFirst` / `fLogBlocks` / `fLogDma` / `fReady` / `fLock`)<br>yellow `1`: the window is ready and writing started, but no write has succeeded yet<br>green `2`: at least one slot and header write succeeded<br>cyan `#00FFFF` (state `5`): USB live logging is healthy and the disk sink is intentionally paused, not a USB-start failure and not an error |
| (80, 0) | H410 USB CDC live-log link | dark gray `#404040`: the USB driver has not started<br>yellow `#FFFF00`: started but the host has not configured the CDC data endpoints (not connected)<br>green `#00FF00`: connected and idle<br>green/white: Bulk-IN log frames are actually completing (alternates at the ~1 Hz panel repaint; returns to green ~500 ms after the last successful completion) |

## Quick triage

1. **Top-left**: did SpringBoard exec, and did it exit? A red cell means user space never started.
2. **Top-right**: with no client, read `0x400`. Purple means backboardd queried `IOMobile*` and nothing matched; orange means it never queried `IOMobile*` at all.
3. **Bottom-right, top half**: dark gray, then white, then purple tells "nothing submitted" from "a copy was attempted" from "swap validation has run".
4. **Bottom-left**: combined with the top-right cell, tells "nothing opened it" from "something opened it, but it was not backboardd".

> The fourth cell is cyan while USB live logging is healthy and the disk sink is paused.
> The colours are a sample taken at the last repaint. To locate the actual failure, combine
> them with `plans/oneplus5-cheeseburger/STATUS.md`, the `NATIVE_EXEC` / `NATIVE_IOKIT` /
> `NATIVE_LEGACY` console lines and the persistent log slots.
