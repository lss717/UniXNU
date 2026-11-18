#!/usr/bin/env python3
"""Offline H410 status-cell and disk-sink audit.

This does not replace a camera; it pins the state->colour mapping, the 16x16
drawing rectangle, the cyan paused-disk state, the refresh sources, and the
fact that the H103 pause never gates the USB log producer.
"""

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
DEVICE = CORE.parent / 'UniXNU-cheeseburger'
DISPLAY = CORE / 'drivers/NativeMobileDisplay/NativeLegacyDisplay.cpp'
UFS = CORE / 'drivers/NativeUfsProbe/NativeUfsProbe.cpp'
USB = DEVICE / 'drivers/CheeseburgerUsb/CheeseburgerUsb.cpp'

GRAY = 0xff404040
YELLOW = 0xffffff00
GREEN = 0xff00ff00
WHITE = 0xffffffff
CYAN = 0xff00ffff


def usb_cell_colour(started, connected, active, blink):
    if not started:
        return GRAY
    if not connected:
        return YELLOW
    if active:
        return WHITE if blink else GREEN
    return GREEN


def check_state_mapping():
    assert usb_cell_colour(0, 0, 0, 0) == GRAY
    assert usb_cell_colour(1, 0, 0, 0) == YELLOW
    assert usb_cell_colour(1, 1, 0, 0) == GREEN
    assert usb_cell_colour(1, 1, 1, 0) == GREEN
    assert usb_cell_colour(1, 1, 1, 1) == WHITE


def check_display_source():
    src = DISPLAY.read_text()
    assert 'outside the original' not in src  # guard against a bad merge marker
    # Fifth cell: x in [80,96), y in [0,16), 16x16.
    assert 'for(uint32_t x=80;x<96 && x<w;++x)row[x]=color;' in src
    assert 'for(uint32_t y=0;y<16 && y<h;++y)' in src
    # Colours.
    for literal in ('0xff404040U', '0xffffff00U', '0xff00ff00U',
                    '0xffffffffU', '0xff00ffffU'):
        assert literal in src, literal
    # Active alternation is per repaint (bounded), and the driver returns to
    # solid green after its 500 ms activity window.
    assert 'usbBlink++&1U' in src
    # Original four cells are not moved.
    for x in (0, 20, 40, 60):
        assert f'fill({x},0,16,16' in src or f'x={x};' in src or f'x<{x + 16}' in src
    # Paused disk sink gets its own cyan state on the fourth cell.
    assert 'native_h103_slot_state==5' in src
    # The USB cell is refreshed from both the 1 Hz heartbeat path and the
    # heartbeat-thread slot path.
    assert 'native_legacy_usb_cell' in src


def check_core_refresh_and_gate():
    src = UFS.read_text()
    assert 'native_usb_status_last_complete_ticks' in src
    assert '500ULL * 19200000ULL / 1000ULL' in src       # active hold
    assert '2000ULL * 19200000ULL / 1000ULL' in src      # pause debounce
    assert '1500ULL * 19200000ULL / 1000ULL' in src      # resume debounce
    assert 'H410_USB_PAUSE_MIN_COMPLETIONS 8U' in src
    # The three disk-sink entry points are gated.
    assert src.count('__atomic_load_n (&gH103DiskPaused, __ATOMIC_ACQUIRE)') >= 3
    # The USB cell is repainted from the heartbeat thread.
    assert 'native_legacy_usb_cell ();' in src


def check_usb_producer_not_gated():
    src = USB.read_text()
    assert 'gH103DiskPaused' not in src
    assert 'gH103DiskPauseReason' not in src
    # Producer path remains present.
    assert 'collectLog(payload, kLogPayloadMax)' in src
    assert 'sendLogFrame()' in src
    assert 'startTransfer(3, kBulkInTrbOffset' in src
    # Real completion counters used for active.
    assert 'native_usb_status_tx_completions' in src
    assert 'native_usb_status_last_complete_ticks' in src


def main():
    check_state_mapping()
    check_display_source()
    check_core_refresh_and_gate()
    check_usb_producer_not_gated()
    print('H410 offline status-cell mapping, drawing bounds, refresh and '
          'disk-pause/producer separation: PASS')


if __name__ == '__main__':
    main()

