#!/usr/bin/env python3
"""Check that the payload command line leaves room for DarwinBoot's zap-base.

H236cv: the payload args were already 997 characters and DarwinBoot's old
"len + 32 < 1024" test silently skipped appending `zap-base=0x...`; NativeA540C3
then logged "zap-base missing or invalid: 0" and C3 stopped. The loader now
measures the formatted argument, but a longer command line can still run out of
room (the boot_args CommandLine field is 1024 bytes).

Usage:
    python3 scripts/check-bootargs-fit.py --payload /tmp/opencode/payload-H236da.img
    python3 scripts/check-bootargs-fit.py --toml path/to/unixnu.toml

Exit status 1 when even the current value cannot be appended; 2 when it fits
today but the 16-hex-digit worst case would not (a warning, not a failure).
"""
import argparse
import pathlib
import re
import shutil
import subprocess
import sys

LIMIT = 1024
PREFIX = ' zap-base=0x'


def toml_from_payload(image: pathlib.Path) -> str:
    mtype = shutil.which('mtype')
    if not mtype:
        raise SystemExit('mtype (mtools) is required for --payload')
    result = subprocess.run([mtype, '-i', str(image), '::/EFI/UniXNU/unixnu.toml'],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'mtype failed: {result.stderr.strip()}')
    return result.stdout


def args_of(toml: str) -> str:
    for line in toml.splitlines():
        match = re.match(r'\s*args\s*=\s*"(.*)"\s*$', line)
        if match:
            return match.group(1)
    raise SystemExit('no args = "..." line in unixnu.toml')


def main():
    ap = argparse.ArgumentParser()
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--payload', type=pathlib.Path, help='UniXNU payload FAT image')
    source.add_argument('--toml', type=pathlib.Path, help='unixnu.toml directly')
    ap.add_argument('--address', default='0xABE00000',
                    help='zap-base value used for the length estimate (default 8 hex digits)')
    args = ap.parse_args()

    text = toml_from_payload(args.payload) if args.payload else args.toml.read_text()
    command = args_of(text)
    base = args.address.lower().removeprefix('0x')
    current = len(command) + len(PREFIX) + len(base)
    worst = len(command) + len(PREFIX) + 16
    print(f'args length            {len(command)}')
    print(f'+ zap-base=0x{base}   {current} / {LIMIT} bytes')
    print(f'+ 16 hex digits       {worst} / {LIMIT} bytes (worst case)')
    if current + 1 > LIMIT:
        print('FAIL: zap-base does not fit; shorten the payload args', file=sys.stderr)
        return 1
    if worst + 1 > LIMIT:
        print('WARN: fits only while zap-base has <= %d hex digits' % (LIMIT - 1 - len(command) - len(PREFIX)))
        return 2
    print('OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
