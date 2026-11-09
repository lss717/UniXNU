#!/usr/bin/env python3
"""Check the A540 ZAP PAS layout against the vendor .mdt rules.

The 2026-11-10 bring-up showed that guessing this layout is expensive:

* the a540_zap.elf and a540_zap.mdt are both ELF32 with three program
  headers, but only .b02 is PT_LOAD; .b00/.b01 are type 0 (header/hash);
* PAS therefore wants first=0x5000, extent=0x2000, with .b02 at offset 0 of
  the image, and the whole .mdt (header 0x94 + hash 0x1988) as metadata;
* handing over a "full 0x9000 image" built from every file-backed phdr makes
  PAS_AUTH fail with -68 (H236cy), and .b02 with a page-aligned length breaks
  NativeRamBlock-style exact-size checks (H236cn).

Run it against the private firmware cache (never commit the blobs):

    python3 scripts/check-zap-layout.py --firmware ~/.cache/firmware/a540

It only reads, prints the derived layout, and fails on anything unexpected.
"""
import argparse
import pathlib
import struct
import sys


def phdrs32(data):
    if data[:4] != b'\x7fELF' or data[4] != 1:
        raise SystemExit('expected an ELF32 file')
    phoff = struct.unpack_from('<I', data, 0x1c)[0]
    phentsize = struct.unpack_from('<H', data, 0x2a)[0]
    phnum = struct.unpack_from('<H', data, 0x2c)[0]
    out = []
    for index in range(phnum):
        off = phoff + index * phentsize
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = \
            struct.unpack_from('<IIIIIIII', data, off)
        out.append(dict(type=p_type, offset=p_offset, vaddr=p_vaddr, paddr=p_paddr,
                        filesz=p_filesz, memsz=p_memsz, flags=p_flags, align=p_align))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--firmware', type=pathlib.Path, default=pathlib.Path('.cache/firmware/a540'))
    args = ap.parse_args()

    mdt = (args.firmware / 'a540_zap.mdt').read_bytes()
    b02 = (args.firmware / 'a540_zap.b02').read_bytes()
    segments = phdrs32(mdt)

    load = [s for s in segments if s['type'] == 1 and s['memsz']]
    hash_entry = None
    for s in segments:
        if (s['flags'] >> 24) & 7 == 2:
            hash_entry = s
    if len(load) != 1 or load[0]['filesz'] != len(b02):
        print('FAIL: expected exactly one PT_LOAD of the .b02 size', file=sys.stderr)
        for s in segments:
            print('  type=%d paddr=%#x filesz=%#x memsz=%#x flags=%#x align=%#x'
                  % (s['type'], s['paddr'], s['filesz'], s['memsz'], s['flags'], s['align']),
                  file=sys.stderr)
        return 1

    seg = load[0]
    first = seg['paddr']
    extent = (seg['paddr'] + seg['memsz'] + 0xfff) & ~0xfff
    extent -= first
    alignment = max(s['align'] for s in load)
    relocate = bool(seg['flags'] & (1 << 27))
    header_bytes = segments[0]['filesz']
    hash_bytes = hash_entry['filesz'] if hash_entry else 0
    metadata = header_bytes + hash_bytes

    print('a540 ZAP PAS layout:')
    print('  metadata   %#x bytes (header %#x + hash %#x), mdt file %#x'
          % (metadata, header_bytes, hash_bytes, len(mdt)))
    print('  first      %#x (segment paddr, image offset 0)' % first)
    print('  extent     %#x bytes' % extent)
    print('  alignment  %#x' % alignment)
    print('  relocate   %s' % ('yes' if relocate else 'no'))
    print('  image      .b02 %#x bytes at offset 0x0' % len(b02))

    ok = True
    if metadata != len(mdt):
        print('  note: metadata is a prefix of the .mdt (PAS takes the first %#x bytes)' % metadata)
    if len(b02) > extent:
        print('FAIL: .b02 larger than the image extent', file=sys.stderr)
        ok = False
    if first & 0xfff:
        print('FAIL: first is not page aligned', file=sys.stderr)
        ok = False
    if relocate and alignment < 0x1000:
        print('FAIL: relocatable image needs a real alignment', file=sys.stderr)
        ok = False
    print('OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
