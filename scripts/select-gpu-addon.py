#!/usr/bin/env python3
"""Select exact entries from an NGPUADD2 addon without recompressing them."""

import struct
import sys
from pathlib import Path


MAGIC = b"NGPUADD2"
HEADER = struct.Struct("<8sIIQ")
ENTRY = struct.Struct("<IIQQII")


def padded(value):
    return value + bytes(-len(value) % 8)


def read_entries(blob):
    magic, count, repair_offset, total_size = HEADER.unpack_from(blob)
    if magic != MAGIC or total_size != len(blob):
        raise ValueError("invalid NGPUADD2 header")
    body_end = repair_offset or total_size
    offset = HEADER.size
    entries = {}
    order = []
    while offset < body_end:
        start = offset
        path_len, mode, size, packed_size, crc, stored = ENTRY.unpack_from(blob, offset)
        if path_len == 0 or path_len > 160:
            raise ValueError("invalid addon path length")
        offset += ENTRY.size
        encoded = blob[offset:offset + path_len]
        offset += len(padded(encoded))
        offset += len(padded(blob[offset:offset + packed_size]))
        path = encoded[:-1].decode("utf-8")
        entries[path] = blob[start:offset]
        order.append(path)
    return entries, order, blob[body_end:]


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    wanted = sys.argv[3:]
    entries, order, tail = read_entries(source.read_bytes())
    selected = wanted or order
    missing = [path for path in selected if path not in entries]
    if missing:
        raise SystemExit("missing addon entries: " + ", ".join(missing))
    body = b"".join(entries[path] for path in selected)
    total_size = HEADER.size + len(body) + len(tail)
    blob = MAGIC + struct.pack("<IIQ", len(selected), len(body) + HEADER.size if tail else 0,
                               total_size) + body + tail
    output.write_bytes(blob)
    for path in selected:
        print(path)
    print(f"{output}: {len(selected)} files, {len(blob)} bytes")


if __name__ == "__main__":
    main()
