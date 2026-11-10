#!/usr/bin/env python3
"""Pack the real Adreno Metal plugin as a GPU addon with a 16-character bundle directory name.

make-gpu-addon.py hardcodes addons/NativeAdrenoMetal.bundle; the kernel's _offline-accelerator-plugin
argument copies at most 16 characters, so the staging directory name must be shortened to match what
MetalPluginName can carry ("NativeAdreno"). The bundle's CFBundleExecutable stays NativeAdrenoMetal.
"""
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'build/adreno-metal-plugin'
BUNDLE = PLUGIN / 'NativeAdrenoMetal.bundle'
ADDON_NAME = 'NativeAdreno.bundle'


def pad(data: bytes) -> bytes:
    return data + bytes(-len(data) % 8)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if len(args) != 1 or flags - {'--trace', '--publish'}:
        sys.exit(__doc__)
    output = Path(args[0]).resolve()
    if output.exists():
        sys.exit('Refuse to overwrite ' + str(output))
    if not (BUNDLE / 'NativeAdrenoMetal').is_file():
        sys.exit('Build the plugin first: python3 scripts/build-adreno-metal-plugin.py')
    files = []
    for path in sorted(p for p in BUNDLE.rglob('*') if p.is_file()):
        mode = 0o755 if path.name in ('NativeAdrenoMetal', 'libvulkan_freedreno.dylib') else 0o644
        files.append(('addons/' + ADDON_NAME + '/' + path.relative_to(BUNDLE).as_posix(), mode, path.read_bytes()))
    if (PLUGIN / 'adrenoprobed').is_file():
        files.append(('bin/adrenoprobed', 0o755, (PLUGIN / 'adrenoprobed').read_bytes()))
    # H236ft: the plugin returns the native Metal device only when this marker
    # sits beside the bundle in /System/Library/Extensions (the addons/ tree is
    # mounted there by zzy-native-gpu-addon-mount). Without it the principal
    # class runs the ABI test and returns nil, so CoreAnimation never gets a
    # device.
    if '--publish' in flags:
        files.append(('addons/NativeAdrenoMetal.publish', 0o644, b'1\n'))
    if '--trace' in flags:
        files.append(('addons/NativeAdrenoMetal.trace', 0o644, b'1\n'))
    for plist in sorted(PLUGIN.glob('*.plist')):
        if not plist.name.endswith('-entitlements.plist') and plist.is_file():
            files.append(('daemons/' + plist.name, 0o644, plist.read_bytes()))
    body = b''
    for name, mode, data in files:
        encoded = name.encode() + b'\0'
        if len(encoded) > 160 or '..' in name.split('/') or name.startswith('/'):
            sys.exit('Bad addon path ' + name)
        packed = zlib.compress(data, 9)
        # H208: every entry carries the CRC-32 of its stored bytes so the kernel can tell an
        # intact boot-time addon block from one that was overwritten (the H205-H207 21.7 MB
        # plugin stream decoded 32 bytes past its size with Z_DATA_ERROR in the kernel although
        # the host zlib 1.2.3 decodes the same file exactly). Entries are stored as they are
        # only when compression does not help: the boot image cannot exceed ~81 MB (H86f), so
        # the plugin must stay compressed.
        stored = len(packed) >= len(data)
        if stored:
            packed = data
        body += struct.pack('<IIQQII', len(encoded), mode, len(data), len(packed),
                            zlib.crc32(packed) & 0xffffffff, 1 if stored else 0) + pad(encoded) + pad(packed)
    # H217: this port's boot window loses exactly 8 bytes at a fixed addon offset. H214-H216
    # narrowed it to addon+0x7b9aa0 becoming 00 f0 7f 80 00 00 00 00 (8-byte aligned store,
    # physical 0x186711aa0) while the payload file itself is byte-identical and every other
    # byte matches. The repair table travels with the addon: it records the observed wrong
    # bytes and the original ones, and the kernel restores them only when the current bytes
    # match the record, so a changed layout can never be "repaired" blindly.
    REPAIRS = [(0x7b9800, bytes.fromhex('00f07f8000000000'))]
    repairs = b''
    for offset, wrong in REPAIRS:
        if offset + len(wrong) > len(body):
            sys.exit('repair offset past the addon body')
        original = body[offset - 24:offset - 24 + len(wrong)]
        repairs += struct.pack('<QII', offset, len(wrong), 0) + wrong + original
    if repairs:
        repairs = struct.pack('<I', len(REPAIRS)) + repairs
    repair_off = 24 + len(body) if repairs else 0
    blob = (b'NGPUADD2' + struct.pack('<IIQ', len(files), repair_off, 24 + len(body) + len(repairs)) +
            body + repairs)
    output.write_bytes(blob)
    for name, mode, data in files:
        print(f'{mode:o} {len(data):>10} {name}')
    if repairs:
        for offset, wrong in REPAIRS:
            print(f'repair {offset:#x}: {wrong.hex()} <- '
                  f'{body[offset - 24:offset - 24 + len(wrong)].hex()}')
    print(f'{output}: {len(files)} files, {len(blob)} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
