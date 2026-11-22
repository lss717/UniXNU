#!/usr/bin/env python3
"""Overlay exact entries from one NGPUADD2 addon onto another."""

import struct
import sys
from pathlib import Path


MAGIC = b"NGPUADD2"
HEADER = struct.Struct("<8sIIQ")
ENTRY = struct.Struct("<IIQQII")


def padded(value: bytes) -> bytes:
    return value + bytes(-len(value) % 8)


def read_entries(blob: bytes):
    magic, count, repair_offset, total_size = HEADER.unpack_from(blob)
    if magic != MAGIC or total_size != len(blob) or count > 256:
        raise ValueError("invalid NGPUADD2 header")
    body_end = repair_offset or total_size
    offset = HEADER.size
    entries = {}
    order = []
    while offset < body_end:
        start = offset
        path_len, mode, size, packed_size, crc, stored = ENTRY.unpack_from(
            blob, offset
        )
        if path_len == 0 or path_len > 160:
            raise ValueError("invalid addon path length")
        offset += ENTRY.size
        encoded = blob[offset:offset + path_len]
        offset += len(padded(encoded))
        if offset + packed_size > len(blob):
            raise ValueError("invalid addon payload length")
        offset += len(padded(blob[offset:offset + packed_size]))
        path = encoded[:-1].decode("utf-8")
        if path in entries:
            raise ValueError("duplicate addon path " + path)
        entries[path] = blob[start:offset]
        order.append(path)
    return entries, order, blob[body_end:]


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    base = Path(sys.argv[1]).resolve()
    overlay = Path(sys.argv[2]).resolve()
    output = Path(sys.argv[3]).resolve()
    if output.exists():
        raise SystemExit("Refuse to overwrite " + str(output))

    base_entries, order, tail = read_entries(base.read_bytes())
    overlay_entries, overlay_order, overlay_tail = read_entries(overlay.read_bytes())
    if overlay_tail or tail:
        raise SystemExit("Repair tails are not supported by this overlay tool")

    replaced = []
    added = []
    for path in overlay_order:
        if path in base_entries:
            replaced.append(path)
        else:
            added.append(path)
            order.append(path)
        base_entries[path] = overlay_entries[path]

    body = b"".join(base_entries[path] for path in order)
    blob = MAGIC + struct.pack("<IIQ", len(order), 0, HEADER.size + len(body)) + body
    output.write_bytes(blob)
    print("replaced:", ", ".join(replaced))
    print("added:", ", ".join(added))
    print(f"{output}: {len(order)} files, {len(blob)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
