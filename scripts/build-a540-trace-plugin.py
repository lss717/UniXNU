#!/usr/bin/env python3
"""Build the standalone A540 Metal trace plugin and pack it as a GPU addon.

The bundle depends only on Foundation/IOKit, so it is the minimal probe of
"does CoreAnimation accept this Metal plugin at all". Output:
build/a540-trace/A540Trace.bundle plus the addon image given on the command
line (addons/A540Trace.bundle/...), which the kernel mounts over
/System/Library/Extensions.
"""
import json
import plistlib
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/a540-trace'
BUNDLE = OUT / 'A540Trace.bundle'


def pad(data: bytes) -> bytes:
    return data + bytes(-len(data) % 8)


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    output = Path(sys.argv[1]).resolve()
    if output.exists():
        sys.exit('Refuse to overwrite ' + str(output))
    BUNDLE.mkdir(parents=True, exist_ok=True)
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    executable = BUNDLE / 'A540Trace'
    subprocess.run(['xcrun', 'clang++', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk,
                    '-Os', '-Wall', '-Wextra', '-Werror', '-fstack-protector-strong',
                    '-std=c++17', '-fobjc-arc', '-bundle',
                    '-framework', 'Foundation', '-framework', 'IOKit', '-framework', 'Metal',
                    str(ROOT / 'drivers/NativeMetal/A540TracePlugin.mm'), '-o', str(executable)], check=True)
    subprocess.run(['strip', '-x', str(executable)], check=True)
    (BUNDLE / 'Info.plist').write_bytes(plistlib.dumps(dict(
        CFBundleIdentifier='org.blu-sharky.A540Trace', CFBundleExecutable='A540Trace',
        CFBundlePackageType='BNDL', CFBundleVersion='1', CFBundleShortVersionString='1',
        NSPrincipalClass='A540TraceDevice', MinimumOSVersion='17.0'), fmt=plistlib.FMT_XML))
    subprocess.run(['codesign', '--force', '--sign', '-', '--pagesize', '4096',
                    '--identifier', 'org.blu-sharky.A540Trace', str(BUNDLE)], check=True)
    subprocess.run(['codesign', '--verify', '--strict', str(BUNDLE)], check=True)
    detail = subprocess.run(['codesign', '--display', '--verbose=4', str(BUNDLE)],
                            capture_output=True, text=True, check=True).stderr
    cdhash = next(line.split('=')[1].strip() for line in detail.splitlines() if line.startswith('CDHash='))
    # make-owner-trust-bundle.py reads this shape; AMFI only accepts the bundle
    # when its CDHash is in the boot trust cache (H236gc: ad-hoc alone is not
    # enough, backboardd's Library Validation rejects it).
    (OUT / 'trust.json').write_text(json.dumps({'cdhashes': [cdhash], 'plugin': 'A540Trace',
                                                'purpose': 'standalone Metal trace plugin'}, indent=2) + '\n')
    files = []
    for path in sorted(p for p in BUNDLE.rglob('*') if p.is_file()):
        mode = 0o755 if path.name == 'A540Trace' else 0o644
        files.append(('addons/A540Trace.bundle/' + path.relative_to(BUNDLE).as_posix(), mode, path.read_bytes()))
    body = b''
    for name, mode, data in files:
        encoded = name.encode() + b'\0'
        if len(encoded) > 160 or '..' in name.split('/') or name.startswith('/'):
            sys.exit('Bad addon path ' + name)
        packed = zlib.compress(data, 9)
        stored = len(packed) >= len(data)
        if stored:
            packed = data
        body += struct.pack('<IIQQII', len(encoded), mode, len(data), len(packed),
                            zlib.crc32(packed) & 0xffffffff, 1 if stored else 0) + pad(encoded) + pad(packed)
    blob = (b'NGPUADD2' + struct.pack('<IIQ', len(files), 0, 24 + len(body)) + body)
    output.write_bytes(blob)
    for name, mode, data in files:
        print(f'{mode:o} {len(data):>10} {name}')
    print(f'addon {len(blob)} bytes -> {output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
