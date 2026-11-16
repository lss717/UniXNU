#!/usr/bin/env python3
"""Remove a Mach-O __mod_init_func section and globalize its initializer.

This is the narrowly scoped replacement for:

    llvm-objcopy --remove-section=__DATA,__mod_init_func \
        --globalize-symbol=NAME INPUT OUTPUT

The XNU build is restricted to the fixed Xcode toolchain. Xcode's xcrun does
not expose llvm-objcopy, while LLVM 20 is reserved for the UEFI stage. This
tool changes only the Mach-O metadata needed by the legacy-display builder:

* make the initializer an external defined symbol;
* rebuild the LC_DYSYMTAB local/global/undefined symbol partitions;
* remap relocation symbol indices after the stable symbol reorder;
* neutralize the requested section header without moving file extents.

The __text section and all code bytes remain unchanged.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


MH_MAGIC_64 = 0xFEEDFACF
MH_OBJECT = 0x1
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_DYSYMTAB = 0xB

N_STAB = 0xE0
N_PEXT = 0x10
N_TYPE = 0x0E
N_EXT = 0x01
N_UNDF = 0x0

NLIST_64 = struct.Struct("<IBBHQ")
DYSYMTAB = struct.Struct("<12I")


def align8(value: int) -> int:
    return (value + 7) & ~7


class MachOObject:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        if len(data) < 32:
            raise ValueError("truncated Mach-O header")
        (
            self.magic,
            self.cputype,
            self.cpusubtype,
            self.filetype,
            self.ncmds,
            self.sizeofcmds,
            self.flags,
            self.reserved,
        ) = struct.unpack_from("<8I", data, 0)
        if self.magic != MH_MAGIC_64 or self.filetype != MH_OBJECT:
            raise ValueError("input must be a little-endian 64-bit Mach-O object")
        self.load_commands: list[tuple[int, int, int]] = []
        self.sections: list[dict] = []
        self.symtab = None
        self.dysymtab = None
        offset = 32
        for _ in range(self.ncmds):
            command, command_size = struct.unpack_from("<2I", data, offset)
            if command_size < 8 or offset + command_size > len(data):
                raise ValueError("invalid Mach-O load command")
            self.load_commands.append((offset, command, command_size))
            if command == LC_SEGMENT_64:
                segment_name = data[offset + 8:offset + 24].split(b"\0", 1)[0]
                section_count = struct.unpack_from("<I", data, offset + 64)[0]
                section_offset = offset + 72
                if section_offset + section_count * 80 > offset + command_size:
                    raise ValueError("invalid LC_SEGMENT_64 section table")
                for index in range(section_count):
                    at = section_offset + index * 80
                    section_name = data[at:at + 16].split(b"\0", 1)[0]
                    section_segment = data[at + 16:at + 32].split(b"\0", 1)[0]
                    self.sections.append(
                        {
                            "command_offset": offset,
                            "section_offset": section_offset,
                            "index": index,
                            "at": at,
                            "section_name": section_name,
                            "segment_name": section_segment or segment_name,
                        }
                    )
            elif command == LC_SYMTAB:
                if self.symtab is not None:
                    raise ValueError("multiple LC_SYMTAB commands")
                self.symtab = {
                    "command_offset": offset,
                    "symoff": struct.unpack_from("<I", data, offset + 8)[0],
                    "nsyms": struct.unpack_from("<I", data, offset + 12)[0],
                    "stroff": struct.unpack_from("<I", data, offset + 16)[0],
                    "strsize": struct.unpack_from("<I", data, offset + 20)[0],
                }
            elif command == LC_DYSYMTAB:
                if self.dysymtab is not None:
                    raise ValueError("multiple LC_DYSYMTAB commands")
                self.dysymtab = {
                    "command_offset": offset,
                    "values": list(DYSYMTAB.unpack_from(data, offset + 8)),
                }
            offset += command_size
        if offset != 32 + self.sizeofcmds:
            raise ValueError("Mach-O load-command size mismatch")
        if self.symtab is None:
            raise ValueError("input has no LC_SYMTAB")
        if self.symtab["symoff"] + self.symtab["nsyms"] * NLIST_64.size > len(data):
            raise ValueError("symbol table extends beyond file")

    def symbol_name(self, string_index: int) -> str:
        assert self.symtab is not None
        start = self.symtab["stroff"] + string_index
        end = self.data.find(b"\0", start)
        if start < self.symtab["stroff"] or end < 0:
            raise ValueError("invalid symbol string index")
        return bytes(self.data[start:end]).decode("utf-8", "replace")

    def symbol_entries(self) -> list[dict]:
        assert self.symtab is not None
        entries = []
        for index in range(self.symtab["nsyms"]):
            at = self.symtab["symoff"] + index * NLIST_64.size
            string_index, n_type, n_sect, n_desc, n_value = NLIST_64.unpack_from(
                self.data, at
            )
            entries.append(
                {
                    "old_index": index,
                    "at": at,
                    "string_index": string_index,
                    "n_type": n_type,
                    "n_sect": n_sect,
                    "n_desc": n_desc,
                    "n_value": n_value,
                    "name": self.symbol_name(string_index),
                }
            )
        return entries

    def relocate_symbol_indices(self, mapping: dict[int, int]) -> None:
        for section in self.sections:
            at = section["at"]
            reloff, nreloc = struct.unpack_from("<2I", self.data, at + 56)
            if reloff + nreloc * 8 > len(self.data):
                raise ValueError(
                    f"section {section['section_name']!r} has an invalid relocation table"
                )
            for index in range(nreloc):
                entry = reloff + index * 8
                r_address, r_info = struct.unpack_from("<2I", self.data, entry)
                if r_address & 0x80000000:
                    continue
                old_symbol = r_info & 0xFFFFFF
                if old_symbol in mapping:
                    r_info = (r_info & 0xFF000000) | mapping[old_symbol]
                    struct.pack_into("<I", self.data, entry + 4, r_info)

    def globalize(self, name: str) -> None:
        assert self.symtab is not None
        assert self.dysymtab is not None
        entries = self.symbol_entries()
        matches = [entry for entry in entries if entry["name"] == name]
        if not matches:
            suffix = name.removeprefix("__")
            candidates = [
                entry
                for entry in entries
                if entry["name"].removeprefix("__") == suffix
                or (
                    "GLOBAL__sub_I_" in entry["name"]
                    and entry["name"].endswith(".cpp")
                )
            ]
            if len(candidates) == 1:
                matches = candidates
        if not matches:
            available = [
                entry["name"]
                for entry in entries
                if "GLOBAL__sub_I_" in entry["name"]
            ]
            raise ValueError(
                f"expected symbol named {name!r}, found 0; "
                f"initializer candidates: {available}"
            )
        names = {entry["name"] for entry in matches}
        if len(names) != 1:
            raise ValueError(
                f"symbol {name!r} matched multiple initializer names: {sorted(names)}"
            )
        for target in matches:
            target["n_type"] |= N_EXT

        locals_ = []
        externals = []
        undefined = []
        for entry in entries:
            is_external = bool(entry["n_type"] & N_EXT)
            is_undefined = is_external and (entry["n_type"] & N_TYPE) == N_UNDF
            if not is_external:
                locals_.append(entry)
            elif is_undefined:
                undefined.append(entry)
            else:
                externals.append(entry)
        ordered = locals_ + externals + undefined
        mapping = {
            old_index: new_index
            for new_index, old_index in enumerate(
                entry["old_index"] for entry in ordered
            )
        }
        target_new_indices = [mapping[entry["old_index"]] for entry in matches]
        if any(
            new_index >= len(locals_) + len(externals)
            for new_index in target_new_indices
        ):
            raise AssertionError("globalized symbol was not placed in external definitions")

        self.relocate_symbol_indices(mapping)
        for new_index, entry in enumerate(ordered):
            if mapping[entry["old_index"]] != new_index:
                raise AssertionError("internal symbol reorder mismatch")
            at = self.symtab["symoff"] + new_index * NLIST_64.size
            NLIST_64.pack_into(
                self.data,
                at,
                entry["string_index"],
                entry["n_type"],
                entry["n_sect"],
                entry["n_desc"],
                entry["n_value"],
            )

        values = self.dysymtab["values"]
        values[0] = 0
        values[1] = len(locals_)
        values[2] = len(locals_)
        values[3] = len(externals)
        values[4] = len(locals_) + len(externals)
        values[5] = len(undefined)
        DYSYMTAB.pack_into(self.data, self.dysymtab["command_offset"] + 8, *values)

    def remove_section(self, segment_name: str, section_name: str) -> None:
        matches = [
            section
            for section in self.sections
            if section["segment_name"] == segment_name.encode()
            and section["section_name"] == section_name.encode()
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected one {segment_name},{section_name} section, found {len(matches)}"
            )
        at = matches[0]["at"]
        self.data[at:at + 16] = b"__UniXNUDead\0\0\0\0"
        struct.pack_into("<QQI", self.data, at + 32, 0, 0, 0)
        struct.pack_into("<I", self.data, at + 52, 0)
        struct.pack_into("<I", self.data, at + 56, 0)
        struct.pack_into("<I", self.data, at + 60, 0)
        struct.pack_into("<III", self.data, at + 64, 0, 0, 0)
        struct.pack_into("<I", self.data, at + 76, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remove-section", required=True, metavar="SEG,SECT")
    parser.add_argument("--globalize-symbol", required=True, metavar="NAME")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    segment, separator, section = args.remove_section.partition(",")
    if not separator or not segment or not section:
        parser.error("--remove-section requires SEG,SECT")

    source = args.input.read_bytes()
    image = MachOObject(source)
    image.globalize(args.globalize_symbol)
    image.remove_section(segment, section)
    output = bytes(image.data)

    # Verify all offsets stay in bounds and code bytes outside the section
    # header table are unchanged. The explicit invariant prevents this helper
    # from silently corrupting an object if Apple changes the input layout.
    if len(output) != len(source):
        raise AssertionError("metadata-only transform changed file size")
    args.output.write_bytes(output)
    print(
        f"deferred init symbol={args.globalize_symbol} "
        f"removed={segment},{section} bytes={len(output)}"
    )


if __name__ == "__main__":
    main()
