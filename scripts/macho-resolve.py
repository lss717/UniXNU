#!/usr/bin/env python3
"""Resolve runtime addresses of a shared-cache process to image + offset.

  macho-resolve.py EXTRACT_DIR RUNTIME_BASE KNOWN_VMADDR ADDR...

EXTRACT_DIR holds the dylibs exported from the cache (dsc_extractor layout).
RUNTIME_BASE is the load address of the image whose cache vmaddr is KNOWN_VMADDR
(take it from the kernel's NATIVE_TRAP_IMAGE_ROW line); every image in the shared
cache moves by the same slide, so one pair is enough.
"""
import struct
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19


def image_range(path):
    with path.open('rb') as f:
        header = f.read(32)
        if len(header) < 32:
            return None
        magic, _, _, _, ncmds, _, _, _ = struct.unpack('<IiiIIIII', header)
        if magic != MH_MAGIC_64:
            return None
        cursor = 32
        for _ in range(ncmds):
            f.seek(cursor)
            raw = f.read(8)
            if len(raw) < 8:
                return None
            cmd, size = struct.unpack('<II', raw)
            if size < 8:
                return None
            if cmd == LC_SEGMENT_64:
                body = f.read(64)
                name, vmaddr, vmsize = struct.unpack('<16sQQ', body[:32])
                if name.rstrip(b'\0') == b'__TEXT':
                    return vmaddr, vmsize
            cursor += size
    return None


def main():
    root, runtime_base, known_vmaddr = Path(sys.argv[1]), int(sys.argv[2], 0), int(sys.argv[3], 0)
    addresses = [int(a, 0) for a in sys.argv[4:]]
    slide = runtime_base - known_vmaddr
    print('slide 0x%x' % slide)
    images = []
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            span = image_range(path)
        except OSError:
            continue
        if span:
            images.append((span[0], span[1], path))
    images.sort()
    print('%d images indexed' % len(images))
    for address in addresses:
        unslid = address - slide
        hit = None
        for vmaddr, vmsize, path in images:
            if vmaddr <= unslid < vmaddr + vmsize:
                hit = (vmaddr, path)
                break
        if hit:
            print('0x%x -> %s + 0x%x' % (address, hit[1].relative_to(root), unslid - hit[0]))
        else:
            print('0x%x -> (unslid 0x%x) no image' % (address, unslid))


if __name__ == '__main__':
    main()
