#!/usr/bin/env python3
"""Add one LC_LOAD_DYLIB command to a thin 64-bit little-endian Mach-O.

Usage:
  add-macho-dylib-load.py INPUT INSTALL_NAME OUTPUT

The command is inserted before LC_CODE_SIGNATURE. The Mach-O must have enough
zero padding between its existing load commands and the first section. This
tool only changes the Mach-O header and load-command area; the caller must
re-sign the output with the required page size.
"""

import pathlib
import struct
import sys


MH_MAGIC_64 = 0xFEEDFACF
LC_LOAD_DYLIB = 0x0C
LC_CODE_SIGNATURE = 0x1D
LC_SEGMENT_64 = 0x19


def align8(value: int) -> int:
    return (value + 7) & ~7


def first_section_offset(data: bytes, ncmds: int) -> int:
    offsets = []
    cursor = 32
    for _ in range(ncmds):
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > len(data):
            raise SystemExit("malformed load command")
        if command == LC_SEGMENT_64:
            nsects = struct.unpack_from("<I", data, cursor + 64)[0]
            section = cursor + 72
            for _ in range(nsects):
                file_offset = struct.unpack_from("<I", data, section + 48)[0]
                if file_offset:
                    offsets.append(file_offset)
                section += 80
        cursor += size
    if not offsets:
        raise SystemExit("no file-backed Mach-O section")
    return min(offsets)


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)

    source = pathlib.Path(sys.argv[1])
    install_name = sys.argv[2]
    output = pathlib.Path(sys.argv[3])
    if not install_name.startswith("/") or "\0" in install_name:
        raise SystemExit("INSTALL_NAME must be an absolute NUL-free path")
    if output.exists():
        raise SystemExit("refuse to overwrite " + str(output))

    data = bytearray(source.read_bytes())
    magic, cputype, _cpusubtype, filetype, ncmds, sizeofcmds, _flags, _reserved = (
        struct.unpack_from("<IiiIIIII", data, 0)
    )
    if magic != MH_MAGIC_64:
        raise SystemExit("require thin little-endian 64-bit Mach-O")
    if filetype != 2:
        raise SystemExit("require MH_EXECUTE")
    old_header_end = 32 + sizeofcmds
    if old_header_end > len(data):
        raise SystemExit("load commands extend beyond the file")

    path_bytes = install_name.encode("utf-8") + b"\0"
    command_size = align8(24 + len(path_bytes))
    command = bytearray(command_size)
    struct.pack_into("<IIIIII", command, 0, LC_LOAD_DYLIB, command_size, 24, 2, 0x10000, 0x10000)
    command[24:24 + len(path_bytes)] = path_bytes

    insert_at = old_header_end
    cursor = 32
    existing = []
    for _ in range(ncmds):
        kind, size = struct.unpack_from("<II", data, cursor)
        if kind == LC_LOAD_DYLIB:
            name_offset = struct.unpack_from("<I", data, cursor + 8)[0]
            if not 24 <= name_offset < size:
                raise SystemExit("malformed LC_LOAD_DYLIB")
            name = bytes(data[cursor + name_offset:cursor + size]).split(b"\0", 1)[0].decode("utf-8")
            existing.append(name)
        if kind == LC_CODE_SIGNATURE:
            insert_at = cursor
        cursor += size

    if install_name in existing:
        raise SystemExit("install name already present: " + install_name)

    new_header_end = old_header_end + command_size
    section_start = first_section_offset(data, ncmds)
    if new_header_end > section_start:
        raise SystemExit(
            f"not enough header padding: need {new_header_end:#x}, first section {section_start:#x}"
        )
    if any(data[old_header_end:new_header_end]):
        raise SystemExit("refusing to overwrite nonzero header padding")
    shifted = bytearray(data)
    shifted[insert_at + command_size:old_header_end + command_size] = data[insert_at:old_header_end]
    shifted[insert_at:insert_at + command_size] = command
    struct.pack_into("<I", shifted, 16, ncmds + 1)
    struct.pack_into("<I", shifted, 20, sizeofcmds + command_size)

    output.write_bytes(shifted)
    print(
        f"added {install_name}: command={command_size} bytes "
        f"ncmds={ncmds}->{ncmds + 1} sizeofcmds={sizeofcmds:#x}->{sizeofcmds + command_size:#x} "
        f"header_end={old_header_end:#x}->{new_header_end:#x} first_section={section_start:#x}"
    )
    print(f"output {output}: {len(shifted)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
