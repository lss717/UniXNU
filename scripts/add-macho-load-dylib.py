#!/usr/bin/env python3
"""Add one LC_LOAD_DYLIB command to a thin 64-bit little-endian Mach-O."""

import struct
import sys
from pathlib import Path


MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_LOAD_DYLIB = 0xC
HEADER_SIZE = 32
SEGMENT_64_SIZE = 72
SECTION_64_SIZE = 80


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def minimum_section_offset(data: bytes, command_offset: int, command_count: int) -> int:
    minimum = len(data)
    cursor = HEADER_SIZE
    for _ in range(command_count):
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > command_offset:
            raise SystemExit("Malformed Mach-O load command")
        if command == LC_SEGMENT_64 and size >= SEGMENT_64_SIZE:
            section_count = struct.unpack_from("<I", data, cursor + 64)[0]
            section = cursor + SEGMENT_64_SIZE
            for _ in range(section_count):
                if section + SECTION_64_SIZE > cursor + size:
                    raise SystemExit("Malformed segment sections")
                section_size = struct.unpack_from("<Q", data, section + 48)[0]
                section_offset = struct.unpack_from("<I", data, section + 56)[0]
                if section_size and section_offset:
                    minimum = min(minimum, section_offset)
                section += SECTION_64_SIZE
        cursor += size
    if cursor != command_offset:
        raise SystemExit("Mach-O command count/size disagreement")
    return minimum


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1])
    dylib_path = sys.argv[2].encode("utf-8") + b"\0"
    output = Path(sys.argv[3])
    data = bytearray(source.read_bytes())
    magic, _cpu, _sub, _filetype, command_count, command_size = struct.unpack_from(
        "<IiiIII", data, 0
    )
    if magic != MH_MAGIC_64:
        raise SystemExit("Only thin little-endian MH_MAGIC_64 is supported")
    command_offset = HEADER_SIZE + command_size
    minimum = minimum_section_offset(data, command_offset, command_count)
    body_size = 24 + len(dylib_path)
    command_bytes = align(body_size, 8)
    if command_offset + command_bytes > minimum:
        raise SystemExit("No Mach-O header padding for the new load command")
    command = (
        struct.pack(
            "<IIIIII",
            LC_LOAD_DYLIB,
            command_bytes,
            24,
            2,
            0x10000,
            0x10000,
        )
        + dylib_path
    )
    data[command_offset:command_offset + command_bytes] = command.ljust(
        command_bytes, b"\0"
    )
    struct.pack_into("<I", data, 16, command_count + 1)
    struct.pack_into("<I", data, 20, command_size + command_bytes)
    output.write_bytes(data)
    print(
        f"added LC_LOAD_DYLIB {sys.argv[2]} to {output} "
        f"({command_count + 1} commands, +{command_bytes} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
