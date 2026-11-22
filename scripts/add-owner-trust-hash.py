#!/usr/bin/env python3
"""Add or replace CDHashes in the owner module of an existing boot trust cache.

  add-owner-trust-hash.py [--replace OLD[,OLD...]] BASE.trustcache HASH[,HASH...] OUTPUT

The boot image carries /EFI/UniXNU/Payloads/kernel.macho.trustcache: module 0 is
the owner module built by make-owner-trust-bundle.py, then the two original Apple
modules byte for byte. A target image that has no unpacked original trust bundle
(such as the incremental build host) can still trust one more owner binary by
inserting its CDHash into module 0 and leaving the Apple modules untouched. The
loader (DarwinBoot ValidTrustCaches, the kernel binary search) needs the hashes
of a module in strictly ascending order, so the entries are re-sorted.

H236gc: a rebuilt Metal plugin bundle is ad-hoc signed, and AMFI rejects it for
backboardd with "unsuitable CT policy 0" / "Library Validation failed"; the same
bundle loads once its CDHash is in this cache.
"""
import struct
import sys
from pathlib import Path


def parse(blob: bytes):
    count = struct.unpack_from('<I', blob)[0]
    if not 0 < count <= 128:
        raise SystemExit('Not a trust bundle: module count %d' % count)
    starts = list(struct.unpack_from('<%dI' % count, blob, 4))
    modules = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < count else len(blob)
        modules.append(blob[start:end])
    return modules


def entries(module: bytes):
    version, identifier, count = struct.unpack_from('<I16sI', module)
    return version, identifier, [module[24 + 24 * i:24 + 24 * (i + 1)] for i in range(count)]


def validate(data: bytes) -> None:
    """The structural checks of drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c ValidTrustCaches."""
    count = struct.unpack_from('<I', data)[0]
    if not 0 < count <= 128:
        raise SystemExit('Refusing to write: bad module count %d' % count)
    for index in range(count):
        start = struct.unpack_from('<I', data, 4 + 4 * index)[0]
        end = struct.unpack_from('<I', data, 8 + 4 * index)[0] if index + 1 < count else len(data)
        if start < 4 + 4 * count or start & 3 or end > len(data) or end - start < 24 \
                or struct.unpack_from('<I', data, start)[0] != 2:
            raise SystemExit('Refusing to write: module %d is malformed' % index)
        total = struct.unpack_from('<I', data, start + 20)[0]
        if end - start != 24 + total * 24:
            raise SystemExit('Refusing to write: module %d entry count disagrees' % index)
        for entry in range(total):
            at = start + 24 + entry * 24
            if not 1 <= data[at + 20] <= 4 or (entry and data[at - 24:at - 4] >= data[at:at + 20]):
                raise SystemExit('Refusing to write: module %d is not sorted' % index)


def main() -> int:
    args = sys.argv[1:]
    replace = []
    if "--replace" in args:
        at = args.index("--replace")
        if at + 1 >= len(args):
            sys.exit("--replace takes comma-separated 20-byte CDHashes")
        replace = [bytes.fromhex(h) for h in args[at + 1].split(",") if h]
        del args[at:at + 2]
    if len(args) != 3:
        sys.exit(__doc__)
    base, output = Path(args[0]), Path(args[2])
    new = [bytes.fromhex(h) for h in args[1].split(',') if h]
    if any(len(h) != 20 for h in replace):
        raise SystemExit('CDHashes are 20 bytes (40 hex digits)')
    if any(len(h) != 20 for h in new):
        raise SystemExit('CDHashes are 20 bytes (40 hex digits)')
    modules = parse(base.read_bytes())
    version, identifier, items = entries(modules[0])
    hashes = {item[:20]: item[20:] for item in items}
    missing = [h for h in replace if h not in hashes]
    if missing:
        raise SystemExit('replacement CDHash not present: ' +
                         ','.join(h.hex() for h in missing))
    for h in replace:
        del hashes[h]
    for h in new:
        hashes.setdefault(h, bytes([2, 0, 0, 0]))
    ordered = [h + flags for h, flags in sorted(hashes.items())]
    own = struct.pack('<I16sI', version, identifier, len(ordered)) + b''.join(ordered)
    built = [own, *modules[1:]]
    cursor, starts = 16, []
    for module in built:
        starts.append(cursor)
        cursor += len(module)
    blob = struct.pack('<%dI' % (1 + len(built)), len(built), *starts) + b''.join(built)
    validate(blob)
    output.write_bytes(blob)
    print('replaced %d, added %d hash(es); owner module now %d entries; '
          'bundle %d bytes -> %s'
          % (len(replace), len(new), len(ordered), len(blob), output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
