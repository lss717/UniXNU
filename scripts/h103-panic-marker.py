#!/usr/bin/env python3
"""Print the panic/stall marker that NativeUfsProbe writes outside the persistent ring.

The driver records one small block at relative LBA 250 of the reserved log area (ring slots
start at 257), and it writes that block without taking the I/O lock.  That makes it the one
record that can still land when the ring flush loses the race for the lock, so it answers the
question a silent log cannot: did the machine panic, or did it stall?

Usage:
  scripts/h103-panic-marker.py --input h103log-H311.bin
  scripts/h103-panic-marker.py --input h103log-H311.bin --raw     # dump the whole block
"""

import argparse
import sys

MARKER_BLOCK = 250
BLOCK = 4096


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="8192-block pull of the log area")
    ap.add_argument("--raw", action="store_true", help="print the whole marker block")
    args = ap.parse_args()

    try:
        with open(args.input, "rb") as fh:
            fh.seek(MARKER_BLOCK * BLOCK)
            data = fh.read(BLOCK)
    except OSError as exc:
        print(f"cannot read {args.input}: {exc}", file=sys.stderr)
        return 2

    if len(data) < BLOCK:
        print("input is shorter than one block; is this the 8192-block log pull?",
              file=sys.stderr)
        return 2

    if args.raw:
        sys.stdout.buffer.write(data)
        return 0

    text = data.split(b"\x00")[0].decode("utf-8", "replace").strip()
    if not text:
        print("no marker: the block is empty, so neither hook ran")
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
