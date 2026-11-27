#!/usr/bin/env python3
"""Locate the original IOMobileFramebufferLegacy ABI in an OP5 21H461 kernelcache."""
import argparse, hashlib, json, plistlib, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kits/NativePrelink'))
from native_prelink import macho, backed_offset

FAMILY = 'com.apple.iokit.IOMobileGraphicsFamily'
EXPECTED_TEXT_SHA = '2e044ee68c1650397e1435234ca6459206262e4c7ed709cb7131c6f664f9bd9b'
PURE = [211,213,245,246,306,307,337,338,345]
SLOTS = 358

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kernelcache', type=Path)
    ap.add_argument('--out', type=Path, default=Path('build/display-analysis/mobile-graphics-legacy-abi.json'))
    a = ap.parse_args()
    data = a.kernelcache.read_bytes()
    outer = macho(data)
    # __PRELINK_INFO __info is a bare <dict> plist padded with NULs.
    info = None
    for seg in outer['segments']:
        for sec in seg['sections']:
            if sec['name'] == '__info' and seg['name'] == '__PRELINK_INFO':
                info = sec
    if not info:
        raise SystemExit('no __PRELINK_INFO/__info')
    raw = data[info['fileoff']:info['fileoff'] + info['size']]
    end = raw.rfind(b'</dict>') + len(b'</dict>')
    blob = b'<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0">' + raw[:end] + b'</plist>\n'
    import re
    blob = re.sub(rb'<integer([^>]*)/>', rb'<integer\1>0</integer>', blob)
    blob = re.sub(rb'<string([^>]*)/>', rb'<string\1></string>', blob)
    pl = plistlib.loads(blob)
    entry = next(e for e in pl['_PrelinkInfoDictionary'] if e.get('CFBundleIdentifier') == FAMILY)
    load = entry['_PrelinkExecutableLoadAddr']
    hdr = macho(data, backed_offset(outer['segments'], load, 32, len(data)))
    text = next(s for s in hdr['segments'] if s['name'] == '__TEXT_EXEC')
    # The embedded segment file offsets are relative to the original kext;
    # map the absolute segment VA through the outer prelinked kernel.
    text_fo = backed_offset(outer['segments'], text['va'], text['size'], len(data))
    code = data[text_fo:text_fo + text['size']]
    sha = hashlib.sha256(code).hexdigest()
    if sha != EXPECTED_TEXT_SHA:
        raise SystemExit(f'unexpected family text {sha}')

    def read(va, n):
        o = backed_offset(outer['segments'], va, n, len(data))
        return data[o:o + n]
    def q(va):
        return struct.unpack('<Q', read(va, 8))[0]

    def vptr(pc):
        a, b, c = struct.unpack('<3I', read(pc, 12))
        if not ((a & 0x9f00001f) == 0x90000008 and (b & 0xffc003ff) == 0x91000108 and c == 0x91004108):
            return None
        imm = ((a >> 5) & 0x7ffff) * 4 + ((a >> 29) & 3)
        if imm & (1 << 20): imm -= 1 << 21
        return (pc & ~4095) + (imm << 12) + ((b >> 10) & 4095)

    candidates = []
    for pc in range(text['va'], text['va'] + text['size'] - 12, 4):
        vt = vptr(pc)
        if vt is None: continue
        try:
            entries = [q(vt + 16 + i * 8) for i in range(SLOTS)]
        except ValueError:
            continue
        if all(entries):
            candidates.append((pc, vt, entries))
    legacy = [c for c in candidates if c[2][211] == 0xfffffff0077785e0 and c[2][337] == 0xfffffff0077785e0]
    if len(legacy) != 1:
        raise SystemExit(f'legacy vtable candidates {len(legacy)} of {len(candidates)}')
    pc, vtable, entries = legacy[0]
    if [i for i, e in enumerate(entries) if e == 0xfffffff0077785e0] != PURE:
        raise SystemExit('abstract slots differ from the known original layout')
    out = dict(
        source_kernelcache_sha256=hashlib.sha256(data).hexdigest(),
        original_family_text_sha256=sha,
        family_load_addr=hex(load),
        family_text_va=hex(text['va']), family_text_size=hex(text['size']),
        legacy_constructor_vptr_pc=hex(pc),
        legacy_vtable=hex(vtable), legacy_method_table=hex(vtable + 16),
        legacy_virtual_entries=SLOTS, legacy_instance_bytes=0x18a0,
        abstract_slots=PURE,
        methods=[dict(slot=i, address=hex(e), abstract=i in PURE) for i, e in enumerate(entries)],
        bindings=dict(
            legacy_gMetaClass='0xfffffff007b35940',
            legacy_constructor='0xfffffff0067865cc',
            legacy_destructor='0xfffffff006786618',
            legacy_vtable='0xfffffff006f38560',
            pure_virtual='0xfffffff0077785e0',
            iosurface_descriptor='0xfffffff005b9ead0',
            iosurface_id='0xfffffff005b9ec14',
            iosurface_width='0xfffffff005b9ebbc',
            iosurface_height='0xfffffff005b9ebc4',
            iosurface_stride='0xfffffff005b9ebd4',
            iosurface_allocation='0xfffffff005b9ebfc',
            iosurface_format='0xfffffff005b9ebac',
            iosurface_planes='0xfffffff005b9ebf4',
            vsync_notify='0xfffffff006796720',
            set_refresh_properties='0xfffffff00679ebb8',
            client_initializer='0xfffffff006776810',
        ),
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2) + '\n')
    print('PASS: OP5 Legacy constructor', hex(pc), 'vtable', hex(vtable), '358 slots,', len(PURE), 'abstract')

if __name__ == '__main__':
    main()
