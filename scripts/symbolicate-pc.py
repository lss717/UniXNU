#!/usr/bin/env python3
"""Map an unslid program counter to the function that contains it.

  symbolicate-pc.py IMAGE 0x100012345 [0x100012999 ...]
  symbolicate-pc.py --base 0x100004000 IMAGE 0x100012345      # override the image base
  symbolicate-pc.py --slide 0x1f00000 IMAGE 0x100012345       # subtract a runtime slide first

Why a separate tool: the kernel can only report a raw user PC.  Apple strips the local
symbol table from shipped binaries, but every arm64 Mach-O keeps LC_FUNCTION_STARTS, a
ULEB128 delta table of function entry addresses.  The containing function plus its offset
is enough to name the call site (or at least to bracket it between two known functions),
and it costs nothing on the device.

Prints one line per address:

  pc=0x... func=0x...(image+0x...) off=0x... symbol=<name|->

`symbol` is only filled when the image still carries a symbol table, or when a symbol
falls exactly on the function start.
"""
import struct
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_FUNCTION_STARTS = 0x26


def uleb128(data, at):
    result = shift = 0
    while True:
        byte = data[at]
        at += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, at
        shift += 7


def load(path):
    blob = Path(path).read_bytes()
    if len(blob) < 32 or struct.unpack_from('<I', blob, 0)[0] != MH_MAGIC_64:
        raise SystemExit(f'{path}: not a thin 64-bit little-endian Mach-O')
    _, _, _, _, ncmds, sizeofcmds, _, _ = struct.unpack_from('<IiiIIIII', blob, 0)
    at = 32
    end = 32 + sizeofcmds
    text_vmaddr = None
    function_starts = None
    symbols = {}
    while at < end:
        cmd, cmdsize = struct.unpack_from('<II', blob, at)
        if cmdsize < 8:
            break
        if cmd == LC_SEGMENT_64:
            name = blob[at + 8:at + 24].split(b'\0', 1)[0].decode('ascii', 'replace')
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', blob, at + 24)
            if name == '__TEXT':
                text_vmaddr = vmaddr
        elif cmd == LC_FUNCTION_STARTS:
            dataoff, datasize = struct.unpack_from('<II', blob, at + 8)
            function_starts = (dataoff, datasize)
        elif cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', blob, at + 8)
            for index in range(nsyms):
                strx, ntype, nsect, ndesc, nvalue = struct.unpack_from('<IBBHQ', blob, symoff + index * 16)
                if ntype & 0x0E != 0x0E:      # N_SECT only: skip stabs/undefined
                    continue
                start = stroff + strx
                symbols.setdefault(nvalue, blob[start:blob.index(b'\0', start)].decode('ascii', 'replace'))
        at += cmdsize
    if text_vmaddr is None:
        raise SystemExit(f'{path}: no __TEXT segment')
    starts = []
    if function_starts:
        dataoff, datasize = function_starts
        cursor = dataoff
        address = text_vmaddr
        limit = dataoff + datasize
        while cursor < limit:
            delta, cursor = uleb128(blob, cursor)
            if delta == 0:
                break
            address += delta
            starts.append(address)
    return text_vmaddr, starts, symbols


def main():
    args = [a for a in sys.argv[1:]]
    base = None
    slide = 0
    while args and args[0].startswith('--'):
        flag = args.pop(0)
        if flag == '--base':
            base = int(args.pop(0), 0)
        elif flag == '--slide':
            slide = int(args.pop(0), 0)
        else:
            raise SystemExit(f'unknown option {flag}')
    if len(args) < 2:
        raise SystemExit(__doc__)
    image = args[0]
    text_vmaddr, starts, symbols = load(image)
    if base is not None:
        text_vmaddr = base
    print(f'image {image} text=0x{text_vmaddr:x} functions={len(starts)} symbols={len(symbols)}')
    for text in args[1:]:
        pc = int(text, 0) - slide
        if not starts:
            print(f'pc=0x{pc:x} func=none (no LC_FUNCTION_STARTS)')
            continue
        low, high = 0, len(starts)
        while low < high:
            middle = (low + high) // 2
            if starts[middle] <= pc:
                low = middle + 1
            else:
                high = middle
        if low == 0:
            print(f'pc=0x{pc:x} below the first function start 0x{starts[0]:x}')
            continue
        start = starts[low - 1]
        name = symbols.get(start, '-')
        print(f'pc=0x{pc:x} func=0x{start:x}(image+0x{start - text_vmaddr:x}) off=0x{pc - start:x} symbol={name}')


if __name__ == '__main__':
    main()
